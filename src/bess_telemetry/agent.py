"""Edge agent: polls the battery over Modbus TCP and bridges it to MQTT.

- Telemetry is published with QoS 1 to bess/<site_id>/telemetry.
- Setpoint commands arrive on bess/<site_id>/commands, are validated, written
  to the PMS, and acknowledged on bess/<site_id>/commands/ack.
- While the uplink is down, paho-mqtt queues QoS 1 messages in memory
  (bounded by MAX_QUEUED_MESSAGES) and flushes them on reconnect.

Run with:  bess-agent  (or  python -m bess_telemetry.agent)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import ssl
from typing import Any

import paho.mqtt.client as mqtt
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from bess_telemetry.config import AgentConfig
from bess_telemetry.messages import CommandError, build_ack, build_telemetry, parse_command
from bess_telemetry.registers import (
    SETPOINT_REGISTER,
    TELEMETRY_COUNT,
    TELEMETRY_START,
    decode_block,
    encode,
)

log = logging.getLogger("bess.agent")


class EdgeAgent:
    def __init__(self, config: AgentConfig, modbus: Any, mqtt_client: Any) -> None:
        self.config = config
        self.modbus = modbus
        self.mqtt = mqtt_client
        self._loop: asyncio.AbstractEventLoop | None = None
        self._modbus_lock = asyncio.Lock()

    # Telemetry ---------------------------------------------------------------

    async def poll_once(self) -> bool:
        """Read the telemetry block and publish it. Returns False on read failure."""
        try:
            async with self._modbus_lock:
                response = await self.modbus.read_holding_registers(
                    TELEMETRY_START, TELEMETRY_COUNT, slave=self.config.modbus_unit_id
                )
        except (ModbusException, OSError) as exc:
            log.warning("Modbus read failed: %s", exc)
            return False
        if response.isError():
            log.warning("Modbus read returned an error: %s", response)
            return False

        payload = build_telemetry(self.config.site_id, decode_block(response.registers))
        self.mqtt.publish(self.config.telemetry_topic, payload, qos=1)
        return True

    # Commands ----------------------------------------------------------------

    async def handle_command(self, raw: bytes) -> None:
        try:
            command = parse_command(raw, self.config.max_power_kw)
        except CommandError as exc:
            log.warning("Rejected command: %s", exc)
            self.mqtt.publish(self.config.ack_topic, build_ack(None, False, str(exc)), qos=1)
            return

        try:
            async with self._modbus_lock:
                response = await self.modbus.write_register(
                    SETPOINT_REGISTER.address,
                    encode(command.setpoint_kw, SETPOINT_REGISTER),
                    slave=self.config.modbus_unit_id,
                )
            accepted = not response.isError()
            reason = "" if accepted else str(response)
        except (ModbusException, OSError) as exc:
            accepted, reason = False, f"modbus write failed: {exc}"

        log.info("Command %s setpoint=%.1fkW accepted=%s", command.command_id, command.setpoint_kw, accepted)
        self.mqtt.publish(self.config.ack_topic, build_ack(command.command_id, accepted, reason), qos=1)

    # paho-mqtt callbacks (run on paho's network thread) -----------------------

    def on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code.is_failure:
            log.error("MQTT connection refused: %s", reason_code)
            return
        log.info("MQTT connected, subscribing to %s", self.config.command_topic)
        client.subscribe(self.config.command_topic, qos=1)

    def on_disconnect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        log.warning("MQTT disconnected (%s), paho will reconnect", reason_code)

    def on_message(self, client: Any, userdata: Any, message: Any) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.handle_command(message.payload), self._loop)

    # Main loop -----------------------------------------------------------------

    async def run(self, stop: asyncio.Event) -> None:
        self._loop = asyncio.get_running_loop()
        await self.modbus.connect()
        self.mqtt.connect_async(self.config.mqtt_host, self.config.mqtt_port, keepalive=60)
        self.mqtt.loop_start()
        try:
            while not stop.is_set():
                await self.poll_once()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self.config.publish_interval_s)
        finally:
            self.mqtt.disconnect()
            self.mqtt.loop_stop()
            self.modbus.close()


def build_mqtt_client(config: AgentConfig) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=config.client_id,
        protocol=mqtt.MQTTv311,
    )
    client.max_queued_messages_set(config.max_queued_messages)
    client.enable_logger(logging.getLogger("bess.mqtt"))
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    if config.mqtt_tls:
        client.tls_set(
            ca_certs=config.mqtt_ca_path,
            certfile=config.mqtt_cert_path,
            keyfile=config.mqtt_key_path,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
    return client


async def _main() -> None:
    config = AgentConfig.from_env()
    modbus = AsyncModbusTcpClient(
        config.modbus_host, port=config.modbus_port, reconnect_delay=1, reconnect_delay_max=30
    )
    client = build_mqtt_client(config)
    agent = EdgeAgent(config, modbus, client)
    client.on_connect = agent.on_connect
    client.on_disconnect = agent.on_disconnect
    client.on_message = agent.on_message

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    log.info(
        "Agent started for site %s (modbus %s:%d, mqtt %s:%d tls=%s)",
        config.site_id,
        config.modbus_host,
        config.modbus_port,
        config.mqtt_host,
        config.mqtt_port,
        config.mqtt_tls,
    )
    await agent.run(stop)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(_main())


if __name__ == "__main__":
    main()
