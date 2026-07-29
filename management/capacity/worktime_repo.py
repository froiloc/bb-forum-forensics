# =============================================================================
# management/capacity/worktime_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# WorktimeRepo — auditierter Schreibpfad fuer die Regel-Arbeitszeit je
# Wochentag (person_worktime, Schema m008). APPEND-ONLY (mc 2026-07-10,
# Entscheidung 2): set_worktime fuegt eine NEUE datierte Zeile ein; die
# Vorgaengerzeile wird NICHT automatisch per effective_to geschlossen. Der
# Leser (Build 358) nimmt die Zeile mit groesstem effective_from <= Stichtag.
#
# Jede Zeile traegt audit_seq == seq des WORKTIME_SET-Belegs (Kopplung wie
# rbac_grant; after_audit-Hook -> Write+Audit atomar).
#
# Beleg: Bauplan B7 v1.1 §11.4; Muster rbac_repo. mc 2026-07-10.
#
# BUILD 560 - DREI ERGAENZUNGEN (mc 2026-07-29):
#   1) DUBLETTENSPERRE. Zwei AKTIVE Zeilen mit demselben
#      (person_id, effective_from) waren bisher moeglich. Die Rechnung
#      blieb dabei richtig (capacity_calculator sortiert nach
#      effective_from ASC, id ASC und nimmt die letzte passende Regel -
#      also die juengere), aber die Tabelle sammelte Karteileichen an,
#      und niemand konnte sehen, welche der beiden Zeilen gilt.
#      set_worktime weist einen solchen Eintrag jetzt ZURUECK; wer
#      korrigieren will, ERSETZT ausdruecklich.
#   2) remove_worktime - Soft-Delete. Die Zeile bleibt stehen und
#      bekommt deleted_at; sie faellt aus Rechnung und Liste, nicht aus
#      der Datenbank. Der Beleg WORKTIME_REMOVED traegt die entfernten
#      Werte, damit die Akte auch dann vollstaendig ist, wenn niemand
#      mehr in die Tabelle sieht.
#   3) replace_worktime - Entfernen UND Neusetzen in EINER Transaktion
#      ueber audited_write_many (Build 534): ZWEI eigene Belege, kein
#      Sammelbeleg, und kein Zwischenzustand, in dem die Person gar
#      keine Regel hat. Die Reihenfolge ist zwingend ERST entfernen,
#      DANN setzen - sonst schluege die eigene Dublettensperre an.
# Version: v0.8.560 · Build: 560 · 2026-07-29
# =============================================================================

import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.capacity.capacity_errors import CapacityError
from management.gateway.coordinator_writer import WriteUnit

_WEEKDAYS = ("mon_min", "tue_min", "wed_min", "thu_min", "fri_min",
             "sat_min", "sun_min")


