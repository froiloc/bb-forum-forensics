/**
 * userinfo/module_panel.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Bausteine-Abschnitt der Support-Sidebar (B6 Phase 7, §4.4.1).
 *   Rendert direkt in #accordion-body-blocks.
 *
 *   Zwei Kategorien (Umschalter):
 *     [Module]      -- Textbausteine mit Platzhaltern aus report_modules
 *     [Einzeldaten] -- Einzelne {{a:...}}-Platzhalter aus placeholder_queries
 *
 *   Module-Ansicht:
 *     - Rollenfilter-Chips: [Alle] [Einleitung] [Hauptteil] [Rechtl.] [Fazit] [Anhang] [Abschluss]
 *     - Freitextsuche ueber Titel, Beschreibung
 *     - Ergebnis: Titel, Rollen-Badge, 80-Zeichen-Vorschau
 *     - [+ Einfuegen]-Schaltflaeche: fuegt Block ein + oeffnet Formular-Akkordeon
 *     - Doppelklick auf Eintrag: sofort einfuegen
 *     - Bereits verwendete Module werden hervorgehoben (client-seitig)
 *
 *   Einzeldaten-Ansicht:
 *     - Filtert auf a:-Queries aus placeholder_queries
 *     - Freitextsuche ueber title + description
 *     - [+ Einfuegen] fuegt {{a:query_id}}-Platzhalter als neuen Block ein
 *
 *   Einfuegen:
 *     1. POST /_forensic/report { action: 'save_block', block_type, block_data }
 *     2. Formular-Akkordeon automatisch oeffnen (Phase 6)
 *
 * Exports:
 *   window.ModulePanel.showPanel(blocks, opts)
 *     Rendert das Panel in #accordion-body-blocks.
 *   window.ModulePanel.open(options)      [Rueckwaerts-Kompatibilitaet]
 *   window.ModulePanel.close()            [Rueckwaerts-Kompatibilitaet]
 *   window.ModulePanel._renderList(modules)    [Tests]
 *   window.ModulePanel._selectModule(id)       [Tests]
 *
 * API-Endpunkte (lesend):
 *   GET /_forensic/templates              -- Modulliste (gefiltert)
 *   GET /_forensic/templates?topics=1     -- Themen
 *   GET /_forensic/templates/<id>         -- Einzelmodul mit Body
 *   GET /_forensic/placeholders/library   -- a:-Queries fuer Einzeldaten
 *
 * Changelog:
 *   Build 093: Erstimplementierung als Modal-Panel.
 *   Build 105 (B6 Phase 7): Modal durch Sidebar-Integration ersetzt.
 *     showPanel() rendert in #accordion-body-blocks.
 *     [Module]/[Einzeldaten]-Umschalter.
 *     Rollenfilter-Chips gemaess §4.4.1.
 *     Einfuegen via save_block (Phase 4 Block-API).
 *     Automatisches Oeffnen des Formular-Akkordeons nach Einfuegen.
 *     Rueckwaerts-Kompatibilitaet open()/close() erhalten.
 *     Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06.
 *
 * Version: v0.6.122 · Build: 122 · 2026-05-08
 * Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
 */

