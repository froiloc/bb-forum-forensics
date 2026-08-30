# =============================================================================
# tests/test_wortlaut_browserbild.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Build 729)
# =============================================================================
# Zweck:
#   DEN BEFUND VON ALEX FESTNAGELN (28.08.2026):
#
#     "Wenn du nach dem Text gesucht hast, hast du dann beruecksichtigt, dass
#      im BLOB \\n zu <br> aufgeloest wird? Du musst dir ansehen, wie
#      'textContent' im JSON von annotation.selection_json erzeugt wird. Das
#      muss rueckwaerts abgewickelt werden."
#
#   Er hat recht, und der Beleg steht in toolbar/toolbar.js Z. 1101:
#       var text = sel.toString().trim();
#   'textContent' ist die GERENDERTE Auswahl, nicht der Quelltext. Darin ist
#   jedes <br> ein '\\n', jede Blockgrenze ein '\\n', und Rand-Leerraum fehlt.
#   Bis Build 728 wurde dieser Text im QUELLTEXT gesucht - mehrzeilige
#   Markierungen konnten damit nur verfehlt werden.
#
#   BR01-BR07 pruefen die Rueckabwicklung, AN01-AN06 die zweite Haelfte des
#   Befundes: dass das Werkzeug nicht mehr pauschal behauptet, der Anker loese
#   nicht auf, sondern den GEMESSENEN Grund nennt.
#
# GEGENPROBEN sind eigens ausgewiesen (BR06, AN06). Ein Test, der auch ohne
#   die Aenderung gruen bliebe, prueft nichts.
#
# Version: v0.8.729 - Build: 729 - 2026-08-28
# =============================================================================

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from report_render.absatz_finder import (           # noqa: E402
    AbsatzFinder,
    GRUND_ANKER_BRICHT,
    GRUND_OHNE_ANKER,
    GRUND_TEXT,
    WEG_KEINER,
    WEG_TEXT,
    WEG_XPATH,
    _klartext,
    browser_wortlaut,
)

#: Ein Absatz, wie ein Forenbeitrag ihn wirklich hat: mehrere <br>, ein <b>,
#: ein <a>. Genau daraus entstehen die hohen text()-Indizes aus Alex' Ankern
#: (text()[5], text()[6], text()[13]).
ABSATZ = ('<div class="postmsg"><p>'
          'Zeile eins.<br>'
          'Zeile zwei mit <b>fett</b> und Rest.<br>'
          'Zeile drei mit <a href="#">Link</a> danach.<br>'
          'Zeile vier ist die letzte.'
          '</p></div>')

#: Zwei Absaetze - fuer die Blockgrenze.
ZWEI = ('<div class="postmsg"><p>Erster Absatz.</p>'
        '<p>Zweiter Absatz.</p></div>')


def _finder(body: str) -> AbsatzFinder:
    return AbsatzFinder.aus_seiten_html(
        ("<html><body>" + body + "</body></html>").encode("utf-8"))


def _auswahl(text: str, anker: str = "", offset_a: int = 0,
             offset_b: int = 0) -> dict:
    return {"xpathStart": anker, "offsetStart": offset_a,
            "xpathEnd": anker, "offsetEnd": offset_b,
            "textContent": text}


