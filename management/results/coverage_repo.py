# =============================================================================
# management/results/coverage_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   ABDECKUNG DER ERGEBNISBEWERTUNG JE FALL — und damit die BLINDEN FLECKEN.
#
# ── DER MANGEL, DEN DIESE KLASSE BEHEBT (gemessen, Build 393) ────────────────
#   ResultsRepo.stats() (Build 387) liest aus v_investigation_current. Dort
#   steht ein Fall NUR, wenn er mindestens EINE Bewertung hat.
#
#   Folge: Ein Fall, den NIEMAND bewertet hat, taucht in der Statistik
#   UEBERHAUPT NICHT AUF. Er wird nicht als Luecke gezeigt — er ist schlicht
#   UNSICHTBAR. Und die Statistik sieht dabei vollstaendig aus.
#
#   Genau diese Faelle sind aber das, wonach die Chef-Ermittlerin sucht. Eine
#   Auswertung, die nur ueber die Faelle spricht, die schon jemand angefasst
#   hat, beantwortet die falsche Frage (Grundregel 1: kein stilles Auslassen).
#
#   Deshalb geht diese Klasse von 'cases' AUS und joint die Bewertungen LINKS
#   an — nicht umgekehrt. Jeder Fall steht in der Liste, auch der mit
#   abdeckung = 0.
# ─────────────────────────────────────────────────────────────────────────────
#
# ABDECKUNG bezieht sich auf das Extrem 'schwerste' (mc 2026-07-12): das ist
#   die Achse, nach der priorisiert wird (die GRAVIERENDSTE Erkenntnis, nicht
#   die bestbelegte). 'beste' wird SEPARAT ausgewiesen, damit man sieht, ob ein
#   Fall zwar bewertet, aber nur einseitig bewertet ist.
#
# KEINE ZAHL OHNE VERMERK: Der Score kommt aus PriorityScorer und traegt dessen
#   Vermerk. Er wird hier NICHT ohne ihn weitergereicht.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import logging
import sqlite3
from typing import Any, Dict, List, Optional, Sequence

from management.results.assessment_catalog_repo import AssessmentCatalogRepo
from management.results.priority_scorer import VERMERK, PriorityScorer
from management.results.results_repo import ResultsRepo

logger = logging.getLogger(__name__)


