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
 *   Build 133 (2026-05-09): Bug 2.22, 2.3, 1.21 (teilw.) behoben.
 *     - Bug 2.22: _renderListWithStandard ruft _renderList([]) nicht mehr auf
 *       wenn modules leer ist, damit mp-empty nicht faelschlich eingeblendet wird.
 *     - Bug 2.3: mp-item-preview in _renderListWithStandard eingefuegt (war nur
 *       in _renderStandardList vorhanden).
 *     Beleg: Bugfix Build 133, Projektgespraech 2026-05-09.
 *
 * Version: v0.6.158 · Build: 158 · 2026-05-10
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
// Build 389: Vorlagen (VOLLSTAENDIGE Berichtsgerueste).
// Abgrenzung, die man staendig verwechselt:
//   MODUL   = EIN Textbaustein  -> wird als EIN paragraph-Block eingefuegt.
//   VORLAGE = EIN GANZER BERICHT -> mehrere typisierte Bloecke (header,
//             paragraph, TABLE). Wird NICHT vom Client Block fuer Block
//             geschrieben, sondern serverseitig und TRANSAKTIONAL ueber die
//             Aktion 'insert_template' (Build 388). Wuerde der Client die
//             Bloecke einzeln senden, koennte bei einem Abbruch ein HALBER
//             Spurenvermerk stehenbleiben — der wie ein vollstaendiger aussieht.
// Beleg: Bauplan Build 389 §4, Projektgespraech 2026-07-12
const FULL_TEMPLATES_API = '/_forensic/templates/full';
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
let _activeCategory  = 'modules';  // 'modules' | 'queries' | 'templates'
let _templates       = [];     // geladene Vorlagen (Vorlagen-Ansicht, Build 389)
// Bug 2.117 Fix Build 211: _filterRole unter dem _modules zuletzt geladen wurde.
// Wenn _filterRole wechselt, ist der Cache ungueltig.
// Beleg: Bugfix Build 211, Projektgespraech 2026-05-17
let _modulesLoadedWithRole = null;  // undefined = noch nie geladen
let _searchTimer     = null;
/**
 * Bug 2.41 Fix Build 136: Gespeicherte Cursor-Position im Editor.
 * mousedown-Handler auf Einfuegen-Buttons speichert die aktive Selection
 * bevor der Button-Klick den Fokus vom contenteditable nimmt.
 * _insertQuery() stellt die Selection vor execCommand wieder her.
 * Beleg: Bugfix Build 136, Projektgespraech 2026-05-09
 */
let _savedCursorRange = null;
/**
 * Bug 2.64 Fix Build 155/156: _justDropped als Modulvariable.
 * Verhindert Doppel-Insert wenn ein Drop auf einem +Einfuegen-Button landet.
 * Muss Modulvariable sein damit _setJustDropped() darauf zugreifen kann.
 * Beleg: Bugfix Build 156, Projektgespraech 2026-05-10
 */
let _justDropped = false;

// ---------------------------------------------------------------------------
// API-Abfragen
// ---------------------------------------------------------------------------

/**
 * _fehlerAusAntwort: baut eine Fehlermeldung, die den SERVER zu Wort kommen
 * laesst (Build 583).
 *
 * BEFUND mc (2026-07-30): der Server erklaert seit Build 582 genau, was zu tun
 * ist - bei einer nicht migrierten templates.db etwa 'die ALTE Tabelle
 * placeholder_queries gefunden, migrate_templates_placeholders.py ausfuehren'.
 * In der Konsole stand trotzdem nur 'Error: HTTP 503', weil alle drei Abrufer
 * den ANTWORTKOERPER WEGWARFEN. Die Diagnose war da und kam nie an.
 *
 * Ein Fehler, der die Ursache kennt und verschweigt, ist so gut wie keiner.
 */
async function _fehlerAusAntwort(resp, was) {
    let zusatz = '';
    try {
        const roh = await resp.text();
        try {
            const b = JSON.parse(roh);
            // 'massnahme' ist die Handlungsanweisung, 'error'/'ursache' der
            // Befund. Was da ist, wird genommen - nichts wird geraten.
            zusatz = [b.massnahme, b.error, b.ursache]
                .filter(Boolean).join(' — ');
        } catch (e) {
            zusatz = roh.slice(0, 300);
        }
    } catch (e) {
        // Koerper nicht lesbar: dann eben ohne. Kein Grund, den Fehler
        // seinerseits zu verschlucken.
    }
    return new Error(was + ' (HTTP ' + resp.status + ')'
        + (zusatz ? ': ' + zusatz : ''));
}

async function _fetchModules(role, search) {
    const params = new URLSearchParams();
    if (role)   params.set('role',   role);
    if (search) params.set('search', search);
    const url = TEMPLATES_API + (params.toString() ? '?' + params.toString() : '');
    const resp = await fetch(url, { headers: { 'X-Forensic-Request': 'ajax' } });
    if (!resp.ok) {
        throw await _fehlerAusAntwort(resp, 'Bausteine konnten nicht geladen werden');
    }
    return resp.json();
}

async function _fetchModuleBody(id) {
    const resp = await fetch(TEMPLATES_API + '/' + id, {
        headers: { 'X-Forensic-Request': 'ajax' },
    });
    if (!resp.ok) return null;
    return resp.json();
}

/**
 * Laedt die Liste der VOLLSTAENDIGEN Berichtsvorlagen (ohne blocks_json —
 * das kann gross sein und wird zum Anzeigen nicht gebraucht).
 * Beleg: Bauplan Build 389 §4
 */
async function _fetchTemplates(search) {
    const url = FULL_TEMPLATES_API + (search ? '?search=' + encodeURIComponent(search) : '');
    _dbg('_fetchTemplates:', url);
    const resp = await fetch(url, { headers: { 'X-Forensic-Request': 'ajax' } });
    if (!resp.ok) {
        throw await _fehlerAusAntwort(resp, 'Vorlagen konnten nicht geladen werden');
    }
    return await resp.json();
}

