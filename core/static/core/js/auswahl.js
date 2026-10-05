// Durchsuchbare Auswahlfelder mit Overlay-Mini-Formularen.
//
//   <select data-suche>                      wird zu einem Eingabefeld mit Suche (das <select> bleibt als versteckte
//                                            Datenquelle erhalten; "change"-Ereignisse und .value funktionieren weiter)
//   data-schnell-art="kunde|artikel|..."     Kennung für Neu/Bearbeiten und für das Nachführen gleichartiger Felder
//   data-neu-url / data-bearbeiten-url       Knöpfe "+" und Stift öffnen ein Mini-Formular im Dialog
//                                            (bei data-bearbeiten-url steht "/0/" als Platzhalter für die ID)
//
// Nach dem Speichern wird das Ereignis "auswahl:gespeichert" ({art, id, label, daten}) am document ausgelöst,
// bevor das Feld auf den Datensatz umgestellt und "change" gesendet wird. Neu hinzugefügte Zeilen
// (Ereignis "formset:hinzugefuegt") werden automatisch initialisiert.
(function () {
  var MAX_TREFFER = 60;

  function textNormal(text) { return String(text || '').toLowerCase(); }

  function csrf() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  // ---------------------------------------------------------------- Dialog mit Mini-Formular
  var dialog = null;
  function dialogHolen() {
    if (dialog) { return dialog; }
    dialog = document.createElement('dialog');
    dialog.className = 'overlay-dialog';
    document.body.appendChild(dialog);
    return dialog;
  }

  function formularLaden(url, beiErfolg) {
    var d = dialogHolen();
    d.innerHTML = '<p class="m-3 text-muted">Lade…</p>';
    if (!d.open) { d.showModal(); }
    fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) {
        if (r.status === 403) { throw new Error('Dafür fehlt Ihnen die Berechtigung.'); }
        if (!r.ok) { throw new Error('Das Formular konnte nicht geladen werden.'); }
        return r.text();
      })
      .then(function (html) { formularAnzeigen(url, html, beiErfolg); })
      .catch(function (fehler) {
        d.innerHTML = '<div class="p-3"><div class="alert alert-app-danger">' + fehler.message +
          '</div><button type="button" class="btn btn-app-secondary">Schließen</button></div>';
        d.querySelector('button').addEventListener('click', function () { d.close(); });
      });
  }

  function formularAnzeigen(url, html, beiErfolg) {
    var d = dialogHolen();
    d.innerHTML = html;
    var form = d.querySelector('form[data-schnell-form]');
    if (!form) { d.close(); return; }
    var erstes = form.querySelector('input:not([type=hidden]), select, textarea');
    if (erstes) { erstes.focus(); }
    d.querySelector('[data-schnell-abbrechen]').addEventListener('click', function () { d.close(); });
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      fetch(url, {
        method: 'POST', body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf() },
      }).then(function (r) {
        if (r.status === 403) { throw new Error('Dafür fehlt Ihnen die Berechtigung.'); }
        if (r.status === 422) { return r.text().then(function (h) { formularAnzeigen(url, h, beiErfolg); }); }
        if (!r.ok) { throw new Error('Speichern fehlgeschlagen.'); }
        return r.json().then(function (ergebnis) { d.close(); beiErfolg(ergebnis); });
      }).catch(function (fehler) {
        var hinweis = document.createElement('div');
        hinweis.className = 'alert alert-app-danger py-2';
        hinweis.textContent = fehler.message;
        form.insertBefore(hinweis, form.firstChild);
      });
    });
  }

  // ---------------------------------------------------------------- Auswahlfeld
  function optionAktualisieren(select, id, label) {
    var option = null;
    Array.prototype.forEach.call(select.options, function (o) { if (o.value === String(id)) { option = o; } });
    if (!option) {
      option = document.createElement('option');
      option.value = id;
      select.appendChild(option);
    }
    option.textContent = label;
  }

  function aufbauen(select) {
    if (select.dataset.auswahlBereit) { return; }
    select.dataset.auswahlBereit = '1';
    var art = select.dataset.schnellArt || '';

    var huelle = document.createElement('div');
    huelle.className = 'auswahl input-group';
    var eingabe = document.createElement('input');
    eingabe.type = 'text';
    eingabe.className = 'form-control auswahl-eingabe';
    eingabe.autocomplete = 'off';
    eingabe.placeholder = 'Suchen oder auswählen…';
    eingabe.required = select.required;
    select.required = false;
    eingabe.setAttribute('aria-label', select.getAttribute('aria-label') || '');
    var liste = document.createElement('ul');
    liste.className = 'auswahl-liste';
    liste.hidden = true;
    // Grundlegende Darstellung inline, damit die Liste auch mit veraltetem CSS-Cache als Overlay erscheint.
    liste.style.cssText = 'position:fixed;z-index:2000;max-height:280px;overflow-y:auto;margin:0;padding:.25rem 0;' +
      'list-style:none;background:#fff;border:1px solid rgba(0,0,0,.2);border-radius:.375rem;' +
      'box-shadow:0 .5rem 1rem rgba(0,0,0,.15)';

    select.parentNode.insertBefore(huelle, select);
    huelle.appendChild(eingabe);
    huelle.appendChild(select);
    select.hidden = true;
    select.style.display = 'none';
    document.body.appendChild(liste);

    var neuKnopf = null, bearbeitenKnopf = null;
    function knopf(text, titel, icon) {
      var k = document.createElement('button');
      k.type = 'button';
      k.className = 'btn btn-app-outline-secondary';
      k.title = titel;
      k.innerHTML = '<i class="bi ' + icon + '"></i>';
      huelle.appendChild(k);
      return k;
    }
    if (select.dataset.neuUrl) {
      neuKnopf = knopf('+', 'Neu anlegen', 'bi-plus-lg');
      neuKnopf.addEventListener('click', function () {
        formularLaden(select.dataset.neuUrl, function (e) { gespeichert(select, art, e, true); });
      });
    }
    if (select.dataset.bearbeitenUrl) {
      bearbeitenKnopf = knopf('✎', 'Auswahl bearbeiten', 'bi-pencil');
      bearbeitenKnopf.addEventListener('click', function () {
        if (!select.value) { return; }
        var url = select.dataset.bearbeitenUrl.replace(/\/0\/$/, '/' + select.value + '/');
        formularLaden(url, function (e) { gespeichert(select, art, e, false); });
      });
    }

    var treffer = [], aktiv = -1;

    function ausgewaehlterText() {
      var o = select.options[select.selectedIndex];
      return o && o.value ? o.textContent : '';
    }
    function anzeigeAktualisieren() {
      eingabe.value = ausgewaehlterText();
      if (bearbeitenKnopf) { bearbeitenKnopf.disabled = !select.value; }
    }

    function schliessen() { liste.hidden = true; aktiv = -1; }
    function positionieren() {
      var r = eingabe.getBoundingClientRect();
      liste.style.left = r.left + 'px';
      liste.style.top = r.bottom + 'px';
      liste.style.minWidth = Math.max(r.width, 260) + 'px';
    }
    function hervorheben() {
      Array.prototype.forEach.call(liste.children, function (li, i) { li.classList.toggle('aktiv', i === aktiv); });
      if (aktiv >= 0 && liste.children[aktiv]) { liste.children[aktiv].scrollIntoView({ block: 'nearest' }); }
    }
    function waehlen(wert) {
      select.value = wert;
      anzeigeAktualisieren();
      schliessen();
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }
    function listeBauen(filter) {
      var worte = textNormal(filter).split(/\s+/).filter(Boolean);
      treffer = [];
      Array.prototype.forEach.call(select.options, function (o) {
        var t = textNormal(o.textContent);
        if (worte.every(function (w) { return t.indexOf(w) !== -1; })) { treffer.push(o); }
      });
      liste.innerHTML = '';
      treffer.slice(0, MAX_TREFFER).forEach(function (o) {
        var li = document.createElement('li');
        li.textContent = o.value ? o.textContent : (o.textContent || '— keine Auswahl —');
        if (!o.value) { li.classList.add('leer'); }
        li.addEventListener('mousedown', function (e) { e.preventDefault(); waehlen(o.value); });
        liste.appendChild(li);
      });
      if (treffer.length > MAX_TREFFER) {
        var mehr = document.createElement('li');
        mehr.className = 'mehr';
        mehr.textContent = '… ' + (treffer.length - MAX_TREFFER) + ' weitere, bitte Suche eingrenzen';
        liste.appendChild(mehr);
      }
      if (!treffer.length) {
        var keine = document.createElement('li');
        keine.className = 'mehr';
        keine.textContent = 'Keine Treffer';
        liste.appendChild(keine);
      }
      aktiv = treffer.length === 1 && filter ? 0 : -1;
      positionieren();
      liste.hidden = false;
      hervorheben();
    }

    eingabe.addEventListener('focus', function () { eingabe.select(); listeBauen(''); });
    eingabe.addEventListener('input', function () { listeBauen(eingabe.value); });
    eingabe.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (liste.hidden) { listeBauen(eingabe.value); } aktiv = Math.min(aktiv + 1, Math.min(treffer.length, MAX_TREFFER) - 1); hervorheben(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); aktiv = Math.max(aktiv - 1, 0); hervorheben(); }
      else if (e.key === 'Enter') { if (!liste.hidden && aktiv >= 0 && treffer[aktiv]) { e.preventDefault(); waehlen(treffer[aktiv].value); } }
      else if (e.key === 'Escape') { schliessen(); anzeigeAktualisieren(); }
    });
    eingabe.addEventListener('blur', function () {
      setTimeout(function () {
        schliessen();
        // Freitext, der zu keinem Eintrag passt, wird verworfen; ein leeres Feld löscht die Auswahl (falls erlaubt).
        var text = textNormal(eingabe.value).trim();
        var gefunden = null;
        Array.prototype.forEach.call(select.options, function (o) {
          if (o.value && textNormal(o.textContent) === text) { gefunden = o; }
        });
        if (gefunden) { if (select.value !== gefunden.value) { waehlen(gefunden.value); } }
        else if (!text && select.querySelector('option[value=""]') && select.value) { waehlen(''); }
        else { anzeigeAktualisieren(); }
      }, 120);
    });
    window.addEventListener('scroll', function () { if (!liste.hidden) { positionieren(); } }, true);
    window.addEventListener('resize', function () { if (!liste.hidden) { positionieren(); } });
    select.addEventListener('change', anzeigeAktualisieren);
    select.addEventListener('auswahl:neu-gesetzt', anzeigeAktualisieren);
    anzeigeAktualisieren();
  }

  // Ergebnis eines Mini-Formulars: gleichartige Felder nachführen, Ereignis senden, Auswahl setzen.
  function gespeichert(select, art, ergebnis, neu) {
    document.querySelectorAll('select[data-schnell-art="' + art + '"]').forEach(function (s) {
      var vorhanden = Array.prototype.some.call(s.options, function (o) { return o.value === String(ergebnis.id); });
      if (vorhanden || s === select) { optionAktualisieren(s, ergebnis.id, ergebnis.label); }
      s.dispatchEvent(new Event('auswahl:neu-gesetzt'));
    });
    document.dispatchEvent(new CustomEvent('auswahl:gespeichert', {
      detail: { art: art, id: ergebnis.id, label: ergebnis.label, daten: ergebnis.daten || {}, neu: neu },
    }));
    select.value = String(ergebnis.id);
    select.dispatchEvent(new Event('change', { bubbles: true }));
    select.dispatchEvent(new Event('auswahl:neu-gesetzt'));
  }

  function alleAufbauen(wurzel) {
    (wurzel || document).querySelectorAll('select[data-suche]').forEach(aufbauen);
  }

  document.addEventListener('formset:hinzugefuegt', function (e) { alleAufbauen(e.target); });
  alleAufbauen(document);
})();
