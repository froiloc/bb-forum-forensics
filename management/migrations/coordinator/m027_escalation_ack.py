# =============================================================================
# management/migrations/coordinator/m027_escalation_ack.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Eskalationen (Build 517)
# =============================================================================
# Migration M027 — coordinator.db (ADDITIV)
#   Legt die QUITTIERUNG von Eskalationen an ('escalation_ack') und seedet die
#   dafuer noetige Faehigkeit 'escalation.ack'.
#
# BEFUND, DER DIESEN BUILD AUSLOEST (Uebergabe 440-453 §3.3):
#   "Die Eskalation ist nur auswertend — der auditierte Schreibpfad fehlt."
#   Bis hierher konnte eine Leitung eine Eskalation SEHEN, aber nirgends
#   festhalten, dass sie sie gesehen und was sie veranlasst hat. Damit fehlte
#   genau der Beleg, der eine Aufsichtsentscheidung nachvollziehbar macht.
#
# WAS EINE QUITTIERUNG IST — UND WAS SIE AUSDRUECKLICH NICHT IST:
#   Sie ist ein VERMERK ("gesehen am ..., von ..., veranlasst wurde ...").
#   Sie ist KEIN Erledigen. Die Eskalation VERSCHWINDET NICHT aus der Liste:
#   der zugrunde liegende Zustand (Fall liegt seit N Tagen) besteht ja fort.
#   Wuerde die Quittierung die Meldung ausblenden, koennte ein Fall durch
#   einen Klick unsichtbar gemacht werden, ohne dass sich an ihm etwas aendert
#   — das waere die gefaehrlichste Form eines stillen Beweisverlusts
#   (Grundregel 1). Die Meldung bleibt also stehen und traegt ihren Vermerk.
#
# SCHLUESSEL (rule_code, subject_id):
#   Eskalationen sind ABGELEITET, nicht gespeichert — sie haben keine eigene,
#   dauerhafte ID. Der einzige stabile Bezug ist "diese Regel an diesem Fall".
#   subject_id IST NULL fuer die systemische Regel 'rueckstau_hoch', die zu
#   gar keinem Fall gehoert; NULL ist hier also eine AUSSAGE und kein
#   fehlender Wert. Deshalb bewusst KEIN NOT NULL und KEIN UNIQUE ueber
#   (rule_code, subject_id): in SQLite sind NULL-Werte in einem UNIQUE-Index
#   untereinander verschieden, ein UNIQUE haette fuer die systemische Regel
#   also ohnehin nicht gegriffen und dabei falsche Sicherheit vorgetaeuscht.
#   Die Fachregel "hoechstens EIN gueltiger Vermerk je Regel und Fall" setzt
#   das Repo INNERHALB der Schreibtransaktion (BEGIN IMMEDIATE) durch.
#
# BEOBACHTETER STAND ZUM ZEITPUNKT DER QUITTIERUNG:
#   'days_inactive_at_ack' haelt fest, WIE ALT der Fall war, als quittiert
#   wurde. Ohne diesen Wert waere ein Vermerk von vor einem halben Jahr nicht
#   von einem heutigen zu unterscheiden — die Lesesicht kann daraus ohne jede
#   zusaetzliche Schwelle die Tatsache ableiten, dass sich die Lage seit der
#   Quittierung VERSCHLECHTERT hat. NULL ist zulaessig (die systemische Regel
#   kennt keine Inaktivitaet) und bedeutet "nicht erhoben", nicht "0 Tage".
#
# WIDERRUF STATT LOESCHUNG (Linie M022):
#   Ein Vermerk wird NIE geloescht. Ein irrtuemlicher oder ueberholter Vermerk
#   wird mit Pflichtgrund WIDERRUFEN (revoked_at/-by/-reason gesetzt); die
#   Zeile bleibt als Beleg stehen. Die Spalten sind von Anfang an da und
#   werden von Anfang an bedient — es gibt keine tote Struktur.
#
# SENSIBILITAET: 'reason' und 'revoke_reason' sind Freitexte und stehen NIE im
#   audit_log-Payload (Muster M018/M022) — dort nur FAKTEN und Textlaengen.
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + INSERT OR IGNORE + Guard.
# MIGRATIONSKLASSE: rein additiv, NUR coordinator.db, NEUE Tabelle. Keine
#   bestehende Zeile wird angefasst, keine Spalte umgebaut; die Ermittler-
#   Ergebnisdatenbanken (evidence_/forensic_/assets_<uid>.db) sind nicht
#   beruehrt. Der Migrationsvorbehalt seit 01.07.2026 greift damit nicht —
#   es kann kein bestehendes Wissen verloren gehen.
#
# Beleg: Uebergabe 440-453 §3.3; Idee 23 (AP-2G).
# Version: v0.8.517 · Build: 517 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 27
NAME = "Quittierung von Eskalationen (escalation_ack) + escalation.ack"
KIND = "additive"


