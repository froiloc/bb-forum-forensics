# =============================================================================
# tests/test_view_export_api.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem (AP-2B)
# =============================================================================
# Testsuite fuer Build 511: GET /api/view/export (Akten-Export je Sicht).
#
# VE01 — unbekannte/fehlende 'view' -> 404 mit der Liste der bekannten IDs.
# VE02 — RECHTE-ERBE (der Kern des Entwurfs): OHNE das Recht der Sicht liefert
#        der Export 403 mit der Faehigkeit der SICHT — obwohl der Export selbst
#        keine Rechtepruefung enthaelt. Belegt, dass es keinen zweiten,
#        abdriftbaren Rechtepfad gibt.
# VE03 — MIT dem Recht: 200, text/html, Aktenkopf + Erzeugungsvermerk +
#        Pruefsumme; die Daten der Sicht stehen drin.
# VE04 — Query-DURCHREICHUNG: zusaetzliche Parameter erreichen den Sicht-
#        Endpunkt (hier ?subject_id=), 'view' selbst wird entfernt und die
#        angewandten Parameter stehen im Dokument.
# VE05 — Nicht-200 des Sicht-Endpunkts wird UNVERAENDERT durchgereicht (kein
#        beschoenigtes Leer-Dokument, Grundregel 1).
# VE06 — echter Leerbefund: 200 mit „Keine Einträge", nicht mit einem Fehler.
# VE07 — jede Sicht des Katalogs ist tatsaechlich abrufbar (Rauchtest ueber
#        ALLE Specs mit einem Vollrechte-Konto) — keine tote Katalogzeile.
# VE08 — KATALOG-KONSISTENZ gegen cockpit.js: jede exportierbare view_id
#        existiert im VIEW_CATALOG, und jede Cockpit-Sicht ist entweder
#        exportierbar oder in der Ausnahmeliste des Katalogs benannt. So faellt
#        eine kuenftige neue Sicht nicht STILL aus dem Export heraus.
#
# Version: v0.8.511 · Build: 511 · 2026-07-24
# =============================================================================

import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.export.view_export_catalog import (
    VIEW_EXPORTS,
    known_view_ids,
    spec_for,
)
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac.catalog import CAPABILITY_CODES
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

#: Sichten, die BEWUSST keinen generischen Akten-Export haben. Deckungsgleich
#  mit dem Kommentar in view_export_catalog.py — hier als pruefbare Liste, damit
#  die Begruendung nicht nur im Fliesstext steht.
_BEWUSST_OHNE_EXPORT = {"notes", "lectorate", "approval",
                        # Build 563 (AP-3E, Instanz B): die
                        # Volltextsuche. Begruendung ausfuehrlich in
                        # view_export_catalog.py — kurz: sie hat keinen
                        # Bestand, ihre Endpunkte sind POST mit
                        # PFLICHT-Zweckangabe, und ein generischer
                        # Export wuerde die Stufe-2-Sperre umgehen.
                        "search"}


