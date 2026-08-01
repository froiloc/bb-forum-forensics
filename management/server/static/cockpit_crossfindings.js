// =============================================================================
// management/server/static/cockpit_crossfindings.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Querfunde (AP-2A)
// =============================================================================
// Zweck (Idee 6, Frontend zu Build 474):
//   REIN LESENDE Meta-Uebersicht der Querfunde ("Fund ueber B im Fall A") aus
//   GET /api/crossfindings. Zeigt je Fund: Ziel-Subjekt (subject_id), Quell-
//   Ermittler, Status (offen/integriert), Zeiten. Erfassung + Transport laufen
//   AUTOMATISCH (forensic_api) — hier wird NICHTS geschrieben.
//
// ERWEITERT IN BUILD 508 (Idee 7, Frontend zu 507): der QUERFUND-RUECKKANAL.
//   'integrated_at' belegt nur, dass die TECHNIK den Fund kopiert hat. Ob ein
//   MENSCH ihn gesehen und was daraus geworden ist, zeigt und setzt jetzt
//   diese Sicht (Zustaende offen -> zugestellt -> quittiert -> verwertet bzw.
//   nicht_relevant). Der ANBAU an diese Sicht ist hier richtig (anders als beim
//   Alias-Katalog, Build 505): der Rueckkanal betrifft GENAU DIE ZEILE, die
//   diese Sicht schon zeigt — eine zweite Sicht haette den Fund und seinen
//   Bearbeitungsstand auseinandergerissen.
//
// Datenform GET /api/crossfindings (ManagementApp._crossfindings):
//   { findings: [ {id, subject_id, source_iid, source_name, has_case,
//                  annotation_local_id, db_path, created_at, integrated_at,
//                  status,
//                  // ab Build 508 additiv:
//                  feedback_status, feedback_label, feedback_final,
//                  feedback_reason, decided_by, decided_name, decided_at,
//                  allowed_next: [{code,label,reason_required,reason_meaning}]
//                 }, ... ],
//     counts: { total, offen, integriert },            // TRANSPORT (Build 474)
//     feedback_counts: { offen, zugestellt, quittiert, // RUECKKANAL (Build 507)
//                        verwertet, nicht_relevant, gesamt } }
//   Bei fehlendem Substrat liefert der Endpunkt 503; loadCrossfindings reicht
//   das als {error: <text>} an renderCrossfindings weiter.
//
// SCHREIBEN (nur mit crossref.edit):
//   onDecide({finding_id, status_code, reason}) -> POST /api/crossfindings/decide
//   Die zulaessigen Folgezustaende kommen VOM SERVER (allowed_next je Zeile) —
//   das Frontend erfindet KEINE Uebergaenge. Verlangt ein Zustand einen
//   Pflichttext (Basis bei 'verwertet', Grund bei 'nicht_relevant'), erscheint
//   das Feld und der Absende-Knopf prueft es, BEVOR er den Server behelligt.
//   KEIN optimistisches UI: nach der Entscheidung laedt cockpit.js neu.
//
// GRUNDREGEL 1 (kein stiller Leerbefund): Ein 503/Fehler zeigt „Uebersicht
//   derzeit nicht verfuegbar" — NICHT eine leere Liste, die faelschlich „keine
//   Querfunde" suggerierte. Ein echter Leerbefund (Substrat da, 0 Funde) zeigt
//   dagegen bewusst „Keine Querfunde".
//
// KEIN SSE-REFRESH (bewusst): Querfunde entstehen ueber die automatische
//   forensic_api-Pipeline (pending_cross_annotations), NICHT ueber den
//   coordinator-audit_log. Der SSE-Strom triggert auf Audit-Ereignisse und
//   wuerde fuer neue Querfunde nicht feuern — ein SSE-Refresh waere irrefuehrend.
//   Deshalb ein expliziter „Aktualisieren"-Knopf.
//
// KAPSELUNG / GEBOTE: IIFE + 'use strict'; DEV-Logging; ausfuehrliche
//   Kommentare; reine Helfer ohne DOM (vitest); UMD-Export. XSS: textContent.
//
// Build 634 (Vorgang 17200856, Welle B2): HILFE-MARKEN fuer die zwei weitere
//   Bedienelemente dieser Sicht - damit tragen alle eine. Die Texte
//   stehen in management/help/inhalt/identitaeten.py. Die Eingabezeilen
//   stammen aus der Fabrik '_field'; ihre Marken sitzen deshalb an den
//   ABNAHMESTELLEN und nicht in der Fabrik - eine Fabrik kann nur EINE
//   Kennung setzen, und die Felder meinen Verschiedenes (Fabrikregel,
//   tests/_bedienelemente.py, Build 633).
// Version: v0.8.634 · Build: 634 · 2026-08-01
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
        args.unshift('[AIW-Querfunde]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';

    // ------------------------------------------------------------------ Helfer
    // (rein — kein DOM, damit unter vitest direkt pruefbar)

    function statusLabel(code) {
        if (code === 'integriert') { return 'integriert'; }
        if (code === 'offen') { return 'offen'; }
        return String(code == null ? '' : code);
    }
    function statusClass(code) {
        if (code === 'integriert') { return 'aiw-cf-integriert'; }
        if (code === 'offen') { return 'aiw-cf-offen'; }
        return 'aiw-cf-unbekannt';
    }

    // findings: robuste Extraktion der Listenform.
    function findings(data) {
        return (data && Array.isArray(data.findings)) ? data.findings : [];
    }

    // ---------------------------------------------------- Rueckkanal (508)
    // Reihenfolge = Handlungsbedarf (deckungsgleich mit STATUS_ORDER in
    // crossfinding_channel_status.py). Wird NUR fuer Beschriftung/Klassen
    // benutzt — welche Uebergaenge erlaubt sind, sagt allein der Server.
    var FEEDBACK_LABEL = {
        offen: 'offen',
        zugestellt: 'zugestellt',
        quittiert: 'quittiert',
        verwertet: 'verwertet',
        nicht_relevant: 'nicht relevant'
    };

    // feedbackLabel: Anzeigetext des Rueckkanal-Zustands. Der Server schickt
    // 'feedback_label' mit; diese Funktion ist der Rueckfall (und die reine,
    // testbare Form).
    function feedbackLabel(code) {
        return FEEDBACK_LABEL[code] || String(code == null ? '' : code);
    }

    // feedbackClass: CSS-Suffix. 'offen' wird ABSICHTLICH hervorgehoben — das
    // ist der handlungsbeduerftige Fall, und ihn zu uebersehen ist genau der
    // Fehler, den dieser Rueckkanal verhindern soll.
    function feedbackClass(code) {
        if (code === 'verwertet') { return 'aiw-cff-verwertet'; }
        if (code === 'nicht_relevant') { return 'aiw-cff-nichtrelevant'; }
        if (code === 'quittiert') { return 'aiw-cff-quittiert'; }
        if (code === 'zugestellt') { return 'aiw-cff-zugestellt'; }
        if (code === 'offen') { return 'aiw-cff-offen'; }
        return 'aiw-cff-unbekannt';
    }

    // allowedNext: die vom SERVER gelieferten Folgezustaende einer Zeile.
    // Fehlt das Feld (alter Server), ist die Liste leer -> die Sicht bietet
    // KEINE Aktion an, statt einen Uebergang zu raten.
    function allowedNext(f) {
        return (f && Array.isArray(f.allowed_next)) ? f.allowed_next : [];
    }

    // feedbackCountsText: Kopfzeile des Rueckkanals.
    function feedbackCountsText(data) {
        var c = (data && data.feedback_counts) ? data.feedback_counts : null;
        if (!c) { return ''; }
        return 'Rückkanal — offen: ' + (c.offen || 0)
            + '  ·  zugestellt: ' + (c.zugestellt || 0)
            + '  ·  quittiert: ' + (c.quittiert || 0)
            + '  ·  verwertet: ' + (c.verwertet || 0)
            + '  ·  nicht relevant: ' + (c.nicht_relevant || 0);
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

    // =========================================================================
    // DOM: Sicht rendern. data = {findings, counts} ODER {error: <text>}.
    // =========================================================================
    function renderCrossfindings(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return; }
        data = data || {};
        var onlyOpen = opts.onlyOpen === true;
        var canEdit = opts.canEdit === true;

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Querfunde — fallübergreifende Funde';
        // Build 604 (Baustelle H / H13): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'crossfindings.titel');
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Funde über ein anderes Subjekt (B), die bei der '
            + 'Ermittlung im Fall A entstanden sind. Erfassung und Transport '
            + 'laufen automatisch — diese Sicht ist rein lesend.';
        sub.setAttribute('data-hilfe-id', 'crossfindings.kennzeile');
        mainEl.appendChild(sub);

        // --- Steuerleiste: zwei Filter + Aktualisieren -----------------------
        mainEl.appendChild(_controls(doc, onlyOpen, opts));

        // --- Fehler-/Nichtverfuegbar-Zustand (Grundregel 1) ------------------
        if (data.error) {
            var err = doc.createElement('div');
            err.className = 'aiw-cf-result error';
            err.textContent = 'Übersicht derzeit nicht verfügbar: '
                + data.error;
            mainEl.appendChild(err);
            log('renderCrossfindings: Fehlerzustand', data.error);
            return;
        }

        // --- counts-Kopf -----------------------------------------------------
        var counts = data.counts
            || { total: 0, offen: 0, integriert: 0 };
        var head = doc.createElement('div');
        head.className = 'aiw-cf-counts';
        head.textContent = 'Transport — offen: ' + (counts.offen || 0)
            + '  ·  integriert: ' + (counts.integriert || 0)
            + '  ·  gesamt: ' + (counts.total || 0);
        head.setAttribute('data-hilfe-id', 'crossfindings.zahlen_transport');
        mainEl.appendChild(head);

        // Rueckkanal-Kopfzeile (Build 508). Nur, wenn der Server sie liefert —
        // gegen einen aelteren Server bleibt die Sicht so unveraendert
        // bedienbar, statt eine Zeile aus Nullen zu erfinden.
        var fbText = feedbackCountsText(data);
        if (fbText) {
            var fbHead = doc.createElement('div');
            fbHead.className = 'aiw-cf-counts aiw-cff-counts';
            fbHead.textContent = fbText;
            fbHead.setAttribute('data-hilfe-id',
                                'crossfindings.zahlen_rueckkanal');
            mainEl.appendChild(fbHead);
        }

        // Ergebniszeile der Rueckkanal-Aktionen.
        var result = doc.createElement('div');
        result.className = 'aiw-cf-result';
        result.id = 'aiw-cff-result';
        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }
        mainEl.appendChild(result);

        // --- Tabelle / echter Leerbefund -------------------------------------
        var rows = findings(data);
        if (rows.length === 0) {
            var empty = doc.createElement('p');
            empty.className = 'aiw-placeholder';
            empty.textContent = onlyOpen
                ? 'Keine offenen Querfunde.'
                : 'Keine Querfunde.';
            mainEl.appendChild(empty);
            log('renderCrossfindings: 0 Funde (onlyOpen', onlyOpen, ')');
            return;
        }

        var table = doc.createElement('table');
        table.className = 'aiw-cf-table';
        var thead = doc.createElement('thead');
        var htr = doc.createElement('tr');
        ['subject_id', 'Quell-Ermittler', 'Transport', 'Rückkanal',
         'angelegt', 'integriert', '']
            .forEach(function (label) {
                var th = doc.createElement('th');
                th.textContent = label;
                htr.appendChild(th);
            });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = doc.createElement('tbody');
        rows.forEach(function (f) {
            tbody.appendChild(_rowEl(doc, f, canEdit, setResult, opts));
        });
        table.appendChild(tbody);
        mainEl.appendChild(table);

        log('renderCrossfindings:', rows.length, 'Funde (onlyOpen', onlyOpen,
            ')');
    }

    // _controls: ZWEI Filter + Aktualisieren.
    //
    // Die beiden Filter meinen bewusst VERSCHIEDENES und sind deshalb
    // ausfuehrlich beschriftet — eine Verwechslung waere folgenschwer:
    //   „nur offene (Transport)"  -> die Technik hat den Fund noch nicht
    //                                kopiert. Loest sich von selbst.
    //   „nur unquittierte (Rückkanal)" -> noch KEIN Mensch hat den Fund
    //                                bestaetigt. Das ist die Arbeit.
    // Beide loesen opts.onReload(onlyOpen, onlyUnack) aus (cockpit.js laedt
    // neu). Der Aktualisieren-Knopf bleibt (kein SSE, s. Kopfkommentar).
    function _controls(doc, onlyOpen, opts) {
        var onlyUnack = opts.onlyUnacknowledged === true;
        var bar = doc.createElement('div');
        bar.className = 'aiw-cf-controls';

        function fire(nextOpen, nextUnack) {
            if (typeof opts.onReload === 'function') {
                opts.onReload(nextOpen === true, nextUnack === true);
            }
        }

        var lbl = doc.createElement('label');
        lbl.className = 'aiw-cf-lbl';
        var cb = doc.createElement('input');
        cb.type = 'checkbox';
        cb.id = 'aiw-cf-onlyopen';
        cb.setAttribute('data-hilfe-id', 'crossfindings.bedienung.nur_offen');
        cb.checked = onlyOpen;
        cb.addEventListener('change', function () {
            fire(cb.checked === true, onlyUnack);
        });
        lbl.appendChild(cb);
        lbl.appendChild(doc.createTextNode(' nur offene (Transport)'));
        bar.appendChild(lbl);

        var lbl2 = doc.createElement('label');
        lbl2.className = 'aiw-cf-lbl';
        var cb2 = doc.createElement('input');
        cb2.type = 'checkbox';
        cb2.id = 'aiw-cf-onlyunack';
        cb2.setAttribute('data-hilfe-id',
                         'crossfindings.bedienung.nur_unquittiert');
        cb2.checked = onlyUnack;
        cb2.addEventListener('change', function () {
            fire(onlyOpen, cb2.checked === true);
        });
        lbl2.appendChild(cb2);
        lbl2.appendChild(doc.createTextNode(' nur unquittierte (Rückkanal)'));
        bar.appendChild(lbl2);

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-cf-refresh';
        btn.setAttribute('data-hilfe-id',
                         'crossfindings.bedienung.aktualisieren');
        btn.className = 'aiw-btn aiw-cf-btn';
        btn.textContent = 'Aktualisieren';
        btn.addEventListener('click', function () {
            fire(onlyOpen, onlyUnack);
        });
        bar.appendChild(btn);
        return bar;
    }

    // _rowEl: eine Querfund-Zeile. Ab Build 508 mit Rueckkanal-Spalte und —
    // bei crossref.edit — der Entscheidungs-Aktion.
    function _rowEl(doc, f, canEdit, setResult, opts) {
        var tr = doc.createElement('tr');
        tr.setAttribute('data-subject', String(f.subject_id));
        tr.setAttribute('data-finding-id', String(f.id));
        tr.className = feedbackClass(f.feedback_status || 'offen');

        var tdSid = doc.createElement('td');
        tdSid.textContent = String(f.subject_id);
        tr.appendChild(tdSid);

        var tdSrc = doc.createElement('td');
        // source_name kann null sein (Ermittler nicht zuordenbar) — dann die
        // rohe iid zeigen, damit die Zeile nicht bedeutungslos wird
        // (Grundregel 1: sichtbar bleiben statt verschlucken).
        tdSrc.textContent = f.source_name
            || ('iid ' + (f.source_iid == null ? EM_DASH : f.source_iid));
        tr.appendChild(tdSrc);

        var tdStatus = doc.createElement('td');
        var badge = doc.createElement('span');
        badge.className = 'aiw-badge aiw-cf-badge ' + statusClass(f.status);
        badge.textContent = statusLabel(f.status);
        tdStatus.appendChild(badge);
        tr.appendChild(tdStatus);

        // --- Rueckkanal-Spalte (Build 508) -------------------------------
        var tdFb = doc.createElement('td');
        var fbBadge = doc.createElement('span');
        fbBadge.className = 'aiw-badge aiw-cff-badge '
            + feedbackClass(f.feedback_status || 'offen');
        // Der Server schickt das Label mit; feedbackLabel ist der Rueckfall.
        fbBadge.textContent = f.feedback_label
            || feedbackLabel(f.feedback_status || 'offen');
        tdFb.appendChild(fbBadge);
        // Wer hat entschieden — und mit welcher Begruendung? Beides gehoert
        // sichtbar in die Zeile: die Entscheidung IST das Ermittlungsergebnis.
        if (f.decided_name || f.feedback_reason) {
            var meta = doc.createElement('div');
            meta.className = 'aiw-cff-meta';
            var teile = [];
            if (f.decided_name) { teile.push(f.decided_name); }
            if (f.decided_at) { teile.push(fmtTs(f.decided_at)); }
            meta.textContent = teile.join(' · ');
            tdFb.appendChild(meta);
            if (f.feedback_reason) {
                var rs = doc.createElement('div');
                rs.className = 'aiw-cff-reason';
                // XSS: Freitext der Ermittlerin — immer textContent.
                rs.textContent = f.feedback_reason;
                tdFb.appendChild(rs);
            }
        }
        tr.appendChild(tdFb);

        var tdCreated2 = doc.createElement('td');
        tdCreated2.textContent = fmtTs(f.created_at);
        tr.appendChild(tdCreated2);

        var tdInteg = doc.createElement('td');
        tdInteg.textContent = (f.integrated_at != null)
            ? fmtTs(f.integrated_at) : EM_DASH;
        tr.appendChild(tdInteg);

        // --- Aktionsspalte -----------------------------------------------
        var tdAct = doc.createElement('td');
        tdAct.className = 'aiw-cff-actions';
        var next = allowedNext(f);
        if (!canEdit) {
            tdAct.textContent = EM_DASH;
        } else if (next.length === 0) {
            // Endzustand (oder alter Server ohne allowed_next): KEINE Aktion.
            // Lieber gar nichts anbieten als einen Uebergang raten.
            tdAct.textContent = f.feedback_final ? 'abgeschlossen' : EM_DASH;
        } else {
            tdAct.appendChild(_decideBtn(doc, f, next, setResult, opts));
        }
        tr.appendChild(tdAct);

        return tr;
    }

    // _decideBtn: oeffnet die Entscheidungszeile. Bewusst INLINE (kein Modal),
    // damit der Kontext der Nachbarfunde sichtbar bleibt.
    function _decideBtn(doc, f, next, setResult, opts) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'aiw-btn aiw-cf-btn aiw-cff-decide';
        b.setAttribute('data-finding-id', String(f.id));
        b.textContent = 'Bewerten';
        b.setAttribute('data-hilfe-id', 'crossfindings.bedienung.bewerten');
        b.addEventListener('click', function () {
            var row = b.parentNode && b.parentNode.parentNode;
            if (!row || row.getAttribute('data-deciding') === '1') { return; }
            row.setAttribute('data-deciding', '1');
            row.parentNode.insertBefore(
                _decideRow(doc, f, next, setResult, opts), row.nextSibling);
        });
        return b;
    }

    // _decideRow: Auswahl NUR aus den vom Server gelieferten Folgezustaenden.
    // Das Grund-/Basis-Feld erscheint genau dann, wenn der GEWAEHLTE Zustand
    // es verlangt — und die Beschriftung sagt, was gemeint ist (Basis vs.
    // Grund). Der Absende-Knopf prueft die Pflichtangabe, BEVOR er den Server
    // behelligt; verbindlich prueft ohnehin die Zustandsmaschine im Server.
    function _decideRow(doc, f, next, setResult, opts) {
        var host = doc.createElement('tr');
        host.className = 'aiw-cff-decidrow';
        var td = doc.createElement('td');
        td.setAttribute('colspan', '7');

        var sel = doc.createElement('select');
        sel.className = 'aiw-cf-input aiw-cff-target';
        // Build 634 (Vorgang 17200856): Hilfe-Marke, LITERAL gesetzt.
        // Text in management/help/inhalt/identitaeten.py.
        sel.setAttribute('data-hilfe-id', 'crossfindings.bedienung.folgezustand');
        next.forEach(function (n) {
            var o = doc.createElement('option');
            o.value = n.code;
            o.textContent = n.label || feedbackLabel(n.code);
            sel.appendChild(o);
        });

        var lblReason = doc.createElement('label');
        lblReason.className = 'aiw-cf-lbl aiw-cff-reasonlbl';
        var reasonText = doc.createElement('span');
        lblReason.appendChild(reasonText);
        var inR = doc.createElement('input');
        inR.type = 'text';
        inR.className = 'aiw-cf-input aiw-cff-reasoninput';
        inR.setAttribute('data-hilfe-id', 'crossfindings.bedienung.begruendung');
        lblReason.appendChild(inR);

        function currentSpec() {
            for (var i = 0; i < next.length; i++) {
                if (next[i].code === sel.value) { return next[i]; }
            }
            return null;
        }
        // syncReason: blendet das Pflichtfeld zustandsabhaengig ein/aus.
        function syncReason() {
            var spec = currentSpec();
            var noetig = !!(spec && spec.reason_required);
            lblReason.style.display = noetig ? '' : 'none';
            reasonText.textContent = noetig
                ? ((spec.reason_meaning || 'Begründung') + ': ')
                : '';
        }
        sel.addEventListener('change', syncReason);
        syncReason();

        var go = doc.createElement('button');
        go.type = 'button';
        go.className = 'aiw-btn aiw-cf-btn aiw-cff-decide-go';
        go.textContent = 'Entscheidung belegen';
        go.setAttribute('data-hilfe-id',
                        'crossfindings.bedienung.entscheidung_belegen');
        go.addEventListener('click', function () {
            var spec = currentSpec();
            var reason = String(inR.value || '').trim();
            if (spec && spec.reason_required && !reason) {
                setResult('Pflichtangabe fehlt: '
                    + (spec.reason_meaning || 'Begründung')
                    + '. Ohne sie wird nichts geschrieben.', true);
                return;
            }
            setResult('Schreibe Entscheidung …', null);
            if (typeof opts.onDecide === 'function') {
                opts.onDecide({
                    finding_id: f.id,
                    status_code: sel.value,
                    reason: reason
                });
            } else {
                setResult('Kein Schreibpfad verdrahtet.', true);
            }
        });

        td.appendChild(doc.createTextNode('Neuer Stand: '));
        td.appendChild(sel);
        td.appendChild(lblReason);
        td.appendChild(go);
        host.appendChild(td);
        return host;
    }

    // =========================================================================
    // UMD-Ausgang.
    // =========================================================================
    var API = {
        statusLabel: statusLabel,
        statusClass: statusClass,
        findings: findings,
        fmtTs: fmtTs,
        renderCrossfindings: renderCrossfindings,
        // Build 508 (Rueckkanal)
        feedbackLabel: feedbackLabel,
        feedbackClass: feedbackClass,
        allowedNext: allowedNext,
        feedbackCountsText: feedbackCountsText
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitCrossfindings = API; }
})();
