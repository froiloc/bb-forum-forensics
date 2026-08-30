# =============================================================================
# tests/test_html5_zerleger.py
#
# Build 747: Die Zerlegung nach dem HTML5-Standard.
#
# WAS DIESE DATEI ABLOEST UND WARUM
#
# tests/test_html5_annaeherung.py pruefte einen HANDGEBAUTEN Teilnachbau des
# HTML5-Baumaufbaus. Der Nachbau bildete erst eine, dann zwei Regeln nach und
# zerbrach dabei ueber fuenf Builds hinweg je ein Konstrukt, das vorher heil
# war - zuletzt riss er am echten Abzug '#page-body' nach dem zweiten Beitrag
# auf und liess 498 von 500 Beitraegen herausfallen.
#
# DIE GEGENPROBE IM BROWSER (31.08.2026, Chromium in der Ermittlungs-VM,
# Belege #16 und #25 aus evidence_155955.db, Seite viewtopic.php?id=1989)
# entschied die Sache:
#
#   Alle zwoelf Ankerschritte loesen auf, bis zum Textknoten.
#   '#page-body' haengt unter 'div#wrap' und traegt 500 direkte <article>.
#
#   Zerlegung                      '#page-body' unter   <article> darin
#   -------------------------------------------------------------------
#   Browser (der Massstab)         div#wrap                  500
#   libxml2 roh                    div#page-header           500
#   libxml2 + Teilnachbau 742-746  div#wrap                    2
#
# Der Anker war richtig, der Abzug vollstaendig - falsch war allein die
# Zerlegung. Seit Build 747 fuehrt html5lib den GANZEN Algorithmus aus.
#
# DIE ERWARTUNGSWERTE IN DIESER DATEI SIND GEMESSEN, NICHT AUSGEDACHT. Sie
# stammen aus einem Lauf gegen Chromium (Playwright, 'innerHTML' auf einen
# <div> - genau der Weg des Ermittlungsfensters), 17 Konstrukte:
#
#   lxml.html roh                                      7 von 17
#   lxml.html + Teilnachbau (Build 742-746)           16 von 17
#   html5lib, scripting=True, <template> geleert      17 von 17
#
# HZ01  der Anker traegt bei einem <li> mit offen gebliebenem <div>
#       (der Fall, an dem in Alex' Abzug ALLE 29 Anker gebrochen sind)
# HZ02  ein verirrtes </div> in einer Tabellenzelle reisst den Zweig NICHT
#       auf (der Fall, an dem der Teilnachbau in Build 745 scheiterte)
# HZ03  <noscript> mit offenem Tag: der Inhalt ist Rohtext (scripting-Flag)
# HZ04  GEGENPROBE zu HZ03: mit scripting=False bricht es - das Flag ist
#       also wirksam und nicht bloss gesetzt
# HZ05  <template>: der Inhalt zaehlt nicht mit, das Element aber schon
# HZ06  GEGENPROBE zu HZ05: ein LEERES <template> wird nicht als Eingriff
#       gemeldet - ein Eingriff ohne Wirkung ist kein Eingriff
# HZ07  ein heiler Abzug wird nicht angefasst, und es gibt keine Befunde
# HZ08  Textknoten werden wie im Browser gezaehlt - daran haengt die letzte
#       Stufe jedes Ankers ('text()[n]')
# HZ09  fuehrender und nachfolgender Text am Rand geht nicht verloren
# HZ10  KEIN RUECKFALL: fehlt html5lib, wird abgebrochen statt anders
#       zerlegt
# HZ11  der AbsatzFinder benutzt den neuen Zerleger und meldet den Eingriff
# HZ12  rohtext_stellen unterscheidet ausgeglichen von unausgeglichen
#
# Beleg: report_render/html5_zerleger.py; Messung gegen Chromium 31.08.2026.
# =============================================================================

import builtins

import pytest

from report_render.absatz_finder import AbsatzFinder
from report_render.html5_zerleger import (Html5FehltError, Html5Zerleger,
                                          rohtext_stellen)


# Der Aufbau aus der Messung, gekuerzt. 'donate' ist ein Element der echten
# Seite (kein HTML-Standardelement) - es steht hier, weil die Anker es
# enthalten und ein unbekanntes Element die Zerlegung mit beeinflussen kann.
def _seite(kopf: str) -> str:
    return ("<donate><div id=\"wrap\" class=\"wrap shadow\">"
            "<div id=\"brdleft\">L</div>"
            + kopf +
            "<style>.x{color:red}</style>"
            "<div class=\"announce postmsg\">A</div>"
            "<div id=\"page-body\"><article class=\"post\" id=\"p1\">"
            "<p>Der Zug faehrt ab Hauptbahnhof.</p></article></div>"
            "<div id=\"page-footer\">F</div>"
            "</div></donate>")


