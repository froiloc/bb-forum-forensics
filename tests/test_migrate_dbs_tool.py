# =============================================================================
# tests/test_migrate_dbs_tool.py
# IT-Forensisches Ermittlungswerkzeug — tools/migrate-dbs.py
# =============================================================================
# Testsuite fuer Build 585.
#
# ANLASS (2026-07-30): auf der Anlage fehlten zwei Migrationen der
# templates.db seit dem 21./22. Juli. Kein Fehler, nur Stille. Der Grund war
# struktureller Art: vier Datenbanken haben ein Register, templates.db hatte
# fuenf einzeln aufzurufende Skripte mit UNEINHEITLICHEN Schaltern.
#
# MD01 - Trockenuebung ist die VORGABE: ohne --apply wird nichts geschrieben.
# MD02 - der Bericht nennt die offene Migration beim Namen.
# MD03 - --apply schliesst die Luecke und legt VORHER eine Sicherung an.
# MD04 - --no-backup unterdrueckt die Sicherung (und nur sie).
# MD05 - DER RUECKGABEWERT WIRD NACHGEPRUEFT, nicht behauptet: nach einem
#        erfolgreichen Lauf 0, bei offener Luecke 1.
# MD06 - IDEMPOTENZ: ein zweiter scharfer Lauf aendert nichts.
# MD07 - forensic_<uid>.db wird als versiegelt AUSGEWIESEN und nie migriert.
# MD08 - default.db/translations.db werden GENANNT, aber nicht bewertet.
#
# Version: v0.8.585 . Build: 585 . 2026-07-30
# =============================================================================

import hashlib
import importlib.util
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_WURZEL))

# Der Dateiname enthaelt einen Bindestrich -> kein normaler Import.
_spec = importlib.util.spec_from_file_location(
    "migrate_dbs_tool", str(_WURZEL / "tools" / "migrate-dbs.py"))
mdt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mdt)

_SCHEMA_VOLL = (_WURZEL / "tests" / "fixtures_templates_schema.sql")


def _schema_sql(mit_ci: bool) -> str:
    sql = _SCHEMA_VOLL.read_text(encoding="utf-8")
    if not mit_ci:
        sql = sql.replace('"validation_ci" INTEGER NOT NULL DEFAULT 0,\n', "")
    return sql


