// =============================================================================
// management/server/static/cockpit_crossref.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Kreuzbezug (AP-2A)
// =============================================================================
// Zweck (Ideen 9/10, Frontend zu Build 470):
//   Rendert den KATALOG IDENTIFIZIERTER PERSONEN (/api/crossref) — die
//   Zuordnung eines Forennutzers (subject_id, Prepper-Schema) zu einer realen
//   Person, mit KONFIDENZSTUFE (verdacht < wahrscheinlich < gesichert). Mit dem
//   Recht crossref.edit kann eine Zuordnung angelegt oder revidiert werden (eine
//   Konfidenz reift belegt). Global, NICHT fallbezogen.
//
// Datenform GET /api/crossref (ManagementApp._crossref):
//   { entries: [ {id, subject_id, real_identity, confidence_code,
//                 confidence_ordinal, basis, note, created_by, updated_by,
//                 created_at, updated_at, audit_seq, created_audit_seq}, ... ] }
//   (staerkste Konfidenz zuerst). Optional {entry: {...}} bei ?subject_id=N —
//   hier nutzt die Sicht die Listenform.
//
// SCHREIBEN (opts -> cockpit.js -> postJson mit X-AIW-Token):
//   onSet({subject_id, real_identity, confidence_code, basis, note})
//     -> POST /api/crossref/set. KEIN optimistisches UI: nach dem Schreiben
//        laedt cockpit.js die Sicht NEU (der Server bleibt die Wahrheit).
//   SENSIBILITAET: real_identity/basis/note sind PII-Freitext. Das Frontend
//     reicht nur durch; der Ausschluss aus dem Audit-Payload liegt im Server-
//     Repo. Hier zeigen wir die Werte nur der berechtigten Ermittlerin.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS: (1) IIFE + 'use strict'. (2) DEV-Logging
//   (AIW_COCKPIT_DEBUG). (3) ausfuehrliche Kommentare. (4) reine Funktionen
//   fassen NIE das DOM an -> vitest; opts.doc injizierbar (JSDOM).
// SICHERHEIT (XSS): alle variablen Texte via textContent.
//
// BUILD 555 — TABULATOR + GEMEINSAMES TABELLEN-WERKZEUG:
//   Der Katalog war eine handgebaute <table> ohne Sortierung und ohne Filter.
//   Er ist jetzt eine Tabulator-Tabelle mit Kopffiltern, Trefferzaehler,
//   'Filter zuruecksetzen' und gesicherter Sortierung — dieselbe Bedienung wie
//   in allen uebrigen Listensichten.
//
//   DIE KONFIDENZSPALTE HAT EINEN EIGENEN SORTIERER, und das ist kein Detail:
//   die Werte heissen 'Verdacht', 'wahrscheinlich' und 'gesichert';
//   ALPHABETISCH stuende 'gesichert' vor 'Verdacht' vor 'wahrscheinlich'. Eine
//   Spalte, die nach Beweisstaerke aussieht und alphabetisch sortiert, waere
//   in einem Beweismittelwerkzeug irrefuehrend. Sortiert wird ueber den Rang
//   (10/20/30, deckungsgleich mit der Ordinalkarte des Repos und dem
//   DDL-CHECK aus M018).
//
//   DIE REIHENFOLGE DES SERVERS BLEIBT: er liefert die staerkste Konfidenz
//   zuerst, und das ist eine Aussage. Die Tabelle bekommt deshalb bewusst
//   KEIN 'initialSort'.
//
// Version: v0.8.555 · Build: 555 · 2026-07-26 (Tabulator + tablekit)
//   Build 471: Erstfassung (handgebaute Tabelle).
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
        args.unshift('[AIW-Crossref]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';

    // Konfidenz-Achse 1 (erkenntnisbezogen). Reihenfolge = Beweisstaerke; deckt
    // sich mit dem DDL-CHECK (m018) und der Repo-Ordinalkarte (10/20/30).
    var CONFIDENCE = ['verdacht', 'wahrscheinlich', 'gesichert'];
    var CONFIDENCE_LABEL = {
        verdacht: 'Verdacht',
        wahrscheinlich: 'wahrscheinlich',
        gesichert: 'gesichert'
    };

    var SICHT = 'crossref';   // Praefix der Hilfe-Anker + Zustandsschluessel

    //: Beweisstaerke als Zahl. Sie steuert die SORTIERUNG der Konfidenzspalte.
    //  Die Reihenfolge deckt sich mit der Ordinalkarte des Repos (10/20/30)
    //  und dem DDL-CHECK aus M018.
    var CONFIDENCE_RANG = { verdacht: 10, wahrscheinlich: 20, gesichert: 30 };

    // ------------------------------------------------------------------ Helfer
    // (rein — kein DOM, damit unter vitest direkt pruefbar)

    // _tk / _mitHilfe (Build 555): gemeinsames Tabellen-Werkzeug + Hilfe-Anker
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

    // confidenceRang: Beweisstaerke als Zahl (unbekannt -> 0, also ganz unten).
    // Ein unbekannter Code verschwindet damit NICHT, er sortiert nur zuletzt
    // (Grundregel 1).
    function confidenceRang(code) {
        return Object.prototype.hasOwnProperty.call(CONFIDENCE_RANG, code)
            ? CONFIDENCE_RANG[code] : 0;
    }

    // confidenceLabel: Anzeigetext einer Stufe (unbekannt -> Rohwert).
    function confidenceLabel(code) {
        return CONFIDENCE_LABEL[code] || String(code == null ? '' : code);
    }

    // confidenceClass: CSS-Klassensuffix fuer das Konfidenz-Badge. Drei klar
    // unterscheidbare Stufen: verdacht (schwach) .. gesichert (stark).
    function confidenceClass(code) {
        if (code === 'gesichert') { return 'aiw-conf-gesichert'; }
        if (code === 'wahrscheinlich') { return 'aiw-conf-wahrscheinlich'; }
        if (code === 'verdacht') { return 'aiw-conf-verdacht'; }
        return 'aiw-conf-unbekannt';
    }

    // entries: robuste Extraktion der Listenform.
    function entries(data) {
        return (data && Array.isArray(data.entries)) ? data.entries : [];
    }

    // fmtTs: Epoch-Sekunden -> lokal lesbar; 0/None -> Gedankenstrich.
    function fmtTs(epoch) {
        var n = parseInt(epoch, 10);
        if (!n || isNaN(n)) { return EM_DASH; }
        try {
            return new Date(n * 1000).toLocaleString();
        } catch (e) {
            return String(epoch);
        }
    }

    // toRows: Katalogeintraege -> Tabellenzeilen. REIN (kein DOM).
    //
    // Hier entstehen die abgeleiteten Felder, nach denen gefiltert und sortiert
    // wird:
    //   * 'konfidenz' traegt das LABEL ('Verdacht'/'wahrscheinlich'/
    //     'gesichert') — drei Werte, also eine Auswahlliste. Der Code bleibt
    //     als 'confidence_code' erhalten (Badge-Farbe), der RANG als
    //     'konfidenz_rang' (Sortierung, s. spalten()).
    //   * 'geaendert' ist der bereits formatierte Zeitpunkt; der Rohwert
    //     'updated_at' bleibt daneben stehen, weil danach sortiert wird —
    //     eine Textsortierung ueber '26.07.2026' waere keine Zeitsortierung.
    //   * Leere Freitexte werden zu '—'. Das ist NICHT Kosmetik: eine leere
    //     Zelle sieht aus wie ein Anzeigefehler, ein Gedankenstrich sagt
    //     'nichts hinterlegt'.
    //
    // DIE REIHENFOLGE DER EINGABE BLEIBT ERHALTEN. Der Server liefert die
    // staerkste Konfidenz zuerst (management_app._crossref); diese Funktion
    // sortiert NICHT um, und die Tabelle bekommt bewusst kein 'initialSort'.
    function toRows(data) {
        return entries(data).map(function (e) {
            return {
                subject_id: e.subject_id,
                real_identity: e.real_identity || EM_DASH,
                konfidenz: confidenceLabel(e.confidence_code),
                konfidenz_rang: confidenceRang(e.confidence_code),
                confidence_code: e.confidence_code,
                basis: e.basis || EM_DASH,
                note: e.note || '',
                geaendert: fmtTs(e.updated_at),
                updated_at: e.updated_at,
                _eintrag: e
            };
        });
    }

    // buildPayload: Formularfelder -> POST-Body. REIN. subject_id als Zahl;
    // Freitexte getrimmt; leere Notiz -> weggelassen (Server behandelt null).
    // Wirft NICHT — die Validierung (Pflichtfelder) macht der aufrufende
    // Handler bzw. verbindlich der Server.
    function buildPayload(fields) {
        fields = fields || {};
        var raw = (fields.subject_id == null) ? '' : String(fields.subject_id);
        var sid = parseInt(raw, 10);
        var note = (fields.note == null) ? '' : String(fields.note).trim();
        var body = {
            subject_id: (String(sid) === raw.trim() && !isNaN(sid)) ? sid : null,
            real_identity: String(fields.real_identity || '').trim(),
            confidence_code: String(fields.confidence_code || ''),
            basis: String(fields.basis || '').trim()
        };
        if (note !== '') { body.note = note; }
        return body;
    }

    // =========================================================================
    // 1) DOM: Sicht rendern. data = {entries:[...]} (ggf. leer).
    // =========================================================================
    function renderCrossref(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return { setResult: function () {} }; }
        var canEdit = opts.canEdit === true;

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Kreuzbezug — identifizierte Personen';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Zuordnung eines Forenkontos (subject_id) zu einer '
            + 'realen Person mit Konfidenzstufe. Jede Anlage/Revision wird '
            + 'auditiert.';
        mainEl.appendChild(sub);

        // --- Ergebniszeile ---------------------------------------------------
        var result = doc.createElement('div');
        result.className = 'aiw-xref-result';
        result.id = 'aiw-xref-result';
        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }

        // --- Formular (nur mit crossref.edit) --------------------------------
        if (canEdit) {
            mainEl.appendChild(_form(doc, setResult, opts));
        } else {
            var ro = doc.createElement('p');
            ro.className = 'aiw-pagesub aiw-xref-readonly';
            ro.textContent = 'Nur lesend — zum Pflegen fehlt das Recht '
                + '„crossref.edit“.';
            mainEl.appendChild(ro);
        }
        mainEl.appendChild(result);

        // --- Katalog-Tabelle (Build 555: Tabulator + gemeinsames Werkzeug) ---
        //
        // DER LEERE KATALOG BEKOMMT KEINE SONDERBEHANDLUNG MEHR. Frueher gab
        // es hier einen fruehen Ausstieg mit einem Absatz statt einer Tabelle;
        // damit fehlten bei leerem Katalog auch Werkzeugleiste und
        // Trefferzahl, und die Sicht sah anders aus als alle anderen. Jetzt
        // steht die Tabelle immer, und der Leerzustand ist Tabulators
        // 'placeholder' — derselbe Weg wie in Lektorat und Chef-Freigabe.
        var TK = _tk();
        var rows = toRows(data);
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);

        if (!TK) {
            // Kein stiller Ausfall: die Zahl steht da (Grundregel 1).
            var note = doc.createElement('p');
            note.className = 'aiw-placeholder';
            note.textContent = 'Gemeinsames Tabellen-Werkzeug nicht geladen — '
                + 'es liegen ' + rows.length + ' Zuordnungen vor.';
            mainEl.appendChild(note);
            log('renderCrossref: kein TableKit');
            return { setResult: setResult, table: null };
        }

        var auf = TK.tabelleAufbauen(doc, mainEl, {
            sicht: SICHT,
            rows: rows,
            columns: _mitHilfe(spalten(doc, canEdit), SICHT, doc),
            Ctor: Ctor,
            einheit: 'Zuordnungen',
            tabulator: {
                index: 'subject_id',
                height: '420px',
                placeholder: 'Noch keine Zuordnung im Katalog.'
                // BEWUSST KEIN 'initialSort': der Server liefert die
                // staerkste Konfidenz zuerst (management_app._crossref), und
                // diese Reihenfolge ist eine Aussage. Eine Voreinstellung
                // wuerde sie ueberschreiben.
            }
        });

        log('renderCrossref:', rows.length, 'Eintraege, canEdit', canEdit);
        return { setResult: setResult, table: auf.table };
    }

    // spalten: die Spaltendefinition der Katalogtabelle (Build 555).
    // Braucht 'doc' (Formatter bauen DOM) und 'canEdit' (Aktionsspalte).
    function spalten(doc, canEdit) {
        return [
            { title: 'subject_id', field: 'subject_id', width: 120,
              hozAlign: 'right' },
            { title: 'reale Person', field: 'real_identity', widthGrow: 2 },
            {
                title: 'Konfidenz', field: 'konfidenz', width: 150,
                // EIGENER SORTIERER — und das ist keine Feinheit.
                //
                // Die Werte heissen 'Verdacht', 'wahrscheinlich' und
                // 'gesichert'. Alphabetisch sortiert stuende 'gesichert' vor
                // 'Verdacht' vor 'wahrscheinlich'. Eine Spalte, die nach
                // BEWEISSTAERKE aussieht und alphabetisch sortiert, waere in
                // einem Beweismittelwerkzeug irrefuehrend. Sortiert wird
                // deshalb ueber den Rang (10/20/30), der sich mit der
                // Ordinalkarte des Repos und dem DDL-CHECK aus M018 deckt.
                sorter: function (a, b, aRow, bRow) {
                    return aRow.getData().konfidenz_rang
                        - bRow.getData().konfidenz_rang;
                },
                formatter: function (cell) {
                    var d = cell.getData();
                    var badge = doc.createElement('span');
                    badge.className = 'aiw-badge aiw-conf-badge '
                        + confidenceClass(d.confidence_code);
                    badge.textContent = d.konfidenz;
                    return badge;
                }
            },
            { title: 'Basis', field: 'basis', widthGrow: 2 },
            {
                title: 'geändert', field: 'geaendert', width: 170,
                // Sortiert wird ueber den ROHWERT. Eine Textsortierung ueber
                // '26.07.2026' waere keine Zeitsortierung.
                sorter: function (a, b, aRow, bRow) {
                    return (aRow.getData().updated_at || 0)
                        - (bRow.getData().updated_at || 0);
                }
            },
            {
                title: '', field: 'aktion', width: 130, headerSort: false,
                hozAlign: 'center',
                kein_filter: true,   // ein Filter auf Knoepfen waere sinnlos
                formatter: function (cell) {
                    var d = cell.getData();
                    if (!canEdit) {
                        var dash = doc.createElement('span');
                        dash.textContent = EM_DASH;
                        dash.title = 'Zum Pflegen fehlt das Recht '
                            + '„crossref.edit“.';
                        return dash;
                    }
                    var b = doc.createElement('button');
                    b.type = 'button';
                    b.className = 'aiw-btn aiw-xref-btn aiw-xref-revise';
                    b.setAttribute('data-subject', String(d.subject_id));
                    b.textContent = 'Revidieren';
                    b.setAttribute('aria-label',
                        'Zuordnung für subject_id ' + d.subject_id
                        + ' revidieren');
                    var TK = _tk();
                    if (TK && TK.hilfeAnker) {
                        TK.hilfeAnker(b, SICHT + '.bedienung.revidieren');
                    }
                    b.addEventListener('click', function (ev) {
                        if (ev && typeof ev.stopPropagation === 'function') {
                            ev.stopPropagation();
                        }
                        _fillForm(doc, d._eintrag);
                    });
                    return b;
                }
            }
        ];
    }

    // _form: Anlage/Revision. Ein Formular fuer beides — je subject_id genau ein
    // Eintrag (der Server macht upsert). Die Felder sind ueber data-Attribute
    // adressierbar, damit eine Zeilen-Aktion sie vorbefuellen kann.
    function _form(doc, setResult, opts) {
        var box = doc.createElement('div');
        box.className = 'aiw-xref-form';

        var inSid = _field(doc, box, 'subject_id (Forenkonto): ',
            'aiw-xref-sid', 'text');
        var inReal = _field(doc, box, 'reale Person: ',
            'aiw-xref-real', 'text');

        // Konfidenz-Auswahl
        var lblC = doc.createElement('label');
        lblC.className = 'aiw-xref-lbl';
        lblC.textContent = 'Konfidenz: ';
        var selC = doc.createElement('select');
        selC.id = 'aiw-xref-conf';
        selC.className = 'aiw-xref-input';
        CONFIDENCE.forEach(function (c) {
            var o = doc.createElement('option');
            o.value = c;
            o.textContent = confidenceLabel(c);
            selC.appendChild(o);
        });
        lblC.appendChild(selC);
        box.appendChild(lblC);

        var inBasis = _field(doc, box, 'Basis (Fundgrundlage): ',
            'aiw-xref-basis', 'text');
        var inNote = _field(doc, box, 'Notiz (optional): ',
            'aiw-xref-note', 'text');

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-xref-save';
        btn.className = 'aiw-btn aiw-xref-btn';
        btn.textContent = 'Zuordnung speichern';
        btn.addEventListener('click', function () {
            var body = buildPayload({
                subject_id: inSid.value,
                real_identity: inReal.value,
                confidence_code: selC.value,
                basis: inBasis.value,
                note: inNote.value
            });
            // Frontend-Vorpruefung (der Server bleibt verbindlich): subject_id
            // ganzzahlig, reale Person nicht leer.
            if (body.subject_id == null) {
                setResult('subject_id fehlt oder ist keine ganze Zahl.', true);
                return;
            }
            if (!body.real_identity) {
                setResult('Die reale Person darf nicht leer sein.', true);
                return;
            }
            setResult('Speichere Zuordnung …', null);
            if (typeof opts.onSet === 'function') {
                opts.onSet(body);
            } else {
                setResult('Kein Schreibpfad verdrahtet.', true);
            }
        });
        box.appendChild(btn);
        return box;
    }

    // _field: beschriftetes Textfeld; gibt das <input> zurueck.
    function _field(doc, parent, labelText, id, type) {
        var lbl = doc.createElement('label');
        lbl.className = 'aiw-xref-lbl';
        lbl.textContent = labelText;
        var inp = doc.createElement('input');
        inp.type = type || 'text';
        inp.id = id;
        inp.className = 'aiw-xref-input';
        lbl.appendChild(inp);
        parent.appendChild(lbl);
        return inp;
    }

    // _fillForm: uebertraegt eine Zeile ins Formular (Revision vorbereiten).
    // Greift auf die per id adressierbaren Felder zu; tut nichts, wenn das
    // Formular fehlt (nur-lesend).
    function _fillForm(doc, e) {
        var sid = doc.getElementById('aiw-xref-sid');
        var real = doc.getElementById('aiw-xref-real');
        var conf = doc.getElementById('aiw-xref-conf');
        var basis = doc.getElementById('aiw-xref-basis');
        var note = doc.getElementById('aiw-xref-note');
        if (!sid || !real || !conf) { return; }
        sid.value = String(e.subject_id);
        real.value = e.real_identity || '';
        conf.value = e.confidence_code || 'verdacht';
        if (basis) { basis.value = e.basis || ''; }
        if (note) { note.value = e.note || ''; }
        var res = doc.getElementById('aiw-xref-result');
        if (res) {
            res.textContent = 'Zeile ' + e.subject_id + ' zur Revision '
                + 'uebernommen — Konfidenz/Basis anpassen und speichern.';
            res.classList.remove('error');
            res.classList.add('ok');
        }
    }

    // =========================================================================
    // 2) UMD-Ausgang.
    // =========================================================================
    var API = {
        confidenceLabel: confidenceLabel,
        confidenceClass: confidenceClass,
        entries: entries,
        fmtTs: fmtTs,
        buildPayload: buildPayload,
        renderCrossref: renderCrossref,
        CONFIDENCE: CONFIDENCE,
        // Build 555: reine Abbildung + Spaltendefinition (vitest).
        confidenceRang: confidenceRang,
        toRows: toRows,
        spalten: spalten
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitCrossref = API; }
})();
