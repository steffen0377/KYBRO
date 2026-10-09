"""Kalender-Ansichten: Monatsübersicht, Termine, Kalenderverwaltung, Abo-Adressen und der öffentliche Abo-Feed."""

import calendar
import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, TemplateView, UpdateView

from accounts.mixins import ModulRechtMixin
from accounts.modules import AKTION_LESEN

from . import ics, quellen
from .forms import KalenderForm, TerminForm
from .models import Kalender, KalenderZugang, Termin

User = get_user_model()

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]


class KalenderMixin(ModulRechtMixin):
    modul = "kalender"


def _monat(request) -> tuple[int, int]:
    try:
        jahr, monat = (int(x) for x in request.GET.get("monat", "").split("-"))
        datetime.date(jahr, monat, 1)
        return jahr, monat
    except ValueError:
        heute = timezone.localdate()
        return heute.year, heute.month


def _nachbarmonate(jahr: int, monat: int) -> tuple[str, str]:
    zurueck = (jahr - 1, 12) if monat == 1 else (jahr, monat - 1)
    weiter = (jahr + 1, 1) if monat == 12 else (jahr, monat + 1)
    return "%d-%02d" % zurueck, "%d-%02d" % weiter


def tage_des_ereignisses(e: dict) -> list[datetime.date]:
    """Alle Kalendertage, an denen ein Ereignis stattfindet."""
    beginn = e["beginn"].date() if isinstance(e["beginn"], datetime.datetime) else e["beginn"]
    ende = e["ende"].date() if isinstance(e["ende"], datetime.datetime) else e["ende"]
    if not e["ganztaegig"] and isinstance(e["ende"], datetime.datetime) and e["ende"].time() == datetime.time.min and ende > beginn:
        ende -= datetime.timedelta(days=1)  # endet genau um Mitternacht: der Folgetag gehört nicht mehr dazu
    return [beginn + datetime.timedelta(days=i) for i in range(max((ende - beginn).days, 0) + 1)]


class MonatView(KalenderMixin, TemplateView):
    template_name = "kalender/monat.html"

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        jahr, monat = _monat(self.request)
        sichtbar = quellen.sichtbare_quellen(self.request.user)
        gewaehlt = self.request.GET.getlist("k")
        aktiv = [q for q in sichtbar if q.schluessel in gewaehlt] if gewaehlt else list(sichtbar)
        erster = datetime.date(jahr, monat, 1)
        letzter = datetime.date(jahr, monat, calendar.monthrange(jahr, monat)[1])
        anfang = erster - datetime.timedelta(days=erster.weekday())
        ende = letzter + datetime.timedelta(days=6 - letzter.weekday())
        je_tag: dict[datetime.date, list] = {}
        for q in aktiv:
            for e in quellen.ereignisse(q.schluessel, anfang, ende):
                e = {**e, "farbe": q.farbe, "kalendername": q.name}
                for tag in tage_des_ereignisses(e):
                    je_tag.setdefault(tag, []).append(e)
        for liste in je_tag.values():
            liste.sort(key=lambda e: (not e["ganztaegig"], e["beginn"] if not e["ganztaegig"] else datetime.datetime.min, e["titel"]))
        wochen, tag = [], anfang
        while tag <= ende:
            wochen.append([
                {"datum": d, "im_monat": d.month == monat, "heute": d == timezone.localdate(), "ereignisse": je_tag.get(d, [])}
                for d in (tag + datetime.timedelta(days=i) for i in range(7))
            ])
            tag += datetime.timedelta(days=7)
        zurueck, weiter = _nachbarmonate(jahr, monat)
        kontext.update(
            seitentitel="Kalender", wochen=wochen, monatsname=f"{MONATE[monat - 1]} {jahr}", zurueck=zurueck, weiter=weiter,
            heute_monat=timezone.localdate().strftime("%Y-%m"), quellen=sichtbar, aktive={q.schluessel for q in aktiv},
            monat_param=f"{jahr}-{monat:02d}", darf_schreiben=self.request.user.hat_modulrecht("kalender", "schreiben"),
            auswahl=[("k", q.schluessel) for q in aktiv] if gewaehlt else [],
        )
        return kontext


class TerminMixin(KalenderMixin):
    model = Termin
    form_class = TerminForm
    template_name = "kalender/termin_form.html"
    success_url = reverse_lazy("kalender:monat")

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["keine_kalender"] = not Kalender.objects.exists()
        return kontext

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.erstellt_von = self.request.user
        messages.success(self.request, "Termin gespeichert.")
        antwort = super().form_valid(form)
        d = timezone.localtime(self.object.beginn)
        return redirect(f"{reverse('kalender:monat')}?monat={d.year}-{d.month:02d}")


