# =============================================================================
# core/user_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Ermittelt den Systembenutzernamen der laufenden Session und stellt ihn
#   allen anderen Modulen bereit. Kapselt die plattformspezifischen Unterschiede
#   zwischen Linux (DEV) und Windows (PROD).
#
# Plattformverhalten:
#   Linux  — os.environ['USER'] mit Fallback auf pwd.getpwuid(os.getuid()).pw_name
#   Windows — os.environ['USERNAME'] (SAMAccountName, Format in PROD: h012345)
#
# Wichtige Einschränkung:
#   Dieser Modul liefert nur den Systembenutzernamen der OS-Session. Die
#   Prüfung, ob dieser Benutzer in der investigators-Tabelle der coordinator.db
#   bekannt ist, obliegt coordinator_db.py. user_resolver.py hat keine
#   Datenbankabhängigkeit.
#
# Forensische Relevanz:
#   Der Systembenutzer bestimmt im Modus 'job', welcher Ermittlungsauftrag
#   geladen wird. Er wird in page_visits und viewport_events als
#   investigator_id protokolliert. Eine fehlerhafte Benutzerermittlung
#   würde die Zuordnung von Ermittlungshandlungen zu Personen korrumpieren.
#   Daher: harter Abbruch, wenn kein Benutzername ermittelt werden kann.
#
# Abhängigkeiten: os, pwd (Linux), platform — ausschließlich Stdlib
# Version: v0.1.0 · Build: 003 · 2026-04-10
# =============================================================================

import os
import platform
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


class UserResolverError(Exception):
    """
    Wird geworfen, wenn der Systembenutzername nicht ermittelt werden kann.
    Führt im Produktionsbetrieb zu einem harten Serverabbruch, da ohne
    bekannten Benutzer keine forensisch korrekte Protokollierung möglich ist.
    """


class UserResolver:
    """
    Ermittelt und kapselt den Systembenutzernamen der laufenden Session.

    Verwendung:
        resolver = UserResolver()
        name = resolver.system_username   # z.B. "h012345" (PROD) oder "alice" (DEV)
        plattform = resolver.platform     # "linux" oder "windows"

    Der ermittelte Name ist unveränderlich nach der Initialisierung.
    """

    def __init__(self) -> None:
        """
        Initialisiert den UserResolver und ermittelt sofort den
        Systembenutzernamen.

        Raises:
            UserResolverError: Wenn kein Benutzername ermittelt werden kann.
        """
        self._platform: str = platform.system().lower()
        self._system_username: str = self._resolve()
        logger.debug(
            "Systembenutzer ermittelt: '%s' (Plattform: %s)",
            self._system_username,
            self._platform,
        )

    # ------------------------------------------------------------------
    # Öffentliche Schnittstelle
    # ------------------------------------------------------------------

    @property
    def system_username(self) -> str:
        """
        Gibt den ermittelten Systembenutzernamen zurück.

        Unter Linux (DEV): z.B. "alice", "bob"
        Unter Windows (PROD): SAMAccountName, Format h012345

        Returns:
            Systembenutzername als nicht-leerer String.
        """
        return self._system_username

    @property
    def platform(self) -> str:
        """
        Gibt die erkannte Plattform zurück: "linux", "windows" oder
        den Rückgabewert von platform.system().lower() für andere Systeme.
        """
        return self._platform

    @property
    def is_windows(self) -> bool:
        """True, wenn die laufende Plattform Windows ist (PROD-Umgebung)."""
        return self._platform == "windows"

    @property
    def is_linux(self) -> bool:
        """True, wenn die laufende Plattform Linux ist (DEV-Umgebung)."""
        return self._platform == "linux"

    # ------------------------------------------------------------------
    # Interne Auflösungslogik
    # ------------------------------------------------------------------

    def _resolve(self) -> str:
        """
        Ermittelt den Systembenutzernamen plattformspezifisch.

        Auflösungsreihenfolge:
          Windows: os.environ['USERNAME']
          Linux:   os.environ['USER']  →  pwd.getpwuid(os.getuid()).pw_name

        Raises:
            UserResolverError: Wenn kein Benutzername ermittelt werden kann.
        """
        if self._platform == "windows":
            return self._resolve_windows()
        else:
            # Linux und alle anderen Unix-artigen Systeme
            return self._resolve_linux()

    def _resolve_windows(self) -> str:
        """
        Ermittelt den SAMAccountName unter Windows via os.environ['USERNAME'].

        Der SAMAccountName hat in der PROD-Umgebung das Format h012345.
        Andere Formate sind in der DEV-Umgebung (Windows-Entwicklermaschinen)
        möglich und werden akzeptiert.

        Raises:
            UserResolverError: Wenn USERNAME nicht gesetzt oder leer ist.
        """
        username = os.environ.get("USERNAME", "").strip()
        if not username:
            raise UserResolverError(
                "Windows: Umgebungsvariable USERNAME ist nicht gesetzt oder leer. "
                "Der Serverbetrieb ohne identifizierten Systembenutzer ist nicht "
                "zulässig."
            )
        return username

    def _resolve_linux(self) -> str:
        """
        Ermittelt den Benutzernamen unter Linux.

        Auflösungsreihenfolge:
          1. os.environ['USER']
          2. pwd.getpwuid(os.getuid()).pw_name  (Fallback, robust gegen sudo)

        Raises:
            UserResolverError: Wenn kein Benutzername ermittelt werden kann.
        """
        # Versuch 1: Umgebungsvariable USER
        username = os.environ.get("USER", "").strip()
        if username:
            return username

        # Versuch 2: pwd-Modul — funktioniert auch wenn USER nicht gesetzt ist,
        # z.B. in systemd-Units oder wenn der Prozess unter sudo läuft und
        # USER auf "root" gesetzt wurde, aber der echte UID-Inhaber anders ist.
        try:
            import pwd
            username = pwd.getpwuid(os.getuid()).pw_name.strip()
            if username:
                logger.debug(
                    "USER-Umgebungsvariable nicht gesetzt — "
                    "Benutzername via pwd.getpwuid() ermittelt: '%s'",
                    username,
                )
                return username
        except (ImportError, KeyError, OSError) as exc:
            logger.warning(
                "pwd.getpwuid() fehlgeschlagen: %s", exc
            )

        raise UserResolverError(
            "Linux: Weder Umgebungsvariable USER noch pwd.getpwuid() konnten "
            "einen Benutzernamen liefern. "
            "Der Serverbetrieb ohne identifizierten Systembenutzer ist nicht "
            "zulässig."
        )