(function() {
'use strict';

// ---------------------------------------------------------------------------
// DEV-Logging (Build 110: systematisches Debug-Logging eingefuehrt)
// Ueber window.FORENSIC_DEBUG = false in der Browser-Console abschaltbar.
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

const TEMPLATES_API    = '/_forensic/templates';
const LIBRARY_API      = '/_forensic/placeholders/library';
const REPORT_API       = '/_forensic/report';

/** Rollenbezeichnungen fuer Filter-Chips und Badges. */
const ROLE_LABELS = {
    intro:      'Einleitung',
    conclusion: 'Fazit',
    body:       'Hauptteil',
    legal:      'Rechtsgrundlagen',
    appendix:   'Anhang',
    closing:    'Abschluss',
};

/**
 * Standard-Bloecke: clientseitig fest verdrahtete Editor.js-Systemkategorie.
 * Kein API-Aufruf — direkte Eintraege als Pseudo-Module-Objekte.
 * Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-07 (Build 112)
 */
const STANDARD_BLOCKS = [
    { id: '__std_paragraph', title: '\u00b6 Textabsatz',      description: 'Freier Texteintrag (Paragraph)',    block_type: 'paragraph',  icon: '\u270f\ufe0f' },
    { id: '__std_header',    title: '\ud83c\udd97 \u00dcberschrift', description: 'Abschnitts\u00fcberschrift (H2)', block_type: 'header',     icon: '\ud83c\udd97' },
    { id: '__std_list',      title: '\ud83d\udcdd Liste',         description: 'Aufz\u00e4hlungsliste oder nummerierte Liste',  block_type: 'list',       icon: '\ud83d\udcdd' },
    { id: '__std_table',     title: '\ud83d\udcca Tabelle',        description: 'Strukturierte Tabelle',            block_type: 'table',      icon: '\ud83d\udcca' },
    { id: '__std_quote',     title: '\u201eZitat\u201c',           description: 'Hervorgehobenes Zitat',            block_type: 'quote',      icon: '\u201e' },
    { id: '__std_delimiter', title: '\u2014 Trennlinie',        description: 'Horizontale Trennlinie',           block_type: 'delimiter',  icon: '\u2014' },
];

/** Vorschau-Laenge (Zeichen). */
const PREVIEW_CHARS = 80;

/** Debounce fuer Suche (ms). */
const SEARCH_DEBOUNCE_MS = 260;

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

function _stripTags(html) {
    const tmp = document.createElement('div');
    tmp.innerHTML = html;
    return tmp.textContent || '';
}

// ---------------------------------------------------------------------------
// Panel-Zustand
// ---------------------------------------------------------------------------

let _currentOpts     = {};     // { reportId, onInserted, lockId }
let _currentBlocks   = [];     // geladene Bloecke des Berichts (fuer "bereits verwendet")
let _modules         = [];     // geladene Modulliste (Module-Ansicht)
let _queries         = [];     // geladene Queries (Einzeldaten-Ansicht)
let _selectedId      = null;   // aktuell ausgewaehltes Element (id/string)
let _filterRole      = '';
let _filterSearch    = '';
let _activeCategory  = 'modules';  // 'modules' | 'queries'
let _searchTimer     = null;

// ---------------------------------------------------------------------------
// API-Abfragen
// ---------------------------------------------------------------------------

async function _fetchModules(role, search) {
    const params = new URLSearchParams();
    if (role)   params.set('role',   role);
    if (search) params.set('search', search);
    const url = TEMPLATES_API + (params.toString() ? '?' + params.toString() : '');
    const resp = await fetch(url, { headers: { 'X-Forensic-Request': 'ajax' } });
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    return resp.json();
}

async function _fetchModuleBody(id) {
    const resp = await fetch(TEMPLATES_API + '/' + id, {
        headers: { 'X-Forensic-Request': 'ajax' },
    });
    if (!resp.ok) return null;
    return resp.json();
}

async function _fetchQueries(search) {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    const url = LIBRARY_API + (params.toString() ? '?' + params.toString() : '');
    const resp = await fetch(url, { headers: { 'X-Forensic-Request': 'ajax' } });
    if (!resp.ok) return [];
    const data = await resp.json();
    return Array.isArray(data) ? data : [];
}

// ---------------------------------------------------------------------------
// Haupt-Render
// ---------------------------------------------------------------------------

/**
 * Rendert das Bausteine-Panel in #accordion-body-blocks.
 * Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
 *
 * @param {Array}  blocks  -- Bloecke des aktiven Berichts (fuer "bereits verwendet")
 * @param {Object} opts    -- { reportId, lockId, onInserted }
 */
async function showPanel(blocks, opts) {
    const body = document.getElementById('accordion-body-blocks');
    if (!body) return;

    _currentBlocks  = blocks || [];
    _currentOpts    = opts || {};
    _filterRole     = '';
    _filterSearch   = '';
    _selectedId     = null;
    // Bug 2.13 Fix Build 122: _activeCategory zurücksetzen wenn showPanel neu
    // aufgerufen wird. Ohne Reset blieb die letzte Kategorie ('queries') aktiv,
    // während die Tab-UI 'Module' als aktiv anzeigte — inkonsistenter Zustand.
    // Beleg: Bugfix Build 122, Projektgespraech 2026-05-08
    _activeCategory = 'modules';

    // Skeleton rendern (sofort sichtbar)
    body.innerHTML = _renderSkeleton();

    // Filter-Chips und Suche verdrahten
    _bindPanelEvents(body);

    // Initiale Liste laden
    await _loadAndRender();
}

/**
 * Skeleton-HTML des Panels (Umschalter + Filter + Liste-Container).
 */
function _renderSkeleton() {
    // 'standard' am Ende als spezielle Systemkategorie
    const roleChips = ['', ...Object.keys(ROLE_LABELS), 'standard'].map(role => {
        const label = role === 'standard' ? 'Standard' : (role ? ROLE_LABELS[role] : 'Alle');
        const active = role === '' ? ' mp-chip-active' : '';
        return `<button class="mp-chip${active}" type="button"
                    data-role="${_esc(role)}"
                    aria-pressed="${role === '' ? 'true' : 'false'}">${_esc(label)}</button>`;
    }).join('');

    return `
    <div class="mp-panel">
        <!-- Kategorie-Umschalter -->
        <div class="mp-cat-tabs" role="tablist" aria-label="Bausteine-Kategorien">
            <button class="mp-cat-tab mp-cat-tab--active" role="tab"
                    aria-selected="true" data-category="modules"
                    type="button">Module</button>
            <button class="mp-cat-tab" role="tab"
                    aria-selected="false" data-category="queries"
                    type="button">Einzeldaten</button>
        </div>

        <!-- Suche -->
        <div class="mp-search-wrap">
            <span class="mp-search-icon" aria-hidden="true">&#128269;</span>
            <input class="mp-search-input" id="mp-sidebar-search"
                   type="search"
                   placeholder="Suche\u2026"
                   autocomplete="off"
                   aria-label="Bausteine durchsuchen">
        </div>

        <!-- Rollenfilter-Chips (nur im Module-Modus sichtbar) -->
        <div class="mp-role-chips" id="mp-role-chips" role="group"
             aria-label="Rollenfilter">
            ${roleChips}
        </div>

        <!-- Ergebnisliste -->
        <div class="mp-list" id="mp-list" role="listbox"
             aria-label="Verf\u00fcgbare Bausteine">
            <div class="mp-loading" id="mp-loading">Wird geladen\u2026</div>
        </div>
        <div class="mp-empty" id="mp-empty" style="display:none">
            Keine Eintr\u00e4ge gefunden.
        </div>
    </div>`;
}

// ---------------------------------------------------------------------------
// Event-Verdrahtung
// ---------------------------------------------------------------------------

function _bindPanelEvents(body) {
    // Kategorie-Tabs
    body.querySelectorAll('.mp-cat-tab').forEach(btn => {
        btn.addEventListener('click', async () => {
            _activeCategory = btn.dataset.category;
            _selectedId     = null;
            _filterRole     = '';
            // Aktiv-Klassen tauschen
            body.querySelectorAll('.mp-cat-tab').forEach(t => {
                const isActive = t === btn;
                t.classList.toggle('mp-cat-tab--active', isActive);
                t.setAttribute('aria-selected', String(isActive));
            });
            // Rollenfilter nur bei Modules sichtbar
            const chips = document.getElementById('mp-role-chips');
            if (chips) chips.style.display = _activeCategory === 'modules' ? '' : 'none';
            // Filter-Chips zuruecksetzen
            body.querySelectorAll('.mp-chip').forEach((c, i) => {
                const isFirst = i === 0;
                c.classList.toggle('mp-chip-active', isFirst);
                c.setAttribute('aria-pressed', String(isFirst));
            });
            await _loadAndRender();
        });
    });

    // Rollenfilter-Chips
    body.querySelectorAll('.mp-chip').forEach(chip => {
        chip.addEventListener('click', async () => {
            _filterRole   = chip.dataset.role;
            _selectedId   = null;
            body.querySelectorAll('.mp-chip').forEach(c => {
                const isActive = c === chip;
                c.classList.toggle('mp-chip-active', isActive);
                c.setAttribute('aria-pressed', String(isActive));
            });
            await _loadAndRender();
        });
    });

    // Build 115: Drag&Drop — Bausteine per Drag in Editor-Bereich einziehen
    // Beleg: Projektgespraech 2026-05-07
    body.querySelectorAll('.mp-item[draggable]').forEach(item => {
        item.addEventListener('dragstart', (e) => {
            const modId = parseInt(item.dataset.moduleId, 10);
            if (!modId) return;
            const mod = _modules.find(m => m.id === modId);
            if (!mod) return;
            _dbg('Drag start: module_id=', modId, 'title=', mod.title);
            e.dataTransfer.effectAllowed = 'copy';
            // Daten als JSON serialisieren fuer den Drop-Handler im Editor
            e.dataTransfer.setData('application/x-forensic-module', JSON.stringify({
                module_id:   modId,
                block_type:  'paragraph',
                block_data:  JSON.stringify({ text: mod.text || '' }),
                module_text: mod.text || '',
            }));
        });
    });

    // Suche (debounced)
    const searchInput = document.getElementById('mp-sidebar-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            _filterSearch = searchInput.value.trim();
            clearTimeout(_searchTimer);
            _searchTimer = setTimeout(_loadAndRender, SEARCH_DEBOUNCE_MS);
        });
    }
}

