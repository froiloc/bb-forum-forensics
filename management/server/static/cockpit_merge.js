// =============================================================================
// management/server/static/cockpit_merge.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Identitaet (AP-2A)
// =============================================================================
// Zweck (Idee 11, Frontend zu Build 509):
//   Rendert die IDENTITAETS-GRUPPEN (/api/merge) — die Aussage "Konto A und
//   Konto B werden von DERSELBEN natuerlichen Person betrieben", mit
//   Konfidenzstufe. Mit dem Recht crossref.edit koennen Konten zusammengefuehrt,
//   die Konfidenz reifen gelassen, die Zuordnung GETRENNT und eine Trennung
//   zurueckgenommen werden.
//
// WARUM EINE EIGENE SICHT (wie beim Alias-Katalog, Build 505):
//   Eine Zusammenfuehrung besteht UNABHAENGIG davon, ob eines der Konten
//   identifiziert (M018) oder mit Aliassen versehen (M022) ist — gerade der
//   haeufige Fall ist "wir wissen, dass es dieselbe Person ist, aber noch nicht
//   WER". Ein Anbau an die Kreuzbezug-Sicht haette genau diese Faelle
//   unsichtbar gemacht (Grundregel 1).
//
// Datenform GET /api/merge (ManagementApp._merge):
//   { entries: [ {id, primary_subject_id, merged_subject_id, basis,
//                 confidence_code, confidence_ordinal, is_active,
//                 split_reason, merged_by, split_by, created_at, updated_at,
//                 split_at, audit_seq, created_audit_seq}, ... ],
//     counts: {total, aktiv, getrennt, konten},
//     confidence: [{code,label,ordinal}, ...],   // vom SERVER
//     mode: 'all' | 'group',
//     group: {primary_subject_id, members[], merges[], queried_subject_id,
//             is_primary}   // nur bei ?subject_id=N }
//
// SCHREIBEN (opts -> cockpit.js -> postJson mit X-AIW-Token):
//   onMerge({primary_subject_id, merged_subject_id, basis, confidence_code})
//   onRevise({merge_id, confidence_code, basis})
//   onSplit({merge_id, reason})        — Grund ist PFLICHT
//   onRemerge({merge_id})
//   KEIN optimistisches UI: nach jedem Schreiben laedt cockpit.js neu.
//
// KONFLIKTMELDUNGEN WERDEN WOERTLICH ANGEZEIGT: der Server nennt in seinen
//   400ern die beteiligten subject_ids und den konstruktiven Ausweg ("haenge
//   die Konten direkt an 4711"). Diese Information darf das Frontend NICHT
//   zusammenfassen — die Ermittlerin braucht den konkreten Konflikt.
//
// SENSIBILITAET: 'basis' und 'split_reason' sind PII-nahe Freitexte. Das
//   Frontend reicht sie nur durch; der Ausschluss aus dem Audit-Payload liegt
//   im Server-Repo (subject_merge_repo.py).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS: (1) IIFE + 'use strict'. (2) DEV-Logging
//   (AIW_COCKPIT_DEBUG). (3) ausfuehrliche Kommentare. (4) reine Funktionen
//   fassen NIE das DOM an -> vitest; opts.doc injizierbar (JSDOM).
// SICHERHEIT (XSS): alle variablen Texte via textContent.
//
// Build 634 (Vorgang 17200856, Welle B2): HILFE-MARKEN fuer die acht weitere
//   Bedienelemente dieser Sicht - damit tragen alle eine. Die Texte
//   stehen in management/help/inhalt/identitaeten.py. Die Eingabezeilen
//   stammen aus der Fabrik '_field'; ihre Marken sitzen deshalb an den
//   ABNAHMESTELLEN und nicht in der Fabrik - eine Fabrik kann nur EINE
//   Kennung setzen, und die Felder meinen Verschiedenes (Fabrikregel,
//   tests/_bedienelemente.py, Build 633).
// Version: v0.8.634 · Build: 634 · 2026-08-01
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
        args.unshift('[AIW-Merge]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';

    // Notnagel, falls der Server die Konfidenz-Achse nicht mitliefert.
    // Deckungsgleich mit _CONFIDENCE (subject_merge_repo.py) und der
    // DDL-CHECK in m025 — dieselbe Achse wie im Identitaetskatalog.
    var CONFIDENCE_FALLBACK = [
        { code: 'verdacht', label: 'Verdacht', ordinal: 10 },
        { code: 'wahrscheinlich', label: 'wahrscheinlich', ordinal: 20 },
        { code: 'gesichert', label: 'gesichert', ordinal: 30 }
    ];

    // ------------------------------------------------------------------ Helfer
    // (rein — kein DOM, damit unter vitest direkt pruefbar)

    function entries(data) {
        return (data && Array.isArray(data.entries)) ? data.entries : [];
    }
    function confidence(data) {
        return (data && Array.isArray(data.confidence) && data.confidence.length)
            ? data.confidence : CONFIDENCE_FALLBACK;
    }
    function counts(data) {
        var c = (data && data.counts) ? data.counts : {};
        return {
            total: parseInt(c.total, 10) || 0,
            aktiv: parseInt(c.aktiv, 10) || 0,
            getrennt: parseInt(c.getrennt, 10) || 0,
            konten: parseInt(c.konten, 10) || 0
        };
    }
    function countsText(data) {
        var c = counts(data);
        return c.aktiv + ' aktive Zusammenführungen · ' + c.getrennt
            + ' getrennt · ' + c.konten + ' Konten betroffen';
    }

    // confidenceLabel: Anzeigetext einer Stufe. Nutzt die Server-Liste, wenn
    // sie da ist — sonst den Fallback; unbekannt -> Rohwert (nie leer).
    function confidenceLabel(code, list) {
        var l = list || CONFIDENCE_FALLBACK;
        for (var i = 0; i < l.length; i++) {
            if (l[i] && l[i].code === code) { return l[i].label; }
        }
        return String(code == null ? '' : code);
    }

    // confidenceClass: dieselben Badge-Klassen wie in der Kreuzbezug-Sicht
    // (cockpit_crossref.js) — gleiche Achse, gleiche Optik, damit niemand zwei
    // Bedeutungen lernen muss.
    function confidenceClass(code) {
        if (code === 'gesichert') { return 'aiw-conf-gesichert'; }
        if (code === 'wahrscheinlich') { return 'aiw-conf-wahrscheinlich'; }
        if (code === 'verdacht') { return 'aiw-conf-verdacht'; }
        return 'aiw-conf-unbekannt';
    }

    function statusClass(isActive) {
        return isActive ? 'aiw-merge-aktiv' : 'aiw-merge-getrennt';
    }

    function fmtTs(epoch) {
        var n = parseInt(epoch, 10);
        if (!n || isNaN(n)) { return EM_DASH; }
        try {
            return new Date(n * 1000).toLocaleString();
        } catch (e) {
            return String(epoch);
        }
    }

    // groupText: beschreibt eine Identitaets-Gruppe in einem Satz. Ein Konto
    // OHNE Zusammenfuehrung ist seine eigene Gruppe — das ist ein Befund, kein
    // Leerbefund, und wird auch so formuliert.
    function groupText(group) {
        if (!group) { return ''; }
        var members = Array.isArray(group.members) ? group.members : [];
        if (members.length <= 1) {
            return 'Konto ' + group.queried_subject_id
                + ' ist keiner Identitäts-Gruppe zugeordnet.';
        }
        return 'Identitäts-Gruppe um Primärkonto '
            + group.primary_subject_id + ': ' + members.join(', ')
            + ' (' + members.length + ' Konten).';
    }

    // buildMergePayload: Formularfelder -> POST-Body. REIN. Beide subject_ids
    // nur dann als Zahl, wenn die Eingabe VOLLSTAENDIG ganzzahlig war — '47xy'
    // darf nicht still zu 47 werden (das waere ein FALSCHES Konto und damit
    // eine falsche Identitaetsaussage).
    function buildMergePayload(fields) {
        fields = fields || {};
        function intOrNull(v) {
            var raw = (v == null) ? '' : String(v).trim();
            var n = parseInt(raw, 10);
            return (String(n) === raw && !isNaN(n)) ? n : null;
        }
        return {
            primary_subject_id: intOrNull(fields.primary_subject_id),
            merged_subject_id: intOrNull(fields.merged_subject_id),
            basis: String(fields.basis || '').trim(),
            confidence_code: String(fields.confidence_code || '')
        };
    }

    // validateMerge: Vorpruefung im Browser (der Server bleibt verbindlich).
    function validateMerge(body) {
        if (!body || body.primary_subject_id == null) {
            return 'Primärkonto fehlt oder ist keine ganze Zahl.';
        }
        if (body.merged_subject_id == null) {
            return 'Einzugliederndes Konto fehlt oder ist keine ganze Zahl.';
        }
        if (body.primary_subject_id === body.merged_subject_id) {
            return 'Ein Konto kann nicht mit sich selbst zusammengeführt '
                + 'werden.';
        }
        if (!body.basis) {
            return 'Basis ist Pflicht — eine Zusammenführung ist eine '
                + 'Hypothese und braucht ihre Indizien.';
        }
        if (!body.confidence_code) { return 'Bitte eine Konfidenzstufe wählen.'; }
        return null;
    }

    // =========================================================================
    // 1) DOM: Sicht rendern.
    // =========================================================================
    function renderMerge(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return { setResult: function () {} }; }
        var canEdit = opts.canEdit === true;
        var confList = confidence(data);

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        // Build 604 (Baustelle H / H13): literale Hilfe-Marken.
        h.className = 'aiw-pagehead';
        h.setAttribute('data-hilfe-id', 'merge.titel');
        h.textContent = 'Identitäts-Gruppen — Zusammenführen und Trennen';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'merge.kennzeile');
        sub.textContent = 'Mehrere Forenkonten, die von derselben natürlichen '
            + 'Person betrieben werden. Eine Zusammenführung ist eine '
            + 'Hypothese: sie ist umkehrbar, und jede Trennung wird ebenso '
            + 'belegt wie die Zusammenführung. Gelöscht wird nie.';
        mainEl.appendChild(sub);

        var head = doc.createElement('p');
        head.className = 'aiw-merge-counts';
        head.setAttribute('data-hilfe-id', 'merge.zahlen');
        head.textContent = countsText(data);
        mainEl.appendChild(head);

        var result = doc.createElement('div');
        result.className = 'aiw-merge-result';
        result.id = 'aiw-merge-result';
        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }

        mainEl.appendChild(_searchBar(doc, opts));

        // Gruppen-Befund (nur im Gruppenmodus). Bewusst als eigener Satz —
        // "keiner Gruppe zugeordnet" ist ein BEFUND, kein Leerbefund.
        if (data && data.group) {
            var g = doc.createElement('p');
            g.className = 'aiw-merge-group';
        g.setAttribute('data-hilfe-id', 'merge.gruppenbefund');
            g.textContent = groupText(data.group);
            mainEl.appendChild(g);
        }

        if (canEdit) {
            mainEl.appendChild(_form(doc, confList, setResult, opts));
        } else {
            var ro = doc.createElement('p');
            ro.className = 'aiw-pagesub aiw-merge-readonly';
            ro.textContent = 'Nur lesend — zum Pflegen fehlt das Recht '
                + '„crossref.edit“.';
            mainEl.appendChild(ro);
        }
        mainEl.appendChild(result);

        // Ladefehler ist KEIN Leerbefund (Grundregel 1).
        if (data && data.error) {
            var err = doc.createElement('p');
            err.className = 'aiw-merge-error';
            err.textContent = 'Identitäts-Gruppen nicht abrufbar: '
                + String(data.error);
            mainEl.appendChild(err);
            return { setResult: setResult };
        }

        var rows = entries(data);
        if (rows.length === 0) {
            var empty = doc.createElement('p');
            empty.className = 'aiw-placeholder';
            empty.textContent = (opts.query)
                ? 'Keine Zusammenführung für dieses Konto.'
                : 'Noch keine Zusammenführung erfasst.';
            mainEl.appendChild(empty);
            log('renderMerge: leer, canEdit', canEdit);
            return { setResult: setResult };
        }

        var table = doc.createElement('table');
        table.className = 'aiw-merge-table';
        var thead = doc.createElement('thead');
        var htr = doc.createElement('tr');
        ['Primärkonto', 'eingegliedert', 'Konfidenz', 'Basis', 'Status',
         'geändert', '']
            .forEach(function (label) {
                var th = doc.createElement('th');
                th.textContent = label;
                htr.appendChild(th);
            });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = doc.createElement('tbody');
        rows.forEach(function (e) {
            tbody.appendChild(_rowEl(doc, e, confList, canEdit, setResult,
                                     opts));
        });
        table.appendChild(tbody);
        mainEl.appendChild(table);

        log('renderMerge:', rows.length, 'Zeilen, canEdit', canEdit);
        return { setResult: setResult };
    }

    // _searchBar: Gruppenabfrage + Umschalter „getrennte zeigen".
    function _searchBar(doc, opts) {
        var box = doc.createElement('div');
        box.className = 'aiw-merge-search';

        var lbl = doc.createElement('label');
        lbl.className = 'aiw-merge-lbl';
        lbl.textContent = 'Gruppe zu subject_id: ';
        var inp = doc.createElement('input');
        inp.type = 'text';
        inp.id = 'aiw-merge-q';
        inp.setAttribute('data-hilfe-id', 'merge.bedienung.suche');
        inp.className = 'aiw-merge-input';
        inp.value = opts.query || '';
        lbl.appendChild(inp);
        box.appendChild(lbl);

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-merge-search-btn';
        btn.className = 'aiw-btn aiw-merge-btn';
        btn.textContent = 'Gruppe zeigen';
        // Build 634 (Vorgang 17200856): Hilfe-Marke, LITERAL gesetzt.
        // Text in management/help/inhalt/identitaeten.py.
        btn.setAttribute('data-hilfe-id', 'merge.bedienung.gruppe_zeigen');
        btn.addEventListener('click', function () {
            if (typeof opts.onSearch === 'function') {
                opts.onSearch(inp.value);
            }
        });
        box.appendChild(btn);

        var clear = doc.createElement('button');
        clear.type = 'button';
        clear.id = 'aiw-merge-clear-btn';
        clear.setAttribute('data-hilfe-id', 'merge.bedienung.alle');
        clear.className = 'aiw-btn aiw-merge-btn';
        clear.textContent = 'Alle';
        clear.addEventListener('click', function () {
            if (typeof opts.onSearch === 'function') { opts.onSearch(''); }
        });
        box.appendChild(clear);

        var tog = doc.createElement('label');
        tog.className = 'aiw-merge-lbl aiw-merge-toggle';
        var cb = doc.createElement('input');
        cb.type = 'checkbox';
        cb.id = 'aiw-merge-incl';
        cb.setAttribute('data-hilfe-id', 'merge.bedienung.getrennte');
        cb.checked = opts.includeSplit === true;
        cb.addEventListener('change', function () {
            if (typeof opts.onToggleSplit === 'function') {
                opts.onToggleSplit(cb.checked === true);
            }
        });
        tog.appendChild(cb);
        var tt = doc.createElement('span');
        tt.textContent = ' getrennte zeigen';
        tog.appendChild(tt);
        box.appendChild(tog);

        return box;
    }

    // _form: Anlage einer Zusammenfuehrung. Die Konfidenz kann spaeter ueber
    // die Zeilen-Aktion „Revidieren" reifen; die beteiligten Konten sind
    // bewusst nicht aenderbar (Server-Regel: andere Paarung = andere
    // Hypothese = trennen + neu anlegen).
    function _form(doc, confList, setResult, opts) {
        var box = doc.createElement('div');
        box.className = 'aiw-merge-form';

        var inP = _field(doc, box, 'Primärkonto (führend): ',
            'aiw-merge-primary');
        // Marken an den ABNAHMESTELLEN der Fabrik '_field' - dieselbe Fabrik
        // baut drei verschiedene Felder (Fabrikregel, Build 633).
        inP.setAttribute('data-hilfe-id', 'merge.bedienung.primaerkonto');
        var inM = _field(doc, box, 'einzugliedern: ', 'aiw-merge-merged');
        inM.setAttribute('data-hilfe-id', 'merge.bedienung.zweitkonto');

        var lblC = doc.createElement('label');
        lblC.className = 'aiw-merge-lbl';
        lblC.textContent = 'Konfidenz: ';
        var selC = doc.createElement('select');
        selC.id = 'aiw-merge-conf';
        selC.setAttribute('data-hilfe-id', 'merge.bedienung.konfidenz');
        selC.className = 'aiw-merge-input';
        confList.forEach(function (c) {
            var o = doc.createElement('option');
            o.value = c.code;
            o.textContent = c.label;
            selC.appendChild(o);
        });
        lblC.appendChild(selC);
        box.appendChild(lblC);

        var inB = _field(doc, box, 'Basis (Indizien): ', 'aiw-merge-basis');
        inB.setAttribute('data-hilfe-id', 'merge.bedienung.basis');

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-merge-add';
        btn.setAttribute('data-hilfe-id', 'merge.bedienung.zusammenfuehren');
        btn.className = 'aiw-btn aiw-merge-btn';
        btn.textContent = 'Zusammenführen';
        btn.addEventListener('click', function () {
            var body = buildMergePayload({
                primary_subject_id: inP.value,
                merged_subject_id: inM.value,
                confidence_code: selC.value,
                basis: inB.value
            });
            var problem = validateMerge(body);
            if (problem) { setResult(problem, true); return; }
            setResult('Führe Konten zusammen …', null);
            if (typeof opts.onMerge === 'function') {
                opts.onMerge(body);
            } else {
                setResult('Kein Schreibpfad verdrahtet.', true);
            }
        });
        box.appendChild(btn);
        return box;
    }

    function _field(doc, parent, labelText, id) {
        var lbl = doc.createElement('label');
        lbl.className = 'aiw-merge-lbl';
        lbl.textContent = labelText;
        var inp = doc.createElement('input');
        inp.type = 'text';
        inp.id = id;
        inp.className = 'aiw-merge-input';
        lbl.appendChild(inp);
        parent.appendChild(lbl);
        return inp;
    }

    // _rowEl: eine Zusammenfuehrung. Aktionen je nach Status:
    //   aktiv    -> „Revidieren" (Konfidenz/Basis) und „Trennen" (Grund PFLICHT)
    //   getrennt -> „Trennung zurücknehmen"
    function _rowEl(doc, e, confList, canEdit, setResult, opts) {
        var tr = doc.createElement('tr');
        tr.className = statusClass(e.is_active === true);
        tr.setAttribute('data-merge-id', String(e.id));

        var tdP = doc.createElement('td');
        tdP.textContent = String(e.primary_subject_id);
        tr.appendChild(tdP);

        var tdM = doc.createElement('td');
        tdM.textContent = String(e.merged_subject_id);
        tr.appendChild(tdM);

        var tdC = doc.createElement('td');
        var badge = doc.createElement('span');
        badge.className = 'aiw-badge aiw-conf-badge '
            + confidenceClass(e.confidence_code);
        badge.textContent = confidenceLabel(e.confidence_code, confList);
        tdC.appendChild(badge);
        tr.appendChild(tdC);

        var tdB = doc.createElement('td');
        tdB.textContent = e.basis || EM_DASH;
        tr.appendChild(tdB);

        var tdS = doc.createElement('td');
        if (e.is_active === true) {
            tdS.textContent = 'aktiv';
        } else {
            // Der Trennungsgrund gehoert sichtbar in die Zeile: er ist die
            // Erkenntnis "warum traegt die Hypothese nicht mehr".
            tdS.textContent = 'getrennt'
                + (e.split_at ? ' am ' + fmtTs(e.split_at) : '')
                + (e.split_reason ? ' — ' + e.split_reason : '');
        }
        tr.appendChild(tdS);

        var tdT = doc.createElement('td');
        tdT.textContent = fmtTs(e.updated_at);
        tr.appendChild(tdT);

        var tdA = doc.createElement('td');
        tdA.className = 'aiw-merge-actions';
        if (!canEdit) {
            tdA.textContent = EM_DASH;
        } else if (e.is_active === true) {
            tdA.appendChild(_btnRevise(doc, e, confList, setResult, opts));
            tdA.appendChild(_btnSplit(doc, e, setResult, opts));
        } else {
            tdA.appendChild(_btnRemerge(doc, e, setResult, opts));
        }
        tr.appendChild(tdA);
        return tr;
    }

    function _btnRevise(doc, e, confList, setResult, opts) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'aiw-btn aiw-merge-btn aiw-merge-revise';
        b.setAttribute('data-merge-id', String(e.id));
        b.textContent = 'Revidieren';
        b.setAttribute('data-hilfe-id', 'merge.bedienung.revidieren');
        b.addEventListener('click', function () {
            var row = b.parentNode && b.parentNode.parentNode;
            if (!row || row.getAttribute('data-editing') === '1') { return; }
            row.setAttribute('data-editing', '1');
            var host = doc.createElement('tr');
            host.className = 'aiw-merge-editrow';
            var td = doc.createElement('td');
            td.setAttribute('colspan', '7');

            var selC = doc.createElement('select');
            selC.className = 'aiw-merge-input aiw-merge-edit-conf';
            selC.setAttribute('data-hilfe-id',
                'merge.bedienung.edit_konfidenz');
            confList.forEach(function (c) {
                var o = doc.createElement('option');
                o.value = c.code;
                o.textContent = c.label;
                if (c.code === e.confidence_code) { o.selected = true; }
                selC.appendChild(o);
            });
            var inB = doc.createElement('input');
            inB.type = 'text';
            inB.className = 'aiw-merge-input aiw-merge-edit-basis';
            inB.setAttribute('data-hilfe-id', 'merge.bedienung.edit_basis');
            inB.value = e.basis || '';
            var save = doc.createElement('button');
            save.type = 'button';
            save.className = 'aiw-btn aiw-merge-btn aiw-merge-edit-save';
            save.textContent = 'Speichern';
            save.setAttribute('data-hilfe-id',
                'merge.bedienung.edit_speichern');
            save.addEventListener('click', function () {
                var basis = String(inB.value || '').trim();
                if (!basis) {
                    setResult('Basis darf nicht geleert werden — die '
                        + 'Hypothese braucht ihre Indizien.', true);
                    return;
                }
                setResult('Speichere Revision …', null);
                if (typeof opts.onRevise === 'function') {
                    opts.onRevise({ merge_id: e.id,
                                    confidence_code: selC.value,
                                    basis: basis });
                } else {
                    setResult('Kein Schreibpfad verdrahtet.', true);
                }
            });

            td.appendChild(doc.createTextNode('Konfidenz: '));
            td.appendChild(selC);
            td.appendChild(doc.createTextNode(' Basis: '));
            td.appendChild(inB);
            td.appendChild(save);
            host.appendChild(td);
            if (row.parentNode) {
                row.parentNode.insertBefore(host, row.nextSibling);
            }
        });
        return b;
    }

    // _btnSplit: Trennung mit PFLICHT-Grund. Eine Trennung muss so belegt sein
    // wie die Zusammenfuehrung — deshalb faengt schon das UI den leeren Grund ab.
    function _btnSplit(doc, e, setResult, opts) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'aiw-btn aiw-merge-btn aiw-merge-split';
        b.setAttribute('data-merge-id', String(e.id));
        b.textContent = 'Trennen';
        b.setAttribute('data-hilfe-id', 'merge.bedienung.trennen');
        b.addEventListener('click', function () {
            var row = b.parentNode && b.parentNode.parentNode;
            if (!row || row.getAttribute('data-splitting') === '1') { return; }
            row.setAttribute('data-splitting', '1');
            var host = doc.createElement('tr');
            host.className = 'aiw-merge-reasonrow';
            var td = doc.createElement('td');
            td.setAttribute('colspan', '7');
            var inR = doc.createElement('input');
            inR.type = 'text';
            inR.className = 'aiw-merge-input aiw-merge-reason';
            inR.setAttribute('placeholder',
                'Grund der Trennung (Pflicht)');
            inR.setAttribute('data-hilfe-id', 'merge.bedienung.trennungsgrund');
            var go = doc.createElement('button');
            go.type = 'button';
            go.className = 'aiw-btn aiw-merge-btn aiw-merge-split-go';
            go.textContent = 'Trennung belegen';
            go.setAttribute('data-hilfe-id', 'merge.bedienung.trennung_belegen');
            go.addEventListener('click', function () {
                var reason = String(inR.value || '').trim();
                if (!reason) {
                    setResult('Grund ist Pflicht — eine Trennung muss so '
                        + 'belegt sein wie die Zusammenführung.', true);
                    return;
                }
                setResult('Trenne Zuordnung …', null);
                if (typeof opts.onSplit === 'function') {
                    opts.onSplit({ merge_id: e.id, reason: reason });
                } else {
                    setResult('Kein Schreibpfad verdrahtet.', true);
                }
            });
            td.appendChild(doc.createTextNode('Grund: '));
            td.appendChild(inR);
            td.appendChild(go);
            host.appendChild(td);
            if (row.parentNode) {
                row.parentNode.insertBefore(host, row.nextSibling);
            }
        });
        return b;
    }

    function _btnRemerge(doc, e, setResult, opts) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'aiw-btn aiw-merge-btn aiw-merge-remerge';
        b.setAttribute('data-merge-id', String(e.id));
        b.textContent = 'Trennung zurücknehmen';
        b.setAttribute('data-hilfe-id', 'merge.bedienung.trennung_zuruecknehmen');
        b.addEventListener('click', function () {
            setResult('Nehme Trennung zurück …', null);
            if (typeof opts.onRemerge === 'function') {
                opts.onRemerge({ merge_id: e.id });
            } else {
                setResult('Kein Schreibpfad verdrahtet.', true);
            }
        });
        return b;
    }

    // =========================================================================
    // 2) UMD-Ausgang.
    // =========================================================================
    var API = {
        entries: entries,
        confidence: confidence,
        counts: counts,
        countsText: countsText,
        confidenceLabel: confidenceLabel,
        confidenceClass: confidenceClass,
        statusClass: statusClass,
        fmtTs: fmtTs,
        groupText: groupText,
        buildMergePayload: buildMergePayload,
        validateMerge: validateMerge,
        renderMerge: renderMerge,
        CONFIDENCE_FALLBACK: CONFIDENCE_FALLBACK
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitMerge = API; }
})();
