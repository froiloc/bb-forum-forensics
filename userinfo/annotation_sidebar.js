/**
 * userinfo/annotation_sidebar.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Annotationsseitenleiste fuer Fenster 3 (Phase 7, Bauplan B6 v0.3 §4.7).
 *
 *   Zeigt alle Annotationen aus evidence_<uid>.db. Dient dazu, beim Schreiben
 *   von Paragraphen gezielt Annotationen zu finden und als Beweisanker
 *   (report_anchors) einzufuegen.
 *
 *   Verhalten (§4.7):
 *     - Kategorien standardmaessig kollabiert (nur Bezeichnung + Anzahl)
 *     - Klick auf Kategorie-Zeile klappt auf
 *     - Vier Informationszeilen je Annotation: Tags, Kurztext, Notiz, Originaltext
 *     - Suche filtert sofort ueber Tags, Notiztext und Originaltext
 *     - Filter "bereits verankerte ausblenden"
 *     - "Als Beleg einfuegen": haengt [BELEG:annotation_id=X] an Cursor-Position,
 *       POST action=add_anchor an /_forensic/report
 *     - Vollstaendigkeitsanzeige: "X von Y Annotationen verankert"
 *
 *   Abhaengigkeiten:
 *     Keine (standalone, keine anderen window.*-Module benoetigt)
 *
 * Exports:
 *   window.AnnotationSidebar.init(options)
 *     Initialisiert die Seitenleiste.
 *     options: {
 *       containerId: string,       -- ID des #report-annotation-sidebar Elements
 *       postFn:      async fn,     -- _postWithLock aus report.js
 *       getActiveParagraph: fn,    -- gibt aktuell fokussiertes block_id zurueck
 *       onAnchorAdded: fn,         -- Callback nach erfolgreichem Anker
 *     }
 *   window.AnnotationSidebar.reload()
 *     Laedt Annotationen neu (nach SSE-Event).
 *   window.AnnotationSidebar.updateAnchored(anchoredIds)
 *     Aktualisiert die Menge der bereits verankerten Annotation-IDs.
 *
 * API-Endpunkte:
 *   GET /_forensic/annotations         -- alle Annotationen
 *   POST /_forensic/report             -- action=add_anchor
 *
 * Version: v0.1.0 · Build: 094 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §4.7, Ausdefinitionsgespraech 2026-05-05
 */

'use strict';

// ---------------------------------------------------------------------------
// Konstanten
// ---------------------------------------------------------------------------

const ANN_API = '/_forensic/annotations';

/** Deutsche Bezeichnungen fuer die Kategorie-Codes. */
const CATEGORY_LABELS = {
    CAT_PERSON:   'Person',
    CAT_LOCATION: 'Ort',
    CAT_176:      '\u00a7\u00a7 176/176a StGB',
    CAT_184:      '\u00a7\u00a7 184b/184c StGB',
    CAT_VICTIM:   'Betroffene Person',
    CAT_OTHER:    'Sonstiges',
};

/** Reihenfolge der Kategorien in der Anzeige. */
const CATEGORY_ORDER = [
    'CAT_PERSON', 'CAT_VICTIM', 'CAT_176', 'CAT_184', 'CAT_LOCATION', 'CAT_OTHER',
];

// ---------------------------------------------------------------------------
// HTML-Escape
// ---------------------------------------------------------------------------

function _esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** Kuerzt langen Text auf maxLen Zeichen mit Ellipse. */
function _truncate(s, maxLen) {
    if (!s) return '';
    s = String(s);
    return s.length > maxLen ? s.slice(0, maxLen) + '\u2026' : s;
}

// ---------------------------------------------------------------------------
// Modul-Zustand
// ---------------------------------------------------------------------------

let _opts          = null;
let _annotations   = [];        // alle geladenen Annotations-Objekte
let _anchoredIds   = new Set(); // bereits verankerte Annotation-IDs
let _expanded      = new Set(); // aufgeklappte Kategorien
let _searchText    = '';
let _hideAnchored  = false;
let _searchTimer   = null;

// ---------------------------------------------------------------------------
// Laden
// ---------------------------------------------------------------------------

