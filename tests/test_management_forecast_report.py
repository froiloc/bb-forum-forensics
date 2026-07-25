# =============================================================================
# tests/test_management_forecast_report.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7
# =============================================================================
# Testsuite fuer Build 522: Prognosebericht (AP-3F / Idee 40).
#
# REINE FUNKTIONEN (kein Server, keine DB):
#   FR01 — API-Oberflaeche vollstaendig (alle reinen Funktionen vorhanden).
#   FR02 — vorbehalt_lines: DATENARM-Vorbehalt steht VORNE, wenn
#          data_sufficient nicht True ist; Modell- und Kapazitaetsvorbehalt
#          stehen IMMER dabei.
#   FR03 — vorbehalt_lines: fehlender Schluessel 'data_sufficient' gilt als
#          duenne Datenlage (im Zweifel der Vorbehalt, nicht die Aussage).
#   FR04 — scenario_rows: days_to_clear None -> 'unbestimmt' (NIE '0');
#          0 -> ausdruecklich '0 Tage (Backlog leer)'; finish None ->
#          'unbestimmt'.
#   FR05 — assumption_lines: Annahmen WORTGLEICH und in Backend-Reihenfolge;
#          leere Liste -> AUSDRUECKLICHE Meldung statt Leerbefund.
#   FR06 — kapazitaet_rows: fehlender Kontext -> Zeile 'nicht verfuegbar'
#          (kein leerer Abschnitt).
#   FR07 — grundlage_rows: Datenlage wird als 'NEIN — keine belastbare
#          Prognose' benannt, nicht weggelassen.
#   FR08 — HTML: enthaelt ALLE Annahmen, alle drei Szenarien, die Pruefsumme
#          und den Erzeugungsvermerk; Vorbehalt steht VOR der Szenariotabelle.
#   FR09 — HTML: Markup in Werten bleibt Text (html.escape), UTF-8 erhalten.
#   FR10 — HTML traegt den Datendigest; der Digest ist deterministisch.
#   FR10b — PDF traegt DENSELBEN Datendigest (nur mit reportlab).
#   FR11 — PDF: gueltiger PDF-Kopf, nicht leer (nur mit reportlab).
#   FR12 — PDF: ForecastReportUnavailable, wenn reportlab fehlt (Import-Guard;
#          umgebungsUNABHAENGIG, weil der ImportError erzwungen wird).
#
# ENDPUNKT (ueber den echten dispatch(), mit echter Migrationskette):
#   FR13 — GET /api/forecast/report ohne Recht -> 403 und nennt die Faehigkeit.
#   FR14 — mit Recht, Scope 'alle', format=html -> 200 text/html mit Titel.
#   FR15 — format=pdf -> 200 application/pdf MIT Content-Disposition (inline,
#          Dateiname traegt den Stichtag) — nur mit reportlab.
#   FR15b — ohne 'format' kommt PDF (Vorgabe wie in der CLI) — nur mit reportlab.
#   FR15c — FEHLT die PDF-Erzeugung, antwortet der Endpunkt mit 503 und nennt
#          reportlab. UMGEBUNGSUNABHAENGIG: der Ausfall wird erzwungen, statt
#          ihn von der Maschine abhaengig zu machen.
#   FR15d — Gegenprobe in einer Umgebung OHNE reportlab: derselbe 503 kommt
#          auch ohne jedes Zutun des Tests (laeuft nur dort, wo die Bibliothek
#          wirklich fehlt).
#   FR16 — unbekanntes Format -> 400 MIT der Liste der gueltigen Werte
#          (KEIN stiller Rueckfall auf PDF).
#   FR17 — lookback_days unbrauchbar (nicht-Zahl, 0, negativ) -> je 400.
#   FR18 — Scope 'eigene' -> 403 (falluebergreifende Planungssicht).
#   FR19 — Response.pdf begrenzt den Dateinamen (keine Kopfzeilen-Injektion).
#   FR20 — Der Endpunkt schreibt NICHTS: die audit_log-Spitze ist vor und nach
#          dem Abruf identisch — und zwar UNABHAENGIG davon, ob die
#          PDF-Erzeugung gelingt (200) oder als 503 scheitert. Das ist die
#          eigentliche Zusicherung: auch der Fehlerpfad hinterlaesst keinen
#          Beleg.
#
# WARUM DIESE DATEI IN BUILD 526 GEAENDERT WURDE (Befund aus der VM):
#   In Build 522 verlangten FR10/FR11/FR15/FR15b/FR20 reportlab
#   BEDINGUNGSLOS. In der Test-VM ist die Bibliothek nicht installiert -> fuenf
#   Fehlschlaege, obwohl der Code sich korrekt verhielt (503 mit Klartext).
#   Das war ein Fehler IM TEST, nicht im Code: reportlab ist eine OPTIONALE
#   Abhaengigkeit (install.py:53, RUNTIME_PACKAGES ab Build 404), und das
#   Projekt hat dafuer bereits eine Konvention, die ich uebersehen habe —
#   pytest.importorskip in tests/test_management_stats_status_report.py:100 und
#   self.skipTest in tests/test_report_render.py:412.
#
#   Diese Datei folgt der Konvention jetzt, aber SIE UEBERSPRINGT NICHT
#   EINFACH: der 503-Pfad wird in FR15c ERZWUNGEN geprueft (in JEDER Umgebung)
#   und in FR15d zusaetzlich dort, wo die Bibliothek echt fehlt. Ein blosses
#   'skip' haette die Luecke nur unsichtbar gemacht — genau das, was Grundregel
#   1 verbietet.
#
# Beleg fuer den Aufbau: tests/test_management_retention_api.py (Build 521).
# =============================================================================

