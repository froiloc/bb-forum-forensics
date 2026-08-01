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
// Build 636 (Vorgang 17200856, Welle B4): HILFE-MARKEN fuer die
//   drei Bedienelemente dieser Sicht.
// Version: v0.8.636 · Build: 636 · 2026-08-01
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

    var SICHT = 'promotion';   // Praefix der Hilfe-Anker + Zustandsschluessel

    // _tk / _mitHilfe (Build 557): gemeinsames Tabellen-Werkzeug + Hilfe-Anker
    // der Spaltenkoepfe. LAZY, damit die Ladereihenfolge diese Sicht nicht
    // lautlos brechen kann.
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

    // statusRang: der Zustand als Zahl — die Stellung im ARBEITSABLAUF.
    //
    // Sie steuert die Sortierung der Zustandsspalte. ALPHABETISCH stuende
    // 'fremdzustaendig' vor 'gesichtet' vor 'offen' — also der Endzustand vor
    // dem Handlungsbedarf. Eine Spalte, die nach Bearbeitungsstand aussieht
    // und alphabetisch sortiert, fuehrt genau die in die Irre, die sehen will,
    // was noch zu tun ist. Sortiert wird deshalb ueber STATUS_ORDER
    // (offen -> gesichtet -> zurueckgestellt -> uebernommen ->
    // fremdzustaendig), also Handlungsbedarf zuerst — dieselbe Ordnung, die
    // countsModel() schon fuer die Zaehlerzeile benutzt.
    //
    // Ein unbekannter Zustand bekommt einen Rang HINTER allen bekannten: er
    // verschwindet nicht, er sortiert zuletzt (Grundregel 1).
    function statusRang(status) {
        var i = STATUS_ORDER.indexOf(status == null ? INITIAL : status);
        return (i === -1) ? STATUS_ORDER.length : i;
    }

    // toRows: Kandidaten -> Tabellenzeilen. REIN (kein DOM).
    //
    // Abgeleitete Felder:
    //   * 'zustand' traegt das LABEL — fuenf Werte, also eine Auswahlliste.
    //     Der Code bleibt als 'status' erhalten (Ampelpunkt), der Rang als
    //     'zustand_rang' (Sortierung, s. o.).
    //   * Leere Freitexte werden zu '—': eine leere Zelle sieht aus wie ein
    //     Anzeigefehler, ein Gedankenstrich sagt 'nichts hinterlegt'.
    function toRows(data) {
        return candidateRows(data).map(function (row) {
            return {
                subject_id: row.subject_id,
                status: row.status,
                zustand: row.status_label || statusLabel(row.status),
                zustand_rang: statusRang(row.status),
                grund: row.grund || EM_DASH,
                herkunft: row.herkunft || EM_DASH,
                is_final: isFinal(row.status),
                _kandidat: row
            };
        });
    }

    // spalten: die Spaltendefinition (Build 557). Braucht 'doc' (Formatter
    // bauen DOM), 'canEdit' und den Rueckruf fuer das Begruendungs-Panel.
    function spalten(doc, canEdit, openPanel) {
        return [
            { title: 'Fall (subject_id)', field: 'subject_id', width: 170,
              hozAlign: 'right' },
            {
                title: 'Zustand', field: 'zustand', width: 220,
                // Sortiert nach ARBEITSABLAUF, nicht alphabetisch (s.
                // statusRang) — Handlungsbedarf zuerst.
                sorter: function (a, b, aRow, bRow) {
                    return aRow.getData().zustand_rang
                        - bRow.getData().zustand_rang;
                },
                formatter: function (cell) {
                    var d = cell.getData();
                    var wrap = doc.createElement('span');
                    var dot = doc.createElement('span');
                    dot.className = 'dot ' + statusDotClass(d.status);
                    wrap.appendChild(dot);
                    var tx = doc.createElement('span');
                    tx.textContent = ' ' + d.zustand;
                    wrap.appendChild(tx);
                    return wrap;
                }
            },
            { title: 'Grund', field: 'grund', widthGrow: 2 },
            { title: 'Herkunft', field: 'herkunft', widthGrow: 1 },
            {
                title: 'Aktion', field: 'aktion', width: 260,
                headerSort: false,
                kein_filter: true,   // ein Filter auf Knoepfen waere sinnlos
                formatter: function (cell) {
                    var d = cell.getData();
                    var box = doc.createElement('span');
                    box.className = 'aiw-promo-actions';
                    var actions = allowedActions(d.status);
                    if (!canEdit || !actions.length) {
                        box.textContent = d.is_final ? 'endgueltig' : EM_DASH;
                        return box;
                    }
                    actions.forEach(function (target) {
                        var b = doc.createElement('button');
                        b.type = 'button';
                        b.className = 'aiw-btn aiw-promo-btn';
                        b.setAttribute('data-uid', String(d.subject_id));
                        b.setAttribute('data-target', target);
                        b.textContent = ACTION_LABEL[target] || target;
                        // Build 636 (Vorgang 17200856): Die Kennung war
                        // GERECHNET (SICHT + '.bedienung.entscheiden'). Den
                        // Text gab es seit Build 604 im Register, erreichbar
                        // war er nie - weder SP01/SP02 noch die Erhebung
                        // sehen eine gerechnete Kennung. Jetzt literal.
                        b.setAttribute('data-hilfe-id',
                            'promotion.bedienung.entscheiden');
                        b.addEventListener('click', function (ev) {
                            if (ev && typeof ev.stopPropagation === 'function') {
                                ev.stopPropagation();
                            }
                            openPanel(d._kandidat, target);
                        });
                        box.appendChild(b);
                    });
                    return box;
                }
            }
        ];
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
        // Build 605 (Baustelle H / H14): literale Hilfe-Marken.
        h.className = 'aiw-pagehead';
        h.setAttribute('data-hilfe-id', 'promotion.titel');
        h.textContent = 'Fremdforum-Promotion';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'promotion.kennzeile');
        sub.textContent = 'Faelle mit forensic-Datei, aber ohne Arbeitsstand '
            + '(evidence). Jede Entscheidung wird auditiert; '
            + '„uebernommen“ und „fremdzustaendig“ sind '
            + 'endgueltig.';
        mainEl.appendChild(sub);

        // --- Kennzahlen ------------------------------------------------------
        var counts = doc.createElement('div');
        counts.className = 'aiw-promo-counts';
        counts.setAttribute('data-hilfe-id', 'promotion.zahlen');
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
                warn.setAttribute('data-hilfe-id', 'promotion.warnung');
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
            inH.setAttribute('data-hilfe-id', 'promotion.bedienung.herkunft');
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
            inG.setAttribute('data-hilfe-id', 'promotion.bedienung.grund');
            lblG.appendChild(inG);
            panel.appendChild(lblG);

            var ok = doc.createElement('button');
            ok.type = 'button';
            ok.id = 'aiw-promo-confirm';
            ok.setAttribute('data-hilfe-id', 'promotion.bedienung.bestaetigen');
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
            cancel.setAttribute('data-hilfe-id', 'promotion.bedienung.abbrechen');
            cancel.className = 'aiw-btn aiw-promo-btn';
            cancel.textContent = 'Abbrechen';
            cancel.addEventListener('click', function () {
                closePanel();
                setResult('Abgebrochen. Es wurde nichts geschrieben.', false);
            });
            panel.appendChild(cancel);

            log('openPanel', row.subject_id, '->', target, 'reason?', req);
        }

        // --- Tabelle (Build 557: Tabulator + gemeinsames Werkzeug) -----------
        //
        // DER LEERE FALL BEKOMMT KEINE SONDERBEHANDLUNG MEHR. Frueher stand
        // bei null Kandidaten ein Absatz STATT einer Tabelle; damit fehlten
        // dort auch Werkzeugleiste und Trefferzahl, und die Sicht sah anders
        // aus als alle anderen. Jetzt steht die Tabelle immer, und der
        // Leerzustand ist Tabulators 'placeholder' — mit demselben Wortlaut
        // wie bisher, denn er erklaert, WARUM nichts da ist (kein Fall mit
        // forensic-, aber ohne evidence-Datei).
        var TK = _tk();
        var tabRows = toRows(data);
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);

        if (!TK) {
            var none = doc.createElement('p');
            none.className = 'aiw-placeholder';
            none.textContent = 'Gemeinsames Tabellen-Werkzeug nicht geladen — '
                + 'es liegen ' + tabRows.length + ' Kandidaten vor.';
            mainEl.appendChild(none);
            log('renderPromotion: kein TableKit');
            return { setResult: setResult, table: null };
        }

        var auf = TK.tabelleAufbauen(doc, mainEl, {
            sicht: SICHT,
            rows: tabRows,
            columns: _mitHilfe(spalten(doc, canEdit, openPanel), SICHT, doc),
            Ctor: Ctor,
            einheit: 'Kandidaten',
            tabulator: {
                index: 'subject_id',
                height: '420px',
                placeholder: 'Zurzeit keine Fremdforum-Kandidaten '
                    + '(kein Fall mit forensic-, aber ohne evidence-Datei).'
                // KEIN 'initialSort': der Server liefert die Kandidaten in
                // seiner Ordnung, und eine Voreinstellung wuerde sie
                // ueberschreiben.
            }
        });

        log('renderPromotion:', tabRows.length, 'Kandidat(en), canEdit',
            canEdit);
        return { setResult: setResult, table: auf.table };
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
        // Build 557: reine Abbildung + Spaltendefinition (vitest).
        statusRang: statusRang,
        toRows: toRows,
        spalten: spalten,
        // DOM
        renderPromotion: renderPromotion,
        // Konstanten (fuer Tests/Introspektion)
        STORED: STORED,
        STATUS_ORDER: STATUS_ORDER
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitPromotion = API; }
})();