class ViewExportApiTests(unittest.TestCase):

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

        # Person 1 bekommt ALLE Faehigkeiten (Vollrechte-Konto fuer den
        # Rauchtest VE07). Person 2 bleibt bewusst OHNE jedes Recht.
        for cap in sorted(CAPABILITY_CODES):
            self.rbac.grant("supervisor", cap, scope="alle", actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

        # Etwas Substanz, damit der Export nicht nur Leerbefunde zeigt.
        self.con.execute(
            "INSERT INTO subject_alias (subject_id, alias, alias_norm, "
            "kind_code, basis, is_active, created_at, updated_at, audit_seq, "
            "created_audit_seq) VALUES (4711, 'Panther', 'panther', "
            "'forenname', 'Signatur', 1, ?, ?, 1, 1)", (now, now))

        # ECHTE templates.db: die drei Redaktions-Sichten (templates/
        # doctemplates/modules) lesen aus einer SEPARATEN Datenbank. Ohne sie
        # waere VE07 fuer diese drei nur ein Fehlerpfad-Test — mit ihr deckt
        # der Rauchtest sie wirklich ab.
        #
        # BEFUND (bei Build 511 aufgefallen, siehe Uebergabe): die eingecheckte
        # 'templates.db.schema.sql' im Repo-Wurzelverzeichnis ist gegenueber
        # dem Code VERALTET — ihr fehlt u. a. placeholders.validation_ci
        # (nachgezogen von management/migrate_templates_ci.py, Build 497).
        # Ein Aufbau NUR aus dem Schema laesst /api/templates/placeholders mit
        # 'no such column: validation_ci' scheitern. Die Fixture wendet deshalb
        # dieselben Migrationsskripte an, die auch der Betrieb faehrt — so
        # prueft der Test den ECHTEN Zielzustand und nicht eine Altfassung.
        self.tdb = os.path.join(self._tmp, "templates.db")
        tcon = sqlite3.connect(self.tdb)
        try:
            tcon.executescript(
                Path("templates.db.schema.sql").read_text(encoding="utf-8"))
            tcon.commit()
            from management import migrate_templates_ci
            migrate_templates_ci.apply_migration(tcon)
            tcon.commit()
        finally:
            tcon.close()

        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.app = ManagementApp(self.db_path, templates_db=self.tdb)

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

    def _html(self, resp):
        return resp.body.decode("utf-8")

    def _export(self, person, view, **params):
        q = {"view": [view]}
        for k, v in params.items():
            q[k] = [str(v)]
        return self.app.dispatch(person, "/api/view/export", q)

    # VE01 -------------------------------------------------------------------
    def test_ve01_unknown_view_404(self):
        for q in ({"view": ["gibtsnicht"]}, {}, {"view": [""]}):
            r = self.app.dispatch(1, "/api/view/export", q)
            self.assertEqual(r.status, 404)
            body = self._json(r)
            self.assertEqual(body["error"], "unknown_view")
            # Die Antwort NENNT die bekannten IDs — der Aufrufer bleibt nicht
            # ratlos zurueck.
            self.assertIn("alias", body["known"])
            self.assertEqual(len(body["known"]), len(known_view_ids()))

    # VE02 -------------------------------------------------------------------
    def test_ve02_rechte_werden_geerbt(self):
        """
        Der Kern des Entwurfs: _view_export prueft SELBST kein Recht. Trotzdem
        muss ein Konto ohne das Recht der Sicht ein 403 bekommen — und zwar mit
        der Faehigkeit der SICHT. Das belegt, dass es keinen zweiten,
        abdriftbaren Rechtepfad gibt.
        """
        r = self._export(2, "alias")
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "crossref.view")

        r2 = self._export(2, "policy")
        self.assertEqual(r2.status, 403)
        self.assertEqual(self._json(r2)["capability"], "policy.view")

        # Gegenprobe: mit Recht klappt genau dieselbe Anfrage.
        self.assertEqual(self._export(1, "alias").status, 200)

    # VE03 -------------------------------------------------------------------
    def test_ve03_export_inhalt(self):
        r = self._export(1, "alias")
        self.assertEqual(r.status, 200)
        self.assertIn("text/html", r.content_type)
        out = self._html(r)

        self.assertIn("<!DOCTYPE html>", out)
        self.assertIn("Aliasse — globaler Namenskatalog", out)
        self.assertIn("VERTRAULICH", out)
        self.assertIn("Erstellt von:", out)
        self.assertIn("Werkzeug-Build:", out)
        self.assertIn("Prüfsumme (SHA-256):", out)
        # Die Daten der Sicht stehen wirklich drin.
        self.assertIn("Panther", out)
        self.assertIn("4711", out)
        # Akten-Export ist druckbar und JS-frei.
        self.assertIn("@media print", out)
        self.assertNotIn("<script", out.lower())

    # VE04 -------------------------------------------------------------------
    def test_ve04_query_durchreichung(self):
        # ?subject_id= erreicht den Sicht-Endpunkt: ein anderes Konto -> leer.
        leer = self._html(self._export(1, "alias", subject_id=9999))
        self.assertNotIn("Panther", leer)
        treffer = self._html(self._export(1, "alias", subject_id=4711))
        self.assertIn("Panther", treffer)

        # Die angewandten Parameter stehen IM Dokument (ein Export ohne seinen
        # Filter waere als Beleg wertlos) — 'view' selbst nicht.
        self.assertIn("Angewandte Parameter: subject_id=4711", treffer)
        self.assertNotIn("view=alias", treffer)

    # VE05 -------------------------------------------------------------------
    def test_ve05_fehler_werden_durchgereicht(self):
        # /api/alias?subject_id=abc -> der Sicht-Endpunkt antwortet 400.
        r = self.app.dispatch(1, "/api/view/export",
                              {"view": ["alias"], "subject_id": ["abc"]})
        self.assertEqual(r.status, 400)
        self.assertIn("application/json", r.content_type)
        self.assertEqual(self._json(r)["error"], "bad_request")

    # VE06 -------------------------------------------------------------------
    def test_ve06_leerbefund_ist_kein_fehler(self):
        r = self._export(1, "merge")          # noch keine Zusammenfuehrung
        self.assertEqual(r.status, 200)
        out = self._html(r)
        self.assertIn("Identitäts-Gruppen", out)
        self.assertIn("echter Leerbefund", out)

    # VE07 -------------------------------------------------------------------
    def test_ve07_alle_katalogsichten_sind_abrufbar(self):
        """
        Rauchtest ueber den GESAMTEN Katalog mit einem Vollrechte-Konto: keine
        Spec darf auf einen Endpunkt zeigen, den es nicht gibt, und keine darf
        den Renderer sprengen. Erlaubt sind 200 (Regelfall) und die ehrlich
        durchgereichten 400/503 (fehlender Pflichtparameter bzw. fehlendes
        Substrat) — NICHT aber 404 (toter Endpunkt) oder 500 (Absturz).
        """
        problems = []
        for spec in VIEW_EXPORTS:
            r = self._export(1, spec.view_id)
            if r.status == 200:
                out = self._html(r)
                if "Prüfsumme (SHA-256):" not in out:
                    problems.append((spec.view_id, "kein Erzeugungsvermerk"))
            elif r.status in (400, 503):
                # z. B. capacity ohne 'start', onboarding ohne 'person_id'
                if spec.requires:
                    continue
                detail = self._json(r)
                problems.append((spec.view_id, "%s %s" % (r.status, detail)))
            else:
                problems.append((spec.view_id, "Status %d" % r.status))
        self.assertEqual(problems, [], "Katalogsichten mit Problemen: %r"
                                       % problems)

    # VE08 -------------------------------------------------------------------
    def test_ve08_katalog_deckt_cockpit_view_catalog(self):
        """
        Konsistenz gegen die WAHRHEITSQUELLE cockpit.js: sonst faellt eine
        kuenftige neue Sicht STILL aus dem Akten-Export heraus — genau die Art
        Luecke, die dieser Build schliessen soll.
        """
        js = Path("management/server/static/cockpit.js").read_text(
            encoding="utf-8")
        block = js.split("VIEW_CATALOG", 1)[1].split("];", 1)[0]
        cockpit_ids = set(re.findall(r"\{\s*id:\s*'([a-z]+)'", block))
        self.assertGreater(len(cockpit_ids), 25, "VIEW_CATALOG nicht erkannt")

        export_ids = set(known_view_ids())

        # (a) Jede exportierbare Sicht existiert im Cockpit.
        verwaist = export_ids - cockpit_ids
        self.assertEqual(verwaist, set(),
                         "Export-Katalog nennt Sichten, die es nicht gibt: %r"
                         % verwaist)

        # (b) Jede Cockpit-Sicht ist exportierbar ODER ausdruecklich ausgenommen.
        unversorgt = cockpit_ids - export_ids - _BEWUSST_OHNE_EXPORT
        self.assertEqual(unversorgt, set(),
                         "Sichten ohne Akten-Export und ohne Begruendung: %r"
                         % unversorgt)

        # (c) Die Ausnahmeliste ist nicht veraltet (jede genannte Sicht gibt es).
        self.assertTrue(_BEWUSST_OHNE_EXPORT <= cockpit_ids)

    # VE09 -------------------------------------------------------------------
    def test_ve09_spec_for_und_pflichtparameter(self):
        self.assertIsNone(spec_for("gibtsnicht"))
        self.assertIsNone(spec_for(""))
        self.assertEqual(spec_for("alias").api_path, "/api/alias")
        # 'requires' ist rein informativ — erzwungen wird nichts; der Endpunkt
        # antwortet selbst, und der Export reicht das ehrlich durch.
        self.assertIn("person_id", spec_for("onboarding").requires)
        r = self._export(1, "onboarding")
        self.assertIn(r.status, (200, 400))


if __name__ == "__main__":
    unittest.main()
