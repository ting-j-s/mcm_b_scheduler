"""CP-SAT model builder for MCM B scheduler - V4 with proper multi-equipment support."""

from typing import Dict, List, Set, Tuple, Optional
import math
from collections import defaultdict

from ortools.sat.python.cp_model import CpModel, IntVar, IntervalVar

from models import (
    Process, Equipment, EquipmentType, ProcessEdge, ScheduledOperation,
    ScheduleResult, ProcessRequirement
)
from preprocessing import Preprocessor
from time_utils import calculate_processing_time, calculate_transport_time


class CpModelBuilderV4:
    """
    CP-SAT model builder with proper handling of multi-equipment processes.

    For a process requiring multiple equipment types:
    - All equipment work simultaneously on the same process
    - Each equipment type has its own processing time
    - Each equipment has its own interval with its own end time
    - Process completion = max(all equipment end times)
    """

    def __init__(
        self,
        preprocessor: Preprocessor,
        crew1_available: bool = True,
        crew2_available: bool = True,
        available_equipment: List[Equipment] = None,
        distance_func=None
    ):
        self.preprocessor = preprocessor
        self.crew1_available = crew1_available
        self.crew2_available = crew2_available
        self.available_equipment = available_equipment or preprocessor.equipment
        self.distance_func = distance_func

        self.model = None

        # For each (process_id, equipment_id): selector var
        self._select_vars: Dict[Tuple[str, str], IntVar] = {}

        # For each process: start time
        self._proc_start: Dict[str, IntVar] = {}

        # For each (process_id, equipment_id): end time for that equipment's work
        self._equip_end: Dict[Tuple[str, str], IntVar] = {}

        # For each (process_id, equipment_id): interval var
        self._intervals: Dict[Tuple[str, str], IntervalVar] = {}

        # For each process: process end time (max of all equipment ends)
        self._proc_end: Dict[str, IntVar] = {}

        self._makespan_var: IntVar = None

        # For solution extraction
        self._processes = preprocessor.expanded_processes

    def build_model(self) -> CpModel:
        """Build the complete CP-SAT model."""
        self.model = CpModel()

        processes = self._processes
        precedence_edges = self.preprocessor.precedence_edges

        # Step 1: Create process start variables and process end variables
        self._create_process_variables(processes)

        # Step 2: Create equipment selection and interval variables
        self._create_equipment_variables(processes)

        # Step 3: Add equipment type selection constraints (exactly 1 per type)
        self._add_equipment_selection_constraints(processes)

        # Step 4: Process end = max of all equipment ends
        self._add_process_end_constraints(processes)

        # Step 5: Add precedence constraints
        self._add_precedence_constraints(precedence_edges)

        # Step 6: Add no-overlap constraints per equipment
        self._add_no_overlap_constraints(processes)

        # Step 7: Set objective
        self._set_makespan_objective(processes)

        return self.model

    def _create_process_variables(self, processes: List[Process]):
        """Create start/end variables for each process."""
        max_time = 500000

        for proc in processes:
            proc_id = proc.expanded_id()
            self._proc_start[proc_id] = self.model.NewIntVar(
                0, max_time, f'proc_start_{proc_id}'
            )
            # Process end is a decision variable - it will be set to max of equipment ends
            self._proc_end[proc_id] = self.model.NewIntVar(
                0, max_time, f'proc_end_{proc_id}'
            )

    def _create_equipment_variables(self, processes: List[Process]):
        """Create selector, end time, and interval variables for each process-equipment pair."""
        for proc in processes:
            proc_id = proc.expanded_id()
            proc_start = self._proc_start[proc_id]

            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self._get_available_equipment_for_type(eq_type)

                if not available_eq:
                    raise ValueError(f"No equipment of type {eq_type} available")

                proc_time = calculate_processing_time(proc.workload, req.efficiency)

                # For each available equipment of this type, create variables
                for eq in available_eq:
                    selector = self.model.NewBoolVar(
                        f'sel_{proc_id}_{eq.equipment_id}'
                    )
                    self._select_vars[(proc_id, eq.equipment_id)] = selector

                    # Equipment-specific end time
                    # It's constrained to be start + processing_time when selected
                    equip_end = self.model.NewIntVar(
                        0, 500000, f'equip_end_{proc_id}_{eq.equipment_id}'
                    )
                    self._equip_end[(proc_id, eq.equipment_id)] = equip_end

                    # Optional interval: exists only when this equipment is selected
                    # Duration is the processing time for this equipment
                    interval = self.model.NewOptionalIntervalVar(
                        proc_start,          # start
                        proc_time,           # duration (fixed)
                        equip_end,           # end (equipment-specific)
                        selector,            # presence condition
                        f'interval_{proc_id}_{eq.equipment_id}'
                    )
                    self._intervals[(proc_id, eq.equipment_id)] = interval

    def _get_available_equipment_for_type(self, eq_type: EquipmentType) -> List[Equipment]:
        """Get available equipment of a given type."""
        result = []
        for eq in self.available_equipment:
            if eq.equipment_type == eq_type:
                if eq.crew == 1 and self.crew1_available:
                    result.append(eq)
                elif eq.crew == 2 and self.crew2_available:
                    result.append(eq)
        return result

    def _add_equipment_selection_constraints(self, processes: List[Process]):
        """For each process, ensure exactly one equipment per required type is selected."""
        for proc in processes:
            proc_id = proc.expanded_id()

            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self._get_available_equipment_for_type(eq_type)

                # Sum of selectors for this equipment type = 1
                selectors = [
                    self._select_vars[(proc_id, eq.equipment_id)]
                    for eq in available_eq
                ]
                self.model.Add(sum(selectors) == 1)

    def _add_process_end_constraints(self, processes: List[Process]):
        """For each process, end time = max of all selected equipment end times."""
        for proc in processes:
            proc_id = proc.expanded_id()
            proc_end = self._proc_end[proc_id]

            # Collect all equipment end vars for this process
            equip_ends = []
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self._get_available_equipment_for_type(eq_type)

                for eq in available_eq:
                    equip_end = self._equip_end.get((proc_id, eq.equipment_id))
                    if equip_end is not None:
                        equip_ends.append(equip_end)

            if equip_ends:
                self.model.AddMaxEquality(proc_end, equip_ends)

    def _add_precedence_constraints(self, edges: List[ProcessEdge]):
        """Add precedence constraints between processes."""
        for edge in edges:
            from_proc = edge.from_process
            to_proc = edge.to_process

            if from_proc in self._proc_end and to_proc in self._proc_start:
                self.model.Add(self._proc_end[from_proc] <= self._proc_start[to_proc])

    def _add_no_overlap_constraints(self, processes: List[Process]):
        """Add no-overlap constraints for each piece of equipment."""
        # Group intervals by equipment
        equipment_intervals: Dict[str, List[IntervalVar]] = defaultdict(list)

        for proc in processes:
            proc_id = proc.expanded_id()
            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self._get_available_equipment_for_type(eq_type)

                for eq in available_eq:
                    interval = self._intervals.get((proc_id, eq.equipment_id))
                    if interval:
                        equipment_intervals[eq.equipment_id].append(interval)

        # Add no-overlap for each equipment with 2+ tasks
        for eq_id, intervals in equipment_intervals.items():
            if len(intervals) > 1:
                self.model.AddNoOverlap(intervals)

    def _set_makespan_objective(self, processes: List[Process]):
        """Set makespan (max completion time) as objective."""
        all_ends = [self._proc_end[proc.expanded_id()] for proc in processes]
        self._makespan_var = self.model.NewIntVar(0, 500000, 'makespan')
        self.model.AddMaxEquality(self._makespan_var, all_ends)
        self.model.Minimize(self._makespan_var)

    def get_solution(self, solver=None) -> ScheduleResult:
        """Extract solution from the solved model."""
        operations = []

        def get_val(var):
            if var is None:
                return 0
            if solver is not None:
                return solver.Value(var)
            return var.Value()

        for proc in self._processes:
            proc_id = proc.expanded_id()
            proc_start_val = get_val(self._proc_start[proc_id])
            proc_end_val = get_val(self._proc_end[proc_id])

            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self._get_available_equipment_for_type(eq_type)

                for eq in available_eq:
                    selector = self._select_vars.get((proc_id, eq.equipment_id))
                    if selector is not None:
                        selector_val = get_val(selector)
                        if selector_val == 1:
                            equip_end = self._equip_end.get((proc_id, eq.equipment_id))
                            if equip_end is not None:
                                end_val = get_val(equip_end)
                            else:
                                end_val = proc_end_val

                            operations.append(ScheduledOperation(
                                process=proc,
                                equipment=eq,
                                start_time=proc_start_val,
                                end_time=end_val,
                                transport_time=0
                            ))

        if self._makespan_var is not None:
            makespan = get_val(self._makespan_var)
        else:
            makespan = 0

        return ScheduleResult(
            makespan=makespan,
            operations=operations
        )

    def get_solution_with_transport(
        self,
        crew_location: str = "Crew 1",
        distance_func=None,
        solver=None
    ) -> ScheduleResult:
        """Extract solution and compute transport times."""
        operations = []

        # Helper to get value - handles None and literals properly
        def get_val(var):
            if var is None:
                return 0
            if solver is not None:
                return solver.Value(var)
            return var.Value()

        # Group operations by equipment to compute transport
        equipment_tasks: Dict[str, List[Tuple[Process, int, int]]] = defaultdict(list)

        for proc in self._processes:
            proc_id = proc.expanded_id()
            proc_start_val = get_val(self._proc_start[proc_id])
            proc_end_val = get_val(self._proc_end[proc_id])

            for req in proc.requirements:
                eq_type = req.equipment_type
                available_eq = self._get_available_equipment_for_type(eq_type)

                for eq in available_eq:
                    selector = self._select_vars.get((proc_id, eq.equipment_id))
                    if selector is not None:
                        selector_val = get_val(selector)
                        if selector_val == 1:
                            equip_end = self._equip_end.get((proc_id, eq.equipment_id))
                            if equip_end is not None:
                                end_val = get_val(equip_end)
                            else:
                                end_val = proc_end_val

                            equipment_tasks[eq.equipment_id].append(
                                (proc, proc_start_val, end_val)
                            )

        # Compute transport times for each equipment
        for eq_id, tasks in equipment_tasks.items():
            # Get equipment
            eq = None
            for e in self.available_equipment:
                if e.equipment_id == eq_id:
                    eq = e
                    break

            if eq is None:
                continue

            # Sort tasks by start time
            tasks_sorted = sorted(tasks, key=lambda x: x[1])

            # Compute transport for each task
            for i, (proc, start_val, end_val) in enumerate(tasks_sorted):
                if i == 0:
                    # First task: transport from crew location to first workshop
                    crew_loc = f"Crew {eq.crew}"
                    if distance_func:
                        try:
                            dist = distance_func(crew_loc, proc.workshop)
                            transport = calculate_transport_time(dist, eq.speed_mps)
                        except:
                            transport = 0
                    else:
                        transport = 0
                else:
                    prev_proc = tasks_sorted[i-1][0]
                    if prev_proc.workshop == proc.workshop:
                        transport = 0
                    elif distance_func:
                        try:
                            dist = distance_func(prev_proc.workshop, proc.workshop)
                            transport = calculate_transport_time(dist, eq.speed_mps)
                        except:
                            transport = 0
                    else:
                        transport = 0

                operations.append(ScheduledOperation(
                    process=proc,
                    equipment=eq,
                    start_time=start_val,
                    end_time=end_val,
                    transport_time=transport
                ))

        if self._makespan_var is not None:
            makespan = get_val(self._makespan_var)
        else:
            makespan = 0

        return ScheduleResult(
            makespan=makespan,
            operations=operations
        )


# Aliases for compatibility
CpModelBuilderV3 = CpModelBuilderV4
CpModelBuilderV2 = CpModelBuilderV4
CpModelBuilder = CpModelBuilderV4