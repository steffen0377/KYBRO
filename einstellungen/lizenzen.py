"""Lizenzprüfung: Welche Module sind aktuell freigeschaltet?"""

from django.utils import timezone

from .models import LIZENZ_MODULE, Lizenz

KERNMODUL = "core"


def lizenzierte_module(heute=None) -> set[str]:
    heute = heute or timezone.localdate()
    gueltig = Lizenz.objects.filter(status=Lizenz.Status.AKTIV, gueltig_ab__lte=heute).exclude(gueltig_bis__lt=heute)
    return {modul for lizenz in gueltig for modul in lizenz.module}


def modul_lizenziert(code: str, heute=None) -> bool:
    return code == KERNMODUL or code in lizenzierte_module(heute)


def modulname(code: str) -> str:
    return LIZENZ_MODULE.get(code, code)
