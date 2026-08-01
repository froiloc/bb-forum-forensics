# =============================================================================
# tests/test_issue_tracker_verweise.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# Testsuite fuer Build 642: die Verweise in 'related_to' und ihre Reparatur.
#
# DER BEFUND (gemessen am Bestand von Build 641, 104 Vorgaenge, 35 Verweise):
#   Fuenf Verweise stehen als 8-Zeichen-Kurzform in der Datei:
#     d79671f9 -> '651e6d84'
#     f51fd838 -> '906ede75', 'e9522fe2', 'c3f80e54'
#     88dc129b -> '906ede75'
#
#   server.py loest Verweise ueber exakte Gleichheit auf (view_issue: die
#   Liste 'related_issues' und die Rueckrichtung 'referencing_issues'). Eine
#   Kurzform trifft nie. Die Verweise stehen also in der Datei und werden in
#   der Ansicht STILLSCHWEIGEND nicht angezeigt - ein Beleg, den es gibt und
#   den niemand sieht. Genau das verbietet Grundregel 1.
#
# WAS DIESE SUITE PRUEFT UND WAS NICHT: Sie prueft das Werkzeug und sie prueft
#   den LIVE-BESTAND daraufhin, dass jeder Mangel dort AUFLOESBAR ist. Sie
#   verlangt NICHT, dass der Bestand mangelfrei ist - das waere ab Build 642
#   rot, weil die fuenf Eintraege noch drinstehen und die Reparatur
#   ausdruecklich von Hand ausgeloest wird (Entscheidung mc, 2026-08-01:
#   'Pruefung + Reparaturwerkzeug', issues.json wird von Claude nicht
#   angefasst). Die Sperre gegen NEUE Kurzformen sitzt im Validator von
#   merge.py und wird in tests/test_issue_tracker_merge.py geprueft (MG03).
#
# RR01 - der Trockenlauf findet die Maengel und aendert nichts.
# RR02 - '--apply' loest auf, sichert vorher und laesst den Rest in Ruhe.
# RR03 - ein mehrdeutiger Verweis wird NICHT geraten, sondern gemeldet.
# RR04 - ein unbekannter Verweis wird gemeldet, nicht entfernt.
# RR05 - eine volle UUID auf einen geloeschten Vorgang gilt als unbekannt.
# RR06 - ohne Mangel wird nicht geschrieben (keine leere Sicherung).
# RR07 - LIVE-BESTAND: jeder vorhandene Mangel ist eindeutig aufloesbar.
#
# Version: v0.8.642 - Build: 642 - 2026-08-01
# =============================================================================

import json
import sys
import tempfile
import unittest
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
TRACKER = WURZEL / "issue-tracker"
LIVE = TRACKER / "data" / "issues.json"

if str(TRACKER) not in sys.path:
    sys.path.insert(0, str(TRACKER))

from related_id_repair import (  # noqa: E402
    BEFUND_AUFLOESBAR,
    BEFUND_MEHRDEUTIG,
    BEFUND_UNBEKANNT,
    RelatedIdRepair,
)

#: Zwei Vorgaenge, deren Kurzformen sich unterscheiden - und zwei, deren
#: Kurzformen im ersten Zeichen uebereinstimmen (fuer den Mehrdeutigkeitsfall).
A = "aaaaaaaa-0000-4000-8000-000000000000"
B = "bbbbbbbb-0000-4000-8000-000000000000"
B2 = "bbbbbbbb-1111-4000-8000-000000000000"
FEHLT = "ffffffff-0000-4000-8000-000000000000"


def _vorgang(kennung: str, verweise=None) -> dict:
    return {
        "id": kennung,
        "type": "bug",
        "title": f"Prüfvorgang {kennung[:8]}",
        "affected_version": "0.8.642",
        "reporter": "Testlauf",
        "reported_at": "2026-08-01T12:00:00+00:00",
        "status": "open",
        "related_to": list(verweise or []),
        "updates": [],
    }


