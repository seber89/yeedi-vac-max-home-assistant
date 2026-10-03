# SAFE MQTT PATH: NO

Research-/Design-Gate, 27.09.2026. Ausgang: RC.7,
`54c37594c6f3159e3c5dfe75c98b229bcc72b17c`, Branch `feature/rooms-position-map`.
Kein RC.8, kein Runtime-Patch, kein neuer Tag/Release, kein Merge.
Dieses Ergebnis bedeutet **nicht**, dass ein sicherer Herstellerpfad unmöglich
ist: Mit den überprüften Quellen und Vertrauensankern ist er nicht belegt.

## 1. Hardwarebefund und Schlussfolgerungsgrenzen

Laut Besitzer kennt RC.7 die aktuelle Map über getMapInfo_V2; die ID stimmt mit
der aktiven Map überein. setMajorMap wurde einmal gesendet, Ausgang uncertain.
Die direkten Major-/Minor-Reads liefern technisch gültige, vollständig
dekodierte Null-Pieces. Die offizielle App zeigt die gespeicherte Karte.
Das ist Anlass für Transportrecherche, kein Beleg für einen Decoderfehler oder
für eine bestimmte MQTT-Payload auf 04z443. Kein weiterer Gerätebefehl wurde
in dieser Untersuchung gesendet; insbesondere kein setMajorMap.

## 2. Gepinnte Quellen und Clean Room

Die vorhandenen lokalen Snapshots wurden gegen ihre Commit-IDs geprüft.
Verwendet wurden ausschließlich Namen, Felder, Transport-/Authentifizierungs-
und Lifecycle-Fakten, keine Implementierungen oder fremden Tests/Fixtures.

