#!/usr/bin/env python3
# =============================================================================
# management/migrate_templates_placeholders.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Platzhalter-Neuordnung (Build 489, Slice 1): placeholder_queries -> placeholders
# =============================================================================
# Zweck:
#   Ersetzt templates.db.placeholder_queries durch die einheitliche Tabelle
#   `placeholders`, die ALLE drei Platzhalter-Typen aufnimmt:
#     a = automatisch  ({{a:}}, SQL-Query gegen fdb, KEINE Validierung),
#     m = verpflichtend ({{m:}}, Ermittler-Eingabe, optionale Validierung),
#     o = optional      ({{o:}}, Ermittler-Eingabe, optionale Validierung).
#   Neue Spalten: type, default_value, validation (KLARTEXT UTF-8; Base64 nur
#   im Token-Transport — mc-Entscheid 2026-07-21 zu Bauplan §2.2),
#   validation_type ('regex' | 'list' [JSON-Array] | 'like').
#
#   Ablauf (EINE Transaktion, verlustfrei):
#     1. CREATE TABLE placeholders (+ Indizes).
#     2. Datenuebernahme aus placeholder_queries (alles Bestands-Queries -> type 'a').
#     3. DROP TABLE placeholder_queries (mc 2026-07-21: keine Rueckwaertskompatibilitaet
#        noetig, es existieren de facto noch keine Berichte).
#     4. templates_audit_log-Neubau: target_type-CHECK um 'placeholder' erweitert
#        (SQLite kann CHECKs nicht per ALTER aendern; Muster/Beleg:
#        migrate_templates_audit_check.py, Build 421). Historie 1:1.
#     5. Protokollzeile (action 'migrate', target_type 'placeholder').
#     6. Konsistenzpruefung: Zeilenzahlen, CHECK-Wortlaut, integrity_check.
#
#   Idempotent: existiert `placeholders` bereits und `placeholder_queries` nicht
#   mehr, ist der Lauf ein No-op (die Audit-CHECK-Erweiterung wird dennoch
#   sichergestellt). templates.db hat keinen Migrations-Runner — dieses Skript
#   ist, wie migrate_templates_audit_check.py, STANDALONE auszufuehren.
#
#   Sicherung: main() legt vor einem echten Lauf eine Dateikopie
#   <db>.pre489.bak an (--no-backup unterdrueckt das). Risikoklasse laut
#   Projektregeln niedrig (Ermittler speichern in templates.db keine
#   Ergebnisse), das Backup ist die Vorsichtsregel obendrauf.
#
# Aufruf:
#   python -m management.migrate_templates_placeholders [--templates-db PATH]
#          [--config ./config.yaml] [--no-backup] [--changed-by NAME]
#
# Journal: journal_mode=delete (Build 408/409 — kein WAL, netzlaufwerksicher).
#
# Beleg: Bauplan management/Bauplan_Platzhalter_DB_v0_1.md §3 (mc-Freigabe
# 2026-07-21, inkl. Entscheidungen §2.1-2.6).
# Version: v0.8.489 · Build: 489 · 2026-07-21
# =============================================================================

import argparse
import getpass
import os
import shutil
import sqlite3
import sys
import time
from typing import Any, Dict, Optional
from management.help import cli_epilog  # noqa: E402

# Kanonische DDL der neuen Tabelle. Die CHECKs erzwingen die mc-Regeln
# (Bauplan §3.1): a braucht sql_query und darf KEINE Validierung tragen;
# validation und validation_type treten nur paarweise auf; eine m/o-Default-
# Query muss genau EINEN Wert liefern (return_type 'scalar').
DDL_PLACEHOLDERS = """
CREATE TABLE placeholders (
    id              TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    type            TEXT NOT NULL CHECK (type IN ('a','m','o')),
    sql_query       TEXT,
    default_value   TEXT,
    validation      TEXT,
    validation_type TEXT CHECK (validation_type IN ('regex','list','like')),
    tags            TEXT,
    return_type     TEXT NOT NULL DEFAULT 'scalar'
                    CHECK (return_type IN ('scalar','list','table')),
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_by      TEXT NOT NULL,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    PRIMARY KEY (id),
    CHECK (type <> 'a' OR sql_query IS NOT NULL),
    CHECK (type <> 'a' OR validation IS NULL),
    CHECK ((validation IS NULL) = (validation_type IS NULL)),
    CHECK (type = 'a' OR sql_query IS NULL OR return_type = 'scalar')
)
"""

DDL_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ph_type_idx ON placeholders (type, is_active)",
    "CREATE INDEX IF NOT EXISTS ph_tags_idx ON placeholders (tags)",
)

# Datenuebernahme: jede Bestands-Query ist per Definition ein a-Platzhalter.
_COPY_SQL = (
    "INSERT INTO placeholders "
    "(id, title, description, type, sql_query, default_value, validation, "
    " validation_type, tags, return_type, is_active, created_by, created_at, "
    " updated_at) "
    "SELECT id, title, description, 'a', sql_query, NULL, NULL, NULL, tags, "
    "       return_type, is_active, created_by, created_at, updated_at "
    "FROM placeholder_queries"
)

