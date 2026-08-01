# =============================================================================
# tests/test_help_cli_epilog.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H20)
# =============================================================================
# Testsuite fuer Build 624: der Epilog der eingebauten Werkzeughilfe.
#
# WAS HIER AUF DEM SPIEL STEHT: Der Epilog ist der einzige Ort, an dem die
# gefahrenen Beispielaufrufe jemanden erreichen, der '--help' tippt statt
# 'python tools/hilfe.py zeige'. Ein Epilog, der nicht erscheint, faellt
# niemandem auf - man sieht ja eine Hilfe. Deshalb wird hier nicht nur die
# Textbildung geprueft, sondern der WIRKLICHE Aufruf: CE11 startet jedes
# verdrahtete Werkzeug in einem eigenen Prozess mit '--help' und liest nach,
# was herauskommt.
#
# CE01 - epilog_text: Beispiele mit Aufruf und Wirkung, Aufruf UNGEBROCHEN
# CE02 - ohne Beispiel steht der Grund da, unter derselben Ueberschrift
# CE03 - Rueckgabewerte erscheinen; fehlen sie im Katalog, gibt es keine
#        leere Ueberschrift
# CE04 - der Verweis nennt 'hilfe.py zeige <kennung>' und ZAEHLT die
#        Warnhinweise, die hier bewusst nicht stehen
# CE05 - schreibende Werkzeuge bekommen die ACHTUNG-Zeile, lesende nicht
# CE06 - reines ASCII, keine Zeile laenger als 78 Zeichen ausser den
#        Befehlszeilen selbst
# CE07 - unbekannte Kennung: KEINE Ausnahme, sondern ein Text, der den
#        Befund benennt
# CE08 - HilfeFormat laesst den Epilog roh und umbricht die Beschreibung
# CE09 - OHNE_EPILOG: jede Ausnahme hat eine Begruendung und eine Kennung,
#        die es im Katalog gibt
# CE10 - verify_epilog_abgedeckt gegen den BESTAND: jedes der 65 Werkzeuge
#        ist verdrahtet oder begruendet ausgenommen - kein drittes
# CE11 - GEGENPROBE AM LEBENDEN WERKZEUG: '--help' laeuft, endet mit 0 und
#        zeigt den Epilog wirklich an
# CE12 - der Epilog aendert nichts am Verhalten: dieselben Optionen wie ohne
#
# Version: v0.8.624 - Build: 624 - 2026-08-01
# =============================================================================

import argparse
import os
import re
import subprocess
import sys

import pytest

_WURZEL = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _WURZEL)

from management.help.cli_epilog import (                    # noqa: E402
    EPILOG_OHNE_ARGPARSE, OHNE_EPILOG, CliEpilogError, HilfeFormat,
    epilog, epilog_text, fehlliste_epilog, unbekannt_text,
    verify_epilog_abgedeckt,
)
from management.help.cli_katalog import (                   # noqa: E402
    CLI_KATALOG, CLI_PFADE, eintrag, fehlliste_cli_beispiele,
)
from management.help.cli_modell import (                    # noqa: E402
    CliBefehl, CliBeispiel, CliEintrag, CliTiefe,
)
from management.help.cli_text import BREITE, hilfe_aufruf   # noqa: E402

#: Der Aufruf, den die Werkzeuge im Bestand tragen. Gesucht wird der
#: WOERTLICHE Text - eine zusammengesetzte Kennung stuende nirgends im
#: Quelltext, und dann koennte diese Pruefung sie nicht sehen. Dieselbe
#: Ueberlegung wie bei den Hilfe-Marken (Regel in documents/rules-help.md).
#: Der Bindestrich gehoert in die Zeichenklasse: 'migrate-dbs' heisst so.
#: Ohne ihn haette die Suche dieses Werkzeug fuer nicht verdrahtet gehalten -
#: und CE10 haette einen Befund gemeldet, den es nicht gab.
_MUSTER = re.compile(r'cli_epilog\.epilog\(\s*"([a-z0-9_-]+)"\s*\)')


def _kunst(schluessel="probe_admin", **kw):
    vorgabe = dict(
        pfad="tools/%s.py" % schluessel,
        aufruf="python tools/%s.py --json" % schluessel,
        titel="Probe", gruppe="Diagnose",
        zweck="Ein Wegwerf-Eintrag fuer die Pruefung.",
        art="lesend", betrieb="Der Betrieb darf weiterlaufen.")
    vorgabe.update(kw)
    return CliEintrag(schluessel=schluessel, **vorgabe)


