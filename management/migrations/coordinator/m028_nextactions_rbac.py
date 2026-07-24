# =============================================================================
# management/migrations/coordinator/m028_nextactions_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fallsteuerung (Build 519)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Sicht "Naechstbeste Aktion" (AP-2F / Idee 22):
#     nextactions.view — die priorisierte, BELEGTE Arbeitsschlange lesen.
#   Muster M014/M021/M026 (reiner Capability-Seed). Die Werte sind eine
#   EINGEFRORENE Kopie des Katalogs (management/rbac/catalog.py) — NIE
#   importieren (m005-Prinzip).
#
#   SCOPE-BEHAFTET, und das ist hier der Kern: mit Scope 'eigene' sieht eine
#   Ermittlerin ihre EIGENE Schlange (Selbstorganisation), mit 'alle' die der
#   ganzen Dienststelle (Verteilung). Beides ist sinnvoll, und beides ist
#   etwas anderes. Anders als bei 'escalation.view' (M026) verengt der Scope
#   hier also nicht den Beleg, sondern bestimmt den ZWECK der Sicht.
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (default-deny). Operativ, Empfehlung fuer die Chef-Ermittlerin:
#     python -m management.rbac.rbac_admin grant \
#            --role investigator --capability nextactions.view \
#            --scope eigene --actor <SYSUSER>
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor --capability nextactions.view \
#            --scope alle --actor <SYSUSER>
#
# IDEMPOTENZ: INSERT OR IGNORE + Guard. NUR coordinator.db, rein additiv.
# KEINE Datenaenderung, KEIN Tabellenumbau — der Migrationsvorbehalt ab
# 01.07.2026 ist nicht beruehrt (es entstehen keine Ermittlerdaten).
# Version: v0.8.519 · Build: 519 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 28
NAME = "RBAC-Seed Naechstbeste Aktion (nextactions.view)"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("nextactions.view", "Naechstbeste Aktion sehen",
     "Die priorisierte Arbeitsschlange lesen (naechste sinnvolle Handlung je "
     "offenem Fall, mit belegter Begruendung). Scope 'eigene' = eigene "
     "Faelle, 'alle' = alle Faelle."),
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
            "M028: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    if all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS):
        logger.info("M028: Faehigkeiten bereits vorhanden — No-op.")
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
                "M028: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M028: Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
