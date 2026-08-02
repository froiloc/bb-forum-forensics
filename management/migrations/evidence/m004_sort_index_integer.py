# =============================================================================
# management/migrations/evidence/m004_sort_index_integer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Migration
# =============================================================================
# Migration M004 — evidence_<uid>.db (Build 660, Vorgang 99bf0eb5)
#   Aendert den Typ von 'report_block_order.sort_index' von TEXT auf INTEGER.
#
# ── WORUM ES GEHT, UND WARUM ES SCHWER WIEGT ────────────────────────────────
#
#   Der Prepper legte die Spalte bis Version 0.1.128 als TEXT an, der
#   Webserver deklariert sie als INTEGER. Weil beide Seiten mit
#   'CREATE TABLE IF NOT EXISTS' arbeiten und der Prepper zuerst laeuft,
#   gewinnt sein TEXT — alle bisher erzeugten Falldatenbanken tragen ihn.
#
#   TEXT-Affinitaet heisst lexikographischer Vergleich. Gemessen am
#   2026-07-30 und erneut am 2026-08-02:
#
#       ORDER BY sort_index ueber 1,2,9,10,11,20
#           TEXT     -> '1','10','11','2','20','9'
#           INTEGER  -> 1,2,9,10,11,20
#
#   Ein Vermerk mit zehn oder mehr Bausteinen erscheint also in falscher
#   Reihenfolge. Es gibt dabei KEINE Ausnahme und keine Meldung — nur eine
#   falsche Reihenfolge in einem Dokument, das vor Gericht Bestand haben soll.
#
#   ZWEITE, BISHER NICHT VERZEICHNETE FOLGE (gemessen 2026-08-02):
#   get_blocks_for_report sortiert nach 'COALESCE(rbo.sort_index, 999999)'
#   (db/evidence_db.py:1819). Der Ersatzwert ist ein INTEGER-Literal, die
#   Spaltenwerte sind bei TEXT-Affinitaet Zeichenketten, und SQLite ordnet
#   INTEGER VOR TEXT — unabhaengig vom Zahlenwert ("SELECT '10' < 999999"
#   liefert 0). Ein Block OHNE Sortierungseintrag rutscht damit nicht ans
#   Ende, sondern an den ANFANG des Berichts:
#
#       sort_index TEXT     -> OHNE_ORDNUNG  b00  b01  b10  b02
#       sort_index INTEGER  -> b00  b01  b02  b10  OHNE_ORDNUNG
#
#   Das widerspricht der Zusage im Docstring derselben Methode ("Bloecke ohne
#   Sortierungseintrag werden ans Ende gestellt", :1810) und entwertet
#   WARN_UNORDERED_BLOCK: die Warnung sagt, der Block habe keine Ordnung, und
#   verschweigt, dass er deshalb das Dokument anfuehrt.
#
# ── DIE NEUE DDL WIRD ABGELEITET, NICHT GESCHRIEBEN ─────────────────────────
#
#   SQLite kann den Typ einer Spalte nicht aendern; es braucht einen
#   Tabellenneubau. Der naheliegende Weg — die DDL aus db/evidence_db.py
#   hinschreiben — waere hier FALSCH:
#
#       Falldatei (Prepper):  FOREIGN KEY(block_id) REFERENCES report_blocks(block_id)
#                             ON DELETE CASCADE
#       db/evidence_db.py:    FOREIGN KEY("block_id") REFERENCES "report_blocks"("block_id")
#                             (OHNE Kaskade)
#
#   Die beiden Fassungen unterscheiden sich also in einem ZWEITEN Punkt. Wer
#   nach der Webserver-Vorlage neu baut, nimmt jeder migrierten Beweisdatei
#   still ihre Kaskade weg — eine Verhaltensaenderung an einem Asservat, die
#   niemand beauftragt hat.
#
#   Deshalb wird die neue DDL AUS DER VORHANDENEN abgeleitet: aus
#   sqlite_master.sql wird genau ein Typbezeichner ersetzt, alles andere
#   bleibt zeichengleich. Was in der Datei stand, steht danach immer noch
#   darin. Und es wird nicht behauptet, sondern geprueft: table_info,
#   foreign_key_list und index_list werden vor und nach dem Umbau verglichen
#   und muessen sich in GENAU EINEM Feld unterscheiden (S05/S06).
#
# ── DIE UMWANDLUNG WIRD BELEGT, NICHT ANGENOMMEN ────────────────────────────
#
#   CAST wirft bei nicht-numerischem TEXT keine Ausnahme, sondern liefert eine
#   Zahl (gemessen 2026-08-02):
#
#       '7'->7   '007'->7   ' 3'->3   '-2'->-2
#       '3.9'->3   '1e3'->1   'abc'->0   ''->0
#
#   Ein blindes CAST koennte also mehrere Bausteine auf 0 legen und die
#   Reihenfolge zerstoeren, ohne dass irgendwo etwas meldet.
#
#   FESTLEGUNG mc 2026-08-02: Zweifelsfaelle werden UMGEWANDELT und VERMERKT
#   (nicht: Lauf abbrechen). Dazu gehoert aber, dass der Vermerk das Asservat
#   nicht verlaesst: er wird NICHT nur in das Migrationsprotokoll auf der
#   Migrationsmaschine geschrieben, sondern zusaetzlich in die Hash-Kette
#   'evidence_audit_log' DER BETROFFENEN DATEI (M003). Nur so reist der Beleg
#   mit dem Beweismittel und ist spaeter ohne die Maschine nachweisbar.
#
#   DARAUS FOLGT EINE GRENZE: Gibt es Zweifelsfaelle, kann die Kette aber
#   nicht beschrieben werden (M003 nicht angewandt), dann wird NICHT
#   umgewandelt, sondern abgebrochen. Eine Umwandlung ohne dauerhaften Beleg
#   waere genau die stille Aenderung, die Grundregel 1 verbietet. Bei
#   einwandfreien Werten ist die Kette entbehrlich — dann gibt es nichts zu
#   vermerken, was nicht schon in schema_migrations stuende.
#
# ── IDEMPOTENZ ──────────────────────────────────────────────────────────────
#
#   Traegt die Spalte bereits INTEGER (Dateien, die db/evidence_db.py selbst
#   angelegt hat, und alle ab Prepper 0.1.128), geschieht NICHTS — die
#   Migration wird nur registriert. Ein zweiter Lauf ist folgenlos.
#
# ── KEIN executescript() ────────────────────────────────────────────────────
#
#   Pythons sqlite3 committet vor executescript() IMPLIZIT und beendete damit
#   die Transaktion des Runners. Die Tabelle waere neu, die Registrierung in
#   'schema_migrations' fehlte — die Datei truege eine Struktur, von der sie
#   selbst nichts weiss. In Build 532 ist das einmal passiert (m002-Kopf,
#   Punkt 5a). Es wird ausschliesslich mit execute() gearbeitet.
#
# ── foreign_keys ────────────────────────────────────────────────────────────
#
#   Produktionsverbindungen laufen mit foreign_keys=OFF (SQLite-Vorgabe von
#   sqlite3.connect; ausdruecklich festgehalten in tools/poc_m019_weg_a.py:212),
#   und 'report_block_order' ist die KIND-Seite der Beziehung — ein DROP
#   loest keine Kaskade aus. PRAGMA foreign_key_check laeuft nach dem Umbau
#   trotzdem, weil eine Annahme ueber eine Beweisdatei nichts wert ist.
#
# KIND='destructive' -> precount/postcount/verify sind Pflicht (runner.py:140-149).
# Version: v0.8.660 · Build: 660 · 2026-08-02
# =============================================================================

