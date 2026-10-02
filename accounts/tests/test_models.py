from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from accounts.modules import MODULE, alle_rechte, recht_codename

User = get_user_model()


def gruppe_mit_rechten(name, *codenames):
    gruppe = Group.objects.create(name=name)
    gruppe.permissions.set(
        Permission.objects.filter(
            content_type__app_label="accounts", codename__in=codenames
        )
    )
    return gruppe


class ModulrechtTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("anna", password="geheim-1234")

    def test_fuer_jedes_modul_gibt_es_zwei_rechte(self):
        self.assertEqual(len(alle_rechte()), 2 * len(MODULE))
        vorhanden = set(
            Permission.objects.filter(content_type__app_label="accounts").values_list(
                "codename", flat=True
            )
        )
        for modul in MODULE:
            self.assertIn(f"{modul}_lesen", vorhanden)
            self.assertIn(f"{modul}_schreiben", vorhanden)

    def test_ohne_gruppe_kein_zugriff(self):
        self.assertFalse(self.user.hat_modulrecht("artikel", "lesen"))
        self.assertFalse(self.user.hat_modulrecht("artikel", "schreiben"))

    def test_leserecht_erlaubt_nur_lesen(self):
        self.user.groups.add(gruppe_mit_rechten("Lesen", "artikel_lesen"))
        self.assertTrue(self.user.hat_modulrecht("artikel", "lesen"))
        self.assertFalse(self.user.hat_modulrecht("artikel", "schreiben"))

    def test_schreibrecht_schliesst_lesen_ein(self):
        self.user.groups.add(gruppe_mit_rechten("Schreiben", "artikel_schreiben"))
        self.assertTrue(self.user.hat_modulrecht("artikel", "schreiben"))
        self.assertTrue(self.user.hat_modulrecht("artikel", "lesen"))

    def test_recht_gilt_nur_fuer_das_eigene_modul(self):
        self.user.groups.add(gruppe_mit_rechten("Nur Artikel", "artikel_schreiben"))
        self.assertFalse(self.user.hat_modulrecht("kunden", "lesen"))

    def test_rechte_mehrerer_gruppen_addieren_sich(self):
        self.user.groups.add(
            gruppe_mit_rechten("A", "artikel_lesen"),
            gruppe_mit_rechten("B", "kunden_schreiben"),
        )
        self.assertTrue(self.user.hat_modulrecht("artikel", "lesen"))
        self.assertTrue(self.user.hat_modulrecht("kunden", "schreiben"))

    def test_administrator_hat_immer_vollen_zugriff(self):
        admin = User.objects.create_superuser("admin", password="geheim-1234")
        for modul in MODULE:
            self.assertTrue(admin.hat_modulrecht(modul, "schreiben"))

    def test_inaktiver_benutzer_hat_keinen_zugriff(self):
        admin = User.objects.create_superuser("alt", password="geheim-1234")
        admin.is_active = False
        admin.save()
        self.assertFalse(admin.hat_modulrecht("artikel", "lesen"))

    def test_unbekanntes_modul_ist_ein_programmierfehler(self):
        with self.assertRaises(KeyError):
            self.user.hat_modulrecht("gibt-es-nicht", "lesen")
        with self.assertRaises(KeyError):
            recht_codename("gibt-es-nicht", "lesen")

    def test_unbekannte_aktion_ist_ein_programmierfehler(self):
        with self.assertRaises(ValueError):
            self.user.hat_modulrecht("artikel", "loeschen")


class BenutzerTests(TestCase):
    def test_anzeigename_nutzt_vollen_namen_sonst_benutzernamen(self):
        mit_name = User.objects.create_user(
            "mm", password="geheim-1234", first_name="Max", last_name="Muster"
        )
        ohne_name = User.objects.create_user("xx", password="geheim-1234")
        self.assertEqual(mit_name.anzeigename, "Max Muster")
        self.assertEqual(ohne_name.anzeigename, "xx")

    def test_anmeldequelle_ist_standardmaessig_lokal(self):
        self.assertEqual(
            User.objects.create_user("lokal", password="geheim-1234").auth_source,
            "local",
        )
