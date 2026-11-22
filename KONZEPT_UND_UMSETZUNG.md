# SMA Energy Bridge – Konzept und Umsetzung

**Status:** Technischer Prototyp `v0.2.0` · **Stand:** 22.11.2026  
**Zielplattform:** Home Assistant OS / Supervisor-App (bisher: Add-on)  
**Zielgerät:** SMA Sunny Tripower 8.0, `STP8.0-3AV-40`  
**Messquelle:** vorhandener SolarEdge-Netzzähler am Netzanschlusspunkt, ausgelesen über den **bereits vorhandenen Modbus-TCP-Proxy**  
**Betriebsart:** Zunächst ausschließlich **Visualisierung/Test**; keine zulassungsrelevante Regelung.

> **Einschränkung:** Die Übertragung eines selbst erzeugten SMA-Energy-Meter-Telegramms ist protokollseitig dokumentierbar. Die automatische Erkennung und vollständige Verarbeitung durch genau diesen SMA-Wechselrichter und seine installierte Firmware **ist noch nicht am realen Gerät nachgewiesen**. Dieses Projekt ist keine zertifizierte oder vom Hersteller freigegebene Ersatzmessung.

## 1. Ziel und Abgrenzung

Der vorhandene SolarEdge-Zähler misst **den gesamten Netzbezug und die gesamte Netzeinspeisung des Hauses** am Netzanschlusspunkt – einschließlich SolarEdge- und SMA-Erzeugung sowie Verbraucher. Ein zusätzlicher physischer SMA Energy Meter soll für die *optionale Anzeige* vermieden werden.

Die Bridge soll:

1. den SolarEdge-SunSpec-Zähler **direkt über den vorhandenen Modbus-TCP-Proxy** lesen (kein Umweg über HA-Sensorzustände, keine zweite Direktverbindung zum SolarEdge-Wechselrichter),
2. aktuelle Wirkleistung und die kumulierten Bezugs-/Einspeisezähler auslesen,
3. diese Messwerte in das **SMA Energy Meter Speedwire/OBIS-Protokoll** übersetzen,
4. entsprechende UDP-Multicast-Telegramme im lokalen Netz veröffentlichen,
5. damit – soweit der SMA sie annimmt – im SMA-System Netzbezug, Einspeisung und Verbrauchsdaten verfügbar machen.

**Langfristiges Ziel:** Die modulare Bridge soll später weitere Quellen (z. B. Shelly, Victron und andere Modbus-Zähler) ansprechen können. In dieser Version existiert ausschließlich die SolarEdge-SunSpec-Quelle.\n\n**Nicht im Umfang von v0.2.0:** Integration in die Einspeiseregelung, Leistungsbegrenzung nach Netzbetreibervorgaben, eichrechtliche Messung, Home-Manager-Emulation, Übernahme der SolarEdge-PV-Erzeugungsdaten in die interne SMA-Ertragsbilanz, per-Phase-Messwerte und automatische SunSpec-Geräteerkennung.

## 2. Architektur

```text
                     Haus / PV-Anlage
                 ┌──────────────────────────┐
                 │ Netzanschlusspunkt       │
                 │ SolarEdge-Netzzähler     │
                 │ (misst ALLES)            │
                 └────────────┬─────────────┘
                              │ RS485 / SolarEdge
                 ┌────────────▼─────────────┐
                 │ SolarEdge-Wechselrichter │
                 │ SunSpec Modbus TCP       │
                 └────────────┬─────────────┘
                              │
                 ┌────────────▼─────────────┐
                 │ Vorhandener Modbus-Proxy │
                 │ mehrere lesende Clients  │
                 └─────┬───────────┬────────┘
                       │           │
            Home Assistant       SMA Energy Bridge
            SolarEdge Modbus     (separate Supervisor-App)
                                   │
                                   │ nur Lesezugriff (FC 03)
                                   │ Übersetzung SunSpec → SMA OBIS
                                   │ UDP Multicast 239.12.255.254:9522
                                   ▼
                        SMA STP8.0-3AV-40
                          (SMA Speedwire)
                                   │
                             SMA / Sunny Portal
                             soweit unterstützt
```

