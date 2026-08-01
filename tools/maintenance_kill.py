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
# WOHER DIE WERTE KOMMEN (NEU Build 638, Ticket 15429c75):
#   Argument > aus einem Argument abgeleitet > config.yaml > Vorgabewert,
#   aufgeloest ueber maintenance/cli_config.py — dieselbe Stelle wie bei
#   tools/maintenance.py. Der per --coordinator-db uebergebene DATEINAME geht
#   nicht mehr verloren; die Herkunft jedes Werts wird ausgegeben.
#
# Exitcodes: 0 = ok / alle beendet; 1 = Fehler/nichts gefunden; 2 = Nachzuegler.
# Version: v0.8.638 · Build: 638 · 2026-08-01
# =============================================================================

from __future__ import annotations

import argparse
import getpass
import socket
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.setting_resolver import SettingResolverError  # noqa: E402
from maintenance import MaintenancePaths, ServerRegistration  # noqa: E402
from maintenance.cli_config import (herkunft_ausgeben,  # noqa: E402
                                    pfade_aufloesen, resolver_bauen,
                                    wert_aufloesen)
from management.help import cli_epilog  # noqa: E402

#: Das Wort, mit dem eine rechneruebergreifende Beendigung zu bestaetigen ist.
#: Ein blosses 'j' tippt man versehentlich; dieses Wort nicht.
BESTAETIGUNG = "FREMDE BEENDEN"


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


def _fremde_rechner(regs, ziel_uuids, eigener: str) -> list:
    """
    Die betroffenen Anmeldungen auf ANDEREN Rechnern (Vorgang 1155da11).

    Der Vergleich ist unempfindlich gegen Gross-/Kleinschreibung und gegen
    einen angehaengten Domaenenteil ('KK31-PC7' vs. 'kk31-pc7.polizei.nrw'):
    Auf einem geteilten Laufwerk melden sich Rechner nicht zwingend unter
    demselben Namen an, unter dem der aufrufende Rechner sich selbst kennt.
    Im Zweifel gilt ein Rechner als FREMD - eine zu vorsichtige Rueckfrage
    kostet eine Eingabe, eine unterlassene kostet jemand anderem seinen Lauf.
    """
    def kurz(name: str) -> str:
        return str(name or "").strip().lower().split(".")[0]

    ich = kurz(eigener)
    return sorted({regs[u].host for u in ziel_uuids if kurz(regs[u].host) != ich})


