from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail as djmail
from django.test import TestCase, override_settings
from django.urls import reverse

from einstellungen import formulare, mail
from einstellungen.models import Authentifizierung, Firma, Formulareinstellung, Lizenz, Nummernkreis
from einstellungen.services import naechste_belegnummer

User = get_user_model()
PW = "Sehr-geheim-2026"


class ZugriffTests(TestCase):
    URLS = ["firma", "nummernkreise", "mail", "formulare", "lizenzen", "anmeldung", "lizenz_neu"]

    def test_nur_administratoren(self):
        self.client.force_login(User.objects.create_user("anna", password=PW))
        for name in self.URLS:
            self.assertEqual(self.client.get(reverse(f"einstellungen:{name}")).status_code, 403, name)

    def test_administrator_sieht_alle_seiten_und_menue(self):
        self.client.force_login(User.objects.create_superuser("admin", password=PW))
        for name in self.URLS:
            self.assertEqual(self.client.get(reverse(f"einstellungen:{name}")).status_code, 200, name)
        self.assertContains(self.client.get(reverse("core:dashboard")), reverse("einstellungen:firma"))


class SpeichernTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("admin", password=PW, email="admin@example.com"))

    def test_firma_speichern(self):
        daten = {"firmenname": "IT GmbH", "land": "Deutschland", "praefix_angebot": "A-", "praefix_auftrag": "B-",
                 "praefix_rechnung": "R-", "standard_steuersatz": "19,00", "zahlungsziel_tage": "30"}
        self.assertRedirects(self.client.post(reverse("einstellungen:firma"), daten), reverse("einstellungen:firma"))
        firma = Firma.holen()
        self.assertEqual((firma.firmenname, firma.zahlungsziel_tage, firma.praefix_rechnung), ("IT GmbH", 30, "R-"))
        self.assertEqual(naechste_belegnummer("rechnung", date(2026, 1, 1)), "R-2026-0001")

    def test_nummernkreis_aendern(self):
        naechste_belegnummer("rechnung", date(2026, 1, 1))
        kreis = Nummernkreis.objects.get()
        daten = {"form-TOTAL_FORMS": 1, "form-INITIAL_FORMS": 1, "form-0-id": kreis.pk, "form-0-naechste_nummer": "100"}
        self.client.post(reverse("einstellungen:nummernkreise"), daten)
        self.assertEqual(naechste_belegnummer("rechnung", date(2026, 2, 1)), "RE-2026-0100")
        daten["form-0-naechste_nummer"] = "0"
        antwort = self.client.post(reverse("einstellungen:nummernkreise"), daten)
        self.assertEqual(antwort.status_code, 200)

    def test_smtp_passwort_bleibt_bei_leerem_feld(self):
        firma = Firma.holen(); firma.smtp_passwort = "geheim"; firma.save()
        daten = {"smtp_host": "mail.example.com", "smtp_port": "587", "smtp_verschluesselung": "tls", "smtp_passwort": ""}
        self.client.post(reverse("einstellungen:mail"), daten)
        firma.refresh_from_db()
        self.assertEqual((firma.smtp_host, firma.smtp_passwort), ("mail.example.com", "geheim"))
        self.assertNotContains(self.client.get(reverse("einstellungen:mail")), "geheim")

    def test_testmail(self):
        firma = Firma.holen(); firma.smtp_host = "x"; firma.smtp_absender_adresse = "a@example.com"; firma.save()
        with mock.patch.object(mail, "verbindung", return_value=djmail.get_connection("django.core.mail.backends.locmem.EmailBackend")):
            self.client.post(reverse("einstellungen:mail"), {"test": "1"})
        self.assertEqual(len(djmail.outbox), 1)
        self.assertEqual(djmail.outbox[0].to, ["admin@example.com"])

    def test_testmail_ohne_server_zeigt_fehler(self):
        antwort = self.client.post(reverse("einstellungen:mail"), {"test": "1"}, follow=True)
        self.assertContains(antwort, "Kein SMTP-Server")

    def test_formulareinstellungen(self):
        url = reverse("einstellungen:formulare")
        formular = self.client.get(url).context["form"]
        daten = {n: (f if not isinstance(f, list) else f) for n, f in formular.initial.items()}
        daten = {k: v for k, v in daten.items() if v not in ("", [])}
        daten.update({"global__akzentfarbe": "#ff0000", "rechnung__titel": "Faktura", "angebot__spalten_abweichend": ["pos", "gesamt"],
                      "global__seitenzahl": "0"})
        self.assertRedirects(self.client.post(url, daten), url)
        self.assertEqual(formulare.holen("rechnung", "akzentfarbe"), "#ff0000")
        self.assertEqual(formulare.holen("rechnung", "titel"), "Faktura")
        self.assertEqual(formulare.holen("angebot", "spalten_abweichend"), "pos,gesamt")
        self.assertEqual(formulare.holen("auftrag", "seitenzahl"), "0")
        # Leeren entfernt die Überschreibung wieder
        daten["rechnung__titel"] = ""
        self.client.post(url, daten)
        self.assertEqual(formulare.holen("rechnung", "titel"), "Rechnung")

    def test_lizenz_anlegen_aendern_loeschen(self):
        daten = {"referenz": "Kunde 1", "gueltig_ab": "2026-01-01", "gueltig_bis": "2026-12-31", "status": "active", "module": ["warenwirtschaft"]}
        self.client.post(reverse("einstellungen:lizenz_neu"), daten)
        lizenz = Lizenz.objects.get()
        self.assertEqual(lizenz.module, ["warenwirtschaft"])
        daten["gueltig_bis"] = "2025-01-01"
        self.assertEqual(self.client.post(reverse("einstellungen:lizenz_bearbeiten", args=[lizenz.pk]), daten).status_code, 200)
        self.client.post(reverse("einstellungen:lizenz_loeschen", args=[lizenz.pk]))
        self.assertEqual(Lizenz.objects.count(), 0)

    def test_anmeldeeinstellung_validiert_filter_und_haelt_passwort(self):
        a = Authentifizierung.holen(); a.ldap_bind_passwort = "svc"; a.save()
        basis = {"modus": "ldap_then_local", "ldap_host": "ldap.example.com", "ldap_port": "389", "ldap_verschluesselung": "none",
                 "ldap_benutzerfilter": "(uid=x)", "ldap_namensattribut": "cn", "ldap_mailattribut": "mail"}
        self.assertEqual(self.client.post(reverse("einstellungen:anmeldung"), basis).status_code, 200)
        basis["ldap_benutzerfilter"] = "(uid=%s)"
        self.client.post(reverse("einstellungen:anmeldung"), basis)
        a.refresh_from_db()
        self.assertEqual((a.modus, a.ldap_bind_passwort), ("ldap_then_local", "svc"))
