#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# tools/xpath_versatz_messen.py
# IT-Forensisches Ermittlungswerkzeug - Versatz der XPath-Ausdruecke messen
# =============================================================================
# Zweck:
#   Messen, um wie viele BEITRAEGE der in 'annotations.selection_json'
#   gespeicherte XPath-Ausdruck danebenzeigt - und ob dieser Versatz an der
#   ZEIT der Markierung oder an der POSITION auf der Seite haengt.
#
#   ES SCHREIBT NICHTS. Beide Datenbanken werden ueber 'file:...?mode=ro'
#   geoeffnet - schreibgeschuetzt durch die Verbindung und nicht durch
#   Vorsatz. Einem Werkzeug, das schreiben KANN, muss man ansehen, dass es
#   nicht geschrieben hat; diesem sieht man an, dass es nicht konnte.
#
# ── WORAUS ES ENTSTANDEN IST ─────────────────────────────────────────────────
#
#   Browsermessung vom 31.08.2026 (debug/messung_xpath_blink_M1.js) ueber drei
#   Seiten, gefahren in Chrome 151 im Ermittlungsfenster:
#
#     1. Die CSS Custom Highlights API ist verfuegbar und wird benutzt; im
#        Viewport steht KEIN <mark>. Der DOM wird beim Markieren NICHT
#        veraendert.
#     2. Blink und der gesicherte Abzug sehen DENSELBEN Baum - 23 Textknoten
#        im Traegerabsatz hier wie dort, 53 Kinder am Beitragsbehaelter hier
#        wie dort. html5lib bildet Blink ab (Build 747), und beide scheiden
#        als Ursache aus.
#     3. Die gespeicherten Ausdruecke loesen TROTZDEM auch in Blink nicht auf:
#        'text()[24]' bei 23 Textknoten, 'div[54]' bei 53 Kindern.
#     4. Der Fehler sitzt in GENAU EINEM Schritt - dem Index des
#        Beitragsbehaelters. Auf '/forum/pmsnew.php?mdl=topic&tid=64200' ist
#        er 0 fuer die Plaetze 2 und 4 und +1 Beitrag ab Platz 6; auf
#        '...tid=57358' waechst er stufenweise von +2 auf +18. Der Seitenbau
#        ist dabei vollkommen regelmaessig (Elementindex = 2*Platz+3, ohne
#        eine einzige Abweichung).
#     5. Auf einer kurzen Seite ('...tid=19368', 6 Beitraege): 10 von 10
#        richtig, kein Bruch.
#
#   Daraus folgt: der Baum, gegen den gerechnet wurde, trug an dieser Stelle
#   MEHR Beitraege als der heutige Abzug. Woran das haengt, ist die Frage,
#   die dieses Werkzeug misst.
#
# ── DIE FRAGE, DIE ES BEANTWORTET ────────────────────────────────────────────
#
#   * AN DER ZEIT - spaeter gesetzte Markierungen haben groesseren Versatz,
#     unabhaengig davon, wo auf der Seite sie sitzen. Dann hat sich die
#     ausgelieferte Seite waehrend der Bearbeitung geaendert: ein Befund ueber
#     die SICHERUNG.
#   * AN DER POSITION - weiter unten gesetzte Markierungen haben groesseren
#     Versatz, auch bei gleicher Zeit. Dann fehlen dem Abzug Beitraege VOR der
#     Fundstelle, ueber die Seite verteilt.
#   * AN BEIDEM, nicht trennbar - dann SAGT das Werkzeug das, statt sich eine
#     der beiden Deutungen auszusuchen. Wer eine Seite von oben nach unten
#     abarbeitet, laesst Zeit und Position gleichlaufen; sie trennen sich erst
#     an Seiten, die NICHT der Reihe nach bearbeitet wurden. Genau solche
#     Paare sucht das Werkzeug und nennt sie einzeln.
#
#   Entscheidbar ist die Frage, weil 'annotations.ts' den Markierungszeitpunkt
#   traegt und 'pages.fetched_at' den Zeitpunkt der Sicherung. Beides steht
#   seit jeher in den Datenbanken und ist nie gegeneinander gehalten worden.
#
# ── WAS ES NICHT LEISTET ─────────────────────────────────────────────────────
#
#   Es sagt NICHT, welcher Beitrag der richtige ist. Es misst den Abstand
#   zwischen dem Beitrag, den der Ausdruck benennt, und dem, in dem der
#   markierte Wortlaut EINDEUTIG steht. Kommt der Wortlaut in mehreren
#   Beitraegen vor, gibt es keinen Messwert - und die Zeile bleibt leer
#   statt geraten (Befund Build 752: ein Treffer in einem von vielen
#   Beitraegen bestaetigt nichts).
#
# Version: 0.8.753 - Build 753
# =============================================================================

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sqlite3
import sys

