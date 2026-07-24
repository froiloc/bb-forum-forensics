# =============================================================================
# tests/test_management_handover_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 520 (AP-2G / Idee 30): das Uebergabe-Protokoll aus
# Build 455/469 wird ueber '/api/handover' erreichbar. Bis Build 519 existierte
# es nur als Repo + CLI (Befund aus der Uebergabe 440-453).
#
# Die Rekonstruktionslogik ist in tests/test_management_handover.py belegt.
# HIER wird ausschliesslich die ANBINDUNG geprueft.
#
# HO01 — ohne handover.view -> 403 (default-deny)
# HO02 — Grundform: Zaehler, Eintraege und der angewandte Filter
# HO03 — Erstzuweisung: kind 'initial', KEIN Vorgaenger (from ist None) —
#        das ist eine Aussage, keine Luecke
# HO04 — Uebergabe: kind 'reassignment' mit korrektem Vorgaenger
# HO05 — Rueckgabe in den Rueckstau: kind 'unassignment', kein Empfaenger
# HO06 — jede Zeile traegt ihre BELEGNUMMER (seq) — der Nachweisanker
# HO07 — Filter auf einen Fall: nur dessen Eintraege, und der Filter faehrt
#        in der Antwort MIT (ein Ausschnitt darf nicht wie ein Ganzes wirken)
# HO08 — ungueltige subject_id -> 400 (handlungsleitend, nicht stillschweigend
#        als 'kein Filter' behandelt)
# HO09 — echter Leerbefund bei einem Fall ohne Zuweisungsbeleg
# HO10 — die Reihenfolge folgt der Audit-Kette, und zwar ABSTEIGEND
#        (neueste zuerst, Build 455) — das ist eine Zusage der Sicht
# HO11 — Katalog UND Seed (M029) zeichengleich
# HO12 — Akten-Export; der Export erbt die Rechtepruefung
#
# Version: v0.8.520 · Build: 520 · 2026-07-24
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


