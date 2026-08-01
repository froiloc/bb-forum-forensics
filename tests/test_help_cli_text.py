# =============================================================================
# tests/test_help_cli_text.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H16)
# =============================================================================
# Testsuite fuer Build 608: die Textausgabe des CLI-Katalogs und das
# Dachwerkzeug tools/hilfe.py.
#
# WAS DIESE SUITE LEISTET - UND WAS SIE NICHT KANN:
#   Sie prueft die FORM der Ausgabe (Breite, Zeichensatz, Spalten, Einzug)
#   und die RUECKGABEWERTE des Werkzeugs. Sie kann nicht pruefen, ob ein
#   Katalogtext inhaltlich stimmt - das steht im Quelltext des jeweiligen
#   Werkzeugs und ist beim Verfassen dort geprueft worden.
#
# CT01 - Umbruch: Breite eingehalten, langes Wort nicht zerschnitten
# CT02 - Spaltenzeile: erste Zeile traegt den Kopf, Folgezeilen den Einzug
# CT03 - hilfe_aufruf: aus jeder Aufrufform wird ein brauchbares '--help'
# CT04 - Nahetreffer: Teilwort und Tippfehler fuehren zum Vorschlag
# CT05 - liste: jedes Werkzeug kommt vor, jede Gruppe hat eine Ueberschrift
# CT06 - zeige: alle Pflichtangaben stehen da, auch die fehlende Tiefe
# CT07 - suche: Leerbefund sagt, WO gesucht wurde
# CT08 - REINES ASCII in der gesamten Ausgabe (Windows-Konsole)
# CT09 - keine Zeile ueber 78 Zeichen (ausser einem unteilbaren Wort)
# CT10 - Rueckgabewerte des Werkzeugs: 0 / 1 / 2
# CT11 - das Werkzeug fuehrt nichts aus und oeffnet nichts
#
# Version: v0.8.608 - Build: 608 - 2026-07-31
# =============================================================================

import os
import sys

import pytest
from dataclasses import replace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.cli_katalog import (                 # noqa: E402
    CLI_KATALOG, GRUPPEN_REIHENFOLGE, eintrag,
)
from management.help.cli_text import (                    # noqa: E402
    BREITE, art_kurz, hilfe_aufruf, liste_text, nahetreffer, spaltenzeile,
    suche_text, umbrechen, unbekannt_text, zeige_text,
)
from tools.hilfe import main, stand_text                  # noqa: E402


def _flach(text):
    """
    Alle Zeilenumbrueche und Mehrfach-Leerzeichen zu EINEM Leerzeichen.

    WOZU: Eine Zusicherung wie "der Satz X kommt vor" darf nicht daran
    scheitern, dass der Zeilenumbruch mitten durch den Satz laeuft. Der
    Umbruch ist gewollt; die Pruefung meint den Inhalt. Ohne diese
    Normierung prueft der Test die Zeilenlaenge und nicht den Text - und
    schlaegt beim naechsten laengeren Titel grundlos fehl.
    """
    return " ".join((text or "").split())


def _alle_ausgaben():
    """Jede Ausgabe, die das Werkzeug erzeugen kann - fuer die Formtests."""
    texte = [liste_text(), liste_text(nur_schreibend=True), stand_text(),
             suche_text("sicherung"), suche_text("gibtesnicht"),
             unbekannt_text("backup")]
    texte.extend(zeige_text(e) for e in CLI_KATALOG)
    return texte


# --- CT01 ---------------------------------------------------------------------

