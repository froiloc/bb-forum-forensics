#!/usr/bin/env python3
# =============================================================================
# issue-tracker/literal_newline_repair.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: Zeilenumbrueche, die als ZEICHENFOLGE Backslash+n im Text gelandet
#   sind, in echte Zeilenumbrueche zurueckverwandeln - und dabei die Stellen
#   in Ruhe lassen, an denen '\n' woertlich gemeint ist.
#
# DER ANLASS (mc, 2026-08-01, zu Vorgang 651e6d84): "hat im Feld Beschreibung
#   \n und das wird nicht in <br> uebersetzt. Es wird nach wie vor als \n
#   angezeigt."
#
# DIE URSACHE LIEGT NICHT IN DER ANZEIGE, SONDERN IN DEN DATEN - UND ZWAR BEI
#   MIR. In 651e6d84 steht im Feld 'description' kein Zeilenumbruch, sondern
#   die zwei Zeichen Backslash und n als Text. Der Filter 'zeilen' aus Build
#   647 zeigt sie korrekt als das an, was sie sind. Entstanden ist das beim
#   Erzeugen einer Eingangsdatei in einer frueheren Sitzung: dort wurde in
#   einer Zeichenkette '\\n' geschrieben statt '\n'.
#
#   GEMESSEN am Bestand von Build 647: 22 von 140 Vorgaengen, 320 Vorkommen.
#   19 der 22 Vorgaenge stammen von mir, 3 von mc.
#
# WARUM NICHT MIT sed (Vorschlag mc):
#   'sed -i "s#\\n#\n#g" issues.json' - AUF EINER KOPIE AUSPROBIERT:
#       JSONDecodeError: Invalid control character at: line 347 column 130
#   Der Grund: In der DATEI steht ein echter Zeilenumbruch bereits als die
#   zwei Zeichen \ und n - das ist seine JSON-Kodierung. Das Muster trifft
#   also die SCHON RICHTIGEN Umbrueche und ersetzt sie durch ein rohes
#   Steuerzeichen; rohe Steuerzeichen sind in JSON-Zeichenketten verboten.
#   Die Datei wuchs von 5458 auf 5886 Zeilen und war danach nicht mehr
#   ladbar. Gesucht ist in der Datei die DREIzeichenfolge \\n, nicht \n.
#
# WARUM AUCH EIN RICHTIG GESCHRIEBENES GLOBALES ERSETZEN FALSCH WAERE:
#   Vorgang d2ade5dc von mc handelt VON dieser Zeichenfolge und meint sie
#   woertlich ("Dieser wird als \n gespeichert"). Ein globales Ersetzen
#   machte aus seinem Text Unsinn.
#
# DIE UNTERSCHEIDUNGSREGEL - abgelesen an den Daten, nicht erdacht:
#   Ein verlorener Umbruch KLEBT am Satz: '...PUNKTE.\n\nDER BEFUND:' - vor
#   dem Backslash steht ein Satzzeichen oder ein Buchstabe.
#   Eine woertliche Erwaehnung steht FREI im Satz: 'wird als \n gespeichert' -
#   vor dem Backslash steht ein Leerzeichen (oder der Textanfang).
#
#   Also: LEERZEICHEN ODER TEXTANFANG VOR DEM BACKSLASH -> ERWAEHNUNG,
#   alles andere -> UMBRUCH.
#
#   GEGENGEPRUEFT am gesamten Bestand von Build 647: die Regel trennt 317
#   Umbrueche von 3 Erwaehnungen, und alle drei Erwaehnungen liegen in
#   d2ade5dc - also genau dort, wo die Zeichenfolge das Thema ist.
#
#   Die Regel irrt IN DIE SICHERE RICHTUNG: ein echter Umbruch, dem ein
#   Leerzeichen vorausgeht, wird als Erwaehnung eingestuft und BLEIBT STEHEN.
#   Er wird dabei aber ausdruecklich aufgelistet - Grundregel 1.
#
# Version: v0.8.648 - Build: 648 - 2026-08-01
# =============================================================================

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backup_names import reparatur_sicherungsname
from json_safe_writer import JsonSafeWriter

#: Die Zeichenfolge, um die es geht: Backslash + kleines n, als TEXT.
LITERAL = "\\n"

#: Die Textfelder eines Vorgangs, die geprueft werden. 'title' ist bewusst
#: NICHT dabei: ein Titel hat keine Zeilenumbrueche, und die Hoechstlaenge von
#: 80 Zeichen wuerde durch eine Umwandlung auch nicht besser.
TEXTFELDER = ("description", "expected_behavior", "actual_behavior", "prerequisites")