import json
import logging
import re
import sqlite3
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

VERSION = 4
NAME = "report_block_order.sort_index: TEXT -> INTEGER (Tabellenneubau)"
KIND = "destructive"

TABELLE = "report_block_order"
SPALTE = "sort_index"
ZIELTYP = "INTEGER"
ARBEITSNAME = "report_block_order_m004"
INDEXNAME = "rbo_sort_idx"

#: Genau die Ganzzahlform, die evidence_db.py erzeugt: ein an eine
#  TEXT-Spalte gebundener Python-int landet als kanonische Dezimalzeichenkette
#  ('7', nicht '007', nicht ' 7'). Alles andere ist ein Zweifelsfall und wird
#  einzeln benannt — auch dann, wenn CAST zufaellig dasselbe liefert.
_KANONISCH = re.compile(r"^(0|-?[1-9][0-9]*)$")

#: Ersetzt den Typbezeichner der Spalte in einer vorhandenen DDL. Die
#  Anfuehrungsvarianten decken ab, was SQLite in sqlite_master ablegen kann:
#  ohne Anfuehrung (Prepper-Quelltext) und in doppelten Anfuehrungszeichen
#  (aus dem Schema-Abzug). Der Treffer MUSS eindeutig sein — sonst Abbruch.
_TYP_RE = re.compile(r'(["\[`]?' + SPALTE + r'["\]`]?\s+)TEXT\b', re.IGNORECASE)


