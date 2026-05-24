# =============================================================================
# forensic_api/editor_comment.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   Kommentar-Endpunkt-Logik fuer Fenster 3 (Bericht-Editor, B6 Phase 4).
#   Ausgelagert aus forensic_api/report.py zur besseren Modularitaet.
#
#   Implementiert folgende POST-Aktionen auf /_forensic/report:
#     add_comment     -- Neuen Kommentar zu einem Block anlegen (kein Lock noetig)
#     resolve_comment -- Kommentar-Status aendern (One-Way, Grundregel 15)
#
#   Die Berechtigungspruefung fuer resolve_comment erfolgt in evidence_db.py
#   (EvidenceDb.resolve_comment). Dieses Modul prueft:
#     - Pflichtfelder vorhanden
#     - Gueltiger resolution-Wert
#     - Lock fuer resolve_comment (addressed/dismissed benoetigen Lock,
#       revoked hingegen nicht, da es keine Schreiboperation auf dem Block ist)
#
# Datenbankzugriff:
#   evidence_<uid>.db (READ-WRITE) -- report_blocks, report_comments
#
# Abhaengigkeiten:
#   db.evidence_db.EvidenceDb, db.evidence_db.EvidenceDbError
#
# Changelog:
#   Build 102 (B6 Phase 4): Erstimplementierung.
#     Ausgelagert aus forensic_api/report.py (waren dort _action_add_comment
#     und _action_resolve_comment). Auf neues Block-API umgestellt:
#     get_comments_for_block() statt get_comments_for_paragraph().
#     is_chef-Pruefung gegen coordinator.db ergaenzt (war zuvor Client-seitig).
#     Beleg: Bauplan B6 v0.5 §4.4.4, §5, Projektgespraech 2026-05-06
#
# Version: v0.6.102 · Build: 102 · 2026-05-06
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle

logger = get_logger(__name__)


def _json_err(msg: str, code: str = "ERROR") -> bytes:
    return json.dumps({"error": msg, "code": code}, ensure_ascii=False).encode("utf-8")


def _json_ok(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


class EditorCommentEndpoint:
    """
    Kommentar-Aktionen fuer Fenster 3 (/_forensic/report POST).
    Wird von ReportEndpoint als Delegate fuer Kommentar-Aktionen verwendet.
    Beleg: Bauplan B6 v0.5 §4.4.4, §5, Projektgespraech 2026-05-06
    """

    def __init__(self, bundle: "DatabaseBundle", investigator: str) -> None:
        self._bundle      = bundle
        self._investigator = investigator

    # ------------------------------------------------------------------
    # Oeffentliche Aktionen
    # ------------------------------------------------------------------

    def action_add_comment(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> None:
        """
        Kommentar zu einem Block hinzufuegen.
        Kein Lock erforderlich (Grundregel: Kommentieren immer moeglich).
        Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
        """
        block_id     = str(data.get("block_id", "")).strip()
        comment_text = str(data.get("comment_text", "")).strip()
        suggested    = data.get("suggested_content")
        if suggested is not None:
            suggested = str(suggested).strip() or None

        if not block_id or not comment_text:
            handler.send_response_body(
                400,
                _json_err("block_id und comment_text erforderlich", "MISSING_FIELDS"),
                content_type="application/json; charset=utf-8",
            )
            return

        from db.evidence_db import EvidenceDbError
        try:
            cid = self._bundle.evidence.add_comment(
                block_id=block_id,
                author=self._investigator,
                comment_text=comment_text,
                suggested_content=suggested,
            )
        except EvidenceDbError as exc:
            handler.send_response_body(
                400, _json_err(str(exc)),
                content_type="application/json; charset=utf-8",
            )
            return

        logger.info(
            "Kommentar angelegt: comment_id=%d block_id=%s von '%s'",
            cid, block_id, self._investigator,
        )
        handler.send_response_body(
            201, _json_ok({"comment_id": cid}),
            content_type="application/json; charset=utf-8",
        )

    def action_resolve_comment(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        lock_id: str | None,
    ) -> None:
        """
        Kommentar-Status aendern (One-Way, Grundregel 15).

        addressed / dismissed: Lock erforderlich (Schreiboperation auf Block).
        revoked:               Kein Lock noetig (Kommentator zieht zurueck).

        is_chef wird gegen coordinator.db geprueft — nicht aus dem Request
        uebernommen (verhindert Privilege-Escalation durch manipulierte Anfragen).
        Beleg: Bauplan B6 v0.5 §4.4.4, Grundregel 15, Projektgespraech 2026-05-06
        """
        comment_id = data.get("comment_id")
        resolution = str(data.get("resolution", "")).strip()

        if not comment_id or resolution not in ("addressed", "dismissed", "revoked"):
            handler.send_response_body(
                400,
                _json_err(
                    "comment_id und resolution "
                    "('addressed'|'dismissed'|'revoked') erforderlich",
                    "MISSING_FIELDS",
                ),
                content_type="application/json; charset=utf-8",
            )
            return

        # addressed/dismissed benoetigen Lock (aendert effektiv den Block-Zustand)
        if resolution in ("addressed", "dismissed"):
            if not lock_id:
                handler.send_response_body(
                    423,
                    _json_err("Lock erforderlich", "LOCK_REQUIRED"),
                    content_type="application/json; charset=utf-8",
                )
                return
            rid_raw = data.get("report_id")
            _rid_cm = int(rid_raw) if rid_raw else None
            edb = self._bundle.evidence
            if _rid_cm is not None:
                _lock_ok = edb.validate_lock(_rid_cm, lock_id)
            else:
                _lock_ok = bool(edb._con.execute(
                    "SELECT 1 FROM editor_locks WHERE lock_id=?", (lock_id,)
                ).fetchone())
            if not _lock_ok:
                handler.send_response_body(
                    423,
                    _json_err("Lock abgelaufen oder ungueltig", "LOCK_INVALID"),
                    content_type="application/json; charset=utf-8",
                )
                return

        # is_chef aus coordinator.db lesen — nicht aus dem Request
        # Beleg: Sicherheitsprinzip, Projektgespraech 2026-05-06
        is_chef = self._get_is_chef()

        from db.evidence_db import EvidenceDbError
        try:
            found = self._bundle.evidence.resolve_comment(
                comment_id=int(comment_id),
                new_status=resolution,
                resolved_by=self._investigator,
                requesting_user=self._investigator,
                is_chef=is_chef,
            )
        except EvidenceDbError as exc:
            handler.send_response_body(
                403, _json_err(str(exc), "FORBIDDEN"),
                content_type="application/json; charset=utf-8",
            )
            return

        if not found:
            handler.send_response_body(
                404,
                _json_err(f"Kommentar {comment_id} nicht gefunden.", "NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )
            return

        logger.info(
            "Kommentar aufgeloest: comment_id=%s resolution=%s von '%s'",
            comment_id, resolution, self._investigator,
        )
        handler.send_response_body(
            200, _json_ok({"ok": True, "resolution": resolution}),
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _get_is_chef(self) -> bool:
        """
        Prueft ob der aktuelle Ermittler Chef-Ermittler-Rechte hat.
        Liest aus coordinator.db (can_approve_reports).
        Fallback: False wenn coordinator.db nicht erreichbar.
        Beleg: Bauplan B6 v0.5 §4.4.4, Projektgespraech 2026-05-06
        """
        try:
            inv = self._bundle.coordinator.get_investigator_by_username(
                self._investigator
            )
            if inv is None:
                return False
            return bool(getattr(inv, "can_approve_reports", False))
        except Exception as exc:
            logger.debug(
                "_get_is_chef fehlgeschlagen (Fallback: False): %s", exc
            )
            return False
