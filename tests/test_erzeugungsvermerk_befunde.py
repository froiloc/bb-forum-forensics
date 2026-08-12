# =============================================================================
# tests/test_erzeugungsvermerk_befunde.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Export-Subsystem
# =============================================================================
# Testsuite zu Vorgang ff7e80ab (Build 702):
#   "Berichte entstehen still mit Ersatz-Erzeugungsvermerk (Build 0, unbekannt)"
#
# WAS HIER GEPRUEFT WIRD UND WARUM GENAU DAS:
#   Der Vorgang beanstandet nicht, DASS ein Bericht bei ausgefallenem Rahmen
#   entsteht — das ist gewollt. Er beanstandet, dass der Ausfall danach
#   nirgends steht: nicht auf der Fehlerausgabe und nicht im Dokument. Die
#   Faelle unten pruefen deshalb durchgehend die AUSKUNFT, nicht das Scheitern.
#
#   EV01 — RahmenBefund: Wortlaut fuer Vermerk und Meldung, Grund bleibt drin
#   EV02 — vollstaendiger Rahmen: Vermerk Zeile fuer Zeile wie vor Build 702
#   EV03 — Befund Buildnummer: 'nicht ermittelbar' statt '0', Grund darunter
#   EV04 — Befund Ersteller: Rohwert bleibt, wird als ungeprueft gekennzeichnet
#   EV05 — FELD_RAHMEN schlaegt auf JEDE Einzelangabe durch
#   EV06 — context_builder: unlesbare build.json -> Befund mit Grund
#   EV07 — context_builder: nicht aufloesbare Identitaet -> Befund, Rohwert bleibt
#   EV08 — context_builder: fehlendes audit_log -> Befund, chain_ok bleibt None
#   EV09 — context_builder wirft weiterhin nie (Gegenprobe zu RF06)
#   EV10 — melde_rahmen_befunde: je Befund eine Zeile + genau EIN Nachsatz
#   EV11 — melde_rahmen_befunde: vollstaendiger Rahmen -> keine Ausgabe
#   EV12 — forecast_report_admin: Ausfall wird gemeldet, Bericht traegt ihn,
#          Rueckgabewert bleibt 0
#   EV13 — status_report_admin: dasselbe
#   EV14 — beide Werkzeuge im Regelfall: KEINE Warnung (Gegenprobe zu EV12/13)
#   EV15 — Ersatzzweig (Rahmen gar nicht bildbar) -> FELD_RAHMEN, Meldung,
#          Bericht entsteht, Rueckgabewert 0
#
# GEGENPROBE (fallen gegen den Stand aus Build 698):
#   EV03, EV04, EV05, EV10, EV12, EV13, EV15 — nachgemessen, siehe
#   issue-tracker/eintraege_claude_Build702.json.
#   EV02 und EV14 muessen AUCH gegen Build 698 gruen sein: sie halten fest,
#   dass sich im Regelfall nichts geaendert hat.
#
# Version: v0.8.702 · Build: 702 · 2026-08-12
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

from management.export.export_envelope import (                      # noqa: E402
    ExportContext, ExportEnvelope,
)
from management.export.rahmen_befund import (                        # noqa: E402
    FELD_BUILD, FELD_ERSTELLER, FELD_KETTE, FELD_RAHMEN, RahmenBefund,
)
from management.export.rahmen_meldung import melde_rahmen_befunde    # noqa: E402
from management.export import context_builder                        # noqa: E402
from management.export.context_builder import build_export_context   # noqa: E402


# -- Bausteine ---------------------------------------------------------------

def _ctx(**over):
    """Ein vollstaendiger Rahmen; einzelne Angaben ueberschreibbar."""
    base = dict(
        behoerde="Polizei NRW — EK Zarewitsch",
        aktenzeichen="Prognosebericht",
        ersteller="h012345",
        build_number=702,
        generated_at="2026-08-12 12:00 UTC",
        chain_ok=True, chain_tip_seq=5, chain_tip_hash="ab" * 32,
    )
    base.update(over)
    return ExportContext(**base)


