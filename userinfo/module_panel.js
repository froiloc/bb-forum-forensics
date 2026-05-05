/**
 * userinfo/module_panel.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Modul-Auswahl-Panel fuer Fenster 3 (Phase 6, Bauplan B6 v0.3 §4.4).
 *
 *   Oeffnet als Modal bei Klick auf "Modul einfuegen". Zeigt gefilterte
 *   Liste der Berichtsmodule aus templates.db. Nach Auswahl und "Einfuegen"
 *   wird direkt der Platzhalter-Wizard (§4.5) geoeffnet.
 *
 *   Funktionen:
 *     - Modulliste laden via GET /_forensic/templates
 *     - Filter: role, topic, Freitextsuche (title + description)
 *     - Vorschau: Body-Text mit Platzhalter-Chips gerendert
 *     - Einfuegen: Paragraph anlegen + Wizard starten
 *
 *   Abhaengigkeiten:
 *     placeholder_chips.js   (window.PlaceholderChips)
 *     placeholder_wizard.js  (window.PlaceholderWizard)
 *     report.js              (_postWithLock, loadReport, showStatus —
 *                             werden als window.*-Callbacks uebergeben)
 *
 * Exports:
 *   window.ModulePanel.open(options)
 *     Oeffnet das Panel.
 *     options: {
 *       reportId:   number,
 *       onInserted: async function(blockId) -- nach erfolgreichem Einfuegen
 *     }
 *   window.ModulePanel.close()
 *
 * API-Endpunkte (lesend, aus Build 089):
 *   GET /_forensic/templates              -- Modulliste (gefiltert)
 *   GET /_forensic/templates?topics=1     -- Themen-Liste fuer Filter
 *   GET /_forensic/templates/<id>         -- Einzelmodul mit Body (Vorschau)
 *
 * Version: v0.1.0 · Build: 093 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §4.4, Ausdefinitionsgespraech 2026-05-05
 */

'use strict';

// ---------------------------------------------------------------------------
// Konstanten
// ---------------------------------------------------------------------------

const TEMPLATES_API = '/_forensic/templates';

const ROLE_LABELS = {
    intro:      'Einleitung',
    conclusion: 'Fazit',
    body:       'Hauptteil',
    legal:      'Rechtsgrundlagen',
    appendix:   'Anhang',
    closing:    'Abschluss',
};

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

