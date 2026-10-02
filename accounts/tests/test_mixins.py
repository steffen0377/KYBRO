from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.views import View

from accounts.mixins import AdminRequiredMixin, ModulRechtMixin

User = get_user_model()


class ArtikelAnsicht(ModulRechtMixin, View):
    modul = "artikel"

    def get(self, request):
        return HttpResponse("gelesen")

    def post(self, request):
        return HttpResponse("geschrieben")


class OhneModulAnsicht(ModulRechtMixin, View):
    def get(self, request):
        return HttpResponse("nie erreicht")


class VerwaltungAnsicht(AdminRequiredMixin, View):
    def get(self, request):
        return HttpResponse("verwaltet")


def benutzer_mit(*codenames):
    benutzer = User.objects.create_user(f"u{User.objects.count()}", password="geheim-1234")
    if codenames:
        gruppe = Group.objects.create(name=f"g{Group.objects.count()}")
        gruppe.permissions.set(
            Permission.objects.filter(
                content_type__app_label="accounts", codename__in=codenames
            )
        )
        benutzer.groups.add(gruppe)
    return benutzer


class ModulRechtMixinTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def aufruf(self, view, methode, user):
        request = getattr(self.rf, methode)("/test/")
        request.user = user
        return view.as_view()(request)

    def test_anonym_wird_zur_anmeldung_geleitet(self):
        antwort = self.aufruf(ArtikelAnsicht, "get", AnonymousUser())
        self.assertEqual(antwort.status_code, 302)
        self.assertTrue(antwort.url.startswith(reverse("accounts:login")))

    def test_ohne_recht_ist_der_zugriff_verboten(self):
        with self.assertRaises(PermissionDenied):
            self.aufruf(ArtikelAnsicht, "get", benutzer_mit())

    def test_leserecht_erlaubt_get_aber_nicht_post(self):
        user = benutzer_mit("artikel_lesen")
        self.assertEqual(self.aufruf(ArtikelAnsicht, "get", user).content, b"gelesen")
        with self.assertRaises(PermissionDenied):
            self.aufruf(ArtikelAnsicht, "post", user)

    def test_schreibrecht_erlaubt_get_und_post(self):
        user = benutzer_mit("artikel_schreiben")
        self.assertEqual(self.aufruf(ArtikelAnsicht, "get", user).content, b"gelesen")
        self.assertEqual(self.aufruf(ArtikelAnsicht, "post", user).content, b"geschrieben")

    def test_recht_auf_anderes_modul_hilft_nicht(self):
        with self.assertRaises(PermissionDenied):
            self.aufruf(ArtikelAnsicht, "get", benutzer_mit("kunden_schreiben"))

    def test_administrator_darf_alles(self):
        admin = User.objects.create_superuser("admin", password="geheim-1234")
        self.assertEqual(self.aufruf(ArtikelAnsicht, "post", admin).content, b"geschrieben")

    def test_view_ohne_modul_ist_ein_konfigurationsfehler(self):
        with self.assertRaises(ImproperlyConfigured):
            self.aufruf(OhneModulAnsicht, "get", benutzer_mit())


class AdminRequiredMixinTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def aufruf(self, user):
        request = self.rf.get("/test/")
        request.user = user
        return VerwaltungAnsicht.as_view()(request)

    def test_anonym_wird_zur_anmeldung_geleitet(self):
        self.assertEqual(self.aufruf(AnonymousUser()).status_code, 302)

    def test_normaler_benutzer_ist_ausgeschlossen_auch_mit_allen_modulrechten(self):
        alle = [p.codename for p in Permission.objects.filter(content_type__app_label="accounts")]
        with self.assertRaises(PermissionDenied):
            self.aufruf(benutzer_mit(*alle))

    def test_administrator_hat_zugriff(self):
        admin = User.objects.create_superuser("admin", password="geheim-1234")
        self.assertEqual(self.aufruf(admin).content, b"verwaltet")
