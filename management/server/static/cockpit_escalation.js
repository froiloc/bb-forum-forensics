// =============================================================================
// management/server/static/cockpit_escalation.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Eskalationen
// =============================================================================
// Zweck (AP-2G / Idee 23, Frontend zu Build 515):
//   Zeigt die belegten Eskalationen aus GET /api/escalations. Das Read-Model
//   selbst gibt es seit Build 453 — es war bis Build 514 nur ueber die CLI
//   erreichbar und in KEINER Cockpit-Sicht sichtbar (Befund Uebergabe 440-453).
//
// Datenform GET /api/escalations (ManagementApp._escalations):
//   { generated_at, total_cases,
//     count_hoch, count_mittel, count_niedrig,
//     items: [ {rule_code, label, severity, subject_id, message,
//               days_inactive}, ... ],
//     thresholds: {red_overdue_days, stale_open_days, backlog_high},
//     acknowledgeable: false }
//   Bei einem Fehler reicht loadEscalation {error: <text>} durch.
//
// DREI ENTSCHEIDUNGEN, DIE DEN BELEG TRAGEN:
//
//   (1) subject_id === null IST EINE AUSSAGE, KEINE LUECKE. Die systemische
//       Regel 'rueckstau_hoch' gehoert GAR KEINEM Fall — sie meldet, dass
//       Faelle unverteilt liegen bleiben. Sie wird deshalb ausdruecklich als
//       "systemisch (kein Einzelfall)" ausgewiesen und NICHT als leere Zelle
//       oder als Fall 0. Eine leere Zelle haette wie ein Datenfehler gelesen.
//
//   (2) DER MASSSTAB STEHT DABEI. Die angewandten Schwellen erscheinen unter
//       der Liste. "30 Tage inaktiv" ist erst zusammen mit ">= 30" eine
//       nachpruefbare Aussage; ohne den Massstab waere jede Zeile eine
//       unbelegte Behauptung.
//
//   (3) DER FEHLENDE QUITTIERUNGSWEG WIRD BENANNT. Das Backend sagt ueber
//       'acknowledgeable' ausdruecklich, dass es (noch) keinen Schreibpfad
//       gibt. Die Sicht schreibt das hin, statt einfach keinen Knopf zu
//       zeigen: "kein Knopf" laesst offen, ob die Faehigkeit fehlt oder nur
//       das RECHT — und ein geratener Zustand ist kein Beleg.
//
// GRUNDREGEL 1 (kein stiller Leerbefund): drei UNTERSCHEIDBARE Zustaende —
//   Fehler ("derzeit nicht verfuegbar"), echter Leerbefund ("keine Eskalation,
//   bewertet wurden N Faelle") und Befund (Liste). Eine leere Liste im
//   Fehlerfall haette faelschlich "alles in Ordnung" behauptet.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging, umschaltbar ueber
//   window.AIW_COCKPIT_DEBUG. 3) Ausfuehrliche Kommentare. 4) Reine Funktionen
//   fassen NIE das DOM an; UMD-Ausgang -> vitest testet den ECHTEN Code.
//   Alle Texte ueber textContent (kein innerHTML): die Meldungen enthalten
//   Benutzernamen aus einem multilingualen, ungeprueften Bestand.
//
// Version: v0.8.516 · Build: 516 · 2026-07-24
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
        args.unshift('[AIW-Eskalation]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM).
    // =========================================================================

    // severityClass: CSS-Modifikator je Schwere. Unbekannte Werte bekommen
    // KEINEN Modifikator (statt still auf 'niedrig' zu fallen) — eine neue
    // Schwere aus dem Backend soll auffallen, nicht verschwinden.
    function severityClass(sev) {
        if (sev === 'hoch') { return 'is-hoch'; }
        if (sev === 'mittel') { return 'is-mittel'; }
        if (sev === 'niedrig') { return 'is-niedrig'; }
        return 'is-unbekannt';
    }

    // severityLabel: Anzeigetext je Schwere. Ein unbekannter Wert wird
    // WOERTLICH durchgereicht und als solcher markiert.
    function severityLabel(sev) {
        if (sev === 'hoch') { return 'hoch'; }
        if (sev === 'mittel') { return 'mittel'; }
        if (sev === 'niedrig') { return 'niedrig'; }
        return 'unbekannt (' + String(sev) + ')';
    }

    // itemTarget: Bezugsobjekt einer Meldung als Klartext. Siehe Entscheidung
    // (1) im Dateikopf — null ist hier eine Aussage, keine Luecke.
    function itemTarget(item) {
        if (!item || item.subject_id === null || item.subject_id === undefined) {
            return 'systemisch (kein Einzelfall)';
        }
        return 'Fall ' + item.subject_id;
    }

    // inactiveText: Inaktivitaet als Klartext. null bedeutet "nie eine
    // Aktivitaet erfasst" — das ist etwas anderes als "0 Tage inaktiv".
    function inactiveText(item) {
        if (!item || item.days_inactive === null
            || item.days_inactive === undefined) {
            return '—';
        }
        return item.days_inactive + ' T';
    }

    // countsText: Zusammenfassung ueber der Liste. Nennt IMMER alle drei
    // Schweren, auch wenn sie 0 sind (eine weggelassene 0 waere ein stiller
    // Verzicht), und die Zahl der bewerteten Faelle — sie belegt, dass die
    // Erhebung stattgefunden hat.
    function countsText(data) {
        var d = data || {};
        return (d.count_hoch || 0) + ' hoch · ' + (d.count_mittel || 0)
            + ' mittel · ' + (d.count_niedrig || 0) + ' niedrig — bewertet '
            + 'wurden ' + (d.total_cases || 0) + ' Fälle.';
    }

    // thresholdText: der angewandte Massstab (Entscheidung (2)). Fehlt der
    // Block, wird das BENANNT statt einfach nichts anzuzeigen.
    function thresholdText(data) {
        var t = data && data.thresholds;
        if (!t) {
            return 'Angewandter Maßstab: nicht mitgeliefert — die Einstufungen '
                + 'sind hier NICHT nachrechenbar.';
        }
        return 'Angewandter Maßstab: rote Fälle ab ' + t.red_overdue_days
            + ' Tagen Inaktivität, offene zugewiesene Fälle ab '
            + t.stale_open_days + ' Tagen, Rückstau-Alarm ab '
            + t.backlog_high + ' unzugewiesenen Fällen.';
    }

    // ackText: Ansage zum Quittierungsweg (Entscheidung (3)).
    function ackText(data) {
        if (data && data.acknowledgeable === true) {
            return '';
        }
        return 'Quittieren ist in dieser Fassung nicht möglich: die Sicht ist '
            + 'rein auswertend. Eine Eskalation verschwindet erst, wenn die '
            + 'zugrunde liegende Ursache behoben ist (Fall bearbeiten, '
            + 'zuweisen oder abschließen).';
    }

    // items: die Meldungen in der Reihenfolge des Backends. BEWUSST keine
    // Neusortierung im Frontend — das Backend ordnet bereits nach Schwere,
    // dann Inaktivitaet, dann subject_id. Zwei Sortierungen fuer dieselbe
    // Liste waeren zwei Wahrheitsquellen.
    function items(data) {
        return (data && data.items) || [];
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    function _el(doc, tag, cls, text) {
        var e = doc.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    // renderEscalation: baut die Sicht in mainEl. opts.doc ist injizierbar
    // (JSDOM-Tests); Default ist das Dokument von mainEl.
    function renderEscalation(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = opts.doc || mainEl.ownerDocument
            || (typeof document !== 'undefined' ? document : null);
        if (!doc) { return null; }

        mainEl.textContent = '';
        mainEl.appendChild(_el(doc, 'h2', 'aiw-pagehead', 'Eskalationen'));

        // FEHLER: ausdruecklich als solcher — NICHT als leere Liste.
        if (data && data.error) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
                'Eskalationen derzeit nicht verfügbar: ' + data.error
                + ' — dies ist KEIN Leerbefund. Es ist unbekannt, ob '
                + 'Eskalationen vorliegen.'));
            log('Fehlerzustand:', data.error);
            return { state: 'error' };
        }

        mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub', countsText(data)));

        var liste = items(data);
        if (!liste.length) {
            // ECHTER Leerbefund — und er sagt dazu, worauf er sich stuetzt.
            mainEl.appendChild(_el(doc, 'div', 'aiw-esk-leer',
                'Keine Eskalation. Geprüft wurden '
                + ((data && data.total_cases) || 0)
                + ' Fälle gegen den unten genannten Maßstab.'));
        } else {
            var tbl = _el(doc, 'table', 'aiw-esk-table');
            var thead = doc.createElement('thead');
            var trh = doc.createElement('tr');
            ['Schwere', 'Regel', 'Bezug', 'Inaktiv', 'Begründung']
                .forEach(function (h) {
                    trh.appendChild(_el(doc, 'th', null, h));
                });
            thead.appendChild(trh);
            tbl.appendChild(thead);

            var tbody = doc.createElement('tbody');
            liste.forEach(function (it) {
                var tr = _el(doc, 'tr', 'aiw-esk-row '
                    + severityClass(it.severity));
                tr.setAttribute('data-rule', String(it.rule_code || ''));
                tr.setAttribute('data-severity', String(it.severity || ''));
                tr.appendChild(_el(doc, 'td', 'aiw-esk-sev',
                    severityLabel(it.severity)));
                tr.appendChild(_el(doc, 'td', null, it.label || it.rule_code));
                tr.appendChild(_el(doc, 'td', 'aiw-esk-target',
                    itemTarget(it)));
                tr.appendChild(_el(doc, 'td', 'aiw-esk-days',
                    inactiveText(it)));
                // Die Begruendung kommt WOERTLICH aus dem Backend — das
                // Frontend formuliert keine zweite Fassung derselben Aussage.
                tr.appendChild(_el(doc, 'td', 'aiw-esk-msg', it.message || ''));
                tbody.appendChild(tr);
            });
            tbl.appendChild(tbody);
            mainEl.appendChild(tbl);
        }

        // Massstab (2) und Quittierungs-Ansage (3) stehen IMMER da — auch beim
        // Leerbefund, denn ohne Massstab sagt auch ein Leerbefund nichts aus.
        mainEl.appendChild(_el(doc, 'div', 'aiw-esk-foot', thresholdText(data)));
        var ack = ackText(data);
        if (ack) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-esk-ack', ack));
        }

        log('gerendert:', liste.length, 'Meldungen');
        return { state: liste.length ? 'befund' : 'leer', count: liste.length };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        severityClass: severityClass,
        severityLabel: severityLabel,
        itemTarget: itemTarget,
        inactiveText: inactiveText,
        countsText: countsText,
        thresholdText: thresholdText,
        ackText: ackText,
        items: items,
        renderEscalation: renderEscalation
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitEscalation = API; }
})();
