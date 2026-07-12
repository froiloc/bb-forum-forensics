# =============================================================================
# management/migrations/coordinator/m010_external_matters.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Migration M010 — coordinator.db (ADDITIV)
#   Legt die WIEDERVORLAGE EXTERNER VORGAENGE an (Build 385, Welle 1).
#
#   Ein EXTERNER VORGANG ist ein Ermittlungsschritt, den die Ermittlung nicht
#   selbst abschliessen kann und auf dessen Antwort sie WARTET: Bestandsdaten-
#   auskunft beim Provider, Beschluss bei StA/Ermittlungsrichter, Rechtshilfe-
#   ersuchen, Bankauskunft, Amtshilfe, Gutachten, OSINT-Auftrag, Auswertung.
#
#   Der Vorgang blockiert den Fall faktisch — und er GEHT VERLOREN, wenn ihn
#   niemand wiedervorlegt. Genau das ist der Zweck dieser Tabelle: 'wiedervor-
#   lage_am' ist der Tag, an dem der Vorgang wieder auf den Tisch muss.
#
# ABGRENZUNG ZUR PERSONALPLANUNG (mc 2026-07-12) — WICHTIG:
#   Die Kapazitaets-/Abwesenheitsplanung (M008: person_worktime, holiday,
#   availability_entry) bleibt ein EIGENES Schreibmodell. Sie ist etwas
#   grundsaetzlich anderes:
#     M008  Subjekt = person_id  · Zeit = INTERVALL · Nutzlast = MENGE (Minuten/
#           Prozent, wird gerechnet) · Soft-Delete (Planung darf korrigiert
#           werden).
#     M010  Subjekt = user_id (Fall) · Zeit = ZEITPUNKT (verschiebbar) ·
#           Nutzlast = ZUSTAND (Zustandsmaschine) · Abschluss UNWIDERRUFLICH
#           (forensische Historie).
#   Ein gemeinsamer Speicher haette eine Tabelle erzwungen, in der je nach Zeile
#   die Haelfte der Spalten NULL ist — und einen DESTRUKTIVEN Umbau des bereits
#   produktiven M008. Der gemeinsame Verknuepfungspunkt beider Welten ist die
#   ZEIT, und der gehoert in die LESESCHICHT: management/calendar/ fuehrt beide
#   Quellen (und spaeter Fristen, Berichts-Deadlines) zu einer Sicht zusammen.
#   -> "Gemeinsame Leseschicht, getrennte Schreibmodelle."
#
# FORENSISCHE FESTLEGUNGEN (mc 2026-07-12):
#   - 'erledigt'/'erfolglos' sind ENDGUELTIG. Ein Irrtum wird NICHT zurueck-
#     gedreht, sondern durch einen NEUEN Vorgang korrigiert.
#   - Jedes Verschieben der Wiedervorlage verlangt einen GRUND (Pflichtfeld im
#     Repo). Ein stilles Verschieben waere genau die Luecke, die dieses System
#     verhindern soll (Grundregel 1).
#   - Der Kopf ist veraenderlich; die HISTORIE liegt im hash-verketteten
#     audit_log UND gespiegelt im Zeitstrahl case_events (event_kind
#     'external_matter'). 'audit_seq' traegt den Beleg der LETZTEN Aenderung,
#     'created_audit_seq' unveraenderlich den der Anlage.
#   - Wird ein Fall geschlossen, waehrend ein Vorgang offen ist, wird NICHTS
#     automatisch geschlossen (kein stiller Eingriff in Ermittlungsdaten). Der
#     Vorgang erscheint stattdessen ROT als "Fall geschlossen, Vorgang offen".
#
# VOKABULAR IM CODE, nicht in der DDL:
#   'kind' (Vorgangsart) und 'status' werden im Code validiert
#   (external/matter_kinds.py bzw. external/matter_status.py) — bewusst OHNE
#   CHECK-Constraint, damit eine spaetere Vorgangsart additiv bleibt (kein
#   Tabellen-Rebuild an produktiven Daten). Gleiche Linie wie case_events.
#   AUSNAHME: 'status' bekommt dennoch einen CHECK, weil die Zustandsmenge
#   abgeschlossen ist und ein Tippfehler dort einen Vorgang unsichtbar machen
#   wuerde (er faele aus jedem Filter) — das waere ein stiller Beweisverlust.
#
# RBAC-SEED (eingefroren, m005-Prinzip): 'external.view' und 'external.edit'
#   werden hier mit LITERALEN Werten geseedet. Die Migration importiert
#   ABSICHTLICH NICHT rbac/catalog.py — eine Migration muss auch in Jahren noch
#   exakt dasselbe tun, unabhaengig davon, wie der Katalog sich weiterentwickelt.
#   Die GRANTS (wer die Faehigkeit bekommt) sind eine operative Entscheidung der
#   Chef-Ermittlerin (rbac_admin-CLI), NICHT Teil dieses Builds (default-deny).
#
# IDEMPOTENZ: CREATE TABLE/INDEX IF NOT EXISTS + INSERT OR IGNORE + Guard
#             (INFO-No-op beim zweiten Lauf). Inline-Verifikation -> raise ->
#             ROLLBACK im Runner.
# KIND='additive' -> rein additiv, datenneutral, kein precount/postcount.
#
# Beleg: mc 2026-07-12 (Bauschnitt 385 Backend / 386 Frontend).
# Version: v0.7.385 · Build: 385 · 2026-07-12
# =============================================================================

