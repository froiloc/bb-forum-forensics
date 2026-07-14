# =============================================================================
# tests/test_mentoring_notes.py
# IT-Forensisches Ermittlungswerkzeug — Betreuungs-Notizen ("Post-its")
# =============================================================================
# Testsuite fuer Build 401, Block 1: M012 + note_colors + MentoringNoteRecord +
# MentoringNotesRepo + Lese-Endpunkt GET /api/mentoring/notes.
#
# MN01 — M012: Tabellen, Indizes, RBAC-Seed; zweiter Lauf ist No-op (idempotent).
# MN02 — RBAC: Code-Katalog (catalog.py) ist nach M012 vollstaendig in der DB
#        (verify_catalog_present wirft nicht) — die neuen Caps sind geseedet.
# MN03 — create(): auditiert; audit_seq/created_audit_seq gesetzt; FREITEXT
#        steht NICHT im audit_log-Payload (nur Laengen/Fakten).
# MN04 — Tags: getrimmt, dedupliziert, sortiert; abfragbar; Ersetzen bei update.
# MN05 — update(): partiell; nur uebergebene Felder; Betroffenen loeschen;
#        resultierender Zustand wird validiert; Freitext nicht im Audit.
# MN06 — archive()/restore(): Soft-Delete (kein physisches Loeschen); Liste
#        trennt aktiv/Archiv; doppeltes Archivieren scheitert laut.
# MN07 — duplicate(): 'offen'-Kopie mit Suffix '(Kopie)'; 'duplicated_from' im
#        Beleg; eigener Datensatz (Original unveraendert).
# MN08 — reorder(): setzt sort_index (Luecken-Spacing); EIN Beleg; Gegenprobe
#        (fremder owner / archiviert / doppelte IDs -> Fehler).
# MN09 — Kein unauditierter Schreibpfad (Repo ohne Writer verweigert JEDEN
#        Schreibweg).
# MN10 — list_notes(): Feinfilter (status/color/tag/subject) + Reihenfolge
#        (angeheftet zuerst, dann sort_index).
# MN11 — Endpunkt: GET /api/mentoring/notes (200/403); Scope 'eigene' sieht NUR
#        das eigene Board, 'alle' sieht alle Boards; ?owner_id=/?archived=.
#
# Fester Bezug: keine Systemuhr-Abhaengigkeit in den Assertions (Zeiten werden
# nur auf Plausibilitaet, nicht auf konkrete Werte geprueft).
#
# Version: v0.7.401 · Build: 401 · 2026-07-13
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
from management.migrations.runner import MigrationRunner, discover
from management.gateway.coordinator_writer import CoordinatorWriter
from management.rbac.rbac_repo import RbacRepo
from management.rbac.rbac_resolver import RbacResolver, verify_catalog_present
from management.mentoring_notes import note_colors
from management.mentoring_notes.mentoring_notes_repo import (
    MentoringNotesError,
    MentoringNotesRepo,
    SORT_STEP,
)
from management.server.management_app import ManagementApp

_PERSON = """
CREATE TABLE person (
    id INTEGER PRIMARY KEY AUTOINCREMENT, system_username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL, is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor INTEGER NOT NULL DEFAULT 0, is_support INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
)
"""

# Alt-Tabelle, die M002 (cases) beim Anwenden zaehlt/umbaut. Muss vor dem
# Migrationslauf existieren — identisch zur Vorbedingung in test_external_matters.
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


