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
# Datenverzeichnis: --data-dir oder --coordinator-db (dessen Parent). Dort
#   liegt _maintenance/ und die DBs.
#
# WOHER DIE WERTE KOMMEN (NEU Build 638, Ticket 15429c75):
#   Argument  >  aus einem Argument abgeleitet  >  config.yaml  >  Vorgabewert.
#   Die Reihen sind in maintenance/cli_config.py ausgeschrieben und werden
#   ueber core/setting_resolver.py aufgeloest — EINE Stelle fuer beide
#   Wartungswerkzeuge.
#
#   Bis Build 637 fragte dieses Werkzeug config.yaml ueberhaupt nicht, und
#   ein per --coordinator-db uebergebener abweichender DATEINAME ging
#   verloren (nur das Elternverzeichnis wurde weitergereicht, die
#   RBAC-Pruefung setzte darauf wieder 'coordinator.db'). Beides ist behoben.
#
#   Jeder Aufruf gibt seine Herkunftszeilen aus, BEVOR er etwas tut:
#     [Konfig] config.yaml: /srv/aiw/config.yaml
#     [Konfig] coordinator_db = data/coordinator_2.db  [Argument --coordinator-db]
#     [Konfig] data_dir = data  [Argument --coordinator-db]
#   Damit steht im Sitzungsprotokoll, mit welchen Werten gearbeitet wurde.
#
# Exitcodes: 0 = ok / Wartung freigegeben; 1 = Fehler; 2 = enter gesetzt, aber
#            nicht vollstaendig bestaetigt (Nachzuegler/DB noch gesperrt).
# Version: v0.8.638 · Build: 638 · 2026-08-01
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
from core.setting_resolver import SettingResolverError  # noqa: E402
from maintenance.cli_config import (herkunft_ausgeben,  # noqa: E402
                                    pfade_aufloesen, resolver_bauen,
                                    wert_aufloesen)
from maintenance.cli_support import (exklusiv_beurteilen,  # noqa: E402
                                     pruefe_wartungsberechtigung,
                                     quiesce_status, ziel_pfade)
from management.help import cli_epilog  # noqa: E402


def _einstellungen(args) -> tuple:
    """
    Loest Datenverzeichnis und coordinator.db-Pfad auf und gibt die
    Herkunftszeilen aus (Build 638).

    Returns:
        (data_dir, coordinator_db, resolver) — der Aufloeser wird
        zurueckgegeben, weil die Unterbefehle daraus ihre uebrigen Werte
        (stale, poll, wait_timeout ...) beziehen und JEDE dieser Aufloesungen
        im selben Protokoll landen soll.
    """
    resolver = resolver_bauen(args)
    data_dir, coordinator_db = pfade_aufloesen(args, resolver)
    return (data_dir, coordinator_db, resolver)


# -----------------------------------------------------------------------------
# enter
# -----------------------------------------------------------------------------

