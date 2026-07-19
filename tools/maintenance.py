#!/usr/bin/env python3
# =============================================================================
# tools/maintenance.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 438, Werkzeug)
# =============================================================================
# Zweck:
#   Steuert ein Wartungsfenster: setzen (enter), aufheben (exit), pruefen (status).
#
#   enter setzt das Flag und WARTET, bis alle lebenden Server ihre ACK geschrieben
#   haben UND die Ziel-DBs exklusiv gesperrt werden koennen. Die ACK allein ist
#   nicht der Beweis — der Exklusiv-Lock-Erwerb ist es (Messen, nicht rechnen).
#   Nachzuegler werden NAMENTLICH gemeldet, nie still uebergangen (Grundregel 1).
#
# Aufruf:
#   python tools/maintenance.py enter --reason "Umstempelung" --ziel coordinator \
#          --on-active beenden --wait-timeout 60
#   python tools/maintenance.py status
#   python tools/maintenance.py exit
#
# Datenverzeichnis: --data-dir (Default ./data) oder --coordinator-db (dessen
#   Parent). Dort liegt _maintenance/ und die DBs.
#
# Exitcodes: 0 = ok / Wartung freigegeben; 1 = Fehler; 2 = enter gesetzt, aber
#            nicht vollstaendig bestaetigt (Nachzuegler/DB noch gesperrt).
# Version: v0.7.438 · Build: 438 · 2026-07-19
# =============================================================================

from __future__ import annotations

import argparse
import getpass
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from maintenance import (MaintenancePaths, PresenceBeacon,  # noqa: E402
                         ServerRegistration, WindowFlag, jetzt_epoch)
from maintenance.cli_support import (exklusiv_pruefen,  # noqa: E402
                                     pruefe_wartungsberechtigung,
                                     quiesce_status, ziel_pfade)


def _resolve_data_dir(args) -> Path:
    if getattr(args, "coordinator_db", None):
        return Path(args.coordinator_db).parent
    return Path(args.data_dir)


# -----------------------------------------------------------------------------
# enter
# -----------------------------------------------------------------------------

