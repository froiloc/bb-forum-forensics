# =============================================================================
# tests/test_management_search_index.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B560)
# =============================================================================
# Testsuite fuer Build 560: search_index.db, Quellenleser, Indexbauer, Status,
# Befehlszeile. VOLLSTAENDIG automatisiert, NUR synthetische evidence-foermige
# Datenbanken — KEIN reales Beweismaterial.
#
# LEITLINIE DIESER SUITE (die Lehre aus den Builds 533/535, Uebergabe §4):
#   Ein Test, der die EXISTENZ einer Struktur prueft, ist billig und schwach.
#   Ein Test, der ihre WIRKUNG prueft, findet Fehler. Deshalb prueft SI09 nicht,
#   dass es Trigger GIBT, sondern dass ein neu indizierter Fall seine alten
#   Treffer VERLIERT; SI04/SI05 pruefen nicht, dass zwei FTS-Tabellen angelegt
#   wurden, sondern dass genau die eine findet, was die andere nicht findet.
#
# SI01 — Vokabular ist in sich schluessig (Codes eindeutig, ohne Doppelpunkt,
#        jede Satzart hat Bezeichnung, jeder Modus eine FTS5-Tabelle)
# SI02 — QUERPROBE VOKABULAR <-> ECHTES SCHEMA: jede (Tabelle, Spalte) aus
#        SATZ_ARTEN existiert wirklich in db/evidence_db._SCHEMA_DDL. Ein
#        Tippfehler indizierte sonst NICHTS und saehe aus wie 'nichts gefunden'
# SI03 — Index wird angelegt; Schemaversion und Tokenizer stehen in index_meta
# SI04 — WORTSUCHE findet das Wort, aber NICHT den verklebten Teilstring
#        (die Begruendung der Doppelindizierung, als Anker festgehalten)
# SI05 — TEILSTRINGSUCHE findet den verklebten Treffer
# SI06 — HTML wird entfernt; '<b>Birnen</b>mus' verklebt NICHT zu 'Birnenmus'
# SI07 — Editor.js: Absatz, Liste, Tabelle UND ein unbekannter zehnter
#        Blocktyp landen im Index (Einsammeln statt Aufzaehlen)
# SI08 — Fassungen: aktuell / ueberholt (Nachfolger via prev_id) /
#        zurueckgenommen (geloescht ohne Nachfolger)
# SI09 — WIRKUNG der Synchronisation: nach Neuindizierung ist der alte Text in
#        BEIDEN FTS-Tabellen verschwunden (kein Geisterindex)
# SI10 — UPDATE auf index_satz wird hart abgelehnt (Sperre statt Mechanismus)
# SI11 — inkrementell: unveraenderte DB wird NICHT neu gelesen; nach Aenderung
#        wieder
# SI12 — voll: liest auch Unveraendertes neu
# SI13 — eine defekte DB beendet den Lauf NICHT; die uebrigen sind indiziert
# SI14 — DB ohne die erwarteten Tabellen -> Befund 'ohne_tabelle', ausdruecklich
#        NICHT 'gelesen'
# SI15 — verschwundene DB wird aus dem Index ENTFERNT
# SI16 — fehlendes evidence-Verzeichnis: nichts indiziert, nichts entfernt,
#        verzeichnis_vorhanden=False ('nicht nachgesehen', nicht 'leer')
# SI17 — ein unvollstaendiger Fall wird beim naechsten inkrementellen Lauf
#        ERNEUT versucht, auch ohne Aenderung des Fingerabdrucks
# SI18 — abweichende Schemaversion -> Datei wird verworfen und neu aufgebaut
# SI19 — uebergrosser Text wird gekuerzt UND gezaehlt (Kuerzung ist ein Befund)
# SI20 — ersetze_fall lehnt unbekannte Satzart/Fassung/Befund ab
# SI21 — Mehrsprachigkeit: Diakritika (Mueller/Muller) und nichtlateinische
#        Schrift sind auffindbar (Fallerkenntnis 2)
# SI22 — der Lauf veraendert die Quelldatei NICHT (read-only, belegt ueber
#        SHA-512 vorher/nachher)
# SI23 — CLI: Exit 0 bei sauberem Bestand, Exit 2 bei unvollstaendigem Befund
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================

