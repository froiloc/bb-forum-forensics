# =============================================================================
# tests/test_m039_migration.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Build 725)
# =============================================================================
# Testsuite fuer M039: person.first_name / last_name / rank in coordinator.db.
#
# M39-01 - up() legt die drei Spalten an, display_name bleibt unangetastet
# M39-02 - IDEMPOTENZ: ein zweiter Lauf ist ein No-op
# M39-03 - VERLUSTFREI: keine person-Zeile gewonnen oder verloren, alle
#          Bestandswerte unveraendert, die neuen Spalten NULL
# M39-04 - fehlt 'person', bricht up() LAUT ab (kein halbes Anlegen)
# M39-05 - die Kennwerte des Moduls stimmen (VERSION/KIND/NAME)
# M39-06 - GEGENPROBE: vor up() gibt es die Spalten nicht - der Test kann
#          also ueberhaupt anschlagen
#
# WARUM DER VERLUSTFREIHEITS-TEST HIER STEHT UND NICHT NUR IM RUNNER: Seit
# dem 01.07.2026 laufen Ermittlerdaten auf. coordinator.db traegt zwar keine
# Ermittlungsergebnisse (Projektregeln), aber sehr wohl die Stammdaten, an
# denen jede Zuweisung und jeder Beleg haengt. 'Additiv' ist eine BEHAUPTUNG,
# solange sie niemand nachmisst.
#
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.migrations.coordinator import m039_person_namensteile as m039

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

_BESTAND = [
    (1, "h0chef", "Weyand, Carla", 1, 1, 0, 1750000000),
    (2, "h0erm", "Bergmann, Rita", 1, 0, 0, 1750000100),
    (3, "h0sup", "Okonkwo, Ada", 1, 0, 1, 1750000200),
]


class M039Tests(unittest.TestCase):

    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        self.con.execute(_PERSON)
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?,?,?,?,?,?,?)", _BESTAND)

    def tearDown(self):
        self.con.close()

    def _spalten(self):
        return {r[1] for r in self.con.execute("PRAGMA table_info(person)")}

    def _zeilen(self):
        return [dict(r) for r in self.con.execute(
            "SELECT id, system_username, display_name, is_investigator, "
            "is_supervisor, is_support, created_at FROM person ORDER BY id")]

    # -- M39-06 (zuerst: die Gegenprobe) -----------------------------------
    def test_m39_06_gegenprobe_vorher_keine_spalten(self):
        vorhanden = self._spalten()
        for spalte in ("first_name", "last_name", "rank"):
            self.assertNotIn(spalte, vorhanden,
                             "Die Ausgangslage muss echt sein, sonst prueft "
                             "M39-01 nichts.")

    # -- M39-01 -------------------------------------------------------------
    def test_m39_01_legt_die_drei_spalten_an(self):
        m039.up(self.con)
        vorhanden = self._spalten()
        for spalte in ("first_name", "last_name", "rank"):
            with self.subTest(spalte=spalte):
                self.assertIn(spalte, vorhanden)
        self.assertIn("display_name", vorhanden,
                      "display_name bleibt der Anzeigename und der "
                      "Rueckfallweg fuer den Nachnamen.")

    # -- M39-02 -------------------------------------------------------------
    def test_m39_02_idempotent(self):
        m039.up(self.con)
        nach_erstem = (self._spalten(), self._zeilen())
        m039.up(self.con)          # darf nicht scheitern
        self.assertEqual(nach_erstem, (self._spalten(), self._zeilen()))

    # -- M39-03 -------------------------------------------------------------
    def test_m39_03_verlustfrei(self):
        vorher = self._zeilen()
        m039.up(self.con)
        self.assertEqual(vorher, self._zeilen(),
                         "Kein Bestandswert darf sich geaendert haben.")
        # Die neuen Spalten sind NULL - "nie befuellt", nicht "im AD leer".
        for row in self.con.execute(
                "SELECT first_name, last_name, rank FROM person"):
            self.assertEqual((None, None, None),
                             (row["first_name"], row["last_name"], row["rank"]))

    # -- M39-04 -------------------------------------------------------------
    def test_m39_04_ohne_person_bricht_es_laut_ab(self):
        leer = sqlite3.connect(":memory:")
        leer.row_factory = sqlite3.Row
        with self.assertRaises(RuntimeError) as ctx:
            m039.up(leer)
        self.assertIn("person", str(ctx.exception))
        leer.close()

    # -- M39-05 -------------------------------------------------------------
    def test_m39_05_kennwerte(self):
        self.assertEqual(39, m039.VERSION)
        self.assertEqual("additive", m039.KIND)
        self.assertTrue(m039.NAME)
        # Die Migration darf nichts aus dem Laufzeitcode importieren
        # (m005-Prinzip: eine angewandte Migration aendert ihr Verhalten nie).
        quelle = Path(m039.__file__).read_text(encoding="utf-8")
        for verboten in ("from report_render", "from db.coordinator_db",
                         "import ermittler_namen"):
            with self.subTest(muster=verboten):
                self.assertNotIn(verboten, quelle)


if __name__ == "__main__":
    unittest.main()
