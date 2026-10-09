import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from kalender import ics, quellen
from kalender.models import Kalender, KalenderZugang, Termin
from personal.models import Anwesenheit, Mitarbeiter, Stundenkorrektur, Urlaubsantrag

User = get_user_model()
PW = "Sehr-geheim-2026"
D = datetime.date


def aware(jahr, monat, tag, std=0, minute=0):
    return timezone.make_aware(datetime.datetime(jahr, monat, tag, std, minute))


def benutzer_mit(name, *codenamen):
    user = User.objects.create_user(name, password=PW)
    if codenamen:
        gruppe = Group.objects.create(name=f"g-{name}")
        gruppe.permissions.set(Permission.objects.filter(codename__in=codenamen))
        user.groups.add(gruppe)
        user = User.objects.get(pk=user.pk)
    return user


class IcsTests(TestCase):
    def test_ganztaegig_mit_exklusivem_ende_und_escape(self):
        text = ics.ereignis_text({
            "uid": "a@kybro", "titel": "Müller; Meier, GmbH", "ganztaegig": True, "beginn": D(2026, 10, 5), "ende": D(2026, 10, 6),
            "beschreibung": "Zeile 1\nZeile 2",
        })
        self.assertIn("DTSTART;VALUE=DATE:20261005", text)
        self.assertIn("DTEND;VALUE=DATE:20261007", text)
        self.assertIn("SUMMARY:Müller\\; Meier\\, GmbH", text)
        self.assertIn("DESCRIPTION:Zeile 1\\nZeile 2", text)
        self.assertNotIn("METHOD", text)
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))

    def test_zeitpunkte_in_utc(self):
        text = ics.ereignis_text({
            "uid": "b@kybro", "titel": "x", "ganztaegig": False, "beginn": aware(2026, 7, 1, 9), "ende": aware(2026, 7, 1, 10),
        })
        self.assertIn("DTSTART:20260701T070000Z", text)  # Sommerzeit: UTC+2
        self.assertIn("DTEND:20260701T080000Z", text)

    def test_lange_zeilen_werden_gefaltet(self):
        text = ics.ereignis_text({
            "uid": "c@kybro", "titel": "ä" * 80, "ganztaegig": True, "beginn": D(2026, 1, 1), "ende": D(2026, 1, 1),
        })
        for zeile in text.split("\r\n"):
            self.assertLessEqual(len(zeile.encode()), 75)
        entfaltet = text.replace("\r\n ", "")
        self.assertIn("SUMMARY:" + "ä" * 80, entfaltet)

    def test_text_ist_stabil_und_kalender_hat_kopf(self):
        e = {"uid": "d@kybro", "titel": "x", "ganztaegig": True, "beginn": D(2026, 1, 1), "ende": D(2026, 1, 1)}
        self.assertEqual(ics.ereignis_text(e), ics.ereignis_text(e))
        kal = ics.kalender_text([e], "KYBRO: Test", "#112233")
        self.assertIn("X-WR-CALNAME:KYBRO: Test", kal)
        self.assertIn("METHOD:PUBLISH", kal)
        self.assertEqual(kal.count("BEGIN:VEVENT"), 1)


class QuellenTests(TestCase):
    def setUp(self):
        self.k = Kalender.objects.create(name="Team")
        Termin.objects.create(kalender=self.k, titel="Meeting", beginn=aware(2026, 10, 5, 9), ende=aware(2026, 10, 5, 10))
        Termin.objects.create(kalender=self.k, titel="Messe", ganztaegig=True, beginn=aware(2026, 10, 12), ende=aware(2026, 10, 14))
        Termin.objects.create(kalender=self.k, titel="Später", beginn=aware(2027, 5, 1, 9), ende=aware(2027, 5, 1, 10))
        self.m = Mitarbeiter.objects.create(vorname="Erika", nachname="Muster")

    def test_eigene_termine_im_zeitraum(self):
        titel = {e["titel"] for e in quellen.ereignisse(f"k{self.k.pk}", D(2026, 10, 1), D(2026, 10, 31))}
        self.assertEqual(titel, {"Meeting", "Messe"})

    def test_urlaub_nur_genehmigt_und_ohne_bemerkung(self):
        Urlaubsantrag.objects.create(mitarbeiter=self.m, von=D(2026, 10, 5), bis=D(2026, 10, 9), status="genehmigt", bemerkung="geheim")
        Urlaubsantrag.objects.create(mitarbeiter=self.m, von=D(2026, 10, 19), bis=D(2026, 10, 20), status="beantragt")
        e = quellen.ereignisse("urlaub", D(2026, 10, 1), D(2026, 10, 31))
        self.assertEqual([(x["titel"], x["beginn"], x["ende"]) for x in e], [("Muster, Erika: Urlaub", D(2026, 10, 5), D(2026, 10, 9))])
        self.assertNotIn("geheim", str(e))

    def test_anwesenheit_faltet_tage_und_laesst_krank_weg(self):
        for tag, status in ((8, "homeoffice"), (9, "homeoffice"), (12, "homeoffice"), (14, "homeoffice"), (6, "krank"), (7, "anwesend")):
            Anwesenheit.objects.create(mitarbeiter=self.m, datum=D(2026, 10, tag), status=status)
        Stundenkorrektur.objects.create(mitarbeiter=self.m, datum=D(2026, 10, 8), stunden=2, bemerkung="geheim", status="genehmigt")
        e = quellen.ereignisse("anwesenheit", D(2026, 10, 1), D(2026, 10, 31))
        bereiche = sorted((x["beginn"].day, x["ende"].day) for x in e)
        self.assertEqual(bereiche, [(8, 12), (14, 14)])  # Fr 9.10. und Mo 12.10. über das Wochenende verbunden
        self.assertTrue(all(x["titel"] == "Muster, Erika: Homeoffice" for x in e))
        self.assertNotIn("geheim", str(e))
        self.assertNotIn("krank", str(e).lower())

    def test_systemkalender_nur_mit_personalrecht(self):
        nur_kalender = benutzer_mit("k", "kalender_lesen")
        mit_personal = benutzer_mit("p", "kalender_lesen", "personal_lesen")
        ohne = benutzer_mit("o")
        self.assertEqual([q.name for q in quellen.sichtbare_quellen(nur_kalender)], ["Team"])
        self.assertEqual([q.name for q in quellen.sichtbare_quellen(mit_personal)], ["Team", "Urlaub", "Anwesenheit"])
        self.assertEqual(quellen.sichtbare_quellen(ohne), [])


