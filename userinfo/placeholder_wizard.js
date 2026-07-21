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
 *   Build 492 (Platzhalter-Neuordnung, Slice 3, Teil 2): Stammvater/Klon.
 *     Verdrahtung der reinen Verknuepfungslogik aus placeholder_links.js
 *     (window.PlaceholderLinks, Build 491) in das Sidebar-Formular:
 *     - _buildLinkState() baut beim Rendern den Verknuepfungszustand ueber
 *       ALLE Bloecke des Vermerks (gleichnamige m/o-Felder).
 *     - _renderField() zeigt Klon-Felder mit dem Stammvater-Wert (displayValue)
 *       und markiert jedes Feld optisch mit seiner Rolle (Stammvater/Klon,
 *       Badge + linker Rahmen).
 *     - _propagateLinks() zieht bei jeder Eingabe die Klone LIVE nach
 *       (applyInput -> Klon-Inputs setzen, validieren, speichern) und
 *       aktualisiert die Rollen-Markierung.
 *     ABGRENZUNG: Die dauerhafte Persistenz der explizit/Klon-Unterscheidung
 *     (Wieder-Anhaengen nach Neuladen, 'abgeleitet'-Marker) beruehrt
 *     placeholder_values_json in evidence_<uid>.db und steht unter
 *     Migrationsvorbehalt -> Folge-Build. In DIESEM Build werden Klon-Werte
 *     ueber den normalen onSave-Pfad mitgespeichert (Bericht rendert korrekt);
 *     die Unterscheidung lebt in der Sitzung im _linkState.
 *     Beleg: mc-Wunsch 2026-07-20/21, Bauplan_Platzhalter_DB §Slice3.
 *
 *   Build 494 (Platzhalter-Neuordnung, Slice 3, Teil 3): m/o-Felder werden
 *     gegen die DB-Definition (window.PlaceholderDefs, validation_type
 *     regex/list/like) geprueft — die DB ist Autoritaet fuer bekannte IDs
 *     (Build 489). Fehlt eine DB-Definition, greift weiterhin das 5. Token-Feld
 *     (rule:-Katalog/Base64). _fieldCheck() buendelt die Vorrang-Logik;
 *     _defHint() zeigt zulaessige Werte (list) bzw. das Muster (like).
 *     Definitionen werden beim Form-Oeffnen einmalig geladen und gecacht;
 *     befuellte Felder werden nach dem Laden nachvalidiert.
 *
 * Version: v0.8.494 · Build: 494 · 2026-07-21
 * Beleg: Bauplan B6 v0.5 §4.4.3; Bauplan Platzhalter_DB §2.3 (DB-Autoritaet).
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

// Build 492: Stammvater/Klon-Verknuepfungszustand ueber ALLE Bloecke des
// Vermerks. Wird bei jedem showPlaceholderForm() neu aus den placeholder_
// values_json der Bloecke aufgebaut und bei jeder Eingabe fortgeschrieben
// (reine Logik in window.PlaceholderLinks, Build 491). null wenn die
// Verknuepfungsbibliothek nicht geladen ist (defensive Degradation: dann
// verhaelt sich das Formular exakt wie vor 492).
let _linkState       = null;

// ---------------------------------------------------------------------------
// Build 492: Stammvater/Klon — Zustandsaufbau und Rollen-Markierung
// ---------------------------------------------------------------------------

/**
 * Baut den Verknuepfungszustand (Stammvater/Klon) ueber alle Bloecke.
 *
 * Die Feld-Reihenfolge MUSS der sichtbaren Reihenfolge entsprechen (Block-
 * reihenfolge, je Block erst m:, dann o:), weil die Erst-Stammvater-Wahl in
 * placeholder_links.createState() in Dokumentreihenfolge erfolgt — nur so
 * stimmt die im Formular markierte Rolle mit der Logik ueberein.
 * Ein Feld gilt als EXPLIZIT befuellt, wenn im placeholder_values_json des
 * eigenen Blocks ein nicht-leerer Wert steht.
 *
 * @param {Array} blocks
 * @returns {object|null} PlaceholderLinks-State oder null
 */
