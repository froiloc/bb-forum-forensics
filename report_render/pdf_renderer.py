# =============================================================================
# report_render/pdf_renderer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   Rendert ein ReportDocument in ein PDF (reportlab/platypus). Sieht NUR das
#   ReportDocument, NIE eine Datenbank (Bauplan §2).
#
#   PDF ist — wie DOCX — eine REINE-TEXT-Darstellung ueber die *_plain-Felder
#   des ReportSource. Inline-Editor-Formatierung wird nicht uebernommen.
#
#   Nicht verhandelbar (Bauplan §3):
#     R1 — Statusbanner sichtbar im Kopf.
#     R2 — Abschnitt "Hinweise zur Erzeugung" mit vollstaendiger Warnliste.
#     R3 — unbekannter Blocktyp sichtbar gemeldet, nicht uebersprungen.
#
#   reportlab wird ERST in render() importiert, damit report_render auch ohne die
#   Bibliothek importierbar bleibt (der Endpunkt meldet ihr Fehlen als 503).
#   Beleg §4.3 (mc): reportlab 5.0.0 = py3-none-any (rein Python, 3.14-tauglich),
#   keine Systembibliotheken; kommt ab Build 404 in die Offline-VM (requirements/
#   prepare_deployment/install).
#
# Version: v0.7.404 · Build: 404 · 2026-07-14
# =============================================================================

from __future__ import annotations

import io
from datetime import datetime

from report_render.report_document import ReportDocument, RenderedBlock

CLASSIFICATION = "VERTRAULICH — IT-FORENSISCHES ERMITTLUNGSWERKZEUG NRW"

REPORT_TYPE_LABELS = {
    "interim": "Zwischenbericht", "final": "Abschlussbericht", "addendum": "Nachtrag",
}
WARNING_LABELS = {
    "unresolved_placeholder": "Nicht auflösbarer Platzhalter (Default eingesetzt)",
    "unknown_placeholder":    "Unbekannter Platzhalter (unveraendert belassen)",
    "unordered_block":        "Block ohne Sortierungseintrag (ans Ende gestellt)",
    "unknown_block_type":     "Unbekannter Blocktyp (Inhalt nicht regulaer dargestellt)",
    "missing_image":          "Bild-Verweis nicht auffindbar",
}


