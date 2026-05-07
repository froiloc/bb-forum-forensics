/**
 * userinfo/report_editor.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Editor.js-Integration
 *
 * Zweck:
 *   Editor.js-Modul fuer Fenster 3 (Bericht-Editor).
 *   Wird von userinfo.js geladen wenn #report-editor-body vorhanden ist.
 *   Umbenannt von editor.js -> report_editor.js (Build 100, B6 Phase 2)
 *   zur dauerhaften Trennung von Bibliotheksname und Dateiname.
 *   Beleg: Bauplan B6 v0.5 §4.1, Projektgespraech 2026-05-06
 *
 * Funktionen:
 *   - EditorJsManager: initialisiert Editor.js mit allen Plugins
 *   - EvidenceBlock: custom Tool — rendert Annotation-Gruppe als Beweiskarte
 *   - Report-Auswahl-Dropdown: Berichtsauswahl und Neu-Anlegen
 *   - Auto-Save: onChange-Handler mit konfigurierbarem Debounce
 *   - block_updated-SSE-Handler: re-rendert betroffene Bloecke
 *   - Drag-and-Drop: Annotationen aus Sidebar als EvidenceBlock einfuegen
 *   - window.postMessage-Handler: Annotation aus Fenster 2 einfuegen
 *   - Print-CSS: Toolbar/Lock-Banner im Druck ausblenden
 *
 * Abhaengigkeiten:
 *   - editor.bundle.js (/_forensic/static/editor/editor.bundle.js)
 *     Muss via AP-E2 (build_editor_bundle.py) erstellt worden sein.
 *   - userinfo.js: stellt EditorState, acquireLock(), esc() bereit
 *
 * Konfiguration (via data-Attribute auf #report-editor-body):
 *   data-autosave-debounce-ms  Auto-Save-Debounce in Millisekunden
 *                              (Standard: AUTOSAVE_DEBOUNCE_MS = 1500)
 *
 * Changelog:
 *   Build 045 (AP-E4): Erstimplementierung als editor.js
 *   Build 100 (B6 Phase 2): Umbenannt zu report_editor.js. report.js entfernt.
 *     Beleg: Bauplan B6 v0.5 §4.1, Projektgespraech 2026-05-06
 *   Build 101 (B6 Phase 3): BlockWrapperManager, _ownerColor, initBlockWrappers,
 *     _openAccordionSection, _initSidebarAccordion. _applyOwnershipStyles bleibt
 *     fuer contenteditable-Verwaltung erhalten; initBlockWrappers ergaenzt um
 *     MutationObserver, Hover-Metazeile und Kommentieren-Schaltflaeche.
 *     Neue window-Exports: initBlockWrappers, openAccordionSection, ownerColor.
 *     Beleg: Bauplan B6 v0.5 §4.3, §4.4, Projektgespraech 2026-05-06
 *   Build 103 (B6 Phase 5): PlaceholderInlineTool registriert (CMD+SHIFT+P).
 *   Build 104 (B6 Phase 6): _openAccordionSection fuer 'form' -> _refreshPlaceholderForm().
 *   Build 105 (B6 Phase 7): _refreshModulePanel(), _loadBlocksAndReinit().
 *   Build 106 (B6 Phase 8): _refreshAnnotationSidebar().
 *   Build 118 (Bugfix 2.14/2.16/2.17/2.18):
 *     - _isInitializing-Guard: onChange waehrend onReady unterdrückt.
 *     - aria-hidden → inert auf .block-meta-bar (WCAG 2.18).
 *     - inert per mouseenter/mouseleave/focusout gesteuert.
 *     - blauer Rahmen: Cleanup bei Formular-Akkordeon-Wechsel.
 *     Beleg: Bugfix Build 118, Projektgespraech 2026-05-08
 *     _openAccordionSection fuer 'annotations' -> _refreshAnnotationSidebar().
 *     toggleAnnotationSidebar() leitet auf Annotationen-Akkordeon um.
 *     Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
 *
 * Version: v0.6.119 · Build: 119 · 2026-05-08
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 */

