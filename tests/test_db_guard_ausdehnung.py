# =============================================================================
# tests/test_db_guard_ausdehnung.py
# IT-Forensisches Ermittlungswerkzeug — Schutzhuelle, zweite Ausbaustufe
# =============================================================================
# Testsuite fuer Build 722, Ticket c9d24a7f
# ("Schutzhuelle auch auf placeholders.py und fileasset.py anwenden").
#
# ── WORUM ES GEHT, UND WARUM ES ZWEI ARTEN VON FEHLSCHLAG SIND ──────────────
#
# Ticket f0a3c85b (Build 578) hat gezeigt, wie ein Datenendpunkt scheitern
# kann, ohne etwas zu sagen: die Ausnahme fliegt aus dem Handler, die
# Verbindung stirbt, der Browser meldet 'Failed to fetch'. Dagegen half die
# Huelle (forensic_api/db_guard.geschuetzt).
#
# Build 579 hat dann die ZWEITE Art gefunden, und sie ist die heimtueckischere:
# die untere Schicht FAENGT den Fehler selbst und gibt eine leere Antwort
# zurueck. Dann kommt die Huelle nie zum Zuge, der Endpunkt antwortet mit
# HTTP 200 und einem Leerbefund - und 'es gibt nichts' ist von 'ich konnte
# nicht nachsehen' nicht mehr zu unterscheiden.
#
# Dieses Ticket dehnt beide Vorkehrungen auf die zwei Endpunkte aus, die in
# Build 578 ausdruecklich zurueckgestellt worden waren.
#
# ── DIE PRUEFUNGEN ──────────────────────────────────────────────────────────
#
# ART A - die Huelle (Verbindungsabbruch):
#   GA01 - /_forensic/fileasset: ein sqlite3-Fehler aus der Tiefe wird zur
#          benannten 503-Antwort statt zum Abbruch.
#   GA02 - /_forensic/placeholders/*: dasselbe am Verteiler, geprueft an
#          handle_values (liest evidence_<uid>.db ungeschuetzt).
#   GA03 - DIE GEGENPROBE: ein PROGRAMMIERFEHLER wird an BEIDEN Stellen
#          NICHT gefangen. Ohne sie waere jede Zusicherung wertlos - eine zu
#          weite Huelle macht aus jedem Tippfehler 'Datenbank nicht
#          erreichbar'.
#
# ART B - der Befund (stiller Leerbefund):
#   GA04 - AssetsDb trennt 'kein Treffer' von 'Abfrage gescheitert'.
#   GA05 - AssetsDb: nicht angebunden ist ein DRITTER, eigener Befund.
#   GA06 - fileasset antwortet auf einen Abfragefehler mit 503, NICHT 404.
#   GA07 - fileasset laesst 404, wo 404 richtig ist (kein Treffer,
#          nicht angebunden). Die Gegenprobe zu GA06: eine Meldung, die
#          immer kommt, wird nicht gelesen.
#   GA08 - placeholders/resolve verweigert bei unlesbarer templates.db die
#          Aufloesung, statt Vorgabewerte in den Berichtstext zu schreiben.
#   GA09 - ... aber NUR, wenn der Text ueberhaupt Platzhalter enthaelt.
#   GA10 - placeholders/refresh meldet keinen falschen Freispruch.
#   GA11 - placeholders/cache (POST) weist nicht den Platzhalter ab, wenn in
#          Wahrheit die Quelle nicht lesbar war.
#
# NEBENBEFUND (bei der Durchsicht gemessen, mit Alex am 14.08.2026 zur
# Mitbehebung entschieden):
#   GA12 - '?uid=abc' auf placeholders/cache ergibt 400 und keinen
#          ungefangenen ValueError. Bis Build 721 stand die Umwandlung
#          VOR dem try, der sie abfangen sollte.
#
# Version: v0.8.722 · Build: 722 · 2026-08-14
# Beleg: Ticket c9d24a7f; Vorlaeufer f0a3c85b (Build 578/579/580);
#        db/assets_db.py _abfrage (Build 722); forensic_api/db_guard.py.
# =============================================================================

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.assets_db import (
    AssetsDb,
    BEFUND_ABFRAGEFEHLER,
    BEFUND_KEIN_TREFFER,
    BEFUND_NICHT_ANGEBUNDEN,
    BEFUND_OK,
)
from forensic_api.db_guard import CODE_DB_UNAVAILABLE
from forensic_api.fileasset import FileassetEndpoint


