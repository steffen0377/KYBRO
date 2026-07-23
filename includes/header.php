<?php
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/functions.php';
require_login();
$u = current_user();
?>
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= isset($pageTitle) ? e($pageTitle) . ' – ' : '' ?>Warenwirtschaft</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
<link href="<?= APP_URL ?>/assets/css/style.css" rel="stylesheet">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-dark mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="<?= APP_URL ?>/index.php">📦 Warenwirtschaft</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#nav">
      <span class="navbar-toggler-icon"></span>
    </button>
    <div class="collapse navbar-collapse" id="nav">
      <ul class="navbar-nav me-auto">
        <li class="nav-item"><a class="nav-link" href="<?= APP_URL ?>/index.php">Dashboard</a></li>
        <li class="nav-item"><a class="nav-link" href="<?= APP_URL ?>/artikel.php">Artikel</a></li>
        <li class="nav-item"><a class="nav-link" href="<?= APP_URL ?>/lager.php">Lager</a></li>
        <li class="nav-item"><a class="nav-link" href="<?= APP_URL ?>/kunden.php">Kunden</a></li>
        <li class="nav-item"><a class="nav-link" href="<?= APP_URL ?>/angebote.php">Angebote</a></li>
        <li class="nav-item"><a class="nav-link" href="<?= APP_URL ?>/rechnungen.php">Rechnungen</a></li>
        <?php if ($u['role'] === 'admin'): ?>
        <li class="nav-item"><a class="nav-link" href="<?= APP_URL ?>/benutzer.php">Benutzer</a></li>
        <li class="nav-item"><a class="nav-link" href="<?= APP_URL ?>/einstellungen.php">Einstellungen</a></li>
        <?php endif; ?>
      </ul>
      <span class="navbar-text me-3">Angemeldet als <strong><?= e($u['full_name']) ?></strong></span>
      <a href="<?= APP_URL ?>/logout.php" class="btn btn-outline-light btn-sm">Abmelden</a>
    </div>
  </div>
</nav>
<div class="container-fluid">
<?php foreach (get_flashes() as $f): ?>
  <div class="alert alert-<?= e($f['type']) ?> alert-dismissible fade show" role="alert">
    <?= e($f['message']) ?>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
<?php endforeach; ?>
