/**
 * tests/unit/test_lock_layer.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Unit-Tests für LockLayer (Layer 4).
 *
 * T01 — Initialzustand ist UNINITIALIZED
 * T02 — ready-Promise löst sich auf wenn ReportLayer.ready aufgelöst ist
 * T03 — Nach ready ist Zustand IDLE
 * T04 — contributeToContext() gibt { lockId: null } im IDLE
 * T05 — acquire() → MINE bei 200-Antwort
 * T06 — acquire() setzt lockId und schreibt sessionStorage
 * T07 — acquire() feuert Up-Event 'acquired'
 * T08 — contributeToContext() gibt { lockId } nach acquire()
 * T09 — acquire() → IDLE + 'contested' bei 423-Antwort
 * T10 — acquire() → IDLE + 'error' bei Netzwerkfehler
 * T11 — release() → IDLE + 'released', löscht sessionStorage
 * T12 — release(sync=true) ruft sendBeacon auf
 * T13 — release() aus falschem Zustand wird ignoriert
 * T14 — joinQueue() → QUEUED + 'queued' bei 200-Antwort
 * T15 — leaveQueue() → IDLE aus QUEUED
 * T16 — SSE lock_acquired → MINE aus QUEUED
 * T17 — SSE lock_acquired enthält lock_id → wird übernommen
 * T18 — SSE lock_takeover_request → TAKEOVER_REQUEST_IN aus MINE
 * T19 — respondTakeover(true) → RELEASING → IDLE (grant)
 * T20 — respondTakeover(false) → MINE (deny)
 * T21 — SSE lock_takeover_result granted → wartet auf lock_acquired
 * T22 — SSE lock_takeover_result denied → TAKEOVER_DENIED
 * T23 — requestTakeover() → TAKEOVER_PENDING bei 200
 * T24 — requestTakeover() → TAKEOVER_DENIED bei 429 (Cooldown)
 * T25 — SSE disconnected → Kollaps auf IDLE (war MINE → über RELEASING)
 * T26 — ReportLayer idle → Kollaps auf IDLE
 * T27 — ReportLayer created → MINE mit lock_id aus Event
 * T28 — acquire() in ACQUIRING wird ignoriert (Re-Entry-Guard)
 * T29 — SSE editor_lock_released während MINE → IDLE
 * T30 — sessionStorage-Key ist 'forensic_lock_v2'
 *
 * Version: v0.6.250 · Build: 250 · 2026-05-24
 * Beleg: Layer 4 States, SLA Manifest, Paket 7
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readFileSync } from 'fs';
import { JSDOM } from 'jsdom';

// ---------------------------------------------------------------------------
// Mock-Hilfsfunktionen
// ---------------------------------------------------------------------------

function makeMockSseLayer(opts = {}) {
    let _readyResolve;
    const ready = new Promise(r => { _readyResolve = r; });
    const listeners = {};
    return {
        clientId: opts.clientId ?? 'sse-client-mock',
        ready,
        _resolveReady: () => _readyResolve(),
        on(name, fn) {
            if (!listeners[name]) listeners[name] = [];
            listeners[name].push(fn);
        },
        off(name, fn) {
            if (!listeners[name]) return;
            listeners[name] = listeners[name].filter(f => f !== fn);
        },
        _emit(name, payload) {
            (listeners[name] || []).forEach(fn => fn(payload));
        },
    };
}

function makeMockReportLayer(opts = {}) {
    let _readyResolve;
    const ready = new Promise(r => { _readyResolve = r; });
    const listeners = {};
    return {
        reportId: opts.reportId ?? 7,
        ready,
        _resolveReady: () => _readyResolve(),
        on(name, fn) {
            if (!listeners[name]) listeners[name] = [];
            listeners[name].push(fn);
        },
        off(name, fn) {
            if (!listeners[name]) return;
            listeners[name] = listeners[name].filter(f => f !== fn);
        },
        _emit(name, payload) {
            (listeners[name] || []).forEach(fn => fn(payload));
        },
    };
}

/** Minimales sessionStorage-Mock (Map-basiert). */
function makeSessionStorage() {
    const store = new Map();
    return {
        getItem:    (k)    => store.get(k) ?? null,
        setItem:    (k, v) => store.set(k, v),
        removeItem: (k)    => store.delete(k),
        clear:      ()     => store.clear(),
        _store: store,
    };
}

