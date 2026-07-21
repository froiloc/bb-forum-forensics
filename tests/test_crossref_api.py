# =============================================================================
# tests/test_crossref_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Testsuite fuer Build 470: Management-Endpunkte fuer 'identified_subject'.
#
# CA01 — GET /api/crossref ohne 'crossref.view' -> 403.
# CA02 — POST /api/crossref/set ohne 'crossref.edit' -> 403.
# CA03 — POST set legt an (created=True, audit_seq>0); GET listet ihn;
#        GET ?subject_id=N liefert den Einzeleintrag.
# CA04 — POST set erneut mit anderer Konfidenz -> Revision (created=False),
#        audit_seq steigt.
# CA05 — Validierung: leere real_identity / ungueltige confidence_code -> 400.
# CA06 — GET ?subject_id=<unbekannt> -> 404.
# CA07 — Sensibilitaet auf Endpunktebene: sensibler Klartext taucht NICHT im
#        rohen audit_log-Beleg auf.
#
# Version: v0.8.470 · Build: 470 · 2026-07-20
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

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac.rbac_repo import RbacRepo
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

_SECRET_NAME = "Erika Beispiel, geb. 1965, Beispielstadt"


class CrossrefApiTests(unittest.TestCase):

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
            [(1, "h001", "Chefin", 1, 1, 0, now),
             (2, "h002", "Beta", 1, 0, 0, now)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.rbac = RbacRepo(self.con, self.writer)
        # Person 1: supervisor mit crossref.view/edit. Person 2: investigator
        # OHNE crossref-Rechte (Deny-Nachweis).
        self.rbac.grant("supervisor", "crossref.view", scope="alle", actor_id=1)
        self.rbac.grant("supervisor", "crossref.edit", scope="alle", actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

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

    def _audit_raw(self, seq):
        c = sqlite3.connect(self.db_path)
        try:
            row = c.execute(
                "SELECT content FROM audit_log WHERE seq=?", (seq,)).fetchone()
            return row[0] if row else ""
        finally:
            c.close()

    # CA01 -------------------------------------------------------------------
    def test_ca01_get_forbidden_without_view(self):
        r = self.app.dispatch(2, "/api/crossref")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "crossref.view")

    # CA02 -------------------------------------------------------------------
    def test_ca02_post_forbidden_without_edit(self):
        r = self.app.dispatch_write(2, "/api/crossref/set", {
            "subject_id": 5, "real_identity": "X",
            "confidence_code": "verdacht"})
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "crossref.edit")

    # CA03 -------------------------------------------------------------------
    def test_ca03_set_then_list_and_get(self):
        r = self.app.dispatch_write(1, "/api/crossref/set", {
            "subject_id": 4711, "real_identity": "Max Muster",
            "confidence_code": "wahrscheinlich", "basis": "Zahlungsdaten"})
        self.assertEqual(r.status, 200)
        body = self._json(r)
        self.assertTrue(body["ok"])
        self.assertTrue(body["created"])
        self.assertGreater(body["audit_seq"], 0)

        lst = self._json(self.app.dispatch(1, "/api/crossref"))
        self.assertEqual([e["subject_id"] for e in lst["entries"]], [4711])
        self.assertEqual(lst["entries"][0]["confidence_ordinal"], 20)

        one = self._json(
            self.app.dispatch(1, "/api/crossref", {"subject_id": ["4711"]}))
        self.assertEqual(one["entry"]["real_identity"], "Max Muster")

    # CA04 -------------------------------------------------------------------
    def test_ca04_revision_increases_seq(self):
        r1 = self.app.dispatch_write(1, "/api/crossref/set", {
            "subject_id": 42, "real_identity": "A",
            "confidence_code": "verdacht"})
        seq1 = self._json(r1)["audit_seq"]
        r2 = self.app.dispatch_write(1, "/api/crossref/set", {
            "subject_id": 42, "real_identity": "A",
            "confidence_code": "gesichert"})
        body2 = self._json(r2)
        self.assertEqual(r2.status, 200)
        self.assertFalse(body2["created"])
        self.assertGreater(body2["audit_seq"], seq1)

    # CA05 -------------------------------------------------------------------
    def test_ca05_validation(self):
        r_empty = self.app.dispatch_write(1, "/api/crossref/set", {
            "subject_id": 1, "real_identity": "  ",
            "confidence_code": "verdacht"})
        self.assertEqual(r_empty.status, 400)
        r_bad = self.app.dispatch_write(1, "/api/crossref/set", {
            "subject_id": 1, "real_identity": "A",
            "confidence_code": "gerichtsfest"})
        self.assertEqual(r_bad.status, 400)

    # CA06 -------------------------------------------------------------------
    def test_ca06_get_unknown_404(self):
        r = self.app.dispatch(1, "/api/crossref", {"subject_id": ["999999"]})
        self.assertEqual(r.status, 404)
        self.assertEqual(self._json(r)["error"], "unknown_subject")

    # CA07 -------------------------------------------------------------------
    def test_ca07_freetext_not_in_audit(self):
        r = self.app.dispatch_write(1, "/api/crossref/set", {
            "subject_id": 8, "real_identity": _SECRET_NAME,
            "confidence_code": "gesichert",
            "basis": "vertrauliche Quelle", "note": "nicht aktenkundig"})
        seq = self._json(r)["audit_seq"]
        raw = self._audit_raw(seq)
        self.assertNotIn(_SECRET_NAME, raw)
        self.assertNotIn("vertrauliche Quelle", raw)
        self.assertNotIn("nicht aktenkundig", raw)


if __name__ == "__main__":
    unittest.main()
