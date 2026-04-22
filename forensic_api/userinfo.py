# =============================================================================
# forensic_api/userinfo.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Nutzerinfo-Tab
# =============================================================================
# Zweck:
#   Endpunkt GET /_forensic/userinfo — Auslieferung des Nutzerinfo-Tabs.
#
# Build 031-B: Komplette Überarbeitung.
#   Vorher: Abhängigkeit von fdb.static_pages (Tabelle existiert nicht →
#           immer HTTP 503). Kein Nutzerdaten-Anzeige möglich.
#   Jetzt:  Seite wird direkt aus verfügbaren DB-Daten gerendert:
#             - forensic_meta: user_id, username, domainname, schema_version
#             - scrape_targets: Post-, PM-, Forum-Zähler
#             - evidence_db:    Annotationszähler, letzter Eintrag
#           Kein statischer BLOB erforderlich. Immer aufrufbar.
#
# Build 052: Sperrstatus-Banner für wiederhergestellte Konten.
#   Liest user_is_restricted und user_original_group aus forensic_meta.
#   Zeigt blauen Infokasten wenn user_is_restricted='1'.
#   Beleg: Bauplan Baustelle4 v0.3 Build 004, §7.0; Projektgespräch 2026-04-22, OP-30.
#
# Forensische Relevanz:
#   Alle angezeigten Daten stammen aus READ-ONLY-Quellen.
#   Keine Schreibzugriffe — forensische Integrität gewahrt.
#
# Version: v0.1.0 · Build: 052 · 2026-04-22
# =============================================================================

from __future__ import annotations

import html as html_module
import sqlite3
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# Kategorien-Labels für die Annotationsanzeige
_CAT_LABELS = {
    "CAT_PERSON":   "👤 Persönliche Merkmale",
    "CAT_LOCATION": "📍 Ortsangaben",
    "CAT_176":      "⚖️ §§ 176, 176a StGB",
    "CAT_184":      "🔴 §§ 184b, 184c StGB",
    "CAT_VICTIM":   "🛡️ Hinweise auf Opfer",
    "CAT_OTHER":    "📎 Sonstige Relevanz",
}

# Gruppen-IDs die als Sperrgruppen gelten — für Gruppenname-Anzeige im Banner.
# Beleg: Analyse groups-Tabelle, Projektgespräch 2026-04-22.
_RESTRICTED_GROUP_NAMES: dict[int, str] = {
    30: "Archive",
    32: "Suspended",
    39: "Muted",
    43: "Inactive",
    46: "Delete",
    47: "Troll_autodetect",
}


