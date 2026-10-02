# Mobile API (Version 1)

JSON-Schnittstelle für die spätere Auftrags-App (offlinefähig, mit Unterschrift vor Ort).
Basis-URL: `/api/v1/`. Alle Endpunkte außer `auth/` erwarten den Header
`Authorization: Bearer <token>`.

Antwortformat: Erfolg `{"success": true, "data": ...}`, Fehler `{"success": false, "error": "..."}`.
Statuscodes: 400 ungültige Eingabe, 401 Token fehlt/ungültig, 402 keine gültige Lizenz,
403 fehlende Berechtigung, 404 nicht gefunden, 405 Methode nicht erlaubt, 409 Konflikt, 429 zu viele Anmeldeversuche.

| Endpunkt | Methode | Zweck | Recht |
| --- | --- | --- | --- |
| `auth/` | POST | Anmeldung `{"username","password"}`, liefert Token (30 Tage gültig) | – |
| `auftraege/` | GET | Liste, `?id=`, `?since=` (nur seit dem Zeitpunkt geänderte) | Aufträge lesen |
| `auftraege/` | POST | Auftrag anlegen/aktualisieren (idempotent über `client_uuid`) | Aufträge schreiben |
| `auftraege/rechnung/` | POST | `{"auftrag_id"}` → Rechnung (Entwurf) | Aufträge lesen, Rechnungen schreiben |
| `kunden/` | GET | Liste, `?id=` (mit Ansprechpartnern), `?since=` | Kunden lesen |
| `artikel/` | GET | aktive Artikel, `?id=`, `?since=` (auch deaktivierte) | Artikel lesen |

Die Rechte entsprechen den Gruppenrechten der Weboberfläche. Ohne gültige Lizenz für das Modul
„Warenwirtschaft“ antwortet die API mit 402.

## Zeitangaben und Delta-Sync

`since` erwartet ISO 8601, am besten mit Zeitzone (`2026-08-01T00:00:00Z` oder `+02:00`).
Ohne Zeitzone gilt die Ortszeit des Servers. Die App merkt sich den Zeitpunkt des letzten
erfolgreichen Abrufs minus eine kleine Sicherheitsspanne.

## Auftrag senden (`POST auftraege/`)

```json
{
  "client_uuid": "3f0c…",            // von der App vergeben, Pflicht
  "kunde_id": 12, "datum": "2026-08-01", "notizen": "",
  "status": "offen",                 // offen | in_bearbeitung | unterschrieben | abgeschlossen | storniert
  "unterschrift": "<Base64-PNG/JPEG, auch als data:-URI>", "unterschrieben_von": "Herr Muster",
  "positionen": [
    {"client_uuid": "9a1b…", "artikel_id": 5, "beschreibung": "…", "menge": "2", "einzelpreis": "5.00",
     "rabatt": "0", "steuersatz": "19", "position": 1}
  ]
}
```

* Wiederholtes Senden mit derselben `client_uuid` legt nichts doppelt an (201 beim Anlegen, danach 200).
* Positionen werden über ihre `client_uuid` zugeordnet; fehlende Felder werden aus dem Artikel ergänzt.
* Mit Unterschrift wird ein offener Auftrag automatisch „unterschrieben“.
* Für steuerbefreite Kunden erzwingt der Server 0 % MwSt.
* Bereits abgerechnete Aufträge bleiben unverändert; der Aufruf liefert nur den aktuellen Stand.
* Summen und die Auftragsnummer vergibt der Server.

## Anmeldung

Die Prüfung entspricht der Weboberfläche (lokal oder LDAP). Nach 5 Fehlversuchen innerhalb von 15 Minuten
wird die Kombination aus Benutzername und IP-Adresse gesperrt (429), nicht der Benutzer insgesamt.
Der Signierschlüssel der Tokens wird aus `SECRET_KEY` abgeleitet; mit `API_TOKEN_SCHLUESSEL` in der `.env`
lässt er sich getrennt setzen (ein Wechsel macht alle ausgegebenen Tokens ungültig).
