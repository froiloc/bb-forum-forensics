/**
 * tests/unit/test_placeholder_reuse.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Testsuite fuer userinfo/placeholder_reuse.js (Build 495).
 * window.PlaceholderReuse: case-weite Wiederverwendung von m/o-Werten
 * (placeholder_cache Prefill/Writeback).
 *
 * T01 -- getCached(): aus _setForTest, leere/fehlende Werte -> null
 * T02 -- loadCache(): erfolgreicher fetch mergt in den lokalen Cache
 * T03 -- loadCache(): leere id-Menge -> kein fetch
 * T04 -- loadCache(): HTTP-Fehler -> Cache bleibt nutzbar (kein Wurf)
 * T05 -- writeback(): POST mit id/value, Erfolg aktualisiert lokalen Cache
 * T06 -- writeback(): HTTP 400 (nicht wiederverwendbar) -> false, kein Wurf
 * T07 -- writeback(): leere id -> false, kein fetch
 *
 * Version: v0.8.495 · Build: 495 · 2026-07-21
 */

/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import '../../userinfo/placeholder_reuse.js';

let PR;
beforeEach(() => {
    PR = window.PlaceholderReuse;
    PR._resetForTest();
    vi.restoreAllMocks();
});

describe('getCached()', () => {
    it('T01: liefert Werte, leere/fehlende -> null', () => {
        PR._setForTest({ spur: 'AIW-1', leer: '' });
        expect(PR.getCached('spur')).toBe('AIW-1');
        expect(PR.getCached('leer')).toBeNull();
        expect(PR.getCached('fehlt')).toBeNull();
        expect(PR.getCached(null)).toBeNull();
    });
});

describe('loadCache()', () => {
    it('T02: erfolgreicher fetch mergt in den lokalen Cache', async () => {
        globalThis.fetch = vi.fn(async () => ({
            ok: true, json: async () => ({ spur: 'AIW-9', ampel: 'gruen' }),
        }));
        await PR.loadCache(['spur', 'ampel']);
        expect(PR.getCached('spur')).toBe('AIW-9');
        expect(PR.getCached('ampel')).toBe('gruen');
        // ids landen in der Query
        const url = globalThis.fetch.mock.calls[0][0];
        expect(url).toContain('/_forensic/placeholders/cache?ids=');
    });

    it('T03: leere id-Menge -> kein fetch', async () => {
        globalThis.fetch = vi.fn();
        await PR.loadCache([]);
        expect(globalThis.fetch).not.toHaveBeenCalled();
        expect(PR.isLoaded()).toBe(true);
    });

    it('T04: HTTP-Fehler -> Cache nutzbar, kein Wurf', async () => {
        globalThis.fetch = vi.fn(async () => ({ ok: false, status: 500 }));
        await expect(PR.loadCache(['spur'])).resolves.toBeDefined();
        expect(PR.getCached('spur')).toBeNull();
        expect(PR.isLoaded()).toBe(true);
    });
});

describe('writeback()', () => {
    it('T05: POST mit id/value, Erfolg aktualisiert lokalen Cache', async () => {
        globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ ok: true }) }));
        const ok = await PR.writeback('spur', 'AIW-42');
        expect(ok).toBe(true);
        expect(PR.getCached('spur')).toBe('AIW-42');
        const [url, init] = globalThis.fetch.mock.calls[0];
        expect(url).toBe('/_forensic/placeholders/cache');
        expect(init.method).toBe('POST');
        expect(JSON.parse(init.body)).toEqual({ id: 'spur', value: 'AIW-42' });
    });

    it('T06: HTTP 400 (nicht wiederverwendbar) -> false, kein Cache-Eintrag', async () => {
        globalThis.fetch = vi.fn(async () => ({ ok: false, status: 400 }));
        const ok = await PR.writeback('unbekannt', 'x');
        expect(ok).toBe(false);
        expect(PR.getCached('unbekannt')).toBeNull();
    });

    it('T07: leere id -> false, kein fetch', async () => {
        globalThis.fetch = vi.fn();
        const ok = await PR.writeback('  ', 'x');
        expect(ok).toBe(false);
        expect(globalThis.fetch).not.toHaveBeenCalled();
    });
});
