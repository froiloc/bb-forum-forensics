# =============================================================================
# tests/test_templates_quelle_zustand.py
# IT-Forensisches Ermittlungswerkzeug — Zustand der templates.db
# =============================================================================
# Testsuite fuer Build 579.
#
# ANLASS (2026-07-30, Nachtest zu Build 578): mc benannte templates.db im
# laufenden Betrieb um. Erwartet war eine benannte Fehlermeldung; im Log stand
# aber 'GET /_forensic/templates ... 200'. Die Ursache lag NICHT dort, wo
# Build 578 sie vermutet hatte:
#
#   A) Jede Lesemethode von TemplatesDb faengt sqlite3.OperationalError und
#      gibt [] zurueck. Die Huelle aus Build 578 bekam nie eine Ausnahme zu
#      sehen. Eine fehlende Datenbank ergab eine LEERE LISTE mit HTTP 200 -
#      ununterscheidbar von 'es sind keine Vorlagen angelegt'.
#   B) _available wurde EINMALIG beim Init geprueft; eine Datei, die im
#      Betrieb verschwindet, blieb unsichtbar.
#   C) Die Protokollmeldung RIET die Ursache ('Seed-Skript noch nicht
#      gelaufen') und schickte die Fehlersuche in die falsche Richtung.
#
# TZ01 - zustand() meldet 'ok', wenn die Quelle lesbar ist.
# TZ02 - zustand() meldet 'nicht_angebunden', wenn tdb fehlt.
# TZ03 - DIE WICHTIGSTE: zustand() prueft FRISCH. Eine Quelle, die nach dem
#        Init verschwindet, wird erkannt (Befund B).
# TZ04 - der Endpunkt antwortet 503 mit benanntem Code statt 200 mit [].
# TZ05 - mit lesbarer Quelle bleibt alles beim Alten (200).
# TZ06 - eine Quelle ohne zustand() (aeltere Fassung) fuehrt NICHT zu einem
#        erfundenen Fehler - lieber die bisherige Auskunft.
# TZ07 - die Protokollmeldung raet nicht mehr auf eine einzelne Ursache.
#
# Version: v0.8.579 . Build: 579 . 2026-07-30
# =============================================================================

import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.templates_db import TemplatesDb
from forensic_api.templates_ep import TemplatesListEndpoint


class _Handler:
    def __init__(self):
        self.status = None
        self.body = None

    def send_response_body(self, status, body, content_type=None):
        self.status = status
        self.body = body


class _Bundle:
    def __init__(self, quelle):
        self.templates = quelle


def _con_mit_tdb():
    con = sqlite3.connect(":memory:")
    con.execute('ATTACH DATABASE ":memory:" AS tdb')
    con.execute("CREATE TABLE tdb.placeholders (id INTEGER)")
    con.execute(
        "CREATE TABLE tdb.report_templates (id INTEGER, template_key TEXT, "
        "title TEXT, description TEXT, report_type TEXT, blocks_json TEXT, "
        "sort_order INTEGER, is_active INTEGER)")
    return con


class ZustandTests(unittest.TestCase):

    # TZ01 ---------------------------------------------------------------
    def test_tz01_ok_bei_lesbarer_quelle(self):
        t = TemplatesDb(_con_mit_tdb())
        self.assertEqual(t.zustand(), (TemplatesDb.ZUSTAND_OK, ""))

    # TZ02 ---------------------------------------------------------------
    def test_tz02_nicht_angebunden(self):
        t = TemplatesDb(sqlite3.connect(":memory:"))
        art, meldung = t.zustand()
        self.assertEqual(art, TemplatesDb.ZUSTAND_NICHT_ANGEBUNDEN)
        self.assertIn("placeholders", meldung)

    # TZ03 ---------------------------------------------------------------
    def test_tz03_frisch_geprueft_nicht_gemerkt(self):
        """
        Befund B: _available wurde einmalig beim Init ermittelt. Genau deshalb
        blieb die im Betrieb umbenannte Datei unsichtbar. zustand() muss den
        JETZIGEN Zustand melden, nicht den von damals.
        """
        con = _con_mit_tdb()
        t = TemplatesDb(con)
        self.assertEqual(t.zustand()[0], TemplatesDb.ZUSTAND_OK)

        # Die Quelle verschwindet NACH dem Init.
        con.execute("DETACH DATABASE tdb")
        self.assertEqual(t.zustand()[0], TemplatesDb.ZUSTAND_NICHT_ANGEBUNDEN)
        # Das gemerkte Feld sagt weiterhin das Gegenteil - genau der Befund.
        self.assertTrue(t._available)

    # TZ04 ---------------------------------------------------------------
    def test_tz04_endpunkt_meldet_statt_leer_zu_liefern(self):
        ep = TemplatesListEndpoint(
            _Bundle(TemplatesDb(sqlite3.connect(":memory:"))), None, None)
        for pfad in ("/_forensic/templates",
                     "/_forensic/templates/full",
                     "/_forensic/templates/full/irgendwas",
                     "/_forensic/templates/7"):
            h = _Handler()
            ep.handle_get(h, pfad, {})
            self.assertEqual(h.status, 503, pfad)
            b = json.loads(h.body.decode("utf-8"))
            self.assertEqual(b["code"], "DB_UNAVAILABLE")
            self.assertEqual(b["datenbank"], "templates.db")
            # KEIN Dateipfad in der Antwort (der steht im Protokoll).
            self.assertNotIn("/", b.get("ursache", ""))

    # TZ05 ---------------------------------------------------------------
    def test_tz05_mit_quelle_bleibt_alles_beim_alten(self):
        ep = TemplatesListEndpoint(_Bundle(TemplatesDb(_con_mit_tdb())),
                                   None, None)
        h = _Handler()
        ep.handle_get(h, "/_forensic/templates/full", {})
        self.assertEqual(h.status, 200)
        self.assertEqual(json.loads(h.body.decode("utf-8")), [])

    # TZ06 ---------------------------------------------------------------
    def test_tz06_aeltere_quelle_erzeugt_keinen_fehler(self):
        """Eine Quelle ohne zustand() darf nicht als kaputt gelten - lieber
        die bisherige Auskunft als ein erfundener Fehler."""
        class Alt:
            def list_templates(self, search=None):
                return []

        ep = TemplatesListEndpoint(_Bundle(Alt()), None, None)
        h = _Handler()
        ep.handle_get(h, "/_forensic/templates/full", {})
        self.assertEqual(h.status, 200)

    # TZ07 ---------------------------------------------------------------
    def test_tz07_protokoll_raet_nicht_mehr(self):
        """
        Befund C: die alte Meldung behauptete 'Vermutlich ist das Seed-Skript
        noch nicht gelaufen' - am 2026-07-30 war das falsch und hat die
        Fehlersuche in die Irre geschickt.
        """
        quelle = Path(__file__).resolve().parent.parent / "db" / "templates_db.py"
        text = quelle.read_text(encoding="utf-8")
        self.assertNotIn("Vermutlich \\nist das Seed-Skript", text)
        self.assertIn("Moegliche", text)
        self.assertIn("nicht (mehr) am erwarteten Ort", text)


