# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/annotation_bestand.py
# IT-Forensisches Ermittlungswerkzeug - Bestandsaufnahme der Annotationen
# =============================================================================
# Zweck:
#   ZAEHLEN, WAS DA IST. Sieben Messbloecke ueber evidence_<uid>.db und den
#   Kopfdaten von forensic_<uid>.db. Es wird NICHTS ausgewertet, NICHTS
#   gedeutet und NICHTS geschrieben.
#
#   Diese Datei ist der Vorgang; tools/annotationen_bestand.py ist die
#   Befehlszeile davor (Grundregel 10).
#
# ── WARUM ES DIESES WERKZEUG GIBT ────────────────────────────────────────────
#
#   Etappe 0 des Arbeitsblocks "Annotationen verwendbar machen" (Weisung
#   Alex, 01.09.2026). Ziel des Arbeitsblocks ist, dass aus einer Annotation
#   ohne Browser und ohne Rateschritt post_id, Verfasser, Gespraechspartner,
#   Beitragszeit, umgebender Absatz und Zeichenausschnitt bestimmbar sind.
#
#   VOR JEDER ABLEITUNG STEHT DIE FRAGE, WAS UEBERHAUPT IN DEN ZEILEN STEHT.
#   Alle Messungen der Builds 727 bis 754 haben Annotationen gegen den
#   Seiteninhalt gehalten. Keine hat gezaehlt, wie viele Annotationen es
#   ueberhaupt gibt, wie viele davon aktuell sind und welche Spalten belegt
#   sind. In allen Laeufen war von "477 Annotationen" die Rede, ohne dass
#   feststand, ob das die Zahl ALLER Zeilen oder die der AKTUELLEN ist.
#
#   DIE MESSUNG BENUTZT DEN SEITEN-BLOB NICHT. Der BLOB-Inhalt
#   (forensic_<uid>.db, Spalte pages.html) wird weder gelesen noch geparst.
#   Grund: Der BLOB ist die eine Groesse im Aufbau, deren Verlaesslichkeit
#   selbst in Frage steht - die forensic_<uid>.db ist mehrfach neu erstellt
#   worden, und in mindestens zwei Faellen enthielt sie leere BLOBs
#   (Befund Alex, 01.09.2026; vermutete Ursache: fehlgeschlagene Anmeldung
#   des scrapenden Forennutzers oder ein Speicherproblem). Eine Zahlenbasis,
#   die auf dem BLOB-INHALT aufsetzt, koennte durch genau diesen Defekt
#   verfaelscht sein. Deshalb liest M7 ausschliesslich KOPFDATEN:
#   typeof(html), length(html), http_status, title, fetched_at.
#
# ── WARUM 'title' IN M7 MITGEMESSEN WIRD ─────────────────────────────────────
#
#   Eine fehlgeschlagene Anmeldung liefert KEINEN Fehlercode. Sie liefert
#   eine gueltige Seite mit HTTP 200 und nennenswerter Laenge - nur eben die
#   Anmeldeseite statt der Forenseite. Ueber length(html) allein ist dieser
#   Fall nicht sicher zu erkennen; ueber den Seitentitel ist er es, weil die
#   Anmeldeseite einen anderen Titel traegt als ein Thema. Die Spalte 'title'
#   steht bereits im Schema (forensic_uid.db.schema.sql) und muss nicht neu
#   berechnet werden.
#
#   ES WIRD KEIN SCHWELLWERT FUER "ZU KURZ" FESTGELEGT. Das Werkzeug gibt die
#   Laengenverteilung aus und nennt die kuerzesten Seiten namentlich. Welche
#   davon defekt sind, entscheidet der Ermittler an den Zahlen und nicht das
#   Werkzeug an einer geratenen Grenze (Grundregel 1: kein stilles Aussortieren).
#
# ── DIE SIEBEN MESSBLOECKE ───────────────────────────────────────────────────
#
#   M1 Zeilenbestand   - gesamt, geloescht, Generationen, ueberholt, aktuell
#   M2 Spaltenbelegung - element_id, post_id, local_id, category, ...
#   M3 page_url        - Skripte, Parameter, Adressen fuer dieselbe Seite
#   M4 selection_json  - Gueltigkeit, Schluessel, Signaturen, sinnfreie Marken
#   M5 XPath-Syntax    - Praefix, Textknotenform, Tiefe, Beitragsschritt
#   M6 Zeit            - Monatsverteilung, Trennlinie 01.07.2026, Testbestand
#   M7 Seitenkopfdaten - Laenge, Status, Titel, Zuordnung Annotation -> Seite
#
# Abhaengigkeiten: json, os, re, sqlite3, statistics, datetime (alle Stdlib)
# Version: 0.8.755 - Build 755
# =============================================================================

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sqlite3
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Beginn des Produktivbetriebs. Weisung Alex: ab diesem Zeitpunkt gesetzte
#: Annotationen sind in jedem Fall als echt und wichtig zu betrachten, sofern
#: er nicht im Einzelfall ausdruecklich etwas anderes sagt. VOR diesem
#: Zeitpunkt kann ebenfalls Echtes liegen - es wurden bereits einzelne
#: Arbeiten an Faellen vorgenommen. Die Linie TRENNT die Ausgabe, sie FILTERT
#: nichts.
#: Beleg: Chat 01.09.2026, Antwort 7.3 zum Bauplan Build 755.
PRODUKTIVBETRIEB_AB = int(_dt.datetime(2026, 7, 1, 0, 0, 0,
                                       tzinfo=_dt.timezone.utc).timestamp())

#: Bestaende, die nachweislich zu Testzwecken benutzt wurden. Sie werden
#: GEKENNZEICHNET und NICHT ausgeblendet: auch im Testbetrieb koennen
#: verwertbare Spuren erhoben worden sein, und die Entscheidung darueber ist
#: eine Einzelfallentscheidung des Ermittlers (Grundregel 1).
#: Beleg: Chat 01.09.2026 - "subject_id=2948078 wurde fuer Testzwecke benutzt".
TESTBESTAENDE: Tuple[str, ...] = ("2948078",)

#: Nur Leerraum, von Anfang bis Ende. re.UNICODE ist in Python 3 fuer str
#: die Vorgabe - '\s' erfasst damit auch geschuetzte Leerzeichen (U+00A0)
#: und ideographische Leerzeichen (U+3000), die in einem multilingualen
#: Forum vorkommen.
_RE_NUR_LEERRAUM = re.compile(r"^\s*$")

#: Mindestens EIN Wortzeichen. Weisung Alex, 02.09.2026: eine Markierung ohne
#: Wortzeichen traegt keinen Wortlaut und darf gar nicht erst entstehen.
#: Die Unicode-Semantik ist hier nicht Beiwerk, sondern zwingend: das Forum
#: ist multilingual, und '\w' MUSS kyrillische, arabische und CJK-Zeichen
#: als Wortzeichen erkennen. Eine ASCII-Auswertung meldete ganze Sprachen
#: als leer und loeschte damit echte Beweismittel.
_RE_WORTZEICHEN = re.compile(r"\w")

#: Kennungen, die trotz gueltiger Form NICHT als Ermittlerarbeit gelten.
#: Beleg: Alex, 02.09.2026 - "H0A2898" ist sein Produktivkonto, "paul" sein
#: Entwicklungskonto; beides sind Testmarkierungen. "uid_<Ziffern>" ist eine
#: seinerzeit faelschlich existierende Kennung aus dem Entwicklungsbetrieb.
AUSGENOMMENE_KENNUNGEN: Tuple[str, ...] = ("H0A2898", "paul")

