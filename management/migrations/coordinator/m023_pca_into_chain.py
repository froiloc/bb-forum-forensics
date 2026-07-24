# =============================================================================
# management/migrations/coordinator/m023_pca_into_chain.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Querfunde (AP-2A)
# =============================================================================
# Migration M023 — coordinator.db (ADDITIV)
#   GOVERNANCE-PUNKT A4 (Build 506): 'pending_cross_annotations' in die
#   MIGRATIONSKETTE ueberfuehren und den Schluessel auf 'subject_id' angleichen.
#
# DAS PROBLEM (belegt):
#   Die Tabelle wird bisher ZUR LAUFZEIT von db/coordinator_db.py angelegt
#   (add_pending_cross_annotation -> executescript "CREATE TABLE IF NOT
#   EXISTS ...", Z. 408-421) — eine Notloesung aus Build 185 gegen Bug 2.78
#   ("coordinator.db verfuegbar, aber pending_cross_annotations-Eintrag fehlte
#   lautlos"). Sie steht damit AUSSERHALB der Kette: keine geprueft-versionierte
#   DDL, kein Pruefsummen-Eintrag in schema_migrations, in keiner
#   Migrationsuebersicht sichtbar. Fuer ein forensisches Werkzeug ist das ein
#   Beleg-Loch — der Zustand der Datenbank ist nicht vollstaendig aus der Kette
#   rekonstruierbar. Als "eigener spaeterer Governance-Punkt" vermerkt in
#   Bauplan Build 474 Par. 3 und Bauplan Build 478 Par. 5.
#
# WAS DIESE MIGRATION TUT
#   1. Kanonische DDL in die Kette holen (CREATE TABLE/INDEX IF NOT EXISTS,
#      ZEICHENGENAU wie die Laufzeit-DDL). Existiert die Tabelle bereits
#      (Regelfall im Produktivbetrieb), ist das ein No-op — BESTEHENDE ZEILEN
#      WERDEN NICHT ANGEFASST.
#   2. 'subject_id' angleichen — als VIRTUELL GENERIERTE Spalte auf
#      'target_uid', plus Index.
#
# WARUM EINE GENERIERTE SPALTE (Entwurfsentscheidung, zur Abnahme):
#   (a) 'target_uid' UMBENENNEN haette den LAUFENDEN Schreibpfad in
#       db/coordinator_db.py und den cross_annotation_integrator gebrochen —
#       also die produktive Querfund-Pipeline. Hoechstes Risiko, kein
#       Zusatznutzen. VERWORFEN.
#   (b) ECHTE Spalte + Backfill + Schreibpfad ergaenzen: jede Zeile, die ein
#       alter Binaerstand schriebe, haette 'subject_id IS NULL' -> stille
#       Divergenz zwischen zwei Spalten, die dasselbe bedeuten sollen. Genau
#       die Art Loch, die Grundregel 1 verbietet. VERWORFEN.
#   (c) VIRTUAL GENERATED 'subject_id AS (target_uid)': KANN NICHT DIVERGIEREN
#       (SQLite berechnet den Wert bei jedem Lesen), braucht KEINEN Backfill,
#       KEINE Aenderung am produktiven Schreibpfad, ist indizierbar und rein
#       additiv. Der physisch geschriebene Name bleibt 'target_uid', der
#       kanonische LESEname ist 'subject_id'. GEWAEHLT.
#   Eine spaetere Konsolidierung von 'target_uid' bleibt moeglich, wenn die
#   Pipeline ohnehin angefasst wird; der Beleg-Charakter ist mit (c) aber schon
#   jetzt hergestellt — das war das Ziel dieses Punktes.
#
# MINDESTVERSION SQLITE 3.31 (2020): generierte Spalten. Ist das SQLite aelter,
#   scheitert diese Migration LAUT mit sprechender Meldung (und der Runner rollt
#   zurueck) — statt still ohne die Spalte durchzulaufen und spaeteren Lesern
#   ein 'no such column: subject_id' zu bescheren.
#
# IDEMPOTENZ: CREATE ... IF NOT EXISTS + Spalten-Guard ueber PRAGMA
#   table_xinfo (WICHTIG: PRAGMA table_info LISTET GENERIERTE SPALTEN NICHT —
#   mit table_info haette der Guard die Spalte nie gefunden und die Migration
#   waere beim zweiten Lauf an einem doppelten ALTER TABLE gescheitert).
#
# MIGRATIONSKLASSE: additiv, NUR coordinator.db. Es wird KEINE Zeile
#   geschrieben, geaendert oder geloescht; die neue Spalte ist virtuell und
#   belegt keinen Speicher. Ermittler-Ergebnisdaten unberuehrt. Rueckbau waere
#   DROP INDEX + ALTER TABLE DROP COLUMN — verlustfrei, weil die Spalte keinen
#   eigenen Inhalt traegt.
#
# Beleg: mc 2026-07-24 (Auftrag "A1 bis A4"); Bauplan
#   claude_Bauplan_A4_Governance_PCA_v0_1.md.
# Version: v0.8.506 · Build: 506 · 2026-07-24
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 23
NAME = ("pending_cross_annotations in die Migrationskette + subject_id "
        "(generiert)")
KIND = "additive"

#: Kleinste SQLite-Version mit generierten Spalten.
_MIN_SQLITE = (3, 31, 0)

