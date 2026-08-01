# =============================================================================
# management/help/cli_epilog.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H20)
# =============================================================================
# Zweck:
#   Der EPILOG fuer die eingebaute Hilfe der Werkzeuge - also der Text, der
#   bei 'python -m ... --help' unter den Optionen erscheint. Er wird AUS DEM
#   KATALOG erzeugt (management/help/cli_katalog.py) und nicht je Werkzeug
#   von Hand geschrieben.
#
# WARUM ES DAS BRAUCHT - der Bruch, der ohne dieses Bauteil bleibt:
#   Seit H15 gibt es zu jedem Werkzeug einen Katalogeintrag mit gefahrenen
#   Beispielaufrufen. Zu sehen bekommt man ihn aber nur, wenn man 'python
#   tools/hilfe.py zeige <kennung>' kennt und aufruft. Wer stattdessen den
#   naheliegenden Weg geht - '--help' an das Werkzeug selbst -, sieht eine
#   Optionsliste und kein einziges Beispiel. Die teuerste Auskunft des
#   Katalogs steht damit an der Stelle, an der am wenigsten gesucht wird.
#
# KEIN VIERTER BESTAND. Dieselbe Festlegung wie in H19: Der Katalog ist die
#   Quelle. Die Konsolenuebersicht liest ihn ueber cli_text.py, die Vollhilfe
#   ueber cli_html.py, die eingebaute Hilfe der Werkzeuge ueber dieses Modul.
#   Ein je Werkzeug abgeschriebener Epilog waere binnen zweier Builds von den
#   gefahrenen Beispielen abgewichen - und ein Beispiel, das nicht mehr
#   stimmt, ist schlechter als keines.
#
# REIN ADDITIV. Kein Werkzeug aendert sein Verhalten. Es kommen je Werkzeug
#   drei Zeilen an den ArgumentParser: 'epilog=', 'formatter_class=' und der
#   Import. Optionen, Unterbefehle, Rueckgabewerte und Ablauf bleiben, wie
#   sie sind.
#
# WAS IM EPILOG STEHT - UND WAS NICHT:
#   DRIN sind die gefahrenen Beispielaufrufe und die Rueckgabewerte. Das sind
#   die beiden Auskuenfte, die man VOR dem Druecken der Eingabetaste braucht
#   und die argparse selbst nicht kennt.
#   DRAUSSEN bleiben die Warnhinweise und die Pruefnachweise - nicht, weil
#   sie unwichtig waeren, sondern weil sie lang sind: bei manchen Werkzeugen
#   fuellen sie mehr als eine Bildschirmseite, und eine '--help'-Ausgabe, die
#   man scrollen muss, um die Optionen zu sehen, hat ihren Zweck verfehlt.
#   SIE WERDEN ABER GENANNT UND GEZAEHLT (Grundregel 1): der Epilog sagt, wie
#   viele Warnhinweise es gibt und wo sie stehen. Niemand soll aus dem Fehlen
#   schliessen, es gaebe keine.
#
# WARUM EIN EIGENER FORMATIERER:
#   argparse laesst den Epilog standardmaessig durch textwrap.fill() laufen.
#   Das macht aus mehreren Zeilen EINEN Absatz - Einrueckungen, Leerzeilen
#   und der Zeilenumbruch einer Befehlszeile waeren dahin, und eine
#   Befehlszeile, die man nicht kopieren kann, ist keine.
#   argparse.RawDescriptionHelpFormatter waere die naheliegende Antwort,
#   nimmt aber AUCH die Beschreibung vom Umbruch aus - und die ist in allen
#   63 Werkzeugen als ein langer Satz geschrieben, der dann als eine einzige
#   ueberlange Zeile erschiene. HilfeFormat unterscheidet beides: die
#   Beschreibung wird umbrochen wie bisher, der Epilog nicht.
#
# ASCII, 78 ZEICHEN, KEINE ESCAPE-SEQUENZEN - dieselben drei Festlegungen wie
#   in cli_text.py, und aus denselben Gruenden (die Begruendung steht dort im
#   Kopf). Der Umbruch benutzt dieselbe Funktion.
#
# Version: v0.8.624 - Build: 624 - 2026-08-01
# =============================================================================

from __future__ import annotations

import argparse
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from management.help.cli_katalog import CLI_KATALOG, eintrag
from management.help.cli_modell import CliEintrag
from management.help.cli_text import BREITE, umbrechen

