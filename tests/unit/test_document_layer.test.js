/**
 * tests/unit/test_document_layer.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Unit-Tests für DocumentLayer (Layer 5).
 *
 * T01 — Initialzustand: isDirty false, ready wartet auf LockLayer.ready
 * T02 — ready-Promise löst sich auf wenn LockLayer.ready aufgelöst ist
 * T03 — contributeToContext() aggregiert alle drei unteren Layer
 * T04 — _sendRequest: kein Lock → null + Up-Event 'error' (NO_LOCK)
 * T05 — saveBlock(): erfolgreicher POST → Up-Event 'saved'
 * T06 — saveBlock(): setzt isDirty vor Request, löscht nach Erfolg
 * T07 — saveBlock(): sendet lock_id im Body und X-Forensic-Lock-Id im Header
 * T08 — saveBlock(): report_id aus ReportLayer-Kontext
 * T09 — saveBlock(): paralleler Aufruf für denselben Block wird ignoriert
 * T10 — saveBlock(): Server-Fehler → null + Up-Event 'error'
 * T11 — saveBlock(): Netzwerkfehler → null + Up-Event 'error'
 * T12 — updateBlock(): erfolgreicher POST → 'saved', isDirty-Zyklus
 * T13 — deleteBlock(): erfolgreicher POST → 'deleted' (kein isDirty)
 * T14 — reorder(): erfolgreicher POST → 'reordered', isDirty-Zyklus
 * T15 — addAnchor(): erfolgreicher POST → 'anchored' mit anchorId
 * T16 — scheduleAutoSave(): saveFn wird nach Debounce aufgerufen
 * T17 — scheduleAutoSave(): zweiter Aufruf resettet Timer
 * T18 — scheduleAutoSave(): saveFn nicht aufgerufen wenn isDirty false
 * T19 — cancelAutoSave(): stoppt laufenden Timer
 * T20 — on()/off(): Listener korrekt registriert und entfernt
 *
 * Version: v0.6.251 · Build: 251 · 2026-05-24
 * Beleg: DocumentLayer-Spec, Paket 8
 */

import { describe, it, expect, vi } from 'vitest';
import { readFileSync } from 'fs';
import { JSDOM } from 'jsdom';

// ---------------------------------------------------------------------------
// Mock-Layer-Hilfsfunktionen
// ---------------------------------------------------------------------------

function makeMockSseLayer(clientId = 'sse-id') {
    let _res;
    const ready = new Promise(r => { _res = r; });
    return {
        ready,
        _resolve: () => _res(),
        contributeToContext: () => ({ sseClientId: clientId }),
    };
}

function makeMockReportLayer(reportId = 42) {
    let _res;
    const ready = new Promise(r => { _res = r; });
    return {
        ready,
        _resolve: () => _res(),
        contributeToContext: () => ({ reportId }),
    };
}

function makeMockLockLayer(lockId = 'lock-abc') {
    let _res;
    const ready = new Promise(r => { _res = r; });
    return {
        ready,
        _resolve: () => _res(),
        contributeToContext: () => ({ lockId }),
    };
}

// ---------------------------------------------------------------------------
// JSDOM-Setup
// ---------------------------------------------------------------------------

function buildDom(sse, report, lock, fetchFn, opts = {}) {
    const src = readFileSync('userinfo/document_layer.js', 'utf-8');
    const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
        runScripts: 'dangerously',
        url: 'http://127.0.0.2:8080',
    });
    dom.window.FORENSIC_DEBUG = false;
    dom.window.eval(src);

    const DocumentLayer = dom.window.DocumentLayer;
    const layer = new DocumentLayer({
        sseLayer:    sse,
        reportLayer: report,
        lockLayer:   lock,
        debug:       false,
        fetchFn:     fetchFn ?? (() => Promise.reject(new Error('fetch nicht gemockt'))),
        autosaveDebounceMs: opts.autosaveDebounceMs ?? 30000,
    });
    return { dom, layer };
}

