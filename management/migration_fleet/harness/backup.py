# =============================================================================
# management/migration_fleet/harness/backup.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# BackupTool — Phase 1 des Leitfadens: konsistentes Backup + SHA512.
#
#   create_backup() nutzt 'VACUUM INTO', das eine SAUBERE, WAL-unabhaengige
#   Kopie erzeugt (Beleg: Leitfaden v0.2 §4 "VACUUM INTO"). VACUUM INTO liest
#   die Quelle und schreibt eine NEUE Datei — die Quelle wird NICHT veraendert.
#
#   Namenskonvention aus Leitfaden Phase 1 (mc 2026-07-03 bestaetigt):
#       <db_label>_v<version>_<timestamp>_<host>.backup.db
#   wobei <db_label> die konkrete DB benennt (z. B. 'evidence_18'), sodass
#   Backups ueber die Flotte hinweg eindeutig zuordenbar sind.
#
#   GPG-Signatur ist in Build 317 BEWUSST nicht enthalten (reine Primitive);
#   sie tritt mit Executor/Zeremonie (Build 319) hinzu (mc 2026-07-03).
#
# Beleg: Datenmigrationsleitfaden_AIW.md v0.2 §3 Phase 1/§4, mc 2026-07-03.
# Version: v0.7.317 · Build: 317 · 2026-07-03
# =============================================================================

import os
import socket
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from management.migration_fleet.harness.hashing import sha512_file


@dataclass(frozen=True)
class BackupResult:
    path: str
    sha512: str
    size: int


class BackupTool:
    """Erstellt und verifiziert konsistente DB-Backups (read-only auf Quelle)."""

    @staticmethod
    def backup_filename(db_label: str, version: int,
                        host: Optional[str] = None,
                        ts: Optional[str] = None) -> str:
        """Baut den Backup-Dateinamen nach Leitfaden-Konvention."""
        host = host or socket.gethostname()
        ts = ts or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        return "%s_v%s_%s_%s.backup.db" % (db_label, version, ts, host)

    @staticmethod
    def create_backup(src_path: str, dest_dir: str, *,
                      db_label: Optional[str] = None, version: int = 0,
                      host: Optional[str] = None,
                      ts: Optional[str] = None) -> BackupResult:
        """
        Erzeugt via 'VACUUM INTO' eine konsistente Kopie von src_path im
        dest_dir und liefert Pfad + SHA512 + Groesse. Mutiert die Quelle nicht.
        """
        src = Path(src_path)
        if db_label is None:
            db_label = src.stem  # z. B. 'evidence_18'
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        dest = str(Path(dest_dir) / BackupTool.backup_filename(
            db_label, version, host, ts))

        con = sqlite3.connect(str(src))
        try:
            # VACUUM darf nicht in einer offenen Transaktion laufen -> Autocommit.
            con.isolation_level = None
            con.execute("VACUUM INTO ?", (dest,))
        finally:
            con.close()

        return BackupResult(path=dest, sha512=sha512_file(dest),
                            size=os.path.getsize(dest))

    @staticmethod
    def verify_backup(backup_path: str, expected_sha512: str) -> bool:
        """True, wenn die Backup-Datei den erwarteten SHA512 traegt."""
        return sha512_file(backup_path) == expected_sha512
