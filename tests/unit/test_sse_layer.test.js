/**
 * tests/unit/test_sse_layer.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Unit-Tests für SSELayer (Layer 2).
 *
 * T01 — Initialzustand ist UNINITIALIZED
 * T02 — connect() wechselt in CONNECTING
 * T03 — client_id-Event wechselt in CONNECTED
 * T04 — ready-Promise löst sich beim ersten CONNECTED auf
 * T05 — clientId ist nach CONNECTED korrekt gesetzt
 * T06 — contributeToContext() gibt { sseClientId } zurück
 * T07 — Up-Event 'connected' wird bei Erstverbindung gefeuert
 * T08 — SSE-Passthrough-Event wird als 'sse_event' nach oben weitergeleitet
 * T09 — onerror aus CONNECTED → Zustand RESUMING
 * T10 — Up-Event 'resuming' wird bei Verbindungsabbruch gefeuert
 * T11 — Grace-Timer-Ablauf → Zustand DISCONNECTED
 * T12 — Up-Event 'disconnected' nach Grace-Period-Ablauf
 * T13 — client_id in RESUMING → CONNECTED mit Up-Event 'reconnected'
 * T14 — Grace-Timer wird bei Reconnect abgebrochen
 * T15 — disconnect() schließt Verbindung und setzt clientId auf null
 * T16 — connect() in CONNECTED wird ignoriert (kein Doppel-Aufbau)
 * T17 — on()/off(): Listener korrekt registriert und entfernt
 * T18 — RESUMING: ?resume_client_id wird in EventSource-URL übergeben
 * T19 — ready-Timeout löst Promise auf wenn client_id ausbleibt
 *
 * Version: v0.6.247 · Build: 247 · 2026-05-24
 * Beleg: Layer 2 States, SLA Manifest, Paket 5
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { readFileSync } from 'fs';
import { JSDOM } from 'jsdom';

// ---------------------------------------------------------------------------
// Hilfsfunktionen: MockEventSource
// ---------------------------------------------------------------------------

/**
 * MockEventSource simuliert window.EventSource für JSDOM.
 * Ermöglicht das manuelle Feuern von Events und das Simulieren
 * von Verbindungsabbrüchen (onerror).
 */
class MockEventSource {
    constructor(url) {
        this.url          = url;
        this.readyState   = 1; // OPEN
        this._handlers    = {};
        this.onerror      = null;
        MockEventSource._last = this;
    }

    addEventListener(type, fn) {
        if (!this._handlers[type]) this._handlers[type] = [];
        this._handlers[type].push(fn);
    }

    removeEventListener(type, fn) {
        if (!this._handlers[type]) return;
        this._handlers[type] = this._handlers[type].filter(f => f !== fn);
    }

    close() {
        this.readyState = 2; // CLOSED
    }

    /** Simuliert ein empfangenes SSE-Event. */
    _fire(type, data) {
        const evt = { data: JSON.stringify(data) };
        (this._handlers[type] || []).forEach(fn => fn(evt));
    }

    /** Simuliert einen Verbindungsabbruch. */
    _fireError() {
        this.readyState = 2; // CLOSED
        if (this.onerror) this.onerror(new Event('error'));
    }
}
MockEventSource._last = null;

// ---------------------------------------------------------------------------
// JSDOM-Setup
// ---------------------------------------------------------------------------

/**
 * Baut eine frische JSDOM-Umgebung mit geladenem sse_layer.js auf.
 * Ein neues DOM pro Test verhindert Zustandsverschmutzung zwischen Tests.
 * Beleg: Grundregel Vitest — ein frischer Kontext pro Test
 */
function buildDom(opts = {}) {
    const src = readFileSync('userinfo/sse_layer.js', 'utf-8');
    const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
        runScripts: 'dangerously',
        url: 'http://127.0.0.2:8080',
    });

    // window.EventSource durch Mock ersetzen
    dom.window.EventSource = MockEventSource;

    // FORENSIC_DEBUG steuern
    dom.window.FORENSIC_DEBUG = opts.debug ?? false;

    dom.window.eval(src);
    return dom;
}

/**
 * Erstellt einen SSELayer in der JSDOM-Umgebung.
 * Timeout sehr klein setzen damit T19 nicht 10s wartet.
 */
function makeLayer(dom, extraOpts = {}) {
    // SSELayer-Klasse aus dem window des DOM holen
    const SSELayer = dom.window.SSELayer;
    return new SSELayer({
        endpoint: '/_forensic/events',
        EventSourceCtor: MockEventSource,
        debug: false,
        ...extraOpts,
    });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SSELayer — Initialzustand', () => {

    it('T01 — Initialzustand ist UNINITIALIZED', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        expect(layer.state).toBe('UNINITIALIZED');
        expect(layer.clientId).toBeNull();
    });

});

