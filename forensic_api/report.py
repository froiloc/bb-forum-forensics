# =============================================================================
# forensic_api/report.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/report — GET und POST (Fenster 3: Bericht-Editor).
#
# GET ohne Parameter:
#   Liefert die vollständige HTML-Seite des Bericht-Editors (§5.3 Bauplan B4).
#
# GET mit ?format=json:
#   Liefert den aktuellen Berichtsinhalt als JSON.
#   Aufgerufen vom Read-Only-Reiter in Fenster 2 bei "Aktualisieren".
#
# POST — Aktionen (§8.5 Bauplan B4):
#   action=acquire_lock   → Lock erwerben; Response: {"lock_id": "..."}
#   action=release_lock   → Lock freigeben; lock_id im Body
#   action=add_paragraph  → Neuen Paragraph anlegen (Lock erforderlich)
#   action=suggest_change → Änderungsvorschlag einreichen (kein Lock nötig)
#   action=approve        → Freigabe (nur Chef-Ermittlerin)
#   action=omit_paragraph → Paragraph ausblenden (nur Chef-Ermittlerin)
#
# Lock-Prüfung (§8.6 Bauplan B4):
#   Schreibende Aktionen (add_paragraph, omit_paragraph) prüfen ob der
#   anfragende SAMAccountName den aktiven Lock hält via editor_locks.
#   Kein gültiger Lock → HTTP 423 (Locked).
#   Lock-ID wird per X-Forensic-Lock-Id-Header oder im JSON-Body übermittelt.
#
# SSE-Client-ID (Schicht 2 des Lock-Mechanismus):
#   Bei acquire_lock muss sse_client im Body mitgegeben werden.
#   Der Server verknüpft den Lock mit dieser SSE-Client-ID.
#   Bei SSE-Verbindungsabriss gibt events.py den Lock über
#   release_lock_by_sse_client() frei.
#
# Datenbankzugriff:
#   evidence_<uid>.db (READ-WRITE) — Paragraphen, Anker, Vorschläge, Freigaben, Locks
#
# Neue Datei — Baustelle 4.
# Version: v0.1.0 · Build: 012 · 2026-04-14
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

# HTML-Rahmen für Fenster 3 (Bericht-Editor).
# Platzhalter: {username}, {user_id}
_EDITOR_HTML = """\
<!DOCTYPE html>
<html lang="de">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Bericht-Editor \u00b7 {username} \u00b7 ID: {user_id}</title>
    <link rel="stylesheet" href="/_forensic/userinfo.css">
  </head>
  <body id="report-editor-body" data-user-id="{user_id}">
    <div id="report-editor-container">
      <!-- Bericht-Editor — per userinfo.js initialisiert (§8 Bauplan B4) -->
      <!-- Lock-Status, Paragraphen und Editor-UI werden per JS aufgebaut -->
    </div>
    <script src="/_forensic/userinfo.js" defer></script>
  </body>
</html>"""

# JSON-Antwort bei fehlendem / ungültigem Lock (HTTP 423)
_LOCK_REQUIRED = json.dumps(
    {"error": "Lock erforderlich", "code": "LOCK_REQUIRED"},
    ensure_ascii=False,
).encode("utf-8")

_LOCK_CONFLICT = json.dumps(
    {"error": "Lock bereits belegt", "code": "LOCK_CONFLICT"},
    ensure_ascii=False,
).encode("utf-8")


def _json_err(msg: str, code: str = "ERROR") -> bytes:
    return json.dumps({"error": msg, "code": code}, ensure_ascii=False).encode("utf-8")


