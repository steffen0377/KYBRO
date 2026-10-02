"""Ansichten für Kategorien, Artikel, Kunden und Lieferanten."""

from decimal import Decimal

from django.apps import apps
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from accounts.mixins import ModulRechtMixin
from core.views import LiveSucheMixin
from lager.services import bestand_aendern

from .forms import (
    AnsprechpartnerFormSet,
    ArtikelForm,
    KategorieForm,
    KundeForm,
    LieferantForm,
    LieferantenFormSet,
    PreisoptionFormSet,
    SonderpreisFormSet,
)
from .models import Artikel, Kategorie, Kunde, Lieferant

# ---------------------------------------------------------------------------
# Kategorien
# ---------------------------------------------------------------------------


def kategorie_baum() -> list[dict]:
    """Alle Kategorien als flache Liste in Baumreihenfolge mit Einrückungstiefe."""
    kategorien = list(Kategorie.objects.annotate(anzahl_artikel=Count("artikel")).order_by("name"))
    kinder: dict[int | None, list[Kategorie]] = {}
    for kategorie in kategorien:
        kinder.setdefault(kategorie.uebergeordnet_id, []).append(kategorie)
    ergebnis: list[dict] = []

    def anhaengen(eltern_id, tiefe):
        for kategorie in kinder.get(eltern_id, []):
            ergebnis.append({"kategorie": kategorie, "tiefe": tiefe})
            anhaengen(kategorie.pk, tiefe + 1)

    anhaengen(None, 0)
    return ergebnis


class KategorieListView(ModulRechtMixin, ListView):
    modul = "kategorien"
    model = Kategorie
    template_name = "stammdaten/kategorie_liste.html"
    extra_context = {"seitentitel": "Kategorien"}

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["zeilen"] = kategorie_baum()
        return kontext


class KategorieFormMixin(ModulRechtMixin):
    modul = "kategorien"
    model = Kategorie
    form_class = KategorieForm
    template_name = "stammdaten/kategorie_form.html"
    success_url = reverse_lazy("stammdaten:kategorien_liste")


class KategorieCreateView(KategorieFormMixin, CreateView):
    extra_context = {"seitentitel": "Neue Kategorie"}

    def form_valid(self, form):
        messages.success(self.request, "Kategorie angelegt.")
        return super().form_valid(form)


class KategorieUpdateView(KategorieFormMixin, UpdateView):
    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["seitentitel"] = self.object.name
        return kontext

    def form_valid(self, form):
        messages.success(self.request, "Kategorie aktualisiert.")
        return super().form_valid(form)


class KategorieLoeschenView(ModulRechtMixin, View):
    modul = "kategorien"
    http_method_names = ["post"]

    def post(self, request, pk):
        get_object_or_404(Kategorie, pk=pk).delete()
        messages.success(
            request,
            "Kategorie gelöscht. Unterkategorien wurden zu Hauptkategorien, "
            "Artikelzuordnungen wurden entfernt.",
        )
        return redirect("stammdaten:kategorien_liste")


# ---------------------------------------------------------------------------
# Artikel
# ---------------------------------------------------------------------------

ARTIKEL_SORTIERUNG = {"artikelnummer": "artikelnummer", "name": "name"}


