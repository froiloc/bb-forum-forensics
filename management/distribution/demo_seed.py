# =============================================================================
# management/distribution/demo_seed.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: LKAe-Distribution (AP-2G)
# =============================================================================
# Zweck (Idee 27, Teil 1 — Demo-Daten):
#   Baut eine FRISCHE, REIN SYNTHETISCHE coordinator.db fuer das LKAe-Demo-Paket.
#
#   WICHTIG — NICHT PROD: Diese Datenbank enthaelt AUSSCHLIESSLICH erfundene
#   Demo-Daten (Namen/Kennungen/Faelle sind Platzhalter, kein realer Fallinhalt).
#   Damit ist die Unbedenklichkeit (Fallregel 3) trivial erfuellt — es verlaesst
#   nichts Reales das Haus.
#
#   Die DB wird ueber den ECHTEN Migration-Runner (M001..M0nn) und die ECHTEN
#   auditierten Repos befuellt. Dadurch traegt die Demo-DB eine GUELTIGE
#   hash-verkettete Audit-Kette (die Integritaets-Sicht ist im Demo gruen) — der
#   Demo zeigt das System so, wie es wirklich arbeitet, nur mit Fake-Inhalt.
#
#   Bootstrap-Muster wie in der Testsuite: 'person' + altes 'scrape_jobs' anlegen,
#   dann die Migrationen laufen lassen (M005 benennt nicht um, da 'person' schon
#   existiert — No-op), dann ueber die Repos auditiert seeden.
#
# Version: v0.7.466 · Build: 466 · 2026-07-20
# =============================================================================

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

import management.migrations.coordinator as coordinator_migrations
from management.audit.audit_log import AuditLog
from management.cases.cases_repo import CasesRepo
from management.external.ad_directory import ADDirectory
from management.external.case_release_repo import CaseReleaseRepo
from management.external.external_matters_repo import ExternalMattersRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.migrations.runner import MigrationRunner, discover
from management.onboarding.onboarding_repo import OnboardingRepo
from management.ops.promotion_repo import PromotionRepo
from management.rbac.rbac_repo import RbacRepo

logger = logging.getLogger(__name__)

#: Marker: diese Datenbank ist ein DEMO-Bestand (nicht PROD).
DEMO_MARKER = "AIW-DEMO — synthetische Daten, NICHT PROD"

_PERSON_DDL = """
CREATE TABLE person (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    system_username TEXT    NOT NULL UNIQUE,
    display_name    TEXT    NOT NULL,
    is_investigator INTEGER NOT NULL DEFAULT 1,
    is_supervisor   INTEGER NOT NULL DEFAULT 0,
    is_support      INTEGER NOT NULL DEFAULT 0,
    created_at      INTEGER NOT NULL
)
"""

_OLD_SCRAPE_JOBS_DDL = """
CREATE TABLE scrape_jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,
    username      TEXT    NOT NULL,
    priority      INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    status        TEXT    NOT NULL DEFAULT 'pending'
                  CHECK(status IN ('pending','running','done','failed')),
    manifest_path TEXT, output_path TEXT, worker_id TEXT,
    created_at    INTEGER NOT NULL, started_at INTEGER, finished_at INTEGER,
    error_message TEXT, assigned_to INTEGER, note TEXT,
    FOREIGN KEY(assigned_to) REFERENCES person(id)
)
"""

#: Demo-Personen (fiktiv). id 1 = Leitung, 2..3 = Ermittler, 4 = Gegenleser.
_DEMO_PERSONS = (
    (1, "demo_chef", "Demo-Chefermittlerin", 1, 1, 0),
    (2, "demo_inv1", "Demo-Ermittler Alpha", 1, 0, 0),
    (3, "demo_inv2", "Demo-Ermittlerin Beta", 1, 0, 0),
    (4, "demo_lector", "Demo-Gegenleser", 1, 0, 0),
)

#: Faehigkeiten, die die Leitung (supervisor) im Demo bekommt (Scope 'alle'),
#: damit das Cockpit vollstaendig befuellt gezeigt werden kann.
_SUPERVISOR_CAPS = (
    "dashboard.view", "ops.view", "ops.promote", "workload.view", "policy.view",
    "assignment.edit", "stats.export_sta", "external.view", "external.edit",
    "results.view", "results.edit", "release.view", "release.grant",
    "onboarding.view", "onboarding.edit", "mentoring.view", "capacity.edit",
    "support_history.view", "mycases.view", "myhistory.view",
)


def seed(db_path: str) -> Dict[str, Any]:
    """
    Erzeugt eine frische, synthetische coordinator.db unter 'db_path'.
    -> Zusammenfassung (Zeilenzahlen) fuer das Manifest/Log.
    """
    p = Path(db_path)
    if p.exists():
        raise FileExistsError(
            "Demo-DB existiert bereits: %s (Ziel muss frisch sein)." % db_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(p))
    con.isolation_level = None
    con.row_factory = sqlite3.Row
    # Ein DELETE-Journal (kein WAL) haelt das Demo-Paket bei EINER Datei
    # (keine -wal/-shm-Seitendateien) — projektweit ohnehin die Policy.
    con.execute("PRAGMA journal_mode=delete")

    try:
        _bootstrap(con)
        MigrationRunner(con, discover(coordinator_migrations),
                        audit=AuditLog(con), deployed_by="demo-seed").run()
        summary = _seed_data(con)
        con.execute("PRAGMA journal_mode=delete")  # WAL sicher kollabieren
    finally:
        con.close()

    logger.info("Demo-DB erzeugt: %s (%s)", db_path, summary)
    return summary


