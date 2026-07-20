# =============================================================================
# management/migrations/coordinator/m015_promotion.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Betrieb/Governance (AP-2G)
# =============================================================================
# Migration M015 — coordinator.db (ADDITIV)
#   Legt die FREMDFORUM-PROMOTION an (Build 460, Welle 2, Idee 25 / Fundament
#   F3) und seedet das neue Schreibrecht 'ops.promote'.
#
#   Ein FREMDFORUM-KANDIDAT ist ein Fall mit forensic_<uid>.db, aber OHNE
#   evidence_<uid>.db (der Fall existiert, es fehlt der Arbeitsstand — Beleg
#   storage_overview.py:9-13,155-163; case_detector.py). Die Tabelle
#   'forum_promotion' haelt je Kandidat die BELEGTE Promotions-ENTSCHEIDUNG:
#   uebernommen / zurueckgestellt / fremdzustaendig (Zustandsmaschine:
#   ops/promotion_status.py). Ohne diese Zeile ist der Kandidat implizit 'offen'
#   (unentschieden) — die Abwesenheit einer Zeile IST der Zustand 'offen'.
#
# BEWUSSTE ENTSCHEIDUNG — KEIN FK user_id -> cases(user_id) (mc 2026-07-20):
#   Ein Fremdforum-Kandidat ist gerade der Fall, der NOCH NICHT formal in
#   'cases' steht (case_detector-Zustand 'neu'). Ein FK auf cases wuerde die
#   Entscheidung ueber genau diese Kandidaten unmoeglich machen. Die Existenz
#   des Kandidaten wird stattdessen zur Schreibzeit ueber die Praesenz der
#   forensic_<uid>.db geprueft (Server-Endpunkt, forensic_dir) — nicht ueber
#   die cases-Tabelle. UNIQUE(user_id) sichert dennoch GENAU EINE
#   Entscheidungszeile je Kandidat.
#
# FORENSISCHE FESTLEGUNGEN (mc 2026-07-20):
#   - 'uebernommen'/'fremdzustaendig' sind ENDGUELTIG (PromotionStatus). Ein
#     Irrtum wird durch eine NEUE, belegte Entscheidung korrigiert, nicht durch
#     Zurueckdrehen.
#   - Jeder Uebergang nach 'zurueckgestellt'/'fremdzustaendig' verlangt einen
#     GRUND (Pflichtfeld im Repo). Ein stilles Aussortieren waere genau die
#     Luecke, die dieses System verhindern soll (Grundregel 1).
#   - Der Kopf ist veraenderlich; die HISTORIE liegt im hash-verketteten
#     audit_log. 'audit_seq' traegt den Beleg der LETZTEN Aenderung,
#     'created_audit_seq' unveraenderlich den der Anlage.
#   - KEIN case_events-Zeitstrahl-Spiegel (mc 2026-07-20): ein 'neu'-Kandidat
#     hat noch keine cases-Zeile, der case_events-FK (user_id -> cases) braeche.
#     Der Beleg liegt vollstaendig im audit_log.
#
# VOKABULAR IM CODE, nicht in der DDL:
#   Die Uebergaenge/Labels werden im Code validiert (ops/promotion_status.py) —
#   ohne CHECK, damit spaetere Anpassungen additiv bleiben. AUSNAHME: 'status'
#   bekommt dennoch einen CHECK (abgeschlossene Zustandsmenge; ein Tippfehler
#   wuerde eine Zeile aus jedem Filter fallen lassen = stiller Beweisverlust).
#   Gleiche Linie wie M010.
#
# RBAC-SEED (eingefroren, m005-Prinzip): 'ops.promote' wird hier mit LITERALEN
#   Werten geseedet. Die Migration importiert ABSICHTLICH NICHT rbac/catalog.py
#   — eine Migration muss auch in Jahren noch exakt dasselbe tun. Die GRANTS
#   (wer die Faehigkeit bekommt) sind eine operative Entscheidung der
#   Chef-Ermittlerin (rbac_admin-CLI), NICHT Teil dieses Builds (default-deny).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + INSERT OR IGNORE + Guard
#             (INFO-No-op beim zweiten Lauf). Inline-Verifikation -> raise ->
#             ROLLBACK im Runner.
# KIND='additive' -> rein additiv, datenneutral, kein precount/postcount.
#
# Beleg: mc 2026-07-20 (Bauschnitt 460 Backend; MD5-Handshake bestaetigt).
# Version: v0.7.460 · Build: 460 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 15
NAME = "Fremdforum-Promotion (forum_promotion) + RBAC-Seed ops.promote"
KIND = "additive"


# --- forum_promotion ---------------------------------------------------------
#   user_id: forensic_<uid> des Kandidaten (KEIN FK auf cases, s. Kopf).
#   status : Zustandsmaschine ops/promotion_status.py (CHECK = die vier
#            gespeicherten Zustaende; 'offen' wird NIE gespeichert).
#   grund  : Pflicht bei zurueckgestellt/fremdzustaendig (Durchsetzung im Repo).
#   herkunft: optionaler Freitext-Hinweis auf das Quell-/Fremdforum.
_DDL_PROMOTION = """
CREATE TABLE IF NOT EXISTS forum_promotion (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    status            TEXT    NOT NULL
                      CHECK(status IN ('gesichtet','uebernommen',
                                       'zurueckgestellt','fremdzustaendig')),
    grund             TEXT,
    herkunft          TEXT,
    created_by        INTEGER REFERENCES person(id),
    created_at        INTEGER NOT NULL,
    decided_by        INTEGER REFERENCES person(id),
    decided_at        INTEGER,
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq INTEGER NOT NULL REFERENCES audit_log(seq),
    UNIQUE(user_id)
)
"""

# Kernabfrage der Sicht: "welche Kandidaten sind in welchem Zustand?"
_IDX_STATUS = (
    "ix_promotion_status",
    "CREATE INDEX IF NOT EXISTS ix_promotion_status "
    "ON forum_promotion (status)",
)

_INDICES = (_IDX_STATUS,)
_TABLES = ("forum_promotion",)

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("ops.promote", "Fremdforum-Kandidaten entscheiden",
     "Fremdforum-Kandidaten uebernehmen, zurueckstellen oder als "
     "fremdzustaendig einstufen (auditiert)."),
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
        logger.info("M015: forum_promotion + RBAC-Seed bereits vorhanden "
                    "— No-op.")
        return

    # Vorbedingung: M006 (rbac_capability) muss angewandt sein. Fehlt sie, ist
    # das ein Aufbaufehler und KEIN Grund, den Seed still zu ueberspringen.
    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M015: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    con.execute(_DDL_PROMOTION)
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
            raise RuntimeError("M015: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M015: Index '%s' fehlt nach up()." % ix)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M015: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M015: forum_promotion angelegt; Faehigkeit(en) %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
