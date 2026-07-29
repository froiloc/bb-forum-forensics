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
#   500 = FALLSTART AUS DEM PORTAL. NEU POST /api/case/launch: startet den
#         Forensik-Server (main.py --mode cli --subject-id <id> --auto-port
#         --open-browser) fuer einen dem Aufrufer ZUGEWIESENEN Fall. Tor:
#         CAP_MYCASES; serverseitige Eigentuemer-Pruefung (assigned_to==Aufrufer,
#         sonst 403). KEIN DB-Schreibzugriff -> migrationsneutral. Start ueber
#         die gekapselte Klasse management/cases/case_launcher.py (injizierbar).
#   502 = AD-ABGLEICH (Bauplan Build501_502 §7; Kern aus Build 501). NEU
#         GET /api/adsync (Vorschau, rein lesend, mode=ro; Live-AD ueber
#         injizierbaren Provider, PROD lazy LdapGroupReader.from_config),
#         POST /api/adsync/apply (Neuaufnahmen als investigator + Namens-
#         aenderungen; Plan wird SERVERSEITIG frisch gebildet),
#         POST /api/adsync/decide (Einzel-Entscheidung deactivate/abort/
#         reactivate; Bestaetigungswort "Entfernen"/"Reaktivieren" wird
#         SERVERSEITIG geprueft — nie Loeschen, nur is_active=0). Tor fuer
#         alle drei: CAP_PERSONNEL_SYNC (Seed M020, default-deny).
#   503 = PERSONALVERWALTUNG (Bauplan Build503). NEU GET /api/personnel
#         (Liste: Personen + Aktiv-Status + Flags + aktive Rollenzuweisungen +
#         Rollenkatalog; Recht personnel.view, KEIN AD-Zugriff), POST
#         /api/personnel/flags (PersonRepo.update, Diff-Beleg), POST
#         /api/personnel/role/assign|revoke (RbacRepo, ROLE_ASSIGNED/
#         ROLE_REVOKED, Soft-Revoke). Recht personnel.edit (Seed M021).
#         SELBSTSCHUTZ: die eigene Person ist ueber die Oberflaeche
#         unantastbar (Lockout-Schutz; CLI bleibt offen). Die Grants der
#         Rollen-Matrix (rbac_grant) bleiben bewusst CLI-only (policy_admin).
#   522 = PROGNOSEBERICHT (AP-3F / Idee 40). NEU GET /api/forecast/report
#         ?format=pdf|html[&lookback_days=N] — die Backlog-Abbau-Prognose als
#         vorlegbarer Beleg (management/stats/forecast_report.py, HTML und PDF
#         aus DENSELBEN reinen Funktionen). Rechte ABSICHTLICH identisch zu
#         /api/forecast (stats.export_sta + Scope 'alle'): der Bericht zeigt
#         keine Angabe, die die Sicht 'planung' nicht schon zeigt — ein
#         eigenes Recht waere eine zweite Stelle zum Vergessen. Unbekanntes
#         Format -> 400 MIT Nennung der gueltigen Werte (kein stiller
#         Rueckfall auf PDF); fehlendes reportlab -> 503 mit Klartext (kein
#         leeres PDF, kein stiller Formatwechsel). Response bekommt dafuer das
#         additive Feld 'extra_headers' (Content-Disposition) und die Fabrik
#         Response.pdf. Rein lesend, keine Migration.
#   524 = FRISTEN-/VERJAEHRUNGS-MONITOR (AP-3A / Idee 32). NEU GET
#         '/api/limitation[?vorwarn_tage=N]' — je Fall der Fristbeginn aus
#         forensic_<uid>.db (uid_posts.posted / uid_pms_posts.posted_ts,
#         read-only) und die rechnerische Frist nach §§ 78 ff. StGB.
#         EIGENES Recht 'limitation.view' (Seed M031), NICHT scope-
#         behaftet. DIE SICHT STELLT KEINE VERJAEHRUNG FEST — die Antwort
#         traegt 'stellt_keine_verjaehrung_fest' MIT, und der Befund lautet
#         'rechnerisch ueberschritten', nie 'verjaehrt'. UNBESTAETIGTER
#         Parametersatz -> 200 MIT 'aussage_moeglich': false und Grund
#         (Fallliste und Datenlage sind trotzdem vollstaendig da);
#         UNBRAUCHBARER Parametersatz -> 503 (das ist etwas anderes und
#         darf nicht wie ein Bestaetigungsmangel aussehen). Rein lesend,
#         keine Datenaenderung.
# Version: v0.8.524 · Build: 524 · 2026-07-25
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
# Build 534: Sammelzuweisung — viele Faelle in EINER Transaktion, ein
# audit_log-Beleg JE FALL (kein Sammelbeleg).
from management.cases.cases_batch_repo import (
    BatchChange,
    CasesBatchError,
    CasesBatchRepo,
)
# Build 500: Fallstart aus dem Portal — startet main.py fuer einen Fall.
from management.cases.case_launcher import CaseLauncher, CaseLaunchError
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
# Build 534: Kennzahlen je Fall (uid_stats) fuer die Spalten der Zuweisung.
from management.stats.uid_stats_repo import UidStatsRepo
from management.stats.forecast import Forecaster, forecast_to_dict
# Build 524 (AP-3A / Idee 32): Fristen-/Verjaehrungs-Monitor. Der Parametersatz
# wird bei JEDEM Abruf frisch geladen und geprueft — so wirkt eine Bestaetigung
# durch die StA ohne Serverneustart, und ein fehlerhaft geaenderter Satz faellt
# beim naechsten Abruf auf (statt bis zum naechsten Neustart zu wirken).
from management.deadlines.limitation import DEFAULT_VORWARN_TAGE
from management.deadlines.limitation_params import (
    LimitationParamsError,
    load_params,
)
from management.deadlines.limitation_repo import LimitationRepo
# Build 522 (AP-3F / Idee 40): Prognosebericht (3 Szenarien) als HTML/PDF.
# reportlab wird ERST in build_forecast_report_pdf importiert -> dieser Import
# bleibt auch ohne die Bibliothek moeglich; ihr Fehlen meldet der Endpunkt als
# 503 (Muster forensic_api/export.py:219-224).
from management.stats.forecast_report import (
    ForecastReportUnavailable,
    build_forecast_report_html,
    build_forecast_report_pdf,
)
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
# --- Build 558: Kapazitaetspflege ueber die Oberflaeche -----------------
#   Die vier Repos schreiben AUSSCHLIESSLICH ueber CoordinatorWriter
#   (Write + Beleg in EINER Transaktion, audit_seq an der Datenzeile).
#   Sie waren seit Build 355-357 nur ueber capacity_admin.py erreichbar.
from management.capacity.worktime_repo import WorktimeRepo
from management.capacity.availability_repo import AvailabilityRepo
from management.capacity.holiday_repo import HolidayRepo
from management.capacity.reason_repo import ReasonRepo
from management.workload.workload_repo import (
    WorkloadRepo,
    WorkloadSchemaError,
)
# Build 513 (AP-2F/Idee 21: Ueberlastwarnung SICHTBAR machen). Das Read-Model
# aus Build 451 war bis hierher nur ueber die CLI erreichbar — es hatte keinen
# Weg ins Cockpit. Es wird BEWUSST NICHT als eigene Sicht angebunden, sondern in
# die bestehende Lastverteilung ('/api/workload') hineingezogen: die Warnung ist
# eine BEWERTUNG genau der Zahlen, die dort ohnehin stehen. Eine zweite Sicht
# haette dieselben Zahlen ein zweites Mal geholt und koennte — bei zwei
# getrennten Abfragen zu zwei Zeitpunkten — einen ANDEREN Stand zeigen als die
# Sicht daneben. Das waere ein widerspruechlicher Beleg. Deshalb wird der Report
# hier aus DERSELBEN, bereits geladenen Lastliste gebildet (build_report ist
# rein) statt ueber OverloadEvaluator ein zweites Mal zu messen.
from management.workload.overload import (
    build_report as build_overload_report,
    overload_thresholds_from_config,
    overload_to_dict,
    OverloadThresholds,
)
# Build 515 (AP-2G / Idee 23): Eskalationen. Wie bei der Ueberlastwarnung war
# das Read-Model aus Build 453 bis hierher nur ueber die CLI erreichbar.
from management.cases.escalation import (
    escalation_thresholds_from_config,
    escalation_to_dict,
    EscalationThresholds,
)
from management.cases.escalation_repo import EscalationRepo
# Build 519 (AP-2F / Idee 22): Naechstbeste Aktion. Wie bei Ueberlast und
# Eskalation war das Read-Model aus Build 452/469 nur ueber die CLI da.
from management.cases.next_actions import queue_to_dict
from management.cases.next_actions_repo import NextActionsRepo
# Build 520 (AP-2G / Idee 30): Uebergabe-Protokoll. Ebenfalls nur ueber die
# CLI erreichbar gewesen (Build 455/469).
from management.cases.handover_log import handover_to_dict
from management.cases.handover_repo import HandoverRepo
# Build 521 (AP-2G / Idee 29): Aufbewahrungsfristen. Letztes der fuenf
# Read-Models aus Uebergabe 440-453, die nur ueber die CLI erreichbar waren.
from management.ops.retention import (
    retention_thresholds_from_config,
    retention_to_dict,
    RetentionRepo,
    RetentionThresholds,
)
# Build 517 (AP-2G / Idee 23): der auditierte SCHREIBPFAD zur Eskalation
# (Quittierung). Befund Uebergabe 440-453 §3.3 — bis Build 516 war die Sicht
# rein auswertend.
from management.cases.escalation_ack_repo import (
    annotate_items,
    EscalationAckError,
    EscalationAckRepo,
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
# Build 502 (AD-Abgleich, Bauplan Build501_502 §7): Cockpit-Anbindung des in
# Build 501 gebauten Sync-Kerns (zweiter Bedienweg neben der CLI, mc E2).
from management.ad_sync.sync_executor import (
    AdSyncError,
    CONFIRM_DEACTIVATE,
    CONFIRM_REACTIVATE,
    SyncExecutor,
)
from management.ad_sync.sync_plan import AdSyncPlanError
from management.external.ldap_group_reader import LdapError, LdapGroupReader
from management.person.person_repo import PersonError, PersonRepo
# Build 503 (Personalverwaltung): Lesemodell + auditierte Schreibwege der
# Personal-Seite (Flags via PersonRepo, Rollenzuweisungen via RbacRepo).
from management.person.person_overview_repo import PersonOverviewRepo
from management.rbac.rbac_repo import RbacError, RbacRepo
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
# Build 504 (AP-2A, Idee 8): globaler Alias-Katalog. Nutzt die Fehlerklasse
# CrossrefError und die Rechte crossref.view/edit der gleichen F5-Familie mit
# (keine Rechte-Inflation — Entscheidungslinie Build 474 §3).
from management.crossref.subject_alias_repo import ALIAS_KINDS, SubjectAliasRepo
# Build 600 (Oberflaechen-Zweig): Namensaufloesung fuer die Alias-Sicht —
# subject_id <-> Benutzername ueber Fallakte und globale Namensliste.
from management.crossref.name_resolver import NameResolver
# Build 507 (AP-2A, Idee 7): Querfund-Rueckkanal. Die Zustandslogik liegt in
# crossfinding_channel_status.py (reine Logik) — hier wird sie nur verdrahtet.
from management.crossref.crossfinding_channel_repo import (
    CrossfindingChannelRepo,
)
from management.crossref.crossfinding_channel_status import (
    CrossfindingChannelError,
)
# Build 509 (AP-2A, Idee 11): Identitaets-Merge/Split. Gleiche F5-Familie,
# gleiche Rechte crossref.view/edit (keine Rechte-Inflation).
from management.crossref.subject_merge_repo import SubjectMergeRepo
from management.audit.audit_explorer import AuditExplorer, AuditExplorerError
from management.audit import audit_export
from management.export.context_builder import build_export_context
from management.export.export_envelope import ExportEnvelope
# Build 511 (AP-2B/B1): generischer Akten-Export je Cockpit-Sicht. Er liest
# AUSSCHLIESSLICH ueber den bestehenden dispatch() und erbt damit die
# Rechtepruefung der jeweiligen Sicht — es entsteht KEIN zweiter Lesepfad.
from management.export.view_export_catalog import known_view_ids, spec_for
from management.export.view_renderer import ViewExportRenderer, query_summary

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

# Build 502: AD-Abgleich der Ermittlerstammdaten (Seed in M020). EINE
# Faehigkeit fuer Vorschau UND Vollzug: wer abgleichen darf, traegt die
# Leitungsverantwortung dafuer (Grant an 'supervisor' per policy_admin,
# default-deny — die woertliche Bestaetigung "Entfernen"/"Reaktivieren"
# wird ZUSAETZLICH serverseitig je Einzelfall geprueft).
CAP_PERSONNEL_SYNC = "personnel.sync"

# Build 503: Personalverwaltung (Seed in M021). Lesen und Pflegen getrennt;
# die Grants der Rollen-MATRIX (rbac_grant) bleiben der CLI vorbehalten.
CAP_PERSONNEL_VIEW = "personnel.view"
CAP_PERSONNEL_EDIT = "personnel.edit"

# Build 515 (AP-2G / Idee 23): Eskalationen (Seed in M026). BEWUSST NICHT
# scope-behaftet — die Sicht beantwortet die Frage "wo bleibt etwas liegen,
# das NIEMAND anfasst". Auf 'eigene' verengt haette sie genau die Faelle
# ausgeblendet, um derentwillen es sie gibt (die unzugewiesenen), und waere
# damit ein irrefuehrender Beleg. Wer sie nicht sehen soll, bekommt den Grant
# nicht (default-deny). Analogie: CAP_PERSONNEL_SYNC.
CAP_ESCALATION_VIEW = "escalation.view"

# Build 517 (AP-2G / Idee 23): Quittierung (Seed in M027). EIGENE Faehigkeit
# neben escalation.view — wer Eskalationen SEHEN darf, darf damit noch lange
# nicht fuer die Behoerde festhalten, dass etwas gesehen und veranlasst wurde.
# Ein Lese-Grant darf nie ein Schreibrecht mitbringen.
CAP_ESCALATION_ACK = "escalation.ack"

# Build 519 (AP-2F / Idee 22): Naechstbeste Aktion (Seed in M028).
# SCOPE-BEHAFTET, und hier bestimmt der Scope den ZWECK der Sicht:
# 'eigene' = die eigene Arbeitsschlange (Selbstorganisation), 'alle' =
# die der ganzen Dienststelle (Verteilung). Anders als bei
# CAP_ESCALATION_VIEW verengt der Scope hier keinen Beleg, sondern
# beantwortet eine andere Frage.
CAP_NEXTACTIONS_VIEW = "nextactions.view"

# Build 520 (AP-2G / Idee 30): Uebergabe-Protokoll (Seed in M029). NICHT
# scope-behaftet, gleiche Begruendung wie CAP_ESCALATION_VIEW: ein
# Protokoll ueber UEBERGABEN handelt von der Beziehung zwischen
# Personen; auf die eigenen Eintraege verengt entstuende ein Protokoll
# MIT LUECKEN, das vollstaendig aussieht.
CAP_HANDOVER_VIEW = "handover.view"

# Build 521 (AP-2G / Idee 29): Aufbewahrungsfristen (Seed in M030).
# EIGENES Recht statt 'ops.view': die uebrigen ops.view-Sichten zeigen den
# Zustand der ANLAGE, diese eine LISTE VON FAELLEN mit Beschuldigten-
# Kontonamen. Wer die Anlage betreut, braucht diese Namen nicht.
CAP_RETENTION_VIEW = "retention.view"

# Build 524 (AP-3A / Idee 32): Verjaehrungsfristen (Seed in M031). EIGENES
# Recht statt 'ops.view' oder 'dashboard.view': die Sicht zeigt eine Liste von
# Faellen MIT Beschuldigten-Kontonamen UND eine rechtliche Einschaetzung mit
# unumkehrbarer Folge zusammen. NICHT scope-behaftet (wie CAP_ESCALATION_VIEW):
# auf 'eigene' verengt haette sie genau die Faelle nicht gezeigt, um
# derentwillen es sie gibt — die unzugewiesenen, bei denen die Frist laeuft.
CAP_LIMITATION_VIEW = "limitation.view"

# --- Build 536/537 (AP-3B): Dringlichkeitsmatrix (Seed in M033) ------
# EIGENES Recht, nicht 'dashboard.view' und nicht 'limitation.view'.
# Das Dashboard zeigt den BEARBEITUNGSSTAND je Fall; die Matrix zeigt eine
# RANGFOLGE und daneben den ARBEITSSTAND fremder Faelle (Abdeckung der
# Bewertung, hoechste Konfidenz, Identitaetszuordnung). Wer die Fristen
# sehen darf, darf damit noch nicht sehen, wie weit die Kolleginnen sind.
# NICHT scope-behaftet: eine Rangfolge ueber den eigenen Arbeitsvorrat
# waere keine.
CAP_MATRIX_VIEW = "matrix.view"

# --- Build 562 (AP-3E / Idee 38, Instanz B): Volltextsuche -------------------
# CAP_FULLTEXT_SEARCH liegt seit M006 im Katalog und ist das Recht, ueberhaupt
# zu SUCHEN (Stufe 1). NICHT scope-faehig, default-deny (Entscheidung mc
# 2026-07-26, E-2): eine auf die eigenen Faelle beschraenkte Suche beantwortet
# genau die Frage nicht, fuer die die Funktion gebaut wird (Kreuzbezug ZWISCHEN
# Faellen), wuerde aber als Sicherheitsgewinn verbucht. Die Kapselung leistet in
# Modell B die Stufe 2, nicht der Scope.
CAP_FULLTEXT_SEARCH = "evidence.fulltext_search"
# CAP_FULLTEXT_RELEASE (Seed in M036, Build 561; bis Build 543 M040)
# ist das Recht, ANDEREN den
# Inhalt fremder Faelle zu OEFFNEN. Wer sucht, gibt damit nichts frei; wer
# freigibt, sucht damit nicht.
CAP_FULLTEXT_RELEASE = "fulltext.release"

# --- Build 540/541 (AP-3C): QS-Stichprobe (Seed in M034) -------------
# ZWEI Rechte, ausdruecklich GETRENNT (Muster release.view /
# release.grant): wer die Stichprobe SEHEN darf, darf damit noch nicht
# PRUEFEN. Nur so bleibt Vier-Augen moeglich. Beide NICHT scope-behaftet
# — eine Stichprobe ueber den eigenen Arbeitsvorrat waere keine.
#
# ZWECKBINDUNG: AUSWERTUNGSQUALITAET, KEIN MITARBEITER-BEWERTUNGS-
# INSTRUMENT. Sie wird NICHT hier formuliert, sondern woertlich aus
# management/qs/qs_vokabular.py uebernommen und faehrt in jeder Antwort
# mit — eine zweite Formulierung waere eine zweite Wahrheitsquelle.
CAP_QS_VIEW = "qs.view"
CAP_QS_EDIT = "qs.edit"

# --- Build 542 (AP-3C): Ermittler-Metriken (Seed in M035) ------------
# EIGENES Recht, nicht 'qs.view' und nicht 'stats.export_sta'
# (Begruendung: management/migrations/coordinator/m035_metrics_rbac.py).
# NICHT scope-behaftet; die Antwort enthaelt KEINEN Personenbezug.
CAP_METRICS_VIEW = "metrics.view"

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
    """
    HTTP-Antwort als reines Datenobjekt (Status, Content-Type, Body-Bytes).

    Build 522 (AP-3F): zusaetzlich 'extra_headers' — eine Folge von
    (Name, Wert)-Paaren, die der HTTP-Handler unveraendert mitsendet. Sie ist
    ein TUPEL und nicht ein Dict, damit die Antwort weiterhin unveraenderlich
    (frozen) und die Reihenfolge der Kopfzeilen deterministisch bleibt — eine
    Antwort, die einmal gestempelt ist, wird nicht nachtraeglich veraendert
    (dasselbe Prinzip wie beim ExportContext).

    ANLASS: Der Prognosebericht wird als PDF ausgeliefert. Ohne
    'Content-Disposition' wuerde der Browser eine Datei mit dem Namen des
    Endpunktpfades anbieten ('report'), was in einer Akte nicht zuordenbar
    waere. Das Feld hat einen Vorgabewert -> alle bestehenden
    Response-Erzeugungen bleiben unveraendert gueltig (rein additiv).
    """

    status: int
    content_type: str
    body: bytes
    extra_headers: Tuple[Tuple[str, str], ...] = ()

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

    @staticmethod
    def pdf(status: int, data: bytes, *,
            filename: Optional[str] = None) -> "Response":
        """
        PDF-Antwort (Build 522).

        'inline' und NICHT 'attachment': der Server laeuft lokal (127.0.0.2),
        die Ermittlerin will den Beleg zuerst SEHEN und dann entscheiden, ob er
        in die Akte geht. Der Dateiname wird auf harmlose Zeichen begrenzt —
        ein Kopfzeilenwert mit Anfuehrungszeichen, Semikolon oder Zeilenumbruch
        waere eine Kopfzeilen-Injektion (die Werte kommen zwar hier aus dem
        Code, aber die Absicherung gehoert an die Stelle, die die Kopfzeile
        BAUT, nicht an ihre Aufrufer).
        """
        headers: Tuple[Tuple[str, str], ...] = ()
        if filename:
            safe = "".join(
                ch for ch in str(filename)
                if ch.isalnum() or ch in ("-", "_", ".")
            ) or "bericht.pdf"
            headers = (("Content-Disposition",
                        'inline; filename="%s"' % safe),)
        return Response(
            status=status,
            content_type="application/pdf",
            body=data,
            extra_headers=headers,
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
                 ad_directory: Optional[ADDirectory] = None,
                 case_launcher: Optional[CaseLauncher] = None,
                 ad_members_provider: Optional[Any] = None) -> None:
        self._db_path = db_path
        # Build 502: Mitgliederquelle des AD-Abgleichs (F4-Muster, injizierbar:
        # Test = Mock, PROD = LdapGroupReader aus config.yaml). BEWUSST lazy —
        # erst beim ersten /api/adsync-Aufruf gebaut, damit ein Server ohne
        # ad.ldap-Konfiguration normal startet und der Konfigurationsfehler
        # als Klartext IN der Sicht erscheint (kein Startabbruch fuer alle).
        self._ad_members_provider = ad_members_provider
        # Build 500: Startet den Forensik-Server (main.py) fuer einen Fall.
        # Injizierbar (Test: Fake ohne echten Prozess-Spawn); PROD: Default-
        # CaseLauncher mit plattformabhaengigem, losgeloestem Popen.
        self._case_launcher = case_launcher or CaseLauncher()
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
        # Build 515 (AP-2G / Idee 23): Eskalationen, auswertend.
        if path == "/api/escalations":
            return self._escalations(person_id)
        # Build 519 (AP-2F / Idee 22): Naechstbeste Aktion (Arbeitsschlange).
        if path == "/api/next_actions":
            return self._next_actions(person_id)
        # Build 520 (AP-2G / Idee 30): Uebergabe-Protokoll.
        if path == "/api/handover":
            return self._handover(person_id, query)
        # Build 521 (AP-2G / Idee 29): Aufbewahrungsfristen (Pruefvorschlag).
        if path == "/api/retention":
            return self._retention(person_id)
        # Build 524 (AP-3A / Idee 32): Verjaehrungsfristen (§§ 78 ff. StGB).
        if path == "/api/limitation":
            return self._limitation(person_id, query)
        # --- Build 537/538 (AP-3B): Dringlichkeits-/Erkenntnislage-Matrix ---
        #     Eigener Block am Ende der Fristen-Gruppe, damit er sich
        #     im Parallelbetrieb zusammenfuehren laesst
        #     (management/Parallelbetrieb_Welle3_v0_1.md §4).
        if path == "/api/matrix":
            return self._matrix(person_id, query)
        # --- Build 541 (AP-3C): QS-Stichprobe ---------------------------
        #     Eigener Block, damit er sich im Parallelbetrieb zusammenfuehren
        #     laesst (management/Parallelbetrieb_Welle3_v0_1.md §4).
        if path == "/api/qs":
            return self._qs(person_id, query)
        if path == "/api/qs/recheck":
            return self._qs_recheck(person_id, query)
        # --- Build 542 (AP-3C): Ermittler-Metriken ----------------------
        if path == "/api/metrics":
            return self._metrics(person_id, query)
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
        # Build 522 (AP-3F / Idee 40): Prognosebericht als PDF (oder HTML).
        # MUSS VOR '/api/forecast' geprueft werden? Nein — die Pfade sind
        # verschieden lang und werden exakt verglichen (kein Praefix-Match),
        # die Reihenfolge ist hier also unerheblich. Der Eintrag steht
        # trotzdem direkt daneben, damit beide Wege zur Prognose an einer
        # Stelle sichtbar sind.
        if path == "/api/forecast/report":
            return self._forecast_report(person_id, query)
        if path == "/api/gantt":
            return self._gantt(person_id)
        if path == "/api/annotation-stats":
            return self._annotation_stats(person_id)
        if path == "/api/search":
            return self._search(person_id, query)
        if path == "/api/assignable":
            return self._assignable(person_id)
        # Build 534: Kennzahlen je Fall aus den forensic_<uid>.db (uid_stats).
        # EIGENER Endpunkt, damit die Zuweisung nicht auf eine Nebenquelle
        # wartet (Begruendung: management/stats/uid_stats_repo.py, Kopf).
        if path == "/api/assignable/stats":
            return self._assignable_stats(person_id, query)
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
        # Build 475: Bericht als Vorlage uebernehmen — schreibfreier Entwurf
        # (read-only aus evidence_<uid>.db; Sanitisierung: Platzhalter-Werte
        # entfernt, evidence_ids geleert). Rechte/Scope wie /api/report/render.
        if path == "/api/report/as-template-draft":
            return self._report_as_template_draft(person_id, query)
        # Build 489/490: Platzhalter-Neuordnung (placeholders a/m/o). Der
        # Legacy-Alias /api/templates/queries ist mit dem Maskenumbau
        # (Build 490) entfallen.
        if path == "/api/templates/placeholders":
            return self._templates_placeholders(person_id)
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
        # Build 502: AD-Abgleich — Vorschau (rein lesend; das Live-AD wird
        # gefragt, die coordinator.db NICHT veraendert).
        if path == "/api/adsync":
            return self._adsync(person_id)
        # Build 503: Personalverwaltung — Liste (rein lesend, KEIN AD-Zugriff).
        if path == "/api/personnel":
            return self._personnel(person_id)
        # Build 470 (AP-2A): Katalog identifizierter Personen (Konto->Person).
        if path == "/api/crossref":
            return self._crossref(person_id, query)
        # Build 474 (AP-2A(3)): Querfund-Meta-Uebersicht (rein lesend).
        if path == "/api/crossfindings":
            return self._crossfindings(person_id, query)
        # Build 504 (AP-2A, Idee 8): globaler Alias-Katalog + Rueckwaertssuche.
        if path == "/api/alias":
            return self._alias(person_id, query)
        # Build 509 (AP-2A, Idee 11): Identitaets-Gruppen (Merge/Split).
        if path == "/api/merge":
            return self._merge(person_id, query)
        # Build 511 (AP-2B/B1): Akten-Export der aktiven Sicht.
        if path == "/api/view/export":
            return self._view_export(person_id, query)
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
        # --- Build 600: Namensaufloesung (Oberflaechen-Zweig) ------------
        # Steht am ENDE der Routenliste — so schreibt es Parallelbetrieb
        # Welle 3 §4 fuer diese gemeinsame Datei vor ("am Rand arbeiten, nie in
        # der Mitte"). Die Fachlogik liegt in management/crossref/
        # name_resolver.py; hier steht nur die Route.
        if path == "/api/names":
            return self._names(person_id, query)

        # --- Build 562 (AP-3E / Idee 38, Instanz B): Volltextsuche ---------
        # NUR die Katalog-/Statusauskunft ist ein GET. DIE SUCHE SELBST IST
        # EIN POST (s. dispatch_write): jede Abfrage schreibt einen Beleg
        # (FULLTEXT_SEARCHED, auch der Leerbefund), und ein GET, der schreibt,
        # erzeugte bei jedem Seitenwechsel und jedem Neuladen einen weiteren
        # Beleg — die Protokollspalte waere binnen Tagen unbrauchbar.
        if path == "/api/fulltext/zwecke":
            return self._fulltext_zwecke(person_id)
        if path == "/api/fulltext/indexstand":
            return self._fulltext_indexstand(person_id)
        if path == "/api/fulltext/releases":
            return self._fulltext_releases(person_id, query)

        # --- Build 545 (AP-3G / Idee 37): persoenliche Ansichtseinstellung --
        # OHNE FAEHIGKEITSPRUEFUNG, und das ist keine Luecke: die Antwort
        # enthaelt ausschliesslich die EIGENE Einrichtung der Oberflaeche und
        # einen statischen Katalog. Ein eigenes Recht haette nur die Frage
        # aufgeworfen, wer es wem entzieht. Der Rechtefilter wirkt dort, wo er
        # hingehoert — an den Kacheln ('erlaubt') und, ZULETZT, an den Sichten
        # im Browser.
        if path == "/api/viewprefs":
            return self._viewprefs(person_id)

        # --- Build 558: Kapazitaets-Stammdaten (Pflegegrundlage) ----------
        # GETRENNT von /api/capacity, weil es etwas ANDERES ist: dort steht
        # das ERGEBNIS der Rechnung (Basis/Netto je Person), hier stehen die
        # EINGANGSDATEN, die man aendern kann. Eine Sammelroute haette die
        # Pflegemaske gezwungen, das Ergebnis mitzuladen, das sie nicht
        # braucht - und den Rechner bei jedem Tastendruck laufen zu lassen.
        if path == "/api/capacity/stammdaten":
            return self._capacity_stammdaten(person_id, query)
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

    def _overload_thresholds(self) -> OverloadThresholds:
        """
        Grenzwerte der Ueberlastwarnung aus config.yaml (workload.overload.*).

        Faellt die Konfiguration aus, gelten die Vorgaben aus Build 451 — und
        der Ausfall wird PROTOKOLLIERT (Grundregel 1: kein stiller Zustand).
        Eine fehlende Konfiguration darf die Lastverteilung nicht ausfallen
        lassen; sie darf aber auch nicht unbemerkt andere Schwellen benutzen.
        Die Antwort traegt die tatsaechlich angewandten Schwellen deshalb
        IMMER mit (max_active_cases/max_red_cases/backlog_alert) — der
        Empfaenger kann jede Einstufung nachrechnen.
        """
        try:
            from core.config_loader import ConfigLoader
            return overload_thresholds_from_config(ConfigLoader().as_dict())
        except Exception as exc:  # pragma: no cover - Konfig-Ausfall
            logger.warning("Ueberlast-Schwellen nicht aus config.yaml lesbar "
                           "(%s) — Vorgaben aus Build 451.", exc)
            return OverloadThresholds()

    def _workload(self, person_id: int) -> Response:
        """
        Lastverteilung je Ermittler (read-only). Nutzt WorkloadRepo; liefert je
        Ermittler eine Last-Zeile plus eine Rueckstau-Zeile (unzugewiesen).
        Scope-aware analog _overview: 'alle' -> volle Verteilungssicht;
        'eigene' (oder ungesetzt) -> nur die EIGENE Last-Zeile (Rueckstau und
        fremde Ermittler bleiben gekapselt; Zweckbindung, default restriktiv).

        Build 513 (AP-2F / Idee 21): zusaetzlich die AKTIVE Ueberlastwarnung.
        ZWEI ENTWURFSENTSCHEIDUNGEN, die den Beleg tragen:

        (1) SELBE MESSUNG. Der Report wird aus der bereits geladenen Lastliste
            gebildet (build_report, rein) — nicht ueber einen zweiten
            Datenbankgang. Warnung und Balken koennen so nie auseinanderlaufen.
            'now' wird EINMAL bestimmt und in beide Richtungen gereicht.

        (2) NACH dem Scope-Filter bewertet. Wer nur die eigene Zeile sehen darf,
            bekommt auch nur eine Warnung ueber sich selbst; fremde Ueberlast
            und der systemische Rueckstau bleiben gekapselt (Zweckbindung).
            Die Rueckstau-Zeile traegt investigator_id 0 und faellt durch
            denselben Filter — backlog_size ist dann 0 und backlog_alarm false.
            Das ist KEIN Leerbefund im Sinne von 'kein Rueckstau', sondern ein
            NICHT ERHOBENER Wert; die Antwort weist das ueber
            'overload.scope_limited' aus, damit die Sicht es benennen kann.

        ANTWORTFORM: 'overload' traegt NUR Skalare (Schwellen + Zaehler), die
        Einzelbewertungen stehen daneben in 'overload_assessments'. Grund: der
        Akten-Export (Build 511/512) rendert eine flache Abbildung als
        Schluessel-Wert-Tabelle und eine Zeilenliste als Tabelle. Waeren die
        Bewertungen im dict verschachtelt, stuenden sie im Aktenexport als
        JSON-Klumpen in EINER Zelle — lesbar, aber kein brauchbarer Beleg.
        Es ist bewusst KEINE Doppelablage: jede Angabe steht genau einmal.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_WORKLOAD):
            return self._forbidden(CAP_WORKLOAD)
        scope = policy.scope(CAP_WORKLOAD)  # 'alle' | 'eigene' | None

        # EIN Zeitstempel fuer Messung UND Bewertung (siehe (1) oben).
        now = int(time.time())

        con = self._ro_con()
        try:
            try:
                loads = WorkloadRepo(con).list_workload(now=now)
            except WorkloadSchemaError as exc:
                return Response.json(
                    503, {"error": "schema", "detail": str(exc)})
        finally:
            con.close()

        if scope != "alle":
            loads = [l for l in loads if l.investigator_id == person_id]

        items = [asdict(l) for l in loads]

        report = build_overload_report(loads, self._overload_thresholds(), now)
        overload = overload_to_dict(report)
        # Einzelbewertungen ausgliedern (siehe ANTWORTFORM oben). pop statt
        # copy: 'overload' darf sie NICHT zusaetzlich enthalten, sonst haetten
        # wir zwei Wahrheitsquellen fuer dieselbe Aussage.
        assessments = overload.pop("assessments", [])
        overload["scope_limited"] = (scope != "alle")

        return Response.json(200, {"scope": scope, "count": len(items),
                                   "loads": items,
                                   "overload": overload,
                                   "overload_assessments": assessments})

    def _escalation_thresholds(self) -> EscalationThresholds:
        """
        Schwellen der Eskalationsregeln aus config.yaml (escalation.*).

        Wie bei der Ueberlastwarnung (Build 513): faellt die Konfiguration aus,
        gelten die Vorgaben aus Build 453 — und der Ausfall wird
        PROTOKOLLIERT. Die angewandten Schwellen fahren in der Antwort mit,
        damit jede gemeldete Eskalation nachrechenbar ist.
        """
        try:
            from core.config_loader import ConfigLoader
            return escalation_thresholds_from_config(ConfigLoader().as_dict())
        except Exception as exc:  # pragma: no cover - Konfig-Ausfall
            logger.warning("Eskalations-Schwellen nicht aus config.yaml lesbar "
                           "(%s) — Vorgaben aus Build 453.", exc)
            return EscalationThresholds()

    def _escalations(self, person_id: int) -> Response:
        """
        Eskalationen (read-only, Build 515 zu Build 453 / AP-2G, Idee 23).

        NICHT SCOPE-BEHAFTET — und das ist eine bewusste Entscheidung, keine
        Nachlaessigkeit: die Sicht beantwortet die Frage "wo bleibt etwas
        liegen, das NIEMAND anfasst". Die wichtigste Regel (rueckstau_hoch)
        traegt subject_id=None, weil sie GAR KEINEM Fall und damit auch keiner
        Person zuzuordnen ist. Auf 'eigene' verengt haette die Sicht genau die
        Faelle nicht gezeigt, um derentwillen es sie gibt. Die Zugangskontrolle
        laeuft deshalb ueber das Recht selbst (escalation.view, default-deny),
        nicht ueber einen Ausschnitt.

        ANTWORT: escalation_to_dict + 'thresholds'. Die Schwellen fahren MIT,
        weil eine Eskalationsmeldung ohne ihren Massstab nicht nachpruefbar
        waere ('30 Tage inaktiv' ist erst mit '>= 30' eine Aussage).

        BEWUSSTE LUECKE, die dieser Build NICHT schliesst: es gibt weiterhin
        keinen Weg, eine Eskalation zu QUITTIEREN. Die Sicht ist rein
        auswertend. Der auditierte Schreibpfad ist als eigenes Arbeitspaket
        angesetzt (Befund Uebergabe 440-453 §3.3) — er bekommt eine eigene
        Faehigkeit, damit ein Lese-Grant nie ein Schreibrecht mitbringt.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_ESCALATION_VIEW):
            return self._forbidden(CAP_ESCALATION_VIEW)

        thresholds = self._escalation_thresholds()
        now = int(time.time())
        con = self._ro_con()
        try:
            report = EscalationRepo(con).compute(thresholds=thresholds,
                                                 now=now)
        finally:
            con.close()

        payload = escalation_to_dict(report)
        payload["thresholds"] = {
            "red_overdue_days": thresholds.red_overdue_days,
            "stale_open_days": thresholds.stale_open_days,
            "backlog_high": thresholds.backlog_high,
        }

        # Build 517: Vermerke an die Meldungen heften. KEINE Meldung wird
        # dabei entfernt oder umsortiert — Quittieren ist KEIN Erledigen
        # (Begruendung ausfuehrlich in escalation_ack_repo.py). Faellt M027
        # aus (noch nicht migriert), bleibt 'ack' ueberall None UND
        # 'acknowledgeable' false: die Sicht meldet dann 'nicht moeglich'
        # statt eine leere Vermerklage zu zeigen, die wie 'nichts quittiert'
        # laese (Grundregel 1).
        con = self._ro_con()
        try:
            ack_repo = EscalationAckRepo(con)
            migriert = ack_repo.table_exists(con)
            acks = ack_repo.list_active() if migriert else []
            namen = ack_repo.names() if migriert else {}
        finally:
            con.close()
        payload["items"] = annotate_items(payload.get("items", []), acks,
                                          namen)

        # 'acknowledgeable' sagt der Sicht AUSDRUECKLICH, ob dieser Aufrufer
        # quittieren kann. Ohne diese Angabe muesste das Frontend es RATEN —
        # und ein geratener Zustand ist in diesem Projekt kein Beleg. Beide
        # Bedingungen muessen erfuellt sein: die Struktur (M027) UND das Recht.
        payload["acknowledgeable"] = bool(
            migriert and policy.can(CAP_ESCALATION_ACK))
        payload["ack_migrated"] = migriert
        return Response.json(200, payload)

    def _next_actions(self, person_id: int) -> Response:
        """
        Naechstbeste Aktion (read-only, Build 519 zu Build 452/469, Idee 22).

        SCOPE ENTSCHEIDET UEBER DEN ZWECK, NICHT UEBER DIE VOLLSTAENDIGKEIT:
        mit 'alle' ist es die Verteilsicht der Leitung, mit 'eigene' die
        eigene Arbeitsschlange. Beide sind IN SICH vollstaendig — anders als
        bei der Lastverteilung (Build 513) faellt hier nichts heraus, was zur
        Beurteilung des Gezeigten noetig waere. Deshalb braucht diese Sicht
        auch keinen 'scope_limited'-Hinweis: 'meine Faelle' ist die Frage,
        nicht ein Ausschnitt der Antwort. Der angewandte Scope faehrt
        trotzdem MIT (das Read-Model liefert ihn), damit der Akten-Export
        nicht offenlaesst, wessen Schlange abgebildet ist.

        ZAEHLUNG STATT VERSCHWEIGEN: abgeschlossene Faelle brauchen keine
        Aktion und stehen nicht in der Schlange — sie werden aber GEZAEHLT
        ('done_excluded', Build 452). Ohne diese Zahl saehe eine kurze
        Schlange bei vielen Faellen wie ein Datenfehler aus.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_NEXTACTIONS_VIEW):
            return self._forbidden(CAP_NEXTACTIONS_VIEW)
        scope = policy.scope(CAP_NEXTACTIONS_VIEW)  # 'alle' | 'eigene' | None

        # Default restriktiv: alles ausser einem ausdruecklichen 'alle' wird
        # als 'eigene' behandelt (Linie _workload).
        wirksam = "alle" if scope == "alle" else "eigene"

        con = self._ro_con()
        try:
            result = NextActionsRepo(con).compute(
                scope=wirksam, person_id=person_id, now=int(time.time()))
        finally:
            con.close()

        payload = queue_to_dict(result)
        # Der GRANT-Scope faehrt zusaetzlich mit: 'scope' im Read-Model ist der
        # ANGEWANDTE Wert; wer die Antwort spaeter liest, soll auch sehen,
        # welches Recht dahinterstand (None = kein Scope gesetzt -> 'eigene').
        payload["granted_scope"] = scope
        return Response.json(200, payload)

    def _handover(self, person_id: int,
                  query: Optional[Dict[str, List[str]]]) -> Response:
        """
        Uebergabe-Protokoll (read-only, Build 520 zu Build 455/469, Idee 30).

        Query: subject_id (optional) — auf EINEN Fall einschraenken.

        NICHT SCOPE-BEHAFTET, gleiche Begruendung wie bei den Eskalationen:
        ein Uebergabe-Protokoll handelt von der BEZIEHUNG zwischen Personen.
        Auf die eigenen Eintraege verengt entstuende ein Protokoll MIT
        LUECKEN, das vollstaendig AUSSIEHT — und dessen Zaehler dann etwas
        anderes bedeuteten als sie sagen ('3 Uebergaben' hiesse in Wahrheit
        '3 Uebergaben, an denen ich beteiligt war'). Der Zugang laeuft
        deshalb ueber das Recht selbst (handover.view, default-deny).

        QUELLE IST DIE AUDIT-KETTE, NICHT EIN ZWEITES REGISTER: das Protokoll
        wird aus den unveraenderlichen CASE_ASSIGNED-Belegen rekonstruiert.
        Es gibt also nichts, was nachtraeglich 'aufgeraeumt' werden koennte —
        und es kann nicht von der Fallakte abweichen.

        DER FILTER FAEHRT MIT ('filter_subject_id'): ein gefiltertes Protokoll
        sieht sonst aus wie ein vollstaendiges mit wenigen Eintraegen. Der
        Akten-Export uebernimmt den Wert in den Dokumentkopf.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_HANDOVER_VIEW):
            return self._forbidden(CAP_HANDOVER_VIEW)

        roh = self._q1(query, "subject_id", "")
        subject_id: Optional[int] = None
        if roh not in (None, ""):
            try:
                subject_id = int(roh)
            except (TypeError, ValueError):
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "subject_id muss eine ganze Zahl sein."})

        con = self._ro_con()
        try:
            report = HandoverRepo(con).compute(subject_id=subject_id,
                                               now=int(time.time()))
        finally:
            con.close()

        payload = handover_to_dict(report)
        payload["filter_subject_id"] = subject_id
        return Response.json(200, payload)

    def _retention_thresholds(self) -> RetentionThresholds:
        """
        Aufbewahrungsfrist aus config.yaml (retention.retention_days).

        Wie bei Ueberlast (513) und Eskalation (515): faellt die Konfiguration
        aus, gilt die Vorgabe aus Build 456 — und der Ausfall wird
        PROTOKOLLIERT. Die angewandte Frist faehrt in der Antwort mit, damit
        jede Einstufung nachrechenbar ist.
        """
        try:
            from core.config_loader import ConfigLoader
            return retention_thresholds_from_config(ConfigLoader().as_dict())
        except Exception as exc:  # pragma: no cover - Konfig-Ausfall
            logger.warning("Aufbewahrungsfrist nicht aus config.yaml lesbar "
                           "(%s) — Vorgabe aus Build 456.", exc)
            return RetentionThresholds()

    def _retention(self, person_id: int) -> Response:
        """
        Aufbewahrungsfristen (read-only, Build 521 zu Build 456, Idee 29).

        DIESE SICHT LOESCHT NICHTS UND KANN NICHTS LOESCHEN. Sie erhebt einen
        PRUEFVORSCHLAG. Es gibt im gesamten Werkzeug keinen Weg, aus dieser
        Antwort eine Loeschung auszuloesen — das ist keine noch fehlende
        Bequemlichkeit, sondern Absicht: das Loeschen von Beweismitteln ist
        eine Governance-Entscheidung ausserhalb dieses Systems. Die Antwort
        traegt diese Aussage deshalb ausdruecklich als 'deletes_nothing' mit,
        damit keine Sicht und kein spaeterer Automat sie ueberlesen kann.

        NICHT SCOPE-BEHAFTET: Fristenkontrolle ist eine Leitungsaufgabe.

        DREI ZAHLEN, DIE ZUSAMMENGEHOEREN (aus Build 456): total_cases,
        closed_cases und 'without_reference'. Die letzte ist die wichtigste:
        Faelle, bei denen KEIN Bezugszeitpunkt ermittelbar war. Sie sind
        weder Kandidat noch unverdaechtig — sie sind UNGEPRUEFT. Wuerde man
        sie weglassen, saehe eine kurze Kandidatenliste wie eine
        vollstaendige Pruefung aus (Grundregel 1).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_RETENTION_VIEW):
            return self._forbidden(CAP_RETENTION_VIEW)

        thresholds = self._retention_thresholds()
        con = self._ro_con()
        try:
            report = RetentionRepo(con).compute(thresholds=thresholds,
                                                now=int(time.time()))
        finally:
            con.close()

        payload = retention_to_dict(report)
        # Die Zusicherung faehrt MIT. Sie ist hier keine Verzierung: eine
        # Kandidatenliste ohne den ausdruecklichen Loeschvorbehalt koennte
        # spaeter als Arbeitsauftrag missverstanden werden.
        payload["deletes_nothing"] = True
        return Response.json(200, payload)

    # ---------------------------------------------------------------- Build 524
    # AP-3A / Idee 32: Fristen-/Verjaehrungs-Monitor (§§ 78 ff. StGB).

    def _limitation(self, person_id: int, query) -> Response:
        """
        GET /api/limitation[?vorwarn_tage=N] — der Fristenmonitor.

        DIESE SICHT STELLT KEINE VERJAEHRUNG FEST. Sie rechnet die
        UNUNTERBROCHENE Frist und nennt jede Annahme, die dabei eingeht.
        Unterbrechungen nach § 78c StGB sind dem Werkzeug nicht bekannt und
        koennen die Frist neu in Gang gesetzt haben; deshalb sagt keine Antwort
        'verjaehrt', sondern 'rechnerisch ueberschritten — juristische Pruefung
        erforderlich'.

        IST DER PARAMETERSATZ NICHT BESTAETIGT, LIEFERT DIE ANTWORT DEN GRUND
        UND KEINE AMPEL. Das ist kein Fehler und kein 503: die Fallliste, die
        Datenlage je Fall und die Vorbehalte sind vollstaendig da und nuetzlich
        (man sieht sofort, fuer wie viele Faelle ueberhaupt ein Tatzeitpunkt
        belegt ist). Nur die Rechtsfolge fehlt — und sie fehlt SICHTBAR
        ('aussage_moeglich': false + 'verweigerungsgrund').

        IST DER PARAMETERSATZ UNBRAUCHBAR (Selbstpruefung schlaegt an), ist das
        etwas ANDERES und wird als 503 gemeldet: dann stimmt an der
        Konfiguration etwas nicht, und das darf nicht wie ein blosser
        Bestaetigungsmangel aussehen.

        NICHT SCOPE-BEHAFTET (CAP_LIMITATION_VIEW, Seed M031): Fristenkontrolle
        ist eine Leitungsaufgabe, und die gefaehrlichsten Faelle sind gerade die
        UNZUGEWIESENEN.

        REIN LESEND: coordinator.db und alle forensic_<uid>.db mit mode=ro.
        Kein CoordinatorWriter, kein Schreibpfad — der Migrationsvorbehalt ab
        01.07.2026 ist NICHT beruehrt.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_LIMITATION_VIEW):
            return self._forbidden(CAP_LIMITATION_VIEW)

        # Die Vorwarnschwelle ist uebersteuerbar (die Leitung will je nach Lage
        # 6 oder 18 Monate sehen). Ein unbrauchbarer Wert ist ein 400 — NICHT
        # ein stillschweigend ersetzter Vorgabewert, denn die Schwelle
        # entscheidet ueber die Ampelfarbe und muss nachrechenbar bleiben.
        raw = self._q1(query, "vorwarn_tage")
        vorwarn = DEFAULT_VORWARN_TAGE
        if raw is not None and str(raw) != "":
            try:
                vorwarn = int(raw)
            except (TypeError, ValueError):
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "vorwarn_tage muss eine ganze Zahl sein."})
            if vorwarn < 0:
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "vorwarn_tage darf nicht negativ sein."})

        try:
            params = load_params()
        except LimitationParamsError as exc:
            # UNBRAUCHBARER Satz != unbestaetigter Satz. Der Unterschied gehoert
            # in den Statuscode, damit er im Betrieb nicht untergeht.
            logger.error("Verjaehrungs-Parametersatz unbrauchbar: %s", exc)
            return Response.json(503, {
                "error": "limitation_params_invalid",
                "detail": str(exc),
                "hinweis": "Der Parametersatz management/deadlines/"
                           "limitation_params.json ist in sich "
                           "widerspruechlich oder nicht lesbar. Pruefen mit: "
                           "python -m management.deadlines.limitation_admin "
                           "pruefen"})

        con = self._ro_con()
        try:
            # Build 535: evidence_dir MUSS mit — sonst traegt jede Zeile den
            # Befund 'nicht_geprueft' und der Bericht sagt, dass die
            # festgestellte Tatzeit nicht ausgewertet wurde. Das ist die
            # gewollte Wirkung fuer Aufrufer, die es nicht mitgeben; hier ist
            # es vorhanden und wird gereicht.
            report = LimitationRepo(
                con, self._forensic_dir, self._evidence_dir).compute(
                params=params, now_ts=int(time.time()), vorwarn_tage=vorwarn)
        except Exception as exc:                        # noqa: BLE001
            logger.exception("Fristenmonitor fehlgeschlagen")
            return Response.json(500, {"error": "limitation_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        payload = report.to_dict()
        # Die Zusicherung faehrt MIT — wie 'deletes_nothing' bei den
        # Aufbewahrungsfristen (Build 521). Eine Fristliste ohne diesen Satz
        # koennte als Feststellung der Verjaehrung missverstanden werden, und
        # das waere die folgenschwerste Fehldeutung, die dieses Werkzeug
        # zulassen koennte.
        payload["stellt_keine_verjaehrung_fest"] = True
        # Build 530: die zweite Zusicherung, nach demselben Muster. Sie sagt,
        # was mit den Zahlen NICHT geschehen darf. Ohne sie waere die Regel
        # 'der Bericht zitiert nur Festgestelltes' nur eine Absprache; mit ihr
        # ist sie Bestandteil jeder Antwort und damit pruefbar.
        payload["nur_festgestellte_zitierfaehig"] = True
        return Response.json(200, payload)

    # --- Build 537/538 (AP-3B): Dringlichkeits-/Erkenntnislage-Matrix -----------
    def _matrix(self, person_id: int, query: Dict[str, Any]) -> Response:
        """
        GET /api/matrix — die Rangfolge der Faelle nach Bearbeitungs-
        dringlichkeit (X) und Erkenntnislage (Y). Recht 'matrix.view'.

        NICHT SCOPE-BEHAFTET, aus demselben Grund wie der Fristenmonitor: eine
        Rangfolge ueber den eigenen Arbeitsvorrat waere keine, und die
        gefaehrlichsten Faelle sind gerade die UNZUGEWIESENEN.

        REIN LESEND: coordinator.db mit mode=ro. Kein CoordinatorWriter, kein
        Schreibpfad. Die Matrix schreibt insbesondere NICHT in cases.priority
        (Entscheidung mc) — sie ist ein Vorschlag, den ein Mensch bewertet.

        MIT FRISTBEITRAEGEN (Build 538). '?fristen=0' laesst sie weg und
        liefert die schnelle Sicht: sie luegt nicht, sie sagt weniger, und die
        Antwort sagt WELCHES weniger ('fristen_geladen': false, jede Zeile mit
        dem Grund 'nicht_geladen'). Die Laufzeit faehrt in 'dauer_gesamt_ms'
        und 'dauer_fristen_ms' mit — die Fristkomponente ist der einzige Teil,
        der je Fall Dateien oeffnet, und wer sie abschaltet, will nachlesen
        koennen, was das gebracht hat.

        EIN UNBRAUCHBARER VERJAEHRUNGS-PARAMETERSATZ IST HIER KEIN 503 — im
        Unterschied zu /api/limitation und im Unterschied zum
        Gewichtungssatz. Begruendung: der Gewichtungssatz ist die SKALA, ohne
        ihn bedeutet keine Zahl etwas; der Fristparametersatz traegt EINEN von
        sechs Beitraegen. Er faellt aus, wird in 'fehlende_quellen' benannt,
        und die uebrigen fuenf Beitraege bleiben brauchbar. Vorgelegt mit der
        Bitte um Widerspruch (mc), falls die Leitung hier lieber gar keine
        Matrix saehe.
        """
        from management.results.matrix_repo import MatrixRepo
        from management.results.matrix_weights import (
            MatrixWeightsError, load_weights,
        )

        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_MATRIX_VIEW):
            return self._forbidden(CAP_MATRIX_VIEW)

        # Build 538: das Nachladeverhalten. Ein unverstandener Wert ist ein
        # 400 und KEIN stillschweigend angenommener Vorgabewert — ob die
        # Fristen drin sind, entscheidet ueber bis zu 40 von 90 Punkten der
        # X-Achse und muss nachrechenbar bleiben (Muster: vorwarn_tage in
        # _limitation).
        roh = self._q1(query, "fristen")
        mit_fristen = True
        if roh is not None and str(roh) != "":
            if str(roh) in ("0", "false", "nein"):
                mit_fristen = False
            elif str(roh) in ("1", "true", "ja"):
                mit_fristen = True
            else:
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "fristen muss 0/1 (bzw. false/true, nein/ja) "
                              "sein — '%s' wurde nicht verstanden." % roh})

        try:
            gewichte = load_weights()
        except MatrixWeightsError as exc:
            # UNBRAUCHBARER Gewichtungssatz -> KEINE Matrix. Dieselbe Haltung
            # wie beim Verjaehrungs-Parametersatz: lieber gar keine Zahl als
            # eine, deren Zustandekommen niemand beschlossen hat.
            logger.error("Matrix-Gewichtungssatz unbrauchbar: %s", exc)
            return Response.json(503, {
                "error": "matrix_weights_invalid",
                "detail": str(exc),
                "hinweis": "management/results/matrix_weights.json ist in sich "
                           "widerspruechlich oder nicht lesbar. Die Matrix "
                           "rechnet nicht mit geratenen Gewichten."})

        con = self._ro_con()
        try:
            # Build 538: BEIDE Verzeichnisse gehen mit. Ohne evidence_dir
            # traegt jede Fristzeile den Befund 'nicht_geprueft' (Build 535),
            # und die festgestellte Tatzeit — der einzige Anker, den ein
            # Mensch gesetzt hat — bliebe ungenutzt.
            report = MatrixRepo(
                con, gewichte, self._forensic_dir, self._evidence_dir
            ).compute(now_ts=int(time.time()), mit_fristen=mit_fristen)
        except Exception as exc:                        # noqa: BLE001
            logger.exception("Matrix fehlgeschlagen")
            return Response.json(500, {"error": "matrix_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        # Die Zusicherungen fahren MIT — Muster 'stellt_keine_verjaehrung_fest'
        # (Build 524) und 'deletes_nothing' (Build 521). Eine Rangfolge ohne
        # diese Saetze koennte als Bewertung der Beschuldigten gelesen werden,
        # und das waere hier die folgenschwerste Fehldeutung.
        report["ist_keine_beweiswuerdigung"] = True
        report["schreibt_keine_prioritaet"] = True
        return Response.json(200, report)

    # --- Build 541 (AP-3C): QS-Stichprobe -----------------------------------
    def _qs(self, person_id: int, query: Dict[str, Any]) -> Response:
        """
        GET /api/qs — Ziehungen mit Prueflingen und Ergebnissen. Recht
        'qs.view'.

        NICHT SCOPE-BEHAFTET: eine Stichprobe ueber den eigenen Arbeitsvorrat
        waere keine.

        DIE ANTWORT SAGT AUCH, WAS DER ABRUFENDE NICHT DARF. 'darf_pruefen'
        je Fall kommt aus derselben Regel, die der Schreibpfad durchsetzt
        (QsRepo.darf_pruefen) — die Sicht kann einen gesperrten Fall damit
        vorab kennzeichnen. DIE SPERRE SELBST WIRKT IM SERVER: diese Angabe
        ist eine Bequemlichkeit, keine Kontrolle.

        REIN LESEND: coordinator.db mit mode=ro.
        """
        from management.qs.qs_repo import QsRepo

        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_QS_VIEW):
            return self._forbidden(CAP_QS_VIEW)

        con = self._ro_con()
        try:
            repo = QsRepo(con)
            bericht = repo.liste()
            # Je Prueflings-Zeile: darf DIESE Person ihn pruefen?
            for z in bericht.get("ziehungen", []):
                for it in z.get("faelle", []):
                    darf, gruende = repo.darf_pruefen(
                        int(it["subject_id"]), int(person_id))
                    it["darf_pruefen"] = darf
                    it["sperrgruende"] = gruende
        except Exception as exc:                        # noqa: BLE001
            logger.exception("QS-Sicht fehlgeschlagen")
            return Response.json(500, {"error": "qs_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        bericht["darf_pruefen_recht"] = policy.can(CAP_QS_EDIT)
        return Response.json(200, bericht)

    def _qs_recheck(self, person_id: int, query: Dict[str, Any]) -> Response:
        """
        GET /api/qs/recheck?sample_id=N — eine gespeicherte Ziehung NACHRECHNEN.

        Das ist der eigentliche Zweck des mitgeschriebenen Keims: gegen den
        Vorwurf der gezielten Auswahl hilft nur, dass es jemand nachrechnen
        KANN. Recht 'qs.view' (Lesen genuegt — Nachrechnen aendert nichts).

        EINE ABWEICHUNG IST KEIN FEHLER UND KEIN 500. Die Grundgesamtheit
        aendert sich im laufenden Betrieb; die Antwort sagt das ausdruecklich
        und ueberlaesst die Bewertung dem Menschen.
        """
        from management.qs.qs_repo import QsError, QsRepo

        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_QS_VIEW):
            return self._forbidden(CAP_QS_VIEW)

        roh = self._q1(query, "sample_id")
        try:
            sample_id = int(roh)
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "sample_id muss eine ganze Zahl sein."})

        con = self._ro_con()
        try:
            return Response.json(200, QsRepo(con).nachziehen(sample_id))
        except QsError as exc:
            return Response.json(400, {"error": "qs_invalid",
                                       "detail": str(exc)})
        except Exception as exc:                        # noqa: BLE001
            logger.exception("QS-Nachziehen fehlgeschlagen")
            return Response.json(500, {"error": "qs_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

    def _qs_draw(self, person_id: int, payload: Dict[str, Any]) -> Response:
        """
        POST /api/qs/draw — {seed?, anteil?, hoechstens?, verfahren?,
        bemerkung?}. Recht 'qs.edit' (auditiert).

        DER KEIM DARF MITGEGEBEN WERDEN, und das ist Absicht: nur so laesst
        sich eine Ziehung bewusst wiederholen. Fehlt er, wird EINER ERZEUGT
        und mitgeschrieben — nie eine Ziehung ohne Keim. Der erzeugte Keim
        stammt aus der Uhr und ist damit selbst nachvollziehbar; ein
        kryptografischer Zufall waere hier ein Fehler (s.
        management/qs/qs_sampler.py).
        """
        from management.qs.qs_repo import QsError, QsRepo

        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_QS_EDIT):
            return self._forbidden(CAP_QS_EDIT)

        payload = payload or {}
        try:
            seed = int(payload.get("seed")) if payload.get("seed") is not None \
                else int(time.time())
            anteil = float(payload.get("anteil", 0.1))
            hoechstens = int(payload.get("hoechstens", 10))
        except (TypeError, ValueError) as exc:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "seed/anteil/hoechstens muessen Zahlen sein (%s)."
                          % exc})
        verfahren = str(payload.get("verfahren") or "geschichtet")
        bemerkung = str(payload.get("bemerkung") or "")

        con = self._rw_con()
        try:
            repo = QsRepo(con, CoordinatorWriter(con, AuditLog(con)))
            out = repo.ziehen(seed=seed, anteil=anteil, hoechstens=hoechstens,
                              verfahren=verfahren, bemerkung=bemerkung,
                              actor_id=person_id)
        except QsError as exc:
            return Response.json(400, {"error": "qs_invalid",
                                       "detail": str(exc)})
        except Exception as exc:                        # noqa: BLE001
            logger.exception("QS-Ziehung fehlgeschlagen")
            return Response.json(500, {"error": "qs_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, out)

    def _qs_review(self, person_id: int, payload: Dict[str, Any]) -> Response:
        """
        POST /api/qs/review — {sample_id, subject_id, ergebnis, begruendung}.
        Recht 'qs.edit' (auditiert).

        DREI ABWEISUNGSGRUENDE, DREI STATUSCODES, und der Unterschied ist
        fachlich:
          403 ohne 'qs.edit'                — darf gar nicht pruefen.
          403 bei SELBSTPRUEFUNG            — darf DIESEN Fall nicht pruefen.
          400 bei unbrauchbarer Eingabe     — darf, hat aber falsch ausgefuellt.
        Die Selbstpruefung als 400 zu melden waere irrefuehrend: an der Eingabe
        ist nichts zu bessern.
        """
        from management.qs.qs_repo import (
            QsError, QsRepo, QsSelbstpruefungError,
        )

        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_QS_EDIT):
            return self._forbidden(CAP_QS_EDIT)

        payload = payload or {}
        try:
            sample_id = int(payload.get("sample_id"))
            subject_id = int(payload.get("subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "sample_id und subject_id muessen ganze Zahlen "
                          "sein."})
        ergebnis = str(payload.get("ergebnis") or "")
        begruendung = str(payload.get("begruendung") or "")

        con = self._rw_con()
        try:
            repo = QsRepo(con, CoordinatorWriter(con, AuditLog(con)))
            out = repo.pruefen(sample_id=sample_id, subject_id=subject_id,
                               ergebnis=ergebnis, begruendung=begruendung,
                               actor_id=person_id)
        except QsSelbstpruefungError as exc:
            # KEIN 400: an der Eingabe ist nichts zu bessern.
            return Response.json(403, {"error": "qs_selbstpruefung",
                                       "capability": CAP_QS_EDIT,
                                       "detail": str(exc)})
        except QsError as exc:
            return Response.json(400, {"error": "qs_invalid",
                                       "detail": str(exc)})
        except Exception as exc:                        # noqa: BLE001
            logger.exception("QS-Pruefung fehlgeschlagen")
            return Response.json(500, {"error": "qs_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, out)


    # --- Build 542 (AP-3C): Ermittler-Metriken ------------------------------
    def _metrics(self, person_id: int, query: Dict[str, Any]) -> Response:
        """
        GET /api/metrics[?substanz=1] — Kennzahlen zur Auswertungsqualitaet.
        Recht 'metrics.view'.

        AGGREGIERT WIRD UEBER FAELLE, NICHT UEBER PERSONEN. Die Antwort traegt
        'keine_personenrangfolge' und die Zweckbindung WORTGLEICH aus
        management/metrics/metrics_vokabular.py — eine zweite Formulierung
        waere eine zweite Wahrheitsquelle. Die Lastverteilung JE ERMITTLER gibt
        es weiterhin nur unter /api/workload, mit eigenem Recht und eigenem
        Scope.

        '?substanz=1' schaltet den teuren Block zu (ein Dateizugriff je
        zugewiesenem Fall auf evidence_<uid>.db). Ohne ihn sagt die Antwort
        ausdruecklich, dass NICHT NACHGESEHEN wurde — sie behauptet nicht, es
        gebe keine Faelle ohne Substanz. Muster: die Fristkomponente der Matrix
        (Build 538). Die Dauer faehrt in 'dauer_substanz_ms' mit.

        REIN LESEND: coordinator.db und alle evidence_<uid>.db mit mode=ro.
        """
        from management.metrics.metrics_repo import MetricsRepo

        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_METRICS_VIEW):
            return self._forbidden(CAP_METRICS_VIEW)

        roh = self._q1(query, "substanz")
        mit_substanz = False
        if roh is not None and str(roh) != "":
            if str(roh) in ("1", "true", "ja"):
                mit_substanz = True
            elif str(roh) in ("0", "false", "nein"):
                mit_substanz = False
            else:
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "substanz muss 0/1 (bzw. false/true, nein/ja) "
                              "sein — '%s' wurde nicht verstanden." % roh})

        con = self._ro_con()
        try:
            bericht = MetricsRepo(con, self._evidence_dir).compute(
                now_ts=int(time.time()), mit_substanz=mit_substanz)
        except Exception as exc:                        # noqa: BLE001
            logger.exception("Metriken fehlgeschlagen")
            return Response.json(500, {"error": "metrics_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, bericht)

    def _escalation_ack(self, actor_person_id: int,
                        payload: Dict[str, Any]) -> Response:
        """
        POST /api/escalations/ack — {rule_code, subject_id?, reason,
        days_inactive?}. Recht escalation.ack (auditiert).

        subject_id DARF FEHLEN oder null sein: die systemische Regel
        'rueckstau_hoch' gehoert zu keinem Fall. Das ist hier ein GUELTIGER
        Wert und kein Eingabefehler — ein Pflichtfeld haette die wichtigste
        Meldung der Sicht unquittierbar gemacht.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_ESCALATION_ACK):
            return self._forbidden(CAP_ESCALATION_ACK)

        con = self._rw_con()
        try:
            repo = EscalationAckRepo(con, CoordinatorWriter(con, AuditLog(con)))
            if not repo.table_exists(con):
                return Response.json(503, {
                    "error": "not_migrated",
                    "detail": "Migration M027 (escalation_ack) ist nicht "
                              "angewandt — es kann nichts quittiert werden."})
            res = repo.acknowledge(
                rule_code=str(payload.get("rule_code", "")),
                subject_id=payload.get("subject_id"),
                reason=str(payload.get("reason", "") or ""),
                days_inactive=payload.get("days_inactive"),
                actor_id=actor_person_id,
            )
        except EscalationAckError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Quittierung fehlgeschlagen")
            return Response.json(500, {"error": "escalation_ack_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    def _escalation_ack_revoke(self, actor_person_id: int,
                               payload: Dict[str, Any]) -> Response:
        """
        POST /api/escalations/ack/revoke — {ack_id, reason}. Recht
        escalation.ack (auditiert).

        WIDERRUF STATT LOESCHUNG: die Zeile bleibt als Beleg stehen. Ein
        stilles Loeschen wuerde die Erkenntnis 'es wurde einmal quittiert'
        vernichten — und gerade die ist die aufsichtsrelevante.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_ESCALATION_ACK):
            return self._forbidden(CAP_ESCALATION_ACK)

        try:
            ack_id = int(payload.get("ack_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "ack_id fehlt/ungueltig."})

        con = self._rw_con()
        try:
            repo = EscalationAckRepo(con, CoordinatorWriter(con, AuditLog(con)))
            if not repo.table_exists(con):
                return Response.json(503, {
                    "error": "not_migrated",
                    "detail": "Migration M027 (escalation_ack) ist nicht "
                              "angewandt."})
            res = repo.revoke(ack_id=ack_id,
                              reason=str(payload.get("reason", "") or ""),
                              actor_id=actor_person_id)
        except EscalationAckError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Widerruf einer Quittierung fehlgeschlagen")
            return Response.json(500, {"error": "escalation_ack_revoke_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

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

    # ==================================================================
    # Build 558 — KAPAZITAETSPFLEGE (Schreibwege)
    # ==================================================================
    # WARUM DIESER BUILD: Schema (m008), Schreibpfade (vier Repos ueber
    # CoordinatorWriter) und Belegarten (event_types.py:82-87) stehen seit
    # Build 355-357 vollstaendig - erreichbar waren sie aber NUR ueber die
    # Kommandozeile (management/capacity/capacity_admin.py). Die Sicht aus
    # Build 360 zeigte Personen ohne Regel-Arbeitszeit folglich als graue
    # Balken ("keine Basis"): der Mangel war sichtbar, aber im Werkzeug nicht
    # behebbar. Hier steht deshalb NUR Rechte-, Scope- und Nutzlastpruefung;
    # jede Fachregel (Minutenschranken, genau EINES von value_pct/
    # value_minutes, aktiver reason_code, Zeitraumfolge) bleibt in den Repos,
    # damit Oberflaeche und Kommandozeile nicht auseinanderlaufen koennen.
    #
    # KEIN NEUES RECHT, KEINE MIGRATION (mc 2026-07-29). 'capacity.edit' ist
    # das Recht der Personalverantwortlichen. Die Unterscheidung traegt der
    # SCOPE, den der Lesepfad seit Build 359 bereits auswertet:
    #     'alle'   -> Kapazitaet BELIEBIGER Personen setzen (Leitung).
    #     'eigene' -> ausschliesslich die EIGENE Kapazitaet (Selbstpflege).
    # Damit ist die Selbstpflege GEBAUT, aber NICHT VERGEBEN - sie bleibt bis
    # zu einer ausdruecklichen Grant-Entscheidung unerreichbar. Eine
    # Aufspaltung in capacity.view/capacity.edit wurde VERWORFEN: keine
    # Migration im Bestand schreibt jemals einen Grant (rbac_grant.audit_seq
    # ist NOT NULL mit FK auf audit_log - eine Migration kann ein Recht gar
    # nicht BELEGT vergeben). Ein neues Leserecht waere also im Katalog
    # gestanden, ohne dass es jemand hat, und die Kapazitaetssicht waere fuer
    # alle dunkel geworden, bis jemand von Hand nachvergibt. Genau die stille
    # Funktionsluecke, die Grundregel 1 verbietet.
    #
    # ANLAGENWEITE DATEN SIND NICHT SELBSTPFLEGBAR. Feiertage und
    # Abwesenheitsgruende gehoeren keiner Person, sondern der Anlage: wer sie
    # aendert, verschiebt die Rechnung ALLER Personen. Sie verlangen deshalb
    # hart scope='alle'.
    #
    # KEIN SELBSTSCHUTZ-VERBOT, anders als bei /api/personnel/* (dort
    # management_app.py:116-118). Dort schuetzt es davor, sich selbst aus dem
    # eigenen Konto auszusperren. Eine Arbeitszeit sperrt niemanden aus; ein
    # Verbot haette nur verhindert, dass die Leitung ihre EIGENE Kapazitaet
    # eintraegt. Belegt wird jede Aenderung ohnehin (mc 2026-07-29:
    # "Alles wird dokumentiert und das reicht als Kontrolle aus").

    def _capacity_guard(self, actor_person_id: int, *,
                        target_person_id: Optional[int] = None,
                        anlagenweit: bool = False):
        """
        Gemeinsame Rechte-/Scope-Pruefung aller Kapazitaets-Schreibwege.

        -> None            : erlaubt
        -> Response (403)  : abgelehnt, MIT Begruendung (nie leer, nie stumm)

        'anlagenweit=True' fuer Feiertage/Gruende: diese verlangen scope='alle'
        unabhaengig von einer Zielperson.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CAPACITY):
            return self._forbidden(CAP_CAPACITY)
        scope = policy.scope(CAP_CAPACITY)
        if scope == "alle":
            return None
        if anlagenweit:
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_CAPACITY,
                "detail": "Scope 'eigene': anlagenweite Daten (Feiertage, "
                          "Abwesenheitsgruende) wirken auf ALLE Personen und "
                          "sind nicht selbstpflegbar."})
        if target_person_id is None or target_person_id != actor_person_id:
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_CAPACITY,
                "detail": "Scope 'eigene': nur die eigene Kapazitaet "
                          "(person_id=%s)." % actor_person_id})
        return None

    @staticmethod
    def _capacity_int(payload: Dict[str, Any], key: str,
                      default: Optional[int] = None):
        """
        Ganzzahl aus der Nutzlast. -> (wert, None) | (None, Response 400).
        Fehlt der Schluessel UND es gibt kein Default, ist das ein Fehler -
        kein stilles Ersetzen durch 0 (das waere eine erfundene Arbeitszeit).
        """
        raw = payload.get(key, "__missing__")
        if raw == "__missing__" or raw is None:
            if default is None:
                return None, Response.json(400, {
                    "error": "bad_request", "detail": "%s fehlt." % key})
            return default, None
        try:
            return int(raw), None
        except (TypeError, ValueError):
            return None, Response.json(400, {
                "error": "bad_request",
                "detail": "%s ist keine Ganzzahl (%r)." % (key, raw)})

    @staticmethod
    def _capacity_fehler(exc: CapacityError) -> Response:
        """
        CapacityError -> 400. Build 560: die Antwort nennt das schuldige FELD,
        wenn die Ausnahme es kennt, damit die Pflegemaske das Eingabefeld
        markieren kann. Kennt sie es nicht, steht 'feld' NICHT in der Antwort -
        die Oberflaeche zeigt dann die Meldung ohne Markierung, statt
        irgendein Feld zu raten.
        """
        body = {"error": "capacity", "detail": str(exc)}
        feld = getattr(exc, "feld", None)
        if feld:
            body["feld"] = feld
        return Response.json(400, body)

    def _capacity_repos(self, con: sqlite3.Connection):
        """Die vier Repos an EINEM CoordinatorWriter (ein Beleg je Schreibung)."""
        writer = CoordinatorWriter(con, AuditLog(con))
        return (WorktimeRepo(con, writer), AvailabilityRepo(con, writer),
                HolidayRepo(con, writer), ReasonRepo(con, writer))

    # ------------------------------------------------------------- lesen
    def _capacity_stammdaten(self, person_id: int,
                             query: Optional[Dict[str, List[str]]]) -> Response:
        """
        GET /api/capacity/stammdaten[?person_id=N][&include_deleted=1] — die
        PFLEGBAREN Rohdaten
        hinter der Rechnung: Regel-Arbeitszeiten, Abwesenheiten, Feiertage,
        Gruendekatalog. Recht 'capacity.edit'.

        Scope 'alle'   -> ohne person_id ALLE Personen, mit person_id gefiltert.
        Scope 'eigene' -> immer und ausschliesslich die eigene Person; eine
                          abweichende person_id wird ABGELEHNT und nicht etwa
                          stillschweigend auf die eigene umgebogen (sonst
                          zeigte die Maske Daten unter fremder Ueberschrift).

        Feiertage und Gruende sind anlagenweit und stehen JEDEM zu, der die
        Sicht sehen darf: ohne sie waeren die eigenen Abwesenheitszeilen nicht
        lesbar (reason_code waere ein nackter Code).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_CAPACITY):
            return self._forbidden(CAP_CAPACITY)
        scope = policy.scope(CAP_CAPACITY)

        target: Optional[int] = None
        raw = self._q1(query, "person_id")
        if raw is not None:
            try:
                target = int(raw)
            except (TypeError, ValueError):
                return Response.json(400, {
                    "error": "bad_request", "detail": "person_id ungueltig."})
        if scope != "alle":
            if target is not None and target != person_id:
                return Response.json(403, {
                    "error": "forbidden", "capability": CAP_CAPACITY,
                    "detail": "Scope 'eigene': nur die eigenen Stammdaten."})
            target = person_id

        # BUILD 562 — ENTFERNTE ZEILEN. 'Entfernen' ist in der Kapazitaet ein
        # SOFT-DELETE: die Zeile bleibt in der Datenbank und traegt deleted_at.
        # Sichtbar war sie danach nirgends mehr - und damit war eine
        # Auslassung entstanden, von der die Oberflaeche nichts wusste.
        #
        # ZWEI DINGE, DIE ZUSAMMENGEHOEREN:
        #   a) ?include_deleted=1 liefert sie mit aus.
        #   b) Die Zahl der ausgeblendeten Zeilen steht IMMER in der Antwort,
        #      auch ohne den Schalter. Sonst kann niemand wissen, dass es
        #      etwas einzublenden GIBT - eine stille Auslassung waere genau
        #      das, was Grundregel 1 verbietet.
        #
        # Deshalb wird EINMAL mit include_deleted=True gelesen und danach
        # gezaehlt bzw. gefiltert: eine zweite Abfrage nur zum Zaehlen koennte
        # ein anderes Ergebnis liefern als die erste (und waere teurer).
        include_deleted = self._q1(query, "include_deleted") in (
            "1", "true", "ja", "yes")

        con = self._ro_con()
        try:
            wt, av, ho, re_ = self._capacity_repos(con)
            alle_wt = wt.list_worktime(target, include_deleted=True)
            alle_av = av.list_availability(target, include_deleted=True)
            alle_ho = ho.list_holidays(include_deleted=True)
            alle_re = re_.list_reasons(include_deleted=True)

            def _geteilt(zeilen):
                """-> (sichtbare Zeilen, Zahl der entfernten)."""
                entfernt = [z for z in zeilen if z.get("deleted_at")]
                sichtbar = zeilen if include_deleted else [
                    z for z in zeilen if not z.get("deleted_at")]
                return sichtbar, len(entfernt)

            worktimes, ent_wt = _geteilt(alle_wt)
            availability, ent_av = _geteilt(alle_av)
            holidays, ent_ho = _geteilt(alle_ho)
            reasons, ent_re = _geteilt(alle_re)

            # NAMEN GEHOEREN DAZU (Nachtrag Build 559). Die Repos liefern
            # ausschliesslich person_id - fachlich richtig, denn sie kennen
            # die Personentabelle nicht. Eine Pflegemaske, die "#7" statt
            # "Mueller" anzeigt, ist fuer eine Leitung mit zwanzig Personen
            # aber unbenutzbar, und ein zweiter Abruf ueber /api/personnel
            # waere hier falsch: er verlangt 'personnel.view', das eine
            # Person mit 'capacity.edit' nicht haben muss. Die Aufloesung
            # gehoert deshalb an diese Stelle.
            personen = [
                {"id": r[0], "system_username": r[1], "display_name": r[2]}
                for r in con.execute(
                    "SELECT id, system_username, display_name FROM person "
                    "WHERE is_investigator=1 ORDER BY id ASC").fetchall()]
            if scope != "alle":
                personen = [p for p in personen if p["id"] == person_id]
            namen = {p["id"]: p for p in personen}

            def _mit_namen(zeilen):
                """Anzeigename an jede Zeile. FEHLT die Person, wird das
                BENANNT und nicht verschwiegen: eine Arbeitszeit ohne
                zugehoerigen Personendatensatz ist ein Befund, kein
                Darstellungsproblem (Grundregel 1)."""
                for z in zeilen:
                    pid = z.get("person_id")
                    treffer = namen.get(pid)
                    z["display_name"] = (treffer["display_name"] if treffer
                                         else "unbekannt (#%s)" % pid)
                    z["system_username"] = (treffer["system_username"]
                                            if treffer else None)
                return zeilen

            worktimes = _mit_namen(worktimes)
            availability = _mit_namen(availability)
        finally:
            con.close()

        return Response.json(200, {
            "scope": scope, "person_id": target,
            "persons": personen,
            "include_deleted": include_deleted,
            "worktimes": worktimes, "availability": availability,
            "holidays": holidays, "reasons": reasons,
            "counts": {"worktimes": len(worktimes),
                       "availability": len(availability),
                       "holidays": len(holidays),
                       "reasons": len(reasons),
                       "persons": len(personen)},
            # IMMER dabei, auch wenn nicht eingeblendet wird: erst diese Zahl
            # macht die Auslassung sichtbar. Bei include_deleted=1 sind die
            # gezaehlten Zeilen zugleich die mitgelieferten.
            "entfernt": {"worktimes": ent_wt, "availability": ent_av,
                         "holidays": ent_ho, "reasons": ent_re},
            # Die Rechenarten sind SCHEMAGEBUNDEN (m008: CHECK(kind IN ...))
            # und traegt die Arithmetik in capacity_calculator.py:110
            # (netto = max(basis - einschraenkungen, garantie_boden)). Sie
            # gehen deshalb als feste Liste an die Oberflaeche - anders als
            # die Gruende, die frei erweiterbar sind.
            "kinds": [{"code": "einschraenkung", "label": "Einschraenkung"},
                      {"code": "garantie", "label": "Garantie (Mindestboden)"}],
        })

    # ---------------------------------------------------------- schreiben
    def _capacity_worktime_set(self, actor_person_id: int,
                               payload: Dict[str, Any]) -> Response:
        """
        POST /api/capacity/worktime — {person_id, effective_from,
        mon_min..sun_min, effective_to?}. Recht 'capacity.edit'.

        APPEND-ONLY (mc 2026-07-10, Entscheidung 2): jede Schreibung erzeugt
        eine NEUE datierte Zeile; die Vorgaengerin wird NICHT geschlossen. Der
        Leser (Build 358) nimmt die Zeile mit groesstem effective_from <=
        Stichtag. Die Oberflaeche muss das benennen, sonst wirkt eine Korrektur
        wie ein Verlust der alten Angabe - sie steht aber noch da, als Beleg.
        """
        target_id, err = self._capacity_int(payload, "person_id")
        if err is not None:
            return err
        denied = self._capacity_guard(actor_person_id,
                                      target_person_id=target_id)
        if denied is not None:
            return denied

        effective_from = str(payload.get("effective_from", "") or "").strip()
        if not effective_from:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "effective_from fehlt (ISO-Datum)."})
        effective_to = payload.get("effective_to") or None

        minuten: Dict[str, int] = {}
        for tag in ("mon_min", "tue_min", "wed_min", "thu_min", "fri_min",
                    "sat_min", "sun_min"):
            wert, err = self._capacity_int(payload, tag, default=0)
            if err is not None:
                return err
            minuten[tag] = wert

        con = self._rw_con()
        try:
            wt, _, _, _ = self._capacity_repos(con)
            seq = wt.set_worktime(target_id, effective_from=effective_from,
                                  effective_to=effective_to,
                                  actor_id=actor_person_id,
                                  meta={"quelle": "capacity_ui"}, **minuten)
        except CapacityError as exc:
            return self._capacity_fehler(exc)
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Arbeitszeit setzen fehlgeschlagen")
            return Response.json(500, {"error": "capacity_worktime_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "person_id": target_id,
                                   "effective_from": effective_from,
                                   "audit_seq": seq})

    def _capacity_worktime_remove(self, actor_person_id: int,
                                 payload: Dict[str, Any]) -> Response:
        """
        POST /api/capacity/worktime/remove — {worktime_id}. SOFT-DELETE.

        Wie beim Entfernen einer Abwesenheit steht die Zielperson NICHT in der
        Nutzlast, sondern an der Zeile: die person_id wird deshalb VOR der
        Scope-Pruefung gelesen.
        """
        worktime_id, err = self._capacity_int(payload, "worktime_id")
        if err is not None:
            return err

        con = self._rw_con()
        try:
            row = con.execute(
                "SELECT person_id FROM person_worktime WHERE id=?",
                (worktime_id,)).fetchone()
            if row is None:
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "Unbekannte worktime_id=%s." % worktime_id,
                    "feld": "worktime_id"})
            denied = self._capacity_guard(actor_person_id,
                                          target_person_id=int(row[0]))
            if denied is not None:
                return denied
            wt, _, _, _ = self._capacity_repos(con)
            seq = wt.remove_worktime(worktime_id, actor_id=actor_person_id,
                                     meta={"quelle": "capacity_ui"})
        except CapacityError as exc:
            return self._capacity_fehler(exc)
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Arbeitszeit entfernen fehlgeschlagen")
            return Response.json(500, {"error": "capacity_worktime_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "worktime_id": worktime_id,
                                   "audit_seq": seq})

    def _capacity_worktime_replace(self, actor_person_id: int,
                                   payload: Dict[str, Any]) -> Response:
        """
        POST /api/capacity/worktime/replace — {worktime_id, person_id,
        effective_from, mon_min..sun_min, effective_to?}.

        ERSETZEN IST EINE EIGENE HANDLUNG und nicht zwei Aufrufe hintereinander:
        zwischen einem Entfernen und einem Setzen laege sonst ein Zustand, in
        dem die Person zum Stichtag GAR KEINE Regel hat - und bricht der zweite
        Aufruf ab, bleibt sie darin stehen. Das Repo fuehrt beides in EINER
        Transaktion mit ZWEI Belegen aus (audited_write_many).

        DIE SCOPE-PRUEFUNG LAEUFT ZWEIMAL: einmal gegen die Person der ALTEN
        Zeile, einmal gegen die Zielperson der neuen. Sonst koennte eine
        selbstpflegende Person eine fremde Zeile entfernen, indem sie als
        Zielperson sich selbst angibt.
        """
        worktime_id, err = self._capacity_int(payload, "worktime_id")
        if err is not None:
            return err
        target_id, err = self._capacity_int(payload, "person_id")
        if err is not None:
            return err

        effective_from = str(payload.get("effective_from", "") or "").strip()
        if not effective_from:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "effective_from fehlt (ISO-Datum).",
                "feld": "effective_from"})
        effective_to = payload.get("effective_to") or None

        minuten: Dict[str, int] = {}
        for tag in ("mon_min", "tue_min", "wed_min", "thu_min", "fri_min",
                    "sat_min", "sun_min"):
            wert, err = self._capacity_int(payload, tag, default=0)
            if err is not None:
                return err
            minuten[tag] = wert

        con = self._rw_con()
        try:
            row = con.execute(
                "SELECT person_id FROM person_worktime WHERE id=?",
                (worktime_id,)).fetchone()
            if row is None:
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "Unbekannte worktime_id=%s." % worktime_id,
                    "feld": "worktime_id"})
            for pid in (int(row[0]), target_id):
                denied = self._capacity_guard(actor_person_id,
                                              target_person_id=pid)
                if denied is not None:
                    return denied
            wt, _, _, _ = self._capacity_repos(con)
            seqs = wt.replace_worktime(
                worktime_id, target_id, effective_from=effective_from,
                effective_to=effective_to, actor_id=actor_person_id,
                meta={"quelle": "capacity_ui"}, **minuten)
        except CapacityError as exc:
            return self._capacity_fehler(exc)
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Arbeitszeit ersetzen fehlgeschlagen")
            return Response.json(500, {"error": "capacity_worktime_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "worktime_id": worktime_id,
                                   "person_id": target_id,
                                   "effective_from": effective_from,
                                   "audit_seq": seqs["gesetzt_seq"],
                                   **seqs})

    def _capacity_availability_set(self, actor_person_id: int,
                                   payload: Dict[str, Any]) -> Response:
        """
        POST /api/capacity/availability — {person_id, period_start, period_end,
        kind, value_pct? | value_minutes?, reason_code?, note?}.
        Recht 'capacity.edit'.

        'kind' wird NICHT hier geprueft: das Repo kennt die Positivliste
        ('garantie'/'einschraenkung'), das Schema erzwingt sie per CHECK. Eine
        zweite Kopie der Liste an dieser Stelle wuerde eines Tages von der
        ersten abweichen.
        """
        target_id, err = self._capacity_int(payload, "person_id")
        if err is not None:
            return err
        denied = self._capacity_guard(actor_person_id,
                                      target_person_id=target_id)
        if denied is not None:
            return denied

        period_start = str(payload.get("period_start", "") or "").strip()
        period_end = str(payload.get("period_end", "") or "").strip()
        kind = str(payload.get("kind", "") or "").strip()
        if not (period_start and period_end and kind):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "period_start, period_end und kind sind Pflicht."})

        value_pct = payload.get("value_pct")
        value_minutes = payload.get("value_minutes")
        try:
            value_pct = None if value_pct is None else int(value_pct)
            value_minutes = (None if value_minutes is None
                             else int(value_minutes))
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "value_pct/value_minutes muessen Ganzzahlen sein."})

        reason_code = payload.get("reason_code") or None
        note = payload.get("note") or None

        con = self._rw_con()
        try:
            _, av, _, _ = self._capacity_repos(con)
            seq = av.set_availability(
                target_id, period_start=period_start, period_end=period_end,
                kind=kind, value_pct=value_pct, value_minutes=value_minutes,
                reason_code=reason_code, note=note,
                actor_id=actor_person_id, meta={"quelle": "capacity_ui"})
        except CapacityError as exc:
            return self._capacity_fehler(exc)
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Abwesenheit setzen fehlgeschlagen")
            return Response.json(500, {"error": "capacity_availability_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "person_id": target_id,
                                   "audit_seq": seq})

    def _capacity_availability_remove(self, actor_person_id: int,
                                      payload: Dict[str, Any]) -> Response:
        """
        POST /api/capacity/availability/remove — {entry_id}. Soft-Delete.

        DIE FALLE: die Zielperson steht NICHT in der Nutzlast, sondern an der
        Zeile. Die Scope-Pruefung muss die person_id des Eintrags deshalb
        ZUERST lesen - sonst koennte eine selbstpflegende Person fremde
        Eintraege ueber deren ID entfernen, obwohl sie sie nie sehen konnte.
        """
        entry_id, err = self._capacity_int(payload, "entry_id")
        if err is not None:
            return err

        con = self._rw_con()
        try:
            row = con.execute(
                "SELECT person_id FROM availability_entry WHERE id=?",
                (entry_id,)).fetchone()
            if row is None:
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "Unbekannte entry_id=%s." % entry_id})
            denied = self._capacity_guard(actor_person_id,
                                          target_person_id=int(row[0]))
            if denied is not None:
                return denied
            _, av, _, _ = self._capacity_repos(con)
            seq = av.remove_availability(entry_id, actor_id=actor_person_id,
                                         meta={"quelle": "capacity_ui"})
        except CapacityError as exc:
            return self._capacity_fehler(exc)
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Abwesenheit entfernen fehlgeschlagen")
            return Response.json(500, {"error": "capacity_availability_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "entry_id": entry_id,
                                   "audit_seq": seq})

    def _capacity_holiday_add(self, actor_person_id: int,
                              payload: Dict[str, Any]) -> Response:
        """POST /api/capacity/holiday — {day, label, region?}. Nur scope 'alle'."""
        denied = self._capacity_guard(actor_person_id, anlagenweit=True)
        if denied is not None:
            return denied
        day = str(payload.get("day", "") or "").strip()
        label = str(payload.get("label", "") or "").strip()
        if not (day and label):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "day (ISO-Datum) und label sind Pflicht."})
        region = payload.get("region") or None

        con = self._rw_con()
        try:
            _, _, ho, _ = self._capacity_repos(con)
            seq = ho.add_holiday(day, label, region=region,
                                 actor_id=actor_person_id,
                                 meta={"quelle": "capacity_ui"})
        except CapacityError as exc:
            return self._capacity_fehler(exc)
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Feiertag anlegen fehlgeschlagen")
            return Response.json(500, {"error": "capacity_holiday_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "day": day,
                                   "audit_seq": seq})

    def _capacity_holiday_remove(self, actor_person_id: int,
                                 payload: Dict[str, Any]) -> Response:
        """POST /api/capacity/holiday/remove — {holiday_id}. Nur scope 'alle'."""
        denied = self._capacity_guard(actor_person_id, anlagenweit=True)
        if denied is not None:
            return denied
        holiday_id, err = self._capacity_int(payload, "holiday_id")
        if err is not None:
            return err

        con = self._rw_con()
        try:
            row = con.execute("SELECT 1 FROM holiday WHERE id=?",
                              (holiday_id,)).fetchone()
            if row is None:
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "Unbekannte holiday_id=%s." % holiday_id})
            _, _, ho, _ = self._capacity_repos(con)
            seq = ho.remove_holiday(holiday_id, actor_id=actor_person_id,
                                    meta={"quelle": "capacity_ui"})
        except CapacityError as exc:
            return self._capacity_fehler(exc)
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Feiertag entfernen fehlgeschlagen")
            return Response.json(500, {"error": "capacity_holiday_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "holiday_id": holiday_id,
                                   "audit_seq": seq})

    def _capacity_reason_add(self, actor_person_id: int,
                             payload: Dict[str, Any]) -> Response:
        """
        POST /api/capacity/reason — {code, label, sort?}. Nur scope 'alle'.

        DER FREI ERWEITERBARE KATALOG (mc 2026-07-29): "Urlaub", "Krank",
        "Schulung", "anderer Dienstauftrag" - welche Abwesenheitsarten im Lauf
        der Zeit legitim sind, entscheidet die Leitung, nicht der Code. Genau
        deshalb ist 'reason_code' ein Katalog und 'kind' eine feste Rechenart:
        die eine Liste waechst, die andere darf es nicht.
        """
        denied = self._capacity_guard(actor_person_id, anlagenweit=True)
        if denied is not None:
            return denied
        code = str(payload.get("code", "") or "").strip()
        label = str(payload.get("label", "") or "").strip()
        if not (code and label):
            return Response.json(400, {
                "error": "bad_request", "detail": "code und label sind Pflicht."})
        sort, err = self._capacity_int(payload, "sort", default=0)
        if err is not None:
            return err

        con = self._rw_con()
        try:
            _, _, _, re_ = self._capacity_repos(con)
            seq = re_.add_reason(code, label, sort=sort,
                                 actor_id=actor_person_id,
                                 meta={"quelle": "capacity_ui"})
        except CapacityError as exc:
            return self._capacity_fehler(exc)
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Abwesenheitsgrund anlegen fehlgeschlagen")
            return Response.json(500, {"error": "capacity_reason_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "code": code,
                                   "audit_seq": seq})

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

    # ---------------------------------------------------------------- Build 522
    # AP-3F / Idee 40: Prognosebericht (3 Szenarien) als vorlegbarer Beleg.

    def _forecast_report(self, person_id: int, query) -> Response:
        """
        GET /api/forecast/report?format=pdf|html — der Prognosebericht.

        RECHTE GENAU WIE /api/forecast: CAP_STATS ('stats.export_sta') UND
        Scope 'alle'. Das ist bewusst KEIN eigenes Recht — der Bericht enthaelt
        keine einzige Angabe, die die Sicht 'planung' nicht schon zeigt. Ein
        zweites Recht haette nur eine zweite Stelle geschaffen, an der ein
        Grant vergessen werden kann; und ein Export, der MEHR darf als die
        Sicht, waere ein Loch in der Zweckbindung.

        FORMAT: 'pdf' (Vorgabe) oder 'html'. Ein unbekanntes Format ist ein
        400 mit Nennung der gueltigen Werte — NICHT ein stiller Rueckfall auf
        PDF. Wer 'xlsx' anfragt, soll erfahren, dass es das nicht gibt, statt
        etwas anderes zu bekommen, als er wollte.

        FEHLT reportlab -> 503 mit Klartext und Hinweis auf das Offline-Wheel
        (Muster forensic_api/export.py:219-224). Kein leeres PDF, kein Rueckfall
        auf HTML: ein anderes Format als das angeforderte waere eine stille
        Ersetzung.

        DER BERICHT SCHREIBT NICHTS. Rein lesend (mode=ro), kein
        CoordinatorWriter, keine Migration — der Migrationsvorbehalt ab
        01.07.2026 ist nicht beruehrt.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_STATS) or policy.scope(CAP_STATS) != "alle":
            return self._forbidden(CAP_STATS)

        fmt = str(self._q1(query, "format") or "pdf").lower()
        if fmt not in ("pdf", "html"):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "Unbekanntes Format '%s'. Gueltig: pdf, html." % fmt,
                "known": ["pdf", "html"],
            })

        # Das Rueckblickfenster ist uebersteuerbar (wie in der CLI), damit der
        # Beleg denselben Ausschnitt abbilden kann, den die Leitung betrachtet.
        # Ein unbrauchbarer Wert ist ein 400 — nicht ein stillschweigend
        # ersetzter Vorgabewert, der die Zahlen unerklaerlich machen wuerde.
        raw_lb = self._q1(query, "lookback_days")
        lookback = 30
        if raw_lb is not None and str(raw_lb) != "":
            try:
                lookback = int(raw_lb)
            except (TypeError, ValueError):
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "lookback_days muss eine ganze Zahl sein."})
            if lookback <= 0:
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "lookback_days muss > 0 sein."})

        con = self._ro_con()
        try:
            result = Forecaster(con).compute(now_ts=int(time.time()),
                                             lookback_days=lookback)
            forecast = forecast_to_dict(result)
            person = self._person(con, person_id)
            actor = person.get("system_username") if person else None
            ctx = build_export_context(
                con=con, db_path=self._db_path, actor=actor,
                aktenzeichen="Prognosebericht (3 Szenarien)")
        except Exception as exc:                        # noqa: BLE001
            logger.exception("Prognosebericht fehlgeschlagen")
            return Response.json(500, {"error": "forecast_report_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        if fmt == "html":
            return Response.html(
                200, build_forecast_report_html(forecast, ctx))

        try:
            data = build_forecast_report_pdf(forecast, ctx)
        except ForecastReportUnavailable as exc:
            return Response.json(503, {
                "error": "pdf_unavailable",
                "detail": "reportlab nicht installiert (%s). Bitte "
                          "Offline-Wheel bereitstellen (setup/wheels; "
                          "reportlab in RUNTIME_PACKAGES, Build 404)." % exc})
        except Exception as exc:                        # noqa: BLE001
            logger.exception("PDF-Erzeugung des Prognoseberichts "
                             "fehlgeschlagen")
            return Response.json(500, {"error": "forecast_report_failed",
                                       "detail": str(exc)})

        # Der Dateiname traegt den Stichtag — ein Prognosebeleg ohne Stichtag
        # ist in der Akte nicht zuordenbar (zwei Prognosen unterscheiden sich
        # nur durch ihn).
        stichtag = str(forecast.get("now_day") or "ohne-datum")
        return Response.pdf(200, data,
                            filename="AIW-Prognose_%s.pdf" % stichtag)

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

    #: Build 534: Obergrenze der ausdruecklich angefragten Kennungen in
    #  /api/assignable/stats?subject_ids=… Sie schuetzt vor einer URL, die den
    #  Server dazu braechte, beliebig viele Dateien zu oeffnen. Der Wert liegt
    #  weit ueber der Zahl der derzeit gefuehrten Faelle; wer wirklich ALLE
    #  will, laesst den Parameter weg.
    _STATS_MAX_IDS = 2000

    def _assignable_stats(self, person_id: int,
                          query: Optional[Dict[str, List[str]]]) -> Response:
        """
        Kennzahlen je Fall aus uid_stats der forensic_<uid>.db (Build 534).

        Zweck: die Zuweisungs-Sicht soll zusaetzliche Spalten anbieten koennen
        (Beitraege, private Nachrichten, Downloads, geteilte Dateien und was
        sonst in uid_stats steht). Welche Spalten es GIBT, steht erst nach dem
        Lesen fest — uid_stats ist key-value. Die Antwort enthaelt deshalb
        einen KATALOG, aus dem die Oberflaeche ihre Spaltenauswahl baut.

        RECHTE: dieselben wie /api/assignable (assignment.edit, Scope 'alle').
        Wer die Zuweisung nicht sehen darf, bekommt auch ihre Kennzahlen nicht.

        'force=1' umgeht den prozesslokalen Fingerabdruck-Speicher und liest
        alle Dateien neu — niemand soll einem Zwischenspeicher ausgeliefert
        sein, dem er nicht traut (Muster /api/reports).

        'subject_ids=18,19,20' liest GENAU diese Kennungen — auch solche, die
        (noch) NICHT in der Fallakte stehen. Das braucht die Sicht
        'Fall-Erkennung': dort werden die auf der Platte gefundenen
        forensic_<uid>.db gezeigt, BEVOR sie aufgenommen sind. Ohne diesen
        Weg haette ausgerechnet die Sicht, in der man ueber die Aufnahme
        entscheidet, keine Kennzahlen (mc 2026-07-26: einheitliche Masken).

        REIN LESEND. Die forensic_<uid>.db werden mit mode=ro geoeffnet; der
        Migrationsvorbehalt ab 01.07.2026 ist nicht beruehrt.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_ASSIGNMENT):
            return self._forbidden(CAP_ASSIGNMENT)
        if policy.scope(CAP_ASSIGNMENT) != "alle":
            return Response.json(403, {
                "error": "forbidden", "capability": CAP_ASSIGNMENT,
                "detail": "Zuweisen erfordert Scope 'alle'."})

        q = query or {}
        force = (q.get("force") or ["0"])[0] in ("1", "true", "yes")

        roh_ids = (q.get("subject_ids") or [""])[0].strip()
        subject_ids: Optional[List[int]] = None
        if roh_ids:
            teile = [t.strip() for t in roh_ids.split(",") if t.strip()]
            if len(teile) > self._STATS_MAX_IDS:
                return Response.json(400, {
                    "error": "too_many",
                    "detail": "%d Kennungen ueberschreiten die Grenze von %d."
                              % (len(teile), self._STATS_MAX_IDS)})
            try:
                subject_ids = [int(t) for t in teile]
            except ValueError:
                # Kein Teil-Ergebnis aus einer halb lesbaren Liste: eine
                # unlesbare Kennung wuerde sonst still fehlen, und die Liste
                # saehe vollstaendig aus (Grundregel 1).
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "subject_ids enthaelt eine unlesbare Kennung: "
                              "%r" % roh_ids})

        con = self._ro_con()
        try:
            report = UidStatsRepo(con, self._forensic_dir).collect(
                subject_ids=subject_ids, use_cache=not force)
        except Exception as exc:   # kein stiller Fehlschlag (Grundregel 1)
            logger.exception("Kennzahlen-Abruf fehlgeschlagen")
            return Response.json(500, {"error": "stats_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        payload = report.to_dict()
        payload["forensic_dir"] = str(self._forensic_dir)
        return Response.json(200, payload)

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
    # BERICHT ALS VORLAGE UEBERNEHMEN (Build 475 — Vermaehlung B6xB7).
    #   GET /api/report/as-template-draft?subject_id=<uid>[&report_id=<rid>]
    #   Liefert einen schreibfreien Vorlagen-ENTWURF aus einem bestehenden
    #   Bericht. Read-only (ReadonlyReportBundle, mode=ro) — schreibt NICHTS in
    #   evidence_<uid>.db. Die Sanitisierung (Platzhalter-Werte entfernt,
    #   evidence_ids geleert) liegt zentral im ReportTemplateExtractor.
    #
    #   RECHTE: reports.review ODER reports.approve (identisch zu
    #   /api/report/render); Scope 'eigene' -> nur zugewiesene Faelle. Das
    #   SPEICHERN der Vorlage erfordert zusaetzlich templates.edit und laeuft
    #   ueber den bestehenden auditierten Pfad POST /api/templates/document —
    #   die Doppelbindung schraenkt das Feature faktisch auf die 'supervisor'
    #   ein (operative Grant-Entscheidung, nicht Teil dieses Builds).
    # =====================================================================
    def _report_as_template_draft(self, person_id: int,
                                  query: Optional[Dict[str, List[str]]]
                                  ) -> Response:
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

        # Scope 'eigene': der Fall muss dem Anfragenden zugewiesen sein
        # (identische Regel wie _report_render).
        if scope != "alle":
            if self._case_field(uid, "assigned_to") != person_id:
                return self._forbidden(CAP_REPORTS_REVIEW)

        from management.reports.readonly_report_bundle import (
            ReadonlyReportBundle,
        )
        from management.templates_admin.report_template_extractor import (
            ReportTemplateExtractor, NoReportForTemplateError,
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
            result = ReportTemplateExtractor(bundle.evidence).build_draft(
                report_id)
        except NoReportForTemplateError as exc:
            return Response.json(404, {"error": "no_report",
                                       "subject_id": uid, "detail": str(exc)})
        except Exception as exc:  # pragma: no cover - defensiver 500
            logger.exception(
                "as-template-draft fehlgeschlagen (uid=%s, report_id=%s)",
                uid, report_id,
            )
            return Response.json(500, {"error": "draft_failed",
                                       "detail": str(exc)})
        finally:
            bundle.close()

        logger.info(
            "Vorlagen-Entwurf aus Bericht: uid=%d report_id=%s, %d Bloecke, "
            "%d Befunde, %d Warnungen (person=%d, scope=%s)",
            uid, result.get("report_id"), len(result["draft"]["blocks"]),
            len(result["findings"]), len(result["warnings"]), person_id, scope,
        )
        return Response.json(200, {
            "ok": True,
            "draft": result["draft"],
            "findings": result["findings"],
            "warnings": result["warnings"],
        })

    # =====================================================================
    # AUTHORING: PLATZHALTER (Build 489, W2 — templates.db.placeholders).
    #   Nachfolger der Platzhalter-Queries (Build 422): EINE Tabelle fuer alle
    #   drei Typen a/m/o inkl. Validierung (Bauplan Platzhalter_DB v0.1,
    #   mc-Freigabe 2026-07-21).
    #   GET  /api/templates/placeholders       — Liste (Recht templates.edit)
    #   POST /api/templates/placeholder        — anlegen/aendern (validiert +
    #                                            optionaler fdb-Dry-Run,
    #                                            auditiert, target_type
    #                                            'placeholder')
    #   POST /api/templates/placeholder/dryrun — SCHREIBFREIE Vorschau
    #   Build 490: die Legacy-Aliase (/api/templates/queries, .../query
    #   [+/dryrun]) sind mit dem Maskenumbau entfallen. Ein fehlender 'type'
    #   im Payload wird weiterhin defensiv als 'a' gedeutet.
    # =====================================================================
    def _templates_placeholders(self, person_id: int) -> Response:
        """Liste aller Platzhalter (read-only, alle Typen)."""
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)
        from management.templates_admin.placeholder_repo import (
            PlaceholderAuthorRepo,
        )
        con = self._templates_ro_con()
        try:
            items = PlaceholderAuthorRepo(con).list()
        except sqlite3.Error as exc:
            return Response.json(500, {"error": "templates_read_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"count": len(items),
                                   "placeholders": items})

    def _placeholder_from_payload(self,
                                  payload: Dict[str, Any]) -> Dict[str, Any]:
        """Payload -> Platzhalter-Dict. Fehlender type -> 'a' (Legacy-Maske)."""
        return {
            "id": payload.get("id"),
            "title": payload.get("title"),
            "description": payload.get("description", ""),
            "type": payload.get("type") or "a",
            "sql_query": payload.get("sql_query"),
            "default_value": payload.get("default_value"),
            "validation": payload.get("validation"),
            "validation_type": payload.get("validation_type"),
            # Build 497: case-insensitive-Flag (0/1) fuer regex/list/like.
            "validation_ci": payload.get("validation_ci"),
            "tags": payload.get("tags"),
            "return_type": payload.get("return_type") or "scalar",
        }

    def _placeholder_dry(self, p: Dict[str, Any],
                         payload: Dict[str, Any],
                         errors: List[str]) -> Dict[str, Any]:
        """Optionaler fdb-Dry-Run der (Default-)Query. Fehler -> errors."""
        from management.templates_admin.placeholder_validator import (
            dry_run, PlaceholderValidationError,
        )
        if not str(p.get("sql_query") or "").strip():
            return {"ran": False,
                    "reason": "kein sql_query (statischer Platzhalter)."}
        test_uid_raw = payload.get("test_subject_id")
        if test_uid_raw in (None, ""):
            return {"ran": False, "reason": "kein test_subject_id."}
        try:
            test_uid = int(test_uid_raw)
        except (TypeError, ValueError):
            errors.append("test_subject_id ungueltig (ganze Zahl erwartet).")
            return {"ran": False, "reason": "test_subject_id ungueltig."}
        fdb_path = "%s/forensic_%d.db" % (
            str(self._forensic_dir).rstrip("/"), test_uid)
        try:
            return dry_run(p["sql_query"], test_uid, fdb_path,
                           return_type=p["return_type"])
        except PlaceholderValidationError as exc:
            errors.extend(exc.errors)
            return {"ran": True, "failed": True}

    def _templates_placeholder_upsert(self, person_id: int,
                                      payload: Dict[str, Any]) -> Response:
        """
        Legt einen Platzhalter an oder aendert ihn. Ablauf:
          1. Recht templates.edit.
          2. Statische Validierung (placeholder_validator; Typregeln a/m/o).
             warnings blockieren NICHT (Grundregel 11), errors -> 400.
          3. Optionaler fdb-Dry-Run (nur wenn sql_query + test_subject_id).
          4. Auditiertes Upsert (TemplatesWriter, target_type 'placeholder').
        """
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)

        from management.templates_admin.placeholder_validator import (
            validate_static,
        )
        from management.templates_admin.placeholder_repo import (
            PlaceholderAuthorRepo,
        )

        p = self._placeholder_from_payload(payload)
        errors, warnings = validate_static(p)
        if errors:
            return Response.json(400, {"error": "validation", "errors": errors,
                                       "warnings": warnings})

        dry_errors: List[str] = []
        dry = self._placeholder_dry(p, payload, dry_errors)
        if dry_errors:
            return Response.json(400, {"error": "dry_run",
                                       "errors": dry_errors,
                                       "warnings": warnings})

        # Auditiertes Upsert.
        con = self._ro_con()
        try:
            who = self._person(con, person_id)
        finally:
            con.close()
        changed_by = who["system_username"] if who else str(person_id)

        tcon = self._templates_rw_con()
        try:
            result = PlaceholderAuthorRepo(tcon).upsert(
                p, changed_by=changed_by)
        except sqlite3.Error as exc:
            return Response.json(500, {"error": "templates_write_failed",
                                       "detail": str(exc)})
        finally:
            tcon.close()

        logger.info("Platzhalter %s [%s] (%s) von %s",
                    result["target_id"], p["type"],
                    "angelegt" if result["created"] else "geaendert",
                    changed_by)
        return Response.json(200, {"ok": True, "target_id": result["target_id"],
                                   "created": result["created"],
                                   "dry_run": dry, "warnings": warnings})

    def _templates_placeholder_dryrun(self, person_id: int,
                                      payload: Dict[str, Any]) -> Response:
        """
        SCHREIBFREIE Vorschau (Build 423/489, W2-Frontend): validiert einen
        Platzhalter STATISCH (Typregeln a/m/o) und fuehrt - falls sql_query und
        test_subject_id gesetzt sind - den fdb-Dry-Run READ-ONLY aus. Es wird
        NICHTS geschrieben und NICHTS auditiert (kein Beleg entsteht, weil kein
        Zustand sich aendert). So kann die Redakteur:in testen, BEVOR sie
        speichert (Grundregel: Ueberpruefbarkeit; keine stille Fehlaufloesung).

        Antwort IMMER 200 mit {ok, errors, warnings, dry_run} - Fehler werden
        als DATEN geliefert (nicht als HTTP-Fehler), damit die Editor-Maske sie
        zusammen mit dem Dry-Run-Ergebnis anzeigen kann. warnings (z.B.
        Python-re konnte eine JS-Regex nicht kompilieren) blockieren nicht
        (Grundregel 11). Das Recht bleibt Voraussetzung (403 ohne
        templates.edit); ein POST erfordert - wie jeder Schreibpfad - das
        X-AIW-Token (im HTTP-Handler geprueft), obwohl hier nichts geschrieben
        wird (bewusst: einheitlicher POST-Pfad).
        """
        if not self.resolve_policy(person_id).can(CAP_TEMPLATES_EDIT):
            return self._forbidden(CAP_TEMPLATES_EDIT)

        from management.templates_admin.placeholder_validator import (
            validate_static,
        )

        p = self._placeholder_from_payload(payload)
        errors, warnings = validate_static(p)

        dry: Dict[str, Any] = {"ran": False, "reason": "kein test_subject_id."}
        # Dry-Run nur, wenn die statische Pruefung sauber ist (eine kaputte
        # Query gar nicht erst gegen die fdb ausfuehren).
        if not errors:
            dry = self._placeholder_dry(p, payload, errors)

        return Response.json(200, {"ok": not errors, "errors": errors,
                                   "warnings": warnings, "dry_run": dry})

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
        """
        Baut das Modul-dict aus dem Payload (Basis fuer Upsert und Dry-Run).

        Build 564: 'id' wird MITGEFUEHRT. Sie ist nur fuer EINEN Fall da - das
        Nachtragen eines fehlenden module_key an einer Altzeile. Der Validator
        ignoriert sie; das Repo entscheidet, ob sie greift (nur bei
        module_key IS NULL) und weist jeden anderen Gebrauch zurueck.
        """
        return {
            "id": payload.get("id"),
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
        from management.templates_admin.module_repo import (
            ModuleAuthorRepo, ModuleKeyAssignError,
        )

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
        except ModuleKeyAssignError as exc:
            # 400 statt 500: das ist eine Beanstandung der Eingabe, kein
            # Serverfehler - und sie NENNT das schuldige Feld, damit die
            # Maske es markieren kann (Muster aus Build 560).
            body = {"error": "validation", "errors": [str(exc)]}
            if getattr(exc, "feld", None):
                body["feld"] = exc.feld
            return Response.json(400, body)
        except sqlite3.Error as exc:
            return Response.json(500, {"error": "templates_write_failed",
                                       "detail": str(exc)})
        finally:
            tcon.close()

        logger.info("Baustein-Modul %s (%s%s) von %s",
                    result["target_id"],
                    "angelegt" if result["created"] else "geaendert",
                    ", Schluessel nachgetragen" if result.get("nachtrag") else "",
                    changed_by)
        return Response.json(200, {"ok": True, "target_id": result["target_id"],
                                   "created": result["created"],
                                   "nachtrag": bool(result.get("nachtrag"))})

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

        # Build 564: Wird ein Schluessel NACHGETRAGEN (id gesetzt), prueft die
        # Vorschau denselben Weg wie das Speichern - schreibfrei. Sonst saehe
        # die Vorschau gruen aus und das Speichern schluege fehl, und der
        # Ausfuellende haette die Vorschau umsonst gemacht.
        if not errors and m.get("id") not in (None, ""):
            from management.templates_admin.module_repo import (
                ModuleAuthorRepo, ModuleKeyAssignError,
            )
            tcon = self._templates_ro_con()
            try:
                repo = ModuleAuthorRepo(tcon)
                ziel = repo.get_by_id(int(m["id"]))
                schluessel = str(m.get("module_key") or "").strip()
                if ziel is None:
                    errors.append("Unbekanntes Baustein-Modul (id=%s)."
                                  % m["id"])
                elif ziel.get("module_key"):
                    errors.append(
                        "Das Modul traegt bereits den Schluessel '%s'. Ein "
                        "module_key ist eine stabile Kennung, auf die "
                        "Berichtsvorlagen verweisen - er wird nicht "
                        "umgetragen." % ziel["module_key"])
                else:
                    kollision = repo.get_by_key(schluessel)
                    if kollision is not None:
                        errors.append(
                            "Der Schluessel '%s' ist bereits vergeben "
                            "(Modul id=%s, '%s')."
                            % (schluessel, kollision["id"],
                               kollision["title"]))
            except (ValueError, sqlite3.Error) as exc:
                errors.append("Pruefung des Schluessels fehlgeschlagen: %s"
                              % exc)
            finally:
                tcon.close()

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

    # ------------------------------------------------- AD-Abgleich (Build 502)
    def _adsync_provider(self):
        """
        Mitgliederquelle des AD-Abgleichs: injiziert (Test) oder lazy aus
        config.yaml (PROD). Wirft LdapError bei leerer ad.ldap-Konfiguration
        (DEFAULT-DENY) — der Aufrufer uebersetzt das in eine Klartext-Antwort.
        """
        if self._ad_members_provider is not None:
            return self._ad_members_provider
        return LdapGroupReader.from_config()

    class _NullProvider:
        """
        Platzhalter fuer /api/adsync/decide: die Einzel-Entscheidung arbeitet
        NUR auf der coordinator.db und darf nicht daran scheitern, dass das
        Live-AD gerade nicht erreichbar/konfiguriert ist (die Kandidatenliste
        stammt aus der zuvor geladenen Vorschau). fetch_members() ist hier
        bewusst verboten — ein Aufruf waere ein Programmierfehler.
        """
        target_group = ""

        def fetch_members(self):  # pragma: no cover — Schutzgelaender
            raise AdSyncError(
                "Interner Fehler: decide-Pfad darf das AD nicht abfragen.")

    def _adsync(self, actor_person_id: int) -> Response:
        """
        GET /api/adsync — Vorschau des AD-Abgleichs (Recht personnel.sync).
        REIN LESEND: Live-AD abfragen, Plan bilden, KEIN Beleg, KEIN Write
        (mode=ro-Verbindung; erst der Vollzug belegt). Liefert zusaetzlich
        die woertlichen Bestaetigungen, damit die Oberflaeche exakt die
        serverseitig geprueften Worte anzeigt (eine Wahrheitsquelle).
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_PERSONNEL_SYNC):
            return self._forbidden(CAP_PERSONNEL_SYNC)

        try:
            provider = self._adsync_provider()
        except LdapError as exc:
            return Response.json(502, {"error": "ldap_failed",
                                       "detail": str(exc)})
        con = self._ro_con()
        try:
            executor = SyncExecutor(
                con, CoordinatorWriter(con, AuditLog(con)), provider)
            plan = executor.preview()
        except LdapError as exc:
            return Response.json(502, {"error": "ldap_failed",
                                       "detail": str(exc)})
        except AdSyncPlanError as exc:
            # Glitch-Schutz (leere/mehrdeutige AD-Antwort): Klartext statt
            # eines Plans, der alle Ermittler zu Kandidaten machen wuerde.
            return Response.json(502, {"error": "ad_plan_invalid",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("AD-Abgleich-Vorschau fehlgeschlagen")
            return Response.json(500, {"error": "adsync_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        return Response.json(200, {
            "group": provider.target_group,
            "confirm": {"deactivate": CONFIRM_DEACTIVATE,
                        "reactivate": CONFIRM_REACTIVATE},
            **plan.as_dict(),
        })

    def _adsync_apply(self, actor_person_id: int) -> Response:
        """
        POST /api/adsync/apply — vollzieht die NICHT bestaetigungspflichtigen
        Planteile (Neuaufnahmen als investigator [Flag + person_role],
        Namensaenderungen) und schreibt die AD_SYNC_RUN-Klammer. Kandidaten
        werden hier NIE angefasst (Einzel-Entscheidung via /api/adsync/decide).
        Recht personnel.sync; der Plan wird SERVERSEITIG frisch aus dem AD
        gebildet (kein Client-Plan wird akzeptiert — die Oberflaeche liefert
        keine Daten, nur den Anstoss).
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_PERSONNEL_SYNC):
            return self._forbidden(CAP_PERSONNEL_SYNC)

        try:
            provider = self._adsync_provider()
        except LdapError as exc:
            return Response.json(502, {"error": "ldap_failed",
                                       "detail": str(exc)})
        con = self._rw_con()
        try:
            executor = SyncExecutor(
                con, CoordinatorWriter(con, AuditLog(con)), provider)
            plan = executor.preview()
            summary = executor.apply_automatic(
                plan, actor_id=actor_person_id)
        except LdapError as exc:
            return Response.json(502, {"error": "ldap_failed",
                                       "detail": str(exc)})
        except AdSyncPlanError as exc:
            return Response.json(502, {"error": "ad_plan_invalid",
                                       "detail": str(exc)})
        except AdSyncError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("AD-Abgleich-Vollzug fehlgeschlagen")
            return Response.json(500, {"error": "adsync_apply_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        return Response.json(200, {
            "ok": True,
            "created": summary["created"],
            "renamed": summary["renamed"],
            "run_seq": summary["run_seq"],
            "counts": plan.counts(),
        })

    def _adsync_decide(self, actor_person_id: int,
                       payload: Dict[str, Any]) -> Response:
        """
        POST /api/adsync/decide — Einzel-Entscheidung ueber einen Kandidaten:
          {system_username, action: 'deactivate'|'abort'|'reactivate',
           confirmation?, note?, display_name_ad?}
        Recht personnel.sync. Das Bestaetigungswort wird SERVERSEITIG geprueft
        (SyncExecutor — nie nur im Browser). Ein falsches Wort bei 'deactivate'/
        'reactivate' ist HIER kein automatischer Abbruch-Beleg (anders als der
        one-shot-CLI-Dialog): die Oberflaeche ist interaktiv, der Nutzer kann
        korrigieren; der protokollierte Abbruch ist die EIGENE, bewusste
        Aktion 'abort' (mc 2026-07-24: Abbruch wird protokolliert).
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_PERSONNEL_SYNC):
            return self._forbidden(CAP_PERSONNEL_SYNC)

        sam = str(payload.get("system_username", "") or "").strip()
        action = str(payload.get("action", "") or "").strip()
        if not sam:
            return Response.json(400, {"error": "bad_request",
                                       "detail": "system_username fehlt."})
        if action not in ("deactivate", "abort", "reactivate"):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "action muss deactivate|abort|reactivate sein."})

        confirmation = str(payload.get("confirmation", "") or "")
        note = str(payload.get("note", "") or "")
        display_name_ad = payload.get("display_name_ad")

        con = self._rw_con()
        try:
            executor = SyncExecutor(
                con, CoordinatorWriter(con, AuditLog(con)),
                self._NullProvider())
            if action == "deactivate":
                seq = executor.deactivate(
                    sam, confirmation=confirmation,
                    actor_id=actor_person_id)
            elif action == "abort":
                seq = executor.abort_deactivation(
                    sam, actor_id=actor_person_id, note=note)
            else:
                seq = executor.reactivate(
                    sam, confirmation=confirmation,
                    actor_id=actor_person_id,
                    display_name_ad=(str(display_name_ad)
                                     if display_name_ad else None))
        except (AdSyncError, PersonError) as exc:
            # Falsches Bestaetigungswort, unbekannte Kennung, bereits
            # (in)aktives Konto oder fehlende M020 — Klartext, KEINE
            # Datenaenderung (die Sicht zeigt weiter den Ist-Stand).
            return Response.json(400, {"error": "confirmation_rejected",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("AD-Abgleich-Entscheidung fehlgeschlagen")
            return Response.json(500, {"error": "adsync_decide_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        return Response.json(200, {"ok": True, "action": action,
                                   "system_username": sam,
                                   "audit_seq": seq})

    # -------------------------------------------- Personalverwaltung (Build 503)
    def _personnel(self, actor_person_id: int) -> Response:
        """
        GET /api/personnel — Personalliste (Recht personnel.view): Personen
        inkl. Aktiv-Status/Flags + aktive Rollenzuweisungen + Rollenkatalog.
        can_edit/can_sync steuern NUR die Anzeige der Bedienelemente; jede
        Schreibroute prueft ihr Recht selbst (kein Vertrauen in den Client).
        REIN LESEND, KEIN AD-Zugriff (der AD-Abschnitt der Seite laedt
        /api/adsync separat und nur auf Nutzerhandlung).
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_PERSONNEL_VIEW):
            return self._forbidden(CAP_PERSONNEL_VIEW)

        con = self._ro_con()
        try:
            data = PersonOverviewRepo(con).overview()
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Personalliste nicht lesbar")
            return Response.json(500, {"error": "personnel_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        return Response.json(200, {
            **data,
            "actor_person_id": actor_person_id,
            "can_edit": policy.can(CAP_PERSONNEL_EDIT),
            "can_sync": policy.can(CAP_PERSONNEL_SYNC),
        })

    def _personnel_self_guard(self, actor_person_id: int,
                              target_person_id: int) -> Optional[Response]:
        """
        SELBSTSCHUTZ (Bauplan Build503 §3): die eigene Person ist ueber die
        Oberflaeche unantastbar — eigene Flags/Rollen zu aendern waere ein
        Ein-Klick-Lockout (z. B. eigenes supervisor-Flag/Rolle entziehen).
        Der auditierte CLI-Weg (person_admin/rbac_admin) bleibt dafuer offen.
        """
        if int(target_person_id) == int(actor_person_id):
            return Response.json(400, {
                "error": "self_guard",
                "detail": "Die eigene Person kann ueber die Oberflaeche "
                          "nicht veraendert werden (Lockout-Schutz). "
                          "Bitte den CLI-Weg nutzen (person_admin/"
                          "rbac_admin)."})
        return None

    def _personnel_flags(self, actor_person_id: int,
                         payload: Dict[str, Any]) -> Response:
        """
        POST /api/personnel/flags — {person_id, is_investigator?,
        is_supervisor?, is_support?} (Recht personnel.edit). Auditiert ueber
        PersonRepo.update (INVESTIGATOR_UPDATED, Diff alt->neu).
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_PERSONNEL_EDIT):
            return self._forbidden(CAP_PERSONNEL_EDIT)

        try:
            target_id = int(payload.get("person_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "person_id fehlt/ungueltig."})
        guard = self._personnel_self_guard(actor_person_id, target_id)
        if guard is not None:
            return guard

        # Nur explizit mitgeschickte Flags werden geaendert (None = unberuehrt).
        def _flag(name: str) -> Optional[bool]:
            return (bool(payload[name]) if name in payload
                    and payload[name] is not None else None)

        con = self._rw_con()
        try:
            repo = PersonRepo(con, CoordinatorWriter(con, AuditLog(con)))
            seq = repo.update(
                id=target_id,
                is_investigator=_flag("is_investigator"),
                is_supervisor=_flag("is_supervisor"),
                is_support=_flag("is_support"),
                actor_id=actor_person_id,
                meta={"quelle": "personnel_ui"},
            )
        except PersonError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Flag-Aenderung fehlgeschlagen")
            return Response.json(500, {"error": "personnel_flags_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "person_id": target_id,
                                   "audit_seq": seq})

    def _personnel_role_assign(self, actor_person_id: int,
                               payload: Dict[str, Any]) -> Response:
        """
        POST /api/personnel/role/assign — {person_id, role_code} (Recht
        personnel.edit). Auditiert ueber RbacRepo.assign_role (ROLE_ASSIGNED;
        die person_role-Zeile traegt audit_seq des Belegs).
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_PERSONNEL_EDIT):
            return self._forbidden(CAP_PERSONNEL_EDIT)

        try:
            target_id = int(payload.get("person_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "person_id fehlt/ungueltig."})
        role_code = str(payload.get("role_code", "") or "").strip()
        if not role_code:
            return Response.json(400, {"error": "bad_request",
                                       "detail": "role_code fehlt."})
        # Selbst-Zuweisung ist ungefaehrlich (erweitert nur), aber der
        # Symmetrie und Klarheit halber gilt der Selbstschutz fuer ALLE
        # Personnel-Schreibwege gleichermassen (eine Regel, keine Ausnahmen).
        guard = self._personnel_self_guard(actor_person_id, target_id)
        if guard is not None:
            return guard

        con = self._rw_con()
        try:
            repo = RbacRepo(con, CoordinatorWriter(con, AuditLog(con)))
            seq = repo.assign_role(target_id, role_code,
                                   actor_id=actor_person_id,
                                   meta={"quelle": "personnel_ui"})
        except RbacError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Rollenzuweisung fehlgeschlagen")
            return Response.json(500, {"error": "personnel_assign_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "person_id": target_id,
                                   "role_code": role_code, "audit_seq": seq})

    def _personnel_role_revoke(self, actor_person_id: int,
                               payload: Dict[str, Any]) -> Response:
        """
        POST /api/personnel/role/revoke — {person_role_id} (Recht
        personnel.edit). Soft-Revoke ueber RbacRepo.revoke_role (ROLE_REVOKED;
        die Zeile bleibt als Beleg erhalten). Selbstschutz: die eigene
        Zuweisung ist nicht widerrufbar (Lockout).
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_PERSONNEL_EDIT):
            return self._forbidden(CAP_PERSONNEL_EDIT)

        try:
            person_role_id = int(payload.get("person_role_id"))
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "person_role_id fehlt/ungueltig."})

        con = self._rw_con()
        try:
            row = con.execute(
                "SELECT person_id FROM person_role WHERE id=?",
                (person_role_id,)).fetchone()
            if row is None:
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "Unbekannte person_role_id=%s."
                              % person_role_id})
            guard = self._personnel_self_guard(actor_person_id,
                                               int(row["person_id"]))
            if guard is not None:
                return guard
            repo = RbacRepo(con, CoordinatorWriter(con, AuditLog(con)))
            seq = repo.revoke_role(person_role_id,
                                   actor_id=actor_person_id,
                                   meta={"quelle": "personnel_ui"})
        except RbacError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Rollen-Widerruf fehlgeschlagen")
            return Response.json(500, {"error": "personnel_revoke_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True,
                                   "person_role_id": person_role_id,
                                   "audit_seq": seq})

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
        GET /api/crossfindings — Meta-Uebersicht der Querfunde ("Fund ueber B
        im Fall A") aus pending_cross_annotations. Recht crossref.view.
        Duplziert NICHT die automatische Erfassung/den Transport — nur Anzeige.

        ZWEI UNABHAENGIGE FILTER (bewusst getrennt, sie meinen Verschiedenes):
          ?only_open=1            TRANSPORTstand: noch nicht integriert.
          ?only_unacknowledged=1  RUECKKANALstand (Build 507): noch nicht
                                  quittiert/bewertet.

        RUECKWAERTSVERTRAEGLICH (Build 507): 'findings' und 'counts' behalten
        exakt ihre bisherige Form und Bedeutung; der Rueckkanal kommt ADDITIV
        als Felder 'feedback_*'/'allowed_next' je Zeile und als eigener Block
        'feedback_counts' hinzu. Das Frontend aus Build 478 bleibt damit
        unveraendert gueltig.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_VIEW):
            return self._forbidden(CAP_CROSSREF_VIEW)

        raw = self._q1(query, "only_open")
        only_open = str(raw or "").lower() in ("1", "true", "yes", "ja")
        raw_unack = self._q1(query, "only_unacknowledged")
        only_unack = str(raw_unack or "").lower() in ("1", "true", "yes", "ja")
        con = self._ro_con()
        try:
            repo = CrossfindingsRepo(con)
            channel = CrossfindingChannelRepo(con)
            return Response.json(200, {
                # Transport-Sicht (Build 474) — Form unveraendert.
                "findings": channel.list_with_status(
                    only_open=only_open, only_unacknowledged=only_unack),
                "counts": repo.counts(),
                # Rueckkanal-Sicht (Build 507) — additiv.
                "feedback_counts": channel.counts(),
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

    def _crossfindings_decide(self, actor_person_id: int,
                              payload: Dict[str, Any]) -> Response:
        """
        POST /api/crossfindings/decide — {finding_id, status_code, reason?}.
        Fuehrt einen Querfund im RUECKKANAL in den Zielzustand (zugestellt /
        quittiert / verwertet / nicht_relevant), auditiert. Recht crossref.edit.

        Fehlerbilder, bewusst unterschieden:
          400 unzulaessiger Uebergang / fehlender Pflichttext / unbekannter
              Zielzustand  -> FACHLICH, mit sprechendem Text aus der
              Zustandsmaschine (die Ermittlerin soll den Grund lesen koennen).
          404 unbekannter Querfund.
          503 fehlendes Substrat (Linie Build 474: Betriebsfehler != Leerbefund).
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_EDIT):
            return self._forbidden(CAP_CROSSREF_EDIT)

        try:
            finding_id = int(payload.get("finding_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "finding_id fehlt/ungueltig."})
        target = str(payload.get("status_code", "") or "")

        con = self._rw_con()
        try:
            repo = CrossfindingChannelRepo(
                con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.decide(
                finding_id=finding_id, target_status=target,
                reason=str(payload.get("reason", "") or ""),
                actor_id=actor_person_id)
        except CrossfindingChannelError as exc:
            # Zustandsmaschine: unzulaessiger Uebergang / Pflichttext fehlt.
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except CrossrefError as exc:
            text = str(exc)
            if "Unbekannter Querfund" in text:
                return Response.json(404, {"error": "unknown_finding",
                                           "finding_id": finding_id,
                                           "detail": text})
            if "pending_cross_annotations fehlt" in text:
                return Response.json(503, {"error": "crossfindings_unavailable",
                                           "detail": text})
            return Response.json(400, {"error": "bad_request",
                                       "detail": text})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Querfund-Entscheidung fehlgeschlagen")
            return Response.json(500, {"error": "crossfindings_decide_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    # ---------------------------------------------------------------- Build 504
    # Globaler Alias-Katalog (AP-2A, Idee 8). Recht crossref.view/edit —
    # bewusst wiederverwendet (gleiche F5-Familie wie Identitaetskatalog und
    # Querfunde; Entscheidungslinie Build 474 §3). Global, NICHT scope-behaftet:
    # ein Alias ist genau dann wertvoll, wenn er FALLUEBERGREIFEND sichtbar ist.

    def _alias(self, actor_person_id: int, query) -> Response:
        """
        GET /api/alias — Alias-Katalog. Drei Betriebsarten:
          ?q=<Begriff>       RUECKWAERTSSUCHE "welche Konten fuehren den Namen?"
          ?subject_id=N      Aliasse EINES Kontos
          (ohne Parameter)   ganzer Katalog
        ?include_retracted=1 nimmt widerrufene Eintraege mit auf (sie sind kein
        Leerbefund, sondern ein anderer Erkenntnisstand — Grundregel 1).
        Recht crossref.view.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_VIEW):
            return self._forbidden(CAP_CROSSREF_VIEW)

        raw_sid = self._q1(query, "subject_id")
        term = self._q1(query, "q")
        incl_raw = self._q1(query, "include_retracted")
        include_retracted = str(incl_raw or "").lower() in (
            "1", "true", "yes", "ja")

        con = self._ro_con()
        try:
            repo = SubjectAliasRepo(con)
            if term:
                entries = repo.search(
                    str(term), include_retracted=include_retracted)
                mode = "search"
            elif raw_sid:
                try:
                    sid = int(raw_sid)
                except (TypeError, ValueError):
                    return Response.json(
                        400, {"error": "bad_request",
                              "detail": "subject_id ungueltig."})
                entries = repo.list(
                    subject_id=sid, include_retracted=include_retracted)
                mode = "subject"
            else:
                entries = repo.list(include_retracted=include_retracted)
                mode = "all"
            return Response.json(200, {
                "entries": entries,
                "counts": repo.counts(),
                "mode": mode,
                # Die Arten-Liste kommt vom SERVER, damit die Oberflaeche keine
                # Auswahl anbieten kann, die die DDL-CHECK spaeter ablehnt.
                "kinds": [{"code": c, "label": l}
                          for c, l in ALIAS_KINDS.items()],
            })
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Alias-Katalog nicht lesbar")
            return Response.json(500, {"error": "alias_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

    def _names(self, actor_person_id: int, query) -> Response:
        """
        GET /api/names — NAMENSAUFLOESUNG (Oberflaechen-Zweig, Build 600).

        Zwei Betriebsarten, sich gegenseitig ausschliessend:
          ?subject_id=N   RUECKWAERTS: Kennung -> Benutzername
          ?q=<Begriff>    VORWAERTS:   Name -> Kennung(en), KASKADE
                          Fallakte, dann globale Namensliste (mc 2026-07-26)

        ANLASS (mc 2026-07-26): "Unsere Ermittler sind mit den Namen der
        Forennutzer vertraut, aber nicht mit den user_id oder subject_id. [...]
        In jedem Fall ist es den Anwendern nicht zuzumuten, die subject_id zu
        kennen."

        RECHT: crossref.view — dasselbe wie /api/alias, denn dieser Endpunkt
        speist genau dessen Sicht. KEINE neue Faehigkeit: der Katalog in
        management/rbac/catalog.py bleibt unangetastet, damit dieser Build im
        Parallelbetrieb keinen Ankerwert verschiebt (Welle 3 §6).

        REIN LESEND. coordinator.db und default.db werden mit mode=ro
        geoeffnet; der Migrationsvorbehalt ab 01.07.2026 ist nicht beruehrt.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_VIEW):
            return self._forbidden(CAP_CROSSREF_VIEW)

        raw_sid = self._q1(query, "subject_id")
        term = self._q1(query, "q")

        if raw_sid is None and not term:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "Entweder 'subject_id' oder 'q' angeben."})

        con = self._ro_con()
        try:
            resolver = NameResolver(con, self._default_db)
            if raw_sid is not None:
                try:
                    sid = int(raw_sid)
                except (TypeError, ValueError):
                    return Response.json(400, {
                        "error": "bad_request",
                        "detail": "subject_id ungueltig."})
                payload = resolver.aufloesen(sid)
                return Response.json(200, dict(payload.to_dict(),
                                               modus="aufloesung"))
            payload = resolver.suchen(str(term))
            return Response.json(200, dict(payload.to_dict(), modus="suche"))
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Namensaufloesung fehlgeschlagen")
            return Response.json(500, {"error": "names_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

    def _alias_write(self, actor_person_id: int, what: str,
                     run) -> Response:
        """
        Gemeinsamer Rahmen der vier schreibenden Alias-Routen: Rechtepruefung,
        Verbindung, einheitliche Fehlerbilder. 'run(repo)' fuehrt die eigentliche
        Repo-Methode aus. So bleibt die Fehlerbehandlung an EINER Stelle —
        vier Kopien waeren vier Gelegenheiten, sie auseinanderlaufen zu lassen.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_EDIT):
            return self._forbidden(CAP_CROSSREF_EDIT)
        con = self._rw_con()
        try:
            repo = SubjectAliasRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = run(repo)
        except CrossrefError as exc:
            # Fachlicher Fehler (Duplikat, No-Op, fehlender Grund, unbekannter
            # Eintrag): 400 mit sprechendem Text — die Ermittlerin soll den
            # konkreten Konflikt sehen, nicht ein generisches "geht nicht".
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Alias-Schreibzugriff (%s) fehlgeschlagen", what)
            return Response.json(500, {"error": "alias_%s_failed" % what,
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    def _alias_add(self, actor_person_id: int,
                   payload: Dict[str, Any]) -> Response:
        """POST /api/alias/add — {subject_id, alias, kind_code, basis?, note?}."""
        try:
            subject_id = int(payload.get("subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "subject_id fehlt/ungueltig."})
        note_raw = payload.get("note")
        return self._alias_write(
            actor_person_id, "add",
            lambda repo: repo.add(
                subject_id=subject_id,
                alias=str(payload.get("alias", "") or ""),
                kind_code=str(payload.get("kind_code", "") or ""),
                basis=str(payload.get("basis", "") or ""),
                note=(None if note_raw is None else str(note_raw)),
                actor_id=actor_person_id))

    def _alias_update(self, actor_person_id: int,
                      payload: Dict[str, Any]) -> Response:
        """
        POST /api/alias/update — {alias_id, kind_code?, basis?, note?}.
        Der ALIASTEXT ist bewusst nicht aenderbar (Repo-Kopfkommentar): ein
        anderer Text ist eine andere Erkenntnis und entsteht durch
        retract() + add().
        """
        try:
            alias_id = int(payload.get("alias_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "alias_id fehlt/ungueltig."})
        kind = payload.get("kind_code")
        basis = payload.get("basis")
        note = payload.get("note")
        return self._alias_write(
            actor_person_id, "update",
            lambda repo: repo.update(
                alias_id=alias_id,
                kind_code=(None if kind is None else str(kind)),
                basis=(None if basis is None else str(basis)),
                note=(None if note is None else str(note)),
                actor_id=actor_person_id))

    def _alias_retract(self, actor_person_id: int,
                       payload: Dict[str, Any]) -> Response:
        """POST /api/alias/retract — {alias_id, reason}. Grund ist Pflicht."""
        try:
            alias_id = int(payload.get("alias_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "alias_id fehlt/ungueltig."})
        return self._alias_write(
            actor_person_id, "retract",
            lambda repo: repo.retract(
                alias_id=alias_id,
                reason=str(payload.get("reason", "") or ""),
                actor_id=actor_person_id))

    def _alias_reinstate(self, actor_person_id: int,
                         payload: Dict[str, Any]) -> Response:
        """POST /api/alias/reinstate — {alias_id}. Widerruf zuruecknehmen."""
        try:
            alias_id = int(payload.get("alias_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "alias_id fehlt/ungueltig."})
        return self._alias_write(
            actor_person_id, "reinstate",
            lambda repo: repo.reinstate(
                alias_id=alias_id, actor_id=actor_person_id))

    # ---------------------------------------------------------------- Build 511
    # Akten-Export je Cockpit-Sicht (AP-2B/B1, Idee 5).

    def _view_export(self, actor_person_id: int, query) -> Response:
        """
        GET /api/view/export?view=<id> — druckbarer, gerichtsfester Akten-Export
        der angegebenen Sicht. Weitere Query-Parameter werden UNVERAENDERT an
        den Sicht-Endpunkt durchgereicht (z. B. capacity?start=, onboarding?
        person_id=, alias?q=), damit der Export genau den Ausschnitt abbildet,
        den die Ermittlerin vor sich hat.

        KEINE EIGENE RECHTEPRUEFUNG — und das ist Absicht: der Export ruft den
        Sicht-Endpunkt ueber den BESTEHENDEN dispatch() auf und erbt dadurch
        dessen Faehigkeitspruefung, Scope und Fehlerbilder. Ein zweiter,
        selbstgebauter Rechtepfad koennte vom ersten abdriften und dabei ein
        Recht uebersehen; dieser kann es konstruktiv nicht. Wer die Sicht nicht
        sehen darf, bekommt vom inneren dispatch() ein 403 — und genau das
        wird unveraendert weitergereicht.

        Statuscodes: unbekannte/nicht exportierbare Sicht -> 404 (mit der Liste
        der bekannten IDs); jeder Nicht-200-Status des Sicht-Endpunkts wird
        1:1 durchgereicht (403 bleibt 403, 503 bleibt 503, 400 bleibt 400).
        """
        raw_view = self._q1(query, "view")
        spec = spec_for(str(raw_view or ""))
        if spec is None:
            return Response.json(404, {
                "error": "unknown_view",
                "view": raw_view,
                "detail": "Fuer diese Sicht ist kein Akten-Export hinterlegt.",
                "known": list(known_view_ids()),
            })

        # Query ohne 'view' an den Sicht-Endpunkt weiterreichen.
        inner = {}
        if isinstance(query, dict):
            inner = {k: v for k, v in query.items() if k != "view"}

        try:
            inner_resp = self.dispatch(actor_person_id, spec.api_path, inner)
        except Exception as exc:                       # noqa: BLE001
            # HAERTUNG (bei der Umsetzung von B1 aufgefallen, Test VE07): ein
            # Sicht-Handler kann eine Ausnahme durchreichen, wenn eine
            # NACHGELAGERTE Quelle fehlt (z. B. templates.db nicht vorhanden ->
            # sqlite3.OperationalError aus _templates_ro_con). Der Export darf
            # daran nicht ZERBRECHEN — sonst waere er zerbrechlicher als die
            # Sicht, die er abbildet. Er meldet den Fehler stattdessen als 500
            # und NENNT den inneren Endpunkt, damit die Ursache auffindbar ist.
            # Das Verhalten der Sicht selbst bleibt unveraendert (kein Eingriff
            # in fremde Handler).
            logger.exception("Sicht-Endpunkt %s hat eine Ausnahme "
                             "durchgereicht", spec.api_path)
            return Response.json(500, {
                "error": "view_export_failed",
                "view": spec.view_id,
                "detail": "Der Sicht-Endpunkt %s ist nicht abrufbar: %s"
                          % (spec.api_path, exc)})

        if inner_resp.status != 200:
            # EHRLICH DURCHREICHEN: der Export beschoenigt nichts. Ein 403 des
            # Sicht-Endpunkts ist ein 403 des Exports; ein 503 (fehlendes
            # Substrat) bleibt ein 503 — kein leeres Dokument, das
            # Vollstaendigkeit vortaeuschte (Grundregel 1).
            return inner_resp

        try:
            data = json.loads(inner_resp.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            logger.exception("Sicht-Antwort nicht lesbar (%s)", spec.api_path)
            return Response.json(500, {"error": "view_export_failed",
                                       "detail": "Antwort von %s nicht "
                                                 "auswertbar: %s"
                                                 % (spec.api_path, exc)})

        con = self._ro_con()
        try:
            person = self._person(con, actor_person_id)
            actor = person.get("system_username") if person else None
            ctx = build_export_context(
                con=con, db_path=self._db_path, actor=actor,
                aktenzeichen=spec.label)
            out = ViewExportRenderer(spec).render(
                data, ExportEnvelope(ctx),
                query_summary=query_summary(inner))
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Akten-Export fehlgeschlagen (%s)", spec.view_id)
            return Response.json(500, {"error": "view_export_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.html(200, out)

    # ---------------------------------------------------------------- Build 509
    # Identitaets-Merge/Split (AP-2A, Idee 11). Recht crossref.view/edit.
    # Global, NICHT scope-behaftet: eine Identitaets-Gruppe ist per Definition
    # falluebergreifend.

    def _merge(self, actor_person_id: int, query) -> Response:
        """
        GET /api/merge — Identitaets-Zusammenfuehrungen.
          ?subject_id=N        -> die GANZE Gruppe dieses Kontos (unabhaengig
                                  davon, ob N das Primaerkonto ist)
          ?include_split=1     -> getrennte Zeilen mitliefern (sie sind ein
                                  anderer Erkenntnisstand, kein Leerbefund)
          (ohne Parameter)     -> alle aktiven Zusammenfuehrungen
        Recht crossref.view.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_VIEW):
            return self._forbidden(CAP_CROSSREF_VIEW)

        raw_sid = self._q1(query, "subject_id")
        incl_raw = self._q1(query, "include_split")
        include_split = str(incl_raw or "").lower() in ("1", "true", "yes", "ja")

        con = self._ro_con()
        try:
            repo = SubjectMergeRepo(con)
            body: Dict[str, Any] = {
                "counts": repo.counts(),
                # Die Konfidenz-Stufen kommen vom SERVER — dieselbe Achse wie
                # im Identitaetskatalog (M018), damit die Oberflaeche keine
                # Stufe anbieten kann, die die DDL-CHECK ablehnt.
                "confidence": [
                    {"code": "verdacht", "label": "Verdacht", "ordinal": 10},
                    {"code": "wahrscheinlich", "label": "wahrscheinlich",
                     "ordinal": 20},
                    {"code": "gesichert", "label": "gesichert", "ordinal": 30},
                ],
            }
            if raw_sid:
                try:
                    sid = int(raw_sid)
                except (TypeError, ValueError):
                    return Response.json(
                        400, {"error": "bad_request",
                              "detail": "subject_id ungueltig."})
                body["group"] = repo.group_of(sid)
                body["entries"] = body["group"]["merges"]
                body["mode"] = "group"
            else:
                body["entries"] = repo.list(include_split=include_split)
                body["mode"] = "all"
            return Response.json(200, body)
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Identitaets-Gruppen nicht lesbar")
            return Response.json(500, {"error": "merge_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

    def _merge_write(self, actor_person_id: int, what: str, run) -> Response:
        """
        Gemeinsamer Rahmen der drei schreibenden Merge-Routen. Fachliche
        Konflikte (Kette, Doppelzuordnung, Selbstverschmelzung, fehlender
        Grund) kommen als 400 MIT dem sprechenden Text des Repos zurueck — die
        Ermittlerin braucht den konkreten Konflikt samt der beteiligten
        subject_ids, nicht dessen Zusammenfassung.
        """
        policy = self.resolve_policy(actor_person_id)
        if not policy.can(CAP_CROSSREF_EDIT):
            return self._forbidden(CAP_CROSSREF_EDIT)
        con = self._rw_con()
        try:
            repo = SubjectMergeRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = run(repo)
        except CrossrefError as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except sqlite3.IntegrityError as exc:
            # Letzte Verteidigungslinie: die DDL-CHECK/der UNIQUE-Index. Wenn
            # sie greift, ist eine Repo-Pruefung durchgerutscht — das ist ein
            # fachlicher Konflikt, kein Serverfehler, und wird auch so gemeldet.
            logger.warning("Merge-Integritaetsregel gegriffen: %s", exc)
            return Response.json(400, {"error": "bad_request",
                                       "detail": "Integritaetsregel verletzt: "
                                                 + str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Merge-Schreibzugriff (%s) fehlgeschlagen", what)
            return Response.json(500, {"error": "merge_%s_failed" % what,
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, **res})

    def _merge_set(self, actor_person_id: int,
                   payload: Dict[str, Any]) -> Response:
        """
        POST /api/merge/set — anlegen ODER revidieren.
          mit 'merge_id'  -> revise (Konfidenz/Basis reifen lassen)
          sonst           -> merge {primary_subject_id, merged_subject_id,
                                    basis, confidence_code}
        Die beteiligten Konten sind bewusst NICHT revidierbar: eine andere
        Paarung ist eine andere Hypothese und entsteht durch split() + merge().
        """
        merge_id = payload.get("merge_id")
        if merge_id is not None:
            try:
                mid = int(merge_id)
            except (TypeError, ValueError):
                return Response.json(400, {"error": "bad_request",
                                           "detail": "merge_id ungueltig."})
            basis = payload.get("basis")
            conf = payload.get("confidence_code")
            return self._merge_write(
                actor_person_id, "revise",
                lambda repo: repo.revise(
                    merge_id=mid,
                    basis=(None if basis is None else str(basis)),
                    confidence_code=(None if conf is None else str(conf)),
                    actor_id=actor_person_id))

        try:
            primary = int(payload.get("primary_subject_id"))
            merged = int(payload.get("merged_subject_id"))
        except (TypeError, ValueError):
            return Response.json(
                400, {"error": "bad_request",
                      "detail": "primary_subject_id/merged_subject_id "
                                "fehlen oder sind ungueltig."})
        return self._merge_write(
            actor_person_id, "set",
            lambda repo: repo.merge(
                primary_subject_id=primary, merged_subject_id=merged,
                basis=str(payload.get("basis", "") or ""),
                confidence_code=str(payload.get("confidence_code", "") or ""),
                actor_id=actor_person_id))

    def _merge_split(self, actor_person_id: int,
                     payload: Dict[str, Any]) -> Response:
        """POST /api/merge/split — {merge_id, reason}. Grund ist Pflicht."""
        try:
            mid = int(payload.get("merge_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "merge_id fehlt/ungueltig."})
        return self._merge_write(
            actor_person_id, "split",
            lambda repo: repo.split(
                merge_id=mid, reason=str(payload.get("reason", "") or ""),
                actor_id=actor_person_id))

    def _merge_remerge(self, actor_person_id: int,
                       payload: Dict[str, Any]) -> Response:
        """POST /api/merge/remerge — {merge_id}. Trennung zuruecknehmen."""
        try:
            mid = int(payload.get("merge_id"))
        except (TypeError, ValueError):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "merge_id fehlt/ungueltig."})
        return self._merge_write(
            actor_person_id, "remerge",
            lambda repo: repo.remerge(merge_id=mid, actor_id=actor_person_id))

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

        # Build 517 (AP-2G / Idee 23): auditierte Quittierung einer Eskalation
        # und deren Widerruf. Recht escalation.ack (NICHT escalation.view).
        if path == "/api/escalations/ack":
            return self._escalation_ack(person_id, payload)
        if path == "/api/escalations/ack/revoke":
            return self._escalation_ack_revoke(person_id, payload)
        if path == "/api/case/assign":
            return self._case_assign(person_id, payload)
        # Build 534: Sammelzuweisung (viele Faelle in EINER Transaktion, ein
        # Beleg JE FALL). Begruendung: management/cases/cases_batch_repo.py.
        if path == "/api/case/assign_batch":
            return self._case_assign_batch(person_id, payload)
        if path == "/api/case/priority":
            return self._case_priority(person_id, payload)
        if path == "/api/case/status":
            return self._case_status(person_id, payload)
        # Build 500: Fallstart aus dem Portal. Startet den Forensik-Server
        # (main.py) fuer einen dem Aufrufer zugewiesenen Fall. KEIN DB-Schreib-
        # zugriff (migrationsneutral) — nur Eigentuemer-Lesepruefung + Spawn.
        if path == "/api/case/launch":
            return self._case_launch(person_id, payload)
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
        # --- Build 541 (AP-3C): QS-Stichprobe, auditierte Schreibwege ----
        #     ZWEI Routen statt einer Sammelroute: Ziehen und Pruefen sind
        #     fachlich verschiedene Handlungen verschiedener Personen zu
        #     verschiedenen Zeiten (Muster der vier Alias-Routen, Build 504).
        if path == "/api/qs/draw":
            return self._qs_draw(person_id, payload)
        if path == "/api/qs/review":
            return self._qs_review(person_id, payload)
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
        # Build 502: AD-Abgleich — automatischer Teil (Neuaufnahmen +
        # Namensaenderungen) bzw. Einzel-Entscheidung mit Bestaetigungswort.
        if path == "/api/adsync/apply":
            return self._adsync_apply(person_id)
        if path == "/api/adsync/decide":
            return self._adsync_decide(person_id, payload)
        # Build 503: Personalverwaltung — auditierte Schreibwege.
        if path == "/api/personnel/flags":
            return self._personnel_flags(person_id, payload)
        if path == "/api/personnel/role/assign":
            return self._personnel_role_assign(person_id, payload)
        if path == "/api/personnel/role/revoke":
            return self._personnel_role_revoke(person_id, payload)
        # Build 470 (AP-2A): Katalog identifizierter Personen — auditiert.
        if path == "/api/crossref/set":
            return self._crossref_set(person_id, payload)
        # Build 507 (AP-2A, Idee 7): Querfund-Rueckkanal — auditiert.
        if path == "/api/crossfindings/decide":
            return self._crossfindings_decide(person_id, payload)
        # Build 504 (AP-2A, Idee 8): globaler Alias-Katalog — auditiert.
        # Vier getrennte Routen statt einer Sammelroute: Anlegen, Aendern,
        # Widerrufen und Zuruecknehmen sind fachlich verschieden schwer; eine
        # Sammelroute haette die Absicht des Aufrufers verwischt (und im
        # Audit-Explorer waere nur noch ein einziger Routenname sichtbar).
        if path == "/api/alias/add":
            return self._alias_add(person_id, payload)
        if path == "/api/alias/update":
            return self._alias_update(person_id, payload)
        if path == "/api/alias/retract":
            return self._alias_retract(person_id, payload)
        if path == "/api/alias/reinstate":
            return self._alias_reinstate(person_id, payload)
        # Build 509 (AP-2A, Idee 11): Identitaets-Merge/Split — auditiert.
        if path == "/api/merge/set":
            return self._merge_set(person_id, payload)
        if path == "/api/merge/split":
            return self._merge_split(person_id, payload)
        if path == "/api/merge/remerge":
            return self._merge_remerge(person_id, payload)
        # Build 412 (SF-3): Lektorat/Chef-Kommentare (Addendum-Dateien).
        if path == "/api/report/comment":
            return self._report_comment_create(person_id, payload)
        if path == "/api/report/comment/resolve":
            return self._report_comment_resolve(person_id, payload)
        # Build 489/490 (W2): Platzhalter anlegen/aendern (templates.db.
        # placeholders, Typen a/m/o + Validierung). Die Legacy-query-Pfade
        # sind mit dem Maskenumbau (Build 490) entfallen.
        if path == "/api/templates/placeholder":
            return self._templates_placeholder_upsert(person_id, payload)
        # Build 423/489: schreibfreie Vorschau (Validierung + fdb-Dry-Run),
        # damit die Redakteur:in testen kann, BEVOR sie speichert.
        if path == "/api/templates/placeholder/dryrun":
            return self._templates_placeholder_dryrun(person_id, payload)
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
        # --- Build 562 (AP-3E / Idee 38, Instanz B): Volltextsuche ---------
        # DIE SUCHE IST EIN POST UND KEIN GET, obwohl sie nichts Fachliches
        # schreibt. Begruendung: jede Abfrage IST ein Beleg (Klaerung §6
        # Nr. 1) — auch der Leerbefund, sonst liesse sich spurenfrei
        # sondieren. Ein GET, der belegt, erzeugte bei jedem Neuladen einen
        # weiteren Eintrag; ausserdem traegt der POST-Rumpf die
        # PFLICHT-Zweckangabe (E-3), die in einer URL nichts zu suchen hat.
        if path == "/api/fulltext/lage":
            return self._fulltext_lage(person_id, payload)
        if path == "/api/fulltext/inhalt":
            return self._fulltext_inhalt(person_id, payload)
        if path == "/api/fulltext/release/grant":
            return self._fulltext_release_grant(person_id, payload)
        # --- Build 545 (AP-3G): Ansichtseinstellung speichern/zuruecksetzen
        # POST und nicht GET, weil geschrieben wird; der Token-Check liegt
        # bereits im Handler VOR dieser Stelle.
        if path == "/api/viewprefs":
            return self._viewprefs_speichern(person_id, payload)
        if path == "/api/viewprefs/reset":
            return self._viewprefs_zuruecksetzen(person_id, payload)

        if path == "/api/fulltext/release/revoke":
            return self._fulltext_release_revoke(person_id, payload)

        # --- Build 558: Kapazitaetspflege, auditierte Schreibwege -------
        # SECHS Routen statt einer Sammelroute: es sind sechs fachlich
        # verschiedene Handlungen mit verschiedenen Belegarten
        # (WORKTIME_SET, AVAILABILITY_SET/_REMOVED, HOLIDAY_ADDED/
        # _REMOVED, AVAILABILITY_REASON_ADDED). Eine Sammelroute muesste
        # die Belegart aus der Nutzlast RATEN - und ein falsch geratener
        # Beleg ist schlimmer als gar keiner. Muster: die vier
        # Alias-Routen (Build 504) und /api/qs/draw|review (Build 541).
        if path == "/api/capacity/worktime":
            return self._capacity_worktime_set(person_id, payload)
        if path == "/api/capacity/worktime/remove":
            return self._capacity_worktime_remove(person_id, payload)
        if path == "/api/capacity/worktime/replace":
            return self._capacity_worktime_replace(person_id, payload)
        if path == "/api/capacity/availability":
            return self._capacity_availability_set(person_id, payload)
        if path == "/api/capacity/availability/remove":
            return self._capacity_availability_remove(person_id, payload)
        if path == "/api/capacity/holiday":
            return self._capacity_holiday_add(person_id, payload)
        if path == "/api/capacity/holiday/remove":
            return self._capacity_holiday_remove(person_id, payload)
        if path == "/api/capacity/reason":
            return self._capacity_reason_add(person_id, payload)

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

    #: Build 534: Obergrenze eines Stapels der Sammelzuweisung.
    #  SIE IST KEINE FACHLICHE GRENZE, sondern ein Schutz gegen einen
    #  entgleisten oder boesartigen Rumpf: ein Stapel haelt waehrend seiner
    #  Transaktion die Schreibsperre auf coordinator.db, und eine Anfrage mit
    #  einer Million Eintraegen wuerde den Server fuer alle blockieren.
    #  Der Wert ist grosszuegig ueber dem groessten bekannten Bedarf gewaehlt
    #  (mc am 2026-07-25: gut 80 Faelle) und liegt ueber der Gesamtzahl der
    #  derzeit gefuehrten Faelle, damit 'alle auf einmal' moeglich bleibt.
    #  WIRD SIE UEBERSCHRITTEN, wird der Stapel ABGELEHNT und nicht etwa
    #  gekuerzt — eine stille Kuerzung waere genau die Art von Auslassung, die
    #  Grundregel 1 verbietet.
    _BATCH_MAX = 1000

    def _case_assign_batch(self, person_id: int,
                           payload: Dict[str, Any]) -> Response:
        """
        SAMMELZUWEISUNG (Build 534): weist viele Faelle in EINEM Vorgang zu
        und/oder setzt ihre Prioritaet.

        Rumpf:
            {"changes": [{"subject_id": 18, "person_id": 4, "priority": 2},
                         {"subject_id": 19, "person_id": null}, ...]}

        Je Eintrag sind 'person_id' und 'priority' einzeln optional; mindestens
        eines muss da sein. 'person_id': null bedeutet ausdruecklich ENTZIEHEN
        — deshalb wird zwischen 'Feld fehlt' und 'Feld ist null' unterschieden
        (derselbe Wachwert-Kniff wie in _case_assign).

        Antwort (200): je EINGEREICHTEM Fall eine Ergebniszeile, auch fuer die
        unveraenderten; dazu die Zahl der erzeugten Belege. Antwort (400) bei
        Beanstandungen: die Liste der Beanstandungen — und es wurde NICHTS
        geschrieben (erst pruefen, dann schreiben).
        """
        denied = self._require_assignment_scope(person_id)
        if denied is not None:
            return denied

        roh = payload.get("changes")
        if not isinstance(roh, list):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "'changes' muss eine Liste sein."})
        if not roh:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "'changes' ist leer — es gibt nichts zu schreiben."})
        if len(roh) > self._BATCH_MAX:
            return Response.json(400, {
                "error": "too_many",
                "detail": "Stapel mit %d Eintraegen ueberschreitet die Grenze "
                          "von %d. Es wurde NICHTS geschrieben."
                          % (len(roh), self._BATCH_MAX)})

        changes: List[BatchChange] = []
        maengel: List[str] = []
        for i, eintrag in enumerate(roh):
            if not isinstance(eintrag, dict):
                maengel.append("Eintrag %d ist kein Objekt." % i)
                continue
            try:
                subject_id = int(eintrag.get("subject_id"))
            except (TypeError, ValueError):
                maengel.append("Eintrag %d: subject_id fehlt/ungueltig." % i)
                continue

            assign = "person_id" in eintrag
            ziel: Optional[int] = None
            if assign and eintrag.get("person_id") is not None:
                try:
                    ziel = int(eintrag.get("person_id"))
                except (TypeError, ValueError):
                    maengel.append("Eintrag %d (Fall %d): person_id ungueltig."
                                   % (i, subject_id))
                    continue

            prio: Optional[int] = None
            if eintrag.get("priority") is not None:
                try:
                    prio = int(eintrag.get("priority"))
                except (TypeError, ValueError):
                    maengel.append("Eintrag %d (Fall %d): priority ungueltig."
                                   % (i, subject_id))
                    continue

            changes.append(BatchChange(subject_id=subject_id, assign=assign,
                                       person_id=ziel, priority=prio))

        if maengel:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "%d Beanstandung(en) im Rumpf — es wurde NICHTS "
                          "geschrieben." % len(maengel),
                "zeilen": maengel})

        con = self._rw_con()
        try:
            repo = CasesBatchRepo(con, CoordinatorWriter(con, AuditLog(con)),
                                  priority_min=_PRIORITY_MIN,
                                  priority_max=_PRIORITY_MAX)
            ergebnisse = repo.apply(changes, actor_id=person_id)
        except CasesBatchError as exc:
            # Fachliche Beanstandung VOR dem Schreiben — kein Serverfehler.
            return Response.json(400, {"error": "batch_rejected",
                                       "detail": exc.detail,
                                       "zeilen": list(exc.zeilen)})
        except Exception as exc:
            logger.exception("Sammelzuweisung fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        belege = sum(len(r.audit_seqs) for r in ergebnisse)
        geschrieben = sum(1 for r in ergebnisse if r.ergebnis == "geschrieben")
        return Response.json(200, {
            "ok": True,
            "eingereicht": len(ergebnisse),
            "geschrieben": geschrieben,
            "unveraendert": len(ergebnisse) - geschrieben,
            "belege": belege,
            "results": [r.to_dict() for r in ergebnisse],
        })

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

    def _case_launch(self, person_id: int,
                     payload: Dict[str, Any]) -> Response:
        """
        Startet den FORENSIK-Webserver (main.py) fuer einen dem Aufrufer
        zugewiesenen Fall (Build 500). Beide Server laufen in derselben VM.

        Sicherheits-/Fachregeln (mc 2026-07-22):
          - Tor ist dieselbe Capability wie die Sicht 'Meine Auftraege'
            (CAP_MYCASES). Wer die eigenen Faelle nicht sehen darf, darf auch
            keinen starten.
          - EIGENTUEMER-PRUEFUNG: Es duerfen NUR Faelle gestartet werden, die dem
            Aufrufer zugewiesen sind (cases.assigned_to == person_id). Fremde
            Faelle -> 403. Das ist die serverseitige Durchsetzung von 'nur eigene
            zugewiesene Faelle' (nicht nur ein UI-Filter).
          - KEIN DB-Schreibzugriff: reine Lesepruefung (mode=ro) + Prozess-Spawn.
            Damit ist der Endpoint migrationsneutral (kein Schema-/DB-Eingriff,
            kein neuer EventType) — bewusst gewaehlt fuer den Produktivbetrieb
            ab 01.07.2026. Der Start selbst wird (wie start.bat) NICHT in
            coordinator.db auditiert; ein spaeterer Audit-Beleg bliebe als
            eigene Entscheidung nachruestbar (siehe Uebergabe Build 500).
          - Fehlerpolitik (E2): NUR starten, START-ZEIT-Fehler melden. Fehlende
            fallspezifische DBs fuehren zum harten Abbruch IN main.py (im
            losgeloesten Prozess) und sind daher hier nicht sichtbar.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_MYCASES):
            return self._forbidden(CAP_MYCASES)

        # subject_id validieren (Existenz + Eigentuemer) — read-only.
        con = self._ro_con()
        try:
            subject_id, err = self._case_id(con, payload)
            if err is not None:
                return err
            row = con.execute(
                "SELECT assigned_to FROM cases WHERE subject_id=?",
                (subject_id,)).fetchone()
        finally:
            con.close()

        # Eigentuemer-Durchsetzung: nur der zugewiesene Ermittler darf starten.
        assigned_to = row["assigned_to"] if row is not None else None
        if assigned_to != person_id:
            logger.warning(
                "Fallstart abgewiesen: person_id=%s ist nicht Eigentuemer von "
                "subject_id=%s (assigned_to=%s).",
                person_id, subject_id, assigned_to)
            return Response.json(403, {
                "error": "not_owner",
                "subject_id": subject_id,
                "detail": "Fall ist nicht Ihnen zugewiesen."})

        # Start. START-ZEIT-Fehler werden als klare 500-Antwort gemeldet
        # (Grundregel 1: kein stiller Fehlschlag).
        try:
            info = self._case_launcher.launch(subject_id)
        except CaseLaunchError as exc:
            logger.exception("Fallstart fehlgeschlagen (subject_id=%s)",
                             subject_id)
            return Response.json(500, {
                "error": "launch_failed",
                "subject_id": subject_id,
                "detail": str(exc)})

        return Response.json(200, {
            "ok": True,
            "launched": True,
            "subject_id": subject_id,
            "pid": info.get("pid")})

    # =====================================================================
    # --- Build 562 (AP-3E / Idee 38, Instanz B): Volltextsuche ------------
    # =====================================================================
    # Hier steht AUSSCHLIESSLICH die Anbindung: Recht pruefen, Rumpf
    # auspacken, Fachfehler in HTTP uebersetzen. Die Fachlogik liegt
    # vollstaendig in der eigenen Zone (management/search/**), wie
    # Parallelbetrieb §4 es fuer diese Datei verlangt.

    def _search_index_pfad(self) -> str:
        """
        Pfad der search_index.db.

        Sie liegt NEBEN den Beweismitteln, nicht darin — ein Hilfsmittel, das
        jederzeit geloescht werden darf. Aus der Konfiguration lesbar
        (paths.search_index_db); ohne Eintrag der Standard neben
        coordinator.db, damit die Anlage auch ohne Konfigurationsaenderung
        laeuft. Der Rueckfall wird protokolliert (Grundregel 1).
        """
        try:
            from core.config_loader import ConfigLoader
            wert = ConfigLoader().get("paths.search_index_db")
            if wert:
                return str(wert)
        except Exception as exc:  # pragma: no cover — Konfig-Ausfall
            logger.warning("search_index_db nicht aus config.yaml lesbar "
                           "(%s) — Standard neben coordinator.db.", exc)
        return str(Path(self._db_path).parent / "search_index.db")

    def _fulltext_service(self, con):
        """
        Baut den Suchdienst. Wirft SearchIndexFehler, wenn FTS5/trigram
        fehlen — der Aufrufer uebersetzt das in eine 503 mit Klartext. KEIN
        Rueckfall auf LIKE: er faende nur einen Teil und schwiege darueber.
        """
        from db.search_index_db import SearchIndexDb
        from management.gateway.coordinator_writer import CoordinatorWriter
        from management.search.search_service import FulltextSearchService
        index = SearchIndexDb(self._search_index_pfad())
        writer = CoordinatorWriter(con, AuditLog(con))
        return index, FulltextSearchService(
            coordinator_con=con, index_db=index,
            evidence_dir=self._evidence_dir, writer=writer)

    def _fulltext_zwecke(self, person_id: int) -> Response:
        """
        GET /api/fulltext/zwecke — die Auswahlliste der Zweckcodes (E-3).

        AUS DER DATENBANK, nicht aus dem Code: die Sicht soll genau das
        anbieten, was der Fremdschluessel auch annimmt. Liefen Katalogtabelle
        und Vokabular auseinander, faellt es hier auf und nicht erst beim
        Schreiben.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_FULLTEXT_SEARCH):
            return self._forbidden(CAP_FULLTEXT_SEARCH)
        from management.search.release_repo import FulltextReleaseRepo
        con = self._ro_con()
        try:
            repo = FulltextReleaseRepo(con, None)
            zwecke = repo.zweck_katalog()
        finally:
            con.close()
        return Response.json(200, {
            "zwecke": zwecke,
            "hinweis": ("Die Zweckangabe ist bei JEDER Abfrage Pflicht. Der "
                        "Anteil von 'sonstiges' ist die Kennzahl dafuer, ob "
                        "diese Liste vollstaendig ist — steigt er, fehlt ein "
                        "Code."),
            "vollstaendig": bool(zwecke),
            "detail": (None if zwecke else
                       "Der Zweckkatalog ist leer — die Migration M036 ist "
                       "vermutlich nicht angewandt. Es ist NICHT gesagt, dass "
                       "keine Zwecke vorgesehen sind.")})

    def _fulltext_indexstand(self, person_id: int) -> Response:
        """GET /api/fulltext/indexstand — wie aktuell ist der Index?"""
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_FULLTEXT_SEARCH):
            return self._forbidden(CAP_FULLTEXT_SEARCH)
        con = self._ro_con()
        index = None
        try:
            index, dienst = self._fulltext_service(con)
            return Response.json(200, dienst.indexstand())
        except Exception as exc:
            return self._fulltext_fehler(exc)
        finally:
            if index is not None:
                index.close()
            con.close()

    def _fulltext_releases(self, person_id: int, query) -> Response:
        """
        GET /api/fulltext/releases[?subject_id=N] — bestehende Freigaben.

        OHNE Parameter: die eigenen ('was darf ich sehen?') — dafuer genuegt
        das Suchrecht. MIT subject_id: wer darf in DIESEN Fall sehen — das ist
        die Aufsichtsrichtung und verlangt 'fulltext.release'.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_FULLTEXT_SEARCH):
            return self._forbidden(CAP_FULLTEXT_SEARCH)
        raw = self._q1(query, "subject_id")
        from management.search.release_repo import FulltextReleaseRepo
        con = self._ro_con()
        try:
            repo = FulltextReleaseRepo(con, None)
            if raw in (None, ""):
                return Response.json(200, {
                    "richtung": "eigene",
                    "person_id": person_id,
                    "freigaben": repo.fuer_person(person_id)})
            if not policy.can(CAP_FULLTEXT_RELEASE):
                return self._forbidden(CAP_FULLTEXT_RELEASE)
            try:
                uid = int(raw)
            except (TypeError, ValueError):
                return Response.json(400, {
                    "error": "bad_request",
                    "detail": "subject_id ungueltig."})
            return Response.json(200, {
                "richtung": "fall",
                "subject_id": uid,
                "freigaben": repo.fuer_fall(uid)})
        finally:
            con.close()

    def _fulltext_lage(self, person_id: int,
                       payload: Dict[str, Any]) -> Response:
        """
        POST /api/fulltext/lage — STUFE 1: Trefferlage OHNE Textausschnitt.

        Rumpf: {begriff, zweck_code, zweck_freitext?, modus?}
        Frei fuer alle mit 'evidence.fulltext_search' (kein Scope, E-2).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_FULLTEXT_SEARCH):
            return self._forbidden(CAP_FULLTEXT_SEARCH)
        con = self._rw_con()
        index = None
        try:
            index, dienst = self._fulltext_service(con)
            return Response.json(200, dienst.lage(
                begriff=payload.get("begriff") or "",
                person_id=person_id,
                zweck_code=payload.get("zweck_code"),
                zweck_freitext=payload.get("zweck_freitext"),
                modus=payload.get("modus") or "wort"))
        except Exception as exc:
            return self._fulltext_fehler(exc)
        finally:
            if index is not None:
                index.close()
            con.close()

    def _fulltext_inhalt(self, person_id: int,
                         payload: Dict[str, Any]) -> Response:
        """
        POST /api/fulltext/inhalt — STUFE 2: die Treffer EINES Falls mit Text.

        Rumpf: {begriff, subject_id, zweck_code, zweck_freitext?, modus?}

        EINE ABWEISUNG IST HIER KEIN 403. Die Antwort kommt mit 200 und
        'erlaubt': false samt Grund — denn die Abweisung ist ein
        ERMITTLUNGSERGEBNIS ('zu diesem Fall gibt es etwas, aber Sie duerfen
        es nicht sehen; hier ist der Weg zur Freigabe') und kein
        Berechtigungsfehler. Ein 403 sagte 'Sie haben hier nichts verloren' —
        das waere sachlich falsch und wuerde die Ermittlerin von dem Schritt
        abhalten, den das Modell gerade vorsieht. Das FEHLENDE SUCHRECHT ist
        dagegen sehr wohl ein 403 (s. oben).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_FULLTEXT_SEARCH):
            return self._forbidden(CAP_FULLTEXT_SEARCH)
        try:
            uid = int(payload.get("subject_id"))
        except (TypeError, ValueError):
            return Response.json(400, {
                "error": "bad_request",
                "detail": "subject_id fehlt/ungueltig."})
        con = self._rw_con()
        index = None
        try:
            index, dienst = self._fulltext_service(con)
            return Response.json(200, dienst.inhalt(
                begriff=payload.get("begriff") or "",
                subject_id=uid, person_id=person_id,
                zweck_code=payload.get("zweck_code"),
                zweck_freitext=payload.get("zweck_freitext"),
                modus=payload.get("modus") or "wort"))
        except Exception as exc:
            return self._fulltext_fehler(exc)
        finally:
            if index is not None:
                index.close()
            con.close()

    def _fulltext_release_grant(self, person_id: int,
                                payload: Dict[str, Any]) -> Response:
        """
        POST /api/fulltext/release/grant — Inhaltsfreigabe erteilen.

        Rumpf: {subject_id, person_id, zweck_code, zweck_freitext?,
                begruendung}
        Recht: 'fulltext.release' (NICHT 'evidence.fulltext_search' — wer
        sucht, gibt damit nichts frei).
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_FULLTEXT_RELEASE):
            return self._forbidden(CAP_FULLTEXT_RELEASE)
        from management.gateway.coordinator_writer import CoordinatorWriter
        from management.search.release_repo import (
            FulltextReleaseFehler, FulltextReleaseRepo)
        con = self._rw_con()
        try:
            repo = FulltextReleaseRepo(con, CoordinatorWriter(con,
                                                              AuditLog(con)))
            erg = repo.erteile(
                subject_id=payload.get("subject_id"),
                person_id=payload.get("person_id"),
                zweck_code=payload.get("zweck_code"),
                zweck_freitext=payload.get("zweck_freitext"),
                begruendung=payload.get("begruendung") or "",
                actor_id=person_id)
            return Response.json(200, {"ok": True, **erg})
        except FulltextReleaseFehler as exc:
            return Response.json(400, {"error": "release_failed",
                                       "detail": str(exc)})
        except (TypeError, ValueError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        finally:
            con.close()

    def _fulltext_release_revoke(self, person_id: int,
                                 payload: Dict[str, Any]) -> Response:
        """
        POST /api/fulltext/release/revoke — Inhaltsfreigabe widerrufen.

        Rumpf: {release_id, reason}. Die Zeile BLEIBT stehen; nur is_active
        kippt. Ein stilles Loeschen vernichtete die Erkenntnis "es wurde
        einmal freigegeben", und gerade die ist die aufsichtsrelevante.
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_FULLTEXT_RELEASE):
            return self._forbidden(CAP_FULLTEXT_RELEASE)
        from management.gateway.coordinator_writer import CoordinatorWriter
        from management.search.release_repo import (
            FulltextReleaseFehler, FulltextReleaseRepo)
        con = self._rw_con()
        try:
            repo = FulltextReleaseRepo(con, CoordinatorWriter(con,
                                                              AuditLog(con)))
            erg = repo.widerrufe(
                release_id=payload.get("release_id"),
                reason=payload.get("reason") or "",
                actor_id=person_id)
            return Response.json(200, {"ok": True, **erg})
        except FulltextReleaseFehler as exc:
            return Response.json(400, {"error": "revoke_failed",
                                       "detail": str(exc)})
        except (TypeError, ValueError) as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        finally:
            con.close()

    @staticmethod
    def _fulltext_fehler(exc: Exception) -> Response:
        """
        Uebersetzt die Fachfehler der Suche in HTTP — jeder mit Klartext.

        DREI VERSCHIEDENE LAGEN, DREI VERSCHIEDENE ANTWORTEN:
          * SearchIndexFehler -> 503. Die Anlage kann nicht suchen (FTS5 oder
            trigram fehlen, Indexdatei nicht anlegbar). Das ist ein
            BETRIEBSZUSTAND und darf nicht wie ein Leerbefund aussehen.
          * FulltextSearchFehler -> 400. Die ANFRAGE ist unbrauchbar (fehlende
            oder falsche Zweckangabe). Der Klartext nennt die zulaessigen
            Codes, damit die Sicht ihn anzeigen kann.
          * alles andere -> weiterreichen. Ein unerwarteter Fehler wird NICHT
            zu einer freundlichen 400 verkleinert; er gehoert ins Protokoll
            und in die 500 des Handlers.
        """
        from db.search_index_db import SearchIndexFehler
        from management.search.search_service import FulltextSearchFehler
        if isinstance(exc, SearchIndexFehler):
            logger.error("Volltextsuche nicht betriebsbereit: %s", exc)
            return Response.json(503, {
                "error": "index_unavailable", "detail": str(exc)})
        if isinstance(exc, FulltextSearchFehler):
            return Response.json(400, {
                "error": "bad_request", "detail": str(exc)})
        raise exc

    # =========================================================================
    # Build 545 (AP-3G / Idee 37): persoenliche Ansichtseinstellung
    # =========================================================================
    #
    # DREI ENDPUNKTE, EINE REGEL: eine Person kann ausschliesslich ihre
    # EIGENE Oberflaeche einrichten. Es gibt deshalb keinen person_id-
    # Parameter, den man setzen koennte — die handelnde Person IST die
    # betroffene. Der Repo prueft das ein zweites Mal (Gueretel und
    # Hosentraeger; die Pruefung dort ist die fachlich massgebliche).
    #
    # KEINE FAEHIGKEIT AN DIESEN ENDPUNKTEN. Begruendung im Kopf von
    # m037_view_pref.py: eine Vorliebe kann keine Sicht oeffnen, fuer die das
    # Recht fehlt, weil der Rechtefilter ZULETZT laeuft. Was sie kann, ist
    # etwas ausblenden — und dagegen hilft kein Recht, sondern Sichtbarkeit
    # (Zaehler in der Navigation, Erreichbarkeit ueber die Kommandopalette,
    # Ruecksetzen mit einem Klick; Build 546).

    def _viewprefs(self, person_id: int) -> Response:
        """
        GET /api/viewprefs — die eigene Einstellung UND der Katalog dessen,
        was einstellbar ist.

        WARUM DER KATALOG MITKOMMT statt in einem zweiten Endpunkt zu
        stehen: die Oberflaeche braucht immer beides zugleich, und zwei
        Abrufe koennten in dem Moment auseinanderlaufen, in dem eine Kachel
        wegfaellt. So ist die Antwort in sich stimmig.

        JE KACHEL STEHT 'erlaubt' — die Auskunft des SERVERS darueber, ob die
        speisende Faehigkeit vorliegt. Der Browser leitet das nicht selbst ab:
        die Zuordnung Kachel -> Recht wird an genau einer Stelle gefuehrt
        (viewpref_katalog.py), und das ist die Stelle, die der Server kennt.
        """
        from management.viewprefs import viewpref_katalog as vpkat
        from management.viewprefs.viewpref_repo import ViewPrefRepo

        con = self._ro_con()
        try:
            p = self._person(con, person_id)
            if p is None:
                return Response.json(404, {"error": "unknown_person",
                                           "person_id": person_id})
            gespeichert = ViewPrefRepo(con).lade(person_id)
        finally:
            con.close()

        policy = self.resolve_policy(person_id)
        widgets = [{
            "key": w.key, "label": w.label, "beschreibung": w.beschreibung,
            "cap": w.cap, "standard": bool(w.standard),
            "erlaubt": bool(policy.can(w.cap)),
        } for w in vpkat.WIDGETS]

        return Response.json(200, {
            "person_id": person_id,
            "sichten": gespeichert["sichten"],
            "widgets": gespeichert["widgets"],
            # Gespeicherte Eintraege, die der Katalog nicht (mehr) kennt.
            # Sie werden BENANNT statt uebergangen (Grundregel 1); die
            # Oberflaeche zeigt sie als Hinweis mit Aufraeum-Vorschlag.
            "unbekannt": gespeichert["unbekannt"],
            "katalog": {
                "sichten": list(vpkat.STEUERBARE_SICHTEN),
                "nicht_steuerbar": dict(vpkat.NICHT_STEUERBAR),
                "widgets": widgets,
                "standard_widgets": list(vpkat.standard_widgets()),
            },
        })

    def _viewprefs_speichern(self, person_id: int,
                             payload: Dict[str, Any]) -> Response:
        """
        POST /api/viewprefs — {'sichten': [...], 'widgets': [...]}.

        Beide Felder sind einzeln optional; die nicht genannte Art bleibt
        unberuehrt. Ein Eintrag ist entweder die blosse Kennung ('dashboard')
        oder {'key': ..., 'sichtbar': true|false}. Die REIHENFOLGE der Liste
        ist die Reihenfolge — eine mitgeschickte Position gaebe es zweimal.
        """
        from management.viewprefs.viewpref_repo import (
            ViewPrefFehler, ViewPrefRepo)

        if "sichten" not in payload and "widgets" not in payload:
            return Response.json(400, {
                "error": "bad_request",
                "detail": "Weder 'sichten' noch 'widgets' angegeben — es "
                          "gaebe nichts zu speichern."})

        con = self._rw_con()
        try:
            repo = ViewPrefRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.speichern(
                person_id=person_id,
                sichten=payload.get("sichten"),
                widgets=payload.get("widgets"),
                actor_id=person_id)
        except ViewPrefFehler as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Speichern der Ansichtseinstellung "
                             "fehlgeschlagen")
            return Response.json(500, {"error": "viewprefs_write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "person_id": person_id,
                                   "gespeichert": res["gespeichert"],
                                   "audit_seqs": res["audit_seqs"]})

    def _viewprefs_zuruecksetzen(self, person_id: int,
                                 payload: Dict[str, Any]) -> Response:
        """
        POST /api/viewprefs/reset — {'art': 'sicht'|'widget'|'alle'}.

        Ohne Angabe: 'alle'. Danach gilt wieder die Werkseinstellung.
        """
        from management.viewprefs.viewpref_repo import (
            ViewPrefFehler, ViewPrefRepo)

        art = payload.get("art", "alle")
        if not isinstance(art, str):
            return Response.json(400, {"error": "bad_request",
                                       "detail": "'art' muss eine "
                                                 "Zeichenkette sein."})
        con = self._rw_con()
        try:
            repo = ViewPrefRepo(con, CoordinatorWriter(con, AuditLog(con)))
            res = repo.zuruecksetzen(person_id=person_id, art=art,
                                     actor_id=person_id)
        except ViewPrefFehler as exc:
            return Response.json(400, {"error": "bad_request",
                                       "detail": str(exc)})
        except Exception as exc:                       # noqa: BLE001
            logger.exception("Zuruecksetzen der Ansichtseinstellung "
                             "fehlgeschlagen")
            return Response.json(500, {"error": "viewprefs_reset_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "person_id": person_id,
                                   "arten": res["arten"],
                                   "geloescht": res["geloescht"],
                                   "audit_seq": res["audit_seq"]})