def _bootstrap(con: sqlite3.Connection) -> None:
    now = int(time.time())
    con.execute(_PERSON_DDL)
    for pid, un, dn, inv, sup, supp in _DEMO_PERSONS:
        con.execute(
            "INSERT INTO person (id, system_username, display_name, "
            "is_investigator, is_supervisor, is_support, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)", (pid, un, dn, inv, sup, supp, now))
    con.execute(_OLD_SCRAPE_JOBS_DDL)


def _seed_data(con: sqlite3.Connection) -> Dict[str, Any]:
    writer = CoordinatorWriter(con, AuditLog(con))

    # --- RBAC: Rollen zuweisen + Faehigkeiten granten (auditiert) ------------
    rbac = RbacRepo(con, writer)
    rbac.assign_role(1, "supervisor", actor_id=1)
    rbac.assign_role(2, "investigator", actor_id=1)
    rbac.assign_role(3, "investigator", actor_id=1)
    rbac.assign_role(4, "lector", actor_id=1)
    for cap in _SUPERVISOR_CAPS:
        rbac.grant("supervisor", cap, scope="alle", actor_id=1)

    # --- Faelle (fiktiv) -----------------------------------------------------
    cases = CasesRepo(con, writer)
    demo_cases = [
        (1001, "demo_boarder01", 2, "in_progress", 2, None),
        (1002, "demo_boarder02", 3, "in_progress", 1, "Demo-Notiz: Sichtung laeuft."),
        (1003, "demo_boarder03", 2, "open", 3, None),
        (1004, "demo_boarder04", None, "open", 4, None),
        (1005, "demo_boarder05", 3, "approved", 2, None),
        (1006, "demo_boarder06", None, "open", 5, None),
    ]
    for uid, un, assignee, status, prio, note in demo_cases:
        cases.create_case(uid, un, actor_id=1)
        if assignee is not None:
            cases.assign(uid, assignee, actor_id=1)
        if prio != 3:
            cases.set_priority(uid, prio, actor_id=1)
        if status != "open":
            cases.set_status(uid, status, actor_id=1)
        if note:
            cases.set_note(uid, note, actor_id=1)

    # --- AP-2G-Artefakte (je ein Beispiel, damit die Sichten befuellt sind) --
    # Fremdforum-Promotion (uid ohne cases-FK zulaessig).
    PromotionRepo(con, writer).record_decision(
        user_id=2001, target_status="gesichtet", herkunft="Demo-Nachbarforum",
        actor_id=1)
    # Externe Fallfreigabe (Demo-Empfaenger ueber eine Demo-AD-Allowlist).
    ad = ADDirectory(recipients={"demo_lka1": "KHK Demo, LKA-Musterland"},
                     group="DEMO-EK-Extern")
    CaseReleaseRepo(con, writer, ad=ad).grant(
        user_id=1005, recipient_kennung="demo_lka1", umfang="bericht",
        unbedenklichkeit_grundlage="Demo-Freigabe (synthetisch, kein Realinhalt)",
        actor_id=1)
    # Onboarding-/Offboarding-Schritte.
    onb = OnboardingRepo(con, writer)
    onb.set_step(person_id=2, kind="onboarding", step_code="person_angelegt",
                 status="erledigt", actor_id=1)
    onb.set_step(person_id=2, kind="onboarding", step_code="ad_gruppe_geprueft",
                 status="erledigt", actor_id=1)
    onb.set_step(person_id=3, kind="offboarding", step_code="ad_gruppe_entfernt",
                 status="nicht_zutreffend",
                 note="Demo: noch aktiv, entfaellt.", actor_id=1)
    # Externer Vorgang (Wiedervorlage) fuer die Kalender-/Externsicht.
    ExternalMattersRepo(con, writer).create(
        user_id=1001, kind="bestandsdaten", betreff="Demo-Bestandsdatenauskunft",
        angefordert_am="2026-07-01", wiedervorlage_am="2026-08-01",
        adressat="Demo-Provider", actor_id=1)

    # --- Zusammenfassung -----------------------------------------------------
    def _count(sql: str) -> int:
        return int(con.execute(sql).fetchone()[0])

    return {
        "demo": True,
        "persons": _count("SELECT COUNT(*) FROM person"),
        "cases": _count("SELECT COUNT(*) FROM cases"),
        "promotions": _count("SELECT COUNT(*) FROM forum_promotion"),
        "releases": _count("SELECT COUNT(*) FROM case_release"),
        "onboarding_items": _count("SELECT COUNT(*) FROM onboarding_item"),
        "external_matters": _count("SELECT COUNT(*) FROM external_matters"),
        "audit_rows": _count("SELECT COUNT(*) FROM audit_log"),
    }
