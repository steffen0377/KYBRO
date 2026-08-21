<?php
// Erwartet: $doc (offer oder invoice), $items, $docLabel ('Angebot'/'Rechnung'),
//           $docNumberField ('offer_number'/'invoice_number'), $dateField, $dateLabel,
//           $secondDateField, $secondDateLabel, $company
ob_start();
?>
<style>
  body { font-family: DejaVu Sans, sans-serif; font-size: 11px; color: #222; }
  .header { display: flex; justify-content: space-between; margin-bottom: 30px; }
  .company-name { font-size: 16px; font-weight: bold; }
  h1 { font-size: 20px; margin-bottom: 0; }
  table { width: 100%; border-collapse: collapse; margin-top: 15px; }
  th { background: #eee; text-align: left; padding: 6px; border-bottom: 2px solid #999; }
  td { padding: 6px; border-bottom: 1px solid #ddd; }
  .text-end { text-align: right; }
  .totals td { border: none; padding: 3px 6px; }
  .totals .fw-bold { font-weight: bold; font-size: 13px; }
  .meta { margin: 20px 0; }
  .footer { margin-top: 50px; font-size: 9px; color: #666; border-top: 1px solid #ccc; padding-top: 10px; }
</style>

<div class="header">
  <div>
    <div class="company-name"><?= e($company['company_name']) ?></div>
    <div><?= e($company['street']) ?></div>
    <div><?= e($company['zip'] . ' ' . $company['city']) ?></div>
    <div><?= e($company['country']) ?></div>
  </div>
  <div style="text-align:right;">
    <?php if ($company['email']): ?><div>E-Mail: <?= e($company['email']) ?></div><?php endif; ?>
    <?php if ($company['phone']): ?><div>Tel.: <?= e($company['phone']) ?></div><?php endif; ?>
    <?php if ($company['tax_id']): ?><div>USt-IdNr.: <?= e($company['tax_id']) ?></div><?php endif; ?>
  </div>
</div>

<div>
  <?= e($doc['company'] ?: trim($doc['first_name'].' '.$doc['last_name'])) ?><br>
  <?= e($doc['street']) ?><br>
  <?= e($doc['zip'] . ' ' . $doc['city']) ?>
</div>

<h1><?= e($docLabel) ?> <?= e($doc[$docNumberField]) ?></h1>

<div class="meta">
  <strong><?= e($dateLabel) ?>:</strong> <?= date('d.m.Y', strtotime($doc[$dateField])) ?>
  <?php if (!empty($doc[$secondDateField])): ?>
    &nbsp;&nbsp; <strong><?= e($secondDateLabel) ?>:</strong> <?= date('d.m.Y', strtotime($doc[$secondDateField])) ?>
  <?php endif; ?>
</div>

<table>
  <thead>
    <tr><th>Beschreibung</th><th class="text-end">Menge</th><th class="text-end">Einzelpreis</th><th class="text-end">MwSt.</th><th class="text-end">Gesamt (netto)</th></tr>
  </thead>
  <tbody>
    <?php foreach ($items as $it): ?>
    <tr>
      <td><?= e($it['description']) ?></td>
      <td class="text-end"><?= num($it['quantity']) ?></td>
      <td class="text-end"><?= money($it['unit_price']) ?></td>
      <td class="text-end"><?= num($it['tax_rate']) ?>%</td>
      <td class="text-end"><?= money($it['quantity'] * $it['unit_price']) ?></td>
    </tr>
    <?php endforeach; ?>
  </tbody>
</table>

<table class="totals" style="width:300px; margin-left:auto;">
  <tr><td>Netto-Summe</td><td class="text-end"><?= money($doc['total_net']) ?></td></tr>
  <tr><td>zzgl. MwSt.</td><td class="text-end"><?= money($doc['total_tax']) ?></td></tr>
  <tr><td class="fw-bold">Gesamtbetrag</td><td class="text-end fw-bold"><?= money($doc['total_gross']) ?></td></tr>
</table>

<?php if (!empty($doc['notes'])): ?>
  <div style="margin-top:20px;"><?= nl2br(e($doc['notes'])) ?></div>
<?php endif; ?>

<div class="footer">
  <?= e($company['company_name']) ?> · <?= e($company['street']) ?>, <?= e($company['zip'].' '.$company['city']) ?>
  <?php if ($company['iban']): ?> · IBAN: <?= e($company['iban']) ?><?php endif; ?>
  <?php if ($company['bic']): ?> · BIC: <?= e($company['bic']) ?><?php endif; ?>
</div>
<?php
return ob_get_clean();
