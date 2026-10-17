"""Modbus TCP server exposing a simulated battery.

Run with:  bess-sim  (or  python -m bess_telemetry.simulator)
"""

from __future__ import annotations

import asyncio
import logging
import os

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer

from bess_telemetry.battery import BatteryModel
from bess_telemetry.registers import (
    SETPOINT_REGISTER,
    TELEMETRY_REGISTERS,
    TELEMETRY_START,
    decode,
    encode,
)

log = logging.getLogger("bess.simulator")

HOLDING_REGISTERS = 3  # Modbus function code used by the datastore API
REGISTER_SPACE = 32


def build_context() -> ModbusServerContext:
    block = ModbusSequentialDataBlock(0, [0] * REGISTER_SPACE)
    slave = ModbusSlaveContext(hr=block, zero_mode=True)
    return ModbusServerContext(slaves=slave, single=True)


def sync_registers(context: ModbusServerContext, battery: BatteryModel) -> None:
    """Pull the setpoint written by clients, then publish the battery state."""
    slave = context[0]
    raw_setpoint = slave.getValues(HOLDING_REGISTERS, SETPOINT_REGISTER.address, 1)[0]
    battery.set_setpoint(decode(raw_setpoint, SETPOINT_REGISTER))

    snapshot = battery.snapshot()
    raw = [encode(snapshot[reg.name], reg) for reg in TELEMETRY_REGISTERS]
    slave.setValues(HOLDING_REGISTERS, TELEMETRY_START, raw)


async def run_model(context: ModbusServerContext, battery: BatteryModel, dt_s: float) -> None:
    while True:
        sync_registers(context, battery)
        battery.step(dt_s)
        log.debug("soc=%.1f%% power=%.1fkW", battery.soc_pct, battery.power_kw)
        await asyncio.sleep(dt_s)


async def serve(host: str, port: int, dt_s: float) -> None:
    battery = BatteryModel(
        capacity_kwh=float(os.getenv("BESS_CAPACITY_KWH", "2000")),
        max_power_kw=float(os.getenv("BESS_MAX_POWER_KW", "1000")),
        soc_pct=float(os.getenv("BESS_INITIAL_SOC_PCT", "50")),
    )
    context = build_context()
    sync_registers(context, battery)
    model_task = asyncio.create_task(run_model(context, battery, dt_s))
    log.info("Modbus simulator listening on %s:%d", host, port)
    try:
        await StartAsyncTcpServer(context=context, address=(host, port))
    finally:
        model_task.cancel()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(
        serve(
            host=os.getenv("MODBUS_BIND_HOST", "0.0.0.0"),
            port=int(os.getenv("MODBUS_PORT", "5020")),
            dt_s=float(os.getenv("SIM_STEP_S", "1")),
        )
    )


if __name__ == "__main__":
    main()
