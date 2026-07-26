# =============================================================================
# management/deadlines/tatzeit_anker.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A, Build 535)
# =============================================================================
# Zweck:
#   Liest aus EINER evidence_<uid>.db die von einer Ermittlerin FESTGESTELLTE
#   Tatzeit und macht daraus den Anker fuer die Fristberechnung.
#
#   Reine E/A-Funktion ohne Rechtsbewertung — getrennt von limitation_repo,
#   damit sie einzeln pruefbar ist (Muster read_tatzeit, limitation_repo.py:453).
#   Sie WIRFT NICHT: jeder Fehlerfall wird zu einem benannten Befund, damit der
#   Fall in der Liste BLEIBT. Ein verschwundener Fall ist der gefaehrlichste
#   (Grundregel 1).
#
# ── DIE ENTSCHEIDUNG, DIE HIER DRINSTECKT (mc 2026-07-26) ────────────────────
#
#   Liegen zu einem Fall MEHRERE festgestellte Tatzeitraeume vor, verankert die
#   FRUEHESTE Beendigung die Frist — MIN(COALESCE(bis_ts, von_ts)). Die
#   spaeteste wird MITGEFUEHRT und ausgewiesen, rechnet aber nicht.
#
#   DAS WEICHT BEWUSST VON DER REGEL FUER AKTIVITAETSDATEN AB, und der Grund
#   gehoert hierher, damit es niemand spaeter "geradezieht": Bei den
#   Aktivitaetsquellen nimmt der Monitor die SPAETESTE Handlung
#   (limitation.py:306-312 — "§ 78a StGB knuepft an die BEENDIGUNG der Tat an;
#   die spaeteste belegte Handlung ist die fristrechtlich guenstigste BELEGTE
#   Tatsache"). Fuer festgestellte Tatzeiten hat mc am 2026-07-26 anders
#   entschieden: der Fall soll eher zu frueh als zu spaet auffallen. Eine zu
#   fruehe Warnung kostet Aufmerksamkeit, eine zu spaete kostet das Verfahren.
#
#   Damit die uebergangene Zahl nicht unsichtbar wird — was der eigentliche
#   Einwand gegen MIN war —, faehrt 'spaeteste_beendigung' in jeder Zeile mit,
#   und 'anzahl_hart' sagt, wie viele Zeitraeume dahinterstehen. Wer die Liste
#   liest, sieht also, DASS mehrere vorliegen und WELCHE Spanne sie aufspannen.
#
# ── WELCHE ANGABEN UEBERHAUPT RECHNEN ────────────────────────────────────────
#
#   (1) NUR HARTE Angaben (art='hart'). Unscharfe fuehren per CHECK keine
#       Zeitwerte (m002) — aus ihnen laesst sich nichts rechnen. Sie werden
#       trotzdem GEZAEHLT und ausgewiesen ('anzahl_weich'): eine unscharfe
#       Angabe ist eine Erkenntnis, und ihr Vorhandensein soll man sehen.
#   (2) NUR AKTIVE Angaben (annotation_tatzeit.deleted_at IS NULL).
#   (3) NUR aus Annotationen der Kategorien §§ 176/184. Festlegung mc
#       (Uebergabe §2.2 Nr. 11): in anderen Kategorien ist die Tatzeit
#       "optional setzbar, aber NICHT in die Fristberechnung eingehend".
#       Auch diese werden GEZAEHLT ('anzahl_fremde_kategorie') — sonst waere
#       die Entscheidung unsichtbar und saehe aus wie ein Datenverlust.
#
# ── DIE AUFLOESUNG AUF DIE AKTUELLE ANNOTATION (die heikle Stelle) ───────────
#
#   Die Kategorie steht auf 'annotations', nicht auf 'annotation_tatzeit'. Sie
#   muss von der AKTUELLEN Fassung der Annotation gelesen werden, nicht von
#   der, an der die Tatzeit haengt: aendert eine Ermittlerin die Kategorie von
#   176 auf PERSON, hoert die Tatzeit auf zu rechnen — und umgekehrt.
#
#   'annotations' ist append-only versioniert; die aktuelle Fassung ist die mit
#   deleted_at IS NULL (db/evidence_db.py:884-919). Aufgeloest wird deshalb
#   ueber 'annotation_local_id' (die LOGISCHE Annotation), mit Rueckfall auf
#   'annotation_id' — denn local_id ist optional ("anonyme Einmal-Annotation",
#   db/evidence_db.py:871).
#
#   FOLGE, DIE BEABSICHTIGT IST: Wird die Annotation GELOESCHT, gibt es keine
#   aktive Fassung mehr, der JOIN greift nicht, und die Tatzeit rechnet nicht
#   mehr. Das ist richtig — eine geloeschte Annotation soll keine Frist
#   verankern. Die Tatzeitzeile selbst bleibt in der Datenbank stehen; sie ist
#   Beweismittel und wird nie entfernt.
#
# Version: v0.8.535 · Build: 535 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

