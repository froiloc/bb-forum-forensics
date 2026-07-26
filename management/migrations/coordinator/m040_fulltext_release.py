# =============================================================================
# management/migrations/coordinator/m040_fulltext_release.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B561)
# =============================================================================
#
#  ┌──────────────────────────────────────────────────────────────────────────┐
#  │  ⚠  SPERRVERMERK — DIESE MIGRATION IST NOCH NICHT EINZUSPIELEN.          │
#  │                                                                          │
#  │  ENTSCHEIDUNG mc 2026-07-26: die Migrationen der Instanzen werden        │
#  │  STRIKT SERIALISIERT. Instanz A liefert m035-m039 ZUERST; erst danach    │
#  │  bekommt diese Datei ihre endgueltige Nummer.                            │
#  │                                                                          │
#  │  GRUND (reproduziert, tools/diag_migrationsluecke.py; Vermerk            │
#  │  management/Vermerk_Migrationsluecke_Parallelbetrieb_v0_1.md):           │
#  │  MigrationRunner fuehrt einen HOECHSTSTAND (MAX(version)) und keine      │
#  │  Menge angewandter Versionen (runner.py:97-123). Laeuft m040 VOR         │
#  │  m035-m039, werden diese Migrationen fuer immer UEBERSPRUNGEN — ohne   │
#  │  ohne Fehler, ohne Warnung, ohne Registry-Eintrag. run() meldet dann     │
#  │  "keine ausstehenden Migrationen" fuer einen Zustand, in dem sieben      │
#  │  Schemaaenderungen fehlen.                                               │
#  │                                                                          │
#  │  VOR DEM EINSPIELEN AUSFUEHREN:                                          │
#  │      python tools/pruefe_migrationskette.py --db <coordinator.db>        │
#  │  Der Befehl meldet jede Migration, die im Paket liegt, aber nicht in     │
#  │  schema_migrations steht. Exit 0 = unbedenklich.                         │
#  │                                                                          │
#  │  DIE NUMMER IST VORLAEUFIG. Bis diese Datei in IRGENDEINER Datenbank     │
#  │  gelaufen ist, kostet ihre Umbenennung nichts. Danach ist sie            │
#  │  unantastbar.                                                            │
#  └──────────────────────────────────────────────────────────────────────────┘
#
# Migration M040 — coordinator.db (ADDITIV)
#   Legt das Datenmodell der INHALTSFREIGABE fuer die falluebergreifende
#   Volltextsuche an:
#     * fulltext_zweck   — Katalog der Zweckcodes (geseedet aus einer
#                          EINGEFRORENEN Kopie von zweck_vokabular.py).
#     * fulltext_release — wer darf den Inhalt WELCHES fremden Falls sehen,
#                          zu welchem Zweck, erteilt von wem, wann, Widerruf.
#   und seedet die dafuer noetige Faehigkeit 'fulltext.release'.
#
# ── WAS EINE FREIGABE IST (Modell B, Entscheidungen mc §1 E-1) ──────────────
#
#   Die Suche ist ZWEISTUFIG. Stufe 1 (Trefferlage: Fall, Trefferzahl, Art,
#   Zeitraum — OHNE Textausschnitt) ist fuer alle Berechtigten frei. Stufe 2
#   (der Inhalt) ist frei bei den EIGENEN Faellen und sonst GESPERRT.
#
#   Diese Tabelle fuehrt die Aufhebung dieser Sperre. Sie ist der Ort, an dem
#   nachlesbar ist, WER den Arbeitsstand eines FREMDEN Verfahrens im Volltext
#   lesen durfte und WARUM. In diesen Texten koennen Klarnamen identifizierter
#   Personen, Opferangaben und die Bewertung von Kolleg:innen stehen
#   (Klaerung §3) — nichts davon ist unzulaessig zu lesen, aber nichts davon
#   soll OHNE ANLASS gelesen werden. Der Anlass entsteht erst durch den
#   Treffer, und ab hier ist er belegt.
#
# ── EINE FREIGABE JE FALL UND PERSON, NICHT JE ABFRAGE ─────────────────────
#
#   Ausdrueckliche Abfederung des bekannten Risikos aus E-1: die
#   Chef-Ermittlerin wird sonst zum Nadeloehr. Der Schluessel ist deshalb
#   (subject_id, person_id) und nicht (Abfrage).
#
#   Durchgesetzt wird das mit einem PARTIELLEN UNIQUE-INDEX ueber die AKTIVEN
#   Zeilen. Das ist die ABWEICHUNG von m027 (escalation_ack), wo bewusst KEIN
#   solcher Index gesetzt wurde — dort konnte subject_id NULL sein, und zwei
#   NULL gelten in einem SQLite-UNIQUE-Index als verschieden; der Index haette
#   fuer die systemische Regel nicht gegriffen und dabei falsche Sicherheit
#   vorgetaeuscht. HIER sind BEIDE Schluesselspalten NOT NULL. Damit greift
#   der Index vollstaendig, und die Fachregel steht in der DATENBANK statt nur
#   in einem Repository. Das Repo prueft trotzdem zusaetzlich INNERHALB der
#   Transaktion — nicht zur Sicherheit, sondern fuer die verstaendliche
#   Fehlermeldung.
#
# ── WIDERRUF STATT LOESCHUNG (Linie M022/M027/Build 504) ───────────────────
#
#   Eine Freigabe wird NIE geloescht. Sie wird mit Pflichtgrund WIDERRUFEN;
#   die Zeile bleibt als Beleg stehen. Die Erkenntnis "diese Person durfte
#   einmal in diesen Fall sehen" ist die aufsichtsrelevante — sie zu loeschen
#   waere ein stiller Beweisverlust (Grundregel 1). Danach darf dieselbe
#   Person fuer denselben Fall erneut freigegeben werden.
#
# ── ZWEI SPALTEN FUER DEN ZWECK, MIT FREMDSCHLUESSEL ───────────────────────
#
#   zweck_code REFERENCES fulltext_zweck(code) — ein Tippfehler wird von der
#   DATENBANK abgelehnt, nicht erst von der Anwendung. Das ist der Grund fuer
#   die Katalogtabelle (Entscheidung mc: "Die Codeliste ist eine weitere
#   Katalogtabelle"). Ausfuehrliche Begruendung samt Abgrenzung gegen die
#   zusammengesetzte Ablageform der Tatzeit im Kopf von
#   management/search/zweck_vokabular.py.
#
#   Der CHECK erzwingt: Freitext GENAU DANN, wenn der Code ihn verlangt. Er
#   steht in der TABELLE und nicht nur im Code — eine Regel, die nur die
#   Anwendung kennt, gilt genau so lange, wie alle Schreibpfade durch die
#   Anwendung laufen.
#
# ── SENSIBILITAET ──────────────────────────────────────────────────────────
#
#   'begruendung', 'zweck_freitext' und 'revoke_reason' sind Freitexte und
#   stehen NIEMALS im audit_log-Payload (Muster M018/M022/M027) — dort nur
#   FAKTEN und Textlaengen.
#
# ── EINGEFRORENER SEED (m005-Prinzip) ──────────────────────────────────────
#
#   _SEED_ZWECKE und _SEED_CAPS sind EINGEFRORENE Kopien und importieren
#   zweck_vokabular.py / catalog.py NICHT. Eine bereits angewandte Migration
#   darf ihr Laufzeitverhalten nie aendern (sonst Nichtdeterminismus trotz
#   gleicher Checksumme). Die Bruecke ist der Test FR02
#   (tests/test_management_search_release.py): er verankert
#   "M040-Seed == zweck_vokabular.py" ZUR BAUZEIT.
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + INSERT OR IGNORE + Guard +
#   Inline-Verifikation.
# MIGRATIONSKLASSE: rein additiv, NUR coordinator.db, NEUE Tabellen. Keine
#   bestehende Zeile wird angefasst, keine Spalte umgebaut; die Ermittler-
#   Ergebnisdatenbanken (evidence_/forensic_/assets_<uid>.db) sind NICHT
#   beruehrt. Der Migrationsvorbehalt seit 01.07.2026 greift damit nicht —
#   es kann kein bestehendes Wissen verloren gehen.
#
# Beleg: Entscheidungen mc 2026-07-26 §1 (E-1/E-3); Klaerung AP-3E v0.2 §5;
#        Bauplan AP-3E v0.1 §5.1.
# Version: v0.8.561 · Build: 561 · 2026-07-26
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 40
NAME = "Inhaltsfreigabe der Volltextsuche (fulltext_zweck, fulltext_release)"
KIND = "additive"


