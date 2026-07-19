# =============================================================================
# tests/test_management_annotation_stats.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2D)
# =============================================================================
# Testsuite fuer Build 449: Annotations-Tortenstatistik (AnnotationStatsRepo).
#
# AN01 — aggregate_annotations: Kategorie-Zaehlung; None/'' -> '(ohne Kategorie)'
# AN02 — aggregate_annotations: Tags aus tags_json (JSON-Array) gezaehlt
# AN03 — aggregate_annotations: ungueltiges tags_json -> '(ungueltige Tags)', zaehlt weiter
# AN04 — compute scope 'alle': aggregiert ueber mehrere evidence_<uid>.db
# AN05 — compute: Fall ohne evidence_<uid>.db -> cases_without_evidence (GR1)
# AN06 — compute: soft-geloeschte Annotation (deleted_at) zaehlt NICHT
# AN07 — compute scope 'eigene': nur zugewiesene Faelle (assigned_to)
# AN08 — Ergebnislisten absteigend nach count sortiert
#
# Version: v0.7.449 · Build: 449 · 2026-07-19
# =============================================================================

import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.stats.annotation_stats_repo import (   # noqa: E402
    AnnotationStatsRepo, aggregate_annotations,
)

_NOW = 1_700_000_000


def _coordinator():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE cases(user_id INTEGER PRIMARY KEY, username TEXT, "
                "status TEXT, assigned_to INTEGER)")
    return con


def _evidence(path, annos):
    """annos: Liste (category, tags_json, deleted_at)."""
    con = sqlite3.connect(path)
    con.execute('CREATE TABLE annotations(id INTEGER PRIMARY KEY AUTOINCREMENT, '
                'category TEXT, tags_json TEXT, deleted_at INTEGER)')
    for cat, tags, deleted in annos:
        con.execute("INSERT INTO annotations(category,tags_json,deleted_at) "
                    "VALUES(?,?,?)", (cat, tags, deleted))
    con.commit()
    con.close()


# -- reine Aggregation --------------------------------------------------------

def test_an01_category_counts():
    cat, tag, total = aggregate_annotations(
        [("email", None), ("email", None), (None, None), ("", None)])
    assert total == 4
    assert cat["email"] == 2
    assert cat["(ohne Kategorie)"] == 2


def test_an02_tag_counts():
    cat, tag, total = aggregate_annotations(
        [("x", '["a","b"]'), ("y", '["a"]')])
    assert tag["a"] == 2 and tag["b"] == 1


def test_an03_invalid_tags():
    cat, tag, total = aggregate_annotations(
        [("x", "kein-json"), ("y", '{"not":"list"}')])
    assert total == 2                       # Annotationen zaehlen weiter
    assert tag["(ungueltige Tags)"] == 2


# -- Integration mit evidence-Dateien -----------------------------------------

def test_an04_compute_over_multiple(tmp_path):
    con = _coordinator()
    con.execute("INSERT INTO cases VALUES(10,'a','open',1)")
    con.execute("INSERT INTO cases VALUES(11,'b','open',1)")
    con.commit()
    _evidence(str(tmp_path / "evidence_10.db"),
              [("email", '["realname"]', None), ("telefon", None, None)])
    _evidence(str(tmp_path / "evidence_11.db"),
              [("email", '["realname"]', None)])
    res = AnnotationStatsRepo(con, str(tmp_path)).compute(scope="alle", now=_NOW)
    assert res["annotations_total"] == 3
    bycat = {e["key"]: e["count"] for e in res["by_category"]}
    assert bycat["email"] == 2 and bycat["telefon"] == 1
    bytag = {e["key"]: e["count"] for e in res["by_tag"]}
    assert bytag["realname"] == 2
    assert res["cases_with_evidence"] == 2 and res["cases_without_evidence"] == 0


def test_an05_missing_evidence_counted(tmp_path):
    con = _coordinator()
    con.execute("INSERT INTO cases VALUES(10,'a','open',1)")   # evidence fehlt
    con.execute("INSERT INTO cases VALUES(11,'b','open',1)")
    con.commit()
    _evidence(str(tmp_path / "evidence_11.db"), [("email", None, None)])
    res = AnnotationStatsRepo(con, str(tmp_path)).compute(scope="alle", now=_NOW)
    assert res["cases_total"] == 2
    assert res["cases_with_evidence"] == 1
    assert res["cases_without_evidence"] == 1     # nicht still verschluckt


def test_an06_deleted_excluded(tmp_path):
    con = _coordinator()
    con.execute("INSERT INTO cases VALUES(10,'a','open',1)")
    con.commit()
    _evidence(str(tmp_path / "evidence_10.db"),
              [("email", None, None), ("email", None, 1699999999)])  # 2. geloescht
    res = AnnotationStatsRepo(con, str(tmp_path)).compute(scope="alle", now=_NOW)
    assert res["annotations_total"] == 1


def test_an07_scope_eigene(tmp_path):
    con = _coordinator()
    con.execute("INSERT INTO cases VALUES(10,'a','open',1)")   # person 1
    con.execute("INSERT INTO cases VALUES(11,'b','open',2)")   # person 2
    con.commit()
    _evidence(str(tmp_path / "evidence_10.db"), [("email", None, None)])
    _evidence(str(tmp_path / "evidence_11.db"), [("telefon", None, None)])
    res = AnnotationStatsRepo(con, str(tmp_path)).compute(
        scope="eigene", person_id=1, now=_NOW)
    assert res["cases_total"] == 1
    bycat = {e["key"]: e["count"] for e in res["by_category"]}
    assert bycat == {"email": 1}


def test_an08_sorted_desc(tmp_path):
    con = _coordinator()
    con.execute("INSERT INTO cases VALUES(10,'a','open',1)")
    con.commit()
    _evidence(str(tmp_path / "evidence_10.db"),
              [("b", None, None), ("a", None, None), ("a", None, None),
               ("a", None, None), ("b", None, None), ("c", None, None)])
    res = AnnotationStatsRepo(con, str(tmp_path)).compute(scope="alle", now=_NOW)
    counts = [e["count"] for e in res["by_category"]]
    assert counts == sorted(counts, reverse=True)
    assert res["by_category"][0]["key"] == "a"     # 3x, haeufigste zuerst
