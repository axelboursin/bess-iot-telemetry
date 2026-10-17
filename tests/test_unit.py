import json
from datetime import UTC, datetime

import pytest

from bess_telemetry.battery import BatteryModel
from bess_telemetry.config import AgentConfig
from bess_telemetry.messages import CommandError, build_telemetry, parse_command
from bess_telemetry.registers import (
    SETPOINT_REGISTER,
    TELEMETRY_REGISTERS,
    BatteryStatus,
    decode,
    decode_block,
    encode,
)

# Registers -------------------------------------------------------------------


@pytest.mark.parametrize("value", [-1000.0, -0.1, 0.0, 0.1, 999.9, 3276.7, -3276.8])
def test_signed_roundtrip(value):
    assert decode(encode(value, SETPOINT_REGISTER), SETPOINT_REGISTER) == pytest.approx(value)


def test_negative_values_use_twos_complement():
    assert encode(-0.1, SETPOINT_REGISTER) == 0xFFFF


def test_out_of_range_values_are_rejected():
    with pytest.raises(ValueError):
        encode(5000.0, SETPOINT_REGISTER)
    soc = TELEMETRY_REGISTERS[0]
    with pytest.raises(ValueError):
        encode(-1.0, soc)


def test_decode_block_maps_every_register():
    battery = BatteryModel()
    snapshot = battery.snapshot()
    raw = [encode(snapshot[r.name], r) for r in TELEMETRY_REGISTERS]
    decoded = decode_block(raw)
    for name, value in snapshot.items():
        assert decoded[name] == pytest.approx(value, abs=0.1)


# Battery model ---------------------------------------------------------------


def test_discharge_reduces_soc_and_respects_ramp():
    battery = BatteryModel(capacity_kwh=1000, max_power_kw=500, ramp_kw_per_s=100, soc_pct=50)
    battery.set_setpoint(500)
    battery.step(1)
    assert battery.power_kw == pytest.approx(100)
    for _ in range(60):
        battery.step(1)
    assert battery.power_kw == pytest.approx(500)
    assert battery.soc_pct < 50
    assert battery.status is BatteryStatus.DISCHARGING


def test_setpoint_is_clamped_to_max_power():
    battery = BatteryModel(max_power_kw=500)
    battery.set_setpoint(-10_000)
    assert battery.setpoint_kw == -500


def test_power_drops_to_zero_at_soc_limits():
    battery = BatteryModel(soc_pct=5.0)
    battery.set_setpoint(500)
    battery.step(1)
    assert battery.power_kw == 0
    assert battery.status is BatteryStatus.IDLE


def test_fault_forces_zero_power():
    battery = BatteryModel(power_kw=300, ramp_kw_per_s=1000)
    battery.set_setpoint(300)
    battery.fault = True
    battery.step(1)
    assert battery.power_kw == 0
    assert battery.status is BatteryStatus.FAULT


# Messages --------------------------------------------------------------------


def test_telemetry_payload_contract():
    now = datetime(2026, 1, 2, 3, 4, 5, 678000, tzinfo=UTC)
    payload = json.loads(build_telemetry("site-01", {"soc_pct": 50.0, "status": 1.0}, now))
    assert payload == {
        "schema_version": 1,
        "site_id": "site-01",
        "ts": "2026-01-02T03:04:05.678Z",
        "soc_pct": 50.0,
        "status": 1,
    }


def test_valid_command_is_parsed():
    command = parse_command(b'{"command_id": "c1", "setpoint_kw": -250}', max_power_kw=1000)
    assert command.command_id == "c1"
    assert command.setpoint_kw == -250.0


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        b'{"setpoint_kw": 10}',
        b'{"command_id": "c1"}',
        b'{"command_id": "c1", "setpoint_kw": "10"}',
        b'{"command_id": "c1", "setpoint_kw": true}',
        b'{"command_id": "c1", "setpoint_kw": 1000.1}',
    ],
)
def test_invalid_commands_are_rejected(raw):
    with pytest.raises(CommandError):
        parse_command(raw, max_power_kw=1000)


# Config ----------------------------------------------------------------------


def test_config_requires_site_id():
    with pytest.raises(ValueError):
        AgentConfig.from_env({})


def test_config_requires_certificates_when_tls_enabled():
    with pytest.raises(ValueError):
        AgentConfig.from_env({"SITE_ID": "s", "MQTT_TLS": "true"})


def test_topics_are_scoped_to_site():
    config = AgentConfig.from_env({"SITE_ID": "site-01"})
    assert config.client_id == "site-01"
    assert config.telemetry_topic == "bess/site-01/telemetry"
    assert config.command_topic == "bess/site-01/commands"
