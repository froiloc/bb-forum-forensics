# =============================================================================
# tests/test_review_comment_view.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# Build 661 — Vorgang a84766a7 (Editor-Lesepfad der Kommentar-Bruecke)
# =============================================================================
# Deckt ab: forensic_api/review_comment_view.py und die Haertung von
#           management/reports/review_comment_reader.py.
#
#   RV01 — Zuordnung je Block, aufsteigend nach created_at.
#   RV02 — Positivliste: NUR die benannten Felder wandern in den Editor.
#          Eine Spalte, die spaeter in der Addendum-Datei hinzukommt, gelangt
#          nicht ungeprueft in eine zweite Oberflaeche (Fallregel 3).
#   RV03 — ANKERLOSE Anmerkungen verschwinden nicht: sie stehen in
#          ohne_block() mit grund='ohne_anker'.
#   RV04 — Ein Anker auf einen geloeschten Baustein verschwindet ebenso wenig:
#          grund='block_unbekannt'. DAS IST DER KERN VON GRUNDREGEL 1 HIER —
#          der Kommentar liegt in einer FREMDEN Datei und weiss nichts davon,
#          dass sein Baustein entfernt wurde.
#   RV05 — Nicht lesbare Addendum-Dateien werden durchgereicht.
#   RV06 — Leere Eingaben und Unsinn (None, keine Mapping-Objekte) fuehren
#          nicht zum Absturz.
#   RC10 — read_mit_befund(): eine defekte Addendum-Datei wird GEMELDET und
#          nicht als 'keine Kommentare' getarnt. GEGENPROBE ZU BUILD 660:
#          read() lieferte dort dieselbe leere Liste wie bei einer Person
#          ohne Anmerkungen.
#   RC11 — read() bleibt rueckwaertskompatibel (der Cockpit-Aufrufer).
#
# Version: v0.8.661 · Build: 661 · 2026-08-02
# =============================================================================

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forensic_api.review_comment_view import ReviewCommentView, FELDER
from management.reports.review_comment_reader import ReviewCommentReader
from db.review_addendum_db import open_addendum, addendum_path


def _k(cid, block_id, ts, **kw):
    z = {"comment_id": cid, "report_id": 1, "block_id": block_id,
         "reviewer_pid": 1, "reviewer_role": "lector",
         "comment_text": "Anmerkung " + cid, "suggested_content": None,
         "status": "pending", "block_sha256": None,
         "created_at": ts, "resolved_at": None}
    z.update(kw)
    return z


