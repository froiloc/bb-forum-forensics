# =============================================================================
# management/migration_fleet/rueckweg.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Rueckweg — die Wiederherstellung einer Beweis-DB aus der Pflicht-Sicherung,
# NACHDEM eine Migration gescheitert ist.
#
#   Eine Klasse, eine Datei (Projektregel 10). Das Ergebnis traegt
#   management/migration_fleet/rueckweg_befund.py.
#
# ------------------------------------------------------------------------
# DER BEFUND, DER ZU DIESER DATEI GEFUEHRT HAT (Vorgang 69ede1c7)
# ------------------------------------------------------------------------
# Bis Build 720 stand der Rueckweg als vierzeilige Hilfsfunktion
# FleetExecutor._restore() im Ausfuehrer. Ihr eigener Docstring nannte die
# Voraussetzung ausdruecklich — "Voraussetzung: keine offene Verbindung auf
# path" — und der Code PRUEFTE sie nicht. Er hat die Sicherung bedingungslos
# ueber die Originaldatei kopiert.
#
# WARUM DAS SCHWERER WIEGT ALS EINE GEWOEHNLICHE FEHLENDE PRUEFUNG: Es ist der
# Pfad, der im FEHLERFALL laeuft. Er greift also genau dann, wenn ohnehin schon
# etwas schiefgegangen ist — und wenn die Wahrscheinlichkeit, dass noch eine
# Verbindung offen steht, HOEHER ist als im Normalbetrieb. Trifft die Kopie
# eine geoeffnete Datei, ist das Ergebnis weder der alte noch der neue Stand.
#
# Der Wartungsvorbehalt in migration_fleet_admin.py (Build 612) hat den Mangel
# vorlaeufig UMSTELLT — er prueft die Ruhe VOR dem Lauf. Das ist richtig und
# bleibt, aber es ist kein Ersatz: Zwischen der Vorpruefung und dem Rueckweg
# liegt die gesamte Migration. Wer in dieser Zeitspanne eine Verbindung
# aufmacht, kommt an der Vorpruefung vorbei. Die Pruefung gehoert deshalb
# UNMITTELBAR vor die Kopie.
#
# ------------------------------------------------------------------------
# DIE VIER TORE, UND WARUM SIE IN DIESER REIHENFOLGE STEHEN
# ------------------------------------------------------------------------
# Die Reihenfolge ist nicht beliebig: Sie ist so gewaehlt, dass JEDES Nein
# faellt, BEVOR die Zieldatei angefasst wird. Ein Nein nach dem ersten
# entfernten Seitenfile waere schon ein halb ausgefuehrter Rueckweg.
#
#   TOR 1  Ist die Sicherung ueberhaupt da?
#          Ohne sie gibt es nichts zurueckzuspielen. Frueher haette
#          shutil.copyfile hier eine Ausnahme geworfen — mitten im
#          except-Block des Ausfuehrers, was den ganzen Flottenlauf gerissen
#          haette (Isolationszusage des Ausfuehrers, Kopf executor.py).
#
#   TOR 2  Ist die Sicherung DIE Sicherung? (nur wenn ein SHA512 vorliegt)
#          BackupTool.create_backup liefert den SHA512 der frisch erzeugten
#          Kopie mit. Ihn hier nachzurechnen kostet einen Lesedurchgang und
#          beantwortet die Frage, die man sonst erst nach dem Zurueckspielen
#          stellt: Ist das, was ich gleich ueber das Beweismittel kopiere,
#          unveraendert das, was ich angelegt habe? Eine beschaedigte
#          Sicherung ueber ein beschaedigtes Original zu kopieren, macht aus
#          zwei kaputten Staenden einen.
#
#   TOR 3  Ist die Zieldatei RUHIG? — der Kern dieses Vorgangs.
#          Gemessen wird mit maintenance.cli_support.exklusiv_beurteilen():
#          Versuch, einen EXCLUSIVE-Lock zu erwerben. Gelingt er, haelt
#          niemand die Datei.
#
#          BEWUSST exklusiv_beurteilen() UND NICHT exklusiv_pruefen():
#          Der Vorgang nennt die zweiwertige Form '(ok, grund)'. Die
#          dreiwertige Form ist seit Build 648 da und unterscheidet 'belegt'
#          von 'nicht messbar' — und das sind fuer den Menschen, der danach
#          aufraeumt, ZWEI VERSCHIEDENE AUFGABEN: 'belegt' heisst "beende den
#          Prozess, der sie haelt", 'nicht messbar' heisst "du hast kein
#          Schreibrecht, wechsle das Konto". Beides als "nicht frei" zu
#          melden waere nicht falsch, aber es waere weniger, als wir wissen.
#          Verweigert wird in BEIDEN Faellen — 'nicht messbar' ist keine Ruhe
#          (maintenance/exklusiv_befund.py, ist_ruhig).
#
#   TOR 4  Ist die Kopie angekommen? (nur wenn ein SHA512 vorliegt)
#          NACH dem Kopieren wird die Zieldatei nachgerechnet. Erst wenn ihr
#          SHA512 dem der Sicherung entspricht, gilt der Rueckweg als
#          ausgefuehrt. Ohne dieses Tor waere "kopiert" eine Behauptung ueber
#          den Ausgang eines Systemaufrufs und kein Nachweis ueber den Inhalt
#          einer Datei.
#
# WAS DER RUECKWEG NIEMALS TUT: in die Sicherung schreiben, sie verschieben
# oder sie loeschen. Bei einem Nein ist sie das Einzige, was den alten Stand
# noch traegt. Sie bleibt unter ihrem Namen liegen (so verlangt es der
# Vorgang ausdruecklich).
#
# ------------------------------------------------------------------------
# WAS BEWUSST NICHT GEAENDERT WURDE — und warum das eine Entscheidung ist
# ------------------------------------------------------------------------
# Die Kopie laeuft weiterhin mit shutil.copyfile DIREKT auf die Zieldatei und
# nicht ueber eine Nebendatei mit anschliessendem os.replace(). Ein
# os.replace() waere unteilbar und wuerde den Fall 'kopierfehler' beseitigen —
# es ERSETZT aber die Datei und damit ihren Modus und ihren Eigentuemer durch
# die der frisch angelegten Nebendatei (umask). Auf einer versiegelten oder
# eng berechtigten Beweis-DB waere das eine stille Ausweitung von Rechten.
# copyfile schreibt dagegen IN die vorhandene Datei und laesst Modus und
# Eigentuemer unangetastet.
#
# Der Restrisiko-Fall bleibt damit bestehen: ein Ein-/Ausgabefehler MITTEN in
# der Kopie (Platte voll, Netzlaufwerk weg). Er wird nicht verschwiegen,
# sondern als 'kopierfehler' benannt und im Klartext als UNBESTIMMTER Zustand
# ausgewiesen. Ein eigener Vorgang haelt die Abwaegung fest
# (Grundregel 1: kein Befund wird still uebersprungen).
#
# Beleg: Vorgang 69ede1c7-3fe1-47eb-9d9a-f0cf6468f7dc; Vermerk_Wartungs-
#        vorbehalt_Analyse_K1_K8_v1_0.md §3 (Befund 3); maintenance/
#        cli_support.py (exklusiv_beurteilen, Build 648); management/
#        migration_fleet/harness/backup.py (BackupResult.sha512).
# Version: v0.8.723 · Build: 723 · 2026-08-14
# =============================================================================