def verdrahtete_kennungen():
    """
    Die Kennungen, die im BESTAND wirklich verdrahtet sind.

    Gemessen wird der Quelltext der Werkzeuge, nicht eine gepflegte Liste -
    eine Liste koennte behaupten, ein Werkzeug sei verdrahtet, waehrend es
    das nicht ist. Dasselbe Vorgehen wie bei verify_cli_abgedeckt.
    """
    gefunden = set()
    for pfad in CLI_PFADE:
        voll = os.path.join(_WURZEL, pfad)
        if not os.path.exists(voll):
            continue
        with open(voll, encoding="utf-8", errors="replace") as fh:
            gefunden.update(_MUSTER.findall(fh.read()))
    return gefunden


# --- CE01 / CE02 --------------------------------------------------------------

def test_ce01_beispiele_mit_aufruf_und_wirkung():
    e = eintrag("storage_admin")
    assert e.hat_beispiele()
    text = epilog_text(e)
    assert text.startswith("Beispiele")
    for bsp in e.tiefe.beispiele:
        # Der Aufruf steht in EINER Zeile - eine ueber zwei Zeilen verteilte
        # Befehlszeile laesst sich nicht kopieren, und dafuer steht sie da.
        assert ("  " + bsp.aufruf) in text.split("\n"), bsp.aufruf
        assert bsp.wirkung.split()[0] in text


def test_ce02_ohne_beispiel_steht_der_grund_da():
    """
    DER EINTRAG WIRD NICHT MEHR BEIM NAMEN GENANNT. Bis Build 625 stand hier
    'backup_admin' - in Build 626 hat es Beispiele bekommen, und der Test
    fiel um. Das ist die Sorte Test, die davon lebt, dass etwas unfertig
    bleibt. Er nimmt sich den Eintrag jetzt aus der gerechneten Fehlliste und
    baut sich sonst selbst einen; damit haengt die Aussage nicht mehr am
    Fortschritt der Baustelle. (Dieselbe Berichtigung wie bei CT06 in Build
    620.)
    """
    ohne = fehlliste_cli_beispiele()
    e = eintrag(ohne[0]) if ohne else _kunst("ohne_beispiel")
    assert not e.hat_beispiele()
    text = epilog_text(e)
    assert text.startswith("Beispiele"), "die Ueberschrift fehlt"
    assert "kein Beispielaufruf" in text
    assert "gefahrlos" in text


# --- CE03 ---------------------------------------------------------------------

def test_ce03_rueckgabewerte():
    text = epilog_text(eintrag("storage_admin"))
    assert "Rueckgabewerte" in text
    assert "0 =" in text


def test_ce03b_keine_leere_ueberschrift():
    """
    Ohne Rueckgabewerte im Katalog erscheint keine Ueberschrift ohne Inhalt.
    Anders als bei den Beispielen ist das Fehlen hier keine Auskunft: ein
    Werkzeug ohne erfasste Exit-Codes sagt damit nichts ueber sich aus.
    """
    text = epilog_text(_kunst("karg"))
    assert "Rueckgabewerte" not in text


# --- CE04 / CE05 --------------------------------------------------------------

def test_ce04_verweis_zaehlt_die_warnhinweise():
    e = eintrag("storage_admin")
    text = epilog_text(e)
    assert "python tools/hilfe.py zeige storage_admin" in text
    assert str(len(e.tiefe.warnungen)) in text
    assert "Warnhinweise" in text


def test_ce04b_einzahl_wird_ausgeschrieben():
    """
    'die 1 Warnhinweise' liest sich wie ein Fehler im Text - und wer dem
    Text nicht traut, liest ihn nicht zu Ende.

    Verglichen wird auf ZUSAMMENGEZOGENEM Weissraum: der Epilog ist auf 78
    Zeichen umbrochen, die Wendung kann also ueber einen Zeilenumbruch
    laufen. Ein Vergleich auf der rohen Zeichenkette haette hier ein
    Umbruchergebnis gemessen und nicht die Formulierung.
    """
    e = _kunst("einzeln", tiefe=CliTiefe(warnungen=("Nur dieser eine.",)))
    flach = " ".join(epilog_text(e).split())
    assert "der eine Warnhinweis" in flach
    assert "die 1 Warnhinweise" not in flach


def test_ce04c_ohne_warnhinweise_wird_keine_zahl_erfunden():
    text = epilog_text(_kunst("still"))
    assert "Warnhinweis" not in text
    assert "python tools/hilfe.py zeige still" in text


def test_ce05_achtungzeile_nur_bei_schreibenden():
    schreibend = _kunst("schreiber", art="schreibend")
    lesend = _kunst("leser", art="lesend")
    gemischt = _kunst("beides", art="gemischt",
                      befehle=(CliBefehl("lauf", "schreibend", "tut was"),))
    assert "ACHTUNG" in epilog_text(schreibend)
    assert "ACHTUNG" in epilog_text(gemischt)
    assert "ACHTUNG" not in epilog_text(lesend)


