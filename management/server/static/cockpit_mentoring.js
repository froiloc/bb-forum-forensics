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
        // Build 603 (Baustelle H / H12): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'mentoring.titel');
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = sessions.length + ' laufende Support-Sitzung(en), '
            + stale + ' betreuungsbeduerftig (stale). '
            + 'Aktualisiert automatisch.';
        sub.setAttribute('data-hilfe-id', 'mentoring.kennzeile');
        mainEl.appendChild(sub);

        log('renderMentoring:', sessions.length, 'laufend,', stale, 'stale');
        // Build 549 (UX): Aufbau ueber das gemeinsame Tabellen-Werkzeug.
        // Der eigene rowFormatter bleibt — er wird DURCHGEREICHT, nicht
        // ersetzt.
        //
        // Der frueher hier stehende EIGENE Ersatzpfad ('Tabellenbibliothek
        // nicht verfuegbar.') ist entfallen: er nannte die Zahl der Sitzungen
        // NICHT und war damit genau die leere Flaeche, die wie 'es laeuft
        // nichts' aussieht. Jetzt gibt es einen Ersatzpfad, und er zaehlt.
        var TK = _tk();
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        var rows = toRows(data);
        if (!TK) {
            var note = doc.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Gemeinsames Tabellen-Werkzeug nicht geladen — '
                + 'es laufen ' + rows.length + ' Sitzungen.';
            mainEl.appendChild(note);
            log('renderMentoring: kein TableKit');
            return null;
        }
        var auf = TK.tabelleAufbauen(doc, mainEl, {
            sicht: 'mentoring',
            rows: rows,
            columns: _mitHilfe(_COLUMNS, 'mentoring', doc),
            Ctor: Ctor,
            einheit: 'Sitzungen',
            tabulator: {
                height: '440px',
                // Stale-Zeilen (Betreuungsbedarf) dezent hervorheben.
                rowFormatter: function (row) {
                    var d = row.getData();
                    if (d && !d._live) {
                        try { row.getElement().style.background = COL_STALE_BG; }
                        catch (e) { /* jsdom/Stub ohne getElement */ }
                    }
                }
            }
        });
        return auf.table;
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
