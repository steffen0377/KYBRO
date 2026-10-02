from django.contrib.auth.models import AbstractUser
from django.db import models

from .modules import (
    AKTION_LESEN,
    AKTION_SCHREIBEN,
    APP_LABEL,
    alle_rechte,
    recht_codename,
)


class User(AbstractUser):
    """Benutzerkonto.

    Die bisherige Rolle "Administrator" entspricht ``is_superuser``. Alle
    anderen Benutzer erhalten ihre Rechte über Gruppen (siehe ``ModulRecht``).
    """

    class Quelle(models.TextChoices):
        LOKAL = "local", "Lokal"
        LDAP = "ldap", "LDAP"

    auth_source = models.CharField(
        "Anmeldequelle",
        max_length=10,
        choices=Quelle.choices,
        default=Quelle.LOKAL,
    )

    class Meta:
        verbose_name = "Benutzer"
        verbose_name_plural = "Benutzer"
        ordering = ["username"]

    @property
    def anzeigename(self) -> str:
        return self.get_full_name() or self.get_username()

    @property
    def ist_admin(self) -> bool:
        return self.is_active and self.is_superuser

    def hat_modulrecht(self, modul: str, aktion: str = AKTION_LESEN) -> bool:
        """Prüft das Recht auf ein Modul (``lesen`` oder ``schreiben``).

        Administratoren haben immer vollen Zugriff, inaktive Benutzer keinen.
        Schreibrecht schließt das Leserecht ein.
        """
        # Prüft zugleich, ob Modul und Aktion gültig sind.
        recht_codename(modul, aktion)

        if not self.is_active:
            return False
        if self.is_superuser:
            return True

        schreiben = self.has_perm(f"{APP_LABEL}.{recht_codename(modul, AKTION_SCHREIBEN)}")
        if aktion == AKTION_SCHREIBEN:
            return schreiben
        return schreiben or self.has_perm(
            f"{APP_LABEL}.{recht_codename(modul, AKTION_LESEN)}"
        )


class ModulRecht(models.Model):
    """Platzhalter-Modell, an dem die Modulrechte als Django-Rechte hängen.

    Es gibt keine Tabelle dazu (``managed = False``). Das Modell existiert nur,
    damit Django je Modul die Rechte ``<modul>_lesen`` und ``<modul>_schreiben``
    anlegt, die Gruppen zugewiesen werden können.
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = alle_rechte()
        verbose_name = "Modulrecht"
        verbose_name_plural = "Modulrechte"
