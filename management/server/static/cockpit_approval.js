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
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Build 479: hasSelection() ergaenzt. Identischer Schutz wie im Lektorat
 *   (cockpit_lectorate.js): Das Oeffnen eines Berichts holt in onSelect
 *   /api/report/annotations, was serverseitig den Chain-of-Custody-Beleg
 *   'report_annotations_viewed' in den coordinator.db-audit_log schreibt
 *   (management_app.py:_audit_annotation_view; Grundregel 1). Die SSE meldet
 *   diesen Ausschlag ~2s spaeter als 'changed' -> der frueher folgende
 *   loadApproval()-Reload verwarf Auswahl + iframe-Vorschau. cockpit.js
 *   unterdrueckt den Reload nun anhand von hasSelection().
 * Version: v0.8.479 · Build: 479 · 2026-07-21
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
        verifyBox: null,    // Ausgabe der Siegelpruefung
        annPanel: null,     // Belege-Panel (Annotationen, SF-2, Build 417)
        comPanel: null,     // Kommentar-Panel (SF-3, read-only, Build 417)
        resPanel: null      // Ergebnis-Panel (results, read-only, Build 418)
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
        return '/api/report/render?subject_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }

    function reportLabel(r) {
        if (!r) { return ''; }
        return (r.username || ('uid ' + r.subject_id)) + ' · '
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

    // --- Support-View: Belege (SF-2) + Kommentare (SF-3, read-only) -------
    // Self-contained (Repo-Konvention). Fachlich deckungsgleich zu den Helfern
    // der Lektorat-Sicht; hier read-only (die Chefin verifiziert, sie
    // kommentiert nicht in dieser Sicht).
    function annotationsUrl(uid, rid) {
        return '/api/report/annotations?subject_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }
    function commentsUrl(uid, rid) {
        return '/api/report/comments?subject_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }
    function categoryLabel(cat) {
        switch (cat) {
            case 'CAT_PERSON':   return 'Person';
            case 'CAT_LOCATION': return 'Ort';
            case 'CAT_CONTACT':  return 'Kontakt';
            case 'CAT_TIME':     return 'Zeit';
            case 'CAT_OTHER':    return 'Sonstiges';
            default:             return cat || '—';
        }
    }
    function forumContext(item) {
        if (!item || item.topic_id == null || item.forum_id == null) {
            return '—';
        }
        return 'Thema ' + item.topic_id + ' · Unterforum ' + item.forum_id;
    }
    function commentStatusLabel(status) {
        switch (status) {
            case 'pending':   return 'offen';
            case 'addressed': return 'erledigt';
            case 'dismissed': return 'verworfen';
            case 'revoked':   return 'zurueckgenommen';
            default:          return status || 'unbekannt';
        }
    }
    function reviewerRoleLabel(role) {
        switch (role) {
            case 'supervisor': return 'Chef-Ermittlerin';
            case 'lector':     return 'Lektorat';
            default:           return role || '—';
        }
    }

    // --- Ermittlungsergebnis (results, SF/Build 387ff., read-only) --------
    function resultsUrl(uid) {
        return '/api/results?subject_id=' + encodeURIComponent(uid);
    }
    // extremLabel: das bewertete Extrem eines Kriteriums.
    function extremLabel(e) {
        switch (e) {
            case 'schwerste': return 'schwerste Auspraegung';
            case 'beste':     return 'beste Auspraegung';
            default:          return e || '—';
        }
    }
    // gapLabel: robuste Beschriftung eines nicht bewerteten Kriteriums
    // (String-Code ODER {code,label}).
    function gapLabel(g) {
        if (g == null) { return '—'; }
        return (g.label != null) ? g.label
            : ((g.code != null) ? g.code : String(g));
    }

    // =====================================================================
    // 2) DOM.
    // =====================================================================

    function cleanup() {
        _state.iframe = null;
        _state.selKey = null;
        _state.actionPanel = null;
        _state.verifyBox = null;
        _state.annPanel = null;
        _state.comPanel = null;
        _state.resPanel = null;
        log('cleanup');
    }

    // hasSelection: hat die/der Nutzer:in aktuell einen Bericht geoeffnet?
    // (Build 479) Genutzt vom SSE-'changed'-Handler in cockpit.js, um den
    // destruktiven Live-Reload dieser Sicht zu unterdruecken, solange ein
    // Bericht in Sichtung ist. Begruendung identisch zum Lektorat: das Oeffnen
    // holt ueber /api/report/annotations einen Lesebeleg im audit_log
    // (Grundregel 1); die SSE meldet diesen als 'changed'. Der Beleg bleibt
    // erhalten, stattdessen unterbleibt der Reload, solange hasSelection() true
    // liefert. _state.selKey wird in cleanup/renderApproval auf null gesetzt.
    function hasSelection() { return _state.selKey !== null; }

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

    // --- Belege-Panel (SF-2, read-only) ----------------------------------
    function _annHint(msg) {
        if (!_state.annPanel) { return; }
        _state.annPanel.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'aiw-approval-supp-hint';
        p.textContent = msg;
        _state.annPanel.appendChild(p);
    }
    function annotationsLoading() { _annHint('Belege werden geladen …'); }
    function annotationsError(msg) {
        _annHint('Belege konnten nicht geladen werden: ' + (msg || 'Fehler'));
    }

    // renderAnnotations(data): Belege (Annotationen) zum Bericht anzeigen.
    function renderAnnotations(data) {
        var panel = _state.annPanel;
        if (!panel) { return; }
        panel.innerHTML = '';
        var items = (data && data.items) ? data.items : [];

        var head = document.createElement('h3');
        head.className = 'aiw-approval-supp-head';
        head.textContent = 'Belege (' + items.length + ')';
        panel.appendChild(head);

        if (!items.length) {
            var none = document.createElement('p');
            none.className = 'aiw-approval-supp-hint';
            none.textContent = 'Zu diesem Bericht sind keine Belege verankert.';
            panel.appendChild(none);
            return;
        }

        items.forEach(function (it) {
            var box = document.createElement('div');
            box.className = 'aiw-approval-ann-item';
            if (it.missing) { box.classList.add('is-missing'); }
            if (it.deleted) { box.classList.add('is-deleted'); }

            var cat = document.createElement('span');
            cat.className = 'aiw-approval-ann-cat';
            cat.textContent = categoryLabel(it.category);
            box.appendChild(cat);

            var txt = document.createElement('div');
            txt.className = 'aiw-approval-ann-text';
            txt.textContent = it.missing
                ? '⚠ Beleg nicht (mehr) vorhanden (Annotation #'
                    + it.annotation_id + ')'
                : (it.text || '');
            box.appendChild(txt);

            var metaLine = document.createElement('div');
            metaLine.className = 'aiw-approval-ann-meta';
            var bits = [];
            if (it.post_id != null) { bits.push('Beitrag #' + it.post_id); }
            bits.push('Forum: ' + forumContext(it));
            if (it.block_id) {
                bits.push('Block ' + it.block_id
                    + (it.block_type ? ' (' + it.block_type + ')' : ''));
            }
            if (it.deleted) { bits.push('geloescht'); }
            metaLine.textContent = bits.join(' · ');
            box.appendChild(metaLine);

            panel.appendChild(box);
        });
    }

    // --- Kommentar-Panel (SF-3, READ-ONLY) -------------------------------
    // In der Freigabe-Sicht werden Kommentare NUR ANGEZEIGT (kein Anlegen/
    // Aufloesen): die Chefin liest die Anmerkungen des Lektorats zur
    // Entscheidungsfindung. Kommentieren geschieht in der Lektorat-Sicht (W4).
    function _comHint(msg) {
        if (!_state.comPanel) { return; }
        _state.comPanel.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'aiw-approval-supp-hint';
        p.textContent = msg;
        _state.comPanel.appendChild(p);
    }
    function commentsLoading() { _comHint('Kommentare werden geladen …'); }
    function commentsError(msg) {
        _comHint('Kommentare konnten nicht geladen werden: ' + (msg || 'Fehler'));
    }

    function renderComments(data) {
        var panel = _state.comPanel;
        if (!panel) { return; }
        panel.innerHTML = '';
        var comments = (data && data.comments) ? data.comments : [];

        var head = document.createElement('h3');
        head.className = 'aiw-approval-supp-head';
        head.textContent = 'Kommentare (' + comments.length + ')';
        panel.appendChild(head);

        if (!comments.length) {
            var none = document.createElement('p');
            none.className = 'aiw-approval-supp-hint';
            none.textContent = 'Noch keine Kommentare zu diesem Bericht.';
            panel.appendChild(none);
            return;
        }

        comments.forEach(function (c) {
            var box = document.createElement('div');
            box.className = 'aiw-approval-com-item';
            box.setAttribute('data-status', c.status || '');
            if (c.status && c.status !== 'pending') {
                box.classList.add('is-resolved');
            }

            var top = document.createElement('div');
            top.className = 'aiw-approval-com-top';
            var role = document.createElement('span');
            role.className = 'aiw-approval-com-role';
            role.textContent = reviewerRoleLabel(c.reviewer_role);
            top.appendChild(role);
            var stt = document.createElement('span');
            stt.className = 'aiw-approval-com-status';
            stt.textContent = commentStatusLabel(c.status);
            top.appendChild(stt);
            box.appendChild(top);

            var body = document.createElement('div');
            body.className = 'aiw-approval-com-body';
            body.textContent = c.comment_text || '';
            box.appendChild(body);

            if (c.suggested_content) {
                var sugv = document.createElement('div');
                sugv.className = 'aiw-approval-com-suggestion';
                sugv.textContent = 'Vorschlag: ' + c.suggested_content;
                box.appendChild(sugv);
            }

            var meta = document.createElement('div');
            meta.className = 'aiw-approval-com-meta';
            var mbits = [];
            if (c.block_id) { mbits.push('Block ' + c.block_id); }
            mbits.push('Prueferin #' + c.reviewer_pid);
            meta.textContent = mbits.join(' · ');
            box.appendChild(meta);

            panel.appendChild(box);
        });
    }

    // --- Ermittlungsergebnis-Panel (read-only) ---------------------------
    function _resHint(msg) {
        if (!_state.resPanel) { return; }
        _state.resPanel.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'aiw-approval-res-hint';
        p.textContent = msg;
        _state.resPanel.appendChild(p);
    }
    function resultsLoading() { _resHint('Ermittlungsergebnis wird geladen …'); }
    function resultsError(msg) {
        // z.B. 403 ohne Recht results.view -> sichtbar, nicht still (Grundregel 1).
        _resHint('Ermittlungsergebnis nicht verfuegbar: ' + (msg || 'Fehler'));
    }

    // renderResults(data): AKTUELLEN Stand + provisorische Kennzahl + noch
    // nicht bewertete Kriterien anzeigen (Quelle: GET /api/results).
    function renderResults(data) {
        var panel = _state.resPanel;
        if (!panel) { return; }
        panel.innerHTML = '';

        var head = document.createElement('h3');
        head.className = 'aiw-approval-res-head';
        head.textContent = 'Ermittlungsergebnis (Fall)';
        panel.appendChild(head);

        var score = data && data.score;
        if (score) {
            var sc = document.createElement('p');
            sc.className = 'aiw-approval-res-score';
            sc.textContent = 'Vorlaeufige Kennzahl: ' + score.score
                + ' (Basis: ' + (score.basis || 0) + ' bewertete Kriterien)';
            panel.appendChild(sc);
            if (score.vermerk) {
                var vm = document.createElement('p');
                vm.className = 'aiw-approval-res-vermerk';
                vm.textContent = score.vermerk;
                panel.appendChild(vm);
            }
        }

        var current = (data && data.current) ? data.current : [];
        if (!current.length) {
            var none = document.createElement('p');
            none.className = 'aiw-approval-res-hint';
            none.textContent = 'Noch keine Ermittlungsergebnisse erfasst.';
            panel.appendChild(none);
        } else {
            current.forEach(function (it) {
                var row = document.createElement('div');
                row.className = 'aiw-approval-res-item';
                var crit = document.createElement('div');
                crit.className = 'aiw-approval-res-crit';
                crit.textContent = (it.criterion_label || it.criterion_code)
                    + ' — ' + extremLabel(it.extrem);
                row.appendChild(crit);
                var vals = document.createElement('div');
                vals.className = 'aiw-approval-res-vals';
                var conf = it.confidence_label || it.confidence_code || '—';
                var qual = it.quality_label || it.quality_code || '—';
                vals.textContent = 'Konfidenz: ' + conf + ' · Qualitaet: ' + qual;
                row.appendChild(vals);
                panel.appendChild(row);
            });
        }

        // Noch nicht bewertete Kriterien (blinde Flecken) sichtbar machen.
        var gaps = (score && score.unbewertet) ? score.unbewertet : [];
        if (gaps.length) {
            var g = document.createElement('p');
            g.className = 'aiw-approval-res-gaps';
            g.textContent = 'Noch nicht bewertet: '
                + gaps.map(gapLabel).join(', ');
            panel.appendChild(g);
        }
    }

    // --- Bewertungs-Formular (einpflegen, Build 419, append-only) ---------

    // qualityItemsFor: die Qualitaets-Skalenpunkte des gewaehlten Kriteriums
    // (leer, wenn das Kriterium keine Qualitaetsskala hat). REIN (vitest).
    function qualityItemsFor(catalog, criterionCode) {
        var crits = (catalog && catalog.criteria) ? catalog.criteria : [];
        for (var i = 0; i < crits.length; i++) {
            if (crits[i] && crits[i].code === criterionCode) {
                return crits[i].quality_items || [];
            }
        }
        return [];
    }

    // _fillSelect: <option>s aus items (valKey/labelFn) neu setzen.
    function _fillSelect(sel, items, valKey, labelFn) {
        sel.innerHTML = '';
        (items || []).forEach(function (it) {
            var o = document.createElement('option');
            o.value = it[valKey];
            o.textContent = labelFn ? labelFn(it) : (it.label || it[valKey]);
            sel.appendChild(o);
        });
    }

    // assessError: Fehlermeldung im Formular sichtbar machen (Grundregel 1).
    function assessError(msg) {
        if (!_state.resPanel) { return; }
        var box = _state.resPanel.querySelector('.aiw-approval-assess-err');
        if (box) { box.textContent = 'Bewertung fehlgeschlagen: '
            + (msg || 'Fehler'); }
    }

    // renderAssessForm(catalog, opts): haengt das append-only Bewertungs-
    // Formular UNTER den read-only Ergebnisstand (nur wenn results.edit).
    //   catalog — GET /api/results/catalog {criteria[], confidence_items[],
    //             extreme[]}
    //   opts    — { subjectId, onAssess(body) }
    function renderAssessForm(catalog, opts) {
        var panel = _state.resPanel;
        if (!panel || !catalog) { return; }
        opts = opts || {};

        var form = document.createElement('form');
        form.className = 'aiw-approval-assess-form';

        var head = document.createElement('h4');
        head.className = 'aiw-approval-assess-head';
        head.textContent = 'Bewertung erfassen (append-only)';
        form.appendChild(head);

        function _field(labelText, el) {
            var lbl = document.createElement('label');
            lbl.className = 'aiw-approval-assess-field';
            lbl.appendChild(document.createTextNode(labelText + ' '));
            lbl.appendChild(el);
            form.appendChild(lbl);
            return el;
        }

        // Kriterium.
        var critSel = document.createElement('select');
        critSel.className = 'aiw-approval-assess-crit';
        _fillSelect(critSel, catalog.criteria, 'code');
        _field('Kriterium:', critSel);

        // Extrem.
        var extSel = document.createElement('select');
        extSel.className = 'aiw-approval-assess-extrem';
        _fillSelect(extSel, (catalog.extreme || ['schwerste', 'beste'])
            .map(function (e) { return { code: e }; }), 'code',
            function (it) { return extremLabel(it.code); });
        _field('Auspraegung:', extSel);

        // Konfidenz.
        var confSel = document.createElement('select');
        confSel.className = 'aiw-approval-assess-conf';
        _fillSelect(confSel, catalog.confidence_items, 'code');
        _field('Konfidenz:', confSel);

        // Qualitaet (optional; abhaengig vom Kriterium). Erste Option 'keine'.
        var qualSel = document.createElement('select');
        qualSel.className = 'aiw-approval-assess-qual';
        function _refillQuality() {
            var items = qualityItemsFor(catalog, critSel.value);
            var withEmpty = [{ code: '', label: '— (keine Qualitaet)' }]
                .concat(items);
            _fillSelect(qualSel, withEmpty, 'code');
        }
        _refillQuality();
        // Bei Kriteriumwechsel die Qualitaets-Optionen nachziehen (jede
        // Kriteriumsskala kann eine andere Qualitaetsskala haben).
        critSel.addEventListener('change', _refillQuality);
        _field('Qualitaet:', qualSel);

        // Vermerk (Freitext).
        var note = document.createElement('textarea');
        note.className = 'aiw-approval-assess-note';
        note.setAttribute('rows', '2');
        note.setAttribute('placeholder', 'Vermerk (optional)');
        form.appendChild(note);

        var submit = document.createElement('button');
        submit.type = 'submit';
        submit.className = 'aiw-approval-assess-submit';
        submit.textContent = 'Bewertung erfassen';
        form.appendChild(submit);

        var err = document.createElement('div');
        err.className = 'aiw-approval-assess-err';
        form.appendChild(err);

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            err.textContent = '';
            if (!critSel.value || !extSel.value || !confSel.value) {
                err.textContent = 'Kriterium, Auspraegung und Konfidenz sind '
                    + 'erforderlich.';
                return;
            }
            var body = {
                subject_id: opts.subjectId,
                criterion_code: critSel.value,
                extrem: extSel.value,
                confidence_code: confSel.value,
                quality_code: qualSel.value || null,
                note: (note.value || '').trim()
            };
            log('assess', body);
            if (typeof opts.onAssess === 'function') { opts.onAssess(body); }
        });

        panel.appendChild(form);
        return form;
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
                opts.onVerify(r.subject_id, r.id);
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
                subject_id: r.subject_id, report_id: r.id,
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
                subject_id: r.subject_id, report_id: r.id,
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
        _state.annPanel = null;
        _state.comPanel = null;
        _state.resPanel = null;

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
            var key = selectionKey(r.subject_id, r.id);
            var row = document.createElement('button');
            row.type = 'button';
            row.className = 'aiw-approval-item';
            row.setAttribute('data-uid', String(r.subject_id));
            row.setAttribute('data-rid', String(r.id));
            row.setAttribute('data-key', key);
            row.textContent = reportLabel(r);
            row.addEventListener('click', function () {
                var prev = list.querySelector('.aiw-approval-item.is-active');
                if (prev) { prev.classList.remove('is-active'); }
                row.classList.add('is-active');
                _state.selKey = key;
                frame.src = renderUrl(r.subject_id, r.id);
                _buildActionPanel(r, opts);
                // Support-View (Belege + Kommentare) auf "laedt" setzen; der
                // Abruf laeuft ueber opts.onSelect (cockpit.js holt
                // /api/report/annotations + /api/report/comments).
                annotationsLoading();
                commentsLoading();
                resultsLoading();
                if (typeof opts.onSelect === 'function') {
                    opts.onSelect(r.subject_id, r.id);
                }
                log('select', key, frame.src);
            });
            list.appendChild(row);
        });

        wrap.appendChild(list);
        wrap.appendChild(preview);

        // --- Support-View (SF-2 + SF-3, read-only) unter dem Vorschau-Bereich.
        // Zwei Panels nebeneinander (schmal: gestapelt): Belege | Kommentare.
        var support = document.createElement('div');
        support.className = 'aiw-approval-support';
        var ann = document.createElement('div');
        ann.className = 'aiw-approval-annotations';
        _state.annPanel = ann;
        var com = document.createElement('div');
        com.className = 'aiw-approval-comments';
        _state.comPanel = com;
        support.appendChild(ann);
        support.appendChild(com);
        _annHint('Bericht auswaehlen, um die Belege zu sehen.');
        _comHint('Bericht auswaehlen, um die Kommentare zu sehen.');
        wrap.appendChild(support);

        // --- Ermittlungsergebnis (read-only, Build 418) unter dem Support-View.
        var res = document.createElement('div');
        res.className = 'aiw-approval-results';
        _state.resPanel = res;
        _resHint('Bericht auswaehlen, um das Ermittlungsergebnis zu sehen.');
        wrap.appendChild(res);

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
        annotationsUrl: annotationsUrl,     // SF-2 (Build 417)
        commentsUrl: commentsUrl,           // SF-3 (Build 417)
        categoryLabel: categoryLabel,
        forumContext: forumContext,
        commentStatusLabel: commentStatusLabel,
        reviewerRoleLabel: reviewerRoleLabel,
        resultsUrl: resultsUrl,             // results (Build 418)
        extremLabel: extremLabel,
        gapLabel: gapLabel,
        qualityItemsFor: qualityItemsFor,   // Assess-Formular (Build 419)
        // DOM
        renderApproval: renderApproval,
        renderVerify: renderVerify,
        verifyLoading: verifyLoading,
        verifyError: verifyError,
        renderAnnotations: renderAnnotations,   // Belege (SF-2, read-only)
        annotationsLoading: annotationsLoading,
        annotationsError: annotationsError,
        renderComments: renderComments,         // Kommentare (SF-3, read-only)
        commentsLoading: commentsLoading,
        commentsError: commentsError,
        renderResults: renderResults,           // Ermittlungsergebnis (read-only)
        resultsLoading: resultsLoading,
        resultsError: resultsError,
        renderAssessForm: renderAssessForm,     // Bewertung einpflegen (Build 419)
        assessError: assessError,
        hasSelection: hasSelection,   // SSE-Reload-Schutz (Build 479)
        cleanup: cleanup
    };
    log('Modul geladen.');
})();
