"""Seitenmenü der Anwendung.

Das Menü ist hier als Daten beschrieben und wird je Anfrage für den
angemeldeten Benutzer ausgewertet:

* Einträge mit ``modul`` erscheinen nur, wenn der Benutzer das Leserecht hat.
* Einträge mit ``nur_admin`` erscheinen nur für Administratoren.
* Eine Gruppe erscheint nur, wenn sie mindestens einen sichtbaren Eintrag hat.
* Einträge, deren URL noch nicht existiert (Modul noch nicht umgesetzt),
  werden ausgegraut und ohne Link angezeigt.
"""

from dataclasses import dataclass, field

from django.urls import NoReverseMatch, reverse

from accounts.modules import AKTION_LESEN


@dataclass(frozen=True)
class Eintrag:
    label: str
    icon: str
    url_name: str
    # Aktiv, wenn der Name der aktuellen View mit diesem Präfix beginnt.
    praefix: str = ""
    modul: str | None = None
    nur_admin: bool = False
    # Nur für Benutzer, die mit einem Mitarbeiter verknüpft sind (Self-Service).
    nur_mitarbeiter: bool = False


@dataclass(frozen=True)
class Gruppe:
    id: str
    label: str
    icon: str
    kinder: tuple[Eintrag, ...] = field(default_factory=tuple)
    nur_admin: bool = False
    # Beschriftung ist der Name des angemeldeten Benutzers.
    benutzername: bool = False


MENUE = (
    Gruppe(
        "benutzer",
        "",
        "bi-person-circle",
        (Eintrag("Meine Zeiten", "bi-clock-history", "personal:meine_zeiten", "personal:mein", nur_mitarbeiter=True),),
        benutzername=True,
    ),
    Eintrag("Dashboard", "bi-speedometer2", "core:dashboard", praefix="core:dashboard"),
    Eintrag("Artikel", "bi-box-seam", "stammdaten:artikel_liste", "stammdaten:artikel", "artikel"),
    Eintrag("Kategorien", "bi-tags", "stammdaten:kategorien_liste", "stammdaten:kategorien", "kategorien"),
    Eintrag("Lager", "bi-archive", "lager:uebersicht", "lager:", "lager"),
    Eintrag("Kunden", "bi-people", "stammdaten:kunden_liste", "stammdaten:kunden", "kunden"),
    Eintrag("Kalender", "bi-calendar3", "kalender:monat", "kalender:", "kalender"),
    Gruppe(
        "verkauf",
        "Verkauf",
        "bi-cart",
        (
            Eintrag("Angebote", "bi-file-earmark-text", "belege:angebote_liste", "belege:angebote", "angebote"),
            Eintrag("Aufträge", "bi-clipboard-check", "belege:auftraege_liste", "belege:auftraege", "auftraege"),
            Eintrag("Rechnungen", "bi-receipt", "belege:rechnungen_liste", "belege:rechnungen", "rechnungen"),
            Eintrag("Abonnements", "bi-repeat", "belege:abos_liste", "belege:abos", "abos"),
        ),
    ),
    Gruppe(
        "einkauf",
        "Einkauf",
        "bi-bag",
        (Eintrag("Lieferanten", "bi-truck", "stammdaten:lieferanten_liste", "stammdaten:lieferanten", "lieferanten"),),
    ),
    Gruppe(
        "personal",
        "Personal",
        "bi-person-badge",
        (
            Eintrag("Mitarbeiter", "bi-people", "personal:mitarbeiter_liste", "personal:mitarbeiter", "personal"),
            Eintrag("Anwesenheit", "bi-calendar-check", "personal:anwesenheit", "personal:anwesenheit", "personal"),
            Eintrag("Urlaub", "bi-sun", "personal:urlaub_liste", "personal:urlaub", "personal"),
            Eintrag("Über-/Fehlstunden", "bi-plus-slash-minus", "personal:stunden_liste", "personal:stunden", "personal"),
        ),
    ),
    Gruppe(
        "einstellungen",
        "Einstellungen",
        "bi-gear",
        (
            Eintrag("Benutzer", "bi-person", "accounts:benutzer_liste", "accounts:benutzer", nur_admin=True),
            Eintrag("Gruppen und Rechte", "bi-shield-lock", "accounts:gruppe_liste", "accounts:gruppe", nur_admin=True),
            Eintrag("Personal", "bi-person-badge", "personal:einstellungen", "personal:einstellungen", nur_admin=True),
            Eintrag("Firma und Dokumente", "bi-building-gear", "einstellungen:firma", "einstellungen:", nur_admin=True),
        ),
        nur_admin=True,
    ),
)


def _hat_mitarbeiter(user) -> bool:
    from personal.models import Mitarbeiter

    return Mitarbeiter.objects.filter(benutzer=user).exists()


def _sichtbar(element, user) -> bool:
    if element.nur_admin and not user.ist_admin:
        return False
    if getattr(element, "nur_mitarbeiter", False) and not _hat_mitarbeiter(user):
        return False
    modul = getattr(element, "modul", None)
    if modul and not user.hat_modulrecht(modul, AKTION_LESEN):
        return False
    return True


def _eintrag(eintrag: Eintrag, aktuelle_view: str) -> dict:
    try:
        url = reverse(eintrag.url_name)
    except NoReverseMatch:
        url = None
    praefix = eintrag.praefix or eintrag.url_name
    return {
        "label": eintrag.label,
        "icon": eintrag.icon,
        "url": url,
        "verfuegbar": url is not None,
        "aktiv": url is not None and aktuelle_view.startswith(praefix),
    }


def baue_menue(user, aktuelle_view: str) -> list[dict]:
    """Liefert das Menü für ``user`` als Liste von Dictionaries für das Template."""
    ergebnis = []
    for element in MENUE:
        if not _sichtbar(element, user):
            continue
        if isinstance(element, Eintrag):
            ergebnis.append({"typ": "eintrag", **_eintrag(element, aktuelle_view)})
            continue
        kinder = [
            _eintrag(kind, aktuelle_view)
            for kind in element.kinder
            if _sichtbar(kind, user)
        ]
        if not kinder:
            continue
        ergebnis.append(
            {
                "typ": "gruppe",
                "id": element.id,
                "label": user.anzeigename if element.benutzername else element.label,
                "icon": element.icon,
                "kinder": kinder,
                "aktiv": any(kind["aktiv"] for kind in kinder),
            }
        )
    return ergebnis
