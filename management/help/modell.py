# =============================================================================
# management/help/modell.py
# IT-Forensisches Ermittlungswerkzeug - Baustelle H: Hilfesysteme (H1)
# =============================================================================
# Zweck:
#   Die Datenklassen des Hilfe-Registers. Reine, eingefrorene Datentraeger
#   (frozen dataclasses) nach dem Vorbild von KpiDefinition in
#   management/stats/glossary.py - kein Verhalten ausser Ableitungen, die
#   ohne Seiteneffekt aus den eigenen Feldern folgen.
#
#   WARUM FROZEN (gesicherte Erkenntnis): Hilfetexte sind Auslieferungs-
#   bestand. Ein Registereintrag, den irgendein Codepfad zur Laufzeit aendern
#   koennte, waere in einem forensischen Werkzeug nicht mehr belegbar - der
#   gedruckte Text muesste nicht mehr dem ausgelieferten entsprechen. Frozen
#   schliesst das aus.
#
#   WARUM DREI TEXTARTEN UND NICHT EINE (Konzept §2.1): Ein Popup-Satz taugt
#   nicht als Handbuchkapitel, und ein Handbuchkapitel erschlaegt ein Popup.
#   Die Arten werden getrennt verfasst und ueber Schluessel verknuepft.
#
# Version: v0.8.588 - Build: 588 - 2026-07-31
# =============================================================================

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# Erlaubte Form eines Ankers. Bewusst eng: der Anker landet in einer URL
# (/help#<sicht>-<anker>) und soll ohne Kodierung lesbar bleiben.
ANKER_MUSTER = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")

# Erlaubte Form EINES ABSCHNITTS eines Kontextschluessels.
#
# BUILD 592: ZEICHENGLEICH mit HILFE_MUSTER in cockpit_tablekit.js:584
# (`^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`, dort je Abschnitt). Das ist keine
# Bequemlichkeit, sondern Notwendigkeit: Seit Build 548 setzt das gemeinsame
# Tabellen-Werkzeug Anker der Form '<praefix>.<bereich>.<name>' selbst - waere
# unsere Form auch nur geringfuegig enger, gaebe es Anker im Browser, fuer die
# das Register gar keinen Schluessel BILDEN koennte. Der Paritaetstest kann
# solche Faelle nur melden, wenn beide Seiten dieselbe Form kennen.
SCHLUESSEL_ABSCHNITT = re.compile(r"^[a-z][a-z0-9_]*$")


def schluessel_gueltig(schluessel: str) -> bool:
    """
    Ein Kontextschluessel besteht aus mindestens ZWEI Abschnitten, getrennt
    durch Punkte: '<praefix>.<name>' oder '<praefix>.<bereich>.<name>'.
    Reine Funktion (auch von den Tests benutzt).
    """
    if not isinstance(schluessel, str):
        return False
    teile = schluessel.split(".")
    if len(teile) < 2:
        return False
    return all(SCHLUESSEL_ABSCHNITT.match(t) for t in teile)

# Die Pflichtgliederung jedes Sichtkapitels (Konzept §2.3). Wiedererkennung
# ist in einem Werkzeug mit 43 Sichten die halbe Hilfe: Wer einmal gelernt
# hat, dass "Grenzen & Zusicherungen" das fuenfte Kapitel ist, findet es in
# jeder Sicht sofort wieder.
#
# 'aufbau' darf zusaetzliche, frei benannte Unterabschnitte NACH sich haben -
# dort haengen die Anker, auf die die Kontexthilfe punktgenau verweist.
PFLICHT_ANKER: Tuple[str, ...] = (
    "zweck",     # 1. Zweck & Motivation
    "rechte",    # 2. Rechtelage
    "aufbau",    # 3. Aufbau der Sicht
    "ablaeufe",  # 4. Arbeitsablaeufe
    "grenzen",   # 5. Grenzen & Zusicherungen  (PFLICHT, auch wenn kurz)
    "verweise",  # 6. Querverweise
)

PFLICHT_TITEL: Dict[str, str] = {
    "zweck": "Zweck und Motivation",
    "rechte": "Rechtelage",
    "aufbau": "Aufbau der Sicht",
    "ablaeufe": "Arbeitsabläufe",
    "grenzen": "Grenzen und Zusicherungen",
    "verweise": "Querverweise",
}


class ModellError(Exception):
    """Ein Registereintrag ist formal fehlerhaft."""


