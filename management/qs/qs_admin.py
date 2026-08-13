#!/usr/bin/env python3
# =============================================================================
# management/qs/qs_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AP-3C (Build 541)
# =============================================================================
# Zweck:
#   Das Kommandozeilenwerkzeug zur QS-Stichprobe. Sein wichtigster Befehl ist
#   'nachziehen' — er rechnet eine gespeicherte Ziehung nach.
#
# ── WARUM ES DIESES WERKZEUG GIBT ───────────────────────────────────────────
#
#   Der Keim wird mitgeschrieben, damit sich eine Ziehung nachrechnen LAESST.
#   Ein Keim, den niemand nachrechnen kann, ist eine Zahl in einer Spalte und
#   kein Beleg. Dieser Befehl ist der Unterschied.
#
#   Er ist bewusst NICHT nur ein Endpunkt: wer die Ziehung im Zweifel
#   nachrechnen muss — eine Verteidigung, eine Innenrevision, die StA —, soll
#   das gegen eine gesicherte Kopie der coordinator.db tun koennen, ohne dass
#   ein Server laeuft und ohne Rechteverwaltung.
#
# ── REIN LESEND ─────────────────────────────────────────────────────────────
#
#   Alle Befehle oeffnen die Datenbank mit mode=ro. Es gibt hier KEINEN
#   Schreibweg: eine Ziehung entsteht ueber den auditierten Endpunkt oder gar
#   nicht. Ein CLI-Schreibweg waere ein unauditierter Nebeneingang.
#
# ── WELCHE DATENBANK GEOEFFNET WIRD (Vorgang e61a7dd4, Build 715) ──────────
#
#   Argument '--db'  >  paths.coordinator_db aus config.yaml  >  ABBRUCH.
#
#   Bis Build 712 stand hier ein Rueckfallwert: _VORGABE_DB =
#   "data/coordinator.db". Das war ein RELATIVER Pfad, und damit hing die
#   gepruefte Datenbank am aktuellen Arbeitsverzeichnis des Aufrufers. Wer
#   den Befehl aus einem anderen Verzeichnis fuhr, pruefte eine ANDERE
#   coordinator.db — oder eine, die es nicht gab — und merkte es nicht. Bei
#   einem Werkzeug, dessen ganze Aufgabe die Qualitaetssicherung ist, ist
#   das der unangenehmste Fall von allen: ein 'DIE ZIEHUNG STIMMT' aus dem
#   falschen Verzeichnis sieht aus wie ein Befund und ist keiner.
#
#   Die Aufloesung liegt seit Build 643/644 an EINER Stelle
#   (core/werkzeug_konfig.py, db_pfad); dreissig Verwaltungswerkzeuge
#   benutzen sie, und der CLI-Katalog begruendet den Abbruch bei jedem
#   einzelnen mit demselben Satz: 'ein erratener Pfad waere schlimmer als
#   ein Abbruch.' Genau diesen Pfad hat qs_admin erraten. Ab hier nicht mehr.
#
# AUFRUF:
#     python -m management.qs.qs_admin liste      --db data/coordinator.db
#     python -m management.qs.qs_admin nachziehen --db data/coordinator.db --sample-id 3
#     python -m management.qs.qs_admin zeigen     --db data/coordinator.db --sample-id 3
#   '--db' darf auch VOR dem Befehl stehen:
#     python -m management.qs.qs_admin --db data/coordinator.db liste
#   Ohne '--db' wird 'paths.coordinator_db' aus der config.yaml genommen;
#   '--config' benennt eine andere Konfigurationsdatei (Vorgabe ./config.yaml).
#   Steht der Pfad weder im Argument noch in der config.yaml, bricht das
#   Werkzeug mit Klartext ab (Rueckgabewert 1) — es raet nicht.
#
# Version: v0.8.715 · Build: 715 · 2026-08-13
# =============================================================================

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from management.qs.qs_repo import QsError, QsRepo          # noqa: E402
from management.qs.qs_vokabular import ZWECKBINDUNG        # noqa: E402
from management.help import cli_epilog  # noqa: E402
# Build 643/644: die Vorrangregel 'Argument > config.yaml > Abbruch' steht
# seit diesen Builds an EINER Stelle (Ticket 15429c75). Build 715 (Vorgang
# e61a7dd4) schliesst qs_admin an sie an.
from core import werkzeug_konfig                           # noqa: E402


