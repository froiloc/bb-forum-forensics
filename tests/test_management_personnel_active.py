# =============================================================================
# tests/test_management_personnel_active.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ruhestand von Hand
# =============================================================================
# Testsuite fuer POST /api/personnel/active und die Ausblendung in den
# Auswahllisten (Build 701, Ticket 95139d2a) — voll migrierte coordinator.db.
#
# PA01 — ohne personnel.edit -> 403; KEINE Datenaenderung, KEIN Beleg.
# PA02 — falsches/fehlendes Bestaetigungswort -> 400 'confirmation_rejected';
#        KEINE Datenaenderung, KEIN Beleg. Der exakte Vergleich gilt:
#        'entfernen' ist nicht 'Entfernen'.
# PA03 — fehlender Grund beim Inaktivsetzen -> 400; KEINE Datenaenderung.
# PA04 — Vollzug: is_active=0, Zeitstempel und Grund gesetzt, Beleg
#        person_deactivated mit meta 'personnel_ui' (NICHT 'ad_sync') und der
#        Zahl der offenen Faelle. Zweiter Aufruf -> 400 (bereits inaktiv).
# PA05 — SELBSTSCHUTZ: die eigene Person -> 400 self_guard, keine Aenderung.
# PA06 — Reaktivieren: is_active=1, Zeitstempel/Grund geleert, Beleg
#        person_reactivated; Wort 'Reaktivieren' verlangt.
# PA07 — GET /api/personnel liefert offene_faelle je Person und die
#        Bestaetigungsworte.
# PA08 — AUSWAHLLISTE: /api/assignable bietet die inaktive Person nicht mehr
#        zur Zuweisung an und sagt, dass sie ausgeblendet ist — waehrend ihr
#        Fall in derselben Antwort UNVERAENDERT mit ihrer Zuweisung
#        stehenbleibt.
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


class ManagementPersonnelActiveTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        now = int(time.time())
        con.execute(_PERSON)
        # 1 Chefin (personnel.view/edit + dashboard/caseoverview), 2 Ermittler
        # ohne Rechte, 3 Zielperson des Ruhestands.
        con.execute("INSERT INTO person VALUES (1,'h0chef','Chefin',1,1,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (2,'h0erm','KHK Muster',1,0,0,?)",
                    (now,))
        con.execute("INSERT INTO person VALUES (3,'h0ziel','KOK Ziel',1,0,0,?)",
                    (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        writer = CoordinatorWriter(con, AuditLog(con))
        rbac = RbacRepo(con, writer)
        for cap in ("personnel.view", "personnel.edit"):
            rbac.grant("supervisor", cap, actor_id=1)
        # Die Zuweisungs-Sicht verlangt Umfang 'alle' (management_app
        # _assignable) — sie ist die AUSWAHLLISTE, um die es in PA08 geht.
        rbac.grant("supervisor", "assignment.edit", scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # EIN OFFENER FALL AUF DER ZIELPERSON. Er ist der Kern von PA04/PA08:
        # das Inaktivsetzen darf ihn nicht verstecken und nicht loesen.
        con.execute(
            "INSERT INTO cases (subject_id, username, status, priority, "
            "assigned_to, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (4711, "verdaechtiger", "open", 3, 3, now, now))
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

    def _query(self, sql, args=()):
        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()

    def _person(self, pid=3):
        return self._query("SELECT * FROM person WHERE id=?", (pid,))[0]

    def _events(self, event_type):
        return self._query(
            "SELECT * FROM audit_log WHERE event_type=? ORDER BY seq",
            (event_type,))

    def _deaktivieren(self, app, **ueberschreiben):
        body = {"person_id": 3, "active": False, "reason": "ausgeschieden",
                "confirmation": "Entfernen"}
        body.update(ueberschreiben)
        return app.dispatch_write(1, "/api/personnel/active", body)

    # PA01 -------------------------------------------------------------------
    def test_pa01_ohne_recht_403_und_keine_aenderung(self):
        app = self._app()
        r = app.dispatch_write(2, "/api/personnel/active",
                               {"person_id": 3, "active": False,
                                "reason": "x", "confirmation": "Entfernen"})
        self.assertEqual(r.status, 403)
        self.assertEqual(int(self._person()["is_active"]), 1)
        self.assertEqual(len(self._events("person_deactivated")), 0)

    # PA02 -------------------------------------------------------------------
    def test_pa02_falsches_wort_wird_abgewiesen(self):
        app = self._app()
        for wort in ("", "entfernen", "Entfernen ", "Loeschen"):
            r = self._deaktivieren(app, confirmation=wort)
            self.assertEqual(r.status, 400, "Wort %r kam durch" % wort)
            body = json.loads(r.body)
            self.assertEqual(body["error"], "confirmation_rejected")
            # Die Antwort NENNT das erwartete Wort — sonst raet der Nutzer.
            self.assertEqual(body["expected"], "Entfernen")
        self.assertEqual(int(self._person()["is_active"]), 1)
        self.assertEqual(len(self._events("person_deactivated")), 0)

    # PA03 -------------------------------------------------------------------
    def test_pa03_ohne_grund_kein_vollzug(self):
        app = self._app()
        for grund in (None, "", "   "):
            r = self._deaktivieren(app, reason=grund)
            self.assertEqual(r.status, 400)
            self.assertIn("reason", json.loads(r.body)["detail"])
        self.assertEqual(int(self._person()["is_active"]), 1)
        self.assertEqual(len(self._events("person_deactivated")), 0)

    # PA04 -------------------------------------------------------------------
    def test_pa04_vollzug_mit_beleg_und_offenen_faellen(self):
        app = self._app()
        r = self._deaktivieren(app)
        self.assertEqual(r.status, 200)
        antwort = json.loads(r.body)
        self.assertTrue(antwort["ok"])
        self.assertFalse(antwort["active"])
        # DIE ZAHL DER OFFENEN FAELLE WANDERT IN DIE ANTWORT — sie ist die
        # Verpflichtung zur Umverteilung, nicht bloss eine Anzeige.
        self.assertEqual(antwort["offene_faelle"], 1)

        p = self._person()
        self.assertEqual(int(p["is_active"]), 0)
        self.assertIsNotNone(p["deactivated_at"])
        self.assertEqual(p["deactivated_reason"], "ausgeschieden")

        belege = self._events("person_deactivated")
        self.assertEqual(len(belege), 1)
        payload = json.loads(belege[0]["content"])
        self.assertEqual(payload["reason"], "ausgeschieden")
        self.assertEqual(payload["is_active"], {"alt": 1, "neu": 0})
        meta = json.loads(belege[0]["meta"])
        # QUELLE 'personnel_ui', NICHT 'ad_sync': es hat kein Abgleich
        # stattgefunden, und ein Beleg, der das behauptete, waere eine
        # Falschangabe im Beweismittel.
        self.assertEqual(meta["quelle"], "personnel_ui")
        self.assertEqual(meta["bestaetigungswort"], "Entfernen")
        self.assertEqual(meta["offene_faelle_bei_entscheidung"], 1)

        # DER FALL BLEIBT ZUGEWIESEN. Deaktivieren ist kein Loesen.
        fall = self._query("SELECT assigned_to, status FROM cases")[0]
        self.assertEqual(int(fall["assigned_to"]), 3)
        self.assertEqual(fall["status"], "open")

        # Zweiter Anlauf: bereits inaktiv -> 400, kein zweiter Beleg.
        r = self._deaktivieren(app)
        self.assertEqual(r.status, 400)
        self.assertEqual(len(self._events("person_deactivated")), 1)

    # PA05 -------------------------------------------------------------------
    def test_pa05_selbstschutz(self):
        """
        Sich selbst inaktiv zu setzen waere der vollstaendige Lockout —
        identity.py weist inaktive Konten an der Anmeldung ab.
        """
        app = self._app()
        r = self._deaktivieren(app, person_id=1)
        self.assertEqual(r.status, 400)
        self.assertEqual(json.loads(r.body)["error"], "self_guard")
        self.assertEqual(int(self._person(1)["is_active"]), 1)
        self.assertEqual(len(self._events("person_deactivated")), 0)

    # PA06 -------------------------------------------------------------------
    def test_pa06_reaktivieren(self):
        app = self._app()
        self.assertEqual(self._deaktivieren(app).status, 200)

        # Falsches Wort: 'Entfernen' taugt hier nicht.
        r = app.dispatch_write(1, "/api/personnel/active",
                               {"person_id": 3, "active": True,
                                "confirmation": "Entfernen"})
        self.assertEqual(r.status, 400)
        self.assertEqual(json.loads(r.body)["expected"], "Reaktivieren")
        self.assertEqual(int(self._person()["is_active"]), 0)

        r = app.dispatch_write(1, "/api/personnel/active",
                               {"person_id": 3, "active": True,
                                "confirmation": "Reaktivieren"})
        self.assertEqual(r.status, 200)
        self.assertTrue(json.loads(r.body)["active"])
        p = self._person()
        self.assertEqual(int(p["is_active"]), 1)
        self.assertIsNone(p["deactivated_at"])
        self.assertIsNone(p["deactivated_reason"])

        belege = self._events("person_reactivated")
        self.assertEqual(len(belege), 1)
        # Der alte Grund geht NICHT verloren — er steht als 'alt' im Beleg.
        payload = json.loads(belege[0]["content"])
        self.assertEqual(payload["deactivated_reason"]["alt"], "ausgeschieden")
        self.assertEqual(json.loads(belege[0]["meta"])["quelle"],
                         "personnel_ui")

    # PA07 -------------------------------------------------------------------
    def test_pa07_liste_traegt_offene_faelle_und_worte(self):
        data = json.loads(self._app().dispatch(1, "/api/personnel", {}).body)
        self.assertEqual(data["confirm"],
                         {"deactivate": "Entfernen",
                          "reactivate": "Reaktivieren"})
        self.assertIsNone(data["offene_faelle_hinweis"])
        je_id = {p["id"]: p for p in data["persons"]}
        self.assertEqual(je_id[3]["offene_faelle"], 1)
        self.assertEqual(je_id[2]["offene_faelle"], 0)

    # PA08 -------------------------------------------------------------------
    def test_pa08_auswahl_ohne_inaktive_fall_bleibt_sichtbar(self):
        """
        DER KERN DES TICKETS UND SEINE GRENZE IN EINEM FALL: die Person
        verschwindet aus der AUSWAHL der Zuweisung, ihr Fall aber bleibt in
        der Fallliste stehen — mit ihrer Zuweisung. Verschwaende auch er,
        waere aus dem Ausblenden ein Beweisverlust geworden.
        """
        app = self._app()
        vorher = json.loads(app.dispatch(1, "/api/assignable", {}).body)
        self.assertIn(3, [i["person_id"] for i in vorher["investigators"]])
        self.assertEqual(vorher["inaktive"]["ausgeblendet"], 0)

        self.assertEqual(self._deaktivieren(app).status, 200)

        nachher = json.loads(
            self._app().dispatch(1, "/api/assignable", {}).body)
        self.assertNotIn(3, [i["person_id"]
                             for i in nachher["investigators"]])
        # NICHT STILL: die Ausblendung wird beziffert und benannt.
        self.assertEqual(nachher["inaktive"]["ausgeblendet"], 1)
        self.assertEqual(nachher["inaktive"]["ausgeblendete_kennungen"],
                         ["h0ziel"])
        # Der Fall steht unveraendert da.
        faelle = nachher["cases"]
        self.assertEqual(len(faelle), 1)
        self.assertEqual(faelle[0]["assigned_to"], 3)


if __name__ == "__main__":                                # pragma: no cover
    unittest.main()