@dataclass(frozen=True)
class Abschnitt:
    """
    Ein Abschnitt eines Vollhilfe-Kapitels mit eigenem Anker.

    anker    - eindeutig INNERHALB des Kapitels; bildet mit der Sicht-ID die
               Sprungmarke '<sicht>-<anker>' im Hilfefenster.
    absaetze - Fliesstext. Jeder Eintrag wird als eigener Absatz gerendert.
    liste    - optionale Aufzaehlung; bei 'ablaeufe' die nummerierten Schritte.
    geordnet - True -> die Liste wird nummeriert (Arbeitsschritte), sonst
               als Aufzaehlung gesetzt.
    """
    anker: str
    titel: str
    absaetze: Tuple[str, ...] = ()
    liste: Tuple[str, ...] = ()
    geordnet: bool = False

    def __post_init__(self) -> None:
        if not ANKER_MUSTER.match(self.anker):
            raise ModellError(
                "Unzulaessiger Anker '%s' (erlaubt: kleinbuchstaben, ziffern, "
                "unterstrich)" % self.anker)
        if not self.titel.strip():
            raise ModellError("Abschnitt '%s' ohne Titel" % self.anker)
        if not self.absaetze and not self.liste:
            raise ModellError(
                "Abschnitt '%s' ist leer - ein leerer Abschnitt ist eine "
                "stille Luecke (Grundregel 1)" % self.anker)


@dataclass(frozen=True)
class Kontexthilfe:
    """
    Ein Kontexthilfe-Eintrag: die Antwort auf "Was ist das hier?".

    schluessel - '<sicht>.<name>'. Genau dieser Wert steht LITERAL im
                 data-hilfe-Attribut des Elements (Konvention aus Konzept
                 §4.2a; nie berechnet, damit ein Greptest beide Seiten
                 abgleichen kann).
    text       - 1 bis 4 Saetze. Der erste Satz muss allein tragfaehig sein.
    verweis    - optional '<sicht>#<anker>'. Nur setzen, wenn das Kapitel
                 wirklich mehr sagt als das Popup (Konzept §2.2 Punkt 5).
    """
    schluessel: str
    titel: str
    text: str
    verweis: Optional[str] = None

    def __post_init__(self) -> None:
        if not schluessel_gueltig(self.schluessel):
            raise ModellError(
                "Unzulaessiger Kontextschluessel '%s' - erwartet werden "
                "mindestens zwei Abschnitte der Form <praefix>.<name> bzw. "
                "<praefix>.<bereich>.<name>, je Abschnitt Kleinbuchstaben, "
                "Ziffern und Unterstrich, beginnend mit einem Buchstaben."
                % self.schluessel)
        if not self.text.strip():
            raise ModellError(
                "Kontexthilfe '%s' ohne Text" % self.schluessel)
        if self.verweis is not None and "#" not in self.verweis:
            raise ModellError(
                "Verweis '%s' hat nicht die Form <sicht>#<anker>"
                % self.verweis)

    @property
    def praefix(self) -> str:
        """Der erste Abschnitt - der ANKERPRAEFIX, nicht zwingend die Sicht."""
        return self.schluessel.split(".", 1)[0]

    # Rueckwaertsvertraegliches Alias. Bis Build 591 war der erste Abschnitt
    # immer die Sicht-ID; seit 592 kann er auch ein Ankerpraefix sein
    # (z. B. 'overview' fuer die Sicht 'faelle'). Der Name bleibt, damit
    # bestehende Aufrufer nicht brechen - die Bedeutung steht hier.
    @property
    def sicht(self) -> str:
        return self.praefix


@dataclass(frozen=True)
class Sichthilfe:
    """
    Das Vollhilfe-Kapitel einer Sicht samt ihrer Kontexthilfe-Eintraege.

    recht_klartext - die im Kapitelkopf PROMINENT genannte Rechtelage (E1:
                     "Das jeweils noetige Recht wird im Kapitelkopf prominent
                     benannt"). Bewusst Klartext und keine Ableitung aus dem
                     Katalog: der Scope ('alle'/'eigene') bedeutet je Sicht
                     etwas anderes, und genau das soll dort stehen.
    stand          - Buildnummer der letzten Redaktion. Die Vollhilfe zeigt
                     sie je Kapitel an; Veralterung wird damit wenigstens
                     SICHTBAR statt unsichtbar (Konzept §4.2).
    """
    sicht: str
    titel: str
    recht_klartext: str
    abschnitte: Tuple[Abschnitt, ...]
    kontext: Tuple[Kontexthilfe, ...] = ()
    stand: int = 0
    anker_praefixe: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not ANKER_MUSTER.match(self.sicht):
            raise ModellError("Unzulaessige Sicht-ID '%s'" % self.sicht)
        if not self.abschnitte:
            raise ModellError("Kapitel '%s' ohne Abschnitte" % self.sicht)
        anker = [a.anker for a in self.abschnitte]
        doppelt = sorted({a for a in anker if anker.count(a) > 1})
        if doppelt:
            raise ModellError(
                "Kapitel '%s': doppelte Anker %s"
                % (self.sicht, ", ".join(doppelt)))
        fehlend = [p for p in PFLICHT_ANKER if p not in anker]
        if fehlend:
            raise ModellError(
                "Kapitel '%s': Pflichtabschnitte fehlen: %s (Gliederung nach "
                "Konzept §2.3)" % (self.sicht, ", ".join(fehlend)))
        erlaubt = set(self.praefixe())
        fremd = [k.schluessel for k in self.kontext if k.praefix not in erlaubt]
        if fremd:
            raise ModellError(
                "Kapitel '%s': Kontextschluessel mit fremdem Praefix: %s "
                "(erlaubt: %s)"
                % (self.sicht, ", ".join(fremd), ", ".join(sorted(erlaubt))))
        schluessel = [k.schluessel for k in self.kontext]
        doppelt_k = sorted({s for s in schluessel if schluessel.count(s) > 1})
        if doppelt_k:
            raise ModellError(
                "Kapitel '%s': doppelte Kontextschluessel: %s"
                % (self.sicht, ", ".join(doppelt_k)))

    def praefixe(self) -> Tuple[str, ...]:
        """
        Die Ankerpraefixe, die zu diesem Kapitel gehoeren.

        BUILD 592 - WARUM ES DIESES FELD BRAUCHT (Befund, nicht Wunsch):
        Seit Build 548 setzt das gemeinsame Tabellen-Werkzeug die Anker der
        Spaltenkoepfe und Bedienelemente SELBST, und es benutzt dafuer den
        Namen, unter dem die Tabelle dort gefuehrt wird - nicht die Sicht-ID
        des VIEW_CATALOG. Die Fall-Uebersicht (Sicht 'faelle') traegt deshalb
        Anker mit dem Praefix 'overview'; die Rechte-Sicht 'policy' fuehrt
        sogar ZWEI Tabellen ('policy_grants' und 'policy_assign').
        Diese Namen im Bestand umzubenennen waere ein Eingriff in fuenfzehn
        laufende Sichten fuer einen rein kosmetischen Gewinn. Stattdessen
        nennt das Kapitel seine Praefixe - und anker_katalog.py haelt fest,
        welcher Praefix zu welcher Sicht gehoert.
        """
        return self.anker_praefixe or (self.sicht,)

    def anker(self) -> Tuple[str, ...]:
        return tuple(a.anker for a in self.abschnitte)

    def abschnitt(self, anker: str) -> Optional[Abschnitt]:
        for a in self.abschnitte:
            if a.anker == anker:
                return a
        return None