async function _fetchQueries(search) {
    const params = new URLSearchParams();
    if (search) params.set('search', search);
    const url = LIBRARY_API + (params.toString() ? '?' + params.toString() : '');
    const resp = await fetch(url, { headers: { 'X-Forensic-Request': 'ajax' } });
    // BUILD 581: NICHT MEHR SCHLUCKEN.
    // Bis hierher wurde JEDE Fehlerantwort zu einer leeren Liste - auch das
    // 503 'Datenbank nicht erreichbar' aus Build 580. Deshalb meldeten
    // 'Module' und 'Vorlagen' den Ausfall, die 'Einzeldaten' aber nicht
    // (Befund mc 2026-07-30): die beiden anderen Abrufer werfen seit jeher,
    // dieser eine nicht. Eine leere Bibliothek und eine unerreichbare
    // Bibliothek sind zweierlei.
    if (!resp.ok) {
        throw await _fehlerAusAntwort(resp, 'Einzeldaten konnten nicht geladen werden');
    }
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
    // Bug 2.13 Fix Build 123: _activeCategory und _filterRole bleiben erhalten
    // (_renderSkeleton reflektiert _activeCategory jetzt korrekt).
    // Beleg: Bugfix Build 123, Projektgespraech 2026-05-08
    _filterSearch   = '';
    _selectedId     = null;

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
        // Bug 2.118 Fix Build 212: Aktiven Chip aus _filterRole bestimmen
        // statt immer 'Alle'. Beleg: Bugfix Build 212, 2026-05-17
        const isActive = role === _filterRole;
        const active = isActive ? ' mp-chip-active' : '';
        return `<button class="mp-chip${active}" type="button"
                    data-role="${_esc(role)}"
                    aria-pressed="${isActive ? 'true' : 'false'}">${_esc(label)}</button>`;
    }).join('');

    return `
    <div class="mp-panel">
        <!-- Kategorie-Umschalter -->
        <div class="mp-cat-tabs" role="tablist" aria-label="Bausteine-Kategorien">
            <button class="mp-cat-tab${_activeCategory === 'modules' ? ' mp-cat-tab--active' : ''}" role="tab"
                    aria-selected="${String(_activeCategory === 'modules')}" data-category="modules"
                    type="button">Module</button>
            <button class="mp-cat-tab${_activeCategory === 'queries' ? ' mp-cat-tab--active' : ''}" role="tab"
                    aria-selected="${String(_activeCategory === 'queries')}" data-category="queries"
                    type="button">Einzeldaten</button>
            <!-- Build 389: dritter Reiter. Bewusst 'Vorlagen' und nicht
                 'Komplett'/'Voll-Vorlagen': kurz genug fuer die Tab-Leiste; der
                 Untertitel der Liste sagt, was dahintersteckt. -->
            <button class="mp-cat-tab${_activeCategory === 'templates' ? ' mp-cat-tab--active' : ''}" role="tab"
                    aria-selected="${String(_activeCategory === 'templates')}" data-category="templates"
                    type="button">Vorlagen</button>
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
             aria-label="Rollenfilter"
             style="${_activeCategory !== 'modules' ? 'display:none' : ''}">
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
        btn.addEventListener('click', async (evt) => {
            window._uevt?.(evt, 'module_panel', 'click:mp-cat-tab', { category: btn.dataset.category }); // B200
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
        chip.addEventListener('click', async (evt) => {
            window._uevt?.(evt, 'module_panel', 'click:mp-chip', { role: chip.dataset.role }); // B200
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

    // Build 115: Drag&Drop via Event-Delegation auf body.
    // Bug 2.11 Fix Build 147: Per-Item-Listener sind in Firefox ESR innerhalb
    // von Scroll-Containern unzuverlässig. Event-Delegation löst das.
    // Bug 2.64 Fix Build 155: _justDropped-Flag verhindert Doppel-Insert wenn
    // der Drop auf einem +Einfuegen-Button landet und dessen click-Event feuert.
    // Build 156: _justDropped ist jetzt Modulvariable (nicht mehr lokal).
    // Beleg: Bugfix Build 156, Projektgespraech 2026-05-10

    body.addEventListener('dragstart', () => { _justDropped = false; });
    body.addEventListener('dragend',   () => {
        // Nach kurzer Verzoegerung zuruecksetzen damit der drop+click-Zyklus
        // abgeschlossen ist bevor das Flag zurueckgesetzt wird.
        setTimeout(() => { _justDropped = false; }, 400);
    });

    body.addEventListener('dragstart', (e) => {
        window._uevt?.(e, 'module_panel', 'dragstart:mp-item'); // B200
        const item = e.target.closest('.mp-item[draggable]');
        if (!item) return;
        const modId = parseInt(item.dataset.moduleId, 10);
        if (modId) {
            const mod = _modules.find(m => m.id === modId);
            if (!mod) return;
            _dbg('Drag start (Modul, delegiert): module_id=', modId, 'title=', mod.title);
            e.dataTransfer.effectAllowed = 'copy';
            // Build 655 (Ticket 5d81a0c7): der Blocktyp kommt jetzt AUS DEM
            // BAUSTEIN und ist nicht mehr fest 'paragraph'. Die Listenantwort
            // (GET /_forensic/templates) traegt ihn seit diesem Build mit.
            //
            // block_data wird beim Ziehen bewusst NICHT mitgegeben: die
            // Listenantwort enthaelt weder body noch block_data (beide
            // koennen gross sein). Der Empfaenger laedt den Baustein bei
            // Bedarf einzeln nach - dort kommen die Blockdaten mit. Ein hier
            // aus mod.body gebautes { text: ... } waere fuer einen
            // Tabellen-Baustein schlicht falsch.
            e.dataTransfer.setData('application/x-forensic-module', JSON.stringify({
                module_id:   modId,
                block_type:  mod.block_type || 'paragraph',
                module_text: mod.body || '',
            }));
        } else {
            const blockType = item.dataset.blockType || 'paragraph';
            _dbg('Drag start (Standard, delegiert): type=', blockType);
            e.dataTransfer.effectAllowed = 'copy';
            e.dataTransfer.setData('application/x-forensic-standard', JSON.stringify({
                block_type: blockType,
                title:      item.querySelector('.mp-item-title')?.textContent?.trim() || '',
            }));
        }
    });

    // Suche (debounced)
    const searchInput = document.getElementById('mp-sidebar-search');
    if (searchInput) {
        searchInput.addEventListener('input', (evt) => {
            window._uevt?.(evt, 'module_panel', 'input:mp-sidebar-search', { value: searchInput.value }); // B200
            _filterSearch = searchInput.value.trim();
            clearTimeout(_searchTimer);
            _searchTimer = setTimeout(_loadAndRender, SEARCH_DEBOUNCE_MS);
        });
    }
}

// ---------------------------------------------------------------------------
// Laden und Rendern
// ---------------------------------------------------------------------------

async function _loadAndRender(forceReload = false) {
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
            // Build 124: Cache — nur laden wenn leer oder Force-Reload.
            // Module aendern sich selten; kein Re-Fetch bei jedem Akkordeon-Wechsel.
            // Bug 2.117 Fix Build 211: Cache auch ungueltig wenn _filterRole sich
            // gegenueber dem letzten Ladevorgang geaendert hat. Ohne diese Pruefung
            // blieben bei Rueckkehr zu 'Alle' (filterRole='') die unter 'Fazit'
            // geladenen Module im Cache.
            // Beleg: Bugfix Build 211, Projektgespraech 2026-05-17
            const _roleChanged = _filterRole !== _modulesLoadedWithRole;
            if (forceReload || _modules.length === 0 || _filterRole || _filterSearch || _roleChanged) {
                _modules = await _fetchModules(_filterRole, _filterSearch);
                _modulesLoadedWithRole = _filterRole;
            }
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
        } else if (_activeCategory === 'templates') {
            // Build 389: Vorlagen. Kein Cache-Ueberspringen bei Force-Reload.
            if (forceReload || _templates.length === 0 || _filterSearch) {
                _templates = await _fetchTemplates(_filterSearch);
            }
            _renderTemplateList(_templates);
        } else {
            // Build 124: Cache fuer Queries
            if (forceReload || _queries.length === 0 || _filterSearch) {
                _queries = await _fetchQueries(_filterSearch);
            }
            _renderQueryList(_queries);
        }
    } catch (err) {
        // GRUNDREGEL 1: Ein Ladefehler darf nicht als 'keine Eintraege
        // vorhanden' erscheinen — das sieht fuer den Ermittler aus wie eine
        // leere, aber funktionierende Bibliothek. Fehler sichtbar machen.
        // Beleg: Bauplan Build 389 §4
        console.error('module_panel.js: Laden fehlgeschlagen:', err);
        _modules   = [];
        _queries   = [];
        _templates = [];
        const list    = document.getElementById('mp-list');
        const loading = document.getElementById('mp-loading');
        const empty   = document.getElementById('mp-empty');
        if (loading) loading.style.display = 'none';
        if (empty)   empty.style.display = 'none';
        if (list) {
            list.innerHTML = `<div class="mp-error" role="alert">
                Die Bausteine konnten nicht geladen werden.
                <br><small>${_esc(String(err && err.message ? err.message : err))}</small>
            </div>`;

            // BUILD 581: WAS OHNE DATENBANK GEHT, BLEIBT NUTZBAR.
            //
            // Befund mc (2026-07-30): seit der Server einen Ausfall meldet
            // (Build 579/580), verschwanden in der Ansicht 'Alle' auch die
            // STANDARD-BLOECKE - Absatz, Ueberschrift, Liste, Tabelle, Zitat,
            // Trennlinie. Die stehen als Konstante in dieser Datei und
            // brauchen ueberhaupt keine Datenbank. Aus einem Teilausfall
            // wurde so ein Totalausfall: der Redakteur konnte nicht einmal
            // mehr einen leeren Absatz einfuegen.
            //
            // Richtig ist: zeigen, was da ist - und sagen, was fehlt. Beides,
            // nicht eines davon.
            if (_activeCategory === 'modules' && !_filterRole) {
                const q = _filterSearch.toLowerCase();
                const stdFiltered = q
                    ? STANDARD_BLOCKS.filter(b =>
                        b.title.toLowerCase().includes(q)
                        || b.description.toLowerCase().includes(q))
                    : STANDARD_BLOCKS;
                if (stdFiltered.length) {
                    const hinweis = document.createElement('div');
                    hinweis.className = 'mp-hinweis';
                    hinweis.textContent = 'Die Standard-Bausteine stehen '
                        + 'weiterhin zur Verfuegung - sie brauchen keine '
                        + 'Datenbank.';
                    list.appendChild(hinweis);
                    _appendStandardBlocks(list, stdFiltered);
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Vorlagenliste rendern (Build 389)
// ---------------------------------------------------------------------------

/**
 * Rendert die Liste der vollstaendigen Berichtsvorlagen in #mp-list.
 *
 * Bewusst KEIN Drag&Drop (anders als bei Modulen): eine Vorlage wird immer
 * als GANZES am Ende des Berichts eingefuegt. Ein Drop mitten in einen
 * bestehenden Bericht wuerde suggerieren, man koenne sie an eine beliebige
 * Stelle setzen — die Bloecke werden aber serverseitig ans Ende gehaengt
 * (save_blocks_bulk, Build 388). Ein Knopf sagt die Wahrheit, ein Drag-Ziel
 * wuerde luegen.
 * Beleg: Bauplan Build 389 §4
 *
 * @param {Array} templates
 */
function _renderTemplateList(templates) {
    const list    = document.getElementById('mp-list');
    const empty   = document.getElementById('mp-empty');
    const loading = document.getElementById('mp-loading');
    if (!list) return;

    if (loading) loading.style.display = 'none';

    if (!templates.length) {
        list.innerHTML = '';
        if (empty) {
            empty.textContent = 'Keine Vorlagen vorhanden.';
            empty.style.display = '';
        }
        return;
    }
    if (empty) empty.style.display = 'none';

    const intro = `<div class="mp-cat-intro">
        Vollst\u00e4ndige Berichtsvorlagen. Beim Einf\u00fcgen werden alle
        Bausteine der Vorlage gemeinsam an das Ende des Berichts angeh\u00e4ngt.
    </div>`;

    list.innerHTML = intro + templates.map(t => {
        const desc = t.description
            ? _esc(t.description.slice(0, PREVIEW_CHARS))
                + (t.description.length > PREVIEW_CHARS ? '\u2026' : '')
            : '';
        return `
            <div class="mp-item mp-item--template" role="option"
                 aria-selected="false"
                 data-template-key="${_esc(t.template_key)}"
                 tabindex="0">
                <div class="mp-item-main">
                    <span class="mp-item-icon" aria-hidden="true">&#128203;</span>
                    <div class="mp-item-text">
                        <span class="mp-item-title">${_esc(t.title || t.template_key)}</span>
                        ${desc ? `<span class="mp-item-desc">${desc}</span>` : ''}
                    </div>
                </div>
                <div class="mp-item-footer">
                    <button class="mp-insert-btn" type="button"
                            data-template-key="${_esc(t.template_key)}"
                            aria-label="Vorlage ${_esc(t.title || t.template_key)} einf\u00fcgen">
                        + Vorlage einf\u00fcgen
                    </button>
                </div>
            </div>`;
    }).join('');

    list.querySelectorAll('.mp-insert-btn[data-template-key]').forEach(btn => {
        btn.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'module_panel', 'click:vorlage-insert-btn',
                           { templateKey: btn.dataset.templateKey }); // B200
            _insertTemplate(btn.dataset.templateKey);
        });
    });
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
            window._uevt?.(e, 'module_panel', 'click:mp-item', { moduleId: item.dataset.moduleId }); // B200
            // Klick auf Insert-Button: nicht Selektion aendern
            if (e.target.closest('.mp-insert-btn')) return;
            _selectModule(parseInt(item.dataset.moduleId, 10));
        });
        item.addEventListener('keydown', e => {
            window._uevt?.(e, 'module_panel', 'keydown:mp-item', { key: e.key, moduleId: item.dataset.moduleId }); // B200
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                _selectModule(parseInt(item.dataset.moduleId, 10));
            }
        });
        item.addEventListener('dblclick', (e) => {
            window._uevt?.(e, 'module_panel', 'dblclick:mp-item', { moduleId: item.dataset.moduleId }); // B200
            _selectModule(parseInt(item.dataset.moduleId, 10));
            _insertModule(parseInt(item.dataset.moduleId, 10));
        });
    });

    // Einfuegen-Buttons
    list.querySelectorAll('.mp-insert-btn').forEach(btn => {
        btn.addEventListener('mousedown', (e) => { window._uevt?.(e, 'module_panel', 'mousedown:mp-insert-btn'); _justDropped = false; }); // B200
        btn.addEventListener('click', (e) => {
            window._uevt?.(e, 'module_panel', 'click:mp-insert-btn'); // B200
            e.stopPropagation();
            // Bug 2.64 Fix Build 155: Nach einem Drop den Click ignorieren.
            if (_justDropped) {
                _dbg('mp-insert-btn click nach Drop ignoriert (_justDropped)');
                _justDropped = false;
                return;
            }
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
        // Bug 2.41 Fix Build 136: mousedown speichert Selection VOR dem
        // Fokus-Verlust durch den Button-Klick. Der click-Handler laeuft
        // danach mit der gespeicherten Range in _savedCursorRange.
        // Beleg: Bugfix Build 136, Projektgespraech 2026-05-09
        btn.addEventListener('mousedown', (e) => {
            window._uevt?.(e, 'module_panel', 'mousedown:einzeldaten-insert-btn', { queryId: btn.dataset.queryId }); // B200
            const holder = document.getElementById('editorjs-holder');
            const active = document.activeElement;
            if (active && active.isContentEditable && holder?.contains(active)) {
                const sel = window.getSelection();
                if (sel && sel.rangeCount > 0) {
                    _savedCursorRange = sel.getRangeAt(0).cloneRange();
                } else {
                    _savedCursorRange = null;
                }
            } else {
                _savedCursorRange = null;
            }
        });
        btn.addEventListener('click', (e) => {
            window._uevt?.(e, 'module_panel', 'click:einzeldaten-insert-btn', { queryId: btn.dataset.queryId }); // B200
            e.stopPropagation();
            _insertQuery(btn.dataset.queryId);
        });
    });

    // Bug 2.110 Fix Build 234: Doppelklick auf Einzeldatum fuegt es sofort ein.
    // Analoges Verhalten zu Modulen (dblclick:mp-item).
    // Beleg: Bugfix Build 234, Projektgespraech 2026-05-18
    list.querySelectorAll('.mp-item[data-query-id]').forEach(item => {
        item.addEventListener('dblclick', (e) => {
            window._uevt?.(e, 'module_panel', 'dblclick:einzeldaten-item',
                { queryId: item.dataset.queryId }); // B200
            _insertQuery(item.dataset.queryId);
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
             data-block-type="${_esc(b.block_type)}"
             role="listitem" tabindex="0" draggable="true"
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

    // Drag&Drop via Event-Delegation auf #mp-list.
    // Bug 2.11 Fix Build 147: Firefox feuert dragstart nicht zuverlässig auf
    // einzelnen Items innerhalb von Scroll-Containern. Event-Delegation auf dem
    // Container ist stabiler in Firefox ESR.
    // Beleg: Bugfix Build 147, Projektgespraech 2026-05-10
    list.addEventListener('dragstart', (e) => {
        const item = e.target.closest('.mp-item--standard[draggable]');
        if (!item) return;
        window._uevt?.(e, 'module_panel', 'dragstart:standard-block', { blockType: item.dataset.blockType }); // B200
        const blockType = item.dataset.blockType || item.dataset.stdType || 'paragraph';
        _dbg('Drag start (Standard, delegiert): type=', blockType);
        e.dataTransfer.effectAllowed = 'copy';
        e.dataTransfer.setData('application/x-forensic-standard', JSON.stringify({
            block_type: blockType,
            title:      item.querySelector('.mp-item-title')?.textContent?.trim() || '',
        }));
    });
    list.querySelectorAll('.mp-btn-insert[data-std-type]').forEach(btn => {
        btn.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'module_panel', 'click:std-block-insert', { blockType: btn.dataset.stdType }); // B200
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
            window._uevt?.(e, 'module_panel', 'keydown:std-block-item', { key: e.key }); // B200
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                item.querySelector('.mp-btn-insert')?.click();
            }
        });
        // Bug 2.110 Fix Build 234: Doppelklick fuegt Standard-Block sofort ein.
        // Analoges Verhalten zu Modulen.
        // Beleg: Bugfix Build 234, Projektgespraech 2026-05-18
        item.addEventListener('dblclick', (e) => {
            window._uevt?.(e, 'module_panel', 'dblclick:std-block-item',
                { blockType: item.dataset.blockType }); // B200
            item.querySelector('.mp-btn-insert')?.click();
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
 * _appendStandardBlocks: haengt die Standard-Bloecke an eine Liste an.
 *
 * BUILD 581 - HERAUSGELOEST aus _renderListWithStandard, weil derselbe
 * Aufbau jetzt an ZWEI Stellen gebraucht wird: im Normalfall und im
 * Fehlerfall. Eine Kopie waere die naechste Drift gewesen - beim
 * naechsten Umbau der Kacheln haette nur eine der beiden gewirkt.
 */
function _appendStandardBlocks(list, stdBlocks) {
    if (!list || !stdBlocks || !stdBlocks.length) { return; }
    const divider = document.createElement('div');
    divider.className = 'mp-std-divider';
    divider.textContent = 'Standard-Blöcke';
    list.appendChild(divider);

    const stdHolder = document.createElement('div');
    stdHolder.className = 'mp-std-section';
    list.appendChild(stdHolder);

    // mp-item-preview hinzugefuegt (Bug 2.3 Fix Build 133)
    // Bug 2.63 Fix Build 149: draggable="true" + data-block-type fehlten.
    // Beleg: Bugfix Build 149, Projektgespraech 2026-05-10
    stdHolder.innerHTML = stdBlocks.map(b => `
        <div class="mp-item mp-item--standard" data-std-type="${_esc(b.block_type)}"
             data-block-type="${_esc(b.block_type)}"
             role="listitem" tabindex="0" draggable="true" title="${_esc(b.description)}">
            <div class="mp-item-header">
                <span class="mp-item-icon" aria-hidden="true">${_esc(b.icon)}</span>
                <span class="mp-item-title">${_esc(b.title)}</span>
            </div>
            <div class="mp-item-preview">${_esc(b.description)}</div>
            <button class="mp-btn-insert" type="button"
                    data-std-type="${_esc(b.block_type)}"
                    title="${_esc(b.title)} einfügen">+ Einfügen</button>
        </div>
    `).join('');

    stdHolder.querySelectorAll('.mp-btn-insert[data-std-type]').forEach(btn => {
        btn.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'module_panel', 'click:std-block-insert-secondary', { blockType: btn.dataset.stdType }); // B200
            if (window._editor?.blocks?.insert) {
                window._editor.blocks.insert(btn.dataset.stdType);
                const idx = window._editor.blocks.getBlocksCount() - 1;
                window._editor.caret.setToBlock(idx);
            }
        });
    });
}

/**
 * Rendert Modulliste + Standard-Bloecke in #mp-list (fuer "Alle"-Ansicht).
 * Build 114: Standard-Bloecke werden nach den regulaeren Modulen angezeigt.
 *
 * Bug 2.22 Fix Build 133: Wenn modules leer ist, darf _renderList([]) NICHT
 * aufgerufen werden — _renderList([]) blendet mp-empty ein, obwohl danach
 * noch Standard-Bloecke folgen würden.
 * Beleg: Bugfix Build 133, Projektgespraech 2026-05-09
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

    // mp-empty sicher ausblenden.
    // WICHTIG: _renderList([]) wuerde mp-empty wieder einblenden —
    // deshalb bei leerer Modulliste direkt leeren statt _renderList([]) zu delegieren.
    if (empty) empty.style.display = 'none';

    if (modules.length) {
        // Module rendern via _renderList (setzt mp-empty korrekt auf 'none')
        _renderList(modules);
    } else {
        // Keine Module vorhanden — Liste leeren ohne _renderList([]) aufzurufen,
        // da _renderList([]) mp-empty wieder einblenden wuerde.
        list.innerHTML = '';
    }

    // Standard-Trenner + Standard-Eintraege anhaengen
        _appendStandardBlocks(list, stdBlocks);
}


// ---------------------------------------------------------------------------
// Einfuegen
// ---------------------------------------------------------------------------

/**
 * Fuegt ein Modul als neuen Block in den Bericht ein.
 * Nach dem Einfuegen: Formular-Akkordeon automatisch oeffnen (Phase 6).
 * Beleg: Bauplan B6 v0.5 §4.4.1, Projektgespraech 2026-05-06
 */
/**
 * Fuegt eine VOLLSTAENDIGE Berichtsvorlage ein (Build 389).
 *
 * Der Client sendet NUR den template_key. Der Server laedt die Vorlage,
 * vergibt die UUIDs und legt ALLE Bloecke in EINER Transaktion an
 * (report.py -> insert_template -> evidence_db.save_blocks_bulk).
 *
 * WARUM DER CLIENT DIE BLOECKE NICHT SELBST SCHREIBT:
 *   Der naheliegende Weg waere gewesen, blocks_json abzurufen und N-mal
 *   save_block zu senden. Bricht das bei Block 3 von 7 ab, bliebe ein HALBER
 *   Spurenvermerk stehen — der fuer den Ermittler wie ein vollstaendiger
 *   aussieht. Das ist ein stilles Uebergehen (GRUNDREGEL 1). Deshalb: eine
 *   Anfrage, eine Transaktion, alles oder nichts.
 *
 * BESTAETIGUNG: Anders als ein Modul (ein Block) erzeugt eine Vorlage mehrere
 * Bloecke auf einmal. Ein versehentlicher Klick waere entsprechend laestig
 * rueckgaengig zu machen — deshalb eine Rueckfrage.
 *
 * Beleg: Bauplan Build 389 §4, Projektgespraech 2026-07-12
 */
async function _insertTemplate(templateKey) {
    if (!templateKey) return;

    const lockId = window.lockLayer?.lockId;
    if (!lockId) {
        _showInsertError('Kein aktiver Lock. Bitte Seite neu laden.');
        return;
    }
    if (window.ReportEditor?.isReloading?.()) {
        _dbg('_insertTemplate: Editor-Reload aktiv — Einfuegen zurueckgestellt (150ms)');
        setTimeout(() => _insertTemplate(templateKey), 150);
        return;
    }

    const tpl   = _templates.find(t => t.template_key === templateKey);
    const title = tpl?.title || templateKey;

    if (!window.confirm(
        'Vorlage \u00bb' + title + '\u00ab einf\u00fcgen?\n\n' +
        'Alle Bausteine der Vorlage werden gemeinsam an das Ende des ' +
        'Berichts angeh\u00e4ngt. Pflichtfelder (z.\u202fB. die Spurennummer) ' +
        'm\u00fcssen anschlie\u00dfend im Formular ausgef\u00fcllt werden.'
    )) {
        _dbg('_insertTemplate: vom Benutzer abgebrochen.');
        return;
    }

    const btn = document.querySelector(`.mp-insert-btn[data-template-key="${templateKey}"]`);
    if (btn) { btn.disabled = true; btn.textContent = '\u2026'; }

    try {
        const dl = window.documentLayer;
        if (!dl) throw new Error('documentLayer nicht verf\u00fcgbar');

        const data = await dl._sendRequest({
            action:       'insert_template',
            template_key: templateKey,
        });
        if (data === null) {
            throw new Error('Einf\u00fcgen fehlgeschlagen (kein Lock oder Netzwerkfehler).');
        }

        _dbg('_insertTemplate: Vorlage eingefuegt, block_count=', data.block_count,
             'block_ids=', data.block_ids);

        // Wie bei _insertModule (Build 203): kein blocks.insert() im Client.
        // Der Editor wird im Callback komplett neu geladen, damit Editor-IDs
        // und Server-UUIDs garantiert identisch sind.
        if (_currentOpts.onTemplateInserted) {
            await _currentOpts.onTemplateInserted(
                data.block_ids || [], templateKey, title
            );
        }
    } catch (err) {
        console.error('module_panel.js: _insertTemplate fehlgeschlagen:', err);
        _showInsertError(String(err && err.message ? err.message : err));
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '+ Vorlage einf\u00fcgen'; }
    }
}

async function _insertModule(moduleId) {
    if (!moduleId) return;
    // Paket 9: Lock-Check über LockLayer statt EditorState.
    const _lockId231 = window.lockLayer?.lockId;
    if (!_lockId231) {
        _showInsertError('Kein aktiver Lock. Bitte Seite neu laden.');
        return;
    }

    // Bug 2.104 Fix Build 204: Einfuegen waehrend eines laufenden Editor-Reloads
    // verwerfen. _reloadEditorContent plant bei Bedarf selbst einen Retry.
    // Wird benutzer-seitig als 'kein Block erscheint' wahrgenommen wenn der
    // Doppelklick den onInserted-Callback triggert waehrend _isReloading=true.
    // Beleg: Bugfix Build 204, Projektgespraech 2026-05-17
    if (window.ReportEditor?.isReloading?.()) {
        _dbg('_insertModule: Editor-Reload aktiv — Einfuegen zurueckgestellt (150ms)');
        setTimeout(() => _insertModule(moduleId), 150);
        return;
    }

    const btn = document.querySelector(`.mp-insert-btn[data-module-id="${moduleId}"]`);
    if (btn) { btn.disabled = true; btn.textContent = '\u2026'; }

    try {
        // 1. Modul-Body laden
        const m = await _fetchModuleBody(moduleId);
        if (!m) throw new Error('Modul nicht geladen.');

        // 2. block_data aufbauen.
        //
        // BUILD 655 (Ticket 5d81a0c7): bringt der Baustein eigene Blockdaten
        // mit, werden sie UNVERAENDERT uebernommen - sonst verloere ein
        // Tabellen-Baustein beim Einfuegen seinen Inhalt (derselbe Fehler,
        // den Ticket 3d9016fe fuer den Ziehweg beschreibt). Nur wenn er
        // keine hat, ist es eine Bestandszeile, deren Inhalt in body steht.
        const blockType = m.block_type || 'paragraph';
        const blockData = (m.block_data && typeof m.block_data === 'object')
            ? JSON.stringify(m.block_data)
            : JSON.stringify({ text: m.body || '' });

        // 3. Block speichern (Phase 4 Block-API)
        // Bug 2.114 Fix Build 206: Cursor-Block-ID ermitteln, damit der Server
        // den neuen Block direkt nach dem Cursor-Block einsortiert.
        // _savedCursorRange haelt die zuletzt erfasste Cursor-Position.
        // Beleg: Bugfix Build 206, Projektgespraech 2026-05-17
        let insertAfterBlockId = null;
        if (_savedCursorRange) {
            const container = _savedCursorRange.commonAncestorContainer;
            const el = container.nodeType === Node.ELEMENT_NODE
                ? container
                : container.parentElement;
            const ceBlock = el?.closest?.('.ce-block[data-id]');
            if (ceBlock?.dataset?.id) {
                insertAfterBlockId = ceBlock.dataset.id;
                _dbg('_insertModule: Einfuegen nach Block', insertAfterBlockId);
            }
        }

        const blockId = _generateUUID();
        // Paket 9: Schreiboperation über DocumentLayer. Beleg: Paket 9
        const dl = window.documentLayer;
        if (!dl) throw new Error('documentLayer nicht verfügbar');
        const data = await dl._sendRequest({
            action:               'save_block',
            block_id:             blockId,
            block_type:           blockType,
            block_data:           blockData,
            module_id:            moduleId,
            insert_after_block_id: insertAfterBlockId,
        });
        if (data === null) throw new Error('Block-Save fehlgeschlagen (kein Lock oder Netzwerkfehler)');

        // 4. Kein blocks.insert() mehr — Strategie-Wechsel Build 203.
        //
        //   Problem-Geschichte:
        //     Build 132: blocks.insert(roherText) + execCommand-Hydration (50ms)
        //     Build 155: Template-Syntax statt chipHtml
        //     Build 158: Chip-Hydration per execCommand nach blocks.insert
        //     Build 202: Guard _isProgrammaticInsert — aber execCommand loeste
        //                 nach Guard-Freigabe noch einen block-added-Event aus
        //                 (MutationObserver) → neuer Block mit anderer ID
        //     Build 203: blocks.insert() entfernt. Der onInserted-Callback in
        //                report_editor.js ruft _reloadEditorContent() auf, das
        //                den Editor mit den echten Server-IDs neu initialisiert.
        //
        //   Warum blocks.insert() nicht funktioniert:
        //     blocks.insert() weist dem Block eine neue Editor.js-ID zu (z.B.
        //     'RMW8pkMMux'). Der Block existiert in der DB aber unter seiner
        //     UUID (z.B. 'ac948574-...'). Beide IDs sind nie gleich. Jeder
        //     folgende Auto-Save speichert die Editor.js-ID als neuen Block
        //     und laesst die UUID als Geister-Block in der DB.
        //
        //   Loesung: kein sofortiger visueller Block im Editor. Der Benutzer
        //     sieht den Block nach dem _reloadEditorContent()-Aufruf im
        //     onInserted-Callback (< 500ms, typischerweise < 200ms).
        //     Der Einfuegen-Button bleibt waehrenddessen deaktiviert (see finally).
        //
        // Beleg: Bugfix Build 203, Projektgespraech 2026-05-17 (Bug 2.97/2.107)
        _dbg('_insertModule: Block server-seitig gespeichert, blockId=', blockId,
             '— Editor-Reload via onInserted-Callback');

        // 5. Formular-Akkordeon: wird im onInserted-Callback (report_editor.js)
        // nach _loadBlocksAndReinit geoeffnet, damit _currentBlocks aktuell sind.
        // Bug 2.97/2.107 Fix Build 202: Fruehzeitiges Oeffnen hier verursachte
        // showPlaceholderForm mit blocks=0 (vor Server-Antwort).
        // Beleg: Bugfix Build 202, Projektgespraech 2026-05-17

        // 6. Callback
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
/**
 * Fuegt einen {{a:queryId}}-Platzhalter als Chip inline an der aktuellen
 * Cursorposition im Editor ein.
 *
 * Strategie (Bug 2.21/2.19/2.37 Fix Build 128):
 *   Statt immer einen neuen Block anzulegen, wird der Chip in den aktiven
 *   Editor.js-Block an der Caretposition eingefuegt. Das entspricht dem
 *   erwarteten Verhalten: Chip erscheint sofort im laufenden Text (2.19),
 *   Inline-Einfuegen ist moeglich (2.21), kein verlorener Nachtext mehr (2.37).
 *
 *   Ablauf:
 *   1. Aktives contenteditable-Element im Editor ermitteln.
 *   2. Wenn Cursor in einem Editor-Block steht: Chip-HTML per
 *      document.execCommand('insertHTML') an der Caretposition einsetzen.
 *   3. Editor.js onChange-Callback ausloesen, damit der Block gespeichert wird.
 *   4. Fallback: kein aktiver Cursor → neuer Paragraphen-Block am Ende
 *      (bisheriges Verhalten, damit kein Datenverlust bei Fehler).
 *
 * Beleg: Bugfix Build 128, Projektgespraech 2026-05-09
 *
 * @param {string} queryId  Wert aus placeholder_queries.query_id (z.B. 'user.email')
 */
async function _insertQuery(queryId) {
    if (!queryId) return;
    // Paket 9: Lock-Check über LockLayer. Beleg: Paket 9
    if (!window.lockLayer?.lockId) {
        _showInsertError('Kein aktiver Lock. Bitte Seite neu laden.');
        return;
    }

    const btn = document.querySelector(`.mp-insert-btn[data-query-id="${queryId}"]`);
    if (btn) { btn.disabled = true; btn.textContent = '\u2026'; }

    try {
        // --- Schritt 1: Aktives contenteditable im editorjs-holder ermitteln ---
        // Bug 2.41 Fix Build 136: Zuerst gespeicherte Range pruefen (mousedown-Handler),
        // da der Fokus durch den Button-Klick bereits weg ist wenn click ausloest.
        // Beleg: Bugfix Build 136, Projektgespraech 2026-05-09
        const holder = document.getElementById('editorjs-holder');
        let editorCE = null;

        if (_savedCursorRange) {
            // Range-Container im Editor-Holder suchen
            const container = _savedCursorRange.commonAncestorContainer;
            const el = container.nodeType === Node.ELEMENT_NODE
                ? container
                : container.parentElement;
            const ceBlock = el?.closest('[contenteditable="true"]');
            if (ceBlock && holder?.contains(ceBlock)) {
                editorCE = ceBlock;
            }
        }

        if (!editorCE) {
            // Fallback: activeElement (funktioniert nur wenn Fokus noch im Editor)
            const activeEl = document.activeElement;
            if (
                activeEl &&
                activeEl.isContentEditable &&
                holder?.contains(activeEl)
            ) {
                editorCE = activeEl;
            }
        }

        // Chip-HTML aufbauen (identisch zu PlaceholderChips.hydrateChips-Output)
        // window.PlaceholderChips muss bereits geladen sein.
        // Bug 2.46 Fix Build 137: Zero-Width-Space (\u200B) vor und nach dem Chip
        // als Anker fuer den Cursor. Ohne diese ZWS ist es nicht moeglich, direkt
        // vor oder nach einem Chip zu tippen, da Editor.js keinen Cursor in einen
        // contenteditable=false Span setzen kann.
        // Beleg: Bugfix Build 137, Projektgespraech 2026-05-09
        const ZWS = '\u200B';
        const raw = `{{a:${queryId}}}`;
        let chipHtml;
        if (window.PlaceholderChips?.hydrateChips) {
            chipHtml = ZWS + window.PlaceholderChips.hydrateChips(raw, {}, {}) + ZWS;
        } else {
            chipHtml = `${ZWS}<span class="ph-chip ph-chip-auto" data-chip-raw="${raw}">${queryId}</span>${ZWS}`;
        }

        if (editorCE) {
            // --- Schritt 2: Inline-Einfuegen an Cursorposition ---
            editorCE.focus();
            if (_savedCursorRange) {
                try {
                    const sel = window.getSelection();
                    sel.removeAllRanges();
                    sel.addRange(_savedCursorRange);

                    // Bug 2.61 Fix Build 149: Einfüge-Position loggen.
                    const container = _savedCursorRange.commonAncestorContainer;
                    const el = container.nodeType === Node.ELEMENT_NODE ? container : container.parentElement;
                    const ceBlock = el?.closest('.ce-block[data-id]');
                    _dbg('_insertQuery: Einfuege-Position: blockId=', ceBlock?.dataset?.id,
                        'offset=', _savedCursorRange.startOffset,
                        'queryId=', queryId);

                    // Cursor-Position pruefen: steckt der Anker in einem .ph-chip?
                    const anchorNode = sel.anchorNode;
                    const anchorEl   = anchorNode?.nodeType === Node.ELEMENT_NODE
                        ? anchorNode : anchorNode?.parentElement;
                    const existingChip = anchorEl?.closest('.ph-chip');
                    if (existingChip) {
                        const afterRange = document.createRange();
                        afterRange.setStartAfter(existingChip);
                        afterRange.collapse(true);
                        sel.removeAllRanges();
                        sel.addRange(afterRange);
                        _dbg('_insertQuery: Cursor war in Chip, verschiebe ans Chip-Ende');
                    }
                } catch (_) {}
                _savedCursorRange = null;
            } else {
                _dbg('_insertQuery: _savedCursorRange ist null — kein gespeicherter Cursor vorhanden!');
            }
            const inserted = document.execCommand('insertHTML', false, chipHtml);
            if (!inserted) {
                // execCommand fehlgeschlagen (z.B. readonly) -> Fallback
                _dbg('_insertQuery: execCommand fehlgeschlagen, Fallback auf neuen Block');
                await _insertQueryAsNewBlock(queryId);
                return;
            }

            // --- Schritt 3: onChange in Editor.js ausloesen ---
            // Bug 2.43 Fix Build 145: setTimeout(0) gibt Editor.js Zeit den DOM
            // zu lesen bevor der Auto-Save-Debounce ausgeloest wird. Ohne den
            // Timeout wuerde save() noch den alten Block-Inhalt zurueckgeben.
            // Beleg: Bugfix Build 145, Projektgespraech 2026-05-10
            setTimeout(() => {
                editorCE.dispatchEvent(new Event('input', { bubbles: true }));
            }, 0);

            _dbg('_insertQuery: Chip inline eingefuegt:', queryId);

        } else {
            // --- Schritt 4: Fallback — neuer Block am Ende ---
            // Bug 2.47 Fix Build 137: Auch nach dem Fallback wird der Chip
            // inline in den neuen Block eingefuegt (nicht als raw-Text).
            // Nach _insertQueryAsNewBlock ist der neue Block fokussiert;
            // wir holen sein contenteditable und fuegen den Chip per execCommand ein.
            // Das macht das Verhalten beim ersten Klick identisch zum zweiten.
            // Beleg: Bugfix Build 137, Projektgespraech 2026-05-09
            _dbg('_insertQuery: Kein aktiver Cursor, lege neuen Block an:', queryId);
            await _insertQueryAsNewBlock(queryId);

            // Neuen Block fokussieren und Chip inline einfuegen
            const editor = window._editor;
            if (editor?.blocks && chipHtml) {
                const lastIdx = editor.blocks.getBlocksCount() - 1;
                const editorHolder = document.getElementById('editorjs-holder');
                const ceBlocks = editorHolder?.querySelectorAll(
                    '.ce-block:last-child [contenteditable="true"]'
                );
                const lastCE = ceBlocks?.[ceBlocks.length - 1];
                if (lastCE) {
                    // Leeren Block neu besetzen: raw-Text durch Chip ersetzen
                    lastCE.focus();
                    // Vorhandenen Inhalt (plain-text {{a:...}}) entfernen und
                    // durch hydriertes Chip-HTML ersetzen
                    const sel = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(lastCE);
                    sel.removeAllRanges();
                    sel.addRange(range);
                    document.execCommand('insertHTML', false, chipHtml);
                    lastCE.dispatchEvent(new Event('input', { bubbles: true }));
                    _dbg('_insertQuery: Chip nach Fallback inline ersetzt:', queryId);
                }
            }
        }

    } catch (err) {
        _showInsertError(String(err));
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '+ Einf\u00fcgen'; }
    }
}

/**
 * Fallback: legt einen neuen Paragraphen-Block mit dem Platzhalter am Ende
 * des Berichts an und speichert ihn sofort via POST /_forensic/report.
 * Wird aufgerufen wenn kein Editor-Cursor aktiv ist (Bug 2.21 Fallback).
 *
 * Bug 2.19 Fix Build 132: Block wird nach dem Server-POST sofort per
 * window._editor.blocks.insert() in den Editor eingefuegt, damit er ohne
 * Seiten-Reload sichtbar ist.
 * Beleg: Bugfix Build 132, Projektgespraech 2026-05-09
 * @param {string} queryId
 */
async function _insertQueryAsNewBlock(queryId) {
    const blockData = JSON.stringify({ text: `{{a:${queryId}}}` });
    const blockId   = _generateUUID();
    // Paket 9: Lock-Check und Schreiboperation über Layer. Beleg: Paket 9
    const dl = window.documentLayer;
    if (!dl || !window.lockLayer?.lockId) throw new Error('Kein aktiver Lock oder documentLayer fehlt');
    const data = await dl._sendRequest({
        action:     'save_block',
        block_id:   blockId,
        block_type: 'paragraph',
        block_data: blockData,
    });
    if (data === null) throw new Error('Block-Save fehlgeschlagen');

    // Block sofort in den Editor einfuegen (kein Seiten-Reload noetig).
    // Chip-HTML aufbauen damit der Platzhalter sofort als Chip dargestellt wird.
    const editor = window._editor;
    if (editor?.blocks) {
        const raw = `{{a:${queryId}}}`;
        let chipHtml;
        if (window.PlaceholderChips?.hydrateChips) {
            chipHtml = window.PlaceholderChips.hydrateChips(raw, {}, {});
        } else {
            chipHtml = `<span class="ph-chip ph-chip-auto" data-chip-raw="${raw}">${queryId}</span>`;
        }
        editor.blocks.insert('paragraph', { text: chipHtml }, {}, undefined, true);
        const lastIdx = editor.blocks.getBlocksCount() - 1;
        editor.caret.setToBlock(lastIdx);
        _dbg('_insertQueryAsNewBlock: Block sofort in Editor eingefuegt, idx=', lastIdx);
    } else {
        _dbg('_insertQueryAsNewBlock: Editor nicht verfuegbar, Fallback auf Server-Reload');
    }

    if (_currentOpts.onInserted) {
        await _currentOpts.onInserted(blockId, null, `{{a:${queryId}}}`);
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
    // Build 389: Vorlagen (vollstaendige Berichtsgerueste)
    _renderTemplateList,
    _fetchTemplates,
    _insertTemplate,
    _setTemplatesForTest: (t) => { _templates = Array.isArray(t) ? t : []; },
    _setActiveCategoryForTest: (c) => { _activeCategory = c; },
    // Rueckwaerts-Kompatibilitaet
    open,
    close,
    // Interna
    _fetchModules,
    _fetchModuleBody,
    // Build 581: pruefbar gemacht - der Aufbau der Standard-Bloecke wird
    // seither an zwei Stellen gebraucht (Normal- und Fehlerfall).
    _fetchQueries,
    _fehlerAusAntwort,
    _appendStandardBlocks,
    STANDARD_BLOCKS,
    // Bug 2.57/2.64: Setter fuer Cursor-Range und Drop-Flag
    // Bug 2.120 Fix Build 231: lockId nach Bericht-Wechsel aktualisieren
    _refreshLockId: (lockId) => { _currentOpts.lockId = lockId || null; },
    _setSavedCursorRange: (range) => { _savedCursorRange = range; },
    _getSavedRangeInfo: () => {
        if (!_savedCursorRange) return 'null';
        const el = _savedCursorRange.commonAncestorContainer;
        const ceBlock = (el.nodeType === Node.ELEMENT_NODE ? el : el.parentElement)
            ?.closest?.('.ce-block[data-id]');
        return `blockId=${ceBlock?.dataset?.id || '?'} offset=${_savedCursorRange.startOffset}`;
    },
    // Bug 2.64 Fix Build 155: Drop-Flag damit click nach Drop ignoriert wird.
    _setJustDropped: (val) => { _justDropped = val; },
};

// Alias fuer report_editor.js (window._ModulePanel)
window._ModulePanel = window.ModulePanel;

// Alias: var ModulePanel (fuer Tests ohne window-Prafix)
var ModulePanel = window.ModulePanel;

})();
