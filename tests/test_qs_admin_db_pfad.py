# =============================================================================
# tests/test_qs_admin_db_pfad.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: QS-Stichprobe
# =============================================================================
# Testsuite zu Vorgang e61a7dd4 (Build 715):
#   "qs_admin erraet den Datenbankpfad statt abzubrechen"
#
# WORUM ES GEHT:
#   management/qs/qs_admin.py trug bis Build 712 den Rueckfallwert
#   _VORGABE_DB = "data/coordinator.db" — einen RELATIVEN Pfad. Wer das
#   Werkzeug aus einem anderen Verzeichnis aufrief, pruefte eine ANDERE
#   coordinator.db, ohne es zu merken. Bei einem Werkzeug, dessen ganze
#   Aufgabe die Qualitaetssicherung ist, ist das der unangenehmste Fall: ein
#   'DIE ZIEHUNG STIMMT' aus dem falschen Verzeichnis sieht aus wie ein
#   Befund und ist keiner.
#
#   Ab Build 715 gilt hier dieselbe Regel wie bei den uebrigen dreissig
#   Verwaltungswerkzeugen (core/werkzeug_konfig.py, seit Build 643/644):
#
#       Argument '--db'  >  paths.coordinator_db  >  ABBRUCH mit Klartext.
#
# WIE HIER GEMESSEN WIRD — und warum so:
#   Die Faelle wechseln das ARBEITSVERZEICHNIS und legen dort eine
#   ./data/coordinator.db ab, die NICHT gemeint ist. Genau daran entscheidet
#   sich der Vorgang: eine Pruefung, die nur die Aufloesungsfunktion
#   befragte, wuerde den gemeldeten Fall gar nicht beruehren. Welche Datei
#   das Werkzeug wirklich geoeffnet hat, wird nicht behauptet, sondern an der
#   AUSGABE abgelesen: die beiden Wegwerf-Bestaende unterscheiden sich in der
#   Zahl ihrer Ziehungen (einer hat eine, der andere keine).
#
#   QSD01 — ohne '--db' und ohne config.yaml: ABBRUCH, keine Datenbank
#   QSD02 — die Abbruchmeldung nennt BEIDE Wege und traegt das Werkzeug
#   QSD03 — ohne '--db': der Pfad kommt aus paths.coordinator_db
#   QSD04 — DER VORGANG SELBST: die ./data/coordinator.db im Arbeits-
#           verzeichnis wird NICHT mehr genommen, obwohl es sie gibt
#   QSD05 — '--db' schlaegt die config.yaml (Vorrang, Gegenrichtung)
#   QSD06 — '--db' und '--config' wirken VOR und HINTER dem Unterbefehl
#           (die in Build 541 erkaempfte Eigenschaft darf nicht verlorengehen)
#   QSD07 — die Herkunft steht auf stderr und NIE auf stdout
#   QSD08 — kein toter Zwilling: _VORGABE_DB ist wirklich weg
#   QSD09 — der Katalogeintrag (die HILFE zu diesem Werkzeug) beschreibt den
#           neuen Stand
#
# GEGENPROBE — WIRKLICH GEFAHREN und nicht abgeschaetzt: qs_admin.py UND
# cli_katalog.py auf den Stand 712 zurueckgesetzt (Commit d5aa196), Suite
# unveraendert, Python 3.14.0rc2 im Container.
#   FALLEN (8 von 9): QSD01, QSD02, QSD03, QSD04, QSD06, QSD07, QSD08, QSD09.
#   BESTEHT (1): QSD05 — und das ist richtig so. Er haelt fest, was sich
#     NICHT aendern durfte: ein ausdruecklich angegebenes '--db' gewinnt.
#     Das galt vorher wie nachher. Als Gegenprobe zur Aenderung taugt er
#     ausdruecklich NICHT; das gehoert gesagt, damit die Zahl '8 von 9'
#     nicht spaeter als '9' erinnert wird.
#   INNERHALB VON QSD06 fallen 2 der 4 Stellungen ('--config' vor und hinter
#     dem Unterbefehl — auf Stand 712 gibt es die Option nicht, argparse
#     bricht mit 'unrecognized arguments' ab). Die beiden '--db'-Stellungen
#     bestehen; sie sind die Eigenschaft aus Build 541, die zu bewahren war.
#
# Version: v0.8.715 · Build: 715 · 2026-08-13
# =============================================================================

