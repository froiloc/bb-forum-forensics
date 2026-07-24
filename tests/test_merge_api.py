# =============================================================================
# tests/test_merge_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Testsuite fuer Build 509: Management-Endpunkte des Identitaets-Merge/Split.
#
# MA01 — GET /api/merge ohne 'crossref.view' -> 403.
# MA02 — POST /api/merge/* ohne 'crossref.edit' -> 403 (alle drei Routen).
# MA03 — set (anlegen) -> GET listet; die Konfidenz-Achse kommt vom SERVER.
# MA04 — ?subject_id=N liefert die GANZE Gruppe, auch wenn N nicht das
#        Primaerkonto ist.
# MA05 — split -> ohne Flag unsichtbar, mit ?include_split=1 sichtbar;
#        remerge macht es rueckgaengig.
# MA06 — Fachliche Konflikte (Kette, Doppelzuordnung, Selbstverschmelzung,
#        fehlender Grund) sind 400 MIT sprechendem Text — nicht 500.
# MA07 — SENSIBILITAET auf Endpunktebene: der Klartext steht nicht im Beleg.
#
# Version: v0.8.509 · Build: 509 · 2026-07-24
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

_GEHEIM = "Gleiche IP 203.0.113.9, Bestandsauskunft vom 12.03. (Zeuge M.)"


