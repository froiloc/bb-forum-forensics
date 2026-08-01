# =============================================================================
# maintenance/cli_config.py
# IT-Forensisches Ermittlungswerkzeug — Wartungsmodus (Build 638)
# =============================================================================
# Zweck:
#   Loest fuer die beiden Wartungswerkzeuge (tools/maintenance.py,
#   tools/maintenance_kill.py) saemtliche Einstellwerte nach der projektweiten
#   Vorrangregel auf — an EINER Stelle, gemeinsam fuer beide Werkzeuge.
#
#       Argument  >  aus einem Argument abgeleitet  >  config.yaml  >  Vorgabewert
#
# ABGRENZUNG ZU maintenance/cli_support.py:
#   cli_support.py ist bewusst OHNE Config-Kopplung gebaut, damit die reinen
#   Helfer vollstaendig testbar bleiben. Diese Trennung bleibt bestehen: die
#   Kopplung an config.yaml wohnt hier und nur hier.
#
# DER VORFALL, DER DAZU GEFUEHRT HAT (Ticket 15429c75, gemeldet 2026-07-30):
#   Aufruf in der PROD-Umgebung:
#     py tools\maintenance.py enter --reason "..." --data-dir data \
#        --poll 3 --coordinator-db data\coordinator_2.db
#   Meldung:
#     [RBAC] coordinator.db fehlt (data\coordinator.db) - RBAC nicht pruefbar,
#     abgebrochen.
#
#   ZWEI FEHLER, nicht einer:
#   (1) DER DATEINAME GING VERLOREN. Das alte _resolve_data_dir() nahm vom
#       uebergebenen Pfad nur das ELTERNVERZEICHNIS; die RBAC-Pruefung setzte
#       darauf wieder den festen Namen 'coordinator.db'. Wer die Datei anders
#       benennt — und genau das tut, wer zwei Bestaende nebeneinander faehrt —,
#       bekam eine Meldung ueber eine Datei, die er nie genannt hatte.
#   (2) config.yaml WURDE NIE GEFRAGT. Beide Werkzeuge kannten die Datei
#       ueberhaupt nicht. Der Melder hatte 'paths.coordinator_db' dort bereits
#       richtig eingetragen; es half nichts.
#
#   Beide Fehler sind hier behoben, und der Vollzug ist ausserdem SICHTBAR:
#   die Werkzeuge geben ihre Herkunftszeilen aus, bevor sie etwas tun.
#
# WELCHE VORRANGREIHEN GELTEN — ausgeschrieben, weil sie sich nicht von selbst
# verstehen:
#
#   coordinator_db (die Datei, gegen die RBAC prueft)
#     1. --coordinator-db                              Argument
#     2. <--data-dir>/coordinator.db                   aus Argument abgeleitet
#     3. paths.coordinator_db                          config.yaml
#     4. ./data/coordinator.db                         Vorgabewert
#     Stufe 2 rangiert ueber config.yaml, weil --data-dir eine Angabe des
#     AUFRUFERS ist. Wer ein Datenverzeichnis nennt, meint dessen
#     coordinator.db und nicht die einer anderen Anlage.
#
#   data_dir (wo _maintenance/ und die Ziel-DBs liegen)
#     1. Elternverzeichnis von --coordinator-db        aus Argument abgeleitet
#     2. --data-dir                                    Argument
#     3. maintenance.data_dir                          config.yaml
#     4. Elternverzeichnis des aufgeloesten coordinator_db
#     5. ./data                                        Vorgabewert
#     STUFE 1 UEBER STUFE 2 IST DIE BISHERIGE REGEL und bleibt unveraendert.
#     Sie stand seit Build 438 im Dateikopf beider Werkzeuge ("--data-dir ...
#     oder --coordinator-db (dessen Parent)") und war die EINZIGE Vorrangregel,
#     die es in diesen Werkzeugen ueberhaupt gab. Sie hier umzudrehen waere
#     eine Verhaltensaenderung, die niemand bestellt hat.
#
# Version: v0.8.638 · Build: 638 · 2026-08-01
# =============================================================================

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:  # pragma: no cover — nur beim Direktaufruf
    sys.path.insert(0, str(_REPO_ROOT))

from core.setting_resolver import SettingResolver, als_pfad  # noqa: E402

#: Die festen Vorgabewerte der Wartungswerkzeuge. Sie standen bis Build 637
#: im argparse-Aufbau und waren damit von einer Nutzereingabe nicht zu
#: unterscheiden. Ab hier stehen sie an EINER Stelle — die argparse-Argumente
#: tragen 'default=None' und bedeuten wieder das, was sie sagen: nicht gesetzt.
VORGABEN: dict = {
    "data_dir":       "./data",
    "coordinator_db": "./data/coordinator.db",
    "stale":          30,      # Sekunden bis ein Praesenz-Beacon veraltet ist
    "on_active":      "pause",  # pause | beenden
    "min_build":      0,        # 0 = keine Anforderung
    "ablauf_min":     0,        # 0 = Fenster laeuft nie von selbst ab
    "wait_timeout":   60,       # Sekunden Wartezeit auf ACK + Exklusiv-Lock
    "poll":           1.0,      # Sekunden zwischen zwei Pruefungen
    "kill_wait_timeout": 30,    # tools/maintenance_kill.py
}

