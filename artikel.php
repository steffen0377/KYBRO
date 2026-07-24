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
        'name' => trim($_POST['name']),
        'description' => trim($_POST['description']),
        'unit' => trim($_POST['unit']) ?: 'Stk.',
        'ean' => trim($_POST['ean'] ?? '') ?: null,
        'han' => trim($_POST['han'] ?? '') ?: null,
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
        // Artikelnummer wird nach Vergabe nicht mehr verändert.
        $stmt = $pdo->prepare('UPDATE articles SET name=?,description=?,unit=?,ean=?,han=?,purchase_price=?,sale_price=?,tax_rate=?,min_stock=?,active=?,track_stock=?,track_serials=? WHERE id=?');
        $stmt->execute([...array_values($data), $id]);
        save_article_categories($pdo, $id, $_POST['category_ids'] ?? []);
        flash('success', 'Artikel aktualisiert.');
    } else {
        $initialStock = $data['track_stock'] ? (float)str_replace(',', '.', $_POST['stock_qty'] ?? '0') : 0;
        $pdo->beginTransaction();
        try {
            // Artikel zunächst mit temporärem Platzhalter anlegen, damit die
            // spätere, auf der ID basierende 5-stellige Artikelnummer feststeht.
            $placeholderSku = 'TMP-' . bin2hex(random_bytes(8));
            $stmt = $pdo->prepare('INSERT INTO articles (sku,name,description,unit,ean,han,purchase_price,sale_price,tax_rate,min_stock,active,track_stock,track_serials,stock_qty) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
            $stmt->execute([$placeholderSku, ...array_values($data), $initialStock]);
            $newId = $pdo->lastInsertId();
            $sku = str_pad((string)$newId, 5, '0', STR_PAD_LEFT);
            $pdo->prepare('UPDATE articles SET sku=? WHERE id=?')->execute([$sku, $newId]);
            save_article_categories($pdo, (int)$newId, $_POST['category_ids'] ?? []);
            $pdo->commit();
        } catch (Exception $e) {
            $pdo->rollBack();
            flash('danger', 'Fehler beim Anlegen: ' . $e->getMessage());
            redirect('artikel.php?action=new');
        }
        // Anfangsbestand nur automatisch verbuchen, wenn keine Seriennummern-Pflicht besteht
        // (bei Seriennummern-Artikeln erfolgt die Einbuchung gezielt über das Lager-Modul).
        if ($data['track_stock'] && !$data['track_serials'] && $initialStock != 0) {
            adjust_stock((int)$newId, $initialStock, 'einlagerung', 'initial', null, 'Anfangsbestand');
        }
        flash('success', "Artikel angelegt (Artikelnummer $sku).");

        // Falls der Artikel aus einer manuellen Angebotsposition heraus angelegt wurde:
        // Position verknüpfen und zurück zum Angebot springen.
        $fromOfferItem = (int)($_POST['from_offer_item'] ?? 0);
        if ($fromOfferItem) {
            $itemStmt = $pdo->prepare('SELECT offer_id FROM offer_items WHERE id=? AND article_id IS NULL');
            $itemStmt->execute([$fromOfferItem]);
            $offerItem = $itemStmt->fetch();
            if ($offerItem) {
                $pdo->prepare('UPDATE offer_items SET article_id=? WHERE id=?')->execute([$newId, $fromOfferItem]);
                flash('success', 'Artikel wurde zusätzlich mit der Angebotsposition verknüpft.');
                redirect('angebote.php?action=view&id=' . $offerItem['offer_id']);
            }
        }
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
    $article = ['id'=>0,'sku'=>'','ean'=>'','han'=>'','name'=>'','description'=>'','unit'=>'Stk.','purchase_price'=>0,'sale_price'=>0,'tax_rate'=>19,'stock_qty'=>0,'min_stock'=>0,'active'=>1,'track_stock'=>1,'track_serials'=>0];
    $fromOfferItem = 0;
    if ($action === 'new' && !empty($_GET['from_offer_item'])) {
        $fromOfferItem = (int)$_GET['from_offer_item'];
        $stmt = $pdo->prepare('SELECT * FROM offer_items WHERE id=? AND article_id IS NULL');
        $stmt->execute([$fromOfferItem]);
        $sourceItem = $stmt->fetch();
        if ($sourceItem) {
            $article['name'] = $sourceItem['description'];
            $article['sale_price'] = $sourceItem['unit_price'];
            $article['tax_rate'] = $sourceItem['tax_rate'];
        } else {
            $fromOfferItem = 0; // bereits verknüpft oder ungültig - normales leeres Formular
        }
    }
    if ($action === 'edit') {
        $stmt = $pdo->prepare('SELECT * FROM articles WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        $article = $stmt->fetch();
        if (!$article) { flash('danger','Artikel nicht gefunden.'); redirect('artikel.php'); }
    }
    $allCategories = $pdo->query('SELECT * FROM categories ORDER BY name')->fetchAll();
    $selectedCategoryIds = [];
    if ($article['id']) {
        $catStmt = $pdo->prepare('SELECT category_id FROM article_categories WHERE article_id=?');
        $catStmt->execute([$article['id']]);
        $selectedCategoryIds = array_column($catStmt->fetchAll(), 'category_id');
    }
    ?>
    <h4><?= $action === 'new' ? 'Neuer Artikel' : 'Artikel bearbeiten' ?></h4>
    <?php if ($fromOfferItem): ?>
      <div class="alert alert-info">Übernommen aus einer Angebotsposition. Bitte prüfen und bei Bedarf ergänzen (z.B. Einkaufspreis, Einheit, Artikel- und Lagerbestand-Einstellungen).</div>
    <?php endif; ?>
    <form method="post" action="artikel.php?action=save" class="card p-4" style="max-width:700px;">
      <?= csrf_field() ?>
      <?php if ($fromOfferItem): ?><input type="hidden" name="from_offer_item" value="<?= $fromOfferItem ?>"><?php endif; ?>
      <input type="hidden" name="id" value="<?= $article['id'] ?>">
      <div class="row g-3">
        <div class="col-md-6"><label class="form-label">Artikelnummer</label>
          <?php if ($action === 'edit'): ?>
            <input type="text" class="form-control" value="<?= e($article['sku']) ?>" disabled>
          <?php else: ?>
            <input type="text" class="form-control" value="wird automatisch vergeben" disabled>
          <?php endif; ?>
        </div>
        <div class="col-md-6"><label class="form-label">Einheit</label>
          <input type="text" name="unit" class="form-control" value="<?= e($article['unit']) ?>"></div>
        <div class="col-md-6"><label class="form-label">EAN</label>
          <input type="text" name="ean" class="form-control" value="<?= e($article['ean']) ?>" placeholder="z.B. 4006381333931"></div>
        <div class="col-md-6"><label class="form-label">HAN (Herstellerartikelnummer)</label>
          <input type="text" name="han" class="form-control" value="<?= e($article['han']) ?>"></div>
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
        <div class="col-12">
          <label class="form-label">Kategorien</label>
          <?php if (!$allCategories): ?>
            <div class="form-text">Noch keine Kategorien angelegt. <a href="kategorien.php">Jetzt anlegen</a>.</div>
          <?php else: ?>
          <div class="row">
            <?php foreach ($allCategories as $cat): ?>
              <div class="col-md-4 form-check">
                <input type="checkbox" name="category_ids[]" class="form-check-input" id="cat<?= $cat['id'] ?>" value="<?= $cat['id'] ?>" <?= in_array($cat['id'], $selectedCategoryIds) ? 'checked' : '' ?>>
                <label class="form-check-label" for="cat<?= $cat['id'] ?>"><?= e($cat['name']) ?></label>
              </div>
            <?php endforeach; ?>
          </div>
          <?php endif; ?>
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
$selectedFilterCategory = (int)($_GET['category'] ?? 0);

$where = [];
$params = [];
if ($search) {
    $where[] = '(a.name LIKE ? OR a.sku LIKE ? OR a.ean LIKE ? OR a.han LIKE ?)';
    $params[] = "%$search%";
    $params[] = "%$search%";
    $params[] = "%$search%";
    $params[] = "%$search%";
}
if ($selectedFilterCategory) {
    $where[] = 'a.id IN (SELECT article_id FROM article_categories WHERE category_id = ?)';
    $params[] = $selectedFilterCategory;
}
$sql = 'SELECT a.* FROM articles a';
if ($where) {
    $sql .= ' WHERE ' . implode(' AND ', $where);
}
$sql .= ' ORDER BY a.active DESC, a.name';
$stmt = $pdo->prepare($sql);
$stmt->execute($params);
$articles = $stmt->fetchAll();

// Kategorien je Artikel für die Anzeige nachladen
$articleCategories = [];
if ($articles) {
    $ids = array_column($articles, 'id');
    $placeholders = implode(',', array_fill(0, count($ids), '?'));
    $catStmt = $pdo->prepare("SELECT ac.article_id, c.name FROM article_categories ac JOIN categories c ON c.id=ac.category_id WHERE ac.article_id IN ($placeholders) ORDER BY c.name");
    $catStmt->execute($ids);
    foreach ($catStmt->fetchAll() as $row) {
        $articleCategories[$row['article_id']][] = $row['name'];
    }
}
$selectedCategoryName = null;
if ($selectedFilterCategory) {
    $catNameStmt = $pdo->prepare('SELECT name FROM categories WHERE id=?');
    $catNameStmt->execute([$selectedFilterCategory]);
    $selectedCategoryName = $catNameStmt->fetch()['name'] ?? null;
}
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Artikel<?= $selectedCategoryName ? ' — Kategorie: ' . e($selectedCategoryName) : '' ?></h4>
  <a href="artikel.php?action=new" class="btn btn-primary"><i class="bi bi-plus"></i> Neuer Artikel</a>
</div>
<form class="row g-2 mb-3" method="get">
  <?php if ($selectedFilterCategory): ?><input type="hidden" name="category" value="<?= $selectedFilterCategory ?>"><?php endif; ?>
  <div class="col-auto">
    <input type="text" name="q" class="form-control" placeholder="Suche nach Name/Artikelnummer/EAN/HAN" value="<?= e($search) ?>">
  </div>
  <div class="col-auto">
    <button class="btn btn-outline-primary" type="submit">Suchen</button>
    <a href="<?= $selectedFilterCategory ? 'artikel.php?category=' . $selectedFilterCategory : 'artikel.php' ?>" class="btn btn-outline-secondary">Zurücksetzen</a>
  </div>
</form>
<div class="card p-3">
<table class="table table-hover align-middle">
  <thead><tr><th>Art.-Nr.</th><th>Name</th><th>Kategorien</th><th class="text-end">VK-Preis</th><th class="text-end">MwSt.</th><th class="text-end">Bestand</th><th>Status</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($articles as $a): ?>
    <tr class="<?= !$a['active'] ? 'text-muted' : '' ?>">
      <td><?= e($a['sku']) ?></td>
      <td><a href="artikel.php?action=edit&id=<?= $a['id'] ?>"><?= e($a['name']) ?></a> <?= $a['track_serials'] ? '<span class="badge bg-info text-dark">S/N</span>' : '' ?></td>
      <td>
        <?php foreach ($articleCategories[$a['id']] ?? [] as $catName): ?>
          <span class="badge bg-light text-dark border"><?= e($catName) ?></span>
        <?php endforeach; ?>
      </td>
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
