# =============================================================================
# tests/test_help_api.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H2)
# =============================================================================
# Testsuite fuer Build 589: die drei Hilfe-Routen am lebenden ManagementApp.
#
#   GET /help                      - Vollhilfe als Seite
#   GET /api/help/kontext?sicht=x  - Kontexttexte einer Sicht
#   GET /api/help/sicht/<id>       - ein Kapitel als JSON
#
# DER KERN DIESER SUITE IST DIE SPERRE (E1). Die reine Filterfunktion ist in
# test_help_sichtbarkeit.py belegt; hier wird geprueft, dass die ROUTEN sie
# auch wirklich anwenden - eine korrekte Funktion, die niemand aufruft,
# schuetzt nichts.
#
# HA01 - /help mit Rechten: enthaelt die erlaubten Sichten, NICHT die anderen
# HA02 - /help ohne Rechte: nur die Sicht ohne Rechtepruefung ('viewprefs')
# HA03 - /api/help/sicht/<id> mit Recht -> 200
# HA04 - /api/help/sicht/<id> OHNE Recht -> 403 (der Kern von E1)
# HA05 - /api/help/sicht/<unbekannt> -> 404 (unterschieden von 403)
# HA06 - /api/help/kontext ohne Parameter -> 400
# HA07 - /api/help/kontext ohne Recht -> 403, mit Recht -> 200
# HA08 - Kapitel fehlt noch, Recht vorhanden -> 200 mit ehrlichem Platzhalter
#        (NICHT 404 - das waere eine Luege ueber den Grund)
# HA09 - alle drei Routen schreiben NICHTS (Audit-Spitze unveraendert)
# HA10 - /help liefert text/html und ist UTF-8-kodiert
# HA11 - help.css ist ueber /static/help.css erreichbar
# HA12 - Build 591: die Shell-Kontexthilfe liegt JEDER Antwort bei und
#        unterliegt keiner Sperre (sie erklaert Bedienelemente, die jede
#        Person ohnehin vor sich sieht)
#
# Build 622 (H19) - der Betriebsteil an der lebenden Route:
# HA13 - mit 'ops.view' stehen ALLE Betriebskapitel in der Antwort
# HA14 - ohne 'ops.view' steht von ihnen NICHTS darin - weder Kapitel noch
#        Verzeichniseintrag noch Suchindex-Eintrag
# HA15 - das ausgelieferte Stylesheet kennt die Klassen des Betriebsteils
# HA16 - der Betriebsteil aendert nichts an der Belegkette
#
# Version: v0.8.622 - Build: 622 - 2026-08-01
# =============================================================================

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.rbac.rbac_repo import RbacRepo                      # noqa: E402
from management.server.management_app import ManagementApp          # noqa: E402

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