def test_ct01_umbruch():
    zeilen = umbrechen("ein zwei drei vier fuenf sechs sieben acht", 20)
    assert all(len(z) <= 20 for z in zeilen)
    assert " ".join(zeilen).split() == (
        "ein zwei drei vier fuenf sechs sieben acht".split())

    # EIN LANGES WORT WIRD NICHT ZERSCHNITTEN. Eine zerschnittene Kennung
    # oder ein zerschnittener Pfad waere unbrauchbar - dann lieber eine zu
    # lange Zeile, die man wenigstens kopieren kann.
    lang = "python -m management.migration_fleet.migration_fleet_admin"
    zeilen2 = umbrechen(lang, 20)
    assert any(len(z) > 20 for z in zeilen2)
    assert "migration_fleet_admin" in " ".join(zeilen2)

    assert umbrechen("") == ()
    assert umbrechen(None) == ()

    # Einzug: erste Zeile anders als die folgenden.
    zeilen3 = umbrechen("a b c d e f g h i j k l", 12, einzug="    ",
                        erster_einzug="> ")
    assert zeilen3[0].startswith("> ")
    assert all(z.startswith("    ") for z in zeilen3[1:])


# --- CT02 ---------------------------------------------------------------------

def test_ct02_spaltenzeile():
    """
    Der Befund aus dem ersten Lauf: eine fertig ausgerichtete Zeile durch den
    Umbruch zu schicken zerlegt sie in Woerter und setzt sie neu. Die
    Ausrichtung war dahin, und der Folgeeinzug landete auf der ERSTEN Zeile.
    """
    zeilen = spaltenzeile("LS", "rbac_admin", "Rechte-Matrix pflegen", 20)
    assert zeilen[0].startswith("  LS  rbac_admin")
    assert "Rechte-Matrix pflegen" in zeilen[0]

    lang = ("Ein sehr langer Zwecktext, der ueber mehrere Zeilen laufen muss, "
            "damit der haengende Einzug ueberhaupt sichtbar wird und der "
            "Test etwas zu pruefen hat.")
    mehr = spaltenzeile("L", "kurz", lang, 20)
    assert len(mehr) > 1
    einzug = len("  %-3s %-*s " % ("L", 20, "kurz"))
    for z in mehr[1:]:
        assert z.startswith(" " * einzug), z
        assert z[einzug] != " ", "doppelter Einzug in der Folgezeile"


# --- CT03 ---------------------------------------------------------------------

@pytest.mark.parametrize("aufruf,erwartet", [
    ("python -m management.rbac.rbac_admin <befehl>",
     "python -m management.rbac.rbac_admin --help"),
    ("python -m management.cases.cases_admin --subject-id N [...]",
     "python -m management.cases.cases_admin --help"),
    ("python tools/maintenance.py enter|exit|status",
     "python tools/maintenance.py --help"),
    ("python -m management.search.index_cli --status | --auffrischen [--voll]",
     "python -m management.search.index_cli --help"),
    ("python management/templates_db_status.py",
     "python management/templates_db_status.py --help"),
    ("python run_tests.py [--python-only|--js-only]",
     "python run_tests.py --help"),
])
def test_ct03_hilfe_aufruf(aufruf, erwartet):
    assert hilfe_aufruf(aufruf) == erwartet


def test_ct03b_jeder_katalogeintrag_ergibt_einen_brauchbaren_hilfeaufruf():
    """
    Die Probe aufs Ganze: fuer JEDEN Eintrag muss ein Aufruf herauskommen,
    der mehr ist als 'python --help'. Sonst waere der Verweis am Ende des
    Eintrags eine Sackgasse.
    """
    schwach = []
    for e in CLI_KATALOG:
        ruf = hilfe_aufruf(e.aufruf)
        if ruf in ("python --help", "--help", " --help"):
            schwach.append(e.schluessel)
        if "<" in ruf or "[" in ruf or "|" in ruf:
            schwach.append(e.schluessel + " (Platzhalter im Aufruf)")
    assert not schwach, schwach


# --- CT04 ---------------------------------------------------------------------

def test_ct04_nahetreffer():
    assert "backup_admin" in nahetreffer("backup")
    assert "rbac_admin" in nahetreffer("rbac")
    # Tippfehler
    assert "rbac_admin" in nahetreffer("rbak_admin")
    # Leerer Begriff -> keine Vorschlaege, kein Absturz
    assert nahetreffer("") == ()
    # Voellig fremder Begriff -> lieber nichts als Unsinn
    assert nahetreffer("xyzzy-quux") == ()


