"""Preprocessing module for MCM B scheduler."""

import re
from typing import Dict, List, Set, Tuple
from collections import defaultdict

from models import Process, Equipment, EquipmentType, ProcessEdge, OperationRequirement
from config import C_WORKSHOP_REPEAT_PROCESSES, C_WORKSHOP_REPEAT_TIMES, WORKSHOPS


class Preprocessor:
    """Handles preprocessing of data for the scheduler."""

    def __init__(self, processes: List[Process], equipment: List[Equipment]):
        self.processes = processes
        self.equipment = equipment
        self._expanded_processes: List[Process] = None
        self._precedence_edges: List[ProcessEdge] = None
        self._process_order_within_workshop: Dict[str, List[str]] = None
        self._equipment_by_type: Dict[EquipmentType, List[Equipment]] = None
        self._equipment_by_crew: Dict[int, List[Equipment]] = None

    def preprocess(self):
        """Run all preprocessing steps."""
        self._expand_c_workshop_processes()
        self._build_precedence_edges()
        self._build_process_order_map()
        self._build_equipment_mappings()

    def _expand_c_workshop_processes(self):
        """
        Expand C3, C4, C5 to be repeated 3 times each.

        The order within C workshop follows round-robin across repeat indices:
        C1, C2, C3_1, C4_1, C5_1, C3_2, C4_2, C5_2, C3_3, C4_3, C5_3
        """
        expanded = []

        # Separate processes
        c_workshop_procs = [p for p in self.processes if p.workshop == 'C']
        c_non_repeat = [p for p in c_workshop_procs if p.process_id not in C_WORKSHOP_REPEAT_PROCESSES]
        c_repeat_procs = [p for p in c_workshop_procs if p.process_id in C_WORKSHOP_REPEAT_PROCESSES]

        # Non-C processes
        non_c_procs = [p for p in self.processes if p.workshop != 'C']
        expanded.extend(non_c_procs)

        # Append C1, C2 first
        expanded.extend(c_non_repeat)

        # Round-robin for C3, C4, C5
        for rep in range(1, C_WORKSHOP_REPEAT_TIMES + 1):
            for proc_id in ['C3', 'C4', 'C5']:
                for p in c_repeat_procs:
                    if p.process_id == proc_id:
                        expanded_process = Process(
                            workshop=p.workshop,
                            process_id=p.process_id,
                            expanded_id=f"{proc_id}_{rep}",
                            original_id=p.process_id,
                            requirements=p.requirements,
                            workload=p.workload,
                            note=p.note,
                            repeat_index=rep
                        )
                        expanded.append(expanded_process)
                        break

        self._expanded_processes = expanded

    def _build_precedence_edges(self):
        """
        Build precedence edges within each workshop.
        Uses expanded_processes natural order (not sorted by process_id).
        """
        edges = []
        workshop_processes = defaultdict(list)

        for proc in self._expanded_processes:
            workshop_processes[proc.workshop].append(proc)

        for workshop, procs in workshop_processes.items():
            # Use natural order from expanded_processes
            for i in range(len(procs) - 1):
                edges.append(ProcessEdge(
                    from_process=procs[i].expanded_id,
                    to_process=procs[i + 1].expanded_id,
                    workshop=workshop
                ))

        self._precedence_edges = edges

    def _build_process_order_map(self):
        """
        Build a map of process order within each workshop.
        Uses expanded_processes natural order.
        """
        order_map = defaultdict(list)
        workshop_processes = defaultdict(list)

        for proc in self._expanded_processes:
            workshop_processes[proc.workshop].append(proc)

        for workshop, procs in workshop_processes.items():
            # Use natural order from expanded_processes
            order_map[workshop] = [p.expanded_id for p in procs]

        self._process_order_within_workshop = order_map

    def _build_equipment_mappings(self):
        """Build mappings of equipment by type and crew."""
        by_type = defaultdict(list)
        by_crew = defaultdict(list)

        for eq in self.equipment:
            by_type[eq.equipment_type].append(eq)
            by_crew[eq.crew].append(eq)

        self._equipment_by_type = by_type
        self._equipment_by_crew = by_crew

    @property
    def expanded_processes(self) -> List[Process]:
        if self._expanded_processes is None:
            raise RuntimeError("Preprocessing not done. Call preprocess() first.")
        return self._expanded_processes

    @property
    def precedence_edges(self) -> List[ProcessEdge]:
        if self._precedence_edges is None:
            raise RuntimeError("Preprocessing not done. Call preprocess() first.")
        return self._precedence_edges

    @property
    def process_order_within_workshop(self) -> Dict[str, List[str]]:
        if self._process_order_within_workshop is None:
            raise RuntimeError("Preprocessing not done. Call preprocess() first.")
        return self._process_order_within_workshop

    @property
    def equipment_by_type(self) -> Dict[EquipmentType, List[Equipment]]:
        if self._equipment_by_type is None:
            raise RuntimeError("Preprocessing not done. Call preprocess() first.")
        return self._equipment_by_type

    @property
    def equipment_by_crew(self) -> Dict[int, List[Equipment]]:
        if self._equipment_by_crew is None:
            raise RuntimeError("Preprocessing not done. Call preprocess() first.")
        return self._equipment_by_crew

    def get_process_by_id(self, process_id: str) -> Process:
        """Get a process by its expanded ID."""
        for proc in self._expanded_processes:
            if proc.expanded_id == process_id:
                return proc
        raise ValueError(f"Process not found: {process_id}")

    def get_workshop_for_process(self, process_id: str) -> str:
        """Get the workshop for a process."""
        return self.get_process_by_id(process_id).workshop

    def get_equipment_types_for_process(self, process_id: str) -> List[EquipmentType]:
        """Get the required equipment types for a process."""
        proc = self.get_process_by_id(process_id)
        return [req.equipment_type for req in proc.requirements]

    def get_equipment_for_type_and_crew(
        self, equip_type: EquipmentType, crew: int
    ) -> List[Equipment]:
        """Get equipment of a specific type and crew."""
        result = []
        for eq in self.equipment:
            if eq.equipment_type == equip_type and eq.crew == crew:
                result.append(eq)
        return result

    def get_total_process_count(self) -> int:
        """Get total number of expanded processes."""
        return len(self._expanded_processes)

    def print_summary(self):
        """Print a summary of the preprocessed data."""
        print(f"\n{'='*60}")
        print("预处理摘要")
        print(f"{'='*60}")
        print(f"原始工序数: {len(self.processes)}")
        print(f"展开后工序数: {len(self._expanded_processes)}")
        print(f"优先约束边数: {len(self._precedence_edges)}")

        print(f"\n班组设备数:")
        for crew in [1, 2]:
            crew_eq = self._equipment_by_crew.get(crew, [])
            print(f"  Crew {crew}: {len(crew_eq)} 台")

        print(f"\n各车间工序顺序:")
        for ws in sorted(self._process_order_within_workshop.keys()):
            order = self._process_order_within_workshop[ws]
            print(f"  Workshop {ws}: {', '.join(order)}")

        print(f"\nC车间展开工序:")
        c_procs = [p for p in self._expanded_processes if p.workshop == 'C']
        for p in c_procs:
            req_types = [r.equipment_type.name for r in p.requirements]
            print(f"  {p.expanded_id}: {req_types}, workload={p.workload}m³")