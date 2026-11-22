"""Modbus TCP grid meter -> SMA Energy Meter Speedwire transmitter.

Beta Home Assistant app for displaying meter data from a read-only Modbus TCP
source. No settings are written to the meter or the SMA inverter.
Compatibility with an actual SMA inverter must be verified on site.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import socket
import struct
import time
from ipaddress import IPv4Address
from pathlib import Path

LOG = logging.getLogger("sma_energy_bridge")
MULTICAST_GROUP = "239.12.255.254"
MULTICAST_PORT = 9522
# These are base-0 Modbus register addresses in SolarEdge's SunSpec technical note.
DEFAULT_METER_BASE = 40188
METER_TYPES = {201, 202, 203, 204}
REGISTER_FORMATS = {
    "int16": "h", "uint16": "H", "int32": "i", "uint32": "I",
    "float32": "f", "int64": "q", "uint64": "Q", "float64": "d",
}
REQUIRED_METRICS = {"power", "import_wh", "export_wh"}
PHASE_METRICS = REQUIRED_METRICS | {
    "reactive_power", "apparent_power", "power_factor", "current", "voltage",
    "reactive_import_varh", "reactive_export_varh", "apparent_import_vah", "apparent_export_vah",
}
METRICS = ((PHASE_METRICS - {"current", "voltage"}) | {"frequency"}
           | {f"{metric}_l{phase}" for metric in PHASE_METRICS for phase in (1, 2, 3)})
RegisterMapping = tuple[str, int, str, float, int, bool]
MeterValues = tuple[float, float, float]
MeterDetails = list[int] | dict[str, float] | None


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
                           count: int, timeout: float = 3.0, *,
                           function: int = 3) -> list[int]:
    """Read Modbus TCP registers. Only function 03 and 04 are supported."""
    if not host or host == "REPLACE_ME" or not 1 <= port <= 65535:
        raise ValueError("Configure modbus_host and modbus_port")
    if not 0 <= unit_id <= 247 or not 0 <= start <= 65535:
        raise ValueError("Invalid Modbus unit ID or address")
    if not 1 <= count <= 125 or start + count > 65536:
        raise ValueError("Invalid register count")
    if function not in (3, 4):
        raise ValueError("Only Modbus functions 03 and 04 are supported")
    txid = (time.monotonic_ns() >> 10) & 0xFFFF
    pdu = struct.pack(">BHH", function, start, count)
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
    if pdu_reply[0] == (function | 0x80):
        raise ModbusError(f"Modbus exception {pdu_reply[1] if len(pdu_reply)>1 else '?'}")
    if pdu_reply[0] != function or len(pdu_reply) != 2 + count * 2 or pdu_reply[1] != count * 2:
        raise ModbusError("Unexpected register response")
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
    values, _ = fetch_meter_sample(options)
    return values


def fetch_meter_sample(options: dict) -> tuple[tuple[float, float, float], list[int]]:
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
    return (power, imported, exported), block


def custom_mappings(config: dict) -> list[RegisterMapping]:
    """Parse and validate the register list from the Home Assistant options."""
    mappings = []
    seen = set()
    for line in config.get("custom_registers", []):
        try:
            metric, raw_address, data_type, raw_factor = map(str.strip, line.split(","))
            swapped = data_type.endswith("_swapped")
            code = REGISTER_FORMATS[data_type.removesuffix("_swapped")]
            count = struct.calcsize(">" + code) // 2
            address, factor = int(raw_address), float(raw_factor)
            if (metric not in METRICS or metric in seen or not 0 <= address <= 65536 - count
                    or not math.isfinite(factor) or factor == 0 or (swapped and count == 1)):
                raise ValueError(f"Invalid or duplicate metric: {metric}")
        except (ValueError, KeyError) as exc:
            raise ValueError(f"Invalid custom register mapping: {line!r}") from exc
        seen.add(metric)
        mappings.append((metric, address, code, factor, count, swapped))
    if missing := REQUIRED_METRICS - seen:
        raise ValueError(f"Missing custom metrics: {', '.join(sorted(missing))}")
    for phase in ("_l1", "_l2", "_l3"):
        if "apparent_power" + phase in seen and "power" + phase not in seen:
            raise ValueError(f"apparent_power{phase} needs power{phase} for direction")
    return sorted(mappings, key=lambda item: item[1])


def read_custom_sample(config: dict) -> tuple[MeterValues, dict[str, float]]:
    mappings = custom_mappings(config)
    blocks: list[tuple[int, int]] = []
    for _, address, _, _, count, _ in mappings:
        if (blocks and address <= blocks[-1][1]
                and address + count - blocks[-1][0] <= 125):
            start, end = blocks[-1]
            blocks[-1] = (start, max(end, address + count))
        else:
            blocks.append((address, address + count))
    registers = {}
    for start, end in blocks:
        block = read_holding_registers(
            config["modbus_host"], config["modbus_port"], config["modbus_unit_id"],
            start, end - start, function=config.get("custom_modbus_function", 3),
        )
        registers.update(enumerate(block, start))
    values = {}
    for metric, address, code, factor, count, swapped in mappings:
        words = [registers[index] for index in range(address, address + count)]
        if swapped:
            words.reverse()
        raw, = struct.unpack(">" + code, struct.pack(">" + "H" * count, *words))
        value = raw * factor
        base = metric.rsplit("_", 1)[0] if metric.endswith(("_l1", "_l2", "_l3")) else metric
        if (not math.isfinite(value)
                or (base == "power" and abs(value) > config["max_abs_power_w"])
                or (base == "power_factor" and abs(value) > 100)
                or (base not in {"power", "reactive_power", "power_factor"} and value < 0)):
            raise ValueError(f"Invalid measurement for custom metric {metric}")
        values[metric] = value
    sign = -1 if config["power_sign"] == "export_positive" else 1
    imported, exported = values["import_wh"], values["export_wh"]
    if config.get("swap_counters", False):
        imported, exported = exported, imported
    return (sign * values["power"], imported / 1000, exported / 1000), values


def obis(index: int, kind: int, amount: int, channel: int = 1) -> bytes:
    """kind 4 = instantaneous in 0.1 W; kind 8 = energy in Ws."""
    maxval = 0xFFFFFFFF if kind == 4 else 0xFFFFFFFFFFFFFFFF
    if kind not in (4, 8) or not 0 <= amount <= maxval:
        raise ValueError("Invalid OBIS value")
    return struct.pack(">BBBB", channel, index, kind, 0) + struct.pack(
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
    return wrap_frame(serial, susy, tick_ms, payload)


def wrap_frame(serial: int, susy: int, tick_ms: int, payload: bytes) -> bytes:
    payload = struct.pack(">HII", susy, serial, tick_ms & 0xFFFFFFFF) + payload
    header = b"SMA\x00" + struct.pack(">HHIHHH", 4, 0x02A0, 1, 2 + len(payload), 0x0010, 0x6069)
    return header + payload + b"\x00\x00\x00\x00"


def scaled_meter_value(block: list[int], index: int, scale_index: int) -> float | None:
    """Decode an optional SunSpec int16 measurement and its scale factor."""
    scale = signed16(block[scale_index])
    raw = block[index]
    if raw == 0x8000 or not -6 <= scale <= 6:
        return None
    return signed16(raw) * 10 ** scale


def build_emeter20(config: dict, values: tuple[float, float, float],
                   block: list[int], tick_ms: int) -> bytes:
    """Build the EMETER-20 profile verified with the Sunny Tripower."""
    power, imported, exported = values
    amounts = {
        (1, 4): max(power, 0) * 10,
        (2, 4): max(-power, 0) * 10,
        (1, 8): imported * 3_600_000,
        (2, 8): exported * 3_600_000,
    }
    frequency = scaled_meter_value(block, 16, 17)
    if frequency is not None and frequency > 0:
        amounts[14, 4] = frequency * 1000
    sign = -1 if config["power_sign"] == "export_positive" else 1
    energy_scale = 10 ** signed16(block[54]) * 3600
    for point in range(4):
        offset = 20 * point
        phase_power = scaled_meter_value(block, 18 + point, 22)
        watts = power if point == 0 else (phase_power * sign if phase_power is not None else None)
        reactive = scaled_meter_value(block, 28 + point, 32)
        apparent = scaled_meter_value(block, 23 + point, 27)
        factor = scaled_meter_value(block, 33 + point, 37)
        if reactive is not None:
            reactive *= sign
            amounts[offset + (3 if reactive >= 0 else 4), 4] = abs(reactive) * 10
        if apparent is not None and watts is not None:
            amounts[offset + (9 if watts >= 0 else 10), 4] = abs(apparent) * 10
        if factor is not None and abs(factor) <= 100:
            amounts[offset + 13, 4] = abs(factor) * 10  # Percent to per mille.
        if point == 0:
            continue
        current = scaled_meter_value(block, 2 + point, 6)
        voltage = scaled_meter_value(block, 7 + point, 15)  # Line to neutral.
        if current is not None and current >= 0:
            amounts[offset + 11, 4] = current * 1000
        if voltage is not None and voltage >= 0:
            amounts[offset + 12, 4] = voltage * 1000
        if watts is not None:
            amounts[offset + 1, 4] = max(watts, 0) * 10
            amounts[offset + 2, 4] = max(-watts, 0) * 10
        for direction, base in enumerate((46, 38), 1):
            index = base + 2 * point
            raw = _u32(*block[index:index + 2])
            if raw != 0xFFFFFFFF:
                counter = 3 - direction if config.get("swap_counters", False) else direction
                amounts[offset + counter, 8] = raw * energy_scale

    return pack_emeter20(config["meter_serial"], tick_ms, amounts)


def pack_emeter20(serial: int, tick_ms: int, amounts: dict[tuple[int, int], float]) -> bytes:
    fields = []
    for offset in (0, 20, 40, 60):
        for index in (1, 2, 3, 4, 9, 10):
            for kind in (4, 8):
                fields.append((offset + index, kind))
        fields.extend((offset + index, 4) for index in ((11, 12, 13) if offset else (13, 14)))
    payload = b"".join(obis(index, kind, int(amounts.get((index, kind), 0)), 0)
                       for index, kind in fields)
    payload += bytes.fromhex("90000000 02030452")
    return wrap_frame(serial, 349, tick_ms, payload)


def build_custom_emeter20(config: dict, values: MeterValues,
                         details: dict[str, float], tick_ms: int) -> bytes:
    power, imported, exported = values
    amounts = {
        (1, 8): imported * 3_600_000, (2, 8): exported * 3_600_000,
        (14, 4): details.get("frequency", 0) * 1000,
    }
    sign = -1 if config["power_sign"] == "export_positive" else 1
    counters = (("export_wh", "import_wh") if config.get("swap_counters", False)
                else ("import_wh", "export_wh"))
    for phase in range(4):
        offset = 20 * phase
        suffix = f"_l{phase}" if phase else ""
        watts = details.get("power" + suffix, 0) * sign if phase else power
        reactive = details.get("reactive_power" + suffix, 0) * sign
        amounts[offset + (1 if watts >= 0 else 2), 4] = abs(watts) * 10
        amounts[offset + (3 if reactive >= 0 else 4), 4] = abs(reactive) * 10
        if "power" + suffix in details:
            apparent = details.get("apparent_power" + suffix, 0)
            amounts[offset + (9 if watts >= 0 else 10), 4] = apparent * 10
        amounts[offset + 13, 4] = abs(details.get("power_factor" + suffix, 0)) * 10
        for index, metric in ((3, "reactive_import_varh"), (4, "reactive_export_varh"),
                              (9, "apparent_import_vah"), (10, "apparent_export_vah")):
            amounts[offset + index, 8] = details.get(metric + suffix, 0) * 3600
        if phase:
            for index, metric in enumerate(counters, 1):
                amounts[offset + index, 8] = details.get(metric + suffix, 0) * 3600
            amounts[offset + 11, 4] = details.get("current" + suffix, 0) * 1000
            amounts[offset + 12, 4] = details.get("voltage" + suffix, 0) * 1000
    return pack_emeter20(config["meter_serial"], tick_ms, amounts)


def read_sample(config: dict) -> tuple[MeterValues, MeterDetails]:
    if config.get("source_profile") == "custom_modbus":
        values, details = read_custom_sample(config)
        return values, details if config.get("frame_profile") == "emeter20" else None
    if config.get("frame_profile") == "emeter20":
        return fetch_meter_sample(config)
    return fetch_meter(config), None


def encode_sample(config: dict, values: MeterValues, block: MeterDetails, tick_ms: int) -> bytes:
    if isinstance(block, dict):
        return build_custom_emeter20(config, values, block, tick_ms)
    if block is not None:
        return build_emeter20(config, values, block, tick_ms)
    return build_frame(config["meter_serial"], config["susy_id"], *values, tick_ms)


def validate(options: dict) -> None:
    if options.get("frame_profile", "compact") not in ("compact", "emeter20"):
        raise ValueError("Unsupported frame_profile")
    if unicast_host := options.get("unicast_host"):
        destination = IPv4Address(unicast_host)
        if destination.is_multicast or destination.is_unspecified or int(destination) == 0xFFFFFFFF:
            raise ValueError("unicast_host must be a unicast IPv4 address")
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
    match options.get("source_profile", "solaredge_sunspec"):
        case "solaredge_sunspec":
            if not 0 <= options["meter_model_base"] <= 65536 - 55:
                raise ValueError("Invalid meter_model_base")
        case "custom_modbus":
            if options.get("custom_modbus_function", 3) not in (3, 4):
                raise ValueError("Custom Modbus function must be 3 or 4")
            custom_mappings(options)
        case _:
            raise ValueError("Unsupported meter source profile")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--options", type=Path, default=Path("/data/options.json"))
    parser.add_argument("--check", action="store_true",
                        help="Read one sample and validate the frame locally")
    args = parser.parse_args()
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        log_level = "INFO"
    logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s %(message)s")
    config = json.loads(args.options.read_text(encoding="utf-8"))
    validate(config)
    if args.check:
        values, block = read_sample(config)
        power, imported, exported = values
        frame = encode_sample(config, values, block, 0)
        print(json.dumps({"grid_power_w": power, "import_kwh": imported,
                          "export_kwh": exported, "speedwire_bytes": len(frame)}))
        return
    transmit = config["transmit_enabled"]
    profile = config.get("frame_profile", "compact")
    unicast_host = config.get("unicast_host")
    destination = (unicast_host or MULTICAST_GROUP, MULTICAST_PORT)
    sock = None
    if transmit:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        interface = config.get("multicast_interface") or ""
        if not unicast_host:
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
            if interface:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                socket.inet_aton(interface))
        if profile == "emeter20" or unicast_host:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((interface, MULTICAST_PORT))
    LOG.info("START source=%s (%s:%s, unit=%s); "
             "TX=%s; serial=%s; profile=%s; destination=%s:%s",
             config.get("source_profile", "solaredge_sunspec"),
             config["modbus_host"], config["modbus_port"], config["modbus_unit_id"],
             "ENABLED" if transmit else "DRY-RUN",
             config["meter_serial"], profile, *destination)
    last_good: tuple[float, float, float] | None = None
    last_block: MeterDetails = None
    last_good_at: float | None = None
    last_counters: tuple[float, float] | None = None
    next_poll = 0.0
    next_log = 0.0
    while True:
        now = time.monotonic()
        if now >= next_poll:
            next_poll = now + config["poll_interval_seconds"]
            try:
                new, block = read_sample(config)
                if last_counters is not None and (new[1] + 0.0001 < last_counters[0] or
                                                  new[2] + 0.0001 < last_counters[1]):
                    LOG.error("Counter decreased (reset/wrap); stopping for manual review")
                    return
                last_good = new
                last_block = block
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
                tick = time.time() if last_block is not None else now
                frame = encode_sample(config, last_good, last_block, int(tick * 1000))
                if sock is not None:
                    sock.sendto(frame, destination)
                if now >= next_log:
                    power, inc, out = last_good
                    LOG.info("%s grid=%+.1f W (+=import), import=%.3f kWh, "
                             "export=%.3f kWh, bytes=%d",
                             "SENT" if transmit else "DRY-RUN", power, inc, out,
                             len(frame))
                    next_log = now + 30
            except (ValueError, OSError, OverflowError) as exc:
                LOG.warning("Frame not transmitted: %s", exc)
        elif now >= next_log:
            LOG.warning("No fresh meter data: nothing transmitted")
            next_log = now + 30
        time.sleep(config["transmit_interval_seconds"])


if __name__ == "__main__":
    main()
