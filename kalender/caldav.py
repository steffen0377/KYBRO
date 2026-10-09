"""Kleiner CalDAV-Client (RFC 4791) für den Abgleich mit Nextcloud, Radicale und anderen Kalenderservern.

Benötigt nur ``requests`` und ``lxml``. Unterstützt werden: Kalender finden (Prinzipal und ``calendar-home-set``),
Kalender anlegen (``MKCALENDAR``), Termine speichern, löschen und auflisten. Weiterleitungen werden selbst verfolgt, weil
``requests`` bei 301/302 die Methode von PROPFIND auf GET ändern würde.
"""

from urllib.parse import quote, unquote, urljoin, urlparse
from xml.sax.saxutils import escape

import requests
from lxml import etree

DAV = "DAV:"
CALDAV = "urn:ietf:params:xml:ns:caldav"
NS = {"d": DAV, "c": CALDAV}
KOPF = '<?xml version="1.0" encoding="utf-8"?>'


class CalDavFehler(Exception):
    """Verbindung, Anmeldung oder Anfrage ist fehlgeschlagen (verständlicher Text für die Oberfläche)."""


def _q(praefix: str, name: str) -> str:
    return "{%s}%s" % (NS[praefix], name)


class CalDavClient:
    def __init__(self, url: str, benutzer: str, passwort: str, tls_pruefen: bool = True, timeout: int = 20):
        self.url = (url or "").strip()
        self.session = requests.Session()
        self.session.auth = (benutzer, passwort)
        self.session.verify = tls_pruefen
        self.timeout = timeout
        self.home: str | None = None

    # --- Grundlagen ------------------------------------------------------------------------

    def _anfrage(self, methode: str, url: str, daten: str | bytes | None = None, kopf: dict | None = None, ok=(200,)):
        kopf = dict(kopf or {})
        if isinstance(daten, str):
            daten = daten.encode("utf-8")
        for _ in range(6):
            try:
                antwort = self.session.request(methode, url, data=daten, headers=kopf, timeout=self.timeout, allow_redirects=False)
            except requests.exceptions.SSLError as fehler:
                raise CalDavFehler(f"TLS-Zertifikat nicht vertrauenswürdig ({fehler.__class__.__name__}). Zertifikat prüfen oder die Prüfung abschalten.") from fehler
            except requests.RequestException as fehler:
                raise CalDavFehler(f"Server nicht erreichbar: {fehler.__class__.__name__}: {str(fehler)[:150]}") from fehler
            if antwort.status_code in (301, 302, 307, 308) and antwort.headers.get("Location"):
                url = urljoin(url, antwort.headers["Location"])
                continue
            break
        else:
            raise CalDavFehler("Zu viele Weiterleitungen.")
        if antwort.status_code == 401:
            raise CalDavFehler("Anmeldung abgelehnt (Benutzer oder Passwort bzw. App-Passwort prüfen).")
        if antwort.status_code == 403:
            raise CalDavFehler("Zugriff verweigert (403): fehlen Schreibrechte auf diesen Kalender?")
        if antwort.status_code not in ok:
            auszug = " ".join((antwort.text or "").split())[:150]
            raise CalDavFehler(f"{methode} {urlparse(url).path or '/'}: Server antwortete {antwort.status_code}. {auszug}".strip())
        antwort.url_final = url  # type: ignore[attr-defined]
        return antwort

    def _propfind(self, url: str, eigenschaften: str, tiefe: int = 0):
        body = f'{KOPF}<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>{eigenschaften}</d:prop></d:propfind>'
        antwort = self._anfrage(
            "PROPFIND", url, body, {"Depth": str(tiefe), "Content-Type": "application/xml; charset=utf-8"}, ok=(207,)
        )
        try:
            wurzel = etree.fromstring(antwort.content)
        except etree.XMLSyntaxError as fehler:
            raise CalDavFehler("Der Server lieferte keine gültige CalDAV-Antwort (richtige Adresse?).") from fehler
        ergebnis = []
        for eintrag in wurzel.findall(_q("d", "response")):
            href = eintrag.findtext(_q("d", "href")) or ""
            props = {}
            for stat in eintrag.findall(_q("d", "propstat")):
                if " 200 " in (stat.findtext(_q("d", "status")) or ""):
                    for prop in stat.findall(_q("d", "prop")):
                        for kind in prop:
                            props[kind.tag] = kind
            ergebnis.append({"href": urljoin(antwort.url_final, href), "props": props})  # type: ignore[attr-defined]
        return ergebnis

    # --- Kalender finden --------------------------------------------------------------------

    def _anfangsadressen(self) -> list[str]:
        if not self.url:
            raise CalDavFehler("Keine Server-Adresse angegeben.")
        if not urlparse(self.url).scheme:
            raise CalDavFehler("Die Adresse muss mit https:// oder http:// beginnen.")
        kandidaten = [self.url]
        if urlparse(self.url).path in ("", "/"):
            kandidaten.append(self.url.rstrip("/") + "/remote.php/dav/")  # Nextcloud
        return kandidaten

    def _heim_ab(self, kandidat: str) -> str:
        prinzipal = self._propfind(kandidat, "<d:current-user-principal/>")
        adresse = None
        if prinzipal:
            knoten = prinzipal[0]["props"].get(_q("d", "current-user-principal"))
            href = knoten.findtext(_q("d", "href")) if knoten is not None else None
            if href:
                adresse = urljoin(prinzipal[0]["href"], href)
        heim = self._propfind(adresse or kandidat, "<c:calendar-home-set/>")
        knoten = heim[0]["props"].get(_q("c", "calendar-home-set")) if heim else None
        href = knoten.findtext(_q("d", "href")) if knoten is not None else None
        if href:
            return urljoin(heim[0]["href"], href)
        if adresse:
            return adresse
        raise CalDavFehler("Unter dieser Adresse wurde kein CalDAV-Dienst gefunden.")

    def kalenderheim(self) -> str:
        """Adresse der Sammlung, die die Kalender des Benutzers enthält."""
        letzter = None
        for kandidat in self._anfangsadressen():
            try:
                self.home = self._heim_ab(kandidat)
                return self.home
            except CalDavFehler as fehler:
                if "Anmeldung" in str(fehler):
                    raise
                letzter = fehler
        raise letzter or CalDavFehler("Kein CalDAV-Dienst gefunden.")

    def kalender(self) -> list[dict]:
        """Alle Kalender des Benutzers: ``[{"url", "name"}]``."""
        heim = self.home or self.kalenderheim()
        ergebnis = []
        for e in self._propfind(heim, "<d:resourcetype/><d:displayname/><c:supported-calendar-component-set/>", tiefe=1):
            art = e["props"].get(_q("d", "resourcetype"))
            if art is None or art.find(_q("c", "calendar")) is None:
                continue
            komponenten = e["props"].get(_q("c", "supported-calendar-component-set"))
            if komponenten is not None and not any(k.get("name") == "VEVENT" for k in komponenten):
                continue  # z. B. reine Aufgabenlisten
            anzeige = e["props"].get(_q("d", "displayname"))
            name = (anzeige.text if anzeige is not None and anzeige.text else unquote(urlparse(e["href"]).path.rstrip("/").rsplit("/", 1)[-1]))
            adresse = e["href"] if e["href"].endswith("/") else e["href"] + "/"
            ergebnis.append({"url": adresse, "name": name})
        return sorted(ergebnis, key=lambda k: k["name"].lower())

    def kalender_anlegen(self, name: str) -> dict:
        heim = self.home or self.kalenderheim()
        kennung = "".join(z if z.isalnum() else "-" for z in name.lower()).strip("-") or "kalender"
        adresse = heim.rstrip("/") + "/" + quote(kennung) + "/"
        body = (
            f'{KOPF}<c:mkcalendar xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:set><d:prop>'
            f"<d:displayname>{escape(name)}</d:displayname>"
            '<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set>'
            "</d:prop></d:set></c:mkcalendar>"
        )
        self._anfrage("MKCALENDAR", adresse, body, {"Content-Type": "application/xml; charset=utf-8"}, ok=(201,))
        return {"url": adresse, "name": name}

    # --- Termine ----------------------------------------------------------------------------

    @staticmethod
    def _termin_adresse(kalender_url: str, uid: str) -> str:
        return kalender_url.rstrip("/") + "/" + quote(uid, safe="@") + ".ics"

    def vorhandene(self, kalender_url: str) -> set[str]:
        """Dateinamen aller Termine im Kalender (z. B. ``abc@kybro.ics``)."""
        basis = urlparse(kalender_url).path.rstrip("/")
        namen = set()
        for e in self._propfind(kalender_url, "<d:getetag/>", tiefe=1):
            pfad = urlparse(e["href"]).path
            if pfad.rstrip("/") != basis:
                namen.add(unquote(pfad.rsplit("/", 1)[-1]))
        return namen

    def speichern(self, kalender_url: str, uid: str, ics_text: str) -> None:
        self._anfrage(
            "PUT", self._termin_adresse(kalender_url, uid), ics_text, {"Content-Type": "text/calendar; charset=utf-8"}, ok=(200, 201, 204)
        )

    def loeschen(self, kalender_url: str, uid: str) -> None:
        self._anfrage("DELETE", self._termin_adresse(kalender_url, uid), ok=(200, 204, 404))