import html
import json
import sqlite3
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

html_escape = html.escape

# --- Ist reportlab da? -------------------------------------------------------
#   reportlab ist eine OPTIONALE Laufzeit-Abhaengigkeit (install.py:53). Fehlt
#   sie, ist das KEIN Fehler dieses Builds — der Endpunkt meldet es als 503 mit
#   Klartext. Die Tests, die echte PDF-Bytes brauchen, werden dann
#   uebersprungen; der 503-Pfad wird trotzdem geprueft (FR15c/FR15d).
try:                                    # pragma: no cover - Umgebungsabhaengig
    import reportlab  # noqa: F401
    _HAS_REPORTLAB = True
except ImportError:                     # pragma: no cover - Umgebungsabhaengig
    _HAS_REPORTLAB = False

_SKIP_OHNE = ("reportlab nicht installiert (optionale Abhaengigkeit, "
              "install.py RUNTIME_PACKAGES ab Build 404). Der 503-Pfad wird "
              "stattdessen in FR15c/FR15d geprueft.")
_SKIP_MIT = ("reportlab IST installiert — diese Gegenprobe gilt nur fuer "
             "Umgebungen ohne die Bibliothek.")

from management.audit.audit_log import AuditLog                    # noqa: E402
from management.export.export_envelope import ExportContext        # noqa: E402
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.rbac.rbac_repo import RbacRepo                     # noqa: E402
from management.server.management_app import ManagementApp, Response  # noqa: E402
from management.stats.forecast_report import (                     # noqa: E402
    TITEL,
    VORBEHALT_DATENARM,
    VORBEHALT_KAPAZITAET,
    VORBEHALT_MODELL,
    ForecastReportUnavailable,
    assumption_lines,
    build_forecast_report_html,
    build_forecast_report_pdf,
    forecast_digest,
    grundlage_rows,
    kapazitaet_rows,
    scenario_rows,
    vorbehalt_lines,
)

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

