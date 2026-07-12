# =============================================================================
# management/cases/case_detector.py
# IT-Forensisches Ermittlungswerkzeug — Fall-Autodetektion
# =============================================================================
# CaseDetector — gleicht die auf der Platte liegenden Faelle mit der Fallakte
# (coordinator.db -> cases) ab. REIN LESEND; das Aufnehmen neuer Faelle ist ein
# eigener, AUDITIERTER Vorgang (CaseImporter).
#
# WAS EINEN FALL DEFINIERT (mc 2026-07-10):
#   Ein Fall EXISTIERT, sobald der Prepper seine forensic_<uid>.db geliefert hat
#   — unabhaengig davon, ob schon jemand daran gearbeitet hat. evidence_<uid>.db
#   und assets_<uid>.db entstehen erst durch die Ermittlungsarbeit und sind
#   daher KEIN Existenzkriterium, sondern nur Arbeitsstand.
#
#   Der BENUTZERNAME kommt autoritativ aus forensic_<uid>.db -> uid_profile
#   (NOT NULL, direkt aus users.username uebernommen).
#
# VIER ZUSTAENDE:
#   ok         Fall in cases UND forensic_<uid>.db vorhanden.
#   neu        forensic_<uid>.db da, aber NICHT in cases -> aufnehmbar.
#   vermisst   in cases, aber KEINE forensic_<uid>.db mehr -> MELDEN.
#   unlesbar   DB da, aber nicht lesbar / uid_profile fehlt -> MELDEN.
#
# GRUNDREGEL 1: 'vermisst' und 'unlesbar' werden NIE still uebersprungen. Sie
#   sind eigene, sichtbare Zustaende. Ein vermisster Fall wird BEWUSST NICHT in
#   der Fallakte veraendert (kein stiller Eingriff in Ermittlungsdaten, mc) —
#   er wird gemeldet, und die Sicht zeigt ihn deutlich.
#
# Version: v0.7.383 · Build: 383 · 2026-07-10
# =============================================================================

import re
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

_FORENSIC_RE = re.compile(r"^forensic_(\d+)\.db$")

STATUS_OK = "ok"
STATUS_NEU = "neu"
STATUS_VERMISST = "vermisst"
STATUS_UNLESBAR = "unlesbar"


@dataclass(frozen=True)
class DetectedCase:
    user_id: int
    status: str                      # ok | neu | vermisst | unlesbar
    username: Optional[str]          # aus uid_profile (oder cases, wenn vermisst)
    in_cases: bool
    has_forensic_db: bool
    has_evidence_db: bool            # Arbeitsstand (kein Existenzkriterium)
    has_assets_db: bool
    detail: Optional[str] = None     # Grund bei 'unlesbar'


class CaseDetector:
    """Gleicht Platte und Fallakte ab (read-only)."""

    def __init__(self, con: sqlite3.Connection, forensic_dir: str,
                 evidence_dir: str, assets_dir: str) -> None:
        self._con = con                       # coordinator.db (lesend genuegt)
        self._forensic = Path(forensic_dir)
        self._evidence = Path(evidence_dir)
        self._assets = Path(assets_dir)

    # ---------------------------------------------------------------- public
    def detect(self) -> Dict[str, Any]:
        on_disk = self._forensic_dbs()                 # {uid: pfad}
        known = self._known_cases()                    # {uid: username}

        cases: List[DetectedCase] = []

        # 1) Alles, was auf der Platte liegt.
        for uid in sorted(on_disk):
            username, err = self._read_username(on_disk[uid])
            if err is not None:
                cases.append(DetectedCase(
                    user_id=uid, status=STATUS_UNLESBAR,
                    username=known.get(uid), in_cases=uid in known,
                    has_forensic_db=True,
                    has_evidence_db=self._has(self._evidence, "evidence", uid),
                    has_assets_db=self._has(self._assets, "assets", uid),
                    detail=err))
                continue

            cases.append(DetectedCase(
                user_id=uid,
                status=STATUS_OK if uid in known else STATUS_NEU,
                username=username or known.get(uid),
                in_cases=uid in known,
                has_forensic_db=True,
                has_evidence_db=self._has(self._evidence, "evidence", uid),
                has_assets_db=self._has(self._assets, "assets", uid)))

        # 2) Faelle, die die Fallakte kennt, die aber NICHT (mehr) auf der
        #    Platte liegen. Diese duerfen NICHT untergehen (Grundregel 1).
        for uid in sorted(set(known) - set(on_disk)):
            cases.append(DetectedCase(
                user_id=uid, status=STATUS_VERMISST,
                username=known[uid], in_cases=True, has_forensic_db=False,
                has_evidence_db=self._has(self._evidence, "evidence", uid),
                has_assets_db=self._has(self._assets, "assets", uid),
                detail="forensic_%d.db fehlt im Verzeichnis %s"
                       % (uid, self._forensic)))

        cases.sort(key=lambda c: c.user_id)
        counts = {s: 0 for s in
                  (STATUS_OK, STATUS_NEU, STATUS_VERMISST, STATUS_UNLESBAR)}
        for c in cases:
            counts[c.status] = counts.get(c.status, 0) + 1

        return {
            "forensic_dir": str(self._forensic),
            "evidence_dir": str(self._evidence),
            "assets_dir": str(self._assets),
            "count": len(cases),
            "counts": counts,
            "cases": [asdict(c) for c in cases],
        }

    def importable(self) -> List[DetectedCase]:
        """Nur die aufnehmbaren (Status 'neu') — mit gueltigem Benutzernamen."""
        out = []
        for d in self.detect()["cases"]:
            if d["status"] == STATUS_NEU and d["username"]:
                out.append(DetectedCase(**d))
        return out

    # ------------------------------------------------------------- internals
    def _forensic_dbs(self) -> Dict[int, Path]:
        if not self._forensic.is_dir():
            return {}
        out: Dict[int, Path] = {}
        for entry in self._forensic.iterdir():
            m = _FORENSIC_RE.match(entry.name)
            if m:
                out[int(m.group(1))] = entry
        return out

    @staticmethod
    def _has(directory: Path, prefix: str, uid: int) -> bool:
        return (directory / ("%s_%d.db" % (prefix, uid))).exists()

    def _known_cases(self) -> Dict[int, str]:
        try:
            return {int(r[0]): str(r[1]) for r in self._con.execute(
                "SELECT user_id, username FROM cases")}
        except sqlite3.Error:
            return {}

    @staticmethod
    def _read_username(path: Path):
        """
        Benutzername aus forensic_<uid>.db -> uid_profile (autoritativ).
        -> (username, None) | (None, fehlertext)
        """
        try:
            con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        except sqlite3.Error as exc:
            return None, "nicht oeffenbar: %s" % exc
        try:
            row = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') "
                "AND name='uid_profile'").fetchone()
            if row is None:
                return None, "Tabelle 'uid_profile' fehlt"
            r = con.execute(
                "SELECT username FROM uid_profile LIMIT 1").fetchone()
            if r is None or not r[0]:
                return None, "uid_profile enthaelt keinen Benutzernamen"
            return str(r[0]), None
        except sqlite3.Error as exc:
            return None, "nicht lesbar: %s" % exc
        finally:
            try:
                con.close()
            except Exception:
                pass
