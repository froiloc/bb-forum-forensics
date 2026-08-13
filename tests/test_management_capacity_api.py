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
# KP15 - DUBLETTENSPERRE: eine zweite AKTIVE Regel zum selben Stichtag
#        wird zurueckgewiesen - mit Feldangabe 'effective_from'.
# KP16 - Entfernen ist SOFT-DELETE: Zeile bleibt, deleted_at gesetzt,
#        Beleg WORKTIME_REMOVED TRAEGT DIE ENTFERNTEN WERTE.
# KP17 - nach dem Entfernen ist der Stichtag wieder frei.
# KP18 - Ersetzen: EINE Transaktion, ZWEI Belege, am Ende genau EINE
#        aktive Zeile mit dem neuen Wert.
# KP19 - Ersetzen schlaegt fehl -> NICHTS bleibt zurueck (weder die
#        entfernte Zeile noch ein Beleg): Rollback der ganzen Einheit.
# KP20 - Feldangabe im Fehler: ungueltige Minutenzahl nennt das Feld.
# KP21 - scope 'eigene' kann fremde Zeilen weder entfernen noch
#        ersetzen - auch nicht, indem als Zielperson man selbst
#        angegeben wird.
# KP22 - Stammdaten OHNE Schalter: entfernte Zeilen fehlen in der
#        Liste, ihre ZAHL steht aber trotzdem in der Antwort.
# KP23 - Stammdaten MIT ?include_deleted=1: entfernte Zeilen sind
#        dabei und als solche erkennbar (deleted_at gesetzt).
# KP24 - der Schalter wirkt auf ALLE VIER Bestaende, nicht nur auf
#        die Arbeitszeiten.
# KP25 - der Schalter aendert NICHTS an Rechten und Scope: eine
#        selbstpflegende Person sieht auch entfernte Zeilen nur
#        von sich.
#
# Build 709 (Vorgang 75f84fee) - DER ZEITFILTER:
# KP26 - ohne Schalter beginnt die Liste mit dem laufenden Monat.
# KP27 - die ZAHL der ausgeblendeten historischen Zeilen geht immer mit.
# KP28 - mit ?include_historic=1 sind sie dabei (und werden weiter gezaehlt).
# KP29 - gemessen wird am ENDE: was im Vormonat begann und noch laeuft,
#        bleibt sichtbar.
# KP30 - der Monatserste selbst bleibt sichtbar, der Tag davor nicht.
# KP31 - Arbeitszeiten und Gruende sind ausgenommen - mit Begruendung.
# KP32 - entfernt und historisch sind ZWEI Gruende: eine entfernte
#        historische Zeile braucht beide Schalter.
# KP33 - auch der zweite Schalter haengelt Rechte und Scope nicht aus.
#
# Version: v0.8.709 . Build: 709 . 2026-08-13
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

        # MITGEZOGEN IN BUILD 709 (Vorgang 75f84fee): Der Feiertag liegt im
        # Juli 2026 und ist damit - je nachdem, wann dieser Lauf stattfindet -
        # historisch. Seit Build 709 blendet die Sicht solche Zeilen
        # standardmaessig aus. Dieser Fall prueft, dass ALLE VIER BESTAENDE
        # geliefert werden; dafuer wird ausdruecklich mit eingeblendeter
        # Historie gefragt. Ohne den Schalter haenge das Ergebnis am
        # Kalendertag des Testlaufs - eine Zeitbombe im Bestand.
        r = self._app().dispatch(1, "/api/capacity/stammdaten",
                                 {"include_historic": ["1"]})
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

    # KP11b (Build 664) ---------------------------------------------------
    def test_kp11b_availability_replace_ersetzt_in_einem_zug(self):
        """Ersetzen ueber die Route: eine aktive Zeile, zwei Belege."""
        self._grant("supervisor", "alle", 1)
        self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "einschraenkung",
            "value_minutes": 600})
        self._reload()
        entry_id = self.con.execute(
            "SELECT id FROM availability_entry").fetchone()["id"]

        r = self._app().dispatch_write(
            1, "/api/capacity/availability/replace", {
                "entry_id": entry_id, "person_id": 2,
                "period_start": "2026-07-06", "period_end": "2026-07-08",
                "kind": "einschraenkung", "value_minutes": 300})
        self.assertEqual(r.status, 200, r.body)
        body = self._body(r)
        self.assertEqual(EventType.AVAILABILITY_REMOVED,
                         self._event(body["entfernt_seq"]))
        self.assertEqual(EventType.AVAILABILITY_SET,
                         self._event(body["gesetzt_seq"]))

        self._reload()
        aktiv = self.con.execute(
            "SELECT id, period_end, value_minutes FROM availability_entry "
            "WHERE deleted_at IS NULL").fetchall()
        self.assertEqual(1, len(aktiv))
        self.assertEqual("2026-07-08", aktiv[0]["period_end"])
        self.assertEqual(300, aktiv[0]["value_minutes"])
        # KEIN UPDATE: die alte Zeile steht noch, stillgelegt.
        alle = self.con.execute(
            "SELECT COUNT(*) c FROM availability_entry").fetchone()["c"]
        self.assertEqual(2, alle)

    # KP11c (Build 664) ---------------------------------------------------
    def test_kp11c_replace_prueft_BEIDE_personen(self):
        """
        DIE FALLE: die Zielperson steht in der Nutzlast, die Person der ALTEN
        Zeile nicht. Wer nur die Zielperson prueft, laesst eine selbst-
        pflegende Person fremde Zeilen entfernen, indem sie sich selbst als
        Ziel angibt - der Eintrag der anderen waere weg, und an seiner Stelle
        stuende einer fuer die Aufrufende.
        """
        self._grant("supervisor", "alle", 1)
        self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 3, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "einschraenkung",
            "value_minutes": 600})
        self._reload()
        entry_id = self.con.execute(
            "SELECT id FROM availability_entry").fetchone()["id"]

        self._grant("investigator", "eigene", 2)
        r = self._app().dispatch_write(
            2, "/api/capacity/availability/replace", {
                "entry_id": entry_id, "person_id": 2,
                "period_start": "2026-07-06", "period_end": "2026-07-10",
                "kind": "einschraenkung", "value_minutes": 60})
        self.assertEqual(r.status, 403, r.body)

        self._reload()
        # Nichts entfernt, nichts angelegt.
        self.assertIsNone(self.con.execute(
            "SELECT deleted_at FROM availability_entry WHERE id=?",
            (entry_id,)).fetchone()["deleted_at"])
        self.assertEqual(1, self.con.execute(
            "SELECT COUNT(*) c FROM availability_entry").fetchone()["c"])

    # KP11d (Build 664) ---------------------------------------------------
    def test_kp11d_replace_einer_entfernten_zeile_wird_erklaert(self):
        """Abweisung MIT Grund und mit Feldangabe - nicht nur mit Fehlercode."""
        self._grant("supervisor", "alle", 1)
        self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "einschraenkung",
            "value_minutes": 600})
        self._reload()
        entry_id = self.con.execute(
            "SELECT id FROM availability_entry").fetchone()["id"]
        self._app().dispatch_write(
            1, "/api/capacity/availability/remove", {"entry_id": entry_id})
        self._reload()

        r = self._app().dispatch_write(
            1, "/api/capacity/availability/replace", {
                "entry_id": entry_id, "person_id": 2,
                "period_start": "2026-07-06", "period_end": "2026-07-10",
                "kind": "einschraenkung", "value_minutes": 300})
        self.assertEqual(r.status, 400, r.body)
        body = self._body(r)
        self.assertIn("bereits entfernt", body["detail"])
        self.assertEqual("entry_id", body.get("feld"))

        self._reload()
        # Es ist keine neue Zeile entstanden.
        self.assertEqual(1, self.con.execute(
            "SELECT COUNT(*) c FROM availability_entry").fetchone()["c"])

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

    # KP15 ---------------------------------------------------------------
    def test_kp15_dublettensperre(self):
        self._grant("supervisor", "alle", 1)
        self.assertEqual(self._standardzeit().status, 200)
        r = self._app().dispatch_write(1, "/api/capacity/worktime", {
            "person_id": 2, "effective_from": "2026-01-01", "mon_min": 478})
        self.assertEqual(r.status, 400, r.body)
        b = self._body(r)
        self.assertEqual(b["feld"], "effective_from")
        self.assertIn("bereits eine", b["detail"])

        self._reload()
        # UND ES IST NICHTS ENTSTANDEN - kein halber Schreibvorgang.
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM person_worktime WHERE person_id=2"
        ).fetchone()[0], 1)

    # KP16 ---------------------------------------------------------------
    def test_kp16_entfernen_ist_soft_delete_mit_werten_im_beleg(self):
        self._grant("supervisor", "alle", 1)
        self._standardzeit()
        self._reload()
        wid = self.con.execute(
            "SELECT id FROM person_worktime WHERE person_id=2").fetchone()["id"]

        r = self._app().dispatch_write(1, "/api/capacity/worktime/remove",
                                       {"worktime_id": wid})
        self.assertEqual(r.status, 200, r.body)
        seq = self._body(r)["audit_seq"]
        self.assertEqual(self._event(seq), EventType.WORKTIME_REMOVED)

        self._reload()
        row = self.con.execute(
            "SELECT deleted_at FROM person_worktime WHERE id=?",
            (wid,)).fetchone()
        self.assertIsNotNone(row, "Zeile wurde hart geloescht.")
        self.assertIsNotNone(row["deleted_at"])

        # Der Beleg traegt die entfernten Werte - sonst stuende in der Akte
        # nur "Zeile entfernt".
        # Die Nutzlast des Belegs steht in der Spalte 'content'
        # (audit_log.py:220), nicht in 'payload'.
        inhalt = json.loads(self.con.execute(
            "SELECT content FROM audit_log WHERE seq=?", (seq,)).fetchone()[0])
        self.assertEqual(inhalt["minutes"]["mon_min"], 480)
        self.assertEqual(inhalt["effective_from"], "2026-01-01")

        # Zweites Entfernen erzeugt KEINEN Beleg ohne Wirkung.
        r2 = self._app().dispatch_write(1, "/api/capacity/worktime/remove",
                                        {"worktime_id": wid})
        self.assertEqual(r2.status, 400, r2.body)

    # KP17 ---------------------------------------------------------------
    def test_kp17_nach_entfernen_ist_der_stichtag_wieder_frei(self):
        self._grant("supervisor", "alle", 1)
        self._standardzeit()
        self._reload()
        wid = self.con.execute(
            "SELECT id FROM person_worktime WHERE person_id=2").fetchone()["id"]
        self._app().dispatch_write(1, "/api/capacity/worktime/remove",
                                   {"worktime_id": wid})
        r = self._app().dispatch_write(1, "/api/capacity/worktime", {
            "person_id": 2, "effective_from": "2026-01-01", "mon_min": 478})
        self.assertEqual(r.status, 200, r.body)

    # KP18 ---------------------------------------------------------------
    def test_kp18_ersetzen_zwei_belege_eine_aktive_zeile(self):
        self._grant("supervisor", "alle", 1)
        self._standardzeit()
        self._reload()
        wid = self.con.execute(
            "SELECT id FROM person_worktime WHERE person_id=2").fetchone()["id"]

        r = self._app().dispatch_write(1, "/api/capacity/worktime/replace", {
            "worktime_id": wid, "person_id": 2,
            "effective_from": "2026-01-01",
            "mon_min": 478, "tue_min": 478, "wed_min": 478, "thu_min": 478,
            "fri_min": 478})
        self.assertEqual(r.status, 200, r.body)
        b = self._body(r)
        self.assertEqual(self._event(b["entfernt_seq"]),
                         EventType.WORKTIME_REMOVED)
        self.assertEqual(self._event(b["gesetzt_seq"]), EventType.WORKTIME_SET)
        # Zwei EIGENE Belege, kein Sammelbeleg - und sie stehen unmittelbar
        # hintereinander in der Kette (eine Transaktion).
        self.assertEqual(b["gesetzt_seq"], b["entfernt_seq"] + 1)

        self._reload()
        aktiv = self.con.execute(
            "SELECT mon_min FROM person_worktime "
            "WHERE person_id=2 AND deleted_at IS NULL").fetchall()
        self.assertEqual([z["mon_min"] for z in aktiv], [478])
        # Die alte Zeile ist NICHT verschwunden, nur stillgelegt.
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM person_worktime WHERE person_id=2"
        ).fetchone()[0], 2)

    # KP19 ---------------------------------------------------------------
    def test_kp19_ersetzen_rollt_bei_fehler_vollstaendig_zurueck(self):
        """Der gefaehrlichste Fall: das Entfernen gelingt, das Setzen bricht
        ab. Bliebe der erste Schritt stehen, haette die Person zum Stichtag
        GAR KEINE Regel mehr - stiller Datenverlust durch eine Korrektur."""
        self._grant("supervisor", "alle", 1)
        self._standardzeit()
        self._reload()
        wid = self.con.execute(
            "SELECT id FROM person_worktime WHERE person_id=2").fetchone()["id"]
        vorher = self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0]

        r = self._app().dispatch_write(1, "/api/capacity/worktime/replace", {
            "worktime_id": wid, "person_id": 2,
            "effective_from": "2026-01-01", "mon_min": 99999})
        self.assertEqual(r.status, 400, r.body)
        self.assertEqual(self._body(r)["feld"], "mon_min")

        self._reload()
        row = self.con.execute(
            "SELECT mon_min, deleted_at FROM person_worktime WHERE id=?",
            (wid,)).fetchone()
        self.assertIsNone(row["deleted_at"], "Zeile blieb entfernt zurueck.")
        self.assertEqual(row["mon_min"], 480)
        self.assertEqual(self.con.execute(
            "SELECT MAX(seq) FROM audit_log").fetchone()[0], vorher,
            "Es ist ein Beleg ohne Wirkung zurueckgeblieben.")

    # KP20 ---------------------------------------------------------------
    def test_kp20_feldangabe_im_fehler(self):
        self._grant("supervisor", "alle", 1)
        r = self._app().dispatch_write(1, "/api/capacity/worktime", {
            "person_id": 2, "effective_from": "2026-01-01",
            "mon_min": 99999})
        self.assertEqual(r.status, 400, r.body)
        self.assertEqual(self._body(r)["feld"], "mon_min")

    # KP21 ---------------------------------------------------------------
    def test_kp21_scope_eigene_greift_bei_entfernen_und_ersetzen(self):
        self._grant("supervisor", "alle", 1)
        self._app().dispatch_write(1, "/api/capacity/worktime", {
            "person_id": 3, "effective_from": "2026-01-01", "mon_min": 480})
        self._reload()
        wid = self.con.execute(
            "SELECT id FROM person_worktime WHERE person_id=3").fetchone()["id"]

        self._grant("investigator", "eigene", 2)
        app = self._app()
        r = app.dispatch_write(2, "/api/capacity/worktime/remove",
                               {"worktime_id": wid})
        self.assertEqual(r.status, 403, r.body)

        # Und auch nicht ueber den Umweg "Zielperson bin ich selbst": die
        # Pruefung laeuft gegen BEIDE Personen.
        r2 = app.dispatch_write(2, "/api/capacity/worktime/replace", {
            "worktime_id": wid, "person_id": 2,
            "effective_from": "2026-01-01", "mon_min": 478})
        self.assertEqual(r2.status, 403, r2.body)

        self._reload()
        self.assertIsNone(self.con.execute(
            "SELECT deleted_at FROM person_worktime WHERE id=?",
            (wid,)).fetchone()["deleted_at"])

    # KP22 ---------------------------------------------------------------
    def test_kp22_ohne_schalter_fehlt_die_zeile_aber_nicht_ihre_zahl(self):
        """Der Kern von Grundregel 1 an dieser Stelle: eine ausgeblendete
        Zeile darf nicht spurlos verschwinden. Wer die Zahl nicht sieht, weiss
        nicht, dass es etwas einzublenden GIBT."""
        self._grant("supervisor", "alle", 1)
        self._standardzeit()
        self._reload()
        wid = self.con.execute(
            "SELECT id FROM person_worktime WHERE person_id=2").fetchone()["id"]
        self._app().dispatch_write(1, "/api/capacity/worktime/remove",
                                   {"worktime_id": wid})

        r = self._app().dispatch(1, "/api/capacity/stammdaten", {})
        self.assertEqual(r.status, 200, r.body)
        b = self._body(r)
        self.assertEqual(b["include_deleted"], False)
        self.assertEqual(b["counts"]["worktimes"], 0)
        self.assertEqual(b["entfernt"]["worktimes"], 1)

    # KP23 ---------------------------------------------------------------
    def test_kp23_mit_schalter_sind_entfernte_zeilen_dabei(self):
        self._grant("supervisor", "alle", 1)
        self._standardzeit()
        self._reload()
        wid = self.con.execute(
            "SELECT id FROM person_worktime WHERE person_id=2").fetchone()["id"]
        self._app().dispatch_write(1, "/api/capacity/worktime/remove",
                                   {"worktime_id": wid})

        r = self._app().dispatch(1, "/api/capacity/stammdaten",
                                 {"include_deleted": ["1"]})
        self.assertEqual(r.status, 200, r.body)
        b = self._body(r)
        self.assertEqual(b["include_deleted"], True)
        self.assertEqual(b["counts"]["worktimes"], 1)
        self.assertEqual(b["entfernt"]["worktimes"], 1)
        # Und sie ist ALS entfernt erkennbar - sonst saehe sie aus wie eine
        # gueltige Regel.
        self.assertIsNotNone(b["worktimes"][0]["deleted_at"])
        # Die Namensaufloesung greift auch hier (Build 559).
        self.assertEqual(b["worktimes"][0]["display_name"], "Mueller")

    # KP24 ---------------------------------------------------------------
    def test_kp24_schalter_wirkt_auf_alle_vier_bestaende(self):
        self._grant("supervisor", "alle", 1)
        app = self._app()
        app.dispatch_write(1, "/api/capacity/reason",
                           {"code": "urlaub", "label": "Urlaub"})
        app.dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2026-07-06",
            "period_end": "2026-07-10", "kind": "einschraenkung",
            "value_minutes": 600})
        app.dispatch_write(1, "/api/capacity/holiday",
                           {"day": "2026-07-08", "label": "Testfeiertag"})
        self._standardzeit()
        self._reload()

        aid = self.con.execute("SELECT id FROM availability_entry").fetchone()["id"]
        hid = self.con.execute("SELECT id FROM holiday").fetchone()["id"]
        wid = self.con.execute(
            "SELECT id FROM person_worktime").fetchone()["id"]
        app = self._app()
        app.dispatch_write(1, "/api/capacity/availability/remove",
                           {"entry_id": aid})
        app.dispatch_write(1, "/api/capacity/holiday/remove",
                           {"holiday_id": hid})
        app.dispatch_write(1, "/api/capacity/worktime/remove",
                           {"worktime_id": wid})

        # MITGEZOGEN IN BUILD 709: 'include_historic' steht hier, weil die
        # Testzeilen im Juli 2026 liegen. Gemessen werden soll der
        # ENTFERNT-Schalter; der Zeitfilter darf das Ergebnis nicht
        # ueberlagern (und nicht vom Kalendertag des Laufs abhaengen).
        ohne = self._body(self._app().dispatch(
            1, "/api/capacity/stammdaten", {"include_historic": ["1"]}))
        self.assertEqual([ohne["counts"]["worktimes"],
                          ohne["counts"]["availability"],
                          ohne["counts"]["holidays"]], [0, 0, 0])
        self.assertEqual([ohne["entfernt"]["worktimes"],
                          ohne["entfernt"]["availability"],
                          ohne["entfernt"]["holidays"]], [1, 1, 1])

        mit = self._body(self._app().dispatch(
            1, "/api/capacity/stammdaten",
            {"include_deleted": ["1"], "include_historic": ["1"]}))
        self.assertEqual([mit["counts"]["worktimes"],
                          mit["counts"]["availability"],
                          mit["counts"]["holidays"]], [1, 1, 1])

    # KP25 ---------------------------------------------------------------
    def test_kp25_schalter_haengelt_rechte_und_scope_nicht_aus(self):
        """Der Schalter ist eine ANZEIGE-Frage, keine Rechtefrage. Er darf
        weder das Recht ersetzen noch den Scope aufweichen."""
        self._grant("supervisor", "alle", 1)
        self._app().dispatch_write(1, "/api/capacity/worktime", {
            "person_id": 3, "effective_from": "2026-01-01", "mon_min": 480})
        self._reload()
        wid = self.con.execute(
            "SELECT id FROM person_worktime WHERE person_id=3").fetchone()["id"]
        self._app().dispatch_write(1, "/api/capacity/worktime/remove",
                                   {"worktime_id": wid})

        # Ohne Recht: 403, auch mit Schalter.
        r = self._app().dispatch(3, "/api/capacity/stammdaten",
                                 {"include_deleted": ["1"]})
        self.assertEqual(r.status, 403, r.body)

        # Mit scope 'eigene': nur die eigenen (entfernten) Zeilen.
        self._grant("investigator", "eigene", 2)
        b = self._body(self._app().dispatch(
            2, "/api/capacity/stammdaten", {"include_deleted": ["1"]}))
        self.assertEqual(b["person_id"], 2)
        self.assertEqual(b["counts"]["worktimes"], 0)
        self.assertEqual(b["entfernt"]["worktimes"], 0,
                         "Fremde entfernte Zeile wurde mitgezaehlt.")

    # =====================================================================
    # Build 709 (Vorgang 75f84fee): der ZEITFILTER der Pflegeliste.
    #
    # Der Vorgang: "sollten per Default nur Daten mit Bezug ab dem aktuellen
    # Monat angezeigt werden ... eine Checkbox 'auch historische Daten
    # anzeigen'". Die Regel selbst ist in tests/test_capacity_zeitfilter.py
    # mit festen Datumsangaben gemessen; HIER geht es um das, was der
    # Endpunkt daraus macht - und darum, dass die Zahl der ausgeblendeten
    # Zeilen NICHT verschwindet (Grundregel 1).
    #
    # Die Faelle rechnen den Monatsersten selbst aus, weil sie sonst am
    # Kalendertag des Laufs haengen. Gegen die Regel gespiegelt wird dabei
    # nichts: geprueft werden Zeilen, die eindeutig davor bzw. danach liegen,
    # und zusaetzlich die GRENZE selbst.
    # =====================================================================

    def _monatserster(self):
        from datetime import date
        return date.today().replace(day=1).isoformat()

    def _tag_davor(self):
        from datetime import date, timedelta
        return (date.today().replace(day=1) - timedelta(days=1)).isoformat()

    # KP26 ---------------------------------------------------------------
    def test_kp26_ohne_schalter_beginnt_die_liste_mit_dem_monat(self):
        self._grant("supervisor", "alle", 1)
        app = self._app()
        # Eine abgelaufene und eine kuenftige Abwesenheit, dazu zwei
        # Feiertage derselben Lage.
        app.dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2020-01-01",
            "period_end": "2020-01-31", "kind": "einschraenkung",
            "value_minutes": 600})
        app.dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2099-01-01",
            "period_end": "2099-01-31", "kind": "einschraenkung",
            "value_minutes": 600})
        app.dispatch_write(1, "/api/capacity/holiday",
                           {"day": "2020-05-01", "label": "Alt"})
        app.dispatch_write(1, "/api/capacity/holiday",
                           {"day": "2099-05-01", "label": "Kuenftig"})

        b = self._body(self._app().dispatch(1, "/api/capacity/stammdaten", {}))
        self.assertEqual(b["include_historic"], False)
        self.assertEqual(b["historisch_ab"], self._monatserster())
        self.assertEqual(b["counts"]["availability"], 1)
        self.assertEqual(b["counts"]["holidays"], 1)
        self.assertEqual(b["availability"][0]["period_end"], "2099-01-31")
        self.assertEqual(b["holidays"][0]["day"], "2099-05-01")

    # KP27 ---------------------------------------------------------------
    def test_kp27_die_zahl_der_ausgeblendeten_geht_immer_mit(self):
        """Derselbe Gedanke wie KP22 bei den entfernten Zeilen: wer die Zahl
        nicht sieht, weiss nicht, dass es etwas einzublenden GIBT."""
        self._grant("supervisor", "alle", 1)
        app = self._app()
        app.dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2020-01-01",
            "period_end": "2020-01-31", "kind": "einschraenkung",
            "value_minutes": 600})
        app.dispatch_write(1, "/api/capacity/holiday",
                           {"day": "2020-05-01", "label": "Alt"})

        b = self._body(self._app().dispatch(1, "/api/capacity/stammdaten", {}))
        self.assertEqual(b["counts"]["availability"], 0)
        self.assertEqual(b["counts"]["holidays"], 0)
        self.assertEqual(b["historisch"]["availability"], 1)
        self.assertEqual(b["historisch"]["holidays"], 1)

    # KP28 ---------------------------------------------------------------
    def test_kp28_mit_schalter_sind_historische_zeilen_dabei(self):
        self._grant("supervisor", "alle", 1)
        app = self._app()
        app.dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2020-01-01",
            "period_end": "2020-01-31", "kind": "einschraenkung",
            "value_minutes": 600})
        app.dispatch_write(1, "/api/capacity/holiday",
                           {"day": "2020-05-01", "label": "Alt"})

        b = self._body(self._app().dispatch(
            1, "/api/capacity/stammdaten", {"include_historic": ["1"]}))
        self.assertEqual(b["include_historic"], True)
        self.assertEqual(b["counts"]["availability"], 1)
        self.assertEqual(b["counts"]["holidays"], 1)
        # Auch beim Einblenden wird gezaehlt - die Oberflaeche sagt dann,
        # WIE VIELE der angezeigten Zeilen historisch sind.
        self.assertEqual(b["historisch"]["availability"], 1)
        self.assertEqual(b["historisch"]["holidays"], 1)

    # KP29 ---------------------------------------------------------------
    def test_kp29_gemessen_wird_am_ende_des_zeitraums(self):
        """DER KERN: Eine Abwesenheit, die VOR dem laufenden Monat begann und
        noch laeuft, gehoert in die Liste. Wer am Anfang misst, blendet die
        Angabe aus, die die Rechnung des laufenden Monats bestimmt."""
        self._grant("supervisor", "alle", 1)
        self._app().dispatch_write(1, "/api/capacity/availability", {
            "person_id": 2, "period_start": "2020-01-01",
            "period_end": "2099-12-31", "kind": "garantie",
            "value_minutes": 120})

        b = self._body(self._app().dispatch(1, "/api/capacity/stammdaten", {}))
        self.assertEqual(b["counts"]["availability"], 1)
        self.assertEqual(b["historisch"]["availability"], 0)

    # KP30 ---------------------------------------------------------------
    def test_kp30_die_grenze_selbst_bleibt_sichtbar(self):
        """Der Vorgang sagt: 'beginnen die Daten ab dem 1. des aktuellen
        Monats'. Der Erste gehoert dazu, der Tag davor nicht."""
        self._grant("supervisor", "alle", 1)
        app = self._app()
        app.dispatch_write(1, "/api/capacity/holiday",
                           {"day": self._monatserster(), "label": "Grenze"})
        app.dispatch_write(1, "/api/capacity/holiday",
                           {"day": self._tag_davor(), "label": "Davor"})

        b = self._body(self._app().dispatch(1, "/api/capacity/stammdaten", {}))
        self.assertEqual([h["label"] for h in b["holidays"]], ["Grenze"])
        self.assertEqual(b["historisch"]["holidays"], 1)

    # KP31 ---------------------------------------------------------------
    def test_kp31_arbeitszeiten_und_gruende_bleiben_unberuehrt(self):
        """Der Zeitfilter greift NUR dort, wo ein Datum steht, und das ist
        keine Auslassung: Die Regel-Arbeitszeiten sind die Belegkette (ihre
        derzeit gueltige Zeile traegt fast immer einen Stichtag aus der
        Vergangenheit), und der Gruendekatalog hat ueberhaupt keinen
        Zeitbezug - ohne ihn waeren bestehende Abwesenheitszeilen nicht
        lesbar."""
        self._grant("supervisor", "alle", 1)
        app = self._app()
        app.dispatch_write(1, "/api/capacity/worktime", {
            "person_id": 2, "effective_from": "2020-01-01", "mon_min": 480})
        app.dispatch_write(1, "/api/capacity/reason",
                           {"code": "urlaub", "label": "Urlaub"})

        b = self._body(self._app().dispatch(1, "/api/capacity/stammdaten", {}))
        self.assertEqual(b["counts"]["worktimes"], 1)
        self.assertEqual(b["counts"]["reasons"], 1)
        self.assertNotIn("worktimes", b["historisch"])
        self.assertNotIn("reasons", b["historisch"])

    # KP32 ---------------------------------------------------------------
    def test_kp32_beide_schalter_wirken_unabhaengig(self):
        """Entfernt und historisch sind zwei verschiedene Gruende. Eine
        entfernte HISTORISCHE Zeile braucht BEIDE Schalter."""
        self._grant("supervisor", "alle", 1)
        app = self._app()
        app.dispatch_write(1, "/api/capacity/holiday",
                           {"day": "2020-05-01", "label": "Alt"})
        self._reload()
        hid = self.con.execute("SELECT id FROM holiday").fetchone()["id"]
        self._app().dispatch_write(1, "/api/capacity/holiday/remove",
                                   {"holiday_id": hid})

        nur_entfernt = self._body(self._app().dispatch(
            1, "/api/capacity/stammdaten", {"include_deleted": ["1"]}))
        self.assertEqual(nur_entfernt["counts"]["holidays"], 0,
                         "Der Entfernt-Schalter allein holt keine "
                         "historische Zeile zurueck.")
        self.assertEqual(nur_entfernt["historisch"]["holidays"], 1)

        beide = self._body(self._app().dispatch(
            1, "/api/capacity/stammdaten",
            {"include_deleted": ["1"], "include_historic": ["1"]}))
        self.assertEqual(beide["counts"]["holidays"], 1)

    # KP33 ---------------------------------------------------------------
    def test_kp33_zeitfilter_haengelt_rechte_und_scope_nicht_aus(self):
        """Wie KP25 fuer den zweiten Schalter: eine Anzeigefrage darf weder
        das Recht ersetzen noch den Scope aufweichen."""
        self._grant("supervisor", "alle", 1)
        r = self._app().dispatch(3, "/api/capacity/stammdaten",
                                 {"include_historic": ["1"]})
        self.assertEqual(r.status, 403, r.body)

        self._grant("investigator", "eigene", 2)
        b = self._body(self._app().dispatch(
            2, "/api/capacity/stammdaten", {"include_historic": ["1"]}))
        self.assertEqual(b["person_id"], 2)


if __name__ == "__main__":
    unittest.main()
