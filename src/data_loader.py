"""Data loader module for reading Excel files."""

import re
from typing import Dict, List, Tuple, Optional
import pandas as pd

from models import (
    Process, Equipment, EquipmentType,
    WorkshopDistance, OperationRequirement
)
from config import WORKSHOPS
from time_utils import parse_workload


class WorkshopDistanceTable:
    """Table for looking up distances between workshops."""

    def __init__(self, distances: List[WorkshopDistance]):
        self.distances = distances
        self._matrix: Dict[str, Dict[str, float]] = {}
        self._build_matrix()

    def _build_matrix(self):
        """Build symmetric distance matrix."""
        for d in self.distances:
            if d.origin not in self._matrix:
                self._matrix[d.origin] = {}
            if d.destination not in self._matrix:
                self._matrix[d.destination] = {}

            self._matrix[d.origin][d.destination] = d.distance_m
            self._matrix[d.destination][d.origin] = d.distance_m

    def get_distance(self, origin: str, destination: str) -> float:
        """Get distance between two locations."""
        origin = origin.strip()
        destination = destination.strip()

        if origin == destination:
            return 0.0

        if origin in self._matrix and destination in self._matrix[origin]:
            return self._matrix[origin][destination]

        raise ValueError(f"Distance not found: {origin} -> {destination}")

    def get_all_locations(self) -> List[str]:
        """Get all unique locations."""
        return list(self._matrix.keys())

    def print_matrix(self):
        """Print the distance matrix in readable format."""
        locations = sorted(self.get_all_locations())
        print("\n距离矩阵:")
        header = "      " + "  ".join(f"{loc:>8}" for loc in locations)
        print(header)
        for row_loc in locations:
            row = f"{row_loc:>6}"
            for col_loc in locations:
                dist = self._matrix.get(row_loc, {}).get(col_loc, 0)
                row += f"{dist:>10.0f}"
            print(row)


def parse_process_id(raw_id: str) -> str:
    """
    Parse process ID from raw string like 'A1.缺陷填补' or 'C3.Sealing Coverage'.

    Returns just the ID part, e.g., 'A1', 'C3'.
    """
    raw = raw_id.strip()
    match = re.match(r'^([A-Z]\d+)', raw)
    if match:
        return match.group(1)
    return raw


def parse_equipment_efficiency(eff_str: str) -> List[Tuple[str, float]]:
    """
    Parse equipment efficiency string like:
    '精密灌装机200m³/h和自动化输送臂250m³/h'
    or
    'Precision Filling Machine 200m³/h and Automated Conveying Arm 250m³/h'

    Returns:
        List of (equipment_type_string, efficiency) tuples
    """
    parts = re.split(r'\s+和\s+|\s+and\s+', eff_str)

    results = []
    for part in parts:
        part = part.strip()
        match = re.match(r'^(.+?)\s*(\d+(?:\.\d+)?)\s*m³/?h$', part)
        if not match:
            raise ValueError(f"Cannot parse efficiency string: '{part}'")

        equip_type = match.group(1).strip()
        efficiency = float(match.group(2))
        results.append((equip_type, efficiency))

    return results


def normalize_equipment_type(type_str: str) -> EquipmentType:
    """Normalize equipment type string to EquipmentType enum."""
    type_str_lower = type_str.lower()

    cn_to_en = {
        '自动化输送臂': 'Automated Conveying Arm',
        '精密灌装机': 'Precision Filling Machine',
        '工业清洗机': 'Industrial Cleaning Machine',
        '高速抛光机': 'High-speed Polishing Machine',
        '自动传感多功能机': 'Automatic Sensing Multi-Function Machine',
    }

    for cn, en in cn_to_en.items():
        if cn in type_str_lower or en.lower() in type_str_lower:
            return EquipmentType.from_string(en)

    return EquipmentType.from_string(type_str)


def load_process_flow_table(df: pd.DataFrame) -> Tuple[List[Process], Dict[str, str]]:
    """
    Load and parse the Process Flow Table.
    """
    processes = []
    process_to_workshop: Dict[str, str] = {}

    df = df.copy()
    df['Workshop'] = df['Workshop'].ffill()

    for _, row in df.iterrows():
        workshop = row['Workshop']
        if pd.isna(workshop):
            continue
        workshop = str(workshop).strip()

        process_id_raw = row['Process ID']
        if pd.isna(process_id_raw):
            continue

        process_id = parse_process_id(process_id_raw)
        efficiency_str = row['Operational efficiency']
        workload = parse_workload(str(row['Workload']))
        note = row['Note'] if pd.notna(row.get('Note')) else None

        parsed = parse_equipment_efficiency(efficiency_str)
        requirements = []
        for equip_type_str, efficiency in parsed:
            try:
                equip_type = normalize_equipment_type(equip_type_str)
            except ValueError:
                equip_type_str_lower = equip_type_str.lower()
                found = False
                for et in EquipmentType:
                    if et.value.lower() in equip_type_str_lower or equip_type_str_lower in et.value.lower():
                        equip_type = et
                        found = True
                        break
                if not found:
                    raise ValueError(f"Unknown equipment type: {equip_type_str}")

            requirements.append(OperationRequirement(
                equipment_type=equip_type,
                efficiency=efficiency
            ))

        process = Process(
            workshop=workshop,
            process_id=process_id,
            expanded_id=process_id,
            original_id=process_id,
            requirements=requirements,
            workload=workload,
            note=note
        )
        processes.append(process)
        process_to_workshop[process_id] = workshop

    return processes, process_to_workshop


