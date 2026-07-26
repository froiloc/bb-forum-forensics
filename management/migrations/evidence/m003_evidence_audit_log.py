# =============================================================================
# management/migrations/evidence/m003_evidence_audit_log.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Migration M003 — evidence_<uid>.db (Build 533)
#   Legt die hash-verkettete Audit-Tabelle 'evidence_audit_log' an und schreibt
#   die Genesis-Zeile als Kettenanker.
#
#   Reihenfolge der Kette nach M003:
#     seq=1  genesis  (von up() geschrieben)
#   Danach folgt jeder auditierte Schreibvorgang (TATZEIT_SET, TATZEIT_CLEARED)
#   ueber management/gateway/evidence_writer.py.
#
# ── WARUM DIESE MIGRATION UEBERHAUPT NOETIG IST ──────────────────────────────
#
#   Recherche 2026-07-26: In evidence_<uid>.db gab es bis Build 532 KEINEN
#   Beleg fuer fachliche Schreibvorgaenge. Das vollstaendige Schema
#   (db/evidence_db.py:231-459) fuehrt 16 Tabellen; die beiden mit "Audit" im
#   Kommentar — report_opened (:386) und lock_takeover_requests (:358) — sind
#   zweckfremd. save_annotation (:847-949) schreibt und committet direkt
#   (:947), ohne Gateway und ohne Beleg.
#
#   ENTSCHEIDUNG mc 2026-07-26: Fuer die Tatzeit ist das nicht tragbar, weil
#   aus ihr eine Verjaehrungsfrist gerechnet wird und deren Folge unumkehrbar
#   ist. Die Alternative — Beleg per Best-Effort in coordinator.db, Muster
#   management/server/management_app.py:2316-2337 — wurde VERWORFEN, weil ein
#   Fehlschlag dort nur geloggt wird (:2333-2335). Das ist das stille
#   Ueberspringen eines Belegs, das Grundregel 1 verbietet.
#
# ── ADDITIV UND DATENNEUTRAL ─────────────────────────────────────────────────
#
#   Es wird eine NEUE Tabelle angelegt und KEINE bestehende angefasst. Kein
#   UPDATE, kein ALTER TABLE, kein DELETE. 'annotations' und
#   'annotation_tatzeit' bleiben inhaltlich unveraendert — EA03 weist das mit
#   einem Inhaltshash NACH, statt es zu behaupten (Muster TZ04 aus m002).
#   Der Migrationsvorbehalt ab 01.07.2026 ist damit gewahrt; die Migration
#   laeuft ueber die bestehende Fleet, die fuer Beweis-DB-Arten IMMER ein
#   Backup erzwingt (management/migration_fleet/catalog.py:_requires_backup).
#
# ── WARUM HIER DIE KLASSE IMPORTIERT WIRD (Abweichung vom m005-Prinzip) ──────
#
#   Reine Seed-Migrationen kopieren ihre Werte EINGEFROREN, statt den Katalog
#   zu importieren (m031:9-12). Fuer die Audit-Kette gilt das ausdruecklich
#   NICHT, und der Praezedenzfall steht schon im Baum: die coordinator-Kette
#   wird von m001_audit_log.py:22-40 genauso angelegt — mit Import von
#   AuditLog und Aufruf von create_schema()/write_genesis().
#
#   Der Grund ist nicht Bequemlichkeit. Bei einem Katalog waere eine spaetere
#   Aenderung eine INHALTLICHE Umdeutung alter Zeilen; bei der Audit-Kette ist
#   die Klasse die DEFINITION der Kette selbst. Waere die DDL hier kopiert und
#   liefe sie je auseinander, entstuende eine Tabelle, in die der Schreibpfad
#   nicht mehr passt — und das faellt erst beim ersten Beleg auf. Ein Import
#   macht die Divergenz strukturell unmoeglich.
#
# ── KEIN executescript() ─────────────────────────────────────────────────────
#
#   Pythons sqlite3 committet vor executescript() IMPLIZIT und beendet damit
#   die Transaktion des Runners. Die Folge waere schlimmer als ein Absturz: die
#   Tabelle angelegt, die Registrierung in 'schema_migrations' nicht — die
#   Datei truege eine Struktur, von der sie selbst nichts weiss. Der Fehler ist
#   in Build 532 einmal passiert (m002-Kopf, Punkt 5a); EA09 haelt den
#   Quelltext fest, damit er nicht durch spaeteres "Aufraeumen" zurueckkommt.
#
# ── MIGRATION_APPLIED STEHT NICHT IN DIESER KETTE ────────────────────────────
#
#   Der MigrationRunner schreibt MIGRATION_APPLIED nur, wenn ihm ein AuditLog
#   uebergeben wurde (runner.py). Fuer den evidence-Strang laeuft er ohne
#   (audit=None, s. tests/test_management_migration_executor.py:149). Die
#   evidence-Kette enthaelt nach diesem Lauf also GENAU eine Zeile: die
#   Genesis. Das ist kein Versehen — der Beleg fuer die Migration selbst liegt
#   in 'schema_migrations' und im Fleet-Protokoll der coordinator.db, wo die
#   Leitung ihn erwartet. EA04 haelt die Kettenlaenge 1 fest.
#
# KIND='additive' -> kein precount/postcount/verify noetig.
# Version: v0.8.533 · Build: 533 · 2026-07-26
# =============================================================================

