# =============================================================================
# tests/test_transaktionsschutz.py
# IT-Forensisches Ermittlungswerkzeug — Transaktionsschutz (Build 774)
# =============================================================================
# Prueft das Verhalten von db/schreibvorgang.py (Schreibvorgang) und des
# Sicherheitsnetzes in db/locking_connection.py / server/http_server.py.
#
# BEFUND (13./14.10.2026, Fall 2948078, PROD):
#   evidence_2948078.db war beschaedigt. save_viewport_batch scheiterte mit
#   'database disk image is malformed' und rief kein rollback() auf. Die
#   Transaktion der geteilten Verbindung blieb offen; die naechste Lesung auf
#   cdb (coordinator.db) hielt darin eine SHARED-Sperre, und der Bildschleier-
#   Schreiber (eigene Verbindung, CoordinatorWriter) bekam nach 5 s
#   'database is locked'.
#
# Hier wird die Beschaedigung durch einen TEMP-Trigger ersetzt, der jede
# Einfuegung in viewport_events mit RAISE(ABORT) scheitern laesst. Fuer den
# Mechanismus ist das gleichwertig: das implizite BEGIN ist gelaufen, die
# Anweisung scheitert, die Transaktion bleibt offen. (Belegt durch TS02 —
# die Gegenprobe ohne Schutz MUSS die Sperre erzeugen, sonst waere TS01
# 'gruen aber tot'.)
#
#   TS01  Ablauf 13.10. mit echtem EvidenceDb.save_viewport_batch: nach dem
#         Fehler ist keine Transaktion offen, der Schreiber auf
#         coordinator.db kommt durch.
#   TS02  GEGENPROBE: dieselbe Folge mit derselben Anweisung OHNE Schutz
#         erzeugt 'database is locked' — der Testaufbau bildet den Befund ab.
#   TS03  Schreibvorgang: Ausnahme laeuft unveraendert weiter, rollback
#         erfolgt, Lock wird freigegeben.
#   TS04  Schreibvorgang haelt den Lock fuer die ganze Dauer: ein anderer
#         Thread kommt zwischen INSERT und commit() nicht an die Verbindung.
#   TS05  save_alias mit doppeltem Begriff: keine offene Transaktion danach.
#   TS06  acquire_lock bei belegtem Lock: keine offene Transaktion danach.
#   TS07  Sicherheitsnetz: eigener Thread hat Transaktion offen gelassen ->
#         zurueckgerollt.
#   TS08  Sicherheitsnetz: FREMDE Transaktion (anderer Thread) bleibt
#         unberuehrt, ihre Daten kommen nach deren commit() an.
#   TS09  Sicherheitsnetz: Eroeffner unbekannt -> nur gemeldet, einmal.
#   TS10  ForensicRequestHandler._handle_request ruft das Netz am Ende auf
#         (auch wenn der Router eine Ausnahme wirft).
#   TS11  Besitzer wird auch dann gesetzt, wenn die eroeffnende Anweisung
#         selbst scheitert (genau der Fall des Befunds).
#
# Build 775 — Befunde der unabhaengigen Durchsicht (14.10.2026):
#   TS12  get_sort_index_after: eine Blockverschiebung ueberlebt ein
#         fremdes rollback() (acquire_lock bei belegtem Lock) zwischen
#         Verschiebung und save_block — keine doppelten sort_index.
#   TS13  Sicherheitsnetz: Eroeffner-Thread lebt nicht mehr -> 'verwaist',
#         ERROR, einmal je Transaktion, NICHT zurueckgerollt.
#   TS14  Sicherheitsnetz ohne offene Transaktion wartet nicht auf den Lock.
#
# Version: v0.8.774 · Build: 774 · 2026-10-14
# =============================================================================
from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import EvidenceDb                                 # noqa: E402
import db.locking_connection as _lc_modul                             # noqa: E402
from db.locking_connection import LockingConnection                   # noqa: E402
from db.schreibvorgang import Schreibvorgang                          # noqa: E402

# Kurze Wartezeit fuer den zweiten Schreiber: im Befund 5 s, hier 0,3 s —
# es geht um "kommt durch" gegen "gesperrt", nicht um die Dauer.
_WARTEN_S = 0.3


def _ereignis():
    return {"page_url": "http://f/forum/viewtopic.php?id=1", "element_id": "p1",
            "visible_ms": 100, "ts_enter": 1, "ts_leave": 2}


