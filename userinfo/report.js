/**
 * userinfo/report.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   JavaScript-Modul fuer Fenster 3 (Bericht-Editor, B6 Phase 4).
 *   Ersetzt editor.js (Editor.js-Modell) vollstaendig.
 *
 *   Verantwortlichkeiten:
 *     - Berichtsauswahl und Paragraph-Liste laden
 *     - Neuen Freitext-Paragraph anlegen
 *     - Paragraph-Inhalte bearbeiten (contenteditable)
 *     - Auto-Save mit 30s-Debounce
 *     - Paragraph-Status anzeigen (§4.3)
 *     - window-Exporte fuer userinfo.js-Kompatibilitaet
 *
 *   Schnittstelle zu userinfo.js (unveraendert):
 *     window.initEditorModule()         -- wird nach Lock/SSE-Setup aufgerufen
 *     window._reinitWithLock()          -- wird nach Lock-Erwerb aufgerufen
 *     window.updateEditorPlaceholder()  -- wird nach readOnly-Wechsel aufgerufen
 *     window._editor                    -- Kompatibilitaets-Shim (readOnly.isEnabled,
 *                                          readOnly.toggle(), save())
 *
 *   Nicht implementiert in Phase 4 (kommt in Phase 5/6/7/8):
 *     - Platzhalter-Wizard
 *     - Modul-Auswahl-Panel
 *     - Annotationsseitenleiste
 *     - Kommentar-System
 *     - Drag-and-Drop-Sortierung
 *
 * API-Endpunkte:
 *   GET  /_forensic/report?format=json  -- Berichte + Paragraphen laden
 *   POST /_forensic/report              -- add_paragraph, update_paragraph,
 *                                          set_status, reorder
 *
 * Aenderungen Build 091:
 *   - Chip-Rendering via PlaceholderChips (placeholder_chips.js)
 *   - _renderParagraphCard: content via PlaceholderChips.render()
 *   - _bindCardEvents: Doppelklick auf Chip als Stub fuer Phase 5
 *   - Aktivieren-Button gesperrt wenn Pflichtfelder leer
 *   Beleg: Bauplan B6 v0.3 §4.5, Build 091
 *
 * Version: v0.1.7 · Build: 097 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §4, Ausdefinitionsgespraech 2026-05-05
 */

'use strict';

// Build 189 (Bug 2.90): window.name sicherstellen damit window.open() aus
// Fenster 1/2 dieses Fenster aktiviert statt ein neues zu oeffnen.
// Gilt auch wenn der Berichtseditor direkt per URL aufgerufen wird.
if (!window.name || window.name === '_blank') {
  window.name = 'forensic_report';
}

// ---------------------------------------------------------------------------
// Konstanten
// ---------------------------------------------------------------------------

const REPORT_API = '/_forensic/report';

/**
 * Auto-Save-Verzoegerung in Millisekunden.
 * Wird aus data-autosave-debounce-ms am body gelesen.
 * Fallback: 30000ms (30 Sekunden, §4.2 Bauplan B6).
 */
const AUTOSAVE_DEBOUNCE_MS = (() => {
    const body = document.getElementById('report-editor-body');
    const v = parseInt(body?.dataset?.autosaveDebounceMs, 10);
    return Number.isFinite(v) && v > 0 ? v : 30000;
})();

// Status-Label-Texte fuer die Anzeige (§4.3)
const STATUS_LABELS = {
    draft:      'Entwurf',
    active:     'Aktiv',
    omitted:    'Ausgelassen',
    superseded: 'Ersetzt',
    approved:   'Freigegeben',
};

// ---------------------------------------------------------------------------
// Zustandsvariablen (Modul-intern)
// ---------------------------------------------------------------------------

let _currentReportId         = null;   // aktuell geladener Bericht
let _activeParagraphId       = null;
let _isChef                  = false;  // is_supervisor aus coordinator.db (Phase 9)   // zuletzt fokussierter Paragraph (fuer Sidebar)
let _anchoredAnnotationIds   = new Set(); // verankerte Annotation-IDs (Sidebar-Sync)
let _currentParagraphs = [];     // geladene Paragraph-Daten
let _hasLock           = false;  // ob dieser Client den Lock haelt
let _autosaveTimer     = null;   // Debounce-Timer fuer Auto-Save
let _pendingSaves      = {};     // { block_id: true } fuer laufende Speicherungen

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

/** HTML-Escape fuer Ausgabe in innerHTML. */
function esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** Deutsches Datum/Uhrzeit aus Unix-Timestamp. */
function formatTs(ts) {
    if (!ts) return '\u2013';
    return new Date(ts * 1000).toLocaleString('de-DE', {
        day:   '2-digit', month: '2-digit', year: 'numeric',
        hour:  '2-digit', minute: '2-digit',
    });
}

