<?php
require_once __DIR__ . '/includes/auth.php';
require_once __DIR__ . '/includes/functions.php';
require_login();
require_once __DIR__ . '/vendor/autoload.php';

use Dompdf\Dompdf;
use Dompdf\Options;

$pdo = db();
$stmt = $pdo->prepare('SELECT i.*, c.company, c.first_name, c.last_name, c.street, c.zip, c.city FROM invoices i JOIN customers c ON c.id=i.customer_id WHERE i.id=?');
$stmt->execute([(int)($_GET['id'] ?? 0)]);
$doc = $stmt->fetch();
if (!$doc) { die('Rechnung nicht gefunden.'); }

$itemStmt = $pdo->prepare('SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY position');
$itemStmt->execute([$doc['id']]);
$items = $itemStmt->fetchAll();

$company = company_settings();
$docLabel = 'Rechnung';
$docNumberField = 'invoice_number';
$dateField = 'invoice_date'; $dateLabel = 'Rechnungsdatum';
$secondDateField = 'due_date'; $secondDateLabel = 'Fällig bis';

$html = include __DIR__ . '/includes/pdf_template.php';

$options = new Options();
$options->set('isRemoteEnabled', false);
$dompdf = new Dompdf($options);
$dompdf->loadHtml($html);
$dompdf->setPaper('A4', 'portrait');
$dompdf->render();

$wantsZugferd = isset($_GET['zugferd']) && $_GET['zugferd'] === '1';

if (!$wantsZugferd) {
    $dompdf->stream($doc['invoice_number'] . '.pdf', ['Attachment' => false]);
    exit;
}

// ---------- ZUGFeRD-Export (PDF/A-3 mit eingebettetem XML) ----------
require_once __DIR__ . '/includes/zugferd_builder.php';

$zugferdDocument = build_zugferd_document($doc, $items, $company);
$pdfContent = embed_zugferd_into_pdf($zugferdDocument, $dompdf->output());

header('Content-Type: application/pdf');
header('Content-Disposition: attachment; filename="' . $doc['invoice_number'] . '_zugferd.pdf"');
header('Content-Length: ' . strlen($pdfContent));
echo $pdfContent;
