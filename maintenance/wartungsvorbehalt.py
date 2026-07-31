# =============================================================================
# maintenance/wartungsvorbehalt.py
# IT-Forensisches Ermittlungswerkzeug - Wartungsvorbehalt (Build 610/611)
# =============================================================================
# Zweck:
#   Das gemeinsame Bauteil, das ein Werkzeug der STUFE A vor seinem scharfen
#   Lauf aufruft. Es beantwortet eine einzige Frage - "darf das jetzt laufen?" -
#   und liefert dazu einen fertigen Text fuer die Konsole.
#
#   Grundlage: 'Vermerk_Wartungsvorbehalt_Analyse_K1_K8_v1_0.md' (Einstufung
#   von mc bestaetigt am 2026-07-31) und 'Klaerung_Wartungsvorbehalt_CLI_v0_2.md'
#   Abschnitt 4b. Vorgang: Issue da6c16d0-ef1e-4052-8eb1-526c647de613.
#
# WARUM ES DIESES BAUTEIL GIBT:
#   Fuenf Werkzeuge bauen Tabellen um, tauschen Dateien aus oder schreiben in
#   Datenbanken, die der Auswertungsdienst im Regelbetrieb geoeffnet haelt.
#   Feste Wartungsfenster gibt es nicht (Auskunft der Betriebsseite vom
#   2026-07-31); gewaehlt werden Abend-, Nacht- und Wochenendzeiten. Damit ist
#   die Wahrscheinlichkeit hoch, dass eines dieser Werkzeuge irgendwann doch
#   zur Arbeitszeit laeuft. Eine Betriebsanweisung, an die man sich abends um
#   halb elf erinnern muss, ist keine Sicherung - die Pruefung gehoert deshalb
#   in das Werkzeug.
#
# DER ABLAUF - UND DIE REIHENFOLGE, DIE DAHINTER STECKT:
#
#   1. IMMER ZUERST: die konkret betroffenen Dateien einzeln probeweise
#      exklusiv sperren (BEGIN EXCLUSIVE + sofortiges Zurueckrollen ueber
#      maintenance.cli_support.exklusiv_pruefen). Je Datei einer von DREI
#      Zustaenden: RUHIG, BELEGT, UNPRUEFBAR (siehe Sperrbefund).
#      -> Mindestens eine BELEGT: ABBRUCH unter Nennung der Datei. KEINE
#         Bestaetigungsabfrage. Dass eine Datei belegt ist, ist ein Messwert
#         und keine Ermessensfrage.
#   2. Alle ruhig, keine unpruefbar, UND ein Wartungsfenster deckt sie ab:
#      durchlaufen.
#   3. Sonst: Sachlage ausgeben, dann ein VOLLSTAENDIGES WORT abfragen. Ein
#      Tastendruck ist eine Reflexbewegung, ein getipptes Wort ist eine
#      Entscheidung.
#   4. Kein Terminal (Skript, geplante Aufgabe): IMMER Abbruch.
#
#   DIE SPERRPROBE STEHT BEWUSST VOR DER FENSTERFRAGE. Grund ist Befund 1 des
#   Vermerks: 'maintenance.py enter --ziel all' loest 'all' auf zu den
#   Datenbanken der OBERSTEN Ebene - die Fall-Datenbanken in evidence/,
#   forensic/ und assets/ sind nicht dabei. Ein gesetztes Fenster ist damit
#   KEIN Nachweis, dass eine evidence_<uid>.db ruhig ist. Das Fenster belegt
#   die ABSICHT, die Sperre belegt die RUHE. Nur die Ruhe darf entscheiden.
#
#   UND EINE UNPRUEFBARE DATEI NIMMT DEM FENSTER SEINE WIRKUNG (Build 611).
#   Befund aus dem Regressionslauf von mc zu Build 610: Auf einer
#   SCHREIBGESCHUETZTEN Datei meldet die Sperrprobe IMMER "exklusiv erhalten"
#   - auch wenn ein Leser oder sogar ein Schreiber sie haelt. Sie misst dort
#   nicht, sie ist blind. Betroffen sind genau die versiegelten
#   forensic_<uid>.db, also genau die Dateien, die
#   'forensic_index_upgrade --ausfuehren' entsiegelt und beschreibt. Solche
#   Dateien werden deshalb gar nicht erst geprobt, als UNPRUEFBAR gefuehrt
#   und benannt - und sie erzwingen die Wortabfrage auch dann, wenn ein
#   Fenster gesetzt ist. Ueber eine Datei, deren Ruhe niemand messen kann,
#   hat auch das Fenster nichts ausgesagt.
#
# WAS DIESES BAUTEIL BEWUSST NICHT HAT:
#   * KEINE Option zum Ueberspringen ('--ja', '--force'). Eine Option wandert
#     in ein Skript, und damit waere der Vorbehalt genau dort wirkungslos, wo
#     er gebraucht wird.
#   * KEINEN zweiten Versuch bei der Wortabfrage. Ein Wiederholungslauf macht
#     aus einer Entscheidung ein Geschicklichkeitsspiel. Wer sich vertippt,
#     ruft das Werkzeug erneut auf - das kostet fuenf Sekunden.
#   * KEINEN Schreibzugriff. Das Bauteil laeuft in dem Moment, in dem noch
#     nichts entschieden ist; es darf keine Spur hinterlassen. Es importiert
#     dafuer nicht einmal sqlite3 (die Sperrprobe liegt in cli_support).
#
# RUECKGABEWERT 3 - UND WARUM ES NUR EINER IST:
#   Alle drei Abbruchgruende (belegt / kein Terminal / Wort nicht erteilt)
#   liefern denselben Wert 3 mit derselben Zusicherung: es wurde NICHTS
#   geschrieben. Getrennte Werte wuerden dazu einladen, den Fall "nur das Wort
#   fehlte" im Skript automatisch zu wiederholen - und das ist genau der
#   Automatismus, den die Wortabfrage verhindern soll. Der Grund steht im
#   Text, nicht im Zahlenwert.
#
# ADRESSAT: Betriebsseite, Regel H-2 (documents/rules-help.md). Dateinamen,
#   Datenbanknamen und Aufrufe stehen so da, wie sie einzugeben sind.
# AUSGABE: reines ASCII, 78 Zeichen, keine Escape-Sequenzen - Begruendung im
#   Kopf von management/help/cli_text.py.
#
# Version: v0.8.611 - Build: 611 - 2026-07-31
# =============================================================================

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from maintenance.cli_support import exklusiv_pruefen
from maintenance.paths import MaintenancePaths
from maintenance.window_flag import WindowFlag