@dataclass(frozen=True)
class HilfeRegister:
    """
    Der Gesamtbestand: alle vorhandenen Sichtkapitel plus die Kontexthilfe der
    Shell.

    BEWUSST OHNE die Fehlliste als Feld: die Fehlliste ist keine gepflegte
    Angabe, sondern eine ABLEITUNG (Katalog minus vorhandene Kapitel). Waere
    sie ein Feld, koennte sie luegen - abgeleitet kann sie das nicht.

    shell (Build 591 / H4) - Kontexthilfe fuer die Bedienelemente, die in
    JEDER Sicht an derselben Stelle stehen (Kopfzeile, Navigation, Banner).
    Sie gehoeren zu keiner Sicht und werden jeder Kontext-Antwort beigelegt;
    die Begruendung steht in management/help/inhalt/shell.py.
    """
    sichten: Tuple[Sichthilfe, ...] = ()
    shell: Tuple[Kontexthilfe, ...] = ()

    def __post_init__(self) -> None:
        ids = [s.sicht for s in self.sichten]
        doppelt = sorted({i for i in ids if ids.count(i) > 1})
        if doppelt:
            raise ModellError(
                "Doppelte Kapitel im Register: %s" % ", ".join(doppelt))
        schluessel = [k.schluessel for k in self.shell]
        doppelt_s = sorted({s for s in schluessel if schluessel.count(s) > 1})
        if doppelt_s:
            raise ModellError(
                "Doppelte Shell-Schluessel: %s" % ", ".join(doppelt_s))

    def ids(self) -> Tuple[str, ...]:
        return tuple(s.sicht for s in self.sichten)

    def get(self, sicht_id: str) -> Optional[Sichthilfe]:
        for s in self.sichten:
            if s.sicht == sicht_id:
                return s
        return None

    def kontext_schluessel(self) -> Tuple[str, ...]:
        """Alle Kontextschluessel des Bestands (inkl. Shell), sortiert."""
        out: List[str] = [k.schluessel for k in self.shell]
        for s in self.sichten:
            out.extend(k.schluessel for k in s.kontext)
        return tuple(sorted(out))

    def alle_kontexthilfen(self) -> Tuple[Kontexthilfe, ...]:
        """Shell zuerst, dann die Sichten - fuer Pruefungen und Ausgaben."""
        out: List[Kontexthilfe] = list(self.shell)
        for s in self.sichten:
            out.extend(s.kontext)
        return tuple(out)

    def kontext_der_sicht(self, sicht_id: str) -> Tuple[Kontexthilfe, ...]:
        s = self.get(sicht_id)
        return s.kontext if s is not None else ()

    def mit(self, *sichten: Sichthilfe) -> "HilfeRegister":
        """
        Neues Register mit zusaetzlichen Kapiteln (frozen -> kein Anhaengen).
        Wird von inhalt/__init__.py beim Zusammenbau benutzt und von Tests,
        die ein Probe-Register brauchen.
        """
        return HilfeRegister(sichten=self.sichten + tuple(sichten),
                             shell=self.shell)
