# =============================================================================
# management/deadlines/limitation_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Zweck (Idee 32, Build 524):
#   Das READ-MODEL des Fristenmonitors: es beschafft je Fall den Fristbeginn
#   (§ 78a StGB — Beendigung der Tat) aus den forensic_<uid>.db und laesst die
#   reine Rechenschicht (limitation.py) darauf rechnen.
#
# WORAUS DER FRISTBEGINN GEBILDET WIRD (belegt, nicht geraten):
#   * fdb.uid_posts.posted       — Zeitpunkt eines Forumsbeitrags, Unix-Sekunden
#                                  (Beleg: db/forensic_db.py:401-434; Spalten
#                                  belegt in tests/test_build388_vorlagen.py:356)
#   * fdb.uid_pms_posts.posted_ts — Zeitpunkt einer privaten Nachricht,
#                                  Unix-Sekunden (Beleg: db/forensic_db.py:
#                                  447-480; SCHWAECHERER Beleg — der Spaltenname
#                                  beruht auf einer Entwicklerangabe vom
#                                  2026-07-15, vermerkt in tests/
#                                  test_build432_pm_content_ts.py:11)
#
#   NICHT VERWENDET: pages.fetched_at. Das ist der SICHERUNGSZEITPUNKT des
#   Scrapers und hat mit der Tatzeit nichts zu tun; eine Verwechslung wuerde
#   jede Frist um Jahre verschieben. Ebenso NICHT uid_profile.registered (die
#   Registrierung ist keine Tathandlung).
#
#   NICHT VORHANDEN: ein Zeitstempel je geteilter Datei (share_id). Recherche
#   2026-07-25: im Repository ist kein solcher Wert referenziert, es gibt nur
#   den Zaehler uid_stats.stat_key='shares_total'. Teilungsakte gehen deshalb
#   NICHT in den Fristbeginn ein — das ist eine LUECKE und wird als solche
#   gemeldet (Feld 'hinweise'), nicht durch einen Ersatzwert ueberbrueckt.
#
# DIE SPAETESTE HANDLUNG IST DER FRISTBEGINN — und die frueheste steht daneben.
#   Begruendung: § 78a StGB knuepft an die BEENDIGUNG an; die spaeteste belegte
#   Handlung ist damit die fristrechtlich guenstigste BELEGTE Tatsache. Ob
#   mehrere Handlungen eine Tat im Rechtssinne bilden, ist eine juristische
#   Bewertung — das Werkzeug trifft sie nicht und sagt das im Vorbehalt. Die
#   FRUEHESTE Handlung faehrt trotzdem mit: sie zeigt die Spanne der Aktivitaet
#   und macht sichtbar, wenn zwischen erster und letzter Handlung Jahre liegen.
#
# NICHTS WIRD STILL UEBERSPRUNGEN (Grundregel 1). Jeder Fall landet in genau
#   einer Zeile, auch wenn er unlesbar ist. SECHS Befundarten werden GEZAEHLT und
#   BENANNT:
#     ohne_forensic_db      — Fall in 'cases', aber keine forensic_<uid>.db.
#     ohne_zeittabelle      — Datei da, aber weder uid_posts noch uid_pms_posts.
#     nicht_lesbar          — Datei da, aber nicht oeffenbar/lesbar (mit Grund).
#     zeitspalte_unlesbar   — Tabelle da, aber KEINE Zeitspalte lesbar (Grund
#                             mit). NEU in Build 527.
#     belegt_unvollstaendig — Zeitstempel gefunden, ABER mindestens eine Quelle
#                             war nicht lesbar. NEU in Build 527.
#     ohne_tatzeit          — Tabellen und Spalten lesbar, aber kein einziger
#                             Zeitstempel gesetzt.
#   Ein Monitor, der solche Faelle weglaesst, saehe nach vollstaendiger Pruefung
#   aus und waere der gefaehrlichste denkbare Beleg.
#
# BUILD 527 — WAS HIER FALSCH WAR (Befund aus der PROD-Messung 2026-07-25):
#   In den ECHTEN forensic_<uid>.db existiert die Spalte 'uid_posts.posted'
#   NICHT ('no such column: posted', 162 von 162 Dateien). Build 524 hat daraus
#   ZWEI falsche Aussagen gemacht, und beide waren Grundregel-1-Verstoesse:
#
#   (a) Schlug der Spaltenzugriff fehl und lieferte auch die zweite Quelle
#       nichts, meldete der Fall 'ohne_tatzeit' mit dem Text 'Zeittabelle(n)
#       vorhanden, aber kein einziger Zeitstempel gesetzt'. Das war SCHLICHT
#       FALSCH: es war nicht 'kein Zeitstempel gesetzt', sondern 'die Spalte war
#       nicht lesbar'. Der Unterschied entscheidet darueber, ob man in den Daten
#       oder im Code sucht.
#
#   (b) Schlug uid_posts fehl, lieferte aber uid_pms_posts einen Wert, meldete
#       der Fall schlicht 'belegt' — OHNE jede Spur, dass die STAERKERE Quelle
#       ausgefallen war. Der Fristbeginn stuetzte sich dann allein auf private
#       Nachrichten. Das ist die gefaehrlichere der beiden Fehlwirkungen: die
#       Zahl sah vollwertig aus. (Richtung des Fehlers: fehlen spaetere
#       Beitraege, wird der Fristbeginn ZU FRUEH angesetzt, die Frist also zu
#       kurz gerechnet — der Fall erscheint DRINGENDER als er ist. Das ist die
#       ungefaehrliche Richtung, aber ein Bericht mit falschem Datum bleibt
#       falsch.)
#
#   Seit Build 527 gilt: ein Fall mit ausgefallener Quelle ist NIE einfach
#   'belegt'. Und der Ausfall wird EINMAL je Abruf zusammengefasst protokolliert
#   statt 162-mal einzeln (der Log-Schwall der Messung war selbst ein Befund).
#
# REIN LESEND: coordinator.db und alle forensic_<uid>.db werden mit
#   file:...?mode=ro geoeffnet (Muster management/reports/reports_repo.py:122).
#   Der Migrationsvorbehalt ab 01.07.2026 ist NICHT beruehrt.
#
# Version: v0.8.528 · Build: 528 · 2026-07-25
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from management.deadlines.limitation import (
    DEFAULT_VORWARN_TAGE,
    LimitationAssessment,
    assess_limitation,
)
from management.deadlines.limitation_params import LimitationParams

