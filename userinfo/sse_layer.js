/**
 * userinfo/sse_layer.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Layer 2 der geschichteten Editor-Architektur.
 *   Kapselt die SSE-Verbindung (/_forensic/events) vollständig.
 *   Alle höheren Layer (3, 4, 5, 6) beziehen ihren SSE-Kontext
 *   ausschließlich über diese Klasse.
 *
 * Zustände (clientseitig, gemäß Layer 2 States):
 *   UNINITIALIZED  — Initialzustand vor dem ersten connect()-Aufruf.
 *   DISCONNECTED   — Keine SSE-Verbindung; Grace-Period abgelaufen oder
 *                    noch keine Verbindung aufgebaut.
 *   CONNECTING     — EventSource wird gerade aufgebaut (aus DISCONNECTED).
 *   CONNECTED      — SSE-Verbindung steht; client_id empfangen.
 *   RESUMING       — SSE-Verbindung kurzzeitig unterbrochen; Grace-Period
 *                    läuft. Innerhalb dieser Zeit wird reconnect versucht.
 *
 * Sub-Interfaces:
 *   State  — Lesezugriff auf aktuellen Zustand und Daten.
 *   Up     — Events die SSELayer nach oben (an höhere Layer) sendet.
 *   Down   — Kommandos die höhere Layer an SSELayer senden können.
 *
 * State:
 *   state        {string}       — Aktueller Zustand (s.o.)
 *   clientId     {string|null}  — Aktuelle SSE-Client-ID oder null
 *
 * Up-Events (über _emitUp()):
 *   connected      { clientId }  — Verbindung steht; neue client_id verfügbar
 *   reconnected    { clientId }  — Verbindung nach RESUMING wiederhergestellt
 *   disconnected   {}            — Grace-Period abgelaufen; Verbindung verloren
 *   resuming       {}            — Verbindung unterbrochen; Grace-Period läuft
 *   sse_event      { name, data } — Durchleitung aller anderen SSE-Events an
 *                                   höhere Layer (support_status, lock_*, …)
 *
 * Down-Kommandos:
 *   connect()     — Verbindung aufbauen (aus DISCONNECTED / UNINITIALIZED).
 *   disconnect()  — Verbindung explizit schließen.
 *
 * contributeToContext():
 *   Gibt { sseClientId } zurück für den Kontext-Build höherer Layer.
 *   Beleg: Layer 2 States, contributeToContext()-Muster, Paket 5
 *
 * ready-Promise:
 *   Wird aufgelöst sobald der Zustand CONNECTED erstmalig erreicht wird
 *   (client_id empfangen). Höhere Layer awaiten diesen Promise vor ihrer
 *   eigenen Initialisierung.
 *   Beleg: Layer 2 States, Paket 5
 *
 * Grace-Period:
 *   Beim Verbindungsabbruch wechselt SSELayer in RESUMING und startet
 *   einen clientseitigen Timer (_GRACE_MS). EventSource reconnectet
 *   automatisch (Browser-API). Falls die neue Verbindung das client_id-
 *   Event liefert bevor der Timer abläuft, geht SSELayer in CONNECTED
 *   über und sendet resume_client_id an den Server.
 *   Nach Timer-Ablauf wechselt SSELayer in DISCONNECTED.
 *   Beleg: SLA Punkt 2, Layer 2 States RESUMING, Paket 4 / Paket 5
 *
 * Version: v0.6.247 · Build: 247 · 2026-05-24
 * Beleg: Layer 2 States, SLA Manifest, Paket 5, Architekturentscheidungen
 */

