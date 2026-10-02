"""Ansichten für Angebote, Aufträge und Rechnungen."""

from datetime import timedelta

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from accounts.mixins import ModulRechtMixin
from core.views import LiveSucheMixin
from einstellungen.models import Firma, Nummernkreis
from einstellungen.services import naechste_belegnummer
from lager.models import Seriennummer
from stammdaten.models import Artikel, Sonderpreis

from . import services
from .forms import (
    AngebotForm,
    AngebotPositionenFormSet,
    RechnungForm,
    RechnungPositionenFormSet,
    StatusForm,
)
from .models import Angebot, Auftrag, Rechnung
from .services import BelegFehler

# ---------------------------------------------------------------------------
# Gemeinsame Bausteine
# ---------------------------------------------------------------------------


def status_badge_klasse(status: str) -> str:
    return {
        "entwurf": "secondary", "versendet": "info", "angenommen": "success", "abgelehnt": "dark",
        "offen": "secondary", "in_bearbeitung": "info", "unterschrieben": "primary",
        "abgeschlossen": "success", "storniert": "dark", "bezahlt": "success", "ueberfaellig": "danger",
    }.get(status, "secondary")


class BelegListeView(ModulRechtMixin, LiveSucheMixin, ListView):
    """Liste mit Suche (Nummer, Kunde) und Statusfilter."""

    context_object_name = "belege"
    fragment_template_name = "belege/_beleg_tabelle.html"
    template_name = "belege/beleg_liste.html"
    titel = ""
    url_praefix = ""  # z. B. "angebote"
    neu_url_name: str | None = None
    zeige_loeschen = True

    def get_queryset(self):
        abfrage = self.model.objects.select_related("kunde")
        suche = self.request.GET.get("q", "").strip()
        if suche:
            abfrage = abfrage.filter(
                Q(nummer__icontains=suche)
                | Q(kunde__firma__icontains=suche)
                | Q(kunde__nachname__icontains=suche)
                | Q(kunde__kundennummer__icontains=suche)
            )
        status = self.request.GET.get("status", "")
        if status in self.model.Status.values:
            abfrage = abfrage.filter(status=status)
        return abfrage

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext.update(
            seitentitel=self.titel,
            titel=self.titel,
            suche=self.request.GET.get("q", ""),
            status_filter=self.request.GET.get("status", ""),
            status_auswahl=self.model.Status.choices,
            url_ansehen=f"belege:{self.url_praefix}_ansehen",
            url_loeschen=f"belege:{self.url_praefix}_loeschen",
            url_neu=f"belege:{self.neu_url_name}" if self.neu_url_name else "",
            modul=self.modul,
            darf_schreiben=self.request.user.hat_modulrecht(self.modul, "schreiben"),
        )
        for beleg in kontext["belege"]:
            beleg.badge = status_badge_klasse(beleg.status)
        return kontext


class BelegDetailView(ModulRechtMixin, DetailView):
    context_object_name = "beleg"
    positionen_name = "positionen"

    def get_queryset(self):
        return self.model.objects.select_related("kunde", "erstellt_von")

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        beleg = self.object
        summen = beleg.summen()
        kontext.update(
            seitentitel=f"{self.model._meta.verbose_name} {beleg.nummer}",
            positionen=beleg.positionen.select_related("artikel"),
            summen=summen,
            badge=status_badge_klasse(beleg.status),
            status_form=StatusForm(self.status_auswahl(beleg), initial={"status": beleg.status}),
            modul=self.modul,
            darf_schreiben=self.request.user.hat_modulrecht(self.modul, "schreiben"),
            darf_rechnung_schreiben=self.request.user.hat_modulrecht("rechnungen", "schreiben"),
        )
        return kontext

    def status_auswahl(self, beleg):
        return self.model.Status.choices


def _artikel_fuer_formular() -> list[dict]:
    """Artikeldaten für die Auswahl in Positionsformularen (als JSON an das Template)."""
    artikel = Artikel.objects.filter(aktiv=True).prefetch_related("preisoptionen").order_by("name")
    return [
        {
            "id": a.pk,
            "name": a.name,
            "preis": float(a.verkaufspreis),
            "steuersatz": float(a.steuersatz),
            "optionen": [
                {"id": o.pk, "abrechnung": o.abrechnung, "preis": float(o.preis)}
                for o in a.preisoptionen.all() if o.aktiv
            ],
        }
        for a in artikel
    ]


