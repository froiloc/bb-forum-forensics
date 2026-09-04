# -*- coding: utf-8 -*-
# =============================================================================
# management/maintenance/anker_inventar.py
# IT-Forensisches Ermittlungswerkzeug - Etappe 1: Inventar der Ankerpunkte
# =============================================================================
# Zweck:
#   WELCHE FESTEN ANKERPUNKTE STEHEN IN DEN SEITEN-BLOBS WIRKLICH DRIN?
#   Etappe 0 hat gezaehlt, was in den Annotationen steht, und den BLOB-Inhalt
#   bewusst nicht angefasst. Diese Sperre ist aufgehoben: hier wird der BLOB
#   zerlegt und gegen die Annotationen gehalten.
#
#   Vier Messbloecke:
#     A  Behaelter-Inventar   - welche Elemente tragen 'id="p<n>"'?
#     B  Anker je Behaelter   - Beitragstext, Verfasser, Zeitstempel
#     C  Aufloesung           - wohin zeigen die gespeicherten Ausdruecke?
#     D  Gegenprobe Wortlaut  - wo sie nicht aufloesen: liegt es am Baum?
#
# ── WAS DER FORENQUELLTEXT VORGIBT (Etappe 1, Quelltextteil) ────────────────
#
#   Geruest, include/template/main.tpl Z. 30-32:
#     <body> <donate> <div id="wrap"> [#brdleft, #page-header,
#            (<pun_announcement>), #page-body, #page-footer]
#   Der Platzhalter wird in header0.php Z. 711 nur dann durch
#   '<div id="announce">' ersetzt, wenn o_announcement gesetzt ist. Im
#   vorliegenden Forum ist das nicht der Fall (Angabe Alex, 03.09.2026: das
#   Forum ist postmortem, Schalter werden nicht mehr umgelegt).
#
#   Beitragsbehaelter - FUENF Renderer, ausgewaehlt in viewtopic.php Z. 613:
#     posts.type == 3          -> include/type3.php      <article class="post">
#     topics.type == 2         -> include/gallery.php    (kommt nicht vor:
#                                 topics.type ist durchgaengig 0)
#     posts.type == 4          -> include/type4.php      <article class="systempost">
#     sonst (0, 1, 5)          -> include/viewtopic0.php DREI Formen, s.u.
#     users.group_id == 4      -> include/viewtopic1.php <div class="box typeN">
#                                 (Umleitung in viewforum.php Z. 25)
#     PN                       -> include/pms_new/mdl/topic.php
#                                 <div class="blockpost" id="p<n>">
#
#   viewtopic0.php enthaelt drei Behaelterformen:
#     Z. 351  <article class="systempost" id="p<n>">
#     Z. 886  <article class="post"       id="p<n>">
#     Z. 975  <div     class="box"        id="pp<n>">   <-- DOPPELTES 'p'
#
#   ZEILE 975 IST EIN FEHLER IM ORIGINALCODE: dort steht
#   'id="p<?php echo 'p'.$cur_post['id'];?>"' - das 'p' einmal als Literal
#   und einmal in der Ausgabe. Ein Zerleger mit '^p(\\d+)$' verlaengert diesen
#   Zweig stillschweigend. Das Muster MUSS '^p+(\\d+)$' lauten; dieselbe Form
#   benutzen bereits db/forensic_db.py (_anker_muster), der PostPageMeasurer
#   des Preppers und toolbar.js (_POST_KENNUNG).
#
#   MEHRDEUTIGKEIT BEI '.postmsg': In pms_new/mdl/topic.php traegt die
#   Signatur die Klasse 'postsignature postmsg'. Ein Selektor, der
#   'postmsg' enthaelt, trifft je Beitrag ZWEIMAL. Der Ausdruck aus der
#   Weisung Alex vom 03.09.2026 -
#       div[@class='postright']/div[@class='postmsg'][1]
#   - trifft nur den Beitragstext, weil er das Attribut EXAKT vergleicht.
#   'contains(@class,"postmsg")' taete es nicht.
#
# ── WAS DIESES WERKZEUG NICHT TUT ───────────────────────────────────────────
#
#   Es schreibt nichts. Weisung Alex, 03.09.2026: bis Etappe 4 wird
#   ausschliesslich gelesen. Alle Verbindungen laufen ueber 'mode=ro'.
#
# Version: 0.8.758 - Build 758
# =============================================================================

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

