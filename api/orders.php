<?php
/**
 * GET  /api/orders.php                       -> Liste aller Aufträge
 * GET  /api/orders.php?since=2026-08-01T00:00:00 -> nur seit updated_at geänderte (Delta-Sync)
 * GET  /api/orders.php?id=123                -> Einzelner Auftrag inkl. Positionen
 * POST /api/orders.php                       -> Auftrag/Positionen/Unterschrift von der App hochladen
 *
 * Auth: Authorization: Bearer <token> (siehe api/auth.php)
 */
require_once __DIR__ . '/../includes/api_auth.php';
require_once __DIR__ . '/../includes/license.php';

$auth = api_require_auth();
if (!has_module_license('warenwirtschaft')) {
    api_json_error('Fuer dieses Modul (Warenwirtschaft) liegt keine gueltige Lizenz vor.', 402);
}


if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    handle_orders_get();
} elseif ($_SERVER['REQUEST_METHOD'] === 'POST') {
    handle_orders_post($auth);
} else {
    api_json_error('Methode nicht erlaubt.', 405);
}

function handle_orders_get(): void {
    $pdo = db();

    if (isset($_GET['id'])) {
        $orderId = (int)$_GET['id'];
        $stmt = $pdo->prepare('SELECT * FROM orders WHERE id = ?');
        $stmt->execute([$orderId]);
        $order = $stmt->fetch();
        if (!$order) {
            api_json_error('Auftrag nicht gefunden.', 404);
        }
        $itemsStmt = $pdo->prepare('SELECT * FROM order_items WHERE order_id = ? ORDER BY position ASC');
        $itemsStmt->execute([$orderId]);
        $order['items'] = $itemsStmt->fetchAll();
        api_json_success($order);
    }

    if (!empty($_GET['since'])) {
        $stmt = $pdo->prepare('SELECT * FROM orders WHERE updated_at > ? ORDER BY updated_at ASC');
        $stmt->execute([$_GET['since']]);
    } else {
        $stmt = $pdo->query('SELECT * FROM orders ORDER BY order_date DESC, id DESC');
    }
    $orders = $stmt->fetchAll();

    // Positionen für alle betroffenen Aufträge in einem Rutsch nachladen,
    // statt pro Auftrag einzeln zu fragen (relevant bei Sync mit vielen Aufträgen).
    if ($orders) {
        $ids = array_column($orders, 'id');
        $placeholders = implode(',', array_fill(0, count($ids), '?'));
        $itemsStmt = $pdo->prepare("SELECT * FROM order_items WHERE order_id IN ($placeholders) ORDER BY position ASC");
        $itemsStmt->execute($ids);
        $itemsByOrder = [];
        foreach ($itemsStmt->fetchAll() as $item) {
            $itemsByOrder[$item['order_id']][] = $item;
        }
        foreach ($orders as &$order) {
            $order['items'] = $itemsByOrder[$order['id']] ?? [];
        }
    }

    api_json_success($orders);
}

function handle_orders_post(array $auth): void {
    $pdo = db();
    $body = api_read_json_body();

    $clientUuid = trim($body['client_uuid'] ?? '');
    if ($clientUuid === '') {
        api_json_error('client_uuid ist erforderlich (von der App vergeben, für idempotenten Sync).', 400);
    }

    $required = ['customer_id', 'order_date', 'items'];
    foreach ($required as $field) {
        if (!isset($body[$field])) {
            api_json_error("Feld '$field' fehlt.", 400);
        }
    }

    // Idempotenz: Wurde dieser Auftrag (per client_uuid) schon einmal
    // gesynct, geben wir den bestehenden Datensatz zurück statt ihn
    // erneut anzulegen. Das fängt Doppel-Sends bei Netzwerk-Timeouts ab.
    $existing = $pdo->prepare('SELECT id FROM orders WHERE client_uuid = ?');
    $existing->execute([$clientUuid]);
    $existingId = $existing->fetchColumn();

    $pdo->beginTransaction();
    try {
        if ($existingId) {
            $orderId = (int)$existingId;
            update_order($pdo, $orderId, $body, $auth);
        } else {
            $orderId = insert_order($pdo, $body, $auth, $clientUuid);
        }
        sync_order_items($pdo, $orderId, $body['items']);
        recalculate_order_totals($pdo, $orderId);
        $pdo->commit();
    } catch (Throwable $e) {
        $pdo->rollBack();
        error_log('[API orders] Sync fehlgeschlagen: ' . $e->getMessage());
        api_json_error('Sync fehlgeschlagen, bitte erneut versuchen.', 500);
    }

    $stmt = $pdo->prepare('SELECT * FROM orders WHERE id = ?');
    $stmt->execute([$orderId]);
    $order = $stmt->fetch();
    $itemsStmt = $pdo->prepare('SELECT * FROM order_items WHERE order_id = ? ORDER BY position ASC');
    $itemsStmt->execute([$orderId]);
    $order['items'] = $itemsStmt->fetchAll();

    api_json_success($order, $existingId ? 200 : 201);
}

