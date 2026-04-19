# =============================================================================
# editor/html_renderer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Bericht-Export (AP-E5)
# =============================================================================
# Zweck:
#   Serverseitige HTML-Generierung aus Editor.js-JSON-Daten.
#   Erweitert pyEditorJS (v1.0.0b0) um alle im Projekt verwendeten Block-Typen.
#
#   Unterstuetzte Block-Typen:
#     Nativ (pyEditorJS):    header, paragraph, list, delimiter, image
#     Neu (diese Datei):     table, quote, nestedlist, marker, evidence,
#                            unknown (Fallback fuer unbekannte Typen)
#
#   EvidenceBlock:
#     Rendert eine Beweismittelgruppe als forensische Karte mit Quellenangaben.
#     Benoetigt optional eine EvidenceDb-Instanz fuer Annotationstext.
#     Ohne DB: rendert nur evidence_id-Referenzen.
#
#   Verwendung (Baustelle 6 — Bericht-Export):
#     from editor.html_renderer import EditorHtmlRenderer
#     renderer = EditorHtmlRenderer(evidence_db=edb)
#     html = renderer.render(report_blocks)
#     # report_blocks: Liste von ReportBlockRecord-Objekten aus evidence_db
#
#   Kein Produktionseinsatz in AP-E4 (dort rendert der Browser direkt).
#   Vorbereitet fuer Baustelle 6 (serverseitiger PDF/HTML-Export).
#
# Abhaengigkeiten:
#   pyeditorjs (pip install pyeditorjs) — stdlib + optional bleach
#   Alle anderen: Python-Stdlib
#
# Beleg: AP-E5, Projektgespraech 2026-04-19
# Version: v0.6.045 · Build: 045 · 2026-04-19
# =============================================================================

from __future__ import annotations

import html
import json
import logging
from typing import Optional, TYPE_CHECKING

# Defensiver Import: pyeditorjs ist eine optionale Abhaengigkeit (AP-E5).
# Ohne pyeditorjs ist der Webserver lauffaehig — nur der HTML-Export
# (Baustelle 6) funktioniert nicht. Fehlende Installation wird beim
# Import dieses Moduls klar gemeldet, nicht erst beim ersten Aufruf.
# Beleg: AP-E5 Bugfix, Projektgespraech 2026-04-19
try:
    from pyeditorjs.blocks import EditorJsBlock
    from pyeditorjs.parser import EditorJsParser
    _PYEDITORJS_AVAILABLE = True
except ImportError as _pyeditorjs_import_error:
    _PYEDITORJS_AVAILABLE = False
    _pyeditorjs_import_error_msg = (
        f"pyeditorjs nicht installiert: {_pyeditorjs_import_error}. "
        "Bitte 'pip install pyeditorjs' ausfuehren "
        "oder install.py --target=prod verwenden."
    )
    # Stub-Basisklasse damit Subklassen definierbar bleiben
    class EditorJsBlock:  # type: ignore[no-redef]
        def __init__(self, _data=None): self._data = _data or {}
        @property
        def data(self): return self._data.get('data', {})
        @property
        def type(self): return self._data.get('type', '')
        def html(self, sanitize=False): return ''
    class EditorJsParser:  # type: ignore[no-redef]
        def __init__(self, content): self._content = content
        def blocks(self): return []
        def html(self, sanitize=False): return ''

if TYPE_CHECKING:
    from db.evidence_db import EvidenceDb, ReportBlockRecord

logger = logging.getLogger(__name__)

# =============================================================================
# Hilfsfunktion
# =============================================================================

def _esc(text: str) -> str:
    """HTML-escaped Text. Schuetzt vor XSS in generierten Reports."""
    return html.escape(str(text) if text is not None else "", quote=True)


# =============================================================================
# Neue Block-Klassen
# =============================================================================

class TableBlock(EditorJsBlock):
    """
    Editor.js Table-Block (@editorjs/table).

    Datenformat:
      { "withHeadings": bool, "content": [["Zelle", ...], ...] }

    Beleg: AP-E5, Projektgespraech 2026-04-19
    """

    def html(self, sanitize: bool = False) -> str:
        content = self.data.get("content", [])
        with_headings = bool(self.data.get("withHeadings", False))

        if not content:
            return '<table class="cdx-block tc-table"></table>'

        rows_html = []
        for i, row in enumerate(content):
            cells = "".join(
                f"<{'th' if i == 0 and with_headings else 'td'}>"
                f"{_esc(cell)}"
                f"</{'th' if i == 0 and with_headings else 'td'}>"
                for cell in row
            )
            rows_html.append(f"<tr>{cells}</tr>")

        thead = ""
        tbody_rows = rows_html
        if with_headings and rows_html:
            thead = f"<thead>{rows_html[0]}</thead>"
            tbody_rows = rows_html[1:]

        tbody = f"<tbody>{''.join(tbody_rows)}</tbody>" if tbody_rows else ""
        return f'<table class="cdx-block tc-table">{thead}{tbody}</table>'


