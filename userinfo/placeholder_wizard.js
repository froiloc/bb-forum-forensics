/**
 * userinfo/placeholder_wizard.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Platzhalter-Wizard fuer Fenster 3 (Phase 5, Bauplan B6 v0.3 §4.5).
 *
 *   Fuehrt den Ermittler schrittweise durch das Ausfuellen aller m:- und
 *   o:-Felder eines Paragraphen. Oeffnet beim Einfuegen eines Moduls (Phase 6)
 *   und bei Doppelklick auf einen Chip im fertigen Block.
 *
 *   Grundprinzip (§4.5):
 *     - 2-3 Felder pro Schritt (alle m:-Felder in Schritten a 2-3,
 *       o:-Felder im letzten Schritt je 2-3)
 *     - Vor/Zurueck-Navigation ohne Datenverlust
 *     - {{a:...}}-Werte erscheinen nicht im Wizard
 *     - Pflichtfeld-Validierung direkt am Feld (kein generischer Alert)
 *     - "Weiter" und "In Bericht uebernehmen" deaktiviert solange m: leer
 *     - Doppelklick auf Chip oeffnet Wizard beim richtigen Schritt
 *     - Eingaben werden als JSON in placeholder_values_json gespeichert
 *
 *   Abhaengigkeiten:
 *     placeholder_chips.js (window.PlaceholderChips) muss VOR diesem Skript
 *     geladen sein.
 *
 * Exports:
 *   window.PlaceholderWizard.open(options)
 *     Oeffnet den Wizard.
 *     options: {
 *       blockId:     string,   -- Paragraph-ID
 *       moduleTitle: string,   -- Anzeigename im Wizard-Header
 *       bodyText:    string,   -- Rohtext des Paragraphen mit Platzhaltern
 *       values:      object,   -- aktuelle {name: value}-Werte
 *       onSave:      async function(blockId, newValues)
 *     }
 *   window.PlaceholderWizard.openAtField(options, fieldName)
 *     Oeffnet den Wizard direkt beim Schritt der das Feld fieldName enthaelt.
 *   window.PlaceholderWizard.close()
 *     Schliesst den Wizard (z.B. bei Lock-Verlust).
 *   window.PlaceholderWizard.buildSteps(bodyText)
 *     Gibt die Schritt-Struktur zurueck (fuer Tests).
 *
 * Version: v0.1.0 · Build: 092 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §4.5, Ausdefinitionsgespraech 2026-05-05
 */

'use strict';

// ---------------------------------------------------------------------------
// Konstanten
// ---------------------------------------------------------------------------

/** Maximale Anzahl Felder pro Wizard-Schritt. */
const FIELDS_PER_STEP = 3;

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

// ---------------------------------------------------------------------------
// Schritt-Aufbau
// ---------------------------------------------------------------------------

/**
 * Teilt die Felder eines Paragraphen in Wizard-Schritte auf.
 *
 * Reihenfolge: alle m:-Felder zuerst, dann alle o:-Felder.
 * Jeder Schritt enthaelt maximal FIELDS_PER_STEP Felder.
 * Leere Feldlisten erzeugen einen einzigen leeren Schritt.
 *
 * Jedes Feld-Objekt:
 *   { name, defaultVal, description, b64regex, type: 'm'|'o' }
 *
 * Beleg: Bauplan B6 v0.3 §4.5 (2-3 Felder pro Schritt)
 *
 * @param {string} bodyText
 * @returns {Array<Array>}  Array von Schritten, jeder Schritt ein Array von Feldern
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
 *
 * @param {Array<Array>} steps
 * @param {string} fieldName
 * @returns {number}
 */
function stepIndexForField(steps, fieldName) {
    for (let i = 0; i < steps.length; i++) {
        if (steps[i].some(f => f.name === fieldName)) return i;
    }
    return 0;
}

// ---------------------------------------------------------------------------
// DOM-Aufbau
// ---------------------------------------------------------------------------

/**
 * Erstellt das Modal-Overlay und gibt es zurueck.
 * Das Modal wird dem document.body angehaengt.
 * Beleg: Bauplan B6 v0.3 §4.5 (Dialog-Mockup)
 */
