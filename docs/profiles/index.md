---
title: Custom Modbus profile
---
# Configure a custom Modbus meter

In the Home Assistant app configuration, choose `source_profile: custom_modbus`. Enter the Modbus TCP host, port and unit ID. Use `custom_modbus_function: 3` for holding registers or `4` for input registers. Each profile uses one read function and one meter.

Open the options in YAML to paste a list of mappings. The addresses below illustrate the syntax. Replace them with the zero-based addresses from your meter's manual.

```yaml
source_profile: custom_modbus
custom_modbus_function: 3
frame_profile: emeter20
power_sign: import_positive
transmit_enabled: false
custom_registers:
  - "power, 0, int32, 0.1"
  - "import_wh, 2, uint32, 1"
  - "export_wh, 4, uint32, 1"
  - "voltage_l1, 20, uint16, 0.1"
  - "current_l1, 21, uint16, 0.001"
```

Each entry contains the metric, register address, data type and multiplier. Supported types are `int16`, `uint16`, `int32`, `uint32`, `float32`, `int64`, `uint64` and `float64`. The default is high word first, with big-endian bytes within each word. Append `_swapped` to a multi-register type to reverse the entire register order. The multiplier is fixed. For example, use `1000` to convert kWh to Wh or a power factor from 0 to 1 with `100` to convert it to percent.

| Metric | Unit | Availability |
|---|---|---|
| `power` | W, signed | Required |
| `import_wh`, `export_wh` | Wh | Required. Separate cumulative counters. |
| `reactive_power`, `apparent_power`, `power_factor` | var, VA, % | Optional with EMETER-20 |
| `reactive_import_varh`, `reactive_export_varh` | varh | Optional with EMETER-20 |
| `apparent_import_vah`, `apparent_export_vah` | VAh | Optional with EMETER-20 |
| `frequency` | Hz | Optional total with EMETER-20 |
| `current_l1`, `voltage_l1` | A, V phase-to-neutral | Optional per phase with EMETER-20 |

Append `_l1`, `_l2` or `_l3` for phase values, except for frequency. For apparent power on a phase, map that phase's active power as well. The bridge uses its sign to select the direction. Map reactive and apparent energy separately by direction as documented for your meter. The compact Speedwire format carries only total active power and both active energy counters.

Set `power_sign` to match your meter's raw sign for active and reactive power. Set `swap_counters` only if the meter's active import and export counters are reversed. Check power in both directions and compare the two energy counters with transmission disabled. Only enable transmission after checking the readings. A source register error rejects the sample. Unmapped optional fields are zero-filled in the EMETER-20 frame.

The built-in `solaredge_sunspec` profile reads the scale factors from the meter. You can return to it at any time by selecting it in the app. For other devices, [share a tested register map](https://github.com/Xerolux/sma-energy-bridge/issues) with the meter model, firmware and units so it can become a reusable profile.
