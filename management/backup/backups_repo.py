# =============================================================================
# management/backup/backups_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Backup/PITR (Welle 0)
# =============================================================================
# BackupsRepo — Schreibpfad der 'backups'-Registry (Build 354). Registriert
# einen ausgefuehrten Backup-Lauf auditiert in coordinator.db:
#
#   EIN Beleg pro Lauf: append(BACKUP_CREATED) liefert die seq; danach traegt
#   JEDE 'backups'-Zeile des Laufs audit_seq == diese seq (mc 2026-07-10,
#   Frage 2 — der Lauf ist ein gemeinsamer Prozess fuer alle DBs). Write +
#   Audit + Registry-Zeilen committen atomar oder gar nicht (audited_write /
#   after_audit-Hook; Grundregel 1 — keine stille Teil-Persistenz).
#
#   Feingranular: eine Zeile PRO Datenbank (mc Frage 1) — auch fuer
#   fehlgeschlagene DBs (integrity_ok=0, error=<grund>), damit der Fehlversuch
#   forensisch belegt bleibt und nicht still verschwindet.
#
# Beleg: Bauplan B7 v1.1 §11; Muster rbac_repo/case_events (audit_seq-Kopplung).
# Version: v0.7.354 · Build: 354 · 2026-07-10
# =============================================================================

import sqlite3
import time
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.backup.backup_executor import BackupRun


class BackupsRepo:
    """Registriert Backup-Laeufe (Schreibpfad) und liest die Registry."""

    def __init__(self, con: sqlite3.Connection, writer) -> None:
        self._con = con
        self._writer = writer  # CoordinatorWriter

    # ------------------------------------------------------------- record
    def record_run(self, run: BackupRun, actor_id: Optional[int]) -> int:
        """
        Registriert einen (bereits ausgefuehrten) BackupRun. Schreibt EINEN
        BACKUP_CREATED-Beleg und je Ergebnis eine 'backups'-Zeile mit dessen
        audit_seq. Gibt die audit_log-seq zurueck.

        Auch ein Lauf, der die Vorabpruefung verweigert hat (keine results),
        laesst sich registrieren — dann entsteht nur der Beleg (Nachvollzieh-
        barkeit des Versuchs), aber keine Registry-Zeile.
        """
        now = int(time.time())
        results = run.results

        def _do_write(_con: sqlite3.Connection) -> Dict[str, Any]:
            # Audit-Payload = Lauf-Zusammenfassung (der Beleg-Inhalt).
            failed = [r.label for r in results if r.error is not None
                      or not r.integrity_ok]
            return {
                "run_ts": run.run_ts,
                "host": run.host,
                "ok": run.ok,
                "db_count": len(results),
                "failed": failed,
                "pruned_count": len(run.pruned),
                "manifest_path": run.manifest_path,
                "reason": run.reason,
            }

        def _after(_con: sqlite3.Connection, seq: int) -> None:
            # Je Datenbank eine Zeile, gekoppelt an denselben Beleg.
            _con.executemany(
                "INSERT INTO backups "
                "(run_ts, host, db_label, src_path, backup_path, sha512, "
                " size, user_version, integrity_ok, error, manifest_path, "
                " audit_seq, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(run.run_ts, run.host, r.label, r.src, r.backup_path,
                  r.sha512, r.size, r.user_version,
                  1 if r.integrity_ok else 0, r.error, run.manifest_path,
                  seq, now) for r in results],
            )

        return self._writer.audited_write(
            do_write=_do_write,
            event_type=EventType.BACKUP_CREATED,
            actor_id=actor_id,
            target_type="backup_run",
            target_id=run.run_ts or None,
            after_audit=_after,
        )

    # --------------------------------------------------------------- list
    def list_backups(self, *, db_label: Optional[str] = None,
                     limit: int = 100) -> List[Dict[str, Any]]:
        """
        Registrierte Backups lesen (neueste zuerst). Optional nach db_label
        gefiltert. Reines Lesemodell (dict je Zeile).
        """
        sql = ("SELECT id, run_ts, host, db_label, src_path, backup_path, "
               "sha512, size, user_version, integrity_ok, error, "
               "manifest_path, audit_seq, created_at FROM backups")
        params: list = []
        if db_label:
            sql += " WHERE db_label = ?"
            params.append(db_label)
        sql += " ORDER BY run_ts DESC, db_label ASC LIMIT ?"
        params.append(int(limit))

        cur = self._con.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