class QuoteBlock(EditorJsBlock):
    """
    Editor.js Quote-Block (@cychann/editorjs-quote).

    Datenformat:
      { "text": "...", "caption": "...", "alignment": "left"|"center" }

    Beleg: AP-E5, Projektgespraech 2026-04-19
    """

    def html(self, sanitize: bool = False) -> str:
        text = self.data.get("text", "")
        caption = self.data.get("caption", "")
        alignment = self.data.get("alignment", "left")

        caption_html = (
            f'<cite class="cdx-quote__caption">{_esc(caption)}</cite>'
            if caption else ""
        )
        return (
            f'<blockquote class="cdx-block cdx-quote cdx-quote--{_esc(alignment)}">'
            f'<p class="cdx-quote__text">{_esc(text)}</p>'
            f'{caption_html}'
            f"</blockquote>"
        )


class NestedListBlock(EditorJsBlock):
    """
    Editor.js Nested List-Block (@editorjs/nested-list).

    Datenformat:
      { "style": "ordered"|"unordered", "items": [{"content": "...", "items": [...]}, ...] }

    Rekursiv — jedes Item kann seinerseits verschachtelte Items haben.
    Beleg: AP-E5, Projektgespraech 2026-04-19
    """

    def html(self, sanitize: bool = False) -> str:
        style = self.data.get("style", "unordered")
        items = self.data.get("items", [])
        return self._render_list(style, items)

    @classmethod
    def _render_list(cls, style: str, items: list) -> str:
        tag = "ol" if style == "ordered" else "ul"
        items_html = "".join(cls._render_item(item, style) for item in items)
        return f'<{tag} class="cdx-block cdx-list cdx-list--{_esc(style)}">{items_html}</{tag}>'

    @classmethod
    def _render_item(cls, item, style: str) -> str:
        """Rendert ein einzelnes Item mit optionaler Verschachtelung."""
        if isinstance(item, str):
            # Flaches Format (aelteres Editor.js-Listenformat)
            return f"<li>{_esc(item)}</li>"

        content = item.get("content", "")
        sub_items = item.get("items", [])
        nested = cls._render_list(style, sub_items) if sub_items else ""
        return f"<li>{_esc(content)}{nested}</li>"


class MarkerBlock(EditorJsBlock):
    """
    Editor.js Marker Inline-Tool (@editorjs/marker).

    Das Marker-Tool ist ein Inline-Tool — es erzeugt keinen eigenen Block,
    sondern wird als HTML-Markup innerhalb von Paragraph-Bloecken eingebettet.
    Falls doch als eigenstaendiger Block gespeichert:
      { "text": "..." }

    Beleg: AP-E5, Projektgespraech 2026-04-19
    """

    def html(self, sanitize: bool = False) -> str:
        text = self.data.get("text", "")
        return f'<mark class="cdx-marker">{_esc(text)}</mark>'


class UnknownBlock(EditorJsBlock):
    """
    Fallback fuer unbekannte Block-Typen.

    Rendert einen neutralen Platzhalter anstatt den Block still zu ignorieren.
    Forensische Grundregel: kein stiller Fehlschlag.
    Beleg: AP-E5, Projektgespraech 2026-04-19
    """

    def html(self, sanitize: bool = False) -> str:
        block_type = self.type or "unbekannt"
        logger.warning(
            "html_renderer: Unbekannter Block-Typ '%s' — Platzhalter gerendert",
            block_type,
        )
        return (
            f'<div class="cdx-block cdx-unknown-block" '
            f'data-type="{_esc(block_type)}">'
            f'[Block-Typ: {_esc(block_type)}]'
            f"</div>"
        )


