# =============================================================================
# management/migrations/evidence/m002_annotation_tatzeit.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Zweck (Build 532):
#   Legt in evidence_<uid>.db die Tabelle 'annotation_tatzeit' an: den Ort, an
#   dem eine Ermittlerin den TATZEITRAUM zu einer Annotation FESTSTELLT.
#
#   Damit bekommt die Achse 'feststellung' aus Build 530 ihre Datenquelle. Bis
#   hierhin trug jede Zeile des Fristenmonitors 'vorlaeufig', weil es keine
#   festgestellten Tatzeitpunkte gab — nicht aus Versehen, sondern weil die
#   Spalte fehlte.
#
# ADDITIV UND DATENNEUTRAL. Es wird eine NEUE Tabelle angelegt und KEINE
#   bestehende angefasst. 'annotations' bleibt Byte fuer Byte, wie sie war.
#   Kein UPDATE, kein ALTER TABLE, kein DELETE. Genau das war der Grund fuer die
#   eigene Tabelle (mc 2026-07-26).
#
# WARUM EINE EIGENE TABELLE UND KEINE ZWEI SPALTEN AUF 'annotations'
# (Entscheidung mc 2026-07-26, drei Gruende):
#   1. 'annotations' ist eine PRODUKTIVE Tabelle unter Migrationsvorbehalt (ab
#      01.07.2026). Sie nicht anzufassen ist die sicherste Migration, die es
#      gibt.
#   2. Ein Tatzeitraum ist von Natur aus 1:n. Eine Annotation kann mehrere
#      Zeitangaben tragen ("erstmals 2019, dann wieder 2021"). Ein Spaltenpaar
#      koennte immer nur EINE halten — die zweite Angabe waere verloren oder
#      muesste in Freitext ausweichen, wo sie niemand mehr findet.
#   3. 'annotations' ist append-only VERSIONIERT (version_nr, prev_id,
#      local_id). Eine Spalte dort wuerde in jede neue Version mitkopiert, und
#      man muesste dann entscheiden, welche Version 'gilt'.
#
# WARUM NICHT REIN KEY-VALUE (gemessen, nicht behauptet):
#   In einer EAV-Tabelle ist die Wertspalte TEXT, und SQLite vergleicht TEXT
#   lexikographisch. Messung 2026-07-26:
#       TEXT-Spalte:     MAX(v) ueber {1700000000, 999, 1650000000} -> 999
#       INTEGER-Spalte:  MAX(v) ueber {1700000000, 999, 1650000000} -> 1700000000
#   'MAX(von_ts)' ist genau die Abfrage, die der Fristenmonitor braucht. Ueber
#   eine TEXT-Spalte lieferte sie STILL das falsche Ergebnis — kein Fehler,
#   keine Ausnahme, nur eine falsche Zahl. Und ein CHECK der Art "wenn
#   art='hart', dann ist der Wert eine Ganzzahl im Plausibilitaetsrahmen" laesst
#   sich ueber TEXT nicht formulieren; die Pruefung muesste nach Python wandern,
#   also WEG von den Daten.
#
#   Deshalb: die HARTEN Zeitwerte sind typisiert (INTEGER), der Key-Value-Teil
#   gilt ausschliesslich fuer WEICHE Angaben ("vor zwei Jahren", "als ich 13
#   war"). Dort ist er richtig, weil man die Formen nicht kennt — und weil aus
#   ihnen NIE gerechnet wird.
#
# BEIDE SCHLUESSEL WERDEN GESPEICHERT (Entscheidung mc 2026-07-26):
#   annotation_id       — die Annotationsversion, aus deren Wortlaut die
#                         Zeitangabe gewonnen wurde. Sie wird NIE verworfen:
#                         damit bleibt die Kette zurueck zum urspruenglichen
#                         Wortlaut erhalten.
#   annotation_local_id — die LOGISCHE Annotation. Ueber sie loest die
#                         Arbeitssicht auf, damit die Tatzeit einer bearbeiteten
#                         Annotation FOLGT und nicht bei der alten Version
#                         haengenbleibt.
#   Sie darf NULL sein: 'annotations.local_id' ist optional ("anonyme
#   Einmal-Annotation", db/evidence_db.py:871). Deshalb ist annotation_id das
#   NOT-NULL-Feld und local_id das zusaetzliche.
#
# SELBSTPRUEFUNG NACH DEM ANLEGEN (s. verify_inline):
#   Es wird nicht nur geprueft, DASS die Tabelle da ist, sondern dass die
#   CHECK-Bedingungen auch GREIFEN — mit Probeeinfuegungen in einem SAVEPOINT,
#   der zurueckgerollt wird. Ein geschriebener, aber unwirksamer CHECK waere
#   schlimmer als keiner, weil man sich auf ihn verlaesst.
#
#   KEIN RUECKSTAND: Der Rollback des SAVEPOINT setzt auch 'sqlite_sequence'
#   zurueck (gemessen 2026-07-26). Die erste ECHTE Zeile bekommt daher id=1 und
#   nicht id=4 — sonst haette jemand zu Recht gefragt, warum die Zaehlung nicht
#   bei eins beginnt.
#
# SELF-CONTAINED / FROZEN: bewusst OHNE Import aus gemeinsamen Modulen. Der
#   Modul-Quelltext IST die Pruefsumme (runner._module_checksum); geteilter,
#   spaeter veraenderlicher Code wuerde die Belegbarkeit unterlaufen (Muster
#   m005/m031 im coordinator-Strang).
#
# Beleg: Datenmigrationsleitfaden_AIW.md, management/migrations/runner.py,
#        db/evidence_db.py:258-275 und :856-931 (Versionierung, local_id),
#        mc 2026-07-26 (eigene Tabelle, beide Schluessel).
# Version: v0.8.532 · Build: 532 · 2026-07-26
# =============================================================================

