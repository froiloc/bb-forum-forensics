// =============================================================================
// management/server/static/cockpit_personnel.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Personalverwaltung
// =============================================================================
// Zweck (Build 503, Bauplan Build503 §4):
//   Die "Seite zum Verwalten der Anwender" (mc 2026-07-24): Personenliste mit
//   Aktiv-Status, Rollen-Flags und Rollenzuweisungen — plus der EINGEBUNDENE
//   AD-Abgleich (Wiederverwendung der Komponente AIWCockpitAdSync aus Build
//   502, KEINE Kopie).
//
//   Bedienelemente (nur bei can_edit):
//     - Flags (Ermittler/Supervisor/Support) als Checkboxen -> onFlags.
//     - Rollen-Chips mit Widerrufs-x -> onRevoke (Soft-Revoke, auditiert).
//     - Zuweisen-Dropdown (Rollenkatalog) + Knopf -> onAssign.
//   SELBSTSCHUTZ: die eigene Zeile (actor_person_id) zeigt KEINE
//   Bedienelemente — der Server weist eigene Aenderungen ohnehin mit 400 ab
//   (Lockout-Schutz, Bauplan §3); die Oberflaeche bietet sie gar nicht an.
//
//   AD-Abgleich-Abschnitt (nur bei can_sync): LAZY — der Knopf "AD-Vorschau
//   laden" holt /api/adsync erst auf Klick (kein LDAP-Zugriff beim blossen
//   Oeffnen der Seite; der Abruf kann je nach DC dauern) und rendert die
//   bestehende AdSync-Komponente in einen Unter-Container.
//
// Datenform GET /api/personnel (ManagementApp._personnel):
//   { persons: [{id, system_username, display_name, is_investigator,
//                is_supervisor, is_support, created_at, is_active,
//                deactivated_at, deactivated_reason,
//                roles: [{person_role_id, role_code, label, assigned_at}]}],
//     roles_catalog: [{code, label}],
//     actor_person_id, can_edit, can_sync }
//
// SCHREIBEN (opts -> cockpit.js -> postJson mit X-AIW-Token):
//   onFlags({person_id, <flag>: bool})       — genau EIN Flag je Klick.
//   onAssign({person_id, role_code})         — Rolle zuweisen.
//   onRevoke({person_role_id})               — Zuweisung widerrufen.
//   onAdsyncLoad(containerEl, setResult)     — AD-Vorschau in den Container
//                                              laden (cockpit.js haelt die
//                                              fetch/post-Logik).
//   KEIN optimistisches UI: nach jedem Schreiben laedt cockpit.js die Sicht neu.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS: (1) IIFE + 'use strict'. (2) DEV-Logging
//   (AIW_COCKPIT_DEBUG). (3) ausfuehrliche Kommentare. (4) reine Funktionen
//   fassen NIE das DOM an -> vitest; opts.doc injizierbar (JSDOM).
// SICHERHEIT (XSS): alle variablen Texte via textContent.
//
// Version: v0.8.503 · Build: 503 · 2026-07-24
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
        args.unshift('[AIW-Personnel]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';

    //: Reihenfolge + Beschriftung der Flag-Spalten (person-Schema, Build 310).
    var FLAGS = [
        { key: 'is_investigator', label: 'Ermittler:in' },
        { key: 'is_supervisor', label: 'Supervisor' },
        { key: 'is_support', label: 'Support' }
    ];

    // ------------------------------------------------------------------ Helfer
    // (REINE Funktionen — kein DOM, kein Netz; vitest-geprueft.)

    // statusText: Anzeige des Aktiv-Status. Inaktive tragen Zeitpunkt+Grund
    // (forensische Nachvollziehbarkeit direkt in der Liste).
    function statusText(p) {
        if (p && p.is_active === false) {
            var since = p.deactivated_at
                ? new Date(p.deactivated_at * 1000).toISOString().slice(0, 10)
                : '?';
            var reason = p.deactivated_reason || '';
            return 'inaktiv seit ' + since + (reason ? ' (' + reason + ')' : '');
        }
        return 'aktiv';
    }

    // assignableRoles: Katalogrollen, die die Person noch NICHT aktiv hat
    // (kein No-op-Angebot im Dropdown; der Server prueft verbindlich).
    function assignableRoles(person, catalog) {
        var have = {};
        ((person && person.roles) || []).forEach(function (r) {
            have[r.role_code] = true;
        });
        return (catalog || []).filter(function (r) { return !have[r.code]; });
    }

    // isSelf: die eigene Zeile (Selbstschutz — keine Bedienelemente).
    function isSelf(person, data) {
        return !!(person && data
            && person.id === data.actor_person_id);
    }

    // canEditRow: Bedienelemente nur mit Recht UND nicht auf der eigenen Zeile.
    function canEditRow(person, data) {
        return !!(data && data.can_edit) && !isSelf(person, data);
    }

    // ---------------------------------------------------------------- Render
    function renderPersonnel(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc || !data) { return { setResult: function () {} }; }

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Personalverwaltung';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Anwender der Anlage: Aktiv-Status, Rollen-Flags und '
            + 'Rollenzuweisungen. Jede Aenderung wird auditiert; die eigene '
            + 'Person ist hier unantastbar (Lockout-Schutz), die Grants der '
            + 'Rollen-Matrix pflegt weiterhin die CLI (policy_admin).';
        mainEl.appendChild(sub);

        // --- Ergebniszeile ---------------------------------------------------
        var result = doc.createElement('div');
        result.className = 'aiw-pers-result';
        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }
        mainEl.appendChild(result);

        // --- Personenliste ---------------------------------------------------
        mainEl.appendChild(_table(doc, data, opts));

        // --- AD-Abgleich (lazy, nur mit personnel.sync) ----------------------
        if (data.can_sync) {
            var h3 = doc.createElement('h3');
            h3.className = 'aiw-pers-sect';
            h3.textContent = 'AD-Abgleich';
            mainEl.appendChild(h3);

            var hint = doc.createElement('p');
            hint.className = 'aiw-pers-hint';
            hint.textContent = 'Die Vorschau fragt das Live-AD ab und wird '
                + 'deshalb erst auf Anforderung geladen.';
            mainEl.appendChild(hint);

            var box = doc.createElement('div');
            box.className = 'aiw-pers-adsync';
            var loadBtn = doc.createElement('button');
            loadBtn.type = 'button';
            loadBtn.className = 'aiw-adsync-btn aiw-pers-adsync-load';
            loadBtn.textContent = 'AD-Vorschau laden';
            loadBtn.addEventListener('click', function () {
                loadBtn.disabled = true;  // Doppelklick-Schutz
                if (typeof opts.onAdsyncLoad === 'function') {
                    opts.onAdsyncLoad(box, setResult);
                }
            });
            mainEl.appendChild(loadBtn);
            mainEl.appendChild(box);
            // Nach einer AD-Aktion laedt cockpit.js die Sicht mit offenem
            // Abschnitt neu (opts.adsyncOpen) — dann sofort laden, ohne Klick.
            if (opts.adsyncOpen === true
                    && typeof opts.onAdsyncLoad === 'function') {
                loadBtn.disabled = true;
                opts.onAdsyncLoad(box, setResult);
            }
        }

        log('gerendert:', (data.persons || []).length, 'Personen');
        return { setResult: setResult };
    }

    // _table: die Personenliste als DOM-Tabelle (kein Tabulator: die Zeilen
    // tragen interaktive Elemente, die wir exakt kontrollieren wollen).
    function _table(doc, data, opts) {
        var table = doc.createElement('table');
        table.className = 'aiw-pers-table';

        var thead = doc.createElement('thead');
        var trh = doc.createElement('tr');
        ['Kennung', 'Anzeigename', 'Status'].concat(
            FLAGS.map(function (f) { return f.label; }),
            ['Rollen']
        ).forEach(function (t) {
            var th = doc.createElement('th');
            th.textContent = t;
            trh.appendChild(th);
        });
        thead.appendChild(trh);
        table.appendChild(thead);

        var tbody = doc.createElement('tbody');
        (data.persons || []).forEach(function (p) {
            tbody.appendChild(_row(doc, p, data, opts));
        });
        table.appendChild(tbody);
        return table;
    }

    function _row(doc, p, data, opts) {
        var tr = doc.createElement('tr');
        tr.className = 'aiw-pers-row'
            + (p.is_active === false ? ' inactive' : '')
            + (isSelf(p, data) ? ' self' : '');

        var tdU = doc.createElement('td');
        tdU.textContent = p.system_username
            + (isSelf(p, data) ? ' (ich)' : '');
        tr.appendChild(tdU);

        var tdN = doc.createElement('td');
        tdN.textContent = p.display_name;
        tr.appendChild(tdN);

        var tdS = doc.createElement('td');
        tdS.textContent = statusText(p);
        tr.appendChild(tdS);

        var editable = canEditRow(p, data);

        // Flags: Checkbox (editierbar) oder reiner Text.
        FLAGS.forEach(function (f) {
            var td = doc.createElement('td');
            td.className = 'aiw-pers-flag';
            if (editable) {
                var cb = doc.createElement('input');
                cb.type = 'checkbox';
                cb.checked = p[f.key] === true;
                cb.addEventListener('change', function () {
                    var body = { person_id: p.id };
                    body[f.key] = cb.checked;
                    if (typeof opts.onFlags === 'function') {
                        opts.onFlags(body);
                    }
                });
                td.appendChild(cb);
            } else {
                td.textContent = p[f.key] === true ? '✓' : EM_DASH;
            }
            tr.appendChild(td);
        });

        // Rollen: Chips (+ Widerruf) + Zuweisen-Dropdown.
        var tdR = doc.createElement('td');
        tdR.className = 'aiw-pers-roles';
        (p.roles || []).forEach(function (r) {
            var chip = doc.createElement('span');
            chip.className = 'aiw-pers-chip';
            var lbl = doc.createElement('span');
            lbl.textContent = r.role_code;
            lbl.title = r.label || r.role_code;
            chip.appendChild(lbl);
            if (editable) {
                var x = doc.createElement('button');
                x.type = 'button';
                x.className = 'aiw-pers-chip-x';
                x.textContent = '×';
                x.title = 'Zuweisung widerrufen (auditiert, Soft-Revoke)';
                x.addEventListener('click', function () {
                    if (typeof opts.onRevoke === 'function') {
                        opts.onRevoke({ person_role_id: r.person_role_id });
                    }
                });
                chip.appendChild(x);
            }
            tdR.appendChild(chip);
        });
        if (editable) {
            var candidates = assignableRoles(p, data.roles_catalog);
            if (candidates.length) {
                var sel = doc.createElement('select');
                sel.className = 'aiw-pers-assign-sel';
                var ph = doc.createElement('option');
                ph.value = '';
                ph.textContent = 'Rolle zuweisen …';
                sel.appendChild(ph);
                candidates.forEach(function (r) {
                    var o = doc.createElement('option');
                    o.value = r.code;
                    o.textContent = r.code + ' (' + r.label + ')';
                    sel.appendChild(o);
                });
                sel.addEventListener('change', function () {
                    if (!sel.value) { return; }
                    if (typeof opts.onAssign === 'function') {
                        opts.onAssign({ person_id: p.id,
                                        role_code: sel.value });
                    }
                });
                tdR.appendChild(sel);
            }
        }
        tr.appendChild(tdR);
        return tr;
    }

    // ------------------------------------------------------------------ Export
    var api = {
        renderPersonnel: renderPersonnel,
        // reine Funktionen fuer vitest:
        statusText: statusText,
        assignableRoles: assignableRoles,
        isSelf: isSelf,
        canEditRow: canEditRow,
        FLAGS: FLAGS
    };
    if (typeof window !== 'undefined') {
        window.AIWCockpitPersonnel = api;
    }
})();
