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


# ---------------------------------------------------------------------------
# Build 745 - der Geltungsbereich, und das Einsatzprotokoll
#
# DER SCHADEN, DEN DIESE TESTS FESTHALTEN, WAR MEINER. Die Fassung aus
# Build 742 suchte das Element zu einem Endtag im GANZEN Stapel. HTML5 sucht
# nur innerhalb des Geltungsbereichs und verwirft das Endtag, wenn es das
# Element bis zur naechsten Grenze (<table>, <td>, <th>, <caption>, ...)
# nicht findet.
#
# GEMESSEN am 30.08.2026 an Alex' Bestand: roh standen ALLE 500 <article>
# unter '#page-body', nach meiner Annaeherung nur noch 2 - 498 waren nach
# '#wrap' herausgefallen. Nachgestellt mit einem verirrten '</div>' in einer
# Tabellenzelle und gegen Chromium gehalten:
#
#   Browser              3 <article>, alle 3 unter #page-body
#   libxml2 roh          3 <article>, alle 3 unter #page-body   (richtig)
#   libxml2 + Build 742  3 <article>, nur 1 unter #page-body     (falsch)
#   libxml2 + Build 745  3 <article>, alle 3 unter #page-body   (richtig)
#
# HA17  ein '</div>' in einer Zelle schliesst KEIN <div> ausserhalb der Zelle
# HA18  GEGENPROBE: dasselbe '</div>' INNERHALB der Zelle wirkt weiterhin -
#       der Geltungsbereich darf nicht zu eng sein, sonst heilt gar nichts
# HA19  '</li>' zieht weiterhin nach (Build 742 bleibt wirksam) - <ul> ist
#       zwar Grenze fuer </li>, aber erst UNTERHALB des <li>
# HA20  im_geltungsbereich() unmittelbar: hinter einer Grenze NEIN, davor JA
# HA21  das Einsatzprotokoll nennt Element, Ausloeser und Quelltextzeile
# HA22  ohne Nachzug an einem Element mit Kennung wird auch keiner benannt
# ---------------------------------------------------------------------------

from report_render.html5_annaeherung import (                     # noqa: E402
    annaehern_mit_protokoll, im_geltungsbereich,
    schliesse_offene_mit_protokoll)


#: Alex' Bild, nachgestellt: ein verirrtes '</div>' in einer Tabellenzelle
#: mitten im ersten Beitrag. Ohne den Geltungsbereich schliesst es
#: '#page-body' und wirft alle folgenden Beitraege heraus.
_ZELLE_MIT_STREUNENDEM_DIV = (
    '<donate><div id="wrap"><div id="page-body">'
    '<article class="post" id="p1"><table><tr><td>x</div></td></tr></table>'
    '</article><article class="post" id="p2">c</article>'
    '<article class="post" id="p3">d</article></div>'
    '<div id="page-footer">F</div></div></donate>')


def _artikel_unter_body(text: str):
    wurzel = lxml_html.fragment_fromstring(text, create_parent="div")
    body = wurzel.xpath("//*[@id='page-body']")
    artikel = wurzel.xpath("//article")
    if not body:
        return len(artikel), 0
    return len(artikel), len([a for a in artikel if a.getparent() is body[0]])


def test_HA17_endtag_in_einer_zelle_reicht_nicht_darueber_hinaus():
    # DER BROWSER LIEFERT HIER 3 VON 3 (gemessen mit Chromium, Playwright,
    # innerHTML auf einen <div> - der Weg des Ermittlungsfensters).
    gesamt, unter = _artikel_unter_body(_ZELLE_MIT_STREUNENDEM_DIV)
    assert (gesamt, unter) == (3, 3), "roh ist der Baum hier heil"
    neu, _befunde = annaehern(_ZELLE_MIT_STREUNENDEM_DIV)
    assert _artikel_unter_body(neu) == (3, 3), \
        "die Annaeherung darf #page-body NICHT aufreissen"


def test_HA18_gegenprobe_innerhalb_der_zelle_wirkt_der_nachzug_weiter():
    # OHNE DIESE PROBE waere HA17 auch mit einem Geltungsbereich gruen, der
    # so eng ist, dass ueberhaupt nichts mehr nachgezogen wird - und dann
    # waere der Fix aus Build 742 still wieder ausgebaut.
    quelle = '<td><ul><li><div class="a">x</li></ul></td>'
    neu, befunde = schliesse_offene(quelle)
    assert "</div>" in neu
    assert befunde and "</div>" in befunde[0]


