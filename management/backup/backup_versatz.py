# =============================================================================
# management/backup/backup_versatz.py
# IT-Forensisches Ermittlungswerkzeug - Datensicherung
# =============================================================================
# Zweck:
#   DEN VERSATZ IM SICHERUNGSSATZ AUSRECHNEN - aus den Manifesten, die
#   'backup_admin run' seit Build 617 schreibt.
#
# DER ANLASS (Vorgang 77757536-381e-491d-9c94-e1dda84fd02e):
#   Die Datenbanken werden NACHEINANDER gesichert. Jede Kopie ist fuer sich
#   transaktional stimmig; der SATZ als Ganzes ist es nicht. Zwischen zwei
#   Kopien arbeitet der Ermittlungsbetrieb weiter. Wer aus einem solchen Satz
#   den GESAMTEN Bestand wiederherstellt, bekommt einen Zustand, den es nie
#   gegeben hat.
#
#   mc hat sich am 2026-07-31 gegen ein Wartungsfenster und fuer die
#   KENNZEICHNUNG entschieden - eine taegliche Sicherung soll nebenher laufen
#   koennen. Build 617 hat die Kennzeichnung eingebaut und den Versatz zum
#   ersten Mal ABLESBAR gemacht ('begonnen_ts'/'beendet_ts' je Datenbank,
#   'satz_von'/'satz_bis' je Lauf).
#
#   ABLESBAR IST NICHT GEMESSEN. Die Entscheidung gegen das Wartungsfenster
#   steht bis heute auf einer Annahme: dass der Versatz klein ist. Ob er es
#   ist, entscheidet eine Zahl, die noch niemand gebildet hat. Dieses Bauteil
#   bildet sie.
#
# WAS ES BEANTWORTET - die drei Fragen aus dem Vorgang, woertlich:
#   (1) Wie gross ist die Spanne typischerweise, und wie gross im
#       schlechtesten beobachteten Fall?
#   (2) Faellt die Spanne fast vollstaendig auf EINE Datenbank? (Verdacht:
#       default.db mit rund 4,8 GB.) Dann waere zu ueberlegen, gerade diese -
#       die keine Ermittlungsergebnisse enthaelt - aus dem taeglichen Satz
#       herauszunehmen und gesondert zu sichern.
#   (3) Kam waehrend eines Laufs eine Fall-Datenbank hinzu? Das ist der
#       unmittelbare Beleg dafuer, dass der Betrieb IN den Satz hinein
#       gearbeitet hat - keine Wahrscheinlichkeit mehr, sondern ein Vorfall.
#
# WAS ES AUSDRUECKLICH NICHT TUT - UND WARUM:
#   ES BEURTEILT DIE SPANNE NICHT VON SELBST. Der Vorgang nennt zwei Minuten
#   als 'sehr klein' und zwei Stunden als 'praktisch sicher zu lang', aber
#   keine Grenze dazwischen ist entschieden. Eine hier fest verdrahtete
#   Schwelle waere eine erfundene Entscheidung im Gewand einer Messung. Wer
#   eine Grenze pruefen will, nennt sie (--schwelle-minuten); wer keine
#   nennt, bekommt die Zahlen und die Beurteilung bleibt beim Menschen. Dass
#   NICHT beurteilt wurde, steht im Bericht (Grundregel 1).
#
# REIN LESEND. Es oeffnet keine Datenbank, es fasst keine Sicherungsdatei an,
#   es schreibt nichts. Gelesen werden ausschliesslich die Manifest-Dateien.
#   Damit ist es zu jeder Betriebszeit unbedenklich - anders als der Lauf,
#   den es auswertet.
#
# KEIN MANIFEST WIRD STILL UEBERGANGEN (Grundregel 1). Was nicht ausgewertet
#   werden konnte - unlesbar, kein JSON, aus einem Stand vor Build 617 -
#   steht namentlich und mit Grund im Befund. Ein uebersprungenes Manifest
#   ist sonst von einem nicht vorhandenen nicht zu unterscheiden, und genau
#   daran wuerde die Grundgesamtheit unbemerkt schrumpfen.
#
# ZUR DATEIAUFTEILUNG (Grundregel 10, 'jede Klasse in eine eigene Datei'):
#   Die drei Befund-Datenklassen stehen hier bei der Auswertung und nicht in
#   drei weiteren Dateien. Das ist die Aufteilung, die backup_pruefer.py seit
#   Build 626 vormacht (Dateibefund/Labelbefund/Bestandsbefund neben
#   SicherungsPruefer): reine Ergebnistraeger ohne eigenes Verhalten gehoeren
#   zu dem Bauteil, das sie erzeugt. Eine abweichende Aufteilung im selben
#   Verzeichnis waere die groessere Unordnung.
#
# Version: v0.8.717 - Build: 717 - 2026-08-13
# =============================================================================

from __future__ import annotations

import calendar
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

#: Rueckgabewerte. Sie stehen HIER und nicht im Werkzeug, damit Bericht,
#: Befund und Rueckgabewert dieselbe Quelle haben - dasselbe Muster wie in
#: backup_pruefer.py.
#:
#: DIE ORDNUNG IST NACH SCHWERE, nicht nach Zufall:
#:   3  das Verzeichnis ist nicht lesbar - es ist gar nichts festgestellt
#:   2  es gibt KEINE auswertbare Grundlage (kein Manifest aus Build 617+)
#:   1  ausgewertet, aber mit Befund (zu wenige Laeufe, Nachzuegler,
#:      Schwelle ueberschritten)
#:   0  ausgewertet, nichts zu beanstanden
#: WARUM 2 SCHWERER WIEGT ALS 1: Ein Befund ist Wissen. 'Keine Grundlage'
#: ist die Abwesenheit von Wissen - und die faellt in einem Verfahren
#: schwerer ins Gewicht als eine unangenehme Zahl.
RC_OK = 0
RC_BEFUND = 1
RC_OHNE_GRUNDLAGE = 2
RC_UNLESBAR = 3

