// Live-Suche: <input data-livesuche="#ergebnis"> lädt die Seite mit ?ajax=1 nach
// und ersetzt den Inhalt des Zielelements. Weitere Parameter der Seite
// (Sortierung, Filter) bleiben erhalten.
(function () {
  var eingabe = document.querySelector('[data-livesuche]');
  if (!eingabe) { return; }
  var ziel = document.querySelector(eingabe.dataset.livesuche);
  var leeren = document.querySelector('[data-livesuche-leeren]');
  var timer = null;

  function umschalten() {
    if (leeren) { leeren.style.display = eingabe.value ? '' : 'none'; }
  }

  function suchen() {
    var url = new URL(window.location.href);
    if (eingabe.value) { url.searchParams.set('q', eingabe.value); } else { url.searchParams.delete('q'); }
    var abruf = new URL(url);
    abruf.searchParams.set('ajax', '1');
    fetch(abruf.toString(), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
      .then(function (r) { return r.text(); })
      .then(function (html) {
        ziel.innerHTML = html;
        window.history.replaceState({}, '', url);
      });
  }

  eingabe.addEventListener('input', function () {
    umschalten();
    clearTimeout(timer);
    timer = setTimeout(suchen, 300);
  });
  if (leeren) {
    leeren.addEventListener('click', function () {
      eingabe.value = '';
      umschalten();
      suchen();
      eingabe.focus();
    });
  }
  umschalten();
})();