class ArtikelListView(ModulRechtMixin, LiveSucheMixin, ListView):
    modul = "artikel"
    model = Artikel
    template_name = "stammdaten/artikel_liste.html"
    fragment_template_name = "stammdaten/_artikel_tabelle.html"
    context_object_name = "artikel"

    def get_queryset(self):
        abfrage = Artikel.objects.prefetch_related("kategorien")
        suche = self.request.GET.get("q", "").strip()
        if suche:
            abfrage = abfrage.filter(
                Q(name__icontains=suche)
                | Q(artikelnummer__icontains=suche)
                | Q(ean__icontains=suche)
                | Q(han__icontains=suche)
            )
        kategorie = self.request.GET.get("kategorie", "")
        if kategorie.isdigit():
            abfrage = abfrage.filter(kategorien__pk=int(kategorie))
        sortierung = self.request.GET.get("sort", "")
        if sortierung in ARTIKEL_SORTIERUNG:
            richtung = "-" if self.request.GET.get("dir") == "desc" else ""
            return abfrage.order_by(richtung + ARTIKEL_SORTIERUNG[sortierung])
        return abfrage.order_by("-aktiv", "name")

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        sortierung = self.request.GET.get("sort", "")
        if sortierung not in ARTIKEL_SORTIERUNG:
            sortierung = ""
        richtung = "desc" if self.request.GET.get("dir") == "desc" else "asc"
        kategorie_id = self.request.GET.get("kategorie", "")
        kategorie = Kategorie.objects.filter(pk=kategorie_id).first() if kategorie_id.isdigit() else None
        kontext.update(
            seitentitel="Artikel",
            suche=self.request.GET.get("q", ""),
            sortierung=sortierung,
            richtung=richtung,
            gewaehlte_kategorie=kategorie,
            # Die Richtung, die ein Klick auf die Spaltenüberschrift einstellt.
            naechste_richtung={
                spalte: "desc" if sortierung == spalte and richtung == "asc" else "asc"
                for spalte in ARTIKEL_SORTIERUNG
            },
        )
        return kontext


class ArtikelFormularMixin(ModulRechtMixin):
    """Artikelformular mit den Registerkarten Lieferanten, Sonderpreise, Abo-Preise."""

    modul = "artikel"
    model = Artikel
    form_class = ArtikelForm
    template_name = "stammdaten/artikel_form.html"
    success_url = reverse_lazy("stammdaten:artikel_liste")

    def formsets(self):
        daten = self.request.POST if self.request.method == "POST" else None
        instanz = self.object
        return {
            "lieferanten": LieferantenFormSet(daten, instance=instanz, prefix="lief"),
            "sonderpreise": SonderpreisFormSet(daten, instance=instanz, prefix="sonder"),
            "preisoptionen": PreisoptionFormSet(daten, instance=instanz, prefix="preis"),
        }

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext.update(self.formsets())
        return kontext

    def post(self, request, *args, **kwargs):
        self.object = self.get_object() if isinstance(self, UpdateView) else None
        form = self.get_form()
        formsets = self.formsets()
        if form.is_valid() and all(fs.is_valid() for fs in formsets.values()):
            return self._speichern(form, formsets)
        return self.render_to_response(self.get_context_data(form=form))

    @transaction.atomic
    def _speichern(self, form, formsets):
        neu = form.instance.pk is None
        self.object = form.save()
        for formset in formsets.values():
            formset.instance = self.object
            formset.save()
        anfangsbestand = form.cleaned_data.get("anfangsbestand") if neu else None
        if neu and anfangsbestand and not self.object.seriennummern:
            bestand_aendern(
                self.object, anfangsbestand, "einlagerung",
                bezug_typ="initial", notiz="Anfangsbestand", benutzer=self.request.user,
            )
        if neu:
            messages.success(
                self.request, f"Artikel angelegt (Artikelnummer {self.object.artikelnummer})."
            )
        else:
            messages.success(self.request, "Artikel aktualisiert.")
        return redirect(self.get_success_url())


