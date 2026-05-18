# =============================================================================
# forensic_api/reports.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 2: Python-Webserver
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/reports — GET und POST.
#
#   GET /_forensic/reports:
#     Liefert alle Berichte als JSON-Liste (Metadaten, keine Bloecke).
#     Schema: { "reports": [ {id, report_type, sequence_nr, title,
#                              status, created_by, created_at}, ... ] }
#
#   POST /_forensic/reports:
#     Legt einen neuen Bericht an.
#     Body: { "report_type": "interim"|"final"|"addendum",
#              "title": "...",
#              "template_id": N (optional) }
#     Response: { "id": N, "title": "...", "report_type": "..." }
#     Kein Lock erforderlich — betrifft nur Berichts-Metadaten, keine Bloecke.
#     Jeder Ermittler darf Berichte anlegen.
#     Beleg: AP-E3, Projektgespraech 2026-04-19
#
# Datenbankzugriff:
#   evidence_<uid>.db (READ-WRITE) — reports-Tabelle
#
# Beleg: AP-E3, Projektgespraech 2026-04-19
# Version: v0.6.118 · Build: 118 · 2026-05-08
# =============================================================================

from __future__ import annotations
from typing import Optional

import json
from typing import TYPE_CHECKING

from core.logger import get_logger
from db.evidence_db import EvidenceDbError, VALID_REPORT_TYPES

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

_CT_JSON = "application/json; charset=utf-8"


def _json_err(msg: str, code: str = "ERROR") -> bytes:
    return json.dumps({"error": msg, "code": code}, ensure_ascii=False).encode("utf-8")


class ReportsEndpoint:
    """
    Endpunkt /_forensic/reports — Berichtsverwaltung (Metadaten).
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

    def handle_get(self, handler: "ForensicRequestHandler") -> None:
        """
        GET /_forensic/reports — Alle Berichte als JSON-Liste.
        Keine Bloecke, nur Metadaten (schnelle Uebersicht fuer Report-Auswahl-UI).
        """
        reports = self._bundle.evidence.get_reports()
        payload = {
            "reports": [
                {
                    "id":          r.id,
                    "report_type": r.report_type,
                    "sequence_nr": r.sequence_nr,
                    "title":       r.title,
                    "status":      r.status,
                    "created_by":  r.created_by,
                    "created_at":  r.created_at,
                }
                for r in reports
            ]
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(200, body, content_type=_CT_JSON)
        logger.debug(
            "/_forensic/reports (GET): %d Berichte ausgeliefert", len(reports)
        )

    def handle_post(
        self,
        handler: "ForensicRequestHandler",
        body_bytes: bytes,
    ) -> None:
        """
        POST /_forensic/reports — Neuen Bericht anlegen.
        Kein Lock erforderlich. Jeder Ermittler darf Berichte anlegen.
        Beleg: AP-E3, Projektgespraech 2026-04-19
        """
        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            handler.send_response_body(
                400, _json_err(f"Ungueltiger JSON-Body: {exc}"),
                content_type=_CT_JSON,
            )
            return

        report_type = str(data.get("report_type", "")).strip()
        title       = str(data.get("title", "")).strip()
        template_id_raw = data.get("template_id")

        if not report_type:
            handler.send_response_body(
                400, _json_err("'report_type' fehlt", "MISSING_FIELD"),
                content_type=_CT_JSON,
            )
            return

        if report_type not in VALID_REPORT_TYPES:
            handler.send_response_body(
                400,
                _json_err(
                    f"Ungueltiger report_type: '{report_type}'. "
                    f"Zulaessig: {sorted(VALID_REPORT_TYPES)}",
                    "INVALID_REPORT_TYPE",
                ),
                content_type=_CT_JSON,
            )
            return

        if not title:
            handler.send_response_body(
                400, _json_err("'title' fehlt oder leer", "MISSING_FIELD"),
                content_type=_CT_JSON,
            )
            return

        try:
            template_id = int(template_id_raw) if template_id_raw is not None else None
        except (TypeError, ValueError):
            template_id = None

        # Bug 3.1 Fix (Build 117): Ermittler-Username, nicht Beschuldigter.
        # Beleg: Projektgespraech 2026-05-07
        investigator = self._context.investigator_username

        # Bug 2.120 Fix Build 218: SSE-Client-ID fuer atomares Lock benoetigt.
        # Der Client sendet seine sse_client_id im Body mit.
        sse_client = str(data.get("sse_client", "")).strip()

        try:
            report_id = self._bundle.evidence.create_report(
                report_type=report_type,
                title=title,
                created_by=investigator,
            )
        except EvidenceDbError as exc:
            # Bekannte Fehler: doppelter Abschlussbericht, leerer Titel etc.
            handler.send_response_body(
                409,
                _json_err(str(exc), "CONFLICT"),
                content_type=_CT_JSON,
            )
            return
        except Exception as exc:
            logger.error("create_report fehlgeschlagen: %s", exc)
            handler.send_response_body(
                500, _json_err("Interner Datenbankfehler"),
                content_type=_CT_JSON,
            )
            return

        # Bug 2.120 Fix Build 218: Lock atomar mit Bericht-Erstellung erwerben.
        # Der Lock wird direkt fuer den neuen Bericht erworben, ohne separate
        # acquire_lock-Anfrage. Das verhindert Race Conditions und stellt sicher
        # dass der Ersteller immer den Lock haelt.
        # Beleg: Bugfix Build 218, Projektgespraech 2026-05-17
        lock_id: Optional[str] = None
        if sse_client:
            edb = self._bundle.evidence
            # Alten Lock desselben Ermittlers freigeben falls vorhanden
            # Alle bestehenden Locks des Ermittlers freigeben
            # (über lock_id-Suche, da wir den alten report_id nicht kennen)
            old_row = edb._con.execute(
                "SELECT report_id, lock_id FROM editor_locks WHERE locked_by=? LIMIT 1",
                (investigator,),
            ).fetchone()
            if old_row:
                edb.release_lock(
                    old_row["lock_id"], report_id=old_row["report_id"]
                )
                logger.info(
                    "create_report: alter Lock %s von '%s' freigegeben",
                    old_row["lock_id"], investigator,
                )
            lock_id = edb.acquire_lock(
                locked_by=investigator,
                sse_client=sse_client,
                report_id=report_id,
            )
            if lock_id is None:
                logger.warning(
                    "create_report: Lock fuer Bericht %d nicht erworben "
                    "(bereits belegt). Bericht trotzdem angelegt.",
                    report_id,
                )

        resp_data: dict = {"id": report_id, "title": title, "report_type": report_type}
        if lock_id:
            resp_data["lock_id"] = lock_id
        body = json.dumps(resp_data, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(201, body, content_type=_CT_JSON)
        logger.info(
            "Bericht angelegt: id=%d type='%s' title='%s' von '%s' lock_id=%s",
            report_id, report_type, title, investigator, lock_id or "keiner",
        )
