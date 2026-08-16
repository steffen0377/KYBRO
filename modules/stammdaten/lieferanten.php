<?php
$pageTitle = 'Lieferanten';
$isAjax = isset($_GET['ajax']) && ($_GET['action'] ?? 'list') === 'list';
if ($isAjax) {
    // Live-Suche: nur Auth/Funktionen laden, kein komplettes Seitenlayout
    require_once $_SERVER['DOCUMENT_ROOT'] . '/includes/auth.php';
    require_once ROOT_PATH . '/includes/functions.php';
    require_login();
} else {
    require_once $_SERVER['DOCUMENT_ROOT'] . '/includes/header.php';
}
$pdo = db();
$action = $_GET['action'] ?? 'list';
require_permission('lieferanten', in_array($action, ['save', 'delete', 'new', 'edit'], true) ? 'write' : 'read');

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save') {
    csrf_check();
    $id = (int)($_POST['id'] ?? 0);
    $data = [
        'company' => trim($_POST['company']),
        'first_name' => trim($_POST['first_name']),
        'last_name' => trim($_POST['last_name']),
        'street' => trim($_POST['street']),
        'zip' => trim($_POST['zip']),
        'city' => trim($_POST['city']),
        'country' => trim($_POST['country']) ?: 'Deutschland',
        'email' => trim($_POST['email']),
        'phone' => trim($_POST['phone']),
        'tax_id' => trim($_POST['tax_id']),
        'customer_number_at_supplier' => trim($_POST['customer_number_at_supplier'] ?? ''),
        'notes' => trim($_POST['notes']),
    ];
    if (!$data['company'] && !$data['last_name']) {
        flash('danger', 'Bitte Firma oder Nachname angeben.');
        redirect('lieferanten.php?action=' . ($id ? "edit&id=$id" : 'new'));
    }
    if ($id) {
        $stmt = $pdo->prepare('UPDATE suppliers SET company=?,first_name=?,last_name=?,street=?,zip=?,city=?,country=?,email=?,phone=?,tax_id=?,customer_number_at_supplier=?,notes=? WHERE id=?');
        $stmt->execute([...array_values($data), $id]);
        flash('success', 'Lieferant aktualisiert.');
    } else {
        $stmt = $pdo->prepare('INSERT INTO suppliers (company,first_name,last_name,street,zip,city,country,email,phone,tax_id,customer_number_at_supplier,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)');
        $stmt->execute(array_values($data));
        $newId = $pdo->lastInsertId();
        $pdo->prepare('UPDATE suppliers SET supplier_number=? WHERE id=?')->execute(['L-' . str_pad($newId, 5, '0', STR_PAD_LEFT), $newId]);
        flash('success', 'Lieferant angelegt.');
    }
    redirect('lieferanten.php');
}

if ($action === 'delete' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    try {
        $pdo->prepare('DELETE FROM suppliers WHERE id=?')->execute([(int)$_GET['id']]);
        flash('success', 'Lieferant gelöscht.');
    } catch (PDOException $e) {
        flash('danger', 'Lieferant kann nicht gelöscht werden – es existieren noch verknüpfte Datensätze.');
    }
    redirect('lieferanten.php');
}

