# Yeedi Vac Max für Home Assistant

**0.1.0 — Experimental / initial test release. Technische Vorstufe: noch keine Robotersteuerung.**

Ziel ist eine direkte Integration für das **bestehende Yeedi-Konto**. Der Roboter soll in der Yeedi-App bleiben, ohne Ecovacs-Migration, Node-RED, n8n, zusätzliche Container oder separaten Dienst.

## Aktueller Stand

Die HACS-Struktur und der deutsche/englische Einrichtungshinweis sind vorhanden. Beim Hinzufügen erklärt Home Assistant die fehlende Backend-Unterstützung und beendet die Einrichtung. **Kein Login, kein Gerät, keine Entities und keine Steuerbefehle werden angelegt.** Zugangsdaten werden deshalb noch nicht abgefragt oder gespeichert.

Eine passende JavaScript-Bibliothek existiert: `mrbungle64/ecovacs-deebot.js` unterstützt Yeedi-Login und nennt ausdrücklich `04z443` / K781. Sie ist jedoch kein Python-Client und benötigt Node.js. Der Python-Fork `gyordanov/client.py` enthält einen direkten Yeedi-Login, aber kein Profil für `04z443`; sein Gerätefilter sortiert dieses Modell als nicht unterstützt aus. Die reguläre Python-Bibliothek `deebot-client` 18.6.0 verwendet Ecovacs-Authentifizierung.

Deshalb wurde entsprechend der Projektanforderung vor einem unzuverlässigen eigenen Cloud-Client gestoppt. Das bedeutet nicht, dass die gewünschte Integration unmöglich ist. [Recherche, genaue Quellen und nächster Entwicklungsschritt](docs/RESEARCH.md).

## Zielgerät und Teststand

| Angabe | Stand |
| --- | --- |
| Hersteller / Modell | yeedi / Yeedi Vac Max DVX34 |
| Geräteklasse / Familie | `04z443` / K781 |
| Konto / Land | Yeedi / Deutschland (`DE`) |
| Firmware | 1.2.9 laut Besitzer, **nicht mit dieser Integration getestet** |
| Live-Test | keiner; kein Cloud-Login durchgeführt |

Start, Pause, Stop, Dock, Status, Akku, online/offline und Saugleistung sind offen. Ebenso Wassermenge, Verbrauchsmaterialien, Reinigungsstatistik, Fehler, Karte und Raumreinigung. Saugleistungsstufen werden erst nach Protokollvalidierung umgesetzt.

## HACS-Installation — nur zum Prüfen des Einrichtungshinweises

**Zum Steuern des Roboters lohnt sich die Installation dieser Vorstufe noch nicht.**

1. HACS in Home Assistant öffnen.
2. Im Menü mit den drei Punkten **Benutzerdefinierte Repositories** wählen. Die Anordnung hängt von der HACS-Version ab.
3. `https://github.com/seber89/yeedi-vac-max-home-assistant` einfügen.
4. Kategorie **Integration** wählen und hinzufügen.
5. **Yeedi Vac Max (Experimental)** suchen und herunterladen; falls erforderlich `main` auswählen.
6. Home Assistant neu starten.
7. **Einstellungen → Geräte & Dienste → Integration hinzufügen** öffnen.
8. **Yeedi Vac Max** auswählen.
9. Die Meldung zur noch nicht verfügbaren Cloud-Anbindung lesen und schließen.

Es folgt **kein Login-Formular**. Eine spätere funktionsfähige Version soll nur Yeedi-Konto, Passwort und Land (Vorgabe `DE`) abfragen und automatisch nach `04z443` suchen. Dafür gibt es noch keinen zugesagten Termin.

Die Dateistruktur ist für ein benutzerdefiniertes HACS-Repository vorbereitet. Installation in einer realen HACS-/HA-Instanz wurde nicht getestet. Das Projekt ist nicht im HACS-Standardkatalog. `0.1.0` ist die Manifest-Version; für eine Installation vom Standardbranch ist kein GitHub-Release notwendig.

## Datenschutz und Hilfe

Die Vorstufe führt keine Netzwerkzugriffe aus und installiert keine Cloud-Abhängigkeiten. Sie verändert weder Konto noch Roboter. Die Yeedi-App kann weiter genutzt werden.

- **Backend-Meldung:** erwartetes Verhalten, kein falsches Passwort. Neuinstallation hilft nicht.
- **Nicht auffindbar:** prüfen, ob `custom_components/yeedi_vac_max/manifest.json` im HA-Konfigurationsordner vorhanden ist; HA neu starten und Browser neu laden.
- **Keine Entities:** in 0.1.0 erwartet; es gibt keine Geräteverbindung.
- **Logs:** Einstellungen → System → Protokolle. Bei Problemen nur bereinigte Fehlermeldungen und Versionsnummern in ein GitHub-Issue schreiben. Keine Passwörter, Tokens, Cookies oder vollständigen Diagnoseexporte veröffentlichen.
- **Entfernen:** Repository in HACS entfernen und HA neu starten. Diese Version erzeugt keinen regulären Config Entry.

## Entwicklung

`custom_components/yeedi_vac_max/` enthält Manifest, Config Flow, Setup-/Unload-Schutz und Übersetzungen. `coordinator.py`, `entity.py`, `vacuum.py` und `sensor.py` werden erst mit einem verifizierten Backend ergänzt. Leere Geräteklassen würden hier keine Funktion liefern.

`python scripts/validate.py` prüft Python-Syntax, JSON, Struktur und Übersetzungen. Grenzen der Prüfungen: [VALIDATION.md](docs/VALIDATION.md).

## Lizenz

Die bestehende [MIT-Lizenz](LICENSE) bleibt unverändert. Kein Cloud-Bibliothekscode wurde übernommen. Das Projektsymbol ist eine eigene einfache Darstellung, kein offizielles Yeedi-Logo.
