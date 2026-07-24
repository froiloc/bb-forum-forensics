# =============================================================================
# management/migrations/coordinator/m025_subject_merge.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Migration M025 — coordinator.db (ADDITIV)
#   Legt 'subject_merge' an (Build 509, AP-2A, Idee 11): das UMKEHRBARE,
#   auditierte Zusammenfuehren und Trennen von Identitaeten.
#
# DER ERMITTLUNGSFALL:
#   "Konto 4711 und Konto 90210 werden von DERSELBEN natuerlichen Person
#   betrieben" — Zweitkonto, Wiederanmeldung nach Sperre, Geist + Realkonto.
#   Das ist der Kern des Projektziels ("Forenkonten natuerlichen Personen
#   zuordnen").
#
# WARUM UMKEHRBAR: Die Zusammenfuehrung ist eine HYPOTHESE, keine Tatsache. Sie
#   stuetzt sich auf Indizien (Schreibstil, IP, Zeitmuster, Alias-
#   Ueberschneidung). Erweist sie sich als falsch, muss die TRENNUNG so belegt
#   sein wie die Zusammenfuehrung — und beide Konten muessen danach wieder fuer
#   sich stehen, ohne dass eine Erkenntnis verloren geht.
#
# FESTLEGUNGEN (Bauplan A3 Par. 2.1/2.2):
#   (E1) FLACHE ZWEIEBENEN-STRUKTUR: eine Zeile verbindet ein PRIMAER-Konto mit
#        einem EINGEGLIEDERTEN Konto. KETTEN (A<-B, B<-C) sind verboten — die
#        Pruefung liegt im Repo (sie braucht Abfragen, die eine CHECK-Klausel
#        nicht leisten kann). Begruendung: Ketten machen die Umkehrung
#        MEHRDEUTIG — loest man B->A auf, wohin gehoert dann C? Ein Werkzeug,
#        das diese Frage nicht eindeutig beantwortet, erzeugt in einem
#        Strafverfahren angreifbare Aussagen. Die flache Struktur ist eindeutig,
#        in einem Blick pruefbar und deckt den realen Bedarf ("n Konten, eine
#        Person") vollstaendig ab.
#   (E2) TRENNUNG IST EIN SOFT-WIDERRUF, kein DELETE: is_active=0 +
#        Pflicht-Grund + Zeitpunkt + eigener Beleg. Die Historie "wir hielten
#        das mal fuer dieselbe Person, und hier steht, warum wir es nicht mehr
#        tun" ist SELBST ein Ermittlungsergebnis.
#   (E3) CHECK(primary_subject_id <> merged_subject_id) auf DDL-Ebene:
#        Selbstverschmelzung ist damit auch bei einem Programmierfehler
#        unmoeglich. Der partielle UNIQUE-Index stellt sicher, dass ein Konto
#        zu einer Zeit HOECHSTENS EINMAL eingegliedert ist.
#   (E4) KONFIDENZ-ACHSE WIEDERVERWENDET (verdacht/wahrscheinlich/gesichert,
#        Ordinal 10/20/30, eingefroren) — dieselbe Skala wie identified_subject
#        (M018). Eine Zusammenfuehrung ist genauso eine Erkenntnis mit
#        Reifegrad wie eine Identifizierung; zwei verschiedene Skalen waeren
#        eine Fehlerquelle.
#   (E5) KEIN RBAC-SEED: 'crossref.view'/'crossref.edit' (M018) werden
#        wiederverwendet; der Faehigkeitskatalog bleibt bei 33.
#
# SENSIBILITAET: 'basis' und 'split_reason' sind Freitexte und stehen nie im
#   audit_log-Payload — dort nur Fakten + Textlaengen (Regel wie M018).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + Guard. KIND='additive'.
# MIGRATIONSKLASSE: rein additiv, NUR coordinator.db, neue Tabelle —
#   Ermittler-Ergebnisdaten unberuehrt, Migrationsvorbehalt greift nicht.
#
# Beleg: mc 2026-07-24 (Auftrag "A1 bis A4"); Bauplan
#   claude_Bauplan_A3_MergeSplit_v0_1.md.
# Version: v0.8.509 · Build: 509 · 2026-07-24
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 25
NAME = "Identitaets-Merge/Split (subject_merge)"
KIND = "additive"


_DDL_SUBJECT_MERGE = """
CREATE TABLE IF NOT EXISTS subject_merge (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    primary_subject_id INTEGER NOT NULL,   -- fuehrendes Konto
    merged_subject_id  INTEGER NOT NULL,   -- eingegliedertes Konto
    basis              TEXT    NOT NULL,   -- Indizien (SENSIBEL)
    confidence_code    TEXT    NOT NULL
                       CHECK(confidence_code IN
                             ('verdacht','wahrscheinlich','gesichert')),
    confidence_ordinal INTEGER NOT NULL,   -- eingefroren 10/20/30
    is_active          INTEGER NOT NULL DEFAULT 1
                       CHECK(is_active IN (0, 1)),
    split_reason       TEXT,               -- Grund der Trennung (SENSIBEL)
    merged_by          INTEGER REFERENCES person(id),
    split_by           INTEGER REFERENCES person(id),
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL,
    split_at           INTEGER,
    audit_seq          INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq  INTEGER NOT NULL REFERENCES audit_log(seq),
    CHECK(primary_subject_id <> merged_subject_id)
)
"""

# Die Fachregel "ein Konto ist zu einer Zeit hoechstens EINMAL eingegliedert".
# Partiell (nur is_active=1), damit eine getrennte Zeile als Beleg stehen
# bleibt und dasselbe Konto spaeter erneut zugeordnet werden darf.
_IDX_UNIQUE_ACTIVE = (
    "ux_subject_merge_active",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_subject_merge_active "
    "ON subject_merge (merged_subject_id) WHERE is_active = 1",
)
# Kernabfrage: "welche Konten haengen an diesem Primaerkonto?"
_IDX_PRIMARY = (
    "ix_subject_merge_primary",
    "CREATE INDEX IF NOT EXISTS ix_subject_merge_primary "
    "ON subject_merge (primary_subject_id)",
)

_INDICES = (_IDX_UNIQUE_ACTIVE, _IDX_PRIMARY)
_TABLES = ("subject_merge",)


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
        logger.info("M025: subject_merge bereits vorhanden — No-op.")
        return

    con.execute(_DDL_SUBJECT_MERGE)
    for _name, ddl in _INDICES:
        con.execute(ddl)

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    for t in _TABLES:
        if not _table_exists(con, t):
            raise RuntimeError("M025: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M025: Index '%s' fehlt nach up()." % ix)

    logger.info("M025: subject_merge + %d Indizes angelegt (kein RBAC-Seed — "
                "crossref.view/edit aus M018 wiederverwendet).", len(_INDICES))