(function() {
'use strict';

// ---------------------------------------------------------------------------
// DEV-Logging (Build 110)
// Beleg: Projektgespraech 2026-05-07
// ---------------------------------------------------------------------------
/** @param {...*} args */
function _dbg(...args) {
    if (window.FORENSIC_DEBUG !== false) {
        console.debug('[forensic]', ...args);
    }
}


// ---------------------------------------------------------------------------
// Konstanten
// ---------------------------------------------------------------------------

/**
 * Auto-Save-Debounce in Millisekunden.
 * Konfigurierbar via data-autosave-debounce-ms auf #report-editor-body
 * oder ueber editor_autosave_debounce_ms in config.yaml.
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 */
const AUTOSAVE_DEBOUNCE_MS = (() => {
    const body = document.getElementById('report-editor-body');
    const fromAttr = parseInt(body?.dataset?.autosaveDebounceMs, 10);
    return Number.isFinite(fromAttr) && fromAttr > 0 ? fromAttr : 1500;
})();

/** API-Pfade fuer Editor-Endpunkte (AP-E3) */
const EDITOR_API = {
    REPORTS:  '/_forensic/reports',
    BLOCK:    '/_forensic/editor/block',
    ORDER:    '/_forensic/editor/order',
    EVIDENCE: '/_forensic/editor/evidence',
};

/** Maximale Anzahl Bloecke in der Drag-and-Drop-Annotations-Sidebar */
const SIDEBAR_MAX_ANNOTATIONS = 200;

// ---------------------------------------------------------------------------
// Modul-Zustand
// ---------------------------------------------------------------------------

/** Aktuell geladener Bericht (ReportRecord) oder null */
let _currentReport = null;

/** Aktuell geladene Bloecke (fuer Sidebar-Formular) */
let _currentBlocks = [];

/** Editor.js-Instanz */
let _editor = null;

/** Auto-Save-Debounce-Timer */
let _saveTimer = null;

/** Sidebar-Zustand */
let _sidebarVisible = false;

/** Guard gegen parallele loadReport()-Aufrufe.
 * Verhindert doppelte Editor-Instanzen im #editorjs-holder.
 * Beleg: Bugfix Build 051b, Projektgespraech 2026-04-21
 */
let _loadInProgress = false;

/**
 * Guard: Unterdrückt onChange-Callbacks waehrend der Editor-Initialisierung.
 * Problem: _applyOwnershipStyles und initBlockWrappers veraendern DOM-Attribute
 * in onReady (via setTimeout), was Editor.js's MutationObserver triggert und
 * sofort onChange → _performAutoSave auslöst. Das fuehrt zu:
 *   1. Vorzeitigem Auto-Save bevor alle Bloecke korrekt geladen sind.
 *   2. TypeError in setCurrentBlockByChildNode (Editor noch nicht bereit).
 * Fix: _isInitializing=true von onReady bis nach dem letzten setTimeout,
 * dann auf false setzen. onChange prueft dieses Flag.
 * Beleg: Bugfix Build 117, Projektgespraech 2026-05-08
 */
let _isInitializing = false;

// ---------------------------------------------------------------------------
// Hilfsfunktion: fetch mit Lock-Header
// ---------------------------------------------------------------------------

/**
 * Sendet einen POST-Request mit Lock-Header.
 * Gibt null zurueck wenn kein Lock gehalten wird.
 * @param {string} url
 * @param {object} body
 * @returns {Promise<Response|null>}
 */
async function _fetchWithLock(url, body) {
    // EditorState kommt aus userinfo.js (gemeinsam geladen)
    const lockId = window.EditorState?.lockId;
    if (!lockId) {
        console.warn('report_editor.js: Kein Lock — POST abgebrochen:', url);
        return null;
    }
    return fetch(url, {
        method:  'POST',
        headers: {
            'Content-Type':       'application/json',
            'X-Forensic-Lock-Id': lockId,
        },
        body: JSON.stringify({ ...body, lock_id: lockId }),
    });
}

// ---------------------------------------------------------------------------
// Report-Auswahl-UI
// ---------------------------------------------------------------------------

/**
 * Report-Auswahl-Dropdown laden und aufbauen.
 * Laeuft beim Initialisieren von Fenster 3.
 */
async function initReportSelector() {
    _dbg('initReportSelector() gestartet');
    const container = document.getElementById('report-selector-container');
    if (!container) return;

    container.innerHTML = '<span class="loading-spinner"></span> Lade Berichte…';

    let reports = [];
    try {
        const resp = await fetch(EDITOR_API.REPORTS, {
            headers: { 'X-Forensic-Request': 'ajax' }
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        reports = data.reports || [];
    } catch (err) {
        container.innerHTML = `<div class="status-msg status-msg-error">
            Berichte konnten nicht geladen werden: ${window.esc ? esc(String(err)) : String(err)}
        </div>`;
        return;
    }

    // UI aufbauen
    const typeLabels = { interim: 'Zwischenbericht', final: 'Abschlussbericht', addendum: 'Nachtrag' };
    const options = reports.map(r =>
        `<option value="${r.id}">${r.sequence_nr}. ${typeLabels[r.report_type] || r.report_type}: ${r.title}</option>`
    ).join('');

    container.innerHTML = `
        <div id="report-selector-bar">
            <label for="report-select" class="report-selector-label">Bericht:</label>
            <select id="report-select" class="report-select">
                ${reports.length ? options : '<option value="">— Noch kein Bericht —</option>'}
            </select>
            <button class="editor-btn" id="btn-new-report" title="Neuen Bericht anlegen">+ Neuer Bericht</button>
            <span id="report-selector-status"></span>
        </div>`;

    document.getElementById('report-select')?.addEventListener('change', async (evt) => {
        const reportId = parseInt(evt.target.value, 10);
        if (!reportId) return;
        const report = reports.find(r => r.id === reportId);
        if (report) await loadReport(report);
    });

    document.getElementById('btn-new-report')?.addEventListener('click', () => openNewReportDialog(reports));


    // Ersten Bericht automatisch laden
    if (reports.length) {
        await loadReport(reports[0]);
    }
}

/**
 * Dialog zum Anlegen eines neuen Berichts.
 * @param {Array} existingReports
 */
function openNewReportDialog(existingReports) {
    document.getElementById('new-report-dialog')?.remove();

    const hasFinal = existingReports.some(r => r.report_type === 'final');
    const typeOpts = [
        { value: 'interim',  label: 'Zwischenbericht' },
        { value: 'final',    label: 'Abschlussbericht', disabled: hasFinal },
        { value: 'addendum', label: 'Nachtragsbericht' },
    ];

    const dialog = document.createElement('div');
    dialog.id = 'new-report-dialog';
    dialog.className = 'editor-dialog';
    dialog.innerHTML = `
        <div class="editor-dialog-inner">
            <h3 style="margin:0 0 12px 0;font-size:14px">Neuen Bericht anlegen</h3>
            <div style="margin-bottom:8px">
                <label style="font-size:12px;display:block;margin-bottom:4px">Berichtstyp:</label>
                <select id="new-report-type" class="report-select">
                    ${typeOpts.map(o =>
                        `<option value="${o.value}" ${o.disabled ? 'disabled' : ''}>${o.label}</option>`
                    ).join('')}
                </select>
            </div>
            <div style="margin-bottom:12px">
                <label style="font-size:12px;display:block;margin-bottom:4px">Titel:</label>
                <input id="new-report-title" type="text" class="report-text-input"
                    placeholder="z.B. 1. Zwischenbericht – Ermittlungsstand Q2 2026">
            </div>
            <div style="display:flex;gap:8px">
                <button class="editor-btn editor-btn-primary" id="btn-create-report">Anlegen</button>
                <button class="editor-btn" id="btn-cancel-new-report">Abbrechen</button>
            </div>
        </div>`;

    document.getElementById('report-selector-container').appendChild(dialog);
    document.getElementById('new-report-title').focus();

    document.getElementById('btn-cancel-new-report')?.addEventListener('click', () => dialog.remove());
    document.getElementById('btn-create-report')?.addEventListener('click', async () => {
        const type  = document.getElementById('new-report-type').value;
        const title = document.getElementById('new-report-title').value.trim();
        if (!title) {
            document.getElementById('new-report-title').focus();
            return;
        }
        try {
            const resp = await fetch(EDITOR_API.REPORTS, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ report_type: type, title }),
            });
            const data = await resp.json();
            if (resp.status === 201) {
                dialog.remove();
                await initReportSelector();
                // Neuen Bericht sofort laden
                const select = document.getElementById('report-select');
                if (select) {
                    select.value = data.id;
                    select.dispatchEvent(new Event('change'));
                }
            } else {
                _selectorStatus(data.error || `Fehler ${resp.status}`, 'error');
            }
        } catch (err) {
            _selectorStatus(String(err), 'error');
        }
    });
}

function _selectorStatus(msg, level) {
    const el = document.getElementById('report-selector-status');
    if (el) el.innerHTML = `<span class="status-msg status-msg-${level}" style="font-size:11px">${msg}</span>`;
}

// ---------------------------------------------------------------------------
// Editor.js initialisieren
// ---------------------------------------------------------------------------

/**
 * Laedt einen Bericht und (re-)initialisiert den Editor.
 * @param {object} report  ReportRecord
 */
/**
 * Entfernt doppelte .codex-editor-Instanzen aus dem #editorjs-holder.
 * Wird defensiv aufgerufen bevor ein neuer Editor initialisiert wird.
 * Beleg: Bugfix Build 051b, Projektgespraech 2026-04-21
 */
function _cleanupDuplicateEditors() {
    const holder = document.getElementById('editorjs-holder');
    if (!holder) return;
    const instances = holder.querySelectorAll('.codex-editor');
    if (instances.length <= 1) return;
    // Alle ausser dem ersten entfernen
    for (let i = 1; i < instances.length; i++) {
        instances[i].remove();
        console.warn('report_editor.js: doppelte codex-editor-Instanz entfernt');
    }
}

async function loadReport(report) {
    _dbg('loadReport() report_id=', report?.id, 'type=', report?.report_type);
    // Guard: verhindert parallele Ausfuehrung (z.B. initEditorModule + _reinitWithLock)
    // Beleg: Bugfix Build 051b, Projektgespraech 2026-04-21
    if (_loadInProgress) {
        console.debug('report_editor.js: loadReport() bereits aktiv — übersprungen');
        return;
    }
    _loadInProgress = true;
    try {
        await _loadReportImpl(report);
    } finally {
        _loadInProgress = false;
    }
}

async function _loadReportImpl(report) {
    _currentReport = report;

    // Build 114: Action-Bar-Buttons aktivieren sobald ein Bericht geladen ist.
    // Drucken, Export und Aktualisieren sind lock-unabhaengig.
    // Beleg: Projektgespraech 2026-05-07
    ['btn-print', 'btn-export', 'btn-refresh-placeholders'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.disabled = false;
    });

    // Titel aktualisieren
    const titleEl = document.getElementById('editor-report-title');
    if (titleEl) {
        const typeLabels = { interim: 'Zwischenbericht', final: 'Abschlussbericht', addendum: 'Nachtrag' };
        titleEl.textContent = `${report.sequence_nr}. ${typeLabels[report.report_type] || report.report_type}: ${report.title}`;
    }

    // Bestehenden Editor zerstoeren
    // WICHTIG: Editor.js destroy() entfernt den holder-DOM-Knoten.
    // Daher muss er danach neu angelegt werden, sonst findet
    // _initEditorJs() via getElementById('editorjs-holder') nichts.
    // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
    if (_editor) {
        try { await _editor.destroy(); } catch (_) {}
        _editor = null;
        window._editor = null;
    }
    // editorjs-holder neu anlegen falls Editor.destroy() ihn entfernt hat.
    // Build 113: Holder lebt in #report-main-col (nicht mehr in report-editor-container).
    // Beleg: Projektgespraech 2026-05-07
    const editorContainer = document.getElementById('report-main-col');
    if (editorContainer && !document.getElementById('editorjs-holder')) {
        // Holder nach report-selector-container + report-status-msg einfuegen
        const statusEl = document.getElementById('report-status-msg');
        const newHolder = document.createElement('div');
        newHolder.id = 'editorjs-holder';
        newHolder.className = 'editorjs-holder';
        if (statusEl && statusEl.nextSibling) {
            editorContainer.insertBefore(newHolder, statusEl.nextSibling);
        } else {
            editorContainer.appendChild(newHolder);
        }
    }

    // Bloecke laden
    const blocksResp = await fetch(`/_forensic/report?format=json`, {
        headers: { 'X-Forensic-Request': 'ajax' }
    });
    let existingBlocks = [];
    if (blocksResp.ok) {
        const data = await blocksResp.json();
        // B6 Phase 4+: "blocks" statt "paragraphs"
        existingBlocks = data.blocks || [];
        // B6 Phase 6: _currentBlocks fuer Sidebar-Formular merken
        // Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
        _currentBlocks = existingBlocks;
    }

    // Defensive Bereinigung: doppelte Editor-Instanzen entfernen
    // falls ein paralleler Aufruf die erste Instanz schon gerendert hat.
    _cleanupDuplicateEditors();

    // Auf Bundle warten
    _dbg('_initEditorJs(): window.EditorJS=', !!window.EditorJS);
    if (!window.EditorJS) {
        // Build 113: Fehlermeldung in #report-status-msg (report-editor-container entfernt)
        const statusEl = document.getElementById('report-status-msg');
        if (statusEl) statusEl.innerHTML = `
            <div class="status-msg status-msg-warn" style="margin:12px 0">
                Editor.js-Bundle nicht geladen.
                Bitte <code>deployment/build_editor_bundle.py</code> ausfuehren (AP-E2).
            </div>`;
        return;
    }

    _initEditorJs(existingBlocks, report.id);
}