function _buildLinkState(blocks) {
    if (!window.PlaceholderLinks || !window.PlaceholderChips) return null;
    const chips = window.PlaceholderChips;
    const fieldRefs      = [];
    const explicitValues = {};

    for (const block of (blocks || [])) {
        let blockData = {};
        try {
            blockData = typeof block.block_data === 'string'
                ? JSON.parse(block.block_data)
                : (block.block_data || {});
        } catch (_) {}

        let values = {};
        try {
            if (block.placeholder_values_json) {
                values = JSON.parse(block.placeholder_values_json);
            }
        } catch (_) {}

        const mF = chips.extractFieldsFromBlockData(blockData, 'm').map(f => ({ ...f, type: 'm' }));
        const oF = chips.extractFieldsFromBlockData(blockData, 'o').map(f => ({ ...f, type: 'o' }));
        for (const f of [...mF, ...oF]) {
            fieldRefs.push({ blockId: block.block_id, name: f.name, type: f.type });
            const v = values[f.name];
            if (v != null && String(v).trim() !== '') {
                const k = window.PlaceholderLinks.fieldKey(block.block_id, f.name);
                explicitValues[k] = String(v);
            }
        }
    }

    return window.PlaceholderLinks.createState(fieldRefs, explicitValues);
}

/**
 * Menschliche Beschriftung fuer die Feldrolle (leer = keine Markierung).
 * @param {string} role
 * @returns {string}
 */
function _roleLabel(role) {
    if (role === 'stammvater') return 'Stammvater';
    if (role === 'klon')       return 'Klon';
    return '';   // 'eigenstaendig' und 'leer' bleiben unmarkiert
}

/**
 * Findet die Feld-Gruppe (.pf-field-group) eines Feldes ueber die
 * data-Attribute — ohne CSS-Selektor-Injektion (blockId/name koennen
 * Sonderzeichen enthalten).
 * @returns {HTMLElement|null}
 */
function _findFieldGroup(blockId, name) {
    const groups = document.querySelectorAll('.pf-field-group');
    for (const g of groups) {
        if (g.dataset.blockId === blockId && g.dataset.fieldName === name) return g;
    }
    return null;
}

/**
 * Setzt die Rollen-Markierung (CSS-Klasse + Badge) einer Feld-Gruppe LIVE.
 * @param {string} blockId
 * @param {string} name
 * @param {string} role  -- 'stammvater'|'klon'|'eigenstaendig'|'leer'
 */
function _applyRoleToGroup(blockId, name, role) {
    const grp = _findFieldGroup(blockId, name);
    if (!grp) return;

    grp.classList.remove('pf-role--stammvater', 'pf-role--klon',
                         'pf-role--eigenstaendig', 'pf-role--leer');
    grp.classList.add('pf-role--' + role);
    grp.setAttribute('data-role', role);

    const label = grp.querySelector('.pf-label');
    if (!label) return;
    let badge = label.querySelector('.pf-role-badge');
    const txt = _roleLabel(role);
    if (!txt) {
        if (badge) badge.remove();
        return;
    }
    if (!badge) {
        badge = document.createElement('span');
        badge.className = 'pf-role-badge';
        label.appendChild(badge);
    }
    badge.textContent = txt;
    badge.classList.remove('pf-role-badge--stammvater', 'pf-role-badge--klon');
    badge.classList.add('pf-role-badge--' + role);
}

/**
 * Verarbeitet eine Eingabe und zieht die Klon-Felder LIVE nach.
 * Wird aus dem 'input'-Listener aufgerufen (nach _validateFieldLive).
 *
 * WARUM keine Voll-Neuzeichnung des Formulars: showPlaceholderForm() wuerde
 * den DOM ersetzen und damit Fokus/Cursor zerstoeren (vgl. Bugfixes 142/117).
 * Hier werden ausschliesslich die betroffenen Geschwister-Inputs gezielt
 * aktualisiert — keine Rueckkopplungsschleife.
 *
 * @param {HTMLInputElement} input
 * @param {Object} opts  -- { onSave }
 */
