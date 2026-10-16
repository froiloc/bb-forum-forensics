// =============================================================================
// management/server/static/cockpit_dbvorfaelle.js
// IT-Forensisches Ermittlungswerkzeug — Cockpit: Register Datenbank-Vorfaelle
// =============================================================================
// Zweck (Build 777):
//   Rendert die Sicht "Datenbank-Vorfaelle" (/api/db_vorfaelle). Ein Vorfall
//   ist ein Befund an einer Datenbank, den der Webserver selbst festgestellt
//   hat — ab Build 778 die Startpruefung der evidence_<uid>.db: beschaedigt,
//   gesichert, repariert und ausgetauscht, oder der Start wurde verweigert.
//   Festlegung Alex 14.10.2026: der Webserver repariert selbst, damit die
//   Ermittler arbeiten koennen; die Leitung liest den Vorfall HIER spaeter.
//
// Datenform GET /api/db_vorfaelle (ManagementApp._db_vorfaelle, Build 777):
//   {
//     status_filter: 'alle'|'offen'|'geprueft',
//     zaehler: { offen, geprueft },
//     vorfaelle: [ {id, vorfall_uid, erkannt_at, erfasst_at, nachgetragen,
//                   art, art_klartext, ergebnis, ergebnis_klartext,
//                   subject_id, datei, host, person_id, person_name,
//                   befund, befund_fehler, befund_roh?, status, audit_seq,
//                   geprueft_von, geprueft_von_name, geprueft_at,
//                   pruef_notiz, pruef_audit_seq}, ... ],
//     puffer: { verzeichnis, anzahl, eintraege: [...], fehler },
//     kann_pruefen: bool,
//     arten: {...}, ergebnisse: {...}
//   }
//
// SCHREIBEN: opts.onPruefen({id, notiz}) -> cockpit.js sendet
//   POST /api/db_vorfaelle/pruefen und laedt die Sicht NEU (kein
//   optimistisches UI, Grundregel 1). opts.onFilter(status) laedt mit Filter.
//
// DER PUFFER WIRD IMMER GEZEIGT. Vorfaelle, die beim Erkennen nicht ins
//   Register konnten (coordinator.db nicht erreichbar), liegen bis zum
//   naechsten Start eines Falls im Pufferordner. Ohne diese Anzeige waeren sie
//   bis dahin unsichtbar — die Sicht saehe vollstaendig aus und waere es nicht.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE-Wrapper mit 'use strict'.
//   2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG), zur Laufzeit umschaltbar.
//   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
//   4) Reine Funktionen fassen NIE das DOM an -> vitest testet den ECHTEN Code
//      (UMD-Ausgang). Der DOM-Teil ist ueber opts.doc injizierbar.
//
// SICHERHEIT (XSS): ALLE variablen Texte (Pfade, Notizen, Befund) via
//   textContent, nie via innerHTML.
//
// Version: v0.8.777 · Build: 777 · 2026-10-14
//   Build 778: Ergebnis 'journal_zurueckgerollt' gelb.
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
        args.unshift('[AIW-DbVorfaelle]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';
    var SICHT = 'dbvorfaelle';   // Praefix der Hilfe-Anker

    //: Filterwerte (== GET-Parameter 'status') mit Beschriftung.
    var FILTER = [
        { wert: 'alle', label: 'alle' },
        { wert: 'offen', label: 'offen' },
        { wert: 'geprueft', label: 'geprüft' }
    ];

    var STATUS_LABEL = { offen: 'offen', geprueft: 'geprüft' };

    // ------------------------------------------------------------------ Helfer
    // fmtTs: Epoch -> 'YYYY-MM-DD HH:MM:SS UTC' (deterministisch wie im
    // Audit-Explorer, cockpit_audit.js). Leer -> Gedankenstrich.
    function fmtTs(ts) {
        if (ts === null || ts === undefined || ts === '') { return EM_DASH; }
        var n = parseInt(ts, 10);
        if (isNaN(n)) { return String(ts); }
        return new Date(n * 1000).toISOString().replace('T', ' ')
            .replace(/\..+Z$/, ' UTC');
    }

    // ergebnisStufe: Ampelfarbe des Ergebnisses.
    //   rot  = Start verweigert ODER nicht freigegeben (Handlungsbedarf),
    //   gelb = repariert und freigegeben (es WAR ein Schaden), sowie (Build
    //          778) ein zurueckgerollter, unterbrochener Schreibvorgang,
    //   grau = unbekanntes Ergebnis (verschwindet nicht, wird nur nicht
    //          eingefaerbt — Grundregel 1).
    function ergebnisStufe(ergebnis) {
        if (ergebnis === 'repariert_freigegeben'
            || ergebnis === 'journal_zurueckgerollt') { return 'gelb'; }
        if (ergebnis === 'repariert_nicht_freigegeben'
            || ergebnis === 'start_verweigert') { return 'rot'; }
        return 'grau';
    }

    function statusLabel(status) {
        return STATUS_LABEL[status] || String(status || EM_DASH);
    }

    // zaehlerModell: zwei Zaehler, fehlende Schluessel -> 0.
    function zaehlerModell(data) {
        var z = (data && data.zaehler) || {};
        return [
            { status: 'offen', label: 'offen',
              anzahl: typeof z.offen === 'number' ? z.offen : 0 },
            { status: 'geprueft', label: 'geprüft',
              anzahl: typeof z.geprueft === 'number' ? z.geprueft : 0 }
        ];
    }

    // pufferModell: Aussage ueber den Puffer — EINE Zeile Text, eine Stufe und
    // die Liste der wartenden Dateien. Drei Faelle:
    //   fehler      -> rot,  'Puffer nicht lesbar: ...'
    //   anzahl > 0  -> rot,  'N Vorfall/Vorfaelle noch nicht im Register'
    //   sonst       -> gruen, 'Puffer leer'
    function pufferModell(data) {
        var p = (data && data.puffer) || {};
        if (p.fehler) {
            return { stufe: 'rot', text: 'Puffer nicht lesbar: ' + p.fehler
                + ' — ob Vorfälle auf ihren Nachtrag warten, ist unbekannt.',
                     eintraege: [] };
        }
        var n = typeof p.anzahl === 'number' ? p.anzahl : 0;
        var eintraege = Array.isArray(p.eintraege) ? p.eintraege : [];
        if (n > 0) {
            return { stufe: 'rot',
                     text: n + (n === 1 ? ' Vorfall wartet' : ' Vorfälle warten')
                        + ' auf den Nachtrag ins Register (Puffer '
                        + (p.verzeichnis || EM_DASH) + '). Nachgetragen wird '
                        + 'beim nächsten Start eines Falls.',
                     eintraege: eintraege };
        }
        return { stufe: 'gruen', text: 'Puffer leer — kein Vorfall wartet auf '
            + 'seinen Nachtrag.', eintraege: [] };
    }

    function vorfallZeilen(data) {
        return (data && Array.isArray(data.vorfaelle)) ? data.vorfaelle : [];
    }

    // toRows: Vorfaelle -> Tabellenzeilen. REIN (kein DOM). Leere Felder ->
    // Gedankenstrich (eine leere Zelle saehe wie ein Anzeigefehler aus).
    function toRows(data) {
        return vorfallZeilen(data).map(function (v) {
            return {
                id: v.id,
                erkannt: fmtTs(v.erkannt_at) + (v.nachgetragen ? ' (nachgetragen)' : ''),
                subject_id: (v.subject_id === null || v.subject_id === undefined)
                    ? EM_DASH : v.subject_id,
                ergebnis: v.ergebnis_klartext || v.ergebnis || EM_DASH,
                stufe: ergebnisStufe(v.ergebnis),
                datei: v.datei || EM_DASH,
                rechner: v.host || EM_DASH,
                person: v.person_name
                    || (v.person_id !== null && v.person_id !== undefined
                        ? ('Person ' + v.person_id) : EM_DASH),
                status: statusLabel(v.status),
                offen: v.status === 'offen',
                _vorfall: v
            };
        });
    }

    // befundText: der Befund als eingerueckter Text fuer die Detailansicht.
    // Ein unlesbarer Befund wird als Rohtext MIT Fehlerangabe gezeigt.
    function befundText(v) {
        if (!v) { return ''; }
        if (v.befund_fehler) {
            return v.befund_fehler + '\n\n' + String(v.befund_roh || '');
        }
        try {
            return JSON.stringify(v.befund, null, 2);
        } catch (e) {
            return String(v.befund);
        }
    }

    // pruefvermerkText: wer, wann, was — oder leer bei offenem Vorfall.
    function pruefvermerkText(v) {
        if (!v || v.status !== 'geprueft') { return ''; }
        return 'Geprüft von ' + (v.geprueft_von_name
            || ('Person ' + v.geprueft_von)) + ' am ' + fmtTs(v.geprueft_at)
            + ' (Beleg #' + v.pruef_audit_seq + '): ' + (v.pruef_notiz || '');
    }

    function _tk() {
        return (typeof window !== 'undefined' && window.AIWTableKit)
            ? window.AIWTableKit : null;
    }
    function _mitHilfe(cols, doc) {
        var TK = _tk();
        if (!TK || !doc || !TK.titelMitHilfe) { return cols; }
        return cols.map(function (c) {
            var neu = {};
            Object.keys(c).forEach(function (k) { neu[k] = c[k]; });
            if (c.field && !c.titleFormatter) {
                neu.titleFormatter = TK.titelMitHilfe(
                    doc, c.title || c.field,
                    SICHT + '.spalte.' + String(c.field).toLowerCase());
            }
            return neu;
        });
    }

    // spalten: Spaltendefinition. 'aktion' traegt je Zeile "Befund" und —
    // nur bei offenem Vorfall und mit Recht — "Als geprüft markieren".
    function spalten(doc, kannPruefen, zeigeBefund, oeffnePruefung) {
        return [
            { title: 'Erkannt', field: 'erkannt', width: 210 },
            { title: 'Fall', field: 'subject_id', width: 110, hozAlign: 'right' },
            {
                title: 'Ergebnis', field: 'ergebnis', widthGrow: 2,
                formatter: function (cell) {
                    var d = cell.getData();
                    var wrap = doc.createElement('span');
                    var dot = doc.createElement('span');
                    dot.className = 'dot ' + d.stufe;
                    wrap.appendChild(dot);
                    var tx = doc.createElement('span');
                    tx.textContent = ' ' + d.ergebnis;
                    wrap.appendChild(tx);
                    return wrap;
                }
            },
            { title: 'Datei', field: 'datei', widthGrow: 2 },
            { title: 'Rechner', field: 'rechner', width: 130 },
            { title: 'Person', field: 'person', width: 160 },
            { title: 'Status', field: 'status', width: 100 },
            {
                title: 'Aktion', field: 'aktion', width: 270,
                headerSort: false,
                kein_filter: true,
                formatter: function (cell) {
                    var d = cell.getData();
                    var box = doc.createElement('span');
                    box.className = 'aiw-dbv-aktionen';
                    var b = doc.createElement('button');
                    b.type = 'button';
                    b.className = 'aiw-btn aiw-dbv-btn';
                    b.setAttribute('data-id', String(d.id));
                    b.setAttribute('data-aktion', 'befund');
                    b.setAttribute('data-hilfe-id', 'dbvorfaelle.bedienung.befund');
                    b.textContent = 'Befund';
                    b.addEventListener('click', function (ev) {
                        if (ev && ev.stopPropagation) { ev.stopPropagation(); }
                        zeigeBefund(d._vorfall);
                    });
                    box.appendChild(b);
                    if (kannPruefen && d.offen) {
                        var p = doc.createElement('button');
                        p.type = 'button';
                        p.className = 'aiw-btn aiw-dbv-btn';
                        p.setAttribute('data-id', String(d.id));
                        p.setAttribute('data-aktion', 'pruefen');
                        p.setAttribute('data-hilfe-id',
                            'dbvorfaelle.bedienung.pruefen');
                        p.textContent = 'Als geprüft markieren';
                        p.addEventListener('click', function (ev) {
                            if (ev && ev.stopPropagation) { ev.stopPropagation(); }
                            oeffnePruefung(d._vorfall);
                        });
                        box.appendChild(p);
                    }
                    return box;
                }
            }
        ];
    }

    // =========================================================================
    // 1) DOM: Sicht rendern.
    // =========================================================================
    function renderDbVorfaelle(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return { setResult: function () {} }; }
        data = data || {};
        var kannPruefen = data.kann_pruefen === true;

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.setAttribute('data-hilfe-id', 'dbvorfaelle.titel');
        h.textContent = 'Datenbank-Vorfälle';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'dbvorfaelle.kennzeile');
        sub.textContent = 'Schäden an Datenbanken, die der Webserver beim '
            + 'Start festgestellt hat — mit Sicherung, Reparatur und '
            + 'Ergebnis. Jeder Eintrag und jeder Prüfvermerk ist im '
            + 'Protokollbuch belegt.';
        mainEl.appendChild(sub);

        // --- Zaehler ---------------------------------------------------------
        var counts = doc.createElement('div');
        counts.className = 'aiw-dbv-zaehler';
        counts.setAttribute('data-hilfe-id', 'dbvorfaelle.zahlen');
        zaehlerModell(data).forEach(function (c) {
            var badge = doc.createElement('span');
            badge.className = 'aiw-badge aiw-dbv-badge';
            badge.setAttribute('data-status', c.status);
            var dot = doc.createElement('span');
            dot.className = 'dot ' + (c.status === 'offen' && c.anzahl > 0
                ? 'rot' : 'gruen');
            badge.appendChild(dot);
            var t = doc.createElement('span');
            t.textContent = ' ' + c.label + ': ' + c.anzahl;
            badge.appendChild(t);
            counts.appendChild(badge);
        });
        mainEl.appendChild(counts);

        // --- Puffer ----------------------------------------------------------
        var pm = pufferModell(data);
        var puffer = doc.createElement('div');
        puffer.className = 'aiw-dbv-puffer ' + pm.stufe;
        puffer.id = 'aiw-dbv-puffer';
        puffer.setAttribute('data-hilfe-id', 'dbvorfaelle.puffer');
        var pt = doc.createElement('div');
        pt.textContent = pm.text;
        puffer.appendChild(pt);
        if (pm.eintraege.length) {
            var ul = doc.createElement('ul');
            pm.eintraege.forEach(function (e) {
                var li = doc.createElement('li');
                li.textContent = e.fehler
                    ? (e.datei + ' — nicht lesbar: ' + e.fehler)
                    : (fmtTs(e.erkannt_at) + ' · Fall '
                       + (e.subject_id === null || e.subject_id === undefined
                          ? EM_DASH : e.subject_id)
                       + ' · ' + (e.ergebnis || EM_DASH) + ' · ' + e.datei);
                ul.appendChild(li);
            });
            puffer.appendChild(ul);
        }
        mainEl.appendChild(puffer);

        // --- Filter ----------------------------------------------------------
        var fl = doc.createElement('label');
        fl.className = 'aiw-dbv-filter';
        fl.textContent = 'Anzeigen: ';
        var sel = doc.createElement('select');
        sel.id = 'aiw-dbv-filter';
        sel.setAttribute('data-hilfe-id', 'dbvorfaelle.bedienung.filter');
        FILTER.forEach(function (f) {
            var o = doc.createElement('option');
            o.value = f.wert;
            o.textContent = f.label;
            if (f.wert === (data.status_filter || 'alle')) { o.selected = true; }
            sel.appendChild(o);
        });
        sel.addEventListener('change', function () {
            if (typeof opts.onFilter === 'function') { opts.onFilter(sel.value); }
        });
        fl.appendChild(sel);
        mainEl.appendChild(fl);

        if (!kannPruefen) {
            var hint = doc.createElement('p');
            hint.className = 'aiw-pagesub aiw-dbv-readonly';
            hint.textContent = 'Nur lesend — zum Markieren als geprüft fehlt '
                + 'das Recht „wartung.durchfuehren“.';
            mainEl.appendChild(hint);
        }

        // --- Rueckmeldezeile -------------------------------------------------
        var result = doc.createElement('div');
        result.className = 'aiw-dbv-result';
        result.id = 'aiw-dbv-result';
        mainEl.appendChild(result);
        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }

        // --- Panel (Befund ODER Pruefung, immer genau eines) -----------------
        var panel = doc.createElement('div');
        panel.className = 'aiw-dbv-panel';
        panel.id = 'aiw-dbv-panel';
        mainEl.appendChild(panel);
        function schliessen() { panel.textContent = ''; }

        function kopf(v, text) {
            var t = doc.createElement('div');
            t.className = 'aiw-dbv-panel-title';
            t.textContent = text + ' ' + EM_DASH + ' Vorfall ' + v.vorfall_uid
                + ' (Beleg #' + v.audit_seq + ')';
            panel.appendChild(t);
        }

        function zeigeBefund(v) {
            schliessen();
            kopf(v, 'Befund');
            var info = doc.createElement('div');
            info.className = 'aiw-dbv-info';
            info.textContent = (v.art_klartext || v.art) + ' · '
                + (v.ergebnis_klartext || v.ergebnis) + ' · eingetragen '
                + fmtTs(v.erfasst_at);
            panel.appendChild(info);
            var vermerk = pruefvermerkText(v);
            if (vermerk) {
                var pv = doc.createElement('div');
                pv.className = 'aiw-dbv-vermerk';
                pv.textContent = vermerk;
                panel.appendChild(pv);
            }
            var pre = doc.createElement('pre');
            pre.className = 'aiw-dbv-befund';
            pre.setAttribute('data-hilfe-id', 'dbvorfaelle.befund');
            pre.textContent = befundText(v);
            panel.appendChild(pre);
            var zu = doc.createElement('button');
            zu.type = 'button';
            zu.className = 'aiw-btn aiw-dbv-btn';
            zu.id = 'aiw-dbv-schliessen';
            zu.setAttribute('data-hilfe-id', 'dbvorfaelle.bedienung.schliessen');
            zu.textContent = 'Schließen';
            zu.addEventListener('click', schliessen);
            panel.appendChild(zu);
            log('zeigeBefund', v.id);
        }

        function oeffnePruefung(v) {
            schliessen();
            kopf(v, 'Als geprüft markieren');
            var lbl = doc.createElement('label');
            lbl.className = 'aiw-dbv-lbl';
            lbl.textContent = 'Notiz (Pflicht — was wurde geprüft?): ';
            var ta = doc.createElement('textarea');
            ta.id = 'aiw-dbv-notiz';
            ta.className = 'aiw-dbv-input';
            ta.rows = 3;
            ta.setAttribute('data-hilfe-id', 'dbvorfaelle.bedienung.notiz');
            lbl.appendChild(ta);
            panel.appendChild(lbl);

            var ok = doc.createElement('button');
            ok.type = 'button';
            ok.id = 'aiw-dbv-bestaetigen';
            ok.className = 'aiw-btn aiw-dbv-btn';
            ok.setAttribute('data-hilfe-id', 'dbvorfaelle.bedienung.bestaetigen');
            ok.textContent = 'Bestätigen';
            ok.addEventListener('click', function () {
                var notiz = (ta.value || '').trim();
                if (!notiz) {
                    setResult('Die Notiz ist Pflicht: sie sagt, was geprüft '
                        + 'wurde. Es wurde nichts geschrieben.', true);
                    return;
                }
                schliessen();
                setResult('Speichere Prüfvermerk …', null);
                if (typeof opts.onPruefen === 'function') {
                    opts.onPruefen({ id: v.id, notiz: notiz });
                } else {
                    setResult('Kein Schreibpfad verdrahtet.', true);
                }
            });
            panel.appendChild(ok);

            var ab = doc.createElement('button');
            ab.type = 'button';
            ab.id = 'aiw-dbv-abbrechen';
            ab.className = 'aiw-btn aiw-dbv-btn';
            ab.setAttribute('data-hilfe-id', 'dbvorfaelle.bedienung.abbrechen');
            ab.textContent = 'Abbrechen';
            ab.addEventListener('click', function () {
                schliessen();
                setResult('Abgebrochen. Es wurde nichts geschrieben.', false);
            });
            panel.appendChild(ab);
            log('oeffnePruefung', v.id);
        }

        // --- Tabelle ---------------------------------------------------------
        var TK = _tk();
        var rows = toRows(data);
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        if (!TK) {
            var none = doc.createElement('p');
            none.className = 'aiw-placeholder';
            none.textContent = 'Gemeinsames Tabellen-Werkzeug nicht geladen — '
                + 'es liegen ' + rows.length + ' Vorfälle vor.';
            mainEl.appendChild(none);
            log('renderDbVorfaelle: kein TableKit');
            return { setResult: setResult, table: null,
                     zeigeBefund: zeigeBefund, oeffnePruefung: oeffnePruefung };
        }
        var auf = TK.tabelleAufbauen(doc, mainEl, {
            sicht: SICHT,
            rows: rows,
            columns: _mitHilfe(spalten(doc, kannPruefen, zeigeBefund,
                                       oeffnePruefung), doc),
            Ctor: Ctor,
            einheit: 'Vorfälle',
            tabulator: {
                index: 'id',
                height: '420px',
                // Kein 'initialSort': der Server liefert neueste Erkennung
                // zuerst; eine Voreinstellung wuerde das ueberschreiben.
                placeholder: (data.status_filter && data.status_filter !== 'alle')
                    ? 'Keine Vorfälle mit diesem Status.'
                    : 'Bisher kein Datenbank-Vorfall im Register.'
            }
        });
        log('renderDbVorfaelle:', rows.length, 'Vorfall/Vorfaelle, pruefen',
            kannPruefen);
        return { setResult: setResult, table: auf.table,
                 zeigeBefund: zeigeBefund, oeffnePruefung: oeffnePruefung };
    }

    // =========================================================================
    // 2) UMD-Ausgang.
    // =========================================================================
    var API = {
        fmtTs: fmtTs,
        ergebnisStufe: ergebnisStufe,
        statusLabel: statusLabel,
        zaehlerModell: zaehlerModell,
        pufferModell: pufferModell,
        toRows: toRows,
        befundText: befundText,
        pruefvermerkText: pruefvermerkText,
        spalten: spalten,
        renderDbVorfaelle: renderDbVorfaelle,
        FILTER: FILTER
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitDbVorfaelle = API; }
})();