class ReportEndpoint:
    """
    Endpunkt /_forensic/report — GET und POST (Fenster 3).

    Implementiert den kollaborativen Bericht-Editor mit dreischichtigem
    Lock-Mechanismus (§8.6 Bauplan B4).
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
        """
        Verarbeitet GET /_forensic/report und GET /_forensic/report?format=json.

        Args:
            handler: ForensicRequestHandler-Instanz.
            params:  Query-Parameter als Dict (aus urllib.parse.parse_qs).
        """
        fmt = params.get("format", [None])[0]

        if fmt == "json":
            self._handle_get_json(handler)
        else:
            self._handle_get_html(handler)

    def _handle_get_html(self, handler: "ForensicRequestHandler") -> None:
        """Liefert die Editor-HTML-Seite (Fenster 3) aus."""
        safe_username = html_module.escape(
            self._context.username or f"uid_{self._context.user_id}"
        )
        page_html = _EDITOR_HTML.format(
            username=safe_username,
            user_id=self._context.user_id,
        )
        body = page_html.encode("utf-8")
        handler.send_response_body(200, body, content_type="text/html; charset=utf-8")
        logger.debug("/_forensic/report (HTML) ausgeliefert: user_id=%d",
                     self._context.user_id)

    def _handle_get_json(self, handler: "ForensicRequestHandler") -> None:
        """Liefert den aktuellen Berichtsinhalt als JSON (für Read-Only-Reiter)."""
        edb = self._bundle.evidence
        paras = edb.get_paragraphs(include_omitted=False)
        lock = edb.get_lock()

        payload = {
            "paragraphs": [
                {
                    "id":         p.id,
                    "author":     p.author,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                    "content":    p.content,
                    "status":     p.status,
                    "sort_order": p.sort_order,
                }
                for p in paras
            ],
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
        """
        Verarbeitet POST /_forensic/report.

        Erwartet JSON-Body mit Schlüssel "action" (§8.5 Bauplan B4).
        Aktionen: acquire_lock, release_lock, add_paragraph,
                  suggest_change, approve, omit_paragraph.

        Args:
            handler:    ForensicRequestHandler-Instanz.
            body_bytes: Request-Body (JSON).
        """
        # Body parsen
        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            handler.send_response_body(
                400,
                _json_err(f"Ungültiger JSON-Body: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        action = data.get("action", "")

        # SAMAccountName des anfragenden Ermittlers
        investigator = self._context.username or ""

        if action == "acquire_lock":
            self._action_acquire_lock(handler, data, investigator)
        elif action == "release_lock":
            self._action_release_lock(handler, data)
        elif action == "add_paragraph":
            self._action_add_paragraph(handler, data, investigator)
        elif action == "suggest_change":
            self._action_suggest_change(handler, data, investigator)
        elif action == "approve":
            self._action_approve(handler, data, investigator)
        elif action == "omit_paragraph":
            self._action_omit_paragraph(handler, data, investigator)
        else:
            handler.send_response_body(
                400,
                _json_err(f"Unbekannte Aktion: '{action}'", "UNKNOWN_ACTION"),
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
        """
        action=acquire_lock: Editor-Lock erwerben.
        Body: { "action": "acquire_lock", "sse_client": "..." }
        Response: { "lock_id": "..." } oder HTTP 423.
        """
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
            # Lock belegt
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
        logger.info("acquire_lock: '%s' hat Lock erworben (sse_client=%s)",
                    investigator, sse_client)

    def _action_release_lock(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> None:
        """
        action=release_lock: Editor-Lock freigeben.
        Body: { "action": "release_lock", "lock_id": "..." }
        """
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

    # ------------------------------------------------------------------
    # Schreibende Aktionen (Lock erforderlich)
    # ------------------------------------------------------------------

    def _require_lock(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> "str | None":
        """
        Prüft ob ein gültiger Lock gehalten wird.
        Gibt lock_id zurück wenn gültig, sendet HTTP 423 und gibt None zurück wenn nicht.
        Lock-ID wird aus X-Forensic-Lock-Id-Header oder data["lock_id"] gelesen.
        """
        lock_id = (
            handler.headers.get("X-Forensic-Lock-Id", "")
            or str(data.get("lock_id", ""))
        )
        if not lock_id:
            handler.send_response_body(
                423, _LOCK_REQUIRED, content_type="application/json; charset=utf-8"
            )
            return None

        if not self._bundle.evidence.validate_lock(lock_id):
            handler.send_response_body(
                423, _LOCK_REQUIRED, content_type="application/json; charset=utf-8"
            )
            return None

        return lock_id

    def _action_add_paragraph(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        """
        action=add_paragraph: Neuen Paragraph anlegen.
        Body: { "action": "add_paragraph", "content": "...",
                "sort_after": N (optional), "lock_id": "..." }
        Lock erforderlich (§8.6 Bauplan B4).
        """
        if self._require_lock(handler, data) is None:
            return

        content = str(data.get("content", "")).strip()
        if not content:
            handler.send_response_body(
                400,
                _json_err("content fehlt oder leer", "EMPTY_CONTENT"),
                content_type="application/json; charset=utf-8",
            )
            return

        sort_after_raw = data.get("sort_after")
        sort_after = int(sort_after_raw) if sort_after_raw is not None else None

        try:
            para_id = self._bundle.evidence.add_paragraph(
                author=investigator,
                content=content,
                sort_after=sort_after,
            )
        except Exception as exc:
            logger.error("add_paragraph fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500,
                _json_err(f"Datenbankfehler: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        body = json.dumps({"paragraph_id": para_id}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )
        logger.info("Paragraph %d angelegt von '%s'", para_id, investigator)

    def _action_suggest_change(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        """
        action=suggest_change: Änderungsvorschlag einreichen (kein Lock nötig).
        Body: { "action": "suggest_change", "paragraph_id": N,
                "suggested_content": "..." }
        """
        paragraph_id_raw = data.get("paragraph_id")
        if paragraph_id_raw is None:
            handler.send_response_body(
                400,
                _json_err("paragraph_id fehlt", "MISSING_PARAGRAPH_ID"),
                content_type="application/json; charset=utf-8",
            )
            return

        content = str(data.get("suggested_content", "")).strip()
        if not content:
            handler.send_response_body(
                400,
                _json_err("suggested_content fehlt", "EMPTY_CONTENT"),
                content_type="application/json; charset=utf-8",
            )
            return

        try:
            sugg_id = self._bundle.evidence.add_suggestion(
                paragraph_id=int(paragraph_id_raw),
                author=investigator,
                suggested_content=content,
            )
        except Exception as exc:
            logger.error("add_suggestion fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500,
                _json_err(f"Datenbankfehler: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        body = json.dumps({"suggestion_id": sugg_id}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )

    def _action_approve(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        """
        action=approve: Bericht freigeben.
        Body: { "action": "approve", "is_final": false, "note": "..." }
        """
        is_final = bool(data.get("is_final", False))
        note     = str(data.get("note", "")).strip() or None

        try:
            appr_id = self._bundle.evidence.add_approval(
                approved_by=investigator,
                is_final=is_final,
                note=note,
            )
        except Exception as exc:
            logger.error("add_approval fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500,
                _json_err(f"Datenbankfehler: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        body = json.dumps({"approval_id": appr_id}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )

    def _action_omit_paragraph(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        """
        action=omit_paragraph: Paragraph als 'omitted' markieren.
        Nur Chef-Ermittlerin hat dieses Recht — Prüfung liegt beim Client/Toolbar.
        Body: { "action": "omit_paragraph", "paragraph_id": N,
                "reason": "...", "lock_id": "..." }
        Lock erforderlich (§8.6 Bauplan B4).
        """
        if self._require_lock(handler, data) is None:
            return

        paragraph_id_raw = data.get("paragraph_id")
        if paragraph_id_raw is None:
            handler.send_response_body(
                400,
                _json_err("paragraph_id fehlt", "MISSING_PARAGRAPH_ID"),
                content_type="application/json; charset=utf-8",
            )
            return

        reason = str(data.get("reason", "")).strip() or None

        try:
            found = self._bundle.evidence.omit_paragraph(
                paragraph_id=int(paragraph_id_raw),
                omitted_by=investigator,
                reason=reason,
            )
        except Exception as exc:
            logger.error("omit_paragraph fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500,
                _json_err(f"Datenbankfehler: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        if not found:
            handler.send_response_body(
                404,
                _json_err("Paragraph nicht gefunden", "NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )
            return

        body = json.dumps({"ok": True}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )
        logger.info("Paragraph %d von '%s' ausgeblendet", int(paragraph_id_raw), investigator)
