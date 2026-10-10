# =============================================================================
# management/migrations/coordinator/m040_image_veil.py
# IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 771)
# =============================================================================
# Zweck:
#   Grundlage des Bildschleiers im Forenviewer (Bauplan Builds 771-773,
#   management/Bauplan_Builds771-773_Bildschleier_v0_1.md). Drei Dinge, alle in
#   coordinator.db:
#
#     1) Rolle 'researcher'     — Forschung, Bildschleier verpflichtend
#     2) Recht 'imageveil.lift' — den Bildschleier selbst schalten
#     3) Tabelle person_image_veil — die laufende Wahl je Person
#
# ── ANLASS ──────────────────────────────────────────────────────────────────
#
#   Ein Forschungsteam des LKA (zwei wissenschaftliche Mitarbeiter:innen)
#   erhaelt Zugriff auf den Forenviewer, soll die Bilder des Forums aber nicht
#   unverschleiert sehen (Alex, 09.10.2026). Alle uebrigen Ermittler:innen
#   bekommen denselben Schleier als umschaltbare Ansicht. Schutzziel ist
#   OPTISCHER SELBSTSCHUTZ, kein Zugriffsschutz.
#
# ── WAS DIESE MIGRATION AUSDRUECKLICH NICHT TUT: GRANTS ─────────────────────
#
#   Bauregel aus M006 (Begruendung in voller Laenge im Kopf von M038):
#   rbac_grant.audit_seq ist NOT NULL, jeder Grant traegt den Beleg seiner
#   Vergabe. Eine Migration hat keinen Akteur und keinen Beleg.
#
#   FOLGE, UND SIE IST GEWOLLT: Unmittelbar nach dieser Migration hat NIEMAND
#   das Recht 'imageveil.lift'. JEDE Person sieht die Forenbilder verschleiert,
#   die Schaltflaeche ist gesperrt und nennt im Tooltip den Grund. Das ist die
#   sichere Richtung und nicht still. Die Vergabe ist ein eigener, auditierter
#   Lauf im SELBEN Wartungsfenster:
#
#     python -m management.rbac.rbac_admin grant --role investigator \
#            --capability imageveil.lift --actor <SYSUSER>
#
#   Ebenso weist diese Migration die Rolle 'researcher' niemandem zu
#   (person_role.audit_seq ist ebenfalls NOT NULL). Das geschieht ueber
#   'rbac_admin assign-role' oder die Personalverwaltung.
#
# ── WARUM EINE EIGENE TABELLE (und nicht person_view_pref) ──────────────────
#
#   person_view_pref (M037) traegt CHECK("art" IN ('sicht','widget')). SQLite
#   kann einen CHECK nicht nachtraeglich aendern; ein dritter Wert verlangte
#   einen Tabellenumbau (neu anlegen, umkopieren, alte loeschen) — das ist
#   keine additive Migration mehr. Ausserdem ist jene Tabelle fuer
#   Reihenfolgen gebaut (position, UNIQUE(person_id, art, position)); ein
#   einzelnes Ein/Aus passt dort nicht hinein. Entscheidung Alex, 09.10.2026.
#
# ── EINE ZEILE JE PERSON — DIE LAUFENDE WAHL, NICHT DIE HISTORIE ────────────
#
#   person_id ist PRIMARY KEY. Die Historie steht im audit_log (Ereignis
#   'image_veil_set', Payload mit dem vollstaendigen Zustand nach der
#   Aenderung). Eine zweite Historie in dieser Tabelle waere eine zweite
#   Wahrheit, die mit der Kette streiten koennte.
#
#   KEINE ZEILE heisst: die Person hat nie umgeschaltet. Fuer Personen MIT dem
#   Recht gilt dann die Voreinstellung 'klar' (Alex, 09.10.2026: "Bei
#   normalen Ermittlern wird die Voreinstellung klar sein").
#
# ── MIGRATIONSVORBEHALT (ab 01.07.2026) ─────────────────────────────────────
#
#   NUR coordinator.db. evidence_<uid>.db, forensic_<uid>.db und
#   assets_<uid>.db werden NICHT beruehrt. REIN ADDITIV: eine Rollenzeile,
#   eine Rechtezeile, eine neue Tabelle. Keine Spalte umbenannt, keine Zeile
#   veraendert. KEIN executescript() — jede Anweisung einzeln, damit ein Fehler
#   den Runner in den ROLLBACK zwingt (Lehre aus M019).
#
# ── WAECHTER (Muster M038 seit Build 711: Delta, nicht Bestand) ─────────────
#
#   Grants auf 'imageveil.lift' und Zuweisungen von 'researcher' werden VOR
#   und NACH dem Lauf gezaehlt. Nur ein ZUWACHS bricht ab. Vorgefundene
#   Eintraege gehoeren nicht dieser Migration; sie tragen ihren eigenen Beleg
#   in audit_log und werden BENANNT (Grundregel 1), nicht bestraft.
#
# IDEMPOTENZ: INSERT OR IGNORE, CREATE TABLE IF NOT EXISTS, Spaltenpruefung.
#   Ein zweiter Lauf ist ein No-op.
# RUECKWEG: keiner in dieser Migration (forward-only). Von Hand moeglich,
#   solange kein Grant, keine Zuweisung und keine Zeile in person_image_veil
#   darauf zeigt — Handarbeit unter Aufsicht.
#
# Version: v0.8.771 · Build: 771 · 2026-10-09
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 40
NAME = "Bildschleier: Rolle researcher, Recht imageveil.lift, person_image_veil"
KIND = "additive"

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren, m005-Prinzip) ---
#   Ein Test (BS03) haelt diese Kopie gegen management/rbac/catalog.py.
_SEED_ROLES = (
    ("researcher", "Forschung (Bildschleier verpflichtend)"),
)
_SEED_CAPS = (
    ("imageveil.lift", "Bildschleier aufheben",
     "Die Bildverschleierung im Forenviewer selbst ein- und "
     "ausschalten. Ohne dieses Recht ist der Schleier immer aktiv. "
     "Wirkt nur auf die eigene Oberflaeche."),
)

