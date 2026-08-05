# =============================================================================
# tests/test_diag_spurensequenz_luecken.py
# IT-Forensisches Ermittlungswerkzeug — Regression zu tools/diag_spurensequenz_luecken.py
# =============================================================================
# Was hier bewacht wird (Vorgang 2f1044b9):
#
#   SL01 - Die Selbstprobe des Werkzeugs besteht. Sie ist der Grund, dem
#          Ergebnis zu trauen; faellt sie, darf kein Ergebnis ausgewiesen
#          werden.
#   SL02 - Gegen einen Wegwerf-Bestand mit BEKANNTER Luecke findet das
#          Werkzeug genau diese Luecke und meldet Rueckgabewert 1.
#   SL03 - Gegen einen Bestand OHNE Luecke meldet es 0 und keine Luecke.
#          Ein Waechter, der immer anschlaegt, ist keiner.
#   SL04 - DER WICHTIGSTE FALL: die Datenbankdatei ist nach dem Lauf
#          BYTEGLEICH. Das Werkzeug wird auf Bestaende losgelassen, die
#          Beweismittel sind; die Zusicherung 'nur lesend' muss gemessen
#          werden und nicht nur behauptet.
#   SL05 - Die TYPE_MAP im Werkzeug stimmt mit der in db/forensic_db.py
#          ueberein. Das Werkzeug misst, was der Produktivcode TUT. Weicht
#          die Abschrift ab, misst es etwas anderes - und niemand merkt es.
#
# Version: v0.8.671 - Build: 671 - 2026-08-05
# =============================================================================

from __future__ import annotations

import ast
import hashlib
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_WURZEL = Path(__file__).resolve().parent.parent
_WERKZEUG = _WURZEL / "tools" / "diag_spurensequenz_luecken.py"


def _lade_werkzeug():
    """Laedt das Werkzeug als Modul, ohne es als Skript auszufuehren."""
    spec = importlib.util.spec_from_file_location(
        "diag_spurensequenz_luecken", _WERKZEUG)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["diag_spurensequenz_luecken"] = modul
    spec.loader.exec_module(modul)
    return modul


def _baue_bestand(pfad: Path, seiten: list[str], ziele: list[tuple]) -> None:
    """
    Legt einen Wegwerf-Bestand in der Form von forensic_<uid>.db an.

    ziele: (url_type, topic_id, actor_user_id)
    """
    con = sqlite3.connect(pfad)
    con.executescript("""
        CREATE TABLE forensic_meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO forensic_meta VALUES ('protocol','http'),
                                         ('domainname','alice.onion');
        CREATE TABLE pages (id INTEGER PRIMARY KEY, url_canonical TEXT,
                            html BLOB, title TEXT);
        CREATE TABLE page_aliases (page_id INTEGER, url_raw TEXT);
        CREATE TABLE scrape_targets (
            id INTEGER PRIMARY KEY, scrape_context TEXT, url_type TEXT,
            forum_id INTEGER, topic_id INTEGER, post_id INTEGER,
            pm_topic_id INTEGER, pm_post_id INTEGER, thanks_post_id INTEGER,
            poll_topic_id INTEGER, actor_user_id INTEGER,
            actor_username TEXT, static_url TEXT, source_tables TEXT);
    """)
    for i, u in enumerate(seiten, 1):
        con.execute("INSERT INTO pages VALUES (?,?,NULL,?)",
                    (i, "http://alice.onion" + u, "Titel %d" % i))
    for i, (typ, topic, actor) in enumerate(ziele, 1):
        con.execute(
            "INSERT INTO scrape_targets "
            "(id, scrape_context, url_type, topic_id, actor_user_id, "
            " source_tables) VALUES (?,'user',?,?,?,'probe')",
            (i, typ, topic, actor))
    con.commit()
    con.close()


class DiagSpurensequenzTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.modul = _lade_werkzeug()

    def setUp(self):
        # Das Werkzeug sammelt seine Ausgabe in einer Modulvariablen. Ohne
        # Leeren wuechse sie ueber die Faelle hinweg und die Protokolldatei
        # eines Falls enthielte die Zeilen des vorigen.
        self.modul.LOGLINES.clear()

    # -- SL01 -----------------------------------------------------------------
    def test_sl01_selbstprobe_besteht(self):
        ok, begruendung = self.modul.selbstprobe()
        self.assertTrue(ok, "Selbstprobe fehlgeschlagen: %s" % begruendung)
        self.assertIn("4 bekannte Luecken", begruendung)

    # -- SL02 -----------------------------------------------------------------
    def test_sl02_bekannte_luecke_wird_gefunden(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_probe.db"
            _baue_bestand(
                db,
                seiten=[
                    "/forum/viewtopic.php?id=500",
                    "/forum/viewtopic.php?id=500&p=2",
                    "/forum/viewtopic.php?id=500&p=3",
                ],
                ziele=[("viewtopic", 500, None)],
            )
            con = self.modul.oeffne_lesend(db)
            basis = self.modul.basis_url(con)
            erg = self.modul.messe(self.modul.lade_urls(con, basis),
                                   self.modul.lade_ziele(con))
            con.close()

        self.assertEqual(1, len(erg["sequenz"]),
                         "die Sequenz fuehrt heute genau eine Seite je Thema")
        luecke = sorted(e["url"] for e in erg["luecke"])
        self.assertEqual(
            ["/forum/viewtopic.php?id=500&p=2",
             "/forum/viewtopic.php?id=500&p=3"], luecke,
            "genau die beiden Folgeseiten muessen als uebergangen gelten")

    # -- SL03 -----------------------------------------------------------------
    def test_sl03_ohne_luecke_kein_befund(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_probe.db"
            _baue_bestand(
                db,
                seiten=["/forum/viewtopic.php?id=500"],
                ziele=[("viewtopic", 500, None)],
            )
            con = self.modul.oeffne_lesend(db)
            basis = self.modul.basis_url(con)
            erg = self.modul.messe(self.modul.lade_urls(con, basis),
                                   self.modul.lade_ziele(con))
            con.close()
        self.assertEqual([], erg["luecke"],
                         "ein Waechter, der immer anschlaegt, ist keiner")
        self.assertEqual(1, len(erg["sequenz"]))

    # -- SL04 -----------------------------------------------------------------
    def test_sl04_datenbank_bleibt_bytegleich(self):
        """
        Die Zusicherung 'nur lesend' wird gemessen, nicht geglaubt.

        Geprueft wird die Pruefsumme der Datei UND die Abwesenheit von
        Journal-Nebendateien: ein '-wal' oder '-journal' waere der Beleg, dass
        eine Schreibabsicht bestand, selbst wenn die Hauptdatei gleich bliebe.
        """
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_probe.db"
            _baue_bestand(
                db,
                seiten=["/forum/viewtopic.php?id=500",
                        "/forum/viewtopic.php?id=500&p=2"],
                ziele=[("viewtopic", 500, None)],
            )
            vorher = hashlib.md5(db.read_bytes()).hexdigest()

            con = self.modul.oeffne_lesend(db)
            basis = self.modul.basis_url(con)
            self.modul.messe(self.modul.lade_urls(con, basis),
                             self.modul.lade_ziele(con))
            con.close()

            nachher = hashlib.md5(db.read_bytes()).hexdigest()
            self.assertEqual(vorher, nachher,
                             "die Datenbankdatei wurde veraendert")
            for anhang in ("-wal", "-shm", "-journal"):
                self.assertFalse(
                    Path(str(db) + anhang).exists(),
                    "Nebendatei '%s' entstanden - es gab eine Schreibabsicht"
                    % anhang)

    # -- SL06 -----------------------------------------------------------------
    def test_sl06_zweitadressen_zaehlen_nicht_als_luecke(self):
        """
        BUILD 672, aus eigenem Schaden.

        Die Fassung aus Build 671 zaehlte URLs. Gegen den echten Bestand
        meldete sie 73.796 uebergangene Seiten; nach Seiten gezaehlt sind es
        rund 2.000. Der Rest waren Zweitadressen DERSELBEN Seite - 65.216
        Sprungmarken ('...id=5136#p33461') und 6.346 Adressen unter einem
        zweiten Pfad ('/forum/beginner/...'). Beide stehen in page_aliases und
        tragen dieselbe page_id.

        Eine Messung, die einen Anker als uebergangenen Beleg zaehlt, laesst
        einen Befund dreissigmal groesser aussehen, als er ist. Dieser Fall
        haelt die Berichtigung fest.
        """
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "forensic_probe.db"
            _baue_bestand(
                db,
                seiten=["/forum/viewtopic.php?id=500",
                        "/forum/viewtopic.php?id=500&p=2"],
                ziele=[("viewtopic", 500, None)],
            )
            # Zweitadressen der ERSTEN Seite nachtragen: Sprungmarke und
            # zweiter Pfad. Beide zeigen auf page_id 1.
            con = sqlite3.connect(db)
            con.executemany(
                "INSERT INTO page_aliases (page_id, url_raw) VALUES (?,?)",
                [(1, "http://alice.onion/forum/viewtopic.php?id=500#p9001"),
                 (1, "http://alice.onion/forum/beginner/viewtopic.php?id=500")])
            con.commit()
            con.close()

            lese = self.modul.oeffne_lesend(db)
            basis = self.modul.basis_url(lese)
            erg = self.modul.messe(self.modul.lade_urls(lese, basis),
                                   self.modul.lade_ziele(lese))
            lese.close()

        luecke_seiten = {e["page_id"] for e in erg["luecke"]}
        self.assertNotIn(
            1, luecke_seiten,
            "Die Zweitadressen der ersten Seite werden als uebergangene Seite "
            "gezaehlt - das ist der Fehler aus Build 671.")
        self.assertEqual(
            1, len(erg["luecke"]),
            "Erwartet wird genau EINE uebergangene Seite (die Folgeseite "
            "&p=2); gefunden: %s"
            % sorted(e["url"] for e in erg["luecke"]))
        # Zum Vergleich: nach URLs gezaehlt waeren es drei. Genau diese
        # Differenz ist der berichtigte Fehler.
        self.assertEqual(3, erg["luecke_urls"])

    # -- SL07 -----------------------------------------------------------------
    def test_sl07_null_id_faellt_auf_das_blosse_fragment_zurueck(self):
        """
        BUILD 675, aus eigenem Schaden - und zwar aus einem, der eine falsche
        Schlussfolgerung nach sich gezogen hat.

        get_trace_sequence() verzweigt auf den WERT der ID-Spalte, nicht auf
        ihr Vorhandensein: ist der Wert NULL, wird das BLOSSE Fragment
        gesucht ('%profile.php?id=%'), nicht '<fragment>None'. Genau dieser
        Fall liegt im Bestand vor - das einzige 'pgp_probe'-Ziel traegt
        actor_user_id NULL und holt damit eine Profilseite in die Sequenz.

        Mein Nachbau suchte statt dessen nach 'profile.php?id=None' und fand
        nichts. Ergebnis: ein Sequenzeintrag zu wenig (6346 statt 6347) - und
        ich hatte diese Abweichung der unzugesicherten Reihenfolge von
        'LIMIT 1' zugeschrieben. Eine eigene Abweichung mit einer fremden
        Ursache erklaert; genau das darf nicht passieren.
        """
        zeile = {"id": 1091, "url_type": "pgp_probe", "forum_id": None,
                 "topic_id": None, "post_id": None, "pm_topic_id": None,
                 "actor_user_id": None}
        gruppe, url_typ, suchtext = self.modul.muster_fuer(zeile)
        self.assertEqual("other", gruppe)
        self.assertEqual(
            "profile.php?id=", suchtext,
            "Bei NULL muss das blosse Fragment gesucht werden - so macht es "
            "der Produktivcode.")
        self.assertNotIn("None", suchtext,
                         "'None' im Suchtext ist der berichtigte Fehler.")

        # Gegenprobe: mit dem blossen Fragment wird eine Profilseite gefunden.
        urls = [(2518, "/forum/profile.php?id=1488"),
                (2519, "/forum/profile.php?id=1488&menu=badge")]
        erg = self.modul.messe(urls, [zeile])
        self.assertEqual(
            1, len(erg["sequenz"]),
            "Das Ziel mit NULL-Kennung muss einen Sequenzeintrag beisteuern.")
        self.assertEqual("other", erg["sequenz"][0]["gruppe"])
        self.assertEqual([], erg["ohne_treffer"])

    # -- SL05 -----------------------------------------------------------------
    def test_sl05_type_map_ist_wortgleiche_abschrift(self):
        """
        Vergleicht die TYPE_MAP des Werkzeugs mit der in
        db/forensic_db.py, get_trace_sequence().

        Gelesen wird ueber den Syntaxbaum, nicht ueber einen Import: das
        Modul zieht den halben Serverunterbau nach, und dieser Fall soll
        auch dann noch laufen, wenn dort etwas klemmt.
        """
        quelle = (_WURZEL / "db" / "forensic_db.py").read_text(encoding="utf-8")
        baum = ast.parse(quelle)

        gefunden = None
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Assign):
                continue
            ziele = [z.id for z in knoten.targets if isinstance(z, ast.Name)]
            if "TYPE_MAP" not in ziele:
                continue
            try:
                gefunden = ast.literal_eval(knoten.value)
            except ValueError:                     # pragma: no cover
                continue
            break

        self.assertIsNotNone(
            gefunden, "TYPE_MAP in db/forensic_db.py nicht auffindbar - "
                      "wurde sie umbenannt? Dann ist die Abschrift im "
                      "Werkzeug ungeprueft.")
        self.assertEqual(
            gefunden, self.modul.TYPE_MAP,
            "Die Abschrift im Diagnosewerkzeug weicht vom Produktivcode ab. "
            "Das Werkzeug misst dann etwas anderes als das, was laeuft.")


class DiagSpurensequenzNachweisTests(unittest.TestCase):
    """
    SLN01 bis SLN03 - die Abschrift der Fassung AB Build 677 (messe_neu).

    Warum eigene Faelle und nicht die vorhandenen erweitert: messe() misst
    weiterhin den Zustand BIS Build 676 und muss dafuer unveraendert bleiben.
    Die beiden Rechnungen stehen nebeneinander, ihre Differenz ist der
    Nachweis - und ein Nachweis, dessen Ausgangsgroesse mitwandert, ist
    keiner.
    """

    @classmethod
    def setUpClass(cls):
        cls.modul = _lade_werkzeug()

    def setUp(self):
        self.modul.LOGLINES.clear()

    @staticmethod
    def _ziel(kennung, url_typ, **spalten):
        zeile = {"id": kennung, "url_type": url_typ, "forum_id": None,
                 "topic_id": None, "post_id": None, "pm_topic_id": None,
                 "actor_user_id": None}
        zeile.update(spalten)
        return zeile

    # -- SLN01 ----------------------------------------------------------------
    def test_sln01_alle_seiten_eines_themas(self):
        """
        SLN01 - Die neue Rechnung fuehrt alle drei Seiten des Themas, die
        alte nur eine. Genau diese Differenz ist der Nachweis.
        """
        urls = [(1, "/forum/viewtopic.php?id=120870"),
                (2, "/forum/viewtopic.php?id=120870&p=2"),
                (3, "/forum/viewtopic.php?id=120870&p=3"),
                (1, "/forum/viewtopic.php?id=120870#p4711")]
        ziele = [self._ziel(1, "viewtopic", topic_id=120870)]
        neu = self.modul.messe_neu(urls, ziele)
        self.assertEqual({e["page_id"] for e in neu["sequenz"]}, {1, 2, 3})
        alt = self.modul.messe(urls, ziele)
        self.assertEqual(len({e["page_id"] for e in alt["sequenz"]}), 1)

    # -- SLN02 ----------------------------------------------------------------
    def test_sln02_fremde_kennung_wird_nicht_uebernommen(self):
        """
        SLN02 - Das Ziel zu Thema 12 nimmt nicht die Seite von Thema 120870.
        Die alte Rechnung uebernahm sie (Teilzeichenkette) und verlor darueber
        die eigene Seite.
        """
        urls = [(1, "/forum/viewtopic.php?id=120870"),
                (2, "/forum/viewtopic.php?id=12")]
        ziele = [self._ziel(1, "viewtopic", topic_id=12)]
        neu = self.modul.messe_neu(urls, ziele)
        self.assertEqual([e["page_id"] for e in neu["sequenz"]], [2])

    # -- SLN03 ----------------------------------------------------------------
    def test_sln03_leere_kennung_wird_gezaehlt_statt_geraten(self):
        """
        SLN03 - Ein Ziel mit leerer Kennung zieht keine fremde Seite in die
        Sequenz und erscheint stattdessen in der Zaehlung. Die alte Rechnung
        fiel auf das blosse Fragment zurueck (Vorgang aa0d9033).
        """
        urls = [(1, "/forum/profile.php?id=1488")]
        ziele = [self._ziel(1, "pgp_probe", actor_user_id=None)]
        neu = self.modul.messe_neu(urls, ziele)
        self.assertEqual(neu["sequenz"], [])
        self.assertEqual(neu["ziele_ohne_kennung"], {"pgp_probe": 1})
        alt = self.modul.messe(urls, ziele)
        self.assertEqual(len(alt["sequenz"]), 1,
                         "die Abschrift der alten Fassung muss den Rueckfall "
                         "weiterhin zeigen - sonst ist der Vorher-Zustand "
                         "nicht mehr belegt")


if __name__ == "__main__":
    unittest.main()
