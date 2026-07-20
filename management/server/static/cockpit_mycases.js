// =============================================================================
// management/server/static/cockpit_mycases.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Meine Auftraege
// =============================================================================
// Zweck:
//   Rendert die persoenliche Sicht "Meine Auftraege" (/api/mycases) als
//   Tabulator-Tabelle der dem Ermittler aktuell zugewiesenen Faelle. Bewusst
//   eigenstaendig (keine Kopplung an cockpit_overview) und schlank.
//   Beleg: Bauplan B7 v1.1 §11; Build 363 (/api/mycases).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen ohne DOM; UMD-Ausgang ->
//   vitest testet den ECHTEN Code (daysSince/toRows rein; nur renderMyCases
//   beruehrt document/Tabulator).
//
// XSS: Nur textContent / Tabulator-plaintext (kein innerHTML).
//
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Version: v0.7.469 · Build: 469 · 2026-07-20
// =============================================================================

(function () {
    'use strict';

    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-MeineAuftraege]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    // daysSince: ganze Tage seit tsSec (Epoch-Sekunden). null wenn kein ts.
    function daysSince(tsSec, nowSec) {
        if (!tsSec) { return null; }
        var now = (typeof nowSec === 'number')
            ? nowSec : Math.floor(Date.now() / 1000);
        return Math.floor((now - tsSec) / 86400);
    }

    // toRows: /api/mycases.cases -> Tabellenzeilen (abgeleitete Felder ergaenzt).
    function toRows(data, nowSec) {
        return ((data && data.cases) || []).map(function (c) {
            return {
                subject_id: c.subject_id,
                username: c.username,
                status: c.status,
                priority: c.priority,
                ampel: c.ampel,
                event_count: c.event_count,
                has_note: c.has_note ? 'Notiz' : '',
                since_days: daysSince(c.last_activity_at, nowSec)
            };
        });
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    var _COLUMNS = [
        { title: 'Fall (subject_id)', field: 'subject_id' },
        { title: 'Benutzername', field: 'username', headerFilter: 'input' },
        { title: 'Status', field: 'status', headerFilter: 'input' },
        { title: 'Prio', field: 'priority' },
        { title: 'Ampel', field: 'ampel' },
        { title: 'Ereignisse', field: 'event_count' },
        { title: 'Notiz', field: 'has_note' },
        { title: 'Inaktiv (Tage)', field: 'since_days' }
    ];

    // renderMyCases: Kopf + Tabulator-Tabelle. opts.Tabulator injizierbar
    // (Default window.Tabulator); opts.nowSec fuer daysSince (Testbarkeit).
    // Rueckgabe: Tabulator-Instanz (oder null).
    function renderMyCases(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        mainEl.textContent = '';

        var cases = (data && data.cases) || [];

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Meine Auftraege';
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Mir aktuell zugewiesene Faelle (' + cases.length
            + ').';
        mainEl.appendChild(sub);

        var container = document.createElement('div');
        container.id = 'aiw-mycases-table';
        mainEl.appendChild(container);

        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        if (typeof Ctor !== 'function') {
            var note = document.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Tabellenbibliothek nicht verfuegbar.';
            container.appendChild(note);
            log('renderMyCases: kein Tabulator-Ctor');
            return null;
        }

        var rows = toRows(data, opts.nowSec);
        log('renderMyCases:', rows.length, 'Faelle');
        return new Ctor(container, {
            data: rows, columns: _COLUMNS,
            layout: 'fitColumns', height: '420px'
        });
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        daysSince: daysSince,
        toRows: toRows,
        renderMyCases: renderMyCases
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitMyCases = API; }
})();
