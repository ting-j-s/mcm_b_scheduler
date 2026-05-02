"""Purchase optimizer for Problem 4 - equipment purchase within budget."""

from typing import List, Dict, Tuple, Optional
import itertools
from ortools.sat.python.cp_model import CpModel, CpSolver, OPTIMAL

from models import ScheduleResult, Equipment, EquipmentType
from preprocessing import Preprocessor
from solver import SchedulerSolver
from time_utils import calculate_transport_time


class PurchaseOptimizer:
    """
    Optimizer for Problem 4 that jointly optimizes equipment purchase and scheduling.

    Budget constraint: 500000 yuan total.
    Goal: Minimize makespan while respecting budget.
    """

    def __init__(
        self,
        preprocessor: Preprocessor,
        base_equipment: List[Equipment],
        distance_func,
        max_budget: float = 500000
    ):
        self.preprocessor = preprocessor
        self.base_equipment = base_equipment
        self.distance_func = distance_func
        self.max_budget = max_budget

        # Get unit prices from equipment
        self.unit_prices: Dict[EquipmentType, float] = {}
        for eq in base_equipment:
            self.unit_prices[eq.equipment_type] = eq.unit_price

        # Get equipment types and which crews have them
        self.equipment_types = list(set(eq.equipment_type for eq in base_equipment))

    def generate_purchase_options(self) -> List[Tuple[int, List[Equipment]]]:
        """
        Generate all possible equipment purchase combinations within budget.

        Returns:
            List of (total_cost, equipment_list) tuples
        """
        # Get the base equipment by crew
        crew1_equipment = [eq for eq in self.base_equipment if eq.crew == 1]
        crew2_equipment = [eq for eq in self.base_equipment if eq.crew == 2]

        # Count existing equipment per type per crew
        base_counts: Dict[Tuple[EquipmentType, int], int] = {}
        for eq in self.base_equipment:
            key = (eq.equipment_type, eq.crew)
            base_counts[key] = base_counts.get(key, 0) + 1

        # For each equipment type and crew, generate purchase options
        # Purchase 0, 1, 2, ... units until budget exhausted

        # First, let's generate combinations for a reasonable number of purchases
        max_purchase_per_type = 5  # Reasonable upper bound

        all_options = []

        # Generate purchase counts for each (type, crew) combination
        purchase_vars = []
        for eq_type in self.equipment_types:
            for crew in [1, 2]:
                max_existing = base_counts.get((eq_type, crew), 0)
                # Can purchase up to max_purchase_per_type additional
                purchase_vars.append((eq_type, crew, max_existing, max_purchase_per_type))

        # Use recursive generation
        def generate_recursive(
            idx: int,
            current_cost: float,
            current_additions: Dict[Tuple[EquipmentType, int], int],
            all_options: List
        ):
            if idx == len(purchase_vars):
                if current_cost <= self.max_budget:
                    all_options.append((current_cost, dict(current_additions)))
                return

            eq_type, crew, base_count, max_purchase = purchase_vars[idx]
            unit_price = self.unit_prices[eq_type]

            for num_to_buy in range(max_purchase + 1):
                cost_increment = num_to_buy * unit_price
                if current_cost + cost_increment > self.max_budget:
                    break

                key = (eq_type, crew)
                new_additions = dict(current_additions)
                if num_to_buy > 0:
                    new_additions[key] = num_to_buy

                generate_recursive(idx + 1, current_cost + cost_increment, new_additions, all_options)

        generate_recursive(0, 0.0, {}, all_options)

        # Sort by cost (ascending)
        all_options.sort(key=lambda x: x[0])

        # Now build equipment lists for each option
        results = []
        for cost, additions in all_options:
            # Build full equipment list with purchased items
            equipment_list = list(self.base_equipment)

            # Add purchased equipment
            purchase_id_counter = {}
            for (eq_type, crew), count in additions.items():
                # Find the equipment template
                for eq in self.base_equipment:
                    if eq.equipment_type == eq_type and eq.crew == crew:
                        template = eq
                        break
                else:
                    continue

                # Get max existing ID for this type and crew
                max_id = 0
                for eq in self.base_equipment:
                    if eq.equipment_type == eq_type and eq.crew == crew:
                        # Extract ID number
                        id_str = eq.equipment_id
                        # Format: "TypeName1-X"
                        parts = id_str.split(str(crew))
                        if len(parts) > 1:
                            num = int(parts[-1].split('-')[-1]) if '-' in parts[-1] else int(parts[-1])
                            max_id = max(max_id, num)

                # Create new equipment IDs
                for i in range(count):
                    new_id = f"{template.equipment_type.value}{crew}-{max_id + i + 1}"
                    new_eq = Equipment(
                        equipment_id=new_id,
                        equipment_type=eq_type,
                        crew=crew,
                        speed_mps=template.speed_mps,
                        unit_price=template.unit_price
                    )
                    equipment_list.append(new_eq)

            results.append((cost, equipment_list))

        return results

    def optimize(
        self,
        time_limit_per_problem: int = 180,
        max_combinations_to_try: int = 50,
        log_output: bool = False
    ) -> Tuple[ScheduleResult, float, List[Equipment]]:
        """
        Find the best schedule by trying different purchase combinations.

        Returns:
            Tuple of (best_result, total_cost, purchased_equipment)
        """
        options = self.generate_purchase_options()
        print(f"Generated {len(options)} purchase options")

        best_result = None
        best_makespan = float('inf')
        best_cost = 0.0
        best_equipment = []

        # Sort by cost and try combinations with lower cost first
        # (typically more budget left for better equipment utilization)
        options_to_try = options[:max_combinations_to_try]

        for cost, equipment_list in options_to_try:
            print(f"Trying purchase option with cost {cost} ({len(equipment_list)} equipment)...")

            try:
                solver = SchedulerSolver(
                    preprocessor=self.preprocessor,
                    crew1_available=True,
                    crew2_available=True,
                    available_equipment=equipment_list,
                    distance_func=self.distance_func
                )

                solver.build()
                result = solver.solve(time_limit_seconds=time_limit_per_problem)

                if result.makespan < best_makespan:
                    best_makespan = result.makespan
                    best_result = result
                    best_cost = cost
                    best_equipment = [
                        eq for eq in equipment_list
                        if eq not in self.base_equipment
                    ]
                    print(f"  New best makespan: {best_makespan}s ({cost} yuan)")

            except Exception as e:
                print(f"  Failed: {e}")
                continue

        if best_result is None:
            raise RuntimeError("No valid solution found")

        # Attach cost and purchased equipment to result
        best_result.total_cost = best_cost
        best_result.purchased_equipment = best_equipment

        return best_result, best_cost, best_equipment

    def optimize_binary_search(
        self,
        time_limit_per_problem: int = 120,
        log_output: bool = False
    ) -> Tuple[ScheduleResult, float, List[Equipment]]:
        """
        Optimized approach using binary search on makespan.

        For each makespan budget, try to find a purchase + schedule that fits.
        """
        # First, get a baseline with no purchases
        baseline_solver = SchedulerSolver(
            preprocessor=self.preprocessor,
            crew1_available=True,
            crew2_available=True,
            available_equipment=self.base_equipment,
            distance_func=self.distance_func
        )
        baseline_solver.build()
        baseline_result = baseline_solver.solve(time_limit_seconds=time_limit_per_problem)
        print(f"Baseline makespan (no purchase): {baseline_result.makespan}s")

        # Get purchase options sorted by cost
        options = self.generate_purchase_options()
        print(f"Generated {len(options)} purchase options")

        best_result = baseline_result
        best_cost = 0.0
        best_equipment = []

        # Try purchase options, prioritizing those that might help
        for cost, equipment_list in options:
            if cost > self.max_budget:
                continue

            print(f"Trying cost {cost}...")

            try:
                solver = SchedulerSolver(
                    preprocessor=self.preprocessor,
                    crew1_available=True,
                    crew2_available=True,
                    available_equipment=equipment_list,
                    distance_func=self.distance_func
                )

                solver.build()
                result = solver.solve(time_limit_seconds=time_limit_per_problem)

                if result.makespan < best_result.makespan:
                    best_result = result
                    best_cost = cost
                    best_equipment = [
                        eq for eq in equipment_list
                        if eq not in self.base_equipment
                    ]
                    print(f"  New best: makespan={result.makespan}s, cost={cost}")

                    # If we found a better solution, we might want to try more
                    # But for now, continue to explore

            except Exception as e:
                print(f"  Failed: {e}")
                continue

        best_result.total_cost = best_cost
        best_result.purchased_equipment = best_equipment

        return best_result, best_cost, best_equipment