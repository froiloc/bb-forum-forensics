#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# tools/anker_inventar.py
# IT-Forensisches Ermittlungswerkzeug - Etappe 1: Inventar der Ankerpunkte
# =============================================================================
# Zweck:
#   WELCHE FESTEN ANKERPUNKTE STEHEN IN DEN SEITEN-BLOBS WIRKLICH DRIN, und
#   wie viele der gespeicherten XPath-Ausdruecke finden damit ihren Beitrag?
#
#   Der Vorgang steht in management/maintenance/anker_inventar.py
#   (Grundregel 10). Diese Datei ist die Befehlszeile davor.
#
#   ES SCHREIBT NICHTS. Weisung Alex, 03.09.2026: bis Etappe 4 wird
#   ausschliesslich gelesen. Beide Verbindungen laufen ueber 'mode=ro'.
#
# ── WOZU ────────────────────────────────────────────────────────────────────
#
#   Etappe 0 hat gezaehlt, was in den Annotationen steht. Ergebnis: 497
#   Textmarkierungen, alle in der Fuenf-Feld-Form, alle mit einem rein
#   positionsbezogenen Ausdruck, KEINE mit einer post_id. Das Ziel des
#   Arbeitsblocks ist, aus jeder Annotation ohne Rateschritt post_id,
#   Verfasser, Zeit und umgebenden Absatz bestimmen zu koennen.
#
#   Dieses Werkzeug beantwortet die Vorfrage: Gibt der gespeicherte
#   Seiteninhalt das ueberhaupt her? Vier Bloecke - Behaelter, Anker,
#   Aufloesung, Wortlaut-Gegenprobe.
#
# Version: 0.8.758 - Build 758
# =============================================================================

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

_WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _WURZEL not in sys.path:
    sys.path.insert(0, _WURZEL)

from core import werkzeug_konfig                              # noqa: E402
from core.config_loader import coded_default                  # noqa: E402
from management.help import cli_epilog                        # noqa: E402
from management.maintenance.anker_inventar import (           # noqa: E402
    AnkerInventar, XPATH_BEITRAGSTEXT)

RUECK_OHNE_BEFUND = 0
RUECK_BEFUND = 1
RUECK_ABBRUCH = 2

_RE_EVIDENCE = re.compile(r"^evidence_(\d+)\.db$")


def _buildnummer() -> Any:
    """Die Buildnummer aus build.json - nicht aus dem Quelltext (Build 757)."""
    try:
        with open(os.path.join(_WURZEL, "build.json"), encoding="utf-8") as fh:
            return json.load(fh).get("build")
    except (OSError, ValueError):
        return None


def _pad(s, n) -> str:
    s = str(s)
    return s + " " * max(0, n - len(s))


def _tab(sag, ueberschrift, paare, breite=44) -> None:
    if ueberschrift:
        sag("  %s" % ueberschrift)
    for name, wert in paare:
        sag("    %s %s" % (_pad(name, breite), wert))


