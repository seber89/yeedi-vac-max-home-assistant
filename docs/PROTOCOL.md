# Direkter Yeedi-Client: belegtes Protokoll und offene Live-Prüfung

Stand: 0.2.0-rc.1. Ältere Abschnitte sind historische Entwicklungsbefunde,
keine Beschreibung des aktuellen Runtime-Verhaltens.

## RC1 — Forschung entfernt, bestätigte Funktion unverändert

Der Besitzer bestätigt Beta 6.4: lesbare, aktualisierte Karte, erneutes Laden
nach HA-Neustart, Stop/Pause/Home und Raumreinigung auf echter Hardware.
RC1 entfernt MQTT-Diagnose, ihre temporäre TLS-Ausnahme, den zusätzlichen
getMapInfo-Diagnoseaufruf, Format-/Transportproben und LZMA-Crosscheck.
Keine MQTT-Verbindung und keine deaktivierte Zertifikatsprüfung verbleiben.
Die unten beschriebene Beta-6.3-Ausnahme gilt ausdrücklich NICHT mehr.

Unverändert bleiben funktionale Legacy-Discovery (die historische Methode
probe_legacy_maps liefert weiterhin die aktive Map), Major/Minor-Abfragen,
primärer Decoder, Assembly, Generation-Check, PNG-Palette/Crop/Zoom,
Cache-/Image-Verhalten sowie sämtliche Vacuum-/Raumbefehle.
Keine neuen Protokollannahmen oder Transportwege.
Kompakte Diagnostics exportieren nur feste boolesche Flags, Anzahlklassen
und Fehlerkategorien; keine Forschungsblöcke oder privaten Werte.
Ein abschließender RC-Hardware-Smoke-Test steht noch aus.

## Beta 6.4 — rein lokale PNG-Präsentation

Neuer Hardwarebefund: vollständige sichtbare Direct-RawMap, weiterhin ohne
Raum-Polygone; MQTT-Diagnose empfängt Nonzero-Daten, die nicht zur Image-Entity
gelangen. Beta 6.4 ändert ausschließlich die PNG-Darstellung nach erfolgreichem
Rasteraufbau. Keine Änderung an Transport, Decoder, Generation, Cache oder MQTT.

Der bestehende Nonzero-Crop bleibt Grundlage. Darstellungspadding: 3 Prozent
der längeren sichtbaren Seite, auf ganze Pixel aufgerundet und auf 1–6 begrenzt.
Anders als zuvor auch an Quellrasterkanten symmetrisch. Nur Display-Hintergrund,
keine Rückwirkung auf Pieces, Grundraster oder Positionsdaten.
Integer-Nearest-Neighbor-Zoom: Ziel 320 sichtbare Pixel an der längeren Seite,
Faktor 1–8 und Ausgabe maximal 1040 je Seite. Keine Unschärfe, keine Verzerrung,
keine verlorenen dünnen Wände durch Downsampling. PNG-Palette und 2MiB-Limit
unverändert. Komplett null bleibt no_visible_pixels. Keine neuen Diagnostics.

Der bisherige 4x4-PNG-Regressionstest prüft jetzt das erwartete gepaddete 48x48-
Bild und jede vergrößerte Originalzelle, zusätzlich zu PNG-CRC/Chunk-Prüfung.
Dies aktualisiert nur eine beabsichtigte Ausgabegröße, keine Transportassertion.

Keine Raw-Overlays: Geräte-Y-Richtung ist dokumentiert, doch ein für dieses
Raster validierter absoluter Ursprung und Positionsmaßstab fehlen. Allein
has_robot_position/has_dock_position rechtfertigt keine Umrechnung. Unabhängiger
Polygon-SVG-Fallback unverändert; keine geratenen Marker auf der RawMap.
Image-API/Entity-ID unverändert. Reload startet wie bisher ohne persistenten
Karten-Cache und zeigt die frisch validierte Karte nach bestehendem Cloud-Load.
Die bisherige begrenzte Fehlerfrist bleibt erhalten, nicht unbegrenzt erweitert.

## Beta 6.3 — isolierte passive MQTT-Diagnose

