/**
 * userinfo/debug_events.js
 * IT-Forensisches Ermittlungswerkzeug — B6: Event-Debug-Tracing
 *
 * Zweck:
 *   Stellt window._uevt() bereit — einen zentralen Logging-Wrapper,
 *   der bei Event-Handlern aufgerufen wird und im DevTools-Log
 *   klar unterscheidet, ob ein Ereignis durch den BENUTZER ausgelöst
 *   wurde (Mouse / Keyboard / Touch / Drag&Drop) oder durch den
 *   WORKFLOW (programmatischer Aufruf, SSE, AJAX-Callback, internes
 *   dispatchEvent).
 *
 * Erkennungsmethode:
 *   Das Browser-eigene Event.isTrusted-Flag ist WAHR, wenn ein Event
 *   aus einer echten Benutzerinteraktion stammt, und FALSCH bei
 *   per JavaScript erzeugten Events (dispatchEvent, .click(), etc.).
 *   Dieses Flag ist schreibgeschützt und kann nicht verfälscht werden.
 *   Beleg: https://developer.mozilla.org/en-US/docs/Web/API/Event/isTrusted
 *
 *   Kein Event-Objekt vorhanden → immer WORKFLOW (interner Aufruf).
 *
 * Ausgabe-Format in der DevTools-Console:
 *   [USER]     [module] eventType  — detail
 *   [WORKFLOW] [module] eventType  — detail
 *
 *   Farbcodierung:
 *     [USER]     → grün (console.debug, Group mit grünem Label)
 *     [WORKFLOW] → grau (console.debug, gedämpft)
 *
 * Verwendung in anderen Modulen:
 *   // Am Beginn jedes Event-Handlers aufrufen:
 *   window._uevt(e, 'report_editor', 'click:btn-save', { blockId });
 *   //          ^    ^                ^                  ^
 *   //          |    |                |                  optional Details-Objekt
 *   //          |    |                beschreibender Name des Handlers
 *   //          |    Modulname (Dateiname ohne .js)
 *   //          das DOM-Event-Objekt (oder null für Workflow-Aufrufe)
 *
 * Aktivierung / Deaktivierung:
 *   window.FORENSIC_DEBUG = false  → schaltet gesamtes Logging ab
 *   window.FORENSIC_EVENT_DEBUG = false → schaltet nur _uevt() ab,
 *                                          allgemeines _dbg() bleibt an
 *
 * Build 200: Erstimplementierung.
 * Beleg: Projektgespräch 2026-05-17 — Debugging-Session B6
 *
 * ---------------------------------------------------------------------------
 * IIFE-Wrapper: Kein globaler Namensraum-Leak ausser window._uevt
 * ---------------------------------------------------------------------------
 */
