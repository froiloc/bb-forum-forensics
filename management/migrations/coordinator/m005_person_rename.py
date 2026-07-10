# =============================================================================
# management/migrations/coordinator/m005_person_rename.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M005 — coordinator.db
#   Benennt die Ermittlerstammdaten-Tabelle 'investigators' verlustfrei nach
#   'person' um. Rein mechanisch: keine Zeile, keine Spalte, kein Wert geht
#   verloren. Grund (Beleg: Bauplan B7 v1.1 §11.1, Welle 0): die Rollen laufen
#   auseinander (admin/lector/searchagent), 'investigators' ist semantisch zu
#   eng. Der RBAC-Aufbau (person_role/rbac_*) folgt in einem SEPARATEN Build —
#   diese Migration enthaelt davon bewusst NICHTS.
#
# FK-Nachzug (der Kern des Ganzen):
#   In SQLite mit legacy_alter_table=OFF zieht 'ALTER TABLE ... RENAME TO' die
#   Fremdschluessel-Referenzen in ALLEN anderen Tabellen automatisch nach —
#   sowohl benannte Klauseln (FOREIGN KEY(...) REFERENCES person(id)) als auch
#   Inline-Spalten-FKs (... REFERENCES person(id)). Betroffen sind:
#       cases.assigned_to              (M002)
#       support_sessions.supporter_id  (M003)
#       case_events.created_by         (M004)
#       scrape_jobs.assigned_to        (Bootstrap, falls vorhanden)
#       pending_cross_annotations.source_iid (Bootstrap, falls vorhanden)
#   Empirisch verifiziert auf dev SQLite 3.45.1 (0 foreign_key_check-Verstoesse,
#   Zeilen erhalten). Fuer Prod-Determinismus (Python 3.14, abweichender SQLite-
#   Build) setzt up() legacy_alter_table=OFF EXPLIZIT vor dem Rename — dann gilt
#   der Nachzug unabhaengig vom Build-Default (der ohnehin seit SQLite 3.25.0
#   OFF ist).
#
#   WICHTIG: Die bereits angewandten Migrationen M002-M004 werden NICHT editiert
#   (Checksum-Drift + Rewrite angewandter Historie waere forensisch unzulaessig).
#   Ihr 'REFERENCES investigators(id)' wird ausschliesslich durch den Live-
#   Nachzug DIESER Migration zu 'person' — genau wie im Empirie-Test.
#
# Idempotenz / Frisch-Schema:
#   Fehlt 'investigators' und existiert bereits 'person' (Rename schon erfolgt
#   oder Frisch-Schema, das direkt 'person' anlegt), ist up() ein sauberer
#   No-Op mit INFO-Log — KEIN Hard-Fail, aber auch KEIN stiller Durchgang
#   (Grundregel 1). Fehlt 'investigators' UND 'person', wird ebenfalls sauber
#   uebersprungen und geloggt (dieser Pfad — coordinator.db rein aus m001-m005
#   ohne vorherigen Bootstrap — war schon vor Build 342 unvollstaendig, da keine
#   Migration 'investigators' je erzeugt; offener Punkt fuer den Bootstrap-Build).
#
# KIND='additive' -> ehrliches Label (kein Zeilen-/Spaltenverlust). Der Runner
#   ruft daher weder precount/postcount noch verify auf; die Invariantenpruefung
#   erfolgt INLINE in up() mit 'raise' bei Verstoss -> ROLLBACK (der Runner
#   umschliesst up() mit BEGIN IMMEDIATE/COMMIT und ROLLBACK bei Exception),
#   also kein Teilzustand.
#
# coordinator.db unterliegt keinem Migrations-Lock (kein Beweismittel);
# migrate.py-Lauf beim Deploy ist dennoch ZWINGEND (Schemaaenderung).
#
# Beleg: Bauplan_Baustelle7_Management_v1_1.md §11.1/§11.7,
#        UEBERGABE_BAUSTELLE_7_Welle0_ff.md §3, mc 2026-07-10.
# Version: v0.7.342 · Build: 342 · 2026-07-10
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 5
NAME = "investigators -> person (Rename, FK-Nachzug)"
KIND = "additive"


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _row_count(con: sqlite3.Connection, table: str) -> int:
    return int(con.execute("SELECT COUNT(*) FROM %s" % table).fetchone()[0])


# Tabellen mit FK-Referenz auf die umzubenennende Tabelle. Nur die, die
# tatsaechlich existieren, werden nach dem Rename per foreign_key_check geprueft.
_FK_DEPENDENTS = (
    "audit_log",
    "cases",
    "support_sessions",
    "case_events",
    "scrape_jobs",
    "pending_cross_annotations",
)


def up(con: sqlite3.Connection) -> None:
    # (a) FK-Nachzug deterministisch erzwingen (unabhaengig vom Build-Default).
    con.execute("PRAGMA legacy_alter_table=OFF")

    has_old = _table_exists(con, "investigators")
    has_new = _table_exists(con, "person")

    # (b) Idempotenz-/Frisch-Schema-Guard.
    if not has_old:
        if has_new:
            logger.info(
                "M005: 'investigators' nicht vorhanden, 'person' existiert "
                "bereits -> Rename schon erfolgt oder Frisch-Schema; No-Op."
            )
        else:
            logger.info(
                "M005: weder 'investigators' noch 'person' vorhanden -> kein "
                "Bootstrap gelaufen; No-Op (offener Punkt: Bootstrap-Build)."
            )
        return

    if has_new:
        # 'investigators' UND 'person' existieren gleichzeitig: unerwarteter,
        # mehrdeutiger Zustand -> hart abbrechen (kein stilles Weitermachen).
        raise RuntimeError(
            "M005: 'investigators' UND 'person' existieren gleichzeitig — "
            "mehrdeutiger Zustand, manuelle Klaerung erforderlich."
        )

    # Zeilenzahl VOR dem Rename fuer die Invariantenpruefung sichern.
    before = _row_count(con, "investigators")

    # (c) Der eigentliche, verlustfreie Rename (FK-Nachzug inklusive).
    con.execute("ALTER TABLE investigators RENAME TO person")

    # (d) Inline-Verifikation — bei Verstoss 'raise' -> ROLLBACK im Runner.
    if not _table_exists(con, "person"):
        raise RuntimeError("M005: 'person' nach RENAME nicht vorhanden.")
    if _table_exists(con, "investigators"):
        raise RuntimeError("M005: 'investigators' nach RENAME noch vorhanden.")

    after = _row_count(con, "person")
    if before != after:
        raise RuntimeError(
            "M005: Zeilenzahl-Invariante verletzt: investigators=%d -> person=%d"
            % (before, after)
        )

    # FK-Integritaet aller abhaengigen (existierenden) Tabellen pruefen.
    for table in _FK_DEPENDENTS:
        if not _table_exists(con, table):
            continue
        violations = con.execute(
            "PRAGMA foreign_key_check(%s)" % table
        ).fetchall()
        if violations:
            raise RuntimeError(
                "M005: foreign_key_check(%s) meldet %d Verletzung(en) nach "
                "Rename." % (table, len(violations))
            )

    logger.info(
        "M005: 'investigators' -> 'person' umbenannt (%d Zeilen, FK-Nachzug ok).",
        after,
    )
