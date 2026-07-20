# =============================================================================
# tests/test_management_storage_overview.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Systemzustand (AP-2G)
# =============================================================================
# Testsuite fuer Build 454: Speicher-/data/-Uebersicht (storage_overview).
#
# SO01 — scan_category: Zaehlung + Byte-Summe + uid-Mapping (<cat>_<uid>.db)
# SO02 — scan_category: fehlendes Verzeichnis -> (False,0,0,{}) (kein Absturz)
# SO03 — scan: Kategorien + Gesamtsumme (inkl. Einzeldateien)
# SO04 — scan: per_case Groessen je Fall (Vereinigung der uids)
# SO05 — Fremdforum-Kandidaten: forensic vorhanden, evidence fehlt
# SO06 — Fall MIT evidence ist KEIN Fremdforum-Kandidat
# SO07 — Plattenplatz gemessen; low_disk_alert bei hoher Schwelle
# SO08 — storage_to_dict json-serialisierbar, Schluessel vorhanden
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.ops.storage_overview import (        # noqa: E402
    StorageOverview, scan_category, storage_to_dict,
)


def _mkdb(path, size):
    with open(path, "wb") as fh:
        fh.write(b"\0" * size)


def _dirs(tmp):
    f = tmp / "forensic"; e = tmp / "evidence"; a = tmp / "assets"
    for d in (f, e, a):
        d.mkdir()
    return f, e, a


def test_so01_scan_category(tmp_path):
    f = tmp_path / "forensic"; f.mkdir()
    _mkdb(str(f / "forensic_10.db"), 100)
    _mkdb(str(f / "forensic_11.db"), 200)
    _mkdb(str(f / "readme.txt"), 5)          # ohne uid-Muster
    exists, fc, total, by_uid = scan_category(str(f))
    assert exists and fc == 3 and total == 305
    assert by_uid == {10: 100, 11: 200}


def test_so02_missing_dir():
    assert scan_category("/nonexistent/xyz") == (False, 0, 0, {})


def test_so03_categories_and_total(tmp_path):
    f, e, a = _dirs(tmp_path)
    _mkdb(str(f / "forensic_10.db"), 100)
    _mkdb(str(e / "evidence_10.db"), 50)
    extra = str(tmp_path / "coordinator.db")
    _mkdb(extra, 10)
    rep = StorageOverview(forensic_dir=str(f), evidence_dir=str(e),
                          assets_dir=str(a), extra_files=[extra]).scan(now=1)
    names = {c.name: c for c in rep.categories}
    assert names["forensic"].total_bytes == 100
    assert names["evidence"].total_bytes == 50
    assert names["einzeldateien"].total_bytes == 10
    assert rep.total_bytes == 160


def test_so04_per_case(tmp_path):
    f, e, a = _dirs(tmp_path)
    _mkdb(str(f / "forensic_10.db"), 100)
    _mkdb(str(e / "evidence_10.db"), 50)
    _mkdb(str(a / "assets_10.db"), 25)
    _mkdb(str(f / "forensic_11.db"), 70)
    rep = StorageOverview(forensic_dir=str(f), evidence_dir=str(e),
                          assets_dir=str(a)).scan(now=1)
    by = {c.subject_id: c for c in rep.per_case}
    assert by[10].total_bytes == 175
    assert by[11].forensic_bytes == 70 and by[11].evidence_bytes is None


def test_so05_fremdforum_candidate(tmp_path):
    f, e, a = _dirs(tmp_path)
    _mkdb(str(f / "forensic_11.db"), 70)     # kein evidence_11
    rep = StorageOverview(forensic_dir=str(f), evidence_dir=str(e),
                          assets_dir=str(a)).scan(now=1)
    assert rep.fremdforum_candidates == [11]


def test_so06_with_evidence_not_candidate(tmp_path):
    f, e, a = _dirs(tmp_path)
    _mkdb(str(f / "forensic_10.db"), 70)
    _mkdb(str(e / "evidence_10.db"), 5)
    rep = StorageOverview(forensic_dir=str(f), evidence_dir=str(e),
                          assets_dir=str(a)).scan(now=1)
    assert rep.fremdforum_candidates == []


def test_so07_disk_and_alert(tmp_path):
    f, e, a = _dirs(tmp_path)
    # Schwelle 100% -> freier Anteil ist praktisch immer < 100% -> Alarm.
    rep = StorageOverview(forensic_dir=str(f), evidence_dir=str(e),
                          assets_dir=str(a), disk_path=str(tmp_path),
                          low_disk_pct=100.0).scan(now=1)
    assert rep.disk_total is not None and rep.disk_free is not None
    assert rep.low_disk_alert is True
    # Schwelle 0% -> kein Alarm
    rep2 = StorageOverview(forensic_dir=str(f), evidence_dir=str(e),
                           assets_dir=str(a), disk_path=str(tmp_path),
                           low_disk_pct=0.0).scan(now=1)
    assert rep2.low_disk_alert is False


def test_so08_to_dict(tmp_path):
    f, e, a = _dirs(tmp_path)
    _mkdb(str(f / "forensic_10.db"), 10)
    rep = StorageOverview(forensic_dir=str(f), evidence_dir=str(e),
                          assets_dir=str(a)).scan(now=1)
    d = storage_to_dict(rep)
    s = json.dumps(d, ensure_ascii=False)
    assert '"categories"' in s and '"per_case"' in s
    assert d["fremdforum_candidates"] == [10]
