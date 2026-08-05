# =============================================================================
# tests/test_wartungsstufen_vollstaendig.py
# IT-Forensisches Ermittlungswerkzeug - Wartungsvorbehalt (Build 686)
# =============================================================================
# DER WAECHTER, DER MITWAECHST.
#
# WARUM ES IHN BRAUCHT - der Befund, aus dem er entstanden ist:
#   Der Wartungsvorbehalt ist seit Build 612 gebaut, eingebaut und durch
#   tests/test_wartungsvorbehalt_einbau.py gesichert. Dieser Test beantwortet
#   die Frage "ruft jedes Stufe-A-Werkzeug den Vorbehalt?" - und zwar
#   zuverlaessig.
#
#   NIEMAND BEANTWORTETE DIE ANDERE FRAGE: "ist ueberhaupt jedes schreibende
#   Werkzeug eingestuft?" Am 2026-08-05 lautete die Antwort: 7 von 35. Und
#   die Luecke wuchs nachweisbar - management/migrate_templates_blocktyp.py
#   traegt "Build 655", ist also NACH der Analyse (609) und NACH dem Einbau
#   (612) entstanden, fasst templates.db per ALTER an und war nie eingestuft.
#   Aufgefallen ist es elf Builds spaeter bei einer Nachpruefung.
#
#   EIN WAECHTER, DER NUR DIE BEKANNTEN FAELLE PRUEFT, WAECHST NICHT MIT.
#   Er sichert den Stand vom Tag seiner Entstehung und schweigt zu allem,
#   was danach gebaut wird. Genau das ist hier geschehen.
#
# DIE PRUEFUNG IN EINEM SATZ: Jedes Werkzeug, das der CLI-Katalog als
#   'schreibend' oder 'gemischt' fuehrt, muss in maintenance/wartungsstufen.py
#   in GENAU EINER der drei Listen stehen. Wer ein neues schreibendes
#   Werkzeug baut und nicht einstuft, macht die Suite rot.
#
# WARUM DER KATALOG DIE QUELLE IST und nicht ein Verzeichnisdurchlauf:
#   Der Katalog ist die Stelle, an der ein neues Werkzeug ohnehin eingetragen
#   werden MUSS - ohne Eintrag hat es keine Hilfe, und "keine Neuerung ohne
#   Hilfe" gilt im Projekt bereits. Damit haengt die Einstufungspflicht an
#   einer Pflicht, die schon durchgesetzt wird, statt an einer zweiten, die
#   man auch vergessen koennte. Ein Verzeichnisdurchlauf faende zudem jedes
#   Hilfsskript und erzwaenge Einstufungen fuer Dinge, die keine Werkzeuge
#   sind.
#
# WS01 - jedes schreibende Katalogwerkzeug ist eingestuft
# WS02 - keine Einstufung ohne Katalogeintrag (die Gegenrichtung)
# WS03 - kein Werkzeug steht in zwei Listen
# WS04 - jede Einstufung traegt einen Grund, und zwar einen tragfaehigen
# WS05 - die Stufe-A-Liste deckt sich mit der des Einbautests
# WS06 - jede eingestufte Datei existiert wirklich
# WS07 - kein Stufe-B- oder Stufe-C-Werkzeug ruft den Vorbehalt
#
# Version: v0.8.686 - Build: 686 - 2026-08-05
# =============================================================================

import sys
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent
if str(_WURZEL) not in sys.path:
    sys.path.insert(0, str(_WURZEL))

from maintenance.wartungsstufen import (                   # noqa: E402
    ALLE, STUFE_A, STUFE_B, STUFE_C, STUFEN,
    WERKZEUGE_A, WERKZEUGE_B, WERKZEUGE_C, grund, ist_stufe_a, stufe,
)
from management.help.cli_katalog import CLI_KATALOG        # noqa: E402

#: Die Arten, die der Katalog fuer schreibende Werkzeuge kennt. 'gemischt'
#: ist dabei, weil ein Werkzeug mit lesenden UND schreibenden Unterbefehlen
#: fuer den schreibenden Teil dieselbe Frage aufwirft.
SCHREIBENDE_ARTEN = ("schreibend", "gemischt")