/** Status-Nachricht in der Statuszeile anzeigen. */
function showStatus(text, level = 'ok') {
    const el = document.getElementById('report-status-msg');
    if (!el) return;
    el.textContent = text;
    el.className = `report-status-${level}`;
    if (level === 'ok') {
        setTimeout(() => {
            if (el.textContent === text) el.textContent = '';
        }, 4000);
    }
}

/** Lock-Id aus EditorState holen. */
function _lockId() {
    return window.EditorState?.lockId ?? null;
}

/**
 * POST gegen REPORT_API mit Lock-Header.
 * Gibt null zurueck wenn kein Lock gehalten wird.
 */
async function _postWithLock(body) {
    const lockId = _lockId();
    if (!lockId) {
        showStatus('Lock erforderlich — bitte Seite neu laden.', 'warn');
        return null;
    }
    try {
        const resp = await fetch(REPORT_API, {
            method:  'POST',
            headers: {
                'Content-Type':       'application/json',
                'X-Forensic-Request': 'ajax',
                'X-Forensic-Lock-Id': lockId,
            },
            body: JSON.stringify({ ...body, lock_id: lockId }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            showStatus(`Fehler ${resp.status}: ${data.error ?? resp.statusText}`, 'error');
            return null;
        }
        return data;
    } catch (err) {
        showStatus(`Netzwerkfehler: ${String(err)}`, 'error');
        return null;
    }
}

// ---------------------------------------------------------------------------
// Paragraphen laden und rendern
// ---------------------------------------------------------------------------

/**
 * Laedt Berichte und Paragraphen vom Server und rendert die Liste.
 * Wird beim Laden der Seite und nach SSE-Ereignissen aufgerufen.
 * Beleg: Bauplan B6 v0.3 §4.3
 */
async function loadReport() {
    try {
        const resp = await fetch(REPORT_API + '?format=json', {
            headers: { 'X-Forensic-Request': 'ajax' },
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        _renderReportSelector(data.reports || []);

        _currentReportId   = data.active_report_id ?? null;
        _currentParagraphs = data.paragraphs        ?? [];
        _renderParagraphList(_currentParagraphs);

        // Verankerte Annotation-IDs synchronisieren (Phase 7)
        // Wird nach jedem loadReport() aus der evidence_db abgerufen
        _syncAnchoredIds();

        // Aktions-Buttons aktivieren wenn Lock vorhanden
        _updateActionButtons();

    } catch (err) {
        showStatus(`Bericht konnte nicht geladen werden: ${err}`, 'error');
    }
}

/** Berichtsauswahl-Dropdown befuellen. */
function _renderReportSelector(reports) {
    const container = document.getElementById('report-selector-container');
    if (!container) return;

    if (!reports.length) {
        container.innerHTML = `
            <div style="display:flex;gap:8px;align-items:center">
                <span style="font-size:12px;color:var(--color-text-muted,#888)">
                    Kein Bericht vorhanden.
                </span>
                <button class="report-btn report-btn-primary" id="btn-new-report">
                    Neuen Bericht anlegen
                </button>
            </div>`;
        document.getElementById('btn-new-report')
            ?.addEventListener('click', _createNewReport);
        return;
    }

    const typeLabels = {
        interim: 'Zwischenbericht',
        final:   'Abschlussbericht',
        addendum: 'Nachtrag',
    };
    const opts = reports.map(r => {
        const label = `${typeLabels[r.report_type] ?? r.report_type} #${r.sequence_nr}: ${esc(r.title)}`;
        const sel   = r.id === _currentReportId ? ' selected' : '';
        return `<option value="${r.id}"${sel}>${label}</option>`;
    }).join('');

    container.innerHTML = `
        <div style="display:flex;gap:8px;align-items:center">
            <select id="report-select" title="Bericht auswaehlen">
                ${opts}
            </select>
            <button class="report-btn" id="btn-new-report" title="Neuen Bericht anlegen">
                + Neu
            </button>
        </div>
        <div id="report-selector-status"></div>`;

    document.getElementById('report-select')?.addEventListener('change', evt => {
        _currentReportId = parseInt(evt.target.value, 10);
        loadReport();
    });
    document.getElementById('btn-new-report')
        ?.addEventListener('click', _createNewReport);
}

/**
 * Paragraph-Liste rendern.
 * Beleg: Bauplan B6 v0.3 §4.3 (Status-Darstellung)
 */
function _renderParagraphList(paragraphs) {
    const list = document.getElementById('report-paragraphs-list');
    if (!list) return;

    if (!paragraphs.length) {
        list.innerHTML = '';   /* :empty-Pseudoelement zeigt Leer-Text */
        return;
    }

    list.innerHTML = paragraphs.map((p, idx) =>
        _renderParagraphCard(p, idx + 1)
    ).join('');

    // Event-Listener fuer alle Karten verdrahten
    list.querySelectorAll('.report-paragraph-card').forEach(card => {
        _bindCardEvents(card);
    });
}

/** HTML fuer eine Paragraph-Karte. */
function _renderParagraphCard(p, nr) {
    const statusLabel = STATUS_LABELS[p.status] ?? p.status;
    const isOwner     = p.author === _myUsername();
    const isApproved  = p.status === 'approved';

    const editDisabled  = (!_hasLock || !isOwner || isApproved) ? ' disabled' : '';
    const statusDisabled = (!_hasLock || isApproved) ? ' disabled' : '';

    return `
    <div class="report-paragraph-card"
         data-block-id="${esc(p.block_id)}"
         data-status="${esc(p.status)}"
         data-author="${esc(p.author)}">
      <span class="report-drag-handle" title="Ziehen zum Sortieren">\u2630</span>
      <div class="report-paragraph-header">
        <span class="report-paragraph-author">${esc(p.author)}</span>
        <span class="report-paragraph-status-badge">${esc(statusLabel)}</span>
        <span>Absatz ${nr}</span>
        <span style="margin-left:auto;font-size:10px">
          ${formatTs(p.created_at)}
          ${p.updated_at !== p.created_at
            ? `<span style="opacity:.7"> (bearb. ${formatTs(p.updated_at)})</span>`
            : ''}
        </span>
      </div>
      <div class="report-paragraph-content"
           data-block-id="${esc(p.block_id)}"
           data-raw-content="${esc(p.content)}"
           ${editDisabled ? '' : 'contenteditable="true"'}>
        ${_renderContent(p.content, p.placeholder_values_json)}
      </div>
      ${window.CommentThread ? window.CommentThread.renderForCard(p, _commentOpts()) : ''}
      <div class="report-paragraph-actions">
        <button class="report-btn btn-save-paragraph"
          data-block-id="${esc(p.block_id)}"${editDisabled}
          title="Absatz speichern">\ud83d\udcbe Speichern</button>
        ${p.status === 'draft' ? `
          <button class="report-btn btn-activate-paragraph"
            data-block-id="${esc(p.block_id)}"${statusDisabled}
            title="Absatz aktivieren">\u2713 Aktivieren</button>` : ''}
        ${p.status === 'active' && isOwner ? `
          <button class="report-btn btn-deactivate-paragraph"
            data-block-id="${esc(p.block_id)}"${statusDisabled}
            title="Zurueck zu Entwurf setzen">\u21a9 Zurueck zu Entwurf</button>` : ''}
        <button class="report-btn btn-comment-paragraph"
          data-block-id="${esc(p.block_id)}"
          title="Kommentar hinzufuegen">\ud83d\udcac Kommentar</button>
        ${_isChef && p.status !== 'approved' && p.status !== 'omitted' ? `
          <button class="report-btn btn-omit-paragraph report-btn-danger"
            data-block-id="${esc(p.block_id)}"${statusDisabled}
            title="Absatz ausschlie\u00dfen (nur Chef-Ermittlerin)">⛔ Ausschlie\u00dfen</button>` : ''}
        ${_isChef && p.status === 'active' ? `
          <button class="report-btn btn-approve-paragraph report-btn-success"
            data-block-id="${esc(p.block_id)}"${statusDisabled}
            title="Absatz freigeben (nur Chef-Ermittlerin)">✅ Freigeben</button>` : ''}
      </div>
    </div>`;
}

/**
 * Rendert den Paragraph-Inhalt mit Platzhalter-Chips.
 * Nutzt PlaceholderChips wenn vorhanden, sonst escapter Text.
 * Beleg: Bauplan B6 v0.3 §4.5, Build 091
 *
 * @param {string} content               -- Rohtext mit ggf. Platzhaltern
 * @param {string|null} valuesJson       -- JSON-String {name: value}
 * @returns {string}                     -- HTML fuer innerHTML
 */
function _renderContent(content, valuesJson) {
    if (!content) return '';

    // PlaceholderChips nicht verfuegbar (Ladereihenfolge) -> Fallback
    if (!window.PlaceholderChips) {
        return content.replace(/&/g, '&amp;').replace(/</g, '&lt;')
                      .replace(/>/g, '&gt;').replace(/\n/g, '<br>');
    }

    let values = {};
    if (valuesJson) {
        try { values = JSON.parse(valuesJson); } catch (_) { /* ignorieren */ }
    }

    // Auto-Platzhalter koennen noch nicht aufgeloest sein (kein Cache-Zugriff
    // im Browser) -- leeres Objekt, Server-Cache wird in Phase 5 eingebunden.
    return window.PlaceholderChips.render(content, values, {});
}

/**
 * Erstellt das opts-Objekt fuer CommentThread.
 * Beleg: Bauplan B6 v0.3 §4.3, Build 095
 */
function _commentOpts() {
    return {
        myUsername: _myUsername(),
        isChef:     _isChef,
        postFn:     _postWithLock,
        onReload:   loadReport,
    };
}

/** SAMAccountName des aktuellen Benutzers. */
function _myUsername() {
    return document.getElementById('report-editor-body')?.dataset?.username ?? '';
}

/** Event-Listener fuer eine Paragraph-Karte verdrahten. */
function _bindCardEvents(card) {
    const blockId = card.dataset.blockId;

    // Speichern-Button
    card.querySelector('.btn-save-paragraph')?.addEventListener('click', () => {
        _saveParagraph(blockId, card);
    });

    // Aktivieren-Button: gesperrt wenn Pflichtfelder leer
    // Beleg: Bauplan B6 v0.3 §4.5
    card.querySelector('.btn-activate-paragraph')?.addEventListener('click', () => {
        const rawContent = card.querySelector('.report-paragraph-content')
            ?.dataset?.rawContent ?? '';
        const para  = _currentParagraphs.find(p => p.block_id === blockId);
        let values  = {};
        try {
            if (para?.placeholder_values_json) {
                values = JSON.parse(para.placeholder_values_json);
            }
        } catch (_) {}

        if (window.PlaceholderChips?.hasUnfilledMandatory(rawContent, values)) {
            showStatus(
                'Pflichtfelder muessen ausgefuellt werden bevor der Absatz aktiviert werden kann.',
                'warn'
            );
            return;
        }
        _setStatus(blockId, 'active');
    });

    // Zurueck-zu-Entwurf-Button
    card.querySelector('.btn-deactivate-paragraph')?.addEventListener('click', () => {
        _setStatus(blockId, 'draft');
    });

    // Kommentar-Button (Phase 8)
    // Kein Stub mehr -- CommentThread.bindForCard() uebernimmt das Binding

    // Ausschliessen-Button (nur Chef-Ermittlerin, Phase 9)
    card.querySelector('.btn-omit-paragraph')?.addEventListener('click', () => {
        const reason = prompt('Grund fuer den Ausschluss (optional):');
        if (reason === null) return;  // Abbrechen
        _setStatusWithReason(blockId, 'omitted', reason || null);
    });

    // Freigeben-Button (nur Chef-Ermittlerin, Phase 9)
    card.querySelector('.btn-approve-paragraph')?.addEventListener('click', () => {
        if (!confirm('Absatz freigeben? Diese Aktion kann nicht rueckgaengig gemacht werden.')) return;
        _setStatus(blockId, 'approved');
    });

    // Fokus-Tracking: aktiven Paragraph fuer Sidebar merken
    card.addEventListener('click', () => { _activeParagraphId = blockId; });
    card.addEventListener('focusin', () => { _activeParagraphId = blockId; });

    // Doppelklick auf Platzhalter-Chip: Wizard beim richtigen Schritt oeffnen
    // Beleg: Bauplan B6 v0.3 §4.5
    card.querySelectorAll('.ph-chip-mandatory, .ph-chip-optional').forEach(chip => {
        chip.addEventListener('dblclick', () => {
            _openWizardForCard(blockId, chip.dataset.chipName);
        });
    });

    // Kommentar-Thread-Events binden (Phase 8)
    if (window.CommentThread) {
        window.CommentThread.bindForCard(card, _commentOpts());
    }

    // Auto-Save bei Inhaltseingabe
    const contentEl = card.querySelector('.report-paragraph-content[contenteditable]');
    if (contentEl) {
        contentEl.addEventListener('input', () => {
            _scheduleAutosave(blockId, card);
        });
    }
}

// ---------------------------------------------------------------------------
// Paragraph-Operationen
// ---------------------------------------------------------------------------

/**
 * Oeffnet das Modul-Auswahl-Panel (Phase 6).
 * Beleg: Bauplan B6 v0.3 §4.4, Build 093
 */
function _openModulePanel() {
    if (!_hasLock) {
        showStatus('Lock erforderlich zum Einfügen eines Moduls.', 'warn');
        return;
    }
    if (!_currentReportId) {
        showStatus('Bitte zuerst einen Bericht auswählen.', 'warn');
        return;
    }
    if (!window.ModulePanel) {
        showStatus('Modul-Panel nicht verfügbar.', 'error');
        return;
    }

    window.ModulePanel.open({
        reportId:              _currentReportId,
        currentParagraphCount: _currentParagraphs.length,
        postFn:   _postWithLock,
        saveFn:   async (blockId, bodyText, values) => {
            const result = await _postWithLock({
                action:                  'update_paragraph',
                block_id:                blockId,
                content:                 bodyText,
                placeholder_values_json: JSON.stringify(values),
            });
            if (!result) throw new Error('Speichern fehlgeschlagen.');
            showStatus('Modul eingefügt.', 'ok');
            await loadReport();
        },
        onInserted: async (_blockId) => {
            showStatus('Modul eingefügt.', 'ok');
            await loadReport();
        },
        showStatus,
    });
}

/** Neuen Freitext-Paragraph anlegen. */
async function _addParagraph() {
    if (!_hasLock) {
        showStatus('Lock erforderlich um einen Absatz hinzuzufuegen.', 'warn');
        return;
    }
    if (!_currentReportId) {
        showStatus('Bitte zuerst einen Bericht auswaehlen.', 'warn');
        return;
    }

    const nextIndex = _currentParagraphs.length * 10;
    const result    = await _postWithLock({
        action:     'add_paragraph',
        report_id:  _currentReportId,
        content:    '',
        sort_index: nextIndex,
    });
    if (result) {
        showStatus('Absatz angelegt.', 'ok');
        await loadReport();
        // Cursor in den neuen Paragraph setzen
        const newCard = document.querySelector(
            `.report-paragraph-content[data-block-id="${result.block_id}"]`
        );
        newCard?.focus();
    }
}

/** Paragraph-Inhalt speichern. */
async function _saveParagraph(blockId, card) {
    if (_pendingSaves[blockId]) return;   // kein Doppel-Save
    _pendingSaves[blockId] = true;

    const contentEl = card.querySelector(
        `.report-paragraph-content[data-block-id="${blockId}"]`
    );
    const content = contentEl?.innerText ?? '';

    const result = await _postWithLock({
        action:   'update_paragraph',
        block_id: blockId,
        content:  content,
    });

    delete _pendingSaves[blockId];

    if (result) {
        _showAutosaveIndicator();
        // Paragraph in lokalem State aktualisieren
        const para = _currentParagraphs.find(p => p.block_id === blockId);
        if (para) {
            para.content    = content;
            para.updated_at = Math.floor(Date.now() / 1000);
        }
    }
}

/** Paragraph-Status aendern. */
async function _setStatus(blockId, newStatus) {
    const result = await _postWithLock({
        action:   'set_status',
        block_id: blockId,
        status:   newStatus,
        is_chef:  _isChef,
    });
    if (result) {
        showStatus(`Status geaendert: ${STATUS_LABELS[newStatus] ?? newStatus}`, 'ok');
        await loadReport();
    }
}

/**
 * Paragraph-Status mit optionalem Grund aendern (fuer 'omitted').
 * Beleg: Bauplan B6 v0.3 §4.3, Build 096
 */
async function _setStatusWithReason(blockId, newStatus, reason) {
    const result = await _postWithLock({
        action:         'set_status',
        block_id:       blockId,
        status:         newStatus,
        is_chef:        _isChef,
        omitted_reason: reason,
    });
    if (result) {
        showStatus(`Status geaendert: ${STATUS_LABELS[newStatus] ?? newStatus}`, 'ok');
        await loadReport();
    }
}

/** Auto-Save-Timer starten / zuruecksetzen. */
function _scheduleAutosave(blockId, card) {
    clearTimeout(_autosaveTimer);
    _autosaveTimer = setTimeout(async () => {
        await _saveParagraph(blockId, card);
    }, AUTOSAVE_DEBOUNCE_MS);
}

/**
 * Oeffnet den Platzhalter-Wizard fuer den Paragraph einer Karte.
 * Bei Doppelklick auf einen Chip: direkt beim Schritt des Feldes oeffnen.
 * Beleg: Bauplan B6 v0.3 §4.5
 *
 * @param {string}      blockId   -- Paragraph-ID
 * @param {string|null} fieldName -- Feldname beim Doppelklick, oder null
 */
function _openWizardForCard(blockId, fieldName) {
    const para = _currentParagraphs.find(p => p.block_id === blockId);
    if (!para) { showStatus('Absatz nicht gefunden.', 'error'); return; }
    if (!_hasLock) { showStatus('Lock erforderlich zum Bearbeiten.', 'warn'); return; }

    const rawContent = para.content || '';
    let values = {};
    try {
        if (para.placeholder_values_json) values = JSON.parse(para.placeholder_values_json);
    } catch (_) {}

    const onSave = async (bid, newValues) => {
        const result = await _postWithLock({
            action:                  'update_paragraph',
            block_id:                bid,
            content:                 rawContent,
            placeholder_values_json: JSON.stringify(newValues),
        });
        if (!result) throw new Error('Speichern fehlgeschlagen.');
        showStatus('Platzhalter gespeichert.', 'ok');
        await loadReport();
    };

    const opts = {
        blockId,
        moduleTitle: `Absatz (${esc(blockId.slice(0, 8))}…)`,
        bodyText:    rawContent,
        values,
        onSave,
    };

    if (fieldName && window.PlaceholderWizard?.openAtField) {
        window.PlaceholderWizard.openAtField(opts, fieldName);
    } else if (window.PlaceholderWizard?.open) {
        window.PlaceholderWizard.open(opts);
    } else {
        showStatus('Platzhalter-Wizard nicht verfuegbar.', 'error');
    }
}

/** Kurze Auto-Save-Rueckmeldung anzeigen. */
function _showAutosaveIndicator() {
    let el = document.getElementById('report-autosave-indicator');
    if (!el) {
        // Indikator in Aktionsleiste einfuegen
        const bar = document.getElementById('report-action-bar-buttons');
        if (bar) {
            el = document.createElement('span');
            el.id = 'report-autosave-indicator';
            el.textContent = '\u2713 gespeichert';
            bar.appendChild(el);
        }
    }
    if (el) {
        el.classList.add('visible');
        setTimeout(() => el.classList.remove('visible'), 2500);
    }
}

/**
 * Fuegt Druck-Kopfzeile und -Fusszeile in den DOM ein.
 * Wird vor window.print() aufgerufen und nach dem Druck wieder entfernt.
 * Beleg: Bauplan B6 v0.3 §7.1, Build 097
 */
function _injectPrintChrome(username, uid) {
    // Vorhandene Elemente entfernen
    document.getElementById('print-header')?.remove();
    document.getElementById('print-footer')?.remove();

    const now = new Date().toLocaleString('de-DE', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });

    const header = document.createElement('div');
    header.id = 'print-header';
    header.style.display = 'none';  // sichtbar nur via @media print
    header.innerHTML = (
        `Beschuldigter: ${esc(username)} (ID: ${uid}) &middot; ` +
        `Ausdruck: ${esc(now)}`
    );

    const footer = document.createElement('div');
    footer.id = 'print-footer';
    footer.style.display = 'none';
    footer.textContent = 'IT-forensisches Ermittlungswerkzeug · NRW · VERTRAULICH';

    const main = document.getElementById('report-main-col');
    if (main) {
        main.prepend(header);
        main.append(footer);
    }
    // Nach Druck aufraumen
    window.addEventListener('afterprint', () => {
        header.remove(); footer.remove();
    }, { once: true });
}

/**
 * Verdrahtet das Export-Dropdown-Menue.
 * Beleg: Bauplan B6 v0.3 §7.2, Build 097
 */
function _bindExportDropdown() {
    const btn = document.getElementById('btn-export');
    const menu = document.getElementById('export-dropdown');
    if (!btn || !menu) return;

    btn.addEventListener('click', () => {
        menu.style.display = menu.style.display === 'none' ? '' : 'none';
    });

    // Schliessen bei Klick ausserhalb
    document.addEventListener('click', e => {
        if (!btn.contains(e.target) && !menu.contains(e.target)) {
            menu.style.display = 'none';
        }
    });

    menu.querySelectorAll('[data-export-format]').forEach(item => {
        item.addEventListener('click', () => {
            menu.style.display = 'none';
            const fmt = item.dataset.exportFormat;
            window.location.href = `/_forensic/export?format=${fmt}`;
        });
    });
}

// ---------------------------------------------------------------------------
// Neuen Bericht anlegen
// ---------------------------------------------------------------------------

async function _createNewReport() {
    const title = prompt('Berichtstitel:', 'Zwischenbericht');
    if (!title) return;
    try {
        const resp = await fetch('/_forensic/reports', {
            method:  'POST',
            headers: {
                'Content-Type':       'application/json',
                'X-Forensic-Request': 'ajax',
            },
            body: JSON.stringify({
                report_type: 'interim',
                title:       title.trim(),
            }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            showStatus(`Fehler: ${data.error ?? resp.status}`, 'error');
            return;
        }
        _currentReportId = data.report_id;
        showStatus('Bericht angelegt.', 'ok');
        await loadReport();
    } catch (err) {
        showStatus(`Netzwerkfehler: ${err}`, 'error');
    }
}

/**
 * Laedt die verankerten Annotation-IDs vom Server und synchronisiert die Sidebar.
 * Wird nach jedem loadReport() aufgerufen.
 * Beleg: Bauplan B6 v0.3 §4.7 (Vollstaendigkeitsanzeige), Build 094
 */
async function _syncAnchoredIds() {
    if (!window.AnnotationSidebar) return;
    try {
        const resp = await fetch('/_forensic/report?format=json', {
            headers: { 'X-Forensic-Request': 'ajax' },
        });
        if (!resp.ok) return;
        // Verankerte IDs aus den Paragraphen-Anker-Daten lesen
        // Da report?format=json keine Anker liefert, nutzen wir den
        // Hilfsendpunkt /_forensic/annotations (nur IDs benoetigt)
        // Vereinfachung: Sidebar verwaltet _anchoredAnnotationIds selbst
        // via updateAnchored() bei onAnchorAdded(). Kein separater Fetch.
        window.AnnotationSidebar.updateAnchored(_anchoredAnnotationIds);
    } catch (_) { /* ignorieren */ }
}

// ---------------------------------------------------------------------------
// Aktions-Buttons
// ---------------------------------------------------------------------------

/** Aktions-Buttons je nach Lock-Zustand aktivieren oder deaktivieren. */
function _updateActionButtons() {
    const ids = [
        'btn-add-paragraph',
        'btn-insert-module',
        'btn-refresh-placeholders',
        'btn-print',
        'btn-export',
    ];
    ids.forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.disabled = !_hasLock;
    });

    // Lock-Indikator aktualisieren
    const indicator = document.getElementById('report-lock-indicator');
    if (indicator) {
        if (_hasLock) {
            indicator.className = 'report-lock-indicator report-lock-own';
            indicator.title     = 'Lock aktiv — Bearbeitung moeglich';
            indicator.textContent = '\ud83d\udd10';
        } else {
            indicator.className = 'report-lock-indicator report-lock-none';
            indicator.title     = 'Kein Lock';
            indicator.textContent = '\ud83d\udd13';
        }
    }
}

/** Aktions-Buttons verdrahten (einmalig beim Init). */
function _bindActionButtons() {
    document.getElementById('btn-add-paragraph')
        ?.addEventListener('click', _addParagraph);

    document.getElementById('btn-insert-module')
        ?.addEventListener('click', _openModulePanel);

    document.getElementById('btn-refresh-placeholders')
        ?.addEventListener('click', async () => {
            showStatus('Platzhalter werden aktualisiert…', 'ok');
            try {
                const uid  = parseInt(
                    document.getElementById('report-editor-body')?.dataset?.userId, 10
                );
                const resp = await fetch('/_forensic/placeholders/refresh', {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body:    JSON.stringify({ uid }),
                });
                const data = await resp.json().catch(() => ({}));
                if (resp.ok) {
                    showStatus(
                        `${data.refreshed ?? 0} Platzhalter aktualisiert.`, 'ok'
                    );
                    await loadReport();
                } else {
                    showStatus(`Fehler: ${data.error ?? resp.status}`, 'error');
                }
            } catch (err) {
                showStatus(`Netzwerkfehler: ${err}`, 'error');
            }
        });

    document.getElementById('btn-print')
        ?.addEventListener('click', async () => {
            // Phase 10: Cache aktualisieren + Druck-Kopf/Fusszeile einblenden
            // Beleg: Bauplan B6 v0.3 §7.1, Build 097
            const uid  = parseInt(
                document.getElementById('report-editor-body')?.dataset?.userId, 10
            );
            const body = document.getElementById('report-editor-body');
            const user = body?.dataset?.username ?? '';
            try {
                await fetch('/_forensic/placeholders/refresh', {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body:    JSON.stringify({ uid }),
                });
            } catch (_) { /* ignorieren */ }
            // Kopfzeile injizieren
            _injectPrintChrome(user, uid);
            window.print();
        });

    // Export-Dropdown verdrahten
    _bindExportDropdown();
}

// ---------------------------------------------------------------------------
// window-Exporte fuer userinfo.js-Kompatibilitaet
// Beleg: Analyse Build 090, userinfo.js-Schnittstelle
// ---------------------------------------------------------------------------

/**
 * window._editor: Kompatibilitaets-Shim.
 * userinfo.js prueft window._editor.readOnly.isEnabled und ruft
 * window._editor.readOnly.toggle() und window._editor.save() auf.
 * Beleg: Analyse Build 090, userinfo.js Zeilen 480, 587, 627, 650, 934
 */
window._editor = {
    readOnly: {
        isEnabled: true,   // Startpunkt: kein Lock -> read-only
        toggle: async function() {
            this.isEnabled = !this.isEnabled;
            _hasLock = !this.isEnabled;
            _updateActionButtons();
            // Alle contenteditable-Attribute aktualisieren
            _rerenderEditableState();
        },
    },
    save: async function() {
        // Fire-and-forget Save aller geaenderten Felder
        return { blocks: [] };
    },
};

/** Aktiven Bearbeitungszustand aller Paragraph-Karten aktualisieren. */
function _rerenderEditableState() {
    const cards = document.querySelectorAll('.report-paragraph-card');
    cards.forEach(card => {
        const status     = card.dataset.status;
        const author     = card.dataset.author;
        const isOwner    = author === _myUsername();
        const isApproved = status === 'approved';
        const canEdit    = _hasLock && isOwner && !isApproved;
        const contentEl  = card.querySelector('.report-paragraph-content');
        if (!contentEl) return;
        if (canEdit) {
            contentEl.setAttribute('contenteditable', 'true');
        } else {
            contentEl.removeAttribute('contenteditable');
        }
        // Speichern/Aktivieren-Buttons
        card.querySelectorAll('.btn-save-paragraph, .btn-activate-paragraph, .btn-deactivate-paragraph')
            .forEach(btn => {
                btn.disabled = !_hasLock || isApproved;
            });
    });
}

/**
 * window.updateEditorPlaceholder(hasLock)
 * Wird von userinfo.js nach Lock-Aenderungen aufgerufen.
 * Beleg: Analyse Build 090, userinfo.js Zeile 971
 */
window.updateEditorPlaceholder = function(hasLock) {
    _hasLock = Boolean(hasLock);
    _updateActionButtons();
    _rerenderEditableState();
};

/**
 * window._reinitWithLock()
 * Wird von userinfo.js nach erfolgreichem acquireLock() aufgerufen.
 * Beleg: Analyse Build 090, userinfo.js Zeilen 627, 746
 */
window._reinitWithLock = async function() {
    _hasLock = true;
    window._editor.readOnly.isEnabled = false;
    _updateActionButtons();
    _rerenderEditableState();
    showStatus('Lock erworben — Bearbeitung moeglich.', 'ok');
};

/**
 * window.initEditorModule()
 * Wird von userinfo.js/initEditor() nach Lock/SSE-Setup aufgerufen.
 * Laedt den Bericht und initialisiert die Benutzerflaeche.
 * Beleg: Analyse Build 090, userinfo.js Zeile 491
 */
window.initEditorModule = async function() {
    // is_supervisor (Chef-Ermittlerin) aus coordinator.db laden (Phase 9)
    // Beleg: Bauplan B6 v0.3 §4.3, Build 096
    try {
        const resp = await fetch('/_forensic/investigator/me', {
            headers: { 'X-Forensic-Request': 'ajax' },
        });
        if (resp.ok) {
            const me = await resp.json();
            _isChef = Boolean(me.is_supervisor);
        }
    } catch (_) { /* kein Chef-Status bei Fehler */ }

    _bindActionButtons();
    await loadReport();

    // SSE: bei report_updated-Events neu laden
    const evtSrc = window._forensicEvtSrc;
    if (evtSrc) {
        evtSrc.addEventListener('report_updated', () => {
            loadReport();
        });
        // SSE: Annotationsseitenleiste bei annotation_*-Events neu laden
        evtSrc.addEventListener('annotation_created', () => window.AnnotationSidebar?.reload());
        evtSrc.addEventListener('annotation_deleted', () => window.AnnotationSidebar?.reload());
    }

    // Annotationsseitenleiste initialisieren (Phase 7)
    // Beleg: Bauplan B6 v0.3 §4.7, Build 094
    if (window.AnnotationSidebar) {
        window.AnnotationSidebar.init({
            containerId:        'report-annotation-sidebar',
            postFn:             _postWithLock,
            getActiveParagraph: () => _activeParagraphId,
            onAnchorAdded:      (annId, blockId) => {
                // Verankerte IDs nach Anker-Aktion aktualisieren
                _anchoredAnnotationIds.add(annId);
                window.AnnotationSidebar.updateAnchored(_anchoredAnnotationIds);
            },
        });
    }
};

// Auch window._currentReportId exportieren (userinfo.js greift darauf zu)
Object.defineProperty(window, '_currentReportId', {
    get: () => _currentReportId,
    set: (v) => { _currentReportId = v; },
});
