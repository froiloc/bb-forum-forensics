# =============================================================================
# tests/test_management_server.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 346: Management-Server-Backend (read-only).
#
# M01 — /api/whoami: Identitaet + aufgeloeste Rollen/Faehigkeiten.
# M02 — /api/overview: 403 ohne dashboard.view; 200 mit; Scope 'eigene' filtert
#       auf eigene Zuweisungen, 'alle' liefert alle.
# M03 — /api/integrity: 403 ohne ops.view; 200 mit (ok, tip_seq, detail).
# M04 — / : Shell-HTML enthaelt den Anzeigenamen.
# M05 — unbekannter Pfad -> 404; /static/... -> 404 mit Hinweis.
# M06 — format_sse_event: RFC-8895-Rahmen (event:/data:/Leerzeile).
# M07 — startup_selfcheck: gruen bei vollstaendigem Katalog; RbacCatalogError
#       bei Luecke.
# M08 — IdentityResolver: Aufloesung via os_user_source-Mock; unbekannt ->
#       IdentityError.
# M09 — Live-Server: GET /api/whoami liefert JSON; POST -> 405 (read-only).
# M10 — Live-Server SSE: /events sendet zuerst ein 'hello' im RFC-8895-Rahmen.
# M11 — Read-Only-Nachweis: dispatch aendert audit_log nicht.
#
# Version: v0.7.346 · Build: 346 · 2026-07-10
# =============================================================================

import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac.rbac_repo import RbacRepo
from management.rbac.rbac_resolver import RbacCatalogError
from management.server.identity import IdentityError, IdentityResolver
from management.server.management_app import ManagementApp, format_sse_event
from management.server.management_handler import ManagementHTTPServer

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


class ManagementServerTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")

        now = int(time.time())
        self.con.execute(_PERSON)
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Chefin, Alpha", 1, 1, 0, now),
             (2, "h002", "Beta", 1, 0, 0, now)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        self.mods = discover(coordinator_migrations)
        MigrationRunner(self.con, self.mods, audit=self.audit,
                        deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)

        # h001 (person 1) = supervisor mit dashboard.view(alle) + ops.view(alle).
        self.repo.grant("supervisor", "dashboard.view", scope="alle", actor_id=1)
        self.repo.grant("supervisor", "ops.view", scope="alle", actor_id=1)
        self.repo.assign_role(1, "supervisor", actor_id=1)
        # h002 (person 2) = investigator mit dashboard.view(eigene), kein ops.view.
        self.repo.grant("investigator", "dashboard.view", scope="eigene",
                        actor_id=1)
        self.repo.assign_role(2, "investigator", actor_id=1)

        # Zwei Faelle: 18 h002 zugewiesen, 19 unzugewiesen.
        from management.cases.cases_repo import CasesRepo
        cases = CasesRepo(self.con, self.writer)
        cases.create_case(18, "KEKa", actor_id=1)
        cases.assign(18, 2, actor_id=1)
        cases.create_case(19, "LMN", actor_id=1)

        # WAL in Hauptdatei falten, damit read-only-Verbindungen sauber lesen.
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        self.app = ManagementApp(self.db_path)

    def tearDown(self):
        try:
            self.con.close()
        finally:
            for fn in os.listdir(self._tmp):
                try:
                    os.remove(os.path.join(self._tmp, fn))
                except OSError:
                    pass
            os.rmdir(self._tmp)

    def _json(self, resp):
        return json.loads(resp.body.decode("utf-8"))

    # M01 --------------------------------------------------------------------
    def test_m01_whoami(self):
        r = self.app.dispatch(1, "/api/whoami")
        self.assertEqual(r.status, 200)
        data = self._json(r)
        self.assertEqual(data["system_username"], "h001")
        self.assertEqual(data["display_name"], "Chefin, Alpha")
        self.assertIn("supervisor", data["roles"])
        self.assertEqual(data["capabilities"]["dashboard.view"], "alle")
        self.assertIn("ops.view", data["capabilities"])

    # M02 --------------------------------------------------------------------
    def test_m02_overview_gating_and_scope(self):
        # Person 2 hat dashboard.view(eigene) -> nur eigener Fall (18).
        r2 = self.app.dispatch(2, "/api/overview")
        self.assertEqual(r2.status, 200)
        d2 = self._json(r2)
        self.assertEqual(d2["scope"], "eigene")
        self.assertEqual({c["user_id"] for c in d2["cases"]}, {18})

        # Person 1 hat dashboard.view(alle) -> alle Faelle (18, 19).
        d1 = self._json(self.app.dispatch(1, "/api/overview"))
        self.assertEqual(d1["scope"], "alle")
        self.assertEqual({c["user_id"] for c in d1["cases"]}, {18, 19})

        # Person ohne Grant -> 403.
        self.repo.revoke_role(
            self.repo.list_person_roles(2)[0]["id"], actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        r_denied = self.app.dispatch(2, "/api/overview")
        self.assertEqual(r_denied.status, 403)
        self.assertEqual(self._json(r_denied)["capability"], "dashboard.view")

    # M03 --------------------------------------------------------------------
    def test_m03_integrity_gating(self):
        # Person 2 ohne ops.view -> 403.
        self.assertEqual(self.app.dispatch(2, "/api/integrity").status, 403)
        # Person 1 mit ops.view -> 200.
        r = self.app.dispatch(1, "/api/integrity")
        self.assertEqual(r.status, 200)
        data = self._json(r)
        self.assertTrue(data["ok"])
        self.assertGreater(data["tip_seq"], 0)

    # M04 --------------------------------------------------------------------
    def test_m04_shell(self):
        r = self.app.dispatch(1, "/")
        self.assertEqual(r.status, 200)
        self.assertIn("text/html", r.content_type)
        self.assertIn("Chefin, Alpha", r.body.decode("utf-8"))

    # M05 --------------------------------------------------------------------
    def test_m05_not_found(self):
        self.assertEqual(self.app.dispatch(1, "/nope").status, 404)
        r = self.app.dispatch(1, "/static/cockpit.js")
        self.assertEqual(r.status, 404)
        self.assertIn("Cockpit", self._json(r)["detail"])

    # M06 --------------------------------------------------------------------
    def test_m06_sse_format(self):
        raw = format_sse_event("changed", {"tip_seq": 7})
        self.assertEqual(raw, b'event: changed\ndata: {"tip_seq": 7}\n\n')

    # M07 --------------------------------------------------------------------
    def test_m07_startup_selfcheck(self):
        self.app.startup_selfcheck()  # gruen
        # Katalog-Luecke -> RbacCatalogError.
        self.con.execute("DELETE FROM rbac_capability WHERE code='ops.view'")
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with self.assertRaises(RbacCatalogError):
            self.app.startup_selfcheck()

    # M08 --------------------------------------------------------------------
    def test_m08_identity_resolver(self):
        res = IdentityResolver(self.db_path, os_user_source=lambda: "h001")
        person = res.resolve()
        self.assertEqual(person["id"], 1)
        self.assertEqual(person["system_username"], "h001")
        # Explizit + unbekannt.
        self.assertEqual(res.resolve("h002")["id"], 2)
        with self.assertRaises(IdentityError):
            res.resolve("h999")

    # M09 --------------------------------------------------------------------
    def test_m09_live_server_get_and_readonly(self):
        server = ManagementHTTPServer("127.0.0.1", 0, self.app, 1)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            with urlopen("http://127.0.0.1:%d/api/whoami" % port, timeout=5) as f:
                data = json.loads(f.read().decode("utf-8"))
            self.assertEqual(data["system_username"], "h001")

            # POST -> 405 (read-only).
            req = Request("http://127.0.0.1:%d/api/whoami" % port,
                          data=b"{}", method="POST")
            with self.assertRaises(HTTPError) as ctx:
                urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 405)
        finally:
            server.shutdown()
            server.server_close()

    # M10 --------------------------------------------------------------------
    def test_m10_live_sse_hello(self):
        server = ManagementHTTPServer("127.0.0.1", 0, self.app, 1,
                                      sse_poll_sec=0.2)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=5)
            s.sendall(b"GET /events HTTP/1.1\r\nHost: x\r\n\r\n")
            buf = b""
            s.settimeout(5)
            # Bis zum Ende des ersten SSE-Ereignisses (Leerzeile) lesen.
            deadline = time.time() + 5
            while b"\n\n" not in buf.split(b"\r\n\r\n", 1)[-1] and \
                    time.time() < deadline:
                buf += s.recv(1024)
            s.close()
            self.assertIn(b"text/event-stream", buf)
            self.assertIn(b"event: hello", buf)
            self.assertIn(b'"tip_seq"', buf)
        finally:
            server.shutdown()
            server.server_close()

    # M11 --------------------------------------------------------------------
    def test_m11_dispatch_read_only(self):
        before = self.con.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0]
        self.app.dispatch(1, "/api/whoami")
        self.app.dispatch(1, "/api/overview")
        self.app.dispatch(1, "/api/integrity")
        after = self.con.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
