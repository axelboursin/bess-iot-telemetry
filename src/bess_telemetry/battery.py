"""A deliberately simple physical model of a battery energy storage system.

Sign convention: positive power discharges the battery (export to the grid),
negative power charges it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bess_telemetry.registers import BatteryStatus


@dataclass
class BatteryModel:
    capacity_kwh: float = 2000.0
    max_power_kw: float = 1000.0
    ramp_kw_per_s: float = 200.0
    soc_min_pct: float = 5.0
    soc_max_pct: float = 95.0
    ambient_c: float = 22.0
    nominal_voltage_v: float = 800.0

    soc_pct: float = 50.0
    soh_pct: float = 98.5
    power_kw: float = 0.0
    setpoint_kw: float = 0.0
    temperature_c: float = field(default=22.0)
    fault: bool = False

    def set_setpoint(self, kw: float) -> None:
        self.setpoint_kw = max(-self.max_power_kw, min(self.max_power_kw, kw))

    def step(self, dt_s: float) -> None:
        """Advance the model by dt_s seconds."""
        if dt_s <= 0:
            raise ValueError("dt_s must be positive")

        target = 0.0 if self.fault else self._limit_by_soc(self.setpoint_kw)

        # Power follows the setpoint with a bounded ramp rate.
        max_delta = self.ramp_kw_per_s * dt_s
        delta = max(-max_delta, min(max_delta, target - self.power_kw))
        self.power_kw = self._limit_by_soc(self.power_kw + delta)

        energy_kwh = self.power_kw * dt_s / 3600.0
        self.soc_pct -= 100.0 * energy_kwh / self.capacity_kwh
        self.soc_pct = max(0.0, min(100.0, self.soc_pct))

        # First-order thermal model: heats up with absolute power.
        steady_c = self.ambient_c + 15.0 * abs(self.power_kw) / self.max_power_kw
        tau_s = 600.0
        self.temperature_c += (steady_c - self.temperature_c) * min(1.0, dt_s / tau_s)

    def _limit_by_soc(self, kw: float) -> float:
        if kw > 0 and self.soc_pct <= self.soc_min_pct:
            return 0.0
        if kw < 0 and self.soc_pct >= self.soc_max_pct:
            return 0.0
        return kw

    @property
    def status(self) -> BatteryStatus:
        if self.fault:
            return BatteryStatus.FAULT
        if self.power_kw > 0.5:
            return BatteryStatus.DISCHARGING
        if self.power_kw < -0.5:
            return BatteryStatus.CHARGING
        return BatteryStatus.IDLE

    @property
    def dc_voltage_v(self) -> float:
        # Open-circuit voltage rises roughly linearly with state of charge.
        return self.nominal_voltage_v * (0.9 + 0.2 * self.soc_pct / 100.0)

    @property
    def reactive_power_kvar(self) -> float:
        return 0.05 * self.power_kw

    def snapshot(self) -> dict:
        return {
            "soc_pct": self.soc_pct,
            "soh_pct": self.soh_pct,
            "active_power_kw": self.power_kw,
            "reactive_power_kvar": self.reactive_power_kvar,
            "temperature_c": self.temperature_c,
            "dc_voltage_v": self.dc_voltage_v,
            "status": int(self.status),
        }
