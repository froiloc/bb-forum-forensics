# =============================================================================
# tests/test_html5_annaeherung.py
#
# Build 737: Die Annaeherung des Seitenabzugs an die Browser-Zerlegung.
#
# WAS HIER AUF DEM SPIEL STEHT
#
# Der Anker einer Textmarkierung wird IM BROWSER gerechnet und SERVERSEITIG
# mit libxml2 aufgeloest. Sehen beide verschiedene Baeume, zeigt ein
# richtiger Anker ins Leere - und der Bericht faellt auf die Wortlautsuche
# zurueck, den Notfall-Rueckfall. Genau das geschah in Alex' Laeufen vom
# 28.08.2026 bei ALLEN 25 Belegen.
#
# DIE MESSUNG, AUF DER DIESE DATEI STEHT (30.08.2026): zehn HTML-Konstrukte
# wurden gegen Chromium (Playwright, 'innerHTML' auf einen <div> - der Weg
# des Ermittlungsfensters) und gegen libxml2 gehalten. Gezaehlt wurden die
# Kinder unter 'div#wrap'.
#
#   Konstrukt                          Browser  libxml2  nach Annaeherung
#   ---------------------------------------------------------------------
#   <noscript> mit offenem <div>          6        2            6
#   <template> mit offenem <div>          6        2            6
#   <noscript> heil                       6        6            6
#   <noscript> mit maskiertem </div>      6        6            6
#   <div> ohne Ende                       2        2            2
#   Kommentar ohne Ende                   2        2            2
#   <script> mit "<div>" im String        6        6            6
#   <td> ohne Ende                        6        6            6
#   schlicht                              6        6            6
#   <a> ohne Ende                         3        6            6   <- BLEIBT
#
# Die ersten beiden Zeilen sind das Fehlerbild aus Alex' Laeufen. Die letzte
# ist die BEKANNTE GRENZE - sie wird hier ausdruecklich mitgetestet, damit
# niemand die Annaeherung fuer einen HTML5-Zerleger haelt.
#
# HA01  <noscript> mit unausgeglichenem Inhalt wird geleert
# HA02  <template> ebenso
# HA03  das Element BLEIBT stehen - es zaehlt im Browser mit
# HA04  GEGENPROBE: <script> und <style> werden NICHT angefasst
# HA05  ein Rohtext-Element OHNE schliessendes Gegenstueck bleibt unberuehrt
# HA06  die Befundliste benennt jeden Eingriff (GR1 - nichts still tun)
# HA07  GEGENPROBE: ohne Rohtext-Element aendert sich NICHTS am Text
# HA08  rohtext_stellen unterscheidet ausgeglichen von unausgeglichen
# HA09  DER FALL AUS DER MESSUNG, ganz: der Anker bricht roh und traegt
#       nach der Annaeherung
# HA10  GEGENPROBE ZU HA09: ein Abzug OHNE <noscript> traegt schon roh -
#       die Annaeherung ist nicht das, was ihn traegt
#
# Beleg: report_render/html5_annaeherung.py; Messung gegen Chromium
#        30.08.2026; Alex' Laeufe 28.08.2026; Sonde LAUF D 29.08.2026.
# =============================================================================

from lxml import html as lxml_html

from report_render.html5_annaeherung import (annaehern, rohtext_stellen,
                                             ROHTEXT_ELEMENTE)


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


def _kinder_unter_wrap(body: str):
    """Die Kinder von 'div#wrap' - dieselbe Zaehlung wie in der Messung."""
    wurzel = lxml_html.fragment_fromstring(body, create_parent="div")
    donate = [k for k in wurzel if isinstance(k.tag, str)][0]
    wrap = [k for k in donate if isinstance(k.tag, str)][0]
    return [(k.get("id") or k.tag) for k in wrap if isinstance(k.tag, str)]


# ---------------------------------------------------------------------------
def test_HA01_noscript_mit_offenem_tag_wird_geleert():
    # DER FALL AUS DER MESSUNG. Bei eingeschaltetem JavaScript liest der
    # Browser den Inhalt von <noscript> als ROHTEXT - kein Tag darin wird zu
    # einem Element. libxml2 kennt die Regel nicht; das offene <div>
    # verschluckt dann alles Folgende.
    body = _seite('<div id="page-header"><noscript><div class="n">X</noscript></div>')
    assert _kinder_unter_wrap(body) == ["brdleft", "page-header"]
    neu, _ = annaehern(body)
    assert _kinder_unter_wrap(neu) == ["brdleft", "page-header", "style",
                                       "div", "page-body", "page-footer"]


