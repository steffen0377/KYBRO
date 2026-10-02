import base64
import io
import json
import time
import uuid
from datetime import timedelta
from decimal import Decimal

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from api import auth
from api.models import LoginVersuch
from belege.models import Auftrag, Rechnung
from stammdaten.models import Artikel, Kunde, Preisoption
from einstellungen.models import Lizenz

User = get_user_model()
PW = "Sehr-geheim-2026"


def png_base64():
    puffer = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(puffer, "PNG")
    return base64.b64encode(puffer.getvalue()).decode()


class ApiTestBasis(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PW)
        self.token = auth.token_erzeugen(self.admin)[0]
        self.kunde = Kunde.objects.create(firma="Muster GmbH")
        self.artikel = Artikel.objects.create(name="Kabel", verkaufspreis=Decimal("5.00"), bestand=Decimal("10"))

    def api(self, methode, name, daten=None, token="", **query):
        url = reverse(f"api:{name}")
        if query:
            url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
        kopf = {"HTTP_AUTHORIZATION": f"Bearer {token or self.token}"} if token != "keiner" else {}
        if methode == "get":
            return self.client.get(url, **kopf)
        return self.client.post(url, json.dumps(daten or {}), content_type="application/json", **kopf)

    def auftragsdaten(self, **ueberschreiben):
        d = {"client_uuid": str(uuid.uuid4()), "kunde_id": self.kunde.pk, "datum": "2026-03-01", "notizen": "vor Ort",
             "positionen": [{"client_uuid": str(uuid.uuid4()), "artikel_id": self.artikel.pk, "menge": "2", "einzelpreis": "5,00", "steuersatz": "19"}]}
        d.update(ueberschreiben)
        return d