import contextlib
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.cli_katalog import eintrag              # noqa: E402
from management.qs import qs_admin                           # noqa: E402

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Die config.yaml der Wegwerf-Bestaende. server.* und logging.* stehen darin,
#: weil ConfigLoader._validate() sie verlangt — ohne sie kaeme die Aufloesung
#: gar nicht bis zu dem Eintrag, um den es geht (dieselbe Lehre wie in
#: tests/test_cli_vorrang.py).
_CONFIG_VORLAGE = (
    "server:\n"
    "  host: \"127.0.0.2\"\n"
    "  port: 8080\n"
    "  mode: \"cli\"\n"
    "logging:\n"
    "  level: \"info\"\n"
    "paths:\n"
    "  coordinator_db: \"%s\"\n"
)

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


def _baue_coordinator(pfad: str) -> None:
    """
    Ein Wegwerf-Bestand in der Gestalt, die der Migrationslauf herstellt.

    Derselbe Aufbau wie in tests/test_export_admin_rahmen.py: die beiden
    Tabellen, die VOR den Migrationen dagewesen sein muessen, dann der
    Migrationslauf. Ohne ihn gaebe es die qs_*-Tabellen nicht (m034).
    """
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


def _ziehung_eintragen(pfad: str, seed: int) -> None:
    """
    Traegt EINE Ziehung ein — die Unterscheidungsmarke der beiden Bestaende.

    VON HAND und nicht ueber QsRepo.ziehen(): Der Weg ueber das Fachmodul
    braucht Faelle, Personen und einen Schreiber; er wuerde hier nichts
    belegen, was diese Suite prueft. Gebraucht wird allein ein Bestand, dessen
    AUSGABE sich vom anderen unterscheidet.

    'audit_seq' zeigt bewusst auf eine Nummer, die es im audit_log geben mag
    oder nicht: SQLite prueft Fremdschluessel nur bei eingeschaltetem PRAGMA,
    und qs_admin schaltet es nicht ein (es oeffnet mit mode=ro und setzt kein
    PRAGMA). Das ist hier kein Mangel des Wegwerf-Bestandes, sondern der
    Grund, warum er so einfach sein darf.
    """
    con = sqlite3.connect(pfad)
    con.isolation_level = None
    con.execute(
        "INSERT INTO qs_sample (id, gezogen_von, gezogen_at, verfahren, "
        "grundgesamtheit_n, stichprobe_n, seed, filter_json, bemerkung, "
        "audit_seq) VALUES (1, 1, ?, 'einfach', 0, 0, ?, '{}', "
        "'Wegwerf-Bestand der Testsuite', 1)",
        (int(time.time()), int(seed)))
    con.close()


def _lauf(argv, cwd):
    """
    Fuehrt qs_admin.main(argv) in 'cwd' aus und liefert (code, out, err).

    DAS ARBEITSVERZEICHNIS IST HIER DER PRUEFGEGENSTAND und nicht Beiwerk:
    der gemeldete Mangel bestand darin, dass der Datenbankpfad an ihm hing.

    'code' ist der Rueckgabewert von main() ODER der Wert eines SystemExit —
    der Abbruch der Aufloesung kommt als SystemExit('[qs_admin] ...') und
    haette sonst keinen vergleichbaren Rueckgabewert. Traegt der SystemExit
    einen Text statt einer Zahl, gilt der Rueckgabewert 1; genau so behandelt
    ihn der Python-Interpreter beim Aufruf von der Kommandozeile, und genau
    dieser Wert kommt beim Aufrufer an.
    """
    alt = os.getcwd()
    out, err = io.StringIO(), io.StringIO()
    os.chdir(cwd)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = qs_admin.main(argv)
            except SystemExit as exc:
                wert = exc.code
                if isinstance(wert, int):
                    code = wert
                elif wert is None:
                    code = 0
                else:
                    print(wert, file=sys.stderr)
                    code = 1
    finally:
        os.chdir(alt)
    return code, out.getvalue(), err.getvalue()


