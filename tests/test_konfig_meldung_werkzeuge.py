# =============================================================================
# tests/test_konfig_meldung_werkzeuge.py
# IT-Forensisches Ermittlungswerkzeug — Meldung einer unlesbaren config.yaml
# =============================================================================
# Prueft Ticket cf791ef0: Ein Verwaltungswerkzeug, dessen config.yaml
# ausfaellt, MUSS das melden. Bis Build 712 taten es sechs von vierzehn
# Werkzeugen; acht lieferten wortlos None und arbeiteten mit ihren
# Vorgabewerten weiter. Das ist ein still uebersprungener Beleg
# (Grundregel 1) — und bei den Werkzeugen mit Schwellen veraendert es das
# ERGEBNIS und nicht nur seinen Vermerk: dieselbe Datenbank ergibt mit den
# Vorgabeschwellen eine andere Eskalationslage.
#
# WARUM KM04 UEBER DEN GESAMTEN BESTAND LAEUFT und nicht ueber eine Liste
# von acht Namen: Der Mangel ist durch ABSCHREIBEN entstanden. Eine Pruefung,
# die die acht bekannten Faelle aufzaehlt, belegt die Behebung, verhindert
# aber die neunte Abschrift nicht. Die Pruefung sucht deshalb selbst nach
# allen Werkzeugen mit '_load_config' und verlangt von JEDEM die Meldung.
# Ein neues Werkzeug faellt damit am Tag seiner Entstehung auf und nicht
# erst bei der naechsten Durchsicht.
#
# Kennungen:
#   KM01  konfig_laden: unlesbare Datei -> Meldung auf stderr, Rueckgabe None
#   KM02  konfig_laden: lesbare Datei -> ConfigLoader, KEINE Ausgabe
#   KM03  konfig_laden: der Halbsatz 'folge' steht woertlich in der Meldung
#   KM04  GEGENPROBE UEBER DEN BESTAND: jedes Werkzeug mit _load_config meldet
#   KM05  konfig_laden schreibt nach stderr, NIE nach stdout
#   KM06  kein Werkzeug haelt noch eine eigene Abschrift (Ticket 6c64daf4)
#   KM10  escalation_admin: Schwellenzeile im Textbetrieb, Herkunft 'Vorgabe'
#   KM11  escalation_admin: Herkunft 'config.yaml', wenn der Wert dort steht
#   KM12  escalation_admin --json: stdout ist reines JSON und traegt 'thresholds'
#   KM13  escalation_admin --json: derselbe Schluesselsatz wie der HTTP-Endpunkt
#
# Version: v0.8.724 · Build: 724 · 2026-08-14
# =============================================================================

import importlib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core import werkzeug_konfig                                  # noqa: E402
from core.config_loader import ConfigLoader                       # noqa: E402


class _Args:
    """
    Attrappe eines argparse-Ergebnisses (wie in tests/test_cli_vorrang.py).
    Bewusst so einfach: die Werkzeuge lesen 'config' ueber getattr, und genau
    dieses Verhalten wird hier geprueft — nicht argparse.
    """

    def __init__(self, config=None):
        self.config = config
        self.coordinator_db = None


def _config_schreiben(pfad: Path, inhalt: str = "") -> Path:
    """
    Schreibt eine config.yaml, die den Pflichtteil der Validierung erfuellt.
    ConfigLoader._validate() verlangt gueltige server./logging.-Werte; ohne
    sie kaeme man gar nicht bis zu dem Eintrag, um den es geht. Gleiche
    Begruendung und gleicher Aufbau wie in tests/test_cli_vorrang.py.
    """
    pfad.write_text(
        "server:\n  host: \"127.0.0.2\"\n  port: 8080\n  mode: \"cli\"\n"
        "logging:\n  level: \"info\"\n" + inhalt, encoding="utf-8")
    return pfad


def _ruf_ab(fn, *args, **kwargs):
    """Ruft fn auf und liefert (Rueckgabe, stdout, stderr) als Text."""
    aus, err = io.StringIO(), io.StringIO()
    with redirect_stdout(aus), redirect_stderr(err):
        ergebnis = fn(*args, **kwargs)
    return ergebnis, aus.getvalue(), err.getvalue()