Die Bridge braucht weder das Home-Assistant-API noch das SolarEdge-Cloudkonto. Beide PV-Wechselrichter und der Add-on-Host müssen über ein geeignetes lokales Netz verbunden sein; **Multicast muss den SMA tatsächlich erreichen**.

## 3. Protokoll- und Datenmapping

### 3.1 SolarEdge → Bridge (SunSpec/Modbus TCP)

**Funktionscode:** `03` = Read Holding Registers, strikt **lesend**.  
**Host:** IP/DNS des existierenden Modbus-Proxys.  
**Port:** Port des Proxys (nicht blind `1502` oder `502` übernehmen).  
**Unit ID:** Modbus-ID des SolarEdge-Wechselrichters hinter dem Proxy; gewöhnlich `1`, aber anlagenabhängig.  
**Adressen:** **0-basiert** wie in der SolarEdge-Dokumentation.

Für den ersten SolarEdge-SunSpec-Zähler (`Meter 1`) gilt im dokumentierten Standardlayout:

| Wert | 0-basierte Adresse | Datentyp | Bedeutung |
|---|---:|---|---|
| `C_SunSpec_DID` | `40188` | uint16 | Muss `201`, `202`, `203` oder `204` ergeben |
| `C_SunSpec_Length` | `40189` | uint16 | Modellblocklänge, Plausibilitätsprüfung |
| `M_AC_Power` | `40206` | int16 | Netz-Wirkleistung (mit Vorzeichen) |
| `M_AC_Power_SF` | `40210` | int16 | Dezimal-Skalierungsfaktor der Leistung |
| `M_Exported` | `40226–40227` | uint32 (Big-Endian) | Exportierte Wirkarbeit, vor SF in Wh |
| `M_Imported` | `40234–40235` | uint32 (Big-Endian) | Importierte Wirkarbeit, vor SF in Wh |
| `M_Energy_W_SF` | `40242` | int16 | Gemeinsamer Dezimal-Skalierungsfaktor der Energie |

Ein Poll liest die **55 Holding-Register ab Adresse `40188`** als zusammenhängenden Block. Die Registeradressen des angeschlossenen Zählers können sich unterscheiden: `Meter 2` beginnt im veröffentlichten Layout beim SunSpec-DID `40362` und ist über `meter_model_base` konfigurierbar. Keine festen Adressen annehmen, wenn das Lesen keinen gültigen DID liefert. Das gilt ebenso für spezielle SolarEdge-Topologien/Firmware.

Umrechnung:

```python
power_w      = signed16(raw_power) * 10 ** signed16(power_sf)
imported_kwh = uint32(raw_imported) * 10 ** signed16(energy_sf) / 1000
exported_kwh = uint32(raw_exported) * 10 ** signed16(energy_sf) / 1000
```

**Vorzeichen:** Im Projekt ist `import_positive` die zunächst angenommene Messkonvention: Positive Netzleistung = Bezug, negative = Einspeisung. Bei umgekehrter Sensorrichtung ist `power_sign: export_positive` einzustellen; falls auch die Zählerkanäle seitenverkehrt sind, zusätzlich `swap_counters: true`. **Beides muss vor Freigabe mit dem realen Zähler plausibilisiert werden** (einmal mit eindeutigem Netzbezug, einmal bei eindeutiger Einspeisung).

### 3.2 Bridge → SMA (Speedwire)

Die dokumentierte SMA-Energy-Meter-Multicast-Gruppe lautet **`239.12.255.254`, UDP-Port `9522`**. Die Telegramme enthalten:

- SMA-Kennung `SMA\0`, SMA Net2 und Protokollkennung `0x6069`;
- sechs Byte virtuelle Geräteadresse: **SUSy-ID `270`** und konfigurierbare **32-Bit-Seriennummer** (Default `900000001`, muss im eigenen Netzwerk eindeutig sein);
- Zeitstempel als überlaufender 32-Bit-Millisekundenzähler;
- OBIS-Kanal `1:1.4.0` = momentaner **Netzbezug** mit 0,1-W-Auflösung;
- OBIS-Kanal `1:1.8.0` = **Bezugsarbeit** in Ws;
- OBIS-Kanal `1:2.4.0` = momentane **Einspeisung** mit 0,1-W-Auflösung;
- OBIS-Kanal `1:2.8.0` = **Einspeisearbeit** in Ws.

Die Bridge sendet aktuell **nur die vier Summenkanäle**. Falls der SMA weitere Kanäle/Felder voraussetzt, müssen per Wireshark bekannte gültige SMA-Energy-Meter-Telegramme verglichen und die Implementierung entsprechend ergänzt werden. Die bloße syntaktische Korrektheit garantiert **keine** SMA-Geräteerkennung.

## 4. Designentscheidungen

| Aspekt | Entscheidung |
|---|---|
| Datenquelle | Ausschließlich vorhandener **Modbus-TCP-Proxy** |
| Datenpfad | Direkter TCP-Poll; keine HA-REST-API-Abhängigkeit |
| Fremdbibliotheken | Python-Standardbibliothek; v0.2.0 braucht keine `pymodbus`-Installation |
| Host-Netzwerk | `host_network: true`, damit UDP-Multicast am LAN ankommen kann |
| Abfrage | Standard **5 s** (konfigurierbar) |
| UDP-Sendung | Standard **1 s** mit zuletzt gültigem Messwert, sofern frisch |
| Frischekontrolle | Nach **15 s** ohne gültigen neuen Messwert keine Telegramme mehr |
| Netzbegrenzung | Multicast-TTL **1**: nur lokales Segment |
| Testmodus | `transmit_enabled: false` beim ersten Start |
| Neustart | `boot: manual`; erst nach realem Abnahmetest auf Autostart umstellen |
| Protokoll | Nur lesender Modbus-Funktionscode `03`; nie Schreibregister |
| Plausibilität | DID/SF-Bereich, ungültige SunSpec-Werte, Leistungslimit, fallende Zählerstände prüfen |

**Wichtig für den Polling-Rhythmus:** Die Wiederholung desselben Messwerts alle 1 s macht ihn nicht aktueller. Das ist für eine Anzeige ein Testansatz, **nicht** für dynamische Wirk­leistungsregelung oder 0-%-Einspeisung geeignet.

## 5. Repository-Struktur und bereits vorhandene Umsetzung

```text
sma-energy-bridge/
├── repository.yaml
├── README.md
├── KONZEPT_UND_UMSETZUNG.md
├── sma_energy_bridge/
│   ├── config.yaml          # Supervisor-Konfiguration, Optionen, Validierung
│   ├── Dockerfile           # Container/Startskript
│   └── main.py              # Modbus-TCP-Client + SunSpec + SMA Speedwire
├── tests/
│   └── test_protocol.py     # lokale Protokoll- und Mapping-Tests
└── .github/workflows/
    └── tests.yaml           # Tests bei Push und Pull Request
```

`main.py` implementiert:

1. Modbus-TCP-Request mit MBAP-Header und `Read Holding Registers`;
2. Validierung der Antwort (Transaktionsnummer, Unit-ID, FC, Registeranzahl);
3. Interpretation des SolarEdge-SunSpec-Meterblocks mit Skalierung;
4. Vorzeichen- und Import/Export-Zuordnung;
5. SMA-OBIS-Paketkonstruktion in Network Byte Order;
6. Multicast-Sendeprozess mit Dry-Run-Option und Frischekontrolle;
7. Protokollierung von Messwerten, Ausfällen und ungültigen Zählerständen.