#: Werkzeuge, die KEINEN Epilog bekommen - mit dem Grund, aus dem es bei
#: ihnen nicht geht. DIESE LISTE IST DER EHRLICHE TEIL DES BAUTEILS: ohne sie
#: waere aus dem Bestand nicht zu erkennen, ob ein Werkzeug uebersehen wurde
#: oder bewusst aussen vor bleibt (Grundregel 1). verify_epilog_abgedeckt()
#: erzwingt, dass jedes der 65 Werkzeuge entweder verdrahtet ist oder hier
#: mit Begruendung steht.
OHNE_EPILOG: Dict[str, str] = {
    "pruefe_auslieferung":
        "DAS WERKZEUG, DAS EINE AUSLIEFERUNG PRUEFT, DARF NICHT DAVON "
        "ABHAENGEN, DASS DIE AUSLIEFERUNG HEIL IST. Heute braucht es nur die "
        "Standardbibliothek und die Pruefsummenliste; ein Epilog wuerde ihm "
        "einen Import aus 'management/' aufzwingen. Fehlte dann genau dort "
        "eine Datei - der Fall, fuer den es dieses Werkzeug gibt -, "
        "scheiterte es beim Import statt einen Befund zu melden. Der Preis "
        "waere ein Epilog, der Gewinn ein Werkzeug, das im Ernstfall "
        "schweigt.",
    "diag_migrationsluecke":
        "Das Skript hat keinen Parameter und keine main(): sein ganzer "
        "Ablauf steht auf Modulebene und laeuft beim Import los. Um '--help' "
        "anzubieten, muesste der Ablauf in eine Funktion wandern - eine "
        "Verhaltensaenderung an einem 62 Zeilen langen BELEG, und die waere "
        "hier teurer als der Gewinn.",
}


#: Werkzeuge, die den Epilog haben, ihn aber NICHT ueber argparse ausgeben -
#: weil sie kein argparse benutzen. Auch das gehoert benannt: eine Pruefung,
#: die argparse voraussetzt (etwa die auf den 'usage:'-Block), waere hier
#: sonst still uebersprungen worden.
EPILOG_OHNE_ARGPARSE: Dict[str, str] = {
    "poc_m019_weg_a":
        "Der ganze Aufrufteil sind drei Zeilen ueber sys.argv; daran wird "
        "nichts geaendert. Das Werkzeug bekommt den Epilog trotzdem, weil es "
        "das gefaehrlichste im Bestand ist: es benennt Spalten in einer "
        "coordinator.db um und hat keine eingebaute Pruefung, dass die "
        "uebergebene Datei wirklich eine Kopie ist. '-h' und '--help' werden "
        "abgefangen, BEVOR irgendetwas geoeffnet wird.",
}


class CliEpilogError(Exception):
    """Ein Werkzeug ist weder verdrahtet noch begruendet ausgenommen."""


class _RohText(str):
    """
    Ein Text, der NICHT umbrochen werden darf.

    Warum eine eigene Klasse und keine Markierung im Text: argparse reicht
    den Epilog unveraendert an _fill_text() weiter, und an einem Typ laesst
    sich das erkennen, ohne dem Text ein Steuerzeichen mitzugeben, das
    irgendwann jemand ausgibt. Faellt die Kennzeichnung doch einmal weg
    (etwa weil argparse den Text kopiert), bricht nichts - der Epilog wird
    dann nur umbrochen wie frueher.
    """


class HilfeFormat(argparse.HelpFormatter):
    """
    Umbricht die Beschreibung wie bisher, den Epilog nicht.

    Der Einzug wird bewusst VORANGESTELLT und nicht per textwrap gesetzt:
    argparse gibt hier einen leeren Einzug, und der Epilog bringt seine
    eigene Ausrichtung schon mit.
    """

    def _fill_text(self, text, width, indent):        # noqa: D401
        if isinstance(text, _RohText):
            return "\n".join(indent + z for z in str(text).split("\n"))
        return super()._fill_text(text, width, indent)


# -----------------------------------------------------------------------------
# Bauen
# -----------------------------------------------------------------------------

