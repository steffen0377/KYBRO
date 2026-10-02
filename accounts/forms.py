from django.contrib.auth.forms import AuthenticationForm


class AnmeldeForm(AuthenticationForm):
    """Anmeldeformular mit deutschen Meldungen und Bootstrap-Feldern."""

    error_messages = {
        "invalid_login": "Benutzername oder Passwort ist falsch.",
        "inactive": "Dieses Konto ist deaktiviert.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Benutzername"
        self.fields["password"].label = "Passwort"
        self.fields["username"].widget.attrs.update(
            {"class": "form-control", "autofocus": True}
        )
        self.fields["password"].widget.attrs.update({"class": "form-control"})