_DDL_ESCALATION_ACK = """
CREATE TABLE IF NOT EXISTS escalation_ack (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_code            TEXT    NOT NULL,          -- Regel der Eskalation
    subject_id           INTEGER,                   -- NULL = systemisch
    reason               TEXT    NOT NULL,          -- Pflichttext (SENSIBEL)
    days_inactive_at_ack INTEGER,                   -- Stand bei Quittierung
    acknowledged_by      INTEGER NOT NULL REFERENCES person(id),
    acknowledged_at      INTEGER NOT NULL,
    audit_seq            INTEGER NOT NULL REFERENCES audit_log(seq),
    is_active            INTEGER NOT NULL DEFAULT 1
                         CHECK(is_active IN (0, 1)),
    revoked_at           INTEGER,
    revoked_by           INTEGER REFERENCES person(id),
    revoke_reason        TEXT,                      -- Pflichttext (SENSIBEL)
    revoke_audit_seq     INTEGER REFERENCES audit_log(seq)
)
"""

# Nachschlag "gibt es zu dieser Regel an diesem Fall einen gueltigen Vermerk?"
# — der Zugriffsweg der Lesesicht und der Kollisionspruefung im Repo.
_IDX_KEY = (
    "ix_escalation_ack_key",
    "CREATE INDEX IF NOT EXISTS ix_escalation_ack_key "
    "ON escalation_ack (rule_code, subject_id, is_active)",
)
# "Was hat diese Person quittiert?" — Aufsicht ueber die Aufsicht.
_IDX_BY = (
    "ix_escalation_ack_by",
    "CREATE INDEX IF NOT EXISTS ix_escalation_ack_by "
    "ON escalation_ack (acknowledged_by, acknowledged_at)",
)

_INDICES = (_IDX_KEY, _IDX_BY)
_TABLES = ("escalation_ack",)

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren, m005-Prinzip) ---
# EIGENE Faehigkeit neben 'escalation.view' (M026): wer Eskalationen SEHEN
# darf, darf damit noch lange nicht fuer die Behoerde festhalten, dass etwas
# gesehen und veranlasst wurde. Ein Lese-Grant darf nie ein Schreibrecht
# mitbringen.
_SEED_CAPS = (
    ("escalation.ack", "Eskalationen quittieren",
     "Eine Eskalation mit Pflichtbegruendung als gesehen vermerken und einen "
     "Vermerk mit Pflichtgrund widerrufen (auditiert; die Eskalation bleibt "
     "sichtbar — quittieren ist kein Erledigen)."),
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
    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M027: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    done = (all(_table_exists(con, t) for t in _TABLES)
            and all(_index_exists(con, ix) for ix, _ in _INDICES)
            and all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS))
    if done:
        logger.info("M027: escalation_ack bereits vorhanden — No-op.")
        return

    con.execute(_DDL_ESCALATION_ACK)
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
            raise RuntimeError("M027: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M027: Index '%s' fehlt nach up()." % ix)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M027: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M027: escalation_ack + %d Indizes angelegt, Faehigkeit %s "
                "geseedet.", len(_INDICES),
                ", ".join(c for c, _l, _d in _SEED_CAPS))
