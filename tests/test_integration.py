"""End-to-end test: real Modbus TCP server and client, fake MQTT broker."""

import asyncio
import json
import socket

import pytest
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.server import ServerAsyncStop, StartAsyncTcpServer

from bess_telemetry.agent import EdgeAgent
from bess_telemetry.battery import BatteryModel
from bess_telemetry.config import AgentConfig
from bess_telemetry.simulator import build_context, sync_registers


class FakeMqtt:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, json.loads(payload), qos))


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_agent_reads_simulator_and_writes_setpoint():
    port = free_port()
    battery = BatteryModel(soc_pct=60)
    context = build_context()
    sync_registers(context, battery)
    server = asyncio.create_task(StartAsyncTcpServer(context=context, address=("127.0.0.1", port)))
    await asyncio.sleep(0.3)

    modbus = AsyncModbusTcpClient("127.0.0.1", port=port)
    await modbus.connect()
    mqtt = FakeMqtt()
    agent = EdgeAgent(AgentConfig(site_id="site-test"), modbus, mqtt)

    try:
        assert await agent.poll_once()
        topic, payload, qos = mqtt.published[-1]
        assert topic == "bess/site-test/telemetry"
        assert qos == 1
        assert payload["soc_pct"] == pytest.approx(60.0)
        assert payload["status"] == 0

        await agent.handle_command(b'{"command_id": "c-42", "setpoint_kw": 400}')
        topic, ack, _ = mqtt.published[-1]
        assert topic == "bess/site-test/commands/ack"
        assert ack == {"command_id": "c-42", "accepted": True, "reason": ""}

        # The simulator picks up the setpoint on its next tick.
        sync_registers(context, battery)
        battery.step(1)
        sync_registers(context, battery)
        assert battery.setpoint_kw == pytest.approx(400)

        assert await agent.poll_once()
        assert mqtt.published[-1][1]["active_power_kw"] > 0
        assert mqtt.published[-1][1]["status"] == 2  # discharging

        await agent.handle_command(b'{"command_id": "c-43", "setpoint_kw": 99999}')
        assert mqtt.published[-1][1]["accepted"] is False
    finally:
        modbus.close()
        await ServerAsyncStop()
        server.cancel()
