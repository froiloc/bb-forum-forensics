# =============================================================================
# report_render/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Serverunabhaengiges Renderer-Paket (Bauplan Build 397 §2). Nur Re-Exporte,
# keine Logik. Von forensic_api/export.py und (ab Build 402) vom Management-
# Server gemeinsam genutzt.
# Version: v0.7.403 · Build: 403 · 2026-07-14 (AutoQueryResolver-Kern ergaenzt)
# =============================================================================

from report_render.report_document import (
    ReportDocument,
    RenderedBlock,
    DocWarning,
    VALID_WARNING_KINDS,
    WARN_UNRESOLVED_PLACEHOLDER,
    WARN_UNKNOWN_PLACEHOLDER,
    WARN_UNORDERED_BLOCK,
    WARN_UNKNOWN_BLOCK_TYPE,
    WARN_MISSING_IMAGE,
)
from report_render.placeholder_resolver import PlaceholderResolver
from report_render.auto_query import AutoQueryResolver, AutoResult
from report_render.report_source import ReportSource, NoReportError, KNOWN_BLOCK_TYPES
from report_render.html_renderer import HtmlRenderer, CLASSIFICATION
from report_render.docx_renderer import DocxRenderer, DocxRendererUnavailable
from report_render.sqlite_renderer import SqliteRenderer

__all__ = [
    "ReportDocument",
    "RenderedBlock",
    "DocWarning",
    "VALID_WARNING_KINDS",
    "WARN_UNRESOLVED_PLACEHOLDER",
    "WARN_UNKNOWN_PLACEHOLDER",
    "WARN_UNORDERED_BLOCK",
    "WARN_UNKNOWN_BLOCK_TYPE",
    "WARN_MISSING_IMAGE",
    "PlaceholderResolver",
    "AutoQueryResolver",
    "AutoResult",
    "ReportSource",
    "NoReportError",
    "KNOWN_BLOCK_TYPES",
    "HtmlRenderer",
    "DocxRenderer",
    "DocxRendererUnavailable",
    "SqliteRenderer",
    "CLASSIFICATION",
]
