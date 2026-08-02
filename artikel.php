<?php
$pageTitle = 'Artikel';
// Auth/Funktionen werden immer zuerst geladen (auch für normale Aufrufe),
// damit POST-Aktionen wie "save" oder "delete" ihren redirect() ausführen
// können, BEVOR includes/header.php irgendwelches HTML ausgibt. Sonst
// schlägt header('Location: ...') fehl ("headers already sent") und die
// Seite bleibt nach dem Speichern leer.
require_once __DIR__ . '/includes/auth.php';
require_once __DIR__ . '/includes/functions.php';
require_login();
$isAjax = isset($_GET['ajax']) && ($_GET['action'] ?? 'list') === 'list';
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
        save_article_suppliers($pdo, $id, $_POST['supplier_id'] ?? [], $_POST['supplier_article_number'] ?? [], $_POST['hek_price'] ?? []);
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
            save_article_suppliers($pdo, (int)$newId, $_POST['supplier_id'] ?? [], $_POST['supplier_article_number'] ?? [], $_POST['hek_price'] ?? []);
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

// Ab hier wird tatsächlich HTML ausgegeben - Seitenlayout jetzt laden
// (bei AJAX-Live-Suche wird bewusst kein komplettes Layout gerendert).
if (!$isAjax) {
    require_once __DIR__ . '/includes/header.php';
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
    $allSuppliers = $pdo->query('SELECT id, company, first_name, last_name FROM suppliers ORDER BY company, last_name')->fetchAll();
    $articleSuppliers = [];
    if ($article['id']) {
        $supStmt = $pdo->prepare('SELECT * FROM article_suppliers WHERE article_id=?');
        $supStmt->execute([$article['id']]);
        $articleSuppliers = $supStmt->fetchAll();
    }
    ?>
    <h4><?= $action === 'new' ? 'Neuer Artikel' : e($article['name']) ?></h4>
    <?php if ($fromOfferItem): ?>
      <div class="alert alert-app-info">Übernommen aus einer Angebotsposition. Bitte prüfen und bei Bedarf ergänzen (z.B. Einkaufspreis, Einheit, Artikel- und Lagerbestand-Einstellungen).</div>
    <?php endif; ?>
    <form method="post" action="artikel.php?action=save" class="card p-4" style="max-width:900px;">
      <?= csrf_field() ?>
      <?php if ($fromOfferItem): ?><input type="hidden" name="from_offer_item" value="<?= $fromOfferItem ?>"><?php endif; ?>
      <input type="hidden" name="id" value="<?= $article['id'] ?>">

      <ul class="nav nav-tabs mb-3" role="tablist">
        <li class="nav-item" role="presentation">
          <button class="nav-link active" id="tab-allgemein-btn" data-bs-toggle="tab" data-bs-target="#tab-allgemein" type="button" role="tab" aria-controls="tab-allgemein" aria-selected="true">Allgemein</button>
        </li>
        <li class="nav-item" role="presentation">
          <button class="nav-link" id="tab-lieferanten-btn" data-bs-toggle="tab" data-bs-target="#tab-lieferanten" type="button" role="tab" aria-controls="tab-lieferanten" aria-selected="false">Lieferanten</button>
        </li>
      </ul>

      <div class="tab-content">
        <div class="tab-pane fade show active" id="tab-allgemein" role="tabpanel" aria-labelledby="tab-allgemein-btn">
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
        </div>

        <div class="tab-pane fade" id="tab-lieferanten" role="tabpanel" aria-labelledby="tab-lieferanten-btn">
          <?php if (!$allSuppliers): ?>
            <div class="form-text mb-3">Noch keine Lieferanten angelegt. <a href="lieferanten.php">Jetzt anlegen</a>.</div>
          <?php endif; ?>
          <table class="table" id="supplierTable">
            <thead><tr><th style="width:35%">Lieferant</th><th style="width:30%">Artikelnummer beim Lieferanten</th><th style="width:20%">Unser HEK (€)</th><th style="width:5%"></th></tr></thead>
            <tbody>
              <?php $supplierRows = $articleSuppliers ?: [['supplier_id' => '', 'supplier_article_number' => '', 'hek_price' => 0]]; ?>
              <?php foreach ($supplierRows as $row): ?>
              <tr>
                <td>
                  <select name="supplier_id[]" class="form-select">
                    <option value="">— Lieferant wählen —</option>
                    <?php foreach ($allSuppliers as $s): ?>
                      <option value="<?= $s['id'] ?>" <?= (int)($row['supplier_id'] ?? 0) === (int)$s['id'] ? 'selected' : '' ?>><?= e($s['company'] ?: trim($s['first_name'].' '.$s['last_name'])) ?></option>
                    <?php endforeach; ?>
                  </select>
                </td>
                <td><input type="text" name="supplier_article_number[]" class="form-control" value="<?= e($row['supplier_article_number'] ?? '') ?>"></td>
                <td><input type="text" name="hek_price[]" class="form-control" value="<?= num($row['hek_price'] ?? 0) ?>"></td>
                <td><button type="button" class="btn btn-sm btn-app-outline-danger remove-supplier-row">✕</button></td>
              </tr>
              <?php endforeach; ?>
            </tbody>
          </table>
          <button type="button" id="addSupplierRow" class="btn btn-sm btn-app-outline-primary">+ Lieferant hinzufügen</button>
        </div>
      </div>

      <div class="mt-3">
        <button class="btn btn-app-primary" type="submit">Speichern</button>
        <a href="artikel.php" class="btn btn-app-secondary">Abbrechen</a>
      </div>
    </form>
    <script>
    document.getElementById('addSupplierRow').addEventListener('click', function() {
      const tbody = document.querySelector('#supplierTable tbody');
      const row = tbody.rows[0].cloneNode(true);
      row.querySelectorAll('input').forEach(i => i.value = '');
      row.querySelector('select').value = '';
      tbody.appendChild(row);
      bindSupplierRow(row);
    });
    function bindSupplierRow(row) {
      row.querySelector('.remove-supplier-row').addEventListener('click', function() {
        if (document.querySelectorAll('#supplierTable tbody tr').length > 1) row.remove();
      });
    }
    document.querySelectorAll('#supplierTable tbody tr').forEach(bindSupplierRow);
    </script>
    <?php
    require_once __DIR__ . '/includes/footer.php';
    exit;
}

