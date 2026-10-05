import io
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from einstellungen import briefbogen
from einstellungen.models import BriefbogenElement, Firma

User = get_user_model()
PW = "Sehr-geheim-2026"


def png(breite=400, hoehe=200):
    puffer = io.BytesIO()
    Image.new("RGB", (breite, hoehe), (30, 100, 200)).save(puffer, "PNG")
    return SimpleUploadedFile("logo.png", puffer.getvalue(), content_type="image/png")


def textbox(**kw):
    daten = dict(typ="textbox", x_mm=20, y_mm=280, breite_mm=170, text="Fuß", schriftgroesse=8)
    daten.update(kw)
    return BriefbogenElement.objects.create(**daten)


class PlatzhalterTests(TestCase):
    def test_platzhalter_werden_ersetzt_unbekannte_bleiben(self):
        firma = Firma.holen()
        firma.firmenname, firma.iban = "IT-Dienst GmbH", "DE02120300000000202051"
        self.assertEqual(
            briefbogen.platzhalter_ersetzen("%CompanyName% / %CompanyIban% / %Datum%", firma),
            "IT-Dienst GmbH / DE02 1203 0000 0000 2020 51 / %Datum%",
        )

    def test_unterer_rand_haelt_fusszeile_frei(self):
        firma = Firma.holen()
        self.assertEqual(briefbogen.unterer_rand_mm(firma, 20), 20)
        textbox(y_mm=285, vertikale_ausrichtung="unten", breite_mm=170, text="a\nb\nc")
        rand = briefbogen.unterer_rand_mm(firma, 20)
        self.assertGreater(rand, 20)
        self.assertLess(rand, 60)
        textbox(y_mm=50, text="Kopf")  # Kopfbereich zählt nicht
        self.assertEqual(briefbogen.unterer_rand_mm(firma, 20), rand)

    def test_position_relativ_zum_satzspiegel(self):
        textbox(x_mm=25, y_mm=10, name="oben")
        textbox(x_mm=20, y_mm=290, vertikale_ausrichtung="unten", name="unten")
        oben, unten = briefbogen.elemente_fuer_pdf(Firma.holen(), 20, 20, 20)
        self.assertIn("left:5.00mm", oben["stil"])
        self.assertIn("top:-10.00mm", oben["stil"])
        self.assertIn("bottom:-13.00mm", unten["stil"])


class BriefbogenVerwaltungTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", password=PW)
        self.client.force_login(self.admin)

    def test_nur_administratoren(self):
        el = textbox()
        self.client.force_login(User.objects.create_user("anna", password=PW))
        for name, args in (("briefbogen", []), ("briefbogen_neu", []), ("briefbogen_vorschau", []),
                           ("briefbogen_bearbeiten", [el.pk])):
            self.assertEqual(self.client.get(reverse(f"einstellungen:{name}", args=args)).status_code, 403, name)
        self.assertEqual(self.client.post(reverse("einstellungen:briefbogen_loeschen", args=[el.pk])).status_code, 403)
        self.assertTrue(BriefbogenElement.objects.exists())

    def test_textblock_anlegen_aendern_loeschen(self):
        daten = {"typ": "textbox", "x_mm": "20", "y_mm": "280", "breite_mm": "170", "vertikale_ausrichtung": "unten",
                 "text": "%CompanyName%", "schriftart": "Helvetica", "schriftgroesse": "8", "ausrichtung": "mitte",
                 "reihenfolge": "1"}
        antwort = self.client.post(reverse("einstellungen:briefbogen_neu"), daten)
        self.assertRedirects(antwort, reverse("einstellungen:briefbogen"))
        el = BriefbogenElement.objects.get()
        self.assertEqual((el.x_mm, el.vertikale_ausrichtung, el.ausrichtung), (Decimal("20"), "unten", "mitte"))
        daten["text"] = "Neu"
        self.client.post(reverse("einstellungen:briefbogen_bearbeiten", args=[el.pk]), daten)
        el.refresh_from_db()
        self.assertEqual(el.text, "Neu")
        self.assertContains(self.client.get(reverse("einstellungen:briefbogen")), "Neu")
        self.client.post(reverse("einstellungen:briefbogen_loeschen", args=[el.pk]))
        self.assertFalse(BriefbogenElement.objects.exists())

    def test_pflichtangaben_je_typ(self):
        basis = {"x_mm": "10", "y_mm": "10", "breite_mm": "50", "vertikale_ausrichtung": "oben", "reihenfolge": "0"}
        text_ohne = self.client.post(reverse("einstellungen:briefbogen_neu"), {**basis, "typ": "textbox", "text": " "})
        self.assertContains(text_ohne, "Text angegeben")
        bild_ohne = self.client.post(reverse("einstellungen:briefbogen_neu"), {**basis, "typ": "bild"})
        self.assertContains(bild_ohne, "Bilddatei")
        breite = self.client.post(reverse("einstellungen:briefbogen_neu"), {**basis, "typ": "textbox", "text": "x", "breite_mm": "0"})
        self.assertContains(breite, "größer als 0")
        self.assertFalse(BriefbogenElement.objects.exists())

    def test_bild_hochladen_und_vorschau(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(MEDIA_ROOT=tmp):
            antwort = self.client.post(reverse("einstellungen:briefbogen_neu"), {
                "typ": "bild", "x_mm": "20", "y_mm": "8", "breite_mm": "50", "vertikale_ausrichtung": "oben",
                "reihenfolge": "0", "seitenverhaeltnis_beibehalten": "on", "bild": png(),
            })
            self.assertRedirects(antwort, reverse("einstellungen:briefbogen"))
            textbox(text="Vorschau-Text")
            vorschau = self.client.get(reverse("einstellungen:briefbogen_vorschau"))
            self.assertEqual(vorschau["Content-Type"], "application/pdf")
            self.assertTrue(vorschau.content.startswith(b"%PDF"))

    def test_menue_und_firmenformular_ohne_logo_und_briefbogen_upload(self):
        antwort = self.client.get(reverse("einstellungen:firma"))
        self.assertContains(antwort, reverse("einstellungen:briefbogen"))
        self.assertNotIn("logo", antwort.context["form"].fields)
        self.assertNotIn("briefbogen", antwort.context["form"].fields)
