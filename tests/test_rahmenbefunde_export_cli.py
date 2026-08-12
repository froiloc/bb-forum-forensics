# =============================================================================
# tests/test_rahmenbefunde_export_cli.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem
# =============================================================================
# Testsuite zu Vorgang 70641ff9 (Build 706):
#   "Fuenf Export-CLIs melden Rahmenbefunde noch nicht zur Laufzeit"
#
# WAS BEIM BAUEN DAZUKAM UND WARUM ES DIE FAELLE PRAEGT:
#   Der Vorgang war als Nachzug gedacht - je Werkzeug eine Zeile. Beim
#   Nachmessen zeigte sich bei zwei der fuenf ein schwererer Befund:
#   '--coordinator-db' ist bei 'glossary_admin export-html' und
#   'ausschleus_admin finalize' OPTIONAL, und OHNE die Angabe bauten sich
#   beide bis Build 702 einen Ersatzkontext von Hand - Buildnummer 0,
#   Ersteller 'unbekannt', kein Wort. Das ist derselbe Befund wie in Vorgang
#   ff7e80ab, aber am REGELWEG statt am Fehlerweg, und bei ausschleus_admin
#   betrifft er die UEBERGABE.txt an die Staatsanwaltschaft.
#   Die Buildnummer war dabei die ganze Zeit verfuegbar: sie steht in
#   build.json und braucht keine Datenbank.
#
#   RM01 — Rahmen ohne DB: Buildnummer echt (NICHT 0), zwei Befunde mit Grund
#   RM02 — Rahmen ohne DB: Rohwert aus --actor bleibt und wird gekennzeichnet
#   RM03 — Rahmen ohne DB: unlesbare build.json -> dritter Befund, Reihenfolge
#   RM04 — glossary OHNE --coordinator-db: Meldung, echte Buildnummer, rc 0
#   RM05 — glossary MIT DB und --actor: KEINE Meldung (Gegenprobe zu RM04)
#   RM06 — glossary mit unlesbarer DB: der Grund nennt den Fehler
#   RM07 — ausschleus finalize OHNE DB: Meldung, echte Buildnummer in
#          UEBERGABE.txt, rc 0
#   RM08 — ausschleus finalize MIT DB und --actor: KEINE Meldung, Manifest
#          ohne Befundzeile
#   RM09 — dashboard_admin export-html: ohne --actor Meldung, mit --actor still
#   RM10 — workload_admin export-html: dasselbe
#   RM11 — support_overview_admin export-html: dasselbe
#   RM12 — der Nachsatz spricht vom DOKUMENT, nicht vom Bericht
#
# GEGENPROBE (fallen gegen den Stand aus Build 702):
#   RM01-RM04, RM06-RM12. RM05 muss AUCH gegen Build 702 gruen sein - er
#   haelt fest, dass der Regelfall unveraendert schweigt.
#
# Version: v0.8.706 · Build: 706 · 2026-08-12
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
from management.export.context_builder import (                        # noqa: E402
    build_export_context_ohne_db,
)
from management.export.export_envelope import ExportEnvelope           # noqa: E402
from management.export.rahmen_befund import (                          # noqa: E402
    FELD_BUILD, FELD_ERSTELLER, FELD_KETTE,
)

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _echte_buildnummer() -> int:
    with open(os.path.join(WURZEL, "build.json"), encoding="utf-8") as fh:
        return int(json.load(fh)["build"])


def _pfad_umlenken(ziel_ordner):
    """
    Laesst _build_number() in einen Ordner unserer Wahl greifen.

    Wie in EV06 (Build 702) wird die QUELLE umgelenkt und nicht die Funktion
    ersetzt: sonst pruefte der Fall nur noch sein eigenes Testdouble.
    _build_number bildet 'Path(__file__).resolve().parents[2] / "build.json"';
    ein dreifach geschachtelter Pfad landet damit genau in 'ziel_ordner'.
    """
    from pathlib import Path as _EchterPath
    return lambda _a: _EchterPath(ziel_ordner) / "a" / "b" / "c"


