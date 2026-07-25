# =============================================================================
# management/migrations/coordinator/m030_retention_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Governance (Build 521)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Sicht "Aufbewahrungsfristen" (AP-2G / Idee 29):
#     retention.view — Faelle lesen, deren Aufbewahrungsfrist ueberschritten
#                      ist (PRUEFVORSCHLAG).
#   Muster M014/M021/M026/M028/M029 (reiner Capability-Seed). Die Werte sind
#   eine EINGEFRORENE Kopie des Katalogs (management/rbac/catalog.py) — NIE
#   importieren (m005-Prinzip).
#
# WARUM EIN EIGENES RECHT UND NICHT 'ops.view':
#   Die uebrigen ops.view-Sichten zeigen den Zustand der ANLAGE (Backup,
#   Speicherplatz, Integritaet der Audit-Kette). DIESE Sicht zeigt eine LISTE
#   VON FAELLEN mit Beschuldigten-Kontonamen. Wer die Anlage betreut, braucht
#   diese Namen nicht — eine Wiederverwendung von ops.view waere hier keine
#   Sparsamkeit, sondern ein Zweckbindungsverstoss. (Die Gegenrichtung, das
#   Wiederverwenden von crossref.view in M022, war richtig, weil es dort
#   dieselbe Erkenntnisart betraf.)
#
# MIT DIESEM RECHT IST KEIN LOESCHEN VERBUNDEN. Es gibt im gesamten Werkzeug
#   keinen Weg, aus dieser Sicht eine Loeschung auszuloesen. Das ist keine
#   fehlende Bequemlichkeit, sondern Absicht: das Loeschen von Beweismitteln
#   ist eine Governance-Entscheidung ausserhalb dieses Systems.
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (default-deny). Operativ, Empfehlung fuer die Chef-Ermittlerin:
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor --capability retention.view --actor <SYSUSER>
#
# IDEMPOTENZ: INSERT OR IGNORE + Guard. NUR coordinator.db, rein additiv.
# KEINE Datenaenderung, KEIN Tabellenumbau — der Migrationsvorbehalt ab
# 01.07.2026 ist nicht beruehrt (es entstehen keine Ermittlerdaten).
# Version: v0.8.521 · Build: 521 · 2026-07-24
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 30
NAME = "RBAC-Seed Aufbewahrungsfristen (retention.view)"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("retention.view", "Aufbewahrungsfristen sehen",
     "Faelle lesen, deren Aufbewahrungsfrist ueberschritten ist "
     "(Pruefvorschlag). Loeschen ist damit AUSDRUECKLICH NICHT verbunden — es "
     "gibt dafuer keinen Weg im Werkzeug."),
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
            "M030: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    if all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS):
        logger.info("M030: Faehigkeiten bereits vorhanden — No-op.")
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
                "M030: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M030: Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
