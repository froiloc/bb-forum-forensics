# =============================================================================
# management/results/matrix_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3B (Build 537)
# =============================================================================
# Zweck:
#   Der SAMMLER der Dringlichkeits-/Erkenntnislage-Matrix. Er holt die
#   Tatsachen aus den bestehenden Read-Models, fuegt sie je Fall zusammen und
#   uebergibt sie dem reinen Rechenkern (urgency_matrix.py).
#
# ── DIESES MODUL RECHNET NICHT UND LIEST KEINE EIGENEN TABELLEN ──────────────
#
#   Es gibt in diesem Werkzeug bereits sechs Fall-Aggregate. Ein siebtes mit
#   eigenen SQL-Abfragen waere eine siebte Wahrheit ueber denselben Bestand —
#   und die erste, die auseinanderlaeuft. Der Sammler benutzt deshalb
#   ausschliesslich vorhandene Repositories:
#
#     DashboardRepo.list_case_overview()   1 Abfrage  -> X-3, X-4, X-5
#     ExternalMattersRepo.list_matters()   1 Abfrage  -> X-2
#     v_investigation_current (roh)        1 Abfrage  -> Y-1, Y-2
#     AssessmentCatalogRepo.criteria()     1 Abfrage  -> Bezugsgroesse fuer Y-1
#     IdentifiedSubjectRepo.list()         1 Abfrage  -> Y-3
#
#   Y-1/Y-2 gehen ROH und nicht ueber CoverageRepo.coverage() — die Begruendung
#   steht im naechsten Absatz. Die SICHT 'v_investigation_current' ist dabei
#   dieselbe, auf der auch CoverageRepo arbeitet (coverage_repo.py:169); es
#   entsteht also keine zweite Wahrheit, nur eine andere Verdichtung.
#
#   Verbindungspunkt ist durchgaengig 'subject_id' (seit M019 einheitlich).
#
#   X-1 (die Verjaehrungsfrist) ist BEWUSST NICHT DABEI. Sie kostet zwei
#   Dateizugriffe JE FALL und kommt erst mit Build 538 dazu. Bis dahin ist die
#   Dringlichkeit jeder Zeile ausdruecklich NICHT BESTIMMBAR (Grund
#   'nicht_geladen') und der ausgewiesene Wert eine UNTERGRENZE. Das ist der
#   Unterschied zwischen 'noch nicht geholt' und 'nicht vorhanden', und er
#   steht in jeder Zeile.
#
# ── WARUM DIE BEWERTUNGEN ROH DURCHGEREICHT WERDEN ───────────────────────────
#
#   CoverageRepo rechnet die Abdeckung ueber ALLE zehn Kriterien. Die Matrix
#   braucht sie ueber NEUN — ohne 'identification', das ueber die
#   Identitaetstabelle eigens zaehlt (Entscheidung mc M-3). Statt CoverageRepo
#   umzubauen (es bedient /api/results/coverage, wo die Frage eine andere ist)
#   reicht der Sammler die ROHEN Bewertungszeilen durch und laesst den
#   Rechenkern ausschliessen. Damit gibt es weiterhin genau eine Stelle, an der
#   die Ausschlussregel steht.
#
# ── REIN LESEND ──────────────────────────────────────────────────────────────
#
#   coordinator.db wird vom Aufrufer mit mode=ro geoeffnet. Kein
#   CoordinatorWriter, kein Schreibpfad; der Migrationsvorbehalt ist nicht
#   beruehrt. Die Matrix schreibt insbesondere NICHT in cases.priority
#   (Entscheidung mc) — sie ist ein Vorschlag, den ein Mensch sieht.
#
# Version: v0.8.537 · Build: 537 · 2026-07-26
# =============================================================================

from __future__ import annotations

import dataclasses
import logging
import sqlite3
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from management.cases.escalation import (
    EscalationThresholds,
    evaluate_escalations,
)
from management.crossref.identified_subject_repo import IdentifiedSubjectRepo
from management.dashboard.dashboard_repo import DashboardRepo
from management.external.external_matters_repo import ExternalMattersRepo
from management.results.assessment_catalog_repo import AssessmentCatalogRepo
from management.results.matrix_weights import MatrixGewichte
from management.results.urgency_matrix import MatrixZelle, UrgencyMatrix

