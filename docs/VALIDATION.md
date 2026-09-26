# Prüfprotokoll — 19. September 2026

Stand 0.2.0-rc.6 auf feature/rooms-position-map; kein Merge nach main.

## RC6 — 26. September 2026

503 Tests: alle 457 RC5-Fälle plus 46 neue synthetische Bootstrapfälle.
Nur RC1-Versions-/Diagnose-Top-Level-Erwartungen angepasst; RC5-Persistenz,
Room-, Control- und Overlaytests unverändert. Prüfung: direkter Erfolg ohne
Write, strikt identische Cached-Map vor/nach Write, mehrdeutige/ungültige IDs,
keine Legacy-Ersatzfreigabe, ACK/Reject/Timeout/Uncertain/RateLimit,
Transport ohne Write-Retry, Cancellation ohne Wiederholung, bestehende
Command-Sperre mit gleichzeitig wartendem Steuerbefehl, einmaliger zweiter
Build mit Persistenz oder normalem Backoff, vorhandene gute Caches und Privacy.
Validate: 39 Python / 5 JSON. Compile-/Import-/Manifestprüfung erfolgreich.
Eine externe HA/aiohttp-DeprecationWarning. Kein RC6-Hardwaretest ausgeführt.
Bei weiterem getCachedMapInfo-Timeout bleibt der Write bewusst gesperrt.

## RC5 — 25. September 2026

457 Tests bestanden (412 bestehende Fälle plus 45 neue). Keine deaktivierten
Tests. Angepasst sind ausschließlich widersprechende alte Erwartungen:
Bildablauf/Generationfehler, Charging-vor-Alert, neue Activity-Allowlist und
Setup-Storage-Mock sowie Versionsangabe. Steuerungs-/Room- und Overlaytests
bleiben erhalten. Echte HA-Store-Schreib-/Ladevorgänge mit synthetischen PNGs
prüfen Neustartfallback, private atomare Speicherung, keine sensitiven Felder,
Nullpixel/Timeout/Cloud-/Generationfehler, ungültige Metadaten, Alter,
Docking-Einmalabruf, Map-ID-Wechsel, aktive Zustände, defekten Storage,
Schreibfehler, unveränderte PNGs und frühe Image-Bereitstellung vor Cloud-Refresh.
Validate: 38 Python / 5 JSON. Compile-/Import-/Manifestprüfung erfolgreich.
Eine externe HA/aiohttp-DeprecationWarning. Keine RC5-Hardwarebestätigung;
mehrtägiger Hardwaretest erforderlich.

## RC4

412 Tests bestanden: 384 bisherige Fälle plus 28 neue. Eine RC3-Overlayfixture
wurde von ungeprüfter fester Nullrotation auf eindeutig asymmetrische Geometrie
umgestellt; ihre Bild-/Dock-/Cache-Prüfungen bleiben bestehen. Keine Tests
deaktiviert; Steuerungs-/Raumtests unverändert.
Neue Fälle: drei aktive Zustände, Erstladen ohne Hintergrund, einmalige
Docking-Flanke mit Erfolg/Fehler und atomarem Austausch, initial docked,
vier Drehungen bei drei Auflösungen, jeder eindeutig auswählbare Winkel,
Kandidaten über Updates, Löcher im Raster, Mehrdeutigkeit/Widerspruch,
Dock-Randtoleranz, unabhängige Marker, Generation-Reset und Privacy.
Validate PASS: 36 Python / 5 JSON. Compile-/Import-/Manifestcheck PASS.
Eine externe HA/aiohttp-DeprecationWarning. Kein RC4-Hardwaretest ausgeführt.

## RC3

