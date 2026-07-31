// =============================================================================
// management/server/static/cockpit_retention.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Aufbewahrung
// =============================================================================
// Zweck (AP-2G / Idee 29, Frontend zu Build 521):
//   Zeigt die Aufbewahrungsfristen-Uebersicht aus GET /api/retention: welche
//   abgeschlossenen Faelle die Frist ueberschritten haben. Das Read-Model gibt
//   es seit Build 456 — es war bis Build 520 nur ueber die CLI erreichbar und
//   in KEINER Cockpit-Sicht sichtbar (Befund Uebergabe 440-453).
//
// DIE WICHTIGSTE AUSSAGE DIESER DATEI:
//   HIER WIRD NICHTS GELOESCHT UND HIER KANN NICHTS GELOESCHT WERDEN.
//   Diese Sicht erhebt einen PRUEFVORSCHLAG. Es gibt bewusst KEINEN Knopf,
//   keine Auswahl und keinen Schreibpfad — das Loeschen von Beweismitteln ist
//   eine Governance-Entscheidung ausserhalb dieses Systems. Der Vorbehalt
//   steht deshalb OBEN in der Sicht, in eigener Auszeichnung, und nicht als
//   Fussnote: eine Kandidatenliste ohne ihn koennte als Arbeitsauftrag
//   missverstanden werden. Das Backend sendet ihn zusaetzlich als
//   'deletes_nothing' mit, und die Sicht MELDET es, falls diese Zusicherung
//   einmal fehlen sollte.
//
// Datenform GET /api/retention (ManagementApp._retention):
//   { generated_at, retention_days, total_cases, closed_cases,
//     without_reference, candidate_count, deletes_nothing: true,
//     candidates: [ {subject_id, username, status, reference_ts,
//                    reference_field, days_retained, over_by_days}, ... ] }
//   Bei einem Fehler reicht loadRetention {error: <text>} durch.
//
// DREI WEITERE ENTSCHEIDUNGEN:
//
//   (1) 'without_reference' IST DIE WICHTIGSTE ZAHL und steht deshalb NEBEN
//       der Kandidatenzahl, nicht darunter. Es sind die Faelle, bei denen
//       KEIN Bezugszeitpunkt ermittelbar war: weder Kandidat noch
//       unverdaechtig, sondern UNGEPRUEFT. Ohne sie saehe eine kurze
//       Kandidatenliste wie eine vollstaendige Pruefung aus.
//
//   (2) DAS BEZUGSFELD STEHT IN DER ZEILE. Ob die Frist ab 'approved_at' oder
//       ab 'updated_at' laeuft, aendert das Ergebnis — und ist eine
//       nachpruefbare Tatsache, keine Nebensache. Es wird deshalb angezeigt.
//
//   (3) DIE ANGEWANDTE FRIST STEHT DABEI. '742 Tage aufbewahrt' ist erst
//       zusammen mit 'Frist 730 Tage' eine Aussage.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging. 3) Ausfuehrliche Kommentare.
//   4) Reine Funktionen fassen NIE das DOM an; UMD-Ausgang -> vitest testet
//   den ECHTEN Code. Alle Texte ueber textContent (kein innerHTML).
//
// Version: v0.8.521 · Build: 521 · 2026-07-24
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
        args.unshift('[AIW-Aufbewahrung]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM).
    // =========================================================================

    // vorbehaltText: der LOESCHVORBEHALT. Er ist der Kern dieser Sicht.
    // Fehlt die Zusicherung des Servers, wird das GEMELDET statt sie
    // stillschweigend zu behaupten — eine unbelegte Beruhigung waere hier
    // schlimmer als gar keine.
    function vorbehaltText(data) {
        if (data && data.deletes_nothing === true) {
            return 'PRÜFVORSCHLAG — es wird nichts gelöscht. Diese Sicht '
                + 'kann nicht löschen: es gibt dafür keinen Weg im Werkzeug. '
                + 'Das Löschen von Beweismitteln ist eine Governance-'
                + 'Entscheidung außerhalb dieses Systems.';
        }
        return 'ACHTUNG: Die Antwort trägt den Löschvorbehalt NICHT mit. '
            + 'Behandeln Sie diese Liste keinesfalls als Arbeitsauftrag, '
            + 'bevor die Herkunft geklärt ist.';
    }

    // vorbehaltOk: ob die Zusicherung vorliegt (steuert die Auszeichnung).
    function vorbehaltOk(data) {
        return !!(data && data.deletes_nothing === true);
    }

    // fristText: die ANGEWANDTE Frist (Entscheidung 3).
    function fristText(data) {
        var d = data || {};
        if (d.retention_days === null || d.retention_days === undefined) {
            return 'Angewandte Frist: nicht mitgeliefert — die Einstufungen '
                + 'sind hier NICHT nachrechenbar.';
        }
        return 'Angewandte Frist: ' + d.retention_days + ' Tage ab dem '
            + 'jeweiligen Bezugszeitpunkt.';
    }

    // countsText: die vier Zahlen. 'without_reference' steht bewusst mitten
    // im Satz und nicht am Ende (Entscheidung 1).
    function countsText(data) {
        var d = data || {};
        return (d.candidate_count || 0) + ' über der Frist; '
            + (d.without_reference || 0) + ' ohne ermittelbaren '
            + 'Bezugszeitpunkt (UNGEPRÜFT, weder Kandidat noch unverdächtig); '
            + (d.closed_cases || 0) + ' abgeschlossen von insgesamt '
            + (d.total_cases || 0) + ' Fällen.';
    }

    // referenceLabel: das Bezugsfeld im Klartext (Entscheidung 2).
    function referenceLabel(field) {
        if (field === 'approved_at') { return 'Freigabe (approved_at)'; }
        if (field === 'updated_at') { return 'letzte Änderung (updated_at)'; }
        if (!field) { return '(nicht erfasst)'; }
        return 'unbekannt (' + String(field) + ')';
    }

    // fmtTs: Unix-Sekunden lesbar. Fehlender Wert -> '—', nicht 1970.
    function fmtTs(ts) {
        if (ts === null || ts === undefined || ts === '') { return '—'; }
        var d = new Date(Number(ts) * 1000);
        if (isNaN(d.getTime())) { return String(ts); }
        function p(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
    }

    // overText: die Ueberschreitung. 0 heisst 'genau auf der Frist' und wird
    // als solche benannt, nicht als Leerwert.
    function overText(c) {
        if (!c || c.over_by_days === null || c.over_by_days === undefined) {
            return '—';
        }
        var n = Number(c.over_by_days);
        return n === 0 ? 'genau auf der Frist' : ('+' + n + ' T');
    }

    // candidates: Reihenfolge des Backends (staerkste Ueberschreitung zuerst).
    // KEINE Neusortierung — zwei Sortierungen waeren zwei Wahrheitsquellen.
    function candidates(data) {
        return (data && data.candidates) || [];
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

    // renderRetention: baut die Sicht in mainEl. opts.doc injizierbar.
    // BEWUSST OHNE opts fuer Schreibpfade: es gibt keine.
    function renderRetention(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = opts.doc || mainEl.ownerDocument
            || (typeof document !== 'undefined' ? document : null);
        if (!doc) { return null; }

        mainEl.textContent = '';
        // Build 605 (Baustelle H / H14): literale Hilfe-Marken an der
        // Aufrufstelle.
        var kopf = _el(doc, 'h2', 'aiw-pagehead', 'Aufbewahrungsfristen');
        kopf.setAttribute('data-hilfe-id', 'retention.titel');
        mainEl.appendChild(kopf);

        // FEHLER: ausdruecklich als solcher — NICHT als leere Liste.
        if (data && data.error) {
            mainEl.appendChild(_el(doc, 'p', 'aiw-pagesub',
                'Fristenübersicht derzeit nicht verfügbar: ' + data.error
                + ' — dies ist KEIN Leerbefund. Es ist unbekannt, ob Fristen '
                + 'überschritten sind.'));
            log('Fehlerzustand:', data.error);
            return { state: 'error' };
        }

        // DER LOESCHVORBEHALT — ganz oben, in eigener Auszeichnung.
        var vorbehalt = _el(doc, 'div',
            'aiw-rt-vorbehalt ' + (vorbehaltOk(data) ? 'is-ok' : 'is-fehlt'),
            vorbehaltText(data));
        vorbehalt.setAttribute('data-hilfe-id', 'retention.vorbehalt');
        mainEl.appendChild(vorbehalt);

        var kennzeile = _el(doc, 'p', 'aiw-pagesub', countsText(data));
        kennzeile.setAttribute('data-hilfe-id', 'retention.kennzeile');
        mainEl.appendChild(kennzeile);

        var liste = candidates(data);
        if (!liste.length) {
            // ECHTER Leerbefund — mit der Grundlage, auf der er beruht, UND
            // dem Hinweis auf die ungeprueften Faelle: sonst laese sich
            // 'keine Kandidaten' als 'alles geprueft und in Ordnung'.
            mainEl.appendChild(_el(doc, 'div', 'aiw-rt-leer',
                'Kein Fall über der Frist. Geprüft wurden '
                + ((data && data.closed_cases) || 0)
                + ' abgeschlossene Fälle; '
                + ((data && data.without_reference) || 0)
                + ' davon ließen sich mangels Bezugszeitpunkt NICHT prüfen.'));
        } else {
            var tbl = _el(doc, 'table', 'aiw-rt-table');
            var thead = doc.createElement('thead');
            var trh = doc.createElement('tr');
            ['Fall', 'Status', 'Bezugsfeld', 'Bezugszeitpunkt',
             'aufbewahrt', 'über der Frist']
                .forEach(function (h) {
                    trh.appendChild(_el(doc, 'th', null, h));
                });
            thead.appendChild(trh);
            tbl.appendChild(thead);

            var tbody = doc.createElement('tbody');
            liste.forEach(function (c) {
                var tr = _el(doc, 'tr', 'aiw-rt-row');
                tr.setAttribute('data-subject', String(c.subject_id));
                tr.appendChild(_el(doc, 'td', 'aiw-rt-case',
                    c.subject_id + ' · ' + (c.username || '?')));
                tr.appendChild(_el(doc, 'td', 'aiw-rt-status',
                    c.status || ''));
                // ENTSCHEIDUNG (2): das Bezugsfeld steht in der Zeile.
                tr.appendChild(_el(doc, 'td', 'aiw-rt-field',
                    referenceLabel(c.reference_field)));
                tr.appendChild(_el(doc, 'td', 'aiw-rt-ts',
                    fmtTs(c.reference_ts)));
                tr.appendChild(_el(doc, 'td', 'aiw-rt-days',
                    (c.days_retained === null || c.days_retained === undefined)
                        ? '—' : (c.days_retained + ' T')));
                tr.appendChild(_el(doc, 'td', 'aiw-rt-over', overText(c)));
                tbody.appendChild(tr);
            });
            tbl.appendChild(tbody);
            mainEl.appendChild(tbl);
        }

        // Die angewandte Frist steht IMMER da — auch beim Leerbefund, denn
        // ohne Massstab sagt auch ein Leerbefund nichts aus.
        var fuss = _el(doc, 'div', 'aiw-rt-foot', fristText(data));
        fuss.setAttribute('data-hilfe-id', 'retention.frist');
        mainEl.appendChild(fuss);

        log('gerendert:', liste.length, 'Kandidaten');
        return {
            state: liste.length ? 'befund' : 'leer',
            count: liste.length,
            vorbehalt: vorbehaltOk(data)
        };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        vorbehaltText: vorbehaltText,
        vorbehaltOk: vorbehaltOk,
        fristText: fristText,
        countsText: countsText,
        referenceLabel: referenceLabel,
        fmtTs: fmtTs,
        overText: overText,
        candidates: candidates,
        renderRetention: renderRetention
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitRetention = API; }
})();
