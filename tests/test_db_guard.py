# =============================================================================
# tests/test_db_guard.py
# IT-Forensisches Ermittlungswerkzeug — Schutzhuelle fuer Datenendpunkte
# =============================================================================
# Testsuite fuer Build 578.
#
# ANLASS (2026-07-30): im Berichtseditor liessen sich Bausteine, Platzhalter
# und Vorlagen nicht laden; der Browser meldete NUR 'Failed to fetch'. Ursache
# war eine verschobene templates.db - der eigentliche Mangel aber die fehlende
# Fehlerbehandlung: die Ausnahme flog aus dem Handler, die Verbindung starb,
# und niemand erfuhr, was fehlt.
#
# DG01 - laeuft die Arbeit durch, mischt sich die Huelle NICHT ein.
# DG02 - ein Dateisystemfehler wird zu einer BENANNTEN 503-Antwort.
# DG03 - ein sqlite3-Fehler ebenso.
# DG04 - DIE WICHTIGSTE: ein PROGRAMMIERFEHLER wird NICHT gefangen. Eine zu
#        weite Huelle machte aus jedem Fehler 'Datenbank nicht erreichbar',
#        und wir wuerden Phantomen nachjagen.
# DG05 - der Dateipfad steht NICHT in der Antwort (nur im Protokoll).
# DG06 - die Antwort nennt Datenbank, Code und Ursache - genug zum Handeln.
#
# Version: v0.8.578 . Build: 578 . 2026-07-30
# =============================================================================

import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forensic_api.db_guard import (
    CODE_DB_UNAVAILABLE, db_fehler_koerper, geschuetzt,
)


class _Handler:
    """Minimaler Ersatz fuer den ForensicRequestHandler."""

    def __init__(self):
        self.status = None
        self.body = None
        self.ctype = None

    def send_response_body(self, status, body, content_type=None):
        self.status = status
        self.body = body
        self.ctype = content_type


class DbGuardTests(unittest.TestCase):

    def _koerper(self, h):
        return json.loads(h.body.decode("utf-8"))

    # DG01 ---------------------------------------------------------------
    def test_dg01_erfolg_bleibt_unberuehrt(self):
        h = _Handler()
        gerufen = []
        ok = geschuetzt(h, "templates.db", lambda: gerufen.append(1))
        self.assertTrue(ok)
        self.assertEqual(gerufen, [1])
        # Die Huelle antwortet NICHT selbst, wenn nichts schiefgeht.
        self.assertIsNone(h.status)

    # DG02 ---------------------------------------------------------------
    def test_dg02_fehlende_datei_wird_benannt(self):
        h = _Handler()

        def arbeit():
            raise FileNotFoundError("templates.db")

        ok = geschuetzt(h, "templates.db", arbeit, pfad="/pfad/templates.db")
        self.assertFalse(ok)
        # 503 und nicht 500: ein Zustand der Anlage, kein Programmfehler.
        # Und nicht 404: den Endpunkt gibt es sehr wohl.
        self.assertEqual(h.status, 503)
        b = self._koerper(h)
        self.assertEqual(b["code"], CODE_DB_UNAVAILABLE)
        self.assertEqual(b["datenbank"], "templates.db")
        self.assertEqual(b["ursache"], "FileNotFoundError")

    # DG03 ---------------------------------------------------------------
    def test_dg03_sqlite_fehler_wird_benannt(self):
        h = _Handler()

        def arbeit():
            raise sqlite3.OperationalError("unable to open database file")

        self.assertFalse(geschuetzt(h, "default.db", arbeit))
        self.assertEqual(h.status, 503)
        self.assertEqual(self._koerper(h)["ursache"], "OperationalError")

    # DG04 ---------------------------------------------------------------
    def test_dg04_programmierfehler_wird_NICHT_gefangen(self):
        """
        Der Kern der Entscheidung: die Huelle faengt AUSDRUECKLICH nur
        sqlite3.Error und OSError. Waere hier 'Exception' gefangen, wuerde
        jeder Tippfehler im Code als 'Datenbank nicht erreichbar' erscheinen -
        und die Fehlersuche liefe ins Leere.
        """
        h = _Handler()

        def arbeit():
            raise TypeError("falscher Typ")

        with self.assertRaises(TypeError):
            geschuetzt(h, "templates.db", arbeit)
        # Und die Huelle hat NICHT geantwortet.
        self.assertIsNone(h.status)

        h2 = _Handler()

        def arbeit2():
            raise KeyError("fehlender Schluessel")

        with self.assertRaises(KeyError):
            geschuetzt(h2, "templates.db", arbeit2)
        self.assertIsNone(h2.status)

    # DG05 ---------------------------------------------------------------
    def test_dg05_pfad_nicht_in_der_antwort(self):
        """
        Der Pfad ist fuer die Betriebsleitung, nicht fuer den Browser. Die
        Antwort muss zum Handeln genuegen, ohne Dateisystem-Innereien
        herauszugeben.
        """
        h = _Handler()
        geheim = "/srv/aiw/geheim/templates.db"

        def arbeit():
            raise OSError("kaputt")

        geschuetzt(h, "templates.db", arbeit, pfad=geheim)
        roh = h.body.decode("utf-8")
        self.assertNotIn(geheim, roh)
        self.assertNotIn("/srv/", roh)
        # Aber der Verweis auf das Protokoll steht da.
        self.assertIn("Serverprotokoll", roh)

    # DG06 ---------------------------------------------------------------
    def test_dg06_antwort_ist_maschinen_und_menschenlesbar(self):
        b = json.loads(db_fehler_koerper("templates.db",
                                         "FileNotFoundError").decode("utf-8"))
        for feld in ("error", "code", "datenbank", "ursache", "hinweis"):
            self.assertIn(feld, b)
        self.assertIn("templates.db", b["error"])


