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
 * Version: v0.6.137 · Build: 137 · 2026-05-09
 * Beleg: Bauplan B6 v0.3 §2.2, §4.5, Ausdefinitionsgespraech 2026-05-05
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
            // seg.text stammt aus raw.text (DB-Speicher, bereits HTML-safe via
            // Editor.js-Serialisierung). Kein nochmaliges Escaping — sonst werden
            // korrekte Entities wie &lt; zu &amp;lt; doppelt kodiert.
            // Beleg: Bugfix Build 131, Projektgespraech 2026-05-09
            return seg.text.replace(/\n/g, '<br>');
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
        const displayVal = (resolved ?? defaultVal) || name;
        const title = `Automatisch: ${name}` + (description ? ` — ${description}` : '');
        // Bug 2.50 Fix Build 137: contenteditable="false" verhindert direktes Schreiben
        // in den Chip. Der Span ist damit nicht editierbar (Browser-nativ).
        // Beleg: Bugfix Build 137, Projektgespraech 2026-05-09
        return `<span class="ph-chip ph-chip-auto" contenteditable="false" ${dataAttrs} title="${_esc(title)}">${_esc(displayVal)}</span>`;
    }

    if (chipType === 'm') {
        const val = values[name];
        const isFilled = val !== undefined && val !== null && String(val).trim() !== '';
        if (isFilled) {
            // Bug 2.49 Fix Build 137: Ausgefuellter Wert wird im Chip dargestellt.
            // Bug 2.50 Fix Build 137: contenteditable="false"
            const title = description ? `${name} — ${description}` : name;
            return `<span class="ph-chip ph-chip-mandatory ph-chip-filled" contenteditable="false" ${dataAttrs} title="${_esc(title)}">${_esc(val)}</span>`;
        } else {
            const title = (description || name) + ' (Pflichtfeld — muss ausgefuellt werden)';
            return `<span class="ph-chip ph-chip-mandatory ph-chip-empty" contenteditable="false" ${dataAttrs} title="${_esc(title)}">${_esc(description || name)} *</span>`;
        }
    }

    if (chipType === 'o') {
        const val = values[name];
        const isFilled = val !== undefined && val !== null && String(val).trim() !== '';
        if (isFilled) {
            // Bug 2.49 Fix Build 137: Ausgefuellter Wert wird im Chip dargestellt.
            // Bug 2.50 Fix Build 137: contenteditable="false"
            const title = description ? `${name} — ${description}` : name;
            return `<span class="ph-chip ph-chip-optional ph-chip-filled" contenteditable="false" ${dataAttrs} title="${_esc(title)}">${_esc(val)}</span>`;
        } else {
            const title = (description || name) + ' (optional)';
            return `<span class="ph-chip ph-chip-optional ph-chip-empty" contenteditable="false" ${dataAttrs} title="${_esc(title)}">${_esc(description || name)}</span>`;
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

_dbg('placeholder_chips.js: window.PlaceholderChips exportiert');
window.PlaceholderChips = {
    parse,
    render,
    hasUnfilledMandatory,
    extractFields,
};

// ---------------------------------------------------------------------------
// dehydrateChips / hydrateChips (B6 Phase 5)
// Beleg: Bauplan B6 v0.5 §4.6, OP-B6-5-Verifikation, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

/**
 * Konvertiert gerendertes HTML mit .ph-chip-Spans zurueck in Template-Syntax.
 * Wird im Auto-Save aufgerufen bevor block_data gespeichert wird.
 *
 * Algorithmus:
 *   1. HTML in einen temporaeren DOM-Knoten laden.
 *   2. Jeden .ph-chip-Span durch seinen data-chip-raw-Wert ersetzen.
 *   3. innerHTML des temporaeren Knotens zurueckgeben (= Rohtext).
 *
 * Unbekannte Spans (ohne data-chip-raw) werden nicht veraendert.
 * Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
 *
 * @param {string} html  -- innerHTML eines paragraph-Blocks mit gerenderten Chips
 * @returns {string}     -- Text mit Template-Syntax ({{m:...}} etc.)
 */
function dehydrateChips(html) {
    if (!html) return html;

    // Build 124 Fix: dehydrateChips muss HTML-safe Text zurueckgeben der
    // kein weiteres Escaping benoetigt. Wenn html keine ph-chips enthaelt,
    // direkt zurueckgeben — kein DOM-Roundtrip der Entities veraendern koennte.
    if (!html.includes('ph-chip')) return html;

    const tmp = document.createElement('div');
    tmp.innerHTML = html;

    tmp.querySelectorAll('.ph-chip').forEach(span => {
        const raw = span.dataset.chipRaw;
        if (raw) {
            // Durch Text-Knoten ersetzen, damit kein umschliessendes Element uebrig bleibt
            span.replaceWith(document.createTextNode(raw));
        }
    });

    // tmp.innerHTML serialisiert den DOM zurueck zu HTML.
    // Text-Knoten die Zeichen wie < > & enthalten werden dabei korrekt escaped.
    return tmp.innerHTML;
}

/**
 * Alias fuer render() — Template-Syntax -> HTML mit Chips.
 * Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
 *
 * @param {string} text           -- Rohtext mit Platzhaltern
 * @param {Object} values         -- { name: value } fuer m:/o:-Felder
 * @param {Object} resolvedAuto   -- { query_id: wert } fuer a:-Felder
 * @returns {string}              -- HTML-String mit Chips
 */
function hydrateChips(text, values = {}, resolvedAuto = {}) {
    return render(text, values, resolvedAuto);
}

// window-Export ergaenzen
window.PlaceholderChips.dehydrateChips = dehydrateChips;
window.PlaceholderChips.hydrateChips   = hydrateChips;

// ---------------------------------------------------------------------------
// Block-Data-Helfer (Build 389)
// ---------------------------------------------------------------------------
// PROBLEM, das diese Helfer loesen:
//   Bis Build 388 arbeiteten ALLE Chip-Pfade ausschliesslich auf
//   block_data.text (report_editor.js:697 'Nur Bloecke mit block_type
//   paragraph'). Ein Editor.js-TABLE-Block legt seinen Text aber in
//   block_data.content ab (2D-Array von Zellen), ein LIST-Block in
//   block_data.items. Platzhalter in einer Tabellenzelle wurden deshalb:
//     - beim Laden nicht zu Chips hydriert (der Ermittler saehe rohes
//       '{{a:user.posts_total|0}}' in der Zelle),
//     - vom Wizard nicht als Eingabefeld erfasst,
//     - beim Auto-Save nicht dehydriert (Chip-HTML waere in die Datenbank
//       geschrieben worden — und damit in den Siegel-Hash des Berichts).
//
//   Der Spurenvermerk (Build 388) besteht in seinem Kern aus einer TABELLE.
//   Ohne diese Helfer waere er unbenutzbar.
//
// LOESUNG:
//   mapBlockTexts() kapselt an EINER Stelle, wo in einem Block Text stehen
//   kann. Alle uebrigen Pfade (Hydrieren, Dehydrieren, Feld-Extraktion,
//   Auto-Aufloesung) setzen darauf auf und muessen den Blocktyp nicht mehr
//   kennen. Das ist bewusst die exakte Entsprechung von
//   core/placeholder_syntax.py::PlaceholderSyntax.iter_texts() auf dem
//   Server — beide Seiten MUESSEN dieselben Textstellen sehen, sonst prueft
//   der Server Felder, die der Client nie angeboten hat (oder umgekehrt).
//
// Beleg: Bauplan Build 389 §2, Projektgespraech 2026-07-12
// ---------------------------------------------------------------------------

/**
 * Wendet fn auf JEDE Textstelle eines Editor.js-Blocks an und liefert eine
 * NEUE block_data zurueck (das Original wird nicht veraendert).
 *
 * Beruecksichtigte Textstellen:
 *   .text            paragraph / header / quote
 *   .items[]         list (Strings ODER {content: '...'} bei NestedList)
 *   .content[][]     table (2D-Array von Zellen)
 *
 * @param {Object}   data  block_data (Objekt, nicht JSON-String)
 * @param {Function} fn    (text: string) => string
 * @returns {Object}       neue block_data
 */
function mapBlockTexts(data, fn) {
    if (!data || typeof data !== 'object' || typeof fn !== 'function') return data;

    const out = { ...data };

    // paragraph / header / quote
    if (typeof out.text === 'string') {
        out.text = fn(out.text);
    }

    // list — NestedList liefert je nach Version Strings oder {content}
    if (Array.isArray(out.items)) {
        out.items = out.items.map(item => {
            if (typeof item === 'string') return fn(item);
            if (item && typeof item === 'object' && typeof item.content === 'string') {
                return { ...item, content: fn(item.content) };
            }
            return item;
        });
    }

    // table
    if (Array.isArray(out.content)) {
        out.content = out.content.map(row =>
            Array.isArray(row)
                ? row.map(cell => (typeof cell === 'string' ? fn(cell) : cell))
                : row
        );
    }

    return out;
}

/**
 * Liefert alle Textstellen eines Blocks als Array. Wird gebraucht, wenn nur
 * GELESEN wird (Feld-Extraktion, Auto-Platzhalter-Erkennung).
 * @param {Object} data
 * @returns {string[]}
 */
function collectBlockTexts(data) {
    const texts = [];
    mapBlockTexts(data, (t) => { texts.push(t); return t; });
    return texts;
}

/**
 * Hydriert ALLE Textstellen eines Blocks (Template-Syntax -> Chip-HTML).
 *
 * Wichtig: hydrateChips() wird nur auf Texte angewandt, die tatsaechlich
 * '{{' enthalten. Sonst wuerde render()/_esc() bereits escapte Entities
 * (&lt; usw.) ein zweites Mal escapen — genau der Fehler aus Build 124.
 *
 * @param {Object} data
 * @param {Object} values        { name: wert } fuer m:/o:
 * @param {Object} resolvedAuto  { query_id: wert } fuer a:
 * @returns {Object} neue block_data
 */
function hydrateBlockData(data, values = {}, resolvedAuto = {}) {
    return mapBlockTexts(data, (t) =>
        (t && t.includes('{{')) ? hydrateChips(t, values, resolvedAuto) : t
    );
}

/**
 * Dehydriert ALLE Textstellen eines Blocks (Chip-HTML -> Template-Syntax).
 * Idempotent auf reiner Template-Syntax (dehydrateChips steigt frueh aus,
 * wenn kein 'ph-chip' im Text vorkommt).
 *
 * @param {Object} data
 * @returns {Object} neue block_data
 */
function dehydrateBlockData(data) {
    return mapBlockTexts(data, (t) => dehydrateChips(t));
}

/**
 * Extrahiert die Platzhalter-Felder eines Blocks ueber ALLE Textstellen
 * hinweg — auch aus Tabellenzellen.
 *
 * Duplikate (derselbe Feldname in mehreren Zellen) werden zusammengefasst:
 * ein Feldname = EIN Wert je Block (so ist placeholder_values_json aufgebaut,
 * und so rendert _refreshChipsInBlock() den Wert in alle Vorkommen).
 *
 * @param {Object} data
 * @param {'m'|'o'|'a'} type
 * @returns {Array<{name, defaultVal, description, b64regex}>}
 */
function extractFieldsFromBlockData(data, type) {
    const seen   = new Set();
    const result = [];
    for (const text of collectBlockTexts(data)) {
        for (const f of extractFields(text, type)) {
            if (seen.has(f.name)) continue;
            seen.add(f.name);
            result.push(f);
        }
    }
    return result;
}

window.PlaceholderChips.mapBlockTexts             = mapBlockTexts;
window.PlaceholderChips.collectBlockTexts         = collectBlockTexts;
window.PlaceholderChips.hydrateBlockData          = hydrateBlockData;
window.PlaceholderChips.dehydrateBlockData        = dehydrateBlockData;
window.PlaceholderChips.extractFieldsFromBlockData = extractFieldsFromBlockData;

// ---------------------------------------------------------------------------
// PlaceholderInlineTool (B6 Phase 5)
// Editor.js InlineTool fuer Platzhalter-Chips.
//
// Verifiziert gegen editor.bundle.js (OP-B6-5):
//   - static isInline = true
//   - render(): gibt button-Element zurueck
//   - surround(range): wrap/unwrap (Toggle)
//   - checkState(sel): gibt boolean zurueck
//   - static sanitize: Whitelist fuer Tag + data-chip-*-Attribute
//   - api.selection.findParentTag(tag, cssClass): sucht im DOM nach Elterntag
//   - api.selection.expandToTag(el): Selektion auf Element ausdehnen
//
// Beleg: Bauplan B6 v0.5 §4.6, editor.bundle.js OP-B6-5-Verifikation,
//        Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

/**
 * Editor.js InlineTool fuer Platzhalter-Chips.
 * Ermoeglicht das Setzen und Entfernen von Platzhaltern im Fliesstext.
 * Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
 */
class PlaceholderInlineTool {

    static get isInline() { return true; }

    static get title() { return 'Platzhalter'; }

    /**
     * Sanitize-Konfiguration: erlaubt SPAN mit ph-chip-Klasse und data-chip-*-Attributen.
     * Beleg: Bauplan B6 v0.5 §4.6, editor.bundle.js OP-B6-5-Verifikation
     */
    static get sanitize() {
        return {
            span: {
                class:                    true,
                'data-chip-type':         true,
                'data-chip-name':         true,
                'data-chip-default':      true,
                'data-chip-description':  true,
                'data-chip-b64regex':     true,
                'data-chip-raw':          true,
                title:                    true,
            },
        };
    }

    constructor({ api }) {
        this.api    = api;
        this.button = null;
        this._CSS   = {
            button:       this.api.styles.inlineToolButton,
            buttonActive: this.api.styles.inlineToolButtonActive,
        };
    }

    /**
     * Toolbar-Button rendern.
     * Symbol: { } als Platzhalter-Indikator.
     * Beleg: Bauplan B6 v0.5 §4.6, Projektgespraech 2026-05-06
     */
    render() {
        this.button = document.createElement('button');
        this.button.type = 'button';
        this.button.classList.add(this._CSS.button);
        // SVG: geschweifte Klammern als Chip-Symbol
        this.button.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 3H7a2 2 0 0 0-2 2v5a2 2 0 0 1-2 2 2 2 0 0 1 2 2v5c0 1.1.9 2 2 2h1"/>
            <path d="M16 21h1a2 2 0 0 0 2-2v-5c0-1.1.9-2 2-2a2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h-1"/>
        </svg>`;
        this.button.setAttribute('aria-label', 'Platzhalter einf\u00fcgen');
        return this.button;
    }

    /**
     * Selektion mit Chip-Span umschliessen oder Chip entfernen (Toggle).
     * Ist der Cursor in einem .ph-chip: auswickeln.
     * Sonst: Selektion mit neuem Chip-Span umschliessen.
     * Beleg: OP-B6-5 (Toggle-Logik bestaetigt), editor.bundle.js Annotation-Tool
     * @param {Range} range
     */
    surround(range) {
        if (!range) return;

        // Vorhandenen Chip finden (Toggle: auswickeln)
        const existingChip = this.api.selection.findParentTag('SPAN', 'ph-chip');
        if (existingChip) {
            this._unwrap(existingChip);
            return;
        }

        // Neuen Chip-Span anlegen (Standardtyp 'm' fuer Pflichtfeld)
        // Der Ermittler sieht einen Platzhalter-Chip, der in Phase 6
        // ueber das Formular befuellt wird.
        const selectedText = range.toString().trim();
        const name = selectedText
            ? selectedText.replace(/[^A-Za-z0-9_.-]/g, '_').toLowerCase().slice(0, 40)
            : 'platzhalter';
        const raw = `\u007b\u007bm:${name}\u007d\u007d`;  // {{m:name}}

        const span = document.createElement('span');
        span.className = 'ph-chip ph-chip-mandatory ph-chip-empty';
        span.dataset.chipType        = 'm';
        span.dataset.chipName        = name;
        span.dataset.chipDefault     = '';
        span.dataset.chipDescription = selectedText || name;
        span.dataset.chipRaw         = raw;
        span.title = `${name} (Pflichtfeld \u2014 bitte ausf\u00fcllen)`;
        span.textContent = (selectedText || name) + ' *';

        // Selektion mit Span ersetzen
        span.appendChild(range.extractContents());
        // Wenn extractContents() Inhalt hatte: span.textContent wird ueberschrieben
        // Deshalb: nur wenn keine sinnvollen Kindknoten da sind, textContent setzen
        if (!span.textContent.trim()) {
            span.textContent = (selectedText || name) + ' *';
        }
        range.insertNode(span);
        this.api.selection.expandToTag(span);
    }

    /**
     * Aktivitaetsstatus pruefen: Cursor in einem .ph-chip-Element?
     * Beleg: OP-B6-5-Verifikation, editor.bundle.js
     * @param {Selection} _sel
     * @returns {boolean}
     */
    checkState(_sel) {
        const chip = this.api.selection.findParentTag('SPAN', 'ph-chip');
        const isActive = chip !== null;
        if (this.button) {
            this.button.classList.toggle(this._CSS.buttonActive, isActive);
        }
        return isActive;
    }

    /**
     * Chip-Span auswickeln: Inhalt bleibt als normaler Fliesstext.
     * @param {Element} chipEl
     */
    _unwrap(chipEl) {
        this.api.selection.expandToTag(chipEl);
        const sel   = window.getSelection();
        const range = sel.getRangeAt(0);
        const text  = document.createTextNode(chipEl.textContent
            .replace(/\s*\*\s*$/, '')  // " *" Suffix entfernen
            .trim());
        range.deleteContents();
        range.insertNode(text);
        sel.removeAllRanges();
        const newRange = document.createRange();
        newRange.setStartAfter(text);
        newRange.collapse(true);
        sel.addRange(newRange);
    }
}

window.PlaceholderInlineTool = PlaceholderInlineTool;

})();
