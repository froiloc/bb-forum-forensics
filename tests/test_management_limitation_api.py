# =============================================================================
# tests/test_management_limitation_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7
# =============================================================================
# Testsuite fuer Build 524 (AP-3A / Idee 32): Fristbeginn je Fall aus den
# forensic_<uid>.db, Read-Model und Endpunkt GET /api/limitation.
#
# LESESCHICHT (read_tatzeit — eine forensic_<uid>.db, rein lesend):
#   LM01 — beide Zeitquellen vorhanden: frueheste/spaeteste ueber BEIDE Tabellen
#          gebildet, 'quellen' nennt beide.
#   LM02 — nur uid_posts vorhanden -> belegt, nur diese Quelle genannt.
#   LM03 — Datei fehlt -> befund 'ohne_forensic_db' (Fall bleibt in der Liste).
#   LM04 — Datei da, aber keine der Zeittabellen -> 'ohne_zeittabelle'.
#   LM05 — Tabellen da, aber alle Zeitstempel NULL -> 'ohne_tatzeit'
#          (unterscheidet sich ausdruecklich von 'ohne_zeittabelle').
#   LM06 — Datei unlesbar (kein SQLite) -> 'nicht_lesbar' MIT Grund.
#   LM07 — ZEITQUELLEN nennt genau die zwei belegten Spalten und NICHT
#          pages.fetched_at (Sicherungszeitpunkt, nie Tatzeit).
#
# READ-MODEL (LimitationRepo):
#   LM08 — jeder Fall aus 'cases' erzeugt GENAU EINE Zeile, auch ohne Datei;
#          'datenlage' zaehlt die Befunde, 'zaehler' die Ampelzustaende.
#   LM09 — Sortierung: 'ueberschritten' vor 'knapp' vor 'ohne_tatzeit' vor
#          'offen' (Ungeprueftes rutscht NICHT unter Unverdaechtiges).
#   LM10 — leere Auswahl (subject_ids=[]) bedeutet KEINE Faelle, nicht 'alle'.
#   LM11 — die Hinweise (share_id-Luecke, fetched_at) fahren in JEDER Antwort
#          mit.
#
# ENDPUNKT:
#   LM12 — ohne Recht -> 403 und nennt 'limitation.view'.
#   LM13 — mit Recht (unbestaetigter Satz) -> 200, aussage_moeglich false,
#          verweigerungsgrund gesetzt, ABER Fallliste und Datenlage vollstaendig.
#   LM14 — die Antwort traegt 'stellt_keine_verjaehrung_fest': true.
#   LM15 — vorwarn_tage unbrauchbar (nicht-Zahl, negativ) -> je 400.
#   LM16 — Scope 'eigene' genuegt: die Sicht ist NICHT scope-behaftet (sie
#          zeigt bewusst auch unzugewiesene Faelle).
#   LM17 — Der Endpunkt schreibt NICHTS: audit_log-Spitze unveraendert.
#   LM18 — M031 hat 'limitation.view' geseedet (Migrationskette angewandt).
# =============================================================================

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, time as dtime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.cases.cases_repo import CasesRepo                   # noqa: E402
from management.deadlines.limitation_params import load_params      # noqa: E402
from management.deadlines.limitation_repo import (                  # noqa: E402
    HINWEIS_FETCHED_AT,
    HINWEIS_SHARES,
    ZEITQUELLEN,
    LimitationRepo,
    read_tatzeit,
)
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover   # noqa: E402
from management.rbac.rbac_repo import RbacRepo                       # noqa: E402
from management.server.management_app import ManagementApp           # noqa: E402

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0,
    is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


def _ts(tag: str) -> int:
    return int(datetime.combine(date.fromisoformat(tag), dtime(0, 0),
                                tzinfo=timezone.utc).timestamp())


def _forensic_db(pfad: Path, *, posts=None, pms=None,
                 mit_posts_tabelle=True, mit_pms_tabelle=False) -> None:
    """
    Baut eine minimale forensic_<uid>.db.

    Die Tabellen tragen genau die Spalten, die der Code liest — Beleg fuer die
    DDL: tests/test_build430_content_ts.py:51 (uid_posts) und
    tests/test_build432_pm_content_ts.py:50 (uid_pms_posts).
    """
    con = sqlite3.connect(str(pfad))
    try:
        if mit_posts_tabelle:
            con.execute("CREATE TABLE uid_posts (id INTEGER, posted INTEGER)")
            for i, p in enumerate(posts or []):
                con.execute("INSERT INTO uid_posts VALUES (?,?)", (i + 1, p))
        if mit_pms_tabelle:
            con.execute("CREATE TABLE uid_pms_posts "
                        "(pm_post_id INTEGER, posted_ts INTEGER)")
            for i, p in enumerate(pms or []):
                con.execute("INSERT INTO uid_pms_posts VALUES (?,?)",
                            (500 + i, p))
        con.commit()
    finally:
        con.close()


