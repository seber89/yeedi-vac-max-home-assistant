# Yeedi Vac Max für Home Assistant

**0.2.0-alpha.2 — Etappe 2, Experimental native room cleaning. Noch nicht gemergt.**

Unofficial community integration for Home Assistant.
Not affiliated with, maintained by, or endorsed by Yeedi,
Ecovacs or Home Assistant.

## Etappe 2: native Raumreinigung (experimentell)

Räume stammen ausschließlich aus der aktiven Yeedi-Karte. Ein oder mehrere
Räume lassen sich über die native Home-Assistant-Bereichszuordnung reinigen;
Auto Clean bleibt unverändert verfügbar. Voraussetzung ist ein gültiger
Raumcache. Ohne Räume erscheint CLEAN_AREA nicht. Verwendet werden `Segment`,
`async_get_segments()` und `async_clean_segments()` aus Home Assistant 2026.9.2.
Die Mindestversion ist deshalb auf die tatsächlich geprüfte Version 2026.9.2
angehoben. [HA-Schnittstelle](https://developers.home-assistant.io/docs/core/entity/vacuum/).

In Home Assistant die vom Sauger angebotenen Segmente den gewünschten
HA-Bereichen zuordnen und die native Aktion `vacuum.clean_area` verwenden.
Mehrere ausgewählte Bereiche werden in einen Raumauftrag zusammengefasst.
Unbekannte oder leere Auswahlen werden abgelehnt, Duplikate entfernt.
Es gibt keine zusätzliche Cloud-Raumabfrage in der Vacuum-Entity.
Vor jedem Raumauftrag überprüft der Coordinator unter seinem bestehenden Lock
die aktive Karten-ID. Ein Kartenwechsel verwirft die Auswahl und lädt den Cache
neu. Gleiche Raum-IDs verschiedener Karten werden über die Segmentgruppe
unterschieden; eine alte HA-Zuordnung muss neu eingerichtet werden.

Raumaufträge verwenden dieselbe Queue, denselben Cooldown und dieselben
Bestätigungsregeln wie Basisbefehle. `cleaning` nach unklarer Antwort bestätigt
nur einen laufenden Reinigungsvorgang, **nicht die Auswahl der richtigen Räume**.
Die Raumreinigung ist noch nicht hardwarevalidiert. Zuerst einen Raum, danach
zwei und mehrere Räume beaufsichtigt testen und die Auswahl in der Yeedi-App prüfen.

Live bestätigt für alpha.1: Start, Stop, Return Home, Verbindung, Status und
Docked-Erkennung. Return Home bei bereits angedocktem Gerät wurde von Yeedi
explizit abgelehnt. Alpha.2 überspringt daher lokal: Dock bei docked/returning,
Pause bei paused, Start/Resume bei cleaning, Stop bei idle/docked. Das gilt nur
für einen erfolgreichen, online gemeldeten Status von höchstens 65 Sekunden.
Unbekannte/alte Zustände und noch nicht vollzogene Zustandswechsel nach einem
Befehl verwenden die normale Pipeline. Neue Raumaufträge werden nicht durch
den Auto-Clean-no-op blockiert. Explizite Ablehnungen bleiben Fehler.

## Etappe 1: robuste Befehle und räumliches Datenfundament

Der Besitzer hat HACS-Installation und Basissteuerung mit 0.1.0 bestätigt.
Trotz ausgeführtem Start/Stop/Dock trat gelegentlich eine Bestätigungsfehlermeldung
auf, besonders bei schnellen Klickfolgen. Die genaue Ursache ist nicht belegt.

- Pro Roboter begrenzte FIFO-Warteschlange: maximal vier laufende/wartende Aufrufe.
  Der Lock umfasst Schreiben und anschließende Statusprüfung.
- 1,5 Sekunden Ruhezeit zwischen abgeschlossenen Befehlen. Ein identischer,
  gerade bestätigter Befehl wird in diesem Zeitraum zusammengefasst.
  Start → Stop → Start bleibt in dieser Reihenfolge. Überfüllung meldet Busy.
- Keine automatischen Schreibwiederholungen. Ablehnung, Offline und HTTP 429
  bleiben Fehler. Bei unklarer Antwort oder Timeout wird einmal neu gelesen:
  Start/Resume → cleaning, Pause → paused, Stop → idle, Dock → returning/docked.
  Nur ein online gemeldetes Gerät im passenden Zustand gilt als statusbestätigt.
  Dies ist **keine direkte Gerätequittierung** und kein kausaler Nachweis, wenn
  der Roboter schon vorher im Zielzustand war. Ohne passenden Zustand bleibt
  der Ausgang unklar. Saugleistung erhält keine solche Aktivitätsbestätigung.
- Ein fehlgeschlagener Bestätigungs-Refresh macht die Integration nicht allein
  deshalb unavailable. Vor erneutem manuellem Senden den Roboter prüfen.

`map_data.py` enthält unveränderliche Modelle; `client.py` liest das V1-Protokoll;
`coordinator.py` hält Basisstatus, SpatialState und CommandState je Roboter.
Basisstatus und Position: ungefähr alle 60 Sekunden. Karte/Räume: erster
Online-Poll nach Setup/Reload, danach stündlich oder gezielt über den internen
Hook `async_refresh_map_data(robot)` (noch kein HA-Service).
Nur eine eindeutig aktive reale Karte wird ausgewählt. Raum-IDs stammen aus
`mssid`; Namen bleiben erhalten, sonst Raum A/B/C. Unbekannte/komprimierte
Grenzen bleiben `polygon=None`. Bei optionalen Fehlern bleibt Basissteuerung
erhalten; Cache-Gültigkeitsflags verhindern später die Verwendung alter Räume.

Etappe 2 ergänzt CLEAN_AREA; weiterhin **keine ImageEntity oder SVG-Karte**.
Position und Geometrie bleiben intern. Keine räumlichen Daten, Namen,
Kennungen oder Rohantworten in Logs/Diagnostics; Diagnostics enthält nur Flags
und statische Integrationsinformationen. Neue Funktionen noch live zu testen.

### Alpha testen und zurückwechseln

Nur `feature/rooms-position-map` enthält diese Alpha. `main` bleibt bei 0.1.0.
Für einen bewussten manuellen Test den Feature-Branch als ZIP herunterladen,
den bestehenden Integrationsordner sichern, `custom_components/yeedi_vac_max`
ersetzen und Home Assistant neu starten. Für Rollback den gesicherten Ordner
wiederherstellen und neu starten. [Quellenhinweise](THIRD_PARTY_NOTICES.md).

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
| Mindestversion laut HACS | 2026.9.2; native Segment-API geprüft |

Firmware wird nicht als angeblich gemessener Wert in die Geräte-Registry eingetragen. Wassermenge, Verbrauchsmaterialien, Reinigungsstatistiken und Kartenvisualisierung sind noch nicht implementiert. Raumreinigung ist experimentell; Position und Geometrie bleiben internes Datenfundament.

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

Installation und Basissteuerung wurden bis 0.2.0-alpha.1 vom Besitzer bestätigt. Das Repository ist nicht Bestandteil des Standardkatalogs. Auf diesem Feature-Branch ist die Manifest-Version 0.2.0-alpha.2; der Pre-Release dient dem bewussten Hardwaretest. main bleibt unverändert.

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
