# =============================================================================
# management/stats/uid_stats_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Zuweisung (Build 534)
# =============================================================================
# Zweck:
#   Liefert der Zuweisungs-Sicht die KENNZAHLEN je Fall aus der Tabelle
#   'uid_stats' der forensic_<uid>.db — Beitraege, private Nachrichten,
#   Downloads, geteilte Dateien und was sonst noch dort steht. Die Zuweisung
#   soll nicht blind nach subject_id verteilt werden: wer 80 Faelle vergibt,
#   will sehen, welcher davon 12 Beitraege hat und welcher 40.000.
#   (Auftrag mc 2026-07-26: "weitere Spalten: Posts, PMs, Downloads, Shares".)
#
# WARUM EIN EIGENER ENDPUNKT UND NICHT /api/assignable (mc 2026-07-26):
#   Die Kennzahlen liegen NICHT in coordinator.db, sondern in bis zu einer
#   forensic_<uid>.db JE FALL — bei 162 Faellen sind das 162 Dateioeffnungen.
#   Haengte man sie an /api/assignable, wuerde die KERNSICHT (wer bearbeitet
#   was) erst erscheinen, wenn eine NEBENQUELLE vollstaendig gelesen ist. Die
#   Trennung haelt die Zuweisung arbeitsfaehig, auch wenn die forensic-Dateien
#   langsam, unvollstaendig oder unlesbar sind.
#
# DIE TABELLE (belegt, nicht geraten):
#   forensic_uid.db.schema.sql, Zeilen 395-402:
#     uid_stats(stat_key TEXT PRIMARY KEY, val_reported INTEGER,
#               val_computed INTEGER, discrepancy INTEGER)
#   Sie ist KEY-VALUE: jede Kennzahl ist eine ZEILE, keine Spalte. Genau
#   deshalb kann die Spaltenauswahl der Oberflaeche nicht fest verdrahtet
#   werden — welche Kennzahlen es gibt, steht erst nach dem Lesen fest. Der
#   Katalog in dieser Antwort ist die Datengrundlage der Spaltenauswahl.
#
# ZWEI ZAHLEN, NICHT EINE — UND WARUM BEIDE MITFAHREN:
#   'val_reported' ist die Zahl, die das FORUM SELBST ausgewiesen hat (z. B.
#   users.num_posts); 'val_computed' ist die Zahl, die der Prepper AUS DEN
#   GESICHERTEN DATEN gezaehlt hat (Beleg: aiw_sqlite_prepper,
#   stage1/phase_b_exporter.py:3405-3432, "doppelte Buchfuehrung").
#   'discrepancy' ist die Differenz. Angezeigt wird val_computed — es ist die
#   Zahl, die aus dem Beweismittel folgt. Aber die andere wird NICHT
#   weggeworfen: eine Abweichung ist selbst ein Befund (geloeschte Beitraege,
#   unvollstaendige Sicherung), und sie waere unauffindbar, wenn dieser
#   Lesepfad sie stillschweigend auf einen Wert zusammenzoege.
#
# NICHTS WIRD STILL UEBERSPRUNGEN (Grundregel 1). Jeder angefragte Fall
#   bekommt genau eine Zeile mit einem BENANNTEN Befund — auch der, dessen
#   Datei fehlt. Die Befundarten stehen in BEFUNDE. Der gefaehrlichste
#   denkbare Fehler dieses Moduls waere, eine unlesbare Datei als '0 Beitraege'
#   darzustellen: eine 0 sieht aus wie eine Feststellung und ist hier das
#   Gegenteil davon. Deshalb liefert ein nicht gelesener Fall KEINE Werte
#   (leeres dict) und nicht etwa Nullen; die Oberflaeche zeigt dafuer '—'.
#
# REIN LESEND: die forensic_<uid>.db werden mit file:...?mode=ro geoeffnet
#   (Muster management/deadlines/limitation_repo.py:473). Der
#   Migrationsvorbehalt ab 01.07.2026 ist NICHT beruehrt — es wird kein Byte
#   geschrieben, kein Schema angefasst, keine Datei angelegt.
#
# ZWISCHENSPEICHER (Fingerabdruck, prozesslokal):
#   Ein Abruf oeffnet im schlimmsten Fall 162 Dateien. Das Ergebnis je Datei
#   wird deshalb unter ihrem Fingerabdruck gemerkt: (mtime_ns, size) der
#   Datei UND ihrer -wal-Beidatei. Aendert sich eines von beiden, wird neu
#   gelesen. Die -wal-Datei MUSS mitzaehlen: SQLite schreibt im WAL-Modus in
#   die Beidatei, waehrend die Hauptdatei unveraendert liegen bleibt — ein
#   Fingerabdruck ohne sie wuerde einen veralteten Wert als aktuell ausgeben
#   (dasselbe Problem loest management/reports/reports_repo.py mit seinem
#   WAL-sicheren Cache).
#   Der Speicher ist PROZESSLOKAL und jederzeit verwerfbar: er enthaelt keine
#   Ermittlungsergebnisse, nur eine Kopie dessen, was ohnehin auf der Platte
#   steht. Er wird unter einer Sperre gefuehrt, weil der Management-Server
#   Anfragen nebenlaeufig bedient.
#
# Version: v0.8.534 · Build: 534 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: Die Befundarten je Fall. Als Konstante, damit die Oberflaeche ihre eigene
#  Aufzaehlung dagegen halten kann — ein neuer Befund ohne Platz in der Sicht
#  fiele sonst aus der Zaehlung (Muster limitation_repo.DATENLAGE_BEFUNDE).
BEFUNDE: Tuple[str, ...] = (
    "gelesen",            # uid_stats gelesen, mindestens eine Kennzahl da
    "ohne_kennzahlen",    # Tabelle vorhanden und lesbar, aber ohne Zeilen
    "ohne_uid_stats",     # Datei da, Tabelle 'uid_stats' fehlt
    "tabelle_unlesbar",   # Tabelle da, Abfrage schlug fehl (Grund benannt)
    "ohne_forensic_db",   # Fall in 'cases', aber keine forensic_<uid>.db
    "nicht_lesbar",       # Datei da, aber nicht oeffenbar (Grund benannt)
)

