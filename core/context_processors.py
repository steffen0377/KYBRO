from .navigation import baue_menue

BETROFFENE_BEREICHE = {"belege", "lager", "stammdaten"}
BETROFFENE_SEITEN = {"einstellungen:nummernkreise", "einstellungen:live"}


def navigation(request):
    """Stellt das Seitenmenü und den Betriebsmodus (Testbetrieb-Hinweis) für alle Templates bereit."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    from einstellungen.models import Firma

    aufgeloest = getattr(request, "resolver_match", None)
    aktuelle_view = aufgeloest.view_name if aufgeloest else ""
    testbetrieb = not Firma.objects.filter(pk=1, betriebsmodus=Firma.Betrieb.LIVE).exists()
    # Der Hinweis erscheint nur dort, wo der Wechsel in den Live-Betrieb Daten löscht
    # (Belege, Lager, Stammdaten, Nummernkreise); nicht z. B. in Personal oder bei den Firmeneinstellungen.
    bereich = aktuelle_view.split(":")[0] if ":" in aktuelle_view else ""
    betroffen = bereich in BETROFFENE_BEREICHE or aktuelle_view in BETROFFENE_SEITEN
    return {
        "navigation": baue_menue(user, aktuelle_view),
        "testbetrieb": testbetrieb,
        "testdaten_hinweis": testbetrieb and betroffen,
    }
