# =============================================================================
# management/search/index_builder.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B560)
# =============================================================================
# Zweck:
#   SearchIndexBuilder — die Steuerung des Indexlaufs: welche Faelle gelesen
#   werden, in welcher Reihenfolge, und was der Lauf am Ende BERICHTET.
#
# ── DIE ENTSCHEIDUNG, DIE DIESES MODUL PRAEGT (mc, 2026-07-26) ──────────────
#
#   "Nur ausdruecklich, inkrementell." Die ABFRAGE INDIZIERT NIE. Aufgefrischt
#   wird ueber die Befehlszeile (management/search/index_cli.py) oder — ab
#   Build 563 — ueber einen Knopf in der Sicht, und dabei werden nur die
#   Datenbanken gelesen, deren Fingerabdruck sich seit dem letzten Lauf
#   geaendert hat.
#
#   Begruendung (mitgetragen): In PROD liegen die Beweismitteldatenbanken auf
#   einem Netzlaufwerk; die gemessene Verlangsamung gegenueber DEV betraegt
#   rund Faktor 24 (Messung 2026-07-25, Uebergabe Builds 533-535 §5 Nr. 4).
#   Wuerde die Abfrage nachindizieren, waere die erste Suche eines Arbeitstages
#   ein minutenlanger Vorgang — und, schwerer wiegend, die Antwort haette
#   keinen benennbaren Indexzeitpunkt mehr, weil der Index sich waehrend der
#   Abfrage selbst veraendert haette. Eine Antwort, die ihren eigenen Stand
#   nicht nennen kann, ist in einer Ermittlungsakte wertlos.
#
# ── WAS DER LAUF BERICHTET, UND WARUM SO VIEL ────────────────────────────────
#
#   Der Bericht nennt je Fall den Befund und in der Summe: gelesen, ohne
#   Tabelle, nicht lesbar, nicht oeffenbar, fehlend, entfernt, gekuerzt. KEINE
#   dieser Zahlen ist Zierrat — jede beantwortet eine Frage, die sonst offen
#   bliebe, und zwar in genau der Form, die eine Ermittlungsakte tragen muss:
#   'nachgesehen und nichts gefunden' und 'nicht nachgesehen' duerfen nicht
#   gleich aussehen (dieselbe Trennschaerfe wie im Fristenmonitor, Build 535
#   TA16).
#
#   EIN FEHLER BEI EINEM FALL BEENDET DEN LAUF NICHT. Er wird zum Befund dieses
#   Falls, und der Lauf geht weiter. Die Gegenrichtung — Abbruch beim ersten
#   Fehler — hinterliesse die restlichen Datenbanken ungelesen, ohne Spur
#   darueber, welche das waren.
#
# ── DIE REIHENFOLGE IST AUFSTEIGEND NACH subject_id, UND DAS IST ABSICHT ─────
#
#   Der Lauf ist damit reproduzierbar: zweimal derselbe Ausgangsstand ergibt
#   zweimal denselben Bericht. Eine Reihenfolge nach Dateigroesse oder mtime
#   waere schneller zu 'ersten Ergebnissen', aber der Bericht liesse sich dann
#   zwischen zwei Laeufen nicht mehr vergleichen.
#
# Version: v0.8.560 · Build: 560 · 2026-07-26
# =============================================================================

import logging
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from db.search_index_db import SearchIndexDb
from management.reports.evidence_scanner import EvidenceScanner
from management.search.evidence_source_reader import EvidenceSourceReader
from management.search.index_status import (
    META_LETZTE_LAUFART,
    META_LETZTER_LAUF,
    SearchIndexStatus,
)
from management.search.index_vokabular import (
    BEFUND_GELESEN,
    BEFUNDE_UNVOLLSTAENDIG,
    BEFUND_BEZEICHNUNG,
)

logger = logging.getLogger(__name__)

LAUFART_VOLL = "voll"
LAUFART_INKREMENTELL = "inkrementell"


