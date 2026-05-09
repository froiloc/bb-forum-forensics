/**
 * userinfo/placeholder_wizard.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Platzhalter-Formular fuer den Formular-Akkordeon-Abschnitt der
 *   Support-Sidebar (B6 Phase 6, Bauplan B6 v0.5 §4.4.3).
 *
 *   Zeigt Platzhalter-Eingabefelder ALLER Bloecke des aktiven Berichts
 *   in Dokumentreihenfolge. Der fokussierte Block erscheint scharf,
 *   alle anderen sind geblurt (filter: blur + opacity). Beides ist
 *   synchron mit dem blauen Fokus-Rahmen auf dem Editor-Block.
 *
 *   Verhaltensregeln (§4.4.3):
 *     - Felder: m: mit rotem *, o: ohne, a: nicht angezeigt.
 *     - Klick auf ein geblurtes Feld setzt den Fokus direkt.
 *     - Tab/Shift+Tab: naechstes/vorheriges Feld, Blur wandert mit.
 *     - RegExp-Validierung: gruenem Rahmen bei OK, Warntext bei Fehler.
 *       Kein Speichern blockiert (Grundregel 11).
 *     - Leer-Zustand: "Kein Bericht geoeffnet."
 *     - Block ohne Platzhalter: "Keine Platzhalter" (sichtbar, geblurt).
 *     - Scroll: fokussierter Block bleibt in mittleren 80% des Viewports.
 *
 * Rueckwaerts-Kompatibilitaet:
 *   buildSteps(), stepIndexForField() und die open()/openAtField()-Aufrufe
 *   aus Phase 5 (report_editor.js _bindChipDoubleClick) werden weiter
 *   unterstuetzt. open() ist jetzt ein Alias fuer showPlaceholderForm().
 *
 * Exports:
 *   window.PlaceholderWizard.showPlaceholderForm(blocks, focusedBlockId, opts)
 *     Rendert das Formular in #accordion-body-form.
 *   window.PlaceholderWizard.focusBlock(blockId)
 *     Verschiebt den Formular-Fokus auf einen anderen Block.
 *   window.PlaceholderWizard.open(options)      [Rueckwaerts-Kompatibilitaet]
 *   window.PlaceholderWizard.openAtField(opts, fieldName)  [RW-Compat]
 *   window.PlaceholderWizard.close()            [Rueckwaerts-Kompatibilitaet]
 *   window.PlaceholderWizard.buildSteps(bodyText)
 *   window.PlaceholderWizard.stepIndexForField(steps, name)
 *
 *   opts: {
 *     myUsername: string,
 *     onSave:     async function(blockId, name, value)
 *     blocks:     array (alle Bloecke des Berichts)
 *   }
 *
 * Abhaengigkeiten:
 *   placeholder_chips.js (window.PlaceholderChips) muss VOR diesem Skript
 *   geladen sein.
 *
 * Changelog:
 *   Build 092: Erstimplementierung als Modal-Wizard (buildSteps, stepIndexForField).
 *   Build 104 (B6 Phase 6): Modal-Code durch Sidebar-Formular ersetzt.
 *     showPlaceholderForm() rendert alle Bloecke in #accordion-body-form.
 *     Blur-Fokus-Synchronisation mit Editor-Block (comment_thread.js-Muster).
 *     RegExp-Validierung, Tab-Navigation, Scroll-Zentrierung.
 *     Wert-Speicherung via onSave-Callback pro Feld.
 *     Rueckwaerts-Kompatibilitaet fuer open()/openAtField() erhalten.
 *     Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06.
 *
 * Version: v0.6.136 · Build: 136 · 2026-05-09
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
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

/** Maximale Anzahl Felder pro Wizard-Schritt (fuer buildSteps — bleibt erhalten). */
const FIELDS_PER_STEP = 3;

/** Zeitdauer fuer debounced Auto-Save nach Eingabe (ms). */
const FIELD_SAVE_DEBOUNCE_MS = 700;

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

function _esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** Base64-Decode mit Unicode-Unterstuetzung (OP-B6-5). */
function _b64DecodeUnicode(str) {
    try {
        return decodeURIComponent(atob(str).split('').map(c =>
            '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
        ).join(''));
    } catch (_) {
        return null;
    }
}

