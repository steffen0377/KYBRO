<?php
// Kopiere diese Datei nach config/config.php und trage deine Zugangsdaten ein.
// config/config.php sollte NIE ins Git-Repository oder öffentlich zugänglich sein!

define('DB_HOST', 'localhost');
define('DB_NAME', 'warenwirtschaft');
define('DB_USER', 'ww_user');
define('DB_PASS', 'BITTE_HIER_SICHERES_PASSWORT_EINTRAGEN');
define('DB_CHARSET', 'utf8mb4');

// Basis-URL der Anwendung (ohne abschließenden Slash), z.B. https://ww.meine-firma.de
define('APP_URL', 'http://localhost');

// Zeitzone
date_default_timezone_set('Europe/Berlin');

// Fehleranzeige im Produktivbetrieb deaktivieren
error_reporting(E_ALL);
ini_set('display_errors', '0'); // im Betrieb: '0', zum Debuggen kurzzeitig '1'
