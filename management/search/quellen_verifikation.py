# =============================================================================
# management/search/quellen_verifikation.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B562)
# =============================================================================
# Zweck:
#   QuellenVerifikation — liest zu einem Indextreffer die QUELLE nach und
#   stellt fest, ob der indizierte Text dort noch so steht.
#
#   Grundregel 10: eine Klasse, eine Datei.
#
# ── DIESES MODUL IST DER GRUND, WARUM DER INDEX KEIN BEWEISMITTEL SEIN MUSS ─
#
#   Festlegung aus Klaerung AP-3E v0.2 §6 Nr. 3, von mc bestaetigt:
#   "Der Index ... ist ein HILFSMITTEL, kein Beweismittel. Sie wird nie
#   zitiert; jeder Treffer wird vor der Anzeige GEGEN DIE QUELLE verifiziert."
#
#   Ohne diese Klasse waere der Satz eine Absichtserklaerung. Mit ihr ist er
#   ein Mechanismus: was in Stufe 2 angezeigt wird, stammt aus
#   evidence_<uid>.db und nicht aus search_index.db — der Index liefert nur
#   die ADRESSE (Fall, Tabelle, Spalte, Schluessel).
#
#   DAS IST KEIN FORMALISMUS. Der Index kann veraltet sein (er wird nur
#   ausdruecklich aufgefrischt, Entscheidung mc 2026-07-26). Wuerde die Sicht
#   den indizierten Text zeigen, zitierte eine Ermittlerin unter Umstaenden
#   eine Annotation, die seit Wochen anders lautet — und niemand saehe es.
#
# ── VIER BEFUNDE, UND SIE SIND NICHT AUSTAUSCHBAR ───────────────────────────
#
#   'bestaetigt'          — Quelle gelesen, Text stimmt ueberein. NUR dann
#                           wird ein Ausschnitt angezeigt.
#   'abweichend'          — Der Datensatz existiert, sein Text ist aber ein
#                           anderer. Der Index ist veraltet. Es wird KEIN Text
#                           gezeigt, sondern der Befund benannt.
#   'verschwunden'        — Der Datensatz gibt es nicht mehr.
#   'quelle_nicht_lesbar' — Die Datei fehlt oder ist nicht lesbar. Das ist
#                           NICHT 'verschwunden': im ersten Fall wissen wir,
#                           dass der Datensatz weg ist, im zweiten wissen wir
#                           GAR NICHTS. In einer Ermittlungsakte duerfen diese
#                           beiden Auskuenfte nicht gleich aussehen
#                           (Grundregel 1; dieselbe Trennschaerfe wie
#                           'nicht_geprueft'/'ohne_feststellung' im
#                           Fristenmonitor, Build 535 TA16).
#
# ── DER VERGLEICH LAEUFT UEBER DIESELBE NORMALISIERUNG WIE DER INDEXLAUF ────
#
#   Der Indexbauer speichert nicht den Rohwert, sondern den KLARTEXT
#   (block_text.html_zu_klartext bzw. json_klartext). Verglichen wird deshalb
#   Klartext gegen Klartext — und zwar durch AUFRUF DERSELBEN FUNKTIONEN,
#   nicht durch eine nachgebaute zweite Fassung. Zwei Normalisierungen waeren
#   zwei Antworten auf die Frage, was im Text steht, und der Unterschied
#   erschiene als 'abweichend' bei jedem einzelnen Treffer.
#
#   REIN LESEND: 'file:<pfad>?mode=ro'. Der Migrationsvorbehalt fuer die
#   Beweismitteldatenbanken ist nicht beruehrt.
#
# Version: v0.8.562 · Build: 562 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Dict, Optional

from management.search.block_text import html_zu_klartext, json_klartext
from management.search.index_vokabular import SATZ_ART_NACH_CODE

logger = logging.getLogger(__name__)

BEFUND_BESTAETIGT = "bestaetigt"
BEFUND_ABWEICHEND = "abweichend"
BEFUND_VERSCHWUNDEN = "verschwunden"
BEFUND_QUELLE_NICHT_LESBAR = "quelle_nicht_lesbar"

VERIFIKATION_BEFUNDE = (
    BEFUND_BESTAETIGT,
    BEFUND_ABWEICHEND,
    BEFUND_VERSCHWUNDEN,
    BEFUND_QUELLE_NICHT_LESBAR,
)

BEFUND_KLARTEXT: Dict[str, str] = {
    BEFUND_BESTAETIGT: "gegen die Quelle bestaetigt",
    BEFUND_ABWEICHEND: ("Index veraltet — der Datensatz existiert, sein Text "
                        "lautet in der Quelle anders. Kein Ausschnitt "
                        "angezeigt."),
    BEFUND_VERSCHWUNDEN: ("Der Datensatz ist in der Quelle nicht mehr "
                          "vorhanden."),
    BEFUND_QUELLE_NICHT_LESBAR: ("Die Beweismitteldatenbank ist nicht lesbar "
                                 "— es ist NICHT gesagt, dass der Datensatz "
                                 "fehlt."),
}

#: Welche Quellspalten JSON tragen und deshalb ueber json_klartext laufen.
#  Muss zu evidence_source_reader passen; SU02 haelt beide gegeneinander.
_JSON_SPALTEN = frozenset({"tags_json", "block_data",
                           "placeholder_values_json"})