// ---------------------------------------------------------------------------
// Laden und Rendern
// ---------------------------------------------------------------------------

async function _loadAndRender() {
    const loading = document.getElementById('mp-loading');
    const empty   = document.getElementById('mp-empty');
    const list    = document.getElementById('mp-list');
    if (loading) { loading.textContent = 'Wird geladen\u2026'; loading.style.display = ''; }
    if (empty)   empty.style.display = 'none';

    try {
        if (_activeCategory === 'modules' && _filterRole === 'standard') {
            // Standard: clientseitig gefiltert, kein API-Aufruf
            // Beleg: Bauplan B6 v0.5 §4.4.1, Build 112
            const q = _filterSearch.toLowerCase();
            const filtered = q
                ? STANDARD_BLOCKS.filter(b => b.title.toLowerCase().includes(q) || b.description.toLowerCase().includes(q))
                : STANDARD_BLOCKS;
            _renderStandardList(filtered);
        } else if (_activeCategory === 'modules') {
            _modules = await _fetchModules(_filterRole, _filterSearch);
            // Build 114: Bei "Alle" (kein Rollenfilter) Standard-Bloecke am Ende anfuegen
            // Beleg: Projektgespraech 2026-05-07
            if (!_filterRole) {
                const q = _filterSearch.toLowerCase();
                const stdFiltered = q
                    ? STANDARD_BLOCKS.filter(b => b.title.toLowerCase().includes(q) || b.description.toLowerCase().includes(q))
                    : STANDARD_BLOCKS;
                _renderListWithStandard(_modules, stdFiltered);
            } else {
                _renderList(_modules);
            }
        } else {
            _queries = await _fetchQueries(_filterSearch);
            _renderQueryList(_queries);
        }
    } catch (_) {
        _modules = [];
        _queries = [];
        _renderList([]);
    }
}