def test_HA19_li_zieht_weiterhin_nach():
    # <ul> ist Grenze fuer '</li>' - aber die Suche trifft das <li> vorher.
    # Waere die Reihenfolge vertauscht, fiele der Fix aus Build 742 aus.
    body = _seite('<div id="page-header"><ul><li><div class="a">x</li></ul></div>')
    assert _kinder_unter_wrap(body) == ["brdleft", "page-header"]
    neu, _ = annaehern(body)
    assert _kinder_unter_wrap(neu) == ["brdleft", "page-header", "style",
                                       "div", "page-body", "page-footer"]


def test_HA20_der_geltungsbereich_endet_an_den_genannten_elementen():
    # Der Stapel traegt Tupel (Tagname, Kennzeichen, hat_id).
    def s(*namen):
        return [(n, n, False) for n in namen]
    # 'div' liegt VOR der Grenze - erreichbar.
    assert im_geltungsbereich(s("div", "span"), "div") is True
    # 'div' liegt HINTER einer Zellengrenze - nicht erreichbar.
    assert im_geltungsbereich(s("div", "table", "tr", "td", "span"),
                              "div") is False
    # Die Grenze selbst ist erreichbar - sonst schloesse kein '</td>' mehr.
    assert im_geltungsbereich(s("div", "table", "tr", "td", "span"),
                              "td") is True
    # 'p' hat <button> als zusaetzliche Grenze, 'div' nicht.
    assert im_geltungsbereich(s("p", "button", "span"), "p") is False
    assert im_geltungsbereich(s("div", "button", "span"), "div") is True
    # 'li' hat <ul> als zusaetzliche Grenze.
    assert im_geltungsbereich(s("li", "ul", "li", "span"), "li") is True
    assert im_geltungsbereich(s("li", "ul", "span"), "li") is False


def test_HA21_das_einsatzprotokoll_nennt_element_ausloeser_und_zeile():
    # DIE ZAEHLUNG '2 x </div>' SAGTE NICHT, WELCHES. Genau daran ist die
    # Verortung am 30.08.2026 gescheitert: EIN einziger Nachzug hatte
    # '#page-body' geschlossen, und ohne seine Stelle war er nicht
    # nachzustellen.
    quelle = ('<ul>\n'
              '<li><div id="kasten" class="a b c">x</li>\n'
              '</ul>')
    _neu, befunde, nachzuege = schliesse_offene_mit_protokoll(quelle)
    assert len(nachzuege) == 1
    n = nachzuege[0]
    assert n.kennzeichen == "div#kasten.a.b", n.kennzeichen
    assert n.marke == "div"
    assert n.ausloeser == "</li>"
    assert n.zeile == 2, n.zeile
    assert n.mit_kennung is True
    text = "\n".join(befunde)
    assert "Zeile 2: </li> hat div#kasten.a.b mitgeschlossen" in text, text


def test_HA22_gegenprobe_ohne_kennung_wird_keiner_benannt():
    # Ein nachgezogenes </span> im Beitragskopf verschiebt nichts, was ein
    # Anker verlangt - davon gibt es Hunderte. Sie einzeln zu melden hiesse,
    # die eine Zeile, auf die es ankommt, in Rauschen zu ertraenken. Ihre
    # ZAHL steht weiterhin in der Zeile davor (Grundregel 1).
    _neu, befunde, nachzuege = schliesse_offene_mit_protokoll(
        '<ul><li><div class="a">x</li></ul>')
    assert len(nachzuege) == 1
    assert nachzuege[0].mit_kennung is False
    text = "\n".join(befunde)
    assert "MIT KENNUNG" not in text, text
    assert "1 x </div>" in text, text


def test_HA23_das_protokoll_traegt_keinen_text_und_keine_fremden_attribute():
    # Das Protokoll geht in den Vermerk und ist damit weitergebbar. Offen
    # sind Tagname, 'id' und 'class'; 'href' und 'title' NICHT - dort
    # koennen Benutzernamen stehen.
    quelle = ('<ul><li><div id="k" class="a" title="Klarname Mueller" '
              'href="/profile.php?id=155955">Beitragstext'
              '<span>x</li></ul>')
    _neu, befunde, nachzuege = schliesse_offene_mit_protokoll(quelle)
    text = "\n".join(befunde) + " " + " ".join(n.kennzeichen for n in nachzuege)
    assert "Mueller" not in text, text
    assert "155955" not in text, text
    assert "Beitragstext" not in text, text
    assert "div#k.a" in text, text
