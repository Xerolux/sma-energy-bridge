# SMA Energy Bridge (Experimental)

First supported source: read-only **SolarEdge SunSpec meter → Modbus TCP proxy → SMA Speedwire Energy Meter multicast**. German technical design and implementation: [KONZEPT_UND_UMSETZUNG.md](KONZEPT_UND_UMSETZUNG.md).

⚠️ **Experimental, display/test only.** Compatibility with the real `STP8.0-3AV-40` has **not** been verified. Do not use for mandatory export control. The data source must be the complete *grid connection point meter*, not only inverter PV power.

## Configuration

Configure the existing proxy address and port in the Home Assistant app settings. `meter_model_base: 40188` addresses SolarEdge SunSpec Meter 1 (base-0); verify DID 201–204. `transmit_enabled: false` is the default **dry-run** mode.

| Key | Example | Meaning |
|---|---|---|
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

The command reads one holding-register block and prints grid power, import and export in kWh, and the generated frame size. It does not open a multicast socket.

## Native Home Assistant Modbus

Use [the optional package](examples/home-assistant-modbus.yaml) if you want HA entities for the same meter. Enable [Home Assistant packages](https://www.home-assistant.io/docs/configuration/packages/), copy the package into your packages directory, and set `sma_bridge_modbus_host` in `secrets.yaml`. The example uses SolarEdge Meter 1, TCP port 502 and unit ID 1. Check for existing SolarEdge entities before enabling additional polling. Keep the raw entity IDs used by the templates and select the two kWh entities as grid consumption and return to grid in the Energy dashboard. The native package publishes HA entities. The app handles Speedwire transmission independently.

## Tests

```bash
python -m unittest discover -s tests -v
python -m py_compile sma_energy_bridge/main.py
```

**Architecture:** The initial provider is SolarEdge SunSpec via an existing Modbus TCP proxy; other energy-meter providers are planned and not yet implemented.

The app uses Modbus TCP function 03, validates the SunSpec meter ID and scale factors, and stops on a counter decrease. Hardware acceptance at the SMA receiver and counter rollover handling remain open.
