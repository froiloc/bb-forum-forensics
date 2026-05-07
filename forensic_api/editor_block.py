# =============================================================================
# forensic_api/editor_block.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt POST /_forensic/editor/block — Block speichern oder loeschen.
#
#   action=save:
#     Speichert oder aktualisiert einen Editor.js-Block in report_blocks.
#     Bei neuem Block: Legt auch Eintrag in report_block_order an
#     wenn sort_index im Body mitgegeben wird.
#     Bei Update: Aktualisiert nur block_data und updated_at.
#     Owner ist unveraenderlich.
#     Body: { "action": "save",
#              "block_id": "uuid",
#              "report_id": N,
#              "block_type": "paragraph"|"header"|...|"evidenceBlock",
#              "block_data": { ...Editor.js-Datenfeld... },
#              "owner": "h012345",
#              "sort_index": "a0" (optional, nur bei neuem Block),
#              "lock_id": "uuid" (oder X-Forensic-Lock-Id-Header) }
#     Response: { "block_id": "uuid", "status": "saved" }
#
#   action=delete:
#     Loescht einen Block. Nur der Owner darf loeschen.
#     Kaskadierendes Loeschen: block_evidence_user + report_block_order.
#     Body: { "action": "delete",
#              "block_id": "uuid",
#              "lock_id": "uuid" }
#     Response: { "block_id": "uuid", "status": "deleted" }
#              oder HTTP 403 wenn nicht Owner.
#
#   Lock erforderlich fuer beide Aktionen (§8.6 Bauplan B4).
#   Beleg: AP-E3, Projektgespraech 2026-04-19
#
# Datenbankzugriff:
#   evidence_<uid>.db (READ-WRITE) — report_blocks, report_block_order,
#                                    block_evidence_user, editor_locks
#
# Beleg: AP-E3, Projektgespraech 2026-04-19
# Version: v0.6.115 · Build: 115 · 2026-05-07
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.logger import get_logger
from db.evidence_db import EvidenceDbError
from forensic_api._lock_guard import require_lock

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

_CT_JSON = "application/json; charset=utf-8"


def _json_err(msg: str, code: str = "ERROR") -> bytes:
    return json.dumps({"error": msg, "code": code}, ensure_ascii=False).encode("utf-8")


