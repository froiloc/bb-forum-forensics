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
# Build 623 (H19 Nachtrag), am Ende der Datei - der Betriebsteil:
# LK14 - JEDES Werkzeug des Katalogs hat ein Kapitel in der Vorlage
# LK15 - jeder Beispielaufruf, Nachweis, Rueckgabewert und Warnhinweis steht
#        darin (was fehlt, wird nicht gegengelesen)
# LK16 - kein Rechtefilter, mit Gegenprobe
# LK17 - Kopf, Vorspann und Fusszeile sagen, was beim Gegenlesen zu
#        beachten ist - hier gilt Regel H-2 und nicht H-1
# LK18 - ohne Betriebsteil ist die Fassung ZEICHENGLEICH die von Build 622
# LK19 - --nur-betrieb / --ohne-betrieb / --nur; Widersprueche -> Exit 2
# LK20 - die Meldung zaehlt, was wirklich in der Datei steht
# LK21 - das Verzeichnis fuehrt jedes Betriebskapitel
#
# Version: v0.8.623 - Build: 623 - 2026-08-01
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


# =============================================================================
# Build 623 (H19 Nachtrag) - DIE BETRIEBSKAPITEL IN DER LESEVORLAGE.
#
# WORUM ES GEHT: Mit Build 622 sind die Werkzeugkapitel in die Vollhilfe gekommen, die
# dieses Werkzeug nicht kannte. Sie waren ausgeliefert, aber nicht
# gegengelesen - genau der Fehler, gegen den es die Lektoratsfassung gibt.
# Der wichtigste Test ist deshalb auch hier die VOLLZAEHLIGKEIT (LK14/LK15).
#
# LK14 - JEDES Werkzeug des Katalogs hat ein Kapitel in der Vorlage
# LK15 - jeder Beispielaufruf, jeder Pruefnachweis, jede Warnung und jeder
#        Rueckgabewert steht darin - was fehlt, wird nicht gegengelesen
# LK16 - KEIN Rechtefilter: der Betriebsteil ist ohne 'ops.view' aufrufbar,
#        weil die Sperre fuer /help gilt und nicht fuer die Redaktion
# LK17 - der Kopf nennt den Adressatenwechsel; die Fusszeile nennt die
#        Werkzeuge ohne Beispiellauf namentlich
# LK18 - ohne Betriebsteil ist die Fassung inhaltlich die von Build 622
# LK19 - --nur-betrieb liefert NUR die Werkzeuge, --ohne-betrieb keines;
#        widerspruechliche Schalter werden zurueckgewiesen (Exit 2)
# LK20 - die Meldung zaehlt, was WIRKLICH in der Datei steht (Befund 602,
#        fuer den Betriebsteil nachgezogen)
# LK21 - das Verzeichnis fuehrt jedes Betriebskapitel und verweist richtig
# =============================================================================

from management.help import cli_html as _cli_html            # noqa: E402
from management.help.cli_katalog import CLI_KATALOG          # noqa: E402
from tools.hilfe_lektorat import (                           # noqa: E402
    CLI_QUELLE, betriebsteil_fuer_lektorat,
)


def _vorlage_mit_betrieb():
    return baue_lektoratsfassung(lade_register(), build=623, datum="2026-08-01",
                                 betrieb=betriebsteil_fuer_lektorat())


def test_lk14_jedes_werkzeug_hat_ein_kapitel_in_der_vorlage():
    doc = _vorlage_mit_betrieb()
    fehlend = [e.schluessel for e in CLI_KATALOG
               if 'id="cli-%s"' % e.schluessel not in doc]
    assert not fehlend, ("nicht gegenlesbar, weil nicht in der Vorlage: %s"
                         % ", ".join(fehlend))


def test_lk15_jeder_tiefeninhalt_steht_in_der_vorlage():
    """
    Beispiele, Nachweise, Rueckgabewerte und Warnungen sind der Teil des
    Katalogs, bei dem ein Fehler am teuersten ist - er kostet die Zeit
    dessen, der dem Beispiel folgt. Genau er muss gegengelesen werden.
    """
    import html as _html

    doc = _vorlage_mit_betrieb()
    fehlend = []
    for e in CLI_KATALOG:
        if e.tiefe is None:
            continue
        for bsp in e.tiefe.beispiele:
            for wert in (bsp.aufruf, bsp.wirkung, bsp.geprueft):
                if _html.escape(wert, quote=True) not in doc:
                    fehlend.append("%s/beispiel" % e.schluessel)
        for _, bedeutung in e.tiefe.exit_codes:
            if _html.escape(bedeutung, quote=True) not in doc:
                fehlend.append("%s/rueckgabe" % e.schluessel)
        for w in e.tiefe.warnungen:
            if _html.escape(w, quote=True) not in doc:
                fehlend.append("%s/warnung" % e.schluessel)
    assert not fehlend, "fehlt: %s" % ", ".join(sorted(set(fehlend)))


