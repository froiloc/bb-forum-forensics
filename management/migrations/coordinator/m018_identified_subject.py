# =============================================================================
# management/migrations/coordinator/m018_identified_subject.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kreuzbezug/Identitaet (AP-2A)
# =============================================================================
# Migration M018 — coordinator.db (ADDITIV)
#   Legt den GLOBALEN KATALOG IDENTIFIZIERTER PERSONEN 'identified_subject' an
#   (Build 468, Welle 2, AP-2A, Ideen 9/10) und seedet die Rechte
#   'crossref.view' und 'crossref.edit'.
#
#   Je subject_id HAELT hoechstens EINE Zeile die (aktuelle) Zuordnung eines
#   Forennutzers zu einer realen Person, mit einer KONFIDENZSTUFE. Die Historie
#   der Reifung (verdacht -> wahrscheinlich -> gesichert) liegt im hash-
#   verketteten, nur-anhaengenden audit_log; die Tabelle traegt den Ist-Stand.
#
# SCHLUESSEL subject_id (mc 2026-07-20):
#   subject_id ist der Forennutzer-Schluessel NACH PREPPER-SCHEMA (Realnutzer:
#   subject_id == users.id; Geist: subject_id == prefix + mat_usernames.id,
#   Beleg: Entscheidung SubjectID/Geisternutzer 2026-07-20). BEWUSST KEIN FK auf
#   cases: der Katalog ist global und erfasst auch Geister, fuer die (noch) kein
#   Fallpaket existiert — ein FK wuerde diese > 550k Namen ausschliessen
#   (Grundregel-1-Verstoss). Die globale user_id->subject_id-Umstellung ist ein
#   EIGENER Folge-Build (Datenmigrationsleitfaden), NICHT Teil von 468.
#
# FORENSISCHE FESTLEGUNGEN (mc 2026-07-20):
#   - CHECK auf 'confidence_code' (geschlossene Menge 'verdacht'/'wahrscheinlich'
#     /'gesichert') — ein Tippfehler machte eine Zuordnung unsichtbar/ungueltig
#     (stiller Verlust). Linie wie M010/M016/M017 ('status') und M011 ('extrem').
#     'confidence_ordinal' wird im Repo eingefroren (Code+Zahlenwert, Muster M011).
#   - AKTUALISIERBAR, aber JEDE Aenderung auditiert (Konfidenz reift belegt).
#     Kein append-only-Trigger wie bei investigation_results — dort ist die
#     Bewertung ein Snapshot, hier ist der EINE Katalogeintrag der Ist-Stand.
#   - real_identity/basis/note sind sensible PII-Freitexte: sie stehen nie im
#     audit_log-Payload (Sensibilitaetsregel, im Repo durchgesetzt).
#   - ZWEITE ACHSE 'Verwertbarkeit' (rechtlich) ist ZURUECKGESTELLT (juristische
#     Rueckkopplung StA); sie wird spaeter ADDITIV nachgeruestet (Spalte/Tabelle).
#
# RBAC-SEED (eingefroren, m005-Prinzip): 'crossref.view'/'crossref.edit' LITERAL
#   geseedet (NICHT aus catalog.py importieren). Die GRANTS sind eine operative
#   Entscheidung der Chef-Ermittlerin (default-deny).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + INSERT OR IGNORE + Guard.
# KIND='additive'.
#
# Beleg: mc 2026-07-20 (Bauschnitt 468 Backend; MD5-Handshake bestaetigt).
# Version: v0.7.468 · Build: 468 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 18
NAME = "Katalog identifizierter Personen (identified_subject) + RBAC-Seed"
KIND = "additive"


_DDL_IDENTIFIED_SUBJECT = """
CREATE TABLE IF NOT EXISTS identified_subject (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id         INTEGER NOT NULL,        -- Forennutzer (Prepper-Schema)
    real_identity      TEXT    NOT NULL,        -- reale Person (SENSIBEL)
    confidence_code    TEXT    NOT NULL
                       CHECK(confidence_code IN
                             ('verdacht','wahrscheinlich','gesichert')),
    confidence_ordinal INTEGER NOT NULL,        -- eingefroren (10/20/30)
    basis              TEXT    NOT NULL DEFAULT '',  -- Fundgrundlage (SENSIBEL)
    note               TEXT,                     -- freie Notiz (SENSIBEL)
    created_by         INTEGER REFERENCES person(id),
    updated_by         INTEGER REFERENCES person(id),
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL,
    audit_seq          INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq  INTEGER NOT NULL REFERENCES audit_log(seq),
    UNIQUE(subject_id)
)
"""

# Kernabfrage der spaeteren Sicht: "Katalog, staerkste Konfidenz zuerst".
_IDX_CONFIDENCE = (
    "ix_identified_subject_confidence",
    "CREATE INDEX IF NOT EXISTS ix_identified_subject_confidence "
    "ON identified_subject (confidence_ordinal)",
)

_INDICES = (_IDX_CONFIDENCE,)
_TABLES = ("identified_subject",)

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("crossref.view", "Kreuzbezug/Identitaetskatalog sehen",
     "Den Katalog identifizierter Personen (Konto->reale Person) lesen."),
    ("crossref.edit", "Kreuzbezug/Identitaetskatalog pflegen",
     "Zuordnungen anlegen/revidieren und die Konfidenzstufe setzen "
     "(auditiert)."),
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
        logger.info("M018: identified_subject + RBAC-Seed bereits vorhanden "
                    "— No-op.")
        return

    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M018: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    con.execute(_DDL_IDENTIFIED_SUBJECT)
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
            raise RuntimeError("M018: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M018: Index '%s' fehlt nach up()." % ix)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M018: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M018: identified_subject angelegt; Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
