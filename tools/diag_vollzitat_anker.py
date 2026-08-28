#!/usr/bin/env python3
# =============================================================================
# tools/diag_vollzitat_anker.py
# IT-Forensisches Ermittlungswerkzeug - Vollzitat (Build 727)
# =============================================================================
# Zweck:
#   SAGEN, WARUM EIN MARKIERUNGSANKER IM SEITENABZUG NICHT AUFLOEST.
#
#   Bei der Sichtpruefung am 28.08.2026 loeste in einer echten
#   Beweismittelgruppe KEINER von 23 Ankern auf - alle Absaetze wurden ueber
#   den Wortlaut gefunden oder gar nicht. Aus der Editor-Ansicht allein ist
#   die Ursache nicht zu bestimmen. Dieses Werkzeug bestimmt sie.
#
# WAS ES TUT: Es geht den Anker SCHRITT FUER SCHRITT durch. Fuer jeden Schritt
#   sagt es, ob er im zerlegten Seitenabzug aufloest, und wenn nicht, WAS an
#   dieser Stelle statt dessen steht - mit Anzahl, Kennung und Klasse der
#   vorhandenen Geschwister. Damit ist der Bruch nicht nur festgestellt,
#   sondern lokalisiert:
#
#     - bricht es GANZ OBEN, stimmt der Bezugspunkt nicht (der <body>-Auszug)
#     - bricht es an einem Schritt mit zu WENIGEN Geschwistern, hat der
#       Browser dort mehr Elemente gesehen als im Abzug stehen - dann hat
#       etwas in die Seite hineingeschrieben (die Toolbar, ein Skript)
#     - bricht es erst bei 'text()[n]', stimmt die Zerlegung des Textes nicht
#       (Zeilenumbrueche, eingefuegte <mark>-Elemente)
#
# ES WIRD NUR GELESEN. Alle Datenbanken werden mit 'mode=ro' geoeffnet. Kein
#   Schreibzugriff, keine Migration, keine Aenderung an einem Beweismittel.
#
# AUFRUF (in der VM, aus dem Wurzelverzeichnis des Webservers):
#
#   python tools/diag_vollzitat_anker.py \
#       --evidence /pfad/evidence_700.db \
#       --forensic /pfad/forensic_700.db
#
#   python tools/diag_vollzitat_anker.py --evidence ... --forensic ... \
#       --beleg 26                 # nur eine Beleg-Nummer
#   python tools/diag_vollzitat_anker.py --evidence ... --forensic ... \
#       --grenze 5                 # nur die ersten fuenf
#
#   Die Ausgabe ist Klartext und darf unveraendert weitergegeben werden:
#   sie enthaelt KEINE Beitragsinhalte, nur Baumstruktur, Kennungen und
#   Klassennamen. Der markierte Wortlaut wird auf 40 Zeichen gekuerzt und
#   kann mit '--ohne-wortlaut' ganz unterdrueckt werden.
#
# Version: v0.8.727 - Build: 727 - 2026-08-28
# =============================================================================

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from management.help import cli_epilog  # noqa: E402

#: Ein Schritt eines XPath-Ausdrucks: 'div[4]', 'article[29]', 'text()[3]'.
_SCHRITT = re.compile(r"^([a-zA-Z_][\w.-]*|text\(\))\[(\d+)\]$")


def _oeffne_ro(pfad: str) -> Optional[sqlite3.Connection]:
    """
    Die Hauptverbindung READ-ONLY oeffnen.

    KEINE ':memory:'-HAUPTVERBINDUNG MIT ANGEHAENGTEN LESE-DATENBANKEN. Die
    waere zwar fuer die Beweismittel ebenso ungefaehrlich - angehaengt wird
    ohnehin mit 'mode=ro' -, aber sie ist SCHREIBFAEHIG, und tests/
    test_py4_lesend.py (PY08) sieht genau das: ein als 'lesend' gefuehrtes
    Werkzeug, das eine schreibfaehige Verbindung aufmacht. Der Waechter hat
    bei der ersten Fassung dieses Werkzeugs angeschlagen - zu Recht. Eine
    Ausnahme in die Fehlliste einzutragen waere der bequeme Weg gewesen; die
    Verbindung wirklich lesend zu machen ist der richtige.
    """
    p = Path(pfad)
    if not p.exists():
        print("  FEHLT: %s" % p)
        return None
    con = sqlite3.connect("file:%s?mode=ro" % p.resolve(), uri=True)
    con.row_factory = sqlite3.Row
    return con