#: Die zugehoerigen Schluessel in config.yaml. EIN Eintrag je Wert; wo es
#: keinen gibt, steht None (dann gilt Argument > Vorgabewert).
SCHLUESSEL: dict = {
    "data_dir":       "maintenance.data_dir",
    "coordinator_db": "paths.coordinator_db",
    "stale":          "maintenance.stale_seconds",
    "on_active":      "maintenance.on_active",
    "min_build":      "maintenance.min_build",
    "ablauf_min":     "maintenance.ablauf_min",
    "wait_timeout":   "maintenance.wait_timeout_seconds",
    "poll":           "maintenance.poll_seconds",
    "kill_wait_timeout": "maintenance.kill_wait_timeout_seconds",
}


def resolver_bauen(args) -> SettingResolver:
    """
    Baut den Aufloeser fuer einen Werkzeugaufruf.

    'pflicht' ist genau dann gesetzt, wenn --config ausdruecklich uebergeben
    wurde: Wer eine Konfigurationsdatei benennt, bekommt keine andere und
    keinen stillen Ersatz. Ohne --config bleibt eine fehlende config.yaml
    folgenlos — die Wartungswerkzeuge muessen auch dann noch laufen, wenn der
    Bestand halb zerlegt ist (siehe cli_support.pruefe_wartungsberechtigung,
    Recovery-Fall).
    """
    ausdruecklich = getattr(args, "config", None)
    return SettingResolver(config_path=ausdruecklich,
                           pflicht=bool(ausdruecklich))


def pfade_aufloesen(args, resolver: SettingResolver) -> Tuple[Path, Path]:
    """
    Loest (data_dir, coordinator_db) nach den oben ausgeschriebenen
    Vorrangreihen auf und protokolliert beide Entscheidungen im Aufloeser.

    Returns:
        (data_dir, coordinator_db) — beide als Path.
    """
    arg_coord = getattr(args, "coordinator_db", None)
    arg_data = getattr(args, "data_dir", None)

    # --- coordinator_db --------------------------------------------------
    # Stufe 2: aus --data-dir abgeleitet. NUR wenn --data-dir tatsaechlich
    # uebergeben wurde — sonst waere der Vorgabewert './data' als Argument
    # getarnt, und genau dieser Trugschluss war Fehler (1) des Vorfalls.
    abgeleitet = (str(Path(arg_data) / "coordinator.db")
                  if arg_data is not None else None)
    coord = resolver.aufloesen(
        name="coordinator_db",
        arg_wert=arg_coord, arg_name="--coordinator-db",
        abgeleitet=abgeleitet,
        abgeleitet_quelle="abgeleitet aus Argument --data-dir "
                          "(fester Dateiname coordinator.db)",
        config_schluessel=SCHLUESSEL["coordinator_db"],
        default=VORGABEN["coordinator_db"],
        wandler=als_pfad)

    # --- data_dir --------------------------------------------------------
    # Stufe 1: Elternverzeichnis von --coordinator-db (bisherige Regel).
    eltern = str(Path(arg_coord).parent) if arg_coord is not None else None
    data = resolver.aufloesen(
        name="data_dir",
        arg_wert=eltern, arg_name="--coordinator-db",
        abgeleitet=arg_data,
        abgeleitet_quelle="Argument --data-dir",
        config_schluessel=SCHLUESSEL["data_dir"],
        # Stufe 4: das Elternverzeichnis der oben aufgeloesten coordinator.db.
        # Damit folgt das Datenverzeichnis einem in config.yaml verlegten
        # Bestand, ohne dass dafuer ein zweiter Eintrag noetig waere.
        default=str(coord.wert.parent),
        wandler=als_pfad)

    # Anmerkung zur Herkunftszeile von 'data_dir': Stufe 1 wird als
    # 'Argument --coordinator-db' ausgewiesen, obwohl der Wert dessen
    # Elternverzeichnis ist. Das ist gewollt — die Fundstelle ist das
    # Argument, und der ausgegebene Wert zeigt, was daraus geworden ist.
    return (data.wert, coord.wert)


def wert_aufloesen(args, resolver: SettingResolver, name: str,
                   arg_name: str, wandler=None) -> Any:
    """
    Loest EINEN der uebrigen Werte (stale, poll, wait_timeout ...) auf.

    Der Name ist zugleich der Attributname am argparse-Ergebnis, der
    Schluessel in VORGABEN und der Schluessel in SCHLUESSEL — eine Zuordnung,
    keine drei.
    """
    if name not in VORGABEN:
        raise KeyError("Unbekannter Einstellwert '%s'." % name)
    return resolver.aufloesen(
        name=name,
        arg_wert=getattr(args, name, None), arg_name=arg_name,
        config_schluessel=SCHLUESSEL.get(name),
        default=VORGABEN[name],
        wandler=wandler).wert


def herkunft_ausgeben(resolver: SettingResolver,
                      strom=None) -> None:
    """
    Gibt die Herkunftszeilen aus — VOR der ersten Wirkung des Werkzeugs.

    Das ist kein Komfort, sondern der Beleg: Im Sitzungsprotokoll steht damit
    schwarz auf weiss, mit welchen Werten das Werkzeug gelaufen ist und woher
    jeder einzelne stammt. Der Vorfall aus 15429c75 waere damit in der ersten
    Zeile sichtbar gewesen.
    """
    ziel = strom if strom is not None else sys.stdout
    for zeile in resolver.protokoll_zeilen():
        print("[Konfig] %s" % zeile, file=ziel)
