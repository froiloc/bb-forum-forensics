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
        self.assertIn("im Abzug stehen 1", fund.anker_bruch)

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
