<?php
$pageTitle = 'Kategorien';
require_once __DIR__ . '/includes/header.php';
$pdo = db();
$action = $_GET['action'] ?? 'list';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save') {
    csrf_check();
    $id = (int)($_POST['id'] ?? 0);
    $name = trim($_POST['name'] ?? '');
    $parentId = (int)($_POST['parent_id'] ?? 0) ?: null;

    if (!$name) {
        flash('danger', 'Name ist Pflichtfeld.');
        redirect('kategorien.php');
    }
    if ($id && $parentId === $id) {
        flash('danger', 'Eine Kategorie kann nicht ihre eigene Übergeordnete sein.');
        redirect('kategorien.php');
    }
    // Zyklen verhindern: die neue Übergeordnete darf keine Unterkategorie
    // (auf beliebiger Ebene) der zu bearbeitenden Kategorie sein.
    if ($id && $parentId) {
        $all = $pdo->query('SELECT id, parent_id FROM categories')->fetchAll();
        $byParentTmp = [];
        foreach ($all as $c) { $byParentTmp[$c['parent_id'] ?? 0][] = $c['id']; }
        $descendants = collect_descendant_ids($byParentTmp, $id);
        if (in_array($parentId, $descendants, true)) {
            flash('danger', 'Ungültig: Die gewählte Übergeordnete ist eine Unterkategorie dieser Kategorie.');
            redirect('kategorien.php');
        }
    }
    try {
        if ($id) {
            $pdo->prepare('UPDATE categories SET name=?, parent_id=? WHERE id=?')->execute([$name, $parentId, $id]);
            flash('success', 'Kategorie aktualisiert.');
        } else {
            $pdo->prepare('INSERT INTO categories (name, parent_id) VALUES (?,?)')->execute([$name, $parentId]);
            flash('success', 'Kategorie angelegt.');
        }
    } catch (PDOException $e) {
        flash('danger', 'Diese Kategorie existiert bereits.');
    }
    redirect('kategorien.php');
}

if ($action === 'delete' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $pdo->prepare('DELETE FROM categories WHERE id=?')->execute([(int)$_GET['id']]);
    flash('success', 'Kategorie gelöscht. Etwaige Unterkategorien wurden zu Hauptkategorien, Artikel-Zuordnungen wurden entfernt.');
    redirect('kategorien.php');
}

// Alle Nachfahren-IDs (Kinder, Kindeskinder, ...) einer Kategorie einsammeln
function collect_descendant_ids(array $byParent, int $categoryId): array {
    $result = [];
    foreach ($byParent[$categoryId] ?? [] as $childId) {
        $result[] = $childId;
        $result = array_merge($result, collect_descendant_ids($byParent, $childId));
    }
    return $result;
}

$allCategories = $pdo->query('SELECT c.*, (SELECT COUNT(*) FROM article_categories ac WHERE ac.category_id = c.id) AS article_count
                               FROM categories c ORDER BY name')->fetchAll();

// Baumstruktur aufbauen (parent_id => [Kategorien])
$byParent = [];
foreach ($allCategories as $c) {
    $byParent[$c['parent_id'] ?? 0][] = $c;
}

// Rekursive Ausgabe der Kategorie-Zeilen mit Einrückung je Ebene
function render_category_rows(array $byParent, int $parentId, int $depth): void {
    if (empty($byParent[$parentId])) return;
    foreach ($byParent[$parentId] as $c) {
        $excludeIds = array_merge([(int)$c['id']], collect_descendant_ids(array_map(fn($group)=>array_column($group,'id'), $byParent), (int)$c['id']));
        ?>
        <tr>
          <td>
            <form method="post" action="kategorien.php?action=save" class="d-flex gap-2 align-items-center">
              <?= csrf_field() ?>
              <input type="hidden" name="id" value="<?= $c['id'] ?>">
              <span class="text-muted"><?= str_repeat('— ', $depth) ?></span>
              <input type="text" name="name" class="form-control form-control-sm" value="<?= e($c['name']) ?>" style="max-width:220px;">
              <select name="parent_id" class="form-select form-select-sm" style="max-width:220px;">
                <option value="">— Hauptkategorie —</option>
                <?php render_category_options($byParent, 0, 0, $excludeIds, (int)($c['parent_id'] ?? 0)); ?>
              </select>
              <button class="btn btn-sm btn-outline-secondary" type="submit">Speichern</button>
            </form>
          </td>
          <td class="text-end"><?= $c['article_count'] ?></td>
          <td class="text-end">
            <a href="kategorien.php?action=delete&id=<?= $c['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-outline-danger" onclick="return confirm('Kategorie wirklich löschen? Unterkategorien werden dabei zu Hauptkategorien, Artikel-Zuordnungen werden entfernt (Artikel selbst bleiben erhalten).')">Löschen</a>
          </td>
        </tr>
        <?php
        render_category_rows($byParent, (int)$c['id'], $depth + 1);
    }
}

// Rekursive <option>-Liste für die Übergeordnete-Auswahl (mit Einrückung, bestimmte IDs ausgeschlossen)
function render_category_options(array $byParent, int $parentId, int $depth, array $excludeIds = [], int $selectedId = 0): void {
    if (empty($byParent[$parentId])) return;
    foreach ($byParent[$parentId] as $c) {
        if (in_array((int)$c['id'], $excludeIds, true)) continue;
        $prefix = str_repeat('— ', $depth);
        $sel = ((int)$c['id'] === $selectedId) ? 'selected' : '';
        echo '<option value="' . $c['id'] . '" ' . $sel . '>' . $prefix . htmlspecialchars($c['name']) . '</option>';
        render_category_options($byParent, (int)$c['id'], $depth + 1, $excludeIds, $selectedId);
    }
}
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Kategorien</h4>
  <a href="artikel.php" class="btn btn-outline-secondary">Zurück zu Artikel</a>
</div>

<div class="row g-3">
  <div class="col-md-5">
    <div class="card p-3">
      <h6>Neue Kategorie</h6>
      <form method="post" action="kategorien.php?action=save">
        <?= csrf_field() ?>
        <div class="mb-2">
          <input type="text" name="name" class="form-control" placeholder="Name der Kategorie" required>
        </div>
        <div class="mb-2">
          <select name="parent_id" class="form-select">
            <option value="">— Hauptkategorie —</option>
            <?php render_category_options($byParent, 0, 0, []); ?>
          </select>
          <div class="form-text">Optional: als Unterkategorie einer bestehenden Kategorie anlegen.</div>
        </div>
        <button class="btn btn-primary" type="submit">Anlegen</button>
      </form>
    </div>
  </div>
  <div class="col-md-7">
    <div class="card p-3">
      <h6>Vorhandene Kategorien</h6>
      <?php if (!$allCategories): ?>
        <p class="text-muted mb-0">Noch keine Kategorien angelegt.</p>
      <?php else: ?>
      <table class="table table-sm align-middle">
        <thead><tr><th>Name / Übergeordnete Kategorie</th><th class="text-end">Artikel</th><th></th></tr></thead>
        <tbody>
          <?php render_category_rows($byParent, 0, 0); ?>
        </tbody>
      </table>
      <?php endif; ?>
    </div>
  </div>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