function _createModal() {
    const overlay = document.createElement('div');
    overlay.id = 'pw-overlay';
    overlay.className = 'pw-overlay';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-labelledby', 'pw-title');
    overlay.innerHTML = `
        <div class="pw-dialog" id="pw-dialog">
            <div class="pw-header">
                <span class="pw-header-title" id="pw-title"></span>
                <span class="pw-header-step" id="pw-step-indicator"></span>
                <button class="pw-close-btn" id="pw-btn-close"
                    title="Abbrechen" aria-label="Wizard schliessen">\u2715</button>
            </div>
            <div class="pw-body" id="pw-body"></div>
            <div class="pw-footer">
                <button class="pw-btn" id="pw-btn-cancel">\u2715 Abbrechen</button>
                <span class="pw-footer-spacer"></span>
                <button class="pw-btn" id="pw-btn-back" disabled>\u25c4 Zur\u00fcck</button>
                <button class="pw-btn pw-btn-primary" id="pw-btn-next">Weiter \u25ba</button>
                <button class="pw-btn pw-btn-primary" id="pw-btn-save" style="display:none">
                    \u2714 In Bericht \u00fcbernehmen
                </button>
            </div>
        </div>`;
    document.body.appendChild(overlay);
    return overlay;
}

/**
 * Rendert den Inhalt eines Schrittes in #pw-body.
 *
 * @param {Array}  fields     -- Felder des aktuellen Schrittes
 * @param {Object} values     -- aktuell gespeicherte Werte {name: value}
 * @param {number} stepIdx    -- 0-basierter Schritt-Index
 * @param {number} totalSteps -- Gesamtanzahl Schritte
 */
function _renderStep(fields, values, stepIdx, totalSteps) {
    const body = document.getElementById('pw-body');
    if (!body) return;

    if (!fields.length) {
        body.innerHTML = '<p class="pw-empty">Keine Felder zum Ausf\u00fcllen vorhanden.</p>';
        return;
    }

    body.innerHTML = fields.map(f => {
        const val     = values[f.name] ?? f.defaultVal ?? '';
        const isM     = f.type === 'm';
        const label   = _esc(f.description || f.name);
        const inputId = `pw-field-${_esc(f.name)}`;
        const reqMark = isM ? ' <span class="pw-required" aria-hidden="true">*</span>' : '';
        const optMark = !isM ? ' <span class="pw-optional">(optional)</span>' : '';

        return `
            <div class="pw-field-group" data-field-name="${_esc(f.name)}"
                 data-field-type="${_esc(f.type)}">
                <label class="pw-label" for="${inputId}">
                    ${label}${reqMark}${optMark}
                </label>
                <div class="pw-input-wrap">
                    <input class="pw-input" id="${inputId}"
                           type="text"
                           name="${_esc(f.name)}"
                           value="${_esc(val)}"
                           data-field-name="${_esc(f.name)}"
                           data-field-type="${_esc(f.type)}"
                           autocomplete="off"
                           placeholder="${_esc(val || f.defaultVal || '')}"
                           ${f.b64regex ? `data-b64regex="${_esc(f.b64regex)}"` : ''}>
                    ${!isM ? `<button class="pw-skip-btn"
                        data-field-name="${_esc(f.name)}"
                        title="Dieses optionale Feld \u00fcberspringen">
                        \u00dcberspringen</button>` : ''}
                </div>
                <div class="pw-field-error" id="pw-err-${_esc(f.name)}" role="alert"></div>
            </div>`;
    }).join('');

    // Step-Indikator
    const indicator = document.getElementById('pw-step-indicator');
    if (indicator) {
        indicator.textContent = `Schritt ${stepIdx + 1} von ${totalSteps}`;
    }

    // Zurueck-Button
    const btnBack = document.getElementById('pw-btn-back');
    if (btnBack) btnBack.disabled = stepIdx === 0;

    // Weiter / Speichern
    const btnNext = document.getElementById('pw-btn-next');
    const btnSave = document.getElementById('pw-btn-save');
    const isLast  = stepIdx === totalSteps - 1;
    if (btnNext) btnNext.style.display = isLast ? 'none' : '';
    if (btnSave) btnSave.style.display = isLast ? '' : 'none';

    // Skip-Buttons verdrahten
    body.querySelectorAll('.pw-skip-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const input = body.querySelector(`input[data-field-name="${btn.dataset.fieldName}"]`);
            if (input) { input.value = ''; }
        });
    });

    // Ersten Input fokussieren
    const firstInput = body.querySelector('.pw-input');
    firstInput?.focus();
}

