# =============================================================================
# management/reports/approved_reports_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Berichts-Versiegelung
# =============================================================================
# ApprovedReportsDb — die ZENTRALE Siegel-Datenbank (approved_reports.db).
#
# ZWECK (mc 2026-07-10): Ein freigegebener Bericht wird an ZWEI Orten gesichert,
# weil beide verschiedene Aufgaben haben:
#
#   1) DURCHSETZUNG — in der evidence_<uid>.db: reports.status = approved/final.
#      Dort wird geschrieben, also muss dort auch gesperrt werden (der Ermittler-
#      Webserver verweigert kuenftig Aenderungen; Build 378). Die Spalte gibt es
#      bereits -> KEINE Schemaaenderung an evidence (Migrationsvorbehalt!).
#
#   2) BEWEIS — hier, zentral: das vollstaendige statische ABBILD des Berichts
#      plus sein kanonischer INHALTSHASH (ReportSealer). Diese DB liegt ausserhalb
#      der Reichweite des Ermittlers.
#
#   Warum beides? Die evidence-seitige Sperre schuetzt gegen den NORMALEN Weg
#   (die Anwendung). Sie schuetzt NICHT gegen jemanden, der die evidence-DB
#   direkt mit einem SQLite-Werkzeug manipuliert. Genau dagegen wirkt der
#   zentrale Hash: beim Nachpruefen wird der Bericht neu gehasht und verglichen —
#   ABWEICHUNG = MANIPULATION, nachweisbar.
#
# RECHTE: Geschrieben wird ausschliesslich ueber den auditierten Freigabe-Pfad
#   (reports.approve, Scope 'alle' -> faktisch der Supervisor). Gelesen (verify)
#   darf jeder, der die Berichte sehen darf.
#
# Diese DB ist eine reine ABLAGE (kein Audit-Log): der Beleg der Freigabe liegt
#   im audit_log der coordinator.db (REPORT_APPROVED) und wird hier per
#   audit_seq referenziert — die Kette bleibt damit nachvollziehbar.
#
# SCHLUESSEL (M019, Build 469): Die API dieses Moduls ist subject_id-nativ.
#   Die PHYSISCHE Spalte der approved_reports.db heisst weiterhin 'user_id' —
#   diese DB ist eine eigenstaendige Siegel-Ablage und wurde von Migration M019
#   (nur coordinator.db) NICHT umbenannt. Bestehende Siegel-DBs aus dem
#   Produktivbetrieb duerfen nicht angefasst werden (Migrationsvorbehalt).
#   Nach aussen wird die Spalte per SQL-Alias 'user_id AS subject_id'
#   abgebildet; fuer Realnutzer gilt subject_id == user_id (verlustfrei).
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
#   Build 469: Schluesselumstellung user_id -> subject_id (M019)
# =============================================================================

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from db.journal_policy import apply_journal_mode  # NEU Build 408

_DDL = """
CREATE TABLE IF NOT EXISTS approved_reports (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,          -- Fall; Wert = subject_id (Spaltenname vor M019, s. Kopf)
    report_id      INTEGER NOT NULL,          -- reports.id in jener DB
    content_sha256 TEXT    NOT NULL,          -- kanonischer Inhaltshash
    snapshot_json  TEXT    NOT NULL,          -- vollstaendiges statisches Abbild
    title          TEXT    NOT NULL,
    report_type    TEXT    NOT NULL,
    sequence_nr    INTEGER NOT NULL,
    created_by     TEXT    NOT NULL,          -- Verfasser des Berichts
    approved_by    TEXT    NOT NULL,          -- Kennung des Freigebenden
    approved_by_id INTEGER,                   -- person.id des Freigebenden
    approved_at    INTEGER NOT NULL,
    is_final       INTEGER NOT NULL DEFAULT 0,
    note           TEXT,
    audit_seq      INTEGER NOT NULL,          -- Beleg in coordinator.audit_log
    -- Verhindert versehentliche Doppel-Siegel DESSELBEN Inhalts auf DERSELBEN
    -- Stufe. is_final gehoert dazu: die Aufwertung 'approved' -> 'final' siegelt
    -- denselben Inhalt erneut (der Inhalt aendert sich dabei ja gerade NICHT) —
    -- das ist ein legitimer zweiter Siegel-Eintrag, kein Duplikat.
    UNIQUE(user_id, report_id, content_sha256, is_final)
)
"""

