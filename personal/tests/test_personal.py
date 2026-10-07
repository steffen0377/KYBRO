import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from personal import services
from personal.models import Anwesenheit, Mitarbeiter, Stundenkorrektur, Urlaubsantrag, Urlaubsjahr, Vertrag

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

    def test_anteil_nur_volle_monate_bei_eintritt(self):
        # Eintritt 21.09.2026, 28 Tage: Sept. ist kein voller Monat -> Okt.-Dez. = 3/12 = 7 Tage
        m = mitarbeiter(vorname="Spaet", eintrittsdatum=D(2026, 9, 21))
        vertrag(m, gueltig_ab=D(2026, 9, 21), urlaubstage_pro_jahr=28)
        self.assertEqual(services.urlaub_anspruch(m, 2026), Decimal("7"))
        # Eintritt am Monatsersten zählt den Monat voll: Sept.-Dez. = 4/12 = 9,33 -> 9,5
        m2 = mitarbeiter(vorname="Erster", eintrittsdatum=D(2026, 9, 1))
        vertrag(m2, gueltig_ab=D(2026, 9, 1), urlaubstage_pro_jahr=28)
        self.assertEqual(services.urlaub_anspruch(m2, 2026), Decimal("9.5"))

    def test_anteil_bei_austritt(self):
        m = mitarbeiter(vorname="Weg", austrittsdatum=D(2026, 6, 30))
        vertrag(m, urlaubstage_pro_jahr=24)
        self.assertEqual(services.urlaub_anspruch(m, 2026), Decimal("12"))  # Jan.-Juni
        m.austrittsdatum = D(2026, 6, 15)
        m.save()
        self.assertEqual(services.urlaub_anspruch(m, 2026), Decimal("10"))  # Jan.-Mai

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
        self.assertEqual(services.urlaubskonto(self.m, 2026)["genommen"], Decimal("3.5"))  # 31.12. ist ein halber Tag
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


class KalenderTests(TestCase):
    def test_ostern_und_feiertage_nrw(self):
        from personal.kalender import gesetzliche_feiertage, ostersonntag

        self.assertEqual(ostersonntag(2026), D(2026, 4, 5))
        f = gesetzliche_feiertage(2026, "NW")
        self.assertIn(D(2026, 4, 3), f)  # Karfreitag
        self.assertIn(D(2026, 6, 4), f)  # Fronleichnam
        self.assertIn(D(2026, 11, 1), f)  # Allerheiligen
        self.assertNotIn(D(2026, 10, 31), f)

    def test_laenderunterschiede(self):
        from personal.kalender import gesetzliche_feiertage

        self.assertIn(D(2026, 10, 31), gesetzliche_feiertage(2026, "SN"))
        self.assertIn(D(2026, 11, 18), gesetzliche_feiertage(2026, "SN"))  # Buß- und Bettag
        self.assertIn(D(2026, 3, 8), gesetzliche_feiertage(2026, "BE"))
        self.assertNotIn(D(2026, 3, 8), gesetzliche_feiertage(2026, "BY"))
        self.assertEqual(gesetzliche_feiertage(2026, ""), {})

    def test_standard_halbe_tage(self):
        from personal.kalender import Kalender

        k = Kalender()
        self.assertEqual(k.anteil(D(2026, 12, 24)), Decimal("0.5"))
        self.assertEqual(k.anteil(D(2026, 12, 31)), Decimal("0.5"))
        self.assertEqual(k.anteil(D(2026, 12, 23)), Decimal("1"))

    def test_feiertag_kostet_keinen_urlaub(self):
        from personal.models import PersonalEinstellung

        PersonalEinstellung.objects.update_or_create(pk=1, defaults={"bundesland": "NW"})
        m = mitarbeiter()
        vertrag(m)
        # Do 1.5.2025 (Tag der Arbeit), Fr 2.5.2025
        Urlaubsantrag.objects.create(mitarbeiter=m, von=D(2025, 4, 30), bis=D(2025, 5, 2), status="genehmigt")
        self.assertEqual(services.urlaubskonto(m, 2025)["genommen"], Decimal("2"))

    def test_sondertag_ueberschreibt_und_einmalig(self):
        from personal.kalender import Kalender
        from personal.models import Sondertag

        Sondertag.objects.create(name="Betriebsfest", tag=15, monat=6, jahr=2026, urlaubsanteil=0)
        k = Kalender()
        self.assertEqual(k.anteil(D(2026, 6, 15)), 0)
        self.assertEqual(k.anteil(D(2027, 6, 15)), 1)


class EinstellungenViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PW)
        self.client.force_login(self.admin)

    def test_bundesland_speichern(self):
        from personal.models import PersonalEinstellung

        r = self.client.post(reverse("personal:einstellungen"), {"bundesland": "BY"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(PersonalEinstellung.laden().bundesland, "BY")
        self.assertContains(self.client.get(reverse("personal:einstellungen")), "Heilige Drei Könige")

    def test_ungueltiges_bundesland(self):
        r = self.client.post(reverse("personal:einstellungen"), {"bundesland": "XX"})
        self.assertEqual(r.status_code, 200)

    def test_sondertag_anlegen_aendern_loeschen(self):
        from personal.models import Sondertag

        r = self.client.post(reverse("personal:sondertag_neu"), {"name": "Brückentag", "tag": 15, "monat": 5, "urlaubsanteil": "0"})
        self.assertEqual(r.status_code, 302)
        s = Sondertag.objects.get(name="Brückentag")
        self.client.post(reverse("personal:sondertag_bearbeiten", args=[s.pk]), {"name": "Brückentag", "tag": 15, "monat": 5, "urlaubsanteil": "0.5"})
        s.refresh_from_db()
        self.assertEqual(s.urlaubsanteil, Decimal("0.5"))
        self.client.post(reverse("personal:sondertag_loeschen", args=[s.pk]))
        self.assertFalse(Sondertag.objects.filter(name="Brückentag").exists())

    def test_ungueltiges_datum(self):
        r = self.client.post(reverse("personal:sondertag_neu"), {"name": "X", "tag": 31, "monat": 2, "urlaubsanteil": "0"})
        self.assertEqual(r.status_code, 200)

    def test_nur_admin(self):
        u = User.objects.create_user("u", password=PW)
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse("personal:einstellungen")).status_code, 403)


class JahreszahlenTests(TestCase):
    """Jahreszahlen dürfen kein Tausendertrennzeichen bekommen (USE_THOUSAND_SEPARATOR ist aktiv)."""

    def test_keine_tausenderpunkte(self):
        from personal.models import Sondertag

        admin = User.objects.create_superuser("admin", password=PW)
        self.client.force_login(admin)
        m = mitarbeiter()
        vertrag(m)
        Urlaubsjahr.objects.create(mitarbeiter=m, jahr=2026, uebertrag=2)
        fest = Sondertag.objects.create(name="Fest", tag=1, monat=6, jahr=2026, urlaubsanteil=0)
        seiten = [
            reverse("personal:mitarbeiter_detail", args=[m.pk]) + "?jahr=2026",
            reverse("personal:urlaubsjahr", args=[m.pk, 2026]),
            reverse("personal:einstellungen") + "?jahr=2026",
            reverse("personal:sondertag_bearbeiten", args=[fest.pk]),
        ]
        for url in seiten:
            html = self.client.get(url).content.decode()
            self.assertNotIn("2.026", html, url)
            self.assertNotIn("2.025", html, url)
            self.assertNotIn("2.027", html, url)
        detail = self.client.get(seiten[0]).content.decode()
        self.assertIn("?jahr=2025", detail)
        self.assertIn("?jahr=2027", detail)
        self.assertIn('value="2026"', self.client.get(seiten[3]).content.decode())

    def test_meine_zeiten(self):
        u = User.objects.create_user("erika", password=PW)
        self.client.force_login(u)
        m = mitarbeiter(benutzer=u)
        vertrag(m)
        self.assertNotIn(f"{datetime.date.today().year // 1000}.{datetime.date.today().year % 1000}", self.client.get(reverse("personal:meine_zeiten")).content.decode())


class StundenkorrekturTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("erika", password=PW)
        self.client.force_login(self.user)
        self.m = mitarbeiter(benutzer=self.user)
        vertrag(self.m)

    def personalverantwortlich(self):
        g = Group.objects.create(name="Personal")
        g.permissions.set(Permission.objects.filter(codename__in=["personal_lesen", "personal_schreiben"]))
        self.user.groups.add(g)
        self.user = User.objects.get(pk=self.user.pk)
        self.client.force_login(self.user)

    def einreichen(self, **daten):
        daten = {"datum": "2026-10-05", "stunden": "1,5", "bemerkung": "Kundentermin", **daten}
        return self.client.post(reverse("personal:meine_stunden_neu"), daten)

    def test_einreichen_mit_komma_und_negativ(self):
        self.einreichen()
        self.einreichen(stunden="-2", bemerkung="Arzttermin")
        e = Stundenkorrektur.objects.order_by("pk")
        self.assertEqual([x.stunden for x in e], [Decimal("1.5"), Decimal("-2")])
        self.assertEqual({x.status for x in e}, {"beantragt"})
        self.assertEqual({x.mitarbeiter for x in e}, {self.m})

    def test_bemerkung_ist_pflicht_und_null_nicht_erlaubt(self):
        for daten in ({"bemerkung": ""}, {"bemerkung": "   "}, {"stunden": "0"}):
            antwort = self.einreichen(**daten)
            self.assertEqual(antwort.status_code, 200)
        self.assertFalse(Stundenkorrektur.objects.exists())

    def test_saldo_zaehlt_nur_genehmigtes(self):
        self.einreichen()
        self.einreichen(stunden="-0,5", bemerkung="früher gegangen")
        self.assertEqual(services.stundensaldo(self.m), {"saldo": Decimal("0"), "offen": Decimal("1.00")})
        self.personalverantwortlich()
        e1, e2 = Stundenkorrektur.objects.order_by("pk")
        self.client.post(reverse("personal:stunden_entscheiden", args=[e1.pk]), {"aktion": "genehmigen"})
        self.client.post(reverse("personal:stunden_entscheiden", args=[e2.pk]), {"aktion": "ablehnen"})
        e1.refresh_from_db()
        self.assertEqual((e1.status, e1.entschieden_von), ("genehmigt", self.user))
        self.assertEqual(services.stundensaldo(self.m), {"saldo": Decimal("1.50"), "offen": Decimal("0")})

    def test_entscheiden_nur_mit_schreibrecht(self):
        self.einreichen()
        e = Stundenkorrektur.objects.get()
        antwort = self.client.post(reverse("personal:stunden_entscheiden", args=[e.pk]), {"aktion": "genehmigen"})
        self.assertEqual(antwort.status_code, 403)
        e.refresh_from_db()
        self.assertEqual(e.status, "beantragt")

    def test_zurueckziehen_nur_offen_und_nur_eigene(self):
        self.einreichen()
        e = Stundenkorrektur.objects.get()
        fremd = Stundenkorrektur.objects.create(
            mitarbeiter=mitarbeiter(vorname="Fremd"), datum=D(2026, 10, 5), stunden=1, bemerkung="x"
        )
        self.assertEqual(self.client.post(reverse("personal:meine_stunden_zurueckziehen", args=[fremd.pk])).status_code, 404)
        self.client.post(reverse("personal:meine_stunden_zurueckziehen", args=[e.pk]))
        e.refresh_from_db()
        self.assertEqual(e.status, "storniert")

    def test_personalverwaltung_traegt_direkt_genehmigt_ein(self):
        self.personalverantwortlich()
        andere = mitarbeiter(vorname="Anna")
        self.client.post(reverse("personal:stunden_neu"), {
            "mitarbeiter": andere.pk, "datum": "2026-10-02", "stunden": "-1", "bemerkung": "Fehlzeit",
        })
        e = Stundenkorrektur.objects.get()
        self.assertEqual((e.mitarbeiter, e.status, e.stunden), (andere, "genehmigt", Decimal("-1")))

    def test_seiten_und_anzeige(self):
        self.einreichen()
        self.assertContains(self.client.get(reverse("personal:meine_zeiten")), "Über-/Fehlstunde(n) erfassen")
        self.assertContains(self.client.get(reverse("personal:meine_stunden_neu")), "Bemerkung")
        self.personalverantwortlich()
        self.assertContains(self.client.get(reverse("personal:stunden_liste")), "Kundentermin")
        self.assertContains(self.client.get(reverse("personal:mitarbeiter_detail", args=[self.m.pk])), "Kundentermin")
        self.assertContains(self.client.get(reverse("core:dashboard")), "Über-/Fehlstunden")