# ---------------------------------------------------------------- Hilfsmittel
def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _tabellen_ddl(con: sqlite3.Connection, name: str) -> Optional[str]:
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def _table_info(con: sqlite3.Connection, name: str) -> Tuple[tuple, ...]:
    """(name, typ, notnull, dflt, pk) je Spalte — die Struktur ohne cid."""
    return tuple(
        (r[1], (r[2] or "").upper(), r[3], r[4], r[5])
        for r in con.execute('PRAGMA table_info("%s")' % name).fetchall()
    )


def _fk_liste(con: sqlite3.Connection, name: str) -> Tuple[tuple, ...]:
    """(tabelle, von, nach, on_update, on_delete, match) je Fremdschluessel."""
    return tuple(
        (r[2], r[3], r[4], r[5], r[6], r[7])
        for r in con.execute('PRAGMA foreign_key_list("%s")' % name).fetchall()
    )


def _index_liste(con: sqlite3.Connection, name: str) -> Tuple[tuple, ...]:
    """(indexname, unique, herkunft) je Index, stabil sortiert."""
    return tuple(sorted(
        (r[1], r[2], r[3])
        for r in con.execute('PRAGMA index_list("%s")' % name).fetchall()
    ))


def _deklarierter_typ(con: sqlite3.Connection) -> Optional[str]:
    for spalte, typ, _nn, _df, _pk in _table_info(con, TABELLE):
        if spalte == SPALTE:
            return typ
    return None


# --------------------------------------------------------- Runner-Schnittstelle
def precount(con: sqlite3.Connection) -> int:
    """
    Zeilenzahl VOR dem Umbau. Fehlt die Tabelle, wird 0 gemeldet statt zu
    scheitern — die aussagekraeftige Fehlermeldung gehoert in up(), nicht in
    einen sqlite3-Fehler aus dem Zaehler.
    """
    if not _table_exists(con, TABELLE):
        return 0
    return int(con.execute('SELECT COUNT(*) FROM "%s"' % TABELLE).fetchone()[0])


def postcount(con: sqlite3.Connection) -> int:
    """Zeilenzahl NACH dem Umbau."""
    if not _table_exists(con, TABELLE):
        return 0
    return int(con.execute('SELECT COUNT(*) FROM "%s"' % TABELLE).fetchone()[0])


def verify(con: sqlite3.Connection, before, after) -> None:
    """
    Invariante des Runners: die Zeilenzahl darf sich nicht geaendert haben.
    Ein Verstoss wirft und rollt den GESAMTEN Lauf zurueck.

    Die inhaltliche Verifikation (jeder einzelne Wert, die Struktur, die
    Fremdschluessel) liegt in up() — sie braucht den Zustand VOR dem Umbau,
    und den hat nur up() zur Hand. verify() ist die zweite, unabhaengige
    Klammer, keine Wiederholung.
    """
    if before is None or after is None:
        raise RuntimeError(
            "M004: Zeilenzaehlung fehlt (before=%r, after=%r) — ohne sie ist "
            "die Verlustfreiheit nicht belegt." % (before, after))
    if int(before) != int(after):
        raise RuntimeError(
            "M004: Zeilenzahl in '%s' hat sich geaendert: %d -> %d. "
            "Rueckabwicklung." % (TABELLE, int(before), int(after)))


