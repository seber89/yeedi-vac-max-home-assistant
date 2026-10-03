# Yeedi Vac Max für Home Assistant

Version **0.2.0-rc.13** — Release Candidate für 0.2.0, noch keine Stable-Version.

RC.13 ergänzt ausschließlich privacy-safe RawMap-Refresh-Diagnose: begrenzte
RAM-Zähler für Fresh-/Normalversuche, deren Ergebnisse und aktuelle
Rückhaltebedingungen. Kein Scheduling- oder Funktionsfix; 180-Sekunden-Backoff,
60-Sekunden-Coordinator und Positionspolling bleiben unverändert. Die Zähler
werden beim Unload verworfen und niemals gespeichert.

RC12 erhält eine auf echter RawMap-Geometrie eindeutig erkannte Rotation im
bestehenden privaten RAM-State derselben bestätigten Map. RC11-Fahrmarker und
deren Aktualisierung wurden vom Besitzer hardwarebestätigt. Der Dockmarker nach
frischem Kartenaufbau bleibt der Hardwaretest für RC12.

Ursache im RC11-Code: ein neues RawOverlay übernimmt Kandidaten nur bei exakt
gleicher Major-Struktur einschließlich CRC-Liste. Neue Kartengeometrie kann
behaltene Fahrpunkte erneut mehrdeutig machen; die vorherige eindeutige Rotation
war außerhalb des alten Overlay-Objekts nicht gespeichert.

RC12 verwendet die behaltene Rotation nur mit bestätigter identischer aktiver
Map und einem aktuell plausibel projizierbaren Dock als Anker. Brauchbare aktuelle
Roboterpositionen und die nichtleere gemeinsame Fahrpunkte-Evidenz dürfen ihr
nicht widersprechen. Bei Widerspruch wird sie verworfen und die bestehende
konservative Kandidatenprüfung erneut benutzt. Jeder Marker bleibt separat
geometrisch geprüft; kein Clamping oder Korrigieren gelieferter Positionen.
Ohne Dock-Anker gelten die bisherigen RC11-Regeln. Die Karte bleibt verfügbar,
auch wenn kein Marker sicher möglich ist.

Rotation und Evidenz bleiben RAM-only, werden bei bestätigtem Kartenwechsel und
Unload gelöscht und gelangen weder in Storage, Logs noch Diagnostics. SavedMap
bleibt ohne Overlay. Polling, Cloud, Decoder, Persistenz und Steuerung unverändert.

Hardwaretest RC12: installieren, HA vollständig neu starten, Ausgangsdiagnose
sichern. Normale Reinigung mit geschlossener Yeedi-App starten; nach 1–2 Minuten
bewegten blauen Marker und Diagnose prüfen. Regulär zurückfahren/andocken lassen,
ohne Neustart oder Reload dazwischen. Nach frischem RawMap-Aufbau prüfen, ob bei
vorhandener Dockposition auch ohne Roboterposition ein plausibler orangener
Dockmarker bleibt. Abschlussdiagnose sichern. RC12-Docking-Marker unbestätigt.

RC11 testet ausschließlich begrenzte Orientierungsevidenz für die vorhandenen
Roboter-/Dockmarker. RC10-Fast-Polling ist laut Besitzer auf dem Yeedi Vac Max
hardwarebestätigt: erfolgreiche getPos-Reads während Reinigung und Rückfahrt,
sauberes Ende nach beobachtetem Andocken. Die Marker-Erkennung von RC11 muss
noch auf Hardware geprüft werden.

Während beobachtetem cleaning/returning bleiben maximal 16 unterschiedliche,
valide Roboterpositionen im RAM, gebunden an die bestätigte aktive Map-ID.
Keine Winkelinterpretation, Zeitstempel, Fahrtlinie oder Speicherung auf Platte.
Die Punkte bleiben bis nach dem Andocken für eine neu geladene echte RawMap
nutzbar; bestätigter Map-Wechsel und Unload verwerfen sie.

Für jede neue RawMap-Generation werden die Punkte gegen die vorhandenen vier
Rotationen geprüft. Nur eine eindeutige gemeinsame Schnittmenge erlaubt Marker;
mehrdeutige oder widersprüchliche Evidenz erzwingt keine Rotation. Auch danach
muss jeder aktuelle Robot-/Dockmarker auf belegter Geometrie plausibel sein.
Ein reines SavedMap-PNG erhält weiterhin kein Overlay. RC11 ergänzt keine
Cloud-Abfragen; getPos bleibt bei etwa fünf Sekunden während aktiver Zustände,
der normale Coordinator bei 60 Sekunden. Diagnostics exportieren keine Evidenz.

