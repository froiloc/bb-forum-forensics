# =============================================================================
# management/migrations/coordinator/m024_crossfinding_feedback.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Migration M024 — coordinator.db (ADDITIV)
#   Legt 'crossfinding_feedback' an (Build 507, AP-2A, Idee 7): den
#   QUERFUND-RUECKKANAL. Je Querfund haelt hoechstens EINE Zeile den Ist-Stand
#   des MENSCHLICHEN Umgangs damit (zugestellt / quittiert / verwertet /
#   nicht_relevant); die Historie der Uebergaenge liegt im hash-verketteten
#   audit_log.
#
# WARUM (Grundregel 1): 'pending_cross_annotations.integrated_at' belegt nur,
#   dass die TECHNIK die Fremd-Annotation kopiert hat. Ob ein MENSCH sie je
#   gesehen, verwertet oder verworfen hat, war bisher unbelegt. Genau dieser
#   Nachweis entsteht hier — der TRANSPORT bleibt unangetastet.
#
# FESTLEGUNGEN (Bauplan A2 Par. 2.2):
#   1. UNIQUE(finding_id) — eine Zeile je Querfund, Ist-Stand. Bauform wie
#      identified_subject (M018) und forum_promotion (M015).
#   2. KEIN FK auf pending_cross_annotations — bewusst. Jene Tabelle wird zur
#      LAUFZEIT von db/coordinator_db.py mitverwaltet (Absicherung gegen Bug
#      2.78, siehe M023); ein FK wuerde die Reihenfolge von Migration und
#      Laufzeit-DDL hart koppeln und im Fehlerfall die produktive
#      Querfund-Pipeline blockieren. Stattdessen prueft das REPO die Existenz
#      des Fundes INNERHALB der Transaktion und wirft sichtbar, wenn er fehlt —
#      die belegte statt der stillen Variante.
#   3. 'subject_id' wird MITGEFUEHRT, obwohl aus dem Fund ableitbar: die
#      Rueckkanal-Sicht filtert damit ohne Join auf eine Tabelle, deren Zeilen
#      die Pipeline parallel schreibt. Forensisch ist es die KOPIE ZUM
#      ZEITPUNKT DER ENTSCHEIDUNG — der Beleg, auf welches Subjekt sich die
#      Entscheidung bezog.
#   4. CHECK auf 'status_code' (geschlossene Menge, deckungsgleich mit
#      crossfinding_channel_status.STORED_STATUSES) — Linie M010/M015/M016/M018.
#      'offen' steht bewusst NICHT darin: es ist der Pseudo-Zustand, den die
#      ABWESENHEIT einer Zeile ausdrueckt.
#   5. KEIN RBAC-SEED: 'crossref.view'/'crossref.edit' (M018) werden
#      wiederverwendet (gleiche F5-Familie, Entscheidungslinie Build 474 Par. 3);
#      der Faehigkeitskatalog bleibt bei 33.
#
# SENSIBILITAET: 'reason' (Grund bzw. Basis) ist Freitext und steht nie im
#   audit_log-Payload — dort nur Fakten + Textlaenge (Regel wie M018).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + Guard. KIND='additive'.
# MIGRATIONSKLASSE: rein additiv, NUR coordinator.db, neue Tabelle —
#   Ermittler-Ergebnisdaten unberuehrt, Migrationsvorbehalt greift nicht.
#
# Beleg: mc 2026-07-24 (Auftrag "A1 bis A4"); Bauplan
#   claude_Bauplan_A2_QuerfundRueckkanal_v0_1.md.
# Version: v0.8.507 · Build: 507 · 2026-07-24
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 24
NAME = "Querfund-Rueckkanal (crossfinding_feedback)"
KIND = "additive"


_DDL_FEEDBACK = """
CREATE TABLE IF NOT EXISTS crossfinding_feedback (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id        INTEGER NOT NULL,   -- pending_cross_annotations.id
    subject_id        INTEGER NOT NULL,   -- Ziel-Subjekt (Kopie zum Zeitpunkt)
    status_code       TEXT    NOT NULL
                      CHECK(status_code IN
                            ('zugestellt','quittiert','verwertet',
                             'nicht_relevant')),
    reason            TEXT    NOT NULL DEFAULT '',  -- Grund/Basis (SENSIBEL)
    decided_by        INTEGER REFERENCES person(id),
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq INTEGER NOT NULL REFERENCES audit_log(seq),
    UNIQUE(finding_id)
)
"""

# Kernabfragen der Sicht: "was ist noch nicht quittiert?" und "was betrifft
# dieses Subjekt?".
_IDX_STATUS = (
    "ix_cff_status",
    "CREATE INDEX IF NOT EXISTS ix_cff_status "
    "ON crossfinding_feedback (status_code)",
)
_IDX_SUBJECT = (
    "ix_cff_subject",
    "CREATE INDEX IF NOT EXISTS ix_cff_subject "
    "ON crossfinding_feedback (subject_id)",
)

_INDICES = (_IDX_STATUS, _IDX_SUBJECT)
_TABLES = ("crossfinding_feedback",)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _index_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,)).fetchone() is not None


def up(con: sqlite3.Connection) -> None:
    done = (all(_table_exists(con, t) for t in _TABLES)
            and all(_index_exists(con, ix) for ix, _ in _INDICES))
    if done:
        logger.info("M024: crossfinding_feedback bereits vorhanden — No-op.")
        return

    con.execute(_DDL_FEEDBACK)
    for _name, ddl in _INDICES:
        con.execute(ddl)

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    for t in _TABLES:
        if not _table_exists(con, t):
            raise RuntimeError("M024: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M024: Index '%s' fehlt nach up()." % ix)

    logger.info("M024: crossfinding_feedback + %d Indizes angelegt (kein "
                "RBAC-Seed — crossref.view/edit aus M018 wiederverwendet).",
                len(_INDICES))
