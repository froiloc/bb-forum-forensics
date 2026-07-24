# =============================================================================
# tests/test_management_workload_overload.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Testsuite fuer Build 513 (AP-2F / Idee 21): die AKTIVE Ueberlastwarnung
# (Read-Model aus Build 451) wird ueber '/api/workload' SICHTBAR. Bis Build 512
# war sie ausschliesslich ueber die CLI (overload_admin) erreichbar und in
# keiner Cockpit-Sicht vorhanden — Befund aus der Uebergabe 440-453.
#
# Die Tests belegen nicht die Bewertungslogik selbst (die ist in
# tests/test_management_overload.py bereits belegt), sondern AUSSCHLIESSLICH
# die Anbindung: Form, Rechte, Scope-Kapselung und Deckungsgleichheit von
# Warnung und angezeigter Last.
#
# UB01 — /api/workload traegt einen 'overload'-Block MIT den angewandten
#        Schwellen (nachrechenbar; Grundregel: kein Wert ohne Beleg)
# UB02 — die Einzelbewertungen stehen FLACH in 'overload_assessments'; der
#        'overload'-Block enthaelt sie NICHT (keine zwei Wahrheitsquellen)
# UB03 — die Rueckstau-Zeile erzeugt KEINE Personen-Bewertung, sondern
#        backlog_size/backlog_alarm (systemisch, nicht persoenlich)
# UB04 — Schwelle ueberschritten -> level 'overload' MIT benanntem Ausloeser
# UB05 — Schwelle exakt erreicht -> level 'warn' (nicht 'overload')
# UB06 — scope 'eigene': nur die EIGENE Bewertung; scope_limited=true; der
#        Rueckstau bleibt gekapselt (backlog_size 0 — nicht erhoben!)
# UB07 — scope 'alle': scope_limited=false
# UB08 — SELBE MESSUNG: jede bewertete Person kommt in 'loads' vor und die
#        Zahlen sind zeichengleich (Warnung und Balken koennen nicht divergieren)
# UB09 — ohne workload.view bleibt es bei 403 (die Warnung oeffnet kein Tor)
# UB10 — der Akten-Export der Sicht traegt die Ueberlastwarnung MIT
#        (Grundregel 1: kein Beleg wird ausgelassen)
#
# Version: v0.8.513 · Build: 513 · 2026-07-24
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
# Alt-Tabelle: die Migrationskette erwartet sie als Ausgangszustand
# (identisch zu tests/test_management_server.py).
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


