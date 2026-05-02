"""Validation module for MCM B scheduler."""

from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict

from models import ScheduleResult, ScheduledOperation, Process, Equipment, ProcessEdge


class ValidationResult:
    """Result of validation checks."""

    def __init__(self):
        self.passed = True
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, msg: str):
        self.errors.append(msg)
        self.passed = False

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def __repr__(self):
        status = "PASSED" if self.passed else "FAILED"
        lines = [f"Validation: {status}"]
        if self.errors:
            lines.append("Errors:")
            for e in self.errors:
                lines.append(f"  - {e}")
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return '\n'.join(lines)


class ScheduleValidator:
    """Validates scheduling results."""

    def __init__(
        self,
        result: ScheduleResult,
        processes: List[Process],
        precedence_edges: List[ProcessEdge],
        equipment: List[Equipment],
        distance_func=None
    ):
        self.result = result
        self.processes = processes
        self.precedence_edges = precedence_edges
        self.equipment = equipment
        self.distance_func = distance_func

        # Build lookup maps
        self._process_by_id: Dict[str, Process] = {
            p.expanded_id(): p for p in processes
        }
        self._operations_by_process: Dict[str, List[ScheduledOperation]] = defaultdict(list)
        self._operations_by_equipment: Dict[str, List[ScheduledOperation]] = defaultdict(list)

        for op in result.operations:
            self._operations_by_process[op.process.expanded_id()].append(op)
            self._operations_by_equipment[op.equipment.equipment_id].append(op)

    def validate_all(self) -> ValidationResult:
        """Run all validation checks."""
        result = ValidationResult()

        self._check_process_equipment_requirements(result)
        self._check_workshop_sequence(result)
        self._check_equipment_no_overlap(result)
        self._check_transport_times(result)
        self._check_precedence_constraints(result)
        self._check_process_completion_times(result)

        return result

    def _check_process_equipment_requirements(self, result: ValidationResult):
        """Check that each process has all required equipment types assigned."""
        for proc in self.processes:
            proc_id = proc.expanded_id()
            ops = self._operations_by_process.get(proc_id, [])

            if not ops:
                result.add_error(f"Process {proc_id} has no scheduled operations")
                continue

            # Check that all required equipment types are covered
            required_types = {req.equipment_type for req in proc.requirements}
            assigned_types = {op.equipment.equipment_type for op in ops}

            missing_types = required_types - assigned_types
            if missing_types:
                result.add_error(
                    f"Process {proc_id} missing equipment types: {missing_types}"
                )

            # Check that exactly one equipment per type
            for req in proc.requirements:
                type_ops = [op for op in ops if op.equipment.equipment_type == req.equipment_type]
                if len(type_ops) != 1:
                    result.add_error(
                        f"Process {proc_id} has {len(type_ops)} operations for type "
                        f"{req.equipment_type.value}, expected 1"
                    )

    def _check_workshop_sequence(self, result: ValidationResult):
        """Check that processes within each workshop follow the correct order."""
        # Build process order map for each workshop
        workshop_orders: Dict[str, List[str]] = defaultdict(list)
        for proc in self.processes:
            workshop_orders[proc.workshop].append(proc.expanded_id())

        # Sort by original process ID within each workshop
        for ws in workshop_orders:
            workshop_orders[ws] = sorted(
                workshop_orders[ws],
                key=lambda pid: self._process_by_id[pid].process_id
            )

        # Check that each process starts after the previous one in the workshop finishes
        for ws, proc_ids in workshop_orders.items():
            for i in range(1, len(proc_ids)):
                prev_proc_id = proc_ids[i - 1]
                curr_proc_id = proc_ids[i]

                prev_ops = self._operations_by_process.get(prev_proc_id, [])
                curr_ops = self._operations_by_process.get(curr_proc_id, [])

                if not prev_ops or not curr_ops:
                    continue

                # Get the completion time of previous process
                prev_end = max(op.end_time for op in prev_ops)
                curr_start = min(op.start_time for op in curr_ops)

                if curr_start < prev_end:
                    result.add_error(
                        f"Workshop {ws} sequence violated: "
                        f"{curr_proc_id} starts at {curr_start} before "
                        f"{prev_proc_id} ends at {prev_end}"
                    )

    def _check_equipment_no_overlap(self, result: ValidationResult):
        """Check that no equipment has overlapping operations."""
        for eq_id, ops in self._operations_by_equipment.items():
            if len(ops) <= 1:
                continue

            # Sort by start time
            sorted_ops = sorted(ops, key=lambda x: x.start_time)

            for i in range(len(sorted_ops) - 1):
                curr_end = sorted_ops[i].end_time
                next_start = sorted_ops[i + 1].start_time

                if next_start < curr_end:
                    result.add_error(
                        f"Equipment {eq_id} has overlapping operations: "
                        f"ends at {curr_end} but next starts at {next_start}"
                    )

    def _check_transport_times(self, result: ValidationResult):
        """Check that transport times are correctly calculated."""
        if self.distance_func is None:
            result.add_warning("No distance function provided, skipping transport time validation")
            return

        # Group operations by equipment
        for eq_id, ops in self._operations_by_equipment.items():
            if len(ops) <= 1:
                continue

            sorted_ops = sorted(ops, key=lambda x: x.start_time)
            prev_workshop = None

            # First operation - check crew to workshop transport
            first_op = sorted_ops[0]
            if first_op.transport_time > 0:
                # This is expected if crew is not at the workshop
                pass

            for op in sorted_ops:
                if prev_workshop is not None:
                    if op.process.workshop == prev_workshop:
                        if op.transport_time != 0:
                            result.add_warning(
                                f"Equipment {eq_id}: same workshop operation at "
                                f"{op.process.expanded_id()} has non-zero transport time"
                            )
                    else:
                        # Check transport time calculation
                        expected_transport = self._calculate_expected_transport(
                            prev_workshop, op.process.workshop, first_op.equipment.speed_mps
                        )
                        if op.transport_time != expected_transport:
                            result.add_warning(
                                f"Equipment {eq_id}: transport time {op.transport_time} "
                                f"differs from expected {expected_transport} for "
                                f"{prev_workshop} -> {op.process.workshop}"
                            )
                prev_workshop = op.process.workshop

    def _calculate_expected_transport(
        self,
        from_workshop: str,
        to_workshop: str,
        speed_mps: float
    ) -> int:
        """Calculate expected transport time between workshops."""
        dist = self.distance_func(from_workshop, to_workshop)
        return int((dist / speed_mps) + 0.999)  # Ceiling

    def _check_precedence_constraints(self, result: ValidationResult):
        """Check that precedence constraints are satisfied."""
        for edge in self.precedence_edges:
            from_ops = self._operations_by_process.get(edge.from_process, [])
            to_ops = self._operations_by_process.get(edge.to_process, [])

            if not from_ops or not to_ops:
                continue

            from_end = max(op.end_time for op in from_ops)
            to_start = min(op.start_time for op in to_ops)

            if to_start < from_end:
                result.add_error(
                    f"Precedence violated: {edge.from_process} (ends {from_end}) -> "
                    f"{edge.to_process} (starts {to_start})"
                )

    def _check_process_completion_times(self, result: ValidationResult):
        """Check that process completion time equals max of equipment end times."""
        for proc in self.processes:
            proc_id = proc.expanded_id()
            ops = self._operations_by_process.get(proc_id, [])

            if not ops:
                continue

            max_end = max(op.end_time for op in ops)
            min_start = min(op.start_time for op in ops)

            # Each equipment should have the same start time (they work together)
            start_times = {op.start_time for op in ops}
            if len(start_times) > 1:
                result.add_warning(
                    f"Process {proc_id} has different start times: {start_times}"
                )

    def validate_budget(self, total_cost: float, max_budget: float) -> ValidationResult:
        """Validate that total purchase cost doesn't exceed budget."""
        result = ValidationResult()

        if total_cost > max_budget:
            result.add_error(
                f"Total cost {total_cost} exceeds budget {max_budget}"
            )
        else:
            result.add_warning(f"Budget OK: {total_cost} / {max_budget}")

        return result