def _katalog_schreibend():
    return {e.pfad for e in CLI_KATALOG if e.art in SCHREIBENDE_ARTEN}


# -----------------------------------------------------------------------------
# WS01 - der eigentliche Waechter
# -----------------------------------------------------------------------------

def test_ws01_jedes_schreibende_werkzeug_ist_eingestuft():
    """
    WS01 - kein schreibendes Werkzeug ohne Stufe.

    SCHLAEGT DIESER TEST AN, ist nichts kaputt - es fehlt eine Entscheidung.
    Die Meldung sagt deshalb, WAS zu tun ist, und nicht nur, dass etwas
    fehlt: ein Test, der einen Menschen ratlos zuruecklaesst, wird
    stillgelegt statt beantwortet.
    """
    fehlend = sorted(_katalog_schreibend() - set(ALLE))
    assert fehlend == [], (
        "Diese schreibenden Werkzeuge sind NICHT eingestuft:\n  %s\n\n"
        "Jedes gehoert in maintenance/wartungsstufen.py in GENAU EINE der "
        "drei Listen:\n"
        "  WERKZEUGE_A - braucht ein Wartungsfenster (Rebuild, Dateitausch, "
        "absichtliches Umstellen des Journal-/Sperrmodus, Schreiben auf "
        "Beweismittel, lange Transaktion ohne Rueckweg). Es muss dann auch "
        "wartungsvorbehalt() aufrufen.\n"
        "  WERKZEUGE_B - betriebsvertraeglich MIT benennbarer Einschraenkung.\n"
        "  WERKZEUGE_C - ohne Einschraenkung (schreibt Nutzdaten ueber die "
        "regulaere auditierte Route).\n\n"
        "Der Wert ist jeweils der tragende GRUND, nicht eine Beschreibung "
        "des Werkzeugs." % "\n  ".join(fehlend))


# -----------------------------------------------------------------------------
# WS02 - die Gegenrichtung
# -----------------------------------------------------------------------------

def test_ws02_keine_einstufung_ohne_katalogeintrag():
    """
    WS02 - was eingestuft ist, gibt es auch.

    OHNE DIESE RICHTUNG bliebe eine Einstufung stehen, wenn ihr Werkzeug
    umbenannt oder entfernt wird - und WS01 bliebe gruen, weil er nur in
    eine Richtung sieht. Eine Liste, die Werkzeuge fuehrt, die es nicht mehr
    gibt, laesst den Bestand vollstaendiger aussehen, als er ist.
    """
    ueberzaehlig = sorted(set(ALLE) - _katalog_schreibend())
    assert ueberzaehlig == [], (
        "Diese Werkzeuge sind eingestuft, stehen im Katalog aber nicht (mehr) "
        "als 'schreibend' oder 'gemischt':\n  %s\n"
        "Entweder ist der Katalogeintrag falsch, oder die Einstufung ist "
        "eine Karteileiche." % "\n  ".join(ueberzaehlig))


# -----------------------------------------------------------------------------
# WS03 bis WS06 - die Listen in sich
# -----------------------------------------------------------------------------

def test_ws03_kein_werkzeug_steht_in_zwei_listen():
    """
    WS03 - GENAU eine Stufe je Werkzeug.

    Stuende ein Werkzeug in zwei Listen, entschiede die Reihenfolge des
    Zusammenbaus ueber seine Stufe - und die letzte Zuweisung gewaenne
    lautlos. Bei A gegen C waere das der Unterschied zwischen 'braucht ein
    Wartungsfenster' und 'unbedenklich'.
    """
    doppelt = []
    for pfad in sorted(set(WERKZEUGE_A) | set(WERKZEUGE_B) | set(WERKZEUGE_C)):
        treffer = [name for name, liste in (("A", WERKZEUGE_A),
                                            ("B", WERKZEUGE_B),
                                            ("C", WERKZEUGE_C))
                   if pfad in liste]
        if len(treffer) > 1:
            doppelt.append("%s: %s" % (pfad, ", ".join(treffer)))
    assert doppelt == [], (
        "In mehr als einer Stufenliste:\n  %s" % "\n  ".join(doppelt))


