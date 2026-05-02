"""Time utilities for MCM B scheduler."""

import math
from typing import Union

def calculate_processing_time(workload: float, efficiency: float) -> int:
    """
    Calculate processing time in seconds.

    Args:
        workload: Workload in m³
        efficiency: Efficiency in m³/h

    Returns:
        Processing time in seconds, ceiling rounded
    """
    if efficiency <= 0:
        raise ValueError(f"Efficiency must be positive, got {efficiency}")
    hours = workload / efficiency
    return math.ceil(hours * 3600)

def calculate_transport_time(distance_m: float, speed_mps: float) -> int:
    """
    Calculate transport time in seconds.

    Args:
        distance_m: Distance in meters
        speed_mps: Speed in meters per second

    Returns:
        Transport time in seconds, ceiling rounded
    """
    if speed_mps <= 0:
        raise ValueError(f"Speed must be positive, got {speed_mps}")
    seconds = distance_m / speed_mps
    return math.ceil(seconds)

def format_seconds(total_seconds: int) -> str:
    """
    Format seconds into HH:MM:SS string.

    Args:
        total_seconds: Total seconds

    Returns:
        Formatted string
    """
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def parse_distance(distance_str: str) -> float:
    """
    Parse distance string like '400m' to float.

    Args:
        distance_str: Distance string

    Returns:
        Distance in meters
    """
    return float(distance_str.rstrip('m'))

def parse_workload(workload_str: str) -> float:
    """
    Parse workload string like '300m³' to float.

    Args:
        workload_str: Workload string

    Returns:
        Workload in m³
    """
    s = workload_str.strip()
    s = s.rstrip('m³').rstrip('m3').rstrip('m')
    return float(s)