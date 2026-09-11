# -*- coding: utf-8 -*-
"""
tests/test_wortlaut_abgleich.py — BUILD 767

Waechter fuer den dreistufigen Wortlautabgleich.

WA01  Stufe 1: Treffer im benannten Beitrag
WA02  Stufe 2: der benannte Beitrag ist verrutscht, ein Nachbar traegt ihn
WA03  Stufe 3: der Treffer liegt ausserhalb der zehn Nachbarn
WA04  die Stufen werden in der Reihenfolge gegangen, nicht uebersprungen
WA05  kein Treffer: Aehnlichkeit und Distanz statt Behauptung
WA06  der gemessene Zensurfall loest auf und wird gekennzeichnet
WA07  Lage des Treffers: Inhaltsbereich gegen Rahmen
WA08  Mehrdeutigkeit wird benannt, nicht aufgeloest
WA09  zu kurze Wortlaute werden gekennzeichnet
WA10  Editierdistanz: richtig gerechnet und mit Obergrenze
"""
import sys
from pathlib import Path

from lxml import html as LH

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from management.maintenance.post_bereiche import (                # noqa: E402
    LAGE_CONTENT, LAGE_FRAME)
from management.maintenance.wortlaut_abgleich import (            # noqa: E402
    KURZ_AB, STUFE_BEITRAG, STUFE_NACHBARN, STUFE_SEITE, WortlautAbgleich,
    editierdistanz)


def _beitrag(n, inhalt, rahmen="RAHMENTEXT"):
    return ('<article class="post" id="p%d"><div class="box" id="pp%d">'
            '<div class="postbody">'
            '<div class="postleft">%s%d</div>'
            '<div class="postright"><div class="postmsg">%s</div></div>'
            '</div></div></article>' % (n, n, rahmen, n, inhalt))


def _seite(beitraege):
    return LH.fromstring('<div><div id="page-body">%s</div></div>'
                         % "".join(beitraege))


def _reihe(anzahl=14, ab=700):
    return _seite([_beitrag(ab + i, "Inhalt von Beitrag %d" % (ab + i))
                   for i in range(anzahl)])


def test_WA01_stufe_eins_der_benannte_beitrag():
    a = WortlautAbgleich(_reihe(), "viewtopic")
    b = a.pruefe("Inhalt von Beitrag 703", 703)
    assert b.gefunden and b.stufe == STUFE_BEITRAG, b.als_dict()
    assert b.fundorte[0].post_id == 703
    assert b.eindeutig is True
    assert b.im_benannten_beitrag is True


def test_WA02_stufe_zwei_der_anker_ist_verrutscht():
    """
    Der gemessene Regelfall: der Anker benennt einen Beitrag in der Naehe,
    aber nicht den richtigen. Alex' Messungen ergaben Versaetze von -4, -2,
    -2 und zweimal -42.
    """
    a = WortlautAbgleich(_reihe(), "viewtopic")
    b = a.pruefe("Inhalt von Beitrag 703", 705)
    assert b.gefunden and b.stufe == STUFE_NACHBARN, b.als_dict()
    assert b.fundorte[0].post_id == 703
    assert b.im_benannten_beitrag is False


def test_WA03_stufe_drei_ausserhalb_der_nachbarn():
    """Mehr als fuenf Beitraege entfernt - Stufe 2 greift nicht mehr."""
    a = WortlautAbgleich(_reihe(), "viewtopic")
    b = a.pruefe("Inhalt von Beitrag 700", 713)
    assert b.gefunden and b.stufe == STUFE_SEITE, b.als_dict()
    assert b.fundorte[0].post_id == 700


def test_WA04_die_stufen_werden_der_reihe_nach_gegangen():
    """
    DIE ENTSCHEIDENDE PROBE ZUR ABSTUFUNG. Steht derselbe Wortlaut in
    mehreren Beitraegen, muss der BENANNTE gewinnen - sonst waere die Stufe
    keine Aussage ueber den Anker, sondern nur ueber die Dokumentreihenfolge.
    """
    doppelt = _seite([_beitrag(700 + i, "derselbe Wortlaut ueberall")
                      for i in range(14)])
    a = WortlautAbgleich(doppelt, "viewtopic")
    b = a.pruefe("derselbe Wortlaut ueberall", 706)
    assert b.stufe == STUFE_BEITRAG, b.als_dict()
    assert [f.post_id for f in b.fundorte] == [706], b.als_dict()