class QsAdminDbPfad(unittest.TestCase):
    """
    Der Aufbau ist bei jedem Fall derselbe und bildet die gemeldete Lage ab:

        <tmp>/bestand/coordinator.db   die GEMEINTE Datenbank — MIT Ziehung
        <tmp>/anderswo/                das Arbeitsverzeichnis
        <tmp>/anderswo/data/coordinator.db   die FALSCHE — OHNE Ziehung
        <tmp>/anderswo/config.yaml     zeigt auf die gemeinte

    Wer den geratenen relativen Pfad nimmt, landet bei der falschen und sagt
    'Keine Ziehung vorhanden'. Wer richtig aufloest, sieht die Ziehung.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="qsadmin_")
        os.makedirs(os.path.join(cls._tmp, "bestand"))
        cls.gemeint = os.path.join(cls._tmp, "bestand", "coordinator.db")
        _baue_coordinator(cls.gemeint)
        _ziehung_eintragen(cls.gemeint, seed=4711)

        cls.anderswo = os.path.join(cls._tmp, "anderswo")
        os.makedirs(os.path.join(cls.anderswo, "data"))
        cls.falsch = os.path.join(cls.anderswo, "data", "coordinator.db")
        _baue_coordinator(cls.falsch)          # ohne Ziehung — das ist die Marke

        cls.leer = os.path.join(cls._tmp, "leer")   # weder config noch data/
        os.makedirs(cls.leer)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    def setUp(self):
        """Die config.yaml wird je Fall frisch gelegt — Faelle duerfen sie
        veraendern, ohne den naechsten zu beeinflussen."""
        with open(os.path.join(self.anderswo, "config.yaml"), "w",
                  encoding="utf-8") as fh:
            fh.write(_CONFIG_VORLAGE % self.gemeint)
        # Die Herkunftsausgabe ist opt-in; sie darf nicht aus einem
        # vorangegangenen Fall stehenbleiben.
        os.environ.pop("AIW_KONFIG_HERKUNFT", None)

    # ------------------------------------------------------------------
    # QSD01/02 — der Abbruch
    # ------------------------------------------------------------------
    def test_qsd01_ohne_argument_und_ohne_config_bricht_es_ab(self):
        """
        QSD01: Kein '--db', keine config.yaml, kein ./data — Abbruch.

        DER KERN DES VORGANGS in seiner reinsten Form. Auf Stand 712 nahm das
        Werkzeug hier 'data/coordinator.db' an und meldete anschliessend
        'Datenbank nicht gefunden' (Rueckgabewert 2) — eine Meldung ueber die
        FOLGE des Ratens, nicht ueber das Raten. Jetzt bricht es ab (1), bevor
        es ueberhaupt eine Datei ins Auge fasst.
        """
        code, out, err = _lauf(["liste"], self.leer)
        self.assertEqual(code, 1, "Erwartet: Abbruch mit 1. Ausgabe:\n%s%s"
                         % (out, err))
        self.assertIn("Kein Wert fuer", err)
        self.assertEqual(out, "", "Auf stdout darf beim Abbruch nichts stehen "
                                  "— es gibt keinen Befund zu berichten.")
        self.assertNotIn("Datenbank nicht gefunden", err,
                         "Das waere die Meldung von Stand 712: sie setzt "
                         "voraus, dass ein Pfad geraten wurde.")

    def test_qsd02_die_abbruchmeldung_nennt_beide_wege(self):
        """
        QSD02: Eine Abbruchmeldung, die nicht sagt, WIE man es richtig macht,
        ist eine halbe Auskunft. Verlangt sind beide Wege und die Kennung des
        Werkzeugs — die Meldungen des Bestandes sind an ihrem '[werkzeug]'
        wiederzuerkennen.
        """
        _, _, err = _lauf(["liste"], self.leer)
        self.assertIn("[qs_admin]", err)
        self.assertIn("--db", err)
        self.assertIn("paths.coordinator_db", err)

    # ------------------------------------------------------------------
    # QSD03/04 — die Aufloesung
    # ------------------------------------------------------------------
    def test_qsd03_ohne_argument_kommt_der_pfad_aus_der_config(self):
        """
        QSD03: 'paths.coordinator_db' wird gelesen und benutzt. Beleg ist die
        Ziehung, die es NUR in der gemeinten Datenbank gibt.
        """
        code, out, err = _lauf(["liste"], self.anderswo)
        self.assertEqual(code, 0, err)
        self.assertIn("1 Ziehungen insgesamt", out)
        self.assertIn("4711", out, "Der Keim der Ziehung belegt, WELCHE "
                                   "Datenbank gelesen wurde.")

    def test_qsd04_die_datenbank_im_arbeitsverzeichnis_wird_nicht_genommen(self):
        """
        QSD04 — DER GEMELDETE FALL. Im Arbeitsverzeichnis LIEGT eine
        ./data/coordinator.db, und sie ist eine gueltige, lesbare
        coordinator.db. Auf Stand 712 hat das Werkzeug genau sie geoeffnet
        und 'Keine Ziehung vorhanden' gemeldet — einen Leerbefund ueber den
        falschen Bestand. Der Fall haelt fest, dass das nicht mehr geschieht.

        DIE GEGENPROBE STECKT IM AUFBAU: Waere die falsche Datenbank leer
        oder kaputt, wuerde der Fall auch dann anschlagen, wenn das Werkzeug
        sie oeffnete — und belegte dann nur, dass etwas schiefging. So belegt
        er, WELCHE der beiden gelesen wurde.
        """
        self.assertTrue(os.path.isfile(self.falsch),
                        "Aufbaufehler: die falsche Datenbank muss es geben.")
        code, out, err = _lauf(["liste"], self.anderswo)
        self.assertEqual(code, 0, err)
        self.assertNotIn("Keine Ziehung vorhanden", out,
                         "Das ist die Ausgabe der FALSCHEN Datenbank "
                         "(./data/coordinator.db im Arbeitsverzeichnis).")
        self.assertIn("1 Ziehungen insgesamt", out)

    def test_qsd05_argument_schlaegt_die_config(self):
        """
        QSD05: Die Gegenrichtung — und das, was sich NICHT aendern durfte.
        '--db' zeigt hier ausdruecklich auf die Datenbank OHNE Ziehung,
        waehrend die config.yaml auf die mit Ziehung zeigt. Gewinnen muss das
        Argument; ein Vorrang, der nur in eine Richtung stimmt, ist keiner.
        """
        code, out, err = _lauf(["liste", "--db", self.falsch], self.anderswo)
        self.assertEqual(code, 0, err)
        self.assertIn("Keine Ziehung vorhanden", out)
        self.assertNotIn("4711", out)

    # ------------------------------------------------------------------
    # QSD06 — die Bedienung
    # ------------------------------------------------------------------
    def test_qsd06_beide_stellungen_der_argumente(self):
        """
        QSD06: In Build 541 ist erkaempft worden, dass '--db' VOR und HINTER
        dem Unterbefehl stehen darf (Rauchprobe: die naheliegende Schreibweise
        scheiterte mit 'unrecognized arguments'). Das neue '--config' muss
        beides ebenso koennen — sonst hat der Umbau eine Bedienungseigenschaft
        wieder eingebuesst, die einmal Arbeit gekostet hat.

        Gemessen werden alle vier Stellungen. Jede muss die GEMEINTE Datenbank
        oeffnen, erkennbar am Keim 4711.
        """
        cfg = os.path.join(self.anderswo, "config.yaml")
        faelle = (
            (["liste", "--db", self.gemeint], "--db dahinter"),
            (["--db", self.gemeint, "liste"], "--db davor"),
            (["liste", "--config", cfg], "--config dahinter"),
            (["--config", cfg, "liste"], "--config davor"),
        )
        for argv, benennung in faelle:
            with self.subTest(stellung=benennung):
                code, out, err = _lauf(argv, self.leer)
                self.assertEqual(code, 0, "%s: %s" % (benennung, err))
                self.assertIn("4711", out, benennung)

    # ------------------------------------------------------------------
    # QSD07 — die Herkunft
    # ------------------------------------------------------------------
    def test_qsd07_herkunft_nur_auf_stderr_und_nur_auf_wunsch(self):
        """
        QSD07: Die Herkunftsauskunft beantwortet die Frage, die der Vorgang
        aufwirft — WELCHE Datei wurde geoeffnet. Sie ist opt-in und geht nach
        stderr; auf stdout waere sie bei einem Werkzeug mit '--json' ein
        Fehler und kein Hinweis (Begruendung im Kopf von
        core/werkzeug_konfig.py).

        Beide Richtungen werden gemessen: ohne die Umgebungsvariable darf
        KEINE Herkunftszeile erscheinen. Eine Auskunft, die immer kommt,
        belegt nicht, dass der Schalter wirkt.
        """
        _, out_aus, err_aus = _lauf(["liste"], self.anderswo)
        self.assertNotIn("[Konfig]", err_aus)
        self.assertNotIn("[Konfig]", out_aus)

        os.environ["AIW_KONFIG_HERKUNFT"] = "1"
        try:
            _, out_an, err_an = _lauf(["liste"], self.anderswo)
        finally:
            os.environ.pop("AIW_KONFIG_HERKUNFT", None)
        self.assertIn("[qs_admin][Konfig]", err_an)
        self.assertIn("paths.coordinator_db", err_an)
        self.assertIn(self.gemeint, err_an)
        self.assertNotIn("[Konfig]", out_an,
                         "Die Herkunft gehoert NIE auf stdout.")

    # ------------------------------------------------------------------
    # QSD08/09 — kein toter Zwilling, und die Hilfe sagt es
    # ------------------------------------------------------------------
    def test_qsd08_der_rueckfallwert_ist_wirklich_weg(self):
        """
        QSD08: Ein Umbau, der die alte Fassung danebenstehen laesst, ist
        halbfertig — der naechste Leser weiss dann nicht, welche gilt. Geprueft
        wird am Quelltext: keine Zuweisung von _VORGABE_DB mehr, und die
        gemeinsame Aufloesung ist eingebunden.

        Gesucht wird nach der ZUWEISUNG am Zeilenanfang und nicht nach dem
        blossen Vorkommen des Namens: Kommentar und Dokumentation nennen ihn
        weiterhin, und das sollen sie auch — sie erklaeren, was hier frueher
        stand und warum es weg ist. Ebenso wenig wird auf die Zeichenkette
        'data/coordinator.db' geprueft; sie steht in den Aufrufbeispielen des
        Dateikopfes, und dort gehoert sie hin.
        """
        with open(os.path.join(WURZEL, "management", "qs", "qs_admin.py"),
                  encoding="utf-8") as fh:
            quelle = fh.read()
        for nr, zeile in enumerate(quelle.splitlines(), 1):
            self.assertFalse(zeile.startswith("_VORGABE_DB"),
                             "Zeile %d: der Rueckfallwert wird noch zugewiesen."
                             % nr)
        self.assertIn("from core import werkzeug_konfig", quelle)
        self.assertIn("from core import werkzeug_konfig", quelle)
        self.assertIn("werkzeug_konfig.db_pfad", quelle)

    def test_qsd09_der_katalogeintrag_beschreibt_den_neuen_stand(self):
        """
        QSD09: Der CLI-Katalog IST die Hilfe zu diesem Werkzeug. Er hat den
        Mangel seit Build 640 zutreffend beschrieben — und damit
        zweiundsiebzig Builds lang eine Warnung ausgesprochen, statt dass er
        behoben war. Wird er jetzt nicht nachgezogen, warnt die Hilfe vor
        einem Verhalten, das es nicht mehr gibt; das ist derselbe Mangel mit
        umgekehrtem Vorzeichen.
        """
        e = eintrag("qs_admin")
        self.assertIsNotNone(e)
        schluessel = [k.schluessel for k in (e.konfiguration or ())]
        self.assertIn("paths.coordinator_db", schluessel,
                      "Der Eintrag steht noch auf 'liest keinen Eintrag aus "
                      "config.yaml'.")
        warntext = " ".join(e.tiefe.warnungen)
        self.assertNotIn("WIRD STILL './data/coordinator.db' ANGENOMMEN",
                         warntext,
                         "Die Warnung beschreibt den Stand vor Build 715.")
        self.assertIn("paths.coordinator_db", warntext)


if __name__ == "__main__":
    unittest.main()
