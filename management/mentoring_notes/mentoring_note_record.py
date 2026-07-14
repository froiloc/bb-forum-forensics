# =============================================================================
# management/mentoring_notes/mentoring_note_record.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Reines Lese-DTO (frozen dataclass) EINER Betreuungs-Notiz (Build 401).
#   Eigene Datei gemaess Grundregel 10 (jede Klasse in eine eigene Datei).
#
#   Das DTO buendelt die Notiz-Kopfzeile mit ihren Tags und den (per LEFT JOIN
#   aufgeloesten) Anzeigenamen von Autor:in und betroffenem Mitarbeiter, damit
#   die Frontend-Schicht keine zweite Abfrage braucht.
#
# STATUS-VOKABULAR (stabil, maschinenlesbar; das Frontend lokalisiert):
#   'offen'    — noch abzuarbeiten.
#   'erledigt' — abgearbeitet (frei ruecksetzbar; es ist ein Merkzettel, KEIN
#                forensischer Endzustand wie bei external_matters).
#
# 'MESSEN, NICHT RECHNEN': alle Felder sind der GESCHRIEBENE Wert aus
#   mentoring_notes/-_tags; nichts wird abgeleitet errechnet. is_archived ist
#   eine reine Ableitung aus archived_at (None = aktiv).
#
# Version: v0.7.401 · Build: 401 · 2026-07-13
# =============================================================================

from dataclasses import dataclass
from typing import Optional, Tuple

#: Gueltige Status-Werte (fuer Validierung/Tests).
STATUS_OPEN: str = "offen"
STATUS_DONE: str = "erledigt"
ALL_STATUSES: Tuple[str, ...] = (STATUS_OPEN, STATUS_DONE)


@dataclass(frozen=True)
class MentoringNoteRecord:
    """
    Eine Betreuungs-Notiz als reines Lese-DTO.

    Identitaet / Zuordnung:
        id                — Primaerschluessel der Notiz.
        owner_id          — Autor:in (traegt die Sichtbarkeit: privates Board).
        owner_display_name— Anzeigename der Autor:in (LEFT JOIN person).
        subject_person_id — betroffener Mitarbeiter (None = allgemeine Notiz).
        subject_display_name — dessen Anzeigename (None, falls nicht gesetzt).

    Inhalt (Git-Commit-Metapher):
        title  — erste Zeile, immer sichtbar (Pflicht, nicht leer).
        body   — Folgezeilen, erst nach Aufklappen (kann leer sein).
        color  — Farbcode (Vokabular: note_colors.py).
        tags   — Schlagworte (aufsteigend sortiert, dedupliziert).

    Zustand / Ordnung:
        status     — 'offen' | 'erledigt'.
        pinned     — angeheftet (True/False).
        sort_index — Reihenfolge im Board (Drag & Drop).

    Lebenslauf / Soft-Delete:
        created_by, created_at — Anlage (Unix-Sekunden).
        updated_at             — letzte AEnderung (Unix-Sekunden).
        archived_at, archived_by — Archiv-Flag (None = aktiv).

    Audit-Belegverweise (Nachpruefbarkeit — 'welche Zeile im audit_log'):
        created_audit_seq — audit_log.seq der Anlage (unveraenderlich).
        audit_seq         — audit_log.seq der LETZTEN AEnderung.
    """
    id: int
    owner_id: int
    owner_display_name: Optional[str]
    subject_person_id: Optional[int]
    subject_display_name: Optional[str]

    title: str
    body: str
    color: str
    tags: Tuple[str, ...]

    status: str
    pinned: bool
    sort_index: int

    created_by: int
    created_at: int
    updated_at: int
    archived_at: Optional[int]
    archived_by: Optional[int]

    created_audit_seq: int
    audit_seq: int

    @property
    def is_archived(self) -> bool:
        """True, wenn die Notiz im Archiv liegt (archived_at gesetzt)."""
        return self.archived_at is not None

    def to_json(self) -> dict:
        """
        Serialisiert die Notiz in das JSON-Item fuer die API/Frontend-Schicht.
        Reine Abbildung — keine Logik. Der Freitext (title/body/tags) IST hier
        enthalten (er lebt in der RBAC-gekapselten Fachschicht, nicht im Audit).
        """
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "owner_display_name": self.owner_display_name,
            "subject_person_id": self.subject_person_id,
            "subject_display_name": self.subject_display_name,
            "title": self.title,
            "body": self.body,
            "color": self.color,
            "tags": list(self.tags),
            "status": self.status,
            "pinned": self.pinned,
            "sort_index": self.sort_index,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "archived_at": self.archived_at,
            "archived_by": self.archived_by,
            "created_audit_seq": self.created_audit_seq,
            "audit_seq": self.audit_seq,
            "is_archived": self.is_archived,
        }
