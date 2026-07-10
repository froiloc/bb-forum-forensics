// =============================================================================
// management/server/static/cockpit_overview.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Overview-Sicht
// =============================================================================
// Zweck:
//   Rendert die Fall-Uebersicht (/api/overview) als Tabulator-v6-Tabelle. Die
//   Sicht ist die Cockpit-Entsprechung des Ampel-Dashboards, aber mit client-
//   seitiger Sortierung/Filterung ueber Tabulator (Beleg: Bauplan B7 v1.1
//   §11.2 "Tabellen mit Tabulator.js").
//
// KONVENTIONS-VERTRAG (Quelle der Wahrheit = Backend):
//   Ampel-Vokabular (rot/gelb/gruen), ampel_reason-Codes und die Anzeige-
//   Sortierung (Ampel-Schwere -> Prioritaet aufsteigend -> letzte Aktivitaet
//   absteigend -> user_id) spiegeln dashboard_repo.AMPEL_* (Build 315) und
//   dashboard.js. Bewusst hier eigenstaendig + eigenstaendig getestet gehalten
//   (Split-Build 348, keine Kopplung an die getrennte Dashboard-Auslieferung);
//   der gemeinsame Vertrag ist das Backend-Vokabular, nicht diese Datei.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE-Wrapper mit 'use strict'.
//   2) DEV-Debug-Logging, per Flag abschaltbar (PROD: aus).
//   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
//   4) Logik gekapselt; REINE Funktionen fassen NIE das DOM an.
//   UMD-artiger Ausgang -> vitest testet den ECHTEN Code (keine Dublette).
//
// SICHERHEIT (XSS): Fallwerte (username/status/...) stammen aus Forumsdaten und
//   sind potenziell fremdbestimmt. Textspalten nutzen daher Tabulators
//   'plaintext'-Formatter (textContent). Eigene Formatter bauen DOM-Knoten und
//   setzen variablen Text ausschliesslich via textContent (nie innerHTML).
//
// Version: v0.7.349 · Build: 349 · 2026-07-10
// =============================================================================

