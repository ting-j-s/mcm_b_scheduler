"""CP-SAT solver for Problem 3: All workshops with Crew 1 + Crew 2 equipment."""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from ortools.sat.python.cp_model import CpModel, CpSolver, OPTIMAL, FEASIBLE

from models import (
    Process, Equipment, EquipmentType, OperationRequirement,
    ScheduledOperation, ScheduleResult
)
from preprocessing import Preprocessor
from time_utils import calculate_processing_time, calculate_transport_time, format_seconds


class CpModelBuilderV3:
    """
    CP-SAT model for Problem 3.

    All workshops (A-E), crew 1 + crew 2 equipment.
    Same workshop processes must be sequential, different workshops can be parallel.
    Equipment starts at its crew location and may transport between workshops.
    """

    def __init__(
        self,
        preprocessor: Preprocessor,
        distance_func
    ):
        self.preprocessor = preprocessor
        self.distance_func = distance_func
        self.workshops = ['A', 'B', 'C', 'D', 'E']

        # All expanded processes
        self.processes = preprocessor.expanded_processes

        # All equipment (both crews)
        self.equipment = preprocessor.equipment

        # Group equipment by type (ignoring crew)
        self.equipment_by_type: Dict[EquipmentType, List[Equipment]] = {}
        for eq in self.equipment:
            if eq.equipment_type not in self.equipment_by_type:
                self.equipment_by_type[eq.equipment_type] = []
            self.equipment_by_type[eq.equipment_type].append(eq)

        # Process order within each workshop
        self.process_order = preprocessor.process_order_within_workshop

        # Model
        self.model: Optional[CpModel] = None

        # Variables
        self._select_vars: Dict[Tuple[str, str], any] = {}
        self._start_vars: Dict[Tuple[str, str], any] = {}
        self._end_vars: Dict[Tuple[str, str], any] = {}
        self._proc_start: Dict[str, any] = {}
        self._proc_end: Dict[str, any] = {}
        self._intervals: Dict[Tuple[str, str], any] = {}
        self._makespan: any = None

        # Crew locations
        self.crew_locations = {1: "Crew 1", 2: "Crew 2"}

    def get_crew_location(self, crew: int) -> str:
        return self.crew_locations[crew]

    def get_transport_time(self, from_crew: int, to_workshop: str, speed: float) -> int:
        """Get transport time from crew location to workshop."""
        from_loc = self.get_crew_location(from_crew)
        dist = self.distance_func(from_loc, to_workshop)
        return calculate_transport_time(dist, speed)

    def build_model(self) -> CpModel:
        """Build the CP-SAT model."""
        self.model = CpModel()
        max_time = 600000  # ~167 hours max

        # 1. Create process start/end variables
        for proc in self.processes:
            pid = proc.expanded_id
            self._proc_start[pid] = self.model.NewIntVar(0, max_time, f'start_{pid}')
            self._proc_end[pid] = self.model.NewIntVar(0, max_time, f'end_{pid}')

        # 2. Create equipment selection and interval variables
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])

                if not available_eq:
                    raise ValueError(f"No equipment of type {eq_type.name}")

                proc_time = calculate_processing_time(proc.workload, req.efficiency)

                for eq in available_eq:
                    sel = self.model.NewBoolVar(f'sel_{pid}_{eq.equipment_id}')
                    self._select_vars[(pid, eq.equipment_id)] = sel

                    start = self.model.NewIntVar(0, max_time, f'start_{pid}_{eq.equipment_id}')
                    self._start_vars[(pid, eq.equipment_id)] = start

                    end = self.model.NewIntVar(0, max_time, f'end_{pid}_{eq.equipment_id}')
                    self._end_vars[(pid, eq.equipment_id)] = end

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

        # 4. Selected: start = proc_start, end = start + proc_time
        #    Unselected: start = 0, end = 0
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])
                proc_time = calculate_processing_time(proc.workload, req.efficiency)

                for eq in available_eq:
                    sel = self._select_vars[(pid, eq.equipment_id)]
                    start = self._start_vars[(pid, eq.equipment_id)]
                    end = self._end_vars[(pid, eq.equipment_id)]

                    c1 = self.model.Add(start == self._proc_start[pid])
                    c1.OnlyEnforceIf(sel)
                    c2 = self.model.Add(end == start + proc_time)
                    c2.OnlyEnforceIf(sel)

                    c3 = self.model.Add(start == 0)
                    c3.OnlyEnforceIf(sel.Not())
                    c4 = self.model.Add(end == 0)
                    c4.OnlyEnforceIf(sel.Not())

        # 5. Process end = max of all equipment ends
        for proc in self.processes:
            pid = proc.expanded_id
            equip_ends = []
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])
                for eq in available_eq:
                    equip_ends.append(self._end_vars[(pid, eq.equipment_id)])

            if equip_ends:
                self.model.AddMaxEquality(self._proc_end[pid], equip_ends)

        # 5b. proc_start is independent - selected equipment start == proc_start via step 4

        # 6. Initial transport: equipment starts at crew location
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])

                for eq in available_eq:
                    key = (pid, eq.equipment_id)
                    sel = self._select_vars[key]
                    start = self._start_vars[key]
                    workshop = proc.workshop

                    transport = self.get_transport_time(eq.crew, workshop, eq.speed_mps)

                    c = self.model.Add(start >= transport)
                    c.OnlyEnforceIf(sel)

        # 7. Disjunctive transport constraints for each pair of operations on same equipment
        for eq in self.equipment:
            eq_candidates = []
            for proc in self.processes:
                pid = proc.expanded_id
                key = (pid, eq.equipment_id)
                if key in self._select_vars:
                    eq_candidates.append((pid, proc))

            for i in range(len(eq_candidates)):
                for j in range(i + 1, len(eq_candidates)):
                    pid_i, proc_i = eq_candidates[i]
                    pid_j, proc_j = eq_candidates[j]

                    sel_i = self._select_vars[(pid_i, eq.equipment_id)]
                    sel_j = self._select_vars[(pid_j, eq.equipment_id)]
                    start_i = self._start_vars[(pid_i, eq.equipment_id)]
                    end_i = self._end_vars[(pid_i, eq.equipment_id)]
                    start_j = self._start_vars[(pid_j, eq.equipment_id)]
                    end_j = self._end_vars[(pid_j, eq.equipment_id)]

                    travel_ij = calculate_transport_time(
                        self.distance_func(proc_i.workshop, proc_j.workshop),
                        eq.speed_mps
                    )
                    travel_ji = calculate_transport_time(
                        self.distance_func(proc_j.workshop, proc_i.workshop),
                        eq.speed_mps
                    )

                    # bool_var: 1 = i before j, 0 = j before i
                    i_before_j = self.model.NewBoolVar(f'i_before_j_{pid_i}_{pid_j}_{eq.equipment_id}')

                    c_ij = self.model.Add(start_j >= end_i + travel_ij)
                    c_ij.OnlyEnforceIf(i_before_j)
                    c_ji = self.model.Add(start_i >= end_j + travel_ji)
                    c_ji.OnlyEnforceIf(i_before_j.Not())

                    c_ij.OnlyEnforceIf(sel_i)
                    c_ij.OnlyEnforceIf(sel_j)
                    c_ji.OnlyEnforceIf(sel_i)
                    c_ji.OnlyEnforceIf(sel_j)

        # 8. Precedence constraints within each workshop
        for ws in self.workshops:
            ws_procs = self.process_order.get(ws, [])
            for i in range(len(ws_procs) - 1):
                curr_pid = ws_procs[i]
                next_pid = ws_procs[i + 1]
                self.model.Add(self._proc_end[curr_pid] <= self._proc_start[next_pid])

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
            proc_start = solver.Value(self._proc_start[pid]) if solver else self._proc_start[pid].Value()
            proc_end = solver.Value(self._proc_end[pid]) if solver else self._proc_end[pid].Value()

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

                        # Compute transport time for first operation of this equipment
                        transport_time = 0
                        crew_loc = self.get_crew_location(eq.crew)
                        try:
                            dist = self.distance_func(crew_loc, proc.workshop)
                            transport_time = calculate_transport_time(dist, eq.speed_mps)
                        except:
                            pass

                        operations.append(ScheduledOperation(
                            process=proc,
                            equipment=eq,
                            start_time=int(start),
                            end_time=int(end),
                            transport_time=transport_time
                        ))

        makespan = solver.Value(self._makespan) if solver else self._makespan.Value()

        return ScheduleResult(
            makespan=int(makespan),
            operations=operations
        )


