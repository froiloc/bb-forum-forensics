# =============================================================================
# tests/test_management_case_search.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fall-/Nutzer-Suche (AP-2G)
# =============================================================================
# Testsuite fuer Build 458: CaseSearchRepo + /api/search.
#
# CS01 — leerer Begriff -> keine Treffer
# CS02 — numerisch: user_id-Treffer (exakt zuerst)
# CS03 — Text: username-Teilstring (case-insensitiv)
# CS04 — scope 'eigene': nur zugewiesene Faelle
# CS05 — LIKE-Sonderzeichen (%,_) werden woertlich gesucht (escaped)
# CS06 — limit + truncated-Flag (kein stilles Abschneiden, GR1)
# CS07 — /api/search: 200 mit Treffern; 403 ohne dashboard.view
# CS08 — /api/search: scope 'eigene' (investigator) filtert auf eigene Faelle
#
# Version: v0.7.458 · Build: 458 · 2026-07-19
# =============================================================================

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.cases.case_search_repo import CaseSearchRepo   # noqa: E402


def _con():
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE person(id INTEGER PRIMARY KEY, system_username TEXT, "
                "display_name TEXT)")
    con.execute("INSERT INTO person VALUES(1,'h001','Chefin'),(2,'h002','Mueller')")
    con.execute("CREATE TABLE cases(user_id INTEGER PRIMARY KEY, username TEXT, "
                "status TEXT, assigned_to INTEGER)")
    for uid, un, st, asg in [
        (18, "taeter_sued", "open", 2),
        (19, "TAETER_nord", "in_progress", 2),
        (200, "alice", "open", 1),
        (2001, "bob_2001", "open", None),
        (30, "50%_rabatt", "open", None),
    ]:
        con.execute("INSERT INTO cases VALUES(?,?,?,?)", (uid, un, st, asg))
    con.commit()
    return con


class CaseSearchRepoTests(unittest.TestCase):
    def setUp(self):
        self.con = _con()
        self.repo = CaseSearchRepo(self.con)

    def test_cs01_empty(self):
        r = self.repo.search(q="  ")
        self.assertEqual(r["count"], 0)

    def test_cs02_numeric_userid(self):
        r = self.repo.search(q="200")
        uids = [x["user_id"] for x in r["results"]]
        # exakter Treffer 200 vor Teiltreffer 2001
        self.assertEqual(uids[0], 200)
        self.assertIn(2001, uids)

    def test_cs03_username_substring_ci(self):
        r = self.repo.search(q="taeter")
        uids = sorted(x["user_id"] for x in r["results"])
        self.assertEqual(uids, [18, 19])   # case-insensitiv

    def test_cs04_scope_eigene(self):
        r = self.repo.search(q="taeter", scope="eigene", person_id=2)
        self.assertEqual(sorted(x["user_id"] for x in r["results"]), [18, 19])
        r2 = self.repo.search(q="alice", scope="eigene", person_id=2)
        self.assertEqual(r2["count"], 0)   # alice ist person 1 zugewiesen

    def test_cs05_like_special_literal(self):
        r = self.repo.search(q="50%")
        self.assertEqual([x["user_id"] for x in r["results"]], [30])
        # '%' wird WOERTLICH gesucht: findet nur den Fall mit literalem '%'
        # (nicht alle 5 -> kein Wildcard).
        r2 = self.repo.search(q="%")
        self.assertEqual([x["user_id"] for x in r2["results"]], [30])

    def test_cs06_limit_truncated(self):
        r = self.repo.search(q="taeter", limit=1)
        self.assertEqual(r["count"], 1)
        self.assertTrue(r["truncated"])


# -- Endpunkt-Integration -----------------------------------------------------

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter # noqa: E402
from management.rbac.rbac_repo import RbacRepo                      # noqa: E402
from management.cases.cases_repo import CasesRepo                   # noqa: E402
from management.server.management_app import ManagementApp          # noqa: E402

_PERSON = ("CREATE TABLE person (id INTEGER PRIMARY KEY AUTOINCREMENT, "
           "system_username TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, "
           "is_investigator INTEGER NOT NULL DEFAULT 1, is_supervisor INTEGER "
           "NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0, "
           "created_at INTEGER NOT NULL)")
_OLD_SJ = ("CREATE TABLE scrape_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, "
           "user_id INTEGER NOT NULL, username TEXT NOT NULL, priority INTEGER "
           "NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5), status TEXT NOT "
           "NULL DEFAULT 'pending' CHECK(status IN ('pending','running','done',"
           "'failed')), manifest_path TEXT, output_path TEXT, worker_id TEXT, "
           "created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,"
           " error_message TEXT, assigned_to INTEGER, note TEXT, "
           "FOREIGN KEY(assigned_to) REFERENCES person(id))")


class SearchEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un, sup in ((1, "h0a2898", 1), (2, "h002", 0), (3, "h003", 0)):
            con.execute("INSERT INTO person (id, system_username, display_name, "
                        "is_supervisor, created_at) VALUES (?,?,?,?,?)",
                        (pid, un, un, sup, now))
        con.execute(_OLD_SJ)
        for uid in (18, 19):
            con.execute("INSERT INTO scrape_jobs (user_id, username, created_at) "
                        "VALUES (?,?,?)", (uid, "taeter_%d" % uid, now))
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="t").run()
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.con = con
        w = CoordinatorWriter(con, AuditLog(con))
        rbac = RbacRepo(con, w)
        cases = CasesRepo(con, w)
        rbac.grant("supervisor", "dashboard.view", scope="alle", actor_id=1)
        rbac.grant("investigator", "dashboard.view", scope="eigene", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        rbac.assign_role(2, "investigator", actor_id=1)
        for uid in (18, 19):
            cases.create_case(uid, "taeter_%d" % uid, actor_id=1)
        cases.assign(18, 2, actor_id=1)   # 18 -> person 2
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def tearDown(self):
        self.con.close()
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def test_cs07_endpoint_ok_and_forbidden(self):
        app = ManagementApp(self._db)
        r = app.dispatch(1, "/api/search", {"q": ["taeter"]})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["scope"], "alle")
        self.assertEqual(sorted(x["user_id"] for x in d["results"]), [18, 19])
        # person 3 hat keine Rolle -> 403
        self.assertEqual(app.dispatch(3, "/api/search", {"q": ["taeter"]}).status, 403)

    def test_cs08_endpoint_scope_eigene(self):
        app = ManagementApp(self._db)
        d = json.loads(app.dispatch(
            2, "/api/search", {"q": ["taeter"]}).body.decode("utf-8"))
        self.assertEqual(d["scope"], "eigene")
        self.assertEqual([x["user_id"] for x in d["results"]], [18])  # nur eigener


if __name__ == "__main__":
    unittest.main()
