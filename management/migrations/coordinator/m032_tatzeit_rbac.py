# =============================================================================
# management/migrations/coordinator/m032_tatzeit_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A, Build 533)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Erfassung des Tatzeitraums:
#     tatzeit.edit — zu einer Annotation den festgestellten Tatzeitraum
#                    erfassen, korrigieren oder zuruecknehmen.
#   Muster M014/M021/M026/M028/M029/M030/M031 (reiner Capability-Seed). Die
#   Werte sind eine EINGEFRORENE Kopie des Katalogs
#   (management/rbac/catalog.py) — NIE importieren (m005-Prinzip: eine
#   angewandte Migration darf ihr Laufzeitverhalten nie aendern).
#
# WARUM EIN EIGENES RECHT UND NICHT 'results.edit':
#   'results.edit' erfasst eine ermittlerische BEWERTUNG (Konfidenz und
#   Qualitaet je Bewertungskriterium, M011/M018). 'tatzeit.edit' erfasst eine
#   TATSACHENANGABE, aus der eine Verjaehrungsfrist gerechnet wird — und deren
#   Ablauf ist nicht heilbar. Das sind verschiedene Erkenntnisarten mit
#   verschiedener Tragweite. Eine Wiederverwendung waere hier ein
#   Zweckbindungsverstoss, keine Sparsamkeit; dieselbe Abgrenzung wie bei
#   retention.view (M030) und limitation.view (M031). Die Gegenrichtung
#   (Wiederverwendung von crossref.view in M022) war richtig, weil es dort
#   dieselbe Erkenntnisart betraf.
#
# WARUM NUR EIN RECHT UND KEIN PAAR view/edit:
#   Die Tatzeit steht IN der Annotation. Wer die Annotation sehen darf, sieht
#   sie mit. Ein eigenes Leserecht wuerde eine Trennung behaupten, die die
#   Oberflaeche nicht abbilden kann — und ein Recht, das man nicht durchsetzen
#   kann, ist schlimmer als keines, weil man sich darauf verlaesst.
#
# NICHT SCOPE-BEHAFTET, und hier aus einem anderen Grund als bei den
#   Leitungsrechten: Der forensische Server hat zu jedem Zeitpunkt GENAU EINEN
#   Fall geoeffnet; die subject_id kommt aus dem ResolvedContext und nie aus
#   dem Rumpf der Anfrage (Muster forensic_api/results_endpoint.py:20-27, dort
#   als Festlegung (1) dokumentiert). Ein Scope 'eigene' waere die wirkungslose
#   Doppelung einer Schranke, die bereits STRUKTURELL steht.
#
# MIT DIESEM RECHT IST KEINE FRISTAUSSAGE VERBUNDEN. Es erlaubt das ERFASSEN
#   einer Tatzeit. Ob daraus eine Frist gerechnet wird, entscheidet allein
#   management/deadlines/limitation_params.json ('bestaetigt') — und die
#   Auswertung im Fristenmonitor kommt erst mit Build 535.
#
#   Die role->capability-ZUWEISUNG (Grant) ist NICHT Teil dieses Seeds
#   (default-deny). Operativ, Empfehlung fuer die Chef-Ermittlerin:
#     python -m management.rbac.rbac_admin grant \
#            --role investigator --capability tatzeit.edit --actor <SYSUSER>
#     python -m management.rbac.rbac_admin grant \
#            --role supervisor   --capability tatzeit.edit --actor <SYSUSER>
#
# IDEMPOTENZ: INSERT OR IGNORE + Guard + Inline-Verifikation. NUR
# coordinator.db, rein additiv. KEINE Datenaenderung, KEIN Tabellenumbau — der
# Migrationsvorbehalt ab 01.07.2026 ist nicht beruehrt (es entstehen keine
# Ermittlerdaten).
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 32
NAME = "RBAC-Seed Tatzeiterfassung (tatzeit.edit)"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("tatzeit.edit", "Tatzeitraum erfassen",
     "Zu einer Annotation den festgestellten Tatzeitraum (Beginn und/oder "
     "Ende) erfassen, korrigieren oder zuruecknehmen. Append-only mit Beleg "
     "in der Beweismitteldatenbank."),
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
            "M032: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    if all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS):
        logger.info("M032: Faehigkeiten bereits vorhanden — No-op.")
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
                "M032: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M032: Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
