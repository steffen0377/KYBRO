<?php
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/functions.php';
require_once __DIR__ . '/license.php';
require_login();
$u = current_user();
$company = company_settings();

// Aktiven Menüpunkt anhand des aktuellen Dateinamens bestimmen
$currentScript = basename($_SERVER['SCRIPT_NAME']);
function nav_active(string $script): string {
    global $currentScript;
    return $currentScript === $script ? 'active' : '';
}
function nav_group_active(array $scripts): bool {
    global $currentScript;
    return in_array($currentScript, $scripts, true);
}

// Kategorien für das Artikel-Untermenü laden und als Baum aufbauen
$navCategories = db()->query('SELECT id, name, parent_id FROM categories ORDER BY name')->fetchAll();
$navCategoriesByParent = [];
foreach ($navCategories as $c) {
    $navCategoriesByParent[$c['parent_id'] ?? 0][] = $c;
}
$navSelectedCategory = ($currentScript === 'artikel.php') ? (int)($_GET['category'] ?? 0) : 0;

function render_article_category_nav(array $byParent, int $parentId, int $depth, int $selectedId): void {
    if (empty($byParent[$parentId])) return;
    echo '<ul class="nav flex-column" style="padding-left:' . (12 + $depth * 14) . 'px;">';
    foreach ($byParent[$parentId] as $cat) {
        $isActive = $selectedId === (int)$cat['id'];
        echo '<li class="nav-item">';
        echo '<a class="nav-link text-white-50 ' . ($isActive ? 'active fw-bold' : '') . '" href="' . APP_URL . '/modules/stammdaten/artikel.php?category=' . $cat['id'] . '">' . htmlspecialchars($cat['name']) . '</a>';
        render_article_category_nav($byParent, (int)$cat['id'], $depth + 1, $selectedId);
        echo '</li>';
    }
    echo '</ul>';
}
?>
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= isset($pageTitle) ? e($pageTitle) . ' – ' : '' ?><?= e($company['company_name'] ?: 'Warenwirtschaft') ?></title>
<link href="<?= APP_URL ?>/assets/vendor/bootstrap/css/bootstrap.min.css" rel="stylesheet">
<link href="<?= APP_URL ?>/assets/vendor/bootstrap-icons/bootstrap-icons.css" rel="stylesheet">
<link href="<?= APP_URL ?>/assets/css/style.css?v=<?= @filemtime(__DIR__ . '/../assets/css/style.css') ?: '1' ?>" rel="stylesheet">
</head>
<body>
<div class="d-flex" id="wrapper">

  <nav class="sidebar sidebar-bg text-white p-3 d-none d-md-block" id="sidebar">
    <div class="sidebar-brand text-center mb-4">
      <a href="<?= APP_URL ?>/index.php" class="text-white text-decoration-none">
        <?php if (!empty($company['logo_path'])): ?>
          <img src="<?= APP_URL ?>/<?= e($company['logo_path']) ?>" alt="Logo" class="sidebar-logo mb-2">
        <?php else: ?>
          <div class="fs-2 mb-1">📦</div>
        <?php endif; ?>
        <div class="fw-bold"><?= e($company['company_name'] ?: 'Warenwirtschaft') ?></div>
      </a>
    </div>
    <?php
      $verkaufActive = nav_group_active(['angebote.php', 'auftraege.php', 'rechnungen.php']);
      $einkaufActive = nav_group_active(['lieferanten.php']);
      $einstellungenActive = nav_group_active(['einstellungen.php', 'kategorien.php', 'lizenzen.php']);
      $hasWarenwirtschaftLicense = has_module_license('warenwirtschaft');
    ?>
    <ul class="nav nav-pills flex-column gap-1">
      <li class="nav-item"><a class="nav-link text-white <?= nav_active('index.php') ?>" href="<?= APP_URL ?>/index.php"><i class="bi bi-speedometer2 me-2"></i>Dashboard</a></li>
      <li class="nav-item">
        <a class="nav-link text-white d-flex align-items-center <?= nav_active('artikel.php') ?> <?= $currentScript === 'artikel.php' ? '' : 'collapsed' ?>" href="<?= APP_URL ?>/modules/stammdaten/artikel.php">
          <i class="bi bi-box-seam me-2"></i>Artikel
          <i class="bi bi-chevron-down ms-auto small nav-chevron"></i>
        </a>
        <?php if ($currentScript === 'artikel.php'): ?>
          <?php render_article_category_nav($navCategoriesByParent, 0, 0, $navSelectedCategory); ?>
        <?php endif; ?>
      </li>
      <li class="nav-item"><a class="nav-link text-white <?= nav_active('lager.php') ?>" href="<?= APP_URL ?>/modules/stammdaten/lager.php"><i class="bi bi-archive me-2"></i>Lager</a></li>
      <li class="nav-item"><a class="nav-link text-white <?= nav_active('kunden.php') ?>" href="<?= APP_URL ?>/modules/stammdaten/kunden.php"><i class="bi bi-people me-2"></i>Kunden</a></li>

      <?php if ($hasWarenwirtschaftLicense): ?>
      <li class="nav-item">
        <a class="nav-link text-white d-flex align-items-center <?= $verkaufActive ? '' : 'collapsed' ?>" href="#navVerkauf" data-bs-toggle="collapse" role="button" aria-expanded="<?= $verkaufActive ? 'true' : 'false' ?>" aria-controls="navVerkauf">
          <i class="bi bi-cart me-2"></i>Verkauf
          <i class="bi bi-chevron-down ms-auto small nav-chevron"></i>
        </a>
        <div class="collapse <?= $verkaufActive ? 'show' : '' ?>" id="navVerkauf">
          <ul class="nav flex-column ms-3">
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('angebote.php') ?>" href="<?= APP_URL ?>/modules/warenwirtschaft/angebote.php"><i class="bi bi-file-earmark-text me-2"></i>Angebote</a></li>
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('auftraege.php') ?>" href="<?= APP_URL ?>/modules/warenwirtschaft/auftraege.php"><i class="bi bi-clipboard-check me-2"></i>Aufträge</a></li>
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('rechnungen.php') ?>" href="<?= APP_URL ?>/modules/warenwirtschaft/rechnungen.php"><i class="bi bi-receipt me-2"></i>Rechnungen</a></li>
          </ul>
        </div>
      </li>
      <?php elseif ($u['role'] === 'admin'): ?>
      <li class="nav-item">
        <a class="nav-link text-white-50 d-flex align-items-center" href="<?= APP_URL ?>/admin/lizenzen.php" title="Fuer dieses Modul liegt keine gueltige Lizenz vor">
          <i class="bi bi-cart me-2"></i>Verkauf <span class="badge bg-app-secondary ms-2">Lizenz erforderlich</span>
        </a>
      </li>
      <?php endif; ?>

      <li class="nav-item">
        <a class="nav-link text-white d-flex align-items-center <?= $einkaufActive ? '' : 'collapsed' ?>" href="#navEinkauf" data-bs-toggle="collapse" role="button" aria-expanded="<?= $einkaufActive ? 'true' : 'false' ?>" aria-controls="navEinkauf">
          <i class="bi bi-bag me-2"></i>Einkauf
          <i class="bi bi-chevron-down ms-auto small nav-chevron"></i>
        </a>
        <div class="collapse <?= $einkaufActive ? 'show' : '' ?>" id="navEinkauf">
          <ul class="nav flex-column ms-3">
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('lieferanten.php') ?>" href="<?= APP_URL ?>/modules/stammdaten/lieferanten.php"><i class="bi bi-truck me-2"></i>Lieferanten</a></li>
          </ul>
        </div>
      </li>

      <?php if ($u['role'] === 'admin'): ?>
      <li class="nav-item mt-3"><hr class="text-white-50 my-1"></li>
      <li class="nav-item">
        <a class="nav-link text-white d-flex align-items-center <?= $einstellungenActive ? '' : 'collapsed' ?>" href="#navEinstellungen" data-bs-toggle="collapse" role="button" aria-expanded="<?= $einstellungenActive ? 'true' : 'false' ?>" aria-controls="navEinstellungen">
          <i class="bi bi-gear me-2"></i>Einstellungen
          <i class="bi bi-chevron-down ms-auto small nav-chevron"></i>
        </a>
        <div class="collapse <?= $einstellungenActive ? 'show' : '' ?>" id="navEinstellungen">
          <ul class="nav flex-column ms-3">
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('einstellungen.php') ?>" href="<?= APP_URL ?>/admin/einstellungen.php"><i class="bi bi-building me-2"></i>Firmeneinstellungen</a></li>
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('kategorien.php') ?>" href="<?= APP_URL ?>/modules/stammdaten/kategorien.php"><i class="bi bi-tags me-2"></i>Kategorien</a></li>
            <li class="nav-item"><a class="nav-link text-white-50 <?= nav_active('lizenzen.php') ?>" href="<?= APP_URL ?>/admin/lizenzen.php"><i class="bi bi-key me-2"></i>Lizenzen</a></li>
          </ul>
        </div>
      </li>
      <?php endif; ?>
    </ul>
  </nav>

  <div class="flex-grow-1" style="min-width:0;">
    <div class="topbar d-flex justify-content-between align-items-center px-3 py-2 border-bottom bg-white">
      <button class="btn btn-app-outline-secondary d-md-none" type="button" onclick="document.getElementById('sidebar').classList.toggle('d-none')">
        <i class="bi bi-list"></i>
      </button>
      <span class="d-none d-md-inline"></span>
      <div>
        <span class="me-3">Angemeldet als <strong><?= e($u['full_name']) ?></strong></span>
        <a href="<?= APP_URL ?>/logout.php" class="btn btn-app-outline-secondary btn-sm">Abmelden</a>
      </div>
    </div>
    <div class="container-fluid p-4">
    <?php foreach (get_flashes() as $f): ?>
      <div class="alert alert-app-<?= e($f['type']) ?> alert-dismissible fade show" role="alert">
        <?= e($f['message']) ?>
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    <?php endforeach; ?>
