# =============================================================================
# management/migrations/coordinator/m006_rbac_schema.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M006 — coordinator.db (ADDITIV)
#   Legt die RBAC-Matrix an und seedet den KATALOG (Rollen + Faehigkeiten).
#   Beleg: Bauplan_Baustelle7_Management_v1_1.md §11.1/§11.3/§11.7, Welle 0,
#          RBAC Schnitt (a) "Schema + Seed (auditiert)"; mc 2026-07-10.
#
# Vier Tabellen (Beleg §11.3):
#   rbac_role(code PK, label, created_at)
#   rbac_capability(code PK, label, description, created_at)
#   rbac_grant(id PK, role_code->rbac_role, capability_code->rbac_capability,
#     scope('alle'|'eigene'|NULL), audit_seq NOT NULL ->audit_log(seq),
#     granted_by->person, granted_at, revoked_at, revoked_by->person,
#     revoke_audit_seq->audit_log(seq), note)          -- append-only Soft-Revoke
#   person_role(id PK, person_id->person, role_code->rbac_role, assigned_by,
#     assigned_at, revoked_at, revoked_by, audit_seq NOT NULL ->audit_log(seq),
#     revoke_audit_seq->audit_log(seq))                -- maszgeblich fuer RBAC
#   + Partial-Index ix_rbac_grant_active(role_code, capability_code)
#     WHERE revoked_at IS NULL                         (Beleg §11.3)
#   + Partial-Index ix_person_role_active(person_id)
#     WHERE revoked_at IS NULL                         (Resolver-Lesepfad, additiv)
#
# ABGRENZUNG (mc 2026-07-10):
#   rbac_grant UND person_role starten LEER. Grund: audit_seq ist NOT NULL und
#   muss — wie case_events — PRO Zeile an einen echten audit_log-Eintrag koppeln.
#   Migrations-geseedete Grants haetten kein sauberes audit_seq. Die Basis-Grants
#   (lector->reports.review, admin->feedback.moderate, searchagent->
#   evidence.fulltext_search u.a., §11.3) und Rollenzuweisungen kommen daher in
#   Schnitt (b) ueber die auditierte policy_admin-CLI. default-deny + leer =
#   niemand darf etwas -> forensisch sauberer Ausgangszustand.
#
# EINGEFRORENER SEED (m005-Prinzip): Diese Migration importiert
#   management.rbac.catalog NICHT. Eine bereits angewandte Migration darf ihr
#   Laufzeitverhalten nie aendern (sonst Nichtdeterminismus trotz gleicher
#   Checksumme). Die Werte unten sind eine eingefrorene Kopie von catalog.py zur
#   Bauzeit 343. Die Bruecke ist Test R02 ("m006-Seed == catalog.py"). Waechst
#   der Katalog spaeter, seedet eine NEUE Migration die Differenz.
#
# ZWEI additive Verfeinerungen ueber die §11.3-Skizze hinaus (im Chat
# transparent angemerkt, analog case_created-Spiegel §8.4):
#   1) person_role.revoke_audit_seq ergaenzt (symmetrisch zu rbac_grant): ein
#      Soft-Revoke einer Rollenzuweisung ist ein forensisch relevantes Ereignis
#      und braucht seinen eigenen Beleg (Grundregel 1). Ohne diese Spalte muesste
#      Schnitt (b) coordinator.db spaeter erneut altern.
#   2) ix_person_role_active — Resolver liest aktive Rollen je person_id; der
#      Partial-Index stuetzt genau diesen Lesepfad. Rein additiv.
#
# Idempotenz: CREATE TABLE/INDEX IF NOT EXISTS + INSERT OR IGNORE. Zweiter Lauf
#   ist ein sauberer No-Op (der Runner ueberspringt M006 ohnehin per
#   schema_migrations; die IF-NOT-EXISTS/OR-IGNORE-Form macht up() zusaetzlich
#   in sich reentrant).
#
# KIND='additive' -> kein Zeilen-/Spaltenverlust; der Runner ruft weder
#   precount/postcount noch verify. Die Invariantenpruefung erfolgt INLINE in
#   up() mit 'raise' bei Verstoss -> ROLLBACK (Runner umschliesst up() mit
#   BEGIN IMMEDIATE/COMMIT, ROLLBACK bei Exception) -> kein Teilzustand.
#
# Auditierung: automatisch ueber den Runner (MIGRATION_APPLIED, actor_id=None =
#   System), sofern ein AuditLog uebergeben ist — wie bei allen Migrationen.
#
# Voraussetzung: 'person' existiert (aus M005). FK-Referenzen auf person/
#   audit_log sind zulaessig, auch wenn foreign_keys=OFF; die leeren Tabellen
#   erzeugen keine FK-Verletzung. coordinator.db hat keinen Migrations-Lock;
#   migrate.py-Lauf beim Deploy ist dennoch ZWINGEND (Schemaaenderung).
#
# Version: v0.7.343 · Build: 343 · 2026-07-10
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 6
NAME = "RBAC-Schema + Katalog-Seed (rbac_role/capability/grant, person_role)"
KIND = "additive"