describe('SSELayer — Verbindungsaufbau (connect)', () => {

    it('T02 — connect() wechselt in CONNECTING', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        expect(layer.state).toBe('CONNECTING');
    });

    it('T03 — client_id-Event wechselt in CONNECTED', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        MockEventSource._last._fire('client_id', { client_id: 'test-abc-123' });
        expect(layer.state).toBe('CONNECTED');
    });

    it('T04 — ready-Promise löst sich beim ersten CONNECTED auf', async () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();

        let resolved = false;
        layer.ready.then(() => { resolved = true; });

        MockEventSource._last._fire('client_id', { client_id: 'id-ready' });
        await layer.ready;
        expect(resolved).toBe(true);
    });

    it('T05 — clientId ist nach CONNECTED korrekt gesetzt', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        MockEventSource._last._fire('client_id', { client_id: 'my-client-id' });
        expect(layer.clientId).toBe('my-client-id');
    });

});

describe('SSELayer — contributeToContext()', () => {

    it('T06 — contributeToContext() gibt { sseClientId } zurück', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        MockEventSource._last._fire('client_id', { client_id: 'ctx-id-42' });
        const ctx = layer.contributeToContext();
        expect(ctx).toEqual({ sseClientId: 'ctx-id-42' });
    });

    it('T06b — contributeToContext() gibt null zurück wenn nicht verbunden', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        // Kein connect() — UNINITIALIZED
        const ctx = layer.contributeToContext();
        expect(ctx).toEqual({ sseClientId: null });
    });

});

describe('SSELayer — Up-Events', () => {

    it('T07 — Up-Event "connected" wird bei Erstverbindung gefeuert', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        let received = null;
        layer.on('connected', payload => { received = payload; });

        layer.connect();
        MockEventSource._last._fire('client_id', { client_id: 'first-conn' });

        expect(received).not.toBeNull();
        expect(received.clientId).toBe('first-conn');
    });

    it('T08 — SSE-Passthrough-Event wird als "sse_event" weitergeleitet', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        MockEventSource._last._fire('client_id', { client_id: 'pass-id' });

        let received = null;
        layer.on('sse_event', payload => { received = payload; });

        MockEventSource._last._fire('support_status', {
            support_active: true,
            support_user: 'h001',
            since: 123456789,
        });

        expect(received).not.toBeNull();
        expect(received.name).toBe('support_status');
        expect(received.data.support_active).toBe(true);
        expect(received.data.support_user).toBe('h001');
    });

});

describe('SSELayer — Grace-Period und RESUMING', () => {

    it('T09 — onerror aus CONNECTED → Zustand RESUMING', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        const es = MockEventSource._last;
        es._fire('client_id', { client_id: 'grace-test' });
        expect(layer.state).toBe('CONNECTED');

        es._fireError();
        expect(layer.state).toBe('RESUMING');
    });

    it('T10 — Up-Event "resuming" wird bei Verbindungsabbruch gefeuert', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        const es = MockEventSource._last;
        es._fire('client_id', { client_id: 'resuming-up' });

        let resumingFired = false;
        layer.on('resuming', () => { resumingFired = true; });

        es._fireError();
        expect(resumingFired).toBe(true);
    });

    it('T11 — Grace-Timer-Ablauf → Zustand DISCONNECTED', async () => {
        vi.useFakeTimers();
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        const es = MockEventSource._last;
        es._fire('client_id', { client_id: 'disc-test' });
        es._fireError();

        expect(layer.state).toBe('RESUMING');

        // Grace-Period ablaufen lassen (6000ms)
        await vi.advanceTimersByTimeAsync(7000);
        expect(layer.state).toBe('DISCONNECTED');
        expect(layer.clientId).toBeNull();

        vi.useRealTimers();
    });

    it('T12 — Up-Event "disconnected" nach Grace-Period-Ablauf', async () => {
        vi.useFakeTimers();
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        const es = MockEventSource._last;
        es._fire('client_id', { client_id: 'disc-event' });
        es._fireError();

        let disconnectedFired = false;
        layer.on('disconnected', () => { disconnectedFired = true; });

        await vi.advanceTimersByTimeAsync(7000);
        expect(disconnectedFired).toBe(true);

        vi.useRealTimers();
    });

    it('T13 — client_id in RESUMING → CONNECTED mit Up-Event "reconnected"', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        const es = MockEventSource._last;
        es._fire('client_id', { client_id: 'old-id' });
        es._fireError();

        expect(layer.state).toBe('RESUMING');
        expect(layer.clientId).toBe('old-id');

        let reconnected = null;
        layer.on('reconnected', payload => { reconnected = payload; });

        // Browser reconnectet, neues client_id-Event
        es._fire('client_id', { client_id: 'new-id' });

        expect(layer.state).toBe('CONNECTED');
        expect(layer.clientId).toBe('new-id');
        expect(reconnected).not.toBeNull();
        expect(reconnected.clientId).toBe('new-id');
        expect(reconnected.oldClientId).toBe('old-id');
    });

    it('T14 — Grace-Timer wird bei Reconnect abgebrochen', async () => {
        vi.useFakeTimers();
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        const es = MockEventSource._last;
        es._fire('client_id', { client_id: 'timer-cancel' });
        es._fireError();

        // Reconnect innerhalb Grace-Period
        es._fire('client_id', { client_id: 'new-after-grace' });
        expect(layer.state).toBe('CONNECTED');

        // Grace-Period ablaufen lassen — darf NICHT in DISCONNECTED wechseln
        await vi.advanceTimersByTimeAsync(7000);
        expect(layer.state).toBe('CONNECTED');

        vi.useRealTimers();
    });

});

