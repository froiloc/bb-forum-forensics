# =============================================================================
# management/help/cli_text.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H16)
# =============================================================================
# Zweck:
#   Die Textausgabe des CLI-Katalogs. REINE FUNKTIONEN - keine Ausgabe, kein
#   Dateisystem, kein sys.exit. Das Werkzeug tools/hilfe.py setzt sie nur
#   zusammen und schreibt sie hinaus.
#
# WARUM DIE TRENNUNG: Eine Formatierung, die selbst druckt, laesst sich nur
#   ueber die Konsole pruefen. So ist jede Zeile Rueckgabewert und damit
#   direkt vergleichbar (Grundregel 3).
#
# DREI FESTLEGUNGEN ZUR AUSGABE, alle aus dem Bestand begruendet:
#
#   1) REINES ASCII. Der gesamte Katalog kommt ohne Umlaute und ohne 'ss'
#      aus, und die Ausgabe hier ebenso. Das ist kein Schoenheitsfehler,
#      sondern Hausstil: saemtliche argparse-Beschreibungen im Bestand
#      schreiben 'Uebersicht', 'Kapazitaets-Datenbasis', 'gueltig'. Die
#      Windows-Eingabeaufforderung laeuft nicht zwingend in UTF-8; ein
#      Umlaut wird dort zu einem Kaestchen, und eine Hilfe mit Kaestchen
#      liest niemand zweimal.
#
#   2) KEINE ESCAPE-SEQUENZEN. Keine Farben, kein Fettdruck, kein
#      Loeschen der Zeile. Was hier herauskommt, muss sich in eine Datei
#      umleiten und in einen Vermerk einfuegen lassen.
#
#   3) 78 ZEICHEN. Zwei weniger als die uebliche Konsolenbreite, damit ein
#      Zeilenumbruch der Konsole nichts zerreisst und ein Einzug beim
#      Kopieren erhalten bleibt.
#
# AENDERUNG BUILD 639 (Ticket 60e4236e): zeige_text() gibt einen Abschnitt
#   'Einstellungen in config.yaml' aus - mit allen DREI Zustaenden, also
#   auch 'geprueft, liest keinen Eintrag' und 'noch nicht erhoben'.
#
# AENDERUNG BUILD 696 (Ticket 9e1ba63e): hilfe_aufruf() leitet den Vorschlag
#   'X --help' nicht mehr aus der SCHREIBWEISE der Aufrufform ab, sondern aus
#   ihrer STRUKTUR - Modul hinter '-m' bzw. Dateipfad auf '.py'. Vier von 71
#   Katalogeintraegen nannten bis dahin die Hilfe eines Unterbefehls oder
#   eines Arguments statt die des Werkzeugs; einer davon war als Befehlszeile
#   gar nicht lauffaehig. Naeheres bei hilfe_aufruf().
#
# Version: v0.8.696 - Build: 696 - 2026-08-11
# =============================================================================

from __future__ import annotations

import difflib
from typing import Iterable, List, Sequence, Tuple

from management.help.cli_modell import CliEintrag
from management.help.cli_katalog import (
    CLI_KATALOG, CLI_SCHLUESSEL, eintrag, gruppen, suche,
)

#: Zeilenbreite der Ausgabe.
BREITE = 78

#: Kurzzeichen fuer die Art eines Werkzeugs bzw. eines Unterbefehls.
#: Zwei Zeichen, damit die Spalte in der Liste steht wie gemauert.
ART_KURZ = {
    "lesend": "L ",
    "schreibend": "S ",
    "gemischt": "LS",
}


def art_kurz(art: str) -> str:
    """'lesend' -> 'L ', 'schreibend' -> 'S ', 'gemischt' -> 'LS'."""
    return ART_KURZ.get(art, "? ")


