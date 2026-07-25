# =============================================================================
# tests/test_management_retention_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 521 (AP-2G / Idee 29): die Aufbewahrungsfristen-
# Uebersicht aus Build 456 wird ueber '/api/retention' erreichbar. Bis Build
# 520 existierte sie nur als Repo + CLI (Befund aus der Uebergabe 440-453).
#
# Der wichtigste Test dieser Suite ist RT10: es darf im GESAMTEN Werkzeug
# keinen Weg geben, aus dieser Sicht eine Loeschung auszuloesen.
#
# RT01 — ohne retention.view -> 403 (default-deny)
# RT02 — 'ops.view' allein genuegt NICHT: die Sicht zeigt Beschuldigten-
#        Kontonamen, wer die Anlage betreut braucht die nicht
# RT03 — Grundform: alle vier Kennzahlen und die angewandte Frist
# RT04 — ein ueberfaelliger abgeschlossener Fall wird Kandidat
# RT05 — ein Fall INNERHALB der Frist wird NICHT Kandidat
# RT06 — ein offener Fall ist kein Kandidat (die Frist laeuft erst ab
#        Abschluss) und wird auch nicht als ungeprueft gezaehlt
# RT07 — ohne Bezugszeitpunkt: weder Kandidat noch unverdaechtig, sondern
#        UNGEPRUEFT (without_reference). BEFUND: aus der Datenbank heraus ist
#        dieser Zustand derzeit NICHT erreichbar (cases.updated_at ist seit
#        M002 NOT NULL) — der Test belegt deshalb BEIDES: den Vertrag der
#        reinen Funktion und die Tatsache, dass der DB-Pfad immer einen Bezug
#        liefert
# RT08 — das Bezugsfeld faehrt mit (approved_at vs. updated_at aendert das
#        Ergebnis und ist damit nachpruefbare Tatsache)
# RT09 — echter Leerbefund bei belegter Fallzahl
# RT10 — DIE ZUSICHERUNG: 'deletes_nothing' ist true UND es gibt keinen
#        Schreibpfad, der auf 'retention' lautet
# RT11 — Katalog UND Seed (M030) zeichengleich
# RT12 — Akten-Export traegt den Loeschvorbehalt UND die Kennzahlen
#
# Version: v0.8.521 · Build: 521 · 2026-07-24
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

_DAY = 86400

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


