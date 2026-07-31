# =============================================================================
# management/backup/backup_executor.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# BackupExecutor — Phase des SCHREIBENS (Build 353). Fuehrt fuer jeden Eintrag
# eines geprueften BackupPlan die eigentliche Sicherung durch:
#
#   1) optional 'wal_checkpoint(PASSIVE)' auf der Quelle (nicht blockierend;
#      nie TRUNCATE) — je config.backup.checkpoint,
#   2) transaktionaler Snapshot per 'VACUUM INTO' (via BackupTool, Build 317;
#      Quelle wird NICHT veraendert),
#   3) 'PRAGMA integrity_check' auf der KOPIE (zertifiziert das Backup, stoert
#      keinen Livezugriff; Beleg: Bauplan B7 v1.1 §11 Punkt 7),
#   4) SHA512 (aus BackupTool) als Integritaets-/Provenienzsiegel.
#
# Robustheit (Grundregel 1 — kein stiller Fehlpfad): ein Fehler bei EINER DB
# bricht den Gesamtlauf NICHT ab. Jede DB wird einzeln bilanziert; der Lauf ist
# nur dann ok, wenn ALLE Sicherungen erfolgreich UND integer sind. Alle
# Ergebnisse landen in einem JSON-Manifest je Lauf.
#
# Der Executor VERWEIGERT den Lauf, wenn die Speicherplatz-Vorabpruefung
# (BackupPlan.ok) fehlgeschlagen ist — halbe/unbrauchbare Kopien bei voller
# Platte werden so verhindert (vorfall-getrieben, 2026-07-01).
#
# Registrierung in der 'backups'-Registry + 'BACKUP_CREATED'-Audit folgt in
# Build 354 (bewusst getrennt).
#
# Beleg: Bauplan B7 v1.1 §11; Datenmigrationsleitfaden v0.2 §4; mc 2026-07-10.
# Build 354: BackupRun um run_ts/host erweitert (fuer die backups-Registrierung).
# Version: v0.7.354 · Build: 354 · 2026-07-10
# =============================================================================

import json
import os
import re
import socket
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple

from management.backup.backup_config import BackupConfig
from management.backup.backup_planner import BackupPlan
from management.migration_fleet.harness.backup import BackupTool

#: DER VERMERK ZUR PUNKTGLEICHHEIT (Build 617, Entscheidung mc 2026-07-31).
#:
#: Er steht an EINER Stelle, damit Manifest und Konsole nicht auseinander-
#: laufen. Anlass ist die Nachpruefung aus Build 616: Die Datenbanken werden
#: NACHEINANDER gesichert, jede fuer sich transaktional stimmig - der SATZ
#: als Ganzes ist es nicht. Zwischen zwei Kopien kann der Betrieb einen Fall
#: anlegen oder eine Zuweisung aendern; aus einem solchen Satz
#: wiederhergestellt entstuende ein Zustand, den es nie gegeben hat.
#:
#: mc hat sich am 2026-07-31 fuer die KENNZEICHNUNG entschieden und gegen ein
#: Wartungsfenster: eine taegliche Sicherung soll nebenher laufen koennen.
#: Der Preis ist, dass jeder, der den Satz benutzt, von der Einschraenkung
#: WISSEN muss - und dafuer genuegt es nicht, sie im Vermerk abzulegen. Sie
#: steht deshalb im Manifest UND auf der Konsole, bei jedem Lauf.
PUNKTGLEICH_VERMERK = (
    "NICHT PUNKTGLEICH: Die Datenbanken wurden nacheinander gesichert. Jede "
    "Kopie ist fuer sich transaktional stimmig; der Satz als Ganzes bildet "
    "KEINEN gemeinsamen Zeitpunkt ab. Zwischen zwei Kopien kann der Betrieb "
    "geschrieben haben. Fuer eine Wiederherstellung des GESAMTEN Bestandes "
    "ist ein ruhiger Zustand noetig (keine offenen Schreiber) - sonst kann "
    "ein Zustand entstehen, den es nie gegeben hat. Die Felder "
    "'begonnen_ts' und 'beendet_ts' je Datenbank machen den Versatz "
    "ablesbar."
)

#: Erkennt Backup-Dateinamen der Leitfaden-Konvention
#: '<label>_v<version>_<ts>_<host>.backup.db' fuer die Retention-Gruppierung.
_BACKUP_NAME_RE = re.compile(
    r"^(?P<label>.+)_v\d+_(?P<ts>\d{8}T\d{6}Z)_.+\.backup\.db$")


