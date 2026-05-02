"""CP-SAT solver for Problem 2: All workshops with Crew 1 only."""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from ortools.sat.python.cp_model import CpModel, CpSolver, OPTIMAL, FEASIBLE

from models import (
    Process, Equipment, EquipmentType, OperationRequirement,
    ScheduledOperation, ScheduleResult
)
from preprocessing import Preprocessor
from time_utils import calculate_processing_time, calculate_transport_time, format_seconds


class CpModelBuilderV2:
    """
    CP-SAT model for Problem 2.

    All workshops (A-E), only crew 1 equipment.
    Same workshop processes must be sequential.
    Equipment transport times explicitly modeled via optional intervals.
    """

    def __init__(
        self,
        preprocessor: Preprocessor,
        crew: int = 1,
        distance_func=None
    ):
        self.preprocessor = preprocessor
        self.crew = crew
        self.distance_func = distance_func
        self.workshops = ['A', 'B', 'C', 'D', 'E']

        self.processes = preprocessor.expanded_processes
        self.equipment = [e for e in preprocessor.equipment if e.crew == crew]

        self.equipment_by_type: Dict[EquipmentType, List[Equipment]] = {}
        for eq in self.equipment:
            if eq.equipment_type not in self.equipment_by_type:
                self.equipment_by_type[eq.equipment_type] = []
            self.equipment_by_type[eq.equipment_type].append(eq)

        self.process_order = preprocessor.process_order_within_workshop

        self.model: Optional[CpModel] = None

        # (pid, equipment_id) -> BoolVar selector
        self._select_vars: Dict[Tuple[str, str], any] = {}

        # (pid, equipment_id) -> IntVar start
        self._start_vars: Dict[Tuple[str, str], any] = {}

        # (pid, equipment_id) -> IntVar end
        self._end_vars: Dict[Tuple[str, str], any] = {}

        # pid -> IntVar (process start, shared across equipment for same process)
        self._proc_start: Dict[str, any] = {}

        # pid -> IntVar (max of selected equipment ends)
        self._proc_end: Dict[str, any] = {}

        # (pid, equipment_id) -> IntervalVar
        self._intervals: Dict[Tuple[str, str], any] = {}

        self._makespan: any = None

        self.crew_location = f"Crew {self.crew}"

    def get_transport_time(self, from_loc: str, to_loc: str, speed: float) -> int:
        if self.distance_func is None:
            return 0
        try:
            dist = self.distance_func(from_loc, to_loc)
            return calculate_transport_time(dist, speed)
        except:
            return 0

    def build_model(self) -> CpModel:
        self.model = CpModel()
        max_time = 500000

        # 1. Create process start/end variables
        for proc in self.processes:
            pid = proc.expanded_id
            self._proc_start[pid] = self.model.NewIntVar(0, max_time, f'start_{pid}')
            self._proc_end[pid] = self.model.NewIntVar(0, max_time, f'end_{pid}')

        # 2. For each process and each required equipment type,
        # create selector + optional interval (start, duration, end, selector)
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])
                if not available_eq:
                    raise ValueError(f"No equipment of type {eq_type.name} for crew {self.crew}")

                proc_time = calculate_processing_time(proc.workload, req.efficiency)

                for eq in available_eq:
                    sel = self.model.NewBoolVar(f'sel_{pid}_{eq.equipment_id}')
                    self._select_vars[(pid, eq.equipment_id)] = sel

                    start = self.model.NewIntVar(0, max_time, f'start_{pid}_{eq.equipment_id}')
                    end = self.model.NewIntVar(0, max_time, f'end_{pid}_{eq.equipment_id}')
                    self._start_vars[(pid, eq.equipment_id)] = start
                    self._end_vars[(pid, eq.equipment_id)] = end

                    # Optional interval: when sel=1, start/end define active interval
                    # when sel=0, interval is inactive (start=end=0 by CP-SAT semantics)
                    interval = self.model.NewOptionalIntervalVar(
                        start, proc_time, end, sel,
                        f'interval_{pid}_{eq.equipment_id}'
                    )
                    self._intervals[(pid, eq.equipment_id)] = interval

        # 3. Exactly one equipment per required type per process
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])
                selectors = [self._select_vars[(pid, eq.equipment_id)] for eq in available_eq]
                self.model.Add(sum(selectors) == 1)

        # 4. Process start = min of selected equipment starts
        # Process end = max of selected equipment ends
        for proc in self.processes:
            pid = proc.expanded_id
            equip_starts = []
            equip_ends = []
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])
                for eq in available_eq:
                    equip_starts.append(self._start_vars[(pid, eq.equipment_id)])
                    equip_ends.append(self._end_vars[(pid, eq.equipment_id)])

            if equip_starts:
                self.model.AddMinEquality(self._proc_start[pid], equip_starts)
            if equip_ends:
                self.model.AddMaxEquality(self._proc_end[pid], equip_ends)

        # 5. Initial transport: first operation of each equipment starts at crew location
        for eq in self.equipment:
            for proc in self.processes:
                pid = proc.expanded_id
                key = (pid, eq.equipment_id)
                if key not in self._select_vars:
                    continue

                sel = self._select_vars[key]
                start = self._start_vars[key]
                workshop = proc.workshop

                transport = self.get_transport_time(self.crew_location, workshop, eq.speed_mps)

                # start >= transport_time (only when selected)
                c = self.model.Add(start >= transport)
                c.OnlyEnforceIf(sel)

        # 6. Transport time between consecutive operations on same equipment
        for eq in self.equipment:
            for ws in self.workshops:
                ws_order = self.process_order.get(ws, [])
                for i in range(len(ws_order) - 1):
                    pid_i = ws_order[i]
                    pid_j = ws_order[i + 1]

                    if (pid_i, eq.equipment_id) not in self._select_vars:
                        continue
                    if (pid_j, eq.equipment_id) not in self._select_vars:
                        continue

                    sel_i = self._select_vars[(pid_i, eq.equipment_id)]
                    sel_j = self._select_vars[(pid_j, eq.equipment_id)]
                    start_j = self._start_vars[(pid_j, eq.equipment_id)]
                    end_i = self._end_vars[(pid_i, eq.equipment_id)]

                    # Get workshops for both
                    ws_i = None
                    ws_j = None
                    for p in self.processes:
                        if p.expanded_id == pid_i:
                            ws_i = p.workshop
                        if p.expanded_id == pid_j:
                            ws_j = p.workshop

                    transport = self.get_transport_time(ws_i, ws_j, eq.speed_mps)

                    # start_j >= end_i + transport when both selected
                    c = self.model.Add(start_j >= end_i + transport)
                    c.OnlyEnforceIf(sel_i)
                    c.OnlyEnforceIf(sel_j)

        # 7. Precedence constraints within each workshop (process-level)
        for ws in self.workshops:
            ws_procs = self.process_order.get(ws, [])
            for i in range(len(ws_procs) - 1):
                curr_pid = ws_procs[i]
                next_pid = ws_procs[i + 1]
                self.model.Add(self._proc_end[curr_pid] <= self._proc_start[next_pid])

        # 8. No overlap per equipment (using optional intervals)
        for eq_type, eq_list in self.equipment_by_type.items():
            for eq in eq_list:
                intervals = []
                for proc in self.processes:
                    pid = proc.expanded_id
                    key = (pid, eq.equipment_id)
                    if key in self._intervals:
                        intervals.append(self._intervals[key])

                if len(intervals) > 1:
                    self.model.AddNoOverlap(intervals)

        # 9. Objective: minimize makespan
        all_ends = [self._proc_end[proc.expanded_id] for proc in self.processes]
        self._makespan = self.model.NewIntVar(0, max_time, 'makespan')
        self.model.AddMaxEquality(self._makespan, all_ends)
        self.model.Minimize(self._makespan)

        return self.model

    def get_solution(self, solver: CpSolver = None) -> ScheduleResult:
        """Extract solution from solved model."""
        operations = []

        for proc in self.processes:
            pid = proc.expanded_id

            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])

                for eq in available_eq:
                    key = (pid, eq.equipment_id)
                    sel = self._select_vars.get(key)
                    if sel is None:
                        continue

                    sel_val = solver.Value(sel) if solver else sel.Value()
                    if sel_val == 1:
                        start = solver.Value(self._start_vars[key]) if solver else self._start_vars[key].Value()
                        end = solver.Value(self._end_vars[key]) if solver else self._end_vars[key].Value()

                        # Compute transport time (initial transport from crew)
                        crew_loc = self.crew_location
                        try:
                            dist = self.distance_func(crew_loc, proc.workshop)
                            transport = calculate_transport_time(dist, eq.speed_mps)
                        except:
                            transport = 0

                        operations.append(ScheduledOperation(
                            process=proc,
                            equipment=eq,
                            start_time=int(start),
                            end_time=int(end),
                            transport_time=int(transport)
                        ))

        makespan = solver.Value(self._makespan) if solver else self._makespan.Value()

        return ScheduleResult(
            makespan=int(makespan),
            operations=operations
        )


