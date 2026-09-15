# Yeedi Vac Max für Home Assistant

**0.1.0 — Experimental / initial test release. Implementiert und automatisch getestet; Live-Test am DVX34 steht aus.**

Direkte Verbindung zum **bestehenden Yeedi-Konto** in Deutschland. Der Roboter bleibt in der Yeedi-App. Die Integration läuft in Home Assistant und benötigt weder Node.js noch Node-RED, n8n, einen zusätzlichen Container oder einen separaten Dienst.

## Was diese Version macht

- Config Flow mit Yeedi-Konto/E-Mail, Passwort und Land `DE`.
- Anmeldung über Yeedi-Hosts und Yeedi-App-Identität; automatische Erkennung aller `04z443` im Konto.
- Start/Fortsetzen, Pause, Stop, Rückkehr zur Ladestation.
- Status, Akku-Sensor und Verbindungssensor; Aktualisierung alle 60 Sekunden.
- Saugleistung lesen/setzen: Quiet, Normal, Max. Die Stufen stammen aus dem bekannten Vac-Max-Profil, nicht aus einer geratenen Vierstufenliste. Die Auswahl wird erst angeboten, wenn eine bekannte Saugleistung vom Gerät gelesen wurde.
- Wiederverwendung der Cloud-Tokens, erneute Anmeldung vor deren Ablauf, erneute Eingabe der Zugangsdaten bei Authentifizierungsfehlern.
- Begrenzte Wartezeiten, keine automatische Wiederholung von Steuerbefehlen und keine optimistisch erfundenen Zustände.
- Bereinigte Diagnoseinformationen ohne Konto, Tokens, Geräte-IDs oder Rohantworten.

**Ein bestandener automatischer Test beweist keine funktionierende Anmeldung am echten Konto.** Der Client implementiert das in den Referenzprojekten belegte HTTPS-Protokoll. Änderungen der Yeedi-Cloud oder abweichende Geräteantworten können weitere Anpassungen verlangen. Siehe [Protokoll und Quellen](docs/PROTOCOL.md).

## Zielgerät

| Angabe | Stand |
| --- | --- |
| Hersteller / Modell | yeedi / Yeedi Vac Max DVX34 |
| Geräteklasse / Familie | `04z443` / K781 |
| Region | Deutschland (`DE`); andere Länder werden derzeit ausdrücklich abgelehnt |
| Firmware | 1.2.9 laut Besitzer, **Live-Test damit noch ausstehend** |
| Home Assistant | Imports und Tests mit 2026.9.2, Python 3.14.7 |
| Mindestversion laut HACS | 2026.3.0; nicht separat getestet |

Firmware wird nicht als angeblich gemessener Wert in die Geräte-Registry eingetragen. Wassermenge, Verbrauchsmaterialien, Reinigungsstatistiken, Karten, Räume und Bereiche sind noch nicht implementiert.

## Installation über HACS

Das Repository muss dafür zuerst auf GitHub veröffentlicht sein. Eine lokale ZIP-Datei allein ist kein HACS-Repository.

1. HACS öffnen.
2. Menü mit den drei Punkten → **Benutzerdefinierte Repositories** (Anordnung je nach HACS-Version).
3. `https://github.com/seber89/yeedi-vac-max-home-assistant` einfügen.
4. Kategorie **Integration** auswählen und hinzufügen.
5. **Yeedi Vac Max (Experimental)** herunterladen; bei Bedarf `main` auswählen.
6. Home Assistant neu starten.
7. **Einstellungen → Geräte & Dienste → Integration hinzufügen**.
8. **Yeedi Vac Max** suchen.
9. Die Zugangsdaten des **Yeedi-Kontos**, nicht eines Ecovacs-Kontos, eingeben.
10. Land `DE` verwenden und absenden.

Der Roboter muss vorher in der Yeedi-App eingerichtet sein. Die Integration legt für jeden passenden Vac Max ein Gerät mit Vacuum-, Akku- und Verbindungseintrag an. Ein offline gemeldeter Roboter kann eingerichtet werden und wird als nicht verfügbar angezeigt.

HACS-Struktur ist lokal geprüft; eine vollständige Installation über HACS muss noch getestet werden. Das Repository ist nicht Bestandteil des Standardkatalogs. Die Manifest-Version ist 0.1.0; vom Standardbranch kann ohne GitHub-Release installiert werden.

### Manuell aus der ZIP-Datei

