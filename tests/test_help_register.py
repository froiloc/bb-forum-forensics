# =============================================================================
# tests/test_help_register.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H1)
# =============================================================================
# Testsuite fuer Build 588: Hilfe-Register (Modell + Pruefungen + Fehlliste).
#
# Der Bauplan H1 verlangt ausdruecklich Gut- UND Schlechtfaelle: eine
# Vollstaendigkeitspruefung, die nie anschlaegt, ist keine Pruefung. Jeder
# Schlechtfall unten ist ein Fehler, der in den Inhaltswellen realistisch
# passieren kann.
#
# HR01 - Auslieferungsregister laedt; Fehlliste = alle Sichten ohne Kapitel
# HR02 - verify_sichten_abgedeckt: Gutfall mit vollstaendiger Fehlliste
# HR03 - Sicht weder abgedeckt noch auf der Fehlliste -> Fehler benennt sie
# HR04 - Kapitel ohne Sicht im Katalog (Waise) -> Fehler
# HR05 - Fehlliste nennt eine Sicht, die laengst ein Kapitel hat -> Fehler
# HR06 - Fehlliste nennt eine unbekannte Sicht -> Fehler
# HR07 - Fehlliste darf nur schrumpfen (Monotonie), Wachstum -> Fehler
# HR08 - Verweis auf fehlendes Kapitel / fehlenden Anker -> Fehler
# HR09 - Pflichtgliederung fehlt -> Fehler bereits beim Bauen (ModellError)
# HR10 - Kontextschluessel: Form, Sichtbindung, Doppelvergabe
# HR11 - Abschnitt/Anker: Formregeln, leerer Abschnitt verboten
# HR12 - Regel H-0: Verbotsmuster schlagen an, fiktive Beispiele nicht
# HR13 - eingecheckter Fehllisten-Stand deckt sich mit dem echten Bestand
# HR14 - verify_alles auf dem Auslieferungsbestand ist gruen
#
# Build 591 (H4) ergaenzt die Shell-Kontexthilfe:
# HR15 - der Auslieferungsbestand fuehrt Shell-Texte, alle mit Praefix 'shell.'
# HR16 - ein Shell-Schluessel ohne den Praefix bricht ab
# HR17 - ein Sichtkapitel darf den reservierten Praefix nicht benutzen
# HR18 - Shell-Verweise werden mitgeprueft (kein Verweis ins Leere)
# HR19 - Shell-Texte unterliegen Regel H-0 wie alle anderen
#
# Version: v0.8.588 - Build: 588 - 2026-07-31
# =============================================================================

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from management.help.modell import (                    # noqa: E402
    Abschnitt, HilfeRegister, Kontexthilfe, ModellError, Sichthilfe,
    PFLICHT_ANKER, PFLICHT_TITEL,
)
from management.help import pruefung                    # noqa: E402
from management.help.pruefung import (                  # noqa: E402
    HilfeFehllisteError, HilfeInhaltError, HilfePruefungError,
    HilfeUnvollstaendigError, HilfeVerweisError, fehlliste_sichten,
    verify_alles, verify_fallinhaltsfrei, verify_fehlliste_monoton,
    verify_gliederung, verify_kontextschluessel, verify_shell_kontext,
    verify_sichten_abgedeckt, verify_verweise,
)
from management.help.inhalt.shell import (              # noqa: E402
    SHELL_KONTEXT, SHELL_PRAEFIX,
)
from management.help.inhalt import lade_register        # noqa: E402
from management.help.sicht_katalog import SICHT_IDS     # noqa: E402

STAND_DATEI = os.path.join(os.path.dirname(__file__),
                           "hilfe_fehlliste_stand.json")


# --- Bauhilfen fuer Probe-Register -------------------------------------------

def _pflichtabschnitte(zusatz=()):
    """Die sechs Pflichtabschnitte mit Fuelltext plus optionale Zusaetze."""
    basis = [Abschnitt(a, PFLICHT_TITEL[a], ("Fuelltext fuer den Test.",))
             for a in PFLICHT_ANKER]
    return tuple(basis) + tuple(zusatz)


