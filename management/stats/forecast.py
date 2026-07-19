# =============================================================================
# management/stats/forecast.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck (Idee 18 — Prognose-Modul, 3 Szenarien):
#   Schaetzt, wie lange die Abarbeitung des offenen Fallbestands voraussichtlich
#   dauert — in drei Szenarien (optimistisch / erwartet / pessimistisch).
#
#   TRANSPARENZ IST PFLICHT (Grundregel: keine Behauptung ohne Beleg). Das
#   Modell ist bewusst EINFACH und legt ALLE Annahmen offen (ForecastResult.
#   assumptions):
#     * Backlog  = Faelle mit status IN ('open','in_progress')  (cases).
#     * Abschluss-Signal = case_events.event_kind='approved' (Spiegel von
#       CASE_APPROVED; Beleg case_events_repo.py:48) im Rueckblickfenster.
#     * beobachtete Rate = Abschluesse / Fenster-Tage  [Faelle/Tag].
#     * Szenarien skalieren die Rate (Faktoren offengelegt).
#     * Restdauer = ceil(Backlog / Rate); Fertigstellung = heute + Restdauer.
#
#   EHRLICHKEIT BEI DUeNNER DATENLAGE (GR1): keine beobachteten Abschluesse ->
#   data_sufficient=False, Rate 0, Restdauer/Fertigstellung = None (KEINE
#   erfundene Zahl, keine Division durch 0). Backlog 0 -> Restdauer 0.
#
#   KAPAZITAET ist NUR KONTEXT: verfuegbare Netto-Minuten (CapacityCalculator)
#   werden — falls Daten vorhanden — informativ ausgewiesen, aber bewusst NICHT
#   in Abschluesse umgerechnet (dafuer fehlt ein belegter Aufwand-je-Fall; das
#   waere eine unbelegte Behauptung). Klar als Kontext gekennzeichnet.
#
#   Liest nur; now_ts wird injiziert -> deterministisch/testbar.
#
# Version: v0.7.446 · Build: 446 · 2026-07-19
# =============================================================================

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

_DAY = 86400
_BACKLOG_STATUSES = ("open", "in_progress")
_COMPLETION_KIND = "approved"   # case_events.event_kind (Beleg case_events_repo.py:48)


@dataclass(frozen=True)
class ForecastScenario:
    name: str                       # 'optimistisch' | 'erwartet' | 'pessimistisch'
    factor: float                   # Ratenfaktor (offengelegt)
    rate_per_day: float             # Faelle/Tag in diesem Szenario
    days_to_clear: Optional[int]    # Restdauer in Tagen (None = unbestimmbar)
    finish_day: Optional[str]       # ISO-Datum voraussichtl. Fertigstellung


@dataclass(frozen=True)
class ForecastResult:
    now_day: str
    backlog: int
    lookback_days: int
    completions_observed: int
    observed_rate_per_day: float
    data_sufficient: bool
    scenarios: List[ForecastScenario]
    assumptions: List[str]
    capacity_context: Optional[dict] = None


