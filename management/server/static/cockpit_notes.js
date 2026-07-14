// =============================================================================
// management/server/static/cockpit_notes.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Betreuungs-Notizen
// =============================================================================
// Zweck:
//   Rendert das PINBOARD der Ermittler-Betreuung ("Post-its", Build 406):
//   freie Merkzettel der Leitung zu den Belangen einzelner Mitarbeiter. Jede
//   Karte folgt der GIT-COMMIT-METAPHER — die erste Zeile ist die Ueberschrift
//   (immer sichtbar), alle weiteren Zeilen erscheinen erst nach dem Aufklappen.
//   Farbe + Schlagworte (Tags), Status 'abarbeiten' (offen/erledigt),
//   Volltextsuche + Filter (Farbe/Status/Tag) rein CLIENT-seitig (sofort, ohne
//   Serverrunde), Umschalter Aktiv/Archiv (Lesewechsel am Server), Anlegen/
//   Bearbeiten/Duplizieren/Archivieren/Wiederherstellen.
//
//   ARBEITSTEILUNG mit der Shell (cockpit.js): dieses Modul RENDERT nur und
//   meldet Absichten ueber Callbacks zurueck. Die Shell fuehrt fetch/POST aus
//   (Schreib-Token X-AIW-Token) und laedt danach NEU — kein optimistisches UI,
//   die Oberflaeche zeigt nur bestaetigt geschriebene Zustaende (Grundregel 1).
//   Drag&Drop-Ordnung folgt in BLOCK 4 (dieser Build ordnet nach sort_index,
//   den der Server liefert).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'.
//   2) Exzessives DEV-Debug-Logging, zur Laufzeit umschaltbar (PROD: aus).
//   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
//   4) REINE Funktionen (Filtern/Suchen/Parsen/Farbe) fassen NIE das DOM an und
//      sind per Vitest testbar; nur die render*/open*-Funktionen beruehren
//      document. UMD-artiger Ausgang -> die Tests pruefen den ECHTEN Code
//      (keine 'gruen-aber-tot'-Kopie).
//
// SICHERHEIT (XSS): saemtlicher variabler Text (Ueberschrift, Rumpf, Tags,
//   Anzeigenamen) wird AUSSCHLIESSLICH via textContent gesetzt, NIE via
//   innerHTML. Die Freitexte stammen aus der RBAC-gekapselten Fachschicht, sind
//   aber grundsaetzlich als fremdbestimmt zu behandeln.
//
// Version: v0.7.406 · Build: 406 · 2026-07-14
// =============================================================================

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // DEV-Debug-Logging. Zur Laufzeit umschaltbar (window.AIW_COCKPIT_DEBUG),
    // exakt wie in cockpit.js — ein gemeinsames Flag fuer die ganze Oberflaeche.
    // -------------------------------------------------------------------------
    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Notizen]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM). Per Vitest testbar.
    // =========================================================================

    // Fallback-Kartenfarben, falls der Server-Katalog fehlt. Bewusst helle,
    // Post-it-artige Toene; der linke Rand ist eine gesaettigtere Variante.
    // Die Codes sind mit note_colors.py (Backend) abgestimmt.
    var COLOR_BG = {
        gelb: '#fef3c7', rosa: '#fde2e4', gruen: '#dcfce7', blau: '#dbeafe',
        orange: '#ffedd5', lila: '#ede9fe', grau: '#e5e7eb'
    };
    var COLOR_EDGE = {
        gelb: '#f59e0b', rosa: '#e5679a', gruen: '#22c55e', blau: '#3b82f6',
        orange: '#f97316', lila: '#8b5cf6', grau: '#9ca3af'
    };

    // colorBg / colorEdge: Farbcode -> Hex. Unbekannt -> 'grau' (nie leer,
    // damit eine spaeter additiv ergaenzte Server-Farbe wenigstens neutral
    // dargestellt wird, statt die Karte transparent zu lassen).
    function colorBg(code) { return COLOR_BG[code] || COLOR_BG.grau; }
    function colorEdge(code) { return COLOR_EDGE[code] || COLOR_EDGE.grau; }

    // parseCommit: Git-Commit-Metapher. Trennt einen Freitext in Ueberschrift
    // (erste nicht-leere Zeile) und Rumpf (Rest, fuehrende Leerzeilen entfernt).
    // Rein: keine Seiteneffekte, kein DOM. Basis fuer den Editor.
    function parseCommit(text) {
        var s = (text == null ? '' : String(text)).replace(/\r\n/g, '\n');
        var nl = s.indexOf('\n');
        if (nl < 0) {
            return { title: s.trim(), body: '' };
        }
        var title = s.slice(0, nl).trim();
        var body = s.slice(nl + 1).replace(/^\n+/, '');
        return { title: title, body: body };
    }

    // matchesSearch: True, wenn der Suchbegriff (case-insensitiv) in
    // Ueberschrift, Rumpf oder einem Tag vorkommt. Leerer Begriff -> True.
    function matchesSearch(note, q) {
        q = (q || '').trim().toLowerCase();
        if (!q) { return true; }
        if ((note.title || '').toLowerCase().indexOf(q) >= 0) { return true; }
        if ((note.body || '').toLowerCase().indexOf(q) >= 0) { return true; }
        var tags = note.tags || [];
        for (var i = 0; i < tags.length; i++) {
            if (String(tags[i]).toLowerCase().indexOf(q) >= 0) { return true; }
        }
        return false;
    }

    // matchesFilter: prueft die Feinfilter (Farbe/Status/Tag). Leerer Wert je
    // Dimension = 'egal'. Alle gesetzten Dimensionen muessen zutreffen (UND).
    function matchesFilter(note, f) {
        f = f || {};
        if (f.color && note.color !== f.color) { return false; }
        if (f.status && note.status !== f.status) { return false; }
        if (f.tag && (note.tags || []).indexOf(f.tag) < 0) { return false; }
        return true;
    }

    // filterNotes: wendet Suche + Feinfilter auf eine Notizliste an. Reine
    // Projektion (mutiert die Eingabe nicht).
    function filterNotes(notes, f) {
        f = f || {};
        return (notes || []).filter(function (n) {
            return matchesSearch(n, f.search) && matchesFilter(n, f);
        });
    }

    // allTags: sortierte, deduplizierte Menge aller Tags einer Notizliste
    // (fuer das Tag-Filter-Auswahlfeld).
    function allTags(notes) {
        var seen = {};
        (notes || []).forEach(function (n) {
            (n.tags || []).forEach(function (t) { seen[t] = true; });
        });
        return Object.keys(seen).sort();
    }

    // =========================================================================
    // 2) DOM-HELFER (winzig, damit der Render-Code lesbar bleibt).
    // =========================================================================
    function el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (text != null) { e.textContent = text; }   // NIE innerHTML
        return e;
    }
    function clear(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

    // Modul-weiter UI-Zustand: bleibt ueber Reloads erhalten (ein Schreibvorgang
    // laedt das Board neu; Suche/Filter/aufgeklappte Karten sollen NICHT
    // zuruecksetzen). Bewusst gekapselt, nur hier sichtbar.
    var ui = { search: '', color: '', status: '', tag: '', open: {} };

    // =========================================================================
    // 3) RENDER: Board (Kopf + Filterleiste + Kartenraster).
    // =========================================================================
    function renderNotes(mainEl, data, cb) {
        cb = cb || {};
        var notes = (data && data.notes) || [];
        var colors = (data && data.colors) || [];
        var persons = (data && data.persons) || [];
        var archived = cb.archived === true;
        clear(mainEl);

        var wrap = el('section', 'aiw-notes');

        // --- Kopfzeile: Titel + Rueckmeldung + Archiv-Umschalter + Neu -------
        var head = el('div', 'aiw-notes-head');
        head.appendChild(el('h2', 'aiw-notes-title',
            archived ? 'Betreuungs-Notizen — Archiv'
                     : 'Betreuungs-Notizen'));

        var msg = el('span', 'aiw-notes-msg');
        if (cb.pendingMsg) {
            msg.textContent = cb.pendingMsg.text;
            msg.classList.add(cb.pendingMsg.error ? 'is-error' : 'is-ok');
        }
        head.appendChild(msg);

        var spacer = el('span', 'aiw-notes-spacer');
        head.appendChild(spacer);

        // Archiv-Umschalter (reiner Lesewechsel ueber die Shell).
        var arcBtn = el('button', 'aiw-btn aiw-btn-ghost',
            archived ? '← Zurueck zum Board' : 'Archiv ansehen');
        arcBtn.type = 'button';
        arcBtn.addEventListener('click', function () {
            if (cb.onToggleArchived) { cb.onToggleArchived(!archived); }
        });
        head.appendChild(arcBtn);

        // Neue Notiz — nur im aktiven Board (im Archiv legt man nichts an).
        if (!archived) {
            var newBtn = el('button', 'aiw-btn aiw-btn-primary',
                '+ Neue Notiz');
            newBtn.type = 'button';
            newBtn.addEventListener('click', function () {
                openEditor({
                    colors: colors, persons: persons, note: null,
                    onSubmit: function (payload) {
                        if (cb.onCreate) { cb.onCreate(payload); }
                    }
                });
            });
            head.appendChild(newBtn);
        }
        wrap.appendChild(head);

        // --- Filterleiste: Suche + Farbe + Status + Tag ----------------------
        var bar = el('div', 'aiw-notes-filter');

        var search = el('input', 'aiw-notes-search');
        search.type = 'search';
        search.placeholder = 'Suchen (Ueberschrift, Text, Tags) …';
        search.value = ui.search;
        bar.appendChild(search);

        var colorSel = el('select', 'aiw-notes-sel');
        colorSel.appendChild(optionEl('', 'Farbe: alle'));
        colors.forEach(function (c) {
            colorSel.appendChild(optionEl(c.code, c.label));
        });
        colorSel.value = ui.color;
        bar.appendChild(colorSel);

        var statusSel = el('select', 'aiw-notes-sel');
        statusSel.appendChild(optionEl('', 'Status: alle'));
        statusSel.appendChild(optionEl('offen', 'offen'));
        statusSel.appendChild(optionEl('erledigt', 'erledigt'));
        statusSel.value = ui.status;
        bar.appendChild(statusSel);

        var tagSel = el('select', 'aiw-notes-sel');
        function rebuildTagOptions() {
            clear(tagSel);
            tagSel.appendChild(optionEl('', 'Tag: alle'));
            allTags(notes).forEach(function (t) {
                tagSel.appendChild(optionEl(t, '#' + t));
            });
            tagSel.value = ui.tag;
        }
        rebuildTagOptions();
        bar.appendChild(tagSel);

        wrap.appendChild(bar);

        // --- Kartenraster ----------------------------------------------------
        var board = el('div', 'aiw-notes-board');
        wrap.appendChild(board);

        // countLine: zeigt, wie viele Karten der Filter durchlaesst (Grundregel
        // 1: kein stiller Leerzustand — man sieht, dass gefiltert wird).
        var countLine = el('div', 'aiw-notes-count');
        wrap.appendChild(countLine);

        mainEl.appendChild(wrap);

        // applyFilters: baut NUR das Kartenraster neu (Filterleiste bleibt,
        // damit das Suchfeld den Fokus/Cursor behaelt). Reines Neuzeichnen aus
        // der bereits geladenen Notizliste — kein Serverzugriff.
        function applyFilters() {
            var shown = filterNotes(notes, ui);
            clear(board);
            if (!notes.length) {
                board.appendChild(el('div', 'aiw-notes-empty',
                    archived ? 'Kein Eintrag im Archiv.'
                             : 'Noch keine Notiz. Lege mit "+ Neue Notiz" an.'));
            } else if (!shown.length) {
                board.appendChild(el('div', 'aiw-notes-empty',
                    'Kein Treffer fuer die aktuellen Filter.'));
            } else {
                shown.forEach(function (n) {
                    board.appendChild(renderCard(n, cb, colors, persons));
                });
            }
            countLine.textContent = shown.length + ' von ' + notes.length
                + ' Notiz(en) angezeigt'
                + (archived ? ' (Archiv)' : '');
        }

        // Ereignisse: jede Filter-/Sucheingabe aktualisiert ui + zeichnet neu.
        search.addEventListener('input', function () {
            ui.search = search.value; applyFilters();
        });
        colorSel.addEventListener('change', function () {
            ui.color = colorSel.value; applyFilters();
        });
        statusSel.addEventListener('change', function () {
            ui.status = statusSel.value; applyFilters();
        });
        tagSel.addEventListener('change', function () {
            ui.tag = tagSel.value; applyFilters();
        });

        applyFilters();
        log('renderNotes:', notes.length, 'Notizen', archived ? '(Archiv)' : '');
        return { applyFilters: applyFilters };
    }

    function optionEl(value, label) {
        var o = el('option', null, label);
        o.value = value;
        return o;
    }

    // -------------------------------------------------------------------------
    // renderCard: EINE Post-it-Karte. Git-Commit-Metapher: Ueberschrift immer
    // sichtbar, Rumpf erst nach Aufklappen (Zustand in ui.open gemerkt, damit
    // ein Reload die Karte nicht wieder zuklappt).
    // -------------------------------------------------------------------------
    function renderCard(note, cb, colors, persons) {
        var card = el('article', 'aiw-note');
        card.style.background = colorBg(note.color);
        card.style.borderLeft = '6px solid ' + colorEdge(note.color);
        if (note.status === 'erledigt') { card.classList.add('is-done'); }
        if (note.is_archived) { card.classList.add('is-archived'); }
        if (note.pinned) { card.classList.add('is-pinned'); }

        var hasBody = !!(note.body && note.body.trim());
        var expanded = ui.open[note.id] === true;

        // --- Kopf: Status-Haken + Ueberschrift + Aufklapp-Chevron ------------
        var top = el('div', 'aiw-note-top');

        // 'abarbeiten': Haken schaltet offen <-> erledigt (nur aktives Board).
        if (!note.is_archived) {
            var chk = el('input', 'aiw-note-check');
            chk.type = 'checkbox';
            chk.checked = (note.status === 'erledigt');
            chk.title = 'abarbeiten (offen/erledigt)';
            chk.addEventListener('change', function () {
                if (cb.onUpdate) {
                    cb.onUpdate({ id: note.id,
                        status: chk.checked ? 'erledigt' : 'offen' });
                }
            });
            top.appendChild(chk);
        }

        var titleWrap = el('div', 'aiw-note-titlewrap');
        var title = el('span', 'aiw-note-title', note.title || '(ohne Titel)');
        titleWrap.appendChild(title);
        top.appendChild(titleWrap);

        var chevron = null;
        if (hasBody) {
            chevron = el('button', 'aiw-note-chevron', expanded ? '▾' : '▸');
            chevron.type = 'button';
            chevron.title = expanded ? 'Zuklappen' : 'Aufklappen';
            top.appendChild(chevron);
        }
        card.appendChild(top);

        // --- Meta-Zeile: Betroffene:r + Tags ---------------------------------
        var meta = el('div', 'aiw-note-meta');
        if (note.subject_display_name) {
            meta.appendChild(el('span', 'aiw-note-subject',
                '⚑ ' + note.subject_display_name));
        }
        (note.tags || []).forEach(function (t) {
            meta.appendChild(el('span', 'aiw-note-tag', '#' + t));
        });
        if (meta.childNodes.length) { card.appendChild(meta); }

        // --- Rumpf (aufklappbar) --------------------------------------------
        var body = null;
        if (hasBody) {
            body = el('div', 'aiw-note-body');
            body.textContent = note.body;                 // NIE innerHTML
            body.style.display = expanded ? 'block' : 'none';
            card.appendChild(body);

            var toggle = function () {
                expanded = !expanded;
                ui.open[note.id] = expanded;
                body.style.display = expanded ? 'block' : 'none';
                chevron.textContent = expanded ? '▾' : '▸';
                chevron.title = expanded ? 'Zuklappen' : 'Aufklappen';
            };
            chevron.addEventListener('click', toggle);
            // Auch Klick auf die Ueberschrift klappt auf/zu (bequemer).
            title.classList.add('is-clickable');
            title.addEventListener('click', toggle);
        }

        // --- Aktionsleiste ---------------------------------------------------
        var actions = el('div', 'aiw-note-actions');
        if (note.is_archived) {
            actions.appendChild(actionBtn('Wiederherstellen', function () {
                if (cb.onRestore) { cb.onRestore(note.id); }
            }));
        } else {
            actions.appendChild(actionBtn('Bearbeiten', function () {
                openEditor({
                    colors: colors, persons: persons, note: note,
                    onSubmit: function (payload) {
                        if (cb.onUpdate) { cb.onUpdate(payload); }
                    }
                });
            }));
            actions.appendChild(actionBtn('Duplizieren', function () {
                if (cb.onDuplicate) { cb.onDuplicate(note.id); }
            }));
            actions.appendChild(actionBtn('Archivieren', function () {
                if (cb.onArchive) { cb.onArchive(note.id); }
            }, 'is-danger'));
        }
        card.appendChild(actions);

        return card;
    }

    function actionBtn(label, handler, extra) {
        var b = el('button', 'aiw-note-act' + (extra ? ' ' + extra : ''), label);
        b.type = 'button';
        b.addEventListener('click', handler);
        return b;
    }

    // =========================================================================
    // 4) EDITOR-MODAL (Anlegen/Bearbeiten). Ein einziges Textfeld traegt die
    //    Git-Commit-Metapher: erste Zeile = Ueberschrift, Rest = Rumpf.
    // =========================================================================
    function openEditor(opts) {
        opts = opts || {};
        var note = opts.note;               // null = neu
        var colors = opts.colors || [];
        var persons = opts.persons || [];
        var isEdit = !!note;

        var overlay = el('div', 'aiw-modal-overlay');
        var dialog = el('div', 'aiw-modal');
        dialog.appendChild(el('h3', 'aiw-modal-title',
            isEdit ? 'Notiz bearbeiten' : 'Neue Notiz'));

        // Freitext (Commit-Metapher). Vorbefuellt aus Titel + Rumpf.
        dialog.appendChild(el('label', 'aiw-modal-label',
            'Text (erste Zeile = Ueberschrift, weitere Zeilen = Details)'));
        var ta = el('textarea', 'aiw-modal-text');
        ta.rows = 8;
        ta.value = isEdit
            ? (note.title + (note.body ? '\n' + note.body : ''))
            : '';
        dialog.appendChild(ta);

        // Farbwahl als Swatches (klickbar).
        dialog.appendChild(el('label', 'aiw-modal-label', 'Farbe'));
        var sw = el('div', 'aiw-modal-swatches');
        var chosenColor = (isEdit && note.color) ? note.color
            : (colors[0] ? colors[0].code : 'gelb');
        (colors.length ? colors : [{ code: 'gelb', label: 'Gelb' }])
            .forEach(function (c) {
                var s = el('button', 'aiw-swatch');
                s.type = 'button';
                s.title = c.label;
                s.style.background = colorBg(c.code);
                s.style.borderColor = colorEdge(c.code);
                if (c.code === chosenColor) { s.classList.add('is-sel'); }
                s.addEventListener('click', function () {
                    chosenColor = c.code;
                    Array.prototype.forEach.call(
                        sw.querySelectorAll('.aiw-swatch'),
                        function (x) { x.classList.remove('is-sel'); });
                    s.classList.add('is-sel');
                });
                sw.appendChild(s);
            });
        dialog.appendChild(sw);

        // Tags (kommasepariert).
        dialog.appendChild(el('label', 'aiw-modal-label',
            'Schlagworte (durch Komma getrennt)'));
        var tagsInp = el('input', 'aiw-modal-inp');
        tagsInp.type = 'text';
        tagsInp.value = isEdit ? (note.tags || []).join(', ') : '';
        dialog.appendChild(tagsInp);

        // Betroffene:r (Mitarbeiter) — optional.
        dialog.appendChild(el('label', 'aiw-modal-label',
            'Betroffene:r Mitarbeiter (optional)'));
        var subjSel = el('select', 'aiw-modal-inp');
        subjSel.appendChild(optionEl('', '— keiner —'));
        persons.forEach(function (p) {
            subjSel.appendChild(optionEl(String(p.id), p.display_name));
        });
        subjSel.value = (isEdit && note.subject_person_id != null)
            ? String(note.subject_person_id) : '';
        dialog.appendChild(subjSel);

        // Fehlerzeile im Modal (leere Ueberschrift o.ae.).
        var err = el('div', 'aiw-modal-err');
        dialog.appendChild(err);

        // Aktionen.
        var row = el('div', 'aiw-modal-actions');
        var cancel = el('button', 'aiw-btn aiw-btn-ghost', 'Abbrechen');
        cancel.type = 'button';
        cancel.addEventListener('click', function () { close(); });
        var save = el('button', 'aiw-btn aiw-btn-primary',
            isEdit ? 'Speichern' : 'Anlegen');
        save.type = 'button';
        save.addEventListener('click', function () {
            var parsed = parseCommit(ta.value);
            if (!parsed.title) {
                err.textContent = 'Die erste Zeile (Ueberschrift) darf nicht '
                    + 'leer sein.';
                return;
            }
            var tags = tagsInp.value.split(',')
                .map(function (s) { return s.trim(); })
                .filter(function (s) { return s.length > 0; });
            var subj = subjSel.value ? parseInt(subjSel.value, 10) : null;

            var payload = {
                title: parsed.title, body: parsed.body,
                color: chosenColor, tags: tags, subject_person_id: subj
            };
            if (isEdit) { payload.id = note.id; }
            close();
            if (opts.onSubmit) { opts.onSubmit(payload); }
        });
        row.appendChild(cancel);
        row.appendChild(save);
        dialog.appendChild(row);

        overlay.appendChild(dialog);
        // Klick auf den dunklen Rand schliesst (aber nicht Klick im Dialog).
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) { close(); }
        });
        document.body.appendChild(overlay);
        ta.focus();

        function close() {
            if (overlay.parentNode) { overlay.parentNode.removeChild(overlay); }
        }
        return { close: close };
    }

    // =========================================================================
    // 5) UMD-ARTIGER AUSGANG. Browser: window.AIWCockpitNotes; Vitest:
    //    module.exports. Die reinen Funktionen sind fuer Tests exportiert.
    // =========================================================================
    var api = {
        colorBg: colorBg,
        colorEdge: colorEdge,
        parseCommit: parseCommit,
        matchesSearch: matchesSearch,
        matchesFilter: matchesFilter,
        filterNotes: filterNotes,
        allTags: allTags,
        renderNotes: renderNotes,
        openEditor: openEditor,
        // Nur fuer Tests: erlaubt Ruecksetzen des UI-Zustands zwischen Faellen.
        _resetUi: function () { ui = { search: '', color: '', status: '', tag: '', open: {} }; }
    };
    if (typeof window !== 'undefined') { window.AIWCockpitNotes = api; }
    if (typeof module !== 'undefined' && module.exports) { module.exports = api; }
})();
