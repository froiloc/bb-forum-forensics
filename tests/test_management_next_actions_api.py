# =============================================================================
# tests/test_management_next_actions_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 519 (AP-2F / Idee 22): das Read-Model "Naechstbeste
# Aktion" aus Build 452/469 wird ueber '/api/next_actions' erreichbar. Bis
# Build 518 existierte es nur als Repo + CLI und war in keiner Cockpit-Sicht
# vorhanden (Befund aus der Uebergabe 440-453).
#
# Die Ableitungslogik selbst ist in tests/test_management_next_actions.py
# belegt. HIER wird ausschliesslich die ANBINDUNG geprueft.
#
# NA01 — ohne nextactions.view -> 403 (default-deny)
# NA02 — Grundform: Zaehler und Schlange vorhanden
# NA03 — jede Zeile traegt eine BELEGTE Begruendung (kein erfundener Rat)
# NA04 — Scope 'alle': fremde Faelle sind dabei
# NA05 — Scope 'eigene': NUR die eigenen Faelle — und 'scope' sagt das
# NA06 — kein Scope gesetzt -> restriktiv als 'eigene' behandelt
# NA07 — 'granted_scope' weist den Grant getrennt vom ANGEWANDTEN Scope aus
# NA08 — abgeschlossene Faelle stehen nicht in der Schlange, werden aber
#        GEZAEHLT (done_excluded) — kein stiller Verzicht
# NA09 — echter Leerbefund: leere Schlange bei belegter Fallzahl
# NA10 — Katalog UND Seed (M028) zeichengleich
# NA11 — Akten-Export der Sicht; der Export erbt die Rechtepruefung
#
# Version: v0.8.519 · Build: 519 · 2026-07-24
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
from management.cases.cases_repo import CasesRepo
from management.export.view_export_catalog import spec_for
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac import catalog
from management.rbac.rbac_repo import RbacRepo
from management.server.management_app import ManagementApp

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


class NextActionsApiTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")

        self.NOW = int(time.time())
        self.con.execute(_PERSON)
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Chefin, Alpha", 1, 1, 0, self.NOW),
             (2, "h002", "Beta", 1, 0, 0, self.NOW),
             (3, "h003", "Gamma", 1, 0, 0, self.NOW),
             (4, "h004", "Delta", 1, 0, 0, self.NOW)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)
        # person 1: Verteilsicht (alle).
        self.repo.grant("supervisor", "nextactions.view", scope="alle",
                        actor_id=1)
        self.repo.assign_role(1, "supervisor", actor_id=1)
        # person 2: eigene Schlange.
        self.repo.grant("investigator", "nextactions.view", scope="eigene",
                        actor_id=1)
        self.repo.assign_role(2, "investigator", actor_id=1)
        # person 4: das Recht OHNE Scope -> muss restriktiv als 'eigene'
        # behandelt werden (NA06).
        self.repo.grant("support", "nextactions.view", scope=None, actor_id=1)
        self.repo.assign_role(4, "support", actor_id=1)
        # person 3: gar nichts (NA01).

        self.cases = CasesRepo(self.con, self.writer)
        self._checkpoint()
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

    # ------------------------------------------------------------- Helfer
    def _checkpoint(self):
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _json(self, resp):
        return json.loads(resp.body.decode("utf-8"))

    def _get(self, person_id=1):
        r = self.app.dispatch(person_id, "/api/next_actions")
        self.assertEqual(r.status, 200)
        return self._json(r)

    def _mk(self, subject_id, username, assigned_to=None, status=None):
        self.cases.create_case(subject_id, username, actor_id=1)
        if assigned_to is not None:
            self.cases.assign(subject_id, assigned_to, actor_id=1)
        if status is not None:
            self.cases.set_status(subject_id, status, actor_id=1)
        self._checkpoint()

    def _ids(self, data):
        return sorted(i["subject_id"] for i in data["items"])

    # -------------------------------------------------------------- Tests
    # NA01 — default-deny.
    def test_na01_ohne_recht_403(self):
        r = self.app.dispatch(3, "/api/next_actions")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "nextactions.view")

    # NA02 — Grundform.
    def test_na02_grundform(self):
        self._mk(6001, "offen_unzug")
        d = self._get(1)
        for key in ("generated_at", "scope", "granted_scope", "total_cases",
                    "actionable", "done_excluded", "items"):
            self.assertIn(key, d, "Schluessel '%s' fehlt" % key)
        self.assertIsInstance(d["items"], list)

    # NA03 — jede Zeile ist begruendet. Ein Rat ohne Grundlage waere in
    #        diesem Projekt keine Handlungsempfehlung, sondern eine
    #        unbelegte Behauptung.
    def test_na03_jede_zeile_begruendet(self):
        self._mk(6002, "offen_unzug")
        self._mk(6003, "zugewiesen", assigned_to=2)
        d = self._get(1)
        self.assertTrue(d["items"])
        for i in d["items"]:
            for key in ("subject_id", "username", "action", "reason",
                        "urgency", "priority", "ampel", "status", "assigned",
                        "last_activity_at"):
                self.assertIn(key, i)
            self.assertTrue(i["action"].strip())
            self.assertTrue(i["reason"].strip(),
                            "eine Empfehlung ohne Begruendung waere kein Beleg")
            self.assertIn(i["urgency"], ("dringend", "bald", "routine"))

    # NA04 — Verteilsicht.
    def test_na04_scope_alle(self):
        self._mk(6010, "bei_beta", assigned_to=2)
        self._mk(6011, "unzugewiesen")
        d = self._get(1)
        self.assertEqual(d["scope"], "alle")
        self.assertEqual(self._ids(d), [6010, 6011])

    # NA05 — eigene Schlange.
    def test_na05_scope_eigene(self):
        self._mk(6020, "bei_beta", assigned_to=2)
        self._mk(6021, "bei_chefin", assigned_to=1)
        self._mk(6022, "unzugewiesen")
        d = self._get(2)
        self.assertEqual(d["scope"], "eigene")
        self.assertEqual(self._ids(d), [6020])

    # NA06 — kein Scope -> restriktiv. Ein ungesetzter Scope darf nie
    #        versehentlich die Verteilsicht oeffnen.
    def test_na06_ohne_scope_restriktiv(self):
        self._mk(6030, "bei_beta", assigned_to=2)
        self._mk(6031, "bei_delta", assigned_to=4)
        d = self._get(4)
        self.assertEqual(d["scope"], "eigene")
        self.assertEqual(self._ids(d), [6031])

    # NA07 — der GRANT wird getrennt vom ANGEWANDTEN Scope ausgewiesen.
    def test_na07_granted_scope(self):
        self.assertEqual(self._get(1)["granted_scope"], "alle")
        self.assertEqual(self._get(2)["granted_scope"], "eigene")
        # Ohne Scope: der Grant sagt None, angewandt wurde 'eigene'.
        d4 = self._get(4)
        self.assertIsNone(d4["granted_scope"])
        self.assertEqual(d4["scope"], "eigene")

    # NA08 — abgeschlossene Faelle: nicht in der Schlange, aber gezaehlt.
    def test_na08_abgeschlossene_gezaehlt(self):
        self._mk(6040, "offen", assigned_to=2)
        self._mk(6041, "erledigt", assigned_to=2, status="closed")
        self._mk(6042, "abgenommen", assigned_to=2, status="approved")
        d = self._get(1)
        self.assertEqual(self._ids(d), [6040])
        self.assertEqual(d["done_excluded"], 2,
                         "abgeschlossene Faelle muessen GEZAEHLT werden — "
                         "sonst saehe eine kurze Schlange wie ein Datenfehler "
                         "aus")
        self.assertEqual(d["total_cases"], 3)
        self.assertEqual(d["actionable"], 1)

    # NA09 — echter Leerbefund, unterscheidbar von 'nicht erhoben'.
    def test_na09_echter_leerbefund(self):
        self._mk(6050, "erledigt", assigned_to=2, status="closed")
        d = self._get(1)
        self.assertEqual(d["items"], [])
        self.assertEqual(d["actionable"], 0)
        # Die Erhebung HAT stattgefunden.
        self.assertEqual(d["total_cases"], 1)
        self.assertEqual(d["done_excluded"], 1)

    # NA10 — Katalog UND Seed.
    def test_na10_katalog_und_seed(self):
        self.assertIn("nextactions.view", catalog.CAPABILITY_CODES)
        row = self.con.execute(
            "SELECT code, label, description FROM rbac_capability "
            "WHERE code = 'nextactions.view'").fetchone()
        self.assertIsNotNone(row, "nextactions.view ist nicht geseedet (M028)")
        cat = {c.code: (c.label, c.description) for c in catalog.CAPABILITIES}
        self.assertEqual((row["label"], row["description"]),
                         cat["nextactions.view"])

    # NA11 — Akten-Export.
    def test_na11_aktenexport(self):
        spec = spec_for("nextactions")
        self.assertIsNotNone(spec,
                             "Sicht 'nextactions' fehlt im Export-Katalog")
        self.assertIn("items", [s.key for s in spec.sections])

        self._mk(6060, "offen_unzug")
        r = self.app.dispatch(1, "/api/view/export", {"view": ["nextactions"]})
        self.assertEqual(r.status, 200)
        html = r.body.decode("utf-8")
        self.assertIn("Arbeitsschlange", html)
        self.assertIn("6060", html)
        # Der Umfang steht mit im Dokument — sonst bliebe offen, WESSEN
        # Schlange abgebildet ist.
        self.assertIn("scope", html)

        # Der Export erbt die Rechtepruefung der Sicht.
        r3 = self.app.dispatch(3, "/api/view/export", {"view": ["nextactions"]})
        self.assertEqual(r3.status, 403)


if __name__ == "__main__":
    unittest.main()