class CoverageRepo:
    """Abdeckung der Ergebnisbewertung je Fall (inkl. der nie bewerteten)."""

    def __init__(self, con: sqlite3.Connection,
                 weights: Optional[Dict[str, float]] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._catalog = AssessmentCatalogRepo(con)
        self._results = ResultsRepo(con)
        self._scorer = PriorityScorer(weights)

    # ------------------------------------------------------------------ Lesen
    def coverage(self, *, subject_ids: Optional[Sequence[int]] = None
                 ) -> Dict[str, Any]:
        """
        Eine Zeile JE FALL aus 'cases' — auch fuer nie bewertete Faelle.

        subject_ids=None -> alle Faelle.
        subject_ids=[]   -> KEINE. Das ist die richtige Antwort fuer einen
                         Ermittler ohne Zuweisung — und ausdruecklich NICHT
                         dasselbe wie 'alle'.
        """
        kriterien = [c["code"] for c in self._catalog.criteria()]
        n_krit = len(kriterien)

        # AUSGANGSPUNKT IST 'cases' — nicht die Bewertungstabelle. Das ist der
        # ganze Punkt dieser Klasse.
        sql = (
            "SELECT c.subject_id, c.username, c.status, c.priority, "
            "       p.system_username AS assigned_to "
            "FROM cases c "
            "LEFT JOIN person p ON p.id = c.assigned_to"
        )
        params: List[Any] = []
        if subject_ids is not None:
            if not subject_ids:
                return self._leer(n_krit)
            sql += " WHERE c.subject_id IN (%s)" % ",".join("?" for _ in subject_ids)
            params.extend(int(u) for u in subject_ids)
        sql += " ORDER BY c.subject_id"

        faelle = [dict(r) for r in self._con.execute(sql, params).fetchall()]

        # Der aktuelle Stand ALLER dieser Faelle in EINEM Zug (nicht je Fall
        # eine Abfrage — bei 477.178 Nutzern waere das nicht tragbar).
        stand = self._current_map([f["subject_id"] for f in faelle])

        out: List[Dict[str, Any]] = []
        nie = 0
        for f in faelle:
            uid = f["subject_id"]
            rows = stand.get(uid, [])
            schwerste = [r for r in rows if r["extrem"] == "schwerste"]
            beste = [r for r in rows if r["extrem"] == "beste"]

            bewertet = {r["criterion_code"] for r in schwerste}
            unbewertet = [k for k in kriterien if k not in bewertet]

            sc = self._scorer.score(schwerste)
            letzte = max((r["created_at"] or 0) for r in rows) if rows else None

            # Die hoechste Konfidenz sagt, WORAUF sich der Fall stuetzt.
            hoch = max(schwerste, key=lambda r: r["confidence_ordinal"]) \
                if schwerste else None

            eintrag = dict(f)
            eintrag.update({
                "n_kriterien": n_krit,
                "n_bewertet": len(bewertet),
                "abdeckung": (round(len(bewertet) / n_krit, 2)
                              if n_krit else None),
                "n_beste": len({r["criterion_code"] for r in beste}),
                "unbewertet": unbewertet,
                "score": sc["score"],
                "hoechste_konfidenz": (hoch["confidence_code"] if hoch
                                       else None),
                "hoechstes_kriterium": (hoch["criterion_code"] if hoch
                                        else None),
                "zuletzt_bewertet": letzte,
                # DAS entscheidende Feld: dieser Fall ist ein BLINDER FLECK.
                "nie_bewertet": not rows,
            })
            if eintrag["nie_bewertet"]:
                nie += 1
            out.append(eintrag)

        # Sortierung: die blinden Flecken zuerst, dann die duenn bewerteten.
        # Wer die Liste oeffnet, soll sehen, WO NICHT ERMITTELT WURDE.
        out.sort(key=lambda e: (e["abdeckung"] if e["abdeckung"] is not None
                                else 0, -e["score"], e["subject_id"]))

        return {
            "faelle_gesamt": len(out),
            "nie_bewertet": nie,
            "kriterien": kriterien,
            "n_kriterien": n_krit,
            "catalog_version": self._catalog.version(),
            # Der Vermerk reist mit dem Score MIT — eine Zahl ohne ihn waere
            # eine unbelegte Behauptung.
            "vermerk": VERMERK,
            "faelle": out,
        }

    def _leer(self, n_krit: int) -> Dict[str, Any]:
        return {
            "faelle_gesamt": 0, "nie_bewertet": 0,
            "kriterien": [c["code"] for c in self._catalog.criteria()],
            "n_kriterien": n_krit,
            "catalog_version": self._catalog.version(),
            "vermerk": VERMERK, "faelle": [],
        }

    def _current_map(self, subject_ids: Sequence[int]
                     ) -> Dict[int, List[Dict[str, Any]]]:
        """Aktueller Stand aller genannten Faelle, gebuendelt je Fall."""
        if not subject_ids:
            return {}
        marks = ",".join("?" for _ in subject_ids)
        rows = self._con.execute(
            "SELECT subject_id, criterion_code, extrem, confidence_code, "
            "       confidence_ordinal, quality_code, quality_ordinal, "
            "       created_at "
            "FROM v_investigation_current WHERE subject_id IN (%s)" % marks,
            [int(u) for u in subject_ids]).fetchall()
        out: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            d = dict(r)
            # PriorityScorer erwartet 'criterion_label' — es fehlt hier
            # bewusst nicht, es ist fuer den Score irrelevant.
            out.setdefault(int(d["subject_id"]), []).append(d)
        return out

    # ------------------------------------------------------------- Zaehlwerk
    def summary(self, cov: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verdichtung fuer die Kopfzeile der Sicht. Die Zahl der NIE BEWERTETEN
        Faelle wird AUSDRUECKLICH genannt — sie ist die eigentliche Aussage.
        """
        faelle = cov.get("faelle", [])
        n = len(faelle)
        if not n:
            return {"faelle_gesamt": 0, "nie_bewertet": 0,
                    "voll_bewertet": 0, "abdeckung_mittel": None}
        voll = sum(1 for f in faelle if f["n_bewertet"] == f["n_kriterien"])
        mittel = round(sum(f["abdeckung"] or 0 for f in faelle) / n, 2)
        return {
            "faelle_gesamt": n,
            "nie_bewertet": cov.get("nie_bewertet", 0),
            "voll_bewertet": voll,
            "abdeckung_mittel": mittel,
        }
