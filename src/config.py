"""Configuration module for MCM B scheduler."""

from dataclasses import dataclass
from typing import List

# Workshop names
WORKSHOPS = ['A', 'B', 'C', 'D', 'E']

# C workshop processes that repeat 3 times
C_WORKSHOP_REPEAT_PROCESSES = ['C3', 'C4', 'C5']
C_WORKSHOP_REPEAT_TIMES = 3

# Budget for Problem 4
PURCHASE_BUDGET = 500000

# Default speed (m/s)
DEFAULT_SPEED_MPS = 2.0