logger = logging.getLogger(__name__)

#: Die Vorgangsstaende, die noch auf eine Antwort warten. 'erledigt' und
#: 'erfolglos' sind Endzustaende und koennen nicht ueberfaellig sein
#: (matter_status.py:181-182).
OFFENE_VORGANGSSTAENDE: tuple = ("offen", "beantwortet")

#: Die Ampelfarbe eines externen Vorgangs, die 'ueberfaellig' bedeutet.
#: 'gelb' ist die VORWARNUNG und zaehlt ausdruecklich NICHT — sonst waere die
#: Vorwarnfrist eine zweite Faelligkeit.
AMPEL_UEBERFAELLIG: str = "rot"


class MatrixRepo:
    """Sammelt die Tatsachen je Fall und laesst den Rechenkern rechnen."""

    def __init__(self, con: sqlite3.Connection,
                 gewichte: MatrixGewichte) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._g = gewichte
        self._matrix = UrgencyMatrix(gewichte)

    # ------------------------------------------------------------------ Sammeln
    def _tage(self, ov: Dict[str, Any], now: int) -> Optional[int]:
        """
        Liegezeit in Tagen. Massgeblich ist 'last_activity_at' —
        max(cases.updated_at, MAX(case_events.created_at)),
        dashboard_repo.py:348. Nur das letzte EREIGNIS zu nehmen waere falsch:
        ein Fall ohne jedes Ereignis haette dann gar keine Liegezeit.
        """
        la = ov.get("last_activity_at")
        if la is None:
            return None
        return max(0, (now - int(la)) // 86400)

    def _ueberfaellige_vorgaenge(self, stichtag: str) -> Dict[int, int]:
        """
        subject_id -> Zahl der UEBERFAELLIGEN externen Vorgaenge.

        'Ueberfaellig' ist nicht gespeichert, sondern eine Funktion des
        Stichtags (matter_status.py:194-199). Gefragt wird deshalb der fertige
        Ampelwert und nicht das Datum — sonst entstuende hier eine zweite
        Faelligkeitsregel. Der Sonderfall 'verwaist' (Fall abgeschlossen,
        Vorgang offen) ist damit automatisch mit erfasst: er ist IMMER rot,
        unabhaengig vom Datum.
        """
        repo = ExternalMattersRepo(self._con)
        try:
            rows = repo.list_matters(statuses=list(OFFENE_VORGANGSSTAENDE))
        except sqlite3.Error as exc:
            # M010 nicht angewandt o. Ae. Der Beitrag entfaellt, aber der
            # Aufrufer erfaehrt es (s. compute -> 'fehlende_quellen').
            logger.warning("Matrix: externe Vorgaenge nicht lesbar: %s", exc)
            raise
        out: Dict[int, int] = {}
        for r in repo.with_ampel(rows, stichtag):
            if r.get("ampel") == AMPEL_UEBERFAELLIG:
                sid = int(r["subject_id"])
                out[sid] = out.get(sid, 0) + 1
        return out

    def _eskalationen(self, overviews: List[Dict[str, Any]],
                      now: int) -> Dict[int, int]:
        """
        subject_id -> Zahl der aktiven Eskalationsmeldungen.

        Es wird die REINE Regelauswertung benutzt (escalation.py:71) und NICHT
        EscalationRepo.compute() — Letzteres wuerde die Fallübersicht ein
        zweites Mal aus der Datenbank holen (escalation_repo.py:37-38), die
        hier bereits vorliegt.

        QUITTIERTE MELDUNGEN ZAEHLEN MIT. m027_escalation_ack.py:15-22
        woertlich: 'Sie ist KEIN Erledigen. Die Eskalation VERSCHWINDET NICHT
        aus der Liste.' Der Vermerk wird deshalb hier gar nicht erst gelesen.

        Systemische Meldungen (subject_id=None, etwa 'rueckstau_hoch') gehoeren
        zu KEINEM Fall und werden uebersprungen — sie einem Fall zuzurechnen
        waere eine Erfindung.
        """
        bericht = evaluate_escalations(
            overviews, EscalationThresholds(), now)
        out: Dict[int, int] = {}
        for item in bericht.items:
            if item.subject_id is None:
                continue
            sid = int(item.subject_id)
            out[sid] = out.get(sid, 0) + 1
        return out

    def _bewertungen(self, subject_ids: Sequence[int]
                     ) -> Dict[int, List[Dict[str, Any]]]:
        """
        subject_id -> die aktuellen Bewertungszeilen (roh).

        ROH, nicht verdichtet: die Matrix schliesst 'identification' aus
        (Entscheidung M-3), CoverageRepo tut das nicht — und soll es auch
        nicht, weil /api/results/coverage eine andere Frage beantwortet. Die
        Ausschlussregel steht deshalb an genau EINER Stelle, im Rechenkern.
        """
        if not subject_ids:
            return {}
        marks = ",".join("?" for _ in subject_ids)
        rows = self._con.execute(
            "SELECT subject_id, criterion_code, extrem, confidence_code, "
            "       confidence_ordinal "
            "FROM v_investigation_current WHERE subject_id IN (%s)" % marks,
            [int(s) for s in subject_ids]).fetchall()
        out: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(int(r["subject_id"]), []).append(dict(r))
        return out

    # ------------------------------------------------------------------ Rechnen
    def compute(self, *, now_ts: Optional[int] = None,
                subject_ids: Optional[Sequence[int]] = None
                ) -> Dict[str, Any]:
        """
        Die Matrix ueber alle (oder die genannten) Faelle.

        subject_ids=None -> alle. subject_ids=[] -> KEINE. Eine leere Auswahl
        ist eine Auswahl und bedeutet ausdruecklich nicht 'alle' (Muster
        coverage_repo.py:64-67, limitation_repo.py:677-680).

        OHNE FRISTBEITRAEGE (Build 537). Jede Zeile traegt deshalb
        dringlichkeit_bestimmbar=false mit dem Grund 'nicht_geladen'; der
        ausgewiesene Wert ist eine Untergrenze. Build 538 schliesst die Frist an.
        """
        now = int(time.time()) if now_ts is None else int(now_ts)
        stichtag = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
        fehlende_quellen: List[str] = []

        # --- (1) Fallübersicht: eine Aggregatabfrage ------------------------
        overviews = [dataclasses.asdict(o)
                     for o in DashboardRepo(self._con).list_case_overview(now=now)]
        if subject_ids is not None:
            erlaubt = {int(s) for s in subject_ids}
            overviews = [o for o in overviews
                         if int(o["subject_id"]) in erlaubt]

        ids = [int(o["subject_id"]) for o in overviews]

        # --- (2) die drei uebrigen Quellen ---------------------------------
        #     Faellt eine aus, wird der Fall NICHT weggelassen — der Beitrag
        #     entfaellt, und die Quelle wird BENANNT. Ein stillschweigend
        #     fehlender Beitrag saehe aus wie 'trifft nicht zu'.
        try:
            vorgaenge = self._ueberfaellige_vorgaenge(stichtag)
        except sqlite3.Error as exc:
            vorgaenge = {}
            fehlende_quellen.append("externe Vorgaenge (%s)" % exc)

        try:
            eskalationen = self._eskalationen(overviews, now)
        except Exception as exc:                        # noqa: BLE001
            eskalationen = {}
            fehlende_quellen.append("Eskalationen (%s)" % exc)

        try:
            bewertungen = self._bewertungen(ids)
        except sqlite3.Error as exc:
            bewertungen = {}
            fehlende_quellen.append("Ergebnisbewertungen (%s)" % exc)

        try:
            alle_kriterien = [c["code"]
                              for c in AssessmentCatalogRepo(self._con).criteria()]
        except Exception as exc:                        # noqa: BLE001
            alle_kriterien = []
            fehlende_quellen.append("Bewertungskatalog (%s)" % exc)

        try:
            identitaeten = {int(d["subject_id"]): d.get("confidence_code")
                            for d in IdentifiedSubjectRepo(self._con).list()}
        except Exception as exc:                        # noqa: BLE001
            identitaeten = {}
            fehlende_quellen.append("Identitaetszuordnungen (%s)" % exc)

        # --- (3) je Fall zusammenfuegen und rechnen ------------------------
        faelle = []
        for ov in overviews:
            sid = int(ov["subject_id"])
            faelle.append({
                "subject_id": sid,
                "username": ov.get("username") or "?",
                # Build 538 setzt hier den Fristbericht ein.
                "limitation": None,
                "wiedervorlage_ueberfaellig": vorgaenge.get(sid, 0) > 0,
                "eskalationen": eskalationen.get(sid, 0),
                "tage_ohne_ereignis": self._tage(ov, now),
                "unzugewiesen": ov.get("assigned_to") is None,
                "alle_kriterien": alle_kriterien,
                "bewertungen": bewertungen.get(sid, []),
                "identitaet_konfidenz": identitaeten.get(sid),
            })

        zellen: List[MatrixZelle] = self._matrix.bewerte_alle(faelle)

        quadranten: Dict[str, int] = {}
        belastbarkeit: Dict[str, int] = {}
        unbekannte: Dict[str, int] = {}
        for z in zellen:
            quadranten[z.quadrant] = quadranten.get(z.quadrant, 0) + 1
            belastbarkeit[z.dringlichkeit_belastbarkeit] = (
                belastbarkeit.get(z.dringlichkeit_belastbarkeit, 0) + 1)
            for c in z.unbekannte_codes:
                unbekannte[c] = unbekannte.get(c, 0) + 1

        hinweise = self._hinweise(zellen, fehlende_quellen, unbekannte)

        out: Dict[str, Any] = {
            "stichtag": stichtag,
            "faelle_gesamt": len(zellen),
            "fristen_geladen": False,
            "quadranten": quadranten,
            "belastbarkeit_verteilung": belastbarkeit,
            "unbekannte_codes": unbekannte,
            "fehlende_quellen": fehlende_quellen,
            "hinweise": hinweise,
            "zellen": [z.to_dict() for z in zellen],
        }
        out.update(self._g.to_dict())
        return out

    # ------------------------------------------------------------------ Hinweise
    @staticmethod
    def _hinweise(zellen: Sequence[MatrixZelle],
                  fehlende_quellen: Sequence[str],
                  unbekannte: Dict[str, int]) -> List[str]:
        """
        Die Hinweise der Antwort. Reihenfolge: das Dringendste zuletzt
        eingefuegt, weil insert(0) nach vorn schiebt.
        """
        n = len(zellen)
        hinweise: List[str] = [
            "Die Fristbeitraege sind in diesem Stand NICHT geladen. Jede Zeile "
            "traegt deshalb 'dringlichkeit_bestimmbar': false mit dem Grund "
            "'nicht_geladen', und der Wert in 'dringlichkeit_mindestens' ist "
            "eine UNTERGRENZE — kein Fall ist so wenig dringlich, wie er hier "
            "aussieht.",
        ]

        unbestimmbar = sum(1 for z in zellen
                           if z.quadrant == "nicht_bestimmbar")
        if unbestimmbar:
            hinweise.insert(0,
                "%d von %d Faellen stehen im Feld 'nicht bestimmbar'. Sie sind "
                "damit UNGEPRUEFT und nicht unverdaechtig — deshalb stehen sie "
                "in der Liste OBEN und nicht am Ende."
                % (unbestimmbar, n))

        if unbekannte:
            hinweise.insert(0,
                "Es kommen Konfidenz-Codes vor, die der Gewichtungssatz nicht "
                "kennt: %s. Die betroffenen Faelle werden NICHT mit 0 "
                "gerechnet, sondern als nicht bestimmbar gefuehrt. Vermutlich "
                "wurde der Bewertungskatalog erweitert und "
                "management/results/matrix_weights.json nicht nachgezogen — "
                "das ist eine fachliche Entscheidung, keine Codeanpassung."
                % ", ".join("%s (%dx)" % (k, v)
                            for k, v in sorted(unbekannte.items())))

        if fehlende_quellen:
            hinweise.insert(0,
                "MINDESTENS EINE QUELLE WAR NICHT LESBAR: %s. Die betroffenen "
                "Beitraege fehlen in JEDER Zeile — ein Fall kann deshalb "
                "harmloser aussehen, als er ist."
                % "; ".join(fehlende_quellen))

        return hinweise
