<?php
/**
 * GET /api/customers.php                          -> alle Kunden
 * GET /api/customers.php?since=2026-08-01T00:00:00 -> nur seit updated_at geänderte
 * GET /api/customers.php?id=123                    -> einzelner Kunde inkl. Ansprechpartner
 *
 * Reiner Lese-Endpunkt: Kunden werden aktuell nur im Web-Backend angelegt/
 * geändert, die App braucht sie lediglich zur Auswahl bei neuen Aufträgen.
 */
require_once __DIR__ . '/../includes/api_auth.php';

api_require_auth();

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    api_json_error('Nur GET erlaubt.', 405);
}

$pdo = db();

if (isset($_GET['id'])) {
    $customerId = (int)$_GET['id'];
    $stmt = $pdo->prepare('SELECT * FROM customers WHERE id = ?');
    $stmt->execute([$customerId]);
    $customer = $stmt->fetch();
    if (!$customer) {
        api_json_error('Kunde nicht gefunden.', 404);
    }
    $contactsStmt = $pdo->prepare('SELECT * FROM customer_contacts WHERE customer_id = ?');
    $contactsStmt->execute([$customerId]);
    $customer['contacts'] = $contactsStmt->fetchAll();
    api_json_success($customer);
}

if (!empty($_GET['since'])) {
    $stmt = $pdo->prepare('SELECT * FROM customers WHERE updated_at > ? ORDER BY updated_at ASC');
    $stmt->execute([$_GET['since']]);
} else {
    $stmt = $pdo->query('SELECT * FROM customers ORDER BY company ASC, last_name ASC');
}

api_json_success($stmt->fetchAll());
