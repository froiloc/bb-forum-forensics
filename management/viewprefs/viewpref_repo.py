# =============================================================================
# management/viewprefs/viewpref_repo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3G (Build 545)
# =============================================================================
# Zweck:
#   Lesen und Schreiben der persoenlichen Ansichtseinstellung
#   (person_view_pref, M037). Lesen ohne Schreiber, Schreiben ausschliesslich
#   ueber CoordinatorWriter — Muster QsRepo/MentoringNotesRepo.
#
# ── EINE PERSON SCHREIBT NUR IHRE EIGENE EINSTELLUNG ────────────────────────
#
#   Es gibt hier KEINEN Scope und KEINE Vertretung, auch nicht fuer die
#   Leitung. Das ist eine bewusste Verengung: eine Vorliebe ist keine
#   Fallakte, an die man zur Vertretung heranmuessen koennte. Wer die
#   Oberflaeche einer anderen Person umbauen koennte, koennte ihr auch die
#   Eskalationssicht wegnehmen — und genau das soll niemand koennen ausser
#   ihr selbst, sichtbar und rueckholbar.
#
# ── UNBEKANNTE SCHLUESSEL WERDEN BENANNT, NICHT VERSCHLUCKT ────────────────
#
#   Beim SCHREIBEN wird ein unbekannter Schluessel abgewiesen (400 mit
#   Nennung) — er darf gar nicht erst in die Datenbank.
#
#   Beim LESEN kann er trotzdem auftauchen: wenn eine Sicht spaeter aus dem
#   Cockpit verschwindet, zeigen gespeicherte Zeilen ins Leere. Sie werden
#   dann NICHT stillschweigend uebergangen, sondern in 'unbekannt'
#   ausgewiesen. Grundregel 1 gilt auch fuer Zeilen, die nur noch Ballast
#   sind: wer sie loescht, soll das entscheiden und nicht die Ladefunktion.
#
# ── DIE REIHENFOLGE STEHT IM ARRAY, NICHT IN EINEM ZAEHLERFELD ─────────────
#
#   Der Aufrufer schickt eine LISTE; ihre Reihenfolge IST die Reihenfolge.
#   Eine vom Browser mitgeschickte 'position' waere eine zweite Wahrheit, die
#   mit der Listenfolge streiten kann. Die Position entsteht hier, beim
#   Schreiben, aus enumerate() — an genau einer Stelle.
#
# ── VOLLSTAENDIGES ERSETZEN, KEIN TEILWEISES AENDERN ──────────────────────
#
#   Ein Speichervorgang ersetzt die Einstellung einer Art VOLLSTAENDIG
#   (DELETE + INSERT in EINER Transaktion). Der Grund ist die Ordnung: bei
#   einem teilweisen Update muesste jemand entscheiden, wohin die nicht
#   genannten Elemente rutschen — und jede Antwort darauf waere geraten. Ein
#   vollstaendiger Satz ist ausserdem das, was die Oberflaeche ohnehin hat.
#
# ── EIN AUDIT-BELEG JE ART, NICHT JE ZEILE UND NICHT JE ZIEHEN ─────────────
#
#   Je Speichervorgang und Art genau ein Eintrag im audit_log. Je Zeile waere
#   Rauschen (40 Sichten = 40 Belege fuer einen Klick); ein Sammelbeleg ueber
#   beide Arten waere zu grob, weil Navigationsordnung und Kachelauswahl
#   getrennt betrachtet werden koennen. Der Payload traegt den VOLLSTAENDIGEN
#   Zustand nach der Aenderung — damit ist aus der Kette allein rekonstruierbar,
#   wie die Oberflaeche einer Person zu einem Zeitpunkt eingerichtet war.
#
# Version: v0.8.545 · Build: 545 · 2026-07-26
# =============================================================================

from __future__ import annotations

import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional, Sequence

from management.audit.event_types import EventType
from management.gateway.coordinator_writer import CoordinatorWriter, WriteUnit
from management.viewprefs import viewpref_katalog as kat

logger = logging.getLogger(__name__)


class ViewPrefFehler(Exception):
    """Unzulaessige Eingabe oder fehlender Schreibweg."""