class EvidenceBlockRenderer(EditorJsBlock):
    """
    Renderer fuer den forensischen EvidenceBlock (custom Tool, AP-E4).

    Rendert eine Beweismittelgruppe als forensische Karte.
    Mit EvidenceDb: laedt Annotationstext und Kategorie nach.
    Ohne EvidenceDb: rendert nur evidence_id-Referenzen.

    Datenformat:
      { "evidence_ids": [42, 43], "group_label": "...", "display_mode": "list" }

    Beleg: AP-E5, Projektgespraech 2026-04-19
    """

    # EvidenceDb-Instanz — wird vom EditorHtmlRenderer gesetzt
    _evidence_db: Optional["EvidenceDb"] = None

    @classmethod
    def with_db(cls, evidence_db: "EvidenceDb") -> type:
        """
        Erzeugt eine EvidenceBlockRenderer-Subklasse mit DB-Zugriff.

        Verwendet eine Subklasse statt einer Instanzvariable, weil
        pyEditorJS Block-Klassen (nicht -Instanzen) in der BLOCKS_MAP registriert.
        Beleg: AP-E5, Projektgespraech 2026-04-19
        """
        return type(
            "EvidenceBlockRendererWithDb",
            (cls,),
            {"_evidence_db": evidence_db},
        )

    def html(self, sanitize: bool = False) -> str:
        evidence_ids = self.data.get("evidence_ids", [])
        group_label  = self.data.get("group_label", "")
        edb          = self.__class__._evidence_db

        label_html = (
            f'<div class="evidence-block-label">{_esc(group_label)}</div>'
            if group_label else ""
        )

        items_html = ""
        for evidence_id in evidence_ids:
            items_html += self._render_evidence_item(evidence_id, edb)

        if not items_html:
            items_html = '<div class="evidence-block-empty">Keine Belege angegeben.</div>'

        return (
            f'<div class="cdx-block evidence-block">'
            f'<div class="evidence-block-header">⚖ Beweismittelgruppe</div>'
            f'{label_html}'
            f'<div class="evidence-block-items">{items_html}</div>'
            f"</div>"
        )

    @staticmethod
    def _render_evidence_item(evidence_id: int, edb: Optional["EvidenceDb"]) -> str:
        """
        Rendert einen einzelnen Beleg als HTML-Karte.
        Mit EvidenceDb: Annotationstext, Kategorie und Seitenreferenz.
        Ohne EvidenceDb: nur evidence_id als Referenz.
        Beleg: AP-E5, Projektgespraech 2026-04-19
        """
        if edb is None:
            return (
                f'<div class="evidence-item" data-id="{evidence_id}">'
                f'<span class="evidence-item-id">Beleg #{evidence_id}</span>'
                f"</div>"
            )

        try:
            # Alle Annotationen durchsuchen um die mit der passenden ID zu finden.
            # get_all_annotations() liefert alle — fuer den Export-Kontext akzeptabel.
            # Eine get_annotation_by_id()-Methode waere effizienter, ist aber
            # in der aktuellen EvidenceDb nicht vorhanden.
            # Beleg: AP-E5, Projektgespraech 2026-04-19
            all_anns = edb.get_all_annotations()
            ann = next((a for a in all_anns if a.id == evidence_id), None)
        except Exception as exc:
            logger.warning(
                "html_renderer: Annotation #%d konnte nicht geladen werden: %s",
                evidence_id, exc,
            )
            ann = None

        if ann is None:
            return (
                f'<div class="evidence-item evidence-item-missing" data-id="{evidence_id}">'
                f'<span class="evidence-item-id">Beleg #{evidence_id}</span>'
                f'<span class="evidence-item-warning"> (nicht gefunden)</span>'
                f"</div>"
            )

        return (
            f'<div class="evidence-item" data-id="{evidence_id}">'
            f'<span class="evidence-item-id">Beleg #{evidence_id}</span>'
            f'<span class="evidence-item-cat evidence-cat-{_esc(ann.category)}">'
            f'{_esc(ann.category)}</span>'
            f'<div class="evidence-item-text">{_esc(ann.text)}</div>'
            f'<div class="evidence-item-source">'
            f'Quelle: <a href="{_esc(ann.page_url)}">{_esc(ann.page_url)}</a>'
            f"</div>"
            f"</div>"
        )


# =============================================================================
# Erweiterte Block-Map
# =============================================================================

# Erweitert die native pyEditorJS BLOCKS_MAP um alle Projekttypen.
# Beleg: AP-E5, Projektgespraech 2026-04-19
_EXTENDED_BLOCKS_MAP: dict[str, type] = {
    # Nativ unterstuetzt (pyEditorJS)
    "header":     None,   # wird von pyEditorJS intern aufgeloest
    "paragraph":  None,
    "list":       None,
    "delimiter":  None,
    "image":      None,
    # Neu hinzugefuegt (AP-E5)
    "table":      TableBlock,
    "quote":      QuoteBlock,
    "nestedlist": NestedListBlock,  # @editorjs/nested-list
    "marker":     MarkerBlock,
}


# =============================================================================
# Hauptklasse: EditorHtmlRenderer
# =============================================================================

