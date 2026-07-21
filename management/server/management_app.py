# =============================================================================
# management/server/management_app.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Management-Interface
# =============================================================================
# Zweck:
#   Der TESTBARE KERN des Management-Servers: reine Request-Aufloesung ohne
#   Socket. dispatch(person_id, path, query) liefert eine Response (Status,
#   Content-Type, Body). Der HTTP-Handler (management_handler.py) ist eine duenne
#   Huelle darum; der SSE-Stream nutzt die Hilfen hier. So sind alle Endpunkte
#   per pytest pruefbar (Beleg: Bauplan B7 v1.1 §11.2, §10.6 "Testbarkeit:
#   Request-Handler + JSON per pytest").
#
# Nebenlaeufigkeit (Build-325-Lehre, §11.2): KEINE geteilte Connection. Jeder
#   dispatch-/Tick-Aufruf oeffnet eine kurzlebige READ-ONLY-Verbindung
#   (file:...?mode=ro) und schliesst sie wieder. Damit kein Win32-Mutex-Deadlock
#   (ThreadingHTTPServer + geteilte SQLite-Connection) und kein Schreibpfad.
#
# Policy-Durchsetzung: jeder /api-Endpunkt prueft die aufgeloeste Policy
#   (RbacResolver, Schnitt c). Fehlende Faehigkeit -> 403 (kein stiller
#   Teilinhalt). Scope ('alle'/'eigene') steuert den Umfang (z.B. Falluebersicht
#   'eigene' -> nur eigene Zuweisungen).
#
# READ-ONLY im ersten Build: ausschliesslich GET-Semantik, kein CoordinatorWriter,
#   keine Migration.
#
# Build 347 (Cockpit-Shell): '/' liefert jetzt die statische cockpit.html (der
#   frueher inline gebackene Platzhalter _SHELL_HTML entfaellt; der Anzeigename
#   wird im Browser per fetch('/api/whoami') gesetzt). '/static/<f>' liefert
#   echte Assets ueber StaticAssets (cockpit.* + management-lokale Vendor-Libs)
#   statt des 404-Platzhalters.
#
# Build 350 (Lastverteilung Backend): '/api/workload' liefert die Lastverteilung
#   je Ermittler (WorkloadRepo, read-only, scope-aware); ECharts wird management-
#   lokal vendort und ueber StaticAssets ausgeliefert. Die ECharts-Frontend-Sicht
#   folgt in Build 351 (browser-verifizierbar, console-first).
#
# Build 359 (Kapazitaets-Aggregat): '/api/capacity' ohne person_id liefert je
#   Ermittler eine Kapazitaets-Zeile (inkl. Anzeigename) fuer die Cockpit-Sicht
#   (Build 360). Mit person_id unveraendert (Einzelperson, Build 358).
#
# Build 372 (Zuweisung - ERSTER SCHREIBPFAD): eng begrenzter POST-Pfad
#   (dispatch_write) fuer /api/case/assign, /api/case/priority, /api/case/status.
#   Schreiben NUR ueber CasesRepo+CoordinatorWriter (Audit-Beleg erzwungen).
#   Haertung: X-AIW-Token (Serverlauf-Token via /api/whoami), Content-Type,
#   Origin. Lesepfade bleiben mode=ro. Dazu GET /api/assignable.
#
# Build 383 (Fall-Autodetektion): GET /api/cases/detect gleicht die auf der
#   Platte liegenden forensic_<uid>.db mit der Fallakte ab (ok/neu/vermisst/
#   unlesbar); POST /api/cases/import nimmt neu erkannte Faelle AUDITIERT auf.
#
# Build 380 (Rueckgabe zur Nachbesserung): POST /api/report/return setzt einen
#   EINGEREICHTEN Bericht (submitted) zurueck auf 'draft' — nur Lektor/Chef-
#   Ermittlerin, auditiert. Abgenommene/versandte Berichte NIE.
#
# Build 377 (Berichts-Versiegelung): POST /api/report/approve (reports.approve,
#   Scope 'alle') versiegelt einen Bericht: Beleg (coordinator) -> zentrales
#   Siegel mit Inhaltshash (approved_reports.db) -> Durchsetzung in evidence
#   (status approved/final). GET /api/report/verify prueft das Siegel nach
#   (Hash neu bilden und vergleichen -> Abweichung = Manipulation).
#
# Build 376 (Betriebssicherheit): migration_status() — der Server prueft beim
#   Start, ob coordinator.db auf dem Stand der ausgelieferten Migrationen ist,
#   und WARNT deutlich (er migriert bewusst NICHT selbst).
#
# Build 375 (Berichts-Abnahme, Frontend + Rechte-Korrektur): /api/reports akzeptiert
#   nun reports.review ODER reports.approve ('approve' impliziert 'review') —
#   vorher sah der Supervisor den Reiter, bekam aber 403.
#
# Build 374 (Berichts-Abnahme, Lesepfad): GET /api/reports liest die Berichte
#   ALLER Faelle aus den evidence_<uid>.db (read-only), beschleunigt durch den
#   WAL-sicheren Fingerabdruck-Cache (m009). ManagementApp kennt nun das
#   evidence_db_dir (injizierbar; sonst aus config.yaml).
#
#   385 = WIEDERVORLAGE EXTERNER VORGAENGE (M010) + gemeinsame KALENDER-
#         Leseschicht. GET /api/external (Vorgaenge mit Ampel, scope-gefiltert),
#         GET /api/calendar (externe Vorgaenge + Abwesenheiten + Feiertage in
#         EINER Sicht), POST /api/external/create|defer|answer|close (auditiert).
#         Rechte: external.view / external.edit, BEIDE scope-faehig ('eigene' =
#         nur zugewiesene Faelle) — der Ermittler pflegt seinen Fall selbst.
#   387 = ERMITTLUNGSERGEBNIS-BEWERTUNG (M011). GET /api/results/catalog
#         (Kriterien + Skalen — DATEN, kein Code), GET /api/results?subject_id=
#         (aktueller Stand + VOLLE Historie + provisorische Kennzahl),
#         GET /api/results/stats (fallUEBERGREIFEND, verlangt Scope 'alle'),
#         POST /api/results/assess (APPEND-ONLY). Rechte: results.view /
#         results.edit, beide scope-faehig.
#   391 = HOTFIX Query-Vertrag: dispatch() bekommt die Query als
#         Dict[str, List[str]] (parse_qs). Die Handler aus 385/387 lasen sie
#         als Skalare -> /api/calendar antwortete durchgaengig mit 400,
#         /api/external war latent kaputt. Alle Lesestellen laufen jetzt ueber
#         _q1(). Die Tests pruefen die ECHTE Listenform.
#   393 = ABDECKUNG / BLINDE FLECKEN. NEU GET /api/results/coverage (eine
#         Zeile JE FALL aus 'cases' — auch fuer NIE bewertete Faelle; /stats
#         sieht die gar nicht). /api/results/stats weist jetzt zusaetzlich
#         'faelle_gesamt' und 'faelle_unbewertet' aus.
# Version: v0.7.469 · Build: 469 · 2026-07-20
# =============================================================================

import hmac
import json
import logging
import secrets
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from management.audit.audit_log import AuditLog
from management.cases.cases_repo import CasesRepo
from management.gateway.coordinator_writer import CoordinatorWriter
from management.dashboard.dashboard_repo import (
    DashboardRepo,
    DashboardSchemaError,
)
from management.rbac.rbac_resolver import (
    PersonPolicy,
    RbacCatalogError,
    RbacResolver,
    verify_catalog_present,
)
from management.server.static_assets import StaticAssets
from management.capacity.capacity_calculator import CapacityCalculator
from management.rbac.policy_repo import PolicyRepo
from management.personal.myhistory_repo import MyHistoryRepo
from management.support_overview.support_overview_repo import (
    SupportOverviewRepo,
    SupportOverviewSchemaError,
)
from management.support_sessions.support_sessions_repo import SupportSessionsRepo
from management.stats.stats_repo import StatsRepo
from management.stats.forecast import Forecaster, forecast_to_dict
from management.stats.gantt import GanttModel, gantt_to_dict
from management.stats.annotation_stats_repo import AnnotationStatsRepo
from management.cases.case_search_repo import CaseSearchRepo
from management.reports.reports_repo import ReportsRepo
from management.server.migration_status import MigrationStatusCheck
from management.reports.approval_service import ApprovalService, ApprovalError
from management.cases.case_detector import CaseDetector
from management.cases.case_importer import CaseImporter
from management.external.external_matters_repo import (
    ExternalMattersError,
    ExternalMattersRepo,
)
from management.external.matter_status import (
    OPEN_STATUSES,
    MatterStatus,
    MatterStatusError,
)
from management.external import matter_kinds
from management.calendar.calendar_repo import CalendarError, CalendarRepo
from management.calendar import stichtag as stichtag_mod
from management.results.assessment_catalog_repo import (
    AssessmentCatalogRepo,
    CatalogError,
)
from management.results.results_repo import ResultsError, ResultsRepo
from management.results.priority_scorer import PriorityScorer
from management.results.coverage_repo import CoverageRepo
from db.coordinator_db import DEFAULT_SUPPORT_STALE_SEC
from management.capacity.capacity_errors import CapacityError
from management.workload.workload_repo import (
    WorkloadRepo,
    WorkloadSchemaError,
)
from management.mentoring_notes import note_colors
from management.mentoring_notes.mentoring_notes_repo import (
    MentoringNotesError,
    MentoringNotesRepo,
)
from management.ops.storage_overview import StorageOverview
from management.ops.promotion_repo import PromotionError, PromotionRepo
from management.ops.promotion_status import STORED_STATUSES
from management.external.ad_directory import ADDirectory
from management.external.case_release_repo import (
    CaseReleaseError,
    CaseReleaseRepo,
)
from management.external import release_status
from management.onboarding.onboarding_repo import (
    OnboardingError,
    OnboardingRepo,
)
from management.onboarding.checklist_status import ChecklistStatus
from management.crossref.identified_subject_repo import (
    CrossrefError,
    IdentifiedSubjectRepo,
)
from management.crossref.crossfindings_repo import CrossfindingsRepo
from management.audit.audit_explorer import AuditExplorer, AuditExplorerError
from management.audit import audit_export
from management.export.context_builder import build_export_context
from management.export.export_envelope import ExportEnvelope

#: Basisverzeichnis der statischen Cockpit-Assets (cockpit.* + Vendor).
#: Liegt neben diesem Modul (management/server/static/).
STATIC_DIR = Path(__file__).resolve().parent / "static"

#: Faehigkeits-Gates je Endpunkt (None = kein Gate, nur eigene Identitaet).
CAP_OVERVIEW = "dashboard.view"
CAP_INTEGRITY = "ops.view"
CAP_WORKLOAD = "workload.view"
CAP_CAPACITY = "capacity.edit"
CAP_POLICY = "policy.view"
CAP_MYCASES = "mycases.view"
CAP_MYHISTORY = "myhistory.view"
CAP_SUPPORT = "support_history.view"
CAP_MENTORING = "mentoring.view"
CAP_STATS = "stats.export_sta"
CAP_ASSIGNMENT = "assignment.edit"
CAP_REPORTS_REVIEW = "reports.review"
CAP_REPORTS_APPROVE = "reports.approve"
# Build 385: Wiedervorlage externer Vorgaenge. BEIDE sind scope-faehig —
# 'alle' = alle Faelle, 'eigene' = nur die zugewiesenen (mc 2026-07-12).
CAP_EXTERNAL_VIEW = "external.view"
CAP_EXTERNAL_EDIT = "external.edit"
# Build 387: Ermittlungsergebnis-Bewertung. Beide scope-faehig; 'eigene' =
# nur die zugewiesenen Faelle. Die fallUEBERGREIFENDE Statistik verlangt
# ausdruecklich Scope 'alle' (mc 2026-07-12).
CAP_RESULTS_VIEW = "results.view"
CAP_RESULTS_EDIT = "results.edit"
# Build 420/422: Authoring der Berichtsvorlagen (templates.db). Nicht
# scope-behaftet — der Katalog ist fallunabhaengig. Der Schreibpfad ist
# auditiert (TemplatesWriter, Build 421).
CAP_TEMPLATES_EDIT = "templates.edit"
# Build 401: Betreuungs-Notizen. Scope-faehig: 'alle' (Vertretung/Aufsicht sieht
# fremde Boards), sonst nur das EIGENE Board (privater Merkzettel der Leitung).
CAP_MENTORING_NOTES_VIEW = "mentoring_notes.view"
CAP_MENTORING_NOTES_EDIT = "mentoring_notes.edit"
# Build 460: Fremdforum-Promotion (AP-2G). Das LESEN der Kandidaten-/Zustands-
# sicht haengt an 'ops.view' (wie die data/-Uebersicht, Build 454); das
# ENTSCHEIDEN ist ein eigenes, auditiertes Schreibrecht. Beide NICHT scope-
# behaftet: die Uebernahme eines Kandidaten ist eine Leitungshandlung.
CAP_OPS_VIEW = "ops.view"
CAP_OPS_PROMOTE = "ops.promote"
# Build 462: Externe Fallfreigabe (AP-2G). Lesen und Erteilen/Widerrufen sind
# getrennte, nicht scope-behaftete Rechte (Leitungshandlung; Vier-Augen moeglich).
CAP_RELEASE_VIEW = "release.view"
CAP_RELEASE_GRANT = "release.grant"
# Build 464: Onboarding/Offboarding-Checkliste (AP-2G). Personal-/Leitungs-
# funktion, nicht scope-behaftet; Lesen und Pflegen getrennt.
CAP_ONBOARDING_VIEW = "onboarding.view"
CAP_ONBOARDING_EDIT = "onboarding.edit"

# Build 468 (AP-2A): Kreuzbezug/Identitaetskatalog (Konto->reale Person).
# Global, nicht scope-behaftet; Lesen und Pflegen getrennt. Seed in M018.
CAP_CROSSREF_VIEW = "crossref.view"
CAP_CROSSREF_EDIT = "crossref.edit"

logger = logging.getLogger(__name__)

# Zulaessige Werte fuer die auditierten Schreibpfade (Build 372).
_CASE_STATUSES = ("open", "in_progress", "approved", "closed")
_PRIORITY_MIN, _PRIORITY_MAX = 1, 5


def _case_overview_item(c) -> Dict[str, Any]:
    """Serialisiert eine CaseOverview in das JSON-Item (Overview + Meine Faelle)."""
    return {
        "subject_id": c.subject_id,
        "username": c.username,
        "status": c.status,
        "priority": c.priority,
        "assigned_to": c.assigned_to,
        "assigned_display_name": c.assigned_display_name,
        "ampel": c.ampel,
        "ampel_reason": c.ampel_reason,
        "has_note": c.has_note,
        "event_count": c.event_count,
        "last_activity_at": c.last_activity_at,
        "support_active": c.support_active,
        "support_count": c.support_count,
    }


