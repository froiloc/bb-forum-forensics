// =============================================================================
// management/server/static/cockpit_capacity.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Kapazitaet
// =============================================================================
// Zweck:
//   Rendert die Kapazitaets-Sicht (/api/capacity ohne person_id -> Aggregat) als
//   horizontales ECharts-Balkendiagramm: je Ermittler BASIS (Regel-Soll) und
//   NETTO (verfuegbar nach Einschraenkungen/Garantie-Boden). Die Netto-Balken
//   werden nach AUSLASTUNG (netto/basis) eingefaerbt; stark reduzierte oben.
//   Ein Zeitraum-Wahlfeld (Default: laufender Monat) loest ein Neuladen aus.
//   Beleg: Bauplan B7 v1.1 §11.4; Build 358/359 (Berechnung + Aggregat).
//
// ZWECKBINDUNG: Planungs-/Auswertungshilfe, KEIN Bewertungsinstrument.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen ohne DOM; UMD-Ausgang ->
//   vitest testet den ECHTEN Code (echartsOption/sortRows/utilization/
//   defaultPeriod sind rein; nur renderCapacity beruehrt document/ECharts).
//
// FARB-VERTRAG: Ampelfarben spiegeln cockpit.css (--rot/--gelb/--gruen);
//   Grau fuer "keine Basis" (keine Regel-Arbeitszeit).
//
// Build 637 (Vorgang 17200856, Welle B5 - die letzte): HILFE-MARKEN
//   fuer die drei verbliebenen Bedienelemente dieser Sicht.
// Version: v0.8.637 · Build: 637 · 2026-08-01
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
        args.unshift('[AIW-Kapazitaet]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var COL_ROT = '#c0392b', COL_GELB = '#d68910', COL_GRUEN = '#1e8449';
    var COL_GRAU = '#7f8c8d';           // keine Basis / undefiniert
    var COL_BASIS = '#c8d0d8';          // Referenzbalken (Regel-Soll)

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    function nameLabel(c) {
        return c.display_name || c.system_username || ('#' + c.person_id);
    }

    // utilization: netto/basis. null, wenn keine Basis vorhanden ist (Division
    // durch 0 vermeiden; "kein Regel-Soll" ist ein eigener Zustand).
    function utilization(c) {
        if (!c.basis || c.basis <= 0) { return null; }
        return c.netto / c.basis;
    }

    // utilColor: Auslastungs-Faerbung des Netto-Balkens. Hohe Verfuegbarkeit
    // (netto nahe basis) -> gruen; stark reduziert -> rot; keine Basis -> grau.
    function utilColor(u) {
        if (u === null || u === undefined) { return COL_GRAU; }
        if (u >= 0.8) { return COL_GRUEN; }
        if (u >= 0.5) { return COL_GELB; }
        return COL_ROT;
    }

    // sortRows: stark reduzierte zuerst (utilization aufsteigend); Zeilen ohne
    // Basis (null) ans Ende. Stabil (Index als Tie-Breaker).
    function sortRows(caps) {
        var arr = (caps || []).map(function (c, i) {
            return { c: c, i: i, u: utilization(c) };
        });
        arr.sort(function (a, b) {
            var an = (a.u === null), bn = (b.u === null);
            if (an !== bn) { return an ? 1 : -1; }   // null ans Ende
            if (an && bn) { return a.i - b.i; }
            if (a.u !== b.u) { return a.u - b.u; }   // aufsteigend
            return a.i - b.i;
        });
        return arr.map(function (x) { return x.c; });
    }

    // echartsOption: deterministische ECharts-Option. Zwei Serien: Basis (grau,
    // Referenz) und Netto (je Balken nach Auslastung gefaerbt). yAxis.inverse ->
    // erste (stark reduzierte) Zeile oben.
    function echartsOption(data) {
        var caps = sortRows((data && data.capacities) || []);
        var names = caps.map(nameLabel);
        var basis = caps.map(function (c) { return c.basis || 0; });
        var netto = caps.map(function (c) {
            return { value: c.netto || 0,
                     itemStyle: { color: utilColor(utilization(c)) } };
        });
        return {
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            legend: { data: ['Basis', 'Netto'], top: 0 },
            grid: { left: 160, right: 24, top: 34, bottom: 30 },
            xAxis: { type: 'value', minInterval: 1, name: 'Minuten' },
            yAxis: { type: 'category', inverse: true, data: names },
            series: [
                { name: 'Basis', type: 'bar',
                  itemStyle: { color: COL_BASIS }, data: basis },
                { name: 'Netto', type: 'bar', data: netto }
            ]
        };
    }

    // defaultPeriod: laufender Monat [erster..letzter Tag] als ISO-Daten.
    // 'now' injizierbar (Default: neues Date) -> testbar.
    function defaultPeriod(now) {
        now = now || new Date();
        var y = now.getFullYear(), m = now.getMonth();  // m: 0-basiert
        function iso(yy, mm, dd) {
            function p(n) { return (n < 10 ? '0' : '') + n; }
            return yy + '-' + p(mm + 1) + '-' + p(dd);
        }
        var last = new Date(y, m + 1, 0).getDate();     // Tag 0 des Folgemonats
        return { start: iso(y, m, 1), end: iso(y, m, last) };
    }

    function scopeText(scope) {
        if (scope === 'eigene') {
            return 'Umfang: nur eigene Kapazitaet.';
        }
        if (scope === 'alle') {
            return 'Umfang: alle Ermittler.';
        }
        return 'Umfang: eingeschraenkt.';
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    function _dateInput(id, value) {
        var inp = document.createElement('input');
        inp.type = 'date';
        inp.id = id;
        if (value) { inp.value = value; }
        inp.className = 'aiw-dateinput';
        return inp;
    }

    // renderCapacity: Kopf + Zeitraum-Wahl + ECharts-Diagramm. data = /api/
    // capacity-Aggregat-Antwort. opts.ECharts injizierbar; opts.onPeriodChange
    // (start, end) wird beim Klick auf "Aktualisieren" gerufen (Neuladen).
    // Rueckgabe: ECharts-Instanz (oder null).
    function renderCapacity(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        mainEl.textContent = '';

        var scope = data ? data.scope : null;
        var caps = (data && data.capacities) || [];

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Kapazitaet';
        // Build 602 (Baustelle H / H11): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'capacity.titel');
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'capacity.kennzeile');
        sub.textContent = scopeText(scope) + ' (' + caps.length + ' Ermittler, '
            + 'Zeitraum ' + (data && data.start) + ' bis ' + (data && data.end)
            + ')';
        mainEl.appendChild(sub);

        // Zeitraum-Wahl.
        var ctrl = document.createElement('div');
        ctrl.className = 'aiw-capacity-controls';
        var inStart = _dateInput('aiw-cap-start', data && data.start);
        // Build 637 (Vorgang 17200856): Hilfe-Marken, LITERAL an den
        // Abnahmestellen der Fabrik '_dateInput' (Fabrikregel, Build 633).
        inStart.setAttribute('data-hilfe-id', 'capacity.bedienung.von');
        var inEnd = _dateInput('aiw-cap-end', data && data.end);
        inEnd.setAttribute('data-hilfe-id', 'capacity.bedienung.bis');
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-cap-reload';
        btn.className = 'aiw-btn';
        btn.textContent = 'Aktualisieren';
        btn.setAttribute('data-hilfe-id', 'capacity.bedienung.aktualisieren');
        btn.addEventListener('click', function () {
            if (typeof opts.onPeriodChange === 'function') {
                opts.onPeriodChange(inStart.value, inEnd.value);
            }
        });
        // BUILD 663 (Ticket d3f933cd): Von/Bis koppeln - hier AUSDRUECKLICH
        // NUR die untere Schranke, OHNE Uebernahme des Von-Datums.
        //
        // Das ist keine Nachlaessigkeit, sondern der Unterschied zwischen
        // einer EINGABE und einer ZEITRAUMWAHL: hier bestimmen die beiden
        // Felder, WAS AUSGEWERTET wird. Wuerde das Bis-Feld beim Setzen des
        // Von-Datums stillschweigend auf denselben Tag springen, schruempfte
        // die Auswertung auf 24 Stunden, und wer es uebersieht, haelt das
        // Ergebnis fuer den ganzen Zeitraum. Eine Bequemlichkeitsfunktion
        // darf keine stille Auslassung erzeugen (Grundregel 1).
        //
        // Die Schranke dagegen ist auch hier richtig: ein Ende vor dem Anfang
        // waere in jedem Fall unsinnig.
        var dp = (typeof window !== 'undefined') ? window.AIWDatumspaar : null;
        if (dp && typeof dp.koppeln === 'function') {
            dp.koppeln(inStart, inEnd, { uebernehmen: false, min: true });
        } else {
            log('renderCapacity: cockpit_datumspaar.js nicht geladen - '
                + 'Von/Bis bleiben ungekoppelt.');
        }

        ctrl.appendChild(inStart);
        ctrl.appendChild(inEnd);
        ctrl.appendChild(btn);
        mainEl.appendChild(ctrl);

        var chartEl = document.createElement('div');
        chartEl.id = 'aiw-capacity-chart';
        var height = Math.max(220, 40 + caps.length * 34);
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
            log('renderCapacity: kein ECharts');
            return null;
        }

        var chart = ECharts.init(chartEl);
        chart.setOption(echartsOption(data));
        log('renderCapacity:', caps.length, 'Ermittler, scope', scope);
        return chart;
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        COL_ROT: COL_ROT, COL_GELB: COL_GELB, COL_GRUEN: COL_GRUEN,
        COL_GRAU: COL_GRAU, COL_BASIS: COL_BASIS,
        nameLabel: nameLabel,
        utilization: utilization,
        utilColor: utilColor,
        sortRows: sortRows,
        echartsOption: echartsOption,
        defaultPeriod: defaultPeriod,
        scopeText: scopeText,
        renderCapacity: renderCapacity
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitCapacity = API; }
})();
