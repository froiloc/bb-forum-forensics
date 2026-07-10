# =============================================================================
# management/support_overview/support_overview_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   NUR-LESENDES Read-Model der Support-Sitzungs-HISTORIE (Build 330). Baut die
#   permanente 'wer sah wann welchen Fall'-Uebersicht AUS dem hash-verketteten
#   audit_log (Ereignistypen SUPPORT_SESSION_STARTED / SUPPORT_SESSION_ENDED)
#   und reichert sie um Klarnamen an (person, cases.username).
#
#   WARUM audit_log und nicht support_sessions? Die support_sessions-Tabelle ist
#   FLUECHTIGE Praesenz (prunebar) — beendete/veraltete Zeilen werden von prune()
#   entfernt. Der PERMANENTE Zugriffsbeleg lebt ausschliesslich im audit_log
#   (Start/Ende auditiert, Heartbeats bewusst nicht). Fuer eine forensische
#   Historie ist daher das audit_log die einzig vollstaendige Quelle.
#   (Beleg: support_sessions_repo.py Kopf; Uebergabe B7 §6.)
#
#   Zugriffs-Stil: DIREKTE Verbindung auf coordinator.db mit UNQUALIFIZIERTEN
#   Tabellennamen — konsistent mit DashboardRepo/CasesRepo (Management-Seite).
#
#   KEIN Schreibpfad, KEIN CoordinatorWriter, KEINE Migration. coordinator.db ist
#   ohnehin nur-lesend (Produktivbetrieb-Regel ab 2026-07-01) -> dieser Build
#   traegt KEIN Datenverlust-Risiko.
#
# REKONSTRUKTIONS-VERTRAG (belegt):
#   Verknuepfungsschluessel ist content.session_id (in JEDEM der drei Schreib-
#   pfade start()/end()/close_orphans() gesetzt). target_id taugt NICHT:
#   STARTED.target_id = user_id, ENDED.target_id = session_id (Asymmetrie).
#   Der ENDED-Payload traegt supporter_id NICHT -> der Supporter kommt allein
#   aus dem STARTED-Beleg.
#
# GRUNDREGEL 1: Keine Sitzung wird still verworfen. Unvollstaendige/auffaellige
#   Belege (STARTED ohne ENDED, ENDED ohne STARTED, doppeltes ENDED, fehlende
#   session_id) werden als Datensatz mit passendem Status/anomaly GEFUEHRT.
#
# Version: v0.7.330 · Build: 330 · 2026-07-07
# =============================================================================

import json
import logging
import sqlite3
from typing import Dict, List, Optional, Tuple

from management.audit.event_types import EventType
from management.support_overview.support_session_record import (
    ANOMALY_DOUBLE_ENDED,
    ANOMALY_DOUBLE_STARTED,
    ANOMALY_MISSING_SESSION_ID,
    STATUS_DANGLING,
    STATUS_ENDED_CLEAN,
    STATUS_ENDED_ORPHAN,
    STATUS_OPEN,
    SupportSessionRecord,
)

logger = logging.getLogger(__name__)

# Grund-Marke einer per Zeitueberschreitung (System) beendeten Waise.
# Muss exakt dem Wert entsprechen, den close_orphans() in den Payload schreibt
# (support_sessions_repo.py: payload.reason='orphan_timeout', Build 328).
_REASON_ORPHAN_TIMEOUT = "orphan_timeout"

# Pflichttabellen des Read-Models. audit_log ist die HARTE Quelle; person
# und cases dienen der Namensaufloesung. Fehlt eine, wird NICHT still degradiert,
# sondern mit handlungsleitender Meldung abgebrochen (Grundregel 1; konsistent
# zu DashboardRepo.REQUIRED_TABLES).
REQUIRED_TABLES = ("audit_log", "person", "cases")


class SupportOverviewSchemaError(Exception):
    """
    Erforderliche coordinator.db-Tabelle fehlt (z. B. audit_log ohne M001 oder
    cases ohne M002). Traegt eine handlungsleitende Meldung (welche Tabelle,
    was zu tun ist).
    """


