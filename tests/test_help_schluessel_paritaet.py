# =============================================================================
# tests/test_help_schluessel_paritaet.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H5)
# =============================================================================
# Testsuite fuer Build 592: die Paritaet zwischen den Hilfe-Marken IM BROWSER
# und den Texten IM REGISTER.
#
# WAS DIESER TEST KANN - UND WAS NICHT (bitte lesen, bevor man sich auf ihn
# verlaesst):
#   Er prueft die LITERALEN Marken: alles, was als data-hilfe-id="..." woertlich
#   in cockpit.html oder einer cockpit_*.js steht. Diese Marken kann eine
#   Textsuche vollstaendig finden, und genau deshalb schreibt das Konzept
#   (§4.2a) vor, dass Marken literal zu setzen sind.
#   Er kann NICHT die BERECHNETEN Anker finden, die das gemeinsame
#   Tabellen-Werkzeug seit Build 548 selbst setzt
#   ('sicht + ".spalte." + feldname'). Die entstehen erst beim Rendern. Dafuer
#   gibt es das Gegenstueck in vitest:
#   tests/unit/test_help_anker_paritaet.test.js rendert die Sicht in jsdom und
#   liest die Anker aus dem DOM. Beide Tests zusammen decken beide Arten ab;
#   einer allein waere ein halbes Netz, das sich fuer ein ganzes ausgibt.
#
# SP01 - jede literale Marke im Browser hat einen Text im Register
# SP02 - jeder Registerschluessel mit literalem Praefix kommt im Browser vor
#        (kein Text ins Leere), soweit er nicht ausdruecklich ausgenommen ist
# SP03 - jede Marke hat eine zulaessige Form (dieselbe wie HILFE_MUSTER in
#        cockpit_tablekit.js)
# SP04 - jeder Ankerpraefix, den der Bestand benutzt, ist im anker_katalog
#        einer Sicht zugeordnet
# SP05 - anker_katalog ist in sich stimmig (Sichten existieren, 'shell' fehlt)
# SP06 - keine Marke doppelt mit verschiedener Bedeutung (Eindeutigkeit)
# SP07 - Build 595: fuer die Sichten, deren Tabelle das gemeinsame Werkzeug
#        baut, hat JEDE Spalte mit Feld einen Registertext. Die Anker selbst
#        entstehen erst beim Rendern; die FELDNAMEN aber stehen literal in
#        columnDefs() und lassen sich hier statisch lesen. Die Liste der so
#        geprueften Sichten waechst je Inhaltswelle - sie ist ausdruecklich
#        und nicht abgeleitet, damit eine vergessene Sicht auffaellt.
# SP08 - Build 604: jedes woertliche BILDSCHIRMZITAT, das Regel H-1
#        aushebelt, kommt WIRKLICH als sichtbarer Text im Bestand vor.
#        Ohne diese Pruefung waere die Zitatliste ein Schlupfloch: man
#        koennte jeden Jargon hineinschreiben und behaupten, er stehe
#        auf dem Bildschirm.
#
# Version: v0.8.592 - Build: 592 - 2026-07-31
# =============================================================================

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.anker_katalog import (             # noqa: E402
    ANKER_PRAEFIXE, SHELL, verify_praefixe,
)
from management.help.inhalt import lade_register        # noqa: E402
from management.help.pruefung import BILDSCHIRMZITATE   # noqa: E402
from management.help.modell import schluessel_gueltig   # noqa: E402

STATIC = os.path.join(os.path.dirname(__file__), "..",
                      "management", "server", "static")

#: Literale Marken: data-hilfe-id="..." bzw. 'data-hilfe-id', '...'
_LITERAL = re.compile(r"""data-hilfe-id["']?\s*[=,]\s*["']([a-z0-9_.]+)["']""")

#: ZWEITE FORM EINER LITERALEN MARKE (Build 603): die Kapazitaetspflege baut
#: ihre vier Abschnittsueberschriften mit einem eigenen kleinen Helfer und
#: uebergibt ihm die Kennung als ZEICHENKETTE - '_abschnitt(mainEl,
#: 'capacity_worktime.titel', ...)'. Das Attribut selbst setzt danach das
#: gemeinsame Tabellen-Werkzeug (samt Formpruefung), es steht also nicht
#: woertlich in der Datei.
#:
#: Fuer die Sache ist das genauso literal wie ein geschriebenes Attribut: die
#: Kennung steht im Quelltext und wandert nicht. Nur dieser Test musste die
#: Form erst kennen. Sie ist bewusst an den HELFERNAMEN gebunden und nicht
#: allgemein an "Zeichenkette mit Punkt" - sonst hielte der Test jeden
#: Dateinamen ('cockpit_stats.js') fuer eine Hilfe-Marke.
_LITERAL_ABSCHNITT = re.compile(
    r"""_abschnitt\([^,]+,\s*['"]([a-z0-9_.]+)['"]""")

