"""CP-SAT solver for Problem 4: Budget-constrained equipment purchase and scheduling."""

from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import math

from ortools.sat.python.cp_model import CpModel, CpSolver, OPTIMAL, FEASIBLE

from models import (
    Process, Equipment, EquipmentType, OperationRequirement,
    ScheduledOperation, ScheduleResult
)
from preprocessing import Preprocessor
from time_utils import calculate_processing_time, calculate_transport_time, format_seconds


class CpModelBuilderV4:
    """
    CP-SAT model for Problem 4.

    Joint optimization of equipment purchase and schedule.
    - Existing crew 1 and crew 2 equipment
    - Potential new equipment for each type/crew
    - Buy variables gate whether new equipment is purchased
    - Budget constraint: sum(price * buy) <= 500000
    - Minimize makespan
    """

    def __init__(
        self,
        preprocessor: Preprocessor,
        distance_func,
        unit_prices: Dict[EquipmentType, float],
        budget: float = 500000.0
    ):
        self.preprocessor = preprocessor
        self.distance_func = distance_func
        self.unit_prices = unit_prices
        self.budget = budget
        self.workshops = ['A', 'B', 'C', 'D', 'E']

        self.processes = preprocessor.expanded_processes
        self.equipment = preprocessor.equipment

        # Group existing equipment by type
        self.equipment_by_type: Dict[EquipmentType, List[Equipment]] = defaultdict(list)
        for eq in self.equipment:
            self.equipment_by_type[eq.equipment_type].append(eq)

        self.process_order = preprocessor.process_order_within_workshop

        self.model: Optional[CpModel] = None

        # buy_vars: (et, crew, idx) -> BoolVar (whether to buy this potential equipment)
        self._buy_vars: Dict[Tuple[EquipmentType, int, int], any] = {}

        # real equipment selector vars: (pid, eq_id) -> BoolVar
        self._real_select: Dict[Tuple[str, str], any] = {}

        # real equipment start/end: (pid, eq_id) -> (IntVar, IntVar)
        self._real_start: Dict[Tuple[str, str], any] = {}
        self._real_end: Dict[Tuple[str, str], any] = {}

        # potential equipment selector vars: (pid, et, crew, idx) -> BoolVar
        self._pot_select: Dict[Tuple[str, EquipmentType, int, int], any] = {}

        # potential equipment start/end: (pid, et, crew, idx) -> (IntVar, IntVar)
        self._pot_start: Dict[Tuple[str, EquipmentType, int, int], any] = {}
        self._pot_end: Dict[Tuple[str, EquipmentType, int, int], any] = {}

        # Interval vars for real equipment: (pid, eq_id) -> IntervalVar
        self._real_intervals: Dict[Tuple[str, str], any] = {}

        # Interval vars for potential equipment: (pid, et, crew, idx) -> IntervalVar
        self._pot_intervals: Dict[Tuple[str, EquipmentType, int, int], any] = {}

        # Process start/end: pid -> IntVar
        self._proc_start: Dict[str, any] = {}
        self._proc_end: Dict[str, any] = {}

        self._makespan: any = None

        self.crew_locations = {1: "Crew 1", 2: "Crew 2"}

        # Build speed by equipment type from existing equipment
        self.speed_by_type: Dict[EquipmentType, float] = {}
        for eq in self.equipment:
            if eq.equipment_type not in self.speed_by_type:
                self.speed_by_type[eq.equipment_type] = eq.speed_mps

    def get_transport_time(self, from_crew: int, to_workshop: str, speed: float) -> int:
        from_loc = self.crew_locations[from_crew]
        dist = self.distance_func(from_loc, to_workshop)
        return calculate_transport_time(dist, speed)

    def build_model(self) -> CpModel:
        self.model = CpModel()
        max_time = 600000

        # Determine max potential equipment per (type, crew)
        # max_new[et][crew] = floor(budget / unit_price)
        self._max_potential: Dict[EquipmentType, Dict[int, int]] = {}
        for et, price in self.unit_prices.items():
            self._max_potential[et] = {}
            for crew in [1, 2]:
                self._max_potential[et][crew] = math.floor(self.budget / price)

        # 1. Create process start/end variables
        for proc in self.processes:
            pid = proc.expanded_id
            self._proc_start[pid] = self.model.NewIntVar(0, max_time, f'start_{pid}')
            self._proc_end[pid] = self.model.NewIntVar(0, max_time, f'end_{pid}')

        # 2. Create buy variables for potential new equipment
        for et, crew_max in self._max_potential.items():
            for crew, max_count in crew_max.items():
                for idx in range(max_count):
                    buy_var = self.model.NewBoolVar(f'buy_{et.name}_{crew}_{idx}')
                    self._buy_vars[(et, crew, idx)] = buy_var

        # 3. For each process and each required equipment type, create selectors and intervals
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type
                proc_time = calculate_processing_time(proc.workload, req.efficiency)

                # (a) Real equipment selectors and intervals
                for eq in self.equipment_by_type.get(eq_type, []):
                    sel = self.model.NewBoolVar(f'real_sel_{pid}_{eq.equipment_id}')
                    self._real_select[(pid, eq.equipment_id)] = sel

                    start = self.model.NewIntVar(0, max_time, f'real_start_{pid}_{eq.equipment_id}')
                    end = self.model.NewIntVar(0, max_time, f'real_end_{pid}_{eq.equipment_id}')
                    self._real_start[(pid, eq.equipment_id)] = start
                    self._real_end[(pid, eq.equipment_id)] = end

                    interval = self.model.NewOptionalIntervalVar(
                        start, proc_time, end, sel,
                        f'real_interval_{pid}_{eq.equipment_id}'
                    )
                    self._real_intervals[(pid, eq.equipment_id)] = interval

                # (b) Potential new equipment selectors and intervals
                for crew in [1, 2]:
                    for idx in range(self._max_potential.get(eq_type, {}).get(crew, 0)):
                        sel = self.model.NewBoolVar(f'pot_sel_{pid}_{eq_type.name}_{crew}_{idx}')
                        self._pot_select[(pid, eq_type, crew, idx)] = sel

                        start = self.model.NewIntVar(0, max_time, f'pot_start_{pid}_{eq_type.name}_{crew}_{idx}')
                        end = self.model.NewIntVar(0, max_time, f'pot_end_{pid}_{eq_type.name}_{crew}_{idx}')
                        self._pot_start[(pid, eq_type, crew, idx)] = start
                        self._pot_end[(pid, eq_type, crew, idx)] = end

                        interval = self.model.NewOptionalIntervalVar(
                            start, proc_time, end, sel,
                            f'pot_interval_{pid}_{eq_type.name}_{crew}_{idx}'
                        )
                        self._pot_intervals[(pid, eq_type, crew, idx)] = interval

        # 4. Exactly one equipment per required type per process
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type

                selectors = []

                # Real equipment selectors
                for eq in self.equipment_by_type.get(eq_type, []):
                    selectors.append(self._real_select[(pid, eq.equipment_id)])

                # Potential equipment selectors
                for crew in [1, 2]:
                    for idx in range(self._max_potential.get(eq_type, {}).get(crew, 0)):
                        selectors.append(self._pot_select[(pid, eq_type, crew, idx)])

                self.model.Add(sum(selectors) == 1)

        # 5. Assignment implies buy (pot_sel <= buy) for potential equipment
        for (pid, eq_type, crew, idx), sel_var in self._pot_select.items():
            buy_var = self._buy_vars.get((eq_type, crew, idx))
            if buy_var is not None:
                self.model.Add(sel_var <= buy_var)

        # 5b. If buy=1 then must be used at least once (no phantom purchases)
        for (eq_type, crew, idx), buy_var in self._buy_vars.items():
            uses = []
            for proc in self.processes:
                pid = proc.expanded_id
                key = (pid, eq_type, crew, idx)
                if key in self._pot_select:
                    uses.append(self._pot_select[key])
            if uses:
                self.model.Add(buy_var <= sum(uses))

        # 6. Selected real equipment: start = proc_start, end = start + proc_time
        #    Unselected real equipment: start = 0, end = 0
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type
                proc_time = calculate_processing_time(proc.workload, req.efficiency)

                for eq in self.equipment_by_type.get(eq_type, []):
                    sel = self._real_select[(pid, eq.equipment_id)]
                    start = self._real_start[(pid, eq.equipment_id)]
                    end = self._real_end[(pid, eq.equipment_id)]

                    c1 = self.model.Add(start == self._proc_start[pid])
                    c1.OnlyEnforceIf(sel)
                    c2 = self.model.Add(end == start + proc_time)
                    c2.OnlyEnforceIf(sel)

                    c3 = self.model.Add(start == 0)
                    c3.OnlyEnforceIf(sel.Not())
                    c4 = self.model.Add(end == 0)
                    c4.OnlyEnforceIf(sel.Not())

        # 7. Selected potential equipment: start = proc_start, end = start + proc_time
        #    Unselected potential equipment: start = 0, end = 0
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type
                proc_time = calculate_processing_time(proc.workload, req.efficiency)

                for crew in [1, 2]:
                    for idx in range(self._max_potential.get(eq_type, {}).get(crew, 0)):
                        sel = self._pot_select[(pid, eq_type, crew, idx)]
                        start = self._pot_start[(pid, eq_type, crew, idx)]
                        end = self._pot_end[(pid, eq_type, crew, idx)]

                        c1 = self.model.Add(start == self._proc_start[pid])
                        c1.OnlyEnforceIf(sel)
                        c2 = self.model.Add(end == start + proc_time)
                        c2.OnlyEnforceIf(sel)

                        c3 = self.model.Add(start == 0)
                        c3.OnlyEnforceIf(sel.Not())
                        c4 = self.model.Add(end == 0)
                        c4.OnlyEnforceIf(sel.Not())

        # 8. Budget constraint: sum(price * buy) <= 500000
        # Use integer price to avoid FloatAffine comparison issue
        price_terms = []
        for et in self._max_potential:
            price = int(self.unit_prices[et])
            for crew in [1, 2]:
                for idx in range(self._max_potential[et][crew]):
                    price_terms.append(price * self._buy_vars[(et, crew, idx)])

        self.model.Add(sum(price_terms) <= 500000)

        # 9. Process end = max of all equipment ends (for ALL requirement types)
        for proc in self.processes:
            pid = proc.expanded_id
            equip_ends = []

            # Real equipment for ALL requirements
            for req in proc.requirements:
                eq_type = req.equipment_type
                for eq in self.equipment_by_type.get(eq_type, []):
                    if (pid, eq.equipment_id) in self._real_intervals:
                        equip_ends.append(self._real_end[(pid, eq.equipment_id)])

            # Potential equipment for ALL requirements
            for req in proc.requirements:
                eq_type = req.equipment_type
                for crew in [1, 2]:
                    for idx in range(self._max_potential.get(eq_type, {}).get(crew, 0)):
                        key = (pid, eq_type, crew, idx)
                        if key in self._pot_end:
                            equip_ends.append(self._pot_end[key])

            if equip_ends:
                self.model.AddMaxEquality(self._proc_end[pid], equip_ends)

        # 10. proc_start is independent - selected equipment start == proc_start via steps 6 and 7

        # 11. Initial transport for real equipment: starts at crew location
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type

                for eq in self.equipment_by_type.get(eq_type, []):
                    key = (pid, eq.equipment_id)
                    sel = self._real_select[key]
                    start = self._real_start[key]
                    workshop = proc.workshop

                    transport = self.get_transport_time(eq.crew, workshop, eq.speed_mps)
                    c = self.model.Add(start >= transport)
                    c.OnlyEnforceIf(sel)

        # 12. Initial transport for potential equipment: starts at crew location
        for proc in self.processes:
            pid = proc.expanded_id
            for req in proc.requirements:
                eq_type = req.equipment_type
                speed = self.speed_by_type[eq_type]

                for crew in [1, 2]:
                    for idx in range(self._max_potential.get(eq_type, {}).get(crew, 0)):
                        key = (pid, eq_type, crew, idx)
                        sel = self._pot_select[key]
                        start = self._pot_start[key]
                        workshop = proc.workshop

                        transport = self.get_transport_time(crew, workshop, speed)
                        c = self.model.Add(start >= transport)
                        c.OnlyEnforceIf(sel)

        # 13. Disjunctive transport constraints for real equipment
        for eq in self.equipment:
            eq_candidates = []
            for proc in self.processes:
                pid = proc.expanded_id
                key = (pid, eq.equipment_id)
                if key in self._real_select:
                    eq_candidates.append((pid, proc))

            for i in range(len(eq_candidates)):
                for j in range(i + 1, len(eq_candidates)):
                    pid_i, proc_i = eq_candidates[i]
                    pid_j, proc_j = eq_candidates[j]

                    sel_i = self._real_select[(pid_i, eq.equipment_id)]
                    sel_j = self._real_select[(pid_j, eq.equipment_id)]
                    start_i = self._real_start[(pid_i, eq.equipment_id)]
                    end_i = self._real_end[(pid_i, eq.equipment_id)]
                    start_j = self._real_start[(pid_j, eq.equipment_id)]
                    end_j = self._real_end[(pid_j, eq.equipment_id)]

                    travel_ij = calculate_transport_time(
                        self.distance_func(proc_i.workshop, proc_j.workshop),
                        eq.speed_mps
                    )
                    travel_ji = calculate_transport_time(
                        self.distance_func(proc_j.workshop, proc_i.workshop),
                        eq.speed_mps
                    )

                    i_before_j = self.model.NewBoolVar(f'i_before_j_{pid_i}_{pid_j}_{eq.equipment_id}')

                    c_ij = self.model.Add(start_j >= end_i + travel_ij)
                    c_ij.OnlyEnforceIf(i_before_j)
                    c_ji = self.model.Add(start_i >= end_j + travel_ji)
                    c_ji.OnlyEnforceIf(i_before_j.Not())

                    c_ij.OnlyEnforceIf(sel_i)
                    c_ij.OnlyEnforceIf(sel_j)
                    c_ji.OnlyEnforceIf(sel_i)
                    c_ji.OnlyEnforceIf(sel_j)

        # 14. Disjunctive transport constraints for potential equipment
        for et in self._max_potential:
            for crew in [1, 2]:
                for idx in range(self._max_potential[et][crew]):
                    pot_candidates = []
                    for proc in self.processes:
                        pid = proc.expanded_id
                        key = (pid, et, crew, idx)
                        if key in self._pot_select:
                            pot_candidates.append((pid, proc))

                    for i in range(len(pot_candidates)):
                        for j in range(i + 1, len(pot_candidates)):
                            pid_i, proc_i = pot_candidates[i]
                            pid_j, proc_j = pot_candidates[j]

                            sel_i = self._pot_select[(pid_i, et, crew, idx)]
                            sel_j = self._pot_select[(pid_j, et, crew, idx)]
                            start_i = self._pot_start[(pid_i, et, crew, idx)]
                            end_i = self._pot_end[(pid_i, et, crew, idx)]
                            start_j = self._pot_start[(pid_j, et, crew, idx)]
                            end_j = self._pot_end[(pid_j, et, crew, idx)]

                            speed = self.speed_by_type[et]
                            travel_ij = calculate_transport_time(
                                self.distance_func(proc_i.workshop, proc_j.workshop),
                                speed
                            )
                            travel_ji = calculate_transport_time(
                                self.distance_func(proc_j.workshop, proc_i.workshop),
                                speed
                            )

                            i_before_j = self.model.NewBoolVar(f'pot_i_before_j_{pid_i}_{pid_j}_{et.name}_{crew}_{idx}')

                            c_ij = self.model.Add(start_j >= end_i + travel_ij)
                            c_ij.OnlyEnforceIf(i_before_j)
                            c_ji = self.model.Add(start_i >= end_j + travel_ji)
                            c_ji.OnlyEnforceIf(i_before_j.Not())

                            c_ij.OnlyEnforceIf(sel_i)
                            c_ij.OnlyEnforceIf(sel_j)
                            c_ji.OnlyEnforceIf(sel_i)
                            c_ji.OnlyEnforceIf(sel_j)

        # 15. Precedence constraints within each workshop
        for ws in self.workshops:
            ws_procs = self.process_order.get(ws, [])
            for i in range(len(ws_procs) - 1):
                curr_pid = ws_procs[i]
                next_pid = ws_procs[i + 1]
                self.model.Add(self._proc_end[curr_pid] <= self._proc_start[next_pid])

        # 16. Objective: minimize makespan
        all_ends = [self._proc_end[proc.expanded_id] for proc in self.processes]
        self._makespan = self.model.NewIntVar(0, max_time, 'makespan')
        self.model.AddMaxEquality(self._makespan, all_ends)
        self.model.Minimize(self._makespan)

        return self.model

    def get_solution(self, solver: CpSolver = None) -> Tuple[ScheduleResult, Dict[Tuple[EquipmentType, int], int]]:
        """Extract solution: schedule result and purchase counts by (et, crew)."""
        operations = []

        for proc in self.processes:
            pid = proc.expanded_id

            for req in proc.requirements:
                eq_type = req.equipment_type

                # Check real equipment
                for eq in self.equipment_by_type.get(eq_type, []):
                    key = (pid, eq.equipment_id)
                    sel = self._real_select.get(key)
                    if sel is None:
                        continue

                    sel_val = solver.Value(sel) if solver else sel.Value()
                    if sel_val == 1:
                        start = solver.Value(self._real_start[key]) if solver else self._real_start[key].Value()
                        end = solver.Value(self._real_end[key]) if solver else self._real_end[key].Value()

                        # Transport time from crew location
                        crew_loc = self.crew_locations[eq.crew]
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
                            transport_time=transport
                        ))

                # Check potential equipment
                for crew in [1, 2]:
                    for idx in range(self._max_potential.get(eq_type, {}).get(crew, 0)):
                        key = (pid, eq_type, crew, idx)
                        sel = self._pot_select.get(key)
                        if sel is None:
                            continue

                        sel_val = solver.Value(sel) if solver else sel.Value()
                        if sel_val == 1:
                            start = solver.Value(self._pot_start[key]) if solver else self._pot_start[key].Value()
                            end = solver.Value(self._pot_end[key]) if solver else self._pot_end[key].Value()

                            # Create a synthetic equipment object for the new equipment
                            from models import Equipment
                            new_eq = Equipment(
                                equipment_id=f"New_{eq_type.name}_{crew}_{idx}",
                                equipment_type=eq_type,
                                crew=crew,
                                speed_mps=self.speed_by_type[eq_type],
                                unit_price=self.unit_prices[eq_type]
                            )

                            crew_loc = self.crew_locations[crew]
                            try:
                                dist = self.distance_func(crew_loc, proc.workshop)
                                transport = calculate_transport_time(dist, new_eq.speed_mps)
                            except:
                                transport = 0

                            operations.append(ScheduledOperation(
                                process=proc,
                                equipment=new_eq,
                                start_time=int(start),
                                end_time=int(end),
                                transport_time=transport
                            ))

        makespan = solver.Value(self._makespan) if solver else self._makespan.Value()

        # Determine purchases
        purchases: Dict[Tuple[EquipmentType, int], int] = defaultdict(int)
        for (et, crew, idx), buy_var in self._buy_vars.items():
            val = solver.Value(buy_var) if solver else buy_var.Value()
            if val == 1:
                purchases[(et, crew)] += 1

        result = ScheduleResult(
            makespan=int(makespan),
            operations=operations
        )

        return result, dict(purchases)