def umbrechen(text: str, breite: int = BREITE, einzug: str = "",
              erster_einzug: str = None) -> Tuple[str, ...]:
    """
    Bricht einen Fliesstext auf 'breite' Zeichen um.

    Bewusst von Hand und nicht ueber textwrap: der Einzug der Folgezeilen
    soll frei waehlbar sein, und ein Wort, das laenger ist als die Breite,
    wird NICHT zerschnitten - eine zerschnittene Kennung oder ein
    zerschnittener Pfad waere unbrauchbar (dann lieber eine zu lange Zeile).
    """
    if erster_einzug is None:
        erster_einzug = einzug
    worte = (text or "").split()
    if not worte:
        return ()
    zeilen: List[str] = []
    aktuell = erster_einzug
    leer = True
    for wort in worte:
        kandidat = wort if leer else (aktuell + " " + wort)
        if not leer and len(kandidat) > breite:
            zeilen.append(aktuell)
            aktuell = einzug + wort
        else:
            aktuell = (erster_einzug + wort) if leer else kandidat
        leer = False
    zeilen.append(aktuell)
    return tuple(zeilen)


def _absatz(zeilen: List[str], text: str, einzug: str = "  ",
            erster: str = None) -> None:
    zeilen.extend(umbrechen(text, BREITE, einzug, erster))


def spaltenzeile(marke: str, name: str, text: str,
                 namensbreite: int = 26) -> Tuple[str, ...]:
    """
    Eine Zeile aus Marke, Kennung und Fliesstext - mit haengendem Einzug.

    BEFUND BEIM ERSTEN LAUF (Build 608): Die erste Fassung hat die fertig
    ausgerichtete Zeile durch den Zeilenumbruch geschickt. Der zerlegt sie
    aber in WOERTER und setzt sie neu - die Spaltenausrichtung war damit
    dahin, und der Folgeeinzug landete auch auf der ERSTEN Zeile. Die Liste
    sah aus wie ein Textblock, der nach rechts gerutscht ist.
    Deshalb: der feste Teil wird gesetzt, und NUR der Fliesstext wird
    umbrochen - mit einem Einzug, der genau unter dem Fliesstext steht.
    """
    kopf = "  %-3s %-*s " % (marke, namensbreite, name)
    einzug = " " * len(kopf)
    zeilen = umbrechen(text, BREITE, einzug, kopf)
    return zeilen if zeilen else (kopf.rstrip(),)


#: Zeichen, an denen ein Bestandteil der Aufrufform als Platzhalter, Option
#: oder Alternative erkennbar ist. Nur noch fuer den Notnagel in
#: hilfe_aufruf() gebraucht - siehe dort. '(' steht seit Build 696 mit
#: in der Liste: 'pruefe_profilerfassung' schreibt seine Alternative als
#: '(--verzeichnis VERZ | --forensic-db DATEI)', und die oeffnende Klammer
#: fiel durch jedes Raster, das nur '-', '<', '[' und '|' kannte.
_ABBRUCHZEICHEN: Tuple[str, ...] = ("-", "<", "[", "(", "{")


