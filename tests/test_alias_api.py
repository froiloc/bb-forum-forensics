# =============================================================================
# tests/test_alias_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Testsuite fuer Build 504: Management-Endpunkte des globalen Alias-Katalogs.
#
# AA01 — GET /api/alias ohne 'crossref.view' -> 403.
# AA02 — POST /api/alias/* ohne 'crossref.edit' -> 403 (alle vier Routen).
# AA03 — add -> GET listet; die Arten-Liste kommt vom SERVER mit.
# AA04 — retract -> ohne Flag unsichtbar, mit ?include_retracted=1 sichtbar.
# AA05 — Validierung: Duplikat / fehlender Grund / unbekannte Art / fehlende
#        alias_id -> 400 (nicht 500 — es ist ein FACHLICHER Fehler).
# AA06 — Rueckwaertssuche ?q= findet ueber die Normform, auch bei anderer
#        Gross-/Kleinschreibung und ueber Kontogrenzen hinweg.
# AA07 — SENSIBILITAET auf Endpunktebene: der Klartext steht nicht im Beleg.
#
# HINWEIS zur Query-Form: dispatch() bekommt die Query in der parse_qs-Form
# (Dict[str, List[str]]) — die Tests benutzen bewusst die ECHTE Listenform
# (Lehre aus QV01, siehe _q1-Kommentar in management_app.py).
#
# Version: v0.8.504 · Build: 504 · 2026-07-24
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

_SECRET_ALIAS = "SchmidtHausmeister1972"
_SECRET_BASIS = "Signaturvergleich mit Bestandsauskunft vom 12.03."


