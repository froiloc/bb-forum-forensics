# =============================================================================
# tests/test_ad_sync_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Abgleich (Build 501)
# =============================================================================
# Testsuite fuer die CLI (management/ad_sync/ad_sync_admin.py) — voller
# CLI-Pfad mit gemocktem Provider und geskripteter Eingabe (main(argv,
# provider=..., input_fn=...)); KEIN Live-LDAP, kein Terminal.
#
# CA01 — preview --json: Plan mit Zaehlern auf stdout, Exit 0, KEIN Beleg
#        (Vorschau ist rein lesend).
# CA02 — apply: Neuaufnahme automatisch; Kandidat 1 mit "Entfernen"
#        deaktiviert, Kandidat 2 mit anderer Eingabe protokolliert
#        abgebrochen; Exit 0; Belege vollstaendig.
# CA03 — apply mit Nicht-Supervisor-Actor -> Exit 1, keine Aenderung.
# CA04 — apply mit deaktiviertem Actor -> Exit 1.
# CA05 — DEFAULT-DENY: ohne injizierten Provider und mit leerer
#        ad.ldap-Konfiguration (config.yaml des Repos) -> Exit 1, Klartext.
#
# Version: v0.8.501 · Build: 501 · 2026-07-24
# =============================================================================

import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.ad_sync import ad_sync_admin
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover

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


class FakeProvider:
    def __init__(self, members):
        self.members = members
        self.target_group = "SEC_AIW_Ermittler"

    def fetch_members(self):
        return list(self.members)


class ScriptedInput:
    """Liefert vorbereitete Antworten in Reihenfolge (statt Terminal)."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError("Mehr Prompts als geskriptete Antworten.")
        return self.answers.pop(0)


class AdSyncAdminTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self.db_path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        now = int(time.time())
        con.execute(_PERSON)
        # id=1 Supervisor, id=2/3 Ermittler, id=4 deaktivierter Supervisor
        # (Deaktivierung nach der Migration, s. u.).
        con.execute("INSERT INTO person VALUES (1,'h0chef','Chefin',1,1,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (2,'h0erm','KHK Weg',1,0,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (3,'h0zwei','KOK Bleibt',1,0,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (4,'h0exsup','Ex-Chef',1,1,0,?)",
                    (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        con.execute("BEGIN IMMEDIATE")
        con.execute("UPDATE person SET is_active=0, deactivated_at=?, "
                    "deactivated_reason='Test' WHERE id=4", (now,))
        con.execute("COMMIT")
        con.close()

    def tearDown(self):
        for fn in os.listdir(self._tmp):
            try:
                os.remove(os.path.join(self._tmp, fn))
            except OSError:
                pass
        os.rmdir(self._tmp)

    def _run(self, argv, provider, answers=()):
        out, err = io.StringIO(), io.StringIO()
        script = ScriptedInput(answers)
        with redirect_stdout(out), redirect_stderr(err):
            rc = ad_sync_admin.main(
                ["--db", self.db_path] + argv,
                provider=provider, input_fn=script)
        return rc, out.getvalue(), err.getvalue(), script

    def _query(self, sql, args=()):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    # CA01 -------------------------------------------------------------------
    def test_ca01_preview_json(self):
        provider = FakeProvider([
            {"sam": "h0chef", "display_name": "Chefin"},
            {"sam": "h0zwei", "display_name": "KOK Bleibt"},
            {"sam": "h0neu", "display_name": "Neue Kollegin"},
        ])
        rc, out, _err, _s = self._run(["preview", "--json"], provider)
        self.assertEqual(rc, 0)
        plan = json.loads(out)
        self.assertEqual(plan["counts"]["create"], 1)
        self.assertEqual(plan["counts"]["deactivate_candidates"], 1)  # h0erm
        # Vorschau erzeugt KEINEN Beleg.
        rows = self._query(
            "SELECT COUNT(*) AS c FROM audit_log WHERE event_type='ad_sync_run'")
        self.assertEqual(rows[0]["c"], 0)

    # CA02 -------------------------------------------------------------------
    def test_ca02_apply_interactive(self):
        provider = FakeProvider([
            {"sam": "h0chef", "display_name": "Chefin"},
            {"sam": "h0neu", "display_name": "Neue Kollegin"},
        ])
        # Kandidaten (alphabetisch nach Bestand): h0erm (id=2), h0zwei (id=3).
        rc, out, _err, script = self._run(
            ["apply", "--actor", "h0chef"], provider,
            answers=["Entfernen", "nein, behalten"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(script.prompts), 2)

        # Neuaufnahme vollzogen (Flag + Rolle).
        neu = self._query(
            "SELECT * FROM person WHERE system_username='h0neu'")
        self.assertEqual(len(neu), 1)
        role = self._query(
            "SELECT role_code FROM person_role WHERE person_id=? "
            "AND revoked_at IS NULL", (neu[0]["id"],))
        self.assertEqual(role[0]["role_code"], "investigator")

        # Kandidat 1 deaktiviert (nie geloescht), Kandidat 2 unveraendert.
        p2 = self._query("SELECT * FROM person WHERE id=2")[0]
        self.assertEqual(int(p2["is_active"]), 0)
        p3 = self._query("SELECT * FROM person WHERE id=3")[0]
        self.assertEqual(int(p3["is_active"]), 1)

        # Belege: Lauf-Klammer, Deaktivierung, protokollierter Abbruch.
        for et, n in (("ad_sync_run", 1), ("person_deactivated", 1),
                      ("person_deactivation_aborted", 1)):
            rows = self._query(
                "SELECT COUNT(*) AS c FROM audit_log WHERE event_type=?", (et,))
            self.assertEqual(rows[0]["c"], n, "Beleganzahl %s" % et)
        self.assertIn("nur inaktiv geschaltet", out)

    # CA03 -------------------------------------------------------------------
    def test_ca03_apply_non_supervisor(self):
        provider = FakeProvider([{"sam": "h0chef", "display_name": "Chefin"}])
        rc, _out, err, _s = self._run(
            ["apply", "--actor", "h0zwei"], provider)
        self.assertEqual(rc, 1)
        self.assertIn("kein Supervisor", err)
        # Keine Aenderung, kein Lauf-Beleg.
        rows = self._query(
            "SELECT COUNT(*) AS c FROM audit_log WHERE event_type='ad_sync_run'")
        self.assertEqual(rows[0]["c"], 0)

    # CA04 -------------------------------------------------------------------
    def test_ca04_apply_deactivated_actor(self):
        provider = FakeProvider([{"sam": "h0chef", "display_name": "Chefin"}])
        rc, _out, err, _s = self._run(
            ["apply", "--actor", "h0exsup"], provider)
        self.assertEqual(rc, 1)
        self.assertIn("deaktiviert", err)

    # CA05 -------------------------------------------------------------------
    def test_ca05_default_deny_without_config(self):
        # Kein Provider injiziert -> LdapGroupReader.from_config gegen die
        # Repo-config.yaml (ad.ldap.* leer) -> Klartext-Abbruch, Exit 1.
        # Expliziter --config-Pfad (unabhaengig vom Arbeitsverzeichnis).
        repo_cfg = str(Path(__file__).resolve().parent.parent / "config.yaml")
        rc, _out, err, _s = self._run(
            ["--config", repo_cfg, "preview"], provider=None)
        self.assertEqual(rc, 1)
        self.assertIn("nicht konfiguriert", err)


if __name__ == "__main__":
    unittest.main()
