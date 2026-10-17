"""Modbus holding-register map shared by the simulator and the edge agent.

Every value is stored in a single 16-bit register with a fixed scale factor.
Signed values use two's complement, as most battery PMS vendors do.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class BatteryStatus(IntEnum):
    IDLE = 0
    CHARGING = 1
    DISCHARGING = 2
    FAULT = 3


@dataclass(frozen=True)
class Register:
    name: str
    address: int
    scale: float
    signed: bool
    unit: str


# Read-only telemetry block, starting at address 0.
TELEMETRY_REGISTERS: list[Register] = [
    Register("soc_pct", 0, 0.1, False, "%"),
    Register("soh_pct", 1, 0.1, False, "%"),
    Register("active_power_kw", 2, 0.1, True, "kW"),
    Register("reactive_power_kvar", 3, 0.1, True, "kvar"),
    Register("temperature_c", 4, 0.1, True, "degC"),
    Register("dc_voltage_v", 5, 0.1, False, "V"),
    Register("status", 6, 1, False, ""),
]

TELEMETRY_START = 0
TELEMETRY_COUNT = len(TELEMETRY_REGISTERS)

# Writable control register: active power setpoint (positive = discharge).
SETPOINT_REGISTER = Register("setpoint_kw", 10, 0.1, True, "kW")


def encode(value: float, register: Register) -> int:
    """Convert an engineering value into a raw 16-bit register value."""
    raw = int(round(value / register.scale))
    if register.signed:
        if not -0x8000 <= raw <= 0x7FFF:
            raise ValueError(f"{register.name}={value} does not fit in int16")
        return raw & 0xFFFF
    if not 0 <= raw <= 0xFFFF:
        raise ValueError(f"{register.name}={value} does not fit in uint16")
    return raw


def decode(raw: int, register: Register) -> float:
    """Convert a raw 16-bit register value into an engineering value."""
    if not 0 <= raw <= 0xFFFF:
        raise ValueError(f"raw value {raw} is not a 16-bit register")
    if register.signed and raw >= 0x8000:
        raw -= 0x10000
    return round(raw * register.scale, 3)


def decode_block(raw_values: list[int]) -> dict[str, float]:
    """Decode the telemetry block read starting at TELEMETRY_START."""
    if len(raw_values) != TELEMETRY_COUNT:
        raise ValueError(f"expected {TELEMETRY_COUNT} registers, got {len(raw_values)}")
    return {reg.name: decode(raw, reg) for reg, raw in zip(TELEMETRY_REGISTERS, raw_values, strict=True)}
