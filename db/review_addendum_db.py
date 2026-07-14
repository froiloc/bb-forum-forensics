# =============================================================================
# db/review_addendum_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Vermaehlung B6xB7
# SF-3 (Build 412): Kommentar-Brücke über Addendum-Dateien
# =============================================================================
# Zweck:
#   Lektorat (W4) und Chef-Freigabe (W5) hinterlegen Kommentare zum Berichts-
#   TEXT. Diese duerfen NICHT in die evidence_<uid>.db geschrieben werden
#   (Migrationsvorbehalt ab 01.07.2026; Regel "nie zwei Schreiber pro Datei" —
#   der Ermittler-Webserver haelt die evidence_<uid>.db live offen).
#
#   Modell (mc 2026-07-14, Konzept v0.2 §4): "Eine Person, ein Fall, genau EINE
#   Datei" — jede kommentierende Person schreibt AUSSCHLIESSLICH ihre eigene
#   Addendum-Datei; alle Interessierten LESEN. Kein Transport, kein Merge, kein
#   Loeschen zur Laufzeit ("lesen am Ort"). Die Datei ist Point-of-Truth ihres
#   Besitzers.
#
#   Ablage (Bucket-Sharding gegen ein Fluten von ./data/evidence/):
#       ./data/evidence/addenda/<bucket>/<uid>/evidence_<uid>_<pid>.db
#       bucket = md5(str(uid))[:2]           # 256 Buckets '00'..'ff'
#   Die Ordner-Trennung haelt Addenda ausserdem ausser Reichweite des noch
#   loeschenden Cross-Annotation-Integrators (der nur den Altpfad kennt).
#
# Journalmodus: 'delete' (Build 408/409 — kein WAL, netzlaufwerksicher).
#
# Version: v0.7.412 · Build: 412 · 2026-07-14
# =============================================================================

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Erlaubte Kommentar-Zustaende (deckungsgleich mit report_comments in der
# evidence_<uid>.db, db/evidence_db.py:318-330 — bewusste Formgleichheit).
VALID_STATUS = ("pending", "addressed", "dismissed", "revoked")

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    schema_version INTEGER NOT NULL,
    uid            INTEGER NOT NULL,
    owner_pid      INTEGER NOT NULL,
    created_at     INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS review_comments (
    comment_id        TEXT    PRIMARY KEY,
    report_id         INTEGER NOT NULL,
    block_id          TEXT,
    reviewer_pid      INTEGER NOT NULL,
    reviewer_role     TEXT    NOT NULL,
    comment_text      TEXT    NOT NULL,
    suggested_content TEXT,
    status            TEXT    NOT NULL
                      CHECK(status IN ('pending','addressed','dismissed','revoked')),
    block_sha256      TEXT,
    created_at        INTEGER NOT NULL,
    resolved_at       INTEGER
);
CREATE INDEX IF NOT EXISTS rc_report_idx ON review_comments (report_id);
CREATE INDEX IF NOT EXISTS rc_block_idx  ON review_comments (block_id);
"""

_SCHEMA_VERSION = 1


def bucket_for(uid: int) -> str:
    """Deterministischer 2-Hex-Bucket (256) aus md5(str(uid))[:2] (mc)."""
    return hashlib.md5(str(int(uid)).encode("ascii")).hexdigest()[:2]


def addendum_path(evidence_dir: str, uid: int, pid: int) -> Path:
    """Vollstaendiger Pfad der Addendum-Datei einer Person zu einem Fall."""
    return (
        Path(evidence_dir) / "addenda" / bucket_for(uid) / str(int(uid))
        / ("evidence_%d_%d.db" % (int(uid), int(pid)))
    )


def open_addendum(evidence_dir: str, uid: int, pid: int,
                  *, create: bool = True) -> Optional["ReviewAddendumDb"]:
    """
    Oeffnet (und legt bei create=True an) die Addendum-Datei fuer (uid, pid) und
    gibt eine schreibfaehige ReviewAddendumDb zurueck. create=False + Datei
    fehlt -> None (kein leeres Anlegen beim reinen Lesen/Resolvieren).
    Journalmodus 'delete' (kein WAL); busy_timeout gegen kurzzeitige Sperren.
    """
    path = addendum_path(evidence_dir, uid, pid)
    if not create and not path.exists():
        return None
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=5.0, check_same_thread=False)
    con.row_factory = sqlite3.Row
    # Explizite Transaktionssteuerung: wir setzen BEGIN IMMEDIATE/COMMIT selbst
    # (kein impliziter Autobegin, der mit dem manuellen BEGIN kollidierte).
    con.isolation_level = None
    con.execute("PRAGMA journal_mode=delete")   # Build 408/409: kein WAL
    con.execute("PRAGMA busy_timeout=5000")
    return ReviewAddendumDb(con, uid=uid, owner_pid=pid)


class ReviewAddendumDb:
    """
    Schreibfaehiger Zugriff auf die Addendum-Datei GENAU EINER Person zu einem
    Fall. Es schreibt ausschliesslich der Besitzer (owner_pid) — der Aufrufer
    stellt das ueber den Pfad (pid == person_id) sicher.
    """

    def __init__(self, con: sqlite3.Connection, *, uid: int,
                 owner_pid: int) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._uid = int(uid)
        self._owner_pid = int(owner_pid)
        self._setup_schema()

    # ------------------------------------------------------------------
    def _setup_schema(self) -> None:
        """Legt Tabellen/Indizes an (idempotent) und stempelt meta einmalig."""
        self._con.executescript(_SCHEMA_DDL)
        row = self._con.execute("SELECT COUNT(*) AS c FROM meta").fetchone()
        if row["c"] == 0:
            self._con.execute(
                "INSERT INTO meta (schema_version, uid, owner_pid, created_at) "
                "VALUES (?, ?, ?, ?)",
                (_SCHEMA_VERSION, self._uid, self._owner_pid, int(time.time())),
            )
        self._con.commit()

    # ------------------------------------------------------------------
    def add_comment(
        self, *,
        report_id: int,
        block_id: Optional[str],
        reviewer_role: str,
        comment_text: str,
        suggested_content: Optional[str] = None,
        block_sha256: Optional[str] = None,
        comment_id: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> str:
        """
        Legt einen Kommentar (status='pending') an. Gibt die comment_id zurueck.
        reviewer_pid ist IMMER der Besitzer der Datei (owner_pid).
        """
        cid = comment_id or uuid.uuid4().hex
        now = int(ts if ts is not None else time.time())
        self._con.execute("BEGIN IMMEDIATE")
        try:
            self._con.execute(
                "INSERT INTO review_comments (comment_id, report_id, block_id, "
                "reviewer_pid, reviewer_role, comment_text, suggested_content, "
                "status, block_sha256, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, NULL)",
                (cid, int(report_id), block_id, self._owner_pid,
                 str(reviewer_role), str(comment_text), suggested_content,
                 block_sha256, now),
            )
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise
        return cid

    # ------------------------------------------------------------------
    def set_status(self, comment_id: str, status: str,
                   *, ts: Optional[int] = None) -> bool:
        """
        Setzt den Status eines EIGENEN Kommentars (der/die Kommentierende
        schliesst den eigenen Einwand). status='pending' loescht resolved_at.
        """
        if status not in VALID_STATUS:
            raise ValueError("Ungueltiger Status: %r" % status)
        now = int(ts if ts is not None else time.time())
        resolved_at = None if status == "pending" else now
        self._con.execute("BEGIN IMMEDIATE")
        try:
            cur = self._con.execute(
                "UPDATE review_comments SET status = ?, resolved_at = ? "
                "WHERE comment_id = ?",
                (status, resolved_at, comment_id),
            )
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    def get_comment(self, comment_id: str) -> Optional[Dict[str, Any]]:
        row = self._con.execute(
            "SELECT * FROM review_comments WHERE comment_id = ?", (comment_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def get_comments(self, report_id: Optional[int] = None) -> List[Dict[str, Any]]:
        if report_id is None:
            rows = self._con.execute(
                "SELECT * FROM review_comments "
                "ORDER BY block_id ASC, created_at ASC"
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT * FROM review_comments WHERE report_id = ? "
                "ORDER BY block_id ASC, created_at ASC", (int(report_id),)
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    def close(self) -> None:
        try:
            self._con.close()
        except Exception:  # pragma: no cover
            pass
