# -*- coding: utf-8 -*-
"""
tests/test_wortlaut_norm.py — BUILD 767

Waechter fuer die Normalisierung und die Textentnahme ohne nicht gerenderte
Elemente.

WN01  NFKC fuehrt das geschuetzte Leerzeichen auf ein gewoehnliches zurueck
WN02  Leerraumfolgen werden zu EINEM Leerzeichen, Raender fallen weg
WN03  casefold() statt lower() - das Forum ist multilingual
WN04  Sonderzeichen bleiben stehen
WN05  ein verstecktes Element wird uebersprungen
WN06  GEGENPROBE zu WN05: der 'tail' eines versteckten Elements bleibt
WN07  DER GEMESSENE FALL 1488/273 - Zensur
WN08  GEGENPROBE zu WN07: ohne den Ausschluss scheitert die Gleichheit
WN09  Umbrueche werden wie in browser_wortlaut gesetzt
WN10  versteckte Klassen werden ausgewiesen, nicht nur uebersprungen
"""
import sys
from pathlib import Path

from lxml import html as LH

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from management.maintenance.wortlaut_norm import (                # noqa: E402
    VERSTECKTE_KLASSEN, ist_versteckt, normalisiere, sichtbarer_text,
    versteckte_klassen_im_baum)
from report_render.absatz_finder import browser_wortlaut           # noqa: E402

#: Der gemessene Fall, wortgleich aus dem Abzug von Alex (08.09.2026).
#: Annotation 1488/273, Seite /forum/viewtopic.php?id=107823.
_ZENSUR = ('<div class="postmsg" style="border:0"><p>'
           '<span style="color:green;font-size:bigger">@Alice</span>'
           '&nbsp; &nbsp;'
           '<span style="color:green;font-size:bigger">@'
           '<span class="censorship">'
           '<span class="censored">*censored*</span>'
           '<span class="uncensored hidden">Fenixxx</span>'
           '</span></span></p></div>')

#: Was der Ermittler beim Markieren gesehen und was die Toolbar gespeichert
#: hat - aus dem INSERT von Alex.
_ZENSUR_GESPEICHERT = "@Alice   @*censored*"


def test_WN01_nfkc_fuehrt_das_geschuetzte_leerzeichen_zurueck():
    """
    Im gemessenen Fall stehen zwei '&nbsp;' (U+00A0). Ohne
    Unicode-Normalisierung waere schon dieses eine Beispiel gescheitert.
    """
    assert normalisiere("a\u00a0b") == "a b"
    # Weitere Formen, die ein multilinguales Forum sicher mitbringt.
    assert normalisiere("\uff21\uff22") == "ab", "Breitzeichen"
    assert normalisiere("\ufb01n") == "fin", "Ligatur fi"


def test_WN02_leerraum_wird_gefaltet():
    assert normalisiere("  a \t\n  b  ") == "a b"
    assert normalisiere("\n\n") == ""


def test_WN03_casefold_statt_lower():
    """
    Dieselbe Begruendung wie in subject_alias_repo Z. 103 ff.: das Forum ist
    multilingual, und lower() behandelt nicht jede Schrift richtig. Das
    deutsche Scharf-s ist der Fall, an dem sich beide unterscheiden.
    """
    assert normalisiere("STRASSE") == normalisiere("Stra\u00dfe"), \
        "casefold faltet 'ss' und Scharf-s zusammen, lower() nicht"
    assert "\u00df".lower() == "\u00df", "lower() laesst es stehen"


def test_WN04_sonderzeichen_bleiben_stehen():
    """
    Sie zu entfernen wuerde Wortgrenzen verschmelzen und die Editierdistanz
    entwerten. Die Zensurmarke besteht ueberdies AUS Sonderzeichen.
    """
    assert normalisiere("*censored*") == "*censored*"
    assert normalisiere("@Alice!") == "@alice!"
    assert normalisiere("der Preis: 20 \u20ac") == "der preis: 20 \u20ac"


def test_WN05_verstecktes_element_wird_uebersprungen():
    el = LH.fromstring('<div>vorn<span class="hidden">GEHEIM</span></div>')
    assert ist_versteckt(el.xpath("//span")[0])
    assert "GEHEIM" not in sichtbarer_text(el), sichtbarer_text(el)
    assert "vorn" in sichtbarer_text(el)


def test_WN06_gegenprobe_der_tail_bleibt():
    """
    OHNE DIESE PROBE waere WN05 auch mit einer Fassung gruen, die das ganze
    Element samt Nachtext verschluckt. Der 'tail' steht AUSSERHALB des
    versteckten Elements und ist sichtbar.
    """
    el = LH.fromstring(
        '<div>vorn<span class="hidden">GEHEIM</span>hinten</div>')
    text = sichtbarer_text(el)
    assert "GEHEIM" not in text, text
    assert "vorn" in text and "hinten" in text, text