logger = logging.getLogger(__name__)

#: Die ausgewerteten Zeitquellen: (Tabelle, Spalte, Belegqualitaet).
#
#  BELEG (Build 528): das VOLLSTAENDIGE DDL der forensic_<uid>.db, von mc am
#  2026-07-25 als 'forensic_uid.db.schema.sql' uebergeben, bestaetigt durch zwei
#  unabhaengige Sondenlaeufe (DEV und PROD, je 7 Dateien,
#  tools/diag_limitation_laufzeit.py). DAS IST EIN BELEG AUS DEN ECHTEN DATEN —
#  im Unterschied zu Build 524, das sich auf eine TESTVORRICHTUNG gestuetzt hat
#  (tests/test_build388_vorlagen.py legte 'uid_posts(id, posted)' selbst an; die
#  Spalten heissen in Wirklichkeit 'post_id' und 'posted_ts').
#
#  VIER TATHANDLUNGS-QUELLEN, nicht mehr zwei. Die beiden neuen sind fuer die
#  verfahrensgegenstaendlichen Tatbestaende die AUSSAGEKRAEFTIGSTEN:
#    * uid_shares.posted_ts    — Teilen einer Datei: die Handlung des
#                                Verbreitens (§ 184b Abs. 1 S. 1 Nr. 1).
#    * uid_downloads.time_ts   — Abruf/Download: die Handlung des
#                                Sich-Verschaffens bzw. des Abrufs
#                                (§ 184b Abs. 1 S. 1 Nr. 2, Abs. 3).
#  Beide fehlten in Build 524. Ein Fall, dessen spaeteste Handlung ein Download
#  oder ein Teilungsakt war, bekam dort einen ZU FRUEHEN Fristbeginn.
ZEITQUELLEN: Tuple[Tuple[str, str, str], ...] = (
    ("uid_posts", "posted_ts",
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_posts); Sonde DEV/PROD "
     "2026-07-25 — 7562 Werte, 2019-02-28 .. 2024-07-06"),
    ("uid_pms_posts", "posted_ts",
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_pms_posts); Sonde "
     "DEV/PROD 2026-07-25 — 8813 Werte, 2019-12-26 .. 2024-07-06"),
    ("uid_shares", "posted_ts",
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_shares, Index "
     "uid_shares_ts_idx); Sonde DEV/PROD 2026-07-25 — 2023-01-08 .. 2024-05-12"),
    ("uid_downloads", "time_ts",
     "belegt: forensic_uid.db.schema.sql (Tabelle uid_downloads, Index "
     "uid_dl_ts_idx); Sonde DEV/PROD 2026-07-25 — 2024-02-10 .. 2024-02-16"),
)

