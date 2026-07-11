# =============================================================================
# management/capacity/capacity_calculator.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaet (Welle 0)
# =============================================================================
# CapacityCalculator — berechnet die verfuegbare Kapazitaet einer Person fuer
# einen Zeitraum aus den Kapazitaets-Daten (Schema m008; reine Leseoperation).
#
# MODELL (mc 2026-07-10):
#   Basis(Person, Zeitraum) = Summe ueber alle Kalendertage d in [start, end]:
#     0, wenn d ein (nicht geloeschter) Feiertag ist (ALLE Feiertage zaehlen;
#        Region ist vorerst nur informativ — regionale Ausnahmen werden per
#        individuellem Eintrag modelliert, Entscheidung 3),
#     sonst die Minuten des Wochentags aus der zum Tag AKTIVEN Arbeitszeit-Regel
#        (groesstes effective_from <= d, nicht geloescht, effective_to offen oder
#        >= d); keine Regel -> 0.
#
#   Verfuegbarkeits-Eintraege, die den Zeitraum ueberlappen (aktiv):
#     value_minutes = TOTAL fuer den GESAMTEN Eintrags-Zeitraum -> auf die
#        Ueberlappung anteilig nach Kalendertagen umgelegt (Entscheidung 1).
#     value_pct     = Prozent der BASIS der Ueberlappungstage.
#   Summe Einschraenkungen reduziert; Summe Garantien ist ein BODEN:
#     netto = max(Basis - Summe Einschraenkungen, Summe Garantien)
#   "Garantie bedeutet, drunter geht nicht" (Entscheidung 2). netto ist damit
#   nie negativ (Garantie >= 0).
#
# ZWECKBINDUNG: Planungs-/Auswertungshilfe, KEIN Mitarbeiter-Bewertungs-
#   instrument (Bauplan §11.4/§11.5).
#
# Beleg: Bauplan B7 v1.1 §11.4. Version: v0.7.358 · Build: 358 · 2026-07-10
# =============================================================================

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional

from management.capacity.capacity_errors import CapacityError

_WEEKDAY_COLS = ("mon_min", "tue_min", "wed_min", "thu_min", "fri_min",
                 "sat_min", "sun_min")


@dataclass(frozen=True)
class CapacityResult:
    person_id: int
    period_start: str
    period_end: str
    days: int              # Kalendertage im Zeitraum
    working_days: int      # Tage mit Basis > 0
    basis: int             # Basis-Minuten gesamt
    einschraenkungen: int  # Summe der Einschraenkungs-Beitraege (Minuten)
    garantie_boden: int    # Summe der Garantie-Beitraege (Minuten)
    netto: int             # verfuegbare Minuten (mit Garantie-Boden)


def _daterange(d0: date, d1: date):
    d = d0
    while d <= d1:
        yield d
        d += timedelta(days=1)


class CapacityCalculator:
    """Berechnet Kapazitaet(Person, Zeitraum). Rein lesend."""

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con

    def compute(self, person_id: int, period_start: str,
                period_end: str) -> CapacityResult:
        try:
            d0 = date.fromisoformat(period_start)
            d1 = date.fromisoformat(period_end)
        except ValueError as exc:
            raise CapacityError("Ungueltiges Datum: %s" % exc)
        if d1 < d0:
            raise CapacityError(
                "period_end (%s) liegt vor period_start (%s)."
                % (period_end, period_start))

        holidays = {r[0] for r in self._con.execute(
            "SELECT day FROM holiday WHERE deleted_at IS NULL")}
        wt_rules = self._load_worktime(person_id)

        # Tages-Basis vorberechnen (auch fuer die pct-Beitraege je Ueberlappung).
        day_basis: Dict[str, int] = {}
        basis = 0
        working_days = 0
        for d in _daterange(d0, d1):
            iso = d.isoformat()
            if iso in holidays:
                b = 0
            else:
                b = self._weekday_minutes(wt_rules, iso, d.weekday())
            day_basis[iso] = b
            basis += b
            if b > 0:
                working_days += 1

        einschr = 0
        garantie = 0
        for e in self._load_overlapping_entries(person_id, period_start,
                                                 period_end):
            contrib = self._entry_contribution(e, d0, d1, day_basis)
            if e["kind"] == "einschraenkung":
                einschr += contrib
            else:  # 'garantie'
                garantie += contrib

        netto = max(basis - einschr, garantie)
        days = (d1 - d0).days + 1
        return CapacityResult(
            person_id=person_id, period_start=period_start,
            period_end=period_end, days=days, working_days=working_days,
            basis=basis, einschraenkungen=einschr, garantie_boden=garantie,
            netto=netto)

    # ------------------------------------------------------------- internals
    def _load_worktime(self, person_id: int) -> List[dict]:
        cols = "effective_from, effective_to, " + ", ".join(_WEEKDAY_COLS)
        cur = self._con.execute(
            "SELECT %s FROM person_worktime "
            "WHERE person_id=? AND deleted_at IS NULL "
            "ORDER BY effective_from ASC, id ASC" % cols, (person_id,))
        names = [c[0] for c in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]

    def _weekday_minutes(self, wt_rules: List[dict], iso: str,
                         weekday: int) -> int:
        # Aktive Regel = groesstes effective_from <= iso, effective_to offen
        # oder >= iso. Regeln sind aufsteigend nach effective_from -> die letzte
        # passende gewinnt.
        chosen: Optional[dict] = None
        for r in wt_rules:
            if r["effective_from"] <= iso and (
                    r["effective_to"] is None or r["effective_to"] >= iso):
                chosen = r
        if chosen is None:
            return 0
        return int(chosen[_WEEKDAY_COLS[weekday]] or 0)

    def _load_overlapping_entries(self, person_id: int, start: str,
                                  end: str) -> List[dict]:
        cur = self._con.execute(
            "SELECT period_start, period_end, kind, value_pct, value_minutes "
            "FROM availability_entry "
            "WHERE person_id=? AND deleted_at IS NULL "
            "AND period_start <= ? AND period_end >= ?",
            (person_id, end, start))
        names = [c[0] for c in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]

    def _entry_contribution(self, e: dict, q0: date, q1: date,
                            day_basis: Dict[str, int]) -> int:
        e0 = date.fromisoformat(e["period_start"])
        e1 = date.fromisoformat(e["period_end"])
        ov0 = max(e0, q0)
        ov1 = min(e1, q1)
        if ov1 < ov0:
            return 0
        if e["value_minutes"] is not None:
            # Total ueber den Eintrag -> anteilig nach Kalendertagen umlegen.
            overlap_days = (ov1 - ov0).days + 1
            entry_days = (e1 - e0).days + 1
            return int(round(e["value_minutes"] * overlap_days / entry_days))
        # value_pct: Prozent der Basis der Ueberlappungstage.
        basis_overlap = sum(day_basis.get(d.isoformat(), 0)
                            for d in _daterange(ov0, ov1))
        return int(round(e["value_pct"] / 100.0 * basis_overlap))