class EditorBlockEndpoint:
    """
    Endpunkt POST /_forensic/editor/block — Block speichern oder loeschen.
    Lock erforderlich fuer alle Aktionen.
    Beleg: AP-E3, Projektgespraech 2026-04-19
    """

    def __init__(
        self,
        bundle: "DatabaseBundle",
        context: "ResolvedContext",
        config: "ConfigLoader",
    ) -> None:
        self._bundle  = bundle
        self._context = context

    def handle(
        self,
        handler: "ForensicRequestHandler",
        body_bytes: bytes,
    ) -> None:
        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            handler.send_response_body(
                400, _json_err(f"Ungueltiger JSON-Body: {exc}"),
                content_type=_CT_JSON,
            )
            return

        # Lock pruefen — alle Aktionen erfordern Lock
        if require_lock(handler, data, self._bundle.evidence) is None:
            return

        action = str(data.get("action", "")).strip()

        if action == "save":
            self._action_save(handler, data)
        elif action == "delete":
            self._action_delete(handler, data)
        else:
            handler.send_response_body(
                400,
                _json_err(
                    f"Unbekannte Aktion: '{action}'. Zulaessig: save, delete",
                    "UNKNOWN_ACTION",
                ),
                content_type=_CT_JSON,
            )

    def _action_save(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> None:
        """
        Speichert oder aktualisiert einen Editor.js-Block.
        Bei Update: nur block_data geaendert, owner bleibt unveraenderlich.
        """
        block_id   = str(data.get("block_id", "")).strip()
        block_type = str(data.get("block_type", "")).strip()
        block_data = data.get("block_data")
        owner      = str(data.get("owner", "")).strip()
        sort_index = data.get("sort_index")

        report_id_raw = data.get("report_id")

        # Pflichtfelder pruefen
        for field, value in [
            ("block_id",   block_id),
            ("block_type", block_type),
            ("owner",      owner),
        ]:
            if not value:
                handler.send_response_body(
                    400, _json_err(f"'{field}' fehlt oder leer", "MISSING_FIELD"),
                    content_type=_CT_JSON,
                )
                return

        if block_data is None or not isinstance(block_data, dict):
            handler.send_response_body(
                400,
                _json_err("'block_data' fehlt oder ist kein Objekt", "MISSING_FIELD"),
                content_type=_CT_JSON,
            )
            return

        # Normalisierung: leere Paragraph-Bloecke behalten ein minimales
        # data-Objekt damit Editor.js sie nicht als 'invalid' verwirft.
        # Beleg: Bugfix Build 050, Projektgespraech 2026-04-21
        if block_type == "paragraph" and not block_data.get("text"):
            block_data = {"text": ""}

        try:
            report_id = int(report_id_raw) if report_id_raw is not None else None
        except (TypeError, ValueError):
            report_id = None

        if report_id is None:
            # Pruefe ob Block bereits existiert (Update-Fall benoetigt keine report_id)
            existing = self._bundle.evidence.get_block(block_id)
            if existing is None:
                handler.send_response_body(
                    400,
                    _json_err(
                        "'report_id' erforderlich fuer neuen Block", "MISSING_FIELD"
                    ),
                    content_type=_CT_JSON,
                )
                return
            report_id = existing.report_id

        sort_idx = str(sort_index).strip() if sort_index is not None else None

        try:
            # Build 114: owner= → author= (Signatur evidence_db.save_block)
            # Beleg: Projektgespraech 2026-05-07
            self._bundle.evidence.save_block(
                block_id=block_id,
                report_id=report_id,
                author=owner,
                block_type=block_type,
                block_data=block_data,
                sort_index=sort_idx,
            )
        except EvidenceDbError as exc:
            handler.send_response_body(
                400, _json_err(str(exc)), content_type=_CT_JSON
            )
            return
        except Exception as exc:
            logger.error("save_block fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500, _json_err("Interner Datenbankfehler"), content_type=_CT_JSON
            )
            return

        body = json.dumps(
            {"block_id": block_id, "status": "saved"}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(200, body, content_type=_CT_JSON)
        logger.info(
            "Block gespeichert: block_id=%s type=%s owner=%s",
            block_id, block_type, owner,
        )

    def _action_delete(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> None:
        """
        Loescht einen Block. Nur der Owner darf loeschen.
        HTTP 403 wenn nicht Owner, HTTP 404 wenn nicht gefunden.
        """
        block_id = str(data.get("block_id", "")).strip()
        if not block_id:
            handler.send_response_body(
                400, _json_err("'block_id' fehlt", "MISSING_FIELD"),
                content_type=_CT_JSON,
            )
            return

        # Eigentuemerschaft pruefen bevor delete_block() aufgerufen wird
        block = self._bundle.evidence.get_block(block_id)
        if block is None:
            handler.send_response_body(
                404,
                _json_err(f"Block '{block_id}' nicht gefunden", "NOT_FOUND"),
                content_type=_CT_JSON,
            )
            return

        requesting_owner = self._context.username or ""
        if block.owner != requesting_owner:
            handler.send_response_body(
                403,
                _json_err(
                    "Nur der Ersteller des Blocks darf ihn loeschen",
                    "FORBIDDEN",
                ),
                content_type=_CT_JSON,
            )
            return

        try:
            deleted = self._bundle.evidence.delete_block(block_id, requesting_owner)
        except Exception as exc:
            logger.error("delete_block fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500, _json_err("Interner Datenbankfehler"), content_type=_CT_JSON
            )
            return

        if not deleted:
            # Sollte nach den obigen Pruefungen nicht eintreten
            handler.send_response_body(
                404,
                _json_err(f"Block '{block_id}' nicht gefunden", "NOT_FOUND"),
                content_type=_CT_JSON,
            )
            return

        body = json.dumps(
            {"block_id": block_id, "status": "deleted"}, ensure_ascii=False
        ).encode("utf-8")
        handler.send_response_body(200, body, content_type=_CT_JSON)
        logger.info("Block geloescht: block_id=%s", block_id)
