# =============================================================================
# management/migrations/coordinator/m034_qs_stichprobe.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C (Build 540)
# =============================================================================
# Zweck:
#   Die QS-Stichprobe: drei Tabellen in coordinator.db plus die beiden Rechte
#   'qs.view' und 'qs.edit'.
#
#     qs_sample       — die ZIEHUNG (wer, wann, Verfahren, KEIM, Filter).
#     qs_sample_item  — die gezogenen Faelle in Ziehungsreihenfolge.
#     qs_review       — das PRUEFERGEBNIS je Fall, mit Pflichtbegruendung.
#
# ── DER MIGRATIONSVORBEHALT (ab 01.07.2026) ─────────────────────────────────
#
#   DIES IST DER ERSTE BUILD DER WELLE 3, DER NEUE ERMITTLERDATEN ANLEGT.
#   Er ist trotzdem unbedenklich, und zwar aus einem nachpruefbaren Grund:
#     * NUR coordinator.db. Die unter Vorbehalt stehenden Dateien
#       evidence_<uid>.db, forensic_<uid>.db und assets_<uid>.db werden NICHT
#       beruehrt.
#     * REIN ADDITIV. Keine bestehende Tabelle wird geaendert, keine Spalte
#       umbenannt, keine Zeile angefasst. Eine verlustfreie Migration ist damit
#       trivial erfuellt: es gibt nichts zu migrieren.
#     * KEIN executescript() — jede Anweisung einzeln, damit ein Fehler den
#       Runner in den ROLLBACK zwingt (Lehre aus M019).
#   Der Eintrag im Datenmigrationsleitfaden ist Teil dieses Builds.
#
# ── DER KEIM IST EINE SPALTE, KEIN PROTOKOLLEINTRAG ─────────────────────────
#
#   'seed' ist NOT NULL. Eine Ziehung ohne Keim laesst sich nicht nachrechnen
#   und waere gegen den Vorwurf der gezielten Auswahl nicht zu verteidigen;
#   sie darf im Schema deshalb gar nicht erst entstehen koennen. Zusammen mit
#   'grundgesamtheit_n' und 'filter_json' ist jede Ziehung exakt reproduzierbar
#   (management/qs/qs_sampler.py: ziehe/nachziehen_stimmt).
#
# ── DIE BEGRUENDUNG IST EIN PFLICHTFELD MIT WIRKSAMEM CHECK ─────────────────
#
#   'begruendung' ist NOT NULL UND traegt CHECK(LENGTH(TRIM(...)) > 0). NOT NULL
#   allein liesse den leeren String zu — ein Pruefergebnis mit leerer
#   Begruendung ist ein Daumen und kein Befund. Muster: escalation_ack
#   (Build 517) und annotation_tatzeit.quelle (M002).
#
# ── 'ergebnis' IST KEINE NOTE ───────────────────────────────────────────────
#
#   Die vier Codes sind eine EINGEFRORENE Kopie aus
#   management/qs/qs_vokabular.py (m005-Prinzip: eine angewandte Migration darf
#   ihr Verhalten nie aendern — deshalb Kopie, nicht Import). Ein Test haelt
#   beide gegeneinander. Es gibt kein 'mangelhaft' und keinen Punktwert:
#   geprueft wird die AUSWERTUNG, nicht die Person.
#
# ── KEINE FK AUF cases.subject_id IN qs_sample_item ─────────────────────────
#
#   Doch — sie steht drin, und das ist Absicht: eine Ziehung ueber einen Fall,
#   den es nicht gibt, waere ein Fehler und kein Grenzfall. ABER es gibt
#   ausdruecklich KEIN ON DELETE CASCADE: Faelle werden in diesem System nicht
#   geloescht (retention loescht nichts, Build 521), und eine kaskadierende
#   Loeschung wuerde einen QS-Beleg still mitnehmen.
#
# NUMMERNKREIS: m034 stammt aus dem Kreis der Instanz A (m033-m039), festgelegt
# in management/Parallelbetrieb_Welle3_v0_1.md §5.
# Version: v0.8.540 · Build: 540 · 2026-07-26
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 34
NAME = "QS-Stichprobe (qs_sample/_item/qs_review) + RBAC-Seed"
KIND = "additive"

