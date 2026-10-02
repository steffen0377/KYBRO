from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .modules import (
    AKTION_LESEN,
    AKTION_SCHREIBEN,
    APP_LABEL,
    MODULE,
    recht_codename,
)

User = get_user_model()

MIN_BENUTZERNAME = 3


class AnmeldeForm(AuthenticationForm):
    """Anmeldeformular mit deutschen Meldungen und Bootstrap-Feldern."""

    error_messages = {
        "invalid_login": "Benutzername oder Passwort ist falsch.",
        "inactive": "Dieses Konto ist deaktiviert.",
    }

    def get_invalid_login_error(self):
        if getattr(self.request, "ldap_nicht_erreichbar", False):
            return ValidationError(
                "Der LDAP-Server ist nicht erreichbar. Bitte wenden Sie sich an Ihren Administrator.",
                code="ldap_unavailable",
            )
        return super().get_invalid_login_error()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Benutzername"
        self.fields["password"].label = "Passwort"
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autofocus": True}
        )
        self.fields["password"].widget.attrs.update({"class": "form-control"})


def _bootstrap_klassen(form: forms.BaseForm) -> None:
    """Versieht die Widgets eines Formulars mit den passenden Bootstrap-Klassen."""
    for feld in form.fields.values():
        widget = feld.widget
        if isinstance(widget, forms.CheckboxInput):
            klasse = "form-check-input"
        elif isinstance(widget, forms.CheckboxSelectMultiple):
            continue
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            klasse = "form-select"
        else:
            klasse = "form-control"
        widget.attrs["class"] = f"{widget.attrs.get('class', '')} {klasse}".strip()


