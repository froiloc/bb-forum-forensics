# =============================================================================
# management/gateway/coordinator_writer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Der EINZIGE zulässige Schreibpfad auf die Management-Tabellen der
#   coordinator.db (ab Tag 2: cases, case_events; später notifications, backups).
#   Bindet fachlichen Write und zugehörigen Audit-Eintrag in EINE Transaktion:
#   entweder beide committen oder keines von beidem. Damit existiert kein
#   Management-Write ohne Audit-Eintrag und kein Audit-Eintrag ohne seinen Write.
#   Das ist der forensische Kern des Management-Interfaces.
#   (Beleg: Bauplan B7 v0.2 §2.6, mc 2026-07-01)
#
# Nebenläufigkeit:
#   transaction() öffnet BEGIN IMMEDIATE — die Schreibsperre wird sofort
#   gehalten, sodass das Tip-Lesen der Hash-Kette + der Insert atomar und gegen
#   konkurrierende Schreiber serialisiert sind (kein Race auf prev_hash).
#
# Build 533 (Sammelzuweisung): audited_write_many() — MEHRERE fachliche Writes
#   mit je EIGENEM Audit-Beleg in EINER Transaktion.
#
#   ANLASS: mc musste am 2026-07-25 ueber 80 Faelle einzeln zuweisen. Jede
#   Einzelzuweisung war eine eigene Transaktion; ein Abbruch in der Mitte haette
#   einen Zustand hinterlassen, den niemand mehr rekonstruieren kann ("welche
#   der 80 sind durch?"). Mit einem Rahmen um alle gilt wieder: entweder alle
#   oder keine.
#
#   WAS SICH NICHT AENDERT — und das ist der Punkt: JEDER fachliche Write
#   behaelt seinen EIGENEN audit_log-Eintrag. 80 Zuweisungen ergeben 80 Belege,
#   nicht einen Sammelbeleg. Ein Sammelbeleg waere bequemer und forensisch
#   wertlos: man koennte einer einzelnen Fallzuweisung dann keinen Beleg mehr
#   zuordnen. Die Belege sind ueber die Hash-Kette ohnehin verkettet, ihre
#   Zusammengehoerigkeit ist also aus den fortlaufenden seq ablesbar.
#
#   audited_write() ist seit Build 533 der Einzelfall von audited_write_many()
#   — die Reihenfolge Write -> Audit -> after_audit steht damit an genau EINER
#   Stelle. Zwei Kopien derselben Reihenfolge waeren zwei Wahrheiten, von denen
#   irgendwann eine gepflegt wird und die andere nicht.
#
# Version: v0.8.533 · Build: 533 · 2026-07-26 (audited_write_many)
#   Build 313: after_audit-Hook, Bauplan B7 v0.8 §8.3
# =============================================================================

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

from management.audit.audit_log import AuditLog

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WriteUnit:
    """
    EIN fachlicher Write samt seinem Audit-Beleg — die Einheit, aus der sowohl
    der Einzel- als auch der Sammelschreibweg besteht.

    Die Felder entsprechen genau den Parametern von audited_write(); die
    Einheit existiert, damit ein Aufrufer sie BAUEN kann, ohne sie sofort
    ausfuehren zu muessen (CasesRepo._assign_unit et al.). Genau das macht die
    Sammelzuweisung moeglich, ohne die Schreiblogik ein zweites Mal
    hinzuschreiben.

    frozen=True: eine einmal gebaute Einheit wird nicht mehr veraendert. Wer
    etwas anderes schreiben will, baut eine neue.
    """
    do_write: Callable[[sqlite3.Connection], Optional[Dict[str, Any]]]
    event_type: str
    actor_id: Optional[int] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    meta: Optional[Any] = None
    after_audit: Optional[Callable[[sqlite3.Connection, int], None]] = None


