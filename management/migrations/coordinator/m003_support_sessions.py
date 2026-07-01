# =============================================================================
# management/migrations/coordinator/m003_support_sessions.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M003 — coordinator.db
#   Legt die Präsenz-Tabelle 'support_sessions' an. Sie erfasst LIVE-Support-
#   Sitzungen: Solange die Instanz eines Supporters (Modus 'support') einen Fall
#   betrachtet, hält sie hier einen Heartbeat. Der zugewiesene Ermittler liest
#   daraus, ob gerade jemand mit in seinen Fall schaut.
#
#   Wichtig zur Abgrenzung:
#     - support_sessions ist FLÜCHTIGER Präsenzzustand (prunebar), KEIN Beweis.
#     - Der permanente Zugriffsbeleg (wer sah wann welchen Fall) lebt im
#       audit_log (SUPPORT_SESSION_STARTED / _ENDED). Heartbeats werden NICHT
#       auditiert (sonst flutet die Kette).
#
# KIND='additive' -> rein additiv, datenneutral, kein precount/postcount/verify.
# coordinator.db unterliegt keinem Migrations-Lock (kein Beweismittel).
#
# Beleg: Bauplan B7 v0.5 §6, Projektgespräch 2026-07-01, mc 2026-07-01.
# Version: v0.7.311 · Build: 311 · 2026-07-01
# =============================================================================

import sqlite3

VERSION = 3
NAME = "support_sessions (Live-Support-Präsenz)"
KIND = "additive"

_DDL_TABLE = """
CREATE TABLE IF NOT EXISTS support_sessions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,          -- betrachteter Fall (Beschuldigten-user_id)
    supporter_id   INTEGER,                   -- investigators.id des Supporters
    started_at     INTEGER NOT NULL,          -- Unix-Sekunden
    last_heartbeat INTEGER NOT NULL,          -- Unix-Sekunden, periodisch aktualisiert
    ended_at       INTEGER,                   -- NULL = laufend; gesetzt bei sauberem Ende
    FOREIGN KEY(supporter_id) REFERENCES investigators(id)
)
"""

# Index für den Aktiv-Read (Filter user_id + ended_at IS NULL + last_heartbeat).
_DDL_INDEX = """
CREATE INDEX IF NOT EXISTS support_sessions_active_idx
    ON support_sessions(user_id, ended_at, last_heartbeat)
"""


def up(con: sqlite3.Connection) -> None:
    con.execute(_DDL_TABLE)
    con.execute(_DDL_INDEX)
