# Changelog

## 0.3.3

- Add the tested 608-byte EMETER-20 profile with SUSy ID 349 and UDP source port 9522.
- Encode signed per-phase active power, active energy counters and grid frequency when available.
- Keep the original compact profile as the default and leave transmission disabled by default.

## 0.3.2

- Add `scripts/verify_against_ha.py` to verify live source values against Home
  Assistant reference sensors (validated 2026-11-22 on the reference
  installation: counter drift <= 0.001 kWh, power sign confirmed in both
  directions, DID 203, power_sf -2, energy_sf -1).
- Add option name translations for the app store (English, German).
- Add app icon and logo, link the repository URL and set the stage to
  experimental.
- Follow the Supervisor `LOG_LEVEL` environment variable.
- Simplify the native Modbus example: device_class/state_class and linear
  scale factors pinned at the verified meter replace the template layer.

## 0.3.1

- Correct the Speedwire group tag header so receivers can parse the meter telegram.

## 0.3.0

- Add a one-shot, read-only source and Speedwire frame check.
- Use SolarEdge export-positive power by default on new installs. Check the
  configured sign explicitly when upgrading an existing installation.
- Stop immediately on a counter decrease.
- Define architecture-specific Supervisor build images.
- Provide optional native Home Assistant Modbus sensors for the energy dashboard.
