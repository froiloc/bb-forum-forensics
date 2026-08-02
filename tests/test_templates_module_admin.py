# =============================================================================
# tests/test_templates_module_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — W1 (Build 426): Baustein-Modul-Authoring (Backend)
# =============================================================================
# TM01 — validate_static: gueltiges Modul -> keine Fehler.
# TM02 — validate_static: module_key-Zeichenraum, Pflichtfelder title/topic/body.
# TM03 — validate_static: role-Pruefung (ROLES).
# TM04 — placeholder_summary: zaehlt auto/mandatory/optional in Auftrittsreihenfolge.
# TM05 — ModuleAuthorRepo.upsert: create + update, je Audit-Zeile (module),
#        module_key gesetzt, genau EINE Zeile.
# TM06 — GET /api/templates/modules: 200 mit Recht, 403 ohne.
# TM07 — POST /api/templates/module: anlegen (200) + Liste + Audit; 400 bei
#        ungueltigen Feldern (nichts geschrieben).
# TM08 — POST /api/templates/module/dryrun: schreibfrei (summary), NICHTS
#        geschrieben; ok=False bei Fehler (200); 403 ohne Recht.
#
# Version: v0.7.426 · Build: 426 · 2026-07-15
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
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.server.management_app import ManagementApp
from management.templates_admin.module_validator import (
    validate_static, placeholder_summary, ROLES,
)
from management.templates_admin.module_repo import (
    ModuleAuthorRepo, ModuleKeyAssignError,
)

