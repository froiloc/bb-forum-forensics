/**
 * userinfo/editor_bootstrap.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 6: Berichte & Exports
 *
 * Zweck:
 *   Zentrales Bootstrapping der Editor-Schichtenarchitektur (Option C).
 *   Instanziiert und verdrahtet alle vier Layer in der korrekten Reihenfolge:
 *
 *     SSELayer (Layer 2)
 *       ↓ wird von
 *     ReportLayer (Layer 3)
 *       ↓ wird von
 *     LockLayer (Layer 4)
 *       ↓ wird von
 *     DocumentLayer (Layer 5)
 *
 *   Exportiert alle Instanzen auf window:
 *     window.sseLayer
 *     window.reportLayer
 *     window.lockLayer
 *     window.documentLayer
 *
 *   Registriert Layer-übergreifende Reaktionen:
 *     - LockLayer 'acquired' → readOnly.toggle() im Editor
 *     - LockLayer 'released' → readOnly einschalten
 *     - ReportLayer 'created' → initReportSelector(reportId) aufrufen
 *
 *   Voraussetzungen (müssen vor diesem Skript geladen sein):
 *     sse_layer.js, report_layer.js, lock_layer.js, document_layer.js
 *
 * Diese Datei hat KEINE Abhängigkeit zu userinfo.js.
 * userinfo.js bleibt für Fenster 1/2 (Nutzerinfos, Annotationsübersicht)
 * zuständig. editor_bootstrap.js ist ausschließlich für Fenster 3 (Editor).
 * Beleg: Option C, Architekturentscheidung Paket-9-Review 2026-05-24
 *
 * Version: v0.6.265 · Build: 265 · 2026-05-31
 *
 * Changelog Build 265 (2026-05-31):
 *   - SSELayer erhält role: 'report' damit der Server Duplikat-SSE-Verbindungen
 *     mit HTTP 409 abweisen kann. Beleg: Projektgespräch 2026-05-31.
 * Beleg: Paket 9, editor_bootstrap.js, Schichten-Architektur
 */