def _sonderpreise_fuer_formular() -> dict:
    ergebnis: dict = {}
    for sp in Sonderpreis.objects.filter(aktiv=True):
        ergebnis.setdefault(str(sp.kunde_id), {})[str(sp.artikel_id)] = {"art": sp.art, "wert": float(sp.wert)}
    return ergebnis


class BelegFormularView(ModulRechtMixin, TemplateView):
    """Gemeinsame Logik für Anlegen und Bearbeiten von Angebot und Rechnung."""

    template_name = "belege/beleg_form.html"
    modell = None
    form_klasse = None
    formset_klasse = None
    url_praefix = ""
    neu = True

    def get_aktion(self):
        return "schreiben"  # auch das Formular selbst (GET) ist eine Schreibfunktion

    def get_beleg(self):
        return None if self.neu else get_object_or_404(self.modell, pk=self.kwargs["pk"])

    def pruefe_bearbeitbar(self, beleg) -> str | None:
        """Gibt eine Fehlermeldung zurück, wenn der Beleg nicht bearbeitet werden darf."""
        return None

    def anfangswerte(self) -> dict:
        return {}

    def _gesperrt(self, request):
        """Weiterleitung mit Meldung, falls der Beleg nicht (mehr) bearbeitet werden darf."""
        self.beleg = self.get_beleg()
        if self.beleg is not None:
            fehler = self.pruefe_bearbeitbar(self.beleg)
            if fehler:
                messages.error(request, fehler)
                return redirect(f"belege:{self.url_praefix}_ansehen", pk=self.beleg.pk)
        return None

    def get(self, request, *args, **kwargs):
        return self._gesperrt(request) or super().get(request, *args, **kwargs)

    def forms(self):
        daten = self.request.POST if self.request.method == "POST" else None
        form = self.form_klasse(daten, instance=self.beleg, initial=self.anfangswerte() if self.neu else None)
        formset = self.formset_klasse(daten, instance=self.beleg, prefix="pos")
        return form, formset

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        form, formset = kwargs.get("form"), kwargs.get("formset")
        if form is None:
            form, formset = self.forms()
        kontext.update(
            form=form, formset=formset, beleg=self.beleg, neu=self.neu,
            seitentitel=self.titel(), url_abbrechen=self.url_abbrechen(),
            artikel_daten=_artikel_fuer_formular(),
            sonderpreise=_sonderpreise_fuer_formular(),
            standard_steuer=float(Firma.holen().standard_steuersatz),
        )
        return kontext

    def post(self, request, *args, **kwargs):
        gesperrt = self._gesperrt(request)
        if gesperrt:
            return gesperrt
        form, formset = self.forms()
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    beleg = self.speichern(form, formset)
            except BelegFehler as fehler:
                messages.error(request, str(fehler))
            else:
                return self.nach_speichern(beleg)
        return self.render_to_response(self.get_context_data(form=form, formset=formset))

    def speichern(self, form, formset):
        raise NotImplementedError

    def nach_speichern(self, beleg):
        raise NotImplementedError


class AngebotFormularView(BelegFormularView):
    modul = "angebote"
    modell = Angebot
    form_klasse = AngebotForm
    formset_klasse = AngebotPositionenFormSet
    url_praefix = "angebote"

    def titel(self):
        return "Neues Angebot" if self.neu else f"Angebot {self.beleg.nummer} bearbeiten"

    def url_abbrechen(self):
        return reverse("belege:angebote_liste") if self.neu else reverse("belege:angebote_ansehen", args=[self.beleg.pk])

    def anfangswerte(self):
        return {"datum": timezone.localdate(), "gueltig_bis": timezone.localdate() + timedelta(days=30)}

    def pruefe_bearbeitbar(self, beleg):
        if not beleg.bearbeitbar:
            return "Aus diesem Angebot ist bereits ein Auftrag entstanden und es kann nicht mehr geändert werden."

    def speichern(self, form, formset):
        angebot = form.save(commit=False)
        if self.neu:
            angebot.nummer = naechste_belegnummer(Nummernkreis.Art.ANGEBOT, angebot.datum)
            angebot.erstellt_von = self.request.user
        angebot.save()
        formset.instance = angebot
        formset.speichern(angebot.kunde)
        services.positionen_nummerieren(angebot)
        angebot.summen_neu_berechnen()
        return angebot

    def nach_speichern(self, angebot):
        messages.success(self.request, "Angebot gespeichert.")
        return redirect("belege:angebote_ansehen", pk=angebot.pk)