#: Einordnung einer Fundstelle.
BEFUND_UMBRUCH = "umbruch"
BEFUND_ERWAEHNUNG = "erwaehnung"


@dataclass
class Fundstelle:
    """Eine einzelne Stelle, an der die Zeichenfolge im Text steht."""
    vorgang_id: str
    feld: str                  # 'description' oder 'update[3].comment'
    position: int
    befund: str                # BEFUND_UMBRUCH oder BEFUND_ERWAEHNUNG
    umgebung: str              # Text drumherum, fuer die Anzeige


@dataclass
class Reparaturbericht:
    fundstellen: List[Fundstelle] = field(default_factory=list)
    angewendet: bool = False
    sicherung: Optional[Path] = None
    geschrieben: Optional[Path] = None

    def nach_befund(self, befund: str) -> List[Fundstelle]:
        return [f for f in self.fundstellen if f.befund == befund]

    @property
    def umbrueche(self) -> List[Fundstelle]:
        return self.nach_befund(BEFUND_UMBRUCH)

    @property
    def erwaehnungen(self) -> List[Fundstelle]:
        return self.nach_befund(BEFUND_ERWAEHNUNG)

    @property
    def betroffene_vorgaenge(self) -> int:
        return len({f.vorgang_id for f in self.umbrueche})


def ist_erwaehnung(text: str, position: int) -> bool:
    """
    Wahr, wenn die Zeichenfolge an dieser Stelle WOERTLICH gemeint ist.

    Die Regel steht im Kopf dieser Datei und lautet in einem Satz: Vor einer
    woertlichen Erwaehnung steht ein Leerzeichen oder der Textanfang, vor
    einem verlorenen Umbruch klebt der Satz.

    Args:
        text:     der ganze Feldinhalt.
        position: Index des Backslash.
    """
    vor = text[position - 1] if position > 0 else ""
    return vor == "" or vor.isspace()


def _fundstellen(text: str) -> List[Tuple[int, bool]]:
    """Alle Positionen der Zeichenfolge mit ihrer Einordnung."""
    ergebnis = []
    suchstelle = text.find(LITERAL)
    while suchstelle != -1:
        ergebnis.append((suchstelle, ist_erwaehnung(text, suchstelle)))
        # Weiter NACH der gefundenen Stelle - sonst faende '\n\n' die zweite
        # Haelfte nicht als eigene Stelle.
        suchstelle = text.find(LITERAL, suchstelle + len(LITERAL))
    return ergebnis


def ersetze(text: str) -> Tuple[str, int, int]:
    """
    Ersetzt die Umbrueche und laesst die Erwaehnungen stehen.

    Returns:
        (neuer Text, Anzahl ersetzt, Anzahl stehengelassen)
    """
    stellen = _fundstellen(text)
    if not stellen:
        return text, 0, 0

    ergebnis = []
    letzte = 0
    ersetzt = stehen = 0
    for position, erwaehnung in stellen:
        ergebnis.append(text[letzte:position])
        if erwaehnung:
            ergebnis.append(LITERAL)
            stehen += 1
        else:
            ergebnis.append("\n")
            ersetzt += 1
        letzte = position + len(LITERAL)
    ergebnis.append(text[letzte:])
    return "".join(ergebnis), ersetzt, stehen


