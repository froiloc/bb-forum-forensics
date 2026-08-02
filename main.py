#!/usr/bin/env python3
# =============================================================================
# main.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Einstiegspunkt des forensischen Webservers.
#   Führt alle Module in der definierten Startsequenz zusammen.
#   Jeder Fehler in der Startsequenz führt zu einem harten Abbruch —
#   kein stiller Betrieb unter unklaren Bedingungen (Grundregel 1).
#
# Startsequenz (in dieser Reihenfolge):
#   1. CLI-Argumente parsen (argparse)
#   2. ConfigLoader — config.yaml laden + CLI-Overrides anwenden
#   3. Logging initialisieren (setup_logging)
#   4. UserResolver — Systembenutzernamen ermitteln
#   5. ModeResolver — Startmodus + Datenbankpfade auflösen
#   6. StartupChecker — Datenbank-Integrität prüfen
#   7. HostsManager.setup() — hosts-Eintrag setzen/prüfen
#   8. ConnectionManager.open() — alle DB-Verbindungen aufbauen
#   9. ForensicHTTPServer — Server starten und auf Requests warten
#  10. Sauberes Herunterfahren:
#       - ConnectionManager.close()
#       - HostsManager.cleanup()
#
# Eskalationskette (gilt für alle Konfigurationsparameter):
#   CLI-Argument  >  config.yaml  >  Coded Default
#
# Aufruf-Beispiele:
#   python main.py                                  # Modus 'job' (Default)
#   python main.py --mode cli --subject-id 12345    # Modus 'cli'
#   python main.py --mode support --subject-id 12345  # Modus 'support'
#   python main.py --mode cli --username verdaechtiger
#   python main.py --debug                          # Debug-Logging aktivieren
#   python main.py --config /pfad/zu/config.yaml    # Abweichender Config-Pfad
#   python main.py --host 127.0.0.2 --port 8081     # Host/Port explizit setzen
#   python main.py --auto-port                      # nächsten freien Port ab 8080
#   python main.py --auto-port --open-browser       # + Browser autom. öffnen
#
# Eskalationskette (gilt für alle Konfigurationsparameter):
#   CLI-Argument  >  config.yaml  >  Coded Default
#
# Forensische Relevanz:
#   Dieser Einstiegspunkt ist das einzige Skript, das direkt ausgeführt wird.
#   Alle anderen Module werden als Bibliotheken importiert. Die Startsequenz
#   stellt sicher, dass vor dem ersten HTTP-Request alle Integritätsprüfungen
#   abgeschlossen sind.
#
# Abhängigkeiten: argparse, sys — Stdlib + alle core/db/server-Module
# Version: v0.7.469 · Build: 469 · 2026-07-20
# Build 469: Schluesselumstellung user_id -> subject_id (M019)
# =============================================================================

from __future__ import annotations

import argparse
import atexit
import os
import sys
from pathlib import Path
import subprocess
from management.help import cli_epilog  # noqa: E402

