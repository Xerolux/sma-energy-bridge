# Changelog

## 0.3.0

- Add a one-shot, read-only source and Speedwire frame check.
- Use SolarEdge export-positive power by default on new installs. Check the
  configured sign explicitly when upgrading an existing installation.
- Stop immediately on a counter decrease.
- Define architecture-specific Supervisor build images.
- Provide optional native Home Assistant Modbus sensors for the energy dashboard.
