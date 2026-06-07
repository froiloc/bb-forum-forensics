# =============================================================================
# forensic_api/report.py
# IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
# =============================================================================
# Zweck:
#   Endpunkt /_forensic/report — GET und POST (Fenster 3: Bericht-Editor).
#
# GET ohne Parameter:
#   Liefert die Editor-Shell-HTML (report_editor.js wird eingebunden).
#
# GET mit ?format=json:
#   Liefert alle Berichte mit ihren Bloecken als JSON (B6-Schema).
#   Schema: { "reports": [...], "paragraphs": [...], "lock": {...} | null }
#   Benoetigt von: loadReadonlyReport() in userinfo.js (Fenster 2, Read-Only-Reiter)
#                  und report_editor.js (Fenster 3, Block-Liste).
#
# POST — Aktionen:
#   acquire_lock, release_lock, heartbeat, resume_lock,
#   request_takeover, respond_takeover   (Lock-System v2 — unveraendert)
#   add_paragraph     -> Neuen Freitext-Paragraph anlegen
#   update_paragraph  -> Paragraph-Inhalt aktualisieren (nur Eigentuemer)
#   set_status        -> Paragraph-Status aendern (lifecycle §2.3)
#   reorder           -> Sortierungsreihenfolge aendern
#   add_comment       -> Kommentar zu fremdem Paragraph
#   resolve_comment   -> Kommentar-Status aendern (One-Way)
#   add_anchor        -> Beweisanker Paragraph <-> Annotation
#
# Layout Fenster 3 (§4.1 Bauplan B6 v0.3):
#   height: 100vh, display: flex, zweispaltig:
#   linke Spalte ~65% (Block-Liste), rechte Spalte ~35% (Annotation-Sidebar)
#
# CSP fuer Editorfenster:
#   script-src 'unsafe-inline' erlaubt (report_editor.js-Anforderung).
#   Beleg: AP-E1, Projektgespraech 2026-04-19
#
# Datenbankzugriff:
#   evidence_<uid>.db (READ-WRITE) — Berichte, Bloecke, Locks
#
# Changelog:
#   Build 012: Erstimplementierung mit report_paragraphs-Modell.
#   Build 043 (AP-E1): Umgeschrieben auf Editor.js-Block-Modell.
#   Build 089 (B6): evidence_db auf B6-Schema umgestellt.
#   Build 090 (B6 Phase 4):
#   Build 158 (B6 Bug 2.9): anchor_ids je Block in GET-Response ergaenzt.
#     - _EDITOR_HTML: Fenster-3-Grundgeruest mit 100vh/flex-Layout (§4.1).
#     - GET ?format=json: liefert jetzt paragraphs statt blocks (B6-Schema).
#     - POST: fuenf neue schreibende Aktionen (add_paragraph, update_paragraph,
#       set_status, reorder, add_comment, resolve_comment, add_anchor).
#     - report.js ersetzt editor.js als Fenster-3-Modul.
#     - report.css als dediziertes Stylesheet fuer Fenster 3.
#     Beleg: Bauplan B6 v0.3 §4, Ausdefinitionsgespraech 2026-05-05
#   Build 100 (B6 Phase 2): report_editor.js ersetzt report.js im HTML-Template.
#     Beleg: Bauplan B6 v0.5 §4.1, Projektgespraech 2026-05-06
#   Build 101 (B6 Phase 3): Support-Sidebar Akkordeon-Skelett im HTML-Template.
#     aside#report-annotation-sidebar ersetzt durch aside#support-sidebar mit
#     vier .support-accordion-section-Elementen (Bausteine, Annotationen,
#     Formular, Kommentare). Empty-States und ARIA-Attribute gesetzt.
#     Beleg: Bauplan B6 v0.5 §4.4, Projektgespraech 2026-05-06
#   Build 102 (B6 Phase 4): Block-API-Umbau und Modularisierung.
#     GET ?format=json: "paragraphs" -> "blocks", get_blocks_for_report(),
#       get_comments_for_block(). Felder angepasst (block_type, block_data
#       statt content/status/omitted_*).
#     POST-Aktionen: add_paragraph/update_paragraph/set_status ersetzt durch
#       save_block/update_block/delete_block (Block-API v0.5).
#     add_comment/resolve_comment ausgelagert in editor_comment.py.
#     Beleg: Bauplan B6 v0.5 §5, Projektgespraech 2026-05-06
#
#   Build 109 (Fix): editor.bundle.js in HTML-Template eingebunden (window.EditorJS).
#              Veraltete Buttons btn-add-paragraph, btn-insert-module ersetzt
#              durch btn-new-report-header (delegiert an btn-new-report).
#              Beleg: Projektgespraech 2026-05-07
#
# Build 110 (Fix): IIFE-Wrapper um alle userinfo/*.js eingeführt — behebt
#              SyntaxError durch let/const-Kollisionen im globalen Scope.
#              DEV-Logging (_dbg) in alle JS-Dateien eingeführt.
#              Beleg: Projektgespraech 2026-05-07
#
# Build 111 (Fix): _initSidebarAccordion() direkt in initEditorModule() aufgerufen
#              (nicht mehr ausschliesslich in EditorJS onReady). Akkordeon-Listener
#              sind jetzt ohne aktiven Bericht aktiv.
#              btn-new-report-header aus Action-Bar entfernt (redundant).
#              Beleg: Projektgespraech 2026-05-07
#
# Version: v0.6.282 · Build: 282 · 2026-06-07
# Changelog Build 280 (2026-06-07):
#   - _action_open_report: o.block_id → o["block_id"] in order_map-Comprehension.
#     get_block_order_for_report() gibt list[dict] zurueck, kein Objekt mit Attributen.
#     Beleg: Server-Log 'dict object has no attribute block_id', Projektgespraech 2026-06-07
# Changelog Build 249 (Paket 6 — Layer-3-Aktionen open_report / new_report):
#   - _action_open_report(): OPENING-Aktion; schreibt report_opened-Eintrag,
#     bereinigt Queue, liefert Blöcke zurück.
#   - _action_new_report(): NEW-Aktion; atomare Bericht+Lock-Transaktion
#     (SLA Punkt 7), schreibt report_opened-Eintrag.
#   Beleg: Layer 3 States OPENING / NEW, SLA Punkt 7, Paket 6
# =============================================================================

from __future__ import annotations

import html as html_module
import json
import sqlite3
import uuid
from typing import TYPE_CHECKING

from core.logger import get_logger

if TYPE_CHECKING:
    from server.http_server import ForensicRequestHandler
    from db.connection_manager import DatabaseBundle
    from core.config_loader import ConfigLoader
    from core.mode_resolver import ResolvedContext

logger = get_logger(__name__)

