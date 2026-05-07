# =============================================================================
# forensic_api/editor_order.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt POST /_forensic/editor/order — Blockreihenfolge aktualisieren.
#
#   Empfaengt die neue Blockreihenfolge nach Drag-and-Drop und aktualisiert
#   report_block_order via String-based Fractional Indexing.
#
#   Body: { "report_id": N,
#            "order": [
#              {"block_id": "uuid1", "sort_index": "a0"},
#              {"block_id": "uuid2", "sort_index": "000000"},
#              ...
#            ],
#            "lock_id": "uuid" (oder X-Forensic-Lock-Id-Header) }
#   Response: { "updated": N }
#
#   Lock erforderlich (§8.6 Bauplan B4).
#   Beleg: AP-E3, Projektgespraech 2026-04-19
#
# Datenbankzugriff:
#   evidence_<uid>.db (READ-WRITE) — report_block_order, editor_locks
#
# Fixes:
#   Build 117 (Bug 2.16/2.20): Signatur-Mismatch set_block_order:
#     editor_order.py uebergab report_id, ordered_block_ids, new_sort_indices
#     als separate Parameter — set_block_order erwartet aber (order: list[dict],
#     modified_by: str). Der Mismatch fuehrte zu 500 Internal Server Error
#     bei jedem Auto-Save. Beleg: Projektgespraech 2026-05-08
#   Build 117 (Bug 3.1): context.username ist der Beschuldigte, nicht der
#     Ermittler. Fix: context.investigator_username verwenden.
#     Beleg: Projektgespraech 2026-05-07
#
# Beleg: AP-E3, Projektgespraech 2026-04-19
# Version: v0.6.118 · Build: 118 · 2026-05-08
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


class EditorOrderEndpoint:
    """
    Endpunkt POST /_forensic/editor/order — Blockreihenfolge aktualisieren.
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

        report_id_raw = data.get("report_id")
        order_raw     = data.get("order")

        try:
            report_id = int(report_id_raw) if report_id_raw is not None else None
        except (TypeError, ValueError):
            report_id = None

        if report_id is None:
            handler.send_response_body(
                400, _json_err("'report_id' fehlt oder ungueltig", "MISSING_FIELD"),
                content_type=_CT_JSON,
            )
            return

        if not isinstance(order_raw, list) or len(order_raw) == 0:
            handler.send_response_body(
                400,
                _json_err("'order' fehlt, leer oder kein Array", "MISSING_FIELD"),
                content_type=_CT_JSON,
            )
            return

        # order-Eintraege validieren und in das von set_block_order erwartete
        # Format normalisieren: list[{block_id: str, sort_index: str}].
        # Beleg: Bugfix Build 117, Projektgespraech 2026-05-08
        order_list: list[dict] = []
        for i, entry in enumerate(order_raw):
            if not isinstance(entry, dict):
                handler.send_response_body(
                    400,
                    _json_err(
                        f"order[{i}] ist kein Objekt", "INVALID_ORDER_ENTRY"
                    ),
                    content_type=_CT_JSON,
                )
                return
            bid = str(entry.get("block_id", "")).strip()
            idx = str(entry.get("sort_index", "")).strip()
            if not bid or not idx:
                handler.send_response_body(
                    400,
                    _json_err(
                        f"order[{i}]: 'block_id' und 'sort_index' sind Pflichtfelder",
                        "INVALID_ORDER_ENTRY",
                    ),
                    content_type=_CT_JSON,
                )
                return
            order_list.append({"block_id": bid, "sort_index": idx})

        # Bug 3.1 Fix (Build 117): Ermittler-Username, nicht Beschuldigter.
        # Beleg: Projektgespraech 2026-05-07
        modified_by = self._context.investigator_username

        try:
            # Bug-Fix Build 117: set_block_order(order: list[dict], modified_by: str).
            # Frueherer Aufruf mit separaten report_id/ordered_block_ids/new_sort_indices
            # stimmte nicht mit DB-Signatur ueberein → 500-Fehler.
            # Beleg: Projektgespraech 2026-05-08
            updated = self._bundle.evidence.set_block_order(
                order=order_list,
                modified_by=modified_by,
            )
        except EvidenceDbError as exc:
            handler.send_response_body(
                400, _json_err(str(exc)), content_type=_CT_JSON
            )
            return
        except Exception as exc:
            logger.error("set_block_order fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500, _json_err("Interner Datenbankfehler"), content_type=_CT_JSON
            )
            return

        body = json.dumps({"updated": updated}, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(200, body, content_type=_CT_JSON)
        logger.info(
            "Blockreihenfolge aktualisiert: report_id=%d, %d Eintraege von '%s'",
            report_id, updated, modified_by,
        )