# Das Werkzeug liegt in tools/; Zerleger und Absatzfinder liegen in der
# Wurzel. Ohne diesen Zusatz findet der Import sie nur, wenn zufaellig aus
# der Wurzel aufgerufen wird - und "zufaellig" ist keine Eigenschaft, auf die
# sich eine Messung stuetzen sollte.
_WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from management.help import cli_epilog                      # noqa: E402

#: Rueckgabewerte - siehe Katalogeintrag 'xpath_versatz_messen'.
RUECK_SAUBER = 0
RUECK_BEFUND = 1
RUECK_ABBRUCH = 2


# ---------------------------------------------------------------------------
# Kleinkram
# ---------------------------------------------------------------------------

def sekunden(wert):
    """
    Ein Zeitstempel als Sekunden. None, wenn unbrauchbar.

    Sekunden ODER Millisekunden - beides kommt in Altbestaenden vor, und eine
    Messung, die das nicht abfaengt, vergleicht Aepfel mit Jahrtausenden.
    """
    try:
        n = int(wert)
    except (TypeError, ValueError):
        return None
    return n // 1000 if n > 100000000000 else n


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


def monotonie(folge) -> str:
    """'KONSTANT' | 'monoton steigend' | 'monoton fallend' | 'nicht monoton'."""
    paare = list(zip(folge, folge[1:]))
    steigt = all(b >= a for a, b in paare)
    faellt = all(b <= a for a, b in paare)
    if steigt and faellt:
        return "KONSTANT"
    if steigt:
        return "monoton steigend"
    if faellt:
        return "monoton fallend"
    return "nicht monoton"


def trennende_paare(messwerte):
    """
    Paare, in denen Zeit und Position GEGENEINANDER laufen.

    NUR AN DIESEN PAAREN trennen sich die beiden Deutungen. Wo es keine gibt,
    ist die Frage aus diesem Bestand nicht entscheidbar - und das ist zu
    sagen und nicht zu verschweigen (Grundregel 1).

    'messwerte' sind Tupel (ts, platz, versatz, id).
    """
    heraus = []
    for i in range(len(messwerte)):
        for j in range(i + 1, len(messwerte)):
            a, b = messwerte[i], messwerte[j]
            if (a[0] - b[0]) * (a[1] - b[1]) < 0:
                heraus.append((a, b))
    return heraus


def _pad(s, n):
    s = str(s)
    return s + " " * max(0, n - len(s))


def _oeffne_ro(pfad: str) -> sqlite3.Connection:
    con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
    con.row_factory = sqlite3.Row
    return con


# ---------------------------------------------------------------------------
# Der Abzug
# ---------------------------------------------------------------------------

def abzug_zu(con_f: sqlite3.Connection, url: str):
    """
    Die pages-Zeile zu einer Adresse - mit denselben vier Abfragen und in
    derselben Reihenfolge wie management/maintenance/postid_nachtrag._blob().

    DASS ES DIESELBEN SIND, IST DER PUNKT: eine Messung, die den Abzug anders
    sucht als das gemessene Werkzeug, misst einen anderen Abzug.
    """
    for sql, par in (
        ("SELECT * FROM pages WHERE url_canonical = ? AND method = 'GET' "
         "LIMIT 1", (url,)),
        ("SELECT p.* FROM pages p JOIN page_aliases a ON a.page_id = p.id "
         "WHERE a.url_raw = ? AND p.method = 'GET' LIMIT 1", (url,)),
        ("SELECT * FROM pages WHERE url_canonical LIKE ? AND method = 'GET' "
         "LIMIT 1", ("%" + url,)),
        ("SELECT p.* FROM pages p JOIN page_aliases a ON a.page_id = p.id "
         "WHERE a.url_raw LIKE ? AND p.method = 'GET' LIMIT 1", ("%" + url,)),
    ):
        try:
            z = con_f.execute(sql, par).fetchone()
        except sqlite3.Error:
            continue
        if z is not None:
            return z
    return None


