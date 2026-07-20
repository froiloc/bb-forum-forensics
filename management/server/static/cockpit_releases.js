// =============================================================================
// management/server/static/cockpit_releases.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Externe Fallfreigabe
// =============================================================================
// Zweck (Idee 26, Frontend zu Build 462):
//   Rendert die Sicht der externen Fallfreigaben (/api/releases). Eine Freigabe
//   macht einen Fall einem bestaetigten NRW-Ermittler zugaenglich — belegt,
//   geprueft (Unbedenklichkeit, Fallregel 3) und widerrufbar. Drei Bedingungen
//   erzwingt der Server (ManagementApp/CaseReleaseRepo/ADDirectory): AD-ACL,
//   Unbedenklichkeits-Grundlage (Pflicht), Audit. Diese Sicht bietet nur an,
//   was der Server auch zulaesst — die VERBINDLICHE Pruefung bleibt hinten.
//
// Datenform GET /api/releases (Backend ManagementApp._releases, Build 462):
//   {
//     count: int,
//     counts: { freigegeben, widerrufen },
//     umfang_catalog: [ {code, label}, ... ],
//     recipients: [ {kennung, display_name}, ... ],   // berechtigte NRW-Empfaenger (F4)
//     ad_group: str|null,
//     releases: [ {id, subject_id, fall_username, recipient_kennung,
//                  recipient_display, umfang, umfang_label, status,
//                  status_label, unbedenklichkeit_grundlage, grund_widerruf}, ... ]
//   }
//
// SCHREIBEN (opts, verdrahtet in cockpit.js -> postJson mit X-AIW-Token):
//   onGrant({subject_id, recipient_kennung, umfang, unbedenklichkeit_grundlage})
//   onRevoke({release_id, grund})
//   KEIN optimistisches UI: nach dem Schreiben laedt cockpit.js die Sicht NEU.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS: (1) IIFE + 'use strict'. (2) DEV-Logging
//   (AIW_COCKPIT_DEBUG). (3) ausfuehrliche Kommentare. (4) reine Funktionen
//   fassen NIE das DOM an -> vitest testet den ECHTEN Code (UMD-Ausgang);
//   opts.doc injizierbar (JSDOM).
//
// SICHERHEIT (XSS): alle variablen Texte via textContent, nie via innerHTML.
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
        args.unshift('[AIW-Releases]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';

    // =========================================================================
    // 0) Modell-Konstanten (Spiegel des Server-Zustands; die Wahrheit bleibt
    //    der Server, hier nur die Anzeige-Logik).
    // =========================================================================
    var STATUS_ORDER = ['freigegeben', 'widerrufen'];
    var STATUS_LABEL = {
        freigegeben: 'freigegeben (aktiver externer Zugriff)',
        widerrufen: 'widerrufen (Zugriff zurueckgezogen)'
    };

    // ------------------------------------------------------------------ Helfer
    // statusDotClass: gruen = aktiver Zugriff (freigegeben), grau = beendet
    // (widerrufen). 'grau' wird in cockpit.css definiert (Build 463).
    function statusDotClass(status) {
        if (status === 'freigegeben') { return 'gruen'; }
        if (status === 'widerrufen') { return 'grau'; }
        return 'gelb';
    }
    function statusLabel(status) {
        return STATUS_LABEL[status] || status;
    }
    // allowedRevoke: nur eine AKTIVE Freigabe kann widerrufen werden.
    function allowedRevoke(status) {
        return status === 'freigegeben';
    }

    // countsModel: geordnete Kennzahl-Liste (fehlende Schluessel -> 0).
    function countsModel(data) {
        data = data || {};
        var counts = data.counts || {};
        return STATUS_ORDER.map(function (s) {
            return { status: s, label: statusLabel(s),
                     count: counts[s] != null ? counts[s] : 0 };
        });
    }

    function releaseRows(data) {
        data = data || {};
        return Array.isArray(data.releases) ? data.releases : [];
    }
    function recipientOptions(data) {
        data = data || {};
        return Array.isArray(data.recipients) ? data.recipients : [];
    }
    function umfangOptions(data) {
        data = data || {};
        return Array.isArray(data.umfang_catalog) ? data.umfang_catalog : [];
    }

    // =========================================================================
    // 1) DOM: Sicht rendern.
    // =========================================================================
    function renderReleases(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return { setResult: function () {} }; }
        data = data || {};
        var canEdit = opts.canEdit === true;

        mainEl.textContent = '';

        // --- Kopf ------------------------------------------------------------
        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Externe Fallfreigabe';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        var grp = data.ad_group ? (' Berechtigte Gruppe: ' + data.ad_group + '.')
            : '';
        sub.textContent = 'Weitergabe eines Falls an einen bestaetigten '
            + 'NRW-Ermittler — nach Unbedenklichkeitspruefung, auditiert und '
            + 'widerrufbar.' + grp;
        mainEl.appendChild(sub);

        // --- Kennzahlen ------------------------------------------------------
        var counts = doc.createElement('div');
        counts.className = 'aiw-rel-counts';
        countsModel(data).forEach(function (c) {
            var badge = doc.createElement('span');
            badge.className = 'aiw-badge aiw-rel-badge';
            var dot = doc.createElement('span');
            dot.className = 'dot ' + statusDotClass(c.status);
            badge.appendChild(dot);
            var t = doc.createElement('span');
            t.textContent = ' ' + c.label + ': ' + c.count;
            badge.appendChild(t);
            counts.appendChild(badge);
        });
        mainEl.appendChild(counts);

        // --- Ergebnis-/Meldezeile (gemeinsam) --------------------------------
        var result = doc.createElement('div');
        result.className = 'aiw-rel-result';
        result.id = 'aiw-rel-result';

        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }

        // --- Neue Freigabe (nur mit Schreibrecht) ----------------------------
        if (canEdit) {
            mainEl.appendChild(
                _grantForm(doc, data, opts, setResult));
        } else {
            var ro = doc.createElement('p');
            ro.className = 'aiw-pagesub aiw-rel-readonly';
            ro.textContent = 'Nur lesend — zum Freigeben/Widerrufen fehlt das '
                + 'Recht „release.grant“.';
            mainEl.appendChild(ro);
        }

        // Ergebniszeile NACH dem Formular, VOR der Tabelle.
        mainEl.appendChild(result);

        // --- Widerruf-Panel (immer genau EINES offen) ------------------------
        var panel = doc.createElement('div');
        panel.className = 'aiw-rel-panel';
        panel.id = 'aiw-rel-panel';
        mainEl.appendChild(panel);

        function closePanel() { panel.textContent = ''; }

        // openRevoke: Grund-Eingabe fuer den Widerruf EINER Freigabe.
        function openRevoke(row) {
            panel.textContent = '';
            var title = doc.createElement('div');
            title.className = 'aiw-rel-panel-title';
            title.textContent = 'Freigabe ' + row.id + ' widerrufen '
                + '(Fall ' + row.subject_id + ' → '
                + (row.recipient_display || row.recipient_kennung) + ')';
            panel.appendChild(title);

            var warn = doc.createElement('div');
            warn.className = 'aiw-rel-warn';
            warn.textContent = 'Endgueltig — ein Widerruf kann nicht '
                + 'zurueckgenommen werden. Eine erneute Freigabe ist ein neuer '
                + 'Vorgang.';
            panel.appendChild(warn);

            var lbl = doc.createElement('label');
            lbl.className = 'aiw-rel-lbl';
            lbl.textContent = 'Grund (Pflicht): ';
            var inG = doc.createElement('input');
            inG.type = 'text';
            inG.id = 'aiw-rel-revoke-grund';
            inG.className = 'aiw-rel-input';
            lbl.appendChild(inG);
            panel.appendChild(lbl);

            var ok = doc.createElement('button');
            ok.type = 'button';
            ok.id = 'aiw-rel-revoke-confirm';
            ok.className = 'aiw-btn aiw-rel-btn';
            ok.textContent = 'Widerrufen';
            ok.addEventListener('click', function () {
                var grund = (inG.value || '').trim();
                if (!grund) {
                    setResult('Grund ist Pflicht: ein Widerruf darf nicht ohne '
                        + 'nachvollziehbaren Grund erfolgen.', true);
                    return;
                }
                closePanel();
                setResult('Widerrufe Freigabe …', null);
                if (typeof opts.onRevoke === 'function') {
                    opts.onRevoke({ release_id: row.id, grund: grund });
                } else {
                    setResult('Kein Schreibpfad verdrahtet.', true);
                }
            });
            panel.appendChild(ok);

            var cancel = doc.createElement('button');
            cancel.type = 'button';
            cancel.id = 'aiw-rel-revoke-cancel';
            cancel.className = 'aiw-btn aiw-rel-btn';
            cancel.textContent = 'Abbrechen';
            cancel.addEventListener('click', function () {
                closePanel();
                setResult('Abgebrochen. Es wurde nichts geschrieben.', false);
            });
            panel.appendChild(cancel);
            log('openRevoke', row.id);
        }

        // --- Tabelle ---------------------------------------------------------
        var rows = releaseRows(data);
        if (!rows.length) {
            var none = doc.createElement('p');
            none.className = 'aiw-placeholder';
            none.textContent = 'Noch keine externen Fallfreigaben erfasst.';
            mainEl.appendChild(none);
        } else {
            var table = doc.createElement('table');
            table.className = 'aiw-rel-table';
            var thead = doc.createElement('thead');
            var htr = doc.createElement('tr');
            ['Fall', 'Empfaenger', 'Umfang', 'Zustand', 'Aktion']
                .forEach(function (label) {
                    var th = doc.createElement('th');
                    th.textContent = label;
                    htr.appendChild(th);
                });
            thead.appendChild(htr);
            table.appendChild(thead);

            var tbody = doc.createElement('tbody');
            rows.forEach(function (row) {
                tbody.appendChild(_rowEl(doc, row, canEdit, openRevoke));
            });
            table.appendChild(tbody);
            mainEl.appendChild(table);
        }

        log('renderReleases:', rows.length, 'Freigabe(n), canEdit', canEdit);
        return { setResult: setResult };
    }

    // _grantForm: Formular "Neue Freigabe". Ohne berechtigte Empfaenger (leere
    // AD-Allowlist) wird NICHT stillschweigend ein leeres Formular gezeigt,
    // sondern ein deutlicher Hinweis (Grundregel 1).
    function _grantForm(doc, data, opts, setResult) {
        var box = doc.createElement('div');
        box.className = 'aiw-rel-grant';

        var title = doc.createElement('div');
        title.className = 'aiw-rel-grant-title';
        title.textContent = 'Neue Freigabe';
        box.appendChild(title);

        var recipients = recipientOptions(data);
        if (!recipients.length) {
            var hint = doc.createElement('div');
            hint.className = 'aiw-rel-warn';
            hint.textContent = 'Keine berechtigten Empfaenger konfiguriert '
                + '(ad.release_recipients in config.yaml) — Freigabe nicht '
                + 'moeglich (Default-Deny).';
            box.appendChild(hint);
            return box;
        }

        // Fall (subject_id)
        var lblU = doc.createElement('label');
        lblU.className = 'aiw-rel-lbl';
        lblU.textContent = 'Fall (subject_id): ';
        var inU = doc.createElement('input');
        inU.type = 'text';
        inU.id = 'aiw-rel-grant-user';
        inU.className = 'aiw-rel-input';
        lblU.appendChild(inU);
        box.appendChild(lblU);

        // Empfaenger
        var lblR = doc.createElement('label');
        lblR.className = 'aiw-rel-lbl';
        lblR.textContent = 'Empfaenger (NRW): ';
        var selR = doc.createElement('select');
        selR.id = 'aiw-rel-grant-recipient';
        selR.className = 'aiw-rel-input';
        recipients.forEach(function (r) {
            var o = doc.createElement('option');
            o.value = r.kennung;
            o.textContent = r.display_name + ' (' + r.kennung + ')';
            selR.appendChild(o);
        });
        lblR.appendChild(selR);
        box.appendChild(lblR);

        // Umfang
        var lblM = doc.createElement('label');
        lblM.className = 'aiw-rel-lbl';
        lblM.textContent = 'Umfang: ';
        var selM = doc.createElement('select');
        selM.id = 'aiw-rel-grant-umfang';
        selM.className = 'aiw-rel-input';
        umfangOptions(data).forEach(function (u) {
            var o = doc.createElement('option');
            o.value = u.code;
            o.textContent = u.label;
            selM.appendChild(o);
        });
        lblM.appendChild(selM);
        box.appendChild(lblM);

        // Unbedenklichkeits-Grundlage (Pflicht)
        var lblG = doc.createElement('label');
        lblG.className = 'aiw-rel-lbl';
        lblG.textContent = 'Unbedenklichkeit — Grundlage (Pflicht): ';
        var inG = doc.createElement('input');
        inG.type = 'text';
        inG.id = 'aiw-rel-grant-grundlage';
        inG.className = 'aiw-rel-input aiw-rel-input-wide';
        lblG.appendChild(inG);
        box.appendChild(lblG);

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-rel-grant-submit';
        btn.className = 'aiw-btn aiw-rel-btn';
        btn.textContent = 'Freigeben';
        btn.addEventListener('click', function () {
            var raw = (inU.value || '').trim();
            var uid = parseInt(raw, 10);
            if (!raw || isNaN(uid) || String(uid) !== raw) {
                setResult('Fall (subject_id) fehlt oder ist keine ganze Zahl.',
                    true);
                return;
            }
            var grundlage = (inG.value || '').trim();
            if (!grundlage) {
                setResult('Unbedenklichkeits-Grundlage ist Pflicht '
                    + '(Fallregel 3).', true);
                return;
            }
            setResult('Erteile Freigabe …', null);
            if (typeof opts.onGrant === 'function') {
                opts.onGrant({
                    subject_id: uid,
                    recipient_kennung: selR.value,
                    umfang: selM.value,
                    unbedenklichkeit_grundlage: grundlage
                });
            } else {
                setResult('Kein Schreibpfad verdrahtet.', true);
            }
        });
        box.appendChild(btn);
        return box;
    }

    // _rowEl: eine Tabellenzeile fuer eine Freigabe. Der Widerruf-Button
    // erscheint nur mit Schreibrecht UND nur an aktiven Freigaben.
    function _rowEl(doc, row, canEdit, openRevoke) {
        var tr = doc.createElement('tr');
        tr.setAttribute('data-id', String(row.id));

        var tdFall = doc.createElement('td');
        tdFall.textContent = row.subject_id
            + (row.fall_username ? ' (' + row.fall_username + ')' : '');
        tr.appendChild(tdFall);

        var tdEmp = doc.createElement('td');
        tdEmp.textContent = (row.recipient_display || row.recipient_kennung)
            + ' [' + row.recipient_kennung + ']';
        tr.appendChild(tdEmp);

        var tdUmf = doc.createElement('td');
        tdUmf.textContent = row.umfang_label || row.umfang;
        tr.appendChild(tdUmf);

        var tdStatus = doc.createElement('td');
        var dot = doc.createElement('span');
        dot.className = 'dot ' + statusDotClass(row.status);
        tdStatus.appendChild(dot);
        var stx = doc.createElement('span');
        stx.textContent = ' ' + (row.status_label || statusLabel(row.status));
        tdStatus.appendChild(stx);
        tr.appendChild(tdStatus);

        var tdAct = doc.createElement('td');
        tdAct.className = 'aiw-rel-actions';
        if (canEdit && allowedRevoke(row.status)) {
            var b = doc.createElement('button');
            b.type = 'button';
            b.className = 'aiw-btn aiw-rel-btn';
            b.setAttribute('data-id', String(row.id));
            b.setAttribute('data-act', 'revoke');
            b.textContent = 'Widerrufen';
            b.addEventListener('click', function () { openRevoke(row); });
            tdAct.appendChild(b);
        } else {
            tdAct.textContent = (row.status === 'widerrufen')
                ? 'widerrufen' : EM_DASH;
        }
        tr.appendChild(tdAct);
        return tr;
    }

    // =========================================================================
    // 2) UMD-Ausgang.
    // =========================================================================
    var API = {
        countsModel: countsModel,
        statusDotClass: statusDotClass,
        statusLabel: statusLabel,
        allowedRevoke: allowedRevoke,
        releaseRows: releaseRows,
        recipientOptions: recipientOptions,
        umfangOptions: umfangOptions,
        renderReleases: renderReleases,
        STATUS_ORDER: STATUS_ORDER
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitReleases = API; }
})();