class BrowserbildTests(unittest.TestCase):
    """Die Rueckabwicklung von Range.toString()."""

    # --- BR01 --------------------------------------------------------------
    def test_br01_br_wird_zum_zeilenumbruch(self):
        """
        BR01: <br> erscheint im Browserbild als '\\n', im Quelltext gar nicht.
        Das ist der Unterschied, an dem die Wortlautsuche gescheitert ist.
        """
        p = _finder(ABSATZ)._wurzel.xpath(".//p[1]")[0]
        quelltext = _klartext(p)
        bild, _versaetze = browser_wortlaut(p)

        self.assertNotIn("\n", quelltext,
                         "Der Quelltext traegt keine Umbrueche - <br> ist ein "
                         "Element, kein Zeichen.")
        self.assertEqual(3, bild.count("\n"),
                         "Drei <br> muessen drei Umbrueche ergeben.")
        self.assertIn("Zeile eins.\nZeile zwei", bild)

    # --- BR02 --------------------------------------------------------------
    def test_br02_ein_mehrzeiliger_wortlaut_wird_gefunden(self):
        """
        BR02: DER EIGENTLICHE BEFUND. Ein Wortlaut mit '\\n' - so, wie die
        Toolbar ihn speichert - wird im Absatz wiedergefunden.
        """
        f = _finder(ABSATZ)
        wortlaut = "und Rest.\nZeile drei mit Link danach."
        fund = f.finde(_auswahl(wortlaut), None)

        self.assertEqual(WEG_TEXT, fund.weg)
        self.assertEqual(1, len(fund.treffer))

    # --- BR03 --------------------------------------------------------------
    def test_br03_die_versaetze_zeigen_auf_den_quelltext(self):
        """
        BR03: Der Treffer wird in QUELLTEXT-Versaetze zurueckgesetzt - denn
        die Einfaerbung arbeitet auf dem Quelltext. Ein Treffer, der im
        Browserbild richtig und im Quelltext um drei Zeichen verschoben ist,
        faerbte die falsche Stelle ein und saehe dabei unauffaellig aus.
        """
        f = _finder(ABSATZ)
        fund = f.finde(_auswahl("und Rest.\nZeile drei mit Link danach."), None)
        t = fund.treffer[0]
        gefaerbt = _klartext(t.block)[t.von:t.bis]

        # Im Quelltext fehlen die Umbrueche - der Rest muss stimmen.
        self.assertEqual("und Rest.Zeile drei mit Link danach.", gefaerbt)

    # --- BR04 --------------------------------------------------------------
    def test_br04_blockgrenzen_brechen_ebenfalls_um(self):
        """BR04: Auch </p><p> ist im Browserbild ein Umbruch."""
        p = _finder(ZWEI)._wurzel.xpath(".//div[1]")[0]
        bild, _v = browser_wortlaut(p)
        self.assertIn("Erster Absatz.\nZweiter Absatz.", bild)

    # --- BR05 --------------------------------------------------------------
    def test_br05_rand_leerraum_wird_verziehen(self):
        """
        BR05: toolbar.js speichert 'sel.toString().trim()'. Ein Wortlaut mit
        Rand-Leerraum muss trotzdem treffen - sonst scheitert jede Markierung,
        die an einer Leerstelle beginnt.
        """
        f = _finder('<div class="postmsg"><p>  Ein Satz mit Rand.  </p></div>')
        fund = f.finde(_auswahl("Ein Satz mit Rand."), None)
        self.assertEqual(WEG_TEXT, fund.weg)
        self.assertEqual(1, len(fund.treffer))

    # --- BR06: GEGENPROBE zu BR02 ------------------------------------------
    def test_br06_die_alte_suche_haette_versagt(self):
        """
        BR06: GEGENPROBE. Genau derselbe Wortlaut, gesucht mit dem Verfahren
        aus Build 728 (Suche im Quelltext), findet NICHTS. Ohne diese Probe
        waere BR02 nur der Nachweis, dass irgendetwas zurueckkommt.
        """
        p = _finder(ABSATZ)._wurzel.xpath(".//p[1]")[0]
        wortlaut = "und Rest.\nZeile drei mit Link danach."

        self.assertEqual(-1, _klartext(p).find(wortlaut),
                         "Die alte Suche haette diesen Wortlaut gefunden - "
                         "dann waere der Befund von Alex keiner gewesen.")
        # ... und die neue findet ihn sehr wohl.
        bild, _v = browser_wortlaut(p)
        self.assertGreaterEqual(bild.find(wortlaut), 0)

    # --- BR07 --------------------------------------------------------------
    def test_br07_der_ankerweg_bleibt_unberuehrt(self):
        """
        BR07: Die Umstellung betrifft NUR den Rueckfall. Wo der Anker traegt,
        wird weiterhin zeichengenau ueber die Versaetze gearbeitet, die der
        Browser mitgeschrieben hat - nicht ueber eine Textsuche.
        """
        f = _finder(ABSATZ)
        fund = f.finde({"xpathStart": "./div[1]/p[1]/text()[3]",
                        "offsetStart": 1,
                        "xpathEnd": "./div[1]/p[1]/text()[3]",
                        "offsetEnd": 10,
                        "textContent": "und Rest."}, None)
        self.assertEqual(WEG_XPATH, fund.weg)
        t = fund.treffer[0]
        self.assertEqual("und Rest.", _klartext(t.block)[t.von:t.bis])