class RechnungFormularView(BelegFormularView):
    modul = "rechnungen"
    modell = Rechnung
    form_klasse = RechnungForm
    formset_klasse = RechnungPositionenFormSet
    url_praefix = "rechnungen"

    def titel(self):
        return "Neue Rechnung" if self.neu else f"Rechnung {self.beleg.nummer} bearbeiten"

    def url_abbrechen(self):
        return reverse("belege:rechnungen_liste") if self.neu else reverse("belege:rechnungen_ansehen", args=[self.beleg.pk])

    def anfangswerte(self):
        heute = timezone.localdate()
        return {"datum": heute, "faellig_am": services.faelligkeit(heute)}

    def pruefe_bearbeitbar(self, beleg):
        if not beleg.ist_entwurf:
            return "Nur Entwürfe können bearbeitet werden."

    def speichern(self, form, formset):
        rechnung = form.save(commit=False)
        if self.neu:
            rechnung.nummer = naechste_belegnummer(Nummernkreis.Art.RECHNUNG, rechnung.datum)
            rechnung.erstellt_von = self.request.user
        rechnung.save()
        formset.instance = rechnung
        formset.speichern(rechnung.kunde)
        services.rechnung_nach_bearbeiten(rechnung, self.neu, self.request.user)
        return rechnung

    def nach_speichern(self, rechnung):
        offen = services.offene_seriennummern(rechnung)
        if offen:
            messages.success(
                self.request, "Rechnung gespeichert. Bitte jetzt die Seriennummern der verkauften Geräte zuordnen."
            )
            return redirect("belege:rechnungen_seriennummern", pk=rechnung.pk)
        if self.neu:
            messages.success(self.request, "Rechnung gespeichert. Lagerbestand wurde reduziert.")
        else:
            messages.success(self.request, "Rechnung gespeichert. Die Lagerbuchung wurde an die Änderungen angepasst.")
        return redirect("belege:rechnungen_ansehen", pk=rechnung.pk)


# ---------------------------------------------------------------------------
# Angebote
# ---------------------------------------------------------------------------


class AngebotListeView(BelegListeView):
    modul = "angebote"
    model = Angebot
    titel = "Angebote"
    url_praefix = "angebote"
    neu_url_name = "angebote_neu"


class AngebotDetailView(BelegDetailView):
    modul = "angebote"
    model = Angebot
    template_name = "belege/angebot_detail.html"

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["auftrag"] = Auftrag.objects.filter(angebot=self.object).first()
        kontext["darf_artikel_schreiben"] = self.request.user.hat_modulrecht("artikel", "schreiben")
        return kontext


class AngebotStatusView(ModulRechtMixin, View):
    modul = "angebote"
    http_method_names = ["post"]

    def post(self, request, pk):
        angebot = get_object_or_404(Angebot, pk=pk)
        try:
            auftrag = services.angebot_status_aendern(angebot, request.POST.get("status", ""), request.user)
        except BelegFehler as fehler:
            messages.error(request, str(fehler))
        else:
            if auftrag:
                messages.success(request, f"Status aktualisiert. Auftrag {auftrag.nummer} wurde erstellt.")
            else:
                messages.success(request, "Status aktualisiert.")
        return redirect("belege:angebote_ansehen", pk=pk)


class AngebotZuAuftragView(ModulRechtMixin, View):
    modul = "angebote"
    http_method_names = ["post"]

    def post(self, request, pk):
        angebot = get_object_or_404(Angebot, pk=pk)
        auftrag, neu = services.auftrag_aus_angebot(angebot, request.user)
        if neu:
            messages.success(request, f"Auftrag {auftrag.nummer} wurde erstellt.")
        else:
            messages.info(request, f"Zu diesem Angebot existiert bereits Auftrag {auftrag.nummer}.")
        return redirect("belege:auftraege_ansehen", pk=auftrag.pk)


