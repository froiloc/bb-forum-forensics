# =============================================================================
# management/person/person_sichtbarkeit.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ruhestand von Hand
# =============================================================================
# Zweck:
#   NUR-LESENDE Entscheidungsschicht fuer die Frage "welche Personen gehoeren
#   in diese Tabelle?" (Ticket 95139d2a). Eine Wahrheitsquelle fuer ALLE
#   Sichten — sonst driften fuenf Listen auseinander und jede blendet ein
#   bisschen anders aus.
#
# ---------------------------------------------------------------------------
# DIE DREI KLASSEN VON PERSONENLISTEN — DER KERN DIESES MODULS
# ---------------------------------------------------------------------------
# Bei der Durchsicht der Lesepfade auf 'person' (Volltextsuche "FROM person",
# 12.08.2026) zerfallen sie in drei Klassen, und die Unterscheidung ist keine
# Geschmacksfrage, sondern entscheidet ueber Beweisverlust:
#
#   (1) AUSWAHLLISTEN — die Liste bietet eine Person zur kuenftigen Wahl an
#       (Fall zuweisen, "Betroffene:r" einer Betreuungsnotiz, Personenauswahl
#       der Kapazitaetspflege). Hier ist die Ausblendung VOLLSTAENDIG: wer
#       ausgeschieden ist, darf nicht mehr NEU eingeplant werden — auch dann
#       nicht, wenn er noch Faelle traegt. Sonst waere die Ausblendung
#       wirkungslos, denn das Zuweisen ist genau der Fehler, den sie
#       verhindern soll.  -> fuer_auswahl()
#
#   (2) GRUNDMENGEN-TABELLEN — die Tabelle fuehrt eine Zeile JE PERSON und
#       zeigt daran deren Lage (Arbeitslast, Kapazitaets-Aggregat). Hier gilt
#       die Ausblendung per Default, ABER MIT EINER AUSNAHME: solange eine
#       inaktive Person noch OFFENE zugewiesene Faelle traegt, bleibt ihre
#       Zeile stehen und wird markiert. Wuerde sie verschwinden, verschwaende
#       offene Arbeit aus genau der Sicht, in der sie auffallen muss
#       (Grundregel 1; Entscheidung Alex, 12.08.2026).  -> fuer_grundmenge()
#
#   (3) NAMENSAUFLOESUNG — die Liste beschriftet BESTEHENDE Belege mit dem
#       Namen ihres Urhebers (Supporter einer Sitzung, Uebergabe-Protokoll,
#       Eskalations-Vermerk, Abwesenheits-Beschriftung, Akteur eines
#       Audit-Eintrags). HIER WIRD NIE GEFILTERT. Ein Beleg, dessen Urheber
#       ploetzlich namenlos ist, hat Beweiswert verloren — dieses Modul bietet
#       fuer diesen Fall bewusst KEINE Methode an, damit die Versuchung
#       gar nicht entsteht.
#
# ---------------------------------------------------------------------------
# WAS "OFFENE FAELLE" HEISST
# ---------------------------------------------------------------------------
#   status IN ('open','in_progress'). Das ist NICHT frei gewaehlt, sondern die
#   bestehende Definition der aktiven Last: workload/workload_repo.py,
#   _LoadAccumulator.active == s_open + s_prog, waehrend 'approved' und
#   'closed' dort als 'done' gelten. Eine zweite, eigene Definition an dieser
#   Stelle waere Drift (dieselbe Begruendung wie im Kopf von workload_repo.py
#   fuer die aufgerollte Ampel).
#
# ---------------------------------------------------------------------------
# VERHALTEN BEI UNSICHERHEIT — AUSDRUECKLICH KONSERVATIV
# ---------------------------------------------------------------------------
#   * Fehlen die M020-Spalten (Bestand vor Build 501), gilt jede Person als
#     aktiv und es wird NICHTS ausgeblendet — dasselbe defensive Verhalten wie
#     in PersonRepo._select_cols/_as_dict, damit Lesewerkzeuge auf Altbestand
#     nicht brechen.
#   * Ist die Tabelle 'cases' nicht lesbar, kann NICHT entschieden werden, wer
#     noch offene Arbeit traegt. Dann wird ebenfalls NICHTS ausgeblendet und
#     der Grund wandert als 'hinweis' in den Befund. Ein Filter, der im
#     Zweifel ausblendet, verschweigt im Zweifel Belege.
#
# KEIN Schreibpfad, KEINE Migration: coordinator.db wird ausschliesslich
# gelesen (Produktivbetrieb-Regel) -> kein Erkenntnisverlust moeglich.
#
# Version: v0.8.701 · Build: 701 · 2026-08-12
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