# ------------------------------------------------------------------------ up
def up(con: sqlite3.Connection) -> None:
    # --- Abbruchbedingung 1: ist das ueberhaupt eine evidence-DB? -----------
    #   Muster m002/m003: lieber ein Abbruch ohne Teilzustand als ein Umbau in
    #   einer fremden Datei.
    if not _table_exists(con, "annotations"):
        raise RuntimeError(
            "M004: Tabelle 'annotations' fehlt — das ist keine "
            "evidence_<uid>.db. Abbruch ohne Aenderung.")
    if not _table_exists(con, TABELLE):
        # FEHLT DIE TABELLE, WIRD DAS GENANNT — ABER NICHT ABGEBROCHEN.
        #
        #   Erste Fassung dieser Migration brach hier ab. Das war zu scharf,
        #   und zwar aus einem Grund, der nicht am Testaufbau haengt: M004
        #   steht in einer KETTE. Ein Abbruch hier hielte auch jede spaetere
        #   Migration derselben Datei auf, obwohl es an dieser Stelle
        #   buchstaeblich nichts umzuwandeln gibt.
        #
        #   Zugleich darf das Fehlen nicht verschwinden — beide Schema-Quellen
        #   legen die Tabelle an (Prepper stage2/evidence_db_init.py,
        #   db/evidence_db.py:300). Deshalb eine Meldung mit Rang WARNING, die
        #   die Datei benennt, und ein sauberes Nichtstun. Das ist die Form,
        #   die Build 658 fuer den Startbefund gefunden hat: das Uebergangene
        #   wird gezaehlt und genannt, statt wortlos ausgelassen zu werden.
        logger.warning(
            "M004: Tabelle '%s' fehlt — nichts umzuwandeln. Beide "
            "Schema-Quellen legen sie an; ihr Fehlen ist ein Befund und "
            "gehoert nachgesehen. Die Migration gilt als angewandt.", TABELLE)
        return

    # --- Abbruchbedingung 2: Idempotenz und unbekannter Typ ----------------
    typ = _deklarierter_typ(con)
    if typ == ZIELTYP:
        logger.info("M004: '%s.%s' ist bereits %s — nichts zu tun.",
                    TABELLE, SPALTE, ZIELTYP)
        return
    if typ != "TEXT":
        raise RuntimeError(
            "M004: '%s.%s' traegt den unerwarteten Typ %r (erwartet 'TEXT' "
            "oder '%s'). Abbruch statt Raten." % (TABELLE, SPALTE, typ, ZIELTYP))

    # --- Zustand VOR dem Umbau vollstaendig erheben -------------------------
    alt_ddl = _tabellen_ddl(con, TABELLE)
    if not alt_ddl:
        raise RuntimeError(
            "M004: Zu '%s' liegt keine DDL in sqlite_master — der Neubau "
            "koennte die vorhandene Form nicht erhalten. Abbruch." % TABELLE)
    alt_info = _table_info(con, TABELLE)
    alt_fk = _fk_liste(con, TABELLE)
    alt_idx = _index_liste(con, TABELLE)

    # Rohwerte samt der Zahl, die SQLite selbst daraus machen wuerde. Der
    # Zielwert wird von SQLITE berechnet und nicht in Python nachgebaut —
    # eine zweite Umrechnung koennte von der ersten abweichen, und dann
    # prueften wir etwas anderes, als wir schreiben.
    zeilen = con.execute(
        'SELECT block_id, %s AS roh, CAST(%s AS INTEGER) AS ziel '
        'FROM "%s"' % (SPALTE, SPALTE, TABELLE)).fetchall()
    erwartet: Dict[str, int] = {}
    zweifel: List[dict] = []
    for block_id, roh, ziel in zeilen:
        schluessel = str(block_id)
        erwartet[schluessel] = int(ziel)
        if not _KANONISCH.match(str(roh if roh is not None else "")):
            zweifel.append({"block_id": schluessel,
                            "roh": (None if roh is None else str(roh)),
                            "uebernommen": int(ziel)})

    if len(erwartet) != len(zeilen):
        raise RuntimeError(
            "M004: '%s' enthaelt %d Zeilen, aber nur %d verschiedene "
            "block_id — der Primaerschluessel ist verletzt. Abbruch."
            % (TABELLE, len(zeilen), len(erwartet)))

    # --- Grenze: Umwandeln nur mit dauerhaftem Beleg ------------------------
    #   Festlegung mc: Zweifelsfaelle werden uebernommen und vermerkt. Der
    #   Vermerk gehoert in die Datei, nicht nur ins Maschinenprotokoll.
    kette_da = _table_exists(con, "evidence_audit_log")
    if zweifel and not kette_da:
        raise RuntimeError(
            "M004: %d Wert(e) in '%s.%s' sind keine kanonischen Ganzzahlen "
            "(z.B. block_id=%s, Wert=%r), und 'evidence_audit_log' fehlt "
            "(M003 nicht angewandt). Die Uebernahme waere dann nur im "
            "Maschinenprotokoll belegt und nicht in der Beweisdatei selbst. "
            "Erst M003 anwenden, dann M004."
            % (len(zweifel), TABELLE, SPALTE,
               zweifel[0]["block_id"], zweifel[0]["roh"]))

    # --- Neue DDL ABLEITEN, nicht schreiben ---------------------------------
    neu_ddl, treffer = _TYP_RE.subn(r"\1" + ZIELTYP, alt_ddl)
    if treffer != 1:
        raise RuntimeError(
            "M004: In der vorhandenen DDL von '%s' wurde der Typbezeichner "
            "von '%s' %d-mal getroffen (genau 1 erwartet). Die DDL lautet:\n%s"
            % (TABELLE, SPALTE, treffer, alt_ddl))
    # Der Neubau laeuft unter einem Arbeitsnamen; ersetzt wird NUR das erste
    # Vorkommen (der Tabellenname in CREATE TABLE), damit ein gleichlautender
    # Bezeichner im Rest der DDL unberuehrt bleibt.
    arbeits_ddl = neu_ddl.replace(TABELLE, ARBEITSNAME, 1)
    if ARBEITSNAME not in arbeits_ddl:
        raise RuntimeError(
            "M004: Der Arbeitsname liess sich nicht in die abgeleitete DDL "
            "einsetzen. Abbruch.\n%s" % neu_ddl)

    # --- Umbau (ausschliesslich execute(), kein executescript()) ------------
    if _table_exists(con, ARBEITSNAME):
        # Rest eines abgebrochenen Laufs. Er wird NICHT weiterverwendet — man
        # wuesste nicht, was darin steht.
        con.execute('DROP TABLE "%s"' % ARBEITSNAME)
    con.execute(arbeits_ddl)
    con.execute(
        'INSERT INTO "%s" (block_id, %s, last_modified_by, last_modified_at) '
        'SELECT block_id, CAST(%s AS INTEGER), last_modified_by, '
        '       last_modified_at FROM "%s"'
        % (ARBEITSNAME, SPALTE, SPALTE, TABELLE))
    con.execute('DROP TABLE "%s"' % TABELLE)
    con.execute('ALTER TABLE "%s" RENAME TO "%s"' % (ARBEITSNAME, TABELLE))
    # Der Index verschwand mit der alten Tabelle und wird nachgezogen. Sein
    # Name ist in beiden Schema-Quellen derselbe.
    con.execute('CREATE INDEX IF NOT EXISTS "%s" ON "%s" ("%s")'
                % (INDEXNAME, TABELLE, SPALTE))

    # --- Verifikation: die WIRKUNG, nicht die blosse Ausfuehrung ------------
    neu_typ = _deklarierter_typ(con)
    if neu_typ != ZIELTYP:
        raise RuntimeError(
            "M004: '%s.%s' traegt nach dem Umbau %r statt %r."
            % (TABELLE, SPALTE, neu_typ, ZIELTYP))

    neu_info = _table_info(con, TABELLE)
    # Erwartung: identisch bis auf den Typ der einen Spalte.
    soll_info = tuple(
        (n, ZIELTYP if n == SPALTE else t, nn, df, pk)
        for (n, t, nn, df, pk) in alt_info)
    if neu_info != soll_info:
        raise RuntimeError(
            "M004: Der Spaltenaufbau hat sich ueber den Typwechsel hinaus "
            "veraendert.\n  vorher : %r\n  erwartet: %r\n  nachher : %r"
            % (alt_info, soll_info, neu_info))

    neu_fk = _fk_liste(con, TABELLE)
    if neu_fk != alt_fk:
        # Genau der Fall, der bei einer nachgeschriebenen DDL eingetreten
        # waere: ON DELETE CASCADE waere still verschwunden.
        raise RuntimeError(
            "M004: Die Fremdschluessel haben sich geaendert.\n"
            "  vorher : %r\n  nachher: %r" % (alt_fk, neu_fk))

    neu_idx = _index_liste(con, TABELLE)
    if neu_idx != alt_idx:
        raise RuntimeError(
            "M004: Die Indexlage hat sich geaendert.\n"
            "  vorher : %r\n  nachher: %r" % (alt_idx, neu_idx))

    nachher = {
        str(b): int(s) for b, s in
        con.execute('SELECT block_id, %s FROM "%s"' % (SPALTE, TABELLE))
    }
    if nachher != erwartet:
        fehlend = sorted(set(erwartet) - set(nachher))
        zuviel = sorted(set(nachher) - set(erwartet))
        abweichend = sorted(b for b in set(erwartet) & set(nachher)
                            if erwartet[b] != nachher[b])
        raise RuntimeError(
            "M004: Der Inhalt stimmt nach dem Umbau nicht ueberein. "
            "fehlend=%r zuviel=%r abweichend=%r" % (fehlend, zuviel, abweichend))

    fk_befund = con.execute("PRAGMA foreign_key_check").fetchall()
    if fk_befund:
        raise RuntimeError(
            "M004: PRAGMA foreign_key_check meldet %d Verstoss/Verstoesse: %r"
            % (len(fk_befund), fk_befund[:5]))

    # --- Beleg der Zweifelsfaelle IN DER DATEI ------------------------------
    if zweifel:
        from management.audit.evidence_audit_log import EvidenceAuditLog
        EvidenceAuditLog(con).append(
            event_type="migration_applied",
            actor_id=None,                 # System, kein eingeloggter Ermittler
            target_type="migration",
            target_id=str(VERSION),
            payload={
                "migration": "M004",
                "name": NAME,
                "tabelle": TABELLE,
                "spalte": SPALTE,
                "typ_vorher": "TEXT",
                "typ_nachher": ZIELTYP,
                "zeilen": len(zeilen),
                # Die Zweifelsfaelle VOLLSTAENDIG, nicht als Zahl. Eine Zahl
                # sagte, DASS etwas war, und liesse offen, was.
                "zweifelsfaelle": zweifel,
                "hinweis": (
                    "Werte ohne kanonische Ganzzahlform wurden per CAST "
                    "uebernommen (Festlegung mc 2026-08-02). Die "
                    "Reihenfolge dieser Bausteine ist zu pruefen."),
                "migriert_am": int(time.time()),
            },
        )
        logger.warning(
            "M004: %d Wert(e) in '%s.%s' waren keine kanonischen Ganzzahlen "
            "und wurden per CAST uebernommen; Beleg in evidence_audit_log. "
            "Betroffen: %s",
            len(zweifel), TABELLE, SPALTE,
            json.dumps(zweifel, ensure_ascii=False))

    logger.info(
        "M004: '%s.%s' TEXT -> %s, %d Zeile(n) verlustfrei uebernommen, "
        "%d Zweifelsfall/-faelle.",
        TABELLE, SPALTE, ZIELTYP, len(zeilen), len(zweifel))
