# Warenwirtschaft – Installationsanleitung (Ubuntu Server + MariaDB)

Eine PHP-basierte Warenwirtschaft mit Artikel-, Lager-, Kunden-, Angebots- und
Rechnungsverwaltung inkl. Benutzerlogin und PDF-Export.

## 1. Voraussetzungen installieren

```bash
sudo apt update
sudo apt install apache2 mariadb-server php php-mysql php-mbstring php-xml php-gd php-curl unzip curl
```

Composer installieren (für die PDF-Bibliothek dompdf):
```bash
curl -sS https://getcomposer.org/installer | php
sudo mv composer.phar /usr/local/bin/composer
```

Apache-Rewrite-Modul aktivieren (für den .htaccess-Schutz):
```bash
sudo a2enmod rewrite
sudo systemctl restart apache2
```

## 2. Datenbank einrichten

```bash
sudo mysql_secure_installation
sudo mysql -u root -p
```

In der MariaDB-Shell:
```sql
CREATE DATABASE warenwirtschaft CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ww_user'@'localhost' IDENTIFIED BY 'HIER_SICHERES_PASSWORT';
GRANT ALL PRIVILEGES ON warenwirtschaft.* TO 'ww_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Schema importieren:
```bash
mysql -u ww_user -p warenwirtschaft < database/schema.sql
```

## 3. Anwendung auf den Server kopieren

```bash
# Projektordner z.B. nach /var/www/warenwirtschaft kopieren
sudo mkdir -p /var/www/warenwirtschaft
sudo cp -r ./* /var/www/warenwirtschaft/
cd /var/www/warenwirtschaft
```

Konfigurationsdatei anlegen:
```bash
cp config/config.example.php config/config.php
nano config/config.php
```
Trage dort `DB_USER`, `DB_PASS` und `APP_URL` (z.B. `https://warenwirtschaft.deine-domain.de`) ein.

Composer-Abhängigkeiten installieren:
```bash
composer install --no-dev
```

Rechte setzen:
```bash
sudo chown -R www-data:www-data /var/www/warenwirtschaft
sudo find /var/www/warenwirtschaft -type d -exec chmod 755 {} \;
sudo find /var/www/warenwirtschaft -type f -exec chmod 644 {} \;
sudo chmod 775 /var/www/warenwirtschaft/uploads   # Logo-Upload benötigt Schreibrecht für www-data
```

## 4. Apache virtuellen Host einrichten

```bash
sudo nano /etc/apache2/sites-available/warenwirtschaft.conf
```

Inhalt:
```apache
<VirtualHost *:80>
    ServerName warenwirtschaft.deine-domain.de
    DocumentRoot /var/www/warenwirtschaft

    <Directory /var/www/warenwirtschaft>
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/warenwirtschaft_error.log
    CustomLog ${APACHE_LOG_DIR}/warenwirtschaft_access.log combined
</VirtualHost>
```

Aktivieren:
```bash
sudo a2ensite warenwirtschaft.conf
sudo systemctl reload apache2
```

**Wichtig:** `AllowOverride All` ist nötig, damit die `.htaccess`-Dateien greifen,
die den Zugriff auf `config/`, `includes/`, `database/` und `vendor/` sperren.

### HTTPS einrichten (dringend empfohlen)
```bash
sudo apt install certbot python3-certbot-apache
sudo certbot --apache -d warenwirtschaft.deine-domain.de
```

## 5. Ersteinrichtung (Admin-Konto)

1. Im Browser aufrufen: `https://deine-domain.de/setup_admin.php`
2. Benutzername, Name und Passwort für das erste Admin-Konto festlegen.
3. **Danach die Datei `setup_admin.php` unbedingt vom Server löschen:**
   ```bash
   sudo rm /var/www/warenwirtschaft/setup_admin.php
   ```
4. Unter `login.php` anmelden.
5. Unter "Einstellungen" die Firmendaten (Adresse, Bankverbindung, USt-IdNr.,
   Nummernkreis-Präfixe) eintragen – diese erscheinen auf jedem PDF.

## 6. Funktionsüberblick

- **Artikel**: Verwaltung mit automatisch vergebener, 5-stelliger Artikelnummer
  (Pflichtfeld, z.B. 00001), EAN und HAN (Herstellerartikelnummer), Preisen,
  MwSt.-Satz, Mindestbestand, optionaler Seriennummern-Erfassung. Das
  Formular ist in zwei Registerkarten aufgeteilt: "Allgemein" und
  "Lieferanten" (dort können einem Artikel mehrere Lieferanten mit jeweils
  eigener Lieferanten-Artikelnummer und unserem HEK zugeordnet werden)
- **Lager**: Wareneingang buchen (mit oder ohne Seriennummern), Bestandskorrekturen (Inventur), vollständige Bewegungshistorie, Seriennummern-Verwaltung (defekt melden/entfernen)
- **Kunden**: Stammdatenverwaltung, aufgeteilt in drei Registerkarten:
  "Allgemein" (Adresse, Kontakt, USt-IdNr.), "Ansprechpartner" (beliebig
  viele Kontaktpersonen je Kunde mit Name, Vorname, Firma, Telefon,
  E-Mail) und "Buchhaltung" (Bankverbindung des Kunden, Summe der
  unbezahlten Rechnungen, die letzten 10 Angebote sowie die letzten 10
  Rechnungen mit direkter "Bezahlt"-Schaltfläche; unbezahlte
  Rechnungszeilen sind rosa, bezahlte hellgrün markiert)
- **Einkauf > Lieferanten**: Stammdatenverwaltung für Lieferanten (analog zu
  Kunden), Nummernkreis "L-00001"
- **Angebote**: Erstellen mit mehreren Positionen, PDF-Export, Umwandlung in Rechnung
  (reduziert dabei automatisch den Lagerbestand)
- **Rechnungen**: Erstellen (reduziert bei Neuanlage automatisch den Lagerbestand),
  Statusverwaltung (Entwurf/versendet/bezahlt/überfällig/storniert), PDF-Export.
  Bei Artikeln mit Seriennummern-Pflicht wirst du nach dem Speichern zur
  Seriennummern-Zuordnung weitergeleitet – der Lagerbestand wird erst danach reduziert.
- **Benutzer**: Admin kann weitere Benutzer mit Rolle "Benutzer" oder "Administrator" anlegen
- **Kategorien**: Artikel können mehreren Kategorien zugeordnet werden
  (Zuordnung im Artikel-Formular); Kategorien selbst können hierarchisch
  in Unterkategorien organisiert werden (verwaltet über "Einstellungen
  > Kategorien") und erscheinen als aufklappbare Menüpunkte unter
  "Artikel" in der Seitenleiste zum Filtern der Artikelliste
- **Einstellungen**: Firmendaten, Logo (wird in der linken Seitenleiste angezeigt),
  Bankverbindung, Nummernkreise (nur Admin)

## 7. Hinweise & bekannte Einschränkungen (MVP)

- Bearbeitung einer bereits gespeicherten Rechnung passt den Lagerbestand NICHT
  automatisch erneut an (nur bei Neuanlage). Für Korrekturen bitte das Lager-Modul nutzen.
- Nur Rechnungen im Status "Entwurf" können bearbeitet oder gelöscht werden.
- Es gibt aktuell keinen automatischen Datenbank-Backup-Mechanismus – richte
  regelmäßige `mysqldump`-Backups ein, z.B. per Cronjob:
  ```bash
  mysqldump -u ww_user -p warenwirtschaft > backup_$(date +%F).sql
  ```
- Die Anwendung ist für den Einsatz durch ein kleines Team ausgelegt (einfache
  Rollen: Benutzer/Administrator). Für komplexere Berechtigungen wäre eine Erweiterung nötig.

## 8. Regelmäßige Wartung

```bash
# System aktuell halten
sudo apt update && sudo apt upgrade

# Composer-Abhängigkeiten aktualisieren
cd /var/www/warenwirtschaft && composer update --no-dev
```