def _anhaengen_ro(con: sqlite3.Connection, pfad: str, alias: str) -> bool:
    """Eine zweite Datenbank READ-ONLY anbinden."""
    p = Path(pfad)
    if not p.exists():
        print("  FEHLT: %s" % p)
        return False
    con.execute("ATTACH DATABASE ? AS %s" % alias,
                ("file:%s?mode=ro" % p.resolve(),))
    return True


def _body(roh: bytes) -> str:
    """Der <body>-Auszug - mit DERSELBEN Funktion wie der Auslieferungspfad."""
    from server.blob_handler import BlobHandler
    return BlobHandler._extract_body(roh)


def _beschreibe(el) -> str:
    """Ein Element knapp benennen: Tag, Kennung, Klasse."""
    tag = getattr(el, "tag", "?")
    kennung = (el.get("id") or "") if hasattr(el, "get") else ""
    klasse = (el.get("class") or "") if hasattr(el, "get") else ""
    teile = [str(tag)]
    if kennung:
        teile.append("#" + kennung)
    if klasse:
        teile.append("." + ".".join(klasse.split()[:3]))
    return " ".join(teile)


def _geschwisterbild(eltern, tag: str) -> str:
    """Wie viele Geschwister dieses Tags gibt es hier - und wie heissen sie?"""
    if eltern is None:
        return "(kein Elternteil)"
    if tag == "text()":
        n = len([k for k in eltern.xpath("./text()")])
        return "%d Textknoten vorhanden" % n
    gleiche = [k for k in eltern if getattr(k, "tag", None) == tag]
    andere = sorted({str(getattr(k, "tag", "?")) for k in eltern})
    return ("%d x <%s> vorhanden; Kinder insgesamt: %d (%s)"
            % (len(gleiche), tag, len(list(eltern)), ", ".join(andere[:8])))


def pruefe_anker(wurzel, ausdruck: str) -> None:
    """Den Anker schrittweise aufloesen und jeden Schritt berichten."""
    schritte = [t for t in ausdruck.split("/") if t and t != "."]
    knoten = wurzel
    pfad_bisher = "."
    for i, schritt in enumerate(schritte, 1):
        treffer = _SCHRITT.match(schritt)
        if not treffer:
            print("      Schritt %2d  %-16s  UNLESBAR (Muster passt nicht)"
                  % (i, schritt))
            return
        tag, nr = treffer.group(1), int(treffer.group(2))
        try:
            ergebnis = knoten.xpath("./" + schritt)
        except Exception as exc:
            print("      Schritt %2d  %-16s  XPATH-FEHLER: %s"
                  % (i, schritt, exc))
            return
        if ergebnis:
            knoten = ergebnis[0]
            pfad_bisher += "/" + schritt
            beschreibung = ("Textknoten" if tag == "text()"
                            else _beschreibe(knoten))
            print("      Schritt %2d  %-16s  OK    -> %s"
                  % (i, schritt, beschreibung))
            continue

        # HIER BRICHT ES. Das ist die eigentliche Auskunft dieses Werkzeugs.
        print("      Schritt %2d  %-16s  BRICHT HIER" % (i, schritt))
        print("                  Elternteil: %s" % _beschreibe(knoten))
        print("                  Im Abzug:   %s"
              % _geschwisterbild(knoten, tag))
        print("                  Aufgeloest bis: %s" % pfad_bisher)
        if tag != "text()":
            gleiche = [k for k in knoten if getattr(k, "tag", None) == tag]
            if gleiche and nr > len(gleiche):
                print("                  BEFUND: der Browser hat MEHR <%s> "
                      "gesehen (%d) als im Abzug stehen (%d). Zwischen "
                      "Abzug und Markierung ist etwas in die Seite "
                      "geschrieben worden." % (tag, nr, len(gleiche)))
            elif not gleiche:
                print("                  BEFUND: an dieser Stelle gibt es "
                      "ueberhaupt kein <%s>. Der Bezugspunkt weicht ab - "
                      "vermutlich schon weiter oben." % tag)
        else:
            vorhanden = len(knoten.xpath("./text()"))
            print("                  BEFUND: der Browser hat %d Textknoten "
                  "gesehen, der Abzug hat %d. Die Zerlegung des Textes "
                  "weicht ab (Zeilenumbrueche, eingefuegte Elemente)."
                  % (nr, vorhanden))
        return
    print("      ALLE SCHRITTE LOESEN AUF - der Anker ist in Ordnung.")