class ViewTests(TestCase):
    def setUp(self):
        self.k = Kalender.objects.create(name="Team", farbe="#ff0000")
        self.leser = benutzer_mit("leser", "kalender_lesen")
        self.schreiber = benutzer_mit("schreiber", "kalender_schreiben")

    def test_ohne_recht_verboten_und_ohne_anmeldung_umleiten(self):
        self.assertEqual(self.client.get(reverse("kalender:monat")).status_code, 302)
        self.client.force_login(benutzer_mit("ohne"))
        self.assertEqual(self.client.get(reverse("kalender:monat")).status_code, 403)

    def test_monatsansicht_zeigt_termine(self):
        Termin.objects.create(kalender=self.k, titel="Kundentermin", beginn=aware(2026, 10, 7, 14), ende=aware(2026, 10, 7, 15))
        self.client.force_login(self.leser)
        antwort = self.client.get(reverse("kalender:monat") + "?monat=2026-10")
        self.assertContains(antwort, "Kundentermin")
        self.assertContains(antwort, "Oktober 2026")
        self.assertNotContains(antwort, "Termin an diesem Tag")  # kein Plus ohne Schreibrecht
        leer = self.client.get(reverse("kalender:monat") + "?monat=2026-11")
        self.assertNotContains(leer, "Kundentermin")

    def test_filter_nach_kalender(self):
        anderer = Kalender.objects.create(name="Privat")
        Termin.objects.create(kalender=anderer, titel="Zahnarzt", beginn=aware(2026, 10, 7, 14), ende=aware(2026, 10, 7, 15))
        self.client.force_login(self.leser)
        antwort = self.client.get(reverse("kalender:monat") + f"?monat=2026-10&k=k{self.k.pk}")
        self.assertNotContains(antwort, "Zahnarzt")

    def test_lesen_darf_nicht_schreiben(self):
        self.client.force_login(self.leser)
        antwort = self.client.post(reverse("kalender:termin_neu"), {"kalender": self.k.pk, "titel": "X"})
        self.assertEqual(antwort.status_code, 403)
        self.assertFalse(Termin.objects.exists())

    def test_termin_anlegen_aendern_loeschen(self):
        self.client.force_login(self.schreiber)
        daten = {
            "kalender": self.k.pk, "titel": "Workshop", "beginn_datum": "2026-10-08", "beginn_zeit": "09:30",
            "ende_datum": "2026-10-08", "ende_zeit": "11:00", "ort": "Büro",
        }
        antwort = self.client.post(reverse("kalender:termin_neu"), daten)
        self.assertEqual(antwort.status_code, 302)
        t = Termin.objects.get()
        self.assertEqual((t.titel, t.erstellt_von, timezone.localtime(t.beginn).hour), ("Workshop", self.schreiber, 9))
        self.client.post(reverse("kalender:termin_bearbeiten", args=[t.pk]), {**daten, "titel": "Workshop 2", "ganztaegig": "on", "ende_datum": "2026-10-09"})
        t.refresh_from_db()
        self.assertEqual((t.titel, t.ganztaegig), ("Workshop 2", True))
        self.assertEqual(timezone.localtime(t.ende).date(), D(2026, 10, 9))
        self.client.post(reverse("kalender:termin_loeschen", args=[t.pk]))
        self.assertFalse(Termin.objects.exists())

    def test_formularfehler(self):
        self.client.force_login(self.schreiber)
        grund = {"kalender": self.k.pk, "titel": "X", "beginn_datum": "2026-10-08", "ende_datum": "2026-10-07"}
        for extra, text in (({}, "Bitte eine Uhrzeit"), ({"beginn_zeit": "09:00", "ende_zeit": "10:00"}, "Das Ende liegt vor dem Beginn")):
            antwort = self.client.post(reverse("kalender:termin_neu"), {**grund, **extra})
            self.assertContains(antwort, text)
        self.assertFalse(Termin.objects.exists())

    def test_kalender_verwalten(self):
        self.client.force_login(self.schreiber)
        self.client.post(reverse("kalender:kalender_neu"), {"name": "Neu", "farbe": "#00ff00", "beschreibung": ""})
        neu = Kalender.objects.get(name="Neu")
        antwort = self.client.post(reverse("kalender:kalender_neu"), {"name": "Falsch", "farbe": "rot"})
        self.assertContains(antwort, "#rrggbb")
        Termin.objects.create(kalender=neu, titel="x", beginn=aware(2026, 1, 1), ende=aware(2026, 1, 1))
        self.client.post(reverse("kalender:kalender_loeschen", args=[neu.pk]))
        self.assertFalse(Kalender.objects.filter(name="Neu").exists())
        self.assertFalse(Termin.objects.exists())

    def test_menue(self):
        self.client.force_login(self.leser)
        self.assertContains(self.client.get(reverse("core:dashboard")), reverse("kalender:monat"))
        self.client.force_login(benutzer_mit("ohne2"))
        self.assertNotContains(self.client.get(reverse("core:dashboard")), reverse("kalender:monat"))