# =============================================================================
# EV01 — RahmenBefund
# =============================================================================
class Ev01BefundWortlaut(unittest.TestCase):

    def test_ev01_vermerkzeile_und_meldung_nennen_angabe_und_grund(self):
        b = RahmenBefund(FELD_BUILD, "build.json nicht lesbar: [Errno 2]")

        zeile = b.als_zeile()
        # Die FOLGE zuerst: wer den Vermerk ueberfliegt, soll nicht erst den
        # Grund lesen muessen, um zu erkennen, dass etwas fehlt.
        self.assertTrue(zeile.startswith("Erzeugungsvermerk unvollstaendig"))
        self.assertIn("Buildnummer", zeile)
        # Der Grund wird MITGEFUEHRT und nicht zusammengefasst: 'nicht
        # ermittelbar' allein beantwortet nicht, ob eine Datei fehlt oder ein
        # Verzeichnisdienst schweigt.
        self.assertIn("[Errno 2]", zeile)

        meldung = b.als_meldung("[forecast_report]")
        self.assertTrue(meldung.startswith("[forecast_report]"))
        self.assertIn("WARNUNG", meldung)
        self.assertIn("[Errno 2]", meldung)

    def test_ev01b_unbekannter_schluessel_wird_roh_gefuehrt(self):
        # Ein kuenftiger Schluessel ohne Eintrag in BEZEICHNUNG darf die
        # Auskunft nicht verschlucken (GR1) — er erscheint dann eben roh.
        b = RahmenBefund("etwas_neues", "Grund")
        self.assertIn("etwas_neues", b.als_zeile())
        self.assertIn("Grund", b.als_zeile())