// ---------------------------------------------------------------------------
// JSDOM-Setup
// ---------------------------------------------------------------------------

function buildDom(sse, report, fetchFn, storage) {
    const src = readFileSync('userinfo/lock_layer.js', 'utf-8');
    const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
        runScripts: 'dangerously',
        url: 'http://127.0.0.2:8080',
    });
    dom.window.FORENSIC_DEBUG = false;
    dom.window.eval(src);

    const LockLayer = dom.window.LockLayer;
    const layer = new LockLayer({
        sseLayer:       sse,
        reportLayer:    report,
        debug:          false,
        fetchFn:        fetchFn ?? (() => Promise.reject(new Error('fetch nicht gemockt'))),
        sessionStorage: storage ?? makeSessionStorage(),
    });
    return { dom, layer };
}

function mockAcquireOk(lockId = 'lock-test-id') {
    return vi.fn().mockResolvedValue({
        ok:     true,
        status: 200,
        json:   () => Promise.resolve({ lock_id: lockId }),
    });
}

function mockAcquire423(lockedBy = 'h002', cooldownUntil = null, queueLength = 0) {
    return vi.fn().mockResolvedValue({
        ok:     false,
        status: 423,
        json:   () => Promise.resolve({
            code: 'LOCK_CONFLICT', locked_by: lockedBy,
            cooldown_until: cooldownUntil, queue_length: queueLength,
        }),
    });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LockLayer — Initialzustand', () => {

    it('T01 — Initialzustand ist UNINITIALIZED', () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep);
        expect(layer.state).toBe('UNINITIALIZED');
        expect(layer.lockId).toBeNull();
    });

    it('T02 — ready-Promise löst sich auf wenn ReportLayer.ready aufgelöst ist', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep);
        let resolved = false;
        layer.ready.then(() => { resolved = true; });
        expect(resolved).toBe(false);
        rep._resolveReady();
        await layer.ready;
        expect(resolved).toBe(true);
    });

    it('T03 — Nach ready ist Zustand IDLE', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep);
        rep._resolveReady();
        await layer.ready;
        expect(layer.state).toBe('IDLE');
    });

    it('T04 — contributeToContext() gibt { lockId: null } im IDLE', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep);
        rep._resolveReady();
        await layer.ready;
        expect(layer.contributeToContext()).toEqual({ lockId: null });
    });

});

describe('LockLayer — acquire()', () => {

    it('T05 — acquire() → MINE bei 200-Antwort', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep, mockAcquireOk());
        rep._resolveReady(); await layer.ready;
        await layer.acquire();
        expect(layer.state).toBe('MINE');
    });

    it('T06 — acquire() setzt lockId und schreibt sessionStorage', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const storage = makeSessionStorage();
        const { layer } = buildDom(sse, rep, mockAcquireOk('uuid-abc'), storage);
        rep._resolveReady(); await layer.ready;
        await layer.acquire();
        expect(layer.lockId).toBe('uuid-abc');
        expect(storage.getItem('forensic_lock_v2')).toBe('uuid-abc');
    });

    it('T07 — acquire() feuert Up-Event "acquired"', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep, mockAcquireOk('lid-007'));
        rep._resolveReady(); await layer.ready;
        let received = null;
        layer.on('acquired', p => { received = p; });
        await layer.acquire();
        expect(received).not.toBeNull();
        expect(received.lockId).toBe('lid-007');
    });

    it('T08 — contributeToContext() gibt { lockId } nach acquire()', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep, mockAcquireOk('ctx-lock'));
        rep._resolveReady(); await layer.ready;
        await layer.acquire();
        expect(layer.contributeToContext()).toEqual({ lockId: 'ctx-lock' });
    });

    it('T09 — acquire() → IDLE + "contested" bei 423', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep, mockAcquire423('h099', null, 2));
        rep._resolveReady(); await layer.ready;
        let contested = null;
        layer.on('contested', p => { contested = p; });
        await layer.acquire();
        expect(layer.state).toBe('IDLE');
        expect(contested.lockedBy).toBe('h099');
        expect(contested.queueLength).toBe(2);
    });

    it('T10 — acquire() → IDLE + "error" bei Netzwerkfehler', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn().mockRejectedValue(new Error('offline'));
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        let err = null;
        layer.on('error', p => { err = p; });
        await layer.acquire();
        expect(layer.state).toBe('IDLE');
        expect(err.code).toBe('NETWORK_ERROR');
    });

});

