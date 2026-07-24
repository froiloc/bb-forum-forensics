# =============================================================================
# management/server/identity.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Aufloesung der ausfuehrenden OS-Identitaet auf einen person-Datensatz. Der
#   Management-Server laeuft lokal auf der Offline-VM und ist an die aufgeloeste
#   OS-Identitaet gebunden (Beleg: Bauplan B7 v1.1 §11.1.1/§11.2/§11.6):
#   der Windows-SAMAccountName wird auf person.system_username abgebildet — die
#   STABILE forensische Identitaet. Der AD-Anzeigename ist reines Anzeige-
#   Attribut (hier person.display_name).
#
#   REIN LESEND, gekapselt, MOCKBAR: die Quelle des OS-Benutzernamens ist ein
#   injizierbarer Callable (Default getpass.getuser). Ein expliziter Override
#   (resolve(system_username=...)) dient Tests und dem Dev-Betrieb. So bleibt der
#   AD-/OS-Zugriff an genau einer Stelle gekapselt und ersetzbar.
#
#   user_id=1 (Forum-Systemeintrag) ist hier ohne Belang: system_username ist der
#   Windows-Kontoname der ERMITTLERIN, kein Forum-Benutzer.
#
# Build 501 (AD-Abgleich, Bauplan Build501_502 §5): INAKTIVE Konten
#   (person.is_active=0, M020 — "Ruhestand"/AD-Entfernung) werden ABGEWIESEN:
#   ein entfernter Ermittler darf sich nicht mehr am Management-Portal
#   anmelden. DEFENSIV: fehlt die Spalte (DB vor M020), gilt das Konto als
#   aktiv (Altbestand bricht nicht).
#
# Version: v0.8.501 · Build: 501 · 2026-07-24
# =============================================================================

import getpass
import sqlite3
from typing import Any, Callable, Dict, Optional


class IdentityError(Exception):
    """Die OS-Identitaet konnte keinem person-Datensatz zugeordnet werden."""


class IdentityResolver:
    """Bildet den OS-Benutzernamen (SAMAccountName) auf person ab (nur lesend)."""

    def __init__(
        self, db_path: str, *,
        os_user_source: Optional[Callable[[], str]] = None,
    ) -> None:
        """
        db_path        — Pfad zur coordinator.db (read-only geoeffnet).
        os_user_source — Callable, das den OS-Benutzernamen liefert; Default
                         getpass.getuser. Injizierbar fuer Tests/Mock.
        """
        self._db_path = db_path
        self._os_user_source = os_user_source or getpass.getuser

    def _ro_con(self) -> sqlite3.Connection:
        con = sqlite3.connect(
            "file:%s?mode=ro" % self._db_path, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def resolve(self, system_username: Optional[str] = None) -> Dict[str, Any]:
        """
        Loest die Identitaet auf. Ohne Argument wird der OS-Benutzername der
        laufenden Sitzung verwendet (os_user_source). Liefert den person-Satz
        als dict. Unbekannt -> IdentityError (kein stiller Fallback).
        """
        name = system_username if system_username is not None \
            else self._os_user_source()
        if not name:
            raise IdentityError(
                "Kein OS-Benutzername ermittelbar (leer).")

        con = self._ro_con()
        try:
            # SELECT * statt fester Spaltenliste: liefert die M020-Spalten
            # (is_active, ...) mit, wenn vorhanden, und bricht auf Altbestand
            # vor M020 nicht (Build 501, defensives Lesen wie PersonRepo).
            row = con.execute(
                "SELECT * FROM person WHERE system_username = ?",
                (name,),
            ).fetchone()
        finally:
            con.close()

        if row is None:
            raise IdentityError(
                "OS-Benutzer %r ist keinem person-Datensatz zugeordnet. "
                "Anlegen ueber 'python -m management.person.person_admin "
                "create'." % name
            )

        d = dict(row)
        # Build 501: inaktive Konten abweisen (kein stiller Teilzugang).
        if not d.get("is_active", 1):
            raise IdentityError(
                "OS-Benutzer %r ist deaktiviert (seit %s%s) und hat keinen "
                "Zugang zum Management-Portal mehr. Reaktivierung nur ueber "
                "den AD-Abgleich (Bestaetigungswort) durch die Aufsicht."
                % (name, d.get("deactivated_at"),
                   (", Grund: %s" % d["deactivated_reason"])
                   if d.get("deactivated_reason") else "")
            )
        return d
