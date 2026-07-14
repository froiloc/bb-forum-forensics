# =============================================================================
# report_render/html_renderer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   Rendert ein ReportDocument in ein selbstenthaltendes HTML-Dokument (UTF-8).
#   Der Renderer sieht NUR das ReportDocument, NIE eine Datenbank (Bauplan §2).
#
#   Nicht verhandelbare Regeln (Bauplan Build 397 §3):
#     R1 — Berichtsstatus sichtbar im Kopf (Entwurf != freigegebene Akte).
#     R2 — Kein Platzhalter/kein Datenfehler verschwindet still: Abschnitt
#          "Hinweise zur Erzeugung" listet alle Warnungen.
#     R3 — Unbekannter Blocktyp wird sichtbar gemeldet, nicht uebersprungen.
#
#   Wichtige Escaping-Invariante:
#     Die vom ReportSource/PlaceholderResolver gelieferten Felder
#     (resolved_text, _resolved_items, _resolved_rows, _resolved_caption) sind
#     BEREITS HTML-sichere Fragmente (Editor.js-HTML + escapte Chip-Werte) und
#     werden UNVERAENDERT ausgegeben. Nur "Chrome" und Metadaten (Titel, Name,
#     Ankertexte, Warnungs-Details) werden hier via _esc() escaped.
#     Doppeltes Escaping wuerde die Ansicht vom Bildschirm des Ermittlers
#     abweichen lassen (Parität, §6).
#
# Version: v0.7.399 · Build: 399 · 2026-07-13
# =============================================================================

from __future__ import annotations

from datetime import datetime

from report_render.report_document import ReportDocument, RenderedBlock

CLASSIFICATION = "VERTRAULICH — IT-FORENSISCHES ERMITTLUNGSWERKZEUG NRW"

#: Anzeigenamen der Berichtstypen. Beleg: userinfo/report.js:231-233.
REPORT_TYPE_LABELS = {
    "interim":  "Zwischenbericht",
    "final":    "Abschlussbericht",
    "addendum": "Nachtrag",
}

#: Menschenlesbare Beschreibung der Warn-Arten fuer den Hinweis-Abschnitt (R2).
WARNING_LABELS = {
    "unresolved_placeholder": "Nicht auflösbarer Platzhalter (Default eingesetzt)",
    "unknown_placeholder":    "Unbekannter Platzhalter (unveraendert belassen)",
    "unordered_block":        "Block ohne Sortierungseintrag (ans Ende gestellt)",
    "unknown_block_type":     "Unbekannter Blocktyp (Inhalt nicht regulaer dargestellt)",
    "missing_image":          "Bild-Verweis nicht auffindbar",
}


def _esc(s) -> str:
    """HTML-Escaping fuer Chrome/Metadaten (& < > ")."""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


