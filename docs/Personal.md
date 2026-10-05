# Personalverwaltung

Menü **Personal** (Recht „Personal“ je Gruppe, lesen bzw. schreiben; Gruppen und Rechte entsprechend ergänzen).

* **Mitarbeiter** sind eigenständige Datensätze, unabhängig von LDAP oder lokalen Benutzern. Optional wird ein Mitarbeiter
  mit genau einem vorhandenen Login verknüpft. In der Mitarbeiterliste lassen sich Logins ohne Mitarbeiter mit einem Klick
  als Mitarbeiter übernehmen (Name und E-Mail werden vorbelegt).
* **Verträge** haben einen Gültigkeitszeitraum (Historie): Beschäftigungsart, Wochenstunden, Arbeitstage, Urlaubstage pro Jahr,
  Probezeit, Befristung, Kündigungsfrist. Bei Änderungen (z. B. mehr Urlaub) wird ein neuer Stand angelegt; Zeiträume dürfen
  sich nicht überschneiden. Eintritts- und Austrittsdatum stehen am Mitarbeiter.
* **Urlaub:** Anspruch = Urlaubstage des Vertrags am 1. Januar, bei Eintritt oder Austritt im Jahr anteilig (1/12 je Monat, auf halbe
  Tage gerundet). Je Jahr kann der Anspruch manuell überschrieben und ein Übertrag erfasst werden. Gezählt werden nur Arbeitstage
  laut Vertrag. Gesetzliche Feiertage des eingestellten Bundeslands kosten keinen Urlaub, ebenso eigene Feiertage; halbe Tage (standardmäßig 24.12. und 31.12.) kosten 0,5 Urlaubstage (siehe Einstellungen). Anträge: beantragt, genehmigt, abgelehnt,
  storniert. Wer Urlaub einträgt, genehmigt ihn zugleich.
* **Anwesenheit:** Tagesstatus (anwesend, Homeoffice, Dienstreise, krank, Sonderurlaub, Freizeitausgleich, Berufsschule, Schulung) mit optionalen Zeiten;
  ein Zeitraum lässt sich auf einmal eintragen (nur Arbeitstage). Urlaub kommt aus den Urlaubsanträgen und wird in der
  Monatsübersicht automatisch angezeigt.
* **Meine Zeiten:** Benutzer mit verknüpftem Mitarbeiter sehen ohne Personal-Recht ihre eigenen Zeiten und ihren Resturlaub,
  tragen eigene Anwesenheit ein und beantragen Urlaub (offene Anträge können sie zurückziehen).
* Personaldaten bleiben beim Wechsel in den Live-Betrieb erhalten.

## Einstellungen › Personal (nur Administratoren)

* **Bundesland:** bestimmt die gesetzlichen Feiertage (ohne Auswahl gibt es keine). Die Feiertage werden berechnet, es ist kein Zusatzpaket nötig. Rechts auf der Seite steht die Vorschau je Jahr.
* **Sondertage:** eigene Feiertage (Urlaubsanteil 0, z. B. Brückentage oder Betriebsferien) und halbe Tage (0,5 Urlaubstage), jährlich oder nur in einem bestimmten Jahr. Ein Sondertag überschreibt einen gesetzlichen Feiertag am selben Datum. Standardmäßig sind 24.12. und 31.12. als halbe Tage angelegt; sie lassen sich ändern oder löschen.
* Feiertage erscheinen in der Anwesenheitsübersicht als „F“; bei Zeiträumen werden sie nicht eingetragen.