// ---------------------------------------------------------------------------
// Modulliste rendern (_renderList — signaturkompatibel mit Build 093)
// Beleg: Rueckwaerts-Kompatibilitaet (Tests T02-T10)
// ---------------------------------------------------------------------------

/**
 * Rendert die Modulliste in #mp-list.
 * Beleg: Build 093 (signaturkompatibel), Build 105 (erweitert)
 * @param {Array} modules
 */
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

    // Bereits verwendete module_ids (aus den Bloecken des Berichts)
    const usedModuleIds = new Set(
        _currentBlocks
            .filter(b => b.module_id != null)
            .map(b => b.module_id)
    );

    list.innerHTML = modules.map(m => {
        const roleLabel = ROLE_LABELS[m.role] || _esc(m.role);
        const sel       = m.id === _selectedId ? ' mp-item-selected' : '';
        const usedCls   = usedModuleIds.has(m.id) ? ' mp-item-used' : '';
        const preview   = m.description
            ? _esc(m.description.slice(0, PREVIEW_CHARS))
                + (m.description.length > PREVIEW_CHARS ? '\u2026' : '')
            : '';
        return `
            <div class="mp-item${sel}${usedCls}" role="option" draggable="true"
                 aria-selected="${m.id === _selectedId ? 'true' : 'false'}"
                 data-module-id="${m.id}"
                 tabindex="0">
                <div class="mp-item-main">
                    <span class="mp-item-icon" aria-hidden="true">&#128203;</span>
                    <div class="mp-item-text">
                        <span class="mp-item-title">${_esc(m.title)}</span>
                        ${preview
                            ? `<span class="mp-item-desc">${preview}</span>`
                            : ''}
                    </div>
                </div>
                <div class="mp-item-footer">
                    <span class="mp-item-role-badge">${_esc(roleLabel)}</span>
                    <button class="mp-insert-btn" type="button"
                            data-module-id="${m.id}"
                            aria-label="Modul ${_esc(m.title)} einf\u00fcgen">
                        + Einf\u00fcgen
                    </button>
                </div>
            </div>`;
    }).join('');

    // Klick-Events
    list.querySelectorAll('.mp-item').forEach(item => {
        item.addEventListener('click', (e) => {
            // Klick auf Insert-Button: nicht Selektion aendern
            if (e.target.closest('.mp-insert-btn')) return;
            _selectModule(parseInt(item.dataset.moduleId, 10));
        });
        item.addEventListener('keydown', e => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                _selectModule(parseInt(item.dataset.moduleId, 10));
            }
        });
        item.addEventListener('dblclick', () => {
            _selectModule(parseInt(item.dataset.moduleId, 10));
            _insertModule(parseInt(item.dataset.moduleId, 10));
        });
    });

    // Einfuegen-Buttons
    list.querySelectorAll('.mp-insert-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            _insertModule(parseInt(btn.dataset.moduleId, 10));
        });
    });
}

