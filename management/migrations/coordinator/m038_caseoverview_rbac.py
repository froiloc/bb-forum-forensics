# =============================================================================
# management/migrations/coordinator/m038_caseoverview_rbac.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Rechtetrennung (Build 698)
# =============================================================================
# Zweck:
#   RBAC-Seed fuer die Falluebersicht:
#     caseoverview.view — die Falltabelle sehen (Sicht, Kachel, Fallsuche).
#   Zusaetzlich wird der TEXT von 'dashboard.view' berichtigt, weil dieses
#   Recht mit diesem Vorgang auf das Kachel-Dashboard verengt wird.
#
#   Vorgang: 60fe72fb-b0bb-4c29-9a80-3ac1996bba78
#   Muster M014/M021/M026/M028/M029/M030/M031 (reiner Capability-Seed). Die
#   Werte sind eine EINGEFRORENE Kopie des Katalogs
#   (management/rbac/catalog.py) — NIE importieren (m005-Prinzip: eine
#   angewandte Migration darf ihr Laufzeitverhalten nie aendern).
#
# ── WARUM EIN EIGENES RECHT ─────────────────────────────────────────────────
#
#   Bis Build 696 trug 'dashboard.view' ZWEI Dinge. Als das Dashboard AUS der
#   Falltabelle bestand, war das dasselbe Recht fuer dieselbe Sache. Seit dem
#   Umbau auf das Kachelsystem ist das Dashboard ein RAHMEN, dessen Inhalt
#   jede Kachel ueber ihr eigenes Recht mitbringt (siehe
#   management/viewprefs/viewpref_katalog.py: escalation.view, ops.view,
#   limitation.view ... je Kachel eines). Die Falltabelle war die einzige
#   Kachel ohne eigenes Recht — sie lief auf dem Recht des Rahmens mit.
#
#   Damit bekam jede Person, die den Ueberblick oeffnen darf, die
#   vollstaendige Fallliste mit Beschuldigten-Kontonamen ungefragt dazu. Das
#   ist eine Zweckbindungsfrage und keine Aufraeumarbeit — dieselbe
#   Begruendung, mit der M030 (retention.view) und M031 (limitation.view)
#   jeweils ein eigenes Recht bekommen haben statt 'dashboard.view'
#   mitzubenutzen.
#
# ── WARUM DER TEXT VON 'dashboard.view' MITGEAENDERT WIRD ───────────────────
#
#   M006 hat ihn als "Ampel-Dashboard sehen" / "Falluebersicht mit Ampel und
#   Kennzahlen lesen" eingefroren. Nach dieser Trennung beschreibt dieser Satz
#   GENAU DAS, was das Recht nicht mehr kann. Die RBAC-Matrix (Sicht
#   'policy.view') zeigt diese Texte woertlich an; wer dort Rechte vergibt,
#   entscheidet nach ihnen. Ein stehengelassener Text waere also keine
#   Kleinigkeit, sondern eine Falschangabe an der Stelle, an der ueber Zugang
#   entschieden wird.
#
#   GEAENDERT WIRD AUSSCHLIESSLICH BESCHRIFTUNG UND BESCHREIBUNG. Der Code
#   'dashboard.view' bleibt, alle Grants darauf bleiben unangetastet, kein
#   Zugang aendert sich durch diese Migration.
#
# ── WAS DIESE MIGRATION AUSDRUECKLICH NICHT TUT: GRANTS ─────────────────────
#
#   Sie vergibt das neue Recht an KEINE Rolle. Das ist keine Nachlaessigkeit,
#   sondern die Bauregel aus M006: rbac_grant.audit_seq ist NOT NULL, jeder
#   Grant traegt den Beleg seiner Vergabe. Eine Migration hat keinen Akteur
#   und keinen Beleg — ein von ihr geschriebener Grant waere ein Zugang, den
#   niemand vergeben hat.
#
#   FOLGE, UND SIE IST WICHTIG: Unmittelbar nach dieser Migration sieht
#   NIEMAND mehr die Falluebersicht — auch nicht, wer heute 'dashboard.view'
#   besitzt. Der Zustand ist gewollt sichtbar und nicht still: die Sicht
#   verschwindet aus der Navigation, die Kachel aus dem Ueberblick, und
#   /api/overview antwortet mit 403 unter Nennung des fehlenden Rechts.
#
#   DIE UEBERNAHME DER BESTEHENDEN RECHTE IST EIN EIGENER, AUDITIERTER LAUF:
#     python -m management.rbac.rbac_admin migrate-grants \
#            --from dashboard.view --to caseoverview.view --probe   # Probelauf
#     python -m management.rbac.rbac_admin migrate-grants \
#            --from dashboard.view --to caseoverview.view --actor <SYSUSER>
#   Er uebernimmt je Rolle den Scope 1:1 und schreibt je Grant einen eigenen
#   Beleg. Er gehoert in DASSELBE Wartungsfenster wie das Einspielen.
#
# ── MIGRATIONSVORBEHALT (ab 01.07.2026) ─────────────────────────────────────
#
#   NUR coordinator.db. evidence_<uid>.db, forensic_<uid>.db und
#   assets_<uid>.db werden NICHT beruehrt. Es gehen keine Ermittlerdaten
#   verloren: geschrieben werden eine Katalogzeile und zwei Textfelder einer
#   bestehenden Katalogzeile. Kein Tabellenumbau, kein executescript().
#
#   RUECKWEG: 'DELETE FROM rbac_capability WHERE code=''caseoverview.view''"
#   ist moeglich, solange kein Grant darauf zeigt; die Textberichtigung an
#   dashboard.view laesst sich mit den hier festgehaltenen Altwerten
#   (_ALT_DASHBOARD) woertlich zuruecknehmen. Beides ist Handarbeit unter
#   Aufsicht und kein Bestandteil dieser Migration.
#
# IDEMPOTENZ: INSERT OR IGNORE + Guards + Inline-Verifikation.
# Version: v0.8.698 · Build: 698 · 2026-08-11
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 38
NAME = "RBAC-Seed Falluebersicht (caseoverview.view) + Text dashboard.view"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("caseoverview.view", "Falluebersicht sehen",
     "Die Falltabelle mit Ampel, Prioritaet und Zuweisung lesen — "
     "als Sicht, als Kachel des Ueberblicks und ueber die Fallsuche "
     "der Kommandopalette. Scope 'eigene' beschraenkt auf die "
     "zugewiesenen Faelle."),
)

