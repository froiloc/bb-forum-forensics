# =============================================================================
# management/search/evidence_source_reader.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B560)
# =============================================================================
# Zweck:
#   EvidenceSourceReader — liest GENAU EINE evidence_<uid>.db und liefert die
#   indizierbaren Saetze samt Befund. Kennt den Index nicht; das Schreiben
#   liegt in db/search_index_db.py, die Steuerung in index_builder.py.
#
# ── REIN LESEND, UND ZWAR NACHWEISLICH ───────────────────────────────────────
#
#   Die Verbindung wird 'file:<pfad>?mode=ro' geoeffnet (Muster
#   management/reports/reports_repo.py:122, annotation_stats_repo.py:107).
#   'mode=ro' ist keine Absichtserklaerung, sondern eine Sperre der
#   SQLite-Schicht: ein Schreibversuch scheitert, statt zu gelingen. Der
#   Migrationsvorbehalt fuer die Beweismitteldatenbanken (ab 01.07.2026) ist
#   damit nicht beruehrt (Klaerung §6 Nr. 2, Entscheidungen mc §1).
#
# ── KEIN STILLER TEILTREFFER — DIE DREI ARTEN VON 'NICHTS GEFUNDEN' ─────────
#
#   Der Leser unterscheidet sauber, was in einer Ermittlungsakte nicht gleich
#   aussehen darf:
#     * BEFUND_GELESEN mit null Saetzen  — nachgesehen, nichts gefunden.
#     * BEFUND_OHNE_TABELLE              — die erwarteten Tabellen fehlen
#                                          (m001-Baseline nicht angewandt?).
#                                          Es ist NICHT gesagt, dass nichts da
#                                          ist.
#     * BEFUND_NICHT_OEFFENBAR/-LESBAR   — gar nicht nachgesehen.
#   Dieselbe Trennschaerfe wie 'nicht_geprueft' / 'ohne_feststellung' im
#   Fristenmonitor (Build 535, TA16) und wie 'ohne_tabelle' bei m002 (TA12).
#
# ── EINE FEHLENDE TABELLE BRICHT DEN LAUF NICHT AB ───────────────────────────
#
#   Die elf indizierten Spalten verteilen sich auf sieben Tabellen. Eine
#   evidence-DB aus einem aelteren Stand kann einzelne davon nicht haben
#   (report_approvals kam mit der Berichtsabnahme, investigator_aliases mit
#   AP-2A). Jede Tabelle wird deshalb EINZELN auf Existenz geprueft; fehlende
#   werden GESAMMELT und im Befunddetail benannt — nicht uebersprungen und
#   nicht als Fehler des ganzen Falls gewertet. Fehlen ALLE, ist das der
#   Befund 'ohne_tabelle'.
#
# ── DIE FASSUNGSBESTIMMUNG BEI ANNOTATIONEN ──────────────────────────────────
#
#   annotations ist append-only (db/evidence_db.py:868-874): eine Bearbeitung
#   legt einen NEUEN Datensatz an (version_nr+1, prev_id = alte.id) und stempelt
#   die alte Fassung mit deleted_at. 'deleted_at' heisst dort also GEAENDERT und
#   nicht GELOESCHT.
#
#   Bestimmung (Entscheidung mc 2026-07-26 — ueberholte und zurueckgenommene
#   Fassungen werden mitindiziert und getrennt ausgewiesen):
#     deleted_at IS NULL                      -> aktuell
#     deleted_at gesetzt, Nachfolger vorhanden-> ueberholt
#     deleted_at gesetzt, kein Nachfolger     -> zurueckgenommen
#
#   'Nachfolger vorhanden' heisst: ein anderer Datensatz hat prev_id = diese id.
#   Genau diese Pruefung benutzt der Bestand fuer 'ist die Fassung aktuell?'
#   (db/evidence_db.py:989). UEBER local_id GINGE ES NICHT: local_id ist
#   optional ('anonyme Einmal-Annotation', db/evidence_db.py:871), und eine
#   geloeschte anonyme Annotation waere dann nicht einzuordnen.
#
#   Die Nachfolgermenge wird in EINER Abfrage geholt
#   ('SELECT DISTINCT prev_id ... WHERE prev_id IS NOT NULL') und als Menge im
#   Speicher gehalten — nicht je Zeile einzeln abgefragt. Auf dem Netzlaufwerk
#   (PROD, Faktor rund 24 gegenueber DEV) waere die zeilenweise Variante der
#   teuerste Teil des ganzen Laufs.
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

