// =============================================================================
// management/server/static/cockpit_annostats.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Annotations-Statistik
// =============================================================================
// Zweck:
//   Rendert die Annotations-Tortenstatistik (/api/annotation-stats, Build 449)
//   als ZWEI ECharts-Kreisdiagramme: Verteilung nach Kategorie und nach Tag.
//   Ueber den Diagrammen eine Kopfzeile mit Fallzahlen — inklusive der EHRLICH
//   ausgewiesenen 'Faelle ohne evidence' (GR1: keine stille Auslassung).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG).
//   3) Ausfuehrliche Kommentare. 4) REINE Funktionen (pieOption/summaryText)
//      ohne DOM/ECharts -> vitest testet den echten Code.
//   XSS: Textinhalte via textContent; Kategorie-/Tagnamen sind beliebiger UTF-8.
//
// Version: v0.7.450 · Build: 450 · 2026-07-19
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
        args.unshift('[AIW-AnnoStats]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM/kein ECharts).
    // =========================================================================

    // pieOption: ECharts-Kreisdiagramm-Option aus einer [{key,count}]-Liste.
    // Reine, deterministische Funktion. Leere Liste -> gueltige Option ohne
    // Datenpunkte (der Aufrufer zeigt zusaetzlich einen Leerhinweis).
    function pieOption(entries, title) {
        var data = (entries || []).map(function (e) {
            return { name: e.key, value: e.count };
        });
        return {
            title: { text: title, left: 'center', textStyle: { fontSize: 13 } },
            tooltip: { trigger: 'item',
                       formatter: '{b}: {c} ({d}%)' },
            legend: { type: 'scroll', orient: 'vertical', left: 'left',
                      top: 24, textStyle: { fontSize: 11 } },
            series: [{
                type: 'pie', radius: ['35%', '65%'], center: ['58%', '55%'],
                data: data,
                label: { formatter: '{b}\n{c}' },
                emphasis: { itemStyle: { shadowBlur: 8,
                            shadowColor: 'rgba(0,0,0,0.3)' } }
            }]
        };
    }

    // summaryText: Kopfzeile aus der Antwort. Weist die Faelle ohne evidence
    // ausdruecklich aus (GR1).
    function summaryText(data) {
        var d = data || {};
        var scope = (d.scope === 'eigene') ? 'Eigene Faelle' : 'Alle Faelle';
        return scope + ': ' + (d.cases_total || 0) + ' Faelle ('
            + (d.cases_with_evidence || 0) + ' mit evidence, '
            + (d.cases_without_evidence || 0) + ' ohne) · '
            + (d.annotations_total || 0) + ' Annotationen';
    }

    // =========================================================================
    // 2) RENDER (DOM + ECharts). Gibt die Chart-Instanzen zurueck (cleanupView).
    // =========================================================================

    function renderAnnostats(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return []; }
        mainEl.textContent = '';
        data = data || {};
        var charts = [];

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Annotations-Statistik';
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = summaryText(data);
        mainEl.appendChild(sub);

        // Zwei nebeneinander liegende Chart-Container.
        var catEl = document.createElement('div');
        catEl.className = 'aiw-chart';
        catEl.style.height = '360px'; catEl.style.width = '100%';
        mainEl.appendChild(catEl);

        var tagEl = document.createElement('div');
        tagEl.className = 'aiw-chart';
        tagEl.style.height = '360px'; tagEl.style.width = '100%';
        mainEl.appendChild(tagEl);

        // Leerhinweis, falls gar keine Annotationen (kein leeres Diagramm ohne
        // Erklaerung).
        if (!(data.annotations_total > 0)) {
            var note = document.createElement('p');
            note.className = 'aiw-placeholder';
            note.textContent = 'Keine Annotationen im gewaehlten Umfang.';
            mainEl.appendChild(note);
        }

        var ECharts = opts.ECharts
            || (typeof window !== 'undefined' ? window.echarts : undefined);
        if (!ECharts || typeof ECharts.init !== 'function') {
            var warn = document.createElement('div');
            warn.className = 'aiw-placeholder';
            warn.textContent = 'Diagrammbibliothek (ECharts) nicht verfuegbar.';
            mainEl.appendChild(warn);
            log('renderAnnostats: kein ECharts');
            return [];
        }
        var catChart = ECharts.init(catEl);
        catChart.setOption(pieOption(data.by_category, 'Nach Kategorie'));
        charts.push(catChart);
        var tagChart = ECharts.init(tagEl);
        tagChart.setOption(pieOption(data.by_tag, 'Nach Tag'));
        charts.push(tagChart);
        log('renderAnnostats:', data.annotations_total, 'Annotationen');
        return charts;
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        pieOption: pieOption,
        summaryText: summaryText,
        renderAnnostats: renderAnnostats
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitAnnostats = API; }
})();
