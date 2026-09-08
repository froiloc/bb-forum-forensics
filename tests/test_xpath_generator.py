# -*- coding: utf-8 -*-
"""
tests/test_xpath_generator.py — BUILD 766

Waechter fuer den XPath-Generator (Regelkatalog selection_json 2.0,
Abschnitt 3).

XG01  ein Knoten unter eindeutiger id ankert ueber by_id
XG02  GEGENPROBE: eine MEHRFACH vergebene id wird NICHT verwendet
XG03  mehrfach vergebene ids werden ausgewiesen, nicht nur vermieden
XG04  ohne id wird ueber die Klasse angekert
XG05  GEGENPROBE zu XG04: Zustandsklassen werden nicht verwendet
XG06  der index bei by_class zaehlt ueber die GEFILTERTE Menge
XG07  ohne id und ohne brauchbare Klasse bleibt by_position
XG08  der erzeugte Ausdruck trifft IMMER genau den Zielknoten
XG09  Textknoten: der letzte Schritt bleibt eine Zaehlung
XG10  zwei gleiche Textknoten im selben Element werden unterschieden
XG11  by_id ersetzt den GESAMTEN Praefix
XG12  'haengt_an_zaehlung' meldet nur Zaehlungen NACH dem letzten by_id
"""
import sys
from pathlib import Path

from lxml import html as LH

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from management.maintenance.xpath_generator import (            # noqa: E402
    RANG_ID, RANG_KLASSE, RANG_POSITION, XPathGenerator)


def _baum(roh: str):
    return LH.fromstring(roh)


def _text(doc, wortlaut):
    return doc.xpath("//text()[normalize-space(.)=$t]", t=wortlaut)[0]


#: Ein Abzug nach viewtopic0.php mit ZWEI Beitraegen. 'progressbar' steht in
#: beiden - viewtopic0.php Z. 989 schreibt es innerhalb der postleft, also je
#: Beitrag einmal.
_ZWEI_BEITRAEGE = """<div><div id="page-body">
<article class="post" id="p700"><div class="box" id="pp700">
  <div class="postbody">
    <div class="postleft"><div id="progressbar"><span>BALKEN700</span></div></div>
    <div class="postright"><h3>BETREFF</h3>
      <div class="postmsg">INHALT<p>ABSATZ</p><p class="postedit">EDIT</p></div>
    </div></div></div></article>
<article class="post" id="p701"><div class="box" id="pp701">
  <div class="postbody">
    <div class="postleft"><div id="progressbar"><span>BALKEN701</span></div></div>
    <div class="postright"><div class="postmsg">ZWEITER</div></div>
  </div></div></article>
</div></div>"""


def test_XG01_eindeutige_id_wird_zum_anker():
    """
    Eine dokumentweit eindeutige id ist der staerkste Anker: sie haengt weder
    an sibling-Zaehlung noch an der Reihenfolge.
    """
    doc = _baum(_ZWEI_BEITRAEGE)
    g = XPathGenerator(doc)
    e = g.fuer(_text(doc, "INHALT"))
    assert e.traegt, e.hinweis
    assert e.bester_rang == RANG_ID, e.rangzaehlung
    assert "@id='pp700'" in e.ausdruck, e.ausdruck


def test_XG02_gegenprobe_mehrfache_id_wird_nicht_verwendet():
    """
    DIE ENTSCHEIDENDE PROBE. Das Forum ist nicht normkonform: 'progressbar'
    steht je Beitrag einmal, auf einer Seite mit 500 Beitraegen also 500-mal.

    Ohne Eindeutigkeitspruefung entstuende '//*[@id="progressbar"]/...' - ein
    Ausdruck, der AUFLOEST und den ersten von 500 Kandidaten liefert. Das ist
    schlimmer als ein Bruch, weil es unbemerkt bleibt.
    """
    doc = _baum(_ZWEI_BEITRAEGE)
    g = XPathGenerator(doc)
    e = g.fuer(_text(doc, "BALKEN701"))
    assert e.traegt, e.hinweis
    assert "progressbar" not in e.ausdruck, \
        "eine mehrfach vergebene id darf nicht als Anker dienen: %s" % e.ausdruck
    # Er muss trotzdem eindeutig treffen - ueber die Beitragskennung.
    assert "@id='pp701'" in e.ausdruck, e.ausdruck
    assert len(doc.xpath(e.ausdruck)) == 1