# HTML-Rahmen fuer Fenster 3 (Bericht-Editor, B6 Phase 4).
# Layout: height:100vh, display:flex, zweispaltig (~65% Editor / ~35% Sidebar).
# Beleg: Bauplan B6 v0.3 §4.1, §4.2, Ausdefinitionsgespraech 2026-05-05
_EDITOR_HTML = """\
<!DOCTYPE html>
<html lang="de">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Bericht \u00b7 {subject} \u00b7 ID: {user_id}</title>
    <link rel="stylesheet" href="/_forensic/userinfo.css">
    <link rel="stylesheet" href="/_forensic/report.css">
  </head>
  <body id="report-editor-body"
        data-user-id="{user_id}"
        data-username="{username}"
        data-subject="{subject}"
        data-autosave-debounce-ms="{autosave_debounce_ms}">

    <!-- Fixierte Aktionsleiste (§4.2 Bauplan B6 v0.3) -->
    <header id="report-action-bar">
      <div id="report-action-bar-title">
        📄 Bericht \u00b7 <span id="report-current-title">{investigator} / {subject} (ID: {user_id})</span>
      </div>
      <!-- Bug 1.10 Fix Build 121: editor-report-title als div zwischen title und buttons.
           War bisher als span NACH den Buttons platziert und drückte die Leiste nach unten.
           Beleg: Bugfix Build 121, Projektgespraech 2026-05-08 -->
      <div id="editor-report-title"></div>
      <div id="report-action-bar-buttons">
        <!-- Build 111: btn-new-report-header entfernt.
             "Neuer Bericht" befindet sich bereits im report-selector-container.
             Beleg: Projektgespraech 2026-05-07 -->
        <!-- Bug 2.40/2.43 Absicherung Build 136: Manueller Speichern-Button.
             Wird aktiv sobald ein Bericht geladen ist (disabled -> enabled durch JS).
             Beleg: Bugfix Build 136, Projektgespraech 2026-05-09 -->
        <button class="report-btn" id="btn-save-now"
          title="Bericht jetzt speichern (Strg+S)" disabled>
          💾 Speichern
        </button>
        <button class="report-btn" id="btn-refresh-placeholders"
          title="Automatische Platzhalter aktualisieren" disabled>
          🔄 Aktualisieren
        </button>
        <!-- Bug 1.9 Fix Build 121: ✎ → 🖶 (Drucker-Symbol).
             Beleg: Bugfix Build 121, Projektgespraech 2026-05-08 -->
        <button class="report-btn" id="btn-print"
          title="Bericht drucken" disabled>
          🖶 Drucken
        </button>
        <div class="report-export-wrap">
          <button class="report-btn" id="btn-export"
            title="Bericht exportieren" disabled>
            &#x2b07; Export &#x25be;
          </button>
          <div id="export-dropdown" class="report-export-dropdown" style="display:none">
            <button class="report-export-item" data-export-format="html">
              &#x1F4C4; HTML-Dokument
            </button>
            <button class="report-export-item" data-export-format="docx">
              &#x1F4DD; Word-Dokument (.docx)
            </button>
            <button class="report-export-item" data-export-format="sqlite">
              &#x1F5FA; SQLite3-Fallakte (.db)
            </button>
          </div>
        </div>
        <span id="report-lock-indicator" class="report-lock-indicator report-lock-none"
          title="Lock-Status">&#x1f513;</span>
        <!-- Lock-Status: von userinfo.js beschrieben (Build 113) -->
        <span id="report-lock-status" class="lock-status lock-none"
          title="Editor-Lock-Status" style="font-size:11px"></span>
        <span id="editor-save-indicator"
          class="save-indicator save-indicator--idle" title="Kein Speichern ausstehend">🖫</span>
      </div>
    </header>

    <!-- Zweispaltiger Arbeitsbereich (§4.1, §4.3, §4.7) -->
    <div id="report-workspace">

      <!-- Linke Spalte: Paragraph-Liste (~65%) -->
      <main id="report-main-col">
        <!-- Berichtsauswahl -->
        <div id="report-selector-container"></div>
        <!-- Status-Meldungen -->
        <div id="report-status-msg"></div>
        <!-- Editor-Bereich: EditorJS-Holder direkt in report-main-col.
             Beleg: Bauplan B6 §4.3, Build 113, Projektgespraech 2026-05-07 -->
        <div id="editorjs-holder" class="editorjs-holder"></div>
        <!-- Frozen-Overlay (BroadcastChannel-Schutz, §4.6) -->
        <div id="report-frozen-overlay" style="display:none">
          <div class="report-frozen-inner">
            <strong>Dieser Editor ist bereits in einem anderen Fenster ge\u00f6ffnet.</strong><br>
            Bitte wechseln Sie zum bestehenden Fenster.
            <br><br>
            <button class="report-btn" id="btn-focus-existing">
              Zum bestehenden Fenster wechseln
            </button>
          </div>
        </div>
      </main>

      <!-- Schiebebalken zwischen main und aside (Bug 1.11 Fix) -->
      <!-- Beleg: Projektgespraech 2026-05-11 -->
      <div id="col-resizer" aria-hidden="true">
        <div id="col-resizer-handle"></div>
      </div>

      <!-- Rechte Spalte: Support-Sidebar mit vierstufigem Akkordeon (~35%) -->
      <!-- Beleg: Bauplan B6 v0.5 §4.4, Projektgespraech 2026-05-06 -->
      <aside id="support-sidebar" aria-label="Support-Sidebar">

        <!-- Abschnitt 1: Bausteine (Standard: aufgeklappt) -->
        <section class="support-accordion-section support-accordion-section--open"
                 data-accordion="blocks">
          <button class="support-accordion-toggle" type="button"
                  aria-expanded="true" aria-controls="accordion-body-blocks">
            <span class="support-accordion-icon" aria-hidden="true">📦</span>
            Bausteine
            <span class="support-accordion-chevron" aria-hidden="true">&#x25be;</span>
          </button>
          <div id="accordion-body-blocks" class="support-accordion-body"
               role="region" aria-label="Bausteine">
            <!-- Inhalt wird von module_panel.js/_refreshModulePanel() befuellt (Phase 7) -->
            <!-- Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06 -->
            <p class="support-accordion-empty" id="blocks-loading-state">
              Bausteine werden geladen\u2026
            </p>
          </div>
        </section>

        <!-- Abschnitt 2: Annotationen -->
        <section class="support-accordion-section"
                 data-accordion="annotations">
          <button class="support-accordion-toggle" type="button"
                  aria-expanded="false" aria-controls="accordion-body-annotations">
            <span class="support-accordion-icon" aria-hidden="true">🔍</span>
            Annotationen
            <span class="support-accordion-chevron" aria-hidden="true">&#x25be;</span>
          </button>
          <div id="accordion-body-annotations" class="support-accordion-body"
               role="region" aria-label="Annotationen" hidden>
            <!-- Inhalt wird von annotation_sidebar.js/_refreshAnnotationSidebar() befuellt (Phase 8) -->
            <!-- Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06 -->
            <p class="support-accordion-empty" id="annotations-loading-state">
              Annotationen werden geladen\u2026
            </p>
          </div>
        </section>

        <!-- Abschnitt 3: Formular (Platzhalter-Eingabe) -->
        <section class="support-accordion-section"
                 data-accordion="form">
          <button class="support-accordion-toggle" type="button"
                  aria-expanded="false" aria-controls="accordion-body-form">
            <span class="support-accordion-icon" aria-hidden="true">📝</span>
            Formular
            <span class="support-accordion-chevron" aria-hidden="true">&#x25be;</span>
          </button>
          <div id="accordion-body-form" class="support-accordion-body"
               role="region" aria-label="Platzhalter-Formular" hidden>
            <!-- Inhalt wird von placeholder_wizard.js befuellt (Phase 6) -->
            <p class="support-accordion-empty">
              Kein Bericht ge&#xf6;ffnet.
            </p>
          </div>
        </section>

        <!-- Abschnitt 4: Kommentare (unten) -->
        <section class="support-accordion-section"
                 data-accordion="comments">
          <button class="support-accordion-toggle" type="button"
                  aria-expanded="false" aria-controls="accordion-body-comments">
            <span class="support-accordion-icon" aria-hidden="true">💬</span>
            Kommentare
            <span class="support-accordion-chevron" aria-hidden="true">&#x25be;</span>
          </button>
          <div id="accordion-body-comments" class="support-accordion-body"
               role="region" aria-label="Kommentare" hidden>
            <!-- Inhalt wird von comment_thread.js befuellt (Phase 4) -->
            <p class="support-accordion-empty" id="comments-empty-state">
              Kein Block ausgew&#xe4;hlt.
            </p>
            <!-- Kommentar-Eingabe (wird von comment_thread.js aktiviert) -->
            <textarea class="comment-input-textarea" rows="3"
                      placeholder="Kommentar verfassen…"
                      aria-label="Neuen Kommentar verfassen"
                      style="display:none"></textarea>
          </div>
        </section>

      </aside>
    </div>

    <!-- Lock-Infrastruktur: report-lock-status und Lock-Buttons werden von
         userinfo.js in #report-action-bar-buttons injiziert (Build 113).
         editorjs-holder lebt in #report-paragraphs-list (report-main-col).
         Beleg: Projektgespraech 2026-05-07 -->
    <div id="report-editor-container" style="display:none"></div>

    <!-- Scripts (Reihenfolge wichtig) -->
    <!-- 0a) Web-Debug-Script (nur wenn --web-debug aktiv, sonst leer).
         Muss vor allen defer-Scripts stehen damit FORENSIC_DEBUG beim
         Parsen der Skripte bereits gesetzt ist.
         Beleg: --web-debug Argument, main.py, Build 255 -->
{web_debug_script}    <!-- 0) editor.bundle.js: Editor.js + Tools (window.EditorJS, window.EditorTools).
         Muss vor report_editor.js geladen werden.
         Beleg: AP-E2, Projektgespraech 2026-05-07 (Build 109) -->
    <script src="/_forensic/static/editor/editor.bundle.js" defer></script>
    <!-- 0b) debug_events.js: Event-Tracing (window._uevt). Muss VOR allen anderen
          B6-Skripten geladen werden, damit _uevt beim Laden der Handler verfuegbar ist.
          Build 200, Projektgespraech 2026-05-17 -->
    <script src="/_forensic/debug_events.js" defer></script>
    <!-- 1a) placeholder_chips.js: Chip-Renderer (vor report.js laden) -->
    <script src="/_forensic/placeholder_chips.js" defer></script>
    <!-- 1b) placeholder_wizard.js: Wizard (nach Chips, vor report.js) -->
    <script src="/_forensic/placeholder_wizard.js" defer></script>
    <!-- 1c) module_panel.js: Modul-Auswahl-Panel -->
    <script src="/_forensic/module_panel.js" defer></script>
    <!-- 1d) annotation_sidebar.js: Annotationsseitenleiste -->
    <script src="/_forensic/annotation_sidebar.js" defer></script>
    <!-- 1e) comment_thread.js: Kommentar-System -->
    <script src="/_forensic/comment_thread.js" defer></script>
    <!-- 1f) report_editor.js: B6-Editor-Modul (umbenannt von editor.js, Build 100) -->
    <script src="/_forensic/report_editor.js" defer></script>
    <!-- 2) Layer-Architektur (Paket 5-9, Build 254). Reihenfolge ist Pflicht.
         Beleg: editor_bootstrap.js, Paket 9 Architekturentscheidung Option C -->
    <!-- 2a) userinfo.js: BroadcastChannel, Fenster 1/2 -->
    <script src="/_forensic/userinfo.js" defer></script>
    <!-- 2b) sse_layer.js: Layer 2 -- SSE-Verbindung -->
    <script src="/_forensic/sse_layer.js" defer></script>
    <!-- 2c) report_layer.js: Layer 3 -- Bericht oeffnen/anlegen -->
    <script src="/_forensic/report_layer.js" defer></script>
    <!-- 2d) lock_layer.js: Layer 4 -- Lock-Verwaltung -->
    <script src="/_forensic/lock_layer.js" defer></script>
    <!-- 2e) document_layer.js: Layer 5 -- Schreiboperationen -->
    <script src="/_forensic/document_layer.js" defer></script>
    <!-- 2f) editor_bootstrap.js: Layer-Instanziierung + Verdrahtung.
             Muss als letztes geladen werden (nach report_editor.js + userinfo.js). -->
    <script src="/_forensic/editor_bootstrap.js" defer></script>
  </body>
</html>"""

