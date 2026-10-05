# Abnahmeliste

Diese Liste dient der fachlichen Abnahme von KYBRO (Django) gegenüber der bisherigen PHP-Anwendung. Alle
Punkte lassen sich in einer frisch eingerichteten Testinstallation durchspielen
(Anleitung: `docs/Betrieb.md`, Abschnitt „Erste Einrichtung“). Zu jedem Punkt Ergebnis und Datum eintragen.

## A. Einrichtung und Rechte

- [ ] Lizenzprüfung ist standardmäßig aus (Fachseiten ohne Lizenz nutzbar). Optional: `LIZENZ_PRUEFUNG=True` setzen; ohne Lizenz „Warenwirtschaft“ erscheint „Keine gültige Lizenz“, Einstellungen bleiben erreichbar.
- [ ] Firmendaten hinterlegen; unter Einstellungen › Briefbogen Logo (Bild) und Textblöcke (Anschrift, Bankverbindung, Fußzeile, mit Platzhaltern) anlegen und per Vorschau (PDF) positionieren; Präfixe und Zahlungsziel ändern.
- [ ] Benutzer und Gruppe anlegen; Gruppe mit nur „Artikel: Lesen“ sieht nur Artikel und kann nichts ändern (403 beim Aufruf von Schreibseiten).
- [ ] Ein Administrator kann sich nicht selbst die Rolle entziehen oder das eigene Konto deaktivieren.
- [ ] LDAP (falls genutzt): Anmeldung, automatische Anlage des Benutzers, „Verbindung testen“; bei „Nur LDAP“ und abgeschaltetem Server Notfallzugang nur für lokale Administratoren.

## B. Stammdaten und Lager

- [ ] Artikel anlegen (Artikelnummer wird automatisch fünfstellig vergeben), Kategorien als Baum, Zyklusschutz beim Verschieben.
- [ ] Sonderpreis (Fixpreis und Prozent) und Abo-Preismodelle (monatlich/jährlich, Mindestlaufzeit, Kündigungsfrist) am Artikel.
- [ ] Kunde mit Ansprechpartnern und Buchhaltungsdaten (Kundennummer `K-00001`), Lieferant (`L-00001`); Suche in Listen.
- [ ] Wareneingang, Inventurkorrektur, Seriennummern einlagern/als defekt markieren/entfernen; Lagerbewegungen nachvollziehbar.

## C. Belege

- [ ] Angebot erstellen: Artikelwahl füllt Beschreibung, Preis, MwSt.; Sonderpreis des Kunden wird nur beim Einmalkauf angewendet; Summen live.
- [ ] Steuerbefreiter Kunde: MwSt. wird 0 % und gesperrt; beim Wechsel des Kunden zurück auf den normalen Satz.
- [ ] Angebot → Auftrag → Rechnung; ein zweiter Klick erzeugt nichts doppelt.
- [ ] Rechnung bucht Lagerbestand aus; Bearbeiten des Entwurfs bucht neu; Löschen/Stornieren des Entwurfs stellt den Bestand wieder her.
- [ ] Seriennummern der Rechnung zuordnen; Bestand sinkt je Seriennummer.
- [ ] Ausgestellte Rechnung ist gesperrt (kein Bearbeiten, Löschen, Zurück in den Entwurf); als bezahlt markieren.
- [ ] Belegnummern: fortlaufend je Jahr (`RE-2026-0001`), Zähler im neuen Jahr wieder bei 1; Anpassung unter Einstellungen › Nummernkreise.
- [ ] „Als Artikel anlegen“ aus einer Freitext-Position im Angebot.

## D. PDF und E-Rechnung

- [ ] PDF von Angebot, Auftrag und Rechnung: Briefbogen-Elemente (auch auf Folgeseiten, Inhalt läuft nicht in die Fußzeile), Logo, Empfängerfeld im Fensterumschlag, Spalten, Texte, Fußzeile, Seitenzahl.
- [ ] Formulareinstellungen: Änderung pro Belegart und global wirkt im PDF (Titel, Texte, Akzentfarbe, Spalten).
- [ ] Mehrseitige Rechnung (viele Positionen): Kopfzeile der Tabelle, Seitenzahlen.
- [ ] ZUGFeRD: PDF der Rechnung öffnen und das eingebettete XML (`factur-x.xml`) prüfen, am besten mit dem KoSIT-Validator oder dem Prüfdienst Ihres Steuerberaters/Empfängers; Profil EN 16931.
- [ ] Rechnung mit steuerbefreitem Kunden: Hinweis im PDF, im XML Kategorie E mit Befreiungsgrund.

