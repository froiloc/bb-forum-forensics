# =============================================================================
# management/investigators/investigators_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Zugriffsschicht auf die Ermittlerstammdaten 'investigators' in
#   coordinator.db. Lesende Methoden (list/get) sowie schreibende Methoden
#   (create/update) — Letztere AUSSCHLIESSLICH über das CoordinatorWriter-
#   Gateway, sodass jede Stammdatenänderung und ihr audit_log-Eintrag in EINER
#   Transaktion committen. Damit gibt es kein Anlegen/Ändern eines Ermittlers
#   ohne lückenlosen Audit-Eintrag (Grundregel 1: kein Beleg wird ausgelassen).
#
# Bewusste Entwurfsentscheidungen:
#   - KEIN Löschen. cases.assigned_to referenziert investigators.id (FK); ein
#     Löschen würde Fälle verwaisen lassen und Belege zerstören. Stilllegen
#     erfolgt über is_investigator=0 (Rolle entziehen), die Zeile bleibt als
#     Beleg erhalten.
#   - system_username ist die IDENTITÄT und wird NICHT geändert (er verknüpft
#     den forensischen Datensatz mit dem Windows-SAMAccountName). Nur
#     display_name und die Rollen-Flags sind änderbar.
#   - update schreibt nur, wenn sich tatsächlich etwas ändert (Diff alt->neu im
#     Audit-Payload). Ein No-Op erzeugt keinen irreführenden Audit-Eintrag.
#
# Beleg: Bauplan B7 v0.4 §5, Projektgespräch 2026-07-01, mc 2026-07-01.
# Version: v0.7.310 · Build: 310 · 2026-07-01
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter

logger = logging.getLogger(__name__)

#: Änderbare Flag-Felder (system_username ist Identität und bleibt unverändert).
_FLAG_FIELDS = ("is_investigator", "is_supervisor", "is_support")


class InvestigatorsError(Exception):
    """Fachlicher Fehler (z. B. Ermittler existiert bereits / nicht vorhanden /
    keine Änderung)."""


