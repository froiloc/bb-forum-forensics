# =============================================================================
# db/search_index_db.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B560)
# =============================================================================
# Zweck:
#   SearchIndexDb — Schema und Schreibpfad der search_index.db, des FTS5-Index
#   der falluebergreifenden Volltextsuche.
#
# ── DIE WICHTIGSTE EIGENSCHAFT DIESER DATEI: SIE IST KEIN BEWEISMITTEL ───────
#
#   search_index.db ist ein HILFSMITTEL und jederzeit verwerfbar — dieselbe
#   Einordnung wie evidence_scan_cache (m009:21-25). Beleg:
#   Klaerung_AP3E_..._v0_2.md §6 Nr. 3, bestaetigt in den Entscheidungen mc
#   2026-07-26 §1 (Schlussabsatz).
#
#   Daraus folgt dreierlei, und alles drei ist Absicht:
#     1. SIE LIEGT AUSSERHALB der Beweismitteldatenbanken. Der
#        Migrationsvorbehalt (ab 01.07.2026) ist nicht beruehrt; die
#        evidence_<uid>.db werden ausschliesslich 'mode=ro' gelesen.
#     2. SIE WIRD NIE ZITIERT. Jeder Treffer wird vor der Anzeige gegen die
#        Quelle verifiziert (Build 562). Der Index sagt WO man nachsehen soll,
#        nie WAS dort steht.
#     3. SIE DARF JEDERZEIT GELOESCHT WERDEN. Geht sie verloren, geht kein
#        Beleg verloren — nur Zeit. Deshalb gibt es hier auch KEINE Migration
#        im Sinne von management/migrations/: bei abweichender Schemaversion
#        wird die Datei NEU AUFGEBAUT statt umgebaut (s. SCHEMA_VERSION).
#
# ── WARUM ZWEI FTS5-TABELLEN (Entscheidung mc 2026-07-26) ────────────────────
#
#   'index_wort'  (unicode61 remove_diacritics 2) — Wort- und Wortanfangssuche.
#   'index_teil'  (trigram)                       — Teilstringsuche.
#
#   Nicknames stehen im Ermittlertext regelmaessig verklebt ('birnenmus_2000',
#   'xXbirnenmusXx'). Eine reine Wortsuche fuende sie nicht und schwiege
#   darueber — der Leerbefund saehe aus wie Vollstaendigkeit (Grundregel 1).
#   Eine reine Teilstringsuche haette dafuer keine Wortgrenzen und keine
#   brauchbare Rangfolge. Beide zu fuehren kostet Plattenplatz in einer
#   verwerfbaren Datei: der guenstigste Preis, den diese Wahl haben kann.
#
#   BEIDE SIND EXTERNAL-CONTENT-TABELLEN (content='index_satz'). Sie speichern
#   den Text NICHT ein zweites und drittes Mal, sondern verweisen auf
#   index_satz. Ohne das laege jeder Satz dreifach auf der Platte.
#
#   Der Preis der External-Content-Bauweise ist, dass FTS5 nicht von selbst
#   mitbekommt, wenn sich index_satz aendert — das erledigen die drei Trigger
#   unten. Ein VERGESSENER Trigger waere hier besonders heimtueckisch: der
#   Index lieferte weiter Treffer, nur eben veraltete. Deshalb prueft der Test
#   SI09 nicht die EXISTENZ der Trigger, sondern ihre WIRKUNG (loeschen ->
#   Treffer weg).
#
#   KEIN UPDATE-TRIGGER, UND DAS IST BEWUSST: der Indexbauer ersetzt einen Fall
#   immer vollstaendig (DELETE alle Saetze des Falls, dann INSERT). Ein
#   UPDATE-Trigger waere ein Mechanismus, den niemand benutzt und den deshalb
#   auch kein Test abdeckt — dieselbe Falle wie der scope-faehige, aber
#   ungenutzte Grant aus Build 532. Statt seiner steht in index_satz eine
#   Trigger-SPERRE gegen UPDATE (s. _SCHEMA_DDL): wer den Schreibpfad spaeter
#   aendert, bekommt einen harten Fehler statt eines stillen Indexdrifts.
#
# ── JOURNALMODUS ─────────────────────────────────────────────────────────────
#
#   WAL ist projektweit verboten (Build 499, mc 2026-07-22). Der Journalmodus
#   wird ueber db/journal_policy.py gesetzt — die einzige Stelle im Projekt,
#   an der das geschieht. Auch fuer eine verwerfbare Datei: sie liegt in
#   PROD auf demselben Netzlaufwerk, auf dem WAL den Vorfall ausgeloest hat.
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================