class ReviewCommentViewTests(unittest.TestCase):

    # RV01 -------------------------------------------------------------------
    def test_rv01_zuordnung_und_reihenfolge(self):
        v = ReviewCommentView([
            _k("c3", "b1", 300), _k("c1", "b1", 100), _k("c2", "b2", 200),
        ])
        je = v.je_block(["b1", "b2"])
        self.assertEqual([c["comment_id"] for c in je["b1"]], ["c1", "c3"])
        self.assertEqual([c["comment_id"] for c in je["b2"]], ["c2"])
        self.assertEqual(v.anzahl(), 3)

    # RV02 -------------------------------------------------------------------
    def test_rv02_positivliste(self):
        roh = _k("c1", "b1", 100)
        roh["interne_notiz"] = "GEHT NIEMANDEN AN"
        je = ReviewCommentView([roh]).je_block(["b1"])
        self.assertEqual(set(je["b1"][0].keys()), set(FELDER))
        self.assertNotIn("interne_notiz", je["b1"][0])

    # RV03 -------------------------------------------------------------------
    def test_rv03_ankerlos_bleibt_sichtbar(self):
        v = ReviewCommentView([_k("c1", None, 100), _k("c2", "", 110),
                               _k("c3", "b1", 120)])
        je = v.je_block(["b1"])
        self.assertEqual(len(je.get("b1", [])), 1)
        heimatlos = v.ohne_block(["b1"])
        self.assertEqual([c["comment_id"] for c in heimatlos], ["c1", "c2"])
        self.assertTrue(all(c["grund"] == "ohne_anker" for c in heimatlos))

    # RV04 -------------------------------------------------------------------
    def test_rv04_geloeschter_baustein(self):
        """Der Kommentar liegt in einer FREMDEN Datei und weiss nichts davon,
        dass sein Baustein entfernt wurde. Er darf nicht verschwinden."""
        v = ReviewCommentView([_k("c1", "b_weg", 100), _k("c2", "b1", 110)])
        je = v.je_block(["b1"])
        self.assertNotIn("b_weg", je)
        heimatlos = v.ohne_block(["b1"])
        self.assertEqual(len(heimatlos), 1)
        self.assertEqual(heimatlos[0]["comment_id"], "c1")
        self.assertEqual(heimatlos[0]["grund"], "block_unbekannt")
        # Zusammen ergibt beides wieder die volle Menge - nichts faellt raus.
        self.assertEqual(sum(len(x) for x in je.values()) + len(heimatlos),
                         v.anzahl())

    # RV05 -------------------------------------------------------------------
    def test_rv05_fehler_werden_durchgereicht(self):
        v = ReviewCommentView([], [{"datei": "evidence_700_4.db",
                                    "grund": "nicht zu oeffnen: x"}])
        self.assertEqual(len(v.fehler()), 1)
        self.assertEqual(v.fehler()[0]["datei"], "evidence_700_4.db")

    # RV06 -------------------------------------------------------------------
    def test_rv06_robust(self):
        v = ReviewCommentView(None, None)
        self.assertEqual(v.je_block([]), {})
        self.assertEqual(v.ohne_block([]), [])
        self.assertEqual(v.fehler(), [])
        self.assertEqual(v.anzahl(), 0)
        # Unsinn in der Liste wird uebergangen, ohne zu werfen.
        v2 = ReviewCommentView(["kein dict", 42, _k("c1", "b1", 1)])
        self.assertEqual(v2.anzahl(), 1)


class ReviewCommentReaderBefundTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.evidence_dir = os.path.join(self._tmp, "evidence")
        os.makedirs(self.evidence_dir, exist_ok=True)
        db = open_addendum(self.evidence_dir, 700, 1, create=True)
        try:
            db.add_comment(report_id=1, block_id="b1", reviewer_role="lector",
                           comment_text="Bitte praezisieren",
                           suggested_content=None, block_sha256=None)
        finally:
            db.close()

    def tearDown(self):
        for root, dirs, files in os.walk(self._tmp, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(self._tmp)

    # RC10 -------------------------------------------------------------------
    def test_rc10_defekte_datei_wird_gemeldet(self):
        """GEGENPROBE ZU BUILD 660: dort lieferte read() bei einer defekten
        Datei dieselbe leere Liste wie bei einer Person ohne Anmerkungen —
        'nichts angemerkt' und 'nicht lesbar' waren nicht zu unterscheiden."""
        kaputt = addendum_path(self.evidence_dir, 700, 9)
        kaputt.parent.mkdir(parents=True, exist_ok=True)
        kaputt.write_bytes(b"kein SQLite")

        kommentare, fehler = ReviewCommentReader(
            self.evidence_dir, 700).read_mit_befund()
        # Die heile Datei wird trotzdem gelesen — ein Fehlschlag darf die
        # uebrigen Anmerkungen nicht mitnehmen.
        self.assertEqual(len(kommentare), 1)
        self.assertEqual(len(fehler), 1)
        self.assertEqual(fehler[0]["datei"], kaputt.name)
        self.assertTrue(fehler[0]["grund"])

    # RC11 -------------------------------------------------------------------
    def test_rc11_read_bleibt_rueckwaertskompatibel(self):
        r = ReviewCommentReader(self.evidence_dir, 700)
        self.assertEqual(len(r.read()), 1)
        self.assertEqual(r.read(1)[0]["block_id"], "b1")
        self.assertEqual(r.read(99), [])
        # Kein Verzeichnis -> leer, kein Fehler.
        leer = ReviewCommentReader(self.evidence_dir, 999)
        self.assertEqual(leer.read_mit_befund(), ([], []))


if __name__ == "__main__":
    unittest.main()
