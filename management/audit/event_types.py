# =============================================================================
# management/audit/event_types.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Kontrolliertes, eingefrorenes Vokabular der Audit-Ereignistypen. Die Werte
#   sind Versionsbestandteil: Ein Wert im Log entspricht jahrelang eindeutig
#   einer Bedeutung — auch nach Code-Änderungen. Daher Konstanten im Code, NICHT
#   in der Datenbank (Beleg: Bauplan B7 v0.2 §2.5, Bewertung Idee 9/13).
#
#   Tag-1-Umfang: GENESIS, MIGRATION_APPLIED, CHAIN_VERIFIED.
#   Weitere Werte werden mit ihren jeweiligen Modulen (cases, case_events,
#   notifications, backups) ergänzt — niemals umbenannt, niemals wiederverwendet.
#
# Version: v0.7.306 · Build: 306 · 2026-07-01
# =============================================================================

from typing import FrozenSet


class EventType:
    """Eingefrorene Ereignistyp-Konstanten für audit_log.event_type."""

    # --- Tag 1 (Build 306) ---
    GENESIS: str = "genesis"
    MIGRATION_APPLIED: str = "migration_applied"
    CHAIN_VERIFIED: str = "chain_verified"

    # --- reserviert für spätere Builds (hier dokumentiert, noch nicht aktiv) ---
    # CASE_CREATED, CASE_ASSIGNED, CASE_STATUS_CHANGED, CASE_APPROVED,
    # CASE_EVENT_ADDED, NOTIFICATION_SENT, BACKUP_CREATED, RESTORE_PERFORMED

    #: Alle aktuell gültigen Werte. Erweitern, nie entfernen/umbenennen.
    ALL: FrozenSet[str] = frozenset(
        {
            GENESIS,
            MIGRATION_APPLIED,
            CHAIN_VERIFIED,
        }
    )

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """True, wenn value ein bekannter, aktiver Ereignistyp ist."""
        return value in cls.ALL