VERSION = 2
NAME = "annotation_tatzeit (festgestellter Tatzeitraum je Annotation, additiv)"
KIND = "additive"

#: Die Spalten, die die Tabelle tragen MUSS — in genau dieser Reihenfolge.
#  Sie sind hier als FROZEN COPY hinterlegt und werden nicht aus einem anderen
#  Modul importiert. Die Liste dient der Selbstpruefung: existiert die Tabelle
#  bereits mit einem ANDEREN Aufbau, bricht die Migration ab, statt sie
#  stillschweigend zu uebernehmen.
ERWARTETE_SPALTEN = (
    "id",
    "annotation_id",
    "annotation_local_id",
    "art",
    "von_ts",
    "bis_ts",
    "genauigkeit",
    "angabe_schluessel",
    "angabe_wert",
    "wortlaut",
    "quelle",
    "erfasst_von",
    "erfasst_at",
    "version_nr",
    "prev_id",
    "deleted_at",
)

#: Die Indizes, die mit angelegt werden. Begruendung je Eintrag:
#    tatzeit_ann_idx    — der Zugriffsweg der Oberflaeche (Tatzeit zur Annotation).
#    tatzeit_local_idx  — der Zugriffsweg ueber die LOGISCHE Annotation.
#    tatzeit_von_idx    — MAX(von_ts) des Fristenmonitors. Ohne brauchbaren
#                         Index kostet diese Abfrage O(n) je Fall — genau der
#                         Fehler, den Build 531 auf den forensic-Dateien gerade
#                         beseitigt hat.
#    tatzeit_bis_idx    — MIN(bis_ts), dasselbe fuer das Ende des Zeitraums.
#
#  DIE ZEITINDIZES SIND ABSICHTLICH VOLL UND NICHT PARTIELL (Messung 2026-07-26,
#  SQLite 3.45.1). Ein partieller Index 'WHERE von_ts IS NOT NULL' wird von
#  SQLite fuer 'SELECT MAX(von_ts) FROM ...' NICHT herangezogen — er greift nur,
#  wenn die Abfrage dieselbe WHERE-Bedingung wortgleich wiederholt:
#      partieller Index, ohne WHERE  -> 'SEARCH annotation_tatzeit'
#      partieller Index, mit  WHERE  -> 'SEARCH ... USING COVERING INDEX'
#      voller Index,      ohne WHERE -> 'SEARCH ... USING COVERING INDEX'
#  Ein Index, dessen Wirkung davon abhaengt, wie der lesende Code seine Abfrage
#  formuliert, ist eine Falle: er sieht vorhanden aus und tut nichts. Der erste
#  Entwurf dieser Migration hatte ihn partiell — das war mein Fehler und ist
#  hier vermerkt, damit er nicht als Sparsamkeit missverstanden und
#  zurueckgebaut wird. Kosten des vollen Index: die Zeilen mit NULL (also die
#  weichen Angaben) stehen mit im Baum. Das ist bei einer Tabelle dieser
#  Groessenordnung ohne Bedeutung.
#
#  'tatzeit_local_idx' bleibt PARTIELL, und zwar zu Recht: er dient der
#  Gleichheitssuche 'WHERE annotation_local_id = ?', und dort nutzt SQLite ihn
#  (gemessen ebenda). Das entspricht auch dem bestehenden 'ann_local_id_idx'
#  auf 'annotations' (db/evidence_db.py:450-452).
ERWARTETE_INDIZES = (
    "tatzeit_ann_idx",
    "tatzeit_local_idx",
    "tatzeit_von_idx",
    "tatzeit_bis_idx",
)