#: Beitragskennung. '^p+(\d+)$' und NICHT '^p(\d+)$' - siehe Kopfkommentar.
#: Gruppe 1 haelt die Praefixe, Gruppe 2 die Nummer.
RE_BEITRAGSKENNUNG = re.compile(r"^(p+)(\d+)$")

#: Der Beitragstext laut Weisung Alex, 03.09.2026. EXAKTER Attributvergleich.
XPATH_BEITRAGSTEXT = "div[@class='postright']/div[@class='postmsg']"

#: Weitere Stellen, an denen ein Beitragstext stehen kann. Die Reihenfolge
#: ist die der Pruefung; gemeldet wird, WELCHE getroffen hat.
XPATH_TEXT_ALTERNATIVEN: Tuple[Tuple[str, str], ...] = (
    ("postright_postmsg", ".//div[@class='postright']/div[@class='postmsg']"),
    ("postmsg_direkt", ".//div[@class='postmsg']"),
    ("entry_content", ".//div[contains(@class,'entry-content')]"),
    ("tabellenzelle", ".//td"),
)

#: Verfasser und Zeitstempel.
XPATH_VERFASSER: Tuple[Tuple[str, str], ...] = (
    ("postleft_strong", ".//div[@class='postleft']//dt//strong"),
    ("postleft_beliebig", ".//div[contains(@class,'postleft')]//strong"),
    ("author_klasse", ".//*[contains(@class,'author')]"),
)
XPATH_ZEITSTEMPEL: Tuple[Tuple[str, str], ...] = (
    ("h2_link", "./h2//a[contains(@href,'pid=')]"),
    ("beliebiger_pid_link", ".//a[contains(@href,'pid=')]"),
    ("permalink_klasse", ".//*[contains(@class,'permalink')]"),
)


def kennung_zerlegen(wert) -> Optional[Tuple[str, int]]:
    """('pp', 1234) aus 'pp1234'. None, wenn es keine Beitragskennung ist."""
    if wert is None:
        return None
    m = RE_BEITRAGSKENNUNG.match(str(wert).strip())
    if m is None:
        return None
    return m.group(1), int(m.group(2))


def body_ausschneiden(html: bytes) -> str:
    """
    Der Inhalt zwischen <body> und </body>.

    WORTGLEICH die Logik aus server/blob_handler._extract_body(). Die
    Uebereinstimmung ist Absicht: der Browser bekommt genau diesen
    Ausschnitt in '#forensic-viewport' gesetzt, und die gespeicherten
    XPath-Ausdruecke sind relativ dazu. Wer hier anders schneidet, misst
    einen anderen Baum als den, in dem der Ermittler markiert hat.
    """
    text = html.decode("utf-8", errors="replace") if isinstance(html, bytes) \
        else str(html or "")
    anfang = text.lower().find("<body")
    if anfang == -1:
        return text
    tag_ende = text.find(">", anfang)
    if tag_ende == -1:
        return text
    inhalt = tag_ende + 1
    ende = text.lower().rfind("</body>")
    if ende == -1:
        return text[inhalt:]
    return text[inhalt:ende]


@dataclass
class Inventarbefund:
    """Das Ergebnis EINES Bestands."""
    uid: str
    fehler: List[str] = field(default_factory=list)
    a_behaelter: Dict[str, Any] = field(default_factory=dict)
    b_anker: Dict[str, Any] = field(default_factory=dict)
    c_aufloesung: Dict[str, Any] = field(default_factory=dict)
    d_wortlaut: Dict[str, Any] = field(default_factory=dict)
    seiten: Dict[str, Any] = field(default_factory=dict)

    def als_dict(self) -> Dict[str, Any]:
        return {"uid": self.uid, "fehler": list(self.fehler),
                "a_behaelter": self.a_behaelter, "b_anker": self.b_anker,
                "c_aufloesung": self.c_aufloesung,
                "d_wortlaut": self.d_wortlaut, "seiten": self.seiten}


