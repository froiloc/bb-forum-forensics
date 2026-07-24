# =============================================================================
# tests/test_management_escalation_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 515 (AP-2G / Idee 23): das Eskalations-Read-Model aus
# Build 453 wird ueber '/api/escalations' erreichbar. Bis Build 514 existierte
# es nur als Repo + CLI und war in keiner Cockpit-Sicht vorhanden (Befund aus
# der Uebergabe 440-453).
#
# Die Regel-Logik selbst ist in tests/test_management_escalation.py belegt.
# HIER wird ausschliesslich die ANBINDUNG geprueft: Recht, Form, Massstab und
# die ausdrueckliche Benennung dessen, was der Build NICHT kann.
#
# EA01 — ohne escalation.view -> 403 (default-deny; die neue Sicht oeffnet
#        sich nicht ueber ein bestehendes Recht)
# EA02 — mit escalation.view -> 200 und die Zaehler sind vorhanden
# EA03 — die ANGEWANDTEN SCHWELLEN fahren mit ('thresholds'); ohne sie waere
#        '30 Tage inaktiv' keine nachpruefbare Aussage
# EA04 — jede gemeldete Eskalation traegt Regelcode, Schwere und Klartext
# EA05 — ein ueberfaelliger roter Fall wird gemeldet (Regel fall_ueberfaellig)
# EA06 — ein unbearbeiteter offener Fall wird gemeldet (fall_unbearbeitet)
#        und NICHT zusaetzlich als ueberfaellig (keine Doppelmeldung)
# EA07 — die systemische Regel traegt subject_id=None und wird NICHT
#        weggefiltert (sie ist der eigentliche Zweck der Sicht)
# EA08 — echter Leerbefund: keine Eskalation -> items leer, Zaehler 0,
#        total_cases weiterhin belegt (Leerbefund != fehlende Erhebung)
# EA09 — 'acknowledgeable' ist ausdruecklich false: der Quittierungsweg fehlt
#        noch und wird BENANNT statt vom Frontend geraten
# EA10 — die Faehigkeit ist im Katalog UND in der Migrationskette (M026);
#        ein Katalogeintrag ohne Seed waere ein toter Grant
#
# Version: v0.8.515 · Build: 515 · 2026-07-24
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