function insert_order(PDO $pdo, array $body, array $auth, string $clientUuid): int {
    $orderNumber = generate_next_order_number($pdo);

    $stmt = $pdo->prepare('
        INSERT INTO orders
            (order_number, offer_id, customer_id, order_date, status, notes,
             signature_path, signed_at, signed_by_name, client_uuid, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ');
    $stmt->execute([
        $orderNumber,
        $body['offer_id'] ?? null,
        $body['customer_id'],
        $body['order_date'],
        $body['status'] ?? 'offen',
        $body['notes'] ?? '',
        $body['signature_path'] ?? null,
        $body['signed_at'] ?? null,
        $body['signed_by_name'] ?? null,
        $clientUuid,
        $auth['sub'],
    ]);

    return (int)$pdo->lastInsertId();
}

function update_order(PDO $pdo, int $orderId, array $body, array $auth): void {
    // Ein bereits abgeschlossener/unterschriebener Auftrag wird durch einen
    // erneuten Sync-Versuch nicht mehr inhaltlich verändert, nur der Status
    // kann noch nachgezogen werden, falls die App das offline nachreicht.
    $stmt = $pdo->prepare('
        UPDATE orders SET
            status = ?, notes = ?, signature_path = COALESCE(?, signature_path),
            signed_at = COALESCE(?, signed_at), signed_by_name = COALESCE(?, signed_by_name)
        WHERE id = ?
    ');
    $stmt->execute([
        $body['status'] ?? 'offen',
        $body['notes'] ?? '',
        $body['signature_path'] ?? null,
        $body['signed_at'] ?? null,
        $body['signed_by_name'] ?? null,
        $orderId,
    ]);
}

function sync_order_items(PDO $pdo, int $orderId, array $items): void {
    foreach ($items as $item) {
        $itemUuid = trim($item['client_uuid'] ?? '');
        if ($itemUuid === '') {
            continue; // Position ohne UUID kann nicht idempotent gesynct werden.
        }
        $existing = $pdo->prepare('SELECT id FROM order_items WHERE client_uuid = ?');
        $existing->execute([$itemUuid]);
        $existingId = $existing->fetchColumn();

        if ($existingId) {
            $stmt = $pdo->prepare('
                UPDATE order_items SET article_id = ?, position = ?, description = ?,
                    quantity = ?, unit_price = ?, tax_rate = ?
                WHERE id = ?
            ');
            $stmt->execute([
                $item['article_id'] ?? null,
                $item['position'] ?? 0,
                $item['description'],
                $item['quantity'] ?? 1,
                $item['unit_price'] ?? 0,
                $item['tax_rate'] ?? 19,
                $existingId,
            ]);
        } else {
            $stmt = $pdo->prepare('
                INSERT INTO order_items
                    (order_id, article_id, position, description, quantity, unit_price, tax_rate, client_uuid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ');
            $stmt->execute([
                $orderId,
                $item['article_id'] ?? null,
                $item['position'] ?? 0,
                $item['description'],
                $item['quantity'] ?? 1,
                $item['unit_price'] ?? 0,
                $item['tax_rate'] ?? 19,
                $itemUuid,
            ]);
        }
    }
}

function recalculate_order_totals(PDO $pdo, int $orderId): void {
    $stmt = $pdo->prepare('SELECT quantity, unit_price, tax_rate FROM order_items WHERE order_id = ?');
    $stmt->execute([$orderId]);

    $net = 0.0;
    $tax = 0.0;
    foreach ($stmt->fetchAll() as $item) {
        $lineNet = $item['quantity'] * $item['unit_price'];
        $net += $lineNet;
        $tax += $lineNet * ($item['tax_rate'] / 100);
    }

    $pdo->prepare('UPDATE orders SET total_net = ?, total_tax = ?, total_gross = ? WHERE id = ?')
        ->execute([$net, $tax, $net + $tax, $orderId]);
}

function generate_next_order_number(PDO $pdo): string {
    // Nummernkreis analog zu Angeboten/Rechnungen, siehe company_settings.
    $pdo->exec('LOCK TABLES company_settings WRITE');
    try {
        $settings = $pdo->query('SELECT order_prefix, next_order_number FROM company_settings LIMIT 1')->fetch();
        $number = $settings['order_prefix'] . str_pad((string)$settings['next_order_number'], 5, '0', STR_PAD_LEFT);
        $pdo->prepare('UPDATE company_settings SET next_order_number = next_order_number + 1')->execute();
    } finally {
        $pdo->exec('UNLOCK TABLES');
    }
    return $number;
}
