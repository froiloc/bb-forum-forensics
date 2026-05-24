/**
 * userinfo/report_layer.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Layer 3 der geschichteten Editor-Architektur.
 *   Kapselt alle Operationen die einen Bericht als Ganzes betreffen:
 *   Öffnen, Neu-Anlegen, Zustand halten.
 *   Alle höheren Layer (4, 5, 6) beziehen ihren Berichts-Kontext
 *   ausschließlich über diese Klasse.
 *
 * Voraussetzung:
 *   SSELayer (Layer 2) muss CONNECTED sein bevor ReportLayer operiert.
 *   ready-Promise wartet auf SSELayer.ready.
 *   Beleg: Layer 3 States, Paket 6
 *
 * Zustände (clientseitig, gemäß Layer 3 States):
 *   UNINITIALIZED  — Initialzustand.
 *   IDLE           — Kein Bericht geöffnet.
 *   OPENING        — Bericht wird vom Server geladen.
 *   OPENED         — Bericht geladen und im Client verfügbar.
 *   NEW            — Neuer Bericht wird angelegt (atomar mit Lock).
 *
 * Sub-Interfaces:
 *   State  — Lesezugriff auf Zustand und Berichtsdaten.
 *   Up     — Events die ReportLayer nach oben (an Layer 4/5/6) sendet.
 *   Down   — Kommandos die höhere Layer senden können.
 *
 * State:
 *   state        {string}      — Aktueller Zustand
 *   reportId     {number|null} — ID des aktuell geöffneten Berichts
 *   reportTitle  {string|null} — Titel des aktuell geöffneten Berichts
 *   reportStatus {string|null} — Status (draft/submitted/approved/final)
 *   blocks       {Array}       — Blöcke des aktuell geöffneten Berichts
 *
 * Up-Events:
 *   opened   { reportId, title, reportStatus, reportType, blocks }
 *            — Bericht erfolgreich geöffnet (OPENING → OPENED)
 *   created  { reportId, title, reportType, lockId }
 *            — Neuer Bericht angelegt (NEW → OPENED)
 *   idle     {}
 *            — Kein Bericht mehr geöffnet
 *   error    { code, message }
 *            — Fehler beim Öffnen / Anlegen
 *
 * Down-Kommandos:
 *   open(reportId)              — Bestehenden Bericht öffnen
 *   create(reportType, title)   — Neuen Bericht anlegen
 *   close()                     — Bericht schließen (→ IDLE)
 *
 * contributeToContext():
 *   Gibt { reportId } zurück.
 *   Beleg: contributeToContext()-Muster, Paket 6
 *
 * ready-Promise:
 *   Wird aufgelöst sobald SSELayer.ready aufgelöst ist und ReportLayer
 *   in IDLE ist (einsatzbereit, kein Bericht geöffnet).
 *   Beleg: Paket 6, Layer-3-States
 *
 * Version: v0.6.249 · Build: 249 · 2026-05-24
 * Beleg: Layer 3 States, SLA Manifest, Paket 6
 */

