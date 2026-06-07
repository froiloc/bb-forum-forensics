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
 * Version: v0.6.275 · Build: 275 · 2026-06-07
 * Beleg: Bauplan B6 v0.3 §4.7, Ausdefinitionsgespraech 2026-05-05
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

const ANN_API = '/_forensic/annotations';

/** Deutsche Bezeichnungen fuer die Kategorie-Codes. */
/** Deutsche Bezeichnungen + Icons fuer die Kategorie-Codes.
 * Build 112: Icons ergaenzt.
 * Beleg: Projektgespraech 2026-05-07
 */
/** Anzeigelabels: icon + Kurzform (wie forensic-cat-btn in toolbar.css).
 * Build 115: Angleichung an Toolbar-Stil.
 * Beleg: Projektgespraech 2026-05-07
 */
const CATEGORY_LABELS = {
    CAT_PERSON:   'PER',
    CAT_LOCATION: 'LOC',
    CAT_176:      '176',
    CAT_184:      '184',
    CAT_VICTIM:   'OPF',
    CAT_OTHER:    'SON',
};

/** Bug 1.1 Fix Build 148: Icons identisch zur Toolbar (toolbar.js Zeilen 342-347).
 * Beleg: Bugfix Build 148, Projektgespraech 2026-05-10
 */
const CATEGORY_ICONS = {
    CAT_PERSON:   '👤',
    CAT_LOCATION: '📍',
    CAT_176:      '⚖️',
    CAT_184:      '🔴',
    CAT_VICTIM:   '🛡️',
    CAT_OTHER:    '📎',
};

/** Volle Beschriftung fuer Title- und ARIA-Texte. */
const CATEGORY_TITLES = {
    CAT_PERSON:   '\ud83d\udc64 PER \u2013 Pers\u00f6nliche Identifikationsmerkmale',
    CAT_LOCATION: '\ud83d\udccd LOC \u2013 Ortsangaben, geografische Hinweise',
    CAT_176:      '\u2696\ufe0f 176 \u2013 Relevanz \u00a7\u00a7 176, 176a StGB',
    CAT_184:      '\ud83d\udd34 184 \u2013 Relevanz \u00a7\u00a7 184b, 184c StGB',
    CAT_VICTIM:   '\ud83d\udee1\ufe0f OPF \u2013 Hinweise auf m\u00f6gliche Opfer',
    CAT_OTHER:    '\ud83d\udcce SON \u2013 Sonstige Ermittlungsrelevanz',
};

/** Reihenfolge der Kategorien in der Anzeige.
 * Bug 1.2 Fix Build 148: Reihenfolge entspricht jetzt der Toolbar:
 * PER, LOC, 176, 184, OPF, SON.
 * Beleg: Bugfix Build 148, Projektgespraech 2026-05-10
 */