import logging
import sqlite3
import time

logger = logging.getLogger(__name__)

VERSION = 10
NAME = "Wiedervorlage externer Vorgaenge (external_matters) + RBAC-Seed"
KIND = "additive"


# --- external_matters --------------------------------------------------------
#   vorwarnfrist_tage: je Vorgang pflegbar (mc 2026-07-12), Standard 7 Kalender-
#   tage. Eine Bestandsdatenauskunft braucht eine andere Vorwarnzeit als ein
#   Rechtshilfeersuchen.
_DDL_MATTERS = """
CREATE TABLE IF NOT EXISTS external_matters (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL REFERENCES cases(user_id),
    kind              TEXT    NOT NULL,             -- Vokabular: matter_kinds.py
    betreff           TEXT    NOT NULL,
    adressat          TEXT    NOT NULL DEFAULT '',  -- "Telekom AG", "StA Essen"
    aktenzeichen      TEXT,                         -- externes Aktenzeichen
    angefordert_am    TEXT    NOT NULL,             -- ISO YYYY-MM-DD
    wiedervorlage_am  TEXT    NOT NULL,             -- ISO YYYY-MM-DD  <-- Kern
    vorwarnfrist_tage INTEGER NOT NULL DEFAULT 7,   -- Vorwarnung (gelb)
    status            TEXT    NOT NULL DEFAULT 'offen'
                      CHECK(status IN ('offen','beantwortet',
                                       'erledigt','erfolglos')),
    ergebnis          TEXT,                         -- beim Abschluss
    created_by        INTEGER REFERENCES person(id),
    created_at        INTEGER NOT NULL,
    closed_by         INTEGER REFERENCES person(id),
    closed_at         INTEGER,
    audit_seq         INTEGER NOT NULL REFERENCES audit_log(seq),
    created_audit_seq INTEGER NOT NULL REFERENCES audit_log(seq)
)
"""

# Der Faelligkeits-Index traegt die Kernabfrage der Sicht:
# "welche OFFENEN Vorgaenge sind bis <Datum> wiedervorzulegen?"
_IDX_DUE = (
    "ix_external_due",
    "CREATE INDEX IF NOT EXISTS ix_external_due "
    "ON external_matters (status, wiedervorlage_am)",
)
_IDX_CASE = (
    "ix_external_case",
    "CREATE INDEX IF NOT EXISTS ix_external_case "
    "ON external_matters (user_id, wiedervorlage_am)",
)

_INDICES = (_IDX_DUE, _IDX_CASE)
_TABLES = ("external_matters",)

# --- RBAC-Seed (EINGEFROREN — nie aus catalog.py importieren) ----------------
_SEED_CAPS = (
    ("external.view", "Externe Vorgaenge sehen",
     "Wiedervorlage externer Vorgaenge (Beschluesse, Auskuenfte) lesen."),
    ("external.edit", "Externe Vorgaenge pflegen",
     "Externe Vorgaenge anlegen, wiedervorlegen und abschliessen."),
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


def up(con: sqlite3.Connection) -> None:
    done = (all(_table_exists(con, t) for t in _TABLES)
            and all(_index_exists(con, ix) for ix, _ in _INDICES)
            and all(_cap_exists(con, c) for c, _l, _d in _SEED_CAPS))
    if done:
        logger.info("M010: external_matters + RBAC-Seed bereits vorhanden "
                    "— No-op.")
        return

    # Vorbedingung: M006 (rbac_capability) muss angewandt sein. Fehlt sie, ist
    # das ein Aufbaufehler und KEIN Grund, den Seed still zu ueberspringen.
    if not _table_exists(con, "rbac_capability"):
        raise RuntimeError(
            "M010: rbac_capability fehlt — M006 ist nicht angewandt. "
            "Reihenfolge der Migrationen pruefen.")

    con.execute(_DDL_MATTERS)
    for _name, ddl in _INDICES:
        con.execute(ddl)

    now = int(time.time())
    for code, label, desc in _SEED_CAPS:
        con.execute(
            "INSERT OR IGNORE INTO rbac_capability "
            "(code, label, description, created_at) VALUES (?, ?, ?, ?)",
            (code, label, desc, now),
        )

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -------
    for t in _TABLES:
        if not _table_exists(con, t):
            raise RuntimeError("M010: Tabelle '%s' fehlt nach up()." % t)
    for ix, _ddl in _INDICES:
        if not _index_exists(con, ix):
            raise RuntimeError("M010: Index '%s' fehlt nach up()." % ix)
    for code, _l, _d in _SEED_CAPS:
        if not _cap_exists(con, code):
            raise RuntimeError(
                "M010: Faehigkeit '%s' fehlt nach dem Seed." % code)

    logger.info("M010: external_matters angelegt; Faehigkeiten %s geseedet.",
                ", ".join(c for c, _l, _d in _SEED_CAPS))
