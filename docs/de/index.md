---
title: Übersicht
lang: de
---
# SMA Energy Bridge

Mit der Bridge bindest du einen Modbus-TCP-Netzzähler über Home Assistant an einen kompatiblen SMA-Wechselrichter an. Die Bridge liest den Zähler aus und sendet die Messwerte als SMA-Speedwire-Zählertelegramm. Die Beta dient zur Anzeige und zum Testen. Für eine vorgeschriebene Einspeisebegrenzung ist ein zugelassener Zähler erforderlich.

## Zählerprofile

| Profil | Voraussetzung | Geprüft |
|---|---|---|
| SolarEdge SunSpec | SunSpec-Zählermodell mit Ganzzahlregistern, z. B. SolarEdge Meter 1 an nullbasierter Adresse 40188 | SolarEdge SE10K über Modbus TCP und Sunny Tripower 8.0 mit EMETER-20 |
| Eigenes Modbus-Profil | Registertabelle für Netzleistung, Bezugsenergie und Einspeiseenergie | Registerdekodierung und Speedwire-Telegramm per Softwaretest. Jedes konkrete Gerät vor Ort abgleichen. |

## Unterstützte Architekturen

- `amd64` für 64-Bit-Systeme mit Intel- oder AMD-Prozessor.
- `aarch64` für 64-Bit-ARM-Systeme, etwa Raspberry Pi 4 oder 5 mit 64-Bit-Home-Assistant-OS.

## Installation in Home Assistant

1. Das [Xerolux-Repository](https://github.com/Xerolux/sma-energy-bridge) unter **Einstellungen → Apps → App installieren → Repositories** hinzufügen.
2. **SMA Energy Bridge (Beta)** installieren. Modbus-TCP-Host, Port und Unit-ID eintragen und das Zählerprofil wählen.
3. Beim ersten Start die Übertragung deaktiviert lassen. Netzleistung sowie Bezugs- und Einspeisezähler im Log mit dem Zähler am Netzanschlusspunkt vergleichen. Im Log bedeutet ein positiver Leistungswert Netzbezug.
4. Das Speedwire-Format für den Empfänger wählen. Für den geprüften Sunny Tripower `emeter20` verwenden und für direkte Zustellung bei Bedarf die SMA-IPv4-Adresse eintragen. Eine eindeutige Zähler-Seriennummer vergeben und die Übertragung aktivieren.

[Eigenen Zähler einrichten]({{ '/de/profile/' | relative_url }}) · [Wiki lesen](https://github.com/Xerolux/sma-energy-bridge/wiki)

## Projekt unterstützen

[GitHub Sponsors](https://github.com/sponsors/Xerolux) · [Patreon](https://www.patreon.com/Xerolux) · [Ko-fi](https://ko-fi.com/xerolux) · [Buy Me a Coffee](https://buymeacoffee.com/xerolux) · [PayPal](https://paypal.me/xerolux) · [Tesla-Empfehlungslink](https://ts.la/sebastian564489)
