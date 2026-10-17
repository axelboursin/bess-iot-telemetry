"""Telemetry payloads and command parsing.

Kept free of I/O so the contract with the cloud side is easy to unit test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

SCHEMA_VERSION = 1


def build_telemetry(site_id: str, values: dict[str, float], now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "site_id": site_id,
        "ts": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        **values,
    }
    payload["status"] = int(payload["status"])
    return json.dumps(payload, separators=(",", ":"))


class CommandError(ValueError):
    pass


@dataclass(frozen=True)
class SetpointCommand:
    command_id: str
    setpoint_kw: float


def parse_command(raw: bytes, max_power_kw: float) -> SetpointCommand:
    """Validate a command received from the cloud before it reaches the PMS."""
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandError("payload is not valid JSON") from exc
    if not isinstance(body, dict):
        raise CommandError("payload must be a JSON object")

    command_id = body.get("command_id")
    if not isinstance(command_id, str) or not command_id:
        raise CommandError("command_id must be a non-empty string")

    setpoint = body.get("setpoint_kw")
    if isinstance(setpoint, bool) or not isinstance(setpoint, (int, float)):
        raise CommandError("setpoint_kw must be a number")
    if abs(setpoint) > max_power_kw:
        raise CommandError(f"setpoint_kw must be within +/-{max_power_kw} kW")

    return SetpointCommand(command_id=command_id, setpoint_kw=float(setpoint))


def build_ack(command_id: str | None, accepted: bool, reason: str = "") -> str:
    return json.dumps(
        {"command_id": command_id, "accepted": accepted, "reason": reason},
        separators=(",", ":"),
    )