/**
 * Editor.js-Instanz initialisieren.
 * @param {Array} blocks  Bereits gespeicherte Bloecke
 * @param {number} reportId
 */
function _initEditorJs(blocks, reportId) {
    const holderEl = document.getElementById('editorjs-holder');
    if (!holderEl) return;

    const username = document.getElementById('report-editor-body')?.dataset?.username || '';

    // Editor.js-Datenformat aus gespeicherten block_data aufbauen.
    // Leere paragraph-Bloecke werden normalisiert damit Editor.js sie
    // nicht als 'saved data is invalid' verwirft.
    // Beleg: Bugfix Build 050, Projektgespraech 2026-04-21
    const editorData = {
        time:   Date.now(),
        blocks: blocks.map(b => {
            const raw = typeof b.block_data === 'string'
                ? JSON.parse(b.block_data)
                : (b.block_data || {});
            // paragraph ohne text-Feld: Editor.js wuerde Block verwerfen
            if (b.block_type === 'paragraph' && !raw.text) raw.text = '';
            // B6 Phase 5: Template-Syntax in text-Feld zu Chips hydrieren.
            // Platzhalter-Werte kommen aus placeholder_values_json.
            // Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
            if (raw.text && window.PlaceholderChips?.hydrateChips) {
                const values = b.placeholder_values_json
                    ? (() => { try { return JSON.parse(b.placeholder_values_json); } catch(_) { return {}; } })()
                    : {};
                raw.text = window.PlaceholderChips.hydrateChips(raw.text, values, {});
            }
            return { id: b.block_id, type: b.block_type, data: raw };
        }),
    };

    // readOnly: Lock-Zustand zum Zeitpunkt der Initialisierung.
    // Nach Lock-Erwerb wird der Editor via _reinitWithLock() neu
    // initialisiert — dann mit readOnly: false.
    // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
    const hasLock = !!(window.EditorState?.lockId);

    _editor = new window.EditorJS({
        holder: 'editorjs-holder',
        data:   editorData,
        placeholder: hasLock
            ? 'Schreiben beginnen…'
            : 'Lock erwerben um zu schreiben…',
        readOnly: !hasLock,

        tools: {
            header:     { class: window.EditorTools?.Header,     inlineToolbar: true },
            paragraph:  { class: window.EditorTools?.Paragraph,  inlineToolbar: true },
            list:       { class: window.EditorTools?.NestedList, inlineToolbar: true },
            table:      { class: window.EditorTools?.Table },
            quote:      { class: window.EditorTools?.Quote,      inlineToolbar: true },
            image:      { class: window.EditorTools?.SimpleImage },
            delimiter:  { class: window.EditorTools?.Delimiter },
            marker:     { class: window.EditorTools?.Marker,     shortcut: 'CMD+SHIFT+M' },
            annotation: { class: window.EditorTools?.Annotation },
            evidence:   { class: EvidenceBlock },
            // B6 Phase 5: Platzhalter-Chips als InlineTool (OP-B6-5 verifiziert)
            // Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
            placeholder: {
                class:         window.PlaceholderInlineTool,
                inlineToolbar: true,
                shortcut:      'CMD+SHIFT+P',
            },
        },

        onChange: () => {
            // Bug-Fix Build 117: Waehrend der Initialisierung (onReady + Timeouts)
            // duerfen DOM-Mutationen durch _applyOwnershipStyles und initBlockWrappers
            // keinen Auto-Save ausloesen. Das wuerde den TypeError in
            // setCurrentBlockByChildNode verursachen.
            // Beleg: Bugfix Build 117, Projektgespraech 2026-05-08
            if (_isInitializing) return;
            _scheduleAutoSave(reportId);
        },

        onReady: () => {
            // Initialisierungs-Guard aktivieren: verhindert vorzeitigen Auto-Save
            // durch DOM-Mutationen in _applyOwnershipStyles / initBlockWrappers.
            // Beleg: Bugfix Build 117, Projektgespraech 2026-05-08
            _isInitializing = true;

            // Undo-Plugin initialisieren (muss nach onReady geschehen)
            if (window.EditorTools?.Undo) {
                new window.EditorTools.Undo({ editor: _editor });
            }
            _applyOwnershipStyles(blocks, username);
            // Block-Wrapper und Support-Sidebar initialisieren (B6 Phase 3)
            // Beleg: Bauplan B6 v0.5 §4.3, Projektgespraech 2026-05-06
            initBlockWrappers(blocks, username);
            _initSidebarAccordion();
            // B6 Phase 5: Doppelklick-Handler auf Chips binden
            // Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
            _bindChipDoubleClick();
            // Global bereitstellen fuer Debugging und Reinit
            window._editor = _editor;
            console.debug('report_editor.js: Editor bereit, report_id=', reportId,
                          '| readOnly=', !hasLock);

            // Initialisierungs-Guard freigeben: laengste interne Timeout-Kette
            // ist _applyOwnershipStyles mit 300 ms. Wir waehlen 600 ms als
            // sicheren Puffer, damit alle DOM-Mutationen abgeschlossen sind
            // bevor onChange wieder Auto-Saves ausloesen darf.
            // Beleg: Bugfix Build 117, Projektgespraech 2026-05-08
            setTimeout(() => {
                _isInitializing = false;
                console.debug('report_editor.js: Initialisierungs-Guard freigegeben.');
            }, 600);
        },
    });
}

/**
 * Ownership-Stile anwenden: fremde Bloecke visuell markieren und
 * contenteditable deaktivieren.
 * @param {Array} blocks
 * @param {string} username  Eigener SAMAccountName
 */
function _applyOwnershipStyles(blocks, username) {
    if (!blocks.length) return;
    // Nach kurzer Verzoegerung — Editor.js braucht Zeit zum Rendern.
    // Bug-Fix Build 119: b.owner → b.author (API liefert 'author', nicht 'owner').
    // Vorher wurden alle Bloecke als fremd eingestuft (b.owner immer undefined),
    // was contentEditable='false' auf alle Bloecke setzte.
    // Beleg: Bugfix Build 119, Projektgespraech 2026-05-08
    setTimeout(() => {
        blocks.forEach(b => {
            if (b.author === username) return;
            const el = document.querySelector(`[data-id="${b.block_id}"] .ce-block__content`);
            if (el) {
                el.querySelectorAll('[contenteditable]').forEach(c => {
                    c.contentEditable = 'false';
                });
                el.classList.add('block-foreign');
                el.title = `Erstellt von: ${b.author}`;
            }
        });
    }, 300);
}

// ---------------------------------------------------------------------------
// BlockWrapperManager (B6 Phase 3)
// Beleg: Bauplan B6 v0.5 §4.3, Projektgespraech 2026-05-06
//
// Legt fuer jeden Editor.js-.ce-block-Knoten einen Block-Wrapper an.
// Der Wrapper liegt AUSSERHALB von Editor.js und enthaelt:
//   - border-left in der deterministischen Eigentuemer-Farbe
//   - Hover-Metazeile (Eigentuemer, Erstellungsdatum, Kommentieren-Schaltflaeche)
//
// Der Eigentuemer-Farbe wird per _ownerColor() deterministisch aus dem
// SAMAccountName berechnet (Hash -> HSL), damit dieselbe Person in jeder
// Sitzung konsistent dieselbe Farbe erhaelt.
// ---------------------------------------------------------------------------

/**
 * Berechnet einen deterministischen HSL-Farbton aus einem SAMAccountName.
 * Sattigung und Helligkeit sind fest, nur der Hue variiert.
 * Beleg: Bauplan B6 v0.5 §4.3, Projektgespraech 2026-05-06
 *
 * @param {string} username
 * @returns {string}  CSS-Farbwert, z.B. 'hsl(127, 60%, 40%)'
 */