#: Die Kategorien, deren Tatzeit in die Fristberechnung eingeht.
#
#  EINGEFROREN AN DIESER STELLE und NICHT aus db/evidence_db.VALID_CATEGORIES
#  abgeleitet: dort steht die MENGE aller zulaessigen Kategorien, hier die
#  fachliche Auswahl "welche betreffen die §§ 176/184". Das sind zwei
#  verschiedene Aussagen, und die zweite darf sich nicht aendern, nur weil die
#  erste erweitert wird.
#
#  ZWEI PRUEFUNGEN HALTEN DAS ZUSAMMEN (tests/test_limitation_tatzeit.py):
#    - TA01: jeder Code hier ist auch in VALID_CATEGORIES (faengt Tippfehler).
#    - TA02: die Liste ist WORTGLEICH mit MAHN_KATEGORIEN in
#            toolbar/tatzeit_panel.js. Liefen sie auseinander, mahnte die Maske
#            dort, wo nichts gerechnet wird — oder schwiege dort, wo es zaehlt.
RELEVANTE_KATEGORIEN: Tuple[str, ...] = ("CAT_176", "CAT_184")

#: Die Befunde dieses Lesers. Als Konstante, damit die Oberflaeche sie gegen
#  ihre eigene Aufzaehlung halten kann (Muster DATENLAGE_BEFUNDE, Build 527).
TATZEIT_BEFUNDE: Tuple[str, ...] = (
    "festgestellt",         # mindestens eine harte, aktive, relevante Angabe
    "ohne_feststellung",    # Tabelle da, aber nichts Rechenbares darin
    "ohne_tabelle",         # evidence-DB da, aber m002 nicht angewandt
    "ohne_evidence_db",     # Datei fehlt
    "nicht_lesbar",         # Datei da, aber nicht oeffenbar/abfragbar
    "nicht_geprueft",       # kein evidence-Verzeichnis uebergeben (s. u.)
)

#: Der Befund, wenn gar nicht nachgesehen wurde. Er ist AUSDRUECKLICH ein
#  eigener Wert und nicht 'ohne_feststellung': "nachgesehen und nichts
#  gefunden" und "nicht nachgesehen" duerfen in einer Ermittlungsakte nicht
#  gleich aussehen.
BEFUND_NICHT_GEPRUEFT = "nicht_geprueft"


@dataclass(frozen=True)
class TatzeitAnker:
    """Die festgestellte Tatzeit eines Falls (oder der Grund, warum keine da ist)."""

    subject_id: int
    befund: str
    detail: str
    #: Zahl der harten, aktiven Angaben in relevanten Kategorien.
    anzahl_hart: int = 0
    #: MIN(COALESCE(bis_ts, von_ts)) — DAS IST DER ANKER (mc 2026-07-26).
    frueheste_beendigung: Optional[int] = None
    #: MAX(COALESCE(bis_ts, von_ts)) — wird ausgewiesen, rechnet NICHT.
    spaeteste_beendigung: Optional[int] = None
    #: Unscharfe Angaben — festgehalten, aber nicht rechenbar.
    anzahl_weich: int = 0
    #: Angaben in Kategorien ausserhalb §§ 176/184 — bewusst nicht gerechnet.
    anzahl_fremde_kategorie: int = 0
    #: Lesefehler, die den Fall NICHT aus der Liste werfen duerfen.
    fehler: Tuple[str, ...] = ()

    @property
    def hat_anker(self) -> bool:
        """True, wenn eine festgestellte Tatzeit die Frist verankern kann."""
        return self.frueheste_beendigung is not None

    @property
    def mehrdeutig(self) -> bool:
        """
        True, wenn mehr als eine harte Angabe vorliegt UND sie verschiedene
        Beendigungen tragen. Nur dann ist die Auswahl 'frueheste' eine
        ENTSCHEIDUNG und nicht bloss die einzige Zahl — und nur dann muss die
        Oberflaeche darauf hinweisen.
        """
        return (self.anzahl_hart > 1 and
                self.frueheste_beendigung is not None and
                self.spaeteste_beendigung is not None and
                self.frueheste_beendigung != self.spaeteste_beendigung)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tatzeit_feststellung_befund": self.befund,
            "tatzeit_feststellung_detail": self.detail,
            "tatzeit_anzahl_hart": self.anzahl_hart,
            "tatzeit_frueheste_beendigung": self.frueheste_beendigung,
            "tatzeit_spaeteste_beendigung": self.spaeteste_beendigung,
            "tatzeit_anzahl_weich": self.anzahl_weich,
            "tatzeit_anzahl_fremde_kategorie": self.anzahl_fremde_kategorie,
            "tatzeit_mehrdeutig": self.mehrdeutig,
            "tatzeit_fehler": list(self.fehler),
        }


