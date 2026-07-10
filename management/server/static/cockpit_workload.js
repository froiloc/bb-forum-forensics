// =============================================================================
// management/server/static/cockpit_workload.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Lastverteilung
// =============================================================================
// Zweck:
//   Rendert die Lastverteilung (/api/workload) als horizontal gestapeltes
//   Balkendiagramm (Apache ECharts): je Ermittler ein Balken, segmentiert nach
//   Ampel (rot/gelb/gruen); die Rueckstau-Zeile (unzugewiesen) erscheint als
//   eigener Balken. Reihenfolge kommt aus dem Backend (ROT absteigend, Rueckstau
//   ans Ende) und wird beibehalten (yAxis.inverse -> dringlichster oben).
//   Beleg: Bauplan B7 v1.1 §11.2; Build 350 (/api/workload).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging, zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen fassen NIE das DOM an;
//   UMD-Ausgang -> vitest testet den ECHTEN Code (echartsOption ist rein und
//   deterministisch; nur renderWorkload beruehrt document/ECharts).
//
// FARB-VERTRAG: Die Ampelfarben spiegeln cockpit.css (--rot/--gelb/--gruen).
//   ECharts kann keine CSS-Variablen lesen -> hier als Konstanten gespiegelt.
//
// Version: v0.7.351 · Build: 351 · 2026-07-10
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
        args.unshift('[AIW-Workload]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // Ampelfarben (Spiegel cockpit.css: --rot/--gelb/--gruen).
    var COL_ROT = '#c0392b', COL_GELB = '#d68910', COL_GRUEN = '#1e8449';

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM/kein ECharts).
    // =========================================================================

    // nameLabel: Anzeigename je Last-Zeile (Rueckstau traegt bereits das Label
    // '(nicht zugewiesen)' aus dem Backend).
    function nameLabel(l) {
        return l.display_name || l.system_username || '?';
    }

    // echartsOption: vollstaendige, deterministische ECharts-Option aus der
    // /api/workload-Antwort ({scope, count, loads}). Drei gestapelte Serien
    // (Rot/Gelb/Gruen) ueber den Ermittler-Kategorien. Reine Funktion.
    function echartsOption(data) {
        var loads = (data && data.loads) || [];
        var names = loads.map(nameLabel);
        var rot = loads.map(function (l) { return l.ampel_rot || 0; });
        var gelb = loads.map(function (l) { return l.ampel_gelb || 0; });
        var gruen = loads.map(function (l) { return l.ampel_gruen || 0; });

        return {
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            legend: { data: ['Rot', 'Gelb', 'Gruen'], top: 0 },
            grid: { left: 160, right: 24, top: 34, bottom: 30 },
            xAxis: { type: 'value', minInterval: 1 },
            // inverse: erste Kategorie (dringlichster, ROT desc) landet OBEN.
            yAxis: { type: 'category', inverse: true, data: names },
            color: [COL_ROT, COL_GELB, COL_GRUEN],
            series: [
                { name: 'Rot', type: 'bar', stack: 'ampel', data: rot },
                { name: 'Gelb', type: 'bar', stack: 'ampel', data: gelb },
                { name: 'Gruen', type: 'bar', stack: 'ampel', data: gruen }
            ]
        };
    }

    // scopeText: Umfang-Banner analog Overview.
    function scopeText(scope) {
        if (scope === 'eigene') {
            return 'Umfang: nur eigene Last (fremde Ermittler gekapselt).';
        }
        if (scope === 'alle') {
            return 'Umfang: alle Ermittler inkl. Rueckstau.';
        }
        return 'Umfang: eingeschraenkt.';
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    // renderWorkload: Kopf + ECharts-Diagramm in mainEl. data = /api/workload-
    // Antwort. opts.ECharts injizierbar (Default window.echarts). Rueckgabe:
    // ECharts-Instanz (oder null) — der Aufrufer entsorgt sie via dispose().
    function renderWorkload(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        mainEl.textContent = '';

        var scope = data ? data.scope : null;
        var loads = (data && data.loads) || [];

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Lastverteilung';
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = scopeText(scope) + ' (' + loads.length + ' Zeilen)';
        mainEl.appendChild(sub);

        var chartEl = document.createElement('div');
        chartEl.id = 'aiw-workload-chart';
        // Hoehe waechst mit der Zeilenzahl (min. 220px), damit die Balken bei
        // vielen Ermittlern nicht zusammengedraengt werden.
        var height = Math.max(220, 40 + loads.length * 34);
        chartEl.style.height = height + 'px';
        chartEl.style.width = '100%';
        mainEl.appendChild(chartEl);

        var ECharts = opts.ECharts
            || (typeof window !== 'undefined' ? window.echarts : undefined);
        if (!ECharts || typeof ECharts.init !== 'function') {
            var note = document.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Diagrammbibliothek (ECharts) nicht verfuegbar.';
            mainEl.appendChild(note);
            log('renderWorkload: kein ECharts');
            return null;
        }

        var chart = ECharts.init(chartEl);
        chart.setOption(echartsOption(data));
        log('renderWorkload:', loads.length, 'Zeilen, scope', scope);
        return chart;
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        COL_ROT: COL_ROT, COL_GELB: COL_GELB, COL_GRUEN: COL_GRUEN,
        nameLabel: nameLabel,
        echartsOption: echartsOption,
        scopeText: scopeText,
        renderWorkload: renderWorkload
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitWorkload = API; }
})();