@dataclass(frozen=True)
class BackupItemResult:
    """Ergebnis der Sicherung EINER Datenbank."""
    label: str
    src: str
    backup_path: Optional[str]
    sha512: Optional[str]
    size: int
    user_version: int
    integrity_ok: bool
    error: Optional[str]   # None wenn erfolgreich, sonst Klartext-Grund
    # BUILD 617 — DER ZEITPUNKT JE DATENBANK.
    # Bis Build 616 trug das Manifest nur EINEN Zeitstempel fuer den ganzen
    # Lauf. Damit sah der Sicherungssatz punktgleich aus, ohne es zu sein:
    # die Datenbanken werden nacheinander gesichert, und dazwischen arbeitet
    # der Betrieb weiter. Diese beiden Felder machen den Versatz ABLESBAR.
    # Sie stehen im Manifest, NICHT in der Registry - eine Schemaaenderung an
    # der coordinator.db fiele unter den Migrationsvorbehalt und waere fuer
    # eine Angabe, die ins Manifest gehoert, der falsche Preis.
    begonnen_ts: str = ""
    beendet_ts: str = ""


@dataclass(frozen=True)
class BackupRun:
    """Gesamtergebnis eines Backup-Laufs."""
    ok: bool
    run_ts: str
    host: str
    results: List[BackupItemResult]
    pruned: List[str]
    manifest_path: Optional[str]
    reason: str
    #: Fall-Datenbanken, die WAEHREND des Laufs entstanden sind und deshalb
    #: NICHT gesichert wurden (Build 617). Leer ist der Regelfall.
    nachzuegler: List[str] = field(default_factory=list)


