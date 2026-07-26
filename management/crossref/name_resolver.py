# =============================================================================
# management/crossref/name_resolver.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Namensaufloesung
# =============================================================================
# Zweck (Auftrag mc 2026-07-26):
#   "Unsere Ermittler sind mit den Namen der Forennutzer vertraut, aber nicht
#   mit den user_id oder subject_id." Dieses Modul loest beide Richtungen auf:
#
#     RUECKWAERTS  subject_id -> Benutzername   (aufloesen)
#     VORWAERTS    Name       -> subject_id(s)  (suchen)
#
#   Es ist REIN LESEND und beruehrt keine Beweismitteldatenbank.
#
# DIE SCHLUESSELFRAGE, OHNE DIE DAS GANZE MODUL FALSCH WAERE:
#   Ist 'known_users.user_id' aus der default.db dasselbe wie die 'subject_id'
#   der Fallakte? JA — fuer Realnutzer, und nur die stehen dort.
#   BELEG: Entscheidung "Ermittlungsschluessel subject_id fuer Nutzer ohne
#   users.id" vom 2026-07-20, §3: "Realnutzer (user_id bekannt):
#   subject_id = users.id — unveraendert". Und die default.db wird aus genau
#   dieser Tabelle befuellt: aiw_sqlite_prepper/stage1/phase_b_exporter.py,
#   Schritt 1 — "Export aller Nutzer aus MariaDB users -> id, username".
#   Es wird also NICHT umgerechnet, und es darf auch nicht umgerechnet werden.
#
# WAS known_users NICHT ENTHAELT — und warum das hier steht:
#   Die GEISTER (Namen ohne Forenkonto; Erstlauf 2026-07-20: 552.334 von
#   795.972 Namen) bekommen ihre subject_id aus 'prefix + mat_usernames.id'
#   und liegen damit im Band oberhalb 1.000.000.000. Sie stehen in MariaDB
#   (mat_usernames / mat_subject_map) und sind in KEINER SQLite-Datei dieses
#   Servers abgebildet — der Prepper exportiert nach default.db ausschliesslich
#   'users'. 'known_aliases' wird dort sogar ausdruecklich LEER angelegt
#   ("keine MariaDB-Quelle", phase_b_exporter.py:1571).
#
#   FOLGE, DIE DIE OBERFLAECHE SAGEN MUSS: ein Name, der nur in den
#   100a-Anmeldungen oder in Erwaehnungen vorkommt, ist ueber dieses Modul
#   NICHT zu finden, solange er nicht in einem Fall oder im Aliaskatalog steht.
#   Ein Leerbefund heisst hier also "in den ABGEFRAGTEN Quellen nicht
#   gefunden" und NICHT "gibt es nicht". Der Unterschied ist der ganze
#   Unterschied (Grundregel 1); die Antwort traegt ihn in 'quellen_hinweis'.
#
# DIE KASKADE (Festlegung mc 2026-07-26):
#   Erst die FALLAKTE (coordinator.db 'cases'), und nur wenn dort nichts
#   gefunden wird, die FORENKONTEN (default.db 'known_users').
#   Begruendung des Auftraggebers: die Fallakte ist die Arbeitsmenge; wer dort
#   einen Treffer hat, meint fast immer diesen.
#
#   MEINE ERGAENZUNG, DIE DIE KASKADE NICHT AUFHEBT (und die mc in einer Zeile
#   streichen kann): die NICHT abgefragte Quelle wird trotzdem GEZAEHLT und die
#   Zahl mitgeliefert ('weitere_treffer'). Angezeigt wird weiterhin nur die
#   erste Stufe. Grund: eine Kaskade, die schweigt, sieht aus wie ein
#   vollstaendiges Ergebnis — und der gesuchte Zweitaccount ist genau der
#   Treffer, den sie verschweigen wuerde. Eine Zahl daneben kostet eine
#   COUNT-Abfrage und nimmt der Kaskade nichts.
#
# MINDESTLAENGE 4 ZEICHEN fuer die Suche in known_users:
#   Die Tabelle hat in diesem Fall rund 477.000 Zeilen, und eine
#   Enthaelt-Suche ('%x%') kann KEINEN Index benutzen — sie liest die ganze
#   Tabelle. Die Schwelle ist aus db/default_db.py:300-302 uebernommen (dort
#   mit derselben Begruendung), damit beide Suchen sich gleich verhalten.
#   Sie gilt NICHT fuer die Fallakte (rund 163 Zeilen) und NICHT fuer die
#   Rueckwaerts-Aufloesung (Primaerschluessel-Zugriff).
#
# BEFUND ZUR PROTOKOLLIERUNG (2026-07-26, nicht von mir zu beheben):
#   db/default_db.py:284 behauptet im Kommentar einen Index
#   'known_users_username_idx ON known_users(username COLLATE NOCASE)'.
#   Das DDL des Preppers legt ihn OHNE NOCASE an
#   (phase_b_exporter.py:220: "ON known_users (username)"). Zwei Aussagen
#   ueber dieselbe Tatsache; die falsche steht im Kommentar. Wirkung: die
#   case-insensitive Suche kann den Index auch bei einer Praefixsuche nicht
#   nutzen. Das ist ein Leistungs-, kein Richtigkeitsproblem — gemeldet, nicht
#   behoben (fremde Zone, Parallelbetrieb Welle 3 §3).
#
# Version: v0.8.600 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: Die Quellen, in der Reihenfolge der Kaskade. Als Konstante, damit die
#  Oberflaeche ihre eigene Aufzaehlung dagegen halten kann.
QUELLEN: Tuple[str, ...] = ("fallakte", "forenkonto")

