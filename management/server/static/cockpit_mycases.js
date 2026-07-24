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
//   Build 500 (Fallstart aus dem Portal): Jede Zeile erhaelt eine Aktionsflaeche
//   "Fall starten". Ein Klick ruft opts.onLaunch(subject_id) auf; cockpit.js
//   sendet das per POST /api/case/launch an den Management-Server, der den
//   FORENSIK-Server (main.py) fuer genau diesen Fall startet. Eine Rueckmeldung
//   (Erfolg/Fehler) wird als Banner ueber der Tabelle angezeigt (opts.pendingMsg).
//   Beleg: Projektgespraech 2026-07-22; Bauplan Build 500.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen ohne DOM; UMD-Ausgang ->
//   vitest testet den ECHTEN Code (daysSince/toRows/columnsFor rein; render +
//   actionColumn-Formatter beruehren document/Tabulator).
//
// XSS: Nur textContent / createElement / Tabulator-plaintext (kein innerHTML).
//   Die Aktionsspalte liefert ein echtes <button>-DOM-Element (kein HTML-String).
//
// Build 500: Aktionsspalte "Fall starten" + Rueckmeldebanner (onLaunch/pendingMsg)
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Version: v0.8.500 · Build: 500 · 2026-07-22
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

    // Basisspalten (reine Lesesicht). Die Aktionsspalte wird nur ergaenzt, wenn
    // ein onLaunch-Callback vorliegt (siehe columnsFor()).
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

    // actionColumn: baut die Tabulator-Spalte mit dem "Fall starten"-Knopf.
    // Der Formatter liefert ein echtes <button>-Element (kein innerHTML) und
    // schliesst ueber onLaunch — beim Klick wird onLaunch(subject_id) gerufen.
    // Der Knopf deaktiviert sich beim Klick selbst (Doppelklick-Schutz); der
    // anschliessende Reload der Sicht (cockpit.js) stellt den Ausgangszustand
    // wieder her. Beleg: Bauplan Build 500 §3.
    function actionColumn(onLaunch) {
        return {
            title: 'Aktion',
            field: 'subject_id',       // Wert = subject_id, dient dem Formatter
            headerSort: false,
            hozAlign: 'center',
            width: 140,
            formatter: function (cell) {
                var doc = (typeof document !== 'undefined') ? document : null;
                var sid = (cell && typeof cell.getValue === 'function')
                    ? cell.getValue() : null;
                if (!doc) { return String(sid); }

                var btn = doc.createElement('button');
                btn.type = 'button';
                btn.className = 'aiw-mycases-btn';
                btn.textContent = 'Fall starten';
                btn.setAttribute('data-subject-id', String(sid));
                btn.addEventListener('click', function (ev) {
                    // Zellenklick nicht weiterreichen (kein Zeilen-Select o.ae.).
                    if (ev && typeof ev.stopPropagation === 'function') {
                        ev.stopPropagation();
                    }
                    btn.disabled = true;
                    btn.textContent = 'Startet…';
                    log('onLaunch fuer subject_id=', sid);
                    if (typeof onLaunch === 'function') { onLaunch(sid); }
                });
                return btn;
            }
        };
    }

    // columnsFor: Basisspalten, optional um die Aktionsspalte erweitert.
    function columnsFor(onLaunch) {
        if (typeof onLaunch !== 'function') { return _COLUMNS.slice(); }
        return _COLUMNS.concat([actionColumn(onLaunch)]);
    }

    // renderBanner: haengt (falls vorhanden) eine Rueckmeldung ueber die Tabelle.
    // msg = { text: string, error: boolean } oder null/undefined -> nichts.
    // Reines textContent (kein innerHTML) -> XSS-fest.
    function renderBanner(mainEl, msg) {
        if (!msg || !msg.text) { return; }
        var div = document.createElement('div');
        div.className = 'aiw-mycases-banner '
            + (msg.error ? 'is-error' : 'is-ok');
        div.setAttribute('role', 'status');
        div.textContent = msg.text;
        mainEl.appendChild(div);
    }

    // renderMyCases: Kopf + optionales Banner + Tabulator-Tabelle.
    //   opts.Tabulator  — Tabulator-Ctor (Default window.Tabulator; Test-Stub).
    //   opts.nowSec     — fuer daysSince (Testbarkeit).
    //   opts.onLaunch   — Callback(subject_id) fuer den "Fall starten"-Knopf.
    //                     Fehlt er, entfaellt die Aktionsspalte (reine Lesesicht).
    //   opts.pendingMsg — {text, error} Rueckmeldung nach einem Startversuch.
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

        // Rueckmeldung eines vorangegangenen Startversuchs (Build 500).
        renderBanner(mainEl, opts.pendingMsg);

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
        log('renderMyCases:', rows.length, 'Faelle',
            (typeof opts.onLaunch === 'function') ? '(mit Start)' : '(nur Lesen)');
        return new Ctor(container, {
            data: rows,
            columns: columnsFor(opts.onLaunch),
            layout: 'fitColumns', height: '420px'
        });
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        daysSince: daysSince,
        toRows: toRows,
        columnsFor: columnsFor,
        actionColumn: actionColumn,
        renderMyCases: renderMyCases
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitMyCases = API; }
})();