class AnkergrundTests(unittest.TestCase):
    """
    Dass der Bericht den GEMESSENEN Grund nennt und nicht mehr behauptet.

    DER ANLASS: Bis Build 728 stand in jeder Zeile derselbe Satz - "der Anker
    loest nicht auf". _ueber_xpath() gab aber in FUENF verschiedenen Lagen
    None zurueck, und alle fuenf bekamen diesen einen Satz. Alex' Lauf ueber
    25 echte Markierungen las sich damit wie ein Totalausfall der Anker; ob es
    einer war, war NICHT gemessen.
    """

    # --- AN01 --------------------------------------------------------------
    def test_an01_ein_gebrochener_anker_nennt_den_schritt(self):
        """
        AN01: Bricht der Anker wirklich, wird gesagt, an welchem Schritt und
        was dort statt dessen steht. Erst das unterscheidet die drei Bilder:
        Bezugspunkt falsch / etwas hineingeschrieben / Text anders zerlegt.
        """
        f = _finder(ABSATZ)
        fund = f.finde(_auswahl("Zeile eins.", "./div[1]/p[9]/text()[1]"), None)
        self.assertEqual(GRUND_ANKER_BRICHT, fund.anker_grund)
        self.assertIn("Schritt 2", fund.anker_bruch)
        self.assertIn("p[9]", fund.anker_bruch)
        self.assertIn("im Abzug stehen nur 1", fund.anker_bruch)
        # BUILD 731: Die Zahl allein genuegt nicht - der Abzug muss auch
        # BENENNEN, was dort steht. Genau das fehlte in Alex' Lauf, in dem
        # 25-mal "Browser 4, Abzug 2" stand, ohne zu sagen, welche zwei.
        self.assertIn("Im Abzug steht dort: <p>", fund.anker_bruch)

    # --- AN02 --------------------------------------------------------------
    def test_an02_der_bruch_ganz_oben_wird_als_solcher_benannt(self):
        """
        AN02: Bricht schon der erste Schritt, ist der BEZUGSPUNKT falsch -
        eine ganz andere Ursache als ein verschobener Index weiter unten.
        Das muss dastehen, nicht erschlossen werden.
        """
        f = _finder(ABSATZ)
        fund = f.finde(_auswahl("x", "./section[1]/p[1]/text()[1]"), None)
        self.assertEqual(GRUND_ANKER_BRICHT, fund.anker_grund)
        self.assertIn("BRICHT GANZ OBEN", fund.anker_bruch)

    # --- AN03 --------------------------------------------------------------
    def test_an03_zu_wenige_textknoten_werden_gezaehlt(self):
        """
        AN03: Bricht es erst bei 'text()[n]', weicht die ZERLEGUNG DES TEXTES
        ab - der Browser hat dort mehr Textknoten gesehen als der Abzug hat.
        Die Meldung nennt beide Zahlen, sonst laesst sich nicht rechnen.
        """
        f = _finder(ABSATZ)
        fund = f.finde(_auswahl("x", "./div[1]/p[1]/text()[99]"), None)
        self.assertEqual(GRUND_ANKER_BRICHT, fund.anker_grund)
        self.assertIn("Textknoten", fund.anker_bruch)
        self.assertIn("99", fund.anker_bruch)
        self.assertIn("der Abzug hat 6", fund.anker_bruch)

    # --- AN04 --------------------------------------------------------------
    def test_an04_ohne_anker_ist_ein_eigener_grund(self):
        """
        AN04: Eine Auswahl ohne xpathStart hat keinen gebrochenen Anker - sie
        hat gar keinen. Das ist etwas anderes und heisst jetzt auch anders.
        """
        f = _finder(ABSATZ)
        fund = f.finde(_auswahl("Zeile eins."), None)
        self.assertEqual(GRUND_OHNE_ANKER, fund.anker_grund)
        self.assertEqual("", fund.anker_bruch)

    # --- AN05 --------------------------------------------------------------
    def test_an05_der_grund_steht_auch_im_erfolgsfall_des_rueckfalls(self):
        """
        AN05: Auch wenn der Wortlaut TRAEGT, wandert der Ankergrund mit. Genau
        dann ist er die Auskunft, die in Alex' Lauf gefehlt hat: 17 Zeilen
        'Weg=wortlaut' und kein Wort darueber, warum.
        """
        f = _finder(ABSATZ)
        fund = f.finde(_auswahl("Zeile eins.", "./div[1]/p[9]/text()[1]"), None)
        self.assertEqual(WEG_TEXT, fund.weg,
                         "Der Rueckfall soll hier tragen.")
        self.assertEqual(GRUND_ANKER_BRICHT, fund.anker_grund)
        self.assertIn("Schritt", fund.hinweis)

    # --- AN06: GEGENPROBE --------------------------------------------------
    def test_an06_ein_heiler_anker_traegt_keinen_grund(self):
        """
        AN06: GEGENPROBE. Wo der Anker traegt, darf KEIN Grund stehen -
        sonst waeren AN01-AN05 nur der Nachweis, dass immer irgendetwas
        eingetragen wird.
        """
        f = _finder(ABSATZ)
        fund = f.finde({"xpathStart": "./div[1]/p[1]/text()[1]",
                        "offsetStart": 0,
                        "xpathEnd": "./div[1]/p[1]/text()[1]",
                        "offsetEnd": 11,
                        "textContent": "Zeile eins."}, None)
        self.assertEqual(WEG_XPATH, fund.weg)
        self.assertEqual("", fund.anker_grund)
        self.assertEqual("", fund.anker_bruch)

    # --- AN07 --------------------------------------------------------------
    def test_an07_jeder_grund_hat_einen_klartext(self):
        """
        AN07: Ein Code ohne Satz waere im Bericht eine Abkuerzung, die
        niemand fuehrt. Jeder GRUND_* muss einen Klartext haben.
        """
        from report_render import absatz_finder as af
        codes = [getattr(af, n) for n in dir(af)
                 if n.startswith("GRUND_") and n != "GRUND_TEXT"]
        for code in codes:
            self.assertIn(code, GRUND_TEXT,
                          "Zum Grund %r fehlt der Klartext." % code)
            self.assertTrue(GRUND_TEXT[code].strip())

    # --- AN08 --------------------------------------------------------------
    def test_an08_kein_absatz_und_kein_wortlaut_nennt_beides(self):
        """
        AN08: Faellt beides aus, muss der Hinweis BEIDE Aussagen tragen - den
        gemessenen Ankergrund UND dass der Wortlaut nicht vorkommt. Bis
        Build 728 wurden sie zu einem Satz verschmolzen, der nur die
        unbelegte Haelfte nannte.
        """
        f = _finder(ABSATZ)
        fund = f.finde(_auswahl("Zeppelin ueber Wanne-Eickel",
                                "./div[1]/p[9]/text()[1]"), None)
        self.assertEqual(WEG_KEINER, fund.weg)
        self.assertIn("Schritt", fund.hinweis)
        self.assertIn("Wortlaut", fund.hinweis)


