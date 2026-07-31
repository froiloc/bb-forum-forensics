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
# BUILD 612 - WARTUNGSVORBEHALT: '--apply' steht seit Build 612 unter dem
# Wartungsvorbehalt (Stufe A). Jede setUp setzt deshalb ueber _wartungsfenster()
# ein Fenster auf das Wegwerf-Datenverzeichnis - so, wie es auch in der Anlage
# vor einer Migration gesetzt wird. Ohne Fenster und ohne Terminal braeche der
# Lauf mit Rueckgabewert 3 ab und schriebe nichts; das ist richtig, denn ein
# Test IST ein Aufruf ohne Menschen an der Konsole. Den Vorbehalt zu umgehen
# waere die bequemere und die falsche Loesung: dann pruefte die Suite einen
# Weg, den es in der Anlage nicht mehr gibt.
#
# Version: v0.8.612 . Build: 612 . 2026-07-31
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


def _wartungsfenster(data_dir: Path) -> None:
    """
    Setzt ein Wartungsfenster ueber das Wegwerf-Datenverzeichnis.

    NOETIG SEIT BUILD 612: 'migrate-dbs --apply' steht unter dem
    Wartungsvorbehalt (Stufe A). Ohne aktives Fenster und ohne Terminal
    bricht der Lauf mit Rueckgabewert 3 ab und schreibt nichts - richtig so,
    denn ein Test IST ein Aufruf ohne Menschen an der Konsole.

    DIE TESTS BILDEN DAMIT DEN ECHTEN ABLAUF AB: wer migriert, setzt vorher
    ein Fenster. Den Vorbehalt im Test zu umgehen waere die bequemere und
    die falsche Loesung - dann pruefte die Suite einen Weg, den es in der
    Anlage nicht mehr gibt.
    """
    from maintenance.paths import MaintenancePaths
    from maintenance.window_flag import WindowFlag
    pfade = MaintenancePaths(data_dir)
    pfade.verzeichnisse_anlegen()
    WindowFlag.neu(angefordert_von="test", grund="Regressionslauf",
                   ziel=["all"]).schreiben(pfade)


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
        _wartungsfenster(self.data)

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


