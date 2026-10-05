from django import forms

from core.forms import BootstrapFormMixin

from . import formulare
from .briefbogen import PLATZHALTER as BRIEFBOGEN_PLATZHALTER
from .models import Authentifizierung, BriefbogenElement, Firma, Lizenz, LIZENZ_MODULE, Nummernkreis


class DatumWidget(forms.DateInput):
    input_type = "date"

    def __init__(self, **kw):
        super().__init__(format="%Y-%m-%d", **kw)


class FirmaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Firma
        fields = [
            "firmenname", "strasse", "plz", "ort", "land", "email", "telefon",
            "steuernummer", "ust_id", "iban", "bic", "bank", "kontoinhaber",
            "praefix_angebot", "praefix_auftrag", "praefix_rechnung", "standard_steuersatz", "zahlungsziel_tage",
        ]


class MailForm(BootstrapFormMixin, forms.ModelForm):
    smtp_passwort = forms.CharField(
        label="SMTP-Passwort", required=False, widget=forms.PasswordInput(render_value=False),
        help_text="Leer lassen, um das gespeicherte Passwort beizubehalten.",
    )

    class Meta:
        model = Firma
        fields = ["smtp_host", "smtp_port", "smtp_verschluesselung", "smtp_benutzer", "smtp_passwort",
                  "smtp_absender_adresse", "smtp_absender_name"]

    def clean_smtp_passwort(self):
        return self.cleaned_data["smtp_passwort"] or self.instance.smtp_passwort


class NummernkreisForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Nummernkreis
        fields = ["naechste_nummer"]

    def clean_naechste_nummer(self):
        nummer = self.cleaned_data["naechste_nummer"]
        if nummer < 1:
            raise forms.ValidationError("Die nächste Nummer muss mindestens 1 sein.")
        return nummer


NummernkreisFormSet = forms.modelformset_factory(Nummernkreis, form=NummernkreisForm, extra=0)