def cmd_enter(args) -> int:
    data_dir, coordinator_db, resolver = _einstellungen(args)
    # Die uebrigen Werte VOR der Ausgabe aufloesen, damit das Protokoll
    # vollstaendig ist, wenn es gedruckt wird (Grundregel 1).
    stale = wert_aufloesen(args, resolver, "stale", "--stale", int)
    on_active = wert_aufloesen(args, resolver, "on_active", "--on-active", str)
    min_build = wert_aufloesen(args, resolver, "min_build", "--min-build", int)
    ablauf_min = wert_aufloesen(args, resolver, "ablauf_min", "--ablauf-min", int)
    wait_timeout = wert_aufloesen(args, resolver, "wait_timeout",
                                  "--wait-timeout", int)
    poll = wert_aufloesen(args, resolver, "poll", "--poll", float)
    herkunft_ausgeben(resolver)

    # 'on_active' kann jetzt auch aus config.yaml stammen und ist dort NICHT
    # durch argparse-'choices' gedeckt. Ein unbekannter Wert wuerde sonst
    # klaglos ins Fenster geschrieben und erst die Server verwirren.
    if on_active not in ("pause", "beenden"):
        print("[FEHLER] on_active='%s' ist unzulaessig (pause|beenden). "
              "Herkunft: %s" % (on_active, resolver.herkunft("on_active").quelle),
              file=sys.stderr)
        return 1

    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()

    # RBAC (Build 439): 'enter' erfordert 'wartung.durchfuehren'. Harte Pruefung —
    # coordinator.db ist beim Fenster-Oeffnen noch normal lesbar.
    # Build 638: mit dem AUFGELOESTEN Pfad, Dateiname eingeschlossen.
    ok, meldung = pruefe_wartungsberechtigung(data_dir, recovery=False,
                                              coordinator_db=coordinator_db)
    print("[RBAC] %s" % meldung)
    if not ok:
        print("[FEHLER] Berechtigung fehlt — 'enter' abgebrochen.",
              file=sys.stderr)
        return 1

    if WindowFlag.aktives_fenster(paths) is not None:
        print("[FEHLER] Es ist bereits ein Wartungsfenster aktiv. "
              "Erst 'exit' ausfuehren.", file=sys.stderr)
        return 1

    ablauf = (jetzt_epoch() + ablauf_min * 60) if ablauf_min else None
    window = WindowFlag.neu(
        angefordert_von=getpass.getuser(), grund=args.reason, ziel=args.ziel,
        bei_aktivierung=on_active, min_build=min_build, ablauf_am=ablauf)
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
    print(f"Warte bis {wait_timeout}s auf ACKs und Exklusiv-Lock ...")

    frist = time.monotonic() + wait_timeout
    st = {"gequiesct": [], "offen": [], "tot": [], "fehler": []}
    db_stat: list = []
    bereit = False
    while True:
        st = quiesce_status(paths, window.window_id, stale)
        # BUILD 648 (Vorgang 96f2b18f): dreiwertig. 'nicht messbar' zaehlt
        # NICHT als Ruhe - eine Ruhe, die nie gemessen wurde, ist keine.
        db_stat = [exklusiv_beurteilen(p) for p in dbs]
        alle_db_ok = all(b.ist_ruhig for b in db_stat)
        bereit = (not st["offen"]) and alle_db_ok
        if bereit or time.monotonic() >= frist:
            break
        time.sleep(max(0.2, min(2.0, poll)))

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
    for b in db_stat:
        print(f"  {b.marke} {b.pfad} — {b.grund}")
    # DIE UNMESSBAREN WERDEN EIGENS HERAUSGESTELLT (Build 648). Sie stehen
    # oben schon mit 'UNKLAR' in der Liste, aber wer eine lange Liste
    # ueberfliegt, sieht ein 'UNKLAR' zwischen lauter 'FREI' leicht nicht -
    # und genau dieses eine ist der Grund, warum das Fenster nicht
    # freigegeben wird.
    unklar = [b for b in db_stat if b.zustand == "nicht_messbar"]
    if unklar:
        print("\n--- NICHT MESSBAR (%d) — das ist KEINE Ruhe ---" % len(unklar))
        for b in unklar:
            print(f"  {b.pfad}")
            print(f"     {b.grund}")

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
    data_dir, coordinator_db, resolver = _einstellungen(args)
    herkunft_ausgeben(resolver)
    paths = MaintenancePaths(data_dir)

    # RBAC (Build 439): 'exit' ist eine Wiederherstellung. Bei lesbarer
    # coordinator.db wird 'wartung.durchfuehren' erzwungen; ist sie gerade
    # gesperrt, wird die Wiederherstellung NICHT blockiert (nur protokolliert).
    ok, meldung = pruefe_wartungsberechtigung(data_dir, recovery=True,
                                              coordinator_db=coordinator_db)
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
    data_dir, _coordinator_db, resolver = _einstellungen(args)
    stale = wert_aufloesen(args, resolver, "stale", "--stale", int)
    herkunft_ausgeben(resolver)
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
        st = quiesce_status(paths, f.window_id, stale)
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

# -----------------------------------------------------------------------------
# ALLE Argumente, die an der Vorrangregel teilnehmen, tragen 'default=None'.
#
# DAS IST DER KERN DER BEHEBUNG VON 15429c75 und keine Formsache: Ein
# argparse-Default ist von einer Nutzereingabe nicht zu unterscheiden. Solange
# '--data-dir' den Default './data' trug, sah jeder Aufruf so aus, als habe
# der Aufrufer './data' verlangt — config.yaml konnte damit NIE greifen, auch
# wenn man sie gefragt haette. Die Vorgabewerte stehen jetzt an einer Stelle
# (maintenance/cli_config.VORGABEN) und werden zuletzt eingesetzt.
#
# Die Vorgabewerte stehen weiterhin IM HILFETEXT, damit '--help' die Frage
# "was passiert, wenn ich nichts angebe?" wie bisher beantwortet.
# -----------------------------------------------------------------------------