#: Plausibilitaetsrahmen fuer einen Tatzeitpunkt (Unix-Sekunden).
#
#  WARUM ES IHN GIBT: Ein INTEGER ist noch kein Zeitstempel. Die Sonde hat am
#  2026-07-25 zwei Gegenbeispiele geliefert — 'uid_profile.id' faellt
#  rechnerisch in den Epoch-Bereich (Forum-Benutzer-IDs liegen um 1,0 Mrd.), und
#  'uid_profile.registered' enthaelt Werte von 1970-01-01, also Epoch 0 als
#  Platzhalter fuer 'unbekannt'. Ohne Rahmen entstuende daraus eine Frist, die
#  plausibel AUSSIEHT.
#
#  DIE GRENZEN SIND KEINE ERFINDUNG: mc am 2026-07-25 — "Das Forum war zwischen
#  2019 und 2024 aktiv." Der Rahmen liegt grosszuegig darum (2018-01-01 bis
#  2027-01-01): er soll GROBE Fehlgriffe abfangen, nicht Feinheiten aussortieren.
#
#  KEIN STILLES VERWERFEN: Werte ausserhalb des Rahmens werden GEZAEHLT und in
#  der Antwort ausgewiesen. Ein weggelassener Wert, von dem niemand erfaehrt,
#  waere genau der Fehler, den dieser Rahmen verhindern soll.
PLAUSIBEL_VON = 1514764800     # 2018-01-01T00:00:00Z
PLAUSIBEL_BIS = 1798761600     # 2027-01-01T00:00:00Z

#: KORREKTUR EINER FALSCHEN AUSSAGE AUS BUILD 524 (Build 528).
#
#  Dort stand, fuer geteilte Dateien (share_id) existiere KEIN Zeitstempel. DAS
#  WAR FALSCH. Die Aussage beruhte auf einer Suche im QUELLTEXT dieses Projekts
#  — dort wird kein solcher Wert benutzt — und ich habe daraus geschlossen, es
#  gebe ihn nicht. Das ist ein Fehlschluss von 'der Code verwendet es nicht' auf
#  'die Daten haben es nicht'. uid_shares hat eine Spalte 'posted_ts' MIT
#  eigenem Index; sie ist seit Build 528 eine Tathandlungs-Quelle.
HINWEIS_QUELLEN = (
    "Als Tathandlung gewertet werden: Beitraege (uid_posts.posted_ts), private "
    "Nachrichten (uid_pms_posts.posted_ts), Teilungsakte "
    "(uid_shares.posted_ts) und Abrufe/Downloads (uid_downloads.time_ts). "
    "Teilungsakte und Downloads sind seit Build 528 erfasst; in Build 524 "
    "fehlten sie, weshalb der Fristbeginn dort zu frueh angesetzt sein konnte."
)

#: Der Hinweis auf den bewusst NICHT verwendeten Sicherungszeitpunkt.
HINWEIS_FETCHED_AT = (
    "pages.fetched_at (Sicherungszeitpunkt des Scrapers) wird ausdruecklich "
    "NICHT als Tatzeit verwendet."
)


#: Die Befundarten der Datenlage. Als Konstante, damit die Oberflaeche sie
#  gegen ihre eigene Aufzaehlung halten kann — ein neuer Befund ohne Platz in
#  der Sicht wuerde sonst aus der Zaehlung fallen (Build 527).
DATENLAGE_BEFUNDE: Tuple[str, ...] = (
    "belegt", "belegt_unvollstaendig", "ohne_tatzeit", "zeitspalte_unlesbar",
    "ohne_zeittabelle", "ohne_forensic_db", "nicht_lesbar",
)

