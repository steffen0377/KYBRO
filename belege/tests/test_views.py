from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse

from belege import services
from belege.models import Angebot, Rechnung
from stammdaten.models import Artikel, Kunde

User = get_user_model()


def nutzer(name, *rechte):
    u = User.objects.create_user(name, password="Sehr-geheim-2026")
    g = Group.objects.create(name=name)
    g.permissions.set(Permission.objects.filter(content_type__app_label="accounts", codename__in=rechte))
    u.groups.add(g)
    return u


def formdaten(kunde, positionen, **kopf):
    daten = {"kunde": kunde.pk, "datum": "01.03.2026", "notizen": "",
             "pos-TOTAL_FORMS": len(positionen), "pos-INITIAL_FORMS": 0,
             "pos-MIN_NUM_FORMS": 0, "pos-MAX_NUM_FORMS": 1000}
    daten.update(kopf)
    for i, p in enumerate(positionen):
        for k, v in p.items():
            daten[f"pos-{i}-{k}"] = v
    return daten


POS = {"beschreibung": "Beratung", "menge": "2,00", "einzelpreis": "10,00", "rabatt": "0,00",
       "steuersatz": "19,00", "abrechnung": "einmalig"}


class RechteTests(TestCase):
    def test_login_pflicht_und_403(self):
        self.assertEqual(self.client.get(reverse("belege:angebote_liste")).status_code, 302)
        self.client.force_login(nutzer("ohne"))
        self.assertEqual(self.client.get(reverse("belege:angebote_liste")).status_code, 403)

    def test_leser_darf_nicht_schreiben(self):
        self.client.force_login(nutzer("leser", "angebote_lesen"))
        self.assertEqual(self.client.get(reverse("belege:angebote_liste")).status_code, 200)
        self.assertEqual(self.client.get(reverse("belege:angebote_neu")).status_code, 403)

    def test_rechnung_aus_angebot_braucht_rechnungsrecht(self):
        k = Kunde.objects.create(firma="X")
        self.client.force_login(nutzer("a", "angebote_schreiben"))
        self.client.post(reverse("belege:angebote_neu"), formdaten(k, [POS]))
        angebot = Angebot.objects.get()
        antwort = self.client.post(reverse("belege:angebote_zu_rechnung", args=[angebot.pk]))
        self.assertEqual(antwort.status_code, 403)
        self.assertEqual(Rechnung.objects.count(), 0)


class AngebotFormularTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password="Sehr-geheim-2026")
        self.client.force_login(self.admin)
        self.kunde = Kunde.objects.create(firma="Muster GmbH")

    def test_anlegen_berechnet_summen(self):
        antwort = self.client.post(reverse("belege:angebote_neu"), formdaten(self.kunde, [POS]))
        angebot = Angebot.objects.get()
        self.assertRedirects(antwort, reverse("belege:angebote_ansehen", args=[angebot.pk]))
        self.assertEqual((angebot.netto, angebot.brutto), (Decimal("20.00"), Decimal("23.80")))
        self.assertEqual(angebot.erstellt_von, self.admin)

    def test_ohne_position_wird_abgelehnt(self):
        antwort = self.client.post(reverse("belege:angebote_neu"), formdaten(self.kunde, []))
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(Angebot.objects.count(), 0)

    def test_steuerbefreiter_kunde_erzwingt_null_prozent(self):
        k = Kunde.objects.create(firma="Frei", steuerbefreit=True, befreiungsgrund="Drittland")
        self.client.post(reverse("belege:angebote_neu"), formdaten(k, [POS]))
        angebot = Angebot.objects.get()
        self.assertEqual((angebot.steuer, angebot.brutto), (Decimal("0.00"), Decimal("20.00")))

    def test_formular_zeigt_hilfsdaten(self):
        antwort = self.client.get(reverse("belege:angebote_neu"))
        self.assertContains(antwort, 'id="artikel-daten"')
        self.assertContains(antwort, "beleg_form.js")

    def test_ausgestellte_rechnung_ist_gesperrt_und_entwurf_aenderbar(self):
        angebot = None
        self.client.post(reverse("belege:angebote_neu"), formdaten(self.kunde, [POS]))
        angebot = Angebot.objects.get()
        _, rechnung = services.rechnung_aus_angebot(angebot)
        url = reverse("belege:rechnungen_bearbeiten", args=[rechnung.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        services.rechnung_status_aendern(rechnung, "versendet")
        self.assertNotEqual(self.client.get(url).status_code, 200)

    def test_bestand_sinkt_bei_rechnung_per_formular(self):
        artikel = Artikel.objects.create(name="Kabel", bestand=Decimal("10"))
        pos = dict(POS, artikel=artikel.pk, menge="4,00")
        self.client.post(reverse("belege:rechnungen_neu"),
                         formdaten(self.kunde, [pos], leistungsdatum="01.03.2026", faellig_am="15.03.2026"))
        self.assertEqual(Rechnung.objects.count(), 1)
        artikel.refresh_from_db()
        self.assertEqual(artikel.bestand, Decimal("6"))


class AlsArtikelAnlegenTests(TestCase):
    def test_position_wird_zum_artikel(self):
        admin = User.objects.create_superuser("admin", password="Sehr-geheim-2026")
        self.client.force_login(admin)
        k = Kunde.objects.create(firma="X")
        self.client.post(reverse("belege:angebote_neu"), formdaten(k, [dict(POS, beschreibung="Sonderteil")]))
        position = Angebot.objects.get().positionen.get()
        url = reverse("stammdaten:artikel_neu") + f"?aus_position={position.pk}"
        formular = self.client.get(url).context["form"]
        self.assertEqual(formular["name"].value(), "Sonderteil")
        self.assertContains(self.client.get(url), 'name="aus_position"')
        antwort = self.client.post(url, {
            "name": "Sonderteil", "einheit": "Stk.", "steuersatz": "19,00", "verkaufspreis": "10,00",
            "einkaufspreis": "0,00", "mindestbestand": "0,00", "lagerfuehrung": "on", "aktiv": "on", "aus_position": position.pk,
            "lief-TOTAL_FORMS": 0, "lief-INITIAL_FORMS": 0, "sonder-TOTAL_FORMS": 0, "sonder-INITIAL_FORMS": 0,
            "preis-TOTAL_FORMS": 0, "preis-INITIAL_FORMS": 0,
        })
        position.refresh_from_db()
        self.assertIsNotNone(position.artikel)
        self.assertRedirects(antwort, reverse("belege:angebote_ansehen", args=[position.angebot_id]))
