---
title: Eigenes Modbus-Profil
lang: de
---
# Eigenen Modbus-Zähler einrichten

In den Home-Assistant-App-Optionen `source_profile: custom_modbus` wählen. Modbus-TCP-Host, Port und Unit-ID eintragen. `custom_modbus_function: 3` gilt für Holding Registers, `4` für Input Registers. Ein Profil verwendet eine Lesefunktion und einen Zähler.

Über den YAML-Editor der App-Optionen lässt sich eine Liste einfügen. Die folgenden Adressen zeigen das Format. Verwende die nullbasierten Adressen aus der Anleitung deines Zählers.

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

Jede Zeile enthält Messgröße, Adresse, Datentyp und Faktor. Unterstützt werden `int16`, `uint16`, `int32`, `uint32`, `float32`, `int64`, `uint64` und `float64`. Standardmäßig kommt das höherwertige Wort zuerst, innerhalb jedes Worts gilt Big-Endian. Der Zusatz `_swapped` kehrt die Reihenfolge aller Wörter eines Mehrworttyps um. Der Faktor ist fest. Beispielsweise wandelt `1000` kWh in Wh um. Für einen Leistungsfaktor zwischen 0 und 1 rechnet `100` in Prozent um.

| Messgröße | Einheit | Verfügbarkeit |
|---|---|---|
| `power` | W mit Vorzeichen | Pflicht |
| `import_wh`, `export_wh` | Wh | Pflicht. Getrennte fortlaufende Zählerstände. |
| `reactive_power`, `apparent_power`, `power_factor` | var, VA, % | Optional mit EMETER-20 |
| `reactive_import_varh`, `reactive_export_varh` | varh | Optional mit EMETER-20 |
| `apparent_import_vah`, `apparent_export_vah` | VAh | Optional mit EMETER-20 |
| `frequency` | Hz | Optional als Gesamtwert mit EMETER-20 |
| `current_l1`, `voltage_l1` | A, V Phase gegen Neutralleiter | Optional je Phase mit EMETER-20 |

Für Phasenwerte `_l1`, `_l2` oder `_l3` ergänzen. Die Frequenz gibt es nur einmal. Für Scheinleistung je Phase wird auch die Wirkleistung der jeweiligen Phase benötigt. Ihr Vorzeichen bestimmt die Richtung im Telegramm. Blind- und Scheinenergie gemäß Zählerdokumentation getrennt je Richtung zuordnen. Das kompakte Speedwire-Format überträgt nur die Gesamtwirkleistung und beide Wirkenergiezähler.

Mit `power_sign` das Vorzeichen für Wirk- und Blindleistung einstellen. `swap_counters` nur bei vertauschten Wirkenergiezählern aktivieren. Leistung in beiden Richtungen und beide Zählerstände mit deaktivierter Übertragung vergleichen. Erst danach die Übertragung einschalten. Bei einem Registerfehler verwirft die Bridge die Abfrage. Optionale Felder ohne Zuordnung stehen im EMETER-20-Telegramm auf null.

Das eingebaute Profil `solaredge_sunspec` liest die Skalierungsfaktoren aus dem Zähler. Es lässt sich jederzeit in der App wieder auswählen. Eine [getestete Registerliste für ein weiteres Gerät](https://github.com/Xerolux/sma-energy-bridge/issues) kann mit Modell, Firmware und Einheiten als Grundlage für ein weiteres fertiges Profil eingereicht werden.
