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
# Fixes:
#   Build 117 (Bug 3.4): block_data als dict wurde unseralisiert an save_block()
#     uebergeben. save_block() erwartet JSON-String. Fix: json.dumps() vor Aufruf.
#     Beleg: Projektgespraech 2026-05-07
#   Build 117 (Bug 3.4): sort_index wurde als String (z.B. "a0") uebergeben,
#     save_block() erwartet Optional[int]. Fix: sort_index als String beibehalten
#     und None liefern wenn nicht ganzzahlig konvertierbar.
#     Achtung: report.py konvertiert sort_index mit int() — hier gleiche Behandlung.
#     Beleg: Projektgespraech 2026-05-07
#   Build 117 (Bug 3.1): context.username ist der Beschuldigte, nicht der Ermittler.
#     Der Eigentuemer eines Blocks muss der Ermittler (Systembenutzer) sein.
#     Fix: context.investigator_username verwenden.
#     Beleg: Projektgespraech 2026-05-07
#   Build 135 (Bug 3.6): update_block als Alias fuer save hinzugefuegt.
#     _onPlaceholderFieldSave in report_editor.js sendete 'update_block',
#     das Backend kannte nur 'save' und 'delete'. Fix: update_block wird wie
#     save behandelt. placeholder_values_json wird jetzt aus dem Body gelesen
#     und an save_block() weitergegeben. Bei update_block sind block_type,
#     block_data und owner optional — fehlende Werte werden aus dem
#     bestehenden Block in der DB ergaenzt.
#     Beleg: Bugfix Build 135, Projektgespraech 2026-05-09
# Version: v0.6.143 · Build: 143 · 2026-05-10
# =============================================================================

from __future__ import annotations

