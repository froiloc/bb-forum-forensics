# =============================================================================
# tests/test_spurensequenz_vollstaendigkeit.py
# IT-Forensisches Ermittlungswerkzeug — Spurensequenz, Vollstaendigkeit
# =============================================================================
# Testsuite fuer die Behebung der Vorgaenge
#   2f1044b9 — Spurensequenz enthaelt von mehrseitigen Themen nur eine Seite
#   aa0d9033 — Gruppe 'profile' bleibt leer, Profil-URLs stehen in 'other'
# in db/forensic_db.py::ForensicDb.get_trace_sequence() (Build 677).
#
# WARUM DIESE FAELLE UND NICHT WENIGER:
#   Die Messung vom 05.08.2026 gegen forensic_1488.db hat 185 erfasste Seiten
#   gefunden, die die Spurennavigation nie anlaeuft — 107 Benachrichtigungs-
#   seiten, 62 Themen-Folgeseiten, 16 Unterforen-Folgeseiten. Jede dieser
#   drei Sorten hat hier einen eigenen Fall (SV01, SV08, SV09), damit eine
#   spaetere Aenderung nicht eine Sorte zurueckholt und die anderen still
#   wieder verliert. Grundregel 1: kein Beleg darf still uebersprungen werden.
#
# Testfaelle:
#   SV01 — Mehrseitiges Thema: ALLE erfassten Seiten stehen in der Sequenz
#   SV02 — Reihenfolge innerhalb eines Themas: Seitennummer aufsteigend
#   SV03 — Zweitadressen derselben Seite erzeugen keinen zweiten Eintrag
#   SV04 — Ausgewaehlt wird die kanonische Adresse, nicht der kuerzere Alias
#   SV05 — Kennung wird ganz verglichen: '12' greift nicht auf '120870'
#   SV06 — Ziel mit leerer Kennung faellt NICHT auf das blosse Fragment zurueck
#   SV07 — Findet mehr als ein Ziel dieselbe Seite, gewinnt die bessere Gruppe
#   SV08 — Benachrichtigungsseiten: alle, nicht nur eine
#   SV09 — Unterforum-Folgeseiten stehen in der Sequenz
#   SV10 — Ziele ohne passende Seite werden gemeldet, nicht verschwiegen
#   SV11 — Zwei Aufrufe liefern dieselbe Reihenfolge (Zusicherung)
#   SV12 — Gruppenreihenfolge profile < pm < topic < other bleibt bestehen
#   SV13 — Seitennummern werden als ZAHL geordnet (p=10 hinter p=2)
#
# Version: v0.8.677 · Build: 677 · 2026-08-05
# Klassifikation: VERTRAULICH — NUR FUER DEN DIENSTGEBRAUCH
# =============================================================================

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.logger import reset_for_testing
from db.forensic_db import ForensicDb


# ---------------------------------------------------------------------------
# Hilfsmittel
# ---------------------------------------------------------------------------

