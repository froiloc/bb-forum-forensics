#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# tools/annotationen_verifizieren.py
# IT-Forensisches Ermittlungswerkzeug - Verifikation ALLER Annotationen
# =============================================================================
# Zweck:
#   JEDE Annotation JEDES Bestands gegen ihren gesicherten Seitenabzug halten
#   und benennen, MIT WELCHER BELEGKRAFT sie sich bestaetigen laesst.
#
#   Der Vorgang steht in management/maintenance/annotation_pruefung.py
#   (Grundregel 10). Diese Datei ist die Befehlszeile davor.
#
#   ES SCHREIBT NICHTS. Beide Datenbanken werden ueber 'file:...?mode=ro'
#   geoeffnet - schreibgeschuetzt durch die Verbindung und nicht durch
#   Vorsatz.
#
# ── WARUM ES DIESES WERKZEUG GIBT ────────────────────────────────────────────
#
#   Weil bis Build 753 an KEINER der beiden entscheidenden Stellen geprueft
#   wurde, ob am Ende des Ausdrucks auch der markierte Wortlaut steht:
#
#     * anker_diagnose._anker_pruefen() prueft nur, ob die verlangte Position
#       existiert. Der Wortlaut wird in der ganzen Datei nie gelesen.
#     * postid_nachtrag uebernimmt im Zweig 'Weg=anker' die Beitragsnummer
#       ungeprueft; die Kreuzprobe aus Build 751 lief NUR im Zweig des
#       teilweise aufgeloesten Ausdrucks - also ausgerechnet nur dort, wo der
#       Ausdruck schon gestolpert war.
#
#   Im Lauf vom 31.08.2026 ueber 462 Annotationen entstanden auf diesem
#   ungeprueften Weg 408 von 445 vorgesehenen Eintragungen. Was das wert ist,
#   zeigt die Browsermessung M1b auf '/forum/pmsnew.php?mdl=topic&tid=64200':
#   von 46 Annotationen liefern SIEBEN einen Bereich, dessen Text dem
#   gespeicherten Wortlaut entspricht.
#
#   DIESES WERKZEUG BEANTWORTET DIE FRAGE FUER DEN GANZEN BESTAND, in einem
#   Lauf, mit einer Zahl je Lage.
#
# ── DIE SECHS LAGEN ──────────────────────────────────────────────────────────
#
#   BESTAETIGT      Ausdruck loest auf UND der Text an der Stelle ist der
#                   markierte Wortlaut. Der starke Fall.
#   BEITRAG_BELEGT  Fundstelle nicht zeichengenau zu bestaetigen, aber der
#                   Wortlaut steht in genau einem Beitrag - dem benannten.
#   NUR_WORTLAUT    Ausdruck traegt nicht, Wortlaut auf der Seite eindeutig.
#   UNKLAR          Wortlaut kommt in mehreren oder in keinem Beitrag vor.
#   WIDERLEGT       Wortlaut steht eindeutig in einem ANDEREN Beitrag.
#   UNPRUEFBAR      Kein Ausdruck, kein Abzug, kein brauchbarer Wortlaut.
#
#   SIE WERDEN BENANNT UND NICHT VERRECHNET. Eine Gesamtnote naehme dem
#   Leser genau die Unterscheidung ab, auf die es ankommt.
#
# Version: 0.8.754 - Build 754
# =============================================================================

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys

_WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from management.help import cli_epilog                      # noqa: E402
from management.maintenance.annotation_pruefung import (    # noqa: E402
    AnnotationPruefer, Pruefbefund, URTEILE,
    URTEIL_BESTAETIGT, URTEIL_BEITRAG_BELEGT, URTEIL_NUR_WORTLAUT,
    URTEIL_UNKLAR, URTEIL_WIDERLEGT, URTEIL_UNPRUEFBAR)

RUECK_ALLES_BELEGT = 0
RUECK_OFFEN = 1
RUECK_ABBRUCH = 2

#: Die Lagen, die eine belastbare Beitragsnummer hergeben.
_TRAGEND = (URTEIL_BESTAETIGT, URTEIL_BEITRAG_BELEGT, URTEIL_NUR_WORTLAUT)


def _oeffne_ro(pfad: str) -> sqlite3.Connection:
    con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _pad(s, n):
    s = str(s)
    return s + " " * max(0, n - len(s))