def test_XG03_mehrfache_ids_werden_ausgewiesen():
    """
    Sie werden BENANNT und nicht nur vermieden. Welche ids betroffen sind, ist
    ein Befund am Forum und gehoert ins Protokoll - nicht in eine Annahme.
    Offen war bis Build 766, ob include/poll.php und include/header0.php
    weitere enthalten.
    """
    doc = _baum(_ZWEI_BEITRAEGE)
    g = XPathGenerator(doc)
    assert g.mehrfache_ids == {"progressbar": 2}, g.mehrfache_ids


def test_XG04_ohne_id_wird_ueber_die_klasse_angekert():
    doc = _baum("""<div><section><div class="alpha"><p>EINS</p></div>
        <div class="beta"><p>ZWEI</p></div></section></div>""")
    g = XPathGenerator(doc)
    e = g.fuer(_text(doc, "ZWEI"))
    assert e.traegt, e.hinweis
    assert e.rangzaehlung[RANG_KLASSE] >= 1, e.rangzaehlung
    assert " beta " in e.ausdruck, e.ausdruck


def test_XG05_gegenprobe_zustandsklassen_werden_nicht_verwendet():
    """
    OHNE DIESE PROBE waere XG04 auch mit einer Fassung gruen, die JEDE Klasse
    nimmt. Eine Zustandsklasse sagt nichts darueber aus, WO ein Element steht.
    """
    doc = _baum("""<div><section>
        <div class="hidden"><p>EINS</p></div>
        <div class="censored"><p>ZWEI</p></div></section></div>""")
    g = XPathGenerator(doc)
    e = g.fuer(_text(doc, "ZWEI"))
    assert e.traegt, e.hinweis
    assert "hidden" not in e.ausdruck and "censored" not in e.ausdruck, \
        e.ausdruck
    assert e.bester_rang == RANG_POSITION, e.rangzaehlung


def test_XG06_der_index_zaehlt_ueber_die_gefilterte_menge():
    """
    'div[3]' bedeutet 'das dritte div-Kind'; 'div[contains(...)][3]' bedeutet
    'unter den div-Kindern MIT dieser Klasse das dritte'. Das ist nicht
    dasselbe Element.

    Hier tragen nur zwei von fuenf div-Kindern die Klasse 'ziel'. Das zweite
    davon ist das vierte div-Kind - der index muss 2 sein, nicht 4.
    """
    doc = _baum("""<div><section>
        <div class="ziel"><p>A</p></div>
        <div class="andere"><p>B</p></div>
        <div class="andere"><p>C</p></div>
        <div class="ziel"><p>D</p></div>
        <div class="andere"><p>E</p></div></section></div>""")
    g = XPathGenerator(doc)
    e = g.fuer(_text(doc, "D"))
    assert e.traegt, e.hinweis
    assert "][2]" in e.ausdruck, \
        "der index muss ueber die gefilterte Menge zaehlen: %s" % e.ausdruck
    assert "][4]" not in e.ausdruck, e.ausdruck
    assert len(doc.xpath(e.ausdruck)) == 1


def test_XG07_ohne_id_und_klasse_bleibt_die_zaehlung():
    doc = _baum("<div><section><p>EINS</p><p>ZWEI</p><p>DREI</p></section></div>")
    g = XPathGenerator(doc)
    e = g.fuer(_text(doc, "DREI"))
    assert e.traegt, e.hinweis
    assert e.bester_rang == RANG_POSITION, e.rangzaehlung
    assert e.ausdruck.endswith("p[3]/text()[1]"), e.ausdruck


def test_XG08_der_ausdruck_trifft_immer_genau_den_zielknoten():
    """
    DIE UEBERGREIFENDE ZUSICHERUNG. Fuer JEDEN Knoten des Abzugs muss der
    erzeugte Ausdruck genau einen Treffer liefern, und zwar den erwarteten.
    Ein Ausdruck, der zwei Knoten trifft, ist nicht 'fast richtig' - die
    Auswertung liefert dann stillschweigend den ersten.
    """
    doc = _baum(_ZWEI_BEITRAEGE)
    g = XPathGenerator(doc)
    geprueft = 0
    for el in doc.iter():
        if not isinstance(getattr(el, "tag", None), str):
            continue
        if el is doc:
            continue
        e = g.fuer(el)
        assert e.traegt, "%s: %s" % (e.ausdruck, e.hinweis)
        treffer = doc.xpath(e.ausdruck)
        assert len(treffer) == 1, (e.ausdruck, len(treffer))
        assert treffer[0] is el, e.ausdruck
        geprueft += 1
    assert geprueft >= 15, geprueft


