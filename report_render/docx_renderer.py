# =============================================================================
# report_render/docx_renderer.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6/7: Berichts-Ausgabe
# =============================================================================
# Zweck:
#   Rendert ein ReportDocument in ein Word-Dokument (.docx, python-docx).
#   Sieht NUR das ReportDocument, NIE eine Datenbank (Bauplan §2).
#
#   DOCX ist eine REINE-TEXT-Darstellung: es nutzt die vom ReportSource
#   erzeugten *_plain-Felder (Editor.js-HTML entfernt, Entities aufgeloest,
#   Platzhalter aufgeloest). Inline-Formatierung (fett/kursiv) des Editors wird
#   bewusst nicht uebernommen — dasselbe Verhalten wie der Alt-DOCX-Export
#   (v0.6.097), aber jetzt auf dem gemeinsamen Fundament.
#
#   Nicht verhandelbar (Bauplan §3):
#     R1 — Statuszeile sichtbar im Kopf.
#     R2 — Abschnitt "Hinweise zur Erzeugung" mit vollstaendiger Warnliste.
#     R3 — unbekannter Blocktyp sichtbar gemeldet, nicht uebersprungen.
#
#   python-docx wird ERST in render() importiert, damit report_render auch ohne
#   die Bibliothek importierbar bleibt (der Endpunkt meldet ihr Fehlen als 503).
#
# Version: v0.7.402 · Build: 402 · 2026-07-14
# =============================================================================

from __future__ import annotations

import io

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


class DocxRendererUnavailable(RuntimeError):
    """python-docx ist nicht installiert."""


