# =============================================================================
# management/search/search_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B562)
# =============================================================================
# Zweck:
#   FulltextSearchRepo — die Abfrage auf search_index.db. Liefert die
#   Trefferlage (Stufe 1) und die rohen Treffer eines Falls (Grundlage der
#   Stufe 2). Kennt WEDER Rechte NOCH Belege — das liegt im Service
#   (search_service.py); hier wird nur gesucht.
#
#   Grundregel 10: eine Klasse, eine Datei.
#
# ── STUFE 1 IST DIE EIGENTLICHE FUNKTION ────────────────────────────────────
#
#   "Fall 5023 — 3 aktuelle Treffer, 1 ueberholter, Art: Annotation, Zeitraum
#   2024-03 bis 2024-07." KEIN TEXTAUSSCHNITT. Damit ist die
#   ermittlungsentscheidende Frage vollstaendig beantwortet: es gibt etwas, wo
#   es ist, wie viel, und — ueber 'urheber' — MIT WEM MAN DARUEBER REDET. In
#   der Praxis duerfte das in den meisten Faellen genuegen; C braucht oft nicht
#   den Text von B, sondern B als Gespraechspartnerin (Klaerung §4, Modell B).
#
#   DIE DREI FASSUNGEN WERDEN GETRENNT GEZAEHLT und NIE zu einer Zahl addiert
#   (index_vokabular.FASSUNGEN). 'aktuell' ist Arbeitsstand, 'ueberholt' und
#   'zurueckgenommen' sind Historie. Eine gemeinsame Zahl behauptete eine
#   Trefferlage, die es so nicht gibt.
#
# ── DIE BEHANDLUNG DES SUCHBEGRIFFS ─────────────────────────────────────────
#
#   FTS5-MATCH hat eine eigene Abfragesprache (AND/OR/NOT, NEAR, Anfuehrungs-
#   zeichen, '*'). Ein Ermittlerbegriff ist aber kein Ausdruck, sondern ein
#   Wort — und ein Nickname darf jedes Zeichen enthalten. Ein roh
#   durchgereichter Begriff wie 'birnen*mus' oder 'a OR b' wuerde entweder
#   einen Syntaxfehler werfen oder etwas GANZ ANDERES suchen, als der Mensch
#   eingegeben hat. Beides ist unzulaessig: das zweite waere ein Beleg, der
#   eine andere Suche behauptet als die durchgefuehrte.
#
#   Deshalb wird der Begriff IMMER als PHRASE in doppelte Anfuehrungszeichen
#   gesetzt und ein enthaltenes Anfuehrungszeichen verdoppelt — die von FTS5
#   vorgesehene Maskierung. Damit sucht die Anlage genau die Zeichenfolge, die
#   eingegeben wurde, und nichts sonst.
#
#   FOLGE, DIE IN DER SICHT STEHEN MUSS: Es gibt keine Bool-Suche und keine
#   Platzhalter. Das ist eine bewusste Einschraenkung — wer sie loesen will,
#   braucht eine eigene Entscheidung, weil sie die Belegbarkeit der Abfrage
#   beruehrt.
#
# ── DIE TRIGRAM-GRENZE WIRD GEMELDET, NICHT VERSCHWIEGEN ────────────────────
#
#   FTS5-trigram kann nur Muster ab DREI Zeichen bedienen. Ein kuerzerer
#   Begriff faende im Teilstringmodus IMMER nichts — und dieser Leerbefund
#   saehe aus wie 'nichts gefunden'. Der Repo liefert deshalb einen eigenen
#   Befund 'begriff_zu_kurz', den der Service in eine Klartextantwort
#   uebersetzt (Grundregel 1).
#
# Version: v0.8.562 · Build: 562 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from management.search.index_vokabular import (
    FASSUNGEN,
    MIN_TEILSTRING_LAENGE,
    MODUS_TABELLE,
    MODUS_TEILSTRING,
    SATZ_ART_NACH_CODE,
    normalisiere_suchmodus,
)

logger = logging.getLogger(__name__)

