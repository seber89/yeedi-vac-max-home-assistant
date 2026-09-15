# Direkter Yeedi-Client: belegtes Protokoll und offene Live-Prüfung

Stand: 15. September 2026. Diese Datei beschreibt die **aktuelle Implementierung**, nicht die vorherige reine Hinweis-Vorstufe.

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

Portalantwort und Geräteantwort werden getrennt geprüft. Eine erfolgreiche HTTP-Antwort allein reicht nicht. Steuerung benötigt die Gerätebestätigung code=0; fehlende Bestätigungen und Fehler werden gemeldet. Status wird anschließend frisch gelesen, nie aus dem abgesendeten Befehl erfunden. Offline/Timeout-Codes 4200 und 500 stammen aus der Referenzimplementierung.

## Begrenzung und Datenschutz

15 Sekunden je Anfrage, ein Wiederholungsversuch nur bei geeigneten lesenden Transportfehlern, keine unmittelbare Wiederholung nach Rate-Limit. Koordinator und Einrichtung sind zusätzlich zeitlich begrenzt. Keine Weiterleitung von Auth-Anfragen auf andere Hosts (Redirects deaktiviert). Cloud-Ausnahmen werden durch neutrale Meldungen ersetzt. Polling und Steuerung werden serialisiert; mehrere Geräte teilen eine Authentifizierung.

Live unbestätigt bleiben insbesondere: aktuelle Erreichbarkeit der Loginhosts, Verträglichkeit des Portalpfads mit dem konkreten Konto, Befehlsantworten auf Firmware 1.2.9, Tokenablauf nach mehreren Tagen. Fehlschläge sollen anhand bereinigter Codes korrigiert werden, nicht durch blindes Probieren anderer Herstellerkonten.
