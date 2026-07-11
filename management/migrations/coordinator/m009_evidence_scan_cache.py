# =============================================================================
# management/migrations/coordinator/m009_evidence_scan_cache.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M009 — coordinator.db (ADDITIV)
#   Legt den SCAN-CACHE fuer die Berichts-Abnahme an (Build 374).
#
#   Problem: Berichte liegen NICHT in coordinator.db, sondern je Fall in
#   evidence_<uid>.db. Bei mehreren hundert Faellen waere ein Vollscan bei jedem
#   Seitenaufruf teuer (gemessen: ~0,54 ms je DB, 300 DBs ~161 ms).
#
#   Loesung: Fingerabdruck je Fall ueber ALLE zur DB gehoerenden Dateien
#   (.db, -wal, -shm; jeweils Groesse + mtime_ns). Aendert sich nichts, wird die
#   DB nicht angefasst und die gecachte Berichtsliste verwendet.
#
#   WICHTIG — WAL-Falle (gemessen, Build 374): Ein UPDATE im WAL-Modus aendert
#   mtime und Groesse der .db-Datei NICHT; nur die -wal-Datei aendert sich.
#   Ein Cache, der nur die .db statet, wuerde geaenderte Berichte STILL
#   uebersehen (Grundregel 1). Daher werden alle Dateien einbezogen.
#
#   BERATENDER CHARAKTER (mc 2026-07-10): Der Cache ist ein BESCHLEUNIGER, nie
#   die Quelle der Wahrheit. In PROD (Windows/UNC/SMB) kann mtime grob oder
#   verzoegert sein -> Cache-Treffer = ueberspringen, Fehltreffer = lesen; ein
#   Vollscan-Schalter erzwingt das Neulesen. Fuer BEWEISRELEVANTES (Siegel,
#   Build 376) zaehlt NIEMALS mtime, sondern ausschliesslich der Inhaltshash.
#
#   Der Cache traegt KEIN audit_seq: er enthaelt keine Ermittlungsergebnisse,
#   sondern nur wiederherstellbare Metadaten (jederzeit durch Neuscan erzeugbar).
#   Er ist damit bewusst KEIN auditierter Schreibpfad — sonst wuerde jeder
#   Seitenaufruf das Audit-Log fluten.
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + Guard (INFO-No-op).
# Version: v0.7.374 · Build: 374 · 2026-07-10
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 9
NAME = "Evidence-Scan-Cache (Berichts-Abnahme)"
KIND = "additive"

# evidence_scan_cache: ein Eintrag je Fall (user_id).
#   fingerprint  — kanonischer Fingerabdruck aller DB-Dateien (siehe Scanner)
#   reports_json — die zuletzt gelesene Berichtsliste dieses Falls (JSON)
#   scanned_at   — Zeitpunkt des letzten erfolgreichen Einlesens
#   error        — Fehlertext, falls die DB nicht lesbar war (NICHT verschweigen!)
_DDL_CACHE = """
CREATE TABLE IF NOT EXISTS evidence_scan_cache (
    user_id      INTEGER PRIMARY KEY,
    fingerprint  TEXT    NOT NULL,
    reports_json TEXT    NOT NULL DEFAULT '[]',
    scanned_at   INTEGER NOT NULL,
    error        TEXT
)
"""

_DDL_IDX = """
CREATE INDEX IF NOT EXISTS evidence_scan_cache_scanned_idx
    ON evidence_scan_cache(scanned_at)
"""

_TABLES = ("evidence_scan_cache",)
_INDICES = (("evidence_scan_cache_scanned_idx", _DDL_IDX),)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _index_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,)).fetchone() is not None


def up(con: sqlite3.Connection) -> None:
    if (all(_table_exists(con, t) for t in _TABLES)
            and all(_index_exists(con, ix) for ix, _ in _INDICES)):
        logger.info("M009: Evidence-Scan-Cache bereits vorhanden — No-op.")
        return

    con.execute(_DDL_CACHE)
    for _name, ddl in _INDICES:
        con.execute(ddl)

    # Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner).
    for t in _TABLES:
        if not _table_exists(con, t):
            raise RuntimeError("M009: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M009: Index '%s' fehlt nach up()." % ix)