from __future__ import annotations

import logging
import os
import shutil
from typing import Callable, Optional

from maintenance.cli_support import exklusiv_beurteilen
from maintenance.exklusiv_befund import BELEGT, ExklusivBefund
from management.migration_fleet.harness.hashing import sha512_file
from management.migration_fleet.rueckweg_befund import (
    KOPIERFEHLER, RueckwegBefund, VERWEIGERT, ZURUECKGESPIELT,
)

logger = logging.getLogger(__name__)

#: Seitendateien des WAL-Journalmodus. Sie gehoeren zum ALTEN Inhalt und
#: muessen weg, bevor die Sicherung zurueckgespielt wird — sonst liest SQLite
#: nach dem Zurueckspielen ein Journal, das nicht mehr zur Datei passt.
_SEITENDATEIEN = ("-wal", "-shm")


class Rueckweg:
    """
    Spielt eine Pflicht-Sicherung zurueck — oder sagt begruendet Nein.

    Die Sperrprobe ist INJIZIERBAR (Parameter 'pruefer'). Das ist kein
    Testzucker: Ohne Injektion liesse sich der Fall 'belegt' nur mit einem
    zweiten Prozess und echten Dateisperren pruefen, also nur unzuverlaessig
    und plattformabhaengig. Die Vorgabe ist die echte Messung.
    """

    def __init__(self, *,
                 pruefer: Optional[Callable[[str], ExklusivBefund]] = None,
                 timeout_s: float = 2.0) -> None:
        self._pruefer = pruefer
        self._timeout_s = timeout_s

    # ------------------------------------------------------------- intern
    def _messen(self, pfad: str) -> ExklusivBefund:
        """Sperrprobe — injizierter Pruefer oder die echte Messung."""
        if self._pruefer is not None:
            return self._pruefer(pfad)
        return exklusiv_beurteilen(pfad, timeout_s=self._timeout_s)

    @staticmethod
    def _seitendateien_entfernen(pfad: str):
        """
        Entfernt -wal/-shm. Rueckgabe: (entfernt, fehler).

        Der Fehler wird ZURUECKGEGEBEN und nicht geworfen, weil der Aufrufer
        beides zusammen braucht: Scheitert das Entfernen an der ERSTEN
        Seitendatei, ist die Zieldatei noch unberuehrt; scheitert es an der
        zweiten, ist sie es nicht mehr. Eine geworfene Ausnahme haette diese
        Zahl unterwegs verloren — und mit ihr die Unterscheidung zwischen
        einem sauberen Nein und einem angefangenen Rueckweg.
        """
        entfernt = 0
        for suffix in _SEITENDATEIEN:
            neben = pfad + suffix
            if os.path.exists(neben):
                try:
                    os.remove(neben)
                except OSError as exc:
                    return entfernt, exc
                entfernt += 1
        return entfernt, None

    @staticmethod
    def _klartext_verweigert(pfad: str, sicherung: str, grund: str,
                             zusatz: str) -> str:
        """
        Die Ansage bei einem Nein. Sie nennt Datei, Sicherung, Messung und die
        Handgriffe — in dieser Reihenfolge, weil man in dieser Reihenfolge
        handelt.
        """
        return "\n".join([
            "RUECKWEG NICHT AUSGEFUEHRT — es wurde NICHTS kopiert.",
            "  Zieldatei : %s" % pfad,
            "  Sicherung : %s" % sicherung,
            "              (unveraendert; sie bleibt unter ihrem Namen liegen)",
            "  Messung   : %s" % grund,
            "",
            "  Die Zieldatei ist NICHT angefasst worden. Sie steht damit auf",
            "  dem Stand, den die gescheiterte Migration hinterlassen hat —",
            "  das ist NICHT zwingend der Stand vor dem Lauf.",
            "",
            "  VON HAND ZU TUN:",
            "  1. %s" % zusatz,
            "  2. Ruhe herstellen und nachweisen, z. B. ueber das",
            "     Wartungsfenster:",
            "       python tools/maintenance.py enter --reason \"Rueckweg "
            "Migration\" --data-dir ./data",
            "     'status' zeigt, wer die Datei noch haelt.",
            "  3. Erst bei nachgewiesener Ruhe die Sicherung von Hand",
            "     zurueckspielen (Seitendateien -wal/-shm der Zieldatei",
            "     vorher entfernen).",
            "  4. Das Wartungsfenster wieder aufheben:",
            "       python tools/maintenance.py exit --data-dir ./data",
            "  5. Den Vorgang im Laufbuch (migration.db, migration_runs)",
            "     gegen den hier protokollierten Lauf halten.",
        ])

    @staticmethod
    def _klartext_kopierfehler(pfad: str, sicherung: str, grund: str) -> str:
        """
        Die Ansage, wenn die Kopie BEGONNEN und gescheitert ist. Sie muss
        deutlich schaerfer ausfallen als die Verweigerung: Hier ist der
        Zustand der Zieldatei unbestimmt, und niemand darf sie in diesem
        Zustand fuer einen Beweismittelstand halten.
        """
        return "\n".join([
            "RUECKWEG ABGEBROCHEN — die Zieldatei ist in einem UNBESTIMMTEN "
            "Zustand.",
            "  Zieldatei : %s" % pfad,
            "  Sicherung : %s" % sicherung,
            "              (unveraendert; sie traegt den alten Stand)",
            "  Fehler    : %s" % grund,
            "",
            "  ACHTUNG: Die Kopie wurde begonnen und nicht nachweislich",
            "  abgeschlossen. Der Inhalt der Zieldatei ist weder der alte",
            "  noch der neue Stand. SIE DARF NICHT WEITERVERWENDET WERDEN,",
            "  bevor sie gegen die Sicherung geprueft wurde.",
            "",
            "  VON HAND ZU TUN:",
            "  1. Ursache beheben (Plattenplatz, Netzlaufwerk, Berechtigung).",
            "  2. Die Zieldatei NICHT oeffnen, sondern gegen die Sicherung",
            "     pruefen (SHA512).",
            "  3. Die Sicherung bei nachgewiesener Ruhe von Hand",
            "     zurueckspielen.",
            "  4. Den Abbruch im Laufbuch (migration.db, migration_runs)",
            "     gegen den hier protokollierten Lauf halten.",
        ])

    # --------------------------------------------------------- oeffentlich
    def zurueckspielen(self, pfad: str, sicherung: str, *,
                       sicherung_sha512: Optional[str] = None
                       ) -> RueckwegBefund:
        """
        Spielt 'sicherung' nach 'pfad' zurueck — oder verweigert begruendet.

        Wirft KEINE Ausnahme. Der Aufrufer ist der except-Block des
        Ausfuehrers; eine Ausnahme aus einer Ausnahmebehandlung heraus wuerde
        die Isolationszusage der Flotte brechen (ein Fehler bei Instanz A darf
        Instanz B nicht beruehren, Kopf executor.py).

        sicherung_sha512 — der bei der Anlage gemessene SHA512 der Sicherung.
            Ist er gesetzt, wird die Sicherung VOR und die Zieldatei NACH dem
            Kopieren nachgerechnet (Tore 2 und 4). Ist er None, entfallen
            beide Tore; der Rueckweg laeuft dann so belegarm wie vor diesem
            Build, und genau das steht dann auch im Grund.
        """
        # --- TOR 1: Ist die Sicherung ueberhaupt da? ----------------------
        if not os.path.exists(sicherung):
            grund = "Sicherung nicht vorhanden: %s" % sicherung
            return RueckwegBefund(
                pfad=pfad, sicherung=sicherung, zustand=VERWEIGERT,
                grund=grund,
                klartext=self._klartext_verweigert(
                    pfad, sicherung, grund,
                    "Die Sicherung suchen — ohne sie gibt es nichts "
                    "zurueckzuspielen."))

        # --- TOR 2: Ist die Sicherung DIE Sicherung? ----------------------
        if sicherung_sha512:
            try:
                ist = sha512_file(sicherung)
            except OSError as exc:
                grund = "Sicherung nicht lesbar: %s" % exc
                return RueckwegBefund(
                    pfad=pfad, sicherung=sicherung, zustand=VERWEIGERT,
                    grund=grund,
                    klartext=self._klartext_verweigert(
                        pfad, sicherung, grund,
                        "Den Zugriff auf die Sicherung herstellen."))
            if ist != sicherung_sha512:
                grund = ("Sicherung veraendert: SHA512 erwartet %s..., "
                         "gemessen %s..."
                         % (sicherung_sha512[:16], ist[:16]))
                return RueckwegBefund(
                    pfad=pfad, sicherung=sicherung, zustand=VERWEIGERT,
                    grund=grund,
                    klartext=self._klartext_verweigert(
                        pfad, sicherung, grund,
                        "Die Sicherung ist nicht mehr die, die angelegt "
                        "wurde. Herkunft klaeren, bevor irgendetwas "
                        "zurueckgespielt wird."))

        # --- TOR 3: Ist die Zieldatei ruhig? ------------------------------
        befund = self._messen(pfad)
        if not befund.ist_ruhig:
            zusatz = (
                "Den Prozess beenden, der die Datei geoeffnet haelt "
                "(Webserver, Verwaltungsserver, ein offenes sqlite3)."
                if befund.zustand == BELEGT else
                "Die Ruhe war NICHT MESSBAR — es ist also unbekannt, ob "
                "jemand die Datei haelt. Die Ursache steht oben in der "
                "Messung; meist fehlt dem ausfuehrenden Konto das "
                "Schreibrecht an Datei oder Verzeichnis.")
            grund = "%s: %s" % (befund.marke.strip(), befund.grund)
            logger.warning("Rueckweg verweigert fuer %s: %s", pfad, grund)
            return RueckwegBefund(
                pfad=pfad, sicherung=sicherung, zustand=VERWEIGERT,
                grund=grund,
                klartext=self._klartext_verweigert(
                    pfad, sicherung, grund, zusatz))

        # --- Ab hier wird die Zieldatei angefasst. ------------------------
        # 'beruehrt' entscheidet ueber die Einstufung eines Fehlschlags:
        # solange nichts angefasst ist, ist ein Fehlschlag eine VERWEIGERUNG
        # (Zieldatei nachweislich unberuehrt); danach ist er ein
        # KOPIERFEHLER (Zustand unbestimmt).
        entfernt, entfernfehler = self._seitendateien_entfernen(pfad)
        beruehrt = entfernt > 0
        if entfernfehler is not None:
            grund = "Seitendatei nicht entfernbar: %s" % entfernfehler
            logger.error("Rueckweg abgebrochen fuer %s: %s", pfad, grund)
            if not beruehrt:
                return RueckwegBefund(
                    pfad=pfad, sicherung=sicherung, zustand=VERWEIGERT,
                    grund=grund,
                    klartext=self._klartext_verweigert(
                        pfad, sicherung, grund,
                        "Die Seitendatei (-wal/-shm) laesst sich nicht "
                        "entfernen; die Zieldatei ist noch unberuehrt. "
                        "Berechtigungen und offene Prozesse pruefen."))
            return RueckwegBefund(
                pfad=pfad, sicherung=sicherung, zustand=KOPIERFEHLER,
                grund=grund,
                klartext=self._klartext_kopierfehler(pfad, sicherung, grund))

        try:
            shutil.copyfile(sicherung, pfad)
        except OSError as exc:
            # HIER WIRD BEWUSST NICHT ZWISCHEN 'unberuehrt' UND 'unbestimmt'
            # UNTERSCHIEDEN, obwohl 'beruehrt' an dieser Stelle noch False
            # sein kann. shutil.copyfile oeffnet das Ziel mit 'wb' und
            # LEERT es damit, bevor das erste Byte geschrieben ist. Ein
            # Fehler kann davor liegen (Quelle nicht lesbar — Ziel wirklich
            # unberuehrt) oder danach (Ziel abgeschnitten). Von aussen ist
            # das nicht sicher zu unterscheiden, und eine Unberuehrtheit,
            # die wir nicht belegen koennen, duerfen wir nicht behaupten
            # (Grundregel: keine Behauptung ohne Beleg). Also: unbestimmt.
            grund = "Kopie gescheitert: %s" % exc
            logger.error("Rueckweg abgebrochen fuer %s: %s", pfad, grund)
            return RueckwegBefund(
                pfad=pfad, sicherung=sicherung, zustand=KOPIERFEHLER,
                grund=grund,
                klartext=self._klartext_kopierfehler(pfad, sicherung, grund))

        # --- TOR 4: Ist die Kopie angekommen? -----------------------------
        if sicherung_sha512:
            try:
                nach = sha512_file(pfad)
            except OSError as exc:
                grund = "Zieldatei nach der Kopie nicht lesbar: %s" % exc
                logger.error("Rueckweg unbelegt fuer %s: %s", pfad, grund)
                return RueckwegBefund(
                    pfad=pfad, sicherung=sicherung, zustand=KOPIERFEHLER,
                    grund=grund,
                    klartext=self._klartext_kopierfehler(
                        pfad, sicherung, grund))
            if nach != sicherung_sha512:
                grund = ("Zieldatei stimmt nach der Kopie nicht mit der "
                         "Sicherung ueberein (SHA512 %s... gegen %s...)"
                         % (nach[:16], sicherung_sha512[:16]))
                logger.error("Rueckweg unbelegt fuer %s: %s", pfad, grund)
                return RueckwegBefund(
                    pfad=pfad, sicherung=sicherung, zustand=KOPIERFEHLER,
                    grund=grund,
                    klartext=self._klartext_kopierfehler(
                        pfad, sicherung, grund))
            grund = ("zurueckgespielt und nachgerechnet (SHA512 %s...)"
                     % sicherung_sha512[:16])
        else:
            grund = ("zurueckgespielt; OHNE Nachrechnung — es lag kein "
                     "SHA512 der Sicherung vor")

        return RueckwegBefund(
            pfad=pfad, sicherung=sicherung, zustand=ZURUECKGESPIELT,
            grund=grund,
            klartext="RUECKWEG AUSGEFUEHRT.\n"
                     "  Zieldatei : %s\n"
                     "  Sicherung : %s\n"
                     "  Befund    : %s" % (pfad, sicherung, grund))