@pytest.mark.parametrize("pfad", sorted(ALLE))
def test_ws04_jede_einstufung_traegt_einen_tragfaehigen_grund(pfad):
    """
    WS04 - ein Grund, der etwas sagt.

    Die Mindestlaenge ist grob und mit Absicht: Sie faengt nicht die
    schlechte Begruendung, sondern die FEHLENDE - Eintraege wie "ok", "-"
    oder "geprueft". Wer eine Einstufung nicht in einem Satz begruenden
    kann, hat sie nicht getroffen, sondern geraten.
    """
    st, gr = ALLE[pfad]
    assert st in STUFEN, "%s: unbekannte Stufe '%s'" % (pfad, st)
    assert len(gr.strip()) >= 25, (
        "%s (Stufe %s) hat keinen tragfaehigen Grund: %r" % (pfad, st, gr))
    # Die Zugriffshelfer muessen dasselbe sagen wie die Abbildung - sonst
    # haetten Leser und Liste zwei Wahrheiten.
    assert stufe(pfad) == st
    assert grund(pfad) == gr
    assert ist_stufe_a(pfad) == (st == STUFE_A)


def test_ws05_stufe_a_deckt_sich_mit_dem_einbautest():
    """
    WS05 - EINE Fassung der Stufe-A-Liste.

    Der Einbautest liest seit Build 686 aus demselben Modul; dieser Test
    haelt fest, DASS er es tut. Ohne ihn koennte jemand dort wieder eine
    eigene Liste anlegen - und zwei Listen laufen auseinander, sobald ein
    Werkzeug dazukommt. Genau daran krankte der Bestand bis hierher.
    """
    from tests import test_wartungsvorbehalt_einbau as einbau
    assert einbau.STUFE_A is WERKZEUGE_A, (
        "test_wartungsvorbehalt_einbau.STUFE_A ist nicht mehr dieselbe "
        "Abbildung wie maintenance.wartungsstufen.WERKZEUGE_A - es gibt "
        "wieder zwei Fassungen.")


@pytest.mark.parametrize("pfad", sorted(ALLE))
def test_ws06_jede_eingestufte_datei_existiert(pfad):
    """
    WS06 - die Einstufung zeigt auf etwas Wirkliches.

    Ein Tippfehler im Pfad macht WS01 nicht rot (der Katalogeintrag waere
    ja weiterhin ungedeckt) - wohl aber diesen Test. Ohne ihn koennte eine
    Einstufung ins Leere zeigen und trotzdem beruhigend aussehen.
    """
    assert (_WURZEL / pfad).is_file(), "%s gibt es nicht" % pfad


# -----------------------------------------------------------------------------
# WS07 - die Abgrenzung, jetzt fuer ALLE
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pfad", sorted(set(WERKZEUGE_B) | set(WERKZEUGE_C)))
def test_ws07_nur_stufe_a_ruft_den_vorbehalt(pfad):
    """
    WS07 - wer nicht Stufe A ist, ruft den Vorbehalt auch nicht.

    Das ist die Erweiterung von EB04 auf alle 26 Nicht-A-Werkzeuge. Der
    Grund steht im Kopf des Bauteils: "wer oft ohne Anlass gefragt wird,
    tippt das Wort irgendwann, ohne zu lesen. Dann ist die Sicherung genau
    dort wirkungslos, wo sie gebraucht wird."

    GEPRUEFT WIRD DER AUFRUF, NICHT DAS WORT. EB04 prueft bis Build 680
    'wartungsvorbehalt' not in quelle ueber den ganzen Quelltext - damit
    verbietet er einem Stufe-B-Werkzeug auch, seine Einstufung im Dateikopf
    zu NENNEN. Das ist zu scharf und trifft das Falsche: gefordert ist ja
    gerade, dass die Einstufung im Kopf steht.
    """
    quelle = (_WURZEL / pfad).read_text(encoding="utf-8")
    # Der Aufruf ist der Import - ohne ihn gibt es keinen. Erwaehnungen in
    # Kommentaren und Dateikoepfen bleiben ausdruecklich erlaubt.
    verboten = ("from maintenance.wartungsvorbehalt import",
                "import maintenance.wartungsvorbehalt")
    treffer = [z for z in verboten if z in quelle]
    assert treffer == [], (
        "%s ist als Stufe %s eingestuft (%s) und bindet den Wartungsvorbehalt "
        "trotzdem ein: %s" % (pfad, stufe(pfad), grund(pfad)[:60], treffer))