class ArtikelCreateView(ArtikelFormularMixin, CreateView):
    extra_context = {"seitentitel": "Neuer Artikel"}

    def _position(self):
        """Angebotsposition ohne Artikel, aus der dieser Artikel angelegt wird (?aus_position=)."""
        from belege.models import AngebotPosition

        pk = self.request.GET.get("aus_position") or self.request.POST.get("aus_position")
        if not (pk and str(pk).isdigit()):
            return None
        return AngebotPosition.objects.filter(pk=pk, artikel__isnull=True).select_related("angebot").first()

    def get_initial(self):
        start = {"einheit": "Stk.", "steuersatz": Decimal("19.00"), "lagerfuehrung": True, "aktiv": True}
        position = self._position()
        if position:
            start.update(name=position.beschreibung, verkaufspreis=position.einzelpreis, steuersatz=position.steuersatz)
            if position.einheit:
                start["einheit"] = position.einheit
        return start

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        position = self._position()
        kontext["aus_position"] = position.pk if position else ""
        return kontext

    def get_success_url(self):
        position = self._position()
        if position:
            position.artikel = self.object
            position.artikelnummer = self.object.artikelnummer
            position.save(update_fields=["artikel", "artikelnummer"])
            return reverse("belege:angebote_ansehen", args=[position.angebot_id])
        return super().get_success_url()


class ArtikelUpdateView(ArtikelFormularMixin, UpdateView):
    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["seitentitel"] = self.object.name
        return kontext


class ArtikelDeaktivierenView(ModulRechtMixin, View):
    """Artikel werden nie gelöscht (Belege verweisen darauf), nur deaktiviert."""

    modul = "artikel"
    http_method_names = ["post"]

    def post(self, request, pk):
        artikel = get_object_or_404(Artikel, pk=pk)
        artikel.aktiv = False
        artikel.save(update_fields=["aktiv"])
        messages.success(request, "Artikel deaktiviert.")
        return redirect("stammdaten:artikel_liste")


# ---------------------------------------------------------------------------
# Kunden
# ---------------------------------------------------------------------------


class KundeListView(ModulRechtMixin, LiveSucheMixin, ListView):
    modul = "kunden"
    model = Kunde
    template_name = "stammdaten/kunde_liste.html"
    fragment_template_name = "stammdaten/_kunden_tabelle.html"
    context_object_name = "kunden"

    def get_queryset(self):
        abfrage = Kunde.objects.all()
        suche = self.request.GET.get("q", "").strip()
        if suche:
            abfrage = abfrage.filter(
                Q(firma__icontains=suche)
                | Q(nachname__icontains=suche)
                | Q(kundennummer__icontains=suche)
            )
        return abfrage

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext.update(seitentitel="Kunden", suche=self.request.GET.get("q", ""))
        return kontext


class KundeFormularMixin(ModulRechtMixin):
    modul = "kunden"
    model = Kunde
    form_class = KundeForm
    template_name = "stammdaten/kunde_form.html"
    success_url = reverse_lazy("stammdaten:kunden_liste")

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        daten = self.request.POST if self.request.method == "POST" else None
        kontext["ansprechpartner"] = kwargs.get("ansprechpartner") or AnsprechpartnerFormSet(
            daten, instance=self.object, prefix="ansp"
        )
        kontext["aktiver_tab"] = self.request.GET.get("tab", "allgemein")
        if self.object and self.object.pk:
            kontext.update(self._buchhaltung())
        return kontext

    def _buchhaltung(self) -> dict:
        """Letzte Angebote und Rechnungen, sobald das Belege-Modul vorhanden ist."""
        if not apps.is_installed("belege"):
            return {"angebote": [], "rechnungen": [], "offene_summe": self.object.offene_summe}
        Angebot = apps.get_model("belege", "Angebot")
        Rechnung = apps.get_model("belege", "Rechnung")
        return {
            "angebote": list(Angebot.objects.filter(kunde=self.object).order_by("-datum", "-pk")[:10]),
            "rechnungen": list(Rechnung.objects.filter(kunde=self.object).order_by("-datum", "-pk")[:10]),
            "offene_summe": self.object.offene_summe,
        }

    def post(self, request, *args, **kwargs):
        self.object = self.get_object() if isinstance(self, UpdateView) else None
        form = self.get_form()
        ansprechpartner = AnsprechpartnerFormSet(request.POST, instance=self.object, prefix="ansp")
        if form.is_valid() and ansprechpartner.is_valid():
            with transaction.atomic():
                self.object = form.save()
                ansprechpartner.instance = self.object
                ansprechpartner.save()
            messages.success(
                request, "Kunde aktualisiert." if isinstance(self, UpdateView) else "Kunde angelegt."
            )
            return redirect(self.get_success_url())
        return self.render_to_response(
            self.get_context_data(form=form, ansprechpartner=ansprechpartner)
        )