1. Das fertige ZIP-Paket entpacken.
2. Den enthaltenen Ordner `custom_components/yeedi_vac_max` in den Konfigurationsordner von Home Assistant kopieren, sodass `/config/custom_components/yeedi_vac_max/manifest.json` existiert.
3. Falls die alte Vorstufe installiert ist, den Ordner durch diese Version ersetzen.
4. Home Assistant neu starten und ab Schritt 7 der Anleitung fortfahren.

Hierfür reicht ein bereits vorhandener Zugang zum HA-Konfigurationsordner; es wird kein zusätzlicher Cloud-Dienst benötigt.

## Erster Live-Test

1. Prüfen, dass die normale Yeedi-App den Roboter erreicht.
2. Integration hinzufügen. Falls die Anmeldung scheitert, genaue Fehlermeldung notieren.
3. Akku und Status mit der App vergleichen (bis zu 60 Sekunden Verzögerung).
4. Roboter an einem geeigneten freien Platz testen: Start → Pause → Fortsetzen → Stop → Ladestation.
5. Saugleistung jeweils ändern und in der App prüfen.
6. HA neu starten und die Wiederverbindung prüfen.

Ein Timeout bedeutet **unklarer Ausgang**: Ein Steuerbefehl könnte beim Roboter angekommen sein, obwohl die Bestätigung fehlt. Vor erneutem Start zuerst in der App nachsehen. Keine automatischen Wiederholungen auf eine Fehlermeldung konfigurieren.

## Fehlerbehebung

- **Falsche Zugangsdaten:** Yeedi-Konto und Passwort prüfen. Keine Migration vornehmen.
- **Kein Vac Max gefunden:** Konto und Klasse prüfen; nur `04z443` wird angelegt.
- **Cloud nicht erreichbar:** später erneut versuchen; VPN, DNS und Internetverbindung prüfen.
- **Zusätzliche Geräteverifizierung (1013):** dafür gibt es noch keinen implementierten Bestätigungscode-Ablauf. Die Einrichtung meldet diese Grenze ausdrücklich. Nicht wiederholt Passwörter ausprobieren; Fehler ohne Geheimnisse melden.
- **Roboter offline:** Stromversorgung und Verbindung in der Yeedi-App prüfen.
- **Saugleistung fehlt:** `getSpeed` wurde nicht erfolgreich oder mit unbekanntem Wert beantwortet. Es werden dann keine Stufen angeboten.
- **Unbekannte API-Antwort / Befehl nicht bestätigt:** Debug-Logging einschalten und bereinigte Meldung melden; keine Raw-Cloud-Traces sammeln.
- **Integration nicht sichtbar:** Verzeichnis und Manifest prüfen, HA neu starten, Browser neu laden.

Protokolle: **Einstellungen → System → Protokolle**. Optional in `configuration.yaml` ergänzen:

```yaml
logger:
  logs:
    custom_components.yeedi_vac_max: debug
```

Nach Neustart den Fehler einmal reproduzieren und Debug-Logging wieder deaktivieren. Die Integration protokolliert keine Passwörter, Tokens, Cookies, Konten oder kompletten URLs. Über die Geräte-&-Dienste-Seite lassen sich Diagnoseinformationen herunterladen; auch diese sind auf unkritische Statusfelder begrenzt.

## Sicherheit und Grenzen

Zugangsdaten werden nur im Config Flow eingegeben und durch Home Assistant in dessen Konfigurationsspeicher gespeichert. **HA-Dateisystem und Backups schützen:** diese Speicherung ist kein externer Passworttresor. Tokens bleiben nur im Arbeitsspeicher. Beim Entladen wird die Sitzung beendet, ohne die gemeinsam von HA verwendete HTTP-Verbindung zu schließen.

Keine Garantie für unveränderte Cloud-APIs. Kein separates Refresh-Token-Verfahren wurde verifiziert; wie die Referenzclients erneuert diese Version abgelaufene Zugangstokens durch den Login-Ablauf. Login geschieht nicht bei jeder Statusabfrage.

## Entwicklung und Lizenz

`python scripts/validate.py` prüft Python/JSON und Struktur. Für Laufzeittests mit Python 3.14: `pip install -r requirements-test.txt`, dann `python -m pytest -q`. [Prüfprotokoll](docs/VALIDATION.md).

Die bestehende [MIT-Lizenz](LICENSE) ist unverändert. Der kleine Client wurde eigenständig anhand dokumentierter Protokollfelder implementiert; kein GPL-Bibliothekscode und kein fremdes Paket wurden kopiert. Öffentliche App-Identifikatoren und ihre Quellen stehen in [PROTOCOL.md](docs/PROTOCOL.md). Das Projektsymbol ist kein offizielles Yeedi-Logo.
