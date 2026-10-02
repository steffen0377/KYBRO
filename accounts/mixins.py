"""Zugriffsschutz für Views.

``ModulRechtMixin``  - Zugriff nur mit Modulrecht (Lesen bzw. Schreiben).
``AdminRequiredMixin`` - Zugriff nur für Administratoren.

Nicht angemeldete Besucher werden auf die Anmeldeseite geleitet, angemeldete
Benutzer ohne Berechtigung erhalten die Fehlerseite 403.
"""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.core.exceptions import ImproperlyConfigured, PermissionDenied

from .modules import AKTION_LESEN, AKTION_SCHREIBEN, LIZENZ_MODUL

LESENDE_METHODEN = ("GET", "HEAD", "OPTIONS")


class ModulRechtMixin(LoginRequiredMixin):
    """Verlangt das Recht auf ``modul``.

    Lesende Anfragen (GET, HEAD, OPTIONS) brauchen das Leserecht, alle
    anderen das Schreibrecht. Eine View kann ``get_aktion()`` überschreiben,
    wenn ein GET-Aufruf bereits etwas ändert oder umgekehrt.
    """

    modul: str | None = None

    def get_modul(self) -> str:
        if not self.modul:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} braucht das Attribut 'modul'."
            )
        return self.modul

    def get_aktion(self) -> str:
        if self.request.method in LESENDE_METHODEN:
            return AKTION_LESEN
        return AKTION_SCHREIBEN

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.hat_modulrecht(
            self.get_modul(), self.get_aktion()
        ):
            raise PermissionDenied("Ihnen fehlt die Berechtigung für dieses Modul.")
        lizenzmodul = LIZENZ_MODUL.get(self.modul or "")
        if request.user.is_authenticated and lizenzmodul and settings.LIZENZ_PRUEFUNG:
            from einstellungen.lizenzen import modul_lizenziert, modulname

            if not modul_lizenziert(lizenzmodul):
                return render(request, "402.html", {"modulname": modulname(lizenzmodul)}, status=402)
        # Nicht angemeldete Besucher behandelt LoginRequiredMixin.
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(LoginRequiredMixin):
    """Verlangt einen aktiven Administrator (``is_superuser``)."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.ist_admin:
            raise PermissionDenied("Diese Funktion ist nur für Administratoren.")
        return super().dispatch(request, *args, **kwargs)