_DDL_ZWECK = """
CREATE TABLE IF NOT EXISTS fulltext_zweck (
    code             TEXT    PRIMARY KEY,
    label            TEXT    NOT NULL,
    beschreibung     TEXT    NOT NULL,
    -- 1 = zu diesem Code ist ein Freitext PFLICHT ('sonstiges').
    freitext_pflicht INTEGER NOT NULL DEFAULT 0
                     CHECK(freitext_pflicht IN (0, 1)),
    created_at       INTEGER NOT NULL
)
"""

_DDL_RELEASE = """
CREATE TABLE IF NOT EXISTS fulltext_release (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    -- WESSEN Fall freigegeben wird und WEM. Beide NOT NULL — deshalb greift
    -- der partielle UNIQUE-Index unten vollstaendig (anders als in M027).
    subject_id       INTEGER NOT NULL,
    person_id        INTEGER NOT NULL REFERENCES person(id),
    -- Zweck als CODE mit Fremdschluessel + optionalem Freitext.
    zweck_code       TEXT    NOT NULL REFERENCES fulltext_zweck(code),
    zweck_freitext   TEXT,
    -- Pflichttext der erteilenden Stelle (SENSIBEL — nie im Audit-Payload).
    begruendung      TEXT    NOT NULL,
    granted_by       INTEGER NOT NULL REFERENCES person(id),
    granted_at       INTEGER NOT NULL,
    audit_seq        INTEGER NOT NULL REFERENCES audit_log(seq),
    is_active        INTEGER NOT NULL DEFAULT 1
                     CHECK(is_active IN (0, 1)),
    revoked_at       INTEGER,
    revoked_by       INTEGER REFERENCES person(id),
    revoke_reason    TEXT,
    revoke_audit_seq INTEGER REFERENCES audit_log(seq),
    -- Freitext GENAU DANN, wenn der Code ihn verlangt. Die Regel steht in
    -- der Tabelle, nicht nur im Repository.
    CHECK ((zweck_code = 'sonstiges'
            AND zweck_freitext IS NOT NULL AND TRIM(zweck_freitext) <> '')
        OR (zweck_code <> 'sonstiges' AND zweck_freitext IS NULL))
)
"""