# Audit-Neubau (Muster migrate_templates_audit_check.py): CHECK um
# 'placeholder' erweitert; alle bisherigen Werte bleiben gueltig.
_DDL_AUDIT_NEW = """
CREATE TABLE templates_audit_log__new (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT    NOT NULL,
    target_id   TEXT    NOT NULL,
    target_type TEXT    NOT NULL
                CHECK (target_type IN ('module', 'query', 'template',
                                       'placeholder')),
    changed_by  TEXT    NOT NULL,
    changed_at  INTEGER NOT NULL,
    old_value   TEXT,
    new_value   TEXT
)
"""

_AUDIT_COPY_SQL = (
    "INSERT INTO templates_audit_log__new "
    "(id, action, target_id, target_type, changed_by, changed_at, "
    " old_value, new_value) "
    "SELECT id, action, target_id, target_type, changed_by, changed_at, "
    "       old_value, new_value FROM templates_audit_log"
)


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _table_ddl(con: sqlite3.Connection, table: str) -> Optional[str]:
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row is not None else None


def _widen_audit_check(con: sqlite3.Connection) -> bool:
    """Erweitert die target_type-CHECK um 'placeholder' (Rebuild). Muss in
    einer bereits offenen Transaktion laufen. Gibt True zurueck, wenn ein
    Rebuild stattfand (False = bereits erweitert)."""
    ddl = _table_ddl(con, "templates_audit_log")
    if ddl is None:
        raise SystemExit(
            "[migrate-placeholders] Tabelle 'templates_audit_log' fehlt — ist "
            "das die richtige templates.db?")
    # Idempotenz-Sonde: der QUOTIERTE Skalarwert 'placeholder' steht nur in
    # der erweiterten CHECK (analog migrate_templates_audit_check.py).
    if "'placeholder'" in ddl:
        return False
    con.execute("DROP TABLE IF EXISTS templates_audit_log__new")
    con.execute(_DDL_AUDIT_NEW)
    con.execute(_AUDIT_COPY_SQL)
    con.execute("DROP TABLE templates_audit_log")
    con.execute(
        "ALTER TABLE templates_audit_log__new RENAME TO templates_audit_log")
    return True