class _Aufbau(unittest.TestCase):
    """evidence_<uid>.db als main, coordinator.db als cdb — wie im Bundle."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="aiw_ts_"))
        self.ev_pfad = self.dir / "evidence_4711.db"
        self.co_pfad = self.dir / "coordinator.db"
        co = sqlite3.connect(str(self.co_pfad))
        co.execute("CREATE TABLE einstellung (id INTEGER PRIMARY KEY, wert TEXT)")
        co.execute("INSERT INTO einstellung (wert) VALUES ('start')")
        co.commit()
        co.close()
        roh = sqlite3.connect(str(self.ev_pfad), check_same_thread=False,
                              timeout=_WARTEN_S)
        roh.execute("ATTACH DATABASE ? AS cdb", (str(self.co_pfad),))
        self.roh = roh
        self.lc = LockingConnection(roh)
        self.edb = EvidenceDb(self.lc)

    def tearDown(self):
        try:
            self.roh.close()
        except Exception:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def _viewport_scheitern_lassen(self):
        self.lc.execute(
            "CREATE TEMP TRIGGER aiw_ts_fehler BEFORE INSERT ON main.viewport_events "
            "BEGIN SELECT RAISE(ABORT, 'simulierter Schreibfehler'); END")

    def _coordinator_schreiben(self):
        """Wie CoordinatorWriter: eigene Verbindung, BEGIN IMMEDIATE, COMMIT."""
        w = sqlite3.connect(str(self.co_pfad), timeout=_WARTEN_S,
                            isolation_level=None)
        try:
            w.execute("BEGIN IMMEDIATE")
            w.execute("UPDATE einstellung SET wert='bildschleier' WHERE id=1")
            w.execute("COMMIT")
        finally:
            w.close()


class TestAblauf1310(_Aufbau):

    def test_ts01_kein_offene_transaktion_schreiber_kommt_durch(self):
        self._viewport_scheitern_lassen()
        with self.assertRaises(sqlite3.DatabaseError):
            self.edb.save_viewport_batch([_ereignis()], investigator_id=1)
        self.assertFalse(self.lc.in_transaction,
                         "nach dem Fehler darf keine Transaktion offen sein")
        # Lesung auf cdb — im Befund hielt sie die SHARED-Sperre.
        self.lc.execute("SELECT wert FROM cdb.einstellung").fetchall()
        t0 = time.monotonic()
        self._coordinator_schreiben()          # darf NICHT 'locked' werfen
        self.assertLess(time.monotonic() - t0, _WARTEN_S)

    def test_ts02_gegenprobe_ohne_schutz_sperrt(self):
        """Gleiche Anweisung, aber ohne Schreibvorgang-Rahmen und ohne rollback."""
        self._viewport_scheitern_lassen()
        with self.assertRaises(sqlite3.DatabaseError):
            self.lc.execute(
                "INSERT INTO viewport_events (page_url, element_id, visible_ms, "
                "ts_enter, ts_leave, investigator_id) VALUES (?,?,?,?,?,?)",
                ("u", "p", 1, 1, 2, 1))
        self.assertTrue(self.lc.in_transaction)
        self.lc.execute("SELECT wert FROM cdb.einstellung").fetchall()
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            self._coordinator_schreiben()
        self.assertIn("locked", str(ctx.exception))
        self.lc.rollback()
        self._coordinator_schreiben()          # nach rollback frei


class TestSchreibvorgang(_Aufbau):

    def test_ts03_ausnahme_unveraendert_rollback_lock_frei(self):
        class Eigen(Exception):
            pass
        with self.assertRaises(Eigen):
            with Schreibvorgang(self.lc, "ts03"):
                self.lc.execute("INSERT INTO scraper_log (event, user_id, detail, ts) "
                            "VALUES ('x', 1, NULL, 1)")
                self.assertTrue(self.lc.in_transaction)
                raise Eigen("weiter")
        self.assertFalse(self.lc.in_transaction)
        self.assertEqual(
            self.lc.execute("SELECT COUNT(*) FROM scraper_log").fetchone()[0], 0)
        # Lock frei: ein anderer Thread bekommt ihn sofort.
        frei = []
        t = threading.Thread(target=lambda: frei.append(
            self.lc.lock.acquire(timeout=1) and (self.lc.lock.release() or True)))
        t.start()
        t.join()
        self.assertEqual(frei, [True])

    def test_ts04_lock_fuer_ganze_dauer(self):
        reihenfolge = []
        drin = threading.Event()

        def anderer():
            drin.wait(2)
            self.lc.execute("SELECT 1").fetchall()   # muss warten
            reihenfolge.append("anderer")

        t = threading.Thread(target=anderer)
        t.start()
        with Schreibvorgang(self.lc, "ts04"):
            self.lc.execute("INSERT INTO scraper_log (event, user_id, detail, ts) "
                            "VALUES ('x', 1, NULL, 1)")
            drin.set()
            time.sleep(0.2)                  # anderer haette Zeit gehabt
            reihenfolge.append("commit")
            self.lc.commit()
        t.join(2)
        self.assertEqual(reihenfolge, ["commit", "anderer"])

    def test_ts05_save_alias_doppelt_keine_offene_transaktion(self):
        a = self.edb.save_alias("Obstgarten", "t")
        b = self.edb.save_alias("Obstgarten", "t")   # UNIQUE -> IntegrityError
        self.assertEqual(a, b)
        self.assertFalse(self.lc.in_transaction)

    def test_ts06_acquire_lock_belegt_keine_offene_transaktion(self):
        self.lc.execute(
            "INSERT INTO reports (report_type, sequence_nr, title, created_by, "
            "created_at, status) VALUES ('interim', 1, 'T', 'u', 1, 'draft')")
        self.lc.commit()
        rid = self.lc.execute("SELECT id FROM reports").fetchone()[0]
        erste = self.edb.acquire_lock(rid, "a", "sse-a")
        self.assertIsNotNone(erste)
        zweite = self.edb.acquire_lock(rid, "b", "sse-b")
        self.assertIsNone(zweite)
        self.assertFalse(self.lc.in_transaction)


class TestSicherheitsnetz(_Aufbau):

    def _offen_lassen(self, ergebnis):
        """Laeuft im Thread: Anweisung scheitert, Transaktion bleibt offen."""
        try:
            self.lc.execute(
                "INSERT INTO viewport_events (page_url, element_id, visible_ms, "
                "ts_enter, ts_leave, investigator_id) VALUES (?,?,?,?,?,?)",
                ("u", "p", 1, 1, 2, 1))
        except sqlite3.DatabaseError:
            pass
        ergebnis.append(self.lc.in_transaction)
        ergebnis.append(self.lc.transaktions_besitzer == threading.get_ident())
        ergebnis.append(self.lc.sicherheitsnetz("TEST /ts07"))
        ergebnis.append(self.lc.in_transaction)

    def test_ts07_eigener_thread_wird_zurueckgerollt(self):
        self._viewport_scheitern_lassen()
        erg = []
        with self.assertLogs(_lc_modul.logger, level="ERROR") as log:
            t = threading.Thread(target=self._offen_lassen, args=(erg,))
            t.start()
            t.join()
        self.assertEqual(erg, [True, True, "zurueckgerollt", False])
        self.assertIn("TEST /ts07", "\n".join(log.output))

    def test_ts08_fremde_transaktion_bleibt_unberuehrt(self):
        offen = threading.Event()
        pruefen_fertig = threading.Event()

        def fremd():
            self.lc.execute("INSERT INTO scraper_log (event, user_id, detail, ts) "
                            "VALUES ('fremd', 1, NULL, 8)")
            offen.set()
            pruefen_fertig.wait(2)
            self.lc.commit()

        t = threading.Thread(target=fremd)
        t.start()
        offen.wait(2)
        self.assertIsNone(self.lc.sicherheitsnetz("TEST /ts08"))
        self.assertTrue(self.lc.in_transaction)
        pruefen_fertig.set()
        t.join(2)
        self.assertEqual(self.lc.execute(
            "SELECT COUNT(*) FROM scraper_log WHERE ts = 8").fetchone()[0], 1)

    def test_ts09_unbekannter_eroeffner_nur_gemeldet_einmal(self):
        # An der Huelle vorbei auf der rohen Verbindung: der Wrapper sieht
        # die Eroeffnung nicht.
        self.roh.execute("INSERT INTO scraper_log (event, user_id, detail, ts) "
                            "VALUES ('roh', 1, NULL, 9)")
        self.assertIsNone(self.lc.transaktions_besitzer)
        self.assertEqual(self.lc.sicherheitsnetz("TEST /ts09"), "unbekannt")
        self.assertIsNone(self.lc.sicherheitsnetz("TEST /ts09"))
        self.assertTrue(self.lc.in_transaction)      # unberuehrt
        self.roh.commit()

    def test_ts11_besitzer_auch_bei_scheiternder_eroeffnung(self):
        self._viewport_scheitern_lassen()
        with self.assertRaises(sqlite3.DatabaseError):
            self.lc.execute(
                "INSERT INTO viewport_events (page_url, element_id, visible_ms, "
                "ts_enter, ts_leave, investigator_id) VALUES (?,?,?,?,?,?)",
                ("u", "p", 1, 1, 2, 1))
        self.assertTrue(self.lc.in_transaction)
        self.assertEqual(self.lc.transaktions_besitzer, threading.get_ident())
        self.lc.rollback()
        self.assertIsNone(self.lc.transaktions_besitzer)


class TestBefundeDurchsicht(_Aufbau):

    def test_ts12_verschiebung_ueberlebt_fremdes_rollback(self):
        rid = self.edb.create_report("interim", "T", "u")
        for bid, idx in (("b1", 1000), ("b2", 1001), ("b3", 2000)):
            self.edb.save_block(bid, rid, "u", "paragraph", sort_index=idx)
        # Den Editor-Lock VOR der Verschiebung belegen: sein commit() soll
        # die Verschiebung nicht nebenbei festschreiben (erste Fassung dieses
        # Tests tat das und blieb bei der Gegenprobe gruen).
        self.assertIsNotNone(self.edb.acquire_lock(rid, "a", "sse-a"))
        neu_idx = self.edb.get_sort_index_after("b1", rid)
        self.assertEqual(neu_idx, 1001)
        # Fremder Thread: belegter Editor-Lock -> IntegrityError -> rollback()
        t = threading.Thread(target=lambda: self.edb.acquire_lock(rid, "b", "sse-b"))
        t.start()
        t.join()
        self.edb.save_block("bNEU", rid, "u", "paragraph", sort_index=neu_idx)
        reihe = self.lc.execute(
            "SELECT block_id, sort_index FROM report_block_order "
            "ORDER BY sort_index").fetchall()
        indizes = [r[1] for r in reihe]
        self.assertEqual(len(indizes), len(set(indizes)), reihe)
        self.assertEqual([r[0] for r in reihe], ["b1", "bNEU", "b2", "b3"])

    def test_ts13_verwaister_eroeffner_wird_gemeldet(self):
        def leck():
            self.lc.execute("INSERT INTO scraper_log (event, user_id, detail, ts) "
                            "VALUES ('verwaist', 1, NULL, 13)")
        t = threading.Thread(target=leck)
        t.start()
        t.join()                                   # Eroeffner ist beendet
        self.assertTrue(self.lc.in_transaction)
        with self.assertLogs(_lc_modul.logger, level="ERROR") as log:
            self.assertEqual(self.lc.sicherheitsnetz("TEST /ts13"), "verwaist")
        self.assertIn("nicht mehr lebt", "\n".join(log.output))
        self.assertIsNone(self.lc.sicherheitsnetz("TEST /ts13"))   # einmal
        self.assertTrue(self.lc.in_transaction)    # NICHT zurueckgerollt
        self.lc.rollback()

    def test_ts14_ohne_transaktion_kein_warten_auf_den_lock(self):
        gehalten = threading.Event()
        loslassen = threading.Event()

        def halter():
            with self.lc.lock:
                gehalten.set()
                loslassen.wait(5)
        t = threading.Thread(target=halter)
        t.start()
        gehalten.wait(2)
        t0 = time.monotonic()
        self.assertIsNone(self.lc.sicherheitsnetz("TEST /ts14"))
        self.assertLess(time.monotonic() - t0, 0.5)
        loslassen.set()
        t.join()


class TestRequestHandler(_Aufbau):

    def _handler(self, dispatch):
        from server.http_server import ForensicRequestHandler
        h = object.__new__(ForensicRequestHandler)
        h.server = types.SimpleNamespace(
            bundle=types.SimpleNamespace(connection=self.lc),
            router=types.SimpleNamespace(dispatch=dispatch),
            maintenance_gate=None)
        h.headers = {}
        h.path = "/_forensic/ts10"
        h.gesendet = []
        h._send_500 = lambda: h.gesendet.append(500)
        return h

    def test_ts10_netz_am_ende_jedes_requests(self):
        self._viewport_scheitern_lassen()

        def dispatch(**_kw):
            # Eine Schreibstelle ohne Schutz, die den Fehler weiterwirft.
            self.lc.execute(
                "INSERT INTO viewport_events (page_url, element_id, visible_ms, "
                "ts_enter, ts_leave, investigator_id) VALUES (?,?,?,?,?,?)",
                ("u", "p", 1, 1, 2, 1))

        h = self._handler(dispatch)
        with self.assertLogs(_lc_modul.logger, level="ERROR") as log:
            h._handle_request("POST")
        self.assertEqual(h.gesendet, [500])
        self.assertFalse(self.lc.in_transaction)
        self.assertIn("POST /_forensic/ts10", "\n".join(log.output))
        # Und danach kommt der Schreiber auf coordinator.db durch.
        self.lc.execute("SELECT wert FROM cdb.einstellung").fetchall()
        self._coordinator_schreiben()


if __name__ == "__main__":
    unittest.main()