def hilfe_aufruf(aufruf: str) -> str:
    """
    Aus der Aufrufform den Aufruf des WERKZEUGS mit '--help' bilden.

    WOZU: Jeder gezeigte Eintrag endet mit dem Verweis auf die eingebaute
    Hilfe des Zielwerkzeugs. Der Katalog sagt, WOZU ein Werkzeug da ist;
    die vollstaendige Liste seiner Optionen sagt das Werkzeug selbst - und
    zwar immer aktuell, waehrend ein abgeschriebener Optionsblock veralten
    wuerde.

    AENDERUNG BUILD 696 (Ticket 9e1ba63e-8d6b-4fcc-819b-91b059d9c713):
    Bis Build 693 wurde ab dem ersten Bestandteil abgeschnitten, der wie ein
    Platzhalter, eine Option oder eine Alternative AUSSAH. Dieses Raster ist
    aufgegeben, weil es nicht am Werkzeug hing, sondern an der SCHREIBWEISE
    der Aufrufform im Katalog. Ein als blosses Wort geschriebener Unterbefehl
    fiel hindurch und blieb stehen:

      export_admin           -> '... export_admin case-status-xlsx --help'
      lkae_admin             -> '... lkae_admin build --help'
      poc_m019_weg_a         -> '... poc_m019_weg_a.py kopie.db --help'
      pruefe_profilerfassung -> '... pruefe_profilerfassung.py (--verzeichnis
                                 VERZ --help'   (nicht nur unpassend, sondern
                                 als Kommandozeile unbrauchbar)

    Bei 'backup_admin' geschah es NICHT - allein deshalb, weil die Aufrufform
    dort 'plan|run|list' schreibt und am '|' abgeschnitten wurde. Dieselbe
    Sache, zwei Ergebnisse, je nach Tippweise: das war der eigentliche Fehler.

    DIE JETZIGE REGEL IST STRUKTURELL statt textlich. Sie fragt nicht, wie
    der Rest der Zeile geschrieben ist, sondern woraus ein Python-Aufruf
    besteht - und davon gibt es im Bestand genau zwei Formen:

      Weg 1  Modulaufruf: '... -m <modul> ...'  -> 'python -m <modul> --help'
      Weg 2  Dateiaufruf: '... <pfad>.py ...'   -> 'python <pfad>.py --help'

    Alles hinter dem Modul bzw. dem Dateipfad ist Sache des Werkzeugs und
    gehoert nicht in einen Vorschlag, der die Hilfe DES WERKZEUGS ankuendigt.
    Damit liefert die Zeile 'Vollstaendige Optionen nennt das Werkzeug selbst'
    bei jedem Eintrag dasselbe, unabhaengig von der Schreibweise.

    Es ist bewusst die im Ticket erstgenannte Loesung: der Vorschlag nennt das
    Werkzeug. Die dort ebenfalls erwogene Gegenvariante - Unterbefehl stehen
    lassen, dafuer die 'a|b'-Aufrufformen nachziehen - haette die angekuendigte
    Wirkung der Zeile geaendert und in 26 Katalogeintraegen eine Auswahl
    verlangt, welcher Unterbefehl der beispielhafte sei. Das waere eine neue
    Pflegestelle ohne Gegenwert.

    DIESELBE ABLEITUNG fuehrt tests/test_help_cli_epilog.py._werkzeug_aufruf()
    seit Build 624 als eigene Fassung, weil sie sich auf hilfe_aufruf() nicht
    verlassen konnte. Sie bleibt dort als UNABHAENGIGE Gegenprobe stehen; CT03d
    haelt fest, dass beide Wege fuer jeden Katalogeintrag dasselbe ergeben.

    NOTNAGEL: Kommt eine Aufrufform ohne '-m' und ohne '.py' daher - im
    Bestand gibt es keine, kuenftig kann es eine geben -, greift das alte
    Raster. Es ist als Rueckfall besser als ein leerer Vorschlag; still
    bleibt der Fall nicht, denn CT03c faehrt jeden Eintrag dagegen.
    """
    teile = (aufruf or "").split()
    if not teile:
        return "--help"
    kopf = teile[0]                      # in aller Regel 'python'

    # --- Weg 1: Modulaufruf ----------------------------------------------
    # '-m' und das unmittelbar folgende Modul sind der Aufruf des Werkzeugs.
    if "-m" in teile:
        i = teile.index("-m")
        if i + 1 < len(teile):
            return "%s -m %s --help" % (kopf, teile[i + 1])

    # --- Weg 2: Dateiaufruf ----------------------------------------------
    # Der erste Bestandteil, der auf '.py' endet und KEIN Platzhalter ist.
    # Die Platzhalterprobe ist noetig, weil eine Aufrufform kuenftig auch
    # '<skript.py>' als Argument fuehren kann - das waere nicht das Werkzeug.
    for t in teile[1:]:
        if t.endswith(".py") and not t.startswith(_ABBRUCHZEICHEN):
            return "%s %s --help" % (kopf, t)

    # --- Notnagel: das alte Raster ---------------------------------------
    behalten: List[str] = []
    for t in teile:
        if behalten and (t.startswith(_ABBRUCHZEICHEN) or "|" in t):
            break
        behalten.append(t)
    return " ".join(behalten) + " --help"