class ValidationRulesRoutingTests(unittest.TestCase):
    """
    Build 578: der Regel-Katalog war NIE verdrahtet.

    Diese Pruefungen stehen hier, weil sie dieselbe Wurzel haben wie die
    Schutzhuelle daneben: ein Fehlschlag, der nichts sagt. Die Klasse
    ValidationRulesEndpoint gab es seit Build 389 - instanziiert und verteilt
    wurde sie nie. Der Browser bekam 404, und validation_rules.js meldete
    brav, dass Formatregeln nun NICHT geprueft werden. Fuer die Redaktion
    hiess das: Formatfehler fallen erst beim Einreichen auf.

    VR01 - der Verteiler kennt die Adresse.
    VR02 - es gibt einen Lazy-Getter, und er baut die Klasse.
    VR03 - der Endpunkt antwortet mit 200 und einem 'rules'-Feld.
    """

    _API = Path(__file__).resolve().parent.parent / "forensic_api" / "__init__.py"

    # VR01 ---------------------------------------------------------------
    def test_vr01_verteiler_kennt_die_adresse(self):
        quelle = self._API.read_text(encoding="utf-8")
        self.assertIn('url_path == "/_forensic/validation_rules"', quelle,
                      "Der Datenendpunkt ist nicht verteilt - genau der "
                      "Fehler, den Build 493 schon einmal fuer drei Module "
                      "eingefangen hat.")

    # VR02 ---------------------------------------------------------------
    def test_vr02_getter_vorhanden(self):
        quelle = self._API.read_text(encoding="utf-8")
        self.assertIn("def _get_validation_rules_ep", quelle)
        self.assertIn("ValidationRulesEndpoint(self._config)", quelle)

    # VR03 ---------------------------------------------------------------
    def test_vr03_endpunkt_antwortet(self):
        from forensic_api.validation_rules_ep import ValidationRulesEndpoint

        class _Cfg:
            def get(self, *a, **k):
                return {}

        h = _Handler()
        ValidationRulesEndpoint(_Cfg()).handle_get(h)
        self.assertEqual(h.status, 200)
        b = json.loads(h.body.decode("utf-8"))
        self.assertIn("rules", b)


if __name__ == "__main__":
    unittest.main()