# =============================================================================
# EV02-EV05 — Erzeugungsvermerk
# =============================================================================
class Ev02BisEv05Vermerk(unittest.TestCase):

    def test_ev02_vollstaendiger_rahmen_unveraendert(self):
        """
        Der Regelfall muss Zeichen fuer Zeichen der aus Build 469 bleiben.
        Ein Vermerk, der auch dann ueber sich selbst spricht, wenn nichts
        fehlt, stumpft ab — und jede Aenderung hier wuerde alle bestehenden
        Abgabedokumente von den kuenftigen unterscheidbar machen, ohne dass
        sich an der Sache etwas geaendert haette.
        """
        lines = ExportEnvelope(_ctx()).erzeugungsvermerk_lines()
        self.assertEqual(lines, [
            "Erstellt von: h012345",
            "Erstellt am: 2026-08-12 12:00 UTC",
            "Werkzeug-Build: 702",
            "Audit-Kette: INTAKT (Spitze seq=5, hash=%s)" % ("ab" * 32),
        ])

    def test_ev03_buildnummer_nicht_ermittelbar_statt_null(self):
        ctx = _ctx(build_number=0, rahmen_befunde=(
            RahmenBefund(FELD_BUILD, "build.json nicht lesbar: [Errno 2]"),))
        lines = ExportEnvelope(ctx).erzeugungsvermerk_lines()

        self.assertIn("Werkzeug-Build: nicht ermittelbar", lines)
        # DER KERN DES VORGANGS: die 0 darf nirgends mehr wie eine Angabe
        # aussehen.
        self.assertNotIn("Werkzeug-Build: 0", lines)
        # ... und der Grund steht darunter.
        self.assertTrue(any("[Errno 2]" in z for z in lines))

        # Auch in den abgeleiteten Ausgabeformen (HTML-Fuss, Textfuss).
        env = ExportEnvelope(ctx)
        self.assertIn("Werkzeug-Build: nicht ermittelbar", env.footer_text("d"))
        self.assertIn("Werkzeug-Build: nicht ermittelbar", env.footer_html("d"))

    def test_ev04_ersteller_bleibt_erhalten_und_wird_gekennzeichnet(self):
        """
        Der Rohwert wird NICHT ersetzt: er ist die einzige Spur, die es dann
        noch gibt, und er ist nicht falsch — nur ungeprueft.
        """
        ctx = _ctx(ersteller="h999", rahmen_befunde=(
            RahmenBefund(FELD_ERSTELLER,
                         "Identitaet nicht aufloesbar: no such table"),))
        zeile = ExportEnvelope(ctx).erzeugungsvermerk_lines()[0]
        self.assertIn("h999", zeile)
        self.assertIn("nicht aufgeloest", zeile)

    def test_ev04b_anzeigename_bleibt_neben_dem_kontonamen(self):
        ctx = _ctx(ersteller="h001", anzeigename="Chefin", rahmen_befunde=(
            RahmenBefund(FELD_ERSTELLER, "Grund"),))
        zeile = ExportEnvelope(ctx).erzeugungsvermerk_lines()[0]
        self.assertIn("Chefin (h001)", zeile)
        self.assertIn("nicht aufgeloest", zeile)

    def test_ev05_feld_rahmen_schlaegt_auf_jede_angabe_durch(self):
        """
        Konnte der Rahmen als GANZES nicht gebildet werden, ist keine einzelne
        Angabe belastbar — auch nicht die, die zufaellig plausibel aussieht.
        """
        ctx = _ctx(build_number=0, ersteller="h777", rahmen_befunde=(
            RahmenBefund(FELD_RAHMEN, "Erzeugungsrahmen nicht bildbar: X"),))

        self.assertTrue(ctx.hat_befund(FELD_BUILD))
        self.assertTrue(ctx.hat_befund(FELD_ERSTELLER))
        self.assertTrue(ctx.hat_befund(FELD_KETTE))
        self.assertFalse(ctx.rahmen_vollstaendig())

        lines = ExportEnvelope(ctx).erzeugungsvermerk_lines()
        self.assertIn("Werkzeug-Build: nicht ermittelbar", lines)
        self.assertIn("nicht aufgeloest", lines[0])

    def test_ev05b_vollstaendiger_rahmen_meldet_keinen_befund(self):
        ctx = _ctx()
        self.assertTrue(ctx.rahmen_vollstaendig())
        for feld in (FELD_BUILD, FELD_ERSTELLER, FELD_KETTE, FELD_RAHMEN):
            self.assertFalse(ctx.hat_befund(feld), feld)