def test_WA05_kein_treffer_liefert_zahlen_statt_behauptung():
    a = WortlautAbgleich(_reihe(), "viewtopic")
    b = a.pruefe("ein voellig anderer Text, der nirgends steht", 703)
    assert not b.gefunden
    assert b.stufe == "", b.als_dict()
    assert 0.0 < b.beste_aehnlichkeit < 1.0, b.beste_aehnlichkeit
    assert b.bester_beitrag is not None
    assert isinstance(b.editierdistanz, int) and b.editierdistanz > 0
    assert "kein exakter Treffer" in b.hinweis


def test_WA06_der_gemessene_zensurfall():
    """
    Annotation 1488/273. Der Ausschluss der versteckten Fassung muss den
    Treffer ermoeglichen UND als wirksam gekennzeichnet werden - sonst
    wuesste niemand, dass hier etwas Besonderes vorlag.
    """
    zensiert = ('@Alice&nbsp; &nbsp;@<span class="censorship">'
                '<span class="censored">*censored*</span>'
                '<span class="uncensored hidden">Fenixxx</span></span>')
    a = WortlautAbgleich(_seite([_beitrag(800, zensiert)]), "viewtopic")
    b = a.pruefe("@Alice   @*censored*", 800)
    assert b.gefunden and b.stufe == STUFE_BEITRAG, b.als_dict()
    assert b.versteckt_wirksam is True, \
        "die Wirkung des Ausschlusses muss ausgewiesen sein"
    assert b.fundorte[0].lage == LAGE_CONTENT


def test_WA07_lage_inhalt_gegen_rahmen():
    """
    Ein Treffer im Rahmen ist etwas anderes als einer im Inhalt: bei einer
    'text range' muesste er im Inhalt liegen, sonst ist die Typzuordnung
    nicht belegt.
    """
    a = WortlautAbgleich(_reihe(), "viewtopic")
    im_inhalt = a.pruefe("Inhalt von Beitrag 702", 702)
    assert im_inhalt.fundorte[0].lage == LAGE_CONTENT, im_inhalt.als_dict()
    im_rahmen = a.pruefe("RAHMENTEXT702", 702)
    assert im_rahmen.gefunden, im_rahmen.als_dict()
    assert im_rahmen.fundorte[0].lage == LAGE_FRAME, im_rahmen.als_dict()


def test_WA08_mehrdeutigkeit_wird_benannt():
    """
    Steht der Wortlaut mehrfach, wird das GESAGT und nicht durch die Wahl
    des ersten Fundorts verdeckt. 'eindeutig' ist dann falsch.
    """
    # Zweimal im selben Beitrag.
    doppelt_intern = _seite([_beitrag(700, "hallo welt und nochmal hallo welt")])
    a = WortlautAbgleich(doppelt_intern, "viewtopic")
    b = a.pruefe("hallo welt", 700)
    assert b.gefunden and b.eindeutig is False, b.als_dict()
    assert b.fundorte[0].vorkommen == 2, b.als_dict()

    # In mehreren Beitraegen derselben Stufe.
    mehrere = _seite([_beitrag(700 + i, "gleicher Text") for i in range(3)])
    a2 = WortlautAbgleich(mehrere, "viewtopic")
    b2 = a2.pruefe("gleicher Text", 999)      # Beitrag nicht im Abzug
    assert len(b2.fundorte) == 3, b2.als_dict()
    assert b2.eindeutig is False
    assert "999" in b2.hinweis, b2.hinweis


def test_WA09_zu_kurze_wortlaute_werden_gekennzeichnet():
    """
    Kurze Zeichenketten treffen zufaellig - bei Hypothesis der dokumentierte
    Fehlerfall. Der Befund VERWIRFT sie nicht, er kennzeichnet sie; ob eine
    Laenge ausreicht, entscheidet Alex nach der Messung.
    """
    a = WortlautAbgleich(_reihe(), "viewtopic")
    kurz = a.pruefe("Inhalt", 703)
    assert kurz.zu_kurz is True, (kurz.wortlaut, len(kurz.wortlaut), KURZ_AB)
    assert kurz.gefunden is True, "gekennzeichnet, nicht verworfen"
    lang = a.pruefe("Inhalt von Beitrag 703", 703)
    assert lang.zu_kurz is False


