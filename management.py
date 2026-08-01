#!/usr/bin/env python3
# =============================================================================
# management.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Entry-Point des EIGENSTAENDIGEN Management-Servers (Welle 0, Schritt 3;
#   Beleg: Bauplan B7 v1.1 §11.2). Analog main.py, aber getrennt vom Forensik-
#   Webserver: read-only-first, bindet AUSSCHLIESSLICH localhost, an die
#   aufgeloeste OS-Identitaet gebunden.
#
#   Ablauf:
#     1. Argumente parsen
#     2. coordinator.db-Pfad aufloesen
#     3. Start-Check: RBAC-Katalog vollstaendig in der DB (verify_catalog_present)
#     4. OS-Identitaet -> person aufloesen (IdentityResolver; --as-user Override)
#     5. localhost-Port bestimmen (fest oder --auto-port), Server binden
#     6. optional Browser oeffnen, dann serve_forever
#
#   Aufrufe:
#     python management.py --coordinator-db ./data/coordinator.db
#     python management.py --auto-port --open-browser
#     python management.py --as-user h001            # Identitaet explizit (Dev)
#
#   READ-ONLY: keine Schreibpfade, kein CoordinatorWriter, keine Migration.
#
# Version: v0.7.346 · Build: 346 · 2026-07-10
# =============================================================================

import argparse
import os
import socket
import sys
import webbrowser
from pathlib import Path

from management.server.identity import IdentityError, IdentityResolver
from management.server.management_app import ManagementApp
from management.server.management_handler import ManagementHTTPServer
from management.help import cli_epilog  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8090


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="AIW Management-Server (read-only, localhost).",
        epilog=cli_epilog.epilog("management"),
        formatter_class=cli_epilog.HilfeFormat)
    p.add_argument("--coordinator-db", default=None,
                   help="Pfad zur coordinator.db (sonst aus config.yaml).")
    p.add_argument("--config", default="./config.yaml")
    p.add_argument("--host", default=DEFAULT_HOST,
                   help="Lausch-Adresse (nur localhost sinnvoll). "
                        "Default 127.0.0.1.")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--auto-port", action="store_true", dest="auto_port",
                   help="naechsten freien Port ab --port suchen.")
    p.add_argument("--open-browser", action="store_true", dest="open_browser")
    p.add_argument("--as-user", default=None, dest="as_user",
                   help="OS-Identitaet explizit setzen (system_username; Dev).")
    p.add_argument("--maintenance", action="store_true", default=False,
                   help="Startet als Wartungs-Test-Server: verhaelt sich normal, "
                        "meldet sich unter einer UUID an und beendet sich bei "
                        "Fensterende oder auf Kill. Start NUR bei aktivem "
                        "Wartungsfenster erlaubt (Schutz vor Missbrauch).")
    return p.parse_args(argv)


def _resolve_db_path(args) -> str:
    if args.coordinator_db:
        return args.coordinator_db
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover
        print("[management] config.yaml nicht lesbar: %s" % exc,
              file=sys.stderr)
    raise SystemExit(
        "[management] Kein coordinator.db-Pfad: --coordinator-db oder "
        "paths.coordinator_db in config.yaml.")


def _is_localhost(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost")


def _resolve_port(host: str, start_port: int, auto: bool,
                  max_tries: int = 100) -> int:
    if not auto:
        return start_port
    for offset in range(max_tries):
        candidate = start_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, candidate))
                return candidate
            except OSError:
                continue
    raise SystemExit(
        "[management] Kein freier Port im Bereich %d-%d auf %s."
        % (start_port, start_port + max_tries - 1, host))


