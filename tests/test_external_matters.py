# =============================================================================
# tests/test_external_matters.py
# IT-Forensisches Ermittlungswerkzeug — Wiedervorlage externer Vorgaenge
# =============================================================================
# Testsuite fuer Build 385: M010 + MatterStatus + ExternalMattersRepo +
# Kalender-Leseschicht + Endpunkte + CLI.
#
# EX01 — M010: Tabelle, Indizes, RBAC-Seed; zweiter Lauf ist No-op (idempotent).
# EX02 — MatterStatus: Uebergaenge; Endzustaende sind UNWIDERRUFLICH.
# EX03 — MatterStatus: Ampel (rot/gelb/gruen) und der Sonderfall VERWAIST.
# EX04 — create(): auditiert; audit_seq/created_audit_seq gesetzt; Zeitstrahl-
#        Spiegel in case_events; FREITEXT steht NICHT im audit_log-Payload.
# EX05 — defer(): GRUND ist Pflicht; jedes Verschieben bekommt einen Beleg.
# EX06 — answer()/close(): Zustandsfolge; Abschluss ist endgueltig.
# EX07 — Kein unauditierter Schreibpfad (Repo ohne Writer verweigert).
# EX08 — Kalender: fuehrt Vorgaenge + Abwesenheiten + Feiertage zusammen;
#        UEBERFAELLIGES erscheint auch ausserhalb des Zeitraums.
# EX09 — Kalender: fehlendes Recht -> LEER, aber mit HINWEIS (Grundregel 1).
# EX10 — Endpunkte: /api/external + /api/calendar (200/403); Scope 'eigene'
#        sieht NUR die zugewiesenen Faelle.
# EX11 — Endpunkte: Schreibpfade (create/defer/close) auditiert; Scope-Bruch
#        wird mit 403 abgewiesen.
# EX12 — CLI: Liste, Exit 2 bei roter Ampel, add/defer/close.
#
# Version: v0.7.385 · Build: 385 · 2026-07-12
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
from management.capacity.availability_repo import AvailabilityRepo
from management.capacity.reason_repo import ReasonRepo
from management.external import external_admin
from management.external.external_matters_repo import (
    ExternalMattersError,
    ExternalMattersRepo,
)
from management.external.matter_status import MatterStatus, MatterStatusError
from management.calendar.calendar_repo import CalendarError, CalendarRepo
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

#: Fester Stichtag fuer ALLE Ampel-Tests. Er wird uebergeben, NIE aus der
#: Systemuhr gelesen — sonst haetten wir Tests, die je nach Testtag kippen.
TAG = "2026-07-12"