(function () {
    'use strict';

    // Build 349: DEBUG zur Laufzeit auslesen (kein Reload noetig).
    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Overview]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '\u2014';

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM). vitest-getestet.
    // =========================================================================

    // Ampel-Rang: Schwere zuerst (rot 0 < gelb 1 < gruen 2). Unbekannt -> 99
    // (ans Ende), damit fehlerhafte Werte nie still verschwinden (Grundregel 1).
    var AMPEL_RANK = { rot: 0, gelb: 1, gruen: 2 };
    function ampelRank(ampel) {
        return Object.prototype.hasOwnProperty.call(AMPEL_RANK, ampel)
            ? AMPEL_RANK[ampel] : 99;
    }

    // ampel_reason-Code -> menschliches Label (Spiegel dashboard.js/Backend).
    var REASON_LABEL = {
        abgeschlossen: 'abgeschlossen',
        freigegeben: 'freigegeben',
        offen_nicht_zugewiesen: 'offen, nicht zugewiesen',
        inaktiv_lang: 'lange inaktiv',
        inaktiv_mittel: 'mittlere Inaktivitaet',
        aktiv: 'aktiv'
    };
    function reasonLabel(code) {
        return REASON_LABEL[code] || code || '';
    }

    // Zuweisung: Anzeigename bevorzugt, sonst system_username, sonst Gedankenstrich.
    function assigneeLabel(c) {
        return c.assigned_display_name
            || c.assigned_system_username
            || EM_DASH;
    }

    // Support-Abzeichen-Text (Praesenz, kein Fall-Zustand).
    function supportLabel(c) {
        return c.support_active
            ? ('Support aktiv (' + (c.support_count || 0) + ')')
            : '';
    }

    // Tage seit Unix-Zeitstempel (nowSec injizierbar); null bei fehlend/0.
    function daysSince(tsSec, nowSec) {
        if (!tsSec) { return null; }
        var now = (typeof nowSec === 'number')
            ? nowSec : Math.floor(Date.now() / 1000);
        return Math.floor((now - tsSec) / 86400);
    }

    // toRows: DTO-Faelle -> Tabulator-Zeilen. Ergaenzt abgeleitete Felder
    // (_rank/_reason/_assignee/_sinceDays/_support), laesst die Rohwerte drin.
    // Reine Abbildung; mutiert die Eingabe nicht.
    function toRows(cases, nowSec) {
        return (cases || []).map(function (c) {
            return {
                user_id: c.user_id,
                username: c.username,
                status: c.status,
                priority: c.priority,
                ampel: c.ampel,
                has_note: !!c.has_note,
                event_count: c.event_count,
                last_activity_at: c.last_activity_at,
                // abgeleitet:
                _rank: ampelRank(c.ampel),
                _reason: reasonLabel(c.ampel_reason),
                _assignee: assigneeLabel(c),
                _sinceDays: daysSince(c.last_activity_at, nowSec),
                _support: supportLabel(c)
            };
        });
    }

    // sortRows: Standard-Anzeigeordnung (Ampel-Schwere -> Prioritaet aufsteigend
    // -> letzte Aktivitaet absteigend -> user_id). Gibt eine sortierte KOPIE
    // zurueck (mutiert die Eingabe nicht). Tabulator laesst spaeter Umsortieren zu.
    function sortRows(rows) {
        var copy = (rows || []).slice();
        copy.sort(function (a, b) {
            if (a._rank !== b._rank) { return a._rank - b._rank; }
            if (a.priority !== b.priority) { return a.priority - b.priority; }
            var la = a.last_activity_at || 0, lb = b.last_activity_at || 0;
            if (la !== lb) { return lb - la; }
            return (a.user_id || 0) - (b.user_id || 0);
        });
        return copy;
    }

    // columnDefs: Tabulator-Spaltenspezifikation (deterministisch/rein). Die
    // Formatter bauen DOM-Knoten (XSS-sicher); Textspalten nutzen 'plaintext'.
    function columnDefs() {
        return [
            {
                title: 'Ampel', field: '_rank', sorter: 'number', width: 190,
                // Farbpunkt + Grund; Grund stammt aus der Whitelist (safe).
                formatter: function (cell) {
                    var data = cell.getRow().getData();
                    var wrap = document.createElement('span');
                    var dot = document.createElement('span');
                    dot.className = 'dot ' + (data.ampel || '');
                    wrap.appendChild(dot);
                    var txt = document.createElement('span');
                    txt.textContent = ' ' + (data._reason || '');
                    wrap.appendChild(txt);
                    return wrap;
                }
            },
            { title: 'Prio', field: 'priority', sorter: 'number', hozAlign: 'right', width: 70 },
            { title: 'User-ID', field: 'user_id', sorter: 'number', hozAlign: 'right', width: 90 },
            { title: 'Benutzer', field: 'username', formatter: 'plaintext' },
            { title: 'Status', field: 'status', formatter: 'plaintext', width: 110 },
            { title: 'Zugewiesen', field: '_assignee', formatter: 'plaintext' },
            {
                title: 'Letzte Aktivitaet', field: '_sinceDays', sorter: 'number',
                hozAlign: 'right', width: 140,
                formatter: function (cell) {
                    var v = cell.getValue();
                    var span = document.createElement('span');
                    span.textContent = (v === null || v === undefined)
                        ? EM_DASH : (v + ' Tg');
                    return span;
                }
            },
            { title: 'Ereignisse', field: 'event_count', sorter: 'number', hozAlign: 'right', width: 100 },
            {
                title: 'Notiz', field: 'has_note', width: 80,
                formatter: function (cell) {
                    var span = document.createElement('span');
                    span.textContent = cell.getValue() ? 'Notiz' : '';
                    return span;
                }
            },
            { title: 'Support', field: '_support', formatter: 'plaintext', width: 150 }
        ];
    }

    // scopeText: Umfang-Banner ('alle'/'eigene') als Klartext.
    function scopeText(scope) {
        if (scope === 'eigene') {
            return 'Umfang: nur eigene Zuweisungen (fremde Faelle gekapselt).';
        }
        if (scope === 'alle') {
            return 'Umfang: alle Faelle (Gesamtsicht).';
        }
        return 'Umfang: eingeschraenkt.';
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    // renderOverview: baut Kopf + Tabulator-Tabelle in mainEl. data = Antwort
    // von /api/overview ({scope, count, cases}). opts.Tabulator injizierbar
    // (Default window.Tabulator); opts.nowSec fuer daysSince (Testbarkeit).
    // Rueckgabe: Tabulator-Instanz (oder null, wenn Tabulator fehlt) — der
    // Aufrufer zerstoert sie beim Sichtwechsel/Reload.
    function renderOverview(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        mainEl.textContent = '';

        var scope = data ? data.scope : null;
        var cases = (data && data.cases) || [];

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Fall-Uebersicht';
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = scopeText(scope) + ' (' + cases.length + ' Faelle)';
        mainEl.appendChild(sub);

        var container = document.createElement('div');
        container.id = 'aiw-overview-table';
        mainEl.appendChild(container);

        var rows = sortRows(toRows(cases, opts.nowSec));
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        if (typeof Ctor !== 'function') {
            var note = document.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Tabellenbibliothek nicht verfuegbar.';
            container.appendChild(note);
            log('renderOverview: kein Tabulator-Ctor');
            return null;
        }

        log('renderOverview:', rows.length, 'Zeilen, scope', scope);
        return new Ctor(container, {
            data: rows,
            columns: columnDefs(),
            layout: 'fitColumns',
            height: '65vh',
            placeholder: 'Keine Faelle im Umfang.',
            rowFormatter: function (row) {
                // Ampel-Zeilenklasse (dezente Faerbung, konsistent zum Dashboard).
                var d = row.getData();
                row.getElement().classList.add('aiw-row-' + (d.ampel || 'none'));
            }
        });
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        AMPEL_RANK: AMPEL_RANK,
        ampelRank: ampelRank,
        reasonLabel: reasonLabel,
        assigneeLabel: assigneeLabel,
        supportLabel: supportLabel,
        daysSince: daysSince,
        toRows: toRows,
        sortRows: sortRows,
        columnDefs: columnDefs,
        scopeText: scopeText,
        renderOverview: renderOverview
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitOverview = API; }
})();
