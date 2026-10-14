# =============================================================================
# tests/test_bildschleier_umschalten.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier: Umschalten (Build 775)
# =============================================================================
# Befund 13.10.2026 (PROD): Umschalten scheiterte mit 'database is locked';
# die 500-Antwort trug keinen Zustand, die Schaltflaeche kam aus dem
# Fehlerzustand nur per F5 heraus (D2). Ursache der Sperre: Transaktion der
# geteilten Verbindung offen nach gescheiterter Schreibanweisung (Build 774).
#
#   BSE01  500 bei sqlite3-Fehler: JSON mit gespeichertem Zustand + error
#   BSE02  500 bei unerwartetem Fehler: ebenso, mit Traceback im Protokoll
#   BSE03  DURCHLAUF 13.10.: gescheiterter Schreibvorgang auf evidence, Lesung
#          auf cdb, dann POST /_forensic/image-veil -> 200, Wahl gespeichert
#          (mit Build 774 bleibt keine Transaktion offen)
#   BSE04  GEGENPROBE zu BSE03: dieselbe Folge mit einer Schreibstelle OHNE
#          Schutz -> POST 500 'locked', Rumpf meldet gespeichert 'klar';
#          nach rollback() -> 200. Der Aufbau bildet den Befund also ab.
#          Dauer ~5 s (busy_timeout des Dienstes, wie in PROD).
#
# Version: v0.8.775 · Build: 775 · 2026-10-14
# =============================================================================
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import shutil
import types
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from core import bildschleier_dienst as bd                           # noqa: E402
import forensic_api.bildschleier as endpunkt_mod                     # noqa: E402
from db.evidence_db import EvidenceDb                                # noqa: E402
from db.locking_connection import LockingConnection                  # noqa: E402


class _Handler:
    def __init__(self):
        self.status = None
        self.body = b""
        self.headers = {}

    def send_response_body(self, status, body, content_type="", extra_headers=None):
        self.status = status
        self.body = body
        self.headers = dict(extra_headers or {})

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class _Basis(unittest.TestCase):

    def setUp(self):
        from tests.test_bildschleier_fundament import _Welt
        self.welt = _Welt("setUp")
        self.welt.setUp()
        self.welt._vergeben()             # Person 1 darf umschalten
        bd.zuruecksetzen_fuer_tests()
        from core.config_loader import ConfigLoader
        self.config = ConfigLoader(str(WURZEL / "config.yaml"))

    def tearDown(self):
        bd.zuruecksetzen_fuer_tests()
        self.welt.tearDown()

    def _ctx(self):
        return types.SimpleNamespace(investigator_id=1,
                                     coordinator_db=Path(self.welt.db_path))

    def _post(self, veiled):
        bd.zuruecksetzen_fuer_tests()
        h = _Handler()
        endpunkt_mod.BildschleierEndpoint(None, self._ctx(), self.config).handle_post(
            h, json.dumps({"veiled": veiled}).encode())
        return h


class TestFehlerantwort(_Basis):

    def _mit_fehler(self, fehler):
        alt = bd.BildschleierDienst.setzen

        def _wirft(self, veiled):
            raise fehler
        bd.BildschleierDienst.setzen = _wirft
        try:
            return self._post(True)
        finally:
            bd.BildschleierDienst.setzen = alt

    def test_bse01_sqlite_fehler_500_mit_zustand(self):
        h = self._mit_fehler(sqlite3.OperationalError("database is locked"))
        self.assertEqual(h.status, 500)
        d = h.json()
        self.assertEqual(d["error"], "store_failed")
        self.assertIn("locked", d["detail"])
        self.assertIs(d["veiled"], False)          # gespeichert: klar
        self.assertIs(d["locked"], False)
        self.assertEqual(d["reason"], "default")
        self.assertTrue(d["tooltip"])

    def test_bse02_unerwarteter_fehler_500_mit_zustand(self):
        with self.assertLogs(endpunkt_mod.logger, level="ERROR"):
            h = self._mit_fehler(RuntimeError("unerwartet"))
        self.assertEqual(h.status, 500)
        d = h.json()
        self.assertEqual(d["error"], "store_failed")
        self.assertIs(d["veiled"], False)
        self.assertIs(d["locked"], False)


class TestDurchlauf1310(_Basis):
    """evidence (main) + coordinator (cdb) auf EINER LockingConnection."""

    def setUp(self):
        super().setUp()
        self.dir = Path(tempfile.mkdtemp(prefix="aiw_bse_"))
        roh = sqlite3.connect(str(self.dir / "evidence_1.db"),
                              check_same_thread=False, timeout=0.3)
        roh.execute("ATTACH DATABASE ? AS cdb", (self.welt.db_path,))
        self.roh = roh
        self.lc = LockingConnection(roh)
        self.edb = EvidenceDb(self.lc)
        # Ersatz fuer die beschaedigte Datei: jede Einfuegung scheitert.
        self.lc.execute(
            "CREATE TEMP TRIGGER aiw_bse_fehler BEFORE INSERT ON "
            "main.viewport_events BEGIN SELECT RAISE(ABORT, 'malformed "
            "(simuliert)'); END")

    def tearDown(self):
        try:
            self.roh.close()
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)
            super().tearDown()

    def _lesung_cdb(self):
        self.lc.execute("SELECT COUNT(*) FROM cdb.person").fetchall()

    def _gespeichert(self):
        return self.welt.con.execute(
            "SELECT COUNT(*) FROM person_image_veil WHERE person_id = 1"
        ).fetchone()[0]

    def test_bse03_ablauf_1310_umschalten_gelingt(self):
        ev = {"page_url": "http://f/forum/viewtopic.php?id=1",
              "element_id": "p1", "visible_ms": 5, "ts_enter": 1, "ts_leave": 2}
        with self.assertRaises(sqlite3.DatabaseError):
            self.edb.save_viewport_batch([ev], investigator_id=1)
        self._lesung_cdb()
        h = self._post(True)
        self.assertEqual(h.status, 200, h.body)
        self.assertIs(h.json()["veiled"], True)
        self.assertEqual(self._gespeichert(), 1)
        h = self._post(False)                       # und wieder zurueck
        self.assertEqual(h.status, 200, h.body)
        self.assertIs(h.json()["veiled"], False)

    def test_bse04_gegenprobe_ohne_schutz_500_locked(self):
        with self.assertRaises(sqlite3.DatabaseError):
            self.lc.execute(
                "INSERT INTO viewport_events (page_url, element_id, visible_ms, "
                "ts_enter, ts_leave, investigator_id) VALUES (?,?,?,?,?,?)",
                ("u", "p", 1, 1, 2, 1))
        self._lesung_cdb()
        with self.assertLogs(endpunkt_mod.logger, level="ERROR"):
            h = self._post(True)
        self.assertEqual(h.status, 500, h.body)
        d = h.json()
        self.assertIn("locked", d["detail"])
        self.assertIs(d["veiled"], False)            # gespeichert bleibt klar
        self.assertEqual(self._gespeichert(), 0)
        self.lc.rollback()
        h = self._post(True)
        self.assertEqual(h.status, 200, h.body)


if __name__ == "__main__":
    unittest.main()