class InvestigatorsRepo:
    """Auditierte Lese-/Schreibmethoden auf der Tabelle investigators."""

    def __init__(self, con: sqlite3.Connection, writer: CoordinatorWriter) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # ------------------------------------------------------------------- Lesen
    def list_investigators(self) -> List[Dict[str, Any]]:
        """Alle Ermittler, aufsteigend nach system_username."""
        rows = self._con.execute(
            "SELECT id, system_username, display_name, is_investigator, "
            "       is_supervisor, is_support, created_at "
            "FROM investigators ORDER BY system_username ASC"
        ).fetchall()
        return [self._as_dict(r) for r in rows]

    def get(
        self, *, id: Optional[int] = None, system_username: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Liefert einen Ermittler als dict oder None. Genau eines von id /
        system_username muss angegeben werden.
        """
        row = self._get_row(self._con, id=id, system_username=system_username)
        return self._as_dict(row) if row is not None else None

    # --------------------------------------------------------------- Schreiben
    def create(
        self,
        system_username: str,
        display_name: str,
        *,
        is_investigator: bool = True,
        is_supervisor: bool = False,
        is_support: bool = False,
        actor_id: Optional[int] = None,
        meta: Optional[Any] = None,
    ) -> int:
        """
        Legt einen neuen Ermittler an. Wirft InvestigatorsError, wenn der
        system_username bereits vergeben ist (UNIQUE). Gibt die audit_log-seq
        zurück.
        """
        system_username = system_username.strip()
        display_name = display_name.strip()
        if not system_username:
            raise InvestigatorsError("system_username darf nicht leer sein.")
        if not display_name:
            raise InvestigatorsError("display_name darf nicht leer sein.")

        now = int(time.time())
        i_inv = 1 if is_investigator else 0
        i_sup = 1 if is_supervisor else 0
        i_supp = 1 if is_support else 0

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # UNIQUE-Prüfung innerhalb der Transaktion (BEGIN IMMEDIATE hält die
            # Schreibsperre, kein TOCTOU-Fenster).
            if self._get_row(con, system_username=system_username) is not None:
                raise InvestigatorsError(
                    "Ermittler system_username=%r existiert bereits."
                    % system_username
                )
            cur = con.execute(
                "INSERT INTO investigators "
                "(system_username, display_name, is_investigator, is_supervisor, "
                " is_support, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (system_username, display_name, i_inv, i_sup, i_supp, now),
            )
            new_id = int(cur.lastrowid)
            return {
                "id": new_id,
                "system_username": system_username,
                "display_name": display_name,
                "is_investigator": i_inv,
                "is_supervisor": i_sup,
                "is_support": i_supp,
            }

        return self._writer.audited_write(
            do_write=_w,
            event_type=EventType.INVESTIGATOR_CREATED,
            actor_id=actor_id,
            target_type="investigator",
            target_id=system_username,
            meta=meta,
        )

    def update(
        self,
        *,
        id: Optional[int] = None,
        system_username: Optional[str] = None,
        display_name: Optional[str] = None,
        is_investigator: Optional[bool] = None,
        is_supervisor: Optional[bool] = None,
        is_support: Optional[bool] = None,
        actor_id: Optional[int] = None,
        meta: Optional[Any] = None,
    ) -> int:
        """
        Ändert display_name und/oder Rollen-Flags eines vorhandenen Ermittlers
        (identifiziert über id ODER system_username). Es werden nur tatsächlich
        veränderte Felder geschrieben; der Audit-Payload enthält je Feld
        {alt, neu}. Wirft InvestigatorsError bei unbekanntem Ermittler oder wenn
        sich nichts ändert. Gibt die audit_log-seq zurück.
        """
        # Gewünschte Zielwerte (nur die, die der Aufrufer gesetzt hat).
        wanted: Dict[str, Any] = {}
        if display_name is not None:
            dn = display_name.strip()
            if not dn:
                raise InvestigatorsError("display_name darf nicht leer sein.")
            wanted["display_name"] = dn
        if is_investigator is not None:
            wanted["is_investigator"] = 1 if is_investigator else 0
        if is_supervisor is not None:
            wanted["is_supervisor"] = 1 if is_supervisor else 0
        if is_support is not None:
            wanted["is_support"] = 1 if is_support else 0

        if not wanted:
            raise InvestigatorsError(
                "Keine änderbaren Felder angegeben (--display-name / "
                "--set-investigator / --set-supervisor / --set-support)."
            )

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._get_row(con, id=id, system_username=system_username)
            if row is None:
                raise InvestigatorsError(
                    "Unbekannter Ermittler (id=%r, system_username=%r)."
                    % (id, system_username)
                )

            # Diff berechnen: nur Felder mit tatsächlicher Wertänderung.
            changes: Dict[str, Dict[str, Any]] = {}
            for field, new_val in wanted.items():
                old_val = row[field]
                if old_val != new_val:
                    changes[field] = {"alt": old_val, "neu": new_val}

            if not changes:
                raise InvestigatorsError(
                    "Keine Änderung — die angegebenen Werte entsprechen dem "
                    "aktuellen Stand."
                )

            set_clause = ", ".join("%s = ?" % f for f in changes)
            params = [changes[f]["neu"] for f in changes]
            params.append(int(row["id"]))
            con.execute(
                "UPDATE investigators SET %s WHERE id = ?" % set_clause, params
            )
            return {
                "id": int(row["id"]),
                "system_username": row["system_username"],
                "changes": changes,
            }

        return self._writer.audited_write(
            do_write=_w,
            event_type=EventType.INVESTIGATOR_UPDATED,
            actor_id=actor_id,
            target_type="investigator",
            target_id=str(system_username if system_username is not None else id),
            meta=meta,
        )

    # ------------------------------------------------------------------ intern
    @staticmethod
    def _get_row(
        con: sqlite3.Connection,
        *,
        id: Optional[int] = None,
        system_username: Optional[str] = None,
    ) -> Optional[sqlite3.Row]:
        """Liest eine investigators-Zeile per id ODER system_username."""
        if (id is None) == (system_username is None):
            raise InvestigatorsError(
                "Genau eines von id / system_username muss angegeben werden."
            )
        if id is not None:
            return con.execute(
                "SELECT id, system_username, display_name, is_investigator, "
                "       is_supervisor, is_support, created_at "
                "FROM investigators WHERE id = ?",
                (id,),
            ).fetchone()
        return con.execute(
            "SELECT id, system_username, display_name, is_investigator, "
            "       is_supervisor, is_support, created_at "
            "FROM investigators WHERE system_username = ?",
            (system_username,),
        ).fetchone()

    @staticmethod
    def _as_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": int(row["id"]),
            "system_username": row["system_username"],
            "display_name": row["display_name"],
            "is_investigator": bool(row["is_investigator"]),
            "is_supervisor": bool(row["is_supervisor"]),
            "is_support": bool(row["is_support"]),
            "created_at": int(row["created_at"]),
        }
