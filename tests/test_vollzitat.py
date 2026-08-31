# =============================================================================
# tests/test_vollzitat.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Beweismittelgruppen)
# =============================================================================
# Testsuite fuer Build 725: die vierte Darstellungsvariante einer
# Beweismittelgruppe. Vollstaendig automatisiert, ohne Browser, ohne Netz.
#
# Der Seitenabzug in den Vorrichtungen bildet das FluxBB/PunBB-Markup nach,
# das der Forenquelltext erzeugt (Projektspeicher: topic.php, post.php -
# blockpost > box > inbox > postbody > postright > postmsg). Alle Inhalte
# sind erfunden.
#
# -- Absatzfinder ------------------------------------------------------------
# VZ01 - Anker loest auf: Absatz gefunden, Versaetze zeichengenau (WEG_XPATH)
# VZ02 - Auswahl ueber eine Elementgrenze (<b>) hinweg wird ganz eingefaerbt
# VZ03 - Anker loest nicht auf -> Wortlautsuche (WEG_TEXT) MIT Vorbehalt
# VZ04 - weder Anker noch Wortlaut -> WEG_KEINER, Beleg bleibt bestehen (GR1)
# VZ05 - Markierung in der Uebersetzung -> WEG_UEBERSETZUNG, eigener Hinweis
# VZ06 - zwei Markierungen im selben Absatz: beide Farben, ein Absatz
# VZ07 - ueberlappende Markierungen erzeugen KEINE verschachtelten <span>
# VZ08 - der Seitenabzug wird nicht veraendert (Kopie, nicht Original)
# VZ09 - Wortlautsuche bleibt im richtigen Beitrag (element_id grenzt ein)
# VZ10 - selection_json liest 'textContent' UND 'text'
#
# -- Quellenkunde ------------------------------------------------------------
# VZ11 - Forenbeitrag: Betreff aus uid_topics, Datum aus uid_posts
# VZ12 - private Nachricht: Partner und Betreff aus uid_pms_posts
# VZ13 - fehlende Spalte 'partner_username' wird BENANNT, nicht geraten
# VZ14 - PN und Beitrag mit gleicher Nummer bleiben getrennt (ID-Raeume)
# VZ15 - Beleg ohne Beitragsbezug: Warnung, aber Fundstelle bleibt
#
# -- Ermittlername -----------------------------------------------------------
# VZ16 - AD-Felder gesetzt: "KHK Muster", Quelle 'ad_felder'
# VZ17 - AD-Felder leer: Rueckfall auf display_name bis zum Komma
# VZ18 - Dienstgrad leer -> entfaellt ersatzlos
# VZ19 - unbekanntes Kuerzel bleibt stehen, Quelle 'kuerzel'
# VZ20 - ohne Komma wird NICHTS geraten
#
# -- Bauer und Zusammenfassung ----------------------------------------------
# VZ21 - zwei Belege im selben Beitrag -> EIN Unterblock, EIN Datum, EIN Link
# VZ22 - Reihenfolge der Unterbloecke ist die des Bearbeiters
# VZ23 - fehlende Annotation wird ausgewiesen, nicht uebersprungen (GR1)
# VZ24 - unbekannte Kategorie wird benannt und neutral eingefaerbt
#
# -- Darstellungsvariante ----------------------------------------------------
# VZ25 - normalisiere() bildet unbekannte Werte auf die Vorgabe 'list' ab
# VZ26 - nur 'fullquote' braucht den Absatz
#
# -- Wirkung im Bericht ------------------------------------------------------
# VZ27 - HTML: Rahmen, Quellenart, Originaldatum, Link, Farbe, Nachname, Notiz
# VZ28 - HTML: das Annotationsdatum steht NICHT im Bericht
# VZ29 - die Warnungen landen im Abschnitt "Hinweise zur Erzeugung" (R2)
# VZ30 - GEGENPROBE: ohne Vollzitat-Modus bleibt es bei "Beweis-IDs: ..."
# VZ31 - Klartextfassung traegt dieselben Aussagen wie das HTML
# VZ32 - Themenbetreff mit '<' wird escaped (ein Forum ist voll davon)
#
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

from __future__ import annotations

import json
import sqlite3
import sys
import time
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import kategorie_farben
from report_render import beleg_darstellung
from report_render.absatz_finder import (
    AbsatzFinder,
    Markierung,
    WEG_KEINER,
    WEG_TEXT,
    WEG_UEBERSETZUNG,
    WEG_XPATH,
    _klartext,
    auswahl_text,
)
from report_render.beleg_darstellung import (
    GRUPPE_FELD, MODUS_FELD, MODUS_VOLLZITAT,
)
from report_render.ermittler_namen import (
    ErmittlerNamen,
    QUELLE_AD,
    QUELLE_DISPLAY,
    QUELLE_KUERZEL,
    nachname_aus_display_name,
)
from report_render.html_renderer import HtmlRenderer
from report_render.quellen_kunde import QuellenKunde
from report_render.report_document import (
    ReportDocument, RenderedBlock, WARN_EVIDENCE_GAP,
)
from report_render.vollzitat_bauer import VollzitatBauer
from report_render.vollzitat_klartext import klartext

# ---------------------------------------------------------------------------
# Vorrichtungen
# ---------------------------------------------------------------------------

#: Ein Seitenabzug mit ZWEI Beitraegen. Der zweite enthaelt denselben
#: Wortlaut wie der erste - so laesst sich pruefen, dass die Wortlautsuche
#: nicht in den falschen Beitrag laeuft (VZ09).
BODY = (
    '<div id="p100" class="blockpost rowodd">'
    '<h2><span>#1</span></h2>'
    '<div class="box"><div class="inbox"><div class="postbody">'
    '<div class="postleft"><dl><dt><strong>kirschbaum_71</strong></dt></dl></div>'
    '<div class="postright"><div class="postmsg">'
    '<p>Ich fahre Samstag los, von Bad Honnef aus.</p>'
    '<p>Mein <b>Bruder</b> kommt mit.</p>'
    '</div></div></div></div></div></div>'
    '<div id="p101" class="blockpost roweven">'
    '<h2><span>#2</span></h2>'
    '<div class="box"><div class="inbox"><div class="postbody">'
    '<div class="postright"><div class="postmsg">'
    '<p>Ich fahre Samstag los, von Bad Honnef aus.</p>'
    '</div></div></div></div></div>'
)
SEITE = ("<html><head><title>t</title></head><body>"
         + BODY + "</body></html>").encode("utf-8")

