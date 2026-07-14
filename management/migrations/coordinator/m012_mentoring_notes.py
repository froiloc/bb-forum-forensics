# =============================================================================
# management/migrations/coordinator/m012_mentoring_notes.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M012 — coordinator.db (ADDITIV)
#   Legt die BETREUUNGS-NOTIZEN ("Post-its") der Ermittler-Betreuung an
#   (Build 401, Welle 1). Wunsch der Chef-Ermittlerin (Projektgespraech
#   2026-07-13): frei gestaltbare Merkzettel zu den Belangen einzelner
#   Mitarbeiter — abzuarbeiten, mit Schlagworten und Farbe, aufgebaut wie eine
#   Git-Commit-Message (erste Zeile = Ueberschrift, Rest erst nach Aufklappen).
#
# FORENSISCHE EINORDNUNG (mc-Abstimmung 2026-07-13) — WICHTIG:
#   Diese Notizen sind ARBEITS-/ORGANISATIONSNOTIZEN DER LEITUNG, KEINE
#   Ermittlungsdaten ueber Beschuldigte. Diese Abgrenzung rechtfertigt
#   Eigenschaften, die bei Ermittlungsdaten (z. B. external_matters, M010)
#   ausdruecklich VERBOTEN waeren:
#     - ARCHIVIEREN + WIEDERHERSTELLEN (Soft-Delete via 'archived_at'-Flag).
#       external_matters kennt bewusst KEIN reopen()/delete() — hier ist es
#       gewuenscht, weil ein Merkzettel der Leitung kein Beweis ist.
#     - DUPLIZIEREN, UMSORTIEREN (Drag & Drop) — mutable Board.
#   Der forensische KERN bleibt dennoch unangetastet:
#     - Kein Schreibzugriff ohne Beleg: jede Anlage/AEnderung/Archivierung/
#       Wiederherstellung/Umsortierung laeuft ueber CoordinatorWriter und
#       erzeugt einen hash-verketteten audit_log-Eintrag (Grundregel 1).
#     - KEIN physisches Loeschen — nur 'archived_at'.
#     - SENSIBILITAETSREGEL (wie CasesRepo.set_note / external_matters): der
#       Freitext (title, body, tags) steht NIE im audit_log-Payload; dort nur
#       FAKTEN + TEXTLAENGEN. Der Text lebt in der Fachtabelle, wo die
#       RBAC-Kapselung greift.
#
# ABGRENZUNG ZU case_events: Betreuungs-Notizen haengen an einer PERSON
#   (subject_person_id, optional), NICHT an einem Fall (user_id). Sie werden
#   deshalb NICHT in den fallbezogenen Zeitstrahl (case_events) gespiegelt —
#   ihr einziger Beleg ist das audit_log. Ein Spiegel in case_events waere
#   fachlich falsch (sie sind keine Ereignisse EINES Falls).
#
# VOKABULAR IM CODE, nicht in der DDL:
#   'color' wird im Code validiert (mentoring_notes/note_colors.py) — bewusst
#   OHNE CHECK-Constraint, damit die Farbpalette spaeter ADDITIV erweiterbar
#   bleibt (kein Tabellen-Rebuild an produktiven Daten; gleiche Linie wie
#   matter_kinds).
#   AUSNAHME: 'status' bekommt einen CHECK ('offen'/'erledigt'), weil die
#   Zustandsmenge abgeschlossen ist und ein Tippfehler dort eine Notiz aus
#   jedem Filter fallen liesse — das waere ein stiller Verlust (Grundregel 1).
#
# SORTIERUNG (Drag & Drop): 'sort_index' als INTEGER mit LUECKEN-Spacing.
#   Eine Umsortierung schreibt idealerweise nur die verschobene Karte
#   (neuer Index = Mittelwert der Nachbarn); ist die Luecke erschoepft, folgt
#   ein deterministischer Renormalisierungs-Lauf. Determinismus vor Trickserei
#   — bewusst KEIN Fractional-Float, dessen Praezision langfristig zerfaellt.
#
# RBAC-SEED (eingefroren, m005-Prinzip): 'mentoring_notes.view' und
#   'mentoring_notes.edit' werden hier mit LITERALEN Werten geseedet. Die
#   Migration importiert ABSICHTLICH NICHT rbac/catalog.py — eine Migration
#   muss auch in Jahren noch exakt dasselbe tun, unabhaengig davon, wie der
#   Katalog sich weiterentwickelt. Die GRANTS (wer die Faehigkeit bekommt) sind
#   eine operative Entscheidung der Chef-Ermittlerin (rbac-CLI), NICHT Teil
#   dieses Builds (default-deny). Sichtbarkeit: privates Board pro Autor:in;
#   eine Vertretung/Aufsicht mit Scope 'alle' sieht fremde Boards.
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + INSERT OR IGNORE + Guard
#             (INFO-No-op beim zweiten Lauf). Inline-Verifikation -> raise ->
#             ROLLBACK im Runner.
# KIND='additive' -> rein additiv, datenneutral, kein precount/postcount.
#
# Beleg: mc 2026-07-13 (Bauplan_Betreuungsnotizen_v0_1.md, Block 1).
# Version: v0.7.401 · Build: 401 · 2026-07-13
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 12
NAME = "Betreuungs-Notizen (mentoring_notes + tags) + RBAC-Seed"
KIND = "additive"


