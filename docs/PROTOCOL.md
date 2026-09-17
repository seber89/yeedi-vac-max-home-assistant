# Direkter Yeedi-Client: belegtes Protokoll und offene Live-Prüfung

Stand: 16. September 2026, 0.2.0-alpha.2. Diese Datei beschreibt die aktuelle Implementierung.

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
