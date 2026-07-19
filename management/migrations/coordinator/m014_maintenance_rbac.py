# =============================================================================
# management/migrations/coordinator/m014_maintenance_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Sequenz A-D)
# =============================================================================
# Zweck:
#   Seedet in coordinator.db die neue Rolle 'maintenance' und die Faehigkeit
#   'wartung.durchfuehren' (Wahrheitsquelle: management/rbac/catalog.py). Damit
#   ist verify_catalog_present() nach dem Hinzufuegen zum Code-Katalog wieder
#   erfuellt (Code subset DB), und die Wartungs-Werkzeuge (enter/exit/kill)
#   koennen auf 'wartung.durchfuehren' gaten.
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (Mechanismus B, mc 2026-07-19): sie wird wie ueblich auditiert ueber die
#   policy_admin-CLI vergeben — an 'maintenance' UND 'supervisor', Scope NULL:
#     python -m management.rbac.rbac_admin grant \
#            --role maintenance --capability wartung.durchfuehren --actor <SYSUSER>
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor  --capability wartung.durchfuehren --actor <SYSUSER>
#   Bis dieser Grant gesetzt ist, verweigern die Werkzeuge JEDEM (default-deny).
#
# Idempotent: INSERT OR IGNORE; wiederholtes up() ist ein No-op.
# Forward-only (kein down): der Katalog waechst, er wird nie zurueckgebaut.
#
# Version: v0.7.439 · Build: 439 · 2026-07-19
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 14
NAME = "RBAC-Seed: Rolle maintenance + Recht wartung.durchfuehren (Wartungsmodus)"

# (code, label) — deckungsgleich mit catalog.ROLES.
_SEED_ROLES = (
    ("maintenance", "Wartung / kontrollierter Betriebsstillstand"),
)

# (code, label, description) — deckungsgleich mit catalog.CAPABILITIES.
_SEED_CAPS = (
    ("wartung.durchfuehren", "Wartung durchfuehren",
     "Wartungsfenster setzen/aufheben (enter/exit) und laufende "
     "Wartungs-Test-Server beenden (kill). Nicht fallbezogen."),
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _role_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_role WHERE code=?", (code,)).fetchone() is not None


def _cap_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_capability WHERE code=?",
        (code,)).fetchone() is not None


def up(con: sqlite3.Connection) -> None:
    done = (all(_role_exists(con, c) for c, _l in _SEED_ROLES)
            and all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS))
    if done:
        logger.info("M014: maintenance + wartung.durchfuehren bereits vorhanden "
                    "— No-op.")
        return

    # Vorbedingung: M006 (rbac_role/rbac_capability) muss angewandt sein. Fehlt
    # sie, ist das ein Aufbaufehler und KEIN Grund, den Seed still zu ueberspringen.
    if not (_table_exists(con, "rbac_role")
            and _table_exists(con, "rbac_capability")):
        raise RuntimeError(
            "M014: rbac_role/rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    now = int(time.time())
    for code, label in _SEED_ROLES:
        con.execute(
            "INSERT OR IGNORE INTO rbac_role (code, label, created_at) "
            "VALUES (?, ?, ?)", (code, label, now),
        )
    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now),
        )

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    for code, _l in _SEED_ROLES:
        if not _role_exists(con, code):
            raise RuntimeError("M014: Rolle '%s' fehlt nach dem Seed." % code)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M014: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M014: Rolle(n) %s und Faehigkeit(en) %s geseedet.",
                ", ".join(c for c, _l in _SEED_ROLES),
                ", ".join(c for c, _l, _d in _SEED_CAPS))
