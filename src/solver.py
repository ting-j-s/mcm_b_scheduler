"""Solver module for MCM B scheduler."""

from typing import Dict, List, Optional, Callable
import time as time_module

from ortools.sat.python.cp_model import CpModel, CpSolver, OPTIMAL, FEASIBLE, INFEASIBLE
from ortools.sat.python.cp_model import CpModel as CpModelClass
from ortools.sat.python.cp_model import CpSolverResponse

from models import ScheduleResult, Equipment
from preprocessing import Preprocessor
from cp_model_builder import CpModelBuilder, CpModelBuilderV2


class SchedulerSolver:
    """Main solver class using OR-Tools CP-SAT."""

    def __init__(
        self,
        preprocessor: Preprocessor,
        crew1_available: bool = True,
        crew2_available: bool = True,
        available_equipment: List[Equipment] = None,
        distance_func: Callable[[str, str], float] = None
    ):
        self.preprocessor = preprocessor
        self.crew1_available = crew1_available
        self.crew2_available = crew2_available
        self.available_equipment = available_equipment or preprocessor.equipment
        self.distance_func = distance_func

        self.model_builder: Optional[CpModelBuilder] = None
        self.cp_model: Optional[CpModelClass] = None
        self.solver: Optional[CpSolver] = None
        self._result: Optional[ScheduleResult] = None

    def build(self, use_v2: bool = True) -> CpModel:
        """Build the CP-SAT model."""
        if use_v2:
            self.model_builder = CpModelBuilderV2(
                preprocessor=self.preprocessor,
                crew1_available=self.crew1_available,
                crew2_available=self.crew2_available,
                available_equipment=self.available_equipment,
                distance_func=self.distance_func
            )
        else:
            self.model_builder = CpModelBuilder(
                preprocessor=self.preprocessor,
                crew1_available=self.crew1_available,
                crew2_available=self.crew2_available,
                available_equipment=self.available_equipment,
                distance_func=self.distance_func
            )

        self.cp_model = self.model_builder.build_model()
        return self.cp_model

    def solve(
        self,
        time_limit_seconds: int = 300,
        log_output: bool = False
    ) -> ScheduleResult:
        """Solve the model and return the result."""
        if self.cp_model is None:
            raise RuntimeError("Model not built. Call build() first.")

        self.solver = CpSolver()
        self.solver.parameters.log_search_progress = log_output
        self.solver.parameters.max_time_in_seconds = time_limit_seconds

        start_time = time_module.time()
        status = self.solver.Solve(self.cp_model)
        solve_time = time_module.time() - start_time

        print(f"Solve status: {status} (time: {solve_time:.2f}s)")

        if status == OPTIMAL or status == FEASIBLE:
            # Get solution from model builder
            if hasattr(self.model_builder, 'get_solution_with_transport'):
                self._result = self.model_builder.get_solution_with_transport(
                    crew_location=f"Crew {'1' if self.crew1_available else '2'}",
                    distance_func=self.distance_func,
                    solver=self.solver
                )
            else:
                self._result = self.model_builder.get_solution(solver=self.solver)
        else:
            raise RuntimeError(f"No solution found. Status: {status}")

        return self._result

    @property
    def result(self) -> Optional[ScheduleResult]:
        return self._result

    def get_model(self) -> Optional[CpModelClass]:
        return self.cp_model


def solve_scheduling_problem(
    preprocessor: Preprocessor,
    crew1_available: bool = True,
    crew2_available: bool = True,
    available_equipment: List[Equipment] = None,
    distance_func: Callable[[str, str], float] = None,
    time_limit_seconds: int = 300
) -> ScheduleResult:
    """
    Convenience function to solve a scheduling problem.

    Args:
        preprocessor: Preprocessor with loaded data
        crew1_available: Whether Crew 1 is available
        crew2_available: Whether Crew 2 is available
        available_equipment: List of available equipment (None = all equipment)
        distance_func: Function to get distance between workshops
        time_limit_seconds: Time limit for solver

    Returns:
        ScheduleResult with the optimal schedule
    """
    solver = SchedulerSolver(
        preprocessor=preprocessor,
        crew1_available=crew1_available,
        crew2_available=crew2_available,
        available_equipment=available_equipment,
        distance_func=distance_func
    )

    solver.build()
    result = solver.solve(time_limit_seconds=time_limit_seconds)

    return result