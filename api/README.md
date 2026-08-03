# Mobile API

Diese API ist die Grundlage für die spätere iOS/Android-App (offline-fähig,
mit Vor-Ort-Unterschrift für Aufträge).

## Setup

1. Migrationen einspielen: `database/migrations/migration_011_orders.sql`
   (bei dir ggf. umbenannt zu `migration_012_orders.sql`),
   `migration_013_updated_at.sql`, `migration_014_rate_limit.sql`
2. In `config.local.php` (nicht versioniert) einen eigenen JWT-Schlüssel setzen:
   ```php
   define('JWT_SECRET', 'ein-langer-zufälliger-schlüssel');
   ```
   Ohne diesen Eintrag wird ein Platzhalter-Schlüssel verwendet – **für den
   Produktivbetrieb unbedingt überschreiben**, da sonst jeder mit Kenntnis
   des Platzhalters gültige Tokens fälschen könnte.

## Endpunkte

| Endpoint                    | Methode | Zweck                                                     |
|-----------------------------|---------|-------------------------------------------------------------|
| `api/auth.php`              | POST    | Login, gibt Bearer-Token zurück (rate-limited)               |
| `api/orders.php`            | GET     | Aufträge lesen (Liste, Einzelauftrag, Delta via `since`)     |
| `api/orders.php`            | POST    | Auftrag/Positionen/Unterschrift synchronisieren               |
| `api/orders_to_invoice.php` | POST    | Rechnung aus unterschriebenem/abgeschlossenem Auftrag erzeugen |
| `api/customers.php`         | GET     | Kunden lesen (Liste, Einzelkunde, Delta via `since`)          |
| `api/articles.php`          | GET     | Artikel lesen (Liste, Einzelartikel, Delta via `since`)       |

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

## Rate-Limiting

`api/auth.php` sperrt eine Kombination aus Benutzername + IP-Adresse nach
5 Fehlversuchen innerhalb von 15 Minuten (Tabelle `api_login_attempts`,
siehe `migration_014_rate_limit.sql`). Bewusst nicht rein pro Benutzername,
damit niemand durch gezielte Fehlversuche einen echten Account aussperren
kann.

## Noch offen (nächste Schritte)

- Löschen/Stornieren von Aufträgen per API (aktuell nur über das Web-Backend)
- Ausführlicheres Berechtigungsmodell, falls später mehrere Rollen
  unterschiedliche Rechte in der App bekommen sollen (aktuell: jeder
  eingeloggte Benutzer sieht alle Aufträge/Kunden/Artikel)
