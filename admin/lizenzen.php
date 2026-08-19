<?php
require_once $_SERVER['DOCUMENT_ROOT'] . '/includes/auth.php';
require_once ROOT_PATH . '/includes/functions.php';
require_once ROOT_PATH . '/includes/license.php';
require_admin();
$pdo = db();
$action = $_GET['action'] ?? 'list';

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'save') {
    csrf_check();
    $id = (int)($_POST['id'] ?? 0);
    $customerReference = trim($_POST['customer_reference'] ?? '');
    $validFrom = $_POST['valid_from'] ?? date('Y-m-d');
    $validUntil = trim($_POST['valid_until'] ?? '') ?: null;
    $status = in_array($_POST['status'] ?? '', ['active', 'expired', 'revoked'], true) ? $_POST['status'] : 'active';
    $moduleIds = array_map('intval', $_POST['module_ids'] ?? []);

    if ($customerReference === '') {
        flash('danger', 'Bitte eine Kunden-/Installationsreferenz angeben.');
        redirect('admin/lizenzen.php?action=' . ($id ? "edit&id=$id" : 'new'));
    }
    if ($validUntil !== null && $validUntil < $validFrom) {
        flash('danger', '"Gültig bis" darf nicht vor "Gültig ab" liegen.');
        redirect('admin/lizenzen.php?action=' . ($id ? "edit&id=$id" : 'new'));
    }

    $pdo->beginTransaction();
    try {
        if ($id) {
            $stmt = $pdo->prepare('UPDATE licenses SET customer_reference=?, valid_from=?, valid_until=?, status=? WHERE id=?');
            $stmt->execute([$customerReference, $validFrom, $validUntil, $status, $id]);
            $licenseId = $id;
        } else {
            $stmt = $pdo->prepare('INSERT INTO licenses (customer_reference, valid_from, valid_until, status, created_by) VALUES (?,?,?,?,?)');
            $stmt->execute([$customerReference, $validFrom, $validUntil, $status, current_user()['id']]);
            $licenseId = $pdo->lastInsertId();
        }
        $pdo->prepare('DELETE FROM license_modules WHERE license_id=?')->execute([$licenseId]);
        if ($moduleIds) {
            $modStmt = $pdo->prepare('INSERT INTO license_modules (license_id, module_id) VALUES (?,?)');
            foreach (array_unique($moduleIds) as $moduleId) {
                if ($moduleId > 0) {
                    $modStmt->execute([$licenseId, $moduleId]);
                }
            }
        }
        $pdo->commit();
        flash('success', $id ? 'Lizenz aktualisiert.' : 'Lizenz angelegt.');
    } catch (Exception $e) {
        $pdo->rollBack();
        flash('danger', 'Fehler beim Speichern: ' . $e->getMessage());
    }
    redirect('admin/lizenzen.php');
}

if ($action === 'delete' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    $pdo->prepare('DELETE FROM licenses WHERE id=?')->execute([(int)$_GET['id']]);
    flash('success', 'Lizenz gelöscht.');
    redirect('admin/lizenzen.php');
}

$pageTitle = 'Lizenzen';
require_once ROOT_PATH . '/includes/header.php';

$allModules = $pdo->query('SELECT * FROM modules ORDER BY name')->fetchAll();

