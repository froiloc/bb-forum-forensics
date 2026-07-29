# =============================================================================
# tests/test_management_capacity_api.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle 7: Kapazitaet
# =============================================================================
# Testsuite fuer Build 558: die Schreibwege der Kapazitaetspflege.
#
# WIRKUNG STATT EXISTENZ: kein Test prueft, DASS ein Endpunkt antwortet.
# Jeder prueft, dass die Datenzeile ENTSTEHT und dass ein BELEG mit
# gekoppelter audit_seq daneben steht - denn genau diese Kopplung ist der
# Grund, warum die Pflege ueberhaupt ueber die Repos laeuft und nicht per
# INSERT im Endpunkt.
#
# KP01 - Arbeitszeit: 200, Zeile in person_worktime, Beleg WORKTIME_SET,
#        audit_seq der Zeile == seq des Belegs.
# KP02 - Abwesenheit: 200, Zeile in availability_entry, Beleg AVAILABILITY_SET.
# KP03 - Abwesenheit entfernen: Soft-Delete (Zeile BLEIBT), Beleg
#        AVAILABILITY_REMOVED.
# KP04 - Feiertag anlegen/entfernen: Belege HOLIDAY_ADDED/HOLIDAY_REMOVED.
# KP05 - Abwesenheitsgrund anlegen: Beleg AVAILABILITY_REASON_ADDED, und der
#        Grund ist danach in set_availability VERWENDBAR (frei erweiterbarer
#        Katalog, mc 2026-07-29).
# KP06 - Stammdaten-GET liefert alle vier Bestaende samt Zaehlern und der
#        festen Rechenart-Liste ('garantie'/'einschraenkung').
# KP07 - Fachfehler aus dem Repo kommen als 400 MIT Begruendung an
#        (nicht als 500 und nicht stumm).
# KP08 - ohne capacity.edit -> 403, und die Antwort NENNT das fehlende Recht.
# KP09 - scope 'eigene': fremde person_id -> 403; eigene -> 200.
# KP10 - scope 'eigene' auf anlagenweite Daten (Feiertag, Grund) -> 403.
# KP11 - scope 'eigene' entfernt FREMDEN Abwesenheitseintrag ueber dessen ID
#        -> 403. (Die Zielperson steht nicht in der Nutzlast, sondern an der
#        Zeile; wird sie nicht zuerst gelesen, ist das Loch offen.)
# KP12 - Arbeitszeit zweimal gesetzt -> ZWEI Zeilen (append-only), und der
#        Rechner nimmt die juengere Regel.
# KP13 - Stammdaten unter scope 'eigene': Personenliste auf die eigene
#        Person verkuerzt, fremde person_id -> 403.
# KP14 - Zeile ohne zugehoerige Person wird als 'unbekannt (#id)'
#        AUSGEWIESEN, nicht weggelassen (Grundregel 1).
#
# Version: v0.8.559 . Build: 559 . 2026-07-29
# =============================================================================

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.audit.event_types import EventType
from management.capacity.capacity_calculator import CapacityCalculator
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac.rbac_repo import RbacRepo
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


def _build(db_path):
    """Frische coordinator.db mit drei Personen und voller Migrationskette."""
    con = sqlite3.connect(db_path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_PERSON)
    for pid, un, disp, sup in ((1, "h0a2898", "Chefin", 1),
                               (2, "h002", "Mueller", 0),
                               (3, "h003", "Gamma", 0)):
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, 1, ?, 0, ?)", (pid, un, disp, sup,
                                             int(time.time())))
    con.execute(_OLD_SCRAPE_JOBS)
    MigrationRunner(con, discover(coordinator_migrations),
                    audit=AuditLog(con), deployed_by="tester").run()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return con