def _tag(ts: Optional[int]) -> str:
    """Unix-Sekunden -> ISO-Tag (UTC). Nur fuer Meldungstexte.

    Bewusst dieselbe Form wie _tag_iso in limitation_repo.py — zwei
    Datumsschreibweisen in einer Antwort waeren eine Fehlerquelle beim Lesen.
    """
    if ts is None:
        return "—"
    from datetime import datetime, timezone
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date().isoformat()


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,)).fetchone() is not None


#: Der JOIN auf die AKTUELLE Fassung der Annotation (s. Modulkopf).
#  Als Konstante, weil ihn drei Abfragen brauchen und eine abweichende Kopie
#  genau die Art Fehler waere, die man erst in der Akte bemerkt.
_JOIN_AKTIVE_ANNOTATION = """
    JOIN "annotations" a
      ON ( t."annotation_local_id" IS NOT NULL
           AND a."local_id" = t."annotation_local_id"
           AND a."deleted_at" IS NULL )
      OR ( t."annotation_local_id" IS NULL
           AND a."id" = t."annotation_id"
           AND a."deleted_at" IS NULL )
"""

_PLATZHALTER = ",".join("?" * len(RELEVANTE_KATEGORIEN))

#: Die Anker-Abfrage. COALESCE(bis_ts, von_ts) ist die BEENDIGUNG: ist das Ende
#  bekannt, gilt es; sonst der Beginn — mehr ist nicht belegt. Der Ausdruck
#  kann nicht NULL werden, weil ein CHECK aus m002 fuer art='hart' mindestens
#  einen der beiden Werte erzwingt (m002:190).
_SQL_HART = """
SELECT COUNT(*) AS n,
       MIN(COALESCE(t."bis_ts", t."von_ts")) AS frueheste,
       MAX(COALESCE(t."bis_ts", t."von_ts")) AS spaeteste
FROM "annotation_tatzeit" t
""" + _JOIN_AKTIVE_ANNOTATION + """
WHERE t."deleted_at" IS NULL
  AND t."art" = 'hart'
  AND a."category" IN (%s)
""" % _PLATZHALTER

_SQL_WEICH = """
SELECT COUNT(*) AS n
FROM "annotation_tatzeit" t
""" + _JOIN_AKTIVE_ANNOTATION + """
WHERE t."deleted_at" IS NULL
  AND t."art" = 'weich'
  AND a."category" IN (%s)
""" % _PLATZHALTER

_SQL_FREMD = """
SELECT COUNT(*) AS n
FROM "annotation_tatzeit" t
""" + _JOIN_AKTIVE_ANNOTATION + """
WHERE t."deleted_at" IS NULL
  AND a."category" NOT IN (%s)
""" % _PLATZHALTER


def nicht_geprueft(subject_id: int, grund: str) -> TatzeitAnker:
    """
    Der Befund fuer "es wurde gar nicht nachgesehen".

    Eigene Funktion, damit der Aufrufer ihn nicht versehentlich mit einem
    leeren TatzeitAnker verwechselt — der bedeutet "nachgesehen, nichts
    gefunden", und das ist eine ganz andere Aussage.
    """
    return TatzeitAnker(subject_id=subject_id, befund=BEFUND_NICHT_GEPRUEFT,
                        detail=grund)