def solve_problem_4(
    preprocessor: Preprocessor,
    distance_func,
    unit_prices: Dict[EquipmentType, float],
    budget: float = 500000.0
) -> Tuple[ScheduleResult, Dict[Tuple[EquipmentType, int], int], float]:
    """
    Solve Problem 4: Joint equipment purchase and scheduling.

    Returns:
        (ScheduleResult, purchases_dict, total_cost)
    """
    builder = CpModelBuilderV4(preprocessor, distance_func, unit_prices, budget)
    model = builder.build_model()

    solver = CpSolver()
    solver.parameters.log_search_progress = False

    status = solver.Solve(model)
    print(f"Solve status: {status}")

    if status not in (OPTIMAL, FEASIBLE):
        raise RuntimeError(f"No solution found. Status: {status}")

    result, purchases = builder.get_solution(solver)

    # Compute total cost (integer prices)
    total_cost = sum(
        int(unit_prices[et]) * count
        for (et, crew), count in purchases.items()
    )

    return result, purchases, total_cost


def validate_problem_4(
    result: ScheduleResult,
    purchases: Dict[Tuple[EquipmentType, int], int],
    total_cost: float,
    preprocessor: Preprocessor,
    unit_prices: Dict[EquipmentType, float],
    budget: float = 500000.0,
    distance_func=None
) -> Tuple[bool, List[str]]:
    """Validate Problem 4 solution."""
    from collections import defaultdict

    errors = []

    # 1. Budget check
    if total_cost > budget + 1e-6:
        errors.append(f"Budget exceeded: {total_cost:.0f} > {budget:.0f}")

    # 2. Process-level time aggregation
    process_times: Dict[str, Dict] = defaultdict(lambda: {"start": float('inf'), "end": 0})

    for op in result.operations:
        pid = op.process.expanded_id
        process_times[pid]["start"] = min(process_times[pid]["start"], op.start_time)
        process_times[pid]["end"] = max(process_times[pid]["end"], op.end_time)

    # 3. Within-workshop precedence
    process_order = preprocessor.process_order_within_workshop
    for ws, procs in process_order.items():
        for i in range(len(procs) - 1):
            curr, next_proc = procs[i], procs[i + 1]
            curr_end = process_times[curr]["end"]
            next_start = process_times[next_proc]["start"]
            if next_start < curr_end:
                errors.append(f"Workshop {ws}: {curr} ends at {curr_end} but {next_proc} starts at {next_start}")

    # 4. Equipment no overlap with transport
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

    # 5. All processes scheduled
    scheduled = {op.process.expanded_id for op in result.operations}
    all_procs = {p.expanded_id for p in preprocessor.expanded_processes}
    if missing := all_procs - scheduled:
        errors.append(f"Missing processes: {missing}")

    # 6. Process has all required equipment types
    for proc in preprocessor.expanded_processes:
        ops_for_proc = [op for op in result.operations if op.process.expanded_id == proc.expanded_id]
        if not ops_for_proc:
            errors.append(f"Process {proc.expanded_id} has no operations")
        else:
            assigned = {op.equipment.equipment_type for op in ops_for_proc}
            required = {req.equipment_type for req in proc.requirements}
            if assigned != required:
                errors.append(f"Process {proc.expanded_id} missing types: {required - assigned}")

    # 7. Initial transport: first operation of each equipment must respect crew -> workshop transport
    from collections import defaultdict
    by_eq = defaultdict(list)
    for op in result.operations:
        by_eq[op.equipment.equipment_id].append(op)

    for eq_id, ops in by_eq.items():
        first = sorted(ops, key=lambda x: x.start_time)[0]
        crew_loc = f"Crew {first.equipment.crew}"
        try:
            required = calculate_transport_time(
                distance_func(crew_loc, first.process.workshop),
                first.equipment.speed_mps
            )
            if first.start_time < required:
                errors.append(
                    f"{eq_id}: first operation {first.process.expanded_id} starts at {first.start_time}, "
                    f"but initial transport from {crew_loc} to {first.process.workshop} requires {required}"
                )
        except:
            pass

    is_valid = len(errors) == 0
    return is_valid, errors


