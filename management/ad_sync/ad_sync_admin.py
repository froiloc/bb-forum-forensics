# =============================================================================
# management/ad_sync/ad_sync_admin.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: AD-Abgleich (Build 501)
# =============================================================================
# Zweck:
#   CLI des AD-Abgleichs (BETRIEBSWEG; die Cockpit-Sicht folgt in Build 502 —
#   Muster Onboarding 464/465: gemeinsamer Kern, zwei Bedienwege).
#
#   Aufruf:  python -m management.ad_sync.ad_sync_admin <befehl> [...]
#
#     preview [--json]        Vorschau (rein lesend): Neu / Umbenennung /
#                             Entfernungs-Kandidaten / Reaktivierungs-Kandidaten.
#     apply   --actor KENNUNG Vollzug: Neuaufnahmen + Namensaenderungen
#                             automatisch (auditiert); danach je Kandidat die
#                             INTERAKTIVE Einzel-Frage:
#                               Deaktivierung  -> Eingabe des Wortes "Entfernen"
#                               Reaktivierung  -> Eingabe des Wortes "Reaktivieren"
#                             Jede andere Eingabe ist ein PROTOKOLLIERTER
#                             Abbruch (Beleg, keine Datenaenderung).
#
#   --actor ist beim Vollzug Pflicht und MUSS ein aktiver Supervisor sein
#   (person.is_supervisor=1): die Entfernen-Bestaetigung ist laut Vorgabe
#   Sache des Supervisors (mc 2026-07-24). Entfernte Benutzer werden NIE
#   geloescht — nur inaktiv geschaltet (person.is_active=0, M020).
#
#   EXIT-CODES: 0 = ok · 1 = Aufruf-/Fach-/AD-Fehler.
#
# Testbarkeit:
#   main(argv, provider=..., input_fn=...) — Mitgliederquelle und Eingabe
#   sind injizierbar (Muster F4); Tests fahren den vollen CLI-Pfad ohne
#   Live-AD und ohne Terminal.
#
# Version: v0.8.501 · Build: 501 · 2026-07-24
# =============================================================================

import argparse
import json
import logging
import sqlite3
import sys
from typing import Any, Callable, List, Optional

from management.audit.audit_log import AuditLog
from management.gateway.coordinator_writer import CoordinatorWriter
from management.ad_sync.sync_executor import (
    AdSyncError,
    CONFIRM_DEACTIVATE,
    CONFIRM_REACTIVATE,
    SyncExecutor,
)
from management.ad_sync.sync_plan import AdSyncPlanError, SyncPlan
from management.external.ldap_group_reader import LdapError, LdapGroupReader
from management.help import cli_epilog  # noqa: E402
# Build 643: die Vorrangregel Argument > config.yaml > Vorgabewert
# steht seit diesem Build an EINER Stelle (Ticket 15429c75).
from core import werkzeug_konfig  # noqa: E402

logger = logging.getLogger(__name__)


def _resolve_db_path(args) -> str:
    """
    coordinator.db-Pfad: Argument --db > paths.coordinator_db > Abbruch.

    BUILD 643 - DIE AUFLOESUNG IST UMGEZOGEN, das Verhalten NICHT.
    Bis Build 642 stand hier eine eigene Abschrift derselben zwoelf Zeilen;
    fuenfundzwanzig Werkzeuge trugen sie, und sie waren nicht identisch (die
    Begruendung steht im Kopf von core/werkzeug_konfig.py). Sie steht jetzt an
    EINER Stelle.

    UNVERAENDERT bleiben: die Reihenfolge, das Fehlen eines Vorgabewerts
    (ein erratener Pfad waere schlimmer als ein Abbruch), die Meldung ueber
    eine unlesbare config.yaml auf stderr und der Abbruch mit dem Praefix
    '[ad_sync_admin]'. Die Abbruchmeldung nennt jetzt BEIDE Wege statt nur einen.
    """
    return werkzeug_konfig.db_pfad(
        "ad_sync_admin", args, arg_attribut="db", arg_name="--db",
        config_schluessel="paths.coordinator_db", name="db")


