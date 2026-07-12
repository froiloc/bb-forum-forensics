# =============================================================================
# tests/test_investigation_results.py
# IT-Forensisches Ermittlungswerkzeug — Ermittlungsergebnis-Bewertung
# =============================================================================
# Testsuite fuer Build 387: M011 + Katalog + ResultsRepo + PriorityScorer +
# Endpunkte + CLIs.
#
# IR01 — M011: Tabellen, Sicht, Trigger, Indizes, Seed, RBAC; idempotent.
# IR02 — Seed: 10 Kriterien, 4 Skalen; drei Kriterien MIT Qualitaetsskala,
#        sieben (vorerst) OHNE (mc: kommen spaeter per CLI nach).
# IR03 — assess(): auditiert; NUMERIK EINGEFROREN (ordinal + catalog_version
#        stehen in der Bewertungszeile); Zeitstrahl-Spiegel; Freitext NICHT
#        im audit_log.
# IR04 — APPEND-ONLY: Korrektur ist eine NEUE Zeile; v_investigation_current
#        zeigt die juengste; die Historie bleibt VOLLSTAENDIG.
# IR05 — APPEND-ONLY auf DB-Ebene: UPDATE und DELETE schlagen fehl (Trigger).
# IR06 — Kriterium OHNE Qualitaetsskala weist eine Qualitaetsangabe ZURUECK
#        (kein stilles Verschlucken).
# IR07 — DIE KERNPROBE: Skala wird umnummeriert -> ALTE Bewertungen behalten
#        ihren Zahlenwert und ihre Katalogversion. Zeitreihen kippen NICHT.
# IR08 — Katalog: neues Kriterium + nachgetragene Qualitaetsskala OHNE
#        Migration; Skalenwechsel ist verboten; deprecate loescht NICHT.
# IR09 — PriorityScorer: flach/ungewichtet, nur 'schwerste', VERMERK immer
#        dabei, unbewertete Kriterien werden GENANNT.
# IR10 — stats(): je Kriterium, nicht ueber Kriterien hinweg.
# IR11 — Endpunkte lesend: catalog/results/stats; Scope 'eigene' sieht nur
#        zugewiesene Faelle; die STATISTIK verlangt Scope 'alle' (403).
# IR12 — Endpunkte schreibend: assess auditiert; Scope-Bruch -> 403.
# IR13 — CLIs: results_admin (catalog/assess/history/score) und catalog_admin.
#
# Version: v0.7.387 · Build: 387 · 2026-07-12
# =============================================================================

import io
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.rbac.rbac_resolver import RbacResolver
from management.cases.cases_repo import CasesRepo
from management.results import catalog_admin, results_admin
from management.results.assessment_catalog_repo import (
    AssessmentCatalogRepo,
    CatalogError,
)
from management.results.priority_scorer import PriorityScorer, VERMERK
from management.results.results_repo import ResultsError, ResultsRepo
from management.server.management_app import ManagementApp

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
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


class InvestigationResultsTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")

        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        for pid, kennung, name, sup in ((1, "h0a2898", "Chefin", 1),
                                        (2, "h002", "Mueller", 0),
                                        (3, "h003", "Schmitz", 0)):
            con.execute(
                "INSERT INTO person (id, system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, kennung, name, sup, now))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)
        self.cat = AssessmentCatalogRepo(self.con, self.writer)
        self.repo = ResultsRepo(self.con, self.writer)

        self.cases.create_case(18, "boarder18", actor_id=1)
        self.cases.create_case(19, "boarder19", actor_id=1)
        self.cases.assign(18, 2, actor_id=1)          # Mueller
        self.cases.assign(19, 3, actor_id=1)          # Schmitz

        # Chefin: 'alle'. Mueller: 'eigene'. Schmitz: NICHTS (Gegenprobe).
        self.rbac.grant("supervisor", "results.view", scope="alle", actor_id=1)
        self.rbac.grant("supervisor", "results.edit", scope="alle", actor_id=1)
        self.rbac.grant("investigator", "results.view", scope="eigene",
                        actor_id=1)
        self.rbac.grant("investigator", "results.edit", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(1, "supervisor", actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.unlink(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    def _app(self):
        return ManagementApp(db_path=self._db)

    def _policy(self, pid):
        return RbacResolver(self.con).resolve(pid)

    # ================================================================== IR01
    def test_ir01_migration(self):
        tabs = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for t in ("assessment_scale", "assessment_scale_item",
                  "assessment_criterion", "assessment_catalog_version",
                  "investigation_results"):
            self.assertIn(t, tabs)

        views = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='view'")}
        self.assertIn("v_investigation_current", views)

        trgs = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertIn("trg_investigation_results_no_update", trgs)
        self.assertIn("trg_investigation_results_no_delete", trgs)

        caps = {r[0] for r in self.con.execute(
            "SELECT code FROM rbac_capability")}
        self.assertIn("results.view", caps)
        self.assertIn("results.edit", caps)

        self.assertEqual(self.cat.version(), 1)

        # Zweiter Lauf: No-op, keine Dubletten.
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=AuditLog(self.con), deployed_by="tester").run()
        self.assertEqual(
            self.con.execute("SELECT COUNT(*) FROM assessment_criterion"
                             ).fetchone()[0], 10)

    # ================================================================== IR02
    def test_ir02_seed(self):
        crits = self.cat.criteria()
        self.assertEqual(len(crits), 10)
        by = {c["code"]: c for c in crits}

        # Die drei Kriterien MIT Qualitaetsskala (mc).
        self.assertEqual(by["location_identification"]["quality_scale"],
                         "location_quality")
        self.assertEqual(by["victim_identification"]["quality_scale"],
                         "victim_quality")
        self.assertEqual(by["abuser"]["quality_scale"], "abuser_quality")

        # Die sieben ohne — sie laufen zunaechst NUR mit Konfidenz.
        for c in ("identification", "cp_possession", "cp_distribution",
                  "cp_production", "jp_possession", "jp_distribution",
                  "jp_production"):
            self.assertIsNone(by[c]["quality_scale"])

        # Konfidenz-Skala: 6 Stufen, unbestimmt=0 .. gerichtsfest=5.
        conf = {i["code"]: i["ordinal"]
                for i in self.cat.items("confidence")}
        self.assertEqual(conf["unbestimmt"], 0)
        self.assertEqual(conf["gerichtsfest"], 5)
        self.assertEqual(len(conf), 6)

        # Location: Praezision (Meldeanschrift am hoechsten).
        loc = {i["code"]: i["ordinal"]
               for i in self.cat.items("location_quality")}
        self.assertEqual(loc["meldeanschrift"], 4)
        self.assertEqual(loc["land"], 1)

        # Abuser: ANDERE Semantik (Schwere/Aktualitaet) — sie steht in der
        # Beschreibung der Skala, damit niemand die Zahlen vermischt.
        ab = {i["code"]: i["ordinal"]
              for i in self.cat.items("abuser_quality")}
        self.assertEqual(ab["fortlaufend"], 3)
        self.assertEqual(ab["kontaktlos"], 1)
        besch = {s["code"]: s["beschreibung"] for s in self.cat.scales()}
        self.assertIn("SCHWERE", besch["abuser_quality"])
        self.assertIn("PRAEZISION", besch["location_quality"])

    # ================================================================== IR03
    def test_ir03_assess_audited_and_frozen(self):
        res = self.repo.assess(
            user_id=18, criterion_code="location_identification",
            extrem="beste", confidence_code="wahrscheinlich",
            quality_code="ort", note="IP-Auswertung ergab Essen",
            actor_id=2)
        rid, seq = res["result_id"], res["audit_seq"]

        row = dict(self.con.execute(
            "SELECT * FROM investigation_results WHERE id = ?",
            (rid,)).fetchone())
        # NUMERIK EINGEFROREN: Zahl UND Katalogversion stehen in der Zeile.
        self.assertEqual(row["confidence_ordinal"], 4)     # wahrscheinlich
        self.assertEqual(row["quality_ordinal"], 3)        # ort
        self.assertEqual(row["catalog_version"], 1)
        self.assertEqual(row["audit_seq"], seq)

        ev = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq = ?",
            (seq,)).fetchone()
        self.assertEqual(ev["event_type"], "assessment_recorded")
        p = json.loads(ev["content"])
        self.assertEqual(p["confidence_ordinal"], 4)
        # Sensibilitaetsregel: der Freitext steht NICHT im Beleg.
        self.assertNotIn("note", p)
        self.assertIn("note_len", p)

        # Zeitstrahl-Spiegel.
        ce = self.con.execute(
            "SELECT payload FROM case_events WHERE audit_seq = ?",
            (seq,)).fetchone()
        cep = json.loads(ce["payload"])
        self.assertEqual(cep["criterion"], "location_identification")
        self.assertIn("Essen", cep["note"])

        # Unbekanntes Kriterium / unbekannte Stufe / falsches Extrem.
        with self.assertRaises(ResultsError):
            self.repo.assess(user_id=18, criterion_code="gibtsnicht",
                             extrem="beste", confidence_code="verdacht",
                             actor_id=2)
        with self.assertRaises(ResultsError):
            self.repo.assess(user_id=18, criterion_code="abuser",
                             extrem="beste", confidence_code="voellig_sicher",
                             actor_id=2)
        with self.assertRaises(ResultsError):
            self.repo.assess(user_id=18, criterion_code="abuser",
                             extrem="mittel", confidence_code="verdacht",
                             actor_id=2)

    # ================================================================== IR04
    def test_ir04_append_only_history(self):
        # Erkenntnisgewinn: Verdacht -> wahrscheinlich -> gerichtsfest.
        for conf in ("verdacht", "wahrscheinlich", "gerichtsfest"):
            self.repo.assess(user_id=18, criterion_code="identification",
                             extrem="beste", confidence_code=conf, actor_id=2)

        hist = self.repo.history(18, criterion_code="identification")
        self.assertEqual(len(hist), 3)                 # NICHTS ueberschrieben

        cur = self.repo.current(18)
        self.assertEqual(len(cur), 1)                  # der juengste Stand
        self.assertEqual(cur[0]["confidence_code"], "gerichtsfest")
        self.assertEqual(cur[0]["confidence_ordinal"], 5)
        self.assertEqual(cur[0]["confidence_label"], "gerichtsfest")

        # 'schwerste' und 'beste' sind UNABHAENGIG voneinander.
        self.repo.assess(user_id=18, criterion_code="identification",
                         extrem="schwerste", confidence_code="verdacht",
                         actor_id=2)
        cur = {(r["criterion_code"], r["extrem"]): r
               for r in self.repo.current(18)}
        self.assertEqual(cur[("identification", "beste")]["confidence_code"],
                         "gerichtsfest")
        self.assertEqual(
            cur[("identification", "schwerste")]["confidence_code"], "verdacht")

    # ================================================================== IR05
    def test_ir05_append_only_enforced_by_db(self):
        rid = self.repo.assess(
            user_id=18, criterion_code="cp_possession", extrem="schwerste",
            confidence_code="verdacht", actor_id=2)["result_id"]

        # Der Schutz haengt NICHT allein am Repo — ein Trigger blockt auch
        # direktes SQL (das Repo koennte man umgehen, den Trigger nicht).
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.con.execute(
                "UPDATE investigation_results SET confidence_code='gerichtsfest' "
                "WHERE id = ?", (rid,))
        self.assertIn("append-only", str(ctx.exception))

        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("DELETE FROM investigation_results WHERE id = ?",
                             (rid,))
        # Die Zeile steht unveraendert.
        self.assertEqual(self.con.execute(
            "SELECT confidence_code FROM investigation_results WHERE id=?",
            (rid,)).fetchone()[0], "verdacht")

    # ================================================================== IR06
    def test_ir06_quality_without_scale_rejected(self):
        # cp_possession hat (noch) KEINE Qualitaetsskala.
        with self.assertRaises(ResultsError) as ctx:
            self.repo.assess(user_id=18, criterion_code="cp_possession",
                             extrem="schwerste", confidence_code="verdacht",
                             quality_code="ort", actor_id=2)
        self.assertIn("keine Qualitaetsskala", str(ctx.exception))
        # NICHTS wurde geschrieben (kein stilles Verschlucken der Angabe).
        self.assertEqual(self.repo.current(18), [])

        # Ohne Qualitaet geht es.
        self.repo.assess(user_id=18, criterion_code="cp_possession",
                         extrem="schwerste", confidence_code="verdacht",
                         actor_id=2)
        cur = self.repo.current(18)[0]
        self.assertIsNone(cur["quality_code"])
        self.assertIsNone(cur["quality_ordinal"])

    # ================================================================== IR07
    def test_ir07_KERNPROBE_umnummerierung_kippt_keine_zeitreihe(self):
        """
        Die wichtigste Probe des Moduls: eine Skala wird SPAETER geaendert.
        Alte Bewertungen muessen ihren damaligen Zahlenwert BEHALTEN — sonst
        wuerden Zeitreihen ihre Bedeutung rueckwirkend aendern, still und
        unbemerkt.
        """
        alt = self.repo.assess(
            user_id=18, criterion_code="location_identification",
            extrem="beste", confidence_code="verdacht", quality_code="ort",
            actor_id=2)
        alt_row = dict(self.con.execute(
            "SELECT * FROM investigation_results WHERE id=?",
            (alt["result_id"],)).fetchone())
        self.assertEqual(alt_row["quality_ordinal"], 3)
        self.assertEqual(alt_row["catalog_version"], 1)

        # Jetzt wird der Katalog erweitert (feinere Abstufung).
        self.cat.add_item("location_quality", "hausnummer", "Hausnummer",
                          ordinal=5, sort=5, actor_id=1)
        self.assertEqual(self.cat.version(), 2)

        # Die ALTE Bewertung ist UNVERAENDERT — Zahl und Katalogversion.
        alt_row2 = dict(self.con.execute(
            "SELECT * FROM investigation_results WHERE id=?",
            (alt["result_id"],)).fetchone())
        self.assertEqual(alt_row2["quality_ordinal"], 3)
        self.assertEqual(alt_row2["catalog_version"], 1)

        # Eine NEUE Bewertung traegt die NEUE Katalogversion.
        neu = self.repo.assess(
            user_id=18, criterion_code="location_identification",
            extrem="beste", confidence_code="gerichtsfest",
            quality_code="hausnummer", actor_id=2)
        neu_row = dict(self.con.execute(
            "SELECT * FROM investigation_results WHERE id=?",
            (neu["result_id"],)).fetchone())
        self.assertEqual(neu_row["quality_ordinal"], 5)
        self.assertEqual(neu_row["catalog_version"], 2)

        # Beide Staende sind in der Historie nachvollziehbar.
        hist = self.repo.history(18)
        self.assertEqual([h["catalog_version"] for h in hist], [2, 1])

    # ================================================================== IR08
    def test_ir08_catalog_grows_without_migration(self):
        # Neues Kriterium OHNE Migration (der ausdrueckliche Zweck, mc).
        self.cat.add_criterion("grooming", "Grooming (Kontaktanbahnung)",
                               sort=45, actor_id=1)
        self.assertEqual(len(self.cat.criteria()), 11)
        self.repo.assess(user_id=18, criterion_code="grooming",
                         extrem="schwerste", confidence_code="verdacht",
                         actor_id=2)

        # Qualitaetsskala NACHTRAEGLICH: genau der Weg fuer die CP/JP-Kriterien.
        self.cat.add_scale("cp_quality", "CP-Beweisqualitaet",
                           beschreibung="ordinal misst die BEWEISQUALITAET.",
                           actor_id=1)
        self.cat.add_item("cp_quality", "unbestimmt", "unbestimmt",
                          ordinal=0, actor_id=1)
        self.cat.add_item("cp_quality", "asserviert", "asserviert",
                          ordinal=3, actor_id=1)
        self.cat.set_quality_scale("cp_possession", "cp_quality", actor_id=1)
        self.assertEqual(
            self.cat.criterion("cp_possession")["quality_scale"], "cp_quality")
        self.repo.assess(user_id=18, criterion_code="cp_possession",
                         extrem="schwerste", confidence_code="gerichtsfest",
                         quality_code="asserviert", actor_id=2)

        # Ein WECHSEL der Skala ist verboten — alte Bewertungen zeigten sonst
        # auf Punkte einer fremden Skala.
        with self.assertRaises(CatalogError) as ctx:
            self.cat.set_quality_scale("cp_possession", "location_quality",
                                       actor_id=1)
        self.assertIn("NEUES Kriterium", str(ctx.exception))

        # deprecate LOESCHT NICHT: der Punkt bleibt lesbar, verschwindet nur
        # aus den Auswahllisten.
        self.cat.deprecate("item", "asserviert", scale_code="cp_quality",
                           actor_id=1)
        aktiv = [i["code"] for i in self.cat.items("cp_quality")]
        self.assertNotIn("asserviert", aktiv)
        self.assertEqual(
            self.cat.item("cp_quality", "asserviert")["label"], "asserviert")
        # Die bestehende Bewertung bleibt lesbar (Label wird aufgeloest).
        cur = {(r["criterion_code"], r["extrem"]): r
               for r in self.repo.current(18)}
        self.assertEqual(
            cur[("cp_possession", "schwerste")]["quality_label"], "asserviert")
        # Aber NEU bewerten kann man damit nicht mehr.
        with self.assertRaises(ResultsError):
            self.repo.assess(user_id=19, criterion_code="cp_possession",
                             extrem="beste", confidence_code="verdacht",
                             quality_code="asserviert", actor_id=1)

    # ================================================================== IR09
    def test_ir09_scorer(self):
        self.repo.assess(user_id=18, criterion_code="identification",
                         extrem="schwerste", confidence_code="gerichtsfest",
                         actor_id=2)                              # 5
        self.repo.assess(user_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         quality_code="fortlaufend", actor_id=2)  # 3
        # 'beste' geht NICHT in den Score ein (Priorisierung nach der
        # GRAVIERENDSTEN, nicht der bestbelegten Erkenntnis).
        self.repo.assess(user_id=18, criterion_code="cp_production",
                         extrem="beste", confidence_code="gerichtsfest",
                         actor_id=2)

        alle = [c["code"] for c in self.cat.criteria()]
        res = PriorityScorer().score_with_gaps(self.repo.current(18), alle)

        self.assertEqual(res["score"], 8.0)          # 5 + 3, flach/ungewichtet
        self.assertEqual(res["basis"], 2)
        # Der VERMERK ist IMMER dabei — eine Zahl ohne ihn waere eine
        # unbelegte Behauptung.
        self.assertEqual(res["vermerk"], VERMERK)
        self.assertIn("NICHT abgestimmt", res["vermerk"])

        # Die LUECKE wird ausdruecklich genannt (dort ist zu ermitteln).
        self.assertIn("victim_identification", res["unbewertet"])
        self.assertNotIn("identification", res["unbewertet"])
        self.assertEqual(res["abdeckung"], 0.2)      # 2 von 10

        # Die Qualitaet wird AUSGEWIESEN, aber NICHT addiert (andere Semantik).
        ab = [b for b in res["beitraege"] if b["criterion"] == "abuser"][0]
        self.assertEqual(ab["quality"], "fortlaufend")
        self.assertEqual(ab["beitrag"], 3.0)         # NICHT 3 + 3

        # Gewichtung ist ein PARAMETER, kein Umbau.
        gew = PriorityScorer({"abuser": 2.0}).score(self.repo.current(18))
        self.assertEqual(gew["score"], 11.0)         # 5 + 3*2

    # ================================================================== IR10
    def test_ir10_stats(self):
        self.repo.assess(user_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         quality_code="fortlaufend", actor_id=2)
        self.repo.assess(user_id=19, criterion_code="abuser",
                         extrem="schwerste", confidence_code="gerichtsfest",
                         quality_code="ehemalig", actor_id=1)
        # Korrektur an Fall 18 -> die Statistik zaehlt nur den AKTUELLEN Stand.
        self.repo.assess(user_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="wahrscheinlich",
                         quality_code="fortlaufend", actor_id=2)

        st = self.repo.stats()
        self.assertEqual(st["faelle"], 2)
        ab = st["criteria"]["abuser"]["schwerste"]
        self.assertEqual(ab["n"], 2)                       # nicht 3!
        self.assertEqual(ab["conf_mittel"], 4.5)           # (4 + 5) / 2
        self.assertEqual(ab["conf_hist"],
                         {"wahrscheinlich": 1, "gerichtsfest": 1})
        self.assertEqual(ab["qual_mittel"], 2.5)           # (3 + 2) / 2

        # Scope 'eigene' mit LEERER Zuweisung liefert nichts — nicht alles.
        self.assertEqual(self.repo.stats(user_ids=[])["faelle"], 0)
        self.assertEqual(self.repo.stats(user_ids=[18])["faelle"], 1)

    # ================================================================== IR11
    def test_ir11_endpoints_read(self):
        self.repo.assess(user_id=18, criterion_code="abuser",
                         extrem="schwerste", confidence_code="verdacht",
                         quality_code="fortlaufend", actor_id=2)
        app = self._app()

        r = app.dispatch(1, "/api/results/catalog", {})
        self.assertEqual(r.status, 200)
        cat = json.loads(r.body)
        self.assertEqual(len(cat["criteria"]), 10)
        self.assertEqual(cat["catalog_version"], 1)
        self.assertEqual(cat["extreme"], ["schwerste", "beste"])
        # Die Semantik-Warnung reist mit.
        ab = [c for c in cat["criteria"] if c["code"] == "abuser"][0]
        self.assertIn("SCHWERE", ab["quality_beschreibung"])

        r = app.dispatch(2, "/api/results", {"user_id": "18"})
        self.assertEqual(r.status, 200)
        d = json.loads(r.body)
        self.assertEqual(d["scope"], "eigene")
        self.assertEqual(len(d["current"]), 1)
        self.assertEqual(len(d["history"]), 1)
        self.assertIn("NICHT abgestimmt", d["score"]["vermerk"])

        # Fremder Fall -> 403 (kein stilles Leer).
        self.assertEqual(app.dispatch(2, "/api/results",
                                      {"user_id": "19"}).status, 403)
        # Kein Recht -> 403.
        self.assertEqual(app.dispatch(3, "/api/results",
                                      {"user_id": "19"}).status, 403)

        # Die STATISTIK verlangt Scope 'alle'.
        r = app.dispatch(1, "/api/results/stats", {})
        self.assertEqual(r.status, 200)
        self.assertIn("hinweis", json.loads(r.body))
        # Der Ermittler mit 'eigene' bekommt 403 — NICHT eine stillschweigend
        # zusammengeschrumpfte Statistik, die wie eine Gesamtauswertung aussaehe.
        self.assertEqual(app.dispatch(2, "/api/results/stats", {}).status, 403)

    # ================================================================== IR12
    def test_ir12_endpoints_write(self):
        app = self._app()

        r = app.dispatch_write(2, "/api/results/assess", {
            "user_id": 18, "criterion_code": "victim_identification",
            "extrem": "schwerste", "confidence_code": "wahrscheinlich",
            "quality_code": "alter", "note": "Chatverlauf S. 14"})
        self.assertEqual(r.status, 200)
        seq = json.loads(r.body)["audit_seq"]
        ev = self.con.execute(
            "SELECT event_type, actor_id FROM audit_log WHERE seq=?",
            (seq,)).fetchone()
        self.assertEqual(ev["event_type"], "assessment_recorded")
        self.assertEqual(ev["actor_id"], 2)

        # Fremder Fall -> 403.
        self.assertEqual(app.dispatch_write(2, "/api/results/assess", {
            "user_id": 19, "criterion_code": "abuser", "extrem": "beste",
            "confidence_code": "verdacht"}).status, 403)

        # Ungueltige Eingaben -> 400, kein 500.
        self.assertEqual(app.dispatch_write(1, "/api/results/assess", {
            "user_id": 18, "criterion_code": "cp_possession",
            "extrem": "beste", "confidence_code": "verdacht",
            "quality_code": "ort"}).status, 400)
        self.assertEqual(app.dispatch_write(1, "/api/results/assess", {
            "user_id": 999, "criterion_code": "abuser", "extrem": "beste",
            "confidence_code": "verdacht"}).status, 400)

        # Ohne Recht -> 403.
        self.assertEqual(app.dispatch_write(3, "/api/results/assess", {
            "user_id": 19, "criterion_code": "abuser", "extrem": "beste",
            "confidence_code": "verdacht"}).status, 403)

    # ================================================================== IR13
    def test_ir13_clis(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = results_admin.main(["--db", self._db, "catalog"])
        self.assertEqual(rc, 0)
        self.assertIn("Katalogversion: 1", out.getvalue())
        self.assertIn("location_identification", out.getvalue())

        out = io.StringIO()
        with redirect_stdout(out):
            rc = results_admin.main([
                "--db", self._db, "assess", "--user-id", "18",
                "--criterion", "abuser", "--extrem", "schwerste",
                "--confidence", "verdacht", "--quality", "fortlaufend",
                "--note", "Chat 2024", "--actor", "h002"])
        self.assertEqual(rc, 0)
        self.assertIn("Beleg", out.getvalue())

        out = io.StringIO()
        with redirect_stdout(out):
            rc = results_admin.main(["--db", self._db, "score",
                                     "--user-id", "18"])
        self.assertEqual(rc, 0)
        # Der Vermerk steht IMMER dabei — umrahmt.
        self.assertIn("PROVISORISCH", out.getvalue())
        self.assertIn("NOCH NICHT BEWERTET", out.getvalue())

        # Unbekannte Kennung -> Fehler, kein Beleg ohne Handelnden.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = results_admin.main([
                "--db", self._db, "assess", "--user-id", "18",
                "--criterion", "abuser", "--extrem", "beste",
                "--confidence", "verdacht", "--actor", "gibtsnicht"])
        self.assertEqual(rc, 1)

        # catalog_admin: neues Kriterium OHNE Migration.
        out = io.StringIO()
        with redirect_stdout(out):
            rc = catalog_admin.main([
                "--db", self._db, "add-criterion", "--code", "grooming",
                "--label", "Grooming", "--actor", "h0a2898"])
        self.assertEqual(rc, 0)
        self.assertIn("Katalogversion ist jetzt 2", out.getvalue())
        self.assertIn("NICHT rueckwirkend", out.getvalue())

        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        try:
            self.assertEqual(len(AssessmentCatalogRepo(con).criteria()), 11)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
