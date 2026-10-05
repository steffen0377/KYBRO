"""Einstellungen (nur Administratoren): Firma, Nummernkreise, E-Mail, Formulare, Lizenzen, Anmeldung."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, FormView, ListView, TemplateView, UpdateView

from accounts import ldap
from accounts.mixins import AdminRequiredMixin

from . import live, mail
from .forms import (
    AuthentifizierungForm,
    BriefbogenElementForm,
    FirmaForm,
    FormulareForm,
    LiveAktivierenForm,
    LizenzForm,
    MailForm,
    NummernkreisFormSet,
)
from .models import Authentifizierung, BriefbogenElement, Firma, Lizenz, Nummernkreis

REGISTER = (
    ("firma", "Firma"), ("briefbogen", "Briefbogen"), ("nummernkreise", "Nummernkreise"), ("mail", "E-Mail"),
    ("formulare", "Formulare"), ("lizenzen", "Lizenzen"), ("anmeldung", "Anmeldung"),
)


class EinstellungenMixin(AdminRequiredMixin):
    register = ""
    seitentitel = "Einstellungen"

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext.update(register=REGISTER, aktives_register=self.register, seitentitel=self.seitentitel)
        return kontext


class EinzeleintragView(EinstellungenMixin, UpdateView):
    template_name = "einstellungen/einzeleintrag.html"
    meldung = "Einstellungen gespeichert."

    def get_object(self, queryset=None):
        return self.modell.holen()

    def get_success_url(self):
        return reverse(f"einstellungen:{self.register}")

    def form_valid(self, form):
        antwort = super().form_valid(form)
        messages.success(self.request, self.meldung)
        return antwort


class FirmaView(EinzeleintragView):
    register = "firma"
    modell = Firma
    form_class = FirmaForm
    extra_context = {"titel": "Firmendaten"}


class MailView(EinzeleintragView):
    register = "mail"
    modell = Firma
    form_class = MailForm
    extra_context = {"titel": "E-Mail-Versand (SMTP)", "testknopf": "Testmail an mich senden"}

    def post(self, request, *args, **kwargs):
        if "test" in request.POST:
            return self._test(request)
        return super().post(request, *args, **kwargs)

    def _test(self, request):
        ziel = request.user.email
        if not ziel:
            messages.error(request, "Für Ihr Benutzerkonto ist keine E-Mail-Adresse hinterlegt.")
        else:
            try:
                mail.senden([ziel], "Testmail", "Der E-Mail-Versand ist korrekt eingerichtet.")
            except mail.MailFehler as fehler:
                messages.error(request, f"Testmail konnte nicht gesendet werden: {fehler}")
            else:
                messages.success(request, f"Testmail an {ziel} gesendet.")
        return redirect("einstellungen:mail")


class AnmeldungView(EinzeleintragView):
    register = "anmeldung"
    modell = Authentifizierung
    form_class = AuthentifizierungForm
    template_name = "einstellungen/anmeldung.html"
    extra_context = {"titel": "Anmeldung und LDAP"}

    def post(self, request, *args, **kwargs):
        if "test" in request.POST:
            try:
                messages.success(request, ldap.verbindung_testen())
                benutzer = request.POST.get("test_benutzer", "").strip()
                if benutzer:
                    messages.success(request, ldap.benutzer_testen(benutzer, request.POST.get("test_passwort", "")))
            except ldap.LdapNichtErreichbar as fehler:
                messages.error(request, f"LDAP-Verbindung fehlgeschlagen: {fehler}")
            return redirect("einstellungen:anmeldung")
        return super().post(request, *args, **kwargs)


class LiveAktivierenView(EinstellungenMixin, FormView):
    """Einmaliger Wechsel vom Testbetrieb in den Live-Betrieb (löscht die Testdaten)."""

    register = "firma"
    template_name = "einstellungen/live.html"
    form_class = LiveAktivierenForm
    success_url = reverse_lazy("core:dashboard")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and Firma.holen().betriebsmodus == Firma.Betrieb.LIVE:
            messages.info(request, "Die Installation ist bereits im Live-Betrieb.")
            return redirect("einstellungen:firma")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            anzahl = live.live_aktivieren(self.request.user)
        except live.LiveSchonAktiv:
            return redirect("einstellungen:firma")
        gesamt = sum(anzahl.values())
        messages.success(self.request, f"Live-Betrieb aktiviert. {gesamt} Testdatensätze wurden gelöscht.")
        return super().form_valid(form)


class NummernkreiseView(EinstellungenMixin, TemplateView):
    register = "nummernkreise"
    template_name = "einstellungen/nummernkreise.html"

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["formset"] = kwargs.get("formset") or NummernkreisFormSet(queryset=Nummernkreis.objects.all())
        kontext["jahr"] = timezone.localdate().year
        kontext["firma"] = Firma.holen()
        return kontext

    def post(self, request, *args, **kwargs):
        formset = NummernkreisFormSet(request.POST, queryset=Nummernkreis.objects.all())
        if formset.is_valid():
            formset.save()
            messages.success(request, "Nummernkreise gespeichert.")
            return redirect("einstellungen:nummernkreise")
        return self.render_to_response(self.get_context_data(formset=formset))


class FormulareView(EinstellungenMixin, FormView):
    register = "formulare"
    template_name = "einstellungen/formulare.html"
    form_class = FormulareForm
    success_url = reverse_lazy("einstellungen:formulare")

    def form_valid(self, form):
        form.speichern()
        messages.success(self.request, "Formulareinstellungen gespeichert.")
        return super().form_valid(form)


class BriefbogenListeView(EinstellungenMixin, ListView):
    register = "briefbogen"
    model = BriefbogenElement
    context_object_name = "elemente"
    template_name = "einstellungen/briefbogen_liste.html"


class BriefbogenFormMixin(EinstellungenMixin):
    register = "briefbogen"
    model = BriefbogenElement
    form_class = BriefbogenElementForm
    template_name = "einstellungen/briefbogen_form.html"
    success_url = reverse_lazy("einstellungen:briefbogen")

    def form_valid(self, form):
        messages.success(self.request, "Briefbogen-Element gespeichert.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["bild_felder"] = BriefbogenElementForm.BILD_FELDER
        kontext["text_felder"] = BriefbogenElementForm.TEXT_FELDER
        return kontext


class BriefbogenNeuView(BriefbogenFormMixin, CreateView):
    pass


class BriefbogenBearbeitenView(BriefbogenFormMixin, UpdateView):
    pass


class BriefbogenLoeschenView(AdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        get_object_or_404(BriefbogenElement, pk=pk).delete()
        messages.success(request, "Briefbogen-Element gelöscht.")
        return redirect("einstellungen:briefbogen")


class BriefbogenVorschauView(AdminRequiredMixin, View):
    """PDF-Vorschau: leere Seite nur mit den Briefbogen-Elementen."""

    def get(self, request):
        from belege.pdf import briefbogen_vorschau

        antwort = HttpResponse(briefbogen_vorschau(), content_type="application/pdf")
        antwort["Content-Disposition"] = 'inline; filename="briefbogen-vorschau.pdf"'
        return antwort


class LizenzListeView(EinstellungenMixin, ListView):
    register = "lizenzen"
    model = Lizenz
    context_object_name = "lizenzen"
    template_name = "einstellungen/lizenz_liste.html"


class LizenzFormMixin(EinstellungenMixin):
    register = "lizenzen"
    model = Lizenz
    form_class = LizenzForm
    template_name = "einstellungen/lizenz_form.html"
    success_url = reverse_lazy("einstellungen:lizenzen")

    def form_valid(self, form):
        messages.success(self.request, "Lizenz gespeichert.")
        return super().form_valid(form)


class LizenzNeuView(LizenzFormMixin, CreateView):
    def get_initial(self):
        return {"gueltig_ab": timezone.localdate(), "module": ["warenwirtschaft"]}


class LizenzBearbeitenView(LizenzFormMixin, UpdateView):
    pass


class LizenzLoeschenView(AdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        get_object_or_404(Lizenz, pk=pk).delete()
        messages.success(request, "Lizenz gelöscht.")
        return redirect("einstellungen:lizenzen")
