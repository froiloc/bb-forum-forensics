# =============================================================================
# report_render/__init__.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Serverunabhaengiges Renderer-Paket (Bauplan Build 397 §2). Nur Re-Exporte,
# keine Logik. Von forensic_api/export.py und (ab Build 402) vom Management-
# Server gemeinsam genutzt.
# Version: v0.7.399 · Build: 399 · 2026-07-13
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
from report_render.report_source import ReportSource, NoReportError, KNOWN_BLOCK_TYPES
from report_render.html_renderer import HtmlRenderer, CLASSIFICATION

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
    "ReportSource",
    "NoReportError",
    "KNOWN_BLOCK_TYPES",
    "HtmlRenderer",
    "CLASSIFICATION",
]
