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
# Build 366 (Support-Historie Backend): /api/support (support_history.view,
#   scope-aware) liefert die belegbasiert rekonstruierten Support-Sitzungen
#   (SupportOverviewRepo), je Sitzung markiert mit mine_as_supporter/on_my_case.
#
# Version: v0.7.366 · Build: 366 · 2026-07-10
# =============================================================================

import json
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from management.audit.audit_log import AuditLog
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
                 static_dir: Optional[Path] = None) -> None:
        self._db_path = db_path
        # Statische Auslieferung gekapselt (Grundregel 10). static_dir ist im
        # Test injizierbar; PROD nutzt STATIC_DIR neben diesem Modul.
        self._static = StaticAssets(static_dir or STATIC_DIR)

    # ------------------------------------------------------------- Verbindung
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
