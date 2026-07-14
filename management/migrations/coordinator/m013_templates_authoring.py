# =============================================================================
# management/migrations/coordinator/m013_templates_authoring.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# Vermaehlung B6xB7 — SF-4 (Build 420): RBAC-Seed fuer die Authoring-Werkzeuge
# =============================================================================
# Zweck:
#   Seedet in coordinator.db die neue Rolle 'template_editor' und die
#   Faehigkeit 'templates.edit' (Wahrheitsquelle: management/rbac/catalog.py).
#   Damit ist verify_catalog_present() nach dem Hinzufuegen zum Code-Katalog
#   wieder erfuellt (Code ⊆ DB), und die spaeteren Authoring-Werkzeuge W1/W2/W3
#   (Baustein-Module, Platzhalter/Queries, Dokumentvorlagen) koennen auf
#   'templates.edit' gaten.
#
#   Die role->capability-ZUWEISUNG (Grant mit Scope) ist NICHT Teil dieses
#   Seeds — sie wird wie ueblich auditiert ueber die policy_admin-CLI vergeben
#   (default-deny; Beleg: catalog.py, Bauplan B7 v1.1 §11.3).
#
# Idempotent: INSERT OR IGNORE; wiederholtes up() ist ein No-op.
# Forward-only (kein down): der Katalog waechst, er wird nie zurueckgebaut
#   (eingefrorenes Vokabular; ein spaeterer Grant koennte sonst ins Leere zeigen).
#
# Version: v0.7.420 · Build: 420 · 2026-07-14
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 13
NAME = "RBAC-Seed: Rolle template_editor + Recht templates.edit (Authoring)"

# (code, label) — deckungsgleich mit catalog.ROLES.
_SEED_ROLES = (
    ("template_editor", "Redakteur:in (Berichtsvorlagen/Bausteine)"),
)

# (code, label, description) — deckungsgleich mit catalog.CAPABILITIES.
_SEED_CAPS = (
    ("templates.edit", "Berichtsvorlagen/Bausteine pflegen",
     "Baustein-Module, Platzhalter/Queries und Dokumentvorlagen in "
     "templates.db anlegen und pflegen (auditiert)."),
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
        logger.info("M013: template_editor + templates.edit bereits vorhanden "
                    "— No-op.")
        return

    # Vorbedingung: M006 (rbac_role/rbac_capability) muss angewandt sein. Fehlt
    # sie, ist das ein Aufbaufehler und KEIN Grund, den Seed still zu ueberspringen.
    if not (_table_exists(con, "rbac_role")
            and _table_exists(con, "rbac_capability")):
        raise RuntimeError(
            "M013: rbac_role/rbac_capability fehlt — M006 ist nicht angewandt. "
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
            raise RuntimeError("M013: Rolle '%s' fehlt nach dem Seed." % code)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M013: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M013: Rolle(n) %s und Faehigkeit(en) %s geseedet.",
                ", ".join(c for c, _l in _SEED_ROLES),
                ", ".join(c for c, _l, _d in _SEED_CAPS))
