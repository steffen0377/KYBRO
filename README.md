# KYBRO (Django)

Warenwirtschaft mit Artikel-, Lager-, Kunden-, Angebots- und Rechnungsverwaltung.
Dieses Projekt ersetzt schrittweise die bisherige PHP-Anwendung (Repository `KYBRO`).
Die Ablösung folgt dem Migrationskonzept in sechs Phasen; der aktuelle Stand steht
im Abschnitt "Projektstand".

## Projektstand

Phase 1 (Grundgerüst) ist in Arbeit.

| Phase | Inhalt | Stand |
| --- | --- | --- |
| 1 | Projekt, MariaDB, Login, Benutzer, Gruppen und Rechte | in Arbeit |
| 2 | Stammdaten und Lager | offen |
| 3 | Belege (Angebot, Auftrag, Rechnung) | offen |
| 4 | PDF und E-Rechnung (ZUGFeRD) | offen |
| 5 | Abos, Verwaltung, Mobile-API | offen |
| 6 | Abnahme und Betrieb | offen |

## Entwicklung

Voraussetzung: Python 3.10 oder neuer.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # mysqlclient braucht libmariadb-dev, siehe requirements.txt
cp .env.example .env              # Werte anpassen, SECRET_KEY setzen
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Ohne `DB_NAME` in der `.env` läuft die Anwendung lokal auf SQLite. Für MariaDB
`DB_NAME`, `DB_USER`, `DB_PASSWORD` und `DB_HOST` setzen; die Datenbank muss mit
`CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci` angelegt sein.

Tests ausführen:

```bash
python manage.py test
```

## Aufbau

| Verzeichnis | Zweck |
| --- | --- |
| `config/` | Einstellungen, URL-Wurzel, WSGI/ASGI |
| `accounts/` | Benutzer, Anmeldung, Gruppen und Modulrechte |
| `core/` | Basis-Layout mit Seitenmenü, Dashboard, gemeinsame Styles und Bootstrap |

## Layout und Menü

`core/templates/base.html` ist das gemeinsame Layout (Seitenmenü, Kopfzeile,
Meldungen); jede Seite erweitert es mit `{% extends "base.html" %}`. Das Menü
steht als Daten in `core/navigation.py`: Einträge erscheinen nur mit
Leserecht auf das jeweilige Modul, Administrationspunkte nur für Administratoren.
Menüpunkte, deren Seite noch nicht existiert, sind ausgegraut. Bootstrap und die
Icons liegen lokal unter `core/static/core/vendor/`, es werden keine externen
Server angesprochen.

## Rechte

Jedes Modul (Artikel, Lager, Kunden, ...) hat die Rechte `<modul>_lesen` und
`<modul>_schreiben`; Schreibrecht schließt Lesen ein. Die Rechte werden Gruppen
zugewiesen, Benutzer erhalten sie über ihre Gruppen. Administratoren
(`is_superuser`) haben immer vollen Zugriff. Die Modulliste steht in
`accounts/modules.py`; ein neues Modul braucht dort einen Eintrag und danach
`python manage.py makemigrations accounts`.

Views schützt man mit `accounts.mixins.ModulRechtMixin` (Attribut `modul`; lesende
Anfragen brauchen das Leserecht, alle anderen das Schreibrecht) oder mit
`AdminRequiredMixin`.