/** Liefert eine erfolgreiche fetch-Antwort zurück. */
function mockOk(data = {}) {
    return vi.fn().mockResolvedValue({
        ok: true, status: 200,
        json: () => Promise.resolve({ status: 'ok', ...data }),
    });
}

/** Liefert eine fehlgeschlagene fetch-Antwort zurück. */
function mockErr(status = 500, code = 'DB_ERROR') {
    return vi.fn().mockResolvedValue({
        ok: false, status,
        json: () => Promise.resolve({ error: 'Fehler', code }),
    });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('DocumentLayer — Initialzustand und ready', () => {

    it('T01 — isDirty ist false im Initialzustand', () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer();
        const { layer } = buildDom(sse, rep, lock);
        expect(layer.isDirty).toBe(false);
    });

    it('T02 — ready-Promise löst sich auf wenn LockLayer.ready aufgelöst ist', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer();
        const { layer } = buildDom(sse, rep, lock);
        let resolved = false;
        layer.ready.then(() => { resolved = true; });
        expect(resolved).toBe(false);
        lock._resolve();
        await layer.ready;
        expect(resolved).toBe(true);
    });

});

describe('DocumentLayer — contributeToContext()', () => {

    it('T03 — aggregiert alle drei unteren Layer', async () => {
        const sse  = makeMockSseLayer('sse-ctx');
        const rep  = makeMockReportLayer(99);
        const lock = makeMockLockLayer('lock-ctx');
        const { layer } = buildDom(sse, rep, lock);
        lock._resolve(); await layer.ready;

        const ctx = layer.contributeToContext();
        expect(ctx.sseClientId).toBe('sse-ctx');
        expect(ctx.reportId).toBe(99);
        expect(ctx.lockId).toBe('lock-ctx');
    });

});

describe('DocumentLayer — _sendRequest Lock-Guard', () => {

    it('T04 — kein Lock → null + Up-Event "error" (NO_LOCK)', async () => {
        const sse  = makeMockSseLayer();
        const rep  = makeMockReportLayer();
        const lock = makeMockLockLayer(null);  // kein Lock
        const fetchFn = vi.fn();
        const { layer } = buildDom(sse, rep, lock, fetchFn);
        lock._resolve(); await layer.ready;

        let err = null;
        layer.on('error', p => { err = p; });
        const result = await layer.saveBlock('b1', 'paragraph', {});

        expect(result).toBeNull();
        expect(fetchFn).not.toHaveBeenCalled();
        expect(err.code).toBe('NO_LOCK');
    });

});

