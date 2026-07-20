# =============================================================================
# management/results/results_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Die BEWERTUNG des Ermittlungsergebnisses (investigation_results).
#
#   Je Fall und Kriterium ZWEI Bewertungen (mc 2026-07-12):
#     'schwerste' — die gravierendste Erkenntnis
#     'beste'     — die am besten belegte / praeziseste Erkenntnis
#   Je Bewertung ZWEI Achsen:
#     KONFIDENZ  (wie sicher?)  — einheitliche Skala fuer alle Kriterien
#     QUALITAET  (wie tief?)    — kriterienspezifisch, darf fehlen
#
# APPEND-ONLY (mc):
#   Kein update(), kein delete(). Eine Korrektur ist eine NEUE Zeile. Der
#   Verlauf IST hier die Ermittlungsleistung — er zeigt, wie aus 'Verdacht'
#   'wahrscheinlich' und schliesslich 'gerichtsfest' wurde. Diesen Verlauf zu
#   ueberschreiben hiesse, den Erkenntnisgewinn zu loeschen.
#   Zusaetzlich verbieten Datenbank-TRIGGER (M011) UPDATE und DELETE — der
#   Schutz haengt NICHT allein an dieser Klasse (ein Repo kann man umgehen,
#   einen Trigger nicht).
#
# EINGEFRORENE NUMERIK (mc, der wichtigste Punkt dieses Moduls):
#   Beim Erfassen wird der ORDINAL-Wert des gewaehlten Skalenpunkts AUS DEM
#   KATALOG GELESEN und in der Bewertungszeile MITGESPEICHERT — zusammen mit
#   der Katalogversion.
#
#   Wird eine Skala spaeter umnummeriert (und das ist ausdruecklich vorgesehen),
#   behalten alte Bewertungen ihren damaligen Zahlenwert. Ohne diese Kopie
#   wuerden Zeitreihen ihre Bedeutung RUECKWIRKEND aendern — still, ohne
#   Fehler, ohne dass es jemand merkt. Das waere der schwerste denkbare Fehler
#   dieses Moduls (Grundregel 1).
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence

from management.audit.event_types import EventType
from management.case_events.case_events_repo import insert_event_row
from management.gateway.coordinator_writer import CoordinatorWriter
from management.results.assessment_catalog_repo import (
    AssessmentCatalogRepo,
    CatalogError,
)

logger = logging.getLogger(__name__)

#: Zeitstrahl-Vokabular dieses Moduls (case_events.event_kind).
EVENT_KIND = "assessment"

#: Die beiden Extreme (mc). Bewusst KEINE weiteren: mehr Extreme hiessen mehr
#: Pflegeaufwand ohne Zusatznutzen fuer die Priorisierung.
EXTREME = ("schwerste", "beste")

#: Skala der Konfidenz-Achse (im Katalog, nicht im Code — hier nur der Name).
CONFIDENCE_SCALE = "confidence"


class ResultsError(Exception):
    """Fachlicher Fehler bei der Ergebnisbewertung."""


