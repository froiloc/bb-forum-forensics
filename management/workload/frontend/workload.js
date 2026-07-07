// =============================================================================
// management/workload/frontend/workload.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Lastverteilung (Frontend)
// =============================================================================
// Zweck:
//   Render-Schicht der Ermittler-Lastverteilung (getrennte Admin-Oberflaeche
//   fuer die Chef-Ermittlerin). Nimmt die InvestigatorLoad-DTOs (Backend,
//   Build 335) als JSON-Array entgegen und rendert je Ermittler eine Last-Zeile
//   (Fallzahl nach Ampel/Status, Aktivitaets-Beleg) plus die Rueckstau-Zeile
//   (unzugewiesene Faelle) als Verteilungs-Pool.
//
// KAPSELUNG / KONVENTIONEN (Projekt-Gebote fuer JS):
//   1) IIFE-Wrapper mit 'use strict'. 2) Exzessives DEV-Debug-Logging, per Flag
//   abschaltbar. 3) Ausfuehrliche Kommentare. 4) Logik gekapselt. Zusaetzlich:
//   REINE Funktionen ueber UMD-Ausgang exportiert -> Vitest testet den ECHTEN
//   Code (keine 'gruen-aber-tot'-Falle). Reine Funktionen fassen NIE das DOM an.
//
// BESONDERHEIT: Die Rueckstau-Zeile (is_backlog) ist KEIN Ermittler-Rang; sie
//   wird beim Sortieren NICHT mit einsortiert, sondern bleibt IMMER ans Ende
//   angepinnt (der Pool steht unter den Traegern).
//
// SICHERHEIT: Alle Zellinhalte via textContent (Anzeigenamen sind beliebiger
//   Text) — nie innerHTML.
//
// Version: v0.7.335 · Build: 335 · 2026-07-07
// =============================================================================

