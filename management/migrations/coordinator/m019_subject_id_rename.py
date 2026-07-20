# =============================================================================
# management/migrations/coordinator/m019_subject_id_rename.py
# IT-Forensisches Ermittlungswerkzeug — Globale Schluesselumstellung
# =============================================================================
# Migration M019 — coordinator.db (DESTRUKTIV, aber OHNE Zeilen-Kopie)
#   Globale Umstellung des Ermittlungsschluessels von 'user_id' auf
#   'subject_id' per ALTER TABLE ... RENAME COLUMN (Weg A).
#
# SCHLUESSELSCHEMA (Prepper, mc 2026-07-20):
#   Realnutzer: subject_id == users.id · Geist: subject_id == prefix +
#   mat_usernames.id (prefix = 10^Ziffernzahl(MAX(users.id)), beim Fall 1e9).
#   Beleg: claude_Entscheidung_SubjectID_Schema_Geisternutzer_2026-07-20.md.
#   Fuer alle BESTEHENDEN Zeilen gilt subject_id == user_id (nur Realnutzer
#   vorhanden) — die Umbenennung ist daher semantisch verlustfrei; Geister
#   werden durch sie erst schluesselfaehig.
#
# WEG A (mc-Freigabe 2026-07-20, nach bestandenem PoC):
#   SQLite >= 3.25 mit legacy_alter_table=OFF zieht bei RENAME COLUMN die
#   REFERENCES-Klauseln anderer Tabellen sowie Trigger-/View-/Index-Ruempfe
#   automatisch nach (derselbe Mechanismus trug bereits M005
#   investigators->person). PoC-Nachweis auf Kopie (poc_weg_a.py):
#   PK-Spalte cases.user_id umbenennbar; alle 4 FK-Klauseln, m011-Trigger/
#   View und 6 Indizes automatisch nachgezogen; foreign_key_check leer;
#   integrity_check ok; Zeilenzahlen/Werte identisch; Append-only-Schutz
#   (inkl. Beleg-Kopplung audit_seq 0->seq) intakt. KEINE Zeile wird kopiert.
#
# BLAST-RADIUS (gemessen auf HEAD a26cffd, 2026-07-20):
#   Anker:            cases.user_id (PRIMARY KEY)
#   FK-Kinder (4):    case_events, external_matters, investigation_results
#                     (Trigger/View/Index), case_release
#   Eigenstaendig(4): scrape_jobs (Index), support_sessions (Index),
#                     evidence_scan_cache (PK), forum_promotion (UNIQUE)
#   Nur Kommentare:   mentoring_notes (KEINE Spalte — verifiziert)
#
# INDEX-UMBENENNUNG: Die Namen 'scrape_jobs_user_idx' und
#   'case_events_user_time_idx' tragen 'user' im NAMEN; sie werden auf
#   '..._subject...' umbenannt (DROP + CREATE, Definition identisch bis auf
#   den bereits automatisch nachgezogenen Spaltennamen).
#
# AUDIT-BELEG (mc 2026-07-20): Zusaetzlich zum MIGRATION_APPLIED-Eintrag des
#   Runners haelt die Meta-Tabelle 'subject_key_meta' (analog
#   mat_subject_map_meta des Preppers) das Faktum "Schluesselraum dieser DB
#   ist subject_id (Schema-Version 1)" maschinenlesbar fest. Der prefix-Wert
#   wird hier BEWUSST NICHT dupliziert — Autoritaet dafuer ist
#   mat_subject_map_meta des Preppers (keine zwei Wahrheiten).
#
# NICHT BETROFFEN: Die versiegelten Paket-DBs evidence_/forensic_/
#   assets_<uid>.db (fuer Realnutzer gilt subject_id == user_id; Geister-
#   Pakete existieren noch nicht) sowie default.db/templates.db.
#
# IDEMPOTENZ: je Tabelle Spalten-Guard (nur umbenennen, wenn 'user_id' noch
#   existiert); Meta-Zeile INSERT OR IGNORE; Index-Umbenennung per Guard.
# KIND='destructive' (Schemaaenderung an datentragenden Tabellen) mit
#   precount/postcount/verify: Zeilensumme ueber alle 9 Tabellen vorher ==
#   nachher, Strukturpruefung, foreign_key_check leer.
#
# Beleg: claude_Einstieg_Bauplan_Migration_user_id_zu_subject_id_v0_1.md,
#        mc-Freigabe Weg A 2026-07-20 (dieser Chat).
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 19
NAME = "Schluesselumstellung user_id -> subject_id (Weg A, RENAME COLUMN)"
KIND = "destructive"