if __name__ == "__main__":
    unittest.main()


# ===========================================================================
# Build 743 - die Bruchmeldung nach dem Fix
# ===========================================================================
#
# WARUM DIE MELDUNG GEAENDERT WERDEN MUSSTE: Sie nannte zwei Ursachen und
# verschwieg die haeufigste - dass die ZERLEGUNG die Elemente falsch ablegt.
# Genau daran lagen in Alex' Bestand ALLE 29 Brueche. Seit Build 742 ist das
# behoben; wer die Meldung JETZT liest, hat einen anderen Fall vor sich und
# darf nicht auf die ausgeraeumte Faehrte geschickt werden.
#
# BM01  die Meldung schliesst die Zerlegung ausdruecklich aus
# BM02  bei einem Bruch an einem Beitragsschritt nennt sie, wie viele
#       <article> die GANZE Seite traegt und welche Nummern - damit ist
#       'andere Seite des Themas' von 'spaeter neu gezogen' zu unterscheiden
# BM03  GEGENPROBE: bei einem Bruch an einem NICHT-Beitragsschritt bleibt
#       die Zusatzangabe weg - eine Zahl ohne Bezug waere Beiwerk
#
# BUILD 744 - DIE ANGABE, DIE DIE BEIDEN LAGEN WIRKLICH TRENNT
#
# BM02 zaehlt, wie viele Beitraege die Seite traegt. Diese Zahl allein
# LAESST BEIDE DEUTUNGEN ZU - und eine Angabe, die jede Deutung zulaesst,
# wird nach der gedeutet, die man ohnehin erwartet hat. Was sie trennt, ist
# die Frage, ob die Beitraege INEINANDER stehen: ein <article> gehoert nicht
# in ein <article>. Steht es dort, hat die Zerlegung sie ineinandergeschoben
# (Auswertungsfehler, im Code zu beheben); steht keines darin, stehen sie
# nebeneinander an anderer Stelle (Datenbefund, nicht durch Code zu heilen).
#
# BM04  Beitraege INEINANDER -> die Meldung nennt Zahl und Tiefe
# BM05  GEGENPROBE: Beitraege NEBENEINANDER -> die Meldung sagt
#       ausdruecklich, dass keines verschachtelt ist

from report_render.absatz_finder import AbsatzFinder


def _seite_mit_zwei_beitraegen() -> str:
    return ('<donate><div id="wrap"><div id="brdleft">L</div>'
            '<div id="page-header">K</div>'
            '<div class="announce">A</div>'
            '<div id="page-body">'
            '<article class="post" id="p136"><p>Erster.</p></article>'
            '<article class="post" id="p151"><p>Zweiter.</p></article>'
            '</div><div id="page-footer">F</div></div></donate>')


