# =============================================================================
# tests/test_evidence_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite fuer db/evidence_db.py
#
# T01 — Schema wird beim Init angelegt (Tabellen existieren nach Init)
# T02 — log_page_visit() speichert Eintrag korrekt
# T03 — log_page_visit() mit explizitem Timestamp
# T04 — get_page_visits() gibt Besuche einer URL zurueck
# T05 — save_viewport_event() speichert Event korrekt
# T06 — save_viewport_event(): ts_leave < ts_enter -> EvidenceDbError
# T07 — save_viewport_event(): visible_ms < 0 -> EvidenceDbError
# T08 — save_viewport_batch() speichert mehrere Events
# T09 — save_viewport_batch(): ungueltige Events werden uebersprungen
# T10 — save_annotation(): alle sechs Kategorien akzeptiert
# T11 — save_annotation(): ungueltige Kategorie -> EvidenceDbError
# T12 — get_annotations() gibt Annotationen einer URL zurueck
# T13 — get_all_annotations() gibt alle Annotationen zurueck
# T14 — annotation_count() korrekt
# T15 — Init ist idempotent (mehrfaches Anlegen des Schemas kein Fehler)
# --- Baustelle 3 — Build 011: neue Felder ---
# T16 — annotations-Tabelle enthaelt alle Baustelle-3-Spalten
# T17 — save_annotation(): selection_json korrekt gespeichert/gelesen
# T18 — save_annotation(): tags_json korrekt gespeichert/gelesen
# T19 — save_annotation(): local_id korrekt gespeichert/gelesen
# T20 — save_annotation(): post_id korrekt gespeichert/gelesen
# T21 — save_annotation(): created_by korrekt gespeichert/gelesen
# T22 — alle neuen Felder kombinierbar in einer Annotation
# T23 — neue Felder sind None/'' wenn nicht uebergeben (Rueckwaertskompatibilitaet)
# T24 — _migrate_schema() ergaenzt fehlende Spalten in einer alten DB
# T25 — _migrate_schema() ist idempotent
# T26 — get_all_annotations() liefert neue Felder korrekt zurueck
#
# Version: v0.6.089 · Build: 089 · 2026-05-05
# Geaendert Build 089: T01 auf B6-Schema aktualisiert.
# Geaendert Build 089: T16-T26 (alte Editor.js-Tests) entfernt — B6-Schema-Tests folgen in test_evidence_db_b6.py
# Beleg: Bauplan B6 v0.3 §2.3, Ausdefinitionsgespraech 2026-05-05 · 2026-04-19
# Beleg: AP-E1, Projektgespraech 2026-04-19
# =============================================================================

import sys, os, sqlite3, tempfile, textwrap, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import setup_logging, reset_for_testing
from core.config_loader import ConfigLoader
from db.evidence_db import EvidenceDb, EvidenceDbError, VALID_CATEGORIES


def _setup_test_logging():
    reset_for_testing()
    tmp = tempfile.mkdtemp()
    config_path = os.path.join(tmp, "config.yaml")
    with open(config_path, "w") as fh:
        fh.write(textwrap.dedent(f"""
            logging:
              level: "debug"
              logfile: "{os.path.join(tmp, 'logs', 'test.log')}"
              max_bytes: 1048576
              backup_count: 2
            paths:
              coordinator_db: "./c.db"
              forensic_db_dir: "./f/"
              default_db: "./d.db"
              evidence_db_dir: "./e/"
        """))
    setup_logging(ConfigLoader(config_path=config_path))


