# =============================================================================
# management/person/person_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Zugriffsschicht auf die Ermittlerstammdaten 'person' in
#   coordinator.db. Lesende Methoden (list/get) sowie schreibende Methoden
#   (create/update) — Letztere AUSSCHLIESSLICH über das CoordinatorWriter-
#   Gateway, sodass jede Stammdatenänderung und ihr audit_log-Eintrag in EINER
#   Transaktion committen. Damit gibt es kein Anlegen/Ändern eines Ermittlers
#   ohne lückenlosen Audit-Eintrag (Grundregel 1: kein Beleg wird ausgelassen).
#
# Bewusste Entwurfsentscheidungen:
#   - KEIN Löschen. cases.assigned_to referenziert person.id (FK); ein
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
# Build 342 (Welle 0): Tabelle 'investigators' -> 'person', Klasse
#   InvestigatorsRepo -> PersonRepo, InvestigatorsError -> PersonError,
#   list_investigators() -> list_persons(). Rein mechanisch, verlustfrei.
#   Belege der Audit-Kette (target_type='investigator', EventType.
#   INVESTIGATOR_*) bleiben unveraendert (historische Semantik).
# Build 501 (AD-Abgleich, Bauplan Build501_502 §5):
#   - Lesepfade liefern zusaetzlich is_active/deactivated_at/deactivated_reason
#     (M020). DEFENSIV: fehlen die Spalten (DB vor M020), wird is_active=1
#     angenommen, damit Lesewerkzeuge auf Altbestand nicht brechen.
#   - NEU deactivate()/reactivate(): der "Ruhestand"-Schalter. Deaktivieren
#     setzt is_active=0 + Zeitstempel + Begruendung — NIE ein DELETE (mc
#     2026-07-24). Reaktivieren setzt is_active=1 zurueck; die vorherigen
#     Werte stehen im Audit-Payload (alt->neu). Die WOERTLICHE Bestaetigung
#     ("Entfernen"/"Reaktivieren") ist bewusst NICHT hier, sondern im
#     Workflow (ad_sync/sync_executor.py) verankert — das Repo bleibt die
#     generische, auditierte Stammdaten-Schicht.
# Version: v0.8.501 · Build: 501 · 2026-07-24
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

#: Spalten des Basisschemas (vor M020).
_BASE_COLS = ("id, system_username, display_name, is_investigator, "
              "is_supervisor, is_support, created_at")

#: Zusatzspalten aus M020 (Build 501). Fehlen sie (Altbestand), wird beim
#: Lesen is_active=1 / deactivated_at=None / deactivated_reason=None ergänzt.
_ACTIVE_COLS = ("is_active", "deactivated_at", "deactivated_reason")


class PersonError(Exception):
    """Fachlicher Fehler (z. B. Ermittler existiert bereits / nicht vorhanden /
    keine Änderung)."""