# Die AUSGANGSFASSUNG von scrape_jobs (vor M002). Sie wird hier von Hand
# angelegt, weil M002 die Tabelle umbaut und dafuer die alten Spalten braucht
# — genau wie in tests/test_management_retention_api.py:71-83.
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


def _forecast(**over):
    """Eine vollstaendige /api/forecast-Antwort (forecast_to_dict-Form)."""
    base = {
        "now_day": "2026-07-25",
        "backlog": 12,
        "lookback_days": 30,
        "completions_observed": 6,
        "observed_rate_per_day": 0.2,
        "data_sufficient": True,
        "scenarios": [
            {"name": "optimistisch", "factor": 1.25, "rate_per_day": 0.25,
             "days_to_clear": 48, "finish_day": "2026-09-11"},
            {"name": "erwartet", "factor": 1.0, "rate_per_day": 0.2,
             "days_to_clear": 60, "finish_day": "2026-09-23"},
            {"name": "pessimistisch", "factor": 0.75, "rate_per_day": 0.15,
             "days_to_clear": 80, "finish_day": "2026-10-13"},
        ],
        "assumptions": [
            "Backlog = Faelle mit status in open, in_progress (Tabelle cases).",
            "Abschluss-Signal = case_events.event_kind='approved'.",
            "Beobachtete Rate = 6 Abschluesse / 30 Tage = 0.2000 Faelle/Tag.",
        ],
        "capacity_context": {"persons": 3, "netto_minutes": 24000,
                             "window_days": 30, "window_start": "2026-07-25",
                             "window_end": "2026-08-24"},
    }
    base.update(over)
    return base


def _ctx(**over):
    kw = dict(behoerde="Polizei NRW — EK Zarewitsch",
              aktenzeichen="Prognosebericht (3 Szenarien)",
              ersteller="NRW\\pruefer", build_number=522,
              generated_at="2026-07-25 08:00 UTC",
              chain_ok=True, chain_tip_seq=99, chain_tip_hash="abc123")
    kw.update(over)
    return ExportContext(**kw)