describe('SSELayer — disconnect()', () => {

    it('T15 — disconnect() schließt Verbindung und setzt clientId auf null', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        MockEventSource._last._fire('client_id', { client_id: 'disc-me' });
        expect(layer.state).toBe('CONNECTED');

        layer.disconnect();
        expect(layer.state).toBe('DISCONNECTED');
        expect(layer.clientId).toBeNull();
    });

    it('T16 — connect() in CONNECTED wird ignoriert (kein Doppel-Aufbau)', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        const first = MockEventSource._last;
        first._fire('client_id', { client_id: 'first' });

        // Zweites connect() soll ignoriert werden
        layer.connect();
        const second = MockEventSource._last;

        // MockEventSource._last darf sich nicht geändert haben
        expect(second).toBe(first);
        expect(layer.clientId).toBe('first');
    });

});

describe('SSELayer — on()/off()', () => {

    it('T17 — on()/off(): Listener korrekt registriert und entfernt', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();

        let count = 0;
        const fn = () => { count++; };
        layer.on('connected', fn);
        MockEventSource._last._fire('client_id', { client_id: 'on-off' });
        expect(count).toBe(1);

        // Zweite Verbindung simulieren: disconnect + reconnect
        layer.disconnect();
        layer.on('connected', fn);
        layer.connect();
        layer.off('connected', fn);   // Listener entfernen
        MockEventSource._last._fire('client_id', { client_id: 'on-off-2' });
        // count bleibt 1, weil Listener entfernt wurde
        expect(count).toBe(1);
    });

});

describe('SSELayer — RESUMING URL', () => {

    it('T18 — RESUMING: ?resume_client_id wird in EventSource-URL übergeben', () => {
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();
        const es = MockEventSource._last;
        es._fire('client_id', { client_id: 'old-resume-id' });
        es._fireError();

        // Zweite EventSource-Instanz entsteht beim automatischen Reconnect.
        // Wir simulieren das indem wir _openEventSource direkt aufrufen.
        // (Im echten Browser macht das der EventSource-Reconnect-Mechanismus.)
        layer._openEventSource('old-resume-id');
        const resumeEs = MockEventSource._last;

        expect(resumeEs.url).toContain('resume_client_id=old-resume-id');
    });

});

describe('SSELayer — ready-Timeout', () => {

    it('T19 — ready-Timeout löst Promise auf wenn client_id ausbleibt', async () => {
        // Wir überschreiben den Timeout-Wert durch direktes Patchen
        // des setTimeout in der JSDOM-Umgebung.
        vi.useFakeTimers();
        const dom   = buildDom();
        const layer = makeLayer(dom);
        layer.connect();

        let readyResolved = false;
        layer.ready.then(() => { readyResolved = true; });

        // Kein client_id-Event — 10s Timeout abwarten
        await vi.advanceTimersByTimeAsync(11000);

        // ready muss aufgelöst worden sein
        expect(readyResolved).toBe(true);
        // Zustand: weiterhin CONNECTING (kein CONNECTED ohne client_id)
        expect(layer.state).toBe('CONNECTING');

        vi.useRealTimers();
    });

});