class UserinfoEndpoint:
    """
    Endpunkt GET /_forensic/userinfo

    Liefert eine vollständige Nutzerinfo-Seite aus forensic_meta,
    scrape_targets und evidence_db. Kein statischer BLOB erforderlich.
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

    def handle(self, handler: "ForensicRequestHandler") -> None:
        user_id  = self._context.user_id
        username = self._context.username or f"uid_{user_id}"

        # Alle Daten sammeln
        meta       = self._load_meta()
        stats      = self._load_scrape_stats()
        ann_counts = self._load_annotation_counts()
        last_ann   = self._load_last_annotation()
        page_count = self._bundle.forensic.page_count()

        page_html = self._render(
            user_id, username, meta, stats, ann_counts, last_ann, page_count
        )
        body = page_html.encode("utf-8")
        handler.send_response_body(200, body, content_type="text/html; charset=utf-8")
        logger.debug("/_forensic/userinfo ausgeliefert: user_id=%d", user_id)

    # ------------------------------------------------------------------
    # Daten laden
    # ------------------------------------------------------------------

    def _load_meta(self) -> dict:
        """
        Liest relevante Schlüssel aus fdb.forensic_meta.

        Neu Build 052: user_is_restricted und user_original_group.
        Beleg: Projektgespräch 2026-04-22, OP-30.
        """
        keys = (
            "schema_version", "domainname", "protocol",
            "created_at", "scraper_version",
            # Sperrstatus — Beleg: forensic_db_writer.py Build 012, OP-30
            "user_is_restricted", "user_original_group",
        )
        result = {}
        for k in keys:
            result[k] = self._bundle.forensic.get_meta(k)
        return result

    def _load_scrape_stats(self) -> dict:
        """
        Zählt Posts, PMs, Foren und Seiten aus fdb.scrape_targets.
        Gibt Dict mit Zählern zurück; bei Fehler alle Zähler 0.
        """
        stats = {
            "posts":      0,
            "pm_posts":   0,
            "forums":     0,
            "topics":     0,
            "thanks":     0,
        }
        try:
            con: sqlite3.Connection = self._bundle.forensic._con
            rows = con.execute(
                """
                SELECT
                  COUNT(DISTINCT post_id)       AS posts,
                  COUNT(DISTINCT pm_post_id)    AS pm_posts,
                  COUNT(DISTINCT forum_id)      AS forums,
                  COUNT(DISTINCT topic_id)      AS topics,
                  COUNT(DISTINCT thanks_post_id) AS thanks
                FROM fdb.scrape_targets
                WHERE scrape_context IN ('user', 'actor')
                """
            ).fetchone()
            if rows:
                stats["posts"]    = int(rows["posts"]    or 0)
                stats["pm_posts"] = int(rows["pm_posts"] or 0)
                stats["forums"]   = int(rows["forums"]   or 0)
                stats["topics"]   = int(rows["topics"]   or 0)
                stats["thanks"]   = int(rows["thanks"]   or 0)
        except Exception as exc:
            logger.warning("_load_scrape_stats fehlgeschlagen: %s", exc)
        return stats

    def _load_annotation_counts(self) -> dict:
        """Liest Annotationszähler je Kategorie aus evidence_db."""
        try:
            return self._bundle.evidence.get_annotation_counts_by_category()
        except Exception as exc:
            logger.warning("_load_annotation_counts fehlgeschlagen: %s", exc)
            return {}

    def _load_last_annotation(self) -> "dict | None":
        """Liest Info zur letzten Annotation aus evidence_db."""
        try:
            return self._bundle.evidence.get_last_annotation_info()
        except Exception as exc:
            logger.warning("_load_last_annotation fehlgeschlagen: %s", exc)
            return None

    # ------------------------------------------------------------------
    # HTML-Rendering
    # ------------------------------------------------------------------

    def _render(
        self,
        user_id: int,
        username: str,
        meta: dict,
        stats: dict,
        ann_counts: dict,
        last_ann: "dict | None",
        page_count: int,
    ) -> str:
        e = html_module.escape
        u = e(username)
        domain = e(meta.get("domainname") or "—")

        # Sperrstatus-Banner berechnen
        # Beleg: Bauplan Baustelle4 v0.3 Build 004 §7.0, Projektgespräch 2026-04-22, OP-30.
        is_restricted  = meta.get("user_is_restricted") == "1"
        orig_group_raw = meta.get("user_original_group") or ""
        restricted_banner_html = ""
        if is_restricted:
            # Gruppenname aus bekannter Mapping-Tabelle oder ID als Fallback
            try:
                orig_group_id = int(orig_group_raw) if orig_group_raw else None
            except ValueError:
                orig_group_id = None

            if orig_group_id is not None:
                group_name = _RESTRICTED_GROUP_NAMES.get(
                    orig_group_id,
                    f"Unbekannte Gruppe"
                )
                group_display = e(f"{group_name} (ID: {orig_group_id})")
            else:
                group_display = "unbekannt"

            restricted_banner_html = (
                f'<div class="ui-restricted-banner" role="note" '
                f'aria-label="Gesperrtes Konto">'
                f'<span class="ui-restricted-banner__icon">ℹ</span>'
                f'<div>'
                f'<strong>Dieses Benutzerkonto existiert nicht mehr.</strong> '
                f'Der Zugriff wurde mit forensischen Mitteln wiederhergestellt.'
                f'<div class="ui-restricted-banner__detail">'
                f'Ursprüngliche Gruppe: {group_display}'
                f'</div>'
                f'</div>'
                f'</div>'
            )
            logger.debug(
                "/_forensic/userinfo: Sperrstatus-Banner aktiv für user_id=%d "
                "(original_group=%s).",
                user_id, orig_group_raw or "unbekannt"
            )

        # Annotationstabelle
        ann_rows = ""
        ann_total = 0
        for cat_id, label in _CAT_LABELS.items():
            cnt = ann_counts.get(cat_id, 0)
            ann_total += cnt
            ann_rows += (
                f'<tr><td>{e(label)}</td>'
                f'<td class="ui-num">{cnt}</td></tr>\n'
            )

        last_ann_html = "—"
        if last_ann:
            import datetime
            ts = last_ann.get("ts", 0)
            dt = datetime.datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
            inv = e(last_ann.get("investigator") or "—")
            last_ann_html = f"{dt} · {inv}"

        return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Nutzerinfo · {u} · ID: {user_id}</title>
  <link rel="stylesheet" href="/_forensic/userinfo.css">
  <style>
    body {{ font-family: "Segoe UI", Arial, sans-serif; background: #f4f6fa;
            color: #1a1f2e; margin: 0; padding: 0; }}
    .ui-header {{ background: #1a1f2e; color: #c8d0e8; padding: 18px 28px;
                  display: flex; align-items: center; gap: 16px; }}
    .ui-header h1 {{ margin: 0; font-size: 18px; font-weight: 700; }}
    .ui-header .ui-uid {{ font-size: 12px; color: #4f8ef7; font-family: monospace; }}
    .ui-body {{ padding: 24px 28px; display: grid;
                grid-template-columns: 1fr 1fr; gap: 20px; max-width: 1100px; }}
    .ui-card {{ background: #fff; border: 1px solid #d0d8e8;
                border-radius: 6px; padding: 16px 20px; }}
    .ui-card h2 {{ font-size: 13px; font-weight: 700; color: #4f8ef7;
                   text-transform: uppercase; letter-spacing: .05em;
                   margin: 0 0 12px 0; border-bottom: 1px solid #e8edf4;
                   padding-bottom: 8px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    td {{ padding: 5px 4px; border-bottom: 1px solid #f0f2f8; }}
    td.ui-label {{ color: #5a6a8a; width: 55%; }}
    td.ui-num {{ text-align: right; font-weight: 700; font-family: monospace;
                 font-size: 14px; color: #1a1f2e; }}
    td.ui-val {{ font-family: monospace; font-size: 12px; }}
    .ui-total {{ font-size: 13px; font-weight: 700; margin-top: 10px;
                 text-align: right; color: #1a1f2e; }}
    .ui-badge {{ display: inline-block; background: #e8f0fe; color: #1a56db;
                 border-radius: 3px; padding: 2px 7px; font-size: 11px;
                 font-weight: 700; font-family: monospace; }}
    .ui-domain {{ font-size: 11px; color: #7a8aaa; font-family: monospace;
                  word-break: break-all; }}
    .ui-footer {{ padding: 12px 28px; font-size: 11px; color: #9aa0b8;
                  border-top: 1px solid #e0e4f0; margin-top: 8px; }}
    /* Sperrstatus-Banner — Beleg: Bauplan B4 v0.3 Build 004 §7.0, OP-30 */
    .ui-restricted-banner {{
      display: flex; align-items: flex-start; gap: 12px;
      background: #e8f4fc; border: 1px solid #1a6fa8;
      border-left: 4px solid #1a6fa8;
      border-radius: 4px; padding: 12px 20px;
      margin: 0 28px 0 28px; font-size: 13px; color: #0d3a5c;
    }}
    .ui-restricted-banner__icon {{
      font-size: 18px; color: #1a6fa8; flex-shrink: 0; line-height: 1.3;
    }}
    .ui-restricted-banner__detail {{
      font-size: 11px; color: #3a6080; margin-top: 4px;
      font-family: monospace;
    }}
  </style>
</head>
<body>
  <div class="ui-header">
    <div>
      <div class="ui-uid">Benutzer-ID: {user_id}</div>
      <h1>{u}</h1>
      <div class="ui-domain">{domain}</div>
    </div>
  </div>

  {restricted_banner_html}

  <div class="ui-body">

    <!-- Aktivitätsstatistik -->
    <div class="ui-card">
      <h2>Aktivität im Forum</h2>
      <table>
        <tr><td class="ui-label">Beiträge (Posts)</td>
            <td class="ui-num">{stats["posts"]}</td></tr>
        <tr><td class="ui-label">Private Nachrichten</td>
            <td class="ui-num">{stats["pm_posts"]}</td></tr>
        <tr><td class="ui-label">Themen (Topics)</td>
            <td class="ui-num">{stats["topics"]}</td></tr>
        <tr><td class="ui-label">Unterforen</td>
            <td class="ui-num">{stats["forums"]}</td></tr>
        <tr><td class="ui-label">Danksagungen</td>
            <td class="ui-num">{stats["thanks"]}</td></tr>
        <tr><td class="ui-label">Gesicherte Seiten</td>
            <td class="ui-num">{page_count}</td></tr>
      </table>
    </div>

    <!-- Annotationsstand -->
    <div class="ui-card">
      <h2>Ermittlungsstand · Annotationen</h2>
      <table>
        {ann_rows}
      </table>
      <div class="ui-total">Gesamt: {ann_total}</div>
      <table style="margin-top:12px">
        <tr><td class="ui-label">Letzte Annotation</td>
            <td class="ui-val">{last_ann_html}</td></tr>
      </table>
    </div>

    <!-- Technische Metadaten -->
    <div class="ui-card">
      <h2>Forensische Metadaten</h2>
      <table>
        <tr><td class="ui-label">Schema-Version</td>
            <td class="ui-val">{e(meta.get("schema_version") or "—")}</td></tr>
        <tr><td class="ui-label">Protokoll</td>
            <td class="ui-val">{e(meta.get("protocol") or "—")}</td></tr>
        <tr><td class="ui-label">Domain</td>
            <td class="ui-val">{e(meta.get("domainname") or "—")}</td></tr>
        <tr><td class="ui-label">Scraper-Version</td>
            <td class="ui-val">{e(meta.get("scraper_version") or "—")}</td></tr>
      </table>
    </div>

    <!-- Dynamischer Block (userinfo.js) -->
    <div class="ui-card" id="userinfo-dynamic" aria-live="polite">
      <h2>Ermittlungskoordination</h2>
      <span style="color:#9aa0b8;font-size:12px">Lade…</span>
    </div>

  </div>

  <!-- Berichtsreiter: wird von loadDynamicBlocks() befuellt (AP-E4).
       Erscheint oberhalb des langen Forum-Inhalts fuer schnellen Zugriff.
       Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19 -->
  <div id="userinfo-report-readonly"></div>

  <div id="userinfo-static">
    <p style="color:#9aa0b8;font-size:12px;padding:12px 28px">
      Lade forensische Nutzerdaten…</p>
  </div>

  <div class="ui-footer">
    Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH ·
    Benutzer-ID: {user_id} · {u}
  </div>

  <script src="/_forensic/userinfo.js" defer></script>
</body>
</html>"""