class FeedTests(TestCase):
    def setUp(self):
        self.k = Kalender.objects.create(name="Team")
        Termin.objects.create(
            kalender=self.k, titel="Kundentermin", beginn=timezone.now() + datetime.timedelta(days=3),
            ende=timezone.now() + datetime.timedelta(days=3, hours=1),
        )
        m = Mitarbeiter.objects.create(vorname="Erika", nachname="Muster")
        heute = timezone.localdate()
        Urlaubsantrag.objects.create(mitarbeiter=m, von=heute, bis=heute, status="genehmigt")
        self.user = benutzer_mit("erika", "kalender_lesen")
        self.chef = benutzer_mit("chef", "kalender_lesen", "personal_lesen")

    def schluessel(self, user):
        self.client.force_login(user)
        self.client.get(reverse("kalender:abo"))
        self.client.logout()
        return KalenderZugang.objects.get(benutzer=user).schluessel

    def feed(self, schluessel, kalender):
        return self.client.get(reverse("kalender:feed", args=[schluessel, kalender]))

    def test_feed_ohne_anmeldung_mit_schluessel(self):
        antwort = self.feed(self.schluessel(self.user), f"k{self.k.pk}")
        self.assertEqual(antwort.status_code, 200)
        self.assertTrue(antwort["Content-Type"].startswith("text/calendar"))
        inhalt = antwort.content.decode()
        self.assertIn("SUMMARY:Kundentermin", inhalt)
        self.assertIn("X-WR-CALNAME:KYBRO: Team", inhalt)

    def test_falscher_schluessel_und_unbekannter_kalender(self):
        self.assertEqual(self.feed("falsch", f"k{self.k.pk}").status_code, 404)
        self.assertEqual(self.feed(self.schluessel(self.user), "k99999").status_code, 404)

    def test_systemkalender_nur_mit_personalrecht(self):
        self.assertEqual(self.feed(self.schluessel(self.user), "urlaub").status_code, 404)
        antwort = self.feed(self.schluessel(self.chef), "urlaub")
        self.assertContains(antwort, "Muster\\, Erika: Urlaub")  # Komma ist in iCalendar maskiert

    def test_alle_in_einem(self):
        inhalt = self.feed(self.schluessel(self.chef), "alle").content.decode()
        self.assertIn("Kundentermin", inhalt)
        self.assertIn("Muster\\, Erika: Urlaub", inhalt)
        ohne_personal = self.feed(self.schluessel(self.user), "alle").content.decode()
        self.assertIn("Kundentermin", ohne_personal)
        self.assertNotIn("Urlaub", ohne_personal)

    def test_schluessel_erneuern_sperrt_alte_adresse(self):
        alt = self.schluessel(self.user)
        self.client.force_login(self.user)
        self.client.post(reverse("kalender:abo"))
        self.client.logout()
        self.assertEqual(self.feed(alt, f"k{self.k.pk}").status_code, 404)
        self.assertEqual(self.feed(KalenderZugang.objects.get(benutzer=self.user).schluessel, f"k{self.k.pk}").status_code, 200)

    def test_gesperrter_benutzer_hat_keinen_zugriff(self):
        schluessel = self.schluessel(self.user)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.feed(schluessel, f"k{self.k.pk}").status_code, 404)

    def test_abo_seite_zeigt_webcal(self):
        self.client.force_login(self.user)
        antwort = self.client.get(reverse("kalender:abo"))
        self.assertContains(antwort, "webcal://")
        self.assertContains(antwort, "Team")
        self.assertNotContains(antwort, "Urlaub")  # Systemkalender nur mit Personalrecht