class ReparaturGrundgeruest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.arbeit = Path(self._tmp.name)
        (self.arbeit / "data").mkdir()
        self.ziel = self.arbeit / "data" / "issues.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _bestand(self, vorgaenge):
        self.ziel.write_text(
            json.dumps({"issues": vorgaenge}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return RelatedIdRepair(self.ziel)

    def _lesen(self):
        return json.loads(self.ziel.read_text(encoding="utf-8"))["issues"]


class TestTrockenlauf(ReparaturGrundgeruest):

    def test_rr01_findet_und_aendert_nichts(self):
        reparatur = self._bestand([_vorgang(A, ["bbbbbbbb"]), _vorgang(B)])
        vorher = self.ziel.read_bytes()

        bericht = reparatur.pruefen()

        self.assertEqual(bericht.geprueft, 1)
        self.assertEqual(len(bericht.aufloesbar), 1)
        self.assertEqual(bericht.aufloesbar[0].ziel_id, B)
        self.assertFalse(bericht.angewendet)
        self.assertEqual(self.ziel.read_bytes(), vorher,
                         "Der Trockenlauf hat die Datei veraendert")


class TestAnwenden(ReparaturGrundgeruest):

    def test_rr02_loest_auf_und_sichert_vorher(self):
        reparatur = self._bestand([
            _vorgang(A, ["bbbbbbbb", B]),   # eine Kurzform, eine volle UUID
            _vorgang(B),
        ])

        bericht = reparatur.anwenden()

        self.assertTrue(bericht.angewendet)
        bestand = {v["id"]: v for v in self._lesen()}
        self.assertEqual(bestand[A]["related_to"], [B, B],
                         "Die Kurzform wurde nicht auf die volle UUID gebracht")

        # Die Sicherung muss den Stand VORHER enthalten.
        self.assertIsNotNone(bericht.sicherung)
        self.assertTrue(bericht.sicherung.exists())
        gesichert = json.loads(bericht.sicherung.read_text(encoding="utf-8"))["issues"]
        self.assertEqual(gesichert[0]["related_to"], ["bbbbbbbb", B],
                         "Die Sicherung enthaelt bereits den reparierten Stand")

        # Sie gehoert neben das Datenverzeichnis, nicht irgendwohin.
        self.assertEqual(bericht.sicherung.parent, self.arbeit / "backups")

    def test_rr03_mehrdeutiges_wird_nicht_geraten(self):
        reparatur = self._bestand([
            _vorgang(A, ["bbbbbbbb"]),
            _vorgang(B), _vorgang(B2),
        ])

        bericht = reparatur.anwenden()

        mehrdeutig = bericht.nach_befund(BEFUND_MEHRDEUTIG)
        self.assertEqual(len(mehrdeutig), 1)
        self.assertEqual(mehrdeutig[0].kandidaten, sorted([B, B2]))
        self.assertEqual(self._lesen()[0]["related_to"], ["bbbbbbbb"],
                         "Ein mehrdeutiger Verweis wurde veraendert - das waere "
                         "geraten, und ein falscher Verweis ist schlimmer als "
                         "ein fehlender")

    def test_rr04_unbekanntes_bleibt_stehen(self):
        reparatur = self._bestand([_vorgang(A, ["99999999"]), _vorgang(B)])

        bericht = reparatur.anwenden()

        self.assertEqual(len(bericht.nach_befund(BEFUND_UNBEKANNT)), 1)
        self.assertEqual(self._lesen()[0]["related_to"], ["99999999"],
                         "Ein unbekannter Verweis wurde entfernt - Belege "
                         "verschwinden nicht, sie werden gemeldet")

    def test_rr05_volle_uuid_ohne_vorgang_gilt_als_unbekannt(self):
        reparatur = self._bestand([_vorgang(A, [FEHLT]), _vorgang(B)])

        bericht = reparatur.pruefen()

        self.assertEqual(len(bericht.nach_befund(BEFUND_UNBEKANNT)), 1,
                         "Ein Verweis ins Leere wurde als 'ok' durchgewinkt")

    def test_rr06_ohne_mangel_wird_nicht_geschrieben(self):
        reparatur = self._bestand([_vorgang(A, [B]), _vorgang(B)])
        vorher = self.ziel.read_bytes()

        bericht = reparatur.anwenden()

        self.assertFalse(bericht.angewendet)
        self.assertIsNone(bericht.sicherung,
                          "Ohne Aenderung wurde eine Sicherung angelegt")
        self.assertEqual(self.ziel.read_bytes(), vorher)
        self.assertFalse((self.arbeit / "backups").exists())


class TestLiveBestand(unittest.TestCase):
    """RR07 - die Aussage ueber den echten Bestand."""

    def test_rr07_jeder_mangel_ist_aufloesbar(self):
        if not LIVE.exists():
            self.skipTest("issue-tracker/data/issues.json nicht vorhanden.")

        bericht = RelatedIdRepair(LIVE).pruefen()

        nicht_entscheidbar = bericht.offen
        self.assertEqual(
            nicht_entscheidbar, [],
            "Im Bestand stehen Verweise, die das Werkzeug NICHT aufloesen kann "
            "- sie muessen von Hand geklaert werden: "
            + "; ".join(f"{b.quelle_id[:8]}->{b.verweis!r} ({b.befund})"
                        for b in nicht_entscheidbar)
        )

        # Kein Anspruch auf Mangelfreiheit (siehe Kopf), aber die Zahl wird
        # ausgewiesen: wer sie liest, sieht, ob die Reparatur schon lief.
        offen = len(bericht.nach_befund(BEFUND_AUFLOESBAR))
        self.assertGreaterEqual(bericht.geprueft, offen)


if __name__ == "__main__":
    unittest.main()
