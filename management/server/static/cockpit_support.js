// =============================================================================
// management/server/static/cockpit_support.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Support-Historie
// =============================================================================
// Zweck:
//   Rendert die Support-Historie (/api/support) im Cockpit. Jede Sitzung ist
//   belegbasiert rekonstruiert und traegt die Marker mine_as_supporter /
//   on_my_case (Build 366). Darstellung als bis zu DREI getrennte Tabulator-
//   Listen (nicht ueberlappend):
//     - "Meine Sitzungen"      : mine_as_supporter
//     - "An meinen Faellen"    : on_my_case UND NICHT mine_as_supporter
//     - "Weitere Sitzungen"    : keins von beidem (nur bei scope 'alle')
//   Nur nicht-leere Abschnitte werden gezeigt. Ein Klick auf eine Zeile oeffnet
//   ein MINI-MODAL mit dem vollstaendigen Datensatz (schoene Feld-Darstellung
//   statt eindimensionalem String).
//   Beleg: Bauplan B7 v1.1 §11; Build 366 (/api/support).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen ohne DOM; UMD-Ausgang ->
//   vitest testet den ECHTEN Code (fmtTs/bucketize/detailPairs/decorate rein;
//   buildDetailNode/createModalRoot/showDetail arbeiten auf einem uebergebenen
//   document -> in jsdom testbar).
//
// XSS: ausschliesslich textContent / Tabulator-plaintext (kein innerHTML).
//
// Version: v0.7.367 · Build: 367 · 2026-07-10
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
        args.unshift('[AIW-Support]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    function fmtTs(tsSec) {
        if (!tsSec) { return ''; }
        var d = new Date(tsSec * 1000);
        function p(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
            + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':'
            + p(d.getSeconds());
    }

    function supporterLabel(rec) {
        if (rec.supporter_display_name) { return rec.supporter_display_name; }
        if (rec.supporter_system_username) {
            return rec.supporter_system_username;
        }
        if (rec.supporter_id) { return '#' + rec.supporter_id; }
        return 'herrenlos';
    }

    function markLabel(rec) {
        var mine = !!rec.mine_as_supporter, oncase = !!rec.on_my_case;
        if (mine && oncase) { return 'meine Sitzung \u00b7 mein Fall'; }
        if (mine) { return 'meine Sitzung'; }
        if (oncase) { return 'an meinem Fall'; }
        return '\u2014';
    }

    // bucketize: nicht-ueberlappende Aufteilung. mine hat Vorrang; "an meinen
    // Faellen" meint bewusst Support DURCH ANDERE an meinen Faellen.
    function bucketize(data) {
        var mine = [], oncase = [], weitere = [];
        ((data && data.sessions) || []).forEach(function (s) {
            if (s.mine_as_supporter) { mine.push(s); }
            else if (s.on_my_case) { oncase.push(s); }
            else { weitere.push(s); }
        });
        return { mine: mine, oncase: oncase, weitere: weitere };
    }

    // decorate: fuegt Anzeige-Hilfsfelder hinzu, OHNE den vollen Record zu
    // verlieren (das Modal braucht alle Felder).
    function decorate(session) {
        var c = {};
        for (var k in session) {
            if (Object.prototype.hasOwnProperty.call(session, k)) {
                c[k] = session[k];
            }
        }
        c._supporter = supporterLabel(session);
        c._started = fmtTs(session.started_at);
        c._ended = fmtTs(session.ended_at);
        return c;
    }

    // detailPairs: [Label, Wert]-Paare fuer das Modal (formatiert).
    function detailPairs(rec) {
        function or(v) {
            return (v === null || v === undefined || v === '') ? '\u2014' : v;
        }
        return [
            ['Sitzung (session_id)', or(rec.session_id)],
            ['Fall (user_id)', or(rec.user_id)],
            ['Benutzername', or(rec.username)],
            ['Supporter', supporterLabel(rec)],
            ['Start', or(fmtTs(rec.started_at))],
            ['Ende', or(fmtTs(rec.ended_at))],
            ['Dauer (Sek.)', or(rec.duration_sec)],
            ['Status', or(rec.status)],
            ['Grund', or(rec.reason)],
            ['Anomalie', or(rec.anomaly)],
            ['Beleg Start (seq)', or(rec.started_seq)],
            ['Beleg Ende (seq)', or(rec.ended_seq)],
            ['Markierung', markLabel(rec)]
        ];
    }

    // =========================================================================
    // 2) DOM/RENDER (Browser/jsdom; document wird uebergeben, wo moeglich).
    // =========================================================================

    var _COLUMNS = [
        { title: 'Sitzung', field: 'session_id' },
        { title: 'Fall', field: 'user_id' },
        { title: 'Benutzername', field: 'username', headerFilter: 'input' },
        { title: 'Supporter', field: '_supporter', headerFilter: 'input' },
        { title: 'Start', field: '_started' },
        { title: 'Ende', field: '_ended' },
        { title: 'Status', field: 'status', headerFilter: 'input' }
    ];

    // buildDetailNode: erzeugt eine Definitionsliste (dl) aus detailPairs.
    function buildDetailNode(doc, rec) {
        var dl = doc.createElement('dl');
        dl.className = 'aiw-detail-dl';
        detailPairs(rec).forEach(function (pair) {
            var dt = doc.createElement('dt');
            dt.textContent = pair[0];
            var dd = doc.createElement('dd');
            dd.textContent = String(pair[1]);
            dl.appendChild(dt);
            dl.appendChild(dd);
        });
        return dl;
    }

    // createModalRoot: versteckte Overlay-Struktur. Layout via Inline-Styles
    // (keine CSS-Abhaengigkeit); schliesst per Overlay-Klick, Schliessen-Button
    // und Escape.
    function createModalRoot(doc) {
        var overlay = doc.createElement('div');
        overlay.className = 'aiw-modal';
        overlay.style.cssText = 'position:fixed;inset:0;display:none;'
            + 'align-items:center;justify-content:center;'
            + 'background:rgba(0,0,0,0.45);z-index:1000;';
        var box = doc.createElement('div');
        box.className = 'aiw-modal-box';
        box.style.cssText = 'background:#fff;color:#1b2733;max-width:560px;'
            + 'width:90%;max-height:80vh;overflow:auto;border-radius:8px;'
            + 'padding:18px 20px;box-shadow:0 10px 40px rgba(0,0,0,0.35);';
        var head = doc.createElement('div');
        head.style.cssText = 'display:flex;justify-content:space-between;'
            + 'align-items:center;margin-bottom:8px;';
        var title = doc.createElement('h3');
        title.className = 'aiw-modal-title';
        title.textContent = 'Sitzungs-Details';
        title.style.margin = '0';
        var close = doc.createElement('button');
        close.type = 'button';
        close.className = 'aiw-modal-close';
        close.textContent = 'Schliessen';
        head.appendChild(title);
        head.appendChild(close);
        var body = doc.createElement('div');
        body.className = 'aiw-modal-body';
        box.appendChild(head);
        box.appendChild(body);
        overlay.appendChild(box);

        function hide() { hideDetail(overlay); }
        close.addEventListener('click', hide);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) { hide(); }  // nur Overlay, nicht Box
        });
        doc.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') { hide(); }
        });
        return overlay;
    }

    function showDetail(modalRoot, doc, rec) {
        var body = modalRoot.querySelector('.aiw-modal-body');
        body.textContent = '';
        body.appendChild(buildDetailNode(doc, rec));
        modalRoot.style.display = 'flex';
    }
    function hideDetail(modalRoot) {
        modalRoot.style.display = 'none';
    }

    function _sectionTable(mainEl, doc, titleText, list, Ctor, modalRoot) {
        if (!list.length) { return null; }
        var h = doc.createElement('h3');
        h.className = 'aiw-subhead';
        h.textContent = titleText + ' (' + list.length + ')';
        mainEl.appendChild(h);
        var container = doc.createElement('div');
        mainEl.appendChild(container);
        return new Ctor(container, {
            data: list.map(decorate), columns: _COLUMNS,
            layout: 'fitColumns', height: '260px',
            rowClick: function (e, row) {
                showDetail(modalRoot, doc, row.getData());
            }
        });
    }

    // renderSupport: Kopf + bis zu drei Abschnitts-Tabellen + Modal. Rueckgabe:
    // Array der Tabulator-Instanzen (fuer den Abbau in cleanupView).
    function renderSupport(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return []; }
        var doc = mainEl.ownerDocument || document;
        mainEl.textContent = '';

        var scope = data ? data.scope : null;
        var buckets = bucketize(data);

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Support-Historie';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = (scope === 'alle'
            ? 'Alle Support-Sitzungen.'
            : 'Eigene Support-Sitzungen und Support an eigenen Faellen.')
            + ' Zeile anklicken fuer Details.';
        mainEl.appendChild(sub);

        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        if (typeof Ctor !== 'function') {
            var note = doc.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Tabellenbibliothek nicht verfuegbar.';
            mainEl.appendChild(note);
            log('renderSupport: kein Tabulator-Ctor');
            return [];
        }

        var modalRoot = createModalRoot(doc);
        mainEl.appendChild(modalRoot);

        var tables = [];
        [['Meine Sitzungen', buckets.mine],
         ['An meinen Faellen', buckets.oncase],
         ['Weitere Sitzungen', buckets.weitere]].forEach(function (sec) {
            var t = _sectionTable(mainEl, doc, sec[0], sec[1], Ctor, modalRoot);
            if (t) { tables.push(t); }
        });

        log('renderSupport:', buckets.mine.length, 'eigene,',
            buckets.oncase.length, 'an Faellen,', buckets.weitere.length,
            'weitere; scope', scope);
        return tables;
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        fmtTs: fmtTs,
        supporterLabel: supporterLabel,
        markLabel: markLabel,
        bucketize: bucketize,
        decorate: decorate,
        detailPairs: detailPairs,
        buildDetailNode: buildDetailNode,
        createModalRoot: createModalRoot,
        showDetail: showDetail,
        hideDetail: hideDetail,
        renderSupport: renderSupport
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitSupport = API; }
})();