class WartungsvorbehaltError(Exception):
    """Das aufrufende Werkzeug hat den Vorbehalt unvollstaendig angefordert."""


#: Das Bestaetigungswort. Zwei Woerter, Grossbuchstaben, mit Leerzeichen -
#: bewusst unbequem zu tippen und durch keinen einzelnen Tastendruck
#: erreichbar.
BESTAETIGUNGSWORT = "OHNE WARTUNGSFENSTER"

#: Rueckgabewerte fuer das aufrufende Werkzeug.
RUECKGABE_LAUF = 0
RUECKGABE_VORBEHALT = 3

#: Zeilenbreite der Ausgabe (wie management/help/cli_text.BREITE).
BREITE = 78

#: Hoechstzahl namentlich aufgefuehrter Dateien je Block. Was darueber
#: hinausgeht, wird nach Befund abgezaehlt - Begruendung in _dateiblock.
LISTENGRENZE = 12

#: Die moeglichen Ausgaenge. 'wortabfrage' ist ein Zwischenstand der reinen
#: Entscheidungsfunktion und steht nie in einem fertigen Befund.
ERGEBNIS_LAUF = "lauf"
ERGEBNIS_GESPERRT = "gesperrt"
ERGEBNIS_KEIN_TERMINAL = "kein_terminal"
ERGEBNIS_ABGELEHNT = "abgelehnt"
ERGEBNIS_WORTABFRAGE = "wortabfrage"

#: Ausgaenge, die einen fertigen Befund bilden duerfen.
ERGEBNISSE: Tuple[str, ...] = (
    ERGEBNIS_LAUF, ERGEBNIS_GESPERRT, ERGEBNIS_KEIN_TERMINAL,
    ERGEBNIS_ABGELEHNT,
)

#: Die drei Zustaende der Sperrprobe je Datei (Begruendung an Sperrbefund).
ZUSTAND_RUHIG = "ruhig"
ZUSTAND_BELEGT = "belegt"
ZUSTAND_UNPRUEFBAR = "unpruefbar"
ZUSTAENDE: Tuple[str, ...] = (ZUSTAND_RUHIG, ZUSTAND_BELEGT,
                              ZUSTAND_UNPRUEFBAR)

#: Warum ueberhaupt gefragt wird. Die Abfrage sagt beides an, weil die beiden
#: Anlaesse verschiedene Sorgfalt verlangen und die Ueberschrift sonst luege.
ANLASS_KEIN_FENSTER = "kein_fenster"
ANLASS_UNPRUEFBAR = "unpruefbar"

#: Umschrift fuer Texte, die von aussen kommen. Ein Werkzeug, das
#: "Schemaaenderung" mit Umlaut uebergibt, soll nicht mitten in der Wartung
#: abstuerzen - aber auch kein Kaestchen in die Konsole schreiben.
#:
#: NEBEN DEN UMLAUTEN STEHEN HIER DIE TYPOGRAFISCHEN ZEICHEN, weil die
#: Begruendungstexte der Sperrprobe (maintenance/cli_support.py) den langen
#: Gedankenstrich verwenden - "Datei nicht vorhanden - nichts zu sperren".
#: Ohne diese Zeilen stuende dort ein Fragezeichen mitten im Satz.
_UMSCHRIFT = {
    "ä": "ae", "ö": "oe", "ü": "ue",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    "ß": "ss",
    "–": "-", "—": "-", "·": "-",
    "„": '"', "“": '"', "”": '"',
    "‚": "'", "‘": "'", "’": "'",
    "…": "...",
}


# -----------------------------------------------------------------------------
# Reine Helfer - keine Ausgabe, kein Dateisystem, kein sys.exit
# -----------------------------------------------------------------------------

def nur_ascii(text: str) -> str:
    """
    Setzt einen Fremdtext auf reines ASCII um.

    Die sieben deutschen Sonderzeichen werden umgeschrieben, alles Weitere
    wird zu '?'. Das ist eine sichtbare Ersetzung: ein Fragezeichen faellt
    beim Lesen auf, ein stillschweigend geloeschtes Zeichen nicht.
    """
    ergebnis: List[str] = []
    for zeichen in str(text or ""):
        if zeichen in _UMSCHRIFT:
            ergebnis.append(_UMSCHRIFT[zeichen])
        elif ord(zeichen) < 128:
            ergebnis.append(zeichen)
        else:
            ergebnis.append("?")
    return "".join(ergebnis)