#: Die Befunde, bei denen ein Fristbeginn VORLIEGT (mit oder ohne Einschraenkung).
BEFUNDE_MIT_TATZEIT: Tuple[str, ...] = ("belegt", "belegt_unvollstaendig")


@dataclass(frozen=True)
class CaseTatzeit:
    """Der belegte Tatzeitrahmen eines Falls (oder der Grund, warum keiner da ist)."""
    subject_id: int
    username: str
    frueheste_ts: Optional[int]
    spaeteste_ts: Optional[int]
    quellen: Tuple[str, ...]        # welche Quellen etwas geliefert haben
    befund: str                     # s. DATENLAGE_BEFUNDE
    detail: str
    # Build 527: welche Quellen NICHT lesbar waren, je Eintrag mit dem
    # SQLite-Grund. Das Feld ist auch bei 'belegt_unvollstaendig' gefuellt —
    # gerade dort ist es die eigentliche Information.
    quellen_fehler: Tuple[str, ...] = ()
    # Build 528: Zahl der Zeitwerte AUSSERHALB des Plausibilitaetsrahmens. Sie
    # gehen nicht in die Spanne ein, verschwinden aber auch nicht: eine hohe
    # Zahl deutet darauf, dass eine Spalte etwas anderes fuehrt als eine Zeit.
    unplausible_werte: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id, "username": self.username,
            "frueheste_ts": self.frueheste_ts,
            "spaeteste_ts": self.spaeteste_ts,
            "quellen": list(self.quellen),
            "befund": self.befund, "detail": self.detail,
            "quellen_fehler": list(self.quellen_fehler),
            "unplausible_werte": self.unplausible_werte,
        }


@dataclass(frozen=True)
class LimitationRow:
    """Eine Zeile des Monitors: Tatzeitrahmen + Fristeinschaetzung."""
    tatzeit: CaseTatzeit
    assessment: LimitationAssessment

    def to_dict(self) -> Dict[str, Any]:
        out = self.tatzeit.to_dict()
        out.update(self.assessment.to_dict())
        # 'befund' kommt in BEIDEN Teilen vor und bedeutet Verschiedenes: im
        # Tatzeitteil die Datenlage, in der Einschaetzung die Rechtsfolge. Die
        # Datenlage wird deshalb umbenannt statt ueberschrieben — ein
        # ueberschriebener Befund waere ein verlorener Beleg.
        out["tatzeit_befund"] = self.tatzeit.befund
        out["tatzeit_detail"] = self.tatzeit.detail
        out["befund"] = self.assessment.befund
        out["detail"] = self.tatzeit.detail
        return out


