# Yeedi Vac Max für Home Assistant

**0.2.0-beta.3 — Experimental / Beta / Hardware-Test: MapSubSet-msid. Noch nicht gemergt.**

## Beta 3: belegte MapSet-msid an Raumdetails weiterreichen

Beta 2 zeigt für beide Räume einen leeren value-String, nicht etwa einen belegten
unbekannten Codec. GetMapSet liefert eine msid. Beta 3 validiert diese mit dem
bestehenden identifier()-Helper und sendet sie, sofern gültig, zusätzlich bei
jedem regulären getMapSubSet dieses MapSets. Ohne gültige msid bleibt der bisherige
Request unverändert. Keine erfundene ID und keine weiteren neuen Felder.
Die öffentliche V1-Protokollinformation stammt aus dem Auftrag; kein fremder Code
wurde übernommen. Parser, Formatdiagnose, Queue, Raumreinigung, Lifecycle und
SVG bleiben unverändert. Nichtleere Werte laufen durch den bestehenden Parser;
leere/unverständliche Werte ergeben weiterhin keine erfundene Geometrie.

**Hardwaretest:** Beta 3 über HACS installieren, Home Assistant vollständig neu
starten, den räumlichen Refresh abwarten und prüfen, ob
`image.wohnzimmer_robbi_map` verfügbar wird. Danach Diagnose herunterladen und
bereitstellen; keine Rohantworten/IDs/Koordinaten. Noch kein Saugtest erforderlich.
Der Erfolg dieses Request-Fixes am echten Gerät ist noch nicht bestätigt.

## Beta 2: privacy-safe Raumgeometrie-Formatdiagnose

Echter Beta-1-Befund: aktive Map und Räume sind gültig, Segmentreinigung funktioniert,
aber `has_room_polygons=false`. Die akzeptierten MapSubSet-Antworten enthalten
`value` als String ohne `compress`. Der vorhandene Polygonparser versteht diese
Strings nicht. Beta 2 ergänzt ausschließlich eine lokale Formatdiagnose,
**keinen Decoder und keine neue Kartenfunktion**.

Nach Installation über HACS Home Assistant neu starten und eine neue Diagnose
herunterladen. Kein Saugtest erforderlich. `room_geometry_probe` enthält je Roboter
eine anonyme Zusammenfassung des letzten begonnenen Room-Reads, ohne IDs/Namen:
`value_count`, `polygon_count`, `all_same_shape`, `formats` mit je `count` und `format`.
Gezählt werden passend zugeordnete akzeptierte MapSubSet-Antworten, auch wenn deren
value-Feld fehlt oder unerwartet typisiert ist. Bei einem abgebrochenen Refresh
kann die Zusammenfassung unvollständig sein; sie ist kein Nachweis gültiger Rooms.
Der nächste Room-Read setzt die Probe zurück; Entladen löscht sie aus dem Speicher.

Klassifikationen enthalten nur Präsenz/Typ, Leerstring, grobe Längenklasse,
ASCII-/Whitespace-/Trennzeichenflags, JSON-Gültigkeit und obersten JSON-Typ,
V1-XY-Syntax sowie Base64-/Hex-Zeichensatzflags und Teilbarkeit der Länge durch vier.
Gleiche Klassifikationen werden dedupliziert. Keine Inhalte, exakten Längen,
Prefixes/Suffixes, Hashes, IDs, Namen oder Koordinaten. Base64-/Hex-Flags beweisen
**keinen Codec**; es wird nichts daraus dekodiert, dekomprimiert oder interpretiert.
MajorMap.value wird nicht untersucht. Parser, Requests, Raumreinigung, Lifecycle,
Image-Entity, SVG-Renderer und Geräteidentität bleiben unverändert.

## Beta 1: lokale Kartenansicht und sichere Raumzuordnung

Der Besitzer hat mit Alpha 6 die Legacy-Map-Erkennung und native Segmentreinigung
auf dem echten Vac Max bestätigt. GetMapSet liefert zunächst mssid-Einträge;
der bestehende reguläre GetMapSubSet-Ablauf liefert Raumdetails mit value als String.
Die **Darstellbarkeit dieser echten Strings als Polygone ist noch nicht bestätigt**.
Der unveränderte eigenständige Parser akzeptiert ausschließlich unkomprimierte
V1-Punktlisten oder explizite JSON-Paare. Keine neuen Decoder, keine Rasterkarte.