def read_tatzeit_anker(pfad: Path, subject_id: int) -> TatzeitAnker:
    """
    Liest die festgestellte Tatzeit aus EINER evidence_<uid>.db (read-only).

    Wirft nicht. Jeder Fehler wird zu einem benannten Befund mit Text.
    """
    pfad = Path(pfad)
    if not pfad.exists():
        # KEIN Fehler: eine evidence-DB entsteht erst, wenn eine Ermittlerin
        # den Fall bearbeitet. Der Befund sagt genau das.
        return TatzeitAnker(
            subject_id=subject_id, befund="ohne_evidence_db",
            detail="evidence_%d.db fehlt (%s) — der Fall wurde noch nicht "
                   "bearbeitet." % (subject_id, pfad.parent))

    try:
        con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
    except sqlite3.Error as exc:
        return TatzeitAnker(
            subject_id=subject_id, befund="nicht_lesbar",
            detail="evidence_%d.db nicht oeffenbar: %s" % (subject_id, exc),
            fehler=("oeffnen: %s" % exc,))

    try:
        if not _table_exists(con, "annotation_tatzeit"):
            # m002 nicht angewandt. AUSDRUECKLICH BENANNT: eine leere Antwort
            # saehe aus wie "nichts festgestellt", und der Unterschied
            # entscheidet darueber, ob jemand nachsieht.
            return TatzeitAnker(
                subject_id=subject_id, befund="ohne_tabelle",
                detail="Tabelle 'annotation_tatzeit' fehlt — die "
                       "evidence-Migration m002 ist auf dieser Datei nicht "
                       "angewandt. Es ist NICHT gesagt, dass nichts "
                       "festgestellt wurde.")
        if not _table_exists(con, "annotations"):
            return TatzeitAnker(
                subject_id=subject_id, befund="nicht_lesbar",
                detail="Tabelle 'annotations' fehlt — das ist keine "
                       "evidence_<uid>.db.",
                fehler=("annotations fehlt",))

        fehler = []
        args = tuple(RELEVANTE_KATEGORIEN)

        try:
            r = con.execute(_SQL_HART, args).fetchone()
            anzahl_hart = int(r[0] or 0)
            frueheste = int(r[1]) if r[1] is not None else None
            spaeteste = int(r[2]) if r[2] is not None else None
        except sqlite3.Error as exc:
            # Die HARTE Abfrage ist die, aus der gerechnet wird. Faellt sie
            # aus, darf der Fall NICHT so aussehen, als sei nichts festgestellt.
            logger.debug("tatzeit_anker: harte Abfrage in %s: %s",
                         pfad.name, exc)
            return TatzeitAnker(
                subject_id=subject_id, befund="nicht_lesbar",
                detail="Die Tatzeit-Abfrage ist fehlgeschlagen: %s" % exc,
                fehler=("hart: %s" % exc,))

        # Die beiden Zaehlungen sind BEIWERK. Faellt eine aus, ist das kein
        # Grund, den Anker zu verwerfen — aber der Grund faehrt mit.
        try:
            anzahl_weich = int(
                con.execute(_SQL_WEICH, args).fetchone()[0] or 0)
        except sqlite3.Error as exc:
            anzahl_weich = 0
            fehler.append("weich: %s" % exc)
        try:
            anzahl_fremd = int(
                con.execute(_SQL_FREMD, args).fetchone()[0] or 0)
        except sqlite3.Error as exc:
            anzahl_fremd = 0
            fehler.append("fremde Kategorie: %s" % exc)

        if anzahl_hart == 0:
            teile = ["keine festgestellte Tatzeit in den Kategorien %s"
                     % ", ".join(RELEVANTE_KATEGORIEN)]
            if anzahl_weich:
                teile.append("%d unscharfe Angabe(n) vorhanden — sie werden "
                             "festgehalten, aber nicht gerechnet" % anzahl_weich)
            if anzahl_fremd:
                teile.append("%d Angabe(n) in anderen Kategorien — bewusst "
                             "nicht gerechnet" % anzahl_fremd)
            return TatzeitAnker(
                subject_id=subject_id, befund="ohne_feststellung",
                detail="; ".join(teile), anzahl_weich=anzahl_weich,
                anzahl_fremde_kategorie=anzahl_fremd, fehler=tuple(fehler))

        detail = ("%d festgestellte(r) Tatzeitraum/-raeume; verankert wird die "
                  "FRUEHESTE Beendigung (%s)" % (anzahl_hart, _tag(frueheste)))
        if frueheste != spaeteste:
            # DIE UEBERGANGENE ZAHL GEHOERT IN DEN TEXT. Sie war der einzige
            # Einwand gegen die MIN-Regel; unsichtbar waere sie genau der
            # Fehler, den mc mit "beide ausweisen" vermeiden wollte. Und sie
            # steht HIER, damit die Sicht sie WORTGLEICH uebernehmen kann und
            # keine zweite Formulierung entsteht.
            detail += ("; NICHT verankert wurde die spaeteste Beendigung %s"
                       % _tag(spaeteste))
        if anzahl_weich:
            detail += "; %d unscharfe Angabe(n) nicht gerechnet" % anzahl_weich
        if anzahl_fremd:
            detail += ("; %d Angabe(n) in anderen Kategorien nicht gerechnet"
                       % anzahl_fremd)

        return TatzeitAnker(
            subject_id=subject_id, befund="festgestellt", detail=detail,
            anzahl_hart=anzahl_hart, frueheste_beendigung=frueheste,
            spaeteste_beendigung=spaeteste, anzahl_weich=anzahl_weich,
            anzahl_fremde_kategorie=anzahl_fremd, fehler=tuple(fehler))
    finally:
        try:
            con.close()
        except sqlite3.Error:
            pass
