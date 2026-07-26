# =============================================================================
# management/migrations/coordinator/m037_view_pref.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3G (Build 545)
# =============================================================================
# Zweck:
#   EINE Tabelle in coordinator.db: person_view_pref — die persoenliche
#   Ansichtseinstellung je Person. Sie traegt zweierlei:
#     * die REIHENFOLGE und SICHTBARKEIT der Cockpit-Sichten in der Navigation
#     * die AUSWAHL und Reihenfolge der Kacheln im Ueberblick
#
# ── WARUM UEBERHAUPT SERVERSEITIG ────────────────────────────────────────────
#
#   Weil der Browser als Ablageort projektweit ausgeschlossen ist. Der Beleg
#   steht im Kopf des Zustandsobjekts der Cockpit-Shell:
#   management/server/static/cockpit.js — "Zustand lebt nur im Speicher (kein
#   localStorage — Projekt-/Artefakt-Regel)". Eine Vorliebe, die den Neustart
#   nicht ueberlebt, ist keine Einstellung, sondern eine Geste. Also Datenbank.
#
#   (Der Bauplan Welle 3 zitiert diese Stelle als cockpit.js:413; die Zeile ist
#   seither auf 447 gewandert. Der Inhalt steht unveraendert — nachgesehen am
#   2026-07-26 gegen 0.8.544.)
#
# ── DER MIGRATIONSVORBEHALT (ab 01.07.2026) ─────────────────────────────────
#
#   Unbedenklich, und zwar nachpruefbar:
#     * NUR coordinator.db. evidence_<uid>.db, forensic_<uid>.db und
#       assets_<uid>.db werden NICHT beruehrt.
#     * REIN ADDITIV. Eine neue Tabelle, sonst nichts. Keine Spalte umbenannt,
#       keine Zeile angefasst. Verlustfreie Migration ist trivial erfuellt: es
#       gibt nichts zu migrieren.
#     * KEIN executescript() — jede Anweisung einzeln, damit ein Fehler den
#       Runner in den ROLLBACK zwingt (Lehre aus M019).
#
#   ES ENTSTEHEN ERMITTLERDATEN — aber keine Ermittlungsdaten. Die Zeilen
#   sagen aus, WIE jemand seine Oberflaeche eingerichtet hat, nie WAS er
#   ermittelt hat. Kein Fallbezug, keine subject_id, kein Freitext.
#
# ── WARUM KEIN NEUES RECHT ──────────────────────────────────────────────────
#
#   Weil es nichts zu schuetzen gibt, das nicht schon geschuetzt waere. Eine
#   Vorliebe wirkt AUSSCHLIESSLICH auf die eigene Oberflaeche und kann keine
#   Sicht oeffnen, fuer die das Recht fehlt: der Rechtefilter laeuft ZULETZT
#   (cockpit.js visibleViews()). Ein eigenes Recht haette nur die Frage
#   aufgeworfen, wer es wem entzieht — und die Antwort waere "niemand,
#   sinnvollerweise". Der Bauplan Welle 3 §4 sieht fuer AP-3G ebenfalls keines
#   vor.
#
# ── WARUM NORMALISIERT UND NICHT EIN JSON-KLUMPEN ───────────────────────────
#
#   Eine Spalte 'einstellungen_json' waere in zehn Minuten geschrieben gewesen.
#   Sie haette aber die Frage "wer hat die Eskalationssicht ausgeblendet?"
#   unbeantwortbar gemacht, ohne in der Anwendung JSON zu zerlegen. Genau diese
#   Frage kann betrieblich wichtig werden (s. Kopf von viewpref_katalog.py,
#   Abschnitt zur Ausblendbarkeit). Eine Zeile je Element beantwortet sie mit
#   einem SELECT.
#
# ── DIE POSITION BLEIBT AUCH BEI AUSGEBLENDETEN ELEMENTEN ERHALTEN ──────────
#
#   'sichtbar' und 'position' sind getrennte Spalten. Wer eine Sicht ausblendet
#   und spaeter wieder einblendet, findet sie an ihrem Platz — nicht am Ende.
#   Das ist kein Komfort, sondern verhindert, dass ein Wiedereinblenden die
#   ganze uebrige Ordnung durcheinanderbringt und jemand danach neu sortiert,
#   was er nie sortieren wollte.
#
# NUMMER: 37 — die naechste freie Nummer nach dem Ende des Parallelbetriebs
#   (Build 544, Leitfaden §17.4: "37 — und sie ist gefahrlos"). Kette danach
#   lueckenlos 1-37.
# Version: v0.8.545 · Build: 545 · 2026-07-26
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 37
NAME = "Persoenliche Ansichtseinstellung (person_view_pref)"
KIND = "additive"

# Die beiden Arten sind EINGEFROREN. Sie spiegeln viewpref_katalog.ARTEN, das
# hier bewusst NICHT importiert wird (m005-Prinzip: eine angewandte Migration
# darf ihr Laufzeitverhalten nie aendern). Ein Test haelt beide gegeneinander.
_ARTEN = ("sicht", "widget")

