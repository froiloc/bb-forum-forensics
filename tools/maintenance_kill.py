#!/usr/bin/env python3
# =============================================================================
# tools/maintenance_kill.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 438, Werkzeug)
# =============================================================================
# Zweck:
#   Beendet 'rogue' Wartungs-Test-Server (--maintenance), die nach Fensterende
#   weiterlaufen. Der Kill-Kanal ist DATEIVERMITTELT (kill_angefordert in der
#   Anmeldung), damit er ueber den geteilten Share ohne Netz funktioniert.
#
#   --uuid/--all setzt kill_angefordert=true und wartet, bis die betroffenen
#   Anmeldedateien verschwinden (der Server entfernt sie beim Selbstbeenden) —
#   das ist die Bestaetigung. Nachzuegler werden NAMENTLICH gemeldet (GR1).
#
# Aufruf:
#   python tools/maintenance_kill.py --list
#   python tools/maintenance_kill.py --uuid <UUID> [--uuid <UUID2> ...]
#   python tools/maintenance_kill.py --all
#
# Exitcodes: 0 = ok / alle beendet; 1 = Fehler/nichts gefunden; 2 = Nachzuegler.
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

from maintenance import MaintenancePaths, ServerRegistration  # noqa: E402
from management.help import cli_epilog  # noqa: E402


def _resolve_data_dir(args) -> Path:
    if getattr(args, "coordinator_db", None):
        return Path(args.coordinator_db).parent
    return Path(args.data_dir)


def cmd_list(paths: MaintenancePaths) -> int:
    regs = ServerRegistration.alle_laden(paths)
    if not regs:
        print("Keine --maintenance-Server angemeldet.")
        return 0
    print(f"{len(regs)} angemeldete --maintenance-Server:")
    for r in regs:
        kill = "  [KILL ANGEFORDERT]" if r.kill_angefordert else ""
        print(f"  uuid={r.uuid}  {r.role}  {r.host}/{r.pid}  build={r.build}  "
              f"window={r.window_id}{kill}")
    return 0


def cmd_kill(paths: MaintenancePaths, uuids, alle: bool,
             wait_timeout: int, von: str) -> int:
    regs = {r.uuid: r for r in ServerRegistration.alle_laden(paths)}
    if not regs:
        print("Keine --maintenance-Server angemeldet — nichts zu beenden.")
        return 1

    if alle:
        ziel_uuids = list(regs.keys())
    else:
        ziel_uuids = []
        for u in uuids:
            if u in regs:
                ziel_uuids.append(u)
            else:
                print(f"[WARNUNG] uuid nicht gefunden (gemeldet, nicht still): {u}",
                      file=sys.stderr)
        if not ziel_uuids:
            print("[FEHLER] Keine der angegebenen UUIDs ist angemeldet.",
                  file=sys.stderr)
            return 1

    for u in ziel_uuids:
        r = regs[u]
        r.kill_anfordern(paths, von=von)
        print(f"Kill angefordert: uuid={u} ({r.role} {r.host}/{r.pid})")

    print(f"Warte bis {wait_timeout}s auf Beendigung (Verschwinden der Anmeldung) ...")
    frist = time.monotonic() + wait_timeout
    verbleibend = set(ziel_uuids)
    while verbleibend and time.monotonic() < frist:
        time.sleep(0.5)
        noch = {r.uuid for r in ServerRegistration.alle_laden(paths)}
        verbleibend = verbleibend & noch

    if not verbleibend:
        print(f"Alle {len(ziel_uuids)} Server haben sich beendet.")
        return 0

    print(f"[WARNUNG] {len(verbleibend)} Server NICHT bestaetigt beendet "
          f"(namentlich):", file=sys.stderr)
    for u in sorted(verbleibend):
        r = regs[u]
        print(f"  uuid={u} {r.role} {r.host}/{r.pid} — reagiert (noch) nicht. "
              f"Der Kill-Auftrag steht; ggf. Prozess manuell beenden.",
              file=sys.stderr)
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Beendet --maintenance-Test-Server ueber den dateivermittelten "
                    "Kill-Kanal.",
        epilog=cli_epilog.epilog("maintenance_kill"),
        formatter_class=cli_epilog.HilfeFormat)
    ap.add_argument("--data-dir", default="./data",
                    help="Verzeichnis mit _maintenance/ (Default ./data).")
    ap.add_argument("--coordinator-db", default=None,
                    help="Pfad zur coordinator.db; deren Parent ist das Datenverzeichnis.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="Angemeldete Server auflisten.")
    g.add_argument("--all", action="store_true", help="ALLE angemeldeten Server beenden.")
    g.add_argument("--uuid", action="append", default=[],
                   help="UUID eines zu beendenden Servers (mehrfach moeglich).")
    ap.add_argument("--wait-timeout", type=int, default=30, dest="wait_timeout",
                    help="Maximale Wartezeit auf Beendigung in Sekunden (30).")
    args = ap.parse_args(argv)

    data_dir = _resolve_data_dir(args)
    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()

    if args.list:
        return cmd_list(paths)

    # RBAC (Build 439): Kill ist eine Wiederherstellung. Bei lesbarer
    # coordinator.db wird 'wartung.durchfuehren' erzwungen; ist sie gerade
    # gesperrt, wird der Kill NICHT blockiert (nur protokolliert).
    from maintenance.cli_support import pruefe_wartungsberechtigung
    ok, meldung = pruefe_wartungsberechtigung(data_dir, recovery=True)
    print("[RBAC] %s" % meldung)
    if not ok:
        print("[FEHLER] Berechtigung fehlt — Kill abgebrochen.", file=sys.stderr)
        return 1

    return cmd_kill(paths, args.uuid, args.all, args.wait_timeout,
                    von=getpass.getuser())


if __name__ == "__main__":
    raise SystemExit(main())