384 Tests bestanden: 364 bisherige und 20 neue synthetische Overlayfälle.
Beta-6.4-Bildtest an erlaubte SVG-Hülle angepasst; eingebettetes PNG wird
weiterhin bytegleich und jede Rasterfarbe geprüft. Keine Tests deaktiviert.
Mittelpunkt, X/Y-Richtung, vier Auflösungen, Crop/Padding/Scale, immutable
Geometrie, Positions-/Dockupdates ohne erneute Assembly, fehlende/ungültige/
außerhalb liegende Positionen, Privacy und bestehende Kontrollpfade geprüft.
validate.py: 35 Python / 5 JSON. Compile-/Import-/Manifestcheck erfolgreich.
Eine externe HA/aiohttp-DeprecationWarning. RC3-Overlay-Hardwaretest steht aus.

## RC2 — 20. September 2026

364 Tests bestanden: alle 346 RC1-Fälle plus 18 neue Vorbereitungsregressionen.
Ältere Alpha-6-Fixture isoliert den neuen Vorbereitungsschritt; ihre bisherigen
Discovery-/Room-Assertions bleiben erhalten. RC1-Versionserwartung aktualisiert.
Keine Tests deaktiviert. Eine externe HA/aiohttp-DeprecationWarning.

Geprüft: validierte ID, exaktes Read-Payload, begrenztes 40s-Budget,
Cancellation, Reihenfolge getMapInfo vor Raw-Load, keine Abfrage bei fehlender
Map oder gecachtem Poll, Fehlerisolation für Räume/Steuerung und keine privaten
Diagnosewerte. Bestehende RC1-Sicherheits-/Cleanup-Tests unverändert wirksam.
validate.py PASS: 33 Python / 5 JSON. Compile-/Import-/Manifestcheck PASS.
Runtime-Diff: nur prepare_raw_map plus Aufruf vor _raw_refresh und Versionswerte.
Decoder, Renderer, Cache, Image und Vacuum-/Raumkommandoimplementierung unverändert.
Keine MQTT-Verbindung, TLS-Ausnahme oder Forschungsdiagnose wieder eingeführt.
RC2-Hardwarebestätigung steht aus; kein echter Roboter während Entwicklung bedient.

## RC1

346 Tests bestanden. 331 relevante bestehende Tests bleiben nach Entfernung
von 233 reinen Forschungsdiagnosefällen erhalten; 15 neue Cleanup-Fälle
prüfen entfernte Module/Imports, TLS-/MQTT-Abwesenheit, kompakte Allowlist,
manipulierte Diagnosedaten, primären Decoder und Read-only-Sicherheit.
Der Setup-/Unload-Test verbietet zusätzlich neue Hintergrundtasks.
Keine relevanten Funktionstests deaktiviert.

validate.py: PASS, 32 Python / 5 JSON. Compilecheck und Import sämtlicher
Integrationsmodule: PASS. Manifest ohne zusätzliche Runtime-Abhängigkeit.
AST-Importscan: keine unbenutzten Runtime-Imports. Runtime-Suche: keine
MQTT-/Forschungsdiagnose-Imports oder absichtlich unsichere TLS-Ausnahmen.
Die historische Methode probe_legacy_maps bleibt funktionale Map-Discovery,
kein Diagnoselauf. Deren Timeout-/Fallback-Tests bleiben erhalten.

AST-Vergleich mit Beta 6.4: parse_major, decode_piece, assemble, render_png,
_display_raster und _encode_png unverändert. Vacuum, Image, Datenmodelle,
SVG-Renderer, Config Flow und Konstantendatei byteinhaltlich unverändert.
Coordinator-Diff entfernt ausschließlich den optionalen getMapInfo-Probeaufruf.
Bestehende Tests für Generation, Zwei-Worker-Limit, PNG, Crop/Zoom, Cache,
Reload, last-valid-map, Räume und Befehle grün.
Eine externe HA/aiohttp-DeprecationWarning bleibt.

