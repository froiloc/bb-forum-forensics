# =============================================================================
# tests/test_export_admin_rahmen.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem
# =============================================================================
# Testsuite zu Vorgang 5001d293 (Build 708):
#   "export_admin baut den Erzeugungsvermerk an context_builder vorbei"
#
# WORUM ES GEHT:
#   export_admin hielt bis Build 706 eigene Kopien von _build_number,
#   _verify_tip und _resolve_actor und setzte den ExportContext von Hand
#   zusammen. Es war damit das einzige Werkzeug, das den in Build 442 eigens
#   dafuer geschaffenen context_builder nicht benutzte - und deshalb auch das
#   einzige, an dem die Rahmenbefunde aus Build 702 vorbeigingen: sein
#   _build_number gab bei unlesbarer build.json STILL 0 zurueck.
#
# WAS BEIM UMSTELLEN ZU SICHERN WAR - und was diese Faelle vor allem pruefen:
#   Eine Vereinheitlichung darf die Auskunft nicht AERMER machen. export_admin
#   meldete als einziges Werkzeug eine GEBROCHENE Kette samt Fundstelle. Der
#   context_builder erzeugt dafuer bewusst keinen Rahmenbefund (Build 702,
#   note (6): eine gebrochene Kette ist eine Aussage ueber den BESTAND, nicht
#   ueber den Vermerk). Ein blosser Austausch haette diese Warnung lautlos
#   entfernt - genau die Art Verlust, gegen die dieser Umbau angetreten ist.
#   XA03 ist deshalb der wichtigste Fall dieser Datei.
#
#   XA01 — Regelfall: kein Wort, echte Buildnummer, aufgeloeste Identitaet
#   XA02 — unlesbare build.json: Meldung + 'nicht ermittelbar' (DER VORGANG)
#   XA03 — GEBROCHENE Kette: die Warnung samt Fundstelle bleibt erhalten
#   XA04 — fehlendes audit_log: Rahmenbefund statt frueherem HINWEIS
#   XA05 — ohne --actor: Identitaet als Rahmenbefund gemeldet
#   XA06 — die drei eigenen Kopien sind wirklich weg (kein toter Zwilling)
#   XA07 — ein Fehler in der Kettenpruefung beendet den Export nicht mehr
#   XA08 — der Katalogeintrag beschreibt den neuen Stand
#
# GEGENPROBE, nachgemessen mit export_admin.py und cli_katalog.py auf Stand
# 706 und dem Rahmen auf 708:
#   FALLEN (5): XA02, XA04, XA05, XA06, XA08.
#   BESTEHEN (3), und jedes aus einem eigenen Grund:
#     XA01, XA03 — sie halten fest, was sich NICHT aendern durfte.
#     XA07 — er prueft eine Eigenschaft des CONTEXT_BUILDER, nicht die
#            Umstellung; die gibt es dort seit Build 702. Er steht hier
#            trotzdem, weil er belegt, dass die neue Grundlage genau das
#            leistet, woran die alte Kopie scheiterte. Als Gegenprobe zur
#            Umstellung taugt er ausdruecklich NICHT - das gehoert gesagt,
#            damit die Zahl '5 von 8' nicht spaeter als '6' erinnert wird.
#
# Version: v0.8.708 · Build: 708 · 2026-08-12
# =============================================================================

import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.export import context_builder                          # noqa: E402

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    import openpyxl  # noqa: F401
    _EXCEL_DA = True
except Exception:  # pragma: no cover - openpyxl fehlt in der Umgebung
    _EXCEL_DA = False


def _echte_buildnummer() -> int:
    with open(os.path.join(WURZEL, "build.json"), encoding="utf-8") as fh:
        return int(json.load(fh)["build"])