def apply_migration(con: sqlite3.Connection,
                    changed_by: str = "migrate_templates_placeholders",
                    *, ts: Optional[int] = None) -> Dict[str, Any]:
    """
    Wendet die Neuordnung idempotent auf eine offene templates.db-Verbindung an.

    Returns:
        {migrated, already_migrated, carried_rows, audit_widened}
    """
    has_new = _table_exists(con, "placeholders")
    has_old = _table_exists(con, "placeholder_queries")
    now = int(ts if ts is not None else time.time())

    con.isolation_level = None
    con.execute("PRAGMA journal_mode=delete")
    con.execute("PRAGMA foreign_keys=OFF")

    if has_new and not has_old:
        # Bereits migriert. Die Audit-CHECK dennoch sicherstellen (falls ein
        # aelterer Teil-Lauf sie nicht erweitert haette) — idempotent.
        con.execute("BEGIN IMMEDIATE")
        try:
            widened = _widen_audit_check(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        return {"migrated": False, "already_migrated": True,
                "carried_rows": 0, "audit_widened": widened}

    if not has_old:
        raise SystemExit(
            "[migrate-placeholders] Weder 'placeholders' noch "
            "'placeholder_queries' vorhanden — ist das die richtige "
            "templates.db?")

    old_count = con.execute(
        "SELECT COUNT(*) FROM placeholder_queries").fetchone()[0]
    audit_before = con.execute(
        "SELECT COUNT(*) FROM templates_audit_log").fetchone()[0] \
        if _table_exists(con, "templates_audit_log") else None

    con.execute("BEGIN IMMEDIATE")
    try:
        # 1) Neue Tabelle + Datenuebernahme. (Ein frueherer ABGEBROCHENER Lauf
        #    kann keine halbe placeholders-Tabelle hinterlassen — Transaktion.)
        if has_new:
            # Defensive: beide Tabellen vorhanden -> ein aelterer Lauf wurde
            # nicht sauber abgeschlossen. Kein stilles Raten (Grundregel 1).
            raise SystemExit(
                "[migrate-placeholders] 'placeholders' UND 'placeholder_queries' "
                "existieren gleichzeitig — Zustand bitte manuell pruefen.")
        con.execute(DDL_PLACEHOLDERS)
        for ddl in DDL_INDEXES:
            con.execute(ddl)
        con.execute(_COPY_SQL)
        new_count = con.execute(
            "SELECT COUNT(*) FROM placeholders").fetchone()[0]
        if new_count != old_count:
            raise RuntimeError(
                "[migrate-placeholders] Zeilenzahl weicht ab: %d (alt) vs. %d "
                "(neu) — Abbruch, Rollback." % (old_count, new_count))

        # 2) Alte Tabelle + ihre Indizes entfernen.
        con.execute("DROP INDEX IF EXISTS pq_tags_idx")
        con.execute("DROP INDEX IF EXISTS pq_active_idx")
        con.execute("DROP TABLE placeholder_queries")

        # 3) Audit-CHECK erweitern (VOR der Protokollzeile, die den neuen
        #    target_type 'placeholder' nutzt).
        audit_widened = _widen_audit_check(con)

        # 4) Protokollzeile der Migration (Beleg im templates_audit_log).
        con.execute(
            "INSERT INTO templates_audit_log "
            "(action, target_id, target_type, changed_by, changed_at, "
            " old_value, new_value) "
            "VALUES ('migrate', 'placeholders', 'placeholder', ?, ?, "
            "        'placeholder_queries', 'placeholders (a/m/o + validation)')",
            (changed_by, now))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    # 5) Inline-Verifikation NACH dem Commit (Grundregel: Ueberpruefbarkeit).
    #    Whitespace-toleranter Vergleich gegen die kompaktierte Ziel-DDL.
    compact = (_table_ddl(con, "placeholders") or "").replace(" ", "") \
        .replace("\n", "")
    for probe in ("'a','m','o'", "validation_type", "'regex','list','like'"):
        if probe.replace(" ", "") not in compact:
            raise RuntimeError(
                "[migrate-placeholders] Ziel-DDL unvollstaendig: '%s' fehlt."
                % probe)
    if audit_before is not None:
        audit_after = con.execute(
            "SELECT COUNT(*) FROM templates_audit_log").fetchone()[0]
        if audit_after != audit_before + 1:
            raise RuntimeError(
                "[migrate-placeholders] Audit-Historie unvollstaendig: %s -> %s."
                % (audit_before, audit_after))
    integ = con.execute("PRAGMA integrity_check").fetchone()[0]
    if integ != "ok":
        raise RuntimeError(
            "[migrate-placeholders] integrity_check: %s" % integ)

    return {"migrated": True, "already_migrated": False,
            "carried_rows": old_count, "audit_widened": audit_widened}


def _resolve_db_path(args) -> str:
    if args.templates_db:
        return args.templates_db
    try:
        from core.config_loader import ConfigLoader  # lazy, optional
        cfg = ConfigLoader(args.config)
        path = cfg.get("paths.templates_db")
        if path:
            return path
    except Exception:
        pass
    raise SystemExit(
        "[migrate-placeholders] Kein templates.db-Pfad: --templates-db angeben "
        "oder paths.templates_db in config.yaml setzen.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ersetzt placeholder_queries durch die einheitliche "
                    "Tabelle placeholders (a/m/o + Validierung); idempotent, "
                    "verlustfrei, mit Backup.",
        epilog=cli_epilog.epilog("migrate_templates_placeholders"),
        formatter_class=cli_epilog.HilfeFormat)
    parser.add_argument("--templates-db", help="Pfad zur templates.db")
    parser.add_argument("--config", default="./config.yaml",
                        help="config.yaml (Fallback fuer den Pfad)")
    parser.add_argument("--no-backup", action="store_true",
                        help="keine .pre489.bak-Kopie anlegen")
    parser.add_argument("--changed-by",
                        default=None, help="Urheber-Kennung fuer die "
                        "Audit-Protokollzeile (Default: OS-Benutzer)")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not os.path.exists(db_path):
        print("[migrate-placeholders] templates.db nicht gefunden: %s"
              % db_path, file=sys.stderr)
        return 2

    changed_by = args.changed_by or getpass.getuser()

    # Backup nur, wenn wirklich migriert wird (kein Backup-Muell bei No-ops).
    probe = sqlite3.connect(db_path)
    try:
        will_migrate = (_table_exists(probe, "placeholder_queries")
                        and not _table_exists(probe, "placeholders"))
    finally:
        probe.close()
    if will_migrate and not args.no_backup:
        bak = db_path + ".pre489.bak"
        shutil.copy2(db_path, bak)
        print("[migrate-placeholders] Backup: %s" % bak)

    con = sqlite3.connect(db_path)
    try:
        res = apply_migration(con, changed_by=changed_by)
    finally:
        con.close()

    if res["already_migrated"]:
        print("[migrate-placeholders] bereits migriert — No-op"
              + (" (Audit-CHECK nachgezogen)." if res["audit_widened"]
                 else "."))
    else:
        print("[migrate-placeholders] fertig: %d Query-Definitionen als "
              "Typ 'a' uebernommen, placeholder_queries entfernt, Audit-CHECK "
              "%s." % (res["carried_rows"],
                       "erweitert" if res["audit_widened"]
                       else "war bereits erweitert"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
