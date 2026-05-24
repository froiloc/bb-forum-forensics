/**
 * tests/unit/test_report_layer.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Unit-Tests für ReportLayer (Layer 3).
 *
 * T01 — Initialzustand ist UNINITIALIZED
 * T02 — ready-Promise löst sich auf sobald SSELayer.ready aufgelöst ist
 * T03 — Nach ready ist Zustand IDLE
 * T04 — contributeToContext() gibt { reportId: null } zurück im IDLE
 * T05 — open() wechselt in OPENING, dann OPENED bei 200-Antwort
 * T06 — open() setzt reportId, reportTitle, reportStatus, blocks korrekt
 * T07 — open() feuert Up-Event 'opened' mit korrekten Feldern
 * T08 — contributeToContext() gibt { reportId } zurück nach open()
 * T09 — open() → IDLE + Up-Event 'error' bei 404-Antwort
 * T10 — open() → IDLE + Up-Event 'error' bei Netzwerkfehler
 * T11 — create() wechselt in NEW, dann OPENED bei 200-Antwort
 * T12 — create() feuert Up-Event 'created' mit lock_id
 * T13 — create() → IDLE + 'error' bei fehlendem Titel
 * T14 — create() → IDLE + 'error' bei Server-Fehler
 * T15 — close() setzt Zustand auf IDLE und reportId auf null
 * T16 — close() feuert Up-Event 'idle'
 * T17 — SSE 'disconnected' → close() wird ausgelöst (ReportLayer auf IDLE)
 * T18 — SSE 'report_updated' → _reloadBlocks() wird aufgerufen
 * T19 — open() in OPENING wird ignoriert (kein Doppel-Request)
 * T20 — on()/off(): Listener korrekt registriert und entfernt
 *
 * Version: v0.6.249 · Build: 249 · 2026-05-24
 * Beleg: Layer 3 States, SLA Manifest, Paket 6
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readFileSync } from 'fs';
import { JSDOM } from 'jsdom';

// ---------------------------------------------------------------------------
// Mock-SSELayer
// ---------------------------------------------------------------------------

/**
 * Minimaler SSELayer-Mock für ReportLayer-Tests.
 * Gibt clientId zurück und stellt ready-Promise sowie on()/off() bereit.
 */
function makeMockSseLayer(opts = {}) {
    let _readyResolve;
    const ready = new Promise(r => { _readyResolve = r; });

    const listeners = {};
    const layer = {
        clientId: opts.clientId ?? 'mock-sse-client-id',
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
        /** Test-Hilfsmethode: simuliert ein Up-Event des SSELayer */
        _emit(name, payload) {
            (listeners[name] || []).forEach(fn => fn(payload));
        },
    };
    return layer;
}

// ---------------------------------------------------------------------------
// JSDOM-Setup
// ---------------------------------------------------------------------------

function buildDom(sseLayer, fetchFn) {
    const sseSrc    = readFileSync('userinfo/sse_layer.js',    'utf-8');
    const reportSrc = readFileSync('userinfo/report_layer.js', 'utf-8');

    const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
        runScripts: 'dangerously',
        url: 'http://127.0.0.2:8080',
    });
    dom.window.FORENSIC_DEBUG = false;

    // SSELayer-Klasse laden (für window.SSELayer)
    dom.window.eval(sseSrc);
    // ReportLayer-Klasse laden
    dom.window.eval(reportSrc);

    // ReportLayer instanziieren mit Mock-Abhängigkeiten
    const ReportLayer = dom.window.ReportLayer;
    const layer = new ReportLayer({
        sseLayer: sseLayer,
        debug:    false,
        fetchFn:  fetchFn ?? (() => Promise.reject(new Error('fetch nicht gemockt'))),
    });
    return { dom, layer };
}

/** Hilfsfunktion: fetch-Mock der eine erfolgreiche open_report-Antwort liefert */
function mockOpenFetch(overrides = {}) {
    return vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
            status:        'ok',
            report_id:     42,
            title:         'Testbericht',
            report_status: 'draft',
            report_type:   'interim',
            blocks: [
                { block_id: 'b1', block_type: 'paragraph', block_data: {}, sort_index: 0 },
            ],
            ...overrides,
        }),
    });
}