class EscalationApiTests(unittest.TestCase):

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
             (2, "h002", "Beta", 1, 0, 0, self.NOW)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)
        self.repo.grant("supervisor", "escalation.view", scope="alle",
                        actor_id=1)
        self.repo.assign_role(1, "supervisor", actor_id=1)
        # person 2 bekommt ein ANDERES Recht — damit belegt EA01, dass die
        # Sicht sich nicht ueber ein bestehendes Recht mit oeffnet.
        self.repo.grant("investigator", "dashboard.view", scope="eigene",
                        actor_id=1)
        self.repo.assign_role(2, "investigator", actor_id=1)

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
        r = self.app.dispatch(person_id, "/api/escalations")
        self.assertEqual(r.status, 200)
        return self._json(r)

    def _age_case(self, subject_id, days):
        """
        Den Fall kuenstlich altern lassen.

        last_activity_at ist abgeleitet als max(cases.updated_at,
        letztes case_events.created_at) — BEIDE muessen zurueckdatiert werden,
        sonst haelt das juengere der beiden den Fall kuenstlich 'frisch'.
        Zurueckdatiert wird DIREKT, weil der fachliche Schreibweg (CasesRepo)
        bewusst keine Zeitreise erlaubt. Test-Vorrichtung, kein Produktivpfad.
        """
        ts = self.NOW - days * _DAY
        self.con.execute(
            "UPDATE cases SET created_at = ?, updated_at = ? "
            "WHERE subject_id = ?", (ts, ts, subject_id))
        self.con.execute(
            "UPDATE case_events SET created_at = ? WHERE subject_id = ?",
            (ts, subject_id))
        self._checkpoint()

    def _items_of(self, data, rule_code):
        return [i for i in data["items"] if i["rule_code"] == rule_code]

    # -------------------------------------------------------------- Tests
    # EA01 — default-deny.
    def test_ea01_ohne_recht_403(self):
        r = self.app.dispatch(2, "/api/escalations")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "escalation.view")

    # EA02 — Grundform.
    def test_ea02_grundform(self):
        d = self._get(1)
        for key in ("generated_at", "total_cases", "count_hoch", "count_mittel",
                    "count_niedrig", "items", "thresholds", "acknowledgeable"):
            self.assertIn(key, d, "Schluessel '%s' fehlt" % key)
        self.assertIsInstance(d["items"], list)

    # EA03 — der Massstab faehrt mit.
    def test_ea03_schwellen_fahren_mit(self):
        t = self._get(1)["thresholds"]
        for key in ("red_overdue_days", "stale_open_days", "backlog_high"):
            self.assertIn(key, t)
            self.assertIsInstance(t[key], int)
            self.assertGreater(t[key], 0)

    # EA04 — jede Meldung ist begruendet.
    def test_ea04_jede_meldung_begruendet(self):
        grenze = self._get(1)["thresholds"]["red_overdue_days"]
        self.cases.create_case(7001, "alt_rot", actor_id=1)
        self.cases.assign(7001, 2, actor_id=1)
        self._age_case(7001, grenze + 5)
        d = self._get(1)
        self.assertTrue(d["items"], "es wurde eine Eskalation erwartet")
        for i in d["items"]:
            for key in ("rule_code", "label", "severity", "subject_id",
                        "message", "days_inactive"):
                self.assertIn(key, i)
            self.assertIn(i["severity"], ("hoch", "mittel", "niedrig"))
            self.assertTrue(i["message"].strip(),
                            "eine Meldung ohne Klartext waere kein Beleg")

    # EA05 — Regel 1.
    def test_ea05_ueberfaelliger_roter_fall(self):
        grenze = self._get(1)["thresholds"]["red_overdue_days"]
        self.cases.create_case(7002, "alt_rot", actor_id=1)
        self.cases.assign(7002, 2, actor_id=1)
        self._age_case(7002, grenze + 3)
        d = self._get(1)
        treffer = self._items_of(d, "fall_ueberfaellig")
        self.assertEqual(len(treffer), 1)
        self.assertEqual(treffer[0]["subject_id"], 7002)
        self.assertEqual(treffer[0]["severity"], "hoch")
        self.assertGreaterEqual(treffer[0]["days_inactive"], grenze)
        self.assertGreaterEqual(d["count_hoch"], 1)

    # EA06 — Regel 2, ohne Doppelmeldung.
    def test_ea06_unbearbeitet_ohne_doppelmeldung(self):
        t = self._get(1)["thresholds"]
        # Alter zwischen stale_open_days und red_overdue_days -> nur Regel 2.
        alter = t["stale_open_days"] + 1
        self.assertLess(alter, t["red_overdue_days"],
                        "Testvoraussetzung: die Schwellen muessen sich "
                        "unterscheiden, sonst ist der Fall nicht trennscharf")
        self.cases.create_case(7003, "liegengeblieben", actor_id=1)
        self.cases.assign(7003, 2, actor_id=1)
        self._age_case(7003, alter)
        d = self._get(1)
        self.assertEqual(len(self._items_of(d, "fall_unbearbeitet")), 1)
        self.assertEqual(
            [i for i in self._items_of(d, "fall_ueberfaellig")
             if i["subject_id"] == 7003], [])
        # Und derselbe Fall taucht insgesamt nur EINMAL auf.
        self.assertEqual(
            len([i for i in d["items"] if i["subject_id"] == 7003]), 1)

    # EA07 — die systemische Regel ueberlebt die Anbindung.
    def test_ea07_systemische_regel_ohne_fallbezug(self):
        grenze = self._get(1)["thresholds"]["backlog_high"]
        for n in range(grenze):
            self.cases.create_case(8000 + n, "offen_%d" % n, actor_id=1)
        self._checkpoint()
        d = self._get(1)
        treffer = self._items_of(d, "rueckstau_hoch")
        self.assertEqual(len(treffer), 1)
        self.assertIsNone(treffer[0]["subject_id"],
                          "die systemische Regel gehoert zu KEINEM Fall")
        self.assertEqual(treffer[0]["severity"], "hoch")

    # EA08 — echter Leerbefund, sauber unterscheidbar von 'nicht erhoben'.
    def test_ea08_echter_leerbefund(self):
        self.cases.create_case(7004, "frisch", actor_id=1)
        self.cases.assign(7004, 2, actor_id=1)
        self._checkpoint()
        d = self._get(1)
        self.assertEqual(d["items"], [])
        self.assertEqual(d["count_hoch"], 0)
        self.assertEqual(d["count_mittel"], 0)
        self.assertEqual(d["count_niedrig"], 0)
        # Die Erhebung HAT stattgefunden — belegt durch die Fallzahl.
        self.assertEqual(d["total_cases"], 1)

    # EA09 — die fehlende Faehigkeit wird BENANNT, nicht verschwiegen.
    def test_ea09_quittierung_ausdruecklich_nicht_moeglich(self):
        self.assertIs(self._get(1)["acknowledgeable"], False)
        # Und es gibt tatsaechlich keinen Schreibweg dafuer.
        r = self.app.dispatch_write(1, "/api/escalations/ack",
                                    {"rule_code": "fall_ueberfaellig",
                                     "subject_id": 1})
        self.assertEqual(r.status, 404)

    # EA10 — Katalog UND Seed. Ein Katalogeintrag ohne Migration waere ein
    #        toter Grant: der Resolver faende die Faehigkeit nie in der DB.
    def test_ea10_katalog_und_seed(self):
        self.assertIn("escalation.view", catalog.CAPABILITY_CODES)
        row = self.con.execute(
            "SELECT code, label, description FROM rbac_capability "
            "WHERE code = 'escalation.view'").fetchone()
        self.assertIsNotNone(row, "escalation.view ist nicht geseedet (M026)")
        # Seed und Katalog muessen zeichengleich sein (Prinzip aus R02).
        cat = {c.code: (c.label, c.description) for c in catalog.CAPABILITIES}
        self.assertEqual((row["label"], row["description"]),
                         cat["escalation.view"])


if __name__ == "__main__":
    unittest.main()
