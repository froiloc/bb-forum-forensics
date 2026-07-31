# =============================================================================
# tests/test_pruefe_auslieferung.py
# IT-Forensisches Ermittlungswerkzeug
# =============================================================================
# Testsuite fuer Build 597: tools/pruefe_auslieferung.py.
#
# ANLASS: Am 2026-07-31 wurden zwei Auslieferungsarchive EINE EBENE ZU TIEF
# entpackt. Der Regressionslauf meldete daraufhin einen scheinbaren Codefehler
# ("Kacheln ohne Text im Register"), obwohl am Code nichts fehlte - die neuen
# Texte lagen nur woanders. Die vorhandene MD5-Pruefung konnte das nicht
# fangen: Bei RELATIVEN Pfaden ist ein gleichmaessig verschobener Baum in sich
# stimmig. Der Fehler ist ausschliesslich von der Wurzel aus sichtbar.
#
# PA01 - ist_wurzel: nur wenn ALLE Merkmale nebeneinander liegen
# PA02 - finde_wurzel sucht AUFWAERTS; eine tiefer liegende Kopie gewinnt nicht
# PA03 - DER KERNFALL: ein zweiter vollstaendiger Bestand unterhalb der Wurzel
#        wird als Befund gemeldet, nicht als "alles in Ordnung"
# PA04 - Pruefsummen: Gutfall, Abweichung, fehlende Datei
# PA05 - kaputte Zeile in der Liste -> Fehler, nicht stilles Ueberspringen
# PA06 - leere Liste -> Fehler (eine Liste ohne Eintraege prueft nichts)
# PA07 - ohne Argument wird GENAU die Liste zum Build aus build.json geprueft
# PA08 - falsches Arbeitsverzeichnis -> Exit 2 mit benanntem Grund
#
# Version: v0.8.597 - Build: 597 - 2026-07-31
# =============================================================================

import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.pruefe_auslieferung import (                 # noqa: E402
    AuslieferungsFehler, finde_wurzel, ist_wurzel, lies_liste, main,
    md5_datei, pruefe,
)


def _wurzel(tmp_path, build=597):
    """Ein Miniatur-Bestand mit den drei Wurzelmerkmalen."""
    w = tmp_path / "aiw"
    (w / "management" / "help").mkdir(parents=True)
    (w / "tools").mkdir()
    (w / "run_tests.py").write_text("# leer\n", encoding="utf-8")
    (w / "build.json").write_text(
        json.dumps({"build": build, "version": "0.8.%d" % build}),
        encoding="utf-8")
    return w