Hardwaretest: RC11 installieren, HA vollständig neu starten, normale Reinigung
mit geschlossener Yeedi-App durchführen und regulär zurückfahren/andocken lassen.
Nach dem frischen RawMap-Aufbau prüfen, ob Robot-/Dockmarker sichtbar und
plausibel sind. Nur eine gespeicherte PNG-Karte oder weiterhin mehrdeutige
Orientierung kann weiterhin ohne Marker erscheinen. Diagnose vor Reinigung,
während Reinigung und nach dem Andocken herunterladen.

RC10 ergänzt ausschließlich Position-only Fast Polling: bei beobachtetem
`cleaning` oder `returning` etwa alle fünf Sekunden nur `getPos`.
Ein Task je Roboter, kein Fast-Read-Retry, fünf Sekunden Gesamtlimit.
Belegter Geräte-Lock oder wartende Steuerbefehle: Zyklus überspringen.
Ein bereits laufender Read kann einen neuen Befehl höchstens bis zu seinem
Timeout verzögern. Normale Positionsreads teilen den Fünf-Sekunden-Abstandscheck.
Status, Karten und Räume bleiben beim unveränderten 60-Sekunden-Coordinator.
Die bestehende Session wird wiederverwendet; kein neuer Login je Fast-Poll.

Bei beobachtetem docked/paused/idle/error/offline/unknown stoppt der Task;
Unload beendet und awaited ihn. Fehler behalten die letzte Position, mit
mindestens 15 Sekunden Pause; Rate-Limit mindestens fünf Minuten, Authfehler
setzen den Task bis zum nächsten Aktivitätszyklus aus. Normale Authbehandlung
bleibt maßgeblich. Keine Positionshistorie oder Positionspersistenz.

Ein Marker ist nur mit aktueller RawMap im RAM und eindeutiger vorhandener
Rotation projizierbar. Ein reines persistiertes Last-Good-PNG enthält dafür
keine Geometrie: Fast-Poll kann laufen, ohne dass ein Punkt angezeigt wird.
Keine Pieces/Transformationsdaten werden dafür zusätzlich gespeichert.
Kein MQTT, keine neuen Kartenabfragen, keine Overlay-/Decoderänderung.
RC10-Fast-Poll ist hardwarebestätigt; sichtbare Marker benötigen weiterhin
eine sichere RawMap-Projektion.

Hardwaretest: RC10 installieren, HA vollständig neu starten, Diagnose prüfen,
Reinigung starten und Yeedi-App geschlossen lassen. Nach 1–2 Minuten Karte
beobachten, nach 2–3 Minuten Diagnose laden. Nach beendeter Reinigung/Rückfahrt
und beobachtetem docked erneut Diagnose prüfen: Fast-Poll muss beendet sein.
Nur SavedMap vorhanden und kein Marker ist kein RC10-Fehler; bei später
erfolgreich geladener RawMap erneut testen.

RC9 ist laut Besitzer hardwaregetestet. Der Legacy-CleanLog-Pfad gilt für
dieses Gerät praktisch als negativ und wird in RC10 nicht weiterentwickelt.

RC9 korrigiert ausschließlich das belegte Yeedi-950-GetCleanLogs-Requestprofil:
Query `cv=1.94.76&t=a&av=1.3.0`, zusätzlich `country="DE"` im JSON.
RC8 erreichte auf Hardware den Portalpfad, erhielt aber `ret=ok`, `logs=[]`.
Download, TLS-Prüfung, PNG-/URL-Sicherheit, RAM-only und Backoff bleiben gleich.
Erneut angedockt testen, ohne Reinigung oder Yeedi-App-Refresh. Liefert das exakt
dokumentierte Profil wieder `ret=ok` und `logs=[]`, gilt der Legacy-CleanLog-Pfad
für dieses Gerät praktisch als negativ: keine weiteren RCs mit kleinen
GetCleanLogs-Variationen. RC9-Hardwarefunktion ist noch nicht bestätigt.

RC8 testet ausschließlich einen historischen HTTPS-Bildfallback. Wenn der normale
RawMap-Aufbau vollständig verifiziert nur Nullpixel liefert und keine gute RawMap
oder gespeicherte Last-Good-Karte existiert, wird über GetCleanLogs das neueste
brauchbare Reinigungsbild gesucht. Nur HTTPS auf portal-eu.ecouser.net unter
/api/lg/image/ ist erlaubt: keine Redirects, keine anderen Hosts, normale
TLS-Verifikation. Download und PNG werden begrenzt und strukturell validiert.
Fehlversuche haben mindestens drei Minuten Backoff; ein vorhandenes Fallback
wird nicht bei jedem Poll neu geladen. Kein automatisches setMajorMap mehr.