# HOECHSTENS EINE GUELTIGE FREIGABE je Fall und Person (E-1: nicht je Abfrage,
# sonst wird die Chef-Ermittlerin zum Nadeloehr). Partiell ueber is_active=1,
# damit widerrufene Zeilen als Beleg stehenbleiben duerfen und eine erneute
# Freigabe moeglich ist.
_IDX_AKTIV = (
    "ux_fulltext_release_aktiv",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_fulltext_release_aktiv "
    "ON fulltext_release (subject_id, person_id) WHERE is_active = 1",
)
# "Was darf diese Person sehen?" — der Zugriffsweg der Stufe-2-Pruefung, der
# bei JEDER Inhaltsabfrage laeuft.
_IDX_PERSON = (
    "ix_fulltext_release_person",
    "CREATE INDEX IF NOT EXISTS ix_fulltext_release_person "
    "ON fulltext_release (person_id, is_active)",
)
# "Wer darf in diesen Fall sehen?" — die Aufsichtsrichtung.
_IDX_FALL = (
    "ix_fulltext_release_fall",
    "CREATE INDEX IF NOT EXISTS ix_fulltext_release_fall "
    "ON fulltext_release (subject_id, is_active)",
)

_INDICES = (_IDX_AKTIV, _IDX_PERSON, _IDX_FALL)
_TABLES = ("fulltext_zweck", "fulltext_release")

