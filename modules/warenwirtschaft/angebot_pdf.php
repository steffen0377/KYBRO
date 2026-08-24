<?php
require_once $_SERVER['DOCUMENT_ROOT'] . '/includes/auth.php';
require_once ROOT_PATH . '/includes/functions.php';
require_once ROOT_PATH . '/includes/license.php';
require_once ROOT_PATH . '/includes/letterhead_builder.php';
require_login();
require_module_license('warenwirtschaft');
require_once ROOT_PATH . '/vendor/autoload.php';

use Dompdf\Dompdf;
use Dompdf\Options;

$pdo = db();
$stmt = $pdo->prepare('SELECT o.*, c.company, c.first_name, c.last_name, c.street, c.zip, c.city FROM offers o JOIN customers c ON c.id=o.customer_id WHERE o.id=?');
$stmt->execute([(int)($_GET['id'] ?? 0)]);
$doc = $stmt->fetch();
if (!$doc) { die('Angebot nicht gefunden.'); }

$itemStmt = $pdo->prepare('SELECT * FROM offer_items WHERE offer_id=? ORDER BY position');
$itemStmt->execute([$doc['id']]);
$items = $itemStmt->fetchAll();

$company = company_settings();
$scope = 'angebot';
$docLabel = 'Angebot';
$docNumberField = 'offer_number';
$dateField = 'offer_date'; $dateLabel = 'Angebotsdatum';
$secondDateField = 'valid_until'; $secondDateLabel = 'Gültig bis';

$html = include ROOT_PATH . '/includes/pdf_template.php';

$options = new Options();
$options->set('isRemoteEnabled', false);
$dompdf = new Dompdf($options);
$dompdf->loadHtml($html);
$dompdf->setPaper('A4', 'portrait');
$dompdf->render();

if ($showPageNumber) {
    render_pdf_page_number($dompdf, $marginBottom, $marginRight);
}

$pdfContent = apply_company_letterhead($dompdf->output(), $company);

header('Content-Type: application/pdf');
header('Content-Disposition: inline; filename="' . $doc['offer_number'] . '.pdf"');
header('Content-Length: ' . strlen($pdfContent));
echo $pdfContent;
