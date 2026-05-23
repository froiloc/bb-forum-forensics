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
# Version: v0.6.117 · Build: 117 · 2026-05-07
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
    <!-- 0) editor.bundle.js: Editor.js + Tools (window.EditorJS, window.EditorTools).
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
    <!-- 2) userinfo.js: Lock/SSE/BroadcastChannel — nach report_editor.js laden -->
    <script src="/_forensic/userinfo.js" defer></script>
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
        page_html = _EDITOR_HTML.format(
            username=safe_investigator,   # Ermittler — fuer data-username / Block-Owner-Vergleich
            subject=safe_subject,         # Beschuldigter — nur fuer Anzeigetitel
            investigator=safe_investigator,  # Bug 2.68 Fix Build 162: Ermittler im Titel
            user_id=self._context.user_id,
            autosave_debounce_ms=autosave_ms,
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
            "blocks":           blocks_payload,
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

        # Auto-Resume: selber Benutzer mit neuer SSE (Browser-Reload)
        if current and current.locked_by == investigator:
            resumed = edb.resume_lock(report_id, current.lock_id, investigator, sse_client)
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
        lock_id = str(data.get("lock_id", "")).strip()
        report_id_raw = data.get("report_id")
        if not lock_id or not report_id_raw:
            handler.send_response_body(
                400, _json_err("lock_id und report_id erforderlich", "MISSING_FIELDS"),
                content_type="application/json; charset=utf-8",
            )
            return
        report_id = int(report_id_raw)
        edb = self._bundle.evidence

        # Nur der Inhaber darf freigeben
        current = edb.get_lock(report_id)
        if not current or current.lock_id != lock_id or current.locked_by != investigator:
            handler.send_response_body(
                423, _json_err("Nicht der Lock-Inhaber", "NOT_LOCK_OWNER"),
                content_type="application/json; charset=utf-8",
            )
            return

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
        """RESUMING: SSE-Client-ID nach Reconnect aktualisieren.

        Wird nach Wiederverbindung innerhalb der Grace-Period aufgerufen.
        Beleg: Layer 2 States RESUMING, SLA Punkt 2
        """
        lock_id   = str(data.get("lock_id", "")).strip()
        sse_new   = str(data.get("sse_client", "")).strip()
        report_id_raw = data.get("report_id")
        if not lock_id or not sse_new or not report_id_raw:
            handler.send_response_body(
                400, _json_err("lock_id, sse_client und report_id erforderlich", "MISSING_FIELDS"),
                content_type="application/json; charset=utf-8",
            )
            return
        report_id = int(report_id_raw)
        ok = self._bundle.evidence.resume_lock(report_id, lock_id, investigator, sse_new)
        if ok:
            handler.send_response_body(
                200, _json_ok({"ok": True}),
                content_type="application/json; charset=utf-8",
            )
            logger.info("RESUMING ok: '%s' report_id=%d", investigator, report_id)
        else:
            handler.send_response_body(
                423, _json_err("Resume fehlgeschlagen — Lock nicht gefunden", "LOCK_NOT_FOUND"),
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
            edb.resume_lock(report_id, lock_id, investigator, lock.sse_client)
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
        if not self._bundle.evidence.validate_lock(lock_id, report_id=report_id):
            handler.send_response_body(
                423, _LOCK_REQUIRED,
                content_type="application/json; charset=utf-8",
            )
            return False
        return True
