// =============================================================================
// management/server/static/cockpit_adsync.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit AD-Abgleich
// =============================================================================
// Zweck (Build 502, Bauplan Build501_502 §7 — Frontend zum Sync-Kern 501):
//   Rendert die Vorschau des AD-Abgleichs (/api/adsync) und die Bedienflaechen
//   fuer den Vollzug:
//     - "Automatische Schritte vollziehen": Neuaufnahmen (als investigator)
//       und Namensaenderungen (POST /api/adsync/apply — der Server bildet den
//       Plan FRISCH; die Oberflaeche liefert nur den Anstoss, keine Daten).
//     - Je Entfernungs-Kandidat: Texteingabe des Bestaetigungsworts
//       ("Entfernen") + Knopf "Deaktivieren" ODER Knopf "Abbruch
//       protokollieren" (mit Notiz). Entfernte werden NIE geloescht — nur
//       inaktiv geschaltet (mc 2026-07-24).
//     - Je Reaktivierungs-Kandidat: Texteingabe ("Reaktivieren") + Knopf.
//
//   Die Bestaetigungsworte kommen im Datenpaket VOM SERVER (data.confirm) —
//   eine Wahrheitsquelle; geprueft wird ausschliesslich serverseitig
//   (/api/adsync/decide). Die Oberflaeche prueft NUR als Komfort vor dem
//   Absenden (validateWord), damit ein Tippfehler nicht erst den Server
//   fragen muss — die Server-Pruefung bleibt verbindlich.
//
// Datenform GET /api/adsync (ManagementApp._adsync):
//   {
//     group, confirm: {deactivate, reactivate},
//     create: [{sam, display_name}],
//     rename: [{person_id, system_username, display_name_alt,
//               display_name_neu}],
//     deactivate_candidates: [{person_id, system_username, display_name}],
//     reactivate_candidates: [{person_id, system_username, display_name,
//                              display_name_ad}],
//     counts: {create, rename, deactivate_candidates, reactivate_candidates,
//              unchanged, unchanged_inactive}
//   }
//
// SCHREIBEN (opts -> cockpit.js -> postJson mit X-AIW-Token):
//   onApply()          — automatische Schritte anstossen; danach laedt
//                        cockpit.js die Sicht NEU (KEIN optimistisches UI).
//   onDecide(body)     — Einzel-Entscheidung {system_username, action,
//                        confirmation?, note?, display_name_ad?}.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS: (1) IIFE + 'use strict'. (2) DEV-Logging
//   (AIW_COCKPIT_DEBUG). (3) ausfuehrliche Kommentare. (4) reine Funktionen
//   fassen NIE das DOM an -> vitest; opts.doc injizierbar (JSDOM).
// SICHERHEIT (XSS): alle variablen Texte via textContent.
//
// Version: v0.8.502 · Build: 502 · 2026-07-24
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
        args.unshift('[AIW-AdSync]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';

    // ------------------------------------------------------------------ Helfer
    // (REINE Funktionen — kein DOM, kein Netz; vitest-gepueft.)

    // counts: fehlende Zaehler defensiv als 0 (der Server liefert immer alle;
    // die Sicht darf an einem Teilpaket trotzdem nicht scheitern).
    function counts(data) {
        var c = (data && data.counts) || {};
        return {
            create: c.create || 0,
            rename: c.rename || 0,
            deactivate_candidates: c.deactivate_candidates || 0,
            reactivate_candidates: c.reactivate_candidates || 0,
            unchanged: c.unchanged || 0,
            unchanged_inactive: c.unchanged_inactive || 0
        };
    }

    // hasAutomatic: gibt es Schritte, die /api/adsync/apply vollziehen wuerde?
    function hasAutomatic(data) {
        var c = counts(data);
        return (c.create + c.rename) > 0;
    }

    // summaryText: eine Zeile Lagebild fuer den Kopf der Sicht.
    function summaryText(data) {
        var c = counts(data);
        return 'Neu: ' + c.create
            + ' · Namensaenderungen: ' + c.rename
            + ' · Entfernungs-Kandidaten: ' + c.deactivate_candidates
            + ' · Reaktivierungs-Kandidaten: ' + c.reactivate_candidates
            + ' · unveraendert aktiv: ' + c.unchanged
            + ' · unveraendert inaktiv: ' + c.unchanged_inactive;
    }

    // confirmWords: die vom SERVER vorgegebenen Worte (eine Wahrheitsquelle);
    // Fallback nur, falls ein Altserver das Feld nicht liefert.
    function confirmWords(data) {
        var c = (data && data.confirm) || {};
        return {
            deactivate: c.deactivate || 'Entfernen',
            reactivate: c.reactivate || 'Reaktivieren'
        };
    }

    // validateWord: Komfort-Vorpruefung im Browser (EXAKTER Vergleich wie am
    // Server: keine Normalisierung, kein trim — 'entfernen' zaehlt nicht).
    function validateWord(expected, typed) {
        return typeof typed === 'string' && typed === expected;
    }

    // decideBody: Request-Koerper fuer POST /api/adsync/decide.
    function decideBody(sam, action, confirmation, note, displayNameAd) {
        var body = { system_username: sam, action: action };
        if (confirmation != null) { body.confirmation = confirmation; }
        if (note) { body.note = note; }
        if (displayNameAd) { body.display_name_ad = displayNameAd; }
        return body;
    }

    // =========================================================================
    // 1) DOM: Sicht rendern.
    // =========================================================================
    function renderAdSync(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc || !data) { return { setResult: function () {} }; }
        var words = confirmWords(data);

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'AD-Abgleich';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Abgleich der Ermittlerstammdaten mit der '
            + 'AD-Gruppe „' + (data.group || '?') + '“. Jede '
            + 'Aenderung wird auditiert; Entfernungen werden NIE geloescht, '
            + 'sondern nur inaktiv geschaltet — und nur nach Eingabe '
            + 'des Wortes „' + words.deactivate + '“.';
        mainEl.appendChild(sub);

        // --- Ergebniszeile ---------------------------------------------------
        var result = doc.createElement('div');
        result.className = 'aiw-adsync-result';
        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }
        mainEl.appendChild(result);

        // --- Lagebild + automatischer Vollzug -------------------------------
        var summary = doc.createElement('p');
        summary.className = 'aiw-adsync-summary';
        summary.textContent = summaryText(data);
        mainEl.appendChild(summary);

        if (hasAutomatic(data)) {
            var applyBtn = doc.createElement('button');
            applyBtn.type = 'button';
            applyBtn.className = 'aiw-adsync-btn aiw-adsync-apply';
            applyBtn.textContent = 'Automatische Schritte vollziehen ('
                + counts(data).create + ' Neuaufnahmen als investigator, '
                + counts(data).rename + ' Namensaenderungen)';
            applyBtn.addEventListener('click', function () {
                applyBtn.disabled = true;  // Doppelklick-Schutz
                if (typeof opts.onApply === 'function') { opts.onApply(); }
            });
            mainEl.appendChild(applyBtn);
        }

        // --- Abschnitte ------------------------------------------------------
        _listSection(doc, mainEl, '[Neu] ' + EM_DASH
            + ' werden als investigator aufgenommen',
            data.create || [], function (m) {
                return m.sam + ' · ' + m.display_name;
            });
        _listSection(doc, mainEl, '[Namensaenderung]',
            data.rename || [], function (r) {
                return r.system_username + ': „' + r.display_name_alt
                    + '“ → „' + r.display_name_neu + '“';
            });
        _deactivateSection(doc, mainEl, data, words, opts, setResult);
        _reactivateSection(doc, mainEl, data, words, opts, setResult);

        log('gerendert:', summaryText(data));
        return { setResult: setResult };
    }

    // _listSection: rein anzeigende Liste (Neu / Namensaenderung).
    function _listSection(doc, mainEl, title, items, toText) {
        if (!items.length) { return; }
        var h = doc.createElement('h3');
        h.className = 'aiw-adsync-sect';
        h.textContent = title;
        mainEl.appendChild(h);
        var ul = doc.createElement('ul');
        ul.className = 'aiw-adsync-list';
        items.forEach(function (it) {
            var li = doc.createElement('li');
            li.textContent = toText(it);
            ul.appendChild(li);
        });
        mainEl.appendChild(ul);
    }

    // _candidateRow: eine Kandidaten-Zeile (Label + Wort-Eingabe + Aktionen).
    // buttons: [{label, cls, needsWord, onClick(typedWord, note)}]
    function _candidateRow(doc, labelText, placeholder, withNote, buttons) {
        var row = doc.createElement('div');
        row.className = 'aiw-adsync-cand';

        var label = doc.createElement('span');
        label.className = 'aiw-adsync-cand-label';
        label.textContent = labelText;
        row.appendChild(label);

        var input = doc.createElement('input');
        input.type = 'text';
        input.className = 'aiw-adsync-word';
        input.placeholder = placeholder;
        input.setAttribute('autocomplete', 'off');
        row.appendChild(input);

        var note = null;
        if (withNote) {
            note = doc.createElement('input');
            note.type = 'text';
            note.className = 'aiw-adsync-note';
            note.placeholder = 'Notiz / Grund (fuer den Abbruch-Beleg)';
            row.appendChild(note);
        }

        buttons.forEach(function (b) {
            var btn = doc.createElement('button');
            btn.type = 'button';
            btn.className = 'aiw-adsync-btn ' + b.cls;
            btn.textContent = b.label;
            btn.addEventListener('click', function () {
                b.onClick(input.value, note ? note.value : '');
            });
            row.appendChild(btn);
        });
        return row;
    }

    // _deactivateSection: Entfernungs-Kandidaten. Vollzug NUR mit exakt
    // getipptem Wort; der protokollierte Abbruch ist ein EIGENER Knopf
    // (bewusste Handlung, eigener Beleg — mc 2026-07-24).
    function _deactivateSection(doc, mainEl, data, words, opts, setResult) {
        var cands = data.deactivate_candidates || [];
        if (!cands.length) { return; }
        var h = doc.createElement('h3');
        h.className = 'aiw-adsync-sect warn';
        h.textContent = '[Entfernungs-Kandidaten] ' + EM_DASH
            + ' nicht mehr im AD; Deaktivierung nur nach Eingabe von „'
            + words.deactivate + '“';
        mainEl.appendChild(h);

        cands.forEach(function (c) {
            var row = _candidateRow(
                doc,
                c.system_username + ' · ' + c.display_name,
                words.deactivate, true,
                [{
                    label: 'Deaktivieren', cls: 'aiw-adsync-deact',
                    onClick: function (typed) {
                        // Komfort-Vorpruefung; verbindlich prueft der Server.
                        if (!validateWord(words.deactivate, typed)) {
                            setResult('Nicht vollzogen: Bestaetigungswort '
                                + 'entspricht nicht exakt „'
                                + words.deactivate + '“.', true);
                            return;
                        }
                        if (typeof opts.onDecide === 'function') {
                            opts.onDecide(decideBody(
                                c.system_username, 'deactivate', typed));
                        }
                    }
                }, {
                    label: 'Abbruch protokollieren', cls: 'aiw-adsync-abort',
                    onClick: function (_typed, noteVal) {
                        if (typeof opts.onDecide === 'function') {
                            opts.onDecide(decideBody(
                                c.system_username, 'abort', null, noteVal));
                        }
                    }
                }]);
            mainEl.appendChild(row);
        });
    }

    // _reactivateSection: Rueckkehrer (inaktiv, aber wieder im AD).
    function _reactivateSection(doc, mainEl, data, words, opts, setResult) {
        var cands = data.reactivate_candidates || [];
        if (!cands.length) { return; }
        var h = doc.createElement('h3');
        h.className = 'aiw-adsync-sect';
        h.textContent = '[Reaktivierungs-Kandidaten] ' + EM_DASH
            + ' wieder im AD; Reaktivierung nur nach Eingabe von „'
            + words.reactivate + '“ (historische Rollen werden wieder '
            + 'wirksam)';
        mainEl.appendChild(h);

        cands.forEach(function (c) {
            var row = _candidateRow(
                doc,
                c.system_username + ' · ' + c.display_name
                    + ' (AD: ' + c.display_name_ad + ')',
                words.reactivate, false,
                [{
                    label: 'Reaktivieren', cls: 'aiw-adsync-react',
                    onClick: function (typed) {
                        if (!validateWord(words.reactivate, typed)) {
                            setResult('Nicht vollzogen: Bestaetigungswort '
                                + 'entspricht nicht exakt „'
                                + words.reactivate + '“.', true);
                            return;
                        }
                        if (typeof opts.onDecide === 'function') {
                            opts.onDecide(decideBody(
                                c.system_username, 'reactivate', typed,
                                null, c.display_name_ad));
                        }
                    }
                }]);
            mainEl.appendChild(row);
        });
    }

    // ------------------------------------------------------------------ Export
    var api = {
        renderAdSync: renderAdSync,
        // reine Funktionen fuer vitest:
        counts: counts,
        hasAutomatic: hasAutomatic,
        summaryText: summaryText,
        confirmWords: confirmWords,
        validateWord: validateWord,
        decideBody: decideBody
    };
    if (typeof window !== 'undefined') {
        window.AIWCockpitAdSync = api;
    }
})();