// ---------------------------------------------------------------------------
// Einzeldaten (a:-Queries) rendern
// ---------------------------------------------------------------------------

function _renderQueryList(queries) {
    const list    = document.getElementById('mp-list');
    const empty   = document.getElementById('mp-empty');
    const loading = document.getElementById('mp-loading');
    if (!list) return;

    if (loading) loading.style.display = 'none';

    if (!queries.length) {
        list.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
    }
    if (empty) empty.style.display = 'none';

    list.innerHTML = queries.map(q => {
        const preview = q.description
            ? _esc(q.description.slice(0, PREVIEW_CHARS))
                + (q.description.length > PREVIEW_CHARS ? '\u2026' : '')
            : '';
        const tags = (q.tags || []).map(t => `<span class="mp-tag-chip">${_esc(t)}</span>`).join('');
        return `
            <div class="mp-item" role="option"
                 aria-selected="false"
                 data-query-id="${_esc(q.id)}"
                 tabindex="0">
                <div class="mp-item-main">
                    <span class="mp-item-icon" aria-hidden="true">&#128196;</span>
                    <div class="mp-item-text">
                        <span class="mp-item-title">${_esc(q.title || q.id)}</span>
                        ${preview
                            ? `<span class="mp-item-desc">${preview}</span>`
                            : ''}
                        ${tags ? `<div class="mp-tag-row">${tags}</div>` : ''}
                    </div>
                </div>
                <div class="mp-item-footer">
                    <button class="mp-insert-btn" type="button"
                            data-query-id="${_esc(q.id)}"
                            aria-label="Einzeldatum ${_esc(q.title || q.id)} einf\u00fcgen">
                        + Einf\u00fcgen
                    </button>
                </div>
            </div>`;
    }).join('');

    list.querySelectorAll('.mp-insert-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            _insertQuery(btn.dataset.queryId);
        });
    });
}

