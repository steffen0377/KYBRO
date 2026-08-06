<?php
require_once __DIR__ . '/../includes/auth.php';
require_once __DIR__ . '/../includes/functions.php';
require_once __DIR__ . '/../includes/license.php';
require_login();
require_module_license('warenwirtschaft');
require_once __DIR__ . '/../vendor/autoload.php';

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

$html = include __DIR__ . '/../includes/pdf_template.php';

$options = new Options();
$options->set('isRemoteEnabled', false);
$dompdf = new Dompdf($options);
$dompdf->loadHtml($html);
$dompdf->setPaper('A4', 'portrait');
$dompdf->render();
$dompdf->stream($doc['order_number'] . '.pdf', ['Attachment' => false]);