# --- Vokabular (EINGEFROREN — nie aus qs_vokabular.py importieren) -----------
_ERGEBNIS_CODES = ("in_ordnung", "nachzuarbeiten", "ruecklauf_erforderlich",
                   "nicht_beurteilbar")
_VERFAHREN_CODES = ("geschichtet", "einfach")

_DDL_SAMPLE = """
CREATE TABLE IF NOT EXISTS qs_sample (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    gezogen_von       INTEGER NOT NULL REFERENCES person(id),
    gezogen_at        INTEGER NOT NULL,
    verfahren         TEXT    NOT NULL
                      CHECK("verfahren" IN ('geschichtet','einfach')),
    grundgesamtheit_n INTEGER NOT NULL CHECK("grundgesamtheit_n" >= 0),
    stichprobe_n      INTEGER NOT NULL CHECK("stichprobe_n" >= 0),
    -- DER KEIM. Ohne ihn ist die Ziehung kein Beleg (s. Kopf).
    seed              INTEGER NOT NULL,
    -- Die uebrigen Ziehungsparameter als JSON: Anteil, Hoechstgrenze,
    -- Abdeckungsschwelle, Schichtgroessen. Der Keim ALLEIN genuegt nicht,
    -- weil Verfahren und Schwelle die Schichtung bestimmen.
    filter_json       TEXT    NOT NULL,
    bemerkung         TEXT,
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    -- Die Stichprobe kann NICHT groesser sein als die Grundgesamtheit. Ein
    -- solcher Wert waere ein Rechenfehler, und er soll an der Datenbank
    -- scheitern und nicht erst in einem Bericht auffallen.
    CHECK("stichprobe_n" <= "grundgesamtheit_n")
)
"""

_DDL_ITEM = """
CREATE TABLE IF NOT EXISTS qs_sample_item (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id  INTEGER NOT NULL REFERENCES qs_sample(id),
    subject_id INTEGER NOT NULL REFERENCES cases(subject_id),
    -- Die ZIEHUNGSREIHENFOLGE ist Teil des Belegs: beim Nachziehen muss nicht
    -- nur dieselbe Menge, sondern dieselbe Folge herauskommen.
    position   INTEGER NOT NULL CHECK("position" >= 0),
    schicht    TEXT,
    UNIQUE(sample_id, subject_id),
    UNIQUE(sample_id, position)
)
"""

_DDL_REVIEW = """
CREATE TABLE IF NOT EXISTS qs_review (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id    INTEGER NOT NULL REFERENCES qs_sample(id),
    subject_id   INTEGER NOT NULL REFERENCES cases(subject_id),
    geprueft_von INTEGER NOT NULL REFERENCES person(id),
    geprueft_at  INTEGER NOT NULL,
    ergebnis     TEXT    NOT NULL
                 CHECK("ergebnis" IN ('in_ordnung','nachzuarbeiten',
                                      'ruecklauf_erforderlich',
                                      'nicht_beurteilbar')),
    -- PFLICHT, und der CHECK macht die Pflicht wirksam: NOT NULL allein liesse
    -- den leeren String zu.
    begruendung  TEXT    NOT NULL CHECK(LENGTH(TRIM("begruendung")) > 0),
    -- Ausserhalb der Ziehung geprueft? Die Prueflinge sind ein VORSCHLAG
    -- (Entscheidung mc); eine Abweichung ist erlaubt und wird PROTOKOLLIERT,
    -- statt unsichtbar zu bleiben.
    ausserhalb_der_ziehung INTEGER NOT NULL DEFAULT 0
                 CHECK("ausserhalb_der_ziehung" IN (0,1)),
    audit_seq    INTEGER NOT NULL REFERENCES audit_log(seq),
    -- Ein Fall wird je Ziehung EINMAL geprueft. Eine zweite Meinung ist eine
    -- neue Ziehung und kein zweiter Eintrag unter derselben Nummer.
    UNIQUE(sample_id, subject_id)
)
"""