class CapacityApiTests(unittest.TestCase):
    """Schreibwege der Kapazitaetspflege (Build 558)."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        self.con = _build(self._db)
        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))

    def tearDown(self):
        try:
            self.con.close()
        except Exception:
            pass
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    # ------------------------------------------------------------- Helfer
    def _grant(self, role, scope, person_id):
        rbac = RbacRepo(self.con, self.writer)
        rbac.grant(role, "capacity.edit", scope=scope, actor_id=1)
        rbac.assign_role(person_id, role, actor_id=1)
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _app(self):
        return ManagementApp(self._db)

    def _reload(self):
        """
        Nach einem Schreibvorgang durch den Endpunkt neu einlesen.

        DER WRITER MUSS MIT: er haelt die Verbindung als Feld. Wird nur
        self.con ersetzt, arbeitet self.writer auf der GESCHLOSSENEN
        Verbindung weiter und ein spaeteres _grant() bricht mit
        'Cannot operate on a closed database' ab - ein Fehler im Testaufbau,
        der wie ein Fehler im Pruefling aussieht.
        """
        self.con.close()
        self.con = sqlite3.connect(self._db)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.writer = CoordinatorWriter(self.con, AuditLog(self.con))

    def _body(self, response):
        return json.loads(response.body.decode("utf-8"))

    def _event(self, seq):
        row = self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq=?", (seq,)).fetchone()
        self.assertIsNotNone(row, "Kein Beleg mit seq=%s" % seq)
        return row["event_type"]

    def _standardzeit(self, person_id=2):
        """Mo-Fr 480 Minuten ab 2026-01-01, ueber den Endpunkt gesetzt."""
        return self._app().dispatch_write(1, "/api/capacity/worktime", {
            "person_id": person_id, "effective_from": "2026-01-01",
            "mon_min": 480, "tue_min": 480, "wed_min": 480,
            "thu_min": 480, "fri_min": 480})

    # KP01 ---------------------------------------------------------------
    def test_kp01_worktime_schreibt_zeile_und_beleg(self):
        self._grant("supervisor", "alle", 1)
        r = self._standardzeit()
        self.assertEqual(r.status, 200, r.body)
        seq = self._body(r)["audit_seq"]

        self._reload()
        row = self.con.execute(
            "SELECT person_id, mon_min, audit_seq FROM person_worktime "
            "WHERE person_id=2").fetchone()
        self.assertIsNotNone(row, "Keine Arbeitszeit-Zeile entstanden.")
        self.assertEqual(row["mon_min"], 480)
        # Die Kopplung ist der eigentliche Pruefgegenstand.
        self.assertEqual(row["audit_seq"], seq)
        self.assertEqual(self._event(seq), EventType.WORKTIME_SET)

    # KP02 ---------------------------------------------------------------
    def test_kp02_availability_schreibt_zeile_und_beleg(self):
        self._grant("supervisor", "alle", 1)
        r = self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "einschraenkung",
            "value_minutes": 600})
        self.assertEqual(r.status, 200, r.body)
        seq = self._body(r)["audit_seq"]

        self._reload()
        row = self.con.execute(
            "SELECT kind, value_minutes, audit_seq FROM availability_entry"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["kind"], "einschraenkung")
        self.assertEqual(row["value_minutes"], 600)
        self.assertEqual(row["audit_seq"], seq)
        self.assertEqual(self._event(seq), EventType.AVAILABILITY_SET)

    # KP03 ---------------------------------------------------------------
    def test_kp03_availability_remove_ist_soft_delete(self):
        self._grant("supervisor", "alle", 1)
        self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "einschraenkung",
            "value_minutes": 600})
        self._reload()
        entry_id = self.con.execute(
            "SELECT id FROM availability_entry").fetchone()["id"]

        r = self._app().dispatch_write(
            1, "/api/capacity/availability/remove", {"entry_id": entry_id})
        self.assertEqual(r.status, 200, r.body)
        seq = self._body(r)["audit_seq"]

        self._reload()
        row = self.con.execute(
            "SELECT deleted_at FROM availability_entry WHERE id=?",
            (entry_id,)).fetchone()
        # Die Zeile BLEIBT - ein geloeschter Beleg waere kein Beleg mehr.
        self.assertIsNotNone(row, "Zeile wurde hart geloescht.")
        self.assertIsNotNone(row["deleted_at"])
        self.assertEqual(self._event(seq), EventType.AVAILABILITY_REMOVED)

    # KP04 ---------------------------------------------------------------
    def test_kp04_holiday_anlegen_und_entfernen(self):
        self._grant("supervisor", "alle", 1)
        r = self._app().dispatch_write(1, "/api/capacity/holiday", {
            "day": "2026-07-08", "label": "Testfeiertag"})
        self.assertEqual(r.status, 200, r.body)
        self.assertEqual(self._event(self._body(r)["audit_seq"]),
                         EventType.HOLIDAY_ADDED)

        self._reload()
        hid = self.con.execute("SELECT id FROM holiday").fetchone()["id"]
        r2 = self._app().dispatch_write(1, "/api/capacity/holiday/remove",
                                        {"holiday_id": hid})
        self.assertEqual(r2.status, 200, r2.body)
        self.assertEqual(self._event(self._body(r2)["audit_seq"]),
                         EventType.HOLIDAY_REMOVED)

        self._reload()
        self.assertIsNotNone(self.con.execute(
            "SELECT deleted_at FROM holiday WHERE id=?",
            (hid,)).fetchone()["deleted_at"])

    # KP05 ---------------------------------------------------------------
    def test_kp05_grund_ist_frei_erweiterbar_und_danach_nutzbar(self):
        self._grant("supervisor", "alle", 1)
        r = self._app().dispatch_write(1, "/api/capacity/reason", {
            "code": "schulung", "label": "Schulung", "sort": 30})
        self.assertEqual(r.status, 200, r.body)
        self.assertEqual(self._event(self._body(r)["audit_seq"]),
                         EventType.AVAILABILITY_REASON_ADDED)

        # Der eigentliche Beweis: der neue Grund ist sofort VERWENDBAR.
        # (set_availability prueft reason_code gegen den aktiven Katalog.)
        r2 = self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "einschraenkung",
            "value_pct": 50, "reason_code": "schulung"})
        self.assertEqual(r2.status, 200, r2.body)

    # KP06 ---------------------------------------------------------------
    def test_kp06_stammdaten_liefert_alle_bestaende(self):
        self._grant("supervisor", "alle", 1)
        self._standardzeit()
        self._app().dispatch_write(1, "/api/capacity/holiday", {
            "day": "2026-07-08", "label": "Testfeiertag"})

        r = self._app().dispatch(1, "/api/capacity/stammdaten", {})
        self.assertEqual(r.status, 200, r.body)
        b = self._body(r)
        self.assertEqual(b["counts"]["worktimes"], 1)
        self.assertEqual(b["counts"]["holidays"], 1)
        # Die Rechenarten sind schemagebunden und gehen als feste Liste raus.
        self.assertEqual(sorted(k["code"] for k in b["kinds"]),
                         ["einschraenkung", "garantie"])
        # Nachtrag Build 559: Namen gehoeren dazu, sonst zeigt die
        # Pflegemaske "#2" statt "Mueller".
        self.assertEqual(b["worktimes"][0]["display_name"], "Mueller")
        self.assertEqual(b["counts"]["persons"], 3)

    # KP13 ---------------------------------------------------------------
    def test_kp13_stammdaten_scope_eigene_nur_eigene_person(self):
        """Scope 'eigene': die Personenliste schrumpft auf die eigene Person,
        und eine abweichende person_id wird ABGELEHNT statt stillschweigend
        auf die eigene umgebogen - sonst stuenden fremde Ueberschriften
        ueber eigenen Daten."""
        self._grant("investigator", "eigene", 2)
        app = self._app()

        fremd = app.dispatch(2, "/api/capacity/stammdaten",
                             {"person_id": ["3"]})
        self.assertEqual(fremd.status, 403, fremd.body)

        r = app.dispatch(2, "/api/capacity/stammdaten", {})
        self.assertEqual(r.status, 200, r.body)
        b = self._body(r)
        self.assertEqual(b["person_id"], 2)
        self.assertEqual([p["id"] for p in b["persons"]], [2])

    # KP14 ---------------------------------------------------------------
    def test_kp14_zeile_ohne_person_wird_benannt(self):
        """Eine Arbeitszeit-Zeile, zu der es keine (Ermittler-)Person mehr
        gibt, verschwindet NICHT aus der Liste und bekommt auch keinen leeren
        Namen: sie wird als 'unbekannt (#id)' ausgewiesen. Ein stilles
        Weglassen waere genau die Auslassung, die Grundregel 1 verbietet."""
        self._grant("supervisor", "alle", 1)
        self._standardzeit()
        self._reload()
        # Person 2 ist keine Ermittlerin mehr -> faellt aus der Namensliste.
        self.con.execute("UPDATE person SET is_investigator=0 WHERE id=2")

        r = self._app().dispatch(1, "/api/capacity/stammdaten", {})
        self.assertEqual(r.status, 200, r.body)
        zeilen = self._body(r)["worktimes"]
        self.assertEqual(len(zeilen), 1, "Zeile wurde stillschweigend "
                                         "weggelassen.")
        self.assertEqual(zeilen[0]["display_name"], "unbekannt (#2)")

    # KP07 ---------------------------------------------------------------
    def test_kp07_fachfehler_wird_400_mit_begruendung(self):
        self._grant("supervisor", "alle", 1)
        # Verstoss gegen die Repo-Regel: genau EINES von pct/minutes.
        r = self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "einschraenkung",
            "value_pct": 50, "value_minutes": 600})
        self.assertEqual(r.status, 400, r.body)
        self.assertIn("value_pct", self._body(r)["detail"])

        # Unbekannte Rechenart -> ebenfalls 400, nicht 500.
        r2 = self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "urlaub",
            "value_pct": 50})
        self.assertEqual(r2.status, 400, r2.body)
        self.assertIn("kind", self._body(r2)["detail"])

    # KP08 ---------------------------------------------------------------
    def test_kp08_ohne_recht_403_mit_nennung(self):
        r = self._standardzeit()
        self.assertEqual(r.status, 403, r.body)
        self.assertEqual(self._body(r)["capability"], "capacity.edit")

    # KP09 ---------------------------------------------------------------
    def test_kp09_scope_eigene_nur_eigene_person(self):
        self._grant("investigator", "eigene", 2)
        app = self._app()

        fremd = app.dispatch_write(2, "/api/capacity/worktime", {
            "person_id": 3, "effective_from": "2026-01-01", "mon_min": 480})
        self.assertEqual(fremd.status, 403, fremd.body)
        self.assertIn("eigene", self._body(fremd)["detail"])

        eigen = app.dispatch_write(2, "/api/capacity/worktime", {
            "person_id": 2, "effective_from": "2026-01-01", "mon_min": 480})
        self.assertEqual(eigen.status, 200, eigen.body)

    # KP10 ---------------------------------------------------------------
    def test_kp10_scope_eigene_nicht_auf_anlagenweite_daten(self):
        self._grant("investigator", "eigene", 2)
        app = self._app()
        for pfad, nutzlast in (
                ("/api/capacity/holiday", {"day": "2026-07-08",
                                           "label": "X"}),
                ("/api/capacity/reason", {"code": "x", "label": "X"})):
            r = app.dispatch_write(2, pfad, nutzlast)
            self.assertEqual(r.status, 403, "%s: %s" % (pfad, r.body))
            self.assertIn("anlagenweite", self._body(r)["detail"])

    # KP11 ---------------------------------------------------------------
    def test_kp11_scope_eigene_entfernt_fremden_eintrag_nicht(self):
        # Die Leitung legt einen Eintrag fuer Person 3 an.
        self._grant("supervisor", "alle", 1)
        self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 3, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "einschraenkung",
            "value_minutes": 600})
        self._reload()
        entry_id = self.con.execute(
            "SELECT id FROM availability_entry").fetchone()["id"]

        # Person 2 pflegt nur sich selbst - und kennt die fremde ID trotzdem.
        self._grant("investigator", "eigene", 2)
        r = self._app().dispatch_write(
            2, "/api/capacity/availability/remove", {"entry_id": entry_id})
        self.assertEqual(r.status, 403, r.body)

        self._reload()
        self.assertIsNone(self.con.execute(
            "SELECT deleted_at FROM availability_entry WHERE id=?",
            (entry_id,)).fetchone()["deleted_at"])

    # KP12 ---------------------------------------------------------------
    def test_kp12_worktime_ist_append_only(self):
        self._grant("supervisor", "alle", 1)
        self._standardzeit()
        r2 = self._app().dispatch_write(1, "/api/capacity/worktime", {
            "person_id": 2, "effective_from": "2026-07-09",
            "mon_min": 300, "tue_min": 300, "wed_min": 300,
            "thu_min": 300, "fri_min": 300})
        self.assertEqual(r2.status, 200, r2.body)

        self._reload()
        zeilen = self.con.execute(
            "SELECT effective_from FROM person_worktime WHERE person_id=2 "
            "ORDER BY effective_from").fetchall()
        # Die alte Regel bleibt stehen - sie ist der Beleg fuer den Zeitraum,
        # in dem sie galt. Ein UPDATE haette sie spurlos ersetzt.
        self.assertEqual([z["effective_from"] for z in zeilen],
                         ["2026-01-01", "2026-07-09"])

        # Und der Rechner nimmt fuer Mo-Fr 06.-10.07. die juengere ab dem 09.
        r = CapacityCalculator(self.con).compute(2, "2026-07-06", "2026-07-10")
        self.assertEqual(r.basis, 3 * 480 + 2 * 300)


if __name__ == "__main__":
    unittest.main()