import logging
import sqlite3
import time
from pathlib import Path
from typing import Dict, Optional, Sequence

from db.journal_policy import apply_journal_mode
from management.search.index_vokabular import (
    BEFUND_GELESEN,
    TOKENIZER_TEIL,
    TOKENIZER_WORT,
    ist_befund,
    ist_fassung,
    ist_satz_art,
)
from management.search.satz import Satz

logger = logging.getLogger(__name__)


#: Schemaversion des Index. WIRD SIE ERHOEHT, WIRD DIE DATEI VERWORFEN UND NEU
#  AUFGEBAUT — nicht migriert. Das ist der ganze Sinn eines Hilfsmittels: ein
#  Umbau haette Fehlerquellen, ein Neuaufbau hat keine. Der Neuaufbau kostet
#  einen Lauf ueber alle evidence_<uid>.db; das ist auf dem Netzlaufwerk
#  teuer, aber es geht dabei nichts verloren, was nicht wieder herstellbar ist.
SCHEMA_VERSION = 1

_SCHEMA_DDL = """
-- Stammdaten des Index (Schemaversion, Tokenizer, Erzeugungszeitpunkt).
-- Als Schluessel/Wert, damit eine Ergaenzung keine Schemaaenderung ist.
CREATE TABLE IF NOT EXISTS "index_meta" (
    "schluessel"  TEXT NOT NULL PRIMARY KEY,
    "wert"        TEXT NOT NULL
);

-- Je Quelldatenbank: was wurde wann mit welchem Fingerabdruck indiziert, und
-- mit welchem Befund. DIESE TABELLE IST DER GRUND, WARUM ES KEINEN STILLEN
-- TEILTREFFER GEBEN KANN: eine nicht lesbare Datenbank steht hier mit ihrem
-- Befund und wird von jeder Antwort mitgezaehlt und benannt.
CREATE TABLE IF NOT EXISTS "index_quelle" (
    "subject_id"    INTEGER NOT NULL PRIMARY KEY,
    "db_pfad"       TEXT    NOT NULL,
    -- WAL-sicherer Fingerabdruck der Quelldatei
    -- (management/reports/evidence_scanner.py:75-90). BESCHLEUNIGER, NIE
    -- BEWEISMITTEL: er entscheidet nur, ob neu gelesen werden muss.
    "fingerprint"   TEXT    NOT NULL,
    "indiziert_at"  INTEGER NOT NULL,
    "satz_zahl"     INTEGER NOT NULL DEFAULT 0,
    -- Zahl der Saetze, die wegen MAX_SATZ_LAENGE gekuerzt wurden. Eine
    -- Kuerzung ist ein BEFUND und kein Detail; sie steht hier, damit die
    -- Auslieferung sie benennen kann.
    "gekuerzt_zahl" INTEGER NOT NULL DEFAULT 0,
    "befund"        TEXT    NOT NULL,
    "befund_detail" TEXT    DEFAULT NULL
);

-- Ein indizierter Textfund. Traegt seinen vollstaendigen Rueckweg zur Quelle
-- (Fall, Tabelle, Spalte, Schluessel) — ohne den waere der Index eine
-- Behauptung ohne Beleg.
CREATE TABLE IF NOT EXISTS "index_satz" (
    "satz_id"          INTEGER PRIMARY KEY AUTOINCREMENT,
    "subject_id"       INTEGER NOT NULL,
    "satz_art"         TEXT    NOT NULL,
    "quell_tabelle"    TEXT    NOT NULL,
    "quell_spalte"     TEXT    NOT NULL,
    "quell_schluessel" TEXT    NOT NULL,
    -- aktuell | ueberholt | zurueckgenommen. Die drei duerfen in der Sicht
    -- NIE zusammengezaehlt werden (index_vokabular.FASSUNGEN).
    "fassung"          TEXT    NOT NULL,
    "ts"               INTEGER DEFAULT NULL,
    "urheber"          TEXT    DEFAULT NULL,
    "text"             TEXT    NOT NULL
);

-- Fall + Fassung: die Gruppierung der Stufe 1 ("Fall 5023 — 3 aktuelle,
-- 1 ueberholter Treffer"). Ohne diesen Index waere das ein Vollscan je Antwort.
CREATE INDEX IF NOT EXISTS "index_satz_fall_idx"
    ON "index_satz" ("subject_id", "fassung");

-- Der Loeschpfad des Indexbauers (alle Saetze EINES Falls) — er laeuft bei
-- jedem inkrementellen Lauf je geaenderter Datenbank.
CREATE INDEX IF NOT EXISTS "index_satz_subject_idx"
    ON "index_satz" ("subject_id");

-- Wortsuche: unicode61, Diakritika unicode-vollstaendig entfernt (Stufe 2).
-- Das Forum ist multilingual (Fallerkenntnis 2), die Notizen zitieren daraus.
CREATE VIRTUAL TABLE IF NOT EXISTS "index_wort" USING fts5(
    text,
    content='index_satz',
    content_rowid='satz_id',
    tokenize='%(tok_wort)s'
);

-- Teilstringsuche: trigram. Findet 'birnenmus' auch in 'xXbirnenmusXx'.
-- Harte Grenze der Erweiterung: Muster ab DREI Zeichen.
CREATE VIRTUAL TABLE IF NOT EXISTS "index_teil" USING fts5(
    text,
    content='index_satz',
    content_rowid='satz_id',
    tokenize='%(tok_teil)s'
);

-- Synchronisation der External-Content-Tabellen. WIRKUNGSGEPRUEFT (SI09):
-- der Test loescht einen Satz und stellt fest, dass der Treffer VERSCHWINDET —
-- nicht, dass ein Trigger existiert.
CREATE TRIGGER IF NOT EXISTS "index_satz_nach_insert"
AFTER INSERT ON "index_satz" BEGIN
    INSERT INTO "index_wort"(rowid, text) VALUES (new."satz_id", new."text");
    INSERT INTO "index_teil"(rowid, text) VALUES (new."satz_id", new."text");
END;

CREATE TRIGGER IF NOT EXISTS "index_satz_nach_delete"
AFTER DELETE ON "index_satz" BEGIN
    INSERT INTO "index_wort"("index_wort", rowid, text)
        VALUES ('delete', old."satz_id", old."text");
    INSERT INTO "index_teil"("index_teil", rowid, text)
        VALUES ('delete', old."satz_id", old."text");
END;

-- SPERRE STATT MECHANISMUS: index_satz wird nie aktualisiert, sondern
-- geloescht und neu geschrieben. Wer das spaeter aendert, laeuft in einen
-- harten Fehler statt in einen stillen Indexdrift (der Index lieferte sonst
-- weiter Treffer — nur eben zum alten Text).
CREATE TRIGGER IF NOT EXISTS "index_satz_kein_update"
BEFORE UPDATE ON "index_satz" BEGIN
    SELECT RAISE(ABORT, 'index_satz wird nicht aktualisiert: Fall loeschen und neu schreiben (db/search_index_db.py, Build 560).');
END;
""" % {"tok_wort": TOKENIZER_WORT, "tok_teil": TOKENIZER_TEIL}


