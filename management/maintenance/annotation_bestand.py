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
                 kuerzeste: int = 20) -> None:
        self.uid = str(uid)
        self.evidence_pfad = evidence_pfad
        self.forensic_pfad = forensic_pfad
        self.kuerzeste = max(0, int(kuerzeste))
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

        'SIGNATUR' ist die sortierte Menge der vorhandenen Schluessel. Sie
        beantwortet die Frage, wie viele verschiedene FORMEN im Bestand
        wirklich liegen. Aus dem Quelltext ist das nicht zu beantworten: dort
        stehen zwei Formen (die Fuenf-Feld-Form aus toolbar.js Z. 1129-1135
        und die Uebersetzungsform aus Z. 1115-1126), aber ob im Bestand noch
        weitere liegen, weiss nur der Bestand.

        SINNFREIE MARKEN werden nach zwei getrennten Kriterien gezaehlt:
          * offsetEnd <= offsetStart  - eine Auswahl der Laenge null oder
            eine mit vertauschten Grenzen. Beides traegt keinen Wortlaut.
            Die Gleichheit ist auf Weisung Alex (01.09.2026) eingeschlossen;
            bis Build 754 wurde nur '<' gezaehlt.
          * textContent leer oder nur Leerraum - dasselbe Ergebnis auf dem
            anderen Weg. Beide Zaehler werden getrennt gefuehrt, weil ihre
            Schnittmenge selbst eine Aussage ist.
        """
        null = leer = ungueltig = gueltig = 0
        schluessel: Dict[str, int] = {}
        signaturen: Dict[str, int] = {}
        offset_leer = offset_vertauscht = offset_gleich = 0
        text_leer = text_leerraum = 0
        laengen: List[int] = []
        ohne_offsets = 0
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

            a, e = sel.get("offsetStart"), sel.get("offsetEnd")
            if isinstance(a, int) and isinstance(e, int):
                if e < a:
                    offset_vertauscht += 1
                    offset_leer += 1
                elif e == a:
                    offset_gleich += 1
                    offset_leer += 1
            else:
                ohne_offsets += 1

            txt = sel.get("textContent")
            if txt is None or str(txt) == "":
                text_leer += 1
            elif str(txt).strip() == "":
                text_leerraum += 1
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
            "offset_sinnfrei": offset_leer,
            "offset_vertauscht": offset_vertauscht,
            "offset_gleich": offset_gleich,
            "ohne_offsets": ohne_offsets,
            "textcontent_leer": text_leer,
            "textcontent_nur_leerraum": text_leerraum,
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