const CATEGORY_ORDER = [
    'CAT_PERSON', 'CAT_LOCATION', 'CAT_176', 'CAT_184', 'CAT_VICTIM', 'CAT_OTHER',
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
let _expanded      = new Set(); // aufgeklappte Kategorien (Legacy, nicht mehr genutzt)
let _activeTab     = null;      // Build 114: aktiver Kategorie-Tab (null = Alle)
let _searchText        = '';
let _hideAnchored      = false;
// Bug 2.22 Fix Build 275:
// Die anderen Ausblenden-Checkboxen hatten keinen Modul-State.
// Beim Re-Render nach Aenderung einer Checkbox wurden alle anderen
// ohne 'checked'-Attribut gerendert und erschienen damit demarkiert.
// Jetzt wird der Zustand jeder Checkbox im Modul-State gehalten und
// beim Rendern eingespielt.
// Beleg: Bugfix-Liste 2.22, Projektgespraech 2026-06-07
let _hideTags          = false;
let _hideInvestigator  = false;
let _hideQuotes        = false;
let _hideSource        = false;
let _hideNotes         = false;
let _searchTimer       = null;

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

    // Bug 2.21 Fix Build 275:
    // container.innerHTML ersetzt den gesamten DOM. Das #as-list-Element
    // wird dabei zerstoert und neu erzeugt — sein scrollTop geht verloren.
    // Wir lesen scrollTop vor dem Re-Render und schreiben ihn danach zurueck.
    // Beleg: Bugfix-Liste 2.21, Projektgespraech 2026-06-07
    const listEl = container.querySelector('#as-list');
    const savedScrollTop = listEl ? listEl.scrollTop : 0;

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
                <!-- Bug 2.2 Fix Build 158: Toggle-Schalter statt einzelner Checkbox.
                     CSS-gesteuert ueber :has()-Selektoren; kein JS-Loeschen.
                     Beleg: Projektgespraech 2026-05-11 -->
                <div class="as-filter-toggles" role="group" aria-label="Ausblenden-Filter">
                    <span class="as-filter-label-prefix">Ausblenden:</span>
                    <label class="as-toggle-label" title="Bereits verankerte Annotationen ausblenden">
                        <input type="checkbox" id="as-hide-anchored"
                            ${_hideAnchored ? 'checked' : ''}>
                        Verankerte
                    </label>
                    <label class="as-toggle-label" title="Tags ausblenden">
                        <input type="checkbox" id="as-hide-tags"
                            ${_hideTags ? 'checked' : ''}>
                        Tags
                    </label>
                    <label class="as-toggle-label" title="Ermittler-Namen ausblenden">
                        <input type="checkbox" id="as-hide-investigator"
                            ${_hideInvestigator ? 'checked' : ''}>
                        Ermittler
                    </label>
                    <label class="as-toggle-label" title="Zitate (Originaltext) ausblenden">
                        <input type="checkbox" id="as-hide-quotes"
                            ${_hideQuotes ? 'checked' : ''}>
                        Zitate
                    </label>
                    <label class="as-toggle-label" title="Quellenangaben ausblenden">
                        <input type="checkbox" id="as-hide-source"
                            ${_hideSource ? 'checked' : ''}>
                        Quelle
                    </label>
                    <label class="as-toggle-label" title="Notizen ausblenden">
                        <input type="checkbox" id="as-hide-notes"
                            ${_hideNotes ? 'checked' : ''}>
                        Notizen
                    </label>
                </div>
            </div>
            <div class="as-divider"></div>
            ${_renderCategoryTabs(grouped)}
            <div class="as-list" id="as-list">
                ${_renderFilteredAnnotations(grouped)}
            </div>
            <div class="as-divider"></div>
            ${_renderCompleteness(anchored, total)}
        </div>`;

    _bindEvents(container);

    // Bug 2.21 Fix Build 275: Scrollposition wiederherstellen.
    // Das neue #as-list-Element existiert jetzt im DOM.
    const newListEl = container.querySelector('#as-list');
    if (newListEl && savedScrollTop > 0) {
        newListEl.scrollTop = savedScrollTop;
    }
}

function _renderCategoryTabs(grouped) {
    // Build 115: Toolbar-Stil (forensic-cat-btn), alle Kategorien permanent
    // Beschriftung, Icons, ARIA identisch mit toolbar.js/toolbar.css
    // Beleg: Projektgespraech 2026-05-07
    const allCount = Object.values(grouped).reduce((s, a) => s + a.length, 0);

    const allTabs = [
        { key: null, label: 'Alle', icon: null, title: 'Alle Kategorien' },
        ...CATEGORY_ORDER.map(c => ({
            key:   c,
            label: CATEGORY_LABELS[c] || c,
            icon:  CATEGORY_ICONS[c]  || null,
            title: CATEGORY_TITLES[c] || c,
        })),
    ];

    return `<div class="as-tabs" role="tablist" aria-label="Annotationskategorien">
        ${allTabs.map(t => {
            const count    = t.key ? (grouped[t.key] || []).length : allCount;
            const isActive = t.key === _activeTab;
            const isEmpty  = count === 0 && t.key !== null;
            const cls = [
                'as-tab',
                isActive ? 'as-tab--active' : '',
                isEmpty  ? 'as-tab--empty'  : '',
            ].filter(Boolean).join(' ');
            const catAttr  = t.key ? `data-cat="${_esc(t.key)}"` : `data-cat=""`;
            // Bug 1.1 Fix Build 148: Icon vor Label anzeigen wenn vorhanden.
            // Anzahl bleibt erhalten (as-tab-count). Identisch mit Toolbar-Darstellung.
            const iconHtml = t.icon
                ? `<span class="as-tab-icon" aria-hidden="true">${_esc(t.icon)}</span>`
                : '';
            return `<button class="${cls}" role="tab"
                        aria-selected="${isActive}"
                        ${catAttr}
                        title="${_esc(t.title)}"
                        aria-label="${_esc(t.title)}"
                    >${iconHtml}<span class="as-tab-label">${_esc(t.label)}</span><span class="as-tab-count">${count}</span></button>`;
        }).join('')}
    </div>`;
}


function _renderFilteredAnnotations(grouped) {
    // Build 114: nur aktive Kategorie anzeigen (oder alle)
    const cats = _activeTab
        ? (_activeTab in grouped ? [_activeTab] : [])
        : [
            ...CATEGORY_ORDER.filter(c => grouped[c]?.length),
            ...Object.keys(grouped).filter(c => !CATEGORY_ORDER.includes(c) && grouped[c]?.length),
          ];

    if (!cats.length) {
        return '<div class="as-empty">Keine Annotationen gefunden.</div>';
    }

    return cats.map(cat => {
        const items = grouped[cat];
        const label = CATEGORY_LABELS[cat] || _esc(cat);
        return `<div class="as-category-section">
            ${_activeTab === null ? `<div class="as-category-title">${_esc(label)}</div>` : ''}
            ${items.map(a => _renderAnnotation(a)).join('')}
        </div>`;
    }).join('');
}


function _renderAnnotation(ann) {
    const isAnchored  = _anchoredIds.has(ann.id);
    const anchoredCls = isAnchored ? ' as-ann-anchored' : '';

    // Bug 2.1 Fix Build 158: alle verfuegbaren Felder rendern.
    // Tags, markierter Text (max. 200 Zeichen), Notiz, Quelle mit Verweis,
    // Datum+Zeit, Ermittler. Eigene Klassen fuer CSS-Toggle-Steuerung (Bug 2.2).
    // Beleg: Projektgespraech 2026-05-11

    // Tags
    const tags = (ann.tags || []).map(t =>
        `<span class="as-tag">${_esc(t)}</span>`
    ).join('');

    // Notiz (text): bis 120 Zeichen — Klasse as-ann-text (wie bisher)
    const noteText = _truncate(ann.text, 120);

    // Originaltext / Zitat: bis 200 Zeichen (Bug 2.1: bisher 120)
    const origText = _truncate(ann.selection?.text, 200);

    // Quelle: pageUrl + Anker-Element
    const pageUrl   = ann.pageUrl || '';
    const elementId = ann.elementId || '';
    const sourceHref = elementId ? `${_esc(pageUrl)}#${_esc(elementId)}` : _esc(pageUrl);
    const sourceLabel = pageUrl
        ? _truncate(pageUrl.replace(/^https?:\/\/[^/]+/, ''), 60) || pageUrl
        : '';

    // Datum + Zeit aus createdAt (Millisekunden-Timestamp)
    let dateStr = '';
    if (ann.createdAt) {
        try {
            dateStr = new Date(ann.createdAt).toLocaleString('de-DE', {
                day:    '2-digit',
                month:  '2-digit',
                year:   'numeric',
                hour:   '2-digit',
                minute: '2-digit',
            });
        } catch (_) { /* ignorieren */ }
    }

    // Ermittler-Name
    const investigator = ann.createdBy || '';

    return `
        <div class="as-annotation${anchoredCls}" data-ann-id="${ann.id}"
             draggable="true"
             title="Ziehen um als EvidenceBlock einzuf\u00fcgen">
            ${isAnchored
                ? '<span class="as-anchored-badge" title="Bereits verankert">\ud83d\udccc verankert</span>'
                : ''}
            ${tags
                ? `<div class="as-ann-tags">${tags}</div>`
                : ''}
            ${noteText
                ? `<div class="as-ann-notes">${_esc(noteText)}</div>`
                : ''}
            ${origText
                ? `<div class="as-ann-quote">\u201e${_esc(origText)}\u201c</div>`
                : ''}
            ${sourceLabel
                ? `<div class="as-ann-source">
                       <a class="as-ann-source-link"
                          href="${sourceHref}"
                          title="${_esc(pageUrl)}"
                          target="_blank"
                          rel="noopener">\ud83d\udd17 ${_esc(sourceLabel)}</a>
                   </div>`
                : ''}
            <div class="as-ann-meta">
                <span class="as-ann-id">ID\u00a0${ann.id}</span>
                ${dateStr
                    ? `<span class="as-ann-date" title="Erstellt am ${_esc(dateStr)}">\ud83d\uddd3\u00a0${_esc(dateStr)}</span>`
                    : ''}
                ${investigator
                    ? `<span class="as-ann-investigator" title="Ermittler: ${_esc(investigator)}">\ud83d\udc64\u00a0${_esc(investigator)}</span>`
                    : ''}
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
    // Build 114: Kategorie-Tab-Clicks
    container.querySelectorAll('.as-tab').forEach(tab => {
        tab.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'annotation_sidebar', 'click:as-tab', { cat: tab.dataset.cat }); // B200
            _activeTab = tab.dataset.cat || null;
            _render();
        });
    });

    // Suche
    const searchInput = container.querySelector('#as-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', e => {
            window._uevt?.(e, 'annotation_sidebar', 'input:as-search', { value: e.target.value }); // B200
            clearTimeout(_searchTimer);
            _searchText = e.target.value;
            // Bug 2.20 Fix Build 274:
            // 200 ms war zu kurz — _render() baut das DOM komplett neu auf
            // (innerHTML-Zuweisung), dadurch wird das #as-search-input-Element
            // zerstoert und neu erzeugt. Der Browser verliert dadurch
            // unweigerlich den Fokus, noch bevor der Nutzer fertig tippt.
            // Massnahmen:
            //   1. Debounce auf 400 ms erhoehen, damit schnelles Tippen
            //      selten einen Render ausloest.
            //   2. Nach dem Render Fokus und Cursor-Position wiederherstellen,
            //      damit der Nutzer nahtlos weitertippen kann.
            // Beleg: Bugfix-Liste 2.20, Projektgespraech 2026-06-07
            const selStart = e.target.selectionStart;
            const selEnd   = e.target.selectionEnd;
            _searchTimer = setTimeout(() => {
                _render();
                // Fokus und Cursor-Position im neu gerenderten Input wiederherstellen.
                // Das neue #as-search-input liegt im selben container.
                const newInput = container.querySelector('#as-search-input');
                if (newInput) {
                    newInput.focus();
                    // setSelectionRange ist nur auf text/search-Inputs verfuegbar.
                    try {
                        newInput.setSelectionRange(selStart, selEnd);
                    } catch (_) { /* ignorieren falls Input-Typ nicht unterstuetzt */ }
                }
            }, 400);
        });
    }

    // Verankert-Filter
    const hideChk = container.querySelector('#as-hide-anchored');
    if (hideChk) {
        hideChk.addEventListener('change', e => {
            window._uevt?.(e, 'annotation_sidebar', 'change:as-hide-anchored', { checked: e.target.checked }); // B200
            _hideAnchored = e.target.checked;
            _render();
        });
    }

    // Bug 2.22 Fix Build 275:
    // Alle weiteren Ausblenden-Checkboxen haben jetzt State-Variablen im
    // Modul-Scope und dedizierte Change-Handler. Damit werden ihre
    // Zustände beim Re-Render korrekt wiederhergestellt.
    // Beleg: Bugfix-Liste 2.22, Projektgespraech 2026-06-07
    const hideTagsChk = container.querySelector('#as-hide-tags');
    if (hideTagsChk) {
        hideTagsChk.addEventListener('change', e => {
            _hideTags = e.target.checked;
            _render();
        });
    }

    const hideInvestigatorChk = container.querySelector('#as-hide-investigator');
    if (hideInvestigatorChk) {
        hideInvestigatorChk.addEventListener('change', e => {
            _hideInvestigator = e.target.checked;
            _render();
        });
    }

    const hideQuotesChk = container.querySelector('#as-hide-quotes');
    if (hideQuotesChk) {
        hideQuotesChk.addEventListener('change', e => {
            _hideQuotes = e.target.checked;
            _render();
        });
    }

    const hideSourceChk = container.querySelector('#as-hide-source');
    if (hideSourceChk) {
        hideSourceChk.addEventListener('change', e => {
            _hideSource = e.target.checked;
            _render();
        });
    }

    const hideNotesChk = container.querySelector('#as-hide-notes');
    if (hideNotesChk) {
        hideNotesChk.addEventListener('change', e => {
            _hideNotes = e.target.checked;
            _render();
        });
    }

    // Kategorie-Zeilen aufklappen/zuklappen
    container.querySelectorAll('.as-category-header').forEach(btn => {
        btn.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'annotation_sidebar', 'click:as-category-header', { cat: btn.dataset.category }); // B200
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
        btn.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'annotation_sidebar', 'click:as-btn-anchor', { annId: btn.dataset.annId }); // B200
            const annId = parseInt(btn.dataset.annId, 10);
            _insertAnchor(annId);
        });
    });

    // Drag-and-Drop: Annotation-Karten als Drag-Quelle (Phase 8)
    // dataTransfer-Format: text/x-annotation-id (kompatibel mit EvidenceBlock)
    // Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
    container.querySelectorAll('.as-annotation[draggable="true"]').forEach(card => {
        card.addEventListener('dragstart', e => {
            window._uevt?.(e, 'annotation_sidebar', 'dragstart:as-annotation', { annId: card.dataset.annId }); // B200
            const annId = card.dataset.annId;
            e.dataTransfer.setData('text/x-annotation-id', annId);
            e.dataTransfer.effectAllowed = 'copy';
            card.classList.add('as-annotation--dragging');
        });
        card.addEventListener('dragend', (e) => {
            window._uevt?.(e, 'annotation_sidebar', 'dragend:as-annotation'); // B200
            card.classList.remove('as-annotation--dragging');
        });
    });
}

// ---------------------------------------------------------------------------
// Beweisanker einfuegen
// ---------------------------------------------------------------------------

/**
 * Fuegt die Annotation als neuen EvidenceBlock in den Editor ein.
 *
 * Ablauf (Bauplan B6 §4.7, Planungsgespraech 2026-05-11):
 * 1. window.insertEvidenceBlockFromAnnotation(annId) aufrufen
 *    (report_editor.js) -> fuegt EvidenceBlock nach fokussiertem Block ein
 * 2. _anchoredIds aktualisieren, Sidebar neu rendern
 *
 * Beleg: Bauplan B6 §4.7, Planungsgespraech 2026-05-11
 */
async function _insertAnchor(annId) {
    _dbg('_insertAnchor: annId=', annId);

    const btn = document.querySelector(`.as-btn-anchor[data-ann-id="${annId}"]`);
    if (btn) { btn.disabled = true; btn.textContent = 'Wird eingefügt…'; }

    // Pruefen ob report_editor.js die Funktion bereitstellt
    // Beleg: Bauplan B6 §4.7, Planungsgespraech 2026-05-11
    if (typeof window.insertEvidenceBlockFromAnnotation !== 'function') {
        _showInsertError('Editor nicht bereit. Bitte Seite neu laden.');
        if (btn) { btn.disabled = false; btn.textContent = '📌 Als Beleg einfügen'; }
        return;
    }

    try {
        const ok = await window.insertEvidenceBlockFromAnnotation(annId);
        if (!ok) throw new Error('Einfügen fehlgeschlagen (kein Lock oder Editor nicht bereit)');

        // Sidebar: Annotation als verankert markieren
        _anchoredIds.add(annId);
        _render();
        _opts?.onAnchorAdded?.(annId, null);
        _dbg('_insertAnchor: EvidenceBlock eingefügt für annId=', annId);

    } catch (err) {
        if (btn) { btn.disabled = false; btn.textContent = '📌 Als Beleg einfügen'; }
        _showInsertError('Beleg konnte nicht eingefügt werden: ' + String(err));
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
    _hideAnchored     = false;
    _hideTags         = false;
    _hideInvestigator = false;
    _hideQuotes       = false;
    _hideSource       = false;
    _hideNotes        = false;
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
// Sidebar-Integration (B6 Phase 8)
// Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

/**
 * Rendert die Annotationssidebar in #accordion-body-annotations.
 * Haupteinstiegspunkt fuer report_editor.js.
 * Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
 *
 * @param {Array}  blocks  -- Bloecke des aktiven Berichts (fuer bereits-verankert-Filter)
 * @param {Object} opts    -- { getActiveBlockId, onAnchorAdded }
 *                           lockId wird nicht mehr direkt übergeben — DocumentLayer
 *                           verwaltet Lock-Kontext intern. Beleg: Paket 9
 */
function showSidebar(blocks, opts) {
    _opts = {
        containerId:         'accordion-body-annotations',
        // Paket 9: postFn delegiert an DocumentLayer statt _fetchWithLockInternal.
        // DocumentLayer prüft Lock-Guard und baut Kontext selbst auf.
        postFn:              (data) => {
            const dl = window.documentLayer;
            if (!dl) return Promise.reject(new Error('documentLayer nicht verfügbar'));
            return dl._sendRequest(data);
        },
        getActiveParagraph:  opts?.getActiveBlockId || (() => null),
        onAnchorAdded:       opts?.onAnchorAdded || (() => {}),
    };

    // Verankerte IDs aus report_anchors der Bloecke bestimmen
    // Beleg: Bauplan B6 v0.5 §4.4.2
    const anchoredFromBlocks = new Set();
    (blocks || []).forEach(b => {
        // Wenn der Block anchor_ids oder evidence_ids hat
        (b.anchor_ids || []).forEach(id => anchoredFromBlocks.add(id));
        // evidence_ids aus block_data (EvidenceBlock)
        if (b.block_type === 'evidence' && b.block_data) {
            try {
                const data = typeof b.block_data === 'string'
                    ? JSON.parse(b.block_data)
                    : b.block_data;
                (data.evidence_ids || []).forEach(id => anchoredFromBlocks.add(id));
            } catch (_) {}
        }
    });
    if (anchoredFromBlocks.size > 0) {
        _anchoredIds = anchoredFromBlocks;
    }

    if (_annotations.length === 0) {
        // Noch nicht geladen: laden + rendern
        _loadAnnotations();
    } else {
        // Bereits geladen: nur rendern (z.B. nach Akkordeon-Oeffnen)
        _render();
    }
}

/**
 * Interner postFn-Wrapper: sendet POST an /_forensic/report mit Lock-Header.
 * Kapselt das Fetch damit annotation_sidebar.js unabhaengig bleibt.
 * Beleg: Bauplan B6 v0.5 §4.4.2, Projektgespraech 2026-05-06
 */
async function _fetchWithLockInternal(data, lockId) {
    const headers = {
        'Content-Type':       'application/json',
        'X-Forensic-Request': 'ajax',
    };
    if (lockId) headers['X-Forensic-Lock-Id'] = lockId;
    const resp = await fetch('/_forensic/report', {
        method:  'POST',
        headers,
        body:    JSON.stringify(data),
    });
    const result = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(result.error || 'HTTP ' + resp.status);
    return result;
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

/**
 * Markiert eine einzelne Annotation als verankert und aktualisiert die Sidebar.
 *
 * Wird von report_editor.js aufgerufen nach einem Drop-Einfügen
 * (Option D) oder nach _addEvidence() in EvidenceBlock.
 * Bug 2.72 Fix Build 164: Drop-Weg benachrichtigte Sidebar nicht.
 * Beleg: Projektgespräch 2026-05-11
 *
 * @param {number} annId  -- Annotation-ID
 */
function notifyAnchored(annId) {
    _dbg('notifyAnchored: annId=', annId);
    if (!annId) return;
    _anchoredIds.add(annId);
    _render();
}

_dbg('annotation_sidebar.js: window.AnnotationSidebar exportiert');
window.AnnotationSidebar = {
    // Phase 8 Haupt-API
    showSidebar,
    // Bug 2.72 Fix Build 164: Sidebar nach Drop-Einfügen benachrichtigen
    notifyAnchored,
    // Unveraenderte API (Rueckwaerts-Kompatibilitaet und Tests)
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

})();
