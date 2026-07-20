// =============================================================================
// management/server/static/cockpit_palette.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Kommandopalette
// =============================================================================
// Zweck (Idee 28 — Kommandopalette / Strg-K):
//   Schnelles Springen zu einer Cockpit-Sicht ueber eine Tastatur-getriebene
//   Palette (Strg-K bzw. Cmd-K). Diese Fassung deckt die FUNKTIONS-/SEITEN-
//   SUCHE ab (Sprung zu einer sichtbaren Sicht). Der Sprung zu Fall/Nutzer/
//   Alias braucht einen eigenen Such-Endpunkt und Fall-Fokus-Mechanik und ist
//   ein Folge-Build.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG).
//   3) Ausfuehrliche Kommentare. 4) REINE Funktion filterViews (kein DOM) ->
//      vitest testet den echten Code. Der Rest kapselt DOM/Tastatur.
//   XSS: Trefferbeschriftung via textContent (Labels sind statisch, aber die
//   Disziplin bleibt).
//
//   Die Palette erhaelt ihre Sichten und die Auswahl-Aktion INJIZIERT (init) —
//   sie kennt VIEW_CATALOG nicht selbst und bleibt so entkoppelt/testbar.
//   Die Sicht-Liste wird bei jedem Oeffnen frisch geholt (getViews), damit sie
//   stets die aktuelle Rechtelage widerspiegelt (default-deny bleibt gewahrt:
//   die Palette zeigt nur, was die Nav auch zeigt).
//
// Version: v0.7.457 · Build: 457 · 2026-07-19
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
        args.unshift('[AIW-Palette]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTION (kein DOM).
    // =========================================================================

    // filterViews: filtert die uebergebene Sicht-Liste nach dem Suchbegriff
    // (Teilstring im Label, case-insensitiv) und ordnet Treffer mit frueherer
    // Fundstelle zuerst (Praefix schlaegt Mitte), dann alphabetisch. Leerer
    // Begriff -> die Liste unveraendert (Kopie). REIN + deterministisch.
    function filterViews(views, query) {
        var list = views || [];
        var q = String(query || '').toLowerCase().trim();
        if (!q) { return list.slice(); }
        var scored = [];
        list.forEach(function (v) {
            var label = String(v.label || '').toLowerCase();
            var idx = label.indexOf(q);
            if (idx >= 0) { scored.push({ v: v, idx: idx }); }
        });
        scored.sort(function (a, b) {
            if (a.idx !== b.idx) { return a.idx - b.idx; }
            return String(a.v.label).localeCompare(String(b.v.label));
        });
        return scored.map(function (s) { return s.v; });
    }

    // =========================================================================
    // 2) CONTROLLER (DOM + Tastatur).
    // =========================================================================

    var _getViews = function () { return []; };
    var _onSelect = function () {};
    // Fall-Suche (Build 459): injizierte, asynchrone Suchfunktion + Auswahl-
    // Aktion. _searchToken verwirft veraltete (out-of-order) Antworten.
    var _searchCases = null;
    var _onSelectCase = function () {};
    var _searchToken = 0;
    var _bound = false;

    var dom = { overlay: null, input: null, list: null };
    var view = { items: [], sel: 0, open: false };

    function ensureDom() {
        if (dom.overlay) { return; }
        var overlay = document.createElement('div');
        overlay.id = 'aiw-palette-overlay';
        overlay.className = 'aiw-palette-overlay';
        overlay.setAttribute('hidden', 'hidden');

        var box = document.createElement('div');
        box.className = 'aiw-palette-box';

        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'aiw-palette-input';
        input.setAttribute('placeholder', 'Sicht suchen … (Strg-K)');
        input.setAttribute('autocomplete', 'off');

        var list = document.createElement('ul');
        list.className = 'aiw-palette-list';

        box.appendChild(input);
        box.appendChild(list);
        overlay.appendChild(box);
        document.body.appendChild(overlay);

        // Klick auf den dunklen Rand schliesst; Klick in die Box nicht.
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) { close(); }
        });
        input.addEventListener('input', function () { render(input.value); });
        input.addEventListener('keydown', onInputKeydown);

        dom.overlay = overlay;
        dom.input = input;
        dom.list = list;
    }

    // Item-Fabriken: vereinheitlichen Sichten UND Fall-Treffer zu EINEM
    // Listenmodell (view.items), damit Tastatur-Navigation beide umfasst.
    function _mkViewItem(v) {
        return { type: 'view', id: v.id, label: v.label || v.id,
                 group: v.group || '' };
    }
    function _mkCaseItem(c) {
        return { type: 'case', userId: c.user_id,
                 label: 'Fall ' + c.user_id + ' · ' + (c.username || '?'),
                 group: 'Fall', status: c.status };
    }

    // _draw: zeichnet view.items (typ-bewusst). Sicht-Items tragen
    // data-view-id, Fall-Items data-case-id. Alles via textContent (XSS-sicher).
    function _draw() {
        dom.list.textContent = '';
        if (view.items.length === 0) {
            var empty = document.createElement('li');
            empty.className = 'aiw-palette-empty';
            empty.textContent = 'Kein Treffer.';
            dom.list.appendChild(empty);
            return;
        }
        view.items.forEach(function (item, i) {
            var li = document.createElement('li');
            li.className = 'aiw-palette-item'
                + (i === view.sel ? ' aiw-palette-active' : '');
            if (item.type === 'case') {
                li.setAttribute('data-case-id', String(item.userId));
            } else {
                li.setAttribute('data-view-id', item.id);
            }
            var grp = document.createElement('span');
            grp.className = 'aiw-palette-grp';
            grp.textContent = item.group || '';
            var lbl = document.createElement('span');
            lbl.className = 'aiw-palette-lbl';
            lbl.textContent = item.label || '';
            li.appendChild(grp);
            li.appendChild(lbl);
            li.addEventListener('click', function () { choose(i); });
            dom.list.appendChild(li);
        });
    }

    // render: Sichten SOFORT (synchron, rechte-gefiltert). Ist eine Fall-Suche
    // injiziert und der Begriff nicht leer, wird zusaetzlich asynchron gesucht
    // und die Fall-Treffer angehaengt (nur, wenn die Antwort noch aktuell ist).
    function render(query) {
        ensureDom();
        var token = ++_searchToken;
        var viewItems = filterViews(_getViews(), query).map(_mkViewItem);
        view.items = viewItems;
        view.sel = 0;
        _draw();

        var q = String(query || '').trim();
        if (_searchCases && q) {
            _searchCases(q).then(function (cases) {
                if (token !== _searchToken) { return; }   // veraltet -> verwerfen
                var caseItems = (cases || []).map(_mkCaseItem);
                view.items = viewItems.concat(caseItems);
                _draw();
            }).catch(function (e) { log('searchCases', e); });
        }
    }

    function highlight() {
        var lis = dom.list.querySelectorAll('.aiw-palette-item');
        for (var i = 0; i < lis.length; i++) {
            if (i === view.sel) { lis[i].classList.add('aiw-palette-active'); }
            else { lis[i].classList.remove('aiw-palette-active'); }
        }
    }

    function move(delta) {
        if (view.items.length === 0) { return; }
        view.sel = (view.sel + delta + view.items.length) % view.items.length;
        highlight();
    }

    function choose(i) {
        if (typeof i === 'number') { view.sel = i; }
        var item = view.items[view.sel];
        if (!item) { return; }
        close();
        if (item.type === 'case') {
            _onSelectCase(item.userId);
            log('Fall gewaehlt:', item.userId);
        } else {
            _onSelect(item.id);
            log('gewaehlt:', item.id);
        }
    }

    function open() {
        ensureDom();
        view.open = true;
        dom.input.value = '';
        render('');
        dom.overlay.removeAttribute('hidden');
        // Fokus nach dem Sichtbarwerden.
        try { dom.input.focus(); } catch (e) { /* JSDOM: egal */ }
        log('geoeffnet');
    }

    function close() {
        if (!dom.overlay) { return; }
        view.open = false;
        dom.overlay.setAttribute('hidden', 'hidden');
    }

    function toggle() { if (view.open) { close(); } else { open(); } }

    function onInputKeydown(e) {
        if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
        else if (e.key === 'Enter') { e.preventDefault(); choose(); }
        else if (e.key === 'Escape') { e.preventDefault(); close(); }
    }

    function onGlobalKeydown(e) {
        // Strg-K / Cmd-K oeffnet/schliesst; Escape schliesst (falls offen).
        var isK = (e.key === 'k' || e.key === 'K');
        if ((e.ctrlKey || e.metaKey) && isK) {
            e.preventDefault();
            toggle();
        } else if (e.key === 'Escape' && view.open) {
            close();
        }
    }

    // init: Getter fuer die (rechte-gefilterten) Sichten + Auswahl-Aktion
    // injizieren und den globalen Tasten-Listener EINMAL binden.
    function init(opts) {
        opts = opts || {};
        if (typeof opts.getViews === 'function') { _getViews = opts.getViews; }
        if (typeof opts.onSelect === 'function') { _onSelect = opts.onSelect; }
        if (typeof opts.searchCases === 'function') {
            _searchCases = opts.searchCases;
        }
        if (typeof opts.onSelectCase === 'function') {
            _onSelectCase = opts.onSelectCase;
        }
        if (!_bound && typeof document !== 'undefined') {
            document.addEventListener('keydown', onGlobalKeydown);
            _bound = true;
        }
        log('init');
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        filterViews: filterViews,
        init: init,
        open: open,
        close: close,
        toggle: toggle,
        _debugState: function () { return view; }   // nur fuer Tests
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitPalette = API; }
})();