# =============================================================================
# KM01-KM05 — die gemeinsame Fassung in core/werkzeug_konfig.py
# =============================================================================

class KonfigLadenTests(unittest.TestCase):

    def test_km01_unlesbare_datei_meldet_und_liefert_none(self):
        """KM01: Fehlende Datei -> eine Zeile auf stderr, Rueckgabe None."""
        args = _Args(config="/gibt/es/nicht/config.yaml")
        cfg, aus, err = _ruf_ab(werkzeug_konfig.konfig_laden,
                                "pruef_admin", args)
        self.assertIsNone(cfg)
        erste = err.splitlines()[0]
        self.assertTrue(erste.startswith("[pruef_admin] config.yaml nicht "
                                        "lesbar"), erste)
        # DER GRUND MUSS MIT — eine Meldung ohne ihn zwingt zum Raten. Er
        # stammt woertlich aus der Ausnahme des ConfigLoader und ist bei
        # einer fehlenden Datei ZWEIZEILIG (Fundstelle + Abhilfe); die
        # Pruefung schreibt deshalb keine Zeilenzahl vor, sondern verlangt
        # den Pfad, an dem gesucht wurde.
        self.assertIn("/gibt/es/nicht/config.yaml", err)

    def test_km02_lesbare_datei_schweigt(self):
        """KM02: Ist die Datei lesbar, gibt es keinerlei Ausgabe."""
        with tempfile.TemporaryDirectory() as tmp:
            pfad = _config_schreiben(Path(tmp) / "config.yaml")
            cfg, aus, err = _ruf_ab(werkzeug_konfig.konfig_laden,
                                    "pruef_admin", _Args(config=str(pfad)))
        self.assertIsInstance(cfg, ConfigLoader)
        self.assertEqual("", aus)
        self.assertEqual("", err)

    def test_km03_folge_steht_woertlich_in_der_meldung(self):
        """
        KM03: Der Halbsatz beantwortet die Frage 'und was gilt jetzt?'.
        Alle drei im Bestand vorkommenden Auspraegungen werden geprueft,
        einschliesslich des Vorgabewerts.
        """
        args = _Args(config="/gibt/es/nicht/config.yaml")
        for folge in ("Vorgabe-Schwellen werden verwendet",
                      "Vorgaben werden verwendet",
                      "es gelten nur die Angaben von der Befehlszeile"):
            with self.subTest(folge=folge):
                _, _, err = _ruf_ab(werkzeug_konfig.konfig_laden,
                                    "pruef_admin", args, folge=folge)
                self.assertIn("(%s)" % folge, err)
        # Ohne Angabe gilt der dokumentierte Vorgabewert.
        _, _, err = _ruf_ab(werkzeug_konfig.konfig_laden, "pruef_admin", args)
        self.assertIn("(%s)" % werkzeug_konfig.FOLGE_VORGABEN, err)

    #: Der Aufbau, den jede Meldung haben muss (Build 724, Ticket 6c64daf4):
    #:     [<werkzeug>] config.yaml nicht lesbar (<folge>): <grund>
    #: Der Halbsatz in Klammern ist der Teil, um den es geht — er beantwortet
    #: die Frage "und was gilt jetzt?". Drei Werkzeuge hatten ihn nicht.
    _MELDUNGSFORM = re.compile(
        r"^\[(?P<werkzeug>[a-z_]+)\] config\.yaml nicht lesbar "
        r"\((?P<folge>[^)]+)\): (?P<grund>.+)$")

    #: Die Folgen, die es geben DARF. Kommt eine vierte hinzu, ist das kein
    #: Fehler — sie gehoert dann aber in den Kopf von konfig_laden(), sonst
    #: waechst wieder ein Wildwuchs. Der Test ist deshalb ein Stolperdraht
    #: und keine Sperre gegen neue Faelle.
    _ERLAUBTE_FOLGEN = {
        "Vorgabe-Schwellen werden verwendet",
        "Vorgaben werden verwendet",
        "es gelten nur die Angaben von der Befehlszeile",
    }

    def test_km04_jedes_werkzeug_mit_load_config_meldet(self):
        """
        KM04: Die Gegenprobe ueber den GESAMTEN Bestand (siehe Kopf).

        Gesucht werden alle Module unter management/ mit einer Funktion
        '_load_config'; jedes wird mit einem nicht vorhandenen Konfigpfad
        aufgerufen. Verlangt wird: Rueckgabe None UND eine Meldung auf
        stderr, die die Datei benennt.

        BUILD 724 (Ticket 6c64daf4) — JETZT AUCH DER AUFBAU. In Build 718
        liess dieser Test den Wortlaut bewusst offen: acht Werkzeuge hatten
        gar keine Meldung, sechs je eine eigene, und ein erzwungener
        Einheitssatz waere damals ungenauer gewesen als das Schweigen darueber.
        Seit alle vierzehn dieselbe Fassung aufrufen, ist die Form pruefbar —
        und erst damit faellt auch die naechste Abschrift auf, die zwar meldet,
        aber ohne Folgesatz (das war der Befund bei status_report,
        forecast_report und support_overview_admin).
        """
        module = self._werkzeuge_mit_load_config()
        self.assertGreaterEqual(
            len(module), 14,
            "Die Modulsuche findet zu wenig — sie greift ins Leere.")
        stumme, formfehler, unbekannte_folgen = [], [], []
        for modulname in module:
            mod = importlib.import_module(modulname)
            cfg, aus, err = _ruf_ab(mod._load_config,
                                    _Args(config="/gibt/es/nicht/config.yaml"))
            if cfg is not None or "config.yaml" not in err:
                stumme.append("%s (stdout=%r, stderr=%r)"
                              % (modulname, aus, err))
                continue
            # Auch hier gilt: stdout bleibt unberuehrt (--json-Zusage).
            self.assertEqual("", aus, "%s schreibt nach stdout" % modulname)
            erste = err.splitlines()[0]
            treffer = self._MELDUNGSFORM.match(erste)
            if treffer is None:
                formfehler.append("%s: %r" % (modulname, erste))
                continue
            if treffer.group("folge") not in self._ERLAUBTE_FOLGEN:
                unbekannte_folgen.append(
                    "%s: %r" % (modulname, treffer.group("folge")))
            # Der GRUND muss mitkommen — eine Meldung ohne ihn zwingt zum Raten.
            self.assertIn("/gibt/es/nicht/config.yaml", err, modulname)
        self.assertEqual(
            [], stumme,
            "Diese Werkzeuge uebergehen eine unlesbare config.yaml wortlos "
            "(Ticket cf791ef0): " + "; ".join(stumme))
        self.assertEqual(
            [], formfehler,
            "Diese Meldungen haben nicht den gemeinsamen Aufbau "
            "'[werkzeug] config.yaml nicht lesbar (folge): grund' — sie "
            "stammen vermutlich aus einer eigenen Abschrift statt aus "
            "werkzeug_konfig.konfig_laden() (Ticket 6c64daf4): "
            + "; ".join(formfehler))
        self.assertEqual(
            [], unbekannte_folgen,
            "Diese Werkzeuge nennen eine Folge, die im Kopf von "
            "konfig_laden() nicht beschrieben ist. Ist sie richtig, gehoert "
            "sie dort hinein UND in _ERLAUBTE_FOLGEN: "
            + "; ".join(unbekannte_folgen))

    def test_km06_kein_werkzeug_haelt_noch_eine_eigene_abschrift(self):
        """
        KM06 (Build 724, Ticket 6c64daf4): Kein Verwaltungswerkzeug baut
        seinen ConfigLoader mehr selbst.

        WARUM DAS EIN EIGENER TEST IST, obwohl KM04 die Wirkung prueft: KM04
        misst die AUSGABE. Eine Abschrift, die zufaellig denselben Satz
        ausgibt, kaeme dort durch — und waere doch wieder die Stelle, an der
        beim naechsten Mal etwas auseinanderlaeuft. Dieser Test sieht
        stattdessen in den Quelltext und verbietet das Muster selbst.

        AUSGENOMMEN sind bewusst die Werkzeuge, die ihre Konfiguration NICHT
        ueber '_load_config' laden (case_detect, seal_check, lkae_admin): Sie
        haben eigene Vorrangreihen und sind in Ticket 6c64daf4 ausdruecklich
        nicht enthalten. Sie stehen hier namentlich, damit die Ausnahme eine
        Entscheidung bleibt und nicht zur Luecke wird.
        """
        ausgenommen = {"management.cases.case_detect",
                       "management.reports.seal_check",
                       "management.distribution.lkae_admin"}
        eigenbau = []
        for pfad in sorted((_REPO_ROOT / "management").rglob("*.py")):
            modulname = ".".join(pfad.relative_to(_REPO_ROOT)
                                 .with_suffix("").parts)
            if modulname in ausgenommen:
                continue
            text = pfad.read_text(encoding="utf-8")
            if not re.search(r"^def _load_config\(", text, re.M):
                continue
            rumpf = text.split("def _load_config(", 1)[1].split("\ndef ", 1)[0]
            if "ConfigLoader(" in rumpf:
                eigenbau.append(modulname)
        self.assertEqual(
            [], eigenbau,
            "Diese Werkzeuge bauen ihren ConfigLoader in _load_config wieder "
            "selbst, statt werkzeug_konfig.konfig_laden() zu rufen "
            "(Ticket 6c64daf4): " + ", ".join(eigenbau))

    def test_km05_meldung_geht_nach_stderr_nicht_nach_stdout(self):
        """
        KM05: Werkzeuge mit '--json' liefern auf stdout ausschliesslich JSON.
        Eine Hinweiszeile dort waere kein Hinweis, sondern ein Fehler.
        """
        _, aus, err = _ruf_ab(werkzeug_konfig.konfig_laden, "pruef_admin",
                              _Args(config="/gibt/es/nicht/config.yaml"))
        self.assertEqual("", aus)
        self.assertNotEqual("", err)

    # ------------------------------------------------------------- Helfer

    @staticmethod
    def _werkzeuge_mit_load_config():
        """
        Sucht im Quelltext nach 'def _load_config(' und liefert die
        Modulnamen. Der Quelltext wird GELESEN und nicht importiert, um
        Module ohne die Funktion gar nicht erst zu laden.
        """
        treffer = []
        wurzel = _REPO_ROOT / "management"
        for pfad in sorted(wurzel.rglob("*.py")):
            try:
                text = pfad.read_text(encoding="utf-8")
            except OSError:                              # pragma: no cover
                continue
            if re.search(r"^def _load_config\(", text, re.M):
                rel = pfad.relative_to(_REPO_ROOT).with_suffix("")
                treffer.append(".".join(rel.parts))
        return treffer