def _nach_rechnung_erstellt(request, rechnung: Rechnung, auftrag: Auftrag | None = None):
    teile = []
    if auftrag is not None:
        teile.append(f"Auftrag {auftrag.nummer} und ")
    teile.append(f"Rechnung {rechnung.nummer}")
    if services.offene_seriennummern(rechnung):
        messages.success(
            request, "".join(teile) + " wurden erstellt. Bitte jetzt die Seriennummern der verkauften Geräte zuordnen."
        )
        return redirect("belege:rechnungen_seriennummern", pk=rechnung.pk)
    messages.success(request, "".join(teile) + " wurde(n) erstellt (Lagerbestand wurde reduziert).")
    return redirect("belege:rechnungen_ansehen", pk=rechnung.pk)


class AngebotZuRechnungView(ModulRechtMixin, View):
    """Schnellweg Angebot -> Auftrag -> Rechnung. Braucht Schreibrecht auf Rechnungen."""

    modul = "angebote"
    http_method_names = ["post"]

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.hat_modulrecht("rechnungen", "schreiben"):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Für diese Funktion wird das Recht „Rechnungen: schreiben“ benötigt.")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        angebot = get_object_or_404(Angebot, pk=pk)
        try:
            auftrag, rechnung = services.rechnung_aus_angebot(angebot, request.user)
        except BelegFehler as fehler:
            messages.error(request, str(fehler))
            return redirect("belege:angebote_ansehen", pk=pk)
        return _nach_rechnung_erstellt(request, rechnung, auftrag)


class AngebotLoeschenView(ModulRechtMixin, View):
    modul = "angebote"
    http_method_names = ["post"]

    def post(self, request, pk):
        angebot = get_object_or_404(Angebot, pk=pk)
        if not angebot.bearbeitbar:
            messages.error(request, "Aus diesem Angebot ist bereits ein Auftrag entstanden und es kann nicht gelöscht werden.")
            return redirect("belege:angebote_ansehen", pk=pk)
        angebot.delete()
        messages.success(request, "Angebot gelöscht.")
        return redirect("belege:angebote_liste")


# ---------------------------------------------------------------------------
# Aufträge
# ---------------------------------------------------------------------------


class AuftragListeView(BelegListeView):
    modul = "auftraege"
    model = Auftrag
    titel = "Aufträge"
    url_praefix = "auftraege"


class AuftragDetailView(BelegDetailView):
    modul = "auftraege"
    model = Auftrag
    template_name = "belege/auftrag_detail.html"

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["rechnungen"] = self.object.rechnungen.all()
        return kontext


class AuftragStatusView(ModulRechtMixin, View):
    modul = "auftraege"
    http_method_names = ["post"]

    def post(self, request, pk):
        auftrag = get_object_or_404(Auftrag, pk=pk)
        status = request.POST.get("status", "")
        if status not in Auftrag.Status.values:
            messages.error(request, "Unbekannter Status.")
        else:
            auftrag.status = status
            auftrag.save(update_fields=["status"])
            messages.success(request, "Status aktualisiert.")
        return redirect("belege:auftraege_ansehen", pk=pk)


class AuftragZuRechnungView(ModulRechtMixin, View):
    modul = "auftraege"
    http_method_names = ["post"]

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.hat_modulrecht("rechnungen", "schreiben"):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Für diese Funktion wird das Recht „Rechnungen: schreiben“ benötigt.")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk):
        auftrag = get_object_or_404(Auftrag, pk=pk)
        try:
            rechnung = services.rechnung_aus_auftrag(auftrag, request.user)
        except BelegFehler as fehler:
            messages.error(request, str(fehler))
            return redirect("belege:auftraege_ansehen", pk=pk)
        return _nach_rechnung_erstellt(request, rechnung)


class AuftragLoeschenView(ModulRechtMixin, View):
    modul = "auftraege"
    http_method_names = ["post"]

    def post(self, request, pk):
        auftrag = get_object_or_404(Auftrag, pk=pk)
        if auftrag.abgerechnet:
            messages.error(request, "Der Auftrag wurde bereits abgerechnet und kann nicht gelöscht werden.")
            return redirect("belege:auftraege_ansehen", pk=pk)
        auftrag.delete()
        messages.success(request, "Auftrag gelöscht.")
        return redirect("belege:auftraege_liste")


# ---------------------------------------------------------------------------
# Rechnungen
# ---------------------------------------------------------------------------