Es gibt bereits automatisierte Tests für SMA-Telegrammaufbau, Leistungsvorzeichen, Energieeinheiten, SunSpec-Skalierung, ungültige Messwerte, Kanaltausch und eine simulierte Modbus-TCP-Serverantwort. **Keine reale SolarEdge-/SMA-Hardware war für diesen Prototyp angeschlossen.**

## 6. Konfiguration für die vorhandene Anlage

Die folgenden Werte sind eine **Startvorlage**. Insbesondere `modbus_host`, `modbus_port`, `modbus_unit_id` und `meter_model_base` sind aus der vorhandenen Proxy-Konfiguration zu übernehmen beziehungsweise am realen Gerät zu verifizieren.

```yaml
modbus_host: "IP_DEINES_MODBUS_PROXY"
modbus_port: 502               # tatsächlichen Proxy-Port eintragen
modbus_unit_id: 1             # SolarEdge Unit-ID hinter dem Proxy
meter_model_base: 40188       # SolarEdge Meter 1, base-0
power_sign: "import_positive"
swap_counters: false
meter_serial: 900000001        # virtuelle Gerätekennung, eindeutig halten
susy_id: 270
poll_interval_seconds: 5
transmit_interval_seconds: 1
stale_after_seconds: 15
max_abs_power_w: 30000
multicast_interface: ""      # bei mehreren LANs eigene IPv4-Adresse eintragen
transmit_enabled: false       # bis Vorzeichen und Werte geprüft sind
```

Bei mehreren Interfaces auf dem HA-Host empfiehlt es sich, `multicast_interface` auf die **IPv4-Adresse der Schnittstelle im SMA-LAN** zu setzen. Diese Option nimmt *keinen* Gerätenamen (`eth0`), sondern eine IPv4-Adresse.

## 7. Installation im eigenen GitHub-Repository

1. Neuen GitHub-Repository-Namen festlegen, `Xerolux/sma-energy-bridge`.
2. Sämtliche Dateien aus dem gelieferten Projektordner in die Repository-Wurzel hochladen; **nicht nur** das Markdown.
3. Optional `repository.yaml` mit deiner echten Repository-URL und Maintainer-Angabe versehen; aktuell enthält die Vorlage Platzhalter.
4. In Home Assistant OS: **Einstellungen → Apps / Add-ons → App-Store → Repositories** öffnen und die GitHub-Repository-URL hinzufügen. Der genaue Menüname hängt von der Home-Assistant-Version ab.
5. **SMA Energy Bridge (Experimental)** installieren, `modbus_host`/Port/Unit-ID anpassen und starten.
6. Mit `transmit_enabled: false` in den Logs die realen Werte für `grid`, `import`, `export` prüfen.
7. Nach bestandenem Test `transmit_enabled: true` setzen und die Bridge neu starten.
8. Im SMA-Webinterface als Installateur prüfen, ob der virtuelle Zähler erkannt beziehungsweise unter **Meter auf Speedwire** mit der eingestellten Seriennummer auswählbar ist. Menüpunkt und unterstützte Funktion sind firmwareabhängig.
9. Zum Schluss am SMA die Anzeige gegen SolarEdge-Zähler, Home Assistant und ggf. Netzbetreiberzähler vergleichen.

**Beispiel Git-Befehle**, nachdem du lokal den Projektordner geöffnet hast und dein Repository angelegt ist:

```bash
git init
git add .
git commit -m "feat: initial SolarEdge Modbus proxy to SMA Speedwire prototype"
git branch -M main
git remote add origin https://github.com/Xerolux/sma-energy-bridge.git
git push -u origin main
```

Keine Passwörter, privaten Zugangstokens, echten IP-Adressen aus dem Heimnetz oder Internetfreigaben mit ins öffentliche Git-Repository nehmen.

