"""Rauchtest: Alle Menüseiten laden für Administratoren mit gültiger Lizenz ohne Fehler."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.navigation import MENUE, Abschnitt, Eintrag
from einstellungen.models import Lizenz

User = get_user_model()


def alle_eintraege():
    for e in MENUE:
        if isinstance(e, Abschnitt):
            continue
        yield from (k for k in ([e] if isinstance(e, Eintrag) else e.kinder) if not k.post)


@override_settings(LIZENZ_PRUEFUNG=True)
class RauchTests(TestCase):
    def test_alle_menuepunkte_sind_verlinkbar_und_laden(self):
        Lizenz.objects.create(referenz="Test", gueltig_ab=timezone.localdate(), module=["warenwirtschaft"])
        admin = User.objects.create_superuser("admin", password="Sehr-geheim-2026")
        # "Meine Zeiten" gibt es nur für Benutzer, die mit einem Mitarbeiter verknüpft sind.
        from personal.models import Mitarbeiter

        Mitarbeiter.objects.create(vorname="Ad", nachname="Min", benutzer=admin)
        self.client.force_login(admin)
        for eintrag in alle_eintraege():
            antwort = self.client.get(reverse(eintrag.url_name))
            self.assertEqual(antwort.status_code, 200, eintrag.url_name)
        menue = self.client.get(reverse("core:dashboard")).context["navigation"]
        gruppen = [k for m in menue if m["typ"] != "abschnitt" for k in (m.get("kinder") or [m])]
        self.assertTrue(all(k["verfuegbar"] for k in gruppen), "ein Menüpunkt ist noch ausgegraut")
