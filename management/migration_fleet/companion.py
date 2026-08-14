# =============================================================================
# management/migration_fleet/companion.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# MigrationCompanion — Migrations-Ausfuehrung Scheibe 4/4 (Build 320).
#
#   Der gefuehrte, TEILAUTOMATISIERTE Begleiter (Leitfaden v0.2 §7): KEINE
#   Vollautomatisierung. Er buendelt die bestehenden Bausteine (Reconciler 316,
#   Planner 316, Executor 319, Ledger 318) zu einem Ablauf mit klaren TOREN und
#   sorgt dafuer, dass der Administrator NICHTS vergisst und auf Auffaelligkeiten
#   HINGEWIESEN wird. Die Entscheidungen bleiben beim Menschen (explizite
#   Bestaetigung + Gegenzeichnung).
#
#   Reine STEUERUNG — kein neuer Datenpfad. Der Companion fuehrt selbst keine
#   Migration aus; er ruft den Executor (safe-by-design) auf und verweigert die
#   Ausfuehrung, solange eine Vorpruefung blockiert.
#
#   Tore der Vorpruefung (preflight):
#     - KATALOG_DRIFT      : Katalog/Code stimmen nicht ueberein (catalog-sync?)
#     - LEDGER_KETTE       : migration_runs-Hashkette fehlerhaft (Manipulation?)
#     - UNTERBROCHENE_LAEUFE: 'started' ohne Abschluss aus frueherem Lauf
#     - KEIN_BACKUP_DIR    : Pflicht-Backup-Ziel fehlt (nur fuer Ausfuehrung)
#   Erst wenn ALLE Tore offen sind UND der Mensch explizit bestaetigt
#   (confirm=True), wird ausgefuehrt.
#
# Beleg: Datenmigrationsleitfaden_AIW.md v0.2 §7/§8/§10, Bauplan Migrations-
#        Ausfuehrung v0.1 §1 (317-320), management/migration_fleet/{executor,
#        ledger,catalog,planner,migration_db}, mc 2026-07-03.
# Version: v0.8.723 · Build: 723 · 2026-08-14 (Rueckweg durchgereicht, zwei Fehlerstatus)
# =============================================================================

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from management.migration_fleet.catalog import CatalogReconciler
from management.migration_fleet.executor import (
    ExecutionResult, FEHLERSTATUS, FleetExecutor,
)
from management.migration_fleet.ledger import MigrationLedger
from management.migration_fleet.migration_db import MigrationDb, RegistryEntry
from management.migration_fleet.planner import TargetDb
from management.migration_fleet.rueckweg import Rueckweg

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Blocker:
    code: str
    message: str


@dataclass
class PreflightResult:
    ok: bool
    blockers: List[Blocker] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class CompanionResult:
    executed: bool
    preflight: PreflightResult
    results: List[ExecutionResult] = field(default_factory=list)
    reason: str = ""


@dataclass
class SummaryReport:
    chain_ok: bool
    registry: List[RegistryEntry] = field(default_factory=list)
    recent_runs: List = field(default_factory=list)
    interrupted: List = field(default_factory=list)
    reminders: List[str] = field(default_factory=list)