# --- mentoring_notes ---------------------------------------------------------
#   owner_id          Autor:in der Notiz — traegt die Sichtbarkeit (privates
#                     Board; Scope 'alle' sieht fremde Boards).
#   subject_person_id betroffener Mitarbeiter (optional; NULL = allgemein).
#   title             erste Zeile (immer sichtbar) — Pflicht (im Code geprueft).
#   body              Folgezeilen (nur aufgeklappt).
#   sort_index        Reihenfolge fuer Drag & Drop (Luecken-Spacing).
#   archived_at       NULL = aktiv; gesetzt = im Archiv (Soft-Delete).
#   audit_seq         Beleg der LETZTEN AEnderung; created_audit_seq den der
#                     Anlage (unveraenderlich). Beide NOT NULL -> im
#                     after_audit-Hook gesetzt (Platzhalter 0, wie M010).
_DDL_NOTES = """
CREATE TABLE IF NOT EXISTS mentoring_notes (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id          INTEGER NOT NULL REFERENCES person(id),
    subject_person_id INTEGER REFERENCES person(id),
    title             TEXT    NOT NULL,
    body              TEXT    NOT NULL DEFAULT '',
    color             TEXT    NOT NULL DEFAULT 'gelb',   -- Vokabular: note_colors.py
    status            TEXT    NOT NULL DEFAULT 'offen'
                      CHECK(status IN ('offen','erledigt')),
    pinned            INTEGER NOT NULL DEFAULT 0,
    sort_index        INTEGER NOT NULL DEFAULT 0,
    created_by        INTEGER NOT NULL REFERENCES person(id),
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    archived_at       INTEGER,
    archived_by       INTEGER REFERENCES person(id),
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq INTEGER NOT NULL REFERENCES audit_log(seq)
)
"""

# --- mentoring_note_tags (normalisiert) --------------------------------------
#   Normalisierte Kindtabelle statt CSV/JSON-Spalte: Tags sind ABFRAGBAR
#   (Filter "alle Notizen mit Tag X") und sauber indizierbar. Loeschung einer
#   Notiz-Tag-Menge geschieht per DELETE+Neuanlage in DERSELBEN Transaktion
#   wie der auditierte Notiz-Write (kein tag-Waisenzustand ohne Beleg).
_DDL_TAGS = """
CREATE TABLE IF NOT EXISTS mentoring_note_tags (
    note_id INTEGER NOT NULL REFERENCES mentoring_notes(id),
    tag     TEXT    NOT NULL,
    PRIMARY KEY (note_id, tag)
)
"""

# Board-Index: die Kernabfrage "aktives Board einer Autor:in in Reihenfolge".
_IDX_BOARD = (
    "ix_notes_board",
    "CREATE INDEX IF NOT EXISTS ix_notes_board "
    "ON mentoring_notes (owner_id, archived_at, sort_index)",
)
# Betroffenen-Index: "alle Notizen zu Mitarbeiter X".
_IDX_SUBJECT = (
    "ix_notes_subject",
    "CREATE INDEX IF NOT EXISTS ix_notes_subject "
    "ON mentoring_notes (subject_person_id)",
)
# Tag-Index: Filter/Suche nach Schlagwort.
_IDX_TAG = (
    "ix_note_tag",
    "CREATE INDEX IF NOT EXISTS ix_note_tag "
    "ON mentoring_note_tags (tag)",
)

_INDICES = (_IDX_BOARD, _IDX_SUBJECT, _IDX_TAG)
_TABLES = ("mentoring_notes", "mentoring_note_tags")

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("mentoring_notes.view", "Betreuungs-Notizen sehen",
     "Betreuungs-Notizen (Post-its) der Ermittler-Betreuung lesen."),
    ("mentoring_notes.edit", "Betreuungs-Notizen pflegen",
     "Betreuungs-Notizen anlegen, aendern, archivieren, wiederherstellen "
     "und ordnen."),
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _index_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,)).fetchone() is not None


def _cap_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_capability WHERE code=?",
        (code,)).fetchone() is not None


def up(con: sqlite3.Connection) -> None:
    done = (all(_table_exists(con, t) for t in _TABLES)
            and all(_index_exists(con, ix) for ix, _ in _INDICES)
            and all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS))
    if done:
        logger.info("M012: mentoring_notes + RBAC-Seed bereits vorhanden "
                    "— No-op.")
        return

    # Vorbedingung: M006 (rbac_capability) muss angewandt sein. Fehlt sie, ist
    # das ein Aufbaufehler und KEIN Grund, den Seed still zu ueberspringen.
    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M012: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    con.execute(_DDL_NOTES)
    con.execute(_DDL_TAGS)
    for _name, ddl in _INDICES:
        con.execute(ddl)

    now = int(time.time())
    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now),
        )

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    for t in _TABLES:
        if not _table_exists(con, t):
            raise RuntimeError("M012: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M012: Index '%s' fehlt nach up()." % ix)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M012: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M012: mentoring_notes + mentoring_note_tags angelegt; "
                "Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