Das Bild ist **keine bestätigte Live-Karte**: Es kann eine frühere Raumaufteilung
oder Etage zeigen. Deshalb ausschließlich RAM, keine Last-Good-Persistenz und
keine Roboter-/Dockmarker darauf. Bei erkanntem Kartenwechsel wird es verworfen.
Priorität: echte RawMap, gespeicherte RawMap, historisches PNG, Raum-SVG.
Steuerung, Räume, Polling, Raw-Decoder/-Renderer und Raw-Overlay bleiben unverändert.
MQTT bleibt entfernt: Ein sicherer Vertrauensanker ist derzeit nicht belegt
(siehe docs/RESEARCH_SAFE_MAP_EVENTS.md). Keine TLS-Ausnahme wird eingeführt.
Der HTTPS-Fallback ist noch nicht auf dem echten Yeedi hardwarebestätigt.

Hardwaretest: RC8 installieren, HA vollständig neu starten, Roboter angedockt
lassen, keine Reinigung und keinen Yeedi-App-Refresh auslösen. Nach etwa zwei
Minuten Image-Entity prüfen und Diagnose herunterladen.

RC5 ergänzt einen privaten lokalen Last-Good-Map-Cache über Home Assistants
Storage. Gespeichert werden nur das fertig gerenderte Basis-PNG und die
versionsgebundene Karten-/Gerätezuordnung. Keine Pieces, Cloudantworten,
Positionen, Räume oder Zugangsdaten. Der Grundriss ist privat: HA-Storage
und Backups entsprechend schützen. Nach Neustart kann zunächst dieses PNG
ohne alte Positionsmarker erscheinen, während der normale Cloudabruf läuft.
Timeouts, Nullpixel, ungültige Raum-/Map-Metadaten und Cache-Alter löschen
das letzte gute Bild nicht. Eine bestätigt andere aktive Map-ID invalidiert es.
Explizites isCharging=1/"1" hat bei gleichzeitigem Cleaning-Alert Vorrang.
RC5 muss noch mehrere Tage auf echter Hardware getestet werden.

RC4 bewahrt einen bestehenden Kartenhintergrund derselben aktiven Map während
cleaning/paused/returning ohne periodischen Raw-Neubuild. Positionen werden
weiter regulär gelesen. Ein beobachteter Übergang eines bekannten, online
nicht angedockten Zustands zu docked löst einmalig einen frischen Kartenabruf
aus. Wiederholtes docked allein löst keinen weiteren Sonderabruf aus.
Ohne bekannte Karte bleibt normales Laden möglich; RC5 ergänzt den PNG-Fallback.

Marker erscheinen erst bei eindeutiger Zuordnung aus 0/90/180/270 Grad.
Die Kandidaten werden je Raw-Generation anhand belegter Rasterzellen eingegrenzt;
für das Dock ist eine Rasterzelle Randtoleranz erlaubt. Mehrdeutigkeit bedeutet
Karte ohne Marker. RC4-Lebenszyklus und Orientierung sind noch nicht auf
Hardware bestätigt.

RC3 ergänzt auf der bestätigten RC2-RawMap einen blauen Roboterkreis und
ein orangefarbenes Dockquadrat. Die Marker folgen dem vorhandenen
Positions-Polling (etwa 60 Sekunden), ohne zusätzliche Cloudabfragen.
Fehlende, ungültige oder außerhalb des sichtbaren Kartenausschnitts liegende
Positionen werden ausgelassen. Kein Richtungspfeil, keine Winkelannahme.
Die Overlay-Ausrichtung muss mit RC3 noch auf echter Hardware geprüft werden.

RC2 stellt den begrenzten read-only getMapInfo-Aufruf vor dem Raw-Map-Laden
wieder her. Dieser Ablauf war in Beta 6.4 vorhanden und wurde in RC1
irrtümlich als reine Forschungsdiagnose entfernt. Der RC1-Hardwaretest zeigte
danach vollständig dekodierte, aber leere Karten-Pieces. Ein notwendiger
Map-Warmup ist die Arbeitshypothese; RC2 muss dies auf Hardware bestätigen.
Keine MQTT-Diagnose oder TLS-Ausnahme kehrt zurück. Decoder, Darstellung,
Cache und Steuerung bleiben unverändert.