def nahetreffer(begriff: str,
                schluessel: Sequence[str] = CLI_SCHLUESSEL,
                hoechstens: int = 5) -> Tuple[str, ...]:
    """
    Vorschlaege zu einer unbekannten Kennung.

    Zwei Wege, in dieser Reihenfolge: erst die Kennungen, die den Begriff
    ENTHALTEN (wer 'backup' tippt, meint 'backup_admin'), dann die
    aehnlich geschriebenen (wer sich vertippt, bekommt trotzdem einen
    Vorschlag). Ohne Vorschlaege waere die Fehlermeldung eine Sackgasse.
    """
    b = (begriff or "").strip().lower()
    if not b:
        return ()
    enthalten = [s for s in schluessel if b in s.lower()]
    aehnlich = difflib.get_close_matches(b, list(schluessel), n=hoechstens,
                                         cutoff=0.6)
    raus: List[str] = []
    for s in enthalten + aehnlich:
        if s not in raus:
            raus.append(s)
    return tuple(raus[:hoechstens])


# -----------------------------------------------------------------------------
# 1) liste
# -----------------------------------------------------------------------------

def liste_text(nur_schreibend: bool = False) -> str:
    """
    Alle Werkzeuge, nach Arbeitsbereich gruppiert.

    DIE ART STEHT VORNE, nicht hinten: 'L', 'S' oder 'LS'. Wer die Liste
    ueberfliegt, sucht meistens genau danach - was aendert etwas und was
    nicht. Eine Angabe am Zeilenende faende er erst beim zweiten Lesen.
    """
    zeilen: List[str] = []
    zeilen.append("AIW - Werkzeuge der Kommandozeile")
    zeilen.append("=" * BREITE)
    zeilen.append("")
    _absatz(zeilen,
            "L = liest nur, S = schreibt, LS = beides je nach Unterbefehl. "
            "Einzelheiten zu einem Werkzeug: 'python tools/hilfe.py zeige "
            "<kennung>'.", einzug="")
    if nur_schreibend:
        zeilen.append("")
        _absatz(zeilen,
                "AUSSCHNITT: nur Werkzeuge, die etwas aendern koennen.",
                einzug="")
    zeilen.append("")

    gezeigt = 0
    for name, eintraege in gruppen():
        auswahl = [e for e in eintraege
                   if not nur_schreibend or e.schreibt()]
        if not auswahl:
            continue
        zeilen.append(name)
        zeilen.append("-" * len(name))
        for e in auswahl:
            gezeigt += 1
            zeilen.extend(spaltenzeile(art_kurz(e.art).strip(),
                                       e.schluessel, e.titel, 28))
        zeilen.append("")

    zeilen.append("-" * BREITE)
    zeilen.append("%d Werkzeuge%s." % (
        gezeigt, " (Ausschnitt)" if nur_schreibend else ""))
    return "\n".join(zeilen)


# -----------------------------------------------------------------------------
# 2) zeige
# -----------------------------------------------------------------------------