def _db(scrape_targets=None, pages=None, aliases=None) -> sqlite3.Connection:
    """
    Baut eine Haupt-DB (evidence, im Arbeitsspeicher) mit ATTACH auf eine
    temporaere fdb-Datei — dasselbe Muster wie tests/test_trace_sequence.py.

    Zusaetzlich zu jener Fassung fuellt diese hier page_aliases. Das ist
    keine Bequemlichkeit: die Entdopplung nach page_id (SV03) und die Wahl
    der Adresse (SV04) sind ohne Aliasse gar nicht pruefbar, und genau dort
    lag der Fehler, der die Zahl der uebergangenen Seiten zweimal um ein
    Vielfaches zu hoch erscheinen liess.

    Args:
        scrape_targets: dicts mit id, url_type und den ID-Spalten
        pages:          dicts mit url_canonical, title
        aliases:        Paare (url_raw, page_id)
    """
    fdb_path = tempfile.mktemp(suffix="_fdb.db")
    fdb = sqlite3.connect(fdb_path)
    fdb.executescript("""
        CREATE TABLE forensic_meta (
            key TEXT NOT NULL PRIMARY KEY, value TEXT);
        CREATE TABLE pages (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            url_canonical  TEXT NOT NULL,
            html           BLOB,
            title          TEXT,
            fetched_at     INTEGER NOT NULL DEFAULT 0,
            http_status    INTEGER NOT NULL DEFAULT 200,
            scrape_context TEXT NOT NULL DEFAULT 'user',
            method         TEXT NOT NULL DEFAULT 'GET',
            UNIQUE(url_canonical, method));
        CREATE TABLE page_aliases (
            url_raw TEXT NOT NULL PRIMARY KEY,
            page_id INTEGER NOT NULL REFERENCES pages(id));
        CREATE TABLE scrape_targets (
            id             INTEGER PRIMARY KEY,
            scrape_context TEXT NOT NULL DEFAULT 'user',
            url_type       TEXT NOT NULL,
            forum_id       INTEGER,
            topic_id       INTEGER,
            post_id        INTEGER,
            pm_topic_id    INTEGER,
            pm_post_id     INTEGER,
            thanks_post_id INTEGER,
            poll_topic_id  INTEGER,
            actor_user_id  INTEGER,
            actor_username TEXT,
            static_url     TEXT,
            source_tables  TEXT NOT NULL DEFAULT '');
        INSERT INTO forensic_meta VALUES ('user_id', '1488');
        INSERT INTO forensic_meta VALUES ('username', 'testnutzer');
    """)
    for p in (pages or []):
        fdb.execute(
            "INSERT INTO pages (url_canonical, title, html) VALUES (?, ?, ?)",
            (p["url_canonical"], p.get("title"), b"<html></html>"))
    for url_raw, page_id in (aliases or []):
        fdb.execute(
            "INSERT INTO page_aliases (url_raw, page_id) VALUES (?, ?)",
            (url_raw, page_id))
    for st in (scrape_targets or []):
        fdb.execute(
            "INSERT INTO scrape_targets "
            "(id, url_type, forum_id, topic_id, post_id, pm_topic_id, "
            " actor_user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (st["id"], st["url_type"], st.get("forum_id"), st.get("topic_id"),
             st.get("post_id"), st.get("pm_topic_id"), st.get("actor_user_id")))
    fdb.commit()
    fdb.close()

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE annotations (
            id INTEGER PRIMARY KEY, page_url TEXT NOT NULL, element_id TEXT,
            category TEXT, text TEXT, ts INTEGER, investigator_id TEXT,
            local_id TEXT, tags_json TEXT, post_id INTEGER, created_by TEXT,
            selection_json TEXT);
        CREATE TABLE page_visits (
            id INTEGER PRIMARY KEY, page_url TEXT NOT NULL,
            scrape_context TEXT, ts INTEGER, investigator_id TEXT);
    """)
    con.execute("ATTACH DATABASE '%s' AS fdb" % fdb_path)
    con.commit()
    return con


class TestSpurensequenzVollstaendigkeit(unittest.TestCase):

    def setUp(self):
        reset_for_testing()

    # -- SV01 -----------------------------------------------------------------
    def test_sv01_mehrseitiges_thema_vollstaendig(self):
        """
        SV01 — Ein Thema mit drei erfassten Seiten steht mit DREI Eintraegen
        in der Sequenz.

        Der Kern von 2f1044b9. Bis Build 676 lieferte 'LIMIT 1' je Ziel genau
        eine Seite; gemessen trug keiner von 6.347 Eintraegen einen
        Seitenteil. Die Seite, auf der die Fehlersuche stattfand, trug 40
        Spuren und war ueber die Navigation nicht erreichbar.
        """
        con = _db(
            pages=[
                {"url_canonical": "/forum/viewtopic.php?id=120870", "title": "S1"},
                {"url_canonical": "/forum/viewtopic.php?id=120870&p=2", "title": "S2"},
                {"url_canonical": "/forum/viewtopic.php?id=120870&p=3", "title": "S3"},
            ],
            scrape_targets=[{"id": 1, "url_type": "viewtopic", "topic_id": 120870}],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual(len(erg), 3, "nicht alle erfassten Seiten in der Sequenz")
        self.assertEqual(
            [e["url"] for e in erg],
            ["/forum/viewtopic.php?id=120870",
             "/forum/viewtopic.php?id=120870&p=2",
             "/forum/viewtopic.php?id=120870&p=3"])

    # -- SV02 -----------------------------------------------------------------
    def test_sv02_reihenfolge_nach_seitennummer(self):
        """
        SV02 — Auch wenn die Seiten in umgekehrter Reihenfolge erfasst wurden,
        stehen sie in der Sequenz aufsteigend nach Seitennummer.

        Das ist die im Vorgang ausdruecklich verlangte Ordnung. Ohne sie
        haengt die Reihenfolge an der Speicherreihenfolge — und Ermittelnde
        arbeiten ein Thema dann von hinten nach vorn ab.
        """
        con = _db(
            pages=[
                {"url_canonical": "/forum/viewtopic.php?id=7&p=3", "title": "S3"},
                {"url_canonical": "/forum/viewtopic.php?id=7", "title": "S1"},
                {"url_canonical": "/forum/viewtopic.php?id=7&p=2", "title": "S2"},
            ],
            scrape_targets=[{"id": 1, "url_type": "viewtopic", "topic_id": 7}],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual([e["title"] for e in erg], ["S1", "S2", "S3"])

    # -- SV03 -----------------------------------------------------------------
    def test_sv03_zweitadressen_erzeugen_keinen_zweiten_eintrag(self):
        """
        SV03 — Sprungmarke und Zweitpfad tragen dieselbe page_id und ergeben
        EINEN Eintrag.

        Ohne diese Entdopplung waere die Behebung von 2f1044b9 schlimmer als
        der Fehler: im Bestand traegt eine Seite rund 23 Adressen, die
        Sequenz haette sich vervielfacht und dieselbe Seite immer wieder
        angeboten.
        """
        con = _db(
            pages=[{"url_canonical": "/forum/viewtopic.php?id=42", "title": "T"}],
            aliases=[("/forum/viewtopic.php?id=42#p33461", 1),
                     ("/forum/beginner/viewtopic.php?id=42", 1)],
            scrape_targets=[{"id": 1, "url_type": "viewtopic", "topic_id": 42}],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual(len(erg), 1)
        self.assertEqual(erg[0]["url"], "/forum/viewtopic.php?id=42")

    # -- SV04 -----------------------------------------------------------------
    def test_sv04_kanonische_adresse_schlaegt_kuerzeren_alias(self):
        """
        SV04 — Die kanonische Adresse wird auch dann gewaehlt, wenn ein Alias
        kuerzer ist.

        Der Fall ist so gebaut, dass eine Laengenregel allein die falsche
        Adresse waehlen wuerde. Die Spur-Navigation vergleicht zeichengenau;
        steht ein Alias in der Sequenz, findet sie die Seite nicht wieder.
        """
        con = _db(
            pages=[{"url_canonical": "/forum/beginner/viewtopic.php?id=9",
                    "title": "T"}],
            aliases=[("/forum/viewtopic.php?id=9", 1)],
            scrape_targets=[{"id": 1, "url_type": "viewtopic", "topic_id": 9}],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual(len(erg), 1)
        self.assertEqual(erg[0]["url"], "/forum/beginner/viewtopic.php?id=9")

    # -- SV05 -----------------------------------------------------------------
    def test_sv05_kennung_wird_ganz_verglichen(self):
        """
        SV05 — Das Ziel zu Thema 12 nimmt die Seite von Thema 12 und NICHT
        die von Thema 120870 oder 120.

        Bis Build 676 wurde als Teilzeichenkette gesucht: '%…id=12%' passt
        auch auf '…id=120870'. Das konnte die Seite eines FREMDEN Themas in
        die Spurenliste eines Beschuldigten holen — und zugleich die eigene
        verdraengen, weil die fremde Adresse dann schon vergeben war. Ein
        falsch zugeordneter Beleg ist schwerer als ein fehlender.

        ZUR EHRLICHKEIT DIESES FALLES: Der alte Fehler zeigte sich hier NICHT
        zuverlaessig. 'LIMIT 1' ohne ORDER BY hat keine zugesicherte
        Reihenfolge; gegen einen Aufbau mit nur einer Seite je Thema lieferte
        SQLite am 05.08.2026 zufaellig die richtige, und der Fall waere gruen
        gewesen, obwohl der Fehler vorlag. Thema 12 traegt hier deshalb ZWEI
        erfasste Seiten: an ihrer Zahl scheitert die alte Fassung in jedem
        Fall, gleich welche Zeile SQLite zuerst hergibt. Ein Fall, der einen
        Fehler nur manchmal findet, ist gefaehrlicher als keiner — er
        beruhigt.
        """
        con = _db(
            pages=[
                {"url_canonical": "/forum/viewtopic.php?id=120870", "title": "gross"},
                {"url_canonical": "/forum/viewtopic.php?id=120", "title": "mittel"},
                {"url_canonical": "/forum/viewtopic.php?id=12", "title": "klein"},
                {"url_canonical": "/forum/viewtopic.php?id=12&p=2", "title": "klein2"},
            ],
            scrape_targets=[{"id": 1, "url_type": "viewtopic", "topic_id": 12}],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual([e["url"] for e in erg],
                         ["/forum/viewtopic.php?id=12",
                          "/forum/viewtopic.php?id=12&p=2"],
                         "fremdes Thema in der Sequenz oder eigene Seite fehlt")

    # -- SV06 -----------------------------------------------------------------
    def test_sv06_leere_kennung_ohne_rueckfall(self):
        """
        SV06 — Ein Ziel, dessen ID-Spalte NULL ist, zieht KEINE beliebige
        Seite in die Sequenz.

        Das ist der gemessene Fall aus aa0d9033: das einzige pgp_probe-Ziel
        des Bestandes traegt actor_user_id NULL, suchte darauf das blosse
        '%profile.php?id=%' und fuehrte so eine fremde Profilseite unter der
        Gruppe 'other'. Erwartet wird jetzt: kein Eintrag — und eine Meldung
        (SV10 prueft, dass geredet wird).
        """
        con = _db(
            pages=[{"url_canonical": "/forum/profile.php?id=1488", "title": "P"}],
            scrape_targets=[{"id": 1, "url_type": "pgp_probe",
                             "actor_user_id": None}],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual(erg, [])

    # -- SV07 -----------------------------------------------------------------
    def test_sv07_bessere_gruppe_gewinnt(self):
        """
        SV07 — Finden zwei Ziele dieselbe Seite, entscheidet die Gruppe und
        nicht die Reihenfolge der Kennungen.

        Das pgp_probe-Ziel (Gruppe 'other') traegt hier die KLEINERE id und
        kam bis Build 676 deshalb zuerst — die Profilseite landete unter
        'Sonstiges' und wurde zuletzt statt zuerst betrachtet.
        """
        con = _db(
            pages=[{"url_canonical": "/forum/profile.php?id=1488", "title": "P"}],
            scrape_targets=[
                {"id": 1, "url_type": "pgp_probe",     "actor_user_id": 1488},
                {"id": 2, "url_type": "other_profile", "actor_user_id": 1488},
            ],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual(len(erg), 1)
        self.assertEqual(erg[0]["group"], "profile")
        self.assertEqual(erg[0]["trace_id"], 2)

    # -- SV08 -----------------------------------------------------------------
    def test_sv08_alle_benachrichtigungsseiten(self):
        """
        SV08 — Alle erfassten Benachrichtigungsseiten stehen in der Sequenz.

        Mit 107 Seiten war das die groesste der drei gemessenen Sorten. Der
        url_type traegt keine Kennung; bis Build 676 nahm 'LIMIT 1' davon
        genau eine.
        """
        con = _db(
            pages=[
                {"url_canonical": "/forum/notifications.php", "title": "N"},
                {"url_canonical": "/forum/notifications.php?filter=2", "title": "N2"},
                {"url_canonical": "/forum/notifications.php?id=5", "title": "N5"},
            ],
            scrape_targets=[{"id": 1, "url_type": "notifications"}],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual(len(erg), 3)
        self.assertTrue(all(e["group"] == "other" for e in erg))

    # -- SV09 -----------------------------------------------------------------
    def test_sv09_unterforum_folgeseiten(self):
        """SV09 — Auch Folgeseiten von Unterforen stehen in der Sequenz (16 gemessen)."""
        con = _db(
            pages=[
                {"url_canonical": "/forum/viewforum.php?id=3", "title": "F1"},
                {"url_canonical": "/forum/viewforum.php?id=3&p=2", "title": "F2"},
            ],
            scrape_targets=[{"id": 1, "url_type": "viewforum", "forum_id": 3}],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual([e["title"] for e in erg], ["F1", "F2"])

    # -- SV10 -----------------------------------------------------------------
    def test_sv10_uebergangene_ziele_werden_gemeldet(self):
        """
        SV10 — Ziele ohne passende Seite und Ziele ohne Kennung werden
        gemeldet.

        Grundregel 1 verlangt nicht, dass nichts uebersprungen wird — sie
        verlangt, dass nichts STILL uebersprungen wird. Bis Build 676 endeten
        beide Faelle in einem 'continue' ohne jede Spur im Betriebsbuch.
        """
        con = _db(
            pages=[],
            scrape_targets=[
                {"id": 1, "url_type": "viewtopic", "topic_id": 99},
                {"id": 2, "url_type": "pgp_probe", "actor_user_id": None},
            ],
        )
        with patch("db.forensic_db.logger") as log:
            erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual(erg, [])
        gesagt = " ".join(str(a) for a, _k in
                          [(c.args, c.kwargs) for c in log.warning.call_args_list])
        self.assertIn("ohne passende erfasste", gesagt)
        self.assertIn("ohne Kennung", gesagt)

    # -- SV11 -----------------------------------------------------------------
    def test_sv11_reihenfolge_ist_zwischen_aufrufen_gleich(self):
        """
        SV11 — Zwei Aufrufe liefern dieselbe Reihenfolge.

        Der Rang eines Eintrags wird in Vermerken genannt ('Spur 1501 von
        6347'). Eine Sequenz, die sich zwischen zwei Aufrufen umsortiert,
        macht solche Angaben wertlos. Die Zusicherung haengt an der letzten
        Sortierstufe (Adresse) — ohne sie entschiede die nicht zugesicherte
        Zeilenfolge aus SQLite.
        """
        seiten = [{"url_canonical": "/forum/viewtopic.php?id=5&p=%d" % n,
                   "title": "S%d" % n} for n in range(2, 12)]
        seiten.append({"url_canonical": "/forum/viewtopic.php?id=5", "title": "S1"})
        con = _db(pages=seiten,
                  scrape_targets=[{"id": 1, "url_type": "viewtopic", "topic_id": 5}])
        fdb = ForensicDb(con)
        self.assertEqual([e["url"] for e in fdb.get_trace_sequence()],
                         [e["url"] for e in fdb.get_trace_sequence()])

    # -- SV12 -----------------------------------------------------------------
    def test_sv12_gruppenreihenfolge_bleibt(self):
        """SV12 — profile < pm < topic < other, auch mit mehrseitigen Themen."""
        con = _db(
            pages=[
                {"url_canonical": "/forum/viewtopic.php?id=10", "title": "T1"},
                {"url_canonical": "/forum/viewtopic.php?id=10&p=2", "title": "T2"},
                {"url_canonical": "/forum/pmsnew.php?mdl=topic&tid=5", "title": "PM"},
                {"url_canonical": "/forum/profile.php?id=1488", "title": "Profil"},
                {"url_canonical": "/forum/viewforum.php?id=3", "title": "Forum"},
            ],
            scrape_targets=[
                {"id": 1, "url_type": "viewtopic",    "topic_id": 10},
                {"id": 2, "url_type": "pmsnew_topic", "pm_topic_id": 5},
                {"id": 3, "url_type": "profile",      "actor_user_id": 1488},
                {"id": 4, "url_type": "viewforum",    "forum_id": 3},
            ],
        )
        gruppen = [e["group"] for e in ForensicDb(con).get_trace_sequence()]
        self.assertEqual(gruppen, ["profile", "pm", "topic", "topic", "other"])

    # -- SV13 -----------------------------------------------------------------
    def test_sv13_seitennummer_wird_als_zahl_geordnet(self):
        """
        SV13 — Seite 10 steht hinter Seite 2, nicht davor.

        Eine Ordnung ueber die Adresse als Zeichenkette stellte '&p=10' vor
        '&p=2'. Bei Themen mit mehr als neun Seiten liefe die Navigation dann
        in einer Reihenfolge, die keiner Seitenzaehlung entspricht.
        """
        con = _db(
            pages=[
                {"url_canonical": "/forum/viewtopic.php?id=8&p=10", "title": "S10"},
                {"url_canonical": "/forum/viewtopic.php?id=8&p=2", "title": "S2"},
                {"url_canonical": "/forum/viewtopic.php?id=8", "title": "S1"},
            ],
            scrape_targets=[{"id": 1, "url_type": "viewtopic", "topic_id": 8}],
        )
        erg = ForensicDb(con).get_trace_sequence()
        self.assertEqual([e["title"] for e in erg], ["S1", "S2", "S10"])


if __name__ == "__main__":
    unittest.main()