def _ausgeben(b, sag) -> None:
    sag("=" * 78)
    sag("BESTAND %s" % b.uid)
    sag("=" * 78)
    for f in b.fehler:
        sag("  FEHLER: %s" % f)
    if not b.a_behaelter:
        return
    s, a, bb, c, d = b.seiten, b.a_behaelter, b.b_anker, b.c_aufloesung, \
        b.d_wortlaut

    _tab(sag, "SEITEN", (
        ("Adressen mit Annotationen", s["adressen"]),
        ("davon ohne Seite im Bestand", s["ohne_seite"]),
        ("davon ohne Inhalt", s["ohne_inhalt"]),
        ("erfolgreich zerlegt", a["seiten_zerlegt"]),
        ("zerlegt, aber OHNE Beitragsbehaelter", a["seiten_ohne_treffer"]),
    ))
    for u in a["ohne_behaelter"]:
        sag("      ohne Behaelter: %s" % u)

    sag("")
    sag("A  BEITRAGSBEHAELTER  (Kennung nach '^p+(\\d+)$')")
    _tab(sag, "", (("gefundene Kennungen", a["behaelter_gesamt"]),))
    _tab(sag, "Praefixe:", sorted(a["praefix"].items()))
    sag("    'pp' stammt aus viewtopic0.php Z. 975 - dort steht das 'p'")
    sag("    doppelt, einmal als Literal und einmal in der Ausgabe. Ein")
    sag("    Zerleger mit '^p(\\d+)$' verloere diesen Zweig stillschweigend.")
    _tab(sag, "Elementnamen (nur zur Einordnung, nicht zur Identifikation):",
         sorted(a["elementnamen"].items(), key=lambda p: -p[1])[:8])
    _tab(sag, "Klassen der Behaelter:",
         sorted(a["klassen"].items(), key=lambda p: -p[1])[:12])
    if a["mehrfache_nummern"]:
        sag("    DIESELBE NUMMER MIT DEMSELBEN PRAEFIX MEHRFACH (%d):"
            % len(a["mehrfache_nummern"]))
        for m in a["mehrfache_nummern"][:10]:
            sag("      Nummer %s, Praefix %s, %sx auf %s"
                % (m["nummer"], m["praefix"], m["anzahl"], m["url"]))

    sag("")
    sag("B  ANKER JE BEHAELTER")
    sag("    Beitragstext, gesucht in dieser Reihenfolge. Der erste Ausdruck")
    sag("    ist der aus der Weisung: %s" % XPATH_BEITRAGSTEXT)
    _tab(sag, "", (("geprueft", bb["behaelter_geprueft"]),))
    _tab(sag, "Beitragstext gefunden ueber:",
         sorted(bb["text"].items(), key=lambda p: -p[1]))
    _tab(sag, "Verfasser gefunden ueber:",
         sorted(bb["verfasser"].items(), key=lambda p: -p[1]))
    _tab(sag, "Zeitstempel gefunden ueber:",
         sorted(bb["zeitstempel"].items(), key=lambda p: -p[1]))
    if bb["text_mehrfach"]:
        sag("    ACHTUNG: %d Behaelter liefern MEHR ALS EINEN Treffer auf"
            % bb["text_mehrfach"])
        sag("    den Textausdruck. Der exakte Attributvergleich sollte die")
        sag("    Signatur ('postsignature postmsg') ausschliessen.")

    sag("")
    sag("C  AUFLOESUNG DER GESPEICHERTEN AUSDRUECKE")
    _tab(sag, "", (
        ("Annotationen mit Ausdruck", c["mit_ausdruck"]),
        ("  Ausdruck findet einen Knoten", c["aufgeloest"]),
        ("  Ausdruck findet KEINEN Knoten", c["kein_knoten"]),
        ("  Knoten ohne Beitragsbehaelter darueber",
         c["knoten_ohne_behaelter"]),
        ("  POST_ID BESTIMMT", c["post_id_bestimmt"]),
        ("Variante 1 'whole post'", c["whole_post"]),
        ("  Behaelter im Seiteninhalt vorhanden",
         c["whole_post_behaelter_da"]),
    ))
    for f in c["whole_post_behaelter_fehlt"]:
        sag("      BEHAELTER FEHLT: id=%s Nummer=%s auf %s"
            % (f["id"], f["nummer"], f["url"]))
    for e in c["beispiele"][:5]:
        sag("      Beispiel: annotations.id=%s -> post_id=%s"
            % (e["id"], e["post_id"]))

    sag("")
    sag("D  GEGENPROBE UEBER DEN WORTLAUT  (nur fuer die Faelle aus C, die")
    sag("   nicht aufgeloest haben)")
    _tab(sag, "", (
        ("geprueft", d["geprueft"]),
        ("Wortlaut steht in GENAU EINEM Behaelter", d["wortlaut_eindeutig"]),
        ("Wortlaut steht in MEHREREN", d["wortlaut_mehrfach"]),
        ("Wortlaut steht NIRGENDS", d["wortlaut_nirgends"]),
    ))
    if d.get("fassung"):
        sag("    Getroffene Vergleichsfassung (die Reihenfolge ist die")
        sag("    Rangfolge - 'gefaltet' ist der schwaechste Treffer):")
        for name in ("woertlich", "ohne_randleerraum", "gefaltet"):
            if name in d["fassung"]:
                sag("      %s %s" % (_pad(name, 24), d["fassung"][name]))
    for f in d["faelle"][:10]:
        sag("      id=%s %s Traeger=%s (%d) Laenge=%s Umbrueche=%s %s"
            % (f["id"], _pad(f["lage"], 22), f["traeger"],
               f["traeger_anzahl"], f["wortlaut_laenge"],
               f.get("zeilenumbrueche"), f.get("fassung") or ""))


def _bilanz(befunde, sag) -> int:
    sag("=" * 78)
    sag("GESAMTBILANZ")
    sag("=" * 78)
    sag("  %s %8s %8s %9s %9s %9s"
        % (_pad("Bestand", 12), "Ausdruck", "aufgel.", "post_id", "wholeP",
           "W-eind."))
    sag("  " + "-" * 66)
    su = dict.fromkeys(("mit", "auf", "pid", "wp", "we"), 0)
    for b in befunde:
        if not b.c_aufloesung:
            sag("  %s  NICHT AUSGEWERTET" % _pad(b.uid, 12))
            continue
        c, d = b.c_aufloesung, b.d_wortlaut
        sag("  %s %8d %8d %9d %9d %9d"
            % (_pad(b.uid, 12), c["mit_ausdruck"], c["aufgeloest"],
               c["post_id_bestimmt"], c["whole_post"],
               d["wortlaut_eindeutig"]))
        su["mit"] += c["mit_ausdruck"]; su["auf"] += c["aufgeloest"]
        su["pid"] += c["post_id_bestimmt"]; su["wp"] += c["whole_post"]
        su["we"] += d["wortlaut_eindeutig"]
    sag("  " + "-" * 66)
    sag("  %s %8d %8d %9d %9d %9d"
        % (_pad("SUMME", 12), su["mit"], su["auf"], su["pid"], su["wp"],
           su["we"]))
    sag("")
    tragend = su["pid"] + su["we"]
    sag("  MIT BESTIMMBARER BEITRAGSNUMMER: %d von %d Textmarkierungen"
        % (su["pid"], su["mit"]))
    sag("  ZUZUEGLICH ueber den Wortlaut eindeutig zuzuordnen: %d"
        % su["we"])
    sag("  Zusammen: %d von %d." % (tragend, su["mit"]))
    sag("  DIE ZWEITE ZAHL IST KEINE ZUSAGE. Sie sagt, dass der Wortlaut in")
    sag("  genau einem Behaelter steht - ob das die richtige Stelle ist,")
    sag("  entscheidet der Ermittler, nicht dieses Werkzeug.")
    offen = su["mit"] - tragend
    sag("")
    sag("  OFFEN: %d Textmarkierung(en) ohne Zuordnung." % offen)
    sag("=" * 78)
    sag("Es wurde nichts am Bestand geaendert.")
    return offen


