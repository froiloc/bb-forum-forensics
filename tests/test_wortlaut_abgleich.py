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
