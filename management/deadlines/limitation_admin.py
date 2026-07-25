# =============================================================================
# management/deadlines/limitation_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
# =============================================================================
# Zweck (Idee 32, Build 523):
#   NUR-LESENDE CLI zum Parametersatz und zur Rechenschicht. Sie hat drei
#   Aufgaben, und alle drei dienen der Ueberpruefbarkeit:
#
#     pruefen  — laedt den Parametersatz und prueft ihn (inkl. Nachrechnen der
#                Fristen gegen § 78 Abs. 3 StGB). Genau der Befehl, den die StA
#                nach einer Aenderung an der JSON-Datei laufen laesst.
#     zeigen   — listet die hinterlegten Fassungen mit Fundstelle. Der Ausdruck
#                ist das, was gegengelesen wird.
#     rechnen  — rechnet EINE Fristeinschaetzung fuer einen frei angegebenen
#                Tatzeitpunkt. Damit laesst sich jede Zahl der Sicht von Hand
#                nachvollziehen, ohne Datenbank und ohne Server.
#
#   python -m management.deadlines.limitation_admin pruefen
#   python -m management.deadlines.limitation_admin zeigen [--code 184b_abs3]
#   python -m management.deadlines.limitation_admin rechnen --tatzeit 2022-03-14
#          [--stichtag 2026-07-25] [--code C ...] [--vorwarn-tage 365]
#
# BERUEHRT KEINE DATENBANK. Kein CoordinatorWriter, keine Migration — der
#   Migrationsvorbehalt ab 01.07.2026 ist nicht beruehrt.
#
# EXIT-CODE ist Teil der Aussage: 0 = in Ordnung, 2 = Parametersatz unbrauchbar,
#   3 = keine Fristaussage moeglich (z. B. nicht bestaetigt). Ein Skript soll den
#   Unterschied sehen koennen, ohne die Ausgabe zu lesen.
#
# Version: v0.8.523 · Build: 523 · 2026-07-25
# =============================================================================

import argparse
import json
import sys
from datetime import date, datetime, time, timezone

from management.deadlines.limitation import (
    DEFAULT_VORWARN_TAGE,
    assess_limitation,
)
from management.deadlines.limitation_params import (
    LimitationParamsError,
    load_params,
)


def _tag_zu_ts(tag: str) -> int:
    """ISO-Tag -> Unix-Sekunden (Tagesbeginn UTC; das Projekt rechnet UTC)."""
    d = date.fromisoformat(tag)
    return int(datetime.combine(d, time(0, 0), tzinfo=timezone.utc).timestamp())


def _load(args):
    try:
        return load_params(args.params)
    except LimitationParamsError as exc:
        print("[limitation] PARAMETERSATZ UNBRAUCHBAR: %s" % exc,
              file=sys.stderr)
        raise SystemExit(2)


def cmd_pruefen(args) -> int:
    p = _load(args)
    print("[limitation] Parametersatz in Ordnung.")
    print("  Stand:            %s" % p.stand)
    print("  Fassungen:        %d (Tatbestaende: %d)"
          % (len(p.offences), len(p.codes())))
    print("  Vorgabesatz:      %s" % ", ".join(p.vorgabe_tatbestaende))
    print("  Vorbehalte:       %d" % len(p.vorbehalte))
    if p.fehlende_fassungen:
        # KEIN stiller Verzicht: die bekannten Luecken werden BENANNT, auch
        # wenn der Satz sonst in Ordnung ist.
        print("  BEKANNTE LUECKEN: %d" % len(p.fehlende_fassungen))
        for l in p.fehlende_fassungen:
            print("    - %s" % l)
    grund = p.verweigerungsgrund()
    if grund:
        print("[limitation] KEINE FRISTAUSSAGE MOEGLICH: %s" % grund)
        return 3
    print("[limitation] Bestaetigt von %s am %s."
          % (p.bestaetigt_von, p.bestaetigt_am))
    return 0