from management.search.block_text import (
    gekuerzt,
    html_zu_klartext,
    json_klartext,
    kuerze,
)
from management.search.index_vokabular import (
    BEFUND_GELESEN,
    BEFUND_NICHT_LESBAR,
    BEFUND_NICHT_OEFFENBAR,
    BEFUND_OHNE_TABELLE,
    BEFUND_FEHLT,
    FASSUNG_AKTUELL,
    FASSUNG_UEBERHOLT,
    FASSUNG_ZURUECKGENOMMEN,
    QUELL_TABELLEN,
)
from management.search.satz import Satz

logger = logging.getLogger(__name__)


class Lesebefund:
    """
    Ergebnis eines Lesevorgangs: Saetze + Befund + was dabei gefehlt hat.

    Eigene kleine Klasse statt eines dict, weil der Aufrufer (index_builder)
    jedes Feld auswerten MUSS — ein dict laedt dazu ein, eines zu vergessen,
    und das vergessene waere hier regelmaessig das Befunddetail.
    """

    __slots__ = ("saetze", "befund", "detail", "fehlende_tabellen",
                 "gekuerzt_zahl")

    def __init__(self, saetze: List[Satz], befund: str,
                 detail: Optional[str] = None,
                 fehlende_tabellen: Optional[Sequence[str]] = None,
                 gekuerzt_zahl: int = 0) -> None:
        self.saetze = saetze
        self.befund = befund
        self.detail = detail
        self.fehlende_tabellen = list(fehlende_tabellen or ())
        self.gekuerzt_zahl = int(gekuerzt_zahl)

    def __repr__(self) -> str:  # pragma: no cover — Diagnosehilfe
        return ("Lesebefund(saetze=%d, befund=%r, fehlt=%r, gekuerzt=%d)"
                % (len(self.saetze), self.befund, self.fehlende_tabellen,
                   self.gekuerzt_zahl))