describe('LockLayer — release()', () => {

    async function layerInMine(lockId = 'lock-release') {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const storage = makeSessionStorage();
        const fetchFn = vi.fn()
            .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ lock_id: lockId }) })
            .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ freed: true }) });
        const { layer } = buildDom(sse, rep, fetchFn, storage);
        rep._resolveReady(); await layer.ready;
        await layer.acquire();
        return { layer, storage, fetchFn };
    }

    it('T11 — release() → IDLE + "released", löscht sessionStorage', async () => {
        const { layer, storage } = await layerInMine();
        let released = false;
        layer.on('released', () => { released = true; });
        layer.release();
        await new Promise(r => setTimeout(r, 10));
        expect(layer.state).toBe('IDLE');
        expect(layer.lockId).toBeNull();
        expect(storage.getItem('forensic_lock_v2')).toBeNull();
        expect(released).toBe(true);
    });

    it('T12 — release(sync=true) ruft sendBeacon auf', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const storage = makeSessionStorage();
        const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
            runScripts: 'dangerously', url: 'http://127.0.0.2:8080',
        });
        dom.window.FORENSIC_DEBUG = false;
        // sendBeacon-Mock
        const beaconCalls = [];
        dom.window.navigator.sendBeacon = (...args) => { beaconCalls.push(args); return true; };
        dom.window.eval(readFileSync('userinfo/lock_layer.js', 'utf-8'));
        const fetchFn = vi.fn().mockResolvedValue({
            ok: true, status: 200, json: () => Promise.resolve({ lock_id: 'sync-lock' }),
        });
        const layer = new dom.window.LockLayer({
            sseLayer: sse, reportLayer: rep, debug: false,
            fetchFn, sessionStorage: storage,
        });
        rep._resolveReady(); await layer.ready;
        await layer.acquire();
        layer.release(true);
        expect(beaconCalls.length).toBe(1);
        expect(layer.state).toBe('IDLE');
    });

    it('T13 — release() aus IDLE wird ignoriert', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn();
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        layer.release(); // aus IDLE — darf nichts tun
        expect(fetchFn).not.toHaveBeenCalled();
        expect(layer.state).toBe('IDLE');
    });

});

describe('LockLayer — Queue', () => {

    it('T14 — joinQueue() → QUEUED + "queued"', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn().mockResolvedValue({
            ok: true, status: 200,
            json: () => Promise.resolve({ queued: true, position: 2 }),
        });
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        let queued = null;
        layer.on('queued', p => { queued = p; });
        await layer.joinQueue();
        expect(layer.state).toBe('QUEUED');
        expect(queued.position).toBe(2);
    });

    it('T15 — leaveQueue() → IDLE aus QUEUED', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn()
            .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ queued: true, position: 1 }) })
            .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ ok: true }) });
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        await layer.joinQueue();
        await layer.leaveQueue();
        expect(layer.state).toBe('IDLE');
    });

});