def _beispielzeilen(e: CliEintrag) -> List[str]:
    """
    Die gefahrenen Beispielaufrufe.

    DER AUFRUF WIRD NICHT UMBROCHEN - dieselbe Entscheidung wie in
    cli_text.zeige_text(): eine ueber zwei Zeilen verteilte Befehlszeile
    laesst sich nicht kopieren, und genau dafuer steht sie da. Die WIRKUNG
    wird umbrochen, sie ist Fliesstext.
    """
    t = e.tiefe
    if t is None or not t.beispiele:
        return []
    zeilen: List[str] = ["Beispiele"]
    for bsp in t.beispiele:
        zeilen.append("  " + bsp.aufruf)
        zeilen.extend(umbrechen(bsp.wirkung, BREITE, "      "))
        zeilen.append("")
    return zeilen


def _ohne_beispiel_zeilen(e: CliEintrag) -> List[str]:
    """
    Der Ersatz, wenn es kein Beispiel gibt.

    Er steht unter derselben Ueberschrift wie die Beispiele. Ohne
    Ueberschrift klebte der Satz am Vorherigen und saehe aus wie dessen
    Fortsetzung - dann liest man ueber die Auskunft hinweg, dass hier
    bewusst nichts steht.
    """
    return (["Beispiele"]
            + list(umbrechen(
                "Fuer dieses Werkzeug ist kein Beispielaufruf aufgenommen: es "
                "gibt keinen Lauf, der sich gefahrlos vorfuehren liesse. Ein "
                "erfundenes Beispiel steht hier bewusst nicht.",
                BREITE, "  "))
            + [""])


def _rueckgabezeilen(e: CliEintrag) -> List[str]:
    t = e.tiefe
    if t is None or not t.exit_codes:
        return []
    zeilen: List[str] = ["Rueckgabewerte"]
    for code, bedeutung in t.exit_codes:
        zeilen.extend(umbrechen("%d = %s" % (code, bedeutung),
                                BREITE, "      ", "  "))
    zeilen.append("")
    return zeilen


def _verweiszeilen(e: CliEintrag) -> List[str]:
    """
    Der Verweis auf die volle Auskunft - und die EHRLICHE ZAEHLUNG dessen,
    was hier nicht steht.

    Die Zahl der Warnhinweise gehoert genannt. Sonst schliesst jemand aus
    dem Fehlen eines Warnblocks, es gaebe nichts zu beachten - und bei
    einem Werkzeug, das Daten veraendert, ist das der teuerste Irrtum, den
    eine Hilfe ermoeglichen kann.
    """
    zeilen: List[str] = []
    warnungen = len(e.tiefe.warnungen) if e.tiefe else 0
    hinweis = "Mehr zu diesem Werkzeug - Datenbanken, Betriebsvoraussetzung"
    if warnungen == 1:
        # Die Einzahl wird ausgeschrieben. 'die 1 Warnhinweise' liest sich
        # wie ein Fehler im Text - und wer dem Text nicht traut, liest ihn
        # nicht zu Ende.
        hinweis += ", der eine Warnhinweis"
    elif warnungen:
        hinweis += (", die %d Warnhinweise" % warnungen)
    hinweis += (" und der Nachweis, wo und wann die Beispiele gefahren "
                "wurden - steht in:")
    zeilen.extend(umbrechen(hinweis, BREITE, ""))
    zeilen.append("  python tools/hilfe.py zeige %s" % e.schluessel)
    if e.schreibt():
        zeilen.append("")
        zeilen.extend(umbrechen(
            "ACHTUNG: Dieses Werkzeug kann Daten veraendern. Vor dem ersten "
            "Lauf gehoert die Zeile darueber gelesen.", BREITE, ""))
    return zeilen


def epilog_text(e: CliEintrag) -> str:
    """Der Epilog als reiner Text - fuer Pruefungen und die Textausgabe."""
    zeilen: List[str] = []
    if e.hat_beispiele():
        zeilen.extend(_beispielzeilen(e))
    else:
        zeilen.extend(_ohne_beispiel_zeilen(e))
    zeilen.extend(_rueckgabezeilen(e))
    zeilen.extend(_verweiszeilen(e))
    return "\n".join(zeilen).rstrip()