function _ownerColor(username) {
    if (!username) return 'hsl(0, 0%, 70%)';
    let hash = 0;
    for (let i = 0; i < username.length; i++) {
        hash = (hash * 31 + username.charCodeAt(i)) >>> 0;
    }
    const hue = hash % 360;
    return `hsl(${hue}, 60%, 40%)`;
}

/**
 * Legt einen Block-Wrapper um ein .ce-block-Element.
 * Idempotent: bereits gewrappte Bloecke werden uebersprungen.
 * Beleg: Bauplan B6 v0.5 §4.3, Projektgespraech 2026-05-06
 *
 * @param {Element}  ceBlock    .ce-block-DOM-Knoten
 * @param {object}   blockMeta  { block_id, author, created_at } aus blocks-Array
 * @param {string}   username   Eigener SAMAccountName (bestimmt own vs. foreign)
 */
function _wrapBlock(ceBlock, blockMeta, username) {
    if (ceBlock.closest('.block-wrapper')) return;  // bereits gewrappt

    const isOwn   = blockMeta.author === username;
    const color   = _ownerColor(blockMeta.author);
    const created = blockMeta.created_at
        ? new Date(blockMeta.created_at * 1000).toLocaleString('de-DE', {
              day:   '2-digit', month: '2-digit', year: 'numeric',
              hour:  '2-digit', minute: '2-digit',
          })
        : '';

    // Wrapper-Div erzeugen
    const wrapper = document.createElement('div');
    wrapper.className = 'block-wrapper ' + (isOwn ? 'block-wrapper--own' : 'block-wrapper--foreign');
    wrapper.dataset.blockId  = blockMeta.block_id;
    wrapper.dataset.author   = blockMeta.author;
    wrapper.style.setProperty('--block-owner-color', color);
    wrapper.setAttribute('aria-label', isOwn
        ? `Eigener Block (${blockMeta.author})`
        : `Block von ${blockMeta.author}`);

    // Metazeile (standardmaessig ausgeblendet, erscheint bei Hover).
    // Bug-Fix Build 118: aria-hidden → inert (WCAG 2.18).
    // inert macht Element und Nachkommen fuer AT und Fokus unsichtbar
    // solange nicht gehovert. Hover-Handler toggeln inert per JS.
    // Beleg: Bugfix Build 118, Projektgespraech 2026-05-08
    const metaBar = document.createElement('div');
    metaBar.className = 'block-meta-bar';
    metaBar.setAttribute('inert', '');

    const metaAuthor = document.createElement('span');
    metaAuthor.className = 'block-meta-author';
    metaAuthor.textContent = blockMeta.author;

    const metaDate = document.createElement('span');
    metaDate.className = 'block-meta-date';
    metaDate.textContent = created;

    const btnComment = document.createElement('button');
    btnComment.className = 'block-meta-comment-btn';
    btnComment.type = 'button';
    btnComment.textContent = '💬 Kommentieren';
    btnComment.setAttribute('aria-label', `Kommentar zu Block von ${blockMeta.author} verfassen`);
    btnComment.addEventListener('click', (e) => {
        e.stopPropagation();
        _openCommentAccordion(blockMeta.block_id);
    });

    metaBar.appendChild(metaAuthor);
    metaBar.appendChild(metaDate);
    metaBar.appendChild(btnComment);

    // Wrapper in DOM einsetzen (ceBlock in Wrapper verschieben)
    ceBlock.parentNode.insertBefore(wrapper, ceBlock);
    wrapper.appendChild(metaBar);
    wrapper.appendChild(ceBlock);

    // Bug-Fix Build 117 (2.18): inert-Attribut per Hover-Event toggeln.
    // CSS kann inert nicht entfernen, daher JS-gesteuertes mouseenter/mouseleave.
    // Beim Eintreten: inert entfernen → metaBar und btnComment fokussierbar.
    // Beim Verlassen: inert setzen → AT und Fokus koennen bar nicht mehr erreichen.
    // Beleg: Bugfix Build 117, Projektgespraech 2026-05-08
    wrapper.addEventListener('mouseenter', () => {
        metaBar.removeAttribute('inert');
    });
    wrapper.addEventListener('mouseleave', () => {
        // Nur inert setzen, wenn der Fokus nicht innerhalb der metaBar ist
        if (!metaBar.contains(document.activeElement)) {
            metaBar.setAttribute('inert', '');
        }
    });
    // Wenn Fokus metaBar verlässt (z.B. Tab-Navigation heraus): inert wieder setzen
    metaBar.addEventListener('focusout', (e) => {
        if (!metaBar.contains(e.relatedTarget)) {
            metaBar.setAttribute('inert', '');
        }
    });

    // Fremde Bloecke: contenteditable deaktivieren
    if (!isOwn) {
        ceBlock.querySelectorAll('[contenteditable]').forEach(c => {
            c.contentEditable = 'false';
        });
        ceBlock.classList.add('block-foreign');
    }
}

/**
 * Oeffnet den Kommentar-Abschnitt der Support-Sidebar und
 * setzt den Fokus auf das Eingabefeld.
 * Beleg: Bauplan B6 v0.5 §4.3, §4.4.4, Projektgespraech 2026-05-06
 *
 * @param {string} blockId
 */
function _openCommentAccordion(blockId) {
    const sidebar = document.getElementById('support-sidebar');
    if (!sidebar) return;

    // Kommentar-Akkordeon oeffnen
    const commentSection = sidebar.querySelector('[data-accordion="comments"]');
    if (commentSection) {
        _openAccordionSection(commentSection);
    }

    // Aktiven Block merken (wird von comment_thread.js ausgelesen)
    sidebar.dataset.focusedBlockId = blockId;

    // Eingabefeld fokussieren
    const textarea = sidebar.querySelector('.comment-input-textarea');
    if (textarea) {
        textarea.focus();
    }

    // Fokussierten Block im Editor visuell hervorheben
    document.querySelectorAll('.block-wrapper--comment-focus').forEach(w => {
        w.classList.remove('block-wrapper--comment-focus');
    });
    const wrapper = document.querySelector(`.block-wrapper[data-block-id="${blockId}"]`);
    if (wrapper) {
        wrapper.classList.add('block-wrapper--comment-focus');
    }
}

/**
 * Klappt einen Akkordeon-Abschnitt auf und alle anderen zu.
 * Beleg: Bauplan B6 v0.5 §4.4, Projektgespraech 2026-05-06
 *
 * @param {Element} section  Das .support-accordion-section-Element
 */
function _openAccordionSection(section) {
    const sidebar = document.getElementById('support-sidebar');
    if (!sidebar) return;

    sidebar.querySelectorAll('.support-accordion-section').forEach(s => {
        const isTarget = s === section;
        const body = s.querySelector('.support-accordion-body');
        const btn  = s.querySelector('.support-accordion-toggle');
        const expanded = isTarget;
        s.classList.toggle('support-accordion-section--open', expanded);
        if (body)  body.hidden = !expanded;
        if (btn)   btn.setAttribute('aria-expanded', String(expanded));
    });

    // Zustand in localStorage sichern
    try {
        const key = section.dataset.accordion;
        if (key) localStorage.setItem('b6_sidebar_open', key);
    } catch (_) {}

    // B6 Phase 6: Formular-Akkordeon geoeffnet -> showPlaceholderForm() aufrufen
    // Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
    if (section.dataset.accordion === 'form') {
        _refreshPlaceholderForm();
    }

    // Bug-Fix Build 119 (2.24): Blauen Rahmen nur bereinigen wenn das
    // Formular-Akkordeon VORHER offen war und jetzt ein ANDERER Abschnitt
    // geoeffnet wird. Vorher wurde der Rahmen bei jedem Akkordeon-Wechsel
    // geloescht — auch wenn das Formular gerade erst geoeffnet wurde.
    // Pruefung: vorher-offener Abschnitt war 'form' UND neuer ist nicht 'form'.
    // Beleg: Bugfix Build 119, Projektgespraech 2026-05-08
    const previousOpen = (() => {
        try { return localStorage.getItem('b6_sidebar_open'); } catch(_) { return null; }
    })();
    if (previousOpen === 'form' && section.dataset.accordion !== 'form') {
        if (typeof window.PlaceholderWizard?.getCurrentBlockId === 'function') {
            const lastId = window.PlaceholderWizard.getCurrentBlockId();
            if (lastId) {
                window.CommentThread?._clearEditorBlockPulse?.(lastId);
            }
        }
    }

    // B6 Phase 7: Bausteine-Akkordeon geoeffnet -> _refreshModulePanel() aufrufen
    // Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
    if (section.dataset.accordion === 'blocks') {
        _refreshModulePanel();
    }

    // B6 Phase 8: Annotationen-Akkordeon geoeffnet -> _refreshAnnotationSidebar() aufrufen
    // Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
    if (section.dataset.accordion === 'annotations') {
        _refreshAnnotationSidebar();
    }
}