class RetentionApiTests(unittest.TestCase):

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
             (3, "h003", "Gamma", 1, 0, 0, self.NOW)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)
        self.repo.grant("supervisor", "retention.view", scope="alle",
                        actor_id=1)
        self.repo.assign_role(1, "supervisor", actor_id=1)
        # person 2 bekommt AUSDRUECKLICH ops.view — und darf trotzdem nicht
        # hinein (RT02). Das ist die Probe auf die Zweckbindung.
        self.repo.grant("investigator", "ops.view", scope="alle", actor_id=1)
        self.repo.assign_role(2, "investigator", actor_id=1)
        # person 3: gar nichts (RT01).

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
        r = self.app.dispatch(person_id, "/api/retention")
        self.assertEqual(r.status, 200)
        return self._json(r)

    def _frist(self):
        return self._get(1)["retention_days"]

    def _closed_case(self, subject_id, username, age_days, status="closed"):
        """
        Einen abgeschlossenen Fall mit definiertem Bezugszeitpunkt anlegen.

        Zurueckdatiert wird DIREKT: der fachliche Schreibweg (CasesRepo)
        erlaubt bewusst keine Zeitreise. Test-Vorrichtung, kein Produktivpfad.
        """
        self.cases.create_case(subject_id, username, actor_id=1)
        self.cases.set_status(subject_id, status, actor_id=1)
        ts = self.NOW - age_days * _DAY
        if status == "approved":
            self.con.execute(
                "UPDATE cases SET approved_at = ?, updated_at = ? "
                "WHERE subject_id = ?", (ts, ts, subject_id))
        else:
            self.con.execute(
                "UPDATE cases SET updated_at = ? WHERE subject_id = ?",
                (ts, subject_id))
        self._checkpoint()

    def _cand(self, data, subject_id):
        return [c for c in data["candidates"] if c["subject_id"] == subject_id]

    # -------------------------------------------------------------- Tests
    # RT01 — default-deny.
    def test_rt01_ohne_recht_403(self):
        r = self.app.dispatch(3, "/api/retention")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "retention.view")

    # RT02 — ops.view genuegt NICHT. Zweckbindung: wer die Anlage betreut,
    #        braucht keine Beschuldigten-Kontonamen.
    def test_rt02_ops_view_genuegt_nicht(self):
        r = self.app.dispatch(2, "/api/retention")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "retention.view")

    # RT03 — Grundform.
    def test_rt03_grundform(self):
        d = self._get(1)
        for key in ("generated_at", "retention_days", "total_cases",
                    "closed_cases", "without_reference", "candidate_count",
                    "candidates", "deletes_nothing"):
            self.assertIn(key, d, "Schluessel '%s' fehlt" % key)
        self.assertIsInstance(d["retention_days"], int)
        self.assertGreater(d["retention_days"], 0)

    # RT04 — ueberfaelliger Fall wird Kandidat.
    def test_rt04_ueberfaellig(self):
        frist = self._frist()
        self._closed_case(4001, "alt", frist + 12)
        d = self._get(1)
        c = self._cand(d, 4001)
        self.assertEqual(len(c), 1)
        self.assertGreaterEqual(c[0]["days_retained"], frist)
        self.assertGreaterEqual(c[0]["over_by_days"], 1)
        self.assertEqual(d["candidate_count"], 1)

    # RT05 — innerhalb der Frist: kein Kandidat, aber gezaehlt.
    def test_rt05_innerhalb_der_frist(self):
        frist = self._frist()
        self._closed_case(4002, "jung", max(0, frist - 10))
        d = self._get(1)
        self.assertEqual(self._cand(d, 4002), [])
        self.assertEqual(d["candidate_count"], 0)
        self.assertEqual(d["closed_cases"], 1)
        self.assertEqual(d["without_reference"], 0)

    # RT06 — ein OFFENER Fall ist kein Kandidat und auch nicht 'ungeprueft':
    #        seine Frist hat noch gar nicht begonnen.
    def test_rt06_offener_fall(self):
        self.cases.create_case(4003, "offen", actor_id=1)
        self._checkpoint()
        d = self._get(1)
        self.assertEqual(self._cand(d, 4003), [])
        self.assertEqual(d["closed_cases"], 0)
        self.assertEqual(d["without_reference"], 0)
        self.assertEqual(d["total_cases"], 1)

    # RT07 — ohne Bezugszeitpunkt: UNGEPRUEFT. Weder Kandidat noch
    #        unverdaechtig — der stille Verzicht waere hier der
    #        gefaehrlichste (eine kurze Liste saehe vollstaendig aus).
    #
    #        BEFUND WAEHREND DER UMSETZUNG VON BUILD 521, hier festgehalten
    #        statt ihn zu verschweigen: dieser Zaehler ist AUS DER DATENBANK
    #        HERAUS DERZEIT NICHT ERREICHBAR. 'cases.updated_at' ist seit
    #        M002 NOT NULL, und ein 'approved'-Fall ohne approved_at faellt
    #        auf updated_at zurueck. Es gibt damit keinen Fall, fuer den sich
    #        kein Bezugszeitpunkt ermitteln liesse — 'without_reference' ist
    #        in der Praxis IMMER 0.
    #
    #        Das ist KEIN Fehler und der Zaehler ist NICHT ueberfluessig: er
    #        sichert den Vertrag der REINEN Funktion ab (die auch von der CLI
    #        und von kuenftigen Quellen gespeist werden kann) und faengt eine
    #        spaetere Schemaaenderung auf. Der Test belegt deshalb BEIDES:
    #        die Vertragstreue der reinen Funktion UND die Tatsache, dass der
    #        Datenbankpfad heute immer einen Bezug liefert. Waere nur das
    #        eine geprueft, entstuende ein falscher Eindruck von der
    #        Aussagekraft der Zahl in der Sicht.
    def test_rt07_ohne_bezugszeitpunkt(self):
        from management.ops.retention import (
            evaluate_retention, RetentionThresholds,
        )
        # (a) Vertrag der reinen Funktion: ohne Bezug -> UNGEPRUEFT, NICHT
        #     Kandidat.
        report = evaluate_retention(
            [{"subject_id": 4004, "username": "ohne_bezug",
              "status": "closed", "approved_at": None, "updated_at": None}],
            RetentionThresholds(retention_days=730), self.NOW)
        self.assertEqual(report.candidate_count, 0)
        self.assertEqual(report.without_reference, 1,
                         "ein Fall ohne Bezugszeitpunkt muss GEZAEHLT werden")
        self.assertEqual(report.closed_cases, 1)

        # (b) Datenbankpfad: 'updated_at' ist NOT NULL (M002) — der Bezug
        #     laesst sich einem BESTEHENDEN Fall gar nicht nehmen. Der
        #     Zaehler ist deshalb ueber die DB heute immer 0.
        self.cases.create_case(4004, "ohne_bezug", actor_id=1)
        self.cases.set_status(4004, "closed", actor_id=1)
        self.con.execute(
            "UPDATE cases SET approved_at = NULL WHERE subject_id = 4004")
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "UPDATE cases SET updated_at = NULL WHERE subject_id = 4004")
        self._checkpoint()
        d = self._get(1)
        self.assertEqual(d["without_reference"], 0)
        self.assertEqual(d["closed_cases"], 1)

    # RT08 — das Bezugsfeld faehrt mit.
    def test_rt08_bezugsfeld(self):
        frist = self._frist()
        self._closed_case(4005, "freigegeben", frist + 5, status="approved")
        self._closed_case(4006, "geschlossen", frist + 5, status="closed")
        d = self._get(1)
        felder = {c["subject_id"]: c["reference_field"]
                  for c in d["candidates"]}
        self.assertEqual(felder.get(4005), "approved_at")
        self.assertEqual(felder.get(4006), "updated_at")

    # RT09 — echter Leerbefund.
    def test_rt09_leerbefund(self):
        self._closed_case(4007, "jung", 1)
        d = self._get(1)
        self.assertEqual(d["candidates"], [])
        self.assertEqual(d["candidate_count"], 0)
        # Die Erhebung HAT stattgefunden.
        self.assertEqual(d["closed_cases"], 1)
        self.assertEqual(d["total_cases"], 1)

    # RT10 — DIE ZUSICHERUNG. Sie faehrt mit UND es gibt keinen Schreibpfad.
    def test_rt10_loescht_nichts(self):
        frist = self._frist()
        self._closed_case(4008, "alt", frist + 30)
        d = self._get(1)
        self.assertIs(d["deletes_nothing"], True)
        self.assertEqual(d["candidate_count"], 1)

        # Es gibt KEINEN Schreibpfad zu dieser Sicht — weder einen zum
        # Loeschen noch irgendeinen anderen. 404 = die Route existiert nicht.
        for pfad in ("/api/retention", "/api/retention/delete",
                     "/api/retention/purge"):
            r = self.app.dispatch_write(1, pfad, {"subject_id": 4008})
            self.assertEqual(r.status, 404,
                             "es darf KEINEN Schreibpfad '%s' geben" % pfad)

        # Und der Fall steht nach dem Versuch unveraendert in der Fallakte.
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM cases WHERE subject_id = 4008").fetchone())

    # RT11 — Katalog UND Seed.
    def test_rt11_katalog_und_seed(self):
        self.assertIn("retention.view", catalog.CAPABILITY_CODES)
        row = self.con.execute(
            "SELECT code, label, description FROM rbac_capability "
            "WHERE code = 'retention.view'").fetchone()
        self.assertIsNotNone(row, "retention.view ist nicht geseedet (M030)")
        cat = {c.code: (c.label, c.description) for c in catalog.CAPABILITIES}
        self.assertEqual((row["label"], row["description"]),
                         cat["retention.view"])

    # RT12 — Akten-Export.
    def test_rt12_aktenexport(self):
        spec = spec_for("retention")
        self.assertIsNotNone(spec, "Sicht 'retention' fehlt im Export-Katalog")
        self.assertIn("candidates", [s.key for s in spec.sections])
        # Der Loeschvorbehalt steht schon in der Spec.
        self.assertIn("löscht nichts", spec.note)

        frist = self._frist()
        self._closed_case(4009, "alt_export", frist + 20)
        r = self.app.dispatch(1, "/api/view/export", {"view": ["retention"]})
        self.assertEqual(r.status, 200)
        html = r.body.decode("utf-8")
        self.assertIn("Fälle über der Frist", html)
        self.assertIn("4009", html)
        # Der Vorbehalt UND die wichtigste Kennzahl stehen im Dokument.
        self.assertIn("löscht nichts", html)
        # Der Auto-Modus des Renderers macht aus dem Schluessel eine
        # Ueberschrift ohne Unterstriche ("without reference").
        self.assertIn("without reference", html)
        self.assertIn("deletes nothing", html)

        # Der Export erbt die Rechtepruefung der Sicht.
        r2 = self.app.dispatch(2, "/api/view/export", {"view": ["retention"]})
        self.assertEqual(r2.status, 403)


if __name__ == "__main__":
    unittest.main()