Beta-6.4-Hardwareerfolg laut Besitzer dokumentiert; kein echter Roboter während
dieses Cleanups bedient. Abschließender RC-Smoke-Test noch erforderlich.
Entfernte Forschungsdateien bleiben in der Git-Historie wiederherstellbar.
Ältere Abschnitte unten beschreiben ausschließlich die damaligen Stände.

## Beta 6.4

564 Tests bestanden: alle 530 bisherigen plus 34 neue synthetische Fälle.
validate.py: PASS, 42 Python / 5 JSON. Compile-/Import- und Manifestprüfung PASS.
Crop in der Mitte und an Kanten, symmetrisches Padding, Translation-Invarianz,
Zoom-/Ausgabegrenzen, dünne/langgezogene Geometrie, alle vorhandenen Renderfarben,
Null-/Fehlerraster, PNG-Chunk-CRCs und jede vergrößerte Originalzelle geprüft.
Raw-Image bleibt ohne Polygone/Positionen verfügbar; keine geratenen Overlays.
Reload-Test lädt eine neue valide Karte in frischen State; es wird ausdrücklich
keine Disk-Persistenz behauptet. Bestehende dreiminütige Fehlerfrist und Map-ID-
Schutz bleiben getestet. Eine externe HA/aiohttp-DeprecationWarning.
Synthetische PNG-Vorschau visuell geprüft. Kein echter Roboter bedient; neue
Darstellung muss noch auf Hardware bestätigt werden. Keine Tests deaktiviert.

## Beta 6.3

530 Tests bestanden: alle 446 bisherigen plus 84 neue synthetische Fälle.
validate.py: PASS, 41 Python / 5 JSON. Compile-/Import- und Manifestprüfung PASS.
Geprüft: fester EU-Broker/TLS 443, isolierter SSLContext, unveränderte normale
Zertifikatsprüfung, sessionbasierte Identität ohne Login, ATR-Komposition und
Topic-Injection-Schutz, MQTT-Level 4 / QoS 0 / Clean Session, CONNACK/SUBACK,
Ablehnung, Größenlimits/Framing, getrennte Null-/Nonzero-/Distinct-Klassifikation,
privacy-safe Export, Abbruch während Connect/CONNACK/Empfang, Reader-Task-Cleanup,
Socket-Abbruch bei Cleanup-Fehlern, reale HA-Shutdown-Taskbindung, kein Reconnect
oder Publish, unveränderter Coordinator bei MQTT-Fehlern. Kein Test deaktiviert.
Eine externe HA/aiohttp-DeprecationWarning. Kein echter MQTT-Login im lokalen Test;
Hardwarevalidierung steht aus. Keine neuen Runtime-Abhängigkeiten im Manifest.

## Beta 6.2

446 Tests bestanden: alle 415 bisherigen plus 31 neue synthetische Fälle.
validate.py: PASS, 37 Python / 5 JSON. Compile-/Import- und Manifestprüfung PASS.
Geprüft: unterschiedliche CRC-/Sentinel-/Nullstrukturen, leere Mengen, gleiche und
unterschiedliche decodierte/encodierte Inhalte, transienter Fingerprint-Cleanup,
LZMA1-Raw-Gegencheck für Null-/Nonzero-Daten, tatsächliche Abweichung vom primären
Ergebnis, Properties-/Dictionary-/Output-/Input-Limits, maximal ein Gegencheck,
keine zusätzlichen Requests, Cache-only ohne Gegencheck, Fehlerisolation sowie
strikt allowlisteter Export ohne IDs/Hashes/Inhalte. Keine alten Tests deaktiviert.
Eine externe HA/aiohttp-DeprecationWarning. Hardwarediagnose steht noch aus.

## Beta 6.1