class MergeApiTests(unittest.TestCase):

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
             (2, "h002", "Beta", 1, 0, 0, now)])
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(self.con, self.audit)
        self.rbac = RbacRepo(self.con, self.writer)
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

    def _set(self, primary, merged, conf="verdacht", basis="Indizien",
             actor=1):
        return self.app.dispatch_write(actor, "/api/merge/set", {
            "primary_subject_id": primary, "merged_subject_id": merged,
            "basis": basis, "confidence_code": conf})

    def _all_audit_raw(self):
        c = sqlite3.connect(self.db_path)
        try:
            rows = c.execute(
                "SELECT event_type, content, meta FROM audit_log").fetchall()
            return "\n".join("%s %s %s" % (r[0], r[1], r[2]) for r in rows)
        finally:
            c.close()

    # MA01 -------------------------------------------------------------------
    def test_ma01_get_forbidden_without_view(self):
        r = self.app.dispatch(2, "/api/merge")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "crossref.view")

    # MA02 -------------------------------------------------------------------
    def test_ma02_post_forbidden_without_edit(self):
        for path, body in (
            ("/api/merge/set", {"primary_subject_id": 1,
                                "merged_subject_id": 2, "basis": "x",
                                "confidence_code": "verdacht"}),
            ("/api/merge/split", {"merge_id": 1, "reason": "x"}),
            ("/api/merge/remerge", {"merge_id": 1}),
        ):
            r = self.app.dispatch_write(2, path, body)
            self.assertEqual(r.status, 403, path)
            self.assertEqual(self._json(r)["capability"], "crossref.edit", path)

    # MA03 -------------------------------------------------------------------
    def test_ma03_set_then_list(self):
        r = self._set(4711, 90210, conf="wahrscheinlich",
                      basis="Schreibstil + Zeitmuster")
        self.assertEqual(r.status, 200)
        body = self._json(r)
        self.assertTrue(body["ok"])
        self.assertGreater(body["audit_seq"], 0)

        lst = self._json(self.app.dispatch(1, "/api/merge"))
        self.assertEqual(len(lst["entries"]), 1)
        self.assertEqual(lst["entries"][0]["primary_subject_id"], 4711)
        self.assertEqual(lst["entries"][0]["confidence_ordinal"], 20)
        self.assertEqual(lst["counts"]["aktiv"], 1)
        self.assertEqual(lst["mode"], "all")
        # Die Konfidenz-Achse kommt vom Server (dieselbe wie in M018).
        codes = [c["code"] for c in lst["confidence"]]
        self.assertEqual(codes, ["verdacht", "wahrscheinlich", "gesichert"])

        # Revision ueber dieselbe Route (mit merge_id).
        mid = lst["entries"][0]["id"]
        rev = self.app.dispatch_write(1, "/api/merge/set", {
            "merge_id": mid, "confidence_code": "gesichert"})
        self.assertEqual(rev.status, 200)
        lst2 = self._json(self.app.dispatch(1, "/api/merge"))
        self.assertEqual(lst2["entries"][0]["confidence_code"], "gesichert")

    # MA04 -------------------------------------------------------------------
    def test_ma04_group_from_any_member(self):
        self._set(4711, 90210)
        self._set(4711, 555)

        for gefragt in (4711, 90210, 555):
            g = self._json(self.app.dispatch(
                1, "/api/merge", {"subject_id": [str(gefragt)]}))
            self.assertEqual(g["mode"], "group")
            self.assertEqual(g["group"]["primary_subject_id"], 4711)
            self.assertEqual(sorted(g["group"]["members"]),
                             [555, 4711, 90210])
            self.assertEqual(len(g["entries"]), 2)

        # Unbeteiligtes Konto: eigene Gruppe, kein Leerbefund.
        allein = self._json(self.app.dispatch(
            1, "/api/merge", {"subject_id": ["999"]}))
        self.assertEqual(allein["group"]["members"], [999])
        self.assertTrue(allein["group"]["is_primary"])

        # Ungueltige subject_id -> 400.
        self.assertEqual(self.app.dispatch(
            1, "/api/merge", {"subject_id": ["abc"]}).status, 400)

    # MA05 -------------------------------------------------------------------
    def test_ma05_split_and_remerge(self):
        mid = self._json(self._set(4711, 90210))["merge_id"]
        r = self.app.dispatch_write(1, "/api/merge/split", {
            "merge_id": mid, "reason": "Bestandsauskunft war fehlerhaft"})
        self.assertEqual(r.status, 200)

        ohne = self._json(self.app.dispatch(1, "/api/merge"))
        self.assertEqual(ohne["entries"], [])
        mit = self._json(self.app.dispatch(
            1, "/api/merge", {"include_split": ["1"]}))
        self.assertEqual(len(mit["entries"]), 1)
        self.assertFalse(mit["entries"][0]["is_active"])
        self.assertEqual(mit["entries"][0]["split_reason"],
                         "Bestandsauskunft war fehlerhaft")
        self.assertEqual(mit["counts"]["getrennt"], 1)

        r2 = self.app.dispatch_write(1, "/api/merge/remerge",
                                     {"merge_id": mid})
        self.assertEqual(r2.status, 200)
        self.assertEqual(
            len(self._json(self.app.dispatch(1, "/api/merge"))["entries"]), 1)

    # MA06 -------------------------------------------------------------------
    def test_ma06_conflicts_are_400_with_message(self):
        self._set(4711, 90210)

        # Selbstverschmelzung.
        selbst = self._set(5, 5)
        self.assertEqual(selbst.status, 400)
        self.assertIn("mit sich selbst", self._json(selbst)["detail"])

        # Doppelzuordnung — die Meldung nennt das bisherige Primaerkonto.
        doppel = self._set(1234, 90210)
        self.assertEqual(doppel.status, 400)
        self.assertIn("4711", self._json(doppel)["detail"])

        # KETTE, Richtung B: 90210 haengt schon unter 4711 und soll jetzt
        # selbst Primaerkonto werden. Die Meldung nennt das richtige
        # Primaerkonto als konstruktiven Ausweg.
        kette_b = self._set(90210, 555)
        self.assertEqual(kette_b.status, 400)
        detail_b = self._json(kette_b)["detail"]
        self.assertIn("selbst dem Primaerkonto", detail_b)
        self.assertIn("4711", detail_b)

        # KETTE, Richtung A: 7000 ist Primaer fuer 8000 und soll unter 9000.
        self._set(7000, 8000)
        kette_a = self._set(9000, 7000)
        self.assertEqual(kette_a.status, 400)
        self.assertIn("Ketten sind nicht vorgesehen",
                      self._json(kette_a)["detail"])

        # Fehlende Basis.
        ohne_basis = self._set(1, 2, basis="   ")
        self.assertEqual(ohne_basis.status, 400)

        # Trennung ohne Grund.
        mid = self._json(self.app.dispatch(1, "/api/merge"))["entries"][0]["id"]
        ohne_grund = self.app.dispatch_write(1, "/api/merge/split", {
            "merge_id": mid, "reason": "  "})
        self.assertEqual(ohne_grund.status, 400)

        # Fehlende/ungueltige Kennungen.
        self.assertEqual(self.app.dispatch_write(
            1, "/api/merge/set", {"basis": "x"}).status, 400)
        self.assertEqual(self.app.dispatch_write(
            1, "/api/merge/split", {"reason": "x"}).status, 400)
        self.assertEqual(self.app.dispatch_write(
            1, "/api/merge/remerge", {}).status, 400)
        # Unbekannte Zusammenfuehrung -> fachlich, also 400.
        self.assertEqual(self.app.dispatch_write(
            1, "/api/merge/split",
            {"merge_id": 99999, "reason": "x"}).status, 400)

    # MA07 -------------------------------------------------------------------
    def test_ma07_sensitivity_at_endpoint(self):
        mid = self._json(self._set(4711, 90210, basis=_GEHEIM))["merge_id"]
        self.app.dispatch_write(1, "/api/merge/split", {
            "merge_id": mid, "reason": "Zeuge M. hat widerrufen"})

        raw = self._all_audit_raw()
        for geheim in (_GEHEIM, "203.0.113.9", "Zeuge M. hat widerrufen"):
            self.assertNotIn(geheim, raw,
                             "Sensibler Klartext %r steht im audit_log!"
                             % geheim)
        self.assertIn("subject_merged", raw)
        self.assertIn("subject_split", raw)


if __name__ == "__main__":
    unittest.main()