def test_HA02_template_ebenso():
    # <template> ist der zweite Fall: sein Inhalt gehoert in HTML5 in ein
    # eigenes DocumentFragment und steht ueberhaupt nicht im Baum der Seite.
    body = _seite('<div id="page-header"><template><div>X</template></div>')
    assert _kinder_unter_wrap(body) == ["brdleft", "page-header"]
    neu, _ = annaehern(body)
    assert len(_kinder_unter_wrap(neu)) == 6


def test_HA03_das_element_selbst_bleibt_stehen():
    # ES WIRD GELEERT, NICHT ENTFERNT. Im Browser ist <noscript> ein Element
    # und zaehlt mit; wer es entfernte, verschoebe jede folgende Zaehlung um
    # eins und erzeugte damit denselben Fehler in der Gegenrichtung.
    neu, _ = annaehern('<div><noscript><span>x</span></noscript></div>')
    assert "<noscript>" in neu and "</noscript>" in neu
    assert "<span>" not in neu


def test_HA04_gegenprobe_script_und_style_bleiben_unberuehrt():
    # Ihr Inhalt ist in BEIDEN Verfahren Rohtext - sie brauchen keine
    # Annaeherung. Ohne diese Probe waere HA01 auch mit einer Fassung gruen,
    # die jeden Rohtextbereich leert; dann verschwaende die Formatierung der
    # Seite aus dem Vermerk, und niemand wuesste warum.
    assert "script" not in ROHTEXT_ELEMENTE and "style" not in ROHTEXT_ELEMENTE
    quelle = '<div><script>var s="<div>";</script><style>.a{}</style></div>'
    neu, befunde = annaehern(quelle)
    assert neu == quelle
    assert befunde == []


def test_HA05_ohne_schliessendes_gegenstueck_wird_nichts_angefasst():
    # Wo ein solches Element endet, ist NICHT zu entscheiden. Eine geratene
    # Grenze waere schlimmer als keine: sie schnitte moeglicherweise echten
    # Seiteninhalt weg, und zwar unauffaellig.
    quelle = '<div id="h"><noscript><div>ohne Ende</div>'
    neu, befunde = annaehern(quelle)
    assert neu == quelle
    assert any("OHNE schliessendes" in b for b in befunde)


def test_HA06_jeder_eingriff_wird_benannt():
    # GRUNDREGEL 1: nichts still tun. Die Annaeherung greift in die
    # Auswertung eines Beweismittels ein; was sie getan hat, gehoert in den
    # Vermerk, und dafuer muss es der Aufrufer erfahren.
    _neu, befunde = annaehern('<div><noscript><div>x</div></noscript></div>')
    assert befunde, "ein Eingriff ohne Meldung waere ein stiller Eingriff"
    assert "noscript" in befunde[0]
    assert "geleert" in befunde[0]


def test_HA07_gegenprobe_ohne_rohtextelement_bleibt_alles_gleich():
    # Ein Werkzeug, das immer etwas aendert, ist kein Werkzeug, sondern ein
    # Risiko. Auf der ueberwiegenden Zahl der Seiten darf es nichts tun.
    quelle = _seite('<div id="page-header"><h1>Forum</h1></div>')
    neu, befunde = annaehern(quelle)
    assert neu == quelle
    assert befunde == []


def test_HA08_ausgeglichen_und_unausgeglichen_werden_unterschieden():
    # NUR ein unausgeglichener Inhalt kann die Zerlegung sprengen. Ein heiles
    # <noscript> ist harmlos - das zu unterscheiden erspart eine Fehlspur,
    # und eine Fehlspur hat dieses Teilprojekt schon vier Builds gekostet.
    heil = rohtext_stellen('<noscript><div>x</div></noscript>')
    assert heil and heil[0][1] == "noscript" and heil[0][2] is True
    kaputt = rohtext_stellen('<noscript><div>x</noscript>')
    assert kaputt and kaputt[0][2] is False
    # Leere Elemente duerfen nicht als unausgeglichen gelten - sonst waere
    # jedes <noscript> mit einem <br> ein Verdachtsfall.
    mit_br = rohtext_stellen('<noscript>Bitte JavaScript<br>einschalten</noscript>')
    assert mit_br and mit_br[0][2] is True


def test_HA09_der_anker_traegt_erst_nach_der_annaeherung():
    # DER GANZE FALL, an dem Weg gemessen, den der Bericht geht.
    from report_render.absatz_finder import AbsatzFinder
    anker = "./donate[1]/div[1]/div[4]/article[1]/p[1]/text()[1]"
    body = _seite('<div id="page-header"><noscript><div class="n">X</noscript></div>')

    # Roh - so, wie es bis Build 736 war:
    wurzel = lxml_html.fragment_fromstring(body, create_parent="div")
    assert wurzel.xpath(anker) == []

    # Und ueber den Finder, der die Annaeherung seit Build 737 anwendet:
    finder = AbsatzFinder(body)
    assert finder.brauchbar
    assert finder._wurzel.xpath(anker), \
        "der Anker muss nach der Annaeherung tragen"
    assert finder.annaeherungsbefunde, \
        "und der Eingriff muss am Finder ablesbar sein"


