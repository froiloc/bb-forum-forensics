# =============================================================================
# management/ops/storage_overview.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Systemzustand (AP-2G)
# =============================================================================
# Zweck (Idee 25 read-only-Teil + Ideen §2.7 "Speicher-/Wachstumsuebersicht"):
#   Rein lesende Uebersicht ueber die Datenverzeichnisse (data/): Datei- und
#   Byte-Zaehlung je Kategorie (forensic/evidence/assets + Einzeldateien),
#   Groessen JE FALL sowie der freie Plattenplatz. Zwei Signale:
#     * FREMDFORUM-KANDIDATEN: Faelle mit forensic_<uid>.db, aber OHNE
#       evidence_<uid>.db (Fall existiert, Arbeitsstand fehlt — Beleg
#       case_detector.py: forensic = Existenzkriterium, evidence = Arbeitsstand).
#     * LOW-DISK-ALARM: freier Plattenplatz unter Schwelle -> Vorabwarnung fuer
#       das Backup (vorfallgetrieben: default.db-Malformed durch volle Platte,
#       Bauplan v1.1 §11.8 / §7.5.3).
#
#   NUR LESEND (Dateigroessen + shutil.disk_usage). now injizierbar ->
#   deterministisch bis auf die Plattenzahlen; die Scan-Logik ist rein und mit
#   temporaeren Verzeichnissen vollstaendig testbar (GR1: kein stiller Ausfall —
#   fehlende Verzeichnisse werden mit 0 gezaehlt und vermerkt).
#
# Version: v0.7.454 · Build: 454 · 2026-07-19
# =============================================================================

from __future__ import annotations

import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_UID_RE = {
    "forensic": re.compile(r"^forensic_(\d+)\.db$"),
    "evidence": re.compile(r"^evidence_(\d+)\.db$"),
    "assets": re.compile(r"^assets_(\d+)\.db$"),
}


@dataclass(frozen=True)
class CategoryStorage:
    name: str
    path: str
    exists: bool
    file_count: int
    total_bytes: int


@dataclass(frozen=True)
class CaseStorage:
    user_id: int
    forensic_bytes: Optional[int]   # None = Datei fehlt
    evidence_bytes: Optional[int]
    assets_bytes: Optional[int]
    total_bytes: int


@dataclass(frozen=True)
class StorageReport:
    generated_at: int
    categories: List[CategoryStorage]
    per_case: List[CaseStorage]
    fremdforum_candidates: List[int]    # forensic vorhanden, evidence fehlt
    total_bytes: int
    disk_total: Optional[int]
    disk_used: Optional[int]
    disk_free: Optional[int]
    disk_free_pct: Optional[float]
    low_disk_alert: bool


def scan_category(path: str) -> Tuple[bool, int, int, Dict[int, int]]:
    """
    (exists, file_count, total_bytes, {uid: bytes}) fuer ein Kategorie-
    Verzeichnis. uid nur, wenn der Dateiname dem <cat>_<uid>.db-Muster
    entspricht. Fehlt das Verzeichnis -> (False, 0, 0, {}). REINE, testbare
    Funktion (Dateisystem, kein Zustand).
    """
    p = Path(path)
    if not p.is_dir():
        return (False, 0, 0, {})
    cat = None
    name = p.name.rstrip("/")
    # Kategorie aus dem Verzeichnisnamen ableiten (forensic/evidence/assets),
    # sonst kein uid-Mapping (nur Zaehlung).
    for key in _UID_RE:
        if key in name:
            cat = key
            break
    file_count = 0
    total = 0
    by_uid: Dict[int, int] = {}
    with os.scandir(p) as it:
        for entry in it:
            if not entry.is_file():
                continue
            size = entry.stat().st_size
            file_count += 1
            total += size
            if cat is not None:
                m = _UID_RE[cat].match(entry.name)
                if m:
                    by_uid[int(m.group(1))] = size
    return (True, file_count, total, by_uid)


