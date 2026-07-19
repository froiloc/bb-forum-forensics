# =============================================================================
# management/stats/status_report.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Statistik (AP-2C)
# =============================================================================
# Zweck (Idee 16 — StA-Berichtsgenerator):
#   Fasst die von StatsRepo.compute erzeugten Kennzahlen zu einem der StA/
#   Fuehrung vorlegbaren Status-Bericht zusammen — als self-contained HTML und
#   als PDF. Jede Kennzahl ist ueber das Kennzahlen-Glossar (Build 444) belegt;
#   der Bericht traegt den einheitlichen Aktenkopf, Erzeugungsvermerk und die
#   Pruefsumme (Export-Framework, Build 440).
#
#   REINE FUNKTIONEN (kein DB-/Netz-/Uhr-Zugriff): stats + context werden
#   injiziert -> deterministisch/testbar (Muster der html_export.py). reportlab
#   wird fuer die PDF-Ausgabe LAZY importiert; fehlt sie -> StatusReportUnavailable
#   (kein stiller Ausfall, analog Pdf/Excel-Unavailable).
#
#   PRUEFSUMME: SHA-256 ueber die Kennzahl-Nutzlast (json_payload_sha256(stats)),
#   in HTML wie PDF identisch -> beide Ausgaben desselben Standes tragen denselben
#   Datendigest, vom Empfaenger unabhaengig nachrechenbar.
#
# Version: v0.7.445 · Build: 445 · 2026-07-19
# =============================================================================

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

from management.export.checksum import json_payload_sha256
from management.export.export_envelope import ExportEnvelope


class StatusReportUnavailable(RuntimeError):
    """reportlab ist nicht installiert — PDF-Statusbericht nicht moeglich."""


def stats_digest(stats: Dict[str, Any]) -> str:
    """Datendigest ueber die Kennzahl-Nutzlast (kanonisch, nachrechenbar)."""
    return json_payload_sha256(stats)


# -- gemeinsame Aufbereitung ---------------------------------------------------

def _sections(stats: Dict[str, Any]) -> List[tuple]:
    """
    (Ueberschrift, Zeilen[(schluessel,wert)]) je Kennzahl-Abschnitt. EINE
    Wahrheit fuer HTML und PDF -> keine Divergenz der Ausgaben.
    """
    t = stats.get("totals", {})
    out: List[tuple] = [
        ("Gesamtzahlen", [
            ("Fälle gesamt", t.get("cases", 0)),
            ("Zugewiesen", t.get("assigned", 0)),
            ("Unzugewiesen", t.get("unassigned", 0)),
            ("Ereignisse gesamt", t.get("events", 0)),
        ]),
        ("Fälle je Fallstatus",
         [(k, v) for k, v in stats.get("by_status", {}).items()]),
        ("Fälle je Priorität",
         [("Priorität %s" % k, v) for k, v in stats.get("by_priority", {}).items()]),
        ("Fälle je Ampel",
         [(k, v) for k, v in stats.get("by_ampel", {}).items()]),
        ("Fälle je Ermittler",
         [((a.get("display_name") or ("#%s" % a.get("person_id"))), a.get("count", 0))
          for a in stats.get("by_assignee", [])]),
        ("Durchsatz je Tag (Fall-Ereignisse)",
         [(d.get("day"), d.get("count", 0)) for d in stats.get("throughput_by_day", [])]),
    ]
    return out


# -- HTML ----------------------------------------------------------------------

def build_status_report_html(stats: Dict[str, Any], context,
                             *, period_label: Optional[str] = None) -> str:
    """Self-contained Status-Bericht (HTML) im einheitlichen Rahmen."""
    env = ExportEnvelope(context)
    digest = stats_digest(stats)
    scope = "Alle Fälle" if stats.get("scope") != "eigene" else "Eigene Fälle"

    parts = [
        "<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<title>AIW — StA-Statusbericht</title>\n"
        "<style>table{border-collapse:collapse;margin:.4em 0}"
        "td,th{border:1px solid #ccc;padding:4px 8px;text-align:left}"
        ".aiw-export-band{background:#1F4E79;color:#fff;padding:8px}"
        "h2{margin-top:1.2em}</style>\n</head>\n<body>\n",
        env.classification_band_html(),
        "<h1>StA-Statusbericht</h1>\n",
        "<p>Umfang: %s%s</p>\n" % (
            html.escape(scope),
            (" · Zeitraum: " + html.escape(period_label)) if period_label else ""),
    ]
    for title, rows in _sections(stats):
        parts.append("<h2>%s</h2>\n<table>\n" % html.escape(title))
        if not rows:
            parts.append("<tr><td><em>keine Daten</em></td></tr>\n")
        for k, v in rows:
            parts.append("<tr><td>%s</td><td>%s</td></tr>\n"
                         % (html.escape(str(k)), html.escape(str(v))))
        parts.append("</table>\n")
    parts.append(env.footer_html(digest))
    parts.append("</body>\n</html>\n")
    return "".join(parts)


# -- PDF (reportlab, lazy) -----------------------------------------------------

def build_status_report_pdf(stats: Dict[str, Any], context,
                            *, period_label: Optional[str] = None) -> bytes:
    """Status-Bericht als PDF (reportlab/platypus). Fehlt reportlab -> Unavailable."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)
        import io
    except ImportError as exc:  # pragma: no cover - Umgebungsrandfall
        raise StatusReportUnavailable(str(exc)) from exc

    env = ExportEnvelope(context)
    digest = stats_digest(stats)
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=8,
                           textColor=colors.HexColor("#555555"))

    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))

    story = []
    story.append(Paragraph(esc(context.klassifikation), small))
    story.append(Paragraph("StA-Statusbericht", styles["Title"]))
    scope = "Alle Fälle" if stats.get("scope") != "eigene" else "Eigene Fälle"
    meta = "Behörde: %s · Aktenzeichen: %s · Umfang: %s" % (
        esc(context.behoerde), esc(context.aktenzeichen), esc(scope))
    if period_label:
        meta += " · Zeitraum: " + esc(period_label)
    story.append(Paragraph(meta, small))
    story.append(Spacer(1, 0.4 * cm))

    tstyle = TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ])
    for title, rows in _sections(stats):
        story.append(Paragraph(esc(title), styles["Heading2"]))
        data = [["Kennzahl", "Wert"]]
        if rows:
            data += [[esc(k), esc(v)] for k, v in rows]
        else:
            data += [["keine Daten", ""]]
        tbl = Table(data, colWidths=[11 * cm, 4 * cm])
        tbl.setStyle(tstyle)
        story.append(tbl)
        story.append(Spacer(1, 0.3 * cm))

    story.append(Spacer(1, 0.3 * cm))
    for line in env.erzeugungsvermerk_lines():
        story.append(Paragraph(esc(line), small))
    story.append(Paragraph("Prüfsumme Kennzahlen (SHA-256): %s" % digest, small))

    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title="StA-Statusbericht").build(story)
    return buf.getvalue()
