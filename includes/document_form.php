<?php
// Erwartet: $doc, $docType, $items, $customers, $articles, $dateField, $dateLabel,
//           $secondDateField, $secondDateLabel, $statuses, $saveUrl, $formTitle
if (empty($items)) {
    $items = [['article_id'=>'', 'description'=>'', 'quantity'=>1, 'unit_price'=>0, 'tax_rate'=>company_settings()['default_tax_rate']]];
}
?>
<h4><?= e($formTitle) ?></h4>
<form method="post" action="<?= e($saveUrl) ?>" class="card p-4">
  <?= csrf_field() ?>
  <input type="hidden" name="id" value="<?= $doc['id'] ?>">
  <div class="row g-3 mb-3">
    <div class="col-md-4">
      <label class="form-label">Kunde *</label>
      <select name="customer_id" class="form-select" required>
        <option value="">Kunde wählen…</option>
        <?php foreach ($customers as $c): ?>
          <option value="<?= $c['id'] ?>" <?= (int)$doc['customer_id']===(int)$c['id']?'selected':'' ?>>
            <?= e($c['company'] ?: trim($c['first_name'].' '.$c['last_name'])) ?>
          </option>
        <?php endforeach; ?>
      </select>
    </div>
    <div class="col-md-3">
      <label class="form-label"><?= e($dateLabel) ?></label>
      <input type="date" name="<?= $dateField ?>" class="form-control" value="<?= e($doc[$dateField]) ?>">
    </div>
    <div class="col-md-3">
      <label class="form-label"><?= e($secondDateLabel) ?></label>
      <input type="date" name="<?= $secondDateField ?>" class="form-control" value="<?= e($doc[$secondDateField]) ?>">
    </div>
    <div class="col-md-2">
      <label class="form-label">Status</label>
      <select name="status" class="form-select">
        <?php foreach ($statuses as $s): ?>
          <option value="<?= $s ?>" <?= $doc['status']===$s?'selected':'' ?>><?= ucfirst($s) ?></option>
        <?php endforeach; ?>
      </select>
    </div>
  </div>

  <table class="table" id="itemsTable">
    <thead><tr><th style="width:22%">Artikel</th><th>Beschreibung</th><th style="width:10%">Menge</th><th style="width:13%">Einzelpreis</th><th style="width:10%">MwSt. %</th><th style="width:5%"></th></tr></thead>
    <tbody>
      <?php foreach ($items as $it): ?>
      <tr>
        <td>
          <select class="form-select article-select">
            <option value="">— manuell —</option>
            <?php foreach ($articles as $a): ?>
              <option value="<?= $a['id'] ?>" data-name="<?= e($a['name']) ?>" data-price="<?= num($a['sale_price']) ?>" data-tax="<?= num($a['tax_rate']) ?>" <?= (int)($it['article_id']??0)===(int)$a['id']?'selected':'' ?>><?= e($a['name']) ?></option>
            <?php endforeach; ?>
          </select>
          <input type="hidden" name="article_id[]" class="article-id-field" value="<?= e($it['article_id'] ?? '') ?>">
        </td>
        <td><input type="text" name="description[]" class="form-control desc-field" value="<?= e($it['description']) ?>"></td>
        <td><input type="text" name="quantity[]" class="form-control qty-field" value="<?= num($it['quantity']) ?>"></td>
        <td><input type="text" name="unit_price[]" class="form-control price-field" value="<?= num($it['unit_price']) ?>"></td>
        <td><input type="text" name="tax_rate[]" class="form-control tax-field" value="<?= num($it['tax_rate']) ?>"></td>
        <td><button type="button" class="btn btn-sm btn-outline-danger remove-row">✕</button></td>
      </tr>
      <?php endforeach; ?>
    </tbody>
  </table>
  <button type="button" id="addRow" class="btn btn-sm btn-outline-primary mb-3">+ Position hinzufügen</button>

  <div class="mb-3">
    <label class="form-label">Notizen</label>
    <textarea name="notes" class="form-control" rows="2"><?= e($doc['notes']) ?></textarea>
  </div>

  <div class="mt-3">
    <button class="btn btn-primary" type="submit">Speichern</button>
    <a href="<?= $docType === 'offer' ? 'angebote.php' : 'rechnungen.php' ?>" class="btn btn-secondary">Abbrechen</a>
  </div>
</form>

<script>
document.getElementById('addRow').addEventListener('click', function() {
  const tbody = document.querySelector('#itemsTable tbody');
  const row = tbody.rows[0].cloneNode(true);
  row.querySelectorAll('input').forEach(i => { if (i.type !== 'hidden') i.value = ''; else i.value=''; });
  row.querySelector('.article-select').value = '';
  row.querySelector('.qty-field').value = '1';
  row.querySelector('.tax-field').value = '<?= num(company_settings()['default_tax_rate']) ?>';
  tbody.appendChild(row);
  bindRow(row);
});

function bindRow(row) {
  row.querySelector('.remove-row').addEventListener('click', function() {
    if (document.querySelectorAll('#itemsTable tbody tr').length > 1) row.remove();
  });
  row.querySelector('.article-select').addEventListener('change', function() {
    const opt = this.options[this.selectedIndex];
    row.querySelector('.article-id-field').value = this.value;
    if (this.value) {
      row.querySelector('.desc-field').value = opt.dataset.name;
      row.querySelector('.price-field').value = opt.dataset.price;
      row.querySelector('.tax-field').value = opt.dataset.tax;
    }
  });
}
document.querySelectorAll('#itemsTable tbody tr').forEach(bindRow);
</script>