SEITEN_URL = "/forum/viewtopic.php?id=41623&p=3"
PN_URL = "/forum/pmsnew.php?mdl=topic&tid=8127"


def _pfad(finder, index):
    """Der XPath eines <p> im Finder - so, wie toolbar.js ihn schriebe."""
    baum = finder._wurzel.getroottree()
    wurzel = baum.getpath(finder._wurzel)
    ziel = baum.getpath(list(finder._wurzel.iter("p"))[index])
    return "." + ziel[len(wurzel):]


def _finder():
    return AbsatzFinder(BODY)


def _sel(pfad, von, bis, text):
    return {"xpathStart": pfad + "/text()[1]", "offsetStart": von,
            "xpathEnd": pfad + "/text()[1]", "offsetEnd": bis,
            "textContent": text}


class _FakeForensic:
    """Liefert den Seitenabzug - wie ForensicDb.get_page()."""

    def __init__(self, seiten=None):
        self._seiten = seiten if seiten is not None else {SEITEN_URL: SEITE}

    def get_page(self, url, method="GET"):
        roh = self._seiten.get(url)
        return types.SimpleNamespace(html=roh) if roh else None


class _FakeEvidence:
    def __init__(self, annotationen):
        self._a = list(annotationen)

    def get_all_annotationen(self):  # pragma: no cover - Schreibfehlerschutz
        raise AssertionError("falscher Methodenname")

    def get_all_annotations(self):
        return self._a


def _ann(ident, kategorie, selection, notiz, created_by,
         post_id=100, page_url=SEITEN_URL):
    """Ein AnnotationRecord-Ersatz mit genau den gelesenen Feldern."""
    return types.SimpleNamespace(
        id=ident, page_url=page_url, element_id="p%d" % post_id,
        category=kategorie, text=notiz, ts=1787832000, investigator_id=None,
        selection_json=json.dumps(selection) if selection else None,
        tags_json=None, local_id=None, post_id=post_id,
        created_by=created_by, deleted_at=None, version_nr=1,
        prev_id=None, actual_uid=None)