class TestEvidenceDb(unittest.TestCase):
    def setUp(self):
        _setup_test_logging()
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.edb = EvidenceDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()

    def test_T01_schema_angelegt(self):
        """T01: Tabellen werden beim Init angelegt."""
        tables = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        self.assertIn("page_visits", tables)
        self.assertIn("viewport_events", tables)
        self.assertIn("annotations", tables)
        # AP-E1: reports, report_approvals (unveraendert)
        self.assertIn("reports", tables)
        self.assertIn("report_approvals", tables)
        # B6 Phase 1: Berichts-Tabellen (Build 099 -- report_blocks statt report_paragraphs)
        # Beleg: Bauplan B6 v0.5 §2.3, Projektgespraech 2026-05-06
        self.assertIn("report_blocks", tables)
        self.assertIn("report_block_order", tables)
        self.assertIn("report_anchors", tables)
        self.assertIn("report_comments", tables)
        self.assertIn("placeholder_cache", tables)
        self.assertIn("lock_takeover_requests", tables)
        # AP-E1 entfernt: block_evidence_user, report_templates
        # B6 v0.3 entfernt: report_paragraphs (Phase 1)

    def test_T02_log_page_visit(self):
        """T02: log_page_visit() speichert Eintrag korrekt."""
        row_id = self.edb.log_page_visit(
            "/forum/viewtopic.php?id=100", "user", investigator_id=1
        )
        self.assertIsInstance(row_id, int)
        self.assertGreater(row_id, 0)
        rows = self.con.execute("SELECT * FROM page_visits").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["page_url"], "/forum/viewtopic.php?id=100")
        self.assertEqual(rows[0]["scrape_context"], "user")
        self.assertEqual(rows[0]["investigator_id"], 1)

    def test_T03_log_page_visit_timestamp(self):
        """T03: Expliziter Timestamp wird korrekt gespeichert."""
        ts = 1700000042
        self.edb.log_page_visit("/forum/test", "investigator", ts=ts)
        row = self.con.execute("SELECT ts FROM page_visits").fetchone()
        self.assertEqual(row["ts"], ts)

    def test_T04_get_page_visits(self):
        """T04: get_page_visits() gibt Besuche einer URL zurueck."""
        url = "/forum/viewtopic.php?id=55"
        self.edb.log_page_visit(url, "user", ts=1000)
        self.edb.log_page_visit(url, "user", ts=2000)
        self.edb.log_page_visit("/forum/other", "user", ts=3000)
        visits = self.edb.get_page_visits(url)
        self.assertEqual(len(visits), 2)
        self.assertEqual(visits[0].ts, 1000)
        self.assertEqual(visits[1].ts, 2000)

    def test_T05_save_viewport_event(self):
        """T05: save_viewport_event() speichert Event korrekt."""
        row_id = self.edb.save_viewport_event(
            page_url="/forum/viewtopic.php?id=1",
            element_id="p12345",
            visible_ms=3500,
            ts_enter=1700000000000,
            ts_leave=1700000003500,
            investigator_id=2,
        )
        self.assertGreater(row_id, 0)
        row = self.con.execute("SELECT * FROM viewport_events").fetchone()
        self.assertEqual(row["element_id"], "p12345")
        self.assertEqual(row["visible_ms"], 3500)

    def test_T06_viewport_ts_leave_vor_enter(self):
        """T06: ts_leave < ts_enter -> EvidenceDbError."""
        with self.assertRaises(EvidenceDbError):
            self.edb.save_viewport_event(
                "/forum/x", "p1", 0, ts_enter=2000, ts_leave=1000
            )

    def test_T07_viewport_visible_ms_negativ(self):
        """T07: visible_ms < 0 -> EvidenceDbError."""
        with self.assertRaises(EvidenceDbError):
            self.edb.save_viewport_event(
                "/forum/x", "p1", -1, ts_enter=1000, ts_leave=2000
            )

    def test_T08_viewport_batch(self):
        """T08: save_viewport_batch() speichert mehrere Events."""
        events = [
            {"page_url": "/forum/x", "element_id": "p1",
             "visible_ms": 100, "ts_enter": 1000, "ts_leave": 1100},
            {"page_url": "/forum/x", "element_id": "p2",
             "visible_ms": 200, "ts_enter": 1200, "ts_leave": 1400},
            {"page_url": "/forum/x", "element_id": "p3",
             "visible_ms": 300, "ts_enter": 1500, "ts_leave": 1800},
        ]
        count = self.edb.save_viewport_batch(events, investigator_id=1)
        self.assertEqual(count, 3)
        total = self.con.execute(
            "SELECT COUNT(*) FROM viewport_events"
        ).fetchone()[0]
        self.assertEqual(total, 3)

    def test_T09_viewport_batch_ungueltige_uebersprungen(self):
        """T09: Ungueltige Events im Batch werden uebersprungen."""
        events = [
            {"page_url": "/forum/x", "element_id": "p1",
             "visible_ms": 100, "ts_enter": 1000, "ts_leave": 1100},
            {"page_url": "/forum/x", "element_id": "p2",
             "visible_ms": -5, "ts_enter": 1000, "ts_leave": 1100},
        ]
        count = self.edb.save_viewport_batch(events)
        self.assertEqual(count, 1)

    def test_T10_alle_kategorien_akzeptiert(self):
        """T10: Alle sechs VALID_CATEGORIES werden akzeptiert."""
        for cat in VALID_CATEGORIES:
            row_id = self.edb.save_annotation(
                page_url=f"/forum/{cat}", category=cat, text=f"Test {cat}",
            )
            self.assertGreater(row_id, 0)
        self.assertEqual(self.edb.annotation_count(), len(VALID_CATEGORIES))

    def test_T11_ungueltige_kategorie(self):
        """T11: Ungueltige Kategorie -> EvidenceDbError."""
        with self.assertRaises(EvidenceDbError):
            self.edb.save_annotation("/forum/x", category="CAT_INVALID", text="test")

    def test_T12_get_annotations(self):
        """T12: get_annotations() gibt Annotationen einer URL zurueck."""
        url = "/forum/viewtopic.php?id=77"
        self.edb.save_annotation(url, "CAT_PERSON", "Name erwaehnt", ts=1000)
        self.edb.save_annotation(url, "CAT_176", "Relevanter Inhalt", ts=2000)
        self.edb.save_annotation("/forum/other", "CAT_OTHER", "Nichts", ts=3000)
        anns = self.edb.get_annotations(url)
        self.assertEqual(len(anns), 2)
        self.assertEqual(anns[0].category, "CAT_PERSON")
        self.assertEqual(anns[1].category, "CAT_176")

    def test_T13_get_all_annotations(self):
        """T13: get_all_annotations() gibt alle Annotationen zurueck."""
        self.edb.save_annotation("/forum/a", "CAT_PERSON", "A")
        self.edb.save_annotation("/forum/b", "CAT_184", "B")
        all_anns = self.edb.get_all_annotations()
        self.assertEqual(len(all_anns), 2)

    def test_T14_annotation_count(self):
        """T14: annotation_count() gibt korrekte Anzahl zurueck."""
        self.assertEqual(self.edb.annotation_count(), 0)
        self.edb.save_annotation("/forum/x", "CAT_OTHER", "test")
        self.assertEqual(self.edb.annotation_count(), 1)

    def test_T15_schema_idempotent(self):
        """T15: Mehrfaches Anlegen des Schemas wirft keine Exception."""
        EvidenceDb(self.con)
        EvidenceDb(self.con)

    def test_T16_neue_spalten_im_schema(self):
        """T16: annotations-Tabelle enthaelt alle Baustelle-3-Spalten."""
        cols = {r[1] for r in self.con.execute(
            "PRAGMA table_info(annotations)"
        ).fetchall()}
        for expected in (
            "selection_json", "tags_json", "local_id", "post_id", "created_by"
        ):
            self.assertIn(expected, cols,
                msg=f"Spalte '{expected}' fehlt in annotations")

    def test_T17_save_annotation_mit_selection_json(self):
        """T17: selection_json wird korrekt gespeichert und zurueckgelesen."""
        import json
        sel = {
            "xpathStart": "//article[1]/p[1]", "offsetStart": 5,
            "xpathEnd": "//article[1]/p[1]", "offsetEnd": 20,
            "textContent": "BirnenKenner99",
        }
        self.edb.save_annotation(
            page_url="/forum/viewtopic.php?id=42",
            category="CAT_PERSON",
            text="Benutzername gefunden",
            selection_json=json.dumps(sel),
        )
        anns = self.edb.get_annotations("/forum/viewtopic.php?id=42")
        self.assertEqual(len(anns), 1)
        restored = json.loads(anns[0].selection_json)
        self.assertEqual(restored["textContent"], "BirnenKenner99")
        self.assertEqual(restored["offsetStart"], 5)

    def test_T18_save_annotation_mit_tags_json(self):
        """T18: tags_json wird korrekt gespeichert und zurueckgelesen."""
        import json
        tags = ["pgp", "username", "email"]
        self.edb.save_annotation(
            page_url="/forum/viewtopic.php?id=43",
            category="CAT_PERSON",
            text="Mehrere Identifikatoren",
            tags_json=json.dumps(tags),
        )
        anns = self.edb.get_annotations("/forum/viewtopic.php?id=43")
        self.assertIsNotNone(anns[0].tags_json)
        self.assertEqual(json.loads(anns[0].tags_json), ["pgp", "username", "email"])

    def test_T19_save_annotation_mit_local_id(self):
        """T19: local_id wird gespeichert und zurueckgelesen."""
        local_id = "550e8400-e29b-41d4-a716-446655440000"
        self.edb.save_annotation(
            "/forum/viewtopic.php?id=44", "CAT_OTHER", "", local_id=local_id,
        )
        anns = self.edb.get_annotations("/forum/viewtopic.php?id=44")
        self.assertEqual(anns[0].local_id, local_id)

    def test_T20_save_annotation_mit_post_id(self):
        """T20: post_id wird gespeichert und zurueckgelesen."""
        self.edb.save_annotation(
            "/forum/viewtopic.php?id=45", "CAT_176",
            "Ganzer Post markiert", element_id="p98765", post_id=98765,
        )
        anns = self.edb.get_annotations("/forum/viewtopic.php?id=45")
        self.assertEqual(anns[0].post_id, 98765)
        self.assertIsNone(anns[0].selection_json)

    def test_T21_save_annotation_mit_created_by(self):
        """T21: created_by wird gespeichert und zurueckgelesen."""
        self.edb.save_annotation(
            "/forum/viewtopic.php?id=46", "CAT_LOCATION",
            "Stadtname erwaehnt", created_by="h012345",
        )
        anns = self.edb.get_annotations("/forum/viewtopic.php?id=46")
        self.assertEqual(anns[0].created_by, "h012345")

    def test_T22_save_annotation_alle_neuen_felder(self):
        """T22: Alle neuen Felder kombinierbar."""
        import json
        sel = {"xpathStart": "//p", "offsetStart": 0,
               "xpathEnd": "//p", "offsetEnd": 5, "textContent": "Hallo"}
        self.edb.save_annotation(
            page_url="/forum/viewtopic.php?id=47",
            category="CAT_VICTIM",
            text="Opferhinweis",
            element_id="p55555",
            selection_json=json.dumps(sel),
            tags_json=json.dumps(["opfer", "alter"]),
            local_id="aaaabbbb-cccc-dddd-eeee-ffffffffffff",
            post_id=None,
            created_by="h099999",
        )
        anns = self.edb.get_annotations("/forum/viewtopic.php?id=47")
        ann = anns[0]
        self.assertEqual(ann.category, "CAT_VICTIM")
        self.assertEqual(ann.created_by, "h099999")
        self.assertEqual(ann.local_id, "aaaabbbb-cccc-dddd-eeee-ffffffffffff")
        self.assertIsNone(ann.post_id)
        self.assertIn("opfer", json.loads(ann.tags_json))

    def test_T23_neue_felder_default_none(self):
        """T23: Neue Felder sind None wenn nicht uebergeben."""
        self.edb.save_annotation(
            "/forum/viewtopic.php?id=48", "CAT_OTHER",
            "Einfache Annotation ohne neue Felder",
        )
        anns = self.edb.get_annotations("/forum/viewtopic.php?id=48")
        ann = anns[0]
        self.assertIsNone(ann.selection_json)
        self.assertIsNone(ann.tags_json)
        self.assertIsNone(ann.local_id)
        self.assertIsNone(ann.post_id)
        self.assertEqual(ann.created_by, "")

    def test_T24_migration_aeltere_db(self):
        """T24: _migrate_schema() ergaenzt fehlende Spalten in einer alten DB."""
        old_con = sqlite3.connect(":memory:")
        old_con.row_factory = sqlite3.Row
        old_con.executescript("""
            CREATE TABLE IF NOT EXISTS annotations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                page_url        TEXT NOT NULL,
                element_id      TEXT,
                category        TEXT NOT NULL,
                text            TEXT NOT NULL DEFAULT '',
                ts              INTEGER NOT NULL,
                investigator_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS page_visits (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                page_url        TEXT NOT NULL,
                scrape_context  TEXT NOT NULL,
                ts              INTEGER NOT NULL,
                investigator_id INTEGER
            );
            CREATE TABLE IF NOT EXISTS viewport_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                page_url        TEXT NOT NULL,
                element_id      TEXT,
                visible_ms      INTEGER NOT NULL,
                ts_enter        INTEGER NOT NULL,
                ts_leave        INTEGER NOT NULL,
                investigator_id INTEGER
            );
        """)
        old_con.commit()
        migrated_edb = EvidenceDb(old_con)
        # Eintrag NACH EvidenceDb-Init einfuegen (Schema v2.0 dropt+recreated alle Tabellen)
        old_con.execute(
            "INSERT INTO annotations (page_url, category, text, ts) "
            "VALUES ('/forum/old', 'CAT_OTHER', 'alter Eintrag', 1700000000)"
        )
        old_con.commit()
        cols = {r[1] for r in old_con.execute(
            "PRAGMA table_info(annotations)"
        ).fetchall()}
        # Alle Migrationsspalten prüfen — inkl. Build 178
        for expected in (
            "selection_json", "tags_json", "local_id", "post_id", "created_by",
            "deleted_at", "version_nr", "prev_id",
        ):
            self.assertIn(expected, cols,
                msg=f"Migration: Spalte '{expected}' fehlt")
        anns = migrated_edb.get_annotations("/forum/old")
        self.assertEqual(len(anns), 1)
        self.assertEqual(anns[0].text, "alter Eintrag")
        self.assertIsNone(anns[0].selection_json)
        self.assertEqual(anns[0].created_by, "")
        # Build 178: neue Felder haben Standardwerte
        self.assertIsNone(anns[0].deleted_at)
        self.assertEqual(anns[0].version_nr, 1)
        self.assertIsNone(anns[0].prev_id)
        old_con.close()

    def test_T25_migration_idempotent(self):
        """T25: _migrate_schema() auf bereits migrierter DB wirft keine Exception."""
        EvidenceDb(self.con)
        EvidenceDb(self.con)

    def test_T26_get_all_annotations_neue_felder(self):
        """T26: get_all_annotations() liefert neue Felder korrekt zurueck."""
        import json
        self.edb.save_annotation(
            "/forum/a", "CAT_PERSON", "Notiz A",
            tags_json=json.dumps(["username"]), created_by="h001",
        )
        self.edb.save_annotation(
            "/forum/b", "CAT_184", "Notiz B",
            post_id=12345, created_by="h002",
        )
        all_anns = self.edb.get_all_annotations()
        self.assertEqual(len(all_anns), 2)
        ann_a = next(a for a in all_anns if a.page_url == "/forum/a")
        ann_b = next(a for a in all_anns if a.page_url == "/forum/b")
        self.assertEqual(json.loads(ann_a.tags_json), ["username"])
        self.assertEqual(ann_a.created_by, "h001")
        self.assertEqual(ann_b.post_id, 12345)
        self.assertEqual(ann_b.created_by, "h002")

    # -----------------------------------------------------------------------
    # delete_annotation() — OP-KN-9, Build 059
    # T59f — delete_annotation(): bekannte ID → True, Annotation nicht mehr abrufbar
    # T59g — delete_annotation(): unbekannte ID → False, kein Fehler
    # T59h — delete_annotation(): andere Annotations bleiben erhalten (kein Kollateral)
    # -----------------------------------------------------------------------

    def test_T59f_delete_annotation_bekannte_id(self):
        """T59f: delete_annotation() mit bekannter ID → True, Annotation weg."""
        ann_id = self.edb.save_annotation(
            "/forum/viewtopic.php?id=1", "CAT_PERSON", "Zu löschen"
        )
        # Vor dem Löschen: muss abrufbar sein
        before = self.edb.get_annotations("/forum/viewtopic.php?id=1")
        self.assertEqual(len(before), 1)

        result = self.edb.delete_annotation(ann_id)
        self.assertTrue(result, "delete_annotation() muss True zurückgeben bei bekannter ID")

        # Nach dem Löschen: nicht mehr abrufbar
        after = self.edb.get_annotations("/forum/viewtopic.php?id=1")
        self.assertEqual(len(after), 0,
            "Annotation muss nach delete_annotation() aus DB verschwunden sein")

    def test_T59g_delete_annotation_unbekannte_id(self):
        """T59g: delete_annotation() mit nicht existierender ID → False, kein Fehler."""
        result = self.edb.delete_annotation(99999)
        self.assertFalse(result,
            "delete_annotation() muss False zurückgeben wenn ID nicht existiert")

    def test_T59h_delete_annotation_kein_kollateral(self):
        """T59h: delete_annotation() löscht nur die Ziel-Annotation, nicht andere."""
        id1 = self.edb.save_annotation("/forum/a", "CAT_PERSON", "Bleibt")
        id2 = self.edb.save_annotation("/forum/a", "CAT_176",   "Wird gelöscht")
        id3 = self.edb.save_annotation("/forum/b", "CAT_OTHER", "Auch erhalten")

        self.edb.delete_annotation(id2)

        remaining = self.edb.get_all_annotations()
        remaining_ids = [a.id for a in remaining]
        self.assertIn(id1, remaining_ids, "Annotation id1 muss erhalten bleiben")
        self.assertIn(id3, remaining_ids, "Annotation id3 muss erhalten bleiben")
        self.assertNotIn(id2, remaining_ids, "Annotation id2 muss gelöscht sein")
        self.assertEqual(len(remaining), 2)


