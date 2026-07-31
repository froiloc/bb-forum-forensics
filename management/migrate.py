# =============================================================================
# management/migrate.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Produktiver Einstiegspunkt zum Anwenden ausstehender coordinator.db-Migrationen.
#   Öffnet eine dedizierte coordinator.db-Verbindung (Autocommit, WAL), baut das
#   Audit-Log an, ermittelt die coordinator-Migrationen und lässt den
#   MigrationRunner laufen. Danach Ausgabe der angewandten Versionen und des
#   verify_chain()-Ergebnisses.
#
# Aufruf:
#   python -m management.migrate [--coordinator-db PATH] [--config ./config.yaml]
#                                [--deployed-by NAME]
#
# WARTUNGSVORBEHALT — STUFE A (Build 612):
#   Das Werkzeug baut Tabellen der coordinator.db UM (Rebuild) und legt KEIN
#   Backup an. Ein Abbruch mitten im Lauf hinterlaesst nichts, was sich
#   zurueckspielen liesse. Es prueft deshalb vor dem scharfen Lauf, ob die
#   Datei ruhig ist, und faehrt ohne aktives Wartungsfenster nur nach Eingabe
#   eines vollstaendigen Wortes fort (maintenance/wartungsvorbehalt.py).
#   Einstufung: Vermerk_Wartungsvorbehalt_Analyse_K1_K8_v1_0.md, von mc
#   bestaetigt am 2026-07-31.
#
# Nicht-fatal: klare Fehlermeldungen, definierte Exit-Codes.
#   0 = ok · 1 = Fehler · 3 = Wartungsvorbehalt, es wurde NICHTS geschrieben.
#
# Beleg: Bauplan B7 v0.3 §3.7, mc 2026-07-01.
# Version: v0.8.612 · Build: 612 · 2026-07-31
# =============================================================================

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path

from management.audit.audit_log import AuditLog
from management.migrations import coordinator as coordinator_pkg
from management.migrations.runner import MigrationRunner, discover
from db.journal_policy import apply_journal_mode  # NEU Build 408
from maintenance.wartungsvorbehalt import (            # NEU Build 612
    datenwurzel, wartungsvorbehalt,
)


def _resolve_db_path(args) -> str:
    if args.coordinator_db:
        return args.coordinator_db
    # Fallback: aus config.yaml (paths.coordinator_db).
    try:
        from core.config_loader import ConfigLoader
        cfg = ConfigLoader(config_path=args.config)
        path = cfg.get("paths.coordinator_db")
        if path:
            return str(path)
    except Exception as exc:  # pragma: no cover - Konfig-Randfall
        print("[migrate] Konnte config.yaml nicht lesen: %s" % exc, file=sys.stderr)
    raise SystemExit(
        "[migrate] Kein coordinator.db-Pfad: --coordinator-db angeben oder "
        "paths.coordinator_db in config.yaml setzen."
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Wendet ausstehende coordinator.db-Migrationen an."
    )
    parser.add_argument("--coordinator-db", help="Pfad zur coordinator.db")
    parser.add_argument("--config", default="./config.yaml",
                        help="Pfad zur config.yaml (Fallback für den DB-Pfad)")
    parser.add_argument("--deployed-by", default=None,
                        help="Name des Deployers (sonst OS-Benutzer)")
    args = parser.parse_args(argv)

    db_path = _resolve_db_path(args)
    if not Path(db_path).exists():
        print("[migrate] coordinator.db nicht gefunden: %s" % db_path, file=sys.stderr)
        return 1

    deployed_by = args.deployed_by or getpass.getuser()

    # --- WARTUNGSVORBEHALT (Stufe A, Build 612) --------------------------
    # Dieses Werkzeug baut Tabellen der coordinator.db um (Rebuild, nicht nur
    # ALTER) und legt KEIN Backup an. Bricht es mitten im Lauf ab, gibt es
    # nichts zurueckzuspielen. Deshalb wird vorher geprueft, ob die Datei
    # ruhig ist - und ohne Wartungsfenster nur nach ausdruecklicher Eingabe
    # weitergemacht. Einstufung: Vermerk_Wartungsvorbehalt_Analyse_K1_K8_v1_0,
    # von mc bestaetigt am 2026-07-31. Rueckgabewert 3 = nichts geschrieben.
    befund = wartungsvorbehalt(
        datenwurzel(db_path), [db_path], werkzeug="migrate",
        was_geschieht="wendet ausstehende Migrationen auf die coordinator.db "
                      "an; dabei werden Tabellen umgebaut. Es wird KEIN "
                      "Backup angelegt.")
    print(befund.text)
    if not befund.erlaubt:
        return befund.rueckgabewert

    con = sqlite3.connect(db_path)
    try:
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        # Build 408: siehe db/journal_policy.py (WAL, sonst Rueckfall).
        apply_journal_mode(con, db_path)

        audit = AuditLog(con)
        migrations = discover(coordinator_pkg)
        runner = MigrationRunner(
            con, migrations, audit=audit, deployed_by=deployed_by
        )
        applied = runner.run()

        if applied:
            print("[migrate] Angewandte Migrationen: %s" % applied)
        else:
            print("[migrate] Keine ausstehenden Migrationen (bereits aktuell).")

        # Nur prüfen, wenn die Kette schon existiert (audit_log vorhanden).
        try:
            result = audit.verify_chain()
            print("[migrate] Audit-Kette: %s" % result.detail)
            if not result.ok:
                print("[migrate] WARNUNG: Kette gebrochen bei seq=%s"
                      % result.first_bad_seq, file=sys.stderr)
                return 1
        except sqlite3.OperationalError:
            # audit_log existiert (noch) nicht — sollte nach M001 nicht vorkommen.
            pass

        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