@dataclass(frozen=True)
class LimitationReport:
    """Der Monitor als Ganzes."""
    stichtag: str
    vorwarn_tage: int
    aussage_moeglich: bool
    verweigerungsgrund: Optional[str]
    params_stand: str
    params_bestaetigt: bool
    params_bestaetigt_von: Optional[str]
    params_bestaetigt_am: Optional[str]
    vorgabe_tatbestaende: Tuple[str, ...]
    vorbehalte: Tuple[str, ...]
    hinweise: Tuple[str, ...]
    faelle_gesamt: int
    zaehler: Dict[str, int]         # je Ampelzustand
    datenlage: Dict[str, int]       # je Tatzeit-Befund
    rows: Tuple[LimitationRow, ...]
    # Build 527: das AGGREGAT der Lesefehler — Fehlertext -> Anzahl Faelle.
    # Es ersetzt den Protokoll-Schwall durch EINE nachpruefbare Zahl und macht
    # den systematischen Ausfall sichtbar: '162 Faelle, ein und derselbe
    # Fehler' ist eine Schema-Aussage, '1 Fall' waere eine Datei-Aussage.
    quellenfehler: Dict[str, int] = field(default_factory=dict)
    faelle_mit_quellenfehler: int = 0
    # Build 528: Summe der Zeitwerte ausserhalb des Plausibilitaetsrahmens und
    # die Zahl der betroffenen Faelle. Systematisch hohe Werte sind ein Hinweis
    # darauf, dass eine Spalte etwas anderes fuehrt als eine Zeit.
    unplausible_werte: int = 0
    faelle_mit_unplausiblen: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stichtag": self.stichtag,
            "vorwarn_tage": self.vorwarn_tage,
            "aussage_moeglich": self.aussage_moeglich,
            "verweigerungsgrund": self.verweigerungsgrund,
            "params_stand": self.params_stand,
            "params_bestaetigt": self.params_bestaetigt,
            "params_bestaetigt_von": self.params_bestaetigt_von,
            "params_bestaetigt_am": self.params_bestaetigt_am,
            "vorgabe_tatbestaende": list(self.vorgabe_tatbestaende),
            "vorbehalte": list(self.vorbehalte),
            "hinweise": list(self.hinweise),
            "faelle_gesamt": self.faelle_gesamt,
            "zaehler": dict(self.zaehler),
            "datenlage": dict(self.datenlage),
            "quellenfehler": dict(self.quellenfehler),
            "faelle_mit_quellenfehler": self.faelle_mit_quellenfehler,
            "unplausible_werte": self.unplausible_werte,
            "faelle_mit_unplausiblen": self.faelle_mit_unplausiblen,
            "plausibel_von": PLAUSIBEL_VON, "plausibel_bis": PLAUSIBEL_BIS,
            "datenlage_befunde": list(DATENLAGE_BEFUNDE),
            "rows": [r.to_dict() for r in self.rows],
        }