def test_WA10_editierdistanz():
    assert editierdistanz("abc", "abc") == 0
    assert editierdistanz("abc", "abd") == 1
    assert editierdistanz("kitten", "sitting") == 3, "Lehrbuchbeispiel"
    assert editierdistanz("", "abc") == 3
    # Obergrenze: darueber wird nicht gerechnet, und das wird gesagt.
    assert editierdistanz("a" * 10, "a" * 10, grenze=5) is None


# =============================================================================
# BUILD 768 — der blockweise Vergleich
# =============================================================================
# DER BEFUND AUS DEM LAUF ZU BUILD 767: Von 30 nicht gefundenen Wortlauten
# waren 24 vom Typ 'ganzer Post als text-range markiert'. Die Aehnlichkeiten
# lagen zwischen 0,79 und 0,99 - das sah nach einer Schwelle aus, war aber
# keine Textabweichung, sondern eine FALSCHE SUCHMENGE: bei einem 'whole post'
# umfasst der Wortlaut Rahmen UND Inhalt, in der Reihenfolge, in der der
# Browser sie sichtbar aneinanderreiht, mit Umbruechen, die im Abzug nicht
# stehen.
#
# WA11  Bloecke werden VOR der Normalisierung getrennt
# WA12  ein 'whole post'-Wortlaut wird blockweise gefunden
# WA13  GEGENPROBE: die Reihenfolge der Bloecke muss stimmen
# WA14  der Treffer als EINE Zeichenkette hat Vorrang
# WA15  ein einzelner Block loest keine blockweise Suche aus
# =============================================================================

def _whole_post_seite():
    """
    Ein Beitrag, dessen Rahmen und Inhalt zwischen anderem Text liegen -
    so, wie ein 'ganzer Post' im Abzug steht.
    """
    return LH.fromstring(
        '<div><div id="page-body">'
        '<article class="post" id="p900"><div class="box" id="pp900">'
        '<div class="postbody">'
        '<div class="postleft">Hello77<span>Leumund: 19.353</span></div>'
        '<div class="postright"><h3>Re: Verification</h3>'
        '<div class="postmsg">Der eigentliche Beitragstext.</div></div>'
        '</div></div></article>'
        '</div></div>')


def test_WA11_bloecke_werden_vor_der_normalisierung_getrennt():
    """
    'normalisiere()' faltet Umbrueche zu Leerzeichen. Wer zuerst normalisiert
    und dann trennt, hat keine Blockgrenzen mehr.
    """
    a = WortlautAbgleich(_whole_post_seite(), "viewtopic")
    bloecke = a._bloecke("Hello77\nRe: Verification\nDer eigentliche Beitragstext.")
    assert len(bloecke) == 3, bloecke
    assert bloecke[0] == "hello77", bloecke
    # Leere Zeilen fallen weg, sie tragen keinen Beleg.
    assert a._bloecke("a\n\n\nb") == ["a", "b"]


def test_WA12_whole_post_wird_blockweise_gefunden():
    """
    DER FALL, DER DIESEN NACHTRAG AUSGELOEST HAT. Als EINE Zeichenkette ist
    der Wortlaut nicht zu finden - die Teile stehen im Abzug mit anderem Text
    dazwischen. Blockweise und in Reihenfolge steht er vollstaendig da.
    """
    doc = _whole_post_seite()
    a = WortlautAbgleich(doc, "viewtopic")
    wortlaut = "Hello77\nRe: Verification\nDer eigentliche Beitragstext."

    # Als eine Kette: kein Treffer.
    from management.maintenance.wortlaut_norm import normalisiere
    assert normalisiere(wortlaut) not in a._text_je_nummer[900]

    b = a.pruefe(wortlaut, 900)
    assert b.gefunden, b.als_dict()
    assert b.blockweise is True, b.als_dict()
    assert b.bloecke == 3, b.als_dict()
    assert b.stufe == STUFE_BEITRAG, b.als_dict()
    # Ein Block liegt im Rahmen -> nach der Regel aus Build 764 'whole post'.
    assert b.fundorte[0].lage == LAGE_FRAME, b.als_dict()


def test_WA13_gegenprobe_die_reihenfolge_muss_stimmen():
    """
    OHNE DIESE PROBE waere WA12 auch mit einer Fassung gruen, die nur fragt,
    ob jeder Block irgendwo vorkommt. Dann waere jede Ansammlung derselben
    Woerter ein Treffer - und der Rahmen eines Beitrags wiederholt sich auf
    einer Seite hundertfach.
    """
    a = WortlautAbgleich(_whole_post_seite(), "viewtopic")
    verdreht = "Der eigentliche Beitragstext.\nHello77"
    b = a.pruefe(verdreht, 900)
    assert not b.gefunden, b.als_dict()
    assert b.blockweise is False, b.als_dict()


