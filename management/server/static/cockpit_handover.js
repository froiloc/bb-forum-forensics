// =============================================================================
// management/server/static/cockpit_handover.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Uebergaben
// =============================================================================
// Zweck (AP-2G / Idee 30, Frontend zu Build 520):
//   Zeigt das Uebergabe-Protokoll aus GET /api/handover: wer hat wann welchen
//   Fall an wen uebergeben. Das Read-Model gibt es seit Build 455/469 — es war
//   bis Build 519 nur ueber die CLI erreichbar und in KEINER Cockpit-Sicht
//   sichtbar (Befund Uebergabe 440-453).
//
// Datenform GET /api/handover (ManagementApp._handover):
//   { generated_at, reassignment_count, cases_with_handover,
//     filter_subject_id: null | <int>,
//     entries: [ {subject_id, seq, ts, kind, from_person_id, from_name,
//                 to_person_id, to_name, by_person_id, by_name}, ... ] }
//   Bei einem Fehler reicht loadHandover {error: <text>} durch.
//
// VIER ENTSCHEIDUNGEN, DIE DEN BELEG TRAGEN:
//
//   (1) DIE BELEGNUMMER STEHT IN DER ZEILE. 'seq' ist die Position in der
//       unveraenderlichen Audit-Hashkette. Sie ist das, was diese Sicht von
//       einer bequemen Liste zu einem BELEG macht: jede Zeile ist gegen den
//       Audit-Explorer nachpruefbar. Sie wird deshalb angezeigt und nicht
//       aus Platzgruenden weggelassen.
//
//   (2) 'from' IST BEI DER ERSTZUWEISUNG LEER — UND DAS IST EINE AUSSAGE.
//       kind='initial' heisst: der Fall kam aus dem Rueckstau, es gab keinen
//       Vorgaenger. Die Sicht schreibt dort ausdruecklich "(aus dem
//       Rückstau)" statt eine leere Zelle zu lassen, die wie ein
//       Datenverlust aussaehe.
//
//   (3) DER FILTER WIRD BENANNT. Ein auf einen Fall gefiltertes Protokoll
//       sieht sonst aus wie ein vollstaendiges mit wenigen Eintraegen. Steht
//       ein Filter, sagt die Sicht das ueber der Liste — und die beiden
//       Zaehler werden ausdruecklich als "im gezeigten Ausschnitt" benannt.
//
//   (4) KEINE NEUSORTIERUNG. Das Backend liefert die Eintraege nach der
//       Belegnummer ABSTEIGEND — die JUENGSTE Uebergabe steht oben (Zusage
//       aus Build 455, festgenagelt durch HO10). Das ist die Reihenfolge,
//       in der eine Leitung eine Sicht liest ("was ist zuletzt passiert").
//       Das Frontend legt sie NICHT anders aus; eine zweite Sortierung waere
//       eine zweite Wahrheitsquelle.
//
// GRUNDREGEL 1 (kein stiller Leerbefund): drei UNTERSCHEIDBARE Zustaende —
//   Fehler, echter Leerbefund ("keine Uebergabe erfasst") und Befund.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging. 3) Ausfuehrliche Kommentare.
//   4) Reine Funktionen fassen NIE das DOM an; UMD-Ausgang -> vitest testet
//   den ECHTEN Code. Alle Texte ueber textContent (kein innerHTML).
//
// Version: v0.8.520 · Build: 520 · 2026-07-24
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
        args.unshift('[AIW-Uebergabe]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM).
    // =========================================================================

    // kindLabel / kindClass: Art der Uebergabe. Ein unbekannter Wert wird
    // WOERTLICH durchgereicht und faellt auf — kaeme das Backend einmal mit
    // einer neuen Art, soll sie nicht in einer bestehenden verschwinden.
    function kindLabel(kind) {
        if (kind === 'initial') { return 'Erstzuweisung'; }
        if (kind === 'reassignment') { return 'Übergabe'; }
        if (kind === 'unassignment') { return 'Rückgabe in den Rückstau'; }
        return 'unbekannt (' + String(kind) + ')';
    }
    function kindClass(kind) {
        if (kind === 'initial') { return 'is-initial'; }
        if (kind === 'reassignment') { return 'is-uebergabe'; }
        if (kind === 'unassignment') { return 'is-rueckgabe'; }
        return 'is-unbekannt';
    }

    // personText: Name oder ID — nie 'undefined'. Rein.
    function personText(id, name) {
        if (name) { return name; }
        if (id === null || id === undefined) { return null; }
        return '#' + id;
    }

    // fromText: Entscheidung (2). Bei der Erstzuweisung gibt es KEINEN
    // Vorgaenger — das ist eine Aussage, keine Luecke.
    function fromText(e) {
        var t = personText(e && e.from_person_id, e && e.from_name);
        if (t) { return t; }
        if (e && e.kind === 'initial') { return '(aus dem Rückstau)'; }
        return '(nicht erfasst)';
    }

    // toText: bei einer Rueckgabe gibt es KEINEN Empfaenger.
    function toText(e) {
        var t = personText(e && e.to_person_id, e && e.to_name);
        if (t) { return t; }
        if (e && e.kind === 'unassignment') { return '(zurück in den Rückstau)'; }
        return '(nicht erfasst)';
    }

    // byText: wer die Uebergabe VERANLASST hat. Das ist oft eine dritte
    // Person (die Leitung) und damit eine eigene, wichtige Angabe.
    function byText(e) {
        return personText(e && e.by_person_id, e && e.by_name)
            || '(nicht erfasst)';
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

    // filterText: Entscheidung (3) — ein Ausschnitt wird benannt.
    function filterText(data) {
        var f = data && data.filter_subject_id;
        if (f === null || f === undefined || f === '') {
            return 'Ausschnitt: alle Fälle.';
        }
        return 'Ausschnitt: NUR Fall ' + f
            + ' — die Zahlen unten beziehen sich allein auf diesen Fall.';
    }

    // countsText: die beiden Zaehler, ausdruecklich auf den Ausschnitt
    // bezogen (Entscheidung 3).
    function countsText(data) {
        var d = data || {};
        return (d.reassignment_count || 0) + ' Übergaben in '
            + (d.cases_with_handover || 0)
            + ' Fällen (im gezeigten Ausschnitt).';
    }

    // entries: Reihenfolge des Backends = Reihenfolge der Audit-Kette.
    function entries(data) {
        return (data && data.entries) || [];
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

    // renderHandover: baut die Sicht in mainEl.
    // opts.onFilter(subject_id | null) — Umschalten des Ausschnitts.
    function renderHandover(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = opts.doc || mainEl.ownerDocument
            || (typeof document !== 'undefined' ? document : null);
        if (!doc) { return null; }

        mainEl.textContent = '';
        // Build 605 (Baustelle H / H14): literale Hilfe-Marken. Die Kennung
        // steht an der AUFRUFSTELLE, damit die Paritaetspruefung sie im
        // Quelltext findet (Konzept §4.2a).
        var kopf = _el(doc, 'h2', 'aiw-pagehead', 'Übergabe-Protokoll');
        kopf.setAttribute('data-hilfe-id', 'handover.titel');
        mainEl.appendChild(kopf);

        // FEHLER: ausdruecklich als solcher — NICHT als leeres Protokoll.
        if (data && data.error) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
                'Übergabe-Protokoll derzeit nicht verfügbar: ' + data.error
                + ' — dies ist KEIN Leerbefund. Es ist unbekannt, ob '
                + 'Übergaben stattgefunden haben.'));
            log('Fehlerzustand:', data.error);
            return { state: 'error' };
        }

        var kennzeile = _el(doc, 'p', 'aiw-pagesub',
            filterText(data) + ' ' + countsText(data));
        kennzeile.setAttribute('data-hilfe-id', 'handover.kennzeile');
        mainEl.appendChild(kennzeile);

        // Filterleiste: EIN Feld fuer die Fallnummer plus ein Knopf zum
        // Aufheben. Der Ausschnitt wird nie stillschweigend gewechselt.
        var bar = _el(doc, 'div', 'aiw-hv-bar');
        var feld = doc.createElement('input');
        feld.type = 'text';
        feld.className = 'aiw-hv-filter';
        feld.placeholder = 'Fallnummer (subject_id)';
        feld.setAttribute('aria-label', 'Auf eine Fallnummer einschränken');
        feld.setAttribute('data-hilfe-id', 'handover.bedienung.fallnummer');
        var f = data && data.filter_subject_id;
        feld.value = (f === null || f === undefined) ? '' : String(f);

        var go = _el(doc, 'button', 'aiw-hv-btn', 'Einschränken');
        go.type = 'button';
        go.setAttribute('data-hilfe-id', 'handover.bedienung.einschraenken');
        go.addEventListener('click', function () {
            var v = (feld.value || '').trim();
            if (typeof opts.onFilter !== 'function') { return; }
            opts.onFilter(v === '' ? null : v);
        });
        var alle = _el(doc, 'button', 'aiw-hv-btn', 'Alle Fälle');
        alle.type = 'button';
        alle.setAttribute('data-hilfe-id', 'handover.bedienung.alle');
        alle.addEventListener('click', function () {
            if (typeof opts.onFilter === 'function') { opts.onFilter(null); }
        });

        bar.appendChild(feld);
        bar.appendChild(go);
        bar.appendChild(alle);
        mainEl.appendChild(bar);

        var liste = entries(data);
        if (!liste.length) {
            mainEl.appendChild(_el(doc, 'div', 'aiw-hv-leer',
                (f === null || f === undefined)
                    ? 'Keine Übergabe erfasst. Die Audit-Kette enthält keinen '
                      + 'Zuweisungsbeleg.'
                    : 'Für Fall ' + f + ' ist keine Übergabe erfasst. Das '
                      + 'heißt NICHT, dass es den Fall nicht gibt — nur, dass '
                      + 'die Audit-Kette zu ihm keinen Zuweisungsbeleg trägt.'));
        } else {
            var tbl = _el(doc, 'table', 'aiw-hv-table');
            var thead = doc.createElement('thead');
            var trh = doc.createElement('tr');
            ['Beleg', 'Zeitpunkt', 'Fall', 'Art', 'von', 'an', 'veranlasst von']
                .forEach(function (h) {
                    trh.appendChild(_el(doc, 'th', null, h));
                });
            thead.appendChild(trh);
            tbl.appendChild(thead);

            var tbody = doc.createElement('tbody');
            liste.forEach(function (e) {
                var tr = _el(doc, 'tr', 'aiw-hv-row ' + kindClass(e.kind));
                tr.setAttribute('data-kind', String(e.kind || ''));
                tr.setAttribute('data-seq', String(e.seq));
                // ENTSCHEIDUNG (1): die Belegnummer steht in der Zeile.
                tr.appendChild(_el(doc, 'td', 'aiw-hv-seq', '#' + e.seq));
                tr.appendChild(_el(doc, 'td', 'aiw-hv-ts', fmtTs(e.ts)));
                tr.appendChild(_el(doc, 'td', 'aiw-hv-case',
                    String(e.subject_id)));
                tr.appendChild(_el(doc, 'td', 'aiw-hv-kind',
                    kindLabel(e.kind)));
                tr.appendChild(_el(doc, 'td', 'aiw-hv-from', fromText(e)));
                tr.appendChild(_el(doc, 'td', 'aiw-hv-to', toText(e)));
                tr.appendChild(_el(doc, 'td', 'aiw-hv-by', byText(e)));
                tbody.appendChild(tr);
            });
            tbl.appendChild(tbody);
            mainEl.appendChild(tbl);
        }

        // Herkunftsvermerk: er gehoert unter jede Fassung dieser Sicht, weil
        // er erklaert, warum sie nicht manipulierbar ist.
        var fuss = _el(doc, 'div', 'aiw-hv-foot',
            'Quelle: die unveränderliche Audit-Kette (Ereignistyp '
            + '„case_assigned“). Dieses Protokoll wird bei jedem Aufruf neu '
            + 'rekonstruiert — es gibt kein zweites Register, das von der '
            + 'Fallakte abweichen könnte.');
        fuss.setAttribute('data-hilfe-id', 'handover.herkunft');
        mainEl.appendChild(fuss);

        log('gerendert:', liste.length, 'Eintraege, Filter', f);
        return { state: liste.length ? 'befund' : 'leer', count: liste.length };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        kindLabel: kindLabel,
        kindClass: kindClass,
        personText: personText,
        fromText: fromText,
        toText: toText,
        byText: byText,
        fmtTs: fmtTs,
        filterText: filterText,
        countsText: countsText,
        entries: entries,
        renderHandover: renderHandover
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitHandover = API; }
})();
