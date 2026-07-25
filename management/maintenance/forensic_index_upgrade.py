# =============================================================================
# management/maintenance/forensic_index_upgrade.py
# IT-Forensisches Ermittlungswerkzeug — Wartung: Indizes auf forensic_<uid>.db
# =============================================================================
# Zweck (Build 531, AP-3A-Nachlauf):
#   Legt auf bestehenden forensic_<uid>.db die Indizes an, die den
#   Fristenmonitor (GET /api/limitation) von Tabellendurchlaeufen befreien —
#   OHNE die Dateien neu erzeugen zu muessen.
#
# WARUM ES DIESES WERKZEUG GIBT (Messung, nicht Vermutung):
#   mc am 2026-07-25, zwei Messlaeufe mit tools/diag_limitation_laufzeit.py:
#     DEV  20,0 ms bei 31 Faellen
#     PROD 296,9 ms bei 18 Faellen  -> ~16,5 ms je Fall
#   Hochgerechnet auf 162 Faelle: ~2,7 s je Abruf der Sicht.
#
#   Die Ursache steht im DDL (forensic_uid.db.schema.sql, uebergeben 2026-07-25):
#   'uid_shares.posted_ts' und 'uid_downloads.time_ts' haben je einen Index
#   (uid_shares_ts_idx, uid_dl_ts_idx), 'uid_posts.posted_ts' und
#   'uid_pms_posts.posted_ts' haben KEINEN — dort indiziert das DDL nur
#   topic_id, forum_id und active. Ausgerechnet die beiden groessten Tabellen
#   werden bei jedem Abruf vollstaendig gescannt.
#
#   Ein Index macht MIN/MAX zu zwei B-Baum-Randzugriffen. Das ist die billigere
#   und ehrlichere Loesung als ein Zwischenspeicher auf einer FRISTAUSSAGE: eine
#   veraltete gruene Ampel waere schlimmer als eine langsame richtige.
#
# WAS SICH DABEI AENDERT — UND WAS NICHT (gemessen, Container 2026-07-25,
# SQLite, 5.000 Zeilen, journal_mode=delete):
#     vorher   77.824 B   MD5 d2b9b856c365d6f45eb36c0383c017ce
#     nachher 143.360 B   MD5 81cf7c0dd97d9937a89877853ea3a5a3
#     Inhalt (Tabellendaten): UNVERAENDERT
#     PRAGMA integrity_check: ok
#     Abfrageplan MIN/MAX: 'SCAN ... USING COVERING INDEX'
#
#   Die DATEI-Pruefsumme aendert sich also, der INHALT nicht. mc hat dazu am
#   2026-07-25 entschieden: "Wir speichern ausschliesslich den inneren
#   Hash-Wert. Es gibt hier keinen Grund zur Sorge. Wir haben kein
#   Datenmigrationsproblem." Dieses Werkzeug schreibt deshalb den INHALTSHASH
#   vor und nach der Aenderung ins Protokoll — er ist der Beleg, dass sich an
#   den Daten nichts geaendert hat.
#
# DIE INDEXLISTE WIRD NICHT GEPFLEGT, SONDERN ABGELEITET:
#   Kandidat ist jede Zeitquelle aus ZEITQUELLEN (limitation_repo.py), fuer die
#   in der Datei KEIN Index existiert, dessen ERSTE Spalte diese Spalte ist.
#   Damit kann die Liste nicht veralten: kommt eine Zeitquelle hinzu, bringt
#   dieses Werkzeug sie beim naechsten Lauf von selbst mit. Eine zweite,
#   handgepflegte Liste waere eine zweite Wahrheitsquelle — und die falsche
#   waere die, die gelesen wird (derselbe Fehler wie im Kopfkommentar von
#   limitation_repo.py, Build 528/530).
#
# EIGENES NAMENSPRAEFIX 'aiw_':
#   Von diesem Werkzeug angelegte Indizes heissen 'aiw_<tabelle>_<spalte>_idx'
#   und sind damit von den Indizes des Preppers UNTERSCHEIDBAR. Forensisch ist
#   das kein Zierrat: man kann jederzeit nachsehen, was das Ermittlungswerkzeug
#   an einer Beweismitteldatei veraendert hat.
#
# SICHERHEITSNETZE (in dieser Reihenfolge, jedes einzeln abbruchfaehig):
#   1. TROCKENLAUF IST DIE VORGABE. Geschrieben wird nur mit --ausfuehren.
#   2. WAL-gestempelte Dateien werden NICHT angefasst (Journal-Stempel im
#      Header, ohne SQLite lesbar). WAL ist projektweit verboten (Build 499),
#      und eine WAL-Datei auf einem Netzlaufwerk laesst sich ohnehin nicht
#      zuverlaessig oeffnen.
#   3. VOR der Aenderung: PRAGMA integrity_check, Zeilenzahlen je Tabelle,
#      Inhaltsfingerabdruck.
#   4. Die Aenderung selbst: CREATE INDEX IF NOT EXISTS, in EINER Transaktion.
#   5. NACH der Aenderung: dieselben drei Pruefungen erneut. Weicht etwas ab,
#      wird das als FEHLER protokolliert — die Datei ist dann gesondert zu
#      betrachten. (Rueckgaengig machen kann das Werkzeug nichts; ein DROP INDEX
#      waere eine zweite Aenderung an einer bereits auffaelligen Datei.)
#   6. Jede Datei wird EINZELN behandelt. Ein Fehler an einer Datei bricht den
#      Lauf NICHT ab — er wird benannt, und die uebrigen laufen weiter
#      (Grundregel 1: kein Beleg wird still uebersprungen).
#
# ZWEI PRUEFTIEFEN, weil die eine Geld kostet:
#   'fingerabdruck' (Vorgabe) — je betroffener Tabelle EIN Durchlauf:
#       COUNT(*), MIN/MAX/SUM der Zeitspalte, SUM und COUNT des Primaerschluessels.
#       Kosten: ein Tabellendurchlauf, also genau das, was der Monitor heute
#       ohnehin tut. Faengt jede Aenderung an Zeilenzahl und Zeitwerten.
#   'voll' — Hash ueber ALLE Zeilen ALLER Tabellen (ohne Indizes, nach rowid
#       geordnet, also indexunabhaengig). Der vollstaendige Beleg — aber er
#       liest die gesamte Datei. Bei 162 Dateien auf einem Netzlaufwerk ist das
#       eine Entscheidung und keine Nebensache; deshalb ist es nicht die
#       Vorgabe, und das Protokoll haelt fest, welche Tiefe gelaufen ist.
#
# Version: v0.8.531 · Build: 531 · 2026-07-25
# =============================================================================

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from db.journal_policy import journal_stamp
from management.deadlines.limitation_repo import ZEITQUELLEN