#: Das Zeitstempelformat der Manifeste (UTC). Es steht an einer Stelle,
#: damit Auswertung und Erzeugung nicht auseinanderlaufen; erzeugt wird es in
#: backup_executor.py mit time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()).
TS_FORMAT = "%Y%m%dT%H%M%SZ"

#: Wie viele auswertbare Laeufe der Vorgang als Grundlage verlangt. KEINE
#: technische Grenze, sondern die Vorgabe aus 77757536 ('FUENF BIS ZEHN
#: produktive Laeufe abwarten'). Sie ist ueberschreibbar, aber sie ist die
#: Vorgabe - wer mit dreien auswertet, soll das ausdruecklich tun.
MINDEST_LAEUFE = 5

#: Zeilenbreite des Textberichts - wie in backup_pruefer.py.
_BREITE = 78

#: Der Namensanfang der auszuwertenden Dateien:
#: 'manifest_<zeitstempel>_<rechner>.json' (backup_executor._write_manifest).
_MANIFEST_PRAEFIX = "manifest_"
_MANIFEST_ENDUNG = ".json"


def ts_zu_epoche(ts: str) -> Optional[int]:
    """
    Einen Manifest-Zeitstempel in Sekunden seit der Epoche umrechnen.

    DIE ZEITSTEMPEL SIND UTC ('Z' am Ende) - deshalb calendar.timegm und
    NICHT time.mktime. time.mktime deutet die Angabe als ORTSZEIT des
    auswertenden Rechners; auf der Ermittlungs-VM (Europe/Berlin) waeren alle
    Zeitpunkte um ein bis zwei Stunden verschoben. Auf DIFFERENZEN innerhalb
    eines Laufs faellt das nicht auf - sie waeren trotzdem richtig -, wohl
    aber auf der Uhrzeitfrage des Vorgangs ('lag der Lauf in der Arbeitszeit
    der Ermittelnden'). Genau die waere dann falsch beantwortet.

    Rueckgabe None statt einer Ausnahme: ein einzelner unbrauchbarer
    Zeitstempel darf die Auswertung der uebrigen nicht anhalten. Der Aufrufer
    macht daraus einen benannten Grund.
    """
    if not ts:
        return None
    try:
        return calendar.timegm(time.strptime(ts, TS_FORMAT))
    except (ValueError, TypeError):
        return None


def epoche_zu_uhrzeit(epoche: int, versatz_minuten: int = 0) -> str:
    """
    Eine Epochenzeit als 'JJJJ-MM-TT HH:MM' ausgeben, wahlweise um einen
    festen Versatz verschoben.

    WARUM EIN FESTER VERSATZ IN MINUTEN UND KEINE ZEITZONE: Die Auswertung
    laeuft auf einer Windows-VM. Ob dort eine Zeitzonendatenbank fuer
    zoneinfo bereitliegt, ist nicht zugesichert; ein fehlendes tzdata wuerde
    das Werkzeug an einer Nebensache scheitern lassen. Der Versatz wird
    deshalb genannt, nicht erraten - und er wird in der Ausgabe mitgenannt,
    damit niemand eine Ortszeit fuer UTC haelt oder umgekehrt.
    """
    return time.strftime("%Y-%m-%d %H:%M",
                         time.gmtime(epoche + versatz_minuten * 60))