class WorktimeRepo:
    """Schreibt/liest person_worktime (auditiert, append-only, Soft-Delete)."""

    def __init__(self, con: sqlite3.Connection, writer) -> None:
        self._con = con
        self._writer = writer  # CoordinatorWriter

    # =====================================================================
    # Pruefungen
    # =====================================================================
    @staticmethod
    def _pruefe(effective_from: str, minutes) -> None:
        """
        Wertepruefung. JEDE Ausnahme nennt das schuldige FELD, damit die
        Pflegemaske es markieren kann - bei sieben Minutenfeldern
        nebeneinander ist eine Meldung ohne Feldangabe eine Suchaufgabe.
        """
        if not effective_from:
            raise CapacityError("effective_from ist erforderlich (ISO-Datum).",
                                "effective_from")
        for name, v in zip(_WEEKDAYS, minutes):
            if not isinstance(v, int) or v < 0:
                raise CapacityError(
                    "%s muss eine Minutenzahl >= 0 sein (gefunden: %r)."
                    % (name, v), name)
            if v > 24 * 60:
                raise CapacityError(
                    "%s > 1440 Minuten (mehr als ein Tag) ist unplausibel."
                    % name, name)

    @staticmethod
    def _dublette_pruefen(con: sqlite3.Connection, person_id: int,
                          effective_from: str) -> None:
        """
        Es darf hoechstens EINE aktive Regel je (Person, Stichtag) geben.

        Die Pruefung laeuft INNERHALB der Schreibtransaktion (sie wird aus
        do_write gerufen): so kann zwischen Pruefung und Einfuegen nichts
        dazwischenkommen, und ein Verstoss rollt den ganzen Vorgang zurueck -
        es bleibt weder Zeile noch Beleg stehen.

        Beim Ersetzen greift sie NICHT ins Leere: replace_worktime entfernt
        die alte Zeile in derselben Transaktion VOR dem Setzen, sie traegt
        dann bereits deleted_at und zaehlt hier nicht mehr mit.
        """
        row = con.execute(
            "SELECT id FROM person_worktime "
            "WHERE person_id=? AND effective_from=? AND deleted_at IS NULL",
            (person_id, effective_from)).fetchone()
        if row is not None:
            raise CapacityError(
                "Fuer diese Person gibt es zum Stichtag %s bereits eine "
                "aktive Regel (Zeile #%s). Bestehende Regeln werden nicht "
                "stillschweigend verdoppelt: entferne die alte Zeile oder "
                "ersetze sie ausdruecklich." % (effective_from, row[0]),
                "effective_from")

    # =====================================================================
    # Schreibeinheiten (bauen, nicht ausfuehren - fuer replace_worktime)
    # =====================================================================
    def _set_unit(self, person_id: int, *, effective_from: str,
                  effective_to: Optional[str], minutes,
                  actor_id: Optional[int], meta: Optional[Any]) -> WriteUnit:
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            self._dublette_pruefen(_con, person_id, effective_from)
            return {"person_id": person_id, "effective_from": effective_from,
                    "effective_to": effective_to,
                    "minutes": dict(zip(_WEEKDAYS, minutes))}

        def _after(_con: sqlite3.Connection, seq: int) -> None:
            _con.execute(
                "INSERT INTO person_worktime "
                "(person_id, mon_min, tue_min, wed_min, thu_min, fri_min, "
                " sat_min, sun_min, effective_from, effective_to, audit_seq, "
                " created_by, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                tuple([person_id] + list(minutes)
                      + [effective_from, effective_to, seq, actor_id, now]))

        return WriteUnit(do_write=_w, event_type=EventType.WORKTIME_SET,
                         actor_id=actor_id, target_type="person_worktime",
                         target_id=str(person_id), meta=meta,
                         after_audit=_after)

    def _remove_unit(self, worktime_id: int, *, actor_id: Optional[int],
                     meta: Optional[Any]) -> WriteUnit:
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            cols = "person_id, effective_from, effective_to, " \
                   + ", ".join(_WEEKDAYS)
            row = _con.execute(
                "SELECT %s, deleted_at FROM person_worktime WHERE id=?" % cols,
                (worktime_id,)).fetchone()
            if row is None:
                raise CapacityError(
                    "Unbekannte Arbeitszeit-Zeile #%s." % worktime_id,
                    "worktime_id")
            if row[len(_WEEKDAYS) + 3] is not None:
                raise CapacityError(
                    "Arbeitszeit-Zeile #%s ist bereits entfernt. Ein zweites "
                    "Entfernen erzeugte einen Beleg ohne Wirkung."
                    % worktime_id, "worktime_id")
            # DER BELEG TRAEGT DIE ENTFERNTEN WERTE. Sonst stuende in der
            # Akte nur "Zeile 7 entfernt" - und was darin stand, muesste man
            # aus der Datenbank rekonstruieren.
            return {"worktime_id": worktime_id, "person_id": row[0],
                    "effective_from": row[1], "effective_to": row[2],
                    "minutes": dict(zip(_WEEKDAYS, row[3:3 + len(_WEEKDAYS)]))}

        def _after(_con: sqlite3.Connection, seq: int) -> None:
            _con.execute(
                "UPDATE person_worktime SET deleted_at=? WHERE id=?",
                (now, worktime_id))

        return WriteUnit(do_write=_w, event_type=EventType.WORKTIME_REMOVED,
                         actor_id=actor_id, target_type="person_worktime",
                         target_id=str(worktime_id), meta=meta,
                         after_audit=_after)

    # =====================================================================
    # Oeffentliche Schreibwege
    # =====================================================================
    def set_worktime(self, person_id: int, *, effective_from: str,
                     mon_min: int = 0, tue_min: int = 0, wed_min: int = 0,
                     thu_min: int = 0, fri_min: int = 0, sat_min: int = 0,
                     sun_min: int = 0, effective_to: Optional[str] = None,
                     actor_id: Optional[int] = None,
                     meta: Optional[Any] = None) -> int:
        """
        Neue datierte Arbeitszeit-Regel setzen (append-only). Gibt die
        audit_log-seq (WORKTIME_SET) zurueck.

        Seit Build 560: eine zweite AKTIVE Regel zum selben Stichtag wird
        ZURUECKGEWIESEN (s. _dublette_pruefen). Korrekturen laufen ueber
        replace_worktime oder ueber remove_worktime + set_worktime.
        """
        minutes = (mon_min, tue_min, wed_min, thu_min, fri_min, sat_min,
                   sun_min)
        self._pruefe(effective_from, minutes)
        return self._writer.audited_write_many([
            self._set_unit(person_id, effective_from=effective_from,
                           effective_to=effective_to, minutes=minutes,
                           actor_id=actor_id, meta=meta)])[0]

    def remove_worktime(self, worktime_id: int, *,
                        actor_id: Optional[int] = None,
                        meta: Optional[Any] = None) -> int:
        """
        Arbeitszeit-Regel entfernen (SOFT-DELETE). Gibt die audit_log-seq
        (WORKTIME_REMOVED) zurueck.

        Die Zeile bleibt in der Datenbank stehen und traegt deleted_at. Sie
        faellt aus der Rechnung (capacity_calculator filtert
        deleted_at IS NULL) und aus der Vorgabeliste - nicht aus dem Bestand.
        """
        return self._writer.audited_write_many([
            self._remove_unit(worktime_id, actor_id=actor_id, meta=meta)])[0]

    def replace_worktime(self, worktime_id: int, person_id: int, *,
                         effective_from: str, mon_min: int = 0,
                         tue_min: int = 0, wed_min: int = 0, thu_min: int = 0,
                         fri_min: int = 0, sat_min: int = 0, sun_min: int = 0,
                         effective_to: Optional[str] = None,
                         actor_id: Optional[int] = None,
                         meta: Optional[Any] = None) -> Dict[str, int]:
        """
        Eine Regel ERSETZEN: alte Zeile entfernen und neue setzen, in EINER
        Transaktion. -> {"entfernt_seq": .., "gesetzt_seq": ..}

        ZWEI BELEGE, KEIN SAMMELBELEG: Entfernen und Setzen sind zwei
        fachliche Handlungen und stehen einzeln in der Kette
        (audited_write_many, Build 534). Schlaegt eine fehl, rollt die
        gesamte Transaktion zurueck - es bleibt weder eine geloeschte Zeile
        ohne Nachfolger noch ein Beleg ohne Wirkung.

        Die REIHENFOLGE ist zwingend: erst entfernen, dann setzen. Andersherum
        schluege die eigene Dublettensperre an, weil die alte Zeile zum
        Zeitpunkt des Setzens noch aktiv waere.
        """
        minutes = (mon_min, tue_min, wed_min, thu_min, fri_min, sat_min,
                   sun_min)
        self._pruefe(effective_from, minutes)
        seqs = self._writer.audited_write_many([
            self._remove_unit(worktime_id, actor_id=actor_id, meta=meta),
            self._set_unit(person_id, effective_from=effective_from,
                           effective_to=effective_to, minutes=minutes,
                           actor_id=actor_id, meta=meta),
        ])
        return {"entfernt_seq": seqs[0], "gesetzt_seq": seqs[1]}

    # ----------------------------------------------------------------- list
    def list_worktime(self, person_id: Optional[int] = None, *,
                      include_deleted: bool = False) -> List[Dict[str, Any]]:
        sql = ("SELECT id, person_id, mon_min, tue_min, wed_min, thu_min, "
               "fri_min, sat_min, sun_min, effective_from, effective_to, "
               "audit_seq, created_by, created_at, deleted_at "
               "FROM person_worktime")
        clauses = []
        params: list = []
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        if person_id is not None:
            clauses.append("person_id = ?")
            params.append(person_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY person_id ASC, effective_from ASC, id ASC"
        cur = self._con.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
