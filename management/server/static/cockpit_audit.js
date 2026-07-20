// =============================================================================
// management/server/static/cockpit_audit.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Audit-Explorer
// =============================================================================
// Zweck (Idee 24, Frontend zu Build 467, AP-2E):
//   Rendert den durchblaetterbaren, filterbaren Audit-/Revisions-Explorer
//   (/api/audit) ueber den hash-verketteten, append-only audit_log. Zusaetzlich
//   ein Knopf "Gerichtsfester Export" (/api/audit/export) — ein self-contained,
//   geprüfsummtes HTML mit Erzeugungsvermerk + Integritaets-Kettenspitze.
//
//   REIN LESEND: es gibt keinen Schreibpfad (der audit_log ist per Trigger
//   append-only). Recht: ops.view (wie die Integritaets-Sicht).
//
// Datenform:
//   GET /api/audit?<filter>&limit=&offset=
//     -> {total, rows:[{seq,ts,actor_id,event_type,target_type,target_id,
//                        content,row_hash,actor_name,actor_username}],
//         limit, offset, has_more}
//   GET /api/audit/facets -> {event_types:[...], actors:[{actor_id,actor_name,
//                                                          actor_username}]}
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS: (1) IIFE + 'use strict'. (2) DEV-Logging.
//   (3) ausfuehrliche Kommentare. (4) reine Funktionen fassen NIE das DOM an
//   -> vitest; opts.doc injizierbar. SICHERHEIT: alle Werte via textContent.
//
// Version: v0.7.467 · Build: 467 · 2026-07-20
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
        args.unshift('[AIW-Audit]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';
    //: Filter-Felder, die in die Query/den Export-Link einfliessen.
    var FILTER_KEYS = ['event_type', 'actor_id', 'target_type', 'target_id',
                       'seq_from', 'seq_to'];

    // ------------------------------------------------------------------ Helfer
    // fmtTs: Epoch -> lesbarer UTC-Zeitstempel (deterministisch, gerichtstauglich).
    function fmtTs(ts) {
        var n = parseInt(ts, 10);
        if (isNaN(n)) { return String(ts); }
        var d = new Date(n * 1000);
        // ISO ohne Millisekunden, 'Z' -> ' UTC'.
        return d.toISOString().replace('T', ' ').replace(/\..+Z$/, ' UTC');
    }

    // payloadShort: Kurzform des JSON-Payloads fuer die Tabellenzelle.
    function payloadShort(content, max) {
        max = max || 90;
        var s = (content == null) ? '' : String(content);
        return (s.length > max) ? (s.slice(0, max) + '…') : s;
    }

    // targetLabel: 'typ/id' oder eines von beiden.
    function targetLabel(row) {
        var t = row.target_type || '';
        if (row.target_id != null && row.target_id !== '') {
            return t ? (t + '/' + row.target_id) : String(row.target_id);
        }
        return t || EM_DASH;
    }

    // actorLabel: Anzeigename (Kennung) oder Ersatz.
    function actorLabel(row) {
        if (row.actor_name && row.actor_username) {
            return row.actor_name + ' (' + row.actor_username + ')';
        }
        if (row.actor_username) { return String(row.actor_username); }
        if (row.actor_id != null) { return 'id=' + row.actor_id; }
        return EM_DASH;
    }

    // buildQuery: Filter -> Query-String (leere Werte weggelassen). Fuer den
    // Export-Link, damit dieser EXAKT die angewandten Filter traegt.
    function buildQuery(filters, extra) {
        var f = filters || {};
        var parts = [];
        FILTER_KEYS.forEach(function (k) {
            var v = f[k];
            if (v != null && String(v).trim() !== '') {
                parts.push(encodeURIComponent(k) + '='
                    + encodeURIComponent(String(v).trim()));
            }
        });
        var e = extra || {};
        Object.keys(e).forEach(function (k) {
            if (e[k] != null && e[k] !== '') {
                parts.push(encodeURIComponent(k) + '='
                    + encodeURIComponent(String(e[k])));
            }
        });
        return parts.join('&');
    }

    function rows(data) {
        return (data && Array.isArray(data.rows)) ? data.rows : [];
    }

    // =========================================================================
    // 1) DOM: Sicht rendern.
    // =========================================================================
    function renderAudit(mainEl, data, facets, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return { setResult: function () {} }; }
        data = data || {};
        facets = facets || {};
        var filters = opts.filters || {};

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Audit-/Revisions-Explorer';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Durchsicht des hash-verketteten, append-only '
            + 'Audit-Logs. Rein lesend; der gerichtsfeste Export traegt '
            + 'Pruefsumme und Integritaets-Kettenspitze.';
        mainEl.appendChild(sub);

        // --- Filterleiste ----------------------------------------------------
        var bar = doc.createElement('div');
        bar.className = 'aiw-audit-bar';

        var selEvent = _select(doc, 'aiw-audit-event', 'Ereignis',
            [['', 'alle Ereignisse']].concat(
                (facets.event_types || []).map(function (e) {
                    return [e, e];
                })), filters.event_type);
        bar.appendChild(selEvent.label);

        var selActor = _select(doc, 'aiw-audit-actor', 'Akteur',
            [['', 'alle Akteure']].concat(
                (facets.actors || []).map(function (a) {
                    var lbl = (a.actor_name || ('id=' + a.actor_id))
                        + (a.actor_username ? ' (' + a.actor_username + ')' : '');
                    return [String(a.actor_id), lbl];
                })), filters.actor_id != null ? String(filters.actor_id) : '');
        bar.appendChild(selActor.label);

        var inTt = _input(doc, 'aiw-audit-tt', 'Ziel-Typ', filters.target_type);
        bar.appendChild(inTt.label);
        var inFrom = _input(doc, 'aiw-audit-from', 'seq ab', filters.seq_from);
        bar.appendChild(inFrom.label);
        var inTo = _input(doc, 'aiw-audit-to', 'seq bis', filters.seq_to);
        bar.appendChild(inTo.label);

        function currentFilters() {
            return {
                event_type: selEvent.el.value,
                actor_id: selActor.el.value,
                target_type: (inTt.el.value || '').trim(),
                seq_from: (inFrom.el.value || '').trim(),
                seq_to: (inTo.el.value || '').trim()
            };
        }

        var btnFilter = doc.createElement('button');
        btnFilter.type = 'button';
        btnFilter.id = 'aiw-audit-filter';
        btnFilter.className = 'aiw-btn aiw-audit-btn';
        btnFilter.textContent = 'Filtern';
        btnFilter.addEventListener('click', function () {
            if (typeof opts.onFilter === 'function') {
                opts.onFilter(currentFilters());
            }
        });
        bar.appendChild(btnFilter);

        // Gerichtsfester Export: Link mit den ANGEWANDTEN Filtern (opts.filters),
        // damit der Export exakt die gezeigte Auswahl abbildet.
        var exp = doc.createElement('a');
        exp.id = 'aiw-audit-export';
        exp.className = 'aiw-btn aiw-audit-btn aiw-audit-export';
        exp.textContent = 'Gerichtsfester Export';
        exp.setAttribute('target', '_blank');
        exp.setAttribute('rel', 'noopener');
        var qs = buildQuery(filters);
        exp.setAttribute('href', '/api/audit/export' + (qs ? ('?' + qs) : ''));
        bar.appendChild(exp);

        mainEl.appendChild(bar);

        // --- Trefferzeile + Seiten-Navigation --------------------------------
        var total = data.total || 0;
        var limit = data.limit || 50;
        var offset = data.offset || 0;
        var info = doc.createElement('div');
        info.className = 'aiw-audit-info';
        var von = total === 0 ? 0 : (offset + 1);
        var bis = Math.min(offset + rows(data).length, total);
        info.textContent = total + ' Treffer — Zeige ' + von + '–' + bis + '.';
        mainEl.appendChild(info);

        // --- Tabelle ---------------------------------------------------------
        if (!rows(data).length) {
            var none = doc.createElement('p');
            none.className = 'aiw-placeholder';
            none.textContent = 'Keine Audit-Eintraege fuer diese Filter.';
            mainEl.appendChild(none);
        } else {
            var table = doc.createElement('table');
            table.className = 'aiw-audit-table';
            var thead = doc.createElement('thead');
            var htr = doc.createElement('tr');
            ['seq', 'Zeit (UTC)', 'Akteur', 'Ereignis', 'Ziel', 'Payload']
                .forEach(function (label) {
                    var th = doc.createElement('th');
                    th.textContent = label;
                    htr.appendChild(th);
                });
            thead.appendChild(htr);
            table.appendChild(thead);
            var tbody = doc.createElement('tbody');
            rows(data).forEach(function (r) {
                tbody.appendChild(_rowEl(doc, r));
            });
            table.appendChild(tbody);
            mainEl.appendChild(table);
        }

        // --- Blaettern -------------------------------------------------------
        var nav = doc.createElement('div');
        nav.className = 'aiw-audit-nav';
        var prev = doc.createElement('button');
        prev.type = 'button';
        prev.id = 'aiw-audit-prev';
        prev.className = 'aiw-btn aiw-audit-btn';
        prev.textContent = '‹ Neuere';
        prev.disabled = (offset <= 0);
        prev.addEventListener('click', function () {
            if (typeof opts.onPage === 'function') {
                opts.onPage(Math.max(0, offset - limit));
            }
        });
        nav.appendChild(prev);
        var next = doc.createElement('button');
        next.type = 'button';
        next.id = 'aiw-audit-next';
        next.className = 'aiw-btn aiw-audit-btn';
        next.textContent = 'Aeltere ›';
        next.disabled = !data.has_more;
        next.addEventListener('click', function () {
            if (typeof opts.onPage === 'function') {
                opts.onPage(offset + limit);
            }
        });
        nav.appendChild(next);
        mainEl.appendChild(nav);

        log('renderAudit:', rows(data).length, 'von', total);
        return { setResult: function () {} };
    }

    // _select/_input: kleine beschriftete Steuerelemente (Wert via value gesetzt).
    function _select(doc, id, labelText, options, selected) {
        var label = doc.createElement('label');
        label.className = 'aiw-audit-lbl';
        label.textContent = labelText + ': ';
        var sel = doc.createElement('select');
        sel.id = id;
        sel.className = 'aiw-audit-input';
        options.forEach(function (pair) {
            var o = doc.createElement('option');
            o.value = pair[0];
            o.textContent = pair[1];
            if (String(selected || '') === String(pair[0])) {
                o.selected = true;
            }
            sel.appendChild(o);
        });
        label.appendChild(sel);
        return { label: label, el: sel };
    }

    function _input(doc, id, labelText, value) {
        var label = doc.createElement('label');
        label.className = 'aiw-audit-lbl';
        label.textContent = labelText + ': ';
        var inp = doc.createElement('input');
        inp.type = 'text';
        inp.id = id;
        inp.className = 'aiw-audit-input aiw-audit-input-s';
        if (value != null) { inp.value = String(value); }
        label.appendChild(inp);
        return { label: label, el: inp };
    }

    function _rowEl(doc, r) {
        var tr = doc.createElement('tr');
        tr.setAttribute('data-seq', String(r.seq));
        [String(r.seq), fmtTs(r.ts), actorLabel(r),
         String(r.event_type || ''), targetLabel(r), payloadShort(r.content)]
            .forEach(function (val, i) {
                var td = doc.createElement('td');
                if (i === 5) { td.className = 'aiw-audit-payload'; }
                td.textContent = val;
                tr.appendChild(td);
            });
        return tr;
    }

    // =========================================================================
    // 2) UMD-Ausgang.
    // =========================================================================
    var API = {
        fmtTs: fmtTs,
        payloadShort: payloadShort,
        targetLabel: targetLabel,
        actorLabel: actorLabel,
        buildQuery: buildQuery,
        rows: rows,
        renderAudit: renderAudit,
        FILTER_KEYS: FILTER_KEYS
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitAudit = API; }
})();
