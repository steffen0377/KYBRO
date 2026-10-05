import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from personal import services
from personal.models import Anwesenheit, Mitarbeiter, Urlaubsantrag, Urlaubsjahr, Vertrag

User = get_user_model()
PW = "Sehr-geheim-2026"
D = datetime.date


def mitarbeiter(**kw):
    daten = dict(vorname="Erika", nachname="Muster", eintrittsdatum=D(2020, 1, 1))
    daten.update(kw)
    return Mitarbeiter.objects.create(**daten)


def vertrag(m, **kw):
    daten = dict(gueltig_ab=D(2020, 1, 1), urlaubstage_pro_jahr=30)
    daten.update(kw)
    return Vertrag.objects.create(mitarbeiter=m, **daten)


class ModellTests(TestCase):
    def test_personalnummer(self):
        m = mitarbeiter()
        self.assertEqual(m.personalnummer, f"P-{m.pk:04d}")

    def test_unabhaengig_von_benutzer_und_verknuepfbar(self):
        m = mitarbeiter()
        self.assertIsNone(m.benutzer)
        u = User.objects.create_user("erika", password=PW)
        m.benutzer = u
        m.save()
        self.assertEqual(u.mitarbeiter, m)

    def test_vertraege_duerfen_sich_nicht_ueberschneiden(self):
        from django.core.exceptions import ValidationError

        m = mitarbeiter()
        vertrag(m, gueltig_ab=D(2020, 1, 1), gueltig_bis=D(2022, 12, 31))
        neu = Vertrag(mitarbeiter=m, gueltig_ab=D(2022, 6, 1))
        with self.assertRaises(ValidationError):
            neu.clean()
        Vertrag(mitarbeiter=m, gueltig_ab=D(2023, 1, 1)).clean()


class UrlaubServiceTests(TestCase):
    def setUp(self):
        self.m = mitarbeiter()
        vertrag(self.m)

    def test_anspruch_voll(self):
        self.assertEqual(services.urlaub_anspruch(self.m, 2026), Decimal("30"))

    def test_anspruch_anteilig_bei_eintritt(self):
        m = mitarbeiter(vorname="Neu", eintrittsdatum=D(2026, 7, 1))
        vertrag(m, gueltig_ab=D(2026, 7, 1), urlaubstage_pro_jahr=30)
        self.assertEqual(services.urlaub_anspruch(m, 2026), Decimal("15.0"))

    def test_manueller_anspruch_hat_vorrang(self):
        Urlaubsjahr.objects.create(mitarbeiter=self.m, jahr=2026, anspruch=Decimal("28"), uebertrag=Decimal("3"))
        k = services.urlaubskonto(self.m, 2026)
        self.assertEqual((k["anspruch"], k["uebertrag"], k["rest"]), (Decimal("28"), Decimal("3"), Decimal("31")))

    def test_nur_arbeitstage_zaehlen(self):
        # Mo 5.10.2026 bis So 11.10.2026 = 5 Arbeitstage
        Urlaubsantrag.objects.create(mitarbeiter=self.m, von=D(2026, 10, 5), bis=D(2026, 10, 11), status="genehmigt")
        k = services.urlaubskonto(self.m, 2026)
        self.assertEqual(k["genommen"], 5)
        self.assertEqual(k["rest"], Decimal("25"))

    def test_beantragt_zaehlt_nicht_als_genommen(self):
        Urlaubsantrag.objects.create(mitarbeiter=self.m, von=D(2026, 10, 5), bis=D(2026, 10, 6))
        k = services.urlaubskonto(self.m, 2026)
        self.assertEqual((k["genommen"], k["beantragt"], k["rest_nach_antraegen"]), (0, 2, Decimal("28")))

    def test_teilzeit_arbeitstage(self):
        m = mitarbeiter(vorname="Teil")
        vertrag(m, arbeitstage="0,2")
        self.assertEqual(len(services.arbeitstage(m, D(2026, 10, 5), D(2026, 10, 11))), 2)

    def test_antrag_ueber_jahreswechsel_wird_geteilt(self):
        Urlaubsantrag.objects.create(mitarbeiter=self.m, von=D(2026, 12, 28), bis=D(2027, 1, 5), status="genehmigt")
        self.assertEqual(services.urlaubskonto(self.m, 2026)["genommen"], 4)
        self.assertEqual(services.urlaubskonto(self.m, 2027)["genommen"], 3)

    def test_ueberschneidender_antrag_abgelehnt(self):
        from django.core.exceptions import ValidationError

        Urlaubsantrag.objects.create(mitarbeiter=self.m, von=D(2026, 10, 5), bis=D(2026, 10, 9))
        with self.assertRaises(ValidationError):
            Urlaubsantrag(mitarbeiter=self.m, von=D(2026, 10, 8), bis=D(2026, 10, 12)).clean()

    def test_monatsuebersicht(self):
        Urlaubsantrag.objects.create(mitarbeiter=self.m, von=D(2026, 10, 5), bis=D(2026, 10, 6), status="genehmigt")
        Anwesenheit.objects.create(mitarbeiter=self.m, datum=D(2026, 10, 7), status="krank")
        zellen = services.monatsuebersicht([self.m], 2026, 10)["zeilen"][0]["zellen"]
        self.assertEqual(zellen[4]["status"], "urlaub")
        self.assertEqual(zellen[6]["status"], "krank")
        self.assertEqual(zellen[10]["status"], "frei")  # Samstag


class ViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PW)
        self.client.force_login(self.admin)

    def test_mitarbeiter_anlegen_mit_login(self):
        u = User.objects.create_user("erika", password=PW)
        r = self.client.post(reverse("personal:mitarbeiter_neu"), {"vorname": "Erika", "nachname": "Muster", "benutzer": u.pk})
        m = Mitarbeiter.objects.get()
        self.assertRedirects(r, reverse("personal:mitarbeiter_detail", args=[m.pk]))
        self.assertEqual(m.benutzer, u)

    def test_benutzer_nur_einmal_verknuepfbar(self):
        u = User.objects.create_user("erika", password=PW)
        mitarbeiter(benutzer=u)
        r = self.client.post(reverse("personal:mitarbeiter_neu"), {"vorname": "X", "nachname": "Y", "benutzer": u.pk})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Mitarbeiter.objects.count(), 1)

    def test_vorbelegung_aus_benutzer(self):
        u = User.objects.create_user("erika", password=PW, first_name="Erika", last_name="Muster")
        r = self.client.get(reverse("personal:mitarbeiter_neu") + f"?benutzer={u.pk}")
        self.assertEqual(r.context["form"].initial["nachname"], "Muster")

    def test_seiten_laden(self):
        m = mitarbeiter()
        vertrag(m)
        for name, args in [
            ("mitarbeiter_liste", []), ("mitarbeiter_detail", [m.pk]), ("mitarbeiter_bearbeiten", [m.pk]),
            ("vertrag_neu", [m.pk]), ("urlaubsjahr", [m.pk, 2026]), ("anwesenheit", []), ("urlaub_liste", []), ("urlaub_neu", []),
        ]:
            self.assertEqual(self.client.get(reverse(f"personal:{name}", args=args)).status_code, 200, name)

    def test_vertrag_anlegen(self):
        m = mitarbeiter()
        r = self.client.post(reverse("personal:vertrag_neu", args=[m.pk]), {
            "gueltig_ab": "2026-01-01", "art": "vollzeit", "wochenstunden": "40", "arbeitstage": ["0", "1", "2", "3", "4"],
            "urlaubstage_pro_jahr": "30", "kuendigungsfrist": "4 Wochen",
        })
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        self.assertEqual(Vertrag.objects.get().arbeitstage, "0,1,2,3,4")

    def test_anwesenheit_zeitraum_nur_arbeitstage(self):
        m = mitarbeiter()
        vertrag(m)
        self.client.post(reverse("personal:anwesenheit"), {
            "mitarbeiter": m.pk, "datum": "2026-10-05", "datum_bis": "2026-10-11", "status": "krank",
        })
        self.assertEqual(Anwesenheit.objects.filter(mitarbeiter=m, status="krank").count(), 5)
        self.client.post(reverse("personal:anwesenheit"), {
            "mitarbeiter": m.pk, "datum": "2026-10-05", "datum_bis": "2026-10-11", "status": "krank", "entfernen": "on",
        })
        self.assertEqual(Anwesenheit.objects.count(), 0)

    def test_berufsschule_und_schulung(self):
        m = mitarbeiter()
        for status in ("berufsschule", "schulung"):
            r = self.client.post(reverse("personal:anwesenheit"), {"mitarbeiter": m.pk, "datum": "2026-10-05", "status": status})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(Anwesenheit.objects.get(mitarbeiter=m).status, status)

    def test_urlaub_eintragen_ist_genehmigt(self):
        m = mitarbeiter()
        self.client.post(reverse("personal:urlaub_neu"), {"mitarbeiter": m.pk, "von": "2026-10-05", "bis": "2026-10-06"})
        self.assertEqual(Urlaubsantrag.objects.get().status, "genehmigt")

    def test_genehmigen(self):
        m = mitarbeiter()
        a = Urlaubsantrag.objects.create(mitarbeiter=m, von=D(2026, 10, 5), bis=D(2026, 10, 6))
        self.client.post(reverse("personal:urlaub_entscheiden", args=[a.pk]), {"aktion": "genehmigen"})
        a.refresh_from_db()
        self.assertEqual((a.status, a.entschieden_von), ("genehmigt", self.admin))

    def test_loeschen(self):
        m = mitarbeiter()
        self.client.post(reverse("personal:mitarbeiter_loeschen", args=[m.pk]))
        self.assertFalse(Mitarbeiter.objects.exists())


class RechteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("erika", password=PW)
        self.client.force_login(self.user)

    def gruppe(self, *codenamen):
        g = Group.objects.create(name="Personal")
        g.permissions.set(Permission.objects.filter(codename__in=codenamen))
        self.user.groups.add(g)
        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_login(self.user)

    def test_ohne_recht_verboten(self):
        self.assertEqual(self.client.get(reverse("personal:mitarbeiter_liste")).status_code, 403)
        self.assertEqual(self.client.get(reverse("personal:anwesenheit")).status_code, 403)

    def test_lesen_ohne_schreiben(self):
        self.gruppe("personal_lesen")
        self.assertEqual(self.client.get(reverse("personal:mitarbeiter_liste")).status_code, 200)
        r = self.client.post(reverse("personal:mitarbeiter_neu"), {"vorname": "A", "nachname": "B"})
        self.assertEqual(r.status_code, 403)

    def test_selbstbedienung_nur_mit_verknuepfung(self):
        self.assertEqual(self.client.get(reverse("personal:meine_zeiten")).status_code, 403)
        m = mitarbeiter(benutzer=self.user)
        vertrag(m)
        self.assertEqual(self.client.get(reverse("personal:meine_zeiten")).status_code, 200)
        self.assertEqual(self.client.get(reverse("personal:mitarbeiter_liste")).status_code, 403)

    def test_eigenen_urlaub_beantragen_und_zurueckziehen(self):
        m = mitarbeiter(benutzer=self.user)
        vertrag(m)
        self.client.post(reverse("personal:mein_urlaub_neu"), {"von": "2026-10-05", "bis": "2026-10-06"})
        a = Urlaubsantrag.objects.get()
        self.assertEqual((a.mitarbeiter, a.status), (m, "beantragt"))
        self.client.post(reverse("personal:mein_urlaub_stornieren", args=[a.pk]))
        a.refresh_from_db()
        self.assertEqual(a.status, "storniert")

    def test_eigene_anwesenheit_nur_fuer_sich(self):
        m = mitarbeiter(benutzer=self.user)
        anderer = mitarbeiter(vorname="Anderer")
        self.client.post(reverse("personal:meine_zeiten"), {
            "datum": "2026-10-05", "status": "homeoffice", "mitarbeiter": anderer.pk,
        })
        self.assertEqual(Anwesenheit.objects.get().mitarbeiter, m)

    def test_fremden_antrag_nicht_zurueckziehbar(self):
        mitarbeiter(benutzer=self.user)
        fremd = mitarbeiter(vorname="Fremd")
        a = Urlaubsantrag.objects.create(mitarbeiter=fremd, von=D(2026, 10, 5), bis=D(2026, 10, 6))
        self.assertEqual(self.client.post(reverse("personal:mein_urlaub_stornieren", args=[a.pk])).status_code, 404)

    def test_menue_meine_zeiten_nur_mit_verknuepfung(self):
        r = self.client.get(reverse("core:dashboard"))
        self.assertNotContains(r, "Meine Zeiten")
        mitarbeiter(benutzer=self.user)
        self.assertContains(self.client.get(reverse("core:dashboard")), "Meine Zeiten")
