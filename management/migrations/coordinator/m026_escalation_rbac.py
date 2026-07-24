# =============================================================================
# management/migrations/coordinator/m026_escalation_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Eskalationen (Build 515)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Eskalations-Sicht (AP-2G / Idee 23):
#     escalation.view — belegte Eskalationen aus dem Fallzustand lesen
#                       (ueberfaellige rote Faelle, unbearbeitete offene
#                       Faelle, systemischer Rueckstau).
#   Muster M014/M021 (reiner Capability-Seed). Die Werte sind eine
#   EINGEFRORENE Kopie des Katalogs (management/rbac/catalog.py) — NIE
#   importieren (m005-Prinzip: eine angewandte Migration aendert ihr
#   Laufzeitverhalten nicht, sonst Nichtdeterminismus trotz gleicher
#   Checksumme).
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (default-deny). Operativ, Empfehlung fuer die Chef-Ermittlerin:
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor --capability escalation.view --actor <SYSUSER>
#
#   WARUM NUR EINE FAEHIGKEIT: der auditierte SCHREIBpfad (Quittierung einer
#   Eskalation) ist ausdruecklich NICHT Teil dieses Builds. Er kommt mit
#   seiner eigenen Migration und seiner eigenen Faehigkeit, damit ein
#   Lese-Grant nie versehentlich ein Schreibrecht mitbringt.
#
# IDEMPOTENZ: INSERT OR IGNORE + Guard. NUR coordinator.db, rein additiv.
# KEINE Datenaenderung, KEIN Tabellenumbau — der Migrationsvorbehalt ab
# 01.07.2026 ist nicht beruehrt (es entstehen keine Ermittlerdaten).
# Version: v0.8.515 · Build: 515 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 26
NAME = "RBAC-Seed Eskalationen (escalation.view)"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("escalation.view", "Eskalationen sehen",
     "Belegte Eskalationen aus dem Fallzustand lesen (ueberfaellige rote "
     "Faelle, unbearbeitete offene Faelle, systemischer Rueckstau) — "
     "auswertend, nicht fallbezogen scope-behaftet."),
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
            "M026: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    if all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS):
        logger.info("M026: Faehigkeiten bereits vorhanden — No-op.")
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
                "M026: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M026: Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
