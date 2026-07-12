// =============================================================================
// management/server/static/cockpit_reports.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Berichts-Abnahme
// =============================================================================
// Zweck:
//   Zeigt die Berichte ALLER Faelle (/api/reports, Build 374) fuer die Abnahme.
//   Die Daten stammen aus den evidence_<uid>.db und werden serverseitig ueber
//   einen WAL-sicheren Fingerabdruck-Cache eingelesen.
//
//   Aufbau:
//     - Kopf + Scan-Info (wie viele DBs tatsaechlich neu gelesen wurden)
//     - "Neu einlesen"-Knopf  -> /api/reports?force=1 (Cache umgehen)
//     - Statusfilter (alle / draft / submitted / approved / final)
//     - Tabulator-Tabelle der Berichte (Fall, Titel, Typ, Status, Freigaben)
//     - HINWEISBEREICH: nicht lesbare evidence-DBs (errors) und Faelle ohne
//       evidence-DB (cases_without_db). GRUNDREGEL 1: solche Zustaende werden
//       SICHTBAR gemacht, nicht verschwiegen.
//
//   Die eigentliche FREIGABE (Versiegelung) folgt in Build 376 — diese Sicht
//   ist bewusst zunaechst nur lesend.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging. 3) Ausfuehrliche Kommentare.
//   4) Reine Funktionen (toRows/filterByStatus/scanInfoText) -> vitest testet
//   den ECHTEN Code; nur renderReports beruehrt document/Tabulator.
//
// XSS: nur textContent / Tabulator-plaintext (kein innerHTML).
//
// Build 376: Betriebshinweis, wenn der Scan-Cache fehlt (Migration nicht
//   angewandt) — sichtbar in der Sicht, nicht nur im Log.
// Build 378: Freigabe im Cockpit — Aktionsfeld je Bericht (Freigeben /
//   Endgueltig / Siegel pruefen) inkl. Anzeige des Pruefergebnisses.
// Version: v0.7.378 · Build: 378 · 2026-07-10
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
        args.unshift('[AIW-Berichte]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var STATUS_LABEL = {
        draft: 'Entwurf',
        submitted: 'eingereicht',
        approved: 'freigegeben',
        final: 'final'
    };
    var TYPE_LABEL = {
        interim: 'Zwischenbericht',
        final: 'Abschlussbericht',
        addendum: 'Nachtrag'
    };
    var STATUS_ORDER = ['submitted', 'draft', 'approved', 'final'];

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    function fmtTs(tsSec) {
        if (!tsSec) { return ''; }
        var d = new Date(tsSec * 1000);
        function p(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-'
            + p(d.getDate());
    }

    // toRows: /api/reports.reports -> Tabellenzeilen.
    function toRows(data) {
        return ((data && data.reports) || []).map(function (r) {
            var ap = r.approvals || [];
            return {
                user_id: r.user_id,
                report_id: r.id,
                username: r.username || '',
                title: r.title,
                typ: TYPE_LABEL[r.report_type] || r.report_type,
                nr: r.sequence_nr,
                status: r.status,
                status_label: STATUS_LABEL[r.status] || r.status,
                created_by: r.created_by,
                created: fmtTs(r.created_at),
                freigaben: ap.length,
                // Die letzte Freigabe (fuer die Anzeige "von wem/wann").
                letzte_freigabe: ap.length
                    ? (ap[ap.length - 1].approved_by + ' / '
                        + fmtTs(ap[ap.length - 1].approved_at))
                    : ''
            };
        });
    }

    // filterByStatus: '' (alle) oder ein Status.
    function filterByStatus(rows, status) {
        if (!status) { return rows; }
        return rows.filter(function (r) { return r.status === status; });
    }

    // statusCounts: {status -> Anzahl} ueber alle Berichte.
    function statusCounts(data) {
        var out = {};
        ((data && data.reports) || []).forEach(function (r) {
            out[r.status] = (out[r.status] || 0) + 1;
        });
        return out;
    }

    // scanInfoText: macht transparent, wie die Daten zustande kamen (wie viele
    // evidence-DBs tatsaechlich geoeffnet wurden -> Cache-Wirkung sichtbar).
    function scanInfoText(data) {
        if (!data) { return ''; }
        return (data.case_db_count || 0) + ' Fall-Datenbanken, davon '
            + (data.rescanned || 0) + ' neu eingelesen; '
            + (data.count || 0) + ' Berichte.';
    }

    // availableActions: welche Aktionen sind fuer DIESEN Bericht moeglich?
    // Rein -> in vitest pruefbar. Die Regeln spiegeln die Vorbedingungen des
    // Servers (Build 377): Freigabe nur aus 'submitted', 'final' nur aus
    // 'approved'. Ohne reports.approve bleibt nur die Siegelpruefung.
    function availableActions(row, canApprove) {
        var acts = [];
        if (!row) { return acts; }
        if (canApprove && row.status === 'submitted') {
            acts.push({ kind: 'approve', label: 'Freigeben (versiegeln)' });
        }
        if (canApprove && row.status === 'approved') {
            acts.push({ kind: 'final', label: 'Endgueltig freigeben' });
        }
        if (row.status === 'approved' || row.status === 'final') {
            acts.push({ kind: 'verify', label: 'Siegel pruefen' });
        }
        return acts;
    }

    // verifyText: Klartext zum Pruefergebnis. Eine ABWEICHUNG ist ein
    // Manipulationsverdacht und wird beim Namen genannt.
    function verifyText(v) {
        if (!v) { return ''; }
        if (!v.sealed) {
            return 'Kein Siegel vorhanden (Bericht ist nicht freigegeben).';
        }
        if (v.match === true) {
            return 'Siegel in Ordnung: der Berichtsinhalt entspricht dem '
                + 'freigegebenen Stand.';
        }
        return 'ABWEICHUNG: Der Berichtsinhalt weicht vom versiegelten Stand '
            + 'ab. Das ist ein Manipulationsverdacht und muss geprueft werden.';
    }

    // =========================================================================
    // 2) DOM/RENDER.
    // =========================================================================

    var _COLUMNS = [
        { title: 'Fall', field: 'user_id' },
        { title: 'Benutzername', field: 'username', headerFilter: 'input' },
        { title: 'Titel', field: 'title', headerFilter: 'input' },
        { title: 'Typ', field: 'typ' },
        { title: 'Nr.', field: 'nr' },
        { title: 'Status', field: 'status_label' },
        { title: 'Verfasser', field: 'created_by' },
        { title: 'Erstellt', field: 'created' },
        { title: 'Freigaben', field: 'freigaben' },
        { title: 'Letzte Freigabe', field: 'letzte_freigabe' }
    ];

    // _hints: Fehler + Faelle ohne evidence-DB sichtbar machen (Grundregel 1).
    function _hints(doc, data) {
        var errs = (data && data.errors) || [];
        var missing = (data && data.cases_without_db) || [];
        var cacheErr = data && data.cache_error;
        if (!errs.length && !missing.length && !cacheErr) { return null; }

        var box = doc.createElement('div');
        box.className = 'aiw-hints';
        box.id = 'aiw-reports-hints';

        // BETRIEBSHINWEIS (Build 376): Der Scan-Cache steht nicht zur
        // Verfuegung — typischerweise, weil die Migration nicht angewandt
        // wurde. Das ist kein Datenverlust (die Liste oben ist vollstaendig),
        // aber jeder Aufruf liest alle Fall-Datenbanken neu ein.
        if (cacheErr) {
            var ce = doc.createElement('div');
            ce.className = 'aiw-hint-title error';
            ce.id = 'aiw-reports-cacheerr';
            ce.textContent = 'Scan-Cache nicht verfuegbar (' + cacheErr
                + '). Die Liste ist vollstaendig, aber jeder Aufruf liest alle '
                + 'Fall-Datenbanken neu. Bitte Migrationen anwenden: '
                + 'python -m management.migrate';
            box.appendChild(ce);
        }

        if (errs.length) {
            var h1 = doc.createElement('div');
            h1.className = 'aiw-hint-title error';
            h1.textContent = errs.length
                + ' Fall-Datenbank(en) nicht lesbar:';
            box.appendChild(h1);
            var ul = doc.createElement('ul');
            errs.forEach(function (e) {
                var li = doc.createElement('li');
                li.textContent = 'Fall ' + e.user_id + ': ' + e.error;
                ul.appendChild(li);
            });
            box.appendChild(ul);
        }
        if (missing.length) {
            var h2 = doc.createElement('div');
            h2.className = 'aiw-hint-title';
            h2.textContent = missing.length
                + ' bekannte(r) Fall/Faelle ohne evidence-Datenbank: '
                + missing.join(', ');
            box.appendChild(h2);
        }
        return box;
    }

    // renderReports: Kopf + Scan-Info + Neu-einlesen + Statusfilter + Tabelle
    // + Hinweise. opts.Tabulator injizierbar; opts.onForceRescan() und
    // opts.onFilter(status) werden von den Bedienelementen gerufen.
    // Rueckgabe: Tabulator-Instanz (oder null).
    function renderReports(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = mainEl.ownerDocument || document;
        mainEl.textContent = '';

        var rows = toRows(data);
        var counts = statusCounts(data);

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Berichts-Abnahme';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.id = 'aiw-reports-scaninfo';
        sub.textContent = scanInfoText(data);
        mainEl.appendChild(sub);

        // Bedienleiste: Statusfilter + Neu einlesen.
        var bar = doc.createElement('div');
        bar.className = 'aiw-reports-bar';

        var sel = doc.createElement('select');
        sel.id = 'aiw-reports-filter';
        var optAll = doc.createElement('option');
        optAll.value = '';
        optAll.text = 'alle Status (' + rows.length + ')';
        sel.appendChild(optAll);
        STATUS_ORDER.forEach(function (s) {
            var o = doc.createElement('option');
            o.value = s;
            o.text = (STATUS_LABEL[s] || s) + ' (' + (counts[s] || 0) + ')';
            sel.appendChild(o);
        });
        bar.appendChild(sel);

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-reports-rescan';
        btn.className = 'aiw-btn';
        btn.textContent = 'Neu einlesen';
        btn.addEventListener('click', function () {
            if (typeof opts.onForceRescan === 'function') {
                opts.onForceRescan();
            }
        });
        bar.appendChild(btn);
        mainEl.appendChild(bar);

        var container = doc.createElement('div');
        container.id = 'aiw-reports-table';
        mainEl.appendChild(container);

        var hints = _hints(doc, data);
        if (hints) { mainEl.appendChild(hints); }

        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        if (typeof Ctor !== 'function') {
            var note = doc.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Tabellenbibliothek nicht verfuegbar.';
            container.appendChild(note);
            log('renderReports: kein Tabulator-Ctor');
            return null;
        }

        var table = new Ctor(container, {
            data: rows, columns: _COLUMNS,
            layout: 'fitColumns', height: '440px',
            // Zeilenklick -> Aktionsfeld fuer DIESEN Bericht (Build 378).
            rowClick: function (e, row) {
                selectRow(row.getData());
            }
        });

        // --- AKTIONSFELD (Build 378) ---------------------------------------
        // Bewusst KEINE Knoepfe in den Tabellenzellen: die Freigabe ist ein
        // Schreibvorgang mit Belegpflicht. Der Ermittler waehlt erst einen
        // Bericht, sieht dann Status und Siegel-Aktionen — ein Klick weniger
        // Versehen.
        var panel = doc.createElement('div');
        panel.className = 'aiw-report-actions';
        panel.id = 'aiw-report-actions';
        mainEl.appendChild(panel);

        function selectRow(r) {
            panel.textContent = '';
            if (!r) { return; }

            var head = doc.createElement('div');
            head.className = 'aiw-subhead';
            head.textContent = 'Bericht ' + r.user_id + '/' + r.report_id
                + ' \u2014 ' + r.title + ' (' + r.status_label + ')';
            panel.appendChild(head);

            var acts = availableActions(r, !!opts.canApprove);
            var btns = doc.createElement('div');
            btns.className = 'aiw-report-btns';

            acts.forEach(function (a) {
                var b = doc.createElement('button');
                b.type = 'button';
                b.className = 'aiw-btn';
                b.id = 'aiw-report-' + a.kind;
                b.textContent = a.label;
                b.addEventListener('click', function () {
                    if (a.kind === 'verify') {
                        if (typeof opts.onVerify === 'function') {
                            setResult('Pruefe Siegel \u2026', null);
                            opts.onVerify(r.user_id, r.report_id);
                        }
                        return;
                    }
                    if (typeof opts.onApprove === 'function') {
                        setResult('Schreibe \u2026', null);
                        opts.onApprove(r.user_id, r.report_id,
                                       a.kind === 'final');
                    }
                });
                btns.appendChild(b);
            });
            if (!acts.length) {
                var none = doc.createElement('div');
                none.className = 'aiw-placeholder';
                none.textContent = 'Keine Aktion verfuegbar '
                    + '(Status oder Berechtigung).';
                btns.appendChild(none);
            }
            panel.appendChild(btns);

            var res = doc.createElement('div');
            res.className = 'aiw-report-result';
            res.id = 'aiw-report-result';
            panel.appendChild(res);
        }

        // setResult: Rueckmeldung (Erfolg/Fehler/Siegelpruefung) im Aktionsfeld.
        function setResult(text, isError) {
            var res = panel.querySelector('#aiw-report-result');
            if (!res) { return; }
            res.textContent = text || '';
            res.classList.toggle('error', isError === true);
            res.classList.toggle('ok', isError === false);
        }

        // showVerify: Ergebnis der Siegelpruefung deutlich darstellen. Eine
        // ABWEICHUNG ist ein Manipulationsverdacht — sie wird nicht beschoenigt.
        function showVerify(v) {
            var res = panel.querySelector('#aiw-report-result');
            if (!res) { return; }
            res.textContent = '';
            res.classList.remove('error', 'ok');

            var line = doc.createElement('div');
            line.textContent = verifyText(v);
            line.className = (v && v.match === false) ? 'error'
                : (v && v.match === true ? 'ok' : '');
            res.appendChild(line);

            if (v && v.sealed) {
                var dl = doc.createElement('dl');
                dl.className = 'aiw-detail-dl';
                [['Siegel-Hash', v.sealed_sha256],
                 ['Aktueller Hash', v.current_sha256 || '\u2014'],
                 ['Freigegeben von', v.approved_by],
                 ['Freigegeben am', fmtTs(v.approved_at)],
                 ['Beleg (audit_seq)', v.audit_seq],
                 ['Endgueltig', v.is_final ? 'ja' : 'nein']
                ].forEach(function (p) {
                    var dt = doc.createElement('dt');
                    dt.textContent = p[0];
                    var dd = doc.createElement('dd');
                    dd.textContent = String(p[1] === undefined ? '' : p[1]);
                    dl.appendChild(dt);
                    dl.appendChild(dd);
                });
                res.appendChild(dl);
            }
        }

        // Statusfilter: lokal filtern (kein Server-Roundtrip noetig).
        sel.addEventListener('change', function () {
            var filtered = filterByStatus(rows, sel.value);
            if (typeof table.replaceData === 'function') {
                table.replaceData(filtered);
            }
            if (typeof opts.onFilter === 'function') {
                opts.onFilter(sel.value);
            }
            log('Statusfilter:', sel.value || '(alle)', '->',
                filtered.length, 'Zeilen');
        });

        log('renderReports:', rows.length, 'Berichte;',
            (data && data.rescanned), 'DBs neu eingelesen');
        // Die Shell braucht Zugriff auf das Aktionsfeld (Rueckmeldungen).
        table.aiwSelectRow = selectRow;
        table.aiwSetResult = setResult;
        table.aiwShowVerify = showVerify;
        return table;
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        STATUS_LABEL: STATUS_LABEL,
        TYPE_LABEL: TYPE_LABEL,
        fmtTs: fmtTs,
        toRows: toRows,
        filterByStatus: filterByStatus,
        statusCounts: statusCounts,
        scanInfoText: scanInfoText,
        availableActions: availableActions,
        verifyText: verifyText,
        renderReports: renderReports
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitReports = API; }
})();