def _dauer(sekunden: Optional[float]) -> str:
    """Eine Dauer lesbar machen. Unter einer Minute bleibt es bei Sekunden."""
    if sekunden is None:
        return "-"
    s = int(round(sekunden))
    if s < 60:
        return "%d s" % s
    if s < 3600:
        return "%d:%02d min" % (s // 60, s % 60)
    return "%d:%02d h" % (s // 3600, (s % 3600) // 60)


def _umbruch(text: str, einzug: str = "      ") -> List[str]:
    """
    Fliesstext auf _BREITE umbrechen. Von Hand und nicht ueber textwrap:
    der Einzug soll frei waehlbar sein, und ein ueberlanges Wort - ein
    Dateiname, ein Pfad - wird NICHT zerschnitten. Dieselbe Regel wie in
    backup_pruefer.py und management/help/cli_text.py.
    """
    zeilen: List[str] = []
    aktuell = einzug
    leer = True
    for wort in (text or "").split():
        if not leer and len(aktuell) + 1 + len(wort) > _BREITE:
            zeilen.append(aktuell)
            aktuell = einzug + wort
        else:
            aktuell = (einzug + wort) if leer else (aktuell + " " + wort)
        leer = False
    if not leer:
        zeilen.append(aktuell)
    return zeilen


# =============================================================================
# Die Befunde
# =============================================================================

@dataclass(frozen=True)
class Kopiebefund:
    """
    Was ueber die Sicherung EINER Datenbank innerhalb eines Laufs
    festzustellen war.

    'dauer_s' ist None, wenn einer der beiden Zeitstempel fehlt oder
    unbrauchbar ist. Das ist NICHT dasselbe wie 0 - eine Kopie ohne messbare
    Dauer geht in keinen Mittelwert ein, waehrend eine mit 0 Sekunden es tut.
    """
    label: str
    begonnen_ts: str
    beendet_ts: str
    dauer_s: Optional[float]
    gelungen: bool
    grund: str = ""


@dataclass(frozen=True)
class Laufbefund:
    """Ein einzelner Sicherungslauf, aus seinem Manifest gelesen."""
    manifest: str
    run_ts: str
    host: str
    satz_von: str
    satz_bis: str
    #: Die Spanne des Satzes in Sekunden. None heisst: nicht bestimmbar.
    spanne_s: Optional[float]
    #: Beginn des Satzes als Epochenzeit - Grundlage der Uhrzeitfrage.
    beginn_epoche: Optional[int]
    kopien: Tuple[Kopiebefund, ...] = ()
    nachzuegler: Tuple[str, ...] = ()
    lauf_ok: bool = True
    #: Abweichung zwischen den Feldern 'satz_von'/'satz_bis' des Manifests
    #: und der Nachrechnung aus den Einzelstempeln. Leer ist der Regelfall.
    #:
    #: WARUM NACHGERECHNET WIRD, obwohl dasselbe Programm beides schreibt:
    #: Ein Manifest ist eine Datei im Sicherungsverzeichnis und kann von Hand
    #: veraendert worden sein; ausserdem koennen kuenftige Staende die
    #: Bildung der Felder aendern. Faellt die Nachrechnung auseinander, ist
    #: die Zahl nicht mehr belegt - und das gehoert gesagt statt geglaettet.
    stimmigkeit: str = ""

    @property
    def laengste_kopie(self) -> Optional[Kopiebefund]:
        """Die Kopie mit der laengsten messbaren Dauer."""
        messbar = [k for k in self.kopien if k.dauer_s is not None]
        if not messbar:
            return None
        return max(messbar, key=lambda k: k.dauer_s)

    @property
    def anteil_laengste(self) -> Optional[float]:
        """
        Welcher Anteil der Gesamtspanne auf die laengste Einzelkopie faellt.

        DAS IST DIE ZAHL ZUR ZWEITEN FRAGE DES VORGANGS. Liegt sie nahe bei
        1, dann ist der Satz nicht breit, sondern EINE Datenbank ist langsam
        - und dann hilft es, gerade diese herauszunehmen. Liegt sie bei 0,2,
        verteilt sich die Spanne, und das Herausnehmen einer einzelnen
        Datenbank braechte wenig.
        """
        laengste = self.laengste_kopie
        if laengste is None or not self.spanne_s:
            return None
        return laengste.dauer_s / self.spanne_s

    @property
    def uhrzeit_utc(self) -> Optional[str]:
        if self.beginn_epoche is None:
            return None
        return time.strftime("%H:%M", time.gmtime(self.beginn_epoche))


@dataclass(frozen=True)
class Uebersprungen:
    """
    Ein Manifest, das NICHT in die Auswertung eingeht - mit Grund.

    Es gibt diese Klasse, damit die Grundgesamtheit nachvollziehbar bleibt.
    Wer im Bericht 'sieben Laeufe ausgewertet' liest, muss auch erfahren,
    dass drei weitere Dateien dalagen und warum sie nicht zaehlen.
    """
    name: str
    grund: str


@dataclass(frozen=True)
class Versatzbefund:
    """Die Auswertung aller Manifeste eines Sicherungsverzeichnisses."""
    verzeichnis: str
    lesbar: bool
    laeufe: Tuple[Laufbefund, ...] = ()
    uebersprungen: Tuple[Uebersprungen, ...] = ()
    fehler: Tuple[str, ...] = ()
    #: Die geforderte Mindestzahl auswertbarer Laeufe (Vorgabe MINDEST_LAEUFE).
    mindest_laeufe: int = MINDEST_LAEUFE
    #: Die gepruefte Schwelle in Minuten - None heisst NICHT GEPRUEFT.
    schwelle_minuten: Optional[float] = None
    #: Versatz der Ortszeit gegen UTC in Minuten, nur fuer die Anzeige.
    ortszeit_versatz: int = 0
    #: Arbeitszeitfenster in Ortszeit als (von_minute, bis_minute) seit
    #: Mitternacht. None heisst: nicht geprueft.
    arbeitszeit: Optional[Tuple[int, int]] = None

    # ---------------------------------------------------------------- Zahlen
    @property
    def messbare(self) -> Tuple[Laufbefund, ...]:
        """Laeufe mit bestimmbarer Spanne - nur sie tragen Zahlen."""
        return tuple(l for l in self.laeufe if l.spanne_s is not None)

    @property
    def spannen(self) -> List[float]:
        return [l.spanne_s for l in self.messbare]

    @property
    def spanne_min(self) -> Optional[float]:
        return min(self.spannen) if self.spannen else None

    @property
    def spanne_median(self) -> Optional[float]:
        """
        Der Median und nicht das arithmetische Mittel. Bei fuenf bis zehn
        Werten zieht ein einzelner Ausreisser - ein Lauf, der in eine
        Netzstoerung geriet - das Mittel so weit, dass es keinen typischen
        Lauf mehr beschreibt. Gefragt ist aber genau der typische.
        """
        return statistics.median(self.spannen) if self.spannen else None

    @property
    def spanne_max(self) -> Optional[float]:
        return max(self.spannen) if self.spannen else None

    @property
    def schlechtester(self) -> Optional[Laufbefund]:
        """Der Lauf mit der groessten Spanne - der 'schlechteste Fall'."""
        if not self.messbare:
            return None
        return max(self.messbare, key=lambda l: l.spanne_s)

    @property
    def laeufe_mit_nachzueglern(self) -> Tuple[Laufbefund, ...]:
        """
        DIE DRITTE FRAGE DES VORGANGS. Jeder Eintrag hier ist ein BELEG, kein
        Verdacht: waehrend dieses Laufs ist eine Fall-Datenbank entstanden,
        die im Satz fehlt.
        """
        return tuple(l for l in self.laeufe if l.nachzuegler)

    def je_datenbank(self) -> List[Dict[str, object]]:
        """
        Je Datenbank: wie oft war sie die laengste Kopie, und wie lange
        dauerte sie im Median.

        NACH 'wie oft die laengste' SORTIERT und erst danach nach Dauer. Die
        Frage des Vorgangs lautet nicht 'welche Datenbank ist gross', sondern
        'welche bestimmt die Spanne'. Das ist dieselbe Zahl nur dann, wenn
        eine einzige dauerhaft dominiert - und ob das so ist, soll die
        Auswertung zeigen und nicht voraussetzen.
        """
        dauern: Dict[str, List[float]] = {}
        anteile: Dict[str, List[float]] = {}
        laengste_zaehler: Dict[str, int] = {}
        for lauf in self.laeufe:
            for k in lauf.kopien:
                if k.dauer_s is not None:
                    dauern.setdefault(k.label, []).append(k.dauer_s)
            laengste = lauf.laengste_kopie
            if laengste is not None:
                laengste_zaehler[laengste.label] = (
                    laengste_zaehler.get(laengste.label, 0) + 1)
                anteil = lauf.anteil_laengste
                if anteil is not None:
                    anteile.setdefault(laengste.label, []).append(anteil)
        raus: List[Dict[str, object]] = []
        for label, werte in dauern.items():
            raus.append({
                "label": label,
                "laeufe": len(werte),
                "dauer_median_s": statistics.median(werte),
                "dauer_max_s": max(werte),
                "war_laengste": laengste_zaehler.get(label, 0),
                "anteil_median": (statistics.median(anteile[label])
                                  if anteile.get(label) else None),
            })
        raus.sort(key=lambda e: (-int(e["war_laengste"]),
                                 -float(e["dauer_median_s"])))
        return raus

    @property
    def dominante_datenbank(self) -> Optional[Dict[str, object]]:
        """
        Die Datenbank, die die Spanne bestimmt - falls es EINE gibt.

        BEDINGUNG, und sie ist streng: dieselbe Datenbank muss in ALLEN
        messbaren Laeufen die laengste gewesen sein. Eine, die es nur
        meistens ist, ist kein Grund, den Sicherungssatz umzubauen - und der
        Vorschlag, sie herauszunehmen, waere dann nur teilweise wirksam.
        """
        if not self.messbare:
            return None
        for eintrag in self.je_datenbank():
            if int(eintrag["war_laengste"]) == len(self.messbare):
                return eintrag
        return None

    def in_arbeitszeit(self, lauf: Laufbefund) -> Optional[bool]:
        """
        Lag der Beginn des Laufs im angegebenen Arbeitszeitfenster?

        None heisst NICHT GEPRUEFT - entweder wurde kein Fenster genannt oder
        der Beginn ist unbekannt. Der Unterschied zu 'ausserhalb' muss
        sichtbar bleiben; sonst liest sich eine fehlende Angabe als Entwarnung.

        Ein Fenster darf ueber Mitternacht gehen (von > bis). Das ist kein
        Sonderfall aus Vollstaendigkeitsdrang: eine Sicherung, die man
        bewusst in die Nachtruhe legt, wird genau so beschrieben.
        """
        if self.arbeitszeit is None or lauf.beginn_epoche is None:
            return None
        ortszeit = lauf.beginn_epoche + self.ortszeit_versatz * 60
        st = time.gmtime(ortszeit)
        minute = st.tm_hour * 60 + st.tm_min
        von, bis = self.arbeitszeit
        if von <= bis:
            return von <= minute < bis
        return minute >= von or minute < bis

    @property
    def laeufe_in_arbeitszeit(self) -> Tuple[Laufbefund, ...]:
        return tuple(l for l in self.laeufe if self.in_arbeitszeit(l) is True)

    # --------------------------------------------------------------- Befunde
    def befunde(self) -> List[str]:
        """
        Was an dieser Auswertung Aufmerksamkeit verlangt - als Klartext.

        Diese Liste UND NUR SIE bestimmt den Rueckgabewert 1. Damit koennen
        Bericht und Rueckgabewert nicht auseinanderlaufen: was den Wert
        erhoeht, steht auch im Bericht.
        """
        raus: List[str] = []
        if self.messbare and len(self.messbare) < self.mindest_laeufe:
            raus.append(
                "Nur %d auswertbare Laeufe - der Vorgang verlangt mindestens "
                "%d. Die Zahlen unten sind richtig, aber sie tragen noch "
                "keine Entscheidung."
                % (len(self.messbare), self.mindest_laeufe))
        for lauf in self.laeufe_mit_nachzueglern:
            anzahl = len(lauf.nachzuegler)
            raus.append(
                "Lauf %s: waehrend der Sicherung %s entstanden, die NICHT im "
                "Satz %s (%s). Das ist der unmittelbare Beleg, dass der "
                "Betrieb in den Satz hineingearbeitet hat."
                % (lauf.run_ts,
                   "ist 1 Datenbank" if anzahl == 1
                   else "sind %d Datenbanken" % anzahl,
                   "ist" if anzahl == 1 else "sind",
                   ", ".join(os.path.basename(p) for p in lauf.nachzuegler)))
        if self.schwelle_minuten is not None:
            grenze = self.schwelle_minuten * 60.0
            darueber = [l for l in self.messbare if l.spanne_s > grenze]
            if darueber:
                raus.append(
                    "%d von %d Laeufen liegen ueber der genannten Schwelle "
                    "von %g Minuten (laengster: %s in %s)."
                    % (len(darueber), len(self.messbare),
                       self.schwelle_minuten,
                       _dauer(self.spanne_max),
                       self.schlechtester.run_ts if self.schlechtester
                       else "-"))
        for lauf in self.laeufe:
            if lauf.stimmigkeit:
                raus.append("Lauf %s: %s" % (lauf.run_ts, lauf.stimmigkeit))
        if self.uebersprungen:
            anzahl = len(self.uebersprungen)
            raus.append(
                "%s nicht ausgewertet werden - siehe Abschnitt 'Nicht "
                "ausgewertet'. %s in der Grundgesamtheit."
                % ("1 Manifest konnte" if anzahl == 1
                   else "%d Manifeste konnten" % anzahl,
                   "Es fehlt" if anzahl == 1 else "Sie fehlen"))
        return raus

    def rueckgabewert(self) -> int:
        if not self.lesbar:
            return RC_UNLESBAR
        if not self.messbare:
            return RC_OHNE_GRUNDLAGE
        if self.befunde() or self.fehler:
            return RC_BEFUND
        return RC_OK


# =============================================================================
# Die Auswertung
# =============================================================================

class VersatzAuswertung:
    """
    Liest die Manifeste eines Sicherungsverzeichnisses und rechnet den
    Versatz aus. REIN LESEND.

    Der Konstruktor tut nichts ausser sich die Vorgaben zu merken - alle
    Arbeit steckt in auswerten(), damit ein Aufruf, der nur das Objekt baut,
    keine Platte anfasst. Dasselbe Muster wie SicherungsPruefer.
    """

    def __init__(self, verzeichnis: str,
                 mindest_laeufe: int = MINDEST_LAEUFE,
                 schwelle_minuten: Optional[float] = None,
                 ortszeit_versatz: int = 0,
                 arbeitszeit: Optional[Tuple[int, int]] = None) -> None:
        self._dir = verzeichnis
        self._mindest = mindest_laeufe
        self._schwelle = schwelle_minuten
        self._versatz = ortszeit_versatz
        self._arbeitszeit = arbeitszeit

    # ------------------------------------------------------------------- API
    def auswerten(self) -> Versatzbefund:
        try:
            namen = sorted(os.listdir(self._dir))
        except OSError as exc:
            return Versatzbefund(
                verzeichnis=self._dir, lesbar=False,
                fehler=("Das Verzeichnis ist nicht lesbar: %s" % exc,),
                mindest_laeufe=self._mindest,
                schwelle_minuten=self._schwelle,
                ortszeit_versatz=self._versatz,
                arbeitszeit=self._arbeitszeit)

        laeufe: List[Laufbefund] = []
        uebersprungen: List[Uebersprungen] = []
        for name in namen:
            if not (name.startswith(_MANIFEST_PRAEFIX)
                    and name.endswith(_MANIFEST_ENDUNG)):
                continue
            lauf, grund = self._manifest_lesen(
                os.path.join(self._dir, name), name)
            if lauf is not None:
                laeufe.append(lauf)
            else:
                uebersprungen.append(Uebersprungen(name=name, grund=grund))

        # NACH DEM BEGINN DES SATZES SORTIERT und nicht nach dem Dateinamen.
        # Beide Ordnungen fallen im Regelfall zusammen; wenn nicht, ist die
        # Zeit die richtige - ein Bericht ueber Zeitverlaeufe, der nach
        # Zeichenketten sortiert, waere an der Nase herumgefuehrt.
        laeufe.sort(key=lambda l: (l.beginn_epoche is None,
                                   l.beginn_epoche or 0, l.manifest))
        return Versatzbefund(
            verzeichnis=self._dir, lesbar=True,
            laeufe=tuple(laeufe), uebersprungen=tuple(uebersprungen),
            mindest_laeufe=self._mindest,
            schwelle_minuten=self._schwelle,
            ortszeit_versatz=self._versatz,
            arbeitszeit=self._arbeitszeit)

    # ------------------------------------------------------------- Innenteil
    def _manifest_lesen(self, pfad: str, name: str
                        ) -> Tuple[Optional[Laufbefund], str]:
        """
        Ein Manifest lesen. Rueckgabe (Laufbefund, "") oder (None, Grund).

        JEDER FEHLSCHLAG BEKOMMT EINEN GRUND IM KLARTEXT. Ein 'except:
        continue' waere hier der schwerste denkbare Fehler: die Auswertung
        liefe weiter, die Grundgesamtheit waere kleiner, und niemand saehe es.
        """
        try:
            with open(pfad, "r", encoding="ascii") as fh:
                daten = json.load(fh)
        except OSError as exc:
            return None, "nicht lesbar (%s)" % exc
        except UnicodeDecodeError as exc:
            # Die Manifeste werden ASCII geschrieben (backup_executor
            # _write_manifest, encoding="ascii"). Etwas anderes ist entweder
            # keins oder es wurde nachtraeglich angefasst - beides ist ein
            # Befund und kein Grund zum Weiterlesen mit anderer Codierung.
            return None, "keine ASCII-Datei (%s)" % exc
        except ValueError as exc:
            return None, "kein gueltiges JSON (%s)" % exc
        if not isinstance(daten, dict):
            return None, "kein JSON-Objekt"

        # DIE ABGRENZUNG ZU DEN ALTEN MANIFESTEN. Bis Build 616 trug ein
        # Manifest nur EINEN Zeitstempel fuer den ganzen Lauf; der Versatz
        # war darin nicht enthalten und laesst sich auch nicht nachtraeglich
        # herleiten. Solche Dateien werden benannt und beiseitegelassen -
        # nicht mit einer Spanne von 0 mitgezaehlt, die es nie gab.
        if "satz_von" not in daten or "satz_bis" not in daten:
            return None, ("aus einem Stand vor Build 617 - ohne "
                          "'satz_von'/'satz_bis' ist der Versatz nicht "
                          "enthalten")

        kopien: List[Kopiebefund] = []
        stempel: List[int] = []
        for eintrag in daten.get("results") or []:
            if not isinstance(eintrag, dict):
                continue
            begonnen = str(eintrag.get("begonnen_ts") or "")
            beendet = str(eintrag.get("beendet_ts") or "")
            e_von = ts_zu_epoche(begonnen)
            e_bis = ts_zu_epoche(beendet)
            dauer: Optional[float] = None
            grund = ""
            if e_von is None or e_bis is None:
                grund = "ohne brauchbare Zeitstempel - geht in keine Zahl ein"
            elif e_bis < e_von:
                # Rueckwaerts laufende Zeit. Kann nur durch eine
                # Uhrstellung oder eine Veraenderung der Datei entstehen.
                # Sie wird benannt und NICHT als negative Dauer verrechnet -
                # eine negative Dauer wuerde jeden Median verderben.
                grund = ("Ende liegt vor dem Beginn (%s .. %s) - die Dauer "
                         "ist nicht verwertbar" % (begonnen, beendet))
            else:
                dauer = float(e_bis - e_von)
                stempel.extend((e_von, e_bis))
            kopien.append(Kopiebefund(
                label=str(eintrag.get("label") or "?"),
                begonnen_ts=begonnen, beendet_ts=beendet,
                dauer_s=dauer,
                gelungen=eintrag.get("error") in (None, ""),
                grund=grund))

        satz_von = str(daten.get("satz_von") or "")
        satz_bis = str(daten.get("satz_bis") or "")
        m_von = ts_zu_epoche(satz_von)
        m_bis = ts_zu_epoche(satz_bis)

        spanne: Optional[float] = None
        beginn: Optional[int] = m_von
        stimmigkeit = ""
        if m_von is not None and m_bis is not None and m_bis >= m_von:
            spanne = float(m_bis - m_von)
        elif m_von is not None and m_bis is not None:
            stimmigkeit = ("'satz_bis' liegt vor 'satz_von' (%s .. %s) - die "
                           "Spanne dieses Laufs ist nicht verwertbar"
                           % (satz_von, satz_bis))
        else:
            stimmigkeit = ("'satz_von'/'satz_bis' sind nicht lesbar (%r/%r)"
                           % (satz_von, satz_bis))

        # DIE NACHRECHNUNG: die Felder des Manifests gegen die Einzelstempel.
        # Sie kostet nichts und ist die einzige Stelle, an der eine
        # veraenderte oder fremd erzeugte Datei auffallen kann.
        if stempel:
            nach_von, nach_bis = min(stempel), max(stempel)
            if beginn is None:
                beginn = nach_von
            if m_von is not None and m_bis is not None and not stimmigkeit:
                if nach_von != m_von or nach_bis != m_bis:
                    stimmigkeit = (
                        "die Angaben 'satz_von'/'satz_bis' (%s .. %s) decken "
                        "sich nicht mit den Einzelstempeln (%s .. %s); "
                        "gerechnet wird mit den Angaben des Manifests, aber "
                        "die Zahl ist damit nicht mehr gegengelesen"
                        % (satz_von, satz_bis,
                           time.strftime(TS_FORMAT, time.gmtime(nach_von)),
                           time.strftime(TS_FORMAT, time.gmtime(nach_bis))))

        nachzuegler = [str(p) for p in
                       (daten.get("nicht_gesichert_weil_neu") or [])]
        return Laufbefund(
            manifest=name,
            run_ts=str(daten.get("run_ts") or "?"),
            host=str(daten.get("host") or "?"),
            satz_von=satz_von, satz_bis=satz_bis,
            spanne_s=spanne, beginn_epoche=beginn,
            kopien=tuple(kopien), nachzuegler=tuple(nachzuegler),
            lauf_ok=bool(daten.get("ok")),
            stimmigkeit=stimmigkeit), ""


# =============================================================================
# Die Berichte
# =============================================================================

def bericht_text(b: Versatzbefund) -> str:
    """Der Befund als Text - fuer den Menschen, der entscheiden soll."""
    z: List[str] = []
    z.append("Versatz im Sicherungssatz")
    z.append("=" * _BREITE)
    z.append("Verzeichnis: %s" % b.verzeichnis)
    if not b.lesbar:
        z.append("")
        for zeile in _umbruch("NICHT LESBAR. Es ist nichts festgestellt.",
                             "  "):
            z.append(zeile)
        for f in b.fehler:
            z.append("  %s" % f)
        return "\n".join(z)

    zeitangabe = ("UTC" if b.ortszeit_versatz == 0
                  else "Ortszeit (UTC%+d:%02d)"
                       % (b.ortszeit_versatz // 60,
                          abs(b.ortszeit_versatz) % 60))
    z.append("Ausgewertet: %d %s mit messbarer Spanne, %d uebersprungen. "
             "Zeitangaben in %s."
             % (len(b.messbare),
                "Lauf" if len(b.messbare) == 1 else "Laeufe",
                len(b.uebersprungen), zeitangabe))
    z.append("")

    # ------------------------------------------------------- Frage 1: Spanne
    z.append("1) WIE GROSS IST DIE SPANNE?")
    if not b.messbare:
        for zeile in _umbruch(
                "Keine Grundlage. Es liegt kein Manifest aus Build 617 oder "
                "neuer vor; ohne 'satz_von'/'satz_bis' ist der Versatz nicht "
                "enthalten und auch nicht nachtraeglich herleitbar.", "   "):
            z.append(zeile)
    else:
        z.append("   kleinste  %s" % _dauer(b.spanne_min))
        z.append("   Median    %s" % _dauer(b.spanne_median))
        z.append("   groesste  %s%s"
                 % (_dauer(b.spanne_max),
                    ("   (%s)" % b.schlechtester.run_ts)
                    if b.schlechtester else ""))
        if b.schwelle_minuten is None:
            for zeile in _umbruch(
                    "KEINE SCHWELLE GENANNT - die Spanne ist gemessen, aber "
                    "nicht beurteilt. Eine Grenze, ab der der Versatz zu "
                    "gross ist, ist nicht entschieden; sie hier zu erfinden "
                    "waere eine Entscheidung im Gewand einer Messung. Wer "
                    "eine pruefen will: '--schwelle-minuten'.", "   "):
                z.append(zeile)
    z.append("")

    # -------------------------------------------- Frage 2: eine Datenbank?
    z.append("2) FAELLT DIE SPANNE AUF EINE DATENBANK?")
    dominant = b.dominante_datenbank
    if not b.messbare:
        z.append("   Nicht bestimmbar - keine Grundlage.")
    elif dominant is not None:
        anteil = dominant.get("anteil_median")
        for zeile in _umbruch(
                "JA: '%s' war in allen %d ausgewerteten Laeufen die laengste "
                "Kopie (Median %s, davon %s der Gesamtspanne). Sie aus dem "
                "taeglichen Satz herauszunehmen und gesondert zu sichern, "
                "wuerde den Satz der uebrigen entsprechend enger machen."
                % (dominant["label"], len(b.messbare),
                   _dauer(float(dominant["dauer_median_s"])),
                   ("%.0f %%" % (anteil * 100)) if anteil is not None
                   else "unbekannt"), "   "):
            z.append(zeile)
    else:
        for zeile in _umbruch(
                "NEIN - keine einzelne Datenbank war in allen Laeufen die "
                "laengste. Die Spanne verteilt sich; das Herausnehmen einer "
                "einzelnen Datenbank wuerde sie nicht wesentlich verkuerzen.",
                "   "):
            z.append(zeile)
    if b.laeufe:
        z.append("")
        z.append("   %-28s %6s %10s %10s %8s"
                 % ("Datenbank", "Laeufe", "Median", "laengste", "war max"))
        for e in b.je_datenbank():
            z.append("   %-28s %6d %10s %10s %8d"
                     % (str(e["label"])[:28], e["laeufe"],
                        _dauer(float(e["dauer_median_s"])),
                        _dauer(float(e["dauer_max_s"])), e["war_laengste"]))
    z.append("")

    # ------------------------------------------- Frage 3: Nachzuegler
    z.append("3) HAT DER BETRIEB IN DEN SATZ HINEINGEARBEITET?")
    if b.laeufe_mit_nachzueglern:
        for lauf in b.laeufe_mit_nachzueglern:
            z.append("   %s: %d %s waehrend des Laufs entstanden"
                     % (lauf.run_ts, len(lauf.nachzuegler),
                        "Datenbank" if len(lauf.nachzuegler) == 1
                        else "Datenbanken"))
            for p in lauf.nachzuegler:
                z.append("      %s" % os.path.basename(p))
        for zeile in _umbruch(
                "DAS IST EIN BELEG UND KEINE WAHRSCHEINLICHKEIT: diese "
                "Datenbanken fehlen im Satz. Eine Wiederherstellung des "
                "Gesamtbestandes aus diesem Lauf haette sie nicht.", "   "):
            z.append(zeile)
    elif b.laeufe:
        z.append("   In keinem ausgewerteten Lauf ist eine Datenbank neu "
                 "hinzugekommen.")
        for zeile in _umbruch(
                "Das ist die schwaechere Aussage von beiden: es belegt nur, "
                "dass keine DATENBANK entstanden ist. Ob in eine bestehende "
                "geschrieben wurde, sagt das Manifest nicht.", "   "):
            z.append(zeile)
    else:
        z.append("   Nicht bestimmbar - keine Grundlage.")
    z.append("")

    # ------------------------------------------------------ Die Einzellaeufe
    if b.laeufe:
        z.append("DIE EINZELNEN LAEUFE")
        z.append("   %-17s %-12s %9s %-22s %7s"
                 % ("Lauf (Beginn)", "Rechner", "Spanne", "laengste Kopie",
                    "Anteil"))
        for lauf in b.laeufe:
            laengste = lauf.laengste_kopie
            anteil = lauf.anteil_laengste
            beginn = (epoche_zu_uhrzeit(lauf.beginn_epoche, b.ortszeit_versatz)
                      if lauf.beginn_epoche is not None else "?")
            marke = ""
            in_az = b.in_arbeitszeit(lauf)
            if in_az is True:
                marke = " [Arbeitszeit]"
            elif in_az is False:
                marke = " [ausserhalb]"
            z.append("   %-17s %-12s %9s %-22s %7s%s"
                     % (beginn, str(lauf.host)[:12], _dauer(lauf.spanne_s),
                        (laengste.label[:22] if laengste else "-"),
                        ("%.0f %%" % (anteil * 100)) if anteil is not None
                        else "-", marke))
            if not lauf.lauf_ok:
                z.append("      Lauf war NICHT in Ordnung ('ok': false) - die "
                         "Spanne beschreibt einen unvollstaendigen Satz.")
            for k in lauf.kopien:
                if k.grund:
                    z.append("      %s: %s" % (k.label, k.grund))
        if b.arbeitszeit is not None:
            von, bis = b.arbeitszeit
            z.append("")
            z.append("   Arbeitszeitfenster: %02d:%02d-%02d:%02d Ortszeit; "
                     "%d von %d Laeufen lagen darin."
                     % (von // 60, von % 60, bis // 60, bis % 60,
                        len(b.laeufe_in_arbeitszeit), len(b.laeufe)))
        else:
            for zeile in _umbruch(
                    "Kein Arbeitszeitfenster genannt - ob ein Lauf in die "
                    "Arbeitszeit fiel, ist damit NICHT beurteilt "
                    "('--arbeitszeit').", "   "):
                z.append(zeile)
        z.append("")

    # -------------------------------------------------- Was nicht zaehlt
    if b.uebersprungen:
        z.append("NICHT AUSGEWERTET (%d)" % len(b.uebersprungen))
        for u in b.uebersprungen:
            z.append("   %s" % u.name)
            for zeile in _umbruch(u.grund, "      "):
                z.append(zeile)
        z.append("")

    # ------------------------------------------------------------- Befunde
    befunde = b.befunde()
    if befunde:
        z.append("BEFUNDE")
        for eintrag in befunde:
            for i, zeile in enumerate(_umbruch(eintrag, "     ")):
                z.append(("   * " + zeile.strip()) if i == 0 else zeile)
        z.append("")
    elif b.messbare:
        z.append("BEFUNDE: keine.")
        z.append("")

    for f in b.fehler:
        z.append("FEHLER: %s" % f)

    for zeile in _umbruch(
            "ZUM WEITEREN VORGEHEN: Diese Auswertung ersetzt die Entscheidung "
            "nicht, sie traegt sie. Zu entscheiden bleibt, ob es bei der "
            "Kennzeichnung bleibt (Stand: Entscheidung mc vom 31.07.2026) "
            "oder ob die Sicherung ein Wartungsfenster braucht - dann waere "
            "'backup_admin run' in Wartungsstufe A einzuordnen und mit dem "
            "Wartungsvorbehalt zu versehen. Das Ergebnis gehoert in einen "
            "Vermerk, nicht nur auf diesen Bildschirm.", "  "):
        z.append(zeile)
    z.append("Rueckgabewert: %d" % b.rueckgabewert())
    return "\n".join(z)


def bericht_json(b: Versatzbefund) -> dict:
    """Derselbe Befund als Woerterbuch - fuer Skripte und Weiterrechnen."""
    return {
        "verzeichnis": b.verzeichnis,
        "lesbar": b.lesbar,
        "rueckgabewert": b.rueckgabewert(),
        "mindest_laeufe": b.mindest_laeufe,
        "schwelle_minuten": b.schwelle_minuten,
        "schwelle_geprueft": b.schwelle_minuten is not None,
        "ortszeit_versatz_minuten": b.ortszeit_versatz,
        "arbeitszeit": (list(b.arbeitszeit) if b.arbeitszeit else None),
        "laeufe_gesamt": len(b.laeufe),
        "laeufe_messbar": len(b.messbare),
        "spanne_min_s": b.spanne_min,
        "spanne_median_s": b.spanne_median,
        "spanne_max_s": b.spanne_max,
        "schlechtester_lauf": (b.schlechtester.run_ts
                               if b.schlechtester else None),
        "dominante_datenbank": b.dominante_datenbank,
        "je_datenbank": b.je_datenbank(),
        "befunde": b.befunde(),
        "fehler": list(b.fehler),
        "uebersprungen": [{"name": u.name, "grund": u.grund}
                          for u in b.uebersprungen],
        "laeufe": [
            {
                "manifest": l.manifest,
                "run_ts": l.run_ts,
                "host": l.host,
                "ok": l.lauf_ok,
                "satz_von": l.satz_von,
                "satz_bis": l.satz_bis,
                "spanne_s": l.spanne_s,
                "uhrzeit_utc": l.uhrzeit_utc,
                "in_arbeitszeit": b.in_arbeitszeit(l),
                "stimmigkeit": l.stimmigkeit,
                "laengste_kopie": (l.laengste_kopie.label
                                   if l.laengste_kopie else None),
                "anteil_laengste": l.anteil_laengste,
                "nachzuegler": list(l.nachzuegler),
                "kopien": [
                    {"label": k.label, "begonnen_ts": k.begonnen_ts,
                     "beendet_ts": k.beendet_ts, "dauer_s": k.dauer_s,
                     "gelungen": k.gelungen, "grund": k.grund}
                    for k in l.kopien
                ],
            }
            for l in b.laeufe
        ],
    }


def arbeitszeit_zerlegen(text: str) -> Tuple[int, int]:
    """
    'HH:MM-HH:MM' in zwei Minutenwerte seit Mitternacht zerlegen.

    ES WIRD NICHTS ERRATEN: eine unverstaendliche Angabe fuehrt zu einer
    ValueError und damit zum Abbruch des Werkzeugs. Ein stillschweigend
    angenommenes Fenster wuerde jeden Lauf falsch einordnen, und der Fehler
    saehe aus wie ein Ergebnis.
    """
    teile = (text or "").split("-")
    if len(teile) != 2:
        raise ValueError("Erwartet wird 'HH:MM-HH:MM', bekommen: %r" % text)
    werte: List[int] = []
    for teil in teile:
        stueck = teil.strip().split(":")
        if len(stueck) != 2:
            raise ValueError("Erwartet wird 'HH:MM', bekommen: %r" % teil)
        try:
            stunde, minute = int(stueck[0]), int(stueck[1])
        except ValueError:
            raise ValueError("Keine Zahl in %r" % teil)
        if not (0 <= stunde <= 23 and 0 <= minute <= 59):
            raise ValueError("Keine gueltige Uhrzeit: %r" % teil)
        werte.append(stunde * 60 + minute)
    if werte[0] == werte[1]:
        raise ValueError(
            "Anfang und Ende sind gleich (%s) - ein Fenster der Laenge null "
            "oder eines ueber den ganzen Tag? Das ist nicht zu erraten."
            % teile[0].strip())
    return werte[0], werte[1]
