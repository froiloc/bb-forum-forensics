# =============================================================================
# tests/test_userinfo_results.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Ergebnisbewertung
# =============================================================================
# Testsuite fuer Build 390: ResultsEndpoint (forensischer Server) + Bugfix
# 'investigators' -> 'person' in userinfo_data.
#
# UE01 — GEGENPROBE ZUM BUGFIX: die Tabelle 'investigators' existiert nach den
#        Migrationen NICHT; ein JOIN darauf scheitert. Der ALTE Code haette
#        genau hier still 'nicht zugewiesen' geliefert.
# UE02 — Der KORRIGIERTE Join (auf 'person') liefert die Zuweisung.
# UE03 — Ein Datenbankfehler wird NICHT mehr zu None geschluckt, sondern als
#        {"error": ...} gemeldet (Grundregel 1).
# UE04 — GET /_forensic/results: Katalog + Stand + Historie + Kennzahl.
# UE05 — GET ohne results.view -> 403 MIT BEGRUENDUNG (nicht leere Karte).
# UE06 — POST /_forensic/results/assess: auditiert, append-only.
# UE07 — DIE KAPSELUNGSPROBE: eine 'subject_id' im Rumpf wird IGNORIERT — bewertet
#        wird ausschliesslich der geoeffnete Fall.
# UE08 — POST ohne results.edit -> 403, es wird NICHTS geschrieben.
# UE09 — POST ohne aufloesbaren Ermittler -> 403 (kein Beleg ohne Handelnden).
#
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.cases.cases_repo import CasesRepo
from management.results.results_repo import ResultsRepo
from forensic_api.results_endpoint import ResultsEndpoint

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


