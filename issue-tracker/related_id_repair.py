#!/usr/bin/env python3
# =============================================================================
# issue-tracker/related_id_repair.py
# IT-Forensisches Ermittlungswerkzeug - Issue-Tracker
# =============================================================================
# ZWECK: Verkuerzte Verweise in 'related_to' erkennen und - auf ausdrueckliche
#   Anweisung - auf die volle UUID aufloesen.
#
# HIER STEHT NUR DIE MECHANIK. Der Aufruf von der Kommandozeile steht in
# repair_related_ids.py. Getrennt, weil die Mechanik geprueft werden koennen
# muss, ohne dass ein Prozess gestartet wird (Grundregel 10, Grundregel 3).
#
# DER BEFUND (Build 642, gemessen am Bestand von Build 641):
#   Fuenf Eintraege in issue-tracker/data/issues.json fuehren in 'related_to'
#   eine 8-Zeichen-Kurzform statt der vollen UUID:
#
#     d79671f9 -> '651e6d84'
#     f51fd838 -> '906ede75', 'e9522fe2', 'c3f80e54'
#     88dc129b -> '906ede75'
#
#   Alle fuenf lassen sich eindeutig aufloesen; die vollen Vorgaenge sind
#   vorhanden. Nachgemessen mit einem Praefixvergleich ueber alle 104 IDs.
#
# WARUM DAS EIN FEHLER IST: server.py loest Verweise ueber exakte Gleichheit
#   auf (view_issue: 'i.get("id") in issue["related_to"]', Z. 403, und die
#   Rueckrichtung Z. 406). Eine Kurzform trifft nie. Der Verweis steht in der
#   Datei, aber weder die Liste 'Verwandte Vorgaenge' noch die Rueckrichtung
#   'Verweist auf diesen' zeigt ihn an. Ein Beleg, der da ist und den niemand
#   sieht - Grundregel 1.
#
# WIE VORSICHTIG DAS WERKZEUG IST:
#   * Es aendert nichts ohne '--apply'. Der Trockenlauf ist der Normalfall.
#   * Es aendert NUR das Feld 'related_to' und NUR Eintraege, die sich
#     EINDEUTIG aufloesen lassen.
#   * Mehrdeutige und unbekannte Verweise bleiben unangetastet und werden
#     BENANNT. Raten waere hier das Schlimmste: ein falscher Verweis ist
#     schlechter als ein fehlender, weil er wie ein Befund aussieht.
#   * Vor dem Schreiben wird gesichert, geschrieben wird atomar.
#
# Version: v0.8.642 - Build: 642 - 2026-08-01
# =============================================================================

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backup_names import reparatur_sicherungsname
from json_safe_writer import JsonSafeWriter


# -----------------------------------------------------------------------------
# Einordnung eines Verweises
# -----------------------------------------------------------------------------

#: Der Verweis ist bereits eine volle, gueltige UUID - nichts zu tun.
BEFUND_OK = "ok"
#: Kurzform, die sich eindeutig einem vorhandenen Vorgang zuordnen laesst.
BEFUND_AUFLOESBAR = "aufloesbar"
#: Kurzform, die auf MEHRERE vorhandene Vorgaenge passt - nicht entscheidbar.
BEFUND_MEHRDEUTIG = "mehrdeutig"
#: Verweis, zu dem sich kein Vorgang finden laesst.
BEFUND_UNBEKANNT = "unbekannt"


@dataclass
class Verweisbefund:
    """Ein einzelner geprüfter Verweis."""
    quelle_id: str          # Vorgang, in dem der Verweis steht
    verweis: str            # der Verweis, wie er in der Datei steht
    befund: str             # eine der BEFUND_*-Konstanten
    ziel_id: Optional[str] = None       # aufgeloeste volle UUID
    kandidaten: List[str] = field(default_factory=list)  # bei Mehrdeutigkeit

    @property
    def ist_maengel(self) -> bool:
        return self.befund != BEFUND_OK


@dataclass
class Reparaturbericht:
    """Ergebnis eines Laufs."""
    geprueft: int = 0                       # Anzahl aller Verweise
    befunde: List[Verweisbefund] = field(default_factory=list)
    angewendet: bool = False
    sicherung: Optional[Path] = None
    geschrieben: Optional[Path] = None

    def nach_befund(self, befund: str) -> List[Verweisbefund]:
        return [b for b in self.befunde if b.befund == befund]

    @property
    def aufloesbar(self) -> List[Verweisbefund]:
        return self.nach_befund(BEFUND_AUFLOESBAR)

    @property
    def offen(self) -> List[Verweisbefund]:
        """Was auch nach einem '--apply' noch krumm waere."""
        return self.nach_befund(BEFUND_MEHRDEUTIG) + self.nach_befund(BEFUND_UNBEKANNT)