_TABELLE = "person_image_veil"

_DDL = """
CREATE TABLE IF NOT EXISTS person_image_veil (
    person_id   INTEGER PRIMARY KEY REFERENCES person(id),
    -- 1 = Bilder verschleiert, 0 = unverschleiert. Die laufende Wahl.
    veiled      INTEGER NOT NULL CHECK("veiled" IN (0,1)),
    changed_at  INTEGER NOT NULL,
    audit_seq   INTEGER NOT NULL REFERENCES audit_log(seq)
)
"""

_SPALTEN = {"person_id", "veiled", "changed_at", "audit_seq"}


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _spalten(con: sqlite3.Connection, tabelle: str):
    return {r[1] for r in con.execute(
        'PRAGMA table_info("%s")' % tabelle).fetchall()}


def _role_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_role WHERE code=?", (code,)).fetchone() is not None


def _cap_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_capability WHERE code=?",
        (code,)).fetchone() is not None


def _grant_zahl(con: sqlite3.Connection, code: str) -> int:
    """ALLE Grant-Zeilen auf 'code', auch zurueckgenommene (Vergleichsmass
    vorher/nachher, keine Aussage ueber die Rechtelage — Muster M038)."""
    if not _table_exists(con, "rbac_grant"):
        return 0
    return con.execute(
        "SELECT COUNT(*) FROM rbac_grant WHERE capability_code=?",
        (code,)).fetchone()[0]


def _zuweisungs_zahl(con: sqlite3.Connection, code: str) -> int:
    """ALLE person_role-Zeilen auf 'code', auch widerrufene (wie oben)."""
    if not _table_exists(con, "person_role"):
        return 0
    return con.execute(
        "SELECT COUNT(*) FROM person_role WHERE role_code=?",
        (code,)).fetchone()[0]


