# =============================================================================
# management/migrations/coordinator/m041_db_vorfall.py
# IT-Forensisches Ermittlungswerkzeug — Register "Datenbank-Vorfaelle" (Build 777)
# =============================================================================
# Zweck:
#   Legt in coordinator.db die Tabelle db_vorfall an — das zentrale Register,
#   in das der Webserver einen Datenbankvorfall eintraegt (ab Build 778: die
#   Startpruefung der evidence_<uid>.db hat einen Schaden gefunden, die Datei
#   gesichert, repariert und ausgetauscht, oder den Start verweigert).
#
# ── ANLASS ──────────────────────────────────────────────────────────────────
#
#   PROD 13./14.10.2026: evidence_2948078.db war beschaedigt; der Neuaufbau lief
#   von Hand. Festlegung Alex 14.10.2026: kuenftig repariert der Webserver beim
#   Start selbst, damit die Ermittler arbeiten koennen — und es entsteht ein
#   Eintrag, den Alex spaeter liest. Eine Statusdatei waere ein Medienbruch;
#   der Eintrag gehoert in eine zentrale Datenbank und ins Management
#   ("Speziell fuer mich ist das ganz wichtig").
#
# ── WARUM ERGEBNIS UND ART KEINEN CHECK TRAGEN ──────────────────────────────
#
#   SQLite kann einen CHECK nicht nachtraeglich aendern (Lehre M037/M040: ein
#   neuer Wert verlangte einen Tabellenumbau, keine additive Migration mehr).
#   Arten und Ergebnisse werden kuenftig wachsen; die zulaessigen Werte prueft
#   deshalb der einzige Schreibweg (management/db_vorfall/db_vorfall_repo.py).
#   Einen CHECK tragen nur 'status' (offen/geprueft — ein Zustandspaar, das
#   sich nicht erweitert) und 'nachgetragen' (0/1), sowie die Kopplung
#   'geprueft <=> Pruefer, Zeitpunkt und Beleg vorhanden'.
#
# ── EINE ZEILE JE VORFALL, IDEMPOTENT UEBER vorfall_uid ─────────────────────
#
#   vorfall_uid wird bei der ERKENNUNG vergeben, nicht beim Eintragen. Ist
#   coordinator.db in diesem Moment nicht erreichbar, wird der Vorfall
#   gepuffert und spaeter nachgetragen (db_vorfall_puffer.py). Scheitert nach
#   einem erfolgreichen Nachtrag das Loeschen der Pufferdatei, darf der
#   naechste Versuch KEINE zweite Zeile erzeugen: UNIQUE(vorfall_uid).
#
# ── KEIN FREMDSCHLUESSEL AUF person_id ──────────────────────────────────────
#
#   person_id ist die Person, fuer die der Webserver lief. Der Vorfall muss
#   AUCH DANN eingetragen werden, wenn die Person nicht (mehr) in person
#   steht — ein abgewiesener Eintrag waere ein still verlorener Beleg
#   (Grundregel 1). geprueft_von dagegen ist immer eine handelnde Person des
#   Managements und traegt den Verweis.
#
# ── MIGRATIONSVORBEHALT (ab 01.07.2026) ─────────────────────────────────────
#
#   NUR coordinator.db. evidence_<uid>.db, forensic_<uid>.db und
#   assets_<uid>.db werden NICHT beruehrt. REIN ADDITIV: eine neue Tabelle und
#   ein Index. Keine Rolle, kein Recht, kein Grant: die Sicht nutzt das
#   bestehende Recht 'ops.view', das Pruefen das bestehende
#   'wartung.durchfuehren' (M014). KEIN executescript() — jede Anweisung
#   einzeln, damit ein Fehler den Runner in den ROLLBACK zwingt (Lehre M019).
#
# IDEMPOTENZ: CREATE ... IF NOT EXISTS, Spaltenpruefung. Ein zweiter Lauf ist
#   ein No-op. Eine vorhandene Tabelle mit ANDEREN Spalten bricht ab.
# RUECKWEG: keiner (forward-only). Von Hand moeglich, solange die Tabelle leer
#   ist — Handarbeit unter Aufsicht.
#
# Version: v0.8.777 · Build: 777 · 2026-10-14
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 41
NAME = "Register Datenbank-Vorfaelle: Tabelle db_vorfall"
KIND = "additive"

_TABELLE = "db_vorfall"
_INDEX = "ix_db_vorfall_status"

_DDL = """
CREATE TABLE IF NOT EXISTS db_vorfall (
    id              INTEGER PRIMARY KEY,
    -- bei der Erkennung vergeben (uuid4, hex); macht den Nachtrag idempotent
    vorfall_uid     TEXT    NOT NULL UNIQUE,
    -- Zeitpunkt der Erkennung (Unix-Sekunden) und des Eintrags hier
    erkannt_at      INTEGER NOT NULL,
    erfasst_at      INTEGER NOT NULL,
    -- 1 = aus dem Puffer nachgetragen (coordinator.db war nicht erreichbar)
    nachgetragen    INTEGER NOT NULL CHECK("nachgetragen" IN (0,1)),
    art             TEXT    NOT NULL,
    ergebnis        TEXT    NOT NULL,
    subject_id      INTEGER,
    datei           TEXT    NOT NULL,
    host            TEXT,
    -- die Person, fuer die der Webserver lief (bewusst ohne Fremdschluessel)
    person_id       INTEGER,
    -- vollstaendiger Befund als JSON; seine SHA-256 steht im Beleg
    befund_json     TEXT    NOT NULL,
    status          TEXT    NOT NULL CHECK("status" IN ('offen','geprueft')),
    audit_seq       INTEGER NOT NULL REFERENCES audit_log(seq),
    geprueft_von    INTEGER REFERENCES person(id),
    geprueft_at     INTEGER,
    pruef_notiz     TEXT,
    pruef_audit_seq INTEGER REFERENCES audit_log(seq),
    CHECK (("status" = 'offen' AND geprueft_von IS NULL
            AND geprueft_at IS NULL AND pruef_audit_seq IS NULL)
        OR ("status" = 'geprueft' AND geprueft_von IS NOT NULL
            AND geprueft_at IS NOT NULL AND pruef_audit_seq IS NOT NULL))
)
"""