// ---------------------------------------------------------------------------
// Validierung
// ---------------------------------------------------------------------------

/**
 * Prueft ob alle m:-Felder des aktuellen Schrittes ausgefuellt sind.
 * Zeigt Fehler direkt am Feld an. Gibt true zurueck wenn alles OK.
 * Beleg: Bauplan B6 v0.3 §4.5 (Fehlermeldung direkt am Feld)
 *
 * Optionaler b64regex-Check (OP-B6-5): Wenn das Feld einen b64regex-Wert hat,
 * wird der Regex dekodiert und gegen die Eingabe geprueft. Zeigt Warnung (kein Block).
 */
function _validateStep(body) {
    if (!body) return true;
    let valid = true;

    body.querySelectorAll('.pw-input').forEach(input => {
        const errEl = document.getElementById(`pw-err-${input.dataset.fieldName}`);
        if (!errEl) return;

        const isM    = input.dataset.fieldType === 'm';
        const val    = input.value.trim();
        const b64re  = input.dataset.b64regex;

        errEl.textContent = '';
        input.classList.remove('pw-input-error', 'pw-input-warn');

        // Pflichtfeld-Pruefung
        if (isM && !val) {
            errEl.textContent = 'Dieses Feld ist erforderlich.';
            input.classList.add('pw-input-error');
            valid = false;
            return;
        }

        // Validierungs-Regex (OP-B6-5) — nur Warnung, kein Block
        if (b64re && val) {
            try {
                const pattern = _b64DecodeUnicode(b64re);
                const re      = new RegExp(pattern);
                if (!re.test(val)) {
                    errEl.textContent = 'Eingabe entspricht nicht dem erwarteten Format.';
                    input.classList.add('pw-input-warn');
                    // Kein valid = false: Warnung blockiert nicht
                }
            } catch (_) { /* ungueltige Regex ignorieren */ }
        }
    });

    return valid;
}

/**
 * Liest alle Eingabewerte des aktuellen Schrittes aus.
 * @returns {Object} {fieldName: value}
 */
function _collectStepValues(body) {
    const result = {};
    if (!body) return result;
    body.querySelectorAll('.pw-input').forEach(input => {
        result[input.dataset.fieldName] = input.value;
    });
    return result;
}

// ---------------------------------------------------------------------------
// Base64-Hilfsfunktionen (OP-B6-5)
// Quelle: Projektgespraech 2026-05-05 (bereitgestellt durch Entwickler)
// ---------------------------------------------------------------------------

function _b64DecodeUnicode(str) {
    return decodeURIComponent(atob(str).split('').map(c =>
        '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)
    ).join(''));
}

// ---------------------------------------------------------------------------
// Wizard-Zustand (Modul-intern)
// ---------------------------------------------------------------------------

let _overlay   = null;    // aktuelles Modal-Overlay
let _opts      = null;    // aktuelle open()-Optionen
let _steps     = [];      // Schritt-Array
let _stepIdx   = 0;       // aktueller Schritt-Index
let _values    = {};      // gesammelte Werte {name: value}

// ---------------------------------------------------------------------------
// Oeffentliche API
// ---------------------------------------------------------------------------

/**
 * Oeffnet den Wizard.
 *
 * @param {Object} options
 *   blockId:     string
 *   moduleTitle: string
 *   bodyText:    string
 *   values:      object   -- Vorbelgung {name: value}
 *   onSave:      async function(blockId, newValues)
 */
