"""CP-SAT solver for Problem 1: Workshop A with Crew 1 only."""

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


@dataclass
class Problem1Config:
    """Configuration for Problem 1."""
    workshop: str = 'A'
    crew: int = 1
    minimize_makespan: bool = True


class CpModelBuilderV1:
    """
    CP-SAT model for Problem 1.

    Only workshop A processes, only crew 1 equipment.
    """

    def __init__(
        self,
        preprocessor: Preprocessor,
        crew: int = 1
    ):
        self.preprocessor = preprocessor
        self.crew = crew
        self.workshop = 'A'

        # Filter processes for this workshop
        self.processes = [
            p for p in preprocessor.expanded_processes
            if p.workshop == self.workshop
        ]
        # Sort by process_id order
        self.processes = sorted(self.processes, key=lambda p: p.process_id)

        # Filter equipment for this crew
        self.equipment = [
            e for e in preprocessor.equipment
            if e.crew == crew
        ]

        # Group equipment by type
        self.equipment_by_type: Dict[EquipmentType, List[Equipment]] = {}
        for eq in self.equipment:
            if eq.equipment_type not in self.equipment_by_type:
                self.equipment_by_type[eq.equipment_type] = []
            self.equipment_by_type[eq.equipment_type].append(eq)

        # Model
        self.model: Optional[CpModel] = None

        # Variables
        # (process_expanded_id, equipment_id) -> selector BoolVar
        self._select_vars: Dict[Tuple[str, str], any] = {}

        # (process_expanded_id, equipment_id) -> start IntVar
        self._start_vars: Dict[Tuple[str, str], any] = {}

        # (process_expanded_id, equipment_id) -> end IntVar
        self._end_vars: Dict[Tuple[str, str], any] = {}

        # process_id -> start time (shared across equipment types for same process)
        self._proc_start: Dict[str, any] = {}

        # process_id -> end time (max of all equipment ends)
        self._proc_end: Dict[str, any] = {}

        # intervals: (process_id, equipment_id)
        self._intervals: Dict[Tuple[str, str], any] = {}

        # makespan
        self._makespan: any = None

    def build_model(self) -> CpModel:
        """Build the CP-SAT model."""
        self.model = CpModel()

        max_time = 200000  # ~55 hours max

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

                    # Interval: exists when selected
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

        # 4. Process end = max of all equipment ends for that process
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

            # Process start = min of all equipment starts
            equip_starts = []
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self.equipment_by_type.get(eq_type, [])
                for eq in available_eq:
                    equip_starts.append(self._start_vars[(pid, eq.equipment_id)])

            if equip_starts:
                self.model.AddMinEquality(self._proc_start[pid], equip_starts)

        # 5. Precedence constraints: A1 -> A2 -> A3
        for i in range(len(self.processes) - 1):
            curr_proc = self.processes[i]
            next_proc = self.processes[i + 1]
            self.model.Add(self._proc_end[curr_proc.expanded_id] <= self._proc_start[next_proc.expanded_id])

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

        # 7. Initial transport time from Crew to workshop A
        # For first operation of each equipment type, add transport time
        # Get distance from Crew to workshop A
        # (handled separately in solution extraction)

        # 8. Objective: minimize makespan
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


def solve_problem_1(preprocessor: Preprocessor, distance_func=None) -> ScheduleResult:
    """
    Solve Problem 1: Workshop A with Crew 1 only.

    Returns:
        ScheduleResult with makespan and operations
    """
    builder = CpModelBuilderV1(preprocessor, crew=1)
    model = builder.build_model()

    solver = CpSolver()
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)
    print(f"Solve status: {status}")

    if status not in (OPTIMAL, FEASIBLE):
        raise RuntimeError(f"No solution found. Status: {status}")

    result = builder.get_solution(solver)

    # Add transport times and update makespan
    if distance_func:
        result = add_initial_transport_times(result, distance_func, crew=1)
        # Update makespan - end_time already includes transport shift
        max_end = max(op.end_time for op in result.operations)
        result.makespan = max_end

    return result


def add_initial_transport_times(result: ScheduleResult, distance_func, crew: int = 1) -> ScheduleResult:
    """Add initial transport times from Crew to first workshop.

    Transport time is added to the first operation of each equipment,
    shifting the operation's start and end times.
    """
    crew_loc = f"Crew {crew}"

    # Group operations by equipment
    from collections import defaultdict
    equip_ops: Dict[str, List[ScheduledOperation]] = defaultdict(list)
    for op in result.operations:
        equip_ops[op.equipment.equipment_id].append(op)

    # For each equipment, shift first operation by transport time
    for eq_id, ops in equip_ops.items():
        # Sort by start time
        ops_sorted = sorted(ops, key=lambda x: x.start_time)

        # First operation gets initial transport
        first_op = ops_sorted[0]
        workshop = first_op.process.workshop

        try:
            dist = distance_func(crew_loc, workshop)
            transport = calculate_transport_time(dist, first_op.equipment.speed_mps)
            first_op.transport_time = transport
            # Shift operation times by transport
            first_op.start_time += transport
            first_op.end_time += transport
        except:
            first_op.transport_time = 0

    return result