class ViewPrefRepo:
    """Lesen/Schreiben von person_view_pref."""

    def __init__(self, con: sqlite3.Connection,
                 writer: Optional[CoordinatorWriter] = None) -> None:
        self._con = con
        self._writer = writer

    # ------------------------------------------------------------- Hilfen ---
    def _require_writer(self) -> CoordinatorWriter:
        if self._writer is None:
            raise ViewPrefFehler(
                "Kein Schreibweg: ViewPrefRepo wurde ohne CoordinatorWriter "
                "gebaut. Ohne ihn gaebe es eine Aenderung ohne Beleg.")
        return self._writer

    @staticmethod
    def _pruefe_art(art: str) -> str:
        if art not in kat.ARTEN:
            raise ViewPrefFehler(
                "Unbekannte Art '%s'. Zulaessig: %s."
                % (art, ", ".join(kat.ARTEN)))
        return art

    @staticmethod
    def _pruefe_eintraege(art: str,
                          eintraege: Sequence[Any]) -> List[Dict[str, Any]]:
        """
        Prueft die Liste und gibt sie normalisiert zurueck.

        Abgewiesen wird ALLES, was nicht eindeutig ist — unbekannte
        Schluessel, Doppelungen, falsche Typen. Ein Speichervorgang, der die
        Haelfte annimmt und den Rest verwirft, waere genau die stille
        Teilverarbeitung, die Grundregel 1 verbietet.
        """
        if not isinstance(eintraege, (list, tuple)):
            raise ViewPrefFehler(
                "Fuer '%s' wird eine Liste erwartet." % art)

        raus: List[Dict[str, Any]] = []
        gesehen: Dict[str, int] = {}
        unbekannt: List[str] = []
        for i, e in enumerate(eintraege):
            if isinstance(e, str):
                key, sichtbar = e, True          # Kurzform: nur der Schluessel
            elif isinstance(e, dict):
                key = e.get("key")
                sichtbar = e.get("sichtbar", True)
            else:
                raise ViewPrefFehler(
                    "Eintrag %d ist weder Zeichenkette noch Objekt." % i)
            if not isinstance(key, str) or not key.strip():
                raise ViewPrefFehler(
                    "Eintrag %d hat keinen brauchbaren Schluessel." % i)
            key = key.strip()
            if not isinstance(sichtbar, bool):
                raise ViewPrefFehler(
                    "Eintrag '%s': 'sichtbar' muss wahr oder falsch sein."
                    % key)
            if key in gesehen:
                raise ViewPrefFehler(
                    "Schluessel '%s' kommt mehrfach vor (Positionen %d und "
                    "%d). Eine Reihenfolge mit Doppelung ist keine."
                    % (key, gesehen[key], i))
            gesehen[key] = i
            if not kat.ist_bekannt(art, key):
                unbekannt.append(key)
            raus.append({"key": key, "sichtbar": bool(sichtbar)})

        if unbekannt:
            raise ViewPrefFehler(
                "Unbekannte Schluessel der Art '%s': %s. Bekannt sind: %s."
                % (art, ", ".join(sorted(unbekannt)),
                   ", ".join(kat.bekannte_schluessel(art))))
        return raus

    # -------------------------------------------------------------- Lesen ---
    def lade(self, person_id: int) -> Dict[str, Any]:
        """
        Die gespeicherte Einstellung einer Person.

        -> {'sichten': [...], 'widgets': [...], 'unbekannt': [...]}

        'sichten'/'widgets' sind in gespeicherter Reihenfolge und enthalten
        NUR Schluessel, die der Katalog kennt. Alles Uebrige steht in
        'unbekannt' — mit Art und Schluessel, damit es benannt ist und
        jemand darueber entscheiden kann.

        EINE LEERE LISTE HEISST 'NICHTS GESPEICHERT', NICHT 'ALLES
        AUSGEBLENDET'. Die Unterscheidung trifft die Oberflaeche: ohne
        gespeicherte Einstellung gilt die Werkseinstellung. Deshalb gibt es
        hier auch keinen Vorgriff darauf — diese Stelle liest, sie legt nicht
        aus.
        """
        rows = self._con.execute(
            "SELECT art, element_key, position, sichtbar, geaendert_at "
            "FROM person_view_pref WHERE person_id = ? "
            "ORDER BY art, position", (int(person_id),)).fetchall()

        out: Dict[str, Any] = {"sichten": [], "widgets": [], "unbekannt": []}
        ziel = {kat.ART_SICHT: "sichten", kat.ART_WIDGET: "widgets"}
        for r in rows:
            art = r["art"] if isinstance(r, sqlite3.Row) else r[0]
            key = r["element_key"] if isinstance(r, sqlite3.Row) else r[1]
            pos = r["position"] if isinstance(r, sqlite3.Row) else r[2]
            sic = r["sichtbar"] if isinstance(r, sqlite3.Row) else r[3]
            geae = r["geaendert_at"] if isinstance(r, sqlite3.Row) else r[4]
            if art not in ziel or not kat.ist_bekannt(art, key):
                out["unbekannt"].append({"art": art, "key": key,
                                         "position": int(pos)})
                continue
            out[ziel[art]].append({
                "key": key, "position": int(pos),
                "sichtbar": bool(sic), "geaendert_at": int(geae),
            })

        if out["unbekannt"]:
            # Kein stiller Fehlpfad: der Befund geht auch ins Protokoll, nicht
            # nur in die Antwort.
            logger.warning(
                "Person %d hat %d gespeicherte Ansichtseintraege, die der "
                "Katalog nicht (mehr) kennt: %s",
                int(person_id), len(out["unbekannt"]),
                ", ".join("%s/%s" % (u["art"], u["key"])
                          for u in out["unbekannt"]))
        return out

    # ----------------------------------------------------------- Schreiben ---
    def _einheit(self, person_id: int, art: str,
                 eintraege: List[Dict[str, Any]],
                 actor_id: int) -> WriteUnit:
        """
        Baut die WriteUnit fuer EINE Art. Sie wird gebaut und nicht sofort
        ausgefuehrt, damit 'Sichten und Kacheln in einem Zug' EINE Transaktion
        bleibt (Muster CasesRepo._assign_unit, Build 534).
        """
        now = int(time.time())

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            # Vollstaendiges Ersetzen. DELETE zuerst, sonst kollidiert der
            # neue Satz mit UNIQUE(person_id, art, position).
            con.execute(
                "DELETE FROM person_view_pref WHERE person_id = ? AND art = ?",
                (int(person_id), art))
            for pos, e in enumerate(eintraege):
                con.execute(
                    "INSERT INTO person_view_pref (person_id, art, "
                    "element_key, position, sichtbar, geaendert_at, "
                    "audit_seq) VALUES (?,?,?,?,?,?,0)",
                    (int(person_id), art, e["key"], pos,
                     1 if e["sichtbar"] else 0, now))
            # DER PAYLOAD TRAEGT DEN VOLLSTAENDIGEN ZUSTAND NACH DER
            # AENDERUNG. Aus der Kette allein muss rekonstruierbar sein, wie
            # die Oberflaeche zu einem Zeitpunkt eingerichtet war — ein Delta
            # ("eine Sicht ausgeblendet") koennte man nur mit allen frueheren
            # Belegen zusammen lesen.
            return {
                "art": art,
                "anzahl": len(eintraege),
                "ausgeblendet": [e["key"] for e in eintraege
                                 if not e["sichtbar"]],
                "reihenfolge": [e["key"] for e in eintraege],
            }

        def _after(con: sqlite3.Connection, seq: int) -> None:
            con.execute(
                "UPDATE person_view_pref SET audit_seq = ? "
                "WHERE person_id = ? AND art = ?",
                (seq, int(person_id), art))

        return WriteUnit(
            do_write=_w, event_type=EventType.VIEW_PREF_SET,
            actor_id=int(actor_id), target_type="person_view_pref",
            target_id=str(int(person_id)), after_audit=_after)

    def speichern(self, *, person_id: int,
                  sichten: Optional[Sequence[Any]] = None,
                  widgets: Optional[Sequence[Any]] = None,
                  actor_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Speichert die Einstellung. Mindestens eine der beiden Arten muss
        angegeben sein; die nicht angegebene bleibt unberuehrt.

        -> {'audit_seqs': {art: seq}, 'gespeichert': {art: anzahl}}
        """
        writer = self._require_writer()
        if actor_id is None:
            raise ViewPrefFehler(
                "Eine Aenderung ohne handelnde Person ist kein Beleg "
                "(actor_id fehlt).")
        if int(actor_id) != int(person_id):
            # Siehe Modulkopf: keine Vertretung, auch nicht fuer die Leitung.
            raise ViewPrefFehler(
                "Eine Ansichtseinstellung kann nur die betroffene Person "
                "selbst aendern (actor_id %d != person_id %d)."
                % (int(actor_id), int(person_id)))
        if sichten is None and widgets is None:
            raise ViewPrefFehler(
                "Weder 'sichten' noch 'widgets' angegeben — es gaebe nichts "
                "zu speichern.")

        arbeit = []
        if sichten is not None:
            arbeit.append((kat.ART_SICHT,
                           self._pruefe_eintraege(kat.ART_SICHT, sichten)))
        if widgets is not None:
            arbeit.append((kat.ART_WIDGET,
                           self._pruefe_eintraege(kat.ART_WIDGET, widgets)))

        units = [self._einheit(person_id, art, eintraege, int(actor_id))
                 for art, eintraege in arbeit]
        seqs = writer.audited_write_many(units)

        ergebnis = {
            "audit_seqs": {art: seq
                           for (art, _e), seq in zip(arbeit, seqs)},
            "gespeichert": {art: len(e) for art, e in arbeit},
        }
        logger.info("Ansichtseinstellung Person %d gespeichert: %s",
                    int(person_id), ergebnis["gespeichert"])
        return ergebnis

    def zuruecksetzen(self, *, person_id: int, art: str = "alle",
                      actor_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Loescht die gespeicherte Einstellung — danach gilt wieder die
        Werkseinstellung. art: 'sicht' | 'widget' | 'alle'.

        DAS LOESCHEN IST HIER ZULAESSIG, und der Unterschied zu den
        Ermittlungsdaten ist der Punkt: eine Vorliebe ist kein Beleg. Was
        sie WAR, bleibt trotzdem nachvollziehbar — der letzte
        'view_pref_set'-Eintrag der Kette traegt den vollstaendigen Zustand,
        und dieser Vorgang bekommt seinen eigenen Beleg.
        """
        writer = self._require_writer()
        if actor_id is None:
            raise ViewPrefFehler(
                "Ein Zuruecksetzen ohne handelnde Person ist kein Beleg "
                "(actor_id fehlt).")
        if int(actor_id) != int(person_id):
            raise ViewPrefFehler(
                "Eine Ansichtseinstellung kann nur die betroffene Person "
                "selbst zuruecksetzen (actor_id %d != person_id %d)."
                % (int(actor_id), int(person_id)))
        if art != "alle":
            self._pruefe_art(art)

        arten = list(kat.ARTEN) if art == "alle" else [art]
        ctx: Dict[str, int] = {}

        def _w(con: sqlite3.Connection) -> Dict[str, Any]:
            geloescht = 0
            for a in arten:
                cur = con.execute(
                    "DELETE FROM person_view_pref WHERE person_id = ? "
                    "AND art = ?", (int(person_id), a))
                geloescht += int(cur.rowcount or 0)
            ctx["geloescht"] = geloescht
            return {"arten": arten, "geloescht": geloescht}

        seq = writer.audited_write(
            do_write=_w, event_type=EventType.VIEW_PREF_RESET,
            actor_id=int(actor_id), target_type="person_view_pref",
            target_id=str(int(person_id)))

        logger.info("Ansichtseinstellung Person %d zurueckgesetzt (%s): "
                    "%d Zeilen.", int(person_id), ", ".join(arten),
                    ctx.get("geloescht", 0))
        return {"audit_seq": seq, "arten": arten,
                "geloescht": ctx.get("geloescht", 0)}
