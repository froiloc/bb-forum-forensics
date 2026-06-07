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
#   python main.py --mode cli --user-id 12345       # Modus 'cli'
#   python main.py --mode support --user-id 12345   # Modus 'support'
#   python main.py --mode cli --username verdaechtiger
#   python main.py --debug                          # Debug-Logging aktivieren
#   python main.py --config /pfad/zu/config.yaml    # Abweichender Config-Pfad
#
# Forensische Relevanz:
#   Dieser Einstiegspunkt ist das einzige Skript, das direkt ausgeführt wird.
#   Alle anderen Module werden als Bibliotheken importiert. Die Startsequenz
#   stellt sicher, dass vor dem ersten HTTP-Request alle Integritätsprüfungen
#   abgeschlossen sind.
#
# Abhängigkeiten: argparse, sys — Stdlib + alle core/db/server-Module
# Version: v0.1.0 · Build: 018 · 2026-04-23
# =============================================================================

from __future__ import annotations

import argparse
import atexit
import sys
from pathlib import Path
import subprocess

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
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
            "'cli' = user-id oder username direkt angeben, "
            "'support' = wie cli, aber Schreiben in TEMP-DB."
        ),
    )
    parser.add_argument(
        "--user-id",
        metavar="INT",
        type=int,
        default=None,
        dest="user_id",
        help="User-ID des Beschuldigten (für Modus 'cli'/'support').",
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
        "user_id":  args.user_id,
        "username": args.username,
    }


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
        "Kontext: mode='%s', user_id=%d, username='%s'",
        context.mode, context.user_id, context.username,
    )
    logger.info("forensic_db : '%s'", context.forensic_db)
    logger.info("evidence_db : '%s'", context.evidence_db)
    logger.info("default_db  : '%s'", context.default_db)
    logger.info("coordinator : '%s'", context.coordinator_db)

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
    port = int(config.get("server.port", 80))

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
        "Ermittlung: user_id=%d ('%s'), Modus='%s'",
        context.user_id, context.username, context.mode,
    )
    if args.web_debug:
        logger.warning(
            "⚠  --web-debug aktiv: FORENSIC_DEBUG=true wird an alle "
            "Browser-Clients gesendet. Nur für Entwicklung verwenden!"
        )

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
    # Schritt 10: Sauberes Herunterfahren
    # ------------------------------------------------------------------
    try:
        server.serve_forever_logged()
    finally:
        logger.info("Fahre Server herunter …")
        try:
            bundle.close()
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