class _SessionAccumulator:
    """
    Interner, veraenderlicher Sammler EINER Sitzung waehrend des Chain-Durchlaufs.
    Wird am Ende in ein unveraenderliches SupportSessionRecord gegossen. Bewusst
    gekapselt (Grundregel 10-Geist), aber modul-privat — kein Teil der API.
    """

    __slots__ = (
        "session_id", "user_id",
        "supporter_id",
        "started_at", "ended_at", "duration_sec", "reason",
        "started_seq", "ended_seq", "started_ts", "ended_ts",
        "started_actor_id", "ended_actor_id",
        "anomaly",
    )

    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        self.user_id: Optional[int] = None
        self.supporter_id: Optional[int] = None
        self.started_at: Optional[int] = None
        self.ended_at: Optional[int] = None
        self.duration_sec: Optional[int] = None
        self.reason: Optional[str] = None
        self.started_seq: Optional[int] = None
        self.ended_seq: Optional[int] = None
        self.started_ts: Optional[int] = None
        self.ended_ts: Optional[int] = None
        self.started_actor_id: Optional[int] = None
        self.ended_actor_id: Optional[int] = None
        self.anomaly: Optional[str] = None

    def _mark_anomaly(self, code: str) -> None:
        # Erste Anomalie gewinnt (die Anzeige braucht genau einen Hinweis); ein
        # spaeterer Code ueberschreibt nicht, damit die Meldung stabil bleibt.
        if self.anomaly is None:
            self.anomaly = code

    def apply_started(self, payload: dict, seq: int, ts: int,
                      actor_id: Optional[int]) -> None:
        if self.started_seq is not None:
            # Zweites STARTED fuer dieselbe session_id — darf nicht vorkommen.
            self._mark_anomaly(ANOMALY_DOUBLE_STARTED)
            return  # ersten Beleg behalten
        self.started_at = _as_int_or_none(payload.get("started_at"))
        self.supporter_id = _as_int_or_none(payload.get("supporter_id"))
        if self.user_id is None:
            self.user_id = _as_int_or_none(payload.get("user_id"))
        self.started_seq = seq
        self.started_ts = ts
        self.started_actor_id = actor_id

    def apply_ended(self, payload: dict, seq: int, ts: int,
                   actor_id: Optional[int]) -> None:
        if self.ended_seq is not None:
            # Zweites ENDED — idempotentes end() sollte das verhindern; falls es
            # doch auftritt, den ersten Beleg behalten und markieren.
            self._mark_anomaly(ANOMALY_DOUBLE_ENDED)
            return
        self.ended_at = _as_int_or_none(payload.get("ended_at"))
        self.duration_sec = _as_int_or_none(payload.get("duration_sec"))
        self.reason = payload.get("reason")  # None = sauberes Ende
        if self.user_id is None:
            self.user_id = _as_int_or_none(payload.get("user_id"))
        self.ended_seq = seq
        self.ended_ts = ts
        self.ended_actor_id = actor_id

    def status(self) -> str:
        has_started = self.started_seq is not None
        has_ended = self.ended_seq is not None
        if has_started and has_ended:
            if self.reason == _REASON_ORPHAN_TIMEOUT:
                return STATUS_ENDED_ORPHAN
            return STATUS_ENDED_CLEAN
        if has_started and not has_ended:
            return STATUS_OPEN
        # not has_started and has_ended  -> ENDED ohne STARTED
        return STATUS_DANGLING

    def anchor_ts(self) -> int:
        """
        Anker-Zeitstempel fuer die chronologische Ordnung. Bevorzugt started_at
        (der natuerliche Sitzungsbeginn); faellt sonst auf ended_at, dann auf die
        Schreibzeitpunkte zurueck (fuer 'herrenlose' ENDED ohne started_at).
        """
        for candidate in (self.started_at, self.started_ts,
                          self.ended_at, self.ended_ts):
            if candidate is not None:
                return int(candidate)
        return 0