415 Tests bestanden: alle bisherigen 374 plus 41 neue synthetische Fälle.
validate.py: PASS, 35 Python / 5 JSON. Compile-/Import- und Manifestprüfung PASS.
Eine externe HA/aiohttp-DeprecationWarning; keine Tests deaktiviert.
Geprüft: 1/2/3 unverändert, 4, 5–10 und >10 sichtbar und Crop-relevant,
Nullraster, Generationswechsel bei ID/Dimensionen/CRC-Liste, unveränderte zweite
Prüfung, präzise Stage-Flags, Assembly-/PNG-Fehlerinjektion, alle Pixel-Buckets,
Privacy und Diagnose des aktuellen Fehlers trotz vorherigem Cache-Bild.
Neue Palette/Finalisierung auf echter Hardware noch nicht bestätigt.

## Beta 6

374 Tests bestanden (316 bisherige + 58 neue synthetische Fälle). validate.py:
PASS, 34 Python / 5 JSON. Eine externe HA/aiohttp-DeprecationWarning.
Geprüft: Major-Grenzen/Typen, Sentinel, striktes Base64/Legacy-LZMA, Output- und
Dictionary-Limits, fehlende/überschüssige/trunkierte Daten, Piece-Identität,
spaltenweise Rasteranordnung mit asymmetrischen eigenen Testpixeln, PNG-Chunks
und Checksummen, vollständige Veröffentlichung, maximal zwei aktive Requests,
alle benötigten Pieces, Cache-Wiederverwendung, nur geänderte Pieces, neue Map-ID,
Generationswechsel während des Ladens, Deadline/Cancellation mit Worker-Cleanup,
Fehler-Grace ohne Fristverlängerung, unabhängige Basissteuerung, PNG ohne Räume
oder Position, Render-Cache, Reload, Privacy und keine automatischen Beta-5-Probes.
Alte Alpha-6-/Beta-4-Testclients isolieren den separat geprüften Raw-Loader;
keine alten Assertions oder Tests entfernt. Compile/import und Manifest zusätzlich
geprüft. Keine neue Dependency. Decoder/Bild auf Hardware noch nicht validiert.

## Beta 5

316 Tests bestanden: bisherige 279 plus 37 neue synthetische Fälle. validate.py:
PASS, 32 Python / 5 JSON. Eine externe HA/aiohttp-Warnung. Tests umfassen strenge
CRC-Listengrammatik, Empty-Piece-Sentinel, maximal zwei unterschiedliche reale
Listenpositionen, exakt erlaubte Request-Felder, gültige aktuelle Map-ID,
Map-Mismatch/fehlende Liste ohne Minor-Read, accepted/received/rejected/timeout,
Busy-Abbruch, Gesamtbudget, Cancellation, Formate ohne Decodierung und Privacy
des gesamten Diagnoseexports. Kein MQTT-Code: explizit nicht getestet/verbunden.
Vorhandener Beta-4-Testclient mockt nur den neuen, separat getesteten Zusatzpfad.
Alle bestehenden Tests bleiben aktiv. Compile-/Importcheck und Manifest-JSON
werden zusätzlich geprüft; keine neue Dependency. Hardwarebefunde Beta 5 offen.

## Beta 4

279 Tests bestanden: alle bisherigen 249 plus 30 neue synthetische Fälle.
validate.py: PASS, 30 Python / 5 JSON. Eine externe HA/aiohttp-Warnung.
Geprüft: exakt mid/type=ol, Read-only-Guard vor Netzwerk, unveränderte Read-Retry-
Einstellung ohne Proben-Retry, ungültige/fehlende/mehrdeutige Map ohne Probe,
Timeout/Reject ohne Einfluss auf gültige Rooms, keine Probe im gecachten Poll
oder normaler Raumreinigung, Probe bei erkannter Map trotz Room-Fehler,
feste Response-Pfade und Formatbuckets ohne IDs/CRC/Koordinaten/Rohdaten,
ungewöhnliche Typen und Cancellation. Alpha-6-Testclient mockt nur die neue,
hier separat getestete Probe; bestehende Assertierungen bleiben aktiv.
HardwaregetMapInfo-Antwort noch ausstehend. Kein Decoder oder Renderer ergänzt.