def _md5(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _liste(w, name, eintraege):
    zeilen = ["%s  %s" % (summe, rel) for summe, rel in eintraege]
    (w / name).write_text("\n".join(zeilen) + "\n", encoding="utf-8")
    return w / name


# --- PA01 / PA02 --------------------------------------------------------------

def test_pa01_ist_wurzel(tmp_path):
    w = _wurzel(tmp_path)
    assert ist_wurzel(w) is True
    # Ein einzelnes Merkmal genuegt NICHT - 'management/' gibt es auch eine
    # Ebene tiefer, wenn falsch entpackt wurde.
    halb = tmp_path / "halb"
    (halb / "management").mkdir(parents=True)
    assert ist_wurzel(halb) is False


def test_pa02_finde_wurzel_sucht_aufwaerts(tmp_path):
    w = _wurzel(tmp_path)
    tief = w / "management" / "help"
    assert finde_wurzel(tief) == w.resolve()
    # Ausserhalb jedes Bestands -> None
    assert finde_wurzel(tmp_path.parent.parent) in (None, )


# --- PA03: der Kernfall -------------------------------------------------------

def test_pa03_zweiter_bestand_unterhalb_wird_gemeldet(tmp_path, capsys, monkeypatch):
    """
    Die Lage vom 2026-07-31, nachgestellt: unterhalb der Wurzel liegt ein
    kompletter zweiter Bestand, weil ein Archiv eine Ebene zu tief entpackt
    wurde. Das MUSS auffallen - in sich ist der verschobene Baum stimmig.
    """
    w = _wurzel(tmp_path)
    (w / "management" / "run_tests.py").write_text("#", encoding="utf-8")
    (w / "management" / "build.json").write_text("{}", encoding="utf-8")
    (w / "management" / "management").mkdir()

    monkeypatch.chdir(w)
    code = main([])
    assert code == 1
    fehler = capsys.readouterr().err
    assert "ZWEITER vollstaendiger Bestand" in fehler
    assert "zu tief entpacktes Archiv" in fehler


# --- PA04 / PA05 / PA06 -------------------------------------------------------

def test_pa04_pruefsummen(tmp_path):
    w = _wurzel(tmp_path)
    (w / "management" / "help" / "a.py").write_text("A\n", encoding="utf-8")
    (w / "management" / "help" / "b.py").write_text("B\n", encoding="utf-8")
    liste = _liste(w, "MD5SUMS_Build597.txt", [
        (_md5("A\n"), "management/help/a.py"),
        (_md5("XX"), "management/help/b.py"),      # Abweichung
        (_md5("C\n"), "management/help/c.py"),     # fehlt
    ])
    anzahl, ok, befunde = pruefe(w, liste)
    assert (anzahl, ok) == (3, 1)
    assert any(b.startswith("ABWEICHUNG") and "b.py" in b for b in befunde)
    assert any(b.startswith("FEHLT") and "c.py" in b for b in befunde)
    # md5_datei rechnet dasselbe wie die Vorlage
    assert md5_datei(w / "management" / "help" / "a.py") == _md5("A\n")


def test_pa05_kaputte_zeile_ist_ein_fehler(tmp_path):
    w = _wurzel(tmp_path)
    (w / "MD5SUMS_Build597.txt").write_text(
        "%s  a.py\nirgendwas ohne Pruefsumme\n" % _md5("A"), encoding="utf-8")
    with pytest.raises(AuslieferungsFehler) as exc:
        lies_liste(w / "MD5SUMS_Build597.txt")
    assert "Zeile 2" in str(exc.value)


def test_pa06_leere_liste_ist_ein_fehler(tmp_path):
    w = _wurzel(tmp_path)
    (w / "MD5SUMS_Build597.txt").write_text("# nur ein Kommentar\n",
                                            encoding="utf-8")
    with pytest.raises(AuslieferungsFehler):
        lies_liste(w / "MD5SUMS_Build597.txt")


# --- PA07 / PA08 --------------------------------------------------------------

def test_pa07_ohne_argument_genau_der_aktuelle_build(tmp_path, capsys,
                                                     monkeypatch):
    w = _wurzel(tmp_path, build=597)
    (w / "management" / "help" / "a.py").write_text("A\n", encoding="utf-8")
    _liste(w, "MD5SUMS_Build597.txt", [(_md5("A\n"), "management/help/a.py")])
    # Eine AELTERE Liste, die heute zwangslaeufig abweicht - sie darf ohne
    # Argument NICHT mitgeprueft werden, sonst geht der echte Befund im
    # Rauschen unter.
    _liste(w, "MD5SUMS_Build590.txt", [(_md5("alt"), "management/help/a.py")])

    monkeypatch.chdir(w)
    assert main([]) == 0
    ausgabe = capsys.readouterr().out
    assert "MD5SUMS_Build597.txt" in ausgabe
    assert "MD5SUMS_Build590.txt" not in ausgabe

    # ... mit --alle dagegen schon, samt Hinweis auf die Natur der Sache.
    assert main(["--alle"]) == 1
    ausgabe2 = capsys.readouterr().out
    assert "MD5SUMS_Build590.txt" in ausgabe2
    assert "--alle prueft auch ALTE Listen" in ausgabe2


def test_pa08_falsches_verzeichnis(tmp_path, capsys, monkeypatch):
    leer = tmp_path / "irgendwo"
    leer.mkdir()
    monkeypatch.chdir(leer)
    assert main([]) == 2
    fehler = capsys.readouterr().err
    assert "Kein Wurzelverzeichnis" in fehler
    assert "eine Ebene zu tief entpackt" in fehler