# =============================================================================
# RM01-RM03 — der Rahmen ohne Datenbank
# =============================================================================
class Rm01BisRm03OhneDb(unittest.TestCase):

    GRUND = "keine coordinator.db angegeben (--coordinator-db)"

    def test_rm01_buildnummer_ist_echt_und_zwei_befunde_tragen_den_grund(self):
        """
        DER KERN DIESER LIEFERUNG: die Buildnummer braucht keine Datenbank.
        Sie steht in build.json (GR4). Sie auf 0 zu setzen, weil eine
        Datenbank fehlt, warf eine Angabe weg, die vorlag.
        """
        ctx = build_export_context_ohne_db(
            grund=self.GRUND, aktenzeichen="Kennzahlen-Glossar",
            now_utc="2026-08-12 12:00 UTC")

        self.assertEqual(ctx.build_number, _echte_buildnummer())
        self.assertNotEqual(ctx.build_number, 0)
        self.assertFalse(ctx.hat_befund(FELD_BUILD))

        # Was OHNE Datenbank nicht zu ermitteln ist, wird benannt - nicht
        # unterschlagen (GR1).
        self.assertTrue(ctx.hat_befund(FELD_KETTE))
        self.assertTrue(ctx.hat_befund(FELD_ERSTELLER))
        for b in ctx.rahmen_befunde:
            self.assertIn(self.GRUND, b.grund)

        lines = ExportEnvelope(ctx).erzeugungsvermerk_lines()
        self.assertIn("Werkzeug-Build: %d" % _echte_buildnummer(), lines)
        self.assertNotIn("Werkzeug-Build: 0", lines)
        self.assertIn("Audit-Kette: nicht geprueft", lines)

    def test_rm02_rohwert_aus_actor_bleibt_und_wird_gekennzeichnet(self):
        mit = build_export_context_ohne_db(grund=self.GRUND, actor="h012345",
                                           now_utc="2026-08-12 12:00 UTC")
        zeile = ExportEnvelope(mit).erzeugungsvermerk_lines()[0]
        self.assertIn("h012345", zeile)          # die Spur bleibt
        self.assertIn("nicht aufgeloest", zeile)  # aber ungeprueft

        ohne = build_export_context_ohne_db(grund=self.GRUND,
                                            now_utc="2026-08-12 12:00 UTC")
        self.assertEqual(ohne.ersteller, "unbekannt")

    def test_rm03_unlesbare_build_json_ergibt_dritten_befund(self):
        tmp = tempfile.mkdtemp()
        original = context_builder.Path
        context_builder.Path = _pfad_umlenken(tmp)   # dort liegt keine build.json
        try:
            ctx = build_export_context_ohne_db(grund=self.GRUND,
                                               now_utc="2026-08-12 12:00 UTC")
        finally:
            context_builder.Path = original
            os.rmdir(tmp)

        self.assertTrue(ctx.hat_befund(FELD_BUILD))
        # Reihenfolge wie in build_export_context (Kette, Identitaet,
        # Buildnummer) - ein Vermerk, dessen Zeilen bei jedem Lauf anders
        # stehen, laesst sich zwischen zwei Abgaben nicht vergleichen.
        self.assertEqual([b.feld for b in ctx.rahmen_befunde],
                         [FELD_KETTE, FELD_ERSTELLER, FELD_BUILD])


# =============================================================================
# RM04-RM12 — die Werkzeuge
# =============================================================================
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


