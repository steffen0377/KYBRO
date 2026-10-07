from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

PASSWORT = "geheim-1234"


class AnmeldungTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("anna", password=PASSWORT)
        self.login_url = reverse("accounts:login")

    def test_anmeldeseite_wird_angezeigt(self):
        antwort = self.client.get(self.login_url)
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "KYBRO")
        self.assertContains(antwort, "Benutzername")

    def test_richtige_zugangsdaten_fuehren_zum_dashboard(self):
        antwort = self.client.post(
            self.login_url, {"username": "anna", "password": PASSWORT}
        )
        self.assertRedirects(antwort, reverse("core:dashboard"))

    def test_falsches_passwort_zeigt_fehlermeldung(self):
        antwort = self.client.post(
            self.login_url, {"username": "anna", "password": "falsch"}
        )
        self.assertEqual(antwort.status_code, 200)
        self.assertContains(antwort, "Benutzername oder Passwort ist falsch.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_inaktiver_benutzer_kann_sich_nicht_anmelden(self):
        self.user.is_active = False
        self.user.save()
        antwort = self.client.post(
            self.login_url, {"username": "anna", "password": PASSWORT}
        )
        self.assertContains(antwort, "Benutzername oder Passwort ist falsch.")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_angemeldeter_benutzer_wird_von_der_anmeldeseite_weitergeleitet(self):
        self.client.force_login(self.user)
        antwort = self.client.get(self.login_url)
        self.assertRedirects(antwort, reverse("core:dashboard"))

    def test_next_parameter_wird_beachtet(self):
        ziel = reverse("admin:index")
        antwort = self.client.post(
            self.login_url + "?next=" + ziel,
            {"username": "anna", "password": PASSWORT, "next": ziel},
        )
        self.assertRedirects(antwort, ziel, fetch_redirect_response=False)

    def test_fremde_weiterleitung_wird_ignoriert(self):
        antwort = self.client.post(
            self.login_url,
            {"username": "anna", "password": PASSWORT, "next": "https://boese.example/"},
        )
        self.assertRedirects(antwort, reverse("core:dashboard"))

    def test_abmelden_geht_nur_per_post(self):
        self.client.force_login(self.user)
        url = reverse("accounts:logout")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

        antwort = self.client.post(url)
        self.assertRedirects(antwort, self.login_url)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_sitzung_laeuft_nach_inaktivitaet_ab(self):
        from django.conf import settings

        self.assertEqual(settings.SESSION_COOKIE_AGE, 8 * 60 * 60)
        self.assertTrue(settings.SESSION_SAVE_EVERY_REQUEST)


class AnmeldeSeiteTests(TestCase):
    def test_untertitel_und_festes_logo(self):
        antwort = self.client.get(reverse("accounts:login"))
        self.assertContains(antwort, "das Firmenportal")
        self.assertContains(antwort, "core/img/logo.svg")
