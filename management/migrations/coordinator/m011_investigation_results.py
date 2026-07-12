# =============================================================================
# management/migrations/coordinator/m011_investigation_results.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M011 — coordinator.db (ADDITIV)
#   Legt die ERMITTLUNGSERGEBNIS-BEWERTUNG an (Build 387).
#
# DIE ZENTRALE ARCHITEKTUR-ENTSCHEIDUNG (mc 2026-07-12):
#   Skalen und Kriterien sind DATEN, kein eingefrorenes Code-Vokabular.
#
#   Bei EventType, matter_kinds und case_events.EVENT_KINDS gilt das Gegenteil:
#   dort sind die Werte im CODE eingefroren, weil ein Beleg-Typ in zehn Jahren
#   noch exakt dasselbe bedeuten muss. Hier ist die Lage anders (mc):
#   "Wir stehen noch ganz am Anfang der Ermittlungen und uns fehlt noch die
#   Erfahrung, was sich langfristig als sinnvoll erweist." Skalen sollen
#   NACHTRAEGLICH anpassbar und Kriterien ERGAENZBAR sein — ohne Migration.
#   Also: auditierter KATALOG in der Datenbank.
#
#   Ein neues Kriterium oder ein neuer Skalenpunkt ist damit ein auditierter
#   SCHREIBVORGANG (catalog_admin-CLI), kein Schema-Eingriff an produktiven
#   Ermittlungsdaten.
#
# DIE ZWEITE ENTSCHEIDUNG — NUMERIK EINFRIEREN (mc):
#   Jede Bewertungszeile speichert den Skalen-CODE *und* den zugehoerigen
#   ORDINAL-WERT ZUM ZEITPUNKT DER ERFASSUNG (eingefrorene Kopie), dazu die
#   Katalogversion.
#
#   Warum das nicht verhandelbar ist: Wird eine Skala spaeter umnummeriert
#   (und genau das ist ausdruecklich vorgesehen), wuerden Bewertungen, die nur
#   den Code speichern, ihre BEDEUTUNG RUECKWIRKEND AENDERN. Zeitreihen und
#   Statistiken kippten dann STILL — ohne Fehler, ohne Warnung, ohne dass es
#   jemand merkt. Das waere der schwerste Fehler, den dieses Modul machen
#   koennte (Grundregel 1).
#
# DIE DRITTE ENTSCHEIDUNG — APPEND-ONLY (mc):
#   investigation_results kennt KEIN UPDATE und KEIN DELETE. Eine Korrektur ist
#   eine NEUE ZEILE. Der Verlauf IST hier die Ermittlungsleistung: er zeigt den
#   Erkenntnisgewinn (aus 'Verdacht' wird 'wahrscheinlich' wird 'gerichtsfest').
#   Der jeweils aktuelle Stand kommt aus der Sicht v_investigation_current.
#
#   Auch der KATALOG ist append-only: Skalenpunkte werden nie geloescht, nur
#   'deprecated_at' gesetzt — sonst zeigten bestehende Bewertungen ins Leere.
#
# ZWEI ACHSEN JE KRITERIUM (mc):
#   KONFIDENZ  — "wie sicher?"  (einheitliche Skala fuer ALLE Kriterien)
#   QUALITAET  — "wie tief?"    (KRITERIENSPEZIFISCH, darf fehlen)
#   'Land, aber gerichtsfest' ist ein ANDERER Ermittlungsstand als
#   'Meldeanschrift, aber nur Verdacht' — und beide begruenden andere
#   naechste Massnahmen. Genau darum zwei Achsen und nicht eine Zahl.
#
# ZWEI EXTREME JE KRITERIUM (mc):
#   'schwerste' — die gravierendste Erkenntnis (juengstes Opfer, engster
#                 Beziehungsgrad, fortlaufender Missbrauch ...)
#   'beste'     — die am besten belegte / praeziseste Erkenntnis
#   Ein Fall traegt damit hoechstens 10 Kriterien x 2 Extreme = 20 aktuelle
#   Bewertungen. Bewusst KEINE Personenliste je Fall — das waere ein Vielfaches
#   an Pflegeaufwand ohne Zusatznutzen fuer die Priorisierung (mc).
#
# ACHTUNG ZUR SEMANTIK DES ORDINAL (mc, ausdruecklich bestaetigt):
#   Bei location_quality und victim_quality misst 'ordinal' die PRAEZISION
#   (je hoeher, desto genauer). Bei abuser_quality misst er SCHWERE/AKTUALITAET
#   (fortlaufend > ehemalig > kontaktlos). Das ist eine ANDERE Bedeutung
#   derselben Zahl. Sie steht deshalb ausdruecklich in
#   assessment_scale.beschreibung — wer spaeter Statistiken rechnet, muss das
#   wissen, sonst addiert er Aepfel und Birnen.
#
# SEED (EINGEFROREN, m005-Prinzip):
#   Die Migration importiert ABSICHTLICH NICHTS aus dem Anwendungs-Katalog.
#   Alle Seed-Werte stehen hier literal. Eine Migration muss auch in Jahren
#   noch exakt dasselbe tun, unabhaengig davon, wie der Katalog sich
#   weiterentwickelt hat.
#
# IDEMPOTENZ: CREATE TABLE/INDEX/VIEW IF NOT EXISTS + INSERT OR IGNORE + Guard.
# KIND='additive' -> rein additiv, datenneutral.
#
# Beleg: mc 2026-07-12 (Punkte 1-8 der Klaerung).
# Version: v0.7.387 · Build: 387 · 2026-07-12
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 11
NAME = "Ermittlungsergebnis-Bewertung (Katalog + investigation_results)"
KIND = "additive"

