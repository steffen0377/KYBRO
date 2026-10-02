from django.db import models


class LoginVersuch(models.Model):
    """Protokoll der API-Anmeldungen für die Sperre nach zu vielen Fehlversuchen."""

    benutzername = models.CharField(max_length=150)
    ip_adresse = models.CharField(max_length=45)
    erfolg = models.BooleanField(default=False)
    zeitpunkt = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["benutzername", "ip_adresse", "zeitpunkt"])]