/**
 * Initialisiert den BlockWrapperManager:
 *   1. Bestehende .ce-block-Elemente sofort wrappen.
 *   2. MutationObserver auf #editorjs-holder beobachtet neu eingefuegte Bloecke.
 *
 * Muss aufgerufen werden nachdem loadReport() den Editor initialisiert hat
 * und die Bloecke geladen wurden.
 * Beleg: Bauplan B6 v0.5 §4.3, Projektgespraech 2026-05-06
 *
 * @param {Array}  blocks    Geladene Bloecke [{block_id, author, created_at}]
 * @param {string} username  Eigener SAMAccountName
 */
function initBlockWrappers(blocks, username) {
    const holder = document.getElementById('editorjs-holder');
    if (!holder) return;

    // Index: block_id -> Metadaten (fuer schnellen Zugriff im Observer)
    const blockIndex = Object.create(null);
    blocks.forEach(b => { blockIndex[b.block_id] = b; });

    // Hilfsfunktion: ein .ce-block wrappen wenn block_id bekannt
    function tryWrap(ceBlock) {
        const blockId = ceBlock.dataset?.id;
        if (!blockId) return;
        const meta = blockIndex[blockId];
        if (!meta) return;
        _wrapBlock(ceBlock, meta, username);
    }

    // 1. Bestehende Bloecke sofort wrappen (Editor.js hat sie bereits gerendert)
    holder.querySelectorAll('.ce-block').forEach(tryWrap);

    // 2. MutationObserver fuer dynamisch eingefuegte Bloecke
    // (Editor.js fuegt neue .ce-block-Elemente bei Benutzeraktion ein)
    if (_blockWrapperObserver) {
        _blockWrapperObserver.disconnect();
    }
    _blockWrapperObserver = new MutationObserver(mutations => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) {
                if (!(node instanceof Element)) continue;
                // Direkt eingefuegter .ce-block
                if (node.classList.contains('ce-block')) {
                    tryWrap(node);
                }
                // Untergeordnete .ce-block-Elemente (z.B. bei Batch-Rendering)
                node.querySelectorAll?.('.ce-block').forEach(tryWrap);
            }
        }
    });
    _blockWrapperObserver.observe(holder, { childList: true, subtree: true });
}

// MutationObserver-Instanz (Modul-Scope, damit disconnect() moeglich ist)
// Beleg: Bauplan B6 v0.5 §4.3, Projektgespraech 2026-05-06
let _blockWrapperObserver = null;

// ---------------------------------------------------------------------------
// Platzhalter-Chip Doppelklick (B6 Phase 5)
// Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

/**
 * Registriert Doppelklick-Handler auf dem #editorjs-holder.
 * Doppelklick auf einen .ph-chip oeffnet den Formular-Akkordeon-Abschnitt
 * in der Support-Sidebar und setzt den Fokus auf das zugehoerige Feld.
 * Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
 */
function _bindChipDoubleClick() {
    const holder = document.getElementById('editorjs-holder');
    if (!holder) return;

    holder.addEventListener('dblclick', (e) => {
        const chip = e.target.closest('.ph-chip');
        if (!chip) return;

        e.preventDefault();
        e.stopPropagation();

        const fieldName = chip.dataset.chipName;
        const chipType  = chip.dataset.chipType;

        // a:-Chips (automatisch) brauchen kein Formular
        if (chipType === 'a') return;

        // Formular-Akkordeon in Support-Sidebar oeffnen
        const sidebar = document.getElementById('support-sidebar');
        if (!sidebar) return;

        const formSection = sidebar.querySelector('[data-accordion="form"]');
        if (formSection && typeof _openAccordionSection === 'function') {
            _openAccordionSection(formSection);
        }

        // Fokussiertes Feld fuer Phase 6 merken (PlaceholderWizard)
        sidebar.dataset.focusedChipName  = fieldName || '';
        sidebar.dataset.focusedChipType  = chipType  || '';

        // PlaceholderWizard (Phase 6) vorbereiten: openAtField wenn vorhanden
        if (window.PlaceholderWizard?.openAtField && _currentReport) {
            // Blockinhalt aus Editor.js fuer den Wizard holen
            _editor?.save?.().then(data => {
                if (!data) return;
                // Block finden der den angeklickten Chip enthaelt
                const ceBlock = chip.closest('[data-id]');
                const blockId = ceBlock?.dataset?.id;
                const block   = data.blocks?.find(b => b.id === blockId);
                if (!block) return;

                // Dehydrierter Text (Template-Syntax) fuer den Wizard
                const rawText = window.PlaceholderChips?.dehydrateChips?.(
                    block.data?.text || ''
                ) || '';

                window.PlaceholderWizard.openAtField({
                    blockId:     blockId,
                    moduleTitle: chip.dataset.chipDescription || fieldName,
                    bodyText:    rawText,
                    values:      {},
                    onSave:      () => {},
                }, fieldName);
            }).catch(() => {});
        }

        console.debug('report_editor.js: Chip-Doppelklick:', fieldName, chipType);
    });
}

// ---------------------------------------------------------------------------
// Support-Sidebar Akkordeon (B6 Phase 3)
// Beleg: Bauplan B6 v0.5 §4.4, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

/**
 * Initialisiert das vierstufige Akkordeon der Support-Sidebar.
 * Liest den zuletzt geoeffneten Abschnitt aus localStorage und stellt ihn
 * wieder her. Registriert Click-Handler auf allen Toggle-Schaltflaechen.
 * Beleg: Bauplan B6 v0.5 §4.4, Projektgespraech 2026-05-06
 */
// ---------------------------------------------------------------------------
// Platzhalter-Formular (B6 Phase 6)
// Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

/**
 * Ruft showPlaceholderForm() mit dem aktuellen Editor-Zustand auf.
 * Wird von _openAccordionSection() aufgerufen wenn das Formular-Akkordeon
 * geoeffnet wird.
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
 */
async function _refreshPlaceholderForm() {
    if (!window.PlaceholderWizard?.showPlaceholderForm) return;
    // Build 114: Form auch zeigen wenn Bericht geladen aber noch keine Bloecke existieren
    if (!_currentReport) return;

    // placeholder_values_json aus dem Server laden (aktuellste Werte)
    let blocks = _currentBlocks;
    try {
        const resp = await fetch('/_forensic/placeholders/values', {
            headers: { 'X-Forensic-Request': 'ajax' },
        });
        if (resp.ok) {
            const valuesMap = await resp.json();
            // Werte in die Bloecke einmergen (ohne _currentBlocks zu mutieren)
            blocks = _currentBlocks.map(b => ({
                ...b,
                placeholder_values_json: JSON.stringify(valuesMap[b.block_id] || {}),
            }));
        }
    } catch (_) {}

    // Aktiven Block bestimmen: Sidebar-Datensatz oder erster Block
    const sidebar = document.getElementById('support-sidebar');
    const focusedId = sidebar?.dataset?.focusedBlockId
        || (blocks.length ? blocks[0].block_id : null);

    const username = document.getElementById('report-editor-body')?.dataset?.username || '';

    window.PlaceholderWizard.showPlaceholderForm(blocks, focusedId, {
        myUsername: username,
        onSave:     _onPlaceholderFieldSave,
    });
}

/**
 * Speichert einen einzelnen Platzhalter-Feldwert fuer einen Block.
 * Wird als onSave-Callback von showPlaceholderForm() aufgerufen.
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
 *
 * @param {string} blockId
 * @param {string} fieldName
 * @param {string} value
 */