class _Handler:
    """Minimaler Ersatz fuer den ForensicRequestHandler (wie in DG01-DG06)."""

    def __init__(self):
        self.status = None
        self.body = None
        self.ctype = None
        self.path = "/"

    def send_response_body(self, status, body, content_type=None,
                           extra_headers=None):
        self.status = status
        self.body = body
        self.ctype = content_type

    def json(self):
        return json.loads(self.body.decode("utf-8")) if self.body else None


def _assets_db_mit_daten(tmp: Path) -> sqlite3.Connection:
    """
    Eine echte, angebundene assets_<uid>.db - wie im Betrieb per ATTACH.

    KEIN Mock: der Unterschied zwischen 'kein Treffer' und 'Abfrage
    gescheitert' entsteht in SQLite und nicht in unserer Vorstellung davon.
    """
    pfad = tmp / "assets_42.db"
    roh = sqlite3.connect(str(pfad))
    roh.executescript("""
        CREATE TABLE assets (
            id INTEGER PRIMARY KEY, data BLOB,
            mime_type TEXT, file_size INTEGER, content_hash TEXT
        );
        CREATE TABLE asset_urls (
            url TEXT PRIMARY KEY, asset_id INTEGER,
            url_hash TEXT, url_context TEXT, page_id INTEGER
        );
        INSERT INTO assets (id, data, mime_type, file_size, content_hash)
            VALUES (1, X'89504E47', 'image/png', 4, 'h1');
        INSERT INTO asset_urls (url, asset_id, url_hash)
            VALUES ('http://filer.onion/img/x.png', 1, 'u1');
    """)
    roh.commit()
    roh.close()

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("ATTACH DATABASE '%s' AS adb" % pfad)
    return con


# =============================================================================
# ART B - der Befund
# =============================================================================

