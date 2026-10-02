from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

User = get_user_model()

PASSWORT = "Sehr-geheim-2026"


def formulardaten(**ueberschreibungen):
    daten = {
        "username": "neuer",
        "first_name": "Nina",
        "last_name": "Neu",
        "email": "nina@example.com",
        "password1": PASSWORT,
        "password2": PASSWORT,
        "rolle": "benutzer",
        "is_active": "on",
    }
    daten.update(ueberschreibungen)
    return {k: v for k, v in daten.items() if v is not None}


class ZugriffTests(TestCase):
    def test_ohne_anmeldung_geht_es_zur_anmeldeseite(self):
        url = reverse("accounts:benutzer_liste")
        self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_normaler_benutzer_erhaelt_403(self):
        user = User.objects.create_user("anna", password=PASSWORT)
        self.client.force_login(user)
        for name in ("benutzer_liste", "benutzer_neu", "gruppe_liste", "gruppe_neu"):
            antwort = self.client.get(reverse(f"accounts:{name}"))
            self.assertEqual(antwort.status_code, 403, name)
        self.assertContains(
            self.client.get(reverse("accounts:benutzer_liste")),
            "Zugriff verweigert",
            status_code=403,
        )

    def test_aenderungen_sind_fuer_normale_benutzer_gesperrt(self):
        anna = User.objects.create_user("anna", password=PASSWORT)
        andere = User.objects.create_user("bert", password=PASSWORT)
        self.client.force_login(anna)
        self.assertEqual(
            self.client.post(reverse("accounts:benutzer_deaktivieren", args=[andere.pk])).status_code,
            403,
        )
        andere.refresh_from_db()
        self.assertTrue(andere.is_active)

    def test_menuepunkte_der_verwaltung_sind_fuer_administratoren_verlinkt(self):
        admin = User.objects.create_superuser("admin", password=PASSWORT)
        self.client.force_login(admin)
        antwort = self.client.get(reverse("core:dashboard"))
        self.assertContains(antwort, f'href="{reverse("accounts:benutzer_liste")}"')
        self.assertContains(antwort, f'href="{reverse("accounts:gruppe_liste")}"')


class BenutzerVerwaltungTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PASSWORT)
        self.client.force_login(self.admin)

    def test_liste_zeigt_benutzer_rolle_gruppen_und_status(self):
        gruppe = Group.objects.create(name="Vertrieb")
        anna = User.objects.create_user("anna", password=PASSWORT, first_name="Anna")
        anna.groups.add(gruppe)
        inaktiv = User.objects.create_user("ehemalig", password=PASSWORT, is_active=False)
        antwort = self.client.get(reverse("accounts:benutzer_liste"))
        self.assertContains(antwort, "anna")
        self.assertContains(antwort, "Vertrieb")
        self.assertContains(antwort, "Administrator")
        self.assertContains(antwort, "Inaktiv")
        self.assertContains(antwort, reverse("accounts:benutzer_deaktivieren", args=[anna.pk]))
        self.assertNotContains(antwort, reverse("accounts:benutzer_deaktivieren", args=[inaktiv.pk]))
        # Das eigene Konto lässt sich nicht deaktivieren und hat daher keinen Knopf.
        self.assertNotContains(antwort, reverse("accounts:benutzer_deaktivieren", args=[self.admin.pk]))

    def test_benutzer_anlegen(self):
        gruppe = Group.objects.create(name="Vertrieb")
        antwort = self.client.post(
            reverse("accounts:benutzer_neu"), formulardaten(groups=[gruppe.pk])
        )
        self.assertRedirects(antwort, reverse("accounts:benutzer_liste"))
        neu = User.objects.get(username="neuer")
        self.assertEqual(neu.get_full_name(), "Nina Neu")
        self.assertFalse(neu.is_superuser)
        self.assertFalse(neu.is_staff)
        self.assertTrue(neu.is_active)
        self.assertEqual(list(neu.groups.all()), [gruppe])
        self.assertNotEqual(neu.password, PASSWORT)
        self.assertIsNotNone(authenticate(username="neuer", password=PASSWORT))

    def test_administrator_anlegen_setzt_superuser_und_staff(self):
        self.client.post(reverse("accounts:benutzer_neu"), formulardaten(rolle="administrator"))
        neu = User.objects.get(username="neuer")
        self.assertTrue(neu.is_superuser)
        self.assertTrue(neu.is_staff)

    def test_passwort_ist_beim_anlegen_pflicht(self):
        antwort = self.client.post(
            reverse("accounts:benutzer_neu"), formulardaten(password1="", password2="")
        )
        self.assertEqual(antwort.status_code, 200)
        self.assertFalse(User.objects.filter(username="neuer").exists())
        self.assertTrue(antwort.context["form"].errors["password1"])

    def test_verschiedene_passwoerter_werden_abgelehnt(self):
        antwort = self.client.post(
            reverse("accounts:benutzer_neu"), formulardaten(password2="Anders-2026-x")
        )
        self.assertContains(antwort, "Die beiden Passwörter stimmen nicht überein.")
        self.assertFalse(User.objects.filter(username="neuer").exists())

    def test_zu_kurzes_passwort_wird_abgelehnt(self):
        antwort = self.client.post(
            reverse("accounts:benutzer_neu"), formulardaten(password1="kurz1", password2="kurz1")
        )
        self.assertEqual(antwort.status_code, 200)
        self.assertTrue(antwort.context["form"].errors["password1"])
        self.assertFalse(User.objects.filter(username="neuer").exists())

    def test_passwort_gleich_benutzername_wird_abgelehnt(self):
        antwort = self.client.post(
            reverse("accounts:benutzer_neu"),
            formulardaten(username="petermueller", password1="petermueller", password2="petermueller"),
        )
        self.assertTrue(antwort.context["form"].errors["password1"])

    def test_zu_kurzer_benutzername_wird_abgelehnt(self):
        antwort = self.client.post(reverse("accounts:benutzer_neu"), formulardaten(username="ab"))
        self.assertContains(antwort, "mindestens 3 Zeichen")
        self.assertFalse(User.objects.filter(username="ab").exists())

    def test_doppelter_benutzername_wird_abgelehnt(self):
        User.objects.create_user("neuer", password=PASSWORT)
        antwort = self.client.post(reverse("accounts:benutzer_neu"), formulardaten())
        self.assertEqual(antwort.status_code, 200)
        self.assertTrue(antwort.context["form"].errors["username"])
        self.assertEqual(User.objects.filter(username="neuer").count(), 1)

    def test_bearbeiten_ohne_passwort_laesst_das_passwort_unveraendert(self):
        anna = User.objects.create_user("anna", password=PASSWORT)
        alter_hash = anna.password
        gruppe = Group.objects.create(name="Lager")
        antwort = self.client.post(
            reverse("accounts:benutzer_bearbeiten", args=[anna.pk]),
            formulardaten(username="anna", first_name="Anna", password1="", password2="", groups=[gruppe.pk]),
        )
        self.assertRedirects(antwort, reverse("accounts:benutzer_liste"))
        anna.refresh_from_db()
        self.assertEqual(anna.password, alter_hash)
        self.assertEqual(anna.first_name, "Anna")
        self.assertEqual(list(anna.groups.all()), [gruppe])

    def test_bearbeiten_mit_neuem_passwort_aendert_es(self):
        anna = User.objects.create_user("anna", password=PASSWORT)
        neues = "Ganz-neu-2027!"
        self.client.post(
            reverse("accounts:benutzer_bearbeiten", args=[anna.pk]),
            formulardaten(username="anna", password1=neues, password2=neues),
        )
        self.assertIsNone(authenticate(username="anna", password=PASSWORT))
        self.assertIsNotNone(authenticate(username="anna", password=neues))

    def test_bearbeitungsformular_zeigt_vorhandene_werte(self):
        gruppe = Group.objects.create(name="Lager")
        anna = User.objects.create_user("anna", password=PASSWORT, first_name="Anna")
        anna.groups.add(gruppe)
        antwort = self.client.get(reverse("accounts:benutzer_bearbeiten", args=[anna.pk]))
        formular = antwort.context["form"]
        self.assertEqual(formular["username"].value(), "anna")
        self.assertEqual(formular["rolle"].value(), "benutzer")
        self.assertEqual(list(formular["groups"].value()), [gruppe.pk])

    def test_rolle_wechseln(self):
        anna = User.objects.create_user("anna", password=PASSWORT)
        self.client.post(
            reverse("accounts:benutzer_bearbeiten", args=[anna.pk]),
            formulardaten(username="anna", password1="", password2="", rolle="administrator"),
        )
        anna.refresh_from_db()
        self.assertTrue(anna.is_superuser)
        self.assertTrue(anna.is_staff)

    def test_eigene_administratorrolle_laesst_sich_nicht_entziehen(self):
        antwort = self.client.post(
            reverse("accounts:benutzer_bearbeiten", args=[self.admin.pk]),
            formulardaten(username="admin", password1="", password2="", rolle="benutzer"),
        )
        self.assertContains(antwort, "nicht selbst")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_superuser)

    def test_eigenes_konto_laesst_sich_im_formular_nicht_deaktivieren(self):
        antwort = self.client.post(
            reverse("accounts:benutzer_bearbeiten", args=[self.admin.pk]),
            formulardaten(
                username="admin", password1="", password2="", rolle="administrator", is_active=None
            ),
        )
        self.assertContains(antwort, "nicht selbst")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_anderen_administrator_herabstufen_ist_erlaubt(self):
        zweiter = User.objects.create_superuser("zweiter", password=PASSWORT)
        self.client.post(
            reverse("accounts:benutzer_bearbeiten", args=[zweiter.pk]),
            formulardaten(username="zweiter", password1="", password2="", rolle="benutzer"),
        )
        zweiter.refresh_from_db()
        self.assertFalse(zweiter.is_superuser)
        self.assertFalse(zweiter.is_staff)

    def test_deaktivieren(self):
        anna = User.objects.create_user("anna", password=PASSWORT)
        antwort = self.client.post(reverse("accounts:benutzer_deaktivieren", args=[anna.pk]))
        self.assertRedirects(antwort, reverse("accounts:benutzer_liste"))
        anna.refresh_from_db()
        self.assertFalse(anna.is_active)
        self.assertIsNone(authenticate(username="anna", password=PASSWORT))

    def test_deaktivieren_geht_nur_per_post(self):
        anna = User.objects.create_user("anna", password=PASSWORT)
        antwort = self.client.get(reverse("accounts:benutzer_deaktivieren", args=[anna.pk]))
        self.assertEqual(antwort.status_code, 405)
        anna.refresh_from_db()
        self.assertTrue(anna.is_active)

    def test_eigenes_konto_laesst_sich_nicht_deaktivieren(self):
        User.objects.create_superuser("zweiter", password=PASSWORT)
        antwort = self.client.post(
            reverse("accounts:benutzer_deaktivieren", args=[self.admin.pk]), follow=True
        )
        self.assertContains(antwort, "nicht deaktivieren")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_unbekannter_benutzer_liefert_404(self):
        self.assertEqual(
            self.client.post(reverse("accounts:benutzer_deaktivieren", args=[9999])).status_code, 404
        )