import json
import os
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
        elif action == "update_block":
            # Bug 3.6 Fix Build 135: update_block ist ein Alias fuer save.
            # Der Frontend-Code (_onPlaceholderFieldSave) sendete 'update_block'
            # mit placeholder_values_json — das Backend kannte diese Aktion nicht.
            # Fix: 'update_block' wird wie 'save' behandelt.
            # Beleg: Bugfix Build 135, Projektgespraech 2026-05-09
            self._action_save(handler, data)
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
        placeholder_values_json_raw = data.get("placeholder_values_json")
        placeholder_values_json: str | None = None
        if placeholder_values_json_raw is not None:
            if isinstance(placeholder_values_json_raw, str):
                placeholder_values_json = placeholder_values_json_raw
            else:
                placeholder_values_json = json.dumps(
                    placeholder_values_json_raw, ensure_ascii=False
                )

        report_id_raw = data.get("report_id")

        # Bug 3.7 Diagnose Build 139: Erweitertes Logging fuer Platzhalter-Save.
        # Zeigt genau welche Felder ankommen und was fehlt.
        # Beleg: Bugfix Build 139, Projektgespraech 2026-05-09
        logger.debug(
            "_action_save eingehend: block_id=%r block_type=%r "
            "block_data_type=%s owner=%r report_id=%r "
            "placeholder_values_json_len=%s",
            block_id, block_type,
            type(block_data).__name__,
            owner, report_id_raw,
            len(placeholder_values_json) if placeholder_values_json else 'None',
        )

        # Pflichtfeld block_id immer pruefen
        if not block_id:
            handler.send_response_body(
                400, _json_err("'block_id' fehlt oder leer", "MISSING_FIELD"),
                content_type=_CT_JSON,
            )
            return

        existing_for_fill: object = None
        if not block_type or block_data is None or not owner:
            logger.debug(
                "_action_save: optionale Felder fehlen — lade Block aus DB: "
                "block_type=%r block_data_none=%s owner=%r",
                block_type, block_data is None, owner,
            )
            try:
                existing_for_fill = self._bundle.evidence.get_block(block_id)
            except Exception as exc:
                logger.error("_action_save: get_block fehlgeschlagen block_id=%s: %s",
                             block_id, exc, exc_info=True)
                handler.send_response_body(
                    500, _json_err("Interner Datenbankfehler beim Lesen des Blocks", "ERROR"),
                    content_type=_CT_JSON,
                )
                return
            logger.debug(
                "_action_save: DB-Ergebnis fuer block_id=%r: gefunden=%s "
                "db_block_type=%r db_owner=%r",
                block_id,
                existing_for_fill is not None,
                getattr(existing_for_fill, 'block_type', None),
                getattr(existing_for_fill, 'author', None),
            )
            if existing_for_fill is None and (not block_type or block_data is None):
                handler.send_response_body(
                    400,
                    _json_err(
                        "'block_type' und 'block_data' erforderlich fuer neuen Block",
                        "MISSING_FIELD",
                    ),
                    content_type=_CT_JSON,
                )
                return
            if not block_type and existing_for_fill:
                block_type = existing_for_fill.block_type or ''
            if block_data is None and existing_for_fill:
                try:
                    block_data = json.loads(existing_for_fill.block_data or '{}')
                except (json.JSONDecodeError, TypeError):
                    block_data = {}
            if not owner and existing_for_fill:
                owner = getattr(existing_for_fill, 'author', '') or ''

        # block_type und owner als Pflichtfelder pruefen (nach Auffuellung)
        for field, value in [
            ("block_type", block_type),
            ("owner",      owner),
        ]:
            if not value:
                logger.warning(
                    "_action_save: Pflichtfeld '%s' fehlt nach DB-Auffuellung "
                    "fuer block_id=%r", field, block_id,
                )
                handler.send_response_body(
                    400, _json_err(f"'{field}' fehlt oder leer", "MISSING_FIELD"),
                    content_type=_CT_JSON,
                )
                return

        if not isinstance(block_data, dict):
            logger.warning(
                "_action_save: block_data ist kein dict fuer block_id=%r, "
                "Typ=%s Wert=%r",
                block_id, type(block_data).__name__, str(block_data)[:100],
            )
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

        # Bug 3.4 Fix (Build 117): block_data muss als JSON-String an
        # save_block() uebergeben werden. Der HTTP-Body liefert ein dict
        # (nach json.loads), save_block() erwartet aber str.
        # Beleg: Projektgespraech 2026-05-07
        block_data_json: str = json.dumps(block_data, ensure_ascii=False)

        try:
            report_id = int(report_id_raw) if report_id_raw is not None else None
        except (TypeError, ValueError):
            report_id = None

        if report_id is None:
            # Pruefe ob Block bereits existiert (Update-Fall benoetigt keine report_id)
            if existing_for_fill is not None:
                report_id = existing_for_fill.report_id
            else:
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

        # Bug 3.4 Fix (Build 117): sort_index als optionaler int.
        # Der Client uebergibt Fractional-Index-Strings (z.B. "a0") —
        # save_block() erwartet Optional[int]. Nicht-numerische Werte
        # werden ignoriert (None). Beleg: Projektgespraech 2026-05-07
        sort_idx: int | None = None
        if sort_index is not None:
            try:
                sort_idx = int(sort_index)
            except (TypeError, ValueError):
                sort_idx = None

        # Bug 3.1 Fix (Build 117): context.username ist der Beschuldigte,
        # nicht der Ermittler. Der Block-Eigentuemer muss der Systembenutzer
        # (Ermittler) sein. context.investigator_username liefert den
        # SAMAccountName des angemeldeten Ermittlers.
        # Beleg: Projektgespraech 2026-05-07
        ermittler = self._context.investigator_username

        try:
            # Build 114: owner= → author= (Signatur evidence_db.save_block)
            # Bug 3.6 Fix Build 135: placeholder_values_json mitsenden.
            # Beleg: Projektgespraech 2026-05-07, 2026-05-09
            self._bundle.evidence.save_block(
                block_id=block_id,
                report_id=report_id,
                author=ermittler,
                block_type=block_type,
                block_data=block_data_json,
                sort_index=sort_idx,
                placeholder_values_json=placeholder_values_json,
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

        Bug 2.52 Fix Build 139: block.owner → block.author (Umbenennung Build 114).
        Ausserdem: get_block() in try/except gefasst damit AttributeError nicht
        als leerer 500 ankommt.
        Beleg: Bugfix Build 139, Projektgespraech 2026-05-09
        """
        block_id = str(data.get("block_id", "")).strip()
        if not block_id:
            handler.send_response_body(
                400, _json_err("'block_id' fehlt", "MISSING_FIELD"),
                content_type=_CT_JSON,
            )
            return

        # Eigentuemerschaft pruefen bevor delete_block() aufgerufen wird
        try:
            block = self._bundle.evidence.get_block(block_id)
        except Exception as exc:
            logger.error("_action_delete: get_block fehlgeschlagen block_id=%s: %s",
                         block_id, exc, exc_info=True)
            handler.send_response_body(
                500, _json_err("Interner Datenbankfehler beim Lesen des Blocks", "ERROR"),
                content_type=_CT_JSON,
            )
            return

        if block is None:
            handler.send_response_body(
                404,
                _json_err(f"Block '{block_id}' nicht gefunden", "NOT_FOUND"),
                content_type=_CT_JSON,
            )
            return

        # Bug 2.52 Fix Build 139: Attribut heisst 'author', nicht 'owner'.
        # Umbenennung erfolgte in Build 114 (save_block owner→author).
        # block.owner loest AttributeError aus → unkontrollierter 500.
        # Beleg: Bugfix Build 139, Projektgespraech 2026-05-09
        requesting_owner = self._context.investigator_username
        block_author = getattr(block, 'author', None) or getattr(block, 'owner', None) or ''
        logger.debug(
            "_action_delete: block_id=%s block_author=%r requesting_owner=%r",
            block_id, block_author, requesting_owner,
        )
        if block_author and block_author != requesting_owner:
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
