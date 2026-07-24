<?php
$pageTitle = 'Einstellungen';
require_once __DIR__ . '/includes/header.php';
require_admin();
$pdo = db();

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    csrf_check();
    $stmt = $pdo->prepare('UPDATE company_settings SET company_name=?,street=?,zip=?,city=?,country=?,tax_id=?,iban=?,bic=?,bank_name=?,email=?,phone=?,offer_prefix=?,invoice_prefix=?,default_tax_rate=? WHERE id=1');
    $stmt->execute([
        trim($_POST['company_name']), trim($_POST['street']), trim($_POST['zip']), trim($_POST['city']),
        trim($_POST['country']), trim($_POST['tax_id']), trim($_POST['iban']), trim($_POST['bic']),
        trim($_POST['bank_name']), trim($_POST['email']), trim($_POST['phone']),
        trim($_POST['offer_prefix']), trim($_POST['invoice_prefix']),
        (float)str_replace(',', '.', $_POST['default_tax_rate']),
    ]);

    if (!empty($_POST['remove_logo'])) {
        $current = $pdo->query('SELECT logo_path FROM company_settings WHERE id=1')->fetch()['logo_path'];
        if ($current) { @unlink(__DIR__ . '/' . $current); }
        $pdo->prepare('UPDATE company_settings SET logo_path=NULL WHERE id=1')->execute();
    } elseif (!empty($_FILES['logo']['name']) && $_FILES['logo']['error'] === UPLOAD_ERR_OK) {
        $allowed = ['image/png' => 'png', 'image/jpeg' => 'jpg', 'image/svg+xml' => 'svg', 'image/webp' => 'webp'];
        $finfo = finfo_open(FILEINFO_MIME_TYPE);
        $mime = finfo_file($finfo, $_FILES['logo']['tmp_name']);
        finfo_close($finfo);
        if (isset($allowed[$mime]) && $_FILES['logo']['size'] <= 2 * 1024 * 1024) {
            foreach (glob(__DIR__ . '/uploads/logo.*') as $old) { @unlink($old); }
            $target = 'uploads/logo.' . $allowed[$mime];
            if (move_uploaded_file($_FILES['logo']['tmp_name'], __DIR__ . '/' . $target)) {
                $pdo->prepare('UPDATE company_settings SET logo_path=? WHERE id=1')->execute([$target]);
            } else {
                flash('danger', 'Logo konnte nicht gespeichert werden. Bitte Schreibrechte für den Ordner "uploads/" prüfen.');
            }
        } else {
            flash('danger', 'Ungültiges Bildformat oder Datei zu groß (max. 2 MB; erlaubt: PNG, JPG, SVG, WEBP).');
        }
    }

    flash('success', 'Einstellungen gespeichert.');
    redirect('einstellungen.php');
}

$s = company_settings();
?>
<h4>Firmeneinstellungen</h4>
<form method="post" enctype="multipart/form-data" class="card p-4" style="max-width:700px;">
  <?= csrf_field() ?>
  <div class="row g-3">
    <div class="col-12">
      <label class="form-label">Logo</label><br>
      <?php if (!empty($s['logo_path'])): ?>
        <img src="<?= APP_URL ?>/<?= e($s['logo_path']) ?>?v=<?= time() ?>" alt="Aktuelles Logo" style="max-height:80px; max-width:240px;" class="d-block mb-2 border rounded p-1">
        <div class="form-check mb-2">
          <input type="checkbox" name="remove_logo" value="1" class="form-check-input" id="remove_logo">
          <label class="form-check-label" for="remove_logo">Aktuelles Logo entfernen</label>
        </div>
      <?php else: ?>
        <div class="text-muted mb-2">Kein Logo hinterlegt – es wird stattdessen nur der Firmenname angezeigt.</div>
      <?php endif; ?>
      <input type="file" name="logo" class="form-control" accept=".png,.jpg,.jpeg,.svg,.webp">
      <div class="form-text">PNG, JPG, SVG oder WEBP, max. 2 MB. Wird links in der Seitenleiste angezeigt.</div>
    </div>
    <div class="col-12"><label class="form-label">Firmenname / Anwendungsname</label><input type="text" name="company_name" class="form-control" value="<?= e($s['company_name']) ?>"></div>
    <div class="col-md-8"><label class="form-label">Straße & Nr.</label><input type="text" name="street" class="form-control" value="<?= e($s['street']) ?>"></div>
    <div class="col-md-4"><label class="form-label">PLZ</label><input type="text" name="zip" class="form-control" value="<?= e($s['zip']) ?>"></div>
    <div class="col-md-6"><label class="form-label">Ort</label><input type="text" name="city" class="form-control" value="<?= e($s['city']) ?>"></div>
    <div class="col-md-6"><label class="form-label">Land</label><input type="text" name="country" class="form-control" value="<?= e($s['country']) ?>"></div>
    <div class="col-md-6"><label class="form-label">E-Mail</label><input type="email" name="email" class="form-control" value="<?= e($s['email']) ?>"></div>
    <div class="col-md-6"><label class="form-label">Telefon</label><input type="text" name="phone" class="form-control" value="<?= e($s['phone']) ?>"></div>
    <div class="col-md-6"><label class="form-label">USt-IdNr.</label><input type="text" name="tax_id" class="form-control" value="<?= e($s['tax_id']) ?>"></div>
    <div class="col-md-6"><label class="form-label">Standard-MwSt.-Satz (%)</label><input type="text" name="default_tax_rate" class="form-control" value="<?= num($s['default_tax_rate']) ?>"></div>
    <div class="col-md-4"><label class="form-label">IBAN</label><input type="text" name="iban" class="form-control" value="<?= e($s['iban']) ?>"></div>
    <div class="col-md-4"><label class="form-label">BIC</label><input type="text" name="bic" class="form-control" value="<?= e($s['bic']) ?>"></div>
    <div class="col-md-4"><label class="form-label">Bank</label><input type="text" name="bank_name" class="form-control" value="<?= e($s['bank_name']) ?>"></div>
    <div class="col-md-6"><label class="form-label">Präfix Angebotsnummer</label><input type="text" name="offer_prefix" class="form-control" value="<?= e($s['offer_prefix']) ?>"></div>
    <div class="col-md-6"><label class="form-label">Präfix Rechnungsnummer</label><input type="text" name="invoice_prefix" class="form-control" value="<?= e($s['invoice_prefix']) ?>"></div>
  </div>
  <button class="btn btn-primary mt-3" type="submit">Speichern</button>
</form>
<?php require_once __DIR__ . '/includes/footer.php'; ?>
