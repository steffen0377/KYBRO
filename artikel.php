<?php
$pageTitle = 'Artikel';
require_once __DIR__ . '/includes/header.php';
$pdo = db();
$action = $_GET['action'] ?? 'list';

// ---------- SPEICHERN ----------
if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save') {
    csrf_check();
    $id = (int)($_POST['id'] ?? 0);
    $data = [
        'sku' => trim($_POST['sku']) ?: null,
        'name' => trim($_POST['name']),
        'description' => trim($_POST['description']),
        'unit' => trim($_POST['unit']) ?: 'Stk.',
        'purchase_price' => (float)str_replace(',', '.', $_POST['purchase_price']),
        'sale_price' => (float)str_replace(',', '.', $_POST['sale_price']),
        'tax_rate' => (float)str_replace(',', '.', $_POST['tax_rate']),
        'min_stock' => (float)str_replace(',', '.', $_POST['min_stock']),
        'active' => isset($_POST['active']) ? 1 : 0,
        'track_stock' => isset($_POST['track_stock']) ? 1 : 0,
        'track_serials' => (isset($_POST['track_stock']) && isset($_POST['track_serials'])) ? 1 : 0,
    ];
    if (!$data['name']) {
        flash('danger', 'Name ist Pflichtfeld.');
        redirect('artikel.php?action=' . ($id ? "edit&id=$id" : 'new'));
    }
    if ($id) {
        $stmt = $pdo->prepare('UPDATE articles SET sku=?,name=?,description=?,unit=?,purchase_price=?,sale_price=?,tax_rate=?,min_stock=?,active=?,track_stock=?,track_serials=? WHERE id=?');
        $stmt->execute([...array_values($data), $id]);
        flash('success', 'Artikel aktualisiert.');
    } else {
        $initialStock = $data['track_stock'] ? (float)str_replace(',', '.', $_POST['stock_qty'] ?? '0') : 0;
        $stmt = $pdo->prepare('INSERT INTO articles (sku,name,description,unit,purchase_price,sale_price,tax_rate,min_stock,active,track_stock,track_serials,stock_qty) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)');
        $stmt->execute([...array_values($data), $initialStock]);
        $newId = $pdo->lastInsertId();
        // Anfangsbestand nur automatisch verbuchen, wenn keine Seriennummern-Pflicht besteht
        // (bei Seriennummern-Artikeln erfolgt die Einbuchung gezielt über das Lager-Modul).
        if ($data['track_stock'] && !$data['track_serials'] && $initialStock != 0) {
            adjust_stock((int)$newId, $initialStock, 'einlagerung', 'initial', null, 'Anfangsbestand');
        }
        flash('success', 'Artikel angelegt.');
    }
    redirect('artikel.php');
}

