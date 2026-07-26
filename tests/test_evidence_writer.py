# =============================================================================
# tests/test_evidence_writer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Testsuite fuer Build 533: EvidenceWriter — das Write+Beleg-Gateway auf
# evidence_<uid>.db.
#
# Die Klasse existiert, weil CoordinatorWriter fuer diese Datei nicht taugt
# (andere Datei, andere Transaktion — die Garantie "beide oder keins" waere
# weg). Sie arbeitet auf der GETEILTEN Verbindung des forensischen Servers und
# muss dabei drei Dinge leisten, die CoordinatorWriter nicht leisten muss.
# Genau die werden hier geprueft:
#
#   EW01 — Der Normalfall: Fachzeile und Beleg liegen nach einem Aufruf beide
#          vor, und die Kette verifiziert.
#   EW02 — ATOMARITAET: wirft do_write, bleibt WEDER Fachzeile NOCH Beleg.
#          Das ist die Eigenschaft, derentwegen die Kette ueberhaupt in dieser
#          Datei liegt.
#   EW03 — ATOMARITAET auch rueckwaerts: wirft after_audit — also NACH dem
#          Beleg —, wird trotzdem alles zurueckgerollt.
#   EW04 — Ein unbekannter Ereignistyp wird abgewiesen, und es bleibt nichts
#          zurueck (die Pruefung liegt in EvidenceAuditLog.append).
#   EW05 — OHNE HANDELNDEN WIRD NICHTS GESCHRIEBEN, und die Ablehnung erfolgt
#          VOR jedem Datenbankzugriff.
#   EW06 — DIE EIGENTLICHE NEUERUNG: auf einer LockingConnection wird deren
#          oeffentlicher Lock fuer die GESAMTE Transaktion gehalten. Geprueft
#          wird die WIRKUNG — ein zweiter Thread kommt waehrend der
#          Transaktion nicht dazwischen.
#   EW07 — isolation_level wird GELIEHEN, nicht genommen: nach dem Aufruf hat
#          die Verbindung wieder ihren alten Wert, auch im Fehlerfall.
#   EW08 — Ist auf der Verbindung bereits eine fremde Transaktion offen, wird
#          LAUT abgebrochen statt sie ungefragt festzuschreiben.
#
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.locking_connection import LockingConnection                 # noqa: E402
from management.audit.evidence_audit_log import (                   # noqa: E402
    EvidenceAuditLog, EvidenceAuditLogError,
)
from management.audit.event_types import EventType                  # noqa: E402
from management.gateway.evidence_writer import (                    # noqa: E402
    EvidenceWriteError, EvidenceWriter,
)

_FACH = """
CREATE TABLE "fach" (
    "id"   INTEGER PRIMARY KEY AUTOINCREMENT,
    "wert" TEXT NOT NULL
)
"""