def main(argv=None) -> int:
    args = _parse_args(argv)

    if not _is_localhost(args.host):
        print("[management] WARNUNG: --host %s ist nicht localhost. Der "
              "Management-Server ist ausschliesslich fuer den lokalen Betrieb "
              "vorgesehen." % args.host, file=sys.stderr)

    db_path = _resolve_db_path(args)
    if not Path(db_path).exists():
        print("[management] coordinator.db nicht gefunden: %s" % db_path,
              file=sys.stderr)
        return 1

    # Wartungsmodus-Pfade (Build 437): dateibasiert unter dem geteilten
    # Datenverzeichnis (Parent der coordinator.db), damit es ueber alle VMs wirkt.
    from maintenance import MaintenancePaths, WindowFlag
    _maint_paths = MaintenancePaths(Path(db_path).parent)
    try:
        _maint_paths.verzeichnisse_anlegen()
    except Exception as _exc:
        print("[management] WARNUNG: Wartungsverzeichnisse nicht anlegbar: %s"
              % _exc, file=sys.stderr)

    # --maintenance darf NUR bei aktivem Fenster starten (Schutz vor Missbrauch).
    if args.maintenance:
        if WindowFlag.aktives_fenster(_maint_paths) is None:
            print("[management] --maintenance: Start verweigert — kein aktives "
                  "Wartungsfenster. Ein Start im Wartungsmodus ist nur bei "
                  "aktivem Fenster erlaubt.", file=sys.stderr)
            return 1
        print("[management] LAEUFT IM WARTUNGSMODUS (Testbetrieb). Beendet sich "
              "bei Fensterende oder auf Kill.")

    app = ManagementApp(db_path)

    # Schritt 3: Start-Check (RBAC-Katalog vollstaendig?).
    from management.rbac.rbac_resolver import RbacCatalogError
    try:
        app.startup_selfcheck()
    except RbacCatalogError as exc:
        print("[management] Start-Check fehlgeschlagen: %s" % exc,
              file=sys.stderr)
        return 1

    # Schritt 3b: MIGRATIONSSTAND (Build 376). Der Server migriert BEWUSST NICHT
    # selbst — das Anwenden bleibt eine kontrollierte, im Audit-Log belegte
    # Handlung. Ist die coordinator.db nicht auf dem Stand der ausgelieferten
    # Migrationen, wird das hier DEUTLICH und mit dem exakten Befehl gemeldet
    # (Grundregel 1: kein stiller Betrieb mit unvollstaendigem Schema).
    from management.server.migration_status import MigrationStatusCheck
    try:
        mstatus = app.migration_status()
        for line in MigrationStatusCheck.warning_lines(mstatus):
            print(line, file=sys.stderr)
        if mstatus.ok:
            print("[management] Migrationsstand aktuell (%d Migrationen)."
                  % len(mstatus.applied))
    except Exception as exc:  # pragma: no cover — Pruefung darf nie den Start
        print("[management] WARNUNG: Migrationsstand nicht pruefbar: %s" % exc,
              file=sys.stderr)  # verhindern, aber sie schweigt auch nicht.

    # Schritt 4: Identitaet aufloesen.
    resolver = IdentityResolver(db_path)
    try:
        person = resolver.resolve(args.as_user)
    except IdentityError as exc:
        print("[management] %s" % exc, file=sys.stderr)
        return 1
    print("[management] Angemeldet als %s (%s), person id=%d."
          % (person["display_name"], person["system_username"], person["id"]))

    # Schritt 5: Port + Server.
    port = _resolve_port(args.host, args.port, args.auto_port)
    try:
        server = ManagementHTTPServer(args.host, port, app, person["id"])
    except OSError as exc:
        print("[management] Binden auf %s:%d fehlgeschlagen: %s"
              % (args.host, port, exc), file=sys.stderr)
        return 1

    url = "http://%s:%d/" % (args.host, port)
    # Ab Build 372 ist der Server NICHT mehr rein lesend: die auditierten
    # Schreibrouten (Zuweisung/Prioritaet/Status) sind ueber POST erreichbar —
    # abgesichert per Schreib-Token, Content-Type und localhost-Bindung. Die
    # Meldung benennt das ausdruecklich, damit niemand (auch kein Pruefer) von
    # einem rein lesenden Dienst ausgeht.
    print("[management] Server laeuft: %s" % url)
    print("[management] Lesezugriffe read-only; Schreibzugriffe nur ueber die "
          "auditierten POST-Routen (Token-geschuetzt, jede Aenderung wird im "
          "audit_log belegt).")

    # Schritt 6: optional Browser oeffnen.
    if args.open_browser:
        try:
            webbrowser.open(url)
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------
    # Schritt 7: Wartungsmodus-Integration (Build 437)
    # Per-Request-Modell: KEIN persistentes Bundle. Quiesce = neue DB-Zugriffe
    # blocken (503) + laufende austrudeln + ACK. Resume = nur Gate freigeben
    # (nichts wieder aufzubauen). Controller/Gate/Poller wie beim Webserver.
    # ------------------------------------------------------------------
    from maintenance import (Aktion, AckFile, MaintenanceController,
                             MaintenanceGate, MaintenancePoller, PresenceBeacon,
                             ServerRegistration)
    from core.build_info import BuildInfo

    _own_build = BuildInfo(project_root=Path(__file__).parent).build
    _gate = MaintenanceGate()
    server.maintenance_gate = _gate

    _mh_host = socket.gethostname()
    _mh_pid = os.getpid()
    _mh_role = "management"

    _registration = None
    _beacon = None
    if args.maintenance:
        _fnow = WindowFlag.aktives_fenster(_maint_paths)
        _registration = ServerRegistration.neu(
            role=_mh_role, host=_mh_host, pid=_mh_pid, build=_own_build,
            window_id=(_fnow.window_id if _fnow else ""), port=port,
            config=args.config)
        try:
            _registration.schreiben(_maint_paths)
            print("[management] Wartungs-Anmeldung: uuid=%s" % _registration.uuid)
        except Exception as _exc:
            print("[management] WARNUNG: Anmeldung nicht schreibbar: %s" % _exc,
                  file=sys.stderr)
    else:
        _beacon = PresenceBeacon(role=_mh_role, host=_mh_host, pid=_mh_pid,
                                 build=_own_build, port=port)
        try:
            _beacon.schreiben(_maint_paths)
        except Exception as _exc:
            print("[management] WARNUNG: Praesenz-Beacon nicht schreibbar: %s"
                  % _exc, file=sys.stderr)

    _MGMT_DRAIN_TIMEOUT_S = 30.0

    def _ack_schreiben():
        _f = WindowFlag.laden(_maint_paths)
        _wid = _f.window_id if _f else ""
        try:
            AckFile(role=_mh_role, host=_mh_host, pid=_mh_pid,
                    window_id=_wid).schreiben(_maint_paths)
        except Exception as _exc:
            print("[management] WARNUNG: ACK nicht schreibbar: %s" % _exc,
                  file=sys.stderr)

    def _ack_entfernen():
        try:
            AckFile(role=_mh_role, host=_mh_host, pid=_mh_pid,
                    window_id="").entfernen(_maint_paths)
        except Exception:
            pass

    def _quiesce(beenden):
        print("[management] Wartungsmodus: Quiesce (beenden=%s)." % beenden)
        if not _gate.block_and_drain(timeout=_MGMT_DRAIN_TIMEOUT_S):
            print("[management] WARNUNG: Drain-Timeout — es liefen noch Requests "
                  "(z.B. offene SSE-Verbindung).", file=sys.stderr)
        # Kein persistentes Bundle: per-Request-Verbindungen sind mit dem Drain
        # bereits geschlossen. Nur ACK schreiben.
        _ack_schreiben()
        print("[management] Wartungsmodus: Quiesce abgeschlossen (ACK geschrieben).")
        if beenden:
            server.shutdown()

    def _resume():
        _ack_entfernen()
        _gate.unblock()   # Per-Request-Modell: nur freigeben, nichts neu aufbauen
        print("[management] Wartungsmodus: Resume — Betrieb wieder aufgenommen.")

    def _beenden_versionswaechter():
        print("[management] Wartungsmodus: eigener Build %d unterschreitet "
              "min_build — beende (keine alte Version auf neue Daten)." % _own_build)
        server.shutdown()

    def _terminate(grund):
        print("[management] Wartungsmodus: %s — beende." % grund)
        server.shutdown()

    _aktionen = {
        Aktion.QUIESCE_PAUSE: lambda: _quiesce(False),
        Aktion.QUIESCE_BEENDEN: lambda: _quiesce(True),
        Aktion.RESUME: _resume,
        Aktion.BEENDEN_VERSIONSWAECHTER: _beenden_versionswaechter,
        Aktion.SELBSTBEENDIGUNG_FENSTERENDE:
            lambda: _terminate("Fensterende (--maintenance)"),
        Aktion.KILL: lambda: _terminate("Kill angefordert (--maintenance)"),
    }

    def _touch():
        if _beacon is not None:
            try:
                _beacon.touch(_maint_paths)
            except Exception:
                pass

    _controller = MaintenanceController(
        _maint_paths, own_build=_own_build,
        im_wartungsmodus_gestartet=args.maintenance, registration=_registration)
    _poller = MaintenancePoller(_controller, 3, _aktionen, on_touch=_touch)
    _poller.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[management] Beende.")
    finally:
        try:
            _poller.stop()
        except Exception:
            pass
        try:
            if _registration is not None:
                _registration.entfernen(_maint_paths)
            if _beacon is not None:
                _beacon.entfernen(_maint_paths)
            _ack_entfernen()
        except Exception:
            pass
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
