# =============================================================================
# management/search/search_service.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Volltextsuche (AP-3E, B562)
# =============================================================================
# Zweck:
#   FulltextSearchService — die Klammer um die beiden Stufen des Modells B.
#   Er prueft die Zweckangabe, holt die Trefferlage, entscheidet je Fall ueber
#   die Sichtbarkeit des Inhalts, verifiziert jeden angezeigten Treffer gegen
#   die Quelle und SCHREIBT DEN BELEG.
#
#   Grundregel 10: eine Klasse, eine Datei. Die drei Bausteine liegen daneben:
#   search_repo.py (Abfrage), quellen_verifikation.py (Nachlesen in der
#   Quelle), release_repo.py (Freigabe/Zuweisung).
#
# ── JEDE ABFRAGE IST EIN BELEG — AUCH DER LEERBEFUND ────────────────────────
#
#   Klaerung AP-3E v0.2 §6 Nr. 1, von mc bestaetigt. Der Leerbefund ist der
#   WICHTIGERE Teil der Regel: ohne ihn liesse sich SPURENFREI SONDIEREN — man
#   probiert Namen durch, und nur die Treffer hinterlassen eine Spur. Das waere
#   die vollstaendige Umgehung der Zweckbindung, um derentwillen es das
#   Freigabemodell ueberhaupt gibt.
#
#   DESHALB WIRD DER BELEG GESCHRIEBEN, BEVOR DAS ERGEBNIS ZURUECKGEHT, und
#   ein Fehlschlag beim Schreiben LAESST DIE ABFRAGE SCHEITERN. Die
#   Gegenrichtung — 'Beleg best effort, Ergebnis kommt trotzdem' — waere ein
#   Suchweg ohne Spur, und genau den soll es nicht geben. (Dieselbe Haltung
#   wie bei der Tatzeit-Beleg-Kette, Entscheidung mc 2026-07-26: die
#   Best-Effort-Variante nach Muster REVIEW_COMMENT_* wurde ausdruecklich
#   verworfen, weil dort ein Fehlschlag nur geloggt wird.)
#
# ── WAS IM BELEG STEHT — UND WARUM DER SUCHBEGRIFF DAZUGEHOERT ─────────────
#
#   Klaerung §6 Nr. 1 zaehlt ausdruecklich auf: "Suchbegriff, Zweckangabe,
#   Trefferzahl, Zeitpunkt, Person". Der SUCHBEGRIFF steht damit IM PAYLOAD —
#   und das ist eine BEWUSSTE AUSNAHME von der Sensibilitaetsregel, die sonst
#   nur Fakten und Textlaengen zulaesst (Muster M018/M022/M027).
#
#   Die Ausnahme ist begruendet: ein Beleg, der nur sagt 'jemand hat nach
#   etwas gesucht', belegt nichts. Die Frage einer Aufsicht lautet 'wonach
#   wurde gesucht, und mit welchem Zweck' — ohne den Begriff ist sie nicht
#   beantwortbar, und die Protokollierung waere ein leeres Ritual.
#
#   DER PREIS IST ZU BENENNEN, NICHT ZU VERSCHWEIGEN: Ein Suchbegriff KANN ein
#   Klarname sein. Damit steht ein Klarname in coordinator.audit_log. Das ist
#   hinnehmbar, weil das audit_log ohnehin der schutzwuerdigste Bestand der
#   Anlage ist und dem Recht 'policy.view'/Leitung vorbehalten bleibt — aber
#   es ist eine Folge, die in der Akte benannt gehoert. DER FREITEXT einer
#   'sonstiges'-Zweckangabe geht dagegen NUR ALS LAENGE in den Beleg: er ist
#   von der Ausnahme NICHT gedeckt.
#
# ── DIE ANTWORT NENNT IMMER IHREN EIGENEN STAND ────────────────────────────
#
#   Klaerung §6 Nr. 4/5: kein stiller Teiltreffer, und der Index ist nie
#   aktueller als sein Stand. Jede Antwort traegt deshalb 'indexstand' mit
#   Indexzeitpunkt, der Zahl der seither veraenderten Datenbanken, den
#   unvollstaendigen Faellen und den noch nie indizierten. Eine Suche, die
#   3 von 40 Datenbanken nicht gelesen hat, sagt das — sonst saehe ein
#   Leerbefund aus wie ein vollstaendiger Befund.
#
# Version: v0.8.562 · Build: 562 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Dict, List, Optional