class TestEvidenceWriter(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.pfad = self.dir / "evidence_4711.db"
        roh = sqlite3.connect(str(self.pfad), check_same_thread=False)
        roh.row_factory = sqlite3.Row
        roh.execute(_FACH)
        EvidenceAuditLog.create_schema(roh)
        EvidenceAuditLog(roh).write_genesis({"db": "evidence", "schema": "test"})
        roh.commit()
        self.roh = roh
        self.con = roh                      # Standard: rohe Verbindung
        self.writer = EvidenceWriter(self.con)

    def tearDown(self):
        try:
            self.roh.close()
        except sqlite3.Error:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def _zaehle(self, tabelle):
        return self.roh.execute(
            'SELECT COUNT(*) AS c FROM "%s"' % tabelle).fetchone()["c"]

    # ===================================================================== EW01
    def test_EW01_write_und_beleg_liegen_beide_vor(self):
        def _w(con):
            con.execute('INSERT INTO "fach" ("wert") VALUES (?)', ("a",))
            return {"wert": "a"}

        seq = self.writer.audited_write(
            do_write=_w, event_type=EventType.TATZEIT_SET, actor_id=7,
            target_type="annotation", target_id="1")

        self.assertEqual(seq, 2)                    # 1 = Genesis
        self.assertEqual(self._zaehle("fach"), 1)
        beleg = self.roh.execute(
            "SELECT event_type, actor_id, target_id FROM evidence_audit_log "
            "WHERE seq = 2").fetchone()
        self.assertEqual(beleg["event_type"], EventType.TATZEIT_SET)
        self.assertEqual(int(beleg["actor_id"]), 7)
        self.assertEqual(beleg["target_id"], "1")
        self.assertTrue(EvidenceAuditLog(self.roh).verify_chain().ok)

    # ===================================================================== EW02
    def test_EW02_fehler_im_write_laesst_nichts_zurueck(self):
        def _w(con):
            con.execute('INSERT INTO "fach" ("wert") VALUES (?)', ("b",))
            raise RuntimeError("Absicht")

        with self.assertRaises(RuntimeError):
            self.writer.audited_write(
                do_write=_w, event_type=EventType.TATZEIT_SET, actor_id=7,
                target_type="annotation", target_id="1")

        self.assertEqual(self._zaehle("fach"), 0,
                         "Die Fachzeile blieb trotz Fehler zurueck.")
        self.assertEqual(self._zaehle("evidence_audit_log"), 1,
                         "Es blieb ein Beleg ohne Fachzeile zurueck.")

    # ===================================================================== EW03
    def test_EW03_fehler_nach_dem_beleg_rollt_alles_zurueck(self):
        def _w(con):
            con.execute('INSERT INTO "fach" ("wert") VALUES (?)', ("c",))
            return {"wert": "c"}

        def _nach(con, seq):
            raise RuntimeError("Absicht nach dem Beleg")

        with self.assertRaises(RuntimeError):
            self.writer.audited_write(
                do_write=_w, event_type=EventType.TATZEIT_SET, actor_id=7,
                target_type="annotation", target_id="1", after_audit=_nach)

        self.assertEqual(self._zaehle("fach"), 0)
        self.assertEqual(self._zaehle("evidence_audit_log"), 1,
                         "Der Beleg wurde geschrieben, obwohl der Vorgang "
                         "scheiterte — keine stille Teil-Persistenz.")

    # ===================================================================== EW04
    def test_EW04_unbekannter_ereignistyp_wird_abgewiesen(self):
        def _w(con):
            con.execute('INSERT INTO "fach" ("wert") VALUES (?)', ("d",))
            return {}

        with self.assertRaises(EvidenceAuditLogError):
            self.writer.audited_write(
                do_write=_w, event_type="tatzeit_erfunden", actor_id=7,
                target_type="annotation", target_id="1")
        self.assertEqual(self._zaehle("fach"), 0)
        self.assertEqual(self._zaehle("evidence_audit_log"), 1)

    # ===================================================================== EW05
    def test_EW05_ohne_handelnden_wird_nichts_geschrieben(self):
        aufgerufen = {"ja": False}

        def _w(con):
            aufgerufen["ja"] = True
            return {}

        with self.assertRaises(EvidenceWriteError) as ctx:
            self.writer.audited_write(
                do_write=_w, event_type=EventType.TATZEIT_SET, actor_id=None,
                target_type="annotation", target_id="1")
        self.assertIn("ohne Handelnden", str(ctx.exception))
        self.assertFalse(aufgerufen["ja"],
                         "do_write wurde trotz fehlendem Handelnden gerufen — "
                         "die Ablehnung muss VOR jedem Zugriff kommen.")
        self.assertEqual(self._zaehle("fach"), 0)

    # ===================================================================== EW06
    def test_EW06_lock_wird_ueber_die_ganze_transaktion_gehalten(self):
        """
        Die eigentliche Neuerung gegenueber CoordinatorWriter.

        Geprueft wird die WIRKUNG, nicht die Existenz eines Locks: waehrend
        die Transaktion laeuft, versucht ein zweiter Thread, denselben Lock zu
        nehmen. Gelingt ihm das VOR dem Commit, ist die Serialisierung
        wirkungslos — dann koennte sich in echt ein zweiter Request zwischen
        BEGIN IMMEDIATE und COMMIT schieben.
        """
        lc = LockingConnection(self.roh)
        writer = EvidenceWriter(lc)

        fremder_war_drin = threading.Event()
        transaktion_laeuft = threading.Event()

        def _fremder():
            transaktion_laeuft.wait(timeout=5)
            # blockiert, solange der Writer den Lock haelt
            with lc.lock:
                fremder_war_drin.set()

        t = threading.Thread(target=_fremder, daemon=True)
        t.start()

        def _w(con):
            transaktion_laeuft.set()
            # Dem fremden Thread reichlich Gelegenheit geben.
            time.sleep(0.25)
            self.assertFalse(
                fremder_war_drin.is_set(),
                "Ein zweiter Thread kam MITTEN in die Transaktion — der Lock "
                "wird nicht ueber die ganze Transaktion gehalten.")
            con.execute('INSERT INTO "fach" ("wert") VALUES (?)', ("e",))
            return {"wert": "e"}

        writer.audited_write(
            do_write=_w, event_type=EventType.TATZEIT_SET, actor_id=7,
            target_type="annotation", target_id="1")

        t.join(timeout=5)
        self.assertTrue(fremder_war_drin.is_set(),
                        "Der Lock wurde nach der Transaktion nicht "
                        "freigegeben.")
        self.assertEqual(self._zaehle("fach"), 1)

    # ===================================================================== EW07
    def test_EW07_isolation_level_wird_zurueckgegeben(self):
        """
        Die Verbindung gehoert dem Server, nicht dem Writer. Rund 150 Stellen
        (u. a. db/evidence_db.py:947) verlassen sich auf das Standardverhalten.
        """
        vorher = self.roh.isolation_level

        self.writer.audited_write(
            do_write=lambda con: con.execute(
                'INSERT INTO "fach" ("wert") VALUES (?)', ("f",)) and None,
            event_type=EventType.TATZEIT_SET, actor_id=7,
            target_type="annotation", target_id="1")
        self.assertEqual(self.roh.isolation_level, vorher)

        # Und auch, wenn es schiefgeht.
        def _w(con):
            raise RuntimeError("Absicht")

        with self.assertRaises(RuntimeError):
            self.writer.audited_write(
                do_write=_w, event_type=EventType.TATZEIT_SET, actor_id=7,
                target_type="annotation", target_id="1")
        self.assertEqual(self.roh.isolation_level, vorher,
                         "Nach einem Fehler blieb isolation_level verstellt — "
                         "damit waere das Transaktionsverhalten des ganzen "
                         "Servers still veraendert.")

    # ===================================================================== EW08
    def test_EW08_fremde_offene_transaktion_bricht_laut_ab(self):
        """
        Das Setzen von isolation_level committet eine offene Transaktion
        IMPLIZIT. Waere hier keine Pruefung, schriebe der Writer einem anderen
        Vorgang ungefragt dessen Arbeit fest.
        """
        self.roh.execute('INSERT INTO "fach" ("wert") VALUES (?)', ("offen",))
        self.assertTrue(self.roh.in_transaction)

        with self.assertRaises(EvidenceWriteError) as ctx:
            self.writer.audited_write(
                do_write=lambda con: {}, event_type=EventType.TATZEIT_SET,
                actor_id=7, target_type="annotation", target_id="1")
        self.assertIn("bereits eine Transaktion offen", str(ctx.exception))

        # Die fremde Transaktion ist UNANGETASTET — weder committet noch
        # zurueckgerollt.
        self.assertTrue(self.roh.in_transaction)
        self.roh.rollback()
        self.assertEqual(self._zaehle("fach"), 0)


if __name__ == "__main__":
    unittest.main()