async function _loadAnnotations() {
    try {
        const resp = await fetch(ANN_API, {
            headers: { 'X-Forensic-Request': 'ajax' },
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        _annotations = data.annotations || [];
    } catch (err) {
        _annotations = [];
        _showError('Annotationen konnten nicht geladen werden: ' + String(err));
    }
    _render();
}

// ---------------------------------------------------------------------------
// Filter-Logik
// ---------------------------------------------------------------------------

/**
 * Gibt true zurueck wenn eine Annotation zum aktuellen Suchtext passt.
 * Durchsucht Tags, Notiztext und Originaltext (selection.text).
 * Beleg: Bauplan B6 v0.3 §4.7
 */
function _matchesSearch(ann, lower) {
    if (!lower) return true;
    const tags    = (ann.tags || []).join(' ').toLowerCase();
    const text    = (ann.text || '').toLowerCase();
    const selText = (ann.selection?.text || '').toLowerCase();
    return tags.includes(lower) || text.includes(lower) || selText.includes(lower);
}

/**
 * Gibt gefilterte Annotationen zurueck (Suche + Verankert-Filter).
 * Gibt auch ein Map {category -> [annotations]} zurueck.
 */
function _filterAndGroup() {
    const lower = _searchText.toLowerCase();
    const result = {};

    for (const ann of _annotations) {
        if (_hideAnchored && _anchoredIds.has(ann.id)) continue;
        if (!_matchesSearch(ann, lower)) continue;
        const cat = ann.category || 'CAT_OTHER';
        if (!result[cat]) result[cat] = [];
        result[cat].push(ann);
    }
    return result;
}

// ---------------------------------------------------------------------------
// Rendern
// ---------------------------------------------------------------------------

function _render() {
    const container = _opts?.containerId
        ? document.getElementById(_opts.containerId)
        : null;
    if (!container) return;

    const grouped = _filterAndGroup();
    const total   = _annotations.length;
    const anchored = _annotations.filter(a => _anchoredIds.has(a.id)).length;

    container.innerHTML = `
        <div class="as-panel">
            <div class="as-toolbar">
                <div class="as-search-wrap">
                    <span class="as-search-icon" aria-hidden="true">\ud83d\udd0d</span>
                    <input class="as-search-input" id="as-search-input"
                           type="search"
                           placeholder="Suche in Annotationen\u2026"
                           value="${_esc(_searchText)}"
                           autocomplete="off">
                </div>
                <label class="as-filter-label">
                    <input type="checkbox" id="as-hide-anchored"
                        ${_hideAnchored ? 'checked' : ''}>
                    Bereits verankerte ausblenden
                </label>
            </div>
            <div class="as-divider"></div>
            <div class="as-list" id="as-list">
                ${_renderCategories(grouped)}
            </div>
            <div class="as-divider"></div>
            ${_renderCompleteness(anchored, total)}
        </div>`;

    _bindEvents(container);
}

function _renderCategories(grouped) {
    // Alle Kategorien in definierter Reihenfolge, dann unbekannte
    const cats = [
        ...CATEGORY_ORDER.filter(c => grouped[c]?.length),
        ...Object.keys(grouped).filter(c => !CATEGORY_ORDER.includes(c) && grouped[c]?.length),
    ];

    if (!cats.length) {
        return '<div class="as-empty">Keine Annotationen gefunden.</div>';
    }

    return cats.map(cat => {
        const items    = grouped[cat];
        const label    = CATEGORY_LABELS[cat] || _esc(cat);
        const isOpen   = _expanded.has(cat);
        const count    = items.length;
        const chevron  = isOpen ? '\u25bc' : '\u25b6';

        return `
            <div class="as-category" data-category="${_esc(cat)}">
                <button class="as-category-header" data-category="${_esc(cat)}"
                    aria-expanded="${isOpen ? 'true' : 'false'}">
                    <span class="as-chevron" aria-hidden="true">${chevron}</span>
                    <span class="as-category-label">${_esc(label)}</span>
                    <span class="as-category-count">(${count})</span>
                </button>
                ${isOpen ? `<div class="as-category-body">
                    ${items.map(a => _renderAnnotation(a)).join('')}
                </div>` : ''}
            </div>`;
    }).join('');
}

function _renderAnnotation(ann) {
    const isAnchored = _anchoredIds.has(ann.id);
    const tags       = (ann.tags || []).map(t =>
        `<span class="as-tag">${_esc(t)}</span>`
    ).join('');
    const noteText   = _truncate(ann.text, 120);
    const origText   = _truncate(ann.selection?.text, 120);
    const anchoredCls = isAnchored ? ' as-ann-anchored' : '';

    return `
        <div class="as-annotation${anchoredCls}" data-ann-id="${ann.id}">
            ${isAnchored
                ? '<span class="as-anchored-badge" title="Bereits verankert">\ud83d\udccc verankert</span>'
                : ''}
            ${tags ? `<div class="as-ann-tags">${tags}</div>` : ''}
            ${noteText
                ? `<div class="as-ann-text">${_esc(noteText)}</div>`
                : ''}
            ${origText
                ? `<div class="as-ann-orig">\u201e${_esc(origText)}\u201c</div>`
                : ''}
            <div class="as-ann-meta">
                <span class="as-ann-id">ID: ${ann.id}</span>
                ${ann.createdBy ? `<span>\u2022 ${_esc(ann.createdBy)}</span>` : ''}
            </div>
            <div class="as-ann-actions">
                <button class="as-btn as-btn-anchor"
                    data-ann-id="${ann.id}"
                    title="Beweisanker in aktiven Absatz einf\u00fcgen"
                    ${isAnchored ? 'disabled' : ''}>
                    \ud83d\udccc Als Beleg einf\u00fcgen
                </button>
            </div>
        </div>`;
}

function _renderCompleteness(anchored, total) {
    if (total === 0) {
        return '<div class="as-completeness as-completeness-neutral">Keine Annotationen vorhanden.</div>';
    }
    const cls = anchored === total ? 'as-completeness-ok' : 'as-completeness-warn';
    return `<div class="as-completeness ${cls}">
        ${anchored} von ${total} Annotation${total !== 1 ? 'en' : ''} verankert.
    </div>`;
}

function _showError(msg) {
    const list = document.getElementById('as-list');
    if (list) {
        list.innerHTML = `<div class="as-error">${_esc(msg)}</div>`;
    }
}

// ---------------------------------------------------------------------------
// Event-Binding
// ---------------------------------------------------------------------------

function _bindEvents(container) {
    // Suche
    const searchInput = container.querySelector('#as-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', e => {
            clearTimeout(_searchTimer);
            _searchText = e.target.value;
            _searchTimer = setTimeout(_render, 200);
        });
    }

    // Verankert-Filter
    const hideChk = container.querySelector('#as-hide-anchored');
    if (hideChk) {
        hideChk.addEventListener('change', e => {
            _hideAnchored = e.target.checked;
            _render();
        });
    }

    // Kategorie-Zeilen aufklappen/zuklappen
    container.querySelectorAll('.as-category-header').forEach(btn => {
        btn.addEventListener('click', () => {
            const cat = btn.dataset.category;
            if (_expanded.has(cat)) {
                _expanded.delete(cat);
            } else {
                _expanded.add(cat);
            }
            _render();
        });
    });

    // "Als Beleg einfuegen"-Buttons
    container.querySelectorAll('.as-btn-anchor').forEach(btn => {
        btn.addEventListener('click', () => {
            const annId = parseInt(btn.dataset.annId, 10);
            _insertAnchor(annId);
        });
    });
}

// ---------------------------------------------------------------------------
// Beweisanker einfuegen
// ---------------------------------------------------------------------------

/**
 * Fuegt einen Beweisanker fuer die Annotation ein.
 *
 * Ablauf:
 * 1. Aktiven Paragraph-Block per _opts.getActiveParagraph() ermitteln
 * 2. POST action=add_anchor mit block_id und annotation_id
 * 3. [BELEG:annotation_id=X] an Cursor-Position im contenteditable einfuegen
 * 4. _anchoredIds aktualisieren, Seitenleiste neu rendern
 * Beleg: Bauplan B6 v0.3 §4.7
 */
async function _insertAnchor(annId) {
    const blockId = _opts?.getActiveParagraph?.();
    if (!blockId) {
        _showInsertError('Bitte zuerst einen Absatz zum Bearbeiten ausw\u00e4hlen.');
        return;
    }

    // Anker-Text aus Annotation-Daten aufbauen
    const ann = _annotations.find(a => a.id === annId);
    const anchorText = ann
        ? `[BELEG:annotation_id=${annId}]`
        : `[BELEG:annotation_id=${annId}]`;

    // Visuelles Feedback: Button deaktivieren
    const btn = document.querySelector(`.as-btn-anchor[data-ann-id="${annId}"]`);
    if (btn) { btn.disabled = true; btn.textContent = 'Wird eingetragen\u2026'; }

    try {
        const result = await _opts.postFn({
            action:        'add_anchor',
            block_id:      blockId,
            annotation_id: annId,
            anchor_text:   anchorText,
        });
        if (!result) throw new Error('Keine Serverantwort');

        // [BELEG:...] an Cursor-Position im aktiven contenteditable einfuegen
        _insertTextAtCursor(anchorText);

        // Zustand aktualisieren
        _anchoredIds.add(annId);
        _render();

        _opts?.onAnchorAdded?.(annId, blockId);

    } catch (err) {
        if (btn) { btn.disabled = false; btn.textContent = '\ud83d\udccc Als Beleg einf\u00fcgen'; }
        _showInsertError('Beweisanker konnte nicht eingetragen werden: ' + String(err));
    }
}

/**
 * Fuegt Text an der aktuellen Cursor-Position im aktiven contenteditable ein.
 * Fallback: Text wird an das Ende des Elements angehaengt.
 * Beleg: Bauplan B6 v0.3 §4.7
 */
function _insertTextAtCursor(text) {
    const sel = window.getSelection?.();
    if (sel && sel.rangeCount > 0) {
        const range    = sel.getRangeAt(0);
        const ancestor = range.commonAncestorContainer;
        // Sicherstellen, dass wir in einem report-paragraph-content sind
        const el = ancestor.nodeType === Node.TEXT_NODE
            ? ancestor.parentElement
            : ancestor;
        if (el?.closest?.('.report-paragraph-content')) {
            range.deleteContents();
            range.insertNode(document.createTextNode(text));
            range.collapse(false);
            sel.removeAllRanges();
            sel.addRange(range);
            return;
        }
    }
    // Fallback: aktives Element per getActiveParagraph suchen
    const blockId = _opts?.getActiveParagraph?.();
    if (blockId) {
        const contentEl = document.querySelector(
            `.report-paragraph-content[data-block-id="${blockId}"]`
        );
        if (contentEl) {
            contentEl.textContent += ' ' + text;
        }
    }
}

function _showInsertError(msg) {
    // Kurze Fehlermeldung in der Seitenleiste
    const existing = document.getElementById('as-insert-error');
    if (existing) existing.remove();

    const errEl = document.createElement('div');
    errEl.id = 'as-insert-error';
    errEl.className = 'as-error';
    errEl.textContent = msg;

    const panel = document.querySelector('.as-panel');
    if (panel) panel.prepend(errEl);
    setTimeout(() => errEl.remove(), 5000);
}

// ---------------------------------------------------------------------------
// Oeffentliche API
// ---------------------------------------------------------------------------

/**
 * Initialisiert die Annotationsseitenleiste.
 * Beleg: Bauplan B6 v0.3 §4.7
 *
 * @param {Object} options
 *   containerId:         string   -- ID des Sidebar-Elements
 *   postFn:              function -- _postWithLock aus report.js
 *   getActiveParagraph:  function -- gibt aktuell fokussiertes block_id zurueck
 *   onAnchorAdded:       function -- Callback nach erfolgreichem Anker
 */
function init(options) {
    _opts         = options;
    _annotations  = [];
    _anchoredIds  = new Set();
    _expanded     = new Set();
    _searchText   = '';
    _hideAnchored = false;
    _loadAnnotations();
}

/**
 * Laedt Annotationen neu und rendert die Seitenleiste.
 * Wird nach SSE-Events (annotation_created, annotation_deleted) aufgerufen.
 */
function reload() {
    _loadAnnotations();
}

/**
 * Aktualisiert die Menge der bereits verankerten Annotation-IDs.
 * Wird von report.js nach loadReport() aufgerufen.
 *
 * @param {Iterable<number>} anchoredIds
 */
function updateAnchored(anchoredIds) {
    _anchoredIds = new Set(anchoredIds);
    _render();
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

window.AnnotationSidebar = {
    init,
    reload,
    updateAnchored,
    // Test-Hook: setzt internen Zustand fuer Unit-Tests.
    // Beleg: Build 094, Testbarkeitsanforderung.
    _testSetState: function(annotations, anchoredIds, searchText, hideAnchored) {
        _annotations  = annotations;
        _anchoredIds  = anchoredIds instanceof Set ? anchoredIds : new Set(anchoredIds);
        _searchText   = searchText;
        _hideAnchored = hideAnchored;
    },
    // Interna fuer Tests
    _filterAndGroup,
    _matchesSearch,
    _renderAnnotation,
};