#: So sieht der Browser die Kinder von '#wrap' - GEMESSEN, nicht angenommen.
_SOLL = ["brdleft", "page-header", "style", "div", "page-body", "page-footer"]


def _kinder_unter_wrap(wurzel):
    treffer = wurzel.xpath("//*[@id='wrap']")
    assert treffer, "kein #wrap im Baum"
    return [(k.get("id") or k.tag) for k in treffer[0]
            if isinstance(k.tag, str)]


def test_HZ01_offenes_div_im_li_bricht_den_anker_nicht():
    # DER FALL AUS ALEX' ABZUG. Ein <div> bleibt im <li> offen; HTML5
    # schliesst es beim </li> mit, libxml2 laesst es offen und alles
    # Folgende landet darin.
    wurzel, _ = Html5Zerleger().zerlege(
        _seite('<div id="page-header"><ul><li><div class="a">x</li></ul></div>'))
    assert _kinder_unter_wrap(wurzel) == _SOLL


def test_HZ02_verirrtes_endtag_in_einer_zelle_reisst_nichts_auf():
    # DER FALL, AN DEM DER TEILNACHBAU IN BUILD 745 SCHEITERTE. Er suchte
    # das Element zu einem Endtag im ganzen Stapel, fand '#page-body' und
    # schloss die halbe Seite mit. HTML5 sucht nur innerhalb des
    # Geltungsbereichs; eine Tabellenzelle ist dessen Grenze.
    quelle = ('<donate><div id="wrap"><div id="page-body">'
              '<article class="post" id="p1"><table><tr><td>x</div></td></tr>'
              '</table></article><article class="post" id="p2">c</article>'
              '<article class="post" id="p3">d</article></div>'
              '<div id="page-footer">F</div></div></donate>')
    wurzel, _ = Html5Zerleger().zerlege(quelle)
    body = wurzel.xpath("//*[@id='page-body']")[0]
    darin = [k for k in body if isinstance(k.tag, str) and k.tag == "article"]
    assert len(wurzel.xpath("//article")) == 3
    assert len(darin) == 3, "alle drei Beitraege gehoeren unter #page-body"


def test_HZ03_noscript_inhalt_ist_rohtext():
    # BEI EINGESCHALTETEM JAVASCRIPT ist der Inhalt von <noscript> Rohtext -
    # kein einziges Tag darin wird zu einem Element. Das Ermittlungsfenster
    # IST eine JavaScript-Anwendung (die Toolbar), fuer es gilt das immer.
    wurzel, _ = Html5Zerleger().zerlege(
        _seite('<div id="page-header"><noscript><div class="n">X</noscript>'
               '</div>'))
    assert _kinder_unter_wrap(wurzel) == _SOLL


def test_HZ04_gegenprobe_ohne_scripting_flag_bricht_es():
    # OHNE DIESE PROBE waere HZ03 auch mit einem Zerleger gruen, bei dem das
    # Flag gar nicht ankommt. Die Probe zeigt, dass es WIRKT.
    wurzel, _ = Html5Zerleger(scripting=False).zerlege(
        _seite('<div id="page-header"><noscript><div class="n">X</noscript>'
               '</div>'))
    assert _kinder_unter_wrap(wurzel) != _SOLL


def test_HZ05_template_inhalt_zaehlt_nicht_mit():
    # HTML5 legt den Inhalt eines <template> in ein eigenes
    # DocumentFragment. Ueber 'element.children' ist er nicht erreichbar,
    # ein XPath aus dem Browser zaehlt ihn folglich NIE mit.
    wurzel, befunde = Html5Zerleger().zerlege(
        _seite('<div id="page-header"><template><div>X</template></div>'))
    assert _kinder_unter_wrap(wurzel) == _SOLL
    # Der Eingriff wird benannt - Grundregel 1: nichts still tun.
    assert befunde and "<template>" in befunde[0]
    # DAS ELEMENT SELBST BLEIBT STEHEN: es zaehlt im Browser mit. Wer es
    # entfernte, verschoebe die Zaehlung um eins.
    assert wurzel.xpath("//template")


def test_HZ06_gegenprobe_leeres_template_ist_kein_eingriff():
    _wurzel, befunde = Html5Zerleger().zerlege(
        _seite('<div id="page-header"><template></template></div>'))
    assert befunde == []


def test_HZ07_ein_heiler_abzug_wird_nicht_angefasst():
    quelle = _seite('<div id="page-header"><h1>Forum</h1></div>')
    wurzel, befunde = Html5Zerleger().zerlege(quelle)
    assert _kinder_unter_wrap(wurzel) == _SOLL
    assert befunde == []