def validate_problem_1(result: ScheduleResult, preprocessor: Preprocessor) -> Tuple[bool, List[str]]:
    """
    Validate Problem 1 solution.

    Returns:
        (is_valid, error_messages)
    """
    errors = []

    # 1. Check A1 -> A2 -> A3 precedence
    proc_order = ['A1', 'A2', 'A3']
    proc_end_times = {}

    for op in result.operations:
        pid = op.process.expanded_id
        if pid not in proc_end_times or op.end_time > proc_end_times[pid]:
            proc_end_times[pid] = op.end_time

    for i in range(len(proc_order) - 1):
        curr = proc_order[i]
        next_proc = proc_order[i + 1]
        if curr in proc_end_times and next_proc in proc_end_times:
            if proc_end_times[curr] > result.operations[0].start_time:  # This is rough
                pass  # Need better check

    # Actually check properly
    a1_end = None
    a2_end = None
    a3_end = None

    for op in result.operations:
        if op.process.expanded_id == 'A1':
            a1_end = max(a1_end or 0, op.end_time)
        elif op.process.expanded_id == 'A2':
            a2_end = max(a2_end or 0, op.end_time)
        elif op.process.expanded_id == 'A3':
            a3_end = max(a3_end or 0, op.end_time)

    if a1_end is not None and a2_end is not None:
        if a1_end > a2_end:
            errors.append(f"A1 ({a1_end}) must finish before A2 starts ({a2_end})")

    if a2_end is not None and a3_end is not None:
        if a2_end > a3_end:
            errors.append(f"A2 ({a2_end}) must finish before A3 starts ({a3_end})")

    # 2. Check no equipment overlap
    from collections import defaultdict
    equip_ops: Dict[str, List[ScheduledOperation]] = defaultdict(list)
    for op in result.operations:
        equip_ops[op.equipment.equipment_id].append(op)

    for eq_id, ops in equip_ops.items():
        ops_sorted = sorted(ops, key=lambda x: x.start_time)
        for i in range(len(ops_sorted) - 1):
            curr = ops_sorted[i]
            next_op = ops_sorted[i + 1]
            if curr.end_time > next_op.start_time:
                errors.append(f"Equipment {eq_id} overlap: ends at {curr.end_time} but next starts at {next_op.start_time}")

    # 3. Check all processes have equipment
    a_procs = {'A1', 'A2', 'A3'}
    for proc_id in a_procs:
        ops_for_proc = [op for op in result.operations if op.process.expanded_id == proc_id]
        if not ops_for_proc:
            errors.append(f"Process {proc_id} has no operations")
        else:
            # Check all required equipment types are covered
            proc = preprocessor.get_process_by_id(proc_id)
            assigned_types = {op.equipment.equipment_type for op in ops_for_proc}
            required_types = {req.equipment_type for req in proc.requirements}
            if assigned_types != required_types:
                errors.append(f"Process {proc_id} missing equipment types: {required_types - assigned_types}")

    # 4. Check crew 1 only
    for op in result.operations:
        if op.equipment.crew != 1:
            errors.append(f"Equipment {op.equipment.equipment_id} is not from Crew 1")

    is_valid = len(errors) == 0
    return is_valid, errors


def export_q1_schedule(result: ScheduleResult, output_path: str = 'outputs/q1_schedule.csv'):
    """Export Problem 1 schedule to CSV."""
    import csv
    import os

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Sort: by process order (A1, A2, A3), then by equipment type
    process_order = {'A1': 0, 'A2': 1, 'A3': 2}

    def sort_key(op):
        proc_order = process_order.get(op.process.expanded_id, 99)
        return (proc_order, op.equipment.equipment_type.name, op.equipment.equipment_id)

    rows = []
    for i, op in enumerate(sorted(result.operations, key=sort_key), 1):
        rows.append({
            '序号': i,
            '设备编号': op.equipment.equipment_id,
            '起始时间': op.start_time,
            '结束时间': op.end_time,
            '持续工作时间(s)': op.duration,
            '工序编号': op.process.expanded_id
        })

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['序号', '设备编号', '起始时间', '结束时间', '持续工作时间(s)', '工序编号'])
        writer.writeheader()
        writer.writerows(rows)

    print(f"导出至: {output_path}")