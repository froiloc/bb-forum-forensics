# =============================================================================
# management/search/index_status.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B560)
# =============================================================================
# Zweck:
#   SearchIndexStatus — beantwortet REIN LESEND die Frage, wie aktuell der
#   Index ist: Wann wurde zuletzt indiziert? Welche Faelle sind seither
#   veraendert? Welche sind neu? Welche verschwunden? Bei welchen ist der
#   Indexstand unvollstaendig?
#
# ── WARUM DAS EINE EIGENE KLASSE IST UND NICHT EINE METHODE DES BAUERS ──────
#
#   Weil es an ZWEI Stellen mit voellig verschiedener Berechtigung gebraucht
#   wird:
#     * beim Indexlauf (management/search/index_builder.py) — entscheidet, was
#       neu gelesen werden muss;
#     * bei JEDER Abfrage (Build 562) — jede Antwort nennt den Indexzeitpunkt
#       und die Zahl der seither veraenderten Datenbanken (Klaerung §6 Nr. 5,
#       Entscheidungen mc §1).
#
#   Die Abfrage darf den Index NICHT veraendern (Entscheidung mc 2026-07-26:
#   "Nur ausdruecklich, inkrementell" — die Abfrage indiziert nie). Waere die
#   Statusermittlung eine Methode des Bauers, muesste der Abfragepfad den Bauer
#   instanziieren, und damit laege der Schreibpfad einen Tippfehler weit von
#   einem Pfad entfernt, der nur lesen darf. Getrennte Klassen machen daraus
#   eine Unmoeglichkeit statt einer Verabredung.
#
# ── WARUM DER FINGERABDRUCK UND NICHT DIE UHRZEIT ────────────────────────────
#
#   Verglichen wird der WAL-sichere Fingerabdruck aus
#   management/reports/evidence_scanner.py:75-90 (Groesse + mtime_ns von .db
#   und -wal) gegen den beim Indexlauf gespeicherten. Nicht die Uhrzeit: eine
#   Datei kann geaendert worden sein, ohne dass die mtime der .db sich
#   bewegt hat (die WAL-Falle aus Build 374), und in PROD (Windows/UNC/SMB)
#   kann mtime grob oder verzoegert sein.
#
#   DER FINGERABDRUCK IST EIN BESCHLEUNIGER, NIE EIN BEWEISMITTEL (mc, siehe
#   evidence_scanner.py:17-22). Ein Fehltreffer kostet nur Zeit (unnoetiges
#   Neulesen); ein Treffer spart sie. Fuer Beweisrelevantes gilt ausschliesslich
#   der Inhaltshash — hier geht es aber nicht um einen Beweis, sondern um die
#   Frage, ob nachgelesen werden muss.
#
#   FOLGE, DIE IN JEDER ANTWORT STEHEN MUSS: Ein Fall in 'veraendert' bedeutet
#   NICHT, dass die Trefferlage falsch ist — nur, dass sie nicht belegt aktuell
#   ist. Das ist ein Unterschied, den eine Ermittlungsakte tragen muss.
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================

import time
from pathlib import Path
from typing import Dict, List, Optional

from db.search_index_db import SearchIndexDb
from management.reports.evidence_scanner import EvidenceScanner
from management.search.index_vokabular import (
    BEFUNDE_UNVOLLSTAENDIG,
    BEFUND_BEZEICHNUNG,
)

#: Schluessel in index_meta fuer den Zeitpunkt des letzten abgeschlossenen Laufs.
META_LETZTER_LAUF = "letzter_lauf_at"

#: Schluessel in index_meta fuer die Art des letzten Laufs ('voll' | 'inkrementell').
META_LETZTE_LAUFART = "letzter_lauf_art"