class UebersichtMarkierungTests(TestCase):
    def setUp(self):
        self.m = mitarbeiter(vorname="Erika", nachname="Muster")
        vertrag(self.m)
        Urlaubsantrag.objects.create(
            mitarbeiter=self.m, von=D(2026, 10, 5), bis=D(2026, 10, 6), status="genehmigt", bemerkung="Hochzeit der Schwester"
        )
        Urlaubsantrag.objects.create(mitarbeiter=self.m, von=D(2026, 10, 12), bis=D(2026, 10, 12), status="genehmigt")
        Stundenkorrektur.objects.create(
            mitarbeiter=self.m, datum=D(2026, 10, 8), stunden=Decimal("1.5"), bemerkung="Serverumzug", status="genehmigt"
        )
        Stundenkorrektur.objects.create(
            mitarbeiter=self.m, datum=D(2026, 10, 9), stunden=Decimal("-2"), bemerkung="Arzt", status="beantragt"
        )
        Stundenkorrektur.objects.create(
            mitarbeiter=self.m, datum=D(2026, 10, 14), stunden=Decimal("3"), bemerkung="abgelehnt", status="abgelehnt"
        )

    def zellen(self):
        ue = services.monatsuebersicht([self.m], 2026, 10)
        return {z["datum"].day: z for z in ue["zeilen"][0]["zellen"]}

    def test_urlaub_mit_bemerkung_wird_markiert(self):
        z = self.zellen()
        self.assertTrue(z[5]["bemerkung"] and z[6]["bemerkung"])
        self.assertIn("Bemerkung: Hochzeit der Schwester", z[5]["titel"])
        self.assertFalse(z[12]["bemerkung"])
        self.assertNotIn("Bemerkung", z[12]["titel"])

    def test_stunden_werden_markiert_mit_zeit_und_bemerkung(self):
        z = self.zellen()
        self.assertEqual((z[8]["stunden"], z[8]["stunden_offen"]), ("plus", False))
        self.assertIn("+1,5 Std.: Serverumzug", z[8]["titel"])
        self.assertEqual((z[9]["stunden"], z[9]["stunden_offen"]), ("minus", True))
        self.assertIn("-2 Std. (beantragt): Arzt", z[9]["titel"])
        self.assertEqual(z[14]["stunden"], "")  # abgelehnte Einträge werden nicht markiert

    def test_namen_als_nachname_vorname(self):
        self.assertEqual(self.m.listenname, "Muster, Erika")
        User.objects.create_superuser("chef", password=PW)
        self.client.login(username="chef", password=PW)
        antwort = self.client.get(reverse("personal:anwesenheit") + "?monat=2026-10")
        self.assertContains(antwort, "Muster, Erika")
        self.assertContains(antwort, "az-std-plus")
        self.assertContains(antwort, "az-bem")