#: Startversion des Katalogs. Jede Katalogaenderung erhoeht sie um 1
#: (AssessmentCatalogRepo). Jede Bewertung merkt sich, gegen WELCHE Version
#: sie erfasst wurde.
CATALOG_VERSION_START = 1


# --- Katalog -----------------------------------------------------------------
_DDL_SCALE = """
CREATE TABLE IF NOT EXISTS assessment_scale (
    code          TEXT PRIMARY KEY,
    label         TEXT NOT NULL,
    beschreibung  TEXT NOT NULL DEFAULT '',   -- WAS misst das ordinal? (s. o.)
    audit_seq     INTEGER NOT NULL REFERENCES audit_log(seq),
    created_by    INTEGER REFERENCES person(id),
    created_at    INTEGER NOT NULL,
    deprecated_at INTEGER                      -- append-only: nie DELETE
)
"""

_DDL_ITEM = """
CREATE TABLE IF NOT EXISTS assessment_scale_item (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scale_code    TEXT    NOT NULL REFERENCES assessment_scale(code),
    code          TEXT    NOT NULL,
    label         TEXT    NOT NULL,
    ordinal       INTEGER NOT NULL,            -- numerisch -> statistikfaehig
    sort          INTEGER NOT NULL DEFAULT 0,
    audit_seq     INTEGER NOT NULL REFERENCES audit_log(seq),
    created_by    INTEGER REFERENCES person(id),
    created_at    INTEGER NOT NULL,
    deprecated_at INTEGER,
    UNIQUE(scale_code, code)
)
"""

_DDL_CRITERION = """
CREATE TABLE IF NOT EXISTS assessment_criterion (
    code          TEXT PRIMARY KEY,
    label         TEXT NOT NULL,
    -- NULLABLE (mc): Kriterien ohne festgelegte Qualitaetsskala laufen
    -- zunaechst NUR mit Konfidenz. Die Skala kommt spaeter per CLI nach —
    -- OHNE Migration.
    quality_scale TEXT REFERENCES assessment_scale(code),
    sort          INTEGER NOT NULL DEFAULT 0,
    audit_seq     INTEGER NOT NULL REFERENCES audit_log(seq),
    created_by    INTEGER REFERENCES person(id),
    created_at    INTEGER NOT NULL,
    deprecated_at INTEGER
)
"""

_DDL_CATVER = """
CREATE TABLE IF NOT EXISTS assessment_catalog_version (
    id      INTEGER PRIMARY KEY CHECK(id = 1),
    version INTEGER NOT NULL
)
"""

# --- Bewertungen (APPEND-ONLY) -----------------------------------------------
_DDL_RESULTS = """
CREATE TABLE IF NOT EXISTS investigation_results (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL REFERENCES cases(user_id),
    criterion_code     TEXT    NOT NULL REFERENCES assessment_criterion(code),
    extrem             TEXT    NOT NULL
                       CHECK(extrem IN ('schwerste','beste')),
    -- KONFIDENZ: Code + EINGEFRORENER Zahlenwert (s. Kopfkommentar).
    confidence_code    TEXT    NOT NULL,
    confidence_ordinal INTEGER NOT NULL,
    -- QUALITAET: darf fehlen (Kriterium ohne Skala).
    quality_code       TEXT,
    quality_ordinal    INTEGER,
    -- Gegen WELCHEN Katalogstand wurde bewertet?
    catalog_version    INTEGER NOT NULL,
    note               TEXT    NOT NULL DEFAULT '',
    created_by         INTEGER REFERENCES person(id),
    created_at         INTEGER NOT NULL,
    audit_seq          INTEGER NOT NULL REFERENCES audit_log(seq),
    -- Konsistenz: entweder BEIDE Qualitaetsfelder oder KEINES. Eine halbe
    -- Qualitaetsangabe waere ein stiller Datenfehler.
    CHECK((quality_code IS NULL) = (quality_ordinal IS NULL))
)
"""

