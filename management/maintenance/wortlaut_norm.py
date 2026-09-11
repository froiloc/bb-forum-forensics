# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/wortlaut_norm.py
# IT-Forensisches Ermittlungswerkzeug - aiw_webserver
# BUILD 767
# =============================================================================
# ZWECK
#   Zwei Dinge, die der Abgleich von 'selection_json.textContent' gegen den
#   page BLOB braucht und die es im Baum noch nicht gibt:
#
#     1. eine Unicode-Normalform fuer den Vergleich
#     2. eine Textentnahme, die NICHT GERENDERTE Elemente ueberspringt
#
# WAS ES SCHON GIBT UND HIER NICHT NACHGEBAUT WIRD
#   report_render/absatz_finder.browser_wortlaut() bildet seit Build 729 den
#   Text so, wie 'Range.toString()' ihn bildet - mit Umbruch an <br> und an
#   Blockgrenzen - und schreibt die Rueckabbildung der Versaetze auf den
#   Quelltext mit. Diese Datei ergaenzt genau die zwei Punkte, die dort
#   ausdruecklich ausgelassen sind ("Whitespace-Faltung nach CSS-Regeln bleibt
#   aussen vor").
#
# ZU (1) - WARUM NORMALISIERT WERDEN MUSS UND NICHT ZEICHENGENAU VERGLICHEN
#   'textContent' entsteht in toolbar.js Z. 1101 aus 'sel.toString()', also
#   'Selection.toString()'. Das ist NICHT 'Range.toString()': das erste
#   liefert den SICHTBAR ausgewaehlten Text, das zweite die Verkettung der
#   Textknoten. Im WHATWG-Archiv (Februar 2011) ist festgehalten, dass Gecko,
#   WebKit und IE8 dabei "in much more complicated ways, with lots of
#   complicated whitespace rules" stringifizieren - also browserabhaengig und
#   nicht interoperabel.
#
#   Diese Regeln lassen sich serverseitig nicht nachbilden. Ein zeichengenauer
#   Vergleich ist damit nicht schwierig, sondern unmoeglich. Normalisierung
#   und Aehnlichkeit sind deshalb kein Notbehelf, sondern der einzige Weg.
#   Festlegung Alex, 08.09.2026.
#
# ZU (2) - WARUM VERSTECKTE ELEMENTE UEBERSPRUNGEN WERDEN MUESSEN
#   Gemessener Fall (Alex, 08.09.2026, Annotation 1488/273):
#
#     sichtbar beim Markieren : '@Alice   @*censored*'
#     im page BLOB steht      : '@Alice&nbsp; &nbsp;@<span class="censorship">
#                                <span class="censored">*censored*</span>
#                                <span class="uncensored hidden">Fenixxx</span>
#                                </span>'
#
#   Die unzensierte Fassung steht im Abzug, ist aber 'display: none' und wird
#   erst beim Ueberfahren sichtbar - beim Markieren also nie. Eine naive
#   Textentnahme liefert '@Alice @*censored*Fenixxx'.
#
#   Das ist kein Sonderfall der Zensur, sondern die allgemeine Lage: der
#   Browser ueberspringt nicht gerenderte Elemente, eine Textentnahme aus dem
#   Baum nicht.
#
# WARUM DIE KLASSENLISTE STATISCH IST
#   Das Stylesheet liegt nicht im page BLOB, sondern in einem anderen BLOB in
#   default.db. Es zur Laufzeit zu lesen waere fuer eine Migration, die genau
#   einmal ueber 455 Annotationen laeuft, unverhaeltnismaessig (Festlegung
#   Alex, 08.09.2026). Die Liste wird deshalb aus dem Forenstil ERHOBEN und
#   hier mit Belegzeile gefuehrt.
#
# WARTUNGSSTUFE
#   Rein lesend, keine Datenbank.
# =============================================================================
from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

#: Klassen, die im Forenstil 'display: none' tragen. Ihr Inhalt ist beim
#: Markieren NICHT sichtbar und darf beim Abgleich nicht mitgelesen werden.
#:
#: Beleg: forum/html/style/Air.css Z. 1200 f. und style/index.css Z. 405 f.
#:   .hidden { display: none; }
#:
#: Im Forenquelltext kommt die Klasse an zwei Stellen vor:
#:   'uncensored hidden'  - die unzensierte Fassung eines zensierten Wortes
#:   'dropdown hidden'    - das Menue 'Quick links' im Seitenkopf
#:                          (Alex, 08.09.2026: genau eine Stelle, harmlos)
#:
#: NICHT ABSCHLIESSEND. Air.css nennt 22 weitere Regeln mit 'display: none',
#: unter anderem fuer .dropdown, .responsive-menu, .accordion, .compact,
#: .post-ignore, .lang und .avatar. Ob sie im Bestand vorkommen, ist
#: UNGEPRUEFT - der Messlauf zu Build 767 weist es aus.
VERSTECKTE_KLASSEN: Tuple[str, ...] = ("hidden",)


