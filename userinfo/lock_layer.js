/**
 * userinfo/lock_layer.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Layer 4 der geschichteten Editor-Architektur.
 *   Kapselt die gesamte Lock-Logik für einen geöffneten Bericht.
 *   Nur dieser Layer darf Lock-Operationen an den Server senden.
 *   Nur dieser Layer verwaltet lockId in sessionStorage.
 *
 * Voraussetzungen:
 *   SSELayer (Layer 2) muss CONNECTED sein.
 *   ReportLayer (Layer 3) muss OPENED sein (reportId bekannt).
 *   Beleg: Layer 4 States Präambel
 *
 * Zustände (clientseitig, gemäß Layer 4 States):
 *   UNINITIALIZED        — Initialzustand.
 *   IDLE                 — Kein Lock; kein Anspruch.
 *   ACQUIRING            — Lock wird erworben (nicht-aggressiv).
 *   MINE                 — Lock gehalten; Schreibzugriff erlaubt.
 *   RELEASING            — Lock wird freigegeben.
 *   CONTESTED            — Lock belegt von anderem; wartet auf Entscheidung.
 *   TAKEOVER_PENDING     — Übernahmeanfrage an Lock-Inhaber gesendet.
 *   TAKEOVER_REQUEST_IN  — Übernahmeanfrage eingegangen (wir sind Inhaber).
 *   TAKEOVER_DENIED      — Anfrage abgelehnt; Cooldown läuft.
 *   QUEUED               — In Warteschlange; wartet auf lock_acquired-Event.
 *
 * Sub-Interfaces:
 *   State  — Lesezugriff auf Zustand und lockId.
 *   Up     — Events nach oben (an DocumentLayer / UILayer).
 *   Down   — Kommandos von höheren Layern.
 *
 * State:
 *   state          {string}      — Aktueller Zustand
 *   lockId         {string|null} — Aktuell gehaltene lock_id oder null
 *   lockedBy       {string|null} — Wer den Lock hält (null = ich)
 *   cooldownUntil  {number|null} — Unix-Timestamp Ende des Cooldowns
 *   queueLength    {number}      — Aktuelle Warteschlangenlänge
 *
 * Up-Events:
 *   acquired          { lockId }
 *                     — Lock erworben (ACQUIRING/QUEUED → MINE)
 *   released          {}
 *                     — Lock freigegeben (RELEASING → IDLE)
 *   contested         { lockedBy, cooldownUntil, queueLength }
 *                     — Lock belegt (ACQUIRING → IDLE/CONTESTED)
 *   takeover_request  { requestId, requestedBy }
 *                     — Übernahmeanfrage eingegangen (→ TAKEOVER_REQUEST_IN)
 *   takeover_denied   { cooldownUntil }
 *                     — Anfrage abgelehnt (→ TAKEOVER_DENIED)
 *   takeover_granted  {}
 *                     — Anfrage gewährt; Lock läuft ab (→ RELEASING)
 *   queued            { position }
 *                     — In Warteschlange eingetragen (→ QUEUED)
 *   error             { code, message }
 *
 * Down-Kommandos:
 *   acquire()              — Lock erwerben (aus IDLE)
 *   release()              — Lock freigeben (aus MINE / TAKEOVER_REQUEST_IN)
 *   release(sync=true)     — Synchron via sendBeacon (beforeunload)
 *   joinQueue()            — Warteschlange beitreten (aus IDLE / CONTESTED / TAKEOVER_DENIED)
 *   leaveQueue()           — Warteschlange verlassen (aus QUEUED)
 *   requestTakeover()      — Übernahme anfragen (aus IDLE / CONTESTED / TAKEOVER_DENIED)
 *   respondTakeover(grant) — Auf Anfrage antworten (aus TAKEOVER_REQUEST_IN)
 *
 * contributeToContext():
 *   Gibt { lockId } zurück.
 *   Beleg: contributeToContext()-Muster, Paket 7
 *
 * sessionStorage-Key: 'forensic_lock_v2'
 *   Neuer Key, frei von Altlast forensic_lock_id.
 *   Beleg: Paket-7-Entscheidung 2026-05-24
 *
 * Kollaps-Regel:
 *   Wenn SSELayer DISCONNECTED oder ReportLayer IDLE wird, fällt LockLayer
 *   auf IDLE zurück. Falls Zustand MINE war, geschieht das über RELEASING.
 *   Beleg: Layer 4 States Präambel
 *
 * Version: v0.6.250 · Build: 250 · 2026-05-24
 * Beleg: Layer 4 States, SLA Manifest, Paket 7
 */

