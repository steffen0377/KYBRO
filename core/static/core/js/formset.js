// Dynamische Zeilen für Django-Formsets.
//
// Markup: <tbody data-formset="praefix"> mit den Zeilen, ein
// <template id="praefix-leer"> mit der leeren Zeile (Platzhalter __prefix__),
// ein Knopf <button data-formset-add="praefix">. Der Entfernen-Knopf einer Zeile
// trägt die Klasse "formset-entfernen"; die Zeile enthält das DELETE-Kästchen.
(function () {
  function gesamt(praefix) {
    return document.getElementById('id_' + praefix + '-TOTAL_FORMS');
  }

  function zeileBinden(zeile) {
    var knopf = zeile.querySelector('.formset-entfernen');
    if (!knopf) { return; }
    knopf.addEventListener('click', function () {
      var loeschen = zeile.querySelector('input[type=checkbox][name$="-DELETE"]');
      if (loeschen) { loeschen.checked = true; }
      zeile.style.display = 'none';
    });
  }

  document.querySelectorAll('[data-formset]').forEach(function (koerper) {
    koerper.querySelectorAll('tr').forEach(zeileBinden);
  });

  document.querySelectorAll('[data-formset-add]').forEach(function (knopf) {
    knopf.addEventListener('click', function () {
      var praefix = knopf.dataset.formsetAdd;
      var zaehler = gesamt(praefix);
      var vorlage = document.getElementById(praefix + '-leer');
      var koerper = document.querySelector('[data-formset="' + praefix + '"]');
      var index = parseInt(zaehler.value, 10);
      var huelle = document.createElement('tbody');
      huelle.innerHTML = vorlage.innerHTML.replace(/__prefix__/g, index);
      var zeile = huelle.querySelector('tr');
      koerper.appendChild(zeile);
      zaehler.value = index + 1;
      zeileBinden(zeile);
      zeile.dispatchEvent(new CustomEvent('formset:hinzugefuegt', { bubbles: true }));
    });
  });
})();