#: Die Anweisungen EINZELN — nicht als ein Skript.
#
#  WARUM NICHT executescript(): Pythons sqlite3 fuehrt vor einem executescript()
#  ein implizites COMMIT aus. Innerhalb der Transaktion des Runners (BEGIN
#  IMMEDIATE) beendet das die Transaktion, und das anschliessende COMMIT des
#  Runners scheitert mit 'cannot commit - no transaction is active'. Der Fehler
#  ist beim ersten Probelauf am 2026-07-26 aufgetreten; er ist hier vermerkt,
#  damit ihn niemand durch ein 'aufgeraeumtes' executescript wieder einbaut.
#  Folge waere schlimmer als ein Absturz: die Tabelle waere angelegt, aber die
#  Registrierung in schema_migrations fehlgeschlagen — die Datei traege eine
#  Struktur, von der sie selbst nichts weiss.
_ANWEISUNGEN = (
    """CREATE TABLE IF NOT EXISTS "annotation_tatzeit" (
    "id"                  INTEGER PRIMARY KEY AUTOINCREMENT,
    "annotation_id"       INTEGER NOT NULL,
    "annotation_local_id" TEXT    DEFAULT NULL,
    "art"                 TEXT    NOT NULL,
    "von_ts"              INTEGER DEFAULT NULL,
    "bis_ts"              INTEGER DEFAULT NULL,
    "genauigkeit"         TEXT    DEFAULT NULL,
    "angabe_schluessel"   TEXT    DEFAULT NULL,
    "angabe_wert"         TEXT    DEFAULT NULL,
    "wortlaut"            TEXT    DEFAULT NULL,
    "quelle"              TEXT    NOT NULL,
    "erfasst_von"         INTEGER NOT NULL,
    "erfasst_at"          INTEGER NOT NULL,
    "version_nr"          INTEGER NOT NULL DEFAULT 1,
    "prev_id"             INTEGER DEFAULT NULL,
    "deleted_at"          INTEGER DEFAULT NULL,

    -- Nur zwei Arten. 'hart' = datierbare Angabe, 'weich' = unscharfe
    -- Beschreibung. Ein dritter Wert waere eine Bedeutung, die niemand
    -- festgelegt hat.
    CHECK ("art" IN ('hart', 'weich')),

    -- Genauigkeit: eine nur aufs Jahr bekannte Tatzeit darf keine tagesgenaue
    -- Frist tragen. Der Vorbehalt 'keine Tagesgenauigkeit' im Parametersatz
    -- deckt +/- 1 Tag ab, nicht +/- 1 Jahr.
    CHECK ("genauigkeit" IS NULL
           OR "genauigkeit" IN ('tag', 'monat', 'jahr', 'unbestimmt')),

    -- Eine HARTE Angabe ohne jeden Zeitwert waere leer und wuerde als
    -- 'festgestellt' gezaehlt, ohne etwas festzustellen.
    CHECK ("art" <> 'hart' OR "von_ts" IS NOT NULL OR "bis_ts" IS NOT NULL),

    -- Eine WEICHE Angabe braucht ihren Schluessel, sonst ist sie nicht
    -- auswertbar und auch nicht wiederfindbar.
    CHECK ("art" <> 'weich' OR "angabe_schluessel" IS NOT NULL),

    -- Eine harte Angabe fuehrt KEINE weichen Felder mit und umgekehrt. Ohne
    -- diese Trennung entstuenden Zeilen, bei denen unklar ist, was gilt.
    CHECK ("art" <> 'hart'
           OR ("angabe_schluessel" IS NULL AND "angabe_wert" IS NULL)),
    CHECK ("art" <> 'weich'
           OR ("von_ts" IS NULL AND "bis_ts" IS NULL)),

    -- Ende nicht vor Beginn. Faengt eine vertauschte Eingabe auf
    -- DATENBANKEBENE — eine Fehlerart, die keine Oberflaechenpruefung
    -- zuverlaessig erwischt.
    CHECK ("von_ts" IS NULL OR "bis_ts" IS NULL OR "bis_ts" >= "von_ts"),

    -- Plausibilitaetsrahmen, WORTGLEICH mit PLAUSIBEL_VON/PLAUSIBEL_BIS aus
    -- management/deadlines/limitation_repo.py (2018-01-01 .. 2027-01-01).
    -- Hier als FROZEN COPY, nicht als Import: eine spaetere Aenderung der
    -- Konstante darf diese Migration nicht rueckwirkend umdeuten. Grundlage
    -- mc 2026-07-25: "Das Forum war zwischen 2019 und 2024 aktiv." Der Rahmen
    -- liegt grosszuegig darum und faengt GROBE Fehlgriffe ab (etwa Epoch 0
    -- oder eine Millisekunden-Zeit).
    CHECK ("von_ts" IS NULL
           OR ("von_ts" >= 1514764800 AND "von_ts" <= 1798761600)),
    CHECK ("bis_ts" IS NULL
           OR ("bis_ts" >= 1514764800 AND "bis_ts" <= 1798761600)),

    -- Woher der Wert stammt, ist Pflicht und darf nicht leer sein. Eine
    -- Tatzeit ohne Herkunft ist kein Beleg (Grundregel: Ueberpruefbarkeit).
    CHECK (LENGTH(TRIM("quelle")) > 0)
)""",
    '''CREATE INDEX IF NOT EXISTS "tatzeit_ann_idx"
    ON "annotation_tatzeit" ("annotation_id")''',
    '''CREATE INDEX IF NOT EXISTS "tatzeit_local_idx"
    ON "annotation_tatzeit" ("annotation_local_id")
    WHERE "annotation_local_id" IS NOT NULL''',
    '''CREATE INDEX IF NOT EXISTS "tatzeit_von_idx"
    ON "annotation_tatzeit" ("von_ts")''',
    '''CREATE INDEX IF NOT EXISTS "tatzeit_bis_idx"
    ON "annotation_tatzeit" ("bis_ts")''',
)

