"""Schreibt die Kalender von KYBRO in Kalender auf einem CalDAV-Server (einseitig, KYBRO ist die führende Quelle).

Je Zuordnung wird der Sollzustand aus KYBRO berechnet und mit dem verglichen, was zuletzt geschrieben wurde: neue und
geänderte Termine werden gespeichert, entfernte gelöscht. Termine, die auf dem Server fehlen (dort gelöscht), werden
neu angelegt. Fremde Termine im Zielkalender bleiben unberührt, deshalb sollte der Zielkalender KYBRO allein gehören.
Termine, die älter sind als das Abgleichsfenster, bleiben auf dem Server erhalten.
"""

import hashlib
import logging

from django.utils import timezone

from . import ics, quellen
from .caldav import CalDavClient, CalDavFehler
from .models import CalDavVerbindung, SyncEintrag, Zuordnung

log = logging.getLogger(__name__)
MAX_FEHLERTEXTE = 3


def client_fuer(verbindung: CalDavVerbindung) -> CalDavClient:
    return CalDavClient(verbindung.url, verbindung.benutzer, verbindung.passwort, verbindung.tls_pruefen)


def _datum(wert):
    return wert.date() if hasattr(wert, "date") else wert


def sollzustand(schluessel: str, von, bis) -> dict[str, dict]:
    """``{uid: {"text": ics, "pruefsumme": …, "ende": date}}`` für einen KYBRO-Kalender."""
    ergebnis = {}
    for e in quellen.ereignisse(schluessel, von, bis):
        text = ics.ereignis_text(e)
        ergebnis[e["uid"]] = {
            "text": text, "pruefsumme": hashlib.sha256(text.encode()).hexdigest(), "ende": _datum(e["ende"]),
        }
    return ergebnis


def _zuordnung_abgleichen(client: CalDavClient, z: Zuordnung, von, bis) -> dict:
    zaehler = {"angelegt": 0, "geaendert": 0, "geloescht": 0, "fehler": 0, "meldungen": []}

    def fehler(text):
        zaehler["fehler"] += 1
        if len(zaehler["meldungen"]) < MAX_FEHLERTEXTE:
            zaehler["meldungen"].append(text)

    soll = sollzustand(z.quelle, von, bis) if quellen.quelle(z.quelle) else {}
    bekannt = {e.uid: e for e in z.eintraege.all()}
    auf_server = client.vorhandene(z.ziel_url)  # schlägt bei Verbindungsproblemen fehl und bricht diese Zuordnung ab

    for uid, s in soll.items():
        alt = bekannt.get(uid)
        fehlt = f"{uid}.ics" not in auf_server
        if alt and alt.pruefsumme == s["pruefsumme"] and not fehlt:
            continue
        try:
            client.speichern(z.ziel_url, uid, s["text"])
        except CalDavFehler as ex:
            fehler(f"{uid}: {ex}")
            continue
        zaehler["geaendert" if alt else "angelegt"] += 1
        SyncEintrag.objects.update_or_create(zuordnung=z, uid=uid, defaults={"pruefsumme": s["pruefsumme"], "ende": s["ende"]})

    for uid, alt in bekannt.items():
        if uid in soll or alt.ende < von:
            continue  # noch gültig, bzw. älter als das Fenster: auf dem Server stehen lassen
        try:
            client.loeschen(z.ziel_url, uid)
        except CalDavFehler as ex:
            fehler(f"{uid}: {ex}")
            continue
        alt.delete()
        zaehler["geloescht"] += 1
    return zaehler


def abgleichen(verbindung: CalDavVerbindung | None = None, client: CalDavClient | None = None) -> dict:
    """Gleicht alle Zuordnungen ab. Gibt eine Zusammenfassung zurück (``text`` ist für die Anzeige gedacht)."""
    verbindung = verbindung or CalDavVerbindung.holen()
    summe = {"angelegt": 0, "geaendert": 0, "geloescht": 0, "fehler": 0, "meldungen": []}
    if not verbindung.eingerichtet:
        summe["fehler"] = 1
        summe["meldungen"] = ["Die Verbindung ist nicht vollständig eingerichtet."]
    else:
        client = client or client_fuer(verbindung)
        von, bis = quellen.standardfenster()
        zuordnungen = list(Zuordnung.objects.all())
        if not zuordnungen:
            summe["meldungen"] = ["Es ist noch kein Kalender zugeordnet."]
        for z in zuordnungen:
            try:
                teil = _zuordnung_abgleichen(client, z, von, bis)
            except CalDavFehler as ex:
                summe["fehler"] += 1
                summe["meldungen"].append(f"{z.ziel_name or z.quelle}: {ex}")
                continue
            for schluessel in ("angelegt", "geaendert", "geloescht", "fehler"):
                summe[schluessel] += teil[schluessel]
            summe["meldungen"] += [f"{z.ziel_name or z.quelle}: {m}" for m in teil["meldungen"]]
    summe["text"] = (
        f"{summe['angelegt']} angelegt, {summe['geaendert']} geändert, {summe['geloescht']} gelöscht, {summe['fehler']} Fehler"
        + ("".join(f"\n{m}" for m in summe["meldungen"]) if summe["meldungen"] else "")
    )
    verbindung.zuletzt_abgeglichen = timezone.now()
    verbindung.letzter_status = summe["text"]
    verbindung.save(update_fields=["zuletzt_abgeglichen", "letzter_status"])
    if summe["fehler"]:
        log.warning("[KALENDER] Abgleich mit Fehlern: %s", summe["text"])
    return summe


def zuordnung_entfernen(z: Zuordnung, client: CalDavClient) -> list[str]:
    """Löscht die von KYBRO geschriebenen Termine im Zielkalender und danach die Zuordnung. Gibt Fehlertexte zurück."""
    probleme = []
    for e in z.eintraege.all():
        try:
            client.loeschen(z.ziel_url, e.uid)
        except CalDavFehler as ex:
            probleme.append(f"{e.uid}: {ex}")
            break  # Server nicht erreichbar o. Ä.: nicht jeden Termin einzeln versuchen
    z.delete()
    return probleme
