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
# Version: v0.7.346 · Build: 346 · 2026-07-10
# =============================================================================

import json
import sqlite3
from dataclasses import dataclass
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

#: Faehigkeits-Gates je Endpunkt (None = kein Gate, nur eigene Identitaet).
CAP_OVERVIEW = "dashboard.view"
CAP_INTEGRITY = "ops.view"


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


# Minimale Platzhalter-Shell. Die vollstaendige, policy-getriebene Cockpit-
# Oberflaeche folgt in einem browser-verifizierbaren Build (Split 314/315);
# diese Seite ist bewusst schlicht und dient dem Backend-Nachweis.
_SHELL_HTML = (
    "<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\">"
    "<title>AIW Verwaltung</title></head><body>"
    "<h1>AIW Verwaltung</h1>"
    "<p>Angemeldet als <strong>%(display)s</strong> (%(user)s).</p>"
    "<p>Backend aktiv (read-only). Die Cockpit-Oberflaeche folgt in einem "
    "gesonderten Build.</p>"
    "<ul><li><a href=\"/api/whoami\">/api/whoami</a></li>"
    "<li><a href=\"/api/overview\">/api/overview</a></li>"
    "<li><a href=\"/api/integrity\">/api/integrity</a></li></ul>"
    "</body></html>"
)


class ManagementApp:
    """Read-only Request-Aufloesung des Management-Servers (ohne Socket)."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

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
            return self._shell(person_id)
        if path == "/api/whoami":
            return self._whoami(person_id)
        if path == "/api/overview":
            return self._overview(person_id)
        if path == "/api/integrity":
            return self._integrity(person_id)
        if path.startswith("/static/"):
            return Response.json(
                404, {"error": "not_found",
                       "detail": "Statische Assets folgen mit dem Cockpit-Frontend."})
        return Response.json(404, {"error": "not_found", "path": path})

    # --------------------------------------------------------------- Helfer
    def _forbidden(self, capability: str) -> Response:
        return Response.json(
            403, {"error": "forbidden", "capability": capability})

    def _shell(self, person_id: int) -> Response:
        con = self._ro_con()
        try:
            p = self._person(con, person_id)
        finally:
            con.close()
        display = p["display_name"] if p else "?"
        user = p["system_username"] if p else "?"
        return Response.html(200, _SHELL_HTML % {"display": display, "user": user})

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

        items = [{
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
        } for c in cases]
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