class PersonRepo:
    """Auditierte Lese-/Schreibmethoden auf der Tabelle person."""

    def __init__(self, con: sqlite3.Connection, writer: CoordinatorWriter) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # ------------------------------------------------------------------- Lesen
    def list_persons(self) -> List[Dict[str, Any]]:
        """Alle Ermittler, aufsteigend nach system_username."""
        rows = self._con.execute(
            "SELECT %s FROM person ORDER BY system_username ASC"
            % self._select_cols(self._con)
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
        Legt einen neuen Ermittler an. Wirft PersonError, wenn der
        system_username bereits vergeben ist (UNIQUE). Gibt die audit_log-seq
        zurück.
        """
        system_username = system_username.strip()
        display_name = display_name.strip()
        if not system_username:
            raise PersonError("system_username darf nicht leer sein.")
        if not display_name:
            raise PersonError("display_name darf nicht leer sein.")

        now = int(time.time())
        i_inv = 1 if is_investigator else 0
        i_sup = 1 if is_supervisor else 0
        i_supp = 1 if is_support else 0

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # UNIQUE-Prüfung innerhalb der Transaktion (BEGIN IMMEDIATE hält die
            # Schreibsperre, kein TOCTOU-Fenster).
            if self._get_row(con, system_username=system_username) is not None:
                raise PersonError(
                    "Ermittler system_username=%r existiert bereits."
                    % system_username
                )
            cur = con.execute(
                "INSERT INTO person "
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
        {alt, neu}. Wirft PersonError bei unbekanntem Ermittler oder wenn
        sich nichts ändert. Gibt die audit_log-seq zurück.
        """
        # Gewünschte Zielwerte (nur die, die der Aufrufer gesetzt hat).
        wanted: Dict[str, Any] = {}
        if display_name is not None:
            dn = display_name.strip()
            if not dn:
                raise PersonError("display_name darf nicht leer sein.")
            wanted["display_name"] = dn
        if is_investigator is not None:
            wanted["is_investigator"] = 1 if is_investigator else 0
        if is_supervisor is not None:
            wanted["is_supervisor"] = 1 if is_supervisor else 0
        if is_support is not None:
            wanted["is_support"] = 1 if is_support else 0

        if not wanted:
            raise PersonError(
                "Keine änderbaren Felder angegeben (--display-name / "
                "--set-investigator / --set-supervisor / --set-support)."
            )

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._get_row(con, id=id, system_username=system_username)
            if row is None:
                raise PersonError(
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
                raise PersonError(
                    "Keine Änderung — die angegebenen Werte entsprechen dem "
                    "aktuellen Stand."
                )

            set_clause = ", ".join("%s = ?" % f for f in changes)
            params = [changes[f]["neu"] for f in changes]
            params.append(int(row["id"]))
            con.execute(
                "UPDATE person SET %s WHERE id = ?" % set_clause, params
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

    # ------------------------------------------ Ruhestand (Build 501, M020)
    def deactivate(
        self,
        *,
        id: Optional[int] = None,
        system_username: Optional[str] = None,
        reason: str,
        actor_id: Optional[int] = None,
        meta: Optional[Any] = None,
    ) -> int:
        """
        Schaltet einen Ermittler INAKTIV (is_active=0, Zeitstempel,
        Begruendung) — NIE ein DELETE (mc 2026-07-24; FK cases.assigned_to).
        Rollen-Flags und person_role bleiben als historischer Beleg
        unangetastet. Wirft PersonError bei unbekanntem Ermittler, bereits
        inaktivem Konto, leerer Begruendung oder fehlender M020. Gibt die
        audit_log-seq zurueck (Beleg PERSON_DEACTIVATED).

        Die woertliche Supervisor-Bestaetigung ("Entfernen") prueft der
        Workflow (ad_sync/sync_executor.py) — siehe Kopfkommentar.
        """
        reason = (reason or "").strip()
        if not reason:
            raise PersonError("Begruendung (reason) darf nicht leer sein.")
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._require_m020_row(
                con, id=id, system_username=system_username)
            if not row["is_active"]:
                raise PersonError(
                    "Ermittler %r ist bereits inaktiv (deaktiviert am %s)."
                    % (row["system_username"], row["deactivated_at"]))
            con.execute(
                "UPDATE person SET is_active = 0, deactivated_at = ?, "
                "deactivated_reason = ? WHERE id = ?",
                (now, reason, int(row["id"])),
            )
            return {
                "id": int(row["id"]),
                "system_username": row["system_username"],
                "display_name": row["display_name"],
                "is_active": {"alt": 1, "neu": 0},
                "deactivated_at": now,
                "reason": reason,
            }

        return self._writer.audited_write(
            do_write=_w,
            event_type=EventType.PERSON_DEACTIVATED,
            actor_id=actor_id,
            target_type="investigator",
            target_id=str(system_username if system_username is not None else id),
            meta=meta,
        )

    def reactivate(
        self,
        *,
        id: Optional[int] = None,
        system_username: Optional[str] = None,
        actor_id: Optional[int] = None,
        meta: Optional[Any] = None,
    ) -> int:
        """
        Nimmt einen inaktiven Ermittler wieder in Betrieb (is_active=1;
        deactivated_at/-reason werden geleert — die vorherigen Werte stehen
        im Audit-Payload alt->neu, nichts geht verloren). Wirft PersonError
        bei unbekanntem Ermittler, aktivem Konto oder fehlender M020. Gibt
        die audit_log-seq zurueck (Beleg PERSON_REACTIVATED).
        """
        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._require_m020_row(
                con, id=id, system_username=system_username)
            if row["is_active"]:
                raise PersonError(
                    "Ermittler %r ist bereits aktiv." % row["system_username"])
            con.execute(
                "UPDATE person SET is_active = 1, deactivated_at = NULL, "
                "deactivated_reason = NULL WHERE id = ?",
                (int(row["id"]),),
            )
            return {
                "id": int(row["id"]),
                "system_username": row["system_username"],
                "display_name": row["display_name"],
                "is_active": {"alt": 0, "neu": 1},
                "deactivated_at": {"alt": row["deactivated_at"], "neu": None},
                "deactivated_reason": {"alt": row["deactivated_reason"],
                                       "neu": None},
            }

        return self._writer.audited_write(
            do_write=_w,
            event_type=EventType.PERSON_REACTIVATED,
            actor_id=actor_id,
            target_type="investigator",
            target_id=str(system_username if system_username is not None else id),
            meta=meta,
        )

    @staticmethod
    def _require_m020_row(
        con: sqlite3.Connection,
        *,
        id: Optional[int] = None,
        system_username: Optional[str] = None,
    ) -> sqlite3.Row:
        """
        Liest eine person-Zeile und verlangt die M020-Spalten (Schreibpfade
        des Ruhestands-Schalters duerfen auf einer Alt-DB nicht still einen
        anderen Zustand vortaeuschen).
        """
        have = {r[1] for r in con.execute("PRAGMA table_info(person)")}
        if not all(c in have for c in _ACTIVE_COLS):
            raise PersonError(
                "person.is_active fehlt — Migration M020 ist nicht "
                "angewandt (python -m management.migrate).")
        row = PersonRepo._get_row(con, id=id, system_username=system_username)
        if row is None:
            raise PersonError(
                "Unbekannter Ermittler (id=%r, system_username=%r)."
                % (id, system_username))
        return row

    # ------------------------------------------------------------------ intern
    @staticmethod
    def _get_row(
        con: sqlite3.Connection,
        *,
        id: Optional[int] = None,
        system_username: Optional[str] = None,
    ) -> Optional[sqlite3.Row]:
        """Liest eine person-Zeile per id ODER system_username."""
        if (id is None) == (system_username is None):
            raise PersonError(
                "Genau eines von id / system_username muss angegeben werden."
            )
        cols = PersonRepo._select_cols(con)
        if id is not None:
            return con.execute(
                "SELECT %s FROM person WHERE id = ?" % cols,
                (id,),
            ).fetchone()
        return con.execute(
            "SELECT %s FROM person WHERE system_username = ?" % cols,
            (system_username,),
        ).fetchone()

    @staticmethod
    def _select_cols(con: sqlite3.Connection) -> str:
        """
        Spaltenliste fuer person-SELECTs. Enthaelt die M020-Spalten nur, wenn
        die DB sie hat (DEFENSIV — Lesewerkzeuge auf Altbestand vor M020
        duerfen nicht brechen; Schreibpfade deactivate/reactivate verlangen
        M020 ausdruecklich).
        """
        have = {r[1] for r in con.execute("PRAGMA table_info(person)")}
        if all(c in have for c in _ACTIVE_COLS):
            return _BASE_COLS + ", " + ", ".join(_ACTIVE_COLS)
        return _BASE_COLS

    @staticmethod
    def _as_dict(row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys())
        d = {
            "id": int(row["id"]),
            "system_username": row["system_username"],
            "display_name": row["display_name"],
            "is_investigator": bool(row["is_investigator"]),
            "is_supervisor": bool(row["is_supervisor"]),
            "is_support": bool(row["is_support"]),
            "created_at": int(row["created_at"]),
            # M020 (Build 501): Altbestand ohne die Spalten gilt als aktiv.
            "is_active": bool(row["is_active"]) if "is_active" in keys else True,
            "deactivated_at": (int(row["deactivated_at"])
                               if "deactivated_at" in keys
                               and row["deactivated_at"] is not None else None),
            "deactivated_reason": (row["deactivated_reason"]
                                   if "deactivated_reason" in keys else None),
        }
        return d