class SearchIndexStatus:
    """Vergleicht den Indexstand gegen das Verzeichnis der evidence-Datenbanken."""

    def __init__(self, evidence_dir: object, index_db: SearchIndexDb) -> None:
        self._scanner = EvidenceScanner(str(evidence_dir))
        self._index = index_db

    @property
    def evidence_dir(self) -> Path:
        return self._scanner.directory

    def status(self, jetzt: Optional[int] = None) -> Dict[str, object]:
        """
        Der vollstaendige Indexstand als auswertbare Struktur.

        Rueckgabe (alle Zahlen gemessen, keine geschaetzt):
          verzeichnis            — geprueftes Verzeichnis (Klartext).
          verzeichnis_vorhanden  — False heisst NICHT 'keine Faelle', sondern
                                   'nicht nachgesehen'. Der Aufrufer MUSS das
                                   unterscheiden (Grundregel 1).
          index_pfad, index_erzeugt_at, letzter_lauf_at, letzte_lauf_art
          faelle_im_verzeichnis, faelle_im_index, saetze_gesamt
          neu                    — im Verzeichnis, noch nicht im Index.
          veraendert             — Fingerabdruck weicht ab.
          verschwunden           — im Index, aber nicht mehr im Verzeichnis.
          unveraendert           — belegt aktuell.
          unvollstaendig         — je Fall der Befund, der den Indexstand
                                   unvollstaendig macht (nicht lesbar u.a.).
          aktuell                — True nur, wenn nichts neu, veraendert oder
                                   verschwunden ist UND kein Fall unvollstaendig
                                   ist.
        """
        jetzt = int(time.time()) if jetzt is None else int(jetzt)
        verzeichnis_da = self._scanner.directory.is_dir()
        vorhanden = self._scanner.fingerprints() if verzeichnis_da else {}
        quellen = self._index.quellen()

        neu: List[int] = []
        veraendert: List[int] = []
        unveraendert: List[int] = []
        for uid, fp in sorted(vorhanden.items()):
            zeile = quellen.get(uid)
            if zeile is None:
                neu.append(uid)
            elif str(zeile["fingerprint"]) != fp:
                veraendert.append(uid)
            else:
                unveraendert.append(uid)

        verschwunden = sorted(set(quellen) - set(vorhanden))

        unvollstaendig: List[Dict[str, object]] = []
        for uid in sorted(quellen):
            befund = str(quellen[uid]["befund"])
            if befund in BEFUNDE_UNVOLLSTAENDIG:
                unvollstaendig.append({
                    "subject_id": uid,
                    "befund": befund,
                    "befund_klartext": BEFUND_BEZEICHNUNG.get(befund, befund),
                    "detail": quellen[uid]["befund_detail"],
                })

        letzter = self._index.meta(META_LETZTER_LAUF)
        erzeugt = self._index.meta("erzeugt_at")
        return {
            "geprueft_at": jetzt,
            "verzeichnis": str(self._scanner.directory),
            "verzeichnis_vorhanden": verzeichnis_da,
            "index_pfad": str(self._index.pfad),
            "index_erzeugt_at": int(erzeugt) if erzeugt else None,
            "letzter_lauf_at": int(letzter) if letzter else None,
            "letzte_lauf_art": self._index.meta(META_LETZTE_LAUFART),
            "tokenizer_wort": self._index.meta("tokenizer_wort"),
            "tokenizer_teil": self._index.meta("tokenizer_teil"),
            "faelle_im_verzeichnis": len(vorhanden),
            "faelle_im_index": len(quellen),
            "saetze_gesamt": self._index.satz_zahl(),
            "neu": neu,
            "veraendert": veraendert,
            "verschwunden": verschwunden,
            "unveraendert": unveraendert,
            "unvollstaendig": unvollstaendig,
            "aktuell": (verzeichnis_da and not neu and not veraendert
                        and not verschwunden and not unvollstaendig),
        }

    def zu_indizieren(self, *, voll: bool = False) -> List[int]:
        """
        Die Faelle, die der naechste Lauf lesen muss.

        voll=True liefert ALLE Faelle des Verzeichnisses — der Neuaufbau. Er ist
        auf dem Netzlaufwerk teuer und deshalb ausdruecklich anzufordern; er ist
        aber der einzige Weg, einen Fingerabdruck-Fehltreffer aufzuloesen
        (mtime auf UNC/SMB kann grob sein, evidence_scanner.py:17-22).
        """
        st = self.status()
        if voll:
            return sorted(set(st["neu"]) | set(st["veraendert"])
                          | set(st["unveraendert"]))
        # Unvollstaendige Faelle werden MITGENOMMEN, auch wenn ihr
        # Fingerabdruck unveraendert ist: 'nicht lesbar' kann ein
        # voruebergehender Zustand gewesen sein (Datei gerade in Benutzung),
        # und ein Fall, der einmal nicht gelesen werden konnte, bliebe sonst
        # bis zu seiner naechsten Aenderung dauerhaft ausserhalb des Index.
        unvollstaendig = [int(e["subject_id"]) for e in st["unvollstaendig"]]
        return sorted(set(st["neu"]) | set(st["veraendert"])
                      | set(unvollstaendig))