def test_XG09_der_letzte_schritt_zu_einem_text_bleibt_eine_zaehlung():
    """
    Ein Textknoten traegt weder id noch class. Der Generator macht das
    ELEMENT robust, nicht die Position im Text - genau dort sind 38 der 44
    Brueche des Laufs zu Build 764 entstanden.
    """
    doc = _baum(_ZWEI_BEITRAEGE)
    g = XPathGenerator(doc)
    e = g.fuer(_text(doc, "INHALT"))
    assert e.ausdruck.endswith("/text()[1]"), e.ausdruck


def test_XG10_zwei_gleiche_textknoten_werden_unterschieden():
    """
    Zwei Textknoten desselben Elements koennen denselben Wortlaut tragen. Sie
    ueber den Inhalt zu unterscheiden reicht nicht - die Nummer entscheidet.
    """
    doc = _baum("<div><p>GLEICH<br/>GLEICH</p></div>")
    p = doc.xpath("//p")[0]
    knoten = p.xpath("text()")
    assert len(knoten) == 2, len(knoten)
    g = XPathGenerator(doc)
    e1, e2 = g.fuer(knoten[0]), g.fuer(knoten[1])
    assert e1.traegt and e2.traegt, (e1.hinweis, e2.hinweis)
    assert e1.ausdruck != e2.ausdruck, e1.ausdruck
    assert e1.ausdruck.endswith("text()[1]"), e1.ausdruck
    assert e2.ausdruck.endswith("text()[2]"), e2.ausdruck


def test_XG11_by_id_ersetzt_den_gesamten_praefix():
    """
    Ein by_id-Schritt macht alles davor bedeutungslos - das ist sein Wert.
    Der Ausdruck beginnt danach mit '//*[@id=...]' und nicht mit einem Weg
    von der Wurzel.
    """
    doc = _baum(_ZWEI_BEITRAEGE)
    g = XPathGenerator(doc)
    e = g.fuer(_text(doc, "ZWEITER"))
    assert e.traegt, e.hinweis
    assert e.ausdruck.startswith("//*[@id="), e.ausdruck
    assert any(s.ersetzt_praefix for s in e.schritte), \
        [s.als_dict() for s in e.schritte]


def test_XG12_haengt_an_zaehlung_meldet_nur_was_nach_by_id_kommt():
    """
    Ein by_position VOR einem by_id ist bedeutungslos, weil der Praefix
    ersetzt wurde. Nur was DANACH kommt, haengt noch an der sibling-Zaehlung.

    Das ist die Zahl, an der sich der Nutzen des Generators messen laesst -
    sie darf nicht durch Schritte aufgeblaeht werden, die gar nicht mehr im
    Ausdruck stehen.
    """
    doc = _baum(_ZWEI_BEITRAEGE)
    g = XPathGenerator(doc)
    # 'INHALT' liegt direkt im postmsg: nach dem by_id folgen nur Klassen.
    ohne = g.fuer(_text(doc, "INHALT"))
    assert ohne.haengt_an_zaehlung is False, ohne.ausdruck
    # 'ABSATZ' liegt in einem <p> ohne Klasse: danach folgt eine Zaehlung.
    mit = g.fuer(_text(doc, "ABSATZ"))
    assert mit.haengt_an_zaehlung is True, mit.ausdruck
    assert mit.rangzaehlung[RANG_POSITION] >= 1, mit.rangzaehlung


# =============================================================================
# XG13 bis XG15 — aus Mutationsgegenproben entstanden
# =============================================================================
# Drei Mutationen blieben zunaechst gruen. Zwei davon zeigten echte Luecken:
#
#   M1 'keine Eindeutigkeitspruefung bei by_id'  -> blieb gruen
#   M4 'keine Rueckpruefung je Schritt'          -> blieb gruen
#
# Der Grund ist, dass beide DASSELBE verhindern und sich gegenseitig
# abdecken: Faellt die Eindeutigkeitspruefung weg, faengt die Rueckpruefung
# den mehrdeutigen Ausdruck; faellt die Rueckpruefung weg, kommt der
# mehrdeutige Ausdruck wegen der Eindeutigkeitspruefung gar nicht erst
# zustande. Das ist gute Absicherung in zwei Lagen - aber keine der beiden
# Lagen war EINZELN geprueft. XG13 und XG14 pruefen sie getrennt.
#
# Die dritte Mutation - 'is_text'-Zweig in _textnummer entfernt - blieb
# ebenfalls gruen, und dafuer gibt es KEINE Luecke zu schliessen: der
# Rueckfall ueber den Inhalt liefert fuer einen '.text'-Knoten immer die
# Nummer 1, und das ist die richtige Antwort. Der Zweig ist eine Abkuerzung,
# keine Zusicherung. Das wird hier festgehalten, statt einen Waechter zu
# erfinden, der eine Verhaltensgleichheit als Unterschied ausgibt.
# =============================================================================

