# =============================================================================
# management/cases/cases_batch_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Zuweisung (Build 534)
# =============================================================================
# Zweck:
#   SAMMELZUWEISUNG: viele Faelle in EINEM Vorgang einem Ermittler zuweisen
#   und/oder ihre Prioritaet setzen.
#
# ANLASS (mc 2026-07-25): "Ich habe einen Ermittler, dem ich gestern ueber 80
#   Faelle zuweisen musste. Das musste ich einzeln machen." Jede Einzelzuweisung
#   war ein eigener Netzaufruf, eine eigene Transaktion und ein eigener
#   Neuaufbau der Seite — und weil die Liste sich dabei neu sortierte, traf ein
#   rascher Klick regelmaessig die falsche Zeile. Der Kern des Problems ist
#   nicht die Oberflaeche, sondern dass es fuer 'viele Faelle auf einmal'
#   keinen Schreibweg gab.
#
# DIE DREI ENTSCHEIDUNGEN, DIE DIESE KLASSE TRAEGT:
#
#   1) ERST PRUEFEN, DANN SCHREIBEN. Alle Angaben werden VOLLSTAENDIG geprueft,
#      bevor die Transaktion aufgeht: existiert jeder Fall, ist der Empfaenger
#      Ermittler, liegt jede Prioritaet im erlaubten Bereich. Grund: ein
#      Rollback nach 79 von 80 Schreibvorgaengen ist teuer und, schlimmer, er
#      verschleiert die Ursache. Ein Fehler soll VOR dem ersten Byte feststehen
#      und benannt sein. Geprueft wird gegen dieselbe Verbindung, in der
#      anschliessend geschrieben wird.
#
#   2) ALLES ODER NICHTS. Die eigentlichen Schreibvorgaenge laufen in EINER
#      Transaktion (CoordinatorWriter.audited_write_many). Bricht einer ab,
#      bleibt KEINER stehen. Ein halb ausgefuehrter Stapel waere der
#      schlechteste denkbare Zustand: die Liste zeigt danach eine Mischung, und
#      niemand kann sagen, welche Zuweisung gewollt und welche ein Rest war.
#
#   3) EIN BELEG JE FALL, NICHT EINER JE STAPEL. 80 Zuweisungen erzeugen 80
#      audit_log-Eintraege (und, wo die Prioritaet mitgeht, weitere 80). Ein
#      Sammelbeleg waere kuerzer und forensisch wertlos — man koennte einer
#      einzelnen Fallzuweisung dann keinen Beleg mehr zuordnen. Die
#      Zusammengehoerigkeit ist ueber die fortlaufenden seq der Hash-Kette
#      ohnehin ablesbar.
#
# UNVERAENDERTE WERTE WERDEN NICHT GESCHRIEBEN — ABER GEMELDET:
#   Wird ein Fall dem Ermittler zugewiesen, dem er ohnehin schon gehoert, ist
#   das KEINE Zustandsaenderung. Ein Audit-Eintrag dafuer waere kein Beleg,
#   sondern Rauschen — und Rauschen in einer Beweiskette ist teuer, weil jede
#   Zeile spaeter erklaert werden muss. Solche Faelle werden deshalb
#   uebersprungen, ABER NICHT STILL: sie stehen einzeln in der Antwort
#   ('unveraendert') und die Oberflaeche zeigt sie an. Das ist der Unterschied
#   zwischen 'uebergangen' und 'still uebersprungen' (Grundregel 1).
#
# WAS DIESE KLASSE NICHT TUT: Status setzen. Der Auftrag vom 2026-07-26 nennt
#   fuer den Stapel ausdruecklich Ermittler und Prioritaet. Ein Statuswechsel
#   ist eine fachliche Aussage ueber den Bearbeitungsstand eines EINZELNEN
#   Falls; ihn versehentlich ueber 80 Faelle zu ziehen, waere schwer
#   zurueckzunehmen. Nachruestbar ist er jederzeit — CasesRepo hat set_status,
#   es fehlte nur die Absicht.
#
# Version: v0.8.534 · Build: 534 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter, WriteUnit

logger = logging.getLogger(__name__)