(function () {
    'use strict';

    var DEBUG = (typeof window !== 'undefined' && window.AIW_WORKLOAD_DEBUG === true);
    function log() {
        if (!DEBUG) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Workload]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Anzeigename (Anzeigename bevorzugt, sonst System-Benutzer,
    // sonst der Backend-gesetzte Rueckstau-Text im system_username).
    // -------------------------------------------------------------------------
    function nameLabel(rec) {
        if (rec.is_backlog) { return rec.system_username || '(nicht zugewiesen)'; }
        return rec.display_name || rec.system_username || '(unbekannt)';
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Rollen-Kuerzel 'E/C/S' (Ermittler/Chef/Support). Beim
    // Rueckstau bewusst leer (kein Traeger).
    // -------------------------------------------------------------------------
    function roleLabel(rec) {
        if (rec.is_backlog) { return '\u2014'; }
        var parts = [];
        if (rec.is_investigator) { parts.push('E'); }
        if (rec.is_supervisor) { parts.push('C'); }
        if (rec.is_support) { parts.push('S'); }
        return parts.length ? parts.join('/') : '\u2014';
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Unix-Sekunden -> 'YYYY-MM-DD HH:MMZ' (UTC). null -> '—'.
    // -------------------------------------------------------------------------
    function formatTs(sec) {
        if (sec === null || sec === undefined) { return '\u2014'; }
        var d = new Date(sec * 1000);
        function pad(n) { return (n < 10 ? '0' : '') + n; }
        return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-'
            + pad(d.getUTCDate()) + ' ' + pad(d.getUTCHours()) + ':'
            + pad(d.getUTCMinutes()) + 'Z';
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Aktivitaets-Kurztext (Anzahl auditierter Aktionen). Beim
    // Rueckstau '—' (kein Akteur).
    // -------------------------------------------------------------------------
    function activityLabel(rec) {
        if (rec.is_backlog) { return '\u2014'; }
        return String(rec.audit_action_count || 0);
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Balken-Segmente (rot/gelb/gruen) als Prozentbreiten der
    // Gesamtzahl. Liefert IMMER drei Segmente (0%-Segmente werden beim Rendern
    // uebersprungen). Kein Runden auf 100% erzwungen (ehrliche Anteile).
    // -------------------------------------------------------------------------
    function barSegments(rec) {
        var total = rec.total_cases || 0;
        function pct(n) { return total > 0 ? (100 * (n || 0) / total) : 0; }
        return [
            { cls: 'aiw-seg-rot', pct: pct(rec.ampel_rot) },
            { cls: 'aiw-seg-gelb', pct: pct(rec.ampel_gelb) },
            { cls: 'aiw-seg-gruen', pct: pct(rec.ampel_gruen) }
        ];
    }

    // -------------------------------------------------------------------------
    // Sortierschluessel je Spalte. Text-Schluessel case-insensitiv.
    // -------------------------------------------------------------------------
    var SORT_KEYS = {
        name: function (r) { return nameLabel(r).toLowerCase(); },
        total: function (r) { return r.total_cases || 0; },
        rot: function (r) { return r.ampel_rot || 0; },
        gelb: function (r) { return r.ampel_gelb || 0; },
        gruen: function (r) { return r.ampel_gruen || 0; },
        aktiv: function (r) { return r.active_cases || 0; },
        fertig: function (r) { return r.done_cases || 0; },
        aktionen: function (r) { return r.audit_action_count || 0; },
        letzte: function (r) { return r.last_action_at || 0; }
    };

    // -------------------------------------------------------------------------
    // REINE FUNKTION: sortiert NUR die Ermittler-Zeilen; die Rueckstau-Zeile(n)
    // (is_backlog) werden herausgeloest und IMMER ans Ende angehaengt. default
    // key 'rot' desc (Dringlichkeit zuerst), sonst wie uebergeben. Tiebreak:
    // Name aufsteigend. Mutiert die Eingabe NICHT.
    // -------------------------------------------------------------------------
    function sortRecords(records, key, dir) {
        var all = (records || []).slice();
        var backlog = all.filter(function (r) { return r.is_backlog; });
        var people = all.filter(function (r) { return !r.is_backlog; });
        var extractor = SORT_KEYS[key] || SORT_KEYS.rot;
        // Vorgabe: bei 'rot' absteigend (dringlichste Last oben).
        var effDir = dir || ((key === undefined || key === 'rot') ? 'desc' : 'asc');
        var sign = (effDir === 'desc') ? -1 : 1;
        people.sort(function (a, b) {
            var ka = extractor(a), kb = extractor(b);
            if (ka < kb) { return -1 * sign; }
            if (ka > kb) { return 1 * sign; }
            var na = nameLabel(a).toLowerCase(), nb = nameLabel(b).toLowerCase();
            return na < nb ? -1 : (na > nb ? 1 : 0);
        });
        return people.concat(backlog);
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Filter (Teilstring, case-insensitiv) ueber Name/System-
    // Benutzer. Leerer Filter -> alle. Mutiert nichts.
    // -------------------------------------------------------------------------
    function filterRecords(records, query) {
        var q = (query || '').trim().toLowerCase();
        if (!q) { return (records || []).slice(); }
        return (records || []).filter(function (r) {
            var hay = [nameLabel(r), (r.system_username || '')]
                .join(' \u0001 ').toLowerCase();
            return hay.indexOf(q) !== -1;
        });
    }

    var COLUMNS = [
        { name: 'Ermittler', key: 'name' },
        { name: 'Rollen', key: null },
        { name: 'Faelle', key: 'total' },
        { name: 'Last (rot/gelb/gruen)', key: 'rot' },
        { name: 'Aktiv', key: 'aktiv' },
        { name: 'Fertig', key: 'fertig' },
        { name: 'Aktionen', key: 'aktionen' },
        { name: 'Letzte Aktion', key: 'letzte' }
    ];

    function cell(row, text, className) {
        var td = document.createElement('td');
        td.textContent = (text === null || text === undefined) ? '' : String(text);
        if (className) { td.className = className; }
        row.appendChild(td);
        return td;
    }

    // Baut die Last-Balken-Zelle: Container mit farbigen Segmenten + Zahlentext.
    function loadCell(row, rec) {
        var td = document.createElement('td');
        td.className = 'aiw-loadcell';
        var bar = document.createElement('div');
        bar.className = 'aiw-loadbar';
        barSegments(rec).forEach(function (seg) {
            if (seg.pct <= 0) { return; }
            var s = document.createElement('span');
            s.className = 'aiw-seg ' + seg.cls;
            s.style.width = seg.pct.toFixed(2) + '%';
            bar.appendChild(s);
        });
        td.appendChild(bar);
        var lbl = document.createElement('span');
        lbl_text(lbl, rec);
        td.appendChild(lbl);
        row.appendChild(td);
        return td;
    }
    function lbl_text(span, rec) {
        span.className = 'aiw-loadnums';
        // textContent (kein innerHTML) — reine Zahlen, aber konsequent sicher.
        span.textContent = (rec.ampel_rot || 0) + ' / ' + (rec.ampel_gelb || 0)
            + ' / ' + (rec.ampel_gruen || 0);
    }

    // -------------------------------------------------------------------------
    // DOM-RENDER (nur Browser/jsdom). Rendert BEREITS sortierte/gefilterte
    // Records. opts.onSort(key) verdrahtet Kopf-Klicks; opts.sortKey/sortDir
    // markieren die aktive Spalte.
    // -------------------------------------------------------------------------
    function renderInto(container, records, opts) {
        opts = opts || {};
        var rows = records || [];
        log('renderInto: rendere', rows.length, 'Zeilen');

        while (container.firstChild) { container.removeChild(container.firstChild); }

        var table = document.createElement('table');
        table.className = 'aiw-workload-table';

        var thead = document.createElement('thead');
        var htr = document.createElement('tr');
        COLUMNS.forEach(function (col) {
            var th = document.createElement('th');
            th.textContent = col.name;
            if (col.key) {
                th.className = 'aiw-sortable';
                th.setAttribute('data-sort-key', col.key);
                if (opts.sortKey === col.key) {
                    th.className += ' aiw-sort-active';
                    th.textContent = col.name
                        + (opts.sortDir === 'desc' ? ' \u25BC' : ' \u25B2');
                }
                if (typeof opts.onSort === 'function') {
                    (function (k) {
                        th.addEventListener('click', function () { opts.onSort(k); });
                    })(col.key);
                }
            }
            htr.appendChild(th);
        });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = document.createElement('tbody');
        rows.forEach(function (r) {
            var tr = document.createElement('tr');
            tr.setAttribute('data-investigator-id', String(r.investigator_id));
            if (r.is_backlog) { tr.className = 'aiw-backlog'; }

            cell(tr, nameLabel(r), 'aiw-name');
            cell(tr, roleLabel(r), 'aiw-roles');
            cell(tr, r.total_cases, 'aiw-total');
            loadCell(tr, r);
            cell(tr, r.active_cases, 'aiw-active');
            cell(tr, r.done_cases, 'aiw-done');
            cell(tr, activityLabel(r), 'aiw-actions');
            cell(tr, r.is_backlog ? '\u2014' : formatTs(r.last_action_at));

            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        container.appendChild(table);

        log('renderInto: fertig,', rows.length, 'Zeilen');
        return { rows: rows.length };
    }

    function boot() {
        if (typeof document === 'undefined') { return; }
        var root = document.getElementById('aiw-workload-root');
        if (!root) { log('boot: kein #aiw-workload-root'); return; }

        var all = (typeof window !== 'undefined' && window.__AIW_WORKLOAD__) || [];
        var state = { sortKey: 'rot', sortDir: 'desc', filter: '' };
        log('boot: starte mit', all.length, 'Zeilen');

        var filterInput = document.getElementById('aiw-filter');
        var countEl = document.getElementById('aiw-count');

        function apply() {
            var filtered = filterRecords(all, state.filter);
            var ordered = sortRecords(filtered, state.sortKey, state.sortDir);
            renderInto(root, ordered, {
                sortKey: state.sortKey,
                sortDir: state.sortDir,
                onSort: function (key) {
                    if (state.sortKey === key) {
                        state.sortDir = (state.sortDir === 'asc') ? 'desc' : 'asc';
                    } else {
                        state.sortKey = key;
                        state.sortDir = (key === 'name') ? 'asc' : 'desc';
                    }
                    log('sort ->', state.sortKey, state.sortDir);
                    apply();
                }
            });
            if (countEl) {
                var people = filtered.filter(function (r) { return !r.is_backlog; });
                countEl.textContent = people.length + ' Ermittler';
            }
        }

        if (filterInput) {
            filterInput.addEventListener('input', function () {
                state.filter = filterInput.value;
                apply();
            });
        }
        apply();
    }

    if (typeof document !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', boot);
        } else {
            boot();
        }
    }

    var API = {
        nameLabel: nameLabel,
        roleLabel: roleLabel,
        formatTs: formatTs,
        activityLabel: activityLabel,
        barSegments: barSegments,
        sortRecords: sortRecords,
        filterRecords: filterRecords,
        renderInto: renderInto,
        boot: boot
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWWorkload = API; }
})();
