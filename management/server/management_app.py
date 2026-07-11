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
# Build 374 (Berichts-Abnahme, Lesepfad): GET /api/reports liest die Berichte
#   ALLER Faelle aus den evidence_<uid>.db (read-only), beschleunigt durch den
#   WAL-sicheren Fingerabdruck-Cache (m009). ManagementApp kennt nun das
#   evidence_db_dir (injizierbar; sonst aus config.yaml).
#
# Version: v0.7.374 · Build: 374 · 2026-07-10
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
from management.reports.reports_repo import ReportsRepo
from db.coordinator_db import DEFAULT_SUPPORT_STALE_SEC
from management.capacity.capacity_errors import CapacityError
from management.workload.workload_repo import (
    WorkloadRepo,
    WorkloadSchemaError,
)

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

logger = logging.getLogger(__name__)

# Zulaessige Werte fuer die auditierten Schreibpfade (Build 372).
_CASE_STATUSES = ("open", "in_progress", "approved", "closed")
_PRIORITY_MIN, _PRIORITY_MAX = 1, 5


def _case_overview_item(c) -> Dict[str, Any]:
    """Serialisiert eine CaseOverview in das JSON-Item (Overview + Meine Faelle)."""
    return {
        "user_id": c.user_id,
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
                 evidence_dir: Optional[str] = None) -> None:
        self._db_path = db_path
        # Statische Auslieferung gekapselt (Grundregel 10). static_dir ist im
        # Test injizierbar; PROD nutzt STATIC_DIR neben diesem Modul.
        self._static = StaticAssets(static_dir or STATIC_DIR)
        # Verzeichnis der evidence_<uid>.db (Berichts-Abnahme, Build 374).
        # Injizierbar (Test); sonst aus config.yaml (paths.evidence_db_dir).
        self._evidence_dir = evidence_dir or self._default_evidence_dir()
        # SCHREIB-TOKEN (Build 372): pro Serverlauf zufaellig. Wird nur ueber
        # den authentifizierten GET /api/whoami ausgeliefert und muss bei JEDEM
        # Schreibzugriff im Header 'X-AIW-Token' mitgeschickt werden. Schuetzt
        # gegen Fremd-POSTs ueber Netzwerk-Bridges/Tunnel und CSRF: wer die
        # GET-Antwort nicht lesen kann, kennt das Token nicht.
        self._write_token = secrets.token_urlsafe(32)

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
        if path == "/api/assignable":
            return self._assignable(person_id)
        if path == "/api/reports":
            return self._reports(person_id, query)
        if path.startswith("/static/"):
            return self._serve_static(path[len("/static/"):])
        return Response.json(404, {"error": "not_found", "path": path})

    # --------------------------------------------------------------- Helfer
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
                "SELECT user_id FROM cases WHERE assigned_to = ?",
                (person_id,)).fetchall()}
        finally:
            con.close()

        sessions = []
        for rec in records:
            mine = (rec.supporter_id == person_id)
            oncase = (rec.user_id in my_case_ids)
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
        """
        policy = self.resolve_policy(person_id)
        if not policy.can(CAP_REPORTS_REVIEW):
            return self._forbidden(CAP_REPORTS_REVIEW)
        scope = policy.scope(CAP_REPORTS_REVIEW)

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
        return Response.json(404, {"error": "not_found", "path": path})

    # ------------------------------------------------------------- Schreiben
    def _case_id(self, con: sqlite3.Connection, payload: Dict[str, Any]):
        """Validiert user_id und Existenz des Falls. -> (user_id, None) | (None, Response)"""
        raw = payload.get("user_id")
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            return None, Response.json(400, {
                "error": "bad_request", "detail": "user_id fehlt/ungueltig."})
        row = con.execute("SELECT 1 FROM cases WHERE user_id=?",
                          (user_id,)).fetchone()
        if row is None:
            return None, Response.json(400, {
                "error": "unknown_case", "user_id": user_id})
        return user_id, None

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
            user_id, err = self._case_id(con, payload)
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
                user_id, assignee, actor_id=person_id)
        except Exception as exc:  # kein stiller Fehlschlag (Grundregel 1)
            logger.exception("Zuweisung fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()

        return Response.json(200, {"ok": True, "user_id": user_id,
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
            user_id, err = self._case_id(con, payload)
            if err is not None:
                return err
            writer = CoordinatorWriter(con, AuditLog(con))
            seq = CasesRepo(con, writer).set_priority(
                user_id, prio, actor_id=person_id)
        except Exception as exc:
            logger.exception("Prioritaet setzen fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "user_id": user_id,
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
            user_id, err = self._case_id(con, payload)
            if err is not None:
                return err
            writer = CoordinatorWriter(con, AuditLog(con))
            seq = CasesRepo(con, writer).set_status(
                user_id, status, actor_id=person_id)
        except Exception as exc:
            logger.exception("Status setzen fehlgeschlagen")
            return Response.json(500, {"error": "write_failed",
                                       "detail": str(exc)})
        finally:
            con.close()
        return Response.json(200, {"ok": True, "user_id": user_id,
                                   "status": status, "audit_seq": seq})