import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.evidence_db import _SCHEMA_DDL as EVIDENCE_DDL
from db.search_index_db import SCHEMA_VERSION, SearchIndexDb
from management.search import index_cli
from management.search.index_builder import SearchIndexBuilder
from management.search.index_status import SearchIndexStatus
from management.search.index_vokabular import (
    BEFUND_GELESEN,
    BEFUND_OHNE_TABELLE,
    FASSUNG_AKTUELL,
    FASSUNG_UEBERHOLT,
    FASSUNG_ZURUECKGENOMMEN,
    MODUS_TABELLE,
    SATZ_ARTEN,
    SUCHMODI,
)
from management.search.satz import Satz


# --------------------------------------------------------------------- Helfer
def evidence_anlegen(verzeichnis, uid):
    """Legt eine leere, schemakonforme evidence_<uid>.db an und liefert den Pfad."""
    pfad = Path(verzeichnis) / ("evidence_%d.db" % uid)
    con = sqlite3.connect(str(pfad))
    try:
        con.executescript(EVIDENCE_DDL)
        con.commit()
    finally:
        con.close()
    return pfad


def annotation(pfad, text, *, category="CAT_176", ts=1700000000,
               created_by="h001", tags_json=None, deleted_at=None,
               prev_id=None, version_nr=1):
    """Schreibt eine Annotation und liefert ihre id."""
    con = sqlite3.connect(str(pfad))
    try:
        cur = con.execute(
            "INSERT INTO annotations(page_url, category, text, ts, created_by, "
            "tags_json, deleted_at, prev_id, version_nr) "
            "VALUES ('viewtopic.php?id=1', ?, ?, ?, ?, ?, ?, ?, ?)",
            (category, text, ts, created_by, tags_json, deleted_at, prev_id,
             version_nr))
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def alias(pfad, term, *, created_at=1700000100):
    con = sqlite3.connect(str(pfad))
    try:
        con.execute(
            "INSERT INTO investigator_aliases(term, created_by, created_at) "
            "VALUES (?, 'h001', ?)", (term, created_at))
        con.commit()
    finally:
        con.close()


def baustein(pfad, block_id, block_type, block_data, *, updated_at=1700000200):
    con = sqlite3.connect(str(pfad))
    try:
        con.execute(
            "INSERT INTO reports(id, report_type, sequence_nr, title, "
            "created_by, created_at) VALUES (1, 'interim', 1, 'Vermerk', "
            "'h001', 1700000000) ON CONFLICT(id) DO NOTHING")
        con.execute(
            "INSERT INTO report_blocks(block_id, report_id, author, "
            "created_at, updated_at, block_type, block_data) "
            "VALUES (?, 1, 'h001', ?, ?, ?, ?)",
            (block_id, updated_at, updated_at, block_type,
             json.dumps(block_data, ensure_ascii=False)))
        con.commit()
    finally:
        con.close()


def treffer(index_db, begriff, modus="wort"):
    """Trefferliste (satz_art, text) fuer einen Begriff im gewaehlten Modus."""
    tab = MODUS_TABELLE[modus]
    con = index_db.verbindung()
    rows = con.execute(
        "SELECT s.satz_art, s.text, s.fassung, s.subject_id "
        "FROM %s f JOIN index_satz s ON s.satz_id = f.rowid "
        "WHERE %s MATCH ? ORDER BY s.satz_id" % (tab, tab),
        (begriff,)).fetchall()
    return [(r["satz_art"], r["text"], r["fassung"], r["subject_id"])
            for r in rows]