def _xml_esc(s) -> str:
    """Escaping fuer reportlab-Paragraph-Mini-Markup (&, <, >). \\n -> <br/>.

    reportlab interpretiert Paragraph-Text als XML-aehnliches Markup; unescapte
    &,<,> wuerden das Parsing brechen. Der Text kommt aus *_plain (bereits ohne
    HTML-Tags), muss hier aber XML-sicher gemacht werden.
    """
    if s is None:
        return ""
    out = (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    return out.replace("\n", "<br/>")


class PdfRendererUnavailable(RuntimeError):
    """reportlab ist nicht installiert."""


class PdfRenderer:
    """ReportDocument -> bytes (PDF)."""

    def render(self, doc: ReportDocument) -> bytes:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import cm
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.enums import TA_CENTER
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                HRFlowable, ListFlowable, ListItem,
            )
        except ImportError as exc:      # pragma: no cover - Umgebungsabhaengig
            raise PdfRendererUnavailable(str(exc)) from exc

        styles = getSampleStyleSheet()
        body = styles["BodyText"]
        small = ParagraphStyle("small", parent=body, fontSize=8, textColor=colors.HexColor("#555555"))
        anchor_style = ParagraphStyle("anchor", parent=small, leftIndent=6)
        quote_style = ParagraphStyle("quote", parent=body, leftIndent=18,
                                     textColor=colors.HexColor("#333333"), fontName="Helvetica-Oblique")
        unknown_style = ParagraphStyle("unknown", parent=body, textColor=colors.HexColor("#7A0000"),
                                       fontName="Helvetica-Bold", borderPadding=3)
        hint_style = ParagraphStyle("hint", parent=small)
        hint_warn = ParagraphStyle("hintwarn", parent=small, textColor=colors.HexColor("#7A0000"))
        img_style = ParagraphStyle("img", parent=small, borderPadding=4)

        def P(text, style=body):
            return Paragraph(_xml_esc(text), style)

        story = []
        story.append(self._banner(doc, Paragraph, ParagraphStyle, colors, body))
        story.append(Spacer(1, 10))

        # Titel + Meta
        title_style = ParagraphStyle("title", parent=styles["Title"], alignment=TA_CENTER)
        story.append(Paragraph("Ermittlungsbericht", title_style))
        type_label = REPORT_TYPE_LABELS.get(doc.report_type, doc.report_type)
        meta_style = ParagraphStyle("meta", parent=small, alignment=TA_CENTER)
        story.append(Paragraph(
            _xml_esc(f"Beschuldigter: {doc.username} (ID: {doc.uid})\n"
                     f"{type_label} Nr. {doc.sequence_nr} — {doc.title}\n"
                     f"Erstellt: {self._ts(doc.generated_at)} — {len(doc.blocks)} Bloecke — "
                     f"{doc.anchor_count} Beweisanker"),
            meta_style))
        story.append(Spacer(1, 16))

        # Bloecke
        for blk in doc.blocks:
            self._block(story, blk, P, Paragraph, Spacer, Table, TableStyle,
                        HRFlowable, ListFlowable, ListItem, colors, body, small,
                        quote_style, unknown_style, anchor_style, img_style)

        # R2 Hinweise
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", color=colors.HexColor("#cccccc")))
        story.append(Paragraph("Hinweise zur Erzeugung", ParagraphStyle(
            "hinth", parent=small, fontSize=10, fontName="Helvetica-Bold")))
        story.append(Paragraph(_xml_esc(
            f"Erzeugt: {self._ts(doc.generated_at)} — Status: {doc.status} — "
            f"Bloecke: {len(doc.blocks)} — Beweisanker: {doc.anchor_count}"), hint_style))
        if doc.warnings:
            story.append(Paragraph(_xml_esc(f"Warnungen ({len(doc.warnings)}):"), hint_warn))
            items = []
            for w in doc.warnings:
                label = WARNING_LABELS.get(w.kind, w.kind)
                loc = f" (Block {w.block_id})" if w.block_id else ""
                items.append(ListItem(Paragraph(_xml_esc(f"{label}: {w.detail}{loc}"), hint_warn)))
            story.append(ListFlowable(items, bulletType="bullet"))
        else:
            story.append(Paragraph(
                "Keine Warnungen — alle Platzhalter aufgeloest, alle Bloecke sortiert und bekannt.",
                hint_style))

        buf = io.BytesIO()
        d = SimpleDocTemplate(
            buf, pagesize=A4,
            topMargin=2.5 * cm, bottomMargin=2.5 * cm,
            leftMargin=3.0 * cm, rightMargin=2.5 * cm,
            title=f"{type_label} {doc.username} (ID {doc.uid})",
        )

        def _footer(canvas, docobj):
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 7)
            canvas.setFillColor(colors.HexColor("#888888"))
            canvas.drawCentredString(A4[0] / 2.0, 1.2 * cm, CLASSIFICATION)
            canvas.setFont("Helvetica", 7)
            canvas.drawRightString(A4[0] - 2.5 * cm, 1.2 * cm, f"Seite {docobj.page}")
            canvas.restoreState()

        d.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return buf.getvalue()

    # ------------------------------------------------------------------
    def _ts(self, ts) -> str:
        try:
            return datetime.fromtimestamp(int(ts)).strftime("%d.%m.%Y %H:%M")
        except (ValueError, OSError, OverflowError):
            return str(ts)

    def _banner(self, doc, Paragraph, ParagraphStyle, colors, body):
        """R1 — Statusbanner als farbiger Absatz."""
        st = doc.status
        text, color = {
            "draft":     ("ENTWURF — nicht freigegeben. Nicht zur Vorlage bestimmt.", "#7A0000"),
            "submitted": ("ZUR ABNAHME VORGELEGT — noch nicht freigegeben.", "#7A5200"),
            "approved":  ("FREIGEGEBEN — Stand: " + self._ts(doc.generated_at), "#14532D"),
            "final":     ("ABGESCHLOSSEN / AN STA VERSANDT — Stand: " + self._ts(doc.generated_at), "#14532D"),
        }.get(st, (f"UNBEKANNTER STATUS: {st} — Behandlung wie Entwurf.", "#7A0000"))
        style = ParagraphStyle(
            "banner", parent=body, fontName="Helvetica-Bold",
            textColor=colors.HexColor(color), borderColor=colors.HexColor(color),
            borderWidth=1.2, borderPadding=6, backColor=colors.HexColor("#f7f7f7"),
        )
        return Paragraph(_xml_esc(text), style)

    # ------------------------------------------------------------------
    def _block(self, story, blk: RenderedBlock, P, Paragraph, Spacer, Table, TableStyle,
               HRFlowable, ListFlowable, ListItem, colors, body, small,
               quote_style, unknown_style, anchor_style, img_style) -> None:
        if not blk.is_known_type:      # R3
            story.append(Paragraph(_xml_esc(
                f"⚠ Unbekannter Blocktyp '{blk.block_type}' — "
                f"Inhalt nicht regulaer dargestellt (siehe Hinweise)."), unknown_style))
            self._anchors(story, blk, Paragraph, anchor_style)
            story.append(Spacer(1, 6))
            return

        bt = blk.block_type
        if bt == "paragraph":
            story.append(P(blk.resolved_text_plain))
        elif bt == "header":
            try:
                level = int(blk.data.get("level", 2))
            except (ValueError, TypeError):
                level = 2
            from reportlab.lib.styles import ParagraphStyle
            hstyle = ParagraphStyle(f"h{level}", parent=body, fontName="Helvetica-Bold",
                                    fontSize=max(16 - min(max(level, 1), 6), 10), spaceAfter=4)
            story.append(Paragraph(_xml_esc(blk.resolved_text_plain), hstyle))
        elif bt == "list":
            ordered = blk.data.get("style") == "ordered"
            items = [ListItem(P(it)) for it in blk.data.get("_resolved_items_plain", [])]
            if items:
                story.append(ListFlowable(items, bulletType="1" if ordered else "bullet"))
        elif bt == "table":
            rows = blk.data.get("_resolved_rows_plain", [])
            if rows:
                ncols = max(len(r) for r in rows)
                data = [[P(r[i] if i < len(r) else "") for i in range(ncols)] for r in rows]
                t = Table(data, hAlign="LEFT")
                t.setStyle(TableStyle([
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, 0),
                     colors.HexColor("#eeeeee") if blk.data.get("withHeadings") else colors.white),
                ]))
                story.append(t)
        elif bt == "quote":
            story.append(Paragraph(_xml_esc(blk.resolved_text_plain), quote_style))
            cap = blk.data.get("_resolved_caption_plain", "")
            if cap:
                story.append(Paragraph(_xml_esc(f"— {cap}"), small))
        elif bt == "image":
            story.append(self._image(blk, Paragraph, img_style))
        elif bt == "delimiter":
            story.append(HRFlowable(width="60%", color=colors.HexColor("#999999")))
        elif bt == "marker":
            from reportlab.lib.styles import ParagraphStyle
            mstyle = ParagraphStyle("marker", parent=body, backColor=colors.HexColor("#fff3a0"))
            story.append(Paragraph(_xml_esc(blk.resolved_text_plain), mstyle))
        elif bt == "evidence":
            if blk.resolved_text_plain:
                story.append(P(blk.resolved_text_plain))
            ev = blk.data.get("evidence_ids", [])
            if isinstance(ev, list) and ev:
                story.append(Paragraph(_xml_esc("Beweis-IDs: " + ", ".join(str(e) for e in ev)), small))

        self._anchors(story, blk, Paragraph, anchor_style)
        story.append(Spacer(1, 6))

    def _image(self, blk, Paragraph, img_style):
        """§4.2 — Bildverweis, KEINE Bild-Einbettung."""
        url = blk.data.get("_image_url", "")
        avail = blk.data.get("_image_available", False)
        parts = [f"<b>Bildverweis (nicht eingebettet — §§184b/184c):</b> "
                 f"Quelle: {_xml_esc(url) or '(keine URL)'}; "
                 f"Status: {'vorhanden' if avail else 'NICHT auffindbar'}"]
        if avail:
            uh = blk.data.get("_image_url_hash")
            aid = blk.data.get("_image_asset_id")
            size = blk.data.get("_image_size")
            bits = []
            if uh:
                bits.append(f"url_hash={_xml_esc(uh)}")
            if aid is not None:
                bits.append(f"asset_id={_xml_esc(aid)}")
            if size is not None:
                bits.append(f"file_size={_xml_esc(size)} B")
            if bits:
                parts.append("Anker: " + " · ".join(bits))
        cap = blk.data.get("_resolved_caption_plain", "")
        if cap:
            parts.append(f"Bildunterschrift: {_xml_esc(cap)}")
        # parts sind bereits XML-sicher zusammengesetzt (url/anchor via _xml_esc).
        return Paragraph("<br/>".join(parts), img_style)

    def _anchors(self, story, blk, Paragraph, anchor_style) -> None:
        if not blk.anchors:
            return
        lines = []
        for a in blk.anchors:
            aid = getattr(a, "id", "")
            atext = getattr(a, "anchor_text", "")
            lines.append(_xml_esc(f"[{aid}] {atext}"))
        story.append(Paragraph("Beweisanker: " + "; ".join(lines), anchor_style))
