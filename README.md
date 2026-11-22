# SMA Energy Bridge (Beta)

[![Tests](https://github.com/Xerolux/sma-energy-bridge/actions/workflows/tests.yaml/badge.svg)](https://github.com/Xerolux/sma-energy-bridge/actions/workflows/tests.yaml)

[Website](https://xerolux.github.io/sma-energy-bridge/) · [Deutsch](https://xerolux.github.io/sma-energy-bridge/de/) · [Wiki](https://github.com/Xerolux/sma-energy-bridge/wiki) · [Sponsor](https://github.com/sponsors/Xerolux)

Read a grid meter over Modbus TCP and forward its measurements as SMA Speedwire Energy Meter telegrams. Choose the built-in **SolarEdge SunSpec** profile or [configure a custom Modbus register map](https://xerolux.github.io/sma-energy-bridge/profiles/). The [German design document](KONZEPT_UND_UMSETZUNG.md) describes the original SolarEdge implementation.

⚠️ **Beta, display/test only.** Manual EMETER-20 assignment and live grid readings were verified on a `STP8.0-3AV-40`. Do not use for mandatory export control. The data source must be the complete *grid connection point meter*, not only inverter PV power.

## Supported architectures / Unterstützte Architekturen

| Home Assistant | English | Deutsch |
|---|---|---|
| `amd64` | 64-bit Intel and AMD systems | 64-Bit-Systeme mit Intel- oder AMD-Prozessor |
| `aarch64` | 64-bit ARM systems, e.g. Raspberry Pi 4 or 5 with 64-bit Home Assistant OS | 64-Bit-ARM-Systeme, z. B. Raspberry Pi 4 oder 5 mit 64-Bit-Home-Assistant-OS |

## Configuration

Configure the existing proxy address and port in the Home Assistant app settings. `meter_model_base: 40188` addresses SolarEdge SunSpec Meter 1 (base-0); verify DID 201–204. `transmit_enabled: false` is the default **dry-run** mode.

| Key | Example | Meaning |
|---|---|---|
| `source_profile` | `solaredge_sunspec` | built-in SolarEdge decoding or `custom_modbus` |
| `modbus_host` | `192.168.x.x` | existing TCP proxy hostname/IP |
| `modbus_port` | `502` | proxy listening port |
| `modbus_unit_id` | `1` | SolarEdge unit ID behind proxy |
| `meter_model_base` | `40188` | base-0 address of meter SunSpec DID |
| `power_sign` | `export_positive` | raw register sign convention. Use this when negative power accompanies rising import energy |
| `swap_counters` | `false` | swap imported/exported energy values if meter orientation requires |
| `meter_serial` | `900000001` | unique, simulated meter ID |
| `susy_id` | `270` | SMA Energy Meter SUSy ID |
| `transmit_enabled` | `false` | never emit multicast until source values validated |

With more than one NIC, set `multicast_interface` to the **local IPv4 address** of the NIC facing the SMA, or multicast might leave via the wrong network.

## Repository use

Add [the Xerolux repository](https://github.com/Xerolux/sma-energy-bridge) under **Settings → Apps → Install app → Repositories**, then install SMA Energy Bridge. Configure the proxy and start the app with transmission disabled. In the app log, positive grid power means import. Compare it and both lifetime counters against the reference meter. Check the existing `power_sign` explicitly after upgrading from 0.2.0.

For a one-shot check outside Supervisor, save the options from `sma_energy_bridge/config.yaml` as a JSON object with your proxy host and run:

```bash
python sma_energy_bridge/main.py --options options.json --check
```

The command reads one sample and prints grid power, import and export in kWh, and the generated frame size. It does not open a Speedwire socket.

## Native Home Assistant Modbus

Use [the optional package](examples/home-assistant-modbus.yaml) if you want HA entities for the same meter. Enable [Home Assistant packages](https://www.home-assistant.io/docs/configuration/packages/), copy the package into your packages directory, and set `sma_bridge_modbus_host` in `secrets.yaml`. The example uses SolarEdge Meter 1, TCP port 502 and unit ID 1. Check for existing SolarEdge entities before enabling additional polling. Keep the raw entity IDs used by the templates and select the two kWh entities as grid consumption and return to grid in the Energy dashboard. The native package publishes HA entities. The app handles Speedwire transmission independently.

## Live verification

The source path was verified on 2026-11-22 against a live installation
(SolarEdge SE10K, SunSpec Meter 1 with DID 203, power scale factor −2, energy
scale factor −1, behind a ModBridge proxy, reference sensors from the
SolarEdge Modbus integration in Home Assistant 2026.11):

| Check | Result |
|---|---|
| Meter DID | 203 (validated 201..204) |
| Energy counters vs. reference | worst drift 0.001 kWh over 12/12 samples |
| Power sign (import direction) | matches reference (positive = import) |
| Power sign (export direction) | matches reference (negative = export) |
| Counter assignment | import/export not swapped (`swap_counters: false`) |

Reproduce or repeat this on your own installation with
[`scripts/verify_against_ha.py`](scripts/verify_against_ha.py). It samples the
meter through the proxy with the exact app read path and the Home Assistant
reference sensors at the same time and reports PASS/FAIL:

```bash
HA_URL=http://ha.local:8123 HA_TOKEN=... python scripts/verify_against_ha.py \
    --options options.json --ha-power-entity sensor.meter_1_leistung \
    --ha-import-entity sensor.meter_1_bezogene_energie \
    --ha-export-entity sensor.meter_1_eingespeiste_energie
```

Keep `transmit_enabled: false` until the grid values and assignment have been verified on site.

## Tests

```bash
python -m unittest discover -s tests -v
python -m py_compile sma_energy_bridge/main.py scripts/verify_against_ha.py
ruff check .        # pip install ruff
python scripts/make_icons.py   # regenerate icon.png / logo.png
```

**Architecture:** The source profile reads the meter. The frame profile selects the SMA telegram. SolarEdge uses read-only Modbus FC03 and validates the meter ID and scale factors. Custom maps can use read-only FC03 or FC04. A decrease in a total active energy counter stops the app for manual review.

## Sunny Tripower with EMETER-20

Set `frame_profile: emeter20` in the app and configure a unique `meter_serial`.
In the Sunny Tripower, select **SMA Energy Meter** as the energy meter in use
under **System communication → Measured values**, then enter the same serial
under **Meter on Speedwire**. The manual assignment was verified with a
Sunny Tripower STP8.0-3AV-40 running firmware 4.10.10.R, including while powered
on AC only. The list of available meters can remain empty.

The 608-byte profile uses SUSy ID 349 and UDP source port 9522. It carries
active power and energy, frequency, line-to-neutral voltage, phase current,
power factor, reactive power and apparent power from SunSpec where available.
Reactive power follows the configured grid orientation. Apparent power uses
the direction of active power, and SMA receives the power factor magnitude.
Unavailable fields and reactive and apparent energy counters are zero-filled. Keep transmission
disabled during initial comparisons. Use this app for monitoring and testing.

If the SMA intermittently holds old readings despite fresh multicast frames,
set `unicast_host` to the inverter's IPv4 address and check its readings again.
The app then sends directly to UDP port 9522. Leave the option blank for multicast.
