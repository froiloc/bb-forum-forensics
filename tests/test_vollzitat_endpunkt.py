# =============================================================================
# tests/test_vollzitat_endpunkt.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Build 726)
# =============================================================================
# Testsuite fuer GET /_forensic/vollzitat.
#
# VE-P01 - liefert die Gruppe als JSON, gruppiert nach Quelle
# VE-P02 - die Feldnamen sind die der Datenklassen (kein zweites Vokabular)
# VE-P03 - unauswertbare Beleg-Nummern werden BENANNT, nicht verschluckt
# VE-P04 - eine Auslassung ueber der Obergrenze wird BENANNT (GR1)
# VE-P05 - eine leere Anfrage liefert eine leere Gruppe, keinen Fehler
# VE-P06 - der Endpunkt ist im Router verdrahtet und nur fuer GET/HEAD
# VE-P07 - GEGENPROBE: ohne 'ids' entsteht kein Unterblock
#
# Alle Inhalte sind erfunden.
#
# Version: v0.8.726 - Build: 726 - 2026-08-27
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forensic_api.vollzitat import MAX_BELEGE, VollzitatEndpoint
from tests.test_vollzitat import (          # Vorrichtungen wiederverwenden
    BODY, SEITEN_URL, _FakeEvidence, _FakeForensic, _ann, _con, _finder,
    _pfad, _sel,
)


class _FakeHandler:
    """Nimmt auf, was der Endpunkt senden wuerde."""

    def __init__(self):
        self.status = None
        self.content_type = None
        self.body = None

    def send_response_body(self, status, body, content_type="text/html",
                           extra_headers=None):
        self.status = status
        self.content_type = content_type
        self.body = body

    @property
    def json(self):
        return json.loads(self.body.decode("utf-8"))


class _FakeBundle:
    def __init__(self, evidence, forensic, con):
        self.evidence = evidence
        self.forensic = forensic
        self.connection = con


class VollzitatEndpunktTests(unittest.TestCase):

    def setUp(self):
        f = _finder()
        p0, p1 = _pfad(f, 0), _pfad(f, 1)
        annos = [
            _ann(4711, "CAT_LOCATION", _sel(p0, 27, 37, "Bad Honnef"),
                 "Ausgangsort.", "h0erm"),
            _ann(4712, "CAT_PERSON",
                 {"xpathStart": p1 + "/text()[1]", "offsetStart": 0,
                  "xpathEnd": p1 + "/b[1]/text()[1]", "offsetEnd": 6,
                  "textContent": "Mein Bruder"},
                 "Begleitperson.", "h0erm"),
        ]
        self.bundle = _FakeBundle(_FakeEvidence(annos), _FakeForensic(), _con())
        self.endpunkt = VollzitatEndpoint(self.bundle)

    def _ruf(self, **params):
        h = _FakeHandler()
        self.endpunkt.handle(h, {k: [v] for k, v in params.items()})
        return h

    # -- VE-P01 -------------------------------------------------------------
    def test_vep01_liefert_gruppe_als_json(self):
        h = self._ruf(ids="4711,4712", label="Ortsbezuege")
        self.assertEqual(200, h.status)
        self.assertIn("application/json", h.content_type)
        d = h.json
        self.assertEqual("Ortsbezuege", d["beschriftung"])
        self.assertEqual(2, d["beleg_anzahl"])
        self.assertEqual(1, d["quellen_anzahl"],
                         "Zwei Belege desselben Beitrags gehoeren in EINEN "
                         "Unterblock.")
        ub = d["unterbloecke"][0]
        self.assertIn("Beitrag zum Thema", ub["bezeichnung"])
        self.assertEqual(1710452820, ub["posted_ts"])
        self.assertIn("#p100", ub["link"])
        self.assertEqual(2, len(ub["befunde"]))
        self.assertEqual("KHK Bergmann", ub["befunde"][0]["ermittler"])

    # -- VE-P02 -------------------------------------------------------------
    def test_vep02_feldnamen_wie_die_datenklassen(self):
        d = self._ruf(ids="4711").json
        befund = d["unterbloecke"][0]["befunde"][0]
        for feld in ("nummer", "annotation_id", "kategorie", "kategorie_text",
                     "css_klasse", "farbe", "markierung", "notiz",
                     "ermittler", "name_quelle", "absatz_weg", "hinweis"):
            with self.subTest(feld=feld):
                self.assertIn(feld, befund)
        absatz = d["unterbloecke"][0]["absaetze"][0]
        for feld in ("html", "nummern", "ersatz"):
            with self.subTest(feld=feld):
                self.assertIn(feld, absatz)
        # Die Hinterlegung reist am Element mit - der Browser setzt sie nicht
        # ein zweites Mal aus einer eigenen Farbtafel.
        self.assertIn("background-color", absatz["html"])

    # -- VE-P03 -------------------------------------------------------------
    def test_vep03_unauswertbare_nummern_werden_benannt(self):
        d = self._ruf(ids="4711,abc,,4712").json
        self.assertEqual(1, d["quellen_anzahl"])
        text = " ".join(d["warnungen"])
        self.assertIn("abc", text)
        # Der Leerstring zwischen zwei Kommas ist kein Fehler, sondern
        # Schreibweise - er darf NICHT gemeldet werden, sonst verwaessert
        # jede Anfrage die Warnungsliste.
        self.assertNotIn("''", text)

    # -- VE-P04 -------------------------------------------------------------
    def test_vep04_auslassung_wird_benannt(self):
        viele = ",".join(str(4711 + i) for i in range(MAX_BELEGE + 5))
        d = self._ruf(ids=viele).json
        self.assertEqual(5, d["abgeschnitten"])
        text = " ".join(d["warnungen"])
        self.assertIn("5 weitere", text)
        self.assertIn("Bericht", text,
                      "Die Warnung muss sagen, dass die Akte vollstaendig "
                      "ist - sonst liest sie sich wie ein Datenverlust.")

    # -- VE-P05 -------------------------------------------------------------
    def test_vep05_leere_anfrage_ist_kein_fehler(self):
        h = self._ruf(ids="")
        self.assertEqual(200, h.status)
        d = h.json
        self.assertEqual(0, d["beleg_anzahl"])
        self.assertEqual([], d["unterbloecke"])

    # -- VE-P06 -------------------------------------------------------------
    def test_vep06_router_kennt_den_pfad(self):
        quelle = (Path(__file__).resolve().parent.parent
                  / "forensic_api" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn('url_path == "/_forensic/vollzitat"', quelle)
        # Nur lesende Verfahren - der Endpunkt schreibt nichts und braucht
        # deshalb auch keinen Lock (anders als /_forensic/editor/evidence).
        stelle = quelle.index('url_path == "/_forensic/vollzitat"')
        ausschnitt = quelle[stelle:stelle + 400]
        self.assertIn('method not in ("GET", "HEAD")', ausschnitt)
        self.assertIn("_get_vollzitat()", ausschnitt)

    # -- VE-P07 -------------------------------------------------------------
    def test_vep07_gegenprobe(self):
        """
        Ein Test, der nicht anschlagen kann, ist kein Test.

        Ohne 'ids' darf KEIN Unterblock entstehen - sonst belegte VE-P01 nur,
        dass der Endpunkt irgendetwas zurueckgibt.
        """
        d = self._ruf(ids="").json
        with self.assertRaises(IndexError):
            _ = d["unterbloecke"][0]


if __name__ == "__main__":
    unittest.main()
