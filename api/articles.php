<?php
/**
 * GET /api/articles.php                          -> alle aktiven Artikel
 * GET /api/articles.php?since=2026-08-01T00:00:00 -> nur seit updated_at geänderte
 * GET /api/articles.php?id=123                    -> einzelner Artikel
 *
 * Liefert bewusst nur aktive Artikel (active = 1) für die Positionsauswahl
 * in der App, sofern nicht per ?id= gezielt ein einzelner Artikel geladen
 * wird (z. B. um einen bereits verwendeten, inzwischen deaktivierten
 * Artikel in einem bestehenden Auftrag trotzdem anzeigen zu können).
 */
require_once __DIR__ . '/../includes/api_auth.php';

api_require_auth();

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    api_json_error('Nur GET erlaubt.', 405);
}

$pdo = db();

if (isset($_GET['id'])) {
    $stmt = $pdo->prepare('SELECT * FROM articles WHERE id = ?');
    $stmt->execute([(int)$_GET['id']]);
    $article = $stmt->fetch();
    if (!$article) {
        api_json_error('Artikel nicht gefunden.', 404);
    }
    api_json_success($article);
}

if (!empty($_GET['since'])) {
    $stmt = $pdo->prepare('SELECT * FROM articles WHERE updated_at > ? ORDER BY updated_at ASC');
    $stmt->execute([$_GET['since']]);
} else {
    $stmt = $pdo->query("SELECT * FROM articles WHERE active = 1 ORDER BY name ASC");
}

api_json_success($stmt->fetchAll());