def lauf(evidence_dir, forensic_dir, nur_uids, sag, beispiele, json_ziel):
    if not os.path.isdir(evidence_dir):
        sag("Verzeichnis gibt es nicht: %s" % evidence_dir)
        return RUECK_ABBRUCH
    gefunden = []
    for name in sorted(os.listdir(evidence_dir)):
        m = _RE_EVIDENCE.match(name)
        if m:
            gefunden.append((m.group(1), os.path.join(evidence_dir, name)))
    gefunden.sort(key=lambda p: int(p[0]))
    if nur_uids:
        gewuenscht = {str(u) for u in nur_uids}
        gefunden = [g for g in gefunden if g[0] in gewuenscht]
    if not gefunden:
        sag("Keine passende evidence_<uid>.db in %s." % evidence_dir)
        return RUECK_ABBRUCH

    sag("=" * 78)
    sag("INVENTAR DER ANKERPUNKTE - es wird NICHTS geschrieben")
    sag("  Beweismittel : %s" % evidence_dir)
    sag("  Seitendaten  : %s" % forensic_dir)
    sag("=" * 78)

    befunde = []
    for uid, pfad in gefunden:
        f_pfad = os.path.join(forensic_dir, "forensic_%s.db" % uid)
        b = AnkerInventar(uid, pfad, f_pfad, beispiele=beispiele).erheben()
        befunde.append(b)
        _ausgeben(b, sag)
        sag("")
    offen = _bilanz(befunde, sag)

    if json_ziel:
        inhalt = {"werkzeug": "anker_inventar", "build": _buildnummer(),
                  "evidence_dir": evidence_dir, "forensic_dir": forensic_dir,
                  "bestaende": [b.als_dict() for b in befunde]}
        try:
            with open(json_ziel, "w", encoding="utf-8") as fh:
                json.dump(inhalt, fh, ensure_ascii=True, indent=1,
                          sort_keys=True)
        except OSError as exc:
            sag("JSON-Datei nicht schreibbar: %s" % exc)
            return RUECK_ABBRUCH
        sag("JSON geschrieben: %s" % json_ziel)
    return RUECK_BEFUND if offen else RUECK_OHNE_BEFUND


def main(argv=None) -> int:
    z = argparse.ArgumentParser(
        prog="anker_inventar",
        description="Inventar der Ankerpunkte in den Seiten-BLOBs und "
                    "Aufloesung der gespeicherten XPath-Ausdruecke. Rein "
                    "lesend.",
        epilog=cli_epilog.epilog("anker_inventar"),
        formatter_class=cli_epilog.HilfeFormat)
    z.add_argument("--config", default="./config.yaml")
    z.add_argument("--evidence-dir", default=None,
                   help="ueberstimmt paths.evidence_db_dir")
    z.add_argument("--forensic-dir", default=None,
                   help="ueberstimmt paths.forensic_db_dir")
    z.add_argument("--uid", action="append", default=[],
                   help="nur diesen Bestand; mehrfach angebbar")
    z.add_argument("--beispiele", type=int, default=20,
                   help="wie viele Einzelfaelle namentlich genannt werden")
    z.add_argument("--protokoll", default=None)
    z.add_argument("--json", dest="json_ziel", default=None)
    args = z.parse_args(argv)

    aufl = werkzeug_konfig.resolver(args)
    evidence_dir = werkzeug_konfig.wert(
        "anker_inventar", args, arg_attribut="evidence_dir",
        arg_name="--evidence-dir", config_schluessel="paths.evidence_db_dir",
        default=coded_default("paths.evidence_db_dir"),
        name="evidence_db_dir", r=aufl)
    forensic_dir = werkzeug_konfig.wert(
        "anker_inventar", args, arg_attribut="forensic_dir",
        arg_name="--forensic-dir", config_schluessel="paths.forensic_db_dir",
        default=coded_default("paths.forensic_db_dir"),
        name="forensic_db_dir", r=aufl)

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
        return lauf(str(evidence_dir), str(forensic_dir), args.uid, sag,
                    args.beispiele, args.json_ziel)
    finally:
        if mitschrift is not None:
            mitschrift.close()


if __name__ == "__main__":
    raise SystemExit(main())