# =============================================================================
# EV06-EV09 — context_builder
# =============================================================================
class Ev06BisEv09Builder(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")

    def tearDown(self):
        for fn in os.listdir(self._tmp):
            try:
                os.remove(os.path.join(self._tmp, fn))
            except OSError:
                pass
        os.rmdir(self._tmp)

    def _con(self, with_audit=True):
        con = sqlite3.connect(self.db_path)
        if with_audit:
            con.execute(
                "CREATE TABLE audit_log(seq INTEGER PRIMARY KEY AUTOINCREMENT,"
                "ts INTEGER, actor_id INTEGER, event_type TEXT,"
                "target_type TEXT, target_id TEXT, content TEXT, meta TEXT,"
                "prev_hash TEXT, row_hash TEXT)")
        con.commit()
        return con

    def _lenke_build_json_um(self, ziel_ordner):
        """
        Laesst _build_number() in einen Ordner unserer Wahl greifen, ohne die
        echte build.json anzufassen.

        WARUM SO UND NICHT MIT EINEM PATCH AUF _build_number(): waere die
        Funktion selbst ersetzt, pruefte der Fall nur noch das Testdouble.
        Hier wird die QUELLE umgelenkt und die Funktion echt durchlaufen —
        einschliesslich ihres except-Zweigs, um den es geht.
        _build_number bildet 'Path(__file__).resolve().parents[2] /
        "build.json"'; ein dreifach geschachtelter Pfad landet damit genau in
        'ziel_ordner'.
        """
        from pathlib import Path as _EchterPath

        def _fake_path(_arg):
            return _EchterPath(ziel_ordner) / "a" / "b" / "c"

        return _fake_path

    def test_ev06_unlesbare_build_json_ergibt_befund_mit_grund(self):
        original = context_builder.Path
        context_builder.Path = self._lenke_build_json_um(self._tmp)
        try:
            # In self._tmp liegt KEINE build.json -> FileNotFoundError.
            con = self._con()
            try:
                ctx = build_export_context(con=con, db_path=self.db_path,
                                           actor="h9",
                                           now_utc="2026-08-12 12:00 UTC")
            finally:
                con.close()
        finally:
            context_builder.Path = original

        self.assertEqual(ctx.build_number, 0)
        self.assertTrue(ctx.hat_befund(FELD_BUILD))
        befund = [b for b in ctx.rahmen_befunde if b.feld == FELD_BUILD][0]
        self.assertIn("build.json", befund.grund)
        # Und der Vermerk zeigt die 0 nicht mehr als Angabe.
        self.assertIn("Werkzeug-Build: nicht ermittelbar",
                      ExportEnvelope(ctx).erzeugungsvermerk_lines())

    def test_ev06b_kaputte_build_json_ergibt_ebenfalls_befund(self):
        with open(os.path.join(self._tmp, "build.json"), "w",
                  encoding="utf-8") as fh:
            fh.write("{kein json")

        original = context_builder.Path
        context_builder.Path = self._lenke_build_json_um(self._tmp)
        try:
            con = self._con()
            try:
                ctx = build_export_context(con=con, db_path=self.db_path,
                                           actor="h9",
                                           now_utc="2026-08-12 12:00 UTC")
            finally:
                con.close()
        finally:
            context_builder.Path = original

        self.assertTrue(ctx.hat_befund(FELD_BUILD))

    def test_ev07_identitaet_nicht_aufloesbar_ergibt_befund(self):
        """
        Baut auf RF07 auf: dort wurde nur festgehalten, DASS der Rohwert
        stehenbleibt. Hier kommt dazu, dass der Grund nicht mehr verlorengeht.
        """
        con = self._con(with_audit=True)
        try:
            ctx = build_export_context(con=con, db_path=self.db_path,
                                       actor="hXYZ",
                                       now_utc="2026-08-12 12:00 UTC")
        finally:
            con.close()

        self.assertEqual(ctx.ersteller, "hXYZ")     # RF07 bleibt gueltig
        self.assertTrue(ctx.hat_befund(FELD_ERSTELLER))
        befund = [b for b in ctx.rahmen_befunde if b.feld == FELD_ERSTELLER][0]
        self.assertIn("Identitaet nicht aufloesbar", befund.grund)

    def test_ev08_fehlendes_audit_log_ergibt_kettenbefund(self):
        """Baut auf RF06 auf (chain_ok bleibt None) und ergaenzt den Grund."""
        con = self._con(with_audit=False)
        try:
            ctx = build_export_context(con=con, db_path=self.db_path,
                                       actor="h9",
                                       now_utc="2026-08-12 12:00 UTC")
        finally:
            con.close()

        self.assertIsNone(ctx.chain_ok)             # RF06 bleibt gueltig
        self.assertTrue(ctx.hat_befund(FELD_KETTE))
        self.assertIn("nicht geprueft", ExportEnvelope(ctx).integrity_line())

    def test_ev09_builder_wirft_weiterhin_nie(self):
        """
        Gegenprobe zu RF06 unter der Aenderung: ein Export darf nicht am
        Rahmen scheitern. Hier faellt ALLES gleichzeitig aus.
        """
        con = self._con(with_audit=False)
        original = context_builder.Path
        context_builder.Path = self._lenke_build_json_um(self._tmp)
        try:
            ctx = build_export_context(con=con, db_path="/gibt/es/nicht.db",
                                       actor=None,
                                       now_utc="2026-08-12 12:00 UTC")
        finally:
            context_builder.Path = original
            con.close()

        # Drei Ausfaelle, drei Befunde — keiner still uebersprungen (GR1).
        felder = sorted(b.feld for b in ctx.rahmen_befunde)
        self.assertEqual(felder, sorted([FELD_BUILD, FELD_ERSTELLER,
                                         FELD_KETTE]))
        # Die Reihenfolge ist die des Zusammenbaus und damit stabil: ein
        # Vermerk, dessen Zeilen bei jedem Lauf anders stehen, laesst sich
        # zwischen zwei Abgaben nicht vergleichen.
        self.assertEqual([b.feld for b in ctx.rahmen_befunde],
                         [FELD_KETTE, FELD_ERSTELLER, FELD_BUILD])


# =============================================================================
# EV10-EV11 — melde_rahmen_befunde
# =============================================================================
class Ev10BisEv11Meldung(unittest.TestCase):

    def test_ev10_je_befund_eine_zeile_und_genau_ein_nachsatz(self):
        ctx = _ctx(rahmen_befunde=(
            RahmenBefund(FELD_BUILD, "build.json nicht lesbar: [Errno 2]"),
            RahmenBefund(FELD_ERSTELLER, "Identitaet nicht aufloesbar: X"),
        ))
        puffer = io.StringIO()
        anzahl = melde_rahmen_befunde("[forecast_report]", ctx, puffer)

        self.assertEqual(anzahl, 2)
        zeilen = puffer.getvalue().strip().split("\n")
        self.assertEqual(len(zeilen), 3)            # 2 Befunde + 1 Nachsatz
        self.assertTrue(all(z.startswith("[forecast_report]") for z in zeilen))
        self.assertIn("[Errno 2]", zeilen[0])
        # Der Nachsatz benennt die FOLGE fuer die weitergebende Person.
        self.assertIn("KEINEN vollstaendigen", zeilen[2])
        self.assertIn("Weitergabe", zeilen[2])

    def test_ev11_vollstaendiger_rahmen_schweigt(self):
        puffer = io.StringIO()
        self.assertEqual(melde_rahmen_befunde("[x]", _ctx(), puffer), 0)
        self.assertEqual(puffer.getvalue(), "")

    def test_ev11b_kein_kontext_ist_kein_absturz(self):
        puffer = io.StringIO()
        self.assertEqual(melde_rahmen_befunde("[x]", None, puffer), 0)
        self.assertEqual(puffer.getvalue(), "")


# =============================================================================
# EV12-EV15 — die beiden Berichtswerkzeuge (der eigentliche Vorgang)
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


class Ev12BisEv15Werkzeuge(unittest.TestCase):
    """
    Diese Faelle fahren die Werkzeuge als GANZES (main() mit argv), weil genau
    das der Weg ist, den der Vorgang beanstandet: Rueckgabewert 0, Datei da,
    keine Meldung. Ein Test auf der Ebene einzelner Funktionen haette den
    Befund nicht gezeigt.
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
        now = int(time.time())
        con.execute(_INVESTIGATORS)
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'h001', 'Alpha', 1, 1, 0, ?)", (now,))
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
        for fn in os.listdir(self._out):
            try:
                os.remove(os.path.join(self._out, fn))
            except OSError:
                pass
        os.rmdir(self._out)

    # -- Helfer --------------------------------------------------------------
    def _lauf(self, modul, argv, build_json_umlenken_nach=None,
              import_sabotieren=False):
        """
        Fuehrt main() aus und liefert (rc, stderr-Text, Berichtstext).

        'build_json_umlenken_nach' erzeugt den Ausfall der Buildnummer, ohne
        die echte build.json anzufassen. 'import_sabotieren' erzeugt den
        Ausfall des RAHMENS als Ganzes (der except-Zweig des Werkzeugs),
        indem der Modulname aus sys.modules genommen und blockiert wird.
        """
        from pathlib import Path as _EchterPath

        out = os.path.join(self._out, "bericht.html")
        argv = list(argv) + ["--coordinator-db", self.db_path,
                             "--out", out, "--format", "html"]

        alt_stderr, alt_path = sys.stderr, context_builder.Path
        gemerkt = sys.modules.pop("management.export.context_builder", None)
        puffer = io.StringIO()
        klasse_wiederherstellen = None
        try:
            sys.stderr = puffer
            if build_json_umlenken_nach is not None:
                context_builder.Path = (
                    lambda _a: _EchterPath(build_json_umlenken_nach)
                    / "a" / "b" / "c")
            if import_sabotieren:
                # Ein Platzhalter ohne das erwartete Attribut laesst den
                # 'from ... import build_export_context' mit ImportError
                # fallen — genau der Zweig, den der Vorgang benennt.
                class _Leer:
                    pass
                klasse_wiederherstellen = _Leer()
                sys.modules["management.export.context_builder"] = \
                    klasse_wiederherstellen
            else:
                sys.modules["management.export.context_builder"] = \
                    context_builder
            rc = modul.main(argv)
        finally:
            sys.stderr = alt_stderr
            context_builder.Path = alt_path
            if gemerkt is not None:
                sys.modules["management.export.context_builder"] = gemerkt
            else:  # pragma: no cover - nur wenn das Modul nie geladen war
                sys.modules.pop("management.export.context_builder", None)

        with open(out, encoding="utf-8") as fh:
            bericht = fh.read()
        return rc, puffer.getvalue(), bericht

    # -- EV12 ---------------------------------------------------------------
    def test_ev12_forecast_meldet_und_kennzeichnet(self):
        from management.stats import forecast_report_admin

        rc, err, bericht = self._lauf(
            forecast_report_admin, [],
            build_json_umlenken_nach=self._out)

        # (1) Die Meldung ist da — das war der Befund.
        self.assertIn("[forecast_report]", err)
        self.assertIn("WARNUNG", err)
        self.assertIn("Buildnummer", err)
        self.assertIn("Weitergabe", err)
        # (2) Der Bericht kennzeichnet den Ersatzvermerk.
        self.assertIn("nicht ermittelbar", bericht)
        self.assertNotIn("Werkzeug-Build: 0", bericht)
        # (3) Der Bericht entsteht trotzdem und der Rueckgabewert bleibt 0
        #     (Entscheidung Alex, 12.08.2026): ein geschriebenes Dokument
        #     nachtraeglich zu verwerfen, wuerde die Auskunft mitvernichten.
        self.assertEqual(rc, 0)
        self.assertIn("Prognose", bericht)

    # -- EV13 ---------------------------------------------------------------
    def test_ev13_status_meldet_und_kennzeichnet(self):
        from management.stats import status_report_admin

        rc, err, bericht = self._lauf(
            status_report_admin, [],
            build_json_umlenken_nach=self._out)

        self.assertIn("[status_report]", err)
        self.assertIn("WARNUNG", err)
        self.assertIn("Buildnummer", err)
        self.assertIn("nicht ermittelbar", bericht)
        self.assertNotIn("Werkzeug-Build: 0", bericht)
        self.assertEqual(rc, 0)

    # -- EV14 ---------------------------------------------------------------
    def test_ev14_regelfall_schweigt_weiterhin(self):
        """
        Gegenprobe: eine Warnung, die im Regelfall mitlaeuft, wird nach der
        dritten Ausgabe nicht mehr gelesen. Beide Werkzeuge duerfen bei
        vollstaendigem Rahmen KEINE Warnung ausgeben.

        '--actor h001' IST HIER NOTWENDIG UND KEIN KNIFF: ohne Angabe nimmt
        der IdentityResolver den OS-Benutzer der laufenden Sitzung, und der
        ist im Testbestand — wie auf jedem Rechner ausserhalb der
        Ermittlungs-VM — keinem person-Datensatz zugeordnet. Der Rahmen ist
        dann tatsaechlich unvollstaendig, und die Warnung ist richtig. Der
        REGELFALL, um den es in diesem Fall geht, ist der Lauf MIT
        aufloesbarer Identitaet.
        """
        from management.stats import forecast_report_admin
        from management.stats import status_report_admin

        for modul in (forecast_report_admin, status_report_admin):
            rc, err, bericht = self._lauf(modul, ["--actor", "h001"])
            self.assertEqual(rc, 0, modul.__name__)
            self.assertNotIn("WARNUNG", err, modul.__name__)
            self.assertNotIn("Erzeugungsvermerk unvollstaendig", bericht,
                             modul.__name__)
            # Die echte Buildnummer steht im Vermerk.
            with open(os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "build.json"), encoding="utf-8") as fh:
                erwartet = int(json.load(fh)["build"])
            self.assertIn("Werkzeug-Build: %d" % erwartet, bericht,
                          modul.__name__)

    # -- EV15 ---------------------------------------------------------------
    def test_ev15_ersatzzweig_meldet_ebenfalls(self):
        """
        Der Zweig, den der Vorgang woertlich benennt (Z. 110-115 / 89-94).
        Er ist enger als er aussieht — build_export_context wirft nie, also
        kann hier praktisch nur der import fallen. Genau den laesst dieser
        Fall fallen.
        """
        from management.stats import forecast_report_admin

        rc, err, bericht = self._lauf(forecast_report_admin, [],
                                      import_sabotieren=True)

        self.assertEqual(rc, 0)
        self.assertIn("Erzeugungsrahmen", err)
        self.assertIn("WARNUNG", err)
        # FELD_RAHMEN schlaegt auf alle Angaben durch: weder Buildnummer noch
        # Ersteller sind hier belastbar.
        self.assertIn("Werkzeug-Build: nicht ermittelbar", bericht)
        self.assertNotIn("Werkzeug-Build: 0", bericht)
        self.assertIn("nicht aufgeloest", bericht)


# =============================================================================
# EV16 — die Hilfe darf den behobenen Zustand nicht weiter behaupten
# =============================================================================
class Ev16Hilfe(unittest.TestCase):
    """
    Die Warnung im CLI-Katalog stand seit Build 613 als NOTLOESUNG dort: sie
    beschrieb, dass keine Meldung kommt. Bleibt so ein Text nach der Behebung
    stehen, ist er eine Falschangabe an genau der Stelle, an der jemand
    nachschlaegt, um sein Vorgehen danach zu richten — dieselbe Ueberlegung
    wie bei den Rechtetexten in M038 (Build 698).
    """

    def _warnungen(self, schluessel):
        from management.help import cli_katalog

        eintrag = cli_katalog.eintrag(schluessel)
        self.assertIsNotNone(eintrag, "Kein Katalogeintrag '%s'" % schluessel)
        return " ".join(eintrag.tiefe.warnungen)

    def test_ev16_beide_katalogeintraege_beschreiben_das_neue_verfahren(self):
        for schluessel in ("forecast_report_admin", "status_report_admin"):
            text = self._warnungen(schluessel)
            # Die Behauptung "ohne Meldung" darf nicht stehenbleiben.
            self.assertNotIn("ohne Meldung", text, schluessel)
            self.assertNotIn("Ersteller 'unbekannt'", text, schluessel)
            # Stattdessen: was das Werkzeug jetzt tut.
            self.assertIn("Build 702", text, schluessel)
            self.assertIn("nicht ermittelbar", text, schluessel)
            self.assertIn("Rueckgabewert bleibt 0", text, schluessel)
            # Und der Hinweis auf --actor, der den haeufigsten Ausfall
            # vermeidet (Befund beim Bauen: der OS-Benutzer eines
            # Stapellaufs ist in aller Regel kein person-Datensatz).
            self.assertIn("--actor", text, schluessel)

    def test_ev16b_hilfekapitel_sichert_die_kennzeichnung_zu(self):
        from management.help.inhalt.kennzahlen import STATS

        grenzen = [a for a in STATS.abschnitte if a.anker == "grenzen"][0]
        text = " ".join(grenzen.absaetze) + " " + " ".join(grenzen.liste)
        self.assertIn("nicht ermittelbar", text)
        self.assertIn("Erzeugungsvermerk", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
