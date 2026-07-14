# =============================================================================
# forensic_api/export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichte & Exports
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/export?format=<html|docx|sqlite>[&report_id=<id>]
#
#   Serverseitiger Download der Ermittlungsakte. Dieser Endpunkt ist NUR NOCH
#   eine duenne Schale: er baut die Datenbank-Verbindungen und ruft das
#   serverunabhaengige Paket report_render/ (Bauplan Build 397 §2). Es wird
#   KEINE Renderlogik mehr hier gehalten — zwei Implementierungen desselben
#   Berichts waren die Ursache der "gruen aber tot"-Falle (Befund B1/B2).
#
#   HISTORIE (Warum dieser Umbau, GR6):
#     Der Vorgaengercode (v0.6.097) rief edb.get_paragraphs() auf — eine Methode,
#     die es seit dem Editor.js-Umbau nicht mehr gibt (Befund B1). Der Endpunkt
#     war live, aber jeder Aufruf lief in einen AttributeError. Seit dem
#     Produktivstart 01.07. konnte kein Ermittler seinen Bericht ausgeben.
#     Build 399 (Fundament + HTML) belebt den HTML-Export wieder.
#
#   Formate:
#     html   — LEBENDIG (Build 399): selbstenthaltendes HTML via HtmlRenderer.
#     docx   — 501 (Not Implemented) bis Build 402. Bewusst KEIN Rueckgriff auf
#     sqlite   den toten Altpfad — kein stiller Fehlbetrieb (GR1). Beleg: mc §9.1.
#     (pdf folgt Build 404, reportlab — mc §4.3.)
#
#   Berichtswahl (mc §4.1):
#     report_id optional. Fehlt er -> Bericht mit hoechster sequence_nr
#     (Gleichstand -> juengstes created_at). Siehe report_render/report_source.py.
#
#   Zugriffssteuerung: nur eigener Fall (context.user_id).
#   Migrationsvorbehalt: der Renderer LIEST NUR (kein Schreibpfad in evidence_<uid>.db).
#
# Version: v0.7.399 · Build: 399 · 2026-07-13
# =============================================================================

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Optional

from core.logger import get_logger

from report_render.report_source import ReportSource, NoReportError
from report_render.html_renderer import HtmlRenderer

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

#: In Build 399 aktiv ausgelieferte Formate.
_LIVE_FORMATS = ("html",)
#: Bekannte, aber noch nicht (wieder) implementierte Formate -> 501.
_PENDING_FORMATS = ("docx", "sqlite")


class ExportEndpoint:
    """GET /_forensic/export?format=html|docx|sqlite[&report_id=<id>]

    Duenne Schale um report_render/. Beleg: Bauplan Build 397 §2/§5, Build 399.
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
    def handle_get(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        # Format: optional, Default 'html' (mc). params-Werte sind Listen.
        fmt = (params.get("format", ["html"]) or ["html"])[0] or "html"

        if fmt in _PENDING_FORMATS:
            # Kein stiller Rueckgriff auf den toten Altpfad (GR1).
            self._send_json(
                handler, 501,
                {"error": f"Format '{fmt}' ist in Build 399 noch nicht verfuegbar "
                          f"(HTML lebt; DOCX/SQLite folgen in Build 402, PDF in 404).",
                 "available": list(_LIVE_FORMATS)},
            )
            return

        if fmt not in _LIVE_FORMATS:
            self._send_json(
                handler, 400,
                {"error": "format muss html, docx oder sqlite sein",
                 "available": list(_LIVE_FORMATS)},
            )
            return

        # report_id: optional, ganze Zahl.
        report_id: Optional[int] = None
        raw_rid = (params.get("report_id", [None]) or [None])[0]
        if raw_rid not in (None, ""):
            try:
                report_id = int(raw_rid)
            except (ValueError, TypeError):
                self._send_json(handler, 400, {"error": "report_id muss eine ganze Zahl sein"})
                return

        if fmt == "html":
            self._export_html(handler, report_id)

    # ------------------------------------------------------------------
    def _build_source(self) -> ReportSource:
        """Baut die serverunabhaengige ReportSource aus dem DatabaseBundle.

        Der Zeitstempel wird HIER (im Server) gesetzt und in das reine Modul
        hineingereicht — das Modul selbst ruft nie now() (Determinismus/Test).
        """
        uid = self._context.user_id
        username = self._context.username or f"uid_{uid}"
        return ReportSource(
            evidence=self._bundle.evidence,
            templates=getattr(self._bundle, "templates", None),
            assets=getattr(self._bundle, "assets", None),
            forensic_con=self._bundle.connection,   # traegt ATTACH-Alias 'fdb'/'tdb'
            uid=uid,
            username=username,
            generated_at=int(time.time()),
        )

    # ------------------------------------------------------------------
    def _export_html(self, handler: "ForensicRequestHandler", report_id: Optional[int]) -> None:
        try:
            doc = self._build_source().build(report_id)
        except NoReportError as exc:
            self._send_json(handler, 404, {"error": str(exc)})
            return

        body = HtmlRenderer().render(doc)
        filename = f"bericht_{doc.uid}_{time.strftime('%Y%m%d')}.html"
        handler.send_response_body(
            200, body,
            content_type="text/html; charset=utf-8",
            extra_headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(body)),
            },
        )
        logger.info(
            "Export HTML: uid=%d, report_id=%s, %d Bloecke, %d Warnungen, %d Bytes",
            doc.uid, doc.report_id, len(doc.blocks), len(doc.warnings), len(body),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _send_json(handler: "ForensicRequestHandler", code: int, payload: dict) -> None:
        handler.send_response_body(
            code,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )
