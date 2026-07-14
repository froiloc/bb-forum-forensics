# =============================================================================
# management/mentoring_notes/mentoring_notes_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Zugriffsschicht auf 'mentoring_notes' + 'mentoring_note_tags' (M012, Build
#   401). SCHREIBEN ausschliesslich ueber das CoordinatorWriter-Gateway:
#   fachlicher Write + audit_log-Beleg committen in EINER Transaktion oder gar
#   nicht. Es gibt damit keine Aenderung an einer Betreuungs-Notiz ohne
#   lueckenlosen Beleg (Grundregel 1).
#
# SENSIBILITAETSREGEL (uebernommen von CasesRepo.set_note / external_matters):
#   Freitexte (title, body, tags) gehen NICHT in den audit_log-Payload. Dort
#   stehen nur FAKTEN (note_id, owner, subject, status, color, pinned) und
#   TEXTLAENGEN/Tag-Anzahl. Der Text lebt in der Fachtabelle — dort, wo die
#   RBAC-Kapselung greift. Das Audit-Log ist ein Beleg, kein Notizbuch.
#
# WEICH LOESCHBAR — ABER NIE PHYSISCH:
#   'archive()' setzt nur 'archived_at' (+ 'archived_by'); 'restore()' hebt es
#   auf. Es gibt bewusst KEIN delete(). Anders als bei external_matters
#   (Ermittlungsdaten, Endzustaende UNWIDERRUFLICH) ist das hier gewuenscht:
#   diese Notizen sind Merkzettel der Leitung, kein Beweis.
#
# ABGRENZUNG: KEIN case_events-Spiegel — eine Betreuungs-Notiz haengt an einer
#   PERSON (subject_person_id, optional), nicht an einem Fall. Ihr einziger
#   Beleg ist das audit_log.
#
# Beleg: mc 2026-07-13 (Bauplan_Betreuungsnotizen_v0_1.md, Block 1).
# Version: v0.7.401 · Build: 401 · 2026-07-13
# =============================================================================

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter
from management.mentoring_notes import note_colors
from management.mentoring_notes.mentoring_note_record import (
    ALL_STATUSES,
    MentoringNoteRecord,
    STATUS_OPEN,
)

logger = logging.getLogger(__name__)

#: Abstand zwischen zwei Sortier-Indizes (Luecken-Spacing). Zwischen zwei
#: Nachbarn passen so bis zu ~1000 spaetere Einfuegungen, bevor eine
#: Renormalisierung noetig wird (Block 4). Bewusst grosszuegig.
SORT_STEP: int = 1000

#: Sentinel fuer update(): unterscheidet "Feld nicht uebergeben" (unveraendert)
#: von "Feld ausdruecklich auf None/leer gesetzt" (z. B. Betroffenen loeschen).
_UNSET: Any = object()


class MentoringNotesError(Exception):
    """Fachlicher Fehler beim Zugriff auf Betreuungs-Notizen."""


