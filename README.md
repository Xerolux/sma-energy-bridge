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
| `power_sign` | `import_positive` | sign of the meter power register |
| `swap_counters` | `false` | swap imported/exported energy values if meter orientation requires |
| `meter_serial` | `900000001` | unique, simulated meter ID |
| `susy_id` | `270` | SMA Energy Meter SUSy ID |
| `transmit_enabled` | `false` | never emit multicast until source values validated |

With more than one NIC, set `multicast_interface` to the **local IPv4 address** of the NIC facing the SMA, or multicast might leave via the wrong network.

## Repository use

Add your GitHub repository URL to Home Assistant **Settings → Apps → Install app → Repositories**, then install this app. Customize `repository.yaml` with your GitHub account details first. In the logs validate the signs and counters with transmission disabled. Only then switch on transmission, inspect UDP multicast `239.12.255.254:9522`, and check for recognition at the SMA.

## Tests

```bash
python -m unittest discover -s tests -v
python -m py_compile sma_energy_bridge/main.py
```

**Architecture:** The initial provider is SolarEdge SunSpec via an existing Modbus TCP proxy; other energy-meter providers are planned and not yet implemented.

**Implemented:** custom Modbus TCP function-03 client, SunSpec 201–204 meter mapping, raw-unit conversion, SMA telegram builder, stale-data detection, dry-run mode, and protocol tests. **Not implemented yet:** hardware acceptance, optional phase values, production-grade counter rollover handling, assured recognition on all SMA firmware versions.