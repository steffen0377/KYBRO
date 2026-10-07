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


class AnmeldeLogoTests(TestCase):
    """Logo und Untertitel auf der Anmeldeseite."""

    def setUp(self):
        import tempfile

        from django.test import override_settings

        self._media = override_settings(MEDIA_ROOT=tempfile.mkdtemp())
        self._media.enable()
        self.addCleanup(self._media.disable)

    def _png(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        puffer = io.BytesIO()
        Image.new("RGB", (200, 80), (30, 60, 150)).save(puffer, "PNG")
        return SimpleUploadedFile("logo.png", puffer.getvalue(), content_type="image/png")

    def test_untertitel_immer_ohne_logo_ohne_bild(self):
        antwort = self.client.get(reverse("accounts:login"))
        self.assertContains(antwort, "das Firmenportal")
        self.assertNotContains(antwort, "anmelden/logo/")
        self.assertEqual(self.client.get(reverse("accounts:login_logo")).status_code, 404)

    def test_logo_wird_oeffentlich_angezeigt(self):
        from einstellungen.models import Firma

        firma = Firma.holen()
        firma.portal_logo = self._png()
        firma.save()
        antwort = self.client.get(reverse("accounts:login"))  # nicht angemeldet
        self.assertContains(antwort, reverse("accounts:login_logo"))
        bild = self.client.get(reverse("accounts:login_logo"))
        self.assertEqual(bild.status_code, 200)
        self.assertEqual(bild["Content-Type"], "image/png")
        self.assertTrue(b"".join(bild.streaming_content).startswith(b"\x89PNG"))

    def test_upload_ueber_firmeneinstellungen(self):
        from einstellungen.models import Firma

        admin = User.objects.create_superuser("admin", password="Sehr-geheim-2026")
        self.client.force_login(admin)
        antwort = self.client.post(reverse("einstellungen:firma"), {"firmenname": "BilSE", "portal_logo": self._png(),
                                                                     "land": "Deutschland", "standard_steuersatz": "19",
                                                                     "zahlungsziel_tage": "14", "praefix_angebot": "A",
                                                                     "praefix_auftrag": "AB", "praefix_rechnung": "R"})
        self.assertEqual(antwort.status_code, 302, getattr(antwort, "context", None) and antwort.context["form"].errors)
        self.assertTrue(Firma.holen().portal_logo)

    def test_nur_bilddateien(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        admin = User.objects.create_superuser("admin", password="Sehr-geheim-2026")
        self.client.force_login(admin)
        antwort = self.client.post(reverse("einstellungen:firma"), {
            "firmenname": "X", "portal_logo": SimpleUploadedFile("x.exe", b"MZ"), "land": "Deutschland",
            "standard_steuersatz": "19", "zahlungsziel_tage": "14", "praefix_angebot": "A", "praefix_auftrag": "AB",
            "praefix_rechnung": "R"})
        self.assertEqual(antwort.status_code, 200)


class AnmeldeLogoSvgTests(AnmeldeLogoTests):
    SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><rect width="100" height="40" fill="#123"/></svg>'

    def _firma_post(self, datei):
        admin = User.objects.create_superuser("admin", password="Sehr-geheim-2026")
        self.client.force_login(admin)
        return self.client.post(reverse("einstellungen:firma"), {
            "firmenname": "X", "portal_logo": datei, "land": "Deutschland", "standard_steuersatz": "19",
            "zahlungsziel_tage": "14", "praefix_angebot": "A", "praefix_auftrag": "AB", "praefix_rechnung": "R"})

    def test_svg_hochladen_und_ausliefern(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from einstellungen.models import Firma

        antwort = self._firma_post(SimpleUploadedFile("logo.svg", self.SVG, content_type="image/svg+xml"))
        self.assertEqual(antwort.status_code, 302)
        self.client.logout()
        bild = self.client.get(reverse("accounts:login_logo"))
        self.assertEqual(bild["Content-Type"], "image/svg+xml")
        self.assertIn("sandbox", bild["Content-Security-Policy"])
        self.assertEqual(bild["X-Content-Type-Options"], "nosniff")
        self.assertIn(b"<svg", b"".join(bild.streaming_content))
        self.assertContains(self.client.get(reverse("accounts:login")), reverse("accounts:login_logo"))

    def test_svg_mit_skript_abgelehnt(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        for boese in (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>',
            b'<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"><rect/></a></svg>',
        ):
            antwort = self._firma_post(SimpleUploadedFile("x.svg", boese, content_type="image/svg+xml"))
            self.assertEqual(antwort.status_code, 200)
            self.assertContains(antwort, "Skripte")
            self.client.logout()
            User.objects.all().delete()

    def test_kaputte_dateien_abgelehnt(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.assertEqual(self._firma_post(SimpleUploadedFile("x.svg", b"kein xml")).status_code, 200)
        self.client.logout()
        User.objects.all().delete()
        self.assertEqual(self._firma_post(SimpleUploadedFile("x.png", b"kein bild")).status_code, 200)
