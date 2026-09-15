# Prüfprotokoll — 15. September 2026

## Bestanden

- Alle fünf Python-Dateien mit Python 3.12.14 kompiliert (Syntaxprüfung ohne Ausführung).
- Alle fünf JSON-Dateien geparst, doppelte Schlüssel ausgeschlossen.
- Domain, Version 0.1.0, HACS-Metadaten, genau ein Integrationsordner und vorhandenes PNG-Projektsymbol geprüft.
- Englische Übersetzung identisch mit `strings.json`, deutsche und englische Abbruchschlüssel konsistent.
- `git diff --check` ohne Fehler; bestehende MIT-Lizenz unverändert.
- Quelltextprüfung: Config Flow beendet Einrichtung mit erklärtem Abbruch; keine Speicherung, Netzwerkanfragen oder Task-Erstellung. Auch manuell eingefügte Config Entries werden abgewiesen.

## Grenzen

Die lokale Umgebung enthält Python 3.12, kein aktuelles Home Assistant (2026 benötigt eine neuere Python-Laufzeit). Es wurden daher **keine echten HA-Imports oder HA-Laufzeittests** durchgeführt. Verwendete Symbole wurden mit der aktuellen HA-Dokumentation bzw. dem Core-Quelltext abgeglichen. Das ist kein Ersatz für einen Laufzeittest.

HACS-Installation, Übersetzungsanzeige, Setup/Unload in einer realen Instanz sowie alle Yeedi-Cloud- und Gerätetests stehen aus. Es wurde weder ein Konto verwendet noch Firmware 1.2.9 getestet. Status-/Fan-Speed-Mappingtests entfallen, weil kein solches Mapping implementiert ist.

Reproduzieren: `python scripts/validate.py`. Die HACS-Dateistruktur wurde lokal geprüft, nicht mit dem vollständigen HACS-Validator zertifiziert. Die Grafik lässt sich bei Bedarf mit `python scripts/create_icon.py` (Pillow erforderlich) neu erzeugen; Pillow ist keine Laufzeitabhängigkeit der Integration.