Unofficial community integration for Home Assistant.
Not affiliated with, maintained by, or endorsed by Yeedi,
Ecovacs or Home Assistant.

Direkte Integration des bestehenden Yeedi-Kontos in Deutschland.
Der Roboter bleibt in der Yeedi-App. Kein Ecovacs-Kontoumzug, Node.js,
Node-RED, n8n, Container oder zusätzlicher Dienst erforderlich.

## Funktionen und bestätigter Stand

- Start / Fortsetzen, Pause, Stop und Rückkehr zur Ladestation.
- Saugleistung Quiet / Normal / Max, sofern vom Gerät erfolgreich gelesen.
- Status, Akku und Verbindung; reguläre Aktualisierung etwa alle 60 Sekunden.
- Native Home-Assistant-Raumreinigung für einen oder mehrere zugeordnete Räume.
- Map Image Entity: Karte aus den Yeedi-MajorMap-/MinorMap-Daten,
  mit Crop, Rand und begrenzter pixelgenauer Vergrößerung.
- Kartenanzeige funktioniert unabhängig von Raum-Polygonen und Roboterposition.

Zielgerät: Yeedi Vac Max DVX34 / K781, Geräteklasse 04z443, Region DE.
Andere Länder und Geräteklassen werden nicht angeboten.
Geprüfte Home-Assistant-Version und HACS-Mindestversion: **2026.9.2**.

Der Besitzer hat mit Beta 6.4 die sichtbare, lesbare und aktualisierte Karte,
erneute Kartenverfügbarkeit nach vollständigem HA-Neustart, Stop, Pause,
Return Home und Raumreinigung auf echter Hardware bestätigt.
Start und Basisverbindung wurden bereits in früheren Hardwaretests bestätigt.
Resume und Fan Speed sind implementiert und automatisiert geprüft; dieser
RC behauptet keine zusätzliche aktuelle Hardwarevalidierung dafür.

RC1 entfernt ausschließlich temporäre Forschung: MQTT-Diagnose einschließlich
ihrer isolierten TLS-Ausnahme, zusätzliche Diagnoseabfragen und Formatproben.
Die getestete HTTPS-Kartenpipeline, Bilddarstellung und Steuerung bleiben erhalten.
Es wird keine MQTT-Verbindung aufgebaut und keine Zertifikatsprüfung deaktiviert.
Der RC benötigt noch seinen abschließenden Hardware-Smoke-Test.

## Installation mit HACS

1. Dieses Repository als benutzerdefiniertes Repository der Kategorie Integration hinzufügen:
   https://github.com/seber89/yeedi-vac-max-home-assistant
2. Pre-Releases/Beta-Versionen in HACS anzeigen lassen und gezielt
   **0.2.0-rc.13** herunterladen (nicht main).
3. Home Assistant vollständig neu starten.
4. Unter Einstellungen → Geräte & Dienste → Integration hinzufügen
   **Yeedi Vac Max** auswählen.
5. Zugangsdaten des bestehenden **Yeedi-Kontos** und Land **DE** eingeben.

Der Roboter muss bereits in der Yeedi-App eingerichtet sein. Für ein Update
keine zweite Integration anlegen. Bei manueller ZIP-Installation den Ordner
custom_components/yeedi_vac_max vollständig ersetzen, damit entfernte
Diagnosemodule nicht als alte Dateien zurückbleiben; anschließend HA neu starten.
Vorher die vorhandene Installation sichern.

## Räume und Kartenwechsel

Die Segmente stammen aus der aktuellen Yeedi-Karte. In Home Assistant die
Segmente HA-Bereichen zuordnen und die native Aktion `vacuum.clean_area`
verwenden. Ein oder mehrere Bereiche sind möglich; Auto Clean bleibt separat.
Ohne gültige Räume wird Raumreinigung nicht angeboten.

Die Integration folgt genau der aktuell gemeldeten aktiven Yeedi-Major-Map.
Karten und Räume werden beim Setup/Reload und danach regelmäßig neu geladen.
Kartenwechsel oder geänderte Raumstruktur machen alte Auswahlen ungültig.
Vor einem Raumauftrag werden Karte und Raumgeneration erneut geprüft;
gegebenenfalls ist eine neue HA-Bereichszuordnung nötig.
Keine automatische Zuordnung anhand der Lage und keine parallele Etagenauswahl.

## Kartenbild im Dashboard

