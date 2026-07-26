# =============================================================================
# management/metrics/metrics_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C (Build 542)
# =============================================================================
# Zweck:
#   Die Ermittler-Metriken. REIN LESEND, KEINE eigene Tabelle, KEINE Migration
#   ausser dem Rechte-Seed (M035).
#
# ── AGGREGIERT WIRD UEBER FAELLE, NICHT UEBER PERSONEN ──────────────────────
#
#   Das ist die tragende Entscheidung dieses Moduls, und sie ist im Code
#   sichtbar: es gibt hier KEIN 'GROUP BY person', KEIN 'GROUP BY assigned_to'
#   und keine Sortierung, aus der sich eine Rangfolge zwischen Personen
#   ablesen liesse. Ein Test haelt die Antwortschluessel gegen
#   VERBOTENE_KENNZAHLEN (metrics_vokabular.py) — die Zweckbindung ist damit
#   eine Zusicherung und keine Absichtserklaerung.
#
#   DIE LASTVERTEILUNG JE ERMITTLER GIBT ES BEREITS: /api/workload
#   (WorkloadRepo). Sie ist scope-behaftet und beantwortet die Frage 'wer hat
#   wie viel auf dem Tisch' — eine Verteilungsfrage der Leitung. Sie hier zu
#   wiederholen waere eine zweite Wahrheit UND haette die Metriken in die Naehe
#   dessen gerueckt, was sie ausdruecklich nicht sind.
#
# ── DIE ANLAUFZEIT MISST KEIN TEMPO ─────────────────────────────────────────
#
#   Gemessen wird die Spanne von der ZUWEISUNG bis zum ersten INHALTLICHEN
#   Ereignis (dieselbe Positivliste wie die Selbstpruefungssperre in
#   qs_repo.MITWIRKUNGS_EVENT_KINDS — es waere absurd, denselben Begriff
#   'inhaltliche Arbeit' an zwei Stellen verschieden zu fassen).
#
#   AUSGEWIESEN WERDEN MEDIAN UND QUARTILE, NICHT DER MITTELWERT. Ein
#   Mittelwert ueber Liegezeiten wird von wenigen sehr alten Faellen bestimmt
#   und sagt ueber den Regelfall nichts. Zusaetzlich steht die Zahl der Faelle
#   dabei, die NOCH KEIN inhaltliches Ereignis haben — sie fallen aus einer
#   Median-Rechnung heraus und waeren sonst unsichtbar, obwohl sie die
#   eigentliche Aussage sind.
#
# ── DIE SUBSTANZ IST TEUER UND DESHALB ABSCHALTBAR ──────────────────────────
#
#   'Faelle ohne Annotation trotz Zuweisung' verlangt EINEN DATEIZUGRIFF JE
#   FALL auf evidence_<uid>.db. Das ist dieselbe Kostenklasse wie die
#   Fristkomponente der Matrix (Build 538, Faktor 13-14 im Container, PROD
#   ungemessen). Der Block ist deshalb abschaltbar, seine Dauer wird gemessen
#   und ausgewiesen, und sein Fehlen wird BENANNT — nie stillschweigend als
#   'keine Auffaelligkeit'.
#
# ── AUSREISSER WERDEN BENANNT, NICHT BEWERTET ───────────────────────────────
#
#   Jeder Ausreisser traegt seinen GRUND im Klartext und den Satz, dass er ein
#   Hinweis auf Pruefbedarf AN DER AUSWERTUNG ist. Es gibt keine Schwere, keine
#   Punktzahl und keine Sortierung nach 'Schwere' — nur nach subject_id.
#
# Version: v0.8.542 · Build: 542 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from management.metrics.metrics_vokabular import (
    ABDECKUNG_KLASSEN,
    KENNZAHLEN,
    ZWECKBINDUNG,
    kennzahl_bedeutung,
)
from management.qs.qs_repo import MITWIRKUNGS_EVENT_KINDS

logger = logging.getLogger(__name__)

