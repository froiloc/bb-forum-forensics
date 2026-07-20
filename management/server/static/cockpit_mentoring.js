// =============================================================================
// management/server/static/cockpit_mentoring.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Ermittler-Betreuung
// =============================================================================
// Zweck:
//   Rendert die LIVE-Sicht "Ermittler-Betreuung" (/api/mentoring): die aktuell
//   laufenden Support-Sitzungen mit Live/Stale-Ampel (Heartbeat-Alter vs.
//   stale_sec) und Laufzeit. Betreuungsbeduerftige (stale) Sitzungen werden
//   hervorgehoben. Das periodische Neuladen erledigt cockpit.js (Heartbeats
//   sind bewusst nicht auditiert -> SSE allein genuegt fuer die Live-Sicht
//   nicht). Beleg: Ideen §2.12; Build 368 (/api/mentoring).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen ohne DOM; UMD-Ausgang ->
//   vitest testet den ECHTEN Code (fmtDuration/supporterLabel/toRows rein; nur
//   renderMentoring beruehrt document/Tabulator).
//
// XSS: nur textContent / Tabulator-plaintext (kein innerHTML).
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
        args.unshift('[AIW-Betreuung]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var COL_STALE_BG = '#fdecea';   // dezente Hervorhebung stale-Zeilen

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    // fmtDuration: Sekunden -> kompakte Dauer ('2h 5m' / '3m 12s' / '9s').
    function fmtDuration(sec) {
        sec = Math.max(0, Math.floor(sec || 0));
        var h = Math.floor(sec / 3600);
        var m = Math.floor((sec % 3600) / 60);
        var s = sec % 60;
        if (h > 0) { return h + 'h ' + m + 'm'; }
        if (m > 0) { return m + 'm ' + s + 's'; }
        return s + 's';
    }

    function supporterLabel(s) {
        if (s.supporter_display_name) { return s.supporter_display_name; }
        if (s.supporter_system_username) { return s.supporter_system_username; }
        if (s.supporter_id) { return '#' + s.supporter_id; }
        return 'herrenlos';
    }

    function statusLabel(s) {
        return s.live ? 'live' : 'stale (Betreuung!)';
    }

    // toRows: /api/mentoring.sessions -> Tabellenzeilen. _live steuert die
    // Zeilen-Hervorhebung im rowFormatter.
    function toRows(data) {
        return ((data && data.sessions) || []).map(function (s) {
            return {
                id: s.id,
                subject_id: s.subject_id,
                username: s.username,
                supporter: supporterLabel(s),
                laufzeit: fmtDuration(s.started_ago_sec),
                heartbeat: fmtDuration(s.heartbeat_age_sec) + ' her',
                status: statusLabel(s),
                _live: !!s.live
            };
        });
    }

    function staleCount(data) {
        return ((data && data.sessions) || []).filter(function (s) {
            return !s.live;
        }).length;
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    var _COLUMNS = [
        { title: 'Sitzung', field: 'id' },
        { title: 'Fall', field: 'subject_id' },
        { title: 'Benutzername', field: 'username', headerFilter: 'input' },
        { title: 'Supporter', field: 'supporter', headerFilter: 'input' },
        { title: 'Laufzeit', field: 'laufzeit' },
        { title: 'Letzter Heartbeat', field: 'heartbeat' },
        { title: 'Status', field: 'status' }
    ];

    // renderMentoring: Kopf + Tabulator (stale-Zeilen hervorgehoben). Rueckgabe:
    // Tabulator-Instanz (oder null).
    function renderMentoring(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = mainEl.ownerDocument || document;
        mainEl.textContent = '';

        var sessions = (data && data.sessions) || [];
        var stale = staleCount(data);

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Ermittler-Betreuung';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = sessions.length + ' laufende Support-Sitzung(en), '
            + stale + ' betreuungsbeduerftig (stale). '
            + 'Aktualisiert automatisch.';
        mainEl.appendChild(sub);

        var container = doc.createElement('div');
        container.id = 'aiw-mentoring-table';
        mainEl.appendChild(container);

        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        if (typeof Ctor !== 'function') {
            var note = doc.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Tabellenbibliothek nicht verfuegbar.';
            container.appendChild(note);
            log('renderMentoring: kein Tabulator-Ctor');
            return null;
        }

        log('renderMentoring:', sessions.length, 'laufend,', stale, 'stale');
        return new Ctor(container, {
            data: toRows(data), columns: _COLUMNS,
            layout: 'fitColumns', height: '440px',
            // Stale-Zeilen (Betreuungsbedarf) dezent hervorheben.
            rowFormatter: function (row) {
                var d = row.getData();
                if (d && !d._live) {
                    try { row.getElement().style.background = COL_STALE_BG; }
                    catch (e) { /* jsdom/Stub ohne getElement */ }
                }
            }
        });
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        fmtDuration: fmtDuration,
        supporterLabel: supporterLabel,
        statusLabel: statusLabel,
        toRows: toRows,
        staleCount: staleCount,
        renderMentoring: renderMentoring
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitMentoring = API; }
})();