import logging
import sqlite3
import time

from management.audit.evidence_audit_log import EvidenceAuditLog

logger = logging.getLogger(__name__)

VERSION = 3
NAME = "evidence_audit_log + Genesis (Hash-Kette in der Beweismitteldatenbank)"
KIND = "additive"

#: Der erwartete Spaltensatz — Wahrheit fuer die Bestandspruefung unten UND
#  fuer EA02. Muss deckungsgleich mit EvidenceAuditLog.DDL_TABLE sein.
ERWARTETE_SPALTEN = (
    "seq",
    "ts",
    "actor_id",
    "event_type",
    "target_type",
    "target_id",
    "content",
    "meta",
    "prev_hash",
    "row_hash",
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _spalten(con: sqlite3.Connection, table: str) -> tuple:
    return tuple(
        r[1] for r in con.execute('PRAGMA table_info("%s")' % table).fetchall()
    )


def up(con: sqlite3.Connection) -> None:
    # --- Abbruchbedingung 1: ist das ueberhaupt eine evidence-DB? -----------
    #   Ohne 'annotations' ist es keine. Lieber ein Abbruch ohne Teilzustand
    #   als eine Audit-Tabelle in einer fremden Datei (Muster m002, TZ08).
    if not _table_exists(con, "annotations"):
        raise RuntimeError(
            "M003: Tabelle 'annotations' fehlt — das ist keine "
            "evidence_<uid>.db. Abbruch ohne Aenderung."
        )

    # --- Abbruchbedingung 2: fremder Bestand wird NICHT uebernommen ---------
    #   Existiert die Tabelle schon mit ANDEREM Aufbau, waere sie ab diesem
    #   Lauf die offiziell geprüfte — obwohl niemand sie geprueft hat.
    if _table_exists(con, EvidenceAuditLog.TABLE):
        vorhanden = _spalten(con, EvidenceAuditLog.TABLE)
        if vorhanden != ERWARTETE_SPALTEN:
            raise RuntimeError(
                "M003: '%s' existiert bereits mit abweichendem Aufbau %r "
                "(erwartet %r). Abbruch statt stillschweigender Uebernahme."
                % (EvidenceAuditLog.TABLE, vorhanden, ERWARTETE_SPALTEN)
            )

    # --- 1) Schema (Tabelle + Append-only-Trigger), idempotent --------------
    EvidenceAuditLog.create_schema(con)

    # --- 2) Genesis-Zeile als Kettenanker -----------------------------------
    #   Nur, wenn die Kette leer ist. Ein zweiter Lauf (M003 bereits angewandt,
    #   Datei aus einem Backup wiedereingespielt) darf keine zweite Genesis
    #   schreiben — write_genesis() lehnt das ohnehin ab, aber der Guard sagt
    #   es freundlicher und haelt die Migration idempotent (EA06).
    audit = EvidenceAuditLog(con)
    _prev_hash, prev_seq = audit.tip()
    if prev_seq == 0:
        audit.write_genesis(
            {
                "db": "evidence",
                "schema": "M003",
                "created_at": int(time.time()),
            }
        )
        logger.info("M003: evidence_audit_log angelegt, Genesis geschrieben.")
    else:
        logger.info("M003: Kette bereits vorhanden (seq=%d) — kein Genesis.",
                    prev_seq)

    # --- 3) Inline-Verifikation ---------------------------------------------
    #   Ein Verstoss wirft und rollt damit den GESAMTEN Lauf zurueck. Geprueft
    #   wird die WIRKUNG, nicht die blosse Existenz: die Kette muss sich
    #   nachrechnen lassen.
    if _spalten(con, EvidenceAuditLog.TABLE) != ERWARTETE_SPALTEN:
        raise RuntimeError(
            "M003: Spaltensatz nach dem Anlegen unerwartet: %r"
            % (_spalten(con, EvidenceAuditLog.TABLE),)
        )
    res = audit.verify_chain()
    if not res.ok:
        raise RuntimeError(
            "M003: Die frisch angelegte Kette verifiziert nicht: %s" % res.detail
        )