class AnkerInventar:
    """
    Zerlegt die Seiten-BLOBs eines Bestands und haelt sie gegen die
    Annotationen. Rein lesend, beide Verbindungen 'mode=ro'.
    """

    def __init__(self, uid: str, evidence_pfad: str, forensic_pfad: str,
                 beispiele: int = 20) -> None:
        self.uid = str(uid)
        self.evidence_pfad = evidence_pfad
        self.forensic_pfad = forensic_pfad
        self.beispiele = max(0, int(beispiele))
        self._befund = Inventarbefund(uid=self.uid)
        self._zerleger = None

    # -- Werkzeug ------------------------------------------------------------

    @staticmethod
    def _ro(pfad: str) -> sqlite3.Connection:
        con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def _baum(self, body_html: str):
        """
        Der Baum zu einem Body-Ausschnitt, ueber den Zerleger des Projekts.

        ES GIBT KEINEN RUECKFALL AUF EINEN ANDEREN ZERLEGER. html5lib fuehrt
        denselben Baumaufbau aus wie die Blink-Engine, die den Ausdruck
        erzeugt hat; libxml2 oder html.parser kennen den HTML5-Aufbau nicht
        und lieferten uebereinstimmend das falsche Ergebnis - eine
        Uebereinstimmung, die man faelschlich als Entlastung lesen wuerde.
        Gemessen an 17 Konstrukten gegen Chromium (31.08.2026): lxml roh 7,
        lxml mit Teilnachbau 16, html5lib 17. Beleg:
        management/maintenance/anker_diagnose.py Z. 468-475.
        """
        if self._zerleger is None:
            from report_render.html5_zerleger import Html5Zerleger
            self._zerleger = Html5Zerleger()
        return self._zerleger.zerlege(body_html)

    @staticmethod
    def _seite_holen(con_f: sqlite3.Connection, url: str):
        """
        Die GET-Seite zu einer Adresse, MIT Inhalt.

        Die vier Abfragen und ihre Reihenfolge sind wortgleich die aus
        management/maintenance/postid_nachtrag._blob() und
        tools/annotationen_bestand._seite_finden(). Ein Werkzeug, das eine
        ANDERE Seite findet als die Auswertung, misst etwas anderes als das,
        worueber danach entschieden wird.
        """
        einfach = "id, url_canonical, html, http_status, title, fetched_at"
        verbund = ("p.id AS id, p.url_canonical AS url_canonical, "
                   "p.html AS html, p.http_status AS http_status, "
                   "p.title AS title, p.fetched_at AS fetched_at")
        for sql, par in (
            ("SELECT %s FROM pages WHERE url_canonical = ? AND "
             "method = 'GET' LIMIT 1" % einfach, (url,)),
            ("SELECT %s FROM pages p JOIN page_aliases a ON a.page_id = p.id "
             "WHERE a.url_raw = ? AND p.method = 'GET' LIMIT 1"
             % verbund, (url,)),
            ("SELECT %s FROM pages WHERE url_canonical LIKE ? AND "
             "method = 'GET' LIMIT 1" % einfach, ("%" + url,)),
            ("SELECT %s FROM pages p JOIN page_aliases a ON a.page_id = p.id "
             "WHERE a.url_raw LIKE ? AND p.method = 'GET' LIMIT 1"
             % verbund, ("%" + url,)),
        ):
            try:
                z = con_f.execute(sql, par).fetchone()
            except sqlite3.Error:
                continue
            if z is not None:
                return z
        return None

    # -- Hauptlauf -----------------------------------------------------------

    def erheben(self) -> Inventarbefund:
        b = self._befund
        for pfad, name in ((self.evidence_pfad, "evidence"),
                           (self.forensic_pfad, "forensic")):
            if not os.path.exists(pfad):
                b.fehler.append("%s_<uid>.db gibt es nicht: %s" % (name, pfad))
                return b
        try:
            from report_render.html5_zerleger import Html5Zerleger
            if not Html5Zerleger.verfuegbar():
                b.fehler.append("html5lib fehlt - kein Rueckfall vorgesehen")
                return b
        except ImportError as exc:
            b.fehler.append("Zerleger nicht ladbar: %s" % exc)
            return b

        con_e = self._ro(self.evidence_pfad)
        con_f = self._ro(self.forensic_pfad)
        try:
            zeilen = list(con_e.execute(
                "SELECT id, page_url, element_id, post_id, selection_json, "
                "       created_by, deleted_at, prev_id "
                "FROM annotations ORDER BY id"))
            # Nur die AKTUELLEN Zeilen. Ueberholte Generationen zeigen auf
            # denselben Ort wie ihre Nachfolger; sie doppelt zu messen
            # verzerrte jede Quote.
            vorgaenger = {z["prev_id"] for z in zeilen
                          if z["prev_id"] is not None}
            aktuell = [z for z in zeilen
                       if z["deleted_at"] is None
                       and z["id"] not in vorgaenger]
            self._lauf(con_f, aktuell)
        finally:
            con_e.close()
            con_f.close()
        return b

    def _lauf(self, con_f, zeilen) -> None:
        b = self._befund
        # Je Adresse EINMAL zerlegen. Bei 272 Annotationen auf 40 Seiten
        # waeren 232 Zerlegungen ueberfluessig, und eine Zerlegung ist der
        # teuerste Einzelschritt dieses Werkzeugs.
        je_url: Dict[str, List] = {}
        for z in zeilen:
            je_url.setdefault(str(z["page_url"] or ""), []).append(z)

        a = {"seiten_zerlegt": 0, "seiten_ohne_treffer": 0,
             "behaelter_gesamt": 0, "praefix": {}, "elementnamen": {},
             "klassen": {}, "mehrfache_nummern": [], "ohne_behaelter": []}
        bb = {"behaelter_geprueft": 0, "text": {}, "verfasser": {},
              "zeitstempel": {}, "text_mehrfach": 0,
              "ohne_text": [], "ohne_verfasser": [], "ohne_zeit": []}
        c = {"mit_ausdruck": 0, "aufgeloest": 0, "kein_knoten": 0,
             "knoten_ohne_behaelter": 0, "post_id_bestimmt": 0,
             "whole_post": 0, "whole_post_behaelter_da": 0,
             "whole_post_behaelter_fehlt": [], "beispiele": []}
        d = {"geprueft": 0, "wortlaut_eindeutig": 0, "wortlaut_mehrfach": 0,
             "wortlaut_nirgends": 0, "faelle": []}
        seiten = {"adressen": len(je_url), "ohne_seite": 0, "ohne_inhalt": 0}

        for url, gruppe in sorted(je_url.items()):
            treffer = self._seite_holen(con_f, url) if url else None
            if treffer is None:
                seiten["ohne_seite"] += 1
                continue
            if not treffer["html"]:
                seiten["ohne_inhalt"] += 1
                continue
            try:
                wurzel, _befunde = self._baum(body_ausschneiden(treffer["html"]))
            except Exception as exc:                      # noqa: BLE001
                b.fehler.append("Zerlegung fehlgeschlagen fuer %s: %s"
                                % (url, exc))
                continue
            a["seiten_zerlegt"] += 1
            behaelter = self._behaelter_sammeln(wurzel, a, url)
            self._anker_pruefen(behaelter, bb)
            self._aufloesen(wurzel, behaelter, gruppe, c, d, url)

        b.a_behaelter, b.b_anker = a, bb
        b.c_aufloesung, b.d_wortlaut, b.seiten = c, d, seiten

    # -- Block A -------------------------------------------------------------

    def _behaelter_sammeln(self, wurzel, a: Dict[str, Any],
                           url: str) -> Dict[int, Any]:
        """
        Alle Elemente mit einer Beitragskennung, nach Nummer.

        DER ELEMENTNAME WIRD ERFASST, ABER NICHT ZUR IDENTIFIKATION BENUTZT.
        Weisung Alex, 03.09.2026: die Kennung reicht, gleich welches Element
        sie traegt. Der Name steht nur in der Auswertung, damit sichtbar
        wird, welcher Renderer die Seite erzeugt hat - <article class="post">
        aus viewtopic0.php Z. 886, <article class="systempost"> aus
        type4.php, <div class="blockpost"> aus pms_new/mdl/topic.php.

        MEHRFACHE NUMMERN SIND ZU ERWARTEN und kein Fehler: viewtopic0.php
        verschachtelt einen aeusseren 'p<n>' und einen inneren 'pp<n>'. Beide
        meinen denselben Beitrag. Gemeldet wird nur, wenn dieselbe Nummer
        mit demselben Praefix mehrfach vorkommt - DAS waere ein Fehler.
        """
        gefunden: Dict[int, Any] = {}
        je_nummer: Dict[int, List[str]] = {}
        for el in wurzel.iter():
            kennung = el.get("id") if hasattr(el, "get") else None
            zerlegt = kennung_zerlegen(kennung)
            if zerlegt is None:
                continue
            praefix, nummer = zerlegt
            a["behaelter_gesamt"] += 1
            a["praefix"][praefix] = a["praefix"].get(praefix, 0) + 1
            name = str(getattr(el, "tag", "?"))
            a["elementnamen"][name] = a["elementnamen"].get(name, 0) + 1
            for k in str(el.get("class") or "").split():
                a["klassen"][k] = a["klassen"].get(k, 0) + 1
            je_nummer.setdefault(nummer, []).append(praefix)
            # Der AEUSSERE Behaelter gewinnt. Er wird zuerst durchlaufen
            # (iter() geht in Dokumentreihenfolge) und umschliesst den
            # inneren; fuer die Zuordnung eines Knotens zu einem Beitrag ist
            # das die weitere und damit sichere Wahl.
            if nummer not in gefunden:
                gefunden[nummer] = el
        for nummer, praefixe in je_nummer.items():
            for p in set(praefixe):
                if praefixe.count(p) > 1:
                    a["mehrfache_nummern"].append(
                        {"url": url, "nummer": nummer, "praefix": p,
                         "anzahl": praefixe.count(p)})
        if not gefunden:
            a["seiten_ohne_treffer"] += 1
            if len(a["ohne_behaelter"]) < self.beispiele:
                a["ohne_behaelter"].append(url)
        return gefunden

    # -- Block B -------------------------------------------------------------

    @staticmethod
    def _erster_treffer(el, kandidaten) -> Tuple[Optional[str], int]:
        """(Name des ersten greifenden Ausdrucks, Trefferzahl)."""
        for name, ausdruck in kandidaten:
            try:
                treffer = el.xpath(ausdruck)
            except Exception:                             # noqa: BLE001
                continue
            if treffer:
                return name, len(treffer)
        return None, 0

    def _anker_pruefen(self, behaelter: Dict[int, Any],
                       bb: Dict[str, Any]) -> None:
        """
        Traegt jeder Behaelter Beitragstext, Verfasser und Zeitstempel?

        Das entscheidet, welche Metadaten Etappe 2 ueberhaupt in das neue
        selection_json schreiben kann. type4.php enthaelt kein einziges
        'postmsg' - Systembeitraege geben ihren Text in <td>-Zellen aus
        (viewtopic0.php Z. 354). Bei 27.346 Beitraegen mit posts.type=4 ist
        das keine Randerscheinung, und ein Werkzeug, das nur '.postmsg'
        kennt, faende dort nichts.
        """
        for nummer, el in behaelter.items():
            bb["behaelter_geprueft"] += 1
            name, anzahl = self._erster_treffer(el, XPATH_TEXT_ALTERNATIVEN)
            bb["text"][name or "(keiner)"] = \
                bb["text"].get(name or "(keiner)", 0) + 1
            if name is None and len(bb["ohne_text"]) < self.beispiele:
                bb["ohne_text"].append(nummer)
            # Der Ausdruck aus der Weisung liefert je Beitrag GENAU EINEN
            # Treffer. Mehr hiesse, dass die Signatur mitgezaehlt wird -
            # dann waere der exakte Attributvergleich unterlaufen.
            if name == "postright_postmsg" and anzahl > 1:
                bb["text_mehrfach"] += 1
            vname, _ = self._erster_treffer(el, XPATH_VERFASSER)
            bb["verfasser"][vname or "(keiner)"] = \
                bb["verfasser"].get(vname or "(keiner)", 0) + 1
            if vname is None and len(bb["ohne_verfasser"]) < self.beispiele:
                bb["ohne_verfasser"].append(nummer)
            zname, _ = self._erster_treffer(el, XPATH_ZEITSTEMPEL)
            bb["zeitstempel"][zname or "(keiner)"] = \
                bb["zeitstempel"].get(zname or "(keiner)", 0) + 1
            if zname is None and len(bb["ohne_zeit"]) < self.beispiele:
                bb["ohne_zeit"].append(nummer)

    # -- Block C und D -------------------------------------------------------

    @staticmethod
    def _behaelter_ueber(knoten, behaelter: Dict[int, Any]) -> Optional[int]:
        """
        Die Beitragsnummer des naechsten Vorfahren mit Beitragskennung.

        Aufstieg statt Suche: der Knoten kann tief in der Nachricht liegen,
        und nur der Weg nach oben sagt, ZU WELCHEM Beitrag er gehoert.
        """
        el = knoten
        # Textknoten aus lxml-XPath sind 'smart strings' mit
        # getparent(); Elementknoten haben es ohnehin.
        if hasattr(el, "getparent") and not hasattr(el, "iter"):
            el = el.getparent()
        while el is not None:
            zerlegt = kennung_zerlegen(el.get("id")
                                       if hasattr(el, "get") else None)
            if zerlegt is not None:
                return zerlegt[1]
            el = el.getparent() if hasattr(el, "getparent") else None
        return None

    def _aufloesen(self, wurzel, behaelter, gruppe, c, d, url) -> None:
        """
        Block C: Wohin zeigen die gespeicherten Ausdruecke?
        Block D: Wo sie nicht aufloesen - liegt es am Baum oder am Ausdruck?

        BLOCK D IST DIE GEGENPROBE ZU EINER OFFENEN FRAGE. Loest ein Ausdruck
        nicht auf, gibt es zwei Erklaerungen: der Baum ist ein anderer als
        beim Markieren (etwa weil der <mark>-Rueckfallweg von toolbar.js
        Z. 1419 Textknoten zerlegt hatte), oder der Ausdruck war nie
        richtig. Steht der gespeicherte Wortlaut trotzdem in genau EINEM
        Behaelter, ist die Markierung inhaltlich einwandfrei und nur ihr
        Weg unbrauchbar - dann traegt der Wortlaut die Zuordnung.
        """
        for z in gruppe:
            roh = z["selection_json"]
            sel = None
            if roh:
                try:
                    geladen = json.loads(roh)
                    sel = geladen if isinstance(geladen, dict) else None
                except (ValueError, TypeError):
                    sel = None
            if sel is None or not sel.get("xpathStart"):
                # Variante 1 'whole post': kein Ausdruck, aber ein Ort.
                # Die Pruefung laeuft umgekehrt - gibt es den Behaelter?
                zerlegt = kennung_zerlegen(z["element_id"])
                nummer = zerlegt[1] if zerlegt else z["post_id"]
                if nummer is None:
                    continue
                c["whole_post"] += 1
                if int(nummer) in behaelter:
                    c["whole_post_behaelter_da"] += 1
                elif len(c["whole_post_behaelter_fehlt"]) < self.beispiele:
                    c["whole_post_behaelter_fehlt"].append(
                        {"id": z["id"], "nummer": int(nummer), "url": url})
                continue

            c["mit_ausdruck"] += 1
            ausdruck = str(sel["xpathStart"])
            try:
                treffer = wurzel.xpath(ausdruck)
            except Exception:                             # noqa: BLE001
                treffer = []
            if not treffer:
                c["kein_knoten"] += 1
                self._wortlaut_gegenprobe(z, sel, behaelter, d, url,
                                          "ausdruck_ohne_knoten")
                continue
            c["aufgeloest"] += 1
            nummer = self._behaelter_ueber(treffer[0], behaelter)
            if nummer is None:
                c["knoten_ohne_behaelter"] += 1
                self._wortlaut_gegenprobe(z, sel, behaelter, d, url,
                                          "knoten_ohne_behaelter")
                continue
            c["post_id_bestimmt"] += 1
            if len(c["beispiele"]) < self.beispiele:
                c["beispiele"].append({"id": z["id"], "post_id": nummer,
                                       "url": url})

    def _wortlaut_gegenprobe(self, z, sel, behaelter, d, url, lage) -> None:
        """Steht der gespeicherte Wortlaut in genau EINEM Behaelter?"""
        d["geprueft"] += 1
        wortlaut = str(sel.get("textContent") or "").strip()
        if not wortlaut:
            d["wortlaut_nirgends"] += 1
            return
        traeger = []
        for nummer, el in behaelter.items():
            try:
                text = "".join(el.itertext())
            except Exception:                             # noqa: BLE001
                continue
            if wortlaut in text:
                traeger.append(nummer)
        if len(traeger) == 1:
            d["wortlaut_eindeutig"] += 1
        elif len(traeger) > 1:
            d["wortlaut_mehrfach"] += 1
        else:
            d["wortlaut_nirgends"] += 1
        if len(d["faelle"]) < self.beispiele:
            d["faelle"].append({
                "id": z["id"], "lage": lage, "url": url,
                "traeger": traeger[:5], "traeger_anzahl": len(traeger),
                "wortlaut_laenge": len(wortlaut)})
