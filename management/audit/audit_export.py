# =============================================================================
# management/audit/audit_export.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Audit-Explorer (AP-2E)
# =============================================================================
# Zweck (Idee 24 — gerichtsfester Export):
#   Rendert eine (gefilterte) Audit-Treffermenge als SELF-CONTAINED HTML-Seite,
#   umschlossen vom AP-2B-ExportEnvelope: Aktenkopf + Klassifikation +
#   Erzeugungsvermerk (Ersteller/Build/verify_chain-Ergebnis + Ketten-Spitze) +
#   SHA-256-Pruefsumme des NUTZINHALTS. Der Export zertifiziert damit SELBST die
#   Belegkette, aus der er stammt (Beleg export/export_envelope.py).
#
#   REINE RENDER-FUNKTION (Muster support_overview/html_export.py): keine DB,
#   keine Uhr, kein Netz — Daten und Rahmen kommen vom Aufrufer. Damit voll
#   testbar und deterministisch.
#
# SICHERHEIT (XSS): ALLE variablen Werte (Payload, Ziel-Ids, Akteursnamen aus
#   multilingualen Quellen) werden mit html.escape() entschaerft; UTF-8 bleibt.
#
# Version: v0.7.467 · Build: 467 · 2026-07-20
# =============================================================================

import html
import time
from typing import Any, Dict, List, Optional, Sequence

_DOC_HEAD = (
    "<!DOCTYPE html>\n<html lang=\"de\">\n<head>\n"
    "<meta charset=\"utf-8\">\n"
    "<title>Audit-/Revisions-Auszug</title>\n"
    "<style>\n"
    "  body { font-family: system-ui, sans-serif; color: #1c1e21; margin: 24px; }\n"
    "  .aiw-klass { font-weight: 700; color: #922b21; letter-spacing: .04em; }\n"
    "  .aiw-export-head h1 { margin: 6px 0; font-size: 20px; }\n"
    "  .aiw-akte { color: #606770; font-size: 13px; }\n"
    "  table { border-collapse: collapse; width: 100%; margin-top: 14px;\n"
    "          font-size: 12px; }\n"
    "  th, td { border: 1px solid #ddd; padding: 5px 7px; text-align: left;\n"
    "           vertical-align: top; }\n"
    "  th { background: #f0f2f4; }\n"
    "  td.payload code { white-space: pre-wrap; word-break: break-word; }\n"
    "  .aiw-export-foot { margin-top: 18px; border-top: 2px solid #333;\n"
    "                     padding-top: 8px; font-size: 12px; color: #333; }\n"
    "  .aiw-erzeugungsvermerk { list-style: none; padding-left: 0; }\n"
    "  .aiw-filter { color: #606770; font-size: 12px; margin: 8px 0; }\n"
    "</style>\n</head>\n<body>\n"
)
_DOC_TAIL = "\n</body>\n</html>\n"

_TITLE = "Audit-/Revisions-Auszug"


def _fmt_ts(ts: Any) -> str:
    """Epoch -> deterministischer UTC-Zeitstempel (kein TZ-Zweifel im Gericht)."""
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(int(ts)))
    except (TypeError, ValueError, OSError):
        return str(ts)


def _actor_cell(row: Dict[str, Any]) -> str:
    name = row.get("actor_name")
    user = row.get("actor_username")
    aid = row.get("actor_id")
    if name and user:
        return "%s (%s)" % (name, user)
    if user:
        return str(user)
    if aid is not None:
        return "id=%s" % aid
    return "—"


def _body_html(rows: Sequence[Dict[str, Any]],
               filter_summary: Optional[str], total: Optional[int]) -> str:
    """Der NUTZINHALT (ueber den die Pruefsumme rechnet): Filtervermerk + Tabelle."""
    parts: List[str] = ['<section class="aiw-export-body">\n']

    fs = filter_summary or "ohne Filter (alle Eintraege)"
    cnt = ("%d ausgewiesen" % len(rows))
    if total is not None and total != len(rows):
        cnt += " von %d Treffern (Auszug)" % total
    parts.append('<p class="aiw-filter">Filter: %s — %s.</p>\n'
                 % (html.escape(fs), cnt))

    parts.append("<table>\n<thead><tr>"
                 "<th>seq</th><th>Zeit (UTC)</th><th>Akteur</th>"
                 "<th>Ereignis</th><th>Ziel</th><th>Payload</th>"
                 "<th>row_hash</th></tr></thead>\n<tbody>\n")
    for r in rows:
        ziel = r.get("target_type") or ""
        if r.get("target_id") not in (None, ""):
            ziel = ("%s/%s" % (ziel, r.get("target_id"))) if ziel \
                else str(r.get("target_id"))
        parts.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
            "<td class=\"payload\"><code>%s</code></td><td>%s</td></tr>\n"
            % (html.escape(str(r.get("seq", ""))),
               html.escape(_fmt_ts(r.get("ts"))),
               html.escape(_actor_cell(r)),
               html.escape(str(r.get("event_type", ""))),
               html.escape(ziel),
               html.escape(str(r.get("content", "") or "")),
               html.escape(str(r.get("row_hash", "") or ""))))
    parts.append("</tbody>\n</table>\n</section>\n")
    return "".join(parts)


def render_html(
    rows: Sequence[Dict[str, Any]], envelope, *,
    titel: str = _TITLE, filter_summary: Optional[str] = None,
    total: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Baut die gerichtsfeste HTML-Seite. -> {'html', 'digest'}.
    Die Pruefsumme deckt den NUTZINHALT (Tabelle) ab — unabhaengig vom Rahmen
    nachrechenbar (Beleg ExportEnvelope.footer_html).
    """
    body = _body_html(rows, filter_summary, total)
    digest = envelope.checksum_text(body)
    page = (_DOC_HEAD
            + envelope.header_html(titel)
            + body
            + envelope.footer_html(digest)
            + _DOC_TAIL)
    return {"html": page, "digest": digest}