#: Die Probeeinfuegungen der Selbstpruefung: (Beschreibung, Spalten, Werte,
#  soll_scheitern). Sie laufen in einem SAVEPOINT und werden zurueckgerollt.
_PROBEN = (
    ("gueltige harte Angabe",
     "annotation_id, art, von_ts, bis_ts, genauigkeit, quelle, "
     "erfasst_von, erfasst_at",
     (1, "hart", 1600000000, 1600086400, "tag", "Selbstpruefung m002", 1, 1),
     False),
    ("gueltige weiche Angabe",
     "annotation_id, art, angabe_schluessel, angabe_wert, quelle, "
     "erfasst_von, erfasst_at",
     (1, "weich", "relativ_jahre", "vor zwei Jahren",
      "Selbstpruefung m002", 1, 1),
     False),
    ("unbekannte Art",
     "annotation_id, art, von_ts, quelle, erfasst_von, erfasst_at",
     (1, "vielleicht", 1600000000, "Selbstpruefung m002", 1, 1),
     True),
    ("harte Angabe OHNE Zeitwert",
     "annotation_id, art, quelle, erfasst_von, erfasst_at",
     (1, "hart", "Selbstpruefung m002", 1, 1),
     True),
    ("weiche Angabe OHNE Schluessel",
     "annotation_id, art, quelle, erfasst_von, erfasst_at",
     (1, "weich", "Selbstpruefung m002", 1, 1),
     True),
    ("Ende vor Beginn",
     "annotation_id, art, von_ts, bis_ts, quelle, erfasst_von, erfasst_at",
     (1, "hart", 1600086400, 1600000000, "Selbstpruefung m002", 1, 1),
     True),
    ("Zeitwert ausserhalb des Plausibilitaetsrahmens (Epoch 0)",
     "annotation_id, art, von_ts, quelle, erfasst_von, erfasst_at",
     (1, "hart", 0, "Selbstpruefung m002", 1, 1),
     True),
    ("leere Quelle",
     "annotation_id, art, von_ts, quelle, erfasst_von, erfasst_at",
     (1, "hart", 1600000000, "   ", 1, 1),
     True),
    ("unbekannte Genauigkeit",
     "annotation_id, art, von_ts, genauigkeit, quelle, erfasst_von, erfasst_at",
     (1, "hart", 1600000000, "ungefaehr", "Selbstpruefung m002", 1, 1),
     True),
)


def _spalten(con) -> tuple:
    return tuple(str(r[1]) for r in
                 con.execute('PRAGMA table_info("annotation_tatzeit")'))


def _tabelle_existiert(con) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='annotation_tatzeit'").fetchone() is not None


