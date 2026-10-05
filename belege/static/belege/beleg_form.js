// Positionsformular für Angebote und Rechnungen.
//
// Daten kommen als JSON aus dem Template:
//   #artikel-daten      [{id, name, preis, steuersatz, optionen: [{id, abrechnung, preis}]}]
//   #sonderpreise-daten {kundenId: {artikelId: {art: "fixed"|"percent", wert}}}
//   #steuerbefreit-daten [kundenId, ...]
//   #standard-steuer    Standard-MwSt.-Satz
// Der Server prüft und erzwingt alle Regeln (Steuerbefreiung, Preismodell) erneut.
(function () {
  var artikelListe = JSON.parse(document.getElementById('artikel-daten').textContent);
  var sonderpreise = JSON.parse(document.getElementById('sonderpreise-daten').textContent);
  var steuerbefreit = JSON.parse(document.getElementById('steuerbefreit-daten').textContent);
  var standardSteuer = JSON.parse(document.getElementById('standard-steuer').textContent);
  var artikel = {};
  artikelListe.forEach(function (a) { artikel[a.id] = a; });
  var bezeichnung = { einmalig: 'Einmalig', monatlich: 'Monatlich', jaehrlich: 'Jährlich' };
  var kundenWahl = document.querySelector('select[name$="kunde"]:not([name*="pos-"])') || document.getElementById('id_kunde');
  var koerper = document.querySelector('[data-formset="pos"]');

  function zahl(text) {
    var wert = parseFloat(String(text).replace(/\./g, '').replace(',', '.'));
    return isNaN(wert) ? 0 : wert;
  }
  function format(wert) { return wert.toFixed(2).replace('.', ','); }

  function kundeSteuerbefreit() {
    return kundenWahl && steuerbefreit.indexOf(parseInt(kundenWahl.value, 10)) !== -1;
  }

  // Bei steuerbefreiten Kunden ist die MwSt. fest 0 %. Der vorherige Satz wird gemerkt und
  // beim Wechsel zu einem steuerpflichtigen Kunden wiederhergestellt.
  function steuerAnwenden(zeile) {
    var feld = zeile.querySelector('.feld-steuer');
    if (kundeSteuerbefreit()) {
      if (zeile.dataset.befreit !== '1') {
        zeile.dataset.steuerNormal = feld.value;
        zeile.dataset.befreit = '1';
      }
      feld.value = '0,00';
      feld.readOnly = true;
    } else {
      if (zeile.dataset.befreit === '1') {
        feld.value = zeile.dataset.steuerNormal || format(standardSteuer);
        zeile.dataset.befreit = '';
      }
      feld.readOnly = false;
    }
  }

  function sonderpreis(artikelId, basis) {
    var kunde = kundenWahl ? kundenWahl.value : '';
    var treffer = (sonderpreise[kunde] || {})[artikelId];
    if (!treffer) { return null; }
    if (treffer.art === 'percent') { return Math.round(basis * (1 - treffer.wert / 100) * 100) / 100; }
    return treffer.wert;
  }

  // Sonderpreise gelten nur für den Einmalkauf-Standardpreis, nicht für Abo-Preismodelle.
  function sonderpreisAnwenden(zeile) {
    var abrechnung = zeile.querySelector('.feld-abrechnung');
    var artikelId = zeile.querySelector('.artikel-wahl').value;
    if (!artikelId || abrechnung.value !== 'einmalig') { return; }
    var a = artikel[artikelId];
    if (!a) { return; }
    var sp = sonderpreis(artikelId, a.preis);
    zeile.querySelector('.feld-preis').value = format(sp !== null ? sp : a.preis);
  }

  // Bietet nur die Verkaufsmodelle an, die für den Artikel aktiv hinterlegt sind.
  function optionenAufbauen(zeile, aktuell) {
    var auswahl = zeile.querySelector('.feld-abrechnung');
    var versteckt = zeile.querySelector('input[name$="-preisoption"]');
    var artikelId = zeile.querySelector('.artikel-wahl').value;
    var a = artikelId ? artikel[artikelId] : null;
    var modelle = a && a.optionen.length ? a.optionen : [{ id: '', abrechnung: 'einmalig', preis: a ? a.preis : 0 }];
    var html = modelle.map(function (o) {
      return '<option value="' + o.abrechnung + '" data-option-id="' + o.id + '" data-preis="' + o.preis + '">' + bezeichnung[o.abrechnung] + '</option>';
    }).join('');
    if (aktuell && !modelle.some(function (o) { return o.abrechnung === aktuell; })) {
      html += '<option value="' + aktuell + '">' + bezeichnung[aktuell] + '</option>';
    }
    auswahl.innerHTML = html;
    if (aktuell) { auswahl.value = aktuell; }
    var gewaehlt = auswahl.options[auswahl.selectedIndex];
    if (gewaehlt && gewaehlt.dataset.optionId !== undefined && !aktuell) { versteckt.value = gewaehlt.dataset.optionId; }
    if (!a) { versteckt.value = ''; }
  }

  function modellUebernehmen(zeile) {
    var auswahl = zeile.querySelector('.feld-abrechnung');
    var versteckt = zeile.querySelector('input[name$="-preisoption"]');
    var gewaehlt = auswahl.options[auswahl.selectedIndex];
    if (!gewaehlt) { return; }
    versteckt.value = gewaehlt.dataset.optionId || '';
    if (gewaehlt.dataset.preis !== undefined) {
      zeile.querySelector('.feld-preis').value = format(parseFloat(gewaehlt.dataset.preis));
    }
  }

  function zeileBinden(zeile) {
    zeile.querySelector('.artikel-wahl').addEventListener('change', function () {
      var a = artikel[this.value];
      if (a) {
        zeile.querySelector('.feld-beschreibung').value = a.name;
        zeile.querySelector('.feld-preis').value = format(a.preis);
        zeile.querySelector('.feld-steuer').value = format(a.steuersatz);
        zeile.dataset.befreit = '';
      }
      optionenAufbauen(zeile, null);
      modellUebernehmen(zeile);
      steuerAnwenden(zeile);
      sonderpreisAnwenden(zeile);
    });
    zeile.querySelector('.feld-abrechnung').addEventListener('change', function () {
      modellUebernehmen(zeile);
      sonderpreisAnwenden(zeile);
    });
  }

  // Mini-Formulare (Overlay) liefern aktuelle Artikel-/Kundendaten: Nachschlagetabellen nachführen.
  document.addEventListener('auswahl:gespeichert', function (e) {
    var d = e.detail;
    if (d.art === 'artikel') { artikel[d.id] = d.daten; }
    if (d.art === 'kunde') {
      var i = steuerbefreit.indexOf(d.id);
      if (d.daten.steuerbefreit && i === -1) { steuerbefreit.push(d.id); }
      if (!d.daten.steuerbefreit && i !== -1) { steuerbefreit.splice(i, 1); }
    }
  });

  function zeilenInitialisieren() {
    koerper.querySelectorAll('tr').forEach(function (zeile) {
      var aktuell = zeile.querySelector('.feld-abrechnung').value;
      zeileBinden(zeile);
      optionenAufbauen(zeile, aktuell);
      steuerAnwenden(zeile);
    });
  }

  function summeAnzeigen() {
    var netto = 0, steuer = {};
    koerper.querySelectorAll('tr').forEach(function (zeile) {
      if (zeile.style.display === 'none') { return; }
      var menge = zahl(zeile.querySelector('.feld-menge').value);
      var preis = zahl(zeile.querySelector('.feld-preis').value);
      var rabatt = zahl(zeile.querySelector('.feld-rabatt').value);
      var satz = zahl(zeile.querySelector('.feld-steuer').value);
      var zeilennetto = Math.round(menge * preis * (100 - rabatt)) / 100;
      netto += zeilennetto;
      steuer[satz] = (steuer[satz] || 0) + zeilennetto;
    });
    var mwst = 0;
    Object.keys(steuer).forEach(function (satz) { mwst += Math.round(steuer[satz] * parseFloat(satz)) / 100; });
    document.getElementById('summe-netto').textContent = format(netto) + ' €';
    document.getElementById('summe-steuer').textContent = format(mwst) + ' €';
    document.getElementById('summe-brutto').textContent = format(netto + mwst) + ' €';
  }

  if (kundenWahl) {
    kundenWahl.addEventListener('change', function () {
      koerper.querySelectorAll('tr').forEach(function (zeile) { steuerAnwenden(zeile); sonderpreisAnwenden(zeile); });
      summeAnzeigen();
    });
  }
  koerper.addEventListener('formset:hinzugefuegt', function (e) {
    var zeile = e.target;
    zeile.querySelector('.feld-steuer').value = format(standardSteuer);
    zeile.dataset.befreit = '';
    zeile.querySelector('.feld-menge').value = '1,00';
    zeileBinden(zeile);
    optionenAufbauen(zeile, null);
    steuerAnwenden(zeile);
  });
  document.getElementById('positionen').addEventListener('input', summeAnzeigen);
  document.getElementById('positionen').addEventListener('change', summeAnzeigen);
  document.getElementById('positionen').addEventListener('click', function () { setTimeout(summeAnzeigen, 0); });
  zeilenInitialisieren();
  summeAnzeigen();
})();
