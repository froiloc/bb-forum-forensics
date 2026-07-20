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
#   Weitere Werte werden mit ihren jeweiligen Modulen (cases, investigators,
#   case_events, notifications, backups) ergänzt — niemals umbenannt, niemals
#   wiederverwendet.
#
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

from typing import FrozenSet


class EventType:
    """Eingefrorene Ereignistyp-Konstanten für audit_log.event_type."""

    # --- Tag 1 (Build 306) ---
    GENESIS: str = "genesis"
    MIGRATION_APPLIED: str = "migration_applied"
    CHAIN_VERIFIED: str = "chain_verified"

    # --- Tag 2 (Build 307): Fallakte cases ---
    CASE_CREATED: str = "case_created"
    CASE_ASSIGNED: str = "case_assigned"
    CASE_STATUS_CHANGED: str = "case_status_changed"
    CASE_APPROVED: str = "case_approved"
    CASE_PRIORITY_SET: str = "case_priority_set"
    CASE_NOTE_SET: str = "case_note_set"

    # --- Build 377: Berichts-Versiegelung (approved_reports.db) ---
    REPORT_APPROVED: str = "report_approved"
    REPORT_SEAL_VERIFIED: str = "report_seal_verified"
    #: Build 380 — Rueckgabe zur Nachbesserung (submitted -> draft) durch
    #: Lektor/Chef-Ermittlerin. Der Autor kann sich NICHT selbst zurueckholen.
    REPORT_RETURNED: str = "report_returned"

    # --- Build 310: Ermittler-Verwaltung (investigators) ---
    INVESTIGATOR_CREATED: str = "investigator_created"
    INVESTIGATOR_UPDATED: str = "investigator_updated"

    # --- Build 311: Live-Support-Sitzung (support_sessions) ---
    #   Nur Start/Ende als Zugriffsbeleg; Heartbeats werden NICHT auditiert.
    SUPPORT_SESSION_STARTED: str = "support_session_started"
    SUPPORT_SESSION_ENDED: str = "support_session_ended"

    # --- Build 313: Ereigniszeitstrahl (case_events) ---
    #   Beleg für MANUELL hinzugefügte Zeitstrahl-Einträge. Die automatisch
    #   gespiegelten Einträge (Anlage/Zuweisung/Status/Freigabe) brauchen
    #   KEINEN eigenen Typ — ihr Beleg ist der ohnehin geschriebene
    #   CASE_*-Eintrag, auf den die Zeitstrahl-Zeile per audit_seq zeigt.
    CASE_EVENT_ADDED: str = "case_event_added"

    # --- Build 344: RBAC-Schreibpfad (rbac_grant / person_role) ---
    #   Vergabe/Ruecknahme von Faehigkeits-Grants und Rollenzuweisungen. Jeder
    #   Schreibvorgang koppelt die Zeile per audit_seq an genau diesen Beleg
    #   (append-only Soft-Revoke; kein DELETE). Beleg: Bauplan B7 v1.1
    #   §11.1/§11.3/§11.7, RBAC Schnitt (b); mc 2026-07-10.
    RBAC_GRANTED: str = "rbac_granted"
    RBAC_REVOKED: str = "rbac_revoked"
    ROLE_ASSIGNED: str = "role_assigned"
    ROLE_REVOKED: str = "role_revoked"

    # --- Build 354: Datensicherung (backups) ---
    #   Ein Beleg PRO BACKUP-LAUF (nicht pro DB): der Lauf ist EIN angestossener
    #   Prozess fuer alle Datenbanken gemeinsam. Jede 'backups'-Zeile des Laufs
    #   koppelt per audit_seq an genau diesen Beleg. Beleg: Bauplan B7 v1.1 §11;
    #   mc 2026-07-10.
    BACKUP_CREATED: str = "backup_created"

    # --- Build 355: Kapazitaet (Welle 0, §11.4) ---
    #   Auditierte Schreibpfade fuer die Kapazitaets-Datenbasis. Soft-Delete
    #   erhaelt einen eigenen '_REMOVED'-Beleg (append-only; kein hartes DELETE).
    #   mc 2026-07-10.
    WORKTIME_SET: str = "worktime_set"
    HOLIDAY_ADDED: str = "holiday_added"
    HOLIDAY_REMOVED: str = "holiday_removed"
    AVAILABILITY_REASON_ADDED: str = "availability_reason_added"
    AVAILABILITY_SET: str = "availability_set"
    AVAILABILITY_REMOVED: str = "availability_removed"

    # --- Build 385: Wiedervorlage externer Vorgaenge (external_matters) ---
    #   Ein Beleg PRO ZUSTANDSAENDERUNG des Vorgangs. Das VERSCHIEBEN der
    #   Wiedervorlage bekommt einen EIGENEN Typ (_DEFERRED) und nicht etwa
    #   ein stilles UPDATE: das Verschieben IST der Vorgang, um den es hier
    #   geht — wer wie oft verschoben hat, muss im Bericht stehen koennen.
    #   Der Abschluss (_CLOSED) ist unwiderruflich (MatterStatus).
    #   Freitexte stehen NICHT im Payload, nur Fakten + Textlaengen
    #   (Sensibilitaetsregel wie bei cases.note). mc 2026-07-12.
    EXTERNAL_MATTER_CREATED: str = "external_matter_created"
    EXTERNAL_MATTER_DEFERRED: str = "external_matter_deferred"
    EXTERNAL_MATTER_ANSWERED: str = "external_matter_answered"
    EXTERNAL_MATTER_CLOSED: str = "external_matter_closed"

    # --- Build 387: Ermittlungsergebnis-Bewertung ---------------------------
    #   ASSESSMENT_RECORDED: eine Bewertung (append-only; jede Korrektur ist
    #   eine NEUE Zeile und damit ein NEUER Beleg — der Verlauf IST die
    #   Ermittlungsleistung). Freitext steht NICHT im Payload, nur Fakten,
    #   Zahlen und die Textlaenge.
    #
    #   CATALOG_*: der Bewertungs-KATALOG ist Daten, nicht Code (mc
    #   2026-07-12) — Skalen und Kriterien sollen sich mit der
    #   Ermittlungserfahrung weiterentwickeln koennen, OHNE Migration. Genau
    #   deshalb braucht jede Katalogaenderung einen eigenen Beleg: sie
    #   veraendert die BEDEUTUNG spaeterer Zahlen.
    #   CATALOG_DEPRECATED = ausser Dienst gestellt (nie geloescht — sonst
    #   zeigten bestehende Bewertungen ins Leere).
    ASSESSMENT_RECORDED: str = "assessment_recorded"
    CATALOG_SCALE_ADDED: str = "catalog_scale_added"
    CATALOG_ITEM_ADDED: str = "catalog_item_added"
    CATALOG_CRITERION_ADDED: str = "catalog_criterion_added"
    CATALOG_DEPRECATED: str = "catalog_deprecated"

    # --- Build 401: Betreuungs-Notizen ("Post-its") der Ermittler-Betreuung --
    #   Arbeitsnotizen der Leitung (KEINE Ermittlungsdaten). Jede Aenderung ist
    #   auditiert; das Umsortieren wird GEBUENDELT belegt (ein Ereignis pro
    #   Drop, Payload = neue Reihenfolge), nicht pro Maus-Bewegung.
    MENTORING_NOTE_CREATED: str = "mentoring_note_created"
    MENTORING_NOTE_UPDATED: str = "mentoring_note_updated"
    MENTORING_NOTE_ARCHIVED: str = "mentoring_note_archived"
    MENTORING_NOTE_RESTORED: str = "mentoring_note_restored"
    MENTORING_NOTE_REORDERED: str = "mentoring_note_reordered"

    # --- Build 411: Annotations-Support-View (SF-2, Vermaehlung B6xB7) --------
    #   REPORT_ANNOTATIONS_VIEWED: ein LESENDER Zugriff auf die dem Bericht
    #   zugrunde liegenden Annotationen (Belege) durch Lektorat/Chef-Freigabe.
    #   Chain-of-Custody: es wird belegt, DASS jemand die Belege gesichtet hat.
    #   Bewusst FLACH (mc 2026-07-14: "mehr Tiefe braucht es nicht") — das
    #   Payload traegt nur Fakten (subject_id, report_id, anchor_count, scope),
    #   KEINE Annotationsinhalte.
    REPORT_ANNOTATIONS_VIEWED: str = "report_annotations_viewed"

    # --- Build 412: Kommentar-Bruecke (SF-3, Vermaehlung B6xB7) ---------------
    #   Lektorat/Chef-Kommentare zum Berichtstext liegen in der Addendum-Datei
    #   der jeweiligen Person (evidence_<uid>_<pid>.db), NICHT in coordinator.db.
    #   Hier wird nur die PRUEFSPUR belegt (Fakten: wer/welcher Bericht/Block/
    #   comment_id), KEIN Kommentartext.
    REVIEW_COMMENT_ADDED: str = "review_comment_added"
    REVIEW_COMMENT_RESOLVED: str = "review_comment_resolved"

    # --- Build 460: Fremdforum-Promotion (forum_promotion, AP-2G) ------------
    #   EIN Beleg PRO ENTSCHEIDUNG ueber einen Fremdforum-Kandidaten (anlegen
    #   ODER weiterfuehren; die Zustandsmaschine ops/promotion_status.py
    #   erzwingt zulaessige Uebergaenge). Endzustaende ('uebernommen'/
    #   'fremdzustaendig') sind unwiderruflich. Freitexte (grund, herkunft)
    #   stehen NICHT im Payload, nur Fakten (subject_id, von->auf) + Textlaengen
    #   (Sensibilitaetsregel wie bei cases.note / external_matters). Ein Wechsel
    #   nach 'zurueckgestellt'/'fremdzustaendig' verlangt einen Grund. Kein
    #   case_events-Spiegel: ein 'neu'-Kandidat hat keine cases-Zeile. mc
    #   2026-07-20.
    PROMOTION_DECIDED: str = "promotion_decided"

    # --- Build 462: Externe Fallfreigabe (case_release, AP-2G) ----------------
    #   Je EIN Beleg fuer die Erteilung und den Widerruf einer externen Freigabe
    #   an einen NRW-Ermittler. Der Widerruf ist unwiderruflich (ReleaseStatus).
    #   Freitexte (Unbedenklichkeits-Grundlage, Widerrufsgrund) stehen NICHT im
    #   Payload, nur Fakten (subject_id, recipient_kennung, umfang, von->auf) +
    #   Textlaengen (Sensibilitaetsregel). Die Empfaenger-Kennung IST ein Fakt
    #   (wer externen Zugriff erhielt) und gehoert in den Beleg. mc 2026-07-20.
    CASE_RELEASE_GRANTED: str = "case_release_granted"
    CASE_RELEASE_REVOKED: str = "case_release_revoked"

    # --- Build 464: Onboarding/Offboarding-Checkliste (onboarding_item, AP-2G) -
    #   EIN Beleg PRO SCHRITT-AENDERUNG (erledigt/nicht_zutreffend/Reset auf
    #   offen). Freitext (Notiz) steht NICHT im Payload, nur Fakten (person_id,
    #   kind, step_code, status) + Textlaenge (Sensibilitaetsregel). mc 2026-07-20.
    ONBOARDING_STEP_SET: str = "onboarding_step_set"

    # --- Build 468: Katalog identifizierter Personen (identified_subject, AP-2A)
    #   EIN Beleg PRO ANLAGE/REVISION einer Konto->Person-Zuordnung. Der
    #   sensible Freitext (real_identity/basis/note) steht NICHT im Payload, nur
    #   FAKTEN (subject_id, confidence_code/ordinal, created) + Textlaengen
    #   (Sensibilitaetsregel). Ein Ereignistyp fuer Anlage und Revision; das
    #   Payload-Feld 'created' unterscheidet beides race-frei. mc 2026-07-20.
    SUBJECT_IDENTITY_SET: str = "subject_identity_set"

    # --- reserviert für spätere Builds (hier dokumentiert, noch nicht aktiv) ---
    # NOTIFICATION_SENT, RESTORE_PERFORMED

    #: Alle aktuell gültigen Werte. Erweitern, nie entfernen/umbenennen.
    ALL: FrozenSet[str] = frozenset(
        {
            GENESIS,
            MIGRATION_APPLIED,
            CHAIN_VERIFIED,
            CASE_CREATED,
            CASE_ASSIGNED,
            CASE_STATUS_CHANGED,
            CASE_APPROVED,
            CASE_PRIORITY_SET,
            CASE_NOTE_SET,
            CASE_EVENT_ADDED,
            REPORT_APPROVED,
            REPORT_SEAL_VERIFIED,
            REPORT_RETURNED,
            REPORT_ANNOTATIONS_VIEWED,
            REVIEW_COMMENT_ADDED,
            REVIEW_COMMENT_RESOLVED,
            INVESTIGATOR_CREATED,
            INVESTIGATOR_UPDATED,
            SUPPORT_SESSION_STARTED,
            SUPPORT_SESSION_ENDED,
            RBAC_GRANTED,
            RBAC_REVOKED,
            ROLE_ASSIGNED,
            ROLE_REVOKED,
            BACKUP_CREATED,
            WORKTIME_SET,
            HOLIDAY_ADDED,
            HOLIDAY_REMOVED,
            AVAILABILITY_REASON_ADDED,
            AVAILABILITY_SET,
            AVAILABILITY_REMOVED,
            EXTERNAL_MATTER_CREATED,
            EXTERNAL_MATTER_DEFERRED,
            EXTERNAL_MATTER_ANSWERED,
            EXTERNAL_MATTER_CLOSED,
            ASSESSMENT_RECORDED,
            CATALOG_SCALE_ADDED,
            CATALOG_ITEM_ADDED,
            CATALOG_CRITERION_ADDED,
            CATALOG_DEPRECATED,
            MENTORING_NOTE_CREATED,
            MENTORING_NOTE_UPDATED,
            MENTORING_NOTE_ARCHIVED,
            MENTORING_NOTE_RESTORED,
            MENTORING_NOTE_REORDERED,
            PROMOTION_DECIDED,
            CASE_RELEASE_GRANTED,
            CASE_RELEASE_REVOKED,
            ONBOARDING_STEP_SET,
            SUBJECT_IDENTITY_SET,
        }
    )

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """True, wenn value ein bekannter, aktiver Ereignistyp ist."""
        return value in cls.ALL
