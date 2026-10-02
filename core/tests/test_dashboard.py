from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def beschriftungen(menue):
    """Alle Beschriftungen des Menüs, Gruppen samt ihren Kindern."""
    ergebnis = []
    for punkt in menue:
        ergebnis.append(punkt["label"])
        ergebnis.extend(kind["label"] for kind in punkt.get("kinder", []))
    return ergebnis


class DashboardTests(TestCase):
    def test_ohne_anmeldung_geht_es_zur_anmeldeseite(self):
        antwort = self.client.get(reverse("core:dashboard"))
        self.assertRedirects(
            antwort, f"{reverse('accounts:login')}?next={reverse('core:dashboard')}"
        )

    def test_angemeldeter_benutzer_sieht_das_dashboard_mit_namen(self):
        user = User.objects.create_user(
            "anna", password="geheim-1234", first_name="Anna", last_name="Beispiel"
        )
        self.client.force_login(user)
        antwort = self.client.get(reverse("core:dashboard"))
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Willkommen, Anna Beispiel")
        self.assertContains(antwort, "Angemeldet als")

    def test_abmelden_ist_ein_formular_mit_csrf_schutz(self):
        self.client.force_login(User.objects.create_user("anna", password="geheim-1234"))
        antwort = self.client.get(reverse("core:dashboard"))
        self.assertContains(antwort, f'action="{reverse("accounts:logout")}"')
        self.assertContains(antwort, "csrfmiddlewaretoken")

    def test_statische_dateien_werden_eingebunden(self):
        self.client.force_login(User.objects.create_user("anna", password="geheim-1234"))
        antwort = self.client.get(reverse("core:dashboard"))
        self.assertContains(antwort, "core/vendor/bootstrap/css/bootstrap.min.css")
        self.assertContains(antwort, "core/css/style.css")


class MenueTests(TestCase):
    def menue_fuer(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("core:dashboard")).context["navigation"]

    def test_benutzer_ohne_rechte_sieht_nur_das_dashboard(self):
        user = User.objects.create_user("anna", password="geheim-1234")
        self.assertEqual(beschriftungen(self.menue_fuer(user)), ["Dashboard"])

    def test_leserecht_blendet_den_menuepunkt_ein(self):
        user = User.objects.create_user("anna", password="geheim-1234")
        gruppe = Group.objects.create(name="Lager")
        gruppe.permissions.set(
            Permission.objects.filter(
                content_type__app_label="accounts", codename="lager_lesen"
            )
        )
        user.groups.add(gruppe)
        self.assertEqual(beschriftungen(self.menue_fuer(user)), ["Dashboard", "Lager"])

    def test_gruppe_ohne_sichtbare_eintraege_wird_ausgeblendet(self):
        user = User.objects.create_user("anna", password="geheim-1234")
        self.assertNotIn("Verkauf", beschriftungen(self.menue_fuer(user)))

    def test_eintraege_ohne_vorhandene_seite_sind_ausgegraut(self):
        from unittest import mock

        from core import navigation

        menue = (navigation.Eintrag("Zukunft", "bi-x", "gibt:es_nicht", modul="artikel"),)
        admin = User.objects.create_superuser("admin", password="geheim-1234")
        with mock.patch.object(navigation, "MENUE", menue):
            eintrag = self.menue_fuer(admin)[0]
            self.assertFalse(eintrag["verfuegbar"])
            self.assertIsNone(eintrag["url"])
            antwort = self.client.get(reverse("core:dashboard"))
        self.assertContains(antwort, 'title="Folgt in einer späteren Phase"')

    def test_administrator_sieht_alle_bereiche(self):
        admin = User.objects.create_superuser("admin", password="geheim-1234")
        namen = beschriftungen(self.menue_fuer(admin))
        for erwartet in ("Dashboard", "Artikel", "Kunden", "Verkauf", "Einkauf", "Einstellungen"):
            self.assertIn(erwartet, namen)

    def test_dashboard_ist_als_aktiv_markiert(self):
        admin = User.objects.create_superuser("admin", password="geheim-1234")
        dashboard = self.menue_fuer(admin)[0]
        self.assertTrue(dashboard["aktiv"])