#: Die Befunde, bei denen Werte vorliegen. Alles andere liefert KEINE Werte.
BEFUNDE_MIT_WERTEN: Tuple[str, ...] = ("gelesen",)

#: Vorschlag an die Oberflaeche, welche Kennzahlen ohne eigene Auswahl sichtbar
#  sein sollen (mc 2026-07-26: "Anzahl Posts, PMs, Downloads, Shares").
#  Es ist ein VORSCHLAG, keine Filterung: die Antwort enthaelt IMMER alle
#  gefundenen Kennzahlen. Fehlt einer dieser Schluessel in den Daten, taucht er
#  im Katalog schlicht nicht auf — die Oberflaeche zeigt dann keine leere
#  Spalte, statt eine Spalte mit Nullen vorzutaeuschen.
#  Beleg der Schluesselnamen: aiw_sqlite_prepper/stage1/phase_b_exporter.py
#  (posts_total: 3406, shares_total: 3412, downloads_total: 3419,
#   pm_posts_total: 3450).
VORGESCHLAGENE_SPALTEN: Tuple[str, ...] = (
    "posts_total", "pm_posts_total", "downloads_total", "shares_total",
)

#: Die Abfrage. EXPLIZITE Spalten (kein SELECT *): faellt eine Spalte in einer
#  aelteren Datei weg, soll das ein BENANNTER Fehler sein und keine stille
#  Formatabweichung.
_SQL_STATS = ("SELECT stat_key, val_reported, val_computed, discrepancy "
              "FROM uid_stats")

#: Prozesslokaler Zwischenspeicher: Pfad -> (Fingerabdruck, Befund).
_CACHE: Dict[str, Tuple[Tuple[int, int, int, int], "CaseStats"]] = {}
_CACHE_LOCK = threading.Lock()


def cache_leeren() -> None:
    """
    Verwirft den Zwischenspeicher vollstaendig.

    Existiert fuer Tests und fuer den Fall, dass jemand die forensic-Dateien
    unter laufendem Server austauscht. Der Speicher haelt keine Ergebnisse —
    ihn zu leeren kostet nur Zeit, nie Wissen.
    """
    with _CACHE_LOCK:
        _CACHE.clear()