class HtmlRenderer:
    """ReportDocument -> bytes (UTF-8, selbstenthaltendes HTML)."""

    def render(self, doc: ReportDocument) -> bytes:
        """Erzeugt das vollstaendige HTML-Dokument als UTF-8-Bytes."""
        parts: list[str] = []
        parts.append(self._doc_head(doc))
        parts.append(self._status_banner(doc))
        parts.append(self._meta_header(doc))

        if doc.blocks:
            for blk in doc.blocks:
                parts.append(self._render_block(blk))
        else:
            parts.append('<p><em>Keine Bloecke im Bericht vorhanden.</em></p>')

        parts.append(self._hints_section(doc))     # R2
        parts.append(self._doc_foot())
        return "".join(parts).encode("utf-8")

    # ------------------------------------------------------------------
    def _fmt_ts(self, ts: int) -> str:
        """Formatiert einen Unix-Zeitstempel (deterministisch aus dem Wert)."""
        try:
            return datetime.fromtimestamp(int(ts)).strftime("%d.%m.%Y %H:%M")
        except (ValueError, OSError, OverflowError):
            return str(ts)

    def _doc_head(self, doc: ReportDocument) -> str:
        title = f"{REPORT_TYPE_LABELS.get(doc.report_type, doc.report_type)} — {doc.username} (ID: {doc.uid})"
        return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>{_esc(title)}</title>
  <style>
    body {{ font-family: "Times New Roman", Times, serif; font-size: 11pt;
           max-width: 800px; margin: 40px auto; color: #000; }}
    .status-banner {{ font-family: Arial, sans-serif; font-weight: bold;
           padding: 8pt 12pt; margin-bottom: 18pt; border: 2pt solid; }}
    .status-draft     {{ color: #7a0000; border-color: #7a0000; background: #fff3f3; }}
    .status-submitted {{ color: #7a5200; border-color: #7a5200; background: #fff9ec; }}
    .status-approved  {{ color: #14532d; border-color: #14532d; background: #f0fff4; }}
    .header {{ font-size: 9pt; color: #555; border-bottom: 1pt solid #ccc;
               padding-bottom: 6pt; margin-bottom: 24pt; font-family: Arial, sans-serif; }}
    .block {{ margin-bottom: 14pt; page-break-inside: avoid; }}
    .para-content {{ line-height: 1.6; word-break: break-word; }}
    h1,h2,h3,h4,h5,h6 {{ font-family: Arial, sans-serif; }}
    blockquote {{ border-left: 3pt solid #ccc; margin: 8pt 0; padding: 2pt 12pt; color: #333; }}
    blockquote cite {{ display: block; font-size: 9pt; color: #666; margin-top: 4pt; }}
    table.report-table {{ border-collapse: collapse; width: 100%; }}
    table.report-table td, table.report-table th {{ border: 1pt solid #999; padding: 3pt 6pt; }}
    .image-ref {{ border: 1pt dashed #999; background: #fafafa; padding: 8pt 12pt;
                  font-family: Arial, sans-serif; font-size: 9.5pt; }}
    .image-ref .lbl {{ font-weight: bold; }}
    .image-missing {{ color: #7a0000; }}
    .evidence-ref {{ border-left: 3pt solid #14532d; padding: 2pt 12pt; }}
    .unknown-block {{ color: #7a0000; font-family: Arial, sans-serif; font-weight: bold;
                      border: 1pt solid #7a0000; padding: 4pt 8pt; }}
    .anchors {{ font-size: 8.5pt; color: #555; margin-top: 4pt; }}
    .hints {{ font-family: Arial, sans-serif; font-size: 8.5pt; color: #444;
              border-top: 1pt solid #ccc; margin-top: 36pt; padding-top: 8pt; }}
    .hints h3 {{ font-size: 10pt; margin-bottom: 6pt; }}
    .hints .warn {{ color: #7a0000; }}
    .footer {{ font-size: 8pt; color: #888; border-top: 1pt solid #ddd;
               padding-top: 4pt; margin-top: 24pt; text-align: center;
               font-family: Arial, sans-serif; font-weight: bold; }}
  </style>
</head>
<body>
"""

    def _status_banner(self, doc: ReportDocument) -> str:
        """R1 — Berichtsstatus sichtbar im Kopf."""
        st = doc.status
        if st == "draft":
            return ('<div class="status-banner status-draft">'
                    'ENTWURF — nicht freigegeben. Nicht zur Vorlage bestimmt.</div>')
        if st == "submitted":
            return ('<div class="status-banner status-submitted">'
                    'ZUR ABNAHME VORGELEGT — noch nicht freigegeben.</div>')
        if st in ("approved", "final"):
            label = "FREIGEGEBEN" if st == "approved" else "ABGESCHLOSSEN / AN STA VERSANDT"
            return (f'<div class="status-banner status-approved">'
                    f'{label} — Stand: {_esc(self._fmt_ts(doc.generated_at))}.</div>')
        # Unbekannter Status: nicht still — als Entwurf-aehnliche Warnung behandeln.
        return (f'<div class="status-banner status-draft">'
                f'UNBEKANNTER STATUS: {_esc(st)} — Behandlung wie Entwurf.</div>')

    def _meta_header(self, doc: ReportDocument) -> str:
        type_label = REPORT_TYPE_LABELS.get(doc.report_type, doc.report_type)
        return (
            '<div class="header">'
            f'Beschuldigter: {_esc(doc.username)} &middot; ID: {doc.uid}<br>'
            f'{_esc(type_label)} Nr. {doc.sequence_nr} &middot; Titel: {_esc(doc.title)}<br>'
            f'Erstellt am: {_esc(self._fmt_ts(doc.generated_at))} &middot; '
            f'{len(doc.blocks)} Bl&ouml;cke &middot; {doc.anchor_count} Beweisanker'
            '</div>'
        )

    # ------------------------------------------------------------------
    def _render_block(self, blk: RenderedBlock) -> str:
        """Dispatch auf den passenden Blockrenderer. Unbekannter Typ -> R3."""
        if not blk.is_known_type:
            return self._render_unknown(blk)
        fn = {
            "paragraph": self._render_paragraph,
            "header":    self._render_header,
            "list":      self._render_list,
            "table":     self._render_table,
            "quote":     self._render_quote,
            "image":     self._render_image,
            "delimiter": self._render_delimiter,
            "marker":    self._render_marker,
            "evidence":  self._render_evidence,
        }.get(blk.block_type, self._render_unknown)
        return f'<div class="block">{fn(blk)}{self._anchors(blk)}</div>'

    # -- einzelne Blockrenderer (resolved_* = bereits HTML-sicher!) --

    def _render_paragraph(self, blk: RenderedBlock) -> str:
        return f'<p class="para-content">{blk.resolved_text}</p>'

    def _render_header(self, blk: RenderedBlock) -> str:
        try:
            level = int(blk.data.get("level", 2))
        except (ValueError, TypeError):
            level = 2
        level = min(max(level, 1), 6)
        return f'<h{level}>{blk.resolved_text}</h{level}>'

    def _render_list(self, blk: RenderedBlock) -> str:
        items = blk.data.get("_resolved_items", [])
        tag = "ol" if blk.data.get("style") == "ordered" else "ul"
        lis = "".join(f"<li>{it}</li>" for it in items)
        return f'<{tag}>{lis}</{tag}>'

    def _render_table(self, blk: RenderedBlock) -> str:
        rows = blk.data.get("_resolved_rows", [])
        with_headings = bool(blk.data.get("withHeadings"))
        out = ['<table class="report-table">']
        for i, row in enumerate(rows):
            cell_tag = "th" if (with_headings and i == 0) else "td"
            cells = "".join(f"<{cell_tag}>{c}</{cell_tag}>" for c in row)
            out.append(f"<tr>{cells}</tr>")
        out.append("</table>")
        return "".join(out)

    def _render_quote(self, blk: RenderedBlock) -> str:
        caption = blk.data.get("_resolved_caption", "")
        cite = f"<cite>{caption}</cite>" if caption else ""
        return f'<blockquote>{blk.resolved_text}{cite}</blockquote>'

    def _render_image(self, blk: RenderedBlock) -> str:
        """§4.2: forensisch harter VERWEIS, KEINE Bild-Bytes."""
        url = blk.data.get("_image_url", "")
        caption = blk.data.get("_resolved_caption", "")
        available = blk.data.get("_image_available", False)
        avail_txt = ("in assets_&lt;uid&gt;.db vorhanden" if available
                     else '<span class="image-missing">NICHT in assets_&lt;uid&gt;.db auffindbar</span>')
        cap = f'<br><span class="lbl">Bildunterschrift:</span> {caption}' if caption else ""
        return (
            '<div class="image-ref">'
            '<span class="lbl">Bildverweis (nicht eingebettet — §§184b/184c):</span><br>'
            f'Quelle: {_esc(url) or "(keine URL)"}<br>'
            f'Status: {avail_txt}'
            f'{cap}'
            '</div>'
        )

    def _render_delimiter(self, blk: RenderedBlock) -> str:
        return "<hr>"

    def _render_marker(self, blk: RenderedBlock) -> str:
        # 'marker' als Blocktyp: wie ein hervorgehobener Absatz behandeln.
        return f'<p class="para-content"><mark>{blk.resolved_text}</mark></p>'

    def _render_evidence(self, blk: RenderedBlock) -> str:
        ev_ids = blk.data.get("evidence_ids", [])
        ids_txt = ""
        if isinstance(ev_ids, list) and ev_ids:
            ids_txt = "Beweis-IDs: " + ", ".join(_esc(str(e)) for e in ev_ids)
        body = blk.resolved_text or ""
        inner = body + (f'<div class="anchors">{ids_txt}</div>' if ids_txt else "")
        return f'<div class="evidence-ref">{inner}</div>'

    def _render_unknown(self, blk: RenderedBlock) -> str:
        """R3 — unbekannter Blocktyp sichtbar gemeldet, nicht uebersprungen."""
        return (f'<div class="block"><div class="unknown-block">'
                f'&#9888; Unbekannter Blocktyp \'{_esc(blk.block_type)}\' — '
                f'Inhalt nicht regulaer dargestellt (siehe Hinweise).'
                f'</div>{self._anchors(blk)}</div>')

    def _anchors(self, blk: RenderedBlock) -> str:
        """Beweisanker als Fussnotenliste (Ankertext ist Klartext -> escapen)."""
        if not blk.anchors:
            return ""
        lis = []
        for a in blk.anchors:
            aid = getattr(a, "id", "")
            atext = getattr(a, "anchor_text", "")
            lis.append(f"<li>[{_esc(str(aid))}] {_esc(atext)}</li>")
        return f'<ol class="anchors">{"".join(lis)}</ol>'

    # ------------------------------------------------------------------
    def _hints_section(self, doc: ReportDocument) -> str:
        """R2 — "Hinweise zur Erzeugung": Zeitpunkt, Status, Zahlen, Warnliste."""
        out = ['<div class="hints">']
        out.append("<h3>Hinweise zur Erzeugung</h3>")
        out.append(
            f'<div>Erzeugt: {_esc(self._fmt_ts(doc.generated_at))} &middot; '
            f'Berichtsstatus: {_esc(doc.status)} &middot; '
            f'Bl&ouml;cke: {len(doc.blocks)} &middot; '
            f'Beweisanker: {doc.anchor_count}</div>'
        )
        if doc.warnings:
            out.append(f'<div class="warn">Warnungen ({len(doc.warnings)}):</div><ul class="warn">')
            for w in doc.warnings:
                label = WARNING_LABELS.get(w.kind, w.kind)
                loc = f" (Block {_esc(w.block_id)})" if w.block_id else ""
                out.append(f"<li>{_esc(label)}: {_esc(w.detail)}{loc}</li>")
            out.append("</ul>")
        else:
            out.append("<div>Keine Warnungen — alle Platzhalter aufgeloest, "
                       "alle Bl&ouml;cke sortiert und bekannt.</div>")
        out.append("</div>")
        return "".join(out)

    def _doc_foot(self) -> str:
        return (f'<div class="footer">{_esc(CLASSIFICATION)}</div>\n</body>\n</html>')