class AnmeldeTests(ApiTestBasis):
    def post(self, daten, **extra):
        return self.client.post(reverse("api:auth"), json.dumps(daten), content_type="application/json", **extra)

    def test_login_liefert_token(self):
        antwort = self.post({"username": "admin", "password": PW})
        self.assertEqual(antwort.status_code, 200)
        daten = antwort.json()
        self.assertTrue(daten["success"])
        nutzlast = jwt.decode(daten["data"]["token"], settings.API_TOKEN_SCHLUESSEL, algorithms=["HS256"])
        self.assertEqual(nutzlast["sub"], str(self.admin.pk))
        self.assertEqual(self.api("get", "kunden", token=daten["data"]["token"]).status_code, 200)

    def test_falsche_daten_und_pflichtfelder(self):
        self.assertEqual(self.post({"username": "admin", "password": "x"}).status_code, 401)
        self.assertEqual(self.post({"username": "admin"}).status_code, 400)
        self.assertEqual(self.client.post(reverse("api:auth"), "kaputt", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.get(reverse("api:auth")).status_code, 405)

    def test_sperre_nach_fuenf_fehlversuchen_je_benutzer_und_ip(self):
        for _ in range(5):
            self.assertEqual(self.post({"username": "admin", "password": "x"}).status_code, 401)
        self.assertEqual(self.post({"username": "admin", "password": PW}).status_code, 429)
        # andere IP und anderer Benutzer sind nicht betroffen
        self.assertEqual(self.post({"username": "admin", "password": PW}, REMOTE_ADDR="10.0.0.9").status_code, 200)
        User.objects.create_user("anna", password=PW)
        self.assertEqual(self.post({"username": "anna", "password": PW}).status_code, 200)

    def test_sperre_laeuft_ab_und_alte_eintraege_werden_geloescht(self):
        for _ in range(5):
            self.post({"username": "admin", "password": "x"})
        LoginVersuch.objects.update(zeitpunkt=timezone.now() - timedelta(minutes=16))
        self.assertEqual(self.post({"username": "admin", "password": PW}).status_code, 200)
        LoginVersuch.objects.update(zeitpunkt=timezone.now() - timedelta(days=2))
        self.post({"username": "admin", "password": PW})
        self.assertEqual(LoginVersuch.objects.count(), 1)

    def test_token_pruefung(self):
        self.assertEqual(self.api("get", "kunden", token="keiner").status_code, 401)
        self.assertEqual(self.api("get", "kunden", token="quatsch").status_code, 401)
        abgelaufen = jwt.encode({"sub": str(self.admin.pk), "exp": int(time.time()) - 5}, settings.API_TOKEN_SCHLUESSEL, algorithm="HS256")
        self.assertEqual(self.api("get", "kunden", token=abgelaufen).status_code, 401)
        fremd = jwt.encode({"sub": str(self.admin.pk), "exp": int(time.time()) + 500}, "anderer-schluessel", algorithm="HS256")
        self.assertEqual(self.api("get", "kunden", token=fremd).status_code, 401)
        ohne_alg = jwt.encode({"sub": "1", "exp": int(time.time()) + 500}, None, algorithm="none")
        self.assertEqual(self.api("get", "kunden", token=ohne_alg).status_code, 401)

    def test_deaktivierter_benutzer_verliert_zugriff(self):
        self.admin.is_active = False
        self.admin.save()
        self.assertEqual(self.api("get", "kunden").status_code, 401)


class RechteTests(ApiTestBasis):
    def nutzer(self, *rechte):
        u = User.objects.create_user("u", password=PW)
        g = Group.objects.create(name="g")
        g.permissions.set(Permission.objects.filter(content_type__app_label="accounts", codename__in=rechte))
        u.groups.add(g)
        return auth.token_erzeugen(u)[0]

    def test_ohne_recht_403(self):
        t = self.nutzer("artikel_lesen")
        self.assertEqual(self.api("get", "artikel", token=t).status_code, 200)
        self.assertEqual(self.api("get", "kunden", token=t).status_code, 403)
        self.assertEqual(self.api("get", "auftraege", token=t).status_code, 403)

    def test_lesen_reicht_nicht_zum_schreiben(self):
        t = self.nutzer("auftraege_lesen", "kunden_lesen")
        self.assertEqual(self.api("post", "auftraege", self.auftragsdaten(), token=t).status_code, 403)

    def test_rechnung_braucht_rechnungsrecht(self):
        t = self.nutzer("auftraege_lesen")
        self.assertEqual(self.api("post", "auftrag_zu_rechnung", {"auftrag_id": 1}, token=t).status_code, 403)

    @override_settings(LIZENZ_PRUEFUNG=True)
    def test_lizenz_pflicht(self):
        antwort = self.api("get", "auftraege")
        self.assertEqual(antwort.status_code, 402)
        Lizenz.objects.create(referenz="x", gueltig_ab=timezone.localdate(), module=["warenwirtschaft"])
        self.assertEqual(self.api("get", "auftraege").status_code, 200)

    def test_methode_nicht_erlaubt(self):
        self.assertEqual(self.api("post", "kunden", {}).status_code, 405)


class LesenTests(ApiTestBasis):
    def test_kunden_liste_einzeln_und_delta(self):
        Kunde.objects.filter(pk=self.kunde.pk).update(geaendert=timezone.now() - timedelta(days=2))
        neu = Kunde.objects.create(firma="Neu AG")
        neu.ansprechpartner.create(nachname="Meier")
        liste = self.api("get", "kunden").json()["data"]
        self.assertEqual(len(liste), 2)
        einzeln = self.api("get", "kunden", id=neu.pk).json()["data"]
        self.assertEqual(einzeln["ansprechpartner"][0]["nachname"], "Meier")
        seit = (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        delta = self.api("get", "kunden", since=seit).json()["data"]
        self.assertEqual([k["firma"] for k in delta], ["Neu AG"])
        self.assertEqual(self.api("get", "kunden", id=9999).status_code, 404)
        self.assertEqual(self.api("get", "kunden", since="quatsch").status_code, 400)
        self.assertEqual(self.api("get", "kunden", id="x").status_code, 400)

    def test_artikel_nur_aktive_aber_delta_mit_inaktiven(self):
        Preisoption.objects.create(artikel=self.artikel, abrechnung="monatlich", preis=Decimal("3"))
        inaktiv = Artikel.objects.create(name="Alt", aktiv=False)
        namen = [a["name"] for a in self.api("get", "artikel").json()["data"]]
        self.assertEqual(namen, ["Kabel"])
        self.assertEqual(self.api("get", "artikel", id=inaktiv.pk).status_code, 200)
        delta = self.api("get", "artikel", since="2000-01-01T00:00:00").json()["data"]
        self.assertEqual({a["name"] for a in delta}, {"Kabel", "Alt"})
        kabel = next(a for a in delta if a["name"] == "Kabel")
        self.assertEqual(kabel["preisoptionen"], [{"id": kabel["preisoptionen"][0]["id"], "abrechnung": "monatlich", "preis": "3.00"}])


class AuftragsSyncTests(ApiTestBasis):
    def test_anlegen_berechnet_summen_und_nummer(self):
        antwort = self.api("post", "auftraege", self.auftragsdaten())
        self.assertEqual(antwort.status_code, 201, antwort.content)
        daten = antwort.json()["data"]
        self.assertEqual((daten["netto"], daten["brutto"], daten["status"]), ("10.00", "11.90", "offen"))
        self.assertTrue(daten["nummer"].startswith("AUF-2026-"))
        self.assertEqual(daten["positionen"][0]["artikelnummer"], self.artikel.artikelnummer)
        self.assertEqual(Auftrag.objects.get().erstellt_von, self.admin)

    def test_erneutes_senden_ist_idempotent(self):
        d = self.auftragsdaten()
        self.assertEqual(self.api("post", "auftraege", d).status_code, 201)
        d["positionen"][0]["menge"] = "3"
        d["positionen"].append({"client_uuid": str(uuid.uuid4()), "beschreibung": "Anfahrt", "menge": "1", "einzelpreis": "20", "steuersatz": "19"})
        antwort = self.api("post", "auftraege", d)
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(Auftrag.objects.count(), 1)
        auftrag = Auftrag.objects.get()
        self.assertEqual(auftrag.positionen.count(), 2)
        self.assertEqual(auftrag.netto, Decimal("35.00"))
        self.assertEqual(self.api("post", "auftraege", d).status_code, 200)
        self.assertEqual(auftrag.positionen.count(), 2)

    def test_unterschrift_setzt_status_und_speichert_bild(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            d = self.auftragsdaten(unterschrift="data:image/png;base64," + png_base64(), unterschrieben_von="Herr Muster")
            daten = self.api("post", "auftraege", d).json()["data"]
        self.assertEqual(daten["status"], "unterschrieben")
        self.assertTrue(daten["hat_unterschrift"])
        self.assertEqual(daten["unterschrieben_von"], "Herr Muster")

    def test_ungueltige_unterschrift(self):
        for bild in ("%%%", base64.b64encode(b"kein bild").decode(), base64.b64encode(b"x" * 1_100_000).decode()):
            self.assertEqual(self.api("post", "auftraege", self.auftragsdaten(unterschrift=bild)).status_code, 400)
        self.assertEqual(Auftrag.objects.count(), 0)

    def test_validierung(self):
        d = self.auftragsdaten()
        for aenderung in (
            {"client_uuid": None}, {"client_uuid": "x"}, {"kunde_id": 9999}, {"datum": "gestern"}, {"status": "quatsch"},
            {"positionen": []}, {"positionen": [{"beschreibung": "x", "menge": "-1", "einzelpreis": "1"}]},
            {"positionen": [{"beschreibung": "x", "menge": "1", "einzelpreis": "abc"}]},
            {"positionen": [{"menge": "1", "einzelpreis": "1"}]},
            {"positionen": [{"artikel_id": 9999, "menge": "1"}]},
            {"positionen": [{"beschreibung": "x", "menge": "1", "einzelpreis": "1", "rabatt": "150"}]},
        ):
            antwort = self.api("post", "auftraege", dict(d, **aenderung))
            self.assertIn(antwort.status_code, (400, 404), aenderung)
            self.assertFalse(antwort.json()["success"])
        self.assertEqual(Auftrag.objects.count(), 0)

    def test_steuerbefreiter_kunde_erhaelt_null_prozent(self):
        self.kunde.steuerbefreit = True
        self.kunde.befreiungsgrund = "Drittland"
        self.kunde.save()
        daten = self.api("post", "auftraege", self.auftragsdaten()).json()["data"]
        self.assertEqual((daten["steuer"], daten["brutto"]), ("0.00", "10.00"))

    def test_fremde_positions_uuid_wird_abgelehnt(self):
        a = self.auftragsdaten()
        self.api("post", "auftraege", a)
        b = self.auftragsdaten(positionen=a["positionen"])
        self.assertEqual(self.api("post", "auftraege", b).status_code, 409)

    def test_lesen_einzeln_liste_delta(self):
        a = self.auftragsdaten()
        auftrag_id = self.api("post", "auftraege", a).json()["data"]["id"]
        self.assertEqual(self.api("get", "auftraege", id=auftrag_id).json()["data"]["client_uuid"], a["client_uuid"])
        self.assertEqual(len(self.api("get", "auftraege").json()["data"]), 1)
        # Ohne Zeitzone gilt die Ortszeit des Servers; mit "Z" bzw. Offset ist der Zeitpunkt eindeutig.
        seit = (timezone.localtime() + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")
        self.assertEqual(self.api("get", "auftraege", since=seit).json()["data"], [])
        frueher = (timezone.now() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual(len(self.api("get", "auftraege", since=frueher).json()["data"]), 1)
        self.assertEqual(self.api("get", "auftraege", id=999).status_code, 404)

    def test_abgerechneter_auftrag_bleibt_unveraendert(self):
        a = self.auftragsdaten(unterschrift=png_base64())
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            daten = self.api("post", "auftraege", a).json()["data"]
        self.api("post", "auftrag_zu_rechnung", {"auftrag_id": daten["id"]})
        a["positionen"][0]["menge"] = "99"
        antwort = self.api("post", "auftraege", a)
        self.assertEqual(antwort.status_code, 200)
        self.assertEqual(Auftrag.objects.get().netto, Decimal("10.00"))


class RechnungTests(ApiTestBasis):
    def unterschriebener_auftrag(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            return self.api("post", "auftraege", self.auftragsdaten(unterschrift=png_base64())).json()["data"]["id"]

    def test_rechnung_idempotent_und_lager(self):
        auftrag_id = self.unterschriebener_auftrag()
        erste = self.api("post", "auftrag_zu_rechnung", {"auftrag_id": auftrag_id})
        self.assertEqual(erste.status_code, 201, erste.content)
        zweite = self.api("post", "auftrag_zu_rechnung", {"auftrag_id": auftrag_id})
        self.assertEqual(zweite.status_code, 200)
        self.assertEqual(erste.json()["data"]["nummer"], zweite.json()["data"]["nummer"])
        self.assertEqual(Rechnung.objects.count(), 1)
        self.assertEqual(Rechnung.objects.get().status, "entwurf")
        self.assertEqual(Auftrag.objects.get().status, "abgeschlossen")
        self.artikel.refresh_from_db()
        self.assertEqual(self.artikel.bestand, Decimal("8"))

    def test_offener_auftrag_wird_abgelehnt(self):
        daten = self.api("post", "auftraege", self.auftragsdaten()).json()["data"]
        self.assertEqual(self.api("post", "auftrag_zu_rechnung", {"auftrag_id": daten["id"]}).status_code, 409)
        self.assertEqual(self.api("post", "auftrag_zu_rechnung", {}).status_code, 400)
        self.assertEqual(self.api("post", "auftrag_zu_rechnung", {"auftrag_id": 999}).status_code, 404)