#: Sichten, deren Spaltenanker das gemeinsame Tabellen-Werkzeug erzeugt und
#: deren Texte bereits verfasst sind: Sicht-ID -> (Datei, Ankerpraefix).
#: JE INHALTSWELLE kommt hier ein Eintrag dazu. Steht eine Sicht hier, muss
#: jede ihrer Spalten einen Text haben - kein "fast fertig".
SPALTEN_QUELLEN = {
    "faelle": ("cockpit_overview.js", "overview"),
    "calendar": ("cockpit_calendar.js", "calendar"),
    # Build 596 (H8)
    "mycases": ("cockpit_mycases.js", "mycases"),
    "myhistory": ("cockpit_myhistory.js", "myhistory"),
    # Build 598 (H9)
    "reports": ("cockpit_reports.js", "reports"),
    "lectorate": ("cockpit_lectorate.js", "lectorate"),
    "approval": ("cockpit_approval.js", "approval"),
    # Build 599 (H10)
    "results": ("cockpit_results.js", "results"),
    # Build 602 (H11). Zwei Besonderheiten, beide belegt am Bestand:
    #  - 'stats' fuehrt ihre Tabelle unter der Kennung 'stats_assign'
    #    (cockpit_stats.js, tabelleAufbauen({sicht: 'stats_assign'})).
    #  - 'support' fuehrt DREI Tabellen mit DREI Kennungen (cockpit_support.js,
    #    Build 550). Dieselben sieben Spalten tragen dort drei verschiedene
    #    Praefixe; jeder braucht seinen Text, sonst bleibt eine der drei
    #    Tabellen stumm. Deshalb darf der zweite Wert ab hier auch ein Tupel
    #    von Praefixen sein - eine Sicht mit mehreren Tabellen ist kein
    #    Sonderfall, sondern kam bisher nur noch nicht vor.
    "stats": ("cockpit_stats.js", "stats_assign"),
    "support": ("cockpit_support.js",
                ("support_mine", "support_oncase", "support_weitere")),
    # Build 603 (H12). NUR 'mentoring' kommt hier dazu, und das ist eine
    # bewusste Auswahl, kein Vergessen:
    #  - 'personnel' benennt seine Spaltenanker NICHT nach dem Feld
    #    ('system_username' -> 'personnel.spalte.kennung'). Der Feldname taugt
    #    dort also nicht als Vorhersage; dieser Test wuerde etwas anderes
    #    pruefen, als im Browser entsteht.
    #  - 'capacity_pflege' fuehrt vier Tabellen mit VERSCHIEDENEN Spalten in
    #    EINER Datei. Eine Feldliste je Datei kann das nicht trennen.
    # Beide sind stattdessen von UX11 in der Konformitaetssuite gedeckt: dort
    # wird die Sicht gerendert und im DOM nachgesehen. Das ist die staerkere
    # Messung - sie trifft die Wahrheit statt sie vorherzusagen.
    "mentoring": ("cockpit_mentoring.js", "mentoring"),
    # Build 604 (H13). 'policy' fehlt hier bewusst: die Sicht fuehrt ZWEI
    # Tabellen mit VERSCHIEDENEN Spalten in EINER Datei, und eine Feldliste je
    # Datei kann das nicht trennen (dieselbe Lage wie bei der
    # Kapazitaetspflege). Sie ist von UX11 gedeckt - dort wird gerendert.
    "crossref": ("cockpit_crossref.js", "crossref"),
    # Build 605 (H14). 'handover', 'retention' und 'releases' bauen ihre
    # Tabellen von Hand und haben deshalb gar keine berechneten Spaltenanker -
    # ihre Marken sind literal und damit von SP01/SP02 gedeckt.
    "promotion": ("cockpit_promotion.js", "promotion"),
}

#: Feldnamen aus den literalen columnDefs-Eintraegen.
_FELD = re.compile(r"""field:\s*['"]([A-Za-z0-9_]+)['"]""")

#: Berechnete Anker erkennt dieser Test bewusst NICHT (siehe Kopf). Er sammelt
#: aber die dabei benutzten PRAEFIXE, damit SP04 sie pruefen kann.
_PRAEFIX_AUS_BERECHNUNG = re.compile(
    r"""(?:sicht|SICHT)\s*:\s*['"]([a-z0-9_]+)['"]"""
    r"""|var\s+SICHT\s*=\s*['"]([a-z0-9_]+)['"]""")