def solve_problem_2(preprocessor: Preprocessor, distance_func=None) -> ScheduleResult:
    """Solve Problem 2: All workshops with Crew 1 only."""
    builder = CpModelBuilderV2(preprocessor, crew=1, distance_func=distance_func)
    model = builder.build_model()

    solver = CpSolver()
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)
    print(f"Solve status: {status}")

    if status not in (OPTIMAL, FEASIBLE):
        raise RuntimeError(f"No solution found. Status: {status}")

    result = builder.get_solution(solver)

    max_end = max(op.end_time for op in result.operations)
    result.makespan = max_end

    return result


def validate_problem_2(result: ScheduleResult, preprocessor: Preprocessor) -> Tuple[bool, List[str]]:
    """Validate Problem 2 solution using process-level aggregation."""
    from collections import defaultdict

    # 1. Build process-level start/end times
    process_times: Dict[str, Dict] = defaultdict(lambda: {"start": float('inf'), "end": 0, "ops": []})

    for op in result.operations:
        pid = op.process.expanded_id
        process_times[pid]["start"] = min(process_times[pid]["start"], op.start_time)
        process_times[pid]["end"] = max(process_times[pid]["end"], op.end_time)
        process_times[pid]["ops"].append(op)

    # 2. Check within-workshop precedence
    errors = []
    process_order = preprocessor.process_order_within_workshop

    for ws, procs in process_order.items():
        for i in range(len(procs) - 1):
            curr = procs[i]
            next_proc = procs[i + 1]

            curr_end = process_times[curr]["end"]
            next_start = process_times[next_proc]["start"]

            if next_start < curr_end:
                errors.append(f"Workshop {ws}: {curr} ends at {curr_end} but {next_proc} starts at {next_start}")

    # 3. Check equipment no overlap
    equip_ops: Dict[str, List[ScheduledOperation]] = defaultdict(list)
    for op in result.operations:
        equip_ops[op.equipment.equipment_id].append(op)

    for eq_id, ops in equip_ops.items():
        ops_sorted = sorted(ops, key=lambda x: x.start_time)
        for i in range(len(ops_sorted) - 1):
            curr = ops_sorted[i]
            next_op = ops_sorted[i + 1]
            if next_op.start_time < curr.end_time - 1:
                errors.append(f"Equipment {eq_id}: overlap - {curr.process.expanded_id} ends at {curr.end_time} but {next_op.process.expanded_id} starts at {next_op.start_time}")

    # 4. Check all processes are scheduled
    scheduled_procs = {op.process.expanded_id for op in result.operations}
    all_procs = {p.expanded_id for p in preprocessor.expanded_processes}
    missing = all_procs - scheduled_procs
    if missing:
        errors.append(f"Missing processes: {missing}")

    # 5. Check crew 1 only
    for op in result.operations:
        if op.equipment.crew != 1:
            errors.append(f"Equipment {op.equipment.equipment_id} is not from Crew 1")

    # 6. Check process has all required equipment types
    for proc in preprocessor.expanded_processes:
        ops_for_proc = [op for op in result.operations if op.process.expanded_id == proc.expanded_id]
        if not ops_for_proc:
            errors.append(f"Process {proc.expanded_id} has no operations")
        else:
            assigned_types = {op.equipment.equipment_type for op in ops_for_proc}
            required_types = {req.equipment_type for req in proc.requirements}
            if assigned_types != required_types:
                errors.append(f"Process {proc.expanded_id} missing equipment types: {required_types - assigned_types}")

    is_valid = len(errors) == 0
    return is_valid, errors


def export_q2_schedule(result: ScheduleResult, output_path: str = 'outputs/q2_schedule.csv'):
    """Export Problem 2 schedule to CSV."""
    import csv
    import os

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    rows = []
    for i, op in enumerate(sorted(result.operations, key=lambda x: x.start_time), 1):
        rows.append({
            '序号': i,
            '设备编号': op.equipment.equipment_id,
            '起始时间': op.start_time,
            '结束时间': op.end_time,
            '持续工作时间(s)': op.duration,
            '工序编号': op.process.expanded_id,
            '车间': op.process.workshop,
            '运输时间(s)': op.transport_time
        })

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['序号', '设备编号', '起始时间', '结束时间', '持续工作时间(s)', '工序编号', '车间', '运输时间(s)'])
        writer.writeheader()
        writer.writerows(rows)

    print(f"导出至: {output_path}")