class WerkzeugFall(unittest.TestCase):
    """
    Gemeinsame Grundlage: EIN vollstaendig migrierter Wegwerf-Bestand mit
    genau einer bekannten Person ('h012345'), damit '--actor h012345' den
    Regelfall herstellt und das Weglassen von '--actor' den Ausfall.
    """

    @classmethod
    def setUpClass(cls):
        import management.migrations.coordinator as coordinator_migrations
        from management.audit.audit_log import AuditLog
        from management.migrations.runner import MigrationRunner, discover

        cls._tmp = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls._tmp, "coordinator.db")
        con = sqlite3.connect(cls.db_path)
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
        for wurzel, _dirs, dateien in os.walk(self._out, topdown=False):
            for fn in dateien:
                try:
                    os.remove(os.path.join(wurzel, fn))
                except OSError:
                    pass
            if wurzel != self._out:
                os.rmdir(wurzel)
        os.rmdir(self._out)

    def _lauf(self, modul, argv):
        """main() ausfuehren, (rc, stderr-Text) liefern."""
        alt = sys.stderr
        puffer = io.StringIO()
        try:
            sys.stderr = puffer
            rc = modul.main(argv)
        finally:
            sys.stderr = alt
        return rc, puffer.getvalue()

    def _lies(self, name):
        with open(os.path.join(self._out, name), encoding="utf-8") as fh:
            return fh.read()


# -- RM04-RM06 — glossary_admin ----------------------------------------------
class Rm04BisRm06Glossary(WerkzeugFall):

    def test_rm04_ohne_coordinator_db_meldet_und_traegt_echte_buildnummer(self):
        """
        DER REGELWEG dieses Befehls: '--coordinator-db' ist optional. Bis
        Build 702 entstand hier ein Dokument mit 'Werkzeug-Build: 0' und
        'Erstellt von: unbekannt' - wortlos, Rueckgabewert 0.
        """
        from management.stats import glossary_admin

        rc, err = self._lauf(glossary_admin, [
            "export-html", "--out", os.path.join(self._out, "g.html")])
        doku = self._lies("g.html")

        self.assertEqual(rc, 0)
        self.assertIn("[glossary] WARNUNG", err)
        self.assertIn("Belegkette", err)
        self.assertIn("Identitaet", err)
        self.assertIn("--coordinator-db", err)

        self.assertIn("Werkzeug-Build: %d" % _echte_buildnummer(), doku)
        self.assertNotIn("Werkzeug-Build: 0", doku)
        self.assertIn("Erzeugungsvermerk unvollstaendig", doku)

    def test_rm05_mit_db_und_actor_schweigt_das_werkzeug(self):
        """Gegenprobe: eine Warnung, die immer kommt, wird nicht gelesen."""
        from management.stats import glossary_admin

        rc, err = self._lauf(glossary_admin, [
            "export-html", "--out", os.path.join(self._out, "g.html"),
            "--coordinator-db", self.db_path, "--actor", "h012345"])
        doku = self._lies("g.html")

        self.assertEqual(rc, 0)
        self.assertNotIn("WARNUNG", err)
        self.assertNotIn("Erzeugungsvermerk unvollstaendig", doku)
        self.assertIn("Muster, Erika (h012345)", doku)

    def test_rm06_unlesbare_db_nennt_den_fehler_als_grund(self):
        """
        Die drei Lagen duerfen nicht gleich klingen: 'nicht angegeben' und
        'angegeben, aber kaputt' verlangen verschiedene Abhilfe.
        """
        from management.stats import glossary_admin

        rc, err = self._lauf(glossary_admin, [
            "export-html", "--out", os.path.join(self._out, "g.html"),
            "--coordinator-db", os.path.join(self._out, "gibtsnicht.db")])

        self.assertEqual(rc, 0)
        self.assertIn("WARNUNG", err)
        self.assertIn("coordinator.db nicht lesbar", err)
        self.assertNotIn("keine coordinator.db angegeben", err)