class AliasApiTests(unittest.TestCase):

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
        # OHNE crossref-Rechte (Deny-Nachweis, default-deny).
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

    def _all_audit_raw(self):
        """
        Roher Beleg-Text. 'content' und 'meta' sind die Felder, in denen
        sensibler Klartext dauerhaft haengen bliebe (sie gehen in die
        Hash-Kette ein); 'event_type' ist eine feste Konstante und wird nur
        mitgelesen, damit derselbe Text auch die ANWESENHEIT des Belegs
        nachweisen kann.
        """
        c = sqlite3.connect(self.db_path)
        try:
            rows = c.execute(
                "SELECT event_type, content, meta FROM audit_log").fetchall()
            return "\n".join("%s %s %s" % (r[0], r[1], r[2]) for r in rows)
        finally:
            c.close()

    def _add(self, subject_id=4711, alias="Panther", kind="forenname",
             basis="", note=None, actor=1):
        body = {"subject_id": subject_id, "alias": alias, "kind_code": kind,
                "basis": basis}
        if note is not None:
            body["note"] = note
        return self.app.dispatch_write(actor, "/api/alias/add", body)

    # AA01 -------------------------------------------------------------------
    def test_aa01_get_forbidden_without_view(self):
        r = self.app.dispatch(2, "/api/alias")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "crossref.view")

    # AA02 -------------------------------------------------------------------
    def test_aa02_post_forbidden_without_edit(self):
        for path, body in (
            ("/api/alias/add", {"subject_id": 1, "alias": "X",
                                "kind_code": "forenname"}),
            ("/api/alias/update", {"alias_id": 1, "basis": "y"}),
            ("/api/alias/retract", {"alias_id": 1, "reason": "z"}),
            ("/api/alias/reinstate", {"alias_id": 1}),
        ):
            r = self.app.dispatch_write(2, path, body)
            self.assertEqual(r.status, 403, path)
            self.assertEqual(self._json(r)["capability"], "crossref.edit", path)

    # AA03 -------------------------------------------------------------------
    def test_aa03_add_then_list(self):
        r = self._add(alias="Panther", basis="Signatur in Post 12")
        self.assertEqual(r.status, 200)
        body = self._json(r)
        self.assertTrue(body["ok"])
        self.assertGreater(body["audit_seq"], 0)

        lst = self._json(self.app.dispatch(1, "/api/alias"))
        self.assertEqual(len(lst["entries"]), 1)
        self.assertEqual(lst["entries"][0]["alias"], "Panther")
        self.assertEqual(lst["entries"][0]["alias_norm"], "panther")
        self.assertEqual(lst["counts"]["aktiv"], 1)
        self.assertEqual(lst["mode"], "all")
        # Die Arten-Liste kommt vom Server, damit die Oberflaeche keine Auswahl
        # anbieten kann, die die DDL-CHECK spaeter ablehnt.
        codes = [k["code"] for k in lst["kinds"]]
        self.assertIn("forenname", codes)
        self.assertIn("sonstiges", codes)

        # Filter auf ein Konto (echte parse_qs-Listenform!).
        eines = self._json(
            self.app.dispatch(1, "/api/alias", {"subject_id": ["4711"]}))
        self.assertEqual(eines["mode"], "subject")
        self.assertEqual(len(eines["entries"]), 1)
        leer = self._json(
            self.app.dispatch(1, "/api/alias", {"subject_id": ["9999"]}))
        self.assertEqual(leer["entries"], [])

    # AA04 -------------------------------------------------------------------
    def test_aa04_retract_and_include(self):
        aid = self._json(self._add())["alias_id"]
        r = self.app.dispatch_write(1, "/api/alias/retract", {
            "alias_id": aid, "reason": "Verwechslung"})
        self.assertEqual(r.status, 200)

        ohne = self._json(self.app.dispatch(1, "/api/alias"))
        self.assertEqual(ohne["entries"], [])
        mit = self._json(self.app.dispatch(
            1, "/api/alias", {"include_retracted": ["1"]}))
        self.assertEqual(len(mit["entries"]), 1)
        self.assertFalse(mit["entries"][0]["is_active"])
        self.assertEqual(mit["entries"][0]["retracted_reason"], "Verwechslung")
        self.assertEqual(mit["counts"]["widerrufen"], 1)

        # Zuruecknehmen macht ihn wieder sichtbar.
        r2 = self.app.dispatch_write(1, "/api/alias/reinstate",
                                     {"alias_id": aid})
        self.assertEqual(r2.status, 200)
        self.assertEqual(
            len(self._json(self.app.dispatch(1, "/api/alias"))["entries"]), 1)

    # AA05 -------------------------------------------------------------------
    def test_aa05_validation_is_400_not_500(self):
        aid = self._json(self._add(alias="Panther"))["alias_id"]

        # Duplikat (andere Schreibweise, gleiche Normform).
        dup = self._add(alias="PANTHER")
        self.assertEqual(dup.status, 400)
        self.assertIn("bereits aktiv erfasst", self._json(dup)["detail"])

        # Widerruf ohne Grund.
        no_reason = self.app.dispatch_write(1, "/api/alias/retract", {
            "alias_id": aid, "reason": "   "})
        self.assertEqual(no_reason.status, 400)

        # Unbekannte Art.
        bad_kind = self._add(subject_id=5, alias="Y", kind="quatsch")
        self.assertEqual(bad_kind.status, 400)

        # Fehlende/ungueltige Kennungen.
        self.assertEqual(self.app.dispatch_write(
            1, "/api/alias/add", {"alias": "Z", "kind_code": "handle"}).status,
            400)
        self.assertEqual(self.app.dispatch_write(
            1, "/api/alias/update", {"basis": "x"}).status, 400)
        self.assertEqual(self.app.dispatch_write(
            1, "/api/alias/retract", {"reason": "x"}).status, 400)

        # Unbekannter Eintrag ist ebenfalls fachlich, nicht technisch.
        self.assertEqual(self.app.dispatch_write(
            1, "/api/alias/update",
            {"alias_id": 99999, "basis": "x"}).status, 400)

    # AA06 -------------------------------------------------------------------
    def test_aa06_reverse_search(self):
        self._add(subject_id=1, alias="Panther")
        self._add(subject_id=2, alias="PantherKing", kind="handle")
        self._add(subject_id=3, alias="Luchs")

        res = self._json(self.app.dispatch(1, "/api/alias", {"q": ["PANTH"]}))
        self.assertEqual(res["mode"], "search")
        self.assertEqual(sorted(e["subject_id"] for e in res["entries"]),
                         [1, 2])
        # Leerer Begriff liefert bewusst NICHTS (kein stiller Gesamtabzug).
        leer = self._json(self.app.dispatch(1, "/api/alias", {"q": ["  "]}))
        self.assertEqual(leer["entries"], [])

    # AA07 -------------------------------------------------------------------
    def test_aa07_sensitivity_at_endpoint(self):
        aid = self._json(self._add(
            alias=_SECRET_ALIAS, basis=_SECRET_BASIS,
            note="Quelle: VP 7"))["alias_id"]
        self.app.dispatch_write(1, "/api/alias/retract", {
            "alias_id": aid, "reason": "Bestandsauskunft war fehlerhaft"})

        raw = self._all_audit_raw()
        for geheim in (_SECRET_ALIAS, _SECRET_BASIS, "Quelle: VP 7",
                       "Bestandsauskunft war fehlerhaft"):
            self.assertNotIn(geheim, raw,
                             "Sensibler Klartext %r steht im audit_log!"
                             % geheim)
        # Der Beleg selbst ist trotzdem da und pruefbar.
        self.assertIn("subject_alias_added", raw)
        self.assertIn("subject_alias_retracted", raw)


if __name__ == "__main__":
    unittest.main()