# --- CT05 ---------------------------------------------------------------------

def test_ct05_liste_ist_vollstaendig():
    text = liste_text()
    for e in CLI_KATALOG:
        assert e.schluessel in text, "%s fehlt in der Liste" % e.schluessel
    for g in GRUPPEN_REIHENFOLGE:
        assert g in text, "Gruppe %s fehlt" % g
    assert "%d Werkzeuge" % len(CLI_KATALOG) in text

    nur_s = liste_text(nur_schreibend=True)
    assert "AUSSCHNITT" in nur_s, (
        "Ein Ausschnitt muss als Ausschnitt benannt sein (Grundregel 1).")
    for e in CLI_KATALOG:
        if e.schreibt():
            assert e.schluessel in nur_s
    # Ein rein lesendes Werkzeug darf im Ausschnitt NICHT stehen.
    assert "escalation_admin" not in nur_s


# --- CT06 ---------------------------------------------------------------------

def test_ct06_zeige_nennt_alle_pflichtangaben():
    e = eintrag("rbac_admin")
    text = zeige_text(e)
    for pflicht in ("Aufruf", "Datei", "Art", "Unterbefehle", "Datenbanken",
                    "Betrieb", "Beleg", "Hinweis"):
        assert pflicht in text, "Abschnitt '%s' fehlt" % pflicht
    assert e.pfad in text
    assert hilfe_aufruf(e.aufruf) in text
    assert "Protokollbuch" in text

    # rbac_admin hat seit Build 609 Tiefeninhalte - also stehen sie da.
    for pflicht in ("Beispiele", "Rueckgabewerte", "Zu beachten"):
        assert pflicht in text, "Abschnitt '%s' fehlt" % pflicht
    assert "geprueft:" in text, (
        "Ein Beispiel ohne seinen Nachweis waere ein ungepruefter Aufruf.")

    # DIE FEHLENDE TIEFE WIRD BENANNT, nicht weggelassen - sonst sieht ein
    # Grundeintrag aus wie ein vollstaendiger (Grundregel 1). Geprueft an
    # einem Werkzeug, das (noch) keine hat.
    # BUILD 620: Seit H18 abgeschlossen ist, gibt es KEINEN Eintrag ohne
    # Tiefe mehr - der Test lief hier in einen Abbruch. Geprueft wird die
    # Darstellung jetzt an einem eigens gebauten Eintrag statt an einem
    # zufaellig noch unfertigen. Das ist sogar der bessere Weg: die Aussage
    # 'ein Grundeintrag sieht nicht aus wie ein vollstaendiger' haengt damit
    # nicht mehr davon ab, dass es gerade einen unfertigen gibt.
    ohne = replace(CLI_KATALOG[0], tiefe=None)
    text_ohne = zeige_text(ohne)
    assert "Ausarbeitung" in text_ohne
    assert "noch nicht erfasst" in _flach(text_ohne)


def test_ct06b_zeige_laeuft_fuer_jeden_eintrag():
    for e in CLI_KATALOG:
        text = zeige_text(e)
        assert e.titel in _flach(text)
        assert e.betrieb.split(".")[0][:30] in _flach(text)


# --- CT07 ---------------------------------------------------------------------

def test_ct07_suche_leerbefund_sagt_wo_gesucht_wurde():
    text = suche_text("voellig-unbekannter-begriff")
    assert "Kein Treffer" in text
    assert "NICHT im Quelltext" in _flach(text), (
        "Ein Leerbefund muss sagen, WORIN gesucht wurde - sonst liest er "
        "sich als 'gibt es nicht'.")
    treffer = suche_text("sicherung")
    assert "backup_admin" in treffer
    assert "von %d Werkzeugen" % len(CLI_KATALOG) in _flach(treffer)


# --- CT08 ---------------------------------------------------------------------