def _dateien():
    for name in sorted(os.listdir(STATIC)):
        if name.endswith(".js") or name.endswith(".html"):
            yield os.path.join(STATIC, name)


def _literale_marken():
    """Alle literalen Marken des Bestands: Marke -> Menge der Fundstellen."""
    gefunden = {}
    for pfad in _dateien():
        with open(pfad, encoding="utf-8") as fh:
            inhalt = fh.read()
        gefundene = _LITERAL.findall(inhalt) + _LITERAL_ABSCHNITT.findall(inhalt)
        for treffer in gefundene:
            # Ein Treffer, der auf einen Punkt endet, ist KEINE Marke,
            # sondern der literale ANFANG einer berechneten Marke
            # ("'dashboard.kachel.' + w.key"). Er gehoert nicht in diese
            # Sammlung - sonst pruefte SP03 eine Zeichenkette, die so nie im
            # DOM steht. Gefunden werden solche Anker vom vitest-Gegentest.
            if treffer.endswith("."):
                continue
            gefunden.setdefault(treffer, set()).add(os.path.basename(pfad))
    return gefunden


def _benutzte_praefixe():
    """Praefixe, die der Bestand fuer BERECHNETE Anker benutzt."""
    raus = set()
    for pfad in _dateien():
        with open(pfad, encoding="utf-8") as fh:
            inhalt = fh.read()
        for a, b in _PRAEFIX_AUS_BERECHNUNG.findall(inhalt):
            wert = a or b
            if wert:
                raus.add(wert)
    return raus


@pytest.fixture(scope="module")
def register():
    return lade_register()


# --- SP01 --------------------------------------------------------------------

def test_sp01_jede_marke_hat_einen_text(register):
    """
    Eine Marke ohne Text ist im Betrieb ein Popup, das 'Hilfe folgt' sagt.
    Das ist waehrend der Inhaltswellen richtig - deshalb bricht dieser Test
    nicht an JEDER solchen Marke, sondern nur an denen, deren Sicht bereits
    ein Kapitel hat. Fuer eine fertige Sicht ist eine Marke ohne Text ein
    Fehler, kein Zwischenstand.
    """
    bekannt = set(register.kontext_schluessel())
    fertige_praefixe = set()
    for s in register.sichten:
        fertige_praefixe.update(s.praefixe())
    fertige_praefixe.add(SHELL)

    fehlend = sorted(
        "%s (%s)" % (marke, ", ".join(sorted(quellen)))
        for marke, quellen in _literale_marken().items()
        if marke.split(".", 1)[0] in fertige_praefixe and marke not in bekannt)
    assert not fehlend, (
        "Marken in einer bereits verfassten Sicht ohne Text im Register:\n  "
        + "\n  ".join(fehlend))


# --- SP02 --------------------------------------------------------------------

def test_sp02_kein_text_ins_leere(register):
    """
    Ein Registertext, zu dem es im Browser keine Marke gibt, ist toter
    Bestand: er kostet Pflege und erscheint nie. Geprueft werden nur
    Schluessel, die LITERAL gesetzt werden koennen - die berechneten
    Spalten-/Werkzeuganker deckt der vitest-Gegentest ab.
    """
    marken = set(_literale_marken())
    # Die berechneten Bereiche sind hier ausgenommen und namentlich benannt,
    # nicht stillschweigend uebergangen (Grundregel 1).
    berechnete_bereiche = ("spalte", "werkzeug", "bedienung", "kachel")

    tot = []
    for schluessel in register.kontext_schluessel():
        teile = schluessel.split(".")
        if len(teile) >= 3 and teile[1] in berechnete_bereiche:
            continue
        if schluessel not in marken:
            tot.append(schluessel)
    assert not tot, (
        "Registertexte ohne Marke im Browser (toter Bestand): %s"
        % ", ".join(sorted(tot)))


# --- SP03 --------------------------------------------------------------------

def test_sp03_markenform():
    ungueltig = sorted(m for m in _literale_marken()
                       if not schluessel_gueltig(m))
    assert not ungueltig, (
        "Marken mit unzulaessiger Form (erwartet <praefix>.<name> bzw. "
        "<praefix>.<bereich>.<name>): %s" % ", ".join(ungueltig))


# --- SP04 / SP05 --------------------------------------------------------------