# APPEND-ONLY-TRIGGER: UPDATE und DELETE sind auf Datenbankebene verboten.
# Der Schutz gehoert NICHT allein in die Anwendung — ein Repo kann man umgehen,
# einen Trigger nicht (gleiche Linie wie der audit_log-Schutz, M001).
#
# GENAU EINE AUSNAHME — die BELEG-KOPPLUNG:
#   audit_seq ist NOT NULL, die seq des Belegs ist beim INSERT aber noch nicht
#   bekannt (der CoordinatorWriter schreibt den Beleg NACH dem fachlichen
#   Write). Die Zeile wird deshalb mit audit_seq=0 eingefuegt und im
#   after_audit-Hook — IN DERSELBEN TRANSAKTION — auf die echte seq gesetzt.
#
#   Der Trigger erlaubt exakt diesen einen Schritt: 0 -> positiv, und ALLE
#   Fachspalten unveraendert. Jeder andere UPDATE schlaegt fehl. Damit ist
#   ausgeschlossen, dass jemand die Ausnahme benutzt, um eine Bewertung
#   nachtraeglich umzuschreiben oder sie einem fremden Beleg unterzuschieben.
#
#   Eine Zeile mit audit_seq=0 kann nicht committen: der Hook laeuft in
#   derselben Transaktion, und wirft er, wird alles zurueckgerollt.
_DDL_TRG_UPD = """
CREATE TRIGGER IF NOT EXISTS trg_investigation_results_no_update
BEFORE UPDATE ON investigation_results
WHEN NOT (
        OLD.audit_seq = 0 AND NEW.audit_seq > 0
    AND NEW.id                 =  OLD.id
    AND NEW.user_id            =  OLD.user_id
    AND NEW.criterion_code     =  OLD.criterion_code
    AND NEW.extrem             =  OLD.extrem
    AND NEW.confidence_code    =  OLD.confidence_code
    AND NEW.confidence_ordinal =  OLD.confidence_ordinal
    AND NEW.quality_code       IS OLD.quality_code
    AND NEW.quality_ordinal    IS OLD.quality_ordinal
    AND NEW.catalog_version    =  OLD.catalog_version
    AND NEW.note               =  OLD.note
    AND NEW.created_by         IS OLD.created_by
    AND NEW.created_at         =  OLD.created_at
)
BEGIN
    SELECT RAISE(ABORT, 'investigation_results ist append-only: eine Korrektur ist eine NEUE Zeile (der einzige zulaessige UPDATE ist die Beleg-Kopplung audit_seq 0 -> seq in derselben Transaktion).');
END
"""

_DDL_TRG_DEL = """
CREATE TRIGGER IF NOT EXISTS trg_investigation_results_no_delete
BEFORE DELETE ON investigation_results
BEGIN
    SELECT RAISE(ABORT,
      'investigation_results ist append-only: Zeilen werden nie geloescht.');
END
"""

# AKTUELLER STAND: die hoechste id je (Fall, Kriterium, Extrem) ist die
# juengste Bewertung. Genau das liefert die Sicht — die Historie bleibt
# vollstaendig erhalten und ist ueber die Tabelle jederzeit abrufbar.
_DDL_VIEW = """
CREATE VIEW IF NOT EXISTS v_investigation_current AS
SELECT r.*
FROM investigation_results r
JOIN (
    SELECT user_id, criterion_code, extrem, MAX(id) AS max_id
    FROM investigation_results
    GROUP BY user_id, criterion_code, extrem
) m ON m.max_id = r.id
"""

_INDICES = (
    ("ix_results_case",
     "CREATE INDEX IF NOT EXISTS ix_results_case "
     "ON investigation_results (user_id, criterion_code, extrem, id)"),
    ("ix_results_stats",
     "CREATE INDEX IF NOT EXISTS ix_results_stats "
     "ON investigation_results (criterion_code, confidence_ordinal)"),
)

_TABLES = ("assessment_scale", "assessment_scale_item", "assessment_criterion",
           "assessment_catalog_version", "investigation_results")