# =============================================================================
# KM10-KM13 — escalation_admin weist seinen Massstab aus
# =============================================================================

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
_OLD_SCRAPE_JOBS = """
CREATE TABLE scrape_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""


class EscalationAdminMassstabTests(unittest.TestCase):
    """
    Der leere Bestand genuegt hier: Geprueft wird der AUSWEIS des
    Massstabs, nicht die Auswertung selbst — die hat ihre eigene Suite
    (tests/test_management_escalation.py, ES01-ES08).
    """

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self.db_path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        try:
            con.execute(_PERSON)
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (1, 'h001', 'Chefin, Alpha', 1, 1, 0, ?)",
                (int(time.time()),))
            con.execute(_OLD_SCRAPE_JOBS)
            # Aufbau wie in tests/test_management_escalation_api.py: der
            # Migrationslauf legt die Tabellen an, die DashboardRepo liest.
            import management.migrations.coordinator as coordinator_migrations
            from management.audit.audit_log import AuditLog
            from management.migrations.runner import MigrationRunner, discover
            MigrationRunner(con, discover(coordinator_migrations),
                            audit=AuditLog(con), deployed_by="tester").run()
        finally:
            con.close()

    def tearDown(self):
        for name in os.listdir(self._tmp):
            try:
                os.remove(os.path.join(self._tmp, name))
            except OSError:                              # pragma: no cover
                pass
        os.rmdir(self._tmp)

    def _lauf(self, *zusatz, config=None):
        from management.cases import escalation_admin
        argv = ["--coordinator-db", self.db_path,
                "--config", config or "/gibt/es/nicht/config.yaml"]
        return _ruf_ab(escalation_admin.main, list(argv) + list(zusatz))

    def test_km10_schwellenzeile_mit_herkunft_vorgabe(self):
        """
        KM10: Die erste Zeile nennt alle drei Schwellen und ihre Herkunft.
        Ohne lesbare config.yaml ist das ueberall 'Vorgabe' — und genau das
        muss dastehen, damit zwei Laeufe vergleichbar sind.
        """
        rc, aus, err = self._lauf()
        self.assertEqual(0, rc)
        erste = aus.splitlines()[0]
        self.assertTrue(erste.startswith("Schwellen: "), erste)
        for feld, wert in (("red_overdue_days", 30), ("stale_open_days", 14),
                           ("backlog_high", 10)):
            self.assertIn("%s=%d [Vorgabe]" % (feld, wert), erste)
        # Der Ausfall der Konfiguration ist zusaetzlich gemeldet (cf791ef0).
        self.assertIn("config.yaml nicht lesbar", err)
        self.assertIn("Vorgabe-Schwellen werden verwendet", err)
        # Die bisherige Ausgabe bleibt vollstaendig erhalten.
        self.assertIn("Eskalationen: hoch=0 mittel=0 niedrig=0", aus)
        self.assertIn("(keine Eskalation)", aus)

    def test_km11_herkunft_config_yaml_wenn_der_wert_dort_steht(self):
        """
        KM11: Steht die Schwelle in der Datei, wird sie als 'config.yaml'
        ausgewiesen UND wirkt. Die Gegenprobe im selben Lauf: die beiden
        NICHT eingetragenen Schwellen bleiben 'Vorgabe'. Eine Herkunft, die
        pauschal 'config.yaml' meldet, faellt damit auf.
        """
        pfad = _config_schreiben(Path(self._tmp) / "config.yaml",
                                 "escalation:\n  red_overdue_days: 45\n")
        rc, aus, err = self._lauf(config=str(pfad))
        self.assertEqual(0, rc)
        erste = aus.splitlines()[0]
        self.assertIn("red_overdue_days=45 [config.yaml]", erste)
        self.assertIn("stale_open_days=14 [Vorgabe]", erste)
        self.assertIn("backlog_high=10 [Vorgabe]", erste)
        self.assertEqual("", err, "lesbare Datei -> keine Stoermeldung")

    def test_km12_json_traegt_die_schwellen_und_bleibt_reines_json(self):
        """KM12: stdout ist mit --json vollstaendig parsebar."""
        rc, aus, err = self._lauf("--json")
        self.assertEqual(0, rc)
        payload = json.loads(aus)          # wirft, sobald etwas danebensteht
        self.assertEqual({"red_overdue_days": 30, "stale_open_days": 14,
                          "backlog_high": 10}, payload["thresholds"])
        self.assertNotIn("Schwellen:", aus)
        # Die bisherigen Schluessel sind unveraendert vorhanden.
        for schluessel in ("generated_at", "total_cases", "count_hoch",
                           "count_mittel", "count_niedrig", "items"):
            self.assertIn(schluessel, payload)

    def test_km13_gleicher_schluesselsatz_wie_der_http_endpunkt(self):
        """
        KM13: Der HTTP-Endpunkt haengt seit Build 515 dieselben drei
        Schluessel an. Dieselbe Auskunft darf an zwei Stellen nicht anders
        heissen; die Pruefung liest den Schluesselsatz aus der CLI-Fassung
        und vergleicht ihn mit dem Quelltext des Endpunkts.
        """
        from management.cases.escalation_admin import _SCHWELLEN_FELDER
        quelle = (_REPO_ROOT / "management" / "server"
                  / "management_app.py").read_text(encoding="utf-8")
        block = quelle.split('payload["thresholds"] = {', 1)
        self.assertEqual(2, len(block), "Der Endpunkt hat sich verschoben.")
        endpunkt = block[1].split("}", 1)[0]
        for feld in _SCHWELLEN_FELDER:
            self.assertIn('"%s"' % feld, endpunkt)
        self.assertEqual(len(_SCHWELLEN_FELDER), endpunkt.count('": thresholds.'))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