def test_XG13_die_eindeutigkeitspruefung_wirkt_fuer_sich():
    """
    ISOLIERT DIE ERSTE LAGE. '_bauen' darf fuer eine mehrfach vergebene id
    keinen by_id-Schritt liefern - unabhaengig davon, ob die Rueckpruefung
    danach noch einmal zuschlaegt.
    """
    doc = _baum(_ZWEI_BEITRAEGE)
    g = XPathGenerator(doc)
    doppelt = doc.xpath("//*[@id='progressbar']")[0]
    einzeln = doc.xpath("//*[@id='pp700']")[0]

    assert g._bauen(RANG_ID, "", doppelt, "div") is None, \
        "eine mehrfach vergebene id darf keinen by_id-Schritt liefern"
    gebaut = g._bauen(RANG_ID, "", einzeln, "div")
    assert gebaut is not None and gebaut[0] == "//*[@id='pp700']", gebaut
    assert gebaut[1] is True, "by_id ersetzt den Praefix"


def test_XG14_die_rueckpruefung_wirkt_fuer_sich():
    """
    ISOLIERT DIE ZWEITE LAGE. '_trifft_ziel' muss einen mehrdeutigen Ausdruck
    ablehnen, auch wenn er den Zielknoten enthaelt.

    Ein Ausdruck, der zwei Knoten trifft, ist nicht 'fast richtig' - die
    Auswertung liefert dann stillschweigend den ersten.
    """
    doc = _baum(_ZWEI_BEITRAEGE)
    g = XPathGenerator(doc)
    doppelt = doc.xpath("//*[@id='progressbar']")
    assert len(doppelt) == 2, len(doppelt)

    # Der Ausdruck TRIFFT das Ziel - aber nicht nur das Ziel.
    assert g._trifft_ziel("//*[@id='progressbar']", doppelt[0]) is False
    assert g._trifft_ziel("//*[@id='progressbar']", doppelt[1]) is False
    # Eindeutig und richtig.
    assert g._trifft_ziel("//*[@id='pp700']",
                          doc.xpath("//*[@id='pp700']")[0]) is True
    # Eindeutig, aber der falsche Knoten.
    assert g._trifft_ziel("//*[@id='pp700']",
                          doc.xpath("//*[@id='pp701']")[0]) is False


def test_XG15_die_textnummer_wird_strukturell_bestimmt():
    """
    Die Reihenfolge der Textknoten eines Elements ist festgelegt: zuerst
    '.text' des Elements, danach je Kind dessen '.tail'. Genau daran wird
    abgezaehlt.

    Geprueft werden die Formen, in denen ein Vergleich ueber den Inhalt die
    falsche Antwort gaebe.
    """
    doc = _baum("<div><p>EINS<br/>ZWEI<br/>DREI</p></div>")
    g = XPathGenerator(doc)
    p = doc.xpath("//p")[0]
    for erwartet, knoten in enumerate(p.xpath("text()"), 1):
        assert g._textnummer(p, knoten) == erwartet, \
            (erwartet, str(knoten))

    # Ohne eigenen Text des Elements beginnt die Zaehlung beim ersten tail.
    doc2 = _baum("<div><p><br/>NURTAIL<br/>ZWEITER</p></div>")
    g2 = XPathGenerator(doc2)
    p2 = doc2.xpath("//p")[0]
    assert p2.text is None, repr(p2.text)
    knoten2 = p2.xpath("text()")
    assert g2._textnummer(p2, knoten2[0]) == 1
    assert g2._textnummer(p2, knoten2[1]) == 2

    # Drei gleichlautende Textknoten - der Inhalt unterscheidet nicht.
    doc3 = _baum("<div><p>X<br/>X<br/>X</p></div>")
    g3 = XPathGenerator(doc3)
    p3 = doc3.xpath("//p")[0]
    nummern = [g3._textnummer(p3, k) for k in p3.xpath("text()")]
    assert nummern == [1, 2, 3], nummern


