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
 *   Build 129 (2026-05-09): Bug 2.38 behoben — Block-Klick-Handler entfernt.
 *     Kein automatisches Oeffnen von Kommentare bei jedem Block-Klick mehr.
 *     Kommentiere-Button in .block-meta-bar ist der einzige Einstiegspunkt.
 *     Beleg: Bugfix Build 129, Projektgespraech 2026-05-09.
 *
 *   Build 130 (2026-05-09): Bug 2.39 + Bug 2.27 behoben.
 *     - Bug 2.39: _performAutoSave erkennt geloeschte Bloecke per _knownBlockIds-Set
 *       und sendet delete_block fuer jeden Block, der nicht mehr im Editor vorhanden ist.
 *     - Bug 2.27: Speicher-Indikator drei sichtbare Zustaende: idle/saving/saved.
 *     Beleg: Bugfix Build 130, Projektgespraech 2026-05-09.
 *
 *   Build 134 (2026-05-09): Bug 2.5 behoben.
 *     Drucken-Schaltflaeche (btn-print) loest jetzt window.print() aus.
 *     Wenn ein Lock besteht, wird vor dem Drucken ein letzter Auto-Save
 *     ausgefuehrt damit der gedruckte Stand mit der DB synchron ist.
 *     Beleg: Bugfix Build 134, Projektgespraech 2026-05-09.
 *
 * Version: v0.6.137 · Build: 137 · 2026-05-09
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

/**
 * Set der Block-IDs, die dem Server zuletzt bekannt waren.
 * Wird nach jedem erfolgreichen _performAutoSave aktualisiert.
 * Beim Auto-Save werden Block-IDs, die in _knownBlockIds sind aber nicht mehr
 * in editorData.blocks, als geloescht erkannt und per delete_block entfernt.
 * Beleg: Bugfix Build 130, Projektgespraech 2026-05-09 (Bug 2.39)
 */
