# =============================================================================
# management/migrations/coordinator/m001_audit_log.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M001 — coordinator.db
#   Legt das hash-verkettete Audit-Log an und schreibt die Genesis-Zeile als
#   Kettenanker. Rein additiv und datenneutral (keine bestehenden Daten betroffen).
#
#   Reihenfolge der Kette nach M001:
#     seq=1  genesis            (von up() geschrieben)
#     seq=2  migration_applied  (vom MigrationRunner nach up() geschrieben)
#
# KIND='additive' -> kein precount/postcount/verify nötig.
#
# Beleg: Bauplan B7 v0.2 §2.2/§2.4, mc 2026-07-01.
# Version: v0.7.306 · Build: 306 · 2026-07-01
# =============================================================================

import sqlite3
import time

from management.audit.audit_log import AuditLog

VERSION = 1
NAME = "audit_log + Genesis"
KIND = "additive"


def up(con: sqlite3.Connection) -> None:
    # 1) Schema (Tabelle + Append-only-Trigger).
    AuditLog.create_schema(con)
    # 2) Genesis-Zeile als Kettenanker.
    audit = AuditLog(con)
    audit.write_genesis(
        {
            "db": "coordinator",
            "schema": "M001",
            "created_at": int(time.time()),
        }
    )