function open(options) {
    // Vorhandenes Modal entfernen
    close();

    _opts    = options;
    _steps   = buildSteps(options.bodyText || '');
    _stepIdx = 0;
    _values  = { ...(options.values || {}) };

    _overlay = _createModal();

    // Titel setzen
    const titleEl = document.getElementById('pw-title');
    if (titleEl) {
        titleEl.textContent = `Modul ausf\u00fcllen: \u201e${options.moduleTitle || ''}\u201c`;
    }

    // Schritt rendern
    _renderStep(_steps[_stepIdx] || [], _values, _stepIdx, _steps.length);

    // Schliessen-Buttons
    document.getElementById('pw-btn-close')?.addEventListener('click', close);
    document.getElementById('pw-btn-cancel')?.addEventListener('click', close);

    // Overlay-Klick schliesst nicht (forensische Daten duerfen nicht versehentlich verloren gehen)

    // Escape-Taste schliesst
    _overlay._escHandler = e => { if (e.key === 'Escape') close(); };
    document.addEventListener('keydown', _overlay._escHandler);

    // Weiter
    document.getElementById('pw-btn-next')?.addEventListener('click', _onNext);

    // Zurueck
    document.getElementById('pw-btn-back')?.addEventListener('click', _onBack);

    // Speichern
    document.getElementById('pw-btn-save')?.addEventListener('click', _onSave);
}

/**
 * Oeffnet den Wizard direkt beim Schritt, der das Feld fieldName enthaelt.
 * Beleg: Bauplan B6 v0.3 §4.5 (Doppelklick-Nachbearbeitung)
 */
function openAtField(options, fieldName) {
    open(options);
    if (!fieldName) return;
    const target = stepIndexForField(_steps, fieldName);
    if (target > 0) {
        // Schritte ohne Validierung vorspulen (Werte bleiben erhalten)
        _stepIdx = target;
        _renderStep(_steps[_stepIdx] || [], _values, _stepIdx, _steps.length);
    }
}

/**
 * Schliesst den Wizard und entfernt das Modal aus dem DOM.
 */
function close() {
    if (_overlay) {
        if (_overlay._escHandler) {
            document.removeEventListener('keydown', _overlay._escHandler);
        }
        _overlay.remove();
        _overlay = null;
    }
    _opts = _steps = null;
    _stepIdx = 0;
    _values  = {};
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

function _onNext() {
    const body = document.getElementById('pw-body');
    if (!_validateStep(body)) return;

    // Werte des aktuellen Schrittes sichern
    Object.assign(_values, _collectStepValues(body));

    _stepIdx++;
    _renderStep(_steps[_stepIdx] || [], _values, _stepIdx, _steps.length);
}

function _onBack() {
    const body = document.getElementById('pw-body');
    // Aktuelle Werte sichern (auch ohne Validierung — kein Verlust beim Zurueck)
    Object.assign(_values, _collectStepValues(body));

    _stepIdx = Math.max(0, _stepIdx - 1);
    _renderStep(_steps[_stepIdx] || [], _values, _stepIdx, _steps.length);
}

async function _onSave() {
    const body = document.getElementById('pw-body');
    if (!_validateStep(body)) return;

    // Letzten Schritt sichern
    Object.assign(_values, _collectStepValues(body));

    const btnSave = document.getElementById('pw-btn-save');
    if (btnSave) {
        btnSave.disabled = true;
        btnSave.textContent = 'Wird gespeichert\u2026';
    }

    try {
        await _opts.onSave(_opts.blockId, { ..._values });
        close();
    } catch (err) {
        if (btnSave) {
            btnSave.disabled = false;
            btnSave.textContent = '\u2714 In Bericht \u00fcbernehmen';
        }
        const body2 = document.getElementById('pw-body');
        if (body2) {
            const errDiv = document.createElement('div');
            errDiv.className = 'pw-save-error';
            errDiv.textContent = `Speichern fehlgeschlagen: ${err}`;
            body2.prepend(errDiv);
        }
    }
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

window.PlaceholderWizard = {
    open,
    openAtField,
    close,
    buildSteps,
    stepIndexForField,
};
