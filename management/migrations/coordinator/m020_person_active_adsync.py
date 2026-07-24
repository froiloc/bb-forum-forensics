# =============================================================================
# management/migrations/coordinator/m020_person_active_adsync.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Abgleich (Build 501)
# =============================================================================
# Zweck:
#   Fundament des AD-Abgleichs (Bauplan Build501_502 §4):
#     1. person.is_active (INTEGER NOT NULL DEFAULT 1) — der "Ruhestand"-
#        Schalter. Es gab bisher KEINEN solchen Mechanismus (Beleg: Volltext-
#        suche M001..M019/management/core/db am 2026-07-24 ohne Treffer;
#        mc 2026-07-24: "wir benoetigen eine Spalte is_active mit Default=1
#        plus Zeitstempel und Begruendung der Deaktivierung").
#     2. person.deactivated_at (INTEGER NULL) — Unix-Zeitstempel der
#        Deaktivierung; NULL == aktiv bzw. nie deaktiviert.
#     3. person.deactivated_reason (TEXT NULL) — Begruendung der Deaktivierung.
#     4. Seed der RBAC-Faehigkeit 'personnel.sync' (Muster M017: Schema +
#        Capability-Seed in einer Migration).
#
#   Entfernte Benutzer werden NIE geloescht (FK cases.assigned_to; Belege
#   duerfen nicht verwaisen — Entwurfsentscheidung person_repo.py) — nur
#   is_active=0. Rollen-Flags und person_role bleiben als historischer Beleg
#   unangetastet (mc 2026-07-24, E3).
#
# Verhaeltnis zum Katalog (m005-Prinzip):
#   Der Seed unten ist eine EINGEFRORENE Kopie des Eintrags in
#   management/rbac/catalog.py. NIE aus catalog.py importieren — eine bereits
#   angewandte Migration darf ihr Laufzeitverhalten nicht aendern.
#
# Produktivbetrieb (seit 2026-07-01):
#   Betrifft NUR coordinator.db (Ermittler speichern dort keine Ergebnisse;
#   Projektregeln: kein Erkenntnisverlust moeglich). Rein ADDITIV und
#   verlustfrei: drei neue Spalten mit Default/NULL, eine Capability-Zeile.
#   evidence_/forensic_/assets_<uid>.db bleiben unberuehrt.
#
# IDEMPOTENZ: Spalten-Guards via PRAGMA table_info + INSERT OR IGNORE.
# Version: v0.8.501 · Build: 501 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 20
NAME = "person.is_active/deactivated_at/deactivated_reason + Seed personnel.sync"
KIND = "additive"

#: Neue Spalten auf person: (Name, DDL-Fragment nach ADD COLUMN).
#  ALTER TABLE ... ADD COLUMN mit konstantem DEFAULT ist in SQLite zulaessig;
#  Bestandszeilen erhalten den Default (is_active=1 == aktiv) bzw. NULL.
_NEW_COLUMNS = (
    ("is_active", "is_active INTEGER NOT NULL DEFAULT 1"),
    ("deactivated_at", "deactivated_at INTEGER"),
    ("deactivated_reason", "deactivated_reason TEXT"),
)

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("personnel.sync", "AD-Abgleich durchfuehren",
     "Ermittlerstammdaten mit der Active-Directory-Gruppe abgleichen "
     "(Vorschau, Neuaufnahme, Namensaenderung, bestaetigte "
     "Deaktivierung/Reaktivierung — auditiert, nie Loeschen)."),
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _cols(con: sqlite3.Connection, table: str) -> list:
    return [r[1] for r in con.execute(
        "PRAGMA table_info(%s)" % table).fetchall()]


def _cap_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_capability WHERE code=?",
        (code,)).fetchone() is not None


def up(con: sqlite3.Connection) -> None:
    # Vorbedingungen: person (Basisschema/M005) und rbac_capability (M006).
    if not _table_exists(con, "person"):
        raise RuntimeError(
            "M020: Tabelle 'person' fehlt — Basisschema/M005 nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")
    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M020: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    have = set(_cols(con, "person"))
    done = (all(name in have for name, _ddl in _NEW_COLUMNS)
            and all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS))
    if done:
        logger.info("M020: person-Spalten + Seed bereits vorhanden — No-op.")
        return

    # Verlustfreiheits-Anker: Zeilenzahl vor den ALTERs (die Hooks
    # precount/verify des Runners laufen nur bei KIND='destructive' — diese
    # Migration ist additiv, also wird die Invariante HIER inline geprueft).
    n_before = int(con.execute("SELECT COUNT(*) FROM person").fetchone()[0])

    for name, ddl in _NEW_COLUMNS:
        if name not in have:
            con.execute("ALTER TABLE person ADD COLUMN %s" % ddl)

    now = int(time.time())
    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now),
        )

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    have_after = set(_cols(con, "person"))
    for name, _ddl in _NEW_COLUMNS:
        if name not in have_after:
            raise RuntimeError(
                "M020: Spalte person.%s fehlt nach up()." % name)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M020: Faehigkeit '%s' fehlt nach dem Seed." % code)
    # Kein NULL in is_active (NOT NULL DEFAULT 1 garantiert das; explizit
    # belegt, nicht still angenommen).
    bad = int(con.execute(
        "SELECT COUNT(*) FROM person WHERE is_active IS NULL").fetchone()[0])
    if bad:
        raise RuntimeError(
            "M020: %d person-Zeilen mit is_active IS NULL nach up()." % bad)
    # Verlustfreiheit: keine person-Zeile gewonnen oder verloren.
    n_after = int(con.execute("SELECT COUNT(*) FROM person").fetchone()[0])
    if n_before != n_after:
        raise RuntimeError(
            "M020: person-Zeilenzahl veraendert (%d -> %d) — Migration "
            "haette rein additiv sein muessen." % (n_before, n_after))

    logger.info("M020: person um is_active/deactivated_at/deactivated_reason "
                "erweitert; Faehigkeit %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
