# SMA Energy Bridge (Beta)

Reads an external grid-connection-point meter over Modbus TCP and sends SMA
Speedwire Energy Meter telegrams. The built-in SolarEdge SunSpec profile uses
read-only Modbus FC03. A custom register map can use FC03 or FC04. For display
and testing only. Use an approved meter for mandatory export control.

[Setup and supported profiles](https://xerolux.github.io/sma-energy-bridge/) ·
[Eigene Zählerprofile](https://xerolux.github.io/sma-energy-bridge/de/profile/) ·
[Wiki](https://github.com/Xerolux/sma-energy-bridge/wiki)

## Supported architectures / Unterstützte Architekturen

| Home Assistant | English | Deutsch |
|---|---|---|
| `amd64` | 64-bit Intel and AMD systems | 64-Bit-Systeme mit Intel- oder AMD-Prozessor |
| `aarch64` | 64-bit ARM systems, e.g. Raspberry Pi 4 or 5 with 64-bit Home Assistant OS | 64-Bit-ARM-Systeme, z. B. Raspberry Pi 4 oder 5 mit 64-Bit-Home-Assistant-OS |

## How it works

1. The app polls the selected meter source every `poll_interval_seconds`.
   SolarEdge SunSpec uses base 40188 by default and reads meter scale factors.
2. It sends the last valid readings as an SMA Speedwire telegram every
   `transmit_interval_seconds` until they are stale. Choose compact or EMETER-20
   independently of the meter source. The destination can be multicast or
   an SMA IPv4 address.
3. With `transmit_enabled: false` (default) everything runs in dry-run mode:
   values are read, validated and logged, but no telegram leaves the host.

## Setup

1. Configure the Modbus TCP host, port, unit ID and source profile. Set
   the meter model base for SolarEdge or add register mappings for Custom Modbus.
   The data source must be the complete grid connection point meter, not only
   inverter PV power.
2. Keep `transmit_enabled: false` and start the app. The log prints
   `grid=+W (+=import)` plus both counters every 30 seconds.
3. Verify the logged values against your reference meter - either manually or
   with `scripts/verify_against_ha.py` from the repository (compares the exact
   app read path against Home Assistant reference sensors and reports
   PASS/FAIL).
4. After a successful verification, enable transmission and check whether the
   SMA receiver detects the virtual meter (serial number from the options).
   Reception depends on the SMA device and firmware; a syntactically correct
   telegram alone does not guarantee detection.

## Verified reference installation (2026-11-22)

SolarEdge SE10K with SunSpec Meter 1 (DID 203, power_sf -2, energy_sf -1)
behind a ModBridge proxy. 12/12 verification samples matched the Home
Assistant reference: worst counter drift 0.001 kWh, power sign agreement in
both import and export direction. Configuration used:
`power_sign: export_positive`, `swap_counters: false`.

## Safety notes

- The Modbus source is only read; no values are ever written.
- The app stops itself when an energy counter decreases (reset/wrap) and
  requires a manual restart.
- Do not use the emulated meter as the only measurement signal for feed-in
  limitation or zero-export control; SMA requires much faster measurement
  intervals for such control loops.

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