// ---------------------------------------------------------------------------
// buildSteps / stepIndexForField (unveraendert aus Build 092)
// Beleg: Bauplan B6 v0.3 §4.5
// ---------------------------------------------------------------------------

/**
 * Teilt die Felder eines Paragraphen in Wizard-Schritte auf.
 * m:-Felder zuerst, dann o:-Felder; max FIELDS_PER_STEP pro Schritt.
 */
function buildSteps(bodyText) {
    const chips = window.PlaceholderChips;
    if (!chips) return [[]];

    const mFields = chips.extractFields(bodyText, 'm').map(f => ({ ...f, type: 'm' }));
    const oFields = chips.extractFields(bodyText, 'o').map(f => ({ ...f, type: 'o' }));
    const allFields = [...mFields, ...oFields];

    if (!allFields.length) return [[]];

    const steps = [];
    for (let i = 0; i < allFields.length; i += FIELDS_PER_STEP) {
        steps.push(allFields.slice(i, i + FIELDS_PER_STEP));
    }
    return steps;
}

/**
 * Gibt den Schritt-Index zurueck, der das Feld mit dem Namen fieldName enthaelt.
 * Gibt 0 zurueck wenn das Feld nicht gefunden wird.
 */
function stepIndexForField(steps, fieldName) {
    for (let i = 0; i < steps.length; i++) {
        if (steps[i].some(f => f.name === fieldName)) return i;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// Sidebar-Formular-Zustand
// ---------------------------------------------------------------------------

let _currentBlockId  = null;   // aktuell fokussierter Block-ID
let _currentBlocks   = [];     // alle Bloecke des Berichts
let _currentOpts     = {};     // { myUsername, onSave }
let _saveTimers      = {};     // Debounce-Timer { "blockId:fieldName": timer }

// ---------------------------------------------------------------------------
// Sidebar-Formular rendern
// ---------------------------------------------------------------------------

/**
 * Rendert das Platzhalter-Formular fuer alle Bloecke in #accordion-body-form.
 * Haupteinstiegspunkt fuer report_editor.js.
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
 *
 * @param {Array}  blocks         -- alle Bloecke des Berichts (aus GET format=json)
 * @param {string} focusedBlockId -- block_id des fokussierten Blocks
 * @param {Object} opts           -- { myUsername, onSave: async(blockId, name, val) }
 */
function showPlaceholderForm(blocks, focusedBlockId, opts) {
    const body = document.getElementById('accordion-body-form');
    if (!body) return;

    // Bug 2.29 Fix Build 123: Alten Puls loeschen BEVOR _currentBlockId
    // ueberschrieben wird. showPlaceholderForm wird bei jedem Akkordeon-
    // Oeffnen neu aufgerufen — ohne Cleanup blieben alte Pulse stehen.
    // Beleg: Bugfix Build 123, Projektgespraech 2026-05-08
    if (_currentBlockId && _currentBlockId !== focusedBlockId) {
        window.CommentThread?._clearEditorBlockPulse?.(_currentBlockId);
    }

    _currentBlocks  = blocks || [];
    _currentBlockId = focusedBlockId || null;
    _currentOpts    = opts || {};

    if (!_currentBlocks.length) {
        body.innerHTML = '<p class="pf-empty-state">Kein Bericht ge\u00f6ffnet.</p>';
        return;
    }

    // Alle Bloecke rendern
    body.innerHTML = _renderAllBlocks(_currentBlocks, _currentBlockId);

    // Event-Listener binden
    _bindFormEvents(body, _currentBlocks, opts);

    // Fokussierten Block sichtbar machen (Blur und Scroll)
    _applyFocusBlur(body, _currentBlockId);
    _scrollToFocusedBlock(body, _currentBlockId);

    // Pulsanimation auf Editor-Block
    if (_currentBlockId && typeof window.CommentThread?._pulseEditorBlock === 'function') {
        window.CommentThread._pulseEditorBlock(_currentBlockId);
    }
}

/**
 * Verschiebt den Formular-Fokus auf blockId (z.B. bei Tab-Navigation
 * zwischen Bloecken oder Klick auf geblurtes Feld).
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
 */
function focusBlock(blockId) {
    const body = document.getElementById('accordion-body-form');
    if (!body) return;

    // Bug-Fix Build 117 (2.14): Alten blauen Rahmen entfernen BEVOR
    // _currentBlockId ueberschrieben wird. Vorher wurde _clearEditorBlockPulse
    // mit dem neuen blockId aufgerufen (weil _currentBlockId bereits gesetzt war),
    // sodass der alte Rahmen dauerhaft sichtbar blieb.
    // Beleg: Bugfix Build 117, Projektgespraech 2026-05-08
    if (_currentBlockId && _currentBlockId !== blockId) {
        window.CommentThread?._clearEditorBlockPulse?.(_currentBlockId);
    }

    _currentBlockId = blockId;
    _applyFocusBlur(body, blockId);
    _scrollToFocusedBlock(body, blockId);

    // Pulsanimation auf Editor-Block (nur wenn neuer Block gesetzt)
    if (blockId && typeof window.CommentThread?._pulseEditorBlock === 'function') {
        window.CommentThread._pulseEditorBlock(blockId);
    }
}

// ---------------------------------------------------------------------------
// HTML-Renderer
// ---------------------------------------------------------------------------

/**
 * Rendert alle Block-Gruppen als HTML-String.
 * @param {Array}  blocks
 * @param {string} focusedBlockId
 * @returns {string}
 */
function _renderAllBlocks(blocks, focusedBlockId) {
    if (!blocks.length) {
        return '<p class="pf-empty-state">Keine Bl\u00f6cke im Bericht.</p>';
    }

    return blocks.map(block => _renderBlockGroup(block, focusedBlockId)).join('');
}

/**
 * Rendert eine Block-Gruppe (eine Block-Karte mit allen m:/o:-Feldern).
 * @param {Object} block
 * @param {string} focusedBlockId
 * @returns {string}
 */
function _renderBlockGroup(block, focusedBlockId) {
    const chips  = window.PlaceholderChips;
    const isFocused = block.block_id === focusedBlockId;

    // Rohtext aus block_data extrahieren
    let rawText = '';
    try {
        const data = typeof block.block_data === 'string'
            ? JSON.parse(block.block_data)
            : (block.block_data || {});
        rawText = data.text || '';
    } catch (_) {}

    // Felder extrahieren (m: und o: — a: wird nicht angezeigt)
    const mFields = chips ? chips.extractFields(rawText, 'm').map(f => ({ ...f, type: 'm' })) : [];
    const oFields = chips ? chips.extractFields(rawText, 'o').map(f => ({ ...f, type: 'o' })) : [];
    const fields  = [...mFields, ...oFields];

    // Aktuelle Werte aus placeholder_values_json
    let values = {};
    try {
        if (block.placeholder_values_json) {
            values = JSON.parse(block.placeholder_values_json);
        }
    } catch (_) {}

    const focusedCls = isFocused ? ' pf-block-group--focused' : ' pf-block-group--blurred';

    if (!fields.length) {
        return `<div class="pf-block-group${focusedCls}"
                     data-block-id="${_esc(block.block_id)}"
                     aria-label="Block ohne Platzhalter">
            <div class="pf-block-empty">Keine Platzhalter</div>
        </div>`;
    }

    const fieldsHtml = fields.map(f => _renderField(f, values, block.block_id)).join('');

    return `<div class="pf-block-group${focusedCls}"
                 data-block-id="${_esc(block.block_id)}"
                 aria-label="Platzhalter-Felder f\u00fcr Block ${_esc(block.author || '')}">
        ${fieldsHtml}
    </div>`;
}

/**
 * Rendert ein einzelnes Eingabefeld.
 * @param {Object} field   -- { name, defaultVal, description, b64regex, type }
 * @param {Object} values  -- aktuelle Werte
 * @param {string} blockId
 * @returns {string}
 */
function _renderField(field, values, blockId) {
    // Bug 2.42 Fix Build 136: Nur tatsaechlich gespeicherte Werte als value.
    // field.defaultVal darf NICHT als value eingesetzt werden — das wuerde
    // den Beschreibungstext als Eingabe-Inhalt erscheinen lassen.
    // defaultVal kommt ausschliesslich als placeholder-Attribut zum Einsatz
    // (HTML-Platzhaltermechanismus: erscheint grau wenn Feld leer, verschwindet
    // bei Eingabe — kein CSS erforderlich, native Browser-Funktionalitaet).
    // Beleg: Bugfix Build 136, Projektgespraech 2026-05-09
    const savedVal  = values[field.name] ?? null;
    const val       = savedVal !== null ? savedVal : '';
    const isM       = field.type === 'm';
    const label     = _esc(field.description || field.name);
    const inputId   = `pf-input-${_esc(blockId)}-${_esc(field.name)}`;
    const reqMark   = isM ? ' <span class="pf-required" aria-hidden="true">*</span>' : '';
    const hasVal    = String(val).trim() !== '';

    // Validierungsstatus
    let validCls = '';
    if (hasVal && field.b64regex) {
        const pattern = _b64DecodeUnicode(field.b64regex);
        if (pattern !== null) {
            try {
                validCls = new RegExp(pattern).test(val) ? ' pf-input--valid' : ' pf-input--warn';
            } catch (_) {}
        }
    } else if (hasVal) {
        validCls = ' pf-input--valid';
    }

    return `<div class="pf-field-group"
                 data-block-id="${_esc(blockId)}"
                 data-field-name="${_esc(field.name)}"
                 data-field-type="${_esc(field.type)}">
        <label class="pf-label" for="${inputId}">
            ${label}${reqMark}
        </label>
        <div class="pf-input-wrap">
            <input class="pf-input${validCls}"
                   id="${inputId}"
                   type="text"
                   value="${_esc(val)}"
                   data-block-id="${_esc(blockId)}"
                   data-field-name="${_esc(field.name)}"
                   data-field-type="${_esc(field.type)}"
                   ${field.b64regex ? `data-b64regex="${_esc(field.b64regex)}"` : ''}
                   autocomplete="off"
                   placeholder="${_esc(field.defaultVal || field.description || '')}"
                   aria-required="${isM ? 'true' : 'false'}"
                   aria-label="${label}${isM ? ' (Pflichtfeld)' : ''}">
        </div>
        <div class="pf-field-error" id="pf-err-${_esc(blockId)}-${_esc(field.name)}"
             role="alert"></div>
        ${field.description && field.description !== field.name
            ? `<div class="pf-field-hint">${_esc(field.description)}</div>`
            : ''}
    </div>`;
}

// ---------------------------------------------------------------------------
// Event-Listener
// ---------------------------------------------------------------------------

/**
 * Verdrahtet alle Event-Listener fuer das Sidebar-Formular.
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
 */
function _bindFormEvents(body, blocks, opts) {
    // Klick auf eine Block-Gruppe: Fokus setzen
    body.querySelectorAll('.pf-block-group').forEach(group => {
        group.addEventListener('click', () => {
            const bid = group.dataset.blockId;
            if (bid && bid !== _currentBlockId) {
                _currentBlockId = bid;
                focusBlock(bid);
            }
        });
    });

    // Klick auf ein Eingabefeld: Fokus direkt auf diesem Block setzen
    body.querySelectorAll('.pf-input').forEach(input => {
        input.addEventListener('focus', () => {
            const bid = input.dataset.blockId;
            if (bid && bid !== _currentBlockId) {
                _currentBlockId = bid;
                _applyFocusBlur(body, bid);
                _scrollToFocusedBlock(body, bid);
                if (typeof window.CommentThread?._pulseEditorBlock === 'function') {
                    window.CommentThread._pulseEditorBlock(bid);
                }
            }
            // Visuelles Feedback: grüner/oranger Rahmen live waehrend Eingabe
        });

        // Eingabe: Validierung + debounced Save
        input.addEventListener('input', () => {
            _validateFieldLive(input);
            _scheduleFieldSave(input, opts);
        });

        // Tab-Navigation zwischen Block-Gruppen: Blur wandert mit
        input.addEventListener('keydown', e => {
            if (e.key === 'Tab') {
                // Naechste/vorherige Gruppe bestimmen — wird nach dem
                // DOM-Focus-Wechsel von "focus"-Handler verarbeitet.
                // Kein explizites Handling noetig.
            }
        });
    });
}

// ---------------------------------------------------------------------------
// Validierung
// ---------------------------------------------------------------------------

/**
 * Live-Validierung eines Eingabefeldes (waehrend Eingabe).
 * Pflichtfeld-Check + RegExp-Warnung (kein Block).
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
 */
function _validateFieldLive(input) {
    const errEl = document.getElementById(
        `pf-err-${input.dataset.blockId}-${input.dataset.fieldName}`
    );
    const val  = input.value.trim();
    const isM  = input.dataset.fieldType === 'm';
    const b64re = input.dataset.b64regex;

    // Klassen-Reset
    input.classList.remove('pf-input--valid', 'pf-input--warn', 'pf-input--error');
    if (errEl) errEl.textContent = '';

    if (!val) {
        if (isM && errEl) errEl.textContent = 'Pflichtfeld — bitte ausf\u00fcllen.';
        return;
    }

    // RegExp-Validierung (OP-B6-5, Warnung)
    if (b64re) {
        const pattern = _b64DecodeUnicode(b64re);
        if (pattern !== null) {
            try {
                const ok = new RegExp(pattern).test(val);
                if (!ok) {
                    input.classList.add('pf-input--warn');
                    if (errEl) errEl.textContent = 'Eingabe entspricht nicht dem erwarteten Format.';
                    return;
                }
            } catch (_) {}
        }
    }

    // Alles OK
    input.classList.add('pf-input--valid');
}

// ---------------------------------------------------------------------------
// Auto-Save (debounced)
// ---------------------------------------------------------------------------

/**
 * Startet einen debounced Save fuer ein Eingabefeld.
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
 */
function _scheduleFieldSave(input, opts) {
    if (!opts?.onSave) return;
    const key = `${input.dataset.blockId}:${input.dataset.fieldName}`;
    clearTimeout(_saveTimers[key]);
    _saveTimers[key] = setTimeout(() => {
        _saveField(input, opts);
        delete _saveTimers[key];
    }, FIELD_SAVE_DEBOUNCE_MS);
}

async function _saveField(input, opts) {
    if (!opts?.onSave) return;
    const blockId = input.dataset.blockId;
    const name    = input.dataset.fieldName;
    const val     = input.value;
    try {
        await opts.onSave(blockId, name, val);
    } catch (err) {
        console.warn('placeholder_wizard.js: Feld-Save fehlgeschlagen:', name, err);
    }
}

// ---------------------------------------------------------------------------
// Blur-Effekt und Scroll-Zentrierung
// ---------------------------------------------------------------------------

/**
 * Setzt den Blur-Effekt: fokussierter Block scharf, alle anderen geblurt.
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
 */
function _applyFocusBlur(body, focusedBlockId) {
    body.querySelectorAll('.pf-block-group').forEach(group => {
        const isFocused = group.dataset.blockId === focusedBlockId;
        group.classList.toggle('pf-block-group--focused', isFocused);
        group.classList.toggle('pf-block-group--blurred', !isFocused);
    });
}

/**
 * Scrollt den fokussierten Block in die mittleren 80% des Viewports.
 * Nur wenn der Block ausserhalb dieses Bereichs liegt.
 * Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
 */
function _scrollToFocusedBlock(body, focusedBlockId) {
    if (!focusedBlockId) return;
    const group = body.querySelector(`.pf-block-group[data-block-id="${focusedBlockId}"]`);
    if (!group) return;

    const containerRect = body.getBoundingClientRect();
    const groupRect     = group.getBoundingClientRect();
    const margin        = containerRect.height * 0.1;   // 10% oben/unten = 80% Mitte
    const topBound      = containerRect.top + margin;
    const botBound      = containerRect.bottom - margin;

    // Nur scrollen wenn ausserhalb der 80%-Zone
    if (groupRect.top < topBound || groupRect.bottom > botBound) {
        group.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// ---------------------------------------------------------------------------
// Rueckwaerts-Kompatibilitaet: open() / openAtField() / close()
// Phase 5 ruft open() nicht direkt auf, aber _bindChipDoubleClick() nutzt
// openAtField(). Diese Stubs ersetzen den alten Modal-Code.
// Beleg: Build 104, Rueckwaerts-Kompatibilitaet
// ---------------------------------------------------------------------------

/**
 * Oeffnet das Sidebar-Formular beim Schritt, der fieldName enthaelt.
 * Rueckwaerts-Kompatibilitaet fuer _bindChipDoubleClick (Phase 5).
 * Beleg: Bauplan B6 v0.5 §4.6 (Doppelklick-Handler)
 */
function openAtField(options, fieldName) {
    // Formular-Akkordeon oeffnen
    const sidebar = document.getElementById('support-sidebar');
    const formSection = sidebar?.querySelector('[data-accordion="form"]');
    if (formSection && typeof window.openAccordionSection === 'function') {
        window.openAccordionSection(formSection);
    }

    // Bug 2.42 Fix Build 135: onSave aus Options in _currentOpts setzen damit
    // Feldaenderungen nach dem Chip-Doppelklick korrekt gespeichert werden.
    // Vorher war onSave = () => {} (leer), Werte wurden nicht gespeichert.
    // Beleg: Bugfix Build 135, Projektgespraech 2026-05-09
    if (typeof options?.onSave === 'function') {
        _currentOpts = { ..._currentOpts, onSave: options.onSave };
    }

    // Fokus auf den Block setzen der das Feld enthaelt.
    // focusBlock() rendert das Formular neu — Input-DOM erst danach vorhanden.
    // Bug IndexSizeError Fix Build 139: _pulseEditorBlock ruft caret.setToBlock
    // auf, das intern getRangeAt(0) aufruft. Wenn der Editor keinen Fokus hat
    // (Formular ist gerade aktiv), gibt es keine Range → IndexSizeError.
    // Fix: _pulseEditorBlock temporaer deaktivieren waehrend openAtField laeuft.
    // Beleg: Bugfix Build 139, Projektgespraech 2026-05-09
    if (options?.blockId) {
        const savedPulse = window.CommentThread?._pulseEditorBlock;
        if (window.CommentThread) {
            window.CommentThread._pulseEditorBlock = () => {};
        }
        focusBlock(options.blockId);
        if (window.CommentThread && savedPulse) {
            window.CommentThread._pulseEditorBlock = savedPulse;
        }
    }

    // Bug 2.42 Fix Build 135: _focusDelay aus Options respektieren (Standard 100ms).
    // focusBlock rendert das Formular asynchron; bei 100ms war der Input-DOM
    // noch nicht bereit. 250ms geben genug Zeit fuer den Re-Render.
    // Beleg: Bugfix Build 135, Projektgespraech 2026-05-09
    const focusDelay = (options?._focusDelay ?? 100);

    // Fokussiertes Feld durch scrollen in den Viewport bringen
    if (fieldName && options?.blockId) {
        const inputId = `pf-input-${options.blockId}-${fieldName}`;
        setTimeout(() => {
            const input = document.getElementById(inputId);
            if (input) {
                input.focus();
                input.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }, focusDelay);
    }
}

/**
 * Stub: open() ist in Phase 6 kein Modal mehr.
 * Oeffnet das Formular-Akkordeon fuer den angegeben Block.
 */
function open(options) {
    if (options?.blockId) {
        openAtField(options, null);
    }
}

/** Stub: close() — kein Modal in Phase 6. */
function close() {
    // Nichts zu tun (kein Modal mehr)
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

_dbg('placeholder_wizard.js: window.PlaceholderWizard exportiert');
window.PlaceholderWizard = {
    // Phase 6 Haupt-API
    showPlaceholderForm,
    focusBlock,
    // Build 117: _currentBlockId fuer externen Zugriff (Cleanup blauer Rahmen)
    // Beleg: Bugfix Build 117, Projektgespraech 2026-05-08
    getCurrentBlockId: () => _currentBlockId,
    // Unveraenderte Kern-Funktionen (Tests und Phase 5)
    buildSteps,
    stepIndexForField,
    // Rueckwaerts-Kompatibilitaet
    open,
    openAtField,
    close,
};

})();