def cmd_enter(args) -> int:
    data_dir = _resolve_data_dir(args)
    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()

    # RBAC (Build 439): 'enter' erfordert 'wartung.durchfuehren'. Harte Pruefung —
    # coordinator.db ist beim Fenster-Oeffnen noch normal lesbar.
    ok, meldung = pruefe_wartungsberechtigung(data_dir, recovery=False)
    print("[RBAC] %s" % meldung)
    if not ok:
        print("[FEHLER] Berechtigung fehlt — 'enter' abgebrochen.",
              file=sys.stderr)
        return 1

    if WindowFlag.aktives_fenster(paths) is not None:
        print("[FEHLER] Es ist bereits ein Wartungsfenster aktiv. "
              "Erst 'exit' ausfuehren.", file=sys.stderr)
        return 1

    ablauf = (jetzt_epoch() + args.ablauf_min * 60) if args.ablauf_min else None
    window = WindowFlag.neu(
        angefordert_von=getpass.getuser(), grund=args.reason, ziel=args.ziel,
        bei_aktivierung=args.on_active, min_build=args.min_build, ablauf_am=ablauf)
    window.schreiben(paths)

    dbs = ziel_pfade(data_dir, window.ziel)
    print("=" * 78)
    print("WARTUNGSFENSTER GESETZT")
    print(f"  window_id       : {window.window_id}")
    print(f"  angefordert_von : {window.angefordert_von}")
    print(f"  grund           : {window.grund}")
    print(f"  ziel            : {window.ziel}")
    print(f"  bei_aktivierung : {window.bei_aktivierung}")
    print(f"  min_build       : {window.min_build}")
    print(f"  Ziel-DBs        : {[str(p) for p in dbs] or '(keine)'}")
    print("=" * 78)
    print(f"Warte bis {args.wait_timeout}s auf ACKs und Exklusiv-Lock ...")

    frist = time.monotonic() + args.wait_timeout
    st = {"gequiesct": [], "offen": [], "tot": [], "fehler": []}
    db_stat: list = []
    bereit = False
    while True:
        st = quiesce_status(paths, window.window_id, args.stale)
        db_stat = [(p,) + exklusiv_pruefen(p) for p in dbs]
        alle_db_ok = all(ok for (_p, ok, _grund) in db_stat)
        bereit = (not st["offen"]) and alle_db_ok
        if bereit or time.monotonic() >= frist:
            break
        time.sleep(max(0.2, min(2.0, args.poll)))

    # --- Bericht (Grundregel 1: namentlich) ---------------------------------
    print("\n--- Server ---")
    for b in st["gequiesct"]:
        print(f"  OK     {b.role:20s} {b.host}/{b.pid} (build {b.build})")
    for b in st["offen"]:
        print(f"  OFFEN  {b.role:20s} {b.host}/{b.pid} — noch keine ACK")
    for b in st["tot"]:
        print(f"  TOT?   {b.role:20s} {b.host}/{b.pid} — Beacon veraltet, unbestaetigt")
    for pfad, grund in st["fehler"]:
        print(f"  FEHLER Steuerdatei {pfad}: {grund}")

    print("\n--- Ziel-DBs (Exklusiv-Lock-Beweis) ---")
    for pfad, ok, grund in db_stat:
        print(f"  {'FREI ' if ok else 'BELEGT'} {pfad} — {grund}")

    print("\n" + "=" * 78)
    if bereit:
        print("WARTUNG FREIGEGEBEN — alle lebenden Server gequiesct, Ziel-DBs "
              "exklusiv verfuegbar.")
        print("=" * 78)
        return 0
    print("NICHT vollstaendig bestaetigt innerhalb des Timeouts. Das Fenster "
          "BLEIBT aktiv.")
    print("Offene Server / belegte DBs siehe oben. Erneut pruefen mit 'status', "
          "danach ggf. Arbeit durchfuehren oder 'exit'.")
    print("=" * 78)
    return 2


# -----------------------------------------------------------------------------
# exit
# -----------------------------------------------------------------------------

def cmd_exit(args) -> int:
    data_dir = _resolve_data_dir(args)
    paths = MaintenancePaths(data_dir)

    # RBAC (Build 439): 'exit' ist eine Wiederherstellung. Bei lesbarer
    # coordinator.db wird 'wartung.durchfuehren' erzwungen; ist sie gerade
    # gesperrt, wird die Wiederherstellung NICHT blockiert (nur protokolliert).
    ok, meldung = pruefe_wartungsberechtigung(data_dir, recovery=True)
    print("[RBAC] %s" % meldung)
    if not ok:
        print("[FEHLER] Berechtigung fehlt — 'exit' abgebrochen.",
              file=sys.stderr)
        return 1

    f = WindowFlag.laden(paths)
    if f is None:
        print("Kein Wartungsfenster gesetzt — nichts zu tun.")
        return 0
    WindowFlag.entfernen(paths)
    print(f"Wartungsfenster entfernt (window_id={f.window_id}). "
          f"Pausierte Server nehmen den Betrieb wieder auf.")
    regs = ServerRegistration.alle_laden(paths)
    if regs:
        print(f"Hinweis: {len(regs)} --maintenance-Test-Server noch angemeldet:")
        for r in regs:
            print(f"  uuid={r.uuid} {r.role} {r.host}/{r.pid} build={r.build}")
        print("Diese beenden sich beim naechsten Poll selbst (Fensterende); "
              "sonst tools/maintenance_kill.py.")
    return 0


# -----------------------------------------------------------------------------
# status
# -----------------------------------------------------------------------------