def alle_zeilen_zu(con_f: sqlite3.Connection, url: str):
    """
    ALLE pages-Zeilen zu dieser Adresse, ohne Methodenfilter.

    WARUM OHNE FILTER: pages traegt UNIQUE(url_canonical, method) - es kann
    also hoechstens EINEN GET-Abzug geben. Daneben kann ein POST-Abzug stehen,
    und Aliasse koennen auf eine ANDERE Zeile zeigen. Beides gehoert in den
    Befund, denn beides waere eine Erklaerung dafuer, dass der Ermittler eine
    andere Seite gesehen hat als die heute verglichene.
    """
    try:
        return con_f.execute(
            "SELECT id, url_canonical, method, fetched_at, http_status, "
            "scrape_context, LENGTH(html) AS laenge FROM pages "
            "WHERE url_canonical = ? OR url_canonical LIKE ?",
            (url, "%" + url)).fetchall()
    except sqlite3.Error:
        return []


def beitragsreihe_und_platz(finder):
    """(Liste der Beitragsnummern in Dokumentreihenfolge, {nummer: Platz})."""
    reihe = []
    for el in finder.beitragsreihe():
        m = re.match(r"^pp?(\d+)$", str(el.get("id") or "").strip())
        if m:
            reihe.append(int(m.group(1)))
    return reihe, {nr: i + 1 for i, nr in enumerate(reihe)}


# ---------------------------------------------------------------------------
# Die Messung je Seite
# ---------------------------------------------------------------------------