(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // Debug-Logging
    // -----------------------------------------------------------------------

    function _dbg(...args) {
        if (window.FORENSIC_DEBUG !== false) {
            console.debug('[editor_bootstrap]', ...args);
        }
    }

    // -----------------------------------------------------------------------
    // Bootstrap-Funktion
    // Wird sofort aufgerufen aber wartet auf DOMContentLoaded falls nötig.
    // -----------------------------------------------------------------------

    async function bootstrap() {
        _dbg('bootstrap() gestartet');

        // Voraussetzungen prüfen: alle Layer-Klassen müssen geladen sein
        if (!window.SSELayer || !window.ReportLayer ||
            !window.LockLayer || !window.DocumentLayer) {
            console.error(
                '[editor_bootstrap] Layer-Klassen nicht verfügbar. ' +
                'Reihenfolge der Script-Tags prüfen: ' +
                'sse_layer.js → report_layer.js → lock_layer.js → ' +
                'document_layer.js → editor_bootstrap.js'
            );
            return;
        }

        // ---------------------------------------------------------------
        // Layer 2: SSELayer
        // ---------------------------------------------------------------

        const sseLayer = new window.SSELayer({
            debug: window.FORENSIC_DEBUG !== false,
            // Fenster-Rolle für Duplikat-SSE-Schutz (Build 265).
            // Beleg: Projektgespräch 2026-05-31.
            role: 'report',
        });
        window.sseLayer = sseLayer;
        _dbg('SSELayer instanziiert');

        // SSE-Verbindung herstellen
        sseLayer.connect();

        // ---------------------------------------------------------------
        // Layer 3: ReportLayer
        // ---------------------------------------------------------------

        const reportLayer = new window.ReportLayer({
            sseLayer,
            debug: window.FORENSIC_DEBUG !== false,
        });
        window.reportLayer = reportLayer;
        _dbg('ReportLayer instanziiert');

        // ---------------------------------------------------------------
        // Layer 4: LockLayer
        // ---------------------------------------------------------------

        const lockLayer = new window.LockLayer({
            sseLayer,
            reportLayer,
            debug: window.FORENSIC_DEBUG !== false,
        });
        window.lockLayer = lockLayer;
        _dbg('LockLayer instanziiert');

        // ---------------------------------------------------------------
        // Layer 5: DocumentLayer
        // ---------------------------------------------------------------

        const documentLayer = new window.DocumentLayer({
            sseLayer,
            reportLayer,
            lockLayer,
            debug: window.FORENSIC_DEBUG !== false,
        });
        window.documentLayer = documentLayer;
        _dbg('DocumentLayer instanziiert');

        // ---------------------------------------------------------------
        // Auf alle Layer warten
        // ---------------------------------------------------------------

        await documentLayer.ready;
        _dbg('Alle Layer bereit');

        // ---------------------------------------------------------------
        // Layer-übergreifende Reaktionen verdrahten
        // ---------------------------------------------------------------

        /**
         * LockLayer 'acquired': Lock erworben.
         * Editor aus readOnly-Modus holen (falls er nicht bereits schreibbar ist).
         * Beleg: LockLayer Up-Event 'acquired', Paket 9
         */
        lockLayer.on('acquired', ({ lockId }) => {
            _dbg('LockLayer acquired: lockId=', lockId);
            const ed = window._editor;
            if (ed?.readOnly?.isEnabled) {
                ed.readOnly.toggle().then(() => {
                    _dbg('Editor readOnly deaktiviert nach Lock-Erwerb');
                    if (window.updateEditorPlaceholder) window.updateEditorPlaceholder(true);
                    if (window._updateLockStatus) window._updateLockStatus('lock-mine', 'Lock: ich');
                    // ModulePanel über neue Lock-ID informieren (Lesezugriff auf
                    // lockLayer.lockId statt direkter Übergabe)
                    if (window.ModulePanel?._refreshLockId) {
                        window.ModulePanel._refreshLockId(lockId);
                    }
                }).catch(err => {
                    _dbg('Editor readOnly toggle fehlgeschlagen:', err);
                });
            } else {
                // Editor bereits schreibbar (Create-Flow: Lock und Editor gleichzeitig)
                if (window._updateLockStatus) window._updateLockStatus('lock-mine', 'Lock: ich');
            }
        });

        /**
         * LockLayer 'released': Lock freigegeben.
         * Editor in readOnly-Modus versetzen.
         * Beleg: LockLayer Up-Event 'released', Paket 9
         */
        lockLayer.on('released', () => {
            _dbg('LockLayer released — Editor auf readOnly');
            const ed = window._editor;
            if (ed && !ed.readOnly?.isEnabled) {
                ed.readOnly.toggle().then(() => {
                    _dbg('Editor readOnly aktiviert nach Lock-Freigabe');
                    if (window.updateEditorPlaceholder) window.updateEditorPlaceholder(false);
                    if (window._updateLockStatus) window._updateLockStatus('lock-free', 'Kein Lock');
                }).catch(err => {
                    _dbg('Editor readOnly toggle (release) fehlgeschlagen:', err);
                });
            }
        });

        /**
         * LockLayer 'contested': Lock belegt von anderem.
         * UI informieren.
         * Beleg: LockLayer Up-Event 'contested', Paket 9
         */
        lockLayer.on('contested', ({ lockedBy }) => {
            _dbg('LockLayer contested: lockedBy=', lockedBy);
            if (window._updateLockStatus) {
                window._updateLockStatus('lock-other', `Lock: ${lockedBy || '?'}`);
            }
        });

        /**
         * ReportLayer 'created': Neuer Bericht angelegt.
         * Bericht-Selektor neu aufbauen und auf den neuen Bericht vorwählen.
         * Beleg: ReportLayer Up-Event 'created', Paket 9
         */
        reportLayer.on('created', ({ reportId }) => {
            _dbg('ReportLayer created: reportId=', reportId);
            if (window.initReportSelector) {
                window.initReportSelector(reportId).catch(err => {
                    console.warn('[editor_bootstrap] initReportSelector nach create:', err);
                });
            }
        });

        /**
         * ReportLayer 'opened': Bericht geöffnet.
         * LockLayer informieren dass ein neuer Bericht aktiv ist
         * (löst ggf. Auto-Acquire aus wenn sessionStorage-Lock vorhanden).
         * Beleg: ReportLayer Up-Event 'opened', LockLayer._onReportOpened(), Paket 9
         */
        // (LockLayer hört bereits intern auf reportLayer — kein doppelter Listener nötig)

        /**
         * SSELayer 'connected' / 'reconnected': SSE-Client-ID verfügbar.
         * Debug-Logging.
         */
        sseLayer.on('connected', ({ clientId }) => {
            _dbg('SSELayer connected: clientId=', clientId);
        });
        sseLayer.on('reconnected', ({ clientId, oldClientId }) => {
            _dbg('SSELayer reconnected: alt=', oldClientId, 'neu=', clientId);
        });
        sseLayer.on('disconnected', () => {
            _dbg('SSELayer disconnected — Layer-Kollaps läuft');
        });

        _dbg('bootstrap() abgeschlossen — alle Listener registriert');
    }

    // -----------------------------------------------------------------------
    // Initialisierung: Sofort starten wenn DOM bereit ist
    // -----------------------------------------------------------------------

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap);
    } else {
        // DOM bereits geladen (Skript am Ende des body)
        bootstrap().catch(err => {
            console.error('[editor_bootstrap] bootstrap() fehlgeschlagen:', err);
        });
    }

})();
