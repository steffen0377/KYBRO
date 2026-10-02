from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from accounts.modules import MODULE

User = get_user_model()

PASSWORT = "Sehr-geheim-2026"


def codenames(gruppe):
    return set(
        gruppe.permissions.filter(content_type__app_label="accounts").values_list(
            "codename", flat=True
        )
    )


class GruppenVerwaltungTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PASSWORT)
        self.client.force_login(self.admin)

    def test_gruppe_mit_rechten_anlegen(self):
        antwort = self.client.post(
            reverse("accounts:gruppe_neu"),
            {"name": "Vertrieb", "lesen_artikel": "on", "schreiben_kunden": "on"},
        )
        self.assertRedirects(antwort, reverse("accounts:gruppe_liste"))
        gruppe = Group.objects.get(name="Vertrieb")
        self.assertEqual(
            codenames(gruppe), {"artikel_lesen", "kunden_lesen", "kunden_schreiben"}
        )

    def test_schreiben_ohne_lesen_vergibt_beide_rechte(self):
        self.client.post(
            reverse("accounts:gruppe_neu"), {"name": "Lager", "schreiben_lager": "on"}
        )
        self.assertEqual(
            codenames(Group.objects.get(name="Lager")), {"lager_lesen", "lager_schreiben"}
        )

    def test_gruppe_ohne_rechte_ist_erlaubt(self):
        self.client.post(reverse("accounts:gruppe_neu"), {"name": "Leer"})
        self.assertEqual(codenames(Group.objects.get(name="Leer")), set())

    def test_name_ist_pflicht_und_eindeutig(self):
        Group.objects.create(name="Vertrieb")
        leer = self.client.post(reverse("accounts:gruppe_neu"), {"name": ""})
        self.assertEqual(leer.status_code, 200)
        doppelt = self.client.post(reverse("accounts:gruppe_neu"), {"name": "Vertrieb"})
        self.assertEqual(doppelt.status_code, 200)
        self.assertEqual(Group.objects.filter(name="Vertrieb").count(), 1)

    def test_bearbeitungsformular_zeigt_vorhandene_rechte(self):
        gruppe = Group.objects.create(name="Gemischt")
        gruppe.permissions.set(
            Permission.objects.filter(
                content_type__app_label="accounts",
                codename__in=["artikel_lesen", "kunden_lesen", "kunden_schreiben"],
            )
        )
        formular = self.client.get(
            reverse("accounts:gruppe_bearbeiten", args=[gruppe.pk])
        ).context["form"]
        self.assertTrue(formular["lesen_artikel"].value())
        self.assertFalse(formular["schreiben_artikel"].value())
        self.assertTrue(formular["lesen_kunden"].value())
        self.assertTrue(formular["schreiben_kunden"].value())
        self.assertFalse(formular["lesen_lager"].value())

    def test_rechte_entfernen(self):
        gruppe = Group.objects.create(name="Gemischt")
        gruppe.permissions.set(
            Permission.objects.filter(
                content_type__app_label="accounts",
                codename__in=["artikel_lesen", "kunden_lesen", "kunden_schreiben"],
            )
        )
        self.client.post(
            reverse("accounts:gruppe_bearbeiten", args=[gruppe.pk]),
            {"name": "Gemischt", "lesen_artikel": "on"},
        )
        self.assertEqual(codenames(gruppe), {"artikel_lesen"})

    def test_fremde_rechte_bleiben_beim_speichern_erhalten(self):
        gruppe = Group.objects.create(name="Mit Admin-Recht")
        fremd = Permission.objects.get(codename="view_group")
        gruppe.permissions.add(fremd)
        self.client.post(
            reverse("accounts:gruppe_bearbeiten", args=[gruppe.pk]),
            {"name": "Mit Admin-Recht", "lesen_artikel": "on"},
        )
        self.assertIn(fremd, gruppe.permissions.all())
        self.assertEqual(codenames(gruppe), {"artikel_lesen"})

    def test_umbenennen(self):
        gruppe = Group.objects.create(name="Alt")
        self.client.post(
            reverse("accounts:gruppe_bearbeiten", args=[gruppe.pk]), {"name": "Neu"}
        )
        gruppe.refresh_from_db()
        self.assertEqual(gruppe.name, "Neu")

    def test_rechtetabelle_enthaelt_alle_module(self):
        antwort = self.client.get(reverse("accounts:gruppe_neu"))
        for label in MODULE.values():
            self.assertContains(antwort, label)
        self.assertEqual(len(antwort.context["form"].rechte_zeilen), len(MODULE))

    def test_liste_zeigt_benutzerzahl_und_rechte(self):
        gruppe = Group.objects.create(name="Vertrieb")
        gruppe.permissions.set(
            Permission.objects.filter(
                content_type__app_label="accounts",
                codename__in=["artikel_lesen", "kunden_lesen", "kunden_schreiben"],
            )
        )
        for name in ("anna", "bert"):
            User.objects.create_user(name, password=PASSWORT).groups.add(gruppe)
        antwort = self.client.get(reverse("accounts:gruppe_liste"))
        self.assertContains(antwort, "Vertrieb")
        self.assertContains(antwort, "Artikel (Lesen), Kunden (Schreiben)")
        eintrag = next(g for g in antwort.context["gruppen"] if g.pk == gruppe.pk)
        self.assertEqual(eintrag.anzahl_benutzer, 2)

    def test_gruppe_loeschen_laesst_benutzer_bestehen(self):
        gruppe = Group.objects.create(name="Weg")
        anna = User.objects.create_user("anna", password=PASSWORT)
        anna.groups.add(gruppe)
        antwort = self.client.post(reverse("accounts:gruppe_loeschen", args=[gruppe.pk]))
        self.assertRedirects(antwort, reverse("accounts:gruppe_liste"))
        self.assertFalse(Group.objects.filter(pk=gruppe.pk).exists())
        anna.refresh_from_db()
        self.assertEqual(anna.groups.count(), 0)

    def test_loeschen_geht_nur_per_post(self):
        gruppe = Group.objects.create(name="Bleibt")
        antwort = self.client.get(reverse("accounts:gruppe_loeschen", args=[gruppe.pk]))
        self.assertEqual(antwort.status_code, 405)
        self.assertTrue(Group.objects.filter(pk=gruppe.pk).exists())

    def test_gruppenrechte_wirken_auf_die_mitglieder(self):
        """Ende-zu-Ende: Recht in der Oberfläche vergeben, dann beim Benutzer prüfen."""
        self.client.post(
            reverse("accounts:gruppe_neu"),
            {"name": "Vertrieb", "lesen_artikel": "on", "schreiben_kunden": "on"},
        )
        anna = User.objects.create_user("anna", password=PASSWORT)
        anna.groups.add(Group.objects.get(name="Vertrieb"))
        self.assertTrue(anna.hat_modulrecht("artikel", "lesen"))
        self.assertFalse(anna.hat_modulrecht("artikel", "schreiben"))
        self.assertTrue(anna.hat_modulrecht("kunden", "schreiben"))
        self.assertFalse(anna.hat_modulrecht("lager", "lesen"))

    def test_unbekannte_gruppe_liefert_404(self):
        self.assertEqual(
            self.client.get(reverse("accounts:gruppe_bearbeiten", args=[9999])).status_code, 404
        )
