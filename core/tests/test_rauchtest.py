"""Rauchtest: Alle Menüseiten laden für Administratoren mit gültiger Lizenz ohne Fehler."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.navigation import MENUE, Eintrag
from einstellungen.models import Lizenz

User = get_user_model()


def alle_eintraege():
    for e in MENUE:
        yield from ([e] if isinstance(e, Eintrag) else e.kinder)


@override_settings(LIZENZ_PRUEFUNG=True)
class RauchTests(TestCase):
    def test_alle_menuepunkte_sind_verlinkbar_und_laden(self):
        Lizenz.objects.create(referenz="Test", gueltig_ab=timezone.localdate(), module=["warenwirtschaft"])
        self.client.force_login(User.objects.create_superuser("admin", password="Sehr-geheim-2026"))
        for eintrag in alle_eintraege():
            antwort = self.client.get(reverse(eintrag.url_name))
            self.assertEqual(antwort.status_code, 200, eintrag.url_name)
        menue = self.client.get(reverse("core:dashboard")).context["navigation"]
        gruppen = [k for m in menue for k in (m.get("kinder") or [m])]
        self.assertTrue(all(k["verfuegbar"] for k in gruppen), "ein Menüpunkt ist noch ausgegraut")
