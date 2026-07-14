/**
 * management/server/static/cockpit_approval.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Vermaehlung B6xB7 — W5 (Chef-Freigabe), SLICE 1 (Build 416)
 *
 * Zweck:
 *   Integrierte Freigabe-Sicht der Chef-Ermittlerin (Recht reports.approve):
 *   den vorgelegten Bericht LESEN, das Siegel PRUEFEN und FREIGEBEN/ZURUECK-
 *   WEISEN. SLICE 1 liefert Auswahl + read-only Berichtstext (SF-1) + Aktionen
 *   (approve/return/verify, bestehende Endpunkte). Belege (SF-2), Kommentare
 *   (SF-3, read-only) und das Ergebnis-Mitpruefen (results) folgen in den
 *   naechsten Slices.
 *
 * Abgrenzung zur "Berichts-Abnahme" (cockpit_reports.js): jene ist eine
 *   Metadaten-Tabelle mit denselben Aktionen; DIESE Sicht stellt den
 *   BERICHTSTEXT in den Mittelpunkt (lesen, dann entscheiden).
 *
 * JS-Gebote: IIFE + 'use strict'; DEV-Logging (DEV=false fuer PROD);
 *   ausfuehrliche Kommentare; Kapselung (Closure-Zustand, kleine API);
 *   REINE Funktionen separat exportiert (vitest). Self-contained (eigene
 *   kleine Helfer — Repo-Konvention: jede Cockpit-Sicht ist unabhaengig).
 *
 * Version: v0.7.416 · Build: 416 · 2026-07-14
 */
