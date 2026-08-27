# =============================================================================
# management/migrations/coordinator/m039_person_namensteile.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Build 725)
# =============================================================================
# Zweck:
#   Drei neue Spalten auf person:
#     1. person.first_name (TEXT NULL) - AD-Attribut 'givenName'
#     2. person.last_name  (TEXT NULL) - AD-Attribut 'sn'
#     3. person.rank       (TEXT NULL) - AD-Attribut 'title' (Dienstgrad)
#
# DER ANLASS (Auftrag Chef-Ermittlerin, 27.08.2026, Anforderung 1):
#   "Der Name des Ermittlers, der die Annotation erstellt hat, soll mit
#   Nachname (ohne Vorname) anstelle des SAMAccountName angegeben werden."
#   Der Bericht kennt bis heute nur 'annotations.created_by' - das Kuerzel.
#
# WARUM NICHT EINFACH display_name ZERLEGEN. Weisung Alex (27.08.2026):
#   Vorname, Nachname und Dienstgrad kommen aus dem Active Directory
#   ('givenName', 'sn', 'title') und werden dort GETRENNT gefuehrt. Sie hier
#   getrennt zu speichern heisst, sie aus der Quelle zu nehmen statt sie aus
#   einer Anzeigezeichenkette zurueckzurechnen. Eine Zerlegung von
#   display_name ist eine Vermutung ueber eine Schreibweise; ein
#   AD-Attribut ist ein Beleg.
#
#   Der Ruecksetzweg bleibt trotzdem bestehen und ist ausdruecklich Teil der
#   Weisung: solange die Felder leer sind (Bestand vor dem naechsten
#   AD-Abgleich), wird der Nachname aus display_name bis zum ersten Komma
#   genommen ("Muster, Max" -> "Muster"). Diese Regel steht NICHT hier,
#   sondern in report_render/ermittler_namen.py - eine angewandte Migration
#   darf ihr Verhalten nie aendern (m005-Prinzip), und die Regel wird sich
#   aendern, sobald der AD-Abgleich einmal durchgelaufen ist.
#
# DER DIENSTGRAD WIRD VORANGESTELLT, NICHT EINGEBAUT (Weisung Alex): ist
#   'rank' leer, entfaellt er ersatzlos; sonst steht er vor dem Nachnamen
#   ("KHK Muster"). Deshalb ist er eine EIGENE Spalte und nicht Teil von
#   last_name - wer ihn weglassen will, muss ihn trennen koennen.
#
# WARUM NULL UND NICHT '' ALS VORGABE: NULL sagt "nie befuellt worden",
#   Leerstring sagt "im AD leer". Bei 'title' ist das ein echter Unterschied
#   - ein Mitarbeiter ohne Dienstgrad ist kein Mitarbeiter ohne Abgleich.
#   Der Lesepfad behandelt beides gleich (kein Dienstgrad), die Datenbank
#   bewahrt die Unterscheidung fuer die Frage "ist der Abgleich gelaufen?".
#
# MIGRATIONSVORBEHALT (ab 01.07.2026) - unbedenklich, und zwar nachpruefbar:
#     * NUR coordinator.db. evidence_<uid>.db, forensic_<uid>.db und
#       assets_<uid>.db werden NICHT beruehrt. In coordinator.db speichern
#       Ermittler keine Ergebnisse (Projektregeln) - es kann kein Wissen
#       verloren gehen.
#     * REIN ADDITIV. Drei Spalten mit NULL-Vorgabe. Keine Spalte umbenannt,
#       keine bestehende veraendert, keine Zeile angefasst. display_name
#       bleibt unberuehrt und bleibt der Anzeigename.
#     * Die Zeilenzahl von person wird vor und nach den ALTERs verglichen
#       (Muster M020) - Verlustfreiheit gemessen, nicht behauptet.
#
# IDEMPOTENZ: Spalten-Guards ueber PRAGMA table_info.
#
# NUMMER: 39 - naechste freie nach M038 (Build 700). Kette lueckenlos 1-39.
# Version: v0.8.725 - Build: 725 - 2026-08-27
# =============================================================================

import logging
import sqlite3

logger = logging.getLogger(__name__)

VERSION = 39
NAME = "person.first_name/last_name/rank (AD: givenName/sn/title)"
KIND = "additive"

#: Neue Spalten auf person: (Name, DDL-Fragment nach ADD COLUMN).
#  Alle drei NULL-bar: der Bestand hat sie nicht, und ein NOT NULL mit
#  Leerstring-Default wuerde "nie befuellt" und "im AD leer" verwischen.
_NEW_COLUMNS = (
    ("first_name", "first_name TEXT"),
    ("last_name", "last_name TEXT"),
    ("rank", "rank TEXT"),
)


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _cols(con: sqlite3.Connection, table: str) -> list:
    return [r[1] for r in con.execute(
        "PRAGMA table_info(%s)" % table).fetchall()]


def up(con: sqlite3.Connection) -> None:
    # --- Vorbedingung: laut scheitern statt halb anlegen -------------------
    if not _table_exists(con, "person"):
        raise RuntimeError(
            "M039: Tabelle 'person' fehlt - Basisschema/M005 nicht "
            "angewandt. Reihenfolge der Migrationen pruefen.")

    have = set(_cols(con, "person"))
    if all(name in have for name, _ddl in _NEW_COLUMNS):
        logger.info("M039: person-Namensspalten bereits vorhanden - No-op.")
        return

    # Verlustfreiheits-Anker vor den ALTERs. Die Hooks precount/verify des
    # Runners laufen nur bei KIND='destructive'; diese Migration ist additiv,
    # also wird die Invariante HIER inline geprueft (Muster M020).
    n_before = int(con.execute("SELECT COUNT(*) FROM person").fetchone()[0])

    for name, ddl in _NEW_COLUMNS:
        if name not in have:
            con.execute("ALTER TABLE person ADD COLUMN %s" % ddl)

    # --- Inline-Verifikation (Verstoss -> raise -> ROLLBACK im Runner) -----
    have_after = set(_cols(con, "person"))
    for name, _ddl in _NEW_COLUMNS:
        if name not in have_after:
            raise RuntimeError(
                "M039: Spalte person.%s fehlt nach up()." % name)

    # display_name darf NICHT angetastet worden sein - es bleibt der
    # Anzeigename und der Rueckfallweg fuer den Nachnamen.
    if "display_name" not in have_after:
        raise RuntimeError(
            "M039: person.display_name fehlt nach up() - diese Migration "
            "darf sie nicht beruehren.")

    n_after = int(con.execute("SELECT COUNT(*) FROM person").fetchone()[0])
    if n_before != n_after:
        raise RuntimeError(
            "M039: person-Zeilenzahl veraendert (%d -> %d) - die Migration "
            "haette rein additiv sein muessen." % (n_before, n_after))

    logger.info(
        "M039: person um first_name/last_name/rank erweitert (%d Zeilen "
        "unveraendert, Befuellung erfolgt beim naechsten AD-Abgleich).",
        n_after)