_DDL_IDX = """
CREATE INDEX IF NOT EXISTS approved_reports_case_idx
    ON approved_reports(user_id, report_id, approved_at)
"""

#: Ergebnis-Schluessel der Lese-API (subject_id-nativ, M019). Die physische
#: Spalte heisst weiterhin user_id (s. Kopf) und wird per Alias abgebildet.
_COLS = ("id", "subject_id", "report_id", "content_sha256", "title",
         "report_type", "sequence_nr", "created_by", "approved_by",
         "approved_by_id", "approved_at", "is_final", "note", "audit_seq")

#: SELECT-Spaltenliste: physischer Spaltenname + Alias auf den API-Schluessel.
_SELECT_COLS = ", ".join(
    "user_id AS subject_id" if c == "subject_id" else c for c in _COLS)


class ApprovedReportsDb:
    """Zugriff auf die zentrale Siegel-Datenbank."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def ensure_schema(self) -> None:
        """Legt DB und Tabelle an (idempotent)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(str(self._path))
        try:
            con.isolation_level = None
            # Build 408: siehe db/journal_policy.py (WAL, sonst Rueckfall).
            apply_journal_mode(con, str(self._path))
            con.execute(_DDL)
            con.execute(_DDL_IDX)
        finally:
            con.close()

    # ---------------------------------------------------------------- writes
    def seal(self, *, subject_id: int, report_id: int, content_sha256: str,
             snapshot_json: str, report: Dict[str, Any], approved_by: str,
             approved_by_id: Optional[int], is_final: bool,
             note: Optional[str], audit_seq: int) -> int:
        """Legt ein Siegel ab. Gibt die Zeilen-ID zurueck."""
        self.ensure_schema()
        con = sqlite3.connect(str(self._path))
        try:
            con.isolation_level = None
            # Spaltenname user_id: physisches Schema dieser nicht migrierten
            # Siegel-DB (s. Kopf); der Wert IST die subject_id.
            cur = con.execute(
                "INSERT INTO approved_reports "
                "(user_id, report_id, content_sha256, snapshot_json, title, "
                " report_type, sequence_nr, created_by, approved_by, "
                " approved_by_id, approved_at, is_final, note, audit_seq) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (subject_id, report_id, content_sha256, snapshot_json,
                 report.get("title"), report.get("report_type"),
                 report.get("sequence_nr"), report.get("created_by"),
                 approved_by, approved_by_id, int(time.time()),
                 1 if is_final else 0, note, audit_seq))
            return int(cur.lastrowid)
        finally:
            con.close()

    # ----------------------------------------------------------------- reads
    def _ro(self) -> Optional[sqlite3.Connection]:
        if not self._path.exists():
            return None
        return sqlite3.connect("file:%s?mode=ro" % self._path, uri=True)

    def latest_seal(self, subject_id: int,
                    report_id: int) -> Optional[Dict[str, Any]]:
        """Juengstes Siegel eines Berichts (oder None)."""
        con = self._ro()
        if con is None:
            return None
        try:
            # WHERE user_id: physischer Spaltenname (nicht migrierte DB, s. Kopf).
            row = con.execute(
                "SELECT %s FROM approved_reports "
                "WHERE user_id=? AND report_id=? "
                "ORDER BY approved_at DESC, id DESC LIMIT 1" % _SELECT_COLS,
                (subject_id, report_id)).fetchone()
            return dict(zip(_COLS, row)) if row else None
        except sqlite3.Error:
            return None
        finally:
            con.close()

    def list_seals(self) -> List[Dict[str, Any]]:
        """Alle Siegel (ohne das grosse snapshot_json)."""
        con = self._ro()
        if con is None:
            return []
        try:
            rows = con.execute(
                "SELECT %s FROM approved_reports "
                "ORDER BY approved_at DESC, id DESC" % _SELECT_COLS).fetchall()
            return [dict(zip(_COLS, r)) for r in rows]
        except sqlite3.Error:
            return []
        finally:
            con.close()

    def snapshot_json(self, seal_id: int) -> Optional[str]:
        con = self._ro()
        if con is None:
            return None
        try:
            row = con.execute(
                "SELECT snapshot_json FROM approved_reports WHERE id=?",
                (seal_id,)).fetchone()
            return row[0] if row else None
        finally:
            con.close()