# --- DDL ---------------------------------------------------------------------
_DDL_RBAC_ROLE = """
CREATE TABLE IF NOT EXISTS rbac_role (
    code       TEXT    PRIMARY KEY,
    label      TEXT    NOT NULL,
    created_at INTEGER NOT NULL
)
"""

_DDL_RBAC_CAPABILITY = """
CREATE TABLE IF NOT EXISTS rbac_capability (
    code        TEXT    PRIMARY KEY,
    label       TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
)
"""

_DDL_RBAC_GRANT = """
CREATE TABLE IF NOT EXISTS rbac_grant (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    role_code        TEXT    NOT NULL,
    capability_code  TEXT    NOT NULL,
    scope            TEXT    CHECK(scope IN ('alle','eigene') OR scope IS NULL),
    audit_seq        INTEGER NOT NULL,          -- Beleg-Kopplung (Vergabe)
    granted_by       INTEGER,                    -- person.id; NULL = System
    granted_at       INTEGER NOT NULL,
    revoked_at       INTEGER,                    -- append-only Soft-Revoke
    revoked_by       INTEGER,                    -- person.id
    revoke_audit_seq INTEGER,                    -- Beleg-Kopplung (Ruecknahme)
    note             TEXT,
    FOREIGN KEY(role_code)        REFERENCES rbac_role(code),
    FOREIGN KEY(capability_code)  REFERENCES rbac_capability(code),
    FOREIGN KEY(audit_seq)        REFERENCES audit_log(seq),
    FOREIGN KEY(granted_by)       REFERENCES person(id),
    FOREIGN KEY(revoked_by)       REFERENCES person(id),
    FOREIGN KEY(revoke_audit_seq) REFERENCES audit_log(seq)
)
"""

_DDL_PERSON_ROLE = """
CREATE TABLE IF NOT EXISTS person_role (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id        INTEGER NOT NULL,
    role_code        TEXT    NOT NULL,
    assigned_by      INTEGER,                    -- person.id; NULL = System
    assigned_at      INTEGER NOT NULL,
    revoked_at       INTEGER,                    -- append-only Soft-Revoke
    revoked_by       INTEGER,                    -- person.id
    audit_seq        INTEGER NOT NULL,          -- Beleg-Kopplung (Zuweisung)
    revoke_audit_seq INTEGER,                    -- Beleg-Kopplung (Ruecknahme)
    FOREIGN KEY(person_id)        REFERENCES person(id),
    FOREIGN KEY(role_code)        REFERENCES rbac_role(code),
    FOREIGN KEY(assigned_by)      REFERENCES person(id),
    FOREIGN KEY(revoked_by)       REFERENCES person(id),
    FOREIGN KEY(audit_seq)        REFERENCES audit_log(seq),
    FOREIGN KEY(revoke_audit_seq) REFERENCES audit_log(seq)
)
"""

_DDL_IX_GRANT_ACTIVE = (
    "CREATE INDEX IF NOT EXISTS ix_rbac_grant_active "
    "ON rbac_grant(role_code, capability_code) WHERE revoked_at IS NULL"
)

_DDL_IX_PERSON_ROLE_ACTIVE = (
    "CREATE INDEX IF NOT EXISTS ix_person_role_active "
    "ON person_role(person_id) WHERE revoked_at IS NULL"
)


# --- EINGEFRORENER Seed (Kopie von catalog.py zur Bauzeit 343) ---------------
#   NICHT aus catalog.py importiert (siehe Kopf). Test R02 verankert Gleichheit.
_SEED_ROLES = (
    ("supervisor", "Chef-Ermittlerin / Aufsicht"),
    ("investigator", "Ermittler:in"),
    ("support", "Support / Mentoring (Live-Beistand)"),
    ("admin", "Plattform-Administration"),
    ("lector", "Gegenleser:in (Bericht vor StA-Uebergabe)"),
    ("searchagent", "Recherche mit Volltextsuche"),
)