class HandoverApiTests(unittest.TestCase):

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
        self.repo.grant("supervisor", "handover.view", scope="alle", actor_id=1)
        self.repo.assign_role(1, "supervisor", actor_id=1)
        # person 3 bleibt ohne Rolle (HO01).

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

    def _get(self, person_id=1, subject_id=None):
        query = {} if subject_id is None else {"subject_id": [str(subject_id)]}
        r = self.app.dispatch(person_id, "/api/handover", query)
        self.assertEqual(r.status, 200)
        return self._json(r)

    def _for(self, data, subject_id):
        return [e for e in data["entries"] if e["subject_id"] == subject_id]

    # -------------------------------------------------------------- Tests
    # HO01 — default-deny.
    def test_ho01_ohne_recht_403(self):
        r = self.app.dispatch(3, "/api/handover")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "handover.view")

    # HO02 — Grundform.
    def test_ho02_grundform(self):
        self.cases.create_case(5001, "fall_a", actor_id=1)
        self.cases.assign(5001, 2, actor_id=1)
        self._checkpoint()
        d = self._get(1)
        for key in ("generated_at", "reassignment_count",
                    "cases_with_handover", "entries", "filter_subject_id"):
            self.assertIn(key, d, "Schluessel '%s' fehlt" % key)
        self.assertIsNone(d["filter_subject_id"])
        self.assertIsInstance(d["entries"], list)

    # HO03 — Erstzuweisung ohne Vorgaenger.
    def test_ho03_erstzuweisung(self):
        self.cases.create_case(5002, "fall_b", actor_id=1)
        self.cases.assign(5002, 2, actor_id=1)
        self._checkpoint()
        e = self._for(self._get(1), 5002)
        self.assertEqual(len(e), 1)
        self.assertEqual(e[0]["kind"], "initial")
        self.assertIsNone(e[0]["from_person_id"],
                          "bei der Erstzuweisung gibt es KEINEN Vorgaenger — "
                          "das ist eine Aussage, keine Luecke")
        self.assertEqual(e[0]["to_person_id"], 2)
        self.assertEqual(e[0]["by_person_id"], 1)
        self.assertEqual(e[0]["to_name"], "Beta")

    # HO04 — echte Uebergabe.
    def test_ho04_uebergabe(self):
        self.cases.create_case(5003, "fall_c", actor_id=1)
        self.cases.assign(5003, 2, actor_id=1)
        self.cases.assign(5003, 4, actor_id=1)
        self._checkpoint()
        d = self._get(1)
        # ACHTUNG: das Read-Model ordnet ABSTEIGEND (neueste zuerst, Build
        # 455). e[0] ist damit der JUENGSTE Eintrag.
        e = self._for(d, 5003)
        self.assertEqual(len(e), 2)
        self.assertEqual(e[0]["kind"], "reassignment")
        self.assertEqual(e[0]["from_person_id"], 2)
        self.assertEqual(e[0]["to_person_id"], 4)
        self.assertEqual(e[1]["kind"], "initial")
        self.assertGreaterEqual(d["reassignment_count"], 1)
        self.assertGreaterEqual(d["cases_with_handover"], 1)

    # HO05 — Rueckgabe in den Rueckstau.
    def test_ho05_rueckgabe(self):
        self.cases.create_case(5004, "fall_d", actor_id=1)
        self.cases.assign(5004, 2, actor_id=1)
        self.cases.assign(5004, None, actor_id=1)
        self._checkpoint()
        e = self._for(self._get(1), 5004)   # neueste zuerst
        self.assertEqual(len(e), 2)
        self.assertEqual(e[0]["kind"], "unassignment")
        self.assertEqual(e[0]["from_person_id"], 2)
        self.assertIsNone(e[0]["to_person_id"],
                          "eine Rueckgabe hat KEINEN Empfaenger")

    # HO06 — die Belegnummer ist der Nachweisanker.
    def test_ho06_belegnummer(self):
        self.cases.create_case(5005, "fall_e", actor_id=1)
        self.cases.assign(5005, 2, actor_id=1)
        self._checkpoint()
        e = self._for(self._get(1), 5005)[0]
        self.assertIsInstance(e["seq"], int)
        self.assertGreater(e["seq"], 0)
        # Die seq zeigt wirklich auf den Zuweisungsbeleg.
        row = self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq = ?",
            (e["seq"],)).fetchone()
        self.assertEqual(row["event_type"], "case_assigned")

    # HO07 — Filter, und er faehrt mit.
    def test_ho07_filter(self):
        self.cases.create_case(5010, "fall_f", actor_id=1)
        self.cases.assign(5010, 2, actor_id=1)
        self.cases.create_case(5011, "fall_g", actor_id=1)
        self.cases.assign(5011, 4, actor_id=1)
        self._checkpoint()

        alle = self._get(1)
        self.assertEqual(
            sorted({e["subject_id"] for e in alle["entries"]}), [5010, 5011])

        nur = self._get(1, subject_id=5010)
        self.assertEqual({e["subject_id"] for e in nur["entries"]}, {5010})
        self.assertEqual(nur["filter_subject_id"], 5010,
                         "der angewandte Ausschnitt muss in der Antwort "
                         "stehen — sonst sieht ein Ausschnitt aus wie das "
                         "Ganze")

    # HO08 — ungueltiger Filter wird BENANNT statt stillschweigend ignoriert.
    def test_ho08_ungueltiger_filter(self):
        r = self.app.dispatch(1, "/api/handover", {"subject_id": ["abc"]})
        self.assertEqual(r.status, 400)
        self.assertIn("ganze Zahl", self._json(r)["detail"])

    # HO09 — echter Leerbefund.
    def test_ho09_leerbefund(self):
        self.cases.create_case(5020, "nie_zugewiesen", actor_id=1)
        self._checkpoint()
        d = self._get(1, subject_id=5020)
        self.assertEqual(d["entries"], [])
        self.assertEqual(d["reassignment_count"], 0)
        self.assertEqual(d["filter_subject_id"], 5020)

    # HO10 — Reihenfolge der Audit-Kette: ABSTEIGEND (neueste zuerst).
    #        Das ist die Zusage aus Build 455 und wird hier festgenagelt,
    #        damit das Frontend sie nicht heimlich anders auslegt.
    def test_ho10_reihenfolge_absteigend(self):
        self.cases.create_case(5030, "fall_h", actor_id=1)
        self.cases.assign(5030, 2, actor_id=1)
        self.cases.assign(5030, 4, actor_id=1)
        self.cases.create_case(5031, "fall_i", actor_id=1)
        self.cases.assign(5031, 2, actor_id=1)
        self._checkpoint()
        seqs = [e["seq"] for e in self._get(1)["entries"]]
        self.assertEqual(seqs, sorted(seqs, reverse=True),
                         "die Sicht zeigt die neueste Uebergabe zuerst")
        # Innerhalb EINES Falls bleibt der Ablauf damit rueckwaerts lesbar.
        e = self._for(self._get(1), 5030)
        self.assertEqual([x["kind"] for x in e],
                         ["reassignment", "initial"])

    # HO11 — Katalog UND Seed.
    def test_ho11_katalog_und_seed(self):
        self.assertIn("handover.view", catalog.CAPABILITY_CODES)
        row = self.con.execute(
            "SELECT code, label, description FROM rbac_capability "
            "WHERE code = 'handover.view'").fetchone()
        self.assertIsNotNone(row, "handover.view ist nicht geseedet (M029)")
        cat = {c.code: (c.label, c.description) for c in catalog.CAPABILITIES}
        self.assertEqual((row["label"], row["description"]),
                         cat["handover.view"])

    # HO12 — Akten-Export.
    def test_ho12_aktenexport(self):
        spec = spec_for("handover")
        self.assertIsNotNone(spec, "Sicht 'handover' fehlt im Export-Katalog")
        self.assertIn("entries", [s.key for s in spec.sections])

        self.cases.create_case(5040, "fall_j", actor_id=1)
        self.cases.assign(5040, 2, actor_id=1)
        self._checkpoint()

        r = self.app.dispatch(1, "/api/view/export", {"view": ["handover"]})
        self.assertEqual(r.status, 200)
        html = r.body.decode("utf-8")
        self.assertIn("Übergaben", html)
        self.assertIn("5040", html)

        # Der FILTER faehrt in den Export mit — sonst zeigte das Dokument den
        # ganzen Bestand, waehrend die Sicht eingeschraenkt ist.
        r2 = self.app.dispatch(1, "/api/view/export",
                               {"view": ["handover"], "subject_id": ["5040"]})
        self.assertEqual(r2.status, 200)
        self.assertIn("subject_id", r2.body.decode("utf-8"))

        # Der Export erbt die Rechtepruefung der Sicht.
        r3 = self.app.dispatch(3, "/api/view/export", {"view": ["handover"]})
        self.assertEqual(r3.status, 403)


if __name__ == "__main__":
    unittest.main()