def messe_seite(url, gruppe, con_f, sag) -> bool:
    """
    Eine Seite messen. Rueckgabe: True, wenn etwas zu berichten war.
    'sag' ist die Ausgabefunktion (Konsole und ggf. Protokoll).
    """
    from report_render.absatz_finder import AbsatzFinder

    befund = False
    sag("")
    sag("-" * 78)
    sag("SEITE %s" % url)
    sag("  Annotationen: %d" % len(gruppe))

    stempel = [s for s in (sekunden(z["ts"]) for z in gruppe)
               if s is not None]
    if stempel:
        sag("  Markiert von : %s" % zeit(min(stempel)))
        sag("  Markiert bis : %s" % zeit(max(stempel)))

    alle = alle_zeilen_zu(con_f, url)
    if len(alle) > 1:
        befund = True
        sag("  ACHTUNG: %d pages-Zeilen zu dieser Adresse:" % len(alle))
    for a in alle:
        sag("    id=%-6s method=%-5s gesichert=%s  status=%-4s kontext=%-10s "
            "%s Zeichen"
            % (a["id"], a["method"], zeit(a["fetched_at"]), a["http_status"],
               a["scrape_context"], a["laenge"]))

    zeile = abzug_zu(con_f, url)
    if zeile is None:
        sag("  KEIN GET-ABZUG - hier ist nichts zu vergleichen.")
        return True
    sag("  Genommener Abzug: id=%s, gesichert %s"
        % (zeile["id"], zeit(zeile["fetched_at"])))

    # -- BEFUND 1: Abzug juenger als die Markierung? -----------------------
    #
    # Steht das fest, ist der Baum, gegen den der Ausdruck gerechnet wurde,
    # nicht der Baum, gegen den er heute geprueft wird - und alles Weitere
    # folgt daraus. Deshalb steht es zuerst.
    g = sekunden(zeile["fetched_at"])
    if g is None:
        sag("  Zeitvergleich nicht moeglich (fetched_at unbrauchbar).")
    else:
        aelter = [z for z in gruppe
                  if sekunden(z["ts"]) is not None and sekunden(z["ts"]) < g]
        if aelter:
            befund = True
            sag("  >>> BEFUND: %d von %d Markierungen sind AELTER als der "
                "Abzug." % (len(aelter), len(gruppe)))
            sag("      Der Abzug ist nach der Markierung gezogen worden; der "
                "Ermittler hat eine andere Fassung gesehen.")
        else:
            sag("  Alle Markierungen sind juenger als der Abzug (erwarteter "
                "Fall).")

    finder = AbsatzFinder.aus_seiten_html(zeile["html"])
    if finder is None or not finder.brauchbar:
        sag("  Abzug nicht zerlegbar - keine Positionsmessung moeglich.")
        return True
    reihe, platz = beitragsreihe_und_platz(finder)
    sag("  Beitraege im Abzug: %d" % len(reihe))

    # -- BEFUND 2: je Markierung Zeit, Position und Versatz ----------------
    sag("")
    sag("  %s %s %s %s %s %s"
        % (_pad("ID", 6), _pad("markiert", 20), _pad("Schritte", 9),
           _pad("Anker->Platz", 13), _pad("Wortlaut->Platz", 16), "Versatz"))
    sag("  " + "-" * 74)

    messwerte = []
    for z in gruppe:
        try:
            sel = json.loads(z["selection_json"] or "{}")
        except (TypeError, ValueError):
            sel = {}
        if not isinstance(sel, dict):
            sel = {}
        ausdruck = str(sel.get("xpathStart") or "")
        if not ausdruck:
            continue

        knoten, gegangen, gesamt = finder.anker_teilknoten(ausdruck)
        p_anker = None
        if knoten is not None:
            behaelter = AbsatzFinder.post_behaelter_von(knoten)
            nr = (AbsatzFinder.post_id_von(behaelter)
                  if behaelter is not None else None)
            if nr is not None:
                p_anker = platz.get(int(nr))

        # Der Wortlaut, und in WIE VIELEN Beitraegen er vorkommt. Nur wenn er
        # in GENAU EINEM steht, ist er eine Aussage ueber den Beitrag - sonst
        # bestaetigt er nichts (Befund Build 752, Beleg #65: ein Wortlaut in
        # 24 von 25 Beitraegen bestaetigt jeden davon und damit keinen).
        wortlaut = str(sel.get("textContent") or "")
        traeger = []
        if wortlaut.strip():
            for el in finder.beitragsreihe():
                if AbsatzFinder.wortlaut_im_beitrag(el, wortlaut) is True:
                    m = re.match(r"^pp?(\d+)$", str(el.get("id") or "").strip())
                    if m:
                        traeger.append(int(m.group(1)))
        p_soll = platz.get(traeger[0]) if len(traeger) == 1 else None

        versatz = ((p_anker - p_soll)
                   if (p_anker is not None and p_soll is not None) else None)
        if versatz:
            befund = True

        # DIE SPALTE MUSS DEN UNTERSCHIED ZEIGEN, und zwar diesen: 'kein
        # Wortlaut gefunden' und 'in mehreren Beitraegen gefunden' sind zwei
        # verschiedene Lagen mit zwei verschiedenen Folgen. Beide als '-'
        # auszugeben hiesse, die zweite verschwinden zu lassen - und genau
        # die ist der Fall, in dem NICHTS eingetragen werden darf.
        if p_soll is not None:
            soll_text = "%d" % p_soll
        elif len(traeger) > 1:
            soll_text = "(%d Traeger)" % len(traeger)
        else:
            soll_text = "-"

        sag("  %s %s %s %s %s %s"
            % (_pad(z["id"], 6), _pad(zeit(z["ts"]), 20),
               _pad("%d/%d" % (gegangen, gesamt), 9),
               _pad("-" if p_anker is None else p_anker, 13),
               _pad(soll_text, 16),
               "-" if versatz is None else ("%+d" % versatz)))
        if versatz is not None and sekunden(z["ts"]) is not None:
            messwerte.append((sekunden(z["ts"]), p_soll, versatz, z["id"]))

    # -- BEFUND 3: Zeit oder Position? -------------------------------------
    if len(messwerte) < 3:
        sag("")
        sag("  Zu wenige messbare Faelle (%d) fuer die Trennung von Zeit und "
            "Position." % len(messwerte))
        return befund

    nach_zeit = sorted(messwerte, key=lambda t: (t[0], t[3]))
    nach_platz = sorted(messwerte, key=lambda t: (t[1], t[3]))
    sag("")
    sag("  ZEIT GEGEN POSITION")
    sag("    Versatz nach ZEIT sortiert     : %s"
        % monotonie([t[2] for t in nach_zeit]))
    sag("    Versatz nach POSITION sortiert : %s"
        % monotonie([t[2] for t in nach_platz]))

    paare = trennende_paare(messwerte)
    if not paare:
        sag("    KEIN TRENNENDES PAAR: auf dieser Seite laufen Zeit und "
            "Position gleich (die Seite wurde der Reihe")
        sag("    nach bearbeitet). Aus diesem Bestand ist NICHT zu "
            "entscheiden, woran der Versatz haengt.")
        return befund
    sag("    %d trennende Paare (Zeit und Position laufen gegeneinander):"
        % len(paare))
    for a, b in paare[:10]:
        sag("      #%s (%s, Platz %d, %+d)  gegen  #%s (%s, Platz %d, %+d)"
            % (a[3], zeit(a[0]), a[1], a[2], b[3], zeit(b[0]), b[1], b[2]))
    if len(paare) > 10:
        sag("      ... und %d weitere." % (len(paare) - 10))
    sag("    LESEHILFE: folgt der Versatz in diesen Paaren der ZEIT, hat sich "
        "die Seite waehrend der Bearbeitung")
    sag("    geaendert; folgt er der POSITION, fehlen dem Abzug Beitraege "
        "ueber die Seite verteilt.")
    return befund