#: Reihenfolge: Anker zuerst (zieht die 4 REFERENCES-Klauseln automatisch
#: nach), dann die FK-Kinder (eigene Spalte), dann die eigenstaendigen Spalten.
_TABLES = (
    "cases",
    "case_events",
    "external_matters",
    "investigation_results",
    "case_release",
    "scrape_jobs",
    "support_sessions",
    "evidence_scan_cache",
    "forum_promotion",
)

#: FK-Kinder, deren REFERENCES cases(...) nach dem Rename auf subject_id
#: zeigen muss (Verifikation).
_FK_CHILDREN = ("case_events", "external_matters",
                "investigation_results", "case_release")

#: Index-UMBENENNUNGEN (alter Name -> neuer Name, DDL des neuen Index).
#: Die Spaltennamen in den DDLs sind bereits subject_id — der Rename der
#: Spalte ist zu diesem Zeitpunkt erfolgt.
_INDEX_RENAMES = (
    ("scrape_jobs_user_idx",
     "scrape_jobs_subject_idx",
     "CREATE INDEX IF NOT EXISTS scrape_jobs_subject_idx "
     "ON scrape_jobs(subject_id)"),
    ("case_events_user_time_idx",
     "case_events_subject_time_idx",
     "CREATE INDEX IF NOT EXISTS case_events_subject_time_idx "
     "ON case_events(subject_id, created_at)"),
)

#: Meta-Tabelle: maschinenlesbarer Beleg des Schluesselraums (s. Kopf).
_DDL_META = """
CREATE TABLE IF NOT EXISTS subject_key_meta (
    id             INTEGER PRIMARY KEY CHECK(id = 1),
    scheme         TEXT    NOT NULL,   -- 'prepper-subject-id'
    scheme_version INTEGER NOT NULL,   -- 1
    migrated_from  TEXT    NOT NULL,   -- 'user_id'
    applied_at     INTEGER NOT NULL
)
"""


#: Vorbestehende FK-Verletzungen je Tabelle, VOR den Renames gemessen (in
#: up() gesetzt). M019 darf nur an NEUEN Verletzungen scheitern — vorbestehende
#: sind nicht Werk dieser Migration, werden aber LAUT gemeldet (Grundregel 1:
#: nichts still uebergehen). Modul-Global, weil der Runner-Vertrag precount()
#: auf einen int festlegt; bei ROLLBACK ist der Wert bedeutungslos und wird
#: beim naechsten up() neu gemessen.
_PRE_FK_VIOLATIONS = {}


def _fk_violations(con: sqlite3.Connection, table: str) -> int:
    return len(con.execute("PRAGMA foreign_key_check(%s)" % table).fetchall())


def _cols(con: sqlite3.Connection, table: str) -> list:
    return [r[1] for r in con.execute("PRAGMA table_info(%s)" % table)]


def _index_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,)).fetchone() is not None


def precount(con: sqlite3.Connection) -> int:
    """Zeilensumme ueber alle 9 betroffenen Tabellen (Verlustfrei-Invariante)."""
    total = 0
    for t in _TABLES:
        total += int(con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0])
    return total