def test_WA14_der_treffer_als_eine_kette_hat_vorrang():
    """
    Blockweise ist die SCHWAECHERE Aussage: der Wortlaut steht vollstaendig
    im Beitrag, aber mit Unterbrechungen. Wo er am Stueck steht, muss das
    auch so gemeldet werden.
    """
    a = WortlautAbgleich(_whole_post_seite(), "viewtopic")
    b = a.pruefe("Der eigentliche Beitragstext.", 900)
    assert b.gefunden and b.blockweise is False, b.als_dict()
    assert b.fundorte[0].lage == LAGE_CONTENT, b.als_dict()


def test_WA15_ein_einzelner_block_loest_keine_blockweise_suche_aus():
    """
    Bei einem Wortlaut ohne Umbruch waere die blockweise Suche mit der
    gewoehnlichen identisch - sie wuerde nur ein zweites Mal dasselbe tun und
    das Ergebnis faelschlich als 'blockweise' kennzeichnen.
    """
    a = WortlautAbgleich(_whole_post_seite(), "viewtopic")
    b = a.pruefe("steht hier nirgends", 900)
    assert not b.gefunden
    assert b.blockweise is False, b.als_dict()
    assert b.bloecke == 1, b.als_dict()


# =============================================================================
# BUILD 768 — die Aufspaltung ueber mehrere Beitraege
# =============================================================================
# DER EIGENTLICHE AUFTRAG. Festzustellen, dass eine Markierung ueber mehrere
# Beitraege laeuft, ist keine Leistung - das war bekannt. Gebraucht wird die
# Auskunft, WELCHE Beitraege es sind und WAS aus jedem wuerde. Erst wenn das
# je Beitrag belegt ist, darf die Migration aufspalten.
#
# WA16  eine Markierung ueber drei Beitraege zerfaellt in drei Teilstuecke
# WA17  je Teilstueck steht, was daraus wuerde
# WA18  Bloecke ausserhalb jedes Beitrags werden AUSGEWIESEN, nicht getilgt
# WA19  ein fuehrender Block ausserhalb blockiert die Verteilung nicht
# WA20  die ganze Seite: alle Beitraege einzeln, Fusszeile als entfallend
# =============================================================================

def _mehrere_beitraege(anzahl=5):
    def eins(i):
        return ('<article class="post" id="p%d"><div class="box" id="pp%d">'
                '<div class="postbody"><div class="postleft">Autor%d</div>'
                '<div class="postright"><h3>Betreff %d</h3>'
                '<div class="postmsg">Text von Beitrag %d.</div>'
                '</div></div></div></article>'
                % (900 + i, 900 + i, i, i, i))
    # Der Themenbetreff steht VOR den Beitraegen, die Fusszeile dahinter -
    # wie im echten Abzug. Die Geometrie ist wesentlich: eine Markierung, die
    # in der Fusszeile beginnt und bei Beitrag 2 endet, kann es nicht geben.
    return LH.fromstring(
        '<div><div id="page-body"><h2 class="topic-title">Themenbetreff</h2>'
        '%s<div id="page-footer">Fusszeile</div>'
        '</div></div>' % "".join(eins(i) for i in range(anzahl)))


def _rumpf(i):
    return "Autor%d\nBetreff %d\nText von Beitrag %d." % (i, i, i)


def _anker(doc, erster, letzter):
    """
    Die beiden Ankerpunkte einer Markierung - als Textknoten im Baum.

    BUILD 769: Die Aufspaltung braucht sie zwingend. Ohne sie ist die Spanne
    nicht bestimmbar, und dann gibt es keine Aufspaltung, sondern eine
    Vorlage (siehe WA21).
    """
    def knoten(wortlaut):
        tr = doc.xpath("//text()[contains(., $t)]", t=wortlaut)
        assert tr, "Testvorrichtung: %r steht nicht im Baum" % wortlaut
        return tr[0]
    return knoten(erster), knoten(letzter)