class StorageOverview:
    """Read-only Speicher-/data/-Uebersicht (Systemzustand)."""

    def __init__(self, *, forensic_dir: str, evidence_dir: str, assets_dir: str,
                 extra_files: Optional[List[str]] = None,
                 disk_path: Optional[str] = None,
                 low_disk_pct: float = 10.0) -> None:
        self._forensic_dir = forensic_dir
        self._evidence_dir = evidence_dir
        self._assets_dir = assets_dir
        # Einzeldateien (coordinator.db/default.db/templates.db/...): als eigene
        # Kategorie 'einzeldateien' gezaehlt.
        self._extra_files = list(extra_files or [])
        # Pfad fuer die Plattenplatz-Messung (Default: evidence-Dir bzw. dessen
        # Elternverzeichnis); muss existieren.
        self._disk_path = disk_path or evidence_dir
        self._low_disk_pct = float(low_disk_pct)

    def scan(self, *, now: Optional[int] = None) -> StorageReport:
        now = int(time.time()) if now is None else int(now)

        categories: List[CategoryStorage] = []
        by_uid_all: Dict[str, Dict[int, int]] = {}
        for name, path in (("forensic", self._forensic_dir),
                           ("evidence", self._evidence_dir),
                           ("assets", self._assets_dir)):
            exists, fc, total, by_uid = scan_category(path)
            categories.append(CategoryStorage(name, path, exists, fc, total))
            by_uid_all[name] = by_uid

        # Einzeldateien
        extra_count = 0
        extra_total = 0
        for f in self._extra_files:
            fp = Path(f)
            if fp.is_file():
                extra_count += 1
                extra_total += fp.stat().st_size
        categories.append(CategoryStorage(
            "einzeldateien", ";".join(self._extra_files), extra_count > 0,
            extra_count, extra_total))

        # Je-Fall-Aufstellung (Vereinigung aller uids).
        uids = set()
        for m in by_uid_all.values():
            uids.update(m.keys())
        per_case: List[CaseStorage] = []
        fremdforum: List[int] = []
        for uid in sorted(uids):
            fb = by_uid_all["forensic"].get(uid)
            eb = by_uid_all["evidence"].get(uid)
            ab = by_uid_all["assets"].get(uid)
            total = sum(x for x in (fb, eb, ab) if x is not None)
            per_case.append(CaseStorage(uid, fb, eb, ab, total))
            if fb is not None and eb is None:
                fremdforum.append(uid)   # forensic da, evidence fehlt

        total_bytes = sum(c.total_bytes for c in categories)

        # Plattenplatz (best effort; nie werfen).
        disk_total = disk_used = disk_free = None
        disk_free_pct = None
        low_alert = False
        try:
            du = shutil.disk_usage(self._disk_path)
            disk_total, disk_used, disk_free = du.total, du.used, du.free
            if du.total > 0:
                disk_free_pct = round(100.0 * du.free / du.total, 2)
                low_alert = disk_free_pct < self._low_disk_pct
        except Exception:
            pass

        return StorageReport(
            generated_at=now, categories=categories, per_case=per_case,
            fremdforum_candidates=fremdforum, total_bytes=total_bytes,
            disk_total=disk_total, disk_used=disk_used, disk_free=disk_free,
            disk_free_pct=disk_free_pct, low_disk_alert=low_alert)


def storage_to_dict(report: StorageReport) -> dict:
    return {
        "generated_at": report.generated_at,
        "total_bytes": report.total_bytes,
        "disk_total": report.disk_total,
        "disk_used": report.disk_used,
        "disk_free": report.disk_free,
        "disk_free_pct": report.disk_free_pct,
        "low_disk_alert": report.low_disk_alert,
        "fremdforum_candidates": report.fremdforum_candidates,
        "categories": [
            {"name": c.name, "path": c.path, "exists": c.exists,
             "file_count": c.file_count, "total_bytes": c.total_bytes}
            for c in report.categories
        ],
        "per_case": [
            {"user_id": c.user_id, "forensic_bytes": c.forensic_bytes,
             "evidence_bytes": c.evidence_bytes, "assets_bytes": c.assets_bytes,
             "total_bytes": c.total_bytes}
            for c in report.per_case
        ],
    }