from management.person.sichtbarkeitsbefund import Sichtbarkeitsbefund

logger = logging.getLogger(__name__)

#: Fallstatus, die als OFFENE Arbeit gelten. Beleg: workload_repo.py
#: (_LoadAccumulator.active == status_open + status_in_progress).
OFFENE_STATUS = ("open", "in_progress")

#: Die Spalten aus M020, ohne die keine Aussage ueber Inaktivitaet moeglich ist.
_M020_COLS = ("is_active", "deactivated_at", "deactivated_reason")


class PersonSichtbarkeit:
    """
    Beantwortet nur-lesend, welche Personen in eine Tabelle gehoeren.

    Eine Instanz je Anfrage: die beiden Abfragen (inaktive Personen, offene
    Faelle je Person) werden beim ersten Zugriff EINMAL ausgefuehrt und
    gemerkt. Innerhalb einer Anfrage ist der Bestand ohnehin unveraenderlich
    (nur-lesende Verbindung), und mehrere Sichten pro Paket sollen nicht
    mehrfach zaehlen.
    """

    def __init__(self, con: sqlite3.Connection) -> None:
        self._con = con
        self._inaktive: Optional[Dict[int, Dict[str, Any]]] = None
        self._offene: Optional[Dict[int, int]] = None
        self._offene_hinweis: Optional[str] = None

    # ------------------------------------------------------------------ Lesen
    def hat_m020(self) -> bool:
        """
        True, wenn person die M020-Spalten fuehrt. Ohne sie gibt es im
        Bestand ueberhaupt keinen Inaktiv-Zustand — dann ist jede Ausblendung
        eine Erfindung.
        """
        have = {r[1] for r in self._con.execute("PRAGMA table_info(person)")}
        return all(c in have for c in _M020_COLS)

    def inaktive(self) -> Dict[int, Dict[str, Any]]:
        """
        person.id -> {system_username, display_name, deactivated_at,
        deactivated_reason} aller INAKTIVEN Personen. Leer, wenn M020 fehlt.
        """
        if self._inaktive is not None:
            return self._inaktive
        if not self.hat_m020():
            logger.info("PersonSichtbarkeit: person ohne M020-Spalten — es "
                        "wird nichts ausgeblendet.")
            self._inaktive = {}
            return self._inaktive
        out: Dict[int, Dict[str, Any]] = {}
        for r in self._con.execute(
            "SELECT id, system_username, display_name, deactivated_at, "
            "       deactivated_reason "
            "FROM person WHERE is_active = 0 ORDER BY system_username ASC"
        ):
            out[int(r[0])] = {
                "system_username": r[1],
                "display_name": r[2],
                "deactivated_at": (int(r[3]) if r[3] is not None else None),
                "deactivated_reason": r[4],
            }
        self._inaktive = out
        return out

    def offene_faelle(self) -> Dict[int, int]:
        """
        person.id -> Anzahl der ihr zugewiesenen OFFENEN Faelle (status
        open/in_progress). Personen ohne offene Faelle fehlen im dict (nicht
        mit 0 gefuehrt — die Abwesenheit IST die Null).

        Ist 'cases' nicht lesbar, bleibt das Ergebnis leer und
        offene_hinweis() nennt den Grund; die Filterwege blenden dann nichts
        aus (siehe Modulkopf).
        """
        if self._offene is not None:
            return self._offene
        marken = ", ".join("?" for _ in OFFENE_STATUS)
        try:
            rows = self._con.execute(
                "SELECT assigned_to, COUNT(*) FROM cases "
                "WHERE assigned_to IS NOT NULL AND status IN (%s) "
                "GROUP BY assigned_to" % marken,
                OFFENE_STATUS,
            ).fetchall()
        except sqlite3.Error as exc:
            # KEIN stilles 0: die Zahl ist nicht feststellbar, und das ist ein
            # Befund. Er wandert in den Hinweis und verhindert die Ausblendung.
            self._offene = {}
            self._offene_hinweis = (
                "Offene Faelle je Person nicht feststellbar (%s) — es wird "
                "nichts ausgeblendet. Migrationsstand pruefen: "
                "python -m management.migrate" % exc)
            logger.warning("PersonSichtbarkeit: %s", self._offene_hinweis)
            return self._offene
        self._offene = {int(r[0]): int(r[1]) for r in rows}
        return self._offene

    def offene_hinweis(self) -> Optional[str]:
        """Klartext, falls offene_faelle() nicht ermittelbar war; sonst None."""
        self.offene_faelle()   # erzwingt die Ermittlung (und damit den Hinweis)
        return self._offene_hinweis

    def offene_faelle_von(self, person_id: int) -> int:
        """Anzahl offener zugewiesener Faelle EINER Person (0, wenn keine)."""
        return int(self.offene_faelle().get(int(person_id), 0))

    # ---------------------------------------------------------------- Filtern
    def fuer_auswahl(self, zeilen: Iterable[Any], *,
                     id_feld: str = "id",
                     ausnahmen: Optional[Iterable[int]] = None
                     ) -> Sichtbarkeitsbefund:
        """
        Klasse (1) AUSWAHLLISTE: entfernt ALLE inaktiven Personen — auch die
        mit offenen Faellen. Wer ausgeschieden ist, darf nicht neu eingeplant
        werden; das ist der Zweck der Ausblendung.

        'ausnahmen' — Kennungen, die STEHENBLEIBEN, obwohl sie inaktiv sind,
        weil ein BESTEHENDER Datensatz derselben Sicht sie bereits nennt.
        Ohne diese Ausnahme waere die Ausblendung ein stiller Datenverlust:
        eine Auswahlliste ohne den aktuell gewaehlten Eintrag faellt beim
        naechsten Speichern auf "keiner" zurueck, und die Zuordnung ist weg,
        ohne dass jemand sie angefasst haette. Die Betroffenen werden im
        Befund unter 'behalten_referenziert' benannt, damit die Sicht sie
        kennzeichnen kann.
        """
        return self._filtern(zeilen, id_feld=id_feld,
                             offene_behalten=False, inaktive_zeigen=False,
                             ausnahmen=ausnahmen)

    def fuer_grundmenge(self, zeilen: Iterable[Any], *,
                        id_feld: str = "id",
                        inaktive_zeigen: bool = False) -> Sichtbarkeitsbefund:
        """
        Klasse (2) GRUNDMENGEN-TABELLE: entfernt inaktive Personen, BEHAELT
        aber die mit offenen Faellen (sie werden im Befund unter
        'behalten_mit_arbeit' benannt, damit die Sicht sie markieren kann).

        inaktive_zeigen=True schaltet die Ausblendung ganz ab (Umschalter
        "Inaktive einblenden"); dann ist 'ausgeblendet' 0 und 'gezeigt' True.
        """
        return self._filtern(zeilen, id_feld=id_feld,
                             offene_behalten=True,
                             inaktive_zeigen=inaktive_zeigen)

    # ------------------------------------------------------------------ intern
    def _filtern(self, zeilen: Iterable[Any], *, id_feld: str,
                 offene_behalten: bool,
                 inaktive_zeigen: bool,
                 ausnahmen: Optional[Iterable[int]] = None
                 ) -> Sichtbarkeitsbefund:
        """
        Gemeinsamer Filterkern beider Klassen. Er entscheidet je Zeile und
        fuehrt dabei Buch — die Rechenschaft entsteht HIER und nicht als
        nachtraegliche Schaetzung in der Sicht.
        """
        alle: List[Any] = list(zeilen)

        # (a) Ausblendung ausdruecklich abgeschaltet -> unveraendert durch.
        if inaktive_zeigen:
            return Sichtbarkeitsbefund(zeilen=alle, ausgeblendet=0,
                                       inaktive_gezeigt=True,
                                       hinweis=None)

        inaktive = self.inaktive()
        # (b) Es gibt keine inaktiven Personen (oder kein M020) -> nichts zu tun.
        if not inaktive:
            return Sichtbarkeitsbefund(zeilen=alle, ausgeblendet=0,
                                       inaktive_gezeigt=False, hinweis=None)

        # (c) Bei Grundmengen braucht die Ausnahme die Fallzahlen. Sind sie
        #     nicht feststellbar, wird NICHTS ausgeblendet (konservativ) und
        #     der Grund benannt.
        hinweis: Optional[str] = None
        if offene_behalten:
            self.offene_faelle()
            hinweis = self._offene_hinweis
            if hinweis is not None:
                return Sichtbarkeitsbefund(zeilen=alle, ausgeblendet=0,
                                           inaktive_gezeigt=False,
                                           hinweis=hinweis)

        geschuetzt = {int(a) for a in (ausnahmen or ())}

        behalten: List[str] = []
        referenziert: List[str] = []
        entfernt: List[str] = []
        raus: List[Any] = []
        for z in alle:
            pid = self._id_von(z, id_feld)
            info = inaktive.get(pid) if pid is not None else None
            if info is None:
                raus.append(z)                      # aktiv (oder keine Person)
                continue
            if pid in geschuetzt:
                referenziert.append(info["system_username"])
                raus.append(z)                      # inaktiv, aber referenziert
                continue
            if offene_behalten and self.offene_faelle_von(pid) > 0:
                behalten.append(info["system_username"])
                raus.append(z)                      # inaktiv, aber mit Arbeit
                continue
            entfernt.append(info["system_username"])

        return Sichtbarkeitsbefund(
            zeilen=raus,
            ausgeblendet=len(entfernt),
            ausgeblendete_kennungen=tuple(sorted(entfernt)),
            behalten_mit_arbeit=tuple(sorted(behalten)),
            behalten_referenziert=tuple(sorted(referenziert)),
            inaktive_gezeigt=False,
            hinweis=None,
        )

    @staticmethod
    def _id_von(zeile: Any, id_feld: str) -> Optional[int]:
        """
        Liest die person-id aus einer Zeile. Die aufrufenden Sichten fuehren
        SEHR unterschiedliche Zeilenformen (dict, sqlite3.Row, frozen
        dataclass, Tupel), und dieses Modul soll sie nicht alle kennen
        muessen. Deshalb: dict-Zugriff, dann Attribut, dann Index.

        Laesst sich keine Kennung lesen, gibt es None zurueck — die Zeile
        wird dann BEHALTEN (nie still entfernt, was nicht zugeordnet werden
        konnte).
        """
        wert: Any = None
        try:
            if isinstance(zeile, dict):
                wert = zeile.get(id_feld)
            elif hasattr(zeile, id_feld):
                wert = getattr(zeile, id_feld)
            elif isinstance(zeile, (tuple, list)) and zeile:
                wert = zeile[0]
            elif hasattr(zeile, "keys"):            # sqlite3.Row
                wert = zeile[id_feld] if id_feld in zeile.keys() else None
        except (KeyError, IndexError, TypeError):
            return None
        if wert is None:
            return None
        try:
            return int(wert)
        except (TypeError, ValueError):
            return None