def normalisiere(text: str) -> str:
    """
    Die Normalform fuer den Vergleich.

    In dieser Reihenfolge:

      1. NFKC - vereinheitlicht typografische Varianten, die in einem
         multilingualen Forum sicher vorkommen: geschuetzte Leerzeichen
         (U+00A0, im gemessenen Fall 1488/273 als '&nbsp;'), Ligaturen,
         Breitzeichen, verschiedene Anfuehrungszeichen.
      2. Jede Folge von Leerraum zu EINEM Leerzeichen, Raender abschneiden.
      3. casefold() statt lower() - dieselbe Begruendung wie in
         management/crossref/subject_alias_repo.py Z. 103 ff.: das Forum ist
         multilingual, und lower() behandelt nicht jede Schrift richtig.

    SONDERZEICHEN BLEIBEN STEHEN. Sie zu entfernen wuerde Wortgrenzen
    verschmelzen: aus 'der Preis liegt bei 20' wuerde 'derPreisliegtbei20',
    und ein kurzer Wortlaut faende dann Treffer quer ueber Wortgrenzen hinweg.
    Genau dieser Fehlerfall ist bei Hypothesis dokumentiert (Ticket 3919:
    unscharfes Anchoring wird ineffizient und unzuverlaessig bei kurzen
    Zitaten aus Satz- und Leerraumzeichen). Zudem waere die Editierdistanz
    danach nicht mehr aussagekraeftig, weil die Struktur schon weg ist.
    """
    ohne_form = unicodedata.normalize("NFKC", str(text or ""))
    gefaltet = re.sub(r"\s+", " ", ohne_form).strip()
    return gefaltet.casefold()


def ist_versteckt(el) -> bool:
    """Traegt das Element eine Klasse, die im Forenstil 'display: none' ist?"""
    if not hasattr(el, "get"):
        return False
    klassen = set(str(el.get("class") or "").split())
    return any(k in klassen for k in VERSTECKTE_KLASSEN)


def sichtbarer_text(wurzel) -> str:
    """
    Der Text eines Teilbaums OHNE den Inhalt nicht gerenderter Elemente.

    Bildet 'browser_wortlaut()' nach - Umbruch an <br> und an Blockgrenzen -,
    ueberspringt dabei aber versteckte Teilbaeume. Der 'tail' eines
    versteckten Elements wird MITGENOMMEN: er steht ausserhalb des Elements
    und ist sichtbar.

    Rueckgabe ist der rohe Text; die Normalform bildet der Aufrufer, damit
    die ungefaltete Fassung fuer Gegenproben erhalten bleibt.
    """
    from report_render.absatz_finder import _UMBRUCH_TAGS

    aus: List[str] = []

    def umbruch() -> None:
        if aus and aus[-1] != "\n":
            aus.append("\n")

    def gehe(el) -> None:
        if el.text:
            aus.append(el.text)
        for kind in el:
            if not isinstance(getattr(kind, "tag", None), str):
                # Kommentare tragen keinen Text, ihr 'tail' aber schon.
                if kind.tail:
                    aus.append(kind.tail)
                continue
            if ist_versteckt(kind):
                # DER INHALT ENTFAELLT, DER 'tail' NICHT. Ein verstecktes
                # Element ist unsichtbar; was dahinter steht, ist es nicht.
                if kind.tail:
                    aus.append(kind.tail)
                continue
            if kind.tag in _UMBRUCH_TAGS:
                umbruch()
            gehe(kind)
            if kind.tag in _UMBRUCH_TAGS:
                umbruch()
            if kind.tail:
                aus.append(kind.tail)

    gehe(wurzel)
    return "".join(aus)


def versteckte_klassen_im_baum(wurzel) -> dict:
    """
    Welche Klassenkombinationen mit einer versteckten Klasse im Baum
    vorkommen, und wie oft.

    Ein BEFUND, keine Entscheidung: die Liste VERSTECKTE_KLASSEN ist aus dem
    Forenstil erhoben und ausdruecklich nicht abschliessend. Diese Zaehlung
    sagt, was im Bestand tatsaechlich steht.
    """
    aus: dict = {}
    for el in wurzel.iter():
        if not isinstance(getattr(el, "tag", None), str):
            continue
        if ist_versteckt(el):
            schluessel = " ".join(sorted(str(el.get("class") or "").split()))
            aus[schluessel] = aus.get(schluessel, 0) + 1
    return aus