(function () {
    'use strict';

    // -----------------------------------------------------------------------
    // Interne Hilfsfunktion: Ursprungsklassifikation
    // -----------------------------------------------------------------------

    /**
     * Bestimmt, ob ein Event eine echte Benutzerinteraktion ist.
     *
     * Logik:
     *   1. Kein Event-Objekt → WORKFLOW (programmatischer Aufruf ohne Event)
     *   2. isTrusted === true → USER (Browser hat das Event erzeugt)
     *   3. Alles andere → WORKFLOW (JS-erzeugtes Event)
     *
     * @param {Event|null|undefined} evt
     * @returns {{ isUser: boolean, source: 'USER'|'WORKFLOW', inputType: string }}
     */
    function _classifyEvent(evt) {
        if (!evt || typeof evt !== 'object') {
            return { isUser: false, source: 'WORKFLOW', inputType: 'kein Event' };
        }

        if (evt.isTrusted === true) {
            // Echte Benutzerinteraktion — Eingabeart ermitteln
            const inputType = _detectInputType(evt);
            return { isUser: true, source: 'USER', inputType };
        }

        // isTrusted === false → per JS ausgelöst
        return { isUser: false, source: 'WORKFLOW', inputType: 'programmatisch' };
    }

    /**
     * Ermittelt die Art der Benutzereingabe aus dem Event-Typ.
     *
     * @param {Event} evt
     * @returns {string}
     */
    function _detectInputType(evt) {
        const t = evt.type || '';

        if (t.startsWith('mouse') || t === 'click' || t === 'dblclick' ||
            t === 'contextmenu' || t === 'wheel') {
            return 'Mouse';
        }
        if (t.startsWith('key')) {
            return 'Keyboard';
        }
        if (t.startsWith('touch')) {
            return 'Touch';
        }
        if (t.startsWith('drag') || t === 'drop') {
            return 'Drag&Drop';
        }
        if (t === 'input' || t === 'change' || t === 'focus' ||
            t === 'blur' || t === 'focusin' || t === 'focusout' ||
            t === 'select') {
            // Kann Tastatur- oder Maus-Ursprung haben; als 'Input' markieren.
            // Bei Bedarf kann hier evt.inputType (InputEvent) ausgewertet werden.
            return 'Input';
        }
        // Fallback: Event-Typ direkt ausgeben
        return t || 'unbekannt';
    }

    // -----------------------------------------------------------------------
    // CSS-Farben für console.debug-Gruppen
    // -----------------------------------------------------------------------
    const _COLOR_USER     = 'color: #22c55e; font-weight: bold;'; // grün
    const _COLOR_WORKFLOW = 'color: #94a3b8; font-weight: normal;'; // grau-blau
    const _COLOR_MODULE   = 'color: #f59e0b; font-weight: normal;'; // amber
    const _COLOR_DETAIL   = 'color: #cbd5e1; font-weight: normal;'; // hellgrau

    // -----------------------------------------------------------------------
    // Öffentliche API: window._uevt()
    // -----------------------------------------------------------------------

    /**
     * Zentraler Event-Tracer für alle B6-Event-Handler.
     *
     * Gibt eine farblich codierte Zeile in der DevTools-Console aus:
     *   [USER/WORKFLOW] [module] handlerName — Eingabeart — optionale Details
     *
     * Wird NICHT ausgegeben wenn:
     *   - window.FORENSIC_DEBUG === false  (globaler Kill-Switch)
     *   - window.FORENSIC_EVENT_DEBUG === false (Event-Logging-Kill-Switch)
     *
     * @param {Event|null|undefined} evt      Das DOM-Event-Objekt (oder null)
     * @param {string}               module   Modulname, z.B. 'report_editor'
     * @param {string}               handler  Beschreibender Handler-Name,
     *                                        z.B. 'click:btn-save'
     * @param {Object}               [detail] Optionales Detail-Objekt (beliebige
     *                                        Schlüssel/Werte für extra Kontext)
     */
    window._uevt = function _uevt(evt, module, handler, detail) {
        // Kill-Switches prüfen
        if (window.FORENSIC_DEBUG === false) return;
        if (window.FORENSIC_EVENT_DEBUG === false) return;

        const { isUser, source, inputType } = _classifyEvent(evt);

        const color  = isUser ? _COLOR_USER : _COLOR_WORKFLOW;
        const prefix = isUser ? '[USER]    ' : '[WORKFLOW]';

        // Kompakte Ausgabe mit CSS-Styling in der Console
        // Format: "[USER]    [module_panel] click:btn-insert — Mouse"
        const label = `%c${prefix}%c [${module}]%c ${handler} — ${inputType}`;

        if (detail && typeof detail === 'object' && Object.keys(detail).length > 0) {
            // Mit Detail-Objekt: aufklappbare Gruppe
            console.groupCollapsed(label, color, _COLOR_MODULE, _COLOR_DETAIL);
            console.debug('%cDetails:', _COLOR_DETAIL, detail);
            if (evt) {
                console.debug('%cEvent:', _COLOR_DETAIL, {
                    type:      evt.type,
                    target:    evt.target,
                    isTrusted: evt.isTrusted,
                });
            }
            console.groupEnd();
        } else {
            // Ohne Details: einfache Zeile (ressourcenschonend)
            console.debug(label, color, _COLOR_MODULE, _COLOR_DETAIL);
        }
    };

    // -----------------------------------------------------------------------
    // Globaler Listener-Monitor: protokolliert ALLE isTrusted-Events
    // auf document-Ebene, wenn window.FORENSIC_EVENT_TRACE = true
    // -----------------------------------------------------------------------
    // Zweck:
    //   Mit window.FORENSIC_EVENT_TRACE = true kann man in der Console
    //   JEDEN vom Benutzer ausgelösten Event auf dem gesamten Dokument
    //   sehen — nützlich um zu prüfen, welche Events überhaupt ankommen
    //   und ob sie korrekt als USER klassifiziert würden.
    //
    //   Achtung: Sehr gesprächig! Nur bei gezielter Diagnose einschalten.
    //   In der Console: window.FORENSIC_EVENT_TRACE = true
    //
    // Beleg: Debugging-Anforderung Projektgespräch 2026-05-17
    // -----------------------------------------------------------------------
    const _TRACE_TYPES = [
        'click', 'dblclick', 'mousedown', 'mouseup',
        'keydown', 'keyup', 'keypress',
        'input', 'change', 'focus', 'blur',
        'dragstart', 'dragend', 'dragover', 'drop',
        'touchstart', 'touchend',
    ];

    function _globalEventTrace(evt) {
        if (!window.FORENSIC_EVENT_TRACE) return;
        if (window.FORENSIC_DEBUG === false) return;
        if (!evt.isTrusted) return; // Nur echte User-Events im Trace-Modus

        const tgt = evt.target;
        const tgtDesc = tgt
            ? `<${tgt.tagName?.toLowerCase() || '?'}` +
              (tgt.id    ? `#${tgt.id}`    : '') +
              (tgt.className && typeof tgt.className === 'string'
                  ? `.${tgt.className.trim().split(/\s+/).join('.')}`
                  : '') +
              '>'
            : '(kein Target)';

        console.debug(
            '%c[TRACE][USER] %c%s → %s',
            'color:#f472b6; font-weight:bold;', // pink
            'color:#94a3b8;',
            evt.type,
            tgtDesc,
        );
    }

    // Trace-Listener nur einmal registrieren (auf capture-Phase,
    // damit auch Events mit stopPropagation() erfasst werden)
    _TRACE_TYPES.forEach(type => {
        document.addEventListener(type, _globalEventTrace, { capture: true, passive: true });
    });

    // -----------------------------------------------------------------------
    // Initialisierungs-Log
    // -----------------------------------------------------------------------
    if (window.FORENSIC_DEBUG !== false) {
        console.debug(
            '%c[debug_events.js] Build 200 geladen.' +
            ' window._uevt() verfügbar.' +
            ' Trace-Modus: window.FORENSIC_EVENT_TRACE = true',
            'color:#6366f1; font-weight:bold;',
        );
        console.debug(
            '%c[debug_events.js] Kill-Switches:' +
            ' window.FORENSIC_DEBUG=false (alles)' +
            ' | window.FORENSIC_EVENT_DEBUG=false (nur Events)',
            'color:#6366f1;',
        );
    }

})();
