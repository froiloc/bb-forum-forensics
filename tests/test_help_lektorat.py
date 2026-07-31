# =============================================================================
# tests/test_help_lektorat.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H8a)
# =============================================================================
# Testsuite fuer Build 596: die Lektoratsfassung (tools/hilfe_lektorat.py).
#
# WAS HIER WIRKLICH AUF DEM SPIEL STEHT: Die Lektoratsfassung ist die
# Grundlage der Vier-Augen-Lesung (Entscheidung F6). Ein Text, der es NICHT
# in dieses Dokument schafft, wird auch nicht gegengelesen - und geht damit
# ungeprueft in den Betrieb. Deshalb ist der wichtigste Test hier nicht die
# Formatierung, sondern die VOLLZAEHLIGKEIT (LK03/LK04).
#
# LK01 - erzeugt wohlgeformtes, eigenstaendiges HTML (kein externes CSS/JS)
# LK02 - Kapitel erscheinen in KATALOGREIHENFOLGE, nicht in Registerfolge
# LK03 - JEDER Kapiteltext (Absaetze und Listenpunkte) steht im Dokument
# LK04 - JEDER Popup-Text steht im Dokument, samt Schluessel - auch die der
#        Shell, die zu keiner Sicht gehoeren
# LK05 - kein Rechtefilter: auch Kapitel ohne gemeinsames Recht erscheinen
# LK06 - Escaping: spitze Klammern aus Registertexten landen escaped
# LK07 - --nur grenzt ein; die Shell entfaellt dann (sie gehoert zu keiner
#        gewaehlten Sicht)
# LK08 - unbekannte Sicht in --nur -> Exit 1 MIT Nennung, keine leere Fassung
# LK09 - die Fusszeile nennt die noch offenen Sichten namentlich
# LK10 - die Einstufung steht im Kopf UND in der Fusszeile
# LK12 - Build 597: JEDES Kapitel nennt die Datei, in der sein Text steht
#        (mc 2026-07-31) - und der Shell-Block ebenso
# LK13 - quelle_je_sicht() ist vollzaehlig: kein Kapitel ohne Pfadangabe
#
# Version: v0.8.596 - Build: 596 - 2026-07-31
# =============================================================================

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.inhalt import lade_register            # noqa: E402
from management.help.modell import (                        # noqa: E402
    Abschnitt, HilfeRegister, Kontexthilfe, Sichthilfe,
    PFLICHT_ANKER, PFLICHT_TITEL,
)
from management.help.pruefung import fehlliste_sichten      # noqa: E402
from management.help.sicht_katalog import SICHT_KATALOG     # noqa: E402
from management.help.inhalt import (                        # noqa: E402
    SHELL_QUELLE, quelle_je_sicht,
)
from tools.hilfe_lektorat import (                          # noqa: E402
    baue_lektoratsfassung, main,
)


def _kapitel(sicht_id, zusatz=(), kontext=()):
    return Sichthilfe(
        sicht=sicht_id, titel="Kapitel %s" % sicht_id,
        recht_klartext="Recht: beispiel.view",
        abschnitte=tuple(Abschnitt(a, PFLICHT_TITEL[a], ("Text %s." % a,))
                         for a in PFLICHT_ANKER) + tuple(zusatz),
        kontext=tuple(kontext), stand=596)


@pytest.fixture(scope="module")
def echt():
    """Das Auslieferungsregister - hier wird die WIRKLICHE Fassung geprueft."""
    reg = lade_register()
    return reg, baue_lektoratsfassung(reg, build=596, datum="2026-07-31")


# --- LK01 / LK02 --------------------------------------------------------------

def test_lk01_eigenstaendiges_html(echt):
    _, doc = echt
    assert doc.startswith("<!DOCTYPE html>")
    assert doc.rstrip().endswith("</html>")
    # Eigenstaendig: das Dokument wandert per Datei und muss ueberall lesbar
    # sein - auch ohne den Server, von dem es handelt.
    assert "<style>" in doc
    assert 'rel="stylesheet"' not in doc
    assert "<script" not in doc


def test_lk02_katalogreihenfolge(echt):
    reg, doc = echt
    katalogfolge = [e.id for e in SICHT_KATALOG if reg.get(e.id) is not None]
    stellen = [doc.index('<article id="%s">' % s) for s in katalogfolge]
    assert stellen == sorted(stellen), (
        "Die Kapitel stehen nicht in Katalogreihenfolge - wer nach dem Lesen "
        "etwas wiederfinden will, sucht es dort, wo es auch im Werkzeug steht.")


# --- LK03 / LK04: Vollzaehligkeit ---------------------------------------------

def test_lk03_jeder_kapiteltext_steht_drin(echt):
    """
    Ein Absatz, der es nicht in die Lektoratsfassung schafft, wird nicht
    gegengelesen. Deshalb wird hier JEDER geprueft, nicht eine Stichprobe.
    """
    import html as _h
    reg, doc = echt
    fehlend = []
    for s in reg.sichten:
        for a in s.abschnitte:
            for text in list(a.absaetze) + list(a.liste) + [a.titel]:
                if _h.escape(text, quote=True) not in doc:
                    fehlend.append("%s#%s: %s" % (s.sicht, a.anker, text[:60]))
        if _h.escape(s.recht_klartext, quote=True) not in doc:
            fehlend.append("%s: Rechtelage" % s.sicht)
    assert not fehlend, "Texte fehlen in der Lektoratsfassung:\n  " \
        + "\n  ".join(fehlend)