// ---------------------------------------------------------------------------
// Standard-Blöcke rendern
// ---------------------------------------------------------------------------

/**
 * Rendert die clientseitige Standard-Blockliste in #mp-list.
 * Kein API-Aufruf — Editor.js-Systemkategorie (Bauplan B6 §4.4.1).
 * Beleg: Build 112, Projektgespraech 2026-05-07
 * @param {Array} blocks  Gefilterte Eintraege aus STANDARD_BLOCKS
 */
function _renderStandardList(blocks) {
    const list    = document.getElementById('mp-list');
    const empty   = document.getElementById('mp-empty');
    const loading = document.getElementById('mp-loading');
    if (!list) return;
    if (loading) loading.style.display = 'none';
    if (!blocks.length) {
        list.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
    }
    if (empty) empty.style.display = 'none';

    list.innerHTML = blocks.map(b => `
        <div class="mp-item mp-item--standard" data-std-type="${_esc(b.block_type)}"
             role="listitem" tabindex="0"
             title="${_esc(b.description)}">
            <div class="mp-item-header">
                <span class="mp-item-icon" aria-hidden="true">${_esc(b.icon)}</span>
                <span class="mp-item-title">${_esc(b.title)}</span>
            </div>
            <div class="mp-item-preview">${_esc(b.description)}</div>
            <button class="mp-btn-insert" type="button"
                    data-std-type="${_esc(b.block_type)}"
                    title="${_esc(b.title)} einfuegen"
                    aria-label="${_esc(b.title)} in Editor einfuegen">
                + Einfügen
            </button>
        </div>
    `).join('');

    // Insert-Handler: neuen leeren Block des gewuenschten Typs anlegen
    list.querySelectorAll('.mp-btn-insert[data-std-type]').forEach(btn => {
        btn.addEventListener('click', () => {
            const blockType = btn.dataset.stdType;
            _dbg('Standard-Block einfuegen: type=', blockType);
            if (window._editor?.blocks?.insert) {
                window._editor.blocks.insert(blockType);
                // Fokus in den neuen Block setzen
                const idx = window._editor.blocks.getBlocksCount() - 1;
                window._editor.caret.setToBlock(idx);
            } else {
                _dbg('Standard-Block: _editor nicht verfuegbar');
            }
        });
    });

    // Tastatur: Enter/Space oeffnen Insert
    list.querySelectorAll('.mp-item--standard').forEach(item => {
        item.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                item.querySelector('.mp-btn-insert')?.click();
            }
        });
    });
}

// ---------------------------------------------------------------------------
// Selektion (_selectModule — signaturkompatibel mit Build 093)
// ---------------------------------------------------------------------------

/**
 * Setzt die Selektion auf ein Modul.
 * Beleg: Build 093 (signaturkompatibel), Build 105
 * @param {number} id
 */
