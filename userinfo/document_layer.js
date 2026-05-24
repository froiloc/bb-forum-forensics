/**
 * userinfo/document_layer.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Layer 5 der geschichteten Editor-Architektur.
 *   Kapselt alle HTTP-Schreiboperationen auf dem Dokument (Blöcke, Anker).
 *   Ist der einzige Layer der fetch()-Aufrufe für Dokumentoperationen macht.
 *   Verwaltet den isDirty-Flag und den Auto-Save-Debounce.
 *
 * Voraussetzungen:
 *   SSELayer (Layer 2), ReportLayer (Layer 3) und LockLayer (Layer 4)
 *   müssen initialisiert sein. DocumentLayer wartet auf LockLayer.ready.
 *   Beleg: Schichten-Architektur, Paket 8
 *
 * Block-Operationen (delegiert von Layer 6):
 *   saveBlock(blockId, blockType, blockData, opts)
 *   updateBlock(blockId, blockData, opts)
 *   deleteBlock(blockId)
 *   reorder(order)
 *   addAnchor(blockId, annotationId, anchorText)
 *
 * Alle Schreiboperationen setzen isDirty = true und lösen
 * den Auto-Save-Debounce aus. isDirty wird nach erfolgreichem
 * Speichern zurückgesetzt.
 *
 * _sendRequest(action, payload):
 *   Einziger HTTP-Kanal für Dokumentoperationen.
 *   Baut den Kontext aus allen unteren Layern via _buildContext().
 *   Sendet lock_id im Body und X-Forensic-Lock-Id im Header.
 *   Gibt null zurück wenn kein Lock gehalten wird.
 *
 * _buildContext():
 *   Ruft contributeToContext() auf SSELayer, ReportLayer und LockLayer auf.
 *   Gibt { sseClientId, reportId, lockId } zurück.
 *   Beleg: contributeToContext()-Muster, Pakete 5–8
 *
 * isDirty-Flag:
 *   Wird auf true gesetzt bei jeder ungespeicherten Änderung.
 *   Wird auf false gesetzt nach erfolgreichem _sendRequest().
 *   Auto-Save-Debounce löst nach AUTOSAVE_DEBOUNCE_MS aus.
 *   Beleg: Paket 8, DocumentLayer-Spec
 *
 * Up-Events:
 *   saved     { blockId }   — Block erfolgreich gespeichert
 *   deleted   { blockId }   — Block erfolgreich gelöscht
 *   reordered {}            — Reihenfolge gespeichert
 *   anchored  { anchorId }  — Anker gespeichert
 *   error     { code, message, action } — Fehler bei Operation
 *
 * Version: v0.6.251 · Build: 251 · 2026-05-24
 * Beleg: DocumentLayer-Spec, Schichten-Architektur, Paket 8
 */