def _con(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    return con


def _actor_supervisor_id(con: sqlite3.Connection, kennung: str) -> int:
    """
    Loest --actor auf und ERZWINGT einen aktiven Supervisor (Kopfkommentar).
    is_active defensiv: fehlt die Spalte (vor M020), scheitert ohnehin der
    Vollzug der Kandidaten mit Klartext (PersonRepo._require_m020_row).
    """
    row = con.execute(
        "SELECT * FROM person WHERE system_username = ?", (kennung,)
    ).fetchone()
    if row is None:
        raise AdSyncError(
            "Unbekannte Kennung '%s' (person.system_username)." % kennung)
    d = dict(row)
    if not d.get("is_active", 1):
        raise AdSyncError(
            "Kennung '%s' ist deaktiviert und darf den Abgleich nicht "
            "vollziehen." % kennung)
    if not d.get("is_supervisor"):
        raise AdSyncError(
            "Kennung '%s' ist kein Supervisor — die Entfernen-/"
            "Reaktivieren-Bestaetigung ist der Aufsicht vorbehalten "
            "(mc 2026-07-24)." % kennung)
    return int(d["id"])


def _print_plan(plan: SyncPlan) -> None:
    c = plan.counts()
    print("AD-Abgleich — Vorschau")
    print("-" * 78)
    print("Neuaufnahmen: %d · Namensaenderungen: %d · "
          "Entfernungs-Kandidaten: %d · Reaktivierungs-Kandidaten: %d"
          % (c["create"], c["rename"],
             c["deactivate_candidates"], c["reactivate_candidates"]))
    print("Unveraendert aktiv: %d · unveraendert inaktiv: %d"
          % (c["unchanged"], c["unchanged_inactive"]))
    if plan.create:
        print("\n[NEU] (werden als 'investigator' aufgenommen)")
        for m in plan.create:
            print("  + %-20s %s" % (m["sam"], m["display_name"]))
    if plan.rename:
        print("\n[NAMENSAENDERUNG]")
        for r in plan.rename:
            print("  ~ %-20s %r -> %r"
                  % (r["system_username"], r["display_name_alt"],
                     r["display_name_neu"]))
    if plan.deactivate_candidates:
        print("\n[ENTFERNUNGS-KANDIDATEN] (Vollzug NUR nach Bestaetigung "
              "'%s' — nie Loeschen, nur inaktiv)" % CONFIRM_DEACTIVATE)
        for d in plan.deactivate_candidates:
            print("  - %-20s %s" % (d["system_username"], d["display_name"]))
    if plan.reactivate_candidates:
        print("\n[REAKTIVIERUNGS-KANDIDATEN] (Vollzug NUR nach Bestaetigung "
              "'%s')" % CONFIRM_REACTIVATE)
        for r in plan.reactivate_candidates:
            print("  ^ %-20s %s (AD: %s)"
                  % (r["system_username"], r["display_name"],
                     r["display_name_ad"]))
    print("-" * 78)


def _interactive_candidates(executor: SyncExecutor, plan: SyncPlan,
                            actor_id: int,
                            input_fn: Callable[[str], str]) -> None:
    """
    Einzel-Fragen je Kandidat. Jede Entscheidung erzeugt einen Beleg:
    Bestaetigung -> PERSON_DEACTIVATED / PERSON_REACTIVATED,
    alles andere -> PERSON_DEACTIVATION_ABORTED bzw. Hinweis (Reaktivierung
    hat keinen eigenen Abbruch-Beleg-Typ — der Kandidat bleibt einfach
    inaktiv und erscheint beim naechsten Lauf erneut; der Lauf selbst ist
    ueber AD_SYNC_RUN belegt).
    """
    for d in plan.deactivate_candidates:
        prompt = ("Ermittler %s (%s) ist nicht mehr im AD. Zum "
                  "Deaktivieren '%s' eingeben (alles andere bricht "
                  "protokolliert ab): "
                  % (d["system_username"], d["display_name"],
                     CONFIRM_DEACTIVATE))
        answer = input_fn(prompt)
        if answer == CONFIRM_DEACTIVATE:
            seq = executor.deactivate(
                d["system_username"], confirmation=answer, actor_id=actor_id)
            print("  -> deaktiviert (Beleg #%d). Nicht geloescht — nur "
                  "inaktiv geschaltet." % seq)
        else:
            seq = executor.abort_deactivation(
                d["system_username"], actor_id=actor_id,
                note="Eingabe war %r statt %r" % (answer, CONFIRM_DEACTIVATE))
            print("  -> NICHT deaktiviert; Abbruch protokolliert "
                  "(Beleg #%d)." % seq)

    for r in plan.reactivate_candidates:
        prompt = ("Ermittler %s (%s) ist wieder im AD (Anzeigename dort: "
                  "%s). Zum Reaktivieren '%s' eingeben (alles andere "
                  "ueberspringt): "
                  % (r["system_username"], r["display_name"],
                     r["display_name_ad"], CONFIRM_REACTIVATE))
        answer = input_fn(prompt)
        if answer == CONFIRM_REACTIVATE:
            seq = executor.reactivate(
                r["system_username"], confirmation=answer,
                actor_id=actor_id, display_name_ad=r["display_name_ad"])
            print("  -> reaktiviert (Beleg #%d)." % seq)
        else:
            print("  -> NICHT reaktiviert (Kandidat erscheint beim "
                  "naechsten Lauf erneut).")


def main(argv: Optional[List[str]] = None, *,
         provider: Optional[Any] = None,
         input_fn: Callable[[str], str] = input) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    ap = argparse.ArgumentParser(
        prog="ad_sync_admin",
        description="AD-Abgleich der Ermittlerstammdaten (coordinator.db).",
        epilog=cli_epilog.epilog("ad_sync_admin"),
        formatter_class=cli_epilog.HilfeFormat)
    ap.add_argument("--db", default=None, help="Pfad zur coordinator.db")
    ap.add_argument("--config", default="./config.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("preview", help="Vorschau (rein lesend)")
    p.add_argument("--json", action="store_true",
                   help="Plan als JSON ausgeben")

    p = sub.add_parser("apply", help="Vollzug (auditiert, interaktiv)")
    p.add_argument("--actor", required=True,
                   help="Kennung des vollziehenden Supervisors")

    args = ap.parse_args(argv)

    db = _resolve_db_path(args)
    con = _con(db)
    try:
        if provider is None:
            # Betrieb: Live-AD aus config.yaml (wirft LdapError bei leerer
            # Konfiguration — DEFAULT-DENY, Bauplan §2).
            provider = LdapGroupReader.from_config(config_path=args.config)
        executor = SyncExecutor(
            con, CoordinatorWriter(con, AuditLog(con)), provider)

        if args.cmd == "preview":
            plan = executor.preview()
            if args.json:
                print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2))
            else:
                _print_plan(plan)
            return 0

        if args.cmd == "apply":
            actor_id = _actor_supervisor_id(con, args.actor)
            plan = executor.preview()
            _print_plan(plan)
            summary = executor.apply_automatic(plan, actor_id=actor_id)
            print("Vollzogen: %d Neuaufnahmen, %d Namensaenderungen "
                  "(Lauf-Beleg #%d)."
                  % (len(summary["created"]), len(summary["renamed"]),
                     summary["run_seq"]))
            _interactive_candidates(executor, plan, actor_id, input_fn)
            return 0

        ap.error("Unbekannter Befehl.")
        return 1

    except (AdSyncError, AdSyncPlanError, LdapError) as exc:
        print("FEHLER: %s" % exc, file=sys.stderr)
        return 1
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