_SEED_CAPABILITIES = (
    ("dashboard.view", "Ampel-Dashboard sehen",
     "Falluebersicht mit Ampel und Kennzahlen lesen."),
    ("assignment.edit", "Zuweisungen bearbeiten",
     "Faelle Ermittler:innen zuweisen/entziehen."),
    ("mentoring.view", "Mentoring-/Support-Sicht",
     "Laufende Support-Sitzungen und Beistands-Uebersicht sehen."),
    ("reports.review", "Berichte gegenlesen",
     "Ermittlungsberichte vor StA-Uebergabe pruefen (Vier-Augen)."),
    ("reports.approve", "Berichte freigeben",
     "Finale Freigabe eines Berichts (StA-Uebergabe)."),
    ("stats.export_sta", "StA-Statistik exportieren",
     "Gerichtsfeste Statistik-/Kennzahl-Exporte fuer die StA."),
    ("workload.view", "Lastverteilung sehen",
     "Ermittler-Auslastung und Verteilungsuebersicht lesen."),
    ("support_history.view", "Support-Historie sehen",
     "Abgeschlossene Support-Sitzungen und Verlauf lesen."),
    ("mycases.view", "Eigene Faelle sehen",
     "Die dem eigenen Konto zugewiesenen Faelle lesen."),
    ("myhistory.view", "Eigene Historie sehen",
     "Den eigenen Ereignis-/Taetigkeitsverlauf lesen."),
    ("policy.view", "RBAC-Richtlinie einsehen",
     "Rollen, Faehigkeiten und Grants (die RBAC-Matrix) lesen."),
    ("evidence.fulltext_search", "Volltextsuche (Beweismittel)",
     "Falluebergreifende Volltextsuche (staerkstes Kapselungsmodell, Welle 3)."),
    ("feedback.moderate", "Plattform-Feedback moderieren",
     "Bug-/Feedback-Tickets moderieren und freigeben."),
    ("capacity.edit", "Kapazitaet pflegen",
     "Arbeitszeit-/Verfuegbarkeitsdaten fuer Prognose/Gantt pflegen."),
    ("ops.view", "Betriebs-/Systemzustand sehen",
     "Backup-/Speicher-/Integritaets-Status der Anlage lesen."),
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _index_exists(con: sqlite3.Connection, name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def up(con: sqlite3.Connection) -> None:
    now = int(time.time())

    # (a) Schema anlegen (idempotent).
    con.execute(_DDL_RBAC_ROLE)
    con.execute(_DDL_RBAC_CAPABILITY)
    con.execute(_DDL_RBAC_GRANT)
    con.execute(_DDL_PERSON_ROLE)
    con.execute(_DDL_IX_GRANT_ACTIVE)
    con.execute(_DDL_IX_PERSON_ROLE_ACTIVE)

    # (b) Katalog seeden (idempotent: INSERT OR IGNORE laesst bestehende Zeilen
    #     und ihr created_at unangetastet — kein Clobbern bei Zweitlauf).
    con.executemany(
        "INSERT OR IGNORE INTO rbac_role (code, label, created_at) "
        "VALUES (?, ?, ?)",
        [(code, label, now) for (code, label) in _SEED_ROLES],
    )
    con.executemany(
        "INSERT OR IGNORE INTO rbac_capability "
        "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
        [(code, label, desc, now)
         for (code, label, desc) in _SEED_CAPABILITIES],
    )

    # (c) Inline-Verifikation (bei Verstoss 'raise' -> ROLLBACK im Runner).
    for table in ("rbac_role", "rbac_capability", "rbac_grant", "person_role"):
        if not _table_exists(con, table):
            raise RuntimeError("M006: Tabelle '%s' fehlt nach up()." % table)
    for ix in ("ix_rbac_grant_active", "ix_person_role_active"):
        if not _index_exists(con, ix):
            raise RuntimeError("M006: Index '%s' fehlt nach up()." % ix)

    # Jede geseedete Zeile MUSS vorhanden sein (kein stiller Teil-Seed,
    # Grundregel 1).
    for (code, _label) in _SEED_ROLES:
        if con.execute(
            "SELECT 1 FROM rbac_role WHERE code=?", (code,)
        ).fetchone() is None:
            raise RuntimeError("M006: Rolle '%s' nach Seed nicht vorhanden." % code)
    for (code, _label, _desc) in _SEED_CAPABILITIES:
        if con.execute(
            "SELECT 1 FROM rbac_capability WHERE code=?", (code,)
        ).fetchone() is None:
            raise RuntimeError(
                "M006: Faehigkeit '%s' nach Seed nicht vorhanden." % code
            )

    # rbac_grant/person_role starten LEER (mc): explizit belegt, nicht still.
    n_grants = con.execute("SELECT COUNT(*) FROM rbac_grant").fetchone()[0]
    if n_grants != 0:
        raise RuntimeError(
            "M006: rbac_grant startet nicht leer (%d Zeilen) — Grants gehoeren "
            "in Schnitt (b)." % n_grants
        )

    logger.info(
        "M006: RBAC-Schema angelegt; Katalog geseedet (%d Rollen, %d "
        "Faehigkeiten); rbac_grant/person_role leer.",
        len(_SEED_ROLES), len(_SEED_CAPABILITIES),
    )