# --- Textberichtigung an 'dashboard.view' (ebenfalls eingefroren) ------------
#  _ALT_DASHBOARD haelt fest, was M006 gesetzt hat. Es steht hier NICHT zur
#  Zierde: die Migration aendert den Text nur, wenn sie GENAU diesen Altwert
#  vorfindet. Hat ihn jemand von Hand angefasst, bleibt seine Fassung stehen
#  und der Fall wird gemeldet — eine Migration, die fremde Aenderungen
#  ueberschreibt, macht aus einer Berichtigung einen Datenverlust.
_ALT_DASHBOARD = (
    "Ampel-Dashboard sehen",
    "Falluebersicht mit Ampel und Kennzahlen lesen.",
)
_NEU_DASHBOARD = (
    "Kachel-Dashboard sehen",
    "Den Ueberblick mit seinen Kacheln oeffnen. Das Recht traegt "
    "den RAHMEN, nicht den Inhalt: welche Kacheln erscheinen, "
    "entscheidet je Kachel deren eigenes Recht.",
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
            "M038: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    now = int(time.time())

    # --- (a) Das neue Recht ------------------------------------------------
    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now),
        )

    # --- (b) Der berichtigte Text an 'dashboard.view' -----------------------
    row = con.execute(
        "SELECT label, description FROM rbac_capability WHERE code=?",
        ("dashboard.view",)).fetchone()
    if row is None:
        raise RuntimeError(
            "M038: 'dashboard.view' fehlt — M006 ist nicht angewandt oder "
            "das Recht wurde entfernt.")
    vorgefunden = (row[0], row[1])
    if vorgefunden == _ALT_DASHBOARD:
        con.execute(
            "UPDATE rbac_capability SET label=?, description=? WHERE code=?",
            (_NEU_DASHBOARD[0], _NEU_DASHBOARD[1], "dashboard.view"))
        logger.info("M038: Text von 'dashboard.view' berichtigt.")
    elif vorgefunden == _NEU_DASHBOARD:
        logger.info("M038: Text von 'dashboard.view' bereits berichtigt "
                    "— No-op.")
    else:
        # KEIN Abbruch: der Seed des neuen Rechts ist davon unabhaengig und
        # soll nicht an einer Textfrage scheitern. Aber auch kein Schweigen —
        # wer den Text angepasst hat, muss erfahren, dass er jetzt von der
        # Katalogfassung abweicht (Grundregel 1).
        logger.warning(
            "M038: 'dashboard.view' traegt einen fremden Text und bleibt "
            "UNVERAENDERT. Vorgefunden: %r / %r. Erwartet war die Fassung aus "
            "M006. Der Text weicht damit von management/rbac/catalog.py ab — "
            "bitte von Hand angleichen.", vorgefunden[0], vorgefunden[1])

    # --- (c) Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) --
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M038: Faehigkeit '%s' fehlt nach dem Seed." % code)

    # Die Grants bleiben ausdruecklich leer — siehe Kopf. Belegt statt
    # angenommen: haette diese Migration versehentlich einen Grant erzeugt,
    # faende er sich hier.
    n = con.execute(
        "SELECT COUNT(*) FROM rbac_grant WHERE capability_code=?",
        ("caseoverview.view",)).fetchone()[0]
    if n != 0:
        raise RuntimeError(
            "M038: 'caseoverview.view' traegt bereits %d Grant(s). Diese "
            "Migration vergibt keine — Herkunft klaeren." % n)

    logger.info("M038: Faehigkeit 'caseoverview.view' geseedet (ohne Grants). "
                "Uebernahme der bestehenden Rechte: "
                "'rbac_admin migrate-grants --from dashboard.view "
                "--to caseoverview.view'.")
