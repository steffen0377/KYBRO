<?php
/**
 * Diagnose-Skript fuer die Briefbogen-Einbettung (FPDI)
 * -------------------------------------------------------
 * Laeuft unabhaengig von der Web-App direkt mit der echten
 * vendor/-Installation auf dem Server, um herauszufinden, ob das
 * Problem an der FPDI-Merge-Logik selbst liegt oder an etwas anderem
 * (z.B. abweichende FPDI-Version, defekte Briefbogen-Datei, o.ae.).
 *
 * Aufruf (im ROOT_PATH des Projekts, z.B. /var/www/KYBRO):
 *   php tools/diagnose_letterhead.php /pfad/zum/briefbogen.pdf
 *   php tools/diagnose_letterhead.php /pfad/zum/briefbogen.png
 *
 * Erzeugt eine Test-PDF-Datei tools/diagnose_output.pdf, die man sich
 * direkt anschauen kann, und gibt ausfuehrliche Diagnosewerte auf der
 * Konsole aus (u.a. installierte FPDI/FPDF-Version, Seitenzahl,
 * Seitengroessen).
 */

define('ROOT_PATH', dirname(__DIR__));
require_once ROOT_PATH . '/vendor/autoload.php';

use Dompdf\Dompdf;
use Dompdf\Options;
use setasign\Fpdi\Fpdi;

if ($argc < 2) {
    fwrite(STDERR, "Nutzung: php tools/diagnose_letterhead.php /pfad/zum/briefbogen.(pdf|png|jpg)\n");
    exit(1);
}

$letterheadPath = realpath($argv[1]);
if (!$letterheadPath || !is_readable($letterheadPath)) {
    fwrite(STDERR, "FEHLER: Briefbogen-Datei nicht gefunden oder nicht lesbar: {$argv[1]}\n");
    exit(1);
}

echo "=== Umgebung ===\n";
echo "PHP-Version: " . PHP_VERSION . "\n";

// Versuche, die installierte FPDI/FPDF-Version aus composer/installed.json zu lesen
$installedJsonPath = ROOT_PATH . '/vendor/composer/installed.json';
if (is_file($installedJsonPath)) {
    $installed = json_decode(file_get_contents($installedJsonPath), true);
    $packages = $installed['packages'] ?? $installed; // je nach Composer-Version
    foreach ($packages as $pkg) {
        if (in_array($pkg['name'] ?? '', ['setasign/fpdi', 'setasign/fpdf', 'dompdf/dompdf'], true)) {
            echo $pkg['name'] . ': ' . ($pkg['version'] ?? 'unbekannt') . "\n";
        }
    }
} else {
    echo "(vendor/composer/installed.json nicht gefunden - Versionsermittlung uebersprungen)\n";
}

echo "\n=== Schritt 1: Test-Inhalt per Dompdf erzeugen ===\n";
$html = '<html><body style="font-family: sans-serif;">
<h1>Diagnose-Testinhalt</h1>
<p>Position 1: Testartikel &nbsp; 10,00 EUR</p>
<table border="1" cellpadding="5"><tr><th>Beschreibung</th><th>Preis</th></tr><tr><td>Testartikel</td><td>10,00 EUR</td></tr></table>
</body></html>';

$options = new Options();
$options->set('isRemoteEnabled', false);
$dompdf = new Dompdf($options);
$dompdf->loadHtml($html);
$dompdf->setPaper('A4', 'portrait');
$dompdf->render();
$contentPdf = $dompdf->output();
echo "Dompdf-Ausgabe erzeugt: " . strlen($contentPdf) . " Bytes\n";

echo "\n=== Schritt 2: FPDI-Merge mit echtem Briefbogen ===\n";
require_once ROOT_PATH . '/includes/letterhead_builder.php';

try {
    $merged = apply_letterhead_to_pdf($contentPdf, $letterheadPath);
    $outFile = __DIR__ . '/diagnose_output.pdf';
    file_put_contents($outFile, $merged);
    echo "\nERFOLG: Zusammengefuehrtes PDF gespeichert unter: $outFile\n";
    echo "Groesse: " . strlen($merged) . " Bytes\n";
    echo "\nBitte diese Datei oeffnen und pruefen, ob sowohl der Briefbogen\n";
    echo "als auch der Testinhalt ('Diagnose-Testinhalt' / Tabelle) sichtbar sind.\n";
} catch (Throwable $e) {
    echo "\nFEHLER bei der Einbettung: " . $e->getMessage() . "\n";
    echo "in " . $e->getFile() . ":" . $e->getLine() . "\n";
    echo "\n" . $e->getTraceAsString() . "\n";
    exit(1);
}
