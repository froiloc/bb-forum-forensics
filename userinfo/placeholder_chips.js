/**
 * userinfo/placeholder_chips.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Platzhalter-Chip-Rendering fuer Paragraph-Inhalte in Fenster 3.
 *
 *   Wandelt rohen Platzhalter-Text ({{a:...}}, {{m:...}}, {{o:...}}) in
 *   visuelle Chips um, die im Paragraph-Inhalt inline dargestellt werden.
 *   Chips sind klickbar (Doppelklick oeffnet in Phase 5 den Wizard).
 *
 *   Platzhalter-Syntax (drei Typen, Grundregel 13):
 *     {{a:query_id|default|description}}         -- automatisch (gruen)
 *     {{auto:query_id|default|description}}       -- Langform fuer 'a:'
 *     {{m:name|default|description|b64regex}}     -- Pflichtfeld (rot/blau)
 *     {{mandatory:name|default|description}}       -- Langform fuer 'm:'
 *     {{o:name|default|description|b64regex}}     -- optional (gelb/blau)
 *     {{optional:name|default|description}}        -- Langform fuer 'o:'
 *
 *   Viertes optionales Feld (b64regex): Base64-kodierte Validierungs-Regex.
 *   Wird in Phase 5 (Wizard) ausgewertet. Parser erkennt es jetzt schon.
 *   Beleg: OP-B6-5, Projektgespraech 2026-05-05
 *
 *   Darstellung der Chips (§4.5 Bauplan B6 v0.3):
 *     {{a:...}}  aufgeloest -> gruen, nicht editierbar
 *     {{m:...}}  ausgefuellt -> blau, Doppelklick oeffnet Wizard
 *     {{m:...}}  leer        -> rot blinkend, blockiert Aktivierung
 *     {{o:...}}  ausgefuellt -> blau, Doppelklick oeffnet Wizard
 *     {{o:...}}  leer        -> gelb, Doppelklick oeffnet Wizard
 *
 * Exports (window.*):
 *   window.PlaceholderChips.parse(text)
 *     Parst einen Text und gibt ein Array von Segmenten zurueck.
 *   window.PlaceholderChips.render(text, values, resolvedAuto)
 *     Gibt HTML-String mit Chips zurueck.
 *   window.PlaceholderChips.hasUnfilledMandatory(text, values)
 *     Prueft ob Pflichtfelder leer sind (blockiert Aktivierung).
 *   window.PlaceholderChips.extractNames(text, type)
 *     Gibt alle Feldnamen eines Typs ('m', 'o', 'a') zurueck.
 *
 * Version: v0.1.0 · Build: 091 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §2.2, §4.5, Ausdefinitionsgespraech 2026-05-05
 */

'use strict';

// ---------------------------------------------------------------------------
// Regex fuer alle drei Platzhalter-Typen
//
// Gruppe 1: Typ-Kuerzel (a/auto, m/mandatory, o/optional)
// Gruppe 2: name/query_id
// Gruppe 3: default-Wert (optional)
// Gruppe 4: Beschreibung/Hilfetext (optional)
// Gruppe 5: Base64-Regex fuer Validierung (optional, OP-B6-5)
//
// Das | im Pattern matcht nicht innerhalb von Feldern, da [^|}] verwendet wird.
// Beleg: OP-B6-5 (Base64-Codierung verhindert |-Kollision)
// ---------------------------------------------------------------------------
const _CHIP_RE = /\{\{(a|auto|m|mandatory|o|optional):([A-Za-z0-9._-]+)(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?(?:\|([^|}\n]*))?\}\}/g;

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

/** Normalisiert den Typ-String auf Kurzkuerzel. */
function _normalizeType(raw) {
    switch (raw) {
        case 'a': case 'auto':      return 'a';
        case 'm': case 'mandatory': return 'm';
        case 'o': case 'optional':  return 'o';
        default: return raw;
    }
}