class RechnungListeView(BelegListeView):
    modul = "rechnungen"
    model = Rechnung
    titel = "Rechnungen"
    url_praefix = "rechnungen"
    neu_url_name = "rechnungen_neu"


class RechnungDetailView(BelegDetailView):
    modul = "rechnungen"
    model = Rechnung
    template_name = "belege/rechnung_detail.html"

    def status_auswahl(self, beleg):
        if beleg.ist_entwurf:
            return self.model.Status.choices
        # Eine ausgestellte Rechnung geht nicht zurück in den Entwurf.
        return [c for c in self.model.Status.choices if c[0] != Rechnung.Status.ENTWURF]

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        rechnung = self.object
        seriennummern: dict[int, list[str]] = {}
        for serie in Seriennummer.objects.filter(rechnung=rechnung).order_by("nummer"):
            seriennummern.setdefault(serie.artikel_id, []).append(serie.nummer)
        for position in kontext["positionen"]:
            position.seriennummern_text = ", ".join(seriennummern.get(position.artikel_id, []))
        kontext["offene_seriennummern"] = services.offene_seriennummern(rechnung)
        return kontext


class RechnungStatusView(ModulRechtMixin, View):
    modul = "rechnungen"
    http_method_names = ["post"]

    def post(self, request, pk):
        rechnung = get_object_or_404(Rechnung, pk=pk)
        try:
            services.rechnung_status_aendern(rechnung, request.POST.get("status", ""), request.user)
        except BelegFehler as fehler:
            messages.error(request, str(fehler))
        else:
            messages.success(request, "Status aktualisiert.")
        return redirect("belege:rechnungen_ansehen", pk=pk)


class RechnungLoeschenView(ModulRechtMixin, View):
    modul = "rechnungen"
    http_method_names = ["post"]

    def post(self, request, pk):
        rechnung = get_object_or_404(Rechnung, pk=pk)
        try:
            services.rechnung_loeschen(rechnung, request.user)
        except BelegFehler as fehler:
            messages.error(request, str(fehler))
            return redirect("belege:rechnungen_ansehen", pk=pk)
        messages.success(request, "Rechnung gelöscht. Lagerbuchungen wurden zurückgenommen.")
        return redirect("belege:rechnungen_liste")


class RechnungSeriennummernView(ModulRechtMixin, TemplateView):
    """Ordnet den verkauften Seriennummernartikeln einer Rechnung Seriennummern zu."""

    modul = "rechnungen"
    template_name = "belege/rechnung_seriennummern.html"

    def get_aktion(self):
        # Das Anzeigen der Zuordnung ändert nichts; gespeichert wird per POST.
        return super().get_aktion()

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        rechnung = get_object_or_404(Rechnung, pk=self.kwargs["pk"])
        offen = services.offene_seriennummern(rechnung)
        for eintrag in offen:
            eintrag["verfuegbar"] = list(
                Seriennummer.objects.filter(artikel=eintrag["artikel"], status=Seriennummer.Status.LAGER).order_by("erstellt")
            )
            eintrag["zu_wenig"] = len(eintrag["verfuegbar"]) < eintrag["offen"]
        kontext.update(seitentitel=f"Seriennummern zuordnen – Rechnung {rechnung.nummer}", rechnung=rechnung, offen=offen)
        return kontext

    def post(self, request, pk):
        rechnung = get_object_or_404(Rechnung, pk=pk)
        auswahl = {}
        for schluessel in request.POST:
            if schluessel.startswith("serien_") and schluessel[7:].isdigit():
                ids = [int(i) for i in request.POST.getlist(schluessel) if i.isdigit()]
                auswahl[int(schluessel[7:])] = ids
        try:
            offen = services.seriennummern_zuordnen(rechnung, auswahl, request.user)
        except BelegFehler as fehler:
            messages.error(request, str(fehler))
            return redirect("belege:rechnungen_seriennummern", pk=pk)
        if offen:
            messages.error(
                request,
                "Es fehlen noch Seriennummern für: "
                + ", ".join(f"{e['artikel'].name} ({e['offen']}x)" for e in offen),
            )
            return redirect("belege:rechnungen_seriennummern", pk=pk)
        messages.success(request, "Seriennummern zugeordnet, Lagerbestand aktualisiert.")
        return redirect("belege:rechnungen_ansehen", pk=pk)