#: Klartext je Quelle — EINMAL hier, damit Server und Sicht nicht
#  auseinanderlaufen.
QUELLE_LABEL: Dict[str, str] = {
    "fallakte": "Fallakte (in Bearbeitung)",
    "forenkonto": "Forenkonto (globale Namensliste)",
    "aliaskatalog": "Aliaskatalog",
    "nicht_gefunden": "in den abgefragten Quellen nicht gefunden",
}

#: Mindestlaenge fuer die Suche in known_users (Begruendung im Kopf).
MIN_SUCHLAENGE = 4

#: Obergrenze der zurueckgegebenen Treffer je Quelle. Sie ist eine
#  ANZEIGEgrenze, keine Wahrheitsgrenze: wird sie erreicht, sagt die Antwort
#  das ausdruecklich ('gekuerzt': True) und nennt die Gesamtzahl. Eine still
#  gekuerzte Trefferliste waere eine Auslassung (Grundregel 1).
STANDARD_LIMIT = 50

#: Der Hinweis, der in JEDER Antwort steht. Er ist der Unterschied zwischen
#  "gibt es nicht" und "hier nicht gesucht" (siehe Kopfkommentar).
QUELLEN_HINWEIS = (
    "Abgefragt werden die Fallakte (coordinator.db 'cases') und die globale "
    "Namensliste der Forenkonten (default.db 'known_users'). NICHT erfasst "
    "sind Namen ohne Forenkonto — etwa solche, die nur in den Anmeldungen der "
    "100a-Massnahme oder in Erwaehnungen vorkommen; fuer sie gibt es auf "
    "diesem Server keine globale Quelle. Ein Leerbefund bedeutet daher 'in "
    "den abgefragten Quellen nicht gefunden', nicht 'gibt es nicht'."
)


def _tabelle_da(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,)).fetchone() is not None


