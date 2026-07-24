# =============================================================================
# management/migrations/coordinator/m029_handover_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (Build 520)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Sicht "Uebergabe-Protokoll" (AP-2G / Idee 30):
#     handover.view — nachvollziehen, wer wann welchen Fall an wen uebergeben
#                     hat (rekonstruiert aus der Audit-Kette; rein lesend).
#   Muster M014/M021/M026/M028 (reiner Capability-Seed). Die Werte sind eine
#   EINGEFRORENE Kopie des Katalogs (management/rbac/catalog.py) — NIE
#   importieren (m005-Prinzip).
#
#   KEIN neues Register, KEINE neue Tabelle: das Protokoll wird aus den
#   bereits vorhandenen, unveraenderlichen CASE_ASSIGNED-Belegen des
#   audit_log rekonstruiert. Es gibt damit nichts, was nachtraeglich
#   'aufgeraeumt' werden koennte — und es kann nicht von der Fallakte
#   abweichen. Diese Migration seedet deshalb ausschliesslich das Recht.
#
#   NICHT scope-behaftet (Begruendung im Katalog und in management_app):
#   ein Protokoll ueber UEBERGABEN handelt von der Beziehung zwischen
#   Personen; auf die eigenen Eintraege verengt entstuende ein Protokoll MIT
#   LUECKEN, das vollstaendig aussieht.
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (default-deny). Operativ, Empfehlung fuer die Chef-Ermittlerin:
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor --capability handover.view --actor <SYSUSER>
#
# IDEMPOTENZ: INSERT OR IGNORE + Guard. NUR coordinator.db, rein additiv.
# KEINE Datenaenderung, KEIN Tabellenumbau — der Migrationsvorbehalt ab
# 01.07.2026 ist nicht beruehrt (es entstehen keine Ermittlerdaten).
# Version: v0.8.520 · Build: 520 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 29
NAME = "RBAC-Seed Uebergabe-Protokoll (handover.view)"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("handover.view", "Uebergabe-Protokoll sehen",
     "Nachvollziehen, wer wann welchen Fall an wen uebergeben hat "
     "(rekonstruiert aus der Audit-Kette; rein lesend)."),
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
            "M029: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    if all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS):
        logger.info("M029: Faehigkeiten bereits vorhanden — No-op.")
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
                "M029: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M029: Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
