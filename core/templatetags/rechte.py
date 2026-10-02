from django import template

register = template.Library()


@register.filter
def darf(user, angabe: str) -> bool:
    """Prüft ein Modulrecht im Template: ``{% if user|darf:"artikel:schreiben" %}``."""
    modul, _, aktion = angabe.partition(":")
    return user.is_authenticated and user.hat_modulrecht(modul, aktion or "lesen")