#: Obergrenze der aus dem Index gelesenen Saetze JE ABFRAGE.
#  KEINE STILLE KAPPUNG: wird sie erreicht, meldet die Antwort das
#  ausdruecklich ('gekappt': true) samt der Grenze. Eine Trefferlage, die
#  unbemerkt bei 5000 aufhoert, waere eine falsche Trefferlage.
MAX_TREFFER = 5000


class FulltextSearchRepo:
    """Abfrage auf den FTS5-Index (search_index.db). Rein lesend."""

    def __init__(self, index_con: sqlite3.Connection) -> None:
        self._con = index_con

    # --------------------------------------------------------------- Begriff
    @staticmethod
    def phrase(begriff: str) -> str:
        """
        Baut den FTS5-MATCH-Ausdruck: der Begriff als PHRASE.

        Das doppelte Anfuehrungszeichen ist in FTS5 der Phrasenbegrenzer; ein
        im Begriff enthaltenes wird durch Verdopplung maskiert. Damit ist jede
        Eingabe zulaessig und keine wird als Operator gelesen.
        """
        return '"%s"' % str(begriff).replace('"', '""')

    @staticmethod
    def zu_kurz(begriff: str, modus: str) -> bool:
        """True, wenn der Begriff fuer den Teilstringmodus zu kurz ist."""
        return (modus == MODUS_TEILSTRING
                and len(str(begriff).strip()) < MIN_TEILSTRING_LAENGE)

    # --------------------------------------------------------------- Treffer
    def treffer(self, begriff: str, *, modus: str = "wort",
                subject_id: Optional[int] = None,
                limit: int = MAX_TREFFER) -> Dict[str, Any]:
        """
        Rohtreffer aus dem Index — die Grundlage beider Stufen.

        Rueckgabe:
          {'befund': 'ok'|'begriff_zu_kurz'|'index_fehlt',
           'modus': str, 'gekappt': bool, 'grenze': int, 'treffer': [...]}

        Jeder Treffer traegt seinen vollstaendigen Rueckweg zur Quelle. Das
        ist die Voraussetzung dafuer, dass die Anzeige spaeter aus der QUELLE
        kommt und nicht aus dem Index (quellen_verifikation.py).
        """
        modus = normalisiere_suchmodus(modus)
        begriff = (begriff or "").strip()
        if not begriff:
            return {"befund": "begriff_leer", "modus": modus,
                    "gekappt": False, "grenze": limit, "treffer": []}
        if self.zu_kurz(begriff, modus):
            return {"befund": "begriff_zu_kurz", "modus": modus,
                    "gekappt": False, "grenze": limit, "treffer": []}

        tab = MODUS_TABELLE[modus]
        sql = ("SELECT s.satz_id, s.subject_id, s.satz_art, s.quell_tabelle, "
               "       s.quell_spalte, s.quell_schluessel, s.fassung, s.ts, "
               "       s.urheber, s.text "
               "FROM %s f JOIN index_satz s ON s.satz_id = f.rowid "
               "WHERE %s MATCH ?" % (tab, tab))
        args: List[Any] = [self.phrase(begriff)]
        if subject_id is not None:
            sql += " AND s.subject_id = ?"
            args.append(int(subject_id))
        # Feste Ordnung: der Bericht einer Suche muss zweimal gleich aussehen.
        # Bewusst NICHT nach FTS5-Rangfolge ('bm25'): sie ist bei der
        # trigram-Tabelle ohne Aussage, und eine Rangfolge, die je nach Modus
        # etwas anderes bedeutet, waere in einer Akte irrefuehrend.
        sql += " ORDER BY s.subject_id, s.satz_id LIMIT ?"
        args.append(int(limit) + 1)

        try:
            rows = self._con.execute(sql, args).fetchall()
        except sqlite3.OperationalError as exc:
            # Fehlt die Indextabelle, ist der Index nicht aufgebaut. Das ist
            # ein BETRIEBSBEFUND und ausdruecklich kein Leerbefund.
            logger.warning("Suchindex nicht abfragbar: %s", exc)
            return {"befund": "index_fehlt", "modus": modus, "gekappt": False,
                    "grenze": limit, "treffer": [], "detail": str(exc)}

        gekappt = len(rows) > limit
        rows = rows[:limit]
        treffer = [{
            "satz_id": int(r[0]), "subject_id": int(r[1]), "satz_art": r[2],
            "satz_art_label": (SATZ_ART_NACH_CODE[r[2]].label
                               if r[2] in SATZ_ART_NACH_CODE
                               else "unbekannte Satzart (%s)" % r[2]),
            "quell_tabelle": r[3], "quell_spalte": r[4],
            "quell_schluessel": r[5], "fassung": r[6],
            "ts": None if r[7] is None else int(r[7]),
            "urheber": r[8], "text": r[9],
        } for r in rows]
        if gekappt:
            logger.warning("Suche '%s' (%s): Trefferzahl an der Grenze %d "
                           "gekappt — die Antwort weist das aus.",
                           begriff, modus, limit)
        return {"befund": "ok", "modus": modus, "gekappt": gekappt,
                "grenze": limit, "treffer": treffer}

    # ----------------------------------------------------------------- Lage
    def lage(self, begriff: str, *, modus: str = "wort",
             limit: int = MAX_TREFFER) -> Dict[str, Any]:
        """
        STUFE 1 — die Trefferlage je Fall, OHNE Textausschnitt.

        Je Fall: Trefferzahl GETRENNT nach Fassung, die vorkommenden
        Satzarten, der Zeitraum und die Urheber:innen. Der Zeitraum nennt
        ausserdem, wie viele Saetze OHNE Zeitpunkt eingegangen sind — nicht
        jede Quellspalte fuehrt einen, und ein verschwiegener Anteil liesse
        den Zeitraum vollstaendiger aussehen, als er ist.
        """
        roh = self.treffer(begriff, modus=modus, limit=limit)
        if roh["befund"] != "ok":
            return {**roh, "faelle": [], "treffer_gesamt": 0}

        je_fall: Dict[int, Dict[str, Any]] = {}
        for t in roh["treffer"]:
            uid = t["subject_id"]
            e = je_fall.setdefault(uid, {
                "subject_id": uid,
                "nach_fassung": {f: 0 for f in FASSUNGEN},
                "arten": {},
                "urheber": {},
                "von_ts": None, "bis_ts": None, "ohne_ts": 0,
            })
            e["nach_fassung"][t["fassung"]] = \
                e["nach_fassung"].get(t["fassung"], 0) + 1
            e["arten"][t["satz_art"]] = e["arten"].get(t["satz_art"], 0) + 1
            if t["urheber"]:
                e["urheber"][t["urheber"]] = e["urheber"].get(t["urheber"], 0) + 1
            if t["ts"] is None:
                e["ohne_ts"] += 1
            else:
                e["von_ts"] = (t["ts"] if e["von_ts"] is None
                               else min(e["von_ts"], t["ts"]))
                e["bis_ts"] = (t["ts"] if e["bis_ts"] is None
                               else max(e["bis_ts"], t["ts"]))

        faelle = []
        for uid in sorted(je_fall):
            e = je_fall[uid]
            e["treffer_gesamt"] = sum(e["nach_fassung"].values())
            e["arten"] = [
                {"code": k,
                 "label": (SATZ_ART_NACH_CODE[k].label
                           if k in SATZ_ART_NACH_CODE
                           else "unbekannte Satzart (%s)" % k),
                 "count": v}
                for k, v in sorted(e["arten"].items(),
                                   key=lambda kv: (-kv[1], kv[0]))]
            e["urheber"] = [{"kuerzel": k, "count": v}
                            for k, v in sorted(e["urheber"].items(),
                                               key=lambda kv: (-kv[1], kv[0]))]
            faelle.append(e)

        return {**roh, "treffer": None, "faelle": faelle,
                "treffer_gesamt": sum(f["treffer_gesamt"] for f in faelle)}
