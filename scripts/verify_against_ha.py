"""Verify SMA Energy Bridge source values against live Home Assistant sensors.

Reads the meter through the configured Modbus TCP proxy with the exact code
path the app uses (``read_sample``) and, at the same moment, the corresponding
Home Assistant reference sensors via the REST API. Reports a per-sample table
and a PASS/FAIL summary for counters and power sign agreement.

Only standard-library modules are used, matching the app itself.

Example:

    HA_URL=http://ha.local:8123 HA_TOKEN=... python scripts/verify_against_ha.py \
        --options live_check_options.json \
        --ha-power-entity sensor.meter_1_leistung \
        --ha-import-entity sensor.meter_1_bezogene_energie \
        --ha-export-entity sensor.meter_1_eingespeiste_energie

HA credentials come from the environment (HA_URL, HA_TOKEN), never from files
that could be committed by accident. Exit code 0 means every check passed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sma_energy_bridge"))

from main import read_sample  # noqa: E402


def ha_state(base_url: str, token: str, entity_id: str) -> dict:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--options", type=Path, required=True,
                        help="App options JSON with the live proxy settings")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--ha-power-entity", default="sensor.meter_1_leistung")
    parser.add_argument("--ha-import-entity", default="sensor.meter_1_bezogene_energie")
    parser.add_argument("--ha-export-entity", default="sensor.meter_1_eingespeiste_energie")
    parser.add_argument("--ha-power-sign", choices=("import_positive", "export_positive"),
                        default="export_positive",
                        help="Sign convention of the HA reference power sensor")
    parser.add_argument("--counter-tolerance-kwh", type=float, default=0.05,
                        help="Allowed counter drift between both reads")
    parser.add_argument("--power-tolerance-w", type=float, default=500.0,
                        help="Allowed power delta caused by sampling skew")
    args = parser.parse_args()

    base_url = os.environ.get("HA_URL")
    token = os.environ.get("HA_TOKEN")
    if not base_url or not token:
        print("Set HA_URL and HA_TOKEN in the environment", file=sys.stderr)
        return 2

    options = json.loads(args.options.read_text(encoding="utf-8"))
    print(f"bridge source : {options['modbus_host']}:{options['modbus_port']} "
          f"unit={options['modbus_unit_id']} base={options['meter_model_base']} "
          f"power_sign={options['power_sign']} swap_counters={options.get('swap_counters', False)}")
    print(f"reference     : {base_url} ({args.ha_power_entity}, {args.ha_import_entity}, "
          f"{args.ha_export_entity}, ha power sign={args.ha_power_sign})")
    print("normalized    : bridge grid power + = import (app log convention)\n")

    failures: list[str] = []
    worst_counter = 0.0
    worst_power = 0.0
    for index in range(args.samples):
        try:
            (power, imported, exported), _ = read_sample(options)
        except Exception as exc:  # noqa: BLE001 - report and keep sampling
            print(f"[{index + 1}/{args.samples}] bridge read failed: {exc}")
            failures.append(f"bridge read: {exc}")
            time.sleep(args.interval)
            continue
        try:
            ha_power = float(ha_state(base_url, token, args.ha_power_entity)["state"])
            ha_import = float(ha_state(base_url, token, args.ha_import_entity)["state"])
            ha_export = float(ha_state(base_url, token, args.ha_export_entity)["state"])
        except (urllib.error.URLError, ValueError, KeyError) as exc:
            print(f"[{index + 1}/{args.samples}] HA read failed: {exc}")
            failures.append(f"HA read: {exc}")
            time.sleep(args.interval)
            continue

        ha_power_norm = ha_power if args.ha_power_sign == "import_positive" else -ha_power
        d_import = abs(imported - ha_import)
        d_export = abs(exported - ha_export)
        d_power = abs(power - ha_power_norm)
        worst_counter = max(worst_counter, d_import, d_export)
        worst_power = max(worst_power, d_power)
        verdict = "ok"
        if d_import > args.counter_tolerance_kwh or d_export > args.counter_tolerance_kwh:
            failures.append(f"sample {index + 1}: counter drift import {d_import:.3f} / "
                            f"export {d_export:.3f} kWh")
            verdict = "COUNTER MISMATCH"
        elif d_power > args.power_tolerance_w:
            failures.append(f"sample {index + 1}: power delta {d_power:.1f} W "
                            f"(bridge {power:+.1f} vs HA {ha_power_norm:+.1f})")
            verdict = "POWER MISMATCH"
        sign_note = "import" if power >= 0 else "export"
        print(f"[{index + 1}/{args.samples}] bridge {power:+9.1f} W ({sign_note:6s}) "
              f"imp {imported:12.3f} exp {exported:12.3f} kWh | "
              f"HA {ha_power_norm:+9.1f} W imp {ha_import:12.3f} exp {ha_export:12.3f} kWh | "
              f"dP {d_power:7.1f} W dImp {d_import:.3f} dExp {d_export:.3f} -> {verdict}")
        if index + 1 < args.samples:
            time.sleep(args.interval)

    print(f"\nworst counter drift: {worst_counter:.4f} kWh "
          f"(tolerance {args.counter_tolerance_kwh})")
    print(f"worst power delta  : {worst_power:.1f} W (tolerance {args.power_tolerance_w})")
    if failures:
        print("\nFAILURES:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("\nPASS: source values match the live Home Assistant reference")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