class ExternalMattersTests(unittest.TestCase):

    # ------------------------------------------------------------------ Aufbau
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")

        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(_PERSON)
        now = int(time.time())
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (1, 'h0a2898', 'Chefin', 1, 1, 0, ?)", (now,))
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (2, 'h002', 'Mueller', 1, 0, 0, ?)", (now,))
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (3, 'h003', 'Schmitz', 1, 0, 0, ?)", (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con

        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))
        self.rbac = RbacRepo(self.con, self.writer)
        self.cases = CasesRepo(self.con, self.writer)
        self.repo = ExternalMattersRepo(self.con, self.writer)

        # Faelle: 18 -> Mueller (person 2), 19 -> Schmitz (person 3).
        self.cases.create_case(18, "boarder18", actor_id=1)
        self.cases.create_case(19, "boarder19", actor_id=1)
        self.cases.assign(18, 2, actor_id=1)
        self.cases.assign(19, 3, actor_id=1)

        # Rechte: Chefin 'alle', Mueller 'eigene'. Schmitz bekommt NICHTS —
        # er ist die Gegenprobe fuer den Rechte-Ausfall.
        self.rbac.grant("supervisor", "external.view", scope="alle", actor_id=1)
        self.rbac.grant("supervisor", "external.edit", scope="alle", actor_id=1)
        self.rbac.grant("supervisor", "capacity.edit", scope="alle", actor_id=1)
        self.rbac.grant("investigator", "external.view", scope="eigene",
                        actor_id=1)
        self.rbac.grant("investigator", "external.edit", scope="eigene",
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

    # ------------------------------------------------------------------ Hilfen
    def _policy(self, person_id):
        return RbacResolver(self.con).resolve(person_id)

    def _app(self):
        return ManagementApp(db_path=self._db)

    def _mk(self, user_id=18, kind="bestandsdaten", wv="2026-07-20",
            betreff="Bestandsdaten Kennung xy", frist=7, actor=1):
        return self.repo.create(
            user_id=user_id, kind=kind, betreff=betreff,
            angefordert_am="2026-07-01", wiedervorlage_am=wv,
            adressat="Telekom AG", aktenzeichen="Az-1",
            vorwarnfrist_tage=frist, actor_id=actor)

    # ================================================================== EX01
    def test_ex01_migration_idempotent(self):
        tabs = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("external_matters", tabs)
        idx = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("ix_external_due", idx)
        self.assertIn("ix_external_case", idx)

        caps = {r[0] for r in self.con.execute(
            "SELECT code FROM rbac_capability")}
        self.assertIn("external.view", caps)
        self.assertIn("external.edit", caps)

        # Zweiter Lauf: No-op, keine Fehler, keine Dubletten.
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=AuditLog(self.con), deployed_by="tester").run()
        n = self.con.execute(
            "SELECT COUNT(*) FROM rbac_capability WHERE code='external.view'"
        ).fetchone()[0]
        self.assertEqual(n, 1)

    # ================================================================== EX02
    def test_ex02_transitions_are_final(self):
        self.assertEqual(MatterStatus.allowed_next("offen"),
                         ("beantwortet", "erfolglos"))
        self.assertEqual(MatterStatus.allowed_next("beantwortet"),
                         ("erledigt", "erfolglos"))
        # Endzustaende haben KEINE ausgehende Kante.
        self.assertEqual(MatterStatus.allowed_next("erledigt"), ())
        self.assertEqual(MatterStatus.allowed_next("erfolglos"), ())

        # 'offen' -> 'erledigt' ist BEWUSST nicht vorgesehen: ohne eingegangene
        # Antwort wird ohne Ergebnis abgeschlossen ('erfolglos').
        with self.assertRaises(MatterStatusError):
            MatterStatus.check_transition("offen", "erledigt")

        # Zurueckdrehen eines Abschlusses ist ausgeschlossen.
        with self.assertRaises(MatterStatusError) as ctx:
            MatterStatus.check_transition("erledigt", "offen")
        self.assertIn("ENDGUELTIG", str(ctx.exception))

        # Verschieben nur im offenen Zustand.
        MatterStatus.check_deferrable("offen")
        MatterStatus.check_deferrable("beantwortet")
        with self.assertRaises(MatterStatusError):
            MatterStatus.check_deferrable("erledigt")

    # ================================================================== EX03
    def test_ex03_ampel(self):
        def a(wv, status="offen", frist=7, case_status=None):
            return MatterStatus.ampel(status=status, wiedervorlage_am=wv,
                                      stichtag=TAG, vorwarnfrist_tage=frist,
                                      case_status=case_status)

        self.assertEqual(a("2026-07-12")[0], "rot")    # heute faellig
        self.assertEqual(a("2026-07-01")[0], "rot")    # ueberfaellig
        self.assertIn("Ueberfaellig", a("2026-07-01")[1])
        self.assertEqual(a("2026-07-19")[0], "gelb")   # genau Vorwarnfrist
        self.assertEqual(a("2026-07-20")[0], "gruen")  # 8 Tage -> gruen
        # Vorwarnfrist ist je Vorgang pflegbar (mc): mit 14 Tagen wird gelb.
        self.assertEqual(a("2026-07-20", frist=14)[0], "gelb")

        # Abgeschlossen -> neutral, egal welches Datum.
        self.assertEqual(a("2026-01-01", status="erledigt")[0], "neutral")

        # VERWAIST: Fall geschlossen, Vorgang offen -> IMMER rot.
        ampel, grund = a("2026-12-31", case_status="closed")
        self.assertEqual(ampel, "rot")
        self.assertIn("Fall ist geschlossen", grund)
        self.assertIn("nichts automatisch geschlossen", grund)

        # Kaputtes Datum wird NICHT stillschweigend auf heute gesetzt.
        with self.assertRaises(MatterStatusError):
            a("nicht-ein-datum")

    # ================================================================== EX04
    def test_ex04_create_is_audited_and_mirrored(self):
        res = self._mk()
        mid, seq = res["matter_id"], res["audit_seq"]

        row = self.repo.get(mid)
        self.assertEqual(row["status"], "offen")
        self.assertEqual(row["user_id"], 18)
        self.assertEqual(row["vorwarnfrist_tage"], 7)
        # Die Kopplung Zeile <-> Beleg ist gesetzt (kein audit_seq=0).
        self.assertEqual(row["audit_seq"], seq)
        self.assertEqual(row["created_audit_seq"], seq)

        ev = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq = ?",
            (seq,)).fetchone()
        self.assertEqual(ev["event_type"], "external_matter_created")
        payload = json.loads(ev["content"])
        # SENSIBILITAETSREGEL: der Freitext steht NICHT im Beleg, nur seine Laenge.
        self.assertNotIn("betreff", payload)
        self.assertIn("betreff_len", payload)
        self.assertEqual(payload["matter_id"], mid)

        # Zeitstrahl-Spiegel: der Fall zeigt, worauf er wartet.
        ce = self.con.execute(
            "SELECT event_kind, payload, audit_seq FROM case_events "
            "WHERE user_id = 18 AND event_kind = 'external_matter'").fetchone()
        self.assertIsNotNone(ce)
        self.assertEqual(ce["audit_seq"], seq)
        cep = json.loads(ce["payload"])
        self.assertEqual(cep["action"], "created")
        self.assertEqual(cep["betreff"], "Bestandsdaten Kennung xy")

        # Unbekannte Vorgangsart und leerer Betreff werden abgewiesen.
        with self.assertRaises(ExternalMattersError):
            self.repo.create(user_id=18, kind="quatsch", betreff="x",
                             angefordert_am=TAG, wiedervorlage_am=TAG,
                             actor_id=1)
        with self.assertRaises(ExternalMattersError):
            self.repo.create(user_id=18, kind="beschluss", betreff="  ",
                             angefordert_am=TAG, wiedervorlage_am=TAG,
                             actor_id=1)
        # Unbekannter Fall -> Fehler (keine verwaiste Zeile).
        with self.assertRaises(ExternalMattersError):
            self.repo.create(user_id=999, kind="beschluss", betreff="x",
                             angefordert_am=TAG, wiedervorlage_am=TAG,
                             actor_id=1)

    # ================================================================== EX05
    def test_ex05_defer_requires_reason(self):
        mid = self._mk()["matter_id"]

        # OHNE Grund: keine Aenderung. Ein stilles Verschieben ist genau die
        # Luecke, die dieses System schliessen soll.
        with self.assertRaises(ExternalMattersError) as ctx:
            self.repo.defer(mid, wiedervorlage_am="2026-08-01", grund="",
                            actor_id=2)
        self.assertIn("Grund ist Pflicht", str(ctx.exception))
        self.assertEqual(self.repo.get(mid)["wiedervorlage_am"], "2026-07-20")

        seq = self.repo.defer(mid, wiedervorlage_am="2026-08-01",
                              grund="Provider hat Fristverlaengerung erbeten",
                              actor_id=2)
        row = self.repo.get(mid)
        self.assertEqual(row["wiedervorlage_am"], "2026-08-01")
        self.assertEqual(row["audit_seq"], seq)

        ev = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq = ?",
            (seq,)).fetchone()
        self.assertEqual(ev["event_type"], "external_matter_deferred")
        p = json.loads(ev["content"])
        self.assertEqual(p["von"], "2026-07-20")
        self.assertEqual(p["auf"], "2026-08-01")
        self.assertNotIn("grund", p)          # Freitext nicht im Beleg
        self.assertIn("grund_len", p)

        # Der GRUND steht im Zeitstrahl — dort gehoert er hin.
        ce = self.con.execute(
            "SELECT payload FROM case_events WHERE audit_seq = ?",
            (seq,)).fetchone()
        self.assertIn("Fristverlaengerung", json.loads(ce["payload"])["grund"])

    # ================================================================== EX06
    def test_ex06_answer_close_final(self):
        mid = self._mk()["matter_id"]

        self.repo.answer(mid, ergebnis="Auskunft eingegangen, 3 Seiten",
                         actor_id=2)
        self.assertEqual(self.repo.get(mid)["status"], "beantwortet")

        seq = self.repo.close(mid, status="erledigt", actor_id=2)
        row = self.repo.get(mid)
        self.assertEqual(row["status"], "erledigt")
        self.assertEqual(row["closed_by"], 2)
        self.assertIsNotNone(row["closed_at"])
        # Bereits erfasstes Ergebnis wird beim Abschluss NICHT still geloescht.
        self.assertIn("Auskunft eingegangen", row["ergebnis"])
        self.assertEqual(row["audit_seq"], seq)

        # UNWIDERRUFLICH: kein Weg zurueck, auch nicht ueber close().
        with self.assertRaises(MatterStatusError):
            self.repo.close(mid, status="erfolglos", actor_id=2)
        with self.assertRaises(MatterStatusError):
            self.repo.defer(mid, wiedervorlage_am="2026-09-01",
                            grund="doch nochmal", actor_id=2)

        # Der zweite Vorgang darf direkt 'erfolglos' werden (ohne Antwort).
        mid2 = self._mk(wv="2026-07-25")["matter_id"]
        self.repo.close(mid2, status="erfolglos",
                        ergebnis="Provider antwortet nicht", actor_id=2)
        self.assertEqual(self.repo.get(mid2)["status"], "erfolglos")

    # ================================================================== EX07
    def test_ex07_no_unaudited_write(self):
        readonly = ExternalMattersRepo(self.con)          # KEIN Writer
        with self.assertRaises(ExternalMattersError) as ctx:
            readonly.create(user_id=18, kind="beschluss", betreff="x",
                            angefordert_am=TAG, wiedervorlage_am=TAG)
        self.assertIn("unauditierter Schreibpfad", str(ctx.exception))
        # Lesen bleibt erlaubt.
        self.assertEqual(readonly.list_matters(), [])

    # ================================================================== EX08
    def test_ex08_calendar_merges_sources(self):
        # Eine Wiedervorlage im Zeitraum, eine UEBERFAELLIGE davor.
        self._mk(wv="2026-07-20", betreff="Bestandsdaten")
        self._mk(user_id=19, wv="2026-06-01", betreff="Alter Beschluss",
                 kind="beschluss")

        # Abwesenheit (M008) + Feiertag (M008) — anderes Schreibmodell, gleiche Zeit.
        ReasonRepo(self.con, self.writer).add_reason("urlaub", "Urlaub",
                                                     actor_id=1)
        AvailabilityRepo(self.con, self.writer).set_availability(
            2, period_start="2026-07-15", period_end="2026-07-25",
            kind="einschraenkung", value_pct=100, reason_code="urlaub",
            actor_id=1)
        self.con.execute(
            "INSERT INTO holiday (day, label, region, audit_seq, created_by, "
            "created_at) VALUES ('2026-07-16', 'Testfeiertag', NULL, 1, 1, ?)",
            (int(time.time()),))

        cal = CalendarRepo(self.con, self._policy(1)).view(
            von="2026-07-01", bis="2026-07-31", stichtag=TAG)

        quellen = {q["key"]: q["count"] for q in cal["quellen"]}
        self.assertEqual(quellen["external"], 2)      # inkl. der ueberfaelligen
        self.assertEqual(quellen["availability"], 1)
        self.assertEqual(quellen["holiday"], 1)
        self.assertEqual(cal["count"], 4)

        # Der UEBERFAELLIGE Vorgang liegt VOR dem Zeitraum, erscheint aber
        # trotzdem — er darf beim Blaettern nicht aus dem Blick geraten.
        e0 = cal["entries"][0]
        self.assertEqual(e0["source"], "external")
        self.assertEqual(e0["ampel"], "rot")
        self.assertEqual(e0["von"], "2026-06-01")
        self.assertTrue(e0["ist_zeitpunkt"])
        self.assertIn("Ueberfaellig", e0["ampel_grund"])

        # Sortierung: Handlungsbedarf zuerst.
        self.assertEqual([e["ampel"] for e in cal["entries"]][0], "rot")
        self.assertEqual(cal["counts"]["rot"], 1)

        # Der Zeitraum-Eintrag (Abwesenheit) ist KEIN Zeitpunkt.
        abw = [e for e in cal["entries"] if e["source"] == "availability"][0]
        self.assertFalse(abw["ist_zeitpunkt"])
        self.assertEqual(abw["subject_kind"], "person")
        self.assertEqual(abw["ampel"], "neutral")

        # Die Rechengrundlage steht in der Antwort.
        self.assertEqual(cal["stichtag"], TAG)
        self.assertIn("Faelligkeiten berechnet zum", cal["stichtag_text"])

        # Verkehrter Zeitraum -> Fehler, nicht stillschweigend leer.
        with self.assertRaises(CalendarError):
            CalendarRepo(self.con, self._policy(1)).view(
                von="2026-07-31", bis="2026-07-01", stichtag=TAG)

    # ================================================================== EX09
    def test_ex09_calendar_says_when_it_is_silent(self):
        self._mk()
        # Schmitz (person 3) hat KEINE Rolle und damit KEIN Recht.
        cal = CalendarRepo(self.con, self._policy(3)).view(
            von="2026-07-01", bis="2026-07-31", stichtag=TAG)

        self.assertEqual(cal["count"], 0)
        # Aber der Kalender SCHWEIGT NICHT STUMM (Grundregel 1).
        text = " ".join(cal["hinweise"])
        self.assertIn("external.view", text)
        self.assertIn("capacity.edit", text)

        # Mueller (Scope 'eigene', Fall 18) sieht seinen Vorgang.
        cal2 = CalendarRepo(self.con, self._policy(2)).view(
            von="2026-07-01", bis="2026-07-31", stichtag=TAG)
        self.assertEqual(cal2["count"], 1)
        self.assertEqual(cal2["entries"][0]["subject_id"], 18)
        # Abwesenheiten sieht er NICHT (kein capacity.edit) — und erfaehrt es.
        self.assertIn("capacity.edit", " ".join(cal2["hinweise"]))

    # ================================================================== EX10
    def test_ex10_endpoints_read(self):
        self._mk(user_id=18, wv="2026-07-20")
        self._mk(user_id=19, wv="2026-07-21", kind="beschluss",
                 betreff="Beschluss")
        app = self._app()

        # Chefin (Scope 'alle'): beide Vorgaenge.
        r = app.dispatch(1, "/api/external", {"stichtag": TAG})
        self.assertEqual(r.status, 200)
        data = json.loads(r.body)
        self.assertEqual(data["scope"], "alle")
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["kinds"]), 11)      # inkl. osint/auswertung

        # Mueller (Scope 'eigene'): NUR sein Fall 18.
        r = app.dispatch(2, "/api/external", {"stichtag": TAG})
        self.assertEqual(r.status, 200)
        data = json.loads(r.body)
        self.assertEqual(data["scope"], "eigene")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["matters"][0]["user_id"], 18)

        # Fremder Fall ausdruecklich angefragt -> 403 (kein stilles Leer).
        r = app.dispatch(2, "/api/external", {"user_id": "19"})
        self.assertEqual(r.status, 403)

        # Schmitz: kein Recht -> 403.
        r = app.dispatch(3, "/api/external", {})
        self.assertEqual(r.status, 403)

        # Kalender
        r = app.dispatch(1, "/api/calendar",
                         {"von": "2026-07-01", "bis": "2026-07-31",
                          "stichtag": TAG})
        self.assertEqual(r.status, 200)
        cal = json.loads(r.body)
        self.assertEqual(cal["count"], 2)
        self.assertEqual(cal["stichtag"], TAG)

        # Fehlender Zeitraum -> 400.
        self.assertEqual(app.dispatch(1, "/api/calendar", {}).status, 400)

    # ================================================================== EX11
    def test_ex11_endpoints_write(self):
        app = self._app()

        # Mueller legt fuer SEINEN Fall an.
        r = app.dispatch_write(2, "/api/external/create", {
            "user_id": 18, "kind": "verkehrsdaten", "betreff": "Verkehrsdaten",
            "wiedervorlage_am": "2026-07-30", "vorwarnfrist_tage": 3})
        self.assertEqual(r.status, 200)
        mid = json.loads(r.body)["matter_id"]

        # ... aber NICHT fuer einen fremden Fall.
        r = app.dispatch_write(2, "/api/external/create", {
            "user_id": 19, "kind": "beschluss", "betreff": "fremd",
            "wiedervorlage_am": "2026-07-30"})
        self.assertEqual(r.status, 403)

        # Verschieben ohne Grund -> 400 (und nichts geaendert).
        r = app.dispatch_write(2, "/api/external/defer", {
            "matter_id": mid, "wiedervorlage_am": "2026-08-15", "grund": ""})
        self.assertEqual(r.status, 400)
        self.assertEqual(self.repo.get(mid)["wiedervorlage_am"], "2026-07-30")

        r = app.dispatch_write(2, "/api/external/defer", {
            "matter_id": mid, "wiedervorlage_am": "2026-08-15",
            "grund": "Nachfrage laeuft"})
        self.assertEqual(r.status, 200)
        seq = json.loads(r.body)["audit_seq"]
        ev = self.con.execute(
            "SELECT event_type, actor_id FROM audit_log WHERE seq = ?",
            (seq,)).fetchone()
        self.assertEqual(ev["event_type"], "external_matter_deferred")
        self.assertEqual(ev["actor_id"], 2)          # der Handelnde steht drin

        # Abschluss und dann ein zweiter Versuch -> 400 (unwiderruflich).
        r = app.dispatch_write(2, "/api/external/close", {
            "matter_id": mid, "status": "erfolglos", "ergebnis": "keine Antwort"})
        self.assertEqual(r.status, 200)
        r = app.dispatch_write(2, "/api/external/close", {
            "matter_id": mid, "status": "erledigt"})
        self.assertEqual(r.status, 400)

        # Unbekannter Vorgang -> 400, kein 500.
        r = app.dispatch_write(1, "/api/external/close",
                               {"matter_id": 9999, "status": "erledigt"})
        self.assertEqual(r.status, 400)

        # Ohne Recht -> 403.
        r = app.dispatch_write(3, "/api/external/create", {
            "user_id": 19, "kind": "osint", "betreff": "x",
            "wiedervorlage_am": "2026-08-01"})
        self.assertEqual(r.status, 403)

    # ================================================================== EX12
    def test_ex12_cli(self):
        self._mk(wv="2026-06-01")     # ueberfaellig -> rote Ampel

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = external_admin.main(
                ["--db", self._db, "list", "--stichtag", TAG])
        # Exit 2 = es gibt Handlungsbedarf. Ein Skript darf das nicht uebersehen.
        self.assertEqual(rc, 2)
        self.assertIn("ACHTUNG", err.getvalue())
        self.assertIn("Faelligkeiten berechnet zum", out.getvalue())

        # add + defer + close ueber die CLI.
        out = io.StringIO()
        with redirect_stdout(out):
            rc = external_admin.main([
                "--db", self._db, "add", "--user-id", "19",
                "--kind", "rechtshilfe", "--betreff", "Ersuchen NL",
                "--wiedervorlage", "2026-09-01", "--actor", "h0a2898"])
        self.assertEqual(rc, 0)
        self.assertIn("angelegt", out.getvalue())

        mid = self.con.execute(
            "SELECT id FROM external_matters WHERE user_id = 19"
        ).fetchone()[0]

        with redirect_stdout(io.StringIO()):
            rc = external_admin.main([
                "--db", self._db, "defer", "--id", str(mid),
                "--wiedervorlage", "2026-10-01", "--grund", "Justiz NL langsam",
                "--actor", "h0a2898"])
        self.assertEqual(rc, 0)
        self.assertEqual(self.repo.get(mid)["wiedervorlage_am"], "2026-10-01")

        # Unbekannte Kennung -> Fehler, kein stiller Beleg ohne Handelnden.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = external_admin.main([
                "--db", self._db, "close", "--id", str(mid),
                "--status", "erfolglos", "--actor", "gibtsnicht"])
        self.assertEqual(rc, 1)
        self.assertEqual(self.repo.get(mid)["status"], "offen")


if __name__ == "__main__":
    unittest.main()
