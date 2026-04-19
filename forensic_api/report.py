# =============================================================================
# forensic_api/report.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/report — GET und POST (Fenster 3: Bericht-Editor).
#
# GET ohne Parameter:
#   Liefert die Editor-Shell-HTML (Editor.js wird in AP-E4 eingebunden).
#
# GET mit ?format=json:
#   Liefert alle Berichte und deren Bloecke als JSON.
#   Schema: { "reports": [...], "lock": {...} | null }
#
# POST — Aktionen:
#   action=acquire_lock   -> Lock erwerben; Response: {"lock_id": "..."}
#   action=release_lock   -> Lock freigeben; lock_id im Body
#
#   Weitere schreibende Aktionen (AP-E3) werden in einem Folgebuild ergaenzt:
#   action=add_block, action=delete_block, action=update_order,
#   action=add_evidence, action=remove_evidence, action=approve.
#
# Lock-Pruefung (§8.6 Bauplan B4):
#   Schreibende Aktionen pruefen ob der anfragende SAMAccountName den aktiven
#   Lock haelt via editor_locks. Kein gueltiger Lock -> HTTP 423 (Locked).
#   Lock-ID wird per X-Forensic-Lock-Id-Header oder im JSON-Body uebermittelt.
#
# CSP fuer Editorfenster:
#   Fuer /_forensic/report wird script-src 'unsafe-inline' 'unsafe-eval' und
#   style-src 'unsafe-inline' erlaubt (Editor.js-Anforderung).
#   Beleg: AP-E1, Projektgespraech 2026-04-19
#
# Datenbankzugriff:
#   evidence_<uid>.db (READ-WRITE) — Berichte, Bloecke, Locks
#
# Changelog:
#   Build 012: Erstimplementierung mit report_paragraphs-Modell.
#   Build 043 (AP-E1): Umgeschrieben auf Editor.js-Block-Modell.
#     - GET ?format=json liefert reports + blocks statt paragraphs.
#     - POST: add_paragraph/suggest_change/omit_paragraph entfernt.
#     - POST: acquire_lock/release_lock unveraendert.
#     - _EDITOR_HTML: Platzhalter fuer Editor.js-Bundle (AP-E4).
#     - CSP-Header ergaenzt.
#     Beleg: AP-E1, Projektgespraech 2026-04-19
#
# Version: v0.6.043 · Build: 043 · 2026-04-19
# =============================================================================

from __future__ import annotations

import html as html_module
import json
import sqlite3
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# HTML-Rahmen fuer Fenster 3 (Bericht-Editor).
# Editor.js-Bundle wird in AP-E4 eingebunden (/_forensic/static/editor/editor.bundle.js).
# CSP erlaubt unsafe-inline und unsafe-eval fuer Editor.js.
# Beleg: AP-E1, Projektgespraech 2026-04-19
_EDITOR_HTML = """\
<!DOCTYPE html>
<html lang="de">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Bericht-Editor \u00b7 {username} \u00b7 ID: {user_id}</title>
    <link rel="stylesheet" href="/_forensic/userinfo.css">
  </head>
  <body id="report-editor-body"
        data-user-id="{user_id}"
        data-username="{username}"
        data-autosave-debounce-ms="{autosave_debounce_ms}">
    <div id="report-selector-container">
      <!-- Berichtsauswahl wird von editor.js/initReportSelector() befuellt -->
    </div>
    <div id="report-editor-container">
      <!-- Editor-Toolbar und editorjs-holder werden von userinfo.js/initEditor() erzeugt -->
    </div>
    <!-- 1) Editor.js-Bundle (AP-E2: build_editor_bundle.py ausfuehren falls fehlend) -->
    <script src="/_forensic/static/editor/editor.bundle.js"></script>
    <!-- 2) Editor-Modul: initReportSelector, EvidenceBlock, toggleAnnotationSidebar -->
    <script src="/_forensic/editor.js" defer></script>
    <!-- 3) userinfo.js: initEditor(), Lock/SSE — last, weil es editor.js benoetigt -->
    <script src="/_forensic/userinfo.js" defer></script>
  </body>
</html>"""

# CSP-Header fuer das Editorfenster.
# unsafe-inline und unsafe-eval sind fuer Editor.js erforderlich.
# Beleg: AP-E1, Projektgespraech 2026-04-19
_EDITOR_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self';"
)

_LOCK_REQUIRED = json.dumps(
    {"error": "Lock erforderlich", "code": "LOCK_REQUIRED"},
    ensure_ascii=False,
).encode("utf-8")


def _json_err(msg: str, code: str = "ERROR") -> bytes:
    return json.dumps({"error": msg, "code": code}, ensure_ascii=False).encode("utf-8")