class DocxRenderer:
    """ReportDocument -> bytes (.docx)."""

    def render(self, doc: ReportDocument) -> bytes:
        try:
            from docx import Document
            from docx.shared import Pt, Cm, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
        except ImportError as exc:      # pragma: no cover - Umgebungsabhaengig
            raise DocxRendererUnavailable(str(exc)) from exc

        from datetime import datetime

        d = Document()
        for section in d.sections:
            section.top_margin = Cm(2.5)
            section.bottom_margin = Cm(2.5)
            section.left_margin = Cm(3.0)
            section.right_margin = Cm(2.5)

        def _ts(ts):
            try:
                return datetime.fromtimestamp(int(ts)).strftime("%d.%m.%Y %H:%M")
            except (ValueError, OSError, OverflowError):
                return str(ts)

        # --- R1: Statuszeile ---
        st = doc.status
        banner = {
            "draft":     ("ENTWURF — nicht freigegeben. Nicht zur Vorlage bestimmt.", RGBColor(0x7A, 0, 0)),
            "submitted": ("ZUR ABNAHME VORGELEGT — noch nicht freigegeben.", RGBColor(0x7A, 0x52, 0)),
            "approved":  ("FREIGEGEBEN — Stand: " + _ts(doc.generated_at), RGBColor(0x14, 0x53, 0x2D)),
            "final":     ("ABGESCHLOSSEN / AN STA VERSANDT — Stand: " + _ts(doc.generated_at), RGBColor(0x14, 0x53, 0x2D)),
        }.get(st, (f"UNBEKANNTER STATUS: {st} — Behandlung wie Entwurf.", RGBColor(0x7A, 0, 0)))
        p = d.add_paragraph()
        run = p.add_run(banner[0])
        run.bold = True
        run.font.color.rgb = banner[1]

        # --- Titel + Meta ---
        type_label = REPORT_TYPE_LABELS.get(doc.report_type, doc.report_type)
        title = d.add_paragraph()
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        tr = title.add_run("Ermittlungsbericht")
        tr.bold = True
        tr.font.size = Pt(16)

        meta = d.add_paragraph()
        meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta.add_run(
            f"Beschuldigter: {doc.username} (ID: {doc.uid})\n"
            f"{type_label} Nr. {doc.sequence_nr} — {doc.title}\n"
            f"Erstellt: {_ts(doc.generated_at)} — {len(doc.blocks)} Bloecke — "
            f"{doc.anchor_count} Beweisanker"
        ).font.size = Pt(10)

        d.add_page_break()

        # --- Bloecke ---
        for blk in doc.blocks:
            self._render_block(d, blk, Pt)

        # --- R2: Hinweise zur Erzeugung ---
        d.add_paragraph()
        h = d.add_paragraph()
        h.add_run("Hinweise zur Erzeugung").bold = True
        d.add_paragraph(
            f"Erzeugt: {_ts(doc.generated_at)} — Status: {doc.status} — "
            f"Bloecke: {len(doc.blocks)} — Beweisanker: {doc.anchor_count}"
        )
        if doc.warnings:
            d.add_paragraph(f"Warnungen ({len(doc.warnings)}):")
            for w in doc.warnings:
                label = WARNING_LABELS.get(w.kind, w.kind)
                loc = f" (Block {w.block_id})" if w.block_id else ""
                d.add_paragraph(f"{label}: {w.detail}{loc}", style="List Bullet")
        else:
            d.add_paragraph("Keine Warnungen — alle Platzhalter aufgeloest, "
                            "alle Bloecke sortiert und bekannt.")

        # --- Klassifizierungs-Fusszeile ---
        footer_p = d.sections[0].footer.paragraphs[0]
        footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        footer_p.add_run(CLASSIFICATION).font.size = Pt(8)

        buf = io.BytesIO()
        d.save(buf)
        return buf.getvalue()

    # ------------------------------------------------------------------
    def _render_block(self, d, blk: RenderedBlock, Pt) -> None:
        if not blk.is_known_type:      # R3
            r = d.add_paragraph().add_run(
                f"⚠ Unbekannter Blocktyp '{blk.block_type}' — "
                f"Inhalt nicht regulaer dargestellt (siehe Hinweise)."
            )
            r.bold = True
            self._anchors(d, blk, Pt)
            return

        bt = blk.block_type
        if bt == "paragraph":
            d.add_paragraph(blk.resolved_text_plain)
        elif bt == "header":
            try:
                level = int(blk.data.get("level", 2))
            except (ValueError, TypeError):
                level = 2
            d.add_heading(blk.resolved_text_plain or "", min(max(level, 1), 4))
        elif bt == "list":
            ordered = blk.data.get("style") == "ordered"
            style = "List Number" if ordered else "List Bullet"
            for it in blk.data.get("_resolved_items_plain", []):
                d.add_paragraph(it, style=style)
        elif bt == "table":
            rows = blk.data.get("_resolved_rows_plain", [])
            if rows:
                ncols = max(len(r) for r in rows)
                t = d.add_table(rows=0, cols=ncols)
                try:
                    t.style = "Table Grid"
                except KeyError:       # pragma: no cover
                    pass
                for row in rows:
                    cells = t.add_row().cells
                    for i in range(ncols):
                        cells[i].text = row[i] if i < len(row) else ""
        elif bt == "quote":
            d.add_paragraph(blk.resolved_text_plain, style="Intense Quote")
            cap = blk.data.get("_resolved_caption_plain", "")
            if cap:
                d.add_paragraph(f"— {cap}").italic = True
        elif bt == "image":
            url = blk.data.get("_image_url", "")
            avail = blk.data.get("_image_available", False)
            p = d.add_paragraph()
            p.add_run("Bildverweis (nicht eingebettet — §§184b/184c): ").bold = True
            p.add_run(f"Quelle: {url or '(keine URL)'}; "
                      f"Status: {'vorhanden' if avail else 'NICHT auffindbar'}")
            if avail:
                uh = blk.data.get("_image_url_hash")
                aid = blk.data.get("_image_asset_id")
                size = blk.data.get("_image_size")
                bits = []
                if uh:
                    bits.append(f"url_hash={uh}")
                if aid is not None:
                    bits.append(f"asset_id={aid}")
                if size is not None:
                    bits.append(f"file_size={size} B")
                if bits:
                    d.add_paragraph("Anker: " + " · ".join(bits))
            cap = blk.data.get("_resolved_caption_plain", "")
            if cap:
                d.add_paragraph(f"Bildunterschrift: {cap}")
        elif bt == "delimiter":
            d.add_paragraph("———")
        elif bt == "marker":
            r = d.add_paragraph().add_run(blk.resolved_text_plain)
            r.bold = True
        elif bt == "evidence":
            if blk.resolved_text_plain:
                d.add_paragraph(blk.resolved_text_plain)
            ev_ids = blk.data.get("evidence_ids", [])
            if isinstance(ev_ids, list) and ev_ids:
                d.add_paragraph("Beweis-IDs: " + ", ".join(str(e) for e in ev_ids))

        self._anchors(d, blk, Pt)

    def _anchors(self, d, blk: RenderedBlock, Pt) -> None:
        if not blk.anchors:
            return
        p = d.add_paragraph()
        run = p.add_run("Beweisanker: ")
        run.bold = True
        run.font.size = Pt(9)
        for a in blk.anchors:
            aid = getattr(a, "id", "")
            atext = getattr(a, "anchor_text", "")
            p.add_run(f"[{aid}] {atext}  ").font.size = Pt(9)