def _entschaerft(text: str) -> str:
    """
    LIKE-Sonderzeichen unschaedlich machen.

    Ohne das wuerde die Eingabe '%' zum Platzhalter und die Suche lieferte die
    ganze Tabelle — bei 477.000 Zeilen ein Ergebnis, das aussieht wie ein
    Treffer und keiner ist. (Dasselbe Muster wie SubjectAliasRepo.search.)
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class NameTreffer:
    """EIN Treffer der Vorwaertssuche."""
    subject_id: int
    name: str
    quelle: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {"subject_id": self.subject_id, "name": self.name,
                "quelle": self.quelle,
                "quelle_label": QUELLE_LABEL.get(self.quelle, self.quelle),
                "detail": self.detail}


@dataclass(frozen=True)
class SuchErgebnis:
    """
    Das Ergebnis EINER Vorwaertssuche.

    'quelle' ist die Stufe der Kaskade, die geantwortet hat.
    'weitere_treffer' nennt je NICHT abgefragter Quelle die Zahl der Treffer,
    die dort laegen — angezeigt wird sie nicht (siehe Kopfkommentar).
    """
    begriff: str
    quelle: str
    treffer: Tuple[NameTreffer, ...]
    gesamt: int
    gekuerzt: bool
    weitere_treffer: Dict[str, int] = field(default_factory=dict)
    hinweise: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "begriff": self.begriff,
            "quelle": self.quelle,
            "quelle_label": QUELLE_LABEL.get(self.quelle, self.quelle),
            "treffer": [t.to_dict() for t in self.treffer],
            "gesamt": self.gesamt,
            "gekuerzt": self.gekuerzt,
            "weitere_treffer": dict(self.weitere_treffer),
            "hinweise": list(self.hinweise),
            "quellen_hinweis": QUELLEN_HINWEIS,
        }


@dataclass(frozen=True)
class Aufloesung:
    """
    Das Ergebnis EINER Rueckwaerts-Aufloesung (subject_id -> Name).

    'name' ist None, wenn keine Quelle etwas wusste — dann traegt 'quelle' den
    Wert 'nicht_gefunden'. Es wird KEIN Platzhaltername erfunden.
    """
    subject_id: int
    name: Optional[str]
    quelle: str
    detail: str
    #: Namen desselben Kontos aus dem ALIASKATALOG. Sie stehen NEBEN der
    #  Aufloesung und ersetzen sie nicht: ein Alias ist eine ermittelte
    #  Erkenntnis, der Kontoname eine gesicherte Tatsache. Beides zu einer
    #  Zeile zu verruehren wuerde den Unterschied einebnen.
    aliasse: Tuple[str, ...] = ()
    hinweise: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "name": self.name,
            "gefunden": self.name is not None,
            "quelle": self.quelle,
            "quelle_label": QUELLE_LABEL.get(self.quelle, self.quelle),
            "detail": self.detail,
            "aliasse": list(self.aliasse),
            "hinweise": list(self.hinweise),
            "quellen_hinweis": QUELLEN_HINWEIS,
        }


class NameResolver:
    """
    Namensaufloesung ueber Fallakte und globale Forenkonten-Liste.

    'con'      — READ-ONLY Verbindung zur coordinator.db (der Aufrufer oeffnet
                 und schliesst sie).
    'default_db_path' — Pfad der default.db. Sie wird JE ABFRAGE kurz
                 read-only geoeffnet und wieder geschlossen: sie ist eine
                 Nachschlagequelle, keine Arbeitsdatenbank, und eine offene
                 Verbindung auf einem Netzlaufwerk ueber die Lebensdauer des
                 Servers zu halten hat sich in diesem Projekt schon einmal
                 geraecht (Build 408/409, WAL auf Netzlaufwerk).
                 Fehlt die Datei, ist das KEIN Fehler, sondern ein BENANNTER
                 Befund: die Fallakte antwortet weiter.
    """

    def __init__(self, con: sqlite3.Connection,
                 default_db_path: Optional[Any] = None) -> None:
        self._con = con
        self._con.row_factory = sqlite3.Row
        self._default_db = (Path(default_db_path)
                            if default_db_path else None)

    # ------------------------------------------------------------ default.db
    def _default_con(self) -> Tuple[Optional[sqlite3.Connection], str]:
        """
        (Verbindung, Hinweis). Verbindung ist None, wenn die default.db fehlt
        oder nicht lesbar ist — mit BENANNTEM Grund, nie stillschweigend.
        """
        if self._default_db is None:
            return None, ("Keine default.db konfiguriert — die globale "
                          "Namensliste wurde NICHT abgefragt.")
        if not self._default_db.exists():
            return None, ("default.db nicht gefunden (%s) — die globale "
                          "Namensliste wurde NICHT abgefragt."
                          % self._default_db)
        try:
            con = sqlite3.connect("file:%s?mode=ro" % self._default_db,
                                  uri=True)
            con.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            return None, ("default.db nicht lesbar (%s) — die globale "
                          "Namensliste wurde NICHT abgefragt." % exc)
        try:
            # sqlite3.connect oeffnet die Datei NICHT; ein beschaedigter Inhalt
            # faellt erst bei der ersten Abfrage auf. Diese Lehre stammt aus
            # Build 534 (uid_stats_repo, Test US05) und wird hier von Anfang an
            # beherzigt: die Pruefung steht VOR jeder Nutzung.
            if not _tabelle_da(con, "known_users"):
                con.close()
                return None, ("default.db enthaelt keine Tabelle "
                              "'known_users' — die globale Namensliste wurde "
                              "NICHT abgefragt.")
        except sqlite3.Error as exc:
            con.close()
            return None, ("default.db nicht lesbar (%s) — die globale "
                          "Namensliste wurde NICHT abgefragt." % exc)
        return con, ""

    # ----------------------------------------------------------- Rueckwaerts
    def aufloesen(self, subject_id: int) -> Aufloesung:
        """
        subject_id -> Benutzername. Kaskade: Fallakte, dann Forenkonten.

        Wirft NICHT: jede Stoerung wird zu einem benannten Hinweis, damit die
        Eingabemaske arbeitsfaehig bleibt.
        """
        sid = int(subject_id)
        hinweise: List[str] = []
        aliasse = self._aliasse(sid)

        # Stufe 1: die Fallakte.
        try:
            row = self._con.execute(
                "SELECT username, status FROM cases WHERE subject_id = ?",
                (sid,)).fetchone()
        except sqlite3.Error as exc:
            row = None
            hinweise.append("Fallakte nicht lesbar: %s" % exc)
        if row is not None and (row["username"] or "").strip():
            return Aufloesung(
                subject_id=sid, name=str(row["username"]),
                quelle="fallakte",
                detail="Fall in der Fallakte (Status: %s)"
                       % (row["status"] or "?"),
                aliasse=aliasse, hinweise=tuple(hinweise))
        if row is not None:
            # Der Fall EXISTIERT, fuehrt aber keinen Namen. Das ist etwas
            # anderes als 'kein Fall' und wird auch anders gesagt.
            hinweise.append("Der Fall existiert in der Fallakte, fuehrt dort "
                            "aber keinen Benutzernamen.")

        # Stufe 2: die globale Namensliste.
        con, hinweis = self._default_con()
        if con is None:
            if hinweis:
                hinweise.append(hinweis)
        else:
            try:
                r = con.execute(
                    "SELECT username FROM known_users WHERE user_id = ?",
                    (sid,)).fetchone()
                if r is not None and (r["username"] or "").strip():
                    return Aufloesung(
                        subject_id=sid, name=str(r["username"]),
                        quelle="forenkonto",
                        detail="Forenkonto aus der globalen Namensliste "
                               "(known_users)",
                        aliasse=aliasse, hinweise=tuple(hinweise))
            except sqlite3.Error as exc:
                hinweise.append("known_users nicht abfragbar: %s" % exc)
            finally:
                con.close()

        # Nichts gefunden. KEIN erfundener Platzhalter.
        if sid > 1000000000:
            # Der Geisterbereich (Entscheidung 2026-07-20, §3). Diese Zahl ist
            # kein Zufall und darf dem Anwender nicht als "unbekannt"
            # verkauft werden — sie sagt ihm, WARUM nichts gefunden wurde.
            hinweise.append(
                "Die Kennung liegt im Band der 'Geisternutzer' (oberhalb "
                "1.000.000.000): ein belegter Name OHNE Forenkonto. Solche "
                "Namen stehen nicht in der globalen Namensliste — nur in der "
                "Fallakte, falls der Fall aufgenommen wurde.")
        return Aufloesung(
            subject_id=sid, name=None, quelle="nicht_gefunden",
            detail="Weder in der Fallakte noch in der globalen Namensliste.",
            aliasse=aliasse, hinweise=tuple(hinweise))

    def _aliasse(self, subject_id: int) -> Tuple[str, ...]:
        """AKTIVE Aliasse dieses Kontos (leer, wenn die Tabelle fehlt)."""
        try:
            if not _tabelle_da(self._con, "subject_alias"):
                return ()
            rows = self._con.execute(
                "SELECT alias FROM subject_alias WHERE subject_id = ? "
                "AND is_active = 1 ORDER BY alias_norm ASC",
                (int(subject_id),)).fetchall()
            return tuple(str(r["alias"]) for r in rows)
        except sqlite3.Error as exc:
            logger.warning("Aliasse zu %s nicht lesbar: %s", subject_id, exc)
            return ()

    # -------------------------------------------------------------- Vorwaerts
    def suchen(self, begriff: str,
               limit: int = STANDARD_LIMIT) -> SuchErgebnis:
        """
        Name -> subject_id(s). KASKADE: erst Fallakte, dann Forenkonten
        (Festlegung mc 2026-07-26).

        Ein leerer Begriff liefert eine leere Liste — wer nichts sucht, soll
        nicht versehentlich alles bekommen (Muster SubjectAliasRepo.search).
        """
        term = (begriff or "").strip()
        if not term:
            return SuchErgebnis(begriff="", quelle="fallakte", treffer=(),
                                gesamt=0, gekuerzt=False)

        hinweise: List[str] = []

        # --- Stufe 1: Fallakte ------------------------------------------------
        fall_treffer, fall_gesamt, fehler = self._suche_fallakte(term, limit)
        if fehler:
            hinweise.append(fehler)

        if fall_treffer:
            # Die Kaskade endet hier. Die zweite Quelle wird NICHT gelistet,
            # aber GEZAEHLT (Begruendung im Kopfkommentar).
            weitere, hinweis2 = self._zaehle_forenkonten(term)
            if hinweis2:
                hinweise.append(hinweis2)
            return SuchErgebnis(
                begriff=term, quelle="fallakte",
                treffer=tuple(fall_treffer), gesamt=fall_gesamt,
                gekuerzt=fall_gesamt > len(fall_treffer),
                weitere_treffer=({"forenkonto": weitere}
                                 if weitere is not None else {}),
                hinweise=tuple(hinweise))

        # --- Stufe 2: Forenkonten --------------------------------------------
        if len(term) < MIN_SUCHLAENGE:
            hinweise.append(
                "Kein Treffer in der Fallakte. Die globale Namensliste wurde "
                "NICHT abgefragt: sie verlangt mindestens %d Zeichen "
                "(rund 477.000 Eintraege, die Suche liest die ganze Tabelle)."
                % MIN_SUCHLAENGE)
            return SuchErgebnis(begriff=term, quelle="fallakte", treffer=(),
                                gesamt=0, gekuerzt=False,
                                hinweise=tuple(hinweise))

        konto_treffer, konto_gesamt, fehler2 = self._suche_forenkonten(
            term, limit)
        if fehler2:
            hinweise.append(fehler2)
        return SuchErgebnis(
            begriff=term, quelle="forenkonto",
            treffer=tuple(konto_treffer), gesamt=konto_gesamt,
            gekuerzt=konto_gesamt > len(konto_treffer),
            hinweise=tuple(hinweise))

    # ------------------------------------------------------------- Teilsuchen
    @staticmethod
    def _rang(name: str, term: str) -> int:
        """
        0 = genau, 1 = beginnt mit, 2 = enthaelt.

        Warum in Python und nicht in SQL: die Sortierung soll fuer BEIDE
        Quellen dieselbe sein, und SQLite muesste dafuer je Zeile drei
        LIKE-Ausdruecke auswerten. Die Menge ist durch das LIMIT ohnehin klein.
        """
        n = (name or "").casefold()
        t = (term or "").casefold()
        if n == t:
            return 0
        if n.startswith(t):
            return 1
        return 2

    def _suche_fallakte(self, term: str, limit: int
                        ) -> Tuple[List[NameTreffer], int, str]:
        muster = "%" + _entschaerft(term) + "%"
        try:
            rows = self._con.execute(
                "SELECT subject_id, username, status FROM cases "
                "WHERE username LIKE ? ESCAPE '\\' COLLATE NOCASE "
                "ORDER BY subject_id ASC", (muster,)).fetchall()
        except sqlite3.Error as exc:
            return [], 0, "Fallakte nicht durchsuchbar: %s" % exc

        treffer = [NameTreffer(
            subject_id=int(r["subject_id"]),
            name=str(r["username"] or ""),
            quelle="fallakte",
            detail="Fall in der Fallakte (Status: %s)" % (r["status"] or "?"),
        ) for r in rows]
        treffer.sort(key=lambda t: (self._rang(t.name, term), t.name.casefold(),
                                    t.subject_id))
        return treffer[:limit], len(treffer), ""

    def _suche_forenkonten(self, term: str, limit: int
                           ) -> Tuple[List[NameTreffer], int, str]:
        con, hinweis = self._default_con()
        if con is None:
            return [], 0, hinweis
        muster = "%" + _entschaerft(term) + "%"
        try:
            # Es wird BEWUSST ein Stueck ueber das Limit hinaus geholt: nur so
            # laesst sich die Gesamtzahl wenigstens als "mehr als N" ausweisen,
            # ohne die Tabelle ein zweites Mal zu lesen. Die genaue Gesamtzahl
            # liefert _zaehle_forenkonten, wo sie gebraucht wird.
            rows = con.execute(
                "SELECT user_id, username FROM known_users "
                "WHERE username LIKE ? ESCAPE '\\' COLLATE NOCASE "
                "LIMIT ?", (muster, max(limit * 4, limit + 1))).fetchall()
        except sqlite3.Error as exc:
            con.close()
            return [], 0, "known_users nicht abfragbar: %s" % exc
        con.close()

        treffer = [NameTreffer(
            subject_id=int(r["user_id"]),
            name=str(r["username"] or ""),
            quelle="forenkonto",
            detail="Forenkonto aus der globalen Namensliste",
        ) for r in rows]
        treffer.sort(key=lambda t: (self._rang(t.name, term), t.name.casefold(),
                                    t.subject_id))
        return treffer[:limit], len(treffer), ""

    def _zaehle_forenkonten(self, term: str
                            ) -> Tuple[Optional[int], str]:
        """
        Zahl der Forenkonten-Treffer, OHNE sie zu listen.

        Nur diese Zahl haelt die Kaskade ehrlich (siehe Kopfkommentar). Unter
        der Mindestlaenge wird NICHT gezaehlt — die Abfrage waere derselbe
        Volldurchlauf, den die Schwelle gerade vermeiden soll; die Antwort
        traegt dann None, und die Sicht sagt "nicht abgefragt" statt "0".
        """
        if len(term) < MIN_SUCHLAENGE:
            return None, ""
        con, hinweis = self._default_con()
        if con is None:
            return None, hinweis
        muster = "%" + _entschaerft(term) + "%"
        try:
            row = con.execute(
                "SELECT COUNT(*) AS n FROM known_users "
                "WHERE username LIKE ? ESCAPE '\\' COLLATE NOCASE",
                (muster,)).fetchone()
            return int(row["n"] or 0), ""
        except sqlite3.Error as exc:
            return None, "known_users nicht zaehlbar: %s" % exc
        finally:
            con.close()