def umbrechen(text: str, breite: int = BREITE, einzug: str = "",
              erster_einzug: Optional[str] = None) -> Tuple[str, ...]:
    """
    Bricht einen Fliesstext auf 'breite' Zeichen um.

    ZEICHENGLEICHE ZWEITSCHRIFT von management/help/cli_text.umbrechen. Die
    Verdopplung ist gewollt: dieses Bauteil laeuft in Migrationswerkzeugen,
    und ein Import aus management/help wuerde den gesamten CLI-Katalog in
    jede Migration ziehen. Damit die Verdopplung nicht auseinanderlaeuft,
    vergleicht Test WV17 beide Fassungen Zeichen fuer Zeichen - eine
    Abweichung faellt sofort auf.
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


def wort_akzeptiert(eingabe: object,
                    erwartet: str = BESTAETIGUNGSWORT) -> bool:
    """
    Prueft die Bestaetigungseingabe.

    NACHSICHTIG genau dort, wo Nachsicht nichts kostet: fuehrende und
    abschliessende Leerzeichen fallen weg, mehrfache Leerzeichen im Inneren
    werden zu einem. Beides ist ein Tippartefakt und keine Willensaeusserung.

    STRENG bei der Gross-/Kleinschreibung. Das Wort steht in der Abfrage
    ausdruecklich in Grossbuchstaben da; wer es abschreibt, trifft es. Wer es
    aus dem Gedaechtnis in Kleinbuchstaben tippt, hat es nicht gelesen - und
    genau das Lesen ist der Zweck der Abfrage.
    """
    if eingabe is None:
        return False
    return " ".join(str(eingabe).split()) == erwartet


@dataclass(frozen=True)
class Sperrbefund:
    """
    Das Ergebnis der Sperrprobe fuer EINE Datei.

    DREI ZUSTAENDE, NICHT ZWEI - und der dritte ist der wichtigste:

      RUHIG       Die Probe ist gelungen: niemand haelt die Datei. Auch eine
                  noch nicht angelegte Datei ist ruhig.
      BELEGT      Die Probe ist misslungen: jemand haelt sie.
      UNPRUEFBAR  Die Probe konnte gar nicht messen. Das ist WEDER das eine
                  NOCH das andere, und es darf nicht als eines von beiden
                  verbucht werden.

    WARUM ES DEN DRITTEN ZUSTAND GIBT (Befund aus dem Regressionslauf von mc
    zu Build 610, nachgestellt und belegt): Auf einer SCHREIBGESCHUETZTEN
    Datei meldet die Sperrprobe IMMER "exklusiv erhalten" - auch dann, wenn
    ein Leser und sogar wenn ein Schreiber sie haelt. SQLite oeffnet eine
    nicht beschreibbare Datei still nur lesend, und ein 'BEGIN EXCLUSIVE' auf
    einer nur lesenden Verbindung nimmt keine Sperre; es gelingt folgenlos.
    Die Probe ist dort also nicht streng, sondern BLIND.

    Das trifft genau die versiegelten forensic_<uid>.db - und damit genau die
    Datei, die 'forensic_index_upgrade --ausfuehren' entsiegelt und
    beschreibt. Ein "ruhig" waere dort eine Auskunft, die nichts gemessen hat.

    pfad    - die gepruefte Datei, so wie sie auf der Platte heisst.
    zustand - einer der drei Werte oben.
    grund   - der Klartext. Er steht auch dann im Befund, wenn alles ruhig
              war: eine Pruefung, deren Ergebnis man nur im Fehlerfall sieht,
              ist keine nachvollziehbare Pruefung.
    """
    pfad: str
    zustand: str
    grund: str

    def __post_init__(self) -> None:
        if not str(self.pfad).strip():
            raise WartungsvorbehaltError("Sperrbefund ohne Pfad")
        if self.zustand not in ZUSTAENDE:
            raise WartungsvorbehaltError(
                "Sperrbefund zu '%s': Zustand '%s' ist keiner der zulaessigen "
                "(%s)." % (self.pfad, self.zustand, ", ".join(ZUSTAENDE)))
        if not str(self.grund).strip():
            raise WartungsvorbehaltError(
                "Sperrbefund zu '%s' ohne Grund - ein Befund ohne Begruendung "
                "ist kein Befund." % self.pfad)

    def ist_ruhig(self) -> bool:
        return self.zustand == ZUSTAND_RUHIG

    def ist_belegt(self) -> bool:
        return self.zustand == ZUSTAND_BELEGT

    def ist_unpruefbar(self) -> bool:
        return self.zustand == ZUSTAND_UNPRUEFBAR


@dataclass(frozen=True)
class Befund:
    """
    Das Gesamtergebnis. Das aufrufende Werkzeug braucht daraus drei Dinge:
    'text' zum Ausgeben, 'erlaubt' zum Verzweigen, 'rueckgabewert' zum
    Zurueckgeben.

    'befunde' bleibt vollstaendig erhalten - auch die ruhigen Dateien. Wer den
    Lauf spaeter nachvollzieht, will wissen, WAS geprueft wurde, und nicht nur,
    was auffiel (Grundregel 1).
    """
    ergebnis: str
    erlaubt: bool
    fenster_id: Optional[str]
    befunde: Tuple[Sperrbefund, ...]
    text: str
    rueckgabewert: int

    def __post_init__(self) -> None:
        if self.ergebnis not in ERGEBNISSE:
            raise WartungsvorbehaltError(
                "Ergebnis '%s' ist keines der zulaessigen (%s)."
                % (self.ergebnis, ", ".join(ERGEBNISSE)))
        # DIE ZUSICHERUNG IST TEIL DES DATENTYPS: 'erlaubt' und
        # 'rueckgabewert' duerfen nicht auseinanderfallen. Ein Befund, der
        # den Lauf verbietet und trotzdem 0 zurueckgibt, waere die
        # gefaehrlichste aller Formen von "es hat ja funktioniert".
        erwartet = RUECKGABE_LAUF if self.erlaubt else RUECKGABE_VORBEHALT
        if self.rueckgabewert != erwartet:
            raise WartungsvorbehaltError(
                "Befund '%s': erlaubt=%s verlangt Rueckgabewert %d, nicht %d."
                % (self.ergebnis, self.erlaubt, erwartet, self.rueckgabewert))
        if self.erlaubt != (self.ergebnis == ERGEBNIS_LAUF):
            raise WartungsvorbehaltError(
                "Befund '%s': nur '%s' darf erlaubt sein."
                % (self.ergebnis, ERGEBNIS_LAUF))

    def belegte(self) -> Tuple[Sperrbefund, ...]:
        return tuple(b for b in self.befunde if b.ist_belegt())

    def unpruefbare(self) -> Tuple[Sperrbefund, ...]:
        return tuple(b for b in self.befunde if b.ist_unpruefbar())


def anlass(befunde: Sequence[Sperrbefund]) -> str:
    """Warum gefragt wird - die unpruefbare Datei ist der schwerere Anlass."""
    return (ANLASS_UNPRUEFBAR if any(b.ist_unpruefbar() for b in befunde)
            else ANLASS_KEIN_FENSTER)


def naechster_schritt(fenster_deckt_ab: bool,
                      befunde: Sequence[Sperrbefund],
                      hat_terminal: bool) -> str:
    """
    DIE ENTSCHEIDUNG - rein, ohne Ein- und Ausgabe, damit sie ohne Konsole,
    ohne Dateisystem und ohne Wartezeit pruefbar ist.

    Die Reihenfolge ist die eigentliche Aussage dieses Bauteils; ihre
    Begruendung steht im Dateikopf. Vier Abfragen, in dieser Folge:

      1. BELEGT schlaegt alles. Abbruch, keine Rueckfrage.
      2. UNPRUEFBAR nimmt dem Wartungsfenster seine Wirkung. Auch bei
         gesetztem Fenster wird gefragt - denn ueber eine Datei, deren Ruhe
         nicht gemessen werden KANN, hat das Fenster nichts ausgesagt, und
         die Sperrprobe erst recht nicht. Das ist die einzige verbleibende
         Stelle, an der noch ein Mensch hinsehen kann.
      3. Ohne Terminal wird nicht geraten.
      4. Sonst: Wortabfrage.
    """
    if any(b.ist_belegt() for b in befunde):
        return ERGEBNIS_GESPERRT
    unpruefbar = any(b.ist_unpruefbar() for b in befunde)
    if fenster_deckt_ab and not unpruefbar:
        return ERGEBNIS_LAUF
    if not hat_terminal:
        return ERGEBNIS_KEIN_TERMINAL
    return ERGEBNIS_WORTABFRAGE


def fenster_deckt(flag: Optional[WindowFlag],
                  dateien: Sequence[Path]) -> bool:
    """
    Ob ein aktives Fenster ALLE betroffenen Dateien nennt.

    'all' trifft dabei alles - obwohl 'maintenance.py enter --ziel all' beim
    Setzen nur die oberste Ebene sperrt (Befund 1). Das ist hier vertretbar,
    weil das Fenster in diesem Bauteil NICHT als Ruhenachweis dient: die Ruhe
    ist bereits gemessen, wenn diese Frage ueberhaupt gestellt wird. Das
    Fenster belegt nur, dass ein Mensch die Wartung angesagt hat - und wer
    'all' sagt, hat alles angesagt.
    """
    if flag is None:
        return False
    if not flag.ist_aktiv():
        return False
    return all(flag.betrifft(Path(p).name) for p in dateien)


# -----------------------------------------------------------------------------
# Textbausteine - ebenfalls rein: sie geben Text zurueck, sie drucken nicht
# -----------------------------------------------------------------------------

def _kopf(zeile: str) -> List[str]:
    return [nur_ascii(zeile), "=" * BREITE, ""]


def _absatz(zeilen: List[str], text: str, einzug: str = "",
            leerzeile: bool = True) -> None:
    """Ein umbrochener Absatz. 'leerzeile=False' fuer die Zeile, die eine
    Aufzaehlung ankuendigt - dazwischen gehoert keine Luecke."""
    zeilen.extend(umbrechen(nur_ascii(text), BREITE, einzug, einzug))
    if leerzeile:
        zeilen.append("")


def _anzahl(n: int) -> str:
    """'1 Datei' / '3 Dateien'. Ein '(en)' im Fliesstext liest sich wie ein
    Formular, und ein Formular liest niemand aufmerksam."""
    return "1 Datei" if n == 1 else "%d Dateien" % n


def _dateiblock(zeilen: List[str], befunde: Sequence[Sperrbefund],
                zustand: Optional[str] = None) -> None:
    """
    Die geprueften Dateien mit ihrem Grund - je Datei zwei Zeilen.

    'zustand=None' zeigt alle. Sonst nur die eines Zustands.

    BEI VIELEN DATEIEN WIRD GEKAPPT - aber nicht stillschweigend.
    'forensic_index_upgrade' fasst einen Bestand von ueber 160 Dateien an;
    eine Liste von 320 Zeilen liest niemand, und was niemand liest, wirkt
    nicht. Deshalb: die ersten LISTENGRENZE namentlich, danach eine
    Abzaehlung der uebrigen NACH BEFUND. Damit steht die Zahl da, die Gruende
    stehen da, und nur die einzelnen Namen fehlen - das ist die einzige
    Angabe, die sich aus dem Rest zurueckrechnen laesst (Grundregel 1).
    """
    gewaehlt = [b for b in befunde
                if zustand is None or b.zustand == zustand]
    for b in gewaehlt[:LISTENGRENZE]:
        zeilen.append("  " + nur_ascii(b.pfad))
        zeilen.extend(umbrechen(nur_ascii(b.grund), BREITE, "      ", "      "))
    rest = gewaehlt[LISTENGRENZE:]
    if rest:
        zeilen.append("  ... und %d weitere:" % len(rest))
        gezaehlt: dict = {}
        for b in rest:
            gezaehlt[b.grund] = gezaehlt.get(b.grund, 0) + 1
        for grund, anzahl in sorted(gezaehlt.items(), key=lambda kv: -kv[1]):
            zeilen.extend(umbrechen("%dx %s" % (anzahl, nur_ascii(grund)),
                                    BREITE, "          ", "      "))
    zeilen.append("")


def _unpruefbar_block(z: List[str], befunde: Sequence[Sperrbefund]) -> bool:
    """
    Der Abschnitt zu den Dateien, deren Ruhe nicht MESSBAR war.

    Er steht in jedem Text, in dem er vorkommen kann, und er sagt beim Namen,
    was fehlt: nicht "unauffaellig", sondern "nicht gemessen". Rueckgabe sagt
    dem Aufrufer, ob es etwas zu berichten gab.
    """
    offen = [b for b in befunde if b.ist_unpruefbar()]
    if not offen:
        return False
    _absatz(z, "NICHT PRUEFBAR - die Ruhe dieser Dateien konnte nicht "
               "gemessen werden:", leerzeile=False)
    _dateiblock(z, befunde, zustand=ZUSTAND_UNPRUEFBAR)
    _absatz(z, "Auf einer schreibgeschuetzten Datei gelingt die Sperrprobe "
               "IMMER - auch dann, wenn jemand die Datei geoeffnet haelt. "
               "SQLite oeffnet eine nicht beschreibbare Datei still nur "
               "lesend, und eine nur lesende Verbindung nimmt keine Sperre. "
               "Ein 'ruhig' waere hier also keine Auskunft, sondern eine "
               "Vermutung - deshalb steht die Datei hier und nicht oben.")
    _absatz(z, "Was das bedeutet: Ob ein Auswertungsdienst diese Datei gerade "
               "liest, laesst sich von hier aus NICHT feststellen. Wer "
               "fortfaehrt, entscheidet ohne diesen Messwert.")
    return True


def text_gesperrt(werkzeug: str, befunde: Sequence[Sperrbefund]) -> str:
    """Abbruch, weil mindestens eine Datei belegt ist."""
    z = _kopf("WARTUNGSVORBEHALT - ABBRUCH: der Bestand ist nicht ruhig")
    _absatz(z, "Das Werkzeug '%s' wurde NICHT ausgefuehrt. Es wurde nichts "
               "geschrieben, nichts geloescht und nichts umbenannt."
               % nur_ascii(werkzeug))
    _absatz(z, "Belegt:", leerzeile=False)
    _dateiblock(z, befunde, zustand=ZUSTAND_BELEGT)
    _absatz(z, "Wer die Datei haelt, ist von hier aus nicht erkennbar. In "
               "Frage kommen der Auswertungsdienst eines Falls, der "
               "Verwaltungsdienst und eine offene Konsole.")
    _absatz(z, "Naechster Schritt: den haltenden Dienst beenden und den Aufruf "
               "wiederholen. Eine Bestaetigungsabfrage gibt es an dieser "
               "Stelle bewusst NICHT - dass eine Datei belegt ist, ist ein "
               "Messwert und keine Ermessensfrage.")
    _unpruefbar_block(z, befunde)
    _absatz(z, "Vollstaendig geprueft (%s):" % _anzahl(len(befunde)),
            leerzeile=False)
    _dateiblock(z, befunde)
    return "\n".join(z).rstrip() + "\n"


def text_frage(werkzeug: str, was_geschieht: str,
               befunde: Sequence[Sperrbefund]) -> str:
    """
    Die Sachlage VOR der Wortabfrage. Sie wird ausgegeben, nicht gespeichert.

    DIE UEBERSCHRIFT RICHTET SICH NACH DEM ANLASS. Bei einer unpruefbaren
    Datei zu schreiben "es ist kein Wartungsfenster gesetzt" waere schlicht
    falsch - es kann eines gesetzt sein, und trotzdem wird gefragt.
    """
    unpruefbar = anlass(befunde) == ANLASS_UNPRUEFBAR
    z = _kopf("WARTUNGSVORBEHALT - die Ruhe des Bestandes ist nicht belegt"
              if unpruefbar
              else "WARTUNGSVORBEHALT - es ist kein Wartungsfenster gesetzt")
    z.append("Werkzeug:  " + nur_ascii(werkzeug))
    z.append("")
    _absatz(z, "Vorhaben: " + nur_ascii(was_geschieht))
    # DIE RUHIGEN UND DIE UNPRUEFBAREN STEHEN GETRENNT. Eine Datei in beiden
    # Listen zu fuehren waere doppelt gelesener Text, und die Trennung ist
    # gerade der Punkt: das eine ist gemessen, das andere nicht.
    if any(b.ist_ruhig() for b in befunde):
        _absatz(z, "Geprobt und ruhig - niemand haelt diese Dateien:",
                leerzeile=False)
        _dateiblock(z, befunde, zustand=ZUSTAND_RUHIG)
    hatte_unpruefbare = _unpruefbar_block(z, befunde)
    if not hatte_unpruefbare:
        _absatz(z, "Diese Pruefung ist eine MOMENTAUFNAHME. Sie belegt, dass "
                   "in dieser Sekunde niemand die Dateien haelt - nicht, dass "
                   "in der naechsten Sekunde niemand einen Dienst startet. Ein "
                   "waehrend des Laufs startender Dienst kann den Bestand "
                   "beschaedigen.")
    _absatz(z, "Zum Fortfahren bitte das folgende Wort eingeben, genau so, in "
               "Grossbuchstaben und mit dem Leerzeichen:")
    z.append("    " + BESTAETIGUNGSWORT)
    z.append("")
    _absatz(z, "Jede andere Eingabe bricht ab. Es gibt nur einen Versuch.")
    return "\n".join(z).rstrip() + "\n"


def text_kein_terminal(werkzeug: str, befunde: Sequence[Sperrbefund]) -> str:
    """Abbruch, weil keine Bestaetigung abgefragt werden kann."""
    z = _kopf("WARTUNGSVORBEHALT - ABBRUCH: keine Bestaetigung moeglich")
    unpruefbar = anlass(befunde) == ANLASS_UNPRUEFBAR
    _absatz(z, "Das Werkzeug '%s' wurde NICHT ausgefuehrt. Es wurde nichts "
               "geschrieben." % nur_ascii(werkzeug))
    if unpruefbar:
        _absatz(z, "Die Ruhe mindestens einer betroffenen Datei laesst sich "
                   "nicht messen, und die Standardeingabe ist kein Terminal - "
                   "die Bestaetigung laesst sich also nicht abfragen. Ein "
                   "Wartungsfenster hilft hier NICHT weiter: es sagt ueber "
                   "eine unmessbare Datei ebenso wenig aus wie die "
                   "Sperrprobe. Dieser Aufruf braucht einen Menschen an der "
                   "Konsole.")
    else:
        _absatz(z, "Es ist kein Wartungsfenster gesetzt, das die betroffenen "
                   "Dateien abdeckt, und die Standardeingabe ist kein "
                   "Terminal - die Bestaetigung laesst sich also nicht "
                   "abfragen. Das ist der Regelfall bei einem Aufruf aus "
                   "einem Skript oder einer geplanten Aufgabe.")
        _absatz(z, "Naechster Schritt: ein Wartungsfenster setzen und den "
                   "Aufruf wiederholen.")
        z.append('    python tools/maintenance.py enter --ziel <ziel> '
                 '--grund "<grund>"')
        z.append("")
    _absatz(z, "Die Bestaetigung von Hand laesst sich bewusst NICHT ueber eine "
               "Option abkuerzen. Eine solche Option wandert in ein Skript, "
               "und damit waere der Vorbehalt genau dort wirkungslos, wo er "
               "gebraucht wird.")
    _unpruefbar_block(z, befunde)
    _absatz(z, "Vollstaendig geprueft (%s):" % _anzahl(len(befunde)),
            leerzeile=False)
    _dateiblock(z, befunde)
    return "\n".join(z).rstrip() + "\n"


def text_abgelehnt(werkzeug: str) -> str:
    """Abbruch, weil das Wort nicht (richtig) eingegeben wurde."""
    z = _kopf("WARTUNGSVORBEHALT - ABBRUCH: keine Bestaetigung erteilt")
    _absatz(z, "Das Werkzeug '%s' wurde NICHT ausgefuehrt. Es wurde nichts "
               "geschrieben." % nur_ascii(werkzeug))
    _absatz(z, "Die Eingabe stimmte nicht mit dem verlangten Wort ueberein. "
               "Wenn das ein Tippfehler war: den Aufruf einfach wiederholen. "
               "Ein zweiter Versuch innerhalb desselben Laufs ist bewusst "
               "nicht vorgesehen.")
    return "\n".join(z).rstrip() + "\n"


def text_lauf(werkzeug: str, fenster_id: Optional[str],
              befunde: Sequence[Sperrbefund]) -> str:
    """Freigabe. Kurz - hier wartet jemand darauf, dass es losgeht."""
    z: List[str] = []
    offen = [b for b in befunde if b.ist_unpruefbar()]
    if fenster_id:
        _absatz(z, "Wartungsvorbehalt: Fenster %s ist aktiv und deckt die "
                   "betroffenen Dateien ab; die Sperrprobe war bei allen "
                   "ruhig (%s). Der Lauf von '%s' ist freigegeben."
                   % (nur_ascii(fenster_id), _anzahl(len(befunde)),
                      nur_ascii(werkzeug)))
    else:
        _absatz(z, "Wartungsvorbehalt: OHNE Wartungsfenster, auf ausdrueckliche "
                   "Bestaetigung. Der Lauf von '%s' ist freigegeben (%s "
                   "geprueft)." % (nur_ascii(werkzeug), _anzahl(len(befunde))))
    if offen:
        # DIE FREIGABE VERSCHWEIGT NICHT, WORAUF SIE SICH NICHT STUETZT.
        # Wer diese Zeile spaeter im Protokoll liest, soll sehen, dass hier
        # eine Entscheidung getroffen und nicht ein Messwert abgelesen wurde.
        _absatz(z, "Vermerk: bei %s war die Ruhe NICHT messbar "
                   "(schreibgeschuetzt). Die Freigabe stuetzt sich insoweit "
                   "auf die Entscheidung der aufrufenden Person und nicht auf "
                   "eine Messung: %s"
                   % (_anzahl(len(offen)),
                      ", ".join(nur_ascii(b.pfad) for b in offen)))
    return "\n".join(z).rstrip() + "\n"


# -----------------------------------------------------------------------------
# Die Aussenwelt - Dateisystem, Konsole
# -----------------------------------------------------------------------------

def hat_terminal(strom=None) -> bool:
    """
    Ob eine Bestaetigung ueberhaupt abgefragt werden kann.

    Massgeblich ist die STANDARDEINGABE, nicht die Ausgabe. Wer die Ausgabe in
    eine Datei umleitet, will trotzdem gefragt werden. Wer die Eingabe aus
    einer Datei oder einer Pipe speist, darf NICHT gefragt werden - sonst
    genuegte ein 'echo "OHNE WARTUNGSFENSTER" | python ...', um den Vorbehalt
    zu umgehen, und er waere eine Formalie.
    """
    strom = strom if strom is not None else sys.stdin
    try:
        return bool(strom.isatty())
    except Exception:            # geschlossener oder ersetzter Strom
        return False


def ist_versiegelt(pfad) -> bool:
    """
    Ob eine vorhandene Datei fuer den ausfuehrenden Benutzer NICHT beschreibbar
    ist - und die Sperrprobe damit blind waere.

    WARUM DIESE FRAGE VOR DER SPERRPROBE STEHT: siehe Sperrbefund. Auf einer
    nicht beschreibbaren Datei gelingt 'BEGIN EXCLUSIVE' folgenlos, weil
    SQLite die Verbindung still auf nur-lesend zurueckstuft. Die Probe meldet
    dann "exklusiv erhalten", obwohl sie nichts gemessen hat.

    os.access ist hier das richtige Mittel und nicht ein Schreibversuch: Ein
    Schreibversuch wuerde die Datei anfassen, und dieses Bauteil fasst nichts
    an. Unter Windows bildet os.access das Schreibschutz-Attribut ab, unter
    Linux die Rechtebits - und fuer 'root' liefert es True, was ebenfalls
    richtig ist: root kann tatsaechlich schreiben, dort MISST die Probe.

    NICHT ERFASST ist der Fall 'Datei beschreibbar, Verzeichnis nicht'. Dort
    scheitert die Probe am Journal und meldet 'nicht pruefbar' - das fuehrt
    zu ZUSTAND_BELEGT, also zum Abbruch mit Nennung. Ein Fehlalarm, aber ein
    benannter und der vorsichtigere von beiden.
    """
    p = Path(pfad)
    return p.exists() and not os.access(p, os.W_OK)


def sperren_pruefen(dateien: Sequence[Path],
                    timeout_s: float = 2.0) -> Tuple[Sperrbefund, ...]:
    """
    Prueft ALLE uebergebenen Dateien - auch nach dem ersten Fund.

    Ein Abbruch beim ersten belegten Pfad waere bequemer und waere falsch: die
    aufrufende Person soll in EINEM Durchgang sehen, was alles im Weg steht,
    und nicht nach jedem Beenden eines Dienstes erneut anlaufen (Grundregel 1).

    Eine schreibgeschuetzte Datei wird GAR NICHT ERST geprobt und als
    UNPRUEFBAR gefuehrt - eine Probe, deren Ergebnis feststeht, ist keine.
    """
    befunde: List[Sperrbefund] = []
    for pfad in dateien:
        if ist_versiegelt(pfad):
            befunde.append(Sperrbefund(
                pfad=str(pfad), zustand=ZUSTAND_UNPRUEFBAR,
                grund="schreibgeschuetzt - die Sperrprobe kann hier nicht "
                      "messen, ob jemand die Datei geoeffnet haelt"))
            continue
        ok, grund = exklusiv_pruefen(pfad, timeout_s=timeout_s)
        befunde.append(Sperrbefund(
            pfad=str(pfad),
            zustand=ZUSTAND_RUHIG if ok else ZUSTAND_BELEGT,
            grund=grund))
    return tuple(befunde)


def datenwurzel(start, tiefe: int = 4) -> Path:
    """
    Sucht von 'start' aufwaerts das Verzeichnis, in dem '_maintenance' liegt.

    WARUM DAS NOETIG IST: Die fuenf Werkzeuge der Stufe A bekommen ganz
    verschiedene Pfade genannt - einmal die coordinator.db, einmal das
    Datenverzeichnis, einmal 'data/forensic'. Das Wartungsfenster liegt aber
    immer an derselben Stelle. Jedes Werkzeug einzeln raten zu lassen, wo die
    Wurzel liegt, waere fuenfmal dieselbe Annahme an fuenf Stellen - und beim
    ersten abweichenden Aufbau vier stille Fehlgriffe.

    Gefunden wird das ERSTE Verzeichnis auf dem Weg nach oben, das
    '_maintenance' enthaelt. Wird keines gefunden, gilt der Ausgangspunkt.
    Das ist der richtige Rueckfall: dann gibt es dort kein Fenster, und der
    Vorbehalt fragt nach - er laesst nicht etwa durch.
    """
    p = Path(start)
    if p.is_file():
        p = p.parent
    for _ in range(max(0, int(tiefe)) + 1):
        if (p / MaintenancePaths.WURZEL_NAME).is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    return Path(start).parent if Path(start).is_file() else Path(start)


def aktives_fenster(data_dir) -> Optional[WindowFlag]:
    """Das aktive Wartungsfenster - oder None, wenn keines gesetzt/gueltig ist."""
    return WindowFlag.aktives_fenster(MaintenancePaths(Path(data_dir)))


def _vereinheitlichen(dateien: Sequence) -> Tuple[Path, ...]:
    """
    Doppelte Pfade fallen weg, die Reihenfolge des Aufrufers bleibt.

    Ein Werkzeug, das dieselbe Datei zweimal nennt (etwa weil zwei Migrationen
    sie anfassen), soll sie nicht zweimal sperren und nicht zweimal im Bericht
    stehen haben.
    """
    gesehen = {}
    for p in dateien:
        pfad = Path(p)
        gesehen.setdefault(str(pfad), pfad)
    return tuple(gesehen.values())


def wartungsvorbehalt(data_dir,
                      dateien: Sequence,
                      *,
                      werkzeug: str,
                      was_geschieht: str,
                      timeout_s: float = 2.0,
                      eingabe: Optional[Callable[[str], str]] = None,
                      ausgabe: Optional[Callable[[str], None]] = None,
                      terminal: Optional[bool] = None) -> Befund:
    """
    DER EINSTIEG FUER EIN STUFE-A-WERKZEUG.

    Aufrufmuster im Werkzeug (drei Zeilen, mehr soll es nicht sein):

        befund = wartungsvorbehalt(data_dir, betroffene, werkzeug="migrate",
                                   was_geschieht="baut Tabellen der "
                                                 "coordinator.db um")
        print(befund.text)
        if not befund.erlaubt:
            return befund.rueckgabewert

    data_dir      - das geteilte Datenverzeichnis (dort liegt _maintenance/).
    dateien       - die KONKRET betroffenen Datenbankdateien. Nicht die
                    Fenster-Ziele: die Sperrprobe braucht Pfade.
    werkzeug      - Kennung, wie sie im Werkzeugkatalog steht.
    was_geschieht - ein Satz in der Sprache der Betriebsseite: was wird
                    geaendert, in welcher Datenbank. Er steht in der Abfrage
                    und ist das, was die Person vor der Entscheidung liest.
    eingabe/ausgabe/terminal - nur fuer die Tests; im Betrieb input/print/tty.

    Der Frage-Text wird ueber 'ausgabe' ausgegeben, BEVOR gefragt wird; er
    steht nicht noch einmal in Befund.text. Sonst laese man ihn zweimal.
    """
    if not str(werkzeug or "").strip():
        raise WartungsvorbehaltError("wartungsvorbehalt: 'werkzeug' fehlt.")
    if not str(was_geschieht or "").strip():
        raise WartungsvorbehaltError(
            "wartungsvorbehalt: 'was_geschieht' fehlt. Ohne diesen Satz "
            "entscheidet die aufgeforderte Person ueber etwas, das ihr "
            "niemand gesagt hat.")
    pfade = _vereinheitlichen(dateien)
    if not pfade:
        # EIN STUFE-A-WERKZEUG OHNE BETROFFENE DATEI IST EIN WIDERSPRUCH.
        # Der Fehler faellt beim ersten Aufruf auf und nicht erst dann, wenn
        # eine ungeprueft gebliebene Datei beschaedigt ist.
        raise WartungsvorbehaltError(
            "wartungsvorbehalt: keine betroffene Datei genannt. Ein Werkzeug "
            "der Stufe A, das keine Datei anfasst, ist keines der Stufe A.")

    eingabe = eingabe if eingabe is not None else input
    ausgabe = ausgabe if ausgabe is not None else print
    am_terminal = hat_terminal() if terminal is None else bool(terminal)

    befunde = sperren_pruefen(pfade, timeout_s=timeout_s)
    flag = aktives_fenster(data_dir)
    deckt = fenster_deckt(flag, pfade)

    schritt = naechster_schritt(deckt, befunde, am_terminal)

    if schritt == ERGEBNIS_GESPERRT:
        return Befund(ergebnis=ERGEBNIS_GESPERRT, erlaubt=False,
                      fenster_id=(flag.window_id if flag else None),
                      befunde=befunde, text=text_gesperrt(werkzeug, befunde),
                      rueckgabewert=RUECKGABE_VORBEHALT)

    if schritt == ERGEBNIS_LAUF:
        fid = flag.window_id if flag else None
        return Befund(ergebnis=ERGEBNIS_LAUF, erlaubt=True, fenster_id=fid,
                      befunde=befunde, text=text_lauf(werkzeug, fid, befunde),
                      rueckgabewert=RUECKGABE_LAUF)

    if schritt == ERGEBNIS_KEIN_TERMINAL:
        return Befund(ergebnis=ERGEBNIS_KEIN_TERMINAL, erlaubt=False,
                      fenster_id=None, befunde=befunde,
                      text=text_kein_terminal(werkzeug, befunde),
                      rueckgabewert=RUECKGABE_VORBEHALT)

    # ERGEBNIS_WORTABFRAGE: erst die Sachlage, dann die Frage. Ein Versuch.
    ausgabe(text_frage(werkzeug, was_geschieht, befunde))
    try:
        antwort = eingabe("Eingabe: ")
    except (EOFError, KeyboardInterrupt):
        # ABGEBROCHENE EINGABE IST KEINE BESTAETIGUNG. Strg-C waehrend der
        # Abfrage darf nicht als Fehler durchschlagen, sondern muss dasselbe
        # bedeuten wie ein leerer Text: nein.
        antwort = ""

    if wort_akzeptiert(antwort):
        return Befund(ergebnis=ERGEBNIS_LAUF, erlaubt=True, fenster_id=None,
                      befunde=befunde, text=text_lauf(werkzeug, None, befunde),
                      rueckgabewert=RUECKGABE_LAUF)

    return Befund(ergebnis=ERGEBNIS_ABGELEHNT, erlaubt=False, fenster_id=None,
                  befunde=befunde, text=text_abgelehnt(werkzeug),
                  rueckgabewert=RUECKGABE_VORBEHALT)