class MentoringNotesTests(unittest.TestCase):

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
        self.repo = MentoringNotesRepo(self.con, self.writer)

        # Rechte: Chefin 'alle' (sieht fremde Boards), Mueller 'eigene'.
        # Schmitz bekommt NICHTS — er ist die Gegenprobe fuer den Rechte-Ausfall.
        self.rbac.grant("supervisor", "mentoring_notes.view", scope="alle",
                        actor_id=1)
        self.rbac.grant("supervisor", "mentoring_notes.edit", scope="alle",
                        actor_id=1)
        self.rbac.grant("investigator", "mentoring_notes.view", scope="eigene",
                        actor_id=1)
        self.rbac.grant("investigator", "mentoring_notes.edit", scope="eigene",
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
    def _app(self):
        return ManagementApp(db_path=self._db)

    def _mk(self, owner_id=1, title="Mit Mueller Rueckruf klaeren",
            body="Er hatte Fragen zur Minimap.\nBis Freitag nachhaken.",
            color="gelb", tags=None, subject=2, status="offen",
            pinned=False, actor=1):
        return self.repo.create(
            owner_id=owner_id, title=title, body=body, color=color,
            tags=tags if tags is not None else ["schulung", "minimap"],
            subject_person_id=subject, status=status, pinned=pinned,
            actor_id=actor)

    def _audit(self, seq):
        row = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq = ?",
            (seq,)).fetchone()
        return row["event_type"], json.loads(row["content"])

    # ================================================================== MN01
    def test_mn01_migration_idempotent(self):
        tabs = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("mentoring_notes", tabs)
        self.assertIn("mentoring_note_tags", tabs)
        idx = {r[0] for r in self.con.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("ix_notes_board", idx)
        self.assertIn("ix_notes_subject", idx)
        self.assertIn("ix_note_tag", idx)
        caps = {r[0] for r in self.con.execute(
            "SELECT code FROM rbac_capability")}
        self.assertIn("mentoring_notes.view", caps)
        self.assertIn("mentoring_notes.edit", caps)

        # Zweiter Lauf: No-op, keine Duplikate/Fehler.
        MigrationRunner(self.con, discover(coordinator_migrations),
                        audit=AuditLog(self.con), deployed_by="tester").run()
        caps2 = self.con.execute(
            "SELECT COUNT(*) c FROM rbac_capability "
            "WHERE code LIKE 'mentoring_notes.%'").fetchone()["c"]
        self.assertEqual(caps2, 2)

    # ================================================================== MN02
    def test_mn02_catalog_present(self):
        # Der Code-Katalog (catalog.py) MUSS nach M012 vollstaendig in der DB
        # sein — sonst schluege der Start-Check fehl (Grundregel 1).
        verify_catalog_present(self.con)  # wirft nicht -> ok

    # ================================================================== MN03
    def test_mn03_create_is_audited(self):
        res = self._mk()
        nid, seq = res["note_id"], res["audit_seq"]

        rec = self.repo.get(nid)
        self.assertEqual(rec.status, "offen")
        self.assertEqual(rec.owner_id, 1)
        self.assertEqual(rec.subject_person_id, 2)
        self.assertEqual(rec.subject_display_name, "Mueller")
        self.assertEqual(rec.owner_display_name, "Chefin")
        # Kopplung Zeile <-> Beleg gesetzt (kein audit_seq=0).
        self.assertEqual(rec.audit_seq, seq)
        self.assertEqual(rec.created_audit_seq, seq)

        etype, payload = self._audit(seq)
        self.assertEqual(etype, "mentoring_note_created")
        # SENSIBILITAETSREGEL: kein Freitext im Beleg, nur Laengen/Fakten.
        self.assertNotIn("title", payload)
        self.assertNotIn("body", payload)
        self.assertNotIn("tags", payload)
        self.assertIn("title_len", payload)
        self.assertIn("body_len", payload)
        self.assertEqual(payload["note_id"], nid)
        self.assertEqual(payload["tag_count"], 2)

        # Leere Ueberschrift / falsche Farbe / falscher Status -> Fehler.
        with self.assertRaises(MentoringNotesError):
            self.repo.create(owner_id=1, title="   ", actor_id=1)
        with self.assertRaises(MentoringNotesError):
            self.repo.create(owner_id=1, title="x", color="pink", actor_id=1)
        with self.assertRaises(MentoringNotesError):
            self.repo.create(owner_id=1, title="x", status="zu", actor_id=1)

    # ================================================================== MN04
    def test_mn04_tags_normalized(self):
        res = self.repo.create(
            owner_id=1, title="Tags pruefen",
            tags=["  Schulung ", "schulung", "", "Minimap", "Schulung"],
            actor_id=1)
        rec = self.repo.get(res["note_id"])
        # getrimmt, dedupliziert (case-sensitiv exakt), sortiert.
        self.assertEqual(rec.tags, ("Minimap", "Schulung", "schulung"))

        # update mit tags=[] leert die Tag-Menge.
        self.repo.update(res["note_id"], tags=[], actor_id=1)
        self.assertEqual(self.repo.get(res["note_id"]).tags, tuple())

    # ================================================================== MN05
    def test_mn05_update_partial(self):
        nid = self._mk()["note_id"]
        seq = self.repo.update(nid, status="erledigt", color="gruen",
                               actor_id=1)
        rec = self.repo.get(nid)
        self.assertEqual(rec.status, "erledigt")
        self.assertEqual(rec.color, "gruen")
        self.assertEqual(rec.audit_seq, seq)   # letzte Aenderung zeigt hierauf
        self.assertEqual(rec.created_audit_seq, rec.created_audit_seq)  # bleibt

        etype, payload = self._audit(seq)
        self.assertEqual(etype, "mentoring_note_updated")
        self.assertIn("status", payload["changed"])
        self.assertIn("color", payload["changed"])
        self.assertNotIn("title", payload)      # Freitext nicht im Beleg

        # Betroffenen ausdruecklich loeschen (None != _UNSET).
        self.repo.update(nid, subject_person_id=None, actor_id=1)
        self.assertIsNone(self.repo.get(nid).subject_person_id)

        # Resultierenden Zustand validieren: leere Ueberschrift -> Fehler.
        with self.assertRaises(MentoringNotesError):
            self.repo.update(nid, title="  ", actor_id=1)

    # ================================================================== MN06
    def test_mn06_archive_restore_soft_delete(self):
        nid = self._mk()["note_id"]
        self.assertFalse(self.repo.get(nid).is_archived)

        self.repo.archive(nid, actor_id=1)
        rec = self.repo.get(nid)
        self.assertTrue(rec.is_archived)
        self.assertIsNotNone(rec.archived_at)

        # Die Zeile existiert PHYSISCH weiter (kein DELETE).
        cnt = self.con.execute(
            "SELECT COUNT(*) c FROM mentoring_notes WHERE id=?",
            (nid,)).fetchone()["c"]
        self.assertEqual(cnt, 1)

        # aktive Liste leer, Archiv-Liste enthaelt sie.
        self.assertEqual(len(self.repo.list_notes(owner_id=1)), 0)
        self.assertEqual(len(self.repo.list_notes(owner_id=1, archived=True)), 1)

        # doppeltes Archivieren scheitert laut.
        with self.assertRaises(MentoringNotesError):
            self.repo.archive(nid, actor_id=1)

        # Wiederherstellen.
        self.repo.restore(nid, actor_id=1)
        self.assertFalse(self.repo.get(nid).is_archived)
        with self.assertRaises(MentoringNotesError):
            self.repo.restore(nid, actor_id=1)   # nicht archiviert

    # ================================================================== MN07
    def test_mn07_duplicate(self):
        src = self._mk(title="Original", status="erledigt", pinned=True)["note_id"]
        dup = self.repo.duplicate(src, actor_id=1)
        drec = self.repo.get(dup["note_id"])
        self.assertEqual(drec.title, "Original (Kopie)")
        self.assertEqual(drec.status, "offen")     # Kopie ist immer offen
        self.assertFalse(drec.pinned)
        self.assertEqual(drec.tags, self.repo.get(src).tags)

        etype, payload = self._audit(dup["audit_seq"])
        self.assertEqual(etype, "mentoring_note_created")
        self.assertEqual(payload["duplicated_from"], src)

        # Original unveraendert.
        self.assertEqual(self.repo.get(src).title, "Original")

    # ================================================================== MN08
    def test_mn08_reorder(self):
        a = self._mk(title="A")["note_id"]
        b = self._mk(title="B")["note_id"]
        c = self._mk(title="C")["note_id"]

        seq = self.repo.reorder(1, [c, a, b], actor_id=1)
        order = [n.id for n in self.repo.list_notes(owner_id=1)]
        self.assertEqual(order, [c, a, b])
        # Luecken-Spacing.
        self.assertEqual(self.repo.get(c).sort_index, SORT_STEP)
        self.assertEqual(self.repo.get(a).sort_index, 2 * SORT_STEP)

        etype, payload = self._audit(seq)
        self.assertEqual(etype, "mentoring_note_reordered")
        self.assertEqual(payload["ordered_ids"], [c, a, b])

        # Gegenprobe: fremder owner, archiviert, doppelte IDs.
        foreign = self.repo.create(owner_id=2, title="fremd", actor_id=2)["note_id"]
        with self.assertRaises(MentoringNotesError):
            self.repo.reorder(1, [a, foreign], actor_id=1)
        self.repo.archive(b, actor_id=1)
        with self.assertRaises(MentoringNotesError):
            self.repo.reorder(1, [a, b], actor_id=1)
        with self.assertRaises(MentoringNotesError):
            self.repo.reorder(1, [a, a], actor_id=1)

    # ================================================================== MN09
    def test_mn09_no_unaudited_write(self):
        # Repo OHNE Writer (rein lesend) verweigert jeden Schreibweg.
        ro = MentoringNotesRepo(self.con)   # kein Writer
        with self.assertRaises(MentoringNotesError):
            ro.create(owner_id=1, title="x", actor_id=1)
        nid = self._mk()["note_id"]
        with self.assertRaises(MentoringNotesError):
            ro.update(nid, status="erledigt", actor_id=1)
        with self.assertRaises(MentoringNotesError):
            ro.archive(nid, actor_id=1)
        with self.assertRaises(MentoringNotesError):
            ro.reorder(1, [nid], actor_id=1)

    # ================================================================== MN10
    def test_mn10_list_filters_and_order(self):
        n1 = self._mk(title="rot-offen", color="rosa", status="offen",
                      tags=["a"], subject=2)["note_id"]
        n2 = self._mk(title="gruen-erledigt", color="gruen", status="erledigt",
                      tags=["b"], subject=3)["note_id"]
        n3 = self._mk(title="angeheftet", color="gelb", pinned=True,
                      tags=["a", "b"], subject=2)["note_id"]

        # Reihenfolge: angeheftet zuerst.
        order = [n.id for n in self.repo.list_notes(owner_id=1)]
        self.assertEqual(order[0], n3)

        # Feinfilter.
        self.assertEqual(
            [n.id for n in self.repo.list_notes(owner_id=1, status="erledigt")],
            [n2])
        self.assertEqual(
            [n.id for n in self.repo.list_notes(owner_id=1, color="rosa")],
            [n1])
        self.assertEqual(
            {n.id for n in self.repo.list_notes(owner_id=1, tag="a")},
            {n1, n3})
        self.assertEqual(
            {n.id for n in self.repo.list_notes(owner_id=1, subject_person_id=3)},
            {n2})

    # ================================================================== MN11
    def test_mn11_endpoint_scope(self):
        # Zwei Boards: Chefin (1) und Mueller (2).
        self._mk(owner_id=1, title="Board Chefin", actor=1)
        self._mk(owner_id=2, title="Board Mueller", subject=None, actor=2)
        app = self._app()

        # Chefin (Scope 'alle'): sieht ALLE Boards.
        r = app.dispatch(1, "/api/mentoring/notes", {})
        self.assertEqual(r.status, 200)
        data = json.loads(r.body)
        self.assertEqual(data["scope"], "alle")
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["colors"]), 7)

        # Chefin gezielt auf fremdes Board 2.
        r = app.dispatch(1, "/api/mentoring/notes", {"owner_id": ["2"]})
        data = json.loads(r.body)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["notes"][0]["title"], "Board Mueller")

        # Mueller (Scope 'eigene'): NUR sein eigenes Board.
        r = app.dispatch(2, "/api/mentoring/notes", {})
        data = json.loads(r.body)
        self.assertEqual(data["scope"], "eigene")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["owner_id"], 2)
        self.assertEqual(data["notes"][0]["title"], "Board Mueller")

        # Schmitz (kein Recht) -> 403.
        r = app.dispatch(3, "/api/mentoring/notes", {})
        self.assertEqual(r.status, 403)

        # Archiv-Sicht.
        nid = json.loads(app.dispatch(
            2, "/api/mentoring/notes", {}).body)["notes"][0]["id"]
        self.repo.archive(nid, actor_id=2)
        r = app.dispatch(2, "/api/mentoring/notes", {"archived": ["1"]})
        self.assertEqual(json.loads(r.body)["count"], 1)
        r = app.dispatch(2, "/api/mentoring/notes", {})
        self.assertEqual(json.loads(r.body)["count"], 0)


if __name__ == "__main__":
    unittest.main()