/** HTML-Escape fuer Chip-Inhalt. */
function _esc(s) {
    return String(s ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ---------------------------------------------------------------------------
// Segment-Parser
// ---------------------------------------------------------------------------

/**
 * Parst einen Text mit Platzhaltern in Segmente.
 *
 * Gibt ein Array von Objekten zurueck:
 *   { type: 'text',  text: '...' }
 *   { type: 'chip',  chipType: 'a'|'m'|'o',
 *                    name: '...',          -- query_id fuer a:, Feldname fuer m:/o:
 *                    defaultVal: '...',
 *                    description: '...',
 *                    b64regex: '...'|null, -- OP-B6-5
 *                    raw: '...' }          -- Original-Token fuer Roundtrip
 *
 * @param {string} text
 * @returns {Array}
 */
function parse(text) {
    if (!text) return [{ type: 'text', text: '' }];

    const segments = [];
    let lastIndex  = 0;
    const re       = new RegExp(_CHIP_RE.source, 'g');  // neue Instanz, kein lastIndex-Teilen
    let match;

    while ((match = re.exec(text)) !== null) {
        // Text vor dem Match
        if (match.index > lastIndex) {
            segments.push({ type: 'text', text: text.slice(lastIndex, match.index) });
        }
        segments.push({
            type:        'chip',
            chipType:    _normalizeType(match[1]),
            name:        match[2],
            defaultVal:  match[3] ?? '',
            description: match[4] ?? '',
            b64regex:    match[5] ?? null,   // OP-B6-5
            raw:         match[0],
        });
        lastIndex = match.index + match[0].length;
    }

    // Resttext
    if (lastIndex < text.length) {
        segments.push({ type: 'text', text: text.slice(lastIndex) });
    }

    return segments.length ? segments : [{ type: 'text', text: '' }];
}

// ---------------------------------------------------------------------------
// Chip-HTML-Renderer
// ---------------------------------------------------------------------------

/**
 * Rendert einen Text mit Platzhaltern als HTML-String mit Chips.
 *
 * @param {string} text           -- Rohtext mit Platzhaltern
 * @param {Object} values         -- { name: value } fuer m:/o:-Felder
 * @param {Object} resolvedAuto   -- { query_id: aufgeloester_wert } fuer a:-Felder
 * @returns {string}              -- HTML-String fuer innerHTML
 */
function render(text, values = {}, resolvedAuto = {}) {
    const segments = parse(text);
    return segments.map(seg => {
        if (seg.type === 'text') {
            return _esc(seg.text).replace(/\n/g, '<br>');
        }
        return _renderChip(seg, values, resolvedAuto);
    }).join('');
}

/**
 * Rendert einen einzelnen Chip als HTML-String.
 * Beleg: Bauplan B6 v0.3 §4.5 (Chip-Darstellung)
 */
function _renderChip(seg, values, resolvedAuto) {
    const { chipType, name, defaultVal, description, b64regex, raw } = seg;

    // data-Attribute fuer den Wizard (Phase 5)
    const dataAttrs = [
        `data-chip-type="${_esc(chipType)}"`,
        `data-chip-name="${_esc(name)}"`,
        `data-chip-default="${_esc(defaultVal)}"`,
        `data-chip-description="${_esc(description)}"`,
        b64regex ? `data-chip-b64regex="${_esc(b64regex)}"` : '',
        `data-chip-raw="${_esc(raw)}"`,
    ].filter(Boolean).join(' ');

    if (chipType === 'a') {
        // Automatisch aufgeloest: gruen, zeigt aufgeloesten Wert
        const resolved = resolvedAuto[name];
        const displayVal = resolved ?? defaultVal || name;
        const title = `Automatisch: ${name}` + (description ? ` — ${description}` : '');
        return `<span class="ph-chip ph-chip-auto" ${dataAttrs} title="${_esc(title)}">${_esc(displayVal)}</span>`;
    }

    if (chipType === 'm') {
        const val = values[name];
        const isFilled = val !== undefined && val !== null && String(val).trim() !== '';
        if (isFilled) {
            // Ausgefuellt: blau
            const title = description ? `${name} — ${description}` : name;
            return `<span class="ph-chip ph-chip-mandatory ph-chip-filled" ${dataAttrs} title="${_esc(title)}">${_esc(val)}</span>`;
        } else {
            // Leer: rot blinkend, blockiert Aktivierung
            const title = (description || name) + ' (Pflichtfeld — muss ausgefuellt werden)';
            return `<span class="ph-chip ph-chip-mandatory ph-chip-empty" ${dataAttrs} title="${_esc(title)}">${_esc(description || name)} *</span>`;
        }
    }

    if (chipType === 'o') {
        const val = values[name];
        const isFilled = val !== undefined && val !== null && String(val).trim() !== '';
        if (isFilled) {
            // Ausgefuellt: blau
            const title = description ? `${name} — ${description}` : name;
            return `<span class="ph-chip ph-chip-optional ph-chip-filled" ${dataAttrs} title="${_esc(title)}">${_esc(val)}</span>`;
        } else {
            // Leer: gelb
            const title = (description || name) + ' (optional)';
            return `<span class="ph-chip ph-chip-optional ph-chip-empty" ${dataAttrs} title="${_esc(title)}">${_esc(description || name)}</span>`;
        }
    }

    // Fallback: unbekannter Typ als Text
    return _esc(raw);
}

// ---------------------------------------------------------------------------
// Hilfsmethoden fuer report.js und Phase 5
// ---------------------------------------------------------------------------

/**
 * Prueft ob mindestens ein Pflichtfeld (m:) leer ist.
 * Wird von report.js genutzt um den Aktivieren-Button zu sperren.
 * Beleg: Bauplan B6 v0.3 §4.5 (Pflichtfeld-Validierung)
 *
 * @param {string} text
 * @param {Object} values -- { name: value }
 * @returns {boolean}
 */
function hasUnfilledMandatory(text, values = {}) {
    const segments = parse(text);
    return segments.some(seg => {
        if (seg.type !== 'chip' || seg.chipType !== 'm') return false;
        const val = values[seg.name];
        return val === undefined || val === null || String(val).trim() === '';
    });
}

/**
 * Gibt alle Feldnamen eines bestimmten Typs aus dem Text zurueck.
 * Wird von Phase 5 (Wizard) genutzt um die Wizard-Schritte aufzubauen.
 *
 * @param {string} text
 * @param {'m'|'o'|'a'} type
 * @returns {Array<{name, defaultVal, description, b64regex}>}
 */
function extractFields(text, type) {
    const segments = parse(text);
    const seen     = new Set();
    const result   = [];
    for (const seg of segments) {
        if (seg.type !== 'chip' || seg.chipType !== type) continue;
        if (seen.has(seg.name)) continue;   // Duplikate ueberspringen
        seen.add(seg.name);
        result.push({
            name:        seg.name,
            defaultVal:  seg.defaultVal,
            description: seg.description,
            b64regex:    seg.b64regex,   // OP-B6-5
        });
    }
    return result;
}

// ---------------------------------------------------------------------------
// window-Export
// ---------------------------------------------------------------------------

window.PlaceholderChips = {
    parse,
    render,
    hasUnfilledMandatory,
    extractFields,
};