def test_sp04_jeder_benutzte_praefix_ist_zugeordnet():
    """
    Ein Praefix ohne Zuordnung heisst: die Anker dieser Tabelle koennen nie
    einem Kapitel zugeschlagen werden. Das faellt sonst erst auf, wenn jemand
    die Hilfe fuer diese Sicht schreiben will - also spaet.
    """
    benutzt = _benutzte_praefixe()
    ohne = sorted(p for p in benutzt
                  if p != SHELL and p not in ANKER_PRAEFIXE)
    assert not ohne, (
        "Ankerpraefixe ohne Zuordnung in management/help/anker_katalog.py: %s"
        % ", ".join(ohne))


def test_sp05_anker_katalog_stimmig():
    verify_praefixe()
    assert SHELL not in ANKER_PRAEFIXE


# --- SP06 --------------------------------------------------------------------

def test_sp06_marken_eindeutig():
    """
    Dieselbe Marke an zwei Stellen ist zulaessig (dasselbe Bedienelement in
    zwei Sichten), aber sie muss dann auch DASSELBE meinen. Der Test macht
    solche Faelle sichtbar, statt sie zu verbieten - er scheitert nur, wenn
    eine Marke ueber MEHR ALS ZWEI Dateien verstreut ist, denn dann ist der
    gemeinsame Sinn kaum noch zu behaupten.
    """
    verstreut = {m: q for m, q in _literale_marken().items() if len(q) > 2}
    assert not verstreut, (
        "Marken in mehr als zwei Dateien - meinen sie ueberall dasselbe? %s"
        % "; ".join("%s: %s" % (m, ", ".join(sorted(q)))
                    for m, q in sorted(verstreut.items())))


# --- SP07 --------------------------------------------------------------------

def test_sp07_jede_spalte_hat_einen_text(register):
    """
    Fuer die Sichten, deren Texte verfasst sind: jede Tabellenspalte mit Feld
    braucht einen Registertext.

    Der Feldname wird um fuehrende Unterstriche gekuerzt und kleingeschrieben -
    genau so bildet cockpit_tablekit.hilfeIdNormieren den Anker (Build 592).
    Wuerde hier anders normiert, pruefte der Test etwas anderes, als im
    Browser entsteht.
    """
    bekannt = set(register.kontext_schluessel())
    fehlend = []
    for sicht_id, (datei, praefixe) in sorted(SPALTEN_QUELLEN.items()):
        # Ein einzelner Praefix wird wie ein Tupel mit einem Element behandelt;
        # so bleibt der haeufige Fall kurz geschrieben, ohne dass der Test zwei
        # Wege kennt.
        if isinstance(praefixe, str):
            praefixe = (praefixe,)
        pfad = os.path.join(STATIC, datei)
        with open(pfad, encoding="utf-8") as fh:
            inhalt = fh.read()
        felder = sorted(set(_FELD.findall(inhalt)))
        assert felder, "%s: keine Spaltenfelder gefunden" % datei
        for praefix in praefixe:
            for feld in felder:
                schluessel = "%s.spalte.%s" % (praefix,
                                               feld.lstrip("_").lower())
                if schluessel not in bekannt:
                    fehlend.append("%s (%s, Feld %s)"
                                   % (schluessel, sicht_id, feld))
    assert not fehlend, (
        "Spalten ohne Kontexttext:\n  " + "\n  ".join(fehlend))


# --- SP08 ---------------------------------------------------------------------

def test_sp08_bildschirmzitate_stehen_wirklich_auf_dem_schirm():
    """
    Die Ausnahme von Regel H-1 gilt nur fuer WOERTLICHE Zitate.

    Geprueft wird der Kern des Zitats - der Text zwischen den deutschen
    Anfuehrungszeichen - gegen den sichtbaren Bestand. Steht er dort nicht,
    ist er kein Zitat, sondern Jargon mit Anfuehrungszeichen.
    """
    assert BILDSCHIRMZITATE, "Die Zitatliste ist leer - dann bitte auch die "\
        "Ausnahme in verify_anwendersprache entfernen."

    inhalte = []
    for pfad in _dateien():
        with open(pfad, encoding="utf-8") as fh:
            inhalte.append((os.path.basename(pfad), fh.read()))

    fehlend = []
    for zitat in BILDSCHIRMZITATE:
        kern = zitat.strip("\u201e\u201c\u201d\"'")
        assert kern, "Leeres Zitat in BILDSCHIRMZITATE"
        if not any(kern in inhalt for _name, inhalt in inhalte):
            fehlend.append(zitat)
    assert not fehlend, (
        "Bildschirmzitate ohne Entsprechung im Bestand (also kein Zitat, "
        "sondern Jargon): %s" % ", ".join(fehlend))
