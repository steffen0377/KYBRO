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
        'iban' => trim($_POST['iban'] ?? ''),
        'bic' => trim($_POST['bic'] ?? ''),
        'bank_name' => trim($_POST['bank_name'] ?? ''),
        'notes' => trim($_POST['notes']),
    ];
    if (!$data['company'] && !$data['last_name']) {
        flash('danger', 'Bitte Firma oder Nachname angeben.');
        redirect('kunden.php?action=' . ($id ? "edit&id=$id" : 'new'));
    }
    if ($id) {
        $stmt = $pdo->prepare('UPDATE customers SET company=?,first_name=?,last_name=?,street=?,zip=?,city=?,country=?,email=?,phone=?,tax_id=?,iban=?,bic=?,bank_name=?,notes=? WHERE id=?');
        $stmt->execute([...array_values($data), $id]);
        $customerId = $id;
        flash('success', 'Kunde aktualisiert.');
    } else {
        $stmt = $pdo->prepare('INSERT INTO customers (company,first_name,last_name,street,zip,city,country,email,phone,tax_id,iban,bic,bank_name,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)');
        $stmt->execute(array_values($data));
        $customerId = (int)$pdo->lastInsertId();
        $pdo->prepare('UPDATE customers SET customer_number=? WHERE id=?')->execute(['K-' . str_pad($customerId, 5, '0', STR_PAD_LEFT), $customerId]);
        flash('success', 'Kunde angelegt.');
    }
    save_customer_contacts(
        $pdo,
        $customerId,
        $_POST['contact_last_name'] ?? [],
        $_POST['contact_first_name'] ?? [],
        $_POST['contact_company'] ?? [],
        $_POST['contact_phone'] ?? [],
        $_POST['contact_email'] ?? []
    );
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

// ---------- RECHNUNG ALS BEZAHLT MARKIEREN (aus der Buchhaltungs-Registerkarte) ----------
if ($action === 'mark_invoice_paid' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $invoiceId = (int)$_POST['invoice_id'];
    $customerId = (int)$_POST['customer_id'];
    $pdo->prepare("UPDATE invoices SET status='bezahlt' WHERE id=? AND customer_id=?")->execute([$invoiceId, $customerId]);
    flash('success', 'Rechnung als bezahlt markiert.');
    redirect('kunden.php?action=edit&id=' . $customerId . '&tab=buchhaltung');
}

