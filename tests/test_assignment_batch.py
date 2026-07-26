# =============================================================================
# tests/test_assignment_batch.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Zuweisung (Build 534)
# =============================================================================
# Testsuite fuer die SAMMELZUWEISUNG: management/cases/cases_batch_repo.py und
# POST /api/case/assign_batch.
#
# AB01 — Stapel schreibt alle Faelle UND erzeugt EINEN BELEG JE FALL
#        (kein Sammelbeleg). Prioritaet und Zuweisung ergeben je einen Beleg.
# AB02 — Unveraenderte Faelle werden NICHT geschrieben, aber GEMELDET.
# AB03 — Beanstandungen (unbekannter Fall, doppelter Fall, Prioritaet ausserhalb,
#        Nicht-Ermittler, leerer Eintrag) -> 400 UND es wurde nichts geschrieben.
# AB04 — ALLES ODER NICHTS: bricht eine Einheit ab, bleibt KEINE stehen.
# AB05 — Rechte: ohne assignment.edit 403, mit Scope 'eigene' 403; leerer und
#        uebergrosser Stapel -> 400 (abgelehnt, NICHT gekuerzt).
# AB06 — person_id: null entzieht auch im Stapel.
# AB07 — Die Audit-Hash-Kette bleibt nach einem Stapel unversehrt.
# AB08 — Der Einzelschreibweg ist unveraendert (Regressionsanker fuer die
#        Aufteilung von assign()/set_priority() in *_unit + Ausfuehrung).
#
# Version: v0.8.534 · Build: 534 · 2026-07-26
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
from management.cases.cases_batch_repo import (
    BatchChange,
    CasesBatchError,
    CasesBatchRepo,
)
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter, WriteUnit
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


class AssignmentBatchTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        for pid, user, name, inv, sup, supp in (
                (1, "h0a2898", "Chefin", 1, 1, 0),
                (2, "h002", "Mueller", 1, 0, 0),
                (3, "h003", "Support", 0, 0, 1)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (pid, user, name, inv, sup, supp, int(time.time())))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con

        self.writer = CoordinatorWriter(con, AuditLog(con))
        self.rbac = RbacRepo(con, self.writer)
        self.cases = CasesRepo(con, self.writer)
        self.rbac.grant("supervisor", "assignment.edit", scope="alle",
                        actor_id=1)
        self.rbac.grant("investigator", "assignment.edit", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

        self._uids = (18, 19, 20)
        for uid in self._uids:
            self.cases.create_case(uid, "b%d" % uid, actor_id=1)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    # ---------------------------------------------------------------- Helfer
    def _fresh(self):
        return sqlite3.connect(self._db)

    def _case(self, subject_id):
        c = self._fresh()
        try:
            r = c.execute("SELECT assigned_to, priority FROM cases "
                          "WHERE subject_id=?", (subject_id,)).fetchone()
            return (r[0], r[1])
        finally:
            c.close()

    def _audit_count(self, event_type, target_id):
        c = self._fresh()
        try:
            return c.execute(
                "SELECT COUNT(*) FROM audit_log WHERE event_type=? "
                "AND target_type='case' AND target_id=?",
                (event_type, str(target_id))).fetchone()[0]
        finally:
            c.close()

    def _repo(self):
        return CasesBatchRepo(self.con, self.writer,
                              priority_min=1, priority_max=5)

    # AB01 -------------------------------------------------------------------
    def test_ab01_stapel_schreibt_mit_beleg_je_fall(self):
        app = ManagementApp(self._db)
        r = app.dispatch_write(1, "/api/case/assign_batch", {"changes": [
            {"subject_id": 18, "person_id": 2, "priority": 1},
            {"subject_id": 19, "person_id": 2, "priority": 1},
            {"subject_id": 20, "person_id": 2},
        ]})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))

        self.assertEqual(d["eingereicht"], 3)
        self.assertEqual(d["geschrieben"], 3)
        self.assertEqual(d["unveraendert"], 0)
        # 3 Zuweisungen + 2 Prioritaeten = 5 Belege. KEIN Sammelbeleg.
        self.assertEqual(d["belege"], 5)

        for uid in self._uids:
            self.assertEqual(self._case(uid)[0], 2)
            # Der forensische Kern: JEDER Fall hat seinen eigenen Beleg.
            self.assertEqual(self._audit_count("case_assigned", uid), 1)
        self.assertEqual(self._case(18)[1], 1)
        self.assertEqual(self._audit_count("case_priority_set", 18), 1)
        self.assertEqual(self._audit_count("case_priority_set", 20), 0)

        # Je Fall genau eine Ergebniszeile, mit seinen seq.
        self.assertEqual([e["subject_id"] for e in d["results"]],
                         [18, 19, 20])
        self.assertEqual(len(d["results"][0]["audit_seqs"]), 2)
        self.assertEqual(len(d["results"][2]["audit_seqs"]), 1)

    # AB02 -------------------------------------------------------------------
    def test_ab02_unveraendert_wird_gemeldet_nicht_geschrieben(self):
        app = ManagementApp(self._db)
        app.dispatch_write(1, "/api/case/assign_batch", {"changes": [
            {"subject_id": 18, "person_id": 2, "priority": 2}]})
        vorher = self._audit_count("case_assigned", 18)

        # Genau dasselbe noch einmal -> nichts zu tun.
        r = app.dispatch_write(1, "/api/case/assign_batch", {"changes": [
            {"subject_id": 18, "person_id": 2, "priority": 2}]})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["geschrieben"], 0)
        self.assertEqual(d["unveraendert"], 1)
        self.assertEqual(d["belege"], 0)
        # NICHT still uebersprungen: der Fall steht mit Grund in der Antwort.
        self.assertEqual(d["results"][0]["ergebnis"], "unveraendert")
        self.assertTrue(d["results"][0]["detail"])
        # Kein zusaetzlicher Beleg — Rauschen in der Beweiskette ist teuer.
        self.assertEqual(self._audit_count("case_assigned", 18), vorher)

    # AB03 -------------------------------------------------------------------
    def test_ab03_beanstandungen_schreiben_nichts(self):
        app = ManagementApp(self._db)

        faelle = [
            # unbekannter Fall
            [{"subject_id": 999, "person_id": 2}],
            # derselbe Fall zweimal im Stapel
            [{"subject_id": 18, "person_id": 2},
             {"subject_id": 18, "person_id": 1}],
            # Prioritaet ausserhalb 1..5
            [{"subject_id": 18, "priority": 9}],
            # Empfaenger ist kein Ermittler (Support)
            [{"subject_id": 18, "person_id": 3}],
            # Eintrag ohne jeden Aenderungswunsch
            [{"subject_id": 18}],
        ]
        for changes in faelle:
            r = app.dispatch_write(1, "/api/case/assign_batch",
                                   {"changes": changes})
            self.assertEqual(r.status, 400, changes)
            d = json.loads(r.body.decode("utf-8"))
            # Die Beanstandungen werden EINZELN benannt, nicht summarisch.
            self.assertTrue(d.get("zeilen"), d)
            # Und: es wurde nichts geschrieben.
            self.assertEqual(self._case(18), (None, 3))
            self.assertEqual(self._audit_count("case_assigned", 18), 0)

    # AB04 -------------------------------------------------------------------
    def test_ab04_alles_oder_nichts(self):
        """
        Die zentrale Zusicherung: bricht eine Einheit ab, bleibt KEINE stehen.

        Die Beanstandungspruefung greift hier ausdruecklich NICHT — geprueft
        wird der Rollback des SCHREIBENS. Dafuer wird eine Einheit
        untergeschoben, die beim Ausfuehren wirft (ein Zustand, den nur ein
        echter DB-Fehler erzeugen wuerde).
        """
        def _explodiert(con):
            raise sqlite3.OperationalError("Testfehler in der Mitte")

        einheiten = [
            self.cases.assign_unit(18, 2, actor_id=1),
            WriteUnit(do_write=_explodiert, event_type="case_assigned",
                      actor_id=1, target_type="case", target_id="19"),
            self.cases.assign_unit(20, 2, actor_id=1),
        ]
        with self.assertRaises(sqlite3.OperationalError):
            self.writer.audited_write_many(einheiten)

        # Fall 18 lief VOR dem Fehler durch — und ist trotzdem nicht da.
        self.assertEqual(self._case(18)[0], None)
        self.assertEqual(self._case(20)[0], None)
        self.assertEqual(self._audit_count("case_assigned", 18), 0)

    # AB05 -------------------------------------------------------------------
    def test_ab05_rechte_und_grenzen(self):
        app = ManagementApp(self._db)
        # Person 3: keine Rolle.
        self.assertEqual(app.dispatch_write(
            3, "/api/case/assign_batch",
            {"changes": [{"subject_id": 18, "person_id": 2}]}).status, 403)
        # Person 2: assignment.edit nur mit Scope 'eigene'.
        self.assertEqual(app.dispatch_write(
            2, "/api/case/assign_batch",
            {"changes": [{"subject_id": 18, "person_id": 2}]}).status, 403)
        # Leerer Stapel.
        self.assertEqual(app.dispatch_write(
            1, "/api/case/assign_batch", {"changes": []}).status, 400)
        # 'changes' fehlt/falscher Typ.
        self.assertEqual(app.dispatch_write(
            1, "/api/case/assign_batch", {}).status, 400)
        # Uebergross -> ABGELEHNT, nicht gekuerzt. Eine stille Kuerzung waere
        # genau die Auslassung, die Grundregel 1 verbietet.
        zuviel = [{"subject_id": 18, "person_id": 2}] * (app._BATCH_MAX + 1)
        r = app.dispatch_write(1, "/api/case/assign_batch",
                               {"changes": zuviel})
        self.assertEqual(r.status, 400)
        self.assertIn("too_many", r.body.decode("utf-8"))
        self.assertEqual(self._case(18)[0], None)

    # AB06 -------------------------------------------------------------------
    def test_ab06_entziehen_im_stapel(self):
        app = ManagementApp(self._db)
        app.dispatch_write(1, "/api/case/assign_batch", {"changes": [
            {"subject_id": 18, "person_id": 2},
            {"subject_id": 19, "person_id": 2}]})
        self.assertEqual(self._case(18)[0], 2)

        r = app.dispatch_write(1, "/api/case/assign_batch", {"changes": [
            {"subject_id": 18, "person_id": None},
            {"subject_id": 19, "person_id": None}]})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertEqual(d["geschrieben"], 2)
        self.assertIsNone(self._case(18)[0])
        self.assertIsNone(self._case(19)[0])
        self.assertIn("entzogen", d["results"][0]["detail"])

    # AB07 -------------------------------------------------------------------
    def test_ab07_hashkette_bleibt_unversehrt(self):
        app = ManagementApp(self._db)
        app.dispatch_write(1, "/api/case/assign_batch", {"changes": [
            {"subject_id": u, "person_id": 2, "priority": 2}
            for u in self._uids]})
        c = self._fresh()
        try:
            ergebnis = AuditLog(c).verify_chain()
        finally:
            c.close()
        self.assertTrue(ergebnis.ok, "Hash-Kette nach Stapel beschaedigt")

    # AB08 -------------------------------------------------------------------
    def test_ab08_einzelweg_unveraendert(self):
        """
        Regressionsanker fuer die Aufteilung in *_unit + Ausfuehrung
        (Build 534). Der Einzelweg muss sich verhalten wie vorher: EIN Beleg,
        dessen seq zurueckgegeben wird.
        """
        seq = self.cases.assign(18, 2, actor_id=1)
        self.assertIsInstance(seq, int)
        self.assertEqual(self._case(18)[0], 2)
        self.assertEqual(self._audit_count("case_assigned", 18), 1)

        seq2 = self.cases.set_priority(18, 1, actor_id=1)
        self.assertEqual(seq2, seq + 1)
        self.assertEqual(self._case(18)[1], 1)

        # Und der Zeitstrahl wird weiterhin gespiegelt (Build 313).
        c = self._fresh()
        try:
            n = c.execute("SELECT COUNT(*) FROM case_events WHERE "
                          "subject_id=18 AND event_kind='assigned'"
                          ).fetchone()[0]
        finally:
            c.close()
        self.assertEqual(n, 1)

    # AB09 -------------------------------------------------------------------
    def test_ab09_repo_direkt_meldet_alle_beanstandungen_auf_einmal(self):
        """
        Wer 80 Zeilen schickt, will alle Beanstandungen auf einmal sehen und
        nicht achtzig Mal nacheinander eine.
        """
        with self.assertRaises(CasesBatchError) as ctx:
            self._repo().apply([
                BatchChange(subject_id=999, assign=True, person_id=2),
                BatchChange(subject_id=18, priority=9),
                BatchChange(subject_id=19),
            ], actor_id=1)
        zeilen = ctx.exception.zeilen
        self.assertEqual(len(zeilen), 3, zeilen)
        self.assertTrue(any("999" in z for z in zeilen))
        self.assertTrue(any("Prioritaet 9" in z for z in zeilen))


if __name__ == "__main__":
    unittest.main()