# -----------------------------------------------------------------------------
# WS08 und WS09 - die Einstufung muss ANKOMMEN
# -----------------------------------------------------------------------------
# Der Vorgang da6c16d0 verlangt woertlich: "Jedes schreibende Werkzeug sagt
# im Katalog UND im eigenen Kopf, ob es ein aktives Wartungsfenster braucht."
# WS01 bis WS07 sichern, dass die Einstufung EXISTIERT. Diese beiden sichern,
# dass sie dort steht, wo jemand sie liest.

@pytest.mark.parametrize("pfad", sorted(WERKZEUGE_B))
def test_ws08_stufe_b_nennt_ihre_einschraenkung_im_kopf(pfad):
    """
    WS08 - Stufe B sagt es im Dateikopf.

    WARUM DER KOPF UND NICHT NUR DER KATALOG: Wer die Datei oeffnet, um sie
    zu aendern, liest den Kopf; wer den Katalog liest, aendert gerade keine
    Datei. Dieselbe Begruendung wie EB03 fuer Stufe A - nur dass sie fuer
    Stufe B bis Build 680 nirgends durchgesetzt war. index_cli war seit der
    Analyse (Build 609) eingestuft und hat es elf Builds lang nicht gesagt.

    GEPRUEFT WIRD DIE MARKE, NICHT DER WORTLAUT. Ein Test, der den Text
    vorschreibt, erzwingt Abschreiben statt Nachdenken; die Marke sagt nur,
    dass die Frage im Kopf beantwortet ist.
    """
    kopf = "\n".join(
        (_WURZEL / pfad).read_text(encoding="utf-8").split("\n")[:90]).upper()
    assert "WARTUNGSSTUFE B" in kopf, (
        "%s ist als Stufe B eingestuft (%s), sagt es aber nicht im Dateikopf."
        % (pfad, grund(pfad)[:70]))


def test_ws09_der_katalog_kennt_die_stufe_a_werkzeuge():
    """
    WS09 - was Stufe A ist, steht auch im Katalog.

    DIE GEGENPROBE ZU EINER ECHTEN LUECKE: Am 2026-08-05 stimmten Katalog
    und Code fuer alle sechs damaligen Stufe-A-Werkzeuge ueberein - aber nur,
    weil beide von Hand gepflegt worden waren. Nichts hielt sie zusammen.
    Kommt ein Werkzeug hinzu (in Build 686 waren es drei), muss der Katalog
    mitwachsen, sonst liest ein Ermittler dort weiter 'unbedenklich'.

    GEPRUEFT WIRD DER RUECKGABEWERT 3: Er ist die eine Angabe, die ein
    Stufe-A-Werkzeug im Katalog zwingend tragen muss - ohne sie kann niemand
    einen Abbruch durch den Vorbehalt von einem Fehler unterscheiden.
    """
    eintraege = {e.pfad: e for e in CLI_KATALOG}
    ohne_hinweis = []
    for pfad in sorted(WERKZEUGE_A):
        eintrag = eintraege.get(pfad)
        assert eintrag is not None, "%s fehlt im Katalog" % pfad
        codes = getattr(getattr(eintrag, "tiefe", None), "exit_codes", ()) or ()
        text = " ".join(str(t) for _c, t in codes if _c == 3)
        if "artungsvorbehalt" not in text:
            ohne_hinweis.append(pfad)
    assert ohne_hinweis == [], (
        "Diese Stufe-A-Werkzeuge nennen den Wartungsvorbehalt nicht beim "
        "Rueckgabewert 3 im Katalog:\n  %s" % "\n  ".join(ohne_hinweis))
