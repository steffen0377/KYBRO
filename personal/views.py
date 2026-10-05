"""Ansichten der Personalverwaltung."""

import datetime

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, TemplateView, UpdateView

from accounts.mixins import ModulRechtMixin
from core.views import LiveSucheMixin

from .forms import AnwesenheitForm, MitarbeiterForm, UrlaubsantragForm, UrlaubsjahrForm, VertragForm
from .models import Anwesenheit, Mitarbeiter, Urlaubsantrag, Urlaubsjahr, Vertrag
from .services import antrag_tage, monatsuebersicht, urlaubskonto


def _monat(request) -> tuple[int, int]:
    try:
        jahr, monat = (int(x) for x in request.GET.get("monat", "").split("-"))
        datetime.date(jahr, monat, 1)
        return jahr, monat
    except ValueError:
        heute = datetime.date.today()
        return heute.year, heute.month


def _jahr(request) -> int:
    wert = request.GET.get("jahr", "")
    return int(wert) if wert.isdigit() and 1990 < int(wert) < 2200 else datetime.date.today().year


def _nachbarmonate(jahr: int, monat: int) -> tuple[str, str]:
    vor = datetime.date(jahr, monat, 1) - datetime.timedelta(days=1)
    nach = datetime.date(jahr + (monat == 12), monat % 12 + 1, 1)
    return f"{vor.year}-{vor.month:02d}", f"{nach.year}-{nach.month:02d}"


class PersonalMixin(ModulRechtMixin):
    modul = "personal"


# --- Mitarbeiter --------------------------------------------------------------------------------


class MitarbeiterListView(PersonalMixin, LiveSucheMixin, ListView):
    model = Mitarbeiter
    template_name = "personal/mitarbeiter_liste.html"
    fragment_template_name = "personal/_mitarbeiter_tabelle.html"
    context_object_name = "mitarbeiter"
    extra_context = {"seitentitel": "Mitarbeiter"}

    def get_queryset(self):
        abfrage = Mitarbeiter.objects.select_related("benutzer")
        suche = self.request.GET.get("q", "").strip()
        if suche:
            abfrage = abfrage.filter(
                Q(vorname__icontains=suche) | Q(nachname__icontains=suche) | Q(personalnummer__icontains=suche)
                | Q(abteilung__icontains=suche) | Q(position__icontains=suche)
            )
        if self.request.GET.get("ehemalige") != "1":
            heute = datetime.date.today()
            abfrage = abfrage.filter(Q(austrittsdatum__isnull=True) | Q(austrittsdatum__gte=heute))
        return abfrage

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["suche"] = self.request.GET.get("q", "")
        kontext["ehemalige"] = self.request.GET.get("ehemalige") == "1"
        from django.contrib.auth import get_user_model

        kontext["ohne_mitarbeiter"] = get_user_model().objects.filter(
            is_active=True, mitarbeiter__isnull=True
        ).order_by("username")
        return kontext


class MitarbeiterCreateView(PersonalMixin, CreateView):
    model = Mitarbeiter
    form_class = MitarbeiterForm
    template_name = "personal/mitarbeiter_form.html"
    extra_context = {"seitentitel": "Neuer Mitarbeiter"}

    def get_initial(self):
        """``?benutzer=<id>`` übernimmt Name und E-Mail eines vorhandenen Logins."""
        initial = super().get_initial()
        benutzer_id = self.request.GET.get("benutzer", "")
        if benutzer_id.isdigit():
            from django.contrib.auth import get_user_model

            u = get_user_model().objects.filter(pk=int(benutzer_id), mitarbeiter__isnull=True).first()
            if u:
                initial.update(benutzer=u.pk, vorname=u.first_name, nachname=u.last_name or u.username, email=u.email)
        return initial

    def get_success_url(self):
        messages.success(self.request, "Mitarbeiter angelegt.")
        return reverse("personal:mitarbeiter_detail", args=[self.object.pk])


