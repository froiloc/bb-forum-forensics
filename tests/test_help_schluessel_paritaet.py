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
from management.help.modell import schluessel_gueltig   # noqa: E402

STATIC = os.path.join(os.path.dirname(__file__), "..",
                      "management", "server", "static")

#: Literale Marken: data-hilfe-id="..." bzw. 'data-hilfe-id', '...'
_LITERAL = re.compile(r"""data-hilfe-id["']?\s*[=,]\s*["']([a-z0-9_.]+)["']""")

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
        for treffer in _LITERAL.findall(inhalt):
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
    berechnete_bereiche = ("spalte", "werkzeug", "bedienung")

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