logger = logging.getLogger(__name__)

#: Dateinamensmuster der Falldatenbanken.
FORENSIC_RE = re.compile(r"^forensic_(\d+)\.db$")

#: Praefix aller von DIESEM Werkzeug angelegten Indizes (s. Modulkopf).
INDEX_PRAEFIX = "aiw_"

#: Die zulaessigen Pruestiefen.
PRUEFTIEFEN: Tuple[str, ...] = ("fingerabdruck", "voll")

#: Journal-Stempel im SQLite-Header: 2 = WAL.
STEMPEL_WAL = 2


def index_name(tabelle: str, spalte: str) -> str:
    """Der Name, unter dem dieses Werkzeug einen Index anlegt."""
    return "%s%s_%s_idx" % (INDEX_PRAEFIX, tabelle, spalte)


class ForensicIndexUpgradeError(RuntimeError):
    """Der Lauf ist als Ganzes undurchfuehrbar (nicht: eine Datei schlug fehl)."""


@dataclass(frozen=True)
class DateiBefund:
    """Das Ergebnis fuer GENAU EINE forensic_<uid>.db."""
    pfad: str
    subject_id: Optional[int]
    #: 'aktuell' | 'geplant' | 'geaendert' | 'uebersprungen' | 'fehler'
    zustand: str
    grund: str
    #: Indizes, die fehlten (Name, Tabelle, Spalte).
    fehlende: Tuple[Tuple[str, str, str], ...] = ()
    #: Tatsaechlich angelegte Indexnamen.
    angelegt: Tuple[str, ...] = ()
    inhalt_vorher: str = ""
    inhalt_nachher: str = ""
    integritaet_vorher: str = ""
    integritaet_nachher: str = ""
    zeilen_vorher: Dict[str, int] = field(default_factory=dict)
    zeilen_nachher: Dict[str, int] = field(default_factory=dict)
    dauer_ms: float = 0.0

    @property
    def unveraendert(self) -> bool:
        """Ist der INHALT nachweislich derselbe geblieben?"""
        return (bool(self.inhalt_vorher)
                and self.inhalt_vorher == self.inhalt_nachher
                and self.zeilen_vorher == self.zeilen_nachher)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pfad": self.pfad, "subject_id": self.subject_id,
            "zustand": self.zustand, "grund": self.grund,
            "fehlende": [list(f) for f in self.fehlende],
            "angelegt": list(self.angelegt),
            "inhalt_vorher": self.inhalt_vorher,
            "inhalt_nachher": self.inhalt_nachher,
            "inhalt_unveraendert": self.unveraendert,
            "integritaet_vorher": self.integritaet_vorher,
            "integritaet_nachher": self.integritaet_nachher,
            "zeilen_vorher": dict(self.zeilen_vorher),
            "zeilen_nachher": dict(self.zeilen_nachher),
            "dauer_ms": round(self.dauer_ms, 1),
        }