Verbindungsfakten: [gepinnter Yeedi-Python-Client, mqtt_client.py](https://github.com/gyordanov/client.py/blob/07d93928a1d556aae711b41335afbddd5bd61551/deebot_client/mqtt_client.py)
und [öffentliche MQTT-Protokollbeschreibung](https://deebot.readthedocs.io/advanced/protocols/mqtt/).
EU: mq-eu.ecouser.net, TLS/TCP 443; Username = bestehende Portal-userId,
Passwort = bestehender Portal-Token, Client-ID = userId@ecouser/app-device-id.
ATR: iot/atr/+/device-id/class/resource/j. Nur bereits gefundene 04z443-Geräte.
Keine neue Anmeldung, keine geratenen Sessionwerte. Bekannte Commandnamen
MajorMap/MinorMap/MapInfo/MapSubSet sowie on/get/Get/report-Präfixe werden auf
feste Namen normalisiert (Protokollfakten aus dem gepinnten JS-Dispatcher).
JSON ausschließlich body.data; unbekannte Namen/Inhalte werden nicht exportiert.

Das eigenständig geschriebene Wire-Subset folgt dem
[OASIS MQTT 3.1.1 Standard](https://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html):
CONNECT mit Level 4 / Clean Session, SUBSCRIBE QoS 0 und validierter SUBACK,
PINGREQ/PINGRESP, DISCONNECT; nur Empfang von QoS-0-PUBLISH. Keine Publish-API,
keine Will-Nachricht, kein Reconnect, keine P2P-Requests/Subscriptions.
Keine fremden MQTT-Klassen/Dispatcher/Fixtures portiert.

Bibliotheksprüfung: HA garantiert aiomqtt nicht als allgemeine Abhängigkeit.
aiomqtt 2.5.0 wurde geprüft; sein Connect läuft in einem Executor-Thread, der bei
Coroutine-Abbruch nicht unmittelbar beendet wird. Für das ausdrücklich streng
begrenzte Diagnosefenster wird stattdessen ein schmaler asyncio-Stream-Pfad ohne
neue Dependency verwendet, keine allgemeine neue Ecovacs-Client-Architektur.
Framing-/Paketgrößenlimits, höchstens 256 klassifizierte Nachrichten pro Roboter,
8 vor SUBACK gepufferte Nachrichten und begrenzte Dekompression halten die Probe
klein. Reader-Task wird abgebrochen/abgewartet, Socket geschlossen/abgebrochen.

TLS-Test ohne Credentials ergab hier fehlendes Zertifikatsvertrauen. Der Besitzer
hat die isolierte Ausnahme ausdrücklich genehmigt. Nur dieser feste Broker
erhält einen eigenen SSLContext mit CERT_NONE; kein globaler TLS-/HTTPS-Eingriff.
Verschlüsselung ohne verifizierte Broker-Identität schützt nicht vor aktivem
Man-in-the-Middle/Token-Diebstahl. Das ist keine Empfehlung für Dauerbetrieb.

Start vor erstem Coordinator-Refresh, maximal 85 Sekunden inklusive Verbindungs-
aufbau; begrenzter Cleanup bleibt im 90-Sekunden-Budget. Connect maximal 10s,
SUBACK maximal 5s, TLS-Handshake maximal 5s. Jeder Transport-/JSON-Fehler beendet
die Probe ohne Reconnect und ohne Exceptiontexte. Fehlgeschlagene Piece-Decodes
werden als nicht erfolgreich klassifiziert, niemals mit anderen Codecs versucht.
HA-Config-Entry-Hintergrundtask wird bei Unload/Shutdown beendet; Einrichtung und
HTTPS-Coordinator bleiben unabhängig. Keine extra Map-Befehle werden ausgelöst.

MinorMap-Diagnose: begrenzte Base64-/Legacy-LZMA-Prüfung anhand des bereits
belegten 9-Byte-Headers, maximal 65536 Ausgabebytes / 16MiB Dictionary / 32MiB
Dekompressorbudget. Dies stellt nur Null/Nonzero und Gleichheit fest, keine
Geometrievalidierung oder Renderingfreigabe. Die funktionale RawMap-Decodierung
ist unverändert. Transiente Gleichheits-Digests bleiben intern und werden am
Fensterende gelöscht; weder Bytes noch Digests werden gespeichert/exportiert.
Major-CRC-Merkmale beschreiben die zuletzt beobachtete valide Liste; Minor-
Merkmale aggregieren die begrenzte beobachtete Menge. Die Transportvergleichs-
flags behaupten weder eine passende Generation noch eine fertige Karte.

Hardwarevalidierung des MQTT-Pfads steht aus. ATR-only ohne Ereignis ist kein
Negativbeweis für P2P oder Nachrichten außerhalb des kurzen Zeitfensters.

## Beta 6.2: nur aggregierte Zero-Pixel-Analyse

CRC-Struktur: Anzahl gesamt, bekannter Empty-Sentinel, CRC null, unterschiedliche
CRCs, alle gleich und alle nicht durch den bekannten Sentinel markierten CRCs
gleich. Sentinel und Request-Auswahl bleiben unverändert. Keine CRC veröffentlicht.
Decodierte Pieces: Anzahl, Null-/Nonzero-Anzahlen, alle null/identisch und Anzahl
unterschiedlicher Inhalte. Encoded-Payloads: nur Gleichheit und Distinct-Bucket.
Vergleiche mittels ausschließlich während des Loads gehaltener SHA-256-Digests;
keine Payloadkopien, keine Ausgabe oder Persistierung der Digests. Ergebnis ist
ein reiner Befund, keine automatische Anpassung des Sentinels oder Kartenformats.

Ein primär erfolgreich decodiertes Piece pro Load erhält einen zusätzlichen
unabhängig geschriebenen FORMAT_RAW/FILTER_LZMA1-Aufruf. Grundlage:
[öffentliche LZMA-Formatspezifikation](https://raw.githubusercontent.com/tukaani-project/xz/master/doc/lzma-file-format.txt)
und [Python lzma](https://docs.python.org/3/library/lzma.html).
Properties kodieren lc/lp/pb; Dictionary ist Little-Endian. Der bereits belegte
Legacy-Header endet nach neun Bytes; exakt dessen verbleibender Stream wird
verwendet. Strenges Base64, maximal 512 KiB encoded, 16 MiB Dictionary, lc+lp<=4,
maximal 65536 Ausgabebytes plus ein Überlauf-Prüfbyte. Kein Codec-Raten.
Bei bekannter Ausgabelänge kann LZMA laut Spezifikation ohne EOS enden: der
Gegencheck akzeptiert dann exakt passende Ausgabe bei vollständig verbrauchtem
Input, niemals eine Überlänge. Der funktionale primäre Decoder bleibt unverändert.

Nur alternate_decode_success, alternate_matches_primary und
alternate_nonzero_pixels_present verlassen den Gegencheck. Beide Pfade verwenden
liblzma, keine Behauptung zweier unabhängiger Kompressionsbibliotheken. Alternative
Pixel werden weder gespeichert noch veröffentlicht. Crosscheck-Ausfälle isoliert.
Keine zusätzlichen HTTP-Requests; Cache, zwei Worker, Zeitbudget und zweite
Generationsprüfung bleiben erhalten. Die einmalige Claim-Markierung wird vor dem
await gesetzt; auch bei zwei Workern höchstens ein Gegencheck.

zero_pixel_probe exportiert ausschließlich fest allowlistete Booleans und Buckets
0, 1, 2–8, 9–32, 33–64, 65–256, 257–1024, >1024. Keine exakten Anzahlen oder
Piece-Zuordnungen. Gleichheitsflags bei leerer Menge false. Decoded-Anzahlen hier
inklusive Cache, raw_map.decoded_piece_count_bucket weiterhin nur neue Decodes.
Bei Cache-only-Refresh kein Encoded-/Alternate-Test; Distinct-Encoded-Bucket 0.
Snapshots nach Fehlern können Teilmengen beschreiben, keine Vollständigkeit behauptet.

## Beta 6.1: Palette und Final-Stages

Die bereits gepinnte Legacy-Formatquelle (mapTemplate.js, f1ae56e; Link unten)
belegt neben 1/2/3 auch 4 sowie >10 als darstellbare Klassen. 5–10 haben dort
keine spezifische Farbe. Unser eigener Renderer verwendet eigene neutrale
Farben und behandelt ausnahmslos alle Nonzero-Pixel als Crop-Geometrie.
Keine fremden Renderer-/Decoder-Algorithmen übernommen. LZMA unverändert.

Neue Stage-Flags: generation_verified erst nach identischer zweiter MajorMap;
render_attempted nur bei tatsächlichem Rendering (nicht beim PNG-Cachetreffer);
raster_assembled nach erfolgreichem Zusammenbau. Fehlerlabel ausschließlich:
none, major_initial, piece_download, piece_decode, generation_changed,
raster_assembly, no_visible_pixels, png_generation, unexpected.
Verifikations-Transport-/ungültige Antwortfehler zählen als unexpected, nicht
als behaupteter Generationswechsel. Tatsächliche Unterschiede bleiben strikt
generation_changed; keine Veröffentlichung. Keine Exception-Texte exportiert.

Nonzero-, bekannte (1–4, >10) und sonstige Nonzero-Pixel (5–10) werden über alle
gültigen Pieces einschließlich Cachetreffern aggregiert. Nur Buckets 0, 1, 2–8,
9–32, 33–64, 65–256, 257–1024, >1024 werden ausgegeben. Keine Histogramme oder
Piece-Zuordnung. Nur ein vollständig nulles Raster darf no_visible_pixels sein.
PNG-Fehler nach erfolgreichem Assemble behalten raster_assembled=true.
Die Stage-Flags betreffen den aktuellen Versuch; available/complete dürfen
während der unveränderten kurzen Fehler-Grace das vorherige gültige Bild anzeigen.
image_generated wird dabei nicht mehr durch available überschrieben.

## Beta 6: eigenständiger funktionaler Legacy-Rasterpfad

Hardwaremeldung Beta 5: MajorMap liefert positive numerische Rasterfelder und
33–64 CRC-Tokens; zwei direkte MinorMap-Antworten enthalten nichtleere ASCII- /
Base64-kompatible pieceValue-Strings. Das belegt den Transport, noch nicht den
nachfolgenden Decoder oder das gerenderte Bild auf diesem Gerät.

### Formatfakten und Clean Room

Gezielte Protokollanalyse des bereits gepinnten
[mapTemplate.js (f1ae56e)](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/mapTemplate.js)
belegt folgende Datenformat-Eigenschaften des Legacy-Pfads:

- MajorMap-Rastermaße: Piece-Dimensionen mal Zellenanzahl; nullbasierte
  Piece-Liste. Im quadratischen Raster läuft die Y-Zelle zuerst, dann X.
- Lokale Pixel sind spaltenweise gespeichert (Y läuft zuerst). Die Anzeige hat
  ihren Ursprung oben links; Geräte-Y wächst nach oben.
- Palette: 0 unbekannt, 1 Boden, 2 Wand, 3 Teppich. Andere Werte werden hier
  neutral dargestellt; keine Interpretation als WLAN-/Sonderdaten.
- Base64 kapselt Legacy-LZMA mit 9-Byte-Header: ein Properties-Byte, vier Bytes
  Little-Endian Dictionary-Größe und vier Bytes Little-Endian Ausgabelänge,
  danach der komprimierte Stream. Standard LZMA-alone hat stattdessen eine
  acht Byte breite Ausgabelänge. Es wird nur dieses belegte Format akzeptiert,
  kein Zstd/XZ/gzip-Fallback und keine Codec-Erkennung durch Probieren.

Keine Klassen, Decoder, Renderer, Manager, Tests oder Fixtures übernommen.
`raw_map.py` ist eine originäre Implementierung dieses Datenformats mit
[Python lzma](https://docs.python.org/3/library/lzma.html), Base64 und einem
kleinen eigenen indexed-PNG-Writer (`struct`/`zlib`, nur Standardbibliothek).
PNG-Chunk-Prüfsummen gehören zum PNG-Container, nicht zu einer geratenen
Yeedi-CRC-Prüfung. Vendor-CRCs dienen nur als private Generationskennungen.

### Grenzen und atomare Veröffentlichung

Map-ID muss exakt zur aktiven validierten ID passen. Positive ganzzahlige
Piece-Seiten bis 256, Zellseiten bis 16, Gesamtfläche maximal 1024²; Pixelmaß
positiv/endlich bis 1000. Beide Seiten müssen jeweils gleich sein: rechteckige
Layouts sind aus den gesichteten Legacy-Fakten nicht eindeutig ableitbar und
werden ausdrücklich nicht geraten. CRC-Liste exakt Zellprodukt lang, maximal
8192 Zeichen, nur unsigned 32-bit-Dezimalwerte. Empty-Sentinel unverändert.

Strenges kanonisches Base64, höchstens 512 KiB encodiert pro Piece, beschränkte
Dictionary-Größe (4 KiB–16 MiB), Decoder-Memorylimit 32 MiB. Header und tatsächliche
Ausgabe müssen exakt Piece-Seite² Bytes beschreiben, vollständiges Stream-Ende,
keine nachgestellten Bytes. Unbekannte oder unvollständige Daten: keine Raw-Karte.
Die Quadrat-Beschränkung und strikte Headerprüfung sind bewusst konservativ;
eine abweichende echte Antwort erfordert einen gezielten weiteren Hardwarebefund.

Zwei Worker, maximal zwei Requests gleichzeitig, insgesamt 75 Sekunden. Bei
Fehler/Timeout/HA-Abbruch werden ausstehende Worker abgebrochen und abgewartet.
Begrenzte lokale Dekompression/PNG-Erzeugung läuft außerhalb des HA-Eventloops.
Keine eigenen Write-Retries oder Steuerbefehle. Nach allen Pieces wird MajorMap
erneut gelesen: Map-ID, Dimensionen, Skalierung und CRC-Liste müssen identisch
bleiben. Bei Wechsel wird der gesamte Kandidat verworfen und kein altes Raw-Bild
beibehalten. Eine externe Änderung des Coordinator-State verhindert ebenfalls
die Veröffentlichung. Kein automatisches Zusammenraten verschiedener Generationen.

RawMap enthält ausschließlich im Speicher validierte Pieces, Metadaten und PNG.
Das Bild wird unabhängig von Room-Polygongültigkeit und Positionsverfügbarkeit
bevorzugt bereitgestellt, ohne Overlays. Keine eigene Cloudabfrage der Image-Entity.
PNG maximal 2 MiB; leere Außenränder werden abgeschnitten. Keine Text-/ID-Metadaten.

Stündlicher erfolgreicher Raw-Refresh; gleiche Map/Dimensionen/Skalierung erlauben
Wiederverwendung von Pieces mit identischem CRC. Bei Fehler drei Minuten Backoff,
vorherige vollständige Karte höchstens drei Minuten derselben Map-ID; wiederholte
Fehler verlängern die Bildfrist nicht. Neue Map-ID leert den Raw-State vor dem Laden.
Normaler Map-/Room-Cache und sämtliche Write-Pfade bleiben unabhängig/unverändert.
Die zusätzliche Beta-5-Probe wird nicht mehr automatisch aufgerufen; deren reine
Hilfsfunktionen/Tests bleiben für Regressionen erhalten. MQTT bleibt deaktiviert.

`raw_map` exportiert nur available/complete/major_valid/image_generated und
Bucketwerte für required/loaded/decoded/decode_failures (0, 1, 2–8, 9–32, 33–64, >64).
Loaded/decoded zählen neue Downloads dieses Versuchs, nicht Cache-Treffer. Bei
kurzem Fehler-Grace kann complete weiterhin die letzte gültige Karte beschreiben.
Keine IDs, CRC-Werte, Indizes, Dimensionswerte, Bytes oder Bildinhalte in Diagnostics.

## Beta 5: Direct-Piece-Diagnose; MQTT bewusst nicht gestartet

Hardwaremeldung Beta 4: MapInfo accepted, aber keine verwertbaren Map-Payloadfelder.
Separater optionaler Direct-MajorMap-Read nach der bestehenden Outline-Probe;
funktionale maps()/Legacy-Discovery und sämtliche Steuerpfade unverändert.
Nur bei derselben aktuellen validierten mid werden Piece-Indizes verwendet.
CRC-Listengrammatik: mindestens zwei kommagetrennte ASCII-Dezimalwerte, optional
umgebendes Whitespace je Token, jeweils unsigned 32-bit. Defensive Grenzen:
8192 Zeichen / 256 Tokens, keine Annahme einer festen Piece-Anzahl. Der dokumentierte
Empty-Piece-Sentinel wird ausgeschlossen. Die ersten höchstens zwei verbleibenden
nullbasierten Positionen bilden die Request-Indizes; keine CRC-Berechnung. Tokens
und Roh-MajorMap werden nicht über folgende awaits hinweg behalten oder gespeichert.
Ungültige Liste: keine MinorMap-Requests. Ausschließlich mid/pieceIndex/type=ol.

60s gemeinsames diagnostisches Budget; MajorMap maximal 18s mit unveränderter
Legacy-Read-Strategie, MinorMap je höchstens 40s innerhalb des Restbudgets mit
vorhandenem Read-Retry. Höchstens zwei logische Minor-Reads, keine weitere
Retry-Schleife. Fehlende Antworten/Reject/Timeout verändern Rooms und Online nicht.
Busy/Offline/Auth stoppen weitere Pieces; HA-Cancellation bleibt durchlässig.
Akzeptierte Minor-Formate werden ohne Indexzuordnung dedupliziert. Empfangene
Rejects zählen als response, aber nicht als accepted; deren Inhalte werden nicht
übernommen. MQTT-Flags false bedeuten nicht getestet, keine Transportausschlussdiagnose.

### Recherche nur zu Interoperabilitätsfakten (18.09.2026)

- [DeebotUniverse MQTT-Protokoll](https://deebot.readthedocs.io/advanced/protocols/mqtt/):
  asynchrone Broadcasts und iot/atr/command/device/class/resource/j als Topic-Prinzip.
- [ecovacs-deebot.js constants.js, f1ae56e](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/constants.js):
  bekannter Empty-Piece-CRC-Sentinel; keine benutzerbezogene CRC übernommen.
- [map.js, gleicher Pin](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/commands/map.js)
  und [mapManager.js](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/managers/mapManager.js):
  MajorMap.value als CRC-Liste, nullbasierter Index und MinorMap-Felder mid/pieceIndex/type.
  Keine Renderer-/Decoder-/Architekturübernahme, keine Tests/Fixtures kopiert.
- [ecovacsDeviceSession.js](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/ecovacsDeviceSession.js):
  regionaler mq-Host, TLS/8883, Benutzer mit Realm-Suffix, Session-Token als Passwort,
  Client-Identifier mit Resource, Broadcast-Subscription. Die Referenz deaktiviert
  standardmäßig Zertifikatsprüfung und beschreibt eine private Broker-CA.
- [Yeedi-Fork mqtt_client.py, 07d9392](https://github.com/gyordanov/client.py/blob/07d93928a1d556aae711b41335afbddd5bd61551/deebot_client/mqtt_client.py):
  anderer Port 443 und Benutzer ohne Suffix; Client-Identifier mit Realm/Resource,
  ebenfalls ausgeschaltete Zertifikatsprüfung beim Cloud-Default.

Belegt sind MQTT-Prinzip, Topic-Familie, Session-Token-Nutzung und mögliche
Map-Nachrichten. Nicht hinreichend belegt ist die sichere vollständige Verbindung
für dieses Yeedi-DE-Konto einschließlich vertrauenswürdigem Broker-Zertifikat.
Kein Versuch mit realen Credentials, keine Abschaltung von TLS-Prüfungen und keine
neue Anmeldung. Deshalb MQTT bewusst nicht implementiert; `protocol_verified=false`
bezieht sich auf die vollständige sichere Konfiguration, nicht auf die Existenz
des Protokolls. Keine Dependencies, Konfigurationsfelder, Tasks oder Reconnects.
Die installierte HA-MQTT-Integration nutzt paho-mqtt, der Fork aiomqtt; keines
dieser Pakete wird für den nicht freigegebenen Diagnosepfad neu eingebunden.
Die vorhandene HTTP-Authentifizierung und Device-Identity bleiben unverändert.

## Beta 4: Outline-Probe, keine Interpretation

Owner-reported erneuter Beta-3-Hardwaretest: online, gültige Map/Rooms und Dock,
aber zwei leere MapSubSet.value-Strings auch mit msid. Als vom Auftrag belegter
V1-Read wird getMapInfo mit mid=current validated map ID und type=ol ergänzt.
Keine weiteren Request-Felder oder Map-Kommandos. Eigenständige Implementierung,
keine GPL-Implementierung/Fixtures/Decoder übernommen.

Probe separat nach dem normalen Room-Refresh, nur bei erfolgreicher eindeutiger
Map-Discovery; auch bei Room-Fehler möglich. Keine Erweiterung von client.maps()
oder der normalen Room-Command-Validierung. Maximal 40s einschließlich der
vorhandenen Read-Retry-Strategie (2x15s + 1s Pause + Reserve), keine zusätzliche
Retry-Schleife. Fehler werden isoliert; Cache-Intervalle und Room-Zustand bleiben
unverändert. Cancellation wird weitergereicht. GetMapInfo als Write wird schon
vor Authentifizierung/Netzwerkzugriff abgelehnt. Kein getMinorMap.

Strukturdiagnose verwendet ausschließlich die bereits festen Envelope-Pfade.
Outline-Feld-Allowlist: mid, type, totalWidth, totalHeight, pixel, totalCount,
index, pieceIndex, startX, startY, width, height, crc, value, pieceValue.
Alle Werte nur present/type; Strings value/pieceValue zusätzlich empty und
grober length_bucket. Weder Dimensionen, CRCs, IDs, Koordinaten noch Rohinhalte
werden gespeichert/exportiert. Keine verschachtelte Suche nach Pieces oder
Interpretation von Kartendaten. Echter Response und Eignung bleiben unvalidiert.

## Beta 3: MapSet-spezifische msid

Owner-reported Beta-2-Befund: zwei akzeptierte Raumdetailantworten mit leeren
value-Strings (empty=true, length_bucket=0), kein Polygon. MapSet.data enthält
msid als String. Laut bereitgestellter V1-Interoperabilitätsinformation akzeptiert
getMapSubSet neben mid/type/mssid auch die msid des übergeordneten MapSets.
Eigenständige minimale Umsetzung: identifier(data.get("msid")), bei gültigem
Ergebnis zusätzliches Request-Feld msid für alle regulären Detailreads dieses
Aufrufs. Keine Speicherung über MapSet-Aufrufe hinweg; ungültig/fehlend bleibt
das Feld aus. Keine Änderung am GetMapSet-Request oder an der Response-Verarbeitung.
Kein fremder Implementierungscode verwendet. Keine IDs oder Rohwerte in Diagnosen.
Ob damit Geometrie geliefert wird, muss der Hardwaretest erst bestätigen.

## Beta 2: ausschließlich Formatklassifikation

Owner-reported Beta-1-Befund: Map/Rooms gültig, zwei Subsets, akzeptierte
MapSubSet.data.value-Strings ohne compress, keine geparsten Polygone; Dock vorhanden,
Roboterposition fehlt. Keine realen Strings als Fixture gespeichert oder untersucht.
Der bestehende reguläre Room-Ablauf klassifiziert lokal die value-Felder akzeptierter,
passender MapSubSet-Antworten. Keine zusätzlichen Requests und keine Parseränderung.
Die Diagnose speichert ausschließlich fixe Typ-/Bucket-Labels und boolesche
Formatflags; gleiche Formen werden gezählt, ohne Zuordnung zu Raum-IDs oder Namen.
JSON wird nur auf Gültigkeit und Top-Level-Typ geprüft; NaN/Infinity sind kein JSON.
Base64/Hex ausschließlich Zeichensatzprüfung des vollständigen Strings, ohne
Whitespace-Normalisierung, Paddingvalidierung oder Decodierung. Leere Strings
gelten nicht als Base64-/Hex-Kandidat. `empty` bedeutet exakt leer, Whitespace
wird separat gemeldet. XY-Flag prüft die bestehende Semikolon-Syntax und Grenzen,
nicht die geometrische Brauchbarkeit. Es liefert keine Polygonpunkte.
Die Probe umfasst den letzten begonnenen Room-Read (bei Abbruch ggf. partiell),
wird vor dem nächsten Read zurückgesetzt und bei close gelöscht. Fehlende und
unerwartete value-Typen werden ausschließlich mit present/type beschrieben.
MajorMap.value, Cloud-/Command-/Map-Lifecycle und Renderer bleiben unberührt.

## Beta 1: bestätigte Räume, lokales SVG und Lifecycle

Owner-reported Alpha-6-Hardwaretest: Legacy-Discovery und Segmentreinigung
funktionieren. MapSet.data enthält mid/msid als Strings, type und subsets als
Array; die beobachteten zwei Einträge enthalten zunächst nur mssid. Reguläre
MapSubSet-Reads liefern mid/mssid, subtype, type und value als String, ohne
beobachtetes compress-Feld. Keine Rohantworten gespeichert. Die tatsächlich
gelieferte Polygon-Kodierung ist weiterhin unbekannt: ausschließlich der schon
vorhandene unabhängige polygon()-Parser wird verwendet, keine Decoder ergänzt.

Map-/Positions-/Write-Protokoll, Retry-Budgets und Legacy-Fallback bleiben gleich.
Vor spotArea wird unter dem bestehenden Command-Lock jetzt neben der Map auch
die Raumstruktur neu gelesen (MapSet und gegebenenfalls reguläre MapSubSet-Reads,
insgesamt weiter 40s). Lokale Generation = sortierte eindeutige Room-IDs;
niemals Diagnoseausgabe. Map-ID oder Generation abweichend von der Auswahl:
kein Write, stattdessen erneute HA-Bereichszuordnung. Die Cloud kann nach der
letzten Abfrage theoretisch noch geändert werden; das Protokoll bietet keine
atomare Map-Revision im Schreibbefehl. Keine darüber hinausgehende Garantie.

Erfolgreicher regulärer Refresh bleibt stündlich, Fehler-Backoff 180s. Während
des Refresh werden räumliche Daten als ungültig markiert und Listener informiert;
neue Map-ID verwirft alte Räume vor der Room-Abfrage. Gleiche ID erzwingt bei
fälligem Refresh ebenfalls neue Raumdaten. HA wird über seine öffentliche
Segment-/Repair-API informiert; keine privaten Registries oder Auto-Zuordnung.
Neue Coordinator-Instanz beginnt ohne räumlichen Cache; Geräteidentität unverändert.

Die neue Image-Plattform verarbeitet ausschließlich gültigen Coordinator-State.
Originaler statischer SVG-Renderer, XML-escaped Namen, dynamische Bounds, optionale
Positionsmarker; keine Ressourcen/Code-Fragmente aus Cloudwerten. Kein I/O und keine
persistenten Map-Dateien. Ohne Polygongeometrie/bei ungültigem Cache unavailable,
Bildabruf liefert kein vorheriges SVG. Lokaler Render-Cache berücksichtigt Map-ID,
Room-Generation, vollständige immutable Raumdaten und Positionen. Zeitstempel
werden bei Coordinator-Änderungen gesetzt, nicht beim HTTP-Bildabruf.
Keine Winkelinterpretation ergänzt (Orientierung ist optional und wird nicht dargestellt).
SVG/Koordinaten/Namen/IDs/Fingerprints werden niemals in Diagnostics exportiert.

## Etappe 2: spotArea und redundante Aktionen

Original implementierter V1-Auftrag an `clean`: act=start, type=spotArea,
content=kommaseparierte reale Raum-IDs, count=1, donotClean=0, router=plan.
Protokollreferenz: gepinnte `library/commands/clean.js` (V1 Clean/SpotArea).
Keine kopierten Klassen/Tests/Fixtures, keine neuen Laufzeitabhängigkeiten.
Ein oder mehrere Räume, dedupliziert in Auswahlreihenfolge; IDs bleiben Strings.
Die native HA-API wurde in der lokal installierten Version 2026.9.2 und der
offiziellen Vacuum-Entity-Dokumentation geprüft; diese ist nun Mindestversion.

`coordinator.rooms` ist nur eine gültigkeitsgefilterte Sicht auf SpatialState,
kein neuer Cache. Die Entity fragt keine Räume aus der Cloud ab. Unter dem
bestehenden Command-Lock prüft der Coordinator vor spotArea die aktive Karte.
Bei geändertem/unklarem Kartenbezug wird nicht geschrieben; alte Räume werden
invalidiert und über das vorhandene Verfahren neu geladen. Die Karten-ID als
Segmentgruppe schützt gespeicherte HA-Bereichszuordnungen vor ID-Wiederverwendung.
Ein externer Kartenwechsel exakt zwischen Prüfung und Write kann vom Protokoll
ohne atomaren Kartenbezug im clean-Auftrag nicht vollständig ausgeschlossen werden.

Statusbestätigung `cleaning` beweist nur laufende Reinigung, nicht dass die
angefragten Räume ausgewählt wurden. Raumreinigung ist noch hardwarezuprüfen.
Kein Retry bei Timeout, kein Überstimmen expliziter Ablehnungen, dieselbe Queue.

Live-Bericht alpha.1: Start/Stop/Return Home/Verbindung/Status/Docked funktionieren.
Dock-Befehl im bereits angedockten Zustand wird explizit abgelehnt. Deshalb
no-op bei docked/returning für Dock, paused für Pause, cleaning für Auto-Start/
Resume, idle/docked für Stop. Prüfung unter dem vorhandenen Lock, nur bei frischem
Online-Status (max. 65 s) und erfolgreichem Basisupdate. Ein nach ACK noch nicht
passender Status darf keinen nachfolgenden legitimen Befehl unterdrücken.
Raumaufträge sind von Auto-Start-no-op ausgenommen. Keine Rohantworten publiziert.

## Etappe 1: V1-Daten und zwei Arten von Bestätigung

Zielprofil laut Auftrag und Referenz: DVX34 / 04z443 / K781, DE,
950type=true, 950type_V2=false. Keine V2-Befehle und keine Feature-Erfindungen.
Zusätzliche Faktenquelle im oben gepinnten JavaScript-Projekt:
`library/commands/map.js`, `library/managers/mapManager.js`,
`library/managers/botState.js`, `library/mapInfo.js`.
Nur Protokollinformationen wurden verwendet, keine Parser/Renderer portiert.

| Befehl | Anfrage / gelesene Felder |
| --- | --- |
| getCachedMapInfo | data.info mit mid/name/using; mid=0 ignorieren |
| getMapSet | mid der aktiven Karte, type=ar; subsets[].mssid |
| getMapSubSet | mid, type=ar, mssid; reale name/subtype/value/compress |
| getPos | data-Anfrage [chargePos, deebotPos]; deebotPos-Objekt, chargePos-Liste, x/y/a/invalid |

Aktive Karte nur bei genau einem using=1. Keine Karte/Mehrdeutigkeit ergibt None.
IDs werden nie erfunden. Fehlende Details behalten die reale Raum-ID und einen
Fallback-Namen. connections/index/cleanset werden noch nicht benötigt und nicht
interpretiert. Komprimierte Werte bleiben unbekannt. Unkomprimierte V1-Grenzen
verwenden `x,y;x,y;...`; der unabhängige begrenzte Parser akzeptiert außerdem
explizite JSON-Punktpaare, ohne deren Lieferung vom Zielgerät zu behaupten.
Ungültige Werte/NaN/Infinity werden verworfen. Mehrere Dockpositionen sind
mehrdeutig und ergeben None. Modelle bleiben in Originalkoordinaten im Speicher.

**Direkte Bestätigung:** Portal ret=ok und Geräte-body.code=0. Fehlender Code
ist weiterhin keine Gerätebestätigung. Nichtnull-Code/ret=fail bleibt Ablehnung.
Offline-Codes 4200/500 bleiben Offline/keine Antwort; HTTP 429 bleibt Rate-Limit.
Es werden keine unbekannten Busy-Codes geraten.

**Statusbestätigung:** Nur nach unklarer Antwort oder Transportproblem nach dem
Anmeldeversuch wird ein neuer Basis-Snapshot gelesen. Online und Aktivität
müssen exakt zum Befehl passen: start/resume=cleaning, pause=paused, stop=idle,
charge/go=returning oder docked. Dies ist Beobachtung, keine direkte Quittierung
und kein Kausalitätsbeweis. Keine Bestätigung aus dem alten Coordinator-Cache.
Explizite Ablehnung wird niemals durch Status überstimmt. Fehlender/abweichender
Status bleibt unklar. Schreiben wird unter keinen Umständen automatisch wiederholt.

Der Coordinator gibt intern `device` oder `status` zurück. Je Roboter deckt
ein FIFO-Lock Schreiben und Refresh ab; maximal vier Aufrufe, sonst Busy.
Identischer bestätigter Befehl innerhalb 1,5 Sekunden wird zusammengefasst,
andere Befehle warten diese Ruhezeit ab. Abgebrochene/fehlgeschlagene Befehle
werden nicht als erfolgreicher Debounce-Kandidat gespeichert.

SpatialState ist vom Basis-Snapshot getrennt. 60-Sekunden-Polling für Position,
stündlicher Metadaten-/Raumcache mit explizitem Refresh-Hook. Reload initialisiert
neu. Optionale Zeitbudgets ab Alpha 4: Position 8 Sekunden, Map-Metadaten 40 Sekunden,
Räume/Details separat 20 Sekunden;
Basis-Snapshot 60 Sekunden, Bestätigungs-Snapshot 20 Sekunden. Nach optionalen
Fehlern gelten Cache-Flags als ungültig; spätere Raumsteuerung muss sie prüfen.
Keine Rohantworten oder räumlichen Daten veröffentlichen, loggen oder diagnostizieren.

Live-Befund des Besitzers: 0.1.0 über HACS installiert, Basisbefehle funktionieren,
gelegentlich unklare Quittierung trotz physischer Ausführung. Die neue Alpha,
Karten/Positionsdaten und Langzeitbetrieb sind noch nicht live bestätigt.

## Alpha 3: Strukturdiagnose, kein unbewiesener Parser-Fix

Live-Befund des Besitzers mit Alpha 2: online/Basissteuerung funktionieren,
Dockposition vorhanden, aktive Karte/Metadaten/Räume/Roboterposition fehlen.
Das belegt weder die Lage von `info` noch den Datentyp von `using`.
`metadata_valid=false` kann durch Cloudfehler, Zeitbudget oder Parserfehler entstehen;
es beweist nicht, dass keine Karte gespeichert ist. Die Ursache bleibt offen.

Die temporäre Alpha-3-Probe erfasst ausschließlich Struktur an festen Ebenen:
Portalantwort, `resp`, `resp.data`, `resp.body`, `resp.body.data`.
Ein JSON-String in `resp` wird für die Strukturprüfung dekodiert wie im bestehenden
Antwortparser. Keine rekursive Suche durch unbekannte Felder, keine Rohlogs.
Bekannte Feldnamen werden allowlisted; Werte werden nie übernommen. Typen von
`using`, `mid`, `msid`, `mssid`, Positionen und Kompression sowie Listenanzahlen
werden beschrieben. Ein active-candidate-Zähler beschreibt nur das bisher erwartete
`using=1`/`"1"` mit nichtleerer/nonzero Map-ID; andere Darstellungen werden nicht
als aktive Karte geraten. Bei mehr als 100 Einträgen ist die Inspektion als
abgeschnitten markiert. Mehrdeutige Karten bleiben nicht auswählbar.

Auch abgelehnte/unklare Antwortumschläge werden vor der unveränderten Validierung
strukturell erfasst. Transport, Offline, Timeout, Busy, Authentifizierung und
Abbruch des äußeren Zeitbudgets werden nur als feste Kategorien gespeichert.
Keine Ausnahme-Texte, Codes, IDs oder benutzerdefinierten Schlüssel werden exportiert.
Nicht aufgerufene Befehle bleiben ausdrücklich `attempted=false`.

`getMapSet` bleibt `{mid, type: "ar"}`; `getMapSubSet` bleibt `{mid, type: "ar", mssid}`.
Ob zusätzliche Parameter wie `msid` tatsächlich nötig sind, ist ohne neue
Hardwarebelege nicht entscheidbar. Keine geratenen Parameter oder Fallback-Pfade
ergänzt, keine Referenzimplementierung kopiert. Fehlende Roboterposition bei
vorhandener Dockposition ist schon jetzt zulässig. Die neuen Tests prüfen die
Diagnose mit synthetischen Varianten; sie sind keine realen Map-Fixtures.

Nach dem Hardwarelauf zunächst `getCachedMapInfo` auswerten; nur anhand des
Strukturbelegs korrigieren. Danach können MapSet/SubSet mit real ermittelten IDs
abgefragt und erneut strukturell geprüft werden. Raumreinigung bleibt unvalidiert.

## Alpha 4: minimaler Budget-Fix nach Live-Diagnose

Besitzerbefund Alpha 3: getCachedMapInfo attempted=true, command_success=false,
response_received=false, outcome=cancelled_or_budget_expired; MapSet/SubSet nicht
aufgerufen. getPos akzeptiert unter resp.body.data, chargePos array/deebotPos object;
Dockposition erkannt, Roboterposition weiterhin nicht erkannt.
Damit liegt weiterhin kein belegtes Map-Antwortformat vor. Parser und Parameter
bleiben unverändert. Das zu kurze äußere Budget ist nachgewiesen; ob dessen
Korrektur allein die Cloudabfrage erfolgreich macht, muss der Hardwaretest zeigen.

HTTP_TIMEOUT=15, READ_ATTEMPTS=2, READ_RETRY_DELAY=1 bleiben unverändert als
gemeinsame Konstanten. MAP_READ_TIMEOUT=READ_RETRY_BUDGET+9 ergibt 40 Sekunden
für Metadaten und den Map-Check vor Raumkommandos. Authentifizierung und Wartezeit
auf den Client-Semaphor verbrauchen ebenfalls dieses endliche Budget.
Raum-/Detailabfragen behalten ein separates 20-Sekunden-Gesamtbudget.
Erfolg: 3600 Sekunden Cache ab Abschluss; Fehler: 180 Sekunden Backoff ab Fehler
bis zum nächsten regulären Poll. Manueller Refresh/Reload bleibt explizit möglich.
Keine neuen Cloudbefehle oder Schreibwiederholungen.
Positionsdiagnose: nur present/type für x,y,a,invalid an deebotPos/chargePos[0].
Keine Feldwerte und keine Parseränderung. Keine Etappe-3-Funktionen.

## Alpha 5: Legacy-Discovery als reine Hardwareprobe

Live-Befund Alpha 4: getCachedMapInfo outcome=timeout, keine Antwort. getPos
akzeptiert unter resp.body.data; chargePos array, deebotPos object. x/y/a/invalid
bei deebotPos sind numerisch, chargePos[0] enthält numerische x/y/a. Keine Werte
übernommen; weder Positions- noch Map-Parser geändert.

Interoperabilitätsquelle: ecovacs-deebot.js f1ae56e, library/commands/map.js
belegt getMapState/getMajorMap ohne zusätzliche Parameter; mapManager.js belegt
das Feld state. Es wurden nur Befehls-/Feldnamen und Parameterfakten verwendet,
keine Parser, Klassen, Tests oder Fixtures übernommen. Bestehende MIT-Lizenz und
THIRD_PARTY_NOTICES bleiben unverändert. Die Referenz ist kein Hardwarebeleg.

Nur CommandTimeout von client.maps im Spatial-Refresh löst die Probe aus.
Beide Reads laufen sequenziell innerhalb des vorhandenen Coordinator-Locks,
je ein HTTP-Versuch ohne Retry (15s), außen je 18s. Kein neuer Task/Timer/Queue.
GetCachedMapInfo-Budget bleibt 40s, Backoff 180s nach Abschluss, Erfolgscache 3600s.
Bis zu 36s zusätzliche Wartezeit unter dem Lock ist für die Probe möglich.
Offline/Busy/Auth beendet die Probe; sonst wird der zweite Read auch nach einem
fehlgeschlagenen ersten Read versucht. HA-Cancellation wird nicht verschluckt.
Keine Legacy-Probe im Write-/Statusbestätigungsablauf oder Room-Preflight.
Die Ergebnisse dienen ausschließlich der bestehenden Safe-Structure-Probe;
sie aktivieren keine Map-/Room-Funktionen und werden nicht als Kartendaten gecacht.

## Alpha 6: zentraler funktionaler Legacy-Fallback

Hardwarebefund des Besitzers: CachedMapInfo timeout; MapState akzeptiert mit
resp.body.data.state string, MajorMap akzeptiert mit resp.body.data.mid string
und value string. Keine Werte veröffentlicht. Das belegt den Antwortpfad, nicht
die Semantik von state oder die Struktur von value. Keine neue GPL-Analyse/
Portierung: nur diese Hardwarefakten werden eigenständig verwendet.

client.maps() versucht primär CachedMapInfo (40s). Nur CommandTimeout aktiviert
die wiederverwendete Legacy-Discovery (MapState, MajorMap; je 18s, ohne Retry).
Sie liefert nun einen Kandidaten statt ausschließlich Struktur zu verwerfen:
mid muss string sein, identifier() bestehen und ungleich "0" sein. Sonst liefert
maps() CloudError. Erfolg ergibt genau YeediMap(mid, None, True). Keine Auswertung
von MajorMap.value oder MapState.state. Die bekannte Privacy-Probe bleibt aktiv.
Normales Polling und Room-Preflight nutzen denselben Clientpfad. Kein separater
Coordinator-Fallback und kein erneutes Werfen des ursprünglichen Timeouts nach Erfolg.

Äußere Discovery-Grenze: 40 + 2*18 + 1 = 77s. Primäres Budget nicht erhöht.
Room-Refresh anschließend separat 40s (READ_RETRY_BUDGET+9) inklusive aller regulären
Details, ohne unbegrenzte Schleife. GetMapSet(mid,"ar") folgt im selben Refresh.
Der vorhandene Parser wird unverändert verwendet; bei abweichender Struktur sauberer
Room-Fehler. Kein erzwungenes getMapSubSet. Erste Subset-Struktur diagnostiziert
nur Vorhandensein/Typ von mssid/name/subtype/value/compress, nie Werte.

Nach erfolgreicher Map-Discovery bleibt metadata_valid=true auch bei Room-Fehlern;
active_map bleibt erhalten, rooms_valid=false und Räume werden geleert/gesperrt.
Bei Map-Fehler metadata_valid=false. Fehler-Backoff weiterhin 180s, erfolgreicher
Cache 3600s. Bestehende Queue/no-op-/Write-Validierung und Positionen unverändert.
Alpha-6-Room-Struktur und Raumreinigung sind noch nicht hardwarevalidiert.

## Warum ein kleiner eingebauter Client?

Der reguläre Python-Client bietet in der geprüften Version keinen Yeedi-Login. Der S20-Fork ergänzt ihn, benötigt aber Python/Rust-Paketbau und verwendet denselben Paketnamen wie die HA-Ecovacs-Abhängigkeit. Das `04z443`-Profil fehlt dort. Für die kleine Auswahl an HTTPS-Befehlen wird deshalb ein eigener asynchroner Client ohne zusätzliche Laufzeitabhängigkeit verwendet. Home Assistants vorhandenes aiohttp übernimmt HTTP. Der gesamte MQTT-, Karten- und Fork-Paketbau entfällt für diese erste Polling-Implementierung.

Das ist eine experimentelle Umsetzung belegter Felder und kein Nachweis, dass die heutige Cloud mit dem Konto des Besitzers funktioniert. Die ältere Entscheidung in RESEARCH.md wurde durch die detailliertere Protokollprüfung und den ausdrücklichen Auftrag zur Implementierung überholt.

## Nachvollziehbare Referenzen

- [ecovacs-deebot.js, f1ae56e](https://github.com/mrbungle64/ecovacs-deebot.js/tree/f1ae56e69d409c5e02f72d4ea313024aa146363e): `index.js`, `library/constants.js`, `library/command.js`, `library/commands/clean.js`, `library/commands/movement.js`, `library/dictionary.js`, `library/models.js`, `library/capabilityTypes.js`.
- [Yeedi-Python-Fork, 07d9392](https://github.com/gyordanov/client.py/tree/07d93928a1d556aae711b41335afbddd5bd61551): `authentication.py`, `api_client.py`, `command.py`, JSON-Commands. Direkter Yeedi-Login und europäischer Portalhost sind hier implementiert.
- [Regulärer Python-Client, be8cbbd](https://github.com/DeebotUniverse/client.py/tree/be8cbbda9159e8b750efc4727eccf66ae5ff80bf): zum Abgleich des bisherigen Ecovacs-Standes.

Es wurden Protokollfakten abgeglichen und eine kleine eigene Implementierung geschrieben. Referenz-Quelltexte sind nicht Bestandteil des ausgelieferten Pakets.

## Authentifizierung

1. HTTPS-GET an `gl-de-api.yeedi.com`, private API `user/login`, App-Code `yd_global_e`, App-Version 1.3.0.
2. Das Protokoll verlangt einen MD5-Passworthash und eine MD5-Signatur über sortierte Metadaten/Parameter, eingerahmt von App-Key und App-Secret. Das ist eine Cloud-Vorgabe, keine Empfehlung zur Passwortspeicherung.
3. Auth-Code über `gl-de-openapi.yeedi.com/v1/global/auth/getAuthCode`.
4. Token-Austausch über `portal-eu.ecouser.net/api/users/user.do`, Organisation `ECOYDWW`.
5. Geräteauflistung über `GetDeviceList` und `GetGlobalDeviceList`; Auswahl von `class=04z443`.

Der Portalhost gehört zur gemeinsam genutzten Infrastruktur. **Seine Ecovacs-Domain bedeutet keine Migration:** Login-App und Konto bleiben Yeedi.

Die öffentlichen App-Keys `1581917520081` und `1581923437995` samt Signaturkonstanten stehen in den oben referenzierten `constants.js` und `authentication.py`. Sie kennzeichnen die Yeedi-App; es sind keine persönlichen Zugangsdaten. Die Integration muss diese Werte zur Protokollsignierung verwenden und enthält keine erfundenen Schlüssel.

Tokens werden bis kurz vor der gemeldeten Gültigkeit wiederverwendet. Beide geprüften Referenzansätze erneuern sie durch erneuten Login. Diese Integration behauptet keinen separaten Refresh-Token-Grant. HTTP 401/403 führt zur erneuten Einrichtung; Code 1013 wird als noch nicht unterstützte zusätzliche Verifizierung gemeldet.

## Gerätebefehle

Der JavaScript-Snapshot ordnet `04z443` dem Yeedi-Profil und der nicht-V2-JSON-Kommunikation zu. HTTPS-Endpunkt: `iot/devmanager.do`. Umschlag: Geräte-ID, Geräteklasse, Geräte-Ressource, Benutzer-Auth und JSON-Payload. Keine automatischen Wiederholungen bei schreibenden Befehlen.

| Funktion | Protokoll |
| --- | --- |
| Start | `clean`, act=start, type=auto |
| Fortsetzen / Pause / Stop | `clean`, act=resume / pause / stop |
| Ladestation | `charge`, act=go |
| Akku | `getBattery`, data.value |
| Reinigung / Laden | `getCleanInfo` / `getChargeState` |
| Saugleistung | `getSpeed` / `setSpeed`, data.speed |

Das aktuelle Modell erbt `vacuumBase`: Quiet=1000, Normal=0, Max=1 laut Wörterbuch. Max+ wird nicht angeboten. Diese Werte müssen trotzdem am Zielgerät getestet werden.

Portalantwort und Geräteantwort werden getrennt geprüft. Eine erfolgreiche HTTP-Antwort allein reicht nicht. Direkte Bestätigung benötigt code=0; nur für unklare Ausgänge gilt alternativ die oben beschriebene Statusbestätigung. Status wird frisch gelesen, nie aus dem abgesendeten Befehl erfunden. Offline/Timeout-Codes 4200 und 500 stammen aus der Referenzimplementierung.

## Begrenzung und Datenschutz

15 Sekunden je Anfrage, ein Wiederholungsversuch nur bei geeigneten lesenden Transportfehlern, keine unmittelbare Wiederholung nach Rate-Limit. Koordinator und Einrichtung sind zusätzlich zeitlich begrenzt. Keine Weiterleitung von Auth-Anfragen auf andere Hosts (Redirects deaktiviert). Cloud-Ausnahmen werden durch neutrale Meldungen ersetzt. Polling und Steuerung werden serialisiert; mehrere Geräte teilen eine Authentifizierung.

Login und Basissteuerung von 0.1.0 sind laut Besitzer funktionsfähig. Live unbestätigt bleiben neue Raum-/Positionsantworten, neue Bestätigungslogik und Tokenablauf nach mehreren Tagen. Fehlschläge sollen anhand bereinigter Kategorien korrigiert werden, nicht durch blindes Probieren anderer Herstellerkonten.