def _fingerabdruck(path: Path) -> Tuple[int, int, int, int]:
    """
    (mtime_ns, size) der Datei UND ihrer -wal-Beidatei; fehlende Teile 0.

    Vier Zahlen statt zwei — siehe Kopfkommentar (WAL). Ein Fehler beim
    Abfragen der Dateidaten fuehrt zu (0,0,0,0): das ist ein Fingerabdruck, der
    zu keinem gespeicherten passt, also wird neu gelesen. Der teure, aber
    richtige Ausgang.
    """
    def _stat(p: Path) -> Tuple[int, int]:
        try:
            st = p.stat()
            return (int(st.st_mtime_ns), int(st.st_size))
        except OSError:
            return (0, 0)

    haupt = _stat(path)
    wal = _stat(Path(str(path) + "-wal"))
    return (haupt[0], haupt[1], wal[0], wal[1])


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,)).fetchone() is not None


@dataclass(frozen=True)
class CaseStats:
    """
    Die Kennzahlen EINES Falls — oder der Grund, warum es keine gibt.

    'werte' bildet stat_key -> {'c': val_computed, 'r': val_reported,
    'd': discrepancy}. Die kurzen Schluessel sind Absicht: bei 162 Faellen mal
    24 Kennzahlen spart das rund 100 kB je Abruf, und die Bedeutung steht in
    genau einem Kommentar statt in jedem einzelnen Datensatz.

    Bei jedem Befund ausser 'gelesen' ist 'werte' LEER — nie mit Nullen
    gefuellt (siehe Kopfkommentar, Grundregel 1).
    """
    subject_id: int
    befund: str
    detail: str
    werte: Dict[str, Dict[str, Optional[int]]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"subject_id": self.subject_id, "befund": self.befund,
                "detail": self.detail, "werte": self.werte}


def read_uid_stats(path: Path, subject_id: int) -> CaseStats:
    """
    Liest uid_stats aus EINER forensic_<uid>.db (read-only).

    Reine E/A-Funktion, getrennt testbar. Sie WIRFT NICHT: jeder Fehlerfall
    wird zu einem benannten Befund, damit der Fall in der Liste BLEIBT
    (Grundregel 1; Muster limitation_repo.read_tatzeit).
    """
    if not path.exists():
        return CaseStats(
            subject_id=subject_id, befund="ohne_forensic_db",
            detail="forensic_%d.db fehlt (%s)" % (subject_id, path.parent))

    try:
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    except sqlite3.Error as exc:
        return CaseStats(subject_id=subject_id, befund="nicht_lesbar",
                         detail="nicht oeffenbar: %s" % exc)

    try:
        # EIGENER FEHLER, GEFUNDEN UND BEHOBEN (Build 534, Test US05):
        # Der erste Entwurf hat _table_exists UNGESCHUETZT aufgerufen. Das war
        # falsch, und zwar aus einem Grund, den man dem Code nicht ansieht:
        # sqlite3.connect() OEFFNET keine Datei — es merkt sich nur den Pfad.
        # Der Fehler 'file is not a database' faellt deshalb erst bei der
        # ERSTEN ABFRAGE an, nicht beim Verbinden. Eine beschaedigte oder
        # falsch benannte forensic_<uid>.db haette die Ausnahme bis in den
        # Endpunkt durchgereicht und die Kennzahlen ALLER Faelle mit einem 500
        # beendet — ein einziger kaputter Fall haette die ganze Liste
        # verschwinden lassen. Genau das soll dieses Modul nicht koennen.
        try:
            hat_tabelle = _table_exists(con, "uid_stats")
        except sqlite3.Error as exc:
            return CaseStats(subject_id=subject_id, befund="nicht_lesbar",
                             detail="nicht lesbar: %s" % exc)
        if not hat_tabelle:
            return CaseStats(
                subject_id=subject_id, befund="ohne_uid_stats",
                detail="Tabelle 'uid_stats' fehlt in %s" % path.name)
        try:
            zeilen = con.execute(_SQL_STATS).fetchall()
        except sqlite3.Error as exc:
            # Tabelle da, Abfrage scheitert (z. B. fehlende Spalte in einer
            # aelteren Datei). Das ist etwas ANDERES als 'keine Kennzahlen' —
            # und der Unterschied entscheidet, ob man in den Daten oder im
            # Code sucht (dieselbe Lehre wie limitation_repo, Build 527).
            return CaseStats(
                subject_id=subject_id, befund="tabelle_unlesbar",
                detail="uid_stats nicht abfragbar: %s" % exc)

        werte: Dict[str, Dict[str, Optional[int]]] = {}
        for key, reported, computed, discrepancy in zeilen:
            if key is None:
                continue          # ohne Schluessel keine Spalte — s. u.
            werte[str(key)] = {
                "c": None if computed is None else int(computed),
                "r": None if reported is None else int(reported),
                "d": None if discrepancy is None else int(discrepancy),
            }
        # Ein NULL-Schluessel kann in uid_stats nicht vorkommen (PRIMARY KEY
        # auf TEXT NOT NULL, forensic_uid.db.schema.sql:397). Die Pruefung
        # oben ist trotzdem da — aber sie schweigt nicht: taucht so eine Zeile
        # doch auf, ist die Datei nicht die, fuer die wir sie halten.
        stumme = sum(1 for z in zeilen if z[0] is None)
        if stumme:
            logger.warning(
                "uid_stats in %s enthaelt %d Zeile(n) ohne stat_key — "
                "entgegen dem Schema (PRIMARY KEY). Sie sind NICHT in die "
                "Kennzahlen eingegangen.", path.name, stumme)

        if not werte:
            return CaseStats(
                subject_id=subject_id, befund="ohne_kennzahlen",
                detail="uid_stats vorhanden, aber ohne verwertbare Zeile")
        return CaseStats(
            subject_id=subject_id, befund="gelesen",
            detail="%d Kennzahl(en)" % len(werte), werte=werte)
    finally:
        con.close()