// ---------- LÖSCHEN ----------
if ($action === 'delete' && isset($_GET['id'])) {
    // Löschung über Bestätigungslink mit Token abgesichert
    $token = $_GET['token'] ?? '';
    if (hash_equals(csrf_token(), $token)) {
        $stmt = $pdo->prepare('UPDATE articles SET active=0 WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        flash('success', 'Artikel deaktiviert.');
    } else {
        flash('danger', 'Ungültiger Vorgang.');
    }
    redirect('artikel.php');
}

// ---------- FORMULAR (neu/bearbeiten) ----------
if ($action === 'new' || $action === 'edit') {
    $article = ['id'=>0,'sku'=>'','name'=>'','description'=>'','unit'=>'Stk.','purchase_price'=>0,'sale_price'=>0,'tax_rate'=>19,'stock_qty'=>0,'min_stock'=>0,'active'=>1,'track_stock'=>1,'track_serials'=>0];
    if ($action === 'edit') {
        $stmt = $pdo->prepare('SELECT * FROM articles WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        $article = $stmt->fetch();
        if (!$article) { flash('danger','Artikel nicht gefunden.'); redirect('artikel.php'); }
    }
    ?>
    <h4><?= $action === 'new' ? 'Neuer Artikel' : 'Artikel bearbeiten' ?></h4>
    <form method="post" action="artikel.php?action=save" class="card p-4" style="max-width:700px;">
      <?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= $article['id'] ?>">
      <div class="row g-3">
        <div class="col-md-6"><label class="form-label">Artikelnummer (SKU)</label>
          <input type="text" name="sku" class="form-control" value="<?= e($article['sku']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Einheit</label>
          <input type="text" name="unit" class="form-control" value="<?= e($article['unit']) ?>"></div>
        <div class="col-12"><label class="form-label">Name *</label>
          <input type="text" name="name" class="form-control" required value="<?= e($article['name']) ?>"></div>
        <div class="col-12"><label class="form-label">Beschreibung</label>
          <textarea name="description" class="form-control" rows="2"><?= e($article['description']) ?></textarea></div>
        <div class="col-md-4"><label class="form-label">Einkaufspreis (€)</label>
          <input type="text" name="purchase_price" class="form-control" value="<?= num($article['purchase_price']) ?>"></div>
        <div class="col-md-4"><label class="form-label">Verkaufspreis (€, netto)</label>
          <input type="text" name="sale_price" class="form-control" value="<?= num($article['sale_price']) ?>"></div>
        <div class="col-md-4"><label class="form-label">MwSt.-Satz (%)</label>
          <input type="text" name="tax_rate" class="form-control" value="<?= num($article['tax_rate']) ?>"></div>
        <div class="col-12 form-check">
          <input type="checkbox" name="track_stock" class="form-check-input" id="track_stock" <?= $article['track_stock'] ? 'checked' : '' ?> onchange="document.getElementById('stockFields').style.display = this.checked ? 'flex' : 'none';">
          <label class="form-check-label" for="track_stock">Lagerbestand für diesen Artikel verwalten</label>
          <div class="form-text">Ausschalten für Dienstleistungen oder Artikel ohne Bestandsführung.</div>
        </div>
        <div class="row g-3 col-12" id="stockFields" style="display: <?= $article['track_stock'] ? 'flex' : 'none' ?>;">
        <?php if ($action === 'new'): ?>
        <div class="col-md-6"><label class="form-label">Anfangsbestand</label>
          <input type="text" name="stock_qty" class="form-control" value="0"></div>
        <?php endif; ?>
        <div class="col-md-6"><label class="form-label">Mindestbestand</label>
          <input type="text" name="min_stock" class="form-control" value="<?= num($article['min_stock']) ?>"></div>
        <div class="col-12 form-check">
          <input type="checkbox" name="track_serials" class="form-check-input" id="track_serials" <?= $article['track_serials'] ? 'checked' : '' ?>>
          <label class="form-check-label" for="track_serials">Seriennummern erfassen</label>
          <div class="form-text">Jede Einheit wird einzeln mit Seriennummer im Lager geführt (z.B. Elektronik-Geräte). Ein-/Auslagerung erfolgt dann über das Lager-Modul mit Seriennummernerfassung.</div>
        </div>
        </div>
        <div class="col-12 form-check">
          <input type="checkbox" name="active" class="form-check-input" id="active" <?= $article['active'] ? 'checked' : '' ?>>
          <label class="form-check-label" for="active">Aktiv</label>
        </div>
      </div>
      <div class="mt-3">
        <button class="btn btn-primary" type="submit">Speichern</button>
        <a href="artikel.php" class="btn btn-secondary">Abbrechen</a>
      </div>
    </form>
    <?php
    require_once __DIR__ . '/includes/footer.php';
    exit;
}

// ---------- LISTE ----------
$search = trim($_GET['q'] ?? '');
if ($search) {
    $stmt = $pdo->prepare("SELECT * FROM articles WHERE (name LIKE ? OR sku LIKE ?) ORDER BY name");
    $like = "%$search%";
    $stmt->execute([$like, $like]);
} else {
    $stmt = $pdo->query('SELECT * FROM articles ORDER BY active DESC, name');
}
$articles = $stmt->fetchAll();
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Artikel</h4>
  <a href="artikel.php?action=new" class="btn btn-primary"><i class="bi bi-plus"></i> Neuer Artikel</a>
</div>
<form class="mb-3" method="get">
  <input type="text" name="q" class="form-control" style="max-width:300px;" placeholder="Suche nach Name/SKU" value="<?= e($search) ?>">
</form>
<div class="card p-3">
<table class="table table-hover align-middle">
  <thead><tr><th>SKU</th><th>Name</th><th class="text-end">VK-Preis</th><th class="text-end">MwSt.</th><th class="text-end">Bestand</th><th>Status</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($articles as $a): ?>
    <tr class="<?= !$a['active'] ? 'text-muted' : '' ?>">
      <td><?= e($a['sku']) ?></td>
      <td><a href="artikel.php?action=edit&id=<?= $a['id'] ?>"><?= e($a['name']) ?></a> <?= $a['track_serials'] ? '<span class="badge bg-info text-dark">S/N</span>' : '' ?></td>
      <td class="text-end"><?= money($a['sale_price']) ?></td>
      <td class="text-end"><?= num($a['tax_rate']) ?>%</td>
      <td class="text-end <?= ($a['track_stock'] && $a['stock_qty'] <= $a['min_stock']) ? 'low-stock' : '' ?>">
        <?= $a['track_stock'] ? num($a['stock_qty']) : '<span class="text-muted">— kein Lagerartikel —</span>' ?>
      </td>
      <td><?= $a['active'] ? '<span class="badge bg-success">Aktiv</span>' : '<span class="badge bg-secondary">Inaktiv</span>' ?></td>
      <td class="text-end">
        <a href="artikel.php?action=edit&id=<?= $a['id'] ?>" class="btn btn-sm btn-outline-secondary">Bearbeiten</a>
        <?php if ($a['active']): ?>
        <a href="artikel.php?action=delete&id=<?= $a['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-outline-danger" onclick="return confirm('Artikel deaktivieren?')">Deaktivieren</a>
        <?php endif; ?>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
