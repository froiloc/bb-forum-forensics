# =============================================================================
# tests/test_crossfinding_channel_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Testsuite fuer Build 507: CrossfindingChannelRepo (Querfund-Rueckkanal, M024).
#
# CF01 — erste Entscheidung legt an (created=True, audit_seq>0); status_of()
#        liefert vorher 'offen' (Pseudo-Zustand ohne Zeile).
# CF02 — Folgeentscheidung aktualisiert dieselbe Zeile (created=False,
#        audit_seq steigt, UNIQUE(finding_id) haelt).
# CF03 — unzulaessiger Uebergang wirft UND schreibt NICHTS (Rollback-Beleg:
#        weder Zeile noch audit_log-Eintrag bleiben zurueck).
# CF04 — Pflichttext: 'verwertet'/'nicht_relevant' ohne Angabe -> Fehler,
#        nichts geschrieben.
# CF05 — unbekannter finding_id -> CrossrefError (Existenzpruefung statt FK).
# CF06 — list_with_status(): Funde OHNE Feedback erscheinen als 'offen' und
#        stehen OBEN; allowed_next kommt vom Server mit.
# CF07 — Filter: only_open (Transport) und only_unacknowledged (Rueckkanal)
#        wirken unabhaengig voneinander; counts() zaehlt inkl. 'offen'.
# CF08 — SENSIBILITAET: der Freitext (Grund/Basis) steht nicht im audit_log,
#        die Textlaenge und die Fakten schon.
# CF09 — Reihenfolge-Vertraeglichkeit zu Build 474: solange KEIN Rueckkanal
#        benutzt wird, ist die Zeilenfolge identisch zu CrossfindingsRepo.
#
# Version: v0.8.507 · Build: 507 · 2026-07-24
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
from management.crossref.crossfinding_channel_repo import (
    CrossfindingChannelRepo,
)
from management.crossref.crossfinding_channel_status import (
    CrossfindingChannelError,
)
from management.crossref.crossfindings_repo import CrossfindingsRepo
from management.crossref.identified_subject_repo import CrossrefError
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover

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

_GEHEIM = "Eingeflossen in Vermerk 7, Bl. 214 — Zeuge M."


class CrossfindingChannelRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        now = int(time.time())
        con.execute(_PERSON)
        con.executemany(
            "INSERT INTO person (id, system_username, display_name, created_at)"
            " VALUES (?, ?, ?, ?)",
            [(1, "h001", "Ermittler Eins", now),
             (2, "h002", "Ermittler Zwei", now)])
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.now = now
        self.repo = CrossfindingChannelRepo(
            con, CoordinatorWriter(con, AuditLog(con)))
        self.ro = CrossfindingChannelRepo(con)

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

    # ------------------------------------------------------------------ Hilfen
    def _add_finding(self, subject_id, source_iid=1, local_id="a1",
                     created_delta=-100, integrated=None):
        cur = self.con.execute(
            "INSERT INTO pending_cross_annotations "
            "(source_iid, target_uid, db_path, annotation_local_id, "
            " created_at, integrated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (source_iid, subject_id, "/x/evidence_%d.db" % subject_id,
             local_id, self.now + created_delta, integrated))
        return int(cur.lastrowid)

    def _audit_count(self):
        return int(self.con.execute(
            "SELECT COUNT(*) FROM audit_log").fetchone()[0])

    def _raw_audit(self):
        rows = self.con.execute(
            "SELECT event_type, content, meta FROM audit_log").fetchall()
        return "\n".join("%s %s %s" % (r["event_type"], r["content"], r["meta"])
                         for r in rows)

    # CF01 -------------------------------------------------------------------
    def test_cf01_erste_entscheidung(self):
        fid = self._add_finding(4711)
        # Ohne Zeile ist der Zustand der Pseudo-Zustand 'offen'.
        self.assertEqual(self.ro.status_of(fid), "offen")

        res = self.repo.decide(finding_id=fid, target_status="quittiert",
                               actor_id=2)
        self.assertTrue(res["created"])
        self.assertGreater(res["audit_seq"], 0)
        self.assertEqual(res["subject_id"], 4711)
        self.assertEqual(self.ro.status_of(fid), "quittiert")

        row = self.con.execute(
            "SELECT * FROM crossfinding_feedback WHERE finding_id=?",
            (fid,)).fetchone()
        self.assertEqual(row["subject_id"], 4711)
        self.assertEqual(row["decided_by"], 2)
        # audit_seq-Backfill in beiden Feldern.
        self.assertEqual(row["audit_seq"], res["audit_seq"])
        self.assertEqual(row["created_audit_seq"], res["audit_seq"])

    # CF02 -------------------------------------------------------------------
    def test_cf02_folgeentscheidung(self):
        fid = self._add_finding(4711)
        seq1 = self.repo.decide(finding_id=fid, target_status="zugestellt",
                                actor_id=1)["audit_seq"]
        res2 = self.repo.decide(finding_id=fid, target_status="quittiert",
                                actor_id=2)
        self.assertFalse(res2["created"])
        self.assertGreater(res2["audit_seq"], seq1)
        # UNIQUE(finding_id): es bleibt bei EINER Zeile (Ist-Stand).
        self.assertEqual(int(self.con.execute(
            "SELECT COUNT(*) FROM crossfinding_feedback WHERE finding_id=?",
            (fid,)).fetchone()[0]), 1)
        self.assertEqual(self.ro.status_of(fid), "quittiert")

        res3 = self.repo.decide(finding_id=fid, target_status="verwertet",
                                reason=_GEHEIM, actor_id=2)
        self.assertEqual(self.ro.status_of(fid), "verwertet")
        self.assertGreater(res3["audit_seq"], res2["audit_seq"])

    # CF03 -------------------------------------------------------------------
    def test_cf03_unzulaessiger_uebergang_schreibt_nichts(self):
        fid = self._add_finding(4711)
        self.repo.decide(finding_id=fid, target_status="verwertet",
                         reason="Basis", actor_id=1)
        vor_audit = self._audit_count()
        vor_row = dict(self.con.execute(
            "SELECT * FROM crossfinding_feedback WHERE finding_id=?",
            (fid,)).fetchone())

        # 'verwertet' ist endgueltig.
        with self.assertRaises(CrossfindingChannelError):
            self.repo.decide(finding_id=fid, target_status="quittiert",
                             actor_id=1)

        # NICHTS ist zurueckgeblieben — weder Beleg noch Datenaenderung.
        self.assertEqual(self._audit_count(), vor_audit)
        nach_row = dict(self.con.execute(
            "SELECT * FROM crossfinding_feedback WHERE finding_id=?",
            (fid,)).fetchone())
        self.assertEqual(vor_row, nach_row)

    # CF04 -------------------------------------------------------------------
    def test_cf04_pflichttext(self):
        fid = self._add_finding(4711)
        vor = self._audit_count()
        for target in ("verwertet", "nicht_relevant"):
            with self.assertRaises(CrossfindingChannelError):
                self.repo.decide(finding_id=fid, target_status=target,
                                 reason="   ", actor_id=1)
        self.assertEqual(self._audit_count(), vor)
        self.assertEqual(self.ro.status_of(fid), "offen")

        # Mit Angabe klappt es.
        self.repo.decide(finding_id=fid, target_status="nicht_relevant",
                         reason="Betrifft ein Namensdoppel", actor_id=1)
        self.assertEqual(self.ro.status_of(fid), "nicht_relevant")

    # CF05 -------------------------------------------------------------------
    def test_cf05_unbekannter_fund(self):
        with self.assertRaises(CrossrefError) as cm:
            self.repo.decide(finding_id=999999, target_status="quittiert",
                             actor_id=1)
        self.assertIn("Unbekannter Querfund", str(cm.exception))
        self.assertEqual(int(self.con.execute(
            "SELECT COUNT(*) FROM crossfinding_feedback").fetchone()[0]), 0)

    # CF06 -------------------------------------------------------------------
    def test_cf06_list_with_status(self):
        f_alt = self._add_finding(700, local_id="a1", created_delta=-300)
        f_neu = self._add_finding(701, local_id="a2", created_delta=-10)
        self.repo.decide(finding_id=f_neu, target_status="verwertet",
                         reason="Basis", actor_id=2)

        rows = self.ro.list_with_status()
        self.assertEqual(len(rows), 2)
        # Handlungsbeduerftiges (offen) steht OBEN, obwohl es aelter ist.
        self.assertEqual(rows[0]["id"], f_alt)
        self.assertEqual(rows[0]["feedback_status"], "offen")
        self.assertFalse(rows[0]["feedback_final"])
        self.assertIsNone(rows[0]["decided_at"])
        self.assertEqual(rows[1]["id"], f_neu)
        self.assertEqual(rows[1]["feedback_status"], "verwertet")
        self.assertTrue(rows[1]["feedback_final"])
        self.assertEqual(rows[1]["decided_name"], "Ermittler Zwei")

        # Der SERVER liefert die zulaessigen Folgezustaende mit — die
        # Oberflaeche soll keine Uebergaenge erfinden koennen.
        offen_next = [n["code"] for n in rows[0]["allowed_next"]]
        self.assertEqual(sorted(offen_next),
                         sorted(["zugestellt", "quittiert", "verwertet",
                                 "nicht_relevant"]))
        self.assertEqual(rows[1]["allowed_next"], [])   # endgueltig
        # Pflichttext-Bedarf steht dabei.
        verwertet = [n for n in rows[0]["allowed_next"]
                     if n["code"] == "verwertet"][0]
        self.assertTrue(verwertet["reason_required"])
        self.assertIn("Basis", verwertet["reason_meaning"])

        self.assertEqual(
            [n["code"] for n in self.ro.allowed_next_for(f_neu)], [])

    # CF07 -------------------------------------------------------------------
    def test_cf07_filter_und_counts(self):
        f1 = self._add_finding(700, local_id="a1", created_delta=-300)
        f2 = self._add_finding(701, local_id="a2", created_delta=-200,
                               integrated=self.now)
        f3 = self._add_finding(702, local_id="a3", created_delta=-100,
                               integrated=self.now)
        self.repo.decide(finding_id=f3, target_status="quittiert", actor_id=1)

        # TRANSPORT-Filter: nur nicht integrierte.
        self.assertEqual([r["id"] for r in
                          self.ro.list_with_status(only_open=True)], [f1])
        # RUECKKANAL-Filter: 'offen' und 'zugestellt' — f3 (quittiert) faellt raus.
        unack = [r["id"] for r in
                 self.ro.list_with_status(only_unacknowledged=True)]
        self.assertEqual(sorted(unack), sorted([f1, f2]))
        # Beide zusammen wirken unabhaengig (Schnittmenge).
        beides = [r["id"] for r in self.ro.list_with_status(
            only_open=True, only_unacknowledged=True)]
        self.assertEqual(beides, [f1])

        c = self.ro.counts()
        self.assertEqual(c["gesamt"], 3)
        self.assertEqual(c["offen"], 2)
        self.assertEqual(c["quittiert"], 1)
        self.assertEqual(c["verwertet"], 0)
        # Jeder Zustand ist als Schluessel da (nie ein fehlender Zaehler).
        for key in ("offen", "zugestellt", "quittiert", "verwertet",
                    "nicht_relevant"):
            self.assertIn(key, c)

    # CF08 -------------------------------------------------------------------
    def test_cf08_sensibilitaet(self):
        fid = self._add_finding(4711)
        self.repo.decide(finding_id=fid, target_status="verwertet",
                         reason=_GEHEIM, actor_id=1)

        raw = self._raw_audit()
        self.assertNotIn(_GEHEIM, raw,
                         "Sensibler Klartext steht im audit_log!")
        self.assertNotIn("Vermerk 7", raw)
        self.assertIn("crossfinding_feedback_set", raw)

        row = self.con.execute(
            "SELECT content FROM audit_log "
            "WHERE event_type='crossfinding_feedback_set'").fetchone()
        payload = json.loads(row["content"])
        self.assertEqual(payload["finding_id"], fid)
        self.assertEqual(payload["subject_id"], 4711)
        self.assertEqual(payload["von"], "offen")
        self.assertEqual(payload["nach"], "verwertet")
        self.assertEqual(payload["reason_len"], len(_GEHEIM))

    # CF09 -------------------------------------------------------------------
    def test_cf09_reihenfolge_vertraeglich_zu_build474(self):
        """
        Solange der Rueckkanal NICHT benutzt wird (alle Raenge gleich), muss die
        Zeilenfolge exakt der aus Build 474 entsprechen — sonst waere die Sicht
        aus Build 478 still umsortiert worden.
        """
        self._add_finding(700, local_id="a1", created_delta=-100)
        self._add_finding(701, local_id="a2", created_delta=-10)
        self._add_finding(702, local_id="a3", created_delta=-5,
                          integrated=self.now)

        alt = [r["id"] for r in CrossfindingsRepo(self.con).list()]
        neu = [r["id"] for r in self.ro.list_with_status()]
        self.assertEqual(alt, neu)

        # Erst eine Rueckkanal-Entscheidung darf die Folge aendern — und dann
        # bewusst: das Erledigte wandert nach unten.
        self.repo.decide(finding_id=alt[0], target_status="verwertet",
                         reason="Basis", actor_id=1)
        danach = [r["id"] for r in self.ro.list_with_status()]
        self.assertEqual(danach[-1], alt[0])

    # Schutzregel ------------------------------------------------------------
    def test_cf10_kein_unauditierter_schreibpfad(self):
        fid = self._add_finding(4711)
        with self.assertRaises(CrossrefError):
            self.ro.decide(finding_id=fid, target_status="quittiert")


if __name__ == "__main__":
    unittest.main()