# report_modules (inkl. module_key + partieller UNIQUE-Index) + templates_audit_log.
_DDL_MODULES = """
CREATE TABLE report_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT,
    role TEXT NOT NULL CHECK (role IN ('intro','conclusion','body','legal','appendix','closing')),
    topic TEXT NOT NULL, body TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1, created_by TEXT NOT NULL,
    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, module_key TEXT,
    -- Build 655 (Ticket 5d81a0c7). Deckungsgleich mit templates.db.schema.sql.
    block_type TEXT NOT NULL DEFAULT 'paragraph'
        CHECK (block_type IN ('paragraph','header','list','table','quote','delimiter')),
    block_data TEXT
);
CREATE UNIQUE INDEX ux_report_modules_key ON report_modules (module_key)
    WHERE module_key IS NOT NULL;
"""
_DDL_AUDIT = """
CREATE TABLE templates_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, target_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('module','query','template')),
    changed_by TEXT NOT NULL, changed_at INTEGER NOT NULL, old_value TEXT, new_value TEXT
)
"""
_GOOD = {"module_key": "intro.standard", "title": "Standard-Einleitung",
         "description": "", "role": "intro", "topic": "Allgemein",
         "body": "Guten Tag {{a:username}}, dies ist {{m:sachbearbeiter}}.",
         "sort_order": 1}

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
    error_message TEXT, assigned_to INTEGER, note TEXT
)
"""


def _mk_templates_db(path):
    con = sqlite3.connect(path)
    try:
        con.executescript(_DDL_MODULES)
        con.executescript(_DDL_AUDIT)
        con.commit()
    finally:
        con.close()


class ValidatorTests(unittest.TestCase):
    def test_tm01_good(self):
        self.assertEqual(validate_static(_GOOD), [])

    def test_tm02_key_and_required(self):
        self.assertTrue(any("module_key" in e for e in validate_static(
            {**_GOOD, "module_key": "hat leer"})))
        self.assertTrue(any("module_key" in e for e in validate_static(
            {**_GOOD, "module_key": ""})))
        self.assertTrue(any("title" in e for e in validate_static(
            {**_GOOD, "title": "  "})))
        self.assertTrue(any("topic" in e for e in validate_static(
            {**_GOOD, "topic": ""})))
        self.assertTrue(any("body" in e for e in validate_static(
            {**_GOOD, "body": "   "})))

    def test_tm03_role(self):
        self.assertTrue(any("role" in e for e in validate_static(
            {**_GOOD, "role": "quatsch"})))
        # alle erlaubten Rollen sind gueltig.
        for r in ROLES:
            self.assertEqual(validate_static({**_GOOD, "role": r}), [])

    def test_tm04_placeholder_summary(self):
        s = placeholder_summary(
            "A {{a:x}} und {{auto:y}} sowie {{m:z}} und {{o:w}}.")
        # Reihenfolge des ersten Auftretens: auto, mandatory, optional.
        self.assertEqual(s[0], {"kind": "auto", "count": 2})
        self.assertEqual(s[1], {"kind": "mandatory", "count": 1})
        self.assertEqual(s[2], {"kind": "optional", "count": 1})
        # kein Platzhalter -> leere Liste.
        self.assertEqual(placeholder_summary("nur Text"), [])


class RepoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "templates.db")
        _mk_templates_db(self._db)

    def tearDown(self):
        for root, _d, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
        os.rmdir(self._tmp)

    def test_tm05_upsert_create_and_update(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            repo = ModuleAuthorRepo(con)
            r1 = repo.upsert(_GOOD, changed_by="h004")
            self.assertTrue(r1["created"])
            self.assertEqual(r1["target_id"], "intro.standard")
            row = con.execute("SELECT title, module_key, role FROM report_modules "
                              "WHERE module_key='intro.standard'").fetchone()
            self.assertEqual(row[1], "intro.standard")
            # Update.
            r2 = repo.upsert({**_GOOD, "title": "Neu", "body": "ohne Platzhalter"},
                             changed_by="h004")
            self.assertFalse(r2["created"])
            row2 = con.execute("SELECT title FROM report_modules "
                               "WHERE module_key='intro.standard'").fetchone()
            self.assertEqual(row2[0], "Neu")
            # Genau EINE Zeile (Update, kein zweiter Datensatz).
            self.assertEqual(con.execute("SELECT COUNT(*) FROM report_modules"
                                         ).fetchone()[0], 1)
            # Zwei Audit-Zeilen (create + update), target_type 'module'.
            n = con.execute("SELECT COUNT(*) FROM templates_audit_log "
                            "WHERE target_id='intro.standard' "
                            "AND target_type='module'").fetchone()[0]
            self.assertEqual(n, 2)
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Build 564: module_key an Altzeilen nachtragen.
    # ------------------------------------------------------------------
    def _altzeile(self, con, titel="Alter Baustein"):
        """Eine Zeile wie aus der Zeit vor der Schluessel-Migration:
        vollstaendig, aber module_key IS NULL."""
        con.execute(
            "INSERT INTO report_modules (title, description, role, topic, "
            " body, sort_order, is_active, created_by, created_at, "
            " updated_at, module_key) "
            "VALUES (?, '', 'intro', 'Einleitung', 'Text', 0, 1, "
            "        'alt', 1, 1, NULL)", (titel,))
        return con.execute("SELECT id FROM report_modules WHERE title=?",
                           (titel,)).fetchone()[0]

    def test_tm20_nachtrag_aktualisiert_die_altzeile(self):
        """Der Kern: es darf KEINE zweite Zeile entstehen. Genau das waere
        passiert, wenn man nur das Eingabefeld entsperrt haette - der Upsert
        haette unter dem neuen Schluessel nichts gefunden und eingefuegt."""
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            rid = self._altzeile(con)
            repo = ModuleAuthorRepo(con)
            r = repo.upsert({**_GOOD, "id": rid,
                             "module_key": "alt.nachgetragen"},
                            changed_by="h004")
            self.assertFalse(r["created"])
            self.assertTrue(r["nachtrag"])

            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM report_modules").fetchone()[0], 1,
                "Es ist eine zweite Zeile entstanden.")
            row = con.execute(
                "SELECT module_key, title FROM report_modules WHERE id=?",
                (rid,)).fetchone()
            self.assertEqual(row[0], "alt.nachgetragen")
            self.assertEqual(row[1], _GOOD["title"])
        finally:
            con.close()

    def test_tm21_beleg_nennt_die_zuweisung(self):
        """Ohne diesen Nachweis stuende in der Akte nur 'geaendert' - wer wann
        welchen Schluessel vergeben hat, waere nicht feststellbar."""
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            rid = self._altzeile(con)
            ModuleAuthorRepo(con).upsert(
                {**_GOOD, "id": rid, "module_key": "alt.nachgetragen"},
                changed_by="h004")
            row = con.execute(
                "SELECT old_value, new_value FROM templates_audit_log "
                "WHERE target_id='alt.nachgetragen' AND target_type='module' "
                "ORDER BY id DESC LIMIT 1").fetchone()
            alt_j = json.loads(row[0])
            neu_j = json.loads(row[1])
            self.assertIn("module_key", alt_j)
            self.assertIsNone(alt_j["module_key"])
            self.assertEqual(neu_j["module_key"], "alt.nachgetragen")
        finally:
            con.close()

    def test_tm22_kein_umtragen_eines_vorhandenen_schluessels(self):
        """Der module_key ist eine STABILE Kennung: Berichtsvorlagen verweisen
        ueber ihn. Wanderte er, braeche jede Vorlage - und zwar still."""
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            repo = ModuleAuthorRepo(con)
            repo.upsert(_GOOD, changed_by="h004")
            rid = con.execute(
                "SELECT id FROM report_modules "
                "WHERE module_key='intro.standard'").fetchone()[0]
            with self.assertRaises(ModuleKeyAssignError) as ctx:
                repo.upsert({**_GOOD, "id": rid, "module_key": "ganz.anders"},
                            changed_by="h004")
            self.assertEqual(ctx.exception.feld, "module_key")
            self.assertEqual(con.execute(
                "SELECT module_key FROM report_modules WHERE id=?",
                (rid,)).fetchone()[0], "intro.standard")
        finally:
            con.close()

    def test_tm23_kollision_wird_vor_dem_schreiben_erkannt(self):
        """Der partielle Unique-Index wuerde einen IntegrityError werfen - der
        sagt dem Ausfuellenden nichts. Die Meldung nennt stattdessen, WER den
        Schluessel schon hat."""
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            repo = ModuleAuthorRepo(con)
            repo.upsert(_GOOD, changed_by="h004")
            rid = self._altzeile(con)
            with self.assertRaises(ModuleKeyAssignError) as ctx:
                repo.upsert({**_GOOD, "id": rid,
                             "module_key": "intro.standard"},
                            changed_by="h004")
            self.assertEqual(ctx.exception.feld, "module_key")
            self.assertIn("bereits vergeben", str(ctx.exception))
            self.assertIsNone(con.execute(
                "SELECT module_key FROM report_modules WHERE id=?",
                (rid,)).fetchone()[0])
        finally:
            con.close()

    def test_tm24_unbekannte_id(self):
        con = sqlite3.connect(self._db)
        con.execute("PRAGMA journal_mode=delete")
        try:
            with self.assertRaises(ModuleKeyAssignError) as ctx:
                ModuleAuthorRepo(con).upsert({**_GOOD, "id": 9999},
                                             changed_by="h004")
            self.assertEqual(ctx.exception.feld, "id")
        finally:
            con.close()


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=delete")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, un in ((1, "h001"), (2, "h002")):
            con.execute("INSERT INTO person (id, system_username, display_name,"
                        " is_investigator, is_supervisor, is_support, "
                        "created_at) VALUES (?, ?, ?, 1, 0, 0, ?)",
                        (pid, un, un, now))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.rbac = RbacRepo(con, CoordinatorWriter(con, AuditLog(con)))
        self.rbac.grant("template_editor", "templates.edit", scope="alle",
                        actor_id=1)
        self.rbac.assign_role(1, "template_editor", actor_id=1)

        self._tdb = os.path.join(self._tmp, "templates.db")
        _mk_templates_db(self._tdb)

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

    def _app(self):
        return ManagementApp(self._db, templates_db=self._tdb)

    def _counts(self):
        con = sqlite3.connect("file:%s?mode=ro" % self._tdb, uri=True)
        try:
            r = con.execute("SELECT COUNT(*) FROM report_modules").fetchone()[0]
            a = con.execute("SELECT COUNT(*) FROM templates_audit_log").fetchone()[0]
        finally:
            con.close()
        return r, a

    def test_tm06_list_gated(self):
        self.assertEqual(self._app().dispatch(1, "/api/templates/modules")
                         .status, 200)
        self.assertEqual(self._app().dispatch(2, "/api/templates/modules")
                         .status, 403)

    def test_tm07_create_and_validation(self):
        r = self._app().dispatch_write(1, "/api/templates/module", dict(_GOOD))
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["created"])
        self.assertEqual(d["target_id"], "intro.standard")
        lst = json.loads(self._app().dispatch(1, "/api/templates/modules")
                         .body.decode("utf-8"))
        self.assertEqual(lst["count"], 1)
        self.assertEqual(self._counts(), (1, 1))
        # ungueltige Rolle -> 400.
        bad = {**_GOOD, "module_key": "x.y", "role": "quatsch"}
        r2 = self._app().dispatch_write(1, "/api/templates/module", bad)
        self.assertEqual(r2.status, 400)
        self.assertEqual(json.loads(r2.body.decode("utf-8"))["error"],
                         "validation")
        self.assertEqual(self._counts(), (1, 1))

    # ------------------------------------------------------------------
    # Build 564: der HTTP-Vertrag, auf den die Maske aufbaut.
    # ------------------------------------------------------------------
    def _altzeile_http(self, titel="Alter Baustein"):
        con = sqlite3.connect(self._tdb)
        try:
            con.execute(
                "INSERT INTO report_modules (title, description, role, topic, "
                " body, sort_order, is_active, created_by, created_at, "
                " updated_at, module_key) "
                "VALUES (?, '', 'intro', 'Einleitung', 'Text', 0, 1, 'alt', "
                "        1, 1, NULL)", (titel,))
            con.commit()
            return con.execute("SELECT id FROM report_modules WHERE title=?",
                               (titel,)).fetchone()[0]
        finally:
            con.close()

    def test_tm25_http_nachtrag_und_feldangabe(self):
        rid = self._altzeile_http()
        app = self._app()

        r = app.dispatch_write(1, "/api/templates/module",
                               {**_GOOD, "id": rid,
                                "module_key": "alt.nachgetragen"})
        self.assertEqual(r.status, 200, r.body)
        b = json.loads(r.body.decode("utf-8"))
        self.assertTrue(b["nachtrag"])
        self.assertFalse(b["created"])

        # Ein zweiter Versuch traegt jetzt einen Schluessel -> 400 MIT Feld,
        # nicht 500. Die Maske braucht das Feld, um es zu markieren.
        r2 = app.dispatch_write(1, "/api/templates/module",
                                {**_GOOD, "id": rid,
                                 "module_key": "noch.anders"})
        self.assertEqual(r2.status, 400, r2.body)
        b2 = json.loads(r2.body.decode("utf-8"))
        self.assertEqual(b2["feld"], "module_key")

    def test_tm26_dryrun_prueft_den_nachtrag_mit(self):
        """Sonst saehe die Vorschau gruen aus und das Speichern schluege fehl -
        der Ausfuellende haette die Vorschau umsonst gemacht."""
        app = self._app()
        app.dispatch_write(1, "/api/templates/module", dict(_GOOD))
        rid = self._altzeile_http("Zweiter Alter")

        r = app.dispatch_write(1, "/api/templates/module/dryrun",
                               {**_GOOD, "id": rid,
                                "module_key": "intro.standard"})
        self.assertEqual(r.status, 200, r.body)
        b = json.loads(r.body.decode("utf-8"))
        self.assertFalse(b["ok"])
        self.assertTrue(any("bereits vergeben" in e for e in b["errors"]),
                        b["errors"])

        # Und der Dry-Run bleibt SCHREIBFREI: die Altzeile hat weiterhin
        # keinen Schluessel.
        con = sqlite3.connect(self._tdb)
        try:
            self.assertIsNone(con.execute(
                "SELECT module_key FROM report_modules WHERE id=?",
                (rid,)).fetchone()[0])
        finally:
            con.close()

    def test_tm08_dryrun_is_write_free(self):
        self.assertEqual(self._counts(), (0, 0))
        r = self._app().dispatch_write(
            1, "/api/templates/module/dryrun", dict(_GOOD))
        self.assertEqual(r.status, 200)
        d = json.loads(r.body.decode("utf-8"))
        self.assertTrue(d["ok"])
        self.assertEqual(d["errors"], [])
        kinds = [s["kind"] for s in d["summary"]]
        self.assertIn("auto", kinds)
        self.assertIn("mandatory", kinds)
        self.assertEqual(self._counts(), (0, 0))
        # Fehlerfall als Daten (ok False, 200), nichts geschrieben.
        bad = {**_GOOD, "body": "   "}
        r2 = self._app().dispatch_write(
            1, "/api/templates/module/dryrun", bad)
        self.assertEqual(r2.status, 200)
        d2 = json.loads(r2.body.decode("utf-8"))
        self.assertFalse(d2["ok"])
        self.assertTrue(len(d2["errors"]) >= 1)
        self.assertEqual(self._counts(), (0, 0))
        # ohne Recht 403.
        self.assertEqual(self._app().dispatch_write(
            2, "/api/templates/module/dryrun", dict(_GOOD)).status, 403)


if __name__ == "__main__":
    unittest.main()


# =============================================================================
# Build 654 (Ticket 4b032177) — GET /api/validation/rules
#
# Die Platzhalter-Tabelle der Baustein-Module braucht den Katalog der
# BENANNTEN Formatregeln (config.yaml -> validation.rules). Seit Build 388
# traegt das fuenfte Platzhalterfeld ENTWEDER eine Base64-Regex (Altform)
# ODER einen Verweis 'rule:<name>' in genau diesen Katalog. Der
# Ermittlerserver liefert ihn unter /_forensic/validation_rules aus; der
# Verwaltungsserver hatte dafuer bisher keine Route.
#
# VR01 — die Route liefert den Katalog und ist auf templates.edit gegated.
# VR02 — es ist DERSELBE Katalog wie der des Ermittlerservers (dieselbe
#        Quelle, dasselbe Format). Zwei Wahrheitsquellen waeren genau das,
#        wovor der Kopf von core/validation_rules.py warnt.
# =============================================================================
class ValidationRulesEndpointTests(EndpointTests):
    """Erbt Aufbau und Abbau von EndpointTests (Person 1 darf, Person 2 nicht)."""

    def test_vr01_katalog_und_recht(self):
        r = self._app().dispatch(1, "/api/validation/rules")
        self.assertEqual(r.status, 200, r.body)
        d = json.loads(r.body.decode("utf-8"))
        self.assertIn("rules", d)
        self.assertIn("count", d)
        self.assertEqual(d["count"], len(d["rules"]))
        # Jede Regel traegt genau die drei Felder, die der Browser braucht -
        # das kompilierte Muster wird bewusst NICHT uebertragen.
        for name, spec in d["rules"].items():
            self.assertEqual(sorted(spec.keys()),
                             ["hint", "pattern", "transform"],
                             "Regel %r hat ein unerwartetes Feld" % name)

        # Ohne templates.edit: 403, nicht etwa ein leerer Katalog. Ein
        # leerer Katalog waere von 'keine Rechte' nicht zu unterscheiden.
        self.assertEqual(self._app().dispatch(2, "/api/validation/rules")
                         .status, 403)

    def test_vr02_dieselbe_quelle_wie_der_ermittlerserver(self):
        from core.config_loader import ConfigLoader
        from core.validation_rules import ValidationRules

        erwartet = ValidationRules(ConfigLoader()).as_public_dict()
        d = json.loads(self._app().dispatch(1, "/api/validation/rules")
                       .body.decode("utf-8"))
        # ZEICHENGLEICH. Wer hier eine eigene Aufbereitung einzieht, laesst
        # Verwaltungs- und Ermittlerserver auseinanderlaufen - und ein
        # Redakteur saehe in der Maske ein anderes Muster als das, gegen das
        # der Server am Ende prueft.
        self.assertEqual(d["rules"], erwartet)