def _tag_iso(ts: int) -> str:
    """Unix-Sekunden -> ISO-Tag (UTC). Nur fuer Meldungstexte."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,)).fetchone() is not None


def read_tatzeit(path: Path, subject_id: int, username: str) -> CaseTatzeit:
    """
    Liest den Tatzeitrahmen aus EINER forensic_<uid>.db (read-only).

    Reine E/A-Funktion ohne Rechtsbewertung — dadurch getrennt testbar. Sie
    wirft NICHT: jeder Fehlerfall wird zu einem benannten Befund, damit der
    Fall in der Liste BLEIBT.

    Build 527: ein Lesefehler an einer Zeitquelle wird MITGEFUEHRT
    (quellen_fehler) und aendert den Befund. Frueher verschwand er in einer
    Protokollzeile, und der Fall sah entweder unverdaechtig ('belegt') oder
    falsch beschrieben ('kein Zeitstempel gesetzt') aus.
    """
    if not path.exists():
        return CaseTatzeit(
            subject_id=subject_id, username=username, frueheste_ts=None,
            spaeteste_ts=None, quellen=(), befund="ohne_forensic_db",
            detail="forensic_%d.db fehlt (%s)" % (subject_id, path.parent))

    try:
        con = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    except sqlite3.Error as exc:
        return CaseTatzeit(
            subject_id=subject_id, username=username, frueheste_ts=None,
            spaeteste_ts=None, quellen=(), befund="nicht_lesbar",
            detail="nicht oeffenbar: %s" % exc)

    try:
        vorhanden = [q for q in ZEITQUELLEN if _table_exists(con, q[0])]
        if not vorhanden:
            return CaseTatzeit(
                subject_id=subject_id, username=username, frueheste_ts=None,
                spaeteste_ts=None, quellen=(), befund="ohne_zeittabelle",
                detail="weder %s vorhanden"
                       % " noch ".join(q[0] for q in ZEITQUELLEN))

        frueheste: Optional[int] = None
        spaeteste: Optional[int] = None
        quellen: List[str] = []
        fehler: List[str] = []
        unplausibel = 0
        for tabelle, spalte, _beleg in vorhanden:
            try:
                # EINE Abfrage, ein Tabellendurchlauf: Spanne der PLAUSIBLEN
                # Werte UND die Zahl der verworfenen. Der Filter steht in SQL
                # und nicht in Python, damit auch bei Millionen Zeilen nur zwei
                # Zahlen zurueckkommen; die verworfenen werden GEZAEHLT und
                # spaeter ausgewiesen (kein stilles Verwerfen).
                row = con.execute(
                    "SELECT MIN(CASE WHEN %s BETWEEN ? AND ? THEN %s END), "
                    "       MAX(CASE WHEN %s BETWEEN ? AND ? THEN %s END), "
                    "       SUM(CASE WHEN %s IS NOT NULL "
                    "                AND (%s < ? OR %s > ?) THEN 1 ELSE 0 END) "
                    "FROM %s"
                    % (spalte, spalte, spalte, spalte, spalte, spalte, spalte,
                       tabelle),
                    (PLAUSIBEL_VON, PLAUSIBEL_BIS, PLAUSIBEL_VON,
                     PLAUSIBEL_BIS, PLAUSIBEL_VON, PLAUSIBEL_BIS)).fetchone()
            except sqlite3.Error as exc:
                # EINE unlesbare Quelle darf die andere nicht mitreissen — aber
                # sie darf auch nicht in einer Protokollzeile verschwinden. Der
                # Grund faehrt am Fall MIT (Build 527). Protokolliert wird hier
                # nur auf DEBUG; die Zusammenfassung macht LimitationRepo EINMAL
                # je Abruf (bei 162 Dateien waren es sonst 162 Warnungen).
                fehler.append("%s.%s: %s" % (tabelle, spalte, exc))
                logger.debug("limitation: %s.%s in %s nicht lesbar (%s)",
                             tabelle, spalte, path.name, exc)
                continue
            if row is not None and row[2]:
                unplausibel += int(row[2])
            if row is None or row[0] is None:
                # Kein plausibler Wert in dieser Quelle. Das ist KEIN Fehler der
                # Quelle — sie kann schlicht leer sein — und wird deshalb hier
                # nicht vermerkt; die Zahl der unplausiblen Werte steht bereits
                # in 'unplausibel'.
                continue
            lo, hi = int(row[0]), int(row[1])
            frueheste = lo if frueheste is None else min(frueheste, lo)
            spaeteste = hi if spaeteste is None else max(spaeteste, hi)
            quellen.append("%s.%s" % (tabelle, spalte))

        if spaeteste is None:
            # ZWEI VERSCHIEDENE LAGEN, die frueher beide 'ohne_tatzeit' hiessen.
            if fehler:
                return CaseTatzeit(
                    subject_id=subject_id, username=username,
                    frueheste_ts=None, spaeteste_ts=None, quellen=(),
                    befund="zeitspalte_unlesbar",
                    detail="KEINE Zeitquelle lesbar — es ist damit UNBEKANNT, "
                           "ob Zeitstempel vorliegen: %s" % "; ".join(fehler),
                    quellen_fehler=tuple(fehler),
                    unplausible_werte=unplausibel)
            return CaseTatzeit(
                subject_id=subject_id, username=username, frueheste_ts=None,
                spaeteste_ts=None, quellen=(), befund="ohne_tatzeit",
                detail="Zeittabelle(n) und Spalten lesbar (%s), aber kein "
                       "einziger Zeitstempel im Plausibilitaetsrahmen "
                       "(%d Wert(e) lagen ausserhalb und sind nicht "
                       "eingegangen)"
                       % (", ".join(q[0] for q in vorhanden), unplausibel),
                unplausible_werte=unplausibel)

        if fehler:
            # DER GEFAEHRLICHE FALL: es gibt einen Wert, aber nicht aus allen
            # Quellen. Er ist NIE einfach 'belegt'.
            return CaseTatzeit(
                subject_id=subject_id, username=username,
                frueheste_ts=frueheste, spaeteste_ts=spaeteste,
                quellen=tuple(quellen), befund="belegt_unvollstaendig",
                detail="Fristbeginn NUR aus %s gebildet; nicht lesbar war: %s. "
                       "Fehlen dadurch SPAETERE Handlungen, ist der "
                       "Fristbeginn zu frueh angesetzt und die Frist zu kurz "
                       "gerechnet — der Fall erscheint dringender als er ist."
                       % (", ".join(quellen), "; ".join(fehler)),
                quellen_fehler=tuple(fehler),
                unplausible_werte=unplausibel)

        return CaseTatzeit(
            subject_id=subject_id, username=username, frueheste_ts=frueheste,
            spaeteste_ts=spaeteste, quellen=tuple(quellen), befund="belegt",
            detail="Fristbeginn = spaeteste belegte Tathandlung (§ 78a StGB); "
                   "frueheste Handlung zum Vergleich mitgefuehrt",
            unplausible_werte=unplausibel)
    except sqlite3.Error as exc:
        return CaseTatzeit(
            subject_id=subject_id, username=username, frueheste_ts=None,
            spaeteste_ts=None, quellen=(), befund="nicht_lesbar",
            detail="nicht lesbar: %s" % exc)
    finally:
        try:
            con.close()
        except sqlite3.Error:               # pragma: no cover
            pass


class LimitationRepo:
    """
    Read-Model: Fristenmonitor ueber alle Faelle.

    coordinator.db liefert die Fallliste (subject_id, username), die
    forensic_<uid>.db den Fristbeginn. NICHT scope-behaftet — die Auswahl der
    Faelle trifft der Endpunkt; Fristenkontrolle ist eine Leitungsaufgabe.
    """

    def __init__(self, con: sqlite3.Connection, forensic_dir: Any) -> None:
        self._con = con
        self._forensic = Path(forensic_dir)

    def _cases(self, subject_ids: Optional[Sequence[int]] = None
               ) -> List[Tuple[int, str]]:
        if subject_ids is not None and len(subject_ids) == 0:
            # Eine LEERE Auswahl ist eine Auswahl und bedeutet ausdruecklich
            # NICHT "alle" (Muster coverage_repo.py:82-83).
            return []
        sql = "SELECT subject_id, username FROM cases"
        args: Tuple[Any, ...] = ()
        if subject_ids is not None:
            sql += " WHERE subject_id IN (%s)" % ",".join(
                "?" * len(subject_ids))
            args = tuple(int(s) for s in subject_ids)
        sql += " ORDER BY subject_id"
        return [(int(r[0]), str(r[1] or "?"))
                for r in self._con.execute(sql, args).fetchall()]

    def compute(self, *, params: LimitationParams, now_ts: int,
                vorwarn_tage: int = DEFAULT_VORWARN_TAGE,
                subject_ids: Optional[Sequence[int]] = None
                ) -> LimitationReport:
        """
        Der ganze Monitor. Rein lesend, deterministisch fuer festes now_ts.

        SORTIERUNG: das Dringlichste zuerst — 'ueberschritten' vor 'knapp' vor
        dem Rest, innerhalb dessen nach Restlaufzeit. Faelle OHNE Aussage
        ('ohne_tatzeit', 'ohne_fassung') stehen NICHT am Ende, sondern direkt
        hinter den knappen: sie sind ungeprueft, und Ungeprueftes darf nicht
        unter Unverdaechtiges rutschen (Grundregel 1).
        """
        rows: List[LimitationRow] = []
        zaehler: Dict[str, int] = {}
        datenlage: Dict[str, int] = {}
        quellenfehler: Dict[str, int] = {}
        mit_fehler = 0
        unplausibel_gesamt = 0
        mit_unplausiblen = 0

        for subject_id, username in self._cases(subject_ids):
            pfad = self._forensic / ("forensic_%d.db" % subject_id)
            tatzeit = read_tatzeit(pfad, subject_id, username)
            datenlage[tatzeit.befund] = datenlage.get(tatzeit.befund, 0) + 1
            if tatzeit.unplausible_werte:
                unplausibel_gesamt += tatzeit.unplausible_werte
                mit_unplausiblen += 1
            if tatzeit.quellen_fehler:
                mit_fehler += 1
                for eintrag in tatzeit.quellen_fehler:
                    quellenfehler[eintrag] = quellenfehler.get(eintrag, 0) + 1
            a = assess_limitation(tatzeit_ts=tatzeit.spaeteste_ts,
                                  params=params, now_ts=now_ts,
                                  vorwarn_tage=vorwarn_tage)
            zaehler[a.ampel] = zaehler.get(a.ampel, 0) + 1
            rows.append(LimitationRow(tatzeit=tatzeit, assessment=a))

        rang = {"ueberschritten": 0, "knapp": 1, "ohne_tatzeit": 2,
                "ohne_fassung": 3, "ruht": 4, "offen": 5, "keine_aussage": 6}
        rows.sort(key=lambda r: (
            rang.get(r.assessment.ampel, 9),
            # Build 527: bei gleicher Ampel steht das EINGESCHRAENKT Belegte
            # vorn. Wer die Liste von oben liest, sieht zuerst die Zeilen, deren
            # Zahl unter Vorbehalt steht.
            0 if r.tatzeit.quellen_fehler else 1,
            r.assessment.restlaufzeit_tage
            if r.assessment.restlaufzeit_tage is not None else 10 ** 9,
            r.tatzeit.subject_id))

        # EINE Zusammenfassung statt einer Warnung je Datei. Ein Fehler, der bei
        # ALLEN Faellen gleich lautet, ist ein Schema-Befund und keine
        # Dateistoerung — genau das soll die Zeile sagen.
        if quellenfehler:
            logger.warning(
                "limitation: bei %d von %d Faellen war eine Zeitquelle nicht "
                "lesbar. Aufschluesselung: %s", mit_fehler, len(rows),
                "; ".join("%s (%dx)" % (k, v)
                          for k, v in sorted(quellenfehler.items())))

        grund = params.verweigerungsgrund()

        # Der Lesefehler gehoert in die HINWEISE der Antwort, nicht nur ins
        # Protokoll: die Sicht und der Export zeigen die Hinweise, das
        # Serverprotokoll sieht niemand, der die Liste liest.
        hinweise = [HINWEIS_QUELLEN, HINWEIS_FETCHED_AT]
        if unplausibel_gesamt:
            hinweise.insert(0,
                "%d Zeitwert(e) in %d Fall/Faellen lagen AUSSERHALB des "
                "Plausibilitaetsrahmens (%s bis %s) und sind nicht in die "
                "Fristrechnung eingegangen. Sie sind damit nicht verschwiegen, "
                "aber auch nicht verwertet — eine hohe Zahl deutet darauf, dass "
                "eine Spalte etwas anderes fuehrt als eine Zeit."
                % (unplausibel_gesamt, mit_unplausiblen,
                   _tag_iso(PLAUSIBEL_VON), _tag_iso(PLAUSIBEL_BIS)))
        if quellenfehler:
            hinweise.insert(0,
                "ACHTUNG — DATENLAGE EINGESCHRAENKT: bei %d von %d Faellen war "
                "eine Zeitquelle nicht lesbar (%s). Faelle mit dem Befund "
                "'belegt_unvollstaendig' tragen einen Fristbeginn, der NUR aus "
                "den lesbaren Quellen gebildet ist; Faelle mit "
                "'zeitspalte_unlesbar' tragen gar keinen. Vor einer "
                "Fristentscheidung ist die Ursache zu klaeren."
                % (mit_fehler, len(rows),
                   "; ".join("%s (%dx)" % (k, v)
                             for k, v in sorted(quellenfehler.items()))))
        hinweise = tuple(hinweise)

        # Der Stichtag kommt aus der Rechenschicht, damit es genau EINE Stelle
        # gibt, die Unix-Sekunden in einen Kalendertag umrechnet.
        stichtag = assess_limitation(
            tatzeit_ts=None, params=params, now_ts=now_ts,
            vorwarn_tage=vorwarn_tage).stichtag

        return LimitationReport(
            stichtag=stichtag, vorwarn_tage=max(0, int(vorwarn_tage)),
            aussage_moeglich=(grund is None), verweigerungsgrund=grund,
            params_stand=params.stand, params_bestaetigt=params.bestaetigt,
            params_bestaetigt_von=params.bestaetigt_von,
            params_bestaetigt_am=params.bestaetigt_am,
            vorgabe_tatbestaende=params.vorgabe_tatbestaende,
            vorbehalte=params.vorbehalte,
            hinweise=hinweise,
            faelle_gesamt=len(rows), zaehler=zaehler, datenlage=datenlage,
            rows=tuple(rows), quellenfehler=quellenfehler,
            faelle_mit_quellenfehler=mit_fehler,
            unplausible_werte=unplausibel_gesamt,
            faelle_mit_unplausiblen=mit_unplausiblen)