@dataclass(frozen=True)
class Response:
    """HTTP-Antwort als reines Datenobjekt (Status, Content-Type, Body-Bytes)."""

    status: int
    content_type: str
    body: bytes

    @staticmethod
    def json(status: int, payload: Any) -> "Response":
        return Response(
            status=status,
            content_type="application/json; charset=utf-8",
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    @staticmethod
    def html(status: int, text: str) -> "Response":
        return Response(
            status=status,
            content_type="text/html; charset=utf-8",
            body=text.encode("utf-8"),
        )

    @staticmethod
    def csv(status: int, text: str) -> "Response":
        return Response(
            status=status,
            content_type="text/csv; charset=utf-8",
            body=text.encode("utf-8"),
        )


def format_sse_event(event_name: str, data: Dict[str, Any]) -> bytes:
    """
    Formatiert ein SSE-Ereignis nach RFC 8895: 'event: <name>\\n
    data: <json>\\n\\n'. Identisches Rahmenformat wie der Forensik-Webserver
    (forensic_api/events.py), aber eigene, unabhaengige Maschinerie (§11.2).
    """
    return (
        "event: %s\ndata: %s\n\n"
        % (event_name, json.dumps(data, ensure_ascii=False))
    ).encode("utf-8")


class ManagementApp:
    """Read-only Request-Aufloesung des Management-Servers (ohne Socket)."""

    def __init__(self, db_path: str,
                 static_dir: Optional[Path] = None,
                 evidence_dir: Optional[str] = None,
                 approved_db: Optional[str] = None,
                 forensic_dir: Optional[str] = None,
                 assets_dir: Optional[str] = None,
                 templates_db: Optional[str] = None,
                 default_db: Optional[str] = None,
                 ad_directory: Optional[ADDirectory] = None) -> None:
        self._db_path = db_path
        # Statische Auslieferung gekapselt (Grundregel 10). static_dir ist im
        # Test injizierbar; PROD nutzt STATIC_DIR neben diesem Modul.
        self._static = StaticAssets(static_dir or STATIC_DIR)
        # Verzeichnis der evidence_<uid>.db (Berichts-Abnahme, Build 374).
        # Injizierbar (Test); sonst aus config.yaml (paths.evidence_db_dir).
        self._evidence_dir = evidence_dir or self._default_evidence_dir()
        # Zentrale Siegel-DB (Build 377). Injizierbar (Test); sonst config.yaml.
        self._approved_db = approved_db or self._default_approved_db()
        # Fall-Autodetektion (Build 383): forensic_<uid>.db definiert den Fall;
        # evidence/assets sind nur Arbeitsstand.
        self._forensic_dir = forensic_dir or self._cfg_path(
            "paths.forensic_db_dir", "./data/forensic/")
        self._assets_dir = assets_dir or self._cfg_path(
            "paths.assets_db_dir", "./data/assets/")
        # Build 410 (SF-1): Pfade fuer die read-only Berichts-Vorschau.
        # templates.db (tdb) traegt die {{a:}}-Query-Definitionen; default.db
        # (ddb) dient nur dem Asset-Fallback. Beide injizierbar (Test).
        self._templates_db = templates_db or self._cfg_path(
            "paths.templates_db", "./data/templates.db")
        self._default_db = default_db or self._cfg_path(
            "paths.default_db", "./data/default.db")
        # SCHREIB-TOKEN (Build 372): pro Serverlauf zufaellig. Wird nur ueber
        # den authentifizierten GET /api/whoami ausgeliefert und muss bei JEDEM
        # Schreibzugriff im Header 'X-AIW-Token' mitgeschickt werden. Schuetzt
        # gegen Fremd-POSTs ueber Netzwerk-Bridges/Tunnel und CSRF: wer die
        # GET-Antwort nicht lesen kann, kennt das Token nicht.
        self._write_token = secrets.token_urlsafe(32)
        # AD-Schicht (F4) fuer die externe Fallfreigabe (Build 462). Injizierbar
        # (Test/Mock); sonst aus config.yaml (ad.release_recipients). Faellt die
        # Konfiguration aus, bleibt die Allowlist leer -> Default-Deny; der
        # Ausfall wird protokolliert (Grundregel 1: kein stiller Zustand).
        if ad_directory is not None:
            self._ad_directory = ad_directory
        else:
            try:
                self._ad_directory = ADDirectory.from_config()
            except Exception as exc:  # pragma: no cover - Konfig-Ausfall
                logger.warning("AD-Allowlist nicht aus config.yaml lesbar "
                               "(%s) — Default-Deny (leer).", exc)
                self._ad_directory = ADDirectory()

    @staticmethod
    def _default_evidence_dir() -> str:
        """
        evidence_db_dir aus config.yaml. Faellt die Konfiguration aus, wird der
        Default des ConfigLoaders benutzt — und der Fehler protokolliert
        (Grundregel 1: kein stilles Verschlucken).
        """
        try:
            from core.config_loader import ConfigLoader
            return str(ConfigLoader().get("paths.evidence_db_dir"))
        except Exception as exc:  # pragma: no cover - Konfig-Ausfall
            logger.warning("evidence_db_dir nicht aus config.yaml lesbar "
                           "(%s) — Standard './data/evidence/'.", exc)
            return "./data/evidence/"

    @staticmethod
    def _cfg_path(key: str, fallback: str) -> str:
        """Pfad aus config.yaml; Ausfall wird protokolliert (Grundregel 1)."""
        try:
            from core.config_loader import ConfigLoader
            return str(ConfigLoader().get(key))
        except Exception as exc:  # pragma: no cover
            logger.warning("%s nicht aus config.yaml lesbar (%s) — "
                           "Standard '%s'.", key, exc, fallback)
            return fallback

    @staticmethod
    def _default_approved_db() -> str:
        try:
            from core.config_loader import ConfigLoader
            return str(ConfigLoader().get("paths.approved_reports_db"))
        except Exception as exc:  # pragma: no cover
            logger.warning("approved_reports_db nicht aus config.yaml lesbar "
                           "(%s) — Standard './data/approved_reports.db'.", exc)
            return "./data/approved_reports.db"

    @property
    def write_token(self) -> str:
        return self._write_token

    def check_write_token(self, presented: Optional[str]) -> bool:
        """Konstantzeitlicher Token-Vergleich (kein Timing-Orakel)."""
        if not presented:
            return False
        return hmac.compare_digest(presented, self._write_token)

    # ------------------------------------------------------------- Verbindung
    def _rw_con(self) -> sqlite3.Connection:
        """
        SCHREIB-Verbindung (nur fuer die auditierten Schreibpfade, Build 372).
        Alle Lesepfade nutzen weiterhin _ro_con() (mode=ro) — der read-only-
        Charakter des Servers bleibt fuer alles ausser den expliziten
        Schreibrouten erhalten.
        """
        con = sqlite3.connect(self._db_path)
        con.isolation_level = None
        con.row_factory = sqlite3.Row
        return con

    def _ro_con(self) -> sqlite3.Connection:
        con = sqlite3.connect("file:%s?mode=ro" % self._db_path, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def _templates_ro_con(self) -> sqlite3.Connection:
        """READ-ONLY Verbindung zur templates.db (Autoren-Liste, Build 422)."""
        con = sqlite3.connect("file:%s?mode=ro" % self._templates_db, uri=True)
        con.row_factory = sqlite3.Row
        return con

    def _templates_rw_con(self) -> sqlite3.Connection:
        """
        SCHREIB-Verbindung zur templates.db — NUR fuer den auditierten
        TemplatesWriter-Pfad (Build 421/422). journal_mode=delete (kein WAL,
        Build 408/409), busy_timeout gegen kurzzeitige Sperren.
        """
        con = sqlite3.connect(self._templates_db, timeout=5.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=delete")
        con.execute("PRAGMA busy_timeout=5000")
        return con

    # ------------------------------------------------------------- Start-Check
    def startup_selfcheck(self) -> None:
        """
        Beim Serverstart aufzurufen (management.py). Erzwingt die Katalog-
        Konsistenz (RbacCatalogError bei Luecke) — kein stiller Start mit
        unvollstaendiger RBAC-Basis (Grundregel 1).
        """
        con = self._ro_con()
        try:
            verify_catalog_present(con)
        finally:
            con.close()

    def migration_status(self):
        """
        Migrationsstand der coordinator.db (Build 376). Rein lesend; der Server
        migriert NICHT selbst — er warnt nur (siehe migration_status.py).
        """
        con = self._ro_con()
        try:
            return MigrationStatusCheck(con).status()
        finally:
            con.close()

    # ------------------------------------------------------------------- Tip
    def audit_tip_seq(self) -> int:
        """Aktuelle Spitze der Audit-Kette (fuer den SSE-Tick)."""
        con = self._ro_con()
        try:
            return AuditLog(con).tip()[1]
        finally:
            con.close()

    # --------------------------------------------------------------- Policy
    def resolve_policy(self, person_id: int) -> PersonPolicy:
        con = self._ro_con()
        try:
            return RbacResolver(con).resolve(person_id)
        finally:
            con.close()

    def _person(self, con: sqlite3.Connection, person_id: int) -> Optional[Dict[str, Any]]:
        row = con.execute(
            "SELECT id, system_username, display_name FROM person WHERE id=?",
            (person_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------- Dispatch
    def dispatch(
        self, person_id: int, path: str,
        query: Optional[Dict[str, List[str]]] = None,
    ) -> Response:
        """
        Loest einen (Nicht-SSE-)GET-Request auf. person_id ist die beim
        Serverstart aufgeloeste Identitaet. Gibt eine Response zurueck.
        """
        if path == "/":
            return self._index()
        if path == "/api/whoami":
            return self._whoami(person_id)
        if path == "/api/overview":
            return self._overview(person_id)
        if path == "/api/integrity":
            return self._integrity(person_id)
        if path == "/api/workload":
            return self._workload(person_id)
        if path == "/api/capacity":
            return self._capacity(person_id, query)
        if path == "/api/policy":
            return self._policy(person_id)
        if path == "/api/mycases":
            return self._mycases(person_id)
        if path == "/api/myhistory":
            return self._myhistory(person_id, query)
        if path == "/api/support":
            return self._support(person_id)
        if path == "/api/mentoring":
            return self._mentoring(person_id)
        if path == "/api/stats":
            return self._stats(person_id, query)
        if path == "/api/forecast":
            return self._forecast(person_id)
        if path == "/api/gantt":
            return self._gantt(person_id)
        if path == "/api/annotation-stats":
            return self._annotation_stats(person_id)
        if path == "/api/search":
            return self._search(person_id, query)
        if path == "/api/assignable":
            return self._assignable(person_id)
        if path == "/api/reports":
            return self._reports(person_id, query)
        if path == "/api/report/verify":
            return self._report_verify(person_id, query)
        if path == "/api/report/render":
            return self._report_render(person_id, query)
        if path == "/api/report/annotations":
            return self._report_annotations(person_id, query)
        if path == "/api/report/comments":
            return self._report_comments(person_id, query)
        if path == "/api/templates/queries":
            return self._templates_queries(person_id)
        if path == "/api/templates/documents":
            return self._templates_documents(person_id)
        if path == "/api/templates/modules":
            return self._templates_modules(person_id)
        if path == "/api/cases/detect":
            return self._cases_detect(person_id)
        if path == "/api/promotion":
            return self._promotion(person_id)
        if path == "/api/audit":
            return self._audit(person_id, query)
        if path == "/api/audit/facets":
            return self._audit_facets(person_id)
        if path == "/api/audit/export":
            return self._audit_export(person_id, query)
        if path == "/api/releases":
            return self._releases(person_id, query)
        if path == "/api/onboarding":
            return self._onboarding(person_id, query)
        # Build 470 (AP-2A): Katalog identifizierter Personen (Konto->Person).
        if path == "/api/crossref":
            return self._crossref(person_id, query)
        # Build 474 (AP-2A(3)): Querfund-Meta-Uebersicht (rein lesend).
        if path == "/api/crossfindings":
            return self._crossfindings(person_id, query)
        if path == "/api/external":
            return self._external(person_id, query)
        if path == "/api/calendar":
            return self._calendar(person_id, query)
        if path == "/api/results/catalog":
            return self._results_catalog(person_id)
        if path == "/api/results/stats":
            return self._results_stats(person_id)
        if path == "/api/results/coverage":
            return self._results_coverage(person_id, query)
        if path == "/api/results":
            return self._results(person_id, query)
        # Build 401: Betreuungs-Notizen ("Post-its") der Ermittler-Betreuung.
        # Reiner LESE-Endpunkt (Block 1); die Schreibpfade folgen in Block 2.
        if path == "/api/mentoring/notes":
            return self._mentoring_notes(person_id, query)
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        return Response.json(404, {"error": "not_found", "path": path})

    # --------------------------------------------------------------- Helfer
    @staticmethod
    def _q1(query, key, default=None):
        """
        Ersten Wert eines Query-Parameters holen.

        DER VERTRAG (Build 391, Hotfix): dispatch() bekommt die Query in der
        parse_qs-Form, also Dict[str, List[str]] — die Werte sind LISTEN.
        Die Handler aus 385/387 lasen sie als SKALARE und schickten damit
        ['2026-07-01'] in eine Datumspruefung: /api/calendar antwortete
        durchgaengig mit 400, /api/external war latent kaputt (es fiel nur
        nicht auf, solange die Vorgangsliste leer war).

        Warum das durch die Tests kam: die Tests riefen dispatch() mit
        SKALAREN auf — also mit einer Form, die der echte Server NIE liefert.
        Zwoelf gruene Tests, und der Endpunkt war trotzdem tot: die
        "gruen aber tot"-Falle, nur an der Schnittstelle statt in der Logik.
        Deshalb pruefen die Tests jetzt die ECHTE Listenform (QV01).

        Ein Skalar wird hier trotzdem angenommen — aber NICHT, um den Vertrag
        aufzuweichen, sondern damit ein Aufrufer, der ihn missversteht, ein
        richtiges Ergebnis bekommt statt eines stillen 400.
        """
        if not query:
            return default
        v = query.get(key)
        if v is None:
            return default
        if isinstance(v, (list, tuple)):
            return v[0] if v else default
        return v

    def _forbidden(self, capability: str) -> Response:
        return Response.json(
            403, {"error": "forbidden", "capability": capability})

    def _index(self) -> Response:
        """
        '/' liefert die statische Cockpit-Shell (cockpit.html). Der Anzeigename
        wird NICHT mehr server-seitig eingebacken, sondern im Browser per
        fetch('/api/whoami') gesetzt (policy-getriebene Nav, Build 347).
        """
        status, ctype, body = self._static.serve("cockpit.html")
        return Response(status=status, content_type=ctype, body=body)

    def _serve_static(self, rel: str) -> Response:
        """Statisches Asset unter /static/<rel> ausliefern (StaticAssets)."""
        status, ctype, body = self._static.serve(rel)
        return Response(status=status, content_type=ctype, body=body)

    def _whoami(self, person_id: int) -> Response:
        con = self._ro_con()
        try:
            p = self._person(con, person_id)
            policy = RbacResolver(con).resolve(person_id)
        finally:
            con.close()
        if p is None:
            return Response.json(404, {"error": "unknown_person",
                                       "person_id": person_id})
        return Response.json(200, {
            "person_id": person_id,
            "system_username": p["system_username"],
            "display_name": p["display_name"],
            "roles": sorted(policy.roles),
            "capabilities": {k: policy.capabilities[k]
                             for k in sorted(policy.capabilities)},
            # Schreib-Token (Build 372): nur ueber diesen authentifizierten
            # GET erreichbar; das Cockpit sendet ihn bei POSTs zurueck.
            "write_token": self._write_token,
        })

    def _overview(self, person_id: int) -> Response:
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_OVERVIEW):
            return self._forbidden(CAP_OVERVIEW)
        scope = policy.scope(CAP_OVERVIEW)  # 'alle' | 'eigene' | None

        con = self._ro_con()
        try:
            try:
                cases = DashboardRepo(con).list_case_overview()
            except DashboardSchemaError as exc:
                return Response.json(
                    503, {"error": "schema", "detail": str(exc)})
        finally:
            con.close()

        # Scope 'eigene' (oder ungesetzt) -> nur eigene Zuweisungen. 'alle' ->
        # alle Faelle. Zweckbindung/Kapselung: default restriktiv.
        if scope != "alle":
            cases = [c for c in cases if c.assigned_to == person_id]

        items = [_case_overview_item(c) for c in cases]
        return Response.json(200, {"scope": scope, "count": len(items),
                                   "cases": items})

    def _integrity(self, person_id: int) -> Response:
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_INTEGRITY):
            return self._forbidden(CAP_INTEGRITY)
        con = self._ro_con()
        try:
            audit = AuditLog(con)
            res = audit.verify_chain()
            tip_seq = audit.tip()[1]
        finally:
            con.close()
        return Response.json(200, {
            "ok": bool(res.ok),
            "first_bad_seq": res.first_bad_seq,
            "detail": res.detail,
            "tip_seq": tip_seq,
        })

    def _workload(self, person_id: int) -> Response:
        """
        Lastverteilung je Ermittler (read-only). Nutzt WorkloadRepo; liefert je
        Ermittler eine Last-Zeile plus eine Rueckstau-Zeile (unzugewiesen).
        Scope-aware analog _overview: 'alle' -> volle Verteilungssicht;
        'eigene' (oder ungesetzt) -> nur die EIGENE Last-Zeile (Rueckstau und
        fremde Ermittler bleiben gekapselt; Zweckbindung, default restriktiv).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_WORKLOAD):
            return self._forbidden(CAP_WORKLOAD)
        scope = policy.scope(CAP_WORKLOAD)  # 'alle' | 'eigene' | None

        con = self._ro_con()
        try:
            try:
                loads = WorkloadRepo(con).list_workload()
            except WorkloadSchemaError as exc:
                return Response.json(
                    503, {"error": "schema", "detail": str(exc)})
        finally:
            con.close()

        if scope != "alle":
            loads = [l for l in loads if l.investigator_id == person_id]

        items = [asdict(l) for l in loads]
        return Response.json(200, {"scope": scope, "count": len(items),
                                   "loads": items})

    def _capacity(self, person_id: int,
                  query: Optional[Dict[str, List[str]]]) -> Response:
        """
        Kapazitaet — read-only. Query: start, end (ISO-Daten, Pflicht) und
        OPTIONAL person_id.
          - MIT person_id  -> Einzelperson (flaches CapacityResult, wie 358).
          - OHNE person_id -> AGGREGAT: je Ermittler (person.is_investigator=1)
            eine Kapazitaets-Zeile inkl. Anzeigename (fuer die Cockpit-Sicht 360).
        Scope 'alle' -> beliebige Person / alle Ermittler; 'eigene' -> nur die
        eigene Kapazitaet.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_CAPACITY):
            return self._forbidden(CAP_CAPACITY)
        scope = policy.scope(CAP_CAPACITY)

        q = query or {}

        def _one(key: str) -> Optional[str]:
            vals = q.get(key)
            return vals[0] if vals else None

        start, end = _one("start"), _one("end")
        if not (start and end):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "Query-Parameter start, end erforderlich."})
        target = _one("person_id")

        con = self._ro_con()
        try:
            calc = CapacityCalculator(con)

            # --- Einzelperson (unveraendert seit Build 358) ---
            if target is not None:
                try:
                    target_id = int(target)
                except ValueError:
                    return Response.json(
                        400, {"error": "bad_request",
                              "detail": "person_id ungueltig."})
                if scope != "alle" and target_id != person_id:
                    return Response.json(403, {
                        "error": "forbidden", "capability": CAP_CAPACITY,
                        "detail": "Scope 'eigene': nur die eigene Kapazitaet."})
                try:
                    res = calc.compute(target_id, start, end)
                except CapacityError as exc:
                    return Response.json(
                        400, {"error": "capacity", "detail": str(exc)})
                return Response.json(200, asdict(res))

            # --- Aggregat: alle Ermittler (scope-aware) ---
            persons = con.execute(
                "SELECT id, system_username, display_name FROM person "
                "WHERE is_investigator=1 ORDER BY id ASC").fetchall()
            if scope != "alle":
                persons = [p for p in persons if p[0] == person_id]

            caps = []
            try:
                for pid, uname, disp in persons:
                    row = asdict(calc.compute(pid, start, end))
                    row["system_username"] = uname
                    row["display_name"] = disp
                    caps.append(row)
            except CapacityError as exc:
                return Response.json(
                    400, {"error": "capacity", "detail": str(exc)})
        finally:
            con.close()

        return Response.json(200, {"scope": scope, "count": len(caps),
                                   "start": start, "end": end,
                                   "capacities": caps})

    def _policy(self, person_id: int) -> Response:
        """
        RBAC-Policy-Snapshot (read-only): Rollen, Faehigkeiten, aktive Grants
        und aktive Personen-Zuweisungen. Scope 'alle' -> volle Matrix; 'eigene'
        (oder ungesetzt) -> auf den Aufrufer gefiltert ("meine Rechte").
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_POLICY):
            return self._forbidden(CAP_POLICY)
        scope = policy.scope(CAP_POLICY)

        con = self._ro_con()
        try:
            snap = PolicyRepo(con).snapshot(
                person_id=None if scope == "alle" else person_id)
        finally:
            con.close()
        return Response.json(200, snap)

    def _mycases(self, person_id: int) -> Response:
        """
        Meine Auftraege (read-only): die dem Aufrufer aktuell zugewiesenen
        Faelle (immer nur die eigenen — personenbezogen, Cap ist das Tor).
        Gleiche Item-Form wie /api/overview.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_MYCASES):
            return self._forbidden(CAP_MYCASES)

        con = self._ro_con()
        try:
            try:
                cases = DashboardRepo(con).list_case_overview()
            except DashboardSchemaError as exc:
                return Response.json(
                    503, {"error": "schema", "detail": str(exc)})
        finally:
            con.close()

        mine = [_case_overview_item(c) for c in cases
                if c.assigned_to == person_id]
        return Response.json(200, {"count": len(mine), "cases": mine})

    def _myhistory(self, person_id: int,
                   query: Optional[Dict[str, List[str]]]) -> Response:
        """
        Meine Historie (read-only, kombiniert): eigene Aktionen + Historie der
        eigenen Faelle aus dem audit_log. Optional ?limit=N. Immer nur die
        eigenen Daten (Cap ist das Tor).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_MYHISTORY):
            return self._forbidden(CAP_MYHISTORY)

        limit = 200
        if query and query.get("limit"):
            try:
                limit = int(query["limit"][0])
            except ValueError:
                return Response.json(
                    400, {"error": "bad_request", "detail": "limit ungueltig."})

        con = self._ro_con()
        try:
            result = MyHistoryRepo(con).my_history(person_id, limit=limit)
        finally:
            con.close()
        return Response.json(200, result)

    def _support(self, person_id: int) -> Response:
        """
        Support-Historie (read-only): belegbasiert rekonstruierte Support-
        Sitzungen. Jede Sitzung wird markiert mit mine_as_supporter
        (supporter_id == ich) und on_my_case (Fall mir zugewiesen). Scope
        'alle' -> alle Sitzungen; 'eigene' -> nur solche, die mindestens eine
        der beiden Markierungen tragen (eigene Sitzungen ODER an eigenen Faellen).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_SUPPORT):
            return self._forbidden(CAP_SUPPORT)
        scope = policy.scope(CAP_SUPPORT)

        con = self._ro_con()
        try:
            try:
                records = SupportOverviewRepo(con).list_support_sessions()
            except SupportOverviewSchemaError as exc:
                return Response.json(
                    503, {"error": "schema", "detail": str(exc)})
            my_case_ids = {r[0] for r in con.execute(
                "SELECT subject_id FROM cases WHERE assigned_to = ?",
                (person_id,)).fetchall()}
        finally:
            con.close()

        sessions = []
        for rec in records:
            mine = (rec.supporter_id == person_id)
            oncase = (rec.subject_id in my_case_ids)
            if scope != "alle" and not (mine or oncase):
                continue
            d = asdict(rec)
            d["mine_as_supporter"] = mine
            d["on_my_case"] = oncase
            sessions.append(d)
        return Response.json(200, {"scope": scope, "count": len(sessions),
                                   "sessions": sessions})

    def _mentoring(self, person_id: int) -> Response:
        """
        Ermittler-Betreuung (read-only, LIVE): die aktuell LAUFENDEN Support-
        Sitzungen (support_sessions, ended_at IS NULL) mit Live/Stale-Bewertung
        (Heartbeat-Alter vs. stale_sec). Scope 'alle' -> alle laufenden;
        'eigene' -> nur die eigenen (supporter_id == ich). Betreuungsbeduerftige
        (stale) zuerst, dann laengstlaufende.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_MENTORING):
            return self._forbidden(CAP_MENTORING)
        scope = policy.scope(CAP_MENTORING)
        stale_sec = DEFAULT_SUPPORT_STALE_SEC
        now = int(time.time())

        con = self._ro_con()
        try:
            rows = SupportSessionsRepo(con, None).list_running()
        finally:
            con.close()

        sessions = []
        for r in rows:
            if scope != "alle" and r.get("supporter_id") != person_id:
                continue
            hb = r.get("last_heartbeat") or 0
            r["heartbeat_age_sec"] = now - hb
            r["started_ago_sec"] = now - (r.get("started_at") or now)
            r["live"] = (now - hb) <= stale_sec
            sessions.append(r)
        # Stale (live=False) zuerst; dann aeltester Start zuerst.
        sessions.sort(key=lambda s: (s["live"], s["started_at"]))
        return Response.json(200, {"scope": scope, "stale_sec": stale_sec,
                                   "count": len(sessions),
                                   "sessions": sessions})

    def _stats(self, person_id: int,
               query: Optional[Dict[str, List[str]]]) -> Response:
        """
        Statistiken (StA/Fuehrung, read-only): Kennzahl-Matrizen + Durchsatz.
        Query 'format' = 'json' (Vorgabe) oder 'csv' (Download-Langformat).
        Scope 'alle' -> alle Faelle; 'eigene' -> nur eigene zugewiesene Faelle.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_STATS):
            return self._forbidden(CAP_STATS)
        scope = policy.scope(CAP_STATS)

        q = query or {}
        fmt = (q.get("format") or ["json"])[0]

        con = self._ro_con()
        try:
            stats = StatsRepo(con).compute(
                person_id=None if scope == "alle" else person_id)
        finally:
            con.close()

        if fmt == "csv":
            return Response.csv(200, StatsRepo.to_csv(stats))
        return Response.json(200, stats)

    def _forecast(self, person_id: int) -> Response:
        """
        Backlog-Abbau-Prognose (3 Szenarien, read-only; Build 446/448). Wie
        /api/results/stats eine FALLUEBERGREIFENDE Planungssicht -> verlangt
        Scope 'alle' (sonst 403); gebunden an CAP_STATS (stats.export_sta).
        Antwort = forecast_to_dict (Backlog, beobachtete Rate, Szenarien,
        OFFENGELEGTE Annahmen, Kapazitaets-Kontext).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_STATS) or policy.scope(CAP_STATS) != "alle":
            return self._forbidden(CAP_STATS)
        con = self._ro_con()
        try:
            result = Forecaster(con).compute(now_ts=int(time.time()))
        finally:
            con.close()
        return Response.json(200, forecast_to_dict(result))

    def _gantt(self, person_id: int) -> Response:
        """
        Gantt-Read-Model (Fall-Balken je Ermittler, read-only; Build 447/448).
        Falluebergreifende Planungssicht -> Scope 'alle' (sonst 403), CAP_STATS.
        Antwort = gantt_to_dict (Spuren mit Balken, Zeitraum, belegte Anker).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_STATS) or policy.scope(CAP_STATS) != "alle":
            return self._forbidden(CAP_STATS)
        con = self._ro_con()
        try:
            result = GanttModel(con).build(now_ts=int(time.time()))
        finally:
            con.close()
        return Response.json(200, gantt_to_dict(result))

    def _annotation_stats(self, person_id: int) -> Response:
        """
        Annotations-Tortenstatistik (read-only; Build 449/450). Aggregiert die
        Fall-Annotationen nach Kategorie/Tag. SCOPE-BEWUSST: 'alle' -> alle
        Faelle, 'eigene' -> nur eigene zugewiesene. Recht CAP_STATS. Die
        evidence_<uid>.db werden ausschliesslich read-only gelesen.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_STATS):
            return self._forbidden(CAP_STATS)
        scope = policy.scope(CAP_STATS)
        con = self._ro_con()
        try:
            result = AnnotationStatsRepo(con, self._evidence_dir).compute(
                scope=scope,
                person_id=(None if scope == "alle" else person_id))
        finally:
            con.close()
        return Response.json(200, result)

    def _search(self, person_id: int,
                query: Optional[Dict[str, List[str]]]) -> Response:
        """
        Fall-/Nutzer-Suche fuer die Kommandopalette (read-only; Build 458).
        SCOPE-BEWUSST ueber CAP_OVERVIEW (dashboard.view): 'alle' -> alle
        Faelle, 'eigene' -> nur eigene zugewiesene. Query 'q' (Pflicht) + 'limit'.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_OVERVIEW):
            return self._forbidden(CAP_OVERVIEW)
        scope = policy.scope(CAP_OVERVIEW)

        q = query or {}
        term = (q.get("q") or [""])[0]
        try:
            limit = int((q.get("limit") or ["20"])[0])
        except (TypeError, ValueError):
            limit = 20

        con = self._ro_con()
        try:
            result = CaseSearchRepo(con).search(
                q=term, scope=scope,
                person_id=(None if scope == "alle" else person_id),
                limit=limit)
        finally:
            con.close()
        return Response.json(200, result)

    # =====================================================================
    # ZUWEISUNG — Lesepfad (GET) und AUDITIERTER SCHREIBPFAD (POST), Build 372.
    #
    # Der Server bleibt fuer ALLES ausser den unten gelisteten Schreibrouten
    # read-only. Schreiben erfolgt AUSSCHLIESSLICH ueber CasesRepo +
    # CoordinatorWriter — damit entsteht zwingend ein audit_log-Beleg je
    # Aenderung (Bauplan §2.6: "der einzige zulaessige Schreibpfad"). Kein
    # Direkt-SQL. Fehler werden explizit gemeldet (Grundregel 1), nie still
    # verschluckt.
    # =====================================================================

    def _assignable(self, person_id: int) -> Response:
        """
        Entscheidungsgrundlage fuer die Zuweisungs-Sicht (read-only): alle
        Faelle (Overview-Form) + waehlbare Ermittler mit ihrer aktuellen Last
        (Anzahl zugewiesener Faelle). Erfordert assignment.edit (Scope 'alle').
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_ASSIGNMENT):
            return self._forbidden(CAP_ASSIGNMENT)
        if policy.scope(CAP_ASSIGNMENT) != "alle":
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_ASSIGNMENT,
                "detail": "Zuweisen erfordert Scope 'alle'."})

        con = self._ro_con()
        try:
            try:
                cases = DashboardRepo(con).list_case_overview()
            except DashboardSchemaError as exc:
                return Response.json(
                    503, {"error": "schema", "detail": str(exc)})
            rows = con.execute(
                "SELECT id, system_username, display_name FROM person "
                "WHERE is_investigator=1 ORDER BY id ASC").fetchall()
            load = {r[0]: r[1] for r in con.execute(
                "SELECT assigned_to, COUNT(*) FROM cases "
                "WHERE assigned_to IS NOT NULL GROUP BY assigned_to")}
        finally:
            con.close()

        investigators = [{
            "person_id": r[0], "system_username": r[1], "display_name": r[2],
            "case_count": load.get(r[0], 0),
        } for r in rows]
        return Response.json(200, {
            "cases": [_case_overview_item(c) for c in cases],
            "investigators": investigators,
            "statuses": list(_CASE_STATUSES),
            "priority_min": _PRIORITY_MIN, "priority_max": _PRIORITY_MAX,
        })

    def _reports(self, person_id: int,
                 query: Optional[Dict[str, List[str]]]) -> Response:
        """
        Berichts-Abnahme, Lesepfad (Build 374): Berichte ALLER Faelle aus den
        evidence_<uid>.db — cache-gestuetzt (Fingerabdruck ueber alle DB-Dateien;
        WAL-sicher). Query 'force=1' erzwingt den Vollscan (Cache ignorieren).
        Scope 'alle' -> alle Berichte; 'eigene' -> nur Berichte zu eigenen
        (zugewiesenen) Faellen. Die evidence-DBs werden NUR read-only geoeffnet.

        RECHTE (Korrektur Build 375): Es genuegt EINE der beiden Faehigkeiten —
        reports.review ODER reports.approve. Begruendung: Wer einen Bericht
        FREIGEBEN darf, muss ihn zwingend auch LESEN duerfen; 'approve'
        impliziert 'review'. Vorher gatete der Endpunkt allein auf
        reports.review, waehrend die Cockpit-Nav auf reports.approve gatete —
        der Supervisor (reports.approve) sah den Reiter, bekam aber 403.
        Der wirksame Scope ist der weitere der beiden ('alle' schlaegt 'eigene').
        """
        policy = self.resolve_policy(person_id)
        can_review = policy.can(CAP_REPORTS_REVIEW)
        can_approve = policy.can(CAP_REPORTS_APPROVE)
        if not (can_review or can_approve):
            return self._forbidden(CAP_REPORTS_REVIEW)

        scopes = []
        if can_review:
            scopes.append(policy.scope(CAP_REPORTS_REVIEW))
        if can_approve:
            scopes.append(policy.scope(CAP_REPORTS_APPROVE))
        scope = "alle" if "alle" in scopes else (
            scopes[0] if scopes else None)

        q = query or {}
        force = (q.get("force") or ["0"])[0] in ("1", "true", "yes")

        # Schreibverbindung: NUR fuer den Scan-Cache (m009). Der Cache enthaelt
        # keine Ermittlungsergebnisse und ist jederzeit neu erzeugbar; er ist
        # daher bewusst kein auditierter Schreibpfad.
        con = self._rw_con()
        try:
            result = ReportsRepo(con, self._evidence_dir).list_reports(
                force=force)
        except Exception as exc:
            logger.exception("Berichts-Scan fehlgeschlagen")
            return Response.json(500, {"error": "scan_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        if scope != "alle":
            result["reports"] = [r for r in result["reports"]
                                 if r.get("assigned_to") == person_id]
            result["count"] = len(result["reports"])
        result["scope"] = scope
        return Response.json(200, result)

    # =====================================================================
    # BERICHTS-VORSCHAU (Build 410, SF-1 — Vermaehlung B6xB7).
    #   GET /api/report/render?subject_id=<uid>[&report_id=<rid>]
    #   Read-only HTML-Vorschau des Berichtstexts fuer Lektorat (W4) und
    #   Chef-Freigabe (W5). Byte-identisch zum Ermittler-Export, weil derselbe
    #   DB-neutrale Renderer (report_render) auf denselben Quellen laeuft.
    # =====================================================================
    def _case_field(self, uid: int, column: str):
        """Liest EIN Feld der cases-Zeile (coordinator.db, read-only)."""
        con = self._ro_con()
        try:
            row = con.execute(
                "SELECT %s AS v FROM cases WHERE subject_id = ?" % column, (uid,)
            ).fetchone()
            return row["v"] if row is not None else None
        except sqlite3.Error:
            return None
        finally:
            con.close()

    def _report_render(self, person_id: int,
                       query: Optional[Dict[str, List[str]]]) -> Response:
        """
        Liefert die read-only HTML-Vorschau EINES Berichts.

        RECHTE: reports.review ODER reports.approve ('approve' impliziert
        'review'; identische Regel wie /api/reports und /api/report/verify).
        Scope 'eigene' -> nur eigene zugewiesene Faelle; sonst 403.

        Quelle: report_render.ReportSource + HtmlRenderer ueber ein
        ausschliesslich read-only geoeffnetes ReadonlyReportBundle. Es wird
        NICHTS in die evidence_<uid>.db geschrieben (Migrationsvorbehalt,
        "nie zwei Schreiber pro Datei").
        """
        policy = self.resolve_policy(person_id)
        can_review = policy.can(CAP_REPORTS_REVIEW)
        can_approve = policy.can(CAP_REPORTS_APPROVE)
        if not (can_review or can_approve):
            return self._forbidden(CAP_REPORTS_REVIEW)

        scopes = []
        if can_review:
            scopes.append(policy.scope(CAP_REPORTS_REVIEW))
        if can_approve:
            scopes.append(policy.scope(CAP_REPORTS_APPROVE))
        scope = "alle" if "alle" in scopes else (scopes[0] if scopes else None)

        q = query or {}
        uid_raw = (q.get("subject_id") or [None])[0]
        if uid_raw is None:
            return Response.json(400, {"error": "subject_id_required"})
        try:
            uid = int(uid_raw)
        except (TypeError, ValueError):
            return Response.json(400, {"error": "subject_id_invalid",
                                       "value": uid_raw})

        report_id: Optional[int] = None
        rid_raw = (q.get("report_id") or [None])[0]
        if rid_raw not in (None, ""):
            try:
                report_id = int(rid_raw)
            except (TypeError, ValueError):
                return Response.json(400, {"error": "report_id_invalid",
                                           "value": rid_raw})

        # Scope 'eigene': der Fall muss dem Anfragenden zugewiesen sein.
        if scope != "alle":
            if self._case_field(uid, "assigned_to") != person_id:
                return self._forbidden(CAP_REPORTS_REVIEW)

        # Lazy-Import: das Renderer-Paket nur bei Bedarf laden.
        from report_render.report_source import ReportSource, NoReportError
        from report_render.html_renderer import HtmlRenderer
        from management.reports.readonly_report_bundle import (
            ReadonlyReportBundle,
        )

        try:
            bundle = ReadonlyReportBundle(
                evidence_dir=self._evidence_dir,
                forensic_dir=self._forensic_dir,
                assets_dir=self._assets_dir,
                templates_db=self._templates_db,
                default_db=self._default_db,
                uid=uid,
            ).open()
        except FileNotFoundError as exc:
            return Response.json(404, {"error": "evidence_not_found",
                                       "subject_id": uid, "detail": str(exc)})

        try:
            username = self._case_field(uid, "username") or ("uid_%d" % uid)
            source = ReportSource(
                evidence=bundle.evidence,
                templates=bundle.templates,
                assets=bundle.assets,
                forensic_con=bundle.connection,
                uid=uid,
                username=str(username),
                generated_at=int(time.time()),   # Zeitstempel von aussen (Test/Determinismus)
            )
            doc = source.build(report_id)
            body = HtmlRenderer().render(doc)
        except NoReportError as exc:
            return Response.json(404, {"error": "no_report",
                                       "subject_id": uid, "detail": str(exc)})
        except Exception as exc:  # pragma: no cover - defensiver 500
            logger.exception(
                "Berichts-Render fehlgeschlagen (uid=%s, report_id=%s)",
                uid, report_id,
            )
            return Response.json(500, {"error": "render_failed",
                                       "detail": str(exc)})
        finally:
            bundle.close()

        logger.info(
            "Berichts-Vorschau: uid=%d, report_id=%s, %d Bloecke, %d Warnungen,"
            " %d Bytes (person=%d, scope=%s)",
            uid, doc.report_id, len(doc.blocks), len(doc.warnings), len(body),
            person_id, scope,
        )
        return Response(status=200, content_type="text/html; charset=utf-8",
                        body=body)

    # =====================================================================
    # ANNOTATIONS-SUPPORT-VIEW (Build 411, SF-2 — Vermaehlung B6xB7).
    #   GET /api/report/annotations?subject_id=<uid>[&report_id=<rid>]
    #   Read-only: die dem Bericht zugrunde liegenden Annotationen (Belege) fuer
    #   Lektorat (W4) und Chef-Freigabe (W5), damit Aussagen am Beleg verifiziert
    #   werden koennen. Ein LESENDER Zugriff wird flach im coordinator.db-
    #   audit_log belegt (Chain-of-Custody; mc 2026-07-14).
    # =====================================================================
    def _report_annotations(self, person_id: int,
                            query: Optional[Dict[str, List[str]]]) -> Response:
        """
        Liefert die verankerten Annotationen EINES Berichts (JSON), read-only.

        RECHTE: reports.review ODER reports.approve (identisch zu
        /api/report/render). Scope 'eigene' -> nur eigene zugewiesene Faelle.
        Es wird NICHTS in die evidence_<uid>.db geschrieben.
        """
        policy = self.resolve_policy(person_id)
        can_review = policy.can(CAP_REPORTS_REVIEW)
        can_approve = policy.can(CAP_REPORTS_APPROVE)
        if not (can_review or can_approve):
            return self._forbidden(CAP_REPORTS_REVIEW)

        scopes = []
        if can_review:
            scopes.append(policy.scope(CAP_REPORTS_REVIEW))
        if can_approve:
            scopes.append(policy.scope(CAP_REPORTS_APPROVE))
        scope = "alle" if "alle" in scopes else (scopes[0] if scopes else None)

        q = query or {}
        uid_raw = (q.get("subject_id") or [None])[0]
        if uid_raw is None:
            return Response.json(400, {"error": "subject_id_required"})
        try:
            uid = int(uid_raw)
        except (TypeError, ValueError):
            return Response.json(400, {"error": "subject_id_invalid",
                                       "value": uid_raw})

        report_id: Optional[int] = None
        rid_raw = (q.get("report_id") or [None])[0]
        if rid_raw not in (None, ""):
            try:
                report_id = int(rid_raw)
            except (TypeError, ValueError):
                return Response.json(400, {"error": "report_id_invalid",
                                           "value": rid_raw})

        if scope != "alle":
            if self._case_field(uid, "assigned_to") != person_id:
                return self._forbidden(CAP_REPORTS_REVIEW)

        from management.reports.readonly_report_bundle import (
            ReadonlyReportBundle,
        )
        from management.reports.annotation_support_reader import (
            AnnotationSupportReader,
        )

        try:
            bundle = ReadonlyReportBundle(
                evidence_dir=self._evidence_dir,
                forensic_dir=self._forensic_dir,
                assets_dir=self._assets_dir,
                templates_db=self._templates_db,
                default_db=self._default_db,
                uid=uid,
            ).open()
        except FileNotFoundError as exc:
            return Response.json(404, {"error": "evidence_not_found",
                                       "subject_id": uid, "detail": str(exc)})

        try:
            data = AnnotationSupportReader(bundle).read(report_id)
        except Exception as exc:  # pragma: no cover - defensiver 500
            logger.exception(
                "Annotations-Support-View fehlgeschlagen (uid=%s, report_id=%s)",
                uid, report_id,
            )
            return Response.json(500, {"error": "annotations_failed",
                                       "detail": str(exc)})
        finally:
            bundle.close()

        if data is None:
            return Response.json(404, {"error": "no_report", "subject_id": uid})

        data["subject_id"] = uid
        data["scope"] = scope

        # Flaches Lese-Audit (Chain-of-Custody). BEST-EFFORT: eine momentan
        # gesperrte Audit-Kette darf dem/der Pruefer:in NICHT den Beleg-Einblick
        # verweigern; der Fehlschlag wird protokolliert, nicht verschluckt.
        self._audit_annotation_view(
            person_id, uid, int(data["report_id"]),
            int(data["anchor_count"]), scope,
        )

        logger.info(
            "Annotations-Support-View: uid=%d, report_id=%s, %d Anker "
            "(person=%d, scope=%s)",
            uid, data["report_id"], data["anchor_count"], person_id, scope,
        )
        return Response.json(200, data)

    def _audit_annotation_view(self, person_id: int, uid: int, report_id: int,
                               anchor_count: int, scope: Optional[str]) -> None:
        """
        Belegt EINEN lesenden Zugriff auf die Belege im coordinator.db-audit_log
        (Hash-Kette, ueber den auditierten Schreibpfad). Best-effort: bei Fehler
        nur Warnung, damit der Lesevorgang selbst nicht scheitert.
        """
        self._audit_best_effort(
            event_type="report_annotations_viewed", actor_id=person_id,
            target_type="report", target_id=str(report_id),
            payload={"subject_id": uid, "report_id": report_id,
                     "anchor_count": anchor_count, "scope": scope},
            what="annotations-view",
        )

    def _audit_best_effort(self, *, event_type: str, actor_id: int,
                           target_type: str, target_id: str,
                           payload: Dict[str, Any], what: str) -> None:
        """
        Schreibt einen Audit-Eintrag ueber den auditierten coordinator-Pfad.
        BEST-EFFORT: eine momentan gesperrte Kette darf den ausloesenden Vorgang
        nicht scheitern lassen (Fehler wird protokolliert, nicht verschluckt).
        """
        from management.audit.audit_log import AuditLog
        from management.gateway.coordinator_writer import CoordinatorWriter
        con = self._rw_con()
        try:
            CoordinatorWriter(con, AuditLog(con)).audited_write(
                do_write=lambda c: payload,
                event_type=event_type, actor_id=actor_id,
                target_type=target_type, target_id=target_id,
            )
        except Exception as exc:
            logger.warning("Audit '%s' nicht geschrieben (%s): %s",
                           what, target_id, exc)
        finally:
            con.close()

    # =====================================================================
    # KOMMENTAR-BRUECKE (Build 412, SF-3 — Vermaehlung B6xB7).
    #   Lektorat (W4) / Chef-Freigabe (W5) kommentieren den Berichtstext. Die
    #   Kommentare liegen je Person in DEREN eigener Addendum-Datei
    #   (evidence_<uid>_<pid>.db) — NIE in der evidence_<uid>.db. "Nie zwei
    #   Schreiber pro Datei": nur der Besitzer (pid == person_id) schreibt.
    #     GET  /api/report/comments  — Union aller Prueferinnen (read-only)
    #     POST /api/report/comment          — Kommentar anlegen (eigene Datei)
    #     POST /api/report/comment/resolve  — EIGENEN Kommentar-Status setzen
    # =====================================================================
    def _reviewer_role(self, policy) -> str:
        """Rolle fuer den Kommentar-Beleg: Chefin (approve) schlaegt Lektor."""
        return "supervisor" if policy.can(CAP_REPORTS_APPROVE) else "lector"

    def _block_sha256(self, uid: int, block_id: str) -> Optional[str]:
        """
        Hash des block_data ZUM KOMMENTARZEITPUNKT (read-only aus evidence),
        damit eine spaetere Blockaenderung erkennbar wird. None, wenn evidence/
        Block fehlt.
        """
        import hashlib
        path = Path(self._evidence_dir) / ("evidence_%d.db" % int(uid))
        if not path.exists():
            return None
        try:
            con = sqlite3.connect("file:%s?mode=ro" % path.resolve(), uri=True)
        except sqlite3.Error:
            return None
        try:
            row = con.execute(
                "SELECT block_data FROM report_blocks WHERE block_id = ?",
                (block_id,),
            ).fetchone()
            if row is None or row[0] is None:
                return None
            return hashlib.sha256(str(row[0]).encode("utf-8")).hexdigest()
        except sqlite3.Error:
            return None
        finally:
            con.close()

    def _report_comments(self, person_id: int,
                         query: Optional[Dict[str, List[str]]]) -> Response:
        """Union aller Review-Kommentare eines Berichts (read-only, JSON)."""
        policy = self.resolve_policy(person_id)
        can_review = policy.can(CAP_REPORTS_REVIEW)
        can_approve = policy.can(CAP_REPORTS_APPROVE)
        if not (can_review or can_approve):
            return self._forbidden(CAP_REPORTS_REVIEW)
        scopes = []
        if can_review:
            scopes.append(policy.scope(CAP_REPORTS_REVIEW))
        if can_approve:
            scopes.append(policy.scope(CAP_REPORTS_APPROVE))
        scope = "alle" if "alle" in scopes else (scopes[0] if scopes else None)

        q = query or {}
        uid_raw = (q.get("subject_id") or [None])[0]
        if uid_raw is None:
            return Response.json(400, {"error": "subject_id_required"})
        try:
            uid = int(uid_raw)
        except (TypeError, ValueError):
            return Response.json(400, {"error": "subject_id_invalid",
                                       "value": uid_raw})
        report_id: Optional[int] = None
        rid_raw = (q.get("report_id") or [None])[0]
        if rid_raw not in (None, ""):
            try:
                report_id = int(rid_raw)
            except (TypeError, ValueError):
                return Response.json(400, {"error": "report_id_invalid",
                                           "value": rid_raw})
        if scope != "alle":
            if self._case_field(uid, "assigned_to") != person_id:
                return self._forbidden(CAP_REPORTS_REVIEW)

        from management.reports.review_comment_reader import ReviewCommentReader
        comments = ReviewCommentReader(self._evidence_dir, uid).read(report_id)
        return Response.json(200, {"subject_id": uid, "report_id": report_id,
                                   "count": len(comments), "comments": comments})

    # =====================================================================
    # AUTHORING: PLATZHALTER-QUERIES (Build 422, W2 — templates.db).
    #   GET  /api/templates/queries       — Liste (Recht templates.edit)
    #   POST /api/templates/query         — anlegen/aendern (validiert + fdb-
    #                                       Dry-Run, auditiert ueber TemplatesWriter)
    #   POST /api/templates/query/dryrun  — SCHREIBFREIE Vorschau (Build 423):
    #                                       Validierung + fdb-Dry-Run, KEIN Write,
    #                                       KEIN Audit (Test vor dem Speichern)
    # =====================================================================
    def _templates_queries(self, person_id: int) -> Response:
        """Liste der Platzhalter-Queries (read-only)."""
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)
        from management.templates_admin.query_repo import QueryAuthorRepo
        con = self._templates_ro_con()
        try:
            queries = QueryAuthorRepo(con).list()
        except sqlite3.Error as exc:
            return Response.json(500, {"error": "templates_read_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"count": len(queries), "queries": queries})

    def _templates_query_upsert(self, person_id: int,
                                payload: Dict[str, Any]) -> Response:
        """
        Legt eine Platzhalter-Query an oder aendert sie. Ablauf:
          1. Recht templates.edit.
          2. Statische Validierung (query_validator).
          3. Optionaler fdb-Dry-Run (wenn test_subject_id gesetzt und die
             Beispiel-forensic_<uid>.db vorhanden ist).
          4. Auditiertes Upsert ueber den TemplatesWriter.
        """
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)

        from management.templates_admin.query_validator import (
            validate_static, dry_run, QueryValidationError,
        )
        from management.templates_admin.query_repo import QueryAuthorRepo

        q = {
            "id": payload.get("id"),
            "title": payload.get("title"),
            "description": payload.get("description", ""),
            "sql_query": payload.get("sql_query"),
            "tags": payload.get("tags"),
            "return_type": payload.get("return_type") or "scalar",
        }
        errors = validate_static(q)
        if errors:
            return Response.json(400, {"error": "validation", "errors": errors})

        # Optionaler Dry-Run gegen eine Beispiel-fdb.
        dry: Dict[str, Any] = {"ran": False, "reason": "kein test_subject_id."}
        test_uid_raw = payload.get("test_subject_id")
        if test_uid_raw not in (None, ""):
            try:
                test_uid = int(test_uid_raw)
            except (TypeError, ValueError):
                return Response.json(400, {"error": "bad_request",
                                           "detail": "test_subject_id ungueltig."})
            fdb_path = "%s/forensic_%d.db" % (
                str(self._forensic_dir).rstrip("/"), test_uid)
            try:
                dry = dry_run(q["sql_query"], test_uid, fdb_path,
                              return_type=q["return_type"])
            except QueryValidationError as exc:
                return Response.json(400, {"error": "dry_run",
                                           "errors": exc.errors})

        # Auditiertes Upsert.
        con = self._ro_con()
        try:
            who = self._person(con, person_id)
        finally:
            con.close()
        changed_by = who["system_username"] if who else str(person_id)

        tcon = self._templates_rw_con()
        try:
            result = QueryAuthorRepo(tcon).upsert(q, changed_by=changed_by)
        except sqlite3.Error as exc:
            return Response.json(500, {"error": "templates_write_failed",
                                       "detail": str(exc)})
        finally:
            tcon.close()

        logger.info("Platzhalter-Query %s (%s) von %s",
                    result["target_id"],
                    "angelegt" if result["created"] else "geaendert",
                    changed_by)
        return Response.json(200, {"ok": True, "target_id": result["target_id"],
                                   "created": result["created"], "dry_run": dry})

    def _templates_query_dryrun(self, person_id: int,
                                payload: Dict[str, Any]) -> Response:
        """
        SCHREIBFREIE Vorschau (Build 423, W2-Frontend): validiert eine
        Platzhalter-Query STATISCH und fuehrt - falls test_subject_id gesetzt ist -
        den fdb-Dry-Run READ-ONLY aus. Es wird NICHTS geschrieben und NICHTS
        auditiert (kein Beleg entsteht, weil kein Zustand sich aendert). So kann
        die Redakteur:in eine Query testen, BEVOR sie sie speichert (Grundregel:
        Ueberpruefbarkeit; keine stille Fehlaufloesung).

        Antwort IMMER 200 mit {ok, errors, dry_run} - die Fehler werden als
        DATEN geliefert (nicht als HTTP-Fehler), damit die Editor-Maske sie
        zusammen mit dem Dry-Run-Ergebnis anzeigen kann. Das Recht bleibt
        Voraussetzung (403 ohne templates.edit); ein POST erfordert - wie jeder
        Schreibpfad - das X-AIW-Token (im HTTP-Handler geprueft), obwohl hier
        nichts geschrieben wird (bewusst: einheitlicher POST-Pfad, Token = wer
        ueberhaupt Autoren-Aktionen ausloesen darf).
        """
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)

        from management.templates_admin.query_validator import (
            validate_static, dry_run, QueryValidationError,
        )

        q = {
            "id": payload.get("id"),
            "title": payload.get("title"),
            "description": payload.get("description", ""),
            "sql_query": payload.get("sql_query"),
            "tags": payload.get("tags"),
            "return_type": payload.get("return_type") or "scalar",
        }
        errors = validate_static(q)

        dry: Dict[str, Any] = {"ran": False, "reason": "kein test_subject_id."}
        test_uid_raw = payload.get("test_subject_id")
        # Dry-Run nur, wenn die statische Pruefung sauber ist UND eine test_subject_id
        # vorliegt (eine kaputte Query gar nicht erst gegen die fdb ausfuehren).
        if not errors and test_uid_raw not in (None, ""):
            try:
                test_uid = int(test_uid_raw)
            except (TypeError, ValueError):
                errors.append("test_subject_id ungueltig (ganze Zahl erwartet).")
            else:
                fdb_path = "%s/forensic_%d.db" % (
                    str(self._forensic_dir).rstrip("/"), test_uid)
                try:
                    dry = dry_run(q["sql_query"], test_uid, fdb_path,
                                  return_type=q["return_type"])
                except QueryValidationError as exc:
                    errors.extend(exc.errors)

        return Response.json(200, {"ok": not errors, "errors": errors,
                                   "dry_run": dry})

    # =====================================================================
    # AUTHORING: DOKUMENTVORLAGEN (Build 424, W3 — templates.db).
    #   GET  /api/templates/documents        — Liste (Recht templates.edit)
    #   POST /api/templates/document         — anlegen/aendern (validiert,
    #                                          auditiert ueber TemplatesWriter,
    #                                          target_type='template')
    #   POST /api/templates/document/dryrun  — SCHREIBFREIE Struktur-Vorschau
    #                                          (Validierung + Blocktyp-Zaehlung),
    #                                          kein Write, kein Audit
    # =====================================================================
    def _templates_documents(self, person_id: int) -> Response:
        """Liste der Dokumentvorlagen (read-only)."""
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)
        from management.templates_admin.template_repo import TemplateAuthorRepo
        con = self._templates_ro_con()
        try:
            docs = TemplateAuthorRepo(con).list()
        except sqlite3.Error as exc:
            return Response.json(500, {"error": "templates_read_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"count": len(docs), "documents": docs})

    def _tpl_document_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Baut das Vorlagen-dict aus dem Request-Payload (gemeinsame Basis fuer
        Upsert und Dry-Run). 'blocks' wird als native Liste erwartet."""
        return {
            "template_key": payload.get("template_key"),
            "title": payload.get("title"),
            "description": payload.get("description"),
            "report_type": payload.get("report_type"),
            "blocks": payload.get("blocks"),
            "sort_order": payload.get("sort_order") or 0,
        }

    def _templates_document_upsert(self, person_id: int,
                                   payload: Dict[str, Any]) -> Response:
        """
        Legt eine Dokumentvorlage an oder aendert sie. Ablauf:
          1. Recht templates.edit.
          2. Statische Validierung (template_validator: key/title/report_type +
             Blockstruktur gegen die neun bekannten Blocktypen).
          3. Auditiertes Upsert ueber den TemplatesWriter (target_type='template').
        """
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)

        from management.templates_admin.template_validator import validate_static
        from management.templates_admin.template_repo import TemplateAuthorRepo

        t = self._tpl_document_from_payload(payload)
        errors = validate_static(t)
        if errors:
            return Response.json(400, {"error": "validation", "errors": errors})

        con = self._ro_con()
        try:
            who = self._person(con, person_id)
        finally:
            con.close()
        changed_by = who["system_username"] if who else str(person_id)

        tcon = self._templates_rw_con()
        try:
            result = TemplateAuthorRepo(tcon).upsert(t, changed_by=changed_by)
        except sqlite3.Error as exc:
            return Response.json(500, {"error": "templates_write_failed",
                                       "detail": str(exc)})
        finally:
            tcon.close()

        logger.info("Dokumentvorlage %s (%s) von %s",
                    result["target_id"],
                    "angelegt" if result["created"] else "geaendert",
                    changed_by)
        return Response.json(200, {"ok": True, "target_id": result["target_id"],
                                   "created": result["created"]})

    def _templates_document_dryrun(self, person_id: int,
                                   payload: Dict[str, Any]) -> Response:
        """
        SCHREIBFREIE Vorschau (Build 424): validiert eine Dokumentvorlage
        STATISCH und liefert - bei gueltiger Struktur - eine Blocktyp-Zaehlung
        ("was steckt in der Vorlage?"). Es wird NICHTS geschrieben und NICHTS
        auditiert. Antwort IMMER 200 mit {ok, errors, summary}; Fehler als DATEN
        (nicht als HTTP-Fehler), damit die Editor-Maske sie anzeigen kann.
        Recht bleibt Voraussetzung (403 ohne templates.edit).
        """
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)

        from management.templates_admin.template_validator import (
            validate_static, coerce_blocks, block_type_summary,
        )

        t = self._tpl_document_from_payload(payload)
        errors = validate_static(t)
        summary: List[Dict[str, Any]] = []
        if not errors:
            blocks, _berr = coerce_blocks(t)
            summary = block_type_summary(blocks)
        return Response.json(200, {"ok": not errors, "errors": errors,
                                   "summary": summary})

    # =====================================================================
    # AUTHORING: BAUSTEIN-MODULE (Build 426, W1 — templates.db).
    #   GET  /api/templates/modules        — Liste (Recht templates.edit)
    #   POST /api/templates/module         — anlegen/aendern (validiert,
    #                                        auditiert ueber TemplatesWriter,
    #                                        target_type='module')
    #   POST /api/templates/module/dryrun  — SCHREIBFREIE Vorschau (Feldpruefung
    #                                        + Platzhalter-Zaehlung im body),
    #                                        kein Write, kein Audit
    # =====================================================================
    def _templates_modules(self, person_id: int) -> Response:
        """Liste der Baustein-Module (read-only)."""
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)
        from management.templates_admin.module_repo import ModuleAuthorRepo
        con = self._templates_ro_con()
        try:
            modules = ModuleAuthorRepo(con).list()
        except sqlite3.Error as exc:
            return Response.json(500, {"error": "templates_read_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"count": len(modules), "modules": modules})

    def _tpl_module_from_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Baut das Modul-dict aus dem Payload (Basis fuer Upsert und Dry-Run)."""
        return {
            "module_key": payload.get("module_key"),
            "title": payload.get("title"),
            "description": payload.get("description"),
            "role": payload.get("role"),
            "topic": payload.get("topic"),
            "body": payload.get("body"),
            "sort_order": payload.get("sort_order") or 0,
        }

    def _templates_module_upsert(self, person_id: int,
                                 payload: Dict[str, Any]) -> Response:
        """
        Legt einen Baustein an oder aendert ihn. Ablauf:
          1. Recht templates.edit.
          2. Statische Validierung (module_validator: key/title/role/topic/body).
          3. Auditiertes Upsert ueber den TemplatesWriter (target_type='module').
        """
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)

        from management.templates_admin.module_validator import validate_static
        from management.templates_admin.module_repo import ModuleAuthorRepo

        m = self._tpl_module_from_payload(payload)
        errors = validate_static(m)
        if errors:
            return Response.json(400, {"error": "validation", "errors": errors})

        con = self._ro_con()
        try:
            who = self._person(con, person_id)
        finally:
            con.close()
        changed_by = who["system_username"] if who else str(person_id)

        tcon = self._templates_rw_con()
        try:
            result = ModuleAuthorRepo(tcon).upsert(m, changed_by=changed_by)
        except sqlite3.Error as exc:
            return Response.json(500, {"error": "templates_write_failed",
                                       "detail": str(exc)})
        finally:
            tcon.close()

        logger.info("Baustein-Modul %s (%s) von %s",
                    result["target_id"],
                    "angelegt" if result["created"] else "geaendert",
                    changed_by)
        return Response.json(200, {"ok": True, "target_id": result["target_id"],
                                   "created": result["created"]})

    def _templates_module_dryrun(self, person_id: int,
                                 payload: Dict[str, Any]) -> Response:
        """
        SCHREIBFREIE Vorschau (Build 426): validiert einen Baustein STATISCH und
        liefert - bei gueltigen Feldern - eine Platzhalter-Zaehlung des body
        (auto/mandatory/optional). Kein Write, kein Audit. Antwort IMMER 200 mit
        {ok, errors, summary}; Fehler als DATEN. 403 ohne templates.edit.
        """
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)

        from management.templates_admin.module_validator import (
            validate_static, placeholder_summary,
        )

        m = self._tpl_module_from_payload(payload)
        errors = validate_static(m)
        summary: List[Dict[str, Any]] = []
        if not errors:
            summary = placeholder_summary(m.get("body"))
        return Response.json(200, {"ok": not errors, "errors": errors,
                                   "summary": summary})

    def _report_comment_create(self, person_id: int,
                               payload: Dict[str, Any]) -> Response:
        """Legt einen Kommentar in der EIGENEN Addendum-Datei an."""
        policy = self.resolve_policy(person_id)
        can_review = policy.can(CAP_REPORTS_REVIEW)
        can_approve = policy.can(CAP_REPORTS_APPROVE)
        if not (can_review or can_approve):
            return self._forbidden(CAP_REPORTS_REVIEW)

        try:
            uid = int(payload.get("subject_id"))
            report_id = int(payload.get("report_id"))
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "subject_id und report_id erforderlich."})
        block_id = payload.get("block_id")
        if block_id is not None:
            block_id = str(block_id)
        text = (payload.get("comment_text") or "").strip()
        if not text:
            return Response.json(400, {"error": "empty_comment",
                                       "detail": "comment_text erforderlich."})
        suggested = payload.get("suggested_content")
        if suggested is not None:
            suggested = str(suggested)

        # Scope 'eigene': nur eigene zugewiesene Faelle.
        scope = policy.scope(CAP_REPORTS_APPROVE) if can_approve \
            else policy.scope(CAP_REPORTS_REVIEW)
        if scope != "alle" and self._case_field(uid, "assigned_to") != person_id:
            return self._forbidden(CAP_REPORTS_REVIEW)

        role = self._reviewer_role(policy)
        block_hash = self._block_sha256(uid, block_id) if block_id else None

        from db.review_addendum_db import open_addendum
        db = open_addendum(self._evidence_dir, uid, person_id, create=True)
        try:
            cid = db.add_comment(
                report_id=report_id, block_id=block_id, reviewer_role=role,
                comment_text=text, suggested_content=suggested,
                block_sha256=block_hash,
            )
        except Exception as exc:
            logger.exception("Kommentar anlegen fehlgeschlagen (uid=%s)", uid)
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            db.close()

        self._audit_best_effort(
            event_type="review_comment_added", actor_id=person_id,
            target_type="report", target_id=str(report_id),
            payload={"subject_id": uid, "report_id": report_id,
                     "block_id": block_id, "comment_id": cid, "role": role},
            what="comment-add",
        )
        return Response.json(200, {"comment_id": cid, "status": "pending",
                                   "reviewer_role": role, "subject_id": uid,
                                   "report_id": report_id, "block_id": block_id})

    def _report_comment_resolve(self, person_id: int,
                                payload: Dict[str, Any]) -> Response:
        """Setzt den Status eines EIGENEN Kommentars (owner-only ueber Pfad)."""
        policy = self.resolve_policy(person_id)
        if not (policy.can(CAP_REPORTS_REVIEW) or policy.can(CAP_REPORTS_APPROVE)):
            return self._forbidden(CAP_REPORTS_REVIEW)
        try:
            uid = int(payload.get("subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "subject_id erforderlich."})
        comment_id = payload.get("comment_id")
        status = payload.get("status")
        from db.review_addendum_db import open_addendum, VALID_STATUS
        if not comment_id or status not in VALID_STATUS:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "comment_id und gueltiger status erforderlich.",
                "valid_status": list(VALID_STATUS)})

        # create=False: nur die EIGENE Datei; existiert sie nicht, gibt es auch
        # keinen eigenen Kommentar zu schliessen.
        db = open_addendum(self._evidence_dir, uid, person_id, create=False)
        if db is None:
            return Response.json(404, {"error": "comment_not_found",
                                       "comment_id": comment_id})
        try:
            if db.get_comment(str(comment_id)) is None:
                return Response.json(404, {"error": "comment_not_found",
                                           "comment_id": comment_id})
            db.set_status(str(comment_id), str(status))
        except Exception as exc:
            logger.exception("Kommentar-Status setzen fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            db.close()

        self._audit_best_effort(
            event_type="review_comment_resolved", actor_id=person_id,
            target_type="report_comment", target_id=str(comment_id),
            payload={"subject_id": uid, "comment_id": comment_id,
                     "status": status},
            what="comment-resolve",
        )
        return Response.json(200, {"comment_id": comment_id, "status": status})

    # =====================================================================
    # BERICHTS-VERSIEGELUNG (Build 377).
    #   GET  /api/report/verify   — Siegel nachpruefen (lesend; wer Berichte
    #                                sehen darf, darf auch pruefen).
    #   POST /api/report/approve  — freigeben/versiegeln (reports.approve,
    #                                Scope 'alle'; auditiert + Token-geschuetzt).
    # =====================================================================

    def _approval_service(self, con) -> ApprovalService:
        return ApprovalService(con, self._evidence_dir, self._approved_db)

    def _report_verify(self, person_id: int,
                       query: Optional[Dict[str, List[str]]]) -> Response:
        policy = self.resolve_policy(person_id)
        if not (policy.can(CAP_REPORTS_REVIEW)
                or policy.can(CAP_REPORTS_APPROVE)):
            return self._forbidden(CAP_REPORTS_REVIEW)

        q = query or {}

        def _int(key):
            vals = q.get(key)
            if not vals:
                return None
            try:
                return int(vals[0])
            except ValueError:
                return None

        subject_id, report_id = _int("subject_id"), _int("report_id")
        if subject_id is None or report_id is None:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "subject_id und report_id erforderlich."})

        con = self._ro_con()
        try:
            result = self._approval_service(con).verify(
                subject_id=subject_id, report_id=report_id)
        finally:
            con.close()
        return Response.json(200, result)

    def _report_approve(self, person_id: int,
                        payload: Dict[str, Any]) -> Response:
        """
        Bericht freigeben und versiegeln. Erfordert reports.approve mit Scope
        'alle' (die Abnahme ist per Definition fremdbezogen: der Supervisor
        gibt die Berichte der Ermittler frei).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_REPORTS_APPROVE):
            return self._forbidden(CAP_REPORTS_APPROVE)
        if policy.scope(CAP_REPORTS_APPROVE) != "alle":
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_REPORTS_APPROVE,
                "detail": "Freigabe erfordert Scope 'alle'."})

        try:
            subject_id = int(payload.get("subject_id"))
            report_id = int(payload.get("report_id"))
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "subject_id und report_id erforderlich."})
        is_final = bool(payload.get("is_final", False))
        note = payload.get("note")

        con = self._rw_con()
        try:
            who = self._person(con, person_id)
            username = who["system_username"] if who else str(person_id)
            result = self._approval_service(con).approve(
                subject_id=subject_id, report_id=report_id, actor_id=person_id,
                actor_username=username, is_final=is_final, note=note)
        except ApprovalError as exc:
            # Fachlicher Fehler ODER Teilerfolg — in beiden Faellen mit klarer
            # Begruendung sichtbar machen (Grundregel 1).
            logger.warning("Freigabe abgelehnt/unvollstaendig: %s", exc)
            return Response.json(409, {"error": "approval_failed",
                                       "detail": str(exc)})
        except Exception as exc:
            logger.exception("Freigabe fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, result)

    def _report_return(self, person_id: int,
                       payload: Dict[str, Any]) -> Response:
        """
        RUECKGABE ZUR NACHBESSERUNG (Build 380): submitted -> draft.

        Berechtigt sind Lektor (reports.review) UND Chef-Ermittlerin
        (reports.approve — impliziert reports.review, mc 2026-07-10). Der AUTOR
        kann sich NICHT selbst zurueckholen; er hat keine dieser Faehigkeiten
        auf fremde Berichte.

        Scope 'alle' erforderlich: die Rueckgabe betrifft per Definition den
        Bericht eines ANDEREN (des Autors).
        """
        policy = self.resolve_policy(person_id)
        can_review = policy.can(CAP_REPORTS_REVIEW)
        can_approve = policy.can(CAP_REPORTS_APPROVE)
        if not (can_review or can_approve):
            return self._forbidden(CAP_REPORTS_REVIEW)

        scopes = []
        if can_review:
            scopes.append(policy.scope(CAP_REPORTS_REVIEW))
        if can_approve:
            scopes.append(policy.scope(CAP_REPORTS_APPROVE))
        if "alle" not in scopes:
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_REPORTS_REVIEW,
                "detail": "Rueckgabe erfordert Scope 'alle'."})

        try:
            subject_id = int(payload.get("subject_id"))
            report_id = int(payload.get("report_id"))
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "subject_id und report_id erforderlich."})
        note = payload.get("note")

        con = self._rw_con()
        try:
            who = self._person(con, person_id)
            username = who["system_username"] if who else str(person_id)
            result = self._approval_service(con).return_to_draft(
                subject_id=subject_id, report_id=report_id, actor_id=person_id,
                actor_username=username, note=note)
        except ApprovalError as exc:
            logger.warning("Rueckgabe abgelehnt/unvollstaendig: %s", exc)
            return Response.json(409, {"error": "return_failed",
                                       "detail": str(exc)})
        except Exception as exc:
            logger.exception("Rueckgabe fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, result)

    # =====================================================================
    # FALL-AUTODETEKTION (Build 383).
    #   GET  /api/cases/detect  — Abgleich Platte <-> Fallakte (rein lesend).
    #   POST /api/cases/import  — neu erkannte Faelle AUDITIERT aufnehmen.
    #
    # Ein Fall EXISTIERT, sobald forensic_<uid>.db vorliegt (mc): unabhaengig
    # davon, ob schon jemand daran gearbeitet hat.
    # =====================================================================

    def _detector(self, con) -> CaseDetector:
        return CaseDetector(con, self._forensic_dir, self._evidence_dir,
                            self._assets_dir)

    def _cases_detect(self, person_id: int) -> Response:
        denied = self._require_assignment_scope(person_id)
        if denied is not None:
            return denied

        con = self._ro_con()
        try:
            result = self._detector(con).detect()
        except Exception as exc:
            logger.exception("Fall-Detektion fehlgeschlagen")
            return Response.json(500, {"error": "detect_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, result)

    def _cases_import(self, person_id: int,
                      payload: Dict[str, Any]) -> Response:
        """
        Nimmt neu erkannte Faelle auf — AUDITIERT (CasesRepo.create_case ->
        Beleg case_created je Fall). Auswahl per 'subject_ids' ODER 'all': true.
        """
        denied = self._require_assignment_scope(person_id)
        if denied is not None:
            return denied

        all_new = bool(payload.get("all", False))
        raw_ids = payload.get("subject_ids") or []
        if not all_new and not isinstance(raw_ids, list):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "subject_ids muss eine Liste sein (oder all: true)."})
        try:
            subject_ids = [int(u) for u in raw_ids]
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request", "detail": "subject_ids ungueltig."})

        if not all_new and not subject_ids:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "Keine Faelle ausgewaehlt (subject_ids oder all: true)."})

        con = self._rw_con()
        try:
            importer = CaseImporter(con, self._detector(con))
            result = importer.import_cases(actor_id=person_id,
                                           subject_ids=subject_ids,
                                           all_new=all_new)
        except Exception as exc:
            logger.exception("Fall-Aufnahme fehlgeschlagen")
            return Response.json(500, {"error": "import_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, result)

    # ================================================================
    # WIEDERVORLAGE EXTERNER VORGAENGE (Build 385)
    # ----------------------------------------------------------------
    # SCOPE-AUFLOESUNG — die Kapselung dieses Moduls haengt an genau
    # dieser Methode. Sie liefert BEWUSST drei unterscheidbare Ergebnisse:
    #   (None,  None)   -> Scope 'alle': ALLE Faelle sind erlaubt.
    #   (Liste, None)   -> Scope 'eigene': genau diese (ggf. NULL) Faelle.
    #   (None,  Response) -> kein Recht: 403.
    # Ein leerer Ermittler (keine Zuweisung) bekommt eine LEERE LISTE und
    # NICHT 'alle'. Genau diese Verwechslung waere der klassische
    # Kapselungsbruch ueber einen None-Wert.
    # ================================================================
    # ============================================================
    # FREMDFORUM-PROMOTION (Build 460, AP-2G)
    # ------------------------------------------------------------
    #   Kandidaten = forensic_<uid>.db vorhanden, evidence_<uid>.db fehlt
    #   (Dateisystem-Scan, read-only). Der ZUSTAND je Kandidat liegt in
    #   coordinator.db (forum_promotion). Lesen: 'ops.view'. Entscheiden:
    #   'ops.promote' (auditiert). Der Kandidaten-Scan liefert zugleich die
    #   'allowed_uids' fuer den Schreibpfad — es kann keine Entscheidung fuer
    #   einen Nicht-Kandidaten belegt werden (Grundregel 1).
    # ============================================================
    def _storage_candidates(self) -> set:
        """Aktuelle Fremdforum-Kandidaten (read-only Dateisystem-Scan)."""
        report = StorageOverview(
            forensic_dir=self._forensic_dir,
            evidence_dir=self._evidence_dir,
            assets_dir=self._assets_dir).scan()
        return set(report.fremdforum_candidates)

    def _promotion(self, person_id: int) -> Response:
        """
        GET /api/promotion — Fremdforum-Kandidaten mit ihrem Promotions-Zustand
        plus die Liste ALLER erfassten Entscheidungen (Belege). Recht 'ops.view'.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_OPS_VIEW):
            return self._forbidden(CAP_OPS_VIEW)

        try:
            candidates = sorted(self._storage_candidates())
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Kandidaten-Scan (data/) fehlgeschlagen")
            return Response.json(500, {"error": "promotion_scan_failed",
                                       "detail": str(exc)})

        con = self._ro_con()
        try:
            repo = PromotionRepo(con)
            rows = repo.annotate(candidates)
            decisions = repo.list_all()
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Promotions-Sicht nicht lesbar")
            return Response.json(500, {"error": "promotion_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        counts: Dict[str, int] = {s: 0 for s in STORED_STATUSES}
        counts["offen"] = 0
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1

        return Response.json(200, {
            "candidate_count": len(candidates),
            "counts": counts,
            "statuses": list(STORED_STATUSES),
            "candidates": rows,
            "decisions": decisions,
        })

    def _promotion_decide(self, person_id: int,
                          payload: Dict[str, Any]) -> Response:
        """
        POST /api/promotion/decide — {subject_id, status, grund?, herkunft?}.
        Recht 'ops.promote' (auditiert). Der Kandidat MUSS aktuell gueltig sein
        (Scan liefert allowed_uids) — die Zustandsmaschine erzwingt zulaessige
        Uebergaenge, das Repo die Grund-Pflicht.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_OPS_PROMOTE):
            return self._forbidden(CAP_OPS_PROMOTE)

        try:
            subject_id = int(payload.get("subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "subject_id fehlt/ungueltig."})
        status = str(payload.get("status", ""))
        grund = str(payload.get("grund", "") or "")
        herkunft = payload.get("herkunft")
        if herkunft is not None:
            herkunft = str(herkunft)

        try:
            allowed = self._storage_candidates()
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Kandidaten-Scan (data/) fehlgeschlagen")
            return Response.json(500, {"error": "promotion_scan_failed",
                                       "detail": str(exc)})

        con = self._rw_con()
        try:
            repo = PromotionRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.record_decision(
                subject_id=subject_id, target_status=status, grund=grund,
                herkunft=herkunft, actor_id=person_id, allowed_uids=allowed)
        except PromotionError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Promotions-Entscheidung fehlgeschlagen")
            return Response.json(500, {"error": "promotion_decide_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    # ============================================================
    # AUDIT-/REVISIONS-EXPLORER (Build 467, AP-2E, Idee 24) — REIN LESEND
    # ------------------------------------------------------------
    #   Durchblaetterbarer, filterbarer Zugriff auf den append-only audit_log
    #   (dieselbe Belegkette wie die Integritaets-Sicht) + gerichtsfester Export
    #   ueber das AP-2B-ExportEnvelope. Recht: ops.view (wie 'integrity'). Kein
    #   Schreibpfad; das Ansehen wird — wie Integritaets-/Policy-Sicht — nicht
    #   auditiert.
    # ============================================================
    #: Obergrenze der Export-Zeilen (Schutz vor Riesen-Exporten; bei mehr
    #: Treffern weist der Export "Auszug" aus — kein stiller Abschnitt, GR1).
    _AUDIT_EXPORT_MAX = 2000

    def _audit_filters(self, query) -> Dict[str, Any]:
        """Filter-Kwargs aus der Query (event_type ist MEHRFACH zulaessig)."""
        events = None
        if isinstance(query, dict):
            events = query.get("event_type") or None
        return {
            "event_types": events,
            "actor_id": self._q1(query, "actor_id"),
            "target_type": self._q1(query, "target_type"),
            "target_id": self._q1(query, "target_id"),
            "seq_from": self._q1(query, "seq_from"),
            "seq_to": self._q1(query, "seq_to"),
            "ts_from": self._q1(query, "ts_from"),
            "ts_to": self._q1(query, "ts_to"),
        }

    @staticmethod
    def _audit_filter_summary(f: Dict[str, Any]) -> str:
        parts = []
        if f.get("event_types"):
            parts.append("Ereignis=%s" % ",".join(f["event_types"]))
        for key, lbl in (("actor_id", "Akteur-id"), ("target_type", "Ziel-Typ"),
                         ("target_id", "Ziel-id"), ("seq_from", "seq>="),
                         ("seq_to", "seq<="), ("ts_from", "ts>="),
                         ("ts_to", "ts<=")):
            if f.get(key) not in (None, ""):
                parts.append("%s=%s" % (lbl, f[key]))
        return "; ".join(parts) if parts else ""

    def _audit(self, person_id: int, query) -> Response:
        """GET /api/audit — gefilterte, paginierte Audit-Seite (ops.view)."""
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_OPS_VIEW):
            return self._forbidden(CAP_OPS_VIEW)
        f = self._audit_filters(query)
        con = self._ro_con()
        try:
            res = AuditExplorer(con).query(
                limit=self._q1(query, "limit"),
                offset=self._q1(query, "offset"), **f)
        except AuditExplorerError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Audit-Explorer nicht lesbar")
            return Response.json(500, {"error": "audit_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, res)

    def _audit_facets(self, person_id: int) -> Response:
        """GET /api/audit/facets — vorhandene Event-Typen + Akteure (ops.view)."""
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_OPS_VIEW):
            return self._forbidden(CAP_OPS_VIEW)
        con = self._ro_con()
        try:
            res = AuditExplorer(con).facets()
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Audit-Facetten nicht lesbar")
            return Response.json(500, {"error": "audit_facets_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, res)

    def _audit_export(self, person_id: int, query) -> Response:
        """GET /api/audit/export — gerichtsfestes HTML (ops.view, envelope)."""
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_OPS_VIEW):
            return self._forbidden(CAP_OPS_VIEW)
        f = self._audit_filters(query)
        con = self._ro_con()
        try:
            explorer = AuditExplorer(con)
            res = explorer.query(limit=self._AUDIT_EXPORT_MAX, offset=0, **f)
            person = self._person(con, person_id)
            actor = person.get("system_username") if person else None
            ctx = build_export_context(
                con=con, db_path=self._db_path, actor=actor,
                aktenzeichen="Audit-/Revisions-Auszug")
            out = audit_export.render_html(
                res["rows"], ExportEnvelope(ctx),
                filter_summary=self._audit_filter_summary(f),
                total=res["total"])
        except AuditExplorerError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Audit-Export fehlgeschlagen")
            return Response.json(500, {"error": "audit_export_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.html(200, out["html"])

    # ============================================================
    # EXTERNE FALLFREIGABE (Build 462, AP-2G, Idee 26)
    # ------------------------------------------------------------
    #   Weitergabe eines Falls an einen bestaetigten NRW-Ermittler. Drei
    #   Bedingungen (im Repo erzwungen): AD-ACL (F4, self._ad_directory),
    #   Unbedenklichkeit (Pflicht-Grundlage), auditiert. Lesen: release.view;
    #   Erteilen/Widerrufen: release.grant. Nicht scope-behaftet.
    # ============================================================
    def _release_writer(self, con):
        return CaseReleaseRepo(con, CoordinatorWriter(con, AuditLog(con)),
                               ad=self._ad_directory)

    def _releases(self, person_id: int, query) -> Response:
        """GET /api/releases — Freigaben (optional ?subject_id=, ?status=)."""
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_RELEASE_VIEW):
            return self._forbidden(CAP_RELEASE_VIEW)

        raw_user = self._q1(query, "subject_id")
        status = self._q1(query, "status")
        subject_ids = None
        if raw_user:
            try:
                subject_ids = [int(raw_user)]
            except (TypeError, ValueError):
                return Response.json(400, {"error": "bad_request",
                                           "detail": "subject_id ungueltig."})
        statuses = [status] if status else None

        con = self._ro_con()
        try:
            rows = CaseReleaseRepo(con).list_releases(
                subject_ids=subject_ids, statuses=statuses)
        except CaseReleaseError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Fallfreigaben nicht lesbar")
            return Response.json(500, {"error": "releases_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        counts = {"freigegeben": 0, "widerrufen": 0}
        for r in rows:
            if r["status"] in counts:
                counts[r["status"]] += 1

        return Response.json(200, {
            "count": len(rows),
            "counts": counts,
            "umfang_catalog": list(release_status.umfang_catalog()),
            "recipients": self._ad_directory.members(),
            "ad_group": self._ad_directory.group,
            "releases": rows,
        })

    def _release_grant(self, person_id: int,
                       payload: Dict[str, Any]) -> Response:
        """POST /api/release/grant — {subject_id, recipient_kennung, umfang,
        unbedenklichkeit_grundlage}. Recht release.grant (auditiert)."""
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_RELEASE_GRANT):
            return self._forbidden(CAP_RELEASE_GRANT)

        try:
            subject_id = int(payload.get("subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "subject_id fehlt/ungueltig."})

        con = self._rw_con()
        try:
            res = self._release_writer(con).grant(
                subject_id=subject_id,
                recipient_kennung=str(payload.get("recipient_kennung", "")),
                umfang=str(payload.get("umfang", "")),
                unbedenklichkeit_grundlage=str(
                    payload.get("unbedenklichkeit_grundlage", "")),
                actor_id=person_id,
            )
        except CaseReleaseError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Fallfreigabe fehlgeschlagen")
            return Response.json(500, {"error": "release_grant_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    def _release_revoke(self, person_id: int,
                        payload: Dict[str, Any]) -> Response:
        """POST /api/release/revoke — {release_id, grund}. Recht release.grant."""
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_RELEASE_GRANT):
            return self._forbidden(CAP_RELEASE_GRANT)

        try:
            release_id = int(payload.get("release_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "release_id fehlt/ungueltig."})

        con = self._rw_con()
        try:
            seq = CaseReleaseRepo(
                con, CoordinatorWriter(con, AuditLog(con))).revoke(
                release_id, grund=str(payload.get("grund", "")),
                actor_id=person_id)
        except CaseReleaseError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Widerruf der Fallfreigabe fehlgeschlagen")
            return Response.json(500, {"error": "release_revoke_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "release_id": release_id,
                                   "audit_seq": seq})

    # ============================================================
    # ONBOARDING/OFFBOARDING-CHECKLISTE (Build 464, AP-2G, Idee 31)
    # ------------------------------------------------------------
    #   Personal-/Leitungsfunktion (koppelt AD-Schicht F4 ueber die Person).
    #   Lesen: onboarding.view; Pflegen: onboarding.edit (auditiert). Der SUBJEKT-
    #   Parameter 'person_id' im Payload/Query ist die betroffene Person; der
    #   ACTOR ist die eingeloggte person_id.
    # ============================================================
    def _onboarding(self, actor_person_id: int, query) -> Response:
        """GET /api/onboarding?person_id=N&kind=onboarding|offboarding."""
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_ONBOARDING_VIEW):
            return self._forbidden(CAP_ONBOARDING_VIEW)

        raw = self._q1(query, "person_id")
        kind = self._q1(query, "kind") or "onboarding"
        if not raw:
            return Response.json(400, {"error": "bad_request",
                                       "detail": "person_id erforderlich."})
        try:
            subject_id = int(raw)
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "person_id ungueltig."})
        if not ChecklistStatus.is_valid_kind(kind):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "kind ungueltig."})

        con = self._ro_con()
        try:
            person = self._person(con, subject_id)
            if person is None:
                return Response.json(404, {"error": "unknown_person",
                                           "person_id": subject_id})
            repo = OnboardingRepo(con)
            steps = repo.checklist(subject_id, kind)
            load = repo.open_case_load(subject_id)
        except OnboardingError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Checkliste nicht lesbar")
            return Response.json(500, {"error": "onboarding_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        counts = {"offen": 0, "erledigt": 0, "nicht_zutreffend": 0}
        for s in steps:
            counts[s["status"]] = counts.get(s["status"], 0) + 1

        return Response.json(200, {
            "person_id": subject_id,
            "person": {"display_name": person.get("display_name"),
                       "system_username": person.get("system_username")},
            "kind": kind,
            "kind_label": ChecklistStatus.kind_label(kind),
            "kinds": ["onboarding", "offboarding"],
            "counts": counts,
            "open_case_load": load,
            "steps": steps,
        })

    def _onboarding_step(self, actor_person_id: int,
                         payload: Dict[str, Any]) -> Response:
        """POST /api/onboarding/step — {person_id, kind, step_code, status,
        note?}. Recht onboarding.edit (auditiert)."""
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_ONBOARDING_EDIT):
            return self._forbidden(CAP_ONBOARDING_EDIT)

        try:
            subject_id = int(payload.get("person_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "person_id fehlt/ungueltig."})

        con = self._rw_con()
        try:
            repo = OnboardingRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.set_step(
                person_id=subject_id,
                kind=str(payload.get("kind", "")),
                step_code=str(payload.get("step_code", "")),
                status=str(payload.get("status", "")),
                note=str(payload.get("note", "") or ""),
                actor_id=actor_person_id,
            )
        except OnboardingError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Checklisten-Schritt fehlgeschlagen")
            return Response.json(500, {"error": "onboarding_step_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "person_id": subject_id, **res})

    # ---------------------------------------------------------------- AP-2A
    def _crossref(self, actor_person_id: int, query) -> Response:
        """
        GET /api/crossref — Katalog identifizierter Personen (Konto->reale
        Person), staerkste Konfidenz zuerst. Optional ?subject_id=N liefert
        genau einen Eintrag (404, wenn unbekannt). Recht crossref.view.
        Global, NICHT scope-behaftet (der Katalog ist falluebergreifend und
        erfasst auch Geister ohne Fallpaket).
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_VIEW):
            return self._forbidden(CAP_CROSSREF_VIEW)

        raw = self._q1(query, "subject_id")
        con = self._ro_con()
        try:
            repo = IdentifiedSubjectRepo(con)
            if raw:
                try:
                    sid = int(raw)
                except (TypeError, ValueError):
                    return Response.json(
                        400, {"error": "bad_request",
                              "detail": "subject_id ungueltig."})
                entry = repo.get(sid)
                if entry is None:
                    return Response.json(
                        404, {"error": "unknown_subject", "subject_id": sid})
                return Response.json(200, {"entry": entry})
            return Response.json(200, {"entries": repo.list()})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Kreuzbezug-Katalog nicht lesbar")
            return Response.json(500, {"error": "crossref_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

    def _crossfindings(self, actor_person_id: int, query) -> Response:
        """
        GET /api/crossfindings — REIN LESENDE Meta-Uebersicht der Querfunde
        ("Fund ueber B im Fall A") aus pending_cross_annotations, offene zuerst.
        Optional ?only_open=1 filtert auf noch nicht integrierte Funde. Recht
        crossref.view (gleiche F5-Familie wie der Identitaets-Katalog).
        Duplziert NICHT die automatische Erfassung/den Transport — nur Anzeige.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_VIEW):
            return self._forbidden(CAP_CROSSREF_VIEW)

        raw = self._q1(query, "only_open")
        only_open = str(raw or "").lower() in ("1", "true", "yes", "ja")
        con = self._ro_con()
        try:
            repo = CrossfindingsRepo(con)
            return Response.json(200, {
                "findings": repo.list(only_open=only_open),
                "counts": repo.counts(),
            })
        except CrossrefError as exc:
            # Fehlendes Substrat ist ein Betriebsfehler, kein Leerbefund.
            logger.warning("Querfund-Uebersicht nicht verfuegbar: %s", exc)
            return Response.json(503, {"error": "crossfindings_unavailable",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Querfund-Uebersicht nicht lesbar")
            return Response.json(500, {"error": "crossfindings_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

    def _crossref_set(self, actor_person_id: int,
                      payload: Dict[str, Any]) -> Response:
        """
        POST /api/crossref/set — {subject_id, real_identity, confidence_code,
        basis?, note?}. Legt eine Zuordnung an ODER revidiert die bestehende
        (je subject_id genau ein Eintrag), auditiert. Recht crossref.edit.
        Die Sensibilitaetsregel (Freitext nie im Audit-Payload) liegt im Repo;
        der Endpunkt reicht nur durch. Ein No-Op (identische Werte) -> 400.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_EDIT):
            return self._forbidden(CAP_CROSSREF_EDIT)

        try:
            subject_id = int(payload.get("subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "subject_id fehlt/ungueltig."})

        note_raw = payload.get("note")
        con = self._rw_con()
        try:
            repo = IdentifiedSubjectRepo(
                con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.upsert(
                subject_id=subject_id,
                real_identity=str(payload.get("real_identity", "") or ""),
                confidence_code=str(payload.get("confidence_code", "") or ""),
                basis=str(payload.get("basis", "") or ""),
                note=(None if note_raw is None else str(note_raw)),
                actor_id=actor_person_id,
            )
        except CrossrefError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Kreuzbezug-Eintrag fehlgeschlagen")
            return Response.json(500, {"error": "crossref_set_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    def _external_scope(self, person_id: int, capability: str):
        policy = self.resolve_policy(person_id)
        if not policy.can(capability):
            return None, self._forbidden(capability)
        if policy.scope(capability) == "alle":
            return None, None

        con = self._ro_con()
        try:
            rows = con.execute(
                "SELECT subject_id FROM cases WHERE assigned_to = ?",
                (person_id,)).fetchall()
        finally:
            con.close()
        return [int(r[0]) for r in rows], None

    @staticmethod
    def _external_allowed(case_ids, subject_id: int) -> bool:
        """None = alle erlaubt; sonst muss der Fall in der Liste stehen."""
        return case_ids is None or int(subject_id) in case_ids

    def _external(self, person_id: int, query) -> Response:
        """
        GET /api/external — Vorgaenge mit Ampel. Optional ?offen=1, ?status=,
        ?subject_id=, ?stichtag= (Vorschau/Test).
        """
        case_ids, denied = self._external_scope(person_id, CAP_EXTERNAL_VIEW)
        if denied is not None:
            return denied

        # Query IMMER ueber _q1 lesen: der Server liefert parse_qs-Listen.
        offen = self._q1(query, "offen")
        status = self._q1(query, "status")
        raw_user = self._q1(query, "subject_id")
        raw_stichtag = self._q1(query, "stichtag")

        statuses = None
        if offen:
            statuses = list(OPEN_STATUSES)
        elif status:
            statuses = [status]

        if raw_user:
            try:
                one = int(raw_user)
            except (TypeError, ValueError):
                return Response.json(400, {"error": "bad_request",
                                           "detail": "subject_id ungueltig."})
            if not self._external_allowed(case_ids, one):
                return Response.json(403, {
                    "error": "forbidden", "capability": CAP_EXTERNAL_VIEW,
                    "detail": "Fall %s ist nicht zugewiesen." % one})
            case_ids = [one]

        info = (stichtag_mod.heute() if not raw_stichtag
                else {"stichtag": raw_stichtag, "zeitzone": "vorgegeben",
                      "warnung": None})

        con = self._ro_con()
        try:
            repo = ExternalMattersRepo(con)
            rows = repo.list_matters(subject_ids=case_ids, statuses=statuses)
            rows = repo.with_ampel(rows, info["stichtag"])
        except (ExternalMattersError, MatterStatusError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Externe Vorgaenge nicht lesbar")
            return Response.json(500, {"error": "external_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        counts = {"rot": 0, "gelb": 0, "gruen": 0, "neutral": 0}
        for r in rows:
            if r["ampel"] in counts:
                counts[r["ampel"]] += 1

        return Response.json(200, {
            "scope": ("eigene" if case_ids is not None else "alle"),
            "stichtag": info["stichtag"],
            "zeitzone": info.get("zeitzone"),
            "stichtag_text": stichtag_mod.stichtag_text(info),
            "kinds": list(matter_kinds.catalog()),
            "count": len(rows),
            "counts": counts,
            "matters": rows,
        })

    def _calendar(self, person_id: int, query) -> Response:
        """
        GET /api/calendar?von=&bis= — die GEMEINSAME Sicht ueber alle
        Zeitquellen. Die Rechte prueft jede Quelle selbst; fehlt eine, sagt
        sie es (Feld 'hinweise') — ein stiller Leer-Kalender waere gefaehrlich.
        """
        von = self._q1(query, "von")
        bis = self._q1(query, "bis")
        if not von or not bis:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "von und bis (YYYY-MM-DD) sind erforderlich."})

        policy = self.resolve_policy(person_id)
        con = self._ro_con()
        try:
            result = CalendarRepo(con, policy).view(
                von=von, bis=bis, stichtag=self._q1(query, "stichtag"))
        except (CalendarError, MatterStatusError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Kalender nicht lesbar")
            return Response.json(500, {"error": "calendar_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, result)

    # ---------------------------------------------------- Schreiben (extern)
    def _external_writer(self, con):
        return ExternalMattersRepo(con, CoordinatorWriter(con, AuditLog(con)))

    def _external_guard(self, person_id: int, payload, *, need_id: bool):
        """
        Gemeinsame Vorpruefung aller Schreibpfade:
        Recht + Scope + (bei Aenderungen) Zugehoerigkeit des Vorgangs zum
        erlaubten Fall. -> (case_ids, matter_id|None, None) | (None, None, Response)
        """
        case_ids, denied = self._external_scope(person_id, CAP_EXTERNAL_EDIT)
        if denied is not None:
            return None, None, denied
        if not need_id:
            return case_ids, None, None

        try:
            matter_id = int(payload.get("matter_id"))
        except (TypeError, ValueError):
            return None, None, Response.json(400, {
                "error": "bad_request", "detail": "matter_id fehlt/ungueltig."})

        con = self._ro_con()
        try:
            row = con.execute(
                "SELECT subject_id FROM external_matters WHERE id = ?",
                (matter_id,)).fetchone()
        finally:
            con.close()
        if row is None:
            return None, None, Response.json(
                400, {"error": "unknown_matter", "matter_id": matter_id})
        if not self._external_allowed(case_ids, row[0]):
            return None, None, Response.json(403, {
                "error": "forbidden", "capability": CAP_EXTERNAL_EDIT,
                "detail": "Fall %s ist nicht zugewiesen." % row[0]})
        return case_ids, matter_id, None

    def _external_create(self, person_id: int,
                         payload: Dict[str, Any]) -> Response:
        case_ids, _mid, denied = self._external_guard(person_id, payload,
                                                      need_id=False)
        if denied is not None:
            return denied
        try:
            subject_id = int(payload.get("subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "subject_id fehlt/ungueltig."})
        if not self._external_allowed(case_ids, subject_id):
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_EXTERNAL_EDIT,
                "detail": "Fall %s ist nicht zugewiesen." % subject_id})

        con = self._rw_con()
        try:
            res = self._external_writer(con).create(
                subject_id=subject_id,
                kind=str(payload.get("kind", "")),
                betreff=str(payload.get("betreff", "")),
                angefordert_am=str(payload.get("angefordert_am")
                                   or stichtag_mod.heute()["stichtag"]),
                wiedervorlage_am=str(payload.get("wiedervorlage_am", "")),
                adressat=str(payload.get("adressat", "")),
                aktenzeichen=payload.get("aktenzeichen"),
                vorwarnfrist_tage=payload.get("vorwarnfrist_tage", 7),
                actor_id=person_id,
            )
        except (ExternalMattersError, MatterStatusError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Anlage eines externen Vorgangs fehlgeschlagen")
            return Response.json(500, {"error": "create_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    def _external_defer(self, person_id: int,
                        payload: Dict[str, Any]) -> Response:
        _c, matter_id, denied = self._external_guard(person_id, payload,
                                                     need_id=True)
        if denied is not None:
            return denied
        con = self._rw_con()
        try:
            seq = self._external_writer(con).defer(
                matter_id,
                wiedervorlage_am=str(payload.get("wiedervorlage_am", "")),
                grund=str(payload.get("grund", "")),
                vorwarnfrist_tage=payload.get("vorwarnfrist_tage"),
                actor_id=person_id,
            )
        except (ExternalMattersError, MatterStatusError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Wiedervorlage konnte nicht verschoben werden")
            return Response.json(500, {"error": "defer_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "matter_id": matter_id,
                                   "audit_seq": seq})

    def _external_answer(self, person_id: int,
                         payload: Dict[str, Any]) -> Response:
        _c, matter_id, denied = self._external_guard(person_id, payload,
                                                     need_id=True)
        if denied is not None:
            return denied
        con = self._rw_con()
        try:
            seq = self._external_writer(con).answer(
                matter_id,
                ergebnis=str(payload.get("ergebnis", "")),
                wiedervorlage_am=payload.get("wiedervorlage_am"),
                actor_id=person_id,
            )
        except (ExternalMattersError, MatterStatusError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Antwort konnte nicht erfasst werden")
            return Response.json(500, {"error": "answer_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "matter_id": matter_id,
                                   "audit_seq": seq})

    def _external_close(self, person_id: int,
                        payload: Dict[str, Any]) -> Response:
        """ENDGUELTIGER Abschluss. Es gibt bewusst keinen Weg zurueck."""
        _c, matter_id, denied = self._external_guard(person_id, payload,
                                                     need_id=True)
        if denied is not None:
            return denied
        con = self._rw_con()
        try:
            seq = self._external_writer(con).close(
                matter_id,
                status=str(payload.get("status", "")),
                ergebnis=str(payload.get("ergebnis", "")),
                actor_id=person_id,
            )
        except (ExternalMattersError, MatterStatusError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Abschluss fehlgeschlagen")
            return Response.json(500, {"error": "close_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "matter_id": matter_id,
                                   "audit_seq": seq})

    # ================================================================
    # ERMITTLUNGSERGEBNIS-BEWERTUNG (Build 387)
    # ----------------------------------------------------------------
    # Scope-Aufloesung wie bei den externen Vorgaengen:
    #   (None,  None)     -> 'alle': alle Faelle
    #   (Liste, None)     -> 'eigene': genau diese (ggf. LEER)
    #   (None,  Response) -> kein Recht: 403
    # Ein Ermittler ohne Zuweisung bekommt eine LEERE LISTE, NICHT 'alle'.
    # ================================================================
    def _results_scope(self, person_id: int, capability: str):
        policy = self.resolve_policy(person_id)
        if not policy.can(capability):
            return None, self._forbidden(capability)
        if policy.scope(capability) == "alle":
            return None, None
        con = self._ro_con()
        try:
            rows = con.execute(
                "SELECT subject_id FROM cases WHERE assigned_to = ?",
                (person_id,)).fetchall()
        finally:
            con.close()
        return [int(r[0]) for r in rows], None

    def _results_catalog(self, person_id: int) -> Response:
        """
        GET /api/results/catalog — Kriterien, Skalen, Skalenpunkte.
        Der Katalog ist DATEN (M011), kein Code — die Erfassungsmaske baut
        ihre Auswahlfelder daraus. 'catalog_version' gehoert in JEDE spaetere
        Bewertung.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_RESULTS_VIEW):
            return self._forbidden(CAP_RESULTS_VIEW)
        con = self._ro_con()
        try:
            data = AssessmentCatalogRepo(con).full()
        except CatalogError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Bewertungs-Katalog nicht lesbar")
            return Response.json(500, {"error": "catalog_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        data["can_edit"] = policy.can(CAP_RESULTS_EDIT)
        return Response.json(200, data)

    def _results(self, person_id: int, query) -> Response:
        """
        GET /api/results?subject_id=N — AKTUELLER Stand + VOLLE HISTORIE + die
        provisorische Kennzahl.

        Die Historie wird bewusst MITGELIEFERT: sie belegt den Erkenntnis-
        gewinn und ist damit selbst ein Ermittlungsergebnis (append-only, mc).
        """
        case_ids, denied = self._results_scope(person_id, CAP_RESULTS_VIEW)
        if denied is not None:
            return denied

        try:
            subject_id = int(self._q1(query, "subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "subject_id fehlt/ungueltig."})
        if case_ids is not None and subject_id not in case_ids:
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_RESULTS_VIEW,
                "detail": "Fall %s ist nicht zugewiesen." % subject_id})

        con = self._ro_con()
        try:
            repo = ResultsRepo(con)
            cat = AssessmentCatalogRepo(con)
            current = repo.current(subject_id)
            history = repo.history(subject_id)
            alle = [c["code"] for c in cat.criteria()]
            score = PriorityScorer().score_with_gaps(current, alle)
            catver = cat.version()
        except (ResultsError, CatalogError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Bewertungen nicht lesbar")
            return Response.json(500, {"error": "results_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        return Response.json(200, {
            "subject_id": subject_id,
            "scope": ("eigene" if case_ids is not None else "alle"),
            "catalog_version": catver,
            "current": current,
            "history": history,
            "score": score,
            "can_edit": self.resolve_policy(person_id).can(CAP_RESULTS_EDIT),
        })

    def _results_stats(self, person_id: int) -> Response:
        """
        GET /api/results/stats — fallUEBERGREIFENDE Auswertung.

        Verlangt ausdruecklich Scope 'alle' (mc): die statistische Bewertung
        ueber fremde Faelle hat eine ANDERE Qualitaet als der Blick auf den
        eigenen. Ein Ermittler mit 'eigene' bekommt hier 403 — nicht etwa eine
        stillschweigend auf ihn zusammengeschrumpfte Statistik, die wie eine
        Gesamtauswertung aussaehe.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_RESULTS_VIEW):
            return self._forbidden(CAP_RESULTS_VIEW)
        if policy.scope(CAP_RESULTS_VIEW) != "alle":
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_RESULTS_VIEW,
                "detail": "Die fallUEBERGREIFENDE Auswertung erfordert Scope "
                          "'alle'."})

        con = self._ro_con()
        try:
            st = ResultsRepo(con).stats()
            cat = AssessmentCatalogRepo(con).full()
            # Build 393: 'faelle' zaehlt nur die BEWERTETEN Faelle (die Sicht
            # v_investigation_current kennt keine anderen). Ohne die
            # Gesamtzahl daneben liest sich das wie eine Vollerhebung. Die
            # Differenz IST der Befund — sie wird ausdruecklich ausgewiesen.
            gesamt = int(con.execute(
                "SELECT COUNT(*) FROM cases").fetchone()[0])
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Bewertungs-Statistik fehlgeschlagen")
            return Response.json(500, {"error": "stats_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        st["faelle_gesamt"] = gesamt
        st["faelle_unbewertet"] = max(0, gesamt - int(st.get("faelle", 0)))
        st["catalog"] = cat
        # Die Semantik-Warnung wandert MIT: 'ordinal' bedeutet bei
        # abuser_quality SCHWERE, bei location_quality PRAEZISION. Wer diese
        # Zahlen ueber Skalen hinweg addiert, addiert Aepfel und Birnen.
        st["hinweis"] = (
            "Mittelwerte werden je KRITERIUM gebildet, nie ueber Kriterien "
            "hinweg: 'ordinal' misst je nach Skala Praezision ODER Schwere "
            "(siehe quality_beschreibung).")
        return Response.json(200, st)

    def _results_coverage(self, person_id: int, query) -> Response:
        """
        GET /api/results/coverage — ABDECKUNG JE FALL, inklusive der NIE
        BEWERTETEN.

        Warum ein eigener Endpunkt und nicht ein Feld in /stats:
        /stats liest aus v_investigation_current und sieht damit NUR Faelle mit
        mindestens einer Bewertung. Ein Fall, den niemand angefasst hat, ist
        dort UNSICHTBAR — nicht als Luecke gezeigt, sondern schlicht nicht da.
        Genau diese Faelle sind aber die BLINDEN FLECKEN, nach denen die
        Chef-Ermittlerin sucht. CoverageRepo geht deshalb von 'cases' AUS und
        joint die Bewertungen LINKS an (Build 393).

        Scope: 'alle' -> alle Faelle; 'eigene' -> die zugewiesenen. Anders als
        /stats gibt es hier KEIN 403 fuer 'eigene': "wie vollstaendig habe ICH
        meine Faelle bewertet" ist eine legitime Eigenfrage (mc 2026-07-12).
        """
        case_ids, denied = self._results_scope(person_id, CAP_RESULTS_VIEW)
        if denied is not None:
            return denied

        con = self._ro_con()
        try:
            repo = CoverageRepo(con)
            cov = repo.coverage(subject_ids=case_ids)
            cov["summary"] = repo.summary(cov)
            cov["scope"] = ("eigene" if case_ids is not None else "alle")
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Abdeckung nicht lesbar")
            return Response.json(500, {"error": "coverage_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, cov)

    def _results_assess(self, person_id: int,
                        payload: Dict[str, Any]) -> Response:
        """
        POST /api/results/assess — eine Bewertung erfassen.
        APPEND-ONLY: immer eine NEUE Zeile, nie ein Ueberschreiben.
        """
        case_ids, denied = self._results_scope(person_id, CAP_RESULTS_EDIT)
        if denied is not None:
            return denied
        try:
            subject_id = int(payload.get("subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "subject_id fehlt/ungueltig."})
        if case_ids is not None and subject_id not in case_ids:
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_RESULTS_EDIT,
                "detail": "Fall %s ist nicht zugewiesen." % subject_id})

        con = self._rw_con()
        try:
            repo = ResultsRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.assess(
                subject_id=subject_id,
                criterion_code=str(payload.get("criterion_code", "")),
                extrem=str(payload.get("extrem", "")),
                confidence_code=str(payload.get("confidence_code", "")),
                quality_code=(payload.get("quality_code") or None),
                note=str(payload.get("note", "")),
                actor_id=person_id,
            )
        except (ResultsError, CatalogError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Bewertung fehlgeschlagen")
            return Response.json(500, {"error": "assess_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    # -------------------------------------------------- Betreuungs-Notizen (401)
    def _mentoring_notes(self, person_id: int, query) -> Response:
        """
        GET /api/mentoring/notes — die Betreuungs-Notizen ("Post-its").

        Sichtbarkeit: PRIVATES Board pro Autor:in. Nur wer Scope 'alle' hat
        (Vertretung/Aufsicht), darf fremde Boards sehen und kann per ?owner_id=
        gezielt eines waehlen; ohne Angabe sieht 'alle' saemtliche Boards.
        Alle uebrigen sehen ausschliesslich ihr EIGENES Board (owner_id =
        person_id) — Zweckbindung/Kapselung, default restriktiv.

        Optionale Feinfilter (serverseitig): ?archived=1, ?status=, ?color=,
        ?tag=, ?subject= (subject_person_id).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_MENTORING_NOTES_VIEW):
            return self._forbidden(CAP_MENTORING_NOTES_VIEW)
        scope = policy.scope(CAP_MENTORING_NOTES_VIEW)  # 'alle' | 'eigene' | None

        # owner_id-Auswahl: nur Scope 'alle' darf ein FREMDES Board waehlen.
        owner_filter: Optional[int] = person_id
        if scope == "alle":
            raw_owner = self._q1(query, "owner_id")
            if raw_owner:
                try:
                    owner_filter = int(raw_owner)
                except (TypeError, ValueError):
                    return Response.json(400, {
                        "error": "bad_request",
                        "detail": "owner_id ungueltig."})
            else:
                owner_filter = None  # alle Boards

        archived = bool(self._q1(query, "archived"))
        status = self._q1(query, "status")
        color = self._q1(query, "color")
        tag = self._q1(query, "tag")
        raw_subject = self._q1(query, "subject")
        subject = None
        if raw_subject:
            try:
                subject = int(raw_subject)
            except (TypeError, ValueError):
                return Response.json(400, {
                    "error": "bad_request", "detail": "subject ungueltig."})

        con = self._ro_con()
        try:
            repo = MentoringNotesRepo(con)
            notes = repo.list_notes(
                owner_id=owner_filter, archived=archived, status=status,
                color=color, tag=tag, subject_person_id=subject)
            # Personenliste fuer die Mitarbeiter-Auswahl im Editor (Feld
            # 'Betroffene:r'). Reiner Lesezugriff; nur id + Anzeigename, kein
            # weiteres Personendetail (Datensparsamkeit).
            persons = [
                {"id": int(r["id"]), "display_name": r["display_name"]}
                for r in con.execute(
                    "SELECT id, display_name FROM person ORDER BY display_name")
            ]
        except MentoringNotesError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Betreuungs-Notizen nicht lesbar")
            return Response.json(500, {"error": "notes_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        items = [n.to_json() for n in notes]
        return Response.json(200, {
            "scope": ("alle" if scope == "alle" else "eigene"),
            "owner_id": owner_filter,
            "archived": archived,
            "colors": note_colors.catalog(),
            "persons": persons,
            "count": len(items),
            "notes": items,
        })

    # -------------------------------------- Betreuungs-Notizen: Schreiben (405)
    #   Die Schreibpfade sind der ZWEITE Baustein (Block 2). Muster exakt wie die
    #   externen Vorgaenge: Recht (mentoring_notes.edit) + Scope -> Eigentums-
    #   pruefung -> Repo ueber CoordinatorWriter (jede AEnderung auditiert). Der
    #   Token-Check (X-AIW-Token) liegt im HTTP-Handler VOR dispatch_write.
    def _notes_writer(self, con: sqlite3.Connection) -> MentoringNotesRepo:
        return MentoringNotesRepo(con, CoordinatorWriter(con, AuditLog(con)))

    def _notes_edit_scope(self, person_id: int):
        """
        Prueft das Schreibrecht. -> (scope, None) | (None, Response).
        scope: 'alle' (Vertretung/Aufsicht darf fremde Boards pflegen) |
        'eigene'/None (nur das eigene Board).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_MENTORING_NOTES_EDIT):
            return None, self._forbidden(CAP_MENTORING_NOTES_EDIT)
        return policy.scope(CAP_MENTORING_NOTES_EDIT), None

    def _note_id_from(self, payload: Dict[str, Any]):
        """Validiert die Notiz-ID. -> (note_id, None) | (None, Response)."""
        try:
            return int(payload.get("id")), None
        except (TypeError, ValueError):
            return None, Response.json(400, {
                "error": "bad_request", "detail": "id fehlt/ungueltig."})

    def _may_edit_note(self, repo: MentoringNotesRepo, note_id: int,
                       person_id: int, scope):
        """
        Eigentumspruefung: wer NICHT Scope 'alle' hat, darf nur das EIGENE
        Board aendern. -> None (erlaubt) | Response (404/403).
        """
        rec = repo.get(note_id)
        if rec is None:
            return Response.json(404, {"error": "not_found",
                                       "note_id": note_id})
        if scope != "alle" and rec.owner_id != person_id:
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_MENTORING_NOTES_EDIT,
                "detail": "Fremdes Board (Scope 'alle' erforderlich)."})
        return None

    def _note_create(self, person_id: int,
                     payload: Dict[str, Any]) -> Response:
        scope, denied = self._notes_edit_scope(person_id)
        if denied is not None:
            return denied
        # owner_id = eigene Person; nur Scope 'alle' darf ein FREMDES Board
        # bestuecken (z. B. Vertretung legt fuer die Chefin an).
        owner_id = person_id
        if scope == "alle" and payload.get("owner_id") is not None:
            try:
                owner_id = int(payload["owner_id"])
            except (TypeError, ValueError):
                return Response.json(400, {"error": "bad_request",
                                           "detail": "owner_id ungueltig."})

        tags = payload.get("tags")
        if tags is not None and not isinstance(tags, list):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "tags muss eine Liste sein."})

        con = self._rw_con()
        try:
            res = self._notes_writer(con).create(
                owner_id=owner_id,
                title=str(payload.get("title", "")),
                body=str(payload.get("body", "") or ""),
                color=str(payload.get("color", note_colors.DEFAULT_COLOR)),
                status=str(payload.get("status", "offen")),
                pinned=bool(payload.get("pinned", False)),
                subject_person_id=payload.get("subject_person_id"),
                tags=tags,
                actor_id=person_id,
            )
        except MentoringNotesError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Anlage einer Betreuungs-Notiz fehlgeschlagen")
            return Response.json(500, {"error": "create_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    def _note_update(self, person_id: int,
                     payload: Dict[str, Any]) -> Response:
        scope, denied = self._notes_edit_scope(person_id)
        if denied is not None:
            return denied
        note_id, err = self._note_id_from(payload)
        if err is not None:
            return err

        # Nur ausdruecklich uebergebene Felder aendern: der Repo-Sentinel
        # _UNSET unterscheidet "nicht uebergeben" von "auf null gesetzt".
        # Wir bauen die kwargs allein aus im Payload VORHANDENEN Schluesseln.
        fields = ("title", "body", "color", "status", "pinned",
                  "subject_person_id", "tags")
        kwargs: Dict[str, Any] = {}
        for key in fields:
            if key in payload:
                kwargs[key] = payload[key]
        if "tags" in kwargs and kwargs["tags"] is not None \
                and not isinstance(kwargs["tags"], list):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "tags muss eine Liste sein."})

        con = self._rw_con()
        try:
            repo = self._notes_writer(con)
            forbid = self._may_edit_note(repo, note_id, person_id, scope)
            if forbid is not None:
                return forbid
            seq = repo.update(note_id, actor_id=person_id, **kwargs)
        except MentoringNotesError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("AEnderung einer Betreuungs-Notiz fehlgeschlagen")
            return Response.json(500, {"error": "update_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "note_id": note_id,
                                   "audit_seq": seq})

    def _note_archive(self, person_id: int,
                      payload: Dict[str, Any]) -> Response:
        return self._note_flag_change(person_id, payload, archive=True)

    def _note_restore(self, person_id: int,
                      payload: Dict[str, Any]) -> Response:
        return self._note_flag_change(person_id, payload, archive=False)

    def _note_flag_change(self, person_id: int, payload: Dict[str, Any], *,
                          archive: bool) -> Response:
        """Gemeinsamer Pfad fuer archive()/restore() (Soft-Delete-Flag)."""
        scope, denied = self._notes_edit_scope(person_id)
        if denied is not None:
            return denied
        note_id, err = self._note_id_from(payload)
        if err is not None:
            return err

        con = self._rw_con()
        try:
            repo = self._notes_writer(con)
            forbid = self._may_edit_note(repo, note_id, person_id, scope)
            if forbid is not None:
                return forbid
            if archive:
                seq = repo.archive(note_id, actor_id=person_id)
            else:
                seq = repo.restore(note_id, actor_id=person_id)
        except MentoringNotesError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Archiv-Statuswechsel fehlgeschlagen")
            return Response.json(500, {"error": "archive_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "note_id": note_id,
                                   "audit_seq": seq})

    def _note_duplicate(self, person_id: int,
                        payload: Dict[str, Any]) -> Response:
        scope, denied = self._notes_edit_scope(person_id)
        if denied is not None:
            return denied
        note_id, err = self._note_id_from(payload)
        if err is not None:
            return err

        con = self._rw_con()
        try:
            repo = self._notes_writer(con)
            # Dupliziert wird auf DASSELBE Board wie das Original — der
            # Aufrufer muss dieses Board pflegen duerfen.
            forbid = self._may_edit_note(repo, note_id, person_id, scope)
            if forbid is not None:
                return forbid
            res = repo.duplicate(note_id, actor_id=person_id)
        except MentoringNotesError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Duplizieren einer Betreuungs-Notiz fehlgeschlagen")
            return Response.json(500, {"error": "duplicate_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    def _note_reorder(self, person_id: int,
                      payload: Dict[str, Any]) -> Response:
        scope, denied = self._notes_edit_scope(person_id)
        if denied is not None:
            return denied
        # owner_id des umzusortierenden Boards: eigenes, bei Scope 'alle' auch
        # ein fremdes (dann explizit anzugeben).
        owner_id = person_id
        if payload.get("owner_id") is not None:
            try:
                owner_id = int(payload["owner_id"])
            except (TypeError, ValueError):
                return Response.json(400, {"error": "bad_request",
                                           "detail": "owner_id ungueltig."})
            if scope != "alle" and owner_id != person_id:
                return Response.json(403, {
                    "error": "forbidden",
                    "capability": CAP_MENTORING_NOTES_EDIT,
                    "detail": "Fremdes Board (Scope 'alle' erforderlich)."})

        ids = payload.get("ids")
        if not isinstance(ids, list):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "ids muss eine Liste sein."})
        try:
            ids = [int(i) for i in ids]
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "ids muss eine Liste von Ganzzahlen sein."})

        con = self._rw_con()
        try:
            seq = self._notes_writer(con).reorder(
                owner_id, ids, actor_id=person_id)
        except MentoringNotesError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Umsortieren des Boards fehlgeschlagen")
            return Response.json(500, {"error": "reorder_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "owner_id": owner_id,
                                   "count": len(ids), "audit_seq": seq})

    def _require_assignment_scope(self, person_id: int):
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_ASSIGNMENT):
            return self._forbidden(CAP_ASSIGNMENT)
        if policy.scope(CAP_ASSIGNMENT) != "alle":
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_ASSIGNMENT,
                "detail": "Diese Aktion erfordert Scope 'alle'."})
        return None

    def dispatch_write(self, person_id: int, path: str,
                       payload: Optional[Dict[str, Any]]) -> Response:
        """
        Loest einen POST-Schreibzugriff auf. NUR die hier gelisteten Routen
        sind schreibfaehig; alles andere -> 404 (der Handler weist zudem
        fremde Methoden mit 405 ab). Der Token-Check erfolgt VOR diesem Aufruf
        im Handler.
        """
        if not isinstance(payload, dict):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "JSON-Objekt als Rumpf erwartet."})

        if path == "/api/case/assign":
            return self._case_assign(person_id, payload)
        if path == "/api/case/priority":
            return self._case_priority(person_id, payload)
        if path == "/api/case/status":
            return self._case_status(person_id, payload)
        if path == "/api/report/approve":
            return self._report_approve(person_id, payload)
        if path == "/api/report/return":
            return self._report_return(person_id, payload)
        if path == "/api/cases/import":
            return self._cases_import(person_id, payload)
        if path == "/api/external/create":
            return self._external_create(person_id, payload)
        if path == "/api/external/defer":
            return self._external_defer(person_id, payload)
        if path == "/api/external/answer":
            return self._external_answer(person_id, payload)
        if path == "/api/external/close":
            return self._external_close(person_id, payload)
        if path == "/api/results/assess":
            return self._results_assess(person_id, payload)
        # Build 460 (AP-2G): Fremdforum-Promotion — auditierte Entscheidung.
        if path == "/api/promotion/decide":
            return self._promotion_decide(person_id, payload)
        # Build 462 (AP-2G): Externe Fallfreigabe — auditiert (AD-ACL + Unbedenkl.)
        if path == "/api/release/grant":
            return self._release_grant(person_id, payload)
        if path == "/api/release/revoke":
            return self._release_revoke(person_id, payload)
        # Build 464 (AP-2G): Onboarding/Offboarding-Checkliste — auditiert.
        if path == "/api/onboarding/step":
            return self._onboarding_step(person_id, payload)
        # Build 470 (AP-2A): Katalog identifizierter Personen — auditiert.
        if path == "/api/crossref/set":
            return self._crossref_set(person_id, payload)
        # Build 412 (SF-3): Lektorat/Chef-Kommentare (Addendum-Dateien).
        if path == "/api/report/comment":
            return self._report_comment_create(person_id, payload)
        if path == "/api/report/comment/resolve":
            return self._report_comment_resolve(person_id, payload)
        # Build 422 (W2): Platzhalter-Query anlegen/aendern (templates.db).
        if path == "/api/templates/query":
            return self._templates_query_upsert(person_id, payload)
        # Build 423 (W2-Frontend): schreibfreie Vorschau (Validierung + fdb-
        # Dry-Run), damit die Redakteur:in testen kann, BEVOR sie speichert.
        if path == "/api/templates/query/dryrun":
            return self._templates_query_dryrun(person_id, payload)
        # Build 424 (W3): Dokumentvorlagen (report_templates) anlegen/aendern
        # und schreibfreie Struktur-Vorschau.
        if path == "/api/templates/document":
            return self._templates_document_upsert(person_id, payload)
        if path == "/api/templates/document/dryrun":
            return self._templates_document_dryrun(person_id, payload)
        # Build 426 (W1): Baustein-Module (report_modules) anlegen/aendern und
        # schreibfreie Vorschau (Feldpruefung + Platzhalter-Zaehlung im body).
        if path == "/api/templates/module":
            return self._templates_module_upsert(person_id, payload)
        if path == "/api/templates/module/dryrun":
            return self._templates_module_dryrun(person_id, payload)
        # Build 405 (Block 2): Betreuungs-Notizen — auditierte Schreibpfade.
        if path == "/api/mentoring/note/create":
            return self._note_create(person_id, payload)
        if path == "/api/mentoring/note/update":
            return self._note_update(person_id, payload)
        if path == "/api/mentoring/note/archive":
            return self._note_archive(person_id, payload)
        if path == "/api/mentoring/note/restore":
            return self._note_restore(person_id, payload)
        if path == "/api/mentoring/note/duplicate":
            return self._note_duplicate(person_id, payload)
        if path == "/api/mentoring/note/reorder":
            return self._note_reorder(person_id, payload)
        return Response.json(404, {"error": "not_found", "path": path})

    # ------------------------------------------------------------- Schreiben
    def _case_id(self, con: sqlite3.Connection, payload: Dict[str, Any]):
        """Validiert subject_id und Existenz des Falls. -> (subject_id, None) | (None, Response)"""
        raw = payload.get("subject_id")
        try:
            subject_id = int(raw)
        except (TypeError, ValueError):
            return None, Response.json(400, {
                "error": "bad_request", "detail": "subject_id fehlt/ungueltig."})
        row = con.execute("SELECT 1 FROM cases WHERE subject_id=?",
                          (subject_id,)).fetchone()
        if row is None:
            return None, Response.json(400, {
                "error": "unknown_case", "subject_id": subject_id})
        return subject_id, None

    def _case_assign(self, person_id: int,
                     payload: Dict[str, Any]) -> Response:
        """
        Fall zuweisen oder entziehen. person_id=null -> Zuweisung entziehen.
        Selbstzuweisung ist ausdruecklich erlaubt (wer Scope 'alle' hat, darf
        auch sich selbst zuweisen).
        """
        denied = self._require_assignment_scope(person_id)
        if denied is not None:
            return denied

        target = payload.get("person_id", "__missing__")
        if target == "__missing__":
            return Response.json(400, {
                "error": "bad_request",
                "detail": "person_id erforderlich (null = entziehen)."})

        con = self._rw_con()
        try:
            subject_id, err = self._case_id(con, payload)
            if err is not None:
                return err

            assignee: Optional[int] = None
            if target is not None:
                try:
                    assignee = int(target)
                except (TypeError, ValueError):
                    return Response.json(400, {
                        "error": "bad_request",
                        "detail": "person_id ungueltig."})
                row = con.execute(
                    "SELECT is_investigator FROM person WHERE id=?",
                    (assignee,)).fetchone()
                if row is None:
                    return Response.json(400, {
                        "error": "unknown_person", "person_id": assignee})
                if not row[0]:
                    return Response.json(400, {
                        "error": "not_investigator", "person_id": assignee,
                        "detail": "Person ist kein Ermittler."})

            writer = CoordinatorWriter(con, AuditLog(con))
            seq = CasesRepo(con, writer).assign(
                subject_id, assignee, actor_id=person_id)
        except Exception as exc:  # kein stiller Fehlschlag (Grundregel 1)
            logger.exception("Zuweisung fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        return Response.json(200, {"ok": True, "subject_id": subject_id,
                                   "person_id": assignee, "audit_seq": seq})

    def _case_priority(self, person_id: int,
                       payload: Dict[str, Any]) -> Response:
        denied = self._require_assignment_scope(person_id)
        if denied is not None:
            return denied

        try:
            prio = int(payload.get("priority"))
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request", "detail": "priority fehlt/ungueltig."})
        if not (_PRIORITY_MIN <= prio <= _PRIORITY_MAX):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "priority ausserhalb %d..%d."
                          % (_PRIORITY_MIN, _PRIORITY_MAX)})

        con = self._rw_con()
        try:
            subject_id, err = self._case_id(con, payload)
            if err is not None:
                return err
            writer = CoordinatorWriter(con, AuditLog(con))
            seq = CasesRepo(con, writer).set_priority(
                subject_id, prio, actor_id=person_id)
        except Exception as exc:
            logger.exception("Prioritaet setzen fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "subject_id": subject_id,
                                   "priority": prio, "audit_seq": seq})

    def _case_status(self, person_id: int,
                     payload: Dict[str, Any]) -> Response:
        denied = self._require_assignment_scope(person_id)
        if denied is not None:
            return denied

        status = payload.get("status")
        if status not in _CASE_STATUSES:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "status muss einer von %s sein."
                          % (", ".join(_CASE_STATUSES),)})

        con = self._rw_con()
        try:
            subject_id, err = self._case_id(con, payload)
            if err is not None:
                return err
            writer = CoordinatorWriter(con, AuditLog(con))
            seq = CasesRepo(con, writer).set_status(
                subject_id, status, actor_id=person_id)
        except Exception as exc:
            logger.exception("Status setzen fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "subject_id": subject_id,
                                   "status": status, "audit_seq": seq})
