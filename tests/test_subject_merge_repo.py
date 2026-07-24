# =============================================================================
# tests/test_subject_merge_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Testsuite fuer Build 509: SubjectMergeRepo (Identitaets-Merge/Split, M025).
#
# MG01 — merge() legt an und ist lesbar; audit_seq-Backfill in beiden Feldern.
# MG02 — Selbstverschmelzung: Repo wirft fachlich UND die DDL-CHECK haelt.
# MG03 — Doppelzuordnung desselben Kontos -> Fehler MIT Nennung des bisherigen
#        Primaerkontos (die Ermittlerin soll den Konflikt sehen).
# MG04 — KETTE verboten, Richtung A: das einzugliedernde Konto ist selbst
#        Primaer.
# MG05 — KETTE verboten, Richtung B: das Primaerkonto ist selbst eingegliedert.
# MG06 — group_of() liefert von JEDEM beteiligten Konto aus dieselbe Gruppe;
#        ein unbeteiligtes Konto ist seine eigene Gruppe (kein Leerbefund).
# MG07 — revise(): Konfidenz reift, audit_seq steigt; No-Op wirft; Basis darf
#        nicht geleert werden.
# MG08 — split() ist SOFT (Zeile bleibt, Grund + Zeitpunkt gespeichert).
# MG09 — split() ohne Grund -> Fehler, nichts geaendert.
# MG10 — nach split() ist eine NEUE Zuordnung desselben Kontos erlaubt.
# MG11 — remerge() prueft erneut auf Kollision und wird dann abgelehnt;
#        ohne Kollision klappt es.
# MG12 — SENSIBILITAET: basis/split_reason stehen nicht im audit_log.
# MG13 — counts(); kein unauditierter Schreibpfad.
#
# Version: v0.8.509 · Build: 509 · 2026-07-24
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
from management.crossref.identified_subject_repo import CrossrefError
from management.crossref.subject_merge_repo import SubjectMergeRepo
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

_GEHEIM_BASIS = "Gleiche IP 203.0.113.9 in 14 Sitzungen, Bestandsauskunft 12.03."
_GEHEIM_GRUND = "Bestandsauskunft betraf den Anschlussinhaber, nicht den Nutzer"


class SubjectMergeRepoTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._db = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self._db)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        now = int(time.time())
        con.execute(_PERSON)
        con.execute(
            "INSERT INTO person (id, system_username, display_name, created_at)"
            " VALUES (1, 'h001', 'Ermittler Eins', ?)", (now,))
        con.execute(_OLD_SCRAPE_JOBS)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="tester").run()
        self.con = con
        self.now = now
        self.repo = SubjectMergeRepo(con, CoordinatorWriter(con, AuditLog(con)))
        self.ro = SubjectMergeRepo(con)

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

    def _merge(self, primary, merged, conf="verdacht", basis="Indizien"):
        return self.repo.merge(primary_subject_id=primary,
                               merged_subject_id=merged, basis=basis,
                               confidence_code=conf, actor_id=1)

    def _raw_audit(self):
        rows = self.con.execute(
            "SELECT event_type, content, meta FROM audit_log").fetchall()
        return "\n".join("%s %s %s" % (r["event_type"], r["content"], r["meta"])
                         for r in rows)

    # MG01 -------------------------------------------------------------------
    def test_mg01_merge_und_list(self):
        res = self._merge(4711, 90210, conf="wahrscheinlich",
                          basis="Schreibstil + Zeitmuster")
        self.assertGreater(res["merge_id"], 0)
        self.assertGreater(res["audit_seq"], 0)

        rows = self.ro.list()
        self.assertEqual(len(rows), 1)
        e = rows[0]
        self.assertEqual(e["primary_subject_id"], 4711)
        self.assertEqual(e["merged_subject_id"], 90210)
        self.assertEqual(e["confidence_code"], "wahrscheinlich")
        self.assertEqual(e["confidence_ordinal"], 20)
        self.assertTrue(e["is_active"])
        self.assertIsNone(e["split_reason"])
        self.assertEqual(e["audit_seq"], res["audit_seq"])
        self.assertEqual(e["created_audit_seq"], res["audit_seq"])

    # MG02 -------------------------------------------------------------------
    def test_mg02_selbstverschmelzung(self):
        with self.assertRaises(CrossrefError) as cm:
            self._merge(4711, 4711)
        self.assertIn("mit sich selbst", str(cm.exception))
        # Und die DDL-CHECK haelt auch am Repo vorbei.
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO subject_merge (primary_subject_id, "
                "merged_subject_id, basis, confidence_code, "
                "confidence_ordinal, created_at, updated_at, audit_seq, "
                "created_audit_seq) VALUES (5, 5, 'x', 'verdacht', 10, 1, 1, "
                "1, 1)")

    # MG03 -------------------------------------------------------------------
    def test_mg03_doppelzuordnung(self):
        self._merge(4711, 90210)
        with self.assertRaises(CrossrefError) as cm:
            self._merge(1234, 90210)
        msg = str(cm.exception)
        # Der Konflikt wird BENANNT — inkl. des bisherigen Primaerkontos.
        self.assertIn("90210", msg)
        self.assertIn("4711", msg)
        self.assertIn("Erst trennen", msg)

    # MG04 -------------------------------------------------------------------
    def test_mg04_kette_verboten_richtung_a(self):
        """B ist Primaer fuer C; jetzt soll B unter A — das waere eine Kette."""
        self._merge(90210, 555)          # 90210 <- 555
        with self.assertRaises(CrossrefError) as cm:
            self._merge(4711, 90210)     # 4711 <- 90210  == Kette
        msg = str(cm.exception)
        self.assertIn("selbst Primaerkonto", msg)
        self.assertIn("Ketten sind nicht vorgesehen", msg)
        self.assertIn("4711", msg)       # der konstruktive Hinweis

    # MG05 -------------------------------------------------------------------
    def test_mg05_kette_verboten_richtung_b(self):
        """B haengt unter A; jetzt soll C unter B — ebenfalls eine Kette."""
        self._merge(4711, 90210)         # 4711 <- 90210
        with self.assertRaises(CrossrefError) as cm:
            self._merge(90210, 555)      # 90210 <- 555   == Kette
        msg = str(cm.exception)
        self.assertIn("selbst dem Primaerkonto", msg)
        self.assertIn("4711", msg)

        # Der konstruktive Weg funktioniert: direkt an 4711 haengen.
        self._merge(4711, 555)
        self.assertEqual(len(self.ro.list()), 2)

    # MG06 -------------------------------------------------------------------
    def test_mg06_group_of(self):
        self._merge(4711, 90210)
        self._merge(4711, 555)

        vom_primary = self.ro.group_of(4711)
        vom_merged = self.ro.group_of(90210)
        vom_anderen = self.ro.group_of(555)

        # Von JEDEM beteiligten Konto aus dieselbe Gruppe.
        for g in (vom_primary, vom_merged, vom_anderen):
            self.assertEqual(g["primary_subject_id"], 4711)
            self.assertEqual(sorted(g["members"]), [555, 4711, 90210])
            self.assertEqual(len(g["merges"]), 2)
        self.assertTrue(vom_primary["is_primary"])
        self.assertFalse(vom_merged["is_primary"])
        self.assertEqual(vom_merged["queried_subject_id"], 90210)

        # Ein unbeteiligtes Konto ist seine EIGENE Gruppe — kein Leerbefund.
        allein = self.ro.group_of(999)
        self.assertEqual(allein["primary_subject_id"], 999)
        self.assertEqual(allein["members"], [999])
        self.assertEqual(allein["merges"], [])
        self.assertTrue(allein["is_primary"])

    # MG07 -------------------------------------------------------------------
    def test_mg07_revise(self):
        mid = self._merge(4711, 90210, conf="verdacht")["merge_id"]
        r = self.repo.revise(merge_id=mid, confidence_code="gesichert",
                             actor_id=1)
        self.assertGreater(r["audit_seq"], 0)
        e = self.ro.list()[0]
        self.assertEqual(e["confidence_code"], "gesichert")
        self.assertEqual(e["confidence_ordinal"], 30)

        # No-Op wirft und erzeugt keinen irrefuehrenden Beleg.
        with self.assertRaises(CrossrefError):
            self.repo.revise(merge_id=mid, confidence_code="gesichert",
                             actor_id=1)
        # Basis darf nicht geleert werden — die Hypothese braucht ihre Indizien.
        with self.assertRaises(CrossrefError):
            self.repo.revise(merge_id=mid, basis="   ", actor_id=1)
        # Ungueltige Stufe wird frueh abgefangen.
        with self.assertRaises(CrossrefError):
            self.repo.revise(merge_id=mid, confidence_code="quatsch",
                             actor_id=1)

    # MG08 -------------------------------------------------------------------
    def test_mg08_split_ist_soft(self):
        mid = self._merge(4711, 90210)["merge_id"]
        self.repo.split(merge_id=mid, reason=_GEHEIM_GRUND, actor_id=1)

        self.assertEqual(self.ro.list(), [])
        alle = self.ro.list(include_split=True)
        self.assertEqual(len(alle), 1)
        self.assertFalse(alle[0]["is_active"])
        self.assertEqual(alle[0]["split_reason"], _GEHEIM_GRUND)
        self.assertIsNotNone(alle[0]["split_at"])
        self.assertEqual(alle[0]["split_by"], 1)
        # NIE geloescht:
        self.assertEqual(int(self.con.execute(
            "SELECT COUNT(*) FROM subject_merge").fetchone()[0]), 1)
        # Und die Gruppe ist wieder aufgeloest.
        self.assertEqual(self.ro.group_of(90210)["members"], [90210])

    # MG09 -------------------------------------------------------------------
    def test_mg09_split_ohne_grund(self):
        mid = self._merge(4711, 90210)["merge_id"]
        for leer in ("", "   ", None):
            with self.assertRaises(CrossrefError):
                self.repo.split(merge_id=mid, reason=leer, actor_id=1)
        self.assertTrue(self.ro.list()[0]["is_active"])

    # MG10 -------------------------------------------------------------------
    def test_mg10_neuzuordnung_nach_split(self):
        mid = self._merge(4711, 90210)["merge_id"]
        self.repo.split(merge_id=mid, reason="Irrtum", actor_id=1)
        # Der partielle UNIQUE-Index laesst die Neuzuordnung zu.
        neu = self._merge(1234, 90210, conf="wahrscheinlich")
        self.assertNotEqual(neu["merge_id"], mid)
        aktiv = self.ro.list()
        self.assertEqual(len(aktiv), 1)
        self.assertEqual(aktiv[0]["primary_subject_id"], 1234)
        self.assertEqual(len(self.ro.list(include_split=True)), 2)

    # MG11 -------------------------------------------------------------------
    def test_mg11_remerge(self):
        mid = self._merge(4711, 90210)["merge_id"]
        self.repo.split(merge_id=mid, reason="Zweifel", actor_id=1)
        self._merge(1234, 90210)         # inzwischen anders zugeordnet

        with self.assertRaises(CrossrefError) as cm:
            self.repo.remerge(merge_id=mid, actor_id=1)
        self.assertIn("1234", str(cm.exception))

        # Ohne Kollision klappt die Ruecknahme.
        mid2 = self._merge(7000, 8000)["merge_id"]
        self.repo.split(merge_id=mid2, reason="Irrtum", actor_id=1)
        self.repo.remerge(merge_id=mid2, actor_id=1)
        wieder = [e for e in self.ro.list() if e["id"] == mid2]
        self.assertEqual(len(wieder), 1)
        self.assertIsNone(wieder[0]["split_reason"])
        self.assertIsNone(wieder[0]["split_at"])
        # Doppelte Ruecknahme wirft.
        with self.assertRaises(CrossrefError):
            self.repo.remerge(merge_id=mid2, actor_id=1)

    # MG12 -------------------------------------------------------------------
    def test_mg12_sensibilitaet(self):
        mid = self._merge(4711, 90210, basis=_GEHEIM_BASIS)["merge_id"]
        self.repo.revise(merge_id=mid, confidence_code="gesichert", actor_id=1)
        self.repo.split(merge_id=mid, reason=_GEHEIM_GRUND, actor_id=1)
        self.repo.remerge(merge_id=mid, actor_id=1)

        raw = self._raw_audit()
        for geheim in (_GEHEIM_BASIS, _GEHEIM_GRUND, "203.0.113.9",
                       "Anschlussinhaber"):
            self.assertNotIn(geheim, raw,
                             "Sensibler Klartext %r steht im audit_log!"
                             % geheim)
        for typ in ("subject_merged", "subject_merge_revised",
                    "subject_split", "subject_remerged"):
            self.assertIn(typ, raw, typ)

        row = self.con.execute(
            "SELECT content FROM audit_log "
            "WHERE event_type='subject_merged'").fetchone()
        payload = json.loads(row["content"])
        self.assertEqual(payload["primary_subject_id"], 4711)
        self.assertEqual(payload["merged_subject_id"], 90210)
        self.assertEqual(payload["confidence_ordinal"], 10)
        self.assertEqual(payload["basis_len"], len(_GEHEIM_BASIS))

    # MG13 -------------------------------------------------------------------
    def test_mg13_counts_und_schutzregeln(self):
        m1 = self._merge(4711, 90210)["merge_id"]
        self._merge(4711, 555)
        self._merge(7000, 8000)
        self.repo.split(merge_id=m1, reason="Irrtum", actor_id=1)

        c = self.ro.counts()
        self.assertEqual(c["total"], 3)
        self.assertEqual(c["aktiv"], 2)
        self.assertEqual(c["getrennt"], 1)
        # Betroffene Konten (aktiv): 4711, 555, 7000, 8000
        self.assertEqual(c["konten"], 4)

        # Basis ist Pflicht.
        with self.assertRaises(CrossrefError):
            self.repo.merge(primary_subject_id=1, merged_subject_id=2,
                            basis="   ", confidence_code="verdacht",
                            actor_id=1)
        # Ungueltige Konfidenz.
        with self.assertRaises(CrossrefError):
            self.repo.merge(primary_subject_id=1, merged_subject_id=2,
                            basis="x", confidence_code="quatsch", actor_id=1)
        # Kein unauditierter Schreibpfad.
        with self.assertRaises(CrossrefError):
            self.ro.merge(primary_subject_id=1, merged_subject_id=2,
                          basis="x", confidence_code="verdacht")
        # Unbekannte Zusammenfuehrung.
        with self.assertRaises(CrossrefError):
            self.repo.split(merge_id=99999, reason="x", actor_id=1)


if __name__ == "__main__":
    unittest.main()