class ResultsRepo:
    """Append-only Bewertungen des Ermittlungsergebnisses."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer
        self._catalog = AssessmentCatalogRepo(con, writer)

    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise ResultsError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibpfad zulaessig.")
        return self._writer

    # ------------------------------------------------------------------- Lesen
    def current(self, subject_id: int) -> List[Dict[str, Any]]:
        """
        Der AKTUELLE Stand je Kriterium x Extrem (Sicht v_investigation_current),
        angereichert um die Klartext-Beschriftungen des Katalogs.
        """
        rows = self._con.execute(
            "SELECT * FROM v_investigation_current WHERE subject_id = ? "
            "ORDER BY criterion_code, extrem", (subject_id,)).fetchall()
        return [self._enrich(dict(r)) for r in rows]

    def history(self, subject_id: int, *,
                criterion_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Die VOLLSTAENDIGE Historie. Sie ist kein Beiwerk: sie belegt den
        Erkenntnisgewinn und ist damit selbst ein Ermittlungsergebnis.
        """
        sql = "SELECT * FROM investigation_results WHERE subject_id = ?"
        params: List[Any] = [subject_id]
        if criterion_code:
            sql += " AND criterion_code = ?"
            params.append(criterion_code)
        sql += " ORDER BY created_at DESC, id DESC"
        return [self._enrich(dict(r))
                for r in self._con.execute(sql, params).fetchall()]

    def _enrich(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """Klartext ergaenzen. Auch AUSSER DIENST gestellte Punkte werden
        aufgeloest — eine alte Bewertung darf nicht unlesbar werden."""
        try:
            crit = self._catalog.criterion(d["criterion_code"])
            d["criterion_label"] = crit["label"]
            d["quality_scale"] = crit["quality_scale"]
        except CatalogError:
            d["criterion_label"] = d["criterion_code"]
            d["quality_scale"] = None
        try:
            d["confidence_label"] = self._catalog.item(
                CONFIDENCE_SCALE, d["confidence_code"])["label"]
        except CatalogError:
            d["confidence_label"] = d["confidence_code"]
        if d.get("quality_code") and d.get("quality_scale"):
            try:
                d["quality_label"] = self._catalog.item(
                    d["quality_scale"], d["quality_code"])["label"]
            except CatalogError:
                d["quality_label"] = d["quality_code"]
        else:
            d["quality_label"] = None
        return d

    # --------------------------------------------------------------- Schreiben
    def assess(
        self, *, subject_id: int, criterion_code: str, extrem: str,
        confidence_code: str, quality_code: Optional[str] = None,
        note: str = "", actor_id: Optional[int] = None,
        meta: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Eine Bewertung erfassen — IMMER als NEUE Zeile (append-only).
        -> {'result_id', 'audit_seq', 'catalog_version'}
        """
        writer = self._require_writer()

        if extrem not in EXTREME:
            raise ResultsError(
                "extrem muss '%s' sein (nicht '%s')."
                % ("' oder '".join(EXTREME), extrem))

        # --- Katalog befragen: Codes aufloesen und Zahlenwerte EINFRIEREN ----
        try:
            crit = self._catalog.criterion(criterion_code)
            if crit.get("deprecated_at"):
                raise ResultsError(
                    "Kriterium '%s' ist ausser Dienst gestellt und kann nicht "
                    "mehr neu bewertet werden." % criterion_code)
            conf = self._catalog.item(CONFIDENCE_SCALE, confidence_code)
            if conf.get("deprecated_at"):
                raise ResultsError(
                    "Konfidenz-Stufe '%s' ist ausser Dienst gestellt."
                    % confidence_code)
        except CatalogError as exc:
            raise ResultsError(str(exc)) from exc

        q_scale = crit["quality_scale"]
        q_ordinal: Optional[int] = None
        if quality_code:
            if not q_scale:
                # Kein stilles Verschlucken: das Kriterium HAT keine
                # Qualitaetsskala — eine Qualitaetsangabe waere sinnlos und
                # wuerde spaeter falsche Statistiken speisen.
                raise ResultsError(
                    "Kriterium '%s' hat (noch) keine Qualitaetsskala — eine "
                    "Qualitaetsangabe ist hier nicht vorgesehen. Die Skala "
                    "kann per catalog_admin nachgetragen werden."
                    % criterion_code)
            try:
                qi = self._catalog.item(q_scale, quality_code)
            except CatalogError as exc:
                raise ResultsError(str(exc)) from exc
            if qi.get("deprecated_at"):
                raise ResultsError(
                    "Qualitaets-Stufe '%s' ist ausser Dienst gestellt."
                    % quality_code)
            q_ordinal = int(qi["ordinal"])

        c_ordinal = int(conf["ordinal"])
        catver = self._catalog.version()
        now = int(time.time())
        state: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if not con.execute("SELECT 1 FROM cases WHERE subject_id = ?",
                               (subject_id,)).fetchone():
                raise ResultsError("Kein Fall subject_id=%s." % subject_id)
            cur = con.execute(
                "INSERT INTO investigation_results "
                "(subject_id, criterion_code, extrem, confidence_code, "
                " confidence_ordinal, quality_code, quality_ordinal, "
                " catalog_version, note, created_by, created_at, audit_seq) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (subject_id, criterion_code, extrem, confidence_code, c_ordinal,
                 quality_code, q_ordinal, catver, note or "", actor_id, now))
            state["id"] = int(cur.lastrowid)
            # Audit-Payload: FAKTEN + Zahlen, KEIN Freitext (Sensibilitaets-
            # regel wie bei cases.note und external_matters).
            return {
                "result_id": state["id"], "subject_id": subject_id,
                "criterion": criterion_code, "extrem": extrem,
                "confidence": confidence_code, "confidence_ordinal": c_ordinal,
                "quality": quality_code, "quality_ordinal": q_ordinal,
                "catalog_version": catver, "note_len": len(note or ""),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE investigation_results SET audit_seq = ? WHERE id = ?",
                (seq, state["id"]))
            # Zeitstrahl: der Erkenntnisgewinn wird am Fall sichtbar.
            insert_event_row(
                con, subject_id=subject_id, event_kind=EVENT_KIND,
                payload={
                    "result_id": state["id"], "criterion": criterion_code,
                    "criterion_label": crit["label"], "extrem": extrem,
                    "confidence": confidence_code,
                    "confidence_label": conf["label"],
                    "quality": quality_code, "note": note or "",
                },
                created_by=actor_id, created_at=now, audit_seq=seq,
            )

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.ASSESSMENT_RECORDED,
            actor_id=actor_id, target_type="case", target_id=str(subject_id),
            meta=meta, after_audit=_after,
        )
        logger.info("Bewertung %s: Fall %s / %s / %s -> %s (%d)%s",
                    state["id"], subject_id, criterion_code, extrem,
                    confidence_code, c_ordinal,
                    (" + %s" % quality_code) if quality_code else "")
        return {"result_id": state["id"], "audit_seq": seq,
                "catalog_version": catver}

    # -------------------------------------------------------------- Statistik
    def stats(self, *, subject_ids: Optional[Sequence[int]] = None
              ) -> Dict[str, Any]:
        """
        Auswertung ueber den AKTUELLEN Stand (nicht ueber die Historie — sonst
        zaehlte ein oft korrigierter Fall mehrfach).

        subject_ids=None -> alle Faelle; [] -> keine (Scope 'eigene' ohne
        Zuweisung). Diese Unterscheidung ist Kapselung, kein Detail.

        HINWEIS zur Numerik: die Mittelwerte werden je KRITERIUM gebildet, nie
        ueber Kriterien hinweg — 'ordinal' bedeutet bei abuser_quality etwas
        anderes als bei location_quality (M011). Eine Zahl ueber alle Skalen
        waere Unsinn und wird deshalb gar nicht erst angeboten.
        """
        sql = ("SELECT criterion_code, extrem, confidence_code, "
               "       confidence_ordinal, quality_code, quality_ordinal "
               "FROM v_investigation_current")
        params: List[Any] = []
        if subject_ids is not None:
            if not subject_ids:
                return {"faelle": 0, "criteria": {}}
            sql += " WHERE subject_id IN (%s)" % ",".join("?" for _ in subject_ids)
            params.extend(int(u) for u in subject_ids)

        rows = [dict(r) for r in self._con.execute(sql, params).fetchall()]

        n_sql = "SELECT COUNT(DISTINCT subject_id) FROM v_investigation_current"
        if subject_ids is not None:
            n_sql += " WHERE subject_id IN (%s)" % ",".join("?" for _ in subject_ids)
        n_faelle = int(self._con.execute(n_sql, params).fetchone()[0])

        crit: Dict[str, Any] = {}
        for r in rows:
            key = r["criterion_code"]
            c = crit.setdefault(key, {
                "schwerste": {"n": 0, "conf_sum": 0, "conf_hist": {},
                              "qual_sum": 0, "qual_n": 0, "qual_hist": {}},
                "beste": {"n": 0, "conf_sum": 0, "conf_hist": {},
                          "qual_sum": 0, "qual_n": 0, "qual_hist": {}},
            })
            e = c[r["extrem"]]
            e["n"] += 1
            e["conf_sum"] += int(r["confidence_ordinal"])
            e["conf_hist"][r["confidence_code"]] = \
                e["conf_hist"].get(r["confidence_code"], 0) + 1
            if r["quality_code"] is not None:
                e["qual_n"] += 1
                e["qual_sum"] += int(r["quality_ordinal"] or 0)
                e["qual_hist"][r["quality_code"]] = \
                    e["qual_hist"].get(r["quality_code"], 0) + 1

        for _k, c in crit.items():
            for _e, v in c.items():
                v["conf_mittel"] = (round(v["conf_sum"] / v["n"], 2)
                                    if v["n"] else None)
                v["qual_mittel"] = (round(v["qual_sum"] / v["qual_n"], 2)
                                    if v["qual_n"] else None)

        return {"faelle": n_faelle, "criteria": crit}