Pro Roboter kommt eine Image-Entity **Map** hinzu. Sie zeichnet gültige Raumpolygone
mit Namen sowie vorhandene Roboter-/Dockpositionen als lokale SVG-Karte.
Fehlende Marker verhindern die Karte nicht. Ohne gültige Geometrie oder bei
ungültigen/veralteten Map-/Room-Daten ist die Entity **nicht verfügbar**; ein altes
Bild wird auch beim direkten Bildabruf nicht als aktuelle Karte ausgeliefert.
Die Image-Entity fragt niemals die Cloud ab. Der SVG-Cache liegt nur im Speicher.
Keine offiziellen Logos, Fremdbilder oder externen Ressourcen.

Beispiel für die Standard-[Picture-Entity-Karte](https://www.home-assistant.io/dashboards/picture-entity/)
(Entity-ID durch die eigene Map-Entity ersetzen):

```yaml
type: picture-entity
entity: image.robbi_map
show_name: true
show_state: false
fit_mode: contain
```

Die öffentliche [ImageEntity-API](https://developers.home-assistant.io/docs/core/entity/image/)
wurde gegen Home Assistant 2026.9.2 geprüft. Es ist keine Custom-Dashboardkarte nötig.
Raumreinigung für einen oder mehrere Räume bleibt separat über die nativen
HA-Bereichszuordnungen verfügbar; die Bildkarte selbst ist keine Raum-Auswahlsteuerung.

Die Integration folgt genau der aktuell von Yeedi gemeldeten Major-Map,
ohne parallele Etagenauswahl. Kartenwechsel und geänderte Raum-IDs werden beim
nächsten erfolgreichen räumlichen Refresh automatisch übernommen. Der Erfolgscache
bleibt eine Stunde gültig; Fehler verwenden weiterhin drei Minuten Backoff.
Vor **jedem Raumauftrag** werden unter dem bestehenden Lock zusätzlich Map und
Raumstruktur frisch geprüft. Das kann insbesondere beim Legacy-Pfad dauern.
Bei Änderungen zwischen Auswahl und Ausführung wird **kein Schreibbefehl** gesendet.
HA meldet geänderte Segmente; die Bereiche müssen gegebenenfalls neu zugeordnet werden.
Keine automatische Zuordnung anhand von Lage oder Reihenfolge. Identische Room-IDs
in anderer Antwortreihenfolge ändern die lokale strukturelle Generation nicht.

Reload/Neustart beginnen ohne räumlichen Cache. Nach vollständiger Neukopplung
kann eine neue Yeedi-Geräte-ID ein neues HA-Gerät ergeben; keine Identitätsmigration.
Diagnostics enthalten nur Strukturangaben und Flags (einschließlich
`has_room_polygons`), niemals SVG, Namen, IDs, Koordinaten oder lokale Fingerprints.
Die Karte zeigt naturgemäß Raumgeometrie und Namen im eigenen HA-Dashboard:
Screenshots/Bilder nicht unbedacht öffentlich teilen.

**Hardwaretest Beta 1:** über HACS die Vorabversion installieren, HA neu starten,
Map-Entity und Segmentreinigung prüfen. Bei nicht verfügbarer Karte zuerst das
Flag `has_room_polygons` ansehen, keine Rohwerte veröffentlichen. Neue Karte und
geänderte Raumaufteilung testen; alte HA-Zuordnungen dürfen nicht ausgeführt werden.
Beta-Renderer und Lifecycle sind automatisiert getestet, noch nicht hardwarevalidiert.

Die folgenden Alpha-Abschnitte sind historische Zwischenstände; der obige
Alpha-6-Hardwarebefund ersetzt deren damaligen Hinweis auf ausstehende Raumtests.

## Alpha 6: belegte Major-Map-ID nutzen

Der Besitzer bestätigt mit Alpha 5 erfolgreiche Antworten von getMapState
(data.state string) und getMajorMap (data.mid string, data.value string), während
getCachedMapInfo timeoutet. Alpha 6 nutzt deshalb zentral in client.maps() nach
einem CommandTimeout den bestehenden sequenziellen Legacy-Pfad. Ausschließlich
die gültige, nichtleere, von "0" verschiedene String-ID aus resp.body.data.mid
wird als einzelne aktuelle Map übernommen (name=None, active=True).
state wird nicht interpretiert; value nicht dekodiert, dekomprimiert oder gespeichert.
Der Kandidat ist noch kein Beleg für funktionierende Räume.

Polling und Raumkommando-Mapvalidierung verwenden dieselbe Discovery. Danach
läuft im selben Refresh der vorhandene getMapSet(mid, type="ar")-Ablauf weiter.
Room-Parser und reguläre Bedingungen für getMapSubSet bleiben unverändert;
keine zusätzlichen Diagnoseabfragen. Bei Room-Fehler bleibt die Map gültig,
rooms_valid=false und keine Räume werden exponiert. Die Strukturdiagnose ergänzt
nur Präsenz/Typ von mssid/name/subtype/value/compress des ersten Subsets.

Budget: CachedMapInfo weiterhin 40s, Legacy-Reads je maximal 18s ohne Retry;
die gesamte Discovery ist auf 77s begrenzt. Room-Refresh erhält separat 40s
für getMapSet **und** optionale Subsets zusammen, keine unbegrenzte Detail-Schleife.
Der erste MapSet-Read kann damit sein 31s-Retry-Budget abschließen. Bei langsamen
Details kann der Room-Refresh trotzdem begrenzt fehlschlagen. Backoff bleibt 180s,
Erfolgscache 3600s. Der vorhandene Lock kann Steuerbefehle während der Discovery
und Room-Abfragen warten lassen. Keine neue Command-Pipeline oder Write-Retries.

Nach HACS-Update/HA-Neustart bitte nur die Diagnose-Struktur und Statusflags prüfen:
Map erkannt, aber Räume fehlen, ist nun ausdrücklich darstellbar. Echte getMapSet-
Antworten und Raumreinigung mit Alpha 6 sind noch nicht hardwarevalidiert.

Die folgenden Alpha-Abschnitte dokumentieren die vorherigen Zwischenstände.

## Alpha 5: ausschließlich Legacy-Strukturprobe

Alpha 4 meldet einen vollständigen Client-Timeout für getCachedMapInfo ohne
empfangene Antwort. Nur nach diesem Timeout beim regulären/gezielten Map-Refresh
werden getMapState und getMajorMap nacheinander ohne Zusatzparameter gelesen.
Jeweils ein HTTP-Versuch (15 Sekunden), separat maximal 18 Sekunden einschließlich
Authentifizierung/Wartezeit. Keine Wiederholung dieser Legacy-Reads. Bei Offline,
Rate-Limit oder Authentifizierungsfehler endet die Probe. Abbruch von HA wird
weitergereicht. Kein Fallback bei Parserfehlern, Ablehnung oder äußerem Timeout.

Antworten werden nur strukturell diagnostiziert, nicht als Map-/Raumcache übernommen.
Keine neue Raumabfrage, keine Karte erfunden. getCachedMapInfo behält sein Budget;
der Drei-Minuten-Fehler-Backoff beginnt nach Abschluss der Probe. Die bestehende
Serialisierung bleibt erhalten: die Probe kann wartende Befehle zusätzlich um
bis zu 36 Sekunden verzögern. Normale Vacuum-Schreibbefehle und ihr
Bestätigungsablauf lösen keine Legacy-Probe aus. getPos und alle Parser unverändert.

Nach HACS-Update/HA-Neustart nur structure_probe aus der Diagnose bereitstellen,
insbesondere getMapState/getMajorMap. Keine Rohantworten oder Map-Daten senden.
Echte Hardwareantworten dieser Befehle stehen noch aus. Kein Step 3.

## Alpha 4: konsistentes Map-Zeitbudget

Die echte Alpha-3-Diagnose meldet bei getCachedMapInfo einen Abbruch ohne
empfangene Antwort. Das bisherige äußere 20-Sekunden-Budget konnte den zweiten
Leseversuch unterbrechen (2 × 15 Sekunden + 1 Sekunde Pause). Map-Metadaten
erhalten jetzt separat 40 Sekunden, auch beim Map-Check vor Raumreinigung.
Das umfasst 31 Sekunden HTTP-Retry-Budget plus 9 Sekunden Reserve; lange erneute
Authentifizierung oder Ressourcenkonkurrenz können weiterhin das Budget erschöpfen.
Optionale Raum-/Detailabfragen behalten separat ihr bisheriges 20-Sekunden-Limit.
Die Serialisierung bleibt erhalten: eine laufende Map-Abfrage kann deshalb
nachfolgende Steuerbefehle bis zum Ablauf ihres Budgets warten lassen.

Nach Map-/Room-Fehlern erfolgt der nächste automatische Versuch frühestens nach
180 Sekunden im normalen Polling, nicht erst nach einer Stunde. Erfolgreiche
Abfragen behalten 3600 Sekunden Cache ab Abschluss. Kein zusätzlicher Write-Retry.
Parser und Cloudparameter unverändert: reale Map-Antworten stehen weiterhin aus.
getPos ist laut Live-Diagnose unter resp.body.data erfolgreich (chargePos array,
deebotPos object). Die Diagnose ergänzt für deebotPos und chargePos[0] nur
Vorhandensein/Typ von x, y, a, invalid, niemals Werte. Positionsparser unverändert.
Nach Update HA neu starten und erneut nur structure_probe bereitstellen.

## Alpha 3: Map-/Room-Hardwarediagnose noch offen

Mit Alpha 2 bestätigt der Besitzer: online, Basissteuerung funktionsfähig,
Dockposition erkannt; keine aktive Karte, ungültige Metadaten/Räume und keine
Roboterposition. Die Ursache und die reale Map-Antwortstruktur sind damit
**noch nicht bestimmt**. Alpha 3 ist eine Diagnoseversion, kein behaupteter Map-Fix.
Map-/Room-Parser und Anfrageparameter bleiben bis zu einem Strukturbeleg unverändert.

Nach Installation von Alpha 3 Home Assistant neu starten oder die Integration
neu laden (dadurch erfolgt die Map-Abfrage ohne das stündliche Cache-Intervall).
Anschließend unter Geräte & Dienste bei der Integration die Diagnose herunterladen
und den Abschnitt `structure_probe` für die weitere Analyse bereitstellen.
**Keine Rohantworten, Debug-Traces oder Zugangsdaten senden.** Ein Vergleich im
angedockten Zustand und während einer ohnehin gewünschten Reinigung ist hilfreich;
die Diagnose selbst startet keine Reinigung.

`structure_probe` enthält pro Roboter in derselben Reihenfolge wie `robots` nur
die letzte Abfrage je festem Befehl. Erfasst werden bekannte Feldnamen, JSON-Typen,
Anzahlen und feste Ergebniskategorien; keine IDs, Namen, Koordinaten oder unbekannten
Feldnamen/Werte. Es gibt keine Diagnose-Logs, Dateien, zusätzlichen Cloudaufrufe
oder automatische Übermittlung. Die Daten liegen bis Reload im Speicher.
Diese temporäre Probe soll nach der Hardwareanalyse wieder entfernt werden.

`command_success` bedeutet nur, dass die bestehende Prüfung der **Leseantwort**
bestanden wurde, nicht dass Map-Parsing oder Hardwarevalidierung erfolgreich sind.
`attempted: false` bedeutet nicht abgefragt: Ohne aktive Karte bleiben insbesondere
`getMapSet` und `getMapSubSet` aus. Deren Untersuchung benötigt gegebenenfalls einen
zweiten Hardwaretest nach der belegten Map-Korrektur. Fehlendes `deebotPos` ist
zulässig; eine vorhandene Dockposition bleibt nutzbar. Basissteuerung und
Schreibvalidierung bleiben unverändert.

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
