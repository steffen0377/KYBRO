<?php
/**
 * POST /api/orders_to_invoice.php
 * Body: { "order_id": 123 }
 *
 * Erzeugt eine Rechnung aus einem Auftrag, analog zur bestehenden
 * "Rechnung erstellen"-Funktion in angebote.php, nur eben Auftrag -> Rechnung
 * statt Angebot -> Rechnung. Übernimmt Kunde und Positionen 1:1.
 *
 * Der Auftrag muss unterschrieben oder abgeschlossen sein - eine Rechnung
 * aus einem noch offenen/unbearbeiteten Auftrag zu erzeugen wäre fachlich
 * falsch (der Kunde hat ja noch nicht zugestimmt).
 */
require_once __DIR__ . '/../includes/api_auth.php';
require_once __DIR__ . '/../includes/license.php';

$auth = api_require_auth();
if (!has_module_license('warenwirtschaft')) {
    api_json_error('Fuer dieses Modul (Warenwirtschaft) liegt keine gueltige Lizenz vor.', 402);
}


if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    api_json_error('Nur POST erlaubt.', 405);
}

$body = api_read_json_body();
$orderId = (int)($body['order_id'] ?? 0);
if (!$orderId) {
    api_json_error('order_id ist erforderlich.', 400);
}

$pdo = db();

$orderStmt = $pdo->prepare('SELECT * FROM orders WHERE id = ?');
$orderStmt->execute([$orderId]);
$order = $orderStmt->fetch();
if (!$order) {
    api_json_error('Auftrag nicht gefunden.', 404);
}

if (!in_array($order['status'], ['unterschrieben', 'abgeschlossen'], true)) {
    api_json_error('Nur unterschriebene oder abgeschlossene Aufträge können in eine Rechnung überführt werden.', 409);
}

// Bereits eine Rechnung zu diesem Auftrag vorhanden? Dann diese zurückgeben
// statt eine zweite zu erzeugen (z. B. bei doppeltem Tap in der App ohne
// Internet, wo die Antwort der ersten Anfrage nicht ankam).
$existingInvoice = $pdo->prepare('SELECT * FROM invoices WHERE order_id = ?');
$existingInvoice->execute([$orderId]);
if ($invoice = $existingInvoice->fetch()) {
    $itemsStmt = $pdo->prepare('SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY position ASC');
    $itemsStmt->execute([$invoice['id']]);
    $invoice['items'] = $itemsStmt->fetchAll();
    api_json_success($invoice, 200);
}

$itemsStmt = $pdo->prepare('SELECT * FROM order_items WHERE order_id = ? ORDER BY position ASC');
$itemsStmt->execute([$orderId]);
$orderItems = $itemsStmt->fetchAll();

$pdo->beginTransaction();
try {
    $invoiceNumber = generate_next_invoice_number($pdo);

    $insertInvoice = $pdo->prepare('
        INSERT INTO invoices
            (invoice_number, offer_id, order_id, customer_id, invoice_date, due_date,
             status, notes, total_net, total_tax, total_gross, created_by)
        VALUES (?, ?, ?, ?, CURDATE(), DATE_ADD(CURDATE(), INTERVAL 14 DAY),
                \'entwurf\', ?, ?, ?, ?, ?)
    ');
    $insertInvoice->execute([
        $invoiceNumber,
        $order['offer_id'],
        $orderId,
        $order['customer_id'],
        $order['notes'],
        $order['total_net'],
        $order['total_tax'],
        $order['total_gross'],
        $auth['sub'],
    ]);
    $invoiceId = (int)$pdo->lastInsertId();

    $insertItem = $pdo->prepare('
        INSERT INTO invoice_items (invoice_id, article_id, position, description, quantity, unit_price, tax_rate)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ');
    foreach ($orderItems as $item) {
        $insertItem->execute([
            $invoiceId,
            $item['article_id'],
            $item['position'],
            $item['description'],
            $item['quantity'],
            $item['unit_price'],
            $item['tax_rate'],
        ]);
    }

    $pdo->prepare("UPDATE orders SET status = 'abgeschlossen' WHERE id = ?")->execute([$orderId]);

    $pdo->commit();
} catch (Throwable $e) {
    $pdo->rollBack();
    error_log('[API orders_to_invoice] Fehlgeschlagen: ' . $e->getMessage());
    api_json_error('Rechnung konnte nicht erzeugt werden.', 500);
}

$stmt = $pdo->prepare('SELECT * FROM invoices WHERE id = ?');
$stmt->execute([$invoiceId]);
$invoice = $stmt->fetch();
$itemsStmt = $pdo->prepare('SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY position ASC');
$itemsStmt->execute([$invoiceId]);
$invoice['items'] = $itemsStmt->fetchAll();

api_json_success($invoice, 201);

// Läuft innerhalb der bereits offenen Transaktion. LOCK TABLES ist hier
// bewusst NICHT verwendet, da es in MySQL/MariaDB eine laufende Transaktion
// implizit committen würde. SELECT ... FOR UPDATE sperrt die Zeile stattdessen
// nur bis zum Commit/Rollback der äußeren Transaktion.
function generate_next_invoice_number(PDO $pdo): string {
    $settings = $pdo->query('SELECT invoice_prefix, next_invoice_number FROM company_settings LIMIT 1 FOR UPDATE')->fetch();
    $number = $settings['invoice_prefix'] . str_pad((string)$settings['next_invoice_number'], 5, '0', STR_PAD_LEFT);
    $pdo->prepare('UPDATE company_settings SET next_invoice_number = next_invoice_number + 1')->execute();
    return $number;
}