class TestReadTatzeit(unittest.TestCase):
    """LM01-LM07 — die Leseschicht, eine Datei je Fall."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_LM01_beide_quellen(self):
        p = self.dir / "forensic_11.db"
        _forensic_db(p, posts=[_ts("2022-03-14"), _ts("2023-01-05")],
                     pms=[_ts("2021-08-01"), _ts("2024-02-02")],
                     mit_pms_tabelle=True)
        t = read_tatzeit(p, 11, "nutzer11")
        self.assertEqual(t.befund, "belegt")
        self.assertEqual(t.frueheste_ts, _ts("2021-08-01"))
        self.assertEqual(t.spaeteste_ts, _ts("2024-02-02"))
        self.assertEqual(set(t.quellen),
                         {"uid_posts.posted", "uid_pms_posts.posted_ts"})

    def test_LM02_nur_posts(self):
        p = self.dir / "forensic_12.db"
        _forensic_db(p, posts=[_ts("2022-03-14")])
        t = read_tatzeit(p, 12, "nutzer12")
        self.assertEqual(t.befund, "belegt")
        self.assertEqual(t.spaeteste_ts, _ts("2022-03-14"))
        self.assertEqual(t.quellen, ("uid_posts.posted",))

    def test_LM03_datei_fehlt(self):
        t = read_tatzeit(self.dir / "forensic_13.db", 13, "nutzer13")
        self.assertEqual(t.befund, "ohne_forensic_db")
        self.assertIsNone(t.spaeteste_ts)
        self.assertIn("forensic_13.db", t.detail)

    def test_LM04_ohne_zeittabelle(self):
        p = self.dir / "forensic_14.db"
        _forensic_db(p, mit_posts_tabelle=False)
        # Eine Datei ohne jede Tabelle: SQLite legt sie beim CREATE erst an, wir
        # erzeugen also bewusst eine leere Datenbank mit einer FREMDEN Tabelle.
        con = sqlite3.connect(str(p))
        con.execute("CREATE TABLE pages (page_id INTEGER, fetched_at INTEGER)")
        con.commit()
        con.close()
        t = read_tatzeit(p, 14, "nutzer14")
        self.assertEqual(t.befund, "ohne_zeittabelle")
        self.assertIn("uid_posts", t.detail)

    def test_LM05_ohne_tatzeit_ist_nicht_ohne_tabelle(self):
        p = self.dir / "forensic_15.db"
        _forensic_db(p, posts=[None, None])
        t = read_tatzeit(p, 15, "nutzer15")
        self.assertEqual(t.befund, "ohne_tatzeit")
        self.assertIn("kein einziger", t.detail)
        # Der Unterschied zu 'ohne_zeittabelle' ist der ganze Punkt: hier war
        # die Tabelle da und leer, dort fehlte sie.
        self.assertNotEqual(t.befund, "ohne_zeittabelle")

    def test_LM06_nicht_lesbar_mit_grund(self):
        p = self.dir / "forensic_16.db"
        p.write_bytes(b"das ist keine SQLite-Datei")
        t = read_tatzeit(p, 16, "nutzer16")
        self.assertEqual(t.befund, "nicht_lesbar")
        self.assertTrue(t.detail.strip())
        self.assertIsNone(t.spaeteste_ts)

    def test_LM07_zeitquellen_sind_belegt_und_abgeschlossen(self):
        spalten = {"%s.%s" % (t, s) for t, s, _b in ZEITQUELLEN}
        self.assertEqual(spalten,
                         {"uid_posts.posted", "uid_pms_posts.posted_ts"})
        # pages.fetched_at ist der SICHERUNGSZEITPUNKT und darf nie als Tatzeit
        # dienen — eine Verwechslung wuerde jede Frist um Jahre verschieben.
        self.assertNotIn("pages.fetched_at", spalten)
        for _t, _s, beleg in ZEITQUELLEN:
            self.assertTrue(beleg.strip())


class TestLimitationRepoAndApi(unittest.TestCase):
    """LM08-LM18 — Read-Model und Endpunkt."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.forensic = Path(self._tmp) / "forensic"
        self.forensic.mkdir()

        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=delete")
        self.con.executescript(_PERSON)
        self.con.executescript(_OLD_SCRAPE_JOBS)
        for uname, dname, inv, sup in (
                ("NRW\\chefin", "Chef-Ermittlerin", 0, 1),
                ("NRW\\ermittler", "Ermittler", 1, 0),
                ("NRW\\ohne", "Ohne Rechte", 0, 0)):
            self.con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,0)", (uname, dname, inv, sup))

        self.audit = AuditLog(self.con)
        self.applied = MigrationRunner(
            self.con, discover(coordinator_migrations), audit=self.audit,
            deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        rbac = RbacRepo(self.con, self.writer)
        rbac.grant("supervisor", "limitation.view", scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Person 2 bekommt dasselbe Recht mit Scope 'eigene' — die Sicht ist
        # NICHT scope-behaftet, also muss sie trotzdem antworten (LM16).
        rbac.grant("investigator", "limitation.view", scope="eigene",
                   actor_id=1)
        rbac.assign_role(2, "investigator", actor_id=1)
        # Person 3: nichts.

        cases = CasesRepo(self.con, self.writer)
        for uid, name in ((101, "alt_und_knapp"), (102, "frisch"),
                          (103, "ohne_datei"), (104, "leere_tabelle")):
            cases.create_case(uid, name, actor_id=1)

        # 101: Tat 2021-08-01 -> mit 5-Jahres-Frist am Stichtag ueberschritten.
        _forensic_db(self.forensic / "forensic_101.db",
                     posts=[_ts("2020-01-01"), _ts("2021-08-01")])
        # 102: Tat 2024-08-01 -> reichlich Zeit.
        _forensic_db(self.forensic / "forensic_102.db",
                     posts=[_ts("2024-08-01")])
        # 103: KEINE Datei.
        # 104: Tabelle da, aber leer.
        _forensic_db(self.forensic / "forensic_104.db", posts=[None])

        self.params = load_params()          # der ausgelieferte, UNBESTAETIGTE
        self.app = ManagementApp(self.db_path, forensic_dir=str(self.forensic))

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # -- Read-Model ---------------------------------------------------------

    def _repo(self):
        con = sqlite3.connect("file:%s?mode=ro" % self.db_path, uri=True)
        con.row_factory = sqlite3.Row
        return con, LimitationRepo(con, self.forensic)

    def test_LM08_jeder_fall_genau_eine_zeile(self):
        con, repo = self._repo()
        try:
            r = repo.compute(params=self.params, now_ts=_ts("2026-07-25"))
        finally:
            con.close()
        self.assertEqual(r.faelle_gesamt, 4)
        self.assertEqual(len(r.rows), 4)
        self.assertEqual(sum(r.datenlage.values()), 4)
        self.assertEqual(sum(r.zaehler.values()), 4)
        self.assertEqual(r.datenlage.get("ohne_forensic_db"), 1)
        self.assertEqual(r.datenlage.get("ohne_tatzeit"), 1)
        self.assertEqual(r.datenlage.get("belegt"), 2)
        # Kein Fall verschwindet: alle subject_ids sind vertreten.
        self.assertEqual({row.tatzeit.subject_id for row in r.rows},
                         {101, 102, 103, 104})

    def test_LM09_sortierung_dringlichstes_zuerst(self):
        """Mit BESTAETIGTEM Satz: ueberschritten vor knapp vor ungeprueft."""
        raw = json.loads(
            (Path("management/deadlines/limitation_params.json")
             ).read_text(encoding="utf-8"))
        raw["bestaetigt"] = True
        raw["bestaetigt_von"] = "StA Testfixture"
        raw["bestaetigt_am"] = "2026-07-25"
        p = Path(self._tmp) / "params_ok.json"
        p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        params_ok = load_params(p)

        con, repo = self._repo()
        try:
            r = repo.compute(params=params_ok, now_ts=_ts("2026-08-08"))
        finally:
            con.close()
        ampeln = [row.assessment.ampel for row in r.rows]
        rang = {"ueberschritten": 0, "knapp": 1, "ohne_tatzeit": 2,
                "ohne_fassung": 3, "ruht": 4, "offen": 5, "keine_aussage": 6}
        self.assertEqual(ampeln, sorted(ampeln, key=lambda a: rang[a]),
                         "Reihenfolge: %s" % ampeln)
        # 101 (Tat 2021-08-01, 5-Jahres-Frist) muss ueberschritten sein.
        erste = r.rows[0]
        self.assertEqual(erste.tatzeit.subject_id, 101)
        self.assertEqual(erste.assessment.ampel, "ueberschritten")
        self.assertNotIn("verjaehrt", erste.assessment.befund)
        # Die UNGEPRUEFTEN stehen VOR den unverdaechtigen 'offen'-Faellen.
        self.assertLess(ampeln.index("ohne_tatzeit"), ampeln.index("offen"))

    def test_LM10_leere_auswahl_ist_keine_auswahl_aller(self):
        con, repo = self._repo()
        try:
            r = repo.compute(params=self.params, now_ts=_ts("2026-07-25"),
                             subject_ids=[])
            r2 = repo.compute(params=self.params, now_ts=_ts("2026-07-25"),
                              subject_ids=[101])
        finally:
            con.close()
        self.assertEqual(r.faelle_gesamt, 0)
        self.assertEqual(r2.faelle_gesamt, 1)

    def test_LM11_hinweise_immer_dabei(self):
        con, repo = self._repo()
        try:
            r = repo.compute(params=self.params, now_ts=_ts("2026-07-25"))
        finally:
            con.close()
        self.assertIn(HINWEIS_SHARES, r.hinweise)
        self.assertIn(HINWEIS_FETCHED_AT, r.hinweise)
        self.assertTrue(any("share_id" in h for h in r.hinweise))
        # Und die Vorbehalte des Parametersatzes ebenso.
        self.assertGreaterEqual(len(r.vorbehalte), 4)

    # -- Endpunkt -----------------------------------------------------------

    def _get(self, person_id, query=None):
        return self.app.dispatch(person_id, "/api/limitation", query or {})

    def test_LM12_ohne_recht_403(self):
        r = self._get(3)
        self.assertEqual(r.status, 403)
        self.assertIn("limitation.view", r.body.decode("utf-8"))

    def test_LM13_unbestaetigt_aber_vollstaendig(self):
        r = self._get(1)
        self.assertEqual(r.status, 200)
        b = json.loads(r.body.decode("utf-8"))
        self.assertFalse(b["aussage_moeglich"])
        self.assertIn("NICHT JURISTISCH BESTAETIGT", b["verweigerungsgrund"])
        self.assertFalse(b["params_bestaetigt"])
        # ABER: die nuetzlichen Teile sind vollstaendig da.
        self.assertEqual(b["faelle_gesamt"], 4)
        self.assertEqual(len(b["rows"]), 4)
        self.assertEqual(sum(b["datenlage"].values()), 4)
        self.assertEqual(b["zaehler"].get("keine_aussage"), 4)
        # Jede Zeile nennt ihre Datenlage — auch wenn die Rechtsfolge fehlt.
        befunde = {row["tatzeit_befund"] for row in b["rows"]}
        self.assertEqual(befunde, {"belegt", "ohne_forensic_db",
                                   "ohne_tatzeit"})

    def test_LM14_zusicherung_faehrt_mit(self):
        b = json.loads(self._get(1).body.decode("utf-8"))
        self.assertTrue(b["stellt_keine_verjaehrung_fest"])

    def test_LM15_vorwarn_tage_unbrauchbar_400(self):
        for bad in ("abc", "-1"):
            r = self._get(1, {"vorwarn_tage": [bad]})
            self.assertEqual(r.status, 400, "Wert %r muss 400 ergeben" % bad)
        r_ok = self._get(1, {"vorwarn_tage": ["540"]})
        self.assertEqual(r_ok.status, 200)
        self.assertEqual(
            json.loads(r_ok.body.decode("utf-8"))["vorwarn_tage"], 540)

    def test_LM16_scope_eigene_genuegt(self):
        """
        Die Sicht ist NICHT scope-behaftet. Person 2 hat das Recht nur mit
        Scope 'eigene' und bekommt trotzdem die VOLLE Liste — genau so ist es
        gewollt: die gefaehrlichsten Faelle sind die unzugewiesenen.
        """
        r = self._get(2)
        self.assertEqual(r.status, 200)
        b = json.loads(r.body.decode("utf-8"))
        self.assertEqual(b["faelle_gesamt"], 4)

    def test_LM17_endpunkt_schreibt_nichts(self):
        tip = self.app.audit_tip_seq()
        self.assertEqual(self._get(1).status, 200)
        self.assertEqual(self._get(1, {"vorwarn_tage": ["30"]}).status, 200)
        self.assertEqual(self.app.audit_tip_seq(), tip)

    def test_LM18_m031_hat_geseedet(self):
        self.assertIn(31, self.applied)
        row = self.con.execute(
            "SELECT code FROM rbac_capability WHERE code='limitation.view'"
        ).fetchone()
        self.assertIsNotNone(row)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