def test_HA10_gegenprobe_ohne_noscript_traegt_der_anker_schon_roh():
    # OHNE DIESE PROBE WAERE HA09 AUCH MIT EINER FASSUNG GRUEN, die den
    # Anker aus einem anderen Grund treffen laesst. Hier ist belegt, dass
    # das <noscript> der Unterschied ist und nichts sonst.
    from report_render.absatz_finder import AbsatzFinder
    anker = "./donate[1]/div[1]/div[4]/article[1]/p[1]/text()[1]"
    body = _seite('<div id="page-header"><h1>Forum</h1></div>')
    wurzel = lxml_html.fragment_fromstring(body, create_parent="div")
    assert wurzel.xpath(anker), "schon roh muss er hier tragen"
    finder = AbsatzFinder(body)
    assert finder._wurzel.xpath(anker)
    assert finder.annaeherungsbefunde == [], \
        "und die Annaeherung darf hier NICHTS getan haben"


# ---------------------------------------------------------------------------
# Build 742 - ausstehende Endtags nachziehen
# ---------------------------------------------------------------------------
#
# GEMESSEN gegen Chromium am 30.08.2026 (Playwright, innerHTML auf einen
# <div> - der Weg des Ermittlungsfensters), 18 Konstrukte:
#   6 geheilt, 12 unveraendert richtig, 0 durch den Eingriff verschlechtert.

from report_render.html5_annaeherung import schliesse_offene


def test_HA11_der_fall_aus_dem_echten_bestand():
    # DAS KONSTRUKT AUS ALEX' ABZUG, nachgestellt: ein <div> bleibt in einem
    # <li> offen. libxml2 meldet dafuer GENAU die beiden Fehler aus seinem
    # Lauf ('li and div', 'ul and div') und laesst das <div> offen - alles
    # Folgende landet darin. Der Browser schliesst es.
    body = _seite('<div id="page-header"><ul><li><div class="a">x</li></ul></div>')
    assert _kinder_unter_wrap(body) == ["brdleft", "page-header"]
    neu, befunde = annaehern(body)
    assert _kinder_unter_wrap(neu) == ["brdleft", "page-header", "style",
                                       "div", "page-body", "page-footer"]
    assert any("Endtags nachgezogen" in b for b in befunde)


def test_HA12_auch_dd_und_mehrere_ebenen():
    for kopf in ('<div id="page-header"><dl><dd><div class="a">x</dd></dl></div>',
                 '<div id="page-header"><ul><li><div><div><span>x</li></ul></div>'):
        body = _seite(kopf)
        assert len(_kinder_unter_wrap(body)) == 2, kopf
        neu, _ = annaehern(body)
        assert len(_kinder_unter_wrap(neu)) == 6, kopf


def test_HA13_gegenprobe_am_heilen_abzug_wird_nichts_eingesetzt():
    # Ein Werkzeug, das immer etwas einsetzt, setzt irgendwann etwas
    # Falsches ein. Auf der ueberwiegenden Zahl der Seiten muss es nichts tun.
    heil = _seite('<div id="page-header"><ul><li><div class="a">x</div></li></ul></div>')
    neu, befunde = schliesse_offene(heil)
    assert neu == heil
    assert befunde == []


def test_HA14_gegenprobe_script_inhalt_bleibt_unangetastet():
    # Ein '</div>' in einer Zeichenkette im Skript ist KEIN Endtag. Wer es
    # mitzaehlt, repariert an Stellen, an denen nichts kaputt ist - und
    # macht damit heile Seiten kaputt.
    quelle = '<div id="h"><script>var s = "</div>";</script><p>x</p></div>'
    neu, befunde = schliesse_offene(quelle)
    assert neu == quelle
    assert befunde == []


def test_HA15_gegenprobe_fremdes_endtag_bleibt_stehen():
    # Ein Endtag zu einem gar nicht offenen Element wird NICHT entfernt.
    # Es zu entfernen waere ein Eingriff ohne Not, und jeder Eingriff kann
    # etwas kaputt machen.
    quelle = '<p>x</p></section>'
    neu, befunde = schliesse_offene(quelle)
    assert neu == quelle
    assert befunde == []


def test_HA16_jeder_eingriff_wird_benannt():
    # GRUNDREGEL 1: nichts still tun. Was eingesetzt wurde und wie oft,
    # gehoert in den Vermerk.
    _neu, befunde = schliesse_offene('<ul><li><div class="a">x</li></ul>')
    assert befunde
    assert "</div>" in befunde[0]
    assert "1 x" in befunde[0]