## Beta 3

249 Tests bestanden (alle bisherigen 231 plus 18 neue synthetische Fälle).
validate.py: PASS, 29 Python / 5 JSON. Eine externe HA/aiohttp-Warnung.
Geprüft: validierte MapSet-msid in allen regulären Detailrequests, exakte Felder,
fehlende/ungültige IDs ohne erfundenen Fallback, keine Wiederverwendung einer
vorherigen MapSet-msid, leere und unbekannte Werte ohne Polygon, bestehender
Parser für nichtleere XY-/JSON-Werte sowie Diagnose-/Log-Privacy. Keine Tests
deaktiviert, keine Parser-/Renderer-/Lifecycle-/Command-Änderungen. Hardwaretest offen.

## Beta 2

231 Tests bestanden: alle 201 bisherigen Fälle plus 30 neue synthetische Fälle.
validate.py: PASS, 28 Python / 5 JSON. Eine externe HA/aiohttp-Deprecation-Warnung.
JSON-Top-Level-Typen, XY-Syntax, Base64-/Hex-Zeichensatzflags ohne Decodierung,
Längenklassen an Grenzen, malformed/unexpected values, Deduplizierung, echte
Client-Room-Testpipeline und Diagnoseexport ohne sensible Sentinelwerte geprüft.
Keine zusätzlichen Cloudaufrufe, MajorMap-Probe unverändert, Kopierschutz und
Zurücksetzen der lokalen Formatdiagnose geprüft. Bestehende Raum-/Map-/Write-
und Renderertests bleiben aktiv. Neue Hardwarediagnose noch erforderlich,
für diesen Schritt kein Saugtest nötig.

## Beta 1

201 Tests bestanden (175 bestehende + 26 neue Fälle). validate.py: PASS,
26 Python-Dateien / 5 JSON-Dateien. Eine externe HA/aiohttp-Deprecation-Warnung.

Home Assistant 2026.9.2 / Python 3.14.7. Alle bisherigen 175 Testfälle bleiben
aktiv; Raum-Preflight-Fixtures liefern nun auch die ausdrücklich verlangten
frischen Raumdaten. Zusätzliche synthetische Tests prüfen Image-Plattform,
cloudfreie Bildabfrage, statisches SVG, dynamische/negative Bounds, Text-Escaping,
optionale Marker, Cache-Invalidierung, neue Räume bei gleicher Map-ID,
Generationsprüfung unter dem Write-Lock, HA-Mapping-Meldung und Datenschutz.
Keine echten Cloudwerte als Fixtures übernommen. Der Besitzer bestätigt
Alpha-6-Map-/Room-Erkennung und Segmentreinigung; Beta-1-SVG und Lifecycle
benötigen noch den Hardwaretest. Die folgenden Abschnitte sind historisch.

## Alpha 6

175 Tests bestanden: alle 156 bisherigen Fälle bleiben aktiv, 19 neue synthetische
Fälle. Der Alpha-5-Fallback-/Backoff-Test verwendet jetzt den echten Client mit
gemocktem Transport statt einen Coordinator-internen Fallback vorauszusetzen;
gleiche Assertions für einmalige Probe, gesperrte Räume und Backoff bleiben bestehen.
Keine Tests deaktiviert. validate.py PASS: 23 Python / 5 JSON. Eine unveränderte
externe HA/aiohttp-Deprecation-Warnung.

Neue Tests: primärer Erfolg ohne Legacy, Timeout-Fallback mit gültiger mid,
fehlende/ungültige/Null-/Zero-ID, kein Zugriff des Discovery-Parsers auf value,
gemeinsame Discovery im Room-Preflight, anschließender MapSet-Read im selben Refresh,
Room-Fehler bei gültiger Map, privacy-safe Subset-Struktur und Diagnoseexport,
keine erzwungene Detailabfrage, skalierter tatsächlicher MapSet-Read-Retry über
das alte 20s-Budget hinaus, begrenzte Discovery-/Room-Budgets, Reject ohne Fallback.
Synthetische Daten, keine echten IDs oder Map-Inhalte. Hardwaretest Alpha 6 ausstehend.