def up(con):
    """
    Legt Tabelle und Indizes an und PRUEFT das Ergebnis sofort nach.

    Der Runner haelt bereits eine Transaktion (BEGIN IMMEDIATE) und rollt bei
    jeder Ausnahme zurueck — hier wird deshalb bewusst NICHT selbst committet.
    """
    # LEICHT-GUARD: Es muss eine 'annotations'-Tabelle geben. Ohne sie ist das
    # hier keine evidence-DB, und eine Tatzeittabelle ohne Annotationen waere
    # ein Fremdkoerper in einer fremden Datei.
    if con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='annotations'").fetchone() is None:
        raise RuntimeError(
            "m002 abgebrochen: Tabelle 'annotations' fehlt — dies ist keine "
            "evidence_<uid>.db. Es wurde nichts angelegt.")

    # BESTEHT DIE TABELLE SCHON, wird sie NICHT stillschweigend uebernommen.
    # Ein abweichender Aufbau waere sonst ab jetzt der 'geprueft' geltende.
    schon_da = _tabelle_existiert(con)
    if schon_da:
        vorhanden = _spalten(con)
        if vorhanden != ERWARTETE_SPALTEN:
            raise RuntimeError(
                "m002 abgebrochen: 'annotation_tatzeit' existiert bereits, "
                "aber mit anderem Aufbau.\n  vorhanden: %s\n  erwartet:  %s\n"
                "Diese Datei ist von Hand zu klaeren; es wurde nichts "
                "geaendert." % (", ".join(vorhanden),
                                ", ".join(ERWARTETE_SPALTEN)))

    for anweisung in _ANWEISUNGEN:
        con.execute(anweisung)

    # -- Selbstpruefung 1: Aufbau --------------------------------------------
    vorhanden = _spalten(con)
    if vorhanden != ERWARTETE_SPALTEN:
        raise RuntimeError(
            "m002 abgebrochen: Spalten nach dem Anlegen unerwartet.\n"
            "  vorhanden: %s\n  erwartet:  %s"
            % (", ".join(vorhanden), ", ".join(ERWARTETE_SPALTEN)))

    indizes = {str(r[0]) for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND tbl_name='annotation_tatzeit'")}
    fehlend = [i for i in ERWARTETE_INDIZES if i not in indizes]
    if fehlend:
        raise RuntimeError(
            "m002 abgebrochen: Indizes fehlen nach dem Anlegen: %s"
            % ", ".join(fehlend))

    # -- Selbstpruefung 2: greifen die CHECKs auch? --------------------------
    # Ein geschriebener, aber unwirksamer CHECK ist schlimmer als keiner, weil
    # man sich auf ihn verlaesst. Die Proben laufen in einem SAVEPOINT und
    # werden restlos zurueckgerollt (auch sqlite_sequence, gemessen 2026-07-26).
    con.execute("SAVEPOINT m002_selbstpruefung")
    try:
        for beschreibung, spalten, werte, soll_scheitern in _PROBEN:
            platz = ", ".join("?" * len(werte))
            sql = ('INSERT INTO "annotation_tatzeit" (%s) VALUES (%s)'
                   % (spalten, platz))
            gescheitert = False
            try:
                con.execute(sql, werte)
            except Exception:                # noqa: BLE001 — jede Ablehnung zaehlt
                gescheitert = True
            if gescheitert != soll_scheitern:
                raise RuntimeError(
                    "m002 abgebrochen: Selbstpruefung '%s' verhielt sich "
                    "falsch. Erwartet: %s. Tatsaechlich: %s. Die "
                    "CHECK-Bedingungen greifen nicht wie hinterlegt."
                    % (beschreibung,
                       "Ablehnung" if soll_scheitern else "Annahme",
                       "Ablehnung" if gescheitert else "Annahme"))
    finally:
        # ZUERST zurueckrollen, DANN freigeben — sonst blieben die Probezeilen
        # stehen. Reihenfolge ist hier nicht Geschmack, sondern SQLite-Semantik.
        con.execute("ROLLBACK TO m002_selbstpruefung")
        con.execute("RELEASE m002_selbstpruefung")

    # Letzte Zusicherung: die Tabelle ist LEER. Diese Migration bringt keine
    # Daten mit, und die Probezeilen duerfen nicht ueberlebt haben.
    rest = con.execute(
        'SELECT COUNT(*) FROM "annotation_tatzeit"').fetchone()[0]
    if int(rest) != 0:
        raise RuntimeError(
            "m002 abgebrochen: 'annotation_tatzeit' enthaelt %s Zeile(n), "
            "erwartet 0. Die Selbstpruefung hat Rueckstand hinterlassen."
            % rest)
