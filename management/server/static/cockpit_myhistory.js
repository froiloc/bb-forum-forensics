// =============================================================================
// management/server/static/cockpit_myhistory.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Meine Historie
// =============================================================================
// Zweck:
//   Rendert die persoenliche Sicht "Meine Historie" (/api/myhistory) als
//   Tabulator-Zeitleiste. Kombiniert (Build 363): eigene Aktionen + Historie
//   der eigenen Faelle; jeder Eintrag ist als 'ich' und/oder 'mein Fall'
//   markiert. Neueste zuerst (Backend liefert seq DESC).
//   Beleg: Bauplan B7 v1.1 §11; Build 363 (/api/myhistory).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen ohne DOM; UMD-Ausgang ->
//   vitest testet den ECHTEN Code (fmtTs/herkunftLabel/toRows rein; nur
//   renderMyHistory beruehrt document/Tabulator).
//
// XSS: Nur textContent / Tabulator-plaintext (kein innerHTML).
//
// Version: v0.7.364 · Build: 364 · 2026-07-10
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
        args.unshift('[AIW-MeineHistorie]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    // fmtTs: Epoch-Sekunden -> 'YYYY-MM-DD HH:MM:SS' (lokal). '' wenn kein ts.
    function fmtTs(tsSec) {
        if (!tsSec) { return ''; }
        var d = new Date(tsSec * 1000);
        function p(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
            + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':'
            + p(d.getSeconds());
    }

    // herkunftLabel: Markierung der Herkunft eines Eintrags.
    function herkunftLabel(e) {
        var mine = !!e.mine, mycase = !!e.mycase;
        if (mine && mycase) { return 'ich \u00b7 mein Fall'; }
        if (mine) { return 'ich'; }
        if (mycase) { return 'mein Fall'; }
        return '';
    }

    // targetLabel: 'case #18' bzw. '<typ> #<id>' / ''.
    function targetLabel(e) {
        if (!e.target_type) { return ''; }
        return e.target_type + ' #' + (e.target_id === null
            || e.target_id === undefined ? '' : e.target_id);
    }

    // toRows: /api/myhistory.events -> Tabellenzeilen.
    function toRows(data) {
        return ((data && data.events) || []).map(function (e) {
            return {
                seq: e.seq,
                zeit: fmtTs(e.ts),
                event_type: e.event_type,
                ziel: targetLabel(e),
                herkunft: herkunftLabel(e)
            };
        });
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    var _COLUMNS = [
        { title: 'Beleg (seq)', field: 'seq' },
        { title: 'Zeit', field: 'zeit' },
        { title: 'Ereignis', field: 'event_type', headerFilter: 'input' },
        { title: 'Ziel', field: 'ziel' },
        { title: 'Herkunft', field: 'herkunft', headerFilter: 'input' }
    ];

    // _tk / _mitHilfe (Build 549): Zugriff auf das gemeinsame Tabellen-Werkzeug
    // und die HILFE-ANKER der Spaltenkoepfe. LAZY, damit die Ladereihenfolge
    // diese Sicht nicht lautlos brechen kann. Die Spalten werden KOPIERT —
    // die Modulkonstante bleibt unberuehrt, sonst wuechse sie bei jedem Aufruf
    // einen weiteren Formatter an.
    function _tk() {
        return (typeof window !== 'undefined' && window.AIWTableKit)
            ? window.AIWTableKit : null;
    }
    function _mitHilfe(cols, sicht, doc) {
        var TK = _tk();
        if (!TK || !doc || !TK.titelMitHilfe) { return cols; }
        return cols.map(function (c) {
            var neu = {};
            Object.keys(c).forEach(function (k) { neu[k] = c[k]; });
            if (c.field && !c.titleFormatter) {
                neu.titleFormatter = TK.titelMitHilfe(
                    doc, c.title || c.field,
                    sicht + '.spalte.' + String(c.field).toLowerCase());
            }
            return neu;
        });
    }

    // renderMyHistory: Kopf + Tabulator-Zeitleiste. opts.Tabulator injizierbar.
    // Rueckgabe: Tabulator-Instanz (oder null).
    function renderMyHistory(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        mainEl.textContent = '';

        var events = (data && data.events) || [];
        var myCaseCount = (data && data.my_case_count) || 0;

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Meine Historie';
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Eigene Aktionen und Historie der eigenen Faelle ('
            + events.length + ' Eintraege, ' + myCaseCount + ' eigene Faelle).';
        mainEl.appendChild(sub);

        // Build 549 (UX): Aufbau ueber das gemeinsame Tabellen-Werkzeug.
        var doc = (typeof document !== 'undefined') ? document : null;
        var TK = _tk();
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        var rows = toRows(data);

        if (!TK || !doc) {
            var note = (doc || document).createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Gemeinsames Tabellen-Werkzeug nicht geladen — '
                + 'es liegen ' + rows.length + ' Einträge vor.';
            mainEl.appendChild(note);
            log('renderMyHistory: kein TableKit');
            return null;
        }

        log('renderMyHistory:', rows.length, 'Eintraege,', myCaseCount,
            'eigene Faelle');
        var auf = TK.tabelleAufbauen(doc, mainEl, {
            sicht: 'myhistory',
            rows: rows,
            columns: _mitHilfe(_COLUMNS, 'myhistory', doc),
            Ctor: Ctor,
            einheit: 'Einträge',
            tabulator: { height: '480px' }
        });
        return auf.table;
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        fmtTs: fmtTs,
        herkunftLabel: herkunftLabel,
        targetLabel: targetLabel,
        toRows: toRows,
        renderMyHistory: renderMyHistory
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitMyHistory = API; }
})();
