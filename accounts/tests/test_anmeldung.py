from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from ldap3 import MOCK_SYNC, Connection, Server
from ldap3.core.exceptions import LDAPSocketOpenError

from accounts import ldap
from einstellungen.models import Authentifizierung, Lizenz

User = get_user_model()
PW = "Sehr-geheim-2026"
BASIS = "ou=people,dc=example,dc=com"


def attrappe(benutzer_dn_passwort=None):
    """Ersetzt ``ldap._verbindung`` durch einen simulierten LDAP-Server."""
    server = Server("fake")
    vorbereitung = Connection(server, user="cn=svc,dc=example,dc=com", password="svcpw", client_strategy=MOCK_SYNC)
    vorbereitung.strategy.add_entry("cn=svc,dc=example,dc=com", {"userPassword": "svcpw", "objectClass": "person"})
    vorbereitung.strategy.add_entry(
        f"uid=lena,{BASIS}",
        {"userPassword": "ldap-pw-1", "objectClass": "inetOrgPerson", "uid": "lena", "cn": "Lena Lang", "mail": "lena@example.com"},
    )

    def verbindung(cfg, benutzer, passwort):
        return Connection(server, user=benutzer, password=passwort, client_strategy=MOCK_SYNC)

    # Mock-Strategie ist je Server geteilt: Einträge bleiben erhalten.
    return mock.patch.object(ldap, "_verbindung", verbindung)


def ldap_einrichten(modus):
    a = Authentifizierung.holen()
    a.modus = modus
    a.ldap_host = "fake"
    a.ldap_base_dn = BASIS
    a.ldap_bind_dn = "cn=svc,dc=example,dc=com"
    a.ldap_bind_passwort = "svcpw"
    a.save()


class AnmeldeModiTests(TestCase):
    def setUp(self):
        self.lokal = User.objects.create_user("lokal", password=PW)
        self.admin = User.objects.create_superuser("admin", password=PW)

    def test_lokal_ist_vorgabe(self):
        self.assertEqual(authenticate(username="lokal", password=PW), self.lokal)
        self.assertIsNone(authenticate(username="lokal", password="falsch"))

    def test_ldap_anmeldung_legt_benutzer_an(self):
        ldap_einrichten("ldap_then_local")
        with attrappe():
            benutzer = authenticate(username="lena", password="ldap-pw-1")
            self.assertIsNone(authenticate(username="lena", password="falsch"))
        self.assertEqual((benutzer.auth_source, benutzer.first_name, benutzer.last_name, benutzer.email),
                         ("ldap", "Lena", "Lang", "lena@example.com"))
        self.assertFalse(benutzer.has_usable_password())
        with attrappe():
            self.assertEqual(authenticate(username="lena", password="ldap-pw-1"), benutzer)
        self.assertEqual(User.objects.filter(username="lena").count(), 1)

    def test_inaktiver_ldap_benutzer_bleibt_gesperrt(self):
        ldap_einrichten("ldap_then_local")
        User.objects.create_user("lena", password=PW, is_active=False)
        with attrappe():
            self.assertIsNone(authenticate(username="lena", password="ldap-pw-1"))

    def test_nur_ldap_sperrt_lokale_benutzer_aber_nicht_ausfall_admin(self):
        ldap_einrichten("ldap")
        with attrappe():
            self.assertIsNone(authenticate(username="lokal", password=PW))
        with mock.patch.object(ldap, "_verbindung", side_effect=LDAPSocketOpenError("weg")):
            self.assertIsNone(authenticate(username="lokal", password=PW))
            self.assertEqual(authenticate(username="admin", password=PW), self.admin)

    def test_reihenfolge_lokal_vor_ldap(self):
        ldap_einrichten("local_then_ldap")
        with attrappe():
            self.assertEqual(authenticate(username="lokal", password=PW), self.lokal)
            self.assertEqual(authenticate(username="lena", password="ldap-pw-1").username, "lena")

    def test_ausfall_faellt_bei_kombination_auf_lokal_zurueck(self):
        ldap_einrichten("ldap_then_local")
        with mock.patch.object(ldap, "_verbindung", side_effect=LDAPSocketOpenError("weg")):
            self.assertEqual(authenticate(username="lokal", password=PW), self.lokal)

    def test_ldap_filter_wird_maskiert(self):
        ldap_einrichten("ldap")
        with attrappe():
            self.assertIsNone(ldap.anmelden("*)(uid=*", "x"))
            self.assertIsNone(ldap.anmelden("lena", ""))

    def test_login_seite_meldet_ldap_ausfall(self):
        ldap_einrichten("ldap")
        with mock.patch.object(ldap, "_verbindung", side_effect=LDAPSocketOpenError("weg")):
            antwort = self.client.post(reverse("accounts:login"), {"username": "lokal", "password": PW})
            self.assertContains(antwort, "LDAP-Server ist nicht erreichbar")
            antwort = self.client.post(reverse("accounts:login"), {"username": "admin", "password": PW}, follow=True)
            self.assertContains(antwort, "Notfallzugang")

    def test_verbindung_testen(self):
        ldap_einrichten("ldap")
        with attrappe():
            self.assertIn("erfolgreich", ldap.verbindung_testen())
        a = Authentifizierung.holen(); a.ldap_bind_passwort = "falsch"; a.save()
        with attrappe(), self.assertRaises(ldap.LdapNichtErreichbar):
            ldap.verbindung_testen()

    def test_bind_passwort_wird_verschluesselt_gespeichert(self):
        ldap_einrichten("ldap")
        from django.db import connection
        with connection.cursor() as c:
            c.execute("select ldap_bind_passwort from einstellungen_authentifizierung")
            self.assertTrue(c.fetchone()[0].startswith("enc1:"))


@override_settings(LIZENZ_PRUEFUNG=True)
class LizenzTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PW)
        self.client.force_login(self.admin)

    def lizenz(self, **kw):
        daten = dict(referenz="Test", gueltig_ab=date.today() - timedelta(days=1), module=["warenwirtschaft"])
        daten.update(kw)
        return Lizenz.objects.create(**daten)

    def test_ohne_lizenz_402_aber_einstellungen_frei(self):
        self.assertEqual(self.client.get(reverse("stammdaten:artikel_liste")).status_code, 402)
        self.assertContains(self.client.get(reverse("belege:angebote_liste")), "Keine gültige Lizenz", status_code=402)
        self.assertEqual(self.client.get(reverse("accounts:benutzer_liste")).status_code, 200)

    def test_gueltige_lizenz_schaltet_frei(self):
        self.lizenz()
        self.assertEqual(self.client.get(reverse("stammdaten:artikel_liste")).status_code, 200)

    def test_abgelaufen_widerrufen_zukuenftig(self):
        for kw in (dict(gueltig_bis=date.today() - timedelta(days=1)), dict(status="revoked"),
                   dict(gueltig_ab=date.today() + timedelta(days=1))):
            Lizenz.objects.all().delete()
            self.lizenz(**kw)
            self.assertEqual(self.client.get(reverse("stammdaten:artikel_liste")).status_code, 402, kw)

    def test_unbefristet_und_letzter_tag(self):
        self.lizenz(gueltig_bis=date.today())
        self.assertEqual(self.client.get(reverse("stammdaten:artikel_liste")).status_code, 200)