// ---------- LISTE ----------
$search = trim($_GET['q'] ?? '');
$selectedFilterCategory = (int)($_GET['category'] ?? 0);

// Sortierung: nur Artikelnummer und Name duerfen per Klick auf die Spaltenueberschrift sortiert werden.
$sortableColumns = ['sku' => 'a.sku', 'name' => 'a.name'];
$sortColumn = (string)($_GET['sort'] ?? '');
if (!array_key_exists($sortColumn, $sortableColumns)) {
    $sortColumn = '';
}
$sortDir = (isset($_GET['dir']) && strtolower($_GET['dir']) === 'desc') ? 'desc' : 'asc';

$where = [];
$params = [];
if ($search !== '') {
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
if ($sortColumn) {
    $sql .= ' ORDER BY ' . $sortableColumns[$sortColumn] . ' ' . strtoupper($sortDir);
} else {
    $sql .= ' ORDER BY a.active DESC, a.name';
}

try {
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $articles = $stmt->fetchAll();
} catch (PDOException $e) {
    $articles = [];
    flash('danger', 'Fehler bei der Artikelsuche: ' . $e->getMessage());
}

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

// Erzeugt den Link fuer eine sortierbare Spaltenueberschrift inkl. Sortierpfeil
function article_sort_link(string $column, string $label, string $sortColumn, string $sortDir, string $search, int $selectedFilterCategory): string {
    $newDir = ($sortColumn === $column && $sortDir === 'asc') ? 'desc' : 'asc';
    $query = ['sort' => $column, 'dir' => $newDir];
    if ($search !== '') { $query['q'] = $search; }
    if ($selectedFilterCategory) { $query['category'] = $selectedFilterCategory; }
    $arrow = '';
    if ($sortColumn === $column) {
        $arrow = $sortDir === 'asc' ? ' <i class="bi bi-caret-up-fill"></i>' : ' <i class="bi bi-caret-down-fill"></i>';
    }
    return '<a href="artikel.php?' . http_build_query($query) . '" class="text-dark text-decoration-none">' . e($label) . '</a>' . $arrow;
}

// Rendert nur die Ergebnistabelle (wird auch für die Live-Suche per AJAX genutzt)
function render_articles_table(array $articles, array $articleCategories, string $sortColumn = '', string $sortDir = 'asc', string $search = '', int $selectedFilterCategory = 0): void {
    ?>
    <div class="card p-3">
    <table class="table table-hover align-middle">
      <thead><tr><th><?= article_sort_link('sku', 'Art.-Nr.', $sortColumn, $sortDir, $search, $selectedFilterCategory) ?></th><th><?= article_sort_link('name', 'Name', $sortColumn, $sortDir, $search, $selectedFilterCategory) ?></th><th class="text-end">VK-Preis</th><th class="text-end">MwSt.</th><th class="text-end">Bestand</th><th>Status</th></tr></thead>
      <tbody>
      <?php if (!$articles): ?>
        <tr><td colspan="7" class="text-muted text-center py-3">Keine Artikel gefunden.</td></tr>
      <?php endif; ?>
      <?php foreach ($articles as $a): ?>
        <tr class="<?= !$a['active'] ? 'text-muted' : '' ?>" style="cursor:pointer;" onclick="window.location='artikel.php?action=edit&id=<?= $a['id'] ?>';">
          <td><?= e($a['sku']) ?></td>
          <td><?= e($a['name']) ?> <?= $a['track_serials'] ? '<span class="badge bg-app-info text-dark">S/N</span>' : '' ?></td>
          <td class="text-end"><?= money($a['sale_price']) ?></td>
          <td class="text-end"><?= num($a['tax_rate']) ?>%</td>
          <td class="text-end <?= ($a['track_stock'] && $a['stock_qty'] <= $a['min_stock']) ? 'low-stock' : '' ?>">
            <?= $a['track_stock'] ? num($a['stock_qty']) : '<span class="text-muted">— kein Lagerartikel —</span>' ?>
          </td>
          <td><?= $a['active'] ? '<span class="badge bg-app-success">Aktiv</span>' : '<span class="badge bg-app-secondary">Inaktiv</span>' ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
    </div>
    <?php
}

// Bei Live-Suche (AJAX) nur die Tabelle zurückgeben, ohne Layout drumherum
if ($isAjax) {
    render_articles_table($articles, $articleCategories, $sortColumn, $sortDir, $search, $selectedFilterCategory);
    exit;
}

$selectedCategoryName = null;
if ($selectedFilterCategory) {
    $catNameStmt = $pdo->prepare('SELECT name FROM categories WHERE id=?');
    $catNameStmt->execute([$selectedFilterCategory]);
    $catNameRow = $catNameStmt->fetch();
    $selectedCategoryName = $catNameRow ? $catNameRow['name'] : null;
}
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Artikel<?= $selectedCategoryName ? ' — Kategorie: ' . e($selectedCategoryName) : '' ?></h4>
  <a href="artikel.php?action=new" class="btn btn-app-primary"><i class="bi bi-plus"></i> Neuer Artikel</a>
</div>
<form class="row g-2 mb-3" method="get" id="articleSearchForm">
  <?php if ($selectedFilterCategory): ?><input type="hidden" name="category" value="<?= $selectedFilterCategory ?>"><?php endif; ?>
  <div class="col-auto">
    <div class="position-relative">
      <input type="text" name="q" id="articleSearchInput" class="form-control" style="padding-right:2rem; min-width:320px;" placeholder="Suche nach Name/Artikelnummer/EAN/HAN" value="<?= e($search) ?>" autocomplete="off">
      <button type="button" id="articleSearchClear" class="btn-close position-absolute top-50 end-0 translate-middle-y me-2" style="<?= $search === '' ? 'display:none;' : '' ?>" aria-label="Suche leeren"></button>
    </div>
  </div>
</form>
<div id="articlesTableWrap">
<?php render_articles_table($articles, $articleCategories, $sortColumn, $sortDir, $search, $selectedFilterCategory); ?>
</div>
<script>
(function() {
  var input = document.getElementById('articleSearchInput');
  var clearBtn = document.getElementById('articleSearchClear');
  var wrap = document.getElementById('articlesTableWrap');
  var categoryId = <?= (int)$selectedFilterCategory ?>;
  var sortColumn = <?= json_encode($sortColumn) ?>;
  var sortDir = <?= json_encode($sortDir) ?>;
  var timer = null;

  function toggleClear() {
    clearBtn.style.display = input.value ? '' : 'none';
  }

  function doSearch() {
    var params = new URLSearchParams();
    params.set('q', input.value);
    if (categoryId) { params.set('category', categoryId); }
    if (sortColumn) { params.set('sort', sortColumn); params.set('dir', sortDir); }
    params.set('ajax', '1');
    fetch('artikel.php?' + params.toString())
      .then(function(r) { return r.text(); })
      .then(function(html) {
        wrap.innerHTML = html;
        var url = new URL(window.location);
        if (input.value) { url.searchParams.set('q', input.value); } else { url.searchParams.delete('q'); }
        window.history.replaceState({}, '', url);
      });
  }

  input.addEventListener('input', function() {
    toggleClear();
    clearTimeout(timer);
    timer = setTimeout(doSearch, 300);
  });

  clearBtn.addEventListener('click', function() {
    input.value = '';
    toggleClear();
    doSearch();
    input.focus();
  });
})();
</script>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