#: Form einer gueltigen Ermittlerkennung. Weisung Alex: nur Eintraege, die
#: mit 'H0' oder 'h0' beginnen, wurden von tatsaechlichen Ermittlern mit
#: gueltiger Kennung erzeugt.
_RE_KENNUNG_GUELTIG = re.compile(r"^[Hh]0")

#: Die faelschlich existierende Entwicklungskennung. Schreibungsunabhaengig,
#: weil die Normalisierung auf Grossschreibung sonst 'UID_538299' erzeugte
#: und dieses Muster nicht mehr traefe.
_RE_KENNUNG_UID = re.compile(r"^uid_\d+$", re.IGNORECASE)

#: ── WARUM KENNUNGEN AUF GROSSSCHREIBUNG NORMALISIERT WERDEN ────────────────
#:
#: Beleg (Alex, 03.09.2026): Das Produktivsystem bezieht die Kennungen aus dem
#: Active Directory und verwendet AUSSCHLIESSLICH Grossbuchstaben. Die
#: kleingeschriebene Form stammt aus dem Testsystem, wo die Kennung von Hand
#: eingetragen wurde. 'h082317' und 'H082317' sind dieselbe Person - die
#: Chefermittlerin.
#:
#: DAS IST KEIN DARSTELLUNGSPROBLEM. Die Rechtepruefung vergleicht die
#: Kennung des Anmeldenden mit 'annotations.created_by'. Stimmen sie nicht
#: zeichengenau ueberein, gelten die Eintraege nicht als eigene, und die
#: Person kann ihre eigenen Annotationen weder bearbeiten noch loeschen.
#: Im Bestand betrifft das 77 Zeilen in evidence_2948078.db.
#:
#: DIESE MESSUNG BEHEBT DAS NICHT. Sie STELLT ES FEST und weist die
#: betroffenen Zeilen namentlich aus. Geschrieben wird erst in Etappe 4
#: (Weisung Alex, 03.09.2026: bis dahin ausschliesslich lesend).


def kennung_normal(wert) -> str:
    """
    Eine Kennung in ihrer Vergleichsform: getrimmt und in Grossbuchstaben.

    Nur fuer den VERGLEICH. Die vorgefundene Schreibweise wird daneben
    unveraendert mitgefuehrt - eine Messung, die die Rohform wegwirft, koennte
    die Abweichung anschliessend nicht mehr belegen.
    """
    if wert is None:
        return ""
    return str(wert).strip().upper()

#: Die Spalten aus 'annotations', deren Belegungsgrad M2 zaehlt.
_M2_SPALTEN: Tuple[str, ...] = (
    "element_id", "post_id", "local_id", "investigator_id", "created_by",
    "category", "text", "tags_json", "actual_uid",
)

#: Form eines Beitragsbehaelter-Bezeichners. Der Forencode vergibt 'p<post_id>'
#: (forum/html/include/pms_new/mdl/topic.php Z. 439 und die viewtopic-Vorlage).
#: 'pp<n>' kommt in Altbestaenden vor und wird deshalb getrennt gezaehlt statt
#: mit 'sonstiges' verrechnet.
_RE_ELEMENT_P = re.compile(r"^p(\d+)$")
_RE_ELEMENT_PP = re.compile(r"^pp(\d+)$")

#: Ein XPath-Schritt: Tagname (oder 'text()') mit Positionsindex.
_RE_SCHRITT = re.compile(r"^([A-Za-z0-9_:-]+|text\(\))\[(\d+)\]$")

#: Die Textknotenform aus Build 029. Sie ist kein gueltiger XPath-Schritt und
#: wird in toolbar.js beim Auflesen ersetzt (_nodeFromXpath, Z. 1013 ff.).
#: Im BESTAND kann sie noch stehen; wie oft, ist bis heute ungemessen.
_RE_TEXTKNOTEN_ALT = re.compile(r"#text\[\d+\]")
_RE_TEXTKNOTEN_NEU = re.compile(r"text\(\)\[\d+\]")


def sekunden(wert) -> Optional[int]:
    """
    Ein Zeitstempel als Sekunden. None, wenn unbrauchbar.

    Sekunden ODER Millisekunden - beides kommt in Altbestaenden vor. Die
    Umrechnung ist WORTGLEICH aus tools/xpath_versatz_messen.py uebernommen.
    Eine Bestandsaufnahme, die Zeitstempel anders deutet als die Auswertung,
    zaehlt eine andere Menge als die, ueber die danach entschieden wird.
    """
    try:
        n = int(wert)
    except (TypeError, ValueError):
        return None
    return n // 1000 if n > 100000000000 else n


def ist_millisekunden(wert) -> bool:
    """Ob der Rohwert in Millisekunden vorliegt. Eigener Zaehler in M6."""
    try:
        return int(wert) > 100000000000
    except (TypeError, ValueError):
        return False


def zeit(wert) -> str:
    """Ein Zeitstempel als lesbare Angabe (UTC). Unbrauchbares bleibt so."""
    n = sekunden(wert)
    if n is None:
        return "(kein Zeitstempel)"
    try:
        return _dt.datetime.fromtimestamp(n, _dt.timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S")
    except (OverflowError, OSError, ValueError):
        return "(unplausibel)"


def monat(wert) -> str:
    """Der Monat eines Zeitstempels als 'JJJJ-MM'."""
    n = sekunden(wert)
    if n is None:
        return "(kein Zeitstempel)"
    try:
        return _dt.datetime.fromtimestamp(n, _dt.timezone.utc).strftime("%Y-%m")
    except (OverflowError, OSError, ValueError):
        return "(unplausibel)"


def _kennzahlen(werte: List[int]) -> Dict[str, Any]:
    """Kleinster, groesster, mittlerer Wert einer Liste. Leer -> alles None."""
    if not werte:
        return {"anzahl": 0, "min": None, "max": None, "median": None}
    return {
        "anzahl": len(werte),
        "min": min(werte),
        "max": max(werte),
        "median": int(statistics.median(werte)),
    }


@dataclass
class Bestandsbefund:
    """
    Das Ergebnis EINES Bestands. Reine Zahlen, keine Wertung.

    Die Felder sind bewusst als 'dict' gehalten und nicht als feste Attribute:
    die Ausgabe geht sowohl in ein Klartextprotokoll als auch nach JSON, und
    beide sollen dieselben Werte tragen. Eine zweite Darstellung, die aus der
    ersten nachgebaut wird, weicht frueher oder spaeter ab.
    """
    uid: str
    evidence_pfad: str
    forensic_pfad: Optional[str] = None
    evidence_lesbar: bool = False
    forensic_lesbar: bool = False
    testbestand: bool = False
    fehler: List[str] = field(default_factory=list)
    m1_zeilenbestand: Dict[str, Any] = field(default_factory=dict)
    m2_spalten: Dict[str, Any] = field(default_factory=dict)
    m3_page_url: Dict[str, Any] = field(default_factory=dict)
    m4_selection: Dict[str, Any] = field(default_factory=dict)
    m5_xpath: Dict[str, Any] = field(default_factory=dict)
    m6_zeit: Dict[str, Any] = field(default_factory=dict)
    m7_seiten: Dict[str, Any] = field(default_factory=dict)
    m8_urheber: Dict[str, Any] = field(default_factory=dict)
    m9_variante: Dict[str, Any] = field(default_factory=dict)

    def als_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "evidence_pfad": self.evidence_pfad,
            "forensic_pfad": self.forensic_pfad,
            "evidence_lesbar": self.evidence_lesbar,
            "forensic_lesbar": self.forensic_lesbar,
            "testbestand": self.testbestand,
            "fehler": list(self.fehler),
            "m1_zeilenbestand": self.m1_zeilenbestand,
            "m2_spalten": self.m2_spalten,
            "m3_page_url": self.m3_page_url,
            "m4_selection": self.m4_selection,
            "m5_xpath": self.m5_xpath,
            "m6_zeit": self.m6_zeit,
            "m7_seiten": self.m7_seiten,
            "m8_urheber": self.m8_urheber,
            "m9_variante": self.m9_variante,
        }