class AssetsBefundTests(unittest.TestCase):
    """GA04, GA05 - AssetsDb trennt die drei Lagen."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.con = _assets_db_mit_daten(Path(self._tmp.name))
        self.adb = AssetsDb(self.con)

    def tearDown(self):
        self.con.close()
        self._tmp.cleanup()

    # GA04 ----------------------------------------------------------------
    def test_ga04_treffer_leerbefund_und_fehler_sind_unterscheidbar(self):
        """
        GA04: DIE KERNPRUEFUNG DIESES TICKETS.

        Bis Build 721 gab get_asset_by_full_url() in allen drei Lagen None
        zurueck. Wer nur auf None prueft, kann 'gibt es nicht' und 'konnte
        nicht nachsehen' nicht auseinanderhalten - und genau daraus wurde im
        Endpunkt ein 404 fuer beides.
        """
        # (1) Treffer
        rec, befund = self.adb.get_asset_by_full_url_befund(
            "http://filer.onion/img/x.png")
        self.assertEqual(BEFUND_OK, befund)
        self.assertIsNotNone(rec)
        self.assertEqual(b"\x89PNG", rec.data)

        # (2) Leerbefund - die Datenbank wurde gelesen, das Asset ist nicht da
        rec, befund = self.adb.get_asset_by_full_url_befund(
            "http://filer.onion/img/gibtsnicht.png")
        self.assertEqual(BEFUND_KEIN_TREFFER, befund)
        self.assertIsNone(rec)

        # (3) Fehler - die Abfrage scheitert. Erzeugt durch DETACH: die
        #     Anbindung ist weg, _available bleibt aber True. Genau diese
        #     Lage entsteht im Betrieb, wenn die Datei waehrend des Laufs
        #     verschwindet (Vorfall 2026-07-30).
        self.con.execute("DETACH DATABASE adb")
        rec, befund = self.adb.get_asset_by_full_url_befund(
            "http://filer.onion/img/x.png")
        self.assertEqual(BEFUND_ABFRAGEFEHLER, befund)
        self.assertIsNone(rec)

    # GA05 ----------------------------------------------------------------
    def test_ga05_nicht_angebunden_ist_ein_eigener_befund(self):
        """
        GA05: Ohne Verbindung (con=None) ist die Lage KEIN Fehler - die
        assets_<uid>.db entsteht erst nach dem asset_importer-Lauf. Sie
        bekommt trotzdem einen eigenen Namen, damit der Endpunkt sie
        unterschiedlich protokollieren kann.
        """
        leer = AssetsDb(None)
        rec, befund = leer.get_asset_by_full_url_befund("http://egal/x.png")
        self.assertEqual(BEFUND_NICHT_ANGEBUNDEN, befund)
        self.assertIsNone(rec)

    # GA04b ---------------------------------------------------------------
    def test_ga04b_die_alte_methode_verhaelt_sich_unveraendert(self):
        """
        Die Gegenprobe zur Vertraeglichkeit: get_asset_by_full_url() gibt
        weiterhin genau AssetRecord-oder-None zurueck. Bestehende Aufrufer
        (server/asset_handler.py u. a.) duerfen von dieser Aenderung nichts
        merken.
        """
        self.assertIsNotNone(
            self.adb.get_asset_by_full_url("http://filer.onion/img/x.png"))
        self.assertIsNone(
            self.adb.get_asset_by_full_url("http://filer.onion/img/nein.png"))


class FileassetAntwortTests(unittest.TestCase):
    """GA01, GA06, GA07 - was der Endpunkt aus dem Befund macht."""

    def _endpunkt(self, assets):
        bundle = MagicMock()
        bundle.assets = assets
        return FileassetEndpoint(bundle)

    def _ruf(self, assets, url="http://filer.onion/img/x.png"):
        h = _Handler()
        self._endpunkt(assets).handle(h, {"url": [url]})
        return h

    # GA06 ----------------------------------------------------------------
    def test_ga06_abfragefehler_wird_503_und_nicht_404(self):
        """
        GA06: Der Fall, um den es im Ticket geht. Ein gescheiterter Zugriff
        darf nicht wie ein fehlendes Bild aussehen - sonst hat der Ermittler
        keinen Anlass nachzufragen.
        """
        assets = MagicMock()
        assets.get_asset_by_full_url_befund.return_value = (
            None, BEFUND_ABFRAGEFEHLER)
        h = self._ruf(assets)
        self.assertEqual(503, h.status)
        koerper = h.json()
        self.assertEqual(CODE_DB_UNAVAILABLE, koerper["code"])
        self.assertEqual("assets_<uid>.db", koerper["datenbank"])
        # Die Massnahme muss sagen, dass NICHT nachgesehen wurde - sonst
        # bleibt der Leser bei 'das Bild fehlt wohl'.
        self.assertIn("nicht nachgesehen", koerper["massnahme"])

    # GA07 ----------------------------------------------------------------
    def test_ga07_kein_treffer_und_nicht_angebunden_bleiben_404(self):
        """
        GA07: DIE GEGENPROBE ZU GA06. Eine 503-Meldung, die auch bei jedem
        harmlosen Leerbefund kaeme, wuerde nach dem dritten Mal ignoriert -
        und dann faellt der Fall nicht mehr auf, fuer den sie gedacht war.
        Auf einer Anlage ohne asset_importer-Lauf betraefe das JEDES Bild.
        """
        for befund in (BEFUND_KEIN_TREFFER, BEFUND_NICHT_ANGEBUNDEN):
            with self.subTest(befund=befund):
                assets = MagicMock()
                assets.get_asset_by_full_url_befund.return_value = (None,
                                                                    befund)
                h = self._ruf(assets)
                self.assertEqual(404, h.status)

    # GA01 ----------------------------------------------------------------
    def test_ga01_ausnahme_wird_zur_benannten_antwort(self):
        """
        GA01: Die Huelle als zweites Netz. Wirft die Tiefe doch eine
        sqlite3-Ausnahme (etwa aus einer Schicht, die sie nicht selbst
        faengt), endet das in einer 503-Antwort und NICHT im
        Verbindungsabbruch.
        """
        assets = MagicMock()
        assets.get_asset_by_full_url_befund.side_effect = sqlite3.Error(
            "database disk image is malformed")
        h = self._ruf(assets)
        self.assertEqual(503, h.status)
        self.assertEqual(CODE_DB_UNAVAILABLE, h.json()["code"])

    # GA03a ---------------------------------------------------------------
    def test_ga03a_programmierfehler_wird_nicht_gefangen(self):
        """
        GA03 (erste Haelfte): DIE WICHTIGSTE GEGENPROBE. Eine zu weite Huelle
        machte aus jedem Tippfehler die Meldung 'Datenbank nicht erreichbar',
        und wir wuerden Phantomen nachjagen. Ein AttributeError muss
        durchschlagen.
        """
        assets = MagicMock()
        assets.get_asset_by_full_url_befund.side_effect = AttributeError(
            "kein Attribut 'tippfehler'")
        with self.assertRaises(AttributeError):
            self._ruf(assets)

    # GA07b ---------------------------------------------------------------
    def test_ga07b_ohne_url_bleibt_es_bei_400(self):
        """
        Die Huelle darf die bestehende Eingabepruefung nicht verdecken: ohne
        'url' ist die ANFRAGE falsch und nicht die Datenbank kaputt.
        """
        h = _Handler()
        self._endpunkt(MagicMock()).handle(h, {})
        self.assertEqual(400, h.status)


# =============================================================================
# ART A/B - placeholders
# =============================================================================

class PlaceholdersSchutzTests(unittest.TestCase):
    """GA02, GA03b, GA08-GA12."""

    def setUp(self):
        from forensic_api.placeholders import PlaceholdersEndpoint
        self.bundle = MagicMock()
        kontext = MagicMock()
        kontext.subject_id = 42
        self.ep = PlaceholdersEndpoint(self.bundle, kontext, MagicMock())

    def _quelle_kaputt(self):
        """templates.db meldet sich als nicht nutzbar."""
        self.bundle.templates.zustand.return_value = (
            "nicht_angebunden", "templates.db ist nicht angebunden")

    def _quelle_ok(self):
        self.bundle.templates.zustand.return_value = ("ok", "")

    def _ruf(self, name, *args):
        h = _Handler()
        getattr(self.ep, name)(h, *args)
        return h

    # GA08 ----------------------------------------------------------------
    def test_ga08_resolve_schreibt_keine_vorgabewerte_in_den_bericht(self):
        """
        GA08: Der schwerste der drei Faelle. Ist die templates.db nicht
        lesbar, liefert get_query() None, AutoQueryResolver macht daraus
        'no_query', und der DEFAULT-Wert landet im Berichtstext. Der
        Ermittler sieht eine Ersatzangabe und hat keinen Anlass zu pruefen,
        ob dort der ermittelte Wert steht.
        """
        self._quelle_kaputt()
        h = self._ruf("handle_resolve",
                      json.dumps({"body": "Nutzer {{a:user.username}}.",
                                  "uid": 42}).encode())
        self.assertEqual(503, h.status)
        self.assertEqual(CODE_DB_UNAVAILABLE, h.json()["code"])

    # GA09 ----------------------------------------------------------------
    def test_ga09_ohne_platzhalter_kein_fehlalarm(self):
        """
        GA09: DIE GEGENPROBE ZU GA08. Enthaelt der Text keinen Platzhalter,
        ist 'unveraendert, nichts offen' die vollstaendige Wahrheit - es
        wurde nichts uebersprungen. Ein 503 waere hier ein Fehlalarm, und
        Fehlalarme kosten das Vertrauen, auf das die echte Meldung
        angewiesen ist.
        """
        self._quelle_kaputt()
        h = self._ruf("handle_resolve",
                      json.dumps({"body": "Kein Platzhalter hier.",
                                  "uid": 42}).encode())
        self.assertEqual(200, h.status)
        self.assertEqual("Kein Platzhalter hier.", h.json()["resolved"])

    # GA10 ----------------------------------------------------------------
    def test_ga10_refresh_gibt_keinen_falschen_freispruch(self):
        """
        GA10: list_queries() liefert bei unlesbarer Quelle eine LEERE Liste.
        Der Refresh lief dann ueber null Definitionen und meldete
        {"refreshed": 0, "errors": []} mit HTTP 200 - also 'nichts zu tun,
        keine Fehler'. Wer die Auffrischung anstoesst, WEIL ihm Werte
        veraltet vorkommen, bekaeme die Bestaetigung, dass alles stimmt.
        """
        self._quelle_kaputt()
        h = self._ruf("handle_refresh", json.dumps({"uid": 42}).encode())
        self.assertEqual(503, h.status)

    # GA11 ----------------------------------------------------------------
    def test_ga11_cache_set_beschuldigt_nicht_den_platzhalter(self):
        """
        GA11: Ohne lesbare Quelle gab get_query() None, und die Pruefung
        machte daraus HTTP 400 'Nur bekannte m/o-Platzhalter koennen
        case-weit wiederverwendet werden' - eine Aussage UEBER DEN
        PLATZHALTER, obwohl in Wahrheit die Quelle nicht lesbar war. Der
        Ermittler haelt seine Eingabe fuer unzulaessig; tatsaechlich wurde
        sie nie geprueft und nicht gespeichert.
        """
        self._quelle_kaputt()
        h = self._ruf("handle_cache_set",
                      json.dumps({"id": "spur", "value": "AIW-42",
                                  "uid": 42}).encode())
        self.assertEqual(503, h.status)
        # Und es darf dabei NICHTS geschrieben worden sein.
        self.bundle.evidence.set_cache_entry.assert_not_called()

    # GA12 ----------------------------------------------------------------
    def test_ga12_uid_abc_ergibt_400_und_keinen_absturz(self):
        """
        GA12 (Nebenbefund): Bis Build 721 stand 'int(uid)' VOR dem try, der
        es abfangen sollte. '?uid=abc' warf ein ungefangenes ValueError, die
        Verbindung starb, und der try darunter war fuer diesen Weg toter
        Code.
        """
        self._quelle_ok()
        h = self._ruf("handle_cache_get", {"uid": ["abc"], "ids": ["spur"]})
        self.assertEqual(400, h.status)
        self.assertEqual("BAD_PARAM", h.json()["code"])

    # GA12b ---------------------------------------------------------------
    def test_ga12b_ohne_uid_gilt_weiterhin_der_fall_aus_dem_kontext(self):
        """Die Gegenprobe: das bisherige Verhalten bleibt unangetastet."""
        self._quelle_ok()
        self.bundle.evidence.get_cache_entries_for_ids.return_value = {
            "spur": "AIW-42"}
        h = self._ruf("handle_cache_get", {"ids": ["spur"]})
        self.assertEqual(200, h.status)
        self.bundle.evidence.get_cache_entries_for_ids.assert_called_once_with(
            42, ["spur"])


class VerteilerHuelleTests(unittest.TestCase):
    """GA02, GA03b - die Huelle am Verteiler von /_forensic/placeholders/*."""

    def _api(self, platzhalter):
        """
        Ein ForensicApi mit ausgetauschtem PlaceholdersEndpoint. Gebaut wird
        NUR der Verteiler; alles andere bleibt unberuehrt.
        """
        from forensic_api import ForensicApi
        api = ForensicApi.__new__(ForensicApi)
        api._get_placeholders = lambda: platzhalter
        return api

    # GA02 ----------------------------------------------------------------
    def test_ga02_sqlite_fehler_am_verteiler_wird_benannt(self):
        """
        GA02: handle_values liest die evidence_<uid>.db ueber
        EvidenceDb.get_reports()/get_blocks_for_report() - und die rufen
        self._con.execute() OHNE try. Eine unlesbare Falldatenbank liess die
        Ausnahme bis aus dem Handler fliegen; der Browser meldete 'Failed to
        fetch'.
        """
        platzhalter = MagicMock()
        platzhalter.handle_values.side_effect = sqlite3.DatabaseError(
            "file is not a database")
        h = _Handler()
        self._api(platzhalter)._dispatch_placeholders(
            h, "GET", "/_forensic/placeholders/values", {})
        self.assertEqual(503, h.status)
        koerper = h.json()
        self.assertEqual(CODE_DB_UNAVAILABLE, koerper["code"])
        self.assertIn("evidence_<uid>.db", koerper["datenbank"])

    # GA03b ---------------------------------------------------------------
    def test_ga03b_programmierfehler_schlaegt_am_verteiler_durch(self):
        """
        GA03 (zweite Haelfte): dieselbe Gegenprobe wie GA03a, hier fuer den
        Verteiler. Ohne sie waere die Huelle eine Fehlerquelle statt einer
        Absicherung.
        """
        platzhalter = MagicMock()
        platzhalter.handle_values.side_effect = KeyError("blockidx")
        with self.assertRaises(KeyError):
            self._api(platzhalter)._dispatch_placeholders(
                _Handler(), "GET", "/_forensic/placeholders/values", {})

    # GA02b ---------------------------------------------------------------
    def test_ga02b_erfolg_bleibt_unberuehrt(self):
        """
        Die Huelle darf im Regelfall NICHTS tun. Ohne diese Pruefung koennte
        sie unbemerkt jede Antwort ueberschreiben.
        """
        platzhalter = MagicMock()
        gerufen = []
        platzhalter.handle_values.side_effect = (
            lambda h: gerufen.append(True))
        h = _Handler()
        self._api(platzhalter)._dispatch_placeholders(
            h, "GET", "/_forensic/placeholders/values", {})
        self.assertEqual([True], gerufen)
        self.assertIsNone(h.status)


if __name__ == "__main__":       # pragma: no cover
    unittest.main()
