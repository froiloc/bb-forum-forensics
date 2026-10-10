# =============================================================================
# tests/test_bildschleier_fundament.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier, Fundament (Build 771)
# =============================================================================
# Waechter BS01-BS08 und BS22 (Bauplan Builds 771-773, §9).
#
#   BS01  M040 ist additiv und idempotent; zweiter Lauf ohne Aenderung,
#         keine Bestandszeile gewonnen oder verloren
#   BS02  M040 vergibt KEINEN Grant und weist KEINE Rolle zu (Delta)
#   BS03  Seed in M040 == management/rbac/catalog.py (woertliche Kopie)
#   BS04  keine Person            -> verschleiert + gesperrt (no_investigator)
#   BS05  RBAC nicht lesbar       -> verschleiert + gesperrt (rbac_unavailable)
#   BS06  Recht fehlt             -> verschleiert + gesperrt (no_capability);
#         auch fuer JEDE Person unmittelbar nach M040
#   BS06a Recht da, Tabelle fehlt -> verschleiert + gesperrt (store_unavailable)
#   BS07  Recht da, keine Zeile   -> KLAR, frei (default) — Alex 09.10.2026
#   BS08  Schreiben: genau EIN audit_log-Beleg, audit_seq gekoppelt, Payload
#         mit vollstaendigem Zustand; ohne Recht / fremde Person / kein bool
#         wird abgewiesen und es entsteht weder Zeile noch Beleg
#   BS22  'researcher' setzt sich GEGEN das Recht durch, auch wenn eine
#         zweite Rolle 'imageveil.lift' mitbringt; im Katalog traegt die
#         Rolle das Recht nicht
#
# MUTATIONSGEGENPROBEN (gefahren in Build 771, Ergebnis im build.json):
#   M1  In BildschleierRepo.zustand() die Rollenpruefung hinter die
#       Rechtepruefung verschoben            -> BS22 rot
#   M2  Voreinstellung ohne Zeile auf veiled=True gesetzt -> BS07 rot
#   M3  In M040 einen Grant an 'investigator' geschrieben -> BS02 rot
#   M4  BildschleierZustand-Invariante entfernt (gesperrt ohne Schleier
#       zulaessig)                           -> BS09z rot
#
# Version: v0.8.771 · Build: 771 · 2026-10-09
# =============================================================================

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import management.migrations.coordinator as coordinator_migrations  # noqa: E402
from management.audit.audit_log import AuditLog                     # noqa: E402
from management.audit.event_types import EventType                  # noqa: E402
from management.bildschleier.bildschleier_repo import (             # noqa: E402
    RECHT, ROLLE_PFLICHT, BildschleierFehler, BildschleierRepo,
)
from management.bildschleier.bildschleier_zustand import (          # noqa: E402
    ALLE_GRUENDE, GESPERRTE_GRUENDE, BildschleierZustand,
)
from management.gateway.coordinator_writer import CoordinatorWriter  # noqa: E402
from management.migrations.coordinator import m040_image_veil as m040  # noqa: E402
from management.migrations.runner import MigrationRunner, discover  # noqa: E402
from management.rbac import catalog                                 # noqa: E402
from management.rbac.rbac_repo import RbacRepo                      # noqa: E402

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

#: Personen der Testwelt. 1 = Ermittler (bekommt das Recht), 2 = Forschende,
#: 3 = Ermittler ohne Recht, 4 = Forschende mit ZUSAETZLICHER Ermittlerrolle.
_PERSONEN = (
    ("NRW\\ermittler", "Ermittler"),
    ("NRW\\forschung", "Forschung"),
    ("NRW\\ohnerecht", "Ohne Recht"),
    ("NRW\\doppelt", "Forschung mit Zweitrolle"),
)