#: Primaerschluessel je Quelltabelle. report_blocks hat einen TEXT-Schluessel
#  (db/evidence_db.py:288-298) — deshalb ist quell_schluessel im Index TEXT.
_PK_SPALTE: Dict[str, str] = {
    "annotations": "id",
    "reports": "id",
    "report_blocks": "block_id",
    "report_anchors": "id",
    "report_comments": "id",
    "report_approvals": "id",
    "investigator_aliases": "id",
}


class QuellenVerifikation:
    """Prueft Indextreffer gegen die Beweismitteldatenbank (read-only)."""

    def __init__(self, evidence_dir: object) -> None:
        self._dir = Path(str(evidence_dir))
        #: Verbindungen je Fall, damit eine Trefferliste mit zwanzig Treffern
        #  aus demselben Fall die Datei EINMAL oeffnet und nicht zwanzigmal.
        #  Auf dem Netzlaufwerk (PROD, Faktor rund 24 gegenueber DEV) ist das
        #  der Unterschied zwischen einer Sekunde und einer halben Minute.
        self._offen: Dict[int, Optional[sqlite3.Connection]] = {}

    def pfad(self, subject_id: int) -> Path:
        return self._dir / ("evidence_%d.db" % int(subject_id))

    # ------------------------------------------------------------ Verbindung
    def _con(self, subject_id: int) -> Optional[sqlite3.Connection]:
        """Verbindung zu einem Fall (gepuffert). None = nicht lesbar."""
        uid = int(subject_id)
        if uid in self._offen:
            return self._offen[uid]
        p = self.pfad(uid)
        con: Optional[sqlite3.Connection] = None
        if p.exists():
            try:
                con = sqlite3.connect("file:%s?mode=ro" % p.resolve(),
                                      uri=True)
            except sqlite3.Error as exc:
                logger.warning("Verifikation: %s nicht oeffenbar (%s)", p, exc)
                con = None
        self._offen[uid] = con
        return con

    def close(self) -> None:
        """Alle gepufferten Verbindungen schliessen."""
        for con in self._offen.values():
            if con is not None:
                try:
                    con.close()
                except Exception:  # pragma: no cover
                    pass
        self._offen.clear()

    def __enter__(self) -> "QuellenVerifikation":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ---------------------------------------------------------- Verifikation
    def pruefe(self, *, subject_id: int, satz_art: str, quell_tabelle: str,
               quell_spalte: str, quell_schluessel: str,
               index_text: str) -> Dict[str, object]:
        """
        Prueft EINEN Treffer gegen die Quelle.

        Rueckgabe:
          {'befund': <Code>, 'klartext': str, 'quelltext': str|None}

        'quelltext' ist NUR bei 'bestaetigt' gesetzt — und es ist der Text AUS
        DER QUELLE, nicht der aus dem Index. Auch wenn beide gleich sind: was
        angezeigt wird, muss aus der Beweismitteldatenbank stammen, sonst
        waere die Zusicherung aus Klaerung §6 Nr. 3 nur eine Behauptung.
        """
        con = self._con(subject_id)
        if con is None:
            return self._ergebnis(BEFUND_QUELLE_NICHT_LESBAR)

        pk = _PK_SPALTE.get(quell_tabelle)
        if pk is None:
            # Eine Satzart, deren Tabelle hier nicht gefuehrt ist, kann nicht
            # verifiziert werden — und dann wird auch NICHTS angezeigt. Das
            # ist der sichere Ausgang: eine unverifizierbare Fundstelle als
            # 'bestaetigt' durchzulassen waere die eine Abkuerzung, die dieses
            # Modul gerade verhindern soll.
            logger.warning("Verifikation: unbekannte Quelltabelle %r "
                           "(Satzart %s)", quell_tabelle, satz_art)
            return self._ergebnis(BEFUND_QUELLE_NICHT_LESBAR)

        try:
            row = con.execute(
                'SELECT "%s" FROM "%s" WHERE "%s" = ?'
                % (quell_spalte, quell_tabelle, pk),
                (quell_schluessel,)).fetchone()
        except sqlite3.Error as exc:
            logger.warning("Verifikation: %s.%s nicht lesbar (%s)",
                           quell_tabelle, quell_spalte, exc)
            return self._ergebnis(BEFUND_QUELLE_NICHT_LESBAR)

        if row is None:
            return self._ergebnis(BEFUND_VERSCHWUNDEN)

        roh = row[0]
        # DIESELBE Normalisierung wie beim Indexlauf — durch Aufruf derselben
        # Funktionen, nicht durch eine nachgebaute zweite Fassung.
        quelltext = (json_klartext(roh) if quell_spalte in _JSON_SPALTEN
                     else html_zu_klartext(roh)).strip()

        if quelltext == (index_text or "").strip():
            return self._ergebnis(BEFUND_BESTAETIGT, quelltext)
        return self._ergebnis(BEFUND_ABWEICHEND)

    @staticmethod
    def _ergebnis(befund: str,
                  quelltext: Optional[str] = None) -> Dict[str, object]:
        return {"befund": befund,
                "klartext": BEFUND_KLARTEXT.get(befund, befund),
                "quelltext": quelltext}

    @staticmethod
    def ist_json_spalte(spalte: str) -> bool:
        """Fuer den Querprobe-Test SU02."""
        return spalte in _JSON_SPALTEN

    @staticmethod
    def bekannte_tabellen() -> frozenset:
        """Fuer den Querprobe-Test SU02 gegen SATZ_ART_NACH_CODE."""
        _ = SATZ_ART_NACH_CODE  # Import belegen: die Listen gehoeren zusammen.
        return frozenset(_PK_SPALTE)