class CoordinatorWriter:
    """Atomares Write+Audit-Gateway für coordinator.db."""

    def __init__(self, con: sqlite3.Connection, audit: AuditLog) -> None:
        self._con = con
        # Explizite Transaktionssteuerung (siehe MigrationRunner).
        self._con.isolation_level = None
        self._audit = audit

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """
        Schreibtransaktion mit sofortiger Sperre. Bei Erfolg COMMIT, bei jeder
        Exception ROLLBACK (es bleibt weder Write noch Audit-Eintrag zurück).
        """
        self._con.execute("BEGIN IMMEDIATE")
        try:
            yield self._con
            self._con.execute("COMMIT")
        except Exception:
            self._con.execute("ROLLBACK")
            raise

    def audited_write(
        self,
        *,
        do_write: Callable[[sqlite3.Connection], Optional[Dict[str, Any]]],
        event_type: str,
        actor_id: Optional[int],
        target_type: Optional[str],
        target_id: Optional[str],
        meta: Optional[Any] = None,
        after_audit: Optional[Callable[[sqlite3.Connection, int], None]] = None,
    ) -> int:
        """
        Führt do_write(con) aus und schreibt im selben Transaktionsrahmen den
        zugehörigen Audit-Eintrag. do_write liefert den Audit-Payload (dict) für
        das Ereignis (oder None -> leeres Payload).

        after_audit(con, seq) — optionaler Hook, der NACH dem Audit-Append,
        aber noch INNERHALB derselben Transaktion läuft. Er existiert, damit
        abgeleitete Lesemodell-Zeilen (z. B. case_events, Build 313) die
        exakte seq ihres audit_log-Belegs tragen können; die Kopplung
        Write + Audit + Lesemodell committet atomar oder gar nicht.
        Wirft after_audit, wird die GESAMTE Transaktion zurückgerollt —
        es bleibt weder Write noch Audit-Eintrag noch Lesemodell-Zeile
        zurück (Grundregel 1: keine stille Teil-Persistenz).
        (Beleg: Bauplan B7 v0.8 §8.3, mc 2026-07-02)

        Gibt die seq des Audit-Eintrags zurück.

        Build 533: delegiert an audited_write_many() — der Einzelfall ist die
        Liste mit einem Element. Verhalten und Rückgabe unverändert.
        """
        seq = self.audited_write_many([WriteUnit(
            do_write=do_write, event_type=event_type, actor_id=actor_id,
            target_type=target_type, target_id=target_id, meta=meta,
            after_audit=after_audit,
        )])[0]
        logger.debug(
            "audited_write: type=%s target=%s/%s -> audit seq=%d",
            event_type, target_type, target_id, seq,
        )
        return seq

    def audited_write_many(self, units: Sequence[WriteUnit]) -> List[int]:
        """
        Führt MEHRERE WriteUnits in EINER Transaktion aus und gibt ihre
        audit_log-seq in der Reihenfolge der Einheiten zurück (Build 533).

        Jede Einheit erhält ihren EIGENEN Audit-Eintrag — es gibt keinen
        Sammelbeleg (Begründung im Modulkopf). Wirft irgendeine Einheit, wird
        die GESAMTE Transaktion zurückgerollt: es bleibt weder ein Write noch
        ein Audit-Eintrag noch eine Lesemodell-Zeile zurück, auch nicht von den
        bereits durchgelaufenen Einheiten (Grundregel 1: keine stille
        Teil-Persistenz).

        EINE LEERE LISTE ist kein Fehler, aber auch kein stiller Erfolg: sie
        öffnet gar keine Transaktion (eine leere BEGIN IMMEDIATE-Transaktion
        würde die Schreibsperre ohne Zweck nehmen) und wird protokolliert. Wer
        nichts zu schreiben hat, soll das an der leeren Rückgabe merken.
        """
        if not units:
            logger.info("audited_write_many: keine Einheit — nichts zu tun, "
                        "keine Transaktion eröffnet.")
            return []

        seqs: List[int] = []
        with self.transaction() as con:
            for unit in units:
                payload = unit.do_write(con)
                if payload is None:
                    payload = {}
                seq = self._audit.append(
                    event_type=unit.event_type,
                    actor_id=unit.actor_id,
                    target_type=unit.target_type,
                    target_id=unit.target_id,
                    payload=payload,
                    meta=unit.meta,
                )
                if unit.after_audit is not None:
                    unit.after_audit(con, seq)
                seqs.append(seq)
        logger.debug("audited_write_many: %d Einheit(en) -> seq %s..%s",
                     len(seqs), seqs[0], seqs[-1])
        return seqs