_INDICES = (
    ("ix_qs_item_sample",
     "CREATE INDEX IF NOT EXISTS ix_qs_item_sample "
     "ON qs_sample_item (sample_id, position)"),
    ("ix_qs_review_sample",
     "CREATE INDEX IF NOT EXISTS ix_qs_review_sample "
     "ON qs_review (sample_id, subject_id)"),
    # Die Kernabfrage der Sicht 'was ist an diesem Fall schon geprueft worden?'
    ("ix_qs_review_subject",
     "CREATE INDEX IF NOT EXISTS ix_qs_review_subject "
     "ON qs_review (subject_id, geprueft_at)"),
)

_TABLES = ("qs_sample", "qs_sample_item", "qs_review")

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
#   GETRENNT, damit Vier-Augen moeglich bleibt (Muster release.view /
#   release.grant). Wer die Stichprobe SEHEN darf, darf damit noch nicht
#   PRUEFEN. Beide sind NICHT scope-behaftet: eine Stichprobe ueber den eigenen
#   Arbeitsvorrat waere keine.
_SEED_CAPS = (
    ("qs.view", "QS-Stichproben sehen",
     "Ziehungen und Pruefergebnisse der Qualitaetssicherung lesen. "
     "AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGSINSTRUMENT."),
    ("qs.edit", "QS-Stichproben ziehen und pruefen",
     "Eine Stichprobe ziehen und Pruefergebnisse mit Pflichtbegruendung "
     "erfassen. Die SELBSTPRUEFUNG ist serverseitig gesperrt: wer einen Fall "
     "bearbeitet hat, kann ihn nicht pruefen."),
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _cap_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_capability WHERE code=?",
        (code,)).fetchone() is not None


def _spalten(con: sqlite3.Connection, tabelle: str):
    return {r[1] for r in con.execute(
        'PRAGMA table_info("%s")' % tabelle).fetchall()}


def up(con: sqlite3.Connection) -> None:
    # --- Vorbedingungen: laut scheitern statt halb anlegen ------------------
    for pflicht in ("person", "cases", "audit_log", "rbac_capability"):
        if not _table_exists(con, pflicht):
            raise RuntimeError(
                "M034: '%s' fehlt — fruehere Migrationen sind nicht "
                "angewandt. Reihenfolge pruefen." % pflicht)

    # Eine bereits vorhandene Tabelle mit ANDEREN Spalten ist kein No-op,
    # sondern ein Befund: dann steht dort etwas, das dieses Schema nicht
    # kennt (Muster M003, Build 533).
    erwartet = {
        "qs_sample": {"id", "gezogen_von", "gezogen_at", "verfahren",
                      "grundgesamtheit_n", "stichprobe_n", "seed",
                      "filter_json", "bemerkung", "audit_seq"},
        "qs_sample_item": {"id", "sample_id", "subject_id", "position",
                           "schicht"},
        "qs_review": {"id", "sample_id", "subject_id", "geprueft_von",
                      "geprueft_at", "ergebnis", "begruendung",
                      "ausserhalb_der_ziehung", "audit_seq"},
    }
    for tab, soll in erwartet.items():
        if _table_exists(con, tab):
            ist = _spalten(con, tab)
            if ist != soll:
                raise RuntimeError(
                    "M034: '%s' existiert bereits mit ABWEICHENDEN Spalten "
                    "(vorhanden: %s / erwartet: %s). Es wird nichts "
                    "ueberschrieben." % (tab, sorted(ist), sorted(soll)))

    # --- Anlegen: jede Anweisung EINZELN (kein executescript) --------------
    con.execute(_DDL_SAMPLE)
    con.execute(_DDL_ITEM)
    con.execute(_DDL_REVIEW)
    for _name, sql in _INDICES:
        con.execute(sql)

    now = int(time.time())
    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now),
        )

    # --- Selbstpruefung 1: existieren Tabellen, Indizes und Rechte? --------
    for tab in _TABLES:
        if not _table_exists(con, tab):
            raise RuntimeError("M034: Tabelle '%s' fehlt nach dem Anlegen."
                               % tab)
    vorhandene_idx = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    for name, _sql in _INDICES:
        if name not in vorhandene_idx:
            raise RuntimeError("M034: Index '%s' fehlt nach dem Anlegen."
                               % name)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError("M034: Faehigkeit '%s' fehlt nach dem Seed."
                               % code)

    # --- Selbstpruefung 2: GREIFEN die CHECKs auch? ------------------------
    # Ein geschriebener, aber unwirksamer CHECK ist schlimmer als keiner: er
    # erzeugt Vertrauen, das er nicht traegt. Geprueft wird mit
    # Probeeinfuegungen in einem SAVEPOINT, der IMMER zurueckgerollt wird
    # (Muster M002, Build 532).
    con.execute("SAVEPOINT m034_probe")
    try:
        _probe(con)
    finally:
        con.execute("ROLLBACK TO m034_probe")
        con.execute("RELEASE m034_probe")

    logger.info("M034: qs_sample/_item/qs_review angelegt; Faehigkeiten %s "
                "geseedet.", ", ".join(c for c, _l, _d in _SEED_CAPS))


