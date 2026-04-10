# =============================================================================
# tests/test_evidence_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Testsuite für db/evidence_db.py
#
# T01 — Schema wird beim Init angelegt (Tabellen existieren nach Init)
# T02 — log_page_visit() speichert Eintrag korrekt
# T03 — log_page_visit() mit explizitem Timestamp
# T04 — get_page_visits() gibt Besuche einer URL zurück
# T05 — save_viewport_event() speichert Event korrekt
# T06 — save_viewport_event(): ts_leave < ts_enter → EvidenceDbError
# T07 — save_viewport_event(): visible_ms < 0 → EvidenceDbError
# T08 — save_viewport_batch() speichert mehrere Events
# T09 — save_viewport_batch(): ungültige Events werden übersprungen
# T10 — save_annotation(): alle sechs Kategorien akzeptiert
# T11 — save_annotation(): ungültige Kategorie → EvidenceDbError
# T12 — get_annotations() gibt Annotationen einer URL zurück
# T13 — get_all_annotations() gibt alle Annotationen zurück
# T14 — annotation_count() korrekt
# T15 — Init ist idempotent (mehrfaches Anlegen des Schemas kein Fehler)
#
# Version: v0.1.0 · Build: 007 · 2026-04-10
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
        # In-Memory-DB als Haupt-DB (entspricht evidence_db im Normalmodus)
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
        """T04: get_page_visits() gibt Besuche einer URL zurück."""
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
        """T06: ts_leave < ts_enter → EvidenceDbError."""
        with self.assertRaises(EvidenceDbError):
            self.edb.save_viewport_event(
                "/forum/x", "p1", 0, ts_enter=2000, ts_leave=1000
            )

    def test_T07_viewport_visible_ms_negativ(self):
        """T07: visible_ms < 0 → EvidenceDbError."""
        with self.assertRaises(EvidenceDbError):
            self.edb.save_viewport_event(
                "/forum/x", "p1", -1, ts_enter=1000, ts_leave=2000
            )

    def test_T08_viewport_batch(self):
        """T08: save_viewport_batch() speichert mehrere Events in einer Transaktion."""
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
        """T09: Ungültige Events im Batch werden übersprungen, gültige gespeichert."""
        events = [
            {"page_url": "/forum/x", "element_id": "p1",
             "visible_ms": 100, "ts_enter": 1000, "ts_leave": 1100},  # gültig
            {"page_url": "/forum/x", "element_id": "p2",
             "visible_ms": -5, "ts_enter": 1000, "ts_leave": 1100},   # ungültig
        ]
        count = self.edb.save_viewport_batch(events)
        self.assertEqual(count, 1)

    def test_T10_alle_kategorien_akzeptiert(self):
        """T10: Alle sechs VALID_CATEGORIES werden von save_annotation() akzeptiert."""
        for cat in VALID_CATEGORIES:
            row_id = self.edb.save_annotation(
                page_url=f"/forum/{cat}",
                category=cat,
                text=f"Test {cat}",
            )
            self.assertGreater(row_id, 0)
        self.assertEqual(self.edb.annotation_count(), len(VALID_CATEGORIES))

    def test_T11_ungueltige_kategorie(self):
        """T11: Ungültige Kategorie → EvidenceDbError."""
        with self.assertRaises(EvidenceDbError):
            self.edb.save_annotation("/forum/x", category="CAT_INVALID", text="test")

    def test_T12_get_annotations(self):
        """T12: get_annotations() gibt Annotationen einer URL zurück."""
        url = "/forum/viewtopic.php?id=77"
        self.edb.save_annotation(url, "CAT_PERSON", "Name erwähnt", ts=1000)
        self.edb.save_annotation(url, "CAT_176", "Relevanter Inhalt", ts=2000)
        self.edb.save_annotation("/forum/other", "CAT_OTHER", "Nichts", ts=3000)

        anns = self.edb.get_annotations(url)
        self.assertEqual(len(anns), 2)
        self.assertEqual(anns[0].category, "CAT_PERSON")
        self.assertEqual(anns[1].category, "CAT_176")

    def test_T13_get_all_annotations(self):
        """T13: get_all_annotations() gibt alle Annotationen zurück."""
        self.edb.save_annotation("/forum/a", "CAT_PERSON", "A")
        self.edb.save_annotation("/forum/b", "CAT_184", "B")
        all_anns = self.edb.get_all_annotations()
        self.assertEqual(len(all_anns), 2)

    def test_T14_annotation_count(self):
        """T14: annotation_count() gibt korrekte Anzahl zurück."""
        self.assertEqual(self.edb.annotation_count(), 0)
        self.edb.save_annotation("/forum/x", "CAT_OTHER", "test")
        self.assertEqual(self.edb.annotation_count(), 1)

    def test_T15_schema_idempotent(self):
        """T15: Mehrfaches Anlegen des Schemas wirft keine Exception."""
        EvidenceDb(self.con)  # Zweite Instanz auf derselben Verbindung
        EvidenceDb(self.con)  # Dritte Instanz


if __name__ == "__main__":
    unittest.main(verbosity=2)