def read_uid_stats_cached(path: Path, subject_id: int) -> CaseStats:
    """
    Wie read_uid_stats, aber mit Fingerabdruck-Zwischenspeicher (s. Kopf).

    Der Fingerabdruck wird IMMER frisch bestimmt — gespart wird das Oeffnen
    und Lesen der Datenbank, nie die Pruefung, ob sich die Datei geaendert hat.
    """
    schluessel = str(path)
    abdruck = _fingerabdruck(path)
    with _CACHE_LOCK:
        treffer = _CACHE.get(schluessel)
        if treffer is not None and treffer[0] == abdruck:
            return treffer[1]

    ergebnis = read_uid_stats(path, subject_id)

    with _CACHE_LOCK:
        _CACHE[schluessel] = (abdruck, ergebnis)
    return ergebnis


@dataclass(frozen=True)
class UidStatsReport:
    """
    Die Kennzahlen ALLER angefragten Faelle plus der Katalog der Kennzahlen.

    'katalog' ist die Datengrundlage der Spaltenauswahl in der Oberflaeche:
    je gefundenem stat_key, in wie vielen Faellen er vorkommt. Sortiert nach
    Schluesselname — die Reihenfolge in einer key-value-Tabelle ist sonst
    beliebig, und eine Spaltenauswahl, die bei jedem Abruf anders sortiert
    ist, waere genau die Sorte Unruhe, die diese Ueberarbeitung beseitigen soll.
    """
    faelle: Tuple[CaseStats, ...]
    katalog: Tuple[Tuple[str, int], ...]
    befund_zaehler: Dict[str, int]
    generated_at: int

    def to_dict(self) -> Dict[str, Any]:
        # 'stats' ist nach subject_id geschluesselt (als String — JSON kennt
        # keine Zahlschluessel). Faelle OHNE Werte stehen trotzdem drin, mit
        # leerem 'werte' und ihrem Befund: die Oberflaeche soll den Unterschied
        # zwischen 'null Beitraege' und 'nicht gelesen' anzeigen koennen.
        return {
            "generated_at": self.generated_at,
            "katalog": [{"key": k, "faelle": n} for k, n in self.katalog],
            "vorgeschlagen": [k for k in VORGESCHLAGENE_SPALTEN
                              if k in dict(self.katalog)],
            "befunde": list(BEFUNDE),
            "befund_zaehler": dict(self.befund_zaehler),
            "probleme": [c.to_dict() for c in self.faelle
                         if c.befund not in BEFUNDE_MIT_WERTEN],
            "stats": {str(c.subject_id): {"befund": c.befund,
                                          "werte": c.werte}
                      for c in self.faelle},
        }