def zeige_text(e: CliEintrag) -> str:
    """Ein Werkzeug im Einzelnen."""
    zeilen: List[str] = []
    zeilen.append(e.schluessel)
    zeilen.append("=" * min(len(e.schluessel), BREITE))
    zeilen.append("")
    # BEFUND CT09 (Build 608): diese Zeile wurde roh angehaengt und lief bei
    # langen Titeln ueber die Breite. Sie geht jetzt durch denselben Umbruch
    # wie alles andere - eine Ausnahme "nur diese eine Zeile" waere genau die
    # Sorte Ausnahme, die spaeter niemand mehr erklaeren kann.
    _absatz(zeilen, "%s (%s)" % (e.titel, e.gruppe), einzug="")
    zeilen.append("")

    _absatz(zeilen, e.zweck, einzug="")
    zeilen.append("")

    zeilen.append("Aufruf")
    _absatz(zeilen, e.aufruf, einzug="  ")
    zeilen.append("")

    zeilen.append("Datei")
    zeilen.append("  " + e.pfad)
    zeilen.append("")

    zeilen.append("Art")
    _absatz(zeilen, {
        "lesend": "Liest nur. Keine Datenbank wird veraendert.",
        "schreibend": "Veraendert Daten.",
        "gemischt": "Je nach Unterbefehl lesend oder schreibend - siehe "
                    "unten.",
    }[e.art], einzug="  ")
    if e.ausgabe:
        _absatz(zeilen, "Erzeugt: " + e.ausgabe, einzug="  ")
    zeilen.append("")

    if e.befehle:
        zeilen.append("Unterbefehle")
        for b in e.befehle:
            marke = "S" if b.art == "schreibend" else "L"
            zeilen.extend(spaltenzeile(marke, b.name or "(ohne)", b.zweck, 22))
        zeilen.append("")

    zeilen.append("Datenbanken")
    if e.datenbanken:
        for d in e.datenbanken:
            zeilen.extend(umbrechen("- " + d, BREITE, "    ", "  "))
    else:
        zeilen.append("  keine")
    zeilen.append("")

    zeilen.append("Betrieb")
    _absatz(zeilen, e.betrieb, einzug="  ")
    zeilen.append("")

    zeilen.append("Beleg")
    _absatz(zeilen,
            "Schreibt Belege ins Protokollbuch (audit_log)." if e.beleg
            else "Schreibt keine Belege ins Protokollbuch.", einzug="  ")
    zeilen.append("")

    if e.hinweis:
        zeilen.append("Hinweis")
        _absatz(zeilen, e.hinweis, einzug="  ")
        zeilen.append("")

    # -----------------------------------------------------------------
    # Einstellungen aus config.yaml (NEU Build 639, Ticket 60e4236e).
    #
    # DIE DREI ZUSTAENDE WERDEN ALLE DREI AUSGEGEBEN, und das ist der Punkt:
    # "liest keinen Eintrag" ist eine Auskunft, "noch nicht nachgesehen" ist
    # eine andere. Wer nur die Eintraege druckte, liesse den Leser bei jedem
    # Werkzeug ohne Abschnitt raten, welcher der beiden Faelle vorliegt.
    # -----------------------------------------------------------------
    zeilen.append("Einstellungen in config.yaml")
    if e.hat_konfiguration():
        _absatz(zeilen,
                "Diese Eintraege wertet das Werkzeug aus. Der Vorrang ist "
                "Argument vor config.yaml vor Vorgabewert - wo es ein "
                "Argument gibt, steht es dabei.", einzug="  ")
        zeilen.append("")
        for k in e.konfiguration:
            zeilen.append("  " + k.schluessel)
            zeilen.extend(umbrechen(k.bedeutung, BREITE, "      "))
            zeilen.extend(umbrechen("ohne Eintrag: " + k.vorgabe,
                                    BREITE, "      "))
            if k.argument:
                zeilen.extend(umbrechen("ueberstimmt durch: " + k.argument,
                                        BREITE, "      "))
            zeilen.extend(umbrechen("Fundstelle: " + k.beleg,
                                    BREITE, "      "))
            zeilen.append("")
    elif e.konfiguration_geprueft():
        _absatz(zeilen,
                "Geprueft: Dieses Werkzeug wertet KEINEN Eintrag aus "
                "config.yaml aus.", einzug="  ")
        zeilen.append("")
    else:
        # KEIN STILLES WEGLASSEN - dieselbe Begruendung wie bei
        # "Ausarbeitung" weiter unten.
        _absatz(zeilen,
                "Fuer dieses Werkzeug ist noch nicht erhoben, welche "
                "Eintraege aus config.yaml es auswertet (Ticket 60e4236e). "
                "Das heisst NICHT, dass es keine gibt.", einzug="  ")
        zeilen.append("")

    if e.hat_tiefe():
        t = e.tiefe
        if t.beispiele:
            zeilen.append("Beispiele")
            for bsp in t.beispiele:
                # DER AUFRUF WIRD NICHT UMBROCHEN. Eine ueber zwei Zeilen
                # verteilte Befehlszeile laesst sich nicht kopieren, und
                # genau dafuer steht sie da.
                zeilen.append("  " + bsp.aufruf)
                zeilen.extend(umbrechen(bsp.wirkung, BREITE, "      "))
                zeilen.extend(umbrechen("geprueft: " + bsp.geprueft,
                                        BREITE, "      "))
                zeilen.append("")
        if t.exit_codes:
            zeilen.append("Rueckgabewerte")
            for code, bedeutung in t.exit_codes:
                zeilen.extend(umbrechen("%d = %s" % (code, bedeutung),
                                        BREITE, "      ", "  "))
            zeilen.append("")
        if t.warnungen:
            zeilen.append("Zu beachten")
            for w in t.warnungen:
                zeilen.extend(umbrechen("- " + w, BREITE, "    ", "  "))
            zeilen.append("")
    else:
        # KEIN STILLES WEGLASSEN: dass die Tiefeninhalte fehlen, bekommt eine
        # eigene Ueberschrift. Ohne sie klebte der Satz unter dem Hinweis und
        # saehe aus wie ein Teil von ihm - und ein Grundeintrag saehe aus wie
        # ein vollstaendiger.
        zeilen.append("Ausarbeitung")
        _absatz(zeilen,
                "Beispiele, Rueckgabewerte und Warnhinweise sind fuer dieses "
                "Werkzeug noch nicht erfasst (Baustelle H, H17/H18).",
                einzug="  ")
        zeilen.append("")

    zeilen.append("-" * BREITE)
    _absatz(zeilen,
            "Vollstaendige Optionen nennt das Werkzeug selbst:", einzug="")
    zeilen.append("  " + hilfe_aufruf(e.aufruf))
    return "\n".join(zeilen)