class _Handler:
    """Minimaler Ersatz fuer ForensicRequestHandler: faengt die Antwort ab."""

    def __init__(self):
        self.status = None
        self.body = None
        self.content_type = None

    def send_response_body(self, status, body, content_type=None,
                           extra_headers=None):
        self.status = status
        self.body = body
        self.content_type = content_type

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class UserinfoResultsTests(unittest.TestCase):

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
        self.cases.create_case(18, "boarder18", actor_id=1)
        self.cases.create_case(19, "boarder19", actor_id=1)
        self.cases.assign(18, 2, actor_id=1)         # Mueller

        self.rbac.grant("investigator", "results.view", scope="eigene",
                        actor_id=1)
        self.rbac.grant("investigator", "results.edit", scope="eigene",
                        actor_id=1)
        self.rbac.assign_role(2, "investigator", actor_id=1)
        # Schmitz (3) bleibt OHNE Rolle — die Gegenprobe.
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

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

    # ------------------------------------------------------------------ Hilfen
    def _endpoint(self, *, subject_id=18, investigator_id=2):
        cfg = MagicMock()
        cfg.get.side_effect = lambda key, *a: (
            self._db if key == "paths.coordinator_db" else None)
        ctx = MagicMock()
        ctx.subject_id = subject_id
        ctx.investigator_id = investigator_id
        bundle = MagicMock()
        return ResultsEndpoint(bundle, ctx, cfg)

    # ================================================================== UE01
    def test_ue01_gegenprobe_investigators_existiert_nicht(self):
        """
        Der Bug, den Build 390 behebt: der Join ging auf 'investigators'.
        Diese Tabelle gibt es seit M005 (Build 342) NICHT MEHR — und der alte
        Code machte daraus still ein 'nicht zugewiesen'.
        """
        namen = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        self.assertNotIn("investigators", namen)
        self.assertIn("person", namen)

        with self.assertRaises(sqlite3.OperationalError) as ctx:
            self.con.execute(
                "SELECT c.status, i.system_username FROM cases c "
                "LEFT JOIN investigators i ON i.id = c.assigned_to "
                "WHERE c.subject_id = 18").fetchone()
        self.assertIn("no such table", str(ctx.exception))

    # ================================================================== UE02
    def test_ue02_korrigierter_join_liefert_zuweisung(self):
        row = self.con.execute(
            "SELECT c.status, c.priority, p.system_username AS assigned_to, "
            "       c.note "
            "FROM cases c LEFT JOIN person p ON p.id = c.assigned_to "
            "WHERE c.subject_id = ?", (18,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["assigned_to"], "h002")     # NICHT None!
        self.assertEqual(row["status"], "open")

        # Ein NICHT zugewiesener Fall liefert korrekt None — das ist eine
        # echte Aussage, kein Fehler.
        row19 = self.con.execute(
            "SELECT p.system_username AS assigned_to FROM cases c "
            "LEFT JOIN person p ON p.id = c.assigned_to WHERE c.subject_id = ?",
            (19,)).fetchone()
        self.assertIsNone(row19["assigned_to"])

    # ================================================================== UE03
    def test_ue03_datenbankfehler_wird_gemeldet_nicht_geschluckt(self):
        """
        Grundregel 1: Ein Fehlschlag darf nicht still zu 'nicht zugewiesen'
        werden. _get_investigation_status liefert jetzt {"error": ...}.
        """
        from forensic_api.userinfo_data import UserinfoDataEndpoint

        cfg = MagicMock()
        ctx = MagicMock()
        ctx.subject_id = 18
        bundle = MagicMock()
        bundle.coordinator = object()          # vorhanden
        # Die ATTACH-Verbindung wirft (z. B. weil cdb fehlt).
        bundle.forensic._con.execute.side_effect = sqlite3.OperationalError(
            "no such table: cdb.cases")

        ep = UserinfoDataEndpoint(bundle, ctx, cfg)
        res = ep._get_investigation_status()
        self.assertIsInstance(res, dict)
        self.assertIn("error", res)            # NICHT None
        self.assertIn("no such table", res["error"])

        # Ohne coordinator.db ist None weiterhin richtig: das ist ein
        # Betriebszustand, kein Fehlschlag.
        bundle.coordinator = None
        self.assertIsNone(ep._get_investigation_status())

    # ================================================================== UE04
    def test_ue04_get_results(self):
        repo = ResultsRepo(self.con, self.writer)
        repo.assess(subject_id=18, criterion_code="abuser", extrem="schwerste",
                    confidence_code="verdacht", quality_code="fortlaufend",
                    note="Chat", actor_id=2)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        h = _Handler()
        self._endpoint().handle(h)
        self.assertEqual(h.status, 200)
        d = h.json()

        self.assertEqual(d["subject_id"], 18)
        self.assertTrue(d["can_edit"])
        self.assertEqual(len(d["catalog"]["criteria"]), 10)
        self.assertEqual(d["catalog"]["catalog_version"], 1)
        self.assertEqual(len(d["current"]), 1)
        self.assertEqual(len(d["history"]), 1)
        self.assertIn("NICHT abgestimmt", d["score"]["vermerk"])
        self.assertIn("identification", d["score"]["unbewertet"])

        # Die Semantik-Warnung der Skala reist mit.
        ab = [c for c in d["catalog"]["criteria"] if c["code"] == "abuser"][0]
        self.assertIn("SCHWERE", ab["quality_beschreibung"])

    # ================================================================== UE05
    def test_ue05_get_ohne_recht_403_mit_begruendung(self):
        h = _Handler()
        self._endpoint(investigator_id=3).handle(h)     # Schmitz, keine Rolle
        self.assertEqual(h.status, 403)
        d = h.json()
        self.assertEqual(d["capability"], "results.view")
        # MIT BEGRUENDUNG — der Ermittler soll wissen, WARUM er nichts sieht.
        self.assertIn("nicht vergeben", d["detail"])

    # ================================================================== UE06
    def test_ue06_post_assess_auditiert(self):
        h = _Handler()
        body = json.dumps({
            "criterion_code": "victim_identification", "extrem": "schwerste",
            "confidence_code": "wahrscheinlich", "quality_code": "alter",
            "note": "Chatverlauf S. 14"}).encode("utf-8")
        self._endpoint().handle_assess(h, body)
        self.assertEqual(h.status, 200)
        res = h.json()
        self.assertTrue(res["ok"])

        con = sqlite3.connect(self._db)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute(
                "SELECT * FROM investigation_results WHERE id = ?",
                (res["result_id"],)).fetchone()
            self.assertEqual(row["subject_id"], 18)
            self.assertEqual(row["confidence_ordinal"], 4)
            self.assertEqual(row["quality_ordinal"], 2)     # alter
            self.assertEqual(row["created_by"], 2)          # der Handelnde
            ev = con.execute(
                "SELECT event_type, actor_id FROM audit_log WHERE seq = ?",
                (res["audit_seq"],)).fetchone()
            self.assertEqual(ev["event_type"], "assessment_recorded")
            self.assertEqual(ev["actor_id"], 2)

            # APPEND-ONLY: eine zweite Erfassung ergaenzt, ueberschreibt nicht.
            h2 = _Handler()
            self._endpoint().handle_assess(h2, json.dumps({
                "criterion_code": "victim_identification",
                "extrem": "schwerste", "confidence_code": "gerichtsfest",
                "quality_code": "name"}).encode("utf-8"))
            self.assertEqual(h2.status, 200)
            n = con.execute(
                "SELECT COUNT(*) FROM investigation_results "
                "WHERE subject_id=18 AND criterion_code='victim_identification'"
            ).fetchone()[0]
            self.assertEqual(n, 2)
            cur = con.execute(
                "SELECT confidence_code FROM v_investigation_current "
                "WHERE subject_id=18 AND criterion_code='victim_identification'"
            ).fetchone()[0]
            self.assertEqual(cur, "gerichtsfest")
        finally:
            con.close()

        # Ungueltige Eingabe -> 400, kein 500.
        h3 = _Handler()
        self._endpoint().handle_assess(h3, json.dumps({
            "criterion_code": "cp_possession", "extrem": "beste",
            "confidence_code": "verdacht",
            "quality_code": "ort"}).encode("utf-8"))
        self.assertEqual(h3.status, 400)

    # ================================================================== UE07
    def test_ue07_KAPSELUNG_subject_id_im_rumpf_wird_ignoriert(self):
        """
        Die zentrale Kapselungsprobe: Der Ermittler koennte versuchen, einen
        FREMDEN Fall zu bewerten, indem er eine andere subject_id in den Rumpf
        schreibt. Der Endpunkt nimmt die subject_id AUSSCHLIESSLICH aus dem
        Kontext (dem geoeffneten Fall) — das Feld im Rumpf wird IGNORIERT.
        Fremde Faelle sind damit STRUKTURELL unmoeglich.
        """
        h = _Handler()
        body = json.dumps({
            "subject_id": 19,                       # <-- fremder Fall!
            "user_id": 19,                          # <-- Alt-Schluessel (vor
                                                    #     M019): ebenso ignoriert
            "criterion_code": "abuser", "extrem": "beste",
            "confidence_code": "verdacht"}).encode("utf-8")
        self._endpoint(subject_id=18).handle_assess(h, body)
        self.assertEqual(h.status, 200)

        con = sqlite3.connect(self._db)
        try:
            # Geschrieben wurde auf 18 — NICHT auf 19.
            n18 = con.execute(
                "SELECT COUNT(*) FROM investigation_results WHERE subject_id=18"
            ).fetchone()[0]
            n19 = con.execute(
                "SELECT COUNT(*) FROM investigation_results WHERE subject_id=19"
            ).fetchone()[0]
            self.assertEqual(n18, 1)
            self.assertEqual(n19, 0)
        finally:
            con.close()

    # ================================================================== UE08
    def test_ue08_post_ohne_recht_schreibt_nichts(self):
        h = _Handler()
        self._endpoint(investigator_id=3).handle_assess(h, json.dumps({
            "criterion_code": "abuser", "extrem": "beste",
            "confidence_code": "verdacht"}).encode("utf-8"))
        self.assertEqual(h.status, 403)
        self.assertIn("NICHTS geschrieben", h.json()["detail"])

        con = sqlite3.connect(self._db)
        try:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM investigation_results").fetchone()[0], 0)
        finally:
            con.close()

    # ================================================================== UE09
    def test_ue09_kein_beleg_ohne_handelnden(self):
        h = _Handler()
        self._endpoint(investigator_id=None).handle_assess(h, json.dumps({
            "criterion_code": "abuser", "extrem": "beste",
            "confidence_code": "verdacht"}).encode("utf-8"))
        self.assertEqual(h.status, 403)
        self.assertEqual(h.json()["error"], "no_investigator")

        con = sqlite3.connect(self._db)
        try:
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM investigation_results").fetchone()[0], 0)
        finally:
            con.close()

        # Auch GET verweigert — und sagt WARUM.
        h2 = _Handler()
        self._endpoint(investigator_id=None).handle(h2)
        self.assertEqual(h2.status, 403)
        self.assertEqual(h2.json()["error"], "no_investigator")


if __name__ == "__main__":
    unittest.main()