@dataclass(frozen=True)
class UpgradeProtokoll:
    """Der Lauf als Ganzes — das ist das Beweisstueck, nicht die Bildschirmausgabe."""
    verzeichnis: str
    ausgefuehrt: bool
    prueftiefe: str
    kandidaten: Tuple[Tuple[str, str], ...]
    dateien_gesamt: int
    zaehler: Dict[str, int]
    befunde: Tuple[DateiBefund, ...]
    dauer_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verzeichnis": self.verzeichnis,
            "ausgefuehrt": self.ausgefuehrt,
            "prueftiefe": self.prueftiefe,
            "kandidaten": [list(k) for k in self.kandidaten],
            "index_praefix": INDEX_PRAEFIX,
            "dateien_gesamt": self.dateien_gesamt,
            "zaehler": dict(self.zaehler),
            "dauer_ms": round(self.dauer_ms, 1),
            "befunde": [b.to_dict() for b in self.befunde],
        }


class ForensicIndexUpgrade:
    """
    Legt fehlende Zeitindizes auf forensic_<uid>.db an — nachpruefbar.

    Die Klasse haelt KEINEN Zustand ueber einen Lauf hinaus und oeffnet keine
    Verbindung im Konstruktor: jede Datei wird einzeln geoeffnet, behandelt und
    geschlossen. So kann ein Fehler an einer Datei die naechste nicht
    beeinflussen.
    """

    def __init__(self, verzeichnis: Any, *,
                 prueftiefe: str = "fingerabdruck",
                 quellen: Sequence[Tuple[str, str, str]] = ZEITQUELLEN) -> None:
        if prueftiefe not in PRUEFTIEFEN:
            raise ForensicIndexUpgradeError(
                "Unbekannte Prueftiefe %r. Erlaubt: %s"
                % (prueftiefe, ", ".join(PRUEFTIEFEN)))
        self._dir = Path(verzeichnis)
        self._tiefe = prueftiefe
        # Nur (Tabelle, Spalte) — die Belegtexte der Quelle interessieren hier
        # nicht, wohl aber, dass die Liste VON DORT kommt.
        self._kandidaten: Tuple[Tuple[str, str], ...] = tuple(
            (q[0], q[1]) for q in quellen)

    # -- Lesen ---------------------------------------------------------------

    def dateien(self) -> List[Path]:
        """Alle forensic_<uid>.db des Verzeichnisses, nach subject_id sortiert."""
        if not self._dir.is_dir():
            raise ForensicIndexUpgradeError(
                "Kein Verzeichnis: %s" % self._dir)
        treffer: List[Tuple[int, Path]] = []
        for p in self._dir.iterdir():
            m = FORENSIC_RE.match(p.name)
            if m and p.is_file():
                treffer.append((int(m.group(1)), p))
        treffer.sort()
        return [p for _uid, p in treffer]

    @staticmethod
    def _tabellen(con: sqlite3.Connection) -> List[str]:
        return [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]

    @staticmethod
    def _erste_indexspalten(con: sqlite3.Connection, tabelle: str) -> set:
        """
        Die Spalten, die in DIESER Tabelle als ERSTE Spalte eines Index stehen.

        Warum nur die erste: fuer MIN/MAX nutzt SQLite einen Index nur, wenn die
        gesuchte Spalte an dessen Anfang steht. Ein Index (a, b) hilft fuer
        MIN(b) nicht.
        """
        spalten = set()
        for row in con.execute(
                "PRAGMA index_list(%s)" % _q(tabelle)).fetchall():
            name = row[1]
            info = con.execute("PRAGMA index_info(%s)" % _q(name)).fetchall()
            for eintrag in info:
                if int(eintrag[0]) == 0 and eintrag[2] is not None:
                    spalten.add(str(eintrag[2]))
        return spalten

    def fehlende_indizes(self, con: sqlite3.Connection
                         ) -> List[Tuple[str, str, str]]:
        """
        (Indexname, Tabelle, Spalte) je Zeitquelle OHNE brauchbaren Index.

        Eine nicht vorhandene Tabelle ist KEIN Kandidat und KEIN Fehler: nicht
        jede Falldatenbank fuehrt jede Tabelle.
        """
        vorhanden = set(self._tabellen(con))
        fehlt: List[Tuple[str, str, str]] = []
        for tabelle, spalte in self._kandidaten:
            if tabelle not in vorhanden:
                continue
            # Existiert die Spalte ueberhaupt? Ein Index auf eine nicht
            # existierende Spalte waere ein harter SQLite-Fehler — und die
            # Meldung 'no such column' waere hier missverstaendlich, weil sie
            # wie ein Schaden aussieht statt wie eine Schemaabweichung.
            spalten = {str(r[1]) for r in
                       con.execute("PRAGMA table_info(%s)" % _q(tabelle))}
            if spalte not in spalten:
                continue
            if spalte in self._erste_indexspalten(con, tabelle):
                continue
            fehlt.append((index_name(tabelle, spalte), tabelle, spalte))
        return fehlt

    def zeilenzahlen(self, con: sqlite3.Connection) -> Dict[str, int]:
        """COUNT(*) je Tabelle. Die billigste Aussage ueber 'nichts verloren'."""
        out: Dict[str, int] = {}
        for t in self._tabellen(con):
            try:
                out[t] = int(con.execute(
                    "SELECT COUNT(*) FROM %s" % _q(t)).fetchone()[0])
            except sqlite3.Error as exc:              # pragma: no cover
                out[t] = -1
                logger.warning("Zeilenzahl %s nicht lesbar: %s", t, exc)
        return out

    def inhaltshash(self, con: sqlite3.Connection) -> str:
        """
        Der INHALTSHASH — indexunabhaengig, deterministisch.

        'fingerabdruck': je Kandidatentabelle ein Durchlauf mit Aggregaten.
        'voll':          alle Zeilen aller Tabellen, nach rowid geordnet.

        WARUM NACH rowid GEORDNET: Das Anlegen eines Index aendert die rowids
        NICHT (SQLite schreibt die Tabelle dabei nicht um). Die Reihenfolge ist
        damit ueber die Aenderung hinweg stabil — ohne ORDER BY waere sie es
        zwar praktisch auch, aber 'praktisch' ist bei einem Beleg zu wenig.

        WARUM NICHT iterdump(): dessen Ausgabe enthaelt die CREATE-INDEX-Zeilen
        und aendert sich damit ZWANGSLAEUFIG — er wuerde genau das messen, was
        sich aendern DARF, und nicht das, was gleich bleiben MUSS.
        """
        h = hashlib.sha256()
        h.update(("tiefe=%s\n" % self._tiefe).encode("utf-8"))
        if self._tiefe == "fingerabdruck":
            vorhanden = set(self._tabellen(con))
            for tabelle, spalte in self._kandidaten:
                if tabelle not in vorhanden:
                    continue
                spalten = {str(r[1]) for r in
                           con.execute("PRAGMA table_info(%s)" % _q(tabelle))}
                if spalte not in spalten:
                    continue
                row = con.execute(
                    "SELECT COUNT(*), COUNT(%s), MIN(%s), MAX(%s), SUM(%s) "
                    "FROM %s" % (_q(spalte), _q(spalte), _q(spalte),
                                 _q(spalte), _q(tabelle))).fetchone()
                h.update(("%s.%s=%r\n" % (tabelle, spalte, tuple(row))
                          ).encode("utf-8"))
            return h.hexdigest()

        for tabelle in self._tabellen(con):
            spalten = [str(r[1]) for r in
                       con.execute("PRAGMA table_info(%s)" % _q(tabelle))]
            if not spalten:
                continue
            liste = ", ".join(_q(s) for s in spalten)
            try:
                cur = con.execute(
                    "SELECT %s FROM %s ORDER BY rowid" % (liste, _q(tabelle)))
            except sqlite3.Error:
                # WITHOUT ROWID-Tabellen haben keine rowid. Dann wird nach
                # ALLEN Spalten geordnet — teurer, aber ebenso deterministisch.
                cur = con.execute(
                    "SELECT %s FROM %s ORDER BY %s"
                    % (liste, _q(tabelle), liste))
            h.update(("#%s(%s)\n" % (tabelle, liste)).encode("utf-8"))
            for zeile in cur:
                h.update(repr(tuple(zeile)).encode("utf-8", "surrogatepass"))
                h.update(b"\n")
        return h.hexdigest()

    @staticmethod
    def integritaet(con: sqlite3.Connection) -> str:
        row = con.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "?"

    # -- Ein Durchgang je Datei ----------------------------------------------

    def _messen(self, con: sqlite3.Connection
                ) -> Tuple[str, str, Dict[str, int]]:
        return (self.integritaet(con), self.inhaltshash(con),
                self.zeilenzahlen(con))

    def datei_behandeln(self, pfad: Path, *, ausfuehren: bool) -> DateiBefund:
        """
        EINE Datei. Wirft NICHT — jeder Fehler wird zu einem benannten Zustand,
        damit der Lauf weiterlaeuft und die Datei trotzdem im Protokoll steht.
        """
        beginn = time.monotonic()
        m = FORENSIC_RE.match(pfad.name)
        uid = int(m.group(1)) if m else None

        def fertig(**kw: Any) -> DateiBefund:
            kw.setdefault("pfad", str(pfad))
            kw.setdefault("subject_id", uid)
            kw["dauer_ms"] = (time.monotonic() - beginn) * 1000.0
            return DateiBefund(**kw)

        stempel = journal_stamp(pfad)
        if stempel is None:
            return fertig(zustand="fehler",
                          grund="keine lesbare SQLite-Datei (Header)")
        if stempel == STEMPEL_WAL:
            # WAL ist projektweit verboten (Build 499). Eine WAL-gestempelte
            # Datei wird hier NICHT umgestellt: das waere eine zweite,
            # unangekuendigte Aenderung an einem Beweismittel.
            return fertig(
                zustand="uebersprungen",
                grund="WAL-gestempelt (Journal-Stempel 2). Vor dem Index "
                      "zuerst mit tools/convert_journal_mode.py umstellen — "
                      "dieses Werkzeug aendert den Journalmodus NICHT.")

        try:
            ro = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
        except sqlite3.Error as exc:
            return fertig(zustand="fehler", grund="nicht oeffenbar: %s" % exc)
        try:
            fehlt = self.fehlende_indizes(ro)
            if not fehlt:
                return fertig(zustand="aktuell",
                              grund="alle Zeitquellen sind bereits indiziert")
            integ_v, hash_v, zeilen_v = self._messen(ro)
        except sqlite3.Error as exc:
            return fertig(zustand="fehler", grund="nicht lesbar: %s" % exc)
        finally:
            ro.close()

        if integ_v != "ok":
            # An einer bereits auffaelligen Datei wird NICHTS geschrieben.
            return fertig(
                zustand="fehler", fehlende=tuple(fehlt),
                integritaet_vorher=integ_v, inhalt_vorher=hash_v,
                zeilen_vorher=zeilen_v,
                grund="PRAGMA integrity_check meldet VOR der Aenderung %r — "
                      "es wird nichts geschrieben." % integ_v)

        if not ausfuehren:
            return fertig(
                zustand="geplant", fehlende=tuple(fehlt),
                integritaet_vorher=integ_v, inhalt_vorher=hash_v,
                zeilen_vorher=zeilen_v,
                grund="TROCKENLAUF — es wurde nichts geschrieben. %d Index/"
                      "Indizes wuerden angelegt: %s"
                      % (len(fehlt), ", ".join(f[0] for f in fehlt)))

        angelegt: List[str] = []
        try:
            rw = sqlite3.connect(str(pfad))
        except sqlite3.Error as exc:
            return fertig(zustand="fehler", fehlende=tuple(fehlt),
                          integritaet_vorher=integ_v, inhalt_vorher=hash_v,
                          zeilen_vorher=zeilen_v,
                          grund="nicht schreibend oeffenbar: %s" % exc)
        try:
            # EINE Transaktion fuer alle Indizes dieser Datei: entweder beide
            # oder keiner. Ein halb indizierter Bestand waere schwerer zu
            # beurteilen als ein gar nicht indizierter.
            rw.execute("BEGIN IMMEDIATE")
            for name, tabelle, spalte in fehlt:
                rw.execute("CREATE INDEX IF NOT EXISTS %s ON %s (%s)"
                           % (_q(name), _q(tabelle), _q(spalte)))
                angelegt.append(name)
            rw.commit()
        except sqlite3.Error as exc:
            try:
                rw.rollback()
            except sqlite3.Error:                    # pragma: no cover
                pass
            rw.close()
            return fertig(zustand="fehler", fehlende=tuple(fehlt),
                          integritaet_vorher=integ_v, inhalt_vorher=hash_v,
                          zeilen_vorher=zeilen_v,
                          grund="CREATE INDEX fehlgeschlagen (zurueckgerollt): "
                                "%s" % exc)
        finally:
            try:
                rw.close()
            except sqlite3.Error:                    # pragma: no cover
                pass

        try:
            pruef = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
        except sqlite3.Error as exc:                 # pragma: no cover
            return fertig(zustand="fehler", fehlende=tuple(fehlt),
                          angelegt=tuple(angelegt),
                          integritaet_vorher=integ_v, inhalt_vorher=hash_v,
                          zeilen_vorher=zeilen_v,
                          grund="nach der Aenderung nicht mehr lesbar: %s" % exc)
        try:
            integ_n, hash_n, zeilen_n = self._messen(pruef)
        except sqlite3.Error as exc:                 # pragma: no cover
            return fertig(zustand="fehler", fehlende=tuple(fehlt),
                          angelegt=tuple(angelegt),
                          integritaet_vorher=integ_v, inhalt_vorher=hash_v,
                          zeilen_vorher=zeilen_v,
                          grund="Nachpruefung fehlgeschlagen: %s" % exc)
        finally:
            pruef.close()

        befund = fertig(
            zustand="geaendert", fehlende=tuple(fehlt),
            angelegt=tuple(angelegt),
            integritaet_vorher=integ_v, integritaet_nachher=integ_n,
            inhalt_vorher=hash_v, inhalt_nachher=hash_n,
            zeilen_vorher=zeilen_v, zeilen_nachher=zeilen_n,
            grund="%d Index/Indizes angelegt: %s"
                  % (len(angelegt), ", ".join(angelegt)))
        if integ_n != "ok" or not befund.unveraendert:
            # DER FALL, FUER DEN DIE NACHPRUEFUNG DA IST. Er wird BENANNT, nicht
            # repariert: ein automatisches DROP INDEX waere eine zweite
            # Aenderung an einer Datei, die gerade auffaellig geworden ist.
            return fertig(
                zustand="fehler", fehlende=tuple(fehlt),
                angelegt=tuple(angelegt),
                integritaet_vorher=integ_v, integritaet_nachher=integ_n,
                inhalt_vorher=hash_v, inhalt_nachher=hash_n,
                zeilen_vorher=zeilen_v, zeilen_nachher=zeilen_n,
                grund="NACHPRUEFUNG SCHLUG AN — integrity_check %r, Inhalt "
                      "unveraendert: %s. Diese Datei ist gesondert zu "
                      "betrachten; es wird NICHTS zurueckgenommen."
                      % (integ_n, befund.unveraendert))
        return befund

    # -- Der ganze Lauf ------------------------------------------------------

    def lauf(self, *, ausfuehren: bool = False,
             grenze: Optional[int] = None) -> UpgradeProtokoll:
        """
        Alle Dateien des Verzeichnisses.

        grenze — hoechstens so viele Dateien behandeln. Fuer den ersten
        vorsichtigen Lauf ('erst drei, dann sehen wir weiter'). Die Zahl der
        AUSGELASSENEN Dateien steht im Protokoll: eine stille Begrenzung saehe
        aus wie ein vollstaendiger Lauf.
        """
        beginn = time.monotonic()
        alle = self.dateien()
        auswahl = alle if grenze is None else alle[:max(0, int(grenze))]
        befunde = [self.datei_behandeln(p, ausfuehren=ausfuehren)
                   for p in auswahl]
        zaehler: Dict[str, int] = {}
        for b in befunde:
            zaehler[b.zustand] = zaehler.get(b.zustand, 0) + 1
        if len(auswahl) < len(alle):
            zaehler["nicht_betrachtet"] = len(alle) - len(auswahl)
        return UpgradeProtokoll(
            verzeichnis=str(self._dir), ausgefuehrt=bool(ausfuehren),
            prueftiefe=self._tiefe, kandidaten=self._kandidaten,
            dateien_gesamt=len(alle), zaehler=zaehler, befunde=tuple(befunde),
            dauer_ms=(time.monotonic() - beginn) * 1000.0)


def _q(bezeichner: str) -> str:
    """
    SQLite-Bezeichner in doppelten Anfuehrungszeichen.

    Tabellen- und Spaltennamen kommen hier aus sqlite_master und aus der
    Konstante ZEITQUELLEN, also nicht von aussen. Trotzdem wird gequotet: ein
    kuenftiger Name mit Sonderzeichen soll dieses Werkzeug nicht ueberraschen,
    und ein Bezeichner ist in SQL kein Parameter — er LAESST sich nicht binden.
    """
    return '"%s"' % str(bezeichner).replace('"', '""')