class UidStatsRepo:
    """
    Read-Model: Kennzahlen aller Faelle aus den forensic_<uid>.db.

    coordinator.db liefert die Fallliste, die forensic_<uid>.db die Zahlen.
    NICHT scope-behaftet — die Auswahl der Faelle trifft der Endpunkt
    (Muster LimitationRepo).
    """

    def __init__(self, con: sqlite3.Connection, forensic_dir: Any) -> None:
        self._con = con
        self._forensic = Path(forensic_dir)

    def _cases(self, subject_ids: Optional[Sequence[int]] = None
               ) -> List[int]:
        """
        Welche Faelle gelesen werden.

        subject_ids=None  -> alle Faelle der Fallakte (Tabelle 'cases').
        subject_ids=[...] -> GENAU DIESE, woertlich.

        DIE ZWEITE ZEILE IST WICHTIG UND WAR IM ERSTEN ENTWURF FALSCH:
        dort wurde die uebergebene Liste durch 'WHERE subject_id IN (...)'
        gegen die Fallakte GEFILTERT. Wer eine subject_id anfragte, die (noch)
        nicht in 'cases' steht, bekam sie STILL nicht zurueck — und genau
        dieser Fall ist der Regelfall der Sicht 'Fall-Erkennung': dort stehen
        die auf der Platte gefundenen forensic_<uid>.db, die noch NICHT
        aufgenommen sind. Die Kennzahlen waeren ausgerechnet fuer die Faelle
        verschwunden, fuer die man sie am dringendsten braucht — und zwar
        lautlos (Grundregel 1). Eine angefragte Kennung ist eine ANGABE des
        Aufrufers, kein Suchbegriff in der Fallakte.

        Eine LEERE Liste ist eine Auswahl und bedeutet ausdruecklich NICHT
        'alle' (Muster limitation_repo._cases).
        """
        if subject_ids is not None:
            # sorted(set(...)): doppelte Kennungen ergeben keine doppelte
            # Zeile — und die Reihenfolge ist stabil, nicht die des Aufrufers.
            return sorted({int(s) for s in subject_ids})
        return [int(r[0]) for r in self._con.execute(
            "SELECT subject_id FROM cases ORDER BY subject_id").fetchall()]

    def collect(self, *, subject_ids: Optional[Sequence[int]] = None,
                use_cache: bool = True, now: Optional[int] = None
                ) -> UidStatsReport:
        """
        Liest die Kennzahlen aller (oder der angegebenen) Faelle.

        'use_cache=False' erzwingt das Neulesen aller Dateien — der Endpunkt
        bietet das als 'force=1' an, damit niemand einem Zwischenspeicher
        ausgeliefert ist, dem er nicht traut.
        """
        lesen = read_uid_stats_cached if use_cache else read_uid_stats

        faelle: List[CaseStats] = []
        katalog: Dict[str, int] = {}
        zaehler: Dict[str, int] = {b: 0 for b in BEFUNDE}

        for subject_id in self._cases(subject_ids):
            pfad = self._forensic / ("forensic_%d.db" % subject_id)
            stats = lesen(pfad, subject_id)
            faelle.append(stats)
            # Ein unbekannter Befund wuerde aus der Zaehlung fallen — deshalb
            # wird er aufgenommen UND protokolliert, statt still zu addieren.
            if stats.befund not in zaehler:
                logger.error("Unbekannter Befund %r (Fall %d) — BEFUNDE "
                             "ergaenzen!", stats.befund, subject_id)
                zaehler[stats.befund] = 0
            zaehler[stats.befund] += 1
            for key in stats.werte:
                katalog[key] = katalog.get(key, 0) + 1

        return UidStatsReport(
            faelle=tuple(faelle),
            katalog=tuple(sorted(katalog.items())),
            befund_zaehler=zaehler,
            generated_at=int(time.time()) if now is None else int(now),
        )
