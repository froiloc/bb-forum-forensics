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
 * Version: v0.7.413 · Build: 413 · 2026-07-14
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
        annPanel: null    // Belege-Panel (Annotationen, SF-2, Build 414)
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

    // renderUrl: URL des read-only Berichtstexts (SF-1). user_id + report_id
    // werden URL-kodiert (Multilingualitaet/Sonderzeichen unkritisch).
    function renderUrl(uid, rid) {
        return '/api/report/render?user_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }

    // reportLabel: Zeilentext eines Berichts in der Auswahl.
    function reportLabel(r) {
        if (!r) { return ''; }
        return (r.username || ('uid ' + r.user_id)) + ' · '
            + (r.title || '(ohne Titel)')
            + ' (' + (r.report_type || '?') + ', Nr. ' + (r.sequence_nr || '?')
            + ') — ' + statusLabel(r.status);
    }

    // selectionKey: stabiler Schluessel eines Berichts (fuer die Markierung).
    function selectionKey(uid, rid) { return String(uid) + ':' + String(rid); }

    // annotationsUrl: URL des Annotations-Support-Views (SF-2, Build 411).
    function annotationsUrl(uid, rid) {
        return '/api/report/annotations?user_id=' + encodeURIComponent(uid)
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
        log('cleanup');
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
        sel.addEventListener('change', function () {
            renderLectorate(mainEl, data,
                { status: sel.value, onSelect: opts.onSelect });
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
            var key = selectionKey(r.user_id, r.id);
            var row = document.createElement('button');
            row.type = 'button';
            row.className = 'aiw-lectorate-item';
            row.setAttribute('data-uid', String(r.user_id));
            row.setAttribute('data-rid', String(r.id));
            row.setAttribute('data-key', key);
            row.textContent = reportLabel(r);
            row.addEventListener('click', function () {
                // Auswahl markieren.
                var prev = list.querySelector('.aiw-lectorate-item.is-active');
                if (prev) { prev.classList.remove('is-active'); }
                row.classList.add('is-active');
                _state.selKey = key;
                // Berichtstext read-only in den <iframe> laden.
                frame.src = renderUrl(r.user_id, r.id);
                // Belege-Panel auf "laedt" setzen; der eigentliche Abruf laeuft
                // ueber opts.onSelect (cockpit.js holt /api/report/annotations
                // und ruft danach renderAnnotations).
                annotationsLoading();
                log('select', key, frame.src);
                if (typeof opts.onSelect === 'function') {
                    opts.onSelect(r.user_id, r.id);
                }
            });
            list.appendChild(row);
        });

        wrap.appendChild(list);
        wrap.appendChild(preview);
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
        // DOM
        renderLectorate: renderLectorate,
        renderAnnotations: renderAnnotations,   // Belege-Panel (SF-2)
        annotationsLoading: annotationsLoading,
        annotationsError: annotationsError,
        cleanup: cleanup
    };
    log('Modul geladen.');
})();