def test_ct08_ausgabe_ist_reines_ascii():
    """
    Die Windows-Eingabeaufforderung laeuft nicht zwingend in UTF-8. Ein
    Umlaut wird dort zu einem Kaestchen - und eine Hilfe mit Kaestchen liest
    niemand zweimal. Der ganze Katalog ist deshalb in ASCII verfasst.
    """
    for text in _alle_ausgaben():
        try:
            text.encode("ascii")
        except UnicodeEncodeError as exc:
            stelle = text[max(0, exc.start - 40):exc.start + 40]
            pytest.fail("Nicht-ASCII in der Ausgabe: %r\n...%s..."
                        % (text[exc.start:exc.end], stelle))


# --- CT09 ---------------------------------------------------------------------

def test_ct09_zeilenbreite():
    """
    Keine Zeile ueber der Breite - ausser sie besteht aus einem einzelnen,
    unteilbaren Wort (Pfad, Aufrufform). Diese Ausnahme ist gewollt und
    wird hier ausdruecklich geprueft, statt sie zu uebergehen.
    """
    for text in _alle_ausgaben():
        for zeile in text.split("\n"):
            if len(zeile) <= BREITE:
                continue
            # AUSNAHME 1: ein einzelnes, unteilbares Wort (Pfad, Kennung).
            worte = zeile.split()
            if len(worte) == 1:
                continue
            # AUSNAHME 2: ein BEISPIELAUFRUF. Eine ueber zwei Zeilen
            # verteilte Befehlszeile laesst sich nicht kopieren - und genau
            # dafuer steht sie da. Die Ausnahme ist eng gefasst: nur eine
            # eingerueckte Zeile, die mit 'python' beginnt.
            if zeile.startswith("  python ") and zeile.strip() == zeile.lstrip():
                continue
            pytest.fail("Zeile laenger als %d Zeichen und teilbar: %r"
                        % (BREITE, zeile))


# --- CT10 ---------------------------------------------------------------------

def test_ct10_rueckgabewerte(capsys):
    assert main(["liste"]) == 0
    assert "Werkzeuge" in capsys.readouterr().out

    assert main(["zeige", "rbac_admin"]) == 0
    assert "rbac_admin" in capsys.readouterr().out

    # Unbekanntes Werkzeug: 1, Meldung auf der FEHLERAUSGABE.
    assert main(["zeige", "gibt_es_nicht"]) == 1
    aus = capsys.readouterr()
    assert aus.out.strip() == ""
    assert "Unbekanntes Werkzeug" in aus.err

    # Treffer -> 0, Leerbefund -> 1 (eine Auskunft, kein Fehler).
    assert main(["suche", "sicherung"]) == 0
    capsys.readouterr()
    assert main(["suche", "voellig-unbekannt"]) == 1
    assert "Kein Treffer" in capsys.readouterr().out

    # Ohne Befehl wird nichts geraten.
    assert main([]) == 2
    assert "usage" in capsys.readouterr().out.lower()

    assert main(["stand"]) == 0
    assert "Werkzeuge insgesamt" in capsys.readouterr().out


# --- CT11 ---------------------------------------------------------------------

def test_ct11_werkzeug_oeffnet_nichts_und_fuehrt_nichts_aus():
    """
    Das Dachwerkzeug muss in JEDEM Betriebszustand gefahrlos sein - auch
    mitten in einer Migration. Deshalb: kein sqlite3, kein subprocess, kein
    os.system im Modul und in der Textschicht.

    Geprueft wird am Quelltext und nicht am Verhalten: ein Verhaltenstest
    wuerde nur zeigen, dass es bei DIESEM Aufruf nichts geoeffnet hat.
    """
    for pfad in ("tools/hilfe.py", "management/help/cli_text.py",
                 "management/help/cli_katalog.py",
                 "management/help/cli_modell.py"):
        with open(os.path.join(os.path.dirname(__file__), "..", pfad),
                  encoding="utf-8") as fh:
            quelle = fh.read()
        for verboten in ("import sqlite3", "import subprocess",
                         "os.system", "sqlite3.connect"):
            assert verboten not in quelle, (
                "%s enthaelt '%s' - das Werkzeug muss in jedem "
                "Betriebszustand gefahrlos bleiben." % (pfad, verboten))