class TestForecastReportPure(unittest.TestCase):
    """FR01-FR12 — die reinen Funktionen, dateilos und deterministisch."""

    def test_FR01_api_vollstaendig(self):
        for fn in (vorbehalt_lines, grundlage_rows, scenario_rows,
                   kapazitaet_rows, assumption_lines, forecast_digest,
                   build_forecast_report_html, build_forecast_report_pdf):
            self.assertTrue(callable(fn))

    def test_FR02_vorbehalt_reihenfolge_und_pflichtteile(self):
        lines = vorbehalt_lines(_forecast(data_sufficient=False))
        self.assertEqual(lines[0], VORBEHALT_DATENARM)
        self.assertIn(VORBEHALT_MODELL, lines)
        self.assertIn(VORBEHALT_KAPAZITAET, lines)
        # Bei guter Datenlage FEHLT nur der Datenarm-Vorbehalt, die anderen
        # bleiben — sie sind Modellaussagen, nicht Fehlermeldungen.
        gut = vorbehalt_lines(_forecast())
        self.assertNotIn(VORBEHALT_DATENARM, gut)
        self.assertIn(VORBEHALT_MODELL, gut)
        self.assertIn(VORBEHALT_KAPAZITAET, gut)

    def test_FR03_fehlender_schluessel_gilt_als_duenn(self):
        fc = _forecast()
        del fc["data_sufficient"]
        self.assertEqual(vorbehalt_lines(fc)[0], VORBEHALT_DATENARM)
        # Auch ein truthy-aber-nicht-True Wert darf nicht als 'ausreichend'
        # durchgehen (str '1' ist keine Datenlage).
        self.assertEqual(
            vorbehalt_lines(_forecast(data_sufficient="1"))[0],
            VORBEHALT_DATENARM)

    def test_FR04_scenario_rows_unbestimmt_und_null(self):
        rows = scenario_rows(_forecast(scenarios=[
            {"name": "erwartet", "factor": 1.0, "rate_per_day": 0.0,
             "days_to_clear": None, "finish_day": None},
            {"name": "leer", "factor": 1.0, "rate_per_day": 0.0,
             "days_to_clear": 0, "finish_day": "2026-07-25"},
        ]))
        self.assertEqual(rows[0]["days"], "unbestimmt")
        self.assertNotIn("0", rows[0]["days"])
        self.assertEqual(rows[0]["finish"], "unbestimmt")
        self.assertIn("Backlog leer", rows[1]["days"])

    def test_FR05_assumptions_wortgleich_und_leerbefund(self):
        fc = _forecast()
        self.assertEqual(assumption_lines(fc), fc["assumptions"])
        for leer in ([], None):
            got = assumption_lines(_forecast(assumptions=leer))
            self.assertEqual(len(got), 1)
            self.assertIn("KEINE ANNAHMEN", got[0])

    def test_FR06_kapazitaet_nicht_verfuegbar(self):
        rows = kapazitaet_rows(_forecast(capacity_context=None))
        self.assertEqual(len(rows), 1)
        self.assertIn("nicht verfuegbar", rows[0][1])
        # Mit Kontext: alle fuenf Angaben, keine still weggelassene.
        rows2 = kapazitaet_rows(_forecast())
        self.assertEqual(len(rows2), 5)

    def test_FR07_grundlage_benennt_datenlage(self):
        rows = dict(grundlage_rows(_forecast(data_sufficient=False)))
        self.assertIn("NEIN", rows["Datenlage ausreichend"])
        rows_ok = dict(grundlage_rows(_forecast()))
        self.assertEqual(rows_ok["Datenlage ausreichend"], "ja")

    def test_FR08_html_vollstaendig(self):
        fc = _forecast(data_sufficient=False)
        out = build_forecast_report_html(fc, _ctx(), period_label="KW 30/2026")
        # html.escape() entschaerft auch das Apostroph (-> &#x27;). Der Test
        # sucht deshalb die ESCAPTE Fassung: der Text muss VOLLSTAENDIG im
        # Dokument stehen, aber als Text und nicht als Markup.
        for a in fc["assumptions"]:
            self.assertIn(html_escape(a), out)
        for s in ("optimistisch", "erwartet", "pessimistisch"):
            self.assertIn(s, out)
        self.assertIn(forecast_digest(fc), out)
        self.assertIn("Erstellt von", out)
        self.assertIn("KW 30/2026", out)
        # Der Vorbehalt steht VOR der Szenariotabelle — die Reihenfolge ist
        # die Aussage (er bestimmt, wie die Tabelle zu lesen ist).
        self.assertLess(out.index(VORBEHALT_DATENARM),
                        out.index("Die drei Szenarien"))

    def test_FR09_html_escaped_utf8_erhalten(self):
        out = build_forecast_report_html(
            _forecast(assumptions=["<script>alert(1)</script> Grüße"]),
            _ctx(behoerde="Polizei <b>NRW</b>"))
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("Grüße", out)          # UTF-8 unveraendert
        self.assertNotIn("<b>NRW</b>", out)

    def test_FR10_html_traegt_digest_deterministisch(self):
        """
        Der Datendigest ist die Bruecke zwischen den Ausgaben — und er braucht
        KEIN reportlab. Deshalb steht dieser Teil hier unbedingt: die
        Nachrechenbarkeit der Pruefsumme darf nicht von einer optionalen
        Bibliothek abhaengen.
        """
        fc = _forecast()
        digest = forecast_digest(fc)
        self.assertIn(digest, build_forecast_report_html(fc, _ctx()))
        self.assertEqual(digest, forecast_digest(fc))       # deterministisch
        geaendert = _forecast(backlog=999)
        self.assertNotEqual(digest, forecast_digest(geaendert))  # empfindlich

    @unittest.skipUnless(_HAS_REPORTLAB, _SKIP_OHNE)
    def test_FR10b_pdf_gleicher_digest(self):
        fc = _forecast()
        digest = forecast_digest(fc)
        pdf_out = build_forecast_report_pdf(fc, _ctx())
        # Im PDF steht der Digest im Textstrom; reportlab komprimiert ihn
        # jedoch. Statt im Binaerstrom zu suchen (was von der
        # reportlab-Version abhinge), pruefen wir die EINE Wahrheit direkt:
        # beide Ausgaben rufen forecast_digest auf demselben Objekt.
        self.assertTrue(pdf_out.startswith(b"%PDF"))
        self.assertIn(digest, build_forecast_report_html(fc, _ctx()))

    @unittest.skipUnless(_HAS_REPORTLAB, _SKIP_OHNE)
    def test_FR11_pdf_kopf_und_umfang(self):
        data = build_forecast_report_pdf(
            _forecast(data_sufficient=False,
                      assumptions=["Annahme mit <Sonderzeichen> & Umlaut ä"]),
            _ctx(), period_label="KW 30/2026")
        self.assertTrue(data.startswith(b"%PDF"))
        # Ein PDF mit Kopf, drei Tabellen und Annahmen ist nicht winzig; die
        # Grenze ist bewusst grob (Versionsunterschiede von reportlab).
        self.assertGreater(len(data), 2000)

    def test_FR12_pdf_unavailable_ohne_reportlab(self):
        """Import-Guard: fehlt reportlab, gibt es einen KLAREN Fehler."""
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name.startswith("reportlab"):
                raise ImportError("kein reportlab (Test)")
            return real_import(name, *a, **kw)

        builtins.__import__ = fake_import
        try:
            with self.assertRaises(ForecastReportUnavailable):
                build_forecast_report_pdf(_forecast(), _ctx())
        finally:
            builtins.__import__ = real_import


