# =============================================================================
# management/migrations/coordinator/m033_matrix_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3B (Build 536)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Dringlichkeits-/Erkenntnislage-Matrix:
#     matrix.view — die Priorisierungsmatrix ueber alle Faelle lesen.
#   Muster M014/M021/M026/M028/M029/M030/M031/M032 (reiner Capability-Seed).
#   Die Werte sind eine EINGEFRORENE Kopie des Katalogs
#   (management/rbac/catalog.py) — NIE importieren (m005-Prinzip: eine
#   angewandte Migration darf ihr Laufzeitverhalten nie aendern).
#
# WARUM EIN EIGENES RECHT UND NICHT 'dashboard.view':
#   Das Ampel-Dashboard zeigt den BEARBEITUNGSSTAND je Fall. Die Matrix zeigt
#   eine RANGFOLGE — sie sagt, welcher Fall als naechstes Arbeitskraft bekommen
#   soll, und sie stuetzt sich dabei auf die Verjaehrungsfrist, deren Ablauf
#   unumkehrbar ist. Das ist eine Leitungsauskunft anderer Art. Dieselbe
#   Abgrenzung wie bei retention.view (M030) und limitation.view (M031); die
#   Gegenrichtung (Wiederverwendung von crossref.view in M022) war richtig,
#   weil es dort dieselbe Erkenntnisart betraf.
#
# WARUM AUCH NICHT 'limitation.view' MITBENUTZEN:
#   Die Matrix ENTHAELT die Restlaufzeit, aber sie zeigt daneben die
#   Erkenntnislage, die Abdeckung der Bewertung und die Identitaetszuordnung —
#   also den ARBEITSSTAND fremder Faelle. Wer die Fristen sehen darf, darf
#   damit noch nicht sehen, wie weit die Kolleginnen mit ihren Faellen sind.
#
# NICHT SCOPE-BEHAFTET: eine Rangfolge ueber den eigenen Arbeitsvorrat waere
#   keine. Auf 'eigene' verengt haette die Sicht genau die Faelle nicht
#   gezeigt, um derentwillen es sie gibt — die unzugewiesenen (Analogie
#   escalation.view/M026, limitation.view/M031).
#
# MIT DIESEM RECHT IST KEINE PRIORISIERUNG VERBUNDEN. Die Matrix schreibt
#   NICHT in cases.priority (Entscheidung mc). Sie ist ein Vorschlag, den ein
#   Mensch sieht — und ihre Fristkomponente ist stumm, solange der
#   Verjaehrungs-Parametersatz nicht bestaetigt ist.
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (default-deny). Operativ, Empfehlung fuer die Chef-Ermittlerin:
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor --capability matrix.view --actor <SYSUSER>
#
# IDEMPOTENZ: INSERT OR IGNORE + Guard + Inline-Verifikation. NUR
# coordinator.db, rein additiv. KEINE Datenaenderung, KEIN Tabellenumbau — der
# Migrationsvorbehalt ab 01.07.2026 ist nicht beruehrt (es entstehen keine
# Ermittlerdaten).
#
# NUMMERNKREIS: m033 stammt aus dem Kreis der Instanz A (m033-m039), festgelegt
# in management/Parallelbetrieb_Welle3_v0_1.md §5. Instanz B benutzt m040-m049.
# Version: v0.8.536 · Build: 536 · 2026-07-26
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 33
NAME = "RBAC-Seed Dringlichkeitsmatrix (matrix.view)"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("matrix.view", "Dringlichkeitsmatrix sehen",
     "Die Rangfolge der Faelle nach Bearbeitungsdringlichkeit und "
     "Erkenntnislage lesen. Die Matrix ist ein VORSCHLAG und keine "
     "Beweiswuerdigung (§ 261 StPO); sie schreibt keine Prioritaet."),
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
            "M033: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    if all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS):
        logger.info("M033: Faehigkeiten bereits vorhanden — No-op.")
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
                "M033: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M033: Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