def cmd_zeigen(args) -> int:
    p = _load(args)
    for o in p.offences:
        if args.code and o.code != args.code:
            continue
        print("--- %s (%s)" % (o.code, o.norm))
        print("    gueltig:        %s bis %s"
              % (o.gueltig_von, o.gueltig_bis or "offen"))
        print("    Strafrahmen:    %s" % o.strafrahmen)
        print("    Hoechststrafe:  %d Monate (%s)"
              % (o.hoechststrafe_monate, o.hoechststrafe_grundlage))
        print("    Frist:          %d Jahre (%s)"
              % (o.frist_jahre, o.frist_grundlage))
        print("    Ruhen § 78b:    %s (%s)"
              % ("JA" if o.ruht_bis_30 else "nein", o.ruht_grundlage))
        # Build 529: Das Ankermerkmal wird MIT ausgegeben. Wer den Satz vor der
        # Bestaetigung liest, muss auch diese Entscheidung sehen — sie
        # entscheidet mit darueber, fuer welche Faelle ueberhaupt eine Frist
        # gerechnet wird.
        print("    Ersatzanker:    %s (%s)"
              % ("Registrierung ZULAESSIG"
                 if o.anker_registrierung_zulaessig
                 else "Registrierung UNZULAESSIG", o.anker_grundlage))
        print("    Fundstelle:     %s" % o.fundstelle)
    return 0


def cmd_rechnen(args) -> int:
    p = _load(args)
    tatzeit = _tag_zu_ts(args.tatzeit) if args.tatzeit else None
    stichtag = (_tag_zu_ts(args.stichtag) if args.stichtag
                else int(datetime.now(timezone.utc).timestamp()))
    a = assess_limitation(tatzeit_ts=tatzeit, params=p, now_ts=stichtag,
                          offence_codes=(args.code or None),
                          vorwarn_tage=args.vorwarn_tage)
    if args.json:
        print(json.dumps(a.to_dict(), ensure_ascii=False, indent=2))
    else:
        print("[limitation] Ampel: %s" % a.ampel)
        print("  Befund:     %s" % a.befund)
        print("  Tatzeit:    %s" % (a.tatzeit_tag or "nicht belegt"))
        print("  Stichtag:   %s (Vorwarnschwelle %d Tage)"
              % (a.stichtag, a.vorwarn_tage))
        if a.massgeblich_norm:
            print("  Massgeblich: %s, Ablauf %s, Restlaufzeit %s Tage"
                  % (a.massgeblich_norm, a.massgeblich_ablauf_tag,
                     a.restlaufzeit_tage))
        for d in a.deadlines:
            print("    - %-26s %-14s %s"
                  % (d.code, d.zustand,
                     (d.ablauf_tag or d.hinweis)))
        if a.ohne_fassung:
            print("  OHNE FASSUNG: %s" % ", ".join(a.ohne_fassung))
        print("  Vorbehalte:")
        for v in a.vorbehalte:
            print("    * %s" % v)
    return 0 if a.aussage_moeglich else 3


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="limitation_admin",
        description="Verjaehrungs-Parametersatz pruefen, zeigen, nachrechnen.")
    ap.add_argument("--params", default=None,
                    help="Pfad zum Parametersatz (Vorgabe: neben dem Modul).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pruefen", help="Parametersatz laden und pruefen.")

    p_zeigen = sub.add_parser("zeigen", help="Hinterlegte Fassungen listen.")
    p_zeigen.add_argument("--code", default=None)

    p_rechnen = sub.add_parser("rechnen", help="Eine Fristeinschaetzung.")
    p_rechnen.add_argument("--tatzeit", default=None,
                           help="ISO-Tag der letzten belegten Tathandlung; "
                                "weglassen = kein Tatzeitpunkt belegt.")
    p_rechnen.add_argument("--stichtag", default=None,
                           help="ISO-Tag des Stichtags (Vorgabe: heute).")
    p_rechnen.add_argument("--code", action="append", default=None,
                           help="Tatbestand (mehrfach); Vorgabe: Vorgabesatz.")
    p_rechnen.add_argument("--vorwarn-tage", type=int,
                           default=DEFAULT_VORWARN_TAGE)
    p_rechnen.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    if args.cmd == "pruefen":
        return cmd_pruefen(args)
    if args.cmd == "zeigen":
        return cmd_zeigen(args)
    return cmd_rechnen(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
