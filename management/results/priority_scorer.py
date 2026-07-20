# =============================================================================
# management/results/priority_scorer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Eine PROVISORISCHE Kennzahl aus der Ergebnisbewertung — als Vorschlag fuer
#   eine nachgeordnete Priorisierung.
#
# DER WICHTIGSTE SATZ DIESES MODULS (mc 2026-07-12):
#   Die Formel ist FLACH und UNGEWICHTET. Gewichtung und Struktur sind mit
#   Chef-Ermittlerin und Staatsanwaltschaft NICHT abgestimmt.
#
#   Deshalb liefert dieses Modul NIE eine nackte Zahl, sondern immer
#   {score, beitraege, vermerk} — und der VERMERK sagt woertlich, dass die Zahl
#   keine Massnahme allein begruenden darf. Eine Kennzahl ohne diesen Satz waere
#   eine unbelegte Behauptung im Bericht, und das verletzt die oberste Regel
#   dieses Projekts (Ueberpruefbarkeit von Behauptungen).
#
#   Die Gewichte sind ein PARAMETER (weights), kein fest verdrahteter Wert.
#   Wenn die Gewichtung spaeter festgelegt wird, ist das eine Konfiguration —
#   kein Umbau.
#
# WAS DIESES MODUL AUSDRUECKLICH NICHT TUT:
#   Es schreibt NICHT in cases.priority. Die Zahl ist ein VORSCHLAG, den ein
#   Mensch sieht und bewertet. Eine automatische Priorisierung nach einer
#   unabgestimmten Formel waere genau die Art von stiller Wirkung, die dieses
#   Projekt vermeidet.
#
# RECHENWEG (bewusst simpel, damit er erklaerbar bleibt):
#   Je Kriterium wird das Extrem 'schwerste' herangezogen — die Priorisierung
#   richtet sich nach der GRAVIERENDSTEN Erkenntnis, nicht nach der am besten
#   belegten. (Ein gerichtsfest belegter Bagatellfund priorisiert nicht.)
#   Beitrag = confidence_ordinal * gewicht(kriterium)
#   score   = Summe der Beitraege
#   Der Qualitaetswert geht BEWUSST NICHT in den Score ein: 'ordinal' bedeutet
#   bei abuser_quality SCHWERE, bei location_quality PRAEZISION (M011). Beides
#   zu addieren waere Unsinn. Die Qualitaet wird nur AUSGEWIESEN.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

#: Der Vermerk, der JEDER Kennzahl beiliegt. Wortlaut ist Absicht.
VERMERK = (
    "PROVISORISCH — Gewichtung und Struktur dieser Formel sind mit "
    "Chef-Ermittlerin und Staatsanwaltschaft NICHT abgestimmt. Die Zahl darf "
    "keine Massnahme allein begruenden. Sie dient der Veranschaulichung und "
    "wird ersetzt, sobald die Gewichtung festgelegt ist."
)

#: Standardgewichte: ALLE 1,0 — flach und ungewichtet (mc). Bewusst als
#: Parameter, nicht als Konstante im Rechenweg.
DEFAULT_WEIGHT: float = 1.0


class PriorityScorer:
    """Provisorische Kennzahl aus der Ergebnisbewertung."""

    def __init__(self, weights: Optional[Dict[str, float]] = None) -> None:
        # weights: {criterion_code: gewicht}. Fehlt ein Kriterium, gilt
        # DEFAULT_WEIGHT. Eine leere Abbildung ist damit die flache Formel.
        self._weights = dict(weights or {})

    def weight(self, criterion_code: str) -> float:
        return float(self._weights.get(criterion_code, DEFAULT_WEIGHT))

    def score(self, current: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """
        current: die Zeilen aus ResultsRepo.current(subject_id).
        -> {score, beitraege[], vermerk, basis, unbewertet[]}

        'unbewertet' nennt die Kriterien OHNE Bewertung ausdruecklich. Ein Score
        aus drei von zehn Kriterien ist etwas anderes als einer aus zehn — und
        das darf nicht im Ergebnis untergehen (Grundregel 1).
        """
        beitraege: List[Dict[str, Any]] = []
        total = 0.0

        # Nur 'schwerste' geht in den Score (s. Kopfkommentar).
        rows = [r for r in (current or []) if r.get("extrem") == "schwerste"]

        for r in rows:
            code = r["criterion_code"]
            g = self.weight(code)
            conf = int(r.get("confidence_ordinal") or 0)
            beitrag = conf * g
            total += beitrag
            beitraege.append({
                "criterion": code,
                "criterion_label": r.get("criterion_label", code),
                "confidence": r.get("confidence_code"),
                "confidence_ordinal": conf,
                "gewicht": g,
                "beitrag": round(beitrag, 2),
                # Qualitaet wird AUSGEWIESEN, aber NICHT addiert (s. o.).
                "quality": r.get("quality_code"),
                "quality_ordinal": r.get("quality_ordinal"),
            })

        beitraege.sort(key=lambda b: (-b["beitrag"], b["criterion"]))

        return {
            "score": round(total, 2),
            "basis": len(rows),
            "beitraege": beitraege,
            "vermerk": VERMERK,
        }

    def score_with_gaps(self, current: Sequence[Dict[str, Any]],
                        alle_kriterien: Sequence[str]) -> Dict[str, Any]:
        """
        Wie score(), nennt zusaetzlich die NICHT BEWERTETEN Kriterien.
        Genau diese Luecke ist die interessante Information: sie sagt, wo noch
        ermittelt werden muss.
        """
        res = self.score(current)
        bewertet = {r["criterion_code"] for r in (current or [])
                    if r.get("extrem") == "schwerste"}
        fehlend = [c for c in alle_kriterien if c not in bewertet]
        res["unbewertet"] = fehlend
        res["abdeckung"] = (
            round(len(bewertet) / len(alle_kriterien), 2)
            if alle_kriterien else None)
        return res