Die bestehende Image Entity kann in einer Standard-Bildkarte verwendet werden.
Den Beispielnamen durch die tatsächliche Entity-ID ersetzen:

```yaml
type: picture-entity
entity: image.wohnzimmer_robbi_map
show_name: true
show_state: false
```

Nur vollständig validierte Karten werden angezeigt. Raw-Map-Anzeige benötigt
keine Raum-Polygone. Der belegte Legacy-Ursprung im vollständigen Rasterzentrum
und die tatsächliche Map-Auflösung bestimmen die Positionen; dieselbe Crop-,
Padding- und Skalierungsberechnung wie beim PNG bestimmt die Bildkoordinaten.
Ein selbst erzeugtes SVG bettet das unveränderte PNG ein und zeichnet die Marker.
Ohne darstellbare Marker wird weiterhin das PNG ausgegeben.
Positionsänderungen aktualisieren nur die Bildhülle, nicht Decoder oder Pieces.

Die letzte gute Basis-Karte wird lokal privat und atomar gespeichert. Nach
Neustart steht sie nach Geräteerkennung und Cache-Load als PNG-Fallback bereit,
noch vor dem ersten räumlichen Cloud-Refresh. Aktuelle Marker benötigen wieder
eine frische RawMap im Speicher; Positionen werden niemals persistiert.
Nur ein vollständiger erfolgreicher Build der bestätigten aktiven Karte ersetzt
den Cache. Temporäre Fehler und Zeitablauf verstecken das Bild nicht; Room-
Kommandos bleiben trotzdem an ihre bisherigen Gültigkeitsprüfungen gebunden.
Unload und Neustart erhalten den Cache. Eine positiv bestätigte andere aktive
Map-ID verwirft die alte Zuordnung. Bei fehlendem/defektem Storage oder solange
noch nie eine gute Karte geladen wurde, bleibt normales Cloud-Laden erforderlich.

## Befehle und Fehlerbehandlung

Schreibbefehle werden pro Roboter serialisiert, mit maximal vier laufenden/
wartenden Aufrufen und 1,5 Sekunden Abstand. Offensichtlich bereits erfüllte
Aktionen werden bei frischem eindeutigen Status lokal übersprungen.
Es gibt keine automatischen Schreib-Retries.

Bei unklarer Antwort oder Timeout kann ein gezielter Status-Refresh die passende
Aktivität bestätigen. Explizite Ablehnungen bleiben Fehler.
Ein beobachtetes cleaning bestätigt nur eine laufende Reinigung, nicht
protokollseitig die exakte Auswahl der Räume. Vor einem erneuten manuellen
Befehl bei unklarem Ausgang zuerst den Roboter prüfen.

## Diagnose, Sicherheit und Grenzen

Die herunterladbare Diagnose enthält nur Integrationsversion, grobe
Status-/Gültigkeitsflags, Piece-Anzahlklassen und feste Fehlerkategorien.
Keine Kontodaten, Tokens, Geräte-/Karten-/Raum-IDs, Namen, Koordinaten,
CRCs, Rohantworten oder Kartenbilder. Keine Forschungsproben und kein MQTT.

Home Assistant speichert die eingegebenen Zugangsdaten in seiner Konfiguration.
HA-Dateisystem und Backups schützen. Tokens verbleiben im Speicher.
Die gemeinsame HA-HTTPS-Sitzung wird beim Entladen nicht geschlossen.

Bei Authentifizierungsfehlern Yeedi-Zugangsdaten prüfen; kein Kontoumzug nötig.
Für zusätzliche Yeedi-Geräteverifikation gibt es keinen implementierten
Code-Eingabeablauf. Cloud-Änderungen können Anpassungen erfordern.
Wassermenge, Verbrauchsmaterialien, Reinigungsstatistiken, Karteneditierung
und Navigation per Kartenklick werden nicht angeboten.

## Entwicklung und Lizenz

Validierung: `python scripts/validate.py` und `python -m pytest -q`.
Testumgebung: Python 3.14 mit `requirements-test.txt`.
[Prüfprotokoll](docs/VALIDATION.md) · [Protokollhistorie](docs/PROTOCOL.md)

[MIT-Lizenz](LICENSE) und [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES.md)
bleiben erhalten. Eigenständiger Client, Decoder und Renderer; kein kopierter
oder portierter GPL-Code, keine GPL-Runtime-Abhängigkeit, keine Markenlogos.
Dieser RC liegt ausschließlich auf feature/rooms-position-map.
Kein Merge nach main und keine Veröffentlichung von 0.2.0 Stable.