def _con(mit_partner=True, mit_person=True):
    """Eine Verbindung mit den ATTACH-Aliasen fdb und cdb."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("ATTACH DATABASE ':memory:' AS fdb")
    con.execute("ATTACH DATABASE ':memory:' AS cdb")
    con.execute("CREATE TABLE fdb.uid_posts (post_id INTEGER PRIMARY KEY, "
                "topic_id INT, forum_id INT, posted_ts INT)")
    con.execute("CREATE TABLE fdb.uid_topics (topic_id INTEGER PRIMARY KEY, "
                "subject TEXT, forum_id INT)")
    con.execute("CREATE TABLE fdb.post_aliases (post_id INTEGER PRIMARY KEY, "
                "topic_id INT, forum_id INT)")
    partner = ", partner_user_id INT, partner_username TEXT" if mit_partner else ""
    con.execute("CREATE TABLE fdb.uid_pms_posts (pm_post_id INTEGER PRIMARY "
                "KEY, pm_topic_id INT, topic_subject TEXT, posted_ts INT%s)"
                % partner)
    con.execute("INSERT INTO fdb.uid_posts VALUES (100, 41623, 7, 1710452820)")
    con.execute("INSERT INTO fdb.uid_posts VALUES (101, 41623, 7, 1710453000)")
    con.execute("INSERT INTO fdb.uid_topics VALUES "
                "(41623, 'Wochenendtreffen im Sueden', 7)")
    if mit_partner:
        con.execute("INSERT INTO fdb.uid_pms_posts VALUES "
                    "(100, 8127, 'wegen Samstag', 1712034720, 99, "
                    "'apfelernte_2019')")
    else:
        con.execute("INSERT INTO fdb.uid_pms_posts VALUES "
                    "(100, 8127, 'wegen Samstag', 1712034720)")
    if mit_person:
        con.execute("CREATE TABLE cdb.person (id INTEGER PRIMARY KEY, "
                    "system_username TEXT, display_name TEXT, "
                    "first_name TEXT, last_name TEXT, rank TEXT)")
        con.execute("INSERT INTO cdb.person VALUES "
                    "(1,'h0erm','Bergmann, Rita','Rita','Bergmann','KHK')")
        con.execute("INSERT INTO cdb.person (id, system_username, "
                    "display_name) VALUES (2,'h0chef','Okonkwo, Ada')")
        con.execute("INSERT INTO cdb.person VALUES "
                    "(3,'h0ohne','Chefin',NULL,NULL,NULL)")
    return con


# ===========================================================================
class AbsatzFinderTests(unittest.TestCase):

    def test_vz01_anker_loest_auf(self):
        f = _finder()
        p = _pfad(f, 0)
        fs = f.finde(_sel(p, 27, 37, "Bad Honnef"), "p100")
        self.assertEqual(WEG_XPATH, fs.weg)
        self.assertEqual("p", fs.block.tag)
        self.assertEqual("Bad Honnef", _klartext(fs.block)[fs.von:fs.bis])
        self.assertEqual("", fs.hinweis,
                         "Der Sollweg darf keinen Vorbehalt tragen.")

    def test_vz02_auswahl_ueber_elementgrenze(self):
        f = _finder()
        p = _pfad(f, 1)
        sel = {"xpathStart": p + "/text()[1]", "offsetStart": 0,
               "xpathEnd": p + "/b[1]/text()[1]", "offsetEnd": 6,
               "textContent": "Mein Bruder"}
        fs = f.finde(sel, "p100")
        self.assertEqual(WEG_XPATH, fs.weg)
        self.assertEqual("Mein Bruder", _klartext(fs.block)[fs.von:fs.bis])
        html = f.rendere(fs.block, [Markierung(
            fs.von, fs.bis, "vz-cat-CAT_PERSON", "#fcf1d0", 1)])
        # Beide Teilstuecke sind eingefaerbt - das vor und das im <b>.
        self.assertEqual(2, html.count("vz-cat-CAT_PERSON"),
                         "Eine Auswahl ueber eine Elementgrenze muss in "
                         "BEIDEN Textknoten hinterlegt werden.")

    def test_vz03_wortlautsuche_mit_vorbehalt(self):
        f = _finder()
        fs = f.finde({"xpathStart": "./div[9]/p[7]/text()[1]",
                      "offsetStart": 0, "textContent": "Bad Honnef"}, "p100")
        self.assertEqual(WEG_TEXT, fs.weg)
        self.assertEqual("Bad Honnef", _klartext(fs.block)[fs.von:fs.bis])
        self.assertIn("Wortlaut", fs.hinweis,
                      "Der schwaechere Weg muss BENANNT werden.")

    def test_vz04_nichts_gefunden_beleg_bleibt(self):
        f = _finder()
        fs = f.finde({"xpathStart": "./div[9]/p[7]/text()[1]",
                      "textContent": "kommt hier nicht vor"}, "p100")
        self.assertEqual(WEG_KEINER, fs.weg)
        self.assertIsNone(fs.block)
        # GR1: der markierte Wortlaut geht NICHT verloren.
        self.assertEqual("kommt hier nicht vor", fs.text)
        self.assertTrue(fs.hinweis)

    def test_vz05_uebersetzungsauswahl(self):
        f = _finder()
        fs = f.finde({"target": "translation", "charStart": 3, "charEnd": 9,
                      "textContent": "Bad Honnef"}, "p100")
        self.assertEqual(WEG_UEBERSETZUNG, fs.weg)
        self.assertIsNone(fs.block)
        self.assertIn("Uebersetzung", fs.hinweis)
        self.assertEqual("Bad Honnef", fs.text)

    def test_vz06_zwei_markierungen_ein_absatz(self):
        f = _finder()
        p = _pfad(f, 0)
        a = f.finde(_sel(p, 27, 37, "Bad Honnef"), "p100")
        b = f.finde(_sel(p, 0, 10, "Ich fahre "), "p100")
        html = f.rendere(a.block, [
            Markierung(a.von, a.bis, "vz-cat-CAT_LOCATION", "#d3e3fd", 1),
            Markierung(b.von, b.bis, "vz-cat-CAT_PERSON", "#fcf1d0", 2)])
        self.assertIn("#d3e3fd", html)
        self.assertIn("#fcf1d0", html)
        self.assertEqual(1, html.count("<p>"),
                         "Der Absatz darf nur EINMAL gedruckt werden.")

    def test_vz07_ueberlappung_ohne_verschachtelung(self):
        f = _finder()
        p = _pfad(f, 0)
        block = f.finde(_sel(p, 0, 10, "Ich fahre "), "p100").block
        html = f.rendere(block, [
            Markierung(0, 20, "vz-cat-CAT_176", "#f9cfcf", 1),
            Markierung(10, 30, "vz-cat-CAT_184", "#efcff9", 2)])
        self.assertNotIn('#f9cfcf;" data-beleg="1"><span', html,
                         "Verschachtelte Hinterlegungen verdecken einander.")
        self.assertIn("#f9cfcf", html)
        self.assertIn("#efcff9", html)

    def test_vz08_seitenabzug_bleibt_unveraendert(self):
        f = _finder()
        p = _pfad(f, 0)
        fs = f.finde(_sel(p, 27, 37, "Bad Honnef"), "p100")
        vorher = _klartext(fs.block)
        f.rendere(fs.block, [Markierung(fs.von, fs.bis,
                                        "vz-cat-CAT_LOCATION", "#d3e3fd", 1)])
        f.rendere(fs.block, [Markierung(fs.von, fs.bis,
                                        "vz-cat-CAT_LOCATION", "#d3e3fd", 1)])
        self.assertEqual(vorher, _klartext(fs.block),
                         "Der gesicherte Seitenabzug ist forensisch "
                         "unverletzlich - gearbeitet wird auf einer Kopie.")

    def test_vz09_wortlautsuche_bleibt_im_beitrag(self):
        # Derselbe Satz steht in p100 UND in p101. Ohne Eingrenzung kann die
        # Suche den falschen Beitrag treffen - auf einer Themenseite mit 500
        # Beitraegen ist das ein realer Fall.
        f = _finder()
        fs = f.finde({"xpathStart": "./kaputt", "textContent": "Bad Honnef"},
                     "p101")
        self.assertEqual(WEG_TEXT, fs.weg)
        vorfahr = fs.block
        while vorfahr is not None and vorfahr.get("id") is None:
            vorfahr = vorfahr.getparent()
        self.assertEqual("p101", vorfahr.get("id"))

    def test_vz10_auswahl_text_liest_beide_felder(self):
        # Der Schreiber legt 'textContent' ab, der Berichtseditor liest
        # 'text'. Der Bericht muss beides koennen.
        self.assertEqual("A", auswahl_text({"textContent": "A"}))
        self.assertEqual("B", auswahl_text({"text": "B"}))
        self.assertEqual("A", auswahl_text({"textContent": "A", "text": "B"}))
        self.assertEqual("", auswahl_text(None))
        self.assertEqual("", auswahl_text({"_raw": "kaputt"}))


# ===========================================================================
class QuellenKundeTests(unittest.TestCase):

    def test_vz11_beitrag(self):
        q = QuellenKunde(_con()).ermitteln(
            page_url=SEITEN_URL, post_id=100, element_id="p100")
        self.assertFalse(q.ist_pn)
        self.assertEqual("Wochenendtreffen im Sueden", q.betreff)
        self.assertEqual(1710452820, q.posted_ts)
        self.assertEqual(SEITEN_URL + "#p100", q.link)
        self.assertEqual([], q.warnungen)
        self.assertIn("Beitrag zum Thema", q.bezeichnung())

    def test_vz12_private_nachricht(self):
        q = QuellenKunde(_con()).ermitteln(
            page_url=PN_URL, post_id=100, element_id="p100")
        self.assertTrue(q.ist_pn)
        self.assertEqual("apfelernte_2019", q.partner)
        self.assertEqual("wegen Samstag", q.betreff)
        self.assertEqual(1712034720, q.posted_ts)
        self.assertEqual("Private Nachricht mit »apfelernte_2019«",
                         q.bezeichnung())

    def test_vz13_fehlende_partnerspalte_wird_benannt(self):
        q = QuellenKunde(_con(mit_partner=False)).ermitteln(
            page_url=PN_URL, post_id=100, element_id="p100")
        self.assertIsNone(q.partner)
        self.assertIn("nicht ermittelbar", q.bezeichnung())
        text = " ".join(q.warnungen)
        self.assertIn("partner_username", text)
        self.assertIn("Prepper", text,
                      "Die Warnung muss sagen, WIE der Mangel zu beheben ist.")

    def test_vz14_id_raeume_bleiben_getrennt(self):
        # Beitrag 100 und Nachricht 100 sind zwei verschiedene Dinge.
        kunde = QuellenKunde(_con())
        beitrag = kunde.ermitteln(page_url=SEITEN_URL, post_id=100,
                                  element_id="p100")
        pn = kunde.ermitteln(page_url=PN_URL, post_id=100, element_id="p100")
        self.assertNotEqual(beitrag.posted_ts, pn.posted_ts)
        self.assertEqual("Wochenendtreffen im Sueden", beitrag.betreff)
        self.assertEqual("wegen Samstag", pn.betreff)

    def test_vz15_ohne_beitragsbezug(self):
        q = QuellenKunde(_con()).ermitteln(
            page_url="/forum/index.php", post_id=None, element_id=None)
        self.assertEqual("/forum/index.php", q.link)
        self.assertTrue(q.warnungen)
        self.assertIn("ohne Beitragsbezug", q.warnungen[0])


# ===========================================================================
class ErmittlerNamenTests(unittest.TestCase):

    def test_vz16_ad_felder(self):
        name = ErmittlerNamen(_con()).aufloesen("h0erm")
        self.assertEqual("Bergmann", name.nachname)
        self.assertEqual("KHK", name.rang)
        self.assertEqual("KHK Bergmann", name.anzeige)
        self.assertEqual(QUELLE_AD, name.quelle)
        self.assertTrue(name.ist_gesichert)
        self.assertNotIn("Rita", name.anzeige,
                         "Der Vorname gehoert nicht in den Bericht.")

    def test_vz17_rueckfall_auf_display_name(self):
        name = ErmittlerNamen(_con()).aufloesen("h0chef")
        self.assertEqual("Okonkwo", name.nachname)
        self.assertEqual("Okonkwo", name.anzeige)
        self.assertEqual(QUELLE_DISPLAY, name.quelle)
        self.assertFalse(name.ist_gesichert,
                         "Ein zerlegter Name ist kein gelesener.")

    def test_vz18_ohne_dienstgrad(self):
        con = _con()
        con.execute("UPDATE cdb.person SET rank='' WHERE system_username='h0erm'")
        name = ErmittlerNamen(con).aufloesen("h0erm")
        self.assertEqual("Bergmann", name.anzeige)
        self.assertEqual("", name.rang)

    def test_vz19_unbekanntes_kuerzel_bleibt_stehen(self):
        name = ErmittlerNamen(_con()).aufloesen("h9999")
        self.assertEqual("h9999", name.anzeige)
        self.assertEqual(QUELLE_KUERZEL, name.quelle)
        # Und ein leeres created_by darf nicht stolpern.
        leer = ErmittlerNamen(_con()).aufloesen("")
        self.assertEqual("", leer.anzeige)

    def test_vz20_ohne_komma_wird_nichts_geraten(self):
        self.assertEqual("Muster", nachname_aus_display_name("Muster, Max"))
        self.assertEqual("Chefin", nachname_aus_display_name("Chefin"))
        # Das letzte Wort zu nehmen waere die naheliegende falsche Regel:
        self.assertEqual("Muster zu Guttenberg",
                         nachname_aus_display_name("Muster zu Guttenberg"))
        self.assertEqual("", nachname_aus_display_name(""))


# ===========================================================================
class VollzitatBauerTests(unittest.TestCase):

    def _bauer(self, annotationen, con=None, forensic=None):
        return VollzitatBauer(
            evidence=_FakeEvidence(annotationen),
            forensic=forensic if forensic is not None else _FakeForensic(),
            con=con if con is not None else _con())

    def _zwei_im_selben_beitrag(self):
        f = _finder()
        p0, p1 = _pfad(f, 0), _pfad(f, 1)
        return [
            _ann(4711, "CAT_LOCATION", _sel(p0, 27, 37, "Bad Honnef"),
                 "Ausgangsort.", "h0erm"),
            _ann(4712, "CAT_PERSON",
                 {"xpathStart": p1 + "/text()[1]", "offsetStart": 0,
                  "xpathEnd": p1 + "/b[1]/text()[1]", "offsetEnd": 6,
                  "textContent": "Mein Bruder"},
                 "Begleitperson.", "h0erm"),
        ]

    def test_vz21_zusammenfassung_je_beitrag(self):
        g = self._bauer(self._zwei_im_selben_beitrag()).baue([4711, 4712], "S")
        self.assertEqual(1, g.quellen_anzahl,
                         "Zwei Belege desselben Beitrags gehoeren in EINEN "
                         "Unterblock (Anforderung 9).")
        ub = g.unterbloecke[0]
        self.assertEqual(2, len(ub.befunde))
        self.assertEqual([1, 2], [b.nummer for b in ub.befunde])
        self.assertEqual(2, len(ub.absaetze),
                         "Zwei verschiedene Absaetze desselben Beitrags.")
        # Quellenangabe, Datum und Link stehen genau EINMAL - am Unterblock.
        self.assertEqual(1710452820, ub.quelle.posted_ts)
        self.assertEqual(SEITEN_URL + "#p100", ub.quelle.link)

    def test_vz22_reihenfolge_ist_die_des_bearbeiters(self):
        f = _finder()
        p0 = _pfad(f, 0)
        annos = self._zwei_im_selben_beitrag() + [
            _ann(4730, "CAT_OTHER", _sel(p0, 0, 9, "Ich fahre"),
                 "PN-Beleg.", "h0chef", post_id=100, page_url=PN_URL)]
        g = self._bauer(annos).baue([4730, 4711, 4712], "S")
        self.assertTrue(g.unterbloecke[0].quelle.ist_pn,
                        "Der zuerst genannte Beleg bestimmt die Reihenfolge.")
        self.assertFalse(g.unterbloecke[1].quelle.ist_pn)

    def test_vz23_fehlende_annotation_wird_ausgewiesen(self):
        g = self._bauer(self._zwei_im_selben_beitrag()).baue([4711, 9999], "S")
        self.assertEqual(2, g.beleg_anzahl)
        nummern = [bf.annotation_id
                   for ub in g.unterbloecke for bf in ub.befunde]
        self.assertIn(9999, nummern,
                      "GR1: kein Beleg darf still uebersprungen werden.")
        self.assertTrue(any("9999" in w for w in g.warnungen))

    def test_vz24_unbekannte_kategorie(self):
        f = _finder()
        p0 = _pfad(f, 0)
        a = [_ann(4711, "CAT_XY", _sel(p0, 27, 37, "Bad Honnef"),
                  "Notiz.", "h0erm")]
        g = self._bauer(a).baue([4711], "S")
        bf = g.unterbloecke[0].befunde[0]
        self.assertIn("CAT_XY", bf.kategorie_text)
        self.assertEqual(kategorie_farben.UNBEKANNT_HINTERLEGUNG, bf.farbe)
        self.assertTrue(any("CAT_XY" in w for w in g.warnungen))


# ===========================================================================
class DarstellungsvarianteTests(unittest.TestCase):

    def test_vz25_normalisieren(self):
        self.assertEqual("fullquote",
                         beleg_darstellung.normalisiere("fullquote"))
        for unfug in (None, "", "Vollzitat", 7, ["list"]):
            with self.subTest(wert=unfug):
                self.assertEqual(beleg_darstellung.MODUS_VORGABE,
                                 beleg_darstellung.normalisiere(unfug))
        self.assertEqual("Vollzitat", beleg_darstellung.bezeichnung("fullquote"))
        # Ein Block ohne 'display_mode' bleibt Liste - keine stille Aenderung
        # des Aussehens aller Bestandsberichte.
        self.assertEqual("list", beleg_darstellung.aus_daten({}))
        self.assertEqual("list", beleg_darstellung.aus_daten({"_raw": "x"}))

    def test_vz26_nur_vollzitat_braucht_den_absatz(self):
        self.assertTrue(beleg_darstellung.braucht_absatz("fullquote"))
        for anderer in ("list", "table", "quote", None):
            with self.subTest(modus=anderer):
                self.assertFalse(beleg_darstellung.braucht_absatz(anderer))


# ===========================================================================
class BerichtTests(unittest.TestCase):

    def _dokument(self, modus=MODUS_VOLLZITAT, betreff=None):
        f = _finder()
        p0, p1 = _pfad(f, 0), _pfad(f, 1)
        annos = [
            _ann(4711, "CAT_LOCATION", _sel(p0, 27, 37, "Bad Honnef"),
                 "Ausgangsort, nicht Ziel.", "h0erm"),
            _ann(4712, "CAT_PERSON",
                 {"xpathStart": p1 + "/text()[1]", "offsetStart": 0,
                  "xpathEnd": p1 + "/b[1]/text()[1]", "offsetEnd": 6,
                  "textContent": "Mein Bruder"},
                 "Begleitperson.", "h0erm"),
        ]
        con = _con()
        if betreff is not None:
            con.execute("UPDATE fdb.uid_topics SET subject=? WHERE topic_id=41623",
                        (betreff,))
        bauer = VollzitatBauer(evidence=_FakeEvidence(annos),
                               forensic=_FakeForensic(), con=con)
        gruppe = bauer.baue([4711, 4712], "Ortsbezuege")
        daten = {"evidence_ids": [4711, 4712], "group_label": "Ortsbezuege",
                 MODUS_FELD: modus}
        if modus == MODUS_VOLLZITAT:
            daten[GRUPPE_FELD] = gruppe
        blk = RenderedBlock(block_id="b1", block_type="evidence", data=daten,
                            resolved_text="", resolved_text_plain="",
                            is_known_type=True)
        doc = ReportDocument(report_id=1, report_type="interim",
                             sequence_nr=1, title="Probe", status="draft",
                             uid=700, username="kirschbaum_71",
                             generated_at=1787832000)
        doc.blocks = [blk]
        for w in gruppe.warnungen:
            doc.add_warning(WARN_EVIDENCE_GAP, w, block_id="b1")
        return doc, gruppe

    def test_vz27_html_traegt_alle_neun_anforderungen(self):
        doc, _g = self._dokument()
        html = HtmlRenderer().render(doc).decode("utf-8")
        rumpf = html[html.index("<body>"):]
        # 1 Nachname statt Kuerzel
        self.assertIn("KHK Bergmann", rumpf)
        self.assertNotIn("h0erm", rumpf,
                         "Der SAMAccountName gehoert nicht in die Akte.")
        # 2 der ganze Absatz
        self.assertIn("Ich fahre Samstag los, von", html)
        # 3 Farbe der Kategorie
        self.assertIn(kategorie_farben.hinterlegung("CAT_LOCATION"), html)
        self.assertIn(kategorie_farben.hinterlegung("CAT_PERSON"), html)
        # 4 Originaldatum der Quelle
        self.assertIn("14.03.2024", html)
        # 5 der Link
        self.assertIn("viewtopic.php?id=41623", html)
        self.assertIn("#p100", html)
        # 6 als Gruppe erkennbar
        self.assertIn("vz-gruppe", html)
        # 7 Art der Quelle
        self.assertIn("Beitrag zum Thema", html)
        self.assertIn("Wochenendtreffen im Sueden", html)
        # 8 die Notiz
        self.assertIn("Ausgangsort, nicht Ziel.", html)
        # 9 ein Unterblock, also EINE Fundstellenzeile
        self.assertEqual(1, rumpf.count("Fundstelle:"))

    def test_vz28_annotationsdatum_steht_nicht_im_bericht(self):
        # annotations.ts = 27.08.2026. Es darf NICHT als Quellendatum
        # erscheinen - das ist die ganze Anforderung 4.
        doc, _g = self._dokument()
        html = HtmlRenderer().render(doc).decode("utf-8")
        rumpf = html[html.index("<body>"):]
        gruppe_html = rumpf[rumpf.index("vz-gruppe"):
                            rumpf.index('<div class="hints"')]
        self.assertNotIn("27.08.2026", gruppe_html)
        self.assertIn("14.03.2024", gruppe_html)

    def test_vz29_warnungen_landen_im_hinweisabschnitt(self):
        f = _finder()
        p0 = _pfad(f, 0)
        annos = [_ann(4711, "CAT_LOCATION",
                      {"xpathStart": "./kaputt", "textContent": "gibt es nicht"},
                      "Notiz.", "h0erm")]
        bauer = VollzitatBauer(evidence=_FakeEvidence(annos),
                               forensic=_FakeForensic(), con=_con())
        gruppe = bauer.baue([4711], "S")
        blk = RenderedBlock(
            block_id="b1", block_type="evidence",
            data={"evidence_ids": [4711], MODUS_FELD: MODUS_VOLLZITAT,
                  GRUPPE_FELD: gruppe},
            resolved_text="", resolved_text_plain="", is_known_type=True)
        doc = ReportDocument(report_id=1, report_type="interim",
                             sequence_nr=1, title="P", status="draft",
                             uid=700, username="x", generated_at=1787832000)
        doc.blocks = [blk]
        for w in gruppe.warnungen:
            doc.add_warning(WARN_EVIDENCE_GAP, w, block_id="b1")
        self.assertTrue(doc.warnings)
        html = HtmlRenderer().render(doc).decode("utf-8")
        self.assertIn("Hinweise zur Erzeugung", html)
        self.assertIn("Beleglage unvollst", html)

    def test_vz30_gegenprobe_ohne_vollzitat(self):
        """
        Ein Test, der nicht anschlagen kann, ist kein Test.

        Ohne den Vollzitat-Modus muss der Bericht die ALTE Ausgabe zeigen -
        sonst prueft VZ27 nur, dass irgendwo Text steht.
        """
        doc, _g = self._dokument(modus="list")
        html = HtmlRenderer().render(doc).decode("utf-8")
        # NUR DEN RUMPF PRUEFEN: der Stilblock im Kopf traegt die
        # vz-Klassen IMMER (er ist eine feste Zeichenkette). Ein
        # Gegentest gegen das ganze Dokument haette hier nichts gezeigt
        # ausser der Anwesenheit von CSS.
        rumpf = html[html.index("<body>"):]
        self.assertIn("Beweis-IDs: 4711, 4712", rumpf)
        self.assertNotIn("vz-gruppe-kopf", rumpf)
        self.assertNotIn("KHK Bergmann", rumpf)
        self.assertNotIn("Wochenendtreffen", rumpf)

    def test_vz31_klartext_traegt_dieselben_aussagen(self):
        _doc, gruppe = self._dokument()
        text = klartext(gruppe)
        for erwartet in ("KHK Bergmann", "Wochenendtreffen im Sueden",
                         "14.03.2024", "viewtopic.php?id=41623",
                         "Ausgangsort, nicht Ziel.", "Bad Honnef"):
            with self.subTest(inhalt=erwartet):
                self.assertIn(erwartet, text,
                              "DOCX/PDF/SQLite duerfen nicht weniger wissen "
                              "als der HTML-Bericht.")

    def test_vz32_betreff_wird_escaped(self):
        doc, _g = self._dokument(betreff='Wer <b>weiss</b> was & wo?')
        html = HtmlRenderer().render(doc).decode("utf-8")
        self.assertIn("Wer &lt;b&gt;weiss&lt;/b&gt; was &amp; wo?", html)
        self.assertNotIn("<b>weiss</b>", html)


if __name__ == "__main__":
    unittest.main()


# ===========================================================================
# Build 727 - Befunde aus der Sichtpruefung vom 28.08.2026
# ===========================================================================
#
# VZ33 - post_id aus dem Seitenabzug abgeleitet, wenn die Annotation keine hat
# VZ34 - DIE KERNRUECKGEWINNUNG: zwei Belege ohne post_id im selben Beitrag
#        landen wieder in EINEM Unterblock, mit Betreff und Originaldatum
# VZ35 - mehrdeutiger Wortlaut: ALLE Fundstellen, und KEINE Ableitung
# VZ36 - ein Beleg, den es nicht mehr gibt, bekommt keine erfundene Quellenart
# VZ37 - gleichlautende Warnungen werden zu einer Zeile mit Belegliste
# VZ38 - der Weg zur Beitragsnummer wird im Bericht ausgewiesen
# VZ39 - GEGENPROBE: eine Annotation MIT post_id wird nicht abgeleitet

from report_render.absatz_finder import WEG_FEHLT
from report_render.quellen_kunde import (
    ART_UNBEKANNT, POST_AUS_ANNOTATION, POST_AUS_SEITENABZUG,
)


class SichtpruefungTests(unittest.TestCase):
    """
    Der Auszug einer echten Beweismittelgruppe vom 28.08.2026 zeigte: bei
    ALLEN 23 Belegen war 'post_id' leer - toolbar.js setzt sie fuer
    Textmarkierungen bewusst nicht (Build 336). Daran fielen fuenf der neun
    Anforderungen auf einmal.
    """

    def _bauer(self, annotationen, con=None):
        return VollzitatBauer(evidence=_FakeEvidence(annotationen),
                              forensic=_FakeForensic(),
                              con=con if con is not None else _con())

    def _ann_ohne_post(self, ident, text_der_markierung, kategorie="CAT_OTHER"):
        """Eine Textmarkierung, wie die Toolbar sie bis Build 726 anlegt."""
        a = _ann(ident, kategorie,
                 {"xpathStart": "./laeuft/ins/leere", "offsetStart": 0,
                  "textContent": text_der_markierung},
                 "Notiz zu %d." % ident, "h0erm")
        a.post_id = None
        a.element_id = None
        return a

    # -- VZ33 --------------------------------------------------------------
    def test_vz33_post_id_aus_dem_seitenabzug(self):
        # 'Mein Bruder' kommt in der Vorrichtung NUR in p100 vor - die
        # Fundstelle ist damit eindeutig und die Ableitung zulaessig.
        annos = [self._ann_ohne_post(4711, "Mein Bruder")]
        g = self._bauer(annos).baue([4711], "S")
        q = g.unterbloecke[0].quelle
        self.assertEqual(100, q.post_id,
                         "Der Absatz sitzt in <div id='p100'> - das IST der "
                         "Beitrag.")
        self.assertEqual(POST_AUS_SEITENABZUG, q.post_quelle)
        self.assertEqual("Wochenendtreffen im Sueden", q.betreff)
        self.assertEqual(1710452820, q.posted_ts)
        self.assertIn("#p100", q.link)

    # -- VZ34 --------------------------------------------------------------
    def test_vz34_zwei_belege_ohne_post_id_ein_unterblock(self):
        """
        Der eigentliche Befund: bis Build 726 bekam JEDER Beleg einen eigenen
        Kasten, weil der Schluessel ('einzeln', beleg_id) lautete. Derselbe
        Absatz stand dann mehrfach untereinander.
        """
        annos = [self._ann_ohne_post(4711, "Mein Bruder"),
                 self._ann_ohne_post(4712, "kommt mit")]
        g = self._bauer(annos).baue([4711, 4712], "S")
        self.assertEqual(1, g.quellen_anzahl,
                         "Beide Markierungen stehen im selben Beitrag und "
                         "gehoeren in EINEN Unterblock (Anforderung 9).")
        ub = g.unterbloecke[0]
        self.assertEqual([1, 2], [b.nummer for b in ub.befunde])
        self.assertEqual(1, len(ub.absaetze),
                         "Beide Markierungen sitzen im selben Absatz - er "
                         "darf nur EINMAL gedruckt werden.")
        # Und BEIDE Belege sind darin hinterlegt. Gezaehlt wird ueber
        # 'data-beleg', nicht ueber die Zahl der <span>: 'Mein Bruder' laeuft
        # ueber die <b>-Grenze und wird deshalb in ZWEI Stuecken eingefaerbt
        # (so gewollt, s. VZ02).
        html = ub.absaetze[0].html
        self.assertIn('data-beleg="1"', html)
        self.assertIn('data-beleg="2"', html)
        self.assertEqual("Wochenendtreffen im Sueden", ub.quelle.betreff)
        self.assertEqual(1710452820, ub.quelle.posted_ts)

    # -- VZ35 --------------------------------------------------------------
    def test_vz35_mehrdeutiger_wortlaut(self):
        # 'Ich fahre Samstag los, von Bad Honnef aus.' steht in BODY zweimal:
        # einmal in p100, einmal in p101.
        annos = [self._ann_ohne_post(4711, "Ich fahre Samstag los")]
        g = self._bauer(annos).baue([4711], "S")
        ub = g.unterbloecke[0]
        self.assertEqual(2, len(ub.absaetze),
                         "Beide moeglichen Fundstellen gehoeren gezeigt.")
        for a in ub.absaetze:
            with self.subTest(nummern=a.nummern):
                self.assertTrue(a.moeglich)
                self.assertIsNotNone(a.von_gesamt)
        self.assertEqual([(1, 2), (2, 2)],
                         [a.von_gesamt for a in ub.absaetze])
        # KEINE Ableitung bei Mehrdeutigkeit - sie waere geraten.
        self.assertIsNone(ub.quelle.post_id)
        self.assertTrue(any("2 MAL" in w for w in g.warnungen))

    # -- VZ36 --------------------------------------------------------------
    def test_vz36_fehlbeleg_ohne_erfundene_quellenart(self):
        g = self._bauer([]).baue([14], "S")
        ub = g.unterbloecke[0]
        self.assertEqual(ART_UNBEKANNT, ub.quelle.art)
        self.assertTrue(ub.fehlt)
        self.assertEqual("Beleg nicht mehr vorhanden", ub.quelle.bezeichnung())
        self.assertNotIn("Beitrag zum Thema", ub.quelle.bezeichnung())
        self.assertEqual(WEG_FEHLT, ub.befunde[0].absatz_weg)
        # Und im Bericht steht der wahre Grund, nicht 'Absatz nicht auffindbar'.
        html = HtmlRenderer()._render_vollzitat(g)
        self.assertIn("Beleg nicht mehr vorhanden", html)
        self.assertIn("keine aktive Annotation", html)
        self.assertNotIn("Beitrag zum Thema", html)
        self.assertNotIn("Datum des Beitrags", html)

    # -- VZ37 --------------------------------------------------------------
    def test_vz37_warnungen_werden_gebuendelt(self):
        annos = [self._ann_ohne_post(i, "gibt es nicht") for i in (1, 2, 3)]
        g = self._bauer(annos).baue([1, 2, 3], "S")
        # Drei Belege, dieselbe Begruendung -> EINE Zeile mit allen Nummern.
        # Drei Belege x zwei Begruendungen waeren SECHS Zeilen gewesen.
        # Gebuendelt sind es ZWEI - je Begruendung eine, mit allen Nummern.
        passend = [w for w in g.warnungen if "#1, #2, #3" in w]
        self.assertEqual(2, len(passend),
                         "Je Begruendung EINE Zeile mit allen Belegen; "
                         "43 Zeilen fuer 23 Belege liest niemand.")
        self.assertEqual(2, len(g.warnungen))
        for zeile in passend:
            with self.subTest(zeile=zeile[:40]):
                self.assertIn("3 Stueck", zeile)
        # Aber keine Beleg-Nummer faellt weg (GR1).
        for nr in ("#1", "#2", "#3"):
            with self.subTest(beleg=nr):
                self.assertTrue(any(nr in w for w in g.warnungen))

    # -- VZ38 --------------------------------------------------------------
    def test_vz38_weg_zur_beitragsnummer_wird_ausgewiesen(self):
        annos = [self._ann_ohne_post(4711, "Mein Bruder")]
        g = self._bauer(annos).baue([4711], "S")
        html = HtmlRenderer()._render_vollzitat(g)
        self.assertIn("aus dem Seitenabzug bestimmt", html)
        from report_render.vollzitat_klartext import klartext
        self.assertIn("aus dem Seitenabzug bestimmt", klartext(g))

    # -- VZ39 --------------------------------------------------------------
    def test_vz39_gegenprobe_post_id_aus_der_annotation(self):
        """
        Ein Test, der nicht anschlagen kann, ist kein Test: traegt die
        Annotation eine post_id, darf NICHT abgeleitet werden - sonst
        koennte die Ableitung eine vorhandene Angabe ueberschreiben.
        """
        f = _finder()
        annos = [_ann(4711, "CAT_LOCATION", _sel(_pfad(f, 0), 27, 37,
                                                 "Bad Honnef"),
                      "Notiz.", "h0erm", post_id=100)]
        g = self._bauer(annos).baue([4711], "S")
        q = g.unterbloecke[0].quelle
        self.assertEqual(100, q.post_id)
        self.assertEqual(POST_AUS_ANNOTATION, q.post_quelle)
        html = HtmlRenderer()._render_vollzitat(g)
        self.assertNotIn("aus dem Seitenabzug bestimmt", html)


# ---------------------------------------------------------------------------
# Build 749 - die Versionskette wird VORWAERTS verfolgt
#
# ALEX' BEFUND vom 31.08.2026: "Es wird die Fehlermeldung 'Beleg nicht mehr
# vorhanden' gebracht, wenn eine Annotation mittlerweile geaendert worden
# ist. Es sollte aber zur neusten Version der Annotation durchgehangelt
# werden. Dafuer sind annotations.version_nr und annotations.prev_id da."
#
# MECHANIK: save_annotation legt bei einer Aenderung einen NEUEN Datensatz an
# (version_nr+1, prev_id = Vorgaenger.id) und setzt beim Vorgaenger
# deleted_at. Der Bauer las nur die aktiven Annotationen; die im Bericht
# verzeichnete ALTE Nummer stand darin nicht mehr.
#
# WARUM DIE MELDUNG TROTZDEM BLEIBT, wenn wirklich geloescht wurde: 'ersetzt'
# und 'geloescht' sehen in der Spalte deleted_at gleich aus und verlangen
# Verschiedenes. Wer beides gleich behandelt, verschweigt entweder eine
# Loeschung oder erfindet einen Beleg.
#
# VZ37  eine geaenderte Annotation wird ueber die Kette gefunden
# VZ38  und die Fortfuehrung wird AUSGEWIESEN, nicht still vollzogen
# VZ39  eine mehrgliedrige Kette wird bis zur aktuellen Fassung verfolgt
# VZ40  GEGENPROBE: wirklich geloescht bleibt 'nicht mehr vorhanden' - und
#       die Meldung sagt jetzt, dass die Kette verfolgt wurde
# VZ41  ein Zyklus laesst den Lauf nicht haengen
# ---------------------------------------------------------------------------

class _FakeEvidenceMitKette(_FakeEvidence):
    """
    Ein Bestand MIT Versionskette - die aktiven Datensaetze und die Kette
    getrennt, genau wie in der echten Datenbank: get_all_annotations liefert
    nur die aktiven, get_current_annotation laeuft ueber alle.
    """

    def __init__(self, alle):
        self._alle = {int(a.id): a for a in alle}
        super().__init__([a for a in alle if a.deleted_at is None])

    def get_current_annotation(self, annotation_id):
        zeile = self._alle.get(int(annotation_id))
        if zeile is None:
            return None, []
        kette = [int(annotation_id)]
        gesehen = {int(annotation_id)}
        while True:
            if zeile.deleted_at is None:
                return zeile, kette
            nachfolger = None
            for a in self._alle.values():
                if a.prev_id == zeile.id:
                    nachfolger = a
                    break
            if nachfolger is None:
                return None, kette
            if int(nachfolger.id) in gesehen or len(kette) > 100:
                return None, kette
            gesehen.add(int(nachfolger.id))
            kette.append(int(nachfolger.id))
            zeile = nachfolger


def _markierung():
    """Eine Auswahl auf dem Beispielabsatz - wie toolbar.js sie schriebe."""
    f = _finder()
    return _sel(_pfad(f, 0), 27, 37, "Bad Honnef")


def _kette(alt_id, neu_id, **kw):
    """Ein Vorgaenger (geloescht) und sein Nachfolger (aktiv)."""
    alt = _ann(alt_id, "CAT_LOCATION", _markierung(), "alte Notiz", "mc", **kw)
    alt.deleted_at = 1787832100
    neu = _ann(neu_id, "CAT_LOCATION", _markierung(), "neue Notiz", "mc", **kw)
    neu.version_nr = 2
    neu.prev_id = alt_id
    return alt, neu


def _baue(evidence, ids):
    con = _con()
    bauer = VollzitatBauer(evidence=evidence, forensic=_FakeForensic(), con=con)
    try:
        return bauer.baue(ids)
    finally:
        con.close()


class VersionsketteTests(unittest.TestCase):

    def test_vz37_geaenderte_annotation_wird_gefunden(self):
        alt, neu = _kette(11, 12)
        gruppe = _baue(_FakeEvidenceMitKette([alt, neu]), [11])
        # Der Beleg ist NICHT verloren - er steht unter seiner neuen Nummer.
        ub = gruppe.unterbloecke[0]
        self.assertNotEqual("Beleg nicht mehr vorhanden",
                            ub.quelle.bezeichnung())
        self.assertEqual([12], [b.annotation_id for b in ub.befunde])
        self.assertEqual("neue Notiz", ub.befunde[0].notiz)

    def test_vz38_die_fortfuehrung_wird_ausgewiesen(self):
        # IN EINER AKTE DARF NICHT UNBEMERKT ein anderer Datensatz an die
        # Stelle des zitierten treten - auch nicht derselbe Beleg in neuerer
        # Fassung. Ohne diese Zeile waere der Austausch still (Grundregel 1).
        alt, neu = _kette(11, 12)
        gruppe = _baue(_FakeEvidenceMitKette([alt, neu]), [11])
        text = "\n".join(gruppe.warnungen)
        self.assertIn("#11", text)
        self.assertIn("#12", text)
        self.assertIn("fortgefuehrt", text)

    def test_vz39_mehrgliedrige_kette_wird_ganz_verfolgt(self):
        a1 = _ann(21, "CAT_LOCATION", _markierung(), "v1", "mc")
        a1.deleted_at = 1787832100
        a2 = _ann(22, "CAT_LOCATION", _markierung(), "v2", "mc")
        a2.deleted_at = 1787832200
        a2.version_nr, a2.prev_id = 2, 21
        a3 = _ann(23, "CAT_LOCATION", _markierung(), "v3", "mc")
        a3.version_nr, a3.prev_id = 3, 22
        gruppe = _baue(_FakeEvidenceMitKette([a1, a2, a3]), [21])
        ub = gruppe.unterbloecke[0]
        self.assertEqual([23], [b.annotation_id for b in ub.befunde])
        self.assertEqual("v3", ub.befunde[0].notiz)
        # Die ganze Kette steht im Vermerk, nicht nur Anfang und Ende.
        text = "\n".join(gruppe.warnungen)
        self.assertIn("#21 -> #22 -> #23", text)

    def test_vz40_gegenprobe_wirklich_geloescht_bleibt_fehlend(self):
        # OHNE DIESE PROBE waere VZ37 auch mit einer Fassung gruen, die JEDE
        # fehlende Nummer irgendwie aufloest - und dann verschwaende eine
        # echte Loeschung aus dem Bericht.
        weg = _ann(31, "CAT_LOCATION", _markierung(), "geloescht", "mc")
        weg.deleted_at = 1787832100
        gruppe = _baue(_FakeEvidenceMitKette([weg]), [31])
        ub = gruppe.unterbloecke[0]
        self.assertEqual("Beleg nicht mehr vorhanden", ub.quelle.bezeichnung())
        text = "\n".join(gruppe.warnungen)
        self.assertIn("#31", text)

    def test_vz41_ein_zyklus_laesst_den_lauf_nicht_haengen(self):
        # Ein Zyklus in der Kette ist ein Datenschaden. Er darf den Bericht
        # nicht zum Stehen bringen - der Beleg gilt dann als fehlend, und
        # das ist die ehrliche Auskunft.
        a = _ann(41, "CAT_LOCATION", _markierung(), "a", "mc")
        a.deleted_at = 1787832100
        b = _ann(42, "CAT_LOCATION", _markierung(), "b", "mc")
        b.deleted_at = 1787832200
        b.prev_id = 41
        a.prev_id = 42
        gruppe = _baue(_FakeEvidenceMitKette([a, b]), [41])
        self.assertEqual("Beleg nicht mehr vorhanden",
                         gruppe.unterbloecke[0].quelle.bezeichnung())