def cmd_status(args) -> int:
    data_dir = _resolve_data_dir(args)
    paths = MaintenancePaths(data_dir)

    f = WindowFlag.laden(paths)
    if f is None:
        print("Wartungsfenster: KEINES gesetzt.")
    else:
        aktiv = f.ist_aktiv()
        print(f"Wartungsfenster: {'AKTIV' if aktiv else 'ABGELAUFEN'} "
              f"(window_id={f.window_id})")
        print(f"  angefordert_von={f.angefordert_von}  grund={f.grund!r}")
        print(f"  ziel={f.ziel}  bei_aktivierung={f.bei_aktivierung}  "
              f"min_build={f.min_build}  ablauf_am={f.ablauf_am}")
        st = quiesce_status(paths, f.window_id, args.stale)
        print(f"  Server: {len(st['gequiesct'])} gequiesct, "
              f"{len(st['offen'])} offen, {len(st['tot'])} vermutlich tot")
        for b in st["offen"]:
            print(f"    OFFEN  {b.role} {b.host}/{b.pid} (build {b.build})")
        for b in st["tot"]:
            print(f"    TOT?   {b.role} {b.host}/{b.pid} — Beacon veraltet")
        for b in st["gequiesct"]:
            print(f"    OK     {b.role} {b.host}/{b.pid}")
        for pfad, grund in st["fehler"]:
            print(f"    FEHLER Steuerdatei {pfad}: {grund}")

    beacons = PresenceBeacon.alle_laden(paths)
    print(f"Praesente Server insgesamt: {len(beacons)}")
    regs = ServerRegistration.alle_laden(paths)
    if regs:
        print(f"--maintenance-Anmeldungen: {len(regs)}")
        for r in regs:
            kill = "  [KILL ANGEFORDERT]" if r.kill_angefordert else ""
            print(f"  uuid={r.uuid} {r.role} {r.host}/{r.pid} "
                  f"build={r.build} window={r.window_id}{kill}")
    return 0


# -----------------------------------------------------------------------------
# main
# -----------------------------------------------------------------------------

def _add_common(sp) -> None:
    sp.add_argument("--data-dir", default="./data",
                    help="Verzeichnis mit _maintenance/ und den DBs (Default ./data).")
    sp.add_argument("--coordinator-db", default=None,
                    help="Pfad zur coordinator.db; deren Parent ist das Datenverzeichnis.")
    sp.add_argument("--stale", type=int, default=30,
                    help="Sekunden, ab denen ein Praesenz-Beacon als veraltet gilt (30).")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Steuert ein Wartungsfenster (enter/exit/status).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enter", help="Wartungsfenster setzen und auf Ruhe warten.")
    _add_common(e)
    e.add_argument("--reason", required=True, help="Grund der Wartung (Pflicht).")
    e.add_argument("--ziel", nargs="+", default=["all"],
                   help="Ziel-DBs: all | coordinator | evidence:1488 ... (Default all).")
    e.add_argument("--on-active", choices=["pause", "beenden"], default="pause",
                   dest="on_active",
                   help="Verhalten laufender Normalserver (Default pause).")
    e.add_argument("--min-build", type=int, default=0, dest="min_build",
                   help="Versions-Waechter: Server mit kleinerem Build beenden sich "
                        "beim Resume (0 = keine Anforderung).")
    e.add_argument("--ablauf-min", type=int, default=0, dest="ablauf_min",
                   help="Fenster laeuft nach N Minuten automatisch ab (0 = nie).")
    e.add_argument("--wait-timeout", type=int, default=60, dest="wait_timeout",
                   help="Maximale Wartezeit in Sekunden auf ACK+Lock (60).")
    e.add_argument("--poll", type=float, default=1.0,
                   help="Poll-Intervall der Warteschleife in Sekunden (1.0).")
    e.set_defaults(func=cmd_enter)

    x = sub.add_parser("exit", help="Wartungsfenster aufheben.")
    _add_common(x)
    x.set_defaults(func=cmd_exit)

    s = sub.add_parser("status", help="Aktuellen Wartungszustand anzeigen.")
    _add_common(s)
    s.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
