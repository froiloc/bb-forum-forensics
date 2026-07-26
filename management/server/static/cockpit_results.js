// =============================================================================
// management/server/static/cockpit_results.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ermittlungsergebnis
// =============================================================================
// Zweck:
//   Die AUSWERTUNG der Ergebnisbewertung fuer die Chef-Ermittlerin
//   (Backend: Builds 387 und 393).
//
//     GET /api/results/coverage  -> Abdeckung JE FALL (auch nie bewertete)
//     GET /api/results/stats     -> Verteilung je Kriterium + Gesamtzahlen
//
// ── DIE DREI DINGE, DIE DIESE SICHT LEISTEN MUSS ────────────────────────────
//
//   1) DIE BLINDEN FLECKEN SIND DIE HAUPTAUSSAGE, keine Randnotiz.
//      Die Kopfzeile sagt in Klartext und ROT: "Von 31 Faellen sind 12 noch
//      GAR NICHT bewertet." Ein Fall, den niemand angefasst hat, taucht in
//      /api/results/stats UEBERHAUPT NICHT auf (er hat keine Zeile in
//      v_investigation_current) — genau deshalb gibt es /coverage, und genau
//      deshalb steht die Zahl ganz oben. Eine Auswertung, die nur ueber die
//      bereits bewerteten Faelle spricht, beantwortet die falsche Frage und
//      sieht dabei vollstaendig aus (Grundregel 1).
//
//   2) VERTEILUNGEN NUR JE KRITERIUM, NIE DARUEBER HINWEG.
//      'ordinal' misst bei abuser_quality SCHWERE/AKTUALITAET, bei
//      location_quality und victim_quality PRAEZISION (M011). Ein Diagramm
//      ueber alle Kriterien wuerde Aepfel und Birnen addieren. Es gibt daher
//      EIN Diagramm JE KRITERIUM und ausdruecklich KEIN Gesamtdiagramm; die
//      Semantik-Beschreibung der Skala steht unter dem jeweiligen Diagramm.
//
//   3) DIE ZAHL OHNE DEN VERMERK GIBT ES NICHT.
//      Der Score ist provisorisch und mit niemandem abgestimmt. Der Vermerk
//      steht fest unter der Tabelle und ist nicht wegklickbar. Und: der Score
//      ist BEWUSST NICHT die Standardsortierung (mc 2026-07-12) — sortiert
//      wird nach ABDECKUNG (die Luecken zuerst). Eine Voreinstellung nach
//      Score wuerde eine Priorisierung suggerieren, die niemand abgesegnet hat.
//
// KAPSELUNG/GEBOTE: IIFE + 'use strict'; DEV-Logging; reine Funktionen ohne DOM
//   (vitest gegen den ECHTEN Code, UMD-Ausgang); XSS: nur textContent bzw.
//   Tabulator-Plaintext.
//
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Version: v0.7.469 · Build: 469 · 2026-07-20
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
        args.unshift('[AIW-Ergebnis]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // Wie viele Diagramme stehen offen? Der Rest ist eingeklappt (mc):
    // zehn offene Diagramme machen die Seite unbedienbar.
    var OPEN_CHARTS = 3;

    var FILTER = [
        { code: '', label: 'alle Faelle' },
        { code: 'nie', label: 'nie bewertet' },
        { code: 'teil', label: 'unvollstaendig' },
        { code: 'voll', label: 'vollstaendig' }
    ];

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — genau diese prueft vitest.
    // =========================================================================

    // headline: DIE Hauptaussage. Sie wird ausgeschrieben, nicht angedeutet.
    function headline(cov) {
        var s = (cov && cov.summary) || {};
        var n = s.faelle_gesamt || 0;
        var nie = s.nie_bewertet || 0;
        if (!n) { return 'Keine Faelle in der Fallakte.'; }
        if (!nie) {
            return 'Alle ' + n + ' Faelle sind bewertet (mindestens ein '
                + 'Kriterium). Vollstaendig bewertet: ' + (s.voll_bewertet || 0)
                + '.';
        }
        return 'Von ' + n + ' Faellen sind ' + nie
            + ' noch GAR NICHT bewertet. Vollstaendig bewertet: '
            + (s.voll_bewertet || 0) + '. Mittlere Abdeckung: '
            + Math.round((s.abdeckung_mittel || 0) * 100) + ' %.';
    }

    // hasBlindSpots: faerbt die Kopfzeile.
    function hasBlindSpots(cov) {
        return !!(cov && cov.summary && cov.summary.nie_bewertet > 0);
    }

    // toRows: /coverage -> Tabellenzeilen.
    function toRows(cov) {
        return ((cov && cov.faelle) || []).map(function (f) {
            var fehlend;
            if (f.nie_bewertet) {
                // NICHT "-" und nicht leer: das ist der Befund, und er wird
                // beim Namen genannt.
                fehlend = 'ALLE (nie bewertet)';
            } else if ((f.unbewertet || []).length) {
                fehlend = f.unbewertet.join(', ');
            } else {
                fehlend = '\u2014';
            }
            return {
                subject_id: f.subject_id,
                username: f.username || '',
                status: f.status || '',
                assigned_to: f.assigned_to || '\u2014',
                abdeckung_txt: f.n_bewertet + '/' + f.n_kriterien,
                abdeckung: f.abdeckung,
                n_beste: f.n_beste,
                score: f.score,
                hoechste: f.hoechste_konfidenz || '\u2014',
                fehlend: fehlend,
                nie_bewertet: !!f.nie_bewertet,
                ampel: ampelOf(f)
            };
        });
    }

    // ampelOf: rot = nie bewertet (der blinde Fleck), gruen = vollstaendig,
    // gelb = angefangen, aber nicht fertig.
    function ampelOf(f) {
        if (!f) { return 'neutral'; }
        if (f.nie_bewertet) { return 'rot'; }
        if (f.n_bewertet >= f.n_kriterien) { return 'gruen'; }
        return 'gelb';
    }

    function filterRows(rows, code) {
        if (!code) { return rows || []; }
        return (rows || []).filter(function (r) {
            if (code === 'nie') { return r.nie_bewertet; }
            if (code === 'voll') { return r.ampel === 'gruen'; }
            if (code === 'teil') { return r.ampel === 'gelb'; }
            return true;
        });
    }

    // criteriaOf: Kriterien in Katalogreihenfolge (aus /stats.catalog).
    function criteriaOf(stats) {
        return ((stats && stats.catalog && stats.catalog.criteria) || []);
    }

    // confidenceOption: ECharts-Option fuer EIN Kriterium.
    //
    // Zwei Serien: 'schwerste' und 'beste'. Die x-Achse sind die
    // KONFIDENZ-STUFEN in Katalogreihenfolge (aus confidence_items) — NICHT
    // die im Datensatz zufaellig vorkommenden. Sonst verschoebe sich die Achse
    // je nach Datenlage, und zwei Diagramme waeren nicht vergleichbar.
    //
    // Es gibt AUSDRUECKLICH KEIN Gesamtdiagramm ueber alle Kriterien: 'ordinal'
    // misst je nach Skala Praezision ODER Schwere (M011).
    function confidenceOption(criterionCode, stats) {
        var cat = (stats && stats.catalog) || {};
        var items = cat.confidence_items || [];
        var keys = items.map(function (i) { return i.code; });
        var labels = items.map(function (i) {
            return i.label + ' (' + i.ordinal + ')';
        });

        var c = ((stats && stats.criteria) || {})[criterionCode] || {};

        function serie(ex) {
            var hist = ((c[ex] || {}).conf_hist) || {};
            return keys.map(function (k) { return hist[k] || 0; });
        }

        var crit = criteriaOf(stats).filter(function (x) {
            return x.code === criterionCode;
        })[0];

        return {
            title: {
                text: (crit ? crit.label : criterionCode),
                left: 'center',
                textStyle: { fontSize: 13 }
            },
            tooltip: { trigger: 'axis' },
            legend: { bottom: 0, data: ['schwerste', 'beste'] },
            grid: { left: 44, right: 20, top: 40, bottom: 52 },
            xAxis: { type: 'category', data: labels,
                     axisLabel: { rotate: 30, fontSize: 10 } },
            yAxis: { type: 'value', minInterval: 1 },
            series: [
                { name: 'schwerste', type: 'bar', data: serie('schwerste') },
                { name: 'beste', type: 'bar', data: serie('beste') }
            ]
        };
    }

    // criterionNote: die SEMANTIK-Beschreibung der Qualitaetsskala. Sie steht
    // unter dem Diagramm, damit niemand die Zahlen ueber Skalen hinweg
    // vermischt (M011).
    function criterionNote(crit) {
        if (!crit) { return ''; }
        if (!crit.quality_scale) {
            return 'Kein Qualitaetsmass hinterlegt \u2014 dieses Kriterium '
                + 'wird bislang nur nach Konfidenz bewertet.';
        }
        return 'Qualitaetsskala: ' + (crit.quality_label || crit.quality_scale)
            + (crit.quality_beschreibung
                ? ' \u2014 ' + crit.quality_beschreibung : '');
    }

    // counts: Zaehler fuer die Filterleiste.
    function counts(rows) {
        return {
            alle: (rows || []).length,
            nie: filterRows(rows, 'nie').length,
            teil: filterRows(rows, 'teil').length,
            voll: filterRows(rows, 'voll').length
        };
    }

    // =========================================================================
    // 2) DOM/RENDER
    // =========================================================================

    var _COLUMNS = [
        { title: 'A', field: 'ampel', width: 44, hozAlign: 'center' },
        { title: 'Fall', field: 'subject_id', width: 70, sorter: 'number' },
        { title: 'Benutzername', field: 'username', headerFilter: 'input' },
        { title: 'Zustand', field: 'status', width: 110 },
        { title: 'Ermittler', field: 'assigned_to', width: 110 },
        // Sortiert wird nach dem ZAHLENWERT, angezeigt "2/10".
        { title: 'Abdeckung', field: 'abdeckung', width: 110,
          sorter: 'number',
          formatter: function (cell) {
              return cell.getData().abdeckung_txt;
          } },
        { title: 'beste', field: 'n_beste', width: 70, sorter: 'number' },
        { title: 'hoechste Konfidenz', field: 'hoechste', width: 150 },
        { title: 'Score', field: 'score', width: 80, sorter: 'number' },
        { title: 'fehlende Kriterien', field: 'fehlend' }
    ];

    function _el(doc, tag, cls, text) {
        var e = doc.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    // _tk / _mitHilfe (Build 550): gemeinsames Tabellen-Werkzeug + Hilfe-Anker
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

    // renderResults: die Sicht.
    //   cov   — /api/results/coverage
    //   stats — /api/results/stats   (kann null sein: Scope 'eigene' -> 403)
    //   opts  — { Tabulator, echarts }
    // Rueckgabe: { table, charts[] }  (charts werden von cleanupView entsorgt)
    function renderResults(mainEl, cov, stats, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = mainEl.ownerDocument || document;
        mainEl.textContent = '';

        var rows = toRows(cov);
        var charts = [];

        // --- Kopf ------------------------------------------------------------
        mainEl.appendChild(_el(doc, 'h2', 'aiw-pagehead', 'Ermittlungsergebnis'));

        // DIE HAUPTAUSSAGE. Rot, wenn es blinde Flecken gibt.
        var head = _el(doc, 'div',
                       'aiw-res-headline' + (hasBlindSpots(cov) ? ' warn' : ''),
                       headline(cov));
        head.id = 'aiw-res-headline';
        mainEl.appendChild(head);

        mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
            'Katalogversion ' + ((cov && cov.catalog_version) || '?')
            + ' \u00b7 Abdeckung bezieht sich auf das Extrem "schwerste" '
            + '(die Priorisierungsachse); "beste" wird separat ausgewiesen.'));

        // --- Filterleiste ----------------------------------------------------
        var c = counts(rows);
        var bar = _el(doc, 'div', 'aiw-res-bar');
        var sel = doc.createElement('select');
        sel.id = 'aiw-res-filter';
        FILTER.forEach(function (f) {
            var o = doc.createElement('option');
            o.value = f.code;
            o.text = f.label + ' (' + (c[f.code || 'alle'] || 0) + ')';
            sel.appendChild(o);
        });
        bar.appendChild(sel);
        mainEl.appendChild(bar);

        // --- Abdeckungstabelle ------------------------------------------------
        var tblBox = _el(doc, 'div', null);
        tblBox.id = 'aiw-res-table';
        mainEl.appendChild(tblBox);

        // DER VERMERK. Fest unter der Tabelle, nicht wegklickbar — der Score
        // in der Spalte daneben ist provisorisch und mit niemandem abgestimmt.
        if (cov && cov.vermerk) {
            var v = _el(doc, 'div', 'aiw-res-vermerk', cov.vermerk);
            v.id = 'aiw-res-vermerk';
            mainEl.appendChild(v);
        }

        var table = null;
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        if (typeof Ctor === 'function') {
            // Build 550: Aufbau ueber das gemeinsame Tabellen-Werkzeug.
            table = _tk().tabelleAufbauen(doc, tblBox, {
                sicht: 'results',
                rows: rows,
                columns: _mitHilfe(_COLUMNS, 'results', doc),
                Ctor: Ctor, einheit: 'Fälle',
                tabulator: {
                    height: '380px',
                    // STANDARDSORTIERUNG: Abdeckung aufsteigend — die LUECKEN
                    // zuerst. BEWUSST NICHT nach Score (mc 2026-07-12): eine
                    // Voreinstellung nach der provisorischen Kennzahl wuerde
                    // eine Priorisierung suggerieren, die niemand abgesegnet
                    // hat.
                    initialSort: [{ column: 'abdeckung', dir: 'asc' }],
                    rowFormatter: function (row) {
                        var el = row.getElement();
                        if (el && el.classList) {
                            el.classList.add('aiw-row-' + row.getData().ampel);
                        }
                    }
                }
            }).table;
            sel.addEventListener('change', function () {
                var f = filterRows(rows, sel.value);
                if (typeof table.replaceData === 'function') {
                    table.replaceData(f);
                }
                log('Filter:', sel.value || '(alle)', '->', f.length);
            });
        } else {
            // Build 550: die ZAHL gehoert in die Ersatzmeldung (derselbe
            // Befund wie bei cockpit_mentoring.js in Build 549). Ohne sie
            // saehe der Ausfall aus wie ein Leerbefund.
            tblBox.appendChild(_el(doc, 'div', 'aiw-placeholder',
                'Tabellenbibliothek nicht verfügbar — es liegen '
                + rows.length + ' Fälle vor. Die Aussage oben ist dennoch '
                + 'gültig.'));
        }

        // --- Verteilungen JE KRITERIUM ---------------------------------------
        mainEl.appendChild(_el(doc, 'h3', 'aiw-subhead',
                               'Verteilung der Konfidenz je Kriterium'));

        if (!stats) {
            // Scope 'eigene' bekommt /stats nicht (403). Das wird GESAGT, statt
            // eine leere Flaeche zu zeigen.
            var hint = _el(doc, 'div', 'aiw-placeholder',
                'Die fallUEBERGREIFENDE Verteilung erfordert die Faehigkeit '
                + '"results.view" mit Geltungsbereich "alle". Die Tabelle oben '
                + 'zeigt Ihre eigenen Faelle vollstaendig.');
            hint.id = 'aiw-res-nostats';
            mainEl.appendChild(hint);
            log('renderResults: keine Statistik (Scope eigene)');
            return { table: table, charts: charts };
        }

        mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
            'Bewertet: ' + (stats.faelle || 0) + ' von '
            + (stats.faelle_gesamt || 0) + ' Faellen \u00b7 '
            + (stats.faelle_unbewertet || 0) + ' ohne jede Bewertung. '
            + 'Es gibt bewusst KEIN Gesamtdiagramm ueber alle Kriterien: die '
            + 'Zahlenwerte messen je nach Skala Praezision ODER Schwere.'));

        var E = opts.echarts
            || (typeof window !== 'undefined' ? window.echarts : undefined);

        criteriaOf(stats).forEach(function (crit, idx) {
            // Eingeklappt ab dem vierten Diagramm (mc): zehn offene Diagramme
            // machen die Seite unbedienbar.
            var det = doc.createElement('details');
            det.className = 'aiw-res-chartbox';
            det.setAttribute('data-criterion', crit.code);
            if (idx < OPEN_CHARTS) { det.open = true; }

            var sum = doc.createElement('summary');
            sum.textContent = crit.label;
            det.appendChild(sum);

            var box = _el(doc, 'div', 'aiw-res-chart');
            box.setAttribute('data-chart', crit.code);
            det.appendChild(box);

            // Die SEMANTIK-Beschreibung steht UNTER dem Diagramm.
            det.appendChild(_el(doc, 'div', 'aiw-res-note',
                                criterionNote(crit)));
            mainEl.appendChild(det);

            if (E && typeof E.init === 'function') {
                var inst = E.init(box);
                inst.setOption(confidenceOption(crit.code, stats));
                charts.push(inst);

                // ECharts rendert in einem geschlossenen <details> mit Groesse
                // 0. Beim Aufklappen muss resize() laufen — sonst bleibt das
                // Diagramm leer, und der Nutzer haelt das fuer 'keine Daten'.
                det.addEventListener('toggle', function () {
                    if (det.open && typeof inst.resize === 'function') {
                        try { inst.resize(); } catch (e) { log('resize', e); }
                    }
                });
            }
        });

        log('renderResults:', rows.length, 'Faelle,',
            (cov && cov.summary && cov.summary.nie_bewertet) || 0,
            'blinde Flecken,', charts.length, 'Diagramme');

        return { table: table, charts: charts };
    }

    // =========================================================================
    // 3) UMD-Ausgang
    // =========================================================================
    var API = {
        OPEN_CHARTS: OPEN_CHARTS,
        FILTER: FILTER,
        headline: headline,
        hasBlindSpots: hasBlindSpots,
        ampelOf: ampelOf,
        toRows: toRows,
        filterRows: filterRows,
        counts: counts,
        criteriaOf: criteriaOf,
        confidenceOption: confidenceOption,
        criterionNote: criterionNote,
        renderResults: renderResults
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitResults = API; }
})();