#: Ab wann eine Anlaufzeit als Ausreisser BENANNT wird (Tage). Sie steht hier
#  und nicht im Aufrufer, damit zwei Abrufe dieselbe Grenze haben. Die Zahl
#  faehrt in der Antwort mit — eine Schwelle, die man nicht sieht, laesst sich
#  nicht bestreiten.
ANLAUF_AUSREISSER_TAGE: int = 60

#: Ab welcher Abdeckung ein abgeschlossener Fall NICHT mehr auffaellt.
#  Darunter wird er benannt: ein Fall, der abgeschlossen wurde, ohne dass die
#  Kriterien bewertet sind, ist der Kernfall der Qualitaetssicherung.
ABDECKUNG_AUSREISSER_UNTER: float = 0.5


class MetricsRepo:
    """Aggregate ueber Faelle. Rein lesend, ohne Personenbezug."""

    def __init__(self, con: sqlite3.Connection,
                 evidence_dir: Optional[str] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._evidence_dir = evidence_dir

    # ------------------------------------------------------------- Bestand
    def _bestand(self) -> Dict[str, Any]:
        """
        Faelle je Bearbeitungsstand. GENERISCH gezaehlt (alle vorkommenden
        Werte), damit ein neuer Zustand nicht aus der Summe faellt — dieselbe
        Entscheidung wie bei der Datenlage des Fristenmonitors (Build 527).
        """
        rows = self._con.execute(
            "SELECT status, COUNT(*) AS n FROM cases GROUP BY status "
            "ORDER BY status").fetchall()
        je_status = {str(r["status"]): int(r["n"]) for r in rows}
        gesamt = sum(je_status.values())
        unzugewiesen = int(self._con.execute(
            "SELECT COUNT(*) FROM cases WHERE assigned_to IS NULL"
        ).fetchone()[0])
        return {
            "faelle_gesamt": gesamt,
            "je_status": je_status,
            "unzugewiesen": unzugewiesen,
            "bedeutung": kennzahl_bedeutung("bestand"),
        }

    # ------------------------------------------------------------ Abdeckung
    def _abdeckung(self) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Verteilung der Abdeckung ueber die Faelle, plus die Ausreisser.

        Die Werte kommen aus CoverageRepo und werden hier NICHT nachgerechnet —
        eine zweite Rechnung waere eine zweite Wahrheit ueber denselben
        Bestand.
        """
        from management.results.coverage_repo import CoverageRepo

        cov = CoverageRepo(self._con).coverage()
        faelle = list(cov.get("faelle") or [])

        klassen = {name: 0 for name, _lo, _hi in ABDECKUNG_KLASSEN}
        ausreisser: List[Dict[str, Any]] = []
        for f in faelle:
            a = f.get("abdeckung")
            if f.get("nie_bewertet") or a is None:
                klassen["nie_bewertet"] += 1
            else:
                for name, lo, hi in ABDECKUNG_KLASSEN:
                    if name == "nie_bewertet":
                        continue
                    if lo < float(a) <= hi or (lo < 0 and float(a) == 0.0):
                        klassen[name] += 1
                        break
            # AUSREISSER: ein ABGESCHLOSSENER Fall mit duenner Abdeckung. Ein
            # laufender Fall faellt hier ausdruecklich NICHT auf — dort ist die
            # Luecke ein Zwischenstand (dieselbe Regel wie in der QS-Ziehung).
            if str(f.get("status")) in ("closed", "approved"):
                if f.get("nie_bewertet"):
                    ausreisser.append({
                        "subject_id": int(f["subject_id"]),
                        "art": "abgeschlossen_ohne_bewertung",
                        "grund": "Der Fall ist abgeschlossen, aber KEIN "
                                 "Bewertungskriterium ist gesetzt.",
                    })
                elif (a is not None
                        and float(a) < ABDECKUNG_AUSREISSER_UNTER):
                    ausreisser.append({
                        "subject_id": int(f["subject_id"]),
                        "art": "abgeschlossen_duenn_bewertet",
                        "grund": "Der Fall ist abgeschlossen, die Abdeckung "
                                 "der Bewertungskriterien liegt aber bei %.0f %% "
                                 "(Schwelle %.0f %%)."
                                 % (float(a) * 100,
                                    ABDECKUNG_AUSREISSER_UNTER * 100),
                    })

        block = {
            "faelle_gesamt": len(faelle),
            "n_kriterien": cov.get("n_kriterien"),
            "nie_bewertet": int(cov.get("nie_bewertet") or 0),
            "klassen": klassen,
            "klassengrenzen": [
                {"code": n, "von": lo, "bis": hi}
                for n, lo, hi in ABDECKUNG_KLASSEN],
            "ausreisser_unter": ABDECKUNG_AUSREISSER_UNTER,
            "bedeutung": kennzahl_bedeutung("abdeckung"),
        }
        return block, ausreisser

    # ----------------------------------------------------------- Anlaufzeit
    def _anlaufzeit(self, now: int) -> Tuple[Dict[str, Any],
                                             List[Dict[str, Any]]]:
        """
        Zuweisung -> erstes INHALTLICHES Ereignis, je Fall. Aggregiert.

        DIE FAELLE OHNE INHALTLICHES EREIGNIS SIND DIE EIGENTLICHE AUSSAGE.
        Sie haben keine Anlaufzeit (es gibt kein Ende der Spanne) und fielen
        aus jeder Median-Rechnung heraus. Sie werden deshalb GETRENNT gezaehlt
        und, wenn die Zuweisung lange genug her ist, als Ausreisser BENANNT.
        """
        marks = ",".join("?" for _ in MITWIRKUNGS_EVENT_KINDS)
        # Erste ZUWEISUNG je Fall.
        zuweisung = {int(r[0]): int(r[1]) for r in self._con.execute(
            "SELECT subject_id, MIN(created_at) FROM case_events "
            "WHERE event_kind = 'assigned' GROUP BY subject_id").fetchall()}
        # Erstes INHALTLICHES Ereignis je Fall.
        inhalt = {int(r[0]): int(r[1]) for r in self._con.execute(
            "SELECT subject_id, MIN(created_at) FROM case_events "
            "WHERE event_kind IN (%s) GROUP BY subject_id" % marks,
            MITWIRKUNGS_EVENT_KINDS).fetchall()}

        spannen: List[int] = []
        ohne: List[int] = []
        ausreisser: List[Dict[str, Any]] = []
        for sid, ts_zu in sorted(zuweisung.items()):
            ts_in = inhalt.get(sid)
            if ts_in is None or ts_in < ts_zu:
                # Kein inhaltliches Ereignis NACH der Zuweisung.
                ohne.append(sid)
                tage_offen = max(0, (now - ts_zu) // 86400)
                if tage_offen >= ANLAUF_AUSREISSER_TAGE:
                    ausreisser.append({
                        "subject_id": sid,
                        "art": "ohne_inhaltliches_ereignis",
                        "grund": "Seit der Zuweisung sind %d Tage vergangen, "
                                 "ohne dass ein inhaltliches Ereignis "
                                 "vorliegt (Schwelle %d Tage)."
                                 % (tage_offen, ANLAUF_AUSREISSER_TAGE),
                    })
                continue
            tage = (ts_in - ts_zu) // 86400
            spannen.append(int(tage))
            if tage >= ANLAUF_AUSREISSER_TAGE:
                ausreisser.append({
                    "subject_id": sid,
                    "art": "lange_anlaufzeit",
                    "grund": "Zwischen Zuweisung und erstem inhaltlichen "
                             "Ereignis lagen %d Tage (Schwelle %d Tage)."
                             % (tage, ANLAUF_AUSREISSER_TAGE),
                })

        block: Dict[str, Any] = {
            "faelle_mit_zuweisung": len(zuweisung),
            "faelle_mit_anlaufzeit": len(spannen),
            "faelle_ohne_inhaltliches_ereignis": len(ohne),
            "schwelle_tage": ANLAUF_AUSREISSER_TAGE,
            "bedeutung": kennzahl_bedeutung("anlaufzeit"),
        }
        if spannen:
            geordnet = sorted(spannen)
            block.update({
                "median_tage": int(statistics.median(geordnet)),
                "min_tage": geordnet[0],
                "max_tage": geordnet[-1],
                "q1_tage": int(geordnet[len(geordnet) // 4]),
                "q3_tage": int(geordnet[(3 * len(geordnet)) // 4]),
            })
        else:
            # KEIN Mittelwert und keine 0: es gibt schlicht keine Spanne.
            block.update({"median_tage": None, "min_tage": None,
                          "max_tage": None, "q1_tage": None, "q3_tage": None})
        # DER MITTELWERT FEHLT ABSICHTLICH, und das steht in der Antwort:
        # sonst rechnet ihn irgendwann jemand nach und haelt ihn fuer
        # gleichwertig.
        block["kein_mittelwert"] = (
            "Es wird MEDIAN und QUARTIL ausgewiesen, kein Mittelwert: ein "
            "Mittelwert ueber Liegezeiten wird von wenigen sehr alten Faellen "
            "bestimmt und sagt ueber den Regelfall nichts.")
        return block, ausreisser

    # ------------------------------------------------------------- Substanz
    def _substanz(self) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Zugewiesene Faelle OHNE eine einzige Annotation.

        TEUER: ein Dateizugriff je Fall auf evidence_<uid>.db. Der Aufrufer
        entscheidet, ob dieser Block laeuft; ohne ihn steht in der Antwort
        ausdruecklich, dass NICHT NACHGESEHEN wurde (s. compute).
        """
        if not self._evidence_dir:
            raise RuntimeError(
                "Kein evidence-Verzeichnis uebergeben — es wurde NICHT "
                "nachgesehen.")
        basis = Path(self._evidence_dir)
        rows = self._con.execute(
            "SELECT subject_id FROM cases WHERE assigned_to IS NOT NULL "
            "ORDER BY subject_id").fetchall()

        ohne_datei = 0
        ohne_annotation: List[int] = []
        mit_annotation = 0
        unlesbar: Dict[str, int] = {}

        for r in rows:
            sid = int(r["subject_id"])
            pfad = basis / ("evidence_%d.db" % sid)
            if not pfad.exists():
                ohne_datei += 1
                continue
            try:
                con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
                try:
                    n = con.execute(
                        'SELECT COUNT(*) FROM "annotations" '
                        'WHERE deleted_at IS NULL').fetchone()[0]
                finally:
                    con.close()
            except sqlite3.Error as exc:
                # EIN LESEFEHLER WIRD MITGEFUEHRT und nicht als '0 Annotationen'
                # gewertet — sonst saehe ein unlesbarer Fall aus wie ein
                # unbearbeiteter (Lehre aus Build 527).
                schluessel = str(exc)
                unlesbar[schluessel] = unlesbar.get(schluessel, 0) + 1
                continue
            if int(n or 0) > 0:
                mit_annotation += 1
            else:
                ohne_annotation.append(sid)

        ausreisser = [{
            "subject_id": sid,
            "art": "zugewiesen_ohne_annotation",
            "grund": "Der Fall ist zugewiesen, enthaelt aber keine einzige "
                     "Annotation. Das ist ein Hinweis auf fehlende SUBSTANZ "
                     "in der Akte.",
        } for sid in ohne_annotation]

        return {
            "geprueft": True,
            "faelle_zugewiesen": len(rows),
            "mit_annotation": mit_annotation,
            "ohne_annotation": len(ohne_annotation),
            "ohne_evidence_datei": ohne_datei,
            "unlesbar": unlesbar,
            "bedeutung": kennzahl_bedeutung("substanz"),
        }, ausreisser

    # -------------------------------------------------------------- Rechnen
    def compute(self, *, now_ts: Optional[int] = None,
                mit_substanz: bool = False) -> Dict[str, Any]:
        """
        Alle Kennzahlen. REIN LESEND.

        mit_substanz=False laesst den teuren Block weg. Die Antwort sagt dann
        ausdruecklich, dass NICHT NACHGESEHEN wurde — sie behauptet nicht, es
        gebe keine Faelle ohne Substanz. Muster: die Fristkomponente der Matrix
        (Build 538).
        """
        now = int(time.time()) if now_ts is None else int(now_ts)
        t_start = time.monotonic()
        stichtag = datetime.fromtimestamp(
            now, tz=timezone.utc).date().isoformat()
        hinweise: List[str] = []
        fehlende_quellen: List[str] = []
        ausreisser: List[Dict[str, Any]] = []

        bestand = self._bestand()

        try:
            abdeckung, a1 = self._abdeckung()
            ausreisser.extend(a1)
        except Exception as exc:                        # noqa: BLE001
            logger.exception("Metriken: Abdeckung nicht lesbar")
            abdeckung = {"fehler": str(exc)}
            fehlende_quellen.append("Abdeckung (%s)" % exc)

        try:
            anlaufzeit, a2 = self._anlaufzeit(now)
            ausreisser.extend(a2)
        except Exception as exc:                        # noqa: BLE001
            logger.exception("Metriken: Anlaufzeit nicht lesbar")
            anlaufzeit = {"fehler": str(exc)}
            fehlende_quellen.append("Anlaufzeit (%s)" % exc)

        dauer_substanz_ms: Optional[int] = None
        if not mit_substanz:
            substanz = {
                "geprueft": False,
                "hinweis": "NICHT NACHGESEHEN. Dieser Block oeffnet EINE "
                           "Datei je zugewiesenem Fall und wurde nicht "
                           "angefordert. Das ist ausdruecklich NICHT dasselbe "
                           "wie 'keine Faelle ohne Substanz'.",
                "bedeutung": kennzahl_bedeutung("substanz"),
            }
            fehlende_quellen.append(
                "Substanz (nicht angefordert: mit_substanz=False)")
        else:
            t_sub = time.monotonic()
            try:
                substanz, a3 = self._substanz()
                ausreisser.extend(a3)
            except Exception as exc:                    # noqa: BLE001
                logger.exception("Metriken: Substanz nicht lesbar")
                substanz = {"geprueft": False, "fehler": str(exc),
                            "bedeutung": kennzahl_bedeutung("substanz")}
                fehlende_quellen.append("Substanz (%s)" % exc)
            finally:
                dauer_substanz_ms = int((time.monotonic() - t_sub) * 1000)

        # Ausreisser: nach subject_id sortiert und NICHT nach 'Schwere' — es
        # gibt keine Schwere. Eine Sortierung nach Auffaelligkeit waere eine
        # Rangfolge, und die stellt dieses Werkzeug nicht her.
        ausreisser.sort(key=lambda a: (int(a["subject_id"]), a["art"]))

        if ausreisser:
            hinweise.insert(0,
                "%d Auffaelligkeit(en) benannt. EIN AUSREISSER IST EIN HINWEIS "
                "AUF PRUEFBEDARF AN DER AUSWERTUNG und kein Befund ueber eine "
                "Person. Er ist nicht bewertet, nicht gewichtet und nicht nach "
                "Schwere geordnet." % len(ausreisser))
        if fehlende_quellen:
            hinweise.insert(0,
                "NICHT VOLLSTAENDIG ERHOBEN: %s. Die betroffenen Zahlen fehlen "
                "— sie sind NICHT null." % "; ".join(fehlende_quellen))

        return {
            "stichtag": stichtag,
            "kennzahlen": list(KENNZAHLEN),
            "bestand": bestand,
            "abdeckung": abdeckung,
            "anlaufzeit": anlaufzeit,
            "substanz": substanz,
            "ausreisser": ausreisser,
            "fehlende_quellen": fehlende_quellen,
            "hinweise": hinweise,
            "dauer_gesamt_ms": int((time.monotonic() - t_start) * 1000),
            "dauer_substanz_ms": dauer_substanz_ms,
            "zweckbindung": ZWECKBINDUNG,
            "ist_kein_bewertungsinstrument": True,
            "keine_personenrangfolge": True,
        }