## Alpha 5

156 Tests bestanden: alle bisherigen 141 plus 15 neue synthetische Fälle.
validate.py: PASS, 22 Python / 5 JSON. Eine unveränderte externe HA/aiohttp-Warnung.
Geprüft: Fallback nur nach Client-Timeout, keine Räume aus Probe, 180s Backoff,
leere Payloads, ein Versuch je Legacy-Read, sequenzielle Ausführung, Privacy,
Fortsetzung nach Timeout/Reject, Abbruch bei Busy/Offline/Auth und HA-Cancellation,
keine Legacy-Probe bei normalen Writes, Read-only-Guard vor Netzwerkzugriff.
Echte Antworten von getMapState/getMajorMap stehen noch aus. Keine Parseränderung.

## Alpha 4

141 Tests bestanden: alle 129 bisherigen plus 12 neue synthetische Fälle.
validate.py: PASS, 21 Python-Dateien / 5 JSON-Dateien. Eine unveränderte externe
HA/aiohttp-Deprecation-Warnung. Tests prüfen das abgeleitete Budget, einen echten
Client-Read-Retry unter zeitlich skaliertem äußeren Timeout (erster Versuch Timeout,
zweiter erfolgreich), Fehler-Backoff mit erneutem Poll, langen Erfolgscache,
Raumabfragen nur bei aktiver Map und Positionsdiagnose ohne sensible Werte.
Keine Hardwareantworten als synthetische Fixtures ausgegeben. Der echte
Alpha-3-Befund steht in PROTOCOL.md; Hardwaretest von Alpha 4 noch ausstehend.

## Zwischenschritt 2.5

129 Tests bestanden: alle 109 bisherigen Fälle und 20 neue synthetische
Strukturdiagnose-/Datenschutzfälle. `python scripts/validate.py`: PASS,
20 Python-Dateien, 5 JSON-Dateien. `python -m pytest -q`: 129 passed,
eine unveränderte externe Home-Assistant/aiohttp-Deprecation-Warnung.

Neue Fälle: JSON-/Objekt-Umschläge, feste Antwortebenen ohne Parser-Fallback,
Typvarianten von using, unbekannte Schlüssel und sensible Sentinel-Werte,
Diagnoseexport ohne IDs/Namen/Koordinaten, Kopie und Löschen beim Entladen,
Offline/Busy/Transport/Timeout/Reject, Budget-Abbruch, begrenzte Listeninspektion,
fehlende Roboterposition bei vorhandener Dockposition, keine Probe von Writes.
Der Mock des Clients erhielt die neue synchrone Diagnosemethode;
bestehende Testassertionen wurden nicht entfernt oder abgeschwächt.

Kein Zugriff auf echte Cloudantworten. Der Besitzer meldet Basissteuerung und
Dockposition mit Alpha 2 als funktionierend, aber fehlende Map-/Room-Erkennung.
Die reale Map-/Room-Struktur und Ursache sind noch offen; Alpha 3 erfasst die
dafür benötigte Struktur beim nächsten Hardwarelauf. Keine Hardwarevalidierung
oder Parserkorrektur behauptet. MIT/THIRD_PARTY_NOTICES unverändert.

## Testumgebung

- Python 3.14.7, Home Assistant 2026.9.2, pytest 9.1.1.
- Isolierte lokale Umgebung; echte HA-Imports, kein Zugriff auf ein reales Yeedi-Konto.
- Tests verwenden ausdrücklich synthetische Cloud-Antworten; diese sind keine aufgezeichneten Belege des Zielgeräts.

## Geprüft