_DDL_INDEX = ("CREATE INDEX IF NOT EXISTS ix_db_vorfall_status "
              "ON db_vorfall(status, erkannt_at)")

_SPALTEN = {
    "id", "vorfall_uid", "erkannt_at", "erfasst_at", "nachgetragen", "art",
    "ergebnis", "subject_id", "datei", "host", "person_id", "befund_json",
    "status", "audit_seq", "geprueft_von", "geprueft_at", "pruef_notiz",
    "pruef_audit_seq",
}


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _index_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,)).fetchone() is not None


def _spalten(con: sqlite3.Connection, tabelle: str):
    return {r[1] for r in con.execute(
        'PRAGMA table_info("%s")' % tabelle).fetchall()}


def _probe(con: sqlite3.Connection, werte: dict) -> bool:
    """
    Fuegt eine Probezeile ein und meldet, ob SQLite sie ANNAHM. Laeuft in
    einem Savepoint und wird in jedem Fall zurueckgenommen.
    """
    zeile = {
        "vorfall_uid": "m041-probe", "erkannt_at": 0, "erfasst_at": 0,
        "nachgetragen": 0, "art": "probe", "ergebnis": "probe",
        "datei": "probe", "befund_json": "{}", "status": "offen",
        "audit_seq": -1,
    }
    zeile.update(werte)
    spalten = sorted(zeile)
    con.execute("SAVEPOINT m041_probe")
    try:
        try:
            con.execute(
                "INSERT INTO db_vorfall (%s) VALUES (%s)" % (
                    ", ".join(spalten), ", ".join("?" for _ in spalten)),
                [zeile[s] for s in spalten])
        except sqlite3.IntegrityError:
            return False
        return True
    finally:
        con.execute("ROLLBACK TO m041_probe")
        con.execute("RELEASE m041_probe")


def up(con: sqlite3.Connection) -> None:
    # --- Vorbedingungen: laut scheitern statt halb anlegen ------------------
    for pflicht in ("person", "audit_log"):
        if not _table_exists(con, pflicht):
            raise RuntimeError(
                "M041: '%s' fehlt — fruehere Migrationen sind nicht "
                "angewandt. Reihenfolge pruefen." % pflicht)

    # Eine vorhandene Tabelle mit ANDEREN Spalten ist kein No-op, sondern ein
    # Befund (Muster M037/M040): es wird nichts ueberschrieben.
    if _table_exists(con, _TABELLE):
        ist = _spalten(con, _TABELLE)
        if ist != _SPALTEN:
            raise RuntimeError(
                "M041: '%s' existiert bereits mit ABWEICHENDEN Spalten "
                "(vorhanden: %s / erwartet: %s). Es wird nichts "
                "ueberschrieben." % (_TABELLE, sorted(ist), sorted(_SPALTEN)))
        logger.info("M041: %s bereits vorhanden.", _TABELLE)

    con.execute(_DDL)
    con.execute(_DDL_INDEX)

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) ------
    if not _table_exists(con, _TABELLE):
        raise RuntimeError("M041: %s fehlt nach dem Anlegen." % _TABELLE)
    ist = _spalten(con, _TABELLE)
    if ist != _SPALTEN:
        raise RuntimeError(
            "M041: %s hat nach dem Anlegen den falschen Spaltensatz: %s"
            % (_TABELLE, sorted(ist)))
    if not _index_exists(con, _INDEX):
        raise RuntimeError("M041: Index %s fehlt nach dem Anlegen." % _INDEX)

    # Die CHECKs muessen greifen — geprueft am VERHALTEN, nicht am DDL-Text
    # (Muster M037/M040). Erst die Gegenprobe: eine gueltige Zeile MUSS
    # angenommen werden, sonst bewiesen die Ablehnungen darunter nichts.
    if not _probe(con, {}):
        raise RuntimeError("M041: eine gueltige Probezeile wurde abgelehnt.")
    vermerk = {"geprueft_von": 1, "geprueft_at": 1, "pruef_audit_seq": -1}
    if not _probe(con, dict(vermerk, status="geprueft")):
        raise RuntimeError(
            "M041: eine gueltig gepruefte Probezeile wurde abgelehnt.")
    abzulehnen = [
        ("status ausserhalb offen/geprueft", {"status": "erledigt"}),
        ("nachgetragen ausserhalb 0/1", {"nachgetragen": 2}),
    ]
    # Die Kopplung Status <-> Pruefvermerk, JEDES Feld einzeln: 'geprueft'
    # ohne genau dieses Feld, und 'offen' mit genau diesem Feld (sonst
    # bliebe ein einzelnes vergessenes Feld im CHECK unbemerkt).
    for feld in sorted(vermerk):
        ohne = {k: v for k, v in vermerk.items() if k != feld}
        abzulehnen.append(("geprueft ohne %s" % feld,
                           dict(ohne, status="geprueft")))
        abzulehnen.append(("offen mit %s" % feld, {feld: vermerk[feld]}))
    for beschreibung, werte in abzulehnen:
        if _probe(con, werte):
            raise RuntimeError(
                "M041: der CHECK greift nicht (%s wurde angenommen)."
                % beschreibung)

    logger.info("M041: Tabelle %s angelegt (Register Datenbank-Vorfaelle).",
                _TABELLE)
