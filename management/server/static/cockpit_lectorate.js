/**
 * management/server/static/cockpit_lectorate.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Vermaehlung B6xB7 — W4 (Lektorat), SLICE 1 (Build 413)
 *
 * Zweck:
 *   Gegenlese-Sicht fuer Lektor:innen (Recht reports.review; die Chefin mit
 *   reports.approve sieht sie ebenfalls). SLICE 1 liefert:
 *     - eine Auswahl der gegenzulesenden Berichte (Quelle: /api/reports),
 *     - die READ-ONLY-Vorschau des Berichtstexts in einem <iframe>
 *       (Quelle: /api/report/render, SF-1 Build 410 — byte-identisch zum Export).
 *   Annotationen (SF-2) und das Kommentar-Panel (SF-3) folgen in den naechsten
 *   Slices (Build 414/415).
 *
 * JS-Gebote des Projekts:
 *   1) IIFE-Wrapper mit 'use strict'.
 *   2) Ausgiebiges DEV-Logging (DEV=true), fuer PROD ueber die Konstante DEV
 *      abschaltbar.
 *   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
 *   4) Kapselung: interner Zustand liegt in der Closure; nach aussen nur eine
 *      kleine API (window.AIWCockpitLectorate). REINE Funktionen (kein DOM)
 *      sind separat exportiert und werden von vitest geprueft.
 *
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Build 479: hasSelection() ergaenzt. Schutz vor selbst ausgeloestem
 *   SSE-Reload: Das Oeffnen eines Berichts holt /api/report/annotations, was
 *   serverseitig den Chain-of-Custody-Beleg 'report_annotations_viewed' in den
 *   coordinator.db-audit_log schreibt (management_app.py:_audit_annotation_view;
 *   Grundregel 1). Die SSE beobachtet die audit_log-Spitze und meldet ~2s
 *   spaeter 'changed' (management_handler.py:_handle_sse, poll=2.0s) -> der
 *   frueher folgende loadLectorate()-Reload verwarf Auswahl + iframe-Vorschau
 *   (gemeldeter Fehler). cockpit.js unterdrueckt den Reload nun anhand von
 *   hasSelection(), solange ein Bericht in Sichtung ist.
 * Build 480: Bugfix — der Statusfilter-Wechsel reichte onTransferToTemplate
 *   nicht mehr durch, wodurch der Knopf "Als Vorlage uebernehmen" nach jedem
 *   Filterwechsel verschwand. Callback wird nun beim Neu-Rendern erhalten.
 * Version: v0.8.480 · Build: 480 · 2026-07-21
 */
