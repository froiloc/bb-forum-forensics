# =============================================================================
# forensic_api/editor_evidence.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/editor/evidence — Evidence-Verknuepfungen verwalten.
#
#   POST /_forensic/editor/evidence (action=add):
#     Verknuepft eine Annotation mit einem Block (idempotent).
#     Body: { "action": "add",
#              "block_id": "uuid",
#              "evidence_id": N,
#              "lock_id": "uuid" }
#     Response: { "block_id": "uuid", "evidence_id": N, "status": "linked" }
#
#   POST /_forensic/editor/evidence (action=remove):
#     Entfernt eine Verknuepfung.
#     Body: { "action": "remove",
#              "block_id": "uuid",
#              "evidence_id": N,
#              "lock_id": "uuid" }
#     Response: { "block_id": "uuid", "evidence_id": N, "status": "unlinked" }
#              oder HTTP 404 wenn Verknuepfung nicht gefunden.
#
#   Lock erforderlich fuer beide Aktionen (§8.6 Bauplan B4).
#
#   Nach erfolgreichem add/remove enthaelt die Response zusaetzlich
#   "affected_block_ids" — die Liste aller Bloecke, die diese evidence_id
#   referenzieren. Wird von AP-E4 (editor.js) verwendet um bei Evidence-
#   Aenderungen die betroffenen Bloecke neu zu rendern.
#   Beleg: AP-E3, Projektgespraech 2026-04-19
#
# Datenbankzugriff:
#   evidence_<uid>.db (READ-WRITE) — block_evidence_user, editor_locks
#
# Beleg: AP-E3, Projektgespraech 2026-04-19
# Version: v0.6.115 · Build: 115 · 2026-05-07
# =============================================================================

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from core.logger import get_logger
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


def _parse_ids(data: dict) -> "tuple[str, int] | tuple[None, None]":
    """
    Extrahiert und validiert block_id (str) und evidence_id (int) aus dem Body.
    Gibt (None, None) bei Fehlern zurueck.
    """
    block_id = str(data.get("block_id", "")).strip()
    evidence_id_raw = data.get("evidence_id")
    if not block_id:
        return None, None
    try:
        evidence_id = int(evidence_id_raw)
        if evidence_id <= 0:
            return None, None
    except (TypeError, ValueError):
        return None, None
    return block_id, evidence_id


class EditorEvidenceEndpoint:
    """
    Endpunkt POST /_forensic/editor/evidence — Evidence-Verknuepfungen.
    Lock erforderlich. Beleg: AP-E3, Projektgespraech 2026-04-19
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

        if require_lock(handler, data, self._bundle.evidence) is None:
            return

        action = str(data.get("action", "")).strip()

        if action == "add":
            self._action_add(handler, data)
        elif action == "remove":
            self._action_remove(handler, data)
        else:
            handler.send_response_body(
                400,
                _json_err(
                    f"Unbekannte Aktion: '{action}'. Zulaessig: add, remove",
                    "UNKNOWN_ACTION",
                ),
                content_type=_CT_JSON,
            )

    def _action_add(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> None:
        """Verknuepft eine Annotation mit einem Block (idempotent)."""
        block_id, evidence_id = _parse_ids(data)
        if block_id is None:
            handler.send_response_body(
                400,
                _json_err(
                    "'block_id' und 'evidence_id' (>0) sind Pflichtfelder",
                    "MISSING_FIELD",
                ),
                content_type=_CT_JSON,
            )
            return

        investigator_id = getattr(self._context, "investigator_id", 0) or 0

        # Build 115: add_block_evidence → add_anchor (Signatur evidence_db)
        # anchor_text als Leerstring – der EvidenceBlock speichert selbst.
        # Beleg: Projektgespraech 2026-05-07
        try:
            self._bundle.evidence.add_anchor(
                block_id=block_id,
                annotation_id=evidence_id,
                anchor_text="",
            )
        except Exception as exc:
            logger.error("add_anchor fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500, _json_err("Interner Datenbankfehler"), content_type=_CT_JSON
            )
            return

        # Alle Bloecke zurueckgeben, die diese evidence_id referenzieren.
        # AP-E4 verwendet diese Liste um betroffene Bloecke neu zu rendern.
        affected = [
            r.block_id
            for r in self._bundle.evidence.get_blocks_for_evidence(evidence_id)
        ]

        body = json.dumps(
            {
                "block_id":          block_id,
                "evidence_id":       evidence_id,
                "status":            "linked",
                "affected_block_ids": affected,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(200, body, content_type=_CT_JSON)
        logger.info(
            "Evidence verknuepft: block_id=%s evidence_id=%d",
            block_id, evidence_id,
        )

    def _action_remove(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> None:
        """Entfernt eine Evidence-Verknuepfung."""
        block_id, evidence_id = _parse_ids(data)
        if block_id is None:
            handler.send_response_body(
                400,
                _json_err(
                    "'block_id' und 'evidence_id' (>0) sind Pflichtfelder",
                    "MISSING_FIELD",
                ),
                content_type=_CT_JSON,
            )
            return

        # Alle betroffenen Bloecke BEVOR dem Loeschen ermitteln
        affected = [
            r.block_id
            for r in self._bundle.evidence.get_blocks_for_evidence(evidence_id)
        ]

        try:
            removed = self._bundle.evidence.remove_block_evidence(
                block_id=block_id,
                evidence_id=evidence_id,
            )
        except Exception as exc:
            logger.error("remove_block_evidence fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500, _json_err("Interner Datenbankfehler"), content_type=_CT_JSON
            )
            return

        if not removed:
            handler.send_response_body(
                404,
                _json_err(
                    f"Verknuepfung block_id='{block_id}' evidence_id={evidence_id} "
                    "nicht gefunden",
                    "NOT_FOUND",
                ),
                content_type=_CT_JSON,
            )
            return

        body = json.dumps(
            {
                "block_id":          block_id,
                "evidence_id":       evidence_id,
                "status":            "unlinked",
                "affected_block_ids": affected,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        handler.send_response_body(200, body, content_type=_CT_JSON)
        logger.info(
            "Evidence-Verknuepfung entfernt: block_id=%s evidence_id=%d",
            block_id, evidence_id,
        )
