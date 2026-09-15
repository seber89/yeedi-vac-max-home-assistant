# Recherche und Entscheidung — 15. September 2026

## Ziel

Direkt in Home Assistant mit bestehendem **Yeedi-Konto, DE und Vac Max DVX34/04z443** arbeiten. Keine Ecovacs-Migration. Python-Unterstützung ist nicht grundsätzlich unmöglich; ein vorhandener Fork ist ein konkreter Ansatz. Eine zuverlässig einsetzbare Kombination für das Zielgerät wurde aber nicht gefunden.

## Befunde aus Primärquellen

### JavaScript: das gesuchte Projekt kennt diesen Roboter

[mrbungle64/ecovacs-deebot.js, f1ae56e](https://github.com/mrbungle64/ecovacs-deebot.js/tree/f1ae56e69d409c5e02f72d4ea313024aa146363e): `docs/USAGE.md` beschreibt die Auswahl von `yeedi.com`. `library/models.js` führt `04z443` als yeedi vac max, `library/productIotMap.json` nennt K781. `test/api.test.js` prüft die Auswahl der Yeedi-App-Identität. Das Projekt stuft Yeedi als Community/Best-effort ein. Es benötigt Node.js >=22.15 und ist keine direkt importierbare Python-Bibliothek. Es wurde nicht am Gerät des Besitzers getestet.

### Reguläre Python-Bibliothek

[DeebotUniverse/client.py, be8cbbd](https://github.com/DeebotUniverse/client.py/tree/be8cbbda9159e8b750efc4727eccf66ae5ff80bf), [PyPI 18.6.0](https://pypi.org/project/deebot-client/18.6.0/): `authentication.py` verwendet Ecovacs-App-Metadaten und Ecovacs-Hosts. `create_rest_config` besitzt keinen Yeedi-Domainparameter. Die Suche nach Yeedi/04z443/K781/DVX34 ergibt nur das Hardwareprofil `kd0una` (Floor 3 Station), nicht Vac Max. Das Projekt arbeitet im Contribution-only-Modus.

### Python-Fork mit direktem Yeedi-Login

[gyordanov/client.py, 07d9392](https://github.com/gyordanov/client.py/tree/07d93928a1d556aae711b41335afbddd5bd61551): `authentication.py` ergänzt `auth_domain`, Yeedi-App-Identität und Organisationswerte sowie Yeedi-Loginhosts. Tests prüfen diese Auswahl. Der Zweig heißt `yeedi-s20-irdzs4` und ergänzt das S20-Profil.

**Konkrete Lücke:** `deebot_client/hardware/04z443.py` fehlt. `hardware/__init__.py:get_static_device_info` liefert bei fehlendem Profil `None`. `api_client.py:get_devices` nimmt solche Geräte in `not_supported` auf, statt eine steuerbare MQTT-Instanz anzulegen. Nur den Fork als Abhängigkeit einzutragen reicht somit nicht.

Außerdem ist der Fork als `deebot-client` mit Python >=3.14 und Rust/Maturin-Build konfiguriert. Eine Git-Abhängigkeit würde eine Quellinstallation voraussetzen und denselben Paket-/Modulnamen wie die HA-Ecovacs-Abhängigkeit belegen. Eine wartbare Auslieferung benötigt geeignete versionierte Pakete und Prüfung auf Abhängigkeitskonflikte. Keine dieser Hürden beweist Unmöglichkeit; sie verhindert die Behauptung, das vorhandene Paket sei bereits eine funktionierende HACS-Lösung für 04z443.

### Andere HA-Integration

[correiorafapc/Yeedi_Vaccum](https://github.com/correiorafapc/Yeedi_Vaccum/blob/main/README.md) nennt Vac Station `mnx7f4`, Ecovacs-Konto und notwendige Migration, nach der das Gerät nicht mehr in der Yeedi-App erscheint. Damit erfüllt dieses Projekt die Anforderungen nicht. Die [HA-Ecovacs-Integration](https://www.home-assistant.io/integrations/ecovacs/) belegt ebenfalls keinen direkten Yeedi-Login.

## Warum kein eigener Cloud-Client in 0.1.0?

Ein Modellname und eine andere Basis-URL genügen nicht. Yeedi-App-Identität, Signierung, Login, Auth-Code-Austausch, Geräteauflistung, Befehls-/MQTT-Authentifizierung und Tokenablauf müssen zusammenspielen. Danach sind modellgenaue Status-, Befehls- und Saugleistungsantworten zu prüfen. Es liegen hier keine echten bereinigten Antworten des Vac Max vor. Gemäß Auftrag wird vor einer fragilen Eigenimplementierung gestoppt.

Öffentliche App-Konstanten stehen in den Community-Quellen; diese Vorstufe übernimmt keine. Es wurde auch kein GPL-Quellcode in das MIT-Repository kopiert.

## Minimaler sinnvoller nächster Schritt

Den existierenden Yeedi-Python-Fork gezielt um ein geprüftes `04z443`-Profil erweitern, statt ein Cloud-Protokoll neu zu entwickeln. Mit bereinigten Geräteantworten Authentifizierung in DE, Geräteauflistung, Start/Pause/Stop/Dock, Status, Akku, echte Saugleistungsstufen, Tokenablauf und Wiederverbindung testen. Anschließend als wartbares, konfliktfrei installierbares Paket bereitstellen oder upstream beitragen. Zugangsdaten bleiben bei lokalen Live-Tests des Besitzers und gehören nicht in GitHub.

Falls künftig ein zusätzlicher Prozess akzeptiert wird, wäre ein Node.js-Adapter mit `ecovacs-deebot.js` ein anderer prüfbarer Weg. Er wurde nicht eingerichtet und entspricht nicht dem jetzigen Auftrag. Keine Alternative wird hier ohne Live-Test als garantiert zuverlässig bezeichnet.

## HA-Architektur nach Freigabe des Backends

- Config Flow: Yeedi-Konto, Passwort, Land DE; echte Validierung und Gerätefilter `04z443`, übersetzte Auth-/Cloud-/Offline-Fehler.
- `DataUpdateCoordinator`, nötigenfalls 30–60 Sekunden Polling; begrenzte Timeouts und Wiederholungen lesender Zugriffe, keine blinden Wiederholungen von Steuerbefehlen.
- `StateVacuumEntity`, `VacuumActivity`, `VacuumEntityFeature`; nur belegte Fähigkeiten, Akku als Sensor nach aktueller API.
- Registry mit echter Geräte-ID, Hersteller yeedi, Modell Yeedi Vac Max DVX34 und gemeldeter Firmware.
- `async_forward_entry_setups` / `async_unload_platforms`, Verbindungen und Abonnements aufräumen, Token-Refresh soweit unterstützt.

Referenzen: [Config Flow](https://developers.home-assistant.io/docs/core/integration/config_flow/), [Manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/), [Vacuum Core](https://github.com/home-assistant/core/blob/dev/homeassistant/components/vacuum/__init__.py), [HACS-Struktur](https://www.hacs.xyz/docs/publish/integration/). Diese Vorstufe nutzt ausschließlich Setup-/Unload-Hooks und Config Flow; Geräte-APIs werden noch nicht ausgeführt.