describe('LockLayer — SSE-Events', () => {

    it('T16 — SSE lock_acquired → MINE aus QUEUED', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn().mockResolvedValue({
            ok: true, json: () => Promise.resolve({ queued: true, position: 1 }),
        });
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        await layer.joinQueue();
        expect(layer.state).toBe('QUEUED');

        sse._emit('sse_event', { name: 'lock_acquired', data: { report_id: 7, lock_id: 'queue-lock' } });
        expect(layer.state).toBe('MINE');
    });

    it('T17 — SSE lock_acquired enthält lock_id → wird übernommen', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn().mockResolvedValue({
            ok: true, json: () => Promise.resolve({ queued: true, position: 1 }),
        });
        const storage = makeSessionStorage();
        const { layer } = buildDom(sse, rep, fetchFn, storage);
        rep._resolveReady(); await layer.ready;
        await layer.joinQueue();

        sse._emit('sse_event', { name: 'lock_acquired', data: { report_id: 7, lock_id: 'secret-xyz' } });
        expect(layer.lockId).toBe('secret-xyz');
        expect(storage.getItem('forensic_lock_v2')).toBe('secret-xyz');
    });

    it('T18 — SSE lock_takeover_request → TAKEOVER_REQUEST_IN aus MINE', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep, mockAcquireOk());
        rep._resolveReady(); await layer.ready;
        await layer.acquire();

        let evt = null;
        layer.on('takeover_request', p => { evt = p; });
        sse._emit('sse_event', {
            name: 'lock_takeover_request',
            data: { report_id: 7, request_id: 42, requested_by: 'h099', requested_at: 1000 },
        });
        expect(layer.state).toBe('TAKEOVER_REQUEST_IN');
        expect(evt.requestedBy).toBe('h099');
        expect(evt.requestId).toBe(42);
    });

    it('T29 — SSE editor_lock_released während MINE → IDLE', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep, mockAcquireOk());
        rep._resolveReady(); await layer.ready;
        await layer.acquire();
        expect(layer.state).toBe('MINE');

        sse._emit('sse_event', { name: 'editor_lock_released', data: {} });
        expect(layer.state).toBe('IDLE');
        expect(layer.lockId).toBeNull();
    });

});

describe('LockLayer — Takeover', () => {

    it('T19 — respondTakeover(true) → RELEASING → IDLE (grant)', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn()
            .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ lock_id: 'mine' }) })
            .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ granted: true }) })
            .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ freed: true }) });
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        await layer.acquire();

        // Takeover-Anfrage simulieren
        sse._emit('sse_event', {
            name: 'lock_takeover_request',
            data: { request_id: 5, requested_by: 'h050', requested_at: 1000 },
        });
        expect(layer.state).toBe('TAKEOVER_REQUEST_IN');

        await layer.respondTakeover(true);
        await new Promise(r => setTimeout(r, 10));
        expect(layer.state).toBe('IDLE');
        expect(layer.lockId).toBeNull();
    });

    it('T20 — respondTakeover(false) → zurück nach MINE (deny)', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn()
            .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ lock_id: 'mine' }) })
            .mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve({ denied: true, cooldown_until: 9999 }) });
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        await layer.acquire();

        sse._emit('sse_event', {
            name: 'lock_takeover_request',
            data: { request_id: 6, requested_by: 'h060', requested_at: 1000 },
        });
        await layer.respondTakeover(false);
        expect(layer.state).toBe('MINE');
    });

    it('T21 — SSE lock_takeover_result granted → wartet auf lock_acquired', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn().mockResolvedValue({
            ok: true, json: () => Promise.resolve({ request_id: 10, countdown: 60 }),
        });
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;

        // Manuell in TAKEOVER_PENDING versetzen
        await layer.requestTakeover();
        expect(layer.state).toBe('TAKEOVER_PENDING');

        // granted-Result — Zustand bleibt TAKEOVER_PENDING bis lock_acquired kommt
        sse._emit('sse_event', { name: 'lock_takeover_result', data: { result: 'granted' } });
        expect(layer.state).toBe('TAKEOVER_PENDING');

        // Jetzt kommt lock_acquired
        sse._emit('sse_event', { name: 'lock_acquired', data: { lock_id: 'new-lock' } });
        expect(layer.state).toBe('MINE');
        expect(layer.lockId).toBe('new-lock');
    });

    it('T22 — SSE lock_takeover_result denied → TAKEOVER_DENIED', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn().mockResolvedValue({
            ok: true, json: () => Promise.resolve({ request_id: 11, countdown: 60 }),
        });
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        await layer.requestTakeover();

        let denied = null;
        layer.on('takeover_denied', p => { denied = p; });
        sse._emit('sse_event', { name: 'lock_takeover_result', data: { result: 'denied' } });
        expect(layer.state).toBe('TAKEOVER_DENIED');
        expect(denied).not.toBeNull();
    });

    it('T23 — requestTakeover() → TAKEOVER_PENDING bei 200', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn().mockResolvedValue({
            ok: true, status: 200,
            json: () => Promise.resolve({ request_id: 99, countdown: 60 }),
        });
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        let pending = null;
        layer.on('takeover_pending', p => { pending = p; });
        await layer.requestTakeover();
        expect(layer.state).toBe('TAKEOVER_PENDING');
        expect(pending.countdown).toBe(60);
    });

    it('T24 — requestTakeover() → TAKEOVER_DENIED bei 429 (Cooldown)', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const fetchFn = vi.fn().mockResolvedValue({
            ok: false, status: 429,
            json: () => Promise.resolve({ code: 'COOLDOWN_ACTIVE', cooldown_until: 99999 }),
        });
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;
        let denied = null;
        layer.on('takeover_denied', p => { denied = p; });
        await layer.requestTakeover();
        expect(layer.state).toBe('TAKEOVER_DENIED');
        expect(denied.cooldownUntil).toBe(99999);
    });

});