class MentoringNotesRepo:
    """
    Zugriffsschicht auf die Betreuungs-Notizen. Lesen ist ohne Writer moeglich
    (mode=ro-Verbindung); JEDER Schreibweg verlangt einen CoordinatorWriter und
    scheitert sonst laut (kein unauditierter Schreibpfad).
    """

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._writer = writer

    # ------------------------------------------------------------------ Hilfen
    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise MentoringNotesError(
                "Schreibzugriff ohne CoordinatorWriter — kein unauditierter "
                "Schreibpfad zulaessig.")
        return self._writer

    @staticmethod
    def _tlen(text: Optional[str]) -> int:
        """Zeichenlaenge eines (evtl. None-)Freitextes fuer den Audit-Payload."""
        return len(text) if text else 0

    @staticmethod
    def _norm_tags(tags: Optional[Sequence[str]]) -> Tuple[str, ...]:
        """
        Normalisiert Schlagworte: trimmen, Leere verwerfen, deduplizieren,
        aufsteigend sortieren. Deterministisch (Tests/Diffs), damit dieselbe
        Tag-Menge stets identisch gespeichert und belegt wird.
        """
        if not tags:
            return tuple()
        seen = []
        for t in tags:
            s = (t or "").strip()
            if s and s not in seen:
                seen.append(s)
        return tuple(sorted(seen))

    def _person_exists(self, con: sqlite3.Connection, person_id: int) -> bool:
        return con.execute(
            "SELECT 1 FROM person WHERE id = ?", (person_id,)
        ).fetchone() is not None

    def _note_row(self, con: sqlite3.Connection,
                  note_id: int) -> Optional[sqlite3.Row]:
        return con.execute(
            "SELECT * FROM mentoring_notes WHERE id = ?", (note_id,)
        ).fetchone()

    def _next_sort_index(self, con: sqlite3.Connection, owner_id: int) -> int:
        """
        Naechster Sortier-Index am ENDE des aktiven Boards der Autor:in.
        Neue (und duplizierte) Notizen landen unten; die Reihenfolge bleibt so
        deterministisch, das Umsortieren (Drag & Drop, Block 4) uebernimmt die
        Feinordnung. MAX ueber die AKTIVEN Notizen (archivierte zaehlen nicht).
        """
        row = con.execute(
            "SELECT COALESCE(MAX(sort_index), 0) AS mx FROM mentoring_notes "
            "WHERE owner_id = ? AND archived_at IS NULL", (owner_id,)
        ).fetchone()
        return int(row["mx"]) + SORT_STEP

    def _write_tags(self, con: sqlite3.Connection, note_id: int,
                    tags: Tuple[str, ...]) -> None:
        """
        Ersetzt die Tag-Menge einer Notiz (DELETE + INSERT) — in DERSELBEN
        Transaktion wie der auditierte Notiz-Write, damit nie ein Tag-Rest ohne
        Beleg zurueckbleibt.
        """
        con.execute("DELETE FROM mentoring_note_tags WHERE note_id = ?",
                    (note_id,))
        for tag in tags:
            con.execute(
                "INSERT INTO mentoring_note_tags (note_id, tag) VALUES (?, ?)",
                (note_id, tag))

    # -------------------------------------------------------------------- Lesen
    def _tags_for(self, con: sqlite3.Connection,
                  note_ids: Sequence[int]) -> Dict[int, Tuple[str, ...]]:
        """Alle Tags fuer eine Menge Notiz-IDs in EINER Abfrage (kein N+1)."""
        result: Dict[int, List[str]] = {nid: [] for nid in note_ids}
        if not note_ids:
            return {}
        marks = ",".join("?" for _ in note_ids)
        rows = con.execute(
            "SELECT note_id, tag FROM mentoring_note_tags "
            "WHERE note_id IN (%s) ORDER BY tag" % marks,
            tuple(note_ids)).fetchall()
        for r in rows:
            result.setdefault(r["note_id"], []).append(r["tag"])
        return {nid: tuple(sorted(tags)) for nid, tags in result.items()}

    def _to_record(self, row: sqlite3.Row,
                   tags: Tuple[str, ...]) -> MentoringNoteRecord:
        return MentoringNoteRecord(
            id=int(row["id"]),
            owner_id=int(row["owner_id"]),
            owner_display_name=row["owner_display_name"]
            if "owner_display_name" in row.keys() else None,
            subject_person_id=(int(row["subject_person_id"])
                               if row["subject_person_id"] is not None else None),
            subject_display_name=row["subject_display_name"]
            if "subject_display_name" in row.keys() else None,
            title=row["title"],
            body=row["body"],
            color=row["color"],
            tags=tags,
            status=row["status"],
            pinned=bool(row["pinned"]),
            sort_index=int(row["sort_index"]),
            created_by=int(row["created_by"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
            archived_at=(int(row["archived_at"])
                         if row["archived_at"] is not None else None),
            archived_by=(int(row["archived_by"])
                         if row["archived_by"] is not None else None),
            created_audit_seq=int(row["created_audit_seq"]),
            audit_seq=int(row["audit_seq"]),
        )

    def get(self, note_id: int) -> Optional[MentoringNoteRecord]:
        """Eine einzelne Notiz (mit Anzeigenamen + Tags) — oder None."""
        row = self._con.execute(
            "SELECT n.*, po.display_name AS owner_display_name, "
            "       ps.display_name AS subject_display_name "
            "FROM mentoring_notes n "
            "LEFT JOIN person po ON po.id = n.owner_id "
            "LEFT JOIN person ps ON ps.id = n.subject_person_id "
            "WHERE n.id = ?", (note_id,)).fetchone()
        if row is None:
            return None
        tags = self._tags_for(self._con, [int(row["id"])]).get(
            int(row["id"]), tuple())
        return self._to_record(row, tags)

    def list_notes(
        self, *, owner_id: Optional[int] = None, archived: bool = False,
        status: Optional[str] = None, color: Optional[str] = None,
        tag: Optional[str] = None, subject_person_id: Optional[int] = None,
    ) -> List[MentoringNoteRecord]:
        """
        Liste der Notizen in Board-Reihenfolge (angeheftet zuerst, dann
        sort_index, dann id).

        owner_id=None  -> ALLE Boards (nur fuer Scope 'alle'/Vertretung; der
                          Aufrufer setzt das Recht durch). Ein konkretes
                          owner_id liefert das PRIVATE Board dieser Autor:in.
        archived=False -> aktive Notizen; True -> Archiv.
        status/color/tag/subject_person_id -> optionale Feinfilter (serverseitig).
        """
        where = []
        params: List[Any] = []

        if owner_id is not None:
            where.append("n.owner_id = ?")
            params.append(owner_id)

        # archived ist ein Zustand, kein Freitext -> immer explizit filtern
        # (kein stiller Mix aus aktiv + Archiv).
        if archived:
            where.append("n.archived_at IS NOT NULL")
        else:
            where.append("n.archived_at IS NULL")

        if status is not None:
            where.append("n.status = ?")
            params.append(status)
        if color is not None:
            where.append("n.color = ?")
            params.append(color)
        if subject_person_id is not None:
            where.append("n.subject_person_id = ?")
            params.append(subject_person_id)
        if tag is not None and tag.strip():
            where.append(
                "EXISTS (SELECT 1 FROM mentoring_note_tags t "
                "        WHERE t.note_id = n.id AND t.tag = ?)")
            params.append(tag.strip())

        sql = (
            "SELECT n.*, po.display_name AS owner_display_name, "
            "       ps.display_name AS subject_display_name "
            "FROM mentoring_notes n "
            "LEFT JOIN person po ON po.id = n.owner_id "
            "LEFT JOIN person ps ON ps.id = n.subject_person_id "
        )
        if where:
            sql += "WHERE " + " AND ".join(where) + " "
        # pinned DESC: angeheftete Notizen stehen oben; dann die freie Ordnung.
        sql += "ORDER BY n.pinned DESC, n.sort_index ASC, n.id ASC"

        rows = self._con.execute(sql, tuple(params)).fetchall()
        tagmap = self._tags_for(self._con, [int(r["id"]) for r in rows])
        return [self._to_record(r, tagmap.get(int(r["id"]), tuple()))
                for r in rows]

    # ----------------------------------------------------------------- Anlegen
    def _validate_common(self, *, title: Optional[str], status: str,
                         color: str) -> None:
        if not (title or "").strip():
            raise MentoringNotesError("Ueberschrift (title) ist Pflicht.")
        if status not in ALL_STATUSES:
            raise MentoringNotesError(
                "Unbekannter Status '%s' (gueltig: %s)."
                % (status, ", ".join(ALL_STATUSES)))
        if not note_colors.is_valid(color):
            raise MentoringNotesError(
                "Unbekannte Farbe '%s' (gueltig: %s)."
                % (color, ", ".join(note_colors.COLOR_ORDER)))

    def create(
        self, *, owner_id: int, title: str, body: str = "",
        color: str = note_colors.DEFAULT_COLOR, status: str = STATUS_OPEN,
        pinned: bool = False, subject_person_id: Optional[int] = None,
        tags: Optional[Sequence[str]] = None,
        actor_id: Optional[int] = None, meta: Optional[Any] = None,
        _duplicated_from: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Legt eine Betreuungs-Notiz an. -> {'note_id', 'audit_seq'}.
        Der Freitext geht in die Fachtabelle, NICHT ins Audit (nur Laengen).
        """
        writer = self._require_writer()
        self._validate_common(title=title, status=status, color=color)
        norm_tags = self._norm_tags(tags)
        now = int(time.time())
        state: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            if not self._person_exists(con, owner_id):
                raise MentoringNotesError(
                    "Autor:in person_id=%s existiert nicht." % owner_id)
            if subject_person_id is not None and not self._person_exists(
                    con, subject_person_id):
                raise MentoringNotesError(
                    "Betroffene:r person_id=%s existiert nicht."
                    % subject_person_id)
            sort_index = self._next_sort_index(con, owner_id)
            # audit_seq/created_audit_seq sind NOT NULL — sie werden erst im
            # after_audit-Hook bekannt (Platzhalter 0, wie M010). Beides in
            # DERSELBEN Transaktion: es kann keine Zeile mit audit_seq=0
            # committen.
            cur = con.execute(
                "INSERT INTO mentoring_notes "
                "(owner_id, subject_person_id, title, body, color, status, "
                " pinned, sort_index, created_by, created_at, updated_at, "
                " audit_seq, created_audit_seq) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)",
                (owner_id, subject_person_id, title, body or "", color, status,
                 1 if pinned else 0, sort_index, actor_id, now, now),
            )
            state["note_id"] = int(cur.lastrowid)
            self._write_tags(con, state["note_id"], norm_tags)
            # Audit-Payload: FAKTEN, keine Freitexte (Sensibilitaetsregel).
            payload = {
                "note_id": state["note_id"], "owner_id": owner_id,
                "subject_person_id": subject_person_id, "status": status,
                "color": color, "pinned": bool(pinned),
                "title_len": self._tlen(title), "body_len": self._tlen(body),
                "tag_count": len(norm_tags),
            }
            if _duplicated_from is not None:
                payload["duplicated_from"] = _duplicated_from
            return payload

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE mentoring_notes SET audit_seq = ?, "
                "created_audit_seq = ? WHERE id = ?",
                (seq, seq, state["note_id"]))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.MENTORING_NOTE_CREATED,
            actor_id=actor_id, target_type="mentoring_note",
            target_id=None, meta=meta, after_audit=_after,
        )
        logger.info("Betreuungs-Notiz %s angelegt (owner %s, subject %s).",
                    state["note_id"], owner_id, subject_person_id)
        return {"note_id": state["note_id"], "audit_seq": seq}

    def duplicate(self, note_id: int, *, actor_id: Optional[int] = None,
                  meta: Optional[Any] = None) -> Dict[str, Any]:
        """
        Dupliziert eine Notiz (gleiche:r Autor:in). Die Kopie ist immer
        'offen', nicht angeheftet, Titel mit Suffix ' (Kopie)'. Der Beleg ist
        ein MENTORING_NOTE_CREATED mit 'duplicated_from' im Payload.
        """
        src = self.get(note_id)
        if src is None:
            raise MentoringNotesError("Notiz %s existiert nicht." % note_id)
        return self.create(
            owner_id=src.owner_id, title=(src.title + " (Kopie)"),
            body=src.body, color=src.color, status=STATUS_OPEN, pinned=False,
            subject_person_id=src.subject_person_id, tags=src.tags,
            actor_id=actor_id, meta=meta, _duplicated_from=note_id,
        )

    # ---------------------------------------------------------------- Aendern
    def update(
        self, note_id: int, *, actor_id: Optional[int] = None,
        title: Any = _UNSET, body: Any = _UNSET, color: Any = _UNSET,
        status: Any = _UNSET, pinned: Any = _UNSET,
        subject_person_id: Any = _UNSET, tags: Any = _UNSET,
        meta: Optional[Any] = None,
    ) -> int:
        """
        Partielle AEnderung: nur uebergebene Felder aendern (Sentinel _UNSET =
        unveraendert). 'subject_person_id=None' loescht die Zuordnung bewusst.
        -> audit_seq. Der geaenderte Freitext bleibt in der Fachtabelle.
        """
        writer = self._require_writer()
        now = int(time.time())

        # Zieltext/-status/-farbe fuer die Validierung aufloesen (aus Eingabe
        # oder Bestand). So validieren wir den RESULTIERENDEN Zustand.
        current = self.get(note_id)
        if current is None:
            raise MentoringNotesError("Notiz %s existiert nicht." % note_id)

        new_title = current.title if title is _UNSET else title
        new_status = current.status if status is _UNSET else status
        new_color = current.color if color is _UNSET else color
        self._validate_common(title=new_title, status=new_status,
                              color=new_color)

        norm_tags = (self._norm_tags(tags) if tags is not _UNSET else None)

        changed: List[str] = []
        state: Dict[str, Any] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            sets: List[str] = []
            params: List[Any] = []

            if title is not _UNSET:
                sets.append("title = ?"); params.append(new_title)
                changed.append("title")
            if body is not _UNSET:
                sets.append("body = ?"); params.append(body or "")
                changed.append("body")
            if color is not _UNSET:
                sets.append("color = ?"); params.append(new_color)
                changed.append("color")
            if status is not _UNSET:
                sets.append("status = ?"); params.append(new_status)
                changed.append("status")
            if pinned is not _UNSET:
                sets.append("pinned = ?"); params.append(1 if pinned else 0)
                changed.append("pinned")
            if subject_person_id is not _UNSET:
                if (subject_person_id is not None
                        and not self._person_exists(con, subject_person_id)):
                    raise MentoringNotesError(
                        "Betroffene:r person_id=%s existiert nicht."
                        % subject_person_id)
                sets.append("subject_person_id = ?")
                params.append(subject_person_id)
                changed.append("subject_person_id")

            # updated_at immer mitschreiben (auch wenn nur Tags sich aendern).
            sets.append("updated_at = ?"); params.append(now)
            params.append(note_id)
            con.execute(
                "UPDATE mentoring_notes SET %s WHERE id = ?"
                % ", ".join(sets), tuple(params))

            if norm_tags is not None:
                self._write_tags(con, note_id, norm_tags)
                changed.append("tags")

            # Resultierende Fakten fuer den Beleg neu einlesen (kein Freitext).
            row = self._note_row(con, note_id)
            state["row"] = row
            return {
                "note_id": note_id, "owner_id": int(row["owner_id"]),
                "changed": changed,
                "subject_person_id": (int(row["subject_person_id"])
                                      if row["subject_person_id"] is not None
                                      else None),
                "status": row["status"], "color": row["color"],
                "pinned": bool(row["pinned"]),
                "title_len": self._tlen(row["title"]),
                "body_len": self._tlen(row["body"]),
                "tag_count": (len(norm_tags) if norm_tags is not None
                              else con.execute(
                                  "SELECT COUNT(*) c FROM mentoring_note_tags "
                                  "WHERE note_id=?", (note_id,)).fetchone()[0]),
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE mentoring_notes SET audit_seq = ? WHERE id = ?",
                        (seq, note_id))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.MENTORING_NOTE_UPDATED,
            actor_id=actor_id, target_type="mentoring_note",
            target_id=str(note_id), meta=meta, after_audit=_after,
        )
        logger.info("Betreuungs-Notiz %s geaendert (%s).",
                    note_id, ", ".join(changed) or "keine Felder")
        return seq

    def archive(self, note_id: int, *, actor_id: Optional[int] = None,
                meta: Optional[Any] = None) -> int:
        """Archiviert eine Notiz (Soft-Delete, wiederherstellbar). -> audit_seq."""
        writer = self._require_writer()
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._note_row(con, note_id)
            if row is None:
                raise MentoringNotesError("Notiz %s existiert nicht." % note_id)
            if row["archived_at"] is not None:
                raise MentoringNotesError(
                    "Notiz %s ist bereits archiviert." % note_id)
            con.execute(
                "UPDATE mentoring_notes SET archived_at = ?, archived_by = ?, "
                "updated_at = ? WHERE id = ?",
                (now, actor_id, now, note_id))
            return {"note_id": note_id, "owner_id": int(row["owner_id"])}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE mentoring_notes SET audit_seq = ? WHERE id = ?",
                        (seq, note_id))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.MENTORING_NOTE_ARCHIVED,
            actor_id=actor_id, target_type="mentoring_note",
            target_id=str(note_id), meta=meta, after_audit=_after,
        )
        logger.info("Betreuungs-Notiz %s archiviert.", note_id)
        return seq

    def restore(self, note_id: int, *, actor_id: Optional[int] = None,
                meta: Optional[Any] = None) -> int:
        """Holt eine Notiz aus dem Archiv zurueck. -> audit_seq."""
        writer = self._require_writer()
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            row = self._note_row(con, note_id)
            if row is None:
                raise MentoringNotesError("Notiz %s existiert nicht." % note_id)
            if row["archived_at"] is None:
                raise MentoringNotesError(
                    "Notiz %s ist nicht archiviert." % note_id)
            con.execute(
                "UPDATE mentoring_notes SET archived_at = NULL, "
                "archived_by = NULL, updated_at = ? WHERE id = ?",
                (now, note_id))
            return {"note_id": note_id, "owner_id": int(row["owner_id"])}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute("UPDATE mentoring_notes SET audit_seq = ? WHERE id = ?",
                        (seq, note_id))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.MENTORING_NOTE_RESTORED,
            actor_id=actor_id, target_type="mentoring_note",
            target_id=str(note_id), meta=meta, after_audit=_after,
        )
        logger.info("Betreuungs-Notiz %s wiederhergestellt.", note_id)
        return seq

    def reorder(self, owner_id: int, ordered_ids: Sequence[int], *,
                actor_id: Optional[int] = None,
                meta: Optional[Any] = None) -> int:
        """
        Setzt die Board-Reihenfolge der AKTIVEN Notizen einer Autor:in neu
        (Drag & Drop). EIN gebuendelter Beleg pro Drop (Payload = Reihenfolge),
        nicht pro Maus-Bewegung. -> audit_seq.

        Alle IDs muessen zu 'owner_id' gehoeren und AKTIV (nicht archiviert)
        sein; sonst scheitert der Vorgang laut (kein stilles Ueberspringen).
        Doppelte IDs sind unzulaessig.
        """
        writer = self._require_writer()
        now = int(time.time())
        ids = [int(i) for i in ordered_ids]
        if len(set(ids)) != len(ids):
            raise MentoringNotesError("Doppelte Notiz-IDs in der Reihenfolge.")

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            for nid in ids:
                row = self._note_row(con, nid)
                if row is None:
                    raise MentoringNotesError("Notiz %s existiert nicht." % nid)
                if int(row["owner_id"]) != owner_id:
                    raise MentoringNotesError(
                        "Notiz %s gehoert nicht zu owner %s." % (nid, owner_id))
                if row["archived_at"] is not None:
                    raise MentoringNotesError(
                        "Notiz %s ist archiviert und nicht sortierbar." % nid)
            # Neue Indizes mit Luecken-Spacing (1000, 2000, ...), in der
            # uebergebenen Reihenfolge. updated_at wandert mit.
            for rank, nid in enumerate(ids, start=1):
                con.execute(
                    "UPDATE mentoring_notes SET sort_index = ?, updated_at = ? "
                    "WHERE id = ?", (rank * SORT_STEP, now, nid))
            return {"owner_id": owner_id, "ordered_ids": ids, "count": len(ids)}

        def _after(con: sqlite3.Connection, seq: int) -> None:
            # Der Reorder-Beleg wird ALLEN betroffenen Notizen als letzte
            # AEnderung zugeschrieben (audit_seq), damit jede Karte auf ihren
            # Beleg zeigt.
            for nid in ids:
                con.execute(
                    "UPDATE mentoring_notes SET audit_seq = ? WHERE id = ?",
                    (seq, nid))

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.MENTORING_NOTE_REORDERED,
            actor_id=actor_id, target_type="mentoring_board",
            target_id=str(owner_id), meta=meta, after_audit=_after,
        )
        logger.info("Board %s umsortiert (%d Notizen).", owner_id, len(ids))
        return seq
