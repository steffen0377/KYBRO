"""Endpunkte der mobilen API (JSON). Antwortformat: {"success": true, "data": ...} bzw. {"success": false, "error": "..."}."""

import base64
import binascii
import io
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from belege import services
from belege.models import Auftrag, AuftragPosition
from einstellungen.models import Nummernkreis
from einstellungen.services import naechste_belegnummer
from stammdaten.models import Artikel, Kunde

from . import serializers
from .auth import ApiFehler, api_ansicht, erfolg, json_koerper

MAX_UNTERSCHRIFT_BYTES = 1_000_000
CENT = Decimal("0.01")


def _seit(request):
    roh = request.GET.get("since", "").strip()
    if not roh:
        return None
    try:
        wert = datetime.fromisoformat(roh.replace("Z", "+00:00").replace(" ", "+"))
    except ValueError:
        raise ApiFehler("Ungültiger Parameter 'since' (erwartet ISO-8601, z. B. 2026-08-01T00:00:00).", 400)
    return timezone.make_aware(wert) if timezone.is_naive(wert) else wert


def _id(request):
    roh = request.GET.get("id")
    if roh is None:
        return None
    if not roh.isdigit():
        raise ApiFehler("Ungültiger Parameter 'id'.", 400)
    return int(roh)


# ---------------------------------------------------------------------------
# Lesen: Kunden, Artikel
# ---------------------------------------------------------------------------


@api_ansicht(methoden=["GET"], rechte=(("kunden", "lesen"),))
def kunden(request):
    pk = _id(request)
    if pk is not None:
        k = Kunde.objects.prefetch_related("ansprechpartner").filter(pk=pk).first()
        if not k:
            raise ApiFehler("Kunde nicht gefunden.", 404)
        return erfolg(serializers.kunde(k, mit_kontakten=True))
    abfrage = Kunde.objects.all()
    seit = _seit(request)
    abfrage = abfrage.filter(geaendert__gt=seit).order_by("geaendert") if seit else abfrage.order_by("firma", "nachname")
    return erfolg([serializers.kunde(k) for k in abfrage])


@api_ansicht(methoden=["GET"], rechte=(("artikel", "lesen"),))
def artikel_liste(request):
    pk = _id(request)
    if pk is not None:
        a = Artikel.objects.prefetch_related("preisoptionen").filter(pk=pk).first()
        if not a:
            raise ApiFehler("Artikel nicht gefunden.", 404)
        return erfolg(serializers.artikel(a))
    abfrage = Artikel.objects.prefetch_related("preisoptionen")
    seit = _seit(request)
    # Delta-Sync liefert auch inzwischen deaktivierte Artikel, damit die App sie ausblenden kann.
    abfrage = abfrage.filter(geaendert__gt=seit).order_by("geaendert") if seit else abfrage.filter(aktiv=True).order_by("name")
    return erfolg([serializers.artikel(a) for a in abfrage])


# ---------------------------------------------------------------------------
# Aufträge
# ---------------------------------------------------------------------------


def _dezimal(wert, feld, minimum=None, maximum=None, standard=None):
    if wert is None or wert == "":
        if standard is not None:
            return standard
        raise ApiFehler(f"Feld '{feld}' fehlt.", 400)
    try:
        zahl = Decimal(str(wert).replace(",", "."))
    except InvalidOperation:
        raise ApiFehler(f"Feld '{feld}' ist keine Zahl.", 400)
    if not zahl.is_finite() or (minimum is not None and zahl < minimum) or (maximum is not None and zahl > maximum):
        raise ApiFehler(f"Feld '{feld}' hat einen ungültigen Wert.", 400)
    return zahl


def _uuid(wert, feld):
    try:
        return uuid.UUID(str(wert))
    except (ValueError, AttributeError, TypeError):
        raise ApiFehler(f"Feld '{feld}' muss eine UUID sein.", 400)