_TRIGGERS = ("trg_investigation_results_no_update",
             "trg_investigation_results_no_delete")


# =============================================================================
# SEED — eingefroren-literal (m005-Prinzip; NIE aus catalog.py importieren)
# =============================================================================

#: (code, label, beschreibung)
_SEED_SCALES = (
    ("confidence",
     "Konfidenz (wie sicher?)",
     "Einheitlich fuer ALLE Kriterien. ordinal misst die BEWEISSTAERKE: "
     "je hoeher, desto belastbarer."),
    ("location_quality",
     "Ortsbestimmung (wie genau?)",
     "ordinal misst die PRAEZISION: je hoeher, desto enger eingegrenzt."),
    ("victim_quality",
     "Opferbestimmung (wie genau?)",
     "ordinal misst die PRAEZISION: je hoeher, desto genauer bestimmt."),
    ("abuser_quality",
     "Missbrauchsbeziehung (welche Art?)",
     "ACHTUNG — ANDERE SEMANTIK als bei location/victim: ordinal misst hier "
     "SCHWERE/AKTUALITAET, NICHT Praezision (fortlaufend > ehemalig > "
     "kontaktlos). Wer Statistiken ueber mehrere Skalen rechnet, darf diese "
     "Werte nicht mit Praezisionswerten vermischen (mc 2026-07-12)."),
)

#: (scale_code, code, label, ordinal, sort)
_SEED_ITEMS = (
    ("confidence", "unbestimmt", "unbestimmt", 0, 0),
    ("confidence", "kein_anhalt", "kein Anhalt", 1, 1),
    ("confidence", "anhaltspunkt", "Anhaltspunkt", 2, 2),
    ("confidence", "verdacht", "Verdacht", 3, 3),
    ("confidence", "wahrscheinlich", "wahrscheinlich", 4, 4),
    ("confidence", "gerichtsfest", "gerichtsfest", 5, 5),

    ("location_quality", "unbestimmt", "unbestimmt", 0, 0),
    ("location_quality", "land", "Land", 1, 1),
    ("location_quality", "region", "Region", 2, 2),
    ("location_quality", "ort", "Ort", 3, 3),
    ("location_quality", "meldeanschrift", "Meldeanschrift", 4, 4),

    ("victim_quality", "unbestimmt", "unbestimmt", 0, 0),
    ("victim_quality", "geschlecht", "Geschlecht", 1, 1),
    ("victim_quality", "alter", "Alter", 2, 2),
    ("victim_quality", "beziehungsgrad", "Beziehungsgrad", 3, 3),
    ("victim_quality", "name", "Name", 4, 4),

    ("abuser_quality", "unbestimmt", "unbestimmt", 0, 0),
    ("abuser_quality", "kontaktlos", "kontaktlos", 1, 1),
    ("abuser_quality", "ehemalig", "ehemalig", 2, 2),
    ("abuser_quality", "fortlaufend", "fortlaufend", 3, 3),
)

#: (code, label, quality_scale|None, sort)
#: KEIN '_confidence'-Suffix (mc): das Kriterium IST die Sache; die Konfidenz
#: ist nur EINE der beiden Achsen. 'location_identification_confidence.
#: quality_ordinal' waere irrefuehrend.
_SEED_CRITERIA = (
    ("identification", "Identifizierung des Kontoinhabers", None, 10),
    ("location_identification", "Ortsbestimmung", "location_quality", 20),
    ("victim_identification", "Opferbestimmung", "victim_quality", 30),
    ("abuser", "Missbrauchshandlung (Taeterschaft)", "abuser_quality", 40),
    ("cp_possession", "Kinderpornographie: Besitz", None, 50),
    ("cp_distribution", "Kinderpornographie: Verbreitung", None, 60),
    ("cp_production", "Kinderpornographie: Herstellung", None, 70),
    ("jp_possession", "Jugendpornographie: Besitz", None, 80),
    ("jp_distribution", "Jugendpornographie: Verbreitung", None, 90),
    ("jp_production", "Jugendpornographie: Herstellung", None, 100),
)

#: Faehigkeiten (Seed hier, Katalog in rbac/catalog.py).
_SEED_CAPS = (
    ("results.view", "Ermittlungsergebnis sehen",
     "Bewertung des Ermittlungsergebnisses (Konfidenz/Qualitaet) lesen."),
    ("results.edit", "Ermittlungsergebnis bewerten",
     "Bewertungen des Ermittlungsergebnisses erfassen (append-only)."),
)