_INVESTIGATORS = """
CREATE TABLE person (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username  TEXT UNIQUE NOT NULL,
    display_name     TEXT,
    is_investigator  INTEGER NOT NULL DEFAULT 0,
    is_supervisor    INTEGER NOT NULL DEFAULT 0,
    is_support       INTEGER NOT NULL DEFAULT 0,
    created_at       INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    username      TEXT    NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT,
    output_path   TEXT,
    worker_id     TEXT,
    created_at    INTEGER NOT NULL,
    started_at    INTEGER,
    finished_at   INTEGER,
    error_message TEXT,
    assigned_to   INTEGER,
    note          TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


def _baue_coordinator(pfad):
    import management.migrations.coordinator as coordinator_migrations
    from management.audit.audit_log import AuditLog
    from management.migrations.runner import MigrationRunner, discover

    con = sqlite3.connect(pfad)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_INVESTIGATORS)
    con.execute(
        "INSERT INTO person (id, system_username, display_name, "
        "is_investigator, is_supervisor, is_support, created_at) "
        "VALUES (1, 'h012345', 'Muster, Erika', 1, 1, 0, ?)",
        (int(time.time()),))
    con.execute(_OLD_SCRAPE_JOBS)
    MigrationRunner(con, discover(coordinator_migrations),
                    audit=AuditLog(con), deployed_by="tester").run()
    con.close()


@unittest.skipUnless(_EXCEL_DA, "openpyxl nicht verfuegbar")
class ExportAdminRahmen(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls._tmp, "coordinator.db")
        _baue_coordinator(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        for fn in os.listdir(cls._tmp):
            try:
                os.remove(os.path.join(cls._tmp, fn))
            except OSError:
                pass
        os.rmdir(cls._tmp)

    def setUp(self):
        self._out = tempfile.mkdtemp()

    def tearDown(self):
        for fn in os.listdir(self._out):
            try:
                os.remove(os.path.join(self._out, fn))
            except OSError:
                pass
        os.rmdir(self._out)

    # -- Helfer --------------------------------------------------------------
    def _lauf(self, db_path=None, actor="h012345",
              build_json_umlenken_nach=None):
        """
        main() ausfuehren; liefert (rc, stderr-Text, Vermerkzeilen der XLSX).

        Der Erzeugungsvermerk wird AUS DER ERZEUGTEN DATEI gelesen und nicht
        aus dem Kontext: der Vorgang beanstandet, was IM DOKUMENT steht.
        """
        from pathlib import Path as _EchterPath
        from management.export import export_admin

        ziel = os.path.join(self._out, "fall.xlsx")
        argv = ["case-status-xlsx", "--out", ziel,
                "--coordinator-db", db_path or self.db_path,
                "--config", os.path.join(self._out, "gibtsnicht.yaml")]
        if actor is not None:
            argv += ["--actor", actor]

        alt_stderr, alt_path = sys.stderr, context_builder.Path
        puffer = io.StringIO()
        try:
            sys.stderr = puffer
            if build_json_umlenken_nach is not None:
                context_builder.Path = (
                    lambda _a: _EchterPath(build_json_umlenken_nach)
                    / "a" / "b" / "c")
            rc = export_admin.main(argv)
        finally:
            sys.stderr = alt_stderr
            context_builder.Path = alt_path

        return rc, puffer.getvalue(), self._vermerk(ziel)

    @staticmethod
    def _vermerk(pfad):
        import openpyxl
        zeilen = []
        wb = openpyxl.load_workbook(pfad)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for zelle in row:
                    if isinstance(zelle, str) and (
                            "Erstellt von:" in zelle
                            or "Werkzeug-Build:" in zelle
                            or "Audit-Kette:" in zelle
                            or "Erzeugungsvermerk unvollstaendig" in zelle):
                        zeilen.append(zelle)
        return zeilen

    def _kopie(self, name):
        import shutil
        ziel = os.path.join(self._out, name)
        shutil.copy(self.db_path, ziel)
        return ziel

    # -- XA01 ---------------------------------------------------------------
    def test_xa01_regelfall_schweigt_und_traegt_die_echte_buildnummer(self):
        """
        Was sich NICHT aendern durfte. Muss auch gegen Build 706 gruen sein.
        """
        rc, err, vermerk = self._lauf()
        text = "\n".join(vermerk)

        self.assertEqual(rc, 0)
        self.assertNotIn("WARNUNG", err)
        self.assertIn("Werkzeug-Build: %d" % _echte_buildnummer(), text)
        self.assertIn("Muster, Erika (h012345)", text)
        self.assertIn("Audit-Kette: INTAKT", text)
        self.assertNotIn("Erzeugungsvermerk unvollstaendig", text)

    # -- XA02 — DER VORGANG --------------------------------------------------
    def test_xa02_unlesbare_build_json_wird_gemeldet_und_gekennzeichnet(self):
        """
        DER KERN VON 5001d293. Bis Build 706 gab die eigene Kopie von
        _build_number hier still 0 zurueck; die Fallstatus-XLSX trug dann
        'Werkzeug-Build: 0' - ohne ein Wort auf der Fehlerausgabe.
        """
        rc, err, vermerk = self._lauf(build_json_umlenken_nach=self._out)
        text = "\n".join(vermerk)

        self.assertEqual(rc, 0)
        self.assertIn("[export_admin] WARNUNG", err)
        self.assertIn("Buildnummer", err)
        self.assertIn("build.json", err)
        self.assertIn("Weitergabe", err)

        self.assertIn("Werkzeug-Build: nicht ermittelbar", text)
        self.assertNotIn("Werkzeug-Build: 0", text)
        self.assertTrue(any("Erzeugungsvermerk unvollstaendig" in z
                            for z in vermerk))

    # -- XA03 — DER WICHTIGSTE FALL DIESER DATEI -----------------------------
    def test_xa03_gebrochene_kette_wird_weiterhin_mit_fundstelle_gemeldet(self):
        """
        DIE AUSKUNFT DARF DURCH DIE VEREINHEITLICHUNG NICHT AERMER WERDEN.

        export_admin war das einzige Werkzeug, das eine GEBROCHENE Kette samt
        Fundstelle meldete. Der context_builder fuehrt chain_ok=False bewusst
        NICHT als Rahmenbefund - ein blosser Austausch haette die Warnung
        lautlos entfernt. Dieser Fall muss auch gegen Build 706 gruen sein.

        DIE KETTE WIRD DURCH ANFUEGEN GEBROCHEN, nicht durch Aendern: auf
        audit_log liegt ein Trigger, der UPDATE unterbindet (append-only).
        Das Anfuegen einer Zeile mit falschem prev_hash ist damit zugleich
        der realistischere Fall.
        """
        db = self._kopie("kaputt.db")
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        letzte = con.execute(
            "SELECT * FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
        con.execute(
            "INSERT INTO audit_log (ts, actor_id, event_type, target_type,"
            " target_id, content, meta, prev_hash, row_hash)"
            " VALUES (?, ?, 'probe', 'test', '1', 'X', '{}', ?, ?)",
            (int(letzte["ts"]) + 1, letzte["actor_id"], "f" * 64, "e" * 64))
        con.commit()
        con.close()

        rc, err, vermerk = self._lauf(db_path=db)
        text = "\n".join(vermerk)

        self.assertEqual(rc, 0)
        self.assertIn("audit_log-Kette gebrochen", err)
        self.assertIn("prev_hash-Bruch bei seq=", err)   # die FUNDSTELLE
        self.assertIn("Export erfolgt", err)
        self.assertIn("Audit-Kette: GEBROCHEN", text)

        # Eine gebrochene Kette ist KEIN Rahmenbefund: sie ist ermittelt und
        # eine Aussage ueber den Bestand. Die beiden zu vermengen wuerde die
        # schwerere Lage in der leichteren verstecken.
        self.assertNotIn("Erzeugungsvermerk unvollstaendig", text)

    # -- XA04 ---------------------------------------------------------------
    def test_xa04_fehlendes_audit_log_wird_zum_rahmenbefund(self):
        """
        Frueher ein HINWEIS auf der Fehlerausgabe, jetzt ein Rahmenbefund.
        Der Wortlaut aendert sich, die Auskunft wird eher deutlicher - und
        sie steht jetzt zusaetzlich IM DOKUMENT.
        """
        db = self._kopie("ohnekette.db")
        con = sqlite3.connect(db)
        for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' "
                "AND tbl_name='audit_log'").fetchall():
            con.execute("DROP TRIGGER %s" % name)
        con.execute("DROP TABLE audit_log")
        con.commit()
        con.close()

        rc, err, vermerk = self._lauf(db_path=db)
        text = "\n".join(vermerk)

        self.assertEqual(rc, 0)
        self.assertIn("Belegkette", err)
        self.assertIn("no such table: audit_log", err)
        self.assertIn("Audit-Kette: nicht geprueft", text)
        self.assertTrue(any("Erzeugungsvermerk unvollstaendig" in z
                            for z in vermerk))

    # -- XA05 ---------------------------------------------------------------
    def test_xa05_ohne_actor_wird_die_identitaet_zum_befund(self):
        rc, err, vermerk = self._lauf(actor=None)
        text = "\n".join(vermerk)

        self.assertEqual(rc, 0)
        self.assertIn("Identitaet", err)
        self.assertIn("nicht aufgeloest", text)
        # Der Rohwert bleibt stehen - er ist nicht falsch, nur ungeprueft.
        self.assertIn("Erstellt von:", text)


# =============================================================================
# XA06-XA08 — die Umstellung selbst
# =============================================================================
class Xa06BisXa08Umstellung(unittest.TestCase):

    def test_xa06_die_drei_eigenen_kopien_sind_weg(self):
        """
        Ein toter Zwilling ist schlimmer als gar keine Vereinheitlichung: er
        sieht aus, als wuerde er benutzt, und die naechste Aenderung wird an
        ihm vorgenommen. Geprueft wird der Quelltext, nicht das Verhalten -
        die Abwesenheit einer Funktion laesst sich nicht erproben.
        """
        import ast

        pfad = os.path.join(WURZEL, "management", "export", "export_admin.py")
        with open(pfad, encoding="utf-8") as fh:
            quelle = fh.read()
        baum = ast.parse(quelle)
        namen = {k.name for k in ast.walk(baum)
                 if isinstance(k, ast.FunctionDef)}

        for weg in ("_build_number", "_verify_tip", "_resolve_actor"):
            self.assertNotIn(weg, namen,
                             "%s haette mit Build 708 entfallen sollen" % weg)

        # ... und der gemeinsame Weg wird wirklich benutzt.
        self.assertIn("build_export_context", quelle)
        self.assertIn("melde_rahmen_befunde", quelle)

    def test_xa07_ein_fehler_der_kettenpruefung_beendet_den_export_nicht(self):
        """
        Die alte Kopie fing NUR sqlite3.OperationalError. Ein Attribut- oder
        Importfehler aus AuditLog schlug durch und beendete den Export - an
        einer Angabe, die den Rahmen betrifft und nicht die Daten. Der
        context_builder faengt alles (RF06); hier die Gegenprobe mit einem
        Fehler, den die alte Kopie NICHT gefangen haette.
        """
        from management.export.rahmen_befund import FELD_KETTE

        class _Bockig:
            """Eine Verbindung, die bei jedem Zugriff etwas anderes wirft."""
            def execute(self, *_a, **_k):
                raise AttributeError("kein execute")

        ctx = context_builder.build_export_context(
            con=_Bockig(), db_path="/gibt/es/nicht.db", actor="h1",
            now_utc="2026-08-12 12:00 UTC")

        self.assertIsNone(ctx.chain_ok)
        self.assertTrue(ctx.hat_befund(FELD_KETTE))

    def test_xa08_der_katalogeintrag_beschreibt_den_neuen_stand(self):
        from management.help import cli_katalog

        eintrag = cli_katalog.eintrag("export_admin")
        self.assertIsNotNone(eintrag)
        text = " ".join(eintrag.tiefe.warnungen) + " " + (eintrag.hinweis or "")

        self.assertIn("Build 708", text)
        self.assertIn("nicht ermittelbar", text)
        # Die gebrochene Kette bleibt ausdruecklich davon unterschieden.
        self.assertIn("gebrochen", text.lower())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