class _Welt(unittest.TestCase):
    """coordinator.db ueber die VOLLE Migrationskette, ohne Grants."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.db_path = os.path.join(self._tmp, "coordinator.db")
        con = sqlite3.connect(self.db_path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        con.executescript(_PERSON)
        con.executescript(_OLD_SCRAPE_JOBS)
        now = int(time.time())
        for uname, dname in _PERSONEN:
            con.execute(
                "INSERT INTO person (system_username, display_name, "
                "is_investigator, is_supervisor, is_support, created_at) "
                "VALUES (?,?,1,0,0,?)", (uname, dname, now))
        self.audit = AuditLog(con)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=self.audit, deployed_by="tester").run()
        self.writer = CoordinatorWriter(con, self.audit)
        self.con = con

    def tearDown(self):
        try:
            self.con.close()
        finally:
            shutil.rmtree(self._tmp, ignore_errors=True)

    # ------------------------------------------------------------ Hilfen ---
    def _vergeben(self):
        """Das Wartungsfenster nachstellen: Recht an 'investigator',
        Rollen zuweisen — ueber die auditierten Wege, nicht per SQL."""
        rbac = RbacRepo(self.con, self.writer)
        rbac.grant("investigator", RECHT, scope=None, actor_id=1)
        rbac.assign_role(1, "investigator", actor_id=1)
        rbac.assign_role(2, ROLLE_PFLICHT, actor_id=1)
        # Person 3 bekommt nichts.
        rbac.assign_role(4, ROLLE_PFLICHT, actor_id=1)
        rbac.assign_role(4, "investigator", actor_id=1)

    def _repo(self, writer=True):
        return BildschleierRepo(self.con, self.writer if writer else None)

    def _spitze(self):
        return self.con.execute("SELECT MAX(seq) FROM audit_log").fetchone()[0]


# =============================================================================
# Migration
# =============================================================================
class MigrationTests(_Welt):

    def test_bs01_additiv_und_idempotent(self):
        def _abbild():
            tabellen = {}
            for (name,) in self.con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' ORDER BY name"):
                tabellen[name] = self.con.execute(
                    'SELECT COUNT(*) FROM "%s"' % name).fetchone()[0]
            return tabellen

        vorher = _abbild()
        self.assertIn("person_image_veil", vorher)
        self.assertEqual(vorher["person_image_veil"], 0)
        personen_vorher = [tuple(r) for r in self.con.execute(
            "SELECT * FROM person ORDER BY id")]

        # Zweiter Lauf: No-op
        self.con.execute("BEGIN")
        m040.up(self.con)
        self.con.execute("COMMIT")
        self.assertEqual(_abbild(), vorher)
        self.assertEqual([tuple(r) for r in self.con.execute(
            "SELECT * FROM person ORDER BY id")], personen_vorher)

        # Version und Art stimmen
        self.assertEqual(m040.VERSION, 40)
        self.assertEqual(m040.KIND, "additive")
        row = self.con.execute(
            "SELECT kind FROM schema_migrations WHERE version = 40").fetchone()
        self.assertIsNotNone(row, "M040 steht nicht in schema_migrations")
        self.assertEqual(row[0], "additive")

    def test_bs01a_check_auf_veiled_greift(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute(
                "INSERT INTO person_image_veil (person_id, veiled, "
                "changed_at, audit_seq) VALUES (1, 2, 0, 0)")

    def test_bs02_keine_grants_keine_zuweisungen(self):
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM rbac_grant WHERE capability_code = ?",
            (RECHT,)).fetchone()[0], 0)
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM person_role WHERE role_code = ?",
            (ROLLE_PFLICHT,)).fetchone()[0], 0)

    def test_bs02a_vorgefundener_grant_bricht_nicht_ab(self):
        # Ein VOR dem zweiten Lauf vorhandener Grant gehoert nicht M040 —
        # er darf den Lauf nicht verriegeln (Lehre M038, Build 711).
        RbacRepo(self.con, self.writer).grant(
            "investigator", RECHT, scope=None, actor_id=1)
        self.con.execute("BEGIN")
        m040.up(self.con)       # darf nicht werfen
        self.con.execute("COMMIT")

    def test_bs03_seed_gleich_katalog(self):
        rollen = {r.code: r.label for r in catalog.ROLES}
        rechte = {c.code: (c.label, c.description) for c in catalog.CAPABILITIES}
        for code, label in m040._SEED_ROLES:
            self.assertEqual(rollen.get(code), label, code)
        for code, label, desc in m040._SEED_CAPS:
            self.assertEqual(rechte.get(code), (label, desc), code)
        # und in der Datenbank genau so
        row = self.con.execute(
            "SELECT label, description FROM rbac_capability WHERE code=?",
            (RECHT,)).fetchone()
        self.assertEqual((row[0], row[1]), rechte[RECHT])
        row = self.con.execute(
            "SELECT label FROM rbac_role WHERE code=?",
            (ROLLE_PFLICHT,)).fetchone()
        self.assertEqual(row[0], rollen[ROLLE_PFLICHT])


# =============================================================================
# Zustand
# =============================================================================
class ZustandTests(_Welt):

    def test_bs04_keine_person(self):
        z = self._repo().zustand(None)
        self.assertEqual((z.veiled, z.locked, z.reason),
                         (True, True, "no_investigator"))

    def test_bs05_rbac_nicht_lesbar(self):
        leer = sqlite3.connect(":memory:")   # keine Tabellen
        try:
            z = BildschleierRepo(leer).zustand(1)
        finally:
            leer.close()
        self.assertEqual((z.veiled, z.locked, z.reason),
                         (True, True, "rbac_unavailable"))

    def test_bs06_ohne_vergabe_ist_jeder_verschleiert(self):
        # Unmittelbar nach M040: niemand hat das Recht (Bauplan §6.1).
        for pid in (1, 2, 3, 4):
            z = self._repo().zustand(pid)
            self.assertTrue(z.veiled and z.locked, pid)
        self.assertEqual(self._repo().zustand(1).reason, "no_capability")
        # Nach der Vergabe bleibt Person 3 gesperrt.
        self._vergeben()
        z = self._repo().zustand(3)
        self.assertEqual((z.veiled, z.locked, z.reason),
                         (True, True, "no_capability"))

    def test_bs06a_speicher_nicht_lesbar(self):
        self._vergeben()
        self.con.execute("DROP TABLE person_image_veil")
        z = self._repo().zustand(1)
        self.assertEqual((z.veiled, z.locked, z.reason),
                         (True, True, "store_unavailable"))

    def test_bs07_voreinstellung_klar(self):
        self._vergeben()
        z = self._repo().zustand(1)
        self.assertEqual((z.veiled, z.locked, z.reason),
                         (False, False, "default"))

    def test_bs22_rolle_hat_vorrang_vor_dem_recht(self):
        self._vergeben()
        for pid in (2, 4):
            z = self._repo().zustand(pid)
            self.assertEqual((z.veiled, z.locked, z.reason),
                             (True, True, "required_by_role"), pid)
        # Gegenprobe: Person 4 HAT das Recht ueber die Zweitrolle — sonst
        # waere der Test oben wertlos.
        from management.rbac.rbac_resolver import RbacResolver
        self.assertTrue(RbacResolver(self.con).resolve(4).can(RECHT))

    def test_bs22a_rolle_traegt_das_recht_nicht(self):
        # Kein Grant 'researcher' -> 'imageveil.lift' im Bestand nach der
        # Vergabe des Wartungsfensters.
        self._vergeben()
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM rbac_grant WHERE role_code = ? "
            "AND capability_code = ?", (ROLLE_PFLICHT, RECHT)).fetchone()[0], 0)


# =============================================================================
# Schreiben
# =============================================================================
class SchreibTests(_Welt):

    def test_bs08_ein_beleg_gekoppelt(self):
        self._vergeben()
        spitze = self._spitze()
        seq = self._repo().setzen(person_id=1, veiled=True, actor_id=1)
        self.assertEqual(self._spitze(), spitze + 1)
        self.assertEqual(seq, spitze + 1)
        row = self.con.execute(
            "SELECT event_type, content FROM audit_log WHERE seq = ?",
            (seq,)).fetchone()
        self.assertEqual(row[0], EventType.IMAGE_VEIL_SET)
        self.assertEqual(json.loads(row[1]), {"veiled": True})
        zeile = self.con.execute(
            "SELECT veiled, audit_seq FROM person_image_veil "
            "WHERE person_id = 1").fetchone()
        self.assertEqual((zeile[0], zeile[1]), (1, seq))
        z = self._repo().zustand(1)
        self.assertEqual((z.veiled, z.locked, z.reason),
                         (True, False, "chosen"))
        # Zurueckschalten: dieselbe Zeile, neuer Beleg
        seq2 = self._repo().setzen(person_id=1, veiled=False, actor_id=1)
        self.assertEqual(seq2, seq + 1)
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM person_image_veil").fetchone()[0], 1)
        self.assertFalse(self._repo().zustand(1).veiled)

    def test_bs08a_abweisungen_ohne_spur(self):
        self._vergeben()
        repo = self._repo()
        spitze = self._spitze()
        faelle = (
            dict(person_id=3, veiled=False, actor_id=3),   # kein Recht
            dict(person_id=2, veiled=False, actor_id=2),   # researcher
            dict(person_id=4, veiled=False, actor_id=4),   # researcher+Recht
            dict(person_id=1, veiled=False, actor_id=3),   # fremde Person
            dict(person_id=1, veiled=False, actor_id=None),  # kein Akteur
            dict(person_id=1, veiled=0, actor_id=1),       # kein bool
        )
        for f in faelle:
            with self.assertRaises(BildschleierFehler, msg=str(f)):
                repo.setzen(**f)
        self.assertEqual(self._spitze(), spitze)
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM person_image_veil").fetchone()[0], 0)

    def test_bs08b_ohne_schreiber_kein_schreiben(self):
        self._vergeben()
        with self.assertRaises(BildschleierFehler):
            self._repo(writer=False).setzen(person_id=1, veiled=True,
                                            actor_id=1)


# =============================================================================
# Zustandsobjekt
# =============================================================================
class ZustandsobjektTests(unittest.TestCase):

    def test_bs09z_gesperrt_heisst_verschleiert(self):
        for grund in GESPERRTE_GRUENDE:
            with self.assertRaises(ValueError, msg=grund):
                BildschleierZustand(veiled=False, locked=True, reason=grund)
            with self.assertRaises(ValueError, msg=grund):
                BildschleierZustand(veiled=True, locked=False, reason=grund)
        with self.assertRaises(ValueError):
            BildschleierZustand(veiled=False, locked=True, reason="default")
        with self.assertRaises(ValueError):
            BildschleierZustand(veiled=True, locked=True, reason="unfug")

    def test_bs09t_jeder_grund_hat_einen_tooltip(self):
        for grund in ALLE_GRUENDE:
            if grund in GESPERRTE_GRUENDE:
                z = BildschleierZustand.gesperrt(grund)
                self.assertTrue(z.tooltip.strip(), grund)
            else:
                for v in (True, False):
                    z = BildschleierZustand(veiled=v, locked=False,
                                            reason=grund)
                    self.assertTrue(z.tooltip.strip(), grund)
        d = BildschleierZustand.gesperrt("required_by_role").to_dict()
        self.assertEqual(set(d), {"veiled", "locked", "reason", "tooltip"})
        self.assertIn("Rolle", d["tooltip"])


if __name__ == "__main__":
    unittest.main()