_DDL = """
CREATE TABLE IF NOT EXISTS person_view_pref (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id    INTEGER NOT NULL REFERENCES person(id),
    -- 'sicht'  = ein Eintrag der Cockpit-Navigation
    -- 'widget' = eine Kachel im Ueberblick
    art          TEXT    NOT NULL CHECK("art" IN ('sicht','widget')),
    -- Der Schluessel des Elements (view_id bzw. widget_key). NICHT als FK
    -- modellierbar: die Wahrheitsquelle der Sichten ist cockpit.js, nicht die
    -- Datenbank. Die Pruefung gegen den Katalog leistet der Schreibpfad
    -- (viewpref_repo), und ein unbekannter Schluessel wird beim Lesen BENANNT
    -- statt verschluckt (Grundregel 1).
    element_key  TEXT    NOT NULL CHECK(LENGTH(TRIM("element_key")) > 0),
    position     INTEGER NOT NULL CHECK("position" >= 0),
    sichtbar     INTEGER NOT NULL DEFAULT 1 CHECK("sichtbar" IN (0,1)),
    geaendert_at INTEGER NOT NULL,
    audit_seq    INTEGER NOT NULL REFERENCES audit_log(seq),
    -- Ein Element kommt je Person und Art GENAU EINMAL vor.
    UNIQUE(person_id, art, element_key),
    -- Und jeder Platz ist genau einmal belegt. Zwei Elemente auf Position 3
    -- waeren keine Reihenfolge, sondern eine Behauptung.
    UNIQUE(person_id, art, position)
)
"""

_INDICES = (
    ("ix_person_view_pref_person",
     "CREATE INDEX IF NOT EXISTS ix_person_view_pref_person "
     "ON person_view_pref (person_id, art, position)"),
)

_SPALTEN = {
    "id", "person_id", "art", "element_key", "position", "sichtbar",
    "geaendert_at", "audit_seq",
}


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _spalten(con: sqlite3.Connection, tabelle: str):
    return {r[1] for r in con.execute(
        'PRAGMA table_info("%s")' % tabelle).fetchall()}


def up(con: sqlite3.Connection) -> None:
    # --- Vorbedingungen: laut scheitern statt halb anlegen ------------------
    for pflicht in ("person", "audit_log"):
        if not _table_exists(con, pflicht):
            raise RuntimeError(
                "M037: '%s' fehlt — fruehere Migrationen sind nicht "
                "angewandt. Reihenfolge pruefen." % pflicht)

    # Eine bereits vorhandene Tabelle mit ANDEREN Spalten ist kein No-op,
    # sondern ein Befund (Muster M003/M034): dann steht dort etwas, das dieses
    # Schema nicht kennt. Es wird nichts ueberschrieben.
    if _table_exists(con, "person_view_pref"):
        ist = _spalten(con, "person_view_pref")
        if ist != _SPALTEN:
            raise RuntimeError(
                "M037: 'person_view_pref' existiert bereits mit ABWEICHENDEN "
                "Spalten (vorhanden: %s / erwartet: %s). Es wird nichts "
                "ueberschrieben." % (sorted(ist), sorted(_SPALTEN)))
        logger.info("M037: person_view_pref bereits vorhanden — No-op.")

    # --- Anlegen: jede Anweisung EINZELN (kein executescript) --------------
    con.execute(_DDL)
    for _name, sql in _INDICES:
        con.execute(sql)

    # --- Selbstpruefung (Verstoss -> raise -> ROLLBACK im Runner) ----------
    if not _table_exists(con, "person_view_pref"):
        raise RuntimeError("M037: person_view_pref fehlt nach dem Anlegen.")
    ist = _spalten(con, "person_view_pref")
    if ist != _SPALTEN:
        raise RuntimeError(
            "M037: person_view_pref hat nach dem Anlegen den falschen "
            "Spaltensatz: %s" % sorted(ist))
    vorhandene_idx = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND tbl_name='person_view_pref'").fetchall()}
    for name, _sql in _INDICES:
        if name not in vorhandene_idx:
            raise RuntimeError("M037: Index '%s' fehlt nach dem Anlegen."
                               % name)

    # Der CHECK auf 'art' muss die beiden eingefrorenen Werte tragen — und nur
    # diese. Geprueft wird das nicht am DDL-Text, sondern am Verhalten: ein
    # dritter Wert muss scheitern. (Der Probeschreibvorgang laeuft in der
    # Transaktion des Runners und wird sofort zurueckgenommen.)
    con.execute("SAVEPOINT m037_check")
    try:
        try:
            con.execute(
                "INSERT INTO person_view_pref (person_id, art, element_key, "
                "position, sichtbar, geaendert_at, audit_seq) "
                "VALUES (?,?,?,?,?,?,?)",
                (-1, "unfug", "x", 0, 1, 0, -1))
        except sqlite3.IntegrityError:
            pass  # so soll es sein
        else:
            raise RuntimeError(
                "M037: der CHECK auf 'art' greift nicht — ein unbekannter "
                "Wert wurde angenommen.")
    finally:
        con.execute("ROLLBACK TO m037_check")
        con.execute("RELEASE m037_check")

    logger.info("M037: person_view_pref angelegt (Arten: %s).",
                ", ".join(_ARTEN))
