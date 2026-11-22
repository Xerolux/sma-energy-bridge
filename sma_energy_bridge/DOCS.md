# SMA Energy Bridge

Bridges an external grid-connection-point energy meter into the SMA Speedwire
Energy Meter multicast protocol, so SMA devices can display meter data from a
non-SMA source. First supported source: SolarEdge SunSpec meters, read
strictly read-only (Modbus function 03) through an existing Modbus TCP proxy
such as ModBridge. For display/testing only - never for mandatory export
control. Full design, risks and test plan: [repository README] and
`KONZEPT_UND_UMSETZUNG.md`.

## How it works

1. The app polls the SunSpec meter block (default base 40188) every
   `poll_interval_seconds` and validates the meter DID (201..204), scale
   factors, plausibility limits and counter monotonicity.
2. It converts power and both energy counters to the SMA Energy Meter
   Speedwire/OBIS telegram (multicast 239.12.255.254:9522, SUSy 270).
3. With `transmit_enabled: false` (default) everything runs in dry-run mode:
   values are read, validated and logged, but no telegram leaves the host.

## Setup

1. Configure the Modbus proxy host/port, unit ID and meter model base.
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
active power, active energy and grid frequency from SunSpec where available.
Other fields in the compatibility profile are zero-filled. Keep transmission
disabled during initial comparisons. Use this app for monitoring and testing.

If the SMA intermittently holds old readings despite fresh multicast frames,
set `unicast_host` to the inverter's IPv4 address and check its readings again.
The app then sends directly to UDP port 9522. Leave the option blank for multicast.