class CasesBatchError(Exception):
    """
    Fachlicher Fehler der Sammelzuweisung (vor dem ersten Schreibvorgang).

    'zeilen' nennt die beanstandeten Eintraege einzeln. Eine Fehlermeldung
    'irgendwas stimmt nicht' waere bei 80 Eintraegen unbrauchbar.
    """

    def __init__(self, detail: str, zeilen: Optional[Sequence[str]] = None
                 ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.zeilen: Tuple[str, ...] = tuple(zeilen or ())


@dataclass(frozen=True)
class BatchChange:
    """
    EINE gewuenschte Aenderung an EINEM Fall.

    'person_id' und 'priority' sind je fuer sich optional — der Stapel darf nur
    zuweisen, nur die Prioritaet setzen oder beides. Sie sind aber NICHT beide
    weglassbar; ein Eintrag ohne Aenderungswunsch ist ein Eingabefehler und
    wird als solcher gemeldet.

    person_id=None BEDEUTET ETWAS: 'Zuweisung entziehen'. Damit sich das von
    'nicht angegeben' unterscheiden laesst, gibt es das eigene Kennzeichen
    'assign' — ohne das waere ein Entzug nicht ausdrueckbar (dasselbe Problem
    loest der Einzelendpunkt mit dem Wachwert '__missing__').
    """
    subject_id: int
    assign: bool = False
    person_id: Optional[int] = None
    priority: Optional[int] = None


@dataclass(frozen=True)
class BatchResult:
    """Was mit EINEM Fall geschehen ist — je Fall genau eine Zeile."""
    subject_id: int
    #: 'geschrieben' | 'unveraendert'
    ergebnis: str
    #: Klartext fuer die Oberflaeche ("zugewiesen an #4, Prioritaet 2").
    detail: str
    #: seq der erzeugten audit_log-Belege (leer bei 'unveraendert').
    audit_seqs: Tuple[int, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {"subject_id": self.subject_id, "ergebnis": self.ergebnis,
                "detail": self.detail, "audit_seqs": list(self.audit_seqs)}


class CasesBatchRepo:
    """
    Auditierte SAMMEL-Schreibmethode auf der Tabelle cases.

    Benutzt dieselben Schreibeinheiten wie CasesRepo (assign_unit,
    priority_unit) — es gibt keine zweite Fassung der UPDATE-Anweisungen.
    """

    def __init__(self, con: sqlite3.Connection, writer: CoordinatorWriter,
                 *, priority_min: int, priority_max: int) -> None:
        self._con = con
        self._writer = writer
        self._cases = CasesRepo(con, writer)
        self._pmin = int(priority_min)
        self._pmax = int(priority_max)

    # ------------------------------------------------------------- Pruefungen
    def _pruefe(self, changes: Sequence[BatchChange]
                ) -> Dict[int, Tuple[Optional[int], int]]:
        """
        Prueft den GESAMTEN Stapel vor dem ersten Schreibvorgang.

        -> {subject_id: (aktuell_assigned_to, aktuell_priority)} fuer den
        Abgleich, welche Aenderung ueberhaupt eine ist.

        Wirft CasesBatchError mit EINZELN benannten Zeilen. Es wird bewusst
        NICHT beim ersten Fehler abgebrochen: wer 80 Zeilen schickt, will alle
        Beanstandungen auf einmal sehen und nicht achtzig Mal nacheinander.
        """
        if not changes:
            raise CasesBatchError("Leerer Stapel — es wurde nichts angegeben.")

        fehler: List[str] = []

        # (a) Doppelte Faelle. Zwei Aenderungen am selben Fall in einem Stapel
        #     sind keine Kleinigkeit: welche gilt, haengt dann von der
        #     Reihenfolge ab, und die ist in einer Oberflaeche nicht sichtbar.
        gesehen: Dict[int, int] = {}
        for c in changes:
            gesehen[c.subject_id] = gesehen.get(c.subject_id, 0) + 1
        for sid, n in sorted(gesehen.items()):
            if n > 1:
                fehler.append("Fall %d ist %d-mal im Stapel." % (sid, n))

        # (b) Jeder Eintrag muss etwas wollen.
        for c in changes:
            if not c.assign and c.priority is None:
                fehler.append("Fall %d: weder Zuweisung noch Prioritaet "
                              "angegeben." % c.subject_id)

        # (c) Prioritaeten im erlaubten Bereich.
        for c in changes:
            if c.priority is not None and not (
                    self._pmin <= c.priority <= self._pmax):
                fehler.append("Fall %d: Prioritaet %d ausserhalb %d..%d."
                              % (c.subject_id, c.priority,
                                 self._pmin, self._pmax))

        # (d) Jeder Fall muss existieren — und wir holen gleich den IST-Stand.
        ist: Dict[int, Tuple[Optional[int], int]] = {}
        sids = sorted(gesehen.keys())
        if sids:
            platzhalter = ",".join("?" * len(sids))
            for row in self._con.execute(
                    "SELECT subject_id, assigned_to, priority FROM cases "
                    "WHERE subject_id IN (%s)" % platzhalter, tuple(sids)):
                ist[int(row[0])] = (
                    None if row[1] is None else int(row[1]), int(row[2]))
            for sid in sids:
                if sid not in ist:
                    fehler.append("Fall %d existiert nicht." % sid)

        # (e) Jeder Empfaenger muss Ermittler sein. Nur EINMAL je Person
        #     abgefragt, auch wenn 80 Zeilen auf sie zeigen.
        empfaenger = sorted({c.person_id for c in changes
                             if c.assign and c.person_id is not None})
        for pid in empfaenger:
            row = self._con.execute(
                "SELECT is_investigator FROM person WHERE id=?",
                (pid,)).fetchone()
            if row is None:
                fehler.append("Person %d gibt es nicht." % pid)
            elif not row[0]:
                fehler.append("Person %d ist kein Ermittler." % pid)

        if fehler:
            raise CasesBatchError(
                "%d Beanstandung(en) — es wurde NICHTS geschrieben."
                % len(fehler), fehler)
        return ist

    # ---------------------------------------------------------------- Schreiben
    def apply(self, changes: Sequence[BatchChange], *,
              actor_id: Optional[int] = None,
              meta: Optional[Any] = None,
              now: Optional[int] = None) -> List[BatchResult]:
        """
        Fuehrt den gesamten Stapel aus: erst pruefen, dann EINE Transaktion.

        Rueckgabe: je EINGEREICHTEM Fall genau eine Zeile — auch fuer die
        unveraenderten. Wer 80 Faelle schickt, bekommt 80 Zeilen zurueck; eine
        fehlende waere eine stille Auslassung.

        'now' ist injizierbar (deterministische Tests), wie ueberall in diesem
        Projekt.
        """
        ist = self._pruefe(changes)
        now = int(time.time()) if now is None else int(now)

        einheiten: List[WriteUnit] = []
        # Je Fall: an welchen Stellen der Ergebnisliste seine seq landen.
        bauplan: List[Tuple[BatchChange, List[int], List[str]]] = []

        for c in changes:
            ist_assigned, ist_priority = ist[c.subject_id]
            indizes: List[int] = []
            texte: List[str] = []

            if c.assign and c.person_id != ist_assigned:
                indizes.append(len(einheiten))
                einheiten.append(self._cases.assign_unit(
                    c.subject_id, c.person_id, actor_id=actor_id, meta=meta,
                    now=now))
                texte.append("Zuweisung entzogen" if c.person_id is None
                             else "zugewiesen an Person %d" % c.person_id)

            if c.priority is not None and c.priority != ist_priority:
                indizes.append(len(einheiten))
                einheiten.append(self._cases.priority_unit(
                    c.subject_id, c.priority, actor_id=actor_id, meta=meta,
                    now=now))
                texte.append("Prioritaet %d" % c.priority)

            bauplan.append((c, indizes, texte))

        seqs = self._writer.audited_write_many(einheiten)

        ergebnisse: List[BatchResult] = []
        for c, indizes, texte in bauplan:
            if not indizes:
                # KEIN stiller Uebersprung: der Fall steht in der Antwort und
                # bekommt seinen Grund (siehe Modulkopf).
                ergebnisse.append(BatchResult(
                    subject_id=c.subject_id, ergebnis="unveraendert",
                    detail="Der gewuenschte Stand lag bereits vor."))
                continue
            ergebnisse.append(BatchResult(
                subject_id=c.subject_id, ergebnis="geschrieben",
                detail=", ".join(texte),
                audit_seqs=tuple(seqs[i] for i in indizes)))

        geschrieben = sum(1 for r in ergebnisse if r.ergebnis == "geschrieben")
        logger.info("Sammelzuweisung: %d Fall/Faelle eingereicht, %d "
                    "geschrieben, %d unveraendert, %d Beleg(e).",
                    len(ergebnisse), geschrieben,
                    len(ergebnisse) - geschrieben, len(seqs))
        return ergebnisse