if ($action === 'new' || $action === 'edit') {
    $s = ['id'=>0,'company'=>'','first_name'=>'','last_name'=>'','street'=>'','zip'=>'','city'=>'','country'=>'Deutschland','email'=>'','phone'=>'','tax_id'=>'','customer_number_at_supplier'=>'','notes'=>''];
    if ($action === 'edit') {
        $stmt = $pdo->prepare('SELECT * FROM suppliers WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        $s = $stmt->fetch();
        if (!$s) { flash('danger','Lieferant nicht gefunden.'); redirect('lieferanten.php'); }
    }
    ?>
    <h4><?= $action === 'new' ? 'Neuer Lieferant' : e($s['company'] ?: trim($s['first_name'].' '.$s['last_name'])) ?></h4>
    <form method="post" action="lieferanten.php?action=save" class="card p-4" style="max-width:700px;">
      <?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= $s['id'] ?>">
      <div class="row g-3">
        <div class="col-md-6"><label class="form-label">Firma</label><input type="text" name="company" class="form-control" value="<?= e($s['company']) ?>"></div>
        <div class="col-md-3"><label class="form-label">Vorname</label><input type="text" name="first_name" class="form-control" value="<?= e($s['first_name']) ?>"></div>
        <div class="col-md-3"><label class="form-label">Nachname</label><input type="text" name="last_name" class="form-control" value="<?= e($s['last_name']) ?>"></div>
        <div class="col-md-8"><label class="form-label">Straße & Nr.</label><input type="text" name="street" class="form-control" value="<?= e($s['street']) ?>"></div>
        <div class="col-md-4"><label class="form-label">PLZ</label><input type="text" name="zip" class="form-control" value="<?= e($s['zip']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Ort</label><input type="text" name="city" class="form-control" value="<?= e($s['city']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Land</label><input type="text" name="country" class="form-control" value="<?= e($s['country']) ?>"></div>
        <div class="col-md-6"><label class="form-label">E-Mail</label><input type="email" name="email" class="form-control" value="<?= e($s['email']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Telefon</label><input type="text" name="phone" class="form-control" value="<?= e($s['phone']) ?>"></div>
        <div class="col-md-6"><label class="form-label">USt-IdNr.</label><input type="text" name="tax_id" class="form-control" value="<?= e($s['tax_id']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Unsere Kundennummer bei diesem Lieferanten</label><input type="text" name="customer_number_at_supplier" class="form-control" value="<?= e($s['customer_number_at_supplier']) ?>"></div>
        <div class="col-12"><label class="form-label">Notizen</label><textarea name="notes" class="form-control" rows="2"><?= e($s['notes']) ?></textarea></div>
      </div>
      <div class="mt-3">
        <button class="btn btn-app-primary" type="submit">Speichern</button>
        <a href="lieferanten.php" class="btn btn-app-secondary">Abbrechen</a>
      </div>
    </form>
    <?php require_once __DIR__ . '/../includes/footer.php'; exit;
}

$search = trim($_GET['q'] ?? '');
try {
    if ($search !== '') {
        $like = "%$search%";
        $stmt = $pdo->prepare('SELECT * FROM suppliers WHERE company LIKE ? OR last_name LIKE ? OR supplier_number LIKE ? ORDER BY company, last_name');
        $stmt->execute([$like, $like, $like]);
    } else {
        $stmt = $pdo->query('SELECT * FROM suppliers ORDER BY company, last_name');
    }
    $suppliers = $stmt->fetchAll();
} catch (PDOException $e) {
    $suppliers = [];
    flash('danger', 'Fehler bei der Lieferantensuche: ' . $e->getMessage());
}

// Rendert nur die Ergebnistabelle (wird auch für die Live-Suche per AJAX genutzt)
function render_suppliers_table(array $suppliers): void {
    ?>
    <div class="card p-3">
    <table class="table table-hover align-middle">
      <thead><tr><th>Nr.</th><th>Name/Firma</th><th>Ort</th><th>E-Mail</th><th></th></tr></thead>
      <tbody>
      <?php if (!$suppliers): ?>
        <tr><td colspan="5" class="text-muted text-center py-3">Keine Lieferanten gefunden.</td></tr>
      <?php endif; ?>
      <?php foreach ($suppliers as $s): ?>
        <tr class="<?= !$s['active'] ? 'text-muted' : '' ?>" style="cursor:pointer;" onclick="window.location='lieferanten.php?action=edit&id=<?= $s['id'] ?>';">
          <td><?= e($s['supplier_number']) ?></td>
          <td><?= e($s['company'] ?: trim($s['first_name'].' '.$s['last_name'])) ?></a></td>
          <td><?= e($s['zip'].' '.$s['city']) ?></td>
          <td><?= e($s['email']) ?></td>
          <td class="text-end">
            <a href="lieferanten.php?action=delete&id=<?= $s['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-app-outline-danger" onclick="return confirm('Lieferant wirklich löschen?')">Löschen</a>
          </td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
    </div>
    <?php
}

if ($isAjax) {
    render_suppliers_table($suppliers);
    exit;
}
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Lieferanten</h4>
  <a href="lieferanten.php?action=new" class="btn btn-app-primary"><i class="bi bi-plus"></i> Neuer Lieferant</a>
</div>
<div class="mb-3">
  <div class="position-relative" style="max-width:300px;">
    <input type="text" name="q" id="supplierSearchInput" class="form-control" style="padding-right:2rem;" placeholder="Suche" value="<?= e($search) ?>" autocomplete="off">
    <button type="button" id="supplierSearchClear" class="btn-close position-absolute top-50 end-0 translate-middle-y me-2" style="<?= $search === '' ? 'display:none;' : '' ?>" aria-label="Suche leeren"></button>
  </div>
</div>
<div id="suppliersTableWrap">
<?php render_suppliers_table($suppliers); ?>
</div>
<script>
(function() {
  var input = document.getElementById('supplierSearchInput');
  var clearBtn = document.getElementById('supplierSearchClear');
  var wrap = document.getElementById('suppliersTableWrap');
  var timer = null;

  function toggleClear() {
    clearBtn.style.display = input.value ? '' : 'none';
  }

  function doSearch() {
    var params = new URLSearchParams();
    params.set('q', input.value);
    params.set('ajax', '1');
    fetch('lieferanten.php?' + params.toString())
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
<?php require_once ROOT_PATH . '/includes/footer.php'; ?>