/** Hilfsfunktion: fetch-Mock der eine erfolgreiche new_report-Antwort liefert */
function mockCreateFetch(overrides = {}) {
    return vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({
            status:      'ok',
            report_id:   99,
            title:       'Neuer Bericht',
            report_type: 'interim',
            lock_id:     'lock-uuid-xyz',
            ...overrides,
        }),
    });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ReportLayer — Initialzustand', () => {

    it('T01 — Initialzustand ist UNINITIALIZED', () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse);
        expect(layer.state).toBe('UNINITIALIZED');
        expect(layer.reportId).toBeNull();
    });

    it('T02 — ready-Promise löst sich auf sobald SSELayer.ready aufgelöst ist', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse);

        let resolved = false;
        layer.ready.then(() => { resolved = true; });

        expect(resolved).toBe(false);
        sse._resolveReady();
        await layer.ready;
        expect(resolved).toBe(true);
    });

    it('T03 — Nach ready ist Zustand IDLE', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse);
        sse._resolveReady();
        await layer.ready;
        expect(layer.state).toBe('IDLE');
    });

    it('T04 — contributeToContext() gibt { reportId: null } im IDLE', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse);
        sse._resolveReady();
        await layer.ready;
        expect(layer.contributeToContext()).toEqual({ reportId: null });
    });

});

describe('ReportLayer — open()', () => {

    it('T05 — open() wechselt OPENING → OPENED', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockOpenFetch());
        sse._resolveReady();
        await layer.ready;

        const openPromise = layer.open(42);
        expect(layer.state).toBe('OPENING');
        await openPromise;
        expect(layer.state).toBe('OPENED');
    });

    it('T06 — open() setzt reportId, reportTitle, reportStatus und blocks', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockOpenFetch());
        sse._resolveReady();
        await layer.ready;
        await layer.open(42);

        expect(layer.reportId).toBe(42);
        expect(layer.reportTitle).toBe('Testbericht');
        expect(layer.reportStatus).toBe('draft');
        expect(layer.blocks).toHaveLength(1);
        expect(layer.blocks[0].block_id).toBe('b1');
    });

    it('T07 — open() feuert Up-Event "opened" mit korrekten Feldern', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockOpenFetch());
        sse._resolveReady();
        await layer.ready;

        let received = null;
        layer.on('opened', payload => { received = payload; });
        await layer.open(42);

        expect(received).not.toBeNull();
        expect(received.reportId).toBe(42);
        expect(received.title).toBe('Testbericht');
        expect(received.reportStatus).toBe('draft');
        expect(received.blocks).toHaveLength(1);
    });

    it('T08 — contributeToContext() gibt { reportId } nach open()', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockOpenFetch());
        sse._resolveReady();
        await layer.ready;
        await layer.open(42);

        expect(layer.contributeToContext()).toEqual({ reportId: 42 });
    });

    it('T09 — open() → IDLE + Up-Event "error" bei 404', async () => {
        const sse = makeMockSseLayer();
        const fetchFn = vi.fn().mockResolvedValue({
            ok:   false,
            json: () => Promise.resolve({ error: 'Nicht gefunden', code: 'REPORT_NOT_FOUND' }),
        });
        const { layer } = buildDom(sse, fetchFn);
        sse._resolveReady();
        await layer.ready;

        let err = null;
        layer.on('error', payload => { err = payload; });
        await layer.open(99);

        expect(layer.state).toBe('IDLE');
        expect(err).not.toBeNull();
        expect(err.code).toBe('REPORT_NOT_FOUND');
    });

    it('T10 — open() → IDLE + Up-Event "error" bei Netzwerkfehler', async () => {
        const sse = makeMockSseLayer();
        const fetchFn = vi.fn().mockRejectedValue(new Error('Netzwerk weg'));
        const { layer } = buildDom(sse, fetchFn);
        sse._resolveReady();
        await layer.ready;

        let err = null;
        layer.on('error', payload => { err = payload; });
        await layer.open(42);

        expect(layer.state).toBe('IDLE');
        expect(err.code).toBe('NETWORK_ERROR');
    });

});

describe('ReportLayer — create()', () => {

    it('T11 — create() wechselt NEW → OPENED', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockCreateFetch());
        sse._resolveReady();
        await layer.ready;

        const createPromise = layer.create('interim', 'Neuer Bericht');
        expect(layer.state).toBe('NEW');
        await createPromise;
        expect(layer.state).toBe('OPENED');
    });

    it('T12 — create() feuert Up-Event "created" mit lock_id', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockCreateFetch());
        sse._resolveReady();
        await layer.ready;

        let received = null;
        layer.on('created', payload => { received = payload; });
        await layer.create('interim', 'Neuer Bericht');

        expect(received).not.toBeNull();
        expect(received.reportId).toBe(99);
        expect(received.lockId).toBe('lock-uuid-xyz');
        expect(received.title).toBe('Neuer Bericht');
    });

    it('T13 — create() → IDLE + "error" bei fehlendem Titel', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse);
        sse._resolveReady();
        await layer.ready;

        let err = null;
        layer.on('error', payload => { err = payload; });
        await layer.create('interim', '');

        expect(layer.state).toBe('IDLE');
        expect(err.code).toBe('MISSING_TITLE');
    });

    it('T14 — create() → IDLE + "error" bei Server-Fehler', async () => {
        const sse = makeMockSseLayer();
        const fetchFn = vi.fn().mockResolvedValue({
            ok:   false,
            json: () => Promise.resolve({ error: 'DB-Fehler', code: 'DB_ERROR' }),
        });
        const { layer } = buildDom(sse, fetchFn);
        sse._resolveReady();
        await layer.ready;

        let err = null;
        layer.on('error', payload => { err = payload; });
        await layer.create('interim', 'Titel');

        expect(layer.state).toBe('IDLE');
        expect(err.code).toBe('DB_ERROR');
    });

});