function _propagateLinks(input, opts) {
    if (!window.PlaceholderLinks || !_linkState) return;
    const type = input.dataset.fieldType;
    if (type !== 'm' && type !== 'o') return;   // a: nimmt nicht teil

    const blockId = input.dataset.blockId;
    const name    = input.dataset.fieldName;

    const res = window.PlaceholderLinks.applyInput(_linkState, blockId, name, input.value);
    _linkState = res.state;

    // Rolle des getippten Feldes kann sich geaendert haben (leer -> Stammvater,
    // Klon -> eigenstaendig, ...).
    _applyRoleToGroup(blockId, name,
        window.PlaceholderLinks.classify(_linkState, blockId, name));

    // Klone nachziehen: Wert setzen, validieren, speichern, Rolle markieren.
    for (const upd of res.updates) {
        const sib = document.getElementById(`pf-input-${upd.blockId}-${upd.name}`);
        if (sib && sib.value !== upd.value) {
            sib.value = upd.value;
            _validateFieldLive(sib);
            // Klon-Wert mitspeichern, damit der Bericht ihn rendern kann.
            _scheduleFieldSave(sib, opts);
        }
        _applyRoleToGroup(upd.blockId, upd.name,
            window.PlaceholderLinks.classify(_linkState, upd.blockId, upd.name));
    }
}

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

    // Build 492: Stammvater/Klon-Zustand ueber alle Bloecke neu aufbauen, BEVOR
    // gerendert wird — _renderField liest daraus Rolle und angezeigten Wert.
    _linkState = _buildLinkState(_currentBlocks);

    // Build 141 Logging: Zeigt ob onSave korrekt uebergeben wird.
    console.debug('[PlaceholderWizard] showPlaceholderForm:',
        'blocks=', _currentBlocks.length,
        'focusedId=', _currentBlockId,
        'onSave=', typeof _currentOpts.onSave,
        'myUsername=', _currentOpts.myUsername);

    if (!_currentBlocks.length) {
        body.innerHTML = '<p class="pf-empty-state">Kein Bericht ge\u00f6ffnet.</p>';
        return;
    }

    // Fix Build 142: Fokus vor dem innerHTML-Überschreiben retten.
    // body.innerHTML = ... zerstört den DOM und damit den Fokus. Wenn ein
    // Eingabefeld gerade aktiv ist, wird der Wert gespeichert und der Fokus
    // nach dem Render wiederhergestellt.
    // Beleg: Bugfix Build 142, Projektgespraech 2026-05-09
    const activeEl = document.activeElement;
    const savedBlockId  = activeEl?.dataset?.blockId  || null;
    const savedFieldName = activeEl?.dataset?.fieldName || null;
    const savedValue    = (savedBlockId && savedFieldName) ? activeEl.value : null;

    // Alle Bloecke rendern
    body.innerHTML = _renderAllBlocks(_currentBlocks, _currentBlockId);

    // Fokus wiederherstellen wenn ein Feld aktiv war
    if (savedBlockId && savedFieldName) {
        const inputId = `pf-input-${savedBlockId}-${savedFieldName}`;
        const restored = document.getElementById(inputId);
        if (restored) {
            if (savedValue !== null) restored.value = savedValue;
            // Fokus nur setzen wenn Element noch sichtbar (nicht durch Blur ausgeblendet)
            if (!restored.disabled) {
                // Micro-Task damit der DOM stabil ist
                Promise.resolve().then(() => {
                    restored.focus();
                    // Cursor ans Ende setzen
                    const len = restored.value.length;
                    restored.setSelectionRange(len, len);
                });
            }
        }
    }

    // Event-Listener binden
    _bindFormEvents(body, _currentBlocks, opts);

    // Fokussierten Block sichtbar machen (Blur und Scroll)
    _applyFocusBlur(body, _currentBlockId);
    _scrollToFocusedBlock(body, _currentBlockId);

    // Fix Build 142: _pulseEditorBlock unterdrücken — würde Editor.js-onChange
    // triggern → _scheduleAutoSave → _refreshPlaceholderForm → Rückkopplungsschleife.
    // Puls wird nur beim initialen Formular-Öffnen gesetzt, nicht bei Refreshes.
    // Beleg: Bugfix Build 142, Projektgespraech 2026-05-09
    if (_currentBlockId && !opts?._suppressPulse
        && typeof window.CommentThread?._pulseEditorBlock === 'function') {
        window.CommentThread._pulseEditorBlock(_currentBlockId);
    }

    // Build 494: m/o-Platzhalterdefinitionen (Validierung regex/list/like) einmalig
    // laden. Der erste Render nutzt die evtl. noch nicht geladene DB-Definition
    // nicht; sobald sie da ist, werden die befuellten Felder nachvalidiert.
    // Fire-and-forget — schlaegt der Abruf fehl, bleibt es beim bisherigen
    // Verhalten (Fallback auf das 5. Token-Feld). PlaceholderDefs cached, sodass
    // spaetere Form-Oeffnungen die Definition synchron zur Hand haben.
    if (window.PlaceholderDefs && typeof window.PlaceholderDefs.load === 'function'
        && !window.PlaceholderDefs.isLoaded()) {
        window.PlaceholderDefs.load()
            .then(() => _revalidateFilledInputs(body))
            .catch(() => {});
    }
}