## E. Abonnements

- [ ] Rechnung mit Abo-Artikel (monatlich) ausstellen → Abonnement erscheint; Folgetermin korrekt (auch Monatsende).
- [ ] `python manage.py abo_rechnungen_erzeugen --stichtag JJJJ-MM-TT` zweimal ausführen: nur ein Entwurf entsteht; Freigabe schaltet den Termin weiter.
- [ ] Kündigung: Vorschau des Endtermins (Mindestlaufzeit, Kündigungsfrist, Abrechnungszeitraum); Rücknahme; Ende nach Wirksamkeit.
- [ ] Systemd-Timer `kybro-abos.timer` läuft (`systemctl list-timers`).

## F0. Testbetrieb und Livegang

- [ ] Neue Installation zeigt den Testbetrieb-Hinweis; „Live-Betrieb aktivieren“ erscheint nur für Administratoren.
- [ ] Nach dem Livegang: Testdaten weg, Firmendaten/Benutzer/LDAP/Formulare erhalten, Belegnummer beginnt wieder bei 0001, Hinweis und Funktion verschwunden.

## F. Einstellungen

- [ ] SMTP eintragen und Testmail an die eigene Adresse senden.
- [ ] Gespeicherte Passwörter (SMTP, LDAP) werden im Formular nicht angezeigt und bleiben bei leerem Feld erhalten.

## G. Mobile-API (falls die App-Entwicklung beginnt)

- [ ] Anmeldung, Sperre nach 5 Fehlversuchen, Token läuft ab.
- [ ] Auftrag mit Unterschrift senden; erneutes Senden mit derselben `client_uuid` erzeugt keinen zweiten Auftrag.
- [ ] Rechnung aus unterschriebenem Auftrag; Delta-Abruf (`since`) für Kunden, Artikel, Aufträge.

## H. Betrieb

- [ ] Installation nach `docs/Betrieb.md` auf dem Zielserver; HTTPS, Dienste starten nach Neustart.
- [ ] Sicherung und Wiederherstellung (Datenbank, `media/`, `.env`) einmal durchspielen.

## Bewusste Abweichungen von der PHP-Anwendung

* Belegnummern setzen sich aus Präfix, **Jahr** und vierstelliger Nummer zusammen und zählen jährlich neu (PHP: fortlaufend, fünfstellig).
* Lagerbuchungen eines **Entwurfs** werden bei Änderung, Löschen und Stornierung sauber zurückgenommen.
* Abonnements entstehen beim **ersten Verlassen des Entwurfs**; Termine werden stets vom Abo-Beginn aus gerechnet; die Menge fließt in den Abo-Preis.
* Eine ausgestellte Rechnung kann nicht zurück in den Entwurf gesetzt werden (Unveränderbarkeit).
* Die Steuer wird je Steuersatz auf die Summe der gerundeten Zeilen berechnet (wie in der E-Rechnung gefordert), nicht je Zeile.
* PDF-Erzeugung mit WeasyPrint statt dompdf/FPDI; E-Rechnung im Profil EN 16931 (PHP: BASIC) mit Schema-Prüfung.
* Die Mobile-API prüft die Modulrechte der Gruppen (PHP: jeder angemeldete Benutzer) und verwendet deutsche Feldnamen.
* Der Briefbogen besteht aus frei platzierbaren Bildern und Textblöcken statt einem hochgeladenen Hintergrund-PDF (Konzept aus dem Projekt „rechnung“); Logo und Briefbogen-Upload der Firma entfallen.
* Unterschriften und Briefbogen werden nicht öffentlich ausgeliefert, sondern nur über die Anwendung nach Anmeldung.