class ReportEndpoint:
    """
    Endpunkt /_forensic/report — GET und POST (Fenster 3).
    Implementiert Editor.js-basiertes Berichtssystem (AP-E1).
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context
        self._config  = config

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def handle_get(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        fmt = params.get("format", [None])[0]
        if fmt == "json":
            self._handle_get_json(handler)
        else:
            self._handle_get_html(handler)

    def _handle_get_html(self, handler: "ForensicRequestHandler") -> None:
        """Liefert die Editor-Shell-HTML mit CSP-Header aus."""
        safe_username = html_module.escape(
            self._context.username or f"uid_{self._context.user_id}"
        )
        autosave_ms = int(
            getattr(self._config, "get", lambda k, d: d)(
                "editor.autosave_debounce_ms", 1500
            )
        )
        page_html = _EDITOR_HTML.format(
            username=safe_username,
            user_id=self._context.user_id,
            autosave_debounce_ms=autosave_ms,
        )
        body = page_html.encode("utf-8")
        handler.send_response_body(
            200, body,
            content_type="text/html; charset=utf-8",
            extra_headers={"Content-Security-Policy": _EDITOR_CSP},
        )
        logger.debug(
            "/_forensic/report (HTML) ausgeliefert: user_id=%d",
            self._context.user_id,
        )

    def _handle_get_json(self, handler: "ForensicRequestHandler") -> None:
        """
        Liefert alle Berichte und deren Bloecke als JSON.
        Schema: { "reports": [...], "lock": {...} | null }
        Beleg: AP-E1, Projektgespraech 2026-04-19
        """
        edb = self._bundle.evidence
        reports = edb.get_reports()
        lock = edb.get_lock()

        reports_payload = []
        for r in reports:
            blocks = edb.get_blocks_ordered(r.id)
            reports_payload.append({
                "id":          r.id,
                "report_type": r.report_type,
                "sequence_nr": r.sequence_nr,
                "title":       r.title,
                "status":      r.status,
                "created_by":  r.created_by,
                "created_at":  r.created_at,
                "blocks": [
                    {
                        "block_id":   b.block_id,
                        "block_type": b.block_type,
                        "block_data": json.loads(b.block_data),
                        "owner":      b.owner,
                        "updated_at": b.updated_at,
                    }
                    for b in blocks
                ],
            })

        payload = {
            "reports": reports_payload,
            "lock": {
                "locked_by": lock.locked_by,
                "locked_at": lock.locked_at,
            } if lock else None,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def handle_post(
        self,
        handler: "ForensicRequestHandler",
        body_bytes: bytes,
    ) -> None:
        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            handler.send_response_body(
                400,
                _json_err(f"Ungueltiger JSON-Body: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        action = data.get("action", "")
        investigator = self._context.username or ""

        if action == "acquire_lock":
            self._action_acquire_lock(handler, data, investigator)
        elif action == "release_lock":
            self._action_release_lock(handler, data)
        else:
            # Weitere schreibende Aktionen werden in AP-E3 ergaenzt.
            # Bis dahin: 400 mit Hinweis.
            handler.send_response_body(
                400,
                _json_err(
                    f"Unbekannte oder noch nicht implementierte Aktion: '{action}'",
                    "UNKNOWN_ACTION",
                ),
                content_type="application/json; charset=utf-8",
            )

    # ------------------------------------------------------------------
    # Lock-Aktionen
    # ------------------------------------------------------------------

    def _action_acquire_lock(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        sse_client = str(data.get("sse_client", ""))
        if not sse_client:
            handler.send_response_body(
                400,
                _json_err("sse_client fehlt", "MISSING_SSE_CLIENT"),
                content_type="application/json; charset=utf-8",
            )
            return

        edb = self._bundle.evidence
        lock_id = edb.acquire_lock(locked_by=investigator, sse_client=sse_client)

        if lock_id is None:
            current = edb.get_lock()
            locked_by = current.locked_by if current else "?"
            body = json.dumps(
                {
                    "error":     "Lock bereits belegt",
                    "code":      "LOCK_CONFLICT",
                    "locked_by": locked_by,
                },
                ensure_ascii=False,
            ).encode("utf-8")
            handler.send_response_body(
                423, body, content_type="application/json; charset=utf-8"
            )
            return

        body = json.dumps({"lock_id": lock_id}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )
        logger.info(
            "acquire_lock: '%s' hat Lock erworben (sse_client=%s)",
            investigator, sse_client,
        )

    def _action_release_lock(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> None:
        lock_id = str(data.get("lock_id", ""))
        if not lock_id:
            handler.send_response_body(
                400,
                _json_err("lock_id fehlt", "MISSING_LOCK_ID"),
                content_type="application/json; charset=utf-8",
            )
            return

        freed = self._bundle.evidence.release_lock(lock_id)
        body = json.dumps({"freed": freed}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )

    def _require_lock(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> "str | None":
        """
        Prueft ob ein gueltiger Lock gehalten wird.
        Gibt lock_id zurueck wenn gueltig, sendet HTTP 423 wenn nicht.
        """
        lock_id = (
            handler.headers.get("X-Forensic-Lock-Id", "")
            or str(data.get("lock_id", ""))
        )
        if not lock_id:
            handler.send_response_body(
                423, _LOCK_REQUIRED,
                content_type="application/json; charset=utf-8",
            )
            return None
        if not self._bundle.evidence.validate_lock(lock_id):
            handler.send_response_body(
                423, _LOCK_REQUIRED,
                content_type="application/json; charset=utf-8",
            )
            return None
        return lock_id