## 8. Testplan / Abnahmekriterien

### A. Offline-Tests

```bash
python -m unittest discover -s tests -v
python -m py_compile sma_energy_bridge/main.py
```

**Muss:** Alle Tests bestehen, keine Python-Syntaxfehler, keine Schreib-Funktionscodes an Modbus.

### B. Read-only-Test über Proxy (`transmit_enabled: false`)

- [ ] Modbus-Proxy erreichbar; andere Modbus-Clients laufen weiter ohne Timeout-Anstieg.
- [ ] `C_SunSpec_DID` liegt bei 201–204; beim falschen DID Zählerposition anpassen.
- [ ] Bei ausgeschalteter/geringer PV-Produktion und eindeutigem Hausverbrauch wird **Netzbezug positiv** angezeigt.
- [ ] Bei eindeutiger Überschusseinspeisung wird **Netzleistung negativ** angezeigt.
- [ ] Bezugs- und Einspeisezähler sind in kWh plausibel, steigen monoton und werden nicht getauscht.
- [ ] Bei Trennung des Proxys wird spätestens nach dem `stale_after_seconds`-Fenster nicht mehr gesendet.

### C. SMA-Kompatibilitätstest (`transmit_enabled: true`)

- [ ] UDP-Pakete `239.12.255.254:9522` im SMA-LAN mit `tcpdump`/Wireshark sichtbar.
- [ ] Virtuelle Seriennummer kollidiert mit keinem realen SMA Energy Meter.
- [ ] SMA STP8.0-3AV-40 erkennt die Quelle; ansonsten **nicht** von erfolgreicher Integration sprechen.
- [ ] Netzbezug, Einspeisung und Verbrauchsansicht stimmen mit der SolarEdge-Quelle überein.
- [ ] Keine unbeabsichtigte Leistungsregelung oder Warnung durch SMA-Parameter.
- [ ] Verhalten nach SMA-Neustart, Proxy-Ausfall, HA-Neustart und nächtlichem PV-Stillstand getestet.

### D. Negativtests

- [ ] Falsche Proxy-IP → keine UDP-Telegramme.
- [ ] Falsche Meter-Basisadresse → kein falscher Messwert wird gesendet.
- [ ] Ungültiger Skalierungsfaktor oder `0xFFFFFFFF`-Zähler → kein Senden ungültiger Daten.
- [ ] Sinkender Energiezähler (Reset/Wrap) → kein normaler Weiterbetrieb ohne Prüfung.
- [ ] Zwei Netzwerkinterfaces → nur gewähltes SMA-LAN erhält die Telegramme.

## 9. Risiken und Grenzen

**Kompatibilität:** SMA kann zusätzliche OBIS-Daten, Erkennungsmerkmale, konkrete Sender-IDs oder die Konfiguration einer bekannten Meter-Seriennummer voraussetzen. Das muss am **STP8.0-3AV-40** geprüft werden. Eine erfolgreiche Telegrammerzeugung allein beweist nichts.

**SolarEdge-Spezifika:** Das Dokument beschreibt beispielhafte SunSpec-Zählerpositionen. Je nach Meter-Nummer, Gerätegeneration oder SolarEdge-Topologie können Register verschoben sein. Der Code prüft den Meter-DID, bevor er Daten interpretiert.

**Zählerstände:** SunSpec-Energiezähler sind 32 Bit und können zurückgesetzt oder überlaufen. Das MVP erkennt fallende Werte und meldet sie; eine produktive Version sollte dokumentierte Resynchronisierung, Reboot-Wiederanlauf und ggf. persistierte Counterzustände vorsehen.

**Plausibilität der SMA-Verbrauchsanzeige:** Der gemessene Netzfluss umfasst SolarEdge- und SMA-PV. Der SMA kennt aber ohne gesonderte Kopplung nur **seine eigene** PV-Erzeugung. Eine daraus berechnete SMA-Hausverbrauchsanzeige kann daher trotz korrektem Netzfluss **falsch** sein. Die SMA-Bridge ist keine automatische Fusion beider Erzeugungskurven.