describe('LockLayer — Kollaps', () => {

    it('T25 — SSE disconnected → Kollaps auf IDLE (war MINE)', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep, mockAcquireOk());
        rep._resolveReady(); await layer.ready;
        await layer.acquire();
        expect(layer.state).toBe('MINE');

        let released = false;
        layer.on('released', () => { released = true; });
        sse._emit('disconnected', {});
        expect(layer.state).toBe('IDLE');
        expect(layer.lockId).toBeNull();
        expect(released).toBe(true);
    });

    it('T26 — ReportLayer idle → Kollaps auf IDLE', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const { layer } = buildDom(sse, rep, mockAcquireOk());
        rep._resolveReady(); await layer.ready;
        await layer.acquire();

        rep._emit('idle', {});
        expect(layer.state).toBe('IDLE');
    });

    it('T27 — ReportLayer created → MINE mit lock_id aus Event', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const storage = makeSessionStorage();
        const { layer } = buildDom(sse, rep, vi.fn(), storage);
        rep._resolveReady(); await layer.ready;

        let acquired = null;
        layer.on('acquired', p => { acquired = p; });
        rep._emit('created', { reportId: 5, lockId: 'created-lock', title: 'T' });

        expect(layer.state).toBe('MINE');
        expect(layer.lockId).toBe('created-lock');
        expect(storage.getItem('forensic_lock_v2')).toBe('created-lock');
        expect(acquired.lockId).toBe('created-lock');
    });

});

describe('LockLayer — Re-Entry-Guard und sessionStorage', () => {

    it('T28 — acquire() in ACQUIRING wird ignoriert', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        let resolveFirst;
        const fetchFn = vi.fn().mockReturnValue(
            new Promise(r => { resolveFirst = r; })
        );
        const { layer } = buildDom(sse, rep, fetchFn);
        rep._resolveReady(); await layer.ready;

        layer.acquire(); // geht in ACQUIRING, hält
        const secondCall = layer.acquire(); // darf nicht feuern

        expect(fetchFn).toHaveBeenCalledTimes(1);
        resolveFirst({ ok: false, status: 500, json: () => Promise.resolve({ code: 'X' }) });
        await secondCall;
    });

    it('T30 — sessionStorage-Key ist "forensic_lock_v2"', async () => {
        const sse = makeMockSseLayer(); const rep = makeMockReportLayer();
        const storage = makeSessionStorage();
        const { layer } = buildDom(sse, rep, mockAcquireOk('v2-key-test'), storage);
        rep._resolveReady(); await layer.ready;
        await layer.acquire();

        // Alter Key darf nicht gesetzt sein
        expect(storage.getItem('forensic_lock_id')).toBeNull();
        // Neuer Key muss gesetzt sein
        expect(storage.getItem('forensic_lock_v2')).toBe('v2-key-test');
    });

});