def _db_pfad(args) -> str:
    """
    coordinator.db-Pfad: Argument '--db' > paths.coordinator_db > Abbruch.

    BUILD 715 (Vorgang e61a7dd4) — DER RUECKFALLWERT IST ENTFALLEN.
    Bis Build 712 stand hier '_VORGABE_DB = "data/coordinator.db"', ein
    relativer Pfad. Die Begruendung fuer den Wegfall steht im Dateikopf; die
    Aufloesung selbst in core/werkzeug_konfig.py, db_pfad().

    KEIN VORGABEWERT ('default' wird nicht uebergeben) — das ist der Kern
    dieser Aenderung und nicht eine Nachlaessigkeit: Fuer die Fall-Datenbanken
    gibt es im ganzen Bestand bewusst keinen, weil ein erratener Pfad
    schlimmer ist als ein Abbruch (Grundregel 1).

    WAS SICH FUER DIE BEDIENUNG NICHT AENDERT: '--db' wirkt wie bisher und
    darf weiterhin VOR oder HINTER dem Unterbefehl stehen; die Ausgabe auf
    stdout bleibt Zeichen fuer Zeichen dieselbe. Neu ist allein, was ohne
    '--db' geschieht: vorher ein geratener Pfad, jetzt der Blick in die
    config.yaml und andernfalls der Abbruch mit Klartext.
    """
    return werkzeug_konfig.db_pfad(
        "qs_admin", args, arg_attribut="db", arg_name="--db",
        config_schluessel="paths.coordinator_db", name="db")