class SearchIndexFehler(RuntimeError):
    """
    Der Index ist nicht benutzbar.

    KEIN STILLES WEITERARBEITEN: Fehlt die FTS5-Erweiterung oder der
    trigram-Tokenizer, wird hart abgebrochen. Ein Rueckfall auf LIKE waere die
    schlimmste denkbare Auskunft — die Suche saehe aus, als haette sie
    gearbeitet, und fuende nur einen Teil.
    """


class SearchIndexDb:
    """
    Die FTS5-Indexdatenbank der falluebergreifenden Volltextsuche.

    Lebenszyklus: oeffnen (legt bei Bedarf an) -> je Fall ersetzen -> schliessen.
    Die Klasse kennt KEINE evidence-Datenbank; sie nimmt fertige Saetze
    entgegen. Das Lesen der Quellen liegt in
    management/search/evidence_source_reader.py, die Steuerung in
    management/search/index_builder.py — drei Aufgaben, drei Dateien
    (Grundregel 10).
    """

    def __init__(self, pfad: object, *, journal_mode: str = "auto",
                 journal_fallback: str = "delete") -> None:
        """
        Oeffnet (und erzeugt bei Bedarf) die Indexdatenbank unter 'pfad'.

        Weicht die vorgefundene Schemaversion ab, wird die Datei VERWORFEN und
        neu angelegt — sie ist ein Hilfsmittel, kein Beweismittel (s. Modulkopf).
        Der Vorgang wird protokolliert, damit er in der Betriebsakte auftaucht:
        er ist harmlos, aber er kostet einen vollen Neuaufbau.
        """
        self._pfad = Path(str(pfad))
        self._pfad.parent.mkdir(parents=True, exist_ok=True)
        self._journal_mode = journal_mode
        self._journal_fallback = journal_fallback
        self._neu_aufgebaut = False
        self._con = self._oeffnen()

    # ------------------------------------------------------------------ oeffnen
    def _oeffnen(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self._pfad))
        con.row_factory = sqlite3.Row
        apply_journal_mode(con, self._pfad, mode=self._journal_mode,
                           fallback=self._journal_fallback, log=logger)
        self._pruefe_fts5(con)

        vorgefunden = self._schema_version(con)
        if vorgefunden is not None and vorgefunden != SCHEMA_VERSION:
            logger.warning(
                "search_index.db: Schemaversion %s vorgefunden, erwartet %s — "
                "die Datei wird VERWORFEN und neu aufgebaut. Es geht kein Beleg "
                "verloren (Hilfsmittel, kein Beweismittel); der Neuaufbau kostet "
                "einen Lauf ueber alle evidence-Datenbanken.",
                vorgefunden, SCHEMA_VERSION)
            con.close()
            self._verwerfen()
            con = sqlite3.connect(str(self._pfad))
            con.row_factory = sqlite3.Row
            apply_journal_mode(con, self._pfad, mode=self._journal_mode,
                               fallback=self._journal_fallback, log=logger)
            self._neu_aufgebaut = True

        con.executescript(_SCHEMA_DDL)
        con.execute(
            "INSERT OR IGNORE INTO index_meta(schluessel, wert) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)))
        con.execute(
            "INSERT OR IGNORE INTO index_meta(schluessel, wert) VALUES (?, ?)",
            ("erzeugt_at", str(int(time.time()))))
        # Die Tokenizer werden MITGESCHRIEBEN, damit spaeter nachweisbar ist,
        # womit ein vorgefundener Index gebaut wurde. Aendert sich einer, ist
        # das eine Schemaaenderung und die Version steigt.
        con.execute(
            "INSERT OR REPLACE INTO index_meta(schluessel, wert) VALUES (?, ?)",
            ("tokenizer_wort", TOKENIZER_WORT))
        con.execute(
            "INSERT OR REPLACE INTO index_meta(schluessel, wert) VALUES (?, ?)",
            ("tokenizer_teil", TOKENIZER_TEIL))
        con.commit()
        return con

    def _verwerfen(self) -> None:
        """Indexdatei samt Journal-Nebendateien entfernen (Neuaufbau)."""
        for suffix in ("", "-journal", "-wal", "-shm"):
            p = Path(str(self._pfad) + suffix)
            try:
                if p.exists():
                    p.unlink()
            except OSError as exc:
                raise SearchIndexFehler(
                    "search_index.db konnte nicht verworfen werden (%s): %s"
                    % (p, exc)) from exc

    @staticmethod
    def _schema_version(con: sqlite3.Connection) -> Optional[int]:
        """Vorgefundene Schemaversion, oder None bei leerer/neuer Datei."""
        try:
            da = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='index_meta'").fetchone()
            if da is None:
                return None
            row = con.execute(
                "SELECT wert FROM index_meta WHERE schluessel='schema_version'"
            ).fetchone()
            return int(row[0]) if row else None
        except (sqlite3.Error, ValueError, TypeError):
            # Unlesbare oder unsinnige Angabe wird wie 'unbekannt' behandelt und
            # loest den Neuaufbau aus — die harmlose Richtung.
            return -1

    @staticmethod
    def _pruefe_fts5(con: sqlite3.Connection) -> None:
        """
        Belegt, dass FTS5 UND der trigram-Tokenizer verfuegbar sind.

        Geprueft wird durch ANLEGEN einer temporaeren Tabelle, nicht durch
        Abfragen von compile_options — eine Wirkungspruefung statt einer
        Existenzpruefung (die Lehre aus Builds 533/535).

        trigram gibt es ab SQLite 3.34 (2020-12). Fehlt es, wird HART
        abgebrochen: ohne Teilstringsuche wuerde die Anlage verklebte
        Fundstellen lautlos uebersehen, und der Leerbefund saehe aus wie
        Vollstaendigkeit.
        """
        for name, tok in (("wort", TOKENIZER_WORT), ("teil", TOKENIZER_TEIL)):
            try:
                con.execute(
                    "CREATE VIRTUAL TABLE temp.\"_fts5_probe_%s\" "
                    "USING fts5(x, tokenize='%s')" % (name, tok))
                con.execute("DROP TABLE temp.\"_fts5_probe_%s\"" % name)
            except sqlite3.Error as exc:
                raise SearchIndexFehler(
                    "FTS5 mit Tokenizer '%s' ist in dieser SQLite-Fassung (%s) "
                    "nicht verfuegbar: %s. Die Volltextsuche wird NICHT mit "
                    "einem Rueckfall auf LIKE betrieben — sie faende nur einen "
                    "Teil und schwiege darueber (Grundregel 1)."
                    % (tok, sqlite3.sqlite_version, exc)) from exc

    # ------------------------------------------------------------- Eigenschaften
    @property
    def pfad(self) -> Path:
        """Pfad der Indexdatei."""
        return self._pfad

    @property
    def neu_aufgebaut(self) -> bool:
        """True, wenn die Datei beim Oeffnen wegen Versionsabweichung verworfen
        wurde. Der Aufrufer meldet das — es erklaert einen langen ersten Lauf."""
        return self._neu_aufgebaut

    def verbindung(self) -> sqlite3.Connection:
        """Die offene Verbindung (fuer die Abfrage in Build 562)."""
        return self._con

    # ------------------------------------------------------------- Schreibpfad
    def ersetze_fall(self, subject_id: int, saetze: Sequence[Satz], *,
                     db_pfad: str, fingerprint: str,
                     befund: str = BEFUND_GELESEN,
                     befund_detail: Optional[str] = None,
                     gekuerzt_zahl: int = 0,
                     jetzt: Optional[int] = None) -> int:
        """
        Ersetzt ALLE Saetze eines Falls und schreibt seinen Quellbefund.

        IN EINER TRANSAKTION. Bricht der Lauf mitten im Schreiben ab, steht
        entweder der alte oder der neue Stand da — nie eine Mischung, bei der
        die Haelfte der Annotationen eines Falls fehlt und niemand es merkt.

        Args:
            subject_id:    Fall.
            saetze:        die neuen Saetze (leer ist zulaessig und heisst
                           'nichts Indizierbares gefunden' — NICHT 'Fehler').
            db_pfad:       Pfad der Quelldatei (zur Nachvollziehbarkeit).
            fingerprint:   WAL-sicherer Fingerabdruck der Quelle zum Lesezeitpunkt.
            befund:        Wert aus index_vokabular.QUELL_BEFUNDE.
            befund_detail: Klartext bei Fehlbefund (wird in der Antwort genannt).
            gekuerzt_zahl: Zahl der wegen MAX_SATZ_LAENGE gekuerzten Saetze.
            jetzt:         Zeitpunkt (Unix-Sekunden); Default: time.time().

        Returns:
            Die Zahl der geschriebenen Saetze.
        """
        if not ist_befund(befund):
            raise ValueError("Unbekannter Quellbefund: %r" % (befund,))
        jetzt = int(time.time()) if jetzt is None else int(jetzt)
        uid = int(subject_id)

        zeilen = []
        for s in saetze:
            # Harte Pruefung des Vokabulars VOR dem Schreiben. Ein Tippfehler in
            # der Satzart wuerde sonst als eigene, nirgends aufgefuehrte Art im
            # Index landen und in der Sicht schlicht fehlen.
            if not ist_satz_art(s.satz_art):
                raise ValueError("Unbekannte Satzart: %r" % (s.satz_art,))
            if not ist_fassung(s.fassung):
                raise ValueError("Unbekannte Fassung: %r" % (s.fassung,))
            zeilen.append((uid, s.satz_art, s.quell_tabelle, s.quell_spalte,
                           str(s.quell_schluessel), s.fassung,
                           None if s.ts is None else int(s.ts),
                           s.urheber, s.text))

        try:
            with self._con:
                self._con.execute(
                    "DELETE FROM index_satz WHERE subject_id = ?", (uid,))
                if zeilen:
                    self._con.executemany(
                        "INSERT INTO index_satz(subject_id, satz_art, "
                        "quell_tabelle, quell_spalte, quell_schluessel, "
                        "fassung, ts, urheber, text) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", zeilen)
                self._con.execute(
                    "INSERT OR REPLACE INTO index_quelle(subject_id, db_pfad, "
                    "fingerprint, indiziert_at, satz_zahl, gekuerzt_zahl, "
                    "befund, befund_detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (uid, str(db_pfad), str(fingerprint), jetzt, len(zeilen),
                     int(gekuerzt_zahl), befund, befund_detail))
        except sqlite3.Error as exc:
            raise SearchIndexFehler(
                "Fall %d konnte nicht in den Index geschrieben werden: %s"
                % (uid, exc)) from exc
        return len(zeilen)

    def entferne_fall(self, subject_id: int) -> None:
        """
        Entfernt einen Fall vollstaendig aus dem Index (Saetze + Quellzeile).

        Aufgerufen, wenn eine evidence_<uid>.db VERSCHWUNDEN ist. Der Fall
        stillschweigend im Index stehen zu lassen waere die schlechteste
        Variante: die Suche fuende Treffer, die sich nicht mehr gegen die
        Quelle verifizieren lassen.
        """
        uid = int(subject_id)
        with self._con:
            self._con.execute("DELETE FROM index_satz WHERE subject_id = ?",
                              (uid,))
            self._con.execute("DELETE FROM index_quelle WHERE subject_id = ?",
                              (uid,))

    # ------------------------------------------------------------------- Lesen
    def quellen(self) -> Dict[int, sqlite3.Row]:
        """Alle Quellzeilen des Index: subject_id -> Zeile."""
        cur = self._con.execute(
            "SELECT subject_id, db_pfad, fingerprint, indiziert_at, satz_zahl, "
            "gekuerzt_zahl, befund, befund_detail FROM index_quelle "
            "ORDER BY subject_id")
        return {int(r["subject_id"]): r for r in cur.fetchall()}

    def meta(self, schluessel: str) -> Optional[str]:
        """Ein Stammdatenwert (schema_version, tokenizer_*, erzeugt_at, ...)."""
        row = self._con.execute(
            "SELECT wert FROM index_meta WHERE schluessel = ?",
            (schluessel,)).fetchone()
        return None if row is None else str(row[0])

    def setze_meta(self, schluessel: str, wert: object) -> None:
        """Einen Stammdatenwert setzen (z.B. den Zeitpunkt des letzten Laufs)."""
        with self._con:
            self._con.execute(
                "INSERT OR REPLACE INTO index_meta(schluessel, wert) "
                "VALUES (?, ?)", (str(schluessel), str(wert)))

    def satz_zahl(self, subject_id: Optional[int] = None) -> int:
        """Zahl der indizierten Saetze — gesamt oder fuer einen Fall."""
        if subject_id is None:
            row = self._con.execute(
                "SELECT COUNT(*) FROM index_satz").fetchone()
        else:
            row = self._con.execute(
                "SELECT COUNT(*) FROM index_satz WHERE subject_id = ?",
                (int(subject_id),)).fetchone()
        return int(row[0]) if row else 0

    def optimiere(self) -> None:
        """
        FTS5-Wartung ('optimize') fuer beide Indextabellen.

        NUR NACH EINEM GROSSEN LAUF aufrufen: das Kommando schreibt den Index
        neu und ist entsprechend teuer — auf einem Netzlaufwerk (PROD, Faktor
        rund 24 gegenueber DEV, Messung 2026-07-25) darf das nicht bei jedem
        einzelnen Fall geschehen.
        """
        with self._con:
            self._con.execute(
                "INSERT INTO index_wort(index_wort) VALUES('optimize')")
            self._con.execute(
                "INSERT INTO index_teil(index_teil) VALUES('optimize')")

    def close(self) -> None:
        """Verbindung schliessen (mehrfacher Aufruf ist unschaedlich)."""
        try:
            self._con.close()
        except Exception:  # pragma: no cover — Schliessen darf nie werfen
            pass

    def __enter__(self) -> "SearchIndexDb":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
