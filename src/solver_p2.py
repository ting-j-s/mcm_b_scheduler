"""CP-SAT solver for Problem 2: All workshops with Crew 1 only."""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import math

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
    Same workshop processes must be sequential, different workshops can be parallel.
    Equipment transport times between workshops.
    """

    def __init__(
        self,
        preprocessor: Preprocessor,
        crew: int = 1
    ):
        self.preprocessor = preprocessor
        self.crew = crew
        self.workshops = ['A', 'B', 'C', 'D', 'E']

        # All expanded processes
        self.processes = preprocessor.expanded_processes

        # Filter equipment for this crew
        self.equipment = [e for e in preprocessor.equipment if e.crew == crew]

        # Group equipment by type
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

    def build_model(self) -> CpModel:
        """Build the CP-SAT model."""
        self.model = CpModel()
        max_time = 500000  # ~139 hours max

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
                    raise ValueError(f"No equipment of type {eq_type.name} for crew {self.crew}")

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

        # 4. Process end = max of all equipment ends
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

        # 4b. Process start = min of all equipment starts
        for proc in self.processes:
            pid = proc.expanded_id
            equip_starts = []
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])
                for eq in available_eq:
                    equip_starts.append(self._start_vars[(pid, eq.equipment_id)])

            if equip_starts:
                self.model.AddMinEquality(self._proc_start[pid], equip_starts)

        # 5. Precedence constraints within each workshop
        for ws in self.workshops:
            ws_procs = self.process_order.get(ws, [])
            for i in range(len(ws_procs) - 1):
                curr_pid = ws_procs[i]
                next_pid = ws_procs[i + 1]
                self.model.Add(self._proc_end[curr_pid] <= self._proc_start[next_pid])

        # 6. No overlap per equipment
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

        # 7. Objective: minimize makespan
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

                        operations.append(ScheduledOperation(
                            process=proc,
                            equipment=eq,
                            start_time=int(start),
                            end_time=int(end),
                            transport_time=0
                        ))

        makespan = solver.Value(self._makespan) if solver else self._makespan.Value()

        return ScheduleResult(
            makespan=int(makespan),
            operations=operations
        )


def solve_problem_2(preprocessor: Preprocessor, distance_func=None) -> ScheduleResult:
    """
    Solve Problem 2: All workshops with Crew 1 only.

    Returns:
        ScheduleResult with makespan and operations
    """
    builder = CpModelBuilderV2(preprocessor, crew=1)
    model = builder.build_model()

    solver = CpSolver()
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)
    print(f"Solve status: {status}")

    if status not in (OPTIMAL, FEASIBLE):
        raise RuntimeError(f"No solution found. Status: {status}")

    result = builder.get_solution(solver)

    # No transport time recomputation needed - CP-SAT already respects
    # equipment transport constraints through precedence edges
    max_end = max(op.end_time for op in result.operations)
    result.makespan = max_end

    return result


def add_transport_times(result: ScheduleResult, distance_func, crew: int = 1) -> ScheduleResult:
    """Add transport times for equipment moving between workshops."""
    crew_loc = f"Crew {crew}"

    # Group operations by equipment
    from collections import defaultdict
    equip_ops: Dict[str, List[ScheduledOperation]] = defaultdict(list)
    for op in result.operations:
        equip_ops[op.equipment.equipment_id].append(op)

    # For each equipment, compute transport times
    for eq_id, ops in equip_ops.items():
        # Sort by start time
        ops_sorted = sorted(ops, key=lambda x: x.start_time)

        prev_workshop = crew_loc  # Equipment starts at crew location

        for op in ops_sorted:
            curr_workshop = op.process.workshop

            # Calculate transport time
            if prev_workshop == curr_workshop:
                transport = 0
            else:
                try:
                    dist = distance_func(prev_workshop, curr_workshop)
                    transport = calculate_transport_time(dist, op.equipment.speed_mps)
                except:
                    transport = 0

            op.transport_time = transport

            # Shift operation times by cumulative transport
            # Note: we accumulate transport delays in the loop
            prev_workshop = curr_workshop

    return result


def recompute_transport_and_times(result: ScheduleResult, distance_func, crew: int = 1) -> ScheduleResult:
    """Recompute transport times and adjust operation times.

    For each equipment, operations are sequential (not parallel since AddNoOverlap).
    Transport time is added to the START of each operation after the first.
    The first operation also has initial transport from crew location.
    """
    crew_loc = f"Crew {crew}"

    # Group operations by equipment
    from collections import defaultdict
    equip_ops: Dict[str, List[ScheduledOperation]] = defaultdict(list)
    for op in result.operations:
        equip_ops[op.equipment.equipment_id].append(op)

    # For each equipment, recompute times based on transport
    for eq_id, ops in equip_ops.items():
        ops_sorted = sorted(ops, key=lambda x: x.start_time)

        prev_end_time = 0
        prev_workshop = crew_loc

        for op in ops_sorted:
            curr_workshop = op.process.workshop

            # Calculate transport time from previous location to current workshop
            if prev_workshop == curr_workshop:
                transport = 0
            else:
                try:
                    dist = distance_func(prev_workshop, curr_workshop)
                    transport = calculate_transport_time(dist, op.equipment.speed_mps)
                except:
                    transport = 0

            op.transport_time = transport

            # New start time = max(prev_end_time + transport, original_start)
            # This ensures: 1) transport time is respected, 2) doesn't start before prev ends
            new_start = max(prev_end_time + transport, op.start_time)
            duration = op.end_time - op.start_time

            # Update times
            op.start_time = new_start
            op.end_time = new_start + duration

            # Update tracking
            prev_end_time = op.end_time
            prev_workshop = curr_workshop

    return result


def validate_problem_2(result: ScheduleResult, preprocessor: Preprocessor) -> Tuple[bool, List[str]]:
    """
    Validate Problem 2 solution using process-level aggregation.

    Returns:
        (is_valid, error_messages)
    """
    from collections import defaultdict

    # 1. Build process-level start/end times by aggregating equipment operations
    process_times: Dict[str, Dict] = defaultdict(lambda: {"start": float('inf'), "end": 0, "ops": []})

    for op in result.operations:
        pid = op.process.expanded_id
        process_times[pid]["start"] = min(process_times[pid]["start"], op.start_time)
        process_times[pid]["end"] = max(process_times[pid]["end"], op.end_time)
        process_times[pid]["ops"].append(op)

    # 2. Check within-workshop precedence using process-level times
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

    # 3. Check equipment no overlap (including transport)
    equip_ops: Dict[str, List[ScheduledOperation]] = defaultdict(list)
    for op in result.operations:
        equip_ops[op.equipment.equipment_id].append(op)

    for eq_id, ops in equip_ops.items():
        ops_sorted = sorted(ops, key=lambda x: x.start_time)
        for i in range(len(ops_sorted) - 1):
            curr = ops_sorted[i]
            next_op = ops_sorted[i + 1]
            # Next should start after curr ends
            if next_op.start_time < curr.end_time - 1:  # 1 second tolerance
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

    # Sort by start time
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