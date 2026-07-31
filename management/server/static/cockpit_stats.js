// =============================================================================
// management/server/static/cockpit_stats.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Statistiken
// =============================================================================
// Zweck:
//   Rendert die Auswertungs-/Statistik-Sicht (/api/stats) mit einer REITER-
//   STRUKTUR (Tabs), damit spaeter leicht weitere Statistik-Ansichten ergaenzt
//   werden koennen. Tabs:
//     - "Verteilungen" : ECharts-Balken fuer Status / Prioritaet / Ampel
//     - "Durchsatz"    : ECharts-Linie (Fall-Ereignisse je Tag)
//     - "Ermittler"    : Tabulator-Tabelle (Faelle je Ermittler) + Summen
//   Zusaetzlich Download-Buttons: CSV (via Endpunkt ?format=csv) und JSON (aus
//   den bereits geladenen Daten). Beleg: Ideen §2.4; Build 370 (/api/stats).
//
// CHART-VISIBILITY: In versteckten Tabs (display:none) rendert ECharts mit
//   Groesse 0. Beim Tab-Wechsel wird daher resize() der nun sichtbaren Charts
//   aufgerufen (bewaehrtes Muster).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging. 3) Ausfuehrliche Kommentare.
//   4) Reine Funktionen ohne DOM (barOption/throughputOption/assigneeRows/
//   totalsText) -> vitest testet den ECHTEN Code; nur renderStats beruehrt
//   document/ECharts/Tabulator. Downloads sind ueber Callbacks injizierbar.
//
// XSS: nur textContent / Tabulator-plaintext (kein innerHTML).
//
// Version: v0.7.371 · Build: 371 · 2026-07-10
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
        args.unshift('[AIW-Statistik]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (ECharts-Optionen / Tabellenzeilen / Texte).
    // =========================================================================

    // barOption: Balkendiagramm aus einem {schluessel: anzahl}-Objekt.
    function barOption(title, obj) {
        var keys = Object.keys(obj || {});
        var vals = keys.map(function (k) { return obj[k]; });
        return {
            title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
            tooltip: { trigger: 'axis' },
            grid: { left: 44, right: 20, top: 44, bottom: 40 },
            xAxis: { type: 'category', data: keys },
            yAxis: { type: 'value', minInterval: 1 },
            series: [{ type: 'bar', data: vals }]
        };
    }

    // throughputOption: Linien-Zeitreihe aus [{day, count}].
    function throughputOption(series) {
        series = series || [];
        return {
            title: {
                text: 'Durchsatz (Fall-Ereignisse je Tag)', left: 'center',
                textStyle: { fontSize: 14 }
            },
            tooltip: { trigger: 'axis' },
            grid: { left: 44, right: 20, top: 44, bottom: 56 },
            xAxis: {
                type: 'category',
                data: series.map(function (s) { return s.day; })
            },
            yAxis: { type: 'value', minInterval: 1 },
            series: [{
                type: 'line', smooth: true, areaStyle: {},
                data: series.map(function (s) { return s.count; })
            }]
        };
    }

    // assigneeRows: by_assignee -> Tabellenzeilen; nicht zugewiesene als
    // eigene Zeile.
    function assigneeRows(data) {
        var rows = ((data && data.by_assignee) || []).map(function (a) {
            return {
                ermittler: a.display_name || ('#' + a.person_id),
                anzahl: a.count
            };
        });
        var un = (data && data.totals) ? data.totals.unassigned : 0;
        if (un) { rows.push({ ermittler: '(nicht zugewiesen)', anzahl: un }); }
        return rows;
    }

    function totalsText(data) {
        var t = (data && data.totals) || {};
        return (t.cases || 0) + ' Faelle, ' + (t.assigned || 0)
            + ' zugewiesen, ' + (t.unassigned || 0) + ' offen, '
            + (t.events || 0) + ' Ereignisse.';
    }

    function isoDate(now) {
        return (now || new Date()).toISOString().slice(0, 10);
    }

    // =========================================================================
    // 2) DOM/RENDER.
    // =========================================================================

    var _ASSIGN_COLUMNS = [
        { title: 'Ermittler', field: 'ermittler', headerFilter: 'input' },
        { title: 'Faelle', field: 'anzahl' }
    ];

    function _btn(doc, id, text, handler) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.id = id;
        b.className = 'aiw-btn';
        b.textContent = text;
        if (handler) { b.addEventListener('click', handler); }
        return b;
    }

    function _chartDiv(doc, id, height) {
        var d = doc.createElement('div');
        d.id = id;
        d.style.width = '100%';
        d.style.height = (height || 240) + 'px';
        return d;
    }

    // _tk / _mitHilfe (Build 552): gemeinsames Tabellen-Werkzeug + Hilfe-Anker
    // der Spaltenkoepfe. LAZY; die Spalten werden KOPIERT.
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

    // renderStats: Kopf + Downloads + Reiter (Tabs). opts.ECharts/opts.Tabulator
    // injizierbar; opts.onDownloadCsv/opts.onDownloadJson werden von den Buttons
    // gerufen. Rueckgabe: {charts:[...], tables:[...]} fuer den Abbau.
    function renderStats(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return { charts: [], tables: [] }; }
        var doc = mainEl.ownerDocument || document;
        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Statistiken (StA/Fuehrung)';
        // Build 602 (Baustelle H / H11): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'stats.titel');
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'stats.kennzeile');
        sub.textContent = totalsText(data)
            + (data && data.scope === 'eigene'
                ? ' (nur eigene Faelle)' : ' (alle Faelle)');
        mainEl.appendChild(sub);

        // Download-Leiste.
        var dl = doc.createElement('div');
        dl.className = 'aiw-stats-downloads';
        dl.appendChild(_btn(doc, 'aiw-stats-csv', 'CSV herunterladen',
            function () {
                if (typeof opts.onDownloadCsv === 'function') {
                    opts.onDownloadCsv();
                }
            }));
        dl.appendChild(_btn(doc, 'aiw-stats-json', 'JSON herunterladen',
            function () {
                if (typeof opts.onDownloadJson === 'function') {
                    opts.onDownloadJson(data);
                }
            }));
        mainEl.appendChild(dl);

        // Reiter-Struktur.
        var tabs = [
            { id: 'dist', label: 'Verteilungen' },
            { id: 'flow', label: 'Durchsatz' },
            { id: 'assign', label: 'Ermittler' }
        ];
        var bar = doc.createElement('div');
        bar.className = 'aiw-tabbar';
        var contents = {};
        var buttons = {};
        tabs.forEach(function (t, i) {
            var b = doc.createElement('button');
            b.type = 'button';
            b.className = 'aiw-tab' + (i === 0 ? ' active' : '');
            b.textContent = t.label;
            b.setAttribute('data-tab', t.id);
            bar.appendChild(b);
            buttons[t.id] = b;
            var c = doc.createElement('div');
            c.className = 'aiw-tabcontent';
            c.setAttribute('data-tab', t.id);
            c.style.display = (i === 0 ? 'block' : 'none');
            contents[t.id] = c;
        });
        mainEl.appendChild(bar);
        tabs.forEach(function (t) { mainEl.appendChild(contents[t.id]); });

        var ECharts = opts.ECharts
            || (typeof window !== 'undefined' ? window.echarts : undefined);
        var Tab = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);

        var charts = [];
        var tables = [];
        var byTab = { dist: [], flow: [], assign: [] };

        // --- Tab "Verteilungen": drei Balkendiagramme.
        if (typeof ECharts === 'function' || (ECharts && ECharts.init)) {
            var specs = [
                ['aiw-stats-status', 'Status', (data && data.by_status) || {}],
                ['aiw-stats-prio', 'Prioritaet',
                    (data && data.by_priority) || {}],
                ['aiw-stats-ampel', 'Ampel', (data && data.by_ampel) || {}]
            ];
            specs.forEach(function (sp) {
                var div = _chartDiv(doc, sp[0], 240);
                contents.dist.appendChild(div);
                var ch = ECharts.init(div);
                ch.setOption(barOption(sp[1], sp[2]));
                charts.push(ch); byTab.dist.push(ch);
            });
            // --- Tab "Durchsatz": Linie.
            var fdiv = _chartDiv(doc, 'aiw-stats-flow', 300);
            contents.flow.appendChild(fdiv);
            var fch = ECharts.init(fdiv);
            fch.setOption(throughputOption((data && data.throughput_by_day)));
            charts.push(fch); byTab.flow.push(fch);
        } else {
            var note = doc.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Diagrammbibliothek (ECharts) nicht verfuegbar.';
            contents.dist.appendChild(note);
        }

        // --- Tab "Ermittler": Tabulator (Build 552 ueber das gemeinsame
        // Tabellen-Werkzeug: Kopffilter, Trefferzahl, 'Filter zuruecksetzen',
        // gesicherter Bedienzustand, Hilfe-Anker).
        var assignTable = null;
        var TK = _tk();
        var assignRows = assigneeRows(data);
        if (TK) {
            assignTable = TK.tabelleAufbauen(doc, contents.assign, {
                sicht: 'stats_assign',
                rows: assignRows,
                columns: _mitHilfe(_ASSIGN_COLUMNS, 'stats_assign', doc),
                Ctor: Tab,
                einheit: 'Ermittler:innen',
                tabulator: { height: '320px' }
            }).table;
            if (assignTable) { tables.push(assignTable); }
        } else {
            // Kein stiller Leerzustand: die Zahl steht da (Grundregel 1).
            var tnote = doc.createElement('div');
            tnote.className = 'aiw-placeholder';
            tnote.textContent = 'Gemeinsames Tabellen-Werkzeug nicht geladen '
                + '— es liegen ' + assignRows.length + ' Ermittler:innen vor.';
            contents.assign.appendChild(tnote);
        }

        // Tab-Wechsel: Sichtbarkeit umschalten + Charts der Ansicht resizen.
        function selectTab(id) {
            tabs.forEach(function (t) {
                contents[t.id].style.display = (t.id === id ? 'block' : 'none');
                buttons[t.id].classList.toggle('active', t.id === id);
            });
            (byTab[id] || []).forEach(function (c) {
                if (c && typeof c.resize === 'function') {
                    try { c.resize(); } catch (e) { log('resize', e); }
                }
            });
            if (id === 'assign' && assignTable
                && typeof assignTable.redraw === 'function') {
                try { assignTable.redraw(true); } catch (e) { log('redraw', e); }
            }
        }
        tabs.forEach(function (t) {
            buttons[t.id].addEventListener('click', function () {
                selectTab(t.id);
            });
        });

        log('renderStats: scope', data && data.scope, '-',
            charts.length, 'Charts,', tables.length, 'Tabellen');
        return { charts: charts, tables: tables };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        barOption: barOption,
        throughputOption: throughputOption,
        assigneeRows: assigneeRows,
        totalsText: totalsText,
        isoDate: isoDate,
        renderStats: renderStats
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitStats = API; }
})();
