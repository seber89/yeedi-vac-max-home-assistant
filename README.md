# Yeedi Vac Max für Home Assistant

Version **0.2.0-rc.5** — Release Candidate für 0.2.0, noch keine Stable-Version.

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
   **0.2.0-rc.5** herunterladen (nicht main).
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