def up(con: sqlite3.Connection) -> None:
    # Vorbedingung Weg A: RENAME COLUMN muss abhaengige Schemaobjekte
    # nachziehen. Das tut SQLite nur bei legacy_alter_table=OFF (Default seit
    # 3.25). Ein ON waere ein stiller Korrektheitsverlust -> harter Abbruch.
    legacy = con.execute("PRAGMA legacy_alter_table").fetchone()[0]
    if int(legacy) != 0:
        raise RuntimeError(
            "M019: PRAGMA legacy_alter_table=%s — Weg A setzt 0 (OFF) voraus."
            % legacy)

    # FK-Bestandsaufnahme VOR den Renames: vorbestehende Verletzungen sind
    # nicht Werk dieser Migration — sie werden LAUT gemeldet und in verify()
    # nur als Vergleichsbasis benutzt (keine NEUEN Verletzungen zulaessig).
    _PRE_FK_VIOLATIONS.clear()
    for t in _TABLES:
        n = _fk_violations(con, t)
        _PRE_FK_VIOLATIONS[t] = n
        if n:
            logger.warning(
                "M019: foreign_key_check(%s) meldet BEREITS VOR der Migration "
                "%d Verletzung(en) — bitte gesondert aufklaeren.", t, n)

    for t in _TABLES:
        cols = _cols(con, t)
        if "subject_id" in cols and "user_id" not in cols:
            logger.info("M019: %s bereits subject_id — uebersprungen.", t)
            continue
        if "user_id" not in cols:
            # Weder user_id noch subject_id: Strukturbruch -> niemals still
            # uebergehen (Grundregel 1).
            raise RuntimeError(
                "M019: Tabelle '%s' hat weder user_id noch subject_id "
                "(Spalten: %s)." % (t, cols))
        con.execute(
            "ALTER TABLE %s RENAME COLUMN user_id TO subject_id" % t)
        logger.info("M019: %s.user_id -> subject_id umbenannt.", t)

    # Index-Umbenennung (Namen mit 'user' im Namen; Definition unveraendert).
    for old, new, ddl in _INDEX_RENAMES:
        if _index_exists(con, old):
            con.execute("DROP INDEX %s" % old)
        con.execute(ddl)
        logger.info("M019: Index %s -> %s.", old, new)

    # Meta-Beleg (einmalig; INSERT OR IGNORE haelt die Migration idempotent).
    con.execute(_DDL_META)
    con.execute(
        "INSERT OR IGNORE INTO subject_key_meta "
        "(id, scheme, scheme_version, migrated_from, applied_at) "
        "VALUES (1, 'prepper-subject-id', 1, 'user_id', ?)",
        (int(time.time()),))


def postcount(con: sqlite3.Connection) -> int:
    return precount(con)


def verify(con: sqlite3.Connection, before, after) -> None:
    # Invariante 1: Zeilensumme unveraendert (RENAME kopiert/loescht nichts).
    if before != after:
        raise RuntimeError(
            "M019 Invariante verletzt: Zeilensumme %r -> %r" % (before, after))

    # Invariante 2: alle 9 Tabellen tragen subject_id und KEIN user_id mehr.
    for t in _TABLES:
        cols = _cols(con, t)
        if "subject_id" not in cols or "user_id" in cols:
            raise RuntimeError(
                "M019: Tabelle '%s' nicht vollstaendig umgestellt "
                "(Spalten: %s)." % (t, cols))

    # Invariante 3: FK-Klauseln der 4 Kinder zeigen auf cases(subject_id).
    for t in _FK_CHILDREN:
        fks = [fk for fk in con.execute("PRAGMA foreign_key_list(%s)" % t)
               if fk[2] == "cases"]
        if not fks or not all(
                fk[3] == "subject_id" and fk[4] == "subject_id" for fk in fks):
            raise RuntimeError(
                "M019: FK %s -> cases nicht auf subject_id nachgezogen: %r"
                % (t, fks))

    # Invariante 4: m011-Trigger/View strukturell nachgezogen.
    for name in ("trg_investigation_results_no_update",
                 "v_investigation_current"):
        row = con.execute(
            "SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
        if row is None:
            raise RuntimeError("M019: Schemaobjekt '%s' fehlt." % name)
        sql = row[0]
        if "subject_id" not in sql or ".user_id" in sql:
            raise RuntimeError(
                "M019: '%s' referenziert noch user_id." % name)

    # Invariante 5: Index-Umbenennung vollzogen.
    for old, new, _ddl in _INDEX_RENAMES:
        if _index_exists(con, old) or not _index_exists(con, new):
            raise RuntimeError(
                "M019: Index-Umbenennung %s -> %s unvollstaendig." % (old, new))

    # Invariante 6: KEINE NEUEN FK-Verletzungen durch die Renames (vorbe-
    # stehende wurden in up() laut gemeldet und sind gesondert aufzuklaeren).
    for t in _TABLES:
        n = _fk_violations(con, t)
        pre = _PRE_FK_VIOLATIONS.get(t, 0)
        if n != pre:
            raise RuntimeError(
                "M019: foreign_key_check(%s): %d Verletzung(en) nach der "
                "Migration (vorher %d) — Rename hat Integritaet veraendert."
                % (t, n, pre))

    # Invariante 7: Meta-Beleg vorhanden.
    row = con.execute(
        "SELECT scheme, scheme_version, migrated_from FROM subject_key_meta "
        "WHERE id = 1").fetchone()
    if row is None or row[0] != "prepper-subject-id" or int(row[1]) != 1:
        raise RuntimeError("M019: subject_key_meta-Beleg fehlt/abweichend: %r"
                           % (row,))