function _esc(s) {
    return String(s !== undefined && s !== null ? s : '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Panel-Zustand (Modul-intern)
// ---------------------------------------------------------------------------

let _overlay      = null;
let _opts         = null;
let _modules      = [];    // geladene Modulliste
let _selectedId   = null;  // aktuell ausgewaehltes Modul
let _filterRole   = '';
let _filterTopic  = '';
let _filterSearch = '';

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

/**
 * Laedt die Modulliste vom Server.
 * @returns {Promise<Array>}
 */
async function _fetchModules(role, topic, search) {
    const params = new URLSearchParams();
    if (role)   params.set('role',   role);
    if (topic)  params.set('topic',  topic);
    if (search) params.set('search', search);
    const url = TEMPLATES_API + (params.toString() ? '?' + params.toString() : '');
    const resp = await fetch(url, { headers: { 'X-Forensic-Request': 'ajax' } });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.json();
}

/**
 * Laedt alle vorhandenen Themen fuer den Topic-Filter.
 * @returns {Promise<Array<string>>}
 */
async function _fetchTopics() {
    const resp = await fetch(TEMPLATES_API + '?topics=1', {
        headers: { 'X-Forensic-Request': 'ajax' },
    });
    if (!resp.ok) return [];
    const data = await resp.json();
    return data.topics || [];
}

/**
 * Laedt ein einzelnes Modul mit Body fuer die Vorschau.
 * @param {number} id
 * @returns {Promise<Object|null>}
 */
async function _fetchModuleBody(id) {
    const resp = await fetch(TEMPLATES_API + '/' + id, {
        headers: { 'X-Forensic-Request': 'ajax' },
    });
    if (!resp.ok) return null;
    return resp.json();
}

// ---------------------------------------------------------------------------
// DOM-Aufbau
// ---------------------------------------------------------------------------

function _createOverlay() {
    const overlay = document.createElement('div');
    overlay.id = 'mp-overlay';
    overlay.className = 'mp-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'mp-title');
    overlay.innerHTML = `
        <div class="mp-dialog" id="mp-dialog">
            <div class="mp-header">
                <span class="mp-title" id="mp-title">Modul ausw\u00e4hlen</span>
                <button class="mp-close-btn" id="mp-btn-close"
                    title="Schliessen" aria-label="Panel schliessen">\u2715</button>
            </div>

            <div class="mp-filters">
                <div class="mp-search-wrap">
                    <span class="mp-search-icon" aria-hidden="true">\ud83d\udd0d</span>
                    <input class="mp-search-input" id="mp-search"
                           type="search" placeholder="Suche in Titel und Beschreibung\u2026"
                           autocomplete="off">
                </div>
                <div class="mp-filter-row">
                    <label class="mp-filter-label" for="mp-filter-role">Rolle:</label>
                    <select class="mp-filter-select" id="mp-filter-role">
                        <option value="">Alle</option>
                    </select>
                    <label class="mp-filter-label" for="mp-filter-topic">Thema:</label>
                    <select class="mp-filter-select" id="mp-filter-topic">
                        <option value="">Alle</option>
                    </select>
                </div>
            </div>

            <div class="mp-divider"></div>

            <div class="mp-list-wrap">
                <div class="mp-list" id="mp-list" role="listbox"
                     aria-label="Verf\u00fcgbare Berichtsmodule"></div>
                <div class="mp-empty" id="mp-empty" style="display:none">
                    Keine Module gefunden.
                </div>
                <div class="mp-loading" id="mp-loading">Wird geladen\u2026</div>
            </div>

            <div class="mp-preview-wrap" id="mp-preview-wrap" style="display:none">
                <div class="mp-divider"></div>
                <div class="mp-preview-header">Vorschau</div>
                <div class="mp-preview-body" id="mp-preview-body"></div>
            </div>

            <div class="mp-divider"></div>
            <div class="mp-footer">
                <button class="mp-btn" id="mp-btn-preview" disabled>Vorschau</button>
                <span class="mp-footer-spacer"></span>
                <button class="mp-btn" id="mp-btn-cancel">\u2715 Abbrechen</button>
                <button class="mp-btn mp-btn-primary" id="mp-btn-insert" disabled>
                    Einf\u00fcgen \u25ba
                </button>
            </div>
        </div>`;
    document.body.appendChild(overlay);
    return overlay;
}

// ---------------------------------------------------------------------------
// Filter-Dropdowns befuellen
// ---------------------------------------------------------------------------

function _populateRoleFilter() {
    const sel = document.getElementById('mp-filter-role');
    if (!sel) return;
    Object.entries(ROLE_LABELS).forEach(([val, label]) => {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = label;
        sel.appendChild(opt);
    });
}

async function _populateTopicFilter() {
    const sel = document.getElementById('mp-filter-topic');
    if (!sel) return;
    try {
        const topics = await _fetchTopics();
        topics.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t;
            opt.textContent = t;
            sel.appendChild(opt);
        });
    } catch (_) { /* Topics sind optional */ }
}

// ---------------------------------------------------------------------------
// Liste rendern
// ---------------------------------------------------------------------------