class KundeCreateView(KundeFormularMixin, CreateView):
    extra_context = {"seitentitel": "Neuer Kunde"}


class KundeUpdateView(KundeFormularMixin, UpdateView):
    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["seitentitel"] = self.object.anzeigename
        return kontext


class KundeLoeschenView(ModulRechtMixin, View):
    modul = "kunden"
    http_method_names = ["post"]

    def post(self, request, pk):
        kunde = get_object_or_404(Kunde, pk=pk)
        try:
            kunde.delete()
            messages.success(request, "Kunde gelöscht.")
        except ProtectedError:
            messages.error(
                request,
                "Kunde kann nicht gelöscht werden – es existieren bereits Belege.",
            )
        return redirect("stammdaten:kunden_liste")


class RechnungBezahltView(ModulRechtMixin, View):
    """Markiert eine Rechnung aus der Buchhaltungs-Registerkarte als bezahlt."""

    modul = "kunden"
    http_method_names = ["post"]

    def post(self, request, pk, rechnung_pk):
        kunde = get_object_or_404(Kunde, pk=pk)
        if apps.is_installed("belege"):
            Rechnung = apps.get_model("belege", "Rechnung")
            rechnung = get_object_or_404(Rechnung, pk=rechnung_pk, kunde=kunde)
            rechnung.als_bezahlt_markieren()
            messages.success(request, "Rechnung als bezahlt markiert.")
        return redirect(f"{reverse('stammdaten:kunden_bearbeiten', args=[kunde.pk])}?tab=buchhaltung")


# ---------------------------------------------------------------------------
# Lieferanten
# ---------------------------------------------------------------------------


class LieferantListView(ModulRechtMixin, LiveSucheMixin, ListView):
    modul = "lieferanten"
    model = Lieferant
    template_name = "stammdaten/lieferant_liste.html"
    fragment_template_name = "stammdaten/_lieferanten_tabelle.html"
    context_object_name = "lieferanten"

    def get_queryset(self):
        abfrage = Lieferant.objects.all()
        suche = self.request.GET.get("q", "").strip()
        if suche:
            abfrage = abfrage.filter(
                Q(firma__icontains=suche)
                | Q(nachname__icontains=suche)
                | Q(lieferantennummer__icontains=suche)
            )
        return abfrage

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext.update(seitentitel="Lieferanten", suche=self.request.GET.get("q", ""))
        return kontext


class LieferantFormularMixin(ModulRechtMixin):
    modul = "lieferanten"
    model = Lieferant
    form_class = LieferantForm
    template_name = "stammdaten/lieferant_form.html"
    success_url = reverse_lazy("stammdaten:lieferanten_liste")


class LieferantCreateView(LieferantFormularMixin, CreateView):
    extra_context = {"seitentitel": "Neuer Lieferant"}

    def form_valid(self, form):
        messages.success(self.request, "Lieferant angelegt.")
        return super().form_valid(form)


class LieferantUpdateView(LieferantFormularMixin, UpdateView):
    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["seitentitel"] = self.object.anzeigename
        return kontext

    def form_valid(self, form):
        messages.success(self.request, "Lieferant aktualisiert.")
        return super().form_valid(form)


class LieferantLoeschenView(ModulRechtMixin, View):
    modul = "lieferanten"
    http_method_names = ["post"]

    def post(self, request, pk):
        lieferant = get_object_or_404(Lieferant, pk=pk)
        lieferant.delete()
        messages.success(request, "Lieferant gelöscht.")
        return redirect("stammdaten:lieferanten_liste")
