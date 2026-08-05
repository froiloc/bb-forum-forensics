# =============================================================================
# tests/test_suche_gesamtzahl_und_titel.py
# IT-Forensisches Ermittlungswerkzeug — Suche (Build 676)
# =============================================================================
# Zwei Vorgaenge, die zusammengehoeren:
#
#   36dcdfd8 - 'total' war die Zahl der GELIEFERTEN Zeilen, nicht die der
#              Treffer. Bei limit=200 stand dort 200 - und ob das die
#              Trefferzahl war oder die erreichte Grenze, liess sich nicht
#              unterscheiden. In einem Werkzeug, dessen Zahlen in eine
#              Ermittlungsakte geraten, ist eine Grenze, die sich als
#              Trefferzahl ausgibt, eine falsche Angabe.
#
#   d76c412d - Der Freitextfilter des Servers durchsuchte nur die URL. Solange
#              das Kontext-Dropdown im Browser filterte, fiel das nicht auf -
#              der oertliche Filter sieht URL UND Titel an. Sobald die Suche
#              an den Server geht, verschwaende die Titelsuche STILL.
#
# Testfaelle:
#   SG01 - q trifft eine Seite ueber ihren TITEL, nicht nur ueber die URL.
#   SG02 - q trifft weiterhin ueber die URL (kein Rueckschritt).
#   SG03 - nur_zaehlen liefert die Trefferzahl VOR der Begrenzung.
#   SG04 - Zaehlung und Liste benutzen DIESELBEN Filter: ein q, das die Liste
#          verkleinert, verkleinert auch die Zahl.
#   SG05 - Der Endpunkt weist total, geliefert und begrenzt getrennt aus.
#   SG06 - Bleibt die Grenze unerreicht, ist 'begrenzt' falsch - der Fall, in
#          dem man der Zahl vertrauen darf.
#   SG07 - '-1' heisst 'nicht ermittelbar' und ist von 0 zu unterscheiden.
#          Ein Aufrufer, der beides gleich behandelt, meldet eine leere
#          Ergebnismenge, wo er 'unbekannt' melden muesste.
#
# Version: v0.8.676 - Build: 676 - 2026-08-05
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import reset_for_testing          # noqa: E402
from db.forensic_db import ForensicDb              # noqa: E402
from forensic_api.search import SearchEndpoint     # noqa: E402


def _bestand(seiten: list[tuple[str, str]]) -> sqlite3.Connection:
    """
    Baut einen Wegwerf-Bestand: fdb (Datei, weil ATTACH keine ':memory:'
    nimmt) mit pages, dazu die evidence-Tabellen in der Haupt-DB.

    seiten: (url_canonical, title)
    """
    fdb_pfad = tempfile.mktemp(suffix="_fdb.db")
    fdb = sqlite3.connect(fdb_pfad)
    fdb.executescript("""
        CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_canonical TEXT NOT NULL, html BLOB, title TEXT,
            fetched_at INTEGER NOT NULL DEFAULT 0,
            http_status INTEGER NOT NULL DEFAULT 200,
            scrape_context TEXT NOT NULL DEFAULT 'user',
            method TEXT NOT NULL DEFAULT 'GET',
            UNIQUE(url_canonical, method));
        CREATE TABLE page_aliases (
            url_raw TEXT NOT NULL PRIMARY KEY, page_id INTEGER NOT NULL);
        CREATE TABLE scrape_targets (
            id INTEGER PRIMARY KEY, scrape_context TEXT NOT NULL DEFAULT 'user',
            url_type TEXT NOT NULL, forum_id INTEGER, topic_id INTEGER,
            post_id INTEGER, pm_topic_id INTEGER, pm_post_id INTEGER,
            thanks_post_id INTEGER, poll_topic_id INTEGER,
            actor_user_id INTEGER, actor_username TEXT, static_url TEXT,
            source_tables TEXT NOT NULL DEFAULT '');
    """)
    for url, titel in seiten:
        fdb.execute("INSERT INTO pages (url_canonical, title, html) "
                    "VALUES (?,?,?)", (url, titel, b"<html></html>"))
    fdb.commit()
    fdb.close()

    haupt = sqlite3.connect(":memory:")
    haupt.row_factory = sqlite3.Row
    haupt.executescript("""
        CREATE TABLE annotations (
            id INTEGER PRIMARY KEY, page_url TEXT NOT NULL, element_id TEXT,
            category TEXT, text TEXT, ts INTEGER, investigator_id TEXT,
            local_id TEXT, tags_json TEXT, post_id INTEGER, created_by TEXT,
            selection_json TEXT);
        CREATE TABLE page_visits (
            id INTEGER PRIMARY KEY, page_url TEXT NOT NULL,
            scrape_context TEXT, ts INTEGER, investigator_id TEXT);
    """)
    haupt.execute("ATTACH DATABASE '%s' AS fdb" % fdb_pfad)
    haupt.commit()
    return haupt