def test_WA16_markierung_ueber_drei_beitraege_zerfaellt():
    doc = _mehrere_beitraege()
    a = WortlautAbgleich(doc, "viewtopic")
    b = a.pruefe("\n".join(_rumpf(i) for i in (1, 2, 3)), 901,
                 *_anker(doc, "Autor1", "Text von Beitrag 3."))
    assert not b.gefunden, "kein EINZELNER Beitrag traegt ihn"
    assert [s.post_id for s in b.teilstuecke] == [901, 902, 903], \
        [s.als_dict() for s in b.teilstuecke]
    assert "ueber 3 Beitraege verteilt" in b.hinweis, b.hinweis
    assert b.als_dict()["candidates"] == [901, 902, 903], b.als_dict()
    assert b.als_dict()["split_complete"] is True


def test_WA17_je_teilstueck_steht_was_daraus_wuerde():
    """
    Die Angabe 'would_become' ist die Bruecke zur Migration: sie sagt je
    Beitrag, ob daraus eine 'text range' oder ein 'whole post' wird - nach
    derselben Regel wie in Build 764, naemlich ob alle Bloecke im
    Inhaltsbereich liegen.
    """
    doc = _mehrere_beitraege()
    a = WortlautAbgleich(doc, "viewtopic")
    # Mit Rahmen (Autor, Betreff) -> whole post.
    mit_rahmen = a.pruefe("\n".join(_rumpf(i) for i in (1, 2)), 901,
                          *_anker(doc, "Autor1", "Text von Beitrag 2."))
    assert all(s.als_dict()["would_become"] == "whole post"
               for s in mit_rahmen.teilstuecke), \
        [s.als_dict() for s in mit_rahmen.teilstuecke]
    # Nur Inhalt -> text range.
    nur_inhalt = a.pruefe("Text von Beitrag 1.\nText von Beitrag 2.", 901,
                          *_anker(doc, "Text von Beitrag 1.",
                                  "Text von Beitrag 2."))
    stuecke = [s for s in nur_inhalt.teilstuecke if s.post_id is not None]
    assert stuecke, nur_inhalt.als_dict()
    assert all(s.als_dict()["would_become"] == "text range" for s in stuecke), \
        [s.als_dict() for s in stuecke]


def test_WA18_bloecke_ausserhalb_werden_ausgewiesen():
    """
    Was zwischen den Beitraegen markiert war, entfaellt bei der Aufspaltung
    ersatzlos (Festlegung Alex, 08.09.2026). DASS es entfaellt, muss zu SEHEN
    sein - sonst waere es ein stiller Verlust (Grundregel 1).
    """
    doc = _mehrere_beitraege()
    a = WortlautAbgleich(doc, "viewtopic")
    b = a.pruefe("Text von Beitrag 1.\nirgendwas fremdes\n"
                 "Text von Beitrag 3.", 901,
                 *_anker(doc, "Text von Beitrag 1.", "Text von Beitrag 3."))
    arten = [s.als_dict()["would_become"] for s in b.teilstuecke]
    assert "entfaellt" in arten, [s.als_dict() for s in b.teilstuecke]
    assert b.als_dict()["split_complete"] is False, \
        "mit einem Rest ausserhalb ist die Aufspaltung NICHT vollstaendig"


def test_WA19_ein_fuehrender_block_ausserhalb_blockiert_nicht():
    """
    GEFUNDEN AN EINER PROBE MIT VORANGESTELLTER FUSSZEILE.

    Eine beitragsweise Schleife - 'nimm vom aktuellen Beitrag so viele
    Bloecke wie moeglich' - kaeme hier gar nicht erst in Gang: der erste
    Block steht in keinem Beitrag, also nimmt kein Beitrag etwas, und die
    ganze Markierung gaelte als 'ausserhalb'. Verteilt wird deshalb JE
    BLOCK der naechste Beitrag, der ihn traegt.
    """
    doc = _mehrere_beitraege()
    a = WortlautAbgleich(doc, "viewtopic")
    b = a.pruefe("Themenbetreff\nText von Beitrag 2.\nText von Beitrag 3.",
                 901, *_anker(doc, "Themenbetreff", "Text von Beitrag 3."))
    assert [s.post_id for s in b.teilstuecke] == [None, 902, 903], \
        [s.als_dict() for s in b.teilstuecke]
    assert b.teilstuecke[0].block_von == 0
    assert b.teilstuecke[0].als_dict()["would_become"] == "entfaellt"


