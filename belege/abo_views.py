"""Abonnements: Liste, Detail, Kündigung."""

from datetime import date

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import DetailView, ListView

from accounts.mixins import ModulRechtMixin
from core.views import LiveSucheMixin

from . import abos
from .models import Abo


class AboListeView(ModulRechtMixin, LiveSucheMixin, ListView):
    modul = "abos"
    model = Abo
    context_object_name = "abos"
    template_name = "belege/abo_liste.html"
    fragment_template_name = "belege/_abo_tabelle.html"

    def get_queryset(self):
        abfrage = Abo.objects.select_related("kunde", "artikel")
        suche = self.request.GET.get("q", "").strip()
        if suche:
            abfrage = abfrage.filter(
                Q(kunde__firma__icontains=suche) | Q(kunde__nachname__icontains=suche)
                | Q(kunde__kundennummer__icontains=suche) | Q(artikel__name__icontains=suche)
            )
        status = self.request.GET.get("status", "")
        if status in Abo.Status.values:
            abfrage = abfrage.filter(status=status)
        return abfrage

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext.update(
            seitentitel="Abonnements", suche=self.request.GET.get("q", ""),
            status_filter=self.request.GET.get("status", ""), status_auswahl=Abo.Status.choices,
        )
        return kontext


class AboDetailView(ModulRechtMixin, DetailView):
    modul = "abos"
    model = Abo
    context_object_name = "abo"
    template_name = "belege/abo_detail.html"

    def get_queryset(self):
        return Abo.objects.select_related("kunde", "artikel", "ursprungsrechnung")

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        abo = self.object
        kontext["rechnungen"] = abo.rechnungen.order_by("-zeitraum_von", "-pk")
        kontext["darf_schreiben"] = self.request.user.hat_modulrecht("abos", "schreiben")
        kontext["seitentitel"] = f"Abonnement {abo.artikel.name}"
        if abo.status == Abo.Status.AKTIV:
            kontext["vorschau"] = abos.kuendigung_berechnen(abo)
        return kontext


class AboKuendigenView(ModulRechtMixin, View):
    modul = "abos"
    http_method_names = ["post"]

    def post(self, request, pk):
        abo = get_object_or_404(Abo, pk=pk)
        eingang = None
        if request.POST.get("eingang"):
            try:
                eingang = date.fromisoformat(request.POST["eingang"])
            except ValueError:
                messages.error(request, "Ungültiges Datum.")
                return redirect("belege:abos_ansehen", pk=pk)
        try:
            abos.abo_kuendigen(abo, eingang)
        except ValueError as fehler:
            messages.error(request, str(fehler))
        else:
            messages.success(request, f"Kündigung vorgemerkt, das Abonnement endet am {abo.kuendigung_wirksam:%d.%m.%Y}.")
        return redirect("belege:abos_ansehen", pk=pk)


class AboReaktivierenView(ModulRechtMixin, View):
    modul = "abos"
    http_method_names = ["post"]

    def post(self, request, pk):
        abo = get_object_or_404(Abo, pk=pk)
        try:
            abos.abo_kuendigung_zuruecknehmen(abo)
        except ValueError as fehler:
            messages.error(request, str(fehler))
        else:
            messages.success(request, "Kündigung zurückgenommen.")
        return redirect("belege:abos_ansehen", pk=pk)
