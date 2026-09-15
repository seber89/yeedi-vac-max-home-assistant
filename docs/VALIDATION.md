# Prüfprotokoll — 15. September 2026

Aktueller Stand nach Umsetzung des direkten Clients.

## Testumgebung

- Python 3.14.7, Home Assistant 2026.9.2, pytest 9.1.1.
- Isolierte lokale Umgebung; echte HA-Imports, kein Zugriff auf ein reales Yeedi-Konto.
- Tests verwenden ausdrücklich synthetische Cloud-Antworten; diese sind keine aufgezeichneten Belege des Zielgeräts.

## Geprüft

**34 automatisierte Tests bestanden.** Reale HA-Imports sind erfolgreich; ein HA-internes DeprecationWarning bleibt ohne Testfehler.

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

- Installation über HACS in der echten Home-Assistant-Instanz.
- Login am echten Yeedi-Konto, Firmware 1.2.9 und sämtliche physische Befehle.
- Langzeitbetrieb und Tokenablauf.
- Region außerhalb DE ist nicht unterstützt; Verifizierungscode-Ablauf 1013 ist nicht implementiert.

Ein automatischer Test beweist, dass der Code mit den modellierten Antworten arbeitet. Er beweist nicht, dass die Cloud heute exakt diese Antworten liefert.

Reproduzieren: Python 3.14, `pip install -r requirements-test.txt`, `python -m pytest -q`, `python scripts/validate.py`. Home Assistant selbst verursacht derzeit eine DeprecationWarning zur aiohttp-Application-Unterklasse; die Integrationsimporte funktionieren.