**Alpha-2-Stand: 109 automatisierte Tests bestanden.** Alle 70 Etappe-1-Tests unverändert aktiv;
39 zusätzliche synthetische Etappe-2-Fälle. Reale HA-Imports erfolgreich;
ein HA-internes DeprecationWarning bleibt ohne Testfehler.

Neu geprüft: native Segmente/IDs/Namen/CLEAN_AREA, gültiger/leerer/veralteter
Cache, einzelne/zwei/mehrere Räume, Normalisierung/Duplikate/ungültige Auswahl,
Kartenwechsel/Map-Check-Fehler/HA-Zuordnung mit wiederverwendeten IDs,
Queue/Doppelklick/wechselnde Raumaufträge, unklare Antwort und Timeout,
explizite Ablehnung, alle angeforderten no-op-Zustände, legitime Übergänge
und veraltete Statuswerte. Raumreinigung am echten Gerät noch unbestätigt.

Etappe 1 ergänzt synthetische Tests für V1-Karten/Räume/Position, unkomprimierte
Polygone, unbekannte Kompression, mehrdeutige Karten, Cache und Kartenwechsel,
optionale Fehlerisolation und Privacy-Allowlist. Befehlsfälle: direkt bestätigter
Start, unklarer Start/Resume/Pause/Stop/Dock mit passendem Status, Dock returning
und docked, unpassender/offline/unbekannter Status, explizite Ablehnung,
Rate-Limit, Timeout ohne Retry, Fehler vor dem Write, parallele Writes,
Start/Stop/Dock-Doppelklick, Start–Stop–Start, Lock bis Refresh-Ende,
begrenzte Queue und Abbruch wartender Aufrufe. Bestehende Vacuum-Funktionen geprüft.
`python scripts/validate.py`: 18 Python-Dateien, 5 JSON-Dateien bestanden.

- Protokollsignatur, Token-Wiederverwendung und konkurrierende Anmeldung.
- Yeedi-Hosts/App-Organisation, Gerätefilter, Duplikate und fehlende Geräteantworten.
- Befehlsumschlag, strikte Bestätigung schreibender Befehle, Ablehnung unbekannter Antworten.
- Status-/Saugleistungsmapping, offline versus Cloudfehler.
- Begrenzte Transportwiederholung und bereinigte Fehlermeldungen.
- Config Flow mit echten HA-Klassen, erfolgreiche Einrichtung und Auth-Fehler.
- Vacuum-, Battery- und Connectivity-Entities, Start/Fortsetzen und Fan-Speed-Befehle.
- Setup-/Unload-Funktionen mit gemocktem Cloud-/Plattformzugriff.
- Echter DataUpdateCoordinator: Aktualisierung, Auth-/Cloudfehler und bestätigte/abgelehnte Befehle.
- Python-Syntax, JSON, Übersetzungsschlüssel und HACS-Dateistruktur.
- Bestehende MIT-Lizenz unverändert.

## Noch erforderlich

- Neue Alpha am echten DVX34: Karte, Räume, Position und neue Bestätigungslogik.
- Installation und Basissteuerung von 0.1.0 wurden vom Besitzer bestätigt;
  dennoch gelegentliche Fehlermeldung trotz ausgeführtem Befehl. Daraus keine
  Live-Bestätigung für die neuen Alpha-Funktionen ableiten.
- Langzeitbetrieb und Tokenablauf.
- Region außerhalb DE ist nicht unterstützt; Verifizierungscode-Ablauf 1013 ist nicht implementiert.

Ein automatischer Test beweist, dass der Code mit den modellierten Antworten arbeitet. Er beweist nicht, dass die Cloud heute exakt diese Antworten liefert.

Reproduzieren: Python 3.14, `pip install -r requirements-test.txt`, `python -m pytest -q`, `python scripts/validate.py`. Home Assistant selbst verursacht derzeit eine DeprecationWarning zur aiohttp-Application-Unterklasse; die Integrationsimporte funktionieren.