describe('ReportLayer — close()', () => {

    it('T15 — close() setzt Zustand IDLE und reportId null', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockOpenFetch());
        sse._resolveReady();
        await layer.ready;
        await layer.open(42);
        expect(layer.state).toBe('OPENED');

        layer.close();
        expect(layer.state).toBe('IDLE');
        expect(layer.reportId).toBeNull();
        expect(layer.blocks).toHaveLength(0);
    });

    it('T16 — close() feuert Up-Event "idle"', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockOpenFetch());
        sse._resolveReady();
        await layer.ready;
        await layer.open(42);

        let idleFired = false;
        layer.on('idle', () => { idleFired = true; });
        layer.close();
        expect(idleFired).toBe(true);
    });

});

describe('ReportLayer — SSE-Integration', () => {

    it('T17 — SSE "disconnected" → ReportLayer auf IDLE', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockOpenFetch());
        sse._resolveReady();
        await layer.ready;
        await layer.open(42);
        expect(layer.state).toBe('OPENED');

        // SSELayer sendet disconnected-Event
        sse._emit('disconnected', {});
        expect(layer.state).toBe('IDLE');
        expect(layer.reportId).toBeNull();
    });

    it('T18 — SSE "report_updated" → _reloadBlocks() wird aufgerufen', async () => {
        const sse = makeMockSseLayer();
        // fetchFn wird zweimal aufgerufen: einmal für open(), einmal für _reloadBlocks()
        const reloadData = {
            reports: [{
                id:     42,
                blocks: [
                    { block_id: 'b1', block_type: 'paragraph', block_data: {}, sort_index: 0 },
                    { block_id: 'b2', block_type: 'paragraph', block_data: {}, sort_index: 1 },
                ],
            }],
        };
        const fetchFn = vi.fn()
            .mockResolvedValueOnce({
                ok:   true,
                json: () => Promise.resolve({
                    status: 'ok', report_id: 42, title: 'T',
                    report_status: 'draft', report_type: 'interim', blocks: [],
                }),
            })
            .mockResolvedValueOnce({
                ok:   true,
                json: () => Promise.resolve(reloadData),
            });

        const { layer } = buildDom(sse, fetchFn);
        sse._resolveReady();
        await layer.ready;
        await layer.open(42);

        let openedCount = 0;
        layer.on('opened', () => { openedCount++; });

        // SSELayer sendet report_updated
        sse._emit('sse_event', { name: 'report_updated', data: {} });

        // _reloadBlocks ist async — kurz warten
        await new Promise(r => setTimeout(r, 10));

        expect(fetchFn).toHaveBeenCalledTimes(2);
        expect(openedCount).toBe(1); // 'opened' nach Reload
    });

});

describe('ReportLayer — open() in OPENING ignoriert', () => {

    it('T19 — open() in OPENING wird ignoriert', async () => {
        const sse = makeMockSseLayer();
        // fetch gibt nie auf — hält OPENING aufrecht
        let resolveFirst;
        const fetchFn = vi.fn().mockReturnValue(
            new Promise(r => { resolveFirst = r; })
        );
        const { layer } = buildDom(sse, fetchFn);
        sse._resolveReady();
        await layer.ready;

        layer.open(42); // startet, hält in OPENING
        expect(layer.state).toBe('OPENING');

        // Zweites open() ignoriert
        layer.open(99);
        expect(fetchFn).toHaveBeenCalledTimes(1);

        // Auflösen damit kein pending Promise bleibt
        resolveFirst({ ok: false, json: () => Promise.resolve({ code: 'X' }) });
    });

});

describe('ReportLayer — on()/off()', () => {

    it('T20 — on()/off(): Listener korrekt registriert und entfernt', async () => {
        const sse = makeMockSseLayer();
        const { layer } = buildDom(sse, mockOpenFetch());
        sse._resolveReady();
        await layer.ready;

        let count = 0;
        const fn = () => { count++; };
        layer.on('opened', fn);
        await layer.open(42);
        expect(count).toBe(1);

        layer.off('opened', fn);
        layer.close();
        await layer.open(42);
        expect(count).toBe(1); // nicht erhöht
    });

});