# ---------------------------------------------------------------------------
# Projektroot in sys.path eintragen, damit alle Modul-Imports funktionieren
# unabhängig vom Arbeitsverzeichnis beim Aufruf.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.resolve()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _parse_args() -> argparse.Namespace:
    """
    Parst alle CLI-Argumente gemäß Bauplan v0.4, Abschnitt 3.3.

    Gibt ein Namespace-Objekt zurück, das direkt als cli_overrides-Dict
    an ConfigLoader und ModeResolver weitergereicht werden kann.
    """
    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "IT-Forensisches Ermittlungswerkzeug — FluxBB/PunBB-Forum NRW.\n"
            "Forensischer Webserver zur Auswertung beschlagnahmter Forumsdaten."
        ),
        # BUILD 624: der Formatierer bleibt RawDescriptionHelpFormatter und
        # wird NICHT durch cli_epilog.HilfeFormat ersetzt. Die Beschreibung
        # oben enthaelt einen gesetzten Zeilenumbruch; HilfeFormat wuerde sie
        # umbrechen und die beiden Zeilen zu einer machen. Der Raw-Formatierer
        # laesst ohnehin auch den Epilog in Ruhe - genau das, was HilfeFormat
        # sonst herstellt. Das ist der einzige Fall dieser Art im Bestand.
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cli_epilog.epilog("main"),
    )

    parser.add_argument(
        "--config",
        metavar="PFAD",
        default=None,
        help=(
            "Pfad zur config.yaml. "
            "Default: ./config.yaml (relativ zu main.py)."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["job", "cli", "support"],
        default=None,
        help=(
            "Startmodus: "
            "'job' = offenen Job aus coordinator.db laden (Default), "
            "'cli' = subject-id oder username direkt angeben, "
            "'support' = wie cli, aber Schreiben in TEMP-DB."
        ),
    )
    parser.add_argument(
        "--subject-id",
        metavar="INT",
        type=int,
        default=None,
        dest="subject_id",
        help="Subjekt-ID des Beschuldigten (für Modus 'cli'/'support').",
    )
    parser.add_argument(
        "--username",
        metavar="NAME",
        default=None,
        help="Benutzername des Beschuldigten (für Modus 'cli'/'support').",
    )
    parser.add_argument(
        "--forensic-db-dir",
        metavar="PFAD",
        default=None,
        dest="forensic_db_dir",
        help="Überschreibt paths.forensic_db_dir aus config.yaml.",
    )
    parser.add_argument(
        "--evidence-db-dir",
        metavar="PFAD",
        default=None,
        dest="evidence_db_dir",
        help="Überschreibt paths.evidence_db_dir aus config.yaml.",
    )
    parser.add_argument(
        "--default-db",
        metavar="PFAD",
        default=None,
        dest="default_db",
        help="Überschreibt paths.default_db aus config.yaml.",
    )
    parser.add_argument(
        "--coordinator-db",
        metavar="PFAD",
        default=None,
        dest="coordinator_db",
        help="Überschreibt paths.coordinator_db aus config.yaml.",
    )
    parser.add_argument(
        "--host",
        metavar="IP",
        default=None,
        help=(
            "Lausch-Adresse des Servers (überschreibt server.host aus "
            "config.yaml). Default: 127.0.0.2."
        ),
    )
    parser.add_argument(
        "--port",
        metavar="INT",
        type=int,
        default=None,
        help=(
            "Lausch-Port des Servers (überschreibt server.port aus "
            "config.yaml). Ermöglicht parallelen Betrieb mehrerer Fälle."
        ),
    )
    parser.add_argument(
        "--auto-port",
        action="store_true",
        default=False,
        dest="auto_port",
        help=(
            "Sucht ab dem gewünschten Port (Default 8080) den nächsten freien "
            "Port. Der tatsächlich verwendete Port wird auf der Konsole und im "
            "Log ausgegeben. Nützlich für parallelen Mehrfall-Betrieb."
        ),
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        default=False,
        dest="open_browser",
        help=(
            "Öffnet nach dem Serverstart automatisch den Browser auf der "
            "tatsächlich gebundenen Adresse. Browser wird über browser.path "
            "(config.yaml) oder automatische Erkennung ermittelt."
        ),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Aktiviert Debug-Logging (überschreibt logging.level in config.yaml).",
    )
    parser.add_argument(
        "--web-debug",
        action="store_true",
        default=False,
        dest="web_debug",
        help=(
            "Aktiviert clientseitiges Debug-Logging im Browser "
            "(setzt window.FORENSIC_DEBUG=true und window.FORENSIC_EVENT_TRACE=true "
            "in allen ausgelieferten Editor-Seiten). "
            "Nur für Entwicklung/Debugging verwenden."
        ),
    )
    parser.add_argument(
        "--maintenance",
        action="store_true",
        default=False,
        help=(
            "Startet den Server als Wartungs-Test-Server: verhält sich normal "
            "(zum Testen WÄHREND einer Wartung), meldet sich aber unter einer "
            "UUID an und beendet sich bei Fensterende oder auf Kill. Der Start "
            "ist NUR bei aktivem Wartungsfenster erlaubt (Schutz vor "
            "missbräuchlicher Nutzung des Schalters)."
        ),
    )

    return parser.parse_args()


def _build_config_overrides(args: argparse.Namespace) -> dict:
    """
    Baut das cli_overrides-Dict für ConfigLoader aus den geparsten CLI-Argumenten.

    Nur explizit angegebene Argumente werden übernommen — None-Werte
    werden nicht als Overrides eingetragen (sonst würde None den
    config.yaml-Wert überschreiben).
    """
    overrides: dict = {}

    if args.mode is not None:
        overrides["server.mode"] = args.mode
    if args.host is not None:
        overrides["server.host"] = args.host
    if args.port is not None:
        overrides["server.port"] = args.port
    if args.debug:
        overrides["logging.level"] = "debug"
    if args.web_debug:
        overrides["ui.web_debug"] = True
    if args.forensic_db_dir is not None:
        overrides["paths.forensic_db_dir"] = args.forensic_db_dir
    if args.evidence_db_dir is not None:
        overrides["paths.evidence_db_dir"] = args.evidence_db_dir
    if args.default_db is not None:
        overrides["paths.default_db"] = args.default_db
    if args.coordinator_db is not None:
        overrides["paths.coordinator_db"] = args.coordinator_db

    return overrides


def _build_mode_overrides(args: argparse.Namespace) -> dict:
    """
    Baut das cli_overrides-Dict für ModeResolver aus den geparsten CLI-Argumenten.
    """
    return {
        "mode":     args.mode,
        "subject_id": args.subject_id,
        "username": args.username,
    }


def _resolve_listen_port(host: str, start_port: int, auto: bool,
                         max_tries: int = 100) -> int:
    """
    Ermittelt den tatsächlich zu verwendenden Lausch-Port.

    Verhalten:
      - auto=False: Gibt start_port unverändert zurück. Ist der Port belegt,
        scheitert später das Binden im ForensicHTTPServer mit einer
        sprechenden ForensicHTTPServerBindError (bestehendes Verhalten).
      - auto=True: Sucht ab start_port aufwärts den ersten freien Port
        (start_port, start_port+1, …). Geprüft wird per Test-Bind auf (host, p).

    Hinweis zur Race-Condition: Zwischen Test-Bind und dem späteren echten
    Bind im Server kann der Port theoretisch von einem anderen Prozess belegt
    werden. Dieser Restfall wird vom Server weiterhin als BindError behandelt —
    kein stiller Betrieb (Grundregel 1).

    Beleg: Projektgespräch 2026-06-24 (Auto-Port für parallelen Mehrfall-Betrieb).

    Args:
        host:       Lausch-Adresse (z.B. '127.0.0.2').
        start_port: Gewünschter Startport (z.B. 8080).
        auto:       Wenn True, freien Port ab start_port suchen.
        max_tries:  Maximale Anzahl zu prüfender Ports (Schutz vor Endlosschleife).

    Returns:
        Der zu verwendende Port (int).

    Raises:
        RuntimeError: Wenn auto=True und in max_tries Ports kein freier
                      gefunden wurde.
    """
    import socket

    if not auto:
        return start_port

    for offset in range(max_tries):
        candidate = start_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            # SO_REUSEADDR NICHT setzen: Wir wollen einen wirklich freien Port,
            # nicht einen, der nur im TIME_WAIT-Zustand "wiederverwendbar" wäre.
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue

    raise RuntimeError(
        f"Kein freier Port im Bereich {start_port}–{start_port + max_tries - 1} "
        f"auf {host} gefunden."
    )


def main() -> None:
    """
    Hauptfunktion: Startsequenz des forensischen Webservers.

    Jeder Fehler in den Schritten 1–8 führt zu sys.exit(1) mit einer
    klaren Fehlermeldung — kein stiller Betrieb.
    """

    # ------------------------------------------------------------------
    # Schritt 1: CLI-Argumente parsen
    # ------------------------------------------------------------------
    args = _parse_args()

    # ------------------------------------------------------------------
    # Schritt 2: ConfigLoader
    # ------------------------------------------------------------------
    # =================================================================
    # BUILD 646 - DIESER SERVER IST *NICHT* AUF core/werkzeug_konfig
    # UMGESTELLT WORDEN, UND DAS IST EINE ENTSCHEIDUNG, KEIN REST.
    #
    # Zwischen Build 643 und 646 sind 33 Werkzeuge auf das gemeinsame
    # Bauteil umgestellt worden, weil sie die Vorrangregel jeweils von Hand
    # nachgebaut hatten. main.py hat sie NIE nachgebaut: Es uebergibt die
    # Kommandozeilen-Werte als 'cli_overrides' AN den ConfigLoader, und der
    # loest die Kette selbst auf (CLI > config.yaml > Coded Default). Das
    # ist der urspruengliche, im Kopf von core/config_loader.py
    # niedergeschriebene Weg - die 33 Abschriften waren die Abweichung
    # davon, nicht dieser hier.
    #
    # UND EIN UMBAU WAERE HIER SCHAEDLICH, nicht nur unnoetig: Die Overrides
    # werden IN das Konfigurationsobjekt geschrieben. Alles, was danach
    # kommt - core/mode_resolver.py, core/logger.py, db/connection_manager.py,
    # die Ablaufsteuerung - liest 'config.get(...)' und sieht damit die
    # Kommandozeilen-Werte MIT. Wuerde main.py seine Pfade daneben und fuer
    # sich aufloesen, bekaeme der Server einen Pfad und jedes nachgelagerte
    # Bauteil einen anderen. Das waere genau der Fehler, dessentwegen
    # Ticket 15429c75 aufgemacht wurde - nur an einer schlimmeren Stelle.
    #
    # OFFEN BLEIBT EINE SACHE, und sie ist zu nennen: Der Server kann nicht
    # sagen, WOHER ein Wert stammt. Die umgestellten Werkzeuge koennen das
    # seit Build 643 (AIW_KONFIG_HERKUNFT=1). Hier fehlt es. Der Weg dorthin
    # fuehrt ueber den ConfigLoader (er kennt seit Build 638 die Herkunft
    # ueber 'stammt_aus_datei') und nicht ueber einen zweiten Aufloeser.
    # =================================================================
    from core.config_loader import ConfigLoader, ConfigLoaderError

    config_path = args.config or str(_PROJECT_ROOT / "config.yaml")
    config_overrides = _build_config_overrides(args)

    try:
        config = ConfigLoader(config_path=config_path, cli_overrides=config_overrides)
    except ConfigLoaderError as exc:
        print(f"[FEHLER] Konfiguration konnte nicht geladen werden:\n{exc}",
              file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Schritt 3: Logging initialisieren
    # ------------------------------------------------------------------
    from core.logger import setup_logging

    try:
        setup_logging(
            level   = config.get("logging.level", "info"),
            logfile = config.get("logging.logfile", "./logs/forensic_server.log"),
            max_bytes    = int(config.get("logging.max_bytes",    10 * 1024 * 1024)),
            backup_count = int(config.get("logging.backup_count", 5)),
        )
    except Exception as exc:
        print(f"[FEHLER] Logging konnte nicht initialisiert werden:\n{exc}",
              file=sys.stderr)
        sys.exit(1)

    from core.logger import get_logger
    logger = get_logger(__name__)

    # Git-Befehl ausführen
    #result = subprocess.run(['git', 'log', '-1'], capture_output=True, text=True)

    # Output in Zeilen aufteilen
    #lines = result.stdout.strip().split('\n')

    # Zeile 3 und 5 extrahieren (Index 2 und 4, da Python bei 0 zählt)
    #line_3 = lines[2] if len(lines) > 2 else ""
    #line_5 = lines[4] if len(lines) > 4 else ""

    # Als String speichern (z.B. kombiniert oder separat)
    combined_data = ""
    #combined_data = f"- {line_3} {line_5} "
    
    logger.info(
        f"=== Forensischer Webserver startet {combined_data}==="
    )
    logger.info("Config geladen: '%s'", config_path)

    # ------------------------------------------------------------------
    # Schritt 4: UserResolver
    # ------------------------------------------------------------------
    from core.user_resolver import UserResolver, UserResolverError

    try:
        user_resolver = UserResolver()
        logger.info("Systembenutzer: '%s'", user_resolver.system_username)
    except UserResolverError as exc:
        logger.error("Systembenutzer konnte nicht ermittelt werden: %s", exc)
        print(f"[FEHLER] Systembenutzer konnte nicht ermittelt werden:\n{exc}",
              file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # Schritt 5: ModeResolver
    # ------------------------------------------------------------------
    from core.mode_resolver import ModeResolver, ModeResolverError

    mode_overrides = _build_mode_overrides(args)

    try:
        resolver = ModeResolver(config, user_resolver, mode_overrides)
        context  = resolver.resolve()
    except ModeResolverError as exc:
        logger.error("Startmodus konnte nicht aufgelöst werden: %s", exc)
        print(f"[FEHLER] Startmodus konnte nicht aufgelöst werden:\n{exc}",
              file=sys.stderr)
        sys.exit(1)

    logger.info(
        "Kontext: mode='%s', subject_id=%d, username='%s'",
        context.mode, context.subject_id, context.username,
    )
    logger.info("forensic_db : '%s'", context.forensic_db)
    logger.info("evidence_db : '%s'", context.evidence_db)
    logger.info("default_db  : '%s'", context.default_db)
    logger.info("coordinator : '%s'", context.coordinator_db)

    # ------------------------------------------------------------------
    # Schritt 5a: Wartungsmodus-Pfade + Start-Guard (Build 436)
    # Das Wartungsprotokoll liegt dateibasiert unter dem geteilten
    # Datenverzeichnis (dort, wo coordinator.db liegt), damit es ueber alle VMs
    # hinweg wirkt und keine DB benoetigt, die man gerade stillstellen will.
    #
    # --maintenance darf NUR bei AKTIVEM Wartungsfenster starten. Ein Start
    # ausserhalb wird aktiv verweigert — sonst waere der Schalter ein Weg, das
    # normale Quiesce-Verhalten zu umgehen (Schutz vor feindlicher Uebernahme).
    # ------------------------------------------------------------------
    from maintenance import MaintenancePaths, WindowFlag

    _maint_data_dir = Path(context.coordinator_db).parent
    _maint_paths = MaintenancePaths(_maint_data_dir)
    try:
        _maint_paths.verzeichnisse_anlegen()
    except Exception as _exc:
        logger.warning("Wartungsverzeichnisse konnten nicht angelegt werden: %s",
                       _exc)

    if args.maintenance:
        _startfenster = WindowFlag.aktives_fenster(_maint_paths)
        if _startfenster is None:
            logger.error(
                "--maintenance: Start verweigert — kein aktives Wartungsfenster.")
            print(
                "[FEHLER] --maintenance: Ein Start im Wartungsmodus ist NUR bei "
                "aktivem Wartungsfenster erlaubt.\n"
                "Es ist derzeit kein Fenster aktiv — Start verweigert "
                "(Schutz vor missbräuchlicher Nutzung des Schalters).",
                file=sys.stderr)
            sys.exit(1)
        logger.warning(
            "LÄUFT IM WARTUNGSMODUS — window_id=%s, grund=%r. Der Server "
            "verhält sich normal (Testbetrieb), beendet sich aber bei Fensterende "
            "oder auf Kill.",
            _startfenster.window_id, _startfenster.grund)

    # ------------------------------------------------------------------
    # Schritt 6: StartupChecker
    # ------------------------------------------------------------------
    from core.startup_checks import StartupChecker, StartupCheckError

    try:
        checker = StartupChecker(context, config)
        checker.run_all()
    except StartupCheckError as exc:
        logger.error("Startprüfung fehlgeschlagen: %s", exc)
        print(f"[FEHLER] Startprüfung fehlgeschlagen:\n{exc}", file=sys.stderr)
        sys.exit(1)

    logger.info("Alle Startprüfungen bestanden.")

    # ------------------------------------------------------------------
    # Schritt 6b: SCHEMASTAND ALLER DATENBANKEN (Build 657)
    #
    # StartupChecker darüber prüft Erreichbarkeit, Schemaversion und
    # Integrität der forensic_db — nicht aber den MIGRATIONSSTAND der
    # übrigen Datenbanken. Beim Vorfall vom 2026-08-02 lag die templates.db
    # im Rückstand; niemand hat es gesagt, obwohl das Werkzeug dafür seit
    # dem 30. Juli existiert.
    #
    # Der Katalog (management/db_katalog.py) führt jede Datenbank mit dem
    # Grund ihrer Einstufung. GEHEILT WIRD NICHT — der Befund nennt den
    # Befehl, ausgeführt wird er von einem Menschen.
    #
    # Die Prüfung darf den Start NIE verhindern (blockierende Fälle bleiben
    # beim StartupChecker, wo sie hingehören) und sie darf nie werfen.
    # ------------------------------------------------------------------
    try:
        from management.db_startbefund import (
            DbStartbefund, meldezeilen, zusammenfassung)
        _db_befunde = DbStartbefund("ermittler", config).erhebe()
        for _zeile in meldezeilen(_db_befunde):
            print(_zeile, file=sys.stderr)
            logger.warning(_zeile)
        logger.info(zusammenfassung(_db_befunde))
        print("[main] %s" % zusammenfassung(_db_befunde))
    except Exception as exc:  # pragma: no cover
        logger.warning("Schemastand nicht prüfbar: %s", exc)
        print("[main] WARNUNG: Schemastand nicht prüfbar: %s" % exc,
              file=sys.stderr)

    # ------------------------------------------------------------------
    # Schritt 7: HostsManager
    # ------------------------------------------------------------------
    from core.hosts_manager import HostsManager, HostsManagerError

    hosts_manager = HostsManager(config)

    try:
        hosts_manager.setup()
    except HostsManagerError as exc:
        logger.error("hosts-Eintrag konnte nicht gesetzt werden: %s", exc)
        print(f"[FEHLER] hosts-Eintrag konnte nicht gesetzt werden:\n{exc}",
              file=sys.stderr)
        sys.exit(1)

    # ------------------------------------------------------------------
    # atexit-Handler: Sicherheitsnetz für unerwartetes Prozessende
    # (z.B. SIGTERM, Konsolenfenster schließen, Task-Manager-Kill).
    # Stellt sicher, dass der hosts-Eintrag auch dann entfernt wird,
    # wenn der finally-Block in serve_forever_logged() nicht erreicht wird.
    # Idempotent: HostsManager.cleanup() prüft intern ob dieser Run
    # den Eintrag gesetzt hat (_entry_added_by_us).
    # ------------------------------------------------------------------
    atexit.register(hosts_manager.cleanup)

    # ------------------------------------------------------------------
    # Schritt 8: ConnectionManager — alle DB-Verbindungen aufbauen
    # ------------------------------------------------------------------
    from db.connection_manager import ConnectionManager

    try:
        conn_mgr = ConnectionManager(context, config)
        bundle   = conn_mgr.open()
    except Exception as exc:
        logger.error("Datenbankverbindungen konnten nicht aufgebaut werden: %s",
                     exc, exc_info=True)
        print(f"[FEHLER] Datenbankverbindungen konnten nicht aufgebaut werden:\n{exc}",
              file=sys.stderr)
        # HostsManager bereits aktiv — cleanup versuchen
        hosts_manager.cleanup()
        sys.exit(1)

    logger.info("Alle Datenbankverbindungen aufgebaut.")

    # ------------------------------------------------------------------
    # Schritt 8a: Stale Locks bereinigen (Build 281)
    # Nach einem Server-Neustart sind alle Locks in editor_locks veraltet:
    # Die zugehoerigen SSE-Verbindungen und Grace-Period-Timer existieren
    # nicht mehr. Ohne Bereinigung blockieren diese Stale Locks alle
    # acquire()-Versuche mit HTTP 423.
    # Beleg: Bugfix-Liste 2.23, Projektgespraech 2026-06-07
    # ------------------------------------------------------------------
    try:
        _stale = bundle.evidence.clear_stale_locks_on_startup()
        if _stale:
            logger.warning(
                "Startup: %d Stale-Lock(s) bereinigt — "
                "Server war zuvor nicht korrekt beendet worden.", _stale
            )
    except Exception as _exc:
        logger.warning("Startup: Stale-Lock-Bereinigung fehlgeschlagen: %s", _exc)

    # ------------------------------------------------------------------
    # Schritt 8b: Build-Info laden und Datei-Prüfsummen loggen
    # Beleg: Projektgespräch 2026-05-11
    # ------------------------------------------------------------------
    from core.build_info import BuildInfo, log_file_checksums
    _build_info = BuildInfo(project_root=Path(__file__).parent)
    log_file_checksums(Path(__file__).parent)

    # ------------------------------------------------------------------
    # Schritt 8c: CrossAnnotationIntegrator starten (Build 182 — Bug 2.78)
    # Integriert ausstehende Fremd-Annotationen aus Transportdateien.
    # Laeuft einmalig beim Start + stündlich im Hintergrundthread.
    # Beleg: Projektgespraech 2026-05-12.
    # ------------------------------------------------------------------
    from forensic_api.cross_annotation_integrator import CrossAnnotationIntegrator
    _integrator = CrossAnnotationIntegrator(bundle, context, config)
    try:
        _integrator.run_once()
    except Exception as _exc:
        logger.warning("CrossAnnotationIntegrator Startup-Lauf fehlgeschlagen: %s", _exc)
    _integrator.start_background_polling()

    # Schritt 9: ForensicHTTPServer starten
    # ------------------------------------------------------------------
    from server.http_server import ForensicHTTPServer, ForensicHTTPServerBindError

    host = str(config.get("server.host", "127.0.0.2"))
    # Default-Port 8080 (forensische VM, localhost). Eskalation: CLI > config > 8080.
    # Beleg: Projektgespräch 2026-06-24 — Default von 80 auf 8080 angeglichen
    # (entspricht config.yaml und start.bat; Port 80 erfordert Adminrechte).
    desired_port = int(config.get("server.port", 8080))

    try:
        port = _resolve_listen_port(host, desired_port, auto=args.auto_port)
    except RuntimeError as exc:
        logger.error("Port-Auflösung fehlgeschlagen: %s", exc)
        print(f"[FEHLER] {exc}", file=sys.stderr)
        bundle.close()
        hosts_manager.cleanup()
        sys.exit(1)

    if args.auto_port and port != desired_port:
        logger.warning(
            "Auto-Port: gewünschter Port %d belegt — verwende %d.",
            desired_port, port,
        )
        # Auf der Konsole prominent ausgeben, damit der Ermittler die korrekte
        # URL kennt (der Browser wird bei --open-browser automatisch geöffnet).
        print(
            f"\n[INFO] Port {desired_port} belegt. Server läuft auf Port {port}.\n"
            f"       URL: http://{host}:{port}/\n",
            file=sys.stderr,
        )

    try:
        server = ForensicHTTPServer(host, port, bundle, context, config, build_info=_build_info)
    except ForensicHTTPServerBindError as exc:
        # Differenzierte Fehlermeldung: Port belegt, kein Zugriff, ungültige Adresse.
        # Die Meldung enthält bereits konkrete Handlungshinweise für den Ermittler.
        logger.error("Server-Socket konnte nicht gebunden werden: %s", exc)
        print(f"\n[FEHLER] Server konnte nicht gestartet werden:\n\n{exc}\n",
              file=sys.stderr)
        bundle.close()
        hosts_manager.cleanup()
        sys.exit(1)
    except Exception as exc:
        logger.error("Server konnte nicht initialisiert werden: %s",
                     exc, exc_info=True)
        print(f"[FEHLER] Server konnte nicht initialisiert werden:\n{exc}",
              file=sys.stderr)
        bundle.close()
        hosts_manager.cleanup()
        sys.exit(1)

    logger.info(
        "Server bereit: http://%s:%d | v%s Build %d (%s)",
        host, port,
        _build_info.version, _build_info.build, _build_info.date,
    )
    logger.info(
        "Ermittlung: subject_id=%d ('%s'), Modus='%s'",
        context.subject_id, context.username, context.mode,
    )
    if args.web_debug:
        logger.warning(
            "⚠  --web-debug aktiv: FORENSIC_DEBUG=true wird an alle "
            "Browser-Clients gesendet. Nur für Entwicklung verwenden!"
        )

    # ------------------------------------------------------------------
    # Schritt 9a: Browser öffnen (optional, --open-browser)
    # Der Socket ist an dieser Stelle bereits gebunden (ForensicHTTPServer
    # bindet im Konstruktor). Damit ist garantiert: Server zuerst, dann
    # Browser — der Browser trifft auf einen lauschenden Server und die
    # korrekte (ggf. automatisch gewählte) Portnummer.
    #
    # Der Browser-Start ist eine reine Komfortfunktion ohne Beweisrelevanz.
    # Schlägt er fehl, läuft der Server weiter; der Ermittler kann die URL
    # manuell aufrufen. Es wird daher KEIN Abbruch ausgelöst.
    # Beleg: Projektgespräch 2026-06-24 (Light-Version / Browser-Start)
    # ------------------------------------------------------------------
    if args.open_browser:
        from core.browser_launcher import BrowserLauncher
        _url = f"http://{host}:{port}/"
        logger.info("Öffne Browser auf '%s' …", _url)
        try:
            BrowserLauncher(config, project_root=_PROJECT_ROOT).open(_url)
        except Exception as _exc:
            logger.warning("Browser konnte nicht geöffnet werden: %s "
                           "(URL bitte manuell aufrufen: %s)", _exc, _url)

    # ------------------------------------------------------------------
    # Schritt 9b: Watchdog-Thread für Freeze-Diagnose
    # ------------------------------------------------------------------
    # Zweck: Wenn der Server einfriert, enthält freeze_dump.txt den
    # Stack-Trace aller Threads zum Zeitpunkt des letzten Watchdog-Zyklus.
    # So kann nachvollzogen werden, welcher Thread blockiert ist.
    #
    # Mechanismus:
    #   - Watchdog-Thread schreibt alle _WATCHDOG_INTERVAL_SEC einen
    #     Heartbeat-Log-Eintrag und einen faulthandler-Dump in eine Datei.
    #   - faulthandler.dump_traceback() schreibt Stack-Traces aller Threads,
    #     auch wenn der Hauptprozess eingefroren ist (läuft im Watchdog-Thread).
    #   - Wenn der Heartbeat im Log ausbleibt, ist der Watchdog-Thread selbst
    #     blockiert — das deutet auf einen GIL-Deadlock hin.
    #   - Wenn der Heartbeat läuft aber der Dump leer ist, blockiert etwas
    #     unterhalb des GIL (Kernel-Wait, I/O, SQLite-C-Layer).
    #
    # Die Datei wird bei jedem Zyklus überschrieben — enthält immer den
    # letzten bekannten Zustand vor dem Einfrieren.
    #
    # Beleg: Projektgespräch 2026-04-23 — Freeze-Diagnose PROD
    import faulthandler as _faulthandler
    import threading as _threading
    import time as _time

    _WATCHDOG_INTERVAL_SEC = 30
    _watchdog_dump_path = (
        Path(config.get("logging.logfile", str(_PROJECT_ROOT / "data" / "logs" / "forensic_server.log")))
        .parent / "freeze_dump.txt"
    )

    def _watchdog_loop() -> None:
        """Watchdog: Heartbeat + faulthandler-Dump alle 30 Sekunden."""
        while True:
            _time.sleep(_WATCHDOG_INTERVAL_SEC)
            logger.debug(
                "Watchdog: Heartbeat (Dump: '%s')", _watchdog_dump_path
            )
            try:
                with open(_watchdog_dump_path, "w", encoding="utf-8") as _f:
                    _faulthandler.dump_traceback(_f, all_threads=True)
            except Exception as _exc:
                logger.warning("Watchdog: Dump fehlgeschlagen: %s", _exc)

    _watchdog_thread = _threading.Thread(
        target=_watchdog_loop,
        name="forensic-watchdog",
        daemon=True,
    )
    _watchdog_thread.start()
    logger.info(
        "Watchdog gestartet (Intervall: %ds, Dump: '%s')",
        _WATCHDOG_INTERVAL_SEC, _watchdog_dump_path,
    )

    # ------------------------------------------------------------------
    # Schritt 9c: Wartungsmodus-Integration (Build 436)
    # ------------------------------------------------------------------
    import socket as _socket
    import types as _types
    from maintenance import (Aktion, AckFile, MaintenanceController,
                             MaintenanceGate, MaintenancePoller, PresenceBeacon,
                             ServerRegistration)

    _gate = MaintenanceGate()
    server.maintenance_gate = _gate

    _mh_host = _socket.gethostname()
    _mh_pid = os.getpid()
    _mh_role = f"webserver:{context.subject_id}"

    # Anmeldung (--maintenance) bzw. Praesenz-Beacon (Normalserver)
    _registration = None
    _beacon = None
    if args.maintenance:
        _fnow = WindowFlag.aktives_fenster(_maint_paths)
        _registration = ServerRegistration.neu(
            role=_mh_role, host=_mh_host, pid=_mh_pid, build=_build_info.build,
            window_id=(_fnow.window_id if _fnow else ""), port=port,
            subject_id=context.subject_id, config=config_path)
        try:
            _registration.schreiben(_maint_paths)
            logger.warning("Wartungs-Anmeldung geschrieben: uuid=%s", _registration.uuid)
        except Exception as _exc:
            logger.warning("Wartungs-Anmeldung konnte nicht geschrieben werden: %s", _exc)
    else:
        _beacon = PresenceBeacon(
            role=_mh_role, host=_mh_host, pid=_mh_pid, build=_build_info.build,
            subject_id=context.subject_id, port=port)
        try:
            _beacon.schreiben(_maint_paths)
        except Exception as _exc:
            logger.warning("Präsenz-Beacon konnte nicht geschrieben werden: %s", _exc)

    # Laufzeit-Referenzen, die beim Resume ausgetauscht werden (Bundle/Integrator).
    _rt = _types.SimpleNamespace(bundle=bundle, integrator=_integrator)
    _QUIESCE_DRAIN_TIMEOUT_S = float(config.get("maintenance.drain_timeout_sec", 30))

    def _ack_schreiben() -> None:
        _f = WindowFlag.laden(_maint_paths)
        _wid = _f.window_id if _f else ""
        try:
            AckFile(role=_mh_role, host=_mh_host, pid=_mh_pid,
                    window_id=_wid).schreiben(_maint_paths)
        except Exception as _exc:
            logger.warning("ACK konnte nicht geschrieben werden: %s", _exc)

    def _ack_entfernen() -> None:
        try:
            AckFile(role=_mh_role, host=_mh_host, pid=_mh_pid,
                    window_id="").entfernen(_maint_paths)
        except Exception:
            pass

    def _quiesce(beenden: bool) -> None:
        logger.warning("Wartungsmodus: Quiesce startet (beenden=%s).", beenden)
        if not _gate.block_and_drain(timeout=_QUIESCE_DRAIN_TIMEOUT_S):
            logger.warning(
                "Wartungsmodus: Drain-Timeout (%ss) — es liefen noch Requests "
                "(z.B. offene SSE-Verbindung). Fahre dennoch fort.",
                _QUIESCE_DRAIN_TIMEOUT_S)
        try:
            _rt.integrator.stop()
        except Exception as _exc:
            logger.warning("Integrator-Stop fehlgeschlagen: %s", _exc)
        try:
            _rt.bundle.close()
        except Exception as _exc:
            logger.warning("Bundle-Close fehlgeschlagen: %s", _exc)
        _ack_schreiben()
        logger.warning("Wartungsmodus: Quiesce abgeschlossen — DB-Verbindungen "
                       "freigegeben, ACK geschrieben.")
        if beenden:
            logger.warning("Wartungsmodus: bei_aktivierung=beenden — Server wird beendet.")
            server.shutdown()

    def _resume() -> None:
        logger.warning("Wartungsmodus: Fenster beendet — Resume.")
        try:
            from db.connection_manager import ConnectionManager as _CM
            _neu = _CM(context, config).open()
        except Exception as _exc:
            logger.error("Resume: DB-Verbindungen konnten NICHT wieder aufgebaut "
                         "werden: %s — Server wird beendet.", _exc, exc_info=True)
            server.shutdown()
            return
        _rt.bundle = _neu
        server.bundle = _neu
        # Router haelt eine eigene (gecachte) Bundle-Referenz und Sub-Handler —
        # deshalb komplett neu aufbauen. Sicher, weil das Gate blockiert ist.
        try:
            from server.router import Router as _Router
            server.router = _Router(_neu, context, config, build_info=_build_info)
        except Exception as _exc:
            logger.error("Resume: Router-Neuaufbau fehlgeschlagen: %s — Server "
                         "wird beendet.", _exc, exc_info=True)
            server.shutdown()
            return
        try:
            from forensic_api.cross_annotation_integrator import CrossAnnotationIntegrator as _CAI
            _neui = _CAI(_neu, context, config)
            _neui.start_background_polling()
            _rt.integrator = _neui
        except Exception as _exc:
            logger.warning("Resume: Integrator-Neustart fehlgeschlagen: %s", _exc)
        _ack_entfernen()
        _gate.unblock()
        logger.warning("Wartungsmodus: Resume abgeschlossen — Betrieb wieder aufgenommen.")

    def _beenden_versionswaechter() -> None:
        logger.warning(
            "Wartungsmodus: Fenster beendet, aber eigener Build %d unterschreitet "
            "min_build des Fensters — Server wird beendet, damit keine alte "
            "Version mit neuen Daten arbeitet.", _build_info.build)
        server.shutdown()

    def _selbstbeendigung() -> None:
        logger.warning("Wartungsmodus (--maintenance): Fenster beendet — "
                       "Test-Server beendet sich selbst.")
        server.shutdown()

    def _kill() -> None:
        logger.warning("Wartungsmodus (--maintenance): Kill angefordert — "
                       "Server wird beendet.")
        server.shutdown()

    _maint_aktionen = {
        Aktion.QUIESCE_PAUSE: lambda: _quiesce(beenden=False),
        Aktion.QUIESCE_BEENDEN: lambda: _quiesce(beenden=True),
        Aktion.RESUME: _resume,
        Aktion.BEENDEN_VERSIONSWAECHTER: _beenden_versionswaechter,
        Aktion.SELBSTBEENDIGUNG_FENSTERENDE: _selbstbeendigung,
        Aktion.KILL: _kill,
    }

    def _touch_praesenz() -> None:
        if _beacon is not None:
            try:
                _beacon.touch(_maint_paths)
            except Exception:
                pass

    _maint_controller = MaintenanceController(
        _maint_paths, own_build=_build_info.build,
        im_wartungsmodus_gestartet=args.maintenance, registration=_registration)
    _MAINT_POLL_SEC = int(config.get("maintenance.poll_interval_sec", 3))
    _maint_poller = MaintenancePoller(
        _maint_controller, _MAINT_POLL_SEC, _maint_aktionen,
        logger=logger, on_touch=_touch_praesenz)
    _maint_poller.start()
    logger.info("Wartungsmodus-Poller gestartet (Intervall: %ds).", _MAINT_POLL_SEC)

    # ------------------------------------------------------------------
    # Schritt 10: Sauberes Herunterfahren
    # ------------------------------------------------------------------
    try:
        server.serve_forever_logged()
    finally:
        logger.info("Fahre Server herunter …")
        # Wartungsmodus: Poller stoppen und eigene Steuerdateien entfernen.
        try:
            _maint_poller.stop()
        except Exception:
            pass
        try:
            if _registration is not None:
                _registration.entfernen(_maint_paths)
            if _beacon is not None:
                _beacon.entfernen(_maint_paths)
            _ack_entfernen()
        except Exception as _exc:
            logger.warning("Wartungs-Cleanup fehlgeschlagen: %s", _exc)
        try:
            # Nach einem Resume ist die aktive Verbindung _rt.bundle, nicht das
            # urspruengliche bundle — daher _rt.bundle schliessen.
            _rt.bundle.close()
            logger.info("Datenbankverbindungen geschlossen.")
        except Exception as exc:
            logger.warning("Fehler beim Schließen der DB-Verbindungen: %s", exc)
        try:
            hosts_manager.cleanup()
        except Exception as exc:
            logger.warning("Fehler beim HostsManager-Cleanup: %s", exc)
            # Auch auf stderr ausgeben — der Ermittler muss den hosts-Eintrag
            # manuell entfernen, wenn das automatische Cleanup fehlschlägt.
            print(
                f"\n[WARNUNG] hosts-Eintrag konnte nicht automatisch entfernt werden:\n"
                f"  {exc}\n"
                f"Bitte den Eintrag manuell aus der hosts-Datei löschen:\n"
                f"  C:\\Windows\\System32\\drivers\\etc\\hosts\n"
                f"  (Zeilen mit dem Kommentar '# forensic-tool' entfernen)\n",
                file=sys.stderr,
            )
        logger.info("=== Forensischer Webserver beendet. ===")


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