# ===========================================================================
# Build 178 — Bug 2.75: Soft-Delete + Append-only-Log
# T61 — delete_annotation() setzt deleted_at, kein physisches Löschen
# T62 — get_annotations() liefert nur aktive (deleted_at IS NULL)
# T63 — save_annotation() erzeugt neue Version, Vorgänger bekommt deleted_at
# T64 — restore_annotation() stellt gelöschte Annotation wieder her
# ===========================================================================
class TestSoftDeleteBuild178(unittest.TestCase):
    """T61–T64: Soft-Delete + Append-only-Log (Build 178 — Bug 2.75)."""

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.edb = EvidenceDb(self.con)

    def tearDown(self):
        self.con.close()

    def test_T61_soft_delete_setzt_deleted_at(self):
        """T61: delete_annotation() setzt deleted_at, physischer Datensatz bleibt.
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        ann_id = self.edb.save_annotation(
            "/forum/x", "CAT_OTHER", "Testnotiz", local_id="uuid-t61"
        )
        self.assertTrue(self.edb.delete_annotation(ann_id))

        # Datensatz physisch noch vorhanden
        row = self.con.execute(
            "SELECT deleted_at FROM annotations WHERE id = ?", (ann_id,)
        ).fetchone()
        self.assertIsNotNone(row, "Datensatz muss physisch noch existieren")
        self.assertIsNotNone(row["deleted_at"], "deleted_at muss gesetzt sein")

        # get_annotations() liefert ihn nicht mehr
        anns = self.edb.get_annotations("/forum/x")
        self.assertEqual(len(anns), 0, "Gelöschte Annotation darf nicht in get_annotations erscheinen")

    def test_T62_annotation_count_nur_aktive(self):
        """T62: annotation_count() zählt nur aktive Annotationen.
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        id1 = self.edb.save_annotation("/forum/x", "CAT_OTHER", "A", local_id="uuid-t62a")
        id2 = self.edb.save_annotation("/forum/x", "CAT_OTHER", "B", local_id="uuid-t62b")
        self.assertEqual(self.edb.annotation_count(), 2)
        self.edb.delete_annotation(id1)
        self.assertEqual(self.edb.annotation_count(), 1)

    def test_T63_save_annotation_append_only(self):
        """T63: save_annotation() mit existierender local_id erzeugt neuen Datensatz.
        Vorgänger bekommt deleted_at gesetzt (changed_at-Semantik).
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        local_id = "uuid-t63"
        id_v1 = self.edb.save_annotation(
            "/forum/x", "CAT_OTHER", "Version 1", local_id=local_id
        )
        id_v2 = self.edb.save_annotation(
            "/forum/x", "CAT_OTHER", "Version 2", local_id=local_id
        )

        # Zwei verschiedene Datensätze
        self.assertNotEqual(id_v1, id_v2, "Neue Version muss neuen Datensatz erzeugen")

        # Vorgänger hat deleted_at gesetzt (changed_at)
        row_v1 = self.con.execute(
            "SELECT deleted_at, version_nr FROM annotations WHERE id = ?", (id_v1,)
        ).fetchone()
        self.assertIsNotNone(row_v1["deleted_at"], "Vorgänger muss deleted_at haben")
        self.assertEqual(row_v1["version_nr"], 1)

        # Nachfolger ist aktiv mit version_nr=2 und prev_id=id_v1
        row_v2 = self.con.execute(
            "SELECT deleted_at, version_nr, prev_id FROM annotations WHERE id = ?", (id_v2,)
        ).fetchone()
        self.assertIsNone(row_v2["deleted_at"], "Neue Version muss aktiv sein")
        self.assertEqual(row_v2["version_nr"], 2)
        self.assertEqual(row_v2["prev_id"], id_v1)

        # get_annotations() liefert nur Version 2
        anns = self.edb.get_annotations("/forum/x")
        self.assertEqual(len(anns), 1)
        self.assertEqual(anns[0].text, "Version 2")

    def test_T64_restore_annotation(self):
        """T64: restore_annotation() stellt gelöschte Annotation wieder her.
        Vorgängerversionen (mit Nachfolger) können nicht wiederhergestellt werden.
        Beleg: Projektgespräch 2026-05-12 — Bug 2.75 (BS3).
        """
        local_id = "uuid-t64"
        id_v1 = self.edb.save_annotation(
            "/forum/x", "CAT_OTHER", "Version 1", local_id=local_id
        )
        # Löschen
        self.edb.delete_annotation(id_v1)
        self.assertEqual(len(self.edb.get_annotations("/forum/x")), 0)

        # Wiederherstellen
        self.assertTrue(self.edb.restore_annotation(id_v1))
        anns = self.edb.get_annotations("/forum/x")
        self.assertEqual(len(anns), 1)
        self.assertEqual(anns[0].text, "Version 1")

        # Vorgänger einer aktiven Version kann NICHT wiederhergestellt werden
        id_v2 = self.edb.save_annotation(
            "/forum/x", "CAT_OTHER", "Version 2", local_id=local_id
        )
        # id_v1 ist jetzt Vorgänger von id_v2 → nicht wiederherstellbar
        self.assertFalse(
            self.edb.restore_annotation(id_v1),
            "Vorgängerversion darf nicht wiederhergestellt werden"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestVersionsketteVorwaerts(unittest.TestCase):
    """
    Build 749 - get_current_annotation: von einer alten Nummer zur aktuellen.

    ALEX' BEFUND vom 31.08.2026: Ein Bericht, der eine inzwischen geaenderte
    Annotation fuehrt, wies den Beleg als 'nicht mehr vorhanden' aus. Er war
    aber vorhanden, nur unter einer neuen Nummer: save_annotation legt bei
    einer Aenderung einen NEUEN Datensatz an (version_nr+1, prev_id =
    Vorgaenger.id) und setzt beim Vorgaenger deleted_at.

    get_annotation_history laeuft RUECKWAERTS zum Ersteintrag. Diese Tests
    pruefen das Spiegelbild: vorwaerts bis zur aktuellen Fassung.

    EV50  eine ersetzte Nummer fuehrt zur aktuellen Fassung
    EV51  eine mehrgliedrige Kette wird ganz durchlaufen
    EV52  eine bereits aktuelle Nummer liefert sich selbst, Kette einelementig
    EV53  GEGENPROBE: wirklich geloescht (kein Nachfolger) liefert None -
          sonst verschwaende eine echte Loeschung aus dem Bericht
    EV54  eine unbekannte Nummer liefert None und eine LEERE Kette - das
          unterscheidet 'gibt es nicht' von 'geloescht'
    EV55  ein Zyklus laesst den Aufruf nicht haengen
    """

    def setUp(self):
        _setup_test_logging()
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.edb = EvidenceDb(self.con)

    def tearDown(self):
        self.con.close()
        reset_for_testing()

    def _speichere(self, text, local_id="m1"):
        return self.edb.save_annotation(
            page_url="/forum/viewtopic.php?id=1", category="CAT_LOCATION",
            text=text, local_id=local_id, created_by="mc")

    def test_EV50_ersetzte_nummer_fuehrt_zur_aktuellen_fassung(self):
        alt = self._speichere("erste Fassung")
        neu = self._speichere("zweite Fassung")
        self.assertNotEqual(alt, neu, "eine Aenderung ergibt eine neue Nummer")
        rec, kette = self.edb.get_current_annotation(alt)
        self.assertIsNotNone(rec)
        self.assertEqual(neu, rec.id)
        self.assertEqual("zweite Fassung", rec.text)
        self.assertEqual([alt, neu], kette)

    def test_EV51_mehrgliedrige_kette_wird_ganz_durchlaufen(self):
        a = self._speichere("v1")
        b = self._speichere("v2")
        c = self._speichere("v3")
        rec, kette = self.edb.get_current_annotation(a)
        self.assertEqual(c, rec.id)
        self.assertEqual("v3", rec.text)
        self.assertEqual([a, b, c], kette)
        # Auch von der Mitte aus - ein Bericht kann jede Fassung fuehren.
        rec2, kette2 = self.edb.get_current_annotation(b)
        self.assertEqual(c, rec2.id)
        self.assertEqual([b, c], kette2)

    def test_EV52_aktuelle_nummer_liefert_sich_selbst(self):
        ident = self._speichere("nur eine Fassung")
        rec, kette = self.edb.get_current_annotation(ident)
        self.assertEqual(ident, rec.id)
        self.assertEqual([ident], kette)

    def test_EV53_gegenprobe_wirklich_geloescht_liefert_none(self):
        # OHNE DIESE PROBE waere EV50 auch mit einer Fassung gruen, die jede
        # Nummer irgendwie aufloest - und dann verschwaende eine echte
        # Loeschung aus dem Bericht.
        ident = self._speichere("wird geloescht")
        self.edb.delete_annotation(ident)
        rec, kette = self.edb.get_current_annotation(ident)
        self.assertIsNone(rec)
        # Die Kette ist NICHT leer: die Nummer gibt es, sie ist nur beendet.
        self.assertEqual([ident], kette)

    def test_EV54_unbekannte_nummer_hat_eine_leere_kette(self):
        # 'gibt es nicht' und 'geloescht' sind zwei verschiedene Auskuenfte.
        rec, kette = self.edb.get_current_annotation(999999)
        self.assertIsNone(rec)
        self.assertEqual([], kette)

    def test_EV55_ein_zyklus_laesst_den_aufruf_nicht_haengen(self):
        a = self._speichere("v1")
        b = self._speichere("v2")
        # Datenschaden von Hand herstellen: b zeigt auf a, a auf b.
        self.con.execute(
            "UPDATE annotations SET prev_id = ?, deleted_at = ? WHERE id = ?",
            (b, 1787832100, a))
        self.con.execute(
            "UPDATE annotations SET deleted_at = ? WHERE id = ?",
            (1787832200, b))
        self.con.commit()
        rec, kette = self.edb.get_current_annotation(a)
        self.assertIsNone(rec)
        self.assertLessEqual(len(kette), self.edb.NACHFOLGER_GRENZE)