(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // Konstanten
    // -----------------------------------------------------------------------

    const REPORT_API = '/_forensic/report';

    /**
     * Standard-Auto-Save-Debounce in Millisekunden.
     * Überschreibbar via data-autosave-debounce-ms auf #report-editor-body
     * oder über den opts.autosaveDebounceMs-Konstruktorparameter.
     * Beleg: report_editor.js AUTOSAVE_DEBOUNCE_MS-Muster
     */
    const DEFAULT_AUTOSAVE_MS = 30000;

    // -----------------------------------------------------------------------
    // Klasse DocumentLayer
    // -----------------------------------------------------------------------

    /**
     * DocumentLayer — Layer 5 der Editor-Architektur.
     *
     * Instanziierung:
     *   const layer = new DocumentLayer({ sseLayer, reportLayer, lockLayer });
     *   await layer.ready;
     *   await layer.saveBlock('b1', 'paragraph', { text: 'Hallo' });
     *
     * Beleg: DocumentLayer-Spec, Paket 8
     */
    class DocumentLayer {

        /**
         * @param {object}      opts
         * @param {SSELayer}    opts.sseLayer          — Layer 2 (required)
         * @param {ReportLayer} opts.reportLayer        — Layer 3 (required)
         * @param {LockLayer}   opts.lockLayer          — Layer 4 (required)
         * @param {number}      [opts.autosaveDebounceMs] — Debounce-Zeit
         * @param {boolean}     [opts.debug]            — Debug-Logging
         * @param {Function}    [opts.fetchFn]          — fetch-Ersatz für Tests
         */
        constructor(opts = {}) {
            if (!opts.sseLayer)    throw new Error('[DocumentLayer] sseLayer erforderlich');
            if (!opts.reportLayer) throw new Error('[DocumentLayer] reportLayer erforderlich');
            if (!opts.lockLayer)   throw new Error('[DocumentLayer] lockLayer erforderlich');

            this._sse    = opts.sseLayer;
            this._report = opts.reportLayer;
            this._lock   = opts.lockLayer;
            this._debug  = opts.debug ?? (window.FORENSIC_DEBUG !== false);
            this._fetch  = opts.fetchFn ?? window.fetch.bind(window);

            // Auto-Save-Debounce: aus opts, DOM-Attribut oder Standard
            this._autosaveMs = opts.autosaveDebounceMs
                ?? (() => {
                    const body = typeof document !== 'undefined'
                        ? document.getElementById('report-editor-body')
                        : null;
                    const v = parseInt(body?.dataset?.autosaveDebounceMs, 10);
                    return Number.isFinite(v) && v > 0 ? v : DEFAULT_AUTOSAVE_MS;
                })();

            // isDirty-Flag: true wenn ungespeicherte Änderungen vorliegen
            // Beleg: Paket 8 DocumentLayer-Spec
            this._isDirty = false;

            // Debounce-Timer-Handle
            this._autosaveTimer = null;

            // Laufende Speicher-Requests { blockId -> true }
            // Verhindert parallele Requests für denselben Block
            this._pendingSaves = {};

            // Up-Event-Listener
            this._upListeners = {};

            // ready-Promise: wartet auf LockLayer.ready
            // Beleg: Layer-ready-Kette, Paket 8
            this.ready = this._lock.ready.then(() => {
                this._dbg('ready — LockLayer ist bereit');
            });
        }

        // -------------------------------------------------------------------
        // State (öffentlicher Lesezugriff)
        // -------------------------------------------------------------------

        /** True wenn ungespeicherte Änderungen vorliegen. */
        get isDirty() { return this._isDirty; }

        // -------------------------------------------------------------------
        // contributeToContext() — für künftige Layer 6
        // -------------------------------------------------------------------

        /**
         * Trägt den Dokument-Kontext zum HTTP-Request-Kontext bei.
         * Baut den vollständigen Kontext aus allen unteren Layern auf.
         * @returns {{ sseClientId, reportId, lockId }}
         */
        contributeToContext() {
            return this._buildContext();
        }

        // -------------------------------------------------------------------
        // Block-Operationen (Down-Kommandos von Layer 6)
        // -------------------------------------------------------------------

        /**
         * Block speichern (INSERT oder UPDATE).
         *
         * @param {string} blockId   — Block-ID (UUID)
         * @param {string} blockType — Editor.js-Tool-Name
         * @param {object|string} blockData — Block-Inhalt
         * @param {object} [opts]
         * @param {number} [opts.sortIndex]
         * @param {number} [opts.moduleId]
         * @param {string} [opts.placeholderValuesJson]
         * @returns {Promise<{blockId: string}|null>}
         */
        async saveBlock(blockId, blockType, blockData, opts = {}) {
            if (this._pendingSaves[blockId]) {
                this._dbg('saveBlock: läuft bereits für', blockId, '— übersprungen');
                return null;
            }
            this._pendingSaves[blockId] = true;
            this._setDirty();

            try {
                const payload = {
                    action:     'save_block',
                    block_id:   blockId,
                    block_type: blockType,
                    block_data: typeof blockData === 'string'
                        ? blockData
                        : JSON.stringify(blockData),
                };
                if (opts.sortIndex  != null) payload.sort_index             = opts.sortIndex;
                if (opts.moduleId   != null) payload.module_id              = opts.moduleId;
                if (opts.placeholderValuesJson != null)
                    payload.placeholder_values_json = opts.placeholderValuesJson;

                const result = await this._sendRequest(payload);
                if (result) {
                    this._clearDirty();
                    this._emitUp('saved', { blockId: result.block_id ?? blockId });
                    this._dbg('saveBlock ok:', blockId);
                }
                return result;
            } finally {
                delete this._pendingSaves[blockId];
            }
        }

        /**
         * Block-Inhalt aktualisieren.
         *
         * @param {string} blockId
         * @param {object|string} blockData
         * @param {object} [opts]
         * @returns {Promise<object|null>}
         */
        async updateBlock(blockId, blockData, opts = {}) {
            this._setDirty();
            const payload = {
                action:     'update_block',
                block_id:   blockId,
                block_data: typeof blockData === 'string'
                    ? blockData
                    : JSON.stringify(blockData),
            };
            if (opts.placeholderValuesJson != null)
                payload.placeholder_values_json = opts.placeholderValuesJson;

            const result = await this._sendRequest(payload);
            if (result) {
                this._clearDirty();
                this._emitUp('saved', { blockId });
            }
            return result;
        }

        /**
         * Block löschen.
         *
         * @param {string} blockId
         * @returns {Promise<object|null>}
         */
        async deleteBlock(blockId) {
            const payload = {
                action:   'delete_block',
                block_id: blockId,
            };
            const result = await this._sendRequest(payload);
            if (result) {
                this._emitUp('deleted', { blockId });
                this._dbg('deleteBlock ok:', blockId);
            }
            return result;
        }

        /**
         * Reihenfolge der Blöcke speichern.
         *
         * @param {Array<{id: string, sort_index: number}>} order
         * @returns {Promise<object|null>}
         */
        async reorder(order) {
            this._setDirty();
            const result = await this._sendRequest({
                action: 'reorder',
                order,
            });
            if (result) {
                this._clearDirty();
                this._emitUp('reordered', {});
            }
            return result;
        }

        /**
         * Beweisanker anlegen (Block ↔ Annotation).
         *
         * @param {string} blockId
         * @param {number} annotationId
         * @param {string} anchorText
         * @returns {Promise<{anchorId: number}|null>}
         */
        async addAnchor(blockId, annotationId, anchorText) {
            const payload = {
                action:        'add_anchor',
                block_id:      blockId,
                annotation_id: annotationId,
                anchor_text:   anchorText,
            };
            const result = await this._sendRequest(payload);
            if (result) {
                this._emitUp('anchored', { anchorId: result.anchor_id });
                this._dbg('addAnchor ok: block=', blockId, 'annotation=', annotationId);
            }
            return result;
        }

        // -------------------------------------------------------------------
        // Auto-Save
        // -------------------------------------------------------------------

        /**
         * Auto-Save-Debounce auslösen.
         * Wird von Layer 6 nach jeder Benutzeraktion aufgerufen.
         * Nach _autosaveMs ms ohne weitere Aufrufe wird triggerAutoSave()
         * ausgelöst.
         * Beleg: DocumentLayer-Spec isDirty + Auto-Save-Debounce
         */
        scheduleAutoSave(saveFn) {
            if (this._autosaveTimer !== null) {
                clearTimeout(this._autosaveTimer);
            }
            this._autosaveTimer = setTimeout(() => {
                this._autosaveTimer = null;
                if (this._isDirty) {
                    this._dbg('Auto-Save-Debounce ausgelöst');
                    saveFn();
                }
            }, this._autosaveMs);
        }

        /** Auto-Save-Timer abbrechen (z.B. bei Bericht-Wechsel). */
        cancelAutoSave() {
            if (this._autosaveTimer !== null) {
                clearTimeout(this._autosaveTimer);
                this._autosaveTimer = null;
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
        // Interne Methoden
        // -------------------------------------------------------------------

        /**
         * Baut den vollständigen HTTP-Request-Kontext aus allen unteren Layern auf.
         * Beleg: contributeToContext()-Muster, Pakete 5–8
         * @returns {{ sseClientId, reportId, lockId }}
         */
        _buildContext() {
            return {
                ...this._sse.contributeToContext(),
                ...this._report.contributeToContext(),
                ...this._lock.contributeToContext(),
            };
        }

        /**
         * Einziger HTTP-Kanal für alle Dokumentoperationen.
         *
         * Prüft vor dem Request ob ein Lock gehalten wird.
         * Fügt lock_id in den Body und X-Forensic-Lock-Id in den Header ein.
         * Gibt das geparste JSON-Ergebnis zurück oder null bei Fehler / kein Lock.
         *
         * @param {object} payload — Action + Parameter (ohne lock_id / report_id)
         * @returns {Promise<object|null>}
         */
        async _sendRequest(payload) {
            const ctx = this._buildContext();

            // Lock-Guard: kein Request ohne aktiven Lock
            if (!ctx.lockId) {
                this._dbg('_sendRequest: kein Lock — abgebrochen:', payload.action);
                this._emitUp('error', {
                    code:    'NO_LOCK',
                    message: 'Kein Lock gehalten — Schreiboperation abgebrochen',
                    action:  payload.action,
                });
                return null;
            }

            // report_id aus ReportLayer-Kontext, falls nicht im Payload gesetzt
            const body = {
                ...payload,
                report_id: payload.report_id ?? ctx.reportId,
                lock_id:   ctx.lockId,
            };

            try {
                const resp = await this._fetch(REPORT_API, {
                    method:  'POST',
                    headers: {
                        'Content-Type':       'application/json',
                        // Lock-ID auch im Header — Backend akzeptiert beide Wege
                        'X-Forensic-Lock-Id': ctx.lockId,
                    },
                    body: JSON.stringify(body),
                });

                const data = await resp.json();

                if (!resp.ok) {
                    this._dbg('_sendRequest: Server-Fehler', resp.status, payload.action, data);
                    this._emitUp('error', {
                        code:    data.code   ?? `HTTP_${resp.status}`,
                        message: data.error  ?? `Fehler ${resp.status}`,
                        action:  payload.action,
                    });
                    return null;
                }

                return data;

            } catch (err) {
                this._dbg('_sendRequest: Netzwerkfehler:', payload.action, err);
                this._emitUp('error', {
                    code:    'NETWORK_ERROR',
                    message: String(err),
                    action:  payload.action,
                });
                return null;
            }
        }

        /**
         * isDirty auf true setzen.
         * Beleg: DocumentLayer-Spec
         */
        _setDirty() {
            if (!this._isDirty) {
                this._isDirty = true;
                this._dbg('isDirty = true');
            }
        }

        /**
         * isDirty auf false setzen (nach erfolgreichem Speichern).
         * Beleg: DocumentLayer-Spec
         */
        _clearDirty() {
            if (this._isDirty) {
                this._isDirty = false;
                this._dbg('isDirty = false');
            }
        }

        _emitUp(eventName, payload) {
            const listeners = this._upListeners[eventName];
            if (!listeners || listeners.length === 0) return;
            for (const fn of listeners) {
                try { fn(payload); } catch (err) {
                    console.error('[DocumentLayer] Up-Event-Listener Fehler:', eventName, err);
                }
            }
        }

        _dbg(...args) {
            if (this._debug) console.debug('[DocumentLayer]', ...args);
        }
    }

    // -----------------------------------------------------------------------
    // Export auf window
    // -----------------------------------------------------------------------

    window.DocumentLayer = DocumentLayer;

})();
