// =============================================================================
// management/server/static/cockpit_policy.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Rechte / Policy
// =============================================================================
// Zweck:
//   Rendert die RBAC-Policy-Sicht (/api/policy) im Cockpit: zwei Tabulator-
//   Tabellen — GRANTS (Rolle -> Faehigkeit, mit Scope/Beleg) und ROLLEN-
//   ZUWEISUNGEN (Person -> Rolle) — plus den Rollen-/Faehigkeiten-Katalog als
//   kompakte Referenz. Genau die Matrix, die zuvor per SQL aus coordinator.db
//   gelesen wurde. Beleg: Bauplan B7 v1.1 §11.3; Build 361 (/api/policy).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen ohne DOM; UMD-Ausgang ->
//   vitest testet den ECHTEN Code (grantRows/assignmentRows/capLabelIndex sind
//   rein; nur renderPolicy beruehrt document/Tabulator).
//
// XSS: Nur textContent fuer variablen Text. Die Tabulator-Standard-Formatter
//   ('plaintext') setzen Werte per textContent — kein innerHTML.
//
// Version: v0.7.362 · Build: 362 · 2026-07-10
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
        args.unshift('[AIW-Policy]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) REINE FUNKTIONEN.
    // =========================================================================

    // capLabelIndex: Faehigkeits-Code -> Label (fuer die Anreicherung der
    // Grant-Zeilen).
    function capLabelIndex(data) {
        var idx = {};
        ((data && data.capabilities) || []).forEach(function (c) {
            idx[c.code] = c.label || c.code;
        });
        return idx;
    }

    // grantRows: /api/policy.grants -> Tabellenzeilen, angereichert um das
    // Faehigkeits-Label.
    function grantRows(data) {
        var idx = capLabelIndex(data);
        return ((data && data.grants) || []).map(function (g) {
            return {
                role_code: g.role_code,
                capability_code: g.capability_code,
                capability_label: idx[g.capability_code] || g.capability_code,
                scope: g.scope,
                audit_seq: g.audit_seq,
                note: g.note || ''
            };
        });
    }

    // assignmentRows: /api/policy.assignments -> Tabellenzeilen.
    function assignmentRows(data) {
        return ((data && data.assignments) || []).map(function (a) {
            return {
                person_id: a.person_id,
                display_name: a.display_name || '',
                system_username: a.system_username || '',
                role_code: a.role_code,
                audit_seq: a.audit_seq
            };
        });
    }

    function scopeText(scope) {
        if (scope === 'eigene') {
            return 'Umfang: nur eigene Rechte (meine Rollen/Grants).';
        }
        if (scope === 'alle') {
            return 'Umfang: vollstaendige Policy-Matrix.';
        }
        return 'Umfang: eingeschraenkt.';
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    var _GRANT_COLUMNS = [
        { title: 'Rolle', field: 'role_code', headerFilter: 'input' },
        { title: 'Faehigkeit', field: 'capability_code', headerFilter: 'input' },
        { title: 'Bezeichnung', field: 'capability_label' },
        { title: 'Scope', field: 'scope' },
        { title: 'Beleg', field: 'audit_seq' },
        { title: 'Notiz', field: 'note' }
    ];

    var _ASSIGN_COLUMNS = [
        { title: 'Person', field: 'display_name', headerFilter: 'input' },
        { title: 'Kennung', field: 'system_username' },
        { title: 'Rolle', field: 'role_code', headerFilter: 'input' },
        { title: 'Beleg', field: 'audit_seq' }
    ];

    // _section: Abschnittsueberschrift + Behaelter.
    //
    // BUILD 604: gibt jetzt die UEBERSCHRIFT zurueck (der Behaelter wurde von
    // keinem Aufrufer benutzt). Grund: die Hilfe-Kennung wird an der
    // AUFRUFSTELLE gesetzt und nicht als Argument hereingereicht. Nur so steht
    // sie woertlich neben dem Attributnamen, und nur so findet die
    // Paritaetspruefung sie mit einer Textsuche (Konzept §4.2a).
    function _section(mainEl, titleText) {
        var h = document.createElement('h3');
        h.className = 'aiw-subhead';
        h.textContent = titleText;
        mainEl.appendChild(h);
        var container = document.createElement('div');
        mainEl.appendChild(container);
        return h;
    }

    // _catalog: Rollen-/Faehigkeiten-Katalog als kompakte Referenzliste
    // (klein; keine Tabelle noetig). Nur textContent.
    function _catalog(mainEl, data) {
        var h = document.createElement('h3');
        h.className = 'aiw-subhead';
        h.textContent = 'Katalog (Rollen / Faehigkeiten)';
        h.setAttribute('data-hilfe-id', 'policy.abschnitt.katalog');
        mainEl.appendChild(h);
        var wrap = document.createElement('div');
        wrap.className = 'aiw-policy-catalog';

        function list(title, items, fmt) {
            var box = document.createElement('div');
            var t = document.createElement('div');
            t.className = 'aiw-catalog-title';
            t.textContent = title;
            box.appendChild(t);
            var ul = document.createElement('ul');
            (items || []).forEach(function (it) {
                var li = document.createElement('li');
                li.textContent = fmt(it);
                ul.appendChild(li);
            });
            box.appendChild(ul);
            return box;
        }
        wrap.appendChild(list('Rollen', data && data.roles, function (r) {
            return r.code + ' — ' + (r.label || '');
        }));
        wrap.appendChild(list('Faehigkeiten', data && data.capabilities,
            function (c) { return c.code + ' — ' + (c.label || ''); }));
        mainEl.appendChild(wrap);
    }

    // _tk / _mitHilfe (Build 550): gemeinsames Tabellen-Werkzeug + Hilfe-Anker
    // der Spaltenkoepfe. LAZY; die Spalten werden KOPIERT.
    function _tk() {
        return (typeof window !== 'undefined' && window.AIWTableKit)
            ? window.AIWTableKit : null;
    }
    function _mitHilfe(cols, sicht, doc) {
        var TK = _tk();
        if (!TK || !doc || !TK.titelMitHilfe) { return cols; }
        return cols.map(function (c) {
            var neu = {};
            Object.keys(c).forEach(function (k) { neu[k] = c[k]; });
            if (c.field && !c.titleFormatter) {
                neu.titleFormatter = TK.titelMitHilfe(
                    doc, c.title || c.field,
                    sicht + '.spalte.' + String(c.field).toLowerCase());
            }
            return neu;
        });
    }

    // renderPolicy: Kopf + Grants-Tabelle + Zuweisungs-Tabelle + Katalog.
    // opts.Tabulator injizierbar (Default window.Tabulator). Rueckgabe: Array
    // der Tabulator-Instanzen (fuer den sauberen Abbau beim Sichtwechsel).
    function renderPolicy(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return []; }
        mainEl.textContent = '';

        var scope = data ? data.scope : null;
        var counts = (data && data.counts) || {};

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Rechte / Policy';
        // Build 604 (Baustelle H / H13): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'policy.titel');
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = scopeText(scope) + ' ('
            + (counts.grants || 0) + ' Grants, '
            + (counts.assignments || 0) + ' Zuweisungen)';
        sub.setAttribute('data-hilfe-id', 'policy.kennzeile');
        mainEl.appendChild(sub);

        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        if (typeof Ctor !== 'function') {
            var note = document.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Tabellenbibliothek nicht verfügbar — es '
                + 'liegen ' + grantRows(data).length + ' Grants und '
                + assignmentRows(data).length + ' Zuweisungen vor.';
            mainEl.appendChild(note);
            _catalog(mainEl, data);
            log('renderPolicy: kein Tabulator-Ctor');
            return [];
        }

        // Build 550: beide Tabellen ueber das gemeinsame Werkzeug, mit je
        // EIGENER Kennung. Zwei Tabellen unter einer Kennung teilten sich
        // Hilfe-Anker UND gesicherten Bedienzustand und ueberschrieben sich
        // gegenseitig.
        var doc0 = mainEl.ownerDocument || document;
        _section(mainEl, 'Grants (Rolle \u2192 Faehigkeit)')
            .setAttribute('data-hilfe-id', 'policy.abschnitt.grants');
        var grantsTable = _tk().tabelleAufbauen(doc0, mainEl, {
            sicht: 'policy_grants',
            rows: grantRows(data),
            columns: _mitHilfe(_GRANT_COLUMNS, 'policy_grants', doc0),
            Ctor: Ctor, einheit: 'Grants',
            tabulator: { height: '320px' }
        }).table;

        _section(mainEl, 'Rollen-Zuweisungen (Person \u2192 Rolle)')
            .setAttribute('data-hilfe-id', 'policy.abschnitt.zuweisungen');
        var assignTable = _tk().tabelleAufbauen(doc0, mainEl, {
            sicht: 'policy_assign',
            rows: assignmentRows(data),
            columns: _mitHilfe(_ASSIGN_COLUMNS, 'policy_assign', doc0),
            Ctor: Ctor, einheit: 'Zuweisungen',
            tabulator: { height: '260px' }
        }).table;

        _catalog(mainEl, data);

        log('renderPolicy:', (counts.grants || 0), 'Grants,',
            (counts.assignments || 0), 'Zuweisungen, scope', scope);
        return [grantsTable, assignTable];
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        capLabelIndex: capLabelIndex,
        grantRows: grantRows,
        assignmentRows: assignmentRows,
        scopeText: scopeText,
        renderPolicy: renderPolicy
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitPolicy = API; }
})();