(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // Konstanten
    // -----------------------------------------------------------------------

    const REPORT_API = '/_forensic/report';

    const STATES = Object.freeze({
        UNINITIALIZED: 'UNINITIALIZED',
        IDLE:          'IDLE',
        OPENING:       'OPENING',
        OPENED:        'OPENED',
        NEW:           'NEW',
    });

    // -----------------------------------------------------------------------
    // Klasse ReportLayer
    // -----------------------------------------------------------------------

    /**
     * ReportLayer — Layer 3 der Editor-Architektur.
     *
     * Instanziierung:
     *   const layer = new ReportLayer({ sseLayer });
     *   await layer.ready;
     *   await layer.open(5);
     *   const ctx = layer.contributeToContext(); // { reportId: 5 }
     *
     * Beleg: Layer 3 States, SLA Manifest, Paket 6
     */
    class ReportLayer {

        /**
         * @param {object}   opts
         * @param {SSELayer} opts.sseLayer        — Layer-2-Instanz (required)
         * @param {boolean}  [opts.debug=false]   — Debug-Logging ein/aus
         * @param {Function} [opts.fetchFn]       — fetch-Ersatz für Tests
         */
        constructor(opts = {}) {
            if (!opts.sseLayer) {
                throw new Error('[ReportLayer] sseLayer ist erforderlich (Dependency Injection)');
            }
            this._sse       = opts.sseLayer;
            this._debug     = opts.debug    ?? (window.FORENSIC_DEBUG !== false);
            this._fetchFn   = opts.fetchFn  ?? window.fetch.bind(window);

            // Zustand
            this._state        = STATES.UNINITIALIZED;
            this._reportId     = null;
            this._reportTitle  = null;
            this._reportStatus = null;
            this._reportType   = null;
            this._blocks       = [];

            // Up-Event-Listener
            this._upListeners = {};

            // SSE-Events beobachten: report_updated löst Neu-Laden der Blöcke aus.
            // Beleg: Layer 3 States OPENED (passive Aktualisierung via SSE)
            this._sse.on('sse_event', (payload) => this._onSseEvent(payload));

            // Wenn SSELayer die Verbindung verliert, kann der ReportLayer
            // keinen Zustand mehr halten der vom Server abhängt.
            // Beleg: Layer 4 States: „Layer 2 DISCONNECTED lässt Layer 4 kollabieren"
            this._sse.on('disconnected', () => this._onSseDisconnected());

            // ready-Promise: wartet auf SSELayer.ready, dann → IDLE
            // Beleg: Paket 6, Layer-ready-Kette
            this.ready = this._sse.ready.then(() => {
                this._transition(STATES.IDLE);
                this._dbg('ready — SSELayer ist bereit, ReportLayer in IDLE');
            });
        }

        // -------------------------------------------------------------------
        // State (öffentlicher Lesezugriff)
        // -------------------------------------------------------------------

        get state()        { return this._state; }
        get reportId()     { return this._reportId; }
        get reportTitle()  { return this._reportTitle; }
        get reportStatus() { return this._reportStatus; }
        get reportType()   { return this._reportType; }

        /** Kopie des Block-Arrays (defensiv gegen externe Mutation). */
        get blocks()       { return [...this._blocks]; }

        // -------------------------------------------------------------------
        // contributeToContext()
        // -------------------------------------------------------------------

        /**
         * Trägt den Berichts-Kontext zum HTTP-Request-Kontext bei.
         * @returns {{ reportId: number|null }}
         */
        contributeToContext() {
            return { reportId: this._reportId };
        }

        // -------------------------------------------------------------------
        // Down — Kommandos von höheren Layern
        // -------------------------------------------------------------------

        /**
         * Down.open(reportId): Bestehenden Bericht öffnen.
         *
         * IDLE / OPENED → OPENING → OPENED
         * Beleg: Layer 3 States OPENING
         */
        async open(reportId) {
            if (this._state === STATES.OPENING || this._state === STATES.NEW) {
                this._dbg('open() ignoriert — laufende Transaktion:', this._state);
                return;
            }
            this._dbg('open() reportId=', reportId);
            this._transition(STATES.OPENING);

            const sseClientId = this._sse.clientId;
            if (!sseClientId) {
                this._dbg('open(): kein SSE-Client — warte auf SSELayer.ready');
                await this._sse.ready;
            }

            try {
                const resp = await this._fetchFn(REPORT_API, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action:     'open_report',
                        report_id:  reportId,
                        sse_client: this._sse.clientId,
                    }),
                });
                const data = await resp.json();

                if (!resp.ok || data.status !== 'ok') {
                    const code = data.code || 'OPEN_FAILED';
                    const msg  = data.error || 'Bericht konnte nicht geöffnet werden';
                    this._dbg('open() fehlgeschlagen:', code, msg);
                    this._transition(STATES.IDLE);
                    this._emitUp('error', { code, message: msg });
                    return;
                }

                this._reportId     = data.report_id;
                this._reportTitle  = data.title;
                this._reportStatus = data.report_status;
                this._reportType   = data.report_type;
                this._blocks       = data.blocks || [];

                this._transition(STATES.OPENED);
                this._emitUp('opened', {
                    reportId:     this._reportId,
                    title:        this._reportTitle,
                    reportStatus: this._reportStatus,
                    reportType:   this._reportType,
                    blocks:       this.blocks,
                });
                this._dbg('OPENED: report_id=', this._reportId);

            } catch (err) {
                this._dbg('open() Netzwerkfehler:', err);
                this._transition(STATES.IDLE);
                this._emitUp('error', { code: 'NETWORK_ERROR', message: String(err) });
            }
        }

        /**
         * Down.create(reportType, title): Neuen Bericht anlegen.
         *
         * IDLE → NEW → OPENED
         * Atomar: Bericht + Lock werden in einer Transaktion angelegt (SLA Punkt 7).
         * Beleg: Layer 3 States NEW, SLA Punkt 7
         */
        async create(reportType, title) {
            if (this._state === STATES.OPENING || this._state === STATES.NEW) {
                this._dbg('create() ignoriert — laufende Transaktion:', this._state);
                return;
            }
            if (!title || !title.trim()) {
                this._emitUp('error', { code: 'MISSING_TITLE', message: 'Titel erforderlich' });
                return;
            }
            this._dbg('create() type=', reportType, 'title=', title);
            this._transition(STATES.NEW);

            const sseClientId = this._sse.clientId;
            if (!sseClientId) {
                await this._sse.ready;
            }

            try {
                const resp = await this._fetchFn(REPORT_API, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action:      'new_report',
                        report_type: reportType || 'interim',
                        title:       title.trim(),
                        sse_client:  this._sse.clientId,
                    }),
                });
                const data = await resp.json();

                if (!resp.ok || data.status !== 'ok') {
                    const code = data.code || 'CREATE_FAILED';
                    const msg  = data.error || 'Bericht konnte nicht angelegt werden';
                    this._dbg('create() fehlgeschlagen:', code, msg);
                    this._transition(STATES.IDLE);
                    this._emitUp('error', { code, message: msg });
                    return;
                }

                this._reportId     = data.report_id;
                this._reportTitle  = data.title;
                this._reportStatus = 'draft';
                this._reportType   = data.report_type;
                this._blocks       = [];

                this._transition(STATES.OPENED);
                this._emitUp('created', {
                    reportId:   this._reportId,
                    title:      this._reportTitle,
                    reportType: this._reportType,
                    lockId:     data.lock_id,   // Lock-ID für LockLayer
                });
                this._dbg('NEW → OPENED: report_id=', this._reportId, 'lock_id=', data.lock_id);

            } catch (err) {
                this._dbg('create() Netzwerkfehler:', err);
                this._transition(STATES.IDLE);
                this._emitUp('error', { code: 'NETWORK_ERROR', message: String(err) });
            }
        }

        /**
         * Down.close(): Bericht schließen.
         * OPENED → IDLE
         * Beleg: Layer 3 States
         */
        close() {
            this._dbg('close() aufgerufen');
            this._reportId     = null;
            this._reportTitle  = null;
            this._reportStatus = null;
            this._reportType   = null;
            this._blocks       = [];
            this._transition(STATES.IDLE);
            this._emitUp('idle', {});
        }

        // -------------------------------------------------------------------
        // Up — Event-Bus nach oben
        // -------------------------------------------------------------------

        on(eventName, fn) {
            if (!this._upListeners[eventName]) this._upListeners[eventName] = [];
            this._upListeners[eventName].push(fn);
        }

        off(eventName, fn) {
            if (!this._upListeners[eventName]) return;
            this._upListeners[eventName] =
                this._upListeners[eventName].filter(f => f !== fn);
        }

        // -------------------------------------------------------------------
        // Interne Methoden
        // -------------------------------------------------------------------

        /**
         * SSE-Event-Handler: reagiert auf report_updated.
         * Lädt bei geöffnetem Bericht die Blöcke neu.
         * Beleg: Layer 3 States OPENED (passive Aktualisierung via SSE)
         */
        _onSseEvent({ name, data }) {
            if (name === 'report_updated' && this._state === STATES.OPENED) {
                this._dbg('report_updated: Blöcke neu laden für report_id=', this._reportId);
                // Nicht-blockierend: Fehler werden geloggt aber nicht weitergereicht.
                this._reloadBlocks().catch(err =>
                    this._dbg('_reloadBlocks Fehler:', err)
                );
            }
        }

        /**
         * SSE-Verbindung dauerhaft verloren (Grace-Period abgelaufen).
         * Layer 3 fällt auf IDLE zurück — kein Bericht mehr haltbar.
         * Beleg: Layer 3 States, Layer 4 States Präambel
         */
        _onSseDisconnected() {
            if (this._state !== STATES.IDLE && this._state !== STATES.UNINITIALIZED) {
                this._dbg('SSE DISCONNECTED → ReportLayer auf IDLE');
                this.close();
            }
        }

        /**
         * Blöcke des aktuell geöffneten Berichts neu laden (nach report_updated).
         * Macht keinen neuen OPENING-Übergang sondern aktualisiert still.
         */
        async _reloadBlocks() {
            if (!this._reportId) return;
            const resp = await this._fetchFn(
                `${REPORT_API}?format=json&report_id=${this._reportId}`
            );
            const data = await resp.json();
            // Format: { reports: [...], paragraphs: [...] } (bestehender GET-Endpunkt)
            // Wir suchen den richtigen Bericht und seine Blöcke.
            const found = (data.reports || []).find(r => r.id === this._reportId);
            if (found) {
                this._blocks = found.blocks || data.paragraphs || [];
                this._emitUp('opened', {
                    reportId:     this._reportId,
                    title:        this._reportTitle,
                    reportStatus: this._reportStatus,
                    reportType:   this._reportType,
                    blocks:       this.blocks,
                });
            }
        }

        _transition(newState) {
            if (this._state !== newState) {
                this._dbg('Zustandsübergang:', this._state, '→', newState);
                this._state = newState;
            }
        }

        _emitUp(eventName, payload) {
            const listeners = this._upListeners[eventName];
            if (!listeners || listeners.length === 0) return;
            for (const fn of listeners) {
                try { fn(payload); } catch (err) {
                    console.error('[ReportLayer] Up-Event-Listener Fehler:', eventName, err);
                }
            }
        }

        _dbg(...args) {
            if (this._debug) console.debug('[ReportLayer]', ...args);
        }
    }

    // -----------------------------------------------------------------------
    // Export auf window
    // -----------------------------------------------------------------------

    window.ReportLayer       = ReportLayer;
    window.ReportLayerStates = STATES;

})();