def _kapitel(sicht_id, kontext=(), zusatz=()):
    return Sichthilfe(
        sicht=sicht_id, titel="Kapitel %s" % sicht_id,
        recht_klartext="Recht: beispiel.view",
        abschnitte=_pflichtabschnitte(zusatz), kontext=tuple(kontext),
        stand=588)


def _stand():
    with open(STAND_DATEI, encoding="utf-8") as fh:
        return json.load(fh)


# --- HR01 --------------------------------------------------------------------

def test_hr01_auslieferungsregister_laedt():
    reg = lade_register()
    fehlt = fehlliste_sichten(reg)
    # In H1 ist der Bestand leer - und die Fehlliste nennt darum ALLE Sichten.
    # Das ist der ehrliche Zustand, nicht ein Mangel des Tests.
    assert set(fehlt) | set(reg.ids()) == set(SICHT_IDS)
    assert len(fehlt) + len(reg.ids()) == len(SICHT_IDS)


# --- HR02 / HR03 / HR04 -------------------------------------------------------

def test_hr02_abdeckung_gutfall():
    reg = HilfeRegister((_kapitel("faelle"),))
    luecken = [i for i in SICHT_IDS if i != "faelle"]
    verify_sichten_abgedeckt(reg, luecken)  # darf nicht werfen


def test_hr03_sicht_ohne_kapitel_und_ohne_fehlliste():
    reg = HilfeRegister((_kapitel("faelle"),))
    luecken = [i for i in SICHT_IDS if i not in ("faelle", "dashboard")]
    with pytest.raises(HilfeUnvollstaendigError) as exc:
        verify_sichten_abgedeckt(reg, luecken)
    assert "dashboard" in str(exc.value)


def test_hr04_waisenkapitel():
    reg = HilfeRegister((_kapitel("gibtsnicht"),))
    with pytest.raises(HilfeUnvollstaendigError) as exc:
        verify_sichten_abgedeckt(reg, list(SICHT_IDS))
    assert "gibtsnicht" in str(exc.value)


# --- HR05 / HR06 --------------------------------------------------------------

def test_hr05_fehlliste_nicht_fortgeschrieben():
    reg = HilfeRegister((_kapitel("faelle"),))
    with pytest.raises(HilfeFehllisteError) as exc:
        verify_sichten_abgedeckt(reg, list(SICHT_IDS))  # 'faelle' noch drin
    assert "faelle" in str(exc.value)


def test_hr06_fehlliste_nennt_unbekanntes():
    reg = HilfeRegister(())
    with pytest.raises(HilfeFehllisteError) as exc:
        verify_sichten_abgedeckt(reg, list(SICHT_IDS) + ["phantomsicht"])
    assert "phantomsicht" in str(exc.value)


# --- HR07 --------------------------------------------------------------------

def test_hr07_fehlliste_darf_nur_schrumpfen():
    verify_fehlliste_monoton(["a", "b"], ["a", "b", "c"])   # geschrumpft: ok
    verify_fehlliste_monoton([], ["a"])                     # leer: ok
    with pytest.raises(HilfeFehllisteError) as exc:
        verify_fehlliste_monoton(["a", "b"], ["a"])
    assert "GEWACHSEN" in str(exc.value)
    assert "b" in str(exc.value)


# --- HR08 --------------------------------------------------------------------

def test_hr08_verweis_ins_leere():
    # (a) Ziel-Kapitel fehlt
    reg = HilfeRegister((
        _kapitel("faelle", kontext=[Kontexthilfe(
            "faelle.ampel", "Ampel", "Zeigt die Dringlichkeitsstufe.",
            verweis="dashboard#zweck")]),))
    with pytest.raises(HilfeVerweisError) as exc:
        verify_verweise(reg)
    assert "dashboard" in str(exc.value)

    # (b) Ziel-Kapitel da, Anker fehlt
    reg2 = HilfeRegister((
        _kapitel("faelle", kontext=[Kontexthilfe(
            "faelle.ampel", "Ampel", "Zeigt die Dringlichkeitsstufe.",
            verweis="faelle#gibtsnicht")]),))
    with pytest.raises(HilfeVerweisError) as exc2:
        verify_verweise(reg2)
    assert "gibtsnicht" in str(exc2.value)

    # (c) gueltiger Verweis auf einen Zusatzanker
    reg3 = HilfeRegister((
        _kapitel("faelle",
                 kontext=[Kontexthilfe("faelle.ampel", "Ampel",
                                       "Zeigt die Dringlichkeitsstufe.",
                                       verweis="faelle#ampel")],
                 zusatz=[Abschnitt("ampel", "Die Ampel",
                                   ("Erklaerung der Ampel.",))]),))
    verify_verweise(reg3)