class TerminNeuView(TerminMixin, CreateView):
    extra_context = {"seitentitel": "Neuer Termin"}

    def get_initial(self):
        initial = super().get_initial()
        try:
            tag = datetime.date.fromisoformat(self.request.GET.get("datum", ""))
        except ValueError:
            tag = timezone.localdate()
        initial.update(
            beginn_datum=tag, ende_datum=tag, beginn_zeit=datetime.time(9, 0), ende_zeit=datetime.time(10, 0),
        )
        kal = self.request.GET.get("kalender", "")
        if kal.isdigit():
            initial["kalender"] = int(kal)
        return initial


class TerminBearbeitenView(TerminMixin, UpdateView):
    extra_context = {"seitentitel": "Termin bearbeiten", "bearbeiten": True}


class TerminLoeschenView(KalenderMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        termin = get_object_or_404(Termin, pk=pk)
        termin.delete()
        messages.success(request, "Termin gelöscht.")
        return redirect("kalender:monat")


# --- Kalender verwalten ------------------------------------------------------------------------


class KalenderListeView(KalenderMixin, ListView):
    model = Kalender
    template_name = "kalender/kalender_liste.html"
    context_object_name = "kalender"
    extra_context = {"seitentitel": "Kalender verwalten"}

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["systemkalender"] = quellen.SYSTEMKALENDER
        return kontext


class KalenderFormMixin(KalenderMixin):
    model = Kalender
    form_class = KalenderForm
    template_name = "kalender/kalender_form.html"
    success_url = reverse_lazy("kalender:kalender_liste")

    def form_valid(self, form):
        messages.success(self.request, "Kalender gespeichert.")
        return super().form_valid(form)


class KalenderNeuView(KalenderFormMixin, CreateView):
    extra_context = {"seitentitel": "Neuer Kalender"}


class KalenderBearbeitenView(KalenderFormMixin, UpdateView):
    extra_context = {"seitentitel": "Kalender bearbeiten", "bearbeiten": True}


class KalenderLoeschenView(KalenderMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        k = get_object_or_404(Kalender, pk=pk)
        anzahl = k.termine.count()
        k.delete()
        messages.success(request, f"Kalender „{k.name}“ mit {anzahl} Termin(en) gelöscht.")
        return redirect("kalender:kalender_liste")


# --- Abo-Adressen und Feed ----------------------------------------------------------------------


class AboView(KalenderMixin, TemplateView):
    """Adressen zum Abonnieren; jeder Benutzer mit Leserecht darf sie sehen und seinen Schlüssel erneuern."""

    template_name = "kalender/abo.html"

    def get_aktion(self):
        return AKTION_LESEN

    def post(self, request, *args, **kwargs):
        KalenderZugang.objects.get_or_create(benutzer=request.user)[0].erneuern()
        messages.success(request, "Neuer Schlüssel erzeugt. Die alten Abo-Adressen funktionieren nicht mehr.")
        return redirect("kalender:abo")

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        zugang, _ = KalenderZugang.objects.get_or_create(benutzer=self.request.user)
        basis = self.request.build_absolute_uri("/")[:-1]

        def adresse(schluessel):
            https = basis + reverse("kalender:feed", args=[zugang.schluessel, schluessel])
            return {"https": https, "webcal": "webcal://" + https.split("://", 1)[1]}

        sichtbar = quellen.sichtbare_quellen(self.request.user)
        kontext.update(
            seitentitel="Kalender abonnieren",
            eintraege=[{"quelle": q, **adresse(q.schluessel)} for q in sichtbar],
            alle=adresse("alle") if sichtbar else None,
        )
        return kontext


class FeedView(View):
    """Öffentlicher iCal-Feed, geschützt durch den persönlichen Schlüssel in der Adresse (nur lesend)."""

    def get(self, request, schluessel, kalender):
        zugang = KalenderZugang.objects.select_related("benutzer").filter(schluessel=schluessel).first()
        if not zugang or not zugang.benutzer.is_active:
            raise Http404
        user = zugang.benutzer
        sichtbar = quellen.sichtbare_quellen(user)
        if kalender == "alle":
            gewaehlt, name, farbe = sichtbar, "KYBRO", ""
        else:
            gewaehlt = [q for q in sichtbar if q.schluessel == kalender]
            if not gewaehlt:
                raise Http404
            name, farbe = gewaehlt[0].name, gewaehlt[0].farbe
            name = f"KYBRO: {name}"
        von, bis = quellen.standardfenster()
        ereignisse = [e for q in gewaehlt for e in quellen.ereignisse(q.schluessel, von, bis)]
        antwort = HttpResponse(ics.kalender_text(ereignisse, name, farbe), content_type="text/calendar; charset=utf-8")
        antwort["Cache-Control"] = "private, max-age=300"
        antwort["Content-Disposition"] = 'inline; filename="kybro.ics"'
        return antwort
