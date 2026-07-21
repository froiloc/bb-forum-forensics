/**
 * tests/unit/test_validation_rules_typed.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer die typisierte DB-Validierung in userinfo/validation_rules.js
 * (Build 494: checkTyped/likeToRegExp; regex/list/like aus
 *  templates.placeholders.validation_type). Semantik deckungsgleich zur
 *  Management-Maske (cockpit_templates.js, Build 490).
 *
 * T01 -- checkTyped(): leere Pruefart -> ok (nichts zu pruefen)
 * T02 -- checkTyped(): leere Regel bei gesetzter Pruefart -> ok
 * T03 -- checkTyped('regex'): Treffer / kein Treffer
 * T04 -- checkTyped('regex'): fehlerhafte Regex -> nicht ok (Grundregel 1)
 * T05 -- checkTyped('list'): Mitgliedschaft exakt
 * T06 -- checkTyped('list'): kein JSON-Array -> nicht ok
 * T07 -- checkTyped('like'): % = beliebig viele Zeichen
 * T08 -- checkTyped('like'): _ = genau ein Zeichen
 * T09 -- checkTyped('like'): Full-Match (verankert, kein Teiltreffer)
 * T10 -- checkTyped('like'): Regex-Metazeichen werden literal behandelt
 * T11 -- checkTyped(): unbekannte Pruefart -> nicht ok
 * T12 -- likeToRegExp(): verankert und maskiert korrekt
 *
 * Version: v0.8.494 · Build: 494 · 2026-07-21
 * Beleg: mc-Entscheid 2026-07-21 (Klartext, list=JSON-Array).
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import '../../userinfo/validation_rules.js';

let VR;
beforeEach(() => { VR = window.ValidationRules; });

describe('checkTyped()', () => {
    it('T01: leere Pruefart -> ok', () => {
        expect(VR.checkTyped('', '', 'irgendwas').ok).toBe(true);
        expect(VR.checkTyped(null, null, 'x').ok).toBe(true);
    });

    it('T02: leere Regel bei gesetzter Pruefart -> ok', () => {
        expect(VR.checkTyped('regex', '   ', 'x').ok).toBe(true);
    });

    it('T03: regex Treffer / kein Treffer', () => {
        expect(VR.checkTyped('regex', '^AIW[0-9]+$', 'AIW123').ok).toBe(true);
        const bad = VR.checkTyped('regex', '^AIW[0-9]+$', 'XY');
        expect(bad.ok).toBe(false);
        expect(bad.message).toMatch(/Format/);
    });

    it('T04: fehlerhafte Regex -> nicht ok', () => {
        const r = VR.checkTyped('regex', '([', 'x');
        expect(r.ok).toBe(false);
        expect(r.message).toMatch(/fehlerhaft/);
    });

    it('T05: list Mitgliedschaft exakt', () => {
        const rule = JSON.stringify(['rot', 'gruen', 'blau']);
        expect(VR.checkTyped('list', rule, 'gruen').ok).toBe(true);
        const no = VR.checkTyped('list', rule, 'gelb');
        expect(no.ok).toBe(false);
        expect(no.message).toMatch(/Liste/);
        // Teiltreffer zaehlt NICHT
        expect(VR.checkTyped('list', rule, 'ro').ok).toBe(false);
    });

    it('T06: list kein JSON-Array -> nicht ok', () => {
        expect(VR.checkTyped('list', 'rot,gruen', 'rot').ok).toBe(false);
        expect(VR.checkTyped('list', '{"a":1}', 'rot').ok).toBe(false);
    });

    it('T07: like % = beliebig viele Zeichen', () => {
        expect(VR.checkTyped('like', 'AIW%', 'AIW-2024-1').ok).toBe(true);
        expect(VR.checkTyped('like', 'AIW%', 'AIW').ok).toBe(true);      // % = 0 Zeichen
        expect(VR.checkTyped('like', 'AIW%', 'XAIW').ok).toBe(false);
    });

    it('T08: like _ = genau ein Zeichen', () => {
        expect(VR.checkTyped('like', 'A_C', 'ABC').ok).toBe(true);
        expect(VR.checkTyped('like', 'A_C', 'AC').ok).toBe(false);       // fehlt eins
        expect(VR.checkTyped('like', 'A_C', 'ABBC').ok).toBe(false);     // zu viele
    });

    it('T09: like Full-Match (verankert)', () => {
        // Ohne %-Wildcards muss das ganze Feld exakt passen.
        expect(VR.checkTyped('like', 'ABC', 'ABC').ok).toBe(true);
        expect(VR.checkTyped('like', 'ABC', 'ABCD').ok).toBe(false);
    });

    it('T10: like behandelt Regex-Metazeichen literal', () => {
        // Der Punkt ist im LIKE-Muster ein echter Punkt, kein Regex-Any.
        expect(VR.checkTyped('like', 'a.b', 'a.b').ok).toBe(true);
        expect(VR.checkTyped('like', 'a.b', 'axb').ok).toBe(false);
    });

    it('T11: unbekannte Pruefart -> nicht ok', () => {
        const r = VR.checkTyped('zauber', 'x', 'x');
        expect(r.ok).toBe(false);
        expect(r.message).toMatch(/Prüfart/);
    });
});

describe('likeToRegExp()', () => {
    it('T12: verankert und maskiert korrekt', () => {
        const re = VR.likeToRegExp('a%b_c');
        expect(re.source.startsWith('^')).toBe(true);
        expect(re.source.endsWith('$')).toBe(true);
        expect(re.test('aXXXbYc')).toBe(true);
        expect(re.test('abYc')).toBe(true);     // % = 0
        expect(re.test('aXXXbc')).toBe(false);   // _ fehlt
    });
});