function _renderList(modules) {
    const list    = document.getElementById('mp-list');
    const empty   = document.getElementById('mp-empty');
    const loading = document.getElementById('mp-loading');
    if (!list) return;

    if (loading) loading.style.display = 'none';

    if (!modules.length) {
        list.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
    }
    if (empty) empty.style.display = 'none';

    list.innerHTML = modules.map(m => {
        const roleLabel = ROLE_LABELS[m.role] || _esc(m.role);
        const sel = m.id === _selectedId ? ' mp-item-selected' : '';
        return `
            <div class="mp-item${sel}" role="option"
                 aria-selected="${m.id === _selectedId ? 'true' : 'false'}"
                 data-module-id="${m.id}"
                 tabindex="0">
                <div class="mp-item-main">
                    <span class="mp-item-icon" aria-hidden="true">\ud83d\udccb</span>
                    <div class="mp-item-text">
                        <span class="mp-item-title">${_esc(m.title)}</span>
                        ${m.description
                            ? `<span class="mp-item-desc">${_esc(m.description)}</span>`
                            : ''}
                    </div>
                </div>
                <span class="mp-item-role-badge">${_esc(roleLabel)}</span>
            </div>`;
    }).join('');

    // Klick-Events
    list.querySelectorAll('.mp-item').forEach(item => {
        item.addEventListener('click', () => _selectModule(parseInt(item.dataset.moduleId, 10)));
        item.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                _selectModule(parseInt(item.dataset.moduleId, 10));
            }
        });
        // Doppelklick: direkt einfuegen
        item.addEventListener('dblclick', () => {
            _selectModule(parseInt(item.dataset.moduleId, 10));
            _onInsert();
        });
    });
}

function _selectModule(id) {
    _selectedId = id;

    // Selektion visuell aktualisieren
    document.querySelectorAll('.mp-item').forEach(el => {
        const selected = parseInt(el.dataset.moduleId, 10) === id;
        el.classList.toggle('mp-item-selected', selected);
        el.setAttribute('aria-selected', selected ? 'true' : 'false');
    });

    const btnPreview = document.getElementById('mp-btn-preview');
    const btnInsert  = document.getElementById('mp-btn-insert');
    if (btnPreview) btnPreview.disabled = false;
    if (btnInsert)  btnInsert.disabled  = false;
}

// ---------------------------------------------------------------------------
// Vorschau
// ---------------------------------------------------------------------------

async function _showPreview(id) {
    const wrap = document.getElementById('mp-preview-wrap');
    const body = document.getElementById('mp-preview-body');
    if (!wrap || !body) return;

    body.textContent = 'Wird geladen\u2026';
    wrap.style.display = '';

    try {
        const m = await _fetchModuleBody(id);
        if (!m) { body.textContent = 'Vorschau nicht verfuegbar.'; return; }

        if (window.PlaceholderChips) {
            body.innerHTML = window.PlaceholderChips.render(m.body || '', {}, {});
        } else {
            body.textContent = m.body || '';
        }
    } catch (_) {
        body.textContent = 'Vorschau konnte nicht geladen werden.';
    }
}

// ---------------------------------------------------------------------------
// Filter-Logik
// ---------------------------------------------------------------------------

async function _applyFilters() {
    const loading = document.getElementById('mp-loading');
    if (loading) loading.style.display = '';

    try {
        _modules = await _fetchModules(_filterRole, _filterTopic, _filterSearch);
    } catch (_) {
        _modules = [];
    }

    // Selektion zuruecksetzen wenn gefiltertes Modul nicht mehr in der Liste
    if (_selectedId !== null && !_modules.find(m => m.id === _selectedId)) {
        _selectedId = null;
        const btnPreview = document.getElementById('mp-btn-preview');
        const btnInsert  = document.getElementById('mp-btn-insert');
        if (btnPreview) btnPreview.disabled = true;
        if (btnInsert)  btnInsert.disabled  = true;
        const wrap = document.getElementById('mp-preview-wrap');
        if (wrap) wrap.style.display = 'none';
    }

    _renderList(_modules);
}

// ---------------------------------------------------------------------------
// Einfuegen
// ---------------------------------------------------------------------------