# --- Zweckkatalog (EINGEFROREN — nie aus zweck_vokabular.py importieren) -----
_SEED_ZWECKE = (
    ("kreuzbezug_nickname", "Kreuzbezug zu einem Nickname",
     "Pruefen, ob ein im eigenen Fall aufgetretener Nickname in einem "
     "anderen Verfahren bereits aufgefallen ist. Der Hauptzweck der "
     "Funktion.", 0),
    ("alias_pruefung", "Alias-/Identitaetspruefung",
     "Pruefen, ob ein Alias oder eine Schreibvariante bereits einer "
     "Identitaetsgruppe zugeordnet wurde (Anschluss an den "
     "Alias-Katalog aus AP-2A).", 0),
    ("wiedervorlage", "Wiedervorlage / Nachschau",
     "Erneute Nachschau zu einem frueher bearbeiteten Begriff, etwa vor "
     "einer Wiedervorlage oder vor der Abgabe an die StA.", 0),
    ("sonstiges", "Sonstiges (Begruendung erforderlich)",
     "Ein Zweck, den die Liste nicht abbildet. Der Freitext ist PFLICHT. "
     "Der Anteil dieses Codes ist die Kennzahl dafuer, ob die Liste "
     "vollstaendig ist — steigt er, fehlt ein Code.", 1),
)

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ---------------
# EIGENES Recht und ausdruecklich NICHT 'release.grant' (M016): dort geht es
# um die EXTERNE Fallfreigabe an eine andere Dienststelle — eine andere
# Zweckbindung und ein anderer Empfaengerkreis. Eine Wiederverwendung waere
# kein Sparen, sondern ein Zweckbindungsverstoss (dieselbe Abgrenzung wie
# tatzeit.edit gegenueber results.edit in M032). Die Gegenrichtung
# (Wiederverwendung von crossref.view in M022) war richtig, weil es dort
# dieselbe Erkenntnisart betraf.
#
# 'evidence.fulltext_search' — das Recht, ueberhaupt zu suchen — ist bereits
# seit M006 im Katalog (m006_rbac_schema.py:187) und wird hier NICHT erneut
# geseedet.
_SEED_CAPS = (
    ("fulltext.release", "Inhaltsfreigabe der Volltextsuche erteilen",
     "Einer Person den Zugriff auf den Trefferinhalt (Stufe 2) eines ihr "
     "NICHT zugewiesenen Falls erteilen oder widerrufen. Auditiert, mit "
     "Pflichtbegruendung; eine Freigabe je Fall und Person."),
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _index_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        (name,)).fetchone() is not None


def _cap_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM rbac_capability WHERE code=?",
        (code,)).fetchone() is not None


def _zweck_exists(con: sqlite3.Connection, code: str) -> bool:
    return con.execute(
        "SELECT 1 FROM fulltext_zweck WHERE code=?",
        (code,)).fetchone() is not None


def up(con: sqlite3.Connection) -> None:
    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M040: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    done = (all(_table_exists(con, t) for t in _TABLES)
            and all(_index_exists(con, ix) for ix, _ in _INDICES)
            and all(_zweck_exists(con, z) for z, _l, _b, _f in _SEED_ZWECKE)
            and all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS))
    if done:
        logger.info("M040: fulltext_release bereits vorhanden — No-op.")
        return

    now = int(time.time())

    # Reihenfolge: erst der Katalog, dann die Tabelle mit dem Fremdschluessel
    # darauf. Umgekehrt liefe es zwar durch (SQLite prueft FK erst beim
    # Schreiben), aber die Lesbarkeit der Migration ist hier das Argument.
    con.execute(_DDL_ZWECK)
    for code, label, besch, pflicht in _SEED_ZWECKE:
        con.execute(
            "INSERT OR IGNORE INTO fulltext_zweck "
            "(code, label, beschreibung, freitext_pflicht, created_at) "
            "VALUES (?, ?, ?, ?, ?)", (code, label, besch, pflicht, now))

    con.execute(_DDL_RELEASE)
    for _name, ddl in _INDICES:
        con.execute(ddl)

    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now))

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    for t in _TABLES:
        if not _table_exists(con, t):
            raise RuntimeError("M040: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M040: Index '%s' fehlt nach up()." % ix)
    for code, _l, _b, _f in _SEED_ZWECKE:
        if not _zweck_exists(con, code):
            raise RuntimeError("M040: Zweckcode '%s' fehlt nach dem Seed."
                               % code)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError("M040: Faehigkeit '%s' fehlt nach dem Seed."
                               % code)

    logger.info("M040: fulltext_zweck (%d Codes) + fulltext_release + %d "
                "Indizes angelegt, Faehigkeit %s geseedet.",
                len(_SEED_ZWECKE), len(_INDICES),
                ", ".join(c for c, _l, _d in _SEED_CAPS))