class LizenzForm(BootstrapFormMixin, forms.ModelForm):
    module = forms.MultipleChoiceField(
        label="Module", choices=list(LIZENZ_MODULE.items()), required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Lizenz
        fields = ["referenz", "gueltig_ab", "gueltig_bis", "status", "module"]
        widgets = {"gueltig_ab": DatumWidget(), "gueltig_bis": DatumWidget()}

    def clean(self):
        daten = super().clean()
        ab, bis = daten.get("gueltig_ab"), daten.get("gueltig_bis")
        if ab and bis and bis < ab:
            self.add_error("gueltig_bis", '"Gültig bis" darf nicht vor "Gültig ab" liegen.')
        return daten


class AuthentifizierungForm(BootstrapFormMixin, forms.ModelForm):
    ldap_bind_passwort = forms.CharField(
        label="Bind-Passwort", required=False, widget=forms.PasswordInput(render_value=False),
        help_text="Leer lassen, um das gespeicherte Passwort beizubehalten.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hilfe = {
            "ldap_host": "Name oder IP-Adresse des LDAP-Servers bzw. Domänencontrollers.",
            "ldap_base_dn": "Ab hier werden Benutzer gesucht, z. B. DC=firma,DC=local oder OU=Benutzer,DC=firma,DC=local.",
            "ldap_bind_dn": "Konto, das Benutzer suchen darf. Active Directory: auch Benutzername@firma.local möglich.",
            "ldap_benutzerfilter": (
                "Bestimmt, mit welchem Attribut man sich anmeldet; %s steht für den eingegebenen Benutzernamen. "
                "Active Directory: (sAMAccountName=%s) – Anmeldung mit dem Kurznamen, z. B. mmustermann. "
                "OpenLDAP: (uid=%s). Mit E-Mail-Adresse: (mail=%s)."
            ),
            "ldap_namensattribut": "Active Directory: displayName, OpenLDAP: cn.",
            "ldap_mailattribut": "Normalerweise mail.",
        }
        for name, text in hilfe.items():
            self.fields[name].help_text = text

    class Meta:
        model = Authentifizierung
        fields = ["modus", "ldap_host", "ldap_port", "ldap_verschluesselung", "ldap_base_dn", "ldap_bind_dn",
                  "ldap_bind_passwort", "ldap_benutzerfilter", "ldap_namensattribut", "ldap_mailattribut"]

    def clean_ldap_bind_passwort(self):
        return self.cleaned_data["ldap_bind_passwort"] or self.instance.ldap_bind_passwort

    def clean_ldap_benutzerfilter(self):
        filter_ = self.cleaned_data["ldap_benutzerfilter"]
        if "%s" not in filter_:
            raise forms.ValidationError("Der Filter muss %s als Platzhalter für den Benutzernamen enthalten, z. B. (uid=%s).")
        return filter_


class BriefbogenElementForm(BootstrapFormMixin, forms.ModelForm):
    """Bild oder Textblock auf dem Briefbogen; je nach Typ sind nur die passenden Felder relevant."""

    BILD_FELDER = ("bild", "seitenverhaeltnis_beibehalten")
    TEXT_FELDER = ("text", "schriftart", "schriftgroesse", "schriftfarbe", "ausrichtung")

    class Meta:
        model = BriefbogenElement
        fields = [
            "typ", "name", "reihenfolge", "x_mm", "y_mm", "breite_mm", "hoehe_mm", "vertikale_ausrichtung",
            "bild", "seitenverhaeltnis_beibehalten",
            "text", "schriftart", "schriftgroesse", "schriftfarbe", "ausrichtung",
        ]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 5}),
            "schriftfarbe": forms.TextInput(attrs={"type": "color"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["schriftart"] = forms.ChoiceField(
            label="Schriftart", required=False, choices=[(k, k) for k in formulare.SCHRIFTARTEN]
        )
        self.fields["text"].help_text = (
            "Platzhalter: " + ", ".join(BRIEFBOGEN_PLATZHALTER) + ". Sie werden bei jedem PDF durch die aktuellen "
            "Firmendaten ersetzt."
        )
        self.fields["ausrichtung"].required = False
        self.fields["schriftfarbe"].required = False
        self.fields["schriftfarbe"].initial = ""

    def clean(self):
        daten = super().clean()
        typ = daten.get("typ")
        if typ == BriefbogenElement.Typ.BILD and not (daten.get("bild") or self.instance.bild):
            self.add_error("bild", "Bei Typ „Bild“ muss eine Bilddatei hochgeladen werden.")
        if typ == BriefbogenElement.Typ.TEXTBOX and not (daten.get("text") or "").strip():
            self.add_error("text", "Bei Typ „Textblock“ muss ein Text angegeben werden.")
        if daten.get("breite_mm") is not None and daten["breite_mm"] <= 0:
            self.add_error("breite_mm", "Die Breite muss größer als 0 sein.")
        return daten


class LiveAktivierenForm(forms.Form):
    sicherung = forms.BooleanField(
        label="Ich habe eine Sicherung der Datenbank erstellt, falls ich Daten doch noch brauche.",
        error_messages={"required": "Bitte bestätigen."},
    )
    bestaetigung = forms.CharField(
        label="Zur Bestätigung LIVE eintippen", widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )

    def clean_bestaetigung(self):
        if self.cleaned_data["bestaetigung"].strip() != "LIVE":
            raise forms.ValidationError("Bitte genau LIVE eintippen.")
        return "LIVE"


# --- Formulareinstellungen (PDF-Layout und Texte) ---------------------------------------------

JA_NEIN = [("1", "Ja"), ("0", "Nein")]
SPALTEN = [("pos", "Pos."), ("artikelnr", "Artikelnummer"), ("menge", "Menge"), ("einzelpreis", "Einzelpreis"),
           ("rabatt", "Rabatt"), ("gesamt", "Gesamt")]
BEZEICHNUNGEN = {
    "schriftart": "Schriftart", "schriftgroesse": "Schriftgröße (pt)", "rand_oben": "Rand oben (mm)",
    "rand_unten": "Rand unten (mm)", "rand_links": "Rand links (mm)", "rand_rechts": "Rand rechts (mm)",
    "akzentfarbe": "Akzentfarbe", "fusszeile": "Fußzeilentext", "seitenzahl": "Seitenzahl anzeigen",
    "fusszeile_firmenblock": "Firmenblock in der Fußzeile", "spalten": "Tabellenspalten",
    "titel": "Titel", "einleitung": "Einleitungstext", "schluss": "Schlusstext", "termin_bezeichnung": "Bezeichnung des Termins",
    "termin_tage": "Termin nach (Tagen)", "spalten_abweichend": "Tabellenspalten (abweichend)",
    "steueraufschluesselung": "Steuer je Satz aufschlüsseln", "zwischensumme": "Nettosumme anzeigen",
}
BOOL = {"seitenzahl", "fusszeile_firmenblock", "steueraufschluesselung", "zwischensumme"}
TEXTAREA = {"fusszeile", "einleitung", "schluss"}
ZAHL = {"schriftgroesse", "rand_oben", "rand_unten", "rand_links", "rand_rechts", "termin_tage"}
SPALTENFELDER = {"spalten", "spalten_abweichend"}


class FormulareForm(forms.Form):
    """Ein Formular für alle Bereiche; leer = vom Bereich "global" bzw. der Vorgabe geerbt."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        gespeichert = formulare.einstellungen_laden()
        self.bereiche = []
        for bereich, schluessel in formulare.VORGABEN.items():
            felder = []
            for key in schluessel:
                name = f"{bereich}__{key}"
                self.fields[name] = self._feld(bereich, key)
                wert = gespeichert.get((bereich, key), "")
                self.initial[name] = wert.split(",") if key in SPALTENFELDER and wert else wert
                felder.append(name)
            self.bereiche.append((bereich, felder))
        for feld in self.fields.values():
            klasse = "form-check-input" if isinstance(feld.widget, forms.CheckboxSelectMultiple) else (
                "form-select" if isinstance(feld.widget, forms.Select) else "form-control")
            if not isinstance(feld.widget, forms.CheckboxSelectMultiple):
                feld.widget.attrs["class"] = klasse
            else:
                feld.widget.attrs["class"] = ""
        self.initial["global__akzentfarbe"] = self.initial.get("global__akzentfarbe") or formulare.VORGABEN["global"]["akzentfarbe"]

    def _feld(self, bereich, key):
        label = BEZEICHNUNGEN.get(key, key)
        geerbt = bereich != "global"
        vorgabe = formulare.VORGABEN[bereich][key]
        hilfe = ""
        if geerbt and key in formulare.VORGABEN["global"]:
            hilfe = "Leer = Einstellung aus „Global“."
        elif vorgabe != "" and key not in SPALTENFELDER and key not in TEXTAREA:
            hilfe = f"Leer = Vorgabe ({vorgabe})."
        if key in BOOL:
            return forms.ChoiceField(label=label, choices=[("", "(geerbt)")] + JA_NEIN, required=False, help_text=hilfe)
        if key == "schriftart":
            return forms.ChoiceField(label=label, required=False, help_text=hilfe,
                                     choices=[("", "(Vorgabe)")] + [(k, k) for k in formulare.SCHRIFTARTEN])
        if key in SPALTENFELDER:
            return forms.MultipleChoiceField(label=label, choices=SPALTEN, required=False, widget=forms.CheckboxSelectMultiple,
                                             help_text="Beschreibung ist immer enthalten." + (" Keine Auswahl = global." if geerbt else ""))
        if key == "akzentfarbe":
            return forms.CharField(label=label, required=False, help_text=hilfe, max_length=7,
                                   widget=forms.TextInput(attrs={"type": "color"}))
        if key in ZAHL:
            return forms.IntegerField(label=label, required=False, min_value=0, max_value=300, help_text=hilfe)
        widget = forms.Textarea(attrs={"rows": 2}) if key in TEXTAREA else forms.TextInput()
        return forms.CharField(label=label, required=False, widget=widget, help_text=hilfe)

    def speichern(self):
        from .models import Formulareinstellung

        for bereich, felder in self.bereiche:
            for name in felder:
                key = name.split("__", 1)[1]
                wert = self.cleaned_data.get(name)
                wert = ",".join(wert) if isinstance(wert, list) else ("" if wert is None else str(wert))
                if wert == "" or (bereich == "global" and key == "akzentfarbe" and wert == formulare.VORGABEN["global"][key]):
                    Formulareinstellung.objects.filter(bereich=bereich, schluessel=key).delete()
                else:
                    Formulareinstellung.objects.update_or_create(bereich=bereich, schluessel=key, defaults={"wert": wert})
