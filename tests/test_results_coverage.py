# =============================================================================
# tests/test_results_coverage.py
# IT-Forensisches Ermittlungswerkzeug — Abdeckung der Ergebnisbewertung
# =============================================================================
# Testsuite fuer Build 393: CoverageRepo + /api/results/coverage + CLI.
#
# CV01 — DER KERNBEFUND: ein NIE bewerteter Fall erscheint in der Abdeckung
#        (nie_bewertet=true, abdeckung=0) — in stats() taucht er UEBERHAUPT
#        NICHT auf. Genau diese Luecke schliesst Build 393.
# CV02 — Abdeckung bezieht sich auf 'schwerste' (die Priorisierungsachse);
#        'beste' wird SEPARAT ausgewiesen.
# CV03 — Append-only: eine Korrektur erhoeht die Abdeckung NICHT (es zaehlt
#        der aktuelle Stand, nicht die Zahl der Erfassungen).
# CV04 — Sortierung: die blinden Flecken zuerst.
# CV05 — Der VERMERK reist mit dem Score mit.
# CV06 — summary(): die Zahl der nie bewerteten Faelle wird ausdruecklich
#        genannt.
# CV07 — /api/results/stats weist 'faelle_gesamt' und 'faelle_unbewertet' aus.
# CV08 — Endpunkt /api/results/coverage: 200; Scope 'eigene' sieht NUR die
#        zugewiesenen Faelle (und bekommt KEIN 403 — anders als /stats);
#        parse_qs-Vertrag (Build 391).
# CV09 — CLI 'coverage': Exit 2 bei blinden Flecken, umrahmte Warnung.
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.cases.cases_repo import CasesRepo
from management.results import results_admin
from management.results.coverage_repo import CoverageRepo
from management.results.priority_scorer import VERMERK
from management.results.results_repo import ResultsRepo
from management.server.management_app import ManagementApp

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
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


class ResultsCoverageTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")

        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, kennung, name, sup in ((1, "h0a2898", "Chefin", 1),
                                        (2, "h002", "Mueller", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, kennung, name, sup, now))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)
        self.repo = ResultsRepo(self.con, self.writer)

        # DREI Faelle. 18 wird bewertet, 19 teilweise, 20 GAR NICHT.
        self.cases.create_case(18, "boarder18", actor_id=1)
        self.cases.create_case(19, "boarder19", actor_id=1)
        self.cases.create_case(20, "boarder20", actor_id=1)
        self.cases.assign(18, 2, actor_id=1)          # Mueller
        self.cases.assign(19, 2, actor_id=1)          # Mueller

        self.rbac.grant("supervisor", "results.view", scope="alle", actor_id=1)
        self.rbac.grant("investigator", "results.view", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.unlink(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _app(self):
        return ManagementApp(db_path=self._db)

    def _by_case(self, cov):
        return {f["subject_id"]: f for f in cov["faelle"]}

    # ================================================================== CV01
    def test_cv01_KERNBEFUND_nie_bewerteter_fall_ist_sichtbar(self):
        """
        Der Mangel, den Build 393 behebt: stats() liest aus
        v_investigation_current und sieht damit NUR Faelle mit mindestens einer
        Bewertung. Fall 20 (nie bewertet) ist dort UNSICHTBAR — nicht als
        Luecke gezeigt, sondern schlicht nicht da. Genau er ist aber der blinde
        Fleck, nach dem gesucht wird.
        """
        self.repo.assess(subject_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         quality_code="fortlaufend", actor_id=2)

        # DAS ALTE VERHALTEN: stats() kennt Fall 20 nicht.
        st = self.repo.stats()
        self.assertEqual(st["faelle"], 1)            # nur 18!

        # DAS NEUE: coverage() geht von 'cases' aus.
        cov = CoverageRepo(self.con).coverage()
        self.assertEqual(cov["faelle_gesamt"], 3)    # 18, 19, 20
        self.assertEqual(cov["nie_bewertet"], 2)     # 19 und 20

        f = self._by_case(cov)
        self.assertFalse(f[18]["nie_bewertet"])
        self.assertTrue(f[20]["nie_bewertet"])
        self.assertEqual(f[20]["abdeckung"], 0.0)
        self.assertEqual(f[20]["n_bewertet"], 0)
        self.assertIsNone(f[20]["zuletzt_bewertet"])
        self.assertIsNone(f[20]["hoechste_konfidenz"])
        # ALLE Kriterien fehlen — und sie werden BENANNT.
        self.assertEqual(len(f[20]["unbewertet"]), cov["n_kriterien"])

        # Auch die Stammdaten des Falls stehen dabei (Zuweisung, Zustand).
        self.assertEqual(f[18]["username"], "boarder18")
        self.assertEqual(f[18]["assigned_to"], "h002")
        self.assertIsNone(f[20]["assigned_to"])      # nicht zugewiesen

    # ================================================================== CV02
    def test_cv02_abdeckung_auf_schwerste_beste_separat(self):
        self.repo.assess(subject_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         actor_id=2)
        self.repo.assess(subject_id=18, criterion_code="identification",
                         extrem="schwerste", confidence_code="gerichtsfest",
                         actor_id=2)
        # 'beste' zaehlt NICHT in die Abdeckung (mc: 'schwerste' ist die
        # Priorisierungsachse), wird aber SEPARAT ausgewiesen.
        self.repo.assess(subject_id=18, criterion_code="cp_possession",
                         extrem="beste", confidence_code="verdacht",
                         actor_id=2)

        f = self._by_case(CoverageRepo(self.con).coverage())[18]
        self.assertEqual(f["n_bewertet"], 2)         # NICHT 3
        self.assertEqual(f["abdeckung"], 0.2)        # 2 von 10
        self.assertEqual(f["n_beste"], 1)            # separat
        self.assertNotIn("abuser", f["unbewertet"])
        self.assertIn("cp_possession", f["unbewertet"])   # nur 'beste'!

        # Score aus 'schwerste': 3 (verdacht) + 5 (gerichtsfest) = 8
        self.assertEqual(f["score"], 8.0)
        self.assertEqual(f["hoechste_konfidenz"], "gerichtsfest")
        self.assertEqual(f["hoechstes_kriterium"], "identification")

    # ================================================================== CV03
    def test_cv03_korrektur_erhoeht_die_abdeckung_nicht(self):
        for conf in ("verdacht", "wahrscheinlich", "gerichtsfest"):
            self.repo.assess(subject_id=18, criterion_code="abuser",
                             extrem="schwerste", confidence_code=conf,
                             actor_id=2)
        f = self._by_case(CoverageRepo(self.con).coverage())[18]
        # DREI Erfassungen, aber EIN bewertetes Kriterium. Es zaehlt der
        # aktuelle Stand, nicht die Zahl der Erfassungen.
        self.assertEqual(f["n_bewertet"], 1)
        self.assertEqual(f["score"], 5.0)            # der juengste Stand

    # ================================================================== CV04
    def test_cv04_blinde_flecken_zuerst(self):
        self.repo.assess(subject_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         actor_id=2)
        cov = CoverageRepo(self.con).coverage()
        ids = [f["subject_id"] for f in cov["faelle"]]
        # 19 und 20 (Abdeckung 0) stehen VOR 18. Wer die Liste oeffnet, soll
        # sehen, WO NICHT ERMITTELT WURDE.
        self.assertEqual(ids[-1], 18)
        self.assertEqual(set(ids[:2]), {19, 20})

    # ================================================================== CV05
    def test_cv05_vermerk_reist_mit(self):
        cov = CoverageRepo(self.con).coverage()
        self.assertEqual(cov["vermerk"], VERMERK)
        self.assertIn("NICHT abgestimmt", cov["vermerk"])

    # ================================================================== CV06
    def test_cv06_summary(self):
        self.repo.assess(subject_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         actor_id=2)
        repo = CoverageRepo(self.con)
        cov = repo.coverage()
        s = repo.summary(cov)
        self.assertEqual(s["faelle_gesamt"], 3)
        self.assertEqual(s["nie_bewertet"], 2)       # die eigentliche Aussage
        self.assertEqual(s["voll_bewertet"], 0)
        self.assertEqual(s["abdeckung_mittel"], 0.03)   # (0.1+0+0)/3

    # ================================================================== CV07
    def test_cv07_stats_weist_die_differenz_aus(self):
        self.repo.assess(subject_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         actor_id=2)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        r = self._app().dispatch(1, "/api/results/stats", {})
        self.assertEqual(r.status, 200)
        st = json.loads(r.body)
        self.assertEqual(st["faelle"], 1)             # bewertete
        self.assertEqual(st["faelle_gesamt"], 3)      # alle
        # Ohne diese Zahl liest sich 'Bewertete Faelle: 1' wie eine
        # Vollerhebung. Die DIFFERENZ ist der Befund.
        self.assertEqual(st["faelle_unbewertet"], 2)

    # ================================================================== CV08
    def test_cv08_endpunkt_coverage(self):
        self.repo.assess(subject_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         actor_id=2)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        app = self._app()

        # Chefin (Scope 'alle'): alle drei Faelle.
        r = app.dispatch(1, "/api/results/coverage", {})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body)
        self.assertEqual(d["scope"], "alle")
        self.assertEqual(d["faelle_gesamt"], 3)
        self.assertEqual(d["summary"]["nie_bewertet"], 2)

        # Ermittler (Scope 'eigene'): NUR seine Faelle 18 und 19 — und KEIN
        # 403 (anders als bei /stats): "wie vollstaendig habe ICH meine Faelle
        # bewertet" ist eine legitime Eigenfrage.
        r = app.dispatch(2, "/api/results/coverage", {})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body)
        self.assertEqual(d["scope"], "eigene")
        self.assertEqual(d["faelle_gesamt"], 2)
        self.assertEqual({f["subject_id"] for f in d["faelle"]}, {18, 19})
        # Fall 20 (nicht zugewiesen) ist NICHT dabei.
        self.assertEqual(d["summary"]["nie_bewertet"], 1)   # nur 19

        # /stats bleibt fuer 'eigene' gesperrt (fallUEBERGREIFEND).
        self.assertEqual(app.dispatch(2, "/api/results/stats", {}).status, 403)

        # Build-391-Vertrag: parse_qs-Form darf nicht scheitern.
        self.assertEqual(
            app.dispatch(1, "/api/results/coverage", {"x": ["1"]}).status, 200)
        self.assertEqual(
            app.dispatch(1, "/api/results/coverage", None).status, 200)

    # ================================================================== CV09
    def test_cv09_cli_coverage(self):
        self.repo.assess(subject_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         actor_id=2)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = results_admin.main(["--db", self._db, "coverage"])

        # Exit 2 = es gibt blinde Flecken. Ein Skript darf das nicht uebersehen.
        self.assertEqual(rc, 2)
        self.assertIn("BLINDE FLECKEN", err.getvalue())
        self.assertIn("2 von 3", err.getvalue())
        o = out.getvalue()
        self.assertIn("boarder20", o)
        self.assertIn("ALLE (nie bewertet)", o)
        self.assertIn("Faelle gesamt: 3", o)

        # 'stats' nennt die Gesamtzahl jetzt ebenfalls.
        out = io.StringIO()
        with redirect_stdout(out):
            results_admin.main(["--db", self._db, "stats"])
        self.assertIn("1 von 3", out.getvalue())
        self.assertIn("noch gar nicht bewertet", out.getvalue())


if __name__ == "__main__":
    unittest.main()