def _add_common(sp) -> None:
    sp.add_argument("--config", default=None,
                    help="Pfad zur config.yaml (Vorgabe: ./config.yaml). "
                         "Ist die hier ausdruecklich genannte Datei nicht "
                         "auswertbar, bricht das Werkzeug ab.")
    sp.add_argument("--data-dir", default=None,
                    help="Verzeichnis mit _maintenance/ und den DBs. Ohne Angabe: "
                         "maintenance.data_dir aus config.yaml, sonst ./data.")
    sp.add_argument("--coordinator-db", default=None,
                    help="Pfad zur coordinator.db EINSCHLIESSLICH Dateiname; deren "
                         "Parent ist zugleich das Datenverzeichnis. Ohne Angabe: "
                         "<--data-dir>/coordinator.db, sonst paths.coordinator_db "
                         "aus config.yaml, sonst ./data/coordinator.db.")
    sp.add_argument("--stale", type=int, default=None,
                    help="Sekunden, ab denen ein Praesenz-Beacon als veraltet gilt. "
                         "Ohne Angabe: maintenance.stale_seconds aus config.yaml, "
                         "sonst 30.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Steuert ein Wartungsfenster (enter/exit/status).",
        epilog=cli_epilog.epilog("maintenance"),
        formatter_class=cli_epilog.HilfeFormat)
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("enter", help="Wartungsfenster setzen und auf Ruhe warten.")
    _add_common(e)
    e.add_argument("--reason", required=True, help="Grund der Wartung (Pflicht).")
    e.add_argument("--ziel", nargs="+", default=["all"],
                   help="Ziel-DBs: all | coordinator | evidence:1488 ... (Default all).")
    e.add_argument("--on-active", choices=["pause", "beenden"], default=None,
                   dest="on_active",
                   help="Verhalten laufender Normalserver. Ohne Angabe: "
                        "maintenance.on_active aus config.yaml, sonst pause.")
    e.add_argument("--min-build", type=int, default=None, dest="min_build",
                   help="Versions-Waechter: Server mit kleinerem Build beenden sich "
                        "beim Resume (0 = keine Anforderung). Ohne Angabe: "
                        "maintenance.min_build aus config.yaml, sonst 0.")
    e.add_argument("--ablauf-min", type=int, default=None, dest="ablauf_min",
                   help="Fenster laeuft nach N Minuten automatisch ab (0 = nie). "
                        "Ohne Angabe: maintenance.ablauf_min aus config.yaml, "
                        "sonst 0.")
    e.add_argument("--wait-timeout", type=int, default=None, dest="wait_timeout",
                   help="Maximale Wartezeit in Sekunden auf ACK+Lock. Ohne Angabe: "
                        "maintenance.wait_timeout_seconds aus config.yaml, sonst 60.")
    e.add_argument("--poll", type=float, default=None,
                   help="Poll-Intervall der Warteschleife in Sekunden. Ohne Angabe: "
                        "maintenance.poll_seconds aus config.yaml, sonst 1.0.")
    e.set_defaults(func=cmd_enter)

    x = sub.add_parser("exit", help="Wartungsfenster aufheben.")
    _add_common(x)
    x.set_defaults(func=cmd_exit)

    s = sub.add_parser("status", help="Aktuellen Wartungszustand anzeigen.")
    _add_common(s)
    s.set_defaults(func=cmd_status)

    args = ap.parse_args(argv)
    # Build 638: Eine unbrauchbare Konfiguration oder ein nicht wandelbarer
    # Wert aus config.yaml ist ein Abbruch mit Klartext — kein Weiterlaufen
    # mit einem stillschweigend eingesetzten Ersatzwert (Grundregel 1).
    try:
        return args.func(args)
    except SettingResolverError as exc:
        print("[FEHLER] %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