class MitarbeiterUpdateView(PersonalMixin, UpdateView):
    model = Mitarbeiter
    form_class = MitarbeiterForm
    template_name = "personal/mitarbeiter_form.html"

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["seitentitel"] = self.object.anzeigename
        return kontext

    def get_success_url(self):
        messages.success(self.request, "Mitarbeiter gespeichert.")
        return reverse("personal:mitarbeiter_detail", args=[self.object.pk])


class MitarbeiterDetailView(PersonalMixin, DetailView):
    model = Mitarbeiter
    template_name = "personal/mitarbeiter_detail.html"

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        m = self.object
        jahr = _jahr(self.request)
        kontext.update(
            seitentitel=m.anzeigename,
            jahr=jahr,
            konto=urlaubskonto(m, jahr),
            urlaubsjahr=Urlaubsjahr.objects.filter(mitarbeiter=m, jahr=jahr).first(),
            vertraege=m.vertraege.all(),
            antraege=self._antraege(m, jahr),
            aktueller_vertrag=next((v for v in m.vertraege.all() if v.gueltig_bis is None or v.gueltig_bis >= datetime.date.today()), None),
            anwesenheiten=m.anwesenheiten.all()[:20],
        )
        return kontext

    @staticmethod
    def _antraege(m, jahr):
        antraege = list(m.urlaubsantraege.filter(Q(von__year=jahr) | Q(bis__year=jahr)))
        for a in antraege:
            a.tage = antrag_tage(m, a)
        return antraege