def _exists(con: sqlite3.Connection, typ: str, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type=? AND name=?",
        (typ, name)).fetchone() is not None


def _genesis_seq(con: sqlite3.Connection) -> int:
    """
    audit_seq der Seed-Zeilen. Der Seed ist Teil DIESER Migration; ihr Beleg ist
    der 'migration_applied'-Eintrag, den der MigrationRunner schreibt — der
    existiert zum Zeitpunkt von up() aber noch nicht. Wir koppeln daher an den
    letzten vorhandenen Beleg (die Migration laeuft in genau einer Transaktion;
    der migration_applied-Beleg folgt unmittelbar). Das ist derselbe Kunstgriff
    wie bei M006/M008 und wird hier ausdruecklich benannt, damit ihn niemand
    fuer einen Zufall haelt.
    """
    row = con.execute("SELECT MAX(seq) FROM audit_log").fetchone()
    return int(row[0]) if row and row[0] is not None else 1


def up(con: sqlite3.Connection) -> None:
    done = (all(_exists(con, "table", t) for t in _TABLES)
            and _exists(con, "view", "v_investigation_current")
            and all(_exists(con, "trigger", t) for t in _TRIGGERS))
    if done:
        logger.info("M011: Bewertungs-Katalog bereits vorhanden — No-op.")
        return

    if not _exists(con, "table", "rbac_capability"):
        raise RuntimeError(
            "M011: rbac_capability fehlt — M006 ist nicht angewandt.")
    if not _exists(con, "table", "cases"):
        raise RuntimeError("M011: cases fehlt — M002 ist nicht angewandt.")

    con.execute(_DDL_SCALE)
    con.execute(_DDL_ITEM)
    con.execute(_DDL_CRITERION)
    con.execute(_DDL_CATVER)
    con.execute(_DDL_RESULTS)
    for _name, ddl in _INDICES:
        con.execute(ddl)
    con.execute(_DDL_TRG_UPD)
    con.execute(_DDL_TRG_DEL)
    con.execute(_DDL_VIEW)

    now = int(time.time())
    seq = _genesis_seq(con)

    for code, label, besch in _SEED_SCALES:
        con.execute(
            "INSERT OR IGNORE INTO assessment_scale "
            "(code, label, beschreibung, audit_seq, created_by, created_at) "
            "VALUES (?, ?, ?, ?, NULL, ?)", (code, label, besch, seq, now))

    for scale, code, label, ordinal, sort in _SEED_ITEMS:
        con.execute(
            "INSERT OR IGNORE INTO assessment_scale_item "
            "(scale_code, code, label, ordinal, sort, audit_seq, created_by, "
            " created_at) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
            (scale, code, label, ordinal, sort, seq, now))

    for code, label, qscale, sort in _SEED_CRITERIA:
        con.execute(
            "INSERT OR IGNORE INTO assessment_criterion "
            "(code, label, quality_scale, sort, audit_seq, created_by, "
            " created_at) VALUES (?, ?, ?, ?, ?, NULL, ?)",
            (code, label, qscale, sort, seq, now))

    con.execute(
        "INSERT OR IGNORE INTO assessment_catalog_version (id, version) "
        "VALUES (1, ?)", (CATALOG_VERSION_START,))

    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now))

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    for t in _TABLES:
        if not _exists(con, "table", t):
            raise RuntimeError("M011: Tabelle '%s' fehlt nach up()." % t)
    for t in _TRIGGERS:
        if not _exists(con, "trigger", t):
            raise RuntimeError("M011: Trigger '%s' fehlt nach up()." % t)
    if not _exists(con, "view", "v_investigation_current"):
        raise RuntimeError("M011: Sicht v_investigation_current fehlt.")

    n_crit = con.execute(
        "SELECT COUNT(*) FROM assessment_criterion").fetchone()[0]
    if n_crit < len(_SEED_CRITERIA):
        raise RuntimeError(
            "M011: nur %d von %d Kriterien geseedet."
            % (n_crit, len(_SEED_CRITERIA)))
    for code, _l, _d in _SEED_CAPS:
        if not con.execute("SELECT 1 FROM rbac_capability WHERE code=?",
                           (code,)).fetchone():
            raise RuntimeError("M011: Faehigkeit '%s' fehlt." % code)

    logger.info("M011: Bewertungs-Katalog angelegt (%d Skalen, %d Skalenpunkte, "
                "%d Kriterien, Katalogversion %d).",
                len(_SEED_SCALES), len(_SEED_ITEMS), len(_SEED_CRITERIA),
                CATALOG_VERSION_START)