class MigrationCompanion:
    """Gefuehrter Begleiter fuer die Beweis-DB-Migration (Steuerung, kein Datenpfad)."""

    def __init__(self, mdb: MigrationDb, ledger: MigrationLedger, *,
                 backup_dir: Optional[str] = None,
                 operator: Optional[str] = None,
                 packages: Optional[Dict] = None,
                 rueckweg: Optional[Rueckweg] = None) -> None:
        self._mdb = mdb
        self._ledger = ledger
        self._backup_dir = backup_dir
        self._operator = operator
        self._reconciler = CatalogReconciler(mdb, packages)
        # 'rueckweg' wird nur DURCHGEREICHT (Build 723). Der Companion trifft
        # hier wie ueberall keine eigene Entscheidung; er ermoeglicht nur,
        # den Rueckweg im Test zu stellen, ohne den Ausfuehrer zu umgehen.
        self._executor = FleetExecutor(
            mdb, ledger, backup_dir=backup_dir, operator=operator,
            packages=packages, rueckweg=rueckweg)

    # ------------------------------------------------------- Phase A: Vorpruefung
    def preflight(self, *, require_backup_dir: bool = False) -> PreflightResult:
        """
        Prueft die Tore. Blockiert bei Katalog/Code-Drift, fehlerhafter
        Ledger-Kette, unterbrochenen Laeufen und (fuer Ausfuehrung) fehlendem
        Backup-Ziel. Keine stille Auslassung (Grundregel 1): jede Auffaelligkeit
        wird als Blocker mit handlungsleitender Meldung ausgewiesen.
        """
        blockers: List[Blocker] = []
        notes: List[str] = []

        report = self._reconciler.reconcile()
        if report.has_drift:
            blockers.append(Blocker(
                "KATALOG_DRIFT",
                "Katalog/Code-Drift (modified=%s, uncataloged=%s, missing=%s). "
                "Bitte 'catalog-sync' ausfuehren bzw. Code/Katalog pruefen."
                % (report.modified, report.uncataloged, report.missing_module)))
        else:
            notes.append("Katalog/Code: kein Drift (%d Eintraege ok)."
                         % len(report.ok))

        chain = self._ledger.verify_chain()
        if not chain.ok:
            blockers.append(Blocker(
                "LEDGER_KETTE",
                "Ledger-Hashkette fehlerhaft: %s. Manipulation/Korruption pruefen."
                % chain.detail))

        interrupted = self._ledger.interrupted_runs()
        if interrupted:
            blockers.append(Blocker(
                "UNTERBROCHENE_LAEUFE",
                "%d unterbrochene(r) Lauf(e) aus fruehrer Sitzung: %s. Vor "
                "Fortsetzung pruefen/aufloesen."
                % (len(interrupted),
                   [(i.db_kind, i.uid, i.to_version) for i in interrupted])))

        if require_backup_dir and not self._backup_dir:
            blockers.append(Blocker(
                "KEIN_BACKUP_DIR",
                "Kein Backup-Ziel gesetzt — Pflicht-Backup fuer Beweis-DBs "
                "(config paths.backup_dir oder --backup-dir)."))

        return PreflightResult(ok=not blockers, blockers=blockers, notes=notes)

    # ----------------------------------------------------------- Phase B: Plan
    def plan(self, targets: List[TargetDb]) -> List[ExecutionResult]:
        """Dry-Run-Plan je Instanz (fuehrt NICHTS aus)."""
        return self._executor.execute_fleet(targets, dry_run=True)

    # ------------------------------------------------------- Phase C: Ausfuehrung
    def execute(self, targets: List[TargetDb], *, confirm: bool = False,
                verifier: Optional[str] = None) -> CompanionResult:
        """
        Fuehrt aus — aber NUR, wenn (1) die Vorpruefung inkl. Backup-Ziel
        offen ist UND (2) der Mensch explizit bestaetigt hat (confirm=True).
        Sonst wird die Ausfuehrung verweigert und der Grund benannt.
        """
        pf = self.preflight(require_backup_dir=True)
        if not pf.ok:
            return CompanionResult(
                executed=False, preflight=pf, results=[],
                reason="Vorpruefung blockiert (%d Tor[e]) — Ausfuehrung "
                       "unterbleibt." % len(pf.blockers))
        if not confirm:
            return CompanionResult(
                executed=False, preflight=pf, results=[],
                reason="Keine ausdrueckliche Bestaetigung (confirm=False) — "
                       "Ausfuehrung unterbleibt.")

        results = self._executor.execute_fleet(
            targets, dry_run=False, verifier=verifier)
        # BUILD 723 (Vorgang 69ede1c7): Es gibt ZWEI Fehlerstatus. Bis
        # Build 720 stand hier 'r.status == "failed_restored"'. Der Rueckweg
        # konnte damals nicht Nein sagen, also gab es auch nur einen Fall.
        # Jetzt kann er es — und wer weiter nur gegen den EINEN Wert prueft,
        # zaehlt ausgerechnet den SCHWEREREN Fall als Erfolg. Deshalb steht
        # die Liste jetzt in executor.FEHLERSTATUS und nicht hier.
        failed = [r for r in results if r.status in FEHLERSTATUS]
        nicht_zurueck = [r for r in results
                         if r.status == "failed_not_restored"]
        if not failed:
            reason = "Alle Instanzen erfolgreich."
        elif not nicht_zurueck:
            reason = ("%d Instanz(en) fehlgeschlagen und wiederhergestellt — "
                      "menschliche Pruefung noetig." % len(failed))
        else:
            # Der schwerere Fall wird ZUERST genannt und beim Namen. Eine
            # Zusammenfassung, die "wiederhergestellt" sagt, wo nichts
            # wiederhergestellt wurde, waere schlimmer als gar keine.
            reason = ("%d Instanz(en) fehlgeschlagen, davon %d OHNE "
                      "ausgefuehrten Rueckweg — diese Instanz(en) sind VON "
                      "HAND zu klaeren; die Sicherungen liegen unveraendert."
                      % (len(failed), len(nicht_zurueck)))
        return CompanionResult(executed=True, preflight=pf, results=results,
                               reason=reason)

    # ---------------------------------------------------- Phase D: Zusammenfassung
    def summary(self) -> SummaryReport:
        """Statusbild + Gegenzeichnungs-Erinnerung (Vieraugen, Leitfaden §3 Phase 3)."""
        reminders = [
            "Vieraugen: Migrations-Definition und migration_runs-Ledger per "
            "GPG gegenzeichnen (Leitfaden §3 Phase 3).",
            "Backups signieren/WORM-archivieren (Zeremonie).",
        ]
        return SummaryReport(
            chain_ok=self._ledger.verify_chain().ok,
            registry=self._mdb.list_registry(),
            recent_runs=self._ledger.list_runs(),
            interrupted=self._ledger.interrupted_runs(),
            reminders=reminders)