def _as_int_or_none(value) -> Optional[int]:
    """Robuste int-Konvertierung; None/ungueltig -> None (kein stiller Crash)."""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class SupportOverviewRepo:
    """
    NUR-LESENDES Aggregat ueber coordinator.db fuer die Support-Sitzungs-
    Historie. Rekonstruiert Sitzungen aus dem audit_log und reichert Klarnamen
    aus person/cases an.
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row

    def _check_required_tables(self) -> None:
        """
        Prueft VOR der Abfrage, ob alle Pflichttabellen existieren. Fehlt eine,
        wird statt eines rohen sqlite3.OperationalError ein handlungsleitender
        SupportOverviewSchemaError geworfen (nennt Tabelle + Migrationslauf).
        """
        have = {
            row[0] for row in self._con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = [t for t in REQUIRED_TABLES if t not in have]
        if missing:
            raise SupportOverviewSchemaError(
                "Erforderliche Tabelle(n) fehlen in coordinator.db: %s. "
                "Bitte ausstehende Migrationen anwenden: "
                "python -m management.migrate" % ", ".join(missing)
            )

    def _load_investigators(self) -> Dict[int, Tuple[str, str]]:
        """id -> (system_username, display_name). Fuer die Supporter-Aufloesung."""
        out: Dict[int, Tuple[str, str]] = {}
        for r in self._con.execute(
            "SELECT id, system_username, display_name FROM person"
        ):
            out[int(r["id"])] = (r["system_username"], r["display_name"])
        return out

    def _load_case_usernames(self) -> Dict[int, str]:
        """user_id -> cases.username (Forum-Benutzername des betroffenen Nutzers)."""
        out: Dict[int, str] = {}
        for r in self._con.execute("SELECT user_id, username FROM cases"):
            out[int(r["user_id"])] = r["username"]
        return out

    def list_support_sessions(self) -> List[SupportSessionRecord]:
        """
        Liefert die VOLLSTAENDIGE Support-Sitzungs-Historie (mc 2026-07-07:
        immer Vollhistorie, kein Zeitfilter) als flache, chronologisch geordnete
        Liste. Jede Sitzung ist aus ihren audit_log-Belegen rekonstruiert.

        Ordnung (mc 2026-07-07): aufsteigend nach Anker-Zeitstempel
        (started_at, sonst Ersatz), Tiebreak session_id — deterministisch und
        reproduzierbar. Die Frontend-Schicht erlaubt beliebige Umsortierung.

        EINE Abfrage ueber die zwei Support-Ereignistypen; O(n) Zusammenbau.
        """
        self._check_required_tables()

        investigators = self._load_investigators()
        case_usernames = self._load_case_usernames()

        # Chronologische Belegreihenfolge ist zwingend: STARTED kommt (per
        # monotoner seq) vor dem zugehoerigen ENDED. So ist beim ENDED der
        # Sammler bereits angelegt.
        rows = self._con.execute(
            "SELECT seq, ts, actor_id, event_type, content "
            "FROM audit_log "
            "WHERE event_type IN (?, ?) "
            "ORDER BY seq ASC",
            (EventType.SUPPORT_SESSION_STARTED,
             EventType.SUPPORT_SESSION_ENDED),
        ).fetchall()

        # session_id -> Sammler. Fehlt die session_id im Payload (belegt-untypisch,
        # aber Grundregel 1: nie still verwerfen), bekommt der Beleg einen eigenen
        # Negativ-Schluessel, damit er als eigener, markierter Datensatz erscheint.
        acc: Dict[int, _SessionAccumulator] = {}
        missing_id_counter = 0

        for r in rows:
            seq = int(r["seq"])
            ts = int(r["ts"])
            actor_id = r["actor_id"]
            actor_id = int(actor_id) if actor_id is not None else None
            event_type = r["event_type"]

            try:
                payload = json.loads(r["content"])
                if not isinstance(payload, dict):
                    payload = {}
            except (ValueError, TypeError):
                # Nicht-parsbarer content — extrem untypisch (kanonisches JSON),
                # aber nicht still uebergehen: leerer Payload + Anomalie unten.
                payload = {}

            sid = _as_int_or_none(payload.get("session_id"))
            if sid is None:
                missing_id_counter += 1
                key = -missing_id_counter  # eindeutiger Negativ-Schluessel
                a = _SessionAccumulator(session_id=0)
                a._mark_anomaly(ANOMALY_MISSING_SESSION_ID)
                acc[key] = a
            else:
                key = sid
                a = acc.get(key)
                if a is None:
                    a = _SessionAccumulator(session_id=sid)
                    acc[key] = a

            if event_type == EventType.SUPPORT_SESSION_STARTED:
                a.apply_started(payload, seq, ts, actor_id)
            else:  # SUPPORT_SESSION_ENDED
                a.apply_ended(payload, seq, ts, actor_id)

        records: List[SupportSessionRecord] = []
        for a in acc.values():
            sup_sys: Optional[str] = None
            sup_disp: Optional[str] = None
            if a.supporter_id is not None:
                found = investigators.get(a.supporter_id)
                if found is not None:
                    sup_sys, sup_disp = found

            username: Optional[str] = None
            if a.user_id is not None:
                username = case_usernames.get(a.user_id)

            records.append(SupportSessionRecord(
                session_id=a.session_id,
                user_id=(a.user_id if a.user_id is not None else 0),
                username=username,
                supporter_id=a.supporter_id,
                supporter_system_username=sup_sys,
                supporter_display_name=sup_disp,
                started_at=a.started_at,
                ended_at=a.ended_at,
                duration_sec=a.duration_sec,
                reason=a.reason,
                status=a.status(),
                started_seq=a.started_seq,
                ended_seq=a.ended_seq,
                started_ts=a.started_ts,
                ended_ts=a.ended_ts,
                started_actor_id=a.started_actor_id,
                ended_actor_id=a.ended_actor_id,
                anomaly=a.anomaly,
            ))

        # Deterministische chronologische Ordnung (Anker aufsteigend, dann
        # session_id). _anchor je Datensatz via Sammler nicht mehr verfuegbar,
        # daher aus dem Record neu bestimmt (gleiche Regel).
        def _anchor(rec: SupportSessionRecord) -> Tuple[int, int]:
            for c in (rec.started_at, rec.started_ts, rec.ended_at, rec.ended_ts):
                if c is not None:
                    return (int(c), rec.session_id)
            return (0, rec.session_id)

        records.sort(key=_anchor)
        return records