async function _onPlaceholderFieldSave(blockId, fieldName, value) {
    if (!blockId || !fieldName) return;
    if (!window.EditorState?.lockId) return;   // kein Lock = kein Schreiben

    // Aktuelle Werte des Blocks zusammenfuehren
    const block = _currentBlocks.find(b => b.block_id === blockId);
    let existing = {};
    try {
        if (block?.placeholder_values_json) {
            existing = JSON.parse(block.placeholder_values_json);
        }
    } catch (_) {}
    const newValues = { ...existing, [fieldName]: value };

    const resp = await _fetchWithLock(EDITOR_API.BLOCK, {
        action:                  'update_block',
        block_id:                blockId,
        block_data:              block?.block_data || '{}',
        placeholder_values_json: JSON.stringify(newValues),
    });
    if (resp && !resp.ok) {
        const err = await resp.json().catch(() => ({}));
        console.warn('report_editor.js: Platzhalter-Save fehlgeschlagen:', fieldName, err);
    }
}

// ---------------------------------------------------------------------------
// Bausteine-Panel (B6 Phase 7)
// Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

/**
 * Ruft ModulePanel.showPanel() mit dem aktuellen Editor-Zustand auf.
 * Wird von _openAccordionSection() aufgerufen wenn das Bausteine-Akkordeon
 * geoeffnet wird.
 * Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
 */
function _refreshModulePanel() {
    if (!window.ModulePanel?.showPanel) return;

    const lockId   = window.EditorState?.lockId || null;
    const reportId = _currentReport?.id || null;

    window.ModulePanel.showPanel(_currentBlocks, {
        reportId,
        lockId,
        onInserted: async (blockId, moduleId, bodyText) => {
            // Nach Einfuegen: Editor-Daten neu laden
            // Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
            if (_currentReport) {
                await _loadBlocksAndReinit(_currentReport);
            }

            // Formular-Akkordeon automatisch oeffnen wenn m: oder o:-Felder vorhanden
            const chips = window.PlaceholderChips;
            const hasMO = chips && bodyText && (
                chips.extractFields(bodyText, 'm').length > 0 ||
                chips.extractFields(bodyText, 'o').length > 0
            );
            if (hasMO) {
                const sidebar     = document.getElementById('support-sidebar');
                const formSection = sidebar?.querySelector('[data-accordion="form"]');
                if (formSection) {
                    _openAccordionSection(formSection);
                    // PlaceholderWizard auf neuen Block fokussieren
                    if (blockId && typeof window.PlaceholderWizard?.focusBlock === 'function') {
                        window.PlaceholderWizard.focusBlock(blockId);
                    }
                }
            }
        },
    });
}

/**
 * Laedt die Bloecke neu und aktualisiert den Editor-State.
 * Leichter als loadReport() — kein Editor-Destroy/Reinit.
 * Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
 */
async function _loadBlocksAndReinit(report) {
    try {
        const resp = await fetch('/_forensic/report?format=json', {
            headers: { 'X-Forensic-Request': 'ajax' },
        });
        if (resp.ok) {
            const data = await resp.json();
            _currentBlocks = data.blocks || [];
        }
    } catch (_) {}
}

// ---------------------------------------------------------------------------
// Annotationen-Sidebar (B6 Phase 8)
// Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

/**
 * Ruft AnnotationSidebar.showSidebar() mit dem aktuellen Editor-Zustand auf.
 * Wird von _openAccordionSection() aufgerufen wenn das Annotationen-Akkordeon
 * geoeffnet wird.
 * Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
 */
function _refreshAnnotationSidebar() {
    if (!window.AnnotationSidebar?.showSidebar) return;

    const lockId   = window.EditorState?.lockId || null;
    const username = document.getElementById('report-editor-body')?.dataset?.username || '';

    window.AnnotationSidebar.showSidebar(_currentBlocks, {
        lockId,
        getActiveBlockId: () => {
            // Aktiven Block-ID aus dem Editor holen (zuletzt fokussierter Block)
            if (!_editor) return null;
            try {
                const idx = _editor.blocks.getCurrentBlockIndex();
                if (idx < 0) return null;
                const block = _editor.blocks.getBlockByIndex(idx);
                return block?.id || null;
            } catch (_) { return null; }
        },
        onAnchorAdded: (annId, blockId) => {
            // Nach Anker-Einfuegen: Bloecke neu laden
            // Beleg: Bauplan B6 v0.5 §4.4.2
            if (_currentReport) {
                _loadBlocksAndReinit(_currentReport);
            }
            console.debug('report_editor.js: Anker eingefuegt:', annId, '->', blockId);
        },
    });
}

function _initSidebarAccordion() {
    _dbg('_initSidebarAccordion() gestartet');
    const sidebar = document.getElementById('support-sidebar');
    if (!sidebar) return;

    // Letzten Zustand aus localStorage lesen (Standard: 'blocks')
    let lastOpen = 'blocks';
    try {
        lastOpen = localStorage.getItem('b6_sidebar_open') || 'blocks';
    } catch (_) {}

    // Toggle-Handler auf jeder Sektion registrieren
    sidebar.querySelectorAll('.support-accordion-section').forEach(section => {
        const btn  = section.querySelector('.support-accordion-toggle');
        const body = section.querySelector('.support-accordion-body');
        if (!btn || !body) return;

        btn.addEventListener('click', () => {
            const isOpen = section.classList.contains('support-accordion-section--open');
            if (isOpen) return;  // Aufgeklappter Abschnitt bleibt offen
            _openAccordionSection(section);
        });

        // Tastatur: Enter und Space oeffnen Sektion
        btn.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                btn.click();
            }
        });
    });

    // Letzten Zustand wiederherstellen
    const toOpen = sidebar.querySelector(`[data-accordion="${lastOpen}"]`);
    if (toOpen) {
        _openAccordionSection(toOpen);
    } else {
        // Fallback: ersten Abschnitt oeffnen
        const first = sidebar.querySelector('.support-accordion-section');
        if (first) _openAccordionSection(first);
    }
}

// ---------------------------------------------------------------------------
// Auto-Save
// ---------------------------------------------------------------------------

/**
 * Plant einen Auto-Save mit Debounce.
 * Mehrfache Aufrufe innerhalb von AUTOSAVE_DEBOUNCE_MS werden zusammengefasst.
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 * @param {number} reportId
 */
function _scheduleAutoSave(reportId) {
    if (_saveTimer) clearTimeout(_saveTimer);
    _saveTimer = setTimeout(() => _performAutoSave(reportId), AUTOSAVE_DEBOUNCE_MS);
}

/**
 * Auto-Save: speichert alle geaenderten Bloecke.
 * Nur wenn Lock gehalten wird.
 * @param {number} reportId
 */
async function _performAutoSave(reportId) {
    if (!window.EditorState?.lockId) return;
    if (!_editor) return;

    let editorData;
    try {
        editorData = await _editor.save();
    } catch (err) {
        console.warn('report_editor.js: Editor.save() fehlgeschlagen:', err);
        return;
    }

    const username = document.getElementById('report-editor-body')?.dataset?.username || '';

    for (const block of editorData.blocks) {
        // B6 Phase 5: Chips aus block_data.text dehydrieren (gerendertes HTML -> Template-Syntax)
        // bevor gespeichert wird, damit block_data immer rohe Template-Syntax enthaelt.
        // Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
        let blockDataToSave = block.data;
        if (block.data && block.data.text && window.PlaceholderChips?.dehydrateChips) {
            blockDataToSave = {
                ...block.data,
                text: window.PlaceholderChips.dehydrateChips(block.data.text),
            };
        }
        const resp = await _fetchWithLock(EDITOR_API.BLOCK, {
            action:     'save',
            block_id:   block.id,
            report_id:  reportId,
            block_type: block.type,
            block_data: blockDataToSave,
            owner:      username,
        });
        if (resp && !resp.ok) {
            const err = await resp.json().catch(() => ({}));
            console.warn('report_editor.js: Block-Save fehlgeschlagen:', block.id, err);
        }
    }

    // Blockreihenfolge speichern (Fractional Indexing: einfaches 'a0', 'a1', ... fuer jetzt)
    // AP-E4: vollstaendiges Fractional Indexing in einem Folgebuild
    const orderPayload = editorData.blocks.map((b, i) => ({
        block_id:   b.id,
        sort_index: String(i).padStart(6, '0'),  // '000000', '000001', ...
    }));
    if (orderPayload.length) {
        await _fetchWithLock(EDITOR_API.ORDER, {
            report_id: reportId,
            order:     orderPayload,
        });
    }

    _showSaveIndicator();
}

/** Kurze "Gespeichert"-Anzeige */
function _showSaveIndicator() {
    const el = document.getElementById('editor-save-indicator');
    if (!el) return;
    el.textContent = '✓ Gespeichert';
    el.style.opacity = '1';
    setTimeout(() => { el.style.opacity = '0'; }, 2000);
}