def test_XG16_die_rueckpruefung_faengt_einen_mehrdeutigen_schritt():
    """
    DIE RUECKPRUEFUNG IM ABLAUF, nicht nur als Funktion (XG14).

    Warum das eine untergeschobene Konstruktion braucht: Bei korrektem Bau
    ist KEIN Schritt je mehrdeutig - by_id nur bei eindeutiger id, by_class
    und by_position mit einem index ueber die jeweils gefilterte Menge. Die
    Rueckpruefung feuert deshalb im Regelbetrieb nie. Sie ist Absicherung
    gegen einen kuenftigen Konstruktionsfehler, und genau als solche wird sie
    hier geprueft: '_bauen' wird ueberschrieben und liefert fuer by_class
    absichtlich einen mehrdeutigen Ausdruck.

    Ohne die Rueckpruefung wuerde dieser Ausdruck uebernommen, und der
    Generator lieferte still das falsche Element.
    """
    class MitFehlerhaftemBau(XPathGenerator):
        def _bauen(self, rang, praefix, element, marke):
            if rang == RANG_KLASSE:
                # Absichtlich mehrdeutig: trifft ALLE gleichnamigen Elemente.
                return self._anhaengen(praefix, marke), False
            return super()._bauen(rang, praefix, element, marke)

    doc = _baum("""<div><section>
        <div class="alpha"><p>EINS</p></div>
        <div class="alpha"><p>ZWEI</p></div></section></div>""")
    g = MitFehlerhaftemBau(doc)
    e = g.fuer(_text(doc, "ZWEI"))

    assert e.traegt, ("der Generator muss trotz des fehlerhaften Baus einen "
                      "tragfaehigen Ausdruck liefern: %s" % e.hinweis)
    assert len(doc.xpath(e.ausdruck)) == 1, e.ausdruck
    # NUR DER div-SCHRITT IST WIRKLICH MEHRDEUTIG. <section> und <p> sind
    # unter ihren siblings ohnehin eindeutig - dort trifft auch der
    # untergeschobene Ausdruck genau einen Knoten, und die Rueckpruefung hat
    # nichts zu beanstanden. Die Zusicherung muss deshalb den div-Schritt
    # benennen und nicht pauschal alle.
    div_schritte = [s for s in e.schritte if s.marke == "div"]
    assert len(div_schritte) == 1, [s.als_dict() for s in e.schritte]
    div = div_schritte[0]
    assert div.rang == RANG_POSITION, div.als_dict()
    assert div.ausdruck == "div[2]", div.als_dict()
    # Der Rueckfall ist vermerkt, nicht verschwiegen.
    assert any("by_class trifft nicht eindeutig" in grund
               for grund in div.rueckfaelle), div.als_dict()


def test_XG17_lange_befundzeilen_werden_sichtbar_gekuerzt():
    """
    lxml haengt an eine Meldung die betroffene Quellzeile an. Bei
    'DTD_ID_REDEFINED' - das im Forum auf jeder Seite feuert, weil
    'id="progressbar"' je Beitrag einmal geschrieben wird - ist das der
    gesamte anonymisierte Seitenrumpf. Auf einer Seite mit 500 Beitraegen
    entstuende eine Protokollzeile von hunderttausend Zeichen.

    Gekuerzt wird die WIEDERGABE, nicht der Befund: Art und Ort stehen am
    Anfang der Zeile und bleiben. Dass gekuerzt wurde, MUSS sichtbar sein -
    sonst sieht ein abgeschnittener Text wie ein vollstaendiger aus
    (Grundregel 1).
    """
    import tools.anker_diagnose as cli

    kurz = "ERROR:VALID:DTD_ID_REDEFINED: ID progressbar already defined"
    assert cli._gekuerzt(kurz) == kurz, "Kurzes wird nicht angefasst"

    # lxml liefert die Meldung samt Quellzeile als EINEN mehrzeiligen Text.
    # Ohne Einziehen der Umbrueche wuerde nur der erste Abschnitt gekuerzt,
    # und der Rumpf stuende in den Folgezeilen weiter im Protokoll - ohne
    # Kennzeichnung, weil das Praefix nur einmal geschrieben wird.
    mehrzeilig = kurz + "\n   1 | " + ("x" * 5000)
    aus_m = cli._gekuerzt(mehrzeilig)
    assert "\n" not in aus_m, "Umbrueche muessen eingezogen sein"
    assert len(aus_m) < 300, len(aus_m)

    lang = kurz + " | " + ("x" * 5000)
    aus = cli._gekuerzt(lang)
    assert len(aus) < 300, len(aus)
    assert aus.startswith("ERROR:VALID:DTD_ID_REDEFINED"), aus
    assert "gekuerzt" in aus, aus
    assert str(len(lang)) in aus, \
        "die urspruengliche Laenge muss genannt sein: %s" % aus