def test_ce05b_jedes_schreibende_werkzeug_im_katalog_warnt():
    fehlend = [e.schluessel for e in CLI_KATALOG
               if e.schreibt() and "ACHTUNG" not in epilog_text(e)]
    assert not fehlend, "ohne Warnzeile: %s" % ", ".join(fehlend)


# --- CE06 ---------------------------------------------------------------------

def test_ce06_reines_ascii_und_78_zeichen():
    """
    Dieselben Festlegungen wie in cli_text.py (Begruendung dort im Kopf):
    die Windows-Eingabeaufforderung laeuft nicht zwingend in UTF-8, und ein
    Umlaut wird dort zu einem Kaestchen.

    AUSGENOMMEN sind die Befehlszeilen selbst. Sie werden absichtlich nicht
    umbrochen; eine zerschnittene Befehlszeile waere unbrauchbar.
    """
    zu_lang, nicht_ascii = [], []
    for e in CLI_KATALOG:
        aufrufe = {("  " + b.aufruf)
                   for b in (e.tiefe.beispiele if e.tiefe else ())}
        for zeile in epilog_text(e).split("\n"):
            if not zeile.isascii():
                nicht_ascii.append("%s: %s" % (e.schluessel, zeile[:60]))
            if len(zeile) > BREITE and zeile not in aufrufe:
                zu_lang.append("%s: %d Zeichen" % (e.schluessel, len(zeile)))
    assert not nicht_ascii, nicht_ascii[:5]
    assert not zu_lang, zu_lang[:5]


# --- CE07 ---------------------------------------------------------------------

def test_ce07_unbekannte_kennung_wirft_nicht():
    """
    Eine Ausnahme hier machte '--help' unbrauchbar - und zwar bei genau dem
    Werkzeug, dessen Katalogeintrag fehlt, also dort, wo die Hilfe am
    noetigsten waere.
    """
    text = str(epilog("gibt_es_nicht"))
    assert "gibt_es_nicht" in text
    assert "Befund" in text
    assert text == unbekannt_text("gibt_es_nicht")


# --- CE08 ---------------------------------------------------------------------

def test_ce08_hilfeformat_laesst_den_epilog_roh():
    lang = "Eine ziemlich lange Beschreibung, die umbrochen werden soll. " * 3
    p = argparse.ArgumentParser(
        prog="probe", description=lang,
        epilog=epilog("storage_admin"), formatter_class=HilfeFormat)
    aus = p.format_help()
    # Der Epilog behaelt seine Zeilenstruktur ...
    assert "\nBeispiele\n" in aus
    assert "\n  python -m management.ops.storage_admin" in aus
    # ... und die Beschreibung wird trotzdem umbrochen.
    beschreibung = aus[aus.index("probe [-h]"):aus.index("Beispiele")]
    assert lang.strip() not in beschreibung, "Beschreibung nicht umbrochen"
    assert max(len(z) for z in beschreibung.split("\n")) <= 80


def test_ce08b_ohne_hilfeformat_bleibt_argparse_wie_es_war():
    """
    Gegenprobe: Der Formatierer greift nur bei _RohText. Ein gewoehnlicher
    Epilog wird weiterhin umbrochen - HilfeFormat aendert das Verhalten von
    argparse nicht ueber den einen Fall hinaus.
    """
    p = argparse.ArgumentParser(prog="probe", formatter_class=HilfeFormat,
                                epilog="Zeile eins\nZeile zwei")
    assert "Zeile eins Zeile zwei" in p.format_help()


# --- CE09 / CE10 --------------------------------------------------------------

def test_ce09_ausnahmen_sind_begruendet_und_bekannt():
    bekannt = {e.schluessel for e in CLI_KATALOG}
    for liste in (OHNE_EPILOG, EPILOG_OHNE_ARGPARSE):
        for kennung, grund in liste.items():
            assert kennung in bekannt, kennung
            assert len(grund.strip()) > 40, (
                "%s: eine Ausnahme braucht einen Grund, der traegt" % kennung)
    # Die beiden Listen meinen Verschiedenes und duerfen sich nicht
    # ueberschneiden: 'hat keinen Epilog' und 'hat einen, aber ohne argparse'.
    assert not (set(OHNE_EPILOG) & set(EPILOG_OHNE_ARGPARSE))


def test_ce09b_ohne_argparse_ist_wirklich_ohne_argparse():
    """Gegenprobe am Bestand - sonst koennte die Liste veralten."""
    for kennung in EPILOG_OHNE_ARGPARSE:
        pfad = os.path.join(_WURZEL, eintrag(kennung).pfad)
        with open(pfad, encoding="utf-8") as fh:
            assert "ArgumentParser(" not in fh.read(), kennung


