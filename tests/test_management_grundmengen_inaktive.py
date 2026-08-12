# =============================================================================
# tests/test_management_grundmengen_inaktive.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ruhestand von Hand
# =============================================================================
# Testsuite fuer die GRUNDMENGEN-Sichten (Build 701, Ticket 95139d2a):
# /api/workload und /api/capacity fuehren eine Zeile JE PERSON. Ausgeschiedene
# fallen per Default heraus — BLEIBEN aber stehen, solange sie offene Faelle
# tragen (Entscheidung Alex, 12.08.2026).
#
# DIE AUSNAHME IST DER EIGENTLICHE GEGENSTAND DIESER SUITE. Ein Filter, der
# einfach alle Inaktiven entfernt, waere in zehn Minuten gebaut und haette
# offene Arbeit aus der Sicht getilgt, in der sie auffallen muss. Die Faelle
# GM02/GM05 sind genau darauf angesetzt.
#
# GM01 — Ausgangslage: alle drei Personen erscheinen, 'inaktive' meldet 0.
# GM02 — nach dem Ruhestand: die Person OHNE offene Faelle verschwindet, die
#        MIT offenen Faellen bleibt und wird als 'behalten_mit_arbeit' benannt.
# GM03 — '?inaktive=1' zeigt alle wieder und sagt das ('gezeigt': true).
# GM04 — die Ausblendung verfaelscht die Ueberlastwarnung nicht: dieselben
#        Zaehler wie mit eingeblendeten Inaktiven, und zu jeder gezeigten
#        Zeile gibt es genau eine Bewertung (sonst zeigten Tabelle und Banner
#        Verschiedenes).
# GM05 — /api/capacity: dieselbe Regel; der EINZELABRUF einer ausgeschiedenen
#        Person bleibt moeglich (die Ausblendung ist Uebersicht, keine Sperre).
#
# Version: v0.8.701 · Build: 701 · 2026-08-12
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
from management.person.person_repo import PersonRepo
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


class GrundmengenInaktiveTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        now = int(time.time())
        con.execute(_PERSON)
        # 1 Chefin (Rechte), 2 geht OHNE offene Faelle, 3 geht MIT einem
        # offenen Fall — das ist die Ausnahme, um die es geht.
        con.execute("INSERT INTO person VALUES (1,'h0chef','Chefin',1,1,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (2,'h0leer','Ohne Last',1,0,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (3,'h0last','Mit Last',1,0,0,?)",
                    (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        writer = CoordinatorWriter(con, AuditLog(con))
        rbac = RbacRepo(con, writer)
        for cap in ("workload.view", "capacity.edit"):
            rbac.grant("supervisor", cap, scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Person 3: ein OFFENER Fall. Person 2: ein ABGESCHLOSSENER — sie hat
        # gearbeitet, aber nichts Offenes mehr; genau das unterscheidet die
        # beiden Lagen.
        con.execute(
            "INSERT INTO cases (subject_id, username, status, priority, "
            "assigned_to, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (4711, "verd_a", "open", 3, 3, now, now))
        con.execute(
            "INSERT INTO cases (subject_id, username, status, priority, "
            "assigned_to, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (4712, "verd_b", "closed", 3, 2, now, now))
        con.close()

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.unlink(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    # ------------------------------------------------------------------ Helfer
    def _app(self):
        return ManagementApp(db_path=self._db)

    def _ruhestand(self, *person_ids):
        """Setzt Personen auf dem AUDITIERTEN Weg inaktiv (kein Direkt-SQL —
        der Test soll denselben Pfad benutzen wie der Betrieb)."""
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        try:
            repo = PersonRepo(con, CoordinatorWriter(con, AuditLog(con)))
            for pid in person_ids:
                repo.deactivate(id=pid, reason="ausgeschieden", actor_id=1)
        finally:
            con.close()

    def _workload(self, **q):
        query = {k: [str(v)] for k, v in q.items()}
        return json.loads(self._app().dispatch(1, "/api/workload", query).body)

    def _capacity(self, **q):
        query = {"start": ["2026-08-01"], "end": ["2026-08-31"]}
        query.update({k: [str(v)] for k, v in q.items()})
        return json.loads(self._app().dispatch(1, "/api/capacity", query).body)

    @staticmethod
    def _kennungen(data):
        return sorted(l["system_username"] for l in data["loads"]
                      if not l["is_backlog"])

    # GM01 -------------------------------------------------------------------
    def test_gm01_ausgangslage(self):
        d = self._workload()
        self.assertEqual(self._kennungen(d), ["h0chef", "h0last", "h0leer"])
        self.assertEqual(d["inaktive"]["ausgeblendet"], 0)
        self.assertEqual(d["inaktive"]["behalten_mit_arbeit"], [])
        self.assertFalse(d["inaktive"]["gezeigt"])
        self.assertIsNone(d["inaktive"]["hinweis"])
        # Alle gelten als aktiv — das Feld ist additiv und muss belegt sein.
        self.assertTrue(all(l["is_active"] for l in d["loads"]))

    # GM02 -------------------------------------------------------------------
    def test_gm02_ohne_last_verschwindet_mit_last_bleibt(self):
        self._ruhestand(2, 3)
        d = self._workload()

        # h0leer ist weg, h0last ist da — und das ist der ganze Punkt.
        self.assertEqual(self._kennungen(d), ["h0chef", "h0last"])
        self.assertEqual(d["inaktive"]["ausgeblendet"], 1)
        self.assertEqual(d["inaktive"]["ausgeblendete_kennungen"], ["h0leer"])
        self.assertEqual(d["inaktive"]["behalten_mit_arbeit"], ["h0last"])

        # Die stehengebliebene Zeile ist ALS ausgeschieden erkennbar. Ohne
        # dieses Feld waere sie von der einer aktiven Person nicht zu
        # unterscheiden — und hier steht Arbeit, die niemand mehr macht.
        last = [l for l in d["loads"]
                if l["system_username"] == "h0last"][0]
        self.assertFalse(last["is_active"])
        self.assertEqual(last["active_cases"], 1)
        chefin = [l for l in d["loads"]
                  if l["system_username"] == "h0chef"][0]
        self.assertTrue(chefin["is_active"])

        # Die Rueckstau-Zeile ueberlebt den Filter (sie ist keine Person).
        self.assertEqual(len([l for l in d["loads"] if l["is_backlog"]]), 1)

    # GM03 -------------------------------------------------------------------
    def test_gm03_umschalter_zeigt_alle(self):
        self._ruhestand(2, 3)
        d = self._workload(inaktive=1)
        self.assertEqual(self._kennungen(d), ["h0chef", "h0last", "h0leer"])
        self.assertEqual(d["inaktive"]["ausgeblendet"], 0)
        self.assertTrue(d["inaktive"]["gezeigt"])
        # Und der Umschalter ist eine Anzeige-, keine Datenfrage: der
        # Ruhestand steht weiterhin an der Zeile.
        leer = [l for l in d["loads"]
                if l["system_username"] == "h0leer"][0]
        self.assertFalse(leer["is_active"])

    # GM04 -------------------------------------------------------------------
    def test_gm04_warnung_bleibt_deckungsgleich(self):
        """
        Der Filter laeuft VOR der Ueberlastbewertung. Zwei Zusicherungen:
        (a) die Zaehler aendern sich nicht — ausgeblendet wird nur, wer keine
            offenen Faelle mehr hat, und wer keine hat, ist nicht ueberlastet;
        (b) zu jeder GEZEIGTEN Zeile gibt es genau eine Bewertung. Liefe der
            Filter erst danach, stuenden im Banner Personen, die in der
            Tabelle fehlen — ein widerspruechlicher Beleg.
        """
        self._ruhestand(2, 3)
        ohne = self._workload()
        mit = self._workload(inaktive=1)

        for schluessel in ("overloaded_count", "warned_count",
                           "backlog_size", "backlog_alarm"):
            self.assertEqual(ohne["overload"][schluessel],
                             mit["overload"][schluessel], schluessel)

        gezeigt = {l["investigator_id"] for l in ohne["loads"]
                   if not l["is_backlog"]}
        bewertet = {a["investigator_id"]
                    for a in ohne["overload_assessments"]}
        self.assertEqual(gezeigt, bewertet)

    # GM05 -------------------------------------------------------------------
    def test_gm05_capacity_gleiche_regel_einzelabruf_bleibt(self):
        vorher = self._capacity()
        self.assertEqual(
            sorted(c["system_username"] for c in vorher["capacities"]),
            ["h0chef", "h0last", "h0leer"])
        self.assertEqual(vorher["inaktive"]["ausgeblendet"], 0)

        self._ruhestand(2, 3)
        d = self._capacity()
        self.assertEqual(
            sorted(c["system_username"] for c in d["capacities"]),
            ["h0chef", "h0last"])
        self.assertEqual(d["inaktive"]["ausgeblendete_kennungen"], ["h0leer"])
        self.assertEqual(d["inaktive"]["behalten_mit_arbeit"], ["h0last"])

        self.assertEqual(
            sorted(c["system_username"]
                   for c in self._capacity(inaktive=1)["capacities"]),
            ["h0chef", "h0last", "h0leer"])

        # DER EINZELABRUF BLEIBT MOEGLICH: die Ausblendung ordnet die
        # Uebersicht, sie sperrt keinen Zugang. Wer eine ausgeschiedene Person
        # ausdruecklich nennt, bekommt ihre Zahlen (z. B. fuer eine
        # Nachbetrachtung); den Zugang regelt das Recht samt Umfang.
        r = self._app().dispatch(1, "/api/capacity", {
            "start": ["2026-08-01"], "end": ["2026-08-31"],
            "person_id": ["2"]})
        self.assertEqual(r.status, 200)
        self.assertEqual(json.loads(r.body)["person_id"], 2)


if __name__ == "__main__":                                # pragma: no cover
    unittest.main()
