from .navigation import baue_menue


def navigation(request):
    """Stellt das Seitenmenü und den Betriebsmodus (Testbetrieb-Hinweis) für alle Templates bereit."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    from einstellungen.models import Firma

    aufgeloest = getattr(request, "resolver_match", None)
    aktuelle_view = aufgeloest.view_name if aufgeloest else ""
    testbetrieb = not Firma.objects.filter(pk=1, betriebsmodus=Firma.Betrieb.LIVE).exists()
    return {"navigation": baue_menue(user, aktuelle_view), "testbetrieb": testbetrieb}