from management.audit.event_types import EventType
from management.search.index_status import SearchIndexStatus
from management.search.index_vokabular import (
    MIN_TEILSTRING_LAENGE,
    MODUS_BEZEICHNUNG,
    normalisiere_suchmodus,
)
from management.search.quellen_verifikation import (
    BEFUND_BESTAETIGT,
    QuellenVerifikation,
)
from management.search.release_repo import FulltextReleaseRepo
from management.search.search_repo import FulltextSearchRepo
from management.search.zweck_vokabular import ZweckFehler, klartext, pruefe

logger = logging.getLogger(__name__)

STUFE_LAGE = "lage"
STUFE_INHALT = "inhalt"

#: Laenge des angezeigten Ausschnitts je Treffer in Stufe 2.
#  Der Ausschnitt ist eine ANZEIGEHILFE, kein Zitat: wer zitieren will, oeffnet
#  den Fall. Deshalb bewusst knapp — und die Kuerzung wird MARKIERT, damit
#  niemand einen abgeschnittenen Satz fuer den ganzen haelt.
AUSSCHNITT_LAENGE = 400


class FulltextSearchFehler(RuntimeError):
    """Die Abfrage konnte nicht durchgefuehrt oder nicht belegt werden."""


class FulltextSearchService:
    """Stufe 1 und Stufe 2 der falluebergreifenden Volltextsuche."""

    def __init__(self, *, coordinator_con: sqlite3.Connection,
                 index_db: Any, evidence_dir: object,
                 writer: Optional[Any] = None) -> None:
        self._con = coordinator_con
        self._index = index_db
        self._evidence_dir = evidence_dir
        self._writer = writer
        self._repo = FulltextSearchRepo(index_db.verbindung())
        self._release = FulltextReleaseRepo(coordinator_con, writer)
        self._status = SearchIndexStatus(evidence_dir, index_db)

    # ------------------------------------------------------------ Indexstand
    def indexstand(self) -> Dict[str, Any]:
        """
        Der Stand, den JEDE Antwort mitfuehrt (Klaerung §6 Nr. 4/5).

        'belastbar' ist genau dann True, wenn nichts veraendert, nichts neu
        und nichts unvollstaendig ist. Es ist bewusst eine EIGENE Aussage und
        keine Ableitung, die der Leser selbst treffen muss.
        """
        st = self._status.status()
        return {
            "indexzeitpunkt": st["letzter_lauf_at"],
            "verzeichnis_vorhanden": st["verzeichnis_vorhanden"],
            "faelle_im_index": st["faelle_im_index"],
            "faelle_im_verzeichnis": st["faelle_im_verzeichnis"],
            "veraendert_seit_index": len(st["veraendert"]),
            "veraenderte_faelle": st["veraendert"],
            "noch_nie_indiziert": st["neu"],
            "unvollstaendig": st["unvollstaendig"],
            "belastbar": bool(st["aktuell"]),
            "hinweis": self._standhinweis(st),
        }

    @staticmethod
    def _standhinweis(st: Dict[str, Any]) -> str:
        """Der Indexstand im Klartext — fuer Sicht UND Akte."""
        if not st["verzeichnis_vorhanden"]:
            return ("Das Verzeichnis der Beweismitteldatenbanken ist nicht "
                    "erreichbar. Es wurde NICHT nachgesehen — dieser Befund "
                    "ist kein Leerbefund.")
        teile: List[str] = []
        if st["letzter_lauf_at"] is None:
            teile.append("Der Index ist noch nie aufgebaut worden.")
        if st["neu"]:
            teile.append("%d Fall/Faelle sind noch nie indiziert worden."
                         % len(st["neu"]))
        if st["veraendert"]:
            teile.append("%d Datenbank(en) haben sich seit dem Indexlauf "
                         "geaendert; ihre Trefferlage ist nicht belegt "
                         "aktuell." % len(st["veraendert"]))
        if st["unvollstaendig"]:
            teile.append("%d Fall/Faelle konnten beim Indexlauf nicht "
                         "vollstaendig gelesen werden." % len(
                             st["unvollstaendig"]))
        return (" ".join(teile) if teile
                else "Der Index ist belegt aktuell und vollstaendig.")

    # ------------------------------------------------------------------ Beleg
    def _belege(self, *, stufe: str, begriff: str, modus: str,
                zweck_code: str, zweck_freitext: Optional[str],
                trefferzahl: int, faelle: int, person_id: int,
                subject_id: Optional[int] = None,
                befund: str = "ok") -> int:
        """
        Schreibt FULLTEXT_SEARCHED. Schlaegt das fehl, SCHEITERT DIE ABFRAGE.

        Der fachliche 'Write' ist hier leer — es gibt keine Fachtabelle, in
        die eine Suche schreibt. Der Beleg IST der Vorgang. audited_write
        wird trotzdem benutzt, damit derselbe, einzige Schreibweg gilt wie
        ueberall sonst (Hash-Kette, BEGIN IMMEDIATE, keine Sonderbehandlung).
        """
        if self._writer is None:
            raise FulltextSearchFehler(
                "Kein CoordinatorWriter gesetzt — eine Suche ohne Beleg wird "
                "nicht durchgefuehrt. Auch der Leerbefund ist zu belegen, "
                "sonst liesse sich spurenfrei sondieren.")
        if person_id is None:
            raise FulltextSearchFehler(
                "Ohne Handelnden wird nicht gesucht.")

        def _w(_con: sqlite3.Connection) -> Dict[str, Any]:
            # SUCHBEGRIFF IM KLARTEXT — bewusste Ausnahme von der
            # Sensibilitaetsregel (Begruendung im Modulkopf). Der FREITEXT der
            # Zweckangabe dagegen NUR als Laenge.
            return {
                "stufe": stufe,
                "begriff": begriff,
                "modus": modus,
                "zweck_code": zweck_code,
                "zweck_freitext_len": len(zweck_freitext or ""),
                "trefferzahl": int(trefferzahl),
                "faelle_mit_treffern": int(faelle),
                "subject_id": subject_id,
                "befund": befund,
            }

        return self._writer.audited_write(
            do_write=_w, event_type=EventType.FULLTEXT_SEARCHED,
            actor_id=int(person_id), target_type="fulltext_search",
            target_id=(None if subject_id is None else str(subject_id)))

    # ---------------------------------------------------------------- Stufe 1
    def lage(self, *, begriff: str, person_id: int, zweck_code: str,
             zweck_freitext: Optional[str] = None,
             modus: str = "wort") -> Dict[str, Any]:
        """
        STUFE 1 — Trefferlage je Fall, OHNE Textausschnitt.

        Frei fuer alle, die 'evidence.fulltext_search' haben (E-2, kein
        Scope). Je Fall wird zusaetzlich ausgewiesen, OB der Inhalt sichtbar
        waere und WARUM — damit die Sicht sofort den richtigen Knopf anbieten
        kann ('Inhalt anzeigen' oder 'Freigabe anfragen') und die Ermittlerin
        nicht erst in eine Sperre laeuft.
        """
        code, freitext = self._zweck(zweck_code, zweck_freitext)
        modus = normalisiere_suchmodus(modus)
        begriff = (begriff or "").strip()

        erg = self._repo.lage(begriff, modus=modus)
        faelle = erg.get("faelle", [])
        for f in faelle:
            f["sichtbarkeit"] = self._release.darf_inhalt_sehen(
                subject_id=f["subject_id"], person_id=person_id)

        seq = self._belege(
            stufe=STUFE_LAGE, begriff=begriff, modus=modus, zweck_code=code,
            zweck_freitext=freitext, trefferzahl=erg.get("treffer_gesamt", 0),
            faelle=len(faelle), person_id=person_id, befund=erg["befund"])

        return {
            "stufe": STUFE_LAGE,
            "begriff": begriff,
            "modus": modus,
            "modus_klartext": MODUS_BEZEICHNUNG.get(modus, modus),
            "zweck_code": code,
            "zweck_klartext": klartext(code, freitext),
            "befund": erg["befund"],
            "befund_klartext": self._befundtext(erg["befund"], modus),
            "gekappt": erg.get("gekappt", False),
            "grenze": erg.get("grenze"),
            "treffer_gesamt": erg.get("treffer_gesamt", 0),
            "faelle": faelle,
            "indexstand": self.indexstand(),
            "audit_seq": seq,
        }

    # ---------------------------------------------------------------- Stufe 2
    def inhalt(self, *, begriff: str, subject_id: int, person_id: int,
               zweck_code: str, zweck_freitext: Optional[str] = None,
               modus: str = "wort") -> Dict[str, Any]:
        """
        STUFE 2 — die Treffer EINES Falls mit Textausschnitt.

        Zulaessig, wenn der Fall der Person zugewiesen ist ODER eine gueltige
        Freigabe vorliegt (E-1). Sonst wird NICHTS geliefert — aber der
        Versuch WIRD BELEGT: ein abgewiesener Zugriffsversuch ist der Vorgang,
        den eine Aufsicht am ehesten sehen will.

        JEDER angezeigte Ausschnitt kommt AUS DER QUELLE und ist gegen sie
        verifiziert (Klaerung §6 Nr. 3). Treffer, deren Quelle abweicht,
        verschwunden oder nicht lesbar ist, werden MIT BEFUND aufgefuehrt und
        OHNE Text — nicht weggelassen.
        """
        code, freitext = self._zweck(zweck_code, zweck_freitext)
        modus = normalisiere_suchmodus(modus)
        begriff = (begriff or "").strip()
        uid = int(subject_id)

        sicht = self._release.darf_inhalt_sehen(subject_id=uid,
                                                person_id=person_id)
        if not sicht["erlaubt"]:
            seq = self._belege(
                stufe=STUFE_INHALT, begriff=begriff, modus=modus,
                zweck_code=code, zweck_freitext=freitext, trefferzahl=0,
                faelle=0, person_id=person_id, subject_id=uid,
                befund="abgewiesen_" + str(sicht["grund"]))
            return {"stufe": STUFE_INHALT, "subject_id": uid,
                    "erlaubt": False, "sichtbarkeit": sicht,
                    "begriff": begriff, "modus": modus,
                    "zweck_code": code,
                    "zweck_klartext": klartext(code, freitext),
                    "treffer": [], "indexstand": self.indexstand(),
                    "audit_seq": seq}

        erg = self._repo.treffer(begriff, modus=modus, subject_id=uid)
        roh = erg.get("treffer", [])
        treffer: List[Dict[str, Any]] = []
        bestaetigt = 0
        with QuellenVerifikation(self._evidence_dir) as pruefer:
            for t in roh:
                v = pruefer.pruefe(
                    subject_id=t["subject_id"], satz_art=t["satz_art"],
                    quell_tabelle=t["quell_tabelle"],
                    quell_spalte=t["quell_spalte"],
                    quell_schluessel=t["quell_schluessel"],
                    index_text=t["text"])
                eintrag = {k: t[k] for k in
                           ("subject_id", "satz_art", "satz_art_label",
                            "quell_tabelle", "quell_spalte",
                            "quell_schluessel", "fassung", "ts", "urheber")}
                eintrag["verifikation"] = v["befund"]
                eintrag["verifikation_klartext"] = v["klartext"]
                if v["befund"] == BEFUND_BESTAETIGT:
                    bestaetigt += 1
                    text = v["quelltext"] or ""
                    eintrag["ausschnitt"] = text[:AUSSCHNITT_LAENGE]
                    eintrag["ausschnitt_gekuerzt"] = \
                        len(text) > AUSSCHNITT_LAENGE
                else:
                    # KEIN Text aus dem Index — der Index wird nie zitiert.
                    eintrag["ausschnitt"] = None
                    eintrag["ausschnitt_gekuerzt"] = False
                treffer.append(eintrag)

        seq = self._belege(
            stufe=STUFE_INHALT, begriff=begriff, modus=modus, zweck_code=code,
            zweck_freitext=freitext, trefferzahl=len(treffer), faelle=1,
            person_id=person_id, subject_id=uid, befund=erg["befund"])

        nicht_bestaetigt = len(treffer) - bestaetigt
        return {
            "stufe": STUFE_INHALT,
            "subject_id": uid,
            "erlaubt": True,
            "sichtbarkeit": sicht,
            "begriff": begriff,
            "modus": modus,
            "modus_klartext": MODUS_BEZEICHNUNG.get(modus, modus),
            "zweck_code": code,
            "zweck_klartext": klartext(code, freitext),
            "befund": erg["befund"],
            "befund_klartext": self._befundtext(erg["befund"], modus),
            "gekappt": erg.get("gekappt", False),
            "treffer": treffer,
            "treffer_gesamt": len(treffer),
            "gegen_quelle_bestaetigt": bestaetigt,
            "nicht_bestaetigt": nicht_bestaetigt,
            "verifikationshinweis": (
                "Alle Treffer sind gegen die Quelle bestaetigt."
                if nicht_bestaetigt == 0 else
                "%d von %d Treffern konnten NICHT gegen die Quelle bestaetigt "
                "werden; fuer sie wird kein Text angezeigt. Der Index ist ein "
                "Hilfsmittel und wird nie zitiert." % (nicht_bestaetigt,
                                                       len(treffer))),
            "indexstand": self.indexstand(),
            "audit_seq": seq,
        }

    # --------------------------------------------------------------- Helfer
    @staticmethod
    def _zweck(code: object, freitext: Optional[str]):
        """Zweckangabe pruefen — ohne sie wird NICHT gesucht (E-3)."""
        try:
            return pruefe(code, freitext)
        except ZweckFehler as exc:
            raise FulltextSearchFehler(str(exc)) from exc

    @staticmethod
    def _befundtext(befund: str, modus: str) -> str:
        """Der Abfragebefund im Klartext — kein stilles 'nichts gefunden'."""
        if befund == "ok":
            return "Abfrage durchgefuehrt."
        if befund == "begriff_leer":
            return "Es wurde kein Suchbegriff angegeben."
        if befund == "begriff_zu_kurz":
            return ("Die Teilstringsuche braucht mindestens %d Zeichen (harte "
                    "Eigenschaft des trigram-Verfahrens). Es wurde NICHT "
                    "gesucht — dies ist kein Leerbefund. Fuer kuerzere "
                    "Begriffe die Wortsuche verwenden."
                    % MIN_TEILSTRING_LAENGE)
        if befund == "index_fehlt":
            return ("Der Suchindex ist nicht vorhanden oder unvollstaendig "
                    "angelegt. Es wurde NICHT gesucht — dies ist kein "
                    "Leerbefund. Abhilfe: "
                    "'python -m management.search.index_cli --auffrischen'.")
        return "Unbekannter Befund: %s (Modus %s)." % (befund, modus)
