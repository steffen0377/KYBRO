# KYBRO (Django)

Webbasierte Warenwirtschaft mit Artikel-, Lager-, Kunden-, Angebots-, Auftrags- und Rechnungsverwaltung,
Abonnements, PDF-Belegen mit E-Rechnung (ZUGFeRD) und einer Schnittstelle für mobile Endgeräte.
Dieses Projekt ersetzt die bisherige PHP-Anwendung (Repository `KYBRO`); es gibt keine Datenübernahme
und keinen Parallelbetrieb.

## Projektstand

Alle sechs Phasen der Ablösung sind umgesetzt. Offen sind nur die Abnahme durch den Fachanwender
(`docs/Abnahme.md`) und der erste Produktivbetrieb (`docs/Betrieb.md`).

| Phase | Inhalt | Stand |
| --- | --- | --- |
| 1 | Projekt, MariaDB, Login, Benutzer, Gruppen und Rechte | fertig |
| 2 | Stammdaten (Artikel, Kategorien, Kunden, Lieferanten) und Lager | fertig |
| 3 | Belege (Angebot, Auftrag, Rechnung) mit Nummern, Lagerbuchung, Seriennummern | fertig |
| 4 | PDF (WeasyPrint) und E-Rechnung (ZUGFeRD EN 16931) | fertig |
| 5 | Abonnements, Einstellungen, Lizenzen, LDAP, Mobile-API | fertig |
| 6 | Abnahme und Betrieb (Dokumentation, Dienste) | fertig, Abnahme offen |
| 7 | Personalverwaltung (Mitarbeiter, Verträge, Urlaub, Anwesenheit) | fertig |

Geplante Erweiterungen: Zahlungsabgleich, Versand von Angeboten und Rechnungen per E-Mail aus der
Anwendung (die SMTP-Einstellungen und der Versandbaustein `einstellungen/mail.py` sind vorbereitet).

## Entwicklung

Voraussetzung: Python 3.10 oder neuer. Für die PDF-Erzeugung braucht WeasyPrint unter Ubuntu
`libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu fonts-liberation`.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # mysqlclient braucht libmariadb-dev, siehe requirements.txt
cp .env.example .env              # Werte anpassen, SECRET_KEY setzen
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Ohne `DB_NAME` in der `.env` läuft die Anwendung lokal auf SQLite. Für MariaDB `DB_NAME`, `DB_USER`,
`DB_PASSWORD` und `DB_HOST` setzen; die Datenbank muss mit `CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci`
angelegt sein. Die Anwendung ist gegen SQLite und MariaDB 10.11 getestet.

Nach dem ersten Start: **Einstellungen › Firma**. Die Lizenzprüfung ist vorbereitet, aber standardmäßig aus; sie
wird nur mit `LIZENZ_PRUEFUNG=True` in der `.env` aktiv (dann Lizenzen unter Einstellungen › Lizenzen anlegen). Die Schritte stehen in `docs/Betrieb.md`.

Tests ausführen (die Lizenzprüfung ist standardmäßig aus, eigene Tests prüfen sie):

```bash
python manage.py test
```

## Aufbau

| Verzeichnis | Zweck |
| --- | --- |
| `config/` | Einstellungen, URL-Wurzel, WSGI/ASGI |
| `accounts/` | Benutzer, Anmeldung (lokal/LDAP), Gruppen und Modulrechte |
| `core/` | Layout mit Seitenmenü, Dashboard, gemeinsame Formularbausteine, Bootstrap |
| `stammdaten/` | Artikel (Sonderpreise, Abo-Preismodelle), Kategorien, Kunden, Lieferanten |
| `lager/` | Lagerbewegungen, Wareneingang, Inventur, Seriennummern |
| `belege/` | Angebote, Aufträge, Rechnungen, Abonnements, PDF und ZUGFeRD |
| `einstellungen/` | Firmendaten, Nummernkreise, SMTP, Formulareinstellungen, Lizenzen, Anmeldeverfahren |
| `api/` | Mobile-API (JSON, Token), siehe `api/README.md` |
| `deploy/` | Beispiele für systemd, nginx (Standard) und Apache |
| `docs/` | Betriebsanleitung und Abnahmeliste |

## Wichtige Regeln der Fachlogik

* **Belegnummern** bestehen aus Präfix, Jahr und vierstelliger Nummer (`RE-2026-0001`); der Zähler beginnt jedes
  Jahr bei 1. Die Vergabe ist bei gleichzeitigen Zugriffen sicher (Zeilensperre, unter MariaDB geprüft).
* **Beträge** werden mit `Decimal` gerechnet; Zeilensummen werden gerundet, die Steuer je Steuersatz auf die
  Summe der Zeilen. PDF und E-Rechnung verwenden dieselben Summen.
* **Lager:** Eine Rechnung bucht beim Anlegen aus; Änderungen am Entwurf buchen neu, Löschen oder Stornieren eines
  Entwurfs stellt den Bestand wieder her. Seriennummernartikel werden erst bei der Zuordnung der Seriennummer
  ausgebucht. Ausgestellte Rechnungen lassen sich nicht mehr ändern, löschen oder in den Entwurf zurücksetzen.
* **Abonnements** entstehen, wenn eine Rechnung zum ersten Mal den Entwurf verlässt. Der Befehl
  `python manage.py abo_rechnungen_erzeugen` (täglich per Timer) legt Entwurfsrechnungen fälliger Abos an und
  ist wiederholbar, ohne Doppelrechnungen zu erzeugen.
* **Steuerbefreite Kunden** erhalten durchgehend 0 % MwSt.; in der E-Rechnung als Kategorie E mit Befreiungsgrund.
* **Rechte:** je Modul Lesen/Schreiben über Gruppen; Administratoren dürfen alles; Einstellungen nur Administratoren.

## Layout und Menü

`core/templates/base.html` ist das gemeinsame Layout; jede Seite erweitert es mit `{% extends "base.html" %}`.
Das Menü steht als Daten in `core/navigation.py`: Einträge erscheinen nur mit Leserecht auf das jeweilige Modul,
Administrationspunkte nur für Administratoren. Bootstrap und die Icons liegen lokal unter
`core/static/core/vendor/`, es werden keine externen Server angesprochen.

## Rechte

Jedes Modul (Artikel, Lager, Kunden, ...) hat die Rechte `<modul>_lesen` und `<modul>_schreiben`; Schreibrecht
schließt Lesen ein. Die Modulliste steht in `accounts/modules.py`; ein neues Modul braucht dort einen Eintrag und
danach `python manage.py makemigrations accounts`. Views schützen Sie mit `accounts.mixins.ModulRechtMixin`
(Attribut `modul`; lesende Anfragen brauchen das Leserecht, alle anderen das Schreibrecht) oder mit
`AdminRequiredMixin`.

## Benutzer und Gruppen

Administratoren verwalten Benutzer und Gruppen im Menü „Einstellungen“. Benutzer werden nicht gelöscht, sondern
deaktiviert, damit Belege und Lagerbuchungen ihren Bearbeiter weiterhin nennen können. Ein Administrator kann sich
weder selbst die Rolle entziehen noch das eigene Konto deaktivieren. Das erste Administratorkonto entsteht mit
`python manage.py createsuperuser`.
