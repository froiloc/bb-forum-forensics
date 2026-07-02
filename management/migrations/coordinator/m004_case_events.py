# =============================================================================
# management/migrations/coordinator/m004_case_events.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M004 — coordinator.db
#   Legt den Ereigniszeitstrahl 'case_events' an (Idee 11). Er ist das
#   LESE-MODELL für das Ampel-Dashboard (Tag 3) und den Nutzerinfo-Tab:
#   pro Fall (user_id) eine chronologische Folge fachlicher Ereignisse
#   (Fall angelegt, zugewiesen, Statuswechsel, Freigabe, manuelle Einträge).
#
#   Wichtig zur Abgrenzung (analog support_sessions, M003):
#     - case_events ist ein KOMFORT-Lesemodell für die Anzeige. Der
#       forensische BEWEIS jedes Ereignisses lebt unverändert im hash-
#       verketteten audit_log. Jede case_events-Zeile trägt deshalb in
#       'audit_seq' die seq ihres audit_log-Belegs — die Kopplung entsteht
#       IN DERSELBEN Transaktion (CoordinatorWriter.audited_write mit
#       after_audit-Hook), sodass Zeitstrahl-Zeile und Beleg nie
#       auseinanderlaufen können (Grundregel 1: keine stille Auslassung).
#     - Manuelle Eintragstexte liegen NUR hier (payload), nicht im
#       audit_log-Payload (dort nur Faktum + Textlänge) — gleiche
#       Sensibilitätsregel wie bei cases.note (CasesRepo.set_note).
#
#   event_kind wird — wie audit_log.event_type — im CODE validiert
#   (case_events_repo.EVENT_KINDS), bewusst OHNE CHECK-Constraint: ein
#   späterer neuer kind-Wert bleibt damit additiv (kein Tabellen-Rebuild).
#
# KIND='additive' -> rein additiv, datenneutral, kein precount/postcount/verify.
# coordinator.db unterliegt keinem Migrations-Lock (kein Beweismittel);
# migrate.py-Lauf beim Deploy ist dennoch ZWINGEND (neue Tabelle).
#
# Beleg: Bauplan B7 v0.8 §8, Roadmap "Tag 2+" (v0.1), mc 2026-07-02
#        (Design-Entscheidung: Zuweisungen/Statuswechsel/Freigaben werden
#        automatisch gespiegelt).
# Version: v0.7.313 · Build: 313 · 2026-07-02
# =============================================================================

import sqlite3

VERSION = 4
NAME = "case_events (Ereigniszeitstrahl je Fall)"
KIND = "additive"

_DDL_TABLE = """
CREATE TABLE IF NOT EXISTS case_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,           -- Fall (cases.user_id, Beschuldigten-ID)
    event_kind TEXT    NOT NULL,           -- Vokabular: case_events_repo.EVENT_KINDS
    payload    TEXT    NOT NULL DEFAULT '',-- kanonisches JSON (Anzeige-Daten)
    created_by INTEGER,                    -- investigators.id; NULL = System
    created_at INTEGER NOT NULL,           -- Unix-Sekunden
    audit_seq  INTEGER NOT NULL,           -- audit_log.seq des zugehörigen Belegs
    FOREIGN KEY(user_id)    REFERENCES cases(user_id),
    FOREIGN KEY(created_by) REFERENCES investigators(id)
)
"""

# Index für den Zeitstrahl-Read des Dashboards (Filter user_id, Sortierung Zeit).
_DDL_INDEX = """
CREATE INDEX IF NOT EXISTS case_events_user_time_idx
    ON case_events(user_id, created_at)
"""


def up(con: sqlite3.Connection) -> None:
    con.execute(_DDL_TABLE)
    con.execute(_DDL_INDEX)