class MitarbeiterLoeschenView(PersonalMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        m = get_object_or_404(Mitarbeiter, pk=pk)
        name = m.anzeigename
        m.delete()
        messages.success(request, f"{name} wurde samt Verträgen, Urlaub und Anwesenheiten gelöscht.")
        return redirect("personal:mitarbeiter_liste")


# --- Verträge -----------------------------------------------------------------------------------


class VertragMixin(PersonalMixin):
    model = Vertrag
    form_class = VertragForm
    template_name = "personal/vertrag_form.html"

    def get_success_url(self):
        messages.success(self.request, "Vertragsstand gespeichert.")
        return reverse("personal:mitarbeiter_detail", args=[self.mitarbeiter.pk])


class VertragCreateView(VertragMixin, CreateView):
    def dispatch(self, request, *args, **kwargs):
        self.mitarbeiter = get_object_or_404(Mitarbeiter, pk=kwargs["mitarbeiter_pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["mitarbeiter"] = self.mitarbeiter
        letzter = self.mitarbeiter.vertraege.first()
        if letzter and not kwargs.get("data"):
            kwargs["initial"] = {
                "art": letzter.art, "wochenstunden": letzter.wochenstunden, "urlaubstage_pro_jahr": letzter.urlaubstage_pro_jahr,
                "arbeitstage": [str(t) for t in letzter.arbeitstage_liste], "kuendigungsfrist": letzter.kuendigungsfrist,
                "gueltig_ab": letzter.gueltig_bis + datetime.timedelta(days=1) if letzter.gueltig_bis else datetime.date.today(),
            }
        return kwargs

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext.update(mitarbeiter=self.mitarbeiter, seitentitel="Neuer Vertragsstand")
        return kontext


class VertragUpdateView(VertragMixin, UpdateView):
    def dispatch(self, request, *args, **kwargs):
        self.mitarbeiter = get_object_or_404(Vertrag, pk=kwargs["pk"]).mitarbeiter
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["mitarbeiter"] = self.mitarbeiter
        return kwargs

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext.update(mitarbeiter=self.mitarbeiter, seitentitel="Vertragsstand bearbeiten")
        return kontext


class VertragLoeschenView(PersonalMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        v = get_object_or_404(Vertrag, pk=pk)
        mitarbeiter_pk = v.mitarbeiter_id
        v.delete()
        messages.success(request, "Vertragsstand gelöscht.")
        return redirect("personal:mitarbeiter_detail", pk=mitarbeiter_pk)


class UrlaubsjahrView(PersonalMixin, UpdateView):
    form_class = UrlaubsjahrForm
    template_name = "personal/urlaubsjahr_form.html"

    def get_object(self, queryset=None):
        self.mitarbeiter = get_object_or_404(Mitarbeiter, pk=self.kwargs["mitarbeiter_pk"])
        objekt, _ = Urlaubsjahr.objects.get_or_create(mitarbeiter=self.mitarbeiter, jahr=self.kwargs["jahr"])
        return objekt

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext.update(mitarbeiter=self.mitarbeiter, seitentitel=f"Urlaubsjahr {self.object.jahr}")
        return kontext

    def get_success_url(self):
        messages.success(self.request, "Urlaubsjahr gespeichert.")
        return reverse("personal:mitarbeiter_detail", args=[self.mitarbeiter.pk]) + f"?jahr={self.object.jahr}"


# --- Anwesenheit --------------------------------------------------------------------------------


class AnwesenheitView(PersonalMixin, FormView):
    """Monatsübersicht aller Mitarbeiter und Formular zum Eintragen."""

    form_class = AnwesenheitForm
    template_name = "personal/anwesenheit.html"

    def get_success_url(self):
        return self.request.get_full_path()

    def form_valid(self, form):
        anzahl = form.speichern()
        messages.success(self.request, f"{anzahl} Tag(e) gespeichert." if not form.cleaned_data["entfernen"] else f"{anzahl} Eintrag/Einträge entfernt.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        jahr, monat = _monat(self.request)
        erster = datetime.date(jahr, monat, 1)
        letzter = datetime.date(jahr, monat, monthrange(jahr, monat))
        mitarbeiter = Mitarbeiter.objects.filter(
            Q(eintrittsdatum__isnull=True) | Q(eintrittsdatum__lte=letzter),
            Q(austrittsdatum__isnull=True) | Q(austrittsdatum__gte=erster),
        )
        zurueck, weiter = _nachbarmonate(jahr, monat)
        kontext.update(
            seitentitel="Anwesenheit", uebersicht=monatsuebersicht(mitarbeiter, jahr, monat),
            monat_datum=erster, zurueck=zurueck, weiter=weiter, heute=datetime.date.today(),
        )
        return kontext


def monthrange(jahr: int, monat: int) -> int:
    import calendar

    return calendar.monthrange(jahr, monat)[1]


# --- Urlaub -------------------------------------------------------------------------------------


class UrlaubListView(PersonalMixin, ListView):
    model = Urlaubsantrag
    template_name = "personal/urlaub_liste.html"
    context_object_name = "antraege"
    extra_context = {"seitentitel": "Urlaubsanträge"}

    def get_queryset(self):
        abfrage = Urlaubsantrag.objects.select_related("mitarbeiter")
        status = self.request.GET.get("status", "offen")
        if status == "offen":
            abfrage = abfrage.filter(status=Urlaubsantrag.Status.BEANTRAGT)
        elif status in Urlaubsantrag.Status.values:
            abfrage = abfrage.filter(status=status)
        return abfrage

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["status"] = self.request.GET.get("status", "offen")
        kontext["stati"] = Urlaubsantrag.Status.choices
        for a in kontext["antraege"]:
            a.tage = antrag_tage(a.mitarbeiter, a)
        return kontext


class UrlaubNeuView(PersonalMixin, CreateView):
    """Urlaub für beliebige Mitarbeiter eintragen. Wird direkt genehmigt."""

    model = Urlaubsantrag
    form_class = UrlaubsantragForm
    template_name = "personal/urlaub_form.html"
    success_url = reverse_lazy("personal:urlaub_liste")
    extra_context = {"seitentitel": "Urlaub eintragen"}

    def get_initial(self):
        mid = self.request.GET.get("mitarbeiter", "")
        return {"mitarbeiter": int(mid)} if mid.isdigit() else {}

    def form_valid(self, form):
        form.instance.status = Urlaubsantrag.Status.GENEHMIGT
        form.instance.entschieden_von = self.request.user
        form.instance.entschieden_am = timezone.now()
        messages.success(self.request, "Urlaub eingetragen und genehmigt.")
        return super().form_valid(form)


class UrlaubEntscheidenView(PersonalMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        antrag = get_object_or_404(Urlaubsantrag, pk=pk)
        aktion = request.POST.get("aktion")
        neu = {"genehmigen": Urlaubsantrag.Status.GENEHMIGT, "ablehnen": Urlaubsantrag.Status.ABGELEHNT,
               "stornieren": Urlaubsantrag.Status.STORNIERT}.get(aktion)
        if neu:
            antrag.status = neu
            antrag.entschieden_von = request.user
            antrag.entschieden_am = timezone.now()
            try:
                antrag.full_clean()
            except Exception as fehler:
                messages.error(request, "; ".join(getattr(fehler, "messages", [str(fehler)])))
            else:
                antrag.save()
                messages.success(request, f"Urlaubsantrag: {antrag.get_status_display().lower()}.")
        return redirect(request.POST.get("weiter") or "personal:urlaub_liste")


# --- Eigene Daten (Self-Service für verknüpfte Benutzer) --------------------------------------------


class EigeneDatenMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.mitarbeiter = Mitarbeiter.objects.filter(benutzer=request.user).first()
            if not self.mitarbeiter:
                raise PermissionDenied("Ihr Benutzerkonto ist mit keinem Mitarbeiter verknüpft.")
        return super().dispatch(request, *args, **kwargs)


class MeineZeitenView(EigeneDatenMixin, FormView):
    form_class = AnwesenheitForm
    template_name = "personal/meine_zeiten.html"
    success_url = reverse_lazy("personal:meine_zeiten")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["mitarbeiter"] = self.mitarbeiter
        return kwargs

    def form_valid(self, form):
        form.speichern()
        messages.success(self.request, "Gespeichert.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        m = self.mitarbeiter
        jahr, monat = _monat(self.request)
        zurueck, weiter = _nachbarmonate(jahr, monat)
        antraege = list(m.urlaubsantraege.filter(bis__gte=datetime.date(jahr, 1, 1)))
        for a in antraege:
            a.tage = antrag_tage(m, a)
        kontext.update(
            seitentitel="Meine Zeiten", mitarbeiter=m, konto=urlaubskonto(m, datetime.date.today().year),
            uebersicht=monatsuebersicht([m], jahr, monat), monat_datum=datetime.date(jahr, monat, 1),
            zurueck=zurueck, weiter=weiter, antraege=antraege,
        )
        return kontext


class MeinUrlaubNeuView(EigeneDatenMixin, CreateView):
    model = Urlaubsantrag
    form_class = UrlaubsantragForm
    template_name = "personal/urlaub_form.html"
    success_url = reverse_lazy("personal:meine_zeiten")
    extra_context = {"seitentitel": "Urlaub beantragen", "eigener": True}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["mitarbeiter"] = self.mitarbeiter
        return kwargs

    def form_valid(self, form):
        messages.success(self.request, "Urlaubsantrag gestellt.")
        return super().form_valid(form)


class MeinUrlaubStornierenView(EigeneDatenMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        antrag = get_object_or_404(Urlaubsantrag, pk=pk, mitarbeiter=self.mitarbeiter)
        if antrag.status == Urlaubsantrag.Status.BEANTRAGT:
            antrag.status = Urlaubsantrag.Status.STORNIERT
            antrag.save(update_fields=["status"])
            messages.success(request, "Antrag zurückgezogen.")
        else:
            messages.error(request, "Nur offene Anträge können zurückgezogen werden. Bitte wende dich an die Personalverwaltung.")
        return redirect("personal:meine_zeiten")