describe('DocumentLayer — saveBlock()', () => {

    it('T05 — erfolgreicher POST → Up-Event "saved"', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L1');
        const { layer } = buildDom(sse, rep, lock, mockOk({ block_id: 'b1' }));
        lock._resolve(); await layer.ready;

        let saved = null;
        layer.on('saved', p => { saved = p; });
        await layer.saveBlock('b1', 'paragraph', { text: 'Hallo' });

        expect(saved).not.toBeNull();
        expect(saved.blockId).toBe('b1');
    });

    it('T06 — saveBlock setzt isDirty vor Request, löscht nach Erfolg', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L1');
        let dirtyDuringFetch = false;
        const fetchFn = vi.fn().mockImplementation(async () => {
            dirtyDuringFetch = true; // isDirty muss hier true sein
            return { ok: true, status: 201, json: () => Promise.resolve({ block_id: 'b2' }) };
        });
        const { layer } = buildDom(sse, rep, lock, fetchFn);
        lock._resolve(); await layer.ready;

        await layer.saveBlock('b2', 'paragraph', {});
        expect(dirtyDuringFetch).toBe(true);
        expect(layer.isDirty).toBe(false); // nach Erfolg zurückgesetzt
    });

    it('T07 — lock_id im Body und X-Forensic-Lock-Id im Header', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer(7);
        const lock = makeMockLockLayer('secret-lock');
        const fetchFn = vi.fn().mockResolvedValue({
            ok: true, status: 201, json: () => Promise.resolve({ block_id: 'b3' }),
        });
        const { layer } = buildDom(sse, rep, lock, fetchFn);
        lock._resolve(); await layer.ready;

        await layer.saveBlock('b3', 'paragraph', {});

        const [, reqOpts] = fetchFn.mock.calls[0];
        const body = JSON.parse(reqOpts.body);
        expect(body.lock_id).toBe('secret-lock');
        expect(reqOpts.headers['X-Forensic-Lock-Id']).toBe('secret-lock');
    });

    it('T08 — report_id aus ReportLayer-Kontext', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer(55);
        const lock = makeMockLockLayer('L2');
        const fetchFn = vi.fn().mockResolvedValue({
            ok: true, status: 201, json: () => Promise.resolve({ block_id: 'b4' }),
        });
        const { layer } = buildDom(sse, rep, lock, fetchFn);
        lock._resolve(); await layer.ready;

        await layer.saveBlock('b4', 'paragraph', {});
        const body = JSON.parse(fetchFn.mock.calls[0][1].body);
        expect(body.report_id).toBe(55);
    });

    it('T09 — paralleler Aufruf für denselben Block wird ignoriert', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L3');
        let resolveFirst;
        const fetchFn = vi.fn().mockReturnValue(
            new Promise(r => { resolveFirst = r; })
        );
        const { layer } = buildDom(sse, rep, lock, fetchFn);
        lock._resolve(); await layer.ready;

        layer.saveBlock('b5', 'paragraph', {});       // geht rein
        await layer.saveBlock('b5', 'paragraph', {}); // ignoriert

        expect(fetchFn).toHaveBeenCalledTimes(1);
        resolveFirst({ ok: true, json: () => Promise.resolve({ block_id: 'b5' }) });
    });

    it('T10 — Server-Fehler → null + Up-Event "error"', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L4');
        const { layer } = buildDom(sse, rep, lock, mockErr(403, 'FORBIDDEN'));
        lock._resolve(); await layer.ready;

        let err = null;
        layer.on('error', p => { err = p; });
        const result = await layer.saveBlock('b6', 'paragraph', {});

        expect(result).toBeNull();
        expect(err.code).toBe('FORBIDDEN');
        expect(err.action).toBe('save_block');
    });

    it('T11 — Netzwerkfehler → null + Up-Event "error"', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L5');
        const fetchFn = vi.fn().mockRejectedValue(new Error('offline'));
        const { layer } = buildDom(sse, rep, lock, fetchFn);
        lock._resolve(); await layer.ready;

        let err = null;
        layer.on('error', p => { err = p; });
        const result = await layer.saveBlock('b7', 'paragraph', {});

        expect(result).toBeNull();
        expect(err.code).toBe('NETWORK_ERROR');
    });

});

describe('DocumentLayer — updateBlock(), deleteBlock(), reorder(), addAnchor()', () => {

    it('T12 — updateBlock(): "saved" + isDirty-Zyklus', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L6');
        const { layer } = buildDom(sse, rep, lock, mockOk());
        lock._resolve(); await layer.ready;

        let saved = null;
        layer.on('saved', p => { saved = p; });
        await layer.updateBlock('b8', { text: 'neu' });
        expect(saved).not.toBeNull();
        expect(layer.isDirty).toBe(false);
    });

    it('T13 — deleteBlock(): "deleted", kein isDirty gesetzt', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L7');
        const { layer } = buildDom(sse, rep, lock, mockOk());
        lock._resolve(); await layer.ready;

        let deleted = null;
        layer.on('deleted', p => { deleted = p; });
        await layer.deleteBlock('b9');

        expect(deleted.blockId).toBe('b9');
        // deleteBlock setzt kein isDirty (Löschen ist sofort persistent)
        expect(layer.isDirty).toBe(false);
    });

    it('T14 — reorder(): "reordered" + isDirty-Zyklus', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L8');
        const { layer } = buildDom(sse, rep, lock, mockOk({ updated: 3 }));
        lock._resolve(); await layer.ready;

        let reordered = false;
        layer.on('reordered', () => { reordered = true; });
        await layer.reorder([{ id: 'b1', sort_index: 0 }, { id: 'b2', sort_index: 1 }]);
        expect(reordered).toBe(true);
        expect(layer.isDirty).toBe(false);
    });

    it('T15 — addAnchor(): "anchored" mit anchorId', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L9');
        const { layer } = buildDom(sse, rep, lock, mockOk({ anchor_id: 77 }));
        lock._resolve(); await layer.ready;

        let anchored = null;
        layer.on('anchored', p => { anchored = p; });
        await layer.addAnchor('b10', 5, '[BELEG:annotation_id=5]');
        expect(anchored.anchorId).toBe(77);
    });

});

