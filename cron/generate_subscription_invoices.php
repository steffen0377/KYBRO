<?php
// Erzeugt für alle fälligen Abonnements Entwurfs-Rechnungen (Status
// 'entwurf'), die anschließend im Modul "Abonnements" bzw. "Rechnungen"
// manuell geprüft und freigegeben werden müssen. next_billing_date wird
// bewusst erst bei der Freigabe fortgeschrieben (siehe
// advance_subscription_billing_date() in includes/functions.php), wodurch
// dieses Skript idempotent ist und beliebig oft pro Tag laufen kann.
//
// Für den Betrieb per Cron aufrufen, z.B. täglich um 05:00 Uhr:
//   0 5 * * * php /var/www/KYBRO/cron/generate_subscription_invoices.php >> /var/log/kybro/subscription_invoices.log 2>&1

// Nur über die Kommandozeile ausführbar, nicht per HTTP-Aufruf.
if (PHP_SAPI !== 'cli') {
    http_response_code(403);
    die("Dieses Skript darf nur über die Kommandozeile (CLI) ausgeführt werden.\n");
}

define('ROOT_PATH', dirname(__DIR__));
require_once ROOT_PATH . '/includes/functions.php';

// db() wird normalerweise über includes/auth.php mitgeladen, das dieses
// CLI-Skript bewusst NICHT einbindet (kein Login im Cron-Kontext nötig).
// Falls db() dadurch hier noch nicht bekannt ist: Pfad zur Datei, die db()
// tatsächlich definiert, unten anpassen (z.B. includes/db.php).
if (!function_exists('db')) {
    require_once ROOT_PATH . '/includes/db.php';
}

$pdo = db();

try {
    $created = generate_subscription_invoice_drafts($pdo);
} catch (Exception $e) {
    fwrite(STDERR, '[' . date('Y-m-d H:i:s') . "] Fehler: " . $e->getMessage() . "\n");
    exit(1);
}

if (!$created) {
    echo '[' . date('Y-m-d H:i:s') . "] Keine fälligen Abo-Rechnungen zu erzeugen.\n";
    exit(0);
}

echo '[' . date('Y-m-d H:i:s') . '] ' . count($created) . " Entwurfs-Rechnung(en) erzeugt:\n";
foreach ($created as $c) {
    echo "  - {$c['invoice_number']} (Rechnung #{$c['invoice_id']}, Abo #{$c['subscription_id']})\n";
}
