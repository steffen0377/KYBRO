# Betrieb von KYBRO (Ubuntu, MariaDB, nginx, gunicorn)

Diese Anleitung beschreibt die Installation auf einem Ubuntu-Server mit MariaDB und nginx als
Reverse-Proxy. Die Anwendung selbst läuft mit gunicorn als Systemdienst. Die Beispieldateien liegen
im Ordner `deploy/`. Wer lieber Apache einsetzt, findet eine Vorlage in `deploy/alternativ-apache-kybro.conf`
(Befehle am Ende von Abschnitt 4).

## 1. Pakete

```bash
sudo apt install python3-venv python3-dev build-essential pkg-config libmariadb-dev \
                 mariadb-server nginx certbot python3-certbot-nginx libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu fonts-liberation
```

## 2. Datenbank

```sql
CREATE DATABASE kybro CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'kybro'@'localhost' IDENTIFIED BY 'ein-starkes-passwort';
GRANT ALL PRIVILEGES ON kybro.* TO 'kybro'@'localhost';
```

## 3. Anwendung

```bash
sudo useradd --system --create-home --home-dir /opt/kybro --shell /usr/sbin/nologin kybro
# Code per git nach /opt/kybro legen (git clone bzw. git am der Patch-Dateien)
cd /opt/kybro
sudo -u kybro python3 -m venv venv
sudo -u kybro venv/bin/pip install -r requirements.txt
sudo -u kybro cp .env.example .env     # danach bearbeiten (siehe unten)
sudo chmod 600 .env
sudo -u kybro mkdir -p media
sudo -u kybro venv/bin/python manage.py migrate
sudo -u kybro venv/bin/python manage.py collectstatic --noinput
sudo -u kybro venv/bin/python manage.py createsuperuser
```

Pflichtwerte der `.env` im Produktivbetrieb: `DEBUG=False`, `SECRET_KEY` (zufällig, geheim halten und sichern –
aus ihm werden auch die Verschlüsselung der gespeicherten Passwörter und die API-Tokens abgeleitet),
`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS=https://kybro.example.de`, `TRUST_PROXY_SSL_HEADER=True` und die
`DB_*`-Werte.

> **Wichtig:** Wird der `SECRET_KEY` geändert, lassen sich die in den Einstellungen gespeicherten Passwörter
> (SMTP, LDAP-Bind) nicht mehr entschlüsseln und müssen neu eingegeben werden. Alle angemeldeten Sitzungen
> und API-Tokens werden ungültig.

## 4. Dienste

```bash
sudo cp deploy/kybro.service deploy/kybro-abos.service deploy/kybro-abos.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kybro kybro-abos.timer
# Zertifikat zuerst holen (Let's Encrypt), solange nginx die Konfiguration noch nicht braucht:
sudo certbot certonly --standalone -d kybro.example.de \
     --pre-hook "systemctl stop nginx" --post-hook "systemctl start nginx"
sudo cp deploy/nginx-kybro.conf /etc/nginx/sites-available/kybro        # Servername anpassen
sudo ln -s /etc/nginx/sites-available/kybro /etc/nginx/sites-enabled/kybro
sudo nginx -t && sudo systemctl reload nginx
```

gunicorn lauscht nur auf `127.0.0.1:8000` und ist damit von außen nicht erreichbar; nginx liefert `/static/`
direkt aus `staticfiles/` und reicht alles andere weiter. Soll der Server nur KYBRO ausliefern, entfernst du die Standardseite von nginx (`sudo rm /etc/nginx/sites-enabled/default`).

Alternative Apache: `deploy/alternativ-apache-kybro.conf` nach `/etc/apache2/sites-available/kybro.conf` kopieren,
dann `sudo a2enmod proxy proxy_http headers ssl rewrite && sudo a2ensite kybro && sudo systemctl reload apache2`
(Paket `apache2` statt `nginx`).

Der Timer `kybro-abos` erzeugt täglich um 05:00 Uhr die Entwurfsrechnungen fälliger Abonnements
(`manage.py abo_rechnungen_erzeugen`). Der Lauf ist wiederholbar, ohne Doppelrechnungen zu erzeugen.
Die Entwürfe müssen anschließend in der Anwendung geprüft und freigegeben werden.

## 5. Erste Einrichtung in der Anwendung

1. Als Administrator anmelden.
2. **Lizenzen (optional):** Die Lizenzprüfung ist vorbereitet, aber standardmäßig abgeschaltet; es ist keine Lizenz
   nötig. Zum Aktivieren `LIZENZ_PRUEFUNG=True` in die `.env` setzen und unter Einstellungen › Lizenzen eine Lizenz
   mit dem Modul „Warenwirtschaft“ anlegen, sonst sind die Fachmodule gesperrt (Hinweis „Keine gültige Lizenz“).
