"""Edge agent configuration, read from environment variables (12-factor style)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AgentConfig:
    site_id: str
    modbus_host: str = "localhost"
    modbus_port: int = 5020
    modbus_unit_id: int = 1
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_tls: bool = False
    mqtt_ca_path: str | None = None
    mqtt_cert_path: str | None = None
    mqtt_key_path: str | None = None
    publish_interval_s: float = 5.0
    max_power_kw: float = 1000.0
    max_queued_messages: int = 10_000

    @property
    def client_id(self) -> str:
        # AWS IoT policies pin the client ID to the thing name, which is the site ID.
        return self.site_id

    @property
    def telemetry_topic(self) -> str:
        return f"bess/{self.site_id}/telemetry"

    @property
    def command_topic(self) -> str:
        return f"bess/{self.site_id}/commands"

    @property
    def ack_topic(self) -> str:
        return f"bess/{self.site_id}/commands/ack"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> AgentConfig:
        site_id = env.get("SITE_ID")
        if not site_id:
            raise ValueError("SITE_ID is required")
        config = cls(
            site_id=site_id,
            modbus_host=env.get("MODBUS_HOST", "localhost"),
            modbus_port=int(env.get("MODBUS_PORT", "5020")),
            modbus_unit_id=int(env.get("MODBUS_UNIT_ID", "1")),
            mqtt_host=env.get("MQTT_HOST", "localhost"),
            mqtt_port=int(env.get("MQTT_PORT", "1883")),
            mqtt_tls=_bool(env.get("MQTT_TLS", "false")),
            mqtt_ca_path=env.get("MQTT_CA_PATH"),
            mqtt_cert_path=env.get("MQTT_CERT_PATH"),
            mqtt_key_path=env.get("MQTT_KEY_PATH"),
            publish_interval_s=float(env.get("PUBLISH_INTERVAL_S", "5")),
            max_power_kw=float(env.get("MAX_POWER_KW", "1000")),
            max_queued_messages=int(env.get("MAX_QUEUED_MESSAGES", "10000")),
        )
        if config.mqtt_tls and not all((config.mqtt_ca_path, config.mqtt_cert_path, config.mqtt_key_path)):
            raise ValueError("MQTT_TLS=true requires MQTT_CA_PATH, MQTT_CERT_PATH and MQTT_KEY_PATH")
        return config
