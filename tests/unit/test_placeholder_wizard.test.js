/**
 * tests/unit/test_placeholder_wizard.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer userinfo/placeholder_wizard.js
 *
 * T01 -- buildSteps(): leerer Text -> ein leerer Schritt
 * T02 -- buildSteps(): nur m:-Felder -> korrekte Schritt-Aufteilung (max 3)
 * T03 -- buildSteps(): m: und o:-Felder -> m: zuerst, dann o:
 * T04 -- buildSteps(): genau 3 Felder -> ein Schritt
 * T05 -- buildSteps(): 4 Felder -> zwei Schritte (3 + 1)
 * T06 -- stepIndexForField(): Feld in Schritt 0 -> 0
 * T07 -- stepIndexForField(): Feld in Schritt 1 -> 1
 * T08 -- stepIndexForField(): unbekanntes Feld -> 0 (Fallback)
 * T09 -- buildSteps(): Duplikate werden nicht doppelt in Schritte aufgenommen
 * T10 -- buildSteps(): b64regex wird an Feld-Objekt weitergegeben (OP-B6-5)
 * T11 -- buildSteps(): 6 Felder -> zwei Schritte (je 3)
 * T12 -- buildSteps(): o:-Felder erscheinen nach m:-Feldern
 *
 * Version: v0.1.0 · Build: 092 · 2026-05-05
 * Beleg: Bauplan B6 v0.3 §4.5, Ausdefinitionsgespraech 2026-05-05
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
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
// T01-T05: buildSteps() — Schritt-Aufteilung
// ---------------------------------------------------------------------------

describe('buildSteps()', () => {

    it('T01: leerer Text -> ein leerer Schritt', () => {
        const steps = PlaceholderWizard.buildSteps('');
        expect(steps).toHaveLength(1);
        expect(steps[0]).toHaveLength(0);
    });

    it('T02: zwei m:-Felder -> ein Schritt', () => {
        const steps = PlaceholderWizard.buildSteps(
            '{{m:feld1||F1}} {{m:feld2||F2}}'
        );
        expect(steps).toHaveLength(1);
        expect(steps[0]).toHaveLength(2);
        expect(steps[0][0].type).toBe('m');
    });

    it('T03: m: und o:-Felder -> m: zuerst, dann o:', () => {
        const steps = PlaceholderWizard.buildSteps(
            '{{o:opt1||O1}} {{m:mand1||M1}}'
        );
        // Alle Felder: erst m, dann o
        const allFields = steps.flat();
        expect(allFields[0].type).toBe('m');
        expect(allFields[1].type).toBe('o');
    });

    it('T04: genau 3 Felder -> ein Schritt', () => {
        const steps = PlaceholderWizard.buildSteps(
            '{{m:f1}} {{m:f2}} {{m:f3}}'
        );
        expect(steps).toHaveLength(1);
        expect(steps[0]).toHaveLength(3);
    });

    it('T05: 4 Felder -> zwei Schritte (3 + 1)', () => {
        const steps = PlaceholderWizard.buildSteps(
            '{{m:f1}} {{m:f2}} {{m:f3}} {{m:f4}}'
        );
        expect(steps).toHaveLength(2);
        expect(steps[0]).toHaveLength(3);
        expect(steps[1]).toHaveLength(1);
    });

    it('T09: Duplikate werden nicht doppelt in Schritte aufgenommen', () => {
        const steps = PlaceholderWizard.buildSteps(
            '{{m:feld}} und nochmal {{m:feld}}'
        );
        const allFields = steps.flat();
        expect(allFields.filter(f => f.name === 'feld')).toHaveLength(1);
    });

    it('T10: b64regex wird an Feld-Objekt weitergegeben (OP-B6-5)', () => {
        const b64 = 'TESTREGEX==';
        const steps = PlaceholderWizard.buildSteps(`{{m:datum||Datum|${b64}}}`);
        expect(steps[0][0].b64regex).toBe(b64);
    });

    it('T11: 6 Felder -> zwei Schritte (je 3)', () => {
        const steps = PlaceholderWizard.buildSteps(
            '{{m:f1}} {{m:f2}} {{m:f3}} {{m:f4}} {{m:f5}} {{m:f6}}'
        );
        expect(steps).toHaveLength(2);
        expect(steps[0]).toHaveLength(3);
        expect(steps[1]).toHaveLength(3);
    });

    it('T12: o:-Felder erscheinen nach allen m:-Feldern', () => {
        const steps = PlaceholderWizard.buildSteps(
            '{{o:opt1}} {{m:mand1}} {{m:mand2}} {{o:opt2}}'
        );
        const allFields = steps.flat();
        const types = allFields.map(f => f.type);
        // Alle m: kommen vor allen o:
        const lastM = types.lastIndexOf('m');
        const firstO = types.indexOf('o');
        expect(firstO).toBeGreaterThan(lastM);
    });
});

// ---------------------------------------------------------------------------
// T06-T08: stepIndexForField()
// ---------------------------------------------------------------------------

describe('stepIndexForField()', () => {

    it('T06: Feld in Schritt 0 -> 0', () => {
        const steps = [
            [{ name: 'alpha' }, { name: 'beta' }],
            [{ name: 'gamma' }],
        ];
        expect(PlaceholderWizard.stepIndexForField(steps, 'alpha')).toBe(0);
        expect(PlaceholderWizard.stepIndexForField(steps, 'beta')).toBe(0);
    });

    it('T07: Feld in Schritt 1 -> 1', () => {
        const steps = [
            [{ name: 'alpha' }],
            [{ name: 'gamma' }],
        ];
        expect(PlaceholderWizard.stepIndexForField(steps, 'gamma')).toBe(1);
    });

    it('T08: unbekanntes Feld -> 0 (Fallback)', () => {
        const steps = [[{ name: 'alpha' }]];
        expect(PlaceholderWizard.stepIndexForField(steps, 'unbekannt')).toBe(0);
    });
});

// ---------------------------------------------------------------------------
// T13-T22: Phase 6 — Sidebar-Formular (showPlaceholderForm, focusBlock)
// Beleg: Bauplan B6 v0.5 §4.4.3, Projektgespraech 2026-05-06
// ---------------------------------------------------------------------------

describe('Phase 6 — Sidebar-Formular', () => {

    // Hilfsfunktionen
    function _mkBlock(overrides = {}) {
        return {
            block_id:                'blk-001',
            block_type:              'paragraph',
            block_data:              '{"text":"Nutzer {{m:vorname||Vorname}} ist aktiv."}',
            placeholder_values_json: null,
            author:                  'h001',
            ...overrides,
        };
    }

    function _mkOpts(overrides = {}) {
        return {
            myUsername: 'h001',
            onSave:     async () => {},
            ...overrides,
        };
    }

    function _setupBody() {
        const body = document.createElement('div');
        body.id = 'accordion-body-form';
        document.body.appendChild(body);
        return body;
    }

    afterEach(() => {
        document.getElementById('accordion-body-form')?.remove();
    });

    it('T13: showPlaceholderForm ist exportiert', () => {
        expect(typeof window.PlaceholderWizard.showPlaceholderForm).toBe('function');
    });

    it('T14: focusBlock ist exportiert', () => {
        expect(typeof window.PlaceholderWizard.focusBlock).toBe('function');
    });

    it('T15: showPlaceholderForm() mit leeren Bloecken zeigt Leer-Zustand', () => {
        const body = _setupBody();
        window.PlaceholderWizard.showPlaceholderForm([], null, _mkOpts());
        expect(body.innerHTML).toContain('pf-empty-state');
    });

    it('T16: showPlaceholderForm() rendert Block-Gruppen', () => {
        const body = _setupBody();
        const block = _mkBlock();
        window.PlaceholderWizard.showPlaceholderForm([block], 'blk-001', _mkOpts());
        expect(body.querySelectorAll('.pf-block-group')).toHaveLength(1);
    });

    it('T17: fokussierter Block hat pf-block-group--focused', () => {
        const body = _setupBody();
        const blocks = [
            _mkBlock({ block_id: 'blk-001' }),
            _mkBlock({ block_id: 'blk-002', block_data: '{"text":"{{m:feld2}}"}' }),
        ];
        window.PlaceholderWizard.showPlaceholderForm(blocks, 'blk-001', _mkOpts());
        const focused = body.querySelector('[data-block-id="blk-001"]');
        const blurred = body.querySelector('[data-block-id="blk-002"]');
        expect(focused?.classList.contains('pf-block-group--focused')).toBe(true);
        expect(blurred?.classList.contains('pf-block-group--blurred')).toBe(true);
    });

    it('T18: m:-Felder erhalten roten Asterisk (pf-required)', () => {
        const body = _setupBody();
        window.PlaceholderWizard.showPlaceholderForm(
            [_mkBlock()], 'blk-001', _mkOpts()
        );
        expect(body.querySelector('.pf-required')).not.toBeNull();
    });

    it('T19: a:-Felder werden nicht angezeigt', () => {
        const body = _setupBody();
        window.PlaceholderWizard.showPlaceholderForm(
            [_mkBlock({ block_data: '{"text":"Nutzer {{a:user.username}}"}' })],
            'blk-001', _mkOpts()
        );
        // Kein Eingabefeld fuer a:-Felder
        expect(body.querySelectorAll('.pf-input')).toHaveLength(0);
    });

    it('T20: Block ohne Platzhalter zeigt "Keine Platzhalter"', () => {
        const body = _setupBody();
        window.PlaceholderWizard.showPlaceholderForm(
            [_mkBlock({ block_data: '{"text":"Normaler Text ohne Chips."}' })],
            'blk-001', _mkOpts()
        );
        expect(body.innerHTML).toContain('Keine Platzhalter');
    });

    it('T21: Vorhandener Wert wird in Eingabefeld angezeigt', () => {
        const body = _setupBody();
        const block = _mkBlock({
            placeholder_values_json: '{"vorname":"Max"}',
        });
        window.PlaceholderWizard.showPlaceholderForm([block], 'blk-001', _mkOpts());
        const input = body.querySelector('.pf-input');
        expect(input?.value).toBe('Max');
    });

    it('T22: focusBlock() verschiebt Fokus-Klasse auf anderen Block', () => {
        const body = _setupBody();
        const blocks = [
            _mkBlock({ block_id: 'blk-001' }),
            _mkBlock({ block_id: 'blk-002', block_data: '{"text":"{{m:feld2}}"}' }),
        ];
        window.PlaceholderWizard.showPlaceholderForm(blocks, 'blk-001', _mkOpts());

        // Jetzt auf blk-002 fokussieren
        window.PlaceholderWizard.focusBlock('blk-002');

        const b1 = body.querySelector('[data-block-id="blk-001"]');
        const b2 = body.querySelector('[data-block-id="blk-002"]');
        expect(b2?.classList.contains('pf-block-group--focused')).toBe(true);
        expect(b1?.classList.contains('pf-block-group--blurred')).toBe(true);
    });
});