class RelatedIdRepair:
    """
    Prüft und repariert die Verweise in 'related_to'.

    Der Ablauf ist bewusst zweistufig: erst 'pruefen()' - das liest nur -,
    dann optional 'anwenden()'. So kann der Aufrufer den Befund anzeigen,
    bevor er entscheidet, und der Trockenlauf benutzt exakt denselben Code
    wie der Ernstfall. Ein Trockenlauf, der einen anderen Weg nimmt als der
    echte Lauf, sagt nichts aus.
    """

    def __init__(self, ziel: Path, sicherungsverzeichnis: Optional[Path] = None):
        self.ziel = Path(ziel)
        # Vorgabe: 'backups' NEBEN dem Datenverzeichnis - dieselbe Regel wie
        # in merge.py, damit alle Sicherungen an EINEM Ort liegen.
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
                f"{self.ziel} hat nicht die erwartete Form {{'issues': [...]}}"
            )
        return daten

    @staticmethod
    def _ist_volle_uuid(wert: Any) -> bool:
        try:
            uuid.UUID(str(wert))
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Prüfen (verändert nichts)
    # ------------------------------------------------------------------

    def pruefen(self, daten: Optional[Dict[str, Any]] = None) -> Reparaturbericht:
        """Ordnet jeden Verweis ein, ohne etwas zu ändern."""
        if daten is None:
            daten = self.laden()

        vorgaenge = daten.get("issues", [])
        alle_ids = [str(v.get("id", "")) for v in vorgaenge if v.get("id")]
        bericht = Reparaturbericht()

        for vorgang in vorgaenge:
            quelle = str(vorgang.get("id", "?"))
            for verweis in vorgang.get("related_to") or []:
                bericht.geprueft += 1
                bericht.befunde.append(self._einordnen(quelle, verweis, alle_ids))

        return bericht

    def _einordnen(self, quelle: str, verweis: Any, alle_ids: List[str]) -> Verweisbefund:
        text = str(verweis).strip()

        # Volle UUID? Dann muss sie nur noch existieren - aber ein Verweis auf
        # einen geloeschten Vorgang ist ein ANDERER Befund als eine Kurzform
        # und wird hier ausdruecklich als 'unbekannt' gefuehrt, nicht als 'ok'.
        if self._ist_volle_uuid(text):
            if text in alle_ids:
                return Verweisbefund(quelle, text, BEFUND_OK, ziel_id=text)
            return Verweisbefund(quelle, text, BEFUND_UNBEKANNT)

        # Kurzform: ueber das Praefix suchen. Gross-/Kleinschreibung wird
        # ignoriert, weil UUIDs in Hexziffern beides sein koennen.
        treffer = [i for i in alle_ids if i.lower().startswith(text.lower())] if text else []

        # Ein Verweis auf sich selbst ist kein Fund, sondern ein Fehler in der
        # Eingabe. Er wird nicht 'repariert', sondern gemeldet.
        treffer = [t for t in treffer if t != quelle]

        if len(treffer) == 1:
            return Verweisbefund(quelle, text, BEFUND_AUFLOESBAR, ziel_id=treffer[0])
        if len(treffer) > 1:
            return Verweisbefund(quelle, text, BEFUND_MEHRDEUTIG, kandidaten=sorted(treffer))
        return Verweisbefund(quelle, text, BEFUND_UNBEKANNT)

    # ------------------------------------------------------------------
    # Anwenden (verändert die Datei)
    # ------------------------------------------------------------------

    def anwenden(self, jetzt: Optional[datetime] = None) -> Reparaturbericht:
        """
        Löst die eindeutig auflösbaren Verweise auf und schreibt die Datei.

        Reihenfolge mit Bedacht: erst lesen, dann prüfen, dann SICHERN, dann
        schreiben. Die Sicherung entsteht aus der Datei auf der Platte, nicht
        aus dem, was im Speicher steht - sonst sichert man im Fehlerfall
        genau den Zustand, den man loswerden wollte.
        """
        daten = self.laden()
        bericht = self.pruefen(daten)

        aufloesbar = bericht.aufloesbar
        if not aufloesbar:
            # Nichts zu tun heisst: NICHT schreiben. Ein Schreibvorgang ohne
            # Aenderung erzeugt nur eine ueberfluessige Sicherung und einen
            # Git-Diff ohne Inhalt.
            return bericht

        # Zuordnung (Quelle, Verweistext) -> volle UUID
        zuordnung = {(b.quelle_id, b.verweis): b.ziel_id for b in aufloesbar}

        for vorgang in daten.get("issues", []):
            quelle = str(vorgang.get("id", "?"))
            verweise = vorgang.get("related_to")
            if not verweise:
                continue
            neu = []
            for verweis in verweise:
                schluessel = (quelle, str(verweis).strip())
                neu.append(zuordnung.get(schluessel, verweis))
            vorgang["related_to"] = neu

        bericht.sicherung = self._sichern(jetzt or datetime.now())
        bericht.geschrieben = self.writer.write(self.ziel, daten)
        bericht.angewendet = True
        return bericht

    def _sichern(self, jetzt: datetime) -> Path:
        import shutil

        self.sicherungsverzeichnis.mkdir(parents=True, exist_ok=True)
        pfad = self.sicherungsverzeichnis / reparatur_sicherungsname(jetzt)
        shutil.copy2(self.ziel, pfad)
        return pfad