class SearchIndexBuilder:
    """Baut und pflegt den FTS5-Index ueber alle evidence_<uid>.db."""

    def __init__(self, evidence_dir: object, index_db: SearchIndexDb) -> None:
        self._scanner = EvidenceScanner(str(evidence_dir))
        self._index = index_db
        self._status = SearchIndexStatus(evidence_dir, index_db)

    @property
    def evidence_dir(self) -> Path:
        return self._scanner.directory

    @property
    def status(self) -> SearchIndexStatus:
        """Die (rein lesende) Statusermittlung — auch fuer den Aufrufer."""
        return self._status

    # ------------------------------------------------------------------- Lauf
    def lauf(self, *, voll: bool = False,
             nur: Optional[Sequence[int]] = None,
             optimieren: bool = True,
             jetzt: Optional[int] = None,
             fortschritt: Optional[Callable[[int, int, int], None]] = None
             ) -> Dict[str, object]:
        """
        Fuehrt einen Indexlauf aus und liefert den Bericht.

        Args:
            voll:        True = alle Faelle neu lesen (Neuaufbau). Teuer, aber
                         der einzige Weg, einen Fingerabdruck-Fehltreffer
                         aufzuloesen.
            nur:         Nur diese subject_ids (Diagnose/Nacharbeit einzelner
                         Faelle). Schlaegt 'voll' UND die Inkrementlogik.
            optimieren:  Nach dem Lauf FTS5-'optimize' fahren. Teuer; deshalb
                         genau EINMAL am Ende und nicht je Fall.
            jetzt:       Zeitpunkt (Unix-Sekunden), fuer reproduzierbare Tests.
            fortschritt: Rueckruf(fertig, gesamt, subject_id) — fuer die CLI.

        Returns:
            Der Laufbericht (s. Modulkopf). 'verzeichnis_vorhanden=False'
            heisst NICHT 'keine Faelle', sondern 'nicht nachgesehen'.
        """
        jetzt = int(time.time()) if jetzt is None else int(jetzt)
        begonnen = time.monotonic()

        if not self._scanner.directory.is_dir():
            # NICHT STILL WEITERRECHNEN: ein fehlendes Verzeichnis ist ein
            # Betriebsfehler (paths.evidence_db_dir falsch gesetzt), kein
            # leerer Bestand. Derselbe Fall wie 'nicht_geprueft' im
            # Fristenmonitor (Build 535, TA16).
            logger.error(
                "Indexlauf ohne Verzeichnis: %s existiert nicht. Es wird "
                "NICHTS indiziert und NICHTS entfernt.",
                self._scanner.directory)
            return self._bericht(jetzt, begonnen, LAUFART_INKREMENTELL,
                                 [], [], verzeichnis_vorhanden=False)

        vorhanden = dict(self._scanner.list_cases())
        if nur is not None:
            ziele = [int(u) for u in nur]
            laufart = LAUFART_INKREMENTELL
        else:
            ziele = self._status.zu_indizieren(voll=voll)
            laufart = LAUFART_VOLL if voll else LAUFART_INKREMENTELL

        ergebnisse: List[Dict[str, object]] = []
        gesamt = len(ziele)
        for i, uid in enumerate(ziele, start=1):
            ergebnisse.append(self._einen_fall(uid, vorhanden, jetzt))
            if fortschritt is not None:
                try:
                    fortschritt(i, gesamt, uid)
                except Exception:  # pragma: no cover — Anzeige darf nie werfen
                    logger.debug("Fortschrittsanzeige hat geworfen — ignoriert.")

        # Verschwundene Faelle entfernen. Sie stillschweigend stehen zu lassen
        # waere die schlechteste Variante: die Suche fuende Treffer, die sich
        # nicht mehr gegen die Quelle verifizieren lassen (der Index ist
        # Hilfsmittel und wird NIE zitiert — genau deshalb muss er auf eine
        # existierende Quelle zeigen).
        entfernt: List[int] = []
        if nur is None:
            for uid in sorted(set(self._index.quellen()) - set(vorhanden)):
                self._index.entferne_fall(uid)
                entfernt.append(uid)
                logger.info("Fall %d aus dem Index entfernt (Quelle "
                            "verschwunden).", uid)

        if optimieren and ergebnisse:
            self._index.optimiere()

        self._index.setze_meta(META_LETZTER_LAUF, jetzt)
        self._index.setze_meta(META_LETZTE_LAUFART, laufart)
        return self._bericht(jetzt, begonnen, laufart, ergebnisse, entfernt,
                             verzeichnis_vorhanden=True)

    # -------------------------------------------------------------- ein Fall
    def _einen_fall(self, uid: int, vorhanden: Dict[int, Path],
                    jetzt: int) -> Dict[str, object]:
        """Liest einen Fall und schreibt ihn in den Index. Wirft nicht."""
        pfad = vorhanden.get(uid)
        if pfad is None:
            # Der Fall stand in der Zielliste, ist aber nicht (mehr) da. Das
            # ist kein Fehler des Laufs, sondern ein Befund.
            pfad = self._scanner.directory / ("evidence_%d.db" % uid)
        # DER FINGERABDRUCK WIRD VOR DEM LESEN GENOMMEN, UND DAS IST DIE
        # ENTSCHEIDENDE REIHENFOLGE.
        #
        #   Aendert sich die Quelldatei WAEHREND des Lesens, dann steht im
        #   Index anschliessend der ALTE Fingerabdruck — der naechste Lauf
        #   sieht eine Abweichung und liest den Fall erneut. Das kostet einen
        #   ueberfluessigen Lesevorgang.
        #
        #   Naehme man ihn NACH dem Lesen, stuende der NEUE Fingerabdruck im
        #   Index, obwohl der gelesene Inhalt der alte ist: der Fall gaelte als
        #   'belegt aktuell', waere es aber nicht, und niemand erfuehre davon.
        #   Ein ueberfluessiger Lesevorgang ist bezahlbar, eine stille
        #   Falschaussage ueber die Aktualitaet nicht (Grundregel 1).
        fingerprint = EvidenceScanner.fingerprint(pfad)
        leser = EvidenceSourceReader(uid, pfad)
        befund = leser.lies()
        zahl = self._index.ersetze_fall(
            uid, befund.saetze, db_pfad=str(pfad), fingerprint=fingerprint,
            befund=befund.befund, befund_detail=befund.detail,
            gekuerzt_zahl=befund.gekuerzt_zahl, jetzt=jetzt)
        if befund.befund != BEFUND_GELESEN:
            logger.warning("Fall %d: %s (%s)", uid,
                           BEFUND_BEZEICHNUNG.get(befund.befund, befund.befund),
                           befund.detail or "ohne Detail")
        return {
            "subject_id": uid,
            "befund": befund.befund,
            "befund_klartext": BEFUND_BEZEICHNUNG.get(befund.befund,
                                                      befund.befund),
            "detail": befund.detail,
            "saetze": zahl,
            "gekuerzt": befund.gekuerzt_zahl,
            "fehlende_tabellen": befund.fehlende_tabellen,
        }

    # -------------------------------------------------------------- Bericht
    @staticmethod
    def _bericht(jetzt: int, begonnen: float, laufart: str,
                 ergebnisse: Sequence[Dict[str, object]],
                 entfernt: Sequence[int], *,
                 verzeichnis_vorhanden: bool) -> Dict[str, object]:
        """
        Baut den Laufbericht.

        Die Zaehlung nach Befunden ist VOLLSTAENDIG und nicht auf 'Fehler ja/
        nein' verkuerzt: 'ohne Tabelle' und 'nicht lesbar' sind verschiedene
        Sachverhalte mit verschiedenen betrieblichen Folgen (das eine ruft nach
        einer Migration, das andere nach einem Blick auf die Datei).
        """
        nach_befund: Dict[str, int] = {}
        saetze = 0
        gekuerzt = 0
        unvollstaendig: List[Dict[str, object]] = []
        for e in ergebnisse:
            b = str(e["befund"])
            nach_befund[b] = nach_befund.get(b, 0) + 1
            saetze += int(e["saetze"])
            gekuerzt += int(e["gekuerzt"])
            if b in BEFUNDE_UNVOLLSTAENDIG:
                unvollstaendig.append(e)
        return {
            "lauf_at": jetzt,
            "laufart": laufart,
            "verzeichnis_vorhanden": verzeichnis_vorhanden,
            "dauer_ms": int((time.monotonic() - begonnen) * 1000),
            "faelle_gelesen": len(ergebnisse),
            "saetze_geschrieben": saetze,
            "saetze_gekuerzt": gekuerzt,
            "faelle_entfernt": list(entfernt),
            "nach_befund": nach_befund,
            "unvollstaendig": unvollstaendig,
            "ergebnisse": list(ergebnisse),
        }