class LageEindeutigTests(unittest.TestCase):
    """
    Build 586: die Lage wird BENANNT, nicht aus dem Register erschlossen.

    Befund mc (2026-07-30): 'evidence_1488.db  0 von 3  OFFEN: 1,2,3' war
    zweideutig. Es kam allein daraus, dass schema_migrations fehlte - und das
    kann zweierlei heissen: die Migrationen sind nicht gelaufen, ODER ihre
    Wirkungen sind da und nur der Eintrag fehlt. Bei den Fall-Datenbanken ist
    Letzteres der plausible Normalfall, weil m001 datenneutral ist.

    LG01 - fehlende FACHLICHE Tabellen -> 'wirkung_fehlt', mit Nennung.
    LG02 - Tabellen da, kein Register -> 'nur_eintrag_fehlt' (kein Notstand).
    LG03 - das Register ist eine SONDERSPUR: sein Fehlen allein ist nie
           'Wirkung fehlt'.
    LG04 - forensic ist versiegelt und zaehlt NIE als Luecke.
    LG05 - der genannte Befehl ist der ZUSTAENDIGE (Build 585 nannte fuer
           evidence/assets faelschlich den coordinator-Runner).
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.data = Path(self._tmp) / "data"
        for unter in ("evidence", "assets", "forensic"):
            (self.data / unter).mkdir(parents=True)
        _wartungsfenster(self.data)

    def _evidence(self, mit_tabellen: bool, mit_register: bool):
        pfad = self.data / "evidence" / "evidence_1488.db"
        con = sqlite3.connect(str(pfad))
        con.execute("CREATE TABLE annotations (id INTEGER)")
        if mit_tabellen:
            con.execute("CREATE TABLE annotation_tatzeit (id INTEGER)")
            con.execute("CREATE TABLE evidence_audit_log (id INTEGER)")
        if mit_register:
            con.execute("CREATE TABLE schema_migrations (version INTEGER, "
                        "name TEXT, kind TEXT, checksum TEXT, "
                        "applied_at INTEGER)")
            for v in (1, 2, 3):
                con.execute("INSERT INTO schema_migrations VALUES "
                            "(?,'x','additive','y',0)", (v,))
        con.commit()
        con.close()
        return pfad

    # LG01 ---------------------------------------------------------------
    def test_lg01_fehlende_tabellen_sind_wirkung_fehlt(self):
        pfad = self._evidence(mit_tabellen=False, mit_register=False)
        befund = mdt.fall_befund(pfad, "evidence")
        self.assertEqual(befund["lage"], "wirkung_fehlt")
        self.assertEqual(befund["fachlich_fehlt"], [2, 3])
        _, zeilen, _ = mdt.bericht(self.data, 1488, None)
        text = "\n".join(zeilen)
        self.assertIn("annotation_tatzeit", text)
        self.assertIn("evidence_audit_log", text)

    # LG02 ---------------------------------------------------------------
    def test_lg02_nur_eintrag_fehlt_ist_kein_notstand(self):
        pfad = self._evidence(mit_tabellen=True, mit_register=False)
        befund = mdt.fall_befund(pfad, "evidence")
        self.assertEqual(befund["lage"], "nur_eintrag_fehlt")
        self.assertEqual(befund["fachlich_fehlt"], [])
        _, zeilen, _ = mdt.bericht(self.data, 1488, None)
        text = "\n".join(zeilen)
        self.assertIn("nur der Registereintrag fehlt", text)
        self.assertIn("Kein Notstand", text)

    # LG03 ---------------------------------------------------------------
    def test_lg03_register_ist_sonderspur(self):
        """assets hat NUR die Registerspur - ihr Fehlen darf nie wie ein
        fachlicher Ausfall klingen."""
        sqlite3.connect(str(self.data / "assets" / "assets_1488.db")).close()
        befund = mdt.fall_befund(
            self.data / "assets" / "assets_1488.db", "assets")
        self.assertEqual(befund["fachlich_fehlt"], [])
        self.assertEqual(befund["lage"], "nur_eintrag_fehlt")

    # LG04 ---------------------------------------------------------------
    def test_lg04_forensic_zaehlt_nie(self):
        self._evidence(mit_tabellen=True, mit_register=True)
        sqlite3.connect(
            str(self.data / "forensic" / "forensic_1488.db")).close()
        offen, zeilen, dbs = mdt.bericht(self.data, 1488, None)
        text = "\n".join(zeilen)
        self.assertIn("versiegelt", text)
        self.assertIn("keine Luecke", text)
        self.assertNotIn("forensic", dbs)

    # LG05 ---------------------------------------------------------------
    def test_lg05_zustaendiger_befehl(self):
        """
        Die Geschichte dieser Pruefung in zwei Schritten:

        Build 585 nannte fuer evidence/assets 'python -m management.migrate' -
        das behandelt aber NUR coordinator.db. Build 586 korrigierte auf die
        Flotten-Schicht - die auf der Anlage NIE in Betrieb genommen wurde
        (migration.db fehlt). Build 587 zieht die Folgerung: fuer evidence und
        assets wendet das Werkzeug SELBST an, also braucht es dort gar keinen
        fremden Befehl mehr.

        Geblieben ist nur coordinator.db mit ihrem eingefuehrten Weg.
        """
        self.assertEqual(sorted(mdt.BEFEHL), ["coordinator"])
        self.assertIn("management.migrate", mdt.BEFEHL["coordinator"])
        self.assertNotIn("migration_fleet", mdt.BEFEHL["coordinator"])


class FallAnwendenTests(unittest.TestCase):
    """
    Build 587: die Fall-Datenbanken werden DIREKT ueber den MigrationRunner
    nachgezogen.

    Anlass: Build 586 verwies fuer evidence/assets auf die Flotten-Schicht
    (migration_fleet_admin). Die ist auf der Anlage NIE in Betrieb genommen
    worden - migration.db existiert nicht und steht nicht in der config.yaml.
    Der Befehl brach ab, und mc stand vor einer Datei, von der er noch nie
    gehoert hatte. Massgeblich ist ohnehin das Register IN der Datenbank
    (schema_migrations), und genau das schreibt der MigrationRunner.

    FA01 - evidence: die beiden fehlenden Tabellen entstehen, Register wird
           geschrieben.
    FA02 - IDEMPOTENZ: ein zweiter Lauf wendet nichts mehr an.
    FA03 - vor der Anwendung entsteht eine Sicherung (ausser --no-backup).
    FA04 - eine UNGUELTIGE Datenbank wird abgewiesen, ohne Teilzustand.
    FA05 - der Verweis auf die nicht betriebene Flotten-Schicht ist entfallen.
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.data = Path(self._tmp) / "data"
        for unter in ("evidence", "assets", "forensic"):
            (self.data / unter).mkdir(parents=True)
        _wartungsfenster(self.data)

    def _evidence(self):
        pfad = self.data / "evidence" / "evidence_1488.db"
        con = sqlite3.connect(str(pfad))
        con.executescript(
            "CREATE TABLE annotations (id INTEGER PRIMARY KEY, "
            "  page_url TEXT NOT NULL);"
            "CREATE TABLE reports (id INTEGER PRIMARY KEY, title TEXT);"
            "CREATE TABLE report_blocks (block_id TEXT PRIMARY KEY, "
            "  report_id INTEGER);")
        con.commit()
        con.close()
        return pfad

    def _tabellen(self, pfad):
        con = sqlite3.connect(str(pfad))
        try:
            return {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()

    # FA01 ---------------------------------------------------------------
    def test_fa01_fehlende_tabellen_entstehen(self):
        pfad = self._evidence()
        self.assertNotIn("evidence_audit_log", self._tabellen(pfad))
        code = mdt.main(["--data-dir", str(self.data), "--subject-id", "1488",
                         "--apply", "--no-backup"])
        self.assertEqual(code, 0)
        tabellen = self._tabellen(pfad)
        # evidence_audit_log ist die Hash-Kette der Beweismitteldatenbank -
        # kein Beschleuniger, sondern ein forensisches Kernstueck.
        self.assertIn("evidence_audit_log", tabellen)
        self.assertIn("annotation_tatzeit", tabellen)
        self.assertIn("schema_migrations", tabellen)
        con = sqlite3.connect(str(pfad))
        versionen = [r[0] for r in con.execute(
            "SELECT version FROM schema_migrations ORDER BY version")]
        con.close()
        self.assertEqual(versionen, [1, 2, 3])

    # FA02 ---------------------------------------------------------------
    def test_fa02_zweiter_lauf_wendet_nichts_an(self):
        self._evidence()
        mdt.main(["--data-dir", str(self.data), "--subject-id", "1488",
                  "--apply", "--no-backup"])
        # Der zweite Lauf sieht 'aktuell' und tut nichts.
        self.assertEqual(
            mdt.main(["--data-dir", str(self.data), "--subject-id", "1488",
                      "--apply", "--no-backup"]), 0)

    # FA03 ---------------------------------------------------------------
    def test_fa03_sicherung_vor_der_anwendung(self):
        self._evidence()
        mdt.main(["--data-dir", str(self.data), "--subject-id", "1488",
                  "--apply"])
        baks = list((self.data / "evidence").glob("*.bak"))
        self.assertEqual(len(baks), 1)
        # Die Sicherung ist der Stand VORHER: ohne die neuen Tabellen.
        self.assertNotIn("evidence_audit_log", self._tabellen(baks[0]))

    # FA04 ---------------------------------------------------------------
    def test_fa04_ungueltige_db_wird_abgewiesen(self):
        """
        Die Baseline prueft, ob ueberhaupt eine fachliche Tabelle da ist. Eine
        leere Datei ist keine gueltige Fall-Datenbank - und darf nicht
        stillschweigend zu einer gemacht werden.
        """
        pfad = self.data / "assets" / "assets_1488.db"
        sqlite3.connect(str(pfad)).close()
        with self.assertRaises(Exception):
            mdt.fall_anwenden(pfad, "assets")
        # KEIN Teilzustand: das Register KANN bereits angelegt sein
        # (ensure_registry laeuft vor der Transaktion) - aber es darf KEINE
        # Version verzeichnet sein. Genau das ist die Zusicherung: entweder
        # eine Migration gilt vollstaendig, oder gar nicht.
        con = sqlite3.connect(str(pfad))
        try:
            versionen = [r[0] for r in con.execute(
                "SELECT version FROM schema_migrations")]
        except sqlite3.OperationalError:
            versionen = []
        finally:
            con.close()
        self.assertEqual(versionen, [])
        # Und die fachlichen Tabellen sind nicht entstanden.
        self.assertNotIn("annotation_tatzeit", self._tabellen(pfad))

    # FA05 ---------------------------------------------------------------
    def test_fa05_kein_verweis_auf_die_flotte(self):
        quelle = (_WURZEL / "tools" / "migrate-dbs.py").read_text(
            encoding="utf-8")
        # In BEFEHL darf die Flotte nicht mehr auftauchen - sie ist auf der
        # Anlage nicht in Betrieb (migration.db fehlt).
        self.assertNotIn("evidence", mdt.BEFEHL)
        self.assertNotIn("assets", mdt.BEFEHL)
        self.assertIn("coordinator", mdt.BEFEHL)
        # Der Grund steht im Quelltext, damit ihn niemand versehentlich
        # zurueckbaut.
        self.assertIn("migration.db", quelle)


if __name__ == "__main__":
    unittest.main()