// ---------------------------------------------------------------------------
// EvidenceBlock — custom Editor.js Tool
// ---------------------------------------------------------------------------

/**
 * EvidenceBlock — eingebettete Beweismittelgruppe.
 *
 * Rendert eine Liste von Annotationen als forensische Beweiskarte.
 * Datenformat:
 *   { evidence_ids: [42, 43, 47], group_label: "...", display_mode: "list" }
 *
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 */
class EvidenceBlock {
    static get toolbox() {
        return { title: 'Beweismittel', icon: '⚖' };
    }

    static get isReadOnlySupported() { return true; }

    constructor({ data, api, readOnly }) {
        this._api      = api;
        this._readOnly = readOnly;
        this._data     = {
            evidence_ids:  data.evidence_ids  || [],
            group_label:   data.group_label   || '',
            display_mode:  data.display_mode  || 'list',
        };
        this._wrapper  = null;
    }

    render() {
        this._wrapper = document.createElement('div');
        this._wrapper.className = 'evidence-block';
        this._renderContent();

        // Drag-Drop-Ziel: Annotationen aus Sidebar fallen lassen
        if (!this._readOnly) {
            this._wrapper.addEventListener('dragover', e => {
                e.preventDefault();
                this._wrapper.classList.add('evidence-block--dragover');
            });
            this._wrapper.addEventListener('dragleave', () => {
                this._wrapper.classList.remove('evidence-block--dragover');
            });
            this._wrapper.addEventListener('drop', async (e) => {
                e.preventDefault();
                this._wrapper.classList.remove('evidence-block--dragover');
                const annId = parseInt(e.dataTransfer.getData('text/x-annotation-id'), 10);
                if (!annId) return;
                await this._addEvidence(annId);
            });
        }

        return this._wrapper;
    }

    _renderContent() {
        const ids    = this._data.evidence_ids;
        const label  = this._data.group_label;
        const escFn  = window.esc || (s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'));

        let idsHtml = ids.length
            ? ids.map(id => `<span class="evidence-id-chip" data-id="${id}">⚖ Beleg #${id}
                ${!this._readOnly ? `<button class="evidence-remove-btn" data-id="${id}" title="Entfernen">×</button>` : ''}
                </span>`).join('')
            : '<span class="evidence-empty">Noch kein Beleg — aus Sidebar ziehen oder via Schaltfläche hinzufügen.</span>';

        this._wrapper.innerHTML = `
            <div class="evidence-block-header">
                <span class="evidence-block-icon">⚖</span>
                <span class="evidence-block-title">Beweismittelgruppe</span>
            </div>
            ${!this._readOnly ? `<input class="evidence-label-input" type="text"
                value="${escFn(label)}" placeholder="Beschriftung (optional)">` : (label ? `<div class="evidence-label">${escFn(label)}</div>` : '')}
            <div class="evidence-ids">${idsHtml}</div>
            ${!this._readOnly ? `<div class="evidence-actions">
                <button class="editor-btn evidence-add-btn" style="font-size:11px">+ Beleg hinzufügen</button>
            </div>` : ''}`;

        // Label-Eingabe verdrahten
        this._wrapper.querySelector('.evidence-label-input')?.addEventListener('input', e => {
            this._data.group_label = e.target.value;
        });

        // Entfernen-Buttons
        this._wrapper.querySelectorAll('.evidence-remove-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = parseInt(btn.dataset.id, 10);
                await this._removeEvidence(id);
            });
        });

        // Hinzufügen-Button: öffnet Sidebar
        this._wrapper.querySelector('.evidence-add-btn')?.addEventListener('click', () => {
            toggleAnnotationSidebar(this);
        });
    }

    async _addEvidence(annotationId) {
        if (this._data.evidence_ids.includes(annotationId)) return;
        const blockId = this._api.blocks.getCurrentBlockIndex !== undefined
            ? this._getBlockId()
            : null;

        if (blockId) {
            const resp = await _fetchWithLock(EDITOR_API.EVIDENCE, {
                action:      'add',
                block_id:    blockId,
                evidence_id: annotationId,
            });
            if (resp && !resp.ok) {
                console.warn('report_editor.js: Evidence-Add fehlgeschlagen:', annotationId);
                return;
            }
        }
        this._data.evidence_ids = [...this._data.evidence_ids, annotationId];
        this._renderContent();
    }

    async _removeEvidence(annotationId) {
        const blockId = this._getBlockId();
        if (blockId) {
            const resp = await _fetchWithLock(EDITOR_API.EVIDENCE, {
                action:      'remove',
                block_id:    blockId,
                evidence_id: annotationId,
            });
            if (resp && !resp.ok) {
                console.warn('report_editor.js: Evidence-Remove fehlgeschlagen:', annotationId);
                return;
            }
        }
        this._data.evidence_ids = this._data.evidence_ids.filter(id => id !== annotationId);
        this._renderContent();
    }

    _getBlockId() {
        // Editor.js Block-ID aus dem DOM ermitteln
        return this._wrapper?.closest('[data-id]')?.dataset?.id || null;
    }

    save(blockContent) {
        const label = blockContent.querySelector('.evidence-label-input')?.value || this._data.group_label;
        return {
            evidence_ids: this._data.evidence_ids,
            group_label:  label,
            display_mode: this._data.display_mode,
        };
    }

    static get sanitize() {
        return {
            evidence_ids: false,
            group_label:  { br: false },
            display_mode: false,
        };
    }
}

// ---------------------------------------------------------------------------
// Annotations-Sidebar (Drag-and-Drop-Quelle)
// ---------------------------------------------------------------------------

/**
 * Annotations-Sidebar ein-/ausblenden.
 * Laedt alle Annotationen und rendert sie als ziehbare Karten.
 * @param {EvidenceBlock|null} targetBlock  Ziel-Block fuer direktes Hinzufuegen
 */
/**
 * Oeffnet die Annotationssidebar.
 *
 * Phase 8: Leitet auf das Annotationen-Akkordeon in der Support-Sidebar um.
 * Das alte floatende Panel wird nicht mehr benutzt.
 * targetBlock wird an EvidenceBlock._addEvidence uebergeben wenn per
 * Direktklick aufgerufen — das Drag-and-Drop in die EvidenceBlock-Flaeche
 * funktioniert weiterhin direkt ueber text/x-annotation-id.
 * Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
 *
 * @param {Object|null} targetBlock  -- EvidenceBlock-Instanz oder null
 */
async function toggleAnnotationSidebar(targetBlock = null) {
    // Annotationen-Akkordeon in der Support-Sidebar oeffnen
    const sidebar      = document.getElementById('support-sidebar');
    const annSection   = sidebar?.querySelector('[data-accordion="annotations"]');
    if (annSection) {
        _openAccordionSection(annSection);
    }
}

// ---------------------------------------------------------------------------
// window.postMessage-Handler (Option a: Annotation aus Fenster 2 einfügen)
// ---------------------------------------------------------------------------

/**
 * Empfaengt Nachrichten aus Fenster 2 (Nutzerinfo-Tab).
 * Erwartet: { type: 'insert_evidence', annotation_id: N }
 * Fuegt einen neuen EvidenceBlock am Ende des Editors ein.
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 */
window.addEventListener('message', async (evt) => {
    if (!evt.data || evt.data.type !== 'insert_evidence') return;
    const annotationId = parseInt(evt.data.annotation_id, 10);
    if (!annotationId || !_editor || !_currentReport) return;
    if (!window.EditorState?.lockId) {
        console.warn('report_editor.js: insert_evidence: Kein Lock — Einfuegen abgebrochen');
        return;
    }

    // Neuen EvidenceBlock am Ende des Dokuments einfuegen
    const blockId = crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);
    await _editor.blocks.insert('evidence', {
        evidence_ids: [annotationId],
        group_label:  '',
        display_mode: 'list',
    }, {}, undefined, true);

    // Evidence-Verknuepfung serverseitig speichern
    await _fetchWithLock(EDITOR_API.EVIDENCE, {
        action:      'add',
        block_id:    blockId,
        evidence_id: annotationId,
    });
});

// ---------------------------------------------------------------------------
// SSE block_updated-Handler
// ---------------------------------------------------------------------------

/**
 * Registriert sich am bestehenden SSE-Stream fuer block_updated-Events.
 * Wird von initEditorModule() aufgerufen.
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 */
function initBlockUpdatedListener() {
    // SSE-Verbindung wird von userinfo.js gehalten (window._forensicEvtSrc)
    const evtSrc = window._forensicEvtSrc;
    if (!evtSrc) return;

    evtSrc.addEventListener('block_updated', async (evt) => {
        try {
            const { block_id } = JSON.parse(evt.data);
            if (!block_id || !_editor || !_currentReport) return;
            // Block neu laden und rendern
            await _reloadBlock(block_id);
        } catch (_) {}
    });
}

