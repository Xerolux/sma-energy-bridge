"""SolarEdge SunSpec meter -> SMA Energy Meter Speedwire transmitter.

Experimental display-only Home Assistant app. The SolarEdge data source is a
read-only Modbus TCP proxy. No values are written to Modbus or the SMA inverter.
Compatibility with an actual SMA inverter must be verified on site.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import socket
import struct
import time
from pathlib import Path

LOG = logging.getLogger("sma_energy_bridge")
MULTICAST_GROUP = "239.12.255.254"
MULTICAST_PORT = 9522
# These are base-0 Modbus register addresses in SolarEdge's SunSpec technical note.
DEFAULT_METER_BASE = 40188
METER_TYPES = {201, 202, 203, 204}


class ModbusError(Exception):
    """Transport, protocol or Modbus exception."""


def _exact(sock: socket.socket, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        part = sock.recv(count - len(data))
        if not part:
            raise ModbusError("Modbus connection closed mid-response")
        data.extend(part)
    return bytes(data)


def read_holding_registers(host: str, port: int, unit_id: int, start: int,
                           count: int, timeout: float = 3.0) -> list[int]:
    """Read function 03 only, through an existing Modbus TCP proxy."""
    if not host or host == "REPLACE_ME" or not 1 <= port <= 65535:
        raise ValueError("Configure modbus_host and modbus_port")
    if not 0 <= unit_id <= 247 or not 0 <= start <= 65535:
        raise ValueError("Invalid Modbus unit ID or address")
    if not 1 <= count <= 125 or start + count > 65536:
        raise ValueError("Invalid register count")
    txid = (time.monotonic_ns() >> 10) & 0xFFFF
    pdu = struct.pack(">BHH", 3, start, count)
    request = struct.pack(">HHHB", txid, 0, 1 + len(pdu), unit_id) + pdu
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(request)
        header = _exact(sock, 7)
        got_txid, protocol, length, got_unit = struct.unpack(">HHHB", header)
        if (got_txid, protocol, got_unit) != (txid, 0, unit_id):
            raise ModbusError("Unexpected Modbus transaction/protocol/unit ID")
        if length < 3 or length > 253:
            raise ModbusError("Invalid Modbus PDU length")
        pdu_reply = _exact(sock, length - 1)
    if pdu_reply[0] == 0x83:
        raise ModbusError(f"Modbus exception {pdu_reply[1] if len(pdu_reply)>1 else '?'}")
    if pdu_reply[0] != 3 or len(pdu_reply) != 2 + count * 2 or pdu_reply[1] != count * 2:
        raise ModbusError("Unexpected holding-register response")
    return list(struct.unpack(">" + "H" * count, pdu_reply[2:]))


def signed16(n: int) -> int:
    return n - 0x10000 if n & 0x8000 else n


def _u32(hi: int, lo: int) -> int:
    return (hi << 16) | lo


def decode_meter_registers(registers: list[int]) -> tuple[float, float, float]:
    """Return (grid W: positive import, imported kWh, exported kWh).

    SolarEdge SunSpec meter model, relative to C_SunSpec_DID at base-0 40188:
      +18 M_AC_Power (int16), +22 Power SF
      +38 M_Exported (uint32), +46 M_Imported (uint32), +54 Energy SF
    """
    if len(registers) < 55:
        raise ValueError("Incomplete meter register block")
    if registers[0] not in METER_TYPES or not 55 <= registers[1] <= 125:
        raise ValueError(f"No SunSpec meter 201..204 at this address: {registers[:2]}")
    p_sf = signed16(registers[22])
    e_sf = signed16(registers[54])
    if not -6 <= p_sf <= 6 or not -6 <= e_sf <= 6:
        raise ValueError(f"Invalid SunSpec scale factor: power={p_sf}, energy={e_sf}")
    if registers[18] == 0x8000:
        raise ValueError("SunSpec power unavailable")
    raw_import = _u32(registers[46], registers[47])
    raw_export = _u32(registers[38], registers[39])
    if raw_import == 0xFFFFFFFF or raw_export == 0xFFFFFFFF:
        raise ValueError("SunSpec counter unavailable")
    power_w = signed16(registers[18]) * (10 ** p_sf)
    import_kwh = raw_import * (10 ** e_sf) / 1000.0
    export_kwh = raw_export * (10 ** e_sf) / 1000.0
    if not all(map(math.isfinite, (power_w, import_kwh, export_kwh))):
        raise ValueError("Non-finite source measurement")
    return power_w, import_kwh, export_kwh


def fetch_meter(options: dict) -> tuple[float, float, float]:
    block = read_holding_registers(
        options["modbus_host"], options["modbus_port"], options["modbus_unit_id"],
        options["meter_model_base"], 55,
    )
    power, imported, exported = decode_meter_registers(block)
    if options["power_sign"] == "export_positive":
        power = -power
    if options.get("swap_counters", False):
        imported, exported = exported, imported
    if abs(power) > options["max_abs_power_w"]:
        raise ValueError(f"Grid power {power} W exceeds safety sanity limit")
    return power, imported, exported


def obis(index: int, kind: int, amount: int) -> bytes:
    """kind 4 = instantaneous in 0.1 W; kind 8 = energy in Ws."""
    maxval = 0xFFFFFFFF if kind == 4 else 0xFFFFFFFFFFFFFFFF
    if kind not in (4, 8) or not 0 <= amount <= maxval:
        raise ValueError("Invalid OBIS value")
    return struct.pack(">BBBB", 1, index, kind, 0) + struct.pack(
        ">I" if kind == 4 else ">Q", amount
    )


def build_frame(serial: int, susy: int, power_w: float,
                imported_kwh: float, exported_kwh: float, tick_ms: int) -> bytes:
    """SMA Energy Meter Speedwire packet, 4 total power/energy OBIS points."""
    if not 1 <= serial <= 0xFFFFFFFF or not 0 <= susy <= 0xFFFF:
        raise ValueError("Invalid SMA meter address")
    if not all(map(math.isfinite, (power_w, imported_kwh, exported_kwh))):
        raise ValueError("Invalid source values")
    if imported_kwh < 0 or exported_kwh < 0:
        raise ValueError("Negative energy counter")
    payload = b"".join((
        obis(1, 4, round(max(power_w, 0.0) * 10)),
        obis(1, 8, round(imported_kwh * 3_600_000)),
        obis(2, 4, round(max(-power_w, 0.0) * 10)),
        obis(2, 8, round(exported_kwh * 3_600_000)),
    ))
    payload = struct.pack(">HI", susy, serial) + struct.pack(">I", tick_ms & 0xFFFFFFFF) + payload
    header = b"SMA\x00" + struct.pack(">HHIHHH", 4, 0x02A0, 1, 2 + len(payload), 0x0010, 0x6069)
    return header + payload + b"\x00\x00\x00\x00"


def validate(options: dict) -> None:
    if options["power_sign"] not in ("import_positive", "export_positive"):
        raise ValueError("Unsupported sign convention")
    for key, lo, hi in (
        ("poll_interval_seconds", 2, 120),
        ("transmit_interval_seconds", 1, 30),
        ("stale_after_seconds", 3, 300),
        ("max_abs_power_w", 1000, 1000000),
    ):
        if not lo <= options[key] <= hi:
            raise ValueError(f"{key} must be in {lo}..{hi}")
    if options["stale_after_seconds"] <= options["poll_interval_seconds"]:
        raise ValueError("stale_after_seconds must exceed poll_interval_seconds")
    if not 0 <= options["modbus_unit_id"] <= 247:
        raise ValueError("Invalid modbus_unit_id")
    if not 1 <= options["meter_serial"] <= 0xFFFFFFFF:
        raise ValueError("Invalid meter_serial")
    if not 0 <= options["susy_id"] <= 0xFFFF:
        raise ValueError("Invalid susy_id")
    if not 0 <= options["meter_model_base"] <= 65536 - 55:
        raise ValueError("Invalid meter_model_base")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--options", type=Path, default=Path("/data/options.json"))
    parser.add_argument("--check", action="store_true",
                        help="Read one sample and validate the frame locally")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = json.loads(args.options.read_text(encoding="utf-8"))
    validate(config)
    if args.check:
        power, imported, exported = fetch_meter(config)
        frame = build_frame(config["meter_serial"], config["susy_id"],
                            power, imported, exported, 0)
        print(json.dumps({"grid_power_w": power, "import_kwh": imported,
                          "export_kwh": exported, "speedwire_bytes": len(frame)}))
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    interface = config.get("multicast_interface", "")
    if interface:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface))
    transmit = config["transmit_enabled"]
    LOG.info("START source=Modbus TCP proxy (%s:%s, unit=%s, model_base=%s); TX=%s; serial=%s",
             config["modbus_host"], config["modbus_port"], config["modbus_unit_id"],
             config["meter_model_base"], "ENABLED" if transmit else "DRY-RUN", config["meter_serial"])
    last_good: tuple[float, float, float] | None = None
    last_good_at: float | None = None
    last_counters: tuple[float, float] | None = None
    next_poll = 0.0
    next_log = 0.0
    while True:
        now = time.monotonic()
        if now >= next_poll:
            next_poll = now + config["poll_interval_seconds"]
            try:
                new = fetch_meter(config)
                if last_counters is not None and (new[1] + 0.0001 < last_counters[0] or
                                                  new[2] + 0.0001 < last_counters[1]):
                    LOG.error("Counter decreased (reset/wrap); stopping for manual review")
                    return
                last_good = new
                last_good_at = time.monotonic()
                last_counters = (new[1], new[2])
            except (ModbusError, ValueError, OSError, KeyError, OverflowError) as exc:
                LOG.warning("Source read rejected: %s", exc)
        now = time.monotonic()
        fresh = (last_good is not None and last_good_at is not None and
                 now - last_good_at <= config["stale_after_seconds"])
        if fresh:
            assert last_good is not None
            try:
                frame = build_frame(config["meter_serial"], config["susy_id"],
                                    *last_good, int(now * 1000))
                if transmit:
                    sock.sendto(frame, (MULTICAST_GROUP, MULTICAST_PORT))
                if now >= next_log:
                    power, inc, out = last_good
                    LOG.info("%s grid=%+.1f W (+=import), import=%.3f kWh, export=%.3f kWh, bytes=%d",
                             "SENT" if transmit else "DRY-RUN", power, inc, out, len(frame))
                    next_log = now + 30
            except (ValueError, OSError, OverflowError) as exc:
                LOG.warning("Frame not transmitted: %s", exc)
        elif now >= next_log:
            LOG.warning("No fresh meter data: nothing transmitted")
            next_log = now + 30
        time.sleep(config["transmit_interval_seconds"])


if __name__ == "__main__":
    main()
