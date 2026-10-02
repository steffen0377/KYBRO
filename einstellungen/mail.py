"""E-Mail-Versand mit den SMTP-Einstellungen aus den Firmendaten."""

from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend

from .models import Firma


class MailFehler(Exception):
    pass


def absender(firma: Firma) -> str:
    adresse = firma.smtp_absender_adresse or firma.email
    if not adresse:
        raise MailFehler("Keine Absenderadresse eingetragen.")
    return f"{firma.smtp_absender_name} <{adresse}>" if firma.smtp_absender_name else adresse


def verbindung(firma: Firma | None = None) -> EmailBackend:
    firma = firma or Firma.holen()
    if not firma.smtp_host:
        raise MailFehler("Kein SMTP-Server eingetragen.")
    return EmailBackend(
        host=firma.smtp_host, port=firma.smtp_port, username=firma.smtp_benutzer or None,
        password=firma.smtp_passwort or None, use_ssl=firma.smtp_verschluesselung == Firma.Verschluesselung.SSL,
        use_tls=firma.smtp_verschluesselung == Firma.Verschluesselung.TLS, timeout=15, fail_silently=False,
    )


def senden(an: list[str], betreff: str, text: str, anhaenge=(), firma: Firma | None = None) -> None:
    """Sendet eine Mail; ``anhaenge``: Tupel (Dateiname, Inhalt als bytes, MIME-Typ)."""
    firma = firma or Firma.holen()
    server = verbindung(firma)
    nachricht = EmailMessage(betreff, text, absender(firma), an, connection=server)
    for name, inhalt, typ in anhaenge:
        nachricht.attach(name, inhalt, typ)
    try:
        nachricht.send()
    except Exception as fehler:  # SMTP-, Netz- und Anmeldefehler gleich behandeln
        raise MailFehler(str(fehler)) from fehler