def _datum(wert, feld):
    try:
        return datetime.strptime(str(wert)[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ApiFehler(f"Feld '{feld}' ist kein Datum (JJJJ-MM-TT).", 400)


def _unterschrift_datei(roh) -> ContentFile:
    """Base64-PNG/JPEG (optional als data:-URI) prüfen und als Datei zurückgeben."""
    text = str(roh)
    if text.startswith("data:"):
        text = text.split(",", 1)[-1]
    try:
        inhalt = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise ApiFehler("Die Unterschrift ist kein gültiges Base64.", 400)
    if len(inhalt) > MAX_UNTERSCHRIFT_BYTES:
        raise ApiFehler("Die Unterschrift ist zu groß (maximal 1 MB).", 400)
    try:
        bild = Image.open(io.BytesIO(inhalt))
        bild.verify()
        endung = {"PNG": "png", "JPEG": "jpg"}[bild.format]
    except (UnidentifiedImageError, KeyError, OSError, SyntaxError):
        raise ApiFehler("Die Unterschrift muss ein PNG- oder JPEG-Bild sein.", 400)
    return ContentFile(inhalt, name=f"{uuid.uuid4().hex}.{endung}")


def _positionen_pruefen(roh, kunde) -> list[dict]:
    if not isinstance(roh, list) or not roh:
        raise ApiFehler("Feld 'positionen' muss mindestens eine Position enthalten.", 400)
    ergebnis = []
    for nr, p in enumerate(roh, start=1):
        if not isinstance(p, dict):
            raise ApiFehler(f"Position {nr} ist ungültig.", 400)
        artikel = None
        if p.get("artikel_id") not in (None, ""):
            artikel = Artikel.objects.filter(pk=p["artikel_id"]).first() if str(p["artikel_id"]).isdigit() else None
            if artikel is None:
                raise ApiFehler(f"Position {nr}: Artikel nicht gefunden.", 404)
        beschreibung = str(p.get("beschreibung") or (artikel.name if artikel else "")).strip()
        if not beschreibung:
            raise ApiFehler(f"Position {nr}: Beschreibung fehlt.", 400)
        steuer = Decimal("0.00") if kunde.steuerbefreit else _dezimal(
            p.get("steuersatz"), "steuersatz", Decimal(0), Decimal(100), artikel.steuersatz if artikel else Decimal("19.00"))
        ergebnis.append({
            "client_uuid": _uuid(p.get("client_uuid"), f"positionen[{nr - 1}].client_uuid") if p.get("client_uuid") else None,
            "artikel": artikel, "beschreibung": beschreibung[:500],
            "position": int(p.get("position") or nr),
            "menge": _dezimal(p.get("menge"), "menge", Decimal("0.01"), Decimal("99999999"), Decimal(1)),
            "einzelpreis": _dezimal(p.get("einzelpreis"), "einzelpreis", Decimal(0), Decimal("99999999"),
                                    artikel.verkaufspreis if artikel else None),
            "rabatt": _dezimal(p.get("rabatt"), "rabatt", Decimal(0), Decimal(100), Decimal(0)),
            "steuersatz": steuer,
        })
    return ergebnis


def _position_speichern(auftrag, d):
    artikel = d["artikel"]
    felder = dict(
        position=d["position"], artikel=artikel, artikelnummer=artikel.artikelnummer if artikel else "",
        beschreibung=d["beschreibung"], einheit=artikel.einheit if artikel else "", menge=d["menge"],
        einzelpreis=d["einzelpreis"], rabatt=d["rabatt"], steuersatz=d["steuersatz"],
    )
    vorhanden = AuftragPosition.objects.filter(client_uuid=d["client_uuid"]).first() if d["client_uuid"] else None
    if vorhanden:
        if vorhanden.auftrag_id != auftrag.pk:
            raise ApiFehler("Eine Position mit dieser client_uuid gehört zu einem anderen Auftrag.", 409)
        for k, v in felder.items():
            setattr(vorhanden, k, v)
        vorhanden.save()
    else:
        AuftragPosition.objects.create(auftrag=auftrag, client_uuid=d["client_uuid"], **felder)


@api_ansicht(
    methoden={"GET": (("auftraege", "lesen"),), "POST": (("auftraege", "schreiben"),)},
)
def auftraege(request):
    if request.method == "GET":
        return _auftraege_lesen(request)
    return _auftrag_synchronisieren(request)


def _auftraege_lesen(request):
    basis = Auftrag.objects.prefetch_related("positionen")
    pk = _id(request)
    if pk is not None:
        a = basis.filter(pk=pk).first()
        if not a:
            raise ApiFehler("Auftrag nicht gefunden.", 404)
        return erfolg(serializers.auftrag(a))
    seit = _seit(request)
    abfrage = basis.filter(geaendert__gt=seit).order_by("geaendert") if seit else basis.order_by("-datum", "-pk")
    return erfolg([serializers.auftrag(a) for a in abfrage])


@transaction.atomic
def _auftrag_synchronisieren(request):
    """Legt einen Auftrag an oder aktualisiert ihn; idempotent über ``client_uuid``."""
    daten = json_koerper(request)
    if not daten.get("client_uuid"):
        raise ApiFehler("client_uuid ist erforderlich (von der App vergeben, für idempotenten Sync).", 400)
    client_uuid = _uuid(daten["client_uuid"], "client_uuid")
    for pflicht in ("kunde_id", "datum", "positionen"):
        if pflicht not in daten:
            raise ApiFehler(f"Feld '{pflicht}' fehlt.", 400)
    status = daten.get("status") or Auftrag.Status.OFFEN
    if status not in Auftrag.Status.values:
        raise ApiFehler("Unbekannter Status.", 400)
    # Unterschrift prüfen, bevor etwas gespeichert wird
    unterschrift = _unterschrift_datei(daten["unterschrift"]) if daten.get("unterschrift") else None

    auftrag = Auftrag.objects.select_for_update().filter(client_uuid=client_uuid).first()
    if auftrag is not None and auftrag.abgerechnet:
        # Abgerechnete Aufträge bleiben unverändert; ein erneuter Sync liefert nur den Stand zurück.
        return erfolg(serializers.auftrag(Auftrag.objects.prefetch_related("positionen").get(pk=auftrag.pk)))

    kunde_roh = daten["kunde_id"]
    kunde = Kunde.objects.filter(pk=kunde_roh).first() if str(kunde_roh).isdigit() else None
    if kunde is None:
        raise ApiFehler("Kunde nicht gefunden.", 404)
    positionen = _positionen_pruefen(daten["positionen"], kunde)
    datum = _datum(daten["datum"], "datum")

    neu = auftrag is None
    if neu:
        auftrag = Auftrag(
            nummer=naechste_belegnummer(Nummernkreis.Art.AUFTRAG, datum), client_uuid=client_uuid,
            kunde=kunde, datum=datum, erstellt_von=request.user,
        )
    elif auftrag.kunde_id != kunde.pk:
        raise ApiFehler("Der Kunde eines bestehenden Auftrags kann nicht geändert werden.", 409)
    auftrag.datum = datum
    auftrag.notizen = str(daten.get("notizen") or "")
    if unterschrift is not None:
        auftrag.unterschrift = unterschrift
        auftrag.unterschrieben_von = str(daten.get("unterschrieben_von") or "")[:150]
        auftrag.unterschrieben_am = timezone.now()
        if daten.get("unterschrieben_am"):
            try:
                zeitpunkt = datetime.fromisoformat(str(daten["unterschrieben_am"]).replace("Z", "+00:00"))
                auftrag.unterschrieben_am = timezone.make_aware(zeitpunkt) if timezone.is_naive(zeitpunkt) else zeitpunkt
            except ValueError:
                raise ApiFehler("Feld 'unterschrieben_am' ist kein Zeitpunkt (ISO-8601).", 400)
        # Wer unterschreibt, hat den Auftrag bestätigt; die App muss das nicht extra melden.
        if status in (Auftrag.Status.OFFEN, Auftrag.Status.IN_BEARBEITUNG):
            status = Auftrag.Status.UNTERSCHRIEBEN
    auftrag.status = status
    auftrag.save()
    for d in positionen:
        _position_speichern(auftrag, d)
    services.positionen_nummerieren(auftrag)
    auftrag.summen_neu_berechnen()
    auftrag.save(update_fields=["geaendert"])
    auftrag = Auftrag.objects.prefetch_related("positionen").get(pk=auftrag.pk)
    return erfolg(serializers.auftrag(auftrag), 201 if neu else 200)


@api_ansicht(methoden=["POST"], rechte=(("auftraege", "lesen"), ("rechnungen", "schreiben")))
def auftrag_zu_rechnung(request):
    """POST {"auftrag_id": 1} -> Rechnung (Entwurf). Ein zweiter Aufruf liefert die vorhandene Rechnung."""
    daten = json_koerper(request)
    roh = daten.get("auftrag_id")
    if not str(roh).isdigit():
        raise ApiFehler("auftrag_id ist erforderlich.", 400)
    with transaction.atomic():
        auftrag = Auftrag.objects.select_for_update().filter(pk=int(roh)).first()
        if auftrag is None:
            raise ApiFehler("Auftrag nicht gefunden.", 404)
        if auftrag.status not in (Auftrag.Status.UNTERSCHRIEBEN, Auftrag.Status.ABGESCHLOSSEN):
            raise ApiFehler("Nur unterschriebene oder abgeschlossene Aufträge können in eine Rechnung überführt werden.", 409)
        vorhanden = auftrag.rechnungen.exclude(status="storniert").order_by("pk").first()
        if vorhanden:
            return erfolg(serializers.rechnung(vorhanden))
        try:
            rechnung = services.rechnung_aus_auftrag(auftrag, request.user)
        except services.BelegFehler as fehler:
            raise ApiFehler(str(fehler), 409)
    return erfolg(serializers.rechnung(rechnung), 201)