class LiteralNewlineRepair:
    """
    Prüft und repariert literale Backslash-n in den Texten der Vorgänge.

    Zweistufig wie RelatedIdRepair: erst 'pruefen()' - das liest nur -, dann
    'anwenden()'. Der Trockenlauf benutzt exakt denselben Code wie der
    Ernstfall; ein Trockenlauf, der einen anderen Weg nimmt, sagt nichts aus.
    """

    #: Zeichen links und rechts, die in der Anzeige mitgezeigt werden.
    UMGEBUNG = 45

    def __init__(self, ziel: Path, sicherungsverzeichnis: Optional[Path] = None):
        self.ziel = Path(ziel)
        self.sicherungsverzeichnis = (
            Path(sicherungsverzeichnis)
            if sicherungsverzeichnis
            else self.ziel.resolve().parent.parent / "backups"
        )
        self.writer = JsonSafeWriter()

    # ------------------------------------------------------------------
    # Lesen
    # ------------------------------------------------------------------

    def laden(self) -> Dict[str, Any]:
        with open(self.ziel, "r", encoding="utf-8") as f:
            daten = json.load(f)
        if not isinstance(daten, dict) or "issues" not in daten:
            raise ValueError(
                f"{self.ziel} hat nicht die erwartete Form {{'issues': [...]}}")
        return daten

    @staticmethod
    def _textquellen(vorgang: Dict[str, Any]):
        """
        Alle Textstellen eines Vorgangs als (Bezeichnung, Setter, Text).

        Der Setter ist eine kleine Funktion, damit 'anwenden' den neuen Wert
        an genau dieselbe Stelle zurueckschreiben kann, ohne dass die
        Zuordnung an zwei Orten gepflegt wird.
        """
        for feld in TEXTFELDER:
            wert = vorgang.get(feld)
            if isinstance(wert, str) and LITERAL in wert:
                def setzen(neu, _feld=feld):
                    vorgang[_feld] = neu
                yield feld, setzen, wert

        for nummer, eintrag in enumerate(vorgang.get("updates") or []):
            wert = eintrag.get("comment")
            if isinstance(wert, str) and LITERAL in wert:
                def setzen(neu, _eintrag=eintrag):
                    _eintrag["comment"] = neu
                yield f"update[{nummer}].comment", setzen, wert

    # ------------------------------------------------------------------
    # Prüfen (verändert nichts)
    # ------------------------------------------------------------------

    def pruefen(self, daten: Optional[Dict[str, Any]] = None) -> Reparaturbericht:
        if daten is None:
            daten = self.laden()

        bericht = Reparaturbericht()
        for vorgang in daten.get("issues", []):
            kennung = str(vorgang.get("id", "?"))
            for bezeichnung, _setzen, text in self._textquellen(vorgang):
                for position, erwaehnung in _fundstellen(text):
                    a = max(0, position - self.UMGEBUNG)
                    b = min(len(text), position + len(LITERAL) + self.UMGEBUNG)
                    bericht.fundstellen.append(Fundstelle(
                        vorgang_id=kennung,
                        feld=bezeichnung,
                        position=position,
                        befund=BEFUND_ERWAEHNUNG if erwaehnung else BEFUND_UMBRUCH,
                        umgebung=(text[a:position] + " «\\n» " + text[position + len(LITERAL):b]),
                    ))
        return bericht

    # ------------------------------------------------------------------
    # Anwenden (verändert die Datei)
    # ------------------------------------------------------------------

    def anwenden(self, nur_vorgang: Optional[str] = None,
                 jetzt: Optional[datetime] = None) -> Reparaturbericht:
        """
        Ersetzt die als Umbruch eingeordneten Fundstellen und schreibt.

        Reihenfolge mit Bedacht: erst lesen, dann pruefen, dann SICHERN, dann
        schreiben. Die Sicherung entsteht aus der Datei auf der Platte, nicht
        aus dem, was im Speicher steht.

        Args:
            nur_vorgang: Praefix einer Vorgangs-ID. Ist es gesetzt, wird
                         ausschliesslich dieser Vorgang angefasst - fuer den
                         Fall, dass man erst einen einzelnen ansehen will.
        """
        daten = self.laden()
        bericht = self.pruefen(daten)

        if not bericht.umbrueche:
            # Nichts zu tun heisst NICHT schreiben: ein Schreibvorgang ohne
            # Aenderung erzeugt nur eine ueberfluessige Sicherung und einen
            # Git-Diff ohne Inhalt.
            return bericht

        geaendert = False
        for vorgang in daten.get("issues", []):
            kennung = str(vorgang.get("id", "?"))
            if nur_vorgang and not kennung.startswith(nur_vorgang):
                continue
            for _bezeichnung, setzen, text in list(self._textquellen(vorgang)):
                neu, ersetzt, _stehen = ersetze(text)
                if ersetzt:
                    setzen(neu)
                    geaendert = True

        if not geaendert:
            return bericht

        bericht.sicherung = self._sichern(jetzt or datetime.now())
        bericht.geschrieben = self.writer.write(self.ziel, daten)
        bericht.angewendet = True
        return bericht

    def _sichern(self, jetzt: datetime) -> Path:
        self.sicherungsverzeichnis.mkdir(parents=True, exist_ok=True)
        pfad = self.sicherungsverzeichnis / reparatur_sicherungsname(jetzt)
        shutil.copy2(self.ziel, pfad)
        return pfad
