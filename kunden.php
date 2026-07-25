<?php
$pageTitle = 'Kunden';
require_once __DIR__ . '/includes/header.php';
$pdo = db();
$action = $_GET['action'] ?? 'list';

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
        'notes' => trim($_POST['notes']),
    ];
    if (!$data['company'] && !$data['last_name']) {
        flash('danger', 'Bitte Firma oder Nachname angeben.');
        redirect('kunden.php?action=' . ($id ? "edit&id=$id" : 'new'));
    }
    if ($id) {
        $stmt = $pdo->prepare('UPDATE customers SET company=?,first_name=?,last_name=?,street=?,zip=?,city=?,country=?,email=?,phone=?,tax_id=?,notes=? WHERE id=?');
        $stmt->execute([...array_values($data), $id]);
        flash('success', 'Kunde aktualisiert.');
    } else {
        $stmt = $pdo->prepare('INSERT INTO customers (company,first_name,last_name,street,zip,city,country,email,phone,tax_id,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)');
        $stmt->execute(array_values($data));
        $newId = $pdo->lastInsertId();
        $pdo->prepare('UPDATE customers SET customer_number=? WHERE id=?')->execute(['K-' . str_pad($newId, 5, '0', STR_PAD_LEFT), $newId]);
        flash('success', 'Kunde angelegt.');
    }
    redirect('kunden.php');
}

if ($action === 'delete' && isset($_GET['id']) && hash_equals(csrf_token(), $_GET['token'] ?? '')) {
    try {
        $pdo->prepare('DELETE FROM customers WHERE id=?')->execute([(int)$_GET['id']]);
        flash('success', 'Kunde gelöscht.');
    } catch (PDOException $e) {
        flash('danger', 'Kunde kann nicht gelöscht werden – es existieren bereits Angebote/Rechnungen.');
    }
    redirect('kunden.php');
}

if ($action === 'new' || $action === 'edit') {
    $c = ['id'=>0,'company'=>'','first_name'=>'','last_name'=>'','street'=>'','zip'=>'','city'=>'','country'=>'Deutschland','email'=>'','phone'=>'','tax_id'=>'','notes'=>''];
    if ($action === 'edit') {
        $stmt = $pdo->prepare('SELECT * FROM customers WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        $c = $stmt->fetch();
        if (!$c) { flash('danger','Kunde nicht gefunden.'); redirect('kunden.php'); }
    }
    ?>
    <h4><?= $action === 'new' ? 'Neuer Kunde' : e($c['company'] ?: trim($c['first_name'].' '.$c['last_name'])) ?></h4>
    <form method="post" action="kunden.php?action=save" class="card p-4" style="max-width:700px;">
      <?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= $c['id'] ?>">
      <div class="row g-3">
        <div class="col-md-6"><label class="form-label">Firma</label><input type="text" name="company" class="form-control" value="<?= e($c['company']) ?>"></div>
        <div class="col-md-3"><label class="form-label">Vorname</label><input type="text" name="first_name" class="form-control" value="<?= e($c['first_name']) ?>"></div>
        <div class="col-md-3"><label class="form-label">Nachname</label><input type="text" name="last_name" class="form-control" value="<?= e($c['last_name']) ?>"></div>
        <div class="col-md-8"><label class="form-label">Straße & Nr.</label><input type="text" name="street" class="form-control" value="<?= e($c['street']) ?>"></div>
        <div class="col-md-4"><label class="form-label">PLZ</label><input type="text" name="zip" class="form-control" value="<?= e($c['zip']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Ort</label><input type="text" name="city" class="form-control" value="<?= e($c['city']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Land</label><input type="text" name="country" class="form-control" value="<?= e($c['country']) ?>"></div>
        <div class="col-md-6"><label class="form-label">E-Mail</label><input type="email" name="email" class="form-control" value="<?= e($c['email']) ?>"></div>
        <div class="col-md-6"><label class="form-label">Telefon</label><input type="text" name="phone" class="form-control" value="<?= e($c['phone']) ?>"></div>
        <div class="col-md-6"><label class="form-label">USt-IdNr.</label><input type="text" name="tax_id" class="form-control" value="<?= e($c['tax_id']) ?>"></div>
        <div class="col-12"><label class="form-label">Notizen</label><textarea name="notes" class="form-control" rows="2"><?= e($c['notes']) ?></textarea></div>
      </div>
      <div class="mt-3">
        <button class="btn btn-primary" type="submit">Speichern</button>
        <a href="kunden.php" class="btn btn-secondary">Abbrechen</a>
      </div>
    </form>
    <?php require_once __DIR__ . '/includes/footer.php'; exit;
}

$search = trim($_GET['q'] ?? '');
if ($search) {
    $like = "%$search%";
    $stmt = $pdo->prepare('SELECT * FROM customers WHERE company LIKE ? OR last_name LIKE ? OR customer_number LIKE ? ORDER BY company, last_name');
    $stmt->execute([$like, $like, $like]);
} else {
    $stmt = $pdo->query('SELECT * FROM customers ORDER BY company, last_name');
}
$customers = $stmt->fetchAll();
?>
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>Kunden</h4>
  <a href="kunden.php?action=new" class="btn btn-primary"><i class="bi bi-plus"></i> Neuer Kunde</a>
</div>
<form class="mb-3" method="get">
  <input type="text" name="q" class="form-control" style="max-width:300px;" placeholder="Suche" value="<?= e($search) ?>">
</form>
<div class="card p-3">
<table class="table table-hover align-middle">
  <thead><tr><th>Nr.</th><th>Name/Firma</th><th>Ort</th><th>E-Mail</th><th></th></tr></thead>
  <tbody>
  <?php foreach ($customers as $c): ?>
    <tr>
      <td><?= e($c['customer_number']) ?></td>
      <td><a href="kunden.php?action=edit&id=<?= $c['id'] ?>"><?= e($c['company'] ?: trim($c['first_name'].' '.$c['last_name'])) ?></a></td>
      <td><?= e($c['zip'].' '.$c['city']) ?></td>
      <td><?= e($c['email']) ?></td>
      <td class="text-end">
        <a href="kunden.php?action=edit&id=<?= $c['id'] ?>" class="btn btn-sm btn-outline-secondary">Bearbeiten</a>
        <a href="kunden.php?action=delete&id=<?= $c['id'] ?>&token=<?= e(csrf_token()) ?>" class="btn btn-sm btn-outline-danger" onclick="return confirm('Kunde wirklich löschen?')">Löschen</a>
      </td>
    </tr>
  <?php endforeach; ?>
  </tbody>
</table>
</div>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
