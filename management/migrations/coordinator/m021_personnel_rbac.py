# =============================================================================
# management/migrations/coordinator/m021_personnel_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Personalverwaltung (Build 503)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Personalverwaltungs-Sicht (Bauplan Build503 §2):
#     personnel.view — Personalliste (Personen, Aktiv-Status, Flags,
#                      Rollenzuweisungen) lesen.
#     personnel.edit — Rollen-Flags setzen und Rollenzuweisungen
#                      erteilen/widerrufen (auditiert).
#   Muster M014 (reiner Capability-Seed). Die Werte sind eine EINGEFRORENE
#   Kopie des Katalogs (management/rbac/catalog.py) — NIE importieren
#   (m005-Prinzip: eine angewandte Migration aendert ihr Verhalten nicht).
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (default-deny). Operativ, Empfehlung fuer die Chef-Ermittlerin:
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor --capability personnel.view --actor <SYSUSER>
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor --capability personnel.edit --actor <SYSUSER>
#   (personnel.sync fuer den integrierten AD-Abgleich, Seed M020, ebenso.)
#
# IDEMPOTENZ: INSERT OR IGNORE + Guard. NUR coordinator.db, rein additiv.
# Version: v0.8.503 · Build: 503 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 21
NAME = "RBAC-Seed Personalverwaltung (personnel.view / personnel.edit)"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("personnel.view", "Personalliste sehen",
     "Personen mit Aktiv-Status, Rollen-Flags und Rollenzuweisungen lesen."),
    ("personnel.edit", "Personal pflegen",
     "Rollen-Flags setzen und Rollenzuweisungen erteilen/widerrufen "
     "(auditiert; Grants der Rollen-Matrix bleiben der CLI vorbehalten)."),
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _cap_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_capability WHERE code=?",
        (code,)).fetchone() is not None


def up(con: sqlite3.Connection) -> None:
    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M021: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    if all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS):
        logger.info("M021: Faehigkeiten bereits vorhanden — No-op.")
        return

    now = int(time.time())
    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now),
        )

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M021: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M021: Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
