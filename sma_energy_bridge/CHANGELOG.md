# Changelog

## 0.4.1

- Refresh the Home Assistant app icon and logo with a mint signal trace over a bridge. Both assets use transparent corners and are designed for light and dark themes.
- Update the Home Assistant documentation with supported architectures (`amd64` and `aarch64`) in English and German.

## 0.4.0

- Keep SolarEdge SunSpec as the default meter profile and add user-defined Modbus TCP register maps.
- Separate source profiles from the SMA telegram format. Custom maps support read-only Modbus FC03 and FC04, with optional phase measurements and reactive and apparent energy for EMETER-20.
- Add project funding, a GitHub Pages site and bilingual Wiki guides.

## 0.3.6

- Rename the Home Assistant app and repository to SMA Energy Bridge (Beta).
- Remove the experimental store flag. Meter data and transmission behavior are unchanged.

## 0.3.5

- Populate EMETER-20 line-to-neutral voltage, phase current, power factor, and total and per-phase reactive and apparent power from SolarEdge SunSpec.
- Keep unavailable values and unsupported reactive and apparent energy counters zero-filled for compatibility.

## 0.3.4

- Add an optional direct IPv4 destination for Speedwire telegrams when multicast delivery is intermittent.

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
