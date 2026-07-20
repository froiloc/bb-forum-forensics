// =============================================================================
// management/server/static/cockpit_onboarding.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Onboarding/Offboarding
// =============================================================================
// Zweck (Idee 31, Frontend zu Build 464):
//   Rendert die Onboarding-/Offboarding-Checkliste (/api/onboarding). Sie fuehrt
//   durch die belegpflichtigen Schritte bei Aufnahme/Ausscheiden einer
//   Mitarbeiter:in (Konto/Rolle/AD-Gruppe bzw. Rechte entziehen, Faelle
//   umverteilen, Zugang sperren). Ein vergessener Schritt (z. B. nicht entzogene
//   Rechte) waere ein Governance-Risiko — die Checkliste macht den Stand
//   sichtbar und belegt.
//
// Datenform GET /api/onboarding?person_id=N&kind=K (ManagementApp._onboarding):
//   {
//     person_id, person: {display_name, system_username},
//     kind, kind_label, kinds: ["onboarding","offboarding"],
//     counts: {offen, erledigt, nicht_zutreffend},
//     open_case_load: int,          // noch offen zugewiesene Faelle (Offboarding)
//     steps: [ {step_code, label, status, status_label, note, done_by, done_at,
//               requires_reason}, ... ]
//   }
//   data === null  -> es ist noch keine Person gewaehlt (nur die Auswahl zeigen).
//
// SCHREIBEN (opts -> cockpit.js -> postJson mit X-AIW-Token):
//   onLoad({personId, kind})  — Auswahl bestaetigt -> Sicht (neu) laden.
//   onStep({person_id, kind, step_code, status, note})  — Schritt setzen.
//   KEIN optimistisches UI: nach dem Schreiben laedt cockpit.js die Sicht NEU.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS: (1) IIFE + 'use strict'. (2) DEV-Logging
//   (AIW_COCKPIT_DEBUG). (3) ausfuehrliche Kommentare. (4) reine Funktionen
//   fassen NIE das DOM an -> vitest; opts.doc injizierbar (JSDOM).
// SICHERHEIT (XSS): alle variablen Texte via textContent.
//
// Version: v0.7.465 · Build: 465 · 2026-07-20
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
        args.unshift('[AIW-Onboarding]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';
    var KINDS = ['onboarding', 'offboarding'];
    var KIND_LABEL = {
        onboarding: 'Onboarding (Aufnahme)',
        offboarding: 'Offboarding (Ausscheiden)'
    };
    var STATUS_LABEL = {
        offen: 'offen', erledigt: 'erledigt', nicht_zutreffend: 'nicht zutreffend'
    };

    // ------------------------------------------------------------------ Helfer
    // statusDotClass: erledigt = gruen, nicht_zutreffend = grau (neutral,
    // beendet), offen = gelb (Handlungsbedarf). '.dot.grau' seit Build 463.
    function statusDotClass(status) {
        if (status === 'erledigt') { return 'gruen'; }
        if (status === 'nicht_zutreffend') { return 'grau'; }
        return 'gelb';
    }
    function statusLabel(status) { return STATUS_LABEL[status] || status; }

    // stepActions: die aus 'status' sinnvollen Ziel-Aktionen (der Server bleibt
    // die verbindliche Instanz; hier nur, um keinen No-op-Button zu zeigen).
    function stepActions(status) {
        var all = ['erledigt', 'nicht_zutreffend', 'offen'];
        return all.filter(function (s) { return s !== status; });
    }

    function stepRows(data) {
        return (data && Array.isArray(data.steps)) ? data.steps : [];
    }

    // =========================================================================
    // 1) DOM: Sicht rendern. data===null -> nur Auswahl (keine Checkliste).
    // =========================================================================
    function renderOnboarding(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return { setResult: function () {} }; }
        var canEdit = opts.canEdit === true;

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Onboarding / Offboarding';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Belegpflichtige Schritte bei Aufnahme und Ausscheiden '
            + 'einer Mitarbeiter:in. Jede Aenderung wird auditiert.';
        mainEl.appendChild(sub);

        // --- Auswahl (immer) -------------------------------------------------
        var curPerson = (data && data.person_id != null)
            ? String(data.person_id) : (opts.personId != null
                ? String(opts.personId) : '');
        var curKind = (data && data.kind) || opts.kind || 'onboarding';
        mainEl.appendChild(_selector(doc, curPerson, curKind, opts));

        // --- Ergebniszeile ---------------------------------------------------
        var result = doc.createElement('div');
        result.className = 'aiw-onb-result';
        result.id = 'aiw-onb-result';
        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }
        mainEl.appendChild(result);

        if (!data) {
            var hint = doc.createElement('p');
            hint.className = 'aiw-placeholder';
            hint.textContent = 'Bitte eine Person (user-/person_id) und eine '
                + 'Checkliste waehlen und „Anzeigen“ druecken.';
            mainEl.appendChild(hint);
            return { setResult: setResult };
        }

        // --- Kopf der Person + Kennzahlen ------------------------------------
        var head = doc.createElement('div');
        head.className = 'aiw-onb-head';
        var who = (data.person && data.person.display_name)
            ? data.person.display_name : ('Person ' + data.person_id);
        var sam = (data.person && data.person.system_username)
            ? (' [' + data.person.system_username + ']') : '';
        var strong = doc.createElement('strong');
        strong.textContent = who + sam + ' — ' + (data.kind_label || data.kind);
        head.appendChild(strong);
        mainEl.appendChild(head);

        var counts = doc.createElement('div');
        counts.className = 'aiw-onb-counts';
        ['offen', 'erledigt', 'nicht_zutreffend'].forEach(function (s) {
            var badge = doc.createElement('span');
            badge.className = 'aiw-badge aiw-onb-badge';
            var dot = doc.createElement('span');
            dot.className = 'dot ' + statusDotClass(s);
            badge.appendChild(dot);
            var t = doc.createElement('span');
            var n = (data.counts && data.counts[s] != null) ? data.counts[s] : 0;
            t.textContent = ' ' + statusLabel(s) + ': ' + n;
            badge.appendChild(t);
            counts.appendChild(badge);
        });
        mainEl.appendChild(counts);

        // Fall-Last (v. a. Offboarding): offene zugewiesene Faelle sichtbar
        // machen — der Schritt "Faelle umverteilt" wird damit konkret.
        if (data.open_case_load != null) {
            var load = doc.createElement('p');
            load.className = 'aiw-onb-load'
                + (data.open_case_load > 0 ? ' aiw-onb-load-warn' : '');
            load.textContent = 'Noch offen zugewiesene Faelle: '
                + data.open_case_load
                + (data.open_case_load > 0
                    ? ' — vor dem Offboarding umverteilen.' : '.');
            mainEl.appendChild(load);
        }

        if (!canEdit) {
            var ro = doc.createElement('p');
            ro.className = 'aiw-pagesub aiw-onb-readonly';
            ro.textContent = 'Nur lesend — zum Pflegen fehlt das Recht '
                + '„onboarding.edit“.';
            mainEl.appendChild(ro);
        }

        // --- Grund-Panel (fuer 'nicht_zutreffend') ---------------------------
        var panel = doc.createElement('div');
        panel.className = 'aiw-onb-panel';
        panel.id = 'aiw-onb-panel';
        mainEl.appendChild(panel);
        function closePanel() { panel.textContent = ''; }

        function fire(step, status, note) {
            closePanel();
            setResult('Speichere Schritt …', null);
            if (typeof opts.onStep === 'function') {
                opts.onStep({
                    person_id: data.person_id, kind: data.kind,
                    step_code: step.step_code, status: status, note: note || ''
                });
            } else {
                setResult('Kein Schreibpfad verdrahtet.', true);
            }
        }

        function openReason(step) {
            panel.textContent = '';
            var title = doc.createElement('div');
            title.className = 'aiw-onb-panel-title';
            title.textContent = 'Schritt „' + (step.label || step.step_code)
                + '“ als nicht zutreffend markieren';
            panel.appendChild(title);

            var lbl = doc.createElement('label');
            lbl.className = 'aiw-onb-lbl';
            lbl.textContent = 'Grund (Pflicht): ';
            var inG = doc.createElement('input');
            inG.type = 'text';
            inG.id = 'aiw-onb-reason';
            inG.className = 'aiw-onb-input';
            lbl.appendChild(inG);
            panel.appendChild(lbl);

            var ok = doc.createElement('button');
            ok.type = 'button';
            ok.id = 'aiw-onb-reason-confirm';
            ok.className = 'aiw-btn aiw-onb-btn';
            ok.textContent = 'Bestaetigen';
            ok.addEventListener('click', function () {
                var grund = (inG.value || '').trim();
                if (!grund) {
                    setResult('Grund ist Pflicht: ein Schritt darf nicht ohne '
                        + 'nachvollziehbaren Grund als „nicht zutreffend“ '
                        + 'markiert werden.', true);
                    return;
                }
                fire(step, 'nicht_zutreffend', grund);
            });
            panel.appendChild(ok);

            var cancel = doc.createElement('button');
            cancel.type = 'button';
            cancel.id = 'aiw-onb-reason-cancel';
            cancel.className = 'aiw-btn aiw-onb-btn';
            cancel.textContent = 'Abbrechen';
            cancel.addEventListener('click', function () {
                closePanel();
                setResult('Abgebrochen.', false);
            });
            panel.appendChild(cancel);
        }

        // --- Tabelle ---------------------------------------------------------
        var rows = stepRows(data);
        var table = doc.createElement('table');
        table.className = 'aiw-onb-table';
        var thead = doc.createElement('thead');
        var htr = doc.createElement('tr');
        ['Schritt', 'Zustand', 'Notiz', 'Aktion'].forEach(function (label) {
            var th = doc.createElement('th');
            th.textContent = label;
            htr.appendChild(th);
        });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = doc.createElement('tbody');
        rows.forEach(function (step) {
            tbody.appendChild(_rowEl(doc, step, canEdit, fire, openReason));
        });
        table.appendChild(tbody);
        mainEl.appendChild(table);

        log('renderOnboarding:', rows.length, 'Schritte, canEdit', canEdit);
        return { setResult: setResult };
    }

    // _selector: Personen-/Checklisten-Auswahl. person_id als Zahl-Eingabe
    // (kein zusaetzlicher Endpunkt noetig); kind als Auswahl.
    function _selector(doc, curPerson, curKind, opts) {
        var box = doc.createElement('div');
        box.className = 'aiw-onb-select';

        var lblP = doc.createElement('label');
        lblP.className = 'aiw-onb-lbl';
        lblP.textContent = 'Person (person_id): ';
        var inP = doc.createElement('input');
        inP.type = 'text';
        inP.id = 'aiw-onb-person';
        inP.className = 'aiw-onb-input';
        inP.value = curPerson || '';
        lblP.appendChild(inP);
        box.appendChild(lblP);

        var lblK = doc.createElement('label');
        lblK.className = 'aiw-onb-lbl';
        lblK.textContent = 'Checkliste: ';
        var selK = doc.createElement('select');
        selK.id = 'aiw-onb-kind';
        selK.className = 'aiw-onb-input';
        KINDS.forEach(function (k) {
            var o = doc.createElement('option');
            o.value = k;
            o.textContent = KIND_LABEL[k];
            if (k === curKind) { o.selected = true; }
            selK.appendChild(o);
        });
        lblK.appendChild(selK);
        box.appendChild(lblK);

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-onb-show';
        btn.className = 'aiw-btn aiw-onb-btn';
        btn.textContent = 'Anzeigen';
        btn.addEventListener('click', function () {
            var raw = (inP.value || '').trim();
            var pid = parseInt(raw, 10);
            if (!raw || isNaN(pid) || String(pid) !== raw) {
                if (typeof opts.onInvalid === 'function') {
                    opts.onInvalid('person_id fehlt oder ist keine ganze Zahl.');
                }
                return;
            }
            if (typeof opts.onLoad === 'function') {
                opts.onLoad({ personId: pid, kind: selK.value });
            }
        });
        box.appendChild(btn);
        return box;
    }

    // _rowEl: eine Schritt-Zeile mit ihren zulaessigen Aktions-Buttons.
    function _rowEl(doc, step, canEdit, fire, openReason) {
        var tr = doc.createElement('tr');
        tr.setAttribute('data-step', step.step_code);

        var tdS = doc.createElement('td');
        tdS.textContent = step.label || step.step_code;
        tr.appendChild(tdS);

        var tdStatus = doc.createElement('td');
        var dot = doc.createElement('span');
        dot.className = 'dot ' + statusDotClass(step.status);
        tdStatus.appendChild(dot);
        var stx = doc.createElement('span');
        stx.textContent = ' ' + (step.status_label || statusLabel(step.status));
        tdStatus.appendChild(stx);
        tr.appendChild(tdStatus);

        var tdNote = doc.createElement('td');
        tdNote.textContent = step.note || EM_DASH;
        tr.appendChild(tdNote);

        var tdAct = doc.createElement('td');
        tdAct.className = 'aiw-onb-actions';
        if (canEdit) {
            stepActions(step.status).forEach(function (target) {
                var b = doc.createElement('button');
                b.type = 'button';
                b.className = 'aiw-btn aiw-onb-btn';
                b.setAttribute('data-step', step.step_code);
                b.setAttribute('data-target', target);
                b.textContent = (target === 'erledigt') ? 'Erledigt'
                    : (target === 'nicht_zutreffend') ? 'Nicht zutreffend'
                        : 'Zuruecksetzen';
                b.addEventListener('click', function () {
                    // 'nicht_zutreffend' braucht einen Grund -> Panel; sonst
                    // sofort feuern (erledigt/offen).
                    if (target === 'nicht_zutreffend') {
                        openReason(step);
                    } else {
                        fire(step, target, '');
                    }
                });
                tdAct.appendChild(b);
            });
        } else {
            tdAct.textContent = EM_DASH;
        }
        tr.appendChild(tdAct);
        return tr;
    }

    // =========================================================================
    // 2) UMD-Ausgang.
    // =========================================================================
    var API = {
        statusDotClass: statusDotClass,
        statusLabel: statusLabel,
        stepActions: stepActions,
        stepRows: stepRows,
        renderOnboarding: renderOnboarding,
        KINDS: KINDS
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitOnboarding = API; }
})();