def _probe(con: sqlite3.Connection) -> None:
    """
    Probeeinfuegungen. Jede MUSS scheitern; tut sie es nicht, greift der CHECK
    nicht und die Migration bricht ab.

    Die Probe braucht eine gueltige person(id), cases(subject_id) und
    audit_log(seq). Gibt es keine, wird die Probe UEBERSPRUNGEN und das
    ausdruecklich protokolliert — eine Probe gegen eine leere Datenbank wuerde
    an den Fremdschluesseln scheitern und damit etwas anderes messen als
    gemeint.
    """
    p = con.execute("SELECT id FROM person LIMIT 1").fetchone()
    c = con.execute("SELECT subject_id FROM cases LIMIT 1").fetchone()
    a = con.execute("SELECT MAX(seq) FROM audit_log").fetchone()
    if not p or not c or not a or a[0] is None:
        logger.info("M034: CHECK-Probe uebersprungen (keine Person/kein Fall/"
                    "kein audit_log-Eintrag vorhanden). Die CHECKs stehen im "
                    "DDL und greifen ab dem ersten echten Schreibvorgang.")
        return
    pid, sid, seq = int(p[0]), int(c[0]), int(a[0])

    def _muss_scheitern(sql: str, args: tuple, was: str) -> None:
        try:
            con.execute(sql, args)
        except sqlite3.IntegrityError:
            return
        raise RuntimeError(
            "M034: CHECK greift NICHT — %s wurde angenommen. Ein "
            "geschriebener, aber unwirksamer CHECK ist schlimmer als keiner."
            % was)

    # (a) unbekanntes Verfahren
    _muss_scheitern(
        "INSERT INTO qs_sample (gezogen_von, gezogen_at, verfahren, "
        "grundgesamtheit_n, stichprobe_n, seed, filter_json, audit_seq) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (pid, 0, "wuerfeln", 10, 1, 1, "{}", seq),
        "ein unbekanntes Ziehungsverfahren")
    # (b) Stichprobe groesser als Grundgesamtheit
    _muss_scheitern(
        "INSERT INTO qs_sample (gezogen_von, gezogen_at, verfahren, "
        "grundgesamtheit_n, stichprobe_n, seed, filter_json, audit_seq) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (pid, 0, "einfach", 3, 4, 1, "{}", seq),
        "eine Stichprobe groesser als die Grundgesamtheit")

    # Fuer die Review-Proben wird eine echte Ziehung gebraucht.
    cur = con.execute(
        "INSERT INTO qs_sample (gezogen_von, gezogen_at, verfahren, "
        "grundgesamtheit_n, stichprobe_n, seed, filter_json, audit_seq) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (pid, 0, "einfach", 3, 1, 1, "{}", seq))
    sample_id = int(cur.lastrowid)

    # (c) LEERE Begruendung — der Kern des Pflichtfeldes
    _muss_scheitern(
        "INSERT INTO qs_review (sample_id, subject_id, geprueft_von, "
        "geprueft_at, ergebnis, begruendung, audit_seq) VALUES (?,?,?,?,?,?,?)",
        (sample_id, sid, pid, 0, "in_ordnung", "   ", seq),
        "eine leere Begruendung")
    # (d) unbekanntes Ergebnis
    _muss_scheitern(
        "INSERT INTO qs_review (sample_id, subject_id, geprueft_von, "
        "geprueft_at, ergebnis, begruendung, audit_seq) VALUES (?,?,?,?,?,?,?)",
        (sample_id, sid, pid, 0, "mangelhaft", "x", seq),
        "ein unbekanntes Ergebnis ('mangelhaft')")
