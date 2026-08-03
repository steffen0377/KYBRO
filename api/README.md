# Mobile API

Diese API ist die Grundlage für die spätere iOS/Android-App (offline-fähig,
mit Vor-Ort-Unterschrift für Aufträge).

## Setup

1. Migration einspielen: `database/migrations/migration_011_orders.sql`
2. In `config.local.php` (nicht versioniert) einen eigenen JWT-Schlüssel setzen:
   ```php
   define('JWT_SECRET', 'ein-langer-zufälliger-schlüssel');
   ```
   Ohne diesen Eintrag wird ein Platzhalter-Schlüssel verwendet – **für den
   Produktivbetrieb unbedingt überschreiben**, da sonst jeder mit Kenntnis
   des Platzhalters gültige Tokens fälschen könnte.

## Endpunkte

| Endpoint          | Methode | Zweck                                              |
|-------------------|---------|-----------------------------------------------------|
| `api/auth.php`    | POST    | Login, gibt Bearer-Token zurück                     |
| `api/orders.php`  | GET     | Aufträge lesen (Liste, Einzelauftrag, Delta via `since`) |
| `api/orders.php`  | POST    | Auftrag/Positionen/Unterschrift synchronisieren     |

Alle Endpunkte außer `auth.php` erwarten den Header:
`Authorization: Bearer <token>`

## Antwortformat

Erfolg: `{ "success": true, "data": ... }`
Fehler: `{ "success": false, "error": "..." }`

## Offline-Sync-Prinzip

Die App vergibt für jeden Auftrag und jede Position eine `client_uuid`
selbst (z. B. UUID v4), bevor sie synchronisiert. Der Server nutzt diese
UUID, um bei wiederholten Sync-Versuchen (z. B. nach Verbindungsabbruch)
keine doppelten Datensätze anzulegen.

## Noch offen (nächste Schritte)

- Endpunkte für `customers.php` und `articles.php` (Stammdaten für die App,
  damit Aufträge offline mit gültigen IDs angelegt werden können)
- Rechnungserstellung aus einem abgeschlossenen Auftrag
- Rate-Limiting / Brute-Force-Schutz auf `api/auth.php`