3. **Einstellungen › Firma:** Firmen- und Bankdaten, Präfixe, Zahlungsziel. Die Firmendaten gehen in die PDFs und in die
   E-Rechnung (ZUGFeRD) ein. **Einstellungen › Briefbogen:** Logo und Textblöcke (Anschrift, Bankverbindung, Fußzeile) als frei
   platzierbare Elemente anlegen; „Vorschau (PDF)“ zeigt die Positionen. Platzhalter wie `%CompanyName%` oder `%CompanyIban%`
   werden bei jedem PDF durch die aktuellen Firmendaten ersetzt. Wer den eingebauten Firmenblock in der Fußzeile nicht
   braucht, schaltet ihn unter Einstellungen › Formulare („Firmenblock in der Fußzeile“) ab.
4. **Einstellungen › E-Mail:** SMTP-Zugang eintragen und mit „Testmail“ prüfen.
5. **Einstellungen › Formulare:** Layout und Texte der PDFs.
6. **Einstellungen › Anmeldung:** optional LDAP. „Nur LDAP“ lässt lokale Administratoren nur dann zu,
   wenn der LDAP-Server nicht erreichbar ist (Notfallzugang, wird protokolliert).
7. Benutzer und Gruppen anlegen (Menü „Benutzer“, „Gruppen und Rechte“).

## 5a. Testbetrieb und Livegang

Jede neue Installation startet im **Testbetrieb**: Oben in der Anwendung steht ein gelber Hinweis. In dieser Phase
können alle Nutzer testen und Verbesserungswünsche äußern. Firmendaten, Benutzer und alle Einstellungen
pflegst du schon jetzt so, wie sie später gelten sollen.

Zum Produktivstart unter **Einstellungen › Firma** (oder über den Hinweis) auf „Live-Betrieb aktivieren“ klicken.
Vorher eine Datenbanksicherung erstellen (`mysqldump --single-transaction kybro > vor-livegang.sql`). Nach der
Bestätigung (Haken und das Wort LIVE) werden gelöscht: Angebote, Aufträge, Rechnungen, Abonnements,
Artikel, Kategorien, Kunden, Lieferanten, Lagerbewegungen, Seriennummern, Unterschriften, Belegnummern-Zähler und
API-Anmeldeprotokolle. Erhalten bleiben Firmendaten, Briefbogen-Elemente, Präfixe, SMTP, Formulare, Lizenzen, LDAP,
Benutzer, Gruppen und die Personalverwaltung (Mitarbeiter, Verträge, Urlaub, Anwesenheit). Danach verschwindet der Hinweis, und die Funktion ist nicht mehr aufrufbar. Nur
Administratoren können den Wechsel auslösen. Das Ergebnis steht im Protokoll (`journalctl -u kybro`, Eintrag `[LIVE]`).

## 6. Sicherung und Aktualisierung

* Sichern: Datenbank (`mysqldump --single-transaction kybro`), Ordner `media/` (Briefbogen-Bilder, Unterschriften)
  und die Datei `.env` (enthält den `SECRET_KEY`).
* Aktualisieren:

  ```bash
  cd /opt/kybro
  sudo -u kybro git am /tmp/*.patch            # bzw. git pull
  sudo -u kybro venv/bin/pip install -r requirements.txt
  sudo -u kybro venv/bin/python manage.py migrate
  sudo -u kybro venv/bin/python manage.py collectstatic --noinput
  sudo systemctl restart kybro
  ```

* Protokolle: `journalctl -u kybro` (Anwendung), `journalctl -u kybro-abos` (Abo-Lauf).

## 7. Hinweise zur Sicherheit

* Die Anwendung nur über HTTPS betreiben (das nginx-Beispiel leitet um und setzt HSTS).
* `/media` nicht veröffentlichen: Briefbogen und Unterschriften werden nur über die Anwendung ausgeliefert.
* Die Mobile-API (`/api/v1/`) nutzt Token-Anmeldung mit Sperre nach 5 Fehlversuchen je Benutzer und IP-Adresse.
  Beschreibung: `api/README.md`.

## Logo der Anmeldeseite

Das Logo ist eine feste Datei und nicht in der Oberfläche änderbar: `core/static/core/img/logo.svg` (im Git-Projekt
ablegen und einchecken). Fehlt die Datei, erscheint nur der Text „KYBRO – das Firmenportal“. Nach einem Austausch
`collectstatic` ausführen und den Browser-Cache leeren. Das Bild wird auf höchstens 90 Pixel Höhe skaliert.