class EditorHtmlRenderer:
    """
    Rendert Editor.js-Bloecke (aus evidence_db.report_blocks) als HTML.

    Verwendung:
        renderer = EditorHtmlRenderer(evidence_db=edb)
        html_str = renderer.render(blocks)

    blocks: Liste von ReportBlockRecord-Objekten (aus EvidenceDb.get_blocks_ordered())
            ODER Liste von Dicts im Editor.js-Format.

    Mit evidence_db: EvidenceBlock-Karten enthalten Annotationstext.
    Ohne evidence_db: EvidenceBlock-Karten zeigen nur evidence_id-Referenzen.

    Beleg: AP-E5, Projektgespraech 2026-04-19
    """

    def __init__(self, evidence_db: Optional["EvidenceDb"] = None) -> None:
        # Fruehzeitige Fehlermeldung wenn pyeditorjs fehlt.
        # Beleg: AP-E5 Bugfix, Projektgespraech 2026-04-19
        if not _PYEDITORJS_AVAILABLE:
            raise ImportError(_pyeditorjs_import_error_msg)
        self._edb = evidence_db
        # EvidenceBlockRenderer mit oder ohne DB vorbereiten
        self._evidence_block_cls = (
            EvidenceBlockRenderer.with_db(evidence_db)
            if evidence_db is not None
            else EvidenceBlockRenderer
        )

    def render(self, blocks: list) -> str:
        """
        Rendert eine Liste von Bloecken als HTML-String.

        Args:
            blocks: Liste von ReportBlockRecord oder Dicts im Editor.js-Format.

        Returns:
            HTML-String. Leerstring wenn keine Bloecke vorhanden.

        Beleg: AP-E5, Projektgespraech 2026-04-19
        """
        if not blocks:
            return ""

        html_parts = []
        for block in blocks:
            block_html = self._render_block(block)
            if block_html:
                html_parts.append(block_html)

        return "\n".join(html_parts)

    def render_report(self, report, blocks: list) -> str:
        """
        Rendert einen vollstaendigen Bericht mit Titel und Metadaten.

        Args:
            report: ReportRecord-Objekt.
            blocks: Liste von ReportBlockRecord-Objekten.

        Returns:
            HTML-String des vollstaendigen Berichts.

        Beleg: AP-E5, Projektgespraech 2026-04-19
        """
        type_labels = {
            "interim":  "Zwischenbericht",
            "final":    "Abschlussbericht",
            "addendum": "Nachtragsbericht",
        }
        type_label = type_labels.get(report.report_type, report.report_type)
        body_html  = self.render(blocks)

        return (
            f'<article class="forensic-report" data-report-id="{report.id}">\n'
            f'  <header class="forensic-report-header">\n'
            f'    <h1>{report.sequence_nr}. {_esc(type_label)}: {_esc(report.title)}</h1>\n'
            f'    <div class="forensic-report-meta">\n'
            f'      <span>Erstellt von: {_esc(report.created_by)}</span>\n'
            f'      <span>Status: {_esc(report.status)}</span>\n'
            f"    </div>\n"
            f"  </header>\n"
            f'  <div class="forensic-report-body">\n'
            f"{body_html}\n"
            f"  </div>\n"
            f"</article>"
        )

    def _render_block(self, block) -> str:
        """
        Rendert einen einzelnen Block.

        Akzeptiert ReportBlockRecord (hat .block_type und .block_data)
        oder Dict im Editor.js-Format (hat 'type' und 'data').
        Beleg: AP-E5, Projektgespraech 2026-04-19
        """
        # Normalisierung: ReportBlockRecord oder Dict
        if hasattr(block, "block_type"):
            # ReportBlockRecord
            block_type = block.block_type
            block_data_raw = block.block_data
            try:
                block_data = (
                    json.loads(block_data_raw)
                    if isinstance(block_data_raw, str)
                    else block_data_raw
                )
            except (json.JSONDecodeError, TypeError):
                block_data = {}
            editor_js_block_dict = {
                "id":   getattr(block, "block_id", ""),
                "type": block_type,
                "data": block_data,
            }
        else:
            # Dict im Editor.js-Format
            block_type = block.get("type", "")
            editor_js_block_dict = block

        # evidence-Block: eigenen Renderer verwenden
        if block_type == "evidence":
            renderer_instance = self._evidence_block_cls(_data=editor_js_block_dict)
            return renderer_instance.html()

        # Bekannte Erweiterungstypen: direkt rendern
        if block_type in _EXTENDED_BLOCKS_MAP and _EXTENDED_BLOCKS_MAP[block_type] is not None:
            cls = _EXTENDED_BLOCKS_MAP[block_type]
            instance = cls(_data=editor_js_block_dict)
            return instance.html()

        # Nativ von pyEditorJS unterstuetzte Typen: Parser delegieren
        native_types = {"header", "paragraph", "list", "delimiter", "image"}
        if block_type in native_types:
            parser = EditorJsParser({"blocks": [editor_js_block_dict]})
            rendered = parser.html()
            return rendered if rendered else ""

        # Unbekannter Typ: Platzhalter
        unknown = UnknownBlock(_data=editor_js_block_dict)
        return unknown.html()
