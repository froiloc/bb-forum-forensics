# =============================================================================
# management/migrations/coordinator/m031_limitation_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (Build 524)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer den Fristen-/Verjaehrungs-Monitor (AP-3A / Idee 32):
#     limitation.view — Faelle mit ihrer Verjaehrungsfrist lesen.
#   Muster M014/M021/M026/M028/M029/M030 (reiner Capability-Seed). Die Werte
#   sind eine EINGEFRORENE Kopie des Katalogs (management/rbac/catalog.py) —
#   NIE importieren (m005-Prinzip: eine angewandte Migration darf ihr
#   Laufzeitverhalten nie aendern).
#
# WARUM EIN EIGENES RECHT UND NICHT 'ops.view' ODER 'dashboard.view':
#   Die Sicht zeigt zwei Dinge zusammen, die keine der bestehenden Sichten
#   zusammen zeigt: eine LISTE VON FAELLEN MIT BESCHULDIGTEN-KONTONAMEN und
#   eine RECHTLICHE EINSCHAETZUNG mit unumkehrbarer Folge. Wer die Anlage
#   betreut (ops.view: Backup, Speicher, Integritaet), braucht beides nicht;
#   wer das Ampel-Dashboard liest (dashboard.view), bekommt damit noch keine
#   Fristbewertung. Eine Wiederverwendung waere hier keine Sparsamkeit, sondern
#   ein Zweckbindungsverstoss — dieselbe Begruendung wie bei retention.view
#   (M030). Die Gegenrichtung (Wiederverwendung von crossref.view in M022) war
#   richtig, weil es dort dieselbe Erkenntnisart betraf.
#
# NICHT SCOPE-BEHAFTET: Fristenkontrolle ist eine Leitungsaufgabe. Auf 'eigene'
#   verengt haette die Sicht genau die Faelle nicht gezeigt, um derentwillen es
#   sie gibt — die unzugewiesenen, die niemand anfasst und bei denen die Frist
#   trotzdem laeuft (Analogie escalation.view, M026).
#
# MIT DIESEM RECHT IST KEINE FRISTAUSSAGE VERBUNDEN, SOLANGE DER PARAMETERSATZ
#   NICHT BESTAETIGT IST. Das Recht oeffnet die Sicht; ob sie eine Ampel zeigt
#   oder den Grund ihres Schweigens, entscheidet allein
#   management/deadlines/limitation_params.json ('bestaetigt').
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (default-deny). Operativ, Empfehlung fuer die Chef-Ermittlerin:
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor --capability limitation.view --actor <SYSUSER>
#
# IDEMPOTENZ: INSERT OR IGNORE + Guard + Inline-Verifikation. NUR
# coordinator.db, rein additiv. KEINE Datenaenderung, KEIN Tabellenumbau — der
# Migrationsvorbehalt ab 01.07.2026 ist nicht beruehrt (es entstehen keine
# Ermittlerdaten).
# Version: v0.8.524 · Build: 524 · 2026-07-25
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 31
NAME = "RBAC-Seed Fristen-/Verjaehrungs-Monitor (limitation.view)"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("limitation.view", "Verjaehrungsfristen sehen",
     "Faelle mit der rechnerischen Verjaehrungsfrist (§§ 78 ff. StGB) lesen. "
     "Die Sicht stellt KEINE Verjaehrung fest und ist ohne bestaetigten "
     "Parametersatz stumm."),
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
            "M031: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    if all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS):
        logger.info("M031: Faehigkeiten bereits vorhanden — No-op.")
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
                "M031: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M031: Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