let _knownBlockIds = new Set();

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
    // Bug 2.40/2.43 Absicherung Build 136: btn-save-now manueller Speichern-Button.
    // Beleg: Projektgespraech 2026-05-07, 2026-05-09
    ['btn-print', 'btn-export', 'btn-refresh-placeholders', 'btn-save-now'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.disabled = false;
    });

    // Handler fuer manuellen Speichern-Button (Bug 2.40/2.43 Absicherung)
    const btnSaveNow = document.getElementById('btn-save-now');
    if (btnSaveNow && !btnSaveNow._saveHandlerBound) {
        btnSaveNow._saveHandlerBound = true;
        btnSaveNow.addEventListener('click', async () => {
            btnSaveNow.disabled = true;
            btnSaveNow.textContent = '⏳ Speichert…';
            try {
                await _performAutoSave();
            } finally {
                btnSaveNow.disabled = false;
                btnSaveNow.textContent = '💾 Speichern';
            }
        });
    }

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
        // Bug 2.39 Fix Build 130: _knownBlockIds mit den vom Server geladenen
        // Block-IDs initialisieren, damit der Auto-Save Loeschungen erkennen kann.
        // Beleg: Bugfix Build 130, Projektgespraech 2026-05-09
        _knownBlockIds = new Set(existingBlocks.map(b => b.block_id).filter(Boolean));
        console.debug('report_editor.js: _knownBlockIds initialisiert,',
                      _knownBlockIds.size, 'Bloecke geladen.');
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
            // Build 124 Fix: Vor dem Hydrieren zuerst dehydrieren.
            // dehydrateChips ist idempotent auf reiner Template-Syntax.
            // Beleg: Bugfix Build 121/124, Projektgespraech 2026-05-08
            if (raw.text && window.PlaceholderChips?.dehydrateChips) {
                raw.text = window.PlaceholderChips.dehydrateChips(raw.text);
            }
            // B6 Phase 5: Template-Syntax in text-Feld zu Chips hydrieren.
            // NUR wenn Template-Syntax {{...}} vorhanden — sonst wuerde
            // render()/_esc() HTML-Entities wie &lt; nochmals escapen.
            // Beleg: Bugfix Build 124, Projektgespraech 2026-05-08
            if (raw.text && raw.text.includes('{{') && window.PlaceholderChips?.hydrateChips) {
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
 * Dekoriert ein .ce-block-Element mit Metadaten und Hover-Leiste.
 * Idempotent: bereits dekorierte Bloecke werden uebersprungen.
 *
 * Build 120 REDESIGN: statt .ce-block in einen aeusseren Wrapper zu verschieben
 * (was Editor.js DOM-Erwartungen bricht und TypeError in selectionChanged/
 * updateCurrentInput ausloest), werden Dekorationen DIREKT AUF .ce-block gesetzt:
 *   - CSS-Klassen und data-Attribute direkt auf .ce-block
 *   - .block-meta-bar als absolut-positioniertes Kind innerhalb .ce-block
 * Editor.js sieht seine Bloecke weiterhin als direkte Kinder des Holders.
 * Beleg: Bugfix Build 120, Projektgespraech 2026-05-08
 *
 * @param {Element}  ceBlock    .ce-block-DOM-Knoten
 * @param {object}   blockMeta  { block_id, author, created_at } aus blocks-Array
 * @param {string}   username   Eigener SAMAccountName (bestimmt own vs. foreign)
 */
function _wrapBlock(ceBlock, blockMeta, username) {
    // Idempotenz: bereits dekorierte Bloecke ueberspringen
    if (ceBlock.dataset.wrapped) return;
    ceBlock.dataset.wrapped = '1';

    const isOwn   = blockMeta.author === username;
    const color   = _ownerColor(blockMeta.author);
    const created = blockMeta.created_at
        ? new Date(blockMeta.created_at * 1000).toLocaleString('de-DE', {
              day:   '2-digit', month: '2-digit', year: 'numeric',
              hour:  '2-digit', minute: '2-digit',
          })
        : '';

    // Metadaten direkt auf .ce-block setzen — kein DOM-Verschieben.
    ceBlock.classList.add(isOwn ? 'block-wrapper--own' : 'block-wrapper--foreign');
    ceBlock.dataset.blockId = blockMeta.block_id;
    ceBlock.dataset.author  = blockMeta.author;
    ceBlock.style.setProperty('--block-owner-color', color);
    ceBlock.setAttribute('aria-label', isOwn
        ? `Eigener Block (${blockMeta.author})`
        : `Block von ${blockMeta.author}`);

    // .block-meta-bar als absolut-positioniertes Kind in .ce-block injizieren.
    // position: absolute → kein Layout-Shift (Bug 1.14).
    // inert: AT und Fokus erst beim Hover freigeben (Bug 2.18).
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

    // Metazeile als erstes Kind in .ce-block einfuegen (absolut positioniert).
    ceBlock.insertBefore(metaBar, ceBlock.firstChild);

    // Bug 2.34 Fix Build 125: Kommentar-Indikator (Badge) anzeigen.
    // Rot = offene Kommentare, Grau = alle erledigt, keiner = kein Badge.
    // blockMeta.comments kommt aus format=json Response.
    // Beleg: Bugfix Build 125, Projektgespraech 2026-05-08
    const comments = Array.isArray(blockMeta.comments) ? blockMeta.comments : [];
    if (comments.length > 0) {
        const hasPending = comments.some(c => c.status === 'pending');
        const badge = document.createElement('div');
        badge.className = 'block-comment-badge ' +
            (hasPending ? 'block-comment-badge--pending' : 'block-comment-badge--done');
        badge.title = hasPending
            ? `${comments.filter(c => c.status === 'pending').length} offene Kommentare`
            : 'Alle Kommentare erledigt';
        ceBlock.insertBefore(badge, ceBlock.firstChild);
    }

    // inert per mouseenter/mouseleave auf .ce-block toggeln.
    ceBlock.addEventListener('mouseenter', () => {
        metaBar.removeAttribute('inert');
    });
    ceBlock.addEventListener('mouseleave', () => {
        if (!metaBar.contains(document.activeElement)) {
            metaBar.setAttribute('inert', '');
        }
    });
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
/**
 * Aktualisiert die Kommentar-Badges aller bereits gewrappten .ce-block-Elemente.
 *
 * Hintergrund: _wrapBlock() ist idempotent (data-wrapped-Guard) und ueberspringt
 * bereits dekorierte Bloecke. Das Badge wird daher nach einem _loadBlocksAndReinit
 * nicht automatisch aktualisiert — der Block haette nach resolve_comment noch den
 * alten Status (pending), obwohl die DB ihn als addressed/dismissed kennt.
 *
 * Diese Funktion iteriert ueber alle gewrappten .ce-block-Elemente und setzt
 * das Badge neu basierend auf den frisch geladenen _currentBlocks-Daten.
 * Wird nach jedem erfolgreichen _loadBlocksAndReinit aufgerufen.
 *
 * Beleg: Bugfix Build 127, Projektgespraech 2026-05-08
 *
 * @param {Array} blocks  Frisch geladene Bloecke aus _currentBlocks
 */
function _updateBlockBadges(blocks) {
    if (!blocks || !blocks.length) return;

    // Index block_id → Kommentar-Array fuer schnellen Zugriff
    const commentIndex = Object.create(null);
    blocks.forEach(b => {
        if (Array.isArray(b.comments) && b.comments.length > 0) {
            commentIndex[b.block_id] = b.comments;
        }
    });

    document.querySelectorAll('.ce-block[data-wrapped]').forEach(ceBlock => {
        const blockId = ceBlock.dataset.blockId;
        if (!blockId) return;

        // Bestehendes Badge entfernen (wird neu gesetzt)
        const existingBadge = ceBlock.querySelector('.block-comment-badge');
        if (existingBadge) existingBadge.remove();

        const comments = commentIndex[blockId];
        if (!comments || !comments.length) return;

        const hasPending = comments.some(c => c.status === 'pending');
        const badge = document.createElement('div');
        badge.className = 'block-comment-badge ' +
            (hasPending ? 'block-comment-badge--pending' : 'block-comment-badge--done');
        badge.title = hasPending
            ? `${comments.filter(c => c.status === 'pending').length} offene Kommentare`
            : 'Alle Kommentare erledigt';
        // Badge als erstes Kind einfuegen (vor block-meta-bar)
        ceBlock.insertBefore(badge, ceBlock.firstChild);
    });
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

    // Bug 2.15 Fix Build 122: CommentThread.showForBlock() aufrufen.
    // Build 125: myUsername statt investigator in opts (renderForBlock braucht myUsername).
    // Build 126 Fix Bug 3.5/2.31: onReload laedt _currentBlocks vom Server neu bevor
    // der Thread re-rendert. Ohne diesen Reload zeigte showForBlock() den alten
    // Kommentar-Status (pending) obwohl resolve_comment erfolgreich war — weil
    // _currentBlocks noch den veralteten Zustand enthielt. Der User sah den
    // Kommentar weiterhin als offen und klickte erneut (loste die 403-Schleife aus).
    // Beleg: Bugfix Build 126, Projektgespraech 2026-05-08
    if (typeof window.CommentThread?.showForBlock === 'function') {
        const username = document.getElementById('report-editor-body')?.dataset?.username || '';
        const lockId = window.EditorState?.lockId || null;
        const commentOpts = {
            lockId,
            myUsername:  username,
            investigator: username,
            onReload: async () => {
                // Nach Submit/Resolve: _currentBlocks vom Server aktualisieren,
                // DANN Thread mit frischen Daten neu rendern.
                // Verhindert dass geloeste Kommentare weiterhin als 'pending'
                // angezeigt werden (Root-Cause der 403-Retry-Schleife).
                // Beleg: Bugfix Build 126, Projektgespraech 2026-05-08
                if (_currentReport) {
                    await _loadBlocksAndReinit(_currentReport);
                }
                window.CommentThread.showForBlock(blockId, _currentBlocks, commentOpts);
            },
        };
        window.CommentThread.showForBlock(blockId, _currentBlocks, commentOpts);
    }

    // Eingabefeld fokussieren
    setTimeout(() => {
        const textarea = sidebar.querySelector('.comment-input-textarea, .ct-compose textarea');
        if (textarea) textarea.focus();
    }, 80);

    // Fokussierten Block im Editor visuell hervorheben
    document.querySelectorAll('.ce-block.block-wrapper--comment-focus').forEach(w => {
        w.classList.remove('block-wrapper--comment-focus');
    });
    const wrapper = document.querySelector(`.ce-block[data-block-id="${blockId}"]`);
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
        // Build 122 Fix 1.8: hidden-Attribut durch CSS-Klasse ersetzen,
        // damit CSS-Transition animieren kann (hidden=display:none blockiert Transitions).
        // Beleg: Bugfix Build 122, Projektgespraech 2026-05-08
        if (body) {
            body.hidden = false;  // native hidden entfernen
            body.classList.toggle('support-accordion-body--closed', !expanded);
        }
        if (btn)   btn.setAttribute('aria-expanded', String(expanded));
    });

    // Zustand in localStorage sichern
    // Build 122: _previousAccordionKey VOR dem Speichern lesen (Bug 2.29 Fix)
    let previousKey = null;
    try {
        previousKey = localStorage.getItem('b6_sidebar_open');
        const key = section.dataset.accordion;
        if (key) localStorage.setItem('b6_sidebar_open', key);
    } catch (_) {}

    // B6 Phase 6: Formular-Akkordeon geoeffnet -> showPlaceholderForm() aufrufen
    // Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
    if (section.dataset.accordion === 'form') {
        _refreshPlaceholderForm();
    }

    // Bug 2.29 Fix Build 122: Blauen Rahmen bereinigen wenn das Formular-Akkordeon
    // VERLASSEN wird. previousKey lesen VOR dem localStorage.setItem-Aufruf.
    // Beleg: Bugfix Build 122, Projektgespraech 2026-05-08
    if (previousKey === 'form' && section.dataset.accordion !== 'form') {
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

    // Hilfsfunktion: ein .ce-block wrappen.
    // Build 121: Neue Bloecke ohne blockIndex-Eintrag erhalten Fallback-Metadata
    // (author=username, created_at=jetzt). Sonst blieben vom Nutzer neu angelegte
    // Bloecke ohne Wrapper bis zum naechsten Reload.
    // Beleg: Bugfix Build 121, Projektgespraech 2026-05-08
    function tryWrap(ceBlock) {
        const blockId = ceBlock.dataset?.id;
        if (!blockId) return;
        const meta = blockIndex[blockId] || {
            block_id:   blockId,
            author:     username,
            created_at: Math.floor(Date.now() / 1000),
        };
        _wrapBlock(ceBlock, meta, username);

        // Bug 2.38 Fix Build 129: Block-Klick-Handler ENTFERNT.
        // Der vorherige Handler (Build 125) oeffnete bei jedem Klick in einen
        // Block den Kommentar-Akkordeon und setzte den Fokus ins Textarea —
        // dadurch war kein Bearbeiten des Block-Inhalts mehr moeglich (Prio 50).
        // Der Kommentieren-Button in .block-meta-bar hat seinen eigenen Handler
        // (_openCommentAccordion via btnComment.addEventListener) — das reicht.
        // Kommentare werden durch expliziten Klick auf "💬 Kommentieren" geoeffnet,
        // nicht durch jeden Block-Klick.
        // Beleg: Bugfix Build 129, Projektgespraech 2026-05-09
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
 *
 * Bug 2.50 Fix Build 137: Einfacher Klick auf einen Chip loest Aufleuchten-
 * Animation (.ph-chip--flash) aus als visuelles Feedback "geschuetzt".
 * Beleg: Bugfix Build 137, Projektgespraech 2026-05-09
 */
function _bindChipDoubleClick() {
    const holder = document.getElementById('editorjs-holder');
    if (!holder) return;

    // Einfacher Klick: Flash-Animation als "nicht editierbar"-Feedback
    // (Bug 2.50 Fix Build 137)
    holder.addEventListener('click', (e) => {
        const chip = e.target.closest('.ph-chip');
        if (!chip) return;
        // Nur flashen wenn kein Doppelklick folgt (250ms Toleranz)
        chip._flashTimer && clearTimeout(chip._flashTimer);
        chip._flashTimer = setTimeout(() => {
            chip.classList.remove('ph-chip--flash');
            chip.classList.add('ph-chip--flash');
            // Klasse nach Animation entfernen damit sie wiederholbar ist
            chip.addEventListener('animationend', () => {
                chip.classList.remove('ph-chip--flash');
            }, { once: true });
        }, 180);
    });

    holder.addEventListener('dblclick', (e) => {
        const chip = e.target.closest('.ph-chip');
        if (!chip) return;

        // Flash-Timer aus dem Einfach-Klick-Handler abbrechen
        chip._flashTimer && clearTimeout(chip._flashTimer);
        chip._flashTimer = null;

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

                // Bug 2.42 Fix Build 135: onSave muss auf _onPlaceholderFieldSave
                // zeigen statt auf eine leere Funktion, damit Werte tatsaechlich
                // gespeichert werden. Ausserdem: focusBlock rendert das Formular
                // asynchron — der Input-Fokus wird erst nach 250ms gesetzt
                // (statt 100ms) damit der DOM sicher bereit ist.
                // Beleg: Bugfix Build 135, Projektgespraech 2026-05-09
                window.PlaceholderWizard.openAtField({
                    blockId:     blockId,
                    moduleTitle: chip.dataset.chipDescription || fieldName,
                    bodyText:    rawText,
                    values:      {},
                    onSave:      _onPlaceholderFieldSave,
                    _focusDelay: 250,
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
 * Bug 3.7 Fix Build 136: block_data war ein JSON-String, das Backend erwartet
 * aber ein Objekt (dict). Fix: JSON.parse() vor dem Senden.
 * Aktion auf 'save' vereinfacht (statt 'update_block') — Backend benoetigt
 * dann keine spezielle Alias-Behandlung mehr.
 * Beleg: Bugfix Build 136, Projektgespraech 2026-05-09
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

    // Bug 3.7 Fix Build 136: block_data als Objekt senden, nicht als String.
    // _currentBlocks speichert block_data als JSON-String — JSON.parse() noetig.
    let blockDataObj = {};
    try {
        blockDataObj = JSON.parse(block?.block_data || '{}');
    } catch (_) {}

    const resp = await _fetchWithLock(EDITOR_API.BLOCK, {
        action:                  'save',
        block_id:                blockId,
        block_data:              blockDataObj,
        placeholder_values_json: JSON.stringify(newValues),
    });
    if (resp && !resp.ok) {
        const err = await resp.json().catch(() => ({}));
        console.warn('report_editor.js: Platzhalter-Save fehlgeschlagen:', fieldName, err);
    } else if (resp?.ok) {
        // Lokalen Cache aktualisieren damit nachfolgende Saves korrekte Basis haben
        if (block) {
            block.placeholder_values_json = JSON.stringify(newValues);
        }
        // Bug 2.49 Fix Build 137: Chips im Editor sofort mit neuem Wert rendern.
        // Den Block im Editor-DOM suchen und die Chip-Spans fuer diesen Feldnamen
        // aktualisieren (Klassen + Textinhalt) ohne die gesamte Block-Struktur zu ersetzen.
        // Beleg: Bugfix Build 137, Projektgespraech 2026-05-09
        _refreshChipsInBlock(blockId, newValues);
    }
}

/**
 * Bug 2.49 Fix Build 137: Aktualisiert Chip-Spans im Editor-DOM nach einem
 * Formular-Save. Sucht alle .ph-chip-Spans im betroffenen Block und ersetzt
 * Klassen und Textinhalt anhand der neuen Werte — ohne den Block neu zu laden.
 *
 * @param {string} blockId   Editor.js Block-ID (data-id am .ce-block)
 * @param {Object} values    { fieldName: value } — alle bekannten Feldwerte
 */
function _refreshChipsInBlock(blockId, values) {
    if (!blockId || !values) return;
    const holder = document.getElementById('editorjs-holder');
    if (!holder) return;

    // Block-Element im DOM suchen
    const ceBlock = holder.querySelector(`.ce-block[data-id="${blockId}"]`);
    if (!ceBlock) return;

    // Alle Chips in diesem Block aktualisieren
    ceBlock.querySelectorAll('.ph-chip[data-chip-name]').forEach(chip => {
        const name     = chip.dataset.chipName;
        const chipType = chip.dataset.chipType;

        // Nur m: und o: Chips rendern Formularwerte
        if (chipType !== 'm' && chipType !== 'o') return;

        const val      = values[name];
        const isFilled = val !== undefined && val !== null && String(val).trim() !== '';
        const description = chip.dataset.chipDescription || name;

        if (isFilled) {
            // Chip als ausgefuellt markieren
            chip.classList.remove('ph-chip-empty');
            chip.classList.add('ph-chip-filled');
            chip.textContent = String(val);
        } else {
            // Chip als leer markieren
            chip.classList.remove('ph-chip-filled');
            chip.classList.add('ph-chip-empty');
            chip.textContent = chipType === 'm'
                ? (description + ' *')
                : description;
        }
    });
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
            // Bug 2 Fix Build 127: Kommentar-Badges nach Reload aktualisieren.
            // _wrapBlock() ist idempotent (data-wrapped-Guard) und setzt Badges
            // bei bereits dekorierten Bloecken nicht neu. Expliziter Badge-Update
            // ist noetig damit der Status nach resolve_comment sofort sichtbar wird.
            // Beleg: Bugfix Build 127, Projektgespraech 2026-05-08
            _updateBlockBadges(_currentBlocks);
        }
    } catch (_) {}
}

/**
 * Laedt den Editor komplett neu vom Server (ohne Seiten-Reload).
 * Zerstoert den bestehenden Editor und initialisiert ihn mit den
 * aktuellen Bloecken aus der Datenbank.
 * Wird von der Aktualisieren-Schaltflaeche (Bug 2.7) aufgerufen.
 * Beleg: Bugfix Build 132, Projektgespraech 2026-05-09
 */
async function _reloadEditorContent() {
    if (!_currentReport) return;
    _dbg('_reloadEditorContent(): Starte Neuladen fuer report_id=', _currentReport.id);

    try {
        // Aktuelle Bloecke vom Server laden
        const resp = await fetch(
            `/_forensic/report?format=json&report_id=${_currentReport.id}`,
            { headers: { 'X-Forensic-Request': 'ajax' } }
        );
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        const freshBlocks = data.blocks || [];

        // Bestehenden Editor zerstoeren
        if (_editor) {
            try { await _editor.destroy(); } catch (_) {}
            _editor = null;
        }
        // editorjs-holder neu anlegen (Editor.js entfernt ihn beim destroy())
        const workspace = document.getElementById('report-main-col');
        let holder = document.getElementById('editorjs-holder');
        if (!holder && workspace) {
            holder = document.createElement('div');
            holder.id = 'editorjs-holder';
            holder.className = 'editorjs-holder';
            const frozen = document.getElementById('report-frozen-overlay');
            if (frozen) {
                workspace.insertBefore(holder, frozen);
            } else {
                workspace.appendChild(holder);
            }
        }

        // _currentBlocks aktualisieren und _knownBlockIds neu setzen
        _currentBlocks = freshBlocks;
        _knownBlockIds = new Set(freshBlocks.map(b => b.block_id).filter(Boolean));

        // Editor neu initialisieren
        _initEditorJs(freshBlocks, _currentReport.id);

        // Sidebar-Module aktualisieren
        _refreshModulePanel();
        _updateBlockBadges(freshBlocks);

        _dbg('_reloadEditorContent(): Abgeschlossen.',
             freshBlocks.length, 'Bloecke geladen.');
    } catch (err) {
        console.warn('report_editor.js: _reloadEditorContent fehlgeschlagen:', err);
    }
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

    // Build 122 Fix 1.8: Alle nativen hidden-Attribute durch CSS-Klasse ersetzen,
    // damit CSS-Transitions animieren können.
    sidebar.querySelectorAll('.support-accordion-body[hidden]').forEach(body => {
        body.hidden = false;
        body.classList.add('support-accordion-body--closed');
    });

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
 * Auto-Save: speichert alle geaenderten Bloecke und loescht entfernte Bloecke.
 * Nur wenn Lock gehalten wird.
 *
 * Bug 2.39 Fix Build 130: Erkennt entfernte Bloecke durch Vergleich von
 * editorData.blocks mit _knownBlockIds und sendet delete_block fuer jeden
 * Block, der in _knownBlockIds steht aber nicht mehr im Editor vorhanden ist.
 * Ohne diesen Fix wurden geloeschte Bloecke beim naechsten Reload wieder
 * aus der DB geladen und erschienen erneut im Editor.
 * Beleg: Bugfix Build 130, Projektgespraech 2026-05-09
 *
 * @param {number} reportId
 */
async function _performAutoSave(reportId) {
    if (!window.EditorState?.lockId) return;
    if (!_editor) return;

    // Speicher-Indikator auf "Speichern laeuft..." setzen (pulsierend gruen)
    _showSavingIndicator();
    console.debug('report_editor.js: Auto-Save gestartet, report_id=', reportId,
                  '| bekannte Block-IDs:', _knownBlockIds.size);

    let editorData;
    try {
        editorData = await _editor.save();
    } catch (err) {
        console.warn('report_editor.js: Editor.save() fehlgeschlagen:', err);
        _hideSavingIndicator();
        return;
    }

    const username = document.getElementById('report-editor-body')?.dataset?.username || '';

    // Schnellzugriff: welche Block-IDs gehoeren dem aktuellen Nutzer?
    // Fremde Bloecke werden im Auto-Save uebersprungen (Bug 2.26 Fix Build 133).
    // Beleg: Bugfix Build 133, Projektgespraech 2026-05-09
    const ownBlockIds = new Set(
        _currentBlocks
            .filter(b => !b.author || b.author === username)
            .map(b => b.block_id)
    );

    // Schritt 1: Vorhandene Bloecke speichern — nur eigene Bloecke
    const currentBlockIds = new Set();
    for (const block of editorData.blocks) {
        currentBlockIds.add(block.id);

        // Fremde Bloecke nicht ueberschreiben.
        // _knownBlockIds kennt diese IDs vom Laden — sie kommen in editorData
        // weil Editor.js alle sichtbaren Bloecke zurueckgibt, auch fremde.
        if (!ownBlockIds.has(block.id) && _knownBlockIds.has(block.id)) {
            // Bekannter fremder Block: ueberspringen
            continue;
        }

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

    // Schritt 2: Geloeschte Bloecke erkennen und serverseitig entfernen.
    // Bug 2.39 Fix: _knownBlockIds enthaelt Block-IDs aus dem letzten gespeicherten
    // Zustand. Jede ID, die dort steht aber nicht mehr in currentBlockIds, wurde
    // vom Benutzer geloescht und muss per delete_block aus der DB entfernt werden.
    // Beleg: Bugfix Build 130, Projektgespraech 2026-05-09
    const deletedIds = [];
    for (const knownId of _knownBlockIds) {
        if (!currentBlockIds.has(knownId)) {
            deletedIds.push(knownId);
        }
    }
    if (deletedIds.length > 0) {
        console.debug('report_editor.js: Geloeschte Bloecke erkannt:', deletedIds);
        for (const blockId of deletedIds) {
            const resp = await _fetchWithLock(EDITOR_API.BLOCK, {
                action:   'delete_block',
                block_id: blockId,
            });
            if (resp) {
                if (resp.ok || resp.status === 404) {
                    // 404 = bereits geloescht (OK), 200 = erfolgreich geloescht
                    console.debug('report_editor.js: Block geloescht:', blockId,
                                  '| Status:', resp.status);
                    _knownBlockIds.delete(blockId);
                } else {
                    const errBody = await resp.json().catch(() => ({}));
                    console.warn('report_editor.js: delete_block fehlgeschlagen:',
                                 blockId, resp.status, errBody);
                }
            }
        }
    }

    // Schritt 3: Blockreihenfolge speichern
    // (Fractional Indexing: einfaches '000000', '000001', ... fuer jetzt)
    // AP-E4: vollstaendiges Fractional Indexing in einem Folgebuild
    const orderPayload = editorData.blocks.map((b, i) => ({
        block_id:   b.id,
        sort_index: String(i).padStart(6, '0'),
    }));
    if (orderPayload.length) {
        await _fetchWithLock(EDITOR_API.ORDER, {
            report_id: reportId,
            order:     orderPayload,
        });
    }

    // _knownBlockIds auf aktuellen Stand bringen
    _knownBlockIds = new Set(currentBlockIds);

    // Speicher-Indikator: Erfolg anzeigen
    _showSaveIndicator();
    console.debug('report_editor.js: Auto-Save abgeschlossen.',
                  '| Bloecke gespeichert:', currentBlockIds.size,
                  '| Bloecke geloescht:', deletedIds.length);

    // Bug 2.30 Fix Build 123: _currentBlocks nach jedem Auto-Save aktualisieren.
    // Neue Bloecke erhalten server-seitige Metadaten (author, created_at etc.),
    // Sortierung kann sich durch Drag-Drop geaendert haben.
    // Wenn das Formular-Akkordeon gerade offen ist: gleich neu rendern.
    // Beleg: Bugfix Build 123, Projektgespraech 2026-05-08
    try {
        const resp = await fetch('/_forensic/report?format=json', {
            headers: { 'X-Forensic-Request': 'ajax' },
        });
        if (resp.ok) {
            const data = await resp.json();
            _currentBlocks = data.blocks || [];
            // Formular aktualisieren wenn es gerade offen ist
            const sidebar = document.getElementById('support-sidebar');
            const openAccordion = sidebar?.querySelector('.support-accordion-section--open');
            if (openAccordion?.dataset?.accordion === 'form') {
                _refreshPlaceholderForm();
            }
        }
    } catch (_) {}
}

/**
 * Zeigt den Speicher-Indikator als pulsierend-gruen waehrend des Speichervorgangs.
 * Zustand: --saving (gruener pulsierender Rahmen, Diskette gruen).
 * Beleg: Bugfix Build 132, Projektgespraech 2026-05-09 (Bug 1.22)
 */
function _showSavingIndicator() {
    const el = document.getElementById('editor-save-indicator');
    if (!el) return;
    el.textContent = '🖫';
    el.title = 'Speichern läuft…';
    el.className = 'save-indicator save-indicator--saving';
    // Inline-Style zuruecksetzen damit CSS-Klasse allein steuert
    el.style.opacity = '';
    el.style.color = '';
}

/**
 * Zeigt Fehler-Zustand: Diskette rot, dauerhaft bis Erfolg.
 * Zustand: --failed
 * Beleg: Bugfix Build 132, Projektgespraech 2026-05-09 (Bug 1.22)
 */
function _showSaveFailedIndicator() {
    const el = document.getElementById('editor-save-indicator');
    if (!el) return;
    el.textContent = '🖫';
    el.title = 'Speichern fehlgeschlagen! Bitte Seite neu laden.';
    el.className = 'save-indicator save-indicator--failed';
    el.style.opacity = '';
    el.style.color = '';
}

/**
 * Blendet den pulsierenden Indikator aus (bei Fehler -> --failed).
 * Beleg: Bugfix Build 132, Projektgespraech 2026-05-09 (Bug 1.22)
 */
function _hideSavingIndicator() {
    _showSaveFailedIndicator();
}

/**
 * Zeigt kurz "Gespeichert" (gruen), nach 5s Rueckkehr zum Ruhezustand.
 * Zustand: --saved -> --idle
 * Beleg: Bugfix Build 132, Projektgespraech 2026-05-09 (Bug 1.22)
 */
function _showSaveIndicator() {
    const el = document.getElementById('editor-save-indicator');
    if (!el) return;
    el.textContent = '🖫';
    el.title = 'Gespeichert';
    el.className = 'save-indicator save-indicator--saved';
    el.style.opacity = '';
    el.style.color = '';
    // Nach 5 Sekunden in den grauen Ruhezustand zurueckfallen
    setTimeout(() => {
        // Nur zuruecksetzen wenn kein Fehler- oder Speicher-Zustand eingetreten
        if (el.classList.contains('save-indicator--saved')) {
            el.textContent = '🖫';
            el.title = 'Kein Speichern ausstehend';
            el.className = 'save-indicator save-indicator--idle';
        }
    }, 5000);
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
    // Bug 1.22 Fix Build 132: Speicher-Indikator mit Disketten-Symbol initialisieren.
    // Grau und leicht gebluert im Ruhezustand (--idle).
    // Beleg: Bugfix Build 132, Projektgespraech 2026-05-09
    const saveEl = document.getElementById('editor-save-indicator');
    if (saveEl) {
        saveEl.textContent = '🖫';
        saveEl.title = 'Kein Speichern ausstehend';
        saveEl.className = 'save-indicator save-indicator--idle';
        saveEl.style.opacity = '';
        saveEl.style.color = '';
    }
    await initReportSelector();
    initBlockUpdatedListener();

    // Bug 2.7 Fix Build 132: Aktualisieren-Schaltflaeche laedt Editor-Inhalte
    // neu ohne Seiten-Reload. Zerstoert den alten Editor und initialisiert ihn
    // mit den neu vom Server geladenen Bloecken.
    // Beleg: Bugfix Build 132, Projektgespraech 2026-05-09
    const btnRefresh = document.getElementById('btn-refresh-placeholders');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', async () => {
            if (!_currentReport) return;
            btnRefresh.disabled = true;
            btnRefresh.textContent = '⏳ Lädt…';
            try {
                await _reloadEditorContent();
            } finally {
                btnRefresh.disabled = false;
                btnRefresh.textContent = '🔄 Aktualisieren';
            }
        });
    }

    // Bug 2.5 Fix Build 134: Drucken-Schaltflaeche oeffnet Browser-Druckdialog.
    // Vor dem Drucken wird ein letzter Auto-Save ausgeloest wenn ein Lock besteht,
    // damit der gedruckte Stand mit der Datenbank synchron ist.
    // Beleg: Bugfix Build 134, Projektgespraech 2026-05-09
    const btnPrint = document.getElementById('btn-print');
    if (btnPrint) {
        btnPrint.addEventListener('click', async () => {
            // Letzten Stand speichern bevor gedruckt wird
            if (window.EditorState?.lockId && _currentReport?.id) {
                btnPrint.disabled = true;
                btnPrint.textContent = '🖶 …';
                try {
                    await _performAutoSave(_currentReport.id);
                } catch (_) { /* Drucken trotzdem fortsetzen */ }
                finally {
                    btnPrint.disabled = false;
                    btnPrint.textContent = '🖶 Drucken';
                }
            }
            window.print();
        });
    }

    // Bug 2.40/2.43 Absicherung Build 136: Ctrl+S / Cmd+S als globaler
    // Tastatur-Shortcut fuer manuelles Speichern.
    // Beleg: Bugfix Build 136, Projektgespraech 2026-05-09
    if (!window._saveShortcutBound) {
        window._saveShortcutBound = true;
        document.addEventListener('keydown', async (e) => {
            const isSave = (e.ctrlKey || e.metaKey) && e.key === 's';
            if (!isSave) return;
            e.preventDefault();
            if (!_currentReport?.id || !window.EditorState?.lockId) return;
            await _performAutoSave(_currentReport.id);
        });
    }
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