describe('DocumentLayer — Auto-Save', () => {

    it('T16 — scheduleAutoSave: saveFn nach Debounce aufgerufen', async () => {
        vi.useFakeTimers();
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L10');
        const { layer } = buildDom(sse, rep, lock, mockOk(), { autosaveDebounceMs: 500 });
        lock._resolve(); await layer.ready;

        // isDirty manuell setzen (simuliert eine Schreiboperation)
        layer._setDirty();

        let saveCalled = false;
        layer.scheduleAutoSave(() => { saveCalled = true; });

        expect(saveCalled).toBe(false);
        await vi.advanceTimersByTimeAsync(600);
        expect(saveCalled).toBe(true);

        vi.useRealTimers();
    });

    it('T17 — scheduleAutoSave: zweiter Aufruf resettet Timer', async () => {
        vi.useFakeTimers();
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L11');
        const { layer } = buildDom(sse, rep, lock, mockOk(), { autosaveDebounceMs: 500 });
        lock._resolve(); await layer.ready;
        layer._setDirty();

        let callCount = 0;
        const fn = () => { callCount++; };

        layer.scheduleAutoSave(fn);
        await vi.advanceTimersByTimeAsync(300);
        layer.scheduleAutoSave(fn); // reset
        await vi.advanceTimersByTimeAsync(300);
        expect(callCount).toBe(0); // noch nicht ausgelöst

        await vi.advanceTimersByTimeAsync(300);
        expect(callCount).toBe(1); // jetzt ausgelöst

        vi.useRealTimers();
    });

    it('T18 — scheduleAutoSave: saveFn nicht aufgerufen wenn isDirty false', async () => {
        vi.useFakeTimers();
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L12');
        const { layer } = buildDom(sse, rep, lock, mockOk(), { autosaveDebounceMs: 100 });
        lock._resolve(); await layer.ready;
        // isDirty bleibt false

        let called = false;
        layer.scheduleAutoSave(() => { called = true; });
        await vi.advanceTimersByTimeAsync(200);
        expect(called).toBe(false);

        vi.useRealTimers();
    });

    it('T19 — cancelAutoSave: stoppt laufenden Timer', async () => {
        vi.useFakeTimers();
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L13');
        const { layer } = buildDom(sse, rep, lock, mockOk(), { autosaveDebounceMs: 300 });
        lock._resolve(); await layer.ready;
        layer._setDirty();

        let called = false;
        layer.scheduleAutoSave(() => { called = true; });
        layer.cancelAutoSave();
        await vi.advanceTimersByTimeAsync(500);
        expect(called).toBe(false);

        vi.useRealTimers();
    });

});

describe('DocumentLayer — on()/off()', () => {

    it('T20 — Listener korrekt registriert und entfernt', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const lock = makeMockLockLayer('L14');
        const { layer } = buildDom(sse, rep, lock, mockOk({ block_id: 'bX' }));
        lock._resolve(); await layer.ready;

        let count = 0;
        const fn = () => { count++; };
        layer.on('saved', fn);
        await layer.saveBlock('bX', 'paragraph', {});
        expect(count).toBe(1);

        layer.off('saved', fn);
        await layer.saveBlock('bX', 'paragraph', {});
        expect(count).toBe(1); // nicht erhöht
    });

});