def _fingerabdruck(pfad: Path) -> str:
    con = sqlite3.connect(str(pfad))
    teile = []
    for (name,) in con.execute(
            "SELECT name FROM sqlite_master ORDER BY name"):
        ddl = con.execute("SELECT sql FROM sqlite_master WHERE name=?",
                          (name,)).fetchone()[0]
        teile.append("O:%s:%s" % (name, ddl or ""))
    for (name,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        if name == "templates_audit_log":
            continue                      # Protokoll darf wachsen
        for row in con.execute("SELECT * FROM %s ORDER BY 1" % name):
            teile.append("%s:%s" % (name, "|".join(str(v) for v in row)))
    con.close()
    return hashlib.sha256("\n".join(teile).encode()).hexdigest()


class MigrateDbsToolTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.data = Path(self._tmp) / "data"
        self.data.mkdir()

    def _templates(self, mit_ci: bool) -> Path:
        pfad = self.data / "templates.db"
        con = sqlite3.connect(str(pfad))
        con.executescript(_schema_sql(mit_ci))
        con.commit()
        con.close()
        return pfad

    def _baks(self):
        return sorted(p.name for p in self.data.glob("*.bak"))

    # MD01 ---------------------------------------------------------------
    def test_md01_trockenuebung_schreibt_nicht(self):
        pfad = self._templates(mit_ci=False)
        vorher = _fingerabdruck(pfad)
        code = mdt.main(["--data-dir", str(self.data)])
        # Vorgabe ist die Trockenuebung - ohne --apply passiert NICHTS.
        self.assertEqual(code, 1)
        self.assertEqual(_fingerabdruck(pfad), vorher)
        self.assertEqual(self._baks(), [])

    # MD02 ---------------------------------------------------------------
    def test_md02_bericht_nennt_die_luecke(self):
        self._templates(mit_ci=False)
        offen, zeilen, dbs = mdt.bericht(self.data, None, None)
        text = "\n".join(zeilen)
        self.assertEqual(offen, 1)
        self.assertEqual(dbs, ["templates"])
        self.assertIn("497", text)
        self.assertIn("[ ] Build 497", text)
        self.assertIn("[x] Build 489", text)

    # MD03 ---------------------------------------------------------------
    def test_md03_apply_schliesst_und_sichert(self):
        pfad = self._templates(mit_ci=False)
        code = mdt.main(["--data-dir", str(self.data), "--apply"])
        self.assertEqual(code, 0)
        spalten = [r[1] for r in sqlite3.connect(str(pfad)).execute(
            "PRAGMA table_info(placeholders)")]
        self.assertIn("validation_ci", spalten)
        # Die Sicherung entsteht VOR der Aenderung.
        self.assertEqual(len(self._baks()), 1)

    # MD04 ---------------------------------------------------------------
    def test_md04_no_backup_unterdrueckt_nur_die_sicherung(self):
        pfad = self._templates(mit_ci=False)
        code = mdt.main(["--data-dir", str(self.data), "--apply",
                         "--no-backup"])
        self.assertEqual(code, 0)
        self.assertEqual(self._baks(), [])
        spalten = [r[1] for r in sqlite3.connect(str(pfad)).execute(
            "PRAGMA table_info(placeholders)")]
        self.assertIn("validation_ci", spalten)

    # MD05 ---------------------------------------------------------------
    def test_md05_rueckgabewert_wird_nachgeprueft(self):
        self._templates(mit_ci=True)
        # Vollstaendig -> 0, und zwar OHNE etwas zu tun.
        self.assertEqual(mdt.main(["--data-dir", str(self.data)]), 0)
        self.assertEqual(mdt.main(["--data-dir", str(self.data), "--apply"]), 0)
        self.assertEqual(self._baks(), [])

    # MD06 ---------------------------------------------------------------
    def test_md06_zweiter_scharfer_lauf_aendert_nichts(self):
        pfad = self._templates(mit_ci=False)
        mdt.main(["--data-dir", str(self.data), "--apply", "--no-backup"])
        nach_erstem = _fingerabdruck(pfad)
        mdt.main(["--data-dir", str(self.data), "--apply", "--no-backup"])
        # Idempotenz ist die Grundlage der Entscheidung mc (b): erneutes
        # Anwenden auf vollstaendigem Stand darf nichts veraendern.
        self.assertEqual(_fingerabdruck(pfad), nach_erstem)

    # MD07 ---------------------------------------------------------------
    def test_md07_forensic_wird_als_versiegelt_ausgewiesen(self):
        self._templates(mit_ci=True)
        (self.data / "forensic").mkdir()
        pfad = self.data / "forensic" / "forensic_42.db"
        sqlite3.connect(str(pfad)).close()
        vorher = _fingerabdruck(pfad)
        _, zeilen, dbs = mdt.bericht(self.data, 42, None)
        text = "\n".join(zeilen)
        self.assertIn("versiegelt", text)
        # Sie zaehlt NIE als offene Migration - ein Werkzeug, das dort
        # schreibt, veraendert Beweismittel.
        self.assertNotIn("forensic", dbs)
        mdt.main(["--data-dir", str(self.data), "--subject-id", "42",
                  "--apply", "--no-backup"])
        self.assertEqual(_fingerabdruck(pfad), vorher)

    # MD08 ---------------------------------------------------------------
    def test_md08_prepper_erzeugnisse_genannt_nicht_bewertet(self):
        self._templates(mit_ci=True)
        (self.data / "default.db").write_bytes(b"")
        _, zeilen, dbs = mdt.bericht(self.data, None, None)
        text = "\n".join(zeilen)
        # Genannt - sonst fragte sich jemand, warum sie fehlen ...
        self.assertIn("default.db", text)
        self.assertIn("translations.db", text)
        self.assertIn("nicht bewertet", text)
        # ... aber nicht bewertet.
        self.assertNotIn("default", dbs)


if __name__ == "__main__":
    unittest.main()
