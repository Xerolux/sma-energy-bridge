# SMA Energy Bridge

Install from the Xerolux SMA Energy Bridge app repository. See the repository
README for the option reference and an optional native Modbus sensor package.

1. Set the Modbus proxy host, port, unit ID and SunSpec meter model address.
2. Leave transmission disabled and start the app. Compare the signed grid
   power and both counters in the logs against your reference meter.
3. Choose a unique meter serial. Keep transmission disabled on systems that use
   the SMA meter for grid or battery control until the topology is validated.