function _selectModule(id) {
    _selectedId = id;

    document.querySelectorAll('.mp-item').forEach(el => {
        const mid     = parseInt(el.dataset.moduleId, 10);
        const selected = mid === id;
        el.classList.toggle('mp-item-selected', selected);
        el.setAttribute('aria-selected', selected ? 'true' : 'false');
    });
}
/**
 * Rendert Modulliste + Standard-Bloecke in #mp-list (fuer "Alle"-Ansicht).
 * Build 114: Standard-Bloecke werden nach den regulaeren Modulen angezeigt.
 * Beleg: Projektgespraech 2026-05-07
 * @param {Array} modules
 * @param {Array} stdBlocks
 */
function _renderListWithStandard(modules, stdBlocks) {
    const list    = document.getElementById('mp-list');
    const empty   = document.getElementById('mp-empty');
    const loading = document.getElementById('mp-loading');
    if (!list) return;
    if (loading) loading.style.display = 'none';

    if (!modules.length && !stdBlocks.length) {
        list.innerHTML = '';
        if (empty) empty.style.display = '';
        return;
    }
    if (empty) empty.style.display = 'none';

    // Module-Eintraege rendern (wiederverwendet _renderList-Logik)
    _renderList(modules);

    // Standard-Trenner + Standard-Eintraege anhaengen
    if (stdBlocks.length) {
        const divider = document.createElement('div');
        divider.className = 'mp-std-divider';
        divider.textContent = 'Standard-Blöcke';
        list.appendChild(divider);

        const stdHolder = document.createElement('div');
        stdHolder.className = 'mp-std-section';
        list.appendChild(stdHolder);

        // Standard-Rendering in den stdHolder umleiten
        const origList = document.getElementById('mp-list');
        // Temporaer stdHolder als Ziel setzen via innere Render-Funktion
        stdHolder.innerHTML = stdBlocks.map(b => `
            <div class="mp-item mp-item--standard" data-std-type="${_esc(b.block_type)}"
                 role="listitem" tabindex="0" title="${_esc(b.description)}">
                <div class="mp-item-header">
                    <span class="mp-item-icon" aria-hidden="true">${_esc(b.icon)}</span>
                    <span class="mp-item-title">${_esc(b.title)}</span>
                </div>
                <button class="mp-btn-insert" type="button"
                        data-std-type="${_esc(b.block_type)}"
                        title="${_esc(b.title)} einfügen">+ Einfügen</button>
            </div>
        `).join('');

        stdHolder.querySelectorAll('.mp-btn-insert[data-std-type]').forEach(btn => {
            btn.addEventListener('click', () => {
                if (window._editor?.blocks?.insert) {
                    window._editor.blocks.insert(btn.dataset.stdType);
                }
            });
        });
    }
}


// ---------------------------------------------------------------------------
// Einfuegen
// ---------------------------------------------------------------------------

/**
 * Fuegt ein Modul als neuen Block in den Bericht ein.
 * Nach dem Einfuegen: Formular-Akkordeon automatisch oeffnen (Phase 6).
 * Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
 */
