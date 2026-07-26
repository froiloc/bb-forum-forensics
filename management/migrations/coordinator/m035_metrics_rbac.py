# =============================================================================
# management/migrations/coordinator/m035_metrics_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C (Build 542)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Ermittler-Metriken:
#     metrics.view — die Kennzahlen zur Auswertungsqualitaet lesen.
#   Muster M014/M021/M026/.../M033 (reiner Capability-Seed). Die Werte sind
#   eine EINGEFRORENE Kopie des Katalogs (management/rbac/catalog.py) — NIE
#   importieren (m005-Prinzip: eine angewandte Migration darf ihr
#   Laufzeitverhalten nie aendern).
#
# WARUM EIN EIGENES RECHT UND NICHT 'qs.view':
#   Die QS-Stichprobe zeigt ein PRUEFERGEBNIS ZU EINEM FALL, mit Namen der
#   pruefenden Person und einer Begruendung im Klartext. Die Metriken zeigen
#   AGGREGATE ueber viele Faelle. Das eine ist eine Einzelfallauskunft, das
#   andere ein Lagebild — wer das Lagebild sehen darf, darf damit noch nicht
#   die Begruendung lesen, mit der eine Kollegin die Arbeit einer anderen
#   bewertet hat. Dieselbe Abgrenzung wie limitation.view (M031) gegen
#   matrix.view (M033).
#
# WARUM AUCH NICHT 'stats.export_sta':
#   Jenes Recht steht fuer den STATISTIKEXPORT an StA und Fuehrung. Die
#   Metriken sind eine INNENSICHT der Dienststelle auf ihre eigene
#   Auswertungsqualitaet; sie gehen ausdruecklich nicht an die StA und sollen
#   nicht ueber dasselbe Recht mit hinauswandern.
#
# NICHT SCOPE-BEHAFTET: ein Lagebild ueber den eigenen Arbeitsvorrat waere
#   keines. Die Metriken enthalten dafuer KEINEN Personenbezug — sie
#   aggregieren ueber FAELLE, nicht ueber Personen
#   (management/metrics/metrics_repo.py, Kopf).
#
# ZWECKBINDUNG, DIE AN DIESEM RECHT HAENGT: AUSWERTUNGSQUALITAET, KEIN
#   MITARBEITER-BEWERTUNGSINSTRUMENT. Sie faehrt in jeder Antwort mit, und ein
#   Test haelt die Antwortschluessel gegen eine Verbotsliste.
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (default-deny). Operativ, Empfehlung fuer die Chef-Ermittlerin:
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor --capability metrics.view --actor <SYSUSER>
#
# IDEMPOTENZ: INSERT OR IGNORE + Guard + Inline-Verifikation. NUR
# coordinator.db, rein additiv. KEINE Datenaenderung, KEIN Tabellenumbau — der
# Migrationsvorbehalt ab 01.07.2026 ist nicht beruehrt (es entstehen keine
# Ermittlerdaten).
#
# NUMMERNKREIS: m035 stammt aus dem Kreis der Instanz A (m033-m039), festgelegt
# in management/Parallelbetrieb_Welle3_v0_1.md §5. Der Parallelbetrieb ist
# seit dem 2026-07-26 beendet; die Kette lautet nach Build 544 durchgehend
# 33, 34, 35, 36.
# Version: v0.8.542 · Build: 542 · 2026-07-26
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 35
NAME = "RBAC-Seed Ermittler-Metriken (metrics.view)"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("metrics.view", "Ermittler-Metriken sehen",
     "Kennzahlen zum Zustand der Auswertung und zur Verteilung der Arbeit "
     "lesen. AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT: "
     "keine Leistungsdaten, keine Rangfolge zwischen Personen."),
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
            "M035: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    if all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS):
        logger.info("M035: Faehigkeiten bereits vorhanden — No-op.")
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
                "M035: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M035: Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