def test_BM01_die_zerlegung_wird_ausdruecklich_ausgeschlossen():
    f = AbsatzFinder(_seite_mit_zwei_beitraegen())
    meldung = f.anker_bruchstelle(
        "./donate[1]/div[1]/div[4]/article[29]/p[1]/text()[1]")
    assert "Zerlegung scheidet" in meldung
    assert "Build 742" in meldung
    # Und die beiden verbleibenden Lagen werden benannt.
    assert "ANDEREN SEITE" in meldung
    assert "SPAETER neu gezogen" in meldung


def test_BM02_die_seitenlage_wird_mitgezaehlt():
    # DIE ANGABE DEUTET NICHT, SIE ZAEHLT. Zwei niedrige Nummern in einem
    # Thema, dessen Markierungen fuenfstellige tragen, sprechen fuer eine
    # andere Seite - aber das zu entscheiden ist Sache der Sichtpruefung.
    f = AbsatzFinder(_seite_mit_zwei_beitraegen())
    meldung = f.anker_bruchstelle(
        "./donate[1]/div[1]/div[4]/article[29]/p[1]/text()[1]")
    assert "Die ganze Seite traegt 2 <article>" in meldung
    assert "136" in meldung and "151" in meldung
    assert "Der Anker verlangt den 29." in meldung


def test_BM03_gegenprobe_ohne_beitragsschritt_keine_zusatzangabe():
    # Ohne diese Probe waere BM02 auch mit einer Fassung gruen, die die Zahl
    # an jeden Bruch haengt - und eine Zahl ohne Bezug ist Beiwerk, das die
    # Meldung verwaessert.
    f = AbsatzFinder(_seite_mit_zwei_beitraegen())
    meldung = f.anker_bruchstelle("./donate[1]/div[1]/div[9]/p[1]/text()[1]")
    assert "Die ganze Seite traegt" not in meldung


def _seite_mit_kaskade() -> str:
    """Zwoelf <article>, ineinandergeschoben - die Lage 'Kaskade'."""
    innen = "<p>Text.</p>"
    for i in range(12, 0, -1):
        innen = '<article class="post" id="p%d">%s</article>' % (100 + i, innen)
    return ('<donate><div id="wrap"><div id="brdleft">L</div>'
            '<div id="page-header">K</div>'
            '<div class="announce">A</div>'
            '<div id="page-body">' + innen +
            '</div><div id="page-footer">F</div></div></donate>')


def test_BM04_die_schachtelung_wird_gezaehlt_und_benannt():
    # ELF VON ZWOELF stehen in einem anderen - der zwoelfte ist der
    # aeusserste. Die tiefste Schachtelung ist damit 11.
    f = AbsatzFinder(_seite_mit_kaskade())
    meldung = f.anker_bruchstelle(
        "./donate[1]/div[1]/div[4]/article[29]/p[1]/text()[1]")
    assert "11 davon stehen INNERHALB eines anderen <article>" in meldung, meldung
    assert "tiefste Schachtelung: 11" in meldung, meldung
    assert "Die Schachtelung stammt also aus der Zerlegung" in meldung, meldung
    # BUILD 746 - DIE WIDERSPRUCHSPROBE. Bis Build 745 stand hinter dieser
    # Angabe unbedingt 'Die Zerlegung scheidet als Ursache aus'. Die Meldung
    # widersprach sich damit in zwei aufeinanderfolgenden Saetzen - und der
    # Leser waehlt dann die Haelfte, die zu seiner Erwartung passt.
    assert "Zerlegung scheidet als Ursache aus" not in meldung, meldung
    assert "NICHT ausgeraeumt" in meldung, meldung
    assert "M8" in meldung, meldung


def test_BM05_gegenprobe_nebeneinander_ist_keine_kaskade():
    # OHNE DIESE PROBE waere BM04 auch mit einer Fassung gruen, die bei
    # jedem Bruch von einer Kaskade spricht. Genau dieser Kurzschluss hat
    # dieses Teilprojekt vier Builds gekostet.
    f = AbsatzFinder(_seite_mit_zwei_beitraegen())
    meldung = f.anker_bruchstelle(
        "./donate[1]/div[1]/div[4]/article[29]/p[1]/text()[1]")
    assert "KEINES davon steht innerhalb eines anderen <article>" in meldung, meldung
    assert "Kaskade der Zerlegung scheidet damit aus" in meldung, meldung
    assert "INNERHALB eines anderen" not in meldung, meldung
    # Und HIER darf der Schlusssatz stehen - ohne Schachtelung ist die
    # Zerlegung tatsaechlich ausgeraeumt.
    assert "Zerlegung scheidet als Ursache aus" in meldung, meldung