def test_WA20_die_ganze_seite_zerfaellt_in_ihre_beitraege():
    """
    DER FALL 1704143/1: 62988 Zeichen, 'hier wurde einfach mal die gesamte
    Seite markiert'. Bis Build 767 war das nur ein 'nicht gefunden'. Jetzt
    muss der Lauf sagen, welche Beitraege eingeschlossen sind und was aus
    jedem wuerde - sonst waere es kein Fortschritt, sondern die Wiederholung
    einer bekannten Feststellung.
    """
    doc = _mehrere_beitraege(5)
    a = WortlautAbgleich(doc, "viewtopic")
    ganze = "\n".join(_rumpf(i) for i in range(5)) + "\nFusszeile"
    b = a.pruefe(ganze, 900, *_anker(doc, "Autor0", "Fusszeile"))
    d = b.als_dict()
    assert d["split_posts"] == [900, 901, 902, 903, 904], d["split_posts"]
    assert d["split_complete"] is False, "die Fusszeile entfaellt"
    assert b.teilstuecke[-1].post_id is None
    assert b.teilstuecke[-1].als_dict()["would_become"] == "entfaellt"
    # Je Beitrag ein eigener Datensatz - das ist die Aussage, die die
    # Migration braucht.
    assert len([s for s in b.teilstuecke if s.post_id is not None]) == 5



def test_WA21_ohne_ankerpunkte_gibt_es_keine_aufspaltung():
    """
    DIE REGEL AUS BUILD 769. Ohne beide Ankerpunkte ist die Spanne nicht
    bestimmbar - und eine Aufspaltung ohne Schranke waere geraten.

    Gemessen am Fall 583231/6: ohne Schranke verteilte das Verfahren die
    Bloecke ueber NEUN Beitraege, weil kurze Bloecke in spaeteren Beitraegen
    zufaellig treffen und jeder Zufallstreffer den Suchzeiger weiterschiebt.
    Mit Schranke sind es ZWEI - die beiden, die zwischen Start- und Endanker
    liegen.

    Eine geratene Zuordnung ist schlimmer als keine (Grundregel 1). Der Fall
    kommt deshalb auf die Vorlageliste.
    """
    doc = _mehrere_beitraege()
    a = WortlautAbgleich(doc, "viewtopic")
    b = a.pruefe("\n".join(_rumpf(i) for i in (1, 2, 3)), 901)
    assert not b.teilstuecke, [s.als_dict() for s in b.teilstuecke]
    assert b.kandidaten == [], b.kandidaten
    assert "nicht bestimmbar" in b.hinweis, b.hinweis


def test_WA22_die_schranke_begrenzt_auf_die_spanne():
    """
    Die Kandidaten sind genau die Beitraege, deren Bereich im Baum die Spanne
    zwischen den Ankerpunkten beruehrt - nicht alle Beitraege der Seite.
    """
    doc = _mehrere_beitraege(5)
    a = WortlautAbgleich(doc, "viewtopic")
    start, ende = _anker(doc, "Autor1", "Text von Beitrag 2.")
    assert a.kandidaten_zwischen(start, ende) == [901, 902], \
        a.kandidaten_zwischen(start, ende)
    # Ein Endpunkt AUSSERHALB jedes Beitrags verschiebt die Grenze nicht
    # willkuerlich: die Fusszeile steht hinter allen Beitraegen.
    start2, ende2 = _anker(doc, "Autor3", "Fusszeile")
    assert a.kandidaten_zwischen(start2, ende2) == [903, 904], \
        a.kandidaten_zwischen(start2, ende2)
    assert a.beitragszahl == 5


def test_WA23_beitraege_werden_gezaehlt_nicht_abschnitte():
    """
    Ein Beitrag kann mehrfach vorkommen, wenn zwischen seinen Bloecken etwas
    liegt, das in keinem Kandidaten steht. 'ueber 19 Beitraege verteilt' war
    in einer Messung zu 583231/6 die Ausgabe - es waren ZWEI Beitraege mit
    neunzehn Abschnitten.
    """
    doc = _mehrere_beitraege(3)
    a = WortlautAbgleich(doc, "viewtopic")
    # Zweimal derselbe Beitrag, dazwischen Fremdtext.
    wortlaut = "Autor1\nirgendwas fremdes\nText von Beitrag 1."
    b = a.pruefe(wortlaut, 901, *_anker(doc, "Autor1", "Text von Beitrag 1."))
    d = b.als_dict()
    assert d["split_post_count"] == 1, d
    assert d["split_sections"] >= 2, d
    assert "ueber 1 Beitrag verteilt" in b.hinweis, b.hinweis