def main() -> int:
    # Der Epilog kommt aus dem Katalog (management/help/cli_katalog.py) -
    # '--help' und die Hilfe im Management sagen damit dasselbe, und zwar aus
    # einer Quelle. tests/test_help_cli_epilog.py (CE10) verlangt die
    # Verdrahtung ausdruecklich: ein Werkzeug ohne Epilog muss mit
    # BEGRUENDUNG in OHNE_EPILOG stehen - stillschweigend weglassen gilt nicht.
    zerleger = argparse.ArgumentParser(
        description="Diagnose: warum loest ein Vollzitat-Anker nicht auf?",
        epilog=cli_epilog.epilog("diag_vollzitat_anker"),
        formatter_class=cli_epilog.HilfeFormat)
    zerleger.add_argument("--evidence", required=True,
                          help="Pfad zur evidence_<uid>.db")
    zerleger.add_argument("--forensic", required=True,
                          help="Pfad zur forensic_<uid>.db")
    zerleger.add_argument("--beleg", type=int, default=None,
                          help="nur diese annotations.id")
    zerleger.add_argument("--grenze", type=int, default=10,
                          help="hoechstens so viele Belege (Vorgabe 10)")
    zerleger.add_argument("--ohne-wortlaut", action="store_true",
                          help="den markierten Wortlaut nicht ausgeben")
    args = zerleger.parse_args()

    from lxml import html as lxml_html

    print("=== Datenbanken (READ-ONLY) ===")
    con = _oeffne_ro(args.evidence)
    if con is None:
        return 2
    if not _anhaengen_ro(con, args.forensic, "fdb"):
        return 2
    print("  angebunden.\n")

    bedingung = "AND id = %d" % args.beleg if args.beleg else ""
    zeilen = con.execute(
        "SELECT id, page_url, element_id, post_id, selection_json "
        "FROM annotations "
        "WHERE deleted_at IS NULL AND selection_json IS NOT NULL %s "
        "ORDER BY id DESC LIMIT %d" % (bedingung, max(1, args.grenze))
    ).fetchall()
    if not zeilen:
        print("Keine passende Annotation gefunden.")
        return 1

    # Seitenabzuege je Adresse einmal zerlegen.
    abzuege = {}
    aufgeloest = gebrochen = ohne_anker = ohne_seite = 0

    for r in zeilen:
        print("=" * 78)
        print("Beleg #%s   post_id=%s   element_id=%s"
              % (r["id"], r["post_id"], r["element_id"]))
        print("  Seite: %s" % r["page_url"])
        try:
            sel = json.loads(r["selection_json"])
        except Exception as exc:
            print("  selection_json unlesbar: %s" % exc)
            continue
        if sel.get("target") == "translation":
            print("  Markierung in einer KI-Uebersetzung - kein Seitenanker.")
            continue
        anker = sel.get("xpathStart") or ""
        wortlaut = sel.get("textContent") or sel.get("text") or ""
        if not args.ohne_wortlaut:
            print("  Wortlaut: %r%s" % (wortlaut[:40],
                                        " …" if len(wortlaut) > 40 else ""))
        if not anker:
            print("  KEIN Anker in selection_json.")
            ohne_anker += 1
            continue
        print("  Anker: %s" % anker)

        url = r["page_url"]
        if url not in abzuege:
            zeile = con.execute(
                "SELECT html FROM fdb.pages WHERE url_canonical = ? "
                "OR url_canonical LIKE ? LIMIT 1",
                (url, "%" + url)).fetchone()
            roh = zeile["html"] if zeile else None
            if not roh:
                abzuege[url] = None
            else:
                try:
                    abzuege[url] = lxml_html.fragment_fromstring(
                        _body(roh), create_parent="div")
                except Exception as exc:
                    print("  Abzug nicht zerlegbar: %s" % exc)
                    abzuege[url] = None
        wurzel = abzuege[url]
        if wurzel is None:
            print("  KEIN Seitenabzug zu dieser Adresse in fdb.pages.")
            ohne_seite += 1
            continue

        # Zum Vergleich: was steht ganz oben im Abzug?
        print("  Abzug, oberste Ebene: %s"
              % ", ".join(_beschreibe(k) for k in list(wurzel)[:6]))
        voll = wurzel.xpath(anker)
        if voll:
            print("      DER GANZE ANKER LOEST AUF.")
            aufgeloest += 1
        else:
            gebrochen += 1
            pruefe_anker(wurzel, anker)

    print("=" * 78)
    print("ZUSAMMENFASSUNG: %d geprueft | %d Anker loesen auf | %d brechen | "
          "%d ohne Anker | %d ohne Seitenabzug"
          % (len(zeilen), aufgeloest, gebrochen, ohne_anker, ohne_seite))
    return 0


if __name__ == "__main__":
    sys.exit(main())