class ZustandGenauerTests(unittest.TestCase):
    """
    Build 582: DREI Faelle statt zwei.

    Befund mc (2026-07-30): die Meldung aus Build 579 lautete 'no such table:
    tdb.placeholders' - waehrend die Datei vorlag, der Pfad stimmte und ein
    Neustart nicht half. Die Meldung klang nach 'Datenbank fehlt' und schickte
    die Suche in die falsche Richtung. Der Unterschied, auf den es ankommt:
    ist die Datei nicht angebunden (Datei/Pfad), oder ist sie angebunden und
    nur die Kerntabelle fehlt (Migration nicht gelaufen)?

    TG01 - nicht angebunden -> 'nicht_angebunden', Meldung nennt Datei/Pfad.
    TG02 - angebunden ohne Kerntabelle -> 'fehler', Meldung nennt die
           Migration; die ALTE Tabelle wird ausdruecklich erkannt.
    TG03 - die vorhandenen Tabellen stehen in der Meldung (Diagnosewert).
    TG04 - die Massnahme erreicht die HTTP-Antwort, nicht nur das Protokoll.
    """

    def _con_alt(self):
        con = sqlite3.connect(":memory:")
        con.execute('ATTACH DATABASE ":memory:" AS tdb')
        con.execute("CREATE TABLE tdb.placeholder_queries (id INTEGER)")
        con.execute("CREATE TABLE tdb.report_modules (id INTEGER)")
        return con

    # TG01 ---------------------------------------------------------------
    def test_tg01_nicht_angebunden_nennt_datei_und_pfad(self):
        art, meldung = TemplatesDb(sqlite3.connect(":memory:")).zustand()
        self.assertEqual(art, TemplatesDb.ZUSTAND_NICHT_ANGEBUNDEN)
        self.assertIn("nicht angebunden", meldung)
        self.assertIn("paths.templates_db", meldung)

    # TG02 ---------------------------------------------------------------
    def test_tg02_alte_tabelle_wird_erkannt(self):
        art, meldung = TemplatesDb(self._con_alt()).zustand()
        # NICHT 'nicht_angebunden' - die Datei ist ja da. Genau diese
        # Verwechslung hat die Fehlersuche gekostet.
        self.assertEqual(art, TemplatesDb.ZUSTAND_FEHLER)
        self.assertIn("angebunden", meldung)
        self.assertIn("placeholder_queries", meldung)
        self.assertIn("migrate_templates_placeholders.py", meldung)

    # TG03 ---------------------------------------------------------------
    def test_tg03_vorhandene_tabellen_werden_genannt(self):
        _, meldung = TemplatesDb(self._con_alt()).zustand()
        self.assertIn("report_modules", meldung)

    # TG04 ---------------------------------------------------------------
    def test_tg04_massnahme_steht_in_der_antwort(self):
        ep = TemplatesListEndpoint(_Bundle(TemplatesDb(self._con_alt())),
                                   None, None)
        h = _Handler()
        ep.handle_get(h, "/_forensic/templates", {})
        self.assertEqual(h.status, 503)
        b = json.loads(h.body.decode("utf-8"))
        # Eine Fehlermeldung, die nicht sagt, was zu tun ist, kostet genauso
        # viel Zeit wie gar keine.
        self.assertIn("massnahme", b)
        self.assertIn("migrate_templates_placeholders.py", b["massnahme"])


if __name__ == "__main__":
    unittest.main()
