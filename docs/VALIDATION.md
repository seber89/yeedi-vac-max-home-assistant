# Prüfprotokoll — 16. September 2026

Stand 0.2.0-alpha.2 auf feature/rooms-position-map; kein Merge nach main.

## Testumgebung

- Python 3.14.7, Home Assistant 2026.9.2, pytest 9.1.1.
- Isolierte lokale Umgebung; echte HA-Imports, kein Zugriff auf ein reales Yeedi-Konto.
- Tests verwenden ausdrücklich synthetische Cloud-Antworten; diese sind keine aufgezeichneten Belege des Zielgeräts.

## Geprüft

**109 automatisierte Tests bestanden.** Alle 70 Etappe-1-Tests unverändert aktiv;
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