async function _onInsert() {
    if (_selectedId === null) return;

    const btnInsert = document.getElementById('mp-btn-insert');
    if (btnInsert) { btnInsert.disabled = true; btnInsert.textContent = 'Wird eingef\u00fcgt\u2026'; }

    try {
        // 1. Modul-Body holen (fuer Wizard)
        const m = await _fetchModuleBody(_selectedId);
        if (!m) throw new Error('Modul nicht geladen.');

        // 2. Paragraph anlegen via _opts.postFn
        const sortIndex = (_opts.currentParagraphCount || 0) * 10;
        const result    = await _opts.postFn({
            action:    'add_paragraph',
            report_id: _opts.reportId,
            content:   m.body || '',
            sort_index: sortIndex,
        });
        if (!result || !result.block_id) throw new Error('Paragraph-Anlage fehlgeschlagen.');

        const blockId = result.block_id;
        close();

        // 3. Wizard oeffnen (falls m: oder o:-Felder vorhanden)
        const chips = window.PlaceholderChips;
        const hasMO = chips && (
            chips.extractFields(m.body || '', 'm').length > 0 ||
            chips.extractFields(m.body || '', 'o').length > 0
        );

        if (hasMO && window.PlaceholderWizard) {
            window.PlaceholderWizard.open({
                blockId,
                moduleTitle: m.title,
                bodyText:    m.body || '',
                values:      {},
                onSave:      (bid, newValues) => _opts.saveFn(bid, m.body || '', newValues),
            });
        } else {
            // Kein Wizard noetig (nur a:-Platzhalter oder kein Platzhalter)
            await _opts.onInserted(blockId);
        }

    } catch (err) {
        if (btnInsert) {
            btnInsert.disabled  = false;
            btnInsert.textContent = 'Einf\u00fcgen \u25ba';
        }
        if (_opts && _opts.showStatus) {
            _opts.showStatus('Fehler beim Einf\u00fcgen: ' + String(err), 'error');
        }
    }
}

// ---------------------------------------------------------------------------
// Event-Verdrahtung
// ---------------------------------------------------------------------------

function _bindEvents() {
    document.getElementById('mp-btn-close')?.addEventListener('click',   close);
    document.getElementById('mp-btn-cancel')?.addEventListener('click',  close);
    document.getElementById('mp-btn-insert')?.addEventListener('click',  _onInsert);
    document.getElementById('mp-btn-preview')?.addEventListener('click', () => {
        if (_selectedId !== null) _showPreview(_selectedId);
    });

    // Escape schliesst
    _overlay._escHandler = e => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', _overlay._escHandler);

    // Suche mit Debounce
    let _searchTimer = null;
    document.getElementById('mp-search')?.addEventListener('input', e => {
        clearTimeout(_searchTimer);
        _filterSearch = e.target.value.trim();
        _searchTimer  = setTimeout(_applyFilters, 280);
    });

    // Rolle-Filter
    document.getElementById('mp-filter-role')?.addEventListener('change', e => {
        _filterRole = e.target.value;
        _applyFilters();
    });

    // Thema-Filter
    document.getElementById('mp-filter-topic')?.addEventListener('change', e => {
        _filterTopic = e.target.value;
        _applyFilters();
    });
}

// ---------------------------------------------------------------------------
// Oeffentliche API
// ---------------------------------------------------------------------------

/**
 * Oeffnet das Modul-Auswahl-Panel.
 *
 * @param {Object} options
 *   reportId:              number   -- ID des aktiven Berichts
 *   currentParagraphCount: number   -- fuer sort_index-Berechnung
 *   postFn:                function -- _postWithLock aus report.js
 *   saveFn:                async function(blockId, bodyText, values)
 *   onInserted:            async function(blockId)
 *   showStatus:            function(text, level)
 */
function open(options) {
    close();

    _opts         = options;
    _selectedId   = null;
    _filterRole   = '';
    _filterTopic  = '';
    _filterSearch = '';
    _modules      = [];

    _overlay = _createOverlay();

    _populateRoleFilter();
    _populateTopicFilter();  // async, Fehler werden ignoriert
    _bindEvents();
    _applyFilters();         // Initialliste laden
}

/**
 * Schliesst das Panel.
 */
function close() {
    if (_overlay) {
        if (_overlay._escHandler) {
            document.removeEventListener('keydown', _overlay._escHandler);
        }
        _overlay.remove();
        _overlay = null;
    }
    _opts       = null;
    _selectedId = null;
    _modules    = [];
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

window.ModulePanel = {
    open,
    close,
    // Interna fuer Tests
    _fetchModules,
    _renderList,
    _selectModule,
};