(function () {
    'use strict';

    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[approval]');
            console.log.apply(console, a);
        }
    }

    var _state = {
        iframe: null,       // Berichtstext-<iframe>
        selKey: null,       // gewaehlter Bericht ('uid:rid')
        actionPanel: null,  // Aktionsbereich (Freigabe/Rueckgabe/Pruefung)
        verifyBox: null     // Ausgabe der Siegelpruefung
    };

    // =====================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — vitest.
    // =====================================================================

    function statusLabel(status) {
        switch (status) {
            case 'draft':     return 'Entwurf';
            case 'submitted': return 'Zur Abnahme vorgelegt';
            case 'approved':  return 'Freigegeben';
            case 'final':     return 'Versandt/abgeschlossen';
            default:          return status || 'unbekannt';
        }
    }

    // filterReports: Berichte je Status; 'alle' -> alle. Neues Array.
    function filterReports(data, status) {
        var list = (data && data.reports) ? data.reports : [];
        if (!status || status === 'alle') { return list.slice(); }
        return list.filter(function (r) { return r && r.status === status; });
    }

    function renderUrl(uid, rid) {
        return '/api/report/render?user_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }

    function reportLabel(r) {
        if (!r) { return ''; }
        return (r.username || ('uid ' + r.user_id)) + ' · '
            + (r.title || '(ohne Titel)')
            + ' (' + (r.report_type || '?') + ', Nr. ' + (r.sequence_nr || '?')
            + ') — ' + statusLabel(r.status);
    }

    function selectionKey(uid, rid) { return String(uid) + ':' + String(rid); }

    // canApprove/canVerify: Aktionslogik anhand des Berichtsstatus (mc/Build
    // 378/380). Freigeben/Zurueckweisen NUR bei 'submitted'; Siegelpruefung
    // bei 'approved'/'final' (dort existiert ein Siegel).
    function canApprove(status) { return status === 'submitted'; }
    function canVerify(status) {
        return status === 'approved' || status === 'final';
    }

    // verifyText: Klartext zum Pruefergebnis. Eine ABWEICHUNG wird als
    // Manipulationsverdacht beim Namen genannt (Grundregel 1). Deckungsgleich
    // zur Formulierung in cockpit_reports.js:verifyText.
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

    // =====================================================================
    // 2) DOM.
    // =====================================================================

    function cleanup() {
        _state.iframe = null;
        _state.selKey = null;
        _state.actionPanel = null;
        _state.verifyBox = null;
        log('cleanup');
    }

    function _actionHint(msg) {
        if (!_state.actionPanel) { return; }
        _state.actionPanel.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'aiw-approval-hint';
        p.textContent = msg;
        _state.actionPanel.appendChild(p);
    }

    // renderVerify(result): Ergebnis der Siegelpruefung im verifyBox anzeigen.
    function renderVerify(result) {
        if (!_state.verifyBox) { return; }
        _state.verifyBox.textContent = verifyText(result);
        _state.verifyBox.setAttribute('data-match',
            result && result.match === true ? 'ok'
            : (result && result.sealed ? 'mismatch' : 'unsealed'));
    }
    function verifyLoading() {
        if (_state.verifyBox) { _state.verifyBox.textContent = 'Pruefe Siegel …'; }
    }
    function verifyError(msg) {
        if (_state.verifyBox) {
            _state.verifyBox.textContent = 'Siegelpruefung fehlgeschlagen: '
                + (msg || 'Fehler');
        }
    }

    // _buildActionPanel: fuellt den Aktionsbereich fuer EINEN gewaehlten
    // Bericht r. opts.canApprove (bool) kommt aus der Policy (Scope 'alle').
    function _buildActionPanel(r, opts) {
        var panel = _state.actionPanel;
        panel.innerHTML = '';

        var st = document.createElement('p');
        st.className = 'aiw-approval-statusline';
        st.textContent = 'Status: ' + statusLabel(r.status);
        panel.appendChild(st);

        // Siegelpruefung (immer anbietbar; das Ergebnis erklaert den Fall).
        var vbtn = document.createElement('button');
        vbtn.type = 'button';
        vbtn.className = 'aiw-approval-verify';
        vbtn.textContent = 'Siegel pruefen';
        vbtn.addEventListener('click', function () {
            verifyLoading();
            if (typeof opts.onVerify === 'function') {
                opts.onVerify(r.user_id, r.id);
            }
        });
        panel.appendChild(vbtn);

        var vbox = document.createElement('div');
        vbox.className = 'aiw-approval-verifybox';
        _state.verifyBox = vbox;
        panel.appendChild(vbox);

        if (r.status !== 'submitted') {
            var hint = document.createElement('p');
            hint.className = 'aiw-approval-hint';
            hint.textContent = 'Nur vorgelegte Berichte ("Zur Abnahme '
                + 'vorgelegt") koennen freigegeben oder zurueckgewiesen werden.';
            panel.appendChild(hint);
            return;
        }

        if (!opts.canApprove) {
            var noperm = document.createElement('p');
            noperm.className = 'aiw-approval-hint';
            noperm.textContent = 'Zum Freigeben wird das Recht reports.approve '
                + '(Scope „alle") benoetigt.';
            panel.appendChild(noperm);
            return;
        }

        // --- Freigabe ---------------------------------------------------
        var appBox = document.createElement('div');
        appBox.className = 'aiw-approval-approve';

        var noteA = document.createElement('textarea');
        noteA.className = 'aiw-approval-note';
        noteA.setAttribute('rows', '2');
        noteA.setAttribute('placeholder', 'Freigabevermerk (optional)');
        appBox.appendChild(noteA);

        var finalLbl = document.createElement('label');
        finalLbl.className = 'aiw-approval-final';
        var finalCb = document.createElement('input');
        finalCb.type = 'checkbox';
        finalCb.className = 'aiw-approval-isfinal';
        finalLbl.appendChild(finalCb);
        finalLbl.appendChild(document.createTextNode(
            ' Als Abschlussbericht/versandt kennzeichnen (is_final)'));
        appBox.appendChild(finalLbl);

        var appBtn = document.createElement('button');
        appBtn.type = 'button';
        appBtn.className = 'aiw-approval-approvebtn';
        appBtn.textContent = 'Freigeben & versiegeln';
        appBtn.addEventListener('click', function () {
            var body = {
                user_id: r.user_id, report_id: r.id,
                is_final: !!finalCb.checked,
                note: (noteA.value || '').trim() || null
            };
            log('approve', body);
            if (typeof opts.onApprove === 'function') { opts.onApprove(body); }
        });
        appBox.appendChild(appBtn);
        panel.appendChild(appBox);

        // --- Rueckgabe zur Nachbesserung --------------------------------
        var retBox = document.createElement('div');
        retBox.className = 'aiw-approval-return';
        var retNote = document.createElement('textarea');
        retNote.className = 'aiw-approval-returnnote';
        retNote.setAttribute('rows', '2');
        retNote.setAttribute('placeholder', 'Grund der Rueckweisung (optional)');
        retBox.appendChild(retNote);
        var retBtn = document.createElement('button');
        retBtn.type = 'button';
        retBtn.className = 'aiw-approval-returnbtn';
        retBtn.textContent = 'Zurueckweisen (an Entwurf)';
        retBtn.addEventListener('click', function () {
            var body = {
                user_id: r.user_id, report_id: r.id,
                note: (retNote.value || '').trim() || null
            };
            log('return', body);
            if (typeof opts.onReturn === 'function') { opts.onReturn(body); }
        });
        retBox.appendChild(retBtn);
        panel.appendChild(retBox);
    }

    // renderApproval(mainEl, data, opts)
    //   data — /api/reports (reports[], scope, ...).
    //   opts — { status?, canApprove?, onApprove, onReturn, onVerify }
    function renderApproval(mainEl, data, opts) {
        opts = opts || {};
        var status = opts.status || 'submitted';
        log('renderApproval', { status: status, count: (data && data.count) });

        mainEl.innerHTML = '';
        _state.iframe = null;
        _state.selKey = null;
        _state.actionPanel = null;
        _state.verifyBox = null;

        var wrap = document.createElement('div');
        wrap.className = 'aiw-approval';

        var h = document.createElement('h2');
        h.textContent = 'Chef-Freigabe — Berichte abnehmen';
        wrap.appendChild(h);

        var meta = document.createElement('p');
        meta.className = 'aiw-approval-meta';
        meta.textContent = 'Sichtbarer Umfang: ' + ((data && data.scope)
            || 'unbekannt') + '. Freigabe & Versiegelung sind unwiderruflich; '
            + 'inhaltliche Maengel gehen als Rueckweisung an den Entwurf zurueck.';
        wrap.appendChild(meta);

        // Statusfilter (Vorgabe 'submitted').
        var bar = document.createElement('div');
        bar.className = 'aiw-approval-toolbar';
        var lbl = document.createElement('label');
        lbl.textContent = 'Status: ';
        var sel = document.createElement('select');
        sel.className = 'aiw-approval-status';
        [['submitted', 'Zur Abnahme vorgelegt'], ['approved', 'Freigegeben'],
         ['final', 'Versandt'], ['draft', 'Entwurf'], ['alle', 'Alle']]
            .forEach(function (o) {
                var opt = document.createElement('option');
                opt.value = o[0]; opt.textContent = o[1];
                if (o[0] === status) { opt.selected = true; }
                sel.appendChild(opt);
            });
        sel.addEventListener('change', function () {
            renderApproval(mainEl, data, {
                status: sel.value, canApprove: opts.canApprove,
                onApprove: opts.onApprove, onReturn: opts.onReturn,
                onVerify: opts.onVerify
            });
        });
        lbl.appendChild(sel);
        bar.appendChild(lbl);
        wrap.appendChild(bar);

        // Auswahl-Liste.
        var rows = filterReports(data, status);
        var list = document.createElement('div');
        list.className = 'aiw-approval-list';
        if (!rows.length) {
            var empty = document.createElement('p');
            empty.className = 'aiw-approval-empty';
            empty.textContent = 'Keine Berichte im gewaehlten Status.';
            list.appendChild(empty);
        }

        // Vorschau-Bereich: Berichtstext + Aktionen.
        var preview = document.createElement('div');
        preview.className = 'aiw-approval-preview-wrap';
        var frame = document.createElement('iframe');
        frame.className = 'aiw-approval-preview';
        frame.title = 'Berichtstext (read-only)';
        frame.setAttribute('sandbox', 'allow-same-origin');
        _state.iframe = frame;

        var action = document.createElement('div');
        action.className = 'aiw-approval-action';
        _state.actionPanel = action;
        _actionHint('Bericht links auswaehlen, um ihn zu lesen und zu '
            + 'entscheiden.');

        preview.appendChild(frame);
        preview.appendChild(action);

        rows.forEach(function (r) {
            var key = selectionKey(r.user_id, r.id);
            var row = document.createElement('button');
            row.type = 'button';
            row.className = 'aiw-approval-item';
            row.setAttribute('data-uid', String(r.user_id));
            row.setAttribute('data-rid', String(r.id));
            row.setAttribute('data-key', key);
            row.textContent = reportLabel(r);
            row.addEventListener('click', function () {
                var prev = list.querySelector('.aiw-approval-item.is-active');
                if (prev) { prev.classList.remove('is-active'); }
                row.classList.add('is-active');
                _state.selKey = key;
                frame.src = renderUrl(r.user_id, r.id);
                _buildActionPanel(r, opts);
                log('select', key, frame.src);
            });
            list.appendChild(row);
        });

        wrap.appendChild(list);
        wrap.appendChild(preview);
        mainEl.appendChild(wrap);
        return wrap;
    }

    window.AIWCockpitApproval = {
        // reine Funktionen (vitest)
        statusLabel: statusLabel,
        filterReports: filterReports,
        renderUrl: renderUrl,
        reportLabel: reportLabel,
        selectionKey: selectionKey,
        canApprove: canApprove,
        canVerify: canVerify,
        verifyText: verifyText,
        // DOM
        renderApproval: renderApproval,
        renderVerify: renderVerify,
        verifyLoading: verifyLoading,
        verifyError: verifyError,
        cleanup: cleanup
    };
    log('Modul geladen.');
})();
