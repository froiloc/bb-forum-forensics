// =============================================================================
// management/server/static/cockpit_dashboard_charts.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Überblick
// =============================================================================
// Zweck:
//   Die Diagramme der Überblick-Kacheln (Build 570, Ticket 3fb9f16e). Diese
//   Datei enthält AUSSCHLIESSLICH reine Funktionen: Eimerbildung aus den
//   Endpunktdaten und ECharts-Optionen. Kein DOM, kein fetch, kein Zustand —
//   bis auf zwei kurze Einhänge-Helfer am Ende.
//
// WARUM EINE EIGENE DATEI (Grundregel 10): cockpit_dashboard.js führt die
//   Datenreduktion und den Aufbau der Kacheln. Die Diagrammoptionen sind ein
//   eigener Gegenstand mit eigener Prüfbarkeit — eine ECharts-Option ist ein
//   DATENOBJEKT, und genau deshalb lässt sie sich ohne Browser prüfen: der
//   Test schaut in die Option, nicht auf Pixel. Dieselbe Trennung wie bei
//   cockpit_capacity.js (echartsOption) seit Build 360.
//
// ── WOZU EIN DASHBOARD DA IST ───────────────────────────────────────────────
//
//   Es soll in drei Sekunden und ohne Lesen die Frage beantworten: brennt
//   etwas, und wo? Daraus folgen drei Regeln, die diese Datei durchhält:
//
//   (1) EINE FARBE BEDEUTET IN JEDER KACHEL DASSELBE. Rot heißt überall
//       "überschritten", Gelb "Vorwarnung", Grün "in Ordnung", Grau "keine
//       Aussage möglich". Wären die Farben je Kachel anders belegt, müsste man
//       jede Kachel einzeln lesen — und dann ist der Überblick keiner.
//
//   (2) EIN DIAGRAMM MUSS MEHR SAGEN ALS DIE ZAHL DANEBEN. Wo die Unterzeile
//       schon "3 hoch · 2 mittel" nennt, fügt ein Balken derselben drei Zahlen
//       nichts hinzu. Deshalb zeigt die Eskalationskachel das ALTER und nicht
//       die Schwere: wie lange etwas liegt, steht sonst nirgends.
//
//   (3) KEIN DIAGRAMM AUF EINER JA/NEIN-AUSSAGE. Der Zustand der Audit-Kette
//       ist unversehrt oder nicht. Ein Tacho darauf wäre Dekoration, und
//       Dekoration auf einer forensischen Aussage ist schlechter als nichts.
//       Diese Kachel bekommt bewusst KEINE Option (siehe DIAGRAMMLOS).
//
//   Und eine vierte, die aus Grundregel 1 folgt:
//
//   (4) EIN EIMER, DER NICHT BESETZT IST, VERSCHWINDET NICHT. Alle Eimer
//       stehen immer in derselben Reihenfolge da, auch mit dem Wert 0. Sonst
//       verschöbe sich die Form von Abruf zu Abruf, und ein leerer Eimer sähe
//       aus wie ein nicht erhobener.
//
// Version: v0.8.570 · Build: 570 · 2026-07-29
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
        args.unshift('[AIW-Kacheldiagramme]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) FARBEN — eine Bedeutung je Farbe, projektweit gleich.
    // =========================================================================
    // Die Werte spiegeln die Ampelfarben der Oberflaeche. Sie stehen hier als
    // Hexwerte und nicht als CSS-Variablen, weil ECharts auf eine Leinwand
    // zeichnet und dort keine Variablen des Stylesheets lesen kann.
    var FARBE = {
        rot:   '#c0392b',   // ueberschritten / ueberlastet / kritisch
        gelb:  '#d68910',   // Vorwarnung / erreicht
        gruen: '#1e8449',   // in Ordnung
        grau:  '#8a9199',   // keine Aussage / ohne Einstufung / Rest
        blau:  '#2471a3'    // neutrale Information
    };

    // Kacheln, die ABSICHTLICH kein Diagramm bekommen — mit Begruendung, damit
    // niemand es fuer eine Luecke haelt und "nachtraegt".
    var DIAGRAMMLOS = {
        kettenzustand: 'Ja/Nein-Aussage: ein Diagramm waere Dekoration.',
        naechste_aktion: 'Die Arbeitsschlange IST die Aussage; sie bekommt '
            + 'einen Anteilsbalken statt eines Diagramms.'
    };

    function zahl(n) { return (typeof n === 'number' && isFinite(n)) ? n : 0; }

    // =========================================================================
    // 2) EIMERBILDUNG (rein).
    // =========================================================================

    // ampelEimer: Ampelverteilung einer Fallliste. Feste Reihenfolge, feste
    // Eimer — auch die leeren (Regel 4).
    function ampelEimer(faelle) {
        var z = { rot: 0, gelb: 0, gruen: 0, sonst: 0 };
        (faelle || []).forEach(function (c) {
            var a = c && c.ampel;
            if (a === 'rot' || a === 'gelb' || a === 'gruen') { z[a] += 1; }
            else { z.sonst += 1; }
        });
        return z;
    }

    // alterEimer: wie lange liegen die Eskalationen schon? Die Grenzen sind
    // Arbeitstage-nah gewaehlt (bis 3 / bis 7 / bis 14 / darueber) und
    // ausdruecklich GROB - eine Kachel soll die Groessenordnung zeigen, nicht
    // den Einzelfall.
    var ALTER_EIMER = [
        { key: 'bis3',  label: 'bis 3 Tage',   max: 3,        farbe: 'gelb' },
        { key: 'bis7',  label: '4–7 Tage',     max: 7,        farbe: 'gelb' },
        { key: 'bis14', label: '8–14 Tage',    max: 14,       farbe: 'rot' },
        { key: 'ueber', label: 'über 14 Tage', max: Infinity, farbe: 'rot' }
    ];
    function alterEimer(items) {
        var z = { bis3: 0, bis7: 0, bis14: 0, ueber: 0, unbekannt: 0 };
        (items || []).forEach(function (i) {
            var d = i && i.days_inactive;
            if (typeof d !== 'number' || !isFinite(d)) {
                // NICHT unter 'bis 3 Tage' verbuchen: ein fehlender Wert ist
                // keine kurze Liegezeit, sondern eine fehlende Angabe.
                z.unbekannt += 1;
                return;
            }
            if (d <= 3) { z.bis3 += 1; }
            else if (d <= 7) { z.bis7 += 1; }
            else if (d <= 14) { z.bis14 += 1; }
            else { z.ueber += 1; }
        });
        return z;
    }

    // restEimer: Restlaufzeit der Verjaehrungsfristen. NUR Zeilen mit
    // moeglicher Aussage - eine Zeile ohne belegten Anker darf in keinem Eimer
    // landen, auch nicht im groessten.
    var REST_EIMER = [
        { key: 'bis7',   label: '≤ 7 Tage',    farbe: 'rot' },
        { key: 'bis30',  label: '8–30 Tage',   farbe: 'rot' },
        { key: 'bis90',  label: '31–90 Tage',  farbe: 'gelb' },
        { key: 'ueber90', label: '> 90 Tage',  farbe: 'gruen' }
    ];
    function restEimer(rows) {
        var z = { bis7: 0, bis30: 0, bis90: 0, ueber90: 0, ohne_aussage: 0 };
        (rows || []).forEach(function (r) {
            if (!r || r.aussage_moeglich !== true
                    || typeof r.restlaufzeit_tage !== 'number') {
                z.ohne_aussage += 1;
                return;
            }
            var t = r.restlaufzeit_tage;
            if (t <= 7) { z.bis7 += 1; }
            else if (t <= 30) { z.bis30 += 1; }
            else if (t <= 90) { z.bis90 += 1; }
            else { z.ueber90 += 1; }
        });
        return z;
    }

    // lastZeilen: Personen mit ihrer Last, absteigend, auf 'max' gekuerzt.
    // Die Rueckstauzeile ist KEINE Person und faellt heraus.
    function lastZeilen(data, max) {
        var bewertung = {};
        ((data && data.overload_assessments) || []).forEach(function (a) {
            if (a && a.name) { bewertung[a.name] = a.level; }
        });
        var rows = ((data && data.loads) || [])
            .filter(function (l) { return l && l.is_backlog !== true; })
            .map(function (l) {
                return {
                    name: l.display_name || '—',
                    aktiv: zahl(l.active_cases),
                    stufe: bewertung[l.display_name] || 'ok'
                };
            })
            .sort(function (a, b) { return b.aktiv - a.aktiv; });
        return (typeof max === 'number') ? rows.slice(0, max) : rows;
    }

    // =========================================================================
    // 3) ECHARTS-OPTIONEN (rein — pruefbar ohne Browser).
    // =========================================================================
    // Gemeinsame Grundhaltung aller Optionen:
    //   animation: false  — ein Ueberblick soll sofort stehen, nicht wachsen.
    //                       Ausserdem sind animationsfreie Optionen im Test
    //                       deterministisch.
    //   grid schmal       — die Kachel ist klein; Achsenbeschriftung nur, wo
    //                       sie etwas traegt.

    var BASIS = { animation: false, textStyle: { fontSize: 11 } };

    function _mit(basis, extra) {
        var o = {};
        var f;
        for (f in basis) {
            if (Object.prototype.hasOwnProperty.call(basis, f)) { o[f] = basis[f]; }
        }
        for (f in extra) {
            if (Object.prototype.hasOwnProperty.call(extra, f)) { o[f] = extra[f]; }
        }
        return o;
    }

    // optionAmpelRing: Ampelverteilung als Ring, Gesamtzahl in der Mitte.
    // Der Ring ist hier richtig und ein Balken waere falsch: es geht um
    // ANTEILE eines Ganzen, und das Ganze steht als Zahl im Loch.
    function optionAmpelRing(z, gesamt, titel) {
        z = z || {};
        var daten = [
            { name: 'rot', value: zahl(z.rot), itemStyle: { color: FARBE.rot } },
            { name: 'gelb', value: zahl(z.gelb),
              itemStyle: { color: FARBE.gelb } },
            { name: 'grün', value: zahl(z.gruen),
              itemStyle: { color: FARBE.gruen } },
            { name: 'ohne Einstufung', value: zahl(z.sonst),
              itemStyle: { color: FARBE.grau } }
        ];
        var summe = daten.reduce(function (s, d) { return s + d.value; }, 0);
        return _mit(BASIS, {
            tooltip: { trigger: 'item' },
            series: [{
                type: 'pie', radius: ['58%', '82%'], center: ['50%', '52%'],
                avoidLabelOverlap: false,
                label: {
                    show: true, position: 'center',
                    formatter: String(typeof gesamt === 'number'
                        ? gesamt : summe),
                    fontSize: 22, fontWeight: 600
                },
                labelLine: { show: false },
                // Ein leerer Eimer bleibt in den Daten stehen (Regel 4); nur
                // gezeichnet wird er naturgemaess nicht.
                data: daten
            }],
            _titel: titel || 'Ampelverteilung'
        });
    }

    // optionEimerBalken: senkrechte Balken ueber feste Eimer. Für "wie alt"
    // und aehnliche Verteilungen mit natuerlicher Ordnung — ein Ring waere
    // hier falsch, weil die Eimer eine REIHENFOLGE haben.
    function optionEimerBalken(eimerDef, werte, titel) {
        var namen = eimerDef.map(function (e) { return e.label; });
        var daten = eimerDef.map(function (e) {
            return { value: zahl(werte[e.key]),
                     itemStyle: { color: FARBE[e.farbe] } };
        });
        return _mit(BASIS, {
            tooltip: { trigger: 'axis' },
            grid: { left: 4, right: 8, top: 10, bottom: 2,
                    containLabel: true },
            xAxis: {
                type: 'category', data: namen,
                axisLabel: { fontSize: 10, interval: 0 },
                axisTick: { show: false }
            },
            yAxis: {
                type: 'value', minInterval: 1,
                splitLine: { lineStyle: { opacity: 0.35 } }
            },
            series: [{
                type: 'bar', data: daten, barMaxWidth: 26,
                label: { show: true, position: 'top', fontSize: 10 }
            }],
            _titel: titel || 'Verteilung'
        });
    }

    function optionAlterBalken(werte) {
        return optionEimerBalken(ALTER_EIMER, werte || {},
                                 'Liegezeit der Eskalationen');
    }

    function optionRestlaufzeit(werte) {
        return optionEimerBalken(REST_EIMER, werte || {},
                                 'Restlaufzeit der Fristen');
    }

    // optionAnteilBalken: EIN liegender Balken, der einen Teil im Ganzen
    // zeigt. Für Aussagen der Form "7 von 42". Bewusst kein Tacho: ein Tacho
    // suggeriert eine Skala mit gut und schlecht, und die gibt es hier nicht.
    function optionAnteilBalken(teil, gesamt, farbe, titel) {
        var t = Math.max(0, zahl(teil));
        var g = Math.max(t, zahl(gesamt));
        var rest = g - t;
        return _mit(BASIS, {
            tooltip: { trigger: 'axis' },
            grid: { left: 2, right: 2, top: 6, bottom: 2, containLabel: false },
            xAxis: { type: 'value', max: g || 1, show: false },
            yAxis: { type: 'category', data: [''], show: false },
            series: [
                { type: 'bar', stack: 'a', data: [t], barWidth: 18,
                  itemStyle: { color: FARBE[farbe] || FARBE.blau },
                  label: { show: t > 0, position: 'insideLeft',
                           formatter: String(t), fontSize: 11,
                           color: '#fff' } },
                { type: 'bar', stack: 'a', data: [rest], barWidth: 18,
                  itemStyle: { color: FARBE.grau, opacity: 0.35 },
                  label: { show: rest > 0, position: 'insideRight',
                           formatter: String(g), fontSize: 10 } }
            ],
            _titel: titel || 'Anteil'
        });
    }

    // optionLastBalken: liegende Balken je Person, gefaerbt nach Stufe, mit
    // einer Markierungslinie auf der Grenze. Die Linie ist der eigentliche
    // Gewinn: ohne sie sieht man Balken, aber nicht, ob sie zu lang sind.
    function optionLastBalken(zeilen, grenze) {
        var namen = (zeilen || []).map(function (z) { return z.name; });
        var daten = (zeilen || []).map(function (z) {
            var f = z.stufe === 'overload' ? FARBE.rot
                : (z.stufe === 'warn' ? FARBE.gelb : FARBE.gruen);
            return { value: zahl(z.aktiv), itemStyle: { color: f } };
        });
        var serie = {
            type: 'bar', data: daten, barMaxWidth: 14,
            label: { show: true, position: 'right', fontSize: 10 }
        };
        if (typeof grenze === 'number' && grenze > 0) {
            serie.markLine = {
                silent: true, symbol: 'none',
                lineStyle: { color: FARBE.rot, type: 'dashed', width: 1 },
                label: { formatter: 'Grenze ' + grenze, fontSize: 9,
                         position: 'end' },
                data: [{ xAxis: grenze }]
            };
        }
        return _mit(BASIS, {
            tooltip: { trigger: 'axis' },
            grid: { left: 4, right: 26, top: 6, bottom: 2, containLabel: true },
            xAxis: { type: 'value', minInterval: 1,
                     splitLine: { lineStyle: { opacity: 0.35 } } },
            yAxis: {
                type: 'category', data: namen, inverse: true,
                axisLabel: { fontSize: 10 }, axisTick: { show: false }
            },
            series: [serie],
            _titel: 'Aktive Fälle je Ermittler:in'
        });
    }

    // =========================================================================
    // 4) ZUORDNUNG KACHEL -> OPTION (rein).
    // =========================================================================
    // Rueckgabe null heisst: diese Kachel bekommt KEIN Diagramm. Das ist eine
    // Aussage und kein Ausfall — DIAGRAMMLOS nennt den Grund.
    function optionFuer(key, daten) {
        if (!daten || daten.fehler) { return null; }
        switch (key) {
        case 'fallampel':
            return optionAmpelRing(ampelEimer(daten.cases), zahl(daten.count),
                                   'Fälle nach Ampel');
        case 'meine_auftraege':
            return optionAmpelRing(ampelEimer(daten.cases), zahl(daten.count),
                                   'Eigene Fälle nach Ampel');
        case 'eskalationen':
            return optionAlterBalken(alterEimer(daten.items));
        case 'fristen':
            // KEINE FORM OHNE AUSSAGE. Ist der Parametersatz nicht bestaetigt
            // oder verweigert der Endpunkt die Aussage, gibt es auch kein
            // Diagramm - ein Balken waere eine unbelegte Rechtsbehauptung.
            if (daten.params_bestaetigt === false
                    || daten.aussage_moeglich === false) { return null; }
            return optionRestlaufzeit(restEimer(daten.rows));
        case 'wiedervorlage':
            var c = daten.counts || {};
            var faellig = zahl(c.rot) + zahl(c.gelb);
            return optionAnteilBalken(faellig,
                                      (daten.matters || []).length,
                                      zahl(c.rot) > 0 ? 'rot' : 'gelb',
                                      'Fällige von allen Vorgängen');
        case 'naechste_aktion':
            return optionAnteilBalken(zahl(daten.actionable),
                                      zahl(daten.total_cases), 'blau',
                                      'Bearbeitbar von allen Fällen');
        case 'lastverteilung':
            return optionLastBalken(lastZeilen(daten, 8),
                                    zahl(daten.max_active_cases) || null);
        default:
            return null;
        }
    }

    // =========================================================================
    // 5) EINHAENGEN (die einzigen zwei Funktionen mit Nebenwirkung).
    // =========================================================================
    // zeichne: Option in ein Element haengen. 'Ctor' ist injizierbar, damit
    // Tests ohne echtes ECharts auskommen.
    function zeichne(el, option, Ctor) {
        if (!el || !option) { return null; }
        var e = Ctor || (typeof window !== 'undefined' ? window.echarts : null);
        if (!e || typeof e.init !== 'function') {
            // KEIN STILLER AUSFALL: fehlt die Bibliothek, sagt die Kachel das.
            el.textContent = 'Diagrammbibliothek nicht geladen.';
            el.className += ' aiw-kachel-chart-fehlt';
            return null;
        }
        var inst = e.init(el);
        inst.setOption(option);
        log('gezeichnet:', option._titel);
        return inst;
    }

    function entsorge(inst) {
        if (inst && typeof inst.dispose === 'function') {
            try { inst.dispose(); } catch (e) { log('dispose', e); }
        }
    }

    // =========================================================================
    // 6) UMD-Ausgang.
    // =========================================================================
    var API = {
        FARBE: FARBE,
        DIAGRAMMLOS: DIAGRAMMLOS,
        ALTER_EIMER: ALTER_EIMER,
        REST_EIMER: REST_EIMER,
        ampelEimer: ampelEimer,
        alterEimer: alterEimer,
        restEimer: restEimer,
        lastZeilen: lastZeilen,
        optionAmpelRing: optionAmpelRing,
        optionEimerBalken: optionEimerBalken,
        optionAlterBalken: optionAlterBalken,
        optionRestlaufzeit: optionRestlaufzeit,
        optionAnteilBalken: optionAnteilBalken,
        optionLastBalken: optionLastBalken,
        optionFuer: optionFuer,
        zeichne: zeichne,
        entsorge: entsorge
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') {
        window.AIWCockpitDashboardCharts = API;
    }
})();