# -- RM07-RM08 — ausschleus_admin --------------------------------------------
class Rm07BisRm08Ausschleus(WerkzeugFall):

    def _paket(self):
        """Ein Ausschleus-Verzeichnis mit genau einem gepruefen Artefakt."""
        from management.export import ausschleus_admin

        verz = os.path.join(self._out, "paket")
        os.makedirs(verz, exist_ok=True)
        quelle = os.path.join(self._out, "probe.txt")
        with open(quelle, "w", encoding="utf-8") as fh:
            fh.write("unverfaenglicher Testinhalt\n")
        self._lauf(ausschleus_admin, [
            "add", "--dir", verz, "--file", quelle, "--kind", "report_pdf",
            "--source-ref", "uid=4711", "--cleared-by", "h012345",
            "--unbedenklich"])
        return ausschleus_admin, verz

    def test_rm07_finalize_ohne_db_meldet_und_stempelt_echte_buildnummer(self):
        """
        HIER WIEGT ES AM SCHWERSTEN: der Vermerk dieses Laufs wird in
        UEBERGABE.txt gestempelt und geht mit dem Paket an die
        Staatsanwaltschaft.
        """
        modul, verz = self._paket()

        rc, err = self._lauf(modul, ["finalize", "--dir", verz])
        with open(os.path.join(verz, "UEBERGABE.txt"), encoding="utf-8") as fh:
            uebergabe = fh.read()

        self.assertEqual(rc, 0)
        self.assertIn("[ausschleus] WARNUNG", err)
        self.assertIn("Werkzeug-Build: %d" % _echte_buildnummer(), uebergabe)
        self.assertNotIn("Werkzeug-Build: 0", uebergabe)
        self.assertIn("Erzeugungsvermerk unvollstaendig", uebergabe)

    def test_rm08_finalize_mit_db_und_actor_schweigt(self):
        modul, verz = self._paket()

        rc, err = self._lauf(modul, [
            "finalize", "--dir", verz, "--coordinator-db", self.db_path,
            "--actor", "h012345"])
        with open(os.path.join(verz, "UEBERGABE.txt"), encoding="utf-8") as fh:
            uebergabe = fh.read()
        with open(os.path.join(verz, "manifest.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)

        self.assertEqual(rc, 0)
        self.assertNotIn("WARNUNG", err)
        self.assertNotIn("Erzeugungsvermerk unvollstaendig", uebergabe)
        # Auch das Manifest fuehrt den Vermerk; es darf dort nichts anderes
        # stehen als in der UEBERGABE.txt.
        vermerk = "\n".join(manifest.get("erzeugungsvermerk", []))
        self.assertNotIn("unvollstaendig", vermerk)
        self.assertIn("Werkzeug-Build: %d" % _echte_buildnummer(), vermerk)


# -- RM09-RM11 — die drei Sichten-Exporte ------------------------------------
class Rm09BisRm11Sichten(WerkzeugFall):
    """
    Bei diesen dreien war die Kennzeichnung IM DOKUMENT seit Build 702 schon
    richtig - gefehlt hat nur die Meldung zur Laufzeit. Die Faelle pruefen
    deshalb beide Seiten: dass sie kommt, und dass sie im Regelfall ausbleibt.
    """

    def _pruefe(self, modul, praefix, dateiname):
        ziel = os.path.join(self._out, dateiname)

        # (1) ohne --actor: der OS-Benutzer des Laufs ist keinem
        #     person-Datensatz zugeordnet -> Identitaet nicht aufloesbar.
        rc, err = self._lauf(modul, [
            "export-html", "--coordinator-db", self.db_path, "--out", ziel])
        self.assertEqual(rc, 0, praefix)
        self.assertIn("%s WARNUNG" % praefix, err, praefix)
        self.assertIn("Identitaet", err, praefix)
        self.assertIn("Weitergabe", err, praefix)

        # (2) mit --actor: Regelfall, kein Wort.
        rc, err = self._lauf(modul, [
            "export-html", "--coordinator-db", self.db_path, "--out", ziel,
            "--actor", "h012345"])
        self.assertEqual(rc, 0, praefix)
        self.assertNotIn("WARNUNG", err, praefix)
        with open(ziel, encoding="utf-8") as fh:
            doku = fh.read()
        self.assertIn("Werkzeug-Build: %d" % _echte_buildnummer(), doku,
                      praefix)
        self.assertNotIn("Erzeugungsvermerk unvollstaendig", doku, praefix)

    def test_rm09_dashboard_admin(self):
        from management.dashboard import dashboard_admin
        self._pruefe(dashboard_admin, "[dashboard_admin]", "d.html")

    def test_rm10_workload_admin(self):
        from management.workload import workload_admin
        self._pruefe(workload_admin, "[workload_admin]", "w.html")

    def test_rm11_support_overview_admin(self):
        from management.support_overview import support_overview_admin
        self._pruefe(support_overview_admin, "[support_overview_admin]",
                     "s.html")


# -- RM12 — Wortlaut des Nachsatzes ------------------------------------------
class Rm12Nachsatz(unittest.TestCase):

    def test_rm12_der_nachsatz_spricht_vom_dokument(self):
        """
        Bis Build 702 lautete er 'Der erzeugte Bericht ...'. Seit Build 706
        nutzen ihn auch ein Glossar, eine StA-Uebergabe und drei
        Sichten-Exporte - keines davon ist ein Bericht. Ein Nachsatz, der die
        Sache falsch benennt, laesst den Leser zweifeln, ob er gemeint ist.
        """
        from management.export.rahmen_befund import RahmenBefund
        from management.export.rahmen_meldung import melde_rahmen_befunde

        ctx = build_export_context_ohne_db(
            grund="Grund", now_utc="2026-08-12 12:00 UTC")
        self.assertGreater(len(ctx.rahmen_befunde), 0)

        puffer = io.StringIO()
        melde_rahmen_befunde("[x]", ctx, puffer)
        nachsatz = puffer.getvalue().strip().split("\n")[-1]

        self.assertIn("Dokument", nachsatz)
        self.assertNotIn("Bericht", nachsatz)
        self.assertIn("Weitergabe", nachsatz)
        # Der Befund selbst bleibt unangetastet.
        self.assertIn("nicht ermittelbar",
                      RahmenBefund(FELD_KETTE, "Grund").als_zeile())


# -- RM13 — die Hilfe darf den behobenen Zustand nicht weiter behaupten ------
class Rm13Hilfe(unittest.TestCase):
    """
    Bei 'glossary_admin' stand im Katalog, der Ausfall stehe "auf der
    Fehlerausgabe". Gemessen am 12.08.2026 stand dort NICHTS. Das ist der
    unangenehmere von zwei Fehlern: eine Hilfe, die eine Meldung ZUSICHERT,
    die es nicht gibt, laesst den Leser darauf vertrauen, dass er einen
    Ausfall bemerken wuerde.
    """

    def _warnungen(self, schluessel):
        from management.help import cli_katalog

        eintrag = cli_katalog.eintrag(schluessel)
        self.assertIsNotNone(eintrag, "Kein Katalogeintrag '%s'" % schluessel)
        return " ".join(eintrag.tiefe.warnungen)

    def test_rm13_alle_fuenf_eintraege_beschreiben_das_neue_verfahren(self):
        for schluessel in ("glossary_admin", "ausschleus_admin",
                           "dashboard_admin", "workload_admin",
                           "support_overview_admin"):
            text = self._warnungen(schluessel)
            self.assertIn("Build 706", text, schluessel)
            self.assertIn("Fehlerausgabe", text, schluessel)
            self.assertIn("Rueckgabewert bleibt 0", text, schluessel)

    def test_rm13b_glossary_behauptet_die_alte_lage_nicht_mehr(self):
        text = self._warnungen("glossary_admin")
        # Die alte, falsche Zusicherung darf nicht stehenbleiben ...
        self.assertNotIn("Datei OHNE Kettenspitze", text)
        # ... und die Buildnummer ist ausdruecklich ausgenommen.
        self.assertIn("Werkzeug-Build: 0", text)
        self.assertIn("build.json", text)

    def test_rm13c_ausschleus_benennt_das_abgabedokument(self):
        text = self._warnungen("ausschleus_admin")
        self.assertIn("UEBERGABE", text)
        self.assertIn("--actor", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
