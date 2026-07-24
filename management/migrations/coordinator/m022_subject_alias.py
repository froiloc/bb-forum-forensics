# =============================================================================
# management/migrations/coordinator/m022_subject_alias.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Migration M022 — coordinator.db (ADDITIV)
#   Legt den GLOBALEN ALIAS-KATALOG 'subject_alias' an (Build 504, Welle 2,
#   AP-2A, Idee 8): die fallUEBERGREIFENDE Erkenntnis "Forenkonto <subject_id>
#   tritt AUSSERDEM unter dem Namen <alias> auf".
#
# ABGRENZUNG (belegte Reconciliation, mc 2026-07-24 — kein Duplizieren):
#   - forensic_api/aliases.py ist der FALLBEZOGENE Ermittler-SUCHBEGRIFF
#     ("Panther") in der evidence_<uid>.db (Baustelle 3, Build 179). Das ist
#     eine Arbeitshilfe, KEIN Katalog ueber Forennutzer.
#   - identified_subject (M018) haelt "Konto -> REALE PERSON" (eine Zeile je
#     Konto, hoechste PII-Stufe).
#   - DIESE Tabelle haelt "Konto -> WEITERER FORENNAME" (n Zeilen je Konto,
#     Forenwelt). Zwei getrennte Erkenntnisarten; eine Vermischung haette die
#     Konfidenz-Achse von M018 verwaessert.
#
# SCHLUESSEL subject_id: Forennutzer-Schluessel NACH PREPPER-SCHEMA (Realnutzer:
#   subject_id == users.id; Geist: subject_id == prefix + mat_usernames.id;
#   Beleg: Entscheidung SubjectID/Geisternutzer 2026-07-20, global vollzogen mit
#   M019). BEWUSST KEIN FK auf cases — der Katalog ist global und erfasst auch
#   Geister, fuer die (noch) kein Fallpaket existiert; ein FK schloesse > 550k
#   Namen aus (Grundregel-1-Verstoss). Gleiche Begruendung wie M018.
#
# FORENSISCHE FESTLEGUNGEN (Bauplan A1 §2.1):
#   1. 'alias_norm' = str.casefold(alias), im REPO gebildet und GESPEICHERT.
#      Die Kollations-Leitlinie des Falls richtet alles an users.username
#      (utf8mb4_unicode_ci, case-INsensitiv) aus (mc 2026-07-20,
#      Wiedervorlage_offene_Punkte.md). SQLite kennt nur ASCII-NOCASE — bei
#      einem multilingualen Forum (Fall-Erkenntnis 2) waeren 'Ярослав' und
#      'ЯРОСЛАВ' still zu zwei Eintraegen geworden. casefold() ist die
#      Unicode-korrekte Normalform. 'alias' bleibt im ORIGINAL erhalten
#      (Beweismittel — die Schreibweise selbst kann eine Erkenntnis sein).
#   2. PARTIELLER UNIQUE-Index (nur is_active=1) statt harter UNIQUE-Spalte:
#      nach einem Widerruf darf derselbe Alias erneut vergeben werden, die
#      widerrufene Zeile bleibt als Beleg stehen. ES WIRD NIE GELOESCHT.
#   3. CHECK auf 'kind_code' (geschlossene Menge) — Linie M010/M015/M016/M018:
#      ein Tippfehler liesse eine Zeile aus jedem Filter fallen (stiller
#      Beweisverlust).
#   4. KEIN RBAC-SEED: 'crossref.view'/'crossref.edit' (M018) werden
#      wiederverwendet — gleiche F5-Familie, keine Rechte-Inflation
#      (Entscheidungslinie Build 474 §3). Der Faehigkeitskatalog bleibt bei 33.
#
# SENSIBILITAET: alias/basis/note sind Freitexte, die eine reale Person
#   identifizierbar machen KOENNEN. Sie stehen nie im audit_log-Payload (im
#   Repo durchgesetzt, Muster M018).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + Guard. KIND='additive'.
# MIGRATIONSKLASSE: rein additiv, NUR coordinator.db, neue Tabelle —
#   Ermittler-Ergebnisdaten (evidence_/forensic_/assets_<uid>.db) unberuehrt,
#   der Migrationsvorbehalt seit 01.07.2026 greift nicht.
#
# Beleg: mc 2026-07-24 ("Arbeiten wir also AP-2A bitte zunaechst vollstaendig
#   ab"); Bauplan claude_Bauplan_A1_AliasKatalog_v0_1.md §2.1.
# Version: v0.8.504 · Build: 504 · 2026-07-24
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 22
NAME = "Globaler Alias-Katalog (subject_alias)"
KIND = "additive"


_DDL_SUBJECT_ALIAS = """
CREATE TABLE IF NOT EXISTS subject_alias (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id        INTEGER NOT NULL,          -- Forenkonto (Prepper-Schema)
    alias             TEXT    NOT NULL,          -- Originalschreibweise (Beleg)
    alias_norm        TEXT    NOT NULL,          -- casefold(alias), Dedup
    kind_code         TEXT    NOT NULL
                      CHECK(kind_code IN
                            ('forenname','handle','signatur','kontakt',
                             'sonstiges')),
    basis             TEXT    NOT NULL DEFAULT '',  -- Fundgrundlage (SENSIBEL)
    note              TEXT,                         -- freie Notiz (SENSIBEL)
    is_active         INTEGER NOT NULL DEFAULT 1
                      CHECK(is_active IN (0, 1)),
    retracted_reason  TEXT,                         -- Grund des Widerrufs
    created_by        INTEGER REFERENCES person(id),
    updated_by        INTEGER REFERENCES person(id),
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq INTEGER NOT NULL REFERENCES audit_log(seq)
)
"""

# Der partielle UNIQUE-Index ist die eigentliche Fachregel: EIN aktiver Alias je
# (Konto, Normform). Widerrufene Zeilen sind davon ausgenommen und bleiben als
# Beleg erhalten.
_IDX_UNIQUE_ACTIVE = (
    "ux_subject_alias_active",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_subject_alias_active "
    "ON subject_alias (subject_id, alias_norm) WHERE is_active = 1",
)
# Rueckwaertssuche "welche Konten fuehren diesen Namen?" — der Kern des
# Ermittlungsnutzens dieses Katalogs.
_IDX_NORM = (
    "ix_subject_alias_norm",
    "CREATE INDEX IF NOT EXISTS ix_subject_alias_norm "
    "ON subject_alias (alias_norm)",
)
# Vorwaertssuche "welche Namen fuehrt dieses Konto?".
_IDX_SUBJECT = (
    "ix_subject_alias_subject",
    "CREATE INDEX IF NOT EXISTS ix_subject_alias_subject "
    "ON subject_alias (subject_id)",
)

_INDICES = (_IDX_UNIQUE_ACTIVE, _IDX_NORM, _IDX_SUBJECT)
_TABLES = ("subject_alias",)


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
        logger.info("M022: subject_alias bereits vorhanden — No-op.")
        return

    con.execute(_DDL_SUBJECT_ALIAS)
    for _name, ddl in _INDICES:
        con.execute(ddl)

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    for t in _TABLES:
        if not _table_exists(con, t):
            raise RuntimeError("M022: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M022: Index '%s' fehlt nach up()." % ix)

    logger.info("M022: subject_alias + %d Indizes angelegt (kein RBAC-Seed — "
                "crossref.view/crossref.edit aus M018 werden wiederverwendet).",
                len(_INDICES))
