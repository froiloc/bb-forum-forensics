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
#   einer Zeile, auch wenn er unlesbar ist. Vier Befundarten werden GEZAEHLT und
#   BENANNT:
#     ohne_forensic_db     — Fall in 'cases', aber keine forensic_<uid>.db.
#     ohne_zeittabelle     — Datei da, aber weder uid_posts noch uid_pms_posts.
#     nicht_lesbar         — Datei da, aber nicht oeffenbar/lesbar (mit Grund).
#     ohne_tatzeit         — Tabellen da, aber kein einziger Zeitstempel.
#   Ein Monitor, der solche Faelle weglaesst, saehe nach vollstaendiger Pruefung
#   aus und waere der gefaehrlichste denkbare Beleg.
#
# REIN LESEND: coordinator.db und alle forensic_<uid>.db werden mit
#   file:...?mode=ro geoeffnet (Muster management/reports/reports_repo.py:122).
#   Der Migrationsvorbehalt ab 01.07.2026 ist NICHT beruehrt.
#
# Version: v0.8.524 · Build: 524 · 2026-07-25
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
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
#  Als Konstante, damit ein Test sie gegen den Modulkopf halten kann und eine
#  spaetere Ergaenzung nicht unbemerkt eine neue Quelle einfuehrt.
ZEITQUELLEN: Tuple[Tuple[str, str, str], ...] = (
    ("uid_posts", "posted", "belegt (db/forensic_db.py:401-434)"),
    ("uid_pms_posts", "posted_ts",
     "schwaecherer Beleg — Spaltenname aus Entwicklerangabe 2026-07-15 "
     "(db/forensic_db.py:447-480)"),
)

#: Der Hinweis auf die bekannte Datenluecke. Faehrt in JEDER Antwort mit.
HINWEIS_SHARES = (
    "Teilungsakte (share_id) gehen NICHT in den Fristbeginn ein: fuer geteilte "
    "Dateien existiert in den ausgewerteten Datenbanken kein Zeitstempel, nur "
    "der Zaehler uid_stats.stat_key='shares_total'. Ist eine Teilung die "
    "spaeteste Tathandlung, ist der hier ausgewiesene Fristbeginn ZU FRUEH "
    "angesetzt — die Frist waere also laenger, nicht kuerzer."
)

#: Der Hinweis auf den bewusst NICHT verwendeten Sicherungszeitpunkt.
HINWEIS_FETCHED_AT = (
    "pages.fetched_at (Sicherungszeitpunkt des Scrapers) wird ausdruecklich "
    "NICHT als Tatzeit verwendet."
)


@dataclass(frozen=True)
class CaseTatzeit:
    """Der belegte Tatzeitrahmen eines Falls (oder der Grund, warum keiner da ist)."""
    subject_id: int
    username: str
    frueheste_ts: Optional[int]
    spaeteste_ts: Optional[int]
    quellen: Tuple[str, ...]        # welche Tabellen etwas geliefert haben
    befund: str                     # 'belegt' | 'ohne_forensic_db' |
    #                                 'ohne_zeittabelle' | 'nicht_lesbar' |
    #                                 'ohne_tatzeit'
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id, "username": self.username,
            "frueheste_ts": self.frueheste_ts,
            "spaeteste_ts": self.spaeteste_ts,
            "quellen": list(self.quellen),
            "befund": self.befund, "detail": self.detail,
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
            "rows": [r.to_dict() for r in self.rows],
        }


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
        for tabelle, spalte, _beleg in vorhanden:
            try:
                row = con.execute(
                    "SELECT MIN(%s), MAX(%s) FROM %s WHERE %s IS NOT NULL"
                    % (spalte, spalte, tabelle, spalte)).fetchone()
            except sqlite3.Error as exc:
                # EINE unlesbare Tabelle darf die andere nicht mitreissen; der
                # Grund wird aber vermerkt (kein stiller Teilbefund).
                logger.warning("limitation: %s.%s nicht lesbar (%s)",
                               tabelle, spalte, exc)
                continue
            if row is None or row[0] is None:
                continue
            lo, hi = int(row[0]), int(row[1])
            frueheste = lo if frueheste is None else min(frueheste, lo)
            spaeteste = hi if spaeteste is None else max(spaeteste, hi)
            quellen.append("%s.%s" % (tabelle, spalte))

        if spaeteste is None:
            return CaseTatzeit(
                subject_id=subject_id, username=username, frueheste_ts=None,
                spaeteste_ts=None, quellen=(), befund="ohne_tatzeit",
                detail="Zeittabelle(n) vorhanden (%s), aber kein einziger "
                       "Zeitstempel gesetzt"
                       % ", ".join(q[0] for q in vorhanden))

        return CaseTatzeit(
            subject_id=subject_id, username=username, frueheste_ts=frueheste,
            spaeteste_ts=spaeteste, quellen=tuple(quellen), befund="belegt",
            detail="Fristbeginn = spaeteste belegte Tathandlung (§ 78a StGB); "
                   "frueheste Handlung zum Vergleich mitgefuehrt")
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

        for subject_id, username in self._cases(subject_ids):
            pfad = self._forensic / ("forensic_%d.db" % subject_id)
            tatzeit = read_tatzeit(pfad, subject_id, username)
            datenlage[tatzeit.befund] = datenlage.get(tatzeit.befund, 0) + 1
            a = assess_limitation(tatzeit_ts=tatzeit.spaeteste_ts,
                                  params=params, now_ts=now_ts,
                                  vorwarn_tage=vorwarn_tage)
            zaehler[a.ampel] = zaehler.get(a.ampel, 0) + 1
            rows.append(LimitationRow(tatzeit=tatzeit, assessment=a))

        rang = {"ueberschritten": 0, "knapp": 1, "ohne_tatzeit": 2,
                "ohne_fassung": 3, "ruht": 4, "offen": 5, "keine_aussage": 6}
        rows.sort(key=lambda r: (
            rang.get(r.assessment.ampel, 9),
            r.assessment.restlaufzeit_tage
            if r.assessment.restlaufzeit_tage is not None else 10 ** 9,
            r.tatzeit.subject_id))

        grund = params.verweigerungsgrund()
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
            hinweise=(HINWEIS_SHARES, HINWEIS_FETCHED_AT),
            faelle_gesamt=len(rows), zaehler=zaehler, datenlage=datenlage,
            rows=tuple(rows))