def _blob(con_f: sqlite3.Connection, url: str):
    """
    Der GET-Abzug zu einer Adresse - mit denselben vier Abfragen und in
    derselben Reihenfolge wie management/maintenance/postid_nachtrag._blob().
    Eine Verifikation, die einen anderen Abzug sucht als die Auswertung,
    verifiziert das Falsche.
    """
    for sql, par in (
        ("SELECT html FROM pages WHERE url_canonical = ? AND method = 'GET' "
         "LIMIT 1", (url,)),
        ("SELECT p.html FROM pages p JOIN page_aliases a ON a.page_id = p.id "
         "WHERE a.url_raw = ? AND p.method = 'GET' LIMIT 1", (url,)),
        ("SELECT html FROM pages WHERE url_canonical LIKE ? AND "
         "method = 'GET' LIMIT 1", ("%" + url,)),
        ("SELECT p.html FROM pages p JOIN page_aliases a ON a.page_id = p.id "
         "WHERE a.url_raw LIKE ? AND p.method = 'GET' LIMIT 1", ("%" + url,)),
    ):
        try:
            z = con_f.execute(sql, par).fetchone()
        except sqlite3.Error:
            continue
        if z is not None and z[0]:
            return z[0]
    return None


def pruefe_bestand(uid: str, evidence: str, forensic: str, sag,
                   ausfuehrlich: bool = False):
    """
    Einen Bestand pruefen. Rueckgabe: Zaehlung je Urteil (dict).
    """
    from report_render.absatz_finder import AbsatzFinder

    zaehlung = {u: 0 for u in URTEILE}
    sag("=" * 78)
    sag("BESTAND %s" % uid)
    sag("  Beweismittel : %s (mode=ro)" % evidence)
    sag("  Seitenabzug  : %s (mode=ro)" % forensic)
    sag("=" * 78)
    for pfad in (evidence, forensic):
        if not os.path.exists(pfad):
            sag("  UEBERSPRUNGEN: %s gibt es nicht." % pfad)
            return zaehlung

    con_e = _oeffne_ro(evidence)
    con_f = _oeffne_ro(forensic)
    try:
        zeilen = con_e.execute(
            "SELECT id, page_url, selection_json, post_id "
            "FROM annotations WHERE deleted_at IS NULL "
            "ORDER BY page_url, id").fetchall()
    except sqlite3.Error as exc:
        sag("  ABBRUCH: annotations nicht lesbar (%s)" % exc)
        con_e.close()
        con_f.close()
        return zaehlung

    nach_seite = {}
    for z in zeilen:
        nach_seite.setdefault(str(z["page_url"] or ""), []).append(z)

    for url, gruppe in sorted(nach_seite.items()):
        sag("")
        sag("  SEITE %s   (%d Annotationen)" % (url, len(gruppe)))
        roh = _blob(con_f, url)
        if not roh:
            # KEIN ABZUG IST EIN BEFUND UEBER DIE SICHERUNG, nicht ueber den
            # Ausdruck. Er wird als eigene Lage gezaehlt und nicht unter die
            # unklaren gemischt.
            sag("    KEIN GET-ABZUG - alle %d Annotationen bleiben "
                "UNPRUEFBAR." % len(gruppe))
            zaehlung[URTEIL_UNPRUEFBAR] += len(gruppe)
            continue
        finder = AbsatzFinder.aus_seiten_html(roh)
        if finder is None or not finder.brauchbar:
            sag("    ABZUG NICHT ZERLEGBAR - alle %d Annotationen bleiben "
                "UNPRUEFBAR." % len(gruppe))
            zaehlung[URTEIL_UNPRUEFBAR] += len(gruppe)
            continue
        pruefer = AnnotationPruefer(finder)
        sag("    Beitraege im Abzug: %d" % len(pruefer.reihe))
        sag("    %s %s %s %s %s"
            % (_pad("ID", 7), _pad("URTEIL", 15), _pad("Anker", 10),
               _pad("Wortlaut", 12), "Textprobe"))
        for z in gruppe:
            b = pruefer.pruefe(z["id"], url, z["selection_json"])
            zaehlung[b.urteil] += 1
            wl = ("#%d" % b.beitraege_wortlaut[0]
                  if len(b.beitraege_wortlaut) == 1
                  else ("(%d)" % len(b.beitraege_wortlaut)
                        if b.beitraege_wortlaut else "-"))
            sag("    %s %s %s %s %s"
                % (_pad(z["id"], 7), _pad(b.urteil, 15),
                   _pad("-" if b.beitrag_anker is None
                        else "#%d" % b.beitrag_anker, 10),
                   _pad(wl, 12), b.textprobe))
            if ausfuehrlich or b.urteil in (URTEIL_WIDERLEGT, URTEIL_UNKLAR):
                sag("        %s" % b.bemerkung)
            # Widerspruch zu einer bereits eingetragenen Nummer ist IMMER zu
            # melden - er entscheidet nichts, aber er ist ein Befund.
            if z["post_id"] is not None and b.beitrag is not None \
                    and int(z["post_id"]) != int(b.beitrag):
                sag("        WIDERSPRUCH: eingetragen ist #%s, die Pruefung "
                    "sagt #%d." % (z["post_id"], b.beitrag))
    con_e.close()
    con_f.close()

    sag("")
    sag("  ZAEHLUNG BESTAND %s" % uid)
    for u in URTEILE:
        sag("    %s %d" % (_pad(u, 16), zaehlung[u]))
    return zaehlung