def _ro(pfad: str) -> sqlite3.Connection:
    """READ-ONLY-Verbindung. Kein PRAGMA, kein Schreibpfad."""
    con = sqlite3.connect("file:%s?mode=ro" % pfad, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _zeit(ts) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC")


def _kopf() -> None:
    print("=" * 78)
    print("AIW — QS-Stichprobe. REIN LESEND.")
    print("=" * 78)
    print(ZWECKBINDUNG)
    print("=" * 78)
    print()


def cmd_liste(args) -> int:
    con = _ro(args.db)
    try:
        b = QsRepo(con).liste(hoechstens=args.hoechstens)
    finally:
        con.close()
    _kopf()
    if not b["ziehungen"]:
        print("Keine Ziehung vorhanden. Das ist ein Leerbefund ueber die "
              "STICHPROBEN und keine Aussage ueber die Auswertungsqualitaet.")
        return 0
    print("%-5s %-20s %-16s %-10s %-9s %s"
          % ("ID", "gezogen am", "von", "Keim", "Umfang", "Stand"))
    for z in b["ziehungen"]:
        print("%-5d %-20s %-16s %-10d %-9s %d von %d geprueft"
              % (z["id"], _zeit(z["gezogen_at"]),
                 (z.get("gezogen_von_name") or "?")[:16], z["seed"],
                 "%d/%d" % (z["stichprobe_n"], z["grundgesamtheit_n"]),
                 z["geprueft_n"], len(z["faelle"])))
    print()
    print("%d Ziehungen insgesamt." % b["ziehungen_gesamt"])
    return 0


def cmd_zeigen(args) -> int:
    con = _ro(args.db)
    try:
        b = QsRepo(con).liste(hoechstens=10_000)
    finally:
        con.close()
    treffer = [z for z in b["ziehungen"] if int(z["id"]) == args.sample_id]
    if not treffer:
        print("[qs] Ziehung %d nicht gefunden." % args.sample_id,
              file=sys.stderr)
        return 2
    z = treffer[0]
    _kopf()
    print("Ziehung %d — %s, gezogen von %s am %s"
          % (z["id"], z["verfahren"], z.get("gezogen_von_name") or "?",
             _zeit(z["gezogen_at"])))
    print("Keim %d · %d von %d Faellen · Filter: %s"
          % (z["seed"], z["stichprobe_n"], z["grundgesamtheit_n"],
             json.dumps(z.get("filter") or {}, ensure_ascii=False,
                        sort_keys=True)))
    print()
    print("%-4s %-10s %-20s %-22s %s"
          % ("Pos", "Fall", "Schicht", "Ergebnis", "geprueft von"))
    for it in z["faelle"]:
        print("%-4d %-10s %-20s %-22s %s"
              % (it["position"], it["subject_id"], it.get("schicht") or "—",
                 it.get("ergebnis_label") or "OFFEN",
                 it.get("geprueft_von_name") or "—"))
    if z["ausserhalb_der_ziehung"]:
        print()
        print("AUSSERHALB DER ZIEHUNG geprueft (zulaessig, wird protokolliert):")
        for r in z["ausserhalb_der_ziehung"]:
            print("  Fall %s — %s (%s)"
                  % (r["subject_id"], r["ergebnis"],
                     r.get("geprueft_von_name") or "?"))
    return 0


def cmd_nachziehen(args) -> int:
    """
    Der Kernbefehl. Er rechnet die Ziehung nach und meldet jede Abweichung.

    RUECKGABEWERT: 0 wenn die Ziehung stimmt, 1 wenn sie abweicht. Der von 0
    verschiedene Wert ist ABSICHT — er macht den Befehl in einem Pruefskript
    verwendbar. Er bedeutet ausdruecklich NICHT 'Fehler': eine Abweichung kann
    erklaerbar sein, weil sich die Grundgesamtheit im laufenden Betrieb
    aendert. Die Bewertung bleibt beim Menschen.
    """
    con = _ro(args.db)
    try:
        r = QsRepo(con).nachziehen(args.sample_id)
    except QsError as exc:
        print("[qs] %s" % exc, file=sys.stderr)
        return 2
    finally:
        con.close()

    _kopf()
    print("Ziehung %d — Verfahren '%s', Keim %d, damals %d Faelle in der "
          "Grundgesamtheit."
          % (r["sample_id"], r["verfahren"], r["seed"], r["damals_n"]))
    print()
    if r["stimmt"]:
        print("ERGEBNIS: DIE ZIEHUNG STIMMT.")
        print("Dieselben %d Faelle in derselben Reihenfolge."
              % len(r["damals_subject_ids"]))
    else:
        print("ERGEBNIS: ABWEICHUNG.")
        for a in r["abweichungen"]:
            print("  - %s" % a)
    print()
    print(r["hinweis"])
    if args.json:
        print()
        print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["stimmt"] else 1


def main(argv=None) -> int:
    # '--db' liegt in einem GEMEINSAMEN Elternparser und nicht nur am
    # Hauptparser. Grund: mit argparse-Vorgabe muesste '--db' VOR dem Befehl
    # stehen ('qs_admin --db X liste'), und die naheliegende Schreibweise
    # ('qs_admin liste --db X') scheiterte mit 'unrecognized arguments'. Bei
    # einem Werkzeug, das im Zweifel von einer Revision unter Zeitdruck
    # bedient wird, ist das kein Schoenheitsfehler. So funktionieren BEIDE
    # Reihenfolgen. (Gefunden in der Rauchprobe zu Build 541.)
    #
    # default=SUPPRESS ist dabei der Kern: mit einem gewoehnlichen Vorgabewert
    # SETZT der Unterparser die Vorgabe erneut und ueberschreibt damit ein
    # '--db', das VOR dem Befehl stand. Mit SUPPRESS fehlt das Attribut, wenn
    # niemand es angegeben hat — die Aufloesung sieht dann ueber
    # getattr(args, "db", None) genau das, was der Fall ist: nichts angegeben.
    #
    # '--config' LIEGT AUS DEMSELBEN GRUND IM ELTERNPARSER (Build 715). Es
    # traegt ebenfalls SUPPRESS und NICHT das sonst uebliche
    # default="./config.yaml": ein Unterparser mit gewoehnlichem Vorgabewert
    # wuerde ein vorangestelltes '--config' ueberschreiben — derselbe Fehler,
    # der bei '--db' in der Rauchprobe zu Build 541 aufgefallen ist. Fehlt das
    # Attribut, nimmt core/setting_resolver.py von sich aus './config.yaml';
    # das Ergebnis ist dasselbe wie bei den uebrigen dreissig Werkzeugen.
    gemeinsam = argparse.ArgumentParser(add_help=False)
    gemeinsam.add_argument("--db", default=argparse.SUPPRESS)
    gemeinsam.add_argument("--config", default=argparse.SUPPRESS)

    p = argparse.ArgumentParser(
        prog="qs_admin", parents=[gemeinsam],
        description="QS-Stichprobe ansehen und nachrechnen. REIN LESEND.",
        epilog=cli_epilog.epilog("qs_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    sub = p.add_subparsers(dest="befehl", required=True)

    a = sub.add_parser("liste", parents=[gemeinsam],
                       help="Ziehungen auflisten")
    a.add_argument("--hoechstens", type=int, default=50)
    a.set_defaults(func=cmd_liste)

    b = sub.add_parser("zeigen", parents=[gemeinsam],
                       help="Eine Ziehung im Einzelnen")
    b.add_argument("--sample-id", type=int, required=True, dest="sample_id")
    b.set_defaults(func=cmd_zeigen)

    c = sub.add_parser("nachziehen", parents=[gemeinsam],
                       help="Eine gespeicherte Ziehung NACHRECHNEN")
    c.add_argument("--sample-id", type=int, required=True, dest="sample_id")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_nachziehen)

    args = p.parse_args(argv)
    # Die Aufloesung steht VOR jeder Pruefung auf die Datei: erst muss
    # feststehen, WELCHE Datei gemeint ist, dann kann man fragen, ob es sie
    # gibt. Kommt kein Pfad zustande, bricht db_pfad() mit Klartext und
    # Rueckgabewert 1 ab (SystemExit) — die Meldung nennt BEIDE Wege.
    args.db = _db_pfad(args)
    if not Path(args.db).exists():
        print("[qs] Datenbank nicht gefunden: %s" % args.db, file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