def export_q4_schedule(result: ScheduleResult, output_path: str = 'outputs/q4_schedule.csv'):
    """Export Problem 4 schedule to CSV."""
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
            '班组': op.equipment.crew
        })

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['序号', '设备编号', '起始时间', '结束时间', '持续工作时间(s)', '工序编号', '班组'])
        writer.writeheader()
        writer.writerows(rows)

    print(f"导出至: {output_path}")


def export_q4_purchase(
    purchases: Dict[Tuple[EquipmentType, int], int],
    unit_prices: Dict[EquipmentType, float],
    output_path: str = 'outputs/q4_purchase.csv'
):
    """Export Problem 4 purchase plan to CSV."""
    import csv
    import os

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Aggregate by equipment type name
    type_names = {
        EquipmentType.AUTOMATED_CONVEYING_ARM: '自动化输送臂',
        EquipmentType.INDUSTRIAL_CLEANING_MACHINE: '工业清洗机',
        EquipmentType.PRECISION_FILLING_MACHINE: '精密灌装机',
        EquipmentType.AUTOMATIC_SENSING_MULTI_FUNCTION_MACHINE: '自动传感多功能机',
        EquipmentType.HIGH_SPEED_POLISHING_MACHINE: '高速抛光机',
    }

    rows = []
    for et in EquipmentType:
        crew1_count = purchases.get((et, 1), 0)
        crew2_count = purchases.get((et, 2), 0)
        rows.append({
            '设备名称': type_names.get(et, et.name),
            '班组1购买台数': crew1_count,
            '班组2购买台数': crew2_count
        })

    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['设备名称', '班组1购买台数', '班组2购买台数'])
        writer.writeheader()
        writer.writerows(rows)

    print(f"导出至: {output_path}")