class Forecaster:
    """Backlog-Abbau-Prognose in drei Szenarien (transparent, belegt)."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def compute(self, *, now_ts: int, lookback_days: int = 30,
                factor_opt: float = 1.25, factor_pess: float = 0.75,
                horizon_days: int = 3650,
                include_capacity: bool = True,
                capacity_window_days: int = 30) -> ForecastResult:
        if lookback_days <= 0:
            raise ValueError("lookback_days muss > 0 sein")

        now_day = datetime.fromtimestamp(now_ts, tz=timezone.utc).date().isoformat()

        backlog = int(self._con.execute(
            "SELECT COUNT(*) FROM cases WHERE status IN (%s)"
            % ",".join("?" * len(_BACKLOG_STATUSES)),
            _BACKLOG_STATUSES).fetchone()[0])

        since = now_ts - lookback_days * _DAY
        completions = int(self._con.execute(
            "SELECT COUNT(*) FROM case_events "
            "WHERE event_kind=? AND created_at >= ?",
            (_COMPLETION_KIND, since)).fetchone()[0])

        observed_rate = completions / float(lookback_days)
        data_sufficient = completions > 0

        scenarios = [
            self._scenario("optimistisch", factor_opt, observed_rate, backlog,
                           now_ts, horizon_days),
            self._scenario("erwartet", 1.0, observed_rate, backlog,
                           now_ts, horizon_days),
            self._scenario("pessimistisch", factor_pess, observed_rate, backlog,
                           now_ts, horizon_days),
        ]

        assumptions = [
            "Backlog = Faelle mit status in %s (Tabelle cases)."
            % (", ".join(_BACKLOG_STATUSES)),
            "Abschluss-Signal = case_events.event_kind='approved' "
            "(Spiegel CASE_APPROVED) im Rueckblickfenster von %d Tagen."
            % lookback_days,
            "Beobachtete Rate = %d Abschluesse / %d Tage = %.4f Faelle/Tag."
            % (completions, lookback_days, observed_rate),
            "Szenario-Faktoren: optimistisch x%.2f, erwartet x1.00, "
            "pessimistisch x%.2f." % (factor_opt, factor_pess),
            "Restdauer = aufgerundet(Backlog / Rate); lineare Fortschreibung "
            "ohne Zu-/Abgaenge neuer Faelle.",
        ]
        if not data_sufficient:
            assumptions.append(
                "KEINE beobachteten Abschluesse im Fenster -> keine Prognose "
                "moeglich (Restdauer/Fertigstellung = unbestimmt).")
        if backlog == 0:
            assumptions.append("Backlog = 0 -> nichts abzuarbeiten.")

        capacity_context = None
        if include_capacity:
            capacity_context = self._capacity_context(
                now_ts, capacity_window_days, assumptions)

        return ForecastResult(
            now_day=now_day, backlog=backlog, lookback_days=lookback_days,
            completions_observed=completions,
            observed_rate_per_day=round(observed_rate, 6),
            data_sufficient=data_sufficient, scenarios=scenarios,
            assumptions=assumptions, capacity_context=capacity_context)

    # ------------------------------------------------------------- internals

    def _scenario(self, name: str, factor: float, base_rate: float,
                  backlog: int, now_ts: int, horizon_days: int
                  ) -> ForecastScenario:
        rate = base_rate * factor
        if backlog == 0:
            days: Optional[int] = 0
        elif rate <= 0:
            days = None
        else:
            days = int(math.ceil(backlog / rate))
        finish = None
        if days is not None and days <= horizon_days:
            finish = (datetime.fromtimestamp(now_ts, tz=timezone.utc).date()
                      + timedelta(days=days)).isoformat()
        return ForecastScenario(name=name, factor=factor,
                                rate_per_day=round(rate, 6),
                                days_to_clear=days, finish_day=finish)

    def _capacity_context(self, now_ts: int, window_days: int,
                          assumptions: List[str]) -> Optional[dict]:
        """
        Best-effort: Summe verfuegbarer Netto-Minuten aller Personen mit
        Arbeitszeitregeln ueber ein Vorwaertsfenster. NUR KONTEXT (nicht in
        Abschluesse umgerechnet). Voll abgesichert -> None bei fehlenden Daten.
        """
        try:
            from management.capacity.capacity_calculator import CapacityCalculator
            rows = self._con.execute(
                "SELECT DISTINCT person_id FROM person_worktime "
                "WHERE deleted_at IS NULL").fetchall()
            if not rows:
                assumptions.append(
                    "Kapazitaets-Kontext: keine Arbeitszeitdaten vorhanden.")
                return None
            d0 = datetime.fromtimestamp(now_ts, tz=timezone.utc).date()
            d1 = d0 + timedelta(days=window_days)
            calc = CapacityCalculator(self._con)
            total_netto = 0
            persons = 0
            for r in rows:
                res = calc.compute(int(r[0]), d0.isoformat(), d1.isoformat())
                total_netto += int(res.netto)
                persons += 1
            assumptions.append(
                "Kapazitaets-Kontext: %d Person(en), %d Netto-Minuten ueber %d "
                "Tage — KONTEXT, nicht in Abschluesse umgerechnet (kein belegter "
                "Aufwand je Fall)." % (persons, total_netto, window_days))
            return {"persons": persons, "netto_minutes": total_netto,
                    "window_days": window_days,
                    "window_start": d0.isoformat(), "window_end": d1.isoformat()}
        except Exception as exc:  # nie eskalieren — Kontext ist optional
            assumptions.append(
                "Kapazitaets-Kontext nicht verfuegbar (%s)." % exc)
            return None


def forecast_to_dict(result: ForecastResult) -> dict:
    """Serialisierung fuer Ausgabe/Pruefsumme (stabile Schluessel)."""
    return {
        "now_day": result.now_day,
        "backlog": result.backlog,
        "lookback_days": result.lookback_days,
        "completions_observed": result.completions_observed,
        "observed_rate_per_day": result.observed_rate_per_day,
        "data_sufficient": result.data_sufficient,
        "scenarios": [
            {"name": s.name, "factor": s.factor, "rate_per_day": s.rate_per_day,
             "days_to_clear": s.days_to_clear, "finish_day": s.finish_day}
            for s in result.scenarios
        ],
        "assumptions": result.assumptions,
        "capacity_context": result.capacity_context,
    }
