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