def test_lk16_kein_rechtefilter_in_der_lesevorlage():
    """
    Die Sperre (E1) gilt fuer die ausgelieferte Hilfe, nicht fuer die
    Redaktion des Bestands - so wie diese Fassung auch Sichtkapitel zeigt,
    die eine lesende Person im Betrieb nicht saehe (LK05).
    """
    teil = betriebsteil_fuer_lektorat()
    assert not teil.leer()
    assert len(teil.eintraege()) == len(CLI_KATALOG)
    # ... und die Gegenprobe: ohne das Recht liefert dieselbe Funktion in
    # cli_html nichts. Der Unterschied ist also nicht zufaellig.
    assert _cli_html.baue_betriebsgliederung(("dashboard.view",)).leer()


def test_lk16b_abschaltbar():
    assert betriebsteil_fuer_lektorat(einbeziehen=False).leer()


def test_lk17_kopf_und_fusszeile_sagen_das_noetige():
    doc = _vorlage_mit_betrieb()
    kopf = doc[:doc.index('<nav class="toc"')]
    assert "Betriebskapitel" in kopf
    assert "H-2" in kopf and "H-1" in kopf
    assert CLI_QUELLE in kopf

    fuss = doc[doc.rindex("<footer"):]
    ohne = betriebsteil_fuer_lektorat().ohne_beispiele()
    assert "ohne gefahrenen Beispielaufruf" in fuss
    for schluessel in ohne:
        assert schluessel in fuss, schluessel


def test_lk17b_lesehinweis_nennt_was_zu_pruefen_ist():
    """
    Regel H-1 gilt hier nicht - wer das beim Gegenlesen nicht weiss,
    'korrigiert' die Dateinamen weg. Der Hinweis steht deshalb unmittelbar
    vor dem ersten Betriebskapitel und nicht nur im Kopf.
    """
    doc = _vorlage_mit_betrieb()
    vorspann = doc[doc.index('<div class="betriebsvorspann">'):
                   doc.index('id="cli-vorspann"')]
    assert "Regel H-1" in vorspann
    assert "schreibend" in vorspann
    assert "Prüfnachweis" in vorspann


def test_lk18_ohne_betriebsteil_ist_die_fassung_die_alte():
    """
    ZEICHENGLEICH mit Build 622 - auch im Stylesheet. Die Regeln fuer den
    Betriebsteil stehen in einem eigenen Block, der nur mitkommt, wenn auch
    Kapitel da sind. Sonst waere selbst eine Fassung ohne Betriebsteil an
    den Klassennamen im CSS als 'nach 623' erkennbar gewesen, und dieser
    Vergleich haette nur noch halb getragen.
    """
    reg = lade_register()
    alt = baue_lektoratsfassung(reg, build=623, datum="2026-08-01")
    neu = baue_lektoratsfassung(reg, build=623, datum="2026-08-01",
                                betrieb=betriebsteil_fuer_lektorat(False))
    assert alt == neu
    assert "Betriebskapitel" not in alt
    assert "cli-" not in alt
    assert "aiw-h-" not in alt


def test_lk19_schalter(tmp_path, capsys):
    ziel = tmp_path / "l.html"

    assert main(["--nur-betrieb", "--ziel", str(ziel)]) == 0
    doc = ziel.read_text(encoding="utf-8")
    assert 'id="cli-backup_admin"' in doc
    assert 'id="dashboard"' not in doc

    assert main(["--ohne-betrieb", "--ziel", str(ziel)]) == 0
    doc = ziel.read_text(encoding="utf-8")
    assert 'id="dashboard"' in doc
    assert 'id="cli-backup_admin"' not in doc

    # --nur meint die Sichten; der Betriebsteil entfaellt dann - genau wie
    # die Shell-Texte heute schon (LK07).
    assert main(["--nur", "faelle", "--ziel", str(ziel)]) == 0
    assert "cli-" not in ziel.read_text(encoding="utf-8")


def test_lk19b_widerspruechliche_schalter_werden_zurueckgewiesen(tmp_path):
    """
    Nicht ausgelegt, sondern zurueckgewiesen: eine Vorrangregel muesste man
    sich merken, und wer sich vertut, bekaeme wortlos eine Fassung, die er
    nicht wollte.
    """
    ziel = str(tmp_path / "l.html")
    assert main(["--nur-betrieb", "--ohne-betrieb", "--ziel", ziel]) == 2
    assert main(["--nur-betrieb", "--nur", "faelle", "--ziel", ziel]) == 2


def test_lk20_meldung_zaehlt_was_in_der_datei_steht(tmp_path, capsys):
    ziel = tmp_path / "l.html"

    main(["--ziel", str(ziel)])
    zeile = capsys.readouterr().out
    assert "%d Betriebskapitel" % len(CLI_KATALOG) in zeile

    main(["--ohne-betrieb", "--ziel", str(ziel)])
    assert "0 Betriebskapitel" in capsys.readouterr().out

    main(["--nur-betrieb", "--ziel", str(ziel)])
    aus = capsys.readouterr().out
    assert "0 Kapitel" in aus
    assert "%d Betriebskapitel" % len(CLI_KATALOG) in aus


def test_lk21_verzeichnis_fuehrt_jedes_betriebskapitel():
    doc = _vorlage_mit_betrieb()
    toc = doc[doc.index('<nav class="toc"'):doc.index("</nav>")]
    for e in CLI_KATALOG:
        marke = _cli_html.kapitel_id(e.schluessel)
        assert 'href="#%s"' % marke in toc, e.schluessel
        assert 'id="%s"' % marke in doc, e.schluessel