- **ecovacs-deebot.js f1ae56e69d409c5e02f72d4ea313024aa146363e**:
  [Map-Commands](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/commands/map.js),
  [Nachrichtenbeschreibung](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/ecovacsMessageDispatcher.js),
  [Feldnamen des MapInfo-Ereignisses](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/managers/mapManager.js),
  [MQTT-/TLS-Fakten](https://github.com/mrbungle64/ecovacs-deebot.js/blob/f1ae56e69d409c5e02f72d4ea313024aa146363e/library/ecovacsDeviceSession.js).
- **Yeedi-Python-Fork 07d93928a1d556aae711b41335afbddd5bd61551**:
  [MQTT-Konfiguration](https://github.com/gyordanov/client.py/blob/07d93928a1d556aae711b41335afbddd5bd61551/deebot_client/mqtt_client.py).
- **DeebotUniverse be8cbbda9159e8b750efc4727eccf66ae5ff80bf**:
  [MQTT-Konfiguration](https://github.com/DeebotUniverse/client.py/blob/be8cbbda9159e8b750efc4727eccf66ae5ff80bf/deebot_client/mqtt_client.py),
  [Map-Nachrichtennamen](https://github.com/DeebotUniverse/client.py/blob/be8cbbda9159e8b750efc4727eccf66ae5ff80bf/deebot_client/messages/json/map/__init__.py).
- **ioBroker 9ff88d556f32639dd040aae60ad010b8bd71f35e**:
  [Modellzuordnung](https://github.com/mrbungle64/ioBroker.ecovacs-deebot/blob/9ff88d556f32639dd040aae60ad010b8bd71f35e/lib/deebotModel.js),
  wie bereits für RC.7 dokumentiert: 04z443 wird p5nx9u zugeordnet.
- Ergänzend, nicht commit-gepinnt: öffentliche
  [MQTT-Protokolldokumentation](https://deebot.readthedocs.io/advanced/protocols/mqtt/),
  abgerufen am 27.09.2026; sie beschreibt ATR-Broadcasts und JSON-Umschläge.

## 3. TLS-Gate: tatsächliche Prüfung ohne Credentials

Nur TCP/TLS, kein MQTT CONNECT, keine Subscription, keine Benutzeranmeldung.
Python 3.14.7 / OpenSSL 3.5.8; SNI und Hostprüfung für `mq-eu.ecouser.net`.
Jeweils `ssl.create_default_context()`, `CERT_REQUIRED`, `check_hostname=True`.
Zwei Trust-Varianten: System-Defaults und explizites Mozilla/certifi-Bundle
2026.7.22. Keine alternative CA importiert, keine Verifikationsregel gelockert.
Verbindungs-/Handshake-Timeout je Versuch zehn Sekunden.

| Host/Port | System-Trust | Mozilla-Trust |
| --- | --- | --- |
| mq-eu.ecouser.net:443 | Fehler 20: unable to get local issuer certificate | derselbe Fehler |
| mq-eu.ecouser.net:8883 | Fehler 20: unable to get local issuer certificate | derselbe Fehler |
| github.com:443, Kontrollziel | nicht benötigt | erfolgreich, TLS 1.3 |

Damit konnte auf diesem Rechner und Netzwerk keine vertrauenswürdige Kette
für den belegten EU-Broker aufgebaut werden. Das ist kein MQTT-Authfehler.
Es beweist allein noch nicht, welche CA fehlt oder ob nach Behebung zusätzlich
ein SAN-/Hostnameproblem auftreten würde. Eine verifizierte Broker-Kette und
Hostidentität können deshalb nicht angegeben werden. Die Behauptung einer
privaten "ECOVACS CA" stammt aus dem gepinnten JS-Quellkommentar, nicht aus
einer erfolgreich authentifizierten Live-Kette.

Die Referenz-Cloud-Defaults sind nicht übernehmbar: Python schaltet Host- und
Zertifikatsprüfung aus; JS beschreibt die private, nicht öffentlich validierbare
CA und deaktiviert die Prüfung ebenfalls standardmäßig. Diese Einstellungen
wurden weder für den Test noch für unsere Integration verwendet.

## 4. Sichere Alternativen geprüft

### A. Öffentliche PKI

Beide belegten Ports scheitern mit beiden Trust-Speichern. Portwechsel löst das
Problem nicht. Keine geratenen Broker-/WebSocket-Adressen wurden ausprobiert.
Ein neues, vom Hersteller dokumentiertes öffentlich validierbares Ziel könnte
das Gate später öffnen, ist für diesen Yeedi-/Region-/Kontopfad aber nicht belegt.

### B. Private CA mit belastbarer Herkunft

In den drei gepinnten Client-Repositories wurde die Zertifikats-Dateiliste
geprüft. Keine als Broker-CA dokumentierte Datei gefunden. JS enthält zwar
`key.pem`, aber diese Datei wird als API-PUBLIC_KEY verwendet. Ihre lokale
X.509-Metadatenprüfung ergab keine BasicConstraints-CA-Extension und keine SANs;
Subject/Issuer heißen generisch "Default Company Ltd". Das ist kein belastbarer
Nachweis eines MQTT-Vertrauensankers und wird nicht als solcher eingebunden.

Gezielte Suche in öffentlicher Hersteller-/Projekt-Dokumentation ergab keine
offiziell veröffentlichte oder nachvollziehbar lizenzierte Broker-CA mit
bestätigter Provenienz. Das ist ein begrenztes Rechercheergebnis, kein Beweis,
dass der Hersteller keine solche CA besitzt. Die
[Hersteller-Sicherheitsmeldung zu fehlender TLS-Prüfung](https://www.ecovacs.com/global/userhelp/dsa20241217001)
liefert keine CA und ist keine Spezifikation für K781/Yeedi.

[Bumper-Zertifikate](https://bumper.readthedocs.io/en/latest/Create_Certs/)
sind eigens erzeugte Zertifikate für einen lokalen Ersatzserver, keine
Authentifizierung des Hersteller-Cloud-Brokers. Sie lösen dieses Problem nicht.
Keine Zertifikate aus Foren oder einer unverifizierten Broker-Verbindung
übernommen. Ohne konkretes CA-Artefakt plus Herkunft/Rechten ist eine
Redistribution nicht freigegeben; die Lizenz eines umgebenden Repositories
belegt nicht automatisch die Rechte an eingebetteten Herstellerzertifikaten.

### C. Zertifikats-/SPKI-Pinning

Ein unabhängig authentifizierter Hersteller-Pin könnte konzeptionell eine
zusätzliche Bindung ermöglichen. Es fehlt aber eine vertrauenswürdige Quelle
für diesen Pin und dessen genaue Host-/Servicezuordnung. Ein live aus derselben
unverifizierten Verbindung gewonnener Pin wäre TOFU und ist ausgeschlossen.
SPKI-Prüfung als Zusatz zu gültiger PKI behebt die fehlende CA nicht.
Keine Umsetzung mit zunächst deaktivierter TLS-Prüfung und späterem Hashvergleich.

Auch mit unabhängiger Quelle müssten Hostidentität, Zertifikatsgültigkeit,
ServerAuth-Verwendung, zulässige Schlüssel, Rotation/Überlappung und widerrufene
Pins definiert werden. Leaf-Pins brechen bei Zertifikatswechsel, SPKI-Pins bei
Schlüsselwechsel. Es fehlt ein authentifizierter Update-/Rotationskanal.
Ein legitimer privater CA-Trust im isolierten SSLContext mit unverändertem
CERT_REQUIRED und Hostnamenprüfung wäre einfacher, benötigt aber dieselbe
noch fehlende Herkunfts-/Lizenzklärung.

## 5. Broker, Authentifizierung und Topics: nur Quellenbefund

Wegen des TLS-Abbruchs keine praktische MQTT-Authentifizierung geprüft.
Die Varianten dürfen nicht zu einer geratenen Mischkonfiguration kombiniert werden.

| Fakt | Python-/Yeedi-Referenz | JS-Referenz |
| --- | --- | --- |
| EU-Broker | mq-eu.ecouser.net | regionaler mq-eu.ecouser.net |
| TLS/TCP-Port | 443 | 8883 |
| Username | Portal-userId, ohne Realm-Suffix | userId@ecouser |
| Secret | authentifizierter Session-Token | Session-Secret/Token |
| Client-ID | userId@ecouser/client-device-id | userId@ecouser/client-resource |
| MQTT-Version | Bibliotheksdefault 3.1.1 | explizit Protokollversion 4 = MQTT 3.1.1 |

Client-device-id/resource ist die Kennung des angemeldeten Clients, nicht
automatisch die DID/resource des Roboters. Der eigene YeediClient hält bereits
Portal-user_id, token und client-device_id im RAM. Das reicht strukturell für
die Python-Variante; echte Broker-Akzeptanz für dieses Konto ist nicht bestätigt.
Keine zweite Anmeldung oder Tokenpersistenz nötig bzw. in dieser Recherche erfolgt.

ATR-Schema: `iot/atr/<event>/<did>/<class>/<resource>/j`.
Ein künftiger Listener könnte auf `onMapInfo` für exakt das konfigurierte Gerät
begrenzen; gegebenenfalls separat `onMapInfo_V2`. Falls Namensbeobachtung nötig
wäre, höchstens `+` an der Eventstelle desselben Gerätes, niemals `iot/atr/#`.
P2P-Topics sind dokumentiert, aber für den hier postulierten ATR-Push nach
HTTPS-Trigger nicht als nötig belegt; daher nicht vorsorglich abonnieren.

## 6. getMapInfo -> onMapInfo: belegt und noch offen

Der gepinnte JS-Nachrichtenkommentar unterscheidet ausdrücklich Statusantwort
auf getMapInfo und anschließend onMapInfo-Ereignisse. Das klassische
Request-Schema ist `getMapInfo({"mid": current_mid, "type": "ol"})`.
Unser vorhandenes prepare_raw_map verwendet bereits genau diesen Read.
Das macht die Hypothese plausibel; es beweist noch keine erfolgreiche
gespeicherte Kartenübertragung auf 04z443.

Öffentlich verwendete MapInfo-Feldnamen: mid, type, totalWidth, totalHeight,
pixel, totalCount, index, startX, startY, width, height, crc, value;
pieceValue wird ebenfalls referenziert. Daraus darf insbesondere NICHT folgen,
dass value und pieceValue austauschbar sind oder jedes Feld auf K781 vorkommt.
onMapInfo_V2 ist separat dokumentiert; die Yeedi-V2-Discovery unterscheidet sich
vom allgemeinen V2-Pfad. Der bestätigte getMapInfo_V2(type="0")-ID-Read ist kein
Beleg für dasselbe Bildformat oder dass sein Event einen Bild-Decoder erlaubt.

Künftiger, erst nach TLS-Freigabe zu prüfender Ablauf:
verifizierte Verbindung -> enges SUBACK -> bestätigter aktueller Map-ID-Read ->
klassischer HTTP-getMapInfo-Trigger -> begrenztes Warten auf passende Map-Events.
Zunächst nur bekannte Feldnamen/Typen und harmlose Flags, keine Rohpayloads.
Keine implizite setMajorMap-Voraussetzung und kein weiterer Reactivation-Write.

## 7. Eignung des eigenen Decoders / atomare Generationen

Der vorhandene decode_piece verlangt Map-ID, type=ol, pieceIndex und pieceValue
plus Major-Metadaten; sein Format ist Base64 und ein 9-Byte-Legacy-LZMA-Header,
exakte quadratische Piece-Pixelmenge und begrenzte Dekompression.
assemble benötigt ein vollständiges quadratisches, column-major Major-Raster
mit verifizierter CRC-Generation. MapInfo nennt dagegen index, Offsets und
individuelle Dimensionen. Ein bloßes Umbenennen von Feldern wäre nicht belegt.

Wiederverwendung der eigenen Dekompression/PNG-Erzeugung ist eventuell möglich,
aber direkte Wiederverwendung von decode_piece und assemble ist NICHT bestätigt.
Es fehlen K781-Strukturbefunde zu Header, Pixelmenge, Offsets, Indexsemantik,
vollständiger Serie und Generation. Kein neuer Decoder/Adapter gebaut.

Selbst eine gleiche mid reicht bei überlappenden Serien nicht als
Generationsnachweis. Vor späterem Assembly müssen Zuordnung, erwartete Anzahl
und Abschluss tatsächlich belegt sein. Dann: Duplikate idempotent,
Out-of-order-Empfang begrenzt puffern, andere Map/Generation verwerfen,
Timeout/Disconnect verwirft unvollständige Generation, Last-Good bleibt bis
zum atomaren vollständigen Ersatz. Keine Bewertung nach Piece-Anzahl.

## 8. Bibliothek und Lifecycle-Design, nicht implementiert

Die lokale HA-2026.9.2-MQTT-Integration deklariert paho-mqtt==2.1.0; das ist
keine allgemeine Laufzeitgarantie für unsere Custom Integration.
[aiomqtt 2.5.0](https://pypi.org/project/aiomqtt/2.5.0/) ist ein Kandidat:
BSD-3-Clause, paho >=2.1,<3 als Abhängigkeit; paho bietet EPL-2.0 ODER
BSD-3-Clause. Das offizielle Wheel ist py3-none-any, Python >=3.8,<4.
Damit kein architekturspezifischer MQTT-Nativbuild für aarch64 zu erwarten;
Python-3.14-Import ist lokal vorhanden, ein HA/aarch64-Laufzeittest steht aus.
Die SSL-Laufzeit selbst bleibt plattformabhängig. Keine neue Dependency installiert.

Bei späterer Freigabe expliziter Manifest-Pin, kein Verlass auf andere Custom
Components. Eigener SSLContext nur mit verifiziertem Trust. Ein Client pro
Config Entry; vorhandene Auth-Session nutzen, bei Tokenwechsel alten Client
schließen, bevor ein neuer startet. Ein kontrollierter Lifecycle-Owner,
clean session, begrenzte Verbindungs-/Subscribe-/Empfangszeiten, beschränkter
Reconnect-Backoff. Unload/Shutdown: laufenden Versuch abbrechen, Tasks awaiten,
Unsubscribe/Disconnect; CancelledError nicht verschlucken. Executor-basierte
Connect-Arbeit der Bibliothek braucht insbesondere einen belegten bounded
Socket-Timeout, nicht nur Cancellation des wartenden Coroutines.
Keine Ereignisdaten, Tokens oder Topics loggen; Bibliothekslogs ebenfalls prüfen.
Fehler dürfen Status/Rooms/Steuerung und Last-Good-Store nicht invalidieren.
Das ist ein Designkandidat, kein bereits getesteter Listener.

## 9. Konkreter nächster Schritt

1. Hersteller oder nachvollziehbarer Maintainer muss den **authentifizierten**
   EU-Broker-Vertrauensanker bzw. verifizierbaren Endpoint bereitstellen,
   inklusive Herkunft, Hostbindung, Rotation und Redistributionsbedingungen.
   Alternativ reproduzierbare Extraktion aus offiziell bezogenem und unabhängig
   signaturverifiziertem Herstellerpaket, nur nach gesonderter Provenienz- und
   Rechteprüfung. Keine zufällige APK-/PEM-Quelle.
2. Credential-freie TLS-Prüfung mit diesem legitimen Trust auf dem HA-Rechner
   wiederholen: komplette Kette, SAN für den belegten Host, Laufzeit/ServerAuth,
   weiterhin CERT_REQUIRED und Hostnamenprüfung. Ein passiver DNS/SNI-/Port-
   Vergleich der offiziellen App kann einen anderen Endpoint identifizieren,
   authentifiziert aber selbst weder dessen Zertifikat noch einen Pin.
   Kein MITM und keine Entschlüsselung von Accountverkehr notwendig.
3. Erst danach eine belegte Credential-Variante mit vorhandener Session und
   gerätespezifischem SUBACK testen; keine Kombinationen durchprobieren.
4. Dann einmaliger HTTPS-getMapInfo-Read und privacy-safe Strukturbeobachtung
   auf K781. Erst mit belegter Serien-/Payloadsemantik über einen funktionalen
   Map-Event-Decoder entscheiden.

Bis dahin STOP. RC.7-Runtime, Version, Commits und Releases unverändert.
Dieser lokale Forschungsbericht ist die einzige Repository-Ergänzung und wird
nicht automatisch committed oder veröffentlicht. Kein Hardwareerfolg behauptet.

Abschließender Baseline-Check: 525 bestehende Tests bestanden, Validate erfolgreich
(40 Python / 5 JSON), eine bekannte externe HA/aiohttp-DeprecationWarning.
Keine getrackte Datei geändert. Feature-Branch und RC.7-Tag bleiben auf
54c37594c6f3159e3c5dfe75c98b229bcc72b17c; remote main bleibt auf
b1efd7393bd38c84159113fc15bc2494ada1bf5b. Kein MQTT-Login versucht.