class EvidenceSourceReader:
    """Liest die indizierbaren Textspalten EINER evidence_<uid>.db (read-only)."""

    def __init__(self, subject_id: int, db_pfad: object) -> None:
        self._uid = int(subject_id)
        self._pfad = Path(str(db_pfad))

    @property
    def pfad(self) -> Path:
        return self._pfad

    # ------------------------------------------------------------------ lesen
    def lies(self) -> Lesebefund:
        """
        Liest die Quelle und liefert einen Lesebefund.

        Wirft NICHT: jeder Fehlerfall wird zu einem Befund. Ein Ausnahmefehler
        mitten im Lauf ueber vierzig Datenbanken haette zur Folge, dass die
        restlichen gar nicht erst gelesen werden — und das ohne Spur darueber,
        welche das waren.
        """
        if not self._pfad.exists():
            return Lesebefund([], BEFUND_FEHLT,
                              "Datei nicht vorhanden: %s" % self._pfad)
        try:
            con = sqlite3.connect("file:%s?mode=ro" % self._pfad.resolve(),
                                  uri=True)
        except sqlite3.Error as exc:
            logger.warning("evidence-DB nicht oeffenbar: %s (%s)",
                           self._pfad, exc)
            return Lesebefund([], BEFUND_NICHT_OEFFENBAR,
                              "nicht oeffenbar: %s" % exc)
        try:
            con.row_factory = sqlite3.Row
            vorhanden = self._vorhandene_tabellen(con)
            fehlend = [t for t in QUELL_TABELLEN if t not in vorhanden]
            if not vorhanden:
                return Lesebefund(
                    [], BEFUND_OHNE_TABELLE,
                    "keine der erwarteten Tabellen vorhanden (%s). Es ist "
                    "NICHT gesagt, dass nichts erfasst wurde — diese Datenbank "
                    "wurde nur nicht ausgewertet."
                    % ", ".join(QUELL_TABELLEN),
                    fehlende_tabellen=fehlend)

            saetze: List[Satz] = []
            gekuerzt_zahl = 0
            for leser in (self._annotationen, self._berichte, self._bausteine,
                          self._anker, self._kommentare, self._freigaben,
                          self._aliase):
                neu, gek = leser(con, vorhanden)
                saetze.extend(neu)
                gekuerzt_zahl += gek

            detail = None
            if fehlend:
                detail = ("nicht ausgewertet, weil im Schema nicht vorhanden: "
                          "%s" % ", ".join(fehlend))
            return Lesebefund(saetze, BEFUND_GELESEN, detail,
                              fehlende_tabellen=fehlend,
                              gekuerzt_zahl=gekuerzt_zahl)
        except sqlite3.Error as exc:
            logger.warning("evidence-DB nicht lesbar: %s (%s)", self._pfad, exc)
            return Lesebefund([], BEFUND_NICHT_LESBAR,
                              "nicht lesbar: %s" % exc)
        finally:
            try:
                con.close()
            except Exception:  # pragma: no cover
                pass

    # -------------------------------------------------------------- internals
    @staticmethod
    def _vorhandene_tabellen(con: sqlite3.Connection) -> Set[str]:
        """Welche der erwarteten Quelltabellen gibt es in dieser Datei?"""
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
        alle = {str(r[0]) for r in cur.fetchall()}
        return {t for t in QUELL_TABELLEN if t in alle}

    def _satz(self, art: str, tabelle: str, spalte: str, schluessel: object,
              fassung: str, ts: Optional[int], urheber: Optional[str],
              text: str) -> Tuple[Optional[Satz], int]:
        """
        Baut einen Satz — oder keinen, wenn kein Text uebrig bleibt.

        Rueckgabe: (Satz oder None, 1 wenn gekuerzt sonst 0).
        Leere Texte werden NICHT indiziert: sie kosten Platz und koennen
        definitionsgemaess nie ein Treffer sein.
        """
        text = (text or "").strip()
        if not text:
            return None, 0
        gek = 1 if gekuerzt(text) else 0
        if gek:
            logger.debug("Satz gekuerzt (Fall %d, %s.%s, Schluessel %s)",
                         self._uid, tabelle, spalte, schluessel)
            text = kuerze(text)
        return Satz(subject_id=self._uid, satz_art=art, quell_tabelle=tabelle,
                    quell_spalte=spalte, quell_schluessel=str(schluessel),
                    fassung=fassung, ts=ts, urheber=urheber, text=text), gek

    @staticmethod
    def _spalten(con: sqlite3.Connection, tabelle: str) -> Set[str]:
        """Spaltennamen einer Tabelle (fuer nachtraeglich ergaenzte Spalten)."""
        try:
            cur = con.execute('PRAGMA table_info("%s")' % tabelle)
            return {str(r[1]) for r in cur.fetchall()}
        except sqlite3.Error:
            return set()

    # ------------------------------------------------------------ annotationen
    def _annotationen(self, con: sqlite3.Connection,
                      vorhanden: Set[str]) -> Tuple[List[Satz], int]:
        """
        annotations.text / .category / .tags_json samt Fassungsbestimmung.

        Die Spalten deleted_at/prev_id sind erst nachtraeglich hinzugekommen
        (db/evidence_db.py:206-208 fuehrt sie als Nachruestspalten). Fehlt eine
        davon in einer alten Datei, wird sie als 'nicht gesetzt' behandelt und
        alles gilt als 'aktuell' — die harmlose Richtung: es wird nichts
        ausgelassen, hoechstens etwas zu wohlwollend eingeordnet. Der Fall wird
        protokolliert.
        """
        if "annotations" not in vorhanden:
            return [], 0
        spalten = self._spalten(con, "annotations")
        hat_deleted = "deleted_at" in spalten
        hat_prev = "prev_id" in spalten
        if not (hat_deleted and hat_prev):
            logger.info(
                "Fall %d: annotations ohne %s — alle Fassungen gelten als "
                "'aktuell' (alter Schemastand).", self._uid,
                "deleted_at" if not hat_deleted else "prev_id")

        nachfolger: Set[int] = set()
        if hat_prev:
            cur = con.execute(
                "SELECT DISTINCT prev_id FROM annotations "
                "WHERE prev_id IS NOT NULL")
            nachfolger = {int(r[0]) for r in cur.fetchall() if r[0] is not None}

        felder = ["id", "category", "text", "ts", "created_by"]
        if "tags_json" in spalten:
            felder.append("tags_json")
        if hat_deleted:
            felder.append("deleted_at")
        cur = con.execute("SELECT %s FROM annotations ORDER BY id"
                          % ", ".join('"%s"' % f for f in felder))

        saetze: List[Satz] = []
        gek_gesamt = 0
        for r in cur.fetchall():
            aid = int(r["id"])
            geloescht = hat_deleted and r["deleted_at"] is not None
            if not geloescht:
                fassung = FASSUNG_AKTUELL
            elif aid in nachfolger:
                fassung = FASSUNG_UEBERHOLT
            else:
                fassung = FASSUNG_ZURUECKGENOMMEN

            ts = None if r["ts"] is None else int(r["ts"])
            urheber = r["created_by"] or None

            for art, spalte, rohwert, ist_json in (
                    ("annotation_text", "text", r["text"], False),
                    ("annotation_kategorie", "category", r["category"], False),
                    ("annotation_schlagworte", "tags_json",
                     r["tags_json"] if "tags_json" in felder else None, True)):
                if rohwert is None:
                    continue
                text = (json_klartext(rohwert) if ist_json
                        else html_zu_klartext(rohwert))
                satz, gek = self._satz(art, "annotations", spalte, aid,
                                       fassung, ts, urheber, text)
                gek_gesamt += gek
                if satz is not None:
                    saetze.append(satz)
        return saetze, gek_gesamt

    # ---------------------------------------------------------------- berichte
    def _berichte(self, con: sqlite3.Connection,
                  vorhanden: Set[str]) -> Tuple[List[Satz], int]:
        """reports.title — Vermerk-/Berichtstitel."""
        if "reports" not in vorhanden:
            return [], 0
        cur = con.execute(
            'SELECT "id", "title", "created_by", "created_at" '
            'FROM reports ORDER BY id')
        saetze: List[Satz] = []
        gek_gesamt = 0
        for r in cur.fetchall():
            satz, gek = self._satz(
                "bericht_titel", "reports", "title", int(r["id"]),
                FASSUNG_AKTUELL,
                None if r["created_at"] is None else int(r["created_at"]),
                r["created_by"] or None, html_zu_klartext(r["title"]))
            gek_gesamt += gek
            if satz is not None:
                saetze.append(satz)
        return saetze, gek_gesamt

    # -------------------------------------------------------------- bausteine
    def _bausteine(self, con: sqlite3.Connection,
                   vorhanden: Set[str]) -> Tuple[List[Satz], int]:
        """
        report_blocks.block_data (Editor.js-JSON) und .placeholder_values_json.

        Der Klartext wird REKURSIV eingesammelt statt nach Blocktypen
        aufgezaehlt — ein zehnter Blocktyp waere in einer Aufzaehlung
        unsichtbar (Begruendung ausfuehrlich in block_text.py).

        'updated_at' ist der Zeitstempel des Satzes und nicht 'created_at':
        gesucht wird nach dem, was JETZT im Baustein steht, und das stammt vom
        Zeitpunkt der letzten Bearbeitung.
        """
        if "report_blocks" not in vorhanden:
            return [], 0
        spalten = self._spalten(con, "report_blocks")
        felder = ["block_id", "block_data", "author", "updated_at"]
        if "placeholder_values_json" in spalten:
            felder.append("placeholder_values_json")
        cur = con.execute("SELECT %s FROM report_blocks ORDER BY block_id"
                          % ", ".join('"%s"' % f for f in felder))
        saetze: List[Satz] = []
        gek_gesamt = 0
        for r in cur.fetchall():
            bid = str(r["block_id"])
            ts = None if r["updated_at"] is None else int(r["updated_at"])
            urheber = r["author"] or None
            for art, spalte in (("berichtsbaustein", "block_data"),
                                ("platzhalterwert", "placeholder_values_json")):
                if spalte not in felder:
                    continue
                satz, gek = self._satz(art, "report_blocks", spalte, bid,
                                       FASSUNG_AKTUELL, ts, urheber,
                                       json_klartext(r[spalte]))
                gek_gesamt += gek
                if satz is not None:
                    saetze.append(satz)
        return saetze, gek_gesamt

    # ------------------------------------------------------------------ anker
    def _anker(self, con: sqlite3.Connection,
               vorhanden: Set[str]) -> Tuple[List[Satz], int]:
        """
        report_anchors.anchor_text — der ZITIERTE Ankertext.

        Er ist bewusst eigenstaendig indiziert und keine Dublette des
        Annotationstextes: der Anker haelt den Wortlaut fest, wie er ZUM
        ZITATZEITPUNKT lautete. Wird die Annotation spaeter bearbeitet, sind
        beide Texte verschieden — und genau diese Abweichung kann in einer
        Ermittlung erheblich sein.
        """
        if "report_anchors" not in vorhanden:
            return [], 0
        cur = con.execute(
            'SELECT "id", "anchor_text", "created_at" '
            'FROM report_anchors ORDER BY id')
        saetze: List[Satz] = []
        gek_gesamt = 0
        for r in cur.fetchall():
            satz, gek = self._satz(
                "berichtsanker", "report_anchors", "anchor_text", int(r["id"]),
                FASSUNG_AKTUELL,
                None if r["created_at"] is None else int(r["created_at"]),
                None, html_zu_klartext(r["anchor_text"]))
            gek_gesamt += gek
            if satz is not None:
                saetze.append(satz)
        return saetze, gek_gesamt

    # ------------------------------------------------------------- kommentare
    def _kommentare(self, con: sqlite3.Connection,
                    vorhanden: Set[str]) -> Tuple[List[Satz], int]:
        """
        report_comments.comment_text / .suggested_content (Gegenlesen).

        FASSUNG: status='revoked' -> zurueckgenommen, alles andere -> aktuell.
        'dismissed' ist AUSDRUECKLICH NICHT 'zurueckgenommen': ein abgelehnter
        Kommentar ist geaeussert worden und bleibt Arbeitsstand; nur der
        WIDERRUF nimmt ihn zurueck. Die CHECK-Liste der Spalte steht in
        db/evidence_db.py:322 ('pending','addressed','dismissed','revoked').
        """
        if "report_comments" not in vorhanden:
            return [], 0
        spalten = self._spalten(con, "report_comments")
        felder = ["id", "comment_text", "author", "created_at"]
        if "suggested_content" in spalten:
            felder.append("suggested_content")
        hat_status = "status" in spalten
        if hat_status:
            felder.append("status")
        cur = con.execute("SELECT %s FROM report_comments ORDER BY id"
                          % ", ".join('"%s"' % f for f in felder))
        saetze: List[Satz] = []
        gek_gesamt = 0
        for r in cur.fetchall():
            fassung = (FASSUNG_ZURUECKGENOMMEN
                       if hat_status and str(r["status"]) == "revoked"
                       else FASSUNG_AKTUELL)
            ts = None if r["created_at"] is None else int(r["created_at"])
            urheber = r["author"] or None
            for art, spalte in (("gegenlesen_kommentar", "comment_text"),
                                ("gegenlesen_vorschlag", "suggested_content")):
                if spalte not in felder:
                    continue
                satz, gek = self._satz(art, "report_comments", spalte,
                                       int(r["id"]), fassung, ts, urheber,
                                       html_zu_klartext(r[spalte]))
                gek_gesamt += gek
                if satz is not None:
                    saetze.append(satz)
        return saetze, gek_gesamt

    # --------------------------------------------------------------- freigaben
    def _freigaben(self, con: sqlite3.Connection,
                   vorhanden: Set[str]) -> Tuple[List[Satz], int]:
        """report_approvals.note — der Freigabevermerk."""
        if "report_approvals" not in vorhanden:
            return [], 0
        cur = con.execute(
            'SELECT "id", "note", "approved_by", "approved_at" '
            'FROM report_approvals ORDER BY id')
        saetze: List[Satz] = []
        gek_gesamt = 0
        for r in cur.fetchall():
            satz, gek = self._satz(
                "freigabevermerk", "report_approvals", "note", int(r["id"]),
                FASSUNG_AKTUELL,
                None if r["approved_at"] is None else int(r["approved_at"]),
                r["approved_by"] or None, html_zu_klartext(r["note"]))
            gek_gesamt += gek
            if satz is not None:
                saetze.append(satz)
        return saetze, gek_gesamt

    # ------------------------------------------------------------------ aliase
    def _aliase(self, con: sqlite3.Connection,
                vorhanden: Set[str]) -> Tuple[List[Satz], int]:
        """
        investigator_aliases.term — die fallbezogenen Alias-Notizen.

        Fuer den Hauptzweck der Funktion (Kreuzbezug ueber Nicknames) ist das
        die ergiebigste Spalte ueberhaupt: hier steht genau das, wonach gesucht
        wird, und nichts sonst.
        """
        if "investigator_aliases" not in vorhanden:
            return [], 0
        cur = con.execute(
            'SELECT "id", "term", "created_by", "created_at" '
            'FROM investigator_aliases ORDER BY id')
        saetze: List[Satz] = []
        gek_gesamt = 0
        for r in cur.fetchall():
            satz, gek = self._satz(
                "ermittler_alias", "investigator_aliases", "term",
                int(r["id"]), FASSUNG_AKTUELL,
                None if r["created_at"] is None else int(r["created_at"]),
                r["created_by"] or None, html_zu_klartext(r["term"]))
            gek_gesamt += gek
            if satz is not None:
                saetze.append(satz)
        return saetze, gek_gesamt
