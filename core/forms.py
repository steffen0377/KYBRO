"""Gemeinsame Formular-Helfer: Bootstrap-Klassen und deutsche Dezimalzahlen."""

from django import forms


def bootstrap_klassen(form: forms.BaseForm) -> None:
    """Versieht die Widgets eines Formulars mit den passenden Bootstrap-Klassen."""
    for feld in form.fields.values():
        widget = feld.widget
        if isinstance(widget, forms.CheckboxInput):
            klasse = "form-check-input"
        elif isinstance(widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
            continue
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            klasse = "form-select"
        else:
            klasse = "form-control"
        widget.attrs["class"] = f"{widget.attrs.get('class', '')} {klasse}".strip()


class BootstrapFormMixin:
    """Bootstrap-Klassen und Dezimalschreibweise mit Komma ("19,00") für alle Felder.

    Wird in ``__init__`` nach dem Aufruf des Basisformulars angewendet.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for feld in self.fields.values():
            if isinstance(feld, forms.DecimalField):
                # Textfeld statt <input type=number>, sonst lehnt der Browser das Komma ab.
                feld.localize = True
                feld.widget = forms.TextInput(attrs={**feld.widget.attrs, "inputmode": "decimal"})
                feld.widget.is_localized = True
        bootstrap_klassen(self)