/**
 * Build 494: Validiert alle bereits befuellten Eingabefelder erneut. Wird nach
 * dem asynchronen Laden der DB-Definitionen aufgerufen, damit deren Regeln
 * (regex/list/like) auch beim ersten Form-Oeffnen greifen. Leere Felder werden
 * ausgelassen (kein verfruehtes Pflichtfeld-Rot beim Laden).
 * @param {HTMLElement} body
 */
function _revalidateFilledInputs(body) {
    if (!body) return;
    body.querySelectorAll('.pf-input').forEach(inp => {
        if (String(inp.value).trim() !== '') _validateFieldLive(inp);
    });
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

    // block_data auspacken
    let blockData = {};
    try {
        blockData = typeof block.block_data === 'string'
            ? JSON.parse(block.block_data)
            : (block.block_data || {});
    } catch (_) {}

    // Felder extrahieren (m: und o: — a: wird nicht angezeigt).
    //
    // Build 389: extractFieldsFromBlockData statt extractFields(data.text).
    // Ein TABLE-Block hat KEIN .text — sein Inhalt steht in .content (2D).
    // Mit der alten Zeile blieb die gesamte Feststellungstabelle des
    // Spurenvermerks im Formular unsichtbar: der Ermittler haette die
    // Spurennummer nirgends eintragen koennen.
    // Beleg: Bauplan Build 389 §2, Projektgespraech 2026-07-12
    const mFields = chips
        ? chips.extractFieldsFromBlockData(blockData, 'm').map(f => ({ ...f, type: 'm' }))
        : [];
    const oFields = chips
        ? chips.extractFieldsFromBlockData(blockData, 'o').map(f => ({ ...f, type: 'o' }))
        : [];
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
 * Build 494: Prueft einen Feldwert. Die DB-Definition (window.PlaceholderDefs,
 * validation_type regex/list/like) hat fuer bekannte m/o-IDs VORRANG (DB-
 * Autoritaet, Build 489) und wird ueber ValidationRules.checkTyped geprueft.
 * Ist keine DB-Definition vorhanden, greift der bisherige Weg ueber das
 * 5. Token-Feld (rule:-Katalog oder Base64-Regex, ValidationRules.check).
 *
 * @param {string} name       Feldname (= m/o-Platzhalter-ID)
 * @param {string} fieldType  'm' | 'o' | (a: nimmt nicht teil)
 * @param {string} b64re      5. Token-Feld (rule:/Base64) oder leer
 * @param {string} val        aktueller Wert
 * @returns {{ok: boolean, value: string, message: string}}
 */
function _fieldCheck(name, fieldType, b64re, val) {
    // DB-Definition zuerst (Autoritaet fuer bekannte m/o-IDs).
    if ((fieldType === 'm' || fieldType === 'o')
        && window.PlaceholderDefs && window.ValidationRules
        && typeof window.ValidationRules.checkTyped === 'function') {
        const def = window.PlaceholderDefs.get(name);
        if (def && def.validation && def.validation_type) {
            return window.ValidationRules.checkTyped(
                def.validation_type, def.validation, val);
        }
    }
    // Fallback: 5. Token-Feld (rule:-Katalog oder Base64-Regex).
    if (b64re && window.ValidationRules
        && typeof window.ValidationRules.check === 'function') {
        return window.ValidationRules.check(b64re, val);
    }
    return { ok: true, value: val, message: '' };
}

/**
 * Build 494: Menschlicher Hinweistext zur DB-Definition eines m/o-Feldes.
 * list -> zulaessige Werte, like -> Muster. Fuer regex gibt es keinen
 * DB-Hinweis (das Muster selbst ist keine Hilfe) -> leer.
 * @param {object|null} def
 * @returns {string}
 */
function _defHint(def) {
    if (!def || !def.validation || !def.validation_type) return '';
    if (def.validation_type === 'list') {
        try {
            const arr = JSON.parse(def.validation);
            if (Array.isArray(arr) && arr.length) {
                return 'Zulässige Werte: ' + arr.join(', ');
            }
        } catch (_) {}
        return '';
    }
    if (def.validation_type === 'like') {
        return 'Muster: ' + def.validation;
    }
    return '';
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
    let   val       = savedVal !== null ? savedVal : '';

    // Build 492: Bei einem KLON (gleichnamiges m/o-Feld ohne eigenen Wert)
    // wird der Stammvater-Wert angezeigt (displayValue). Der eigene Wert hat
    // Vorrang. So sieht der Ermittler den gespiegelten Wert sofort, ohne ihn
    // erneut eintippen zu muessen (mc-Wunsch). Rolle fuer die Markierung.
    let role = 'leer';
    if (_linkState && window.PlaceholderLinks
        && (field.type === 'm' || field.type === 'o')) {
        val  = window.PlaceholderLinks.displayValue(_linkState, blockId, field.name);
        role = window.PlaceholderLinks.classify(_linkState, blockId, field.name);
    }

    const isM       = field.type === 'm';
    const label     = _esc(field.description || field.name);
    const inputId   = `pf-input-${_esc(blockId)}-${_esc(field.name)}`;
    const reqMark   = isM ? ' <span class="pf-required" aria-hidden="true">*</span>' : '';
    const hasVal    = String(val).trim() !== '';

    // Build 492: Rollen-Badge (nur Stammvater/Klon werden markiert).
    const roleLbl   = _roleLabel(role);
    const roleBadge = roleLbl
        ? ` <span class="pf-role-badge pf-role-badge--${role}">${_esc(roleLbl)}</span>`
        : '';
    const roleCls   = ` pf-role--${role}`;

    // Validierungsstatus.
    //
    // Build 389: Die Pruefung laeuft ueber window.ValidationRules. Das
    // 5. Platzhalterfeld (field.b64regex) traegt ENTWEDER einen Verweis in den
    // zentralen Katalog ('rule:spurennummer', neu) ODER eine Base64-Regex
    // (Alt-Form) — ValidationRules.check() erkennt beide. Damit bleiben alle
    // bestehenden Bausteine unveraendert gueltig.
    // Beleg: Bauplan Build 389 §3; Build 494: DB-Definition (PlaceholderDefs)
    // hat Vorrang (_fieldCheck).
    const dbDef = (window.PlaceholderDefs && (field.type === 'm' || field.type === 'o'))
        ? window.PlaceholderDefs.get(field.name)
        : null;

    let validCls = '';
    if (hasVal) {
        const res = _fieldCheck(field.name, field.type, field.b64regex, val);
        validCls = res.ok ? ' pf-input--valid' : ' pf-input--warn';
    }

    // Hinweistext der Regel (z.B. 'AIW/R3X/... gefolgt von Ziffern'). Ohne ihn
    // saehe der Ermittler im Fehlerfall nur 'entspricht nicht dem Format' —
    // ohne zu erfahren, WAS erwartet wird. Build 494: DB-Definition zuerst
    // (zulaessige Werte / Muster), sonst der rule:-Katalog-Hinweis.
    let ruleHint = _defHint(dbDef);
    if (!ruleHint && field.b64regex && window.ValidationRules) {
        const spec = window.ValidationRules.resolve(field.b64regex);
        if (spec && spec.hint) ruleHint = spec.hint;
    }

    return `<div class="pf-field-group${roleCls}"
                 data-block-id="${_esc(blockId)}"
                 data-field-name="${_esc(field.name)}"
                 data-field-type="${_esc(field.type)}"
                 data-role="${_esc(role)}">
        <label class="pf-label" for="${inputId}">
            ${label}${reqMark}${roleBadge}
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
        ${ruleHint
            ? `<div class="pf-field-hint pf-field-hint--format">Format: ${_esc(ruleHint)}</div>`
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
        group.addEventListener('click', (evt) => {
            window._uevt?.(evt, 'placeholder_wizard', 'click:pf-block-group', { blockId: group.dataset.blockId }); // B200
            const bid = group.dataset.blockId;
            if (bid && bid !== _currentBlockId) {
                _currentBlockId = bid;
                focusBlock(bid);
            }
        });
    });

    // Klick auf ein Eingabefeld: Fokus direkt auf diesem Block setzen
    body.querySelectorAll('.pf-input').forEach(input => {
        input.addEventListener('focus', (evt) => {
            window._uevt?.(evt, 'placeholder_wizard', 'focus:pf-input', { blockId: input.dataset.blockId, field: input.dataset.fieldName }); // B200
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
        input.addEventListener('input', (evt) => {
            window._uevt?.(evt, 'placeholder_wizard', 'input:pf-input', { field: input.dataset.fieldName }); // B200
            _validateFieldLive(input);
            // Build 492: Stammvater/Klon LIVE nachziehen (gleichnamige Felder).
            // MUSS vor _scheduleFieldSave des getippten Feldes laufen, damit die
            // Rolle (leer->Stammvater) korrekt gesetzt ist; die Klone werden
            // innerhalb von _propagateLinks selbst gespeichert.
            _propagateLinks(input, opts);
            _scheduleFieldSave(input, opts);
        });

        // Build 389: Beim VERLASSEN des Feldes wird der Wert normalisiert
        // (z.B. transform: upper -> 'aiw123' wird zu 'AIW123') und sofort
        // sichtbar zurueckgeschrieben.
        //
        // WARUM ERST BEIM BLUR und nicht schon bei jedem Tastendruck:
        // Ein Umschreiben des Feldinhalts waehrend der Eingabe setzt die
        // Cursorposition zurueck — der Ermittler wuerde beim Tippen aus dem
        // Feld 'springen'. Beim Blur ist das unschaedlich und der Ermittler
        // SIEHT, welcher Wert tatsaechlich gespeichert wurde. Der Wert im
        // Feld und der Wert in der Akte sind damit immer identisch.
        // Beleg: Bauplan Build 389 §3, Entwicklervorgabe 2026-07-12
        input.addEventListener('blur', (evt) => {
            window._uevt?.(evt, 'placeholder_wizard', 'blur:pf-input', { field: input.dataset.fieldName }); // B200
            const b64re = input.dataset.b64regex;
            if (!b64re || !window.ValidationRules) return;

            const normalized = window.ValidationRules.normalize(b64re, input.value);
            if (normalized !== input.value) {
                _dbg('blur: Wert normalisiert:', JSON.stringify(input.value),
                     '->', JSON.stringify(normalized));
                input.value = normalized;
                _validateFieldLive(input);
                // Sofort speichern — der normalisierte Wert ist der gueltige.
                _scheduleFieldSave(input, opts);
            }
        });

        // Tab-Navigation zwischen Block-Gruppen: Blur wandert mit
        input.addEventListener('keydown', e => {
            window._uevt?.(e, 'placeholder_wizard', 'keydown:pf-input', { key: e.key, field: input.dataset.fieldName }); // B200
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
    const type = input.dataset.fieldType;
    const name = input.dataset.fieldName;
    const b64re = input.dataset.b64regex;

    // Klassen-Reset
    input.classList.remove('pf-input--valid', 'pf-input--warn', 'pf-input--error');
    if (errEl) errEl.textContent = '';

    if (!val) {
        if (isM && errEl) errEl.textContent = 'Pflichtfeld — bitte ausf\u00fcllen.';
        return;
    }

    // Formatpruefung (Build 389: ueber den zentralen Katalog).
    // Waehrend der Eingabe wird NUR gewarnt, nicht blockiert — sonst koennte
    // der Ermittler eine Nummer nicht zeichenweise tippen ('AIW1' ist beim
    // vierten Zeichen noch unvollstaendig). Die harte Pruefung erfolgt beim
    // Verlassen des Feldes (_normalizeAndValidateField) und ein zweites Mal
    // serverseitig beim Einreichen (report.py::_validate_report_fields).
    // Build 494: DB-Definition (PlaceholderDefs) hat Vorrang (regex/list/like);
    // sonst greift der rule:-Katalog / die Base64-Regex — beides ueber _fieldCheck.
    const res = _fieldCheck(name, type, b64re, val);
    if (!res.ok) {
        input.classList.add('pf-input--warn');
        if (errEl) errEl.textContent = res.message;
        return;
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
    // Build 141 Logging: Zeigt ob onSave ueberhaupt vorhanden ist.
    if (!opts?.onSave) {
        console.warn('[PlaceholderWizard] _scheduleFieldSave: kein onSave in opts!',
            'blockId=', input.dataset.blockId,
            'field=', input.dataset.fieldName,
            'opts=', opts);
        return;
    }
    const key = `${input.dataset.blockId}:${input.dataset.fieldName}`;
    console.debug('[PlaceholderWizard] _scheduleFieldSave: Timer gesetzt fuer', key,
        'value=', JSON.stringify(input.value));
    clearTimeout(_saveTimers[key]);
    _saveTimers[key] = setTimeout(() => {
        _saveField(input, opts);
        delete _saveTimers[key];
    }, FIELD_SAVE_DEBOUNCE_MS);
}

async function _saveField(input, opts) {
    const blockId = input.dataset.blockId;
    const name    = input.dataset.fieldName;
    // Build 389: Es wird der NORMALISIERTE Wert gespeichert (transform aus dem
    // Regel-Katalog, z.B. upper). Damit steht in der Akte einheitlich
    // 'AIW12345' — auch wenn der Ermittler 'aiw12345' getippt und das Feld per
    // debounce-Timer vor dem Blur gespeichert hat. Der Server normalisiert
    // beim Einreichen ein zweites Mal identisch
    // (core/validation_rules.py::_apply_transform) — beide Seiten kommen zum
    // selben Ergebnis.
    const b64re   = input.dataset.b64regex;
    const val     = (b64re && window.ValidationRules)
        ? window.ValidationRules.normalize(b64re, input.value)
        : input.value;
    // Build 141 Logging: Zeigt genau was gespeichert wird.
    console.debug('[PlaceholderWizard] _saveField: blockId=', blockId,
        'name=', name, 'val=', JSON.stringify(val),
        'onSave=', typeof opts?.onSave);
    if (!opts?.onSave) {
        console.warn('[PlaceholderWizard] _saveField: kein onSave — Abbruch');
        return;
    }
    try {
        await opts.onSave(blockId, name, val);
        console.debug('[PlaceholderWizard] _saveField: onSave abgeschlossen fuer', name);
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
        console.debug('[PlaceholderWizard] openAtField: onSave aus Options gesetzt,',
            'blockId=', options.blockId, 'fieldName=', fieldName);
    } else {
        console.warn('[PlaceholderWizard] openAtField: KEIN onSave in options!',
            'options=', options);
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
