# =============================================================================
# management/migrations/coordinator/m017_onboarding.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Onboarding/Offboarding (AP-2G)
# =============================================================================
# Migration M017 — coordinator.db (ADDITIV)
#   Legt die ONBOARDING-/OFFBOARDING-CHECKLISTE an (Build 464, Welle 2, Idee 31)
#   und seedet die Rechte 'onboarding.view' und 'onboarding.edit'.
#
#   Je (person_id, kind, step_code) HAELT eine Zeile den BELEGTEN Zustand eines
#   Checklisten-Schritts. Das Schritt-Vokabular (kind/step_code) und die
#   Zustandslogik leben im Code (onboarding/checklist_status.py) — hier steht
#   nur der Zustand + Beleg.
#
#   FK AUF person: die Checkliste gehoert zu einem echten Personendatensatz
#   (= AD-Identitaet, system_username = SAMAccountName). Kopplung an F4.
#
# FORENSISCHE FESTLEGUNGEN (mc 2026-07-20):
#   - 'offen' wird NICHT gespeichert (Abwesenheit einer Zeile). Der CHECK deckt
#     daher nur die zwei materialisierten Zustaende 'erledigt'/'nicht_zutreffend'.
#     Ein Reset auf 'offen' LOESCHT die Zeile (auditiert) — die Historie liegt im
#     hash-verketteten audit_log.
#   - Uebergaenge sind frei (Checkliste = Arbeitsmittel, Korrektur moeglich), aber
#     JEDE Aenderung ist auditiert; 'nicht_zutreffend' verlangt einen Grund.
#   - Kein case_events-Spiegel: Personal-/Governance-Vorgang, kein Ermittlungs-
#     Zeitstrahl-Ereignis.
#
# VOKABULAR IM CODE, nicht in der DDL: 'kind'/'step_code' werden im Code
#   validiert (additiv, kein CHECK). AUSNAHME: 'status' bekommt einen CHECK
#   (abgeschlossene Zustandsmenge; ein Tippfehler machte einen Schritt
#   unsichtbar = stiller Verlust). Linie wie M010/M016.
#
# RBAC-SEED (eingefroren, m005-Prinzip): 'onboarding.view'/'onboarding.edit'
#   LITERAL geseedet (NICHT aus catalog.py importieren). Die GRANTS sind eine
#   operative Entscheidung der Chef-Ermittlerin (default-deny).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + INSERT OR IGNORE + Guard.
# KIND='additive'.
#
# Beleg: mc 2026-07-20 (Bauschnitt 464 Backend; MD5-Handshake bestaetigt).
# Version: v0.7.464 · Build: 464 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 17
NAME = "Onboarding/Offboarding-Checkliste (onboarding_item) + RBAC-Seed"
KIND = "additive"


_DDL_ONBOARDING = """
CREATE TABLE IF NOT EXISTS onboarding_item (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id         INTEGER NOT NULL REFERENCES person(id),
    kind              TEXT    NOT NULL,          -- 'onboarding' | 'offboarding'
    step_code         TEXT    NOT NULL,           -- Vokabular checklist_status.py
    status            TEXT    NOT NULL
                      CHECK(status IN ('erledigt','nicht_zutreffend')),
    note              TEXT,
    done_by           INTEGER REFERENCES person(id),
    done_at           INTEGER,
    created_at        INTEGER NOT NULL,
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq INTEGER NOT NULL REFERENCES audit_log(seq),
    UNIQUE(person_id, kind, step_code)
)
"""

# Kernabfrage der Sicht: "welchen Stand hat Person X in Checkliste 'kind'?"
_IDX_PERSON = (
    "ix_onboarding_person",
    "CREATE INDEX IF NOT EXISTS ix_onboarding_person "
    "ON onboarding_item (person_id, kind)",
)

_INDICES = (_IDX_PERSON,)
_TABLES = ("onboarding_item",)

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("onboarding.view", "Onboarding-/Offboarding-Checkliste sehen",
     "Den Stand der Onboarding-/Offboarding-Checklisten der Mitarbeiter lesen."),
    ("onboarding.edit", "Onboarding-/Offboarding-Checkliste pflegen",
     "Checklisten-Schritte als erledigt/nicht zutreffend setzen oder "
     "zuruecksetzen (auditiert)."),
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
        logger.info("M017: onboarding_item + RBAC-Seed bereits vorhanden "
                    "— No-op.")
        return

    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M017: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    con.execute(_DDL_ONBOARDING)
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
            raise RuntimeError("M017: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M017: Index '%s' fehlt nach up()." % ix)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M017: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M017: onboarding_item angelegt; Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
