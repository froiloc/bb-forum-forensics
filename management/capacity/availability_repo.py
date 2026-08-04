# =============================================================================
# management/capacity/availability_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# AvailabilityRepo — auditierter Schreibpfad fuer Verfuegbarkeits-Eintraege
# (availability_entry, Schema m008): je Person/Zeitraum eine Garantie ODER eine
# Einschraenkung, ausgedrueckt als Prozent ODER Minuten (genau eines).
#
#   set_availability     -> AVAILABILITY_SET     (neue Zeile, audit_seq==Beleg)
#   remove_availability  -> AVAILABILITY_REMOVED (Soft-Delete deleted_at)
#   replace_availability -> beides in EINER Transaktion  [Build 664]
#
# VALIDIERUNG (klarer Fehler vor DB-CHECK): genau eines von value_pct/
# value_minutes; kind in {garantie, einschraenkung}; value_pct in [0,100];
# value_minutes >= 0; period_start <= period_end; reason_code (falls gesetzt)
# muss ein AKTIVER Grund sein.
#
# KEIN Overlap-Guard: mehrere Garantien/Einschraenkungen fuer denselben
# Zeitraum sind zulaessig; ihr Zusammenspiel loest die Kapazitaets-Berechnung
# (Build 358) auf ("Einschraenkungen im Rahmen der Garantien", §11.4).
#
# BUILD 664 (Ticket 7b2f4a19): BERICHTIGEN STATT LOESCHEN-UND-NEU. Eine
# bestehende Zeile laesst sich jetzt in EINEM Vorgang ersetzen. Der Weg ist
# derselbe wie bei den Arbeitszeiten (replace_worktime, Build 555) und
# AUSDRUECKLICH KEIN UPDATE: die alte Zeile wird stillgelegt und bleibt als
# Beleg stehen. Ein UPDATE schriebe forensische Historie um - danach waere
# nicht mehr feststellbar, was vor der Korrektur in der Akte stand.
#
# Dafuer sind set/remove in WriteUnits zerlegt (_set_unit/_remove_unit), die
# gebaut und NICHT sofort ausgefuehrt werden; erst audited_write_many fuehrt
# sie im selben Transaktionsrahmen aus. Verhalten und Rueckgabe der beiden
# oeffentlichen Einzelwege bleiben unveraendert.
#
# Beleg: Bauplan B7 v1.1 §11.4. Version: v0.8.664 · Build: 664 · 2026-08-04
# =============================================================================

import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.capacity.capacity_errors import CapacityError
from management.capacity.reason_repo import ReasonRepo
from management.gateway.coordinator_writer import WriteUnit

_KINDS = ("garantie", "einschraenkung")


