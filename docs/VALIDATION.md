# Prüfprotokoll — 16. September 2026

Stand 0.2.0-alpha.5 auf feature/rooms-position-map; kein Merge nach main.

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