class HilfeApiTest(unittest.TestCase):
    """
    Person 1 = Chefin (dashboard.view, caseoverview.view, ops.view),
    Person 2 = Ermittler OHNE jedes Recht. Der Unterschied traegt die Sperre.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.forensic = Path(self._tmp) / "forensic"
        self.evidence = Path(self._tmp) / "evidence"
        self.forensic.mkdir()
        self.evidence.mkdir()

        con = sqlite3.connect(self.db_path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.executescript(_PERSON)
        con.executescript(_OLD_SCRAPE_JOBS)
        now = int(time.time())
        for uname, dname, inv, sup in (
                ("NRW\\chefin", "Chef-Ermittlerin", 0, 1),
                ("NRW\\ermittler", "Ermittler", 1, 0)):
            con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,?)", (uname, dname, inv, sup, now))

        self.audit = AuditLog(con)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(con, self.audit)

        rbac = RbacRepo(con, self.writer)
        # Build 698 (Vorgang 60fe72fb): 'caseoverview.view' ergaenzt, damit
        # HA01 weiterhin BEIDE Kapitel prueft. Die Trennung selbst prueft
        # tests/test_help_sichtbarkeit.py (HS02).
        for cap in ("dashboard.view", "caseoverview.view", "ops.view"):
            rbac.grant("supervisor", cap, scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Person 2 bekommt bewusst nichts.

        self.con = con
        self.app = ManagementApp(self.db_path,
                                 forensic_dir=str(self.forensic),
                                 evidence_dir=str(self.evidence))

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------------ Hilfen
    def _get(self, path, query=None):
        return self.app.dispatch(1, path, query or {})

    def _get_als(self, person_id, path, query=None):
        return self.app.dispatch(person_id, path, query or {})

    def _json(self, resp):
        return json.loads(resp.body.decode("utf-8"))

    def _spitze(self):
        return self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]

    # --- HA01 / HA02 ------------------------------------------------------
    def test_ha01_help_seite_zeigt_nur_erlaubte_sichten(self):
        resp = self._get("/help")
        self.assertEqual(200, resp.status)
        html = resp.body.decode("utf-8")
        # dashboard.view -> 'dashboard'; caseoverview.view -> 'faelle'
        self.assertIn('id="dashboard"', html)
        self.assertIn('id="faelle"', html)
        # ops.view -> 'integrity', 'audit', 'promotion'
        self.assertIn('id="integrity"', html)
        # KEIN Recht auf die Berichts-Abnahme -> das Kapitel fehlt ganz,
        # auch im Verzeichnis (strenge Lesart von E1).
        self.assertNotIn('id="approval"', html)
        self.assertNotIn('href="#approval"', html)

    def test_ha02_ohne_rechte_nur_viewprefs(self):
        resp = self._get_als(2, "/help")
        self.assertEqual(200, resp.status)
        html = resp.body.decode("utf-8")
        self.assertIn('id="viewprefs"', html)
        self.assertNotIn('id="dashboard"', html)
        self.assertNotIn('id="integrity"', html)

    # --- HA03 / HA04 / HA05 ------------------------------------------------
    def test_ha03_kapitel_mit_recht(self):
        resp = self._get("/api/help/sicht/dashboard")
        self.assertEqual(200, resp.status)
        self.assertEqual("dashboard", self._json(resp)["sicht"])

    def test_ha04_kapitel_ohne_recht_ist_403(self):
        resp = self._get_als(2, "/api/help/sicht/dashboard")
        self.assertEqual(403, resp.status)
        self.assertEqual("forbidden", self._json(resp)["error"])

    def test_ha05_unbekannte_sicht_ist_404(self):
        resp = self._get("/api/help/sicht/gibtsnicht")
        self.assertEqual(404, resp.status)
        self.assertEqual("unbekannte_sicht", self._json(resp)["error"])

    # --- HA06 / HA07 -------------------------------------------------------
    def test_ha06_kontext_ohne_parameter_ist_400(self):
        resp = self._get("/api/help/kontext")
        self.assertEqual(400, resp.status)

    def test_ha07_kontext_rechtelage(self):
        ok = self._get("/api/help/kontext", {"sicht": ["dashboard"]})
        self.assertEqual(200, ok.status)
        self.assertEqual("dashboard", self._json(ok)["sicht"])

        gesperrt = self._get_als(2, "/api/help/kontext",
                                 {"sicht": ["dashboard"]})
        self.assertEqual(403, gesperrt.status)

        unbekannt = self._get("/api/help/kontext", {"sicht": ["gibtsnicht"]})
        self.assertEqual(404, unbekannt.status)

    # --- HA08 --------------------------------------------------------------
    def test_ha08_fehlendes_kapitel_ist_kein_404(self):
        """
        In H2 gibt es noch KEIN Kapitel. Die Route muss das ehrlich sagen -
        mit 200 und 'vorhanden': false - statt mit 404 zu behaupten, es gaebe
        die Sicht nicht. Der Unterschied ist fuer die Fehlersuche im Betrieb
        entscheidend.
        """
        resp = self._get("/api/help/sicht/dashboard")
        daten = self._json(resp)
        if daten.get("vorhanden") is False:
            self.assertIn("folgt", daten["hinweis"])
            self.assertEqual("Dashboard", daten["label"])
        else:
            # Ab H7 existiert das Kapitel - dann muss es vollstaendig sein.
            self.assertIn("abschnitte", daten)
            self.assertTrue(daten["abschnitte"])

    # --- HA09 --------------------------------------------------------------
    def test_ha09_hilfe_schreibt_nichts(self):
        vorher = self._spitze()
        self._get("/help")
        self._get("/api/help/kontext", {"sicht": ["dashboard"]})
        self._get("/api/help/sicht/dashboard")
        self._get_als(2, "/api/help/sicht/dashboard")
        self.assertEqual(vorher, self._spitze())

    # --- HA10 / HA11 -------------------------------------------------------
    def test_ha10_content_type_und_kodierung(self):
        resp = self._get("/help")
        self.assertIn("text/html", resp.content_type)
        self.assertIn("charset=utf-8", resp.content_type)
        # Umlaute aus den Katalog-Labels muessen unbeschadet ankommen.
        self.assertIn("Fallübersicht", resp.body.decode("utf-8"))

    def test_ha12_shell_kontext_liegt_bei(self):
        """
        Kopfzeile, Navigation und Banner stehen in JEDER Sicht. Ihre
        Erklaerungen an eine einzelne Sicht zu haengen hiesse, sie auf allen
        anderen unerreichbar zu machen - deshalb liegen sie jeder Antwort bei.
        """
        from management.help.inhalt.shell import SHELL_KONTEXT

        daten = self._json(self._get("/api/help/kontext",
                                     {"sicht": ["dashboard"]}))
        for k in SHELL_KONTEXT:
            self.assertIn(k.schluessel, daten["eintraege"])
            self.assertTrue(daten["eintraege"][k.schluessel]["text"])
        # auch auf einer anderen Sicht
        daten2 = self._json(self._get("/api/help/kontext",
                                      {"sicht": ["integrity"]}))
        self.assertIn("shell.navigation", daten2["eintraege"])

    def test_ha11_stylesheet_wird_ausgeliefert(self):
        resp = self._get("/static/help.css")
        self.assertEqual(200, resp.status)
        self.assertIn("text/css", resp.content_type)
        self.assertIn(b"aiw-h-kapitel", resp.body)

    # --- Build 622 (H19): der Betriebsteil an der lebenden Route ----------
    # HA13 - mit 'ops.view' liefert /help die Betriebskapitel mit aus
    # HA14 - OHNE 'ops.view' ist von ihnen NICHTS in der Antwort - der Kern
    #        von E1, hier an der Route und nicht nur an der reinen Funktion
    # HA15 - das Stylesheet traegt die Regeln fuer den Betriebsteil (ein
    #        ausgeliefertes Markup ohne die zugehoerige Gestaltung waere ein
    #        halber Einbau)
    # HA16 - der Betriebsteil aendert nichts: /help schreibt weiterhin nicht

    def test_ha13_betriebsteil_mit_ops_view(self):
        """
        Person 1 hat 'ops.view'. ALLE Werkzeuge muessen als Kapitel in der
        Antwort stehen - geprueft wird VOLLZAEHLIG und nicht stichprobenhaft:
        ein einzelnes fehlendes Kapitel faellt im Handbuch niemandem auf.
        """
        from management.help.cli_katalog import CLI_KATALOG

        html = self._get("/help").body.decode("utf-8")
        self.assertIn("Betriebskapitel", html)
        self.assertIn('id="cli-vorspann"', html)
        fehlend = [e.schluessel for e in CLI_KATALOG
                   if 'id="cli-%s"' % e.schluessel not in html]
        self.assertEqual([], fehlend, "ohne Kapitel: %s" % fehlend)

    def test_ha14_ohne_ops_view_kein_betriebsteil(self):
        """
        Person 2 hat kein einziges Recht. Von den Betriebskapiteln darf
        nichts durchkommen: keine Kennung, kein Verzeichniseintrag, kein
        Suchindex-Eintrag. Ein durchsuchbarer Index waere die Luecke, durch
        die eine Sperre am haeufigsten faellt.
        """
        html = self._get_als(2, "/help").body.decode("utf-8")
        self.assertNotIn("Betriebskapitel", html)
        self.assertNotIn("cli-", html)
        self.assertNotIn("backup_admin", html)
        self.assertNotIn("coordinator.db", html)

    def test_ha15_stylesheet_kennt_den_betriebsteil(self):
        resp = self._get("/static/help.css")
        self.assertIn(b"aiw-h-betrieb", resp.body)
        self.assertIn(b"aiw-h-cli-tabelle", resp.body)

    def test_ha16_betriebsteil_schreibt_nichts(self):
        """
        /help war lesend und bleibt es. Gemessen an der Spitze der
        Belegkette - dieselbe Messung wie HA09.
        """
        vorher = self._spitze()
        self._get("/help")
        self._get_als(2, "/help")
        self.assertEqual(vorher, self._spitze())


if __name__ == "__main__":
    unittest.main()