**Netzwerk:** UDP-Multicast über VLANs, WLAN-Isolation, IGMP-Snooping oder Proxmox-/Docker-Bridges kann blockiert werden. Multicast-Empfang auf dem SMA-LAN ist zu testen; notfalls Add-on-Host oder Interface anpassen.

**Regelung:** **Keine Nutzung als einziges Messsignal für gesetzlich/vertraglich vorgeschriebene Einspeisebegrenzung**, Nulleinspeisung oder sicherheitsrelevante Anlagensteuerung. SMA nennt für bestimmte Regelungsfälle erheblich schnellere Messintervalle (200 ms) als der hier verwendete SolarEdge-Poll.

**Messung und Datenschutz:** Ein vorhandener, korrekt installierter Netzbetreiber-Zweirichtungszähler bleibt für die abrechnungsrelevante Messung bestehen. Modbus-TCP bietet üblicherweise keine Authentisierung/Verschlüsselung; Proxy und Add-on nur im vertrauenswürdigen LAN betreiben.

## 10. Roadmap

| Version | Meilenstein | Abschlusskriterium |
|---|---|---|
| `0.2.0` | SunSpec via Modbus-Proxy, SMA-Summendaten, Dry Run, Unit-Tests | **Quellcode und Offline-Tests vorhanden** |
| `0.2.x` | Realdaten-Test am vorhandenen SolarEdge-Proxy | DID, Leistungsvorzeichen und kWh verifiziert |
| `0.3.0` | SMA-Erkennung und Telegramminhalt mit Wireshark bestätigen | Werte im STP8.0-Webinterface sichtbar |
| `0.4.0` | Optional Phasenkanäle, Geräteerkennung, Diagnostik/Health-Sensor | Vergleich über alle drei Phasen |
| `0.5.0` | Persistenz nach Reset/Wrap, Konfigurationstests, zuverlässiger Multicast-Betrieb | 24–72 h Ausfall-/Neustarttest bestanden |
| `1.0.0` | Dokumentierte Kompatibilität und HA-Store-Veröffentlichung | Reale Anlagenfreigabe für **Visualisierung**, keine Regelungsfreigabe |

## 11. Referenzen / Primärdokumente

1. **SMA, Energy Meter – Meter Protocol**, `EMETER-Protocol-TI-en-10` (Speedwire/OBIS, 0x6069): https://cdn.sma.de/fileadmin/content/www.developer.sma.de/docs/EMETER-Protokoll-TI-en-10.pdf
2. **SolarEdge, Inverters – SunSpec Logging**, Technical Note v3.2, Juni 2025 (SunSpec Meter 1/2, Skalierung, Registeradressen): https://knowledge-center.solaredge.com/sites/kc/files/sunspec-implementation-technical-note.pdf
3. **SMA, Sunny Tripower 8.0 / 10.0 – Interfaces and Functions:** https://manuals.sma.de/STP8-10-3AV-40/en-US/391139595.html
4. **SMA, Messwerte am Netzanschlusspunkt einstellen** (Hinweis zu 200-ms-Regelungsanforderungen): https://manuals.sma.de/ZeroFeedIn-PL/de-DE/15421387659.html
5. **Home Assistant Developers, Create/Share an App Repository:** https://contributors.home-assistant.io/apps/guides/repository/

---

**Ist-Zustand:** Eine lauffähig strukturierte **experimentelle Repository-Vorlage** inklusive Python-MVP und automatisierten Offline-Tests wurde erstellt. **Nicht behauptet** werden: echter Test am Modbus-Proxy, Test der SMA-Kompatibilität, Installation in Home Assistant oder Veröffentlichung auf GitHub. Die voreingestellte Netzübertragung ist bewusst abgeschaltet.