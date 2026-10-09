# Kalender

Das Modul „Kalender“ (Menü „Kalender“) bringt eigene Kalender mit Terminen und Abo-Adressen für Endgeräte.

## Kalender und Termine

* **Eigene Kalender** (z. B. „Team“, „Kundentermine“) legt an, wer das Schreibrecht für „Kalender“ hat („Kalender verwalten“). Jeder Kalender
  hat eine Farbe. Termine haben Titel, Ort, Beschreibung, Beginn und Ende; ganztägige Termine zählen nur nach Datum (Ende = letzter Tag).
  Serientermine gibt es noch nicht.
* **Systemkalender** entstehen automatisch aus der Personalverwaltung und werden nur Benutzern mit Leserecht für „Personal“ angezeigt:
  * **Urlaub**: genehmigter Urlaub aller Mitarbeiter,
  * **Anwesenheit**: Homeoffice, Dienstreise, Berufsschule, Schulung, Sonderurlaub und Freizeitausgleich (aufeinanderfolgende Tage,
    auch über ein Wochenende, werden zu einem Termin zusammengefasst).

  Krankheit, Über-/Fehlstunden und Bemerkungen sind nie enthalten.
* Die Monatsübersicht zeigt alle sichtbaren Kalender; einzelne lassen sich ausblenden.

## Rechte

Wie bei den anderen Modulen: **Kalender: lesen** (ansehen, Abo-Adressen) und **Kalender: schreiben** (Termine und Kalender ändern).
Das Menü „Kalender“ erscheint nur mit Leserecht.

## Kalender auf Endgeräten abonnieren (nur lesen)

Unter „Kalender → Abonnieren“ stehen `webcal://`-Adressen für jeden sichtbaren Kalender und für alle Kalender in einem. Die Adresse enthält einen
**persönlichen Schlüssel**; sie funktioniert ohne Anmeldung, aber nur lesend, und liefert genau die Kalender, die der Benutzer sehen darf.

* iPhone/Mac: Einstellungen → Kalender → Accounts → Account hinzufügen → Andere → Kalenderabo; Android (DAVx⁵ oder ICSx⁵), Thunderbird und
  Outlook können iCal-Abos ebenfalls.
* Die Geräte rufen den Kalender in eigenen Abständen ab (meist etwa stündlich).
* „Schlüssel erneuern“ sperrt alle bisherigen Adressen des Benutzers. Wird ein Benutzer deaktiviert, funktionieren seine Adressen nicht mehr.
* Der Schlüssel steht in der Adresse und damit auch in den Zugriffsprotokollen des Webservers; diese Protokolle gehören nicht in fremde Hände.
* Der Feed enthält Termine von 90 Tagen in der Vergangenheit bis 540 Tage in die Zukunft.

## Abgleich mit einem CalDAV-Server (Nextcloud, Radicale u. a.)

KYBRO kann seine Kalender über CalDAV in Kalender eines Servers schreiben. Dort erscheinen sie auf allen Geräten, die den Server nutzen,
auch mit Schreibzugriff des Servers für andere Dienste. Der Abgleich ist **einseitig**: KYBRO ist die führende Quelle, Änderungen an diesen Terminen
auf dem Server werden beim nächsten Abgleich überschrieben, Termine, die dort gelöscht wurden, neu angelegt. Fremde Termine im Zielkalender
bleiben unberührt; deshalb sollte ein Zielkalender nur von KYBRO befüllt werden. Termine, die älter sind als 90 Tage, werden nicht mehr angefasst und bleiben auf dem Server.

### Einrichtung mit Nextcloud (Anmeldung über LDAP)

1. In Nextcloud ein **Dienstkonto** anlegen, z. B. `kybro-sync` (bei LDAP-Anmeldung entweder ein lokales Nextcloud-Konto oder ein dafür
   vorgesehenes LDAP-Konto). Nextcloud kennt keinen „API-Benutzer“; das Dienstkonto ist ein normaler Benutzer, dem die Zielkalender gehören.
2. Als dieser Benutzer unter *Einstellungen → Sicherheit → Geräte & Sitzungen* ein **App-Passwort** erzeugen (bei LDAP-Konten ist das ohnehin der
   empfohlene Weg, und es lässt sich jederzeit widerrufen).
3. In KYBRO unter *Einstellungen → Kalender*: Server-Adresse (`https://cloud.example.de`), Benutzer und App-Passwort eintragen, „Abgleich aktiv“ ankreuzen,
   „Speichern und Verbindung testen“. Die Endung `/remote.php/dav` wird bei Bedarf ergänzt.
4. Bei „Zuordnung der Kalender“ je KYBRO-Kalender einen vorhandenen Zielkalender wählen oder einen neuen anlegen lassen (z. B. „KYBRO Urlaub“),
   dann „Zuordnung speichern“ und „Jetzt abgleichen“.
5. Die Zielkalender in Nextcloud für die Belegschaft freigeben (nur lesen) oder den gewünschten Personen Zugriff geben.

Andere Server (Radicale, Baikal, …) funktionieren genauso; als Adresse die Basisadresse des Servers eintragen, z. B. `http://server:5232`.

### Automatischer Abgleich

Der Abgleich läuft nicht von selbst bei jeder Änderung, sondern regelmäßig. Auf dem Server einrichten:

```
sudo cp deploy/kybro-kalender.service deploy/kybro-kalender.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kybro-kalender.timer
```

Der Timer startet den Abgleich alle 10 Minuten (`manage.py kalender_abgleich`). Prüfen: `systemctl list-timers kybro-kalender.timer`, Protokoll:
`journalctl -u kybro-kalender.service`. Das Ergebnis des letzten Laufs steht unter *Einstellungen → Kalender*.

### Datenschutz

Welche Daten übertragen werden, bestimmt KYBRO: eigene Termine mit Titel, Ort und Beschreibung sowie die Systemkalender Urlaub und Anwesenheit
(nur Name und Art, ohne Bemerkungen, ohne Krankheit und ohne Über-/Fehlstunden). Wer die Zielkalender auf dem Server lesen darf, regelt dort die
Freigabe; sie sollte zu den Rechten passen, die in KYBRO für die Systemkalender gelten (Personal-Leserecht).

### Für Entwickler

`kalender/caldav.py` ist ein kleiner CalDAV-Client (nur `requests` und `lxml`). Die Tests unter `kalender/tests/test_caldav.py` laufen gegen einen echten
Radicale-Server, der für die Dauer des Tests gestartet wird (`pip install -r requirements-dev.txt`); ohne Radicale werden diese Tests übersprungen.