def unbekannt_text(schluessel: str) -> str:
    """
    Der Epilog fuer eine Kennung, die es im Katalog nicht gibt.

    ES WIRD NICHT GEWORFEN. Eine Ausnahme an dieser Stelle wuerde '--help'
    unbrauchbar machen - und zwar bei genau dem Werkzeug, dessen Eintrag
    fehlt, also dort, wo die Hilfe am noetigsten waere. Stattdessen sagt der
    Epilog, was los ist; verify_epilog_abgedeckt() und der zugehoerige Test
    lassen den Fall gar nicht erst in eine Auslieferung.
    """
    return "\n".join(umbrechen(
        "Zu diesem Werkzeug fehlt der Eintrag im Werkzeugkatalog "
        "(management/help/cli_katalog.py, Kennung '%s'). Damit fehlen hier "
        "die Beispielaufrufe und die Rueckgabewerte. Das ist ein Befund und "
        "keine Eigenheit des Werkzeugs." % schluessel, BREITE, ""))


def epilog(schluessel: str):
    """
    DIE FUNKTION, DIE DIE WERKZEUGE AUFRUFEN.

        p = argparse.ArgumentParser(
                prog="...", description="...",
                epilog=cli_epilog.epilog("cases_admin"),
                formatter_class=cli_epilog.HilfeFormat)

    Der Rueckgabewert ist ein _RohText, damit HilfeFormat ihn vom Umbruch
    ausnimmt. Fuer alles andere ist er eine gewoehnliche Zeichenkette.
    """
    e = eintrag(schluessel)
    if e is None:
        return _RohText(unbekannt_text(schluessel))
    return _RohText(epilog_text(e))


# -----------------------------------------------------------------------------
# Pruefung
# -----------------------------------------------------------------------------

def verify_epilog_abgedeckt(verdrahtet: Iterable[str],
                            katalog: Sequence[CliEintrag] = CLI_KATALOG
                            ) -> None:
    """
    Jedes Werkzeug ist entweder verdrahtet oder steht begruendet in
    OHNE_EPILOG - und zwar genau eines von beiden.

    'verdrahtet' sind die Kennungen, die der Test im Bestand tatsaechlich
    gefunden hat (Textsuche nach dem Aufruf). Gegen eine gepflegte Liste zu
    pruefen waere wertlos: sie koennte behaupten, ein Werkzeug sei
    verdrahtet, waehrend es das nicht ist. Dasselbe Vorgehen wie bei
    cli_katalog.verify_cli_abgedeckt - gemessen wird der Bestand.
    """
    gefunden = set(verdrahtet)
    alle = {e.schluessel for e in katalog}

    fremd = sorted(gefunden - alle)
    if fremd:
        raise CliEpilogError(
            "Epilog verdrahtet fuer Kennungen ohne Katalogeintrag: %s"
            % ", ".join(fremd))

    ausgenommen = set(OHNE_EPILOG)
    fremd_ausnahme = sorted(ausgenommen - alle)
    if fremd_ausnahme:
        raise CliEpilogError(
            "OHNE_EPILOG nennt Kennungen ohne Katalogeintrag: %s"
            % ", ".join(fremd_ausnahme))

    doppelt = sorted(gefunden & ausgenommen)
    if doppelt:
        raise CliEpilogError(
            "Diese Werkzeuge sind verdrahtet UND als Ausnahme gefuehrt - "
            "eines von beidem ist falsch: %s" % ", ".join(doppelt))

    offen = sorted(alle - gefunden - ausgenommen)
    if offen:
        raise CliEpilogError(
            "Diese Werkzeuge haben keinen Epilog und stehen auch nicht mit "
            "Begruendung in OHNE_EPILOG: %s. Beides ist zu vertreten - "
            "stillschweigend weglassen nicht." % ", ".join(offen))

    ohne_grund = sorted(k for k, g in OHNE_EPILOG.items() if not g.strip())
    if ohne_grund:
        raise CliEpilogError(
            "Ausnahme ohne Begruendung: %s" % ", ".join(ohne_grund))


def fehlliste_epilog(verdrahtet: Iterable[str],
                     katalog: Sequence[CliEintrag] = CLI_KATALOG
                     ) -> Tuple[str, ...]:
    """
    Die Werkzeuge ohne Epilog und ohne Ausnahme - gerechnet, nicht gefuehrt.
    Fuer 'python tools/hilfe.py stand'.
    """
    gefunden = set(verdrahtet)
    return tuple(sorted({e.schluessel for e in katalog}
                        - gefunden - set(OHNE_EPILOG)))
