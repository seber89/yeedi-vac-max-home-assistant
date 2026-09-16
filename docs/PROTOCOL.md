# Direkter Yeedi-Client: belegtes Protokoll und offene Live-Prüfung

Stand: 16. September 2026, 0.2.0-alpha.1. Diese Datei beschreibt die aktuelle Implementierung.

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
neu. Optionale Zeitbudgets: Position 8 Sekunden, Karten/Räume insgesamt 20 Sekunden;
Basis-Snapshot 60 Sekunden, Bestätigungs-Snapshot 20 Sekunden. Nach optionalen
Fehlern gelten Cache-Flags als ungültig; spätere Raumsteuerung muss sie prüfen.
Keine Rohantworten oder räumlichen Daten veröffentlichen, loggen oder diagnostizieren.

Live-Befund des Besitzers: 0.1.0 über HACS installiert, Basisbefehle funktionieren,
gelegentlich unklare Quittierung trotz physischer Ausführung. Die neue Alpha,
Karten/Positionsdaten und Langzeitbetrieb sind noch nicht live bestätigt.

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