if ($action === 'new' || $action === 'edit') {
    $c = ['id'=>0,'company'=>'','first_name'=>'','last_name'=>'','street'=>'','zip'=>'','city'=>'','country'=>'Deutschland','email'=>'','phone'=>'','tax_id'=>'','iban'=>'','bic'=>'','bank_name'=>'','notes'=>''];
    if ($action === 'edit') {
        $stmt = $pdo->prepare('SELECT * FROM customers WHERE id=?');
        $stmt->execute([(int)$_GET['id']]);
        $c = $stmt->fetch();
        if (!$c) { flash('danger','Kunde nicht gefunden.'); redirect('kunden.php'); }
    }

    $contacts = [];
    $offers = [];
    $invoices = [];
    $unpaidSum = 0.0;
    if ($c['id']) {
        $ctStmt = $pdo->prepare('SELECT * FROM customer_contacts WHERE customer_id=? ORDER BY id');
        $ctStmt->execute([$c['id']]);
        $contacts = $ctStmt->fetchAll();

        $offStmt = $pdo->prepare('SELECT * FROM offers WHERE customer_id=? ORDER BY offer_date DESC, id DESC LIMIT 10');
        $offStmt->execute([$c['id']]);
        $offers = $offStmt->fetchAll();

        $invStmt = $pdo->prepare('SELECT * FROM invoices WHERE customer_id=? ORDER BY invoice_date DESC, id DESC LIMIT 10');
        $invStmt->execute([$c['id']]);
        $invoices = $invStmt->fetchAll();

        $sumStmt = $pdo->prepare("SELECT COALESCE(SUM(total_gross),0) AS s FROM invoices WHERE customer_id=? AND status NOT IN ('bezahlt','storniert')");
        $sumStmt->execute([$c['id']]);
        $unpaidSum = (float)$sumStmt->fetch()['s'];
    }

    $activeTab = in_array($_GET['tab'] ?? '', ['allgemein', 'ansprechpartner', 'buchhaltung'], true) ? $_GET['tab'] : 'allgemein';
    ?>
    <h4><?= $action === 'new' ? 'Neuer Kunde' : e($c['company'] ?: trim($c['first_name'].' '.$c['last_name'])) ?></h4>
    <form method="post" action="kunden.php?action=save" class="card p-4" style="max-width:900px;">
      <?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= $c['id'] ?>">

      <ul class="nav nav-tabs mb-3" role="tablist">
        <li class="nav-item" role="presentation">
          <button class="nav-link <?= $activeTab === 'allgemein' ? 'active' : '' ?>" id="tab-allgemein-btn" data-bs-toggle="tab" data-bs-target="#tab-allgemein" type="button" role="tab" aria-controls="tab-allgemein" aria-selected="<?= $activeTab === 'allgemein' ? 'true' : 'false' ?>">Allgemein</button>
        </li>
        <li class="nav-item" role="presentation">
          <button class="nav-link <?= $activeTab === 'ansprechpartner' ? 'active' : '' ?>" id="tab-ansprechpartner-btn" data-bs-toggle="tab" data-bs-target="#tab-ansprechpartner" type="button" role="tab" aria-controls="tab-ansprechpartner" aria-selected="<?= $activeTab === 'ansprechpartner' ? 'true' : 'false' ?>">Ansprechpartner</button>
        </li>
        <li class="nav-item" role="presentation">
          <button class="nav-link <?= $activeTab === 'buchhaltung' ? 'active' : '' ?>" id="tab-buchhaltung-btn" data-bs-toggle="tab" data-bs-target="#tab-buchhaltung" type="button" role="tab" aria-controls="tab-buchhaltung" aria-selected="<?= $activeTab === 'buchhaltung' ? 'true' : 'false' ?>">Buchhaltung</button>
        </li>
      </ul>

      <div class="tab-content">
        <div class="tab-pane fade <?= $activeTab === 'allgemein' ? 'show active' : '' ?>" id="tab-allgemein" role="tabpanel" aria-labelledby="tab-allgemein-btn">
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
        </div>

        <div class="tab-pane fade <?= $activeTab === 'ansprechpartner' ? 'show active' : '' ?>" id="tab-ansprechpartner" role="tabpanel" aria-labelledby="tab-ansprechpartner-btn">
          <table class="table" id="contactTable">
            <thead><tr><th style="width:20%">Nachname</th><th style="width:20%">Vorname</th><th style="width:20%">Firma</th><th style="width:17%">Telefonnummer</th><th style="width:18%">E-Mailadresse</th><th style="width:5%"></th></tr></thead>
            <tbody>
              <?php $contactRows = $contacts ?: [['last_name'=>'','first_name'=>'','company'=>'','phone'=>'','email'=>'']]; ?>
              <?php foreach ($contactRows as $row): ?>
              <tr>
                <td><input type="text" name="contact_last_name[]" class="form-control" value="<?= e($row['last_name']) ?>"></td>
                <td><input type="text" name="contact_first_name[]" class="form-control" value="<?= e($row['first_name']) ?>"></td>
                <td><input type="text" name="contact_company[]" class="form-control" value="<?= e($row['company']) ?>"></td>
                <td><input type="text" name="contact_phone[]" class="form-control" value="<?= e($row['phone']) ?>"></td>
                <td><input type="email" name="contact_email[]" class="form-control" value="<?= e($row['email']) ?>"></td>
                <td><button type="button" class="btn btn-sm btn-outline-danger remove-contact-row">✕</button></td>
              </tr>
              <?php endforeach; ?>
            </tbody>
          </table>
          <button type="button" id="addContactRow" class="btn btn-sm btn-outline-primary">+ Ansprechpartner hinzufügen</button>
        </div>

        <div class="tab-pane fade <?= $activeTab === 'buchhaltung' ? 'show active' : '' ?>" id="tab-buchhaltung" role="tabpanel" aria-labelledby="tab-buchhaltung-btn">
          <h6 class="mb-3">Bankverbindung</h6>
          <div class="row g-3 mb-4">
            <div class="col-md-4"><label class="form-label">IBAN</label><input type="text" name="iban" class="form-control" value="<?= e($c['iban']) ?>"></div>
            <div class="col-md-4"><label class="form-label">BIC</label><input type="text" name="bic" class="form-control" value="<?= e($c['bic']) ?>"></div>
            <div class="col-md-4"><label class="form-label">Bank</label><input type="text" name="bank_name" class="form-control" value="<?= e($c['bank_name']) ?>"></div>
          </div>

          <?php if (!$c['id']): ?>
            <div class="alert alert-info">Offene Posten sowie die Angebots- und Rechnungshistorie sind verfügbar, sobald der Kunde gespeichert wurde.</div>
          <?php else: ?>
            <div class="alert <?= $unpaidSum > 0 ? 'alert-warning' : 'alert-success' ?> d-flex justify-content-between align-items-center">
              <span>Summe unbezahlter Rechnungen</span>
              <strong><?= money($unpaidSum) ?></strong>
            </div>

            <h6 class="mt-4 mb-2">Letzte 10 Angebote</h6>
            <?php if (!$offers): ?>
              <p class="text-muted">Noch keine Angebote vorhanden.</p>
            <?php else: ?>
            <table class="table table-sm">
              <thead><tr><th>Angebotsnummer</th><th>Angebotsdatum</th><th class="text-end">Summe ohne MwSt.</th><th class="text-end">Summe mit MwSt.</th></tr></thead>
              <tbody>
                <?php foreach ($offers as $o): ?>
                <tr>
                  <td><a href="angebote.php?action=view&id=<?= $o['id'] ?>"><?= e($o['offer_number']) ?></a></td>
                  <td><?= date('d.m.Y', strtotime($o['offer_date'])) ?></td>
                  <td class="text-end"><?= money($o['total_net']) ?></td>
                  <td class="text-end"><?= money($o['total_gross']) ?></td>
                </tr>
                <?php endforeach; ?>
              </tbody>
            </table>
            <?php endif; ?>

            <h6 class="mt-4 mb-2">Letzte 10 Rechnungen</h6>
            <?php if (!$invoices): ?>
              <p class="text-muted">Noch keine Rechnungen vorhanden.</p>
            <?php else: ?>
            <table class="table table-sm align-middle">
              <thead><tr><th>Rechnungsnummer</th><th>Rechnungsdatum</th><th class="text-end">Summe inkl. MwSt.</th><th class="text-end"></th></tr></thead>
              <tbody>
                <?php foreach ($invoices as $inv): $isPaid = $inv['status'] === 'bezahlt'; ?>
                <tr class="<?= $isPaid ? 'row-paid' : 'row-unpaid' ?>">
                  <td><a href="rechnungen.php?action=view&id=<?= $inv['id'] ?>"><?= e($inv['invoice_number']) ?></a></td>
                  <td><?= date('d.m.Y', strtotime($inv['invoice_date'])) ?></td>
                  <td class="text-end"><?= money($inv['total_gross']) ?></td>
                  <td class="text-end">
                    <?php if (!$isPaid): ?>
                    <button type="submit" form="markPaid<?= $inv['id'] ?>" class="btn btn-sm btn-success">Bezahlt</button>
                    <?php endif; ?>
                  </td>
                </tr>
                <?php endforeach; ?>
              </tbody>
            </table>
            <?php endif; ?>
          <?php endif; ?>
        </div>
      </div>

      <div class="mt-3">
        <button class="btn btn-primary" type="submit">Speichern</button>
        <a href="kunden.php" class="btn btn-secondary">Abbrechen</a>
      </div>
    </form>

    <?php // Eigenständige Mini-Formulare für "Bezahlt"-Schaltflächen (außerhalb des Haupt-Formulars, da HTML kein verschachteltes <form> erlaubt) ?>
    <?php foreach ($invoices as $inv): if ($inv['status'] !== 'bezahlt'): ?>
      <form id="markPaid<?= $inv['id'] ?>" method="post" action="kunden.php?action=mark_invoice_paid">
        <?= csrf_field() ?>
        <input type="hidden" name="invoice_id" value="<?= $inv['id'] ?>">
        <input type="hidden" name="customer_id" value="<?= $c['id'] ?>">
      </form>
    <?php endif; endforeach; ?>

    <script>
    document.getElementById('addContactRow').addEventListener('click', function() {
      const tbody = document.querySelector('#contactTable tbody');
      const row = tbody.rows[0].cloneNode(true);
      row.querySelectorAll('input').forEach(i => i.value = '');
      tbody.appendChild(row);
      bindContactRow(row);
    });
    function bindContactRow(row) {
      row.querySelector('.remove-contact-row').addEventListener('click', function() {
        if (document.querySelectorAll('#contactTable tbody tr').length > 1) row.remove();
      });
    }
    document.querySelectorAll('#contactTable tbody tr').forEach(bindContactRow);
    </script>
    <?php
    require_once __DIR__ . '/includes/footer.php'; exit;
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