if ($action === 'new' || $action === 'edit') {
    $license = ['id' => 0, 'customer_reference' => '', 'valid_from' => date('Y-m-d'), 'valid_until' => '', 'status' => 'active'];
    $selectedModuleIds = [];
    if ($action === 'edit') {
        $stmt = $pdo->prepare('SELECT * FROM licenses WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        $license = $stmt->fetch();
        if (!$license) { flash('danger', 'Lizenz nicht gefunden.'); redirect('admin/lizenzen.php'); }
        $modStmt = $pdo->prepare('SELECT module_id FROM license_modules WHERE license_id=?');
        $modStmt->execute([$license['id']]);
        $selectedModuleIds = array_column($modStmt->fetchAll(), 'module_id');
    }
    ?>
    <h4><?= $action === 'new' ? 'Neue Lizenz' : 'Lizenz bearbeiten' ?></h4>
    <form method="post" action="<?= APP_URL ?>/admin/lizenzen.php?action=save" class="card p-4" style="max-width:700px;">
      <?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= $license['id'] ?>">
      <div class="row g-3">
        <div class="col-12">
          <label class="form-label">Kunde / Installation *</label>
          <input type="text" name="customer_reference" class="form-control" value="<?= e($license['customer_reference']) ?>" placeholder="z.B. Firma Mustermann GmbH" required>
        </div>
        <div class="col-md-4">
          <label class="form-label">Gültig ab</label>
          <input type="date" name="valid_from" class="form-control" value="<?= e($license['valid_from']) ?>">
        </div>
        <div class="col-md-4">
          <label class="form-label">Gültig bis</label>
          <input type="date" name="valid_until" class="form-control" value="<?= e($license['valid_until']) ?>">
          <div class="form-text">Leer lassen für unbefristet.</div>
        </div>
        <div class="col-md-4">
          <label class="form-label">Status</label>
          <select name="status" class="form-select">
            <option value="active" <?= $license['status'] === 'active' ? 'selected' : '' ?>>Aktiv</option>
            <option value="expired" <?= $license['status'] === 'expired' ? 'selected' : '' ?>>Abgelaufen</option>
            <option value="revoked" <?= $license['status'] === 'revoked' ? 'selected' : '' ?>>Widerrufen</option>
          </select>
        </div>
        <div class="col-12">
          <label class="form-label">Freigeschaltete Module</label>
          <?php if (!$allModules): ?>
            <div class="form-text">Keine Module im Katalog gefunden. Bitte Migration migration_011_licensing.sql einspielen.</div>
          <?php else: ?>
          <div class="row">
            <?php foreach ($allModules as $mod): ?>
              <div class="col-md-6 form-check">
                <input type="checkbox" name="module_ids[]" class="form-check-input" id="mod<?= $mod['id'] ?>" value="<?= $mod['id'] ?>" <?= in_array($mod['id'], $selectedModuleIds) ? 'checked' : '' ?>>
                <label class="form-check-label" for="mod<?= $mod['id'] ?>"><?= e($mod['name']) ?><?php if ($mod['description']): ?> <span class="text-muted small">– <?= e($mod['description']) ?></span><?php endif; ?></label>
              </div>
            <?php endforeach; ?>
          </div>
          <?php endif; ?>
        </div>
      </div>
      <div class="mt-3">
        <button class="btn btn-app-primary" type="submit">Speichern</button>
        <a href="<?= APP_URL ?>/admin/lizenzen.php" class="btn btn-app-secondary">Abbrechen</a>
      </div>
    </form>
    <?php require_once ROOT_PATH . '/includes/footer.php'; exit;
}

$licenses = $pdo->query('SELECT * FROM licenses ORDER BY status = "active" DESC, valid_until IS NULL DESC, valid_until DESC, id DESC')->fetchAll();
$modulesByLicense = [];
$stmt = $pdo->query('SELECT lm.license_id, m.name FROM license_modules lm JOIN modules m ON m.id = lm.module_id ORDER BY m.name');
foreach ($stmt->fetchAll() as $row) {
    $modulesByLicense[$row['license_id']][] = $row['name'];
}
$today = date('Y-m-d');
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Lizenzen</h4>
  <a href="<?= APP_URL ?>/admin/lizenzen.php?action=new" class="btn btn-app-primary"><i class="bi bi-plus"></i> Neue Lizenz</a>
</div>
<div class="card p-3">
<table class="table table-hover align-middle">
  <thead><tr><th>Kunde / Installation</th><th>Module</th><th>Gültig ab</th><th>Gültig bis</th><th>Status</th><th></th></tr></thead>
  <tbody>
  <?php if (!$licenses): ?>
    <tr><td colspan="6" class="text-muted text-center py-3">Keine Lizenzen vorhanden.</td></tr>
  <?php endif; ?>
  <?php foreach ($licenses as $l):
    $isExpired = $l['valid_until'] && $l['valid_until'] < $today;
    $effectiveStatus = $l['status'] === 'active' && $isExpired ? 'abgelaufen' : $l['status'];
    $badgeClass = ['active' => 'success', 'expired' => 'secondary', 'revoked' => 'danger', 'abgelaufen' => 'warning'][$effectiveStatus] ?? 'secondary';
  ?>
    <tr>
      <td><a href="<?= APP_URL ?>/admin/lizenzen.php?action=edit&id=<?= $l['id'] ?>"><?= e($l['customer_reference']) ?></a></td>
      <td><?= $modulesByLicense[$l['id']] ? e(implode(', ', $modulesByLicense[$l['id']])) : '<span class="text-muted">— keine —</span>' ?></td>
      <td><?= date('d.m.Y', strtotime($l['valid_from'])) ?></td>
      <td><?= $l['valid_until'] ? date('d.m.Y', strtotime($l['valid_until'])) : '<span class="text-muted">unbefristet</span>' ?></td>
      <td><span class="badge bg-app-<?= $badgeClass ?>"><?= e(ucfirst($effectiveStatus)) ?></span></td>
      <td class="text-end">
        <a href="<?= APP_URL ?>/admin/lizenzen.php?action=edit&id=<?= $l['id'] ?>" class="btn btn-sm btn-app-outline-secondary">Bearbeiten</a>
        <a href="<?= APP_URL ?>/admin/lizenzen.php?action=delete&id=<?= $l['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-app-outline-danger" onclick="return confirm('Lizenz wirklich löschen?')">Löschen</a>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
</div>
<?php require_once ROOT_PATH . '/includes/footer.php'; ?>