(function () {
    'use strict';

    // --- DEV-Logging (fuer PROD auf false) -------------------------------
    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[lectorate]');
            console.log.apply(console, a);
        }
    }

    // --- gekapselter Sicht-Zustand (Closure, nicht nach aussen sichtbar) --
    var _state = {
        iframe: null,     // aktuelles Vorschau-<iframe>
        selKey: null,     // aktuell gewaehlter Bericht ('uid:rid')
        annPanel: null,   // Belege-Panel (Annotationen, SF-2, Build 414)
        comPanel: null,   // Kommentar-Panel (SF-3, Build 415)
        // Build 475: "Bericht als Vorlage uebernehmen"
        selUid: null,     // subject_id des gewaehlten Berichts
        selRid: null,     // report_id des gewaehlten Berichts
        xferBtn: null,    // Uebernahme-Schaltflaeche (nur mit templates.edit)
        xferMsg: null     // Rueckmeldezeile der Uebernahme
    };

    // =====================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — genau diese testet vitest.
    // =====================================================================

    // Menschliche Statusbezeichnung (R1-Sprachregelung wie im Renderer).
    function statusLabel(status) {
        switch (status) {
            case 'draft':     return 'Entwurf';
            case 'submitted': return 'Zur Abnahme vorgelegt';
            case 'approved':  return 'Freigegeben';
            case 'final':     return 'Versandt/abgeschlossen';
            default:          return status || 'unbekannt';
        }
    }

    // filterReports: liefert die Berichte je Status. status==='alle' -> alle;
    // Vorgabe der Sicht ist 'submitted' (die zum Gegenlesen vorgelegten). Gibt
    // IMMER ein neues Array (mutiert die Eingabe nicht).
    function filterReports(data, status) {
        var list = (data && data.reports) ? data.reports : [];
        if (!status || status === 'alle') { return list.slice(); }
        return list.filter(function (r) { return r && r.status === status; });
    }

    // renderUrl: URL des read-only Berichtstexts (SF-1). subject_id + report_id
    // werden URL-kodiert (Multilingualitaet/Sonderzeichen unkritisch).
    function renderUrl(uid, rid) {
        return '/api/report/render?subject_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }

    // reportLabel: Zeilentext eines Berichts in der Auswahl.
    function reportLabel(r) {
        if (!r) { return ''; }
        return (r.username || ('uid ' + r.subject_id)) + ' · '
            + (r.title || '(ohne Titel)')
            + ' (' + (r.report_type || '?') + ', Nr. ' + (r.sequence_nr || '?')
            + ') — ' + statusLabel(r.status);
    }

    // selectionKey: stabiler Schluessel eines Berichts (fuer die Markierung).
    function selectionKey(uid, rid) { return String(uid) + ':' + String(rid); }

    // annotationsUrl: URL des Annotations-Support-Views (SF-2, Build 411).
    function annotationsUrl(uid, rid) {
        return '/api/report/annotations?subject_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }

    // categoryLabel: menschliche Kategoriebezeichnung. Fallback = Rohcode,
    // damit eine unbekannte Kategorie sichtbar bleibt (Grundregel 1).
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

    // forumContext: Forenkontext einer Annotation als Text ('—' wenn unbekannt,
    // z.B. wenn fdb.post_aliases die post_id nicht fuehrt).
    function forumContext(item) {
        if (!item || item.topic_id == null || item.forum_id == null) {
            return '—';
        }
        return 'Thema ' + item.topic_id + ' · Unterforum ' + item.forum_id;
    }

    // --- Kommentare (SF-3, Build 415) ---
    // commentsUrl: URL des Union-Lesepfads der Review-Kommentare (SF-3).
    function commentsUrl(uid, rid) {
        return '/api/report/comments?subject_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }

    // commentStatusLabel: menschliche Statusbezeichnung eines Kommentars.
    function commentStatusLabel(status) {
        switch (status) {
            case 'pending':   return 'offen';
            case 'addressed': return 'erledigt';
            case 'dismissed': return 'verworfen';
            case 'revoked':   return 'zurueckgenommen';
            default:          return status || 'unbekannt';
        }
    }

    // reviewerRoleLabel: Rolle der/des Kommentierenden.
    function reviewerRoleLabel(role) {
        switch (role) {
            case 'supervisor': return 'Chef-Ermittlerin';
            case 'lector':     return 'Lektorat';
            default:           return role || '—';
        }
    }

    // isOwnComment: gehoert der Kommentar der aktuell angemeldeten Person?
    // (Nur eigene Kommentare koennen aufgeloest werden — der Server erzwingt es
    // strukturell ueber den Dateipfad; das UI zeigt die Knoepfe entsprechend.)
    function isOwnComment(comment, personId) {
        return !!comment && personId != null
            && Number(comment.reviewer_pid) === Number(personId);
    }

    // =====================================================================
    // 2) DOM-Aufbau.
    // =====================================================================

    // cleanup: Sicht-Artefakte abbauen (wird aus cockpit.js:cleanupView beim
    // Sichtwechsel gerufen). Da renderLectorate mainEl.innerHTML neu setzt,
    // werden Knoten/Listener ohnehin ersetzt; wir loesen zusaetzlich die
    // internen Referenzen, damit nichts haengen bleibt.
    function cleanup() {
        _state.iframe = null;
        _state.selKey = null;
        _state.annPanel = null;
        _state.comPanel = null;
        _state.selUid = null;
        _state.selRid = null;
        _state.xferBtn = null;
        _state.xferMsg = null;
        log('cleanup');
    }

    // hasSelection: hat die/der Nutzer:in aktuell einen Bericht geoeffnet?
    // (Build 479) Genutzt vom SSE-'changed'-Handler in cockpit.js, um einen
    // destruktiven Live-Reload dieser Sicht zu unterdruecken, solange ein
    // Bericht in Sichtung ist. Hintergrund: Das Oeffnen eines Berichts erzeugt
    // ueber /api/report/annotations ZWINGEND einen Lesebeleg im audit_log
    // (Grundregel 1 — der Beleg darf NICHT entfallen); die SSE meldet diesen
    // Ausschlag als 'changed'. Ein Reload wuerde die Auswahl verwerfen, und ein
    // automatisches Wieder-Auswaehlen wuerde erneut auditieren -> Endlosschleife.
    // Deshalb bleibt der Beleg erhalten und STATTDESSEN unterbleibt der Reload,
    // solange hasSelection() true liefert. _state.selKey wird beim Verlassen der
    // Sicht (cleanup) bzw. beim Neuaufbau (renderLectorate) auf null gesetzt.
    function hasSelection() { return _state.selKey !== null; }

    // --- Uebernahme "Bericht als Vorlage" (Build 475) --------------------
    // _setXferMsg: Rueckmeldezeile der Uebernahme setzen ('' leert). kind:
    // '' | 'err' | 'ok'. XSS-sicher (textContent).
    function _setXferMsg(text, kind) {
        if (!_state.xferMsg) { return; }
        _state.xferMsg.textContent = text || '';
        _state.xferMsg.className = 'aiw-lectorate-xfermsg'
            + (kind ? (' is-' + kind) : '');
    }

    // transferError: von cockpit.js gerufen, wenn der Entwurf NICHT geholt
    // werden konnte (Grundregel 1: kein stiller Fehlpfad). Reaktiviert den
    // Knopf, damit die supervisor:in es erneut versuchen kann.
    function transferError(msg) {
        _setXferMsg('Uebernahme fehlgeschlagen: ' + (msg || 'Fehler'), 'err');
        if (_state.xferBtn
            && _state.selUid !== null && _state.selRid !== null) {
            _state.xferBtn.disabled = false;
        }
    }

    // renderLectorate(mainEl, data, opts)
    //   data — Antwort von /api/reports (reports[], scope, ...).
    //   opts — { status?: 'submitted'|'approved'|'final'|'draft'|'alle',
    //            onSelect?: function(uid, rid){}   // Benachrichtigung (Logging)
    //          }
    // Baut: Kopf + Statusfilter + Auswahl-Liste + Vorschau-<iframe>.
    function renderLectorate(mainEl, data, opts) {
        opts = opts || {};
        var status = opts.status || 'submitted';
        log('renderLectorate', { status: status,
            count: (data && data.count) });

        // Vollstaendiger Neuaufbau (kein optimistisches UI, Grundregel 1).
        mainEl.innerHTML = '';
        _state.iframe = null;
        _state.selKey = null;
        _state.annPanel = null;
        _state.comPanel = null;
        _state.selUid = null;
        _state.selRid = null;
        _state.xferBtn = null;
        _state.xferMsg = null;

        var wrap = document.createElement('div');
        wrap.className = 'aiw-lectorate';

        var h = document.createElement('h2');
        h.textContent = 'Lektorat — Gegenlesen';
        wrap.appendChild(h);

        // Scope-Hinweis (der Server filtert scope-korrekt; wir benennen ihn).
        var meta = document.createElement('p');
        meta.className = 'aiw-lectorate-meta';
        meta.textContent = 'Sichtbarer Umfang: ' + ((data && data.scope)
            || 'unbekannt') + '. Vorgelegt zum Gegenlesen sind Berichte im '
            + 'Status „Zur Abnahme vorgelegt".';
        wrap.appendChild(meta);

        // --- Statusfilter ------------------------------------------------
        var bar = document.createElement('div');
        bar.className = 'aiw-lectorate-toolbar';
        var lbl = document.createElement('label');
        lbl.textContent = 'Status: ';
        var sel = document.createElement('select');
        sel.className = 'aiw-lectorate-status';
        [['submitted', 'Zur Abnahme vorgelegt'], ['approved', 'Freigegeben'],
         ['final', 'Versandt'], ['draft', 'Entwurf'], ['alle', 'Alle']]
            .forEach(function (o) {
                var opt = document.createElement('option');
                opt.value = o[0]; opt.textContent = o[1];
                if (o[0] === status) { opt.selected = true; }
                sel.appendChild(opt);
            });
        // Reiner Lesewechsel: bei Statuswechsel die Liste neu rendern (die
        // Daten liegen bereits vor; kein erneuter Serverabruf noetig).
        // Build 480 (Bugfix): onTransferToTemplate MUSS mit durchgereicht werden.
        // Der Uebernahme-Knopf ("Als Vorlage uebernehmen") wird in
        // renderLectorate nur erzeugt, wenn dieser Callback vorliegt
        // (canTransfer = typeof opts.onTransferToTemplate === 'function'). Fehlte
        // er beim Neu-Rendern nach Statuswechsel, verschwand der Knopf dauerhaft
        // (praktisch funktionslos, da man zum Sichten meist den Status filtert).
        // onSelect wurde bereits durchgereicht; onTransferToTemplate war die
        // Luecke.
        sel.addEventListener('change', function () {
            renderLectorate(mainEl, data, {
                status: sel.value,
                onSelect: opts.onSelect,
                onTransferToTemplate: opts.onTransferToTemplate
            });
        });
        lbl.appendChild(sel);
        bar.appendChild(lbl);
        wrap.appendChild(bar);

        // --- Auswahl-Liste ----------------------------------------------
        var rows = filterReports(data, status);
        var list = document.createElement('div');
        list.className = 'aiw-lectorate-list';

        if (!rows.length) {
            var empty = document.createElement('p');
            empty.className = 'aiw-lectorate-empty';
            empty.textContent = 'Keine Berichte im gewaehlten Status.';
            list.appendChild(empty);
        }

        // --- Uebernahme-Leiste (Build 475): "Bericht als Vorlage uebernehmen".
        // Nur wenn der Aufrufer (cockpit.js) einen Callback liefert — das setzt
        // er ausschliesslich bei vorhandenem Recht templates.edit. Der Knopf ist
        // erst aktiv, sobald ein Bericht gewaehlt wurde (selUid/selRid gesetzt).
        var canTransfer = (typeof opts.onTransferToTemplate === 'function');
        if (canTransfer) {
            var xbar = document.createElement('div');
            xbar.className = 'aiw-lectorate-xferbar';
            var xbtn = document.createElement('button');
            xbtn.type = 'button';
            xbtn.className = 'aiw-lectorate-xfer';
            xbtn.textContent = 'Als Vorlage uebernehmen';
            xbtn.disabled = true;   // erst nach Berichtsauswahl
            xbtn.title = 'Aus dem gewaehlten Bericht eine Dokumentvorlage '
                + 'erzeugen (fallbezogene Platzhalter-Werte werden entfernt).';
            xbtn.addEventListener('click', function () {
                if (_state.selUid === null || _state.selRid === null) { return; }
                _setXferMsg('Uebernehme Bericht in Vorlage …', '');
                xbtn.disabled = true;
                opts.onTransferToTemplate(_state.selUid, _state.selRid);
            });
            _state.xferBtn = xbtn;
            xbar.appendChild(xbtn);
            var xmsg = document.createElement('span');
            xmsg.className = 'aiw-lectorate-xfermsg';
            _state.xferMsg = xmsg;
            xbar.appendChild(xmsg);
            wrap.appendChild(xbar);
        }

        // --- Vorschau-Bereich: Berichtstext (iframe) + Belege (Annotationen) -
        // Nebeneinander (breit) bzw. gestapelt (schmal) via CSS (flex-wrap).
        var preview = document.createElement('div');
        preview.className = 'aiw-lectorate-preview-wrap';

        var frame = document.createElement('iframe');
        frame.className = 'aiw-lectorate-preview';
        frame.title = 'Berichtstext (read-only)';
        frame.setAttribute('sandbox', 'allow-same-origin');
        _state.iframe = frame;

        // Belege-Panel (SF-2, Slice 2). Startzustand: Hinweis.
        var ann = document.createElement('div');
        ann.className = 'aiw-lectorate-annotations';
        _state.annPanel = ann;
        _annHint('Bericht links auswaehlen, um die zugrunde liegenden Belege '
            + 'zu sehen.');

        preview.appendChild(frame);
        preview.appendChild(ann);

        rows.forEach(function (r) {
            var key = selectionKey(r.subject_id, r.id);
            var row = document.createElement('button');
            row.type = 'button';
            row.className = 'aiw-lectorate-item';
            row.setAttribute('data-uid', String(r.subject_id));
            row.setAttribute('data-rid', String(r.id));
            row.setAttribute('data-key', key);
            row.textContent = reportLabel(r);
            row.addEventListener('click', function () {
                // Auswahl markieren.
                var prev = list.querySelector('.aiw-lectorate-item.is-active');
                if (prev) { prev.classList.remove('is-active'); }
                row.classList.add('is-active');
                _state.selKey = key;
                // Build 475: gewaehlten Bericht fuer die Uebernahme merken und
                // den Uebernahme-Knopf aktivieren (falls vorhanden).
                _state.selUid = r.subject_id;
                _state.selRid = r.id;
                if (_state.xferBtn) {
                    _state.xferBtn.disabled = false;
                    _setXferMsg('', '');
                }
                // Berichtstext read-only in den <iframe> laden.
                frame.src = renderUrl(r.subject_id, r.id);
                // Belege- UND Kommentar-Panel auf "laedt" setzen; die Abrufe
                // laufen ueber opts.onSelect (cockpit.js holt Annotationen +
                // Kommentare und ruft renderAnnotations/renderComments).
                annotationsLoading();
                commentsLoading();
                log('select', key, frame.src);
                if (typeof opts.onSelect === 'function') {
                    opts.onSelect(r.subject_id, r.id);
                }
            });
            list.appendChild(row);
        });

        wrap.appendChild(list);
        wrap.appendChild(preview);

        // --- Kommentar-Panel (SF-3, Slice 3) unter dem Vorschau-Bereich. ----
        var com = document.createElement('div');
        com.className = 'aiw-lectorate-comments';
        _state.comPanel = com;
        _comHint('Bericht auswaehlen, um Kommentare zu sehen und zu erfassen.');
        wrap.appendChild(com);

        mainEl.appendChild(wrap);
        return wrap;
    }

    // --- Belege-Panel (SF-2) ---------------------------------------------

    // _annHint: setzt das Belege-Panel auf EINEN Hinweistext (ersetzt Inhalt).
    function _annHint(msg) {
        if (!_state.annPanel) { return; }
        _state.annPanel.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'aiw-lectorate-ann-hint';
        p.textContent = msg;
        _state.annPanel.appendChild(p);
    }

    // Ladehinweis waehrend der Abruf von /api/report/annotations laeuft.
    function annotationsLoading() { _annHint('Belege werden geladen …'); }

    // Fehlerhinweis (kein stiller Fehlpfad, Grundregel 1).
    function annotationsError(msg) {
        _annHint('Belege konnten nicht geladen werden: ' + (msg || 'Fehler'));
    }

    // renderAnnotations(data): baut das Belege-Panel aus der SF-2-Antwort
    // (data.items). Ohne aktives Panel (Sicht verlassen) ein No-op.
    function renderAnnotations(data) {
        var panel = _state.annPanel;
        if (!panel) { return; }
        panel.innerHTML = '';
        var items = (data && data.items) ? data.items : [];

        var head = document.createElement('h3');
        head.className = 'aiw-lectorate-ann-head';
        head.textContent = 'Belege (' + items.length + ')';
        panel.appendChild(head);

        if (!items.length) {
            var p = document.createElement('p');
            p.className = 'aiw-lectorate-ann-hint';
            p.textContent = 'Zu diesem Bericht sind keine Belege verankert.';
            panel.appendChild(p);
            return;
        }

        items.forEach(function (it) {
            var box = document.createElement('div');
            box.className = 'aiw-lectorate-ann-item';
            if (it.missing) { box.classList.add('is-missing'); }
            if (it.deleted) { box.classList.add('is-deleted'); }

            var cat = document.createElement('span');
            cat.className = 'aiw-lectorate-ann-cat';
            cat.textContent = categoryLabel(it.category);
            box.appendChild(cat);

            var txt = document.createElement('div');
            txt.className = 'aiw-lectorate-ann-text';
            // Fehlt die Annotation (Anker zeigt ins Leere) -> sichtbar machen.
            txt.textContent = it.missing
                ? '⚠ Beleg nicht (mehr) vorhanden (Annotation #'
                    + it.annotation_id + ')'
                : (it.text || '');
            box.appendChild(txt);

            var metaLine = document.createElement('div');
            metaLine.className = 'aiw-lectorate-ann-meta';
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

    // --- Kommentar-Panel (SF-3) ------------------------------------------

    // _comHint: setzt das Kommentar-Panel auf EINEN Hinweistext.
    function _comHint(msg) {
        if (!_state.comPanel) { return; }
        _state.comPanel.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'aiw-lectorate-com-hint';
        p.textContent = msg;
        _state.comPanel.appendChild(p);
    }

    function commentsLoading() { _comHint('Kommentare werden geladen …'); }
    function commentsError(msg) {
        _comHint('Kommentar-Aktion fehlgeschlagen: ' + (msg || 'Fehler'));
    }

    // renderComments(data, opts): baut Formular (neuer Kommentar) + Liste der
    // vorhandenen Kommentare (Union aller Prueferinnen) in das Kommentar-Panel.
    //   data — Antwort von /api/report/comments {subject_id, report_id, comments[]}
    //   opts — { personId, onAdd(body), onResolve(body) }
    function renderComments(data, opts) {
        var panel = _state.comPanel;
        if (!panel) { return; }
        opts = opts || {};
        panel.innerHTML = '';
        var comments = (data && data.comments) ? data.comments : [];
        var uid = data ? data.subject_id : null;
        var rid = data ? data.report_id : null;

        var head = document.createElement('h3');
        head.className = 'aiw-lectorate-com-head';
        head.textContent = 'Kommentare (' + comments.length + ')';
        panel.appendChild(head);

        // --- Formular: neuen Kommentar erfassen --------------------------
        var form = document.createElement('form');
        form.className = 'aiw-lectorate-com-form';

        var ta = document.createElement('textarea');
        ta.className = 'aiw-lectorate-com-text';
        ta.setAttribute('rows', '2');
        ta.setAttribute('placeholder', 'Kommentar zum Bericht …');
        form.appendChild(ta);

        var blockIn = document.createElement('input');
        blockIn.type = 'text';
        blockIn.className = 'aiw-lectorate-com-block';
        blockIn.setAttribute('placeholder', 'Block-ID (optional)');
        form.appendChild(blockIn);

        var sug = document.createElement('textarea');
        sug.className = 'aiw-lectorate-com-suggest';
        sug.setAttribute('rows', '1');
        sug.setAttribute('placeholder', 'Aenderungsvorschlag (optional)');
        form.appendChild(sug);

        var submit = document.createElement('button');
        submit.type = 'submit';
        submit.className = 'aiw-lectorate-com-submit';
        submit.textContent = 'Kommentar hinzufuegen';
        form.appendChild(submit);

        var errBox = document.createElement('div');
        errBox.className = 'aiw-lectorate-com-formerr';
        form.appendChild(errBox);

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            errBox.textContent = '';
            var text = (ta.value || '').trim();
            if (!text) {
                errBox.textContent = 'Bitte einen Kommentartext eingeben.';
                return;
            }
            var body = {
                subject_id: uid, report_id: rid,
                block_id: (blockIn.value || '').trim() || null,
                comment_text: text,
                suggested_content: (sug.value || '').trim() || null
            };
            log('addComment', body);
            if (typeof opts.onAdd === 'function') { opts.onAdd(body); }
        });
        panel.appendChild(form);

        // --- Liste vorhandener Kommentare --------------------------------
        if (!comments.length) {
            var none = document.createElement('p');
            none.className = 'aiw-lectorate-com-hint';
            none.textContent = 'Noch keine Kommentare zu diesem Bericht.';
            panel.appendChild(none);
            return;
        }

        comments.forEach(function (c) {
            var box = document.createElement('div');
            box.className = 'aiw-lectorate-com-item';
            box.setAttribute('data-status', c.status || '');
            if (c.status && c.status !== 'pending') {
                box.classList.add('is-resolved');
            }

            var top = document.createElement('div');
            top.className = 'aiw-lectorate-com-top';
            var role = document.createElement('span');
            role.className = 'aiw-lectorate-com-role';
            role.textContent = reviewerRoleLabel(c.reviewer_role);
            top.appendChild(role);
            var st = document.createElement('span');
            st.className = 'aiw-lectorate-com-status';
            st.textContent = commentStatusLabel(c.status);
            top.appendChild(st);
            box.appendChild(top);

            var body = document.createElement('div');
            body.className = 'aiw-lectorate-com-body';
            body.textContent = c.comment_text || '';
            box.appendChild(body);

            if (c.suggested_content) {
                var sugv = document.createElement('div');
                sugv.className = 'aiw-lectorate-com-suggestion';
                sugv.textContent = 'Vorschlag: ' + c.suggested_content;
                box.appendChild(sugv);
            }

            var meta = document.createElement('div');
            meta.className = 'aiw-lectorate-com-meta';
            var mbits = [];
            if (c.block_id) { mbits.push('Block ' + c.block_id); }
            mbits.push('Prueferin #' + c.reviewer_pid);
            meta.textContent = mbits.join(' · ');
            box.appendChild(meta);

            // Aufloesen NUR fuer eigene, offene Kommentare (Server erzwingt es
            // strukturell; das UI zeigt die Knoepfe nur, wo sie wirken).
            if (isOwnComment(c, opts.personId) && c.status === 'pending') {
                var actions = document.createElement('div');
                actions.className = 'aiw-lectorate-com-actions';
                [['addressed', 'Als erledigt'], ['dismissed', 'Verwerfen']]
                    .forEach(function (a) {
                        var btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = 'aiw-lectorate-com-resolve';
                        btn.setAttribute('data-status', a[0]);
                        btn.textContent = a[1];
                        btn.addEventListener('click', function () {
                            var rb = { subject_id: uid, comment_id: c.comment_id,
                                       status: a[0] };
                            log('resolveComment', rb);
                            if (typeof opts.onResolve === 'function') {
                                opts.onResolve(rb);
                            }
                        });
                        actions.appendChild(btn);
                    });
                box.appendChild(actions);
            }

            panel.appendChild(box);
        });
    }

    // --- oeffentliche API -------------------------------------------------
    window.AIWCockpitLectorate = {
        // reine Funktionen (vitest)
        statusLabel: statusLabel,
        filterReports: filterReports,
        renderUrl: renderUrl,
        reportLabel: reportLabel,
        selectionKey: selectionKey,
        annotationsUrl: annotationsUrl,   // SF-2 (Build 414)
        categoryLabel: categoryLabel,
        forumContext: forumContext,
        commentsUrl: commentsUrl,         // SF-3 (Build 415)
        commentStatusLabel: commentStatusLabel,
        reviewerRoleLabel: reviewerRoleLabel,
        isOwnComment: isOwnComment,
        // DOM
        renderLectorate: renderLectorate,
        renderAnnotations: renderAnnotations,   // Belege-Panel (SF-2)
        annotationsLoading: annotationsLoading,
        annotationsError: annotationsError,
        renderComments: renderComments,         // Kommentar-Panel (SF-3)
        commentsLoading: commentsLoading,
        commentsError: commentsError,
        transferError: transferError,           // Uebernahme B6->Vorlage (Build 475)
        hasSelection: hasSelection,             // SSE-Reload-Schutz (Build 479)
        cleanup: cleanup
    };
    log('Modul geladen.');
})();
