"""Firmendaten, Nummernkreise und weitere Anwendungseinstellungen."""

from decimal import Decimal

from django.core.validators import FileExtensionValidator
from django.db import models

from core.fields import VerschluesseltesTextFeld


class Firma(models.Model):
    """Die eigene Firma (Einzeleintrag): Briefkopf, Bank, Nummernkreise, E-Mail-Versand."""

    class Verschluesselung(models.TextChoices):
        KEINE = "none", "Keine"
        SSL = "ssl", "SSL/TLS (meist Port 465)"
        TLS = "tls", "STARTTLS (meist Port 587)"

    class Betrieb(models.TextChoices):
        TEST = "test", "Testbetrieb"
        LIVE = "live", "Live-Betrieb"

    # Jede neue Installation startet im Testbetrieb. Der Wechsel zu "live" geschieht nur einmalig über
    # einstellungen.live.live_aktivieren (löscht die Testdaten) und ist in der Oberfläche nicht umkehrbar.
    betriebsmodus = models.CharField("Betriebsmodus", max_length=4, choices=Betrieb.choices, default=Betrieb.TEST)

    firmenname = models.CharField("Firmenname", max_length=150, blank=True)
    logo = models.ImageField(
        "Logo", upload_to="firma/", blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg"])],
    )
    briefbogen = models.FileField(
        "Briefbogen (Hintergrund der PDFs)", upload_to="firma/", blank=True,
        validators=[FileExtensionValidator(["png", "jpg", "jpeg", "pdf"])],
    )
    strasse = models.CharField("Straße & Nr.", max_length=150, blank=True)
    plz = models.CharField("PLZ", max_length=20, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    land = models.CharField("Land", max_length=100, blank=True, default="Deutschland")
    steuernummer = models.CharField("Steuernummer", max_length=50, blank=True)
    ust_id = models.CharField("USt-IdNr.", max_length=20, blank=True)
    iban = models.CharField("IBAN", max_length=50, blank=True)
    bic = models.CharField("BIC", max_length=30, blank=True)
    bank = models.CharField("Bank", max_length=100, blank=True)
    kontoinhaber = models.CharField("Kontoinhaber", max_length=150, blank=True)
    email = models.EmailField("E-Mail", max_length=150, blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)

    praefix_angebot = models.CharField("Präfix Angebote", max_length=20, default="ANG-")
    praefix_auftrag = models.CharField("Präfix Aufträge", max_length=20, default="AUF-")
    praefix_rechnung = models.CharField("Präfix Rechnungen", max_length=20, default="RE-")
    standard_steuersatz = models.DecimalField(
        "Standard-MwSt.-Satz (%)", max_digits=5, decimal_places=2, default=Decimal("19.00")
    )
    zahlungsziel_tage = models.PositiveIntegerField("Zahlungsziel (Tage)", default=14)

    smtp_host = models.CharField("SMTP-Server", max_length=150, blank=True)
    smtp_port = models.PositiveIntegerField("SMTP-Port", default=587)
    smtp_verschluesselung = models.CharField(
        "Verschlüsselung", max_length=4, choices=Verschluesselung.choices, default=Verschluesselung.TLS
    )
    smtp_benutzer = models.CharField("SMTP-Benutzer", max_length=150, blank=True)
    smtp_passwort = VerschluesseltesTextFeld("SMTP-Passwort", blank=True)
    smtp_absender_adresse = models.EmailField("Absenderadresse", max_length=150, blank=True)
    smtp_absender_name = models.CharField("Absendername", max_length=150, blank=True)

    class Meta:
        verbose_name = "Firma"
        verbose_name_plural = "Firma"

    def __str__(self):
        return self.firmenname or "Firma"

    @classmethod
    def holen(cls) -> "Firma":
        """Liefert den Einzeleintrag und legt ihn beim ersten Aufruf an."""
        firma, _ = cls.objects.get_or_create(pk=1)
        return firma

    @property
    def adresszeile(self) -> str:
        return ", ".join(t for t in (self.strasse, f"{self.plz} {self.ort}".strip()) if t)


class Nummernkreis(models.Model):
    """Laufende Nummer je Belegart und Jahr (Zähler beginnt jedes Jahr bei 1)."""

    class Art(models.TextChoices):
        ANGEBOT = "angebot", "Angebot"
        AUFTRAG = "auftrag", "Auftrag"
        RECHNUNG = "rechnung", "Rechnung"

    art = models.CharField(max_length=10, choices=Art.choices)
    jahr = models.PositiveIntegerField()
    naechste_nummer = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Nummernkreis"
        verbose_name_plural = "Nummernkreise"
        constraints = [models.UniqueConstraint(fields=["art", "jahr"], name="eindeutig_nummernkreis")]
        ordering = ["art", "-jahr"]

    def __str__(self):
        return f"{self.get_art_display()} {self.jahr}: {self.naechste_nummer}"


class Formulareinstellung(models.Model):
    """Einzelner Layout-/Textwert für PDFs (Bereich ``global`` oder je Belegart).

    Ein leerer Wert heißt "nicht überschrieben"; gelesen wird mit der Kette
    Belegart -> global -> Vorgabe (siehe ``einstellungen.formulare``).
    """

    bereich = models.CharField("Bereich", max_length=20)
    schluessel = models.CharField("Schlüssel", max_length=50)
    wert = models.TextField("Wert", blank=True)

    class Meta:
        verbose_name = "Formulareinstellung"
        verbose_name_plural = "Formulareinstellungen"
        constraints = [models.UniqueConstraint(fields=["bereich", "schluessel"], name="eindeutig_formulareinstellung")]

    def __str__(self):
        return f"{self.bereich}.{self.schluessel}"


# Module, die per Lizenz freigeschaltet werden. Weitere Module (CRM, Tickets, ...)
# werden hier eingetragen; "core" (Benutzer, Einstellungen) ist immer frei.
LIZENZ_MODULE = {
    "warenwirtschaft": "Warenwirtschaft",
}


class Lizenz(models.Model):
    class Status(models.TextChoices):
        AKTIV = "active", "Aktiv"
        ABGELAUFEN = "expired", "Abgelaufen"
        WIDERRUFEN = "revoked", "Widerrufen"

    referenz = models.CharField("Kunden-/Installationsreferenz", max_length=150)
    gueltig_ab = models.DateField("Gültig ab")
    gueltig_bis = models.DateField("Gültig bis", null=True, blank=True, help_text="Leer = unbefristet.")
    status = models.CharField("Status", max_length=10, choices=Status.choices, default=Status.AKTIV)
    module = models.JSONField("Module", default=list, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lizenz"
        verbose_name_plural = "Lizenzen"
        ordering = ["-gueltig_ab", "-pk"]

    def __str__(self):
        return self.referenz

    @property
    def modul_namen(self) -> str:
        return ", ".join(LIZENZ_MODULE.get(m, m) for m in self.module)


class Authentifizierung(models.Model):
    """Anmeldeverfahren (Einzeleintrag): lokal und/oder LDAP."""

    class Modus(models.TextChoices):
        LOKAL = "local", "Nur lokale Datenbank"
        LDAP = "ldap", "Nur LDAP (lokale Administratoren nur im Notfall)"
        LDAP_DANN_LOKAL = "ldap_then_local", "LDAP vor lokaler Datenbank"
        LOKAL_DANN_LDAP = "local_then_ldap", "Lokale Datenbank vor LDAP"

    class Verschluesselung(models.TextChoices):
        KEINE = "none", "Keine"
        STARTTLS = "starttls", "StartTLS"
        LDAPS = "ldaps", "LDAPS"

    modus = models.CharField("Anmeldeverfahren", max_length=20, choices=Modus.choices, default=Modus.LOKAL)
    ldap_host = models.CharField("LDAP-Server", max_length=150, blank=True)
    ldap_port = models.PositiveIntegerField("Port", default=389)
    ldap_verschluesselung = models.CharField(
        "Verschlüsselung", max_length=10, choices=Verschluesselung.choices, default=Verschluesselung.KEINE
    )
    ldap_base_dn = models.CharField("Base DN", max_length=255, blank=True)
    ldap_bind_dn = models.CharField("Bind-DN (Service-Account)", max_length=255, blank=True)
    ldap_bind_passwort = VerschluesseltesTextFeld("Bind-Passwort", blank=True)
    ldap_benutzerfilter = models.CharField("Benutzerfilter", max_length=255, default="(uid=%s)")
    ldap_namensattribut = models.CharField("Attribut Anzeigename", max_length=50, default="cn")
    ldap_mailattribut = models.CharField("Attribut E-Mail", max_length=50, default="mail")

    class Meta:
        verbose_name = "Authentifizierung"
        verbose_name_plural = "Authentifizierung"

    def __str__(self):
        return "Authentifizierung"

    @classmethod
    def holen(cls) -> "Authentifizierung":
        einstellung, _ = cls.objects.get_or_create(pk=1)
        return einstellung