(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // Konstanten
    // -----------------------------------------------------------------------

    /** SSE-Endpunkt. Muss mit FORENSIC_API.EVENTS in userinfo.js übereinstimmen. */
    const SSE_ENDPOINT = '/_forensic/events';

    /**
     * Grace-Period in Millisekunden (clientseitig).
     * Muss zum serverseitigen _GRACE_PERIOD_SEC (events.py) passen.
     * Etwas großzügiger als serverseitig (6s statt 5s) damit der
     * Reconnect-Handshake Zeit hat abzuschließen bevor der Server
     * den Lock freigibt.
     * Beleg: SLA Punkt 2, events.py _GRACE_PERIOD_SEC=5
     */
    const _GRACE_MS = 6000;

    /**
     * Maximale Wartezeit auf das erste client_id-Event beim initialen
     * Verbindungsaufbau. Nach Ablauf wird ready() trotzdem aufgelöst
     * (Fehlertoleranz), der Zustand bleibt CONNECTING bis client_id kommt.
     * Beleg: Bugfix Build 089 (10s-Timeout), userinfo.js initSSEWindow3()
     */
    const _READY_TIMEOUT_MS = 10000;

    // Gültige Zustände
    const STATES = Object.freeze({
        UNINITIALIZED: 'UNINITIALIZED',
        DISCONNECTED:  'DISCONNECTED',
        CONNECTING:    'CONNECTING',
        CONNECTED:     'CONNECTED',
        RESUMING:      'RESUMING',
    });

    // -----------------------------------------------------------------------
    // Klasse SSELayer
    // -----------------------------------------------------------------------

    /**
     * SSELayer — Layer 2 der Editor-Architektur.
     *
     * Instanziierung:
     *   const layer = new SSELayer({ debug: true });
     *   await layer.ready;
     *   const ctx = layer.contributeToContext(); // { sseClientId: '...' }
     *
     * Beleg: Layer 2 States, SLA Manifest, Paket 5
     */
    class SSELayer {

        /**
         * @param {object}   [opts]
         * @param {boolean}  [opts.debug=false]   — Debug-Logging ein/aus
         * @param {string}   [opts.endpoint]       — SSE-Endpunkt (überschreibbar
         *                                           für Tests)
         * @param {Function} [opts.EventSourceCtor] — EventSource-Klasse
         *                                            (Injection für Tests;
         *                                             Standard: window.EventSource)
         */
        constructor(opts = {}) {
            this._debug        = opts.debug        ?? (window.FORENSIC_DEBUG !== false);
            this._endpoint     = opts.endpoint     ?? SSE_ENDPOINT;
            this._EventSource  = opts.EventSourceCtor ?? window.EventSource;

            // Zustand
            this._state     = STATES.UNINITIALIZED;
            this._clientId  = null;

            // Laufende EventSource-Instanz
            this._evtSrc    = null;

            // Grace-Period-Timer (clientseitig)
            this._graceTimer = null;

            // Up-Event-Listener { eventName -> [fn, ...] }
            this._upListeners = {};

            // ready-Promise: wird aufgelöst beim ersten CONNECTED
            // Beleg: Paket 5, higher-layer auto-init via ready-Promise
            this._readyResolve = null;
            this.ready = new Promise(resolve => {
                this._readyResolve = resolve;
            });

            // Ready-Timeout: fortfahren auch wenn client_id ausbleibt
            this._readyTimeoutId = setTimeout(() => {
                this._dbg('ready-Timeout nach', _READY_TIMEOUT_MS, 'ms — fortfahren ohne client_id');
                if (this._readyResolve) {
                    this._readyResolve();
                    this._readyResolve = null;
                }
            }, _READY_TIMEOUT_MS);

            this._dbg('SSELayer konstruiert');
        }

        // -------------------------------------------------------------------
        // State (öffentlicher Lesezugriff)
        // -------------------------------------------------------------------

        /** Aktueller Zustandsname (UNINITIALIZED / DISCONNECTED / …). */
        get state() { return this._state; }

        /**
         * Aktuelle SSE-Client-ID oder null wenn keine Verbindung steht.
         * Beleg: Layer 2 States, SLA Punkt 1
         */
        get clientId() { return this._clientId; }

        // -------------------------------------------------------------------
        // contributeToContext()
        // -------------------------------------------------------------------

        /**
         * Trägt den SSE-Layer-Kontext zum HTTP-Request-Kontext bei.
         * Wird von DocumentLayer._buildContext() aufgerufen.
         *
         * @returns {{ sseClientId: string|null }}
         * Beleg: contributeToContext()-Muster, Paket 5
         */
        contributeToContext() {
            return { sseClientId: this._clientId };
        }

        // -------------------------------------------------------------------
        // Down — Kommandos von höheren Layern
        // -------------------------------------------------------------------

        /**
         * Down.connect(): SSE-Verbindung aufbauen.
         *
         * Nur aus UNINITIALIZED oder DISCONNECTED sinnvoll.
         * Im Zustand CONNECTING oder CONNECTED wird der Aufruf ignoriert.
         * Beleg: Layer 2 States DISCONNECTED -> CONNECTING
         */
        connect() {
            if (this._state === STATES.CONNECTING ||
                this._state === STATES.CONNECTED  ||
                this._state === STATES.RESUMING) {
                this._dbg('connect() ignoriert — Zustand:', this._state);
                return;
            }
            this._dbg('connect() aufgerufen aus Zustand:', this._state);
            this._transition(STATES.CONNECTING);
            this._openEventSource(null);
        }

        /**
         * Down.disconnect(): SSE-Verbindung explizit schließen.
         *
         * Schließt die EventSource und wechselt in DISCONNECTED.
         * Grace-Period wird abgebrochen (kein automatischer Reconnect).
         * Beleg: Layer 2 States
         */
        disconnect() {
            this._dbg('disconnect() aufgerufen');
            this._cancelGraceTimer();
            this._closeEventSource();
            this._clientId = null;
            this._transition(STATES.DISCONNECTED);
        }

        // -------------------------------------------------------------------
        // Up — Event-Bus nach oben
        // -------------------------------------------------------------------

        /**
         * Listener auf ein Up-Event registrieren.
         *
         * @param {string}   eventName  — z.B. 'connected', 'sse_event'
         * @param {Function} fn         — Callback(payload)
         */
        on(eventName, fn) {
            if (!this._upListeners[eventName]) {
                this._upListeners[eventName] = [];
            }
            this._upListeners[eventName].push(fn);
        }

        /**
         * Listener entfernen.
         *
         * @param {string}   eventName
         * @param {Function} fn
         */
        off(eventName, fn) {
            if (!this._upListeners[eventName]) return;
            this._upListeners[eventName] =
                this._upListeners[eventName].filter(f => f !== fn);
        }

        // -------------------------------------------------------------------
        // Interne Methoden
        // -------------------------------------------------------------------

        /**
         * EventSource öffnen.
         *
         * @param {string|null} resumeClientId  — Alte SSE-Client-ID für RESUMING
         *                                         oder null beim ersten Aufbau.
         *                                         Beleg: Layer 2 States RESUMING,
         *                                         Paket 4 events.py ?resume_client_id
         */
        _openEventSource(resumeClientId) {
            // Vorherige Verbindung schließen falls noch offen
            this._closeEventSource();

            // URL zusammenbauen
            // RESUMING: alte client_id mitsenden damit der Server den Grace-Timer
            // löscht und den Lock auf die neue client_id umschreibt.
            // Beleg: Paket 4 events.py _cancel_grace_timer(), resume_lock()
            let url = this._endpoint;
            if (resumeClientId) {
                url += '?resume_client_id=' + encodeURIComponent(resumeClientId);
            }
            this._dbg('EventSource öffnen:', url);

            // EventSource-Instanz erzeugen (injizierbar für Tests)
            const es = new this._EventSource(url);
            this._evtSrc = es;

            // client_id-Event: Server bestätigt Verbindung und sendet neue ID
            es.addEventListener('client_id', (evt) => {
                this._onClientId(evt);
            });

            // Alle anderen SSE-Events als generisches sse_event nach oben weiterleiten.
            // Layer 3 und 4 abonnieren spezifische Ereignisse darüber.
            // Beleg: Up.sse_event, Paket 5
            const _passthroughEvents = [
                'support_status',
                'editor_lock_acquired',
                'editor_lock_released',
                'lock_acquired',
                'lock_takeover_request',
                'lock_takeover_result',
                'report_updated',
            ];
            for (const name of _passthroughEvents) {
                es.addEventListener(name, (evt) => {
                    let data = null;
                    try { data = JSON.parse(evt.data); } catch (_) { data = {}; }
                    this._emitUp('sse_event', { name, data });
                });
            }

            // Verbindungsabbruch: Grace-Period starten
            es.onerror = () => {
                this._onError();
            };
        }

        /**
         * Empfang des client_id-Events vom Server.
         *
         * Unterscheidet:
         *   a) Erstverbindung (CONNECTING)      → CONNECTED
         *   b) Reconnect in Grace-Period (RESUMING) → CONNECTED (reconnected)
         *   c) Reconnect nach Grace-Period (DISCONNECTED, CONNECTING)
         *      → CONNECTED (neue Verbindung)
         *
         * @param {MessageEvent} evt
         */
        _onClientId(evt) {
            let newClientId;
            try {
                const payload = JSON.parse(evt.data);
                newClientId = payload.client_id;
            } catch (_) {
                this._dbg('client_id-Event: ungültiges JSON', evt.data);
                return;
            }
            if (!newClientId) return;

            this._dbg('client_id empfangen:', newClientId, 'Zustand vorher:', this._state);

            const wasResuming  = (this._state === STATES.RESUMING);
            const oldClientId  = this._clientId;

            // Grace-Timer löschen — Verbindung ist geheilt
            this._cancelGraceTimer();

            this._clientId = newClientId;
            this._transition(STATES.CONNECTED);

            // ready-Promise auflösen (einmalig)
            if (this._readyResolve) {
                clearTimeout(this._readyTimeoutId);
                this._readyResolve();
                this._readyResolve = null;
            }

            if (wasResuming && oldClientId) {
                // RESUMING → CONNECTED: alte client_id an Server melden
                // Der Server hat in events.py _cancel_grace_timer() bereits
                // durch den ?resume_client_id-Parameter ausgelöst.
                // Hier nur Up-Event für höhere Layer.
                // Beleg: Layer 2 States RESUMING → CONNECTED
                this._dbg('RESUMING → CONNECTED: alte_id=', oldClientId, 'neue_id=', newClientId);
                this._emitUp('reconnected', { clientId: newClientId, oldClientId });
            } else {
                this._emitUp('connected', { clientId: newClientId });
            }
        }

        /**
         * Verbindungsabbruch (EventSource.onerror bei readyState CLOSED).
         *
         * EventSource versucht automatisch zu reconnecten (Browser-API).
         * Wir starten nur den Grace-Timer und wechseln in RESUMING wenn
         * wir vorher CONNECTED waren.
         *
         * Beleg: Layer 2 States CONNECTED → RESUMING, SLA Punkt 2
         */
        _onError() {
            // EventSource.CLOSED = 2; CONNECTING = 0
            const isClosed = this._evtSrc && this._evtSrc.readyState === 2;

            if (this._state === STATES.CONNECTED) {
                this._dbg('SSE-Verbindung unterbrochen — RESUMING, Grace-Period startet');
                this._transition(STATES.RESUMING);
                this._emitUp('resuming', {});
                this._startGraceTimer();
            } else if (this._state === STATES.CONNECTING && isClosed) {
                // Initiale Verbindung scheitert vollständig
                this._dbg('SSE-Verbindungsaufbau fehlgeschlagen → DISCONNECTED');
                this._transition(STATES.DISCONNECTED);
                this._emitUp('disconnected', {});
            }
            // Im Zustand RESUMING: Browser reconnectet bereits automatisch —
            // wir warten auf das nächste client_id-Event.
        }

        /**
         * Grace-Timer starten.
         * Nach _GRACE_MS Millisekunden → DISCONNECTED.
         * Beleg: SLA Punkt 2, Layer 2 States RESUMING
         */
        _startGraceTimer() {
            this._cancelGraceTimer();
            this._graceTimer = setTimeout(() => {
                this._graceTimer = null;
                this._dbg('Grace-Period abgelaufen → DISCONNECTED');
                this._clientId = null;
                this._transition(STATES.DISCONNECTED);
                this._emitUp('disconnected', {});
            }, _GRACE_MS);
        }

        /** Grace-Timer abbrechen (RESUMING erfolgreich geheilt). */
        _cancelGraceTimer() {
            if (this._graceTimer !== null) {
                clearTimeout(this._graceTimer);
                this._graceTimer = null;
                this._dbg('Grace-Timer abgebrochen');
            }
        }

        /** EventSource schließen ohne Zustandsänderung. */
        _closeEventSource() {
            if (this._evtSrc) {
                try { this._evtSrc.close(); } catch (_) {}
                this._evtSrc = null;
            }
        }

        /**
         * Zustandsübergang mit Logging.
         * @param {string} newState
         */
        _transition(newState) {
            if (this._state !== newState) {
                this._dbg('Zustandsübergang:', this._state, '→', newState);
                this._state = newState;
            }
        }

        /**
         * Up-Event an registrierte Listener senden.
         * @param {string} eventName
         * @param {object} payload
         */
        _emitUp(eventName, payload) {
            const listeners = this._upListeners[eventName];
            if (!listeners || listeners.length === 0) return;
            for (const fn of listeners) {
                try { fn(payload); } catch (err) {
                    console.error('[SSELayer] Up-Event-Listener Fehler:', eventName, err);
                }
            }
        }

        /** Debug-Logging (nur wenn FORENSIC_DEBUG !== false). */
        _dbg(...args) {
            if (this._debug) {
                console.debug('[SSELayer]', ...args);
            }
        }
    }

    // -----------------------------------------------------------------------
    // Export auf window
    // -----------------------------------------------------------------------

    /**
     * SSELayer auf window exportieren damit userinfo.js und höhere Layer
     * (report_layer.js, lock_layer.js, …) darauf zugreifen können.
     * Beleg: Paket 5, Architekturentscheidung je-Datei-je-Layer
     */
    window.SSELayer = SSELayer;

    /**
     * STATES-Konstante exportieren damit Tests und höhere Layer die
     * Zustandsnamen typsicher verwenden können.
     */
    window.SSELayerStates = STATES;

})();