/**
 * Einen einzelnen Block neu aus der DB laden und im Editor aktualisieren.
 * @param {string} blockId
 */
async function _reloadBlock(blockId) {
    // Aktuellen Editor-Zustand speichern
    const data = await _editor.save().catch(() => null);
    if (!data) return;

    const idx = data.blocks.findIndex(b => b.id === blockId);
    if (idx === -1) return;

    // Block-Daten vom Server holen (via report JSON)
    const resp = await fetch(`/_forensic/report?format=json`, {
        headers: { 'X-Forensic-Request': 'ajax' }
    });
    if (!resp.ok) return;
    const reportData = await resp.json();
    const report = (reportData.reports || []).find(r => r.id === _currentReport?.id);
    if (!report) return;
    const block = (report.blocks || []).find(b => b.block_id === blockId);
    if (!block) return;

    // Editor.js unterstuetzt kein partielles Update — Block ersetzen
    _editor.blocks.update(blockId, typeof block.block_data === 'string'
        ? JSON.parse(block.block_data)
        : block.block_data
    ).catch(() => {});
}

// ---------------------------------------------------------------------------
// Fenster-2-Erweiterung: "In Bericht einfügen"-Button
// ---------------------------------------------------------------------------

/**
 * Erweitert Annotationskarten in Fenster 2 um einen "In Bericht"-Button.
 * Sendet window.postMessage an das Editor-Fenster (Option a).
 * Muss von userinfo.js nach dem Rendern der Annotationen aufgerufen werden.
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 */
function injectInsertInReportButtons() {
    // Alle Annotationskarten in Fenster 2 erweitern
    document.querySelectorAll('[data-annotation-id]').forEach(card => {
        if (card.querySelector('.btn-insert-in-report')) return;  // bereits vorhanden
        const annId = card.dataset.annotationId;
        if (!annId) return;
        const btn = document.createElement('button');
        btn.className = 'editor-btn btn-insert-in-report';
        btn.textContent = '→ In Bericht';
        btn.title = 'Diesen Beleg in den Berichts-Editor einfügen';
        btn.style.cssText = 'font-size:11px;padding:2px 6px;margin-left:6px';
        btn.addEventListener('click', () => {
            const editorWin = window.open('', 'forensic_report');
            editorWin?.postMessage(
                { type: 'insert_evidence', annotation_id: parseInt(annId, 10) },
                window.location.origin
            );
        });
        card.querySelector('.editor-paragraph-actions, .annotation-actions, div')?.appendChild(btn);
    });
}

// ---------------------------------------------------------------------------
// Öffentliche Initialisierungsfunktion
// ---------------------------------------------------------------------------

/**
 * Initialisiert das Editor-Modul fuer Fenster 3.
 * Wird von userinfo.js (initEditor) aufgerufen nach Lock/SSE-Setup.
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 */
/**
 * Initialisiert Drag&Drop-Empfang auf dem Editor-Bereich.
 * Bausteine aus der Sidebar koennen per Drag in den Editor gezogen werden.
 * Build 115: Beleg: Projektgespraech 2026-05-07
 */
function _initDragDrop() {
    const holder = document.getElementById('editorjs-holder');
    if (!holder) return;

    holder.addEventListener('dragover', (e) => {
        if (!e.dataTransfer.types.includes('application/x-forensic-module')) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        holder.classList.add('editorjs-holder--drag-over');
    });

    holder.addEventListener('dragleave', () => {
        holder.classList.remove('editorjs-holder--drag-over');
    });

    holder.addEventListener('drop', async (e) => {
        holder.classList.remove('editorjs-holder--drag-over');
        if (!e.dataTransfer.types.includes('application/x-forensic-module')) return;
        e.preventDefault();

        let modData;
        try {
            modData = JSON.parse(e.dataTransfer.getData('application/x-forensic-module'));
        } catch (_) { return; }

        _dbg('Drop: module_id=', modData.module_id);

        if (!window._editor?.blocks) {
            _dbg('Drop: Editor nicht bereit');
            return;
        }

        // Block am Ende einfuegen
        const blockData = modData.block_type === 'paragraph'
            ? { text: modData.module_text || '' }
            : {};
        window._editor.blocks.insert(modData.block_type || 'paragraph', blockData);
        const lastIdx = window._editor.blocks.getBlocksCount() - 1;
        window._editor.caret.setToBlock(lastIdx);
        _dbg('Drop: Block eingefuegt, type=', modData.block_type, 'idx=', lastIdx);
    });

    _dbg('_initDragDrop: Drop-Zone registriert auf #editorjs-holder');
}

async function initEditorModule() {
    _dbg('initEditorModule() gestartet');
    // Akkordeon-Listener sofort verdrahten — unabhaengig von Berichten und EditorJS.
    // Beleg: Bugfix Build 111, Projektgespraech 2026-05-07
    _initSidebarAccordion();
    // Build 115: Drag&Drop-Zone auf editorjs-holder registrieren
    _initDragDrop();
    await initReportSelector();
    initBlockUpdatedListener();
}

/**
 * Editor nach Lock-Erwerb neu initialisieren (readOnly: false).
 * Wird von userinfo.js nach erfolgreichem acquireLock() aufgerufen.
 * Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
 */
async function _reinitWithLock() {
    if (!_currentReport) return;

    // Lock-ID vor dem destroy() sichern — nach await koennte EditorState
    // durch einen parallel eintreffenden SSE-Event zurueckgesetzt worden sein.
    // Beleg: AP-E4 Bugfix, Projektgespraech 2026-04-19
    const lockIdSnapshot = window.EditorState?.lockId;
    if (!lockIdSnapshot) {
        console.debug('report_editor.js: _reinitWithLock: kein Lock — abgebrochen');
        return;
    }
    // Flag setzen: verhindert doppelten Aufruf via SSE-Handler
    window._reinitInProgress = true;

    // Bestehenden Editor zerstoeren
    if (_editor) {
        try { await _editor.destroy(); } catch (_) {}
        _editor = null;
        window._editor = null;
    }

    // Sicherstellen dass lockId nach dem destroy() noch gesetzt ist
    if (window.EditorState && !window.EditorState.lockId) {
        window.EditorState.lockId = lockIdSnapshot;
    }

    // Neu laden — jetzt mit gesetztem lockId
    try {
        await loadReport(_currentReport);
    } finally {
        window._reinitInProgress = false;
    }
}

// Im globalen Scope bereitstellen
_dbg('report_editor.js: Exports auf window gesetzt');
window.initEditorModule            = initEditorModule;
window.injectInsertInReportButtons = injectInsertInReportButtons;
window.toggleAnnotationSidebar     = toggleAnnotationSidebar;
window.EvidenceBlock               = EvidenceBlock;
// Phase 3: BlockWrapper und Akkordeon
// Beleg: Bauplan B6 v0.5 §4.3, §4.4, Projektgespraech 2026-05-06
window.initBlockWrappers           = initBlockWrappers;
window.openAccordionSection        = _openAccordionSection;
window.ownerColor                  = _ownerColor;
// Konstante exportieren fuer Tests und externe Konfigurationspruefung
// Beleg: AP-E4, Projektgespraech 2026-04-19
window.AUTOSAVE_DEBOUNCE_MS        = AUTOSAVE_DEBOUNCE_MS;

/**
 * Placeholder im Editor aktualisieren nach readOnly-Aenderung.
 * Wird von userinfo.js nach releaseLock() / _reinitWithLock() aufgerufen.
 * Beleg: Bugfix Build 050, Projektgespraech 2026-04-21
 * @param {boolean} hasLock
 */
window.updateEditorPlaceholder = function(hasLock) {
    const text = hasLock
        ? 'Schreiben beginnen…'
        : 'Lock erwerben um zu schreiben…';
    // Editor.js setzt den Placeholder als data-placeholder auf .ce-paragraph
    document.querySelectorAll('.ce-paragraph[data-placeholder-active]').forEach(el => {
        el.setAttribute('data-placeholder-active', text);
    });
    document.querySelectorAll('.ce-paragraph[data-placeholder]').forEach(el => {
        el.setAttribute('data-placeholder', text);
    });
};
window._reinitWithLock             = _reinitWithLock;

})();