def parse_equipment_ids_list(raw_str: str, expected_count: int) -> List[str]:
    """
    Parse equipment IDs from raw string like:
    'Automated Conveying Arm1-1；
    Automated Conveying Arm1-2；
    ...'
    """
    if pd.isna(raw_str) or not raw_str:
        return []

    parts = re.split(r'[；;\n]+', raw_str.strip())
    ids = []

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Match full equipment ID like "Automated Conveying Arm1-1" or "High-speed Polishing Machine1-1"
        # Pattern: words, spaces, hyphens, then digit-digit at the end
        match = re.search(r'([A-Za-z][A-Za-z\s\-]*?\d+-\d+)', part)
        if match:
            full_id = match.group(1).strip()
            # Remove trailing period if present
            full_id = full_id.rstrip('。').rstrip('.')
            ids.append(full_id)
        else:
            # Fallback: try to extract any pattern
            match = re.search(r'([A-Za-z一-鿿]+)(\d+-\d+)', part)
            if match:
                type_name = match.group(1).strip()
                suffix = match.group(2)
                ids.append(f"{type_name}{suffix}")

    # If we got expected count, return them
    if len(ids) == expected_count:
        return ids

    # If we got nothing but expected count > 0, generate IDs
    if len(ids) == 0 and expected_count > 0:
        # Extract type name from first part
        type_match = re.match(r'^([A-Za-z\s]+)', parts[0] if parts else '')
        type_name = type_match.group(1).strip().replace(' ', '') if type_match else '设备'
        for i in range(1, expected_count + 1):
            ids.append(f"{type_name}1-{i}")

    return ids


def load_crew_configuration(df: pd.DataFrame) -> Tuple[List[Equipment], Dict[EquipmentType, float]]:
    """
    Load and parse the Crew Configuration Table.
    """
    equipment = []
    unit_prices: Dict[EquipmentType, float] = {}

    for _, row in df.iterrows():
        equip_type_raw = row['Equipment type']
        crew1_ids_raw = row['Equipment ID of Crew 1']
        crew2_ids_raw = row['Equipment ID of Crew 2']
        crew1_count = int(row['Crew 1'])
        crew2_count = int(row['Crew 2'])
        speed = float(row['Speed(m/s)'])
        unit_price = float(row['Unit Price(per unit)'])

        equip_type = normalize_equipment_type(equip_type_raw)
        unit_prices[equip_type] = unit_price

        crew1_ids = parse_equipment_ids_list(crew1_ids_raw, crew1_count)
        for eq_id in crew1_ids:
            equipment.append(Equipment(
                equipment_id=eq_id,
                equipment_type=equip_type,
                crew=1,
                speed_mps=speed,
                unit_price=unit_price
            ))

        crew2_ids = parse_equipment_ids_list(crew2_ids_raw, crew2_count)
        for eq_id in crew2_ids:
            equipment.append(Equipment(
                equipment_id=eq_id,
                equipment_type=equip_type,
                crew=2,
                speed_mps=speed,
                unit_price=unit_price
            ))

    return equipment, unit_prices


def load_workshop_distances(df: pd.DataFrame) -> WorkshopDistanceTable:
    """Load and parse the Workshop Distance Table."""
    distances = []

    for _, row in df.iterrows():
        origin = str(row['Origin']).strip()
        destination = str(row['Destination']).strip()
        dist_str = str(row['Distance']).strip()

        dist_match = re.match(r'(\d+(?:\.\d+)?)\s*m', dist_str)
        if not dist_match:
            raise ValueError(f"Cannot parse distance: {dist_str}")

        distance = float(dist_match.group(1))
        distances.append(WorkshopDistance(
            origin=origin,
            destination=destination,
            distance_m=distance
        ))

    return WorkshopDistanceTable(distances)


class DataLoader:
    """Main data loader class."""

    def __init__(self, excel_path: str):
        self.excel_path = excel_path
        self._processes: List[Process] = None
        self._equipment: List[Equipment] = None
        self._distances: WorkshopDistanceTable = None
        self._unit_prices: Dict[EquipmentType, float] = None
        self._process_to_workshop: Dict[str, str] = None

    def load_all(self):
        """Load all data from Excel file."""
        xl = pd.ExcelFile(self.excel_path)

        df_process = xl.parse('Process Flow Table')
        self._processes, self._process_to_workshop = load_process_flow_table(df_process)

        df_crew = xl.parse('Crew Configuration Table')
        self._equipment, self._unit_prices = load_crew_configuration(df_crew)

        df_dist = xl.parse('Workshop Distance Table')
        self._distances = load_workshop_distances(df_dist)

    @property
    def processes(self) -> List[Process]:
        if self._processes is None:
            raise RuntimeError("Data not loaded. Call load_all() first.")
        return self._processes

    @property
    def equipment(self) -> List[Equipment]:
        if self._equipment is None:
            raise RuntimeError("Data not loaded. Call load_all() first.")
        return self._equipment

    @property
    def distances(self) -> WorkshopDistanceTable:
        if self._distances is None:
            raise RuntimeError("Data not loaded. Call load_all() first.")
        return self._distances

    @property
    def unit_prices(self) -> Dict[EquipmentType, float]:
        if self._unit_prices is None:
            raise RuntimeError("Data not loaded. Call load_all() first.")
        return self._unit_prices

    def get_distance(self, origin: str, destination: str) -> float:
        """Get distance between two locations."""
        return self._distances.get_distance(origin, destination)