def test_HZ08_textknoten_werden_wie_im_browser_gezaehlt():
    # DARAN HAENGT DIE LETZTE STUFE JEDES ANKERS. Beleg #25 verlangt
    # 'text()[3]' - waere die Zaehlung um eins verschoben, traefe der Anker
    # die falsche Stelle, und zwar OHNE zu brechen. Das ist der gefaehrlichere
    # Fehler: er faellt nicht auf.
    #
    # Chromium liefert fuer '<p>a<br>b<!--k-->c</p>' DREI Textknoten.
    wurzel, _ = Html5Zerleger().zerlege("<p>a<br>b<!--k-->c</p>")
    p = wurzel.xpath("./p")[0]
    assert len(p.xpath("./text()")) == 3


def test_HZ09_text_am_rand_geht_nicht_verloren():
    # parseFragment liefert fuehrenden Text als Zeichenkette und
    # nachfolgenden als 'tail'. Wer nur die Elemente einsammelt, verliert
    # beides - und ein verlorener Textknoten verschiebt 'text()[n]'.
    wurzel, _ = Html5Zerleger().zerlege("Vor<p>x</p>Nach")
    assert wurzel.text == "Vor"
    assert wurzel.xpath("./p")[0].tail == "Nach"


def test_HZ10_kein_rueckfall_wenn_html5lib_fehlt(monkeypatch):
    # EIN WERKZEUG, DAS JE NACH INSTALLATIONSLAGE ANDERS ZERLEGT, liefert
    # Ergebnisse, die nicht vergleichbar sind. In einem Beweismittelverfahren
    # ist ein still abweichendes Verfahren schlimmer als ein Abbruch.
    echt = builtins.__import__

    def _ohne_html5lib(name, *a, **k):
        if name.startswith("html5lib"):
            raise ImportError("html5lib nicht vorhanden (Testaufbau)")
        return echt(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _ohne_html5lib)
    with pytest.raises(Html5FehltError) as fehler:
        Html5Zerleger().zerlege("<p>x</p>")
    text = str(fehler.value)
    assert "KEINEN" in text and "Rueckfall" in text
    # Und die Abhilfe steht dabei - eine Fehlermeldung ohne Ausweg ist eine
    # halbe Fehlermeldung.
    assert "pip install html5lib" in text


def test_HZ11_der_absatzfinder_benutzt_den_neuen_zerleger():
    anker = "./donate[1]/div[1]/div[4]/article[1]/p[1]/text()[1]"
    body = _seite('<div id="page-header"><ul><li><div class="a">x</li></ul>'
                  '</div>')
    finder = AbsatzFinder(body)
    assert finder.brauchbar
    assert finder._wurzel.xpath(anker), "der Anker muss tragen"
    # Ohne <template> gibt es nichts zu melden - und was nicht getan wurde,
    # wird auch nicht gemeldet.
    assert finder.zerlegungsbefunde == []

    mit_template = AbsatzFinder(
        _seite('<div id="page-header"><template><div>X</template></div>'))
    assert mit_template.brauchbar
    assert mit_template.zerlegungsbefunde, \
        "der Eingriff muss am Finder ablesbar sein"


def test_HZ12_rohtext_stellen_unterscheidet_ausgeglichen():
    heil = rohtext_stellen('<noscript><div>x</div></noscript>')
    assert heil and heil[0][1] == "noscript" and heil[0][2] is True
    kaputt = rohtext_stellen('<noscript><div>x</noscript>')
    assert kaputt and kaputt[0][2] is False
    # Ein <br> darf nicht als unausgeglichen gelten - sonst waere jeder
    # heile Hinweistext ein Befund.
    mit_br = rohtext_stellen('<noscript>Bitte JavaScript<br>an</noscript>')
    assert mit_br and mit_br[0][2] is True


