"""Benutzer- und Gruppenverwaltung (nur für Administratoren)."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView
from django.contrib.auth.models import Group
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from .forms import AnmeldeForm, BenutzerForm, GruppeForm
from .mixins import AdminRequiredMixin
from .modules import AKTION_SCHREIBEN, APP_LABEL, MODULE

User = get_user_model()


# ---------------------------------------------------------------------------
# Benutzer
# ---------------------------------------------------------------------------


class BenutzerListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "accounts/benutzer_liste.html"
    context_object_name = "benutzer"
    extra_context = {"seitentitel": "Benutzer"}

    def get_queryset(self):
        return User.objects.prefetch_related("groups").order_by("username")


class BenutzerFormMixin:
    form_class = BenutzerForm
    template_name = "accounts/benutzer_form.html"
    success_url = reverse_lazy("accounts:benutzer_liste")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["angemeldeter_benutzer"] = self.request.user
        return kwargs


class BenutzerCreateView(
    AdminRequiredMixin, BenutzerFormMixin, SuccessMessageMixin, CreateView
):
    model = User
    success_message = "Benutzer angelegt."
    extra_context = {"seitentitel": "Neuer Benutzer"}


class BenutzerUpdateView(
    AdminRequiredMixin, BenutzerFormMixin, SuccessMessageMixin, UpdateView
):
    model = User
    success_message = "Benutzer aktualisiert."

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["seitentitel"] = self.object.anzeigename
        return kontext


class BenutzerDeaktivierenView(AdminRequiredMixin, View):
    """Deaktiviert ein Konto. Benutzer werden nie gelöscht, damit Belege und
    Lagerbuchungen weiterhin ihren Bearbeiter nennen können."""

    http_method_names = ["post"]

    def post(self, request, pk):
        benutzer = get_object_or_404(User, pk=pk)
        if benutzer.pk == request.user.pk:
            messages.error(request, "Sie können das eigene Konto nicht deaktivieren.")
        else:
            benutzer.is_active = False
            benutzer.save(update_fields=["is_active"])
            messages.success(request, "Benutzer deaktiviert.")
        return redirect("accounts:benutzer_liste")


# ---------------------------------------------------------------------------
# Gruppen und Rechte
# ---------------------------------------------------------------------------


def rechte_zusammenfassung(gruppe) -> list[str]:
    """Kurzbeschreibung der Rechte, z. B. ["Artikel (Schreiben)", "Kunden (Lesen)"]."""
    codenames = {
        recht.codename
        for recht in gruppe.permissions.all()
        if recht.content_type.app_label == APP_LABEL
    }
    zeilen = []
    for modul, label in MODULE.items():
        if f"{modul}_{AKTION_SCHREIBEN}" in codenames:
            zeilen.append(f"{label} (Schreiben)")
        elif f"{modul}_lesen" in codenames:
            zeilen.append(f"{label} (Lesen)")
    return zeilen


class GruppeListView(AdminRequiredMixin, ListView):
    model = Group
    template_name = "accounts/gruppe_liste.html"
    context_object_name = "gruppen"
    extra_context = {"seitentitel": "Gruppen und Rechte"}

    def get_queryset(self):
        return (
            Group.objects.annotate(anzahl_benutzer=Count("user"))
            .prefetch_related("permissions__content_type")
            .order_by("name")
        )

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        for gruppe in kontext["gruppen"]:
            gruppe.rechte_text = ", ".join(rechte_zusammenfassung(gruppe))
        return kontext


class GruppeFormMixin:
    form_class = GruppeForm
    template_name = "accounts/gruppe_form.html"
    success_url = reverse_lazy("accounts:gruppe_liste")


class GruppeCreateView(
    AdminRequiredMixin, GruppeFormMixin, SuccessMessageMixin, CreateView
):
    model = Group
    success_message = "Gruppe gespeichert."
    extra_context = {"seitentitel": "Neue Gruppe"}


class GruppeUpdateView(
    AdminRequiredMixin, GruppeFormMixin, SuccessMessageMixin, UpdateView
):
    model = Group
    success_message = "Gruppe gespeichert."

    def get_context_data(self, **kwargs):
        kontext = super().get_context_data(**kwargs)
        kontext["seitentitel"] = self.object.name
        return kontext


class GruppeLoeschenView(AdminRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request, pk):
        gruppe = get_object_or_404(Group, pk=pk)
        gruppe.delete()
        messages.success(request, "Gruppe gelöscht.")
        return redirect("accounts:gruppe_liste")


class AnmeldeView(LoginView):
    """Anmeldeseite mit optionalem Firmenlogo (hochgeladen unter Einstellungen › Firma)."""

    template_name = "accounts/login.html"
    authentication_form = AnmeldeForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        from einstellungen.models import Firma

        kontext = super().get_context_data(**kwargs)
        kontext["hat_logo"] = bool(Firma.holen().portal_logo)
        return kontext


def anmeldelogo(request):
    """Liefert das Logo der Anmeldeseite. Öffentlich, denn die Anmeldeseite wird ohne Login angezeigt."""
    import mimetypes

    from django.http import FileResponse, Http404

    from einstellungen.models import Firma

    logo = Firma.holen().portal_logo
    if not logo:
        raise Http404
    try:
        datei = logo.open("rb")
    except FileNotFoundError:
        raise Http404
    antwort = FileResponse(datei, content_type=mimetypes.guess_type(logo.name)[0] or "image/png")
    antwort["Cache-Control"] = "public, max-age=300"
    # SVG darf auch bei direktem Aufruf nichts ausführen.
    antwort["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; sandbox"
    antwort["X-Content-Type-Options"] = "nosniff"
    return antwort
