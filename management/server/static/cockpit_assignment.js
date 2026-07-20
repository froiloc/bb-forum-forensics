// =============================================================================
// management/server/static/cockpit_assignment.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Zuweisung
// =============================================================================
// Zweck:
//   Erste SCHREIB-Sicht des Cockpits (/api/assignable + POST /api/case/*).
//   Zeigt alle Faelle mit Ermittler-Zuordnung, Prioritaet und Status; jede
//   Zelle ist per Auswahlfeld aenderbar. Jede Aenderung geht als POST an den
//   auditierten Schreibpfad (Build 372) und erzeugt serverseitig zwingend
//   einen audit_log-Beleg. Die Antwort (audit_seq) wird als Bestaetigung
//   angezeigt — der Ermittler sieht, DASS und WOMIT belegt wurde.
//
// SCHREIB-TOKEN: Der Server liefert pro Lauf ein Token ueber GET /api/whoami.
//   Es MUSS bei jedem POST im Header 'X-AIW-Token' mitgeschickt werden; das
//   Cockpit reicht es aus der Shell (cockpit.js) durch.
//
// KEIN OPTIMISTISCHES UI (bewusst): In einem forensischen Werkzeug darf die
//   Oberflaeche NIE einen Zustand zeigen, der nicht bestaetigt geschrieben ist.
//   Wir schreiben, warten auf die Server-Antwort und laden dann neu. Fehler
//   werden sichtbar gemeldet, nie still verschluckt (Grundregel 1).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging. 3) Ausfuehrliche Kommentare.
//   4) Reine Funktionen (toRows/investigatorOptions/changeRequest) -> vitest
//   testet den ECHTEN Code; DOM/Netz nur in renderAssignment (Callbacks
//   injizierbar).
//
// XSS: nur textContent / Option.text (kein innerHTML).
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
        args.unshift('[AIW-Zuweisung]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var STATUS_LABEL = {
        open: 'offen',
        in_progress: 'in Arbeit',
        approved: 'freigegeben',
        closed: 'abgeschlossen'
    };

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    function assigneeLabel(c, investigators) {
        if (c.assigned_to === null || c.assigned_to === undefined) {
            return '(nicht zugewiesen)';
        }
        if (c.assigned_display_name) { return c.assigned_display_name; }
        var hit = (investigators || []).filter(function (i) {
            return i.person_id === c.assigned_to;
        })[0];
        return hit ? hit.display_name : ('#' + c.assigned_to);
    }

    // toRows: /api/assignable -> Zeilen fuer die Tabelle.
    function toRows(data) {
        var inv = (data && data.investigators) || [];
        return ((data && data.cases) || []).map(function (c) {
            return {
                subject_id: c.subject_id,
                username: c.username,
                assigned_to: (c.assigned_to === undefined
                    ? null : c.assigned_to),
                assignee: assigneeLabel(c, inv),
                priority: c.priority,
                status: c.status,
                status_label: STATUS_LABEL[c.status] || c.status
            };
        });
    }

    // investigatorOptions: Auswahl-Eintraege inkl. Last und "entziehen".
    function investigatorOptions(data) {
        var opts = [{ value: '', label: '(nicht zugewiesen)' }];
        ((data && data.investigators) || []).forEach(function (i) {
            opts.push({
                value: String(i.person_id),
                label: (i.display_name || i.system_username)
                    + ' (' + i.case_count + ')'
            });
        });
        return opts;
    }

    // changeRequest: baut die Schreibanforderung (Pfad + Rumpf) fuer eine
    // Aenderung. Rein -> in vitest pruefbar, ohne Netz.
    function changeRequest(kind, subjectId, value) {
        if (kind === 'assign') {
            return {
                path: '/api/case/assign',
                body: {
                    subject_id: subjectId,
                    // '' -> null (Zuweisung entziehen)
                    person_id: (value === '' || value === null)
                        ? null : parseInt(value, 10)
                }
            };
        }
        if (kind === 'priority') {
            return {
                path: '/api/case/priority',
                body: { subject_id: subjectId, priority: parseInt(value, 10) }
            };
        }
        if (kind === 'status') {
            return {
                path: '/api/case/status',
                body: { subject_id: subjectId, status: value }
            };
        }
        return null;   // unbekannte Aenderungsart -> Aufrufer meldet Fehler
    }

    // =========================================================================
    // 2) DOM/RENDER.
    // =========================================================================

    function _select(doc, options, current, onChange) {
        var sel = doc.createElement('select');
        sel.className = 'aiw-cell-select';
        options.forEach(function (o) {
            var op = doc.createElement('option');
            op.value = o.value;
            op.text = o.label;               // text -> kein innerHTML
            if (String(current) === String(o.value)) { op.selected = true; }
            sel.appendChild(op);
        });
        sel.addEventListener('change', function () { onChange(sel.value); });
        return sel;
    }

    // renderAssignment: Kopf + Statuszeile + Tabelle mit Auswahlfeldern.
    // opts.onChange(kind, subjectId, value) wird bei jeder Aenderung gerufen
    // (die Shell fuehrt den POST aus). opts.message zeigt eine Rueckmeldung.
    // Rueckgabe: {setMessage} (die Shell meldet Erfolg/Fehler zurueck).
    function renderAssignment(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = mainEl.ownerDocument || document;
        mainEl.textContent = '';

        var rows = toRows(data);
        var invOpts = investigatorOptions(data);
        var statuses = (data && data.statuses) || [];
        var pmin = (data && data.priority_min) || 1;
        var pmax = (data && data.priority_max) || 5;

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Zuweisung';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = rows.length + ' Faelle. Jede Aenderung wird sofort '
            + 'geschrieben und im audit_log belegt.';
        mainEl.appendChild(sub);

        // Rueckmeldebereich (Erfolg/Fehler) — nie still scheitern.
        var msg = doc.createElement('div');
        msg.className = 'aiw-assign-msg';
        msg.id = 'aiw-assign-msg';
        mainEl.appendChild(msg);

        function setMessage(text, isError) {
            msg.textContent = text || '';
            msg.classList.toggle('error', !!isError);
        }

        var table = doc.createElement('table');
        table.className = 'aiw-assign-table';
        var thead = doc.createElement('thead');
        var htr = doc.createElement('tr');
        ['Fall', 'Benutzername', 'Ermittler', 'Prioritaet', 'Status']
            .forEach(function (t) {
                var th = doc.createElement('th');
                th.textContent = t;
                htr.appendChild(th);
            });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = doc.createElement('tbody');
        rows.forEach(function (r) {
            var tr = doc.createElement('tr');
            tr.setAttribute('data-subject-id', String(r.subject_id));

            var tdId = doc.createElement('td');
            tdId.textContent = String(r.subject_id);
            tr.appendChild(tdId);

            var tdName = doc.createElement('td');
            tdName.textContent = r.username || '';
            tr.appendChild(tdName);

            // Ermittler-Auswahl (inkl. entziehen).
            var tdAss = doc.createElement('td');
            tdAss.appendChild(_select(doc, invOpts,
                (r.assigned_to === null ? '' : String(r.assigned_to)),
                function (v) {
                    if (typeof opts.onChange === 'function') {
                        opts.onChange('assign', r.subject_id, v);
                    }
                }));
            tr.appendChild(tdAss);

            // Prioritaets-Auswahl.
            var prios = [];
            for (var p = pmin; p <= pmax; p++) {
                prios.push({ value: String(p), label: String(p) });
            }
            var tdPrio = doc.createElement('td');
            tdPrio.appendChild(_select(doc, prios, String(r.priority),
                function (v) {
                    if (typeof opts.onChange === 'function') {
                        opts.onChange('priority', r.subject_id, v);
                    }
                }));
            tr.appendChild(tdPrio);

            // Status-Auswahl.
            var stOpts = statuses.map(function (s) {
                return { value: s, label: STATUS_LABEL[s] || s };
            });
            var tdSt = doc.createElement('td');
            tdSt.appendChild(_select(doc, stOpts, r.status, function (v) {
                if (typeof opts.onChange === 'function') {
                    opts.onChange('status', r.subject_id, v);
                }
            }));
            tr.appendChild(tdSt);

            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        mainEl.appendChild(table);

        log('renderAssignment:', rows.length, 'Faelle');
        return { setMessage: setMessage };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        STATUS_LABEL: STATUS_LABEL,
        assigneeLabel: assigneeLabel,
        toRows: toRows,
        investigatorOptions: investigatorOptions,
        changeRequest: changeRequest,
        renderAssignment: renderAssignment
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitAssignment = API; }
})();