def test_WN07_der_gemessene_zensurfall():
    """
    DER FALL, DER DIESEN BUILD AUSGELOEST HAT. Annotation 1488/273.

    Der Ermittler sieht '*censored*', der Abzug traegt zusaetzlich die
    unzensierte Fassung 'Fenixxx' in einem 'display: none'-Element. Erst mit
    dem Ausschluss ist der gespeicherte Wortlaut GLEICH dem sichtbaren Text.
    """
    el = LH.fromstring(_ZENSUR)
    sichtbar = normalisiere(sichtbarer_text(el))
    gespeichert = normalisiere(_ZENSUR_GESPEICHERT)

    assert "fenixxx" not in sichtbar, sichtbar
    assert gespeichert == sichtbar, (gespeichert, sichtbar)


def test_WN08_gegenprobe_ohne_ausschluss_scheitert_die_gleichheit():
    """
    OHNE DIESE PROBE bliebe unbelegt, dass der Ausschluss ueberhaupt etwas
    aendert. Sie haelt zugleich den feinen Unterschied fest, der die Sache
    so lange verdeckt hat:

      Die TEILKETTENSUCHE trifft auch ohne Ausschluss - der versteckte Text
      steht ja HINTER dem gesuchten. Nur die GLEICHHEIT scheitert. Genau
      deshalb hat 'wortlaut_im_beitrag()' den richtigen Beitrag gefunden,
      waehrend die Rueckprobe am Fundort fehlschlug.
    """
    el = LH.fromstring(_ZENSUR)
    ohne_ausschluss, _versaetze = browser_wortlaut(el)
    ohne = normalisiere(ohne_ausschluss)
    gespeichert = normalisiere(_ZENSUR_GESPEICHERT)

    assert "fenixxx" in ohne, ohne
    assert gespeichert in ohne, "die Teilkettensuche traf auch vorher"
    assert gespeichert != ohne, "die Gleichheit scheiterte - das ist der Punkt"


def test_WN09_umbrueche_wie_im_browser():
    """
    Die Entnahme bildet browser_wortlaut nach: Umbruch an <br> und an
    Blockgrenzen, aber keine Leerzeilen bei zwei Grenzen hintereinander.
    """
    el = LH.fromstring("<div><p>eins</p><p>zwei</p></div>")
    text = sichtbarer_text(el)
    assert "eins" in text and "zwei" in text
    assert "\n\n" not in text, repr(text)
    mit_br = LH.fromstring("<div><p>a<br/>b</p></div>")
    assert "\n" in sichtbarer_text(mit_br), repr(sichtbarer_text(mit_br))


def test_WN10_versteckte_klassen_werden_ausgewiesen():
    """
    Die Liste VERSTECKTE_KLASSEN ist aus dem Forenstil erhoben und
    ausdruecklich NICHT abschliessend. Was im Bestand tatsaechlich steht,
    muss deshalb gezaehlt und benannt werden - sonst bliebe eine Annahme
    stehen, wo eine Messung moeglich ist.
    """
    assert VERSTECKTE_KLASSEN, "die Liste darf nicht leer sein"
    assert "hidden" in VERSTECKTE_KLASSEN

    el = LH.fromstring(
        '<div><span class="uncensored hidden">a</span>'
        '<div class="dropdown hidden">b</div>'
        '<span class="hidden">c</span></div>')
    gezaehlt = versteckte_klassen_im_baum(el)
    assert gezaehlt == {"hidden uncensored": 1, "dropdown hidden": 1,
                        "hidden": 1}, gezaehlt


def test_AS01_der_arbeitsstand_nennt_die_ausgelieferte_buildnummer():
    """
    DIE ANTWORT AUF DIE UEBERGABEVERLUSTE.

    Ein Uebergabedokument, das am Ende einer Sitzung geschrieben wird,
    verliert die Haelfte des Wissens. Was traegt, steht im Repository. Was
    fehlte, war der Hinweis, WELCHE Dokumente in welcher Reihenfolge zu lesen
    sind - documents/Arbeitsstand.md.

    Sie kann nur helfen, wenn sie aktuell ist. Dieser Waechter haelt sie an
    build.json: nennt sie eine andere Buildnummer als die ausgelieferte,
    faellt er. Damit kann sie nicht veralten, ohne dass es auffaellt.
    """
    import json

    wurzel = Path(__file__).resolve().parent.parent
    pfad = wurzel / "documents" / "Arbeitsstand.md"
    assert pfad.exists(), "documents/Arbeitsstand.md fehlt"
    text = pfad.read_text(encoding="utf-8")

    with open(wurzel / "build.json", encoding="utf-8") as fh:
        build = json.load(fh)["build"]
    assert ("Build %d" % build) in text, \
        ("Der Arbeitsstand nennt Build %d nicht - er ist veraltet" % build)

    # Die Dokumente, ohne die keine Entscheidung nachvollziehbar ist.
    for pflicht in ("Regelkatalog_selection_json_2_0.md",
                    "Post_Bereiche_Katalog.md",
                    "build.json",
                    "issues.json"):
        assert pflicht in text, "Der Arbeitsstand verweist nicht auf %s" % pflicht