# ZEICHENGENAUE Kopie der Laufzeit-DDL aus db/coordinator_db.py (Build 185).
# Sie ist ab jetzt hier KANONISCH; die Laufzeit-Variante bleibt als Absicherung
# gegen Bug 2.78 bestehen und verweist im Kommentar auf diese Migration.
_DDL_PCA = """
CREATE TABLE IF NOT EXISTS pending_cross_annotations (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    source_iid           INTEGER NOT NULL,
    target_uid           INTEGER NOT NULL,
    db_path              TEXT    NOT NULL,
    annotation_local_id  TEXT    NOT NULL,
    created_at           INTEGER NOT NULL,
    integrated_at        INTEGER DEFAULT NULL
)
"""

# Der partielle Index der Laufzeit-DDL (offene Transportnotizen je Ziel).
_DDL_IDX_LEGACY = """
CREATE INDEX IF NOT EXISTS pca_target_uid_idx
    ON pending_cross_annotations (target_uid)
    WHERE integrated_at IS NULL
"""

_ALTER_SUBJECT_ID = (
    "ALTER TABLE pending_cross_annotations "
    "ADD COLUMN subject_id INTEGER GENERATED ALWAYS AS (target_uid) VIRTUAL"
)

_DDL_IDX_SUBJECT = (
    "CREATE INDEX IF NOT EXISTS ix_pca_subject_id "
    "ON pending_cross_annotations (subject_id)"
)

_TABLE = "pending_cross_annotations"
_INDICES = ("pca_target_uid_idx", "ix_pca_subject_id")


def _sqlite_version_tuple() -> tuple:
    return tuple(int(p) for p in sqlite3.sqlite_version.split(".")[:3])


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _index_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,)).fetchone() is not None


def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    """
    Spalten-Guard ueber PRAGMA table_xinfo. table_info WUERDE GENERIERTE
    SPALTEN VERSCHWEIGEN — dieser Unterschied ist der Grund, warum hier
    ausdruecklich table_xinfo steht (verifiziert SQLite 3.45.1, 2026-07-24).
    """
    rows = con.execute("PRAGMA table_xinfo(%s)" % table).fetchall()
    return any(str(r[1]) == column for r in rows)


def _row_count(con: sqlite3.Connection) -> int:
    if not _table_exists(con, _TABLE):
        return 0
    return int(con.execute("SELECT COUNT(*) FROM %s" % _TABLE).fetchone()[0])


def up(con: sqlite3.Connection) -> None:
    if _sqlite_version_tuple() < _MIN_SQLITE:
        raise RuntimeError(
            "M023: SQLite %s ist zu alt — generierte Spalten brauchen "
            "mindestens %s. Die Migration bricht bewusst LAUT ab, statt die "
            "Spalte 'subject_id' still auszulassen."
            % (sqlite3.sqlite_version,
               ".".join(str(p) for p in _MIN_SQLITE)))

    already = (_table_exists(con, _TABLE)
               and all(_index_exists(con, ix) for ix in _INDICES)
               and _column_exists(con, _TABLE, "subject_id"))
    if already:
        logger.info("M023: pending_cross_annotations bereits in der Kette "
                    "(Tabelle, Indizes, subject_id vorhanden) — No-op.")
        return

    # ZEILENZAHL-INVARIANTE (Muster M020): vorher merken, hinterher belegen.
    # Diese Migration darf KEINE Zeile anfassen — im Produktivbetrieb liegen
    # hier echte, noch nicht integrierte Querfunde.
    rows_before = _row_count(con)

    con.execute(_DDL_PCA)
    con.execute(_DDL_IDX_LEGACY)

    if not _column_exists(con, _TABLE, "subject_id"):
        con.execute(_ALTER_SUBJECT_ID)
    con.execute(_DDL_IDX_SUBJECT)

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    if not _table_exists(con, _TABLE):
        raise RuntimeError("M023: Tabelle '%s' fehlt nach up()." % _TABLE)
    for ix in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M023: Index '%s' fehlt nach up()." % ix)
    if not _column_exists(con, _TABLE, "subject_id"):
        raise RuntimeError(
            "M023: generierte Spalte 'subject_id' fehlt nach up().")

    rows_after = _row_count(con)
    if rows_after != rows_before:
        raise RuntimeError(
            "M023: Zeilenzahl-Invariante verletzt (%d -> %d). Diese Migration "
            "darf keine Zeile anfassen." % (rows_before, rows_after))

    # Der eigentliche fachliche Beweis: subject_id deckt sich fuer JEDE Zeile
    # mit target_uid. Bei einer generierten Spalte kann das gar nicht anders
    # sein — geprueft wird es trotzdem, weil eine Annahme, die nie geprueft
    # wird, in einem Beweismittel nichts verloren hat.
    mismatch = con.execute(
        "SELECT COUNT(*) FROM %s WHERE subject_id IS NOT target_uid" % _TABLE
    ).fetchone()[0]
    if int(mismatch) != 0:
        raise RuntimeError(
            "M023: %s Zeilen mit subject_id != target_uid — die Angleichung "
            "ist nicht verlustfrei." % mismatch)

    logger.info("M023: pending_cross_annotations in der Kette; subject_id "
                "(generiert) + Index angelegt; %d Zeilen unveraendert.",
                rows_after)
