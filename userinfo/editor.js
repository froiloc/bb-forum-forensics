/**
 * userinfo/editor.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Editor.js-Integration
 *
 * Zweck:
 *   Editor.js-Modul fuer Fenster 3 (Bericht-Editor).
 *   Wird von userinfo.js geladen wenn #report-editor-body vorhanden ist.
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
 * Version: v0.6.045 · Build: 045 · 2026-04-19
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 */

'use strict';

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

/** Editor.js-Instanz */
let _editor = null;

/** Auto-Save-Debounce-Timer */
let _saveTimer = null;

/** Sidebar-Zustand */
let _sidebarVisible = false;

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
        console.warn('editor.js: Kein Lock — POST abgebrochen:', url);
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
async function loadReport(report) {
    _currentReport = report;

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
    // editorjs-holder neu anlegen falls destroy() ihn entfernt hat
    const editorContainer = document.getElementById('report-editor-container');
    if (editorContainer && !document.getElementById('editorjs-holder')) {
        // Toolbar, Status-Msg und Frozen-Overlay bleiben erhalten —
        // nur den Holder neu einfuegen
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
        const found = (data.reports || []).find(r => r.id === report.id);
        if (found) existingBlocks = found.blocks || [];
    }

    // Auf Bundle warten
    if (!window.EditorJS) {
        document.getElementById('report-editor-container').innerHTML = `
            <div class="status-msg status-msg-warn" style="margin:20px">
                Editor.js-Bundle nicht geladen.<br>
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

    // Editor.js-Datenformat aus gespeicherten block_data aufbauen
    const editorData = {
        time:   Date.now(),
        blocks: blocks.map(b => ({
            id:   b.block_id,
            type: b.block_type,
            data: typeof b.block_data === 'string' ? JSON.parse(b.block_data) : b.block_data,
        })),
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
        },

        onChange: () => _scheduleAutoSave(reportId),

        onReady: () => {
            // Undo-Plugin initialisieren (muss nach onReady geschehen)
            if (window.EditorTools?.Undo) {
                new window.EditorTools.Undo({ editor: _editor });
            }
            _applyOwnershipStyles(blocks, username);
            // Global bereitstellen fuer Debugging und Reinit
            window._editor = _editor;
            console.debug('editor.js: Editor bereit, report_id=', reportId,
                          '| readOnly=', !hasLock);
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
    // Nach kurzer Verzoegerung — Editor.js braucht Zeit zum Rendern
    setTimeout(() => {
        blocks.forEach(b => {
            if (b.owner === username) return;
            const el = document.querySelector(`[data-id="${b.block_id}"] .ce-block__content`);
            if (el) {
                el.querySelectorAll('[contenteditable]').forEach(c => {
                    c.contentEditable = 'false';
                });
                el.classList.add('block-foreign');
                el.title = `Erstellt von: ${b.owner}`;
            }
        });
    }, 300);
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
        console.warn('editor.js: Editor.save() fehlgeschlagen:', err);
        return;
    }

    const username = document.getElementById('report-editor-body')?.dataset?.username || '';

    for (const block of editorData.blocks) {
        const resp = await _fetchWithLock(EDITOR_API.BLOCK, {
            action:     'save',
            block_id:   block.id,
            report_id:  reportId,
            block_type: block.type,
            block_data: block.data,
            owner:      username,
        });
        if (resp && !resp.ok) {
            const err = await resp.json().catch(() => ({}));
            console.warn('editor.js: Block-Save fehlgeschlagen:', block.id, err);
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
                console.warn('editor.js: Evidence-Add fehlgeschlagen:', annotationId);
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
                console.warn('editor.js: Evidence-Remove fehlgeschlagen:', annotationId);
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
async function toggleAnnotationSidebar(targetBlock = null) {
    _sidebarVisible = !_sidebarVisible;
    let sidebar = document.getElementById('annotation-sidebar');

    if (!_sidebarVisible) {
        sidebar?.remove();
        return;
    }

    if (!sidebar) {
        sidebar = document.createElement('div');
        sidebar.id = 'annotation-sidebar';
        sidebar.className = 'annotation-sidebar';
        document.getElementById('report-editor-body')?.appendChild(sidebar);
    }

    sidebar.innerHTML = '<div class="sidebar-header">Annotationen<button id="btn-close-sidebar" class="sidebar-close">×</button></div>'
        + '<div class="sidebar-content"><span class="loading-spinner"></span> Lade…</div>';

    document.getElementById('btn-close-sidebar')?.addEventListener('click', () => {
        _sidebarVisible = false;
        sidebar.remove();
    });

    try {
        const resp = await fetch('/_forensic/annotations', {
            headers: { 'X-Forensic-Request': 'ajax' }
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const annotations = (data.annotations || []).slice(0, SIDEBAR_MAX_ANNOTATIONS);

        if (!annotations.length) {
            sidebar.querySelector('.sidebar-content').innerHTML =
                '<p style="font-size:12px;color:#666;padding:8px">Keine Annotationen vorhanden.</p>';
            return;
        }

        const escFn = window.esc || (s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'));
        const catColors = {
            CAT_PERSON:   '#e3f2fd',
            CAT_LOCATION: '#e8f5e9',
            CAT_176:      '#ffebee',
            CAT_184:      '#ffebee',
            CAT_VICTIM:   '#fff3e0',
            CAT_OTHER:    '#f5f5f5',
        };

        sidebar.querySelector('.sidebar-content').innerHTML = annotations.map(a => `
            <div class="sidebar-annotation" draggable="true"
                data-id="${a.id}" style="background:${catColors[a.category] || '#f9f9f9'}">
                <div class="sidebar-ann-meta">#${a.id} · ${escFn(a.category)}</div>
                <div class="sidebar-ann-text">${escFn((a.text || '').slice(0, 100))}</div>
                ${targetBlock ? `<button class="editor-btn sidebar-add-btn" data-id="${a.id}"
                    style="margin-top:4px;font-size:10px;padding:2px 6px">+ Einfügen</button>` : ''}
            </div>`).join('');

        // Drag-Events
        sidebar.querySelectorAll('.sidebar-annotation').forEach(el => {
            el.addEventListener('dragstart', e => {
                e.dataTransfer.setData('text/x-annotation-id', el.dataset.id);
                e.dataTransfer.effectAllowed = 'copy';
            });
        });

        // Direkt-Einfuegen-Buttons
        if (targetBlock) {
            sidebar.querySelectorAll('.sidebar-add-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    await targetBlock._addEvidence(parseInt(btn.dataset.id, 10));
                    _sidebarVisible = false;
                    sidebar.remove();
                });
            });
        }

    } catch (err) {
        sidebar.querySelector('.sidebar-content').innerHTML =
            `<p style="font-size:12px;color:#c00;padding:8px">Fehler: ${String(err)}</p>`;
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
        console.warn('editor.js: insert_evidence: Kein Lock — Einfuegen abgebrochen');
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
async function initEditorModule() {
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
    // Bestehenden Editor zerstoeren
    if (_editor) {
        try { await _editor.destroy(); } catch (_) {}
        _editor = null;
        window._editor = null;
    }
    // Neu laden — jetzt mit gesetztem lockId
    await loadReport(_currentReport);
}

// Im globalen Scope bereitstellen
window.initEditorModule            = initEditorModule;
window.injectInsertInReportButtons = injectInsertInReportButtons;
window.toggleAnnotationSidebar     = toggleAnnotationSidebar;
window.EvidenceBlock               = EvidenceBlock;
// Konstante exportieren fuer Tests und externe Konfigurationspruefung
// Beleg: AP-E4, Projektgespraech 2026-04-19
window.AUTOSAVE_DEBOUNCE_MS        = AUTOSAVE_DEBOUNCE_MS;
window._reinitWithLock             = _reinitWithLock;
