# =============================================================================
# management/migrations/coordinator/m016_case_release.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Externe Fallfreigabe (AP-2G)
# =============================================================================
# Migration M016 — coordinator.db (ADDITIV)
#   Legt die EXTERNE FALLFREIGABE an (Build 462, Welle 2, Idee 26) und seedet
#   die neuen Rechte 'release.view' und 'release.grant'.
#
#   Eine FALLFREIGABE dokumentiert BELEGT, dass ein Fall einem externen
#   NRW-Ermittler zugaenglich gemacht wurde — nach drei Bedingungen (Idee 26):
#     * AD-ACL: der Empfaenger ist bestaetigtes Mitglied der berechtigten Gruppe
#       (geprueft zur Schreibzeit ueber die AD-Schicht F4, ad_directory.py),
#     * UNBEDENKLICHKEIT: eine Pflicht-Grundlage gem. Fallregel 3 (Weitergabe nur
#       nach Pruefung auf Unverfaenglichkeit; gleiche Linie wie export/staging.py),
#     * AUDITIERT: Freigabe UND Widerruf sind hash-verkettete Belege.
#
# FK AUF cases (ANDERS ALS BEI DER PROMOTION, mc 2026-07-20):
#   Man gibt nur einen ECHTEN, aufgenommenen Fall frei -> user_id REFERENCES
#   cases(user_id). (Der Fremdforum-Kandidat war gerade der NOCH-NICHT-Fall;
#   hier ist das Gegenteil verlangt.)
#
# FORENSISCHE FESTLEGUNGEN (mc 2026-07-20):
#   - 'widerrufen' ist ENDGUELTIG (ReleaseStatus). Eine erneute Freigabe ist ein
#     NEUER Record; die Historie einer Weitergabe wird nicht umgeschrieben.
#   - Der Widerruf verlangt einen GRUND (Pflichtfeld im Repo).
#   - Der Kopf ist veraenderlich; die HISTORIE liegt im audit_log. 'audit_seq'
#     traegt den Beleg der LETZTEN Aenderung, 'created_audit_seq' unveraenderlich
#     den der Anlage, 'revoke_audit_seq' den des Widerrufs.
#   - KEIN case_events-Zeitstrahl-Spiegel: die externe Weitergabe ist ein
#     GOVERNANCE-Vorgang, kein Ermittlungs-Zeitstrahl-Ereignis.
#
# VOKABULAR IM CODE, nicht in der DDL:
#   'umfang' (bericht/akte/auszug) wird im Code validiert (release_status.py) —
#   ohne CHECK, damit eine spaetere Umfangsart additiv bleibt. AUSNAHME:
#   'status' bekommt einen CHECK (abgeschlossene Zustandsmenge; ein Tippfehler
#   dort machte eine Freigabe unsichtbar = stiller Verlust). Linie wie M010.
#
# RBAC-SEED (eingefroren, m005-Prinzip): 'release.view'/'release.grant' werden
#   hier LITERAL geseedet (NICHT aus catalog.py importieren). Die GRANTS (wer die
#   Faehigkeit bekommt) sind eine operative Entscheidung der Chef-Ermittlerin
#   (rbac_admin-CLI), NICHT Teil dieses Builds (default-deny).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + INSERT OR IGNORE + Guard.
# KIND='additive' -> rein additiv, datenneutral.
#
# Beleg: mc 2026-07-20 (Bauschnitt 462 Backend; MD5-Handshake bestaetigt).
# Version: v0.7.462 · Build: 462 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 16
NAME = "Externe Fallfreigabe (case_release) + RBAC-Seed release.view/release.grant"
KIND = "additive"


# --- case_release ------------------------------------------------------------
_DDL_RELEASE = """
CREATE TABLE IF NOT EXISTS case_release (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES cases(user_id),
    recipient_kennung TEXT    NOT NULL,          -- AD-SAMAccountName (NRW-Ermittler)
    recipient_display TEXT    NOT NULL,          -- AD-Anzeigename (aus F4)
    umfang            TEXT    NOT NULL,           -- Vokabular release_status.py
    status            TEXT    NOT NULL DEFAULT 'freigegeben'
                      CHECK(status IN ('freigegeben','widerrufen')),
    unbedenklichkeit_grundlage TEXT NOT NULL,     -- Pflicht-Vermerk (Fallregel 3)
    grund_widerruf    TEXT,
    created_by        INTEGER REFERENCES person(id),
    created_at        INTEGER NOT NULL,
    revoked_by        INTEGER REFERENCES person(id),
    revoked_at        INTEGER,
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq INTEGER NOT NULL REFERENCES audit_log(seq),
    revoke_audit_seq  INTEGER REFERENCES audit_log(seq)
)
"""

# Kernabfragen: "welche AKTIVEN Freigaben hat Fall X?" und "was hat Empfaenger Y?"
_IDX_CASE = (
    "ix_release_case",
    "CREATE INDEX IF NOT EXISTS ix_release_case "
    "ON case_release (user_id, status)",
)
_IDX_RECIPIENT = (
    "ix_release_recipient",
    "CREATE INDEX IF NOT EXISTS ix_release_recipient "
    "ON case_release (recipient_kennung)",
)

_INDICES = (_IDX_CASE, _IDX_RECIPIENT)
_TABLES = ("case_release",)

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("release.view", "Externe Fallfreigaben sehen",
     "Externe Fallfreigaben an NRW-Ermittler (Empfaenger, Umfang, Zustand) "
     "lesen."),
    ("release.grant", "Externe Fallfreigabe erteilen/widerrufen",
     "Einen Fall an einen bestaetigten NRW-Ermittler freigeben oder eine "
     "Freigabe widerrufen (auditiert, Unbedenklichkeit Pflicht)."),
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
        logger.info("M016: case_release + RBAC-Seed bereits vorhanden — No-op.")
        return

    # Vorbedingung: M006 (rbac_capability) muss angewandt sein. Fehlt sie, ist
    # das ein Aufbaufehler und KEIN Grund, den Seed still zu ueberspringen.
    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M016: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    con.execute(_DDL_RELEASE)
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
            raise RuntimeError("M016: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M016: Index '%s' fehlt nach up()." % ix)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M016: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M016: case_release angelegt; Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