class WorkloadOverloadApiTests(unittest.TestCase):

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
             (2, "h002", "Beta", 1, 0, 0, now),
             (3, "h003", "Gamma", 1, 0, 0, now)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)
        self.repo.grant("supervisor", "workload.view", scope="alle", actor_id=1)
        self.repo.assign_role(1, "supervisor", actor_id=1)
        self.repo.grant("investigator", "workload.view", scope="eigene",
                        actor_id=1)
        self.repo.assign_role(2, "investigator", actor_id=1)
        # person 3 bleibt OHNE Rolle -> Default-Deny (UB09).

        self.cases = CasesRepo(self.con, self.writer)
        # Ein unzugewiesener Fall -> die Rueckstau-Zeile ist nicht leer.
        self.cases.create_case(9001, "backlog_eins", actor_id=1)

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
        """WAL in die Hauptdatei falten — die App liest read-only."""
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _json(self, resp):
        return json.loads(resp.body.decode("utf-8"))

    def _get(self, person_id=1):
        r = self.app.dispatch(person_id, "/api/workload")
        self.assertEqual(r.status, 200)
        return self._json(r)

    def _assign_open_cases(self, person_id, count, base_subject):
        """
        'count' offene, der Person zugewiesene Faelle anlegen.

        BEWUSST 'open' und frisch: so zaehlen sie als active_cases, ohne durch
        Liegezeit zusaetzlich rot zu werden — die Ueberschreitung ist damit
        EINDEUTIG der Fallzahl zuzuordnen und nicht der Ampel.
        """
        for i in range(count):
            sid = base_subject + i
            self.cases.create_case(sid, "u%d" % sid, actor_id=1)
            self.cases.assign(sid, person_id, actor_id=1)
        self._checkpoint()

    def _row_for(self, data, person_id):
        rows = [a for a in data["overload_assessments"]
                if a["investigator_id"] == person_id]
        self.assertEqual(len(rows), 1,
                         "genau eine Bewertung je Ermittler:in erwartet")
        return rows[0]

    # -------------------------------------------------------------- Tests
    # UB01 — der Block existiert und traegt die ANGEWANDTEN Schwellen mit.
    #        Ohne sie waere eine Einstufung eine unbelegte Behauptung.
    def test_ub01_overload_block_traegt_schwellen(self):
        d = self._get(1)
        self.assertIn("overload", d)
        ov = d["overload"]
        for key in ("generated_at", "max_active_cases", "max_red_cases",
                    "backlog_alert", "overloaded_count", "warned_count",
                    "backlog_size", "backlog_alarm", "scope_limited"):
            self.assertIn(key, ov, "Schluessel '%s' fehlt" % key)
        self.assertIsInstance(ov["max_active_cases"], int)
        self.assertGreater(ov["max_active_cases"], 0)

    # UB02 — Einzelbewertungen FLACH daneben, NICHT im Block verschachtelt.
    def test_ub02_assessments_flach_und_einmalig(self):
        d = self._get(1)
        self.assertIn("overload_assessments", d)
        self.assertIsInstance(d["overload_assessments"], list)
        self.assertNotIn("assessments", d["overload"],
                         "Doppelablage: 'assessments' darf NICHT zusaetzlich "
                         "im overload-Block stehen")
        # Jede Zeile ist flach genug fuer eine Tabellenspalte je Schluessel.
        for row in d["overload_assessments"]:
            for key in ("investigator_id", "name", "active_cases",
                        "red_cases", "total_cases", "level", "reasons"):
                self.assertIn(key, row)
            self.assertIn(row["level"], ("ok", "warn", "overload"))

    # UB03 — Rueckstau ist systemisch, nicht persoenlich.
    def test_ub03_rueckstau_ist_keine_person(self):
        d = self._get(1)
        ids = [a["investigator_id"] for a in d["overload_assessments"]]
        self.assertNotIn(0, ids, "die Rueckstau-Zeile (id 0) darf nicht als "
                                 "Person bewertet werden")
        # Der eine unzugewiesene Fall aus setUp muss gezaehlt sein.
        self.assertGreaterEqual(d["overload"]["backlog_size"], 1)

    # UB04 — Schwelle UEBERSCHRITTEN -> 'overload' mit benanntem Ausloeser.
    #        Die Fallzahl wird aus der ANTWORT abgeleitet (nicht hart kodiert),
    #        damit der Test auch bei geaenderter config.yaml gueltig bleibt.
    def test_ub04_ueberschritten_ist_overload(self):
        grenze = self._get(1)["overload"]["max_active_cases"]
        self._assign_open_cases(2, grenze + 1, 2000)
        row = self._row_for(self._get(1), 2)
        self.assertEqual(row["active_cases"], grenze + 1)
        self.assertEqual(row["level"], "overload")
        self.assertTrue(any(">" in r for r in row["reasons"]),
                        "der Ausloeser muss benannt sein: %r" % (row["reasons"],))
        self.assertGreaterEqual(self._get(1)["overload"]["overloaded_count"], 1)

    # UB05 — Schwelle EXAKT erreicht -> 'warn'. Die Unterscheidung ist der
    #        eigentliche Nutzen: 'einer mehr kippt' ist noch handlungsfaehig.
    def test_ub05_erreicht_ist_warn(self):
        grenze = self._get(1)["overload"]["max_active_cases"]
        self._assign_open_cases(2, grenze, 3000)
        row = self._row_for(self._get(1), 2)
        self.assertEqual(row["active_cases"], grenze)
        self.assertEqual(row["level"], "warn")
        self.assertGreaterEqual(self._get(1)["overload"]["warned_count"], 1)

    # UB06 — Zweckbindung: 'eigene' sieht nur sich selbst. Der Rueckstau ist
    #        dann NICHT ERHOBEN (0) — die Sicht muss das benennen koennen,
    #        deshalb scope_limited.
    def test_ub06_scope_eigene_gekapselt(self):
        self._assign_open_cases(1, 3, 4000)   # fremde Last erzeugen
        d = self._get(2)
        self.assertEqual(d["scope"], "eigene")
        self.assertTrue(d["overload"]["scope_limited"])
        ids = [a["investigator_id"] for a in d["overload_assessments"]]
        self.assertEqual(ids, [2])
        self.assertEqual(d["overload"]["backlog_size"], 0)
        self.assertFalse(d["overload"]["backlog_alarm"])

    # UB07 — volle Sicht meldet sich als vollstaendig.
    def test_ub07_scope_alle_nicht_begrenzt(self):
        d = self._get(1)
        self.assertEqual(d["scope"], "alle")
        self.assertFalse(d["overload"]["scope_limited"])

    # UB08 — SELBE MESSUNG. Der Kern der Entwurfsentscheidung: Warnung und
    #        Balken stammen aus EINER Abfrage, also muss jede Bewertung eine
    #        zeichengleiche Last-Zeile haben.
    def test_ub08_selbe_messung_wie_die_balken(self):
        self._assign_open_cases(2, 4, 5000)
        d = self._get(1)
        by_id = {l["investigator_id"]: l for l in d["loads"]
                 if not l["is_backlog"]}
        self.assertTrue(d["overload_assessments"])
        for a in d["overload_assessments"]:
            self.assertIn(a["investigator_id"], by_id,
                          "bewertet, aber nicht in 'loads' — die Sicht koennte "
                          "die Warnung niemandem zuordnen")
            load = by_id[a["investigator_id"]]
            self.assertEqual(a["active_cases"], load["active_cases"])
            self.assertEqual(a["red_cases"], load["ampel_rot"])
            self.assertEqual(a["total_cases"], load["total_cases"])
        # Und umgekehrt: keine Last-Zeile ohne Bewertung (Grundregel 1).
        bewertet = {a["investigator_id"] for a in d["overload_assessments"]}
        self.assertEqual(set(by_id.keys()), bewertet)

    # UB09 — die neue Angabe oeffnet kein Tor: ohne Recht weiter 403.
    def test_ub09_ohne_recht_weiter_403(self):
        r = self.app.dispatch(3, "/api/workload")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "workload.view")

    # UB10 — Akten-Export: die Warnung gehoert MIT in die Akte. Belegt wird
    #        die Katalog-Zusage UND das gerenderte Dokument.
    def test_ub10_aktenexport_traegt_die_warnung(self):
        spec = spec_for("workload")
        keys = [s.key for s in spec.sections]
        self.assertIn("overload", keys)
        self.assertIn("overload_assessments", keys)
        # Der Alarm steht VOR der Last — so liest man ihn zuerst.
        self.assertLess(keys.index("overload"), keys.index("loads"))

        self._assign_open_cases(2, 2, 6000)
        r = self.app.dispatch(1, "/api/view/export", {"view": ["workload"]})
        self.assertEqual(r.status, 200)
        html = r.body.decode("utf-8")
        self.assertIn("Überlastwarnung", html)
        self.assertIn("max_active_cases", html)


if __name__ == "__main__":
    unittest.main()
