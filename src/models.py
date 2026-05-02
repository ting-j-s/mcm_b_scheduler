"""Data models for MCM B scheduler."""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

class EquipmentType(Enum):
    """Equipment type enumeration."""
    AUTOMATED_CONVEYING_ARM = "Automated Conveying Arm"
    INDUSTRIAL_CLEANING_MACHINE = "Industrial Cleaning Machine"
    PRECISION_FILLING_MACHINE = "Precision Filling Machine"
    AUTOMATIC_SENSING_MULTI_FUNCTION_MACHINE = "Automatic Sensing Multi-Function Machine"
    HIGH_SPEED_POLISHING_MACHINE = "High-speed Polishing Machine"

    @classmethod
    def from_string(cls, s: str) -> 'EquipmentType':
        s_lower = s.strip().lower()
        for member in cls:
            if member.value.lower() == s_lower:
                return member
            if member.name.lower().replace('_', ' ') == s_lower:
                return member
        raise ValueError(f"Unknown equipment type: {s}")

@dataclass
class OperationRequirement:
    """Single equipment requirement for a process operation."""
    equipment_type: EquipmentType
    efficiency: float  # m³/h

    def __hash__(self):
        return hash((self.equipment_type, self.efficiency))

@dataclass
class Process:
    """Represents a single process in the workshop flow."""
    workshop: str
    process_id: str          # e.g., 'A1', 'C3'
    expanded_id: str          # e.g., 'A1', 'C3_1', 'C3_2'
    original_id: str          # Original ID before expansion
    requirements: List[OperationRequirement]
    workload: float           # m³
    note: Optional[str] = None
    repeat_index: Optional[int] = None  # 1, 2, 3 for expanded processes

@dataclass
class Equipment:
    """Represents a specific equipment instance."""
    equipment_id: str
    equipment_type: EquipmentType
    crew: int  # 1 or 2
    speed_mps: float
    unit_price: float

    def __hash__(self):
        return hash(self.equipment_id)

    def __eq__(self, other):
        if not isinstance(other, Equipment):
            return False
        return self.equipment_id == other.equipment_id

@dataclass
class WorkshopDistance:
    """Represents distance between two locations."""
    origin: str
    destination: str
    distance_m: float

@dataclass
class ProcessEdge:
    """Represents a precedence constraint between processes."""
    from_process: str
    to_process: str
    workshop: str

@dataclass
class ScheduledOperation:
    """Represents a scheduled operation."""
    process: Process
    equipment: Equipment
    start_time: int   # seconds
    end_time: int     # seconds
    transport_time: int = 0

    @property
    def duration(self) -> int:
        return self.end_time - self.start_time

@dataclass
class ScheduleResult:
    """Result of a scheduling problem."""
    makespan: int
    operations: List[ScheduledOperation]
    total_cost: float = 0.0
    purchased_equipment: List[Equipment] = field(default_factory=list)