from .navigation import baue_menue


def navigation(request):
    """Stellt das Seitenmenü für alle Templates bereit."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    aufgeloest = getattr(request, "resolver_match", None)
    aktuelle_view = aufgeloest.view_name if aufgeloest else ""
    return {"navigation": baue_menue(user, aktuelle_view)}
