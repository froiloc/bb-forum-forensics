// =============================================================================
// management/server/static/cockpit_planung.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Prognose & Gantt
// =============================================================================
// Zweck:
//   Rendert die Planungssicht aus zwei read-only-Endpunkten:
//     * /api/forecast — Backlog-Abbau-Prognose in 3 Szenarien (Build 446) mit
//       OFFENGELEGTEN Annahmen. Darstellung: Szenario-Tabelle + Balken der
//       Restdauer (Tage) je Szenario.
//     * /api/gantt   — Termin-/Ressourcenuebersicht (Build 447): je Fall ein
//       Balken (Beginn->Ende), gruppiert nach Ermittler. Darstellung: ECharts-
//       'custom'-Gantt (eine Zeile je Fall, Farbe nach laufend/abgeschlossen).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging, zur Laufzeit umschaltbar
//      (window.AIW_COCKPIT_DEBUG). 3) Ausfuehrliche Kommentare. 4) REINE
//      Funktionen fassen NIE das DOM/ECharts an -> vitest testet den echten
//      Code (forecastRows/forecastOption/ganttOption sind deterministisch).
//   XSS: alle Textinhalte via textContent (Benutzernamen sind beliebiger UTF-8).
//
// BELEGTREUE (GR1): keine erfundenen Zahlen. Ist die Prognose datenarm
//   (data_sufficient=false), wird das ausgewiesen (Restdauer 'unbestimmt'),
//   nicht kaschiert. Die Annahmen aus dem Backend werden UNVERAENDERT gelistet.
//
// FARBEN (Spiegel cockpit.css): laufend=blau, abgeschlossen=gruen, Szenarien
//   optimistisch/erwartet/pessimistisch = gruen/blau/rot.
//
// Version: v0.7.448 · Build: 448 · 2026-07-19
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
        args.unshift('[AIW-Planung]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var COL_LAUFEND = '#2471a3';    // offener Fall (ongoing)
    var COL_FERTIG = '#1e8449';     // abgeschlossen
    var SCEN_COL = {                // Szenariofarben
        optimistisch: '#1e8449', erwartet: '#2471a3', pessimistisch: '#c0392b'
    };

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM/kein ECharts).
    // =========================================================================

    // forecastRows: Tabellenzeilen aus der /api/forecast-Antwort. Restdauer/
    // Fertigstellung koennen 'unbestimmt' sein (null) -> ehrliche Anzeige.
    function forecastRows(fc) {
        var scen = (fc && fc.scenarios) || [];
        return scen.map(function (s) {
            return {
                name: s.name,
                factor: s.factor,
                rate: s.rate_per_day,
                days: (s.days_to_clear === null || s.days_to_clear === undefined)
                    ? null : s.days_to_clear,
                finish: s.finish_day || null
            };
        });
    }

    // forecastOption: ECharts-Balken der Restdauer (Tage) je Szenario. Reine,
    // deterministische Funktion. Unbestimmte Restdauer -> 0 im Balken, aber die
    // Tabelle weist 'unbestimmt' aus (kein Vortaeuschen eines Wertes).
    function forecastOption(fc) {
        var rows = forecastRows(fc);
        var names = rows.map(function (r) { return r.name; });
        var data = rows.map(function (r) {
            return {
                value: (r.days === null) ? 0 : r.days,
                itemStyle: { color: SCEN_COL[r.name] || '#666' }
            };
        });
        return {
            title: { text: 'Restdauer bis Backlog-Abbau (Tage)', left: 'center',
                     textStyle: { fontSize: 13 } },
            tooltip: { trigger: 'axis' },
            grid: { left: 110, right: 30, top: 40, bottom: 30 },
            xAxis: { type: 'value', name: 'Tage' },
            yAxis: { type: 'category', data: names, inverse: true },
            series: [{ type: 'bar', data: data, barWidth: '55%' }]
        };
    }

    // ganttTasks: flache Aufgabenliste aus der /api/gantt-Antwort. Eine Zeile je
    // Fall, Label 'Fall <uid> (username)', mit Lane-Name (Ermittler) und Farbe.
    function ganttTasks(g) {
        var lanes = (g && g.lanes) || [];
        var tasks = [];
        lanes.forEach(function (lane) {
            (lane.bars || []).forEach(function (b) {
                tasks.push({
                    label: 'Fall ' + b.user_id + ' (' + (b.username || '?') + ')',
                    lane: lane.assignee_name,
                    startMs: b.start_ts * 1000,
                    endMs: b.end_ts * 1000,
                    ongoing: !!b.ongoing,
                    status: b.status,
                    userId: b.user_id
                });
            });
        });
        return tasks;
    }

    // ganttOption: ECharts-'custom'-Gantt. Eine Kategorie je Task; Balken von
    // Start bis Ende auf einer Zeit-Achse. renderItem zeichnet das Rechteck.
    // Reine Funktion (renderItem ist eine Funktion, aber die OPTION-Struktur ist
    // deterministisch und testbar).
    function ganttOption(g) {
        var tasks = ganttTasks(g);
        var categories = tasks.map(function (t) { return t.label; });
        var data = tasks.map(function (t, i) {
            return {
                name: t.label,
                value: [i, t.startMs, t.endMs, t.ongoing ? 1 : 0],
                itemStyle: { color: t.ongoing ? COL_LAUFEND : COL_FERTIG },
                _lane: t.lane, _status: t.status
            };
        });

        function renderItem(params, api) {
            var catIndex = api.value(0);
            var start = api.coord([api.value(1), catIndex]);
            var end = api.coord([api.value(2), catIndex]);
            var height = (api.size([0, 1])[1]) * 0.6;
            var rect = {
                x: start[0], y: start[1] - height / 2,
                width: Math.max(end[0] - start[0], 2), height: height
            };
            return {
                type: 'rect', shape: rect,
                style: api.style()
            };
        }

        return {
            title: { text: 'Fall-Zeitschienen je Ermittler', left: 'center',
                     textStyle: { fontSize: 13 } },
            tooltip: {
                // Kein HTML-Injektions-Risiko: ECharts-Tooltip-Formatter gibt
                // hier reine, aus Zahlen/gefilterten Feldern gebaute Strings.
                formatter: function (p) {
                    var d = p.data || {};
                    return (p.name || '') + '<br/>Spur: ' + (d._lane || '-')
                        + '<br/>Status: ' + (d._status || '-')
                        + (d.value && d.value[3] ? '<br/>(laufend)' : '');
                }
            },
            grid: { left: 220, right: 30, top: 40, bottom: 40 },
            xAxis: { type: 'time' },
            yAxis: { type: 'category', data: categories, inverse: true },
            series: [{
                type: 'custom', renderItem: renderItem,
                encode: { x: [1, 2], y: 0 }, data: data
            }]
        };
    }

    function fmtDate(ts) {
        if (ts === null || ts === undefined) { return '-'; }
        var d = new Date(ts * 1000);
        // ISO-Datum (UTC), stabil und locale-unabhaengig.
        return d.toISOString().slice(0, 10);
    }

    // =========================================================================
    // 2) RENDER (DOM + ECharts). Gibt ein Array der erzeugten Chart-Instanzen
    //    zurueck, damit die Shell sie im cleanupView entsorgen kann.
    // =========================================================================

    function renderPlanung(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return []; }
        mainEl.textContent = '';
        var forecast = (data && data.forecast) || {};
        var gantt = (data && data.gantt) || {};
        var charts = [];

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Prognose & Gantt';
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        var rate = (forecast.observed_rate_per_day !== undefined)
            ? forecast.observed_rate_per_day : 0;
        sub.textContent = 'Backlog: ' + (forecast.backlog || 0)
            + ' offene Faelle · beobachtete Rate: ' + rate + ' Faelle/Tag'
            + (forecast.data_sufficient ? '' : ' · keine belastbare Prognose');
        mainEl.appendChild(sub);

        // -- Prognose-Tabelle --------------------------------------------------
        var rows = forecastRows(forecast);
        var table = document.createElement('table');
        table.className = 'aiw-table aiw-forecast';
        var thead = document.createElement('thead');
        var htr = document.createElement('tr');
        ['Szenario', 'Faktor', 'Rate/Tag', 'Restdauer', 'Fertigstellung']
            .forEach(function (t) {
                var th = document.createElement('th');
                th.textContent = t; htr.appendChild(th);
            });
        thead.appendChild(htr); table.appendChild(thead);
        var tbody = document.createElement('tbody');
        rows.forEach(function (r) {
            var tr = document.createElement('tr');
            [r.name, 'x' + r.factor, String(r.rate),
             (r.days === null ? 'unbestimmt' : (r.days + ' Tage')),
             (r.finish || '-')].forEach(function (v) {
                var td = document.createElement('td');
                td.textContent = v;   // XSS-sicher
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        mainEl.appendChild(table);

        // -- Prognose-Diagramm -------------------------------------------------
        var fcEl = document.createElement('div');
        fcEl.className = 'aiw-chart';
        fcEl.style.height = '220px'; fcEl.style.width = '100%';
        mainEl.appendChild(fcEl);

        // -- Gantt-Diagramm ----------------------------------------------------
        var gEl = document.createElement('div');
        gEl.className = 'aiw-chart';
        var taskN = ((gantt.lanes || []).reduce(function (a, l) {
            return a + ((l.bars || []).length); }, 0));
        gEl.style.height = Math.max(220, 60 + taskN * 26) + 'px';
        gEl.style.width = '100%';
        mainEl.appendChild(gEl);

        // -- Annahmen (unveraendert aus dem Backend, GR1) ----------------------
        var aTitle = document.createElement('h3');
        aTitle.textContent = 'Annahmen der Prognose';
        mainEl.appendChild(aTitle);
        var ul = document.createElement('ul');
        ul.className = 'aiw-assumptions';
        (forecast.assumptions || []).forEach(function (a) {
            var li = document.createElement('li');
            li.textContent = a;   // XSS-sicher
            ul.appendChild(li);
        });
        mainEl.appendChild(ul);

        // -- ECharts instanziieren (falls verfuegbar) --------------------------
        var ECharts = opts.ECharts
            || (typeof window !== 'undefined' ? window.echarts : undefined);
        if (!ECharts || typeof ECharts.init !== 'function') {
            var note = document.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Diagrammbibliothek (ECharts) nicht verfuegbar.';
            mainEl.appendChild(note);
            log('renderPlanung: kein ECharts');
            return [];
        }
        var fcChart = ECharts.init(fcEl);
        fcChart.setOption(forecastOption(forecast));
        charts.push(fcChart);
        var gChart = ECharts.init(gEl);
        gChart.setOption(ganttOption(gantt));
        charts.push(gChart);
        log('renderPlanung: Backlog', forecast.backlog, '| Tasks', taskN);
        return charts;
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        COL_LAUFEND: COL_LAUFEND, COL_FERTIG: COL_FERTIG, SCEN_COL: SCEN_COL,
        forecastRows: forecastRows,
        forecastOption: forecastOption,
        ganttTasks: ganttTasks,
        ganttOption: ganttOption,
        fmtDate: fmtDate,
        renderPlanung: renderPlanung
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitPlanung = API; }
})();
