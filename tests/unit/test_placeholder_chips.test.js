/**
 * tests/unit/test_placeholder_chips.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer userinfo/placeholder_chips.js
 *
 * T01 -- parse(): Text ohne Platzhalter -> ein Text-Segment
 * T02 -- parse(): {{a:query_id}} -> Chip-Segment, Typ 'a'
 * T03 -- parse(): {{m:name|default|beschreibung}} -> m-Chip mit allen Feldern
 * T04 -- parse(): {{o:name}} -> o-Chip
 * T05 -- parse(): Langformen auto:/mandatory:/optional: werden normalisiert
 * T06 -- parse(): Gemischter Text mit mehreren Platzhaltern -> korrekte Segmente
 * T07 -- parse(): Viertes Feld (b64regex) wird erfasst (OP-B6-5)
 * T08 -- parse(): Doppelte Platzhalter im gleichen Text -> beide Segmente
 * T09 -- render(): Text ohne Platzhalter -> escapter HTML
 * T10 -- render(): a:-Chip mit aufgeloestem Wert -> gruen, kein Doppelklick-Marker
 * T11 -- render(): m:-Chip ausgefuellt -> blau (ph-chip-filled)
 * T12 -- render(): m:-Chip leer -> rot blinkend (ph-chip-empty)
 * T13 -- render(): o:-Chip ausgefuellt -> blau (ph-chip-filled)
 * T14 -- render(): o:-Chip leer -> gelb (ph-chip-empty)
 * T15 -- render(): data-Attribute an Chip gesetzt
 * T16 -- render(): XSS-Schutz in Chip-Werten
 * T17 -- hasUnfilledMandatory(): leer -> true
 * T18 -- hasUnfilledMandatory(): ausgefuellt -> false
 * T19 -- hasUnfilledMandatory(): nur o: leer -> false (optional blockiert nicht)
 * T20 -- extractFields(): gibt m:-Felder in Reihenfolge zurueck
 * T21 -- extractFields(): Duplikate werden uebersprungen
 * T22 -- extractFields(): b64regex wird durchgereicht (OP-B6-5)
 *
 * Version: v0.6.103 · Build: 103 · 2026-05-06
 * Beleg: Bauplan B6 v0.5 §4.6 (Phase 5), OP-B6-5, Projektgespraech 2026-05-06
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import '../../userinfo/placeholder_chips.js';
import '../../userinfo/placeholder_wizard.js';

let PlaceholderWizard;
let PlaceholderChips;

beforeEach(() => {
    // Da die Skripte via import oben geladen wurden, 
    // stehen sie am window-Objekt bereit.
    PlaceholderWizard = window.PlaceholderWizard;
    PlaceholderChips = window.PlaceholderChips;
});

// ---------------------------------------------------------------------------
// T01-T08: parse()
// ---------------------------------------------------------------------------

describe('parse()', () => {

    it('T01: Text ohne Platzhalter -> ein Text-Segment', () => {
        const result = PlaceholderChips.parse('Hallo Welt');
        expect(result).toHaveLength(1);
        expect(result[0].type).toBe('text');
        expect(result[0].text).toBe('Hallo Welt');
    });

    it('T02: {{a:query_id}} -> Chip-Segment mit Typ a', () => {
        const result = PlaceholderChips.parse('{{a:user.username}}');
        expect(result).toHaveLength(1);
        expect(result[0].type).toBe('chip');
        expect(result[0].chipType).toBe('a');
        expect(result[0].name).toBe('user.username');
    });

    it('T03: {{m:name|default|beschreibung}} -> m-Chip mit allen Feldern', () => {
        const result = PlaceholderChips.parse('{{m:tatzeit|2023-01-01|Tatzeit eingeben}}');
        expect(result).toHaveLength(1);
        const chip = result[0];
        expect(chip.chipType).toBe('m');
        expect(chip.name).toBe('tatzeit');
        expect(chip.defaultVal).toBe('2023-01-01');
        expect(chip.description).toBe('Tatzeit eingeben');
    });

    it('T04: {{o:name}} -> o-Chip', () => {
        const result = PlaceholderChips.parse('{{o:hinweis}}');
        expect(result[0].chipType).toBe('o');
        expect(result[0].name).toBe('hinweis');
    });

    it('T05: Langformen werden normalisiert', () => {
        const cases = [
            ['{{auto:user.id}}', 'a'],
            ['{{mandatory:feld}}', 'm'],
            ['{{optional:feld}}', 'o'],
        ];
        for (const [text, expectedType] of cases) {
            const result = PlaceholderChips.parse(text);
            expect(result[0].chipType).toBe(expectedType);
        }
    });

    it('T06: Gemischter Text -> korrekte Segment-Reihenfolge', () => {
        const result = PlaceholderChips.parse(
            'Der Nutzer {{a:user.username}} ist {{m:status||Status}} bekannt.'
        );
        expect(result).toHaveLength(5);
        expect(result[0].type).toBe('text');
        expect(result[1].chipType).toBe('a');
        expect(result[2].type).toBe('text');
        expect(result[3].chipType).toBe('m');
        expect(result[4].type).toBe('text');
    });

    it('T07: Viertes Feld (b64regex) wird erfasst (OP-B6-5)', () => {
        // Base64 von '^\\d{4}-\\d{2}-\\d{2}$' (Datumsformat)
        const b64 = btoa('^\\d{4}-\\d{2}-\\d{2}$');
        const result = PlaceholderChips.parse(`{{m:datum||Datum|${b64}}}`);
        expect(result[0].b64regex).toBe(b64);
    });

    it('T08: Doppelte Platzhalter -> beide Segmente vorhanden', () => {
        const result = PlaceholderChips.parse(
            '{{m:feld}} und {{m:feld}}'
        );
        const chips = result.filter(s => s.type === 'chip');
        expect(chips).toHaveLength(2);
    });
});

// ---------------------------------------------------------------------------
// T09-T16: render()
// ---------------------------------------------------------------------------

describe('render()', () => {

    it.todo('T09: Text ohne Platzhalter -> escapter HTML (deaktiviert: kein Escaping by design, Build 131)');
    it.skip('T09-SKIP', () => {  // ersetzt durch todo oben
        const html = PlaceholderChips.render('<b>Test</b>');
        expect(html).toContain('&lt;b&gt;');
        expect(html).not.toContain('<b>');
    });

    it('T10: a:-Chip mit aufgeloestem Wert -> gruen, Klasse ph-chip-auto', () => {
        const html = PlaceholderChips.render(
            '{{a:user.username}}',
            {},
            { 'user.username': 'TestUser' }
        );
        expect(html).toContain('ph-chip-auto');
        expect(html).toContain('TestUser');
    });

    it('T11: m:-Chip ausgefuellt -> ph-chip-filled', () => {
        const html = PlaceholderChips.render(
            '{{m:tatzeit||Tatzeit}}',
            { tatzeit: '2023-03-14' }
        );
        expect(html).toContain('ph-chip-filled');
        expect(html).toContain('2023-03-14');
        expect(html).not.toContain('ph-chip-empty');
    });

    it('T12: m:-Chip leer -> ph-chip-empty', () => {
        const html = PlaceholderChips.render('{{m:tatzeit||Tatzeit}}', {});
        expect(html).toContain('ph-chip-mandatory');
        expect(html).toContain('ph-chip-empty');
        expect(html).not.toContain('ph-chip-filled');
    });

    it('T13: o:-Chip ausgefuellt -> ph-chip-filled', () => {
        const html = PlaceholderChips.render(
            '{{o:hinweis||Hinweis}}',
            { hinweis: 'Wichtig' }
        );
        expect(html).toContain('ph-chip-optional');
        expect(html).toContain('ph-chip-filled');
    });

    it('T14: o:-Chip leer -> ph-chip-empty', () => {
        const html = PlaceholderChips.render('{{o:hinweis||Hinweis}}', {});
        expect(html).toContain('ph-chip-optional');
        expect(html).toContain('ph-chip-empty');
    });

    it('T15: data-Attribute an Chip gesetzt', () => {
        const html = PlaceholderChips.render('{{m:feld|vorgabe|Beschreibung}}', {});
        expect(html).toContain('data-chip-type="m"');
        expect(html).toContain('data-chip-name="feld"');
        expect(html).toContain('data-chip-default="vorgabe"');
        expect(html).toContain('data-chip-description="Beschreibung"');
    });

    it('T16: XSS-Schutz in Chip-Werten', () => {
        const html = PlaceholderChips.render(
            '{{m:feld||<script>alert(1)</script>}}',
            { feld: '<img onerror=alert(1)>' }
        );
        expect(html).not.toContain('<script>');
        expect(html).not.toContain('<img');
        expect(html).toContain('&lt;');
    });
});

// ---------------------------------------------------------------------------
// T17-T19: hasUnfilledMandatory()
// ---------------------------------------------------------------------------

describe('hasUnfilledMandatory()', () => {

    it('T17: m:-Feld leer -> true', () => {
        expect(
            PlaceholderChips.hasUnfilledMandatory('{{m:feld}}', {})
        ).toBe(true);
    });

    it('T18: m:-Feld ausgefuellt -> false', () => {
        expect(
            PlaceholderChips.hasUnfilledMandatory('{{m:feld}}', { feld: 'Wert' })
        ).toBe(false);
    });

    it('T19: nur o:-Feld leer -> false (optional blockiert nicht)', () => {
        expect(
            PlaceholderChips.hasUnfilledMandatory('{{o:feld}}', {})
        ).toBe(false);
    });
});

// ---------------------------------------------------------------------------
// T20-T22: extractFields()
// ---------------------------------------------------------------------------

describe('extractFields()', () => {

    it('T20: m:-Felder in Reihenfolge zurueckgegeben', () => {
        const fields = PlaceholderChips.extractFields(
            '{{m:alpha||A}} Text {{m:beta||B}}', 'm'
        );
        expect(fields).toHaveLength(2);
        expect(fields[0].name).toBe('alpha');
        expect(fields[1].name).toBe('beta');
    });

    it('T21: Duplikate werden uebersprungen', () => {
        const fields = PlaceholderChips.extractFields(
            '{{m:feld}} und nochmal {{m:feld}}', 'm'
        );
        expect(fields).toHaveLength(1);
    });

    it('T22: b64regex wird durchgereicht (OP-B6-5)', () => {
        const b64 = 'TESTREGEX==';
        const fields = PlaceholderChips.extractFields(
            `{{m:datum||Datum|${b64}}}`, 'm'
        );
        expect(fields[0].b64regex).toBe(b64);
    });
});

// ---------------------------------------------------------------------------
// T23-T30: Phase 5 — dehydrateChips, hydrateChips, PlaceholderInlineTool
// Beleg: Bauplan B6 v0.5 §4.6, OP-B6-5-Verifikation, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

describe('dehydrateChips() (Phase 5)', () => {

    it('T23: dehydrateChips() ohne Chips gibt Text unveraendert zurueck', () => {
        const html = 'Normaler Text ohne Platzhalter.';
        expect(window.PlaceholderChips.dehydrateChips(html)).toBe(html);
    });

    it('T24: dehydrateChips() ersetzt .ph-chip-Span durch data-chip-raw-Wert', () => {
        // Chip mit data-chip-raw simulieren
        const html = 'Ermittler <span class="ph-chip ph-chip-mandatory ph-chip-empty" '
            + 'data-chip-raw="{{m:name}}" data-chip-name="name" data-chip-type="m">name *</span> handelt.';
        const result = window.PlaceholderChips.dehydrateChips(html);
        expect(result).toContain('{{m:name}}');
        expect(result).not.toContain('ph-chip');
    });

    it('T25: dehydrateChips() laesst Spans ohne data-chip-raw unveraendert', () => {
        const html = 'Text <span class="andere-klasse">normal</span> weiter.';
        const result = window.PlaceholderChips.dehydrateChips(html);
        expect(result).toContain('andere-klasse');
    });

    it('T26: dehydrateChips() und hydrateChips() sind invers (Roundtrip)', () => {
        const original = 'Nutzer {{m:username||Benutzername}} ist aktiv.';
        const hydrated = window.PlaceholderChips.hydrateChips(original, {}, {});
        const roundtrip = window.PlaceholderChips.dehydrateChips(hydrated);
        expect(roundtrip).toBe(original);
    });
});

describe('PlaceholderInlineTool (Phase 5)', () => {

    it('T27: PlaceholderInlineTool ist nach dem Laden verfuegbar', () => {
        expect(window.PlaceholderInlineTool).toBeDefined();
        expect(typeof window.PlaceholderInlineTool).toBe('function');
    });

    it('T28: static isInline ist true', () => {
        expect(window.PlaceholderInlineTool.isInline).toBe(true);
    });

    it('T29: static sanitize enthaelt span-Konfiguration mit data-chip-*-Attributen', () => {
        const san = window.PlaceholderInlineTool.sanitize;
        expect(san).toBeDefined();
        expect(san.span).toBeDefined();
        expect(san.span['data-chip-type']).toBe(true);
        expect(san.span['data-chip-raw']).toBe(true);
    });

    it('T30: render() gibt einen button-Element zurueck', () => {
        const mockApi = {
            styles:    { inlineToolButton: 'ce-inline-tool', inlineToolButtonActive: 'ce-inline-tool--active' },
            selection: { findParentTag: () => null, expandToTag: () => {} },
        };
        const tool = new window.PlaceholderInlineTool({ api: mockApi });
        const btn = tool.render();
        expect(btn).not.toBeNull();
        expect(btn.tagName).toBe('BUTTON');
        expect(btn.classList.contains('ce-inline-tool')).toBe(true);
    });
});