def lauf(data_dir: str, uids, sag=print, ausfuehrlich: bool = False) -> int:
    ev_verz = os.path.join(data_dir, "evidence")
    fo_verz = os.path.join(data_dir, "forensic")
    if not os.path.isdir(ev_verz):
        sag("ABBRUCH: %s gibt es nicht." % ev_verz)
        return RUECK_ABBRUCH

    if not uids:
        uids = []
        for name in sorted(os.listdir(ev_verz)):
            m = re.match(r"^evidence_(\d+)\.db$", name)
            if m:
                uids.append(m.group(1))
    if not uids:
        sag("Keine Beweismitteldatenbanken gefunden.")
        return RUECK_ABBRUCH

    gesamt = {u: 0 for u in URTEILE}
    for uid in uids:
        z = pruefe_bestand(uid,
                           os.path.join(ev_verz, "evidence_%s.db" % uid),
                           os.path.join(fo_verz, "forensic_%s.db" % uid),
                           sag, ausfuehrlich)
        for k, v in z.items():
            gesamt[k] += v
        sag("")

    summe = sum(gesamt.values())
    tragend = sum(gesamt[u] for u in _TRAGEND)
    sag("=" * 78)
    sag("GESAMT ueber %d Bestaende - %d Annotationen" % (len(uids), summe))
    sag("=" * 78)
    for u in URTEILE:
        anteil = (100.0 * gesamt[u] / summe) if summe else 0.0
        sag("  %s %6d   %5.1f %%" % (_pad(u, 16), gesamt[u], anteil))
    sag("")
    sag("  Mit belastbarer Beitragsnummer (BESTAETIGT + BEITRAG_BELEGT + "
        "NUR_WORTLAUT): %d von %d" % (tragend, summe))
    sag("")
    sag("  LESEHILFE: 'BESTAETIGT' ist der einzige Fall, in dem Position UND")
    sag("  Inhalt dasselbe sagen. 'BEITRAG_BELEGT' und 'NUR_WORTLAUT' tragen")
    sag("  den BEITRAG, nicht die Stelle darin - fuer das Vollzitat ist das")
    sag("  ein Unterschied. 'WIDERLEGT' heisst nicht, dass der Ermittler")
    sag("  sich geirrt hat, sondern dass die Angabe des Ausdrucks vom Inhalt")
    sag("  nicht getragen wird.")
    sag("=" * 78)
    sag("Es wurde nichts geschrieben.")
    return RUECK_ALLES_BELEGT if tragend == summe else RUECK_OFFEN


def main(argv=None) -> int:
    zerleger = argparse.ArgumentParser(
        prog="annotationen_verifizieren",
        description="Jede Annotation jedes Bestands gegen ihren gesicherten "
                    "Seitenabzug halten und die Belegkraft benennen. Rein "
                    "lesend.",
        epilog=cli_epilog.epilog("annotationen_verifizieren"),
        formatter_class=cli_epilog.HilfeFormat)
    zerleger.add_argument("--data-dir", default="./data",
                          help="Verzeichnis mit 'evidence/' und 'forensic/' "
                               "(Vorgabe: ./data)")
    zerleger.add_argument("--uid", action="append", default=[],
                          help="nur diesen Bestand pruefen; mehrfach "
                               "angebbar. Ohne Angabe: alle gefundenen.")
    zerleger.add_argument("--ausfuehrlich", action="store_true",
                          help="zu JEDER Annotation die Begruendung ausgeben "
                               "(ohne den Schalter nur bei WIDERLEGT und "
                               "UNKLAR)")
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
        return lauf(args.data_dir, args.uid, sag, args.ausfuehrlich)
    finally:
        if mitschrift is not None:
            mitschrift.close()


if __name__ == "__main__":
    raise SystemExit(main())