# -----------------------------------------------------------------------------
# 3) suche
# -----------------------------------------------------------------------------

def suche_text(begriff: str) -> str:
    """
    Treffer zu einem Suchbegriff.

    EIN LEERBEFUND SAGT, WO GESUCHT WURDE. Sonst liest sich 'keine Treffer'
    als 'gibt es nicht', obwohl nur der Katalogtext durchsucht wurde und
    nicht etwa der Quelltext der Werkzeuge (Grundregel 1).
    """
    treffer = suche(begriff)
    zeilen: List[str] = []
    zeilen.append("Suche: %s" % (begriff or "(leer)"))
    zeilen.append("=" * BREITE)
    zeilen.append("")

    if not treffer:
        _absatz(zeilen,
                "Kein Treffer. Gesucht wurde in Kennung, Titel, Zweck, "
                "Aufrufform, Arbeitsbereich, Hinweis und den Unterbefehlen "
                "der %d Katalogeintraege - NICHT im Quelltext der Werkzeuge."
                % len(CLI_KATALOG), einzug="")
        vorschlag = nahetreffer(begriff)
        if vorschlag:
            zeilen.append("")
            _absatz(zeilen, "Meinten Sie: " + ", ".join(vorschlag), einzug="")
        return "\n".join(zeilen)

    for e in treffer:
        zeilen.extend(spaltenzeile(art_kurz(e.art).strip(), e.schluessel,
                                   e.titel, 28))
        zeilen.extend(umbrechen(e.zweck, BREITE, " " * 35, " " * 35))
        zeilen.append("")
    zeilen.append("-" * BREITE)
    zeilen.append("%d von %d Werkzeugen." % (len(treffer), len(CLI_KATALOG)))
    return "\n".join(zeilen)


def unbekannt_text(begriff: str) -> str:
    """Meldung fuer eine unbekannte Kennung - immer mit einem Ausweg."""
    zeilen: List[str] = []
    _absatz(zeilen, "Unbekanntes Werkzeug: %s" % begriff, einzug="")
    vorschlag = nahetreffer(begriff)
    if vorschlag:
        zeilen.append("")
        _absatz(zeilen, "Meinten Sie: " + ", ".join(vorschlag), einzug="")
    zeilen.append("")
    _absatz(zeilen,
            "Alle Werkzeuge: 'python tools/hilfe.py liste'. Volltextsuche: "
            "'python tools/hilfe.py suche <begriff>'.", einzug="")
    return "\n".join(zeilen)