def test_lk04_jeder_popup_text_steht_drin(echt):
    import html as _h
    reg, doc = echt
    fehlend = []
    for k in reg.alle_kontexthilfen():
        if _h.escape(k.schluessel, quote=True) not in doc:
            fehlend.append("Schluessel %s" % k.schluessel)
        if _h.escape(k.text, quote=True) not in doc:
            fehlend.append("Text zu %s" % k.schluessel)
    assert not fehlend, "Popup-Texte fehlen:\n  " + "\n  ".join(fehlend)
    # Die Shell-Texte gehoeren zu keiner Sicht und haetten deshalb leicht
    # herausfallen koennen - sie bekommen einen eigenen Block.
    assert '<article id="shell">' in doc
    assert reg.shell, "Der Shell-Bestand ist leer - dann prueft LK04 nichts."


# --- LK05 / LK06 --------------------------------------------------------------

def test_lk05_kein_rechtefilter():
    """
    Zwei Kapitel mit UNVEREINBAREN Rechten. Unter /help saehe sie niemand
    gemeinsam; in der Lektoratsfassung muessen beide stehen.
    """
    reg = HilfeRegister((_kapitel("dashboard"), _kapitel("policy")))
    doc = baue_lektoratsfassung(reg)
    assert '<article id="dashboard">' in doc
    assert '<article id="policy">' in doc


def test_lk06_escaping():
    boese = 'Ein <script>alert("x")</script> & mehr'
    reg = HilfeRegister((
        _kapitel("dashboard",
                 zusatz=[Abschnitt("probe", "Probe", (boese,))],
                 kontext=[Kontexthilfe("dashboard.x", "T", boese)]),))
    doc = baue_lektoratsfassung(reg)
    assert "<script>alert" not in doc
    assert "&lt;script&gt;" in doc


# --- LK07 / LK08 --------------------------------------------------------------

def test_lk07_nur_grenzt_ein():
    reg = HilfeRegister(
        sichten=(_kapitel("dashboard"), _kapitel("faelle")),
        shell=(Kontexthilfe("shell.x", "Shell", "Ein Shell-Text."),))
    doc = baue_lektoratsfassung(reg, nur=["faelle"])
    assert '<article id="faelle">' in doc
    assert '<article id="dashboard">' not in doc
    # Bei einer Einschraenkung entfaellt der Shell-Block: er gehoert zu keiner
    # der gewaehlten Sichten.
    assert '<article id="shell">' not in doc


def test_lk08_unbekannte_sicht_bricht_ab(tmp_path, capsys):
    ziel = tmp_path / "x.html"
    code = main(["--nur", "gibtsnicht", "--ziel", str(ziel)])
    assert code == 1
    ausgabe = capsys.readouterr()
    assert "gibtsnicht" in ausgabe.err
    # Es entsteht KEINE leere Fassung, die wie ein Ergebnis aussieht.
    assert not ziel.exists()


# --- LK09 / LK10 --------------------------------------------------------------

def test_lk09_offene_sichten_werden_genannt(echt):
    reg, doc = echt
    offen = fehlliste_sichten(reg)
    if offen:
        assert "Noch ohne Kapitel" in doc
        for sicht_id in offen:
            assert sicht_id in doc, (
                "Die offene Sicht '%s' wird in der Fusszeile nicht genannt - "
                "sie fiele damit still aus der Abnahme." % sicht_id)
    else:
        assert "Alle Sichten haben ein Kapitel." in doc


def test_lk10_einstufung_im_kopf_und_fuss(echt):
    _, doc = echt
    assert "VS-NfD" in doc
    assert "VS-NUR FÜR DEN DIENSTGEBRAUCH" in doc
    assert "Regel H-0" in doc


def test_lk11_schreibt_die_datei(tmp_path, capsys):
    ziel = tmp_path / "lektorat.html"
    assert main(["--ziel", str(ziel)]) == 0
    assert ziel.exists()
    inhalt = ziel.read_text(encoding="utf-8")
    assert inhalt.startswith("<!DOCTYPE html>")
    assert "Geschrieben:" in capsys.readouterr().out


# --- LK12 / LK13 (Build 597) --------------------------------------------------

def test_lk12_jedes_kapitel_nennt_seine_datei(echt):
    """
    Ohne diese Angabe muesste beim Gegenlesen jede Formulierung erst in vier
    Dateien gesucht werden. Genau das soll die Lektoratsfassung ersparen.
    """
    reg, doc = echt
    quellen = quelle_je_sicht()
    for s in reg.sichten:
        pfad = quellen.get(s.sicht)
        assert pfad, "Kapitel '%s' ohne Pfadangabe" % s.sicht
        # Der Pfad muss im Dokument NEBEN dem Kapitel stehen.
        beginn = doc.index('<article id="%s">' % s.sicht)
        ende = doc.index("</article>", beginn)
        assert pfad in doc[beginn:ende], (
            "Kapitel '%s' nennt seine Datei '%s' nicht." % (s.sicht, pfad))
    # ... und der Shell-Block nennt seine.
    beginn = doc.index('<article id="shell">')
    ende = doc.index("</article>", beginn)
    assert SHELL_QUELLE in doc[beginn:ende]


def test_lk13_pfadangabe_ist_vollzaehlig(echt):
    reg, _ = echt
    quellen = quelle_je_sicht()
    ohne = sorted(set(reg.ids()) - set(quellen))
    assert not ohne, "Kapitel ohne Eintrag in quelle_je_sicht(): %s" % ohne
    # Umgekehrt kein Eintrag ins Leere.
    waisen = sorted(set(quellen) - set(reg.ids()))
    assert not waisen, "Pfadangabe zu Kapiteln, die es nicht gibt: %s" % waisen