(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // Konstanten
    // -----------------------------------------------------------------------

    const REPORT_API = '/_forensic/report';

    /** sessionStorage-Key für lockId-Persistenz. Neuer Key ab Paket 7. */
    const SESSION_KEY = 'forensic_lock_v2';

    const STATES = Object.freeze({
        UNINITIALIZED:       'UNINITIALIZED',
        IDLE:                'IDLE',
        ACQUIRING:           'ACQUIRING',
        MINE:                'MINE',
        RELEASING:           'RELEASING',
        CONTESTED:           'CONTESTED',
        TAKEOVER_PENDING:    'TAKEOVER_PENDING',
        TAKEOVER_REQUEST_IN: 'TAKEOVER_REQUEST_IN',
        TAKEOVER_DENIED:     'TAKEOVER_DENIED',
        QUEUED:              'QUEUED',
    });

    // -----------------------------------------------------------------------
    // Klasse LockLayer
    // -----------------------------------------------------------------------

    /**
     * LockLayer — Layer 4 der Editor-Architektur.
     *
     * Instanziierung:
     *   const layer = new LockLayer({ sseLayer, reportLayer });
     *   await layer.ready;
     *   await layer.acquire();
     *
     * Beleg: Layer 4 States, SLA Manifest, Paket 7
     */
    class LockLayer {

        /**
         * @param {object}      opts
         * @param {SSELayer}    opts.sseLayer     — Layer-2-Instanz (required)
         * @param {ReportLayer} opts.reportLayer  — Layer-3-Instanz (required)
         * @param {boolean}     [opts.debug]      — Debug-Logging
         * @param {Function}    [opts.fetchFn]    — fetch-Ersatz für Tests
         * @param {object}      [opts.sessionStorage] — sessionStorage-Ersatz
         *                                            für Tests
         */
        constructor(opts = {}) {
            if (!opts.sseLayer)    throw new Error('[LockLayer] sseLayer erforderlich');
            if (!opts.reportLayer) throw new Error('[LockLayer] reportLayer erforderlich');

            this._sse     = opts.sseLayer;
            this._report  = opts.reportLayer;
            this._debug   = opts.debug   ?? (window.FORENSIC_DEBUG !== false);
            this._fetchFn = opts.fetchFn ?? window.fetch.bind(window);
            this._storage = opts.sessionStorage ?? (
                typeof sessionStorage !== 'undefined' ? sessionStorage : null
            );

            // Zustand
            this._state         = STATES.UNINITIALIZED;
            this._lockId        = null;
            this._lockedBy      = null;
            this._cooldownUntil = null;
            this._queueLength   = 0;

            // Laufende Pending-Takeover-Anfrage-ID (für respondTakeover)
            this._pendingRequestId = null;

            // Re-Entry-Guard für acquire() — verhindert parallele Requests
            this._acquiring = false;

            // Up-Event-Listener
            this._upListeners = {};

            // SSE-Events beobachten
            this._sse.on('sse_event',    (p) => this._onSseEvent(p));
            this._sse.on('disconnected', ()  => this._onLayerCollapse('SSE DISCONNECTED'));
            this._sse.on('reconnected',  (p) => this._onSseReconnected(p));

            // ReportLayer-Events beobachten
            this._report.on('idle',    () => this._onLayerCollapse('ReportLayer IDLE'));
            this._report.on('opened',  () => this._onReportOpened());
            this._report.on('created', (p) => this._onReportCreated(p));

            // ready-Promise: wartet auf ReportLayer.ready (der auf SSELayer.ready wartet)
            // Beleg: Layer-ready-Kette, Paket 7
            this.ready = this._report.ready.then(() => {
                // lockId aus sessionStorage wiederherstellen (Browser-Reload innerhalb
                // Grace-Period — Lock könnte noch gültig sein)
                const stored = this._storage?.getItem(SESSION_KEY);
                if (stored) {
                    this._lockId = stored;
                    this._dbg('ready: lockId aus sessionStorage wiederhergestellt:', stored);
                }
                this._transition(STATES.IDLE);
                this._dbg('ready — ReportLayer ist bereit, LockLayer in IDLE');
            });
        }

        // -------------------------------------------------------------------
        // State (öffentlicher Lesezugriff)
        // -------------------------------------------------------------------

        get state()         { return this._state; }
        get lockId()        { return this._lockId; }
        get lockedBy()      { return this._lockedBy; }
        get cooldownUntil() { return this._cooldownUntil; }
        get queueLength()   { return this._queueLength; }

        // -------------------------------------------------------------------
        // contributeToContext()
        // -------------------------------------------------------------------

        /**
         * Trägt den Lock-Kontext zum HTTP-Request-Kontext bei.
         * @returns {{ lockId: string|null }}
         */
        contributeToContext() {
            return { lockId: this._lockId };
        }

        // -------------------------------------------------------------------
        // Down — Kommandos von höheren Layern
        // -------------------------------------------------------------------

        /**
         * Down.acquire(): Lock erwerben.
         * Nicht-aggressiv: nur wenn Lock frei ist (ACQUIRING-Semantik der Spec).
         * Beleg: Layer 4 States ACQUIRING
         */
        async acquire() {
            if (!this._canAcquire()) return;
            if (this._acquiring) {
                this._dbg('acquire() ignoriert — läuft bereits');
                return;
            }

            const reportId    = this._report.reportId;
            const sseClientId = this._sse.clientId;

            if (!reportId) {
                this._emitUp('error', { code: 'NO_REPORT', message: 'Kein Bericht geöffnet' });
                return;
            }
            if (!sseClientId) {
                this._emitUp('error', { code: 'NO_SSE', message: 'SSE-Verbindung nicht bereit' });
                return;
            }

            this._acquiring = true;
            this._transition(STATES.ACQUIRING);

            try {
                const resp = await this._fetchFn(REPORT_API, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action:     'acquire_lock',
                        report_id:  reportId,
                        sse_client: sseClientId,
                    }),
                });
                const data = await resp.json();

                if (resp.ok && data.lock_id) {
                    // Erfolg: MINE
                    this._setLockId(data.lock_id);
                    this._lockedBy      = null;
                    this._cooldownUntil = null;
                    this._transition(STATES.MINE);
                    this._emitUp('acquired', { lockId: this._lockId });
                    this._dbg('MINE: lock_id=', this._lockId);

                } else if (resp.status === 423) {
                    // Lock belegt — IDLE + Info für UI
                    this._lockedBy      = data.locked_by      ?? null;
                    this._cooldownUntil = data.cooldown_until  ?? null;
                    this._queueLength   = data.queue_length    ?? 0;
                    this._transition(STATES.IDLE);
                    this._emitUp('contested', {
                        lockedBy:      this._lockedBy,
                        cooldownUntil: this._cooldownUntil,
                        queueLength:   this._queueLength,
                    });
                    this._dbg('CONTESTED: locked_by=', this._lockedBy);

                } else {
                    this._transition(STATES.IDLE);
                    this._emitUp('error', {
                        code:    data.code    ?? 'ACQUIRE_FAILED',
                        message: data.error   ?? 'Lock konnte nicht erworben werden',
                    });
                }
            } catch (err) {
                this._transition(STATES.IDLE);
                this._emitUp('error', { code: 'NETWORK_ERROR', message: String(err) });
            } finally {
                this._acquiring = false;
            }
        }

        /**
         * Down.release(): Lock freigeben.
         * @param {boolean} [sync=false] — true = sendBeacon (beforeunload)
         * Beleg: Layer 4 States RELEASING
         */
        release(sync = false) {
            if (this._state !== STATES.MINE &&
                this._state !== STATES.TAKEOVER_REQUEST_IN) {
                this._dbg('release() ignoriert — Zustand:', this._state);
                return;
            }
            const lockId   = this._lockId;
            const reportId = this._report.reportId;
            if (!lockId || !reportId) return;

            this._transition(STATES.RELEASING);

            const body = JSON.stringify({
                action:    'release_lock',
                lock_id:   lockId,
                report_id: reportId,
            });

            if (sync) {
                // beforeunload — sendBeacon ist einzige zuverlässige Methode
                if (typeof navigator !== 'undefined' && navigator.sendBeacon) {
                    navigator.sendBeacon(REPORT_API,
                        new Blob([body], { type: 'application/json' }));
                }
                this._clearLockId();
                this._transition(STATES.IDLE);
                this._emitUp('released', {});
            } else {
                this._fetchFn(REPORT_API, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body,
                }).then(() => {
                    this._clearLockId();
                    this._transition(STATES.IDLE);
                    this._emitUp('released', {});
                    this._dbg('RELEASING → IDLE');
                }).catch(err => {
                    // Netzwerkfehler: lokal aufräumen, Lock auf Server läuft per
                    // Grace-Period ab. Besser konsistenter lokaler Zustand als
                    // kein Aufräumen.
                    this._dbg('release() Netzwerkfehler (lokal aufgeräumt):', err);
                    this._clearLockId();
                    this._transition(STATES.IDLE);
                    this._emitUp('released', {});
                });
            }
        }

        /**
         * Down.joinQueue(): Warteschlange beitreten.
         * Beleg: Layer 4 States QUEUED
         */
        async joinQueue() {
            const reportId    = this._report.reportId;
            const sseClientId = this._sse.clientId;
            if (!reportId || !sseClientId) {
                this._emitUp('error', { code: 'MISSING_CONTEXT', message: 'report_id oder sse_client fehlt' });
                return;
            }
            try {
                const resp = await this._fetchFn(REPORT_API, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action:     'queue_join',
                        report_id:  reportId,
                        sse_client: sseClientId,
                    }),
                });
                const data = await resp.json();
                if (resp.ok && data.queued) {
                    this._transition(STATES.QUEUED);
                    this._emitUp('queued', { position: data.position ?? 1 });
                    this._dbg('QUEUED: position=', data.position);
                } else {
                    this._emitUp('error', {
                        code:    data.code  ?? 'QUEUE_FAILED',
                        message: data.error ?? 'Warteschlange beitreten fehlgeschlagen',
                    });
                }
            } catch (err) {
                this._emitUp('error', { code: 'NETWORK_ERROR', message: String(err) });
            }
        }

        /**
         * Down.leaveQueue(): Warteschlange verlassen.
         * Beleg: Layer 4 States QUEUED → IDLE
         */
        async leaveQueue() {
            if (this._state !== STATES.QUEUED) return;
            const reportId = this._report.reportId;
            if (!reportId) return;

            this._transition(STATES.IDLE);
            try {
                await this._fetchFn(REPORT_API, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'queue_leave', report_id: reportId }),
                });
            } catch (err) {
                this._dbg('leaveQueue() Netzwerkfehler (lokal bereits IDLE):', err);
            }
            this._emitUp('released', {});
        }

        /**
         * Down.requestTakeover(): Übernahme des Locks anfragen.
         * Beleg: Layer 4 States TAKEOVER_PENDING
         */
        async requestTakeover() {
            const reportId = this._report.reportId;
            if (!reportId) return;

            try {
                const resp = await this._fetchFn(REPORT_API, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action:    'request_takeover',
                        report_id: reportId,
                    }),
                });
                const data = await resp.json();

                if (resp.ok && data.request_id) {
                    // countdown kommt vom Server; Client zeigt ihn nur an.
                    // Beleg: Paket-7-Entscheidung 2026-05-24 (Timer liegt auf Server)
                    this._transition(STATES.TAKEOVER_PENDING);
                    this._emitUp('takeover_pending', {
                        requestId: data.request_id,
                        countdown: data.countdown ?? 60,
                    });
                    this._dbg('TAKEOVER_PENDING: request_id=', data.request_id);

                } else if (resp.status === 429) {
                    // Cooldown aktiv — sofort TAKEOVER_DENIED
                    this._cooldownUntil = data.cooldown_until ?? null;
                    this._transition(STATES.TAKEOVER_DENIED);
                    this._emitUp('takeover_denied', { cooldownUntil: this._cooldownUntil });

                } else {
                    this._emitUp('error', {
                        code:    data.code  ?? 'TAKEOVER_FAILED',
                        message: data.error ?? 'Übernahmeanfrage fehlgeschlagen',
                    });
                }
            } catch (err) {
                this._emitUp('error', { code: 'NETWORK_ERROR', message: String(err) });
            }
        }

        /**
         * Down.respondTakeover(grant): Auf eingehende Übernahmeanfrage antworten.
         * @param {boolean} grant — true = übergeben, false = ablehnen
         * Beleg: Layer 4 States TAKEOVER_REQUEST_IN
         */
        async respondTakeover(grant) {
            if (this._state !== STATES.TAKEOVER_REQUEST_IN) {
                this._dbg('respondTakeover() ignoriert — Zustand:', this._state);
                return;
            }
            const requestId = this._pendingRequestId;
            const reportId  = this._report.reportId;
            const lockId    = this._lockId;
            if (!requestId || !reportId || !lockId) return;

            try {
                const resp = await this._fetchFn(REPORT_API, {
                    method:  'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action:     'respond_takeover',
                        report_id:  reportId,
                        request_id: requestId,
                        response:   grant ? 'grant' : 'deny',
                        lock_id:    lockId,
                    }),
                });
                const data = await resp.json();

                if (grant) {
                    // Lock wird übergeben: RELEASING → IDLE
                    this._pendingRequestId = null;
                    this._emitUp('takeover_granted', {});
                    this.release();
                } else {
                    // Anfrage abgelehnt: zurück nach MINE + Cooldown
                    this._cooldownUntil = data.cooldown_until ?? null;
                    this._pendingRequestId = null;
                    this._transition(STATES.MINE);
                    this._dbg('respondTakeover deny → MINE, cooldown=', this._cooldownUntil);
                }
            } catch (err) {
                this._dbg('respondTakeover() Netzwerkfehler:', err);
                // Bei Fehler: sicherheitshalber zurück nach MINE
                this._transition(STATES.MINE);
                this._emitUp('error', { code: 'NETWORK_ERROR', message: String(err) });
            }
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
        // Interne Methoden — SSE-Event-Handling
        // -------------------------------------------------------------------

        /**
         * Verteilt SSE-Events an die relevanten Handler.
         * Beleg: Layer 4 States — SSE-Events als Zustandsauslöser
         */
        _onSseEvent({ name, data }) {
            switch (name) {

                case 'lock_acquired':
                    // Direkt an uns: Lock aus Queue-Kaskade oder Takeover erhalten.
                    // Enthält die neue lock_id (geheim, nur für uns).
                    // Beleg: Layer 4 States QUEUED → MINE, SLA Punkt 4, Paket 7
                    if (this._state === STATES.QUEUED ||
                        this._state === STATES.TAKEOVER_PENDING) {
                        this._setLockId(data.lock_id);
                        this._lockedBy = null;
                        this._transition(STATES.MINE);
                        this._emitUp('acquired', { lockId: this._lockId });
                        this._dbg('lock_acquired (Queue/Takeover) → MINE, lock_id=', this._lockId);
                    }
                    break;

                case 'editor_lock_released':
                    // Globales Event: Lock freigegeben. Wenn wir MINE waren und
                    // unser Lock verschwunden ist (Grace-Period abgelaufen), lokal aufräumen.
                    // Normalfall: wir haben selbst release() aufgerufen, dann sind
                    // wir bereits IDLE — dieses Event wird ignoriert.
                    if (this._state === STATES.MINE) {
                        this._dbg('editor_lock_released während MINE — Lock extern verloren');
                        this._clearLockId();
                        this._transition(STATES.IDLE);
                        this._emitUp('released', {});
                    }
                    break;

                case 'lock_takeover_request':
                    // Übernahmeanfrage eingegangen — wir sind Lock-Inhaber.
                    // Beleg: Layer 4 States TAKEOVER_REQUEST_IN
                    if (this._state === STATES.MINE) {
                        this._pendingRequestId = data.request_id ?? null;
                        this._transition(STATES.TAKEOVER_REQUEST_IN);
                        this._emitUp('takeover_request', {
                            requestId:   data.request_id,
                            requestedBy: data.requested_by,
                            requestedAt: data.requested_at,
                        });
                        this._dbg('TAKEOVER_REQUEST_IN: requestedBy=', data.requested_by);
                    }
                    break;

                case 'lock_takeover_result':
                    // Ergebnis unserer Übernahmeanfrage (wir sind der Anfragende).
                    // Beleg: Layer 4 States TAKEOVER_PENDING → MINE / TAKEOVER_DENIED
                    if (this._state === STATES.TAKEOVER_PENDING) {
                        if (data.result === 'granted') {
                            // lock_acquired folgt separat mit der neuen lock_id.
                            // Hier nur Logging — Zustandswechsel nach MINE kommt
                            // über das lock_acquired-Event.
                            this._dbg('lock_takeover_result: granted — warte auf lock_acquired');
                        } else {
                            // denied: Cooldown beginnt
                            this._transition(STATES.TAKEOVER_DENIED);
                            this._emitUp('takeover_denied', {
                                cooldownUntil: this._cooldownUntil,
                            });
                            this._dbg('TAKEOVER_DENIED');
                        }
                    }
                    break;

                default:
                    // Andere Events (support_status, report_updated) ignorieren
                    break;
            }
        }

        /**
         * SSE reconnected (RESUMING → CONNECTED): Lock-Bindung prüfen.
         * Der Server hat in Paket 4 den Lock bereits auf die neue client_id
         * umgeschrieben. Wir müssen nichts tun außer zu loggen.
         * Beleg: Layer 2 States RESUMING, events.py resume_lock()
         */
        _onSseReconnected({ clientId, oldClientId }) {
            this._dbg('SSE reconnected: alte_id=', oldClientId, 'neue_id=', clientId);
            // Lock bleibt erhalten — kein Zustandswechsel nötig
        }

        /**
         * Layer-Kollaps: SSE DISCONNECTED oder ReportLayer IDLE.
         * Fällt auf IDLE zurück, ggf. über RELEASING.
         * Beleg: Layer 4 States Präambel
         */
        _onLayerCollapse(reason) {
            this._dbg('Layer-Kollaps:', reason, '— aktueller Zustand:', this._state);
            if (this._state === STATES.MINE ||
                this._state === STATES.TAKEOVER_REQUEST_IN) {
                // War Lock-Inhaber: RELEASING → IDLE (kein HTTP-Request — Verbindung weg)
                this._clearLockId();
                this._transition(STATES.RELEASING);
                this._transition(STATES.IDLE);
                this._emitUp('released', {});
            } else if (this._state !== STATES.IDLE &&
                       this._state !== STATES.UNINITIALIZED) {
                this._clearLockId();
                this._transition(STATES.IDLE);
            }
        }

        /**
         * ReportLayer hat einen Bericht geöffnet (OPENING → OPENED).
         * Automatischer acquire()-Versuch wenn ein lockId aus sessionStorage
         * vorhanden ist (Browser-Reload-Szenario).
         * Beleg: Layer 4 States ACQUIRING
         */
        _onReportOpened() {
            this._dbg('ReportLayer OPENED — prüfe sessionStorage auf lockId');
            // Wenn eine lockId aus sessionStorage vorliegt, versuchen wir einen
            // Auto-Resume via acquire() — der Server macht Auto-Resume wenn
            // locked_by == investigator (bereits in _action_acquire_lock implementiert).
            if (this._lockId && this._state === STATES.IDLE) {
                this._dbg('Auto-acquire mit gespeicherter lockId:', this._lockId);
                this.acquire();
            }
        }

        /**
         * ReportLayer hat einen neuen Bericht erstellt (NEW → OPENED).
         * Der Lock wurde atomar miterzeugt — lock_id aus dem created-Event übernehmen.
         * Beleg: Layer 3 States NEW, SLA Punkt 7
         */
        _onReportCreated({ lockId }) {
            if (!lockId) return;
            this._dbg('ReportLayer created: lock_id=', lockId, '→ MINE');
            this._setLockId(lockId);
            this._lockedBy = null;
            this._transition(STATES.MINE);
            this._emitUp('acquired', { lockId });
        }

        // -------------------------------------------------------------------
        // Interne Hilfsmethoden
        // -------------------------------------------------------------------

        /**
         * Prüft ob acquire() aus dem aktuellen Zustand sinnvoll ist.
         */
        _canAcquire() {
            const allowed = [STATES.IDLE, STATES.CONTESTED, STATES.TAKEOVER_DENIED];
            return allowed.includes(this._state);
        }

        /**
         * lockId setzen und in sessionStorage schreiben.
         * Beleg: Paket-7-Entscheidung sessionStorage-Key 'forensic_lock_v2'
         */
        _setLockId(lockId) {
            this._lockId = lockId;
            try { this._storage?.setItem(SESSION_KEY, lockId); } catch (_) {}
        }

        /**
         * lockId löschen und aus sessionStorage entfernen.
         */
        _clearLockId() {
            this._lockId = null;
            try { this._storage?.removeItem(SESSION_KEY); } catch (_) {}
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
                    console.error('[LockLayer] Up-Event-Listener Fehler:', eventName, err);
                }
            }
        }

        _dbg(...args) {
            if (this._debug) console.debug('[LockLayer]', ...args);
        }
    }

    // -----------------------------------------------------------------------
    // Export auf window
    // -----------------------------------------------------------------------

    window.LockLayer       = LockLayer;
    window.LockLayerStates = STATES;

})();