def up(con: sqlite3.Connection) -> None:
    # --- Vorbedingungen: laut scheitern statt halb anlegen ------------------
    for pflicht in ("person", "audit_log", "rbac_role", "rbac_capability"):
        if not _table_exists(con, pflicht):
            raise RuntimeError(
                "M040: '%s' fehlt — fruehere Migrationen sind nicht "
                "angewandt. Reihenfolge pruefen." % pflicht)

    # Eine vorhandene Tabelle mit ANDEREN Spalten ist kein No-op, sondern ein
    # Befund (Muster M037): es wird nichts ueberschrieben.
    if _table_exists(con, _TABELLE):
        ist = _spalten(con, _TABELLE)
        if ist != _SPALTEN:
            raise RuntimeError(
                "M040: '%s' existiert bereits mit ABWEICHENDEN Spalten "
                "(vorhanden: %s / erwartet: %s). Es wird nichts "
                "ueberschrieben." % (_TABELLE, sorted(ist), sorted(_SPALTEN)))
        logger.info("M040: %s bereits vorhanden.", _TABELLE)

    # --- (0) Ausgangsstand MESSEN, bevor irgendetwas geschrieben wird ------
    grants_vorher = {c: _grant_zahl(con, c) for c, _l, _d in _SEED_CAPS}
    zuweisungen_vorher = {c: _zuweisungs_zahl(con, c) for c, _l in _SEED_ROLES}

    now = int(time.time())

    # --- (a) Rolle und Recht -----------------------------------------------
    for code, label in _SEED_ROLES:
        con.execute(
            "INSERT OR IGNORE INTO rbac_role (code, label, created_at) "
            "VALUES (?, ?, ?)", (code, label, now))
    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now))

    # --- (b) Tabelle --------------------------------------------------------
    con.execute(_DDL)

    # --- (c) Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) --
    for code, _l in _SEED_ROLES:
        if not _role_exists(con, code):
            raise RuntimeError("M040: Rolle '%s' fehlt nach dem Seed." % code)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M040: Faehigkeit '%s' fehlt nach dem Seed." % code)
    if not _table_exists(con, _TABELLE):
        raise RuntimeError("M040: %s fehlt nach dem Anlegen." % _TABELLE)
    ist = _spalten(con, _TABELLE)
    if ist != _SPALTEN:
        raise RuntimeError(
            "M040: %s hat nach dem Anlegen den falschen Spaltensatz: %s"
            % (_TABELLE, sorted(ist)))

    # Der CHECK auf 'veiled' muss greifen — geprueft am VERHALTEN, nicht am
    # DDL-Text (Muster M037). Der Probeschreibvorgang laeuft in einem
    # Savepoint und wird sofort zurueckgenommen.
    con.execute("SAVEPOINT m040_check")
    try:
        try:
            con.execute(
                "INSERT INTO person_image_veil (person_id, veiled, "
                "changed_at, audit_seq) VALUES (?,?,?,?)", (-1, 2, 0, -1))
        except sqlite3.IntegrityError:
            pass  # so soll es sein
        else:
            raise RuntimeError(
                "M040: der CHECK auf 'veiled' greift nicht — der Wert 2 "
                "wurde angenommen.")
    finally:
        con.execute("ROLLBACK TO m040_check")
        con.execute("RELEASE m040_check")

    # --- (d) Delta-Waechter: diese Migration vergibt nichts ----------------
    for code, _l, _d in _SEED_CAPS:
        vorher, nachher = grants_vorher[code], _grant_zahl(con, code)
        if vorher:
            logger.warning(
                "M040: '%s' trug vor dem Seed bereits %d Grant(s). Diese "
                "Migration vergibt keine; die Herkunft steht in audit_log "
                "(rbac_admin list-grants --all).", code, vorher)
        if nachher > vorher:
            raise RuntimeError(
                "M040: '%s' hat waehrend dieses Laufs %d Grant(s) "
                "hinzubekommen (vorher %d, jetzt %d). Diese Migration vergibt "
                "keine — der Lauf wird zurueckgerollt."
                % (code, nachher - vorher, vorher, nachher))
    for code, _l in _SEED_ROLES:
        vorher, nachher = zuweisungen_vorher[code], _zuweisungs_zahl(con, code)
        if vorher:
            logger.warning(
                "M040: Rolle '%s' war vor dem Seed bereits %d-mal "
                "zugewiesen. Diese Migration weist nichts zu.", code, vorher)
        if nachher > vorher:
            raise RuntimeError(
                "M040: Rolle '%s' wurde waehrend dieses Laufs %d-mal "
                "zugewiesen. Diese Migration weist nichts zu — der Lauf wird "
                "zurueckgerollt." % (code, nachher - vorher))

    logger.info(
        "M040: Rolle 'researcher', Recht 'imageveil.lift' (ohne Grants) und "
        "Tabelle %s angelegt. Bis zur Vergabe des Rechts sehen ALLE die "
        "Forenbilder verschleiert: 'rbac_admin grant --role investigator "
        "--capability imageveil.lift'.", _TABELLE)
