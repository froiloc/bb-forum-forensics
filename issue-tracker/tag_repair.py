#!/usr/bin/env python3
# =============================================================================
# issue-tracker/tag_repair.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: Tags nach einer VORGEGEBENEN Zuordnungsliste zusammenlegen.
#
# ANLASS: Vorgang 6e96ae4a. Die Tag-Wolke aus Build 647 machte sichtbar, was
#   vorher niemand sehen konnte: 167 Tags auf 145 Vorgaenge, mehr als die
#   Haelfte davon Einzelstuecke, und darunter Begriffe, die dasselbe meinen.
#
# DIE ZUORDNUNG KOMMT VON mc, NICHT VON MIR - und das ist der ganze Punkt
#   dieses Bausteins. Welche Begriffe dasselbe meinen, ist eine fachliche
#   Frage. Ich habe 36 Vorschlaege vorgelegt; die Entscheidung vom 2026-08-02
#   lautet:
#
#     * "Alles mit Grundregel so lassen. Es bezeichnet die Nummer der
#        Grundregel. Das zu aendern wuerde das Thema der Regel aendern, auf
#        welche hier Bezug genommen wird."
#       -> 'Grundregel1', 'Grundregel2', 'Grundregel-3' und 'Grundregel4'
#          bleiben getrennt. Sie sehen aus wie eine Familie und sind KEINE:
#          die Zahl ist der Inhalt. Genau dafuer war die Vorlage da.
#
#     * "Singular immer auf Plural erweitern. Dabei belassen wir es."
#       -> nur die drei Singular/Plural-Paare unten, sonst nichts.
#
#   Ein Werkzeug, das seine Zuordnung selbst errechnet, haette hier die
#   Grundregeln zusammengelegt. Deshalb steht die Liste im Code und nicht in
#   einem Aehnlichkeitsmass.
#
# WAS DER BAUSTEIN TUT UND WAS NICHT:
#   * Er ersetzt Tags NUR nach der Liste. Was nicht in der Liste steht,
#     bleibt unangetastet.
#   * Er vergleicht ohne Ruecksicht auf Gross- und Kleinschreibung - dieselbe
#     Regel wie in der Wolke.
#   * Entsteht ein Tag dabei doppelt an einem Vorgang, bleibt es EINMAL
#     stehen; die Reihenfolge der uebrigen bleibt erhalten.
#   * Er aendert NUR das Feld 'tags'. Fliesstext, in dem ein Tag-Wort
#     vorkommt, bleibt unberuehrt - dort ist es ein Wort und kein Tag.
#
# Version: v0.8.650 - Build: 650 - 2026-08-02
# =============================================================================

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backup_names import reparatur_sicherungsname
from json_safe_writer import JsonSafeWriter

#: DIE ZUORDNUNG. Links die Schreibweise, die verschwindet, rechts die, die
#: bleibt. Festlegung mc, 2026-08-02: "Singular immer auf Plural erweitern."
#:
#: Die drei Paare sind die vollstaendige Liste der Singular/Plural-Doppel im
#: Bestand von 0.8.649 - ermittelt ueber die Endungen -s, -e und -en und von
#: Hand nachgesehen.
ZUORDNUNG: Dict[str, str] = {
    "test": "Tests",
    "Sicht": "Sichten",
    "Spur": "Spuren",
}


@dataclass
class Tagbefund:
    vorgang_id: str
    alt: str
    neu: str


@dataclass
class Tagbericht:
    befunde: List[Tagbefund] = field(default_factory=list)
    angewendet: bool = False
    sicherung: Optional[Path] = None
    geschrieben: Optional[Path] = None

    @property
    def betroffene_vorgaenge(self) -> int:
        return len({b.vorgang_id for b in self.befunde})


def _zuordnung_klein(zuordnung: Dict[str, str]) -> Dict[str, str]:
    return {k.lower(): v for k, v in zuordnung.items()}


def tags_umschreiben(tags: List[Any], zuordnung: Dict[str, str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    """
    Schreibt die Tags eines Vorgangs um.

    Returns:
        (neue Tagliste, Liste der Ersetzungen als (alt, neu))
    """
    klein = _zuordnung_klein(zuordnung)
    neu: List[str] = []
    ersetzungen: List[Tuple[str, str]] = []
    gesehen = set()

    for roh in tags or []:
        tag = str(roh).strip()
        if not tag:
            continue
        ziel = klein.get(tag.lower(), tag)
        if ziel != tag:
            ersetzungen.append((tag, ziel))
        # Doppelte zusammenfassen - ohne Ruecksicht auf Gross-/Kleinschreibung,
        # sonst stuenden nach der Umschreibung zwei Schreibweisen desselben
        # Tags am selben Vorgang.
        if ziel.lower() in gesehen:
            continue
        gesehen.add(ziel.lower())
        neu.append(ziel)

    return neu, ersetzungen


class TagRepair:
    """Prüft und wendet die Tag-Zuordnung an - zweistufig wie die übrigen Werkzeuge."""

    def __init__(self, ziel: Path, zuordnung: Optional[Dict[str, str]] = None,
                 sicherungsverzeichnis: Optional[Path] = None):
        self.ziel = Path(ziel)
        self.zuordnung = dict(zuordnung if zuordnung is not None else ZUORDNUNG)
        self.sicherungsverzeichnis = (
            Path(sicherungsverzeichnis) if sicherungsverzeichnis
            else self.ziel.resolve().parent.parent / "backups"
        )
        self.writer = JsonSafeWriter()

    def laden(self) -> Dict[str, Any]:
        with open(self.ziel, "r", encoding="utf-8") as f:
            daten = json.load(f)
        if not isinstance(daten, dict) or "issues" not in daten:
            raise ValueError(f"{self.ziel} hat nicht die erwartete Form {{'issues': [...]}}")
        return daten

    def pruefen(self, daten: Optional[Dict[str, Any]] = None) -> Tagbericht:
        if daten is None:
            daten = self.laden()
        bericht = Tagbericht()
        for vorgang in daten.get("issues", []):
            _neu, ersetzungen = tags_umschreiben(vorgang.get("tags"), self.zuordnung)
            for alt, neu in ersetzungen:
                bericht.befunde.append(Tagbefund(str(vorgang.get("id", "?")), alt, neu))
        return bericht

    def anwenden(self, jetzt: Optional[datetime] = None) -> Tagbericht:
        daten = self.laden()
        bericht = self.pruefen(daten)
        if not bericht.befunde:
            # Nichts zu tun heisst NICHT schreiben.
            return bericht

        for vorgang in daten.get("issues", []):
            neu, ersetzungen = tags_umschreiben(vorgang.get("tags"), self.zuordnung)
            if ersetzungen or neu != list(vorgang.get("tags") or []):
                vorgang["tags"] = neu

        bericht.sicherung = self._sichern(jetzt or datetime.now())
        bericht.geschrieben = self.writer.write(self.ziel, daten)
        bericht.angewendet = True
        return bericht

    def _sichern(self, jetzt: datetime) -> Path:
        self.sicherungsverzeichnis.mkdir(parents=True, exist_ok=True)
        pfad = self.sicherungsverzeichnis / reparatur_sicherungsname(jetzt)
        shutil.copy2(self.ziel, pfad)
        return pfad
