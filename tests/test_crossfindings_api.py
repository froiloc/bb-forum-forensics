# =============================================================================
# tests/test_crossfindings_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Testsuite fuer Build 474: Management-Endpunkt GET /api/crossfindings.
#
# CX-API01 — GET /api/crossfindings ohne 'crossref.view' -> 403.
# CX-API02 — Liste + counts; subject_id normalisiert; source_name gejoint;
#            Status offen/integriert.
# CX-API03 — ?only_open=1 filtert auf offene Funde.
# CX-API04 — Substrat fehlt -> 503 (kein stiller Leerbefund, Grundregel 1).
#             SEIT BUILD 506 (M023) bringt die Migrationskette das Substrat
#             mit; der Fall kann in einer migrierten coordinator.db nicht mehr
#             eintreten. Der Test baut deshalb ausdruecklich eine DB OHNE
#             gelaufene Kette — der Waechter wird NICHT entfernt, weil ein
#             entfernter Waechter genau der stille Leerbefund waere, den
#             Grundregel 1 verbietet.
#
# Version: v0.8.506 · Build: 506 · 2026-07-24 (M023-Anpassung)
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

_PCA = """
CREATE TABLE pending_cross_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, source_iid INTEGER NOT NULL,
    target_uid INTEGER NOT NULL, db_path TEXT NOT NULL,
    annotation_local_id TEXT NOT NULL, created_at INTEGER NOT NULL,
    integrated_at INTEGER DEFAULT NULL
)
"""


class CrossfindingsApiTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.now = int(time.time())
        self.con.execute(_PERSON)
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Chefin", 1, 1, 0, self.now),
             (2, "h002", "Beta", 1, 0, 0, self.now)])
        self.con.execute(_OLD_SCRAPE_JOBS)
        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(self.con, self.audit)
        self.rbac = RbacRepo(self.con, self.writer)
        self.rbac.grant("supervisor", "crossref.view", scope="alle", actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)
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

    def _pca_with_rows(self):
        # M023 (Build 506) legt 'pending_cross_annotations' bereits in der
        # Kette an — hier wird deshalb nur noch BEFUELLT, nicht mehr erzeugt.
        self.con.executemany(
            "INSERT INTO pending_cross_annotations "
            "(source_iid, target_uid, db_path, annotation_local_id, "
            " created_at, integrated_at) VALUES (?, ?, ?, ?, ?, ?)",
            [(1, 800, "/x/e1.db", "a1", self.now - 20, None),
             (1, 801, "/x/e2.db", "a2", self.now - 5, self.now)])
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # CX-API01 ---------------------------------------------------------------
    def test_api01_forbidden_without_view(self):
        r = self.app.dispatch(2, "/api/crossfindings")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "crossref.view")

    # CX-API02 ---------------------------------------------------------------
    def test_api02_list_and_counts(self):
        self._pca_with_rows()
        r = self.app.dispatch(1, "/api/crossfindings")
        self.assertEqual(r.status, 200)
        body = self._json(r)
        self.assertEqual(body["counts"],
                         {"total": 2, "offen": 1, "integriert": 1})
        # Offener Fund zuerst; subject_id normalisiert; source gejoint.
        self.assertEqual(body["findings"][0]["subject_id"], 800)
        self.assertEqual(body["findings"][0]["status"], "offen")
        self.assertEqual(body["findings"][0]["source_name"], "Chefin")
        self.assertEqual(body["findings"][1]["status"], "integriert")

    # CX-API03 ---------------------------------------------------------------
    def test_api03_only_open(self):
        self._pca_with_rows()
        r = self.app.dispatch(1, "/api/crossfindings", {"only_open": ["1"]})
        body = self._json(r)
        self.assertEqual([f["subject_id"] for f in body["findings"]], [800])
        self.assertEqual(body["counts"]["total"], 2)  # counts bleibt gesamt

    # CX-API04 ---------------------------------------------------------------
    def test_api04_substrate_missing_503(self):
        """
        Fehlendes Substrat ist ein BETRIEBSFEHLER (503), kein Leerbefund (200
        mit leerer Liste). Seit M023 legt die Kette die Tabelle an, deshalb
        wird hier eine coordinator.db OHNE gelaufene Kette gebaut — nur mit
        dem Minimum, das ManagementApp fuer die Rechtepruefung braucht.
        """
        bare_dir = tempfile.mkdtemp()
        bare_path = os.path.join(bare_dir, "coordinator.db")
        bare = sqlite3.connect(bare_path)
        try:
            bare.isolation_level = None
            bare.row_factory = sqlite3.Row
            # Schema der Rechte-Aufloesung aus der ECHTEN Kette holen, aber
            # NUR bis M022 — M023 ist genau die Migration, die das Substrat
            # anlegen wuerde.
            mods = [m for m in discover(coordinator_migrations)
                    if m.VERSION < 23]
            now = int(time.time())
            bare.execute(_PERSON)
            bare.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (1, 'h001', 'Chefin', 1, 1, 0, ?)", (now,))
            bare.execute(_OLD_SCRAPE_JOBS)
            audit = AuditLog(bare)
            MigrationRunner(bare, mods, audit=audit,
                            deployed_by="tester").run()
            rbac = RbacRepo(bare, CoordinatorWriter(bare, audit))
            rbac.grant("supervisor", "crossref.view", scope="alle",
                       actor_id=1)
            rbac.assign_role(1, "supervisor", actor_id=1)
            # Belegen, dass die Vorbedingung wirklich gilt:
            self.assertIsNone(bare.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='pending_cross_annotations'").fetchone())
            bare.close()

            app = ManagementApp(bare_path)
            r = app.dispatch(1, "/api/crossfindings")
            self.assertEqual(r.status, 503)
            self.assertEqual(self._json(r)["error"],
                             "crossfindings_unavailable")
        finally:
            try:
                bare.close()
            except Exception:      # noqa: BLE001 — schon geschlossen
                pass
            for fn in os.listdir(bare_dir):
                try:
                    os.remove(os.path.join(bare_dir, fn))
                except OSError:
                    pass
            os.rmdir(bare_dir)

    # CX-API05 (Build 506) ---------------------------------------------------
    def test_api05_substrat_kommt_aus_der_kette(self):
        """
        Der positive Gegenbeweis zu API04 und der eigentliche Zweck von M023:
        in einer regulaer migrierten coordinator.db ist das Substrat DA — der
        Endpunkt antwortet mit 200 und einem echten Leerbefund (0 Funde),
        statt mit 503. Genau das schliesst die Luecke aus Bug 2.78.
        """
        r = self.app.dispatch(1, "/api/crossfindings")
        self.assertEqual(r.status, 200)
        body = self._json(r)
        self.assertEqual(body["findings"], [])
        self.assertEqual(body["counts"],
                         {"total": 0, "offen": 0, "integriert": 0})


if __name__ == "__main__":
    unittest.main()