def sha512(pfad):
    h = hashlib.sha512()
    with open(str(pfad), "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


class SearchIndexTestBasis(unittest.TestCase):
    """Gemeinsames Gerüst: temporaeres Verzeichnis, evidence-Ordner, Index."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aiw_search_")
        self.evidence_dir = Path(self.tmp) / "evidence"
        self.evidence_dir.mkdir()
        self.index_pfad = Path(self.tmp) / "search_index.db"
        self.index = None

    def tearDown(self):
        if self.index is not None:
            self.index.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def oeffne_index(self):
        if self.index is not None:
            self.index.close()
        self.index = SearchIndexDb(self.index_pfad)
        return self.index

    def bauer(self):
        return SearchIndexBuilder(self.evidence_dir, self.oeffne_index()
                                  if self.index is None else self.index)


# ============================================================== SI01 · SI02
class TestVokabular(unittest.TestCase):
    """SI01/SI02 — das Vokabular gegen sich selbst und gegen das echte Schema."""

    def test_si01_vokabular_schluessig(self):
        codes = [a.code for a in SATZ_ARTEN]
        self.assertEqual(len(codes), len(set(codes)),
                         "doppelte Satzart-Codes")
        for c in codes:
            self.assertNotIn(":", c,
                             "Satzart-Code mit Doppelpunkt: %s" % c)
        for m in SUCHMODI:
            self.assertIn(m, MODUS_TABELLE,
                          "Suchmodus ohne FTS5-Tabelle: %s" % m)

    def test_si02_vokabular_deckt_sich_mit_evidence_schema(self):
        """
        QUERPROBE ZWISCHEN VOKABULAR UND DATENBANK.

        Waere in SATZ_ARTEN eine Spalte falsch geschrieben, indizierte der
        Leser sie nicht — und der Leerbefund saehe aus wie 'nichts erfasst'.
        Genau die Art stiller Auslassung, die Grundregel 1 verbietet. Deshalb
        wird hier gegen das ECHTE Schema geprueft und nicht gegen eine zweite
        Liste.
        """
        con = sqlite3.connect(":memory:")
        try:
            con.executescript(EVIDENCE_DDL)
            for art in SATZ_ARTEN:
                spalten = {r[1] for r in con.execute(
                    'PRAGMA table_info("%s")' % art.tabelle).fetchall()}
                self.assertTrue(
                    spalten,
                    "Tabelle aus SATZ_ARTEN fehlt im evidence-Schema: %s"
                    % art.tabelle)
                self.assertIn(
                    art.spalte, spalten,
                    "Spalte %s.%s (Satzart %s) gibt es im evidence-Schema nicht"
                    % (art.tabelle, art.spalte, art.code))
        finally:
            con.close()


# =============================================================== SI03 · SI18
class TestIndexDatei(SearchIndexTestBasis):

    def test_si03_index_wird_angelegt_mit_stammdaten(self):
        idx = self.oeffne_index()
        self.assertTrue(self.index_pfad.exists())
        self.assertEqual(idx.meta("schema_version"), str(SCHEMA_VERSION))
        self.assertIn("unicode61", idx.meta("tokenizer_wort"))
        self.assertEqual(idx.meta("tokenizer_teil"), "trigram")
        self.assertFalse(idx.neu_aufgebaut)

    def test_si18_fremde_schemaversion_wird_verworfen(self):
        """
        Der Index ist ein HILFSMITTEL: bei abweichender Version wird er
        NEU AUFGEBAUT statt migriert. Wichtig ist, dass das GEMELDET wird
        (neu_aufgebaut) — der naechste Lauf dauert dadurch lange, und das
        soll erklaerbar sein und nicht raetselhaft.
        """
        idx = self.oeffne_index()
        idx.setze_meta("schema_version", SCHEMA_VERSION + 99)
        idx.close()
        self.index = None
        neu = self.oeffne_index()
        self.assertTrue(neu.neu_aufgebaut)
        self.assertEqual(neu.meta("schema_version"), str(SCHEMA_VERSION))
        self.assertEqual(neu.satz_zahl(), 0)


# ================================================= SI04 · SI05 · SI06 · SI21
class TestSuchmodi(SearchIndexTestBasis):

    def setUp(self):
        super().setUp()
        self.pfad = evidence_anlegen(self.evidence_dir, 4711)

    def test_si04_wortsuche_findet_wort_aber_nicht_den_verklebten_teilstring(self):
        """
        DIESER TEST HAELT DIE BEGRUENDUNG DER DOPPELINDIZIERUNG FEST.

        Faende die Wortsuche auch den verklebten Treffer, waere der
        trigram-Index ueberfluessig — und der Test wuerde brechen, damit
        jemand die Entscheidung neu bewertet statt sie stillschweigend
        weiterzuschleppen.
        """
        annotation(self.pfad, "Nickname birnenmus taucht wieder auf")
        alias(self.pfad, "xXbirnenmusXx")
        self.oeffne_index()
        SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        wort = treffer(self.index, "birnenmus", "wort")
        arten = {t[0] for t in wort}
        self.assertIn("annotation_text", arten)
        self.assertNotIn("ermittler_alias", arten,
                         "Die Wortsuche hat einen verklebten Teilstring "
                         "gefunden — dann ist die Begruendung fuer den "
                         "trigram-Index neu zu bewerten.")

    def test_si05_teilstringsuche_findet_den_verklebten_treffer(self):
        annotation(self.pfad, "Nickname birnenmus taucht wieder auf")
        alias(self.pfad, "xXbirnenmusXx")
        self.oeffne_index()
        SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        teil = treffer(self.index, "birnenmus", "teilstring")
        arten = {t[0] for t in teil}
        self.assertIn("annotation_text", arten)
        self.assertIn("ermittler_alias", arten)

    def test_si06_html_wird_entfernt_und_verklebt_nicht(self):
        """
        '<b>Birnen</b>mus' darf im Index NICHT zu 'Birnenmus' werden — das
        Wort steht so nicht im Text. Und 'href'/'mark' duerfen ueberhaupt
        nicht auftauchen, sonst waeren sie die haeufigsten Treffer der Anlage.
        """
        annotation(self.pfad,
                   'Alias <b>Birnen</b>mus, siehe '
                   '<a href="viewtopic.php?id=9">Beitrag</a> &amp; Anhang')
        self.oeffne_index()
        SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        self.assertEqual([], treffer(self.index, "href", "wort"))
        self.assertEqual([], treffer(self.index, "Birnenmus", "wort"))
        self.assertTrue(treffer(self.index, "Birnen", "wort"))
        text = treffer(self.index, "Birnen", "wort")[0][1]
        self.assertIn("&", text, "HTML-Entitaet wurde nicht aufgeloest")
        self.assertNotIn("<", text)

    def test_si21_mehrsprachigkeit(self):
        """
        Das Forum ist multilingual (Fallerkenntnis 2), die Notizen zitieren
        daraus. 'remove_diacritics 2' muss 'Mueller'-Schreibweisen
        zusammenfuehren, und nichtlateinische Schrift muss auffindbar sein.
        """
        annotation(self.pfad, "Zeuge Müller nennt den Ort")
        annotation(self.pfad, "Пользователь birnenmus schreibt")
        self.oeffne_index()
        SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        self.assertTrue(treffer(self.index, "Muller", "wort"),
                        "Diakritika werden nicht normalisiert")
        self.assertTrue(treffer(self.index, "Пользователь", "wort"),
                        "nichtlateinische Schrift ist nicht auffindbar")


# ======================================================================= SI07
class TestEditorBloecke(SearchIndexTestBasis):

    def test_si07_alle_blocktypen_inklusive_unbekanntem(self):
        """
        Das Einsammeln (statt Aufzaehlen) ist genau dafuer da, dass ein
        ZEHNTER Blocktyp nicht lautlos aus dem Index faellt. Der Bestand
        rechnet ausdruecklich mit einem (report_source.py:57).
        """
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        baustein(pfad, "b1", "paragraph", {"text": "Absatz mit apfelsaft"})
        baustein(pfad, "b2", "list",
                 {"items": ["erstens birnensaft", "zweitens"]})
        baustein(pfad, "b3", "table",
                 {"content": [["Kopf", "kirschsaft"], ["Zeile", "x"]]})
        baustein(pfad, "b4", "zehnter_typ",
                 {"ueberschrift": "traubensaft", "url": "/nicht/indizieren"})
        self.oeffne_index()
        SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        for begriff in ("apfelsaft", "birnensaft", "kirschsaft"):
            self.assertTrue(treffer(self.index, begriff, "wort"),
                            "Blocktext nicht gefunden: %s" % begriff)
        self.assertTrue(
            treffer(self.index, "traubensaft", "wort"),
            "Ein unbekannter Blocktyp ist aus dem Index gefallen — genau das "
            "soll das rekursive Einsammeln verhindern.")
        self.assertEqual(
            [], treffer(self.index, "indizieren", "wort"),
            "Ein Strukturschluessel ('url') ist im Index gelandet.")


# ======================================================================= SI08
class TestFassungen(SearchIndexTestBasis):

    def test_si08_aktuell_ueberholt_zurueckgenommen(self):
        """
        Die drei Zustaende muessen UNTERSCHEIDBAR im Index stehen — sie duerfen
        in der Sicht nie zusammengezaehlt werden. 'deleted_at' heisst bei
        einer bearbeiteten Annotation GEAENDERT, nicht GELOESCHT
        (db/evidence_db.py:868-874).
        """
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        alt = annotation(pfad, "alte fassung apfelsaft", deleted_at=1700000500)
        annotation(pfad, "neue fassung apfelsaft", prev_id=alt, version_nr=2)
        annotation(pfad, "widerrufen birnensaft", deleted_at=1700000600)
        annotation(pfad, "gilt kirschsaft")
        self.oeffne_index()
        SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        fassungen = {t[1]: t[2] for t in treffer(self.index, "fassung", "wort")}
        self.assertEqual(fassungen.get("alte fassung apfelsaft"),
                         FASSUNG_UEBERHOLT)
        self.assertEqual(fassungen.get("neue fassung apfelsaft"),
                         FASSUNG_AKTUELL)
        self.assertEqual(
            treffer(self.index, "widerrufen", "wort")[0][2],
            FASSUNG_ZURUECKGENOMMEN)
        self.assertEqual(
            treffer(self.index, "kirschsaft", "wort")[0][2], FASSUNG_AKTUELL)


# =============================================================== SI09 · SI10
class TestIndexSynchronisation(SearchIndexTestBasis):

    def test_si09_neuindizierung_laesst_keinen_geisterindex_zurueck(self):
        """
        WIRKUNGSPRUEFUNG statt Existenzpruefung: nicht 'gibt es die Trigger?',
        sondern 'ist der alte Treffer weg?'. Ein vergessener Loesch-Trigger
        waere besonders heimtueckisch — der Index lieferte weiter Treffer, nur
        eben zu Text, der so nicht mehr existiert.
        """
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        annotation(pfad, "alter begriff apfelsaft")
        self.oeffne_index()
        bauer = SearchIndexBuilder(self.evidence_dir, self.index)
        bauer.lauf()
        self.assertTrue(treffer(self.index, "apfelsaft", "wort"))
        self.assertTrue(treffer(self.index, "apfelsaft", "teilstring"))

        con = sqlite3.connect(str(pfad))
        con.execute("UPDATE annotations SET text = 'neuer begriff birnensaft'")
        con.commit()
        con.close()
        bauer.lauf(voll=True)

        self.assertEqual([], treffer(self.index, "apfelsaft", "wort"),
                         "Geisterindex in index_wort")
        self.assertEqual([], treffer(self.index, "apfelsaft", "teilstring"),
                         "Geisterindex in index_teil")
        self.assertTrue(treffer(self.index, "birnensaft", "wort"))

    def test_si10_update_auf_index_satz_wird_abgelehnt(self):
        """
        SPERRE STATT MECHANISMUS: es gibt keinen UPDATE-Trigger, weil ihn
        niemand benutzt. Damit ein spaeterer Umbau nicht in einen stillen
        Indexdrift laeuft, bricht ein UPDATE hart ab.
        """
        idx = self.oeffne_index()
        idx.ersetze_fall(
            4711,
            [Satz(4711, "ermittler_alias", "investigator_aliases", "term",
                  "1", FASSUNG_AKTUELL, 1700000000, "h001", "apfelsaft")],
            db_pfad="x", fingerprint="fp")
        with self.assertRaises(sqlite3.IntegrityError):
            idx.verbindung().execute(
                "UPDATE index_satz SET text = 'birnensaft'")


# ================================================= SI11 · SI12 · SI15 · SI16
class TestInkrementellerLauf(SearchIndexTestBasis):

    def test_si11_unveraenderte_db_wird_nicht_neu_gelesen(self):
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        annotation(pfad, "erster stand apfelsaft")
        self.oeffne_index()
        bauer = SearchIndexBuilder(self.evidence_dir, self.index)
        self.assertEqual(1, bauer.lauf()["faelle_gelesen"])
        self.assertEqual(0, bauer.lauf()["faelle_gelesen"],
                         "unveraenderte Datenbank wurde erneut gelesen")

        annotation(pfad, "zweiter stand birnensaft")
        self.assertEqual(1, bauer.lauf()["faelle_gelesen"],
                         "geaenderte Datenbank wurde NICHT neu gelesen")
        self.assertTrue(treffer(self.index, "birnensaft", "wort"))

    def test_si12_voller_lauf_liest_auch_unveraendertes(self):
        evidence_anlegen(self.evidence_dir, 4711)
        evidence_anlegen(self.evidence_dir, 5023)
        self.oeffne_index()
        bauer = SearchIndexBuilder(self.evidence_dir, self.index)
        bauer.lauf()
        self.assertEqual(0, bauer.lauf()["faelle_gelesen"])
        self.assertEqual(2, bauer.lauf(voll=True)["faelle_gelesen"])

    def test_si15_verschwundene_db_wird_entfernt(self):
        """
        Ein Fall, dessen Quelle verschwunden ist, muss AUS dem Index — sonst
        lieferte die Suche Treffer, die sich nicht mehr gegen die Quelle
        verifizieren lassen. Der Index sagt WO nachzusehen ist; zeigt er ins
        Leere, ist er schaedlich.
        """
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        annotation(pfad, "verschwindet apfelsaft")
        evidence_anlegen(self.evidence_dir, 5023)
        self.oeffne_index()
        bauer = SearchIndexBuilder(self.evidence_dir, self.index)
        bauer.lauf()
        self.assertTrue(treffer(self.index, "apfelsaft", "wort"))

        os.remove(str(pfad))
        bericht = bauer.lauf()
        self.assertEqual([4711], bericht["faelle_entfernt"])
        self.assertEqual([], treffer(self.index, "apfelsaft", "wort"))
        self.assertNotIn(4711, self.index.quellen())

    def test_si16_fehlendes_verzeichnis_ist_nicht_nachgesehen(self):
        """
        'Verzeichnis fehlt' und 'Verzeichnis leer' duerfen nicht gleich
        aussehen. Insbesondere darf ein falsch gesetztes
        paths.evidence_db_dir NICHT dazu fuehren, dass der Index geleert wird.
        """
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        annotation(pfad, "bleibt apfelsaft")
        self.oeffne_index()
        SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        falsch = Path(self.tmp) / "gibt_es_nicht"
        bericht = SearchIndexBuilder(falsch, self.index).lauf()
        self.assertFalse(bericht["verzeichnis_vorhanden"])
        self.assertEqual(0, bericht["faelle_gelesen"])
        self.assertEqual([], bericht["faelle_entfernt"])
        self.assertTrue(treffer(self.index, "apfelsaft", "wort"),
                        "Ein falscher Verzeichnispfad hat den Index geleert.")


# ======================================================= SI13 · SI14 · SI17
class TestFehlbefunde(SearchIndexTestBasis):

    def test_si13_defekte_db_beendet_den_lauf_nicht(self):
        kaputt = Path(self.evidence_dir) / "evidence_4711.db"
        kaputt.write_bytes(b"SQLite format 3\x00 das ist keine Datenbank" * 20)
        heil = evidence_anlegen(self.evidence_dir, 5023)
        annotation(heil, "heil geblieben apfelsaft")
        self.oeffne_index()
        bericht = SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        self.assertEqual(2, bericht["faelle_gelesen"])
        self.assertTrue(treffer(self.index, "apfelsaft", "wort"),
                        "Die heile Datenbank wurde wegen der defekten nicht "
                        "indiziert.")
        befunde = {e["subject_id"]: e["befund"] for e in bericht["ergebnisse"]}
        self.assertNotEqual(BEFUND_GELESEN, befunde[4711])
        self.assertEqual(BEFUND_GELESEN, befunde[5023])
        self.assertTrue(bericht["unvollstaendig"],
                        "Der Fehlbefund wurde nicht als unvollstaendig "
                        "ausgewiesen.")

    def test_si14_db_ohne_tabellen_ist_nicht_gelesen(self):
        """
        'ohne_tabelle' ist ein EIGENER Befund. Es ist NICHT gesagt, dass
        nichts erfasst wurde — diese Datenbank wurde nur nicht ausgewertet.
        Dieselbe Trennschaerfe wie bei m002 im Fristenmonitor (TA12).
        """
        leer = Path(self.evidence_dir) / "evidence_4711.db"
        con = sqlite3.connect(str(leer))
        con.execute("CREATE TABLE etwas_anderes (x INTEGER)")
        con.commit()
        con.close()
        self.oeffne_index()
        bericht = SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        e = bericht["ergebnisse"][0]
        self.assertEqual(BEFUND_OHNE_TABELLE, e["befund"])
        self.assertIn("NICHT gesagt", e["detail"])

    def test_si17_unvollstaendiger_fall_wird_erneut_versucht(self):
        """
        'Nicht lesbar' kann voruebergehend sein (Datei gerade in Benutzung).
        Bliebe der Fall bis zu seiner naechsten Aenderung aus dem Index, waere
        er auf unbestimmte Zeit unauffindbar — ohne dass jemand davon wuesste.
        """
        pfad = Path(self.evidence_dir) / "evidence_4711.db"
        pfad.write_bytes(b"kein sqlite")
        self.oeffne_index()
        bauer = SearchIndexBuilder(self.evidence_dir, self.index)
        bauer.lauf()
        self.assertIn(4711, bauer.status.zu_indizieren(),
                      "Ein unvollstaendiger Fall wird nicht erneut versucht.")

        os.remove(str(pfad))
        heil = evidence_anlegen(self.evidence_dir, 4711)
        annotation(heil, "jetzt lesbar apfelsaft")
        bericht = bauer.lauf()
        self.assertEqual(1, bericht["faelle_gelesen"])
        self.assertTrue(treffer(self.index, "apfelsaft", "wort"))


# =============================================================== SI19 · SI20
class TestSchreibpfad(SearchIndexTestBasis):

    def test_si19_uebergrosser_text_wird_gekuerzt_und_gezaehlt(self):
        """
        Eine Kuerzung ist ein BEFUND und kein Detail: der indizierte Text ist
        dann unvollstaendig, und eine Suche nach dem abgeschnittenen Teil
        fuende nichts. Sie muss deshalb im Bericht UND in index_quelle stehen.
        """
        from management.search.block_text import MAX_SATZ_LAENGE
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        annotation(pfad, "kopf " + ("x" * (MAX_SATZ_LAENGE + 500)))
        self.oeffne_index()
        bericht = SearchIndexBuilder(self.evidence_dir, self.index).lauf()

        self.assertEqual(1, bericht["saetze_gekuerzt"])
        self.assertEqual(1, int(self.index.quellen()[4711]["gekuerzt_zahl"]))

    def test_si20_unbekanntes_vokabular_wird_abgelehnt(self):
        """
        Ein Tippfehler in der Satzart landete sonst als eigene, nirgends
        aufgefuehrte Art im Index — und faehlte in jeder Sicht, ohne dass
        etwas anschlaegt.
        """
        idx = self.oeffne_index()
        gut = Satz(4711, "annotation_text", "annotations", "text", "1",
                   FASSUNG_AKTUELL, 1700000000, "h001", "apfelsaft")
        with self.assertRaises(ValueError):
            idx.ersetze_fall(4711, [gut._replace(satz_art="tippfehler")],
                             db_pfad="x", fingerprint="fp")
        with self.assertRaises(ValueError):
            idx.ersetze_fall(4711, [gut._replace(fassung="halbaktuell")],
                             db_pfad="x", fingerprint="fp")
        with self.assertRaises(ValueError):
            idx.ersetze_fall(4711, [gut], db_pfad="x", fingerprint="fp",
                             befund="irgendwie_gelesen")


# ======================================================================= SI22
class TestReadOnly(SearchIndexTestBasis):

    def test_si22_lauf_veraendert_die_quelle_nicht(self):
        """
        Der Migrationsvorbehalt fuer die Beweismitteldatenbanken (ab
        01.07.2026) ist nur dann nicht beruehrt, wenn wirklich nichts
        geschrieben wird. Belegt ueber SHA-512 vorher/nachher — nicht ueber
        mtime, die auf Netzlaufwerken grob sein kann.
        """
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        annotation(pfad, "unveraendert apfelsaft")
        vorher = sha512(pfad)
        self.oeffne_index()
        SearchIndexBuilder(self.evidence_dir, self.index).lauf(voll=True)
        self.assertEqual(vorher, sha512(pfad),
                         "Die Quelldatenbank wurde beim Indexlauf veraendert.")
        for suffix in ("-wal", "-shm", "-journal"):
            self.assertFalse(Path(str(pfad) + suffix).exists(),
                             "Journal-Nebendatei an der Quelle entstanden: %s"
                             % suffix)


# ======================================================================= SI23
class TestBefehlszeile(SearchIndexTestBasis):

    def _lauf(self, *argv):
        puffer = io.StringIO()
        with redirect_stdout(puffer):
            code = index_cli.main(list(argv))
        return code, puffer.getvalue()

    def test_si23_exitcodes(self):
        """
        'gelaufen, aber nicht vollstaendig' darf im Betriebsskript nicht wie
        'gelaufen' aussehen — deshalb der eigene Exit-Code 2.
        """
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        annotation(pfad, "sauberer bestand apfelsaft")
        code, text = self._lauf("--index-db", str(self.index_pfad),
                                "--evidence-dir", str(self.evidence_dir),
                                "--auffrischen", "--leise")
        self.assertEqual(0, code, text)
        self.assertIn("Saetze geschrieben", text)

        kaputt = Path(self.evidence_dir) / "evidence_5023.db"
        kaputt.write_bytes(b"kein sqlite")
        code, text = self._lauf("--index-db", str(self.index_pfad),
                                "--evidence-dir", str(self.evidence_dir),
                                "--auffrischen", "--leise")
        self.assertEqual(2, code, text)
        self.assertIn("UNVOLLSTAENDIG", text)

    def test_si23b_status_als_json(self):
        evidence_anlegen(self.evidence_dir, 4711)
        code, text = self._lauf("--index-db", str(self.index_pfad),
                                "--evidence-dir", str(self.evidence_dir),
                                "--status", "--json")
        self.assertEqual(0, code, text)
        daten = json.loads(text)
        self.assertIn("status", daten)
        self.assertEqual(1, daten["status"]["faelle_im_verzeichnis"])
        self.assertEqual(0, daten["status"]["faelle_im_index"])
        self.assertEqual([4711], daten["status"]["neu"])


# ======================================================================= Status
class TestStatus(SearchIndexTestBasis):

    def test_status_meldet_neu_veraendert_verschwunden(self):
        pfad = evidence_anlegen(self.evidence_dir, 4711)
        annotation(pfad, "erster stand apfelsaft")
        self.oeffne_index()
        bauer = SearchIndexBuilder(self.evidence_dir, self.index)
        bauer.lauf()
        st = SearchIndexStatus(self.evidence_dir, self.index).status()
        self.assertTrue(st["aktuell"])
        self.assertEqual([4711], st["unveraendert"])

        evidence_anlegen(self.evidence_dir, 5023)
        annotation(pfad, "zweiter stand birnensaft")
        st = SearchIndexStatus(self.evidence_dir, self.index).status()
        self.assertEqual([5023], st["neu"])
        self.assertEqual([4711], st["veraendert"])
        self.assertFalse(st["aktuell"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
