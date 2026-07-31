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
//   Build 514 (AP-2F / Idee 21): ZUSAETZLICH die AKTIVE UEBERLASTWARNUNG aus
//   Build 451/513. Sie steht als Banner UEBER dem Diagramm.
//
//   WARUM HIER UND NICHT IN EINER EIGENEN SICHT: die Warnung bewertet genau die
//   Zahlen, die dieses Diagramm zeichnet. Beides kommt aus EINER Antwort
//   (/api/workload, Build 513) und damit aus EINER Messung — Banner und Balken
//   koennen nicht auseinanderlaufen. Eine eigene Sicht haette zwei Abfragen zu
//   zwei Zeitpunkten gehabt und damit die Moeglichkeit, zwei verschiedene
//   Staende nebeneinander zu zeigen. Das waere ein widerspruechlicher Beleg.
//
//   FUENF REGELN FUER DAS BANNER (alle aus Grundregel 1 — kein Beleg wird
//   ausgelassen, kein Beleg still uebersprungen):
//   R1  Jede Einstufung wird BEGRUENDET. Die Ausloeser kommen als Klartext aus
//       dem Backend (assessment.reasons) und werden woertlich angezeigt — das
//       Frontend formuliert KEINE eigene Begruendung, sonst gaebe es zwei
//       Fassungen derselben Aussage (Bildschirm vs. Akten-Export).
//   R2  Die ANGEWANDTEN SCHWELLEN stehen im Banner. Eine Warnung ohne ihren
//       Massstab waere nicht nachrechenbar.
//   R3  Wer NICHT beanstandet ist, wird GEZAEHLT und die Zahl genannt. Nur die
//       auffaelligen Zeilen zu listen und den Rest wegzulassen, waere still.
//   R4  Ein eingeschraenkter Umfang (scope_limited) wird BENANNT. backlog_size
//       ist dann 0, weil NICHT ERHOBEN — nicht, weil es keinen Rueckstau gibt.
//       Diese beiden Faelle duerfen nicht gleich aussehen.
//   R5  Fehlt der overload-Block ganz (aelteres Backend), sagt das Banner das
//       ausdruecklich. Ein stilles Nichts saehe aus wie 'keine Ueberlast'.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging, zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen fassen NIE das DOM an;
//   UMD-Ausgang -> vitest testet den ECHTEN Code (echartsOption ist rein und
//   deterministisch; nur renderWorkload/renderOverloadBanner beruehren das DOM).
//
// FARB-VERTRAG: Die Ampelfarben spiegeln cockpit.css (--rot/--gelb/--gruen).
//   ECharts kann keine CSS-Variablen lesen -> hier als Konstanten gespiegelt.
//
// Version: v0.8.514 · Build: 514 · 2026-07-24
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

    // ------------------------------------------------- Ueberlast (Build 514)

    // overloadOf / assessmentsOf: defensive Zugriffe auf die beiden Bloecke aus
    // Build 513. Sie sind BEWUSST getrennt in der Antwort (flache Skalare vs.
    // Zeilenliste) — Begruendung in management_app._workload.
    function overloadOf(data) {
        return (data && data.overload) ? data.overload : null;
    }
    function assessmentsOf(data) {
        return (data && data.overload_assessments) || [];
    }

    // overloadLevel: Gesamtstufe des Banners. Rein.
    //   'none'     — kein overload-Block in der Antwort (R5)
    //   'overload' — mindestens eine Person UEBER der Schwelle
    //   'warn'     — mindestens eine Person AN der Schwelle ODER Rueckstau-Alarm
    //   'ok'       — nichts davon
    // Der Rueckstau-Alarm ist bewusst 'warn' und nicht 'overload': er ist ein
    // SYSTEMISCHES Signal (Faelle liegen unverteilt), keine Personen-Ueberlast.
    // Er verschwindet dadurch nicht — er bekommt eine eigene Zeile (R1).
    function overloadLevel(data) {
        var ov = overloadOf(data);
        if (!ov) { return 'none'; }
        if ((ov.overloaded_count || 0) > 0) { return 'overload'; }
        if ((ov.warned_count || 0) > 0 || ov.backlog_alarm === true) {
            return 'warn';
        }
        return 'ok';
    }

    // overloadTitle: Ueberschrift des Banners. Rein.
    function overloadTitle(level, ov) {
        ov = ov || {};
        if (level === 'none') { return 'Überlastwarnung nicht verfügbar'; }
        if (level === 'overload') {
            return 'Überlast: ' + (ov.overloaded_count || 0)
                + ' über der Grenze';
        }
        if (level === 'warn') {
            var teile = [];
            if ((ov.warned_count || 0) > 0) {
                teile.push(ov.warned_count + ' an der Grenze');
            }
            if (ov.backlog_alarm === true) { teile.push('Rückstau-Alarm'); }
            return 'Achtung: ' + teile.join(', ');
        }
        return 'Keine Überlast';
    }

    // thresholdText: die ANGEWANDTEN Schwellen als Klartext (R2). Rein.
    // Ohne diese Zeile waere jede Einstufung eine unbelegte Behauptung.
    function thresholdText(ov) {
        if (!ov) { return ''; }
        return 'Angewandte Schwellen: aktive Fälle ' + ov.max_active_cases
            + ', rote Fälle ' + ov.max_red_cases
            + ', Rückstau-Alarm ab ' + ov.backlog_alert + '.';
    }

    // assessmentLine: EINE Zeile je beanstandeter Person. Die Begruendung kommt
    // WOERTLICH aus dem Backend (R1) — das Frontend erfindet keine zweite
    // Fassung derselben Aussage. Rein.
    function assessmentLine(a) {
        var kopf = (a.level === 'overload' ? 'ÜBER GRENZE' : 'an Grenze')
            + ': ' + (a.name || ('#' + a.investigator_id));
        var gruende = (a.reasons || []).join('; ');
        return gruende ? (kopf + ' — ' + gruende) : kopf;
    }

    // overloadLines: alle Klartextzeilen des Banners, in Lesereihenfolge.
    // Rein — und der eigentliche Prueffall der Grundregel 1: hier entscheidet
    // sich, was gesagt und was verschwiegen wird.
    function overloadLines(data) {
        var ov = overloadOf(data);
        var lines = [];
        if (!ov) {
            // R5: das Nichts wird BENANNT, nicht als 'alles gut' dargestellt.
            lines.push('Diese Antwort enthält keinen Überlast-Block. Die '
                + 'Lastzahlen unten sind vollständig, aber NICHT bewertet.');
            return lines;
        }

        // Beanstandete zuerst — das Backend liefert sie bereits nach
        // Dringlichkeit sortiert (overload > warn > ok); die Reihenfolge wird
        // uebernommen und NICHT neu erfunden.
        assessmentsOf(data).forEach(function (a) {
            if (a && a.level && a.level !== 'ok') {
                lines.push(assessmentLine(a));
            }
        });

        // Rueckstau: eigene Zeile, systemisch (R1). Bei begrenztem Umfang wird
        // er GAR NICHT genannt — dort steht stattdessen die R4-Zeile, weil eine
        // Zahl 0 dort nichts belegen wuerde.
        if (ov.backlog_alarm === true) {
            lines.push('Rückstau: ' + ov.backlog_size
                + ' unzugewiesene Fälle (Alarm ab ' + ov.backlog_alert + ').');
        } else if (ov.scope_limited !== true) {
            lines.push('Rückstau: ' + (ov.backlog_size || 0)
                + ' unzugewiesene Fälle (unter der Alarmschwelle '
                + ov.backlog_alert + ').');
        }

        // R3: die Unauffaelligen werden GEZAEHLT, nicht weggelassen.
        var alle = assessmentsOf(data).length;
        var ok = assessmentsOf(data).filter(function (a) {
            return a && a.level === 'ok';
        }).length;
        lines.push(ok + ' von ' + alle + ' ohne Beanstandung.');

        // R4: begrenzter Umfang wird benannt — sonst liest sich eine nicht
        // erhobene 0 wie ein erhobener Leerbefund.
        if (ov.scope_limited === true) {
            lines.push('Umfang begrenzt: bewertet wird nur die eigene Last. '
                + 'Rückstau und fremde Ermittler sind hier NICHT erhoben '
                + '(nicht zu lesen als: nicht vorhanden).');
        }

        return lines;
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    // renderOverloadBanner: haengt das Warnbanner an 'parent' und gibt das
    // erzeugte Element zurueck. Es wird IMMER erzeugt — auch bei 'ok' und auch
    // bei 'none'. Ein Banner, das nur im Alarmfall existiert, laesst offen, ob
    // gerade nichts los ist oder ob die Pruefung ausgefallen ist.
    // Alle Texte ueber textContent (kein innerHTML) — die Anzeigenamen kommen
    // aus einem multilingualen Bestand und duerfen kein Markup ausloesen.
    function renderOverloadBanner(parent, data) {
        if (!parent) { return null; }
        var level = overloadLevel(data);
        var ov = overloadOf(data);

        var box = document.createElement('div');
        box.className = 'aiw-overload is-' + level;
        box.setAttribute('data-level', level);

        var t = document.createElement('div');
        t.className = 'aiw-overload-title';
        t.textContent = overloadTitle(level, ov);
        box.appendChild(t);

        var ul = document.createElement('ul');
        overloadLines(data).forEach(function (text) {
            var li = document.createElement('li');
            li.textContent = text;
            ul.appendChild(li);
        });
        box.appendChild(ul);

        // R2: die Schwellen stehen im Banner — als Fussnote, weil sie den
        // Massstab liefern und nicht selbst ein Befund sind.
        if (ov) {
            var foot = document.createElement('div');
            foot.className = 'aiw-overload-foot';
            foot.textContent = thresholdText(ov);
            box.appendChild(foot);
        }

        parent.appendChild(box);
        log('Ueberlast-Banner:', level, overloadLines(data).length, 'Zeilen');
        return box;
    }

    // renderWorkload: Kopf + Ueberlast-Banner + ECharts-Diagramm in mainEl.
    // data = /api/workload-Antwort. opts.ECharts injizierbar (Default
    // window.echarts). Rueckgabe: ECharts-Instanz (oder null) — der Aufrufer
    // entsorgt sie via dispose().
    function renderWorkload(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        mainEl.textContent = '';

        var scope = data ? data.scope : null;
        var loads = (data && data.loads) || [];

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Lastverteilung';
        // Build 602 (Baustelle H / H11): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'workload.titel');
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'workload.kennzeile');
        sub.textContent = scopeText(scope) + ' (' + loads.length + ' Zeilen)';
        mainEl.appendChild(sub);

        // Build 514: der Alarm steht VOR dem Diagramm — man soll ihn lesen,
        // bevor man die Balken deutet.
        renderOverloadBanner(mainEl, data);

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
        // Build 514 (Ueberlastwarnung) — rein und damit unter vitest pruefbar.
        overloadOf: overloadOf,
        assessmentsOf: assessmentsOf,
        overloadLevel: overloadLevel,
        overloadTitle: overloadTitle,
        thresholdText: thresholdText,
        assessmentLine: assessmentLine,
        overloadLines: overloadLines,
        renderOverloadBanner: renderOverloadBanner,
        renderWorkload: renderWorkload
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitWorkload = API; }
})();