def cmd_kill(paths: MaintenancePaths, uuids, alle: bool,
             wait_timeout: int, von: str, bestaetigt: bool = False,
             eingabe=None) -> int:
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

    # =====================================================================
    # BUILD 648 (Vorgang 1155da11) - ERST ZEIGEN, DANN HANDELN.
    #
    # '--all' nahm ALLE Anmeldungen ohne Filter nach Rechner oder Fenster.
    # Auf einem geteilten Laufwerk beendet das auch die Wartungsdienste
    # ANDERER PERSONEN - und zwar ohne dass die aufrufende Person das vorher
    # sieht. Das ist keine Frage der Datensicherheit (ein Wartungsdienst
    # haelt keine unbestaetigten Ergebnisse), sondern der Zusammenarbeit: die
    # andere Person stand ohne Ansage vor einem abgebrochenen Lauf.
    #
    # DIE AUFLISTUNG STEHT JETZT IMMER DA, auch bei '--uuid'. Wer ein
    # Werkzeug bedient, das Prozesse beendet, soll VOR der Wirkung lesen
    # koennen, was gleich geschieht.
    # =====================================================================
    print("\nBetroffene Anmeldungen (%d):" % len(ziel_uuids))
    for u in sorted(ziel_uuids):
        r = regs[u]
        print("  %-36s %-18s %s/%s  build=%s  window=%s"
              % (u, r.role, r.host, r.pid, r.build, r.window_id))

    # DIE RUECKFRAGE GILT NUR FUER '--all', und das ist eine Abgrenzung und
    # keine Nachlaessigkeit: Wer '--uuid' angibt, hat eine bestimmte
    # Anmeldung BENANNT - er hat sie vorher in '--list' gesehen und sich
    # entschieden. Der Vorgang 1155da11 richtet sich gegen den ungesehenen
    # Rundumschlag, nicht gegen die bewusste Einzelentscheidung. Eine
    # Rueckfrage bei jedem Aufruf waere binnen einer Woche eine Taste.
    fremde = _fremde_rechner(regs, ziel_uuids, socket.gethostname()) if alle else []
    if fremde and not bestaetigt:
        print("")
        print("ACHTUNG: Betroffen sind Dienste auf ANDEREN RECHNERN: %s"
              % ", ".join(fremde))
        print("Dieser Rechner ist '%s'. Wer dort gerade eine Wartung faehrt,"
              % socket.gethostname())
        print("steht danach vor einem abgebrochenen Lauf - ohne Ansage.")
        if eingabe is None and not sys.stdin.isatty():
            # OHNE TERMINAL WIRD NICHT GEFRAGT, SONDERN ABGEBROCHEN - dieselbe
            # Haltung wie beim Wartungsvorbehalt (ERGEBNIS_KEIN_TERMINAL).
            # Eine Rueckfrage, die niemand beantworten kann, ist keine
            # Sicherung; sie waere nur ein Absturz mit anderem Namen.
            print("[ABGEBROCHEN] Kein Terminal fuer die Rueckfrage. Wer das "
                  "in einem Skript braucht, gibt '--ja' an und traegt die "
                  "Entscheidung ausdruecklich.", file=sys.stderr)
            return 1
        antwort = (eingabe or input)(
            "Trotzdem beenden? Dann '%s' eingeben: " % BESTAETIGUNG)
        if str(antwort).strip() != BESTAETIGUNG:
            print("[ABGEBROCHEN] Nichts beendet.", file=sys.stderr)
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
    # Build 638: 'default=None' bei allen Argumenten der Vorrangregel — die
    # Begruendung steht ausfuehrlich in tools/maintenance.py bei _add_common.
    ap.add_argument("--config", default=None,
                    help="Pfad zur config.yaml (Vorgabe: ./config.yaml). Ist die "
                         "hier ausdruecklich genannte Datei nicht auswertbar, "
                         "bricht das Werkzeug ab.")
    ap.add_argument("--data-dir", default=None,
                    help="Verzeichnis mit _maintenance/. Ohne Angabe: "
                         "maintenance.data_dir aus config.yaml, sonst ./data.")
    ap.add_argument("--coordinator-db", default=None,
                    help="Pfad zur coordinator.db EINSCHLIESSLICH Dateiname; deren "
                         "Parent ist zugleich das Datenverzeichnis. Ohne Angabe: "
                         "<--data-dir>/coordinator.db, sonst paths.coordinator_db "
                         "aus config.yaml, sonst ./data/coordinator.db.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--list", action="store_true", help="Angemeldete Server auflisten.")
    g.add_argument("--all", action="store_true", help="ALLE angemeldeten Server beenden.")
    ap.add_argument("--ja", action="store_true",
                    help="Die Rueckfrage bei Diensten auf ANDEREN Rechnern "
                         "uebergehen (fuer Skripte). Ohne sie wird gefragt.")
    g.add_argument("--uuid", action="append", default=[],
                   help="UUID eines zu beendenden Servers (mehrfach moeglich).")
    ap.add_argument("--wait-timeout", type=int, default=None,
                    dest="kill_wait_timeout",
                    help="Maximale Wartezeit auf Beendigung in Sekunden. Ohne "
                         "Angabe: maintenance.kill_wait_timeout_seconds aus "
                         "config.yaml, sonst 30.")
    args = ap.parse_args(argv)

    try:
        resolver = resolver_bauen(args)
        data_dir, coordinator_db = pfade_aufloesen(args, resolver)
        wait_timeout = wert_aufloesen(args, resolver, "kill_wait_timeout",
                                      "--wait-timeout", int)
    except SettingResolverError as exc:
        print("[FEHLER] %s" % exc, file=sys.stderr)
        return 1
    herkunft_ausgeben(resolver)

    paths = MaintenancePaths(data_dir)
    paths.verzeichnisse_anlegen()

    if args.list:
        return cmd_list(paths)

    # RBAC (Build 439): Kill ist eine Wiederherstellung. Bei lesbarer
    # coordinator.db wird 'wartung.durchfuehren' erzwungen; ist sie gerade
    # gesperrt, wird der Kill NICHT blockiert (nur protokolliert).
    from maintenance.cli_support import pruefe_wartungsberechtigung
    # Build 638: mit dem AUFGELOESTEN Pfad, Dateiname eingeschlossen.
    ok, meldung = pruefe_wartungsberechtigung(data_dir, recovery=True,
                                              coordinator_db=coordinator_db)
    print("[RBAC] %s" % meldung)
    if not ok:
        print("[FEHLER] Berechtigung fehlt — Kill abgebrochen.", file=sys.stderr)
        return 1

    return cmd_kill(paths, args.uuid, args.all, wait_timeout,
                    von=getpass.getuser(), bestaetigt=args.ja)


if __name__ == "__main__":
    raise SystemExit(main())