SEITEN = [
    ("/forum/viewtopic.php?id=1", "Annual badge / LET'S TALK"),
    ("/forum/viewtopic.php?id=2", "hola juntos / Espanol"),
    ("/forum/viewtopic.php?id=3", "Ganz etwas anderes"),
    ("/forum/profile.php?id=9",   "Profil: Annual"),
]


class SucheGesamtzahlUndTitelTests(unittest.TestCase):

    def setUp(self):
        reset_for_testing()
        self.con = _bestand(SEITEN)
        self.db = ForensicDb.__new__(ForensicDb)
        self.db._con = self.con

    def tearDown(self):
        self.con.close()

    # -- SG01 -----------------------------------------------------------------
    def test_sg01_treffer_ueber_den_titel(self):
        """
        'badge' kommt in keiner URL vor, nur im Titel. Bis Build 675 fand der
        Server dafuer nichts - und genau das waere beim Umstellen der
        Kontextsuche still verlorengegangen.
        """
        treffer = self.db.search_pages(q="badge", limit=50)
        urls = [t["url"] for t in treffer]
        self.assertIn("/forum/viewtopic.php?id=1", urls,
                      "Der Titeltreffer fehlt: %s" % urls)

    # -- SG02 -----------------------------------------------------------------
    def test_sg02_treffer_ueber_die_url_bleibt(self):
        treffer = self.db.search_pages(q="profile.php", limit=50)
        self.assertEqual(["/forum/profile.php?id=9"],
                         [t["url"] for t in treffer])

    # -- SG03 -----------------------------------------------------------------
    def test_sg03_zaehlung_gilt_vor_der_begrenzung(self):
        alle = self.db.search_pages(limit=50)
        self.assertEqual(4, len(alle))

        begrenzt = self.db.search_pages(limit=2)
        self.assertEqual(2, len(begrenzt),
                         "Die Begrenzung muss weiterhin greifen.")

        gezaehlt = self.db.search_pages(limit=2, nur_zaehlen=True)
        self.assertEqual(
            4, gezaehlt,
            "Gezaehlt wird VOR der Begrenzung - sonst waere die Zahl wieder "
            "nur die Zahl der gelieferten Zeilen.")

    # -- SG04 -----------------------------------------------------------------
    def test_sg04_zaehlung_und_liste_filtern_gleich(self):
        """
        Zwei Abfragen mit zwei Wahrheiten waeren binnen zweier Builds
        auseinandergelaufen. Dieser Fall haelt sie zusammen.
        """
        for begriff in ("badge", "viewtopic", "gibtesnicht", ""):
            with self.subTest(q=begriff):
                liste = self.db.search_pages(q=begriff, limit=50)
                zahl = self.db.search_pages(q=begriff, limit=50,
                                            nur_zaehlen=True)
                self.assertEqual(len(liste), zahl,
                                 "q=%r: Liste %d, Zaehlung %d"
                                 % (begriff, len(liste), zahl))

    # -- SG05 / SG06 ----------------------------------------------------------
    def _endpunkt_antwort(self, params: dict) -> dict:
        bundle = MagicMock()
        bundle.forensic = self.db
        endpunkt = SearchEndpoint(bundle=bundle, context=MagicMock(),
                                  config=MagicMock())
        handler = MagicMock()
        aufgefangen = {}

        def merke(status, body, content_type=None):
            aufgefangen["status"] = status
            aufgefangen["body"] = json.loads(body.decode("utf-8"))

        handler.send_response_body = merke
        endpunkt.handle(handler, params)
        return aufgefangen

    def test_sg05_endpunkt_weist_die_drei_zahlen_getrennt_aus(self):
        antwort = self._endpunkt_antwort({"limit": ["2"]})
        self.assertEqual(200, antwort["status"])
        koerper = antwort["body"]
        self.assertEqual(4, koerper["total"],
                         "total ist die Trefferzahl VOR der Begrenzung.")
        self.assertEqual(2, koerper["geliefert"])
        self.assertEqual(2, len(koerper["pages"]))
        self.assertTrue(koerper["begrenzt"],
                        "Die Grenze hat gegriffen - das muss dranstehen.")

    def test_sg06_ohne_begrenzung_ist_begrenzt_falsch(self):
        koerper = self._endpunkt_antwort({"limit": ["50"]})["body"]
        self.assertEqual(4, koerper["total"])
        self.assertEqual(4, koerper["geliefert"])
        self.assertFalse(koerper["begrenzt"],
                         "Ohne erreichte Grenze darf 'begrenzt' nicht wahr "
                         "sein - sonst warnt die Oberflaeche grundlos.")

    # -- SG08 -----------------------------------------------------------------
    def test_sg08_zaehlung_verbindet_scrape_targets_nicht(self):
        """
        BUILD 677, gemessen am 05.08.2026 in der VM.

        Bei einem grossen Fall (Administrator, >10.000 Beitraege, 800 MB)
        brauchte die Zaehlung rund eine MINUTE. Ursache: die Verbindung zu
        fdb.scrape_targets verknuepft jede Seite mit jedem Erfassungsziel
        ueber ein LIKE ohne Anker - bei 6.500 Seiten und 19.000 Zielen sind
        das ueber 120 Millionen Zeichenkettenvergleiche fuer EINE Zahl.

        Gebraucht wird sie dafuer nicht: sie liefert allein 'trace_count',
        und in keiner Bedingung kommt sie vor. Dieser Fall haelt fest, dass
        sie in der Zaehlabfrage auch kuenftig nicht auftaucht - der Gewinn
        waere sonst beim naechsten Umbau still wieder verloren.
        """
        gesehene = []

        class Mitschrift:
            def __init__(self, echt):
                self._echt = echt

            def execute(self, sql, *args, **kwargs):
                gesehene.append(sql)
                return self._echt.execute(sql, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._echt, name)

        echte = self.db._con
        self.db._con = Mitschrift(echte)
        try:
            self.db.search_pages(q="viewtopic", limit=50, nur_zaehlen=True)
        finally:
            self.db._con = echte

        zaehlabfragen = [s for s in gesehene
                         if s.lstrip().startswith("SELECT COUNT(*) FROM (")]
        self.assertEqual(1, len(zaehlabfragen), gesehene)
        self.assertNotIn(
            "scrape_targets", zaehlabfragen[0],
            "Die Zaehlung verbindet scrape_targets - das kostet bei grossen "
            "Faellen eine Minute und traegt zur Zahl nichts bei.")
        self.assertNotIn(
            "annotations", zaehlabfragen[0],
            "Ohne Annotationsfilter wird annotations nicht gebraucht.")
        self.assertNotIn(
            "page_visits", zaehlabfragen[0],
            "Ohne Zeitraumfilter wird page_visits nicht gebraucht.")

    # -- SG09 -----------------------------------------------------------------
    def test_sg09_bei_annotationsfilter_wird_verbunden(self):
        """
        Die Gegenprobe zu SG08: was gebraucht wird, wird auch verbunden. Ohne
        diesen Fall koennte man die Verbindung ganz entfernen und SG08 bliebe
        gruen - die Zahl waere dann falsch.
        """
        gesehene = []

        class Mitschrift:
            def __init__(self, echt):
                self._echt = echt

            def execute(self, sql, *args, **kwargs):
                gesehene.append(sql)
                return self._echt.execute(sql, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._echt, name)

        echte = self.db._con
        self.db._con = Mitschrift(echte)
        try:
            zahl = self.db.search_pages(has_annotations=True, limit=50,
                                        nur_zaehlen=True)
        finally:
            self.db._con = echte

        zaehlabfrage = [s for s in gesehene
                        if s.lstrip().startswith("SELECT COUNT(*) FROM (")][0]
        self.assertIn("annotations", zaehlabfrage)
        self.assertNotIn("scrape_targets", zaehlabfrage)
        # Im Wegwerf-Bestand gibt es keine Annotationen - die Zahl muss 0 sein
        # und nicht etwa die Zahl aller Seiten.
        self.assertEqual(0, zahl)
        self.assertEqual(
            len(self.db.search_pages(has_annotations=True, limit=50)), zahl,
            "Zaehlung und Liste muessen auch mit Annotationsfilter "
            "uebereinstimmen.")

    # -- SG07 -----------------------------------------------------------------
    def test_sg07_minus_eins_heisst_unbekannt_nicht_null(self):
        """
        Eine gescheiterte Zaehlung darf nicht als 'keine Treffer' erscheinen.

        Nachgestellt wird GENAU die Zaehlabfrage: eine Huelle um execute()
        laesst alles durch und laesst nur das umhuellende 'SELECT COUNT(*)
        FROM (...)' scheitern. Die Verbindung einfach zu schliessen waere
        untauglich - dann scheitert schon das Ermitteln der Basis-URL, und
        der Fall wuerde etwas anderes messen, als er behauptet.
        """
        # sqlite3.Connection.execute laesst sich nicht ersetzen ('read-only
        # attribute'). Die Huelle sitzt deshalb um die Verbindung herum und
        # wird dem ForensicDb untergeschoben - fuer den gemessenen Code ist
        # das derselbe Zugriffsweg.
        class Stoerhuelle:
            def __init__(self, echt):
                self._echt = echt

            def execute(self, sql, *args, **kwargs):
                if sql.lstrip().startswith("SELECT COUNT(*) FROM ("):
                    raise sqlite3.OperationalError(
                        "Zaehlung absichtlich gestoert")
                return self._echt.execute(sql, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._echt, name)

        echte_verbindung = self.db._con
        self.db._con = Stoerhuelle(echte_verbindung)
        try:
            self.assertEqual(
                -1, self.db.search_pages(nur_zaehlen=True),
                "Eine gescheiterte Zaehlung muss -1 liefern, nicht 0 - sonst "
                "ist 'keine Treffer' von 'nicht ermittelbar' nicht zu "
                "unterscheiden.")

            # Und der Endpunkt liefert die Seiten trotzdem aus.
            koerper = self._endpunkt_antwort({"limit": ["50"]})["body"]
        finally:
            self.db._con = echte_verbindung

        self.assertEqual(4, len(koerper["pages"]),
                         "Eine gescheiterte ZAEHLUNG darf die Ergebnisliste "
                         "nicht verhindern.")
        self.assertEqual(-1, koerper["total"])
        self.assertIsNone(koerper["begrenzt"],
                          "Ohne Zahl laesst sich nicht sagen, ob die Grenze "
                          "gegriffen hat - dann steht dort 'unbekannt' und "
                          "nicht 'nein'.")


if __name__ == "__main__":
    unittest.main()