class BackupExecutor:
    """Fuehrt einen geprueften BackupPlan aus (schreibend, Quelle read-only)."""

    def __init__(self, backup_cfg: BackupConfig) -> None:
        self._cfg = backup_cfg

    # ------------------------------------------------------------------- run
    def run(self, plan: BackupPlan) -> BackupRun:
        """
        Sichert alle Quellen des Plans. Verweigert, wenn plan.ok False ist
        (Vorabpruefung fehlgeschlagen).
        """
        if not plan.ok:
            return BackupRun(
                ok=False, run_ts="", host=socket.gethostname(),
                results=[], pruned=[], manifest_path=None,
                reason="Vorabpruefung fehlgeschlagen: " + plan.reason)

        run_ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        host = socket.gethostname()

        results = [self._backup_one(src, plan.dest_dir, run_ts, host)
                   for src in plan.sources]

        # --- NACHSCHAU: WAS IST WAEHREND DES LAUFS DAZUGEKOMMEN? (B617) ---
        # Der Planer liest die Fallverzeichnisse EINMAL VOR dem Lauf. Eine
        # Fall-Datenbank, die waehrend des Laufs entsteht, wurde bis Build 616
        # weder gesichert NOCH genannt - sie verschwand still (Grundregel 1).
        # Gesichert wird sie auch jetzt nicht: sie nachtraeglich mitzunehmen
        # machte den Satz noch ungleichzeitiger, und der Lauf haette kein
        # definiertes Ende. Aber sie wird BENANNT, und damit weiss der
        # naechste Lauf bzw. die auswertende Person davon.
        nachzuegler = self._nachzuegler(plan)

        pruned = self._prune(plan.dest_dir)
        overall_ok = all(r.error is None and r.integrity_ok for r in results)
        manifest_path = self._write_manifest(
            plan.dest_dir, run_ts, host, results, pruned, overall_ok,
            nachzuegler)

        reason = "" if overall_ok else (
            "Mindestens eine DB-Sicherung schlug fehl oder ist nicht integer "
            "(siehe Manifest).")
        return BackupRun(ok=overall_ok, run_ts=run_ts, host=host,
                         results=results, pruned=pruned,
                         manifest_path=manifest_path, reason=reason,
                         nachzuegler=nachzuegler)

    # ----------------------------------------------------------- backup_one
    def _backup_one(self, src, dest_dir: str, run_ts: str,
                    host: str) -> BackupItemResult:
        """Eine DB sichern; jeder Fehler wird gefangen und bilanziert."""
        begonnen = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        try:
            if self._cfg.checkpoint == "passive":
                # Nicht-blockierender WAL-Trim; Fehlschlag ist unkritisch, weil
                # VACUUM INTO ohnehin konsistent liest -> nur protokollieren.
                self._checkpoint_passive(src.path)

            uv = self._user_version(src.path)
            res = BackupTool.create_backup(
                src.path, dest_dir, db_label=src.label, version=uv,
                host=host, ts=run_ts)

            integ_ok, detail = self._integrity_check(res.path)
            return BackupItemResult(
                label=src.label, src=src.path, backup_path=res.path,
                sha512=res.sha512, size=res.size, user_version=uv,
                integrity_ok=integ_ok,
                error=None if integ_ok else ("integrity_check: " + detail),
                begonnen_ts=begonnen,
                beendet_ts=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
        except Exception as exc:  # bewusst breit: kein DB darf den Lauf killen
            return BackupItemResult(
                label=src.label, src=src.path, backup_path=None, sha512=None,
                size=0, user_version=0, integrity_ok=False, error=str(exc),
                begonnen_ts=begonnen,
                beendet_ts=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))

    # ------------------------------------------------------------- helpers
    def _checkpoint_passive(self, src_path: str) -> None:
        con = sqlite3.connect(src_path)
        try:
            con.isolation_level = None
            con.execute("PRAGMA wal_checkpoint(PASSIVE)")
        finally:
            con.close()

    def _user_version(self, src_path: str) -> int:
        con = sqlite3.connect(src_path)
        try:
            row = con.execute("PRAGMA user_version").fetchone()
            return int(row[0]) if row else 0
        finally:
            con.close()

    def _integrity_check(self, backup_path: str) -> Tuple[bool, str]:
        """'PRAGMA integrity_check' auf der Backup-Kopie (read-only)."""
        con = sqlite3.connect(backup_path)
        try:
            rows = con.execute("PRAGMA integrity_check").fetchall()
        finally:
            con.close()
        ok = (len(rows) == 1 and rows[0][0] == "ok")
        detail = "ok" if ok else "; ".join(str(r[0]) for r in rows[:5])
        return ok, detail

    # -------------------------------------------------------------- prune
    def _prune(self, dest_dir: str) -> List[str]:
        """
        Behaelt je DB-Label die retention_count neuesten Generationen (nach dem
        eingebetteten Zeitstempel, lexikografisch sortierbar) und loescht
        aeltere Backup-Dateien. Nur Dateien der Namenskonvention werden
        beruecksichtigt; alles andere bleibt unangetastet.
        """
        try:
            names = os.listdir(dest_dir)
        except OSError:
            return []

        groups = {}
        for name in names:
            m = _BACKUP_NAME_RE.match(name)
            if not m:
                continue
            groups.setdefault(m.group("label"), []).append(
                (m.group("ts"), name))

        pruned: List[str] = []
        for _label, items in groups.items():
            items.sort(reverse=True)  # neueste zuerst
            for _ts, name in items[self._cfg.retention_count:]:
                p = os.path.join(dest_dir, name)
                try:
                    os.remove(p)
                    pruned.append(p)
                except OSError:
                    pass  # bleibt bestehen; nicht fatal
        return pruned

    # ----------------------------------------------------------- manifest
    def _nachzuegler(self, plan: BackupPlan) -> List[str]:
        """
        Fall-Datenbanken, die es beim Planen noch nicht gab.

        Verglichen wird gegen die Quellenliste des Plans; gesucht wird nur in
        den Verzeichnissen, aus denen der Plan seine fallbezogenen Quellen
        gezogen hat. Ein Fehler bei der Nachschau darf den Lauf nicht
        umwerfen - die Sicherungen sind zu diesem Zeitpunkt bereits
        geschrieben.
        """
        bekannt = {os.path.abspath(s.path) for s in plan.sources}
        verzeichnisse = {os.path.dirname(os.path.abspath(s.path))
                         for s in plan.sources}
        neu: List[str] = []
        for d in sorted(verzeichnisse):
            try:
                namen = sorted(os.listdir(d))
            except OSError:
                continue
            for name in namen:
                if not name.endswith(".db"):
                    continue
                voll = os.path.abspath(os.path.join(d, name))
                if voll not in bekannt and os.path.isfile(voll):
                    neu.append(voll)
        return neu

    def _write_manifest(self, dest_dir: str, run_ts: str, host: str,
                        results: List[BackupItemResult], pruned: List[str],
                        overall_ok: bool,
                        nachzuegler: Optional[List[str]] = None
                        ) -> Optional[str]:
        """Schreibt ein JSON-Manifest des Laufs (ASCII-only)."""
        # DIE SPANNE DES SATZES: vom Beginn der ersten bis zum Ende der
        # letzten Kopie. Wer den Satz spaeter beurteilt, sieht damit auf einen
        # Blick, ueber welchen Zeitraum er sich erstreckt.
        stempel = [r.begonnen_ts for r in results if r.begonnen_ts]
        stempel += [r.beendet_ts for r in results if r.beendet_ts]
        manifest = {
            "run_ts": run_ts,
            "host": host,
            "ok": overall_ok,
            "punktgleich": False,
            "punktgleich_hinweis": PUNKTGLEICH_VERMERK,
            "satz_von": min(stempel) if stempel else run_ts,
            "satz_bis": max(stempel) if stempel else run_ts,
            "config": {
                "dest_dir": self._cfg.dest_dir,
                "retention_count": self._cfg.retention_count,
                "min_free_factor": self._cfg.min_free_factor,
                "checkpoint": self._cfg.checkpoint,
                "include_shared_dbs": self._cfg.include_shared_dbs,
            },
            "results": [asdict(r) for r in results],
            "pruned": pruned,
            # Waehrend des Laufs entstanden und deshalb NICHT gesichert.
            # Leer ist der Regelfall; steht hier etwas, fehlt es im Satz.
            "nicht_gesichert_weil_neu": list(nachzuegler or []),
        }
        path = os.path.join(
            dest_dir, "manifest_%s_%s.json" % (run_ts, host))
        try:
            with open(path, "w", encoding="ascii") as fh:
                json.dump(manifest, fh, ensure_ascii=True, indent=2)
            return path
        except OSError:
            return None
