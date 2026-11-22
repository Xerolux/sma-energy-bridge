---
title: Overview
---
# SMA Energy Bridge

Connect a Modbus TCP grid meter to a compatible SMA inverter from Home Assistant. The bridge reads the meter and transmits an SMA Speedwire Energy Meter telegram so the inverter can show grid readings. This beta is for display and testing. Use an approved meter for mandatory export control.

## Meter profiles

| Profile | What you need | Verification |
|---|---|---|
| SolarEdge SunSpec | SunSpec integer meter model, e.g. SolarEdge Meter 1 at zero-based address 40188 | SolarEdge SE10K through Modbus TCP and Sunny Tripower 8.0 with EMETER-20 |
| Custom Modbus | The meter's register map for grid power, imported energy and exported energy | Software-tested through register decoding and Speedwire encoding. Validate each device on site. |

## Install in Home Assistant

1. Add the [Xerolux repository](https://github.com/Xerolux/sma-energy-bridge) under **Settings → Apps → Install app → Repositories**.
2. Install **SMA Energy Bridge (Beta)** and enter the Modbus TCP host, port and unit ID. Choose your source profile.
3. Leave transmission off for the first start. Compare the logged grid power and both energy counters with an independent reading at the grid connection point. Positive power in the log means grid import.
4. Choose the Speedwire format for your receiver. Use `emeter20` for the tested Sunny Tripower setup and enter the SMA IPv4 address for direct delivery if needed. Assign a unique meter serial number, then enable transmission.

[Configure a custom meter]({{ '/profiles/' | relative_url }}) · [Read the Wiki](https://github.com/Xerolux/sma-energy-bridge/wiki)

## Support the project

[GitHub Sponsors](https://github.com/sponsors/Xerolux) · [Patreon](https://www.patreon.com/Xerolux) · [Ko-fi](https://ko-fi.com/xerolux) · [Buy Me a Coffee](https://buymeacoffee.com/xerolux) · [PayPal](https://paypal.me/xerolux) · [Tesla referral](https://ts.la/sebastian564489)