class BenutzerForm(forms.ModelForm):
    """Anlegen und Bearbeiten eines Benutzers durch einen Administrator."""

    ROLLE_BENUTZER = "benutzer"
    ROLLE_ADMIN = "administrator"
    ROLLEN = [(ROLLE_BENUTZER, "Benutzer"), (ROLLE_ADMIN, "Administrator")]

    rolle = forms.ChoiceField(
        label="Rolle",
        choices=ROLLEN,
        initial=ROLLE_BENUTZER,
        help_text="Administratoren dürfen alles. Benutzer erhalten ihre Rechte über Gruppen.",
    )
    groups = forms.ModelMultipleChoiceField(
        label="Gruppen",
        queryset=Group.objects.order_by("name"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    password1 = forms.CharField(
        label="Passwort",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Passwort wiederholen",
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "groups", "is_active"]
        labels = {
            "username": "Benutzername",
            "first_name": "Vorname",
            "last_name": "Nachname",
            "email": "E-Mail",
            "is_active": "Aktiv",
        }
        help_texts = {"username": "", "is_active": ""}

    def __init__(self, *args, angemeldeter_benutzer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.angemeldeter_benutzer = angemeldeter_benutzer
        self.neu = self.instance.pk is None
        if self.neu:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
            self.fields["is_active"].initial = True
        else:
            self.fields["password1"].help_text = "Leer lassen, wenn das Passwort unverändert bleiben soll."
            self.fields["rolle"].initial = (
                self.ROLLE_ADMIN if self.instance.is_superuser else self.ROLLE_BENUTZER
            )
        _bootstrap_klassen(self)

    def clean_username(self):
        benutzername = self.cleaned_data["username"].strip()
        if len(benutzername) < MIN_BENUTZERNAME:
            raise ValidationError(
                f"Der Benutzername muss mindestens {MIN_BENUTZERNAME} Zeichen lang sein."
            )
        return benutzername

    def clean(self):
        daten = super().clean()
        passwort = daten.get("password1") or ""
        wiederholung = daten.get("password2") or ""

        if (passwort or wiederholung) and passwort != wiederholung:
            self.add_error("password2", "Die beiden Passwörter stimmen nicht überein.")

        if not self.neu:
            self._pruefe_aussperrung(daten)
        return daten

    def _post_clean(self):
        # Erst jetzt trägt die Instanz die eingegebenen Namen. Nur dann kann
        # der Ähnlichkeitsprüfer prüfen, ob das Passwort dem Benutzernamen gleicht.
        super()._post_clean()
        passwort = self.cleaned_data.get("password1")
        if passwort and not self.has_error("password2"):
            try:
                validate_password(passwort, user=self.instance)
            except ValidationError as fehler:
                self.add_error("password1", fehler)

    def _pruefe_aussperrung(self, daten):
        """Ein Administrator darf sich nicht selbst aussperren.

        Da nur Administratoren dieses Formular bedienen, bleibt dadurch immer
        mindestens ein aktiver Administrator übrig.
        """
        selbst = (
            self.angemeldeter_benutzer is not None
            and self.angemeldeter_benutzer.pk == self.instance.pk
        )
        bleibt_admin = daten.get("rolle") == self.ROLLE_ADMIN and daten.get("is_active")
        if selbst and self.instance.ist_admin and not bleibt_admin:
            raise ValidationError(
                "Sie können sich nicht selbst die Administratorrolle entziehen "
                "oder das eigene Konto deaktivieren."
            )

    def save(self, commit=True):
        benutzer = super().save(commit=False)
        ist_admin = self.cleaned_data["rolle"] == self.ROLLE_ADMIN
        benutzer.is_superuser = ist_admin
        benutzer.is_staff = ist_admin
        if self.cleaned_data.get("password1"):
            benutzer.set_password(self.cleaned_data["password1"])
        if commit:
            benutzer.save()
            self.save_m2m()
        return benutzer


class GruppeForm(forms.ModelForm):
    """Gruppe mit ihren Rechten je Modul (Lesen / Schreiben).

    Schreibrecht schließt das Leserecht ein: Wer "Schreiben" ankreuzt, erhält
    beide Rechte. Rechte, die nicht zu den Modulrechten gehören (etwa über die
    Django-Admin-Oberfläche vergebene), bleiben beim Speichern unberührt.
    """

    class Meta:
        model = Group
        fields = ["name"]
        labels = {"name": "Name"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        vorhandene = self._vorhandene_codenames()
        for modul, label in MODULE.items():
            lesen = recht_codename(modul, AKTION_LESEN)
            schreiben = recht_codename(modul, AKTION_SCHREIBEN)
            self.fields[f"lesen_{modul}"] = forms.BooleanField(
                label=f"{label}: Lesen",
                required=False,
                initial=lesen in vorhandene or schreiben in vorhandene,
            )
            self.fields[f"schreiben_{modul}"] = forms.BooleanField(
                label=f"{label}: Schreiben",
                required=False,
                initial=schreiben in vorhandene,
            )
        _bootstrap_klassen(self)

    def _vorhandene_codenames(self) -> set[str]:
        if self.instance.pk is None:
            return set()
        return set(
            self.instance.permissions.filter(content_type__app_label=APP_LABEL)
            .values_list("codename", flat=True)
        )

    @property
    def rechte_zeilen(self):
        """Zeilen für die Rechtetabelle: (Modullabel, Lesen-Feld, Schreiben-Feld)."""
        return [
            (label, self[f"lesen_{modul}"], self[f"schreiben_{modul}"])
            for modul, label in MODULE.items()
        ]

    def save(self, commit=True):
        gruppe = super().save(commit=commit)
        if commit:
            self._speichere_rechte(gruppe)
        return gruppe

    def _speichere_rechte(self, gruppe):
        gewollt = set()
        for modul in MODULE:
            schreiben = self.cleaned_data.get(f"schreiben_{modul}")
            lesen = self.cleaned_data.get(f"lesen_{modul}")
            if schreiben:
                gewollt.add(recht_codename(modul, AKTION_LESEN))
                gewollt.add(recht_codename(modul, AKTION_SCHREIBEN))
            elif lesen:
                gewollt.add(recht_codename(modul, AKTION_LESEN))

        modulrechte = Permission.objects.filter(content_type__app_label=APP_LABEL)
        fremde = gruppe.permissions.exclude(pk__in=modulrechte.values("pk"))
        neue = modulrechte.filter(codename__in=gewollt)
        gruppe.permissions.set(list(fremde) + list(neue))
