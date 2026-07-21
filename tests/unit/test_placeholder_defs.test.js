/**
 * tests/unit/test_placeholder_defs.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer userinfo/placeholder_defs.js (Build 494).
 * window.PlaceholderDefs laedt die m/o-Platzhalterdefinitionen aus
 * GET /_forensic/placeholders/library und indiziert sie nach id.
 *
 * T01 -- _setForTest/get: m/o werden indiziert, a wird ausgelassen
 * T02 -- get(): unbekannte id -> null
 * T03 -- isLoaded(): vor/nach _setForTest
 * T04 -- all(): flache Kopie, aendert den internen Zustand nicht
 * T05 -- load(): erfolgreicher fetch -> Index aus m/o
 * T06 -- load(): HTTP-Fehler -> {} (geladen, aber leer), get -> null
 * T07 -- load(): Mehrfachaufruf teilt EIN Versprechen (nur ein fetch)
 *
 * Version: v0.8.494 · Build: 494 · 2026-07-21
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import '../../userinfo/placeholder_defs.js';

let PD;
beforeEach(() => {
    PD = window.PlaceholderDefs;
    // internen Zustand zuruecksetzen (frisch geladen simulieren)
    PD._setForTest([]);
});

const LIB = [
    { id: 'spurennummer', type: 'm', validation: '^AIW[0-9]+$', validation_type: 'regex',
      title: 'Spur', description: 'Spurennummer', default_value: null },
    { id: 'ampel', type: 'o', validation: '["rot","gelb","gruen"]', validation_type: 'list',
      title: 'Ampel', description: '', default_value: 'gruen' },
    { id: 'user.username', type: 'a', validation: null, validation_type: null,
      title: 'User', description: '', default_value: null },
];

describe('PlaceholderDefs — Index/Zugriff', () => {
    it('T01: m/o indiziert, a ausgelassen', () => {
        PD._setForTest(LIB);
        expect(PD.get('spurennummer').validation_type).toBe('regex');
        expect(PD.get('ampel').validation_type).toBe('list');
        expect(PD.get('user.username')).toBeNull();   // a nimmt nicht teil
    });

    it('T02: unbekannte id -> null', () => {
        PD._setForTest(LIB);
        expect(PD.get('gibtsnicht')).toBeNull();
        expect(PD.get(null)).toBeNull();
    });

    it('T03: isLoaded()', () => {
        PD._setForTest(LIB);
        expect(PD.isLoaded()).toBe(true);
    });

    it('T04: all() ist eine flache Kopie', () => {
        PD._setForTest(LIB);
        const a = PD.all();
        delete a['spurennummer'];
        expect(PD.get('spurennummer')).not.toBeNull();  // Original unberuehrt
    });
});

describe('PlaceholderDefs — load()', () => {
    it('T05: erfolgreicher fetch -> Index aus m/o', async () => {
        PD._resetForTest();
        globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => LIB }));
        await PD.load();
        expect(PD.get('spurennummer').validation_type).toBe('regex');
        expect(PD.get('ampel').validation_type).toBe('list');
        expect(PD.get('user.username')).toBeNull();   // a ausgelassen
        expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    });

    it('T06: HTTP-Fehler -> leerer Index, get null, aber isLoaded', async () => {
        PD._resetForTest();
        globalThis.fetch = vi.fn(async () => ({ ok: false, status: 500 }));
        await PD.load();
        expect(PD.get('spurennummer')).toBeNull();
        expect(PD.isLoaded()).toBe(true);
    });

    it('T07: Mehrfachaufruf teilt EIN Versprechen (nur ein fetch)', async () => {
        PD._resetForTest();
        globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => LIB }));
        await Promise.all([PD.load(), PD.load(), PD.load()]);
        expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    });

    it('T08: _setForTest mit gemischten Typen filtert korrekt', () => {
        PD._setForTest([
            { id: 'x', type: 'm', validation: 'a', validation_type: 'like' },
            { id: 'y', type: 'a' },
            { id: null, type: 'o' },   // ohne id -> ignoriert
        ]);
        expect(PD.get('x').validation_type).toBe('like');
        expect(PD.get('y')).toBeNull();
        expect(Object.keys(PD.all())).toEqual(['x']);
    });
});