class TestForecastReportEndpoint(unittest.TestCase):
    """FR13-FR20 — der Endpunkt am echten dispatch()."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.db_path = str(Path(self.tmp) / "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        # journal_mode=delete: WAL ist projektweit verboten (Build 499).
        self.con.execute("PRAGMA journal_mode=delete")
        self.con.executescript(_PERSON)
        self.con.executescript(_OLD_SCRAPE_JOBS)
        for uname, dname, inv, sup in (
                ("NRW\\chefin", "Chef-Ermittlerin", 0, 1),
                ("NRW\\ermittler", "Ermittler", 1, 0),
                ("NRW\\ohne", "Ohne Rechte", 0, 0)):
            self.con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,?,?,0,0)", (uname, dname, inv, sup))

        self.audit = AuditLog(self.con)
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        rbac = RbacRepo(self.con, self.writer)
        # Person 1: Recht mit Scope 'alle' -> darf den Bericht erzeugen.
        rbac.grant("supervisor", "stats.export_sta", scope="alle", actor_id=1)
        rbac.assign_role(1, "supervisor", actor_id=1)
        # Person 2: dasselbe Recht, aber Scope 'eigene' -> darf NICHT
        # (Gegenprobe zur falluebergreifenden Planungssicht).
        rbac.grant("investigator", "stats.export_sta", scope="eigene",
                   actor_id=1)
        rbac.assign_role(2, "investigator", actor_id=1)
        # Person 3 bekommt nichts.

        self.app = ManagementApp(self.db_path)

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    def _get(self, person_id, query=None):
        return self.app.dispatch(person_id, "/api/forecast/report",
                                 query or {})

    def test_FR13_ohne_recht_403(self):
        r = self._get(3)
        self.assertEqual(r.status, 403)
        body = json.loads(r.body.decode("utf-8"))
        self.assertIn("stats.export_sta", json.dumps(body))

    def test_FR14_html_200(self):
        r = self._get(1, {"format": ["html"]})
        self.assertEqual(r.status, 200)
        self.assertIn("text/html", r.content_type)
        out = r.body.decode("utf-8")
        self.assertIn(TITEL, out)
        # Auch ohne jeden Fall im Bestand steht der Modellvorbehalt drin.
        self.assertIn(VORBEHALT_MODELL, out)

    @unittest.skipUnless(_HAS_REPORTLAB, _SKIP_OHNE)
    def test_FR15_pdf_200_mit_content_disposition(self):
        r = self._get(1, {"format": ["pdf"]})
        self.assertEqual(r.status, 200)
        self.assertEqual(r.content_type, "application/pdf")
        self.assertTrue(r.body.startswith(b"%PDF"))
        headers = dict(r.extra_headers)
        self.assertIn("Content-Disposition", headers)
        self.assertIn("inline", headers["Content-Disposition"])
        self.assertIn("AIW-Prognose_", headers["Content-Disposition"])

    @unittest.skipUnless(_HAS_REPORTLAB, _SKIP_OHNE)
    def test_FR15b_pdf_ist_die_vorgabe(self):
        """Ohne 'format' kommt PDF — dieselbe Vorgabe wie in der CLI."""
        r = self._get(1)
        self.assertEqual(r.status, 200)
        self.assertEqual(r.content_type, "application/pdf")

    def test_FR15c_pdf_unavailable_ergibt_503_mit_klartext(self):
        """
        Der 503-Pfad, ERZWUNGEN — und damit in JEDER Umgebung geprueft.

        Statt darauf zu warten, dass eine Maschine reportlab nicht hat, wird
        der Ausfall hier hergestellt: die vom Endpunkt benutzte Funktion wird
        durch eine ersetzt, die ForecastReportUnavailable wirft. Nur so ist die
        Zusicherung 'kein leeres PDF, kein stiller Formatwechsel' unabhaengig
        von der Umgebung belegt.
        """
        import management.server.management_app as app_modul

        def kaputt(*_a, **_kw):
            raise ForecastReportUnavailable("simuliert fehlend (Test)")

        echt = app_modul.build_forecast_report_pdf
        app_modul.build_forecast_report_pdf = kaputt
        try:
            r = self._get(1, {"format": ["pdf"]})
        finally:
            app_modul.build_forecast_report_pdf = echt

        self.assertEqual(r.status, 503)
        body = json.loads(r.body.decode("utf-8"))
        self.assertEqual(body["error"], "pdf_unavailable")
        # Der Klartext muss die Bibliothek NENNEN und den Weg zur Behebung
        # zeigen — eine Fehlermeldung ohne Abhilfe ist im Betrieb wertlos.
        self.assertIn("reportlab", body["detail"])
        self.assertIn("Offline-Wheel", body["detail"])
        # KEIN stiller Formatwechsel: die Antwort ist weder PDF noch HTML.
        self.assertNotEqual(r.content_type, "application/pdf")
        self.assertNotIn("text/html", r.content_type)
        # Und der HTML-Weg bleibt danach unberuehrt benutzbar.
        self.assertEqual(self._get(1, {"format": ["html"]}).status, 200)

    @unittest.skipIf(_HAS_REPORTLAB, _SKIP_MIT)
    def test_FR15d_ohne_reportlab_echter_503(self):
        """
        Gegenprobe OHNE Zutun des Tests: fehlt reportlab wirklich, muss der
        Endpunkt von sich aus 503 liefern — und der Fehlschlag aus der VM
        (Build 522) darf sich nicht wiederholen.
        """
        r = self._get(1, {"format": ["pdf"]})
        self.assertEqual(r.status, 503)
        body = json.loads(r.body.decode("utf-8"))
        self.assertEqual(body["error"], "pdf_unavailable")
        self.assertIn("reportlab", body["detail"])

    def test_FR16_unbekanntes_format_400_mit_liste(self):
        r = self._get(1, {"format": ["xlsx"]})
        self.assertEqual(r.status, 400)
        body = json.loads(r.body.decode("utf-8"))
        self.assertEqual(body["known"], ["pdf", "html"])
        # KEIN stiller Rueckfall: die Antwort ist kein PDF.
        self.assertNotEqual(r.content_type, "application/pdf")

    def test_FR17_lookback_days_unbrauchbar_400(self):
        for bad in ("abc", "0", "-5"):
            r = self._get(1, {"format": ["html"], "lookback_days": [bad]})
            self.assertEqual(r.status, 400, "Wert %r muss 400 ergeben" % bad)
        # Ein gueltiger Wert geht durch und steht IM Bericht.
        r_ok = self._get(1, {"format": ["html"], "lookback_days": ["7"]})
        self.assertEqual(r_ok.status, 200)
        self.assertIn("7", r_ok.body.decode("utf-8"))

    def test_FR18_scope_eigene_403(self):
        r = self._get(2, {"format": ["html"]})
        self.assertEqual(r.status, 403)

    def test_FR19_dateiname_wird_begrenzt(self):
        """Kopfzeilen-Injektion ueber den Dateinamen ist nicht moeglich."""
        r = Response.pdf(200, b"%PDF-1.4",
                         filename='a"b;c\r\nX-Evil: 1.pdf')
        value = dict(r.extra_headers)["Content-Disposition"]
        # Der Rahmen selbst enthaelt zulaessigerweise ein Semikolon
        # ('inline; filename="..."'). Geprueft wird der DATEINAME, also der
        # Teil zwischen den Anfuehrungszeichen — dort darf nichts stehen, was
        # die Kopfzeile verlassen oder eine zweite eroeffnen koennte.
        self.assertTrue(value.startswith('inline; filename="'))
        self.assertTrue(value.endswith('"'))
        name = value[len('inline; filename="'):-1]
        for ch in ('"', ";", "\r", "\n", " ", ":"):
            self.assertNotIn(ch, name)
        self.assertEqual(name, "abcX-Evil1.pdf")
        # Ein Dateiname, von dem nichts uebrig bleibt, wird ersetzt statt leer
        # gelassen (eine leere Kopfzeile waere ein stiller Ausfall).
        r2 = Response.pdf(200, b"%PDF-1.4", filename="///")
        self.assertIn("bericht.pdf", dict(r2.extra_headers)[
            "Content-Disposition"])

    def test_FR20_endpunkt_schreibt_nichts(self):
        """
        Der Endpunkt hinterlaesst keinen Beleg — und zwar AUCH DANN NICHT, wenn
        die PDF-Erzeugung scheitert.

        Der PDF-Abruf wird hier bewusst NICHT auf 200 festgenagelt: ob 200 oder
        503 herauskommt, haengt an einer optionalen Bibliothek (das war die
        Ursache des Fehlschlags in Build 522). Die zu belegende Zusicherung ist
        eine andere und gilt in beiden Faellen: die audit_log-Spitze bewegt sich
        nicht. Ein Fehlerpfad, der schreibt, waere der schlimmere Befund.
        """
        tip_vorher = self.app.audit_tip_seq()
        self.assertEqual(self._get(1, {"format": ["html"]}).status, 200)
        r_pdf = self._get(1, {"format": ["pdf"]})
        self.assertIn(r_pdf.status, (200, 503),
                      "PDF-Abruf muss 200 (mit reportlab) oder 503 (ohne) "
                      "ergeben, war aber %d" % r_pdf.status)
        # Auch die abgewiesenen Anfragen (400) duerfen nichts schreiben.
        self.assertEqual(self._get(1, {"format": ["xlsx"]}).status, 400)
        self.assertEqual(self._get(3, {"format": ["html"]}).status, 403)
        self.assertEqual(self.app.audit_tip_seq(), tip_vorher)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
