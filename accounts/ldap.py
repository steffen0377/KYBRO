"""LDAP-Anmeldung (ldap3).

``anmelden`` sucht den Benutzer mit dem Service-Konto und prüft dann dessen
Passwort durch eine Anmeldung mit seinem eigenen DN. Ist der Server oder das
Service-Konto nicht nutzbar, wird ``LdapNichtErreichbar`` ausgelöst, damit der
Aufrufer "Passwort falsch" von "LDAP-Ausfall" unterscheiden kann.
"""

from dataclasses import dataclass

from ldap3 import Connection, Server
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

from einstellungen.models import Authentifizierung

ZEITLIMIT = 5


class LdapNichtErreichbar(Exception):
    pass


@dataclass
class LdapBenutzer:
    benutzername: str
    anzeigename: str
    email: str


def _verbindung(cfg: Authentifizierung, benutzer: str | None, passwort: str | None) -> Connection:
    """Neue (noch ungebundene) Verbindung; Tests ersetzen diese Funktion durch eine Attrappe."""
    server = Server(
        cfg.ldap_host, port=cfg.ldap_port, use_ssl=cfg.ldap_verschluesselung == "ldaps", connect_timeout=ZEITLIMIT
    )
    return Connection(server, user=benutzer or None, password=passwort or None, receive_timeout=ZEITLIMIT)


def _binden(verbindung: Connection, cfg: Authentifizierung) -> bool:
    verbindung.open()
    if cfg.ldap_verschluesselung == "starttls":
        verbindung.start_tls()
    return verbindung.bind()


def _erster_wert(eintrag, attribut: str) -> str:
    wert = eintrag.entry_attributes_as_dict.get(attribut) if attribut else None
    return str(wert[0]) if wert else ""


def anmelden(benutzername: str, passwort: str, cfg: Authentifizierung | None = None) -> LdapBenutzer | None:
    """Gibt den LDAP-Benutzer zurück oder ``None`` bei falschen Zugangsdaten."""
    cfg = cfg or Authentifizierung.holen()
    if not passwort or not benutzername:
        return None
    if not cfg.ldap_host:
        raise LdapNichtErreichbar("Kein LDAP-Server eingetragen.")
    try:
        suche = _verbindung(cfg, cfg.ldap_bind_dn, cfg.ldap_bind_passwort)
        if not _binden(suche, cfg):
            raise LdapNichtErreichbar("Anmeldung des Service-Kontos fehlgeschlagen.")
        filter_ = cfg.ldap_benutzerfilter.replace("%s", escape_filter_chars(benutzername))
        attribute = [a for a in (cfg.ldap_namensattribut, cfg.ldap_mailattribut) if a]
        suche.search(cfg.ldap_base_dn, filter_, attributes=attribute)
        if len(suche.entries) != 1:
            return None
        eintrag = suche.entries[0]
        dn = eintrag.entry_dn
        pruefung = _verbindung(cfg, dn, passwort)
        if not _binden(pruefung, cfg):
            return None
        return LdapBenutzer(
            benutzername=benutzername,
            anzeigename=_erster_wert(eintrag, cfg.ldap_namensattribut) or benutzername,
            email=_erster_wert(eintrag, cfg.ldap_mailattribut),
        )
    except LDAPException as fehler:
        raise LdapNichtErreichbar(str(fehler)) from fehler


def benutzer_testen(benutzername: str, passwort: str = "", cfg: Authentifizierung | None = None) -> str:
    """Diagnose für die Einstellungsseite: Schritt für Schritt, woran eine Anmeldung scheitert.

    Prüft Service-Konto, Benutzersuche (Base DN und Filter) und, wenn ein Passwort angegeben ist,
    die Anmeldung des Benutzers. Gibt einen Text mit dem Ergebnis zurück oder wirft ``LdapNichtErreichbar``
    mit einer verständlichen Fehlerbeschreibung (auch für "Benutzer nicht gefunden" und "Passwort falsch").
    """
    cfg = cfg or Authentifizierung.holen()
    if not cfg.ldap_host:
        raise LdapNichtErreichbar("Kein LDAP-Server eingetragen.")
    try:
        suche = _verbindung(cfg, cfg.ldap_bind_dn, cfg.ldap_bind_passwort)
        if not _binden(suche, cfg):
            raise LdapNichtErreichbar("Service-Konto: Anmeldung fehlgeschlagen (Bind-DN oder Passwort).")
        filter_ = cfg.ldap_benutzerfilter.replace("%s", escape_filter_chars(benutzername))
        attribute = [a for a in (cfg.ldap_namensattribut, cfg.ldap_mailattribut) if a]
        suche.search(cfg.ldap_base_dn, filter_, attributes=attribute)
        if not suche.entries:
            raise LdapNichtErreichbar(
                f"Benutzer nicht gefunden. Suchfilter: {filter_} unter {cfg.ldap_base_dn}. "
                "Prüfen Sie Base DN und Benutzerfilter (Active Directory: (sAMAccountName=%s))."
            )
        if len(suche.entries) > 1:
            raise LdapNichtErreichbar(f"Der Filter {filter_} liefert {len(suche.entries)} Treffer; er muss eindeutig sein.")
        eintrag = suche.entries[0]
        meldung = f"Benutzer gefunden: {eintrag.entry_dn}"
        name = _erster_wert(eintrag, cfg.ldap_namensattribut)
        mail = _erster_wert(eintrag, cfg.ldap_mailattribut)
        if name or mail:
            meldung += f" (Name: {name or '-'}, E-Mail: {mail or '-'})"
        if not passwort:
            return meldung + "."
        if not _binden(_verbindung(cfg, eintrag.entry_dn, passwort), cfg):
            raise LdapNichtErreichbar(meldung + ". Das Passwort des Benutzers wurde abgelehnt.")
        return meldung + ". Anmeldung mit Passwort erfolgreich."
    except LDAPException as fehler:
        raise LdapNichtErreichbar(str(fehler)) from fehler


def verbindung_testen(cfg: Authentifizierung | None = None) -> str:
    """Prüft Server und Service-Konto. Gibt eine Erfolgsmeldung zurück oder wirft ``LdapNichtErreichbar``."""
    cfg = cfg or Authentifizierung.holen()
    if not cfg.ldap_host:
        raise LdapNichtErreichbar("Kein LDAP-Server eingetragen.")
    try:
        verbindung = _verbindung(cfg, cfg.ldap_bind_dn, cfg.ldap_bind_passwort)
        if not _binden(verbindung, cfg):
            raise LdapNichtErreichbar("Anmeldung am LDAP-Server fehlgeschlagen (Bind-DN oder Passwort).")
        return "Verbindung zum LDAP-Server erfolgreich."
    except LDAPException as fehler:
        raise LdapNichtErreichbar(str(fehler)) from fehler