# CSP-Header fuer das Editorfenster.
# unsafe-inline und unsafe-eval sind fuer Editor.js erforderlich.
# Beleg: AP-E1, Projektgespraech 2026-04-19
_EDITOR_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self';"
)

_LOCK_REQUIRED = json.dumps(
    {"error": "Lock erforderlich", "code": "LOCK_REQUIRED"},
    ensure_ascii=False,
).encode("utf-8")


def _json_err(msg: str, code: str = "ERROR") -> bytes:
    return json.dumps({"error": msg, "code": code}, ensure_ascii=False).encode("utf-8")


def _json_ok(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def _enrich_blocks_with_cache(blocks_payload: list, cache: dict) -> list:
    """Webt auto:query_id-Eintraege aus dem placeholder_cache in
    placeholder_values_json der Bloecke ein (nur im Response, kein DB-Write).

    Existierende auto:-Werte in placeholder_values_json werden beibehalten
    (gespeicherte Overrides). Nur fehlende auto:-Schluessel werden ergaenzt.
    Macht nichts wenn cache leer ist.

    Beleg: Bugfix-Liste 2.17, Projektgespraech 2026-06-07, Build 287
    """
    if not cache:
        return blocks_payload

    result = []
    for b in blocks_payload:
        pvj = b.get("placeholder_values_json")
        try:
            values = json.loads(pvj) if pvj else {}
        except (json.JSONDecodeError, TypeError):
            values = {}

        changed = False
        for query_id, cached_value in cache.items():
            key = f"auto:{query_id}"
            if key not in values:
                values[key] = cached_value
                changed = True

        if changed:
            b = dict(b)
            b["placeholder_values_json"] = json.dumps(values, ensure_ascii=False)
        result.append(b)
    return result


class ReportEndpoint:
    """
    Endpunkt /_forensic/report — GET und POST (Fenster 3).
    Implementiert B6-Paragraph-basiertes Berichtssystem (Phase 4).
    Beleg: Bauplan B6 v0.3 §4, §5
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
    # GET
    # ------------------------------------------------------------------

    def handle_get(
        self,
        handler: "ForensicRequestHandler",
        params: dict,
    ) -> None:
        fmt = params.get("format", [None])[0]
        if fmt == "json":
            # Bug 2.120 Fix Build 220: report_id aus Query-Parameter lesen.
            # Beleg: Bugfix Build 220, Projektgespraech 2026-05-18
            rid_raw = params.get("report_id", [None])[0]
            requested_report_id = int(rid_raw) if rid_raw else None
            self._handle_get_json(handler, requested_report_id=requested_report_id)
        else:
            self._handle_get_html(handler)

    def _handle_get_html(self, handler: "ForensicRequestHandler") -> None:
        """Liefert die Editor-Shell-HTML mit CSP-Header aus."""
        # context.username = Beschuldigter (fuer Anzeigetitel)
        # context.investigator_username = Ermittler (fuer data-username,
        #   Block-Eigentuemer-Vergleich in report_editor.js)
        # Bug-Fix Build 120: data-username muss den Ermittler enthalten,
        # nicht den Beschuldigten. report_editor.js liest data-username als
        # 'username' und vergleicht damit b.author in _applyOwnershipStyles
        # und _wrapBlock. Wenn dieser Wert der Beschuldigte war, wurden alle
        # Bloecke als fremd markiert und gesperrt.
        # Beleg: Bugfix Build 120, Projektgespraech 2026-05-08
        safe_investigator = html_module.escape(
            self._context.investigator_username
        )
        # Bug 2.70 Fix Build 163: echten Forum-Benutzernamen aus forensic_meta
        # lesen statt uid_<id>-Fallback aus coordinator.db.
        # forensic_db.get_meta('username') -> forensic_meta WHERE key='username'.
        # Beleg: Projektgespraech 2026-05-11
        forum_username: Optional[str] = None
        try:
            raw_uname = self._bundle.forensic.get_meta('username')
            if raw_uname and not raw_uname.startswith('uid_'):
                forum_username = raw_uname
        except Exception:
            pass
        safe_subject = html_module.escape(
            forum_username
            or self._context.username
            or f"uid_{self._context.user_id}"
        )
        autosave_ms = int(
            getattr(self._config, "get", lambda k, d: d)(
                "editor.autosave_debounce_ms", 30000
            )
        )
        web_debug = bool(
            getattr(self._config, "get", lambda k, d: d)("ui.web_debug", False)
        )
        web_debug_script = (
            "    <script>/* --web-debug aktiv */\n"
            "      window.FORENSIC_DEBUG = true;\n"
            "      window.FORENSIC_EVENT_TRACE = true;\n"
            "      console.info('[web-debug] FORENSIC_DEBUG=true, FORENSIC_EVENT_TRACE=true');\n"
            "    </script>\n"
        ) if web_debug else ""

        page_html = _EDITOR_HTML.format(
            username=safe_investigator,
            subject=safe_subject,
            investigator=safe_investigator,
            user_id=self._context.user_id,
            autosave_debounce_ms=autosave_ms,
            web_debug_script=web_debug_script,
        )
        body = page_html.encode("utf-8")
        handler.send_response_body(
            200, body,
            content_type="text/html; charset=utf-8",
            extra_headers={"Content-Security-Policy": _EDITOR_CSP},
        )
        logger.debug(
            "/_forensic/report (HTML) ausgeliefert: user_id=%d",
            self._context.user_id,
        )

    def _handle_get_json(
        self, handler: "ForensicRequestHandler",
        requested_report_id: Optional[int] = None,
    ) -> None:
        """
        Liefert alle Berichte mit ihren Paragraphen als JSON (B6-Schema).

        Schema:
        {
          "reports": [
            {
              "id": N,
              "report_type": "interim"|"final"|"addendum",
              "sequence_nr": N,
              "title": "...",
              "status": "draft"|...,
              "created_by": "...",
              "created_at": N
            }
          ],
          "blocks": [    <- aktiver Bericht (erster draft/submitted-Bericht)
            {
              "block_id": "uuid",
              "report_id": N,
              "author": "...",
              "created_at": N,
              "updated_at": N,
              "block_type": "paragraph"|"header"|...,
              "block_data": "{...}",
              "placeholder_values_json": "{...}"|null,
              "module_id": N|null,
              "comments": [...]
            }
          ],
          "active_report_id": N|null,
          "lock": {"locked_by": "...", "locked_at": N} | null
        }

        Beleg: Bauplan B6 v0.5 §5, B6 Phase 4, Projektgespraech 2026-05-06
        """
        edb     = self._bundle.evidence
        lock    = None  # wird nach active_report-Bestimmung gesetzt
        reports = edb.get_reports()

        # Aktiven Bericht bestimmen: requested_report_id hat Vorrang.
        # Bug 2.120 Fix Build 220: Ohne diesen Check lieferte der Server
        # immer den ersten draft-Bericht, unabhaengig vom report_id-Parameter.
        # Beleg: Bugfix Build 220, Projektgespraech 2026-05-18
        active_report = None
        if requested_report_id is not None:
            active_report = next(
                (r for r in reports if r.id == requested_report_id), None
            )
        if active_report is None:
            for r in reports:
                if r.status in ("draft", "submitted"):
                    active_report = r
                    break
        if active_report is None and reports:
            active_report = reports[0]

        # Lock nach Bestimmung von active_report laden — braucht report_id
        lock = edb.get_lock(active_report.id) if active_report else None

        blocks_payload = []
        if active_report:
            # Beleg: Bauplan B6 v0.5 §5, Phase 4 — Block-API statt Paragraph-API
            blocks = edb.get_blocks_for_report(active_report.id)
            for b in blocks:
                comments = edb.get_comments_for_block(b.block_id)
                # Bug 2.9 Fix Build 158: report_anchors je Block laden und als
                # anchor_ids-Liste mitliefern, damit AnnotationSidebar.showSidebar()
                # die bereits verankerten Annotations-IDs korrekt befuellt.
                # Beleg: Projektgespraech 2026-05-11
                anchors = edb.get_anchors_for_block(b.block_id)
                blocks_payload.append({
                    "block_id":                b.block_id,
                    "report_id":               b.report_id,
                    "author":                  b.author,
                    "created_at":              b.created_at,
                    "updated_at":              b.updated_at,
                    "block_type":              b.block_type,
                    "block_data":              b.block_data,
                    "placeholder_values_json": b.placeholder_values_json,
                    "module_id":               b.module_id,
                    "anchor_ids":              [a.annotation_id for a in anchors],
                    "comments": [
                        {
                            "id":                cm.id,
                            "author":            cm.author,
                            "created_at":        cm.created_at,
                            "comment_text":      cm.comment_text,
                            "suggested_content": cm.suggested_content,
                            "status":            cm.status,
                            "resolved_by":       cm.resolved_by,
                            "resolved_at":       cm.resolved_at,
                        }
                        for cm in comments
                    ],
                })

        reports_payload = [
            {
                "id":          r.id,
                "report_type": r.report_type,
                "sequence_nr": r.sequence_nr,
                "title":       r.title,
                "status":      r.status,
                "created_by":  r.created_by,
                "created_at":  r.created_at,
            }
            for r in reports
        ]

        payload = {
            "reports":          reports_payload,
            # Bug 2.17 Fix Build 287: auto:-Eintraege aus placeholder_cache einweben
            "blocks":           _enrich_blocks_with_cache(
                                    blocks_payload,
                                    edb.get_all_cache_entries(self._context.user_id),
                                ),
            "active_report_id": active_report.id if active_report else None,
            "lock": {
                "locked_by": lock.locked_by,
                "locked_at": lock.locked_at,
            } if lock else None,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        handler.send_response_body(
            200, body, content_type="application/json; charset=utf-8"
        )

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------

    def handle_post(
        self,
        handler: "ForensicRequestHandler",
        body_bytes: bytes,
    ) -> None:
        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            handler.send_response_body(
                400,
                _json_err(f"Ungueltiger JSON-Body: {exc}"),
                content_type="application/json; charset=utf-8",
            )
            return

        action = data.get("action", "")
        # Bug 3.1 Fix (Build 117): context.username ist der Beschuldigte.
        # Ermittler-Username kommt aus context.investigator_username.
        # Beleg: Projektgespraech 2026-05-07
        investigator = self._context.investigator_username

        # Lock-Aktionen (Lock-System v2, unveraendert)
        if action == "acquire_lock":
            self._action_acquire_lock(handler, data, investigator)
        elif action == "release_lock":
            self._action_release_lock(handler, data, investigator)
        elif action == "heartbeat":
            self._action_heartbeat(handler, data, investigator)
        elif action == "resume_lock":
            self._action_resume_lock(handler, data, investigator)
        elif action == "queue_join":
            self._action_queue_join(handler, data, investigator)
        elif action == "queue_leave":
            self._action_queue_leave(handler, data, investigator)
        elif action == "request_takeover":
            self._action_request_takeover(handler, data, investigator)
        elif action == "respond_takeover":
            self._action_respond_takeover(handler, data, investigator)

        # Layer-3-Aktionen: Bericht öffnen / neu anlegen
        # Beleg: Layer 3 States OPENING / NEW, Paket 6
        elif action == "open_report":
            self._action_open_report(handler, data, investigator)
        elif action == "new_report":
            self._action_new_report(handler, data, investigator)

        # B6-Schreibaktionen (Phase 4 — auf Block-API umgestellt)
        # Beleg: Bauplan B6 v0.5 §5, Projektgespraech 2026-05-06
        elif action == "save_block":
            self._action_save_block(handler, data, investigator)
        elif action == "delete_block":
            self._action_delete_block(handler, data, investigator)
        elif action == "update_block":
            self._action_update_block(handler, data, investigator)
        elif action == "reorder":
            self._action_reorder(handler, data, investigator)
        elif action == "add_comment":
            from forensic_api.editor_comment import EditorCommentEndpoint
            ep = EditorCommentEndpoint(self._bundle, investigator)
            ep.action_add_comment(handler, data)
        elif action == "resolve_comment":
            lock_id = handler.headers.get("X-Forensic-Lock-Id") or None
            from forensic_api.editor_comment import EditorCommentEndpoint
            ep = EditorCommentEndpoint(self._bundle, investigator)
            ep.action_resolve_comment(handler, data, lock_id)
        elif action == "add_anchor":
            self._action_add_anchor(handler, data, investigator)

        else:
            handler.send_response_body(
                400,
                _json_err(
                    f"Unbekannte Aktion: '{action}'",
                    "UNKNOWN_ACTION",
                ),
                content_type="application/json; charset=utf-8",
            )

    # ------------------------------------------------------------------
    # B6-Schreibaktionen (Phase 4 — Block-API)
    # Beleg: Bauplan B6 v0.5 §5, Projektgespraech 2026-05-06
    # ------------------------------------------------------------------

    def _action_save_block(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        """
        Block speichern (INSERT oder UPDATE).
        Nur der Eigentuemer darf einen vorhandenen Block ueberschreiben.
        Beleg: Bauplan B6 v0.5 §2.3 (Grundregel 14), §5
        """
        if not self._require_lock(handler, data):
            return
        report_id  = data.get("report_id")
        block_id   = str(data.get("block_id") or "").strip() or str(uuid.uuid4())
        block_type = str(data.get("block_type") or "paragraph").strip()
        block_data = data.get("block_data")
        if block_data is None:
            block_data = "{}"
        elif not isinstance(block_data, str):
            import json as _json
            block_data = _json.dumps(block_data, ensure_ascii=False)

        if not report_id:
            handler.send_response_body(
                400, _json_err("report_id fehlt", "MISSING_REPORT_ID"),
                content_type="application/json; charset=utf-8",
            )
            return

        placeholder_values_json = data.get("placeholder_values_json")
        if placeholder_values_json is not None:
            placeholder_values_json = str(placeholder_values_json)
        sort_index = data.get("sort_index")
        module_id  = data.get("module_id")

        from db.evidence_db import EvidenceDbError
        try:
            self._bundle.evidence.save_block(
                block_id=block_id,
                report_id=int(report_id),
                author=investigator,
                block_type=block_type,
                block_data=block_data,
                module_id=int(module_id) if module_id is not None else None,
                placeholder_values_json=placeholder_values_json,
                sort_index=int(sort_index) if sort_index is not None else None,
            )
        except EvidenceDbError as exc:
            handler.send_response_body(
                403, _json_err(str(exc), "FORBIDDEN"),
                content_type="application/json; charset=utf-8",
            )
            return
        except Exception as exc:
            logger.warning("save_block fehlgeschlagen: %s", exc)
            handler.send_response_body(
                400, _json_err(str(exc)),
                content_type="application/json; charset=utf-8",
            )
            return

        handler.send_response_body(
            201, _json_ok({"block_id": block_id}),
            content_type="application/json; charset=utf-8",
        )
        logger.info(
            "save_block: block_id=%s report_id=%s type=%s von '%s'",
            block_id, report_id, block_type, investigator,
        )

    def _action_update_block(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        """
        Block-Inhalt aktualisieren (nur Eigentuemer, Grundregel 14).
        Beleg: Bauplan B6 v0.5 §2.3, §5
        """
        if not self._require_lock(handler, data):
            return
        block_id = str(data.get("block_id") or "").strip()
        if not block_id:
            handler.send_response_body(
                400, _json_err("block_id fehlt", "MISSING_BLOCK_ID"),
                content_type="application/json; charset=utf-8",
            )
            return
        block_data = data.get("block_data")
        if block_data is None:
            block_data = "{}"
        elif not isinstance(block_data, str):
            import json as _json
            block_data = _json.dumps(block_data, ensure_ascii=False)

        placeholder_values_json = data.get("placeholder_values_json")
        if placeholder_values_json is not None:
            placeholder_values_json = str(placeholder_values_json)

        from db.evidence_db import EvidenceDbError
        try:
            found = self._bundle.evidence.update_block(
                block_id=block_id,
                block_data=block_data,
                placeholder_values_json=placeholder_values_json,
                requesting_author=investigator,
            )
        except EvidenceDbError as exc:
            handler.send_response_body(
                403, _json_err(str(exc), "FORBIDDEN"),
                content_type="application/json; charset=utf-8",
            )
            return

        if not found:
            handler.send_response_body(
                404, _json_err(f"Block '{block_id}' nicht gefunden.", "NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )
            return

        handler.send_response_body(
            200, _json_ok({"ok": True}),
            content_type="application/json; charset=utf-8",
        )

    def _action_delete_block(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        """
        Block loeschen (nur Eigentuemer, Grundregel 14).
        Loescht kaskadierend: report_block_order, report_anchors, report_comments.
        Beleg: Bauplan B6 v0.5 §2.3, §5
        """
        if not self._require_lock(handler, data):
            return
        block_id = str(data.get("block_id") or "").strip()
        if not block_id:
            handler.send_response_body(
                400, _json_err("block_id fehlt", "MISSING_BLOCK_ID"),
                content_type="application/json; charset=utf-8",
            )
            return

        from db.evidence_db import EvidenceDbError
        try:
            found = self._bundle.evidence.delete_block(
                block_id=block_id,
                requesting_author=investigator,
            )
        except EvidenceDbError as exc:
            handler.send_response_body(
                403, _json_err(str(exc), "FORBIDDEN"),
                content_type="application/json; charset=utf-8",
            )
            return

        if not found:
            handler.send_response_body(
                404, _json_err(f"Block '{block_id}' nicht gefunden.", "NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )
            return

        handler.send_response_body(
            200, _json_ok({"ok": True}),
            content_type="application/json; charset=utf-8",
        )
        logger.info("delete_block: block_id=%s von '%s'", block_id, investigator)

    def _action_reorder(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        """
        Sortierungsreihenfolge aendern (jeder Ermittler darf).
        Beleg: Bauplan B6 v0.3 §2.3, §5
        """
        if not self._require_lock(handler, data):
            return
        order = data.get("order", [])
        if not isinstance(order, list):
            handler.send_response_body(
                400, _json_err("'order' muss eine Liste sein"),
                content_type="application/json; charset=utf-8",
            )
            return

        updated = self._bundle.evidence.set_block_order(
            order=order,
            modified_by=investigator,
        )
        handler.send_response_body(
            200, _json_ok({"updated": updated}),
            content_type="application/json; charset=utf-8",
        )

    def _action_add_anchor(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
        investigator: str,
    ) -> None:
        """
        Beweisanker Paragraph <-> Annotation anlegen.
        Beleg: Bauplan B6 v0.3 §4.7, §5
        """
        if not self._require_lock(handler, data):
            return
        block_id      = data.get("block_id", "")
        annotation_id = data.get("annotation_id")
        anchor_text   = str(data.get("anchor_text", "")).strip()

        if not block_id or annotation_id is None or not anchor_text:
            handler.send_response_body(
                400, _json_err("block_id, annotation_id und anchor_text erforderlich"),
                content_type="application/json; charset=utf-8",
            )
            return

        from db.evidence_db import EvidenceDbError
        try:
            aid = self._bundle.evidence.add_anchor(
                block_id=block_id,
                annotation_id=int(annotation_id),
                anchor_text=anchor_text,
            )
        except EvidenceDbError as exc:
            handler.send_response_body(
                409, _json_err(str(exc), "CONFLICT"),
                content_type="application/json; charset=utf-8",
            )
            return

        handler.send_response_body(
            201, _json_ok({"anchor_id": aid}),
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Layer-3-Aktionen: Bericht öffnen / neu anlegen
    # Beleg: Layer 3 States OPENING / NEW, SLA Punkt 7, Paket 6
    # ------------------------------------------------------------------

    def _action_open_report(self, handler, data, investigator) -> None:
        """OPENING: Bestehenden Bericht öffnen.

        Schreibt Audit-Eintrag in report_opened und bereinigt Queue-Einträge
        des Clients für andere Berichte (Berichtswechsel).
        Liefert alle Blöcke des Berichts zurück damit ReportLayer seinen
        Zustand aufbauen kann.

        Beleg: Layer 3 States OPENING → OPENED, SLA Punkt 3 (Queue-Bereinigung),
               Paket 6
        """
        report_id_raw = data.get("report_id")
        sse_client    = str(data.get("sse_client", "")).strip()
        if not report_id_raw or not sse_client:
            handler.send_response_body(
                400, _json_err("report_id und sse_client erforderlich", "MISSING_FIELDS"),
                content_type="application/json; charset=utf-8",
            )
            return

        report_id = int(report_id_raw)
        edb = self._bundle.evidence

        # Bericht prüfen ob er existiert
        report = edb.get_report(report_id)
        if not report:
            handler.send_response_body(
                404, _json_err("Bericht nicht gefunden", "REPORT_NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )
            return

        # Audit-Eintrag + Queue-Bereinigung (atomar in log_report_opened)
        edb.log_report_opened(report_id, sse_client, investigator)
        logger.info(
            "OPENING: '%s' öffnet Bericht report_id=%d", investigator, report_id
        )

        # Blöcke laden damit der Client seinen Zustand aufbauen kann
        blocks = edb.get_blocks_for_report(report_id)
        order  = edb.get_block_order_for_report(report_id)
        # get_block_order_for_report gibt list[dict] zurück — Zugriff via []
        # Beleg: evidence_db.py get_block_order_for_report, Build 280
        order_map = {o["block_id"]: o["sort_index"] for o in order}

        # Bug 2.17 Fix Build 287: auto:-Eintraege aus placeholder_cache laden
        _cache = edb.get_all_cache_entries(self._context.user_id)

        _raw_blocks = [
            {
                "block_id":              b.block_id,
                "block_type":            b.block_type,
                "block_data":            json.loads(b.block_data) if b.block_data else {},
                "author":                b.author,
                "created_at":            b.created_at,
                "updated_at":            b.updated_at,
                "sort_index":            order_map.get(b.block_id, 0),
                "placeholder_values_json": b.placeholder_values_json,
            }
            for b in sorted(blocks, key=lambda b: order_map.get(b.block_id, 0))
        ]

        handler.send_response_body(
            200,
            json.dumps({
                "status":    "ok",
                "report_id": report_id,
                "title":     report.title,
                "report_type": report.report_type,
                "report_status": report.status,
                "blocks": _enrich_blocks_with_cache(_raw_blocks, _cache),
            }, ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )

    def _action_new_report(self, handler, data, investigator) -> None:
        """NEW: Neuen Bericht anlegen und Lock atomar erwerben.

        Erzeugt Bericht + Lock in einer Datenbanktransaktion (SLA Punkt 7).
        Schreibt Audit-Eintrag in report_opened.
        Antwortet mit report_id und lock_id.

        Beleg: Layer 3 States NEW, SLA Punkt 7, Paket 6
        """
        sse_client   = str(data.get("sse_client",   "")).strip()
        report_type  = str(data.get("report_type",  "interim")).strip()
        title        = str(data.get("title",        "")).strip()

        if not sse_client:
            handler.send_response_body(
                400, _json_err("sse_client erforderlich", "MISSING_SSE_CLIENT"),
                content_type="application/json; charset=utf-8",
            )
            return
        if not title:
            handler.send_response_body(
                400, _json_err("title erforderlich", "MISSING_TITLE"),
                content_type="application/json; charset=utf-8",
            )
            return
        if report_type not in ("interim", "final", "addendum"):
            handler.send_response_body(
                400, _json_err("Ungültiger report_type", "INVALID_REPORT_TYPE"),
                content_type="application/json; charset=utf-8",
            )
            return

        edb = self._bundle.evidence
        try:
            report_id, lock_id = edb.create_report_with_lock(
                report_type=report_type,
                title=title,
                created_by=investigator,
                sse_client=sse_client,
            )
        except Exception as exc:
            logger.error("_action_new_report: %s", exc)
            handler.send_response_body(
                500, _json_err("Bericht konnte nicht angelegt werden", "DB_ERROR"),
                content_type="application/json; charset=utf-8",
            )
            return

        # Audit-Eintrag (Queue-Bereinigung für anderen Bericht desselben Clients)
        edb.log_report_opened(report_id, sse_client, investigator)
        logger.info(
            "NEW: '%s' legt Bericht an report_id=%d type=%s",
            investigator, report_id, report_type,
        )

        handler.send_response_body(
            200,
            json.dumps({
                "status":    "ok",
                "report_id": report_id,
                "lock_id":   lock_id,
                "title":     title,
                "report_type": report_type,
            }, ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )

    # ------------------------------------------------------------------
    # Lock-Aktionen (Lock-System v2, unveraendert gegenueber Build 088)
    # Beleg: Bauplan B4 §8.6, Lock-System v2, Projektgespraech 2026-04-21
    # ------------------------------------------------------------------

    def _action_acquire_lock(self, handler, data, investigator) -> None:
        """ACQUIRING: Lock fuer einen Bericht erwerben.

        Antwortet mit 200+lock_id bei Erfolg.
        Antwortet mit 423+locked_by+cooldown_until+queue_length bei Misserfolg.
        Beleg: Layer 4 States ACQUIRING, SLA Punkt 11
        """
        sse_client = str(data.get("sse_client", "")).strip()
        if not sse_client:
            handler.send_response_body(
                400, _json_err("sse_client fehlt", "MISSING_SSE_CLIENT"),
                content_type="application/json; charset=utf-8",
            )
            return
        report_id_raw = data.get("report_id")
        if not report_id_raw:
            handler.send_response_body(
                400, _json_err("report_id fehlt", "MISSING_REPORT_ID"),
                content_type="application/json; charset=utf-8",
            )
            return
        report_id = int(report_id_raw)
        edb = self._bundle.evidence

        lock_id = edb.acquire_lock(report_id, investigator, sse_client)
        if lock_id:
            handler.send_response_body(
                200,
                json.dumps({"lock_id": lock_id}, ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            logger.info("ACQUIRING ok: '%s' report_id=%d", investigator, report_id)
            return

        # Lock belegt — 423 mit Kontext fuer Layer 4 ACQUIRING -> IDLE
        current = edb.get_lock(report_id)

        # Auto-Resume: selber Benutzer reconnectet mit neuer SSE (Browser-Reload).
        # Dies ist eine Layer-2-Aktion (RESUMING): Wir kennen hier die alte sse_client-ID
        # aus dem bestehenden Lock und binden sie an die neue SSE-Client-ID.
        # Beleg: Layer 2 States RESUMING, Paket-4-Review 2026-05-24
        if current and current.locked_by == investigator:
            resumed = edb.resume_lock(current.sse_client, sse_client)
            if resumed:
                logger.info("ACQUIRING: Auto-Resume '%s' report_id=%d", investigator, report_id)
                handler.send_response_body(
                    200,
                    json.dumps({"lock_id": current.lock_id, "resumed": True},
                               ensure_ascii=False).encode("utf-8"),
                    content_type="application/json; charset=utf-8",
                )
                return

        locked_by      = current.locked_by if current else "?"
        cooldown_until = edb.get_cooldown_until(report_id)
        queue_length   = edb.queue_count(report_id)
        handler.send_response_body(
            423,
            json.dumps({
                "error":          "Lock bereits belegt",
                "code":           "LOCK_CONFLICT",
                "locked_by":      locked_by,
                "cooldown_until": cooldown_until,
                "queue_length":   queue_length,
            }, ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )

    def _action_release_lock(self, handler, data, investigator) -> None:
        """RELEASING: Lock freigeben und Queue-Kaskade ausfuehren.

        Nach Freigabe: FIFO-Queue durchgehen, ersten gueltigen Kandidaten
        zum neuen Inhaber machen und per SSE benachrichtigen.
        Cooldown wird beim RELEASING entfernt (SLA Punkt 8).
        Beleg: Layer 4 States RELEASING, SLA Punkte 4, 8
        """
        # Bug 2.24 Diagnose Build 284: Eintrittspunkt-Logging
        # Beleg: Projektgespraech 2026-06-07
        logger.debug(
            "RELEASING Eintrittspunkt: investigator='%s' data=%s",
            investigator, {k: v for k, v in data.items() if k != "block_data"},
        )

        lock_id = str(data.get("lock_id", "")).strip()
        if not lock_id:
            handler.send_response_body(
                400, _json_err("lock_id erforderlich", "MISSING_FIELDS"),
                content_type="application/json; charset=utf-8",
            )
            return

        report_id_raw = data.get("report_id")
        report_id: int | None = None
        if report_id_raw is not None:
            try:
                report_id = int(report_id_raw)
            except (TypeError, ValueError):
                pass

        edb = self._bundle.evidence

        # Bug 2.24 Fix Build 282: report_id ist optional.
        if report_id is None:
            row = edb._con.execute(
                "SELECT report_id FROM editor_locks WHERE lock_id=?",
                (lock_id,),
            ).fetchone()
            if row:
                report_id = int(row["report_id"])
                logger.debug(
                    "RELEASING: report_id=%d aus lock_id-Lookup ergaenzt",
                    report_id,
                )
            else:
                handler.send_response_body(
                    200,
                    b'{"freed": true, "note": "lock_not_found"}',
                    content_type="application/json; charset=utf-8",
                )
                return

        # Bug 2.24 Fix Build 284: get_lock() nutzt eigene SQLite-Connection
        # (SSE-Thread-Safety). Im HTTP-Request-Thread kann diese Connection
        # einen veralteten DB-Snapshot sehen wenn der Lock gerade erst durch
        # acquire_lock() auf der Haupt-Connection geschrieben wurde.
        # Loesung: Direkt auf edb._con lesen statt get_lock() aufzurufen.
        # Beleg: Bugfix-Liste 2.24, Projektgespraech 2026-06-07
        current_row = edb._con.execute(
            "SELECT report_id, locked_by, lock_id, locked_at, sse_client "
            "FROM editor_locks WHERE report_id=?",
            (report_id,),
        ).fetchone()

        logger.debug(
            "RELEASING: lock_id_req=%s current_row=%s",
            lock_id,
            dict(current_row) if current_row else None,
        )

        if not current_row or str(current_row["lock_id"]) != lock_id:
            handler.send_response_body(
                423, _json_err("Nicht der Lock-Inhaber oder Lock nicht gefunden", "NOT_LOCK_OWNER"),
                content_type="application/json; charset=utf-8",
            )
            return

        locked_by_db = str(current_row["locked_by"] or "")
        if locked_by_db and locked_by_db != investigator:
            handler.send_response_body(
                423, _json_err("Nicht der Lock-Inhaber", "NOT_LOCK_OWNER"),
                content_type="application/json; charset=utf-8",
            )
            return
        if not locked_by_db:
            logger.warning(
                "RELEASING: Lock hat leeres locked_by — trotzdem freigegeben: "
                "lock_id=%s report_id=%d", lock_id, report_id
            )

        # Cooldown entfernen (SLA Punkt 8: erlischt bei freiwilligem RELEASING)
        edb.clear_cooldown(report_id)

        # Lock freigeben
        edb.release_lock(report_id, lock_id)
        logger.info("RELEASING: '%s' gibt Lock frei fuer report_id=%d", investigator, report_id)

        # Queue-Kaskade (SLA Punkt 4): aktive SSE-Clients aus events.py-Kontext
        active_clients = self._bundle.get_active_sse_clients()
        next_candidate = edb.queue_next_valid(report_id, active_clients)

        new_lock_id = None
        if next_candidate:
            new_lock_id = edb.acquire_lock(
                report_id, next_candidate["requested_by"], next_candidate["sse_client"]
            )
            if new_lock_id:
                edb.queue_remove(report_id, next_candidate["requested_by"])
                logger.info(
                    "RELEASING: Queue-Kaskade — '%s' erhaelt Lock report_id=%d",
                    next_candidate["requested_by"], report_id,
                )
                # SSE-Benachrichtigung an neuen Inhaber
                edb.lock_change_event().set()

        handler.send_response_body(
            200,
            json.dumps({
                "freed":      True,
                "new_holder": next_candidate["requested_by"] if new_lock_id else None,
            }, ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )

    def _action_resume_lock(self, handler, data, investigator) -> None:
        """RESUMING: SSE-Client-ID nach Reconnect innerhalb der Grace-Period aktualisieren.

        RESUMING ist eine Layer-2-Aktion. Die Identifikation erfolgt ausschliesslich
        ueber die alte SSE-Client-ID (old_sse_client) und die neue (sse_new).
        Die lock_id ist Layer-4-Daten und ist hier nicht bekannt / nicht zulaessig.

        Der Endpunkt wird aufgerufen wenn der Client nach einem SSE-Abriss
        innerhalb der Grace-Period reconnectet. Der Webserver prueft ob die
        alte SSE-Client-ID noch einem aktiven Lock zugeordnet ist (d.h. der
        Grace-Timer hat noch nicht abgelaufen). Wenn ja, wird die SSE-Client-ID
        im Lock aktualisiert.

        Beleg: Layer 2 States RESUMING, SLA Punkt 2, Paket-4-Review 2026-05-24
        """
        old_sse = str(data.get("old_sse_client", "")).strip()
        sse_new = str(data.get("sse_client", "")).strip()
        if not old_sse or not sse_new:
            handler.send_response_body(
                400, _json_err("old_sse_client und sse_client erforderlich", "MISSING_FIELDS"),
                content_type="application/json; charset=utf-8",
            )
            return
        ok = self._bundle.evidence.resume_lock(old_sse, sse_new)
        if ok:
            handler.send_response_body(
                200, _json_ok({"ok": True}),
                content_type="application/json; charset=utf-8",
            )
            logger.info("RESUMING ok: '%s' alte_sse=%s neue_sse=%s", investigator, old_sse, sse_new)
        else:
            handler.send_response_body(
                423, _json_err("Resume fehlgeschlagen — Grace-Period abgelaufen oder SSE unbekannt", "LOCK_NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )

    def _action_heartbeat(self, handler, data, investigator) -> None:
        """Heartbeat: locked_at aktualisieren (verhindert Timeout).

        Beleg: SLA Punkt 1 (SSE als Aktivitaetsnachweis)
        """
        lock_id       = str(data.get("lock_id", "")).strip()
        report_id_raw = data.get("report_id")
        if not lock_id or not report_id_raw:
            handler.send_response_body(
                400, _json_err("lock_id und report_id erforderlich", "MISSING_FIELDS"),
                content_type="application/json; charset=utf-8",
            )
            return
        report_id = int(report_id_raw)
        edb  = self._bundle.evidence
        lock = edb.get_lock(report_id)
        if lock and lock.lock_id == lock_id and lock.locked_by == investigator:
            # Heartbeat aktualisiert locked_at — dazu genuegt ein RESUMING
            # auf dieselbe SSE-Client-ID (kein Wechsel noetig).
            # Beleg: SLA Punkt 1 (SSE als Aktivitaetsnachweis)
            edb.resume_lock(lock.sse_client, lock.sse_client)
            handler.send_response_body(
                200, _json_ok({"ok": True}),
                content_type="application/json; charset=utf-8",
            )
        else:
            handler.send_response_body(
                423, _json_err("Lock nicht gefunden", "LOCK_NOT_FOUND"),
                content_type="application/json; charset=utf-8",
            )

    def _action_queue_join(self, handler, data, investigator) -> None:
        """QUEUED: In Warteschlange einreihen.

        Beleg: Layer 4 States QUEUED, SLA Punkt 9
        """
        sse_client    = str(data.get("sse_client", "")).strip()
        report_id_raw = data.get("report_id")
        if not sse_client or not report_id_raw:
            handler.send_response_body(
                400, _json_err("sse_client und report_id erforderlich", "MISSING_FIELDS"),
                content_type="application/json; charset=utf-8",
            )
            return
        report_id = int(report_id_raw)
        entry_id  = self._bundle.evidence.queue_add(report_id, investigator, sse_client)
        queue_pos = self._bundle.evidence.queue_count(report_id)
        handler.send_response_body(
            200,
            json.dumps({"queued": True, "entry_id": entry_id, "position": queue_pos},
                       ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )
        logger.info("QUEUED: '%s' eingereiht fuer report_id=%d (pos=%d)",
                    investigator, report_id, queue_pos)

    def _action_queue_leave(self, handler, data, investigator) -> None:
        """QUEUED -> IDLE: Warteschlange verlassen.

        Beleg: Layer 4 States QUEUED (Bericht-Wechsel)
        """
        report_id_raw = data.get("report_id")
        if not report_id_raw:
            handler.send_response_body(
                400, _json_err("report_id erforderlich", "MISSING_REPORT_ID"),
                content_type="application/json; charset=utf-8",
            )
            return
        report_id = int(report_id_raw)
        removed = self._bundle.evidence.queue_remove(report_id, investigator)
        handler.send_response_body(
            200, _json_ok({"removed": removed}),
            content_type="application/json; charset=utf-8",
        )

    def _action_request_takeover(self, handler, data, investigator) -> None:
        """TAKEOVER_PENDING: Uebernahme-Anfrage stellen.

        Prueft Cooldown bevor Anfrage gesendet wird.
        Beleg: Layer 4 States TAKEOVER_PENDING, SLA Punkt 8
        """
        sse_client    = str(data.get("sse_client", "")).strip()
        report_id_raw = data.get("report_id")
        if not report_id_raw:
            handler.send_response_body(
                400, _json_err("report_id erforderlich", "MISSING_REPORT_ID"),
                content_type="application/json; charset=utf-8",
            )
            return
        report_id = int(report_id_raw)
        edb  = self._bundle.evidence
        lock = edb.get_lock(report_id)

        if not lock:
            handler.send_response_body(
                404, _json_err("Kein Lock vorhanden", "NO_LOCK"),
                content_type="application/json; charset=utf-8",
            )
            return
        if lock.locked_by == investigator:
            handler.send_response_body(
                400, _json_err("Du hast den Lock bereits", "OWN_LOCK"),
                content_type="application/json; charset=utf-8",
            )
            return

        # Cooldown pruefen (SLA Punkt 8)
        cooldown_until = edb.get_cooldown_until(report_id)
        if cooldown_until:
            handler.send_response_body(
                429,
                json.dumps({
                    "error":          "Cooldown aktiv",
                    "code":           "COOLDOWN_ACTIVE",
                    "cooldown_until": cooldown_until,
                }, ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            return

        request_id = edb.log_takeover_request(report_id, lock.lock_id, investigator)
        edb.lock_change_event().set()
        handler.send_response_body(
            200,
            json.dumps({"request_id": request_id, "countdown": 60},
                       ensure_ascii=False).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )
        logger.info("TAKEOVER_PENDING: '%s' fragt '%s' fuer report_id=%d",
                    investigator, lock.locked_by, report_id)

    def _action_respond_takeover(self, handler, data, investigator) -> None:
        """TAKEOVER_REQUEST_IN: Auf eingehende Uebernahme-Anfrage antworten.

        grant: Lock freigeben, Anfragenden bekommt Lock per Queue-Kaskade.
        deny: Cooldown starten, Anfragenden bekommt TAKEOVER_DENIED.
        Beleg: Layer 4 States TAKEOVER_REQUEST_IN
        """
        report_id_raw = data.get("report_id")
        request_id_raw = data.get("request_id")
        response       = str(data.get("response", "")).strip()
        if not report_id_raw or not request_id_raw or response not in ("grant", "deny"):
            handler.send_response_body(
                400,
                _json_err("report_id, request_id und response (grant/deny) erforderlich",
                          "MISSING_FIELDS"),
                content_type="application/json; charset=utf-8",
            )
            return
        report_id  = int(report_id_raw)
        request_id = int(request_id_raw)
        edb  = self._bundle.evidence
        lock = edb.get_lock(report_id)

        if not lock or lock.locked_by != investigator:
            handler.send_response_body(
                423, _json_err("Nur der Lock-Inhaber darf antworten", "NOT_LOCK_OWNER"),
                content_type="application/json; charset=utf-8",
            )
            return

        if response == "grant":
            edb.resolve_takeover(request_id, "granted")
            edb.clear_cooldown(report_id)
            edb.release_lock(report_id, lock.lock_id)
            # Queue-Kaskade startet automatisch nach release_lock
            active_clients  = self._bundle.get_active_sse_clients()
            next_candidate  = edb.queue_next_valid(report_id, active_clients)
            new_lock_id = None
            if next_candidate:
                new_lock_id = edb.acquire_lock(
                    report_id, next_candidate["requested_by"], next_candidate["sse_client"]
                )
                if new_lock_id:
                    edb.queue_remove(report_id, next_candidate["requested_by"])
                    edb.lock_change_event().set()
            handler.send_response_body(
                200, _json_ok({"granted": True}),
                content_type="application/json; charset=utf-8",
            )
            logger.info("TAKEOVER granted: '%s' gibt Lock frei fuer report_id=%d",
                        investigator, report_id)
        else:  # deny
            edb.resolve_takeover(request_id, "denied")
            edb.set_cooldown(report_id, 600)  # 10 Minuten
            edb.lock_change_event().set()
            handler.send_response_body(
                200,
                json.dumps({
                    "denied":         True,
                    "cooldown_until": edb.get_cooldown_until(report_id),
                }, ensure_ascii=False).encode("utf-8"),
                content_type="application/json; charset=utf-8",
            )
            logger.info("TAKEOVER denied: '%s' behaelt Lock fuer report_id=%d (Cooldown 10min)",
                        investigator, report_id)

        # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _require_lock(
        self,
        handler: "ForensicRequestHandler",
        data: dict,
    ) -> bool:
        """
        Prueft ob ein gueltiger Lock gehalten wird.
        Gibt True zurueck wenn gueltig, sendet HTTP 423 wenn nicht.
        """
        lock_id = (
            handler.headers.get("X-Forensic-Lock-Id", "")
            or str(data.get("lock_id", ""))
        )
        if not lock_id:
            handler.send_response_body(
                423, _LOCK_REQUIRED,
                content_type="application/json; charset=utf-8",
            )
            return False
        report_id_raw = data.get("report_id")
        if report_id_raw is None:
            handler.send_response_body(
                400, _json_err("report_id fehlt", "MISSING_REPORT_ID"),
                content_type="application/json; charset=utf-8",
            )
            return False
        try:
            report_id = int(report_id_raw)
        except (TypeError, ValueError):
            handler.send_response_body(
                400, _json_err("report_id ungültig", "INVALID_REPORT_ID"),
                content_type="application/json; charset=utf-8",
            )
            return False
        if not self._bundle.evidence.validate_lock(report_id, lock_id):
            handler.send_response_body(
                423, _LOCK_REQUIRED,
                content_type="application/json; charset=utf-8",
            )
            return False
        return True