def solve_problem_3(preprocessor: Preprocessor, distance_func) -> ScheduleResult:
    """
    Solve Problem 3: All workshops with Crew 1 + Crew 2 equipment.

    Returns:
        ScheduleResult with makespan and operations
    """
    builder = CpModelBuilderV3(preprocessor, distance_func)
    model = builder.build_model()

    solver = CpSolver()
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)
    print(f"Solve status: {status}")

    if status not in (OPTIMAL, FEASIBLE):
        raise RuntimeError(f"No solution found. Status: {status}")

    result = builder.get_solution(solver)

    # Update makespan
    max_end = max(op.end_time for op in result.operations)
    result.makespan = max_end

    return result


def validate_problem_3(result: ScheduleResult, preprocessor: Preprocessor, distance_func=None) -> Tuple[bool, List[str]]:
    """
    Validate Problem 3 solution with transport time checks.

    Returns:
        (is_valid, error_messages)
    """
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

    # 3. Check equipment no overlap with transport
    equip_ops: Dict[str, List[ScheduledOperation]] = defaultdict(list)
    for op in result.operations:
        equip_ops[op.equipment.equipment_id].append(op)

    for eq_id, ops in equip_ops.items():
        ops_sorted = sorted(ops, key=lambda x: x.start_time)
        for i in range(len(ops_sorted) - 1):
            curr = ops_sorted[i]
            next_op = ops_sorted[i + 1]

            if distance_func:
                travel = calculate_transport_time(
                    distance_func(curr.process.workshop, next_op.process.workshop),
                    curr.equipment.speed_mps
                )
                expected = curr.end_time + travel
                if next_op.start_time < expected - 1:
                    errors.append(
                        f"Equipment {eq_id}: {curr.process.expanded_id} ends at {curr.end_time} "
                        f"+ travel {travel} = {expected}, but {next_op.process.expanded_id} starts at {next_op.start_time}"
                    )
            else:
                if next_op.start_time < curr.end_time - 1:
                    errors.append(
                        f"Equipment {eq_id}: overlap - {curr.process.expanded_id} ends at {curr.end_time} "
                        f"but {next_op.process.expanded_id} starts at {next_op.start_time}"
                    )

    # 4. Check all processes are scheduled
    scheduled_procs = {op.process.expanded_id for op in result.operations}
    all_procs = {p.expanded_id for p in preprocessor.expanded_processes}
    missing = all_procs - scheduled_procs
    if missing:
        errors.append(f"Missing processes: {missing}")

    # 5. Check all equipment is crew 1 or 2
    for op in result.operations:
        if op.equipment.crew not in (1, 2):
            errors.append(f"Equipment {op.equipment.equipment_id} has invalid crew {op.equipment.crew}")

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


def export_q3_schedule(result: ScheduleResult, output_path: str = 'outputs/q3_schedule.csv'):
    """Export Problem 3 schedule to CSV."""
    import csv
    import os

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    rows = []
    for i, op in enumerate(sorted(result.operations, key=lambda x: x.start_time), 1):
        rows.append({
            '序号': i,
            '设备编号': op.equipment.equipment_id,
            '班组': op.equipment.crew,
            '起始时间': op.start_time,
            '结束时间': op.end_time,
            '持续工作时间(s)': op.duration,
            '工序编号': op.process.expanded_id,
            '车间': op.process.workshop,
            '运输时间(s)': op.transport_time
        })

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['序号', '设备编号', '班组', '起始时间', '结束时间', '持续工作时间(s)', '工序编号', '车间', '运输时间(s)'])
        writer.writeheader()
        writer.writerows(rows)

    print(f"导出至: {output_path}")