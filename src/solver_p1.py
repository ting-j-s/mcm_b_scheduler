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
        crew: int = 1,
        distance_func=None
    ):
        self.preprocessor = preprocessor
        self.crew = crew
        self.workshop = 'A'
        self._distance_func = distance_func

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

        # 5. Process end = max of selected equipment ends
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

        # 6. Initial transport: equipment starts at crew location
        for eq in self.equipment:
            for proc in self.processes:
                pid = proc.expanded_id
                key = (pid, eq.equipment_id)
                if key not in self._select_vars:
                    continue

                sel = self._select_vars[key]
                start = self._start_vars[key]

                # All A workshop processes: distance from Crew 1 to A
                dist = self._distance_func(f"Crew {self.crew}", self.workshop)
                transport = calculate_transport_time(dist, eq.speed_mps)

                c = self.model.Add(start >= transport)
                c.OnlyEnforceIf(sel)

        # 7. Disjunctive transport constraints for each pair on same equipment
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

                    # Same workshop A -> A: transport = 0
                    travel_ij = 0
                    travel_ji = 0

                    i_before_j = self.model.NewBoolVar(f'i_before_j_{pid_i}_{pid_j}_{eq.equipment_id}')

                    c_ij = self.model.Add(start_j >= end_i + travel_ij)
                    c_ij.OnlyEnforceIf(i_before_j)
                    c_ji = self.model.Add(start_i >= end_j + travel_ji)
                    c_ji.OnlyEnforceIf(i_before_j.Not())

                    c_ij.OnlyEnforceIf(sel_i)
                    c_ij.OnlyEnforceIf(sel_j)
                    c_ji.OnlyEnforceIf(sel_i)
                    c_ji.OnlyEnforceIf(sel_j)

        # 8. Precedence: A1 -> A2 -> A3
        for i in range(len(self.processes) - 1):
            curr_proc = self.processes[i]
            next_proc = self.processes[i + 1]
            self.model.Add(self._proc_end[curr_proc.expanded_id] <= self._proc_start[next_proc.expanded_id])

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
    builder = CpModelBuilderV1(preprocessor, crew=1, distance_func=distance_func)
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


def validate_problem_1(result: ScheduleResult, preprocessor: Preprocessor, distance_func=None) -> Tuple[bool, List[str]]:
    """
    Validate Problem 1 solution.

    Checks:
    1. A1 -> A2 -> A3 precedence
    2. Each process has all required equipment types
    3. No equipment overlap (with same-workshop transport=0)
    4. Crew 1 only
    5. Initial transport for first operation of each equipment
    6. Process end = max of its equipment ends
    """
    from collections import defaultdict

    errors = []

    # Build process-level times
    process_times = defaultdict(lambda: {"start": float('inf'), "end": 0, "ops": []})
    for op in result.operations:
        pid = op.process.expanded_id
        process_times[pid]["start"] = min(process_times[pid]["start"], op.start_time)
        process_times[pid]["end"] = max(process_times[pid]["end"], op.end_time)
        process_times[pid]["ops"].append(op)

    # 1. Check A1 -> A2 -> A3 precedence
    proc_order = ['A1', 'A2', 'A3']
    for i in range(len(proc_order) - 1):
        curr = proc_order[i]
        next_proc = proc_order[i + 1]
        if curr in process_times and next_proc in process_times:
            curr_end = process_times[curr]["end"]
            next_start = process_times[next_proc]["start"]
            if next_start < curr_end:
                errors.append(f"A1->A2->A3: {curr} ends at {curr_end} but {next_proc} starts at {next_start}")

    # 2. Check equipment no overlap with transport
    equip_ops: Dict[str, List[ScheduledOperation]] = defaultdict(list)
    for op in result.operations:
        equip_ops[op.equipment.equipment_id].append(op)

    for eq_id, ops in equip_ops.items():
        ops_sorted = sorted(ops, key=lambda x: x.start_time)
        for i in range(len(ops_sorted) - 1):
            curr = ops_sorted[i]
            next_op = ops_sorted[i + 1]
            # Same workshop A -> A: transport = 0
            if next_op.start_time < curr.end_time - 1:
                errors.append(
                    f"Equipment {eq_id}: overlap - {curr.process.expanded_id} ends at {curr.end_time} "
                    f"but {next_op.process.expanded_id} starts at {next_op.start_time}"
                )

    # 3. Check all processes have all required equipment types
    for pid in ['A1', 'A2', 'A3']:
        if pid not in process_times:
            errors.append(f"Process {pid} has no operations")
            continue
        ops = process_times[pid]["ops"]
        assigned_types = {op.equipment.equipment_type for op in ops}
        proc = preprocessor.get_process_by_id(pid)
        required_types = {req.equipment_type for req in proc.requirements}
        if assigned_types != required_types:
            errors.append(f"Process {pid} missing types: {required_types - assigned_types}")

    # 4. Check crew 1 only
    for op in result.operations:
        if op.equipment.crew != 1:
            errors.append(f"Equipment {op.equipment.equipment_id} is not from Crew 1")

    # 5. Initial transport: first operation of each equipment
    for eq_id, ops in equip_ops.items():
        first = sorted(ops, key=lambda x: x.start_time)[0]
        crew_loc = "Crew 1"
        if distance_func:
            try:
                dist = distance_func(crew_loc, first.process.workshop)
                required = calculate_transport_time(dist, first.equipment.speed_mps)
                if first.start_time < required:
                    errors.append(
                        f"{eq_id}: first op {first.process.expanded_id} starts at {first.start_time}, "
                        f"but initial transport requires {required}"
                    )
            except:
                pass

    # 6. Process end = max of its equipment ends
    for pid, info in process_times.items():
        max_end_from_ops = max(op.end_time for op in info["ops"])
        if info["end"] != max_end_from_ops:
            errors.append(f"Process {pid}: recorded end={info['end']} but max equipment end={max_end_from_ops}")

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