# --- HR09 --------------------------------------------------------------------

def test_hr09_pflichtgliederung():
    unvollstaendig = tuple(
        Abschnitt(a, PFLICHT_TITEL[a], ("Text.",))
        for a in PFLICHT_ANKER if a != "grenzen")
    with pytest.raises(ModellError) as exc:
        Sichthilfe("faelle", "Fallübersicht", "Recht: dashboard.view",
                   unvollstaendig)
    assert "grenzen" in str(exc.value)

    # Bestandspruefung faengt auch ein an der Konstruktion vorbei gebautes
    # Kapitel (object.__new__-Weg wird hier nicht nachgestellt; stattdessen
    # pruefen wir, dass verify_gliederung auf dem Gutfall gruen ist).
    verify_gliederung(HilfeRegister((_kapitel("faelle"),)))


# --- HR10 --------------------------------------------------------------------

def test_hr10_kontextschluessel():
    with pytest.raises(ModellError):
        Kontexthilfe("ohnepunkt", "T", "Text.")
    with pytest.raises(ModellError):
        Kontexthilfe("faelle.Gross", "T", "Text.")     # Grossbuchstabe
    with pytest.raises(ModellError):
        Kontexthilfe("faelle.leer", "T", "   ")        # kein Text
    with pytest.raises(ModellError):
        Kontexthilfe("faelle.x", "T", "Text.", verweis="faelle_ampel")

    # Schluessel fremder Sicht im Kapitel
    with pytest.raises(ModellError) as exc:
        _kapitel("faelle", kontext=[Kontexthilfe("dashboard.x", "T", "Text.")])
    assert "dashboard.x" in str(exc.value)

    # Doppelvergabe innerhalb eines Kapitels
    with pytest.raises(ModellError):
        _kapitel("faelle", kontext=[Kontexthilfe("faelle.x", "T", "Text."),
                                    Kontexthilfe("faelle.x", "T", "Text.")])

    # global eindeutig ueber Kapitel hinweg
    verify_kontextschluessel(HilfeRegister((
        _kapitel("faelle", kontext=[Kontexthilfe("faelle.x", "T", "Text.")]),
        _kapitel("dashboard", kontext=[Kontexthilfe("dashboard.x", "T", "T.")]),
    )))


# --- HR11 --------------------------------------------------------------------

def test_hr11_abschnitt_formregeln():
    with pytest.raises(ModellError):
        Abschnitt("Gross", "T", ("Text.",))
    with pytest.raises(ModellError):
        Abschnitt("mit-strich", "T", ("Text.",))
    with pytest.raises(ModellError) as exc:
        Abschnitt("leer", "Titel")          # weder Absatz noch Liste
    assert "Grundregel 1" in str(exc.value)
    with pytest.raises(ModellError):
        Abschnitt("ok", "   ", ("Text.",))  # ohne Titel

    # doppelter Anker im Kapitel
    with pytest.raises(ModellError) as exc2:
        _kapitel("faelle", zusatz=[Abschnitt("zweck", "Nochmal", ("X.",))])
    assert "zweck" in str(exc2.value)


# --- HR12 --------------------------------------------------------------------

@pytest.mark.parametrize("text,teil", [
    ("Die Datei evidence_4711.db liegt daneben.", "evidence_4711.db"),
    ("Angemeldet als h012345.", "h012345"),
    ("Rueckfrage an sachbearbeiter@polizei.nrw.de.", "@"),
    ("Aktenzeichen 123 Js 4567/25 wird uebernommen.", "Js"),
    ("Der Server antwortet unter 192.168.10.5.", "192.168.10.5"),
])
def test_hr12_regel_h0_schlaegt_an(text, teil):
    reg = HilfeRegister((
        _kapitel("faelle", zusatz=[Abschnitt("probe", "Probe", (text,))]),))
    with pytest.raises(HilfeInhaltError) as exc:
        verify_fallinhaltsfrei(reg)
    assert teil in str(exc.value)


