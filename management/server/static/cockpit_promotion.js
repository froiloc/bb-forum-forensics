// =============================================================================
// management/server/static/cockpit_promotion.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Fremdforum-Promotion
// =============================================================================
// Zweck (Idee 25 / Fundament F3, Frontend zu Build 460):
//   Rendert die Fremdforum-Promotions-Sicht (/api/promotion). Ein FREMDFORUM-
//   KANDIDAT ist ein Fall mit forensic_<uid>.db, aber OHNE evidence_<uid>.db
//   (der Prepper hat geliefert, es fehlt der Arbeitsstand). Diese Sicht macht
//   die bislang IMPLIZITE Entscheidung ("wird der Kandidat uebernommen?")
//   sichtbar und BELEGBAR: je Kandidat kann eine Chef-Ermittlerin (Recht
//   'ops.promote') den Zustand setzen — die Zustandsmaschine des Servers
//   (ops/promotion_status.py) erzwingt zulaessige Uebergaenge, das Repo die
//   Grund-Pflicht. Endzustaende ('uebernommen'/'fremdzustaendig') sind
//   ENDGUELTIG.
//
// Datenform GET /api/promotion (Backend ManagementApp._promotion, Build 460):
//   {
//     candidate_count: int,
//     counts: { offen, gesichtet, uebernommen, zurueckgestellt, fremdzustaendig },
//     statuses: ["gesichtet","uebernommen","zurueckgestellt","fremdzustaendig"],
//     candidates: [ {subject_id, status, status_label, grund, herkunft,
//                    decided_at, decided_by, is_final}, ... ],
//     decisions: [ ...alle forum_promotion-Zeilen (Belege)... ]
//   }
//
// SCHREIBEN: opts.onDecide({subject_id, status, grund, herkunft}) -> der Aufrufer
//   (cockpit.js) sendet POST /api/promotion/decide mit X-AIW-Token und laedt
//   danach die Sicht NEU (KEIN optimistisches UI, Grundregel 1).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE-Wrapper mit 'use strict'.
//   2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG), zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
//   4) Reine Funktionen fassen NIE das DOM an -> vitest testet den ECHTEN Code
//      (UMD-Ausgang). Der DOM-Teil ist gekapselt und ueber Injektion (opts.doc)
//      auch in JSDOM voll testbar.
//
// SICHERHEIT (XSS): ALLE variablen Texte (grund, herkunft, Labels) werden via
//   textContent gesetzt, nie via innerHTML.
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
        args.unshift('[AIW-Promotion]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';

    // =========================================================================
    // 0) ZUSTANDSMODELL (Spiegel der Server-Zustandsmaschine promotion_status.py)
    //    Der Spiegel liegt bewusst HIER, damit die Oberflaeche nur die WIRKLICH
    //    zulaessigen Aktionen anbietet. Die VERBINDLICHE Pruefung bleibt der
    //    Server (der Client kann nie mehr erlauben als das Backend) — hier geht
    //    es nur darum, keine sinnlosen Buttons zu zeigen (z. B. an einem
    //    endgueltigen Kandidaten).
    // =========================================================================

    //: Implizite Eingangslage (nie gespeichert) — Kandidat ohne Entscheidung.
    var INITIAL = 'offen';

    //: Gespeicherte Zustaende (== CHECK in M015).
    var STORED = ['gesichtet', 'uebernommen', 'zurueckgestellt',
                  'fremdzustaendig'];

    //: Endzustaende — unwiderruflich.
    var FINAL = ['uebernommen', 'fremdzustaendig'];

    //: Zielzustaende mit Grund-Pflicht.
    var REASON_REQUIRED = ['zurueckgestellt', 'fremdzustaendig'];

    //: Erlaubte Uebergaenge (inkl. der impliziten Eingangslage 'offen').
    var ALLOWED = {
        offen: ['gesichtet', 'uebernommen', 'zurueckgestellt', 'fremdzustaendig'],
        gesichtet: ['uebernommen', 'zurueckgestellt', 'fremdzustaendig'],
        zurueckgestellt: ['gesichtet', 'uebernommen', 'fremdzustaendig'],
        uebernommen: [],
        fremdzustaendig: []
    };

    //: Anzeige-Reihenfolge (Handlungsbedarf zuerst).
    var STATUS_ORDER = ['offen', 'gesichtet', 'zurueckgestellt',
                        'uebernommen', 'fremdzustaendig'];

    var STATUS_LABEL = {
        offen: 'offen (unentschieden)',
        gesichtet: 'gesichtet (Entscheidung ausstehend)',
        uebernommen: 'in Ermittlung uebernommen',
        zurueckgestellt: 'zurueckgestellt',
        fremdzustaendig: 'fremdzustaendig'
    };

    //: Knappe Beschriftung des Aktions-Buttons je Zielzustand.
    var ACTION_LABEL = {
        gesichtet: 'Als gesichtet markieren',
        uebernommen: 'Uebernehmen',
        zurueckgestellt: 'Zurueckstellen',
        fremdzustaendig: 'Fremdzustaendig'
    };

    // ------------------------------------------------------------------ Helfer
    function isFinal(status) {
        return FINAL.indexOf(status) !== -1;
    }
    function reasonRequired(target) {
        return REASON_REQUIRED.indexOf(target) !== -1;
    }
    // allowedActions: die aus 'status' zulaessigen Zielzustaende (leer bei
    // Endzustand oder unbekanntem Zustand — NIE ein Fehler, damit die Sicht
    // nie ganz zerbricht; ein unbekannter Zustand zeigt eben keine Aktion).
    function allowedActions(status) {
        var key = (status == null) ? INITIAL : status;
        return ALLOWED[key] ? ALLOWED[key].slice() : [];
    }
    function statusLabel(status) {
        return STATUS_LABEL[status] || status || INITIAL;
    }
    // statusDotClass: Ampelpunkt-Klasse (nur die drei vorhandenen Farben).
    //   gruen = uebernommen (in Bearbeitung), rot = fremdzustaendig (raus),
    //   gelb = alles Offene/Geparkte (Handlungsbedarf).
    function statusDotClass(status) {
        if (status === 'uebernommen') { return 'gruen'; }
        if (status === 'fremdzustaendig') { return 'rot'; }
        return 'gelb';
    }

    // countsModel: aus der Server-'counts'-Map eine geordnete Liste mit Labels
    // (Handlungsbedarf zuerst). Fehlende Schluessel -> 0 (nicht verschluckt).
    function countsModel(data) {
        data = data || {};
        var counts = data.counts || {};
        return STATUS_ORDER.map(function (s) {
            return { status: s, label: statusLabel(s),
                     count: counts[s] != null ? counts[s] : 0 };
        });
    }

    // candidateRows: die Kandidatenliste (defensiv: immer ein Array).
    function candidateRows(data) {
        data = data || {};
        return Array.isArray(data.candidates) ? data.candidates : [];
    }

    // =========================================================================
    // 1) DOM: Sicht rendern.
    // =========================================================================
    function renderPromotion(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return { setResult: function () {} }; }
        data = data || {};
        var canEdit = opts.canEdit === true;
        var rows = candidateRows(data);

        mainEl.textContent = '';

        // --- Kopf ------------------------------------------------------------
        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Fremdforum-Promotion';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Faelle mit forensic-Datei, aber ohne Arbeitsstand '
            + '(evidence). Jede Entscheidung wird auditiert; '
            + '„uebernommen“ und „fremdzustaendig“ sind '
            + 'endgueltig.';
        mainEl.appendChild(sub);

        // --- Kennzahlen ------------------------------------------------------
        var counts = doc.createElement('div');
        counts.className = 'aiw-promo-counts';
        countsModel(data).forEach(function (c) {
            var badge = doc.createElement('span');
            badge.className = 'aiw-badge aiw-promo-badge';
            var dot = doc.createElement('span');
            dot.className = 'dot ' + statusDotClass(c.status);
            badge.appendChild(dot);
            var t = doc.createElement('span');
            t.textContent = ' ' + c.label + ': ' + c.count;
            badge.appendChild(t);
            counts.appendChild(badge);
        });
        mainEl.appendChild(counts);

        if (!canEdit) {
            var hint = doc.createElement('p');
            hint.className = 'aiw-pagesub aiw-promo-readonly';
            hint.textContent = 'Nur lesend — zum Entscheiden fehlt das '
                + 'Recht „ops.promote“.';
            mainEl.appendChild(hint);
        }

        // --- Ergebnis-/Meldezeile (gemeinsam) --------------------------------
        var result = doc.createElement('div');
        result.className = 'aiw-promo-result';
        result.id = 'aiw-promo-result';
        mainEl.appendChild(result);

        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }

        // --- Entscheidungs-Panel (immer genau EINES offen) -------------------
        var panel = doc.createElement('div');
        panel.className = 'aiw-promo-panel';
        panel.id = 'aiw-promo-panel';
        mainEl.appendChild(panel);

        function closePanel() { panel.textContent = ''; }

        // openPanel: baut das Eingabefeld fuer EINE Entscheidung (uid -> target).
        // Endgueltige Ziele bekommen eine deutliche Warnung; grund-pflichtige
        // Ziele erzwingen eine nichtleere Eingabe (sonst kein onDecide).
        function openPanel(row, target) {
            panel.textContent = '';

            var title = doc.createElement('div');
            title.className = 'aiw-promo-panel-title';
            title.textContent = 'Kandidat ' + row.subject_id + ' ' + EM_DASH + ' '
                + (ACTION_LABEL[target] || target);
            panel.appendChild(title);

            if (isFinal(target)) {
                var warn = doc.createElement('div');
                warn.className = 'aiw-promo-warn';
                warn.textContent = 'Endgueltig — kein Weg zurueck. '
                    + 'Ein Irrtum wird durch eine neue Entscheidung korrigiert.';
                panel.appendChild(warn);
            }

            // Herkunft (optional) — Hinweis auf das Quell-/Fremdforum.
            var lblH = doc.createElement('label');
            lblH.className = 'aiw-promo-lbl';
            lblH.textContent = 'Herkunft (optional): ';
            var inH = doc.createElement('input');
            inH.type = 'text';
            inH.id = 'aiw-promo-herkunft';
            inH.className = 'aiw-promo-input';
            if (row.herkunft) { inH.value = row.herkunft; }
            lblH.appendChild(inH);
            panel.appendChild(lblH);

            // Grund — Pflicht bei zurueckgestellt/fremdzustaendig.
            var req = reasonRequired(target);
            var lblG = doc.createElement('label');
            lblG.className = 'aiw-promo-lbl';
            lblG.textContent = req ? 'Grund (Pflicht): ' : 'Grund (optional): ';
            var inG = doc.createElement('input');
            inG.type = 'text';
            inG.id = 'aiw-promo-grund';
            inG.className = 'aiw-promo-input';
            lblG.appendChild(inG);
            panel.appendChild(lblG);

            var ok = doc.createElement('button');
            ok.type = 'button';
            ok.id = 'aiw-promo-confirm';
            ok.className = 'aiw-btn aiw-promo-btn';
            ok.textContent = 'Bestaetigen';
            ok.addEventListener('click', function () {
                var grund = (inG.value || '').trim();
                var herkunft = (inH.value || '').trim();
                if (req && !grund) {
                    setResult('Grund ist Pflicht: der Uebergang nach „'
                        + (ACTION_LABEL[target] || target)
                        + '“ darf nicht ohne Grund erfolgen.', true);
                    return;
                }
                closePanel();
                setResult('Speichere Entscheidung …', null);
                if (typeof opts.onDecide === 'function') {
                    opts.onDecide({
                        subject_id: row.subject_id, status: target,
                        grund: grund, herkunft: herkunft || null
                    });
                } else {
                    setResult('Kein Schreibpfad verdrahtet.', true);
                }
            });
            panel.appendChild(ok);

            var cancel = doc.createElement('button');
            cancel.type = 'button';
            cancel.id = 'aiw-promo-cancel';
            cancel.className = 'aiw-btn aiw-promo-btn';
            cancel.textContent = 'Abbrechen';
            cancel.addEventListener('click', function () {
                closePanel();
                setResult('Abgebrochen. Es wurde nichts geschrieben.', false);
            });
            panel.appendChild(cancel);

            log('openPanel', row.subject_id, '->', target, 'reason?', req);
        }

        // --- Tabelle (schlichtes, XSS-sicheres <table>) ----------------------
        if (!rows.length) {
            var none = doc.createElement('p');
            none.className = 'aiw-placeholder';
            none.textContent = 'Zurzeit keine Fremdforum-Kandidaten '
                + '(kein Fall mit forensic-, aber ohne evidence-Datei).';
            mainEl.appendChild(none);
        } else {
            var table = doc.createElement('table');
            table.className = 'aiw-promo-table';
            var thead = doc.createElement('thead');
            var htr = doc.createElement('tr');
            ['Fall (subject_id)', 'Zustand', 'Grund', 'Herkunft', 'Aktion']
                .forEach(function (label) {
                    var th = doc.createElement('th');
                    th.textContent = label;
                    htr.appendChild(th);
                });
            thead.appendChild(htr);
            table.appendChild(thead);

            var tbody = doc.createElement('tbody');
            rows.forEach(function (row) {
                tbody.appendChild(_rowEl(doc, row, canEdit, openPanel));
            });
            table.appendChild(tbody);
            mainEl.appendChild(table);
        }

        log('renderPromotion:', rows.length, 'Kandidat(en), canEdit', canEdit);
        return { setResult: setResult };
    }

    // _rowEl: eine Tabellenzeile fuer einen Kandidaten. Aktionen erscheinen nur
    // mit Schreibrecht UND nur, soweit die Zustandsmaschine sie zulaesst.
    function _rowEl(doc, row, canEdit, openPanel) {
        var tr = doc.createElement('tr');
        tr.setAttribute('data-uid', String(row.subject_id));

        var tdId = doc.createElement('td');
        tdId.textContent = String(row.subject_id);
        tr.appendChild(tdId);

        var tdStatus = doc.createElement('td');
        var dot = doc.createElement('span');
        dot.className = 'dot ' + statusDotClass(row.status);
        tdStatus.appendChild(dot);
        var stx = doc.createElement('span');
        stx.textContent = ' ' + (row.status_label || statusLabel(row.status));
        tdStatus.appendChild(stx);
        tr.appendChild(tdStatus);

        var tdGrund = doc.createElement('td');
        tdGrund.textContent = row.grund || EM_DASH;
        tr.appendChild(tdGrund);

        var tdHerk = doc.createElement('td');
        tdHerk.textContent = row.herkunft || EM_DASH;
        tr.appendChild(tdHerk);

        var tdAct = doc.createElement('td');
        tdAct.className = 'aiw-promo-actions';
        var actions = allowedActions(row.status);
        if (!canEdit || !actions.length) {
            tdAct.textContent = isFinal(row.status) ? 'endgueltig' : EM_DASH;
        } else {
            actions.forEach(function (target) {
                var b = doc.createElement('button');
                b.type = 'button';
                b.className = 'aiw-btn aiw-promo-btn';
                b.setAttribute('data-uid', String(row.subject_id));
                b.setAttribute('data-target', target);
                b.textContent = ACTION_LABEL[target] || target;
                b.addEventListener('click', function () {
                    openPanel(row, target);
                });
                tdAct.appendChild(b);
            });
        }
        tr.appendChild(tdAct);
        return tr;
    }

    // =========================================================================
    // 2) UMD-Ausgang.
    // =========================================================================
    var API = {
        // reine Helfer (vitest)
        allowedActions: allowedActions,
        reasonRequired: reasonRequired,
        isFinal: isFinal,
        statusLabel: statusLabel,
        statusDotClass: statusDotClass,
        countsModel: countsModel,
        candidateRows: candidateRows,
        // DOM
        renderPromotion: renderPromotion,
        // Konstanten (fuer Tests/Introspektion)
        STORED: STORED,
        STATUS_ORDER: STATUS_ORDER
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitPromotion = API; }
})();