# ---------------------------------------------------------------------------
# Build 748 - die Namensumschreibungen des Zerlegers
#
# ALEX' LAUF VOM 31.08.2026 gab vor der eigentlichen Ausgabe drei Zeilen auf
# stderr aus:
#
#   DataLossWarning: Coercing non-XML name: 5
#   DataLossWarning: Coercing non-XML name: &#160;
#
# URSACHE, GEMESSEN: html5lib legt seinen Baum ueber lxml ab, und lxml haelt
# sich an die XML-Namensregeln. Im Quelltext der Seite steht
# 'rel="nofollow"&#160; target="_blank"' - eine Entitaet ZWISCHEN zwei
# Attributen; der HTML-Zerleger liest sie regelgerecht als weiteren
# ATTRIBUTNAMEN, und XML laesst diesen Namen nicht zu.
#
# ZWEI DINGE SIND DARAN ZU TUN, UND ES SIND ZWEI VERSCHIEDENE:
#
#   (1) Die Meldung gehoert nicht auf stderr. Eine Veraenderung an der
#       Auswertung eines Beweismittels darf nicht still geschehen - und
#       eine Zeile, die zwischen den Zeilen eines Laufs auf stderr
#       erscheint, ist so gut wie still: sie steht in keinem Protokoll und
#       in keinem Vermerk (Grundregel 1).
#   (2) ATTRIBUTname und ELEMENTname sind zu unterscheiden. Ein Anker zaehlt
#       Elemente und Textknoten - Attribute kommen darin nicht vor, die
#       Umschreibung ist dort folgenlos. Ein umgeschriebener ELEMENTname
#       dagegen laesst einen Anker brechen, denn der Anker verlangt den
#       urspruenglichen Namen.
#
# HZ13  die Warnung erreicht stderr NICHT mehr, sondern die Befunde
# HZ14  ein Attributname wird als folgenlos benannt - und der Anker traegt
# HZ15  ein ELEMENTname wird laut gemeldet ('DIESE STELLE GEHOERT ANGESEHEN')
# HZ16  GEGENPROBE: ein heiler Abzug erzeugt KEINEN solchen Befund
# ---------------------------------------------------------------------------

import warnings as _warnings


#: Genau der Konstrukt aus Alex' Abzug: eine Entitaet zwischen zwei
#: Attributen (s. M6 zu Zeile 141).
_ENTITAET_ZWISCHEN_ATTRIBUTEN = (
    '<donate><div id="wrap"><div id="page-body">'
    '<article class="post" id="p1">'
    '<p>Vor <a href="/x" rel="nofollow"&#160; target="_blank">T</a> nach.</p>'
    '</article></div></div></donate>')


def _mit_aufgefangenen_warnungen(quelle):
    with _warnings.catch_warnings(record=True) as durchgelassen:
        _warnings.simplefilter("always")
        wurzel, befunde = Html5Zerleger().zerlege(quelle)
    return wurzel, befunde, [str(w.message) for w in durchgelassen]


def test_HZ13_die_warnung_erreicht_stderr_nicht_mehr():
    _wurzel, befunde, durchgelassen = _mit_aufgefangenen_warnungen(
        _ENTITAET_ZWISCHEN_ATTRIBUTEN)
    assert durchgelassen == [], \
        "die Meldung gehoert in die Befunde, nicht auf stderr"
    # ABER SIE VERSCHWINDET NICHT: verschwiegen waere schlimmer als laut.
    assert any("umgeschrieben" in b for b in befunde), befunde


def test_HZ14_ein_attributname_ist_folgenlos_und_wird_so_benannt():
    wurzel, befunde, _ = _mit_aufgefangenen_warnungen(
        _ENTITAET_ZWISCHEN_ATTRIBUTEN)
    text = "\n".join(befunde)
    assert "&#160;" in text
    assert "folgenlos" in text
    assert "ACHTUNG" not in text, "ein Attributname ist kein lauter Befund"
    # UND DER BELEG DAZU: der Anker traegt. Ohne diese Zeile waere die
    # Aussage 'folgenlos' eine Behauptung.
    anker = "./donate[1]/div[1]/div[1]/article[1]/p[1]/text()[1]"
    assert wurzel.xpath(anker)
    assert len(wurzel.xpath("//article/p")[0].xpath("./text()")) == 2


def test_HZ15_ein_elementname_wird_laut_gemeldet():
    # DIESER FALL TRITT WIRKLICH EIN: ein Tagname mit '&' wird zu
    # 'aU00026b' umgeschrieben. Der Anker verlangt weiterhin 'a&b' und
    # faende nichts - der Bruch waere sichtbar, die Ursache stuende nirgends.
    _wurzel, befunde, _ = _mit_aufgefangenen_warnungen(
        '<donate><div id="wrap"><div id="page-body">'
        '<article class="post" id="p1"><a&b>x</a&b><p>T</p></article>'
        '</div></div></donate>')
    text = "\n".join(befunde)
    assert "ACHTUNG" in text, text
    assert "a&b" in text
    assert "GEHOERT ANGESEHEN" in text


def test_HZ16_gegenprobe_ein_heiler_abzug_meldet_nichts():
    # OHNE DIESE PROBE waeren HZ13-HZ15 auch mit einer Fassung gruen, die
    # bei jedem Lauf etwas meldet - und ein Befund ohne Anlass verwaessert
    # die Befunde, auf die es ankommt.
    _wurzel, befunde, durchgelassen = _mit_aufgefangenen_warnungen(
        _seite('<div id="page-header"><h1>Forum</h1></div>'))
    assert befunde == []
    assert durchgelassen == []