def test_ce10_jedes_werkzeug_ist_verdrahtet_oder_begruendet_ausgenommen():
    """
    DER WICHTIGSTE TEST DIESER SUITE. Er misst den BESTAND und nicht eine
    Liste: was im Quelltext nicht steht, gilt als nicht verdrahtet. Damit
    kann kein Werkzeug stillschweigend durchrutschen (Grundregel 1).
    """
    verdrahtet = verdrahtete_kennungen()
    verify_epilog_abgedeckt(verdrahtet)
    assert not fehlliste_epilog(verdrahtet)
    assert len(verdrahtet) + len(OHNE_EPILOG) == len(CLI_KATALOG)


def test_ce10b_die_pruefung_schlaegt_wirklich_an():
    """Eine Pruefung, die nie anschlaegt, belegt nichts."""
    voll = verdrahtete_kennungen()
    with pytest.raises(CliEpilogError) as exc:
        verify_epilog_abgedeckt(voll - {"storage_admin"})
    assert "storage_admin" in str(exc.value)

    with pytest.raises(CliEpilogError):
        verify_epilog_abgedeckt(voll | {"gibt_es_nicht"})

    # verdrahtet UND ausgenommen ist ein Widerspruch, kein Doppelschutz.
    with pytest.raises(CliEpilogError) as exc2:
        verify_epilog_abgedeckt(voll | {"pruefe_auslieferung"})
    assert "pruefe_auslieferung" in str(exc2.value)


# --- CE11 / CE12 --------------------------------------------------------------

def _werkzeug_aufruf(e):
    """
    Der Aufruf des WERKZEUGS SELBST mit '--help' - ohne Unterbefehl.

    BEWUSST NICHT ueber cli_text.hilfe_aufruf(): das schneidet ab dem ersten
    Platzhalter oder der ersten Option ab und laesst einen als BLOSSES WORT
    geschriebenen Unterbefehl stehen. Bei 'export_admin' ergibt es deshalb
    '... case-status-xlsx --help' - die Hilfe des Unterbefehls, nicht die
    des Werkzeugs, und dort steht der Epilog nicht. (Bei 'backup_admin'
    passiert das nicht, weil die Aufrufform dort 'plan|run|list' schreibt
    und am '|' abgeschnitten wird. Die Ungleichbehandlung ist als Vorgang
    festgehalten; sie ist kein Fehler dieses Builds.)

    Hier wird deshalb aus Modul bzw. Dateipfad gebildet, was gemeint ist.
    """
    teile = e.aufruf.split()
    if "-m" in teile:
        modul = teile[teile.index("-m") + 1]
        return ["-m", modul, "--help"]
    return [e.pfad, "--help"]


def _help_lauf(e):
    """'--help' des Werkzeugs in einem eigenen Prozess."""
    return subprocess.run([sys.executable] + _werkzeug_aufruf(e), cwd=_WURZEL,
                          capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("kennung", sorted(verdrahtete_kennungen()))
def test_ce11_help_laeuft_und_zeigt_den_epilog(kennung):
    """
    GEGENPROBE AM LEBENDEN WERKZEUG. Die Textbildung kann stimmen und der
    Epilog trotzdem nie erscheinen - etwa weil der Import fehlschlaegt oder
    der Formatierer nicht gesetzt ist. Das sieht man nur, wenn man das
    Werkzeug wirklich startet.
    """
    e = eintrag(kennung)
    r = _help_lauf(e)
    aus = r.stdout + r.stderr
    assert r.returncode == 0, aus[-1500:]
    assert "Beispiele" in aus, aus[-1500:]
    assert "python tools/hilfe.py zeige %s" % kennung in aus, aus[-1500:]


@pytest.mark.parametrize(
    "kennung", sorted(verdrahtete_kennungen() - set(EPILOG_OHNE_ARGPARSE)))
def test_ce12_der_epilog_aendert_die_optionen_nicht(kennung):
    """
    Rein additiv: der Optionsteil der Ausgabe ist derselbe wie vorher. Statt
    ihn gegen eine abgeschriebene Fassung zu halten (die veralten wuerde),
    wird geprueft, dass der Epilog HINTER dem Optionsteil steht und in ihn
    nicht hineinreicht.

    AUSGENOMMEN sind die Werkzeuge aus EPILOG_OHNE_ARGPARSE: sie haben
    keinen 'usage:'-Block, weil sie kein argparse benutzen. Sie stehen
    namentlich in einer Liste MIT GRUND und werden nicht still ausgelassen;
    CE11 prueft sie unveraendert mit.
    """
    aus = (lambda r: r.stdout + r.stderr)(_help_lauf(eintrag(kennung)))
    i_usage = aus.index("usage:")
    i_beispiele = aus.index("Beispiele")
    assert i_usage < i_beispiele
    kopf = aus[i_usage:i_beispiele]
    assert "-h, --help" in kopf
    assert "hilfe.py zeige" not in kopf