async function _insertModule(moduleId) {
    if (!moduleId) return;
    if (!_currentOpts.lockId) {
        _showInsertError('Kein aktiver Lock. Bitte Seite neu laden.');
        return;
    }

    const btn = document.querySelector(`.mp-insert-btn[data-module-id="${moduleId}"]`);
    if (btn) { btn.disabled = true; btn.textContent = '\u2026'; }

    try {
        // 1. Modul-Body laden
        const m = await _fetchModuleBody(moduleId);
        if (!m) throw new Error('Modul nicht geladen.');

        // 2. block_data aufbauen: text = Modul-Body (Template-Syntax)
        const blockData = JSON.stringify({ text: m.body || '' });

        // 3. Block speichern (Phase 4 Block-API)
        const blockId = _generateUUID();
        const resp = await fetch(REPORT_API, {
            method:  'POST',
            headers: {
                'Content-Type':          'application/json',
                'X-Forensic-Request':    'ajax',
                'X-Forensic-Lock-Id':    _currentOpts.lockId || '',
            },
            body: JSON.stringify({
                action:     'save_block',
                block_id:   blockId,
                report_id:  _currentOpts.reportId,
                block_type: 'paragraph',
                block_data: blockData,
                module_id:  moduleId,
            }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error || 'HTTP ' + resp.status);

        // 4. Formular-Akkordeon oeffnen (Phase 6)
        const sidebar     = document.getElementById('support-sidebar');
        const formSection = sidebar?.querySelector('[data-accordion="form"]');
        if (formSection && typeof window.openAccordionSection === 'function') {
            window.openAccordionSection(formSection);
        }

        // 5. Callback
        if (_currentOpts.onInserted) {
            await _currentOpts.onInserted(blockId, moduleId, m.body || '');
        }

    } catch (err) {
        _showInsertError(String(err));
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '+ Einf\u00fcgen'; }
    }
}

/**
 * Fuegt einen a:-Query-Platzhalter als neuen Paragraph-Block ein.
 * Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
 */
async function _insertQuery(queryId) {
    if (!queryId) return;
    if (!_currentOpts.lockId) {
        _showInsertError('Kein aktiver Lock. Bitte Seite neu laden.');
        return;
    }

    const btn = document.querySelector(`.mp-insert-btn[data-query-id="${queryId}"]`);
    if (btn) { btn.disabled = true; btn.textContent = '\u2026'; }

    try {
        const blockData = JSON.stringify({ text: `{{a:${queryId}}}` });
        const blockId   = _generateUUID();
        const resp = await fetch(REPORT_API, {
            method:  'POST',
            headers: {
                'Content-Type':       'application/json',
                'X-Forensic-Request': 'ajax',
                'X-Forensic-Lock-Id': _currentOpts.lockId || '',
            },
            body: JSON.stringify({
                action:     'save_block',
                block_id:   blockId,
                report_id:  _currentOpts.reportId,
                block_type: 'paragraph',
                block_data: blockData,
            }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data.error || 'HTTP ' + resp.status);

        if (_currentOpts.onInserted) {
            await _currentOpts.onInserted(blockId, null, `{{a:${queryId}}}`);
        }

    } catch (err) {
        _showInsertError(String(err));
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '+ Einf\u00fcgen'; }
    }
}

function _showInsertError(msg) {
    const list = document.getElementById('mp-list');
    if (!list) return;
    const errDiv = document.createElement('div');
    errDiv.className = 'mp-insert-error';
    errDiv.textContent = 'Einf\u00fcgen fehlgeschlagen: ' + msg;
    list.prepend(errDiv);
    setTimeout(() => errDiv.remove(), 4000);
}

function _generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

// ---------------------------------------------------------------------------
// Rueckwaerts-Kompatibilitaet: open() / close() (Modal-API, Build 093)
// Beleg: Build 105, Rueckwaerts-Kompatibilitaet
// ---------------------------------------------------------------------------

/**
 * Stub: open() aus Build 093. Oeffnet jetzt das Bausteine-Akkordeon
 * statt eines Modals.
 */
function open(options) {
    // Bausteine-Akkordeon oeffnen
    const sidebar      = document.getElementById('support-sidebar');
    const blocksSection = sidebar?.querySelector('[data-accordion="blocks"]');
    if (blocksSection && typeof window.openAccordionSection === 'function') {
        window.openAccordionSection(blocksSection);
    }
}

/** Stub: close() — kein Modal in Phase 7. */
function close() {}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

_dbg('module_panel.js: window.ModulePanel exportiert');
window.ModulePanel = {
    // Phase 7 Haupt-API
    showPanel,
    // Unveraenderte Kern-Funktionen (Tests T01-T10)
    _renderList,
    _selectModule,
    // Phase 7 Tests
    _renderSkeleton,
    // Rueckwaerts-Kompatibilitaet
    open,
    close,
    // Interna
    _fetchModules,
};

// Alias: var ModulePanel (fuer Tests ohne window-Prafix)
var ModulePanel = window.ModulePanel;

})();