class AvailabilityRepo:
    """Schreibt/liest availability_entry (auditiert, Soft-Delete)."""

    def __init__(self, con: sqlite3.Connection, writer) -> None:
        self._con = con
        self._writer = writer

    # =====================================================================
    # Pruefung (einmal, fuer set UND replace)
    # =====================================================================
    def _pruefe(self, *, period_start: str, period_end: str, kind: str,
                value_pct: Optional[int], value_minutes: Optional[int],
                reason_code: Optional[str]) -> None:
        """
        Klare Fachfehler VOR dem DB-CHECK. Jeder nennt, wo moeglich, das
        schuldige Feld - die Pflegemaske markiert es dann (Build 560);
        bei einem Formular mit sieben Feldern ist ein Satz ohne Feldnamen
        eine Suchaufgabe.
        """
        if kind not in _KINDS:
            raise CapacityError(
                "kind muss 'garantie' oder 'einschraenkung' sein (%r)." % kind,
                "kind")
        if (value_pct is None) == (value_minutes is None):
            raise CapacityError(
                "Genau EINES von value_pct/value_minutes muss gesetzt sein.",
                "value_pct")
        if value_pct is not None and not (0 <= value_pct <= 100):
            raise CapacityError("value_pct muss in [0, 100] liegen.",
                                "value_pct")
        if value_minutes is not None and value_minutes < 0:
            raise CapacityError("value_minutes muss >= 0 sein.",
                                "value_minutes")
        if not period_start or not period_end:
            raise CapacityError(
                "period_start und period_end sind erforderlich.",
                "period_start" if not period_start else "period_end")
        if period_start > period_end:
            raise CapacityError(
                "period_start (%s) liegt nach period_end (%s)."
                % (period_start, period_end), "period_end")
        if reason_code is not None and not ReasonRepo(
                self._con, None).is_active(reason_code):
            raise CapacityError(
                "reason_code '%s' ist kein aktiver Grund." % reason_code,
                "reason_code")

    # =====================================================================
    # Schreibeinheiten (bauen, nicht ausfuehren - fuer replace_availability)
    # =====================================================================
    def _set_unit(self, person_id: int, *, period_start: str,
                  period_end: str, kind: str, value_pct: Optional[int],
                  value_minutes: Optional[int], reason_code: Optional[str],
                  note: Optional[str], actor_id: Optional[int],
                  meta: Optional[Any]) -> WriteUnit:
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            return {"person_id": person_id, "period_start": period_start,
                    "period_end": period_end, "kind": kind,
                    "value_pct": value_pct, "value_minutes": value_minutes,
                    "reason_code": reason_code}

        def _after(_con: sqlite3.Connection, seq: int) -> None:
            _con.execute(
                "INSERT INTO availability_entry "
                "(person_id, period_start, period_end, kind, value_pct, "
                " value_minutes, reason_code, note, audit_seq, created_by, "
                " created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (person_id, period_start, period_end, kind, value_pct,
                 value_minutes, reason_code, note, seq, actor_id, now))

        return WriteUnit(do_write=_w, event_type=EventType.AVAILABILITY_SET,
                         actor_id=actor_id, target_type="availability_entry",
                         target_id=str(person_id), meta=meta,
                         after_audit=_after)

    def _remove_unit(self, entry_id: int, *, actor_id: Optional[int],
                     meta: Optional[Any]) -> WriteUnit:
        now = int(time.time())

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            row = _con.execute(
                "SELECT person_id, period_start, period_end, kind, value_pct, "
                "value_minutes, reason_code, deleted_at "
                "FROM availability_entry WHERE id=?", (entry_id,)).fetchone()
            if row is None:
                raise CapacityError(
                    "availability_entry id=%s nicht vorhanden oder bereits "
                    "entfernt." % entry_id, "entry_id")
            if row[7] is not None:
                raise CapacityError(
                    "availability_entry id=%s nicht vorhanden oder bereits "
                    "entfernt." % entry_id, "entry_id")
            # DER BELEG TRAEGT DIE ENTFERNTEN WERTE (wie bei den
            # Arbeitszeiten, Build 555). Sonst stuende in der Akte nur
            # "Zeile 7 entfernt", und was darin stand, muesste man aus der
            # Datenbank rekonstruieren. Die NOTIZ bleibt draussen: sie ist
            # Freitext und hat im Audit-Payload nichts verloren.
            return {"entry_id": entry_id, "person_id": row[0],
                    "period_start": row[1], "period_end": row[2],
                    "kind": row[3], "value_pct": row[4],
                    "value_minutes": row[5], "reason_code": row[6]}

        def _after(_con: sqlite3.Connection, seq: int) -> None:
            _con.execute(
                "UPDATE availability_entry SET deleted_at=?, updated_at=? "
                "WHERE id=?", (now, now, entry_id))

        return WriteUnit(do_write=_w,
                         event_type=EventType.AVAILABILITY_REMOVED,
                         actor_id=actor_id, target_type="availability_entry",
                         target_id=str(entry_id), meta=meta,
                         after_audit=_after)

    # =====================================================================
    # Oeffentliche Schreibwege
    # =====================================================================
    def set_availability(self, person_id: int, *, period_start: str,
                         period_end: str, kind: str,
                         value_pct: Optional[int] = None,
                         value_minutes: Optional[int] = None,
                         reason_code: Optional[str] = None,
                         note: Optional[str] = None,
                         actor_id: Optional[int] = None,
                         meta: Optional[Any] = None) -> int:
        """Neue Zeile setzen. Gibt die audit_log-seq (AVAILABILITY_SET)."""
        self._pruefe(period_start=period_start, period_end=period_end,
                     kind=kind, value_pct=value_pct,
                     value_minutes=value_minutes, reason_code=reason_code)
        return self._writer.audited_write_many([
            self._set_unit(person_id, period_start=period_start,
                           period_end=period_end, kind=kind,
                           value_pct=value_pct, value_minutes=value_minutes,
                           reason_code=reason_code, note=note,
                           actor_id=actor_id, meta=meta)])[0]

    # --------------------------------------------------------------- remove
    def remove_availability(self, entry_id: int, *,
                            actor_id: Optional[int] = None,
                            meta: Optional[Any] = None) -> int:
        """
        Zeile entfernen (SOFT-DELETE). Gibt die audit_log-seq
        (AVAILABILITY_REMOVED) zurueck.

        Die Zeile bleibt in der Datenbank stehen und traegt deleted_at. Sie
        faellt aus der Rechnung und aus der Standardliste - nicht aus dem
        Bestand.
        """
        return self._writer.audited_write_many([
            self._remove_unit(entry_id, actor_id=actor_id, meta=meta)])[0]

    # -------------------------------------------------------------- replace
    def replace_availability(self, entry_id: int, person_id: int, *,
                             period_start: str, period_end: str, kind: str,
                             value_pct: Optional[int] = None,
                             value_minutes: Optional[int] = None,
                             reason_code: Optional[str] = None,
                             note: Optional[str] = None,
                             actor_id: Optional[int] = None,
                             meta: Optional[Any] = None) -> Dict[str, int]:
        """
        Eine Zeile ERSETZEN: alte entfernen und neue setzen, in EINER
        Transaktion. -> {"entfernt_seq": .., "gesetzt_seq": ..}

        KEIN UPDATE. Die alte Zeile wird stillgelegt und bleibt als Beleg
        stehen; sie ist ueber "Auch entfernte Zeilen anzeigen" weiter
        sichtbar. Ein UPDATE schriebe forensische Historie um.

        ZWEI BELEGE, KEIN SAMMELBELEG: Entfernen und Setzen sind zwei
        fachliche Handlungen und stehen einzeln in der Kette
        (audited_write_many, Build 534). Schlaegt eine fehl, rollt die
        GESAMTE Transaktion zurueck - es bleibt weder eine stillgelegte Zeile
        ohne Nachfolger noch ein Beleg ohne Wirkung.

        REIHENFOLGE erst entfernen, dann setzen. Anders als bei den
        Arbeitszeiten gibt es hier KEINE Dublettensperre - availability_entry
        laesst ueberlappende Zeitraeume ausdruecklich zu (§11.4). Die
        Reihenfolge ist hier also nicht zwingend, wird aber beibehalten:
        eine Abweichung ohne Not waere nur eine weitere Stelle, an der die
        beiden Wege spaeter auseinanderlaufen koennen.

        DIE PRUEFUNG LAEUFT VOR BEIDEM. Sonst wuerde eine Zeile entfernt und
        die Ersetzung erst danach an einem Wertfehler scheitern; die
        Transaktion faenge das zwar ab, aber die Fehlermeldung stuende dann
        neben einem Vorgang, der ueberhaupt nicht haette beginnen duerfen.
        """
        self._pruefe(period_start=period_start, period_end=period_end,
                     kind=kind, value_pct=value_pct,
                     value_minutes=value_minutes, reason_code=reason_code)
        seqs = self._writer.audited_write_many([
            self._remove_unit(entry_id, actor_id=actor_id, meta=meta),
            self._set_unit(person_id, period_start=period_start,
                           period_end=period_end, kind=kind,
                           value_pct=value_pct, value_minutes=value_minutes,
                           reason_code=reason_code, note=note,
                           actor_id=actor_id, meta=meta),
        ])
        return {"entfernt_seq": seqs[0], "gesetzt_seq": seqs[1]}

    # ----------------------------------------------------------------- list
    def list_availability(self, person_id: Optional[int] = None, *,
                          include_deleted: bool = False
                          ) -> List[Dict[str, Any]]:
        sql = ("SELECT id, person_id, period_start, period_end, kind, "
               "value_pct, value_minutes, reason_code, note, audit_seq, "
               "created_by, created_at, updated_at, deleted_at "
               "FROM availability_entry")
        clauses = []
        params: list = []
        if not include_deleted:
            clauses.append("deleted_at IS NULL")
        if person_id is not None:
            clauses.append("person_id = ?")
            params.append(person_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY person_id ASC, period_start ASC, id ASC"
        cur = self._con.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
