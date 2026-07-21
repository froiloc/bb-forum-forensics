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
// Version: v0.8.471 · Build: 471 · 2026-07-20
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

    // ------------------------------------------------------------------ Helfer
    // (rein — kein DOM, damit unter vitest direkt pruefbar)

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

        // --- Katalog-Tabelle -------------------------------------------------
        var rows = entries(data);
        if (rows.length === 0) {
            var empty = doc.createElement('p');
            empty.className = 'aiw-placeholder';
            empty.textContent = 'Noch keine Zuordnung im Katalog.';
            mainEl.appendChild(empty);
            log('renderCrossref: leerer Katalog, canEdit', canEdit);
            return { setResult: setResult };
        }

        var table = doc.createElement('table');
        table.className = 'aiw-xref-table';
        var thead = doc.createElement('thead');
        var htr = doc.createElement('tr');
        ['subject_id', 'reale Person', 'Konfidenz', 'Basis', 'geaendert', '']
            .forEach(function (label) {
                var th = doc.createElement('th');
                th.textContent = label;
                htr.appendChild(th);
            });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = doc.createElement('tbody');
        rows.forEach(function (e) {
            tbody.appendChild(_rowEl(doc, e, canEdit));
        });
        table.appendChild(tbody);
        mainEl.appendChild(table);

        log('renderCrossref:', rows.length, 'Eintraege, canEdit', canEdit);
        return { setResult: setResult };
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

    // _rowEl: eine Katalogzeile. Bei canEdit ein „Revidieren“-Knopf, der die
    // Formularfelder mit den Werten der Zeile vorbefuellt (Konfidenz reift).
    function _rowEl(doc, e, canEdit) {
        var tr = doc.createElement('tr');
        tr.setAttribute('data-subject', String(e.subject_id));

        var tdSid = doc.createElement('td');
        tdSid.textContent = String(e.subject_id);
        tr.appendChild(tdSid);

        var tdReal = doc.createElement('td');
        tdReal.textContent = e.real_identity || EM_DASH;
        tr.appendChild(tdReal);

        var tdConf = doc.createElement('td');
        var badge = doc.createElement('span');
        badge.className = 'aiw-badge aiw-conf-badge ' + confidenceClass(
            e.confidence_code);
        badge.textContent = confidenceLabel(e.confidence_code);
        tdConf.appendChild(badge);
        tr.appendChild(tdConf);

        var tdBasis = doc.createElement('td');
        tdBasis.textContent = e.basis || EM_DASH;
        tr.appendChild(tdBasis);

        var tdTs = doc.createElement('td');
        tdTs.textContent = fmtTs(e.updated_at);
        tr.appendChild(tdTs);

        var tdAct = doc.createElement('td');
        tdAct.className = 'aiw-xref-actions';
        if (canEdit) {
            var b = doc.createElement('button');
            b.type = 'button';
            b.className = 'aiw-btn aiw-xref-btn aiw-xref-revise';
            b.setAttribute('data-subject', String(e.subject_id));
            b.textContent = 'Revidieren';
            b.addEventListener('click', function () {
                _fillForm(doc, e);
            });
            tdAct.appendChild(b);
        } else {
            tdAct.textContent = EM_DASH;
        }
        tr.appendChild(tdAct);
        return tr;
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
        CONFIDENCE: CONFIDENCE
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitCrossref = API; }
})();
