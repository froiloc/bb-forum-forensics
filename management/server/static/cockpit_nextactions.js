// =============================================================================
// management/server/static/cockpit_nextactions.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Arbeitsschlange
// =============================================================================
// Zweck (AP-2F / Idee 22, Frontend zu Build 519):
//   Zeigt die priorisierte, BELEGTE Arbeitsschlange aus GET /api/next_actions:
//   je offenem Fall die naechste sinnvolle Handlung mit ihrer Begruendung.
//   Das Read-Model gibt es seit Build 452/469 — es war bis Build 518 nur ueber
//   die CLI erreichbar und in KEINER Cockpit-Sicht sichtbar (Befund Uebergabe
//   440-453).
//
// Datenform GET /api/next_actions (ManagementApp._next_actions):
//   { generated_at, scope, granted_scope, total_cases, actionable,
//     done_excluded,
//     items: [ {subject_id, username, action, reason, urgency, priority,
//               ampel, status, assigned, last_activity_at}, ... ] }
//   Bei einem Fehler reicht loadNextActions {error: <text>} durch.
//
// VIER ENTSCHEIDUNGEN, DIE DEN BELEG TRAGEN:
//
//   (1) DIE BEGRUENDUNG IST DIE HAUPTSACHE, NICHT DIE HANDLUNG. Eine
//       Arbeitsschlange, die nur sagt "Fall bearbeiten", ist ein Befehl. Eine,
//       die sagt "rote Ampel, seit 34 Tagen keine Aktivitaet", ist ein Beleg.
//       Die Begruendung kommt WOERTLICH aus dem Backend (sie zitiert dort die
//       tatsaechlichen Signale) und steht deshalb als eigene, breite Spalte —
//       nicht als Tooltip, den niemand aufklappt.
//
//   (2) DIE DREI ZAHLEN GEHOEREN ZUSAMMEN. 'actionable' allein waere
//       irrefuehrend: eine kurze Schlange bei vielen Faellen saehe wie ein
//       Datenfehler aus. Die Sicht nennt deshalb IMMER alle drei —
//       Gesamtzahl, handlungsbeduerftig und abgeschlossen-und-deshalb-nicht-
//       aufgefuehrt (Grundregel 1: nichts still weglassen).
//
//   (3) DER UMFANG WIRD BENANNT. 'eigene' und 'alle' beantworten VERSCHIEDENE
//       Fragen (Selbstorganisation vs. Verteilung). Welche gerade beantwortet
//       wird, steht ueber der Liste — sonst liest sich eine kurze eigene
//       Schlange wie eine leere Dienststelle.
//
//   (4) KEINE NEUSORTIERUNG IM FRONTEND. Das Backend ordnet nach
//       Dringlichkeit, dann Prioritaet, dann letzter Aktivitaet, dann
//       subject_id. Eine zweite Sortierung hier waere eine zweite
//       Wahrheitsquelle.
//
// GRUNDREGEL 1 (kein stiller Leerbefund): drei UNTERSCHEIDBARE Zustaende —
//   Fehler, echter Leerbefund ("nichts zu tun — und zwar bei N Faellen") und
//   Befund. Eine leere Liste im Fehlerfall haette "nichts zu tun" behauptet.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging. 3) Ausfuehrliche Kommentare.
//   4) Reine Funktionen fassen NIE das DOM an; UMD-Ausgang -> vitest testet
//   den ECHTEN Code. Alle Texte ueber textContent (kein innerHTML): die
//   Benutzernamen stammen aus einem multilingualen, ungeprueften Bestand.
//
// Version: v0.8.519 · Build: 519 · 2026-07-24
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
        args.unshift('[AIW-NaechsteAktion]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM).
    // =========================================================================

    // urgencyClass / urgencyLabel: Dringlichkeit. Ein unbekannter Wert faellt
    // AUF, statt still wie 'routine' auszusehen — kaeme das Backend einmal mit
    // einer neuen Stufe, soll sie nicht in der harmlosesten verschwinden.
    function urgencyClass(u) {
        if (u === 'dringend') { return 'is-dringend'; }
        if (u === 'bald') { return 'is-bald'; }
        if (u === 'routine') { return 'is-routine'; }
        return 'is-unbekannt';
    }
    function urgencyLabel(u) {
        if (u === 'dringend' || u === 'bald' || u === 'routine') { return u; }
        return 'unbekannt (' + String(u) + ')';
    }

    // ampelClass: Spiegel der Ampel-Klassen des Cockpits.
    function ampelClass(a) {
        if (a === 'rot' || a === 'gelb' || a === 'gruen') { return a; }
        return 'unbekannt';
    }

    // assignedText: zugewiesen oder nicht. BEWUSST Klartext statt Haekchen —
    // 'nicht zugewiesen' ist die Aussage, auf die es in dieser Sicht ankommt.
    function assignedText(item) {
        return (item && item.assigned) ? 'zugewiesen' : 'NICHT zugewiesen';
    }

    // fmtTs: Unix-Sekunden lesbar. Fehlender Wert -> '—', nicht 1970.
    function fmtTs(ts) {
        if (ts === null || ts === undefined || ts === '') { return '—'; }
        var d = new Date(Number(ts) * 1000);
        if (isNaN(d.getTime())) { return String(ts); }
        function p(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-'
            + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
    }

    // scopeText: welche Frage diese Sicht gerade beantwortet (Entscheidung 3).
    function scopeText(data) {
        var s = data && data.scope;
        if (s === 'alle') {
            return 'Umfang: alle Fälle der Dienststelle (Verteilsicht).';
        }
        if (s === 'eigene') {
            return 'Umfang: nur die eigenen Fälle (eigene Arbeitsschlange).';
        }
        return 'Umfang: nicht angegeben — es ist unklar, wessen Schlange '
            + 'hier steht.';
    }

    // countsText: die DREI Zahlen (Entscheidung 2) — immer alle drei.
    function countsText(data) {
        var d = data || {};
        return (d.actionable || 0) + ' handlungsbedürftig von '
            + (d.total_cases || 0) + ' Fällen; ' + (d.done_excluded || 0)
            + ' abgeschlossen und deshalb nicht aufgeführt.';
    }

    // items: Reihenfolge des Backends, unangetastet (Entscheidung 4).
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

    // renderNextActions: baut die Sicht in mainEl. opts.doc injizierbar.
    function renderNextActions(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = opts.doc || mainEl.ownerDocument
            || (typeof document !== 'undefined' ? document : null);
        if (!doc) { return null; }

        mainEl.textContent = '';
        mainEl.appendChild(_el(doc, 'h2', 'aiw-pagehead', 'Nächstbeste Aktion'));

        // FEHLER: ausdruecklich als solcher — NICHT als leere Schlange.
        if (data && data.error) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
                'Arbeitsschlange derzeit nicht verfügbar: ' + data.error
                + ' — dies ist KEIN Leerbefund. Es ist unbekannt, ob etwas '
                + 'ansteht.'));
            log('Fehlerzustand:', data.error);
            return { state: 'error' };
        }

        mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
            scopeText(data) + ' ' + countsText(data)));

        var liste = items(data);
        if (!liste.length) {
            // ECHTER Leerbefund — mit der Grundlage, auf der er beruht.
            mainEl.appendChild(_el(doc, 'div', 'aiw-na-leer',
                'Nichts zu tun. Geprüft wurden '
                + ((data && data.total_cases) || 0) + ' Fälle; '
                + ((data && data.done_excluded) || 0)
                + ' davon sind abgeschlossen.'));
        } else {
            var tbl = _el(doc, 'table', 'aiw-na-table');
            var thead = doc.createElement('thead');
            var trh = doc.createElement('tr');
            ['Dringlichkeit', 'Fall', 'Nächste Handlung', 'Begründung',
             'Ampel', 'Status', 'Zuweisung', 'Letzte Aktivität']
                .forEach(function (h) {
                    trh.appendChild(_el(doc, 'th', null, h));
                });
            thead.appendChild(trh);
            tbl.appendChild(thead);

            var tbody = doc.createElement('tbody');
            liste.forEach(function (it) {
                var tr = _el(doc, 'tr',
                    'aiw-na-row ' + urgencyClass(it.urgency));
                tr.setAttribute('data-urgency', String(it.urgency || ''));
                tr.setAttribute('data-subject', String(it.subject_id));
                tr.appendChild(_el(doc, 'td', 'aiw-na-urg',
                    urgencyLabel(it.urgency)));
                // Fall: ID UND Benutzername — die ID ist der Schluessel, der
                // Name das, was die Ermittlerin wiedererkennt.
                tr.appendChild(_el(doc, 'td', 'aiw-na-case',
                    it.subject_id + ' · ' + (it.username || '?')));
                tr.appendChild(_el(doc, 'td', 'aiw-na-action',
                    it.action || ''));
                // ENTSCHEIDUNG (1): die Begruendung woertlich und sichtbar.
                tr.appendChild(_el(doc, 'td', 'aiw-na-reason',
                    it.reason || ''));
                var td = _el(doc, 'td', 'aiw-na-ampel');
                var dot = _el(doc, 'span', 'dot ' + ampelClass(it.ampel));
                td.appendChild(dot);
                td.appendChild(doc.createTextNode(' ' + (it.ampel || '?')));
                tr.appendChild(td);
                tr.appendChild(_el(doc, 'td', 'aiw-na-status',
                    it.status || ''));
                tr.appendChild(_el(doc, 'td', 'aiw-na-assigned',
                    assignedText(it)));
                tr.appendChild(_el(doc, 'td', 'aiw-na-ts',
                    fmtTs(it.last_activity_at)));
                tbody.appendChild(tr);
            });
            tbl.appendChild(tbody);
            mainEl.appendChild(tbl);
        }

        log('gerendert:', liste.length, 'Eintraege, scope', data && data.scope);
        return { state: liste.length ? 'befund' : 'leer', count: liste.length };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        urgencyClass: urgencyClass,
        urgencyLabel: urgencyLabel,
        ampelClass: ampelClass,
        assignedText: assignedText,
        fmtTs: fmtTs,
        scopeText: scopeText,
        countsText: countsText,
        items: items,
        renderNextActions: renderNextActions
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitNextActions = API; }
})();
