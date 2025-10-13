from __future__ import annotations
from dataclasses import dataclass

@dataclass
class MotorInfo:
    short: str
    long: str
    steps: int
    eng_value: float
    unit: str            # "mm" or "deg"
    span: float
    lbound: float
    ubound: float
    speed: float
    speed_unit: str      # "mm/s" or "deg/s"