class BestandsAufnahme:
    """
    Zaehlt einen Bestand aus. Rein lesend, beide Verbindungen 'mode=ro'.

    Der Schreibschutz haengt an der VERBINDUNG und nicht am Vorsatz: SQLite
    weist einen Schreibversuch dann ab, statt sich auf die Sorgfalt des
    Aufrufers zu verlassen.
    """

    def __init__(self, uid: str, evidence_pfad: str,
                 forensic_pfad: Optional[str] = None,
                 kuerzeste: int = 20,
                 ausgenommen: Optional[Tuple[str, ...]] = None) -> None:
        self.uid = str(uid)
        self.evidence_pfad = evidence_pfad
        self.forensic_pfad = forensic_pfad
        self.kuerzeste = max(0, int(kuerzeste))
        # Die Ausschlussliste ERGAENZT die Konstante, sie ersetzt sie nicht.
        # Wer per Befehlszeile eine eigene Liste uebergibt, soll damit
        # zusaetzliche Kennungen ausnehmen koennen - aber NICHT versehentlich
        # Alex' eigene Testkonten wieder als Ermittlerarbeit einstufen.
        zusatz = tuple(ausgenommen or ())
        self.ausgenommen = tuple(AUSGENOMMENE_KENNUNGEN) + zusatz
        # Der Vergleich laeuft ueber die Grossform. Sonst rutschte ein
        # 'h0a2898' an der Ausschlussliste vorbei und zaehlte als
        # Ermittlerarbeit - genau der Fall, den 'h082317' belegt.
        self._ausgenommen_normal = frozenset(
            kennung_normal(k) for k in self.ausgenommen)
        self._befund = Bestandsbefund(
            uid=self.uid, evidence_pfad=evidence_pfad,
            forensic_pfad=forensic_pfad,
            testbestand=self.uid in TESTBESTAENDE)

    # -- oeffentlich ---------------------------------------------------------

    def erheben(self) -> Bestandsbefund:
        """Alle sieben Messbloecke. Fehler werden benannt, nie verschluckt."""
        b = self._befund
        if not os.path.exists(self.evidence_pfad):
            b.fehler.append("evidence_<uid>.db gibt es nicht: %s"
                            % self.evidence_pfad)
            return b
        try:
            con_e = self._oeffne_ro(self.evidence_pfad)
        except sqlite3.Error as exc:
            b.fehler.append("evidence_<uid>.db nicht zu oeffnen: %s" % exc)
            return b
        b.evidence_lesbar = True
        try:
            zeilen = self._annotationen(con_e)
            b.m1_zeilenbestand = self._m1(con_e, zeilen)
            b.m2_spalten = self._m2(zeilen)
            b.m3_page_url = self._m3(zeilen)
            b.m4_selection = self._m4(zeilen)
            b.m5_xpath = self._m5(zeilen)
            b.m6_zeit = self._m6(zeilen)
            b.m7_seiten = self._m7(zeilen)
            b.m8_urheber = self._m8(zeilen)
            b.m9_variante = self._m9(zeilen)
        finally:
            con_e.close()
        return b

    # -- Werkzeug ------------------------------------------------------------

    @staticmethod
    def _oeffne_ro(pfad: str) -> sqlite3.Connection:
        con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def _annotationen(self, con: sqlite3.Connection) -> List[sqlite3.Row]:
        """
        ALLE Zeilen aus 'annotations' - geloeschte und ueberholte eingeschlossen.

        Es wird bewusst nicht gefiltert. Welche Zeilen als 'aktuell' gelten,
        entscheidet M1 und weist es getrennt aus; wer hier filtert, kann
        spaeter nicht mehr sagen, was er weggelassen hat (Grundregel 1).
        """
        return list(con.execute(
            "SELECT id, page_url, element_id, category, text, ts, "
            "       investigator_id, selection_json, tags_json, local_id, "
            "       post_id, created_by, deleted_at, version_nr, prev_id, "
            "       actual_uid "
            "FROM annotations ORDER BY id"))

    # -- M1 ------------------------------------------------------------------

    def _m1(self, con: sqlite3.Connection,
            zeilen: List[sqlite3.Row]) -> Dict[str, Any]:
        """
        Zeilenbestand.

        'ueberholt' = auf diese Zeile zeigt das prev_id einer anderen Zeile.
        'aktuell'   = nicht geloescht UND nicht ueberholt. Das ist die Menge,
                      ueber die in Etappe 4 entschieden wird; sie muss hier
                      feststehen, damit spaeter nicht zwei verschiedene
                      Gesamtzahlen nebeneinander stehen.
        """
        vorgaenger = {z["prev_id"] for z in zeilen if z["prev_id"] is not None}
        geloescht = sum(1 for z in zeilen if z["deleted_at"] is not None)
        ueberholt = sum(1 for z in zeilen if z["id"] in vorgaenger)
        aktuell = sum(1 for z in zeilen
                      if z["deleted_at"] is None and z["id"] not in vorgaenger)
        gen = {}
        for z in zeilen:
            schl = str(z["version_nr"])
            gen[schl] = gen.get(schl, 0) + 1
        # GEGENPROBE GEGEN DIE KETTE: ein prev_id, das auf keine vorhandene
        # Zeile zeigt, ist ein Kettenbruch. Er ist zu benennen, nicht zu
        # ignorieren - die Rueckverfolgbarkeit der Generationen ist der
        # Grund, aus dem es die Spalte gibt.
        vorhandene = {z["id"] for z in zeilen}
        kettenbruch = sorted(
            z["id"] for z in zeilen
            if z["prev_id"] is not None and z["prev_id"] not in vorhandene)
        return {
            "zeilen_gesamt": len(zeilen),
            "geloescht": geloescht,
            "nicht_geloescht": len(zeilen) - geloescht,
            "ueberholt": ueberholt,
            "aktuell": aktuell,
            "mit_prev_id": sum(1 for z in zeilen if z["prev_id"] is not None),
            "generationen": gen,
            "kettenbruch_ids": kettenbruch,
            "kettenbruch_anzahl": len(kettenbruch),
        }

    # -- M2 ------------------------------------------------------------------

    def _m2(self, zeilen: List[sqlite3.Row]) -> Dict[str, Any]:
        """
        Belegungsgrad der Spalten - und die FORM von element_id.

        WARUM element_id gesondert: forensic_api/annotate.py Z. 16
        dokumentiert den Inhalt als 'p12345', also den Beitragsbehaelter.
        toolbar/toolbar.js Z. 3842 setzt die Spalte auf mindestens einem
        Codepfad ausdruecklich auf null. Wie viele Annotationen die post_id
        auf diesem Weg BEREITS mitfuehren, ist bis heute ungemessen - und
        genau diese Zahl entscheidet, wie gross der Teil ist, der ohne jede
        Ableitung verwendbar ist.
        """
        erg: Dict[str, Any] = {}
        for spalte in _M2_SPALTEN:
            gesetzt = sum(1 for z in zeilen
                          if z[spalte] is not None and str(z[spalte]) != "")
            erg[spalte] = {"gesetzt": gesetzt, "leer": len(zeilen) - gesetzt}

        form_p = form_pp = form_sonst = 0
        sonstige: List[str] = []
        for z in zeilen:
            roh = z["element_id"]
            if roh is None or str(roh).strip() == "":
                continue
            s = str(roh).strip()
            if _RE_ELEMENT_P.match(s):
                form_p += 1
            elif _RE_ELEMENT_PP.match(s):
                form_pp += 1
            else:
                form_sonst += 1
                if len(sonstige) < 20 and s not in sonstige:
                    sonstige.append(s)
        erg["element_id_form"] = {
            "p_zahl": form_p, "pp_zahl": form_pp, "sonstige": form_sonst,
            "beispiele_sonstige": sonstige,
        }

        # Deckung element_id <-> post_id: sagen beide dasselbe, wo beide da
        # sind? Eine Abweichung waere ein Befund, kein Detail.
        beide = gleich = ungleich = 0
        for z in zeilen:
            m = _RE_ELEMENT_P.match(str(z["element_id"] or "").strip())
            if m is None or z["post_id"] is None:
                continue
            beide += 1
            if int(m.group(1)) == int(z["post_id"]):
                gleich += 1
            else:
                ungleich += 1
        erg["element_id_gegen_post_id"] = {
            "beide_gesetzt": beide, "gleich": gleich, "ungleich": ungleich}

        # Kategorien im Klartext - sie entscheiden mit darueber, welche
        # Annotation ueberhaupt in einen Bericht gehoert.
        kat: Dict[str, int] = {}
        for z in zeilen:
            s = str(z["category"] or "(leer)")
            kat[s] = kat.get(s, 0) + 1
        erg["kategorien"] = dict(sorted(kat.items(), key=lambda p: -p[1]))
        return erg

    # -- M3 ------------------------------------------------------------------

    @staticmethod
    def _url_zerlegen(url: str) -> Tuple[str, Dict[str, str]]:
        """Adresse in Pfad und Parameter zerlegen. Ohne urllib - der Bestand
        enthaelt Adressen mit '&amp;' und Sprungmarken, die urllib anders
        behandelt als der Browser sie geschickt hat."""
        roh = str(url or "")
        roh = roh.split("#", 1)[0]
        if "?" in roh:
            pfad, rest = roh.split("?", 1)
        else:
            pfad, rest = roh, ""
        par: Dict[str, str] = {}
        for stueck in rest.replace("&amp;", "&").split("&"):
            if not stueck:
                continue
            if "=" in stueck:
                k, v = stueck.split("=", 1)
            else:
                k, v = stueck, ""
            par[k] = v
        return pfad, par

    def _m3(self, zeilen: List[sqlite3.Row]) -> Dict[str, Any]:
        """
        page_url - Skripte, Parameter und Adressen, die dieselbe Seite meinen.

        DER TEILMENGENVERGLEICH ist der Kern: Bei Bestand 515056 steht
        dieselbe Seite zweimal, einmal als 'viewtopic.php?id=145446' und
        einmal als 'viewtopic.php?id=145446&uid=515056'. Statt zu raten,
        welche Parameter Beiwerk sind, wird gemessen: liegt die Parametermenge
        einer Adresse VOLLSTAENDIG in der einer anderen desselben Pfades, sind
        beide Kandidaten fuer dieselbe Seite. Das nennt die Zusatzparameter
        beim Namen, statt eine Liste zu pflegen, die veraltet.
        """
        je_skript: Dict[str, int] = {}
        je_parameter: Dict[str, int] = {}
        je_url: Dict[str, int] = {}
        for z in zeilen:
            url = str(z["page_url"] or "(leer)")
            je_url[url] = je_url.get(url, 0) + 1
            pfad, par = self._url_zerlegen(url)
            skript = pfad.rsplit("/", 1)[-1] or pfad
            je_skript[skript] = je_skript.get(skript, 0) + 1
            for k in par:
                je_parameter[k] = je_parameter.get(k, 0) + 1

        zerlegt = {u: self._url_zerlegen(u) for u in je_url}
        gruppen: List[Dict[str, Any]] = []
        adressen = sorted(je_url)
        for i, a in enumerate(adressen):
            pfad_a, par_a = zerlegt[a]
            menge_a = set(par_a.items())
            for b in adressen[i + 1:]:
                pfad_b, par_b = zerlegt[b]
                if pfad_a != pfad_b:
                    continue
                menge_b = set(par_b.items())
                if menge_a and menge_a < menge_b:
                    knapp, weit = a, b
                elif menge_b and menge_b < menge_a:
                    knapp, weit = b, a
                else:
                    continue
                zusatz = sorted(
                    "%s=%s" % (k, v)
                    for k, v in (set(zerlegt[weit][1].items())
                                 - set(zerlegt[knapp][1].items())))
                gruppen.append({
                    "kurz": knapp, "lang": weit, "zusatz": zusatz,
                    "annotationen_kurz": je_url[knapp],
                    "annotationen_lang": je_url[weit],
                })
        return {
            "adressen_verschieden": len(je_url),
            "je_skript": dict(sorted(je_skript.items(), key=lambda p: -p[1])),
            "je_parameter": dict(sorted(je_parameter.items(),
                                        key=lambda p: -p[1])),
            "haeufigste_adressen": sorted(
                ({"url": u, "annotationen": n} for u, n in je_url.items()),
                key=lambda d: -d["annotationen"])[:15],
            "teilmengenpaare": gruppen,
            "teilmengenpaare_anzahl": len(gruppen),
        }

    # -- M4 ------------------------------------------------------------------

    def _m4(self, zeilen: List[sqlite3.Row]) -> Dict[str, Any]:
        """
        selection_json - Gueltigkeit, Schluessel, Signaturen, sinnfreie Marken.

        ── DER FEHLER, DEN DIESE FASSUNG BEHEBT (Build 755 -> 756) ───────────

        Build 755 verglich 'offsetStart' mit 'offsetEnd', OHNE zu pruefen, ob
        sich beide auf denselben Knoten beziehen. Das ist falsch:

          offsetStart ist ein Zeichenversatz IN DEM KNOTEN, den xpathStart
          benennt. offsetEnd ist ein Zeichenversatz IN DEM KNOTEN, den
          xpathEnd benennt.

        Sind das verschiedene Knoten, haben die beiden Zahlen keinen
        gemeinsamen Bezugspunkt und ihr Groessenverhaeltnis sagt nichts.
        Beleg (Alex, Bestand 1704143): xpathStart endet auf
        'h2[1]/span[1]/a[1]/text()[1]' mit offsetStart=25, xpathEnd auf
        'div[6]/.../p[1]/text()[2]' mit offsetEnd=19. Verschiedene Zweige des
        Baums - dass 19 kleiner als 25 ist, bedeutet nichts.

        Von den 25 in Build 755 gemeldeten Faellen waren MINDESTENS 12
        nachweislich falsch (nachgerechnet ueber M5.start_gleich_ende).

        DESHALB WIRD JETZT GETRENNT: Ein Offsetvergleich findet nur dort
        statt, wo xpathStart == xpathEnd gilt. Fuer alles andere gibt es
        KEIN URTEIL, sondern nur einen Zaehler.

        ── DIE LEERPRUEFUNG (Weisung Alex, 02.09.2026) ──────────────────────

        Die belastbare Pruefung laeuft ueber 'textContent', nicht ueber die
        Offsets. Vier getrennte Zaehler: fehlt, leer, nur Leerraum, und -
        neu und schaerfer - OHNE WORTZEICHEN. Eine Markierung, die nur aus
        Zeichensetzung besteht ('---', '...'), traegt keinen Wortlaut und
        ist ebenso sinnfrei wie eine leere.

        '\\w' wird mit Unicode-Semantik ausgewertet (in Python 3 die
        Vorgabe fuer str). Das Forum ist multilingual; kyrillische,
        arabische und CJK-Zeichen MUESSEN als Wortzeichen zaehlen, sonst
        meldet die Pruefung ganze Sprachen als leer.

        ── WARUM DIE ZEILEN NAMENTLICH GENANNT WERDEN ───────────────────────

        Build 755 lieferte nur Zaehlwerte. Als Alex die beanstandeten Faelle
        nachpruefen wollte, konnte das Werkzeug sie nicht benennen - er
        musste dem Ergebnis glauben statt es pruefen zu koennen. Das ist bei
        einer forensischen Messung nicht hinnehmbar. Jeder beanstandete Fall
        wird jetzt mit annotations.id ausgewiesen.

        AUSGEGEBEN WIRD KEIN BEWEISMITTELINHALT. Bei den Offsetfaellen nur
        die Zahlen. Bei den Wortlautfaellen eine Zeichenprobe NUR dort, wo
        per Definition kein Wortzeichen enthalten ist - dort kann kein
        inhaltlicher Text austreten.
        """
        null = leer = ungueltig = gueltig = 0
        schluessel: Dict[str, int] = {}
        signaturen: Dict[str, int] = {}
        # Offsets - streng getrennt nach Vergleichbarkeit.
        selber_knoten = verschiedene_knoten = ohne_offsets = 0
        end_kleiner = end_gleich = end_groesser = 0
        offset_faelle: List[Dict[str, Any]] = []
        # Wortlaut.
        w_fehlt = w_leer = w_leerraum = w_ohne_wortzeichen = 0
        wortlaut_faelle: List[Dict[str, Any]] = []
        laengen: List[int] = []

        for z in zeilen:
            roh = z["selection_json"]
            if roh is None:
                null += 1
                continue
            if str(roh).strip() == "":
                leer += 1
                continue
            try:
                sel = json.loads(roh)
            except (ValueError, TypeError):
                ungueltig += 1
                continue
            if not isinstance(sel, dict):
                ungueltig += 1
                continue
            gueltig += 1
            for k in sel:
                schluessel[k] = schluessel.get(k, 0) + 1
            sig = "|".join(sorted(str(k) for k in sel))
            signaturen[sig] = signaturen.get(sig, 0) + 1

            # -- Offsets ------------------------------------------------------
            a, e = sel.get("offsetStart"), sel.get("offsetEnd")
            xs, xe = sel.get("xpathStart"), sel.get("xpathEnd")
            if not (isinstance(a, int) and isinstance(e, int)):
                ohne_offsets += 1
            elif xs != xe:
                # KEIN URTEIL. Die beiden Zahlen zaehlen in verschiedenen
                # Knoten; ihr Verhaeltnis ist bedeutungslos.
                verschiedene_knoten += 1
            else:
                selber_knoten += 1
                if e < a:
                    end_kleiner += 1
                    offset_faelle.append({
                        "id": z["id"], "art": "ende_vor_anfang",
                        "offsetStart": a, "offsetEnd": e})
                elif e == a:
                    end_gleich += 1
                    offset_faelle.append({
                        "id": z["id"], "art": "laenge_null",
                        "offsetStart": a, "offsetEnd": e})
                else:
                    end_groesser += 1

            # -- Wortlaut -----------------------------------------------------
            txt = sel.get("textContent")
            if txt is None:
                w_fehlt += 1
                wortlaut_faelle.append({"id": z["id"], "art": "fehlt",
                                        "laenge": None, "probe": None})
            elif str(txt) == "":
                w_leer += 1
                wortlaut_faelle.append({"id": z["id"], "art": "leer",
                                        "laenge": 0, "probe": ""})
            elif _RE_NUR_LEERRAUM.match(str(txt)):
                w_leerraum += 1
                wortlaut_faelle.append({
                    "id": z["id"], "art": "nur_leerraum",
                    "laenge": len(str(txt)), "probe": repr(str(txt)[:20])})
                laengen.append(len(str(txt)))
            elif _RE_WORTZEICHEN.search(str(txt)) is None:
                # Enthaelt Zeichen, aber KEIN Wortzeichen - also nur
                # Zeichensetzung oder Sonderzeichen. Die Probe ist hier
                # unbedenklich: was kein Wortzeichen ist, traegt keinen
                # inhaltlichen Text.
                w_ohne_wortzeichen += 1
                wortlaut_faelle.append({
                    "id": z["id"], "art": "ohne_wortzeichen",
                    "laenge": len(str(txt)), "probe": repr(str(txt)[:20])})
                laengen.append(len(str(txt)))
            else:
                laengen.append(len(str(txt)))

        return {
            "null": null, "leer": leer, "ungueltig": ungueltig,
            "gueltig": gueltig,
            "schluessel": dict(sorted(schluessel.items(), key=lambda p: -p[1])),
            "signaturen": sorted(
                ({"signatur": s, "anzahl": n} for s, n in signaturen.items()),
                key=lambda d: -d["anzahl"]),
            "signaturen_anzahl": len(signaturen),
            "offsets": {
                "vergleichbar_selber_knoten": selber_knoten,
                "nicht_vergleichbar_andere_knoten": verschiedene_knoten,
                "ohne_offsets": ohne_offsets,
                "ende_vor_anfang": end_kleiner,
                "laenge_null": end_gleich,
                "in_ordnung": end_groesser,
                "beanstandet": end_kleiner + end_gleich,
                "faelle": offset_faelle,
            },
            "wortlaut": {
                "fehlt": w_fehlt, "leer": w_leer,
                "nur_leerraum": w_leerraum,
                "ohne_wortzeichen": w_ohne_wortzeichen,
                "beanstandet": (w_fehlt + w_leer + w_leerraum
                                + w_ohne_wortzeichen),
                "faelle": wortlaut_faelle,
            },
            "textcontent_laenge": _kennzahlen(laengen),
        }

    # -- M5 ------------------------------------------------------------------

    def _m5(self, zeilen: List[sqlite3.Row]) -> Dict[str, Any]:
        """
        Die XPath-Ausdruecke - REIN ALS ZEICHENKETTE.

        Es wird kein DOM gebaut und keine Seite geladen. Gemessen wird nur,
        WAS DASTEHT: Praefix, Textknotenform, Tiefe, welche Tagnamen
        vorkommen, ob Start- und Endausdruck gleich sind.

        WARUM DER TAGNAME DES BEITRAGSSCHRITTS ZAEHLT: Auf viewtopic.php ist
        der Beitragsbehaelter ein <article>, auf pmsnew.php ein <div>
        (forum/html/include/pms_new/mdl/topic.php Z. 439). Ein Positionsindex
        auf 'div[n]' zaehlt jedes Geschwister-<div> mit, ein Index auf
        'article[n]' nur Beitraege. Die Verteilung der beiden Tagnamen sagt
        also voraus, welcher Teil des Bestands gegen eingeschobene Elemente
        empfindlich ist.
        """
        ohne = 0
        praefix = {"punkt": 0, "doppel": 0, "sonstige": 0}
        alt_form = neu_form = 0
        start_gleich_ende = 0
        tiefen: List[int] = []
        tagnamen: Dict[str, int] = {}
        endet_textknoten = 0
        ohne_ende = 0
        for z in zeilen:
            roh = z["selection_json"]
            if not roh:
                ohne += 1
                continue
            try:
                sel = json.loads(roh)
            except (ValueError, TypeError):
                ohne += 1
                continue
            if not isinstance(sel, dict):
                ohne += 1
                continue
            xs = sel.get("xpathStart")
            xe = sel.get("xpathEnd")
            if not isinstance(xs, str) or xs.strip() == "":
                ohne += 1
                continue
            if not isinstance(xe, str) or xe.strip() == "":
                ohne_ende += 1
            if xs == xe:
                start_gleich_ende += 1
            if xs.startswith("./"):
                praefix["punkt"] += 1
            elif xs.startswith("//"):
                praefix["doppel"] += 1
            else:
                praefix["sonstige"] += 1
            if _RE_TEXTKNOTEN_ALT.search(xs):
                alt_form += 1
            if _RE_TEXTKNOTEN_NEU.search(xs):
                neu_form += 1
            schritte = [s for s in xs.lstrip("./").split("/") if s]
            tiefen.append(len(schritte))
            if schritte and _RE_TEXTKNOTEN_NEU.match(schritte[-1]):
                endet_textknoten += 1
            for s in schritte:
                m = _RE_SCHRITT.match(s)
                name = m.group(1) if m else s
                tagnamen[name] = tagnamen.get(name, 0) + 1
        return {
            "ohne_xpathstart": ohne,
            "ohne_xpathende": ohne_ende,
            "praefix": praefix,
            "textknoten_altform": alt_form,
            "textknoten_neuform": neu_form,
            "start_gleich_ende": start_gleich_ende,
            "tiefe": _kennzahlen(tiefen),
            "tagnamen": dict(sorted(tagnamen.items(), key=lambda p: -p[1])),
            "endet_auf_textknoten": endet_textknoten,
        }

    # -- M6 ------------------------------------------------------------------

    def _m6(self, zeilen: List[sqlite3.Row]) -> Dict[str, Any]:
        """
        Zeit. Die Linie 01.07.2026 TRENNT die Ausgabe, sie FILTERT nichts.

        Zusaetzlich wird gezaehlt, wie viele Zeitstempel in MILLISEKUNDEN
        vorliegen. Das ist keine Spitzfindigkeit: ein Millisekundenwert, der
        als Sekunden gelesen wird, landet im Jahr 57000 und faellt in jeder
        Monatsauswertung als eigener Eimer auf, ohne dass jemand die Ursache
        sieht.
        """
        je_monat: Dict[str, int] = {}
        vor = ab = ohne = 0
        ms = 0
        werte: List[int] = []
        for z in zeilen:
            roh = z["ts"]
            if ist_millisekunden(roh):
                ms += 1
            n = sekunden(roh)
            je_monat[monat(roh)] = je_monat.get(monat(roh), 0) + 1
            if n is None:
                ohne += 1
                continue
            werte.append(n)
            if n < PRODUKTIVBETRIEB_AB:
                vor += 1
            else:
                ab += 1
        return {
            "je_monat": dict(sorted(je_monat.items())),
            "vor_produktivbetrieb": vor,
            "ab_produktivbetrieb": ab,
            "ohne_zeitstempel": ohne,
            "in_millisekunden": ms,
            "frueheste": zeit(min(werte)) if werte else None,
            "spaeteste": zeit(max(werte)) if werte else None,
            "trennlinie": zeit(PRODUKTIVBETRIEB_AB),
        }

    # -- M8 ------------------------------------------------------------------

    def _kennung_klasse(self, wert) -> str:
        """
        Einordnung einer Kennung aus 'created_by'.

        DREI KLASSEN, und die Reihenfolge der Pruefung ist wesentlich:
          'ausgenommen' - Form waere gueltig, die Kennung gehoert aber
                          nachweislich zum Entwicklungs- oder Testbetrieb.
                          MUSS VOR der Formpruefung stehen, sonst faellt
                          'H0A2898' als gueltige Ermittlerkennung durch.
          'gueltig'     - beginnt mit 'H0' oder 'h0'.
          'ungueltig'   - alles Uebrige, EINSCHLIESSLICH leer und NULL.
                          Weisung Alex, 02.09.2026: solche Treffer sollten
                          gar nicht auftauchen und sind Relikte aus dem
                          Entwicklungszeitraum.
        """
        if wert is None:
            return "ungueltig"
        w = str(wert).strip()
        if w == "":
            return "ungueltig"
        if (kennung_normal(w) in self._ausgenommen_normal
                or _RE_KENNUNG_UID.match(w)):
            return "ausgenommen"
        if _RE_KENNUNG_GUELTIG.match(w):
            return "gueltig"
        return "ungueltig"

    def _m8(self, zeilen: List[sqlite3.Row]) -> Dict[str, Any]:
        """
        Wer hat markiert - und ist das Ermittlerarbeit oder Testbetrieb?

        WOZU: Der Testbestand 2948078 traegt 82 Zeilen, also 16 Prozent aller
        Annotationen. Ihn pauschal zu verwerfen waere falsch - dort hat die
        Chefermittlerin eine Arbeitssimulation gefahren, deren Ergebnisse
        wertvoll sind und die zu bewahren sind (Weisung Alex, 03.09.2026).
        Ihn pauschal zu behalten waere ebenso falsch. DIE TRENNLINIE LAEUFT
        NICHT UEBER DEN BESTAND UND NICHT UEBER DIE ZEIT, SONDERN UEBER DIE
        KENNUNG.

        GRUPPIERT WIRD UEBER DIE GROSSFORM, ausgewiesen wird die Rohform.
        Beides ist noetig: ohne Normalisierung stehen 'H082317' und
        'h082317' als zwei Personen nebeneinander, ohne die Rohform liesse
        sich die Abweichung anschliessend nicht mehr belegen.

        Die Zeitverteilung wird je Kennung mitgefuehrt, weil beides zusammen
        mehr sagt als jedes fuer sich: eine gueltige Kennung, die
        ausschliesslich vor dem 01.07.2026 gearbeitet hat, ist ein anderer
        Fall als eine, die durchgehend gearbeitet hat.
        """
        je_wert: Dict[str, Dict[str, Any]] = {}
        klassen = {"gueltig": 0, "ausgenommen": 0, "ungueltig": 0}
        leer_oder_null = 0
        for z in zeilen:
            roh = z["created_by"]
            if roh is None or str(roh).strip() == "":
                leer_oder_null += 1
                roh_form = "(leer oder NULL)"
                schl = "(LEER ODER NULL)"
            else:
                roh_form = str(roh).strip()
                schl = kennung_normal(roh)
            kl = self._kennung_klasse(roh)
            klassen[kl] += 1
            eintrag = je_wert.setdefault(schl, {
                "wert": schl, "klasse": kl, "anzahl": 0,
                "vor_produktivbetrieb": 0, "ab_produktivbetrieb": 0,
                "ohne_zeitstempel": 0, "frueheste": None, "spaeteste": None,
                "schreibweisen": {}})
            eintrag["anzahl"] += 1
            sw = eintrag["schreibweisen"].setdefault(
                roh_form, {"roh": roh_form, "anzahl": 0, "ids": []})
            sw["anzahl"] += 1
            if len(sw["ids"]) < 100:
                sw["ids"].append(z["id"])
            n = sekunden(z["ts"])
            if n is None:
                eintrag["ohne_zeitstempel"] += 1
            else:
                if n < PRODUKTIVBETRIEB_AB:
                    eintrag["vor_produktivbetrieb"] += 1
                else:
                    eintrag["ab_produktivbetrieb"] += 1
                if eintrag["frueheste"] is None or n < eintrag["frueheste"]:
                    eintrag["frueheste"] = n
                if eintrag["spaeteste"] is None or n > eintrag["spaeteste"]:
                    eintrag["spaeteste"] = n

        # Kennungen, die in MEHR ALS EINER Schreibweise vorkommen, und die
        # Zeilen, deren Rohform von der Produktivform abweicht.
        #
        # WARUM DAS EIN BEFUND IST: Die Rechtepruefung vergleicht die Kennung
        # des Anmeldenden mit 'created_by'. Weichen sie in der Schreibweise
        # ab, gelten die Eintraege nicht als eigene - die Person kann ihre
        # eigenen Annotationen weder bearbeiten noch loeschen. Das
        # Produktivsystem bezieht die Kennungen aus dem Active Directory und
        # verwendet ausschliesslich Grossbuchstaben.
        mehrfach: List[Dict[str, Any]] = []
        abweichend: List[Dict[str, Any]] = []
        for e in je_wert.values():
            formen = sorted(e["schreibweisen"])
            e["schreibweisen"] = sorted(e["schreibweisen"].values(),
                                        key=lambda d: -d["anzahl"])
            if len(formen) > 1:
                mehrfach.append({"kennung": e["wert"], "schreibweisen": formen,
                                 "anzahl": e["anzahl"]})
            for sw in e["schreibweisen"]:
                # NUR BEI GUELTIGEN KENNUNGEN. Das Rechteproblem entsteht
                # daraus, dass die Person im Active Directory ein Konto hat
                # und die Rechtepruefung zeichengenau gegen 'created_by'
                # vergleicht. Eine ungueltige Kennung ('pruefer', leer) hat
                # kein AD-Konto - dort gibt es niemanden, der ausgesperrt
                # wuerde, und eine Meldung waere blosses Rauschen.
                if (sw["roh"] != e["wert"] and e["klasse"] == "gueltig"):
                    abweichend.append({
                        "kennung": e["wert"], "roh": sw["roh"],
                        "anzahl": sw["anzahl"], "ids": sw["ids"][:50]})
            e["frueheste"] = zeit(e["frueheste"]) if e["frueheste"] else None
            e["spaeteste"] = zeit(e["spaeteste"]) if e["spaeteste"] else None
        return {
            "je_wert": sorted(je_wert.values(), key=lambda d: -d["anzahl"]),
            "verschiedene_kennungen": len(je_wert),
            "gueltige_kennung": klassen["gueltig"],
            "ausgenommen": klassen["ausgenommen"],
            "ungueltige_kennung": klassen["ungueltig"],
            "leer_oder_null": leer_oder_null,
            "ausschlussliste": list(self.ausgenommen),
            "mehrfachschreibweisen": mehrfach,
            "abweichende_schreibweise": abweichend,
            "zeilen_mit_abweichender_schreibweise": sum(
                d["anzahl"] for d in abweichend),
        }

    # -- M9 ------------------------------------------------------------------

    def _m9(self, zeilen: List[sqlite3.Row]) -> Dict[str, Any]:
        """
        Die beiden Annotationsvarianten - und ob sie sich wirklich ausschliessen.

        BELEG FUER DIE UNTERSCHEIDUNG (Alex, 02.09.2026): Es gab zwei Arten,
        eine Annotation zu setzen.
          Variante 1 'whole post'  - ein vollstaendiger Beitrag wird markiert.
                                     Kein selection_json, nur post_id. Das war
                                     die erste Bauform.
          Variante 2 'text range'  - eine Textpassage wird markiert. Erzeugt
                                     selection_json, urspruenglich ohne post_id.

        Build 755 hat den Verdacht aufgebracht, weil je Bestand die Zahl der
        Zeilen mit element_id EXAKT der Zahl mit selection_json IS NULL
        entsprach (14/14, 2/2, 3/3). GLEICHE ANZAHL IST ABER KEIN BEWEIS
        FUER GLEICHE ZEILEN. Alex hat es fuer die drei Bestaende von Hand
        nachgeprueft (je 0 Zeilen mit beidem). Diese Messung nimmt ihm die
        Handarbeit ab und fuehrt sie fuer ALLE Bestaende.

        SELECTION_JSON UND POST_ID ZUGLEICH IST KEIN FEHLER. Alex' Angabe
        vom 02.09.2026: Variante 2 wurde "vor ein paar Tagen ueberarbeitet" -
        seither wird die post_id nachgetragen. Eine Zeile mit beidem ist also
        eine Variante-2-Zeile MIT bereits nachgetragenem Ort, und nach
        Etappe 4 soll das der Normalfall sein. Sie bekommt deshalb eine
        eigene Klasse und keine Beanstandung.

        BEANSTANDET WIRD NUR 'weder noch': keine Textauswahl und kein Ort.
        Aus einer solchen Zeile ist nicht zu ermitteln, worauf sie sich
        bezieht. Diese Faelle werden namentlich ausgewiesen - eine Zaehlung
        ohne Zeilennummer koennte niemand nachpruefen.
        """
        whole_post = ohne_ort = mit_ort = weder_noch = 0
        weder_ids: List[int] = []
        for z in zeilen:
            hat_sel = (z["selection_json"] is not None
                       and str(z["selection_json"]).strip() != "")
            hat_ort = (z["post_id"] is not None
                       or (z["element_id"] is not None
                           and str(z["element_id"]).strip() != ""))
            if hat_sel and hat_ort:
                mit_ort += 1
            elif hat_sel:
                ohne_ort += 1
            elif hat_ort:
                whole_post += 1
            else:
                weder_noch += 1
                weder_ids.append(z["id"])
        return {
            "whole_post": whole_post,
            "text_range_ohne_ort": ohne_ort,
            "text_range_mit_ort": mit_ort,
            "text_range": ohne_ort + mit_ort,
            "weder_noch": weder_noch,
            "weder_noch_ids": weder_ids[:50],
        }

    # -- M7 ------------------------------------------------------------------

    @staticmethod
    def _seite_finden(con_f: sqlite3.Connection, url: str):
        """
        Die Kopfdaten der GET-Seite zu einer Adresse.

        DIE VIER ABFRAGEN UND IHRE REIHENFOLGE SIND WORTGLEICH DIE AUS
        management/maintenance/postid_nachtrag._blob() und
        tools/annotationen_verifizieren._blob(). Nur die Spaltenliste ist eine
        andere: statt 'html' werden typeof(html), length(html) und die
        Kopfdaten gelesen. Eine Bestandsaufnahme, die eine ANDERE Seite
        findet als die Auswertung, zaehlt etwas anderes als das, worueber
        danach entschieden wird - genau dieser Fehler ist in Build 754 als
        Grundsatz festgehalten worden.

        DIE SPALTE 'html' WIRD NICHT GELESEN. length() und typeof() werden von
        SQLite auf dem Spaltenkopf ausgewertet; der BLOB-Inhalt kommt nicht in
        den Speicher dieses Vorgangs.
        """
        # ZWEI AUSGESCHRIEBENE FELDLISTEN statt einer per Textersetzung
        # praeparierten: die JOIN-Abfragen brauchen den Tabellenpraefix 'p.',
        # die einfachen nicht. Eine Ersetzung auf der Zeichenkette haette bei
        # jeder kuenftigen Spalte, deren Name 'id,' enthaelt, still das
        # Falsche getan.
        felder_einfach = (
            "id, url_canonical, typeof(html) AS htyp, length(html) AS hlen, "
            "http_status, title, fetched_at")
        felder_join = (
            "p.id AS id, p.url_canonical AS url_canonical, "
            "typeof(p.html) AS htyp, length(p.html) AS hlen, "
            "p.http_status AS http_status, p.title AS title, "
            "p.fetched_at AS fetched_at")
        for sql, par in (
            ("SELECT %s FROM pages WHERE url_canonical = ? AND "
             "method = 'GET' LIMIT 1" % felder_einfach, (url,)),
            ("SELECT %s FROM pages p JOIN page_aliases a ON a.page_id = p.id "
             "WHERE a.url_raw = ? AND p.method = 'GET' LIMIT 1"
             % felder_join, (url,)),
            ("SELECT %s FROM pages WHERE url_canonical LIKE ? AND "
             "method = 'GET' LIMIT 1" % felder_einfach, ("%" + url,)),
            ("SELECT %s FROM pages p JOIN page_aliases a ON a.page_id = p.id "
             "WHERE a.url_raw LIKE ? AND p.method = 'GET' LIMIT 1"
             % felder_join, ("%" + url,)),
        ):
            try:
                z = con_f.execute(sql, par).fetchone()
            except sqlite3.Error:
                continue
            if z is not None:
                return z
        return None

    def _m7(self, zeilen: List[sqlite3.Row]) -> Dict[str, Any]:
        """
        Kopfdaten der Seiten - und die Zuordnung Annotation -> Seite.

        Der BLOB-INHALT wird nicht gelesen. Gemessen wird, was ohne ihn
        feststellbar ist: gibt es die Seite ueberhaupt, wie lang ist sie, mit
        welchem Status wurde sie geholt und welchen Titel traegt sie.
        """
        erg: Dict[str, Any] = {"vorhanden": False}
        if not self.forensic_pfad:
            erg["hinweis"] = "kein forensic-Pfad uebergeben"
            return erg
        if not os.path.exists(self.forensic_pfad):
            erg["hinweis"] = ("forensic_<uid>.db gibt es nicht: %s"
                              % self.forensic_pfad)
            return erg
        try:
            con_f = self._oeffne_ro(self.forensic_pfad)
        except sqlite3.Error as exc:
            erg["hinweis"] = "forensic_<uid>.db nicht zu oeffnen: %s" % exc
            return erg
        self._befund.forensic_lesbar = True
        erg["vorhanden"] = True
        try:
            seiten = list(con_f.execute(
                "SELECT id, url_canonical, method, typeof(html) AS htyp, "
                "       length(html) AS hlen, http_status, title, fetched_at "
                "FROM pages"))
            typen: Dict[str, int] = {}
            status: Dict[str, int] = {}
            titel: Dict[str, int] = {}
            laengen: List[int] = []
            null_html = leer_html = 0
            for s in seiten:
                t = str(s["htyp"])
                typen[t] = typen.get(t, 0) + 1
                st = str(s["http_status"])
                status[st] = status.get(st, 0) + 1
                ti = str(s["title"] or "(kein Titel)")
                titel[ti] = titel.get(ti, 0) + 1
                laenge = s["hlen"]
                if laenge is None:
                    null_html += 1
                else:
                    laengen.append(int(laenge))
                    if int(laenge) == 0:
                        leer_html += 1
            erg["seiten_gesamt"] = len(seiten)
            erg["html_typ"] = dict(sorted(typen.items(), key=lambda p: -p[1]))
            erg["html_null"] = null_html
            erg["html_leer"] = leer_html
            erg["http_status"] = dict(sorted(status.items(),
                                             key=lambda p: -p[1]))
            erg["laenge"] = _kennzahlen(laengen)
            erg["titel_haeufigste"] = sorted(
                ({"titel": t, "seiten": n} for t, n in titel.items()),
                key=lambda d: -d["seiten"])[:10]
            erg["kuerzeste_seiten"] = [
                {"id": s["id"], "url": s["url_canonical"],
                 "method": s["method"],
                 "laenge": s["hlen"], "http_status": s["http_status"],
                 "titel": s["title"], "erstellt": zeit(s["fetched_at"])}
                for s in sorted(
                    seiten, key=lambda r: (r["hlen"] is not None,
                                           r["hlen"] or 0))[:self.kuerzeste]]

            # Zuordnung: fuer jede VERSCHIEDENE Adresse aus 'annotations'
            # einmal nachschlagen - nicht je Annotation. Bei 260 Annotationen
            # auf 40 Seiten waeren das sonst 220 ueberfluessige Abfragen.
            je_url: Dict[str, int] = {}
            for z in zeilen:
                u = str(z["page_url"] or "")
                je_url[u] = je_url.get(u, 0) + 1
            mit = ohne = 0
            ann_mit = ann_ohne = ann_leer = 0
            fehlende: List[Dict[str, Any]] = []
            auf_leerer: List[Dict[str, Any]] = []
            for u, n in sorted(je_url.items()):
                treffer = self._seite_finden(con_f, u) if u else None
                if treffer is None:
                    ohne += 1
                    ann_ohne += n
                    fehlende.append({"url": u, "annotationen": n})
                    continue
                mit += 1
                ann_mit += n
                if treffer["hlen"] in (None, 0):
                    ann_leer += n
                    auf_leerer.append({
                        "url": u, "annotationen": n,
                        "page_id": treffer["id"],
                        "laenge": treffer["hlen"],
                        "http_status": treffer["http_status"],
                        "titel": treffer["title"],
                        "erstellt": zeit(treffer["fetched_at"])})
            erg["adressen_mit_seite"] = mit
            erg["adressen_ohne_seite"] = ohne
            erg["annotationen_mit_seite"] = ann_mit
            erg["annotationen_ohne_seite"] = ann_ohne
            erg["annotationen_auf_leerer_seite"] = ann_leer
            erg["fehlende_adressen"] = fehlende
            erg["leere_seiten_mit_annotationen"] = auf_leerer
        finally:
            con_f.close()
        return erg