def test_hr12b_fiktive_beispiele_sind_erlaubt():
    text = ("Beispiel: die Fallakte zur fiktiven Nutzerkennung %s liegt als "
            "evidence_<uid>.db vor; der Server lauscht auf 127.0.0.2. "
            "Sachbearbeitung: %s."
            % (pruefung.FIKTIVE_UIDS[0], pruefung.FIKTIVE_PERSONALNUMMER))
    reg = HilfeRegister((
        _kapitel("faelle", zusatz=[Abschnitt("probe", "Probe", (text,))]),))
    verify_fallinhaltsfrei(reg)  # darf nicht werfen


# --- HR13 / HR14 --------------------------------------------------------------

def test_hr13_eingecheckter_stand_passt_zum_bestand():
    stand = _stand()
    aktuell = fehlliste_sichten(lade_register())
    # Monotonie gegen den eingecheckten Stand ...
    verify_fehlliste_monoton(aktuell, stand["sichten_ohne_hilfe"])
    # ... und der Stand nennt nur bekannte Sichten.
    unbekannt = sorted(set(stand["sichten_ohne_hilfe"]) - set(SICHT_IDS))
    assert not unbekannt, "Stand nennt unbekannte Sichten: %s" % unbekannt


def test_hr14_verify_alles_auf_auslieferungsbestand():
    reg = lade_register()
    verify_alles(reg, fehlliste_sichten(reg))


# --- HR15 bis HR19 (Build 591 / H4): Shell-Kontexthilfe ----------------------

def test_hr15_shell_bestand_vorhanden_und_praefixiert():
    reg = lade_register()
    assert reg.shell, "Der Shell-Bestand darf nicht leer sein (H4)."
    for k in reg.shell:
        assert k.schluessel.startswith(SHELL_PRAEFIX + ".")
    verify_shell_kontext(reg)
    # Der Praefix darf nie zugleich eine Sicht-ID sein.
    assert SHELL_PRAEFIX not in SICHT_IDS


def test_hr16_shell_schluessel_ohne_praefix():
    reg = HilfeRegister(shell=(Kontexthilfe("faelle.x", "T", "Text."),))
    with pytest.raises(HilfePruefungError) as exc:
        verify_shell_kontext(reg)
    assert "faelle.x" in str(exc.value)


def test_hr17_sichtkapitel_darf_praefix_nicht_benutzen():
    kapitel = Sichthilfe(
        sicht=SHELL_PRAEFIX, titel="Unzulaessig",
        recht_klartext="-",
        abschnitte=tuple(Abschnitt(a, PFLICHT_TITEL[a], ("Text.",))
                         for a in PFLICHT_ANKER),
        kontext=(Kontexthilfe("%s.x" % SHELL_PRAEFIX, "T", "Text."),))
    reg = HilfeRegister(sichten=(kapitel,))
    with pytest.raises(HilfePruefungError) as exc:
        verify_shell_kontext(reg)
    assert SHELL_PRAEFIX in str(exc.value)


def test_hr18_shell_verweis_ins_leere():
    reg = HilfeRegister(
        shell=(Kontexthilfe("shell.x", "T", "Text.",
                            verweis="faelle#zweck"),))
    with pytest.raises(HilfeVerweisError) as exc:
        verify_verweise(reg)
    assert "shell.x" in str(exc.value)

    # mit vorhandenem Ziel ist derselbe Verweis in Ordnung
    reg2 = HilfeRegister(
        sichten=(_kapitel("faelle"),),
        shell=(Kontexthilfe("shell.x", "T", "Text.",
                            verweis="faelle#zweck"),))
    verify_verweise(reg2)


def test_hr19_shell_texte_unterliegen_regel_h0():
    reg = HilfeRegister(
        shell=(Kontexthilfe("shell.x", "T",
                            "Angemeldet als h012345."),))
    with pytest.raises(HilfeInhaltError) as exc:
        verify_fallinhaltsfrei(reg)
    assert "h012345" in str(exc.value)
    # der Auslieferungsbestand selbst ist sauber
    verify_fallinhaltsfrei(HilfeRegister(shell=SHELL_KONTEXT))