# ---------------------------------------------------------------------------

def lauf(evidence: str, forensic: str, nur_seite=None, sag=print) -> int:
    """Der ganze Lauf. Rueckgabe: einer der RUECK_*-Werte."""
    sag("=" * 78)
    sag("VERSATZ DER XPATH-AUSDRUECKE - Messung, es wird NICHTS geschrieben")
    sag("  Beweismittel : %s (mode=ro)" % evidence)
    sag("  Seitenabzug  : %s (mode=ro)" % forensic)
    sag("=" * 78)
    for pfad in (evidence, forensic):
        if not os.path.exists(pfad):
            sag("  ABBRUCH: %s gibt es nicht." % pfad)
            return RUECK_ABBRUCH

    con_e = _oeffne_ro(evidence)
    con_f = _oeffne_ro(forensic)
    try:
        zeilen = con_e.execute(
            "SELECT id, page_url, ts, selection_json, post_id "
            "FROM annotations WHERE deleted_at IS NULL "
            "ORDER BY page_url, ts, id").fetchall()
    except sqlite3.Error as exc:
        sag("  ABBRUCH: annotations nicht lesbar (%s)" % exc)
        con_e.close()
        con_f.close()
        return RUECK_ABBRUCH

    nach_seite: dict = {}
    for z in zeilen:
        u = str(z["page_url"] or "")
        if nur_seite and nur_seite not in u:
            continue
        nach_seite.setdefault(u, []).append(z)

    if not nach_seite:
        sag("  Keine Annotationen (nach Filter) - nichts zu messen.")
        con_e.close()
        con_f.close()
        return RUECK_SAUBER

    befund = False
    for url, gruppe in sorted(nach_seite.items()):
        try:
            if messe_seite(url, gruppe, con_f, sag):
                befund = True
        except Exception as exc:                            # noqa: BLE001
            # EIN FEHLER AN EINER SEITE DARF DEN LAUF NICHT BEENDEN - aber er
            # darf auch nicht still bleiben (Grundregel 1).
            befund = True
            sag("  FEHLER bei dieser Seite: %r" % (exc,))
    con_e.close()
    con_f.close()
    sag("")
    sag("=" * 78)
    sag("Es wurde nichts geschrieben.")
    return RUECK_BEFUND if befund else RUECK_SAUBER


def main(argv=None) -> int:
    zerleger = argparse.ArgumentParser(
        prog="xpath_versatz_messen",
        description="Messen, um wie viele Beitraege der gespeicherte "
                    "XPath-Ausdruck danebenzeigt - und ob der Versatz an der "
                    "Zeit der Markierung oder an der Position auf der Seite "
                    "haengt. Rein lesend.",
        epilog=cli_epilog.epilog("xpath_versatz_messen"),
        formatter_class=cli_epilog.HilfeFormat)
    zerleger.add_argument("--evidence", required=True,
                          help="Pfad zur evidence_<uid>.db (wird mit "
                               "mode=ro geoeffnet)")
    zerleger.add_argument("--forensic", required=True,
                          help="Pfad zur forensic_<uid>.db (wird mit "
                               "mode=ro geoeffnet)")
    zerleger.add_argument("--seite", default=None,
                          help="nur Seiten messen, deren page_url diese "
                               "Zeichenkette enthaelt (z. B. 'tid=64200')")
    zerleger.add_argument("--protokoll", default=None,
                          help="dieselben Zeilen zusaetzlich in diese Datei "
                               "schreiben (eingebautes 'tee')")
    args = zerleger.parse_args(argv)

    mitschrift = None
    if args.protokoll:
        try:
            mitschrift = open(args.protokoll, "w", encoding="utf-8")
        except OSError as exc:
            print("Protokolldatei nicht schreibbar: %s" % exc)
            return RUECK_ABBRUCH

    def sag(text=""):
        print(text)
        if mitschrift is not None:
            mitschrift.write(text + "\n")

    try:
        return lauf(args.evidence, args.forensic, args.seite, sag)
    finally:
        if mitschrift is not None:
            mitschrift.close()


if __name__ == "__main__":
    raise SystemExit(main())
