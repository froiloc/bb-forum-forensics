# =============================================================================
# tests/test_management_escalation_ack.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Eskalationen (AP-2G)
# =============================================================================
# Testsuite fuer Build 517: der AUDITIERTE SCHREIBPFAD zur Eskalation
# (Quittierung + Widerruf). Befund Uebergabe 440-453 §3.3: "Die Eskalation ist
# nur auswertend — der auditierte Schreibpfad fehlt."
#
# Der wichtigste Test dieser Suite ist AK05: eine Quittierung darf eine
# Eskalation NICHT verschwinden lassen. Waere das anders, liesse sich ein
# liegengebliebener Fall per Klick unsichtbar machen, ohne dass sich an ihm
# etwas aendert — die gefaehrlichste Form eines stillen Beweisverlusts.
#
# AK01 — M027 legt Tabelle, Indizes und die Faehigkeit 'escalation.ack' an;
#        zweiter Lauf ist No-Op (Idempotenz)
# AK02 — ohne escalation.ack -> 403. escalation.view allein genuegt NICHT
#        (ein Lese-Grant bringt kein Schreibrecht mit)
# AK03 — Begruendung ist Pflicht -> 400 und es wird NICHTS geschrieben
# AK04 — Quittierung schreibt Zeile UND Audit-Beleg atomar; die Kette bleibt
#        intakt; der Freitext steht NICHT im Audit-Payload (Sensibilitaet)
# AK05 — die Eskalation BLEIBT in der Liste und traegt ihren Vermerk
#        (quittieren ist KEIN Erledigen)
# AK06 — die systemische Regel (subject_id null) ist quittierbar — sie ist der
#        wichtigste Fall der Sicht und darf nicht am Pflichtfeld scheitern
# AK07 — zweiter gueltiger Vermerk zu derselben Eskalation -> 400 (Fachregel
#        wird INNERHALB der Transaktion durchgesetzt)
# AK08 — Widerruf ohne Grund -> 400; Widerruf mit Grund -> Zeile BLEIBT, nur
#        is_active kippt; danach ist erneutes Quittieren moeglich
# AK09 — doppelter Widerruf -> 400 (kein irrefuehrender zweiter Beleg)
# AK10 — 'outdated': der Fall ist heute laenger inaktiv als bei der
#        Quittierung — reine Tatsache, ohne zusaetzliche Schwelle
# AK11 — annotate_items ist REIN: keine Meldung wird entfernt oder umsortiert
# AK12 — 'acknowledgeable' spiegelt Recht UND Struktur; ohne das Recht ist es
#        false, obwohl die Sicht lesbar bleibt
#
# Version: v0.8.517 · Build: 517 · 2026-07-24
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
from management.cases.cases_repo import CasesRepo
from management.cases.escalation_ack_repo import annotate_items
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.rbac import catalog
from management.rbac.rbac_repo import RbacRepo
from management.server.management_app import ManagementApp

_DAY = 86400

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


class EscalationAckTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        self.con = sqlite3.connect(self.db_path)
        self.con.isolation_level = None
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")

        self.NOW = int(time.time())
        self.con.execute(_PERSON)
        self.con.executemany(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(1, "h001", "Chefin, Alpha", 1, 1, 0, self.NOW),
             (2, "h002", "Beta", 1, 0, 0, self.NOW),
             (3, "h003", "Gamma", 1, 0, 0, self.NOW)],
        )
        self.con.execute(_OLD_SCRAPE_JOBS)

        self.audit = AuditLog(self.con)
        self.mods = discover(coordinator_migrations)
        self.applied = MigrationRunner(self.con, self.mods, audit=self.audit,
                                       deployed_by="tester").run()

        self.writer = CoordinatorWriter(self.con, self.audit)
        self.repo = RbacRepo(self.con, self.writer)
        # person 1: sehen UND quittieren.
        self.repo.grant("supervisor", "escalation.view", scope="alle",
                        actor_id=1)
        self.repo.grant("supervisor", "escalation.ack", scope="alle",
                        actor_id=1)
        self.repo.assign_role(1, "supervisor", actor_id=1)
        # person 2: NUR sehen — belegt AK02/AK12.
        self.repo.grant("investigator", "escalation.view", scope="alle",
                        actor_id=1)
        self.repo.assign_role(2, "investigator", actor_id=1)
        # person 3: gar nichts.

        self.cases = CasesRepo(self.con, self.writer)
        self._checkpoint()
        self.app = ManagementApp(self.db_path)

    def tearDown(self):
        try:
            self.con.close()
        finally:
            for fn in os.listdir(self._tmp):
                try:
                    os.remove(os.path.join(self._tmp, fn))
                except OSError:
                    pass
            os.rmdir(self._tmp)

    # ------------------------------------------------------------- Helfer
    def _checkpoint(self):
        self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def _json(self, resp):
        return json.loads(resp.body.decode("utf-8"))

    def _list(self, person_id=1):
        r = self.app.dispatch(person_id, "/api/escalations")
        self.assertEqual(r.status, 200)
        return self._json(r)

    def _post(self, path, body, person_id=1):
        return self.app.dispatch_write(person_id, path, body)

    def _age_case(self, subject_id, days):
        """Zeitreise wie in test_management_escalation_api.py (Testvorrichtung)."""
        ts = self.NOW - days * _DAY
        self.con.execute(
            "UPDATE cases SET created_at = ?, updated_at = ? "
            "WHERE subject_id = ?", (ts, ts, subject_id))
        self.con.execute(
            "UPDATE case_events SET created_at = ? WHERE subject_id = ?",
            (ts, subject_id))
        self._checkpoint()

    def _make_overdue_case(self, subject_id=7101, extra_days=5):
        """Einen sicher ueberfaelligen roten Fall herstellen."""
        grenze = self._list(1)["thresholds"]["red_overdue_days"]
        self.cases.create_case(subject_id, "alt_rot", actor_id=1)
        self.cases.assign(subject_id, 2, actor_id=1)
        self._age_case(subject_id, grenze + extra_days)
        return subject_id

    def _item_for(self, data, rule_code, subject_id):
        treffer = [i for i in data["items"]
                   if i["rule_code"] == rule_code
                   and i["subject_id"] == subject_id]
        self.assertEqual(len(treffer), 1,
                         "genau eine Meldung erwartet fuer %s/%s"
                         % (rule_code, subject_id))
        return treffer[0]

    def _ack_rows(self):
        return self.con.execute(
            "SELECT * FROM escalation_ack ORDER BY id").fetchall()

    # -------------------------------------------------------------- Tests
    # AK01 — Struktur + Idempotenz.
    def test_ak01_migration_und_idempotenz(self):
        self.assertIn(27, self.applied)
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='escalation_ack'").fetchone())
        for ix in ("ix_escalation_ack_key", "ix_escalation_ack_by"):
            self.assertIsNotNone(self.con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                (ix,)).fetchone(), "Index %s fehlt" % ix)
        self.assertIn("escalation.ack", catalog.CAPABILITY_CODES)
        self.assertIsNotNone(self.con.execute(
            "SELECT 1 FROM rbac_capability WHERE code='escalation.ack'"
        ).fetchone())
        # Zweiter Runner-Lauf: No-Op.
        second = MigrationRunner(self.con, self.mods, audit=self.audit,
                                 deployed_by="tester").run()
        self.assertEqual(second, [])

    # AK02 — Lesen ist nicht Schreiben.
    def test_ak02_lesen_ist_nicht_schreiben(self):
        sid = self._make_overdue_case()
        r = self._post("/api/escalations/ack",
                       {"rule_code": "fall_ueberfaellig", "subject_id": sid,
                        "reason": "gesehen"}, person_id=2)
        self.assertEqual(r.status, 403)
        self.assertEqual(self._json(r)["capability"], "escalation.ack")
        # person 2 darf die Sicht aber weiterhin LESEN.
        self.assertEqual(
            self.app.dispatch(2, "/api/escalations").status, 200)
        self.assertEqual(len(self._ack_rows()), 0)

    # AK03 — Begruendung ist Pflicht, und ein Fehlversuch hinterlaesst nichts.
    def test_ak03_begruendung_pflicht(self):
        sid = self._make_overdue_case()
        vorher = len(self._ack_rows())
        for leer in ("", "   ", None):
            r = self._post("/api/escalations/ack",
                           {"rule_code": "fall_ueberfaellig",
                            "subject_id": sid, "reason": leer})
            self.assertEqual(r.status, 400, "leerer Grund %r" % (leer,))
            self.assertIn("Begruendung", self._json(r)["detail"])
        self.assertEqual(len(self._ack_rows()), vorher)

    # AK04 — Write + Audit atomar, Kette intakt, KEIN Freitext im Payload.
    def test_ak04_write_und_audit(self):
        sid = self._make_overdue_case()
        geheim = "Rücksprache mit StA; Fall wird priorisiert (Пётр)"
        r = self._post("/api/escalations/ack",
                       {"rule_code": "fall_ueberfaellig", "subject_id": sid,
                        "reason": geheim, "days_inactive": 35})
        self.assertEqual(r.status, 200)
        res = self._json(r)
        self.assertTrue(res["ok"])
        self.assertGreater(res["audit_seq"], 0)

        rows = self._ack_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rule_code"], "fall_ueberfaellig")
        self.assertEqual(rows[0]["subject_id"], sid)
        self.assertEqual(rows[0]["reason"], geheim)
        self.assertEqual(rows[0]["days_inactive_at_ack"], 35)
        self.assertEqual(rows[0]["acknowledged_by"], 1)
        # Die Zeile traegt die seq IHRES Belegs (after_audit-Hook).
        self.assertEqual(rows[0]["audit_seq"], res["audit_seq"])

        beleg = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq = ?",
            (res["audit_seq"],)).fetchone()
        self.assertEqual(beleg["event_type"],
                         EventType.ESCALATION_ACKNOWLEDGED)
        payload = json.loads(beleg["content"])
        # SENSIBILITAET: Fakten ja, Freitext nein.
        self.assertEqual(payload["rule_code"], "fall_ueberfaellig")
        self.assertEqual(payload["subject_id"], sid)
        self.assertEqual(payload["reason_len"], len(geheim))
        self.assertNotIn(geheim, beleg["content"])
        self.assertNotIn("reason", [k for k in payload if k == "reason"])
        # Die Hash-Kette bleibt intakt.
        self.assertTrue(AuditLog(self.con).verify_chain().ok)

    # AK05 — DER KERNTEST: Quittieren ist KEIN Erledigen.
    def test_ak05_quittieren_blendet_nicht_aus(self):
        sid = self._make_overdue_case()
        vorher = self._list(1)
        self.assertIsNone(
            self._item_for(vorher, "fall_ueberfaellig", sid)["ack"])
        anzahl_vorher = len(vorher["items"])

        r = self._post("/api/escalations/ack",
                       {"rule_code": "fall_ueberfaellig", "subject_id": sid,
                        "reason": "gesehen, StA informiert"})
        self.assertEqual(r.status, 200)

        nachher = self._list(1)
        # Die Meldung ist NICHT verschwunden.
        self.assertEqual(len(nachher["items"]), anzahl_vorher)
        item = self._item_for(nachher, "fall_ueberfaellig", sid)
        self.assertIsNotNone(item["ack"])
        self.assertEqual(item["ack"]["reason"], "gesehen, StA informiert")
        self.assertEqual(item["ack"]["acknowledged_by"], 1)
        self.assertEqual(item["ack"]["acknowledged_by_name"], "Chefin, Alpha")
        # Und die Zaehler haben sich NICHT veraendert — eine Quittierung
        # aendert nichts am Befund.
        self.assertEqual(nachher["count_hoch"], vorher["count_hoch"])

    # AK06 — die systemische Regel ist quittierbar.
    def test_ak06_systemische_regel_quittierbar(self):
        grenze = self._list(1)["thresholds"]["backlog_high"]
        for n in range(grenze):
            self.cases.create_case(8100 + n, "offen_%d" % n, actor_id=1)
        self._checkpoint()
        self.assertEqual(
            len([i for i in self._list(1)["items"]
                 if i["rule_code"] == "rueckstau_hoch"]), 1)

        # subject_id wird BEWUSST weggelassen — 'kein Fall' ist hier gueltig.
        r = self._post("/api/escalations/ack",
                       {"rule_code": "rueckstau_hoch",
                        "reason": "Verteilrunde für Montag angesetzt"})
        self.assertEqual(r.status, 200)
        self.assertIsNone(self._json(r)["subject_id"])

        item = self._item_for(self._list(1), "rueckstau_hoch", None)
        self.assertIsNotNone(item["ack"])
        # 'nicht erhoben' bleibt None und wird nicht zu 0 verfaelscht.
        self.assertIsNone(item["ack"]["days_inactive_at_ack"])
        self.assertFalse(item["ack"]["outdated"])

    # AK07 — hoechstens EIN gueltiger Vermerk je Eskalation.
    def test_ak07_kein_zweiter_gueltiger_vermerk(self):
        sid = self._make_overdue_case()
        body = {"rule_code": "fall_ueberfaellig", "subject_id": sid,
                "reason": "erster Vermerk"}
        self.assertEqual(self._post("/api/escalations/ack", body).status, 200)
        r = self._post("/api/escalations/ack",
                       dict(body, reason="zweiter Vermerk"))
        self.assertEqual(r.status, 400)
        self.assertIn("bereits ein gueltiger Vermerk",
                      self._json(r)["detail"])
        self.assertEqual(len(self._ack_rows()), 1)

    # AK08 — Widerruf: Grund Pflicht, Zeile bleibt, danach erneut quittierbar.
    def test_ak08_widerruf(self):
        sid = self._make_overdue_case()
        erst = self._json(self._post(
            "/api/escalations/ack",
            {"rule_code": "fall_ueberfaellig", "subject_id": sid,
             "reason": "erster Vermerk"}))
        aid = erst["ack_id"]

        r = self._post("/api/escalations/ack/revoke",
                       {"ack_id": aid, "reason": "  "})
        self.assertEqual(r.status, 400)
        self.assertIn("Grund ist Pflicht", self._json(r)["detail"])

        r = self._post("/api/escalations/ack/revoke",
                       {"ack_id": aid, "reason": "Verwechslung mit Fall 7102"})
        self.assertEqual(r.status, 200)
        seq = self._json(r)["audit_seq"]

        # WIDERRUF STATT LOESCHUNG: die Zeile ist noch da.
        rows = self._ack_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["is_active"], 0)
        self.assertEqual(rows[0]["revoked_by"], 1)
        self.assertEqual(rows[0]["revoke_reason"], "Verwechslung mit Fall 7102")
        self.assertEqual(rows[0]["revoke_audit_seq"], seq)
        # Der urspruengliche Vermerk ist unangetastet erhalten.
        self.assertEqual(rows[0]["reason"], "erster Vermerk")
        # Eigener Ereignistyp.
        self.assertEqual(self.con.execute(
            "SELECT event_type FROM audit_log WHERE seq = ?",
            (seq,)).fetchone()["event_type"],
            EventType.ESCALATION_ACK_REVOKED)

        # Die Meldung traegt jetzt wieder KEINEN Vermerk ...
        self.assertIsNone(
            self._item_for(self._list(1), "fall_ueberfaellig", sid)["ack"])
        # ... und darf erneut quittiert werden.
        self.assertEqual(self._post(
            "/api/escalations/ack",
            {"rule_code": "fall_ueberfaellig", "subject_id": sid,
             "reason": "neuer Vermerk"}).status, 200)
        self.assertEqual(len(self._ack_rows()), 2)

    # AK09 — kein zweiter Widerruf.
    def test_ak09_doppelter_widerruf(self):
        sid = self._make_overdue_case()
        aid = self._json(self._post(
            "/api/escalations/ack",
            {"rule_code": "fall_ueberfaellig", "subject_id": sid,
             "reason": "Vermerk"}))["ack_id"]
        self.assertEqual(self._post(
            "/api/escalations/ack/revoke",
            {"ack_id": aid, "reason": "Grund"}).status, 200)
        r = self._post("/api/escalations/ack/revoke",
                       {"ack_id": aid, "reason": "nochmal"})
        self.assertEqual(r.status, 400)
        self.assertIn("bereits widerrufen", self._json(r)["detail"])
        # Unbekannter Vermerk ebenfalls 400 (handlungsleitend, nicht 500).
        r = self._post("/api/escalations/ack/revoke",
                       {"ack_id": 99999, "reason": "Grund"})
        self.assertEqual(r.status, 400)

    # AK10 — 'outdated' ist eine Tatsache, keine neue Schwelle.
    def test_ak10_outdated(self):
        sid = self._make_overdue_case(extra_days=5)
        aktuell = self._item_for(self._list(1), "fall_ueberfaellig",
                                 sid)["days_inactive"]
        # Mit dem TATSAECHLICHEN Stand quittieren -> nicht ueberholt.
        self._post("/api/escalations/ack",
                   {"rule_code": "fall_ueberfaellig", "subject_id": sid,
                    "reason": "gesehen", "days_inactive": aktuell})
        self.assertFalse(
            self._item_for(self._list(1), "fall_ueberfaellig",
                           sid)["ack"]["outdated"])

        # Der Fall altert weiter -> der Vermerk ist ueberholt.
        self.con.execute(
            "UPDATE escalation_ack SET days_inactive_at_ack = ? WHERE id = 1",
            (aktuell - 3,))
        self._checkpoint()
        item = self._item_for(self._list(1), "fall_ueberfaellig", sid)
        self.assertTrue(item["ack"]["outdated"])
        self.assertEqual(item["ack"]["days_inactive_at_ack"], aktuell - 3)

    # AK11 — annotate_items ist rein und laesst die Liste unangetastet.
    def test_ak11_annotate_items_rein(self):
        items = [
            {"rule_code": "a", "subject_id": 1, "days_inactive": 10},
            {"rule_code": "b", "subject_id": None, "days_inactive": None},
            {"rule_code": "a", "subject_id": 2, "days_inactive": None},
        ]
        original = json.dumps(items, sort_keys=True)
        acks = [
            {"ack_id": 1, "rule_code": "a", "subject_id": 1,
             "reason": "r", "acknowledged_by": 7, "acknowledged_at": 5,
             "days_inactive_at_ack": 4, "audit_seq": 9},
            {"ack_id": 2, "rule_code": "b", "subject_id": None,
             "reason": "s", "acknowledged_by": 7, "acknowledged_at": 6,
             "days_inactive_at_ack": None, "audit_seq": 10},
        ]
        out = annotate_items(items, acks, {7: "Chefin"})
        # Reihenfolge und Anzahl unveraendert.
        self.assertEqual(len(out), 3)
        self.assertEqual([(o["rule_code"], o["subject_id"]) for o in out],
                         [("a", 1), ("b", None), ("a", 2)])
        # Die Eingabe wurde NICHT veraendert (reine Funktion).
        self.assertEqual(json.dumps(items, sort_keys=True), original)
        self.assertTrue(out[0]["ack"]["outdated"])       # 10 > 4
        self.assertEqual(out[0]["ack"]["acknowledged_by_name"], "Chefin")
        self.assertFalse(out[1]["ack"]["outdated"])      # nicht vergleichbar
        self.assertIsNone(out[2]["ack"])                 # kein Vermerk

    # AK12 — 'acknowledgeable' spiegelt Recht UND Struktur.
    def test_ak12_acknowledgeable(self):
        self.assertTrue(self._list(1)["acknowledgeable"])
        self.assertTrue(self._list(1)["ack_migrated"])
        # person 2 sieht die Sicht, darf aber nicht quittieren.
        d2 = self._list(2)
        self.assertFalse(d2["acknowledgeable"])
        self.assertTrue(d2["ack_migrated"],
                        "die Struktur ist da — nur das Recht fehlt; das darf "
                        "die Sicht nicht verwechseln")


if __name__ == "__main__":
    unittest.main()
