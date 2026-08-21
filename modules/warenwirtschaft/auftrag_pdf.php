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
$stmt = $pdo->prepare('SELECT o.*, c.company, c.first_name, c.last_name, c.street, c.zip, c.city FROM orders o JOIN customers c ON c.id=o.customer_id WHERE o.id=?');
$stmt->execute([(int)($_GET['id'] ?? 0)]);
$doc = $stmt->fetch();
if (!$doc) { die('Auftrag nicht gefunden.'); }

$itemStmt = $pdo->prepare('SELECT * FROM order_items WHERE order_id=? ORDER BY position');
$itemStmt->execute([$doc['id']]);
$items = $itemStmt->fetchAll();

$company = company_settings();
$docLabel = 'Auftrag';
$docNumberField = 'order_number';
$dateField = 'order_date'; $dateLabel = 'Auftragsdatum';
$secondDateField = 'signed_at'; $secondDateLabel = 'Unterschrieben am';

$html = include ROOT_PATH . '/includes/pdf_template.php';

$options = new Options();
$options->set('isRemoteEnabled', false);
$dompdf = new Dompdf($options);
$dompdf->loadHtml($html);
$dompdf->setPaper('A4', 'portrait');
$dompdf->render();

$pdfContent = apply_company_letterhead($dompdf->output(), $company);

header('Content-Type: application/pdf');
header('Content-Disposition: inline; filename="' . $doc['order_number'] . '.pdf"');
header('Content-Length: ' . strlen($pdfContent));
echo $pdfContent;
