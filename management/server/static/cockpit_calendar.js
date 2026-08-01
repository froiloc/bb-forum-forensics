// =============================================================================
// management/server/static/cockpit_calendar.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kalender & Wiedervorlage
// =============================================================================
// Zweck:
//   Frontend zur Wiedervorlage externer Vorgaenge (Backend: Build 385) UND zur
//   gemeinsamen Kalender-Leseschicht.
//
//   Zwei Quellen, EINE Sicht:
//     GET /api/calendar?von=&bis=  -> Monatsraster (externe Vorgaenge +
//                                     Abwesenheiten + Feiertage)
//     GET /api/external            -> Faelligkeitsliste + Arbeitsvorrat
//     POST /api/external/create|defer|answer|close   (auditiert)
//
// DIE DREI DINGE, DIE DIESE SICHT LEISTEN MUSS (und warum):
//
//   1) NICHTS DARF DURCHRUTSCHEN. Ein UEBERFAELLIGER Vorgang aus einem
//      frueheren Monat wird NICHT nur im Raster gezeigt (dort waere er beim
//      Blaettern unsichtbar), sondern zusaetzlich in einem eigenen, roten
//      Block "Ueberfaellig — ausserhalb dieses Monats". Genau dieses
//      Versaeumnis soll das System verhindern (Grundregel 1).
//
//   2) DER KALENDER SAGT, WENN ER SCHWEIGT. Die Serverantwort fuehrt in
//      'hinweise', welche Quelle nichts geliefert hat und warum (fehlendes
//      Recht, fehlende Migration). Diese Hinweise werden ANGEZEIGT. Ein leerer
//      Kalender ohne Erklaerung waere gefaehrlicher als gar keiner: der
//      Ermittler schlósse aus der Leere, es stuende nichts an.
//
//   3) DIE RECHENGRUNDLAGE STEHT DABEI. 'stichtag_text' ("Faelligkeiten
//      berechnet zum ..., Zeitzone ...") wird sichtbar ausgegeben. Eine falsche
//      VM-Uhr faellt so einem Menschen auf, statt still zu wirken.
//
// SCHREIBEN:
//   - Jeder Schreibvorgang ist ZWEISTUFIG (Knopf -> Bestaetigung -> Ausfuehren).
//   - VERSCHIEBEN verlangt einen GRUND; ohne Grund bleibt der Knopf gesperrt.
//     Die Oberflaeche bietet damit keine Aktion an, die der Server zwingend
//     mit 400 abweisen wuerde.
//   - ABSCHLIESSEN ist UNWIDERRUFLICH — der Bestaetigungstext sagt das im
//     Klartext.
//   - KEIN optimistisches UI: nach dem POST wird neu geladen.
//
// KAPSELUNG/GEBOTE: IIFE + 'use strict'; DEV-Logging (window.AIW_COCKPIT_DEBUG);
//   reine Funktionen (Datums-/Raster-/Anfrage-Logik) beruehren NIE das DOM und
//   werden von vitest gegen den ECHTEN Code geprueft (UMD-Ausgang).
//   XSS: ausschliesslich textContent.
//
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Build 636 (Vorgang 17200856, Welle B4): HILFE-MARKEN fuer die
//   zwanzig Bedienelemente dieser Sicht.
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
        args.unshift('[AIW-Kalender]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var WEEKDAYS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
    var MONTHS = ['Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
                  'Juli', 'August', 'September', 'Oktober', 'November',
                  'Dezember'];

    var AMPEL_ORDER = ['rot', 'gelb', 'gruen', 'neutral'];

    // =========================================================================
    // 1) REINE FUNKTIONEN — Datum/Raster/Anfragen. Kein DOM. Genau diese
    //    prueft vitest.
    //
    //    ALLE Datumsrechnung laeuft ueber Date.UTC. Mit lokaler Zeit wuerde in
    //    der Sommerzeit ein Tagessprung um eine Stunde danebenliegen und ein
    //    Monatserster koennte auf den Vormonat fallen. Der SERVER bleibt die
    //    Quelle der Wahrheit fuer den Stichtag (stichtag.py, Europe/Berlin) —
    //    hier wird nur das Raster gezeichnet.
    // =========================================================================

    function pad2(n) { return (n < 10 ? '0' : '') + n; }

    // isoOf: Date -> 'YYYY-MM-DD' (UTC-Felder!).
    function isoOf(d) {
        return d.getUTCFullYear() + '-' + pad2(d.getUTCMonth() + 1) + '-'
            + pad2(d.getUTCDate());
    }

    // dateOf: 'YYYY-MM-DD' -> Date (UTC-Mitternacht).
    function dateOf(iso) {
        var p = String(iso).split('-');
        return new Date(Date.UTC(parseInt(p[0], 10),
                                 parseInt(p[1], 10) - 1,
                                 parseInt(p[2], 10)));
    }

    // ymOf: 'YYYY-MM-DD' -> 'YYYY-MM'
    function ymOf(iso) { return String(iso).slice(0, 7); }

    // monthRange: 'YYYY-MM' -> {von, bis} (erster/letzter Tag, beide inklusiv).
    function monthRange(ym) {
        var p = ym.split('-');
        var y = parseInt(p[0], 10), m = parseInt(p[1], 10);
        var von = new Date(Date.UTC(y, m - 1, 1));
        var bis = new Date(Date.UTC(y, m, 0));      // Tag 0 = letzter des Vormonats
        return { von: isoOf(von), bis: isoOf(bis) };
    }

    // shiftMonth: Monat verschieben (Jahreswechsel inbegriffen).
    function shiftMonth(ym, delta) {
        var p = ym.split('-');
        var d = new Date(Date.UTC(parseInt(p[0], 10),
                                  parseInt(p[1], 10) - 1 + delta, 1));
        return d.getUTCFullYear() + '-' + pad2(d.getUTCMonth() + 1);
    }

    function monthLabel(ym) {
        var p = ym.split('-');
        return MONTHS[parseInt(p[1], 10) - 1] + ' ' + p[0];
    }

    // gridDays: Tage des Monatsrasters, MONTAG zuerst, aufgefuellt bis zu
    // vollen Wochen. Liefert [{iso, tag, imMonat}].
    function gridDays(ym) {
        var r = monthRange(ym);
        var first = dateOf(r.von);
        var last = dateOf(r.bis);

        // getUTCDay(): 0=So..6=Sa -> auf Montag=0 umrechnen.
        var lead = (first.getUTCDay() + 6) % 7;
        var trail = 6 - ((last.getUTCDay() + 6) % 7);

        var out = [];
        var cur = new Date(first.getTime() - lead * 86400000);
        var total = lead + last.getUTCDate() + trail;
        for (var i = 0; i < total; i++) {
            var iso = isoOf(cur);
            out.push({ iso: iso, tag: cur.getUTCDate(),
                       imMonat: ymOf(iso) === ym });
            cur = new Date(cur.getTime() + 86400000);
        }
        return out;
    }

    // entriesByDay: Kalendereintraege auf Tage abbilden. Ein ZEITRAUM
    // (Abwesenheit) erscheint an JEDEM betroffenen Tag — sonst saehe man am
    // Tag der Wiedervorlage nicht, dass der Ermittler da im Urlaub ist. Das ist
    // der eigentliche Nutzen der gemeinsamen Sicht.
    // Begrenzt auf [von, bis], damit ein langer Zeitraum das Raster nicht
    // sprengt.
    function entriesByDay(entries, von, bis) {
        var map = {};
        (entries || []).forEach(function (e) {
            var start = e.von < von ? von : e.von;
            var end = e.bis > bis ? bis : e.bis;
            if (end < start) { return; }
            var cur = dateOf(start);
            var stop = dateOf(end);
            var guard = 0;
            while (cur.getTime() <= stop.getTime() && guard < 400) {
                var iso = isoOf(cur);
                (map[iso] = map[iso] || []).push(e);
                cur = new Date(cur.getTime() + 86400000);
                guard++;
            }
        });
        return map;
    }

    // outsideOverdue: UEBERFAELLIGE Eintraege, die VOR dem angezeigten Monat
    // liegen. Sie wuerden im Raster nicht erscheinen — und genau so gehen
    // Wiedervorlagen verloren. Deshalb bekommen sie einen eigenen Block.
    function outsideOverdue(entries, von) {
        return (entries || []).filter(function (e) {
            return e.ampel === 'rot' && e.bis < von;
        });
    }

    function ampelCounts(entries) {
        var c = { rot: 0, gelb: 0, gruen: 0, neutral: 0 };
        (entries || []).forEach(function (e) {
            if (c[e.ampel] !== undefined) { c[e.ampel] += 1; }
        });
        return c;
    }

    // --- Vorgangsliste ------------------------------------------------------
    function toMatterRows(data) {
        return ((data && data.matters) || []).map(function (m) {
            return {
                id: m.id,
                subject_id: m.subject_id,
                fall_username: m.fall_username || '',
                kind: m.kind,
                kind_label: m.kind_label || m.kind,
                betreff: m.betreff || '',
                adressat: m.adressat || '',
                aktenzeichen: m.aktenzeichen || '',
                angefordert_am: m.angefordert_am,
                wiedervorlage_am: m.wiedervorlage_am,
                vorwarnfrist_tage: m.vorwarnfrist_tage,
                status: m.status,
                status_label: m.status_label || m.status,
                ergebnis: m.ergebnis || '',
                case_status: m.case_status || '',
                ampel: m.ampel,
                ampel_grund: m.ampel_grund || ''
            };
        });
    }

    function filterByAmpel(rows, ampel) {
        if (!ampel) { return rows; }
        return (rows || []).filter(function (r) { return r.ampel === ampel; });
    }

    // availableActions: welche Aktionen sind fuer DIESEN Vorgang moeglich?
    // Spiegelt MatterStatus (Build 385) — die Oberflaeche bietet nichts an,
    // was der Server zwingend abweisen wuerde.
    //   offen       -> verschieben | beantwortet | ohne Ergebnis abschliessen
    //   beantwortet -> verschieben | erledigt    | ohne Ergebnis abschliessen
    //   erledigt/erfolglos -> NICHTS (unwiderruflich)
    function availableActions(row, canEdit) {
        if (!row || !canEdit) { return []; }
        var acts = [];
        if (row.status === 'offen' || row.status === 'beantwortet') {
            acts.push({ kind: 'defer', label: 'Wiedervorlage verschieben' });
        }
        if (row.status === 'offen') {
            acts.push({ kind: 'answer', label: 'Antwort eingegangen' });
        }
        if (row.status === 'beantwortet') {
            acts.push({ kind: 'erledigt',
                        label: 'Erledigt (ausgewertet) \u2014 endgueltig' });
        }
        if (row.status === 'offen' || row.status === 'beantwortet') {
            acts.push({ kind: 'erfolglos',
                        label: 'Ohne Ergebnis abschliessen \u2014 endgueltig' });
        }
        return acts;
    }

    // --- Anfragen (Validierung VOR dem POST) --------------------------------
    // Jede Funktion liefert {path, body} ODER {error: '...'}. Die Oberflaeche
    // zeigt den Fehler an und schickt NICHTS — kein POST, der sicher scheitert.

    function createRequest(f) {
        f = f || {};
        if (!f.subject_id) { return { error: 'Fall (subject_id) fehlt.' }; }
        if (!f.kind) { return { error: 'Vorgangsart fehlt.' }; }
        if (!String(f.betreff || '').trim()) {
            return { error: 'Betreff ist Pflicht.' };
        }
        if (!f.wiedervorlage_am) {
            return { error: 'Wiedervorlagedatum ist Pflicht.' };
        }
        var frist = parseInt(f.vorwarnfrist_tage, 10);
        if (isNaN(frist) || frist < 0) { frist = 7; }
        return {
            path: '/api/external/create',
            body: {
                subject_id: parseInt(f.subject_id, 10),
                kind: f.kind,
                betreff: String(f.betreff).trim(),
                adressat: String(f.adressat || ''),
                aktenzeichen: f.aktenzeichen || null,
                angefordert_am: f.angefordert_am || undefined,
                wiedervorlage_am: f.wiedervorlage_am,
                vorwarnfrist_tage: frist
            }
        };
    }

    function deferRequest(matterId, datum, grund) {
        if (!matterId) { return { error: 'Kein Vorgang gewaehlt.' }; }
        if (!datum) { return { error: 'Neues Wiedervorlagedatum fehlt.' }; }
        // GRUND IST PFLICHT (Build 385). Ein stilles Verschieben ist genau die
        // Luecke, die dieses System schliessen soll.
        if (!String(grund || '').trim()) {
            return { error: 'Grund ist Pflicht: eine Wiedervorlage darf nicht '
                            + 'ohne nachvollziehbaren Grund verschoben werden.' };
        }
        return {
            path: '/api/external/defer',
            body: { matter_id: matterId, wiedervorlage_am: datum,
                    grund: String(grund).trim() }
        };
    }

    function answerRequest(matterId, ergebnis) {
        if (!matterId) { return { error: 'Kein Vorgang gewaehlt.' }; }
        return {
            path: '/api/external/answer',
            body: { matter_id: matterId, ergebnis: String(ergebnis || '') }
        };
    }

    function closeRequest(matterId, status, ergebnis) {
        if (!matterId) { return { error: 'Kein Vorgang gewaehlt.' }; }
        if (status !== 'erledigt' && status !== 'erfolglos') {
            return { error: 'Abschluss nur als erledigt oder erfolglos.' };
        }
        return {
            path: '/api/external/close',
            body: { matter_id: matterId, status: status,
                    ergebnis: String(ergebnis || '') }
        };
    }

    // confirmText: Der Bestaetigungstext nennt die Folgen beim Namen.
    function confirmText(kind, row) {
        var wer = 'Vorgang ' + (row ? row.id : '?') + ' (Fall '
            + (row ? row.subject_id : '?') + ')';
        if (kind === 'defer') {
            return wer + ': Die Wiedervorlage wird verschoben. Der Vorgang und '
                + 'der Grund werden im audit_log belegt.';
        }
        if (kind === 'answer') {
            return wer + ': Die Antwort wird als eingegangen erfasst. Der '
                + 'Vorgang bleibt in der Wiedervorlage, bis er ausgewertet ist.';
        }
        return wer + ': Der Vorgang wird ENDGUELTIG als "'
            + (kind === 'erledigt' ? 'erledigt' : 'ohne Ergebnis abgeschlossen')
            + '" geschlossen. Das laesst sich NICHT zurueckdrehen \u2014 ein '
            + 'Irrtum wird durch einen NEUEN Vorgang korrigiert.';
    }

    // =========================================================================
    // 2) DOM/RENDER
    // =========================================================================

    var _COLUMNS = [
        { title: 'A', field: 'ampel', width: 46, hozAlign: 'center' },
        { title: 'Nr.', field: 'id', width: 60, sorter: 'number' },
        { title: 'Fall', field: 'subject_id', width: 70, sorter: 'number' },
        { title: 'Benutzername', field: 'fall_username',
          headerFilter: 'input' },
        { title: 'Art', field: 'kind_label' },
        { title: 'Betreff', field: 'betreff', headerFilter: 'input' },
        { title: 'Adressat', field: 'adressat' },
        { title: 'Wiedervorlage', field: 'wiedervorlage_am', width: 120 },
        { title: 'Zustand', field: 'status_label' },
        { title: 'Begruendung', field: 'ampel_grund' }
    ];

    function _el(doc, tag, cls, text) {
        var e = doc.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    function _btn(doc, id, text) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.id = id;
        b.className = 'aiw-btn aiw-cal-btn';
        b.textContent = text;
        return b;
    }

    function _field(doc, id, label, type, value) {
        var wrap = _el(doc, 'label', 'aiw-cal-field');
        wrap.appendChild(_el(doc, 'span', null, label));
        var inp = doc.createElement('input');
        inp.type = type || 'text';
        inp.id = id;
        if (value !== undefined && value !== null) { inp.value = value; }
        wrap.appendChild(inp);
        // Build 636 (Vorgang 17200856): Die Fabrik gibt die HUELLE zurueck
        // (das <label> mit Beschriftung und Feld). Die Abnahmestelle braucht
        // aber das Feld, um die Hilfe-Marke LITERAL zu setzen - eine Fabrik
        // koennte nur EINE Kennung fuer alle elf Felder vergeben.
        wrap.eingabe = inp;
        return wrap;
    }

    // _tk / _mitHilfe (Build 551): gemeinsames Tabellen-Werkzeug + Hilfe-Anker
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

    // renderCalendar: die gesamte Sicht.
    //   cal   — Antwort von /api/calendar
    //   ext   — Antwort von /api/external
    //   opts  — { ym, canEdit, Tabulator, onMonth(ym), onCreate(body),
    //             onDefer(body), onAnswer(body), onClose(body) }
    // Rueckgabe: { table, setResult, getSelected }
    function renderCalendar(mainEl, cal, ext, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = mainEl.ownerDocument || document;
        mainEl.textContent = '';

        var ym = opts.ym || ymOf((cal && cal.von) || '2026-01-01');
        var range = monthRange(ym);
        var canEdit = !!opts.canEdit;
        var entries = (cal && cal.entries) || [];
        var rows = toMatterRows(ext);

        // --- Kopf ------------------------------------------------------------
        // Build 595 (Baustelle H / H7): literale Hilfe-Marken fuer Kopf und
        // Stichtagszeile. Die Spaltenkoepfe der Tabelle bekommen ihre Anker
        // vom gemeinsamen Tabellen-Werkzeug (Praefix 'calendar').
        var kopfEl = _el(doc, 'h2', 'aiw-pagehead',
                         'Kalender & Wiedervorlage');
        kopfEl.setAttribute('data-hilfe-id', 'calendar.titel');
        mainEl.appendChild(kopfEl);

        // DIE RECHENGRUNDLAGE. Steht sichtbar, damit eine falsche Uhr auffaellt.
        var st = _el(doc, 'p', 'aiw-pagesub aiw-cal-stichtag',
                     (cal && cal.stichtag_text) || '');
        st.id = 'aiw-cal-stichtag';
        st.setAttribute('data-hilfe-id', 'calendar.stichtag');
        mainEl.appendChild(st);

        // --- HINWEISE: der Kalender sagt, wenn er schweigt --------------------
        var hinweise = (cal && cal.hinweise) || [];
        if (hinweise.length) {
            var hb = _el(doc, 'div', 'aiw-cal-hints');
            hb.id = 'aiw-cal-hints';
            hb.appendChild(_el(doc, 'div', 'aiw-cal-hints-title',
                'Diese Sicht ist NICHT vollstaendig \u2014 '
                + hinweise.length + ' Quelle(n) liefern nichts:'));
            var hl = doc.createElement('ul');
            hinweise.forEach(function (h) {
                hl.appendChild(_el(doc, 'li', null, h));
            });
            hb.appendChild(hl);
            mainEl.appendChild(hb);
        }

        // --- UEBERFAELLIG AUSSERHALB DES MONATS -------------------------------
        // Der wichtigste Block der Sicht: was hier steht, waere sonst beim
        // Blaettern unsichtbar.
        var alt = outsideOverdue(entries, range.von);
        if (alt.length) {
            var ob = _el(doc, 'div', 'aiw-cal-overdue');
            ob.id = 'aiw-cal-overdue';
            ob.appendChild(_el(doc, 'div', 'aiw-cal-overdue-title',
                alt.length + ' UEBERFAELLIGE(R) VORGANG/VORGAENGE aus einem '
                + 'frueheren Zeitraum \u2014 sie stehen NICHT im Raster unten:'));
            var ol = doc.createElement('ul');
            alt.forEach(function (e) {
                ol.appendChild(_el(doc, 'li', null,
                    e.von + ' \u2014 Fall ' + e.subject_id + ' ('
                    + e.subject_label + '): ' + e.titel
                    + ' \u2014 ' + e.ampel_grund));
            });
            ob.appendChild(ol);
            mainEl.appendChild(ob);
        }

        // --- Monatsnavigation -------------------------------------------------
        var nav = _el(doc, 'div', 'aiw-cal-nav');
        var prev = _btn(doc, 'aiw-cal-prev', '\u2039 Vormonat');
        prev.setAttribute('data-hilfe-id', 'calendar.bedienung.vormonat');
        var next = _btn(doc, 'aiw-cal-next', 'Folgemonat \u203a');
        next.setAttribute('data-hilfe-id', 'calendar.bedienung.folgemonat');
        var heute = _btn(doc, 'aiw-cal-today', 'Heute');
        heute.setAttribute('data-hilfe-id', 'calendar.bedienung.heute');
        var titel = _el(doc, 'span', 'aiw-cal-month', monthLabel(ym));
        titel.id = 'aiw-cal-month';

        prev.addEventListener('click', function () {
            if (opts.onMonth) { opts.onMonth(shiftMonth(ym, -1)); }
        });
        next.addEventListener('click', function () {
            if (opts.onMonth) { opts.onMonth(shiftMonth(ym, 1)); }
        });
        heute.addEventListener('click', function () {
            if (opts.onMonth) {
                opts.onMonth(ymOf((cal && cal.stichtag) || range.von));
            }
        });
        nav.appendChild(prev);
        nav.appendChild(titel);
        nav.appendChild(next);
        nav.appendChild(heute);

        var c = ampelCounts(entries);
        nav.appendChild(_el(doc, 'span', 'aiw-cal-counts',
            c.rot + ' faellig/ueberfaellig \u00b7 ' + c.gelb + ' naht \u00b7 '
            + c.gruen + ' spaeter \u00b7 ' + c.neutral + ' sonstige'));
        mainEl.appendChild(nav);

        // --- Monatsraster -----------------------------------------------------
        var byDay = entriesByDay(entries, range.von, range.bis);
        var grid = _el(doc, 'table', 'aiw-cal-grid');
        grid.id = 'aiw-cal-grid';
        var thead = doc.createElement('thead');
        var htr = doc.createElement('tr');
        WEEKDAYS.forEach(function (w) {
            htr.appendChild(_el(doc, 'th', null, w));
        });
        thead.appendChild(htr);
        grid.appendChild(thead);

        var tbody = doc.createElement('tbody');
        var days = gridDays(ym);
        var tr = null;
        days.forEach(function (d, i) {
            if (i % 7 === 0) {
                tr = doc.createElement('tr');
                tbody.appendChild(tr);
            }
            var td = doc.createElement('td');
            td.className = 'aiw-cal-day'
                + (d.imMonat ? '' : ' aiw-cal-out')
                + (d.iso === (cal && cal.stichtag) ? ' aiw-cal-today' : '');
            td.setAttribute('data-day', d.iso);
            td.appendChild(_el(doc, 'div', 'aiw-cal-daynum', String(d.tag)));

            (byDay[d.iso] || []).forEach(function (e) {
                var chip = _el(doc, 'div', 'aiw-cal-chip aiw-a-' + e.ampel);
                chip.setAttribute('data-source', e.source);
                chip.setAttribute('data-ref', String(e.ref_id));
                chip.title = e.titel + (e.ampel_grund
                    ? ' \u2014 ' + e.ampel_grund : '');
                chip.textContent = (e.subject_label ? e.subject_label + ': ' : '')
                    + e.titel;
                td.appendChild(chip);
            });
            tr.appendChild(td);
        });
        grid.appendChild(tbody);
        mainEl.appendChild(grid);

        // --- Faelligkeitsliste (Vorgaenge) ------------------------------------
        mainEl.appendChild(_el(doc, 'h3', 'aiw-subhead',
                               'Externe Vorgaenge (' + rows.length + ')'));

        var bar = _el(doc, 'div', 'aiw-cal-bar');
        var sel = doc.createElement('select');
        sel.id = 'aiw-cal-filter';
        sel.setAttribute('data-hilfe-id', 'calendar.bedienung.ampelfilter');
        var oa = doc.createElement('option');
        oa.value = '';
        oa.text = 'alle Ampeln (' + rows.length + ')';
        sel.appendChild(oa);
        AMPEL_ORDER.forEach(function (a) {
            var o = doc.createElement('option');
            o.value = a;
            o.text = a + ' (' + filterByAmpel(rows, a).length + ')';
            sel.appendChild(o);
        });
        bar.appendChild(sel);

        if (canEdit) {
            // Build 636: frueher direkt in appendChild. Eine Abnahmestelle
            // ohne Variable kann keine Marke tragen - der Knopf waere stumm.
            var neuBtn = _btn(doc, 'aiw-cal-new', 'Neuer Vorgang');
            neuBtn.setAttribute('data-hilfe-id',
                                'calendar.bedienung.neuer_vorgang');
            bar.appendChild(neuBtn);
        }
        mainEl.appendChild(bar);

        var container = _el(doc, 'div', null);
        container.id = 'aiw-cal-table';
        mainEl.appendChild(container);

        // --- Aktionsfeld ------------------------------------------------------
        var panel = _el(doc, 'div', 'aiw-cal-actions');
        panel.id = 'aiw-cal-actions';
        mainEl.appendChild(panel);

        var form = _el(doc, 'div', 'aiw-cal-form');
        form.id = 'aiw-cal-form';
        mainEl.appendChild(form);

        var result = _el(doc, 'div', 'aiw-cal-result');
        result.id = 'aiw-cal-result';
        mainEl.appendChild(result);

        var selected = null;

        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }

        // send: gemeinsamer Weg fuer alle Schreibpfade. Validierung ZUERST —
        // eine Anfrage, die sicher scheitert, wird gar nicht erst gestellt.
        function send(req, cb) {
            if (req.error) { setResult(req.error, true); return; }
            setResult('Schreibe \u2026', null);
            cb(req.body);
        }

        // --- Bestaetigung (zweistufig) ----------------------------------------
        function askConfirm(kind, row, felder, onYes) {
            panel.textContent = '';
            panel.appendChild(_el(doc, 'div', 'aiw-cal-confirm-title',
                                  confirmText(kind, row)));
            var box = _el(doc, 'div', 'aiw-cal-confirm');
            box.id = 'aiw-cal-confirm';
            felder.forEach(function (f) { box.appendChild(f); });

            var yes = _btn(doc, 'aiw-cal-confirm-yes', 'Ja, ausfuehren');
            yes.setAttribute('data-hilfe-id', 'calendar.bedienung.bestaetigen');
            yes.addEventListener('click', function () { onYes(); });
            box.appendChild(yes);

            var no = _btn(doc, 'aiw-cal-confirm-no', 'Abbrechen');
            no.setAttribute('data-hilfe-id', 'calendar.bedienung.abbrechen');
            no.addEventListener('click', function () {
                panel.textContent = '';
                selectRow(selected);
                setResult('Abgebrochen. Es wurde nichts geschrieben.', false);
            });
            box.appendChild(no);
            panel.appendChild(box);
        }

        function selectRow(r) {
            selected = r || null;
            panel.textContent = '';
            if (!r) { return; }

            panel.appendChild(_el(doc, 'div', 'aiw-subhead',
                'Vorgang ' + r.id + ' \u2014 Fall ' + r.subject_id + ' ('
                + r.fall_username + '): ' + r.kind_label + ' \u00b7 '
                + r.status_label));
            panel.appendChild(_el(doc, 'div', 'aiw-cal-grund', r.ampel_grund));

            var acts = availableActions(r, canEdit);
            if (!acts.length) {
                panel.appendChild(_el(doc, 'div', 'aiw-placeholder',
                    canEdit
                        ? 'Der Vorgang ist endgueltig abgeschlossen \u2014 keine '
                          + 'Aktion mehr moeglich. Ein Irrtum wird durch einen '
                          + 'NEUEN Vorgang korrigiert.'
                        : 'Nur Lesezugriff (Faehigkeit external.edit fehlt).'));
                return;
            }

            var btns = _el(doc, 'div', 'aiw-cal-btns');
            acts.forEach(function (a) {
                var b = _btn(doc, 'aiw-cal-act-' + a.kind, a.label);
                b.setAttribute('data-hilfe-id', 'calendar.bedienung.aktion');
                b.addEventListener('click', function () {
                    if (a.kind === 'defer') {
                        var dIn = _field(doc, 'aiw-cal-defer-datum',
                                         'Neues Wiedervorlagedatum', 'date',
                                         r.wiedervorlage_am);
                        dIn.eingabe.setAttribute('data-hilfe-id',
                            'calendar.bedienung.neues_datum');
                        var gIn = _field(doc, 'aiw-cal-defer-grund',
                                         'Grund (Pflicht)', 'text', '');
                        gIn.eingabe.setAttribute('data-hilfe-id',
                            'calendar.bedienung.verschiebegrund');
                        askConfirm('defer', r, [dIn, gIn], function () {
                            send(deferRequest(
                                r.id,
                                doc.getElementById('aiw-cal-defer-datum').value,
                                doc.getElementById('aiw-cal-defer-grund').value
                            ), opts.onDefer || function () {});
                        });
                        return;
                    }
                    if (a.kind === 'answer') {
                        var eIn = _field(doc, 'aiw-cal-answer-erg',
                                         'Ergebnis (optional)', 'text', '');
                        eIn.eingabe.setAttribute('data-hilfe-id',
                            'calendar.bedienung.antwortergebnis');
                        askConfirm('answer', r, [eIn], function () {
                            send(answerRequest(
                                r.id,
                                doc.getElementById('aiw-cal-answer-erg').value
                            ), opts.onAnswer || function () {});
                        });
                        return;
                    }
                    var cIn = _field(doc, 'aiw-cal-close-erg',
                                     'Ergebnis / Begruendung', 'text',
                                     r.ergebnis || '');
                    cIn.eingabe.setAttribute('data-hilfe-id',
                        'calendar.bedienung.abschlussergebnis');
                    askConfirm(a.kind, r, [cIn], function () {
                        send(closeRequest(
                            r.id, a.kind,
                            doc.getElementById('aiw-cal-close-erg').value
                        ), opts.onClose || function () {});
                    });
                });
                btns.appendChild(b);
            });
            panel.appendChild(btns);
        }

        // --- Formular "Neuer Vorgang" -----------------------------------------
        function openForm() {
            form.textContent = '';
            form.appendChild(_el(doc, 'div', 'aiw-subhead',
                                 'Neuer externer Vorgang'));

            // FALL: bewusst ein EINGABEFELD, keine Auswahlliste.
            //
            // Begruendung (wichtig, sonst wirkt das wie eine Bequemlichkeit):
            // /api/external liefert nur Faelle, zu denen SCHON EIN VORGANG
            // existiert. Eine daraus gebaute Auswahlliste koennte fuer einen
            // Fall OHNE Vorgang NIE einen ersten Vorgang anlegen — genau der
            // Normalfall. Eine Auswahlliste haette diesen Mangel STILL
            // versteckt (die Liste sieht ja gefuellt aus).
            // Der Server prueft die Eingabe ohnehin doppelt: unbekannter Fall
            // -> 400, nicht zugewiesener Fall -> 403 (Build 385). Nichts kann
            // durchrutschen.
            // Eine komfortable Fallauswahl braucht einen eigenen Endpunkt
            // ('welche Faelle darf ich?') -> vermerkt fuer einen spaeteren Build.
            var fw = _field(doc, 'aiw-cal-new-fall',
                            'Fall (subject_id) \u2014 Pflicht', 'number',
                            (selected ? String(selected.subject_id) : ''));
            fw.eingabe.setAttribute('data-hilfe-id',
                                    'calendar.bedienung.fall');
            form.appendChild(fw);

            var art = doc.createElement('select');
            art.id = 'aiw-cal-new-kind';
            art.setAttribute('data-hilfe-id', 'calendar.bedienung.vorgangsart');
            ((ext && ext.kinds) || []).forEach(function (k) {
                var o = doc.createElement('option');
                o.value = k.code;
                o.text = k.label;
                art.appendChild(o);
            });
            var aw = _el(doc, 'label', 'aiw-cal-field');
            aw.appendChild(_el(doc, 'span', null, 'Vorgangsart'));
            aw.appendChild(art);
            form.appendChild(aw);

            // Build 636: frueher fuenfmal direkt in appendChild. Ohne
            // Variable kann keine Marke gesetzt werden - die Felder waeren
            // stumm geblieben.
            var fBetreff = _field(doc, 'aiw-cal-new-betreff',
                                  'Betreff (Pflicht)', 'text', '');
            fBetreff.eingabe.setAttribute('data-hilfe-id',
                                          'calendar.bedienung.betreff');
            form.appendChild(fBetreff);
            var fAdressat = _field(doc, 'aiw-cal-new-adressat',
                                   'Adressat', 'text', '');
            fAdressat.eingabe.setAttribute('data-hilfe-id',
                                           'calendar.bedienung.adressat');
            form.appendChild(fAdressat);
            var fAz = _field(doc, 'aiw-cal-new-az',
                             'Aktenzeichen (extern)', 'text', '');
            fAz.eingabe.setAttribute('data-hilfe-id',
                                     'calendar.bedienung.aktenzeichen');
            form.appendChild(fAz);
            var fWv = _field(doc, 'aiw-cal-new-wv',
                             'Wiedervorlage (Pflicht)', 'date', '');
            fWv.eingabe.setAttribute('data-hilfe-id',
                                     'calendar.bedienung.wiedervorlage');
            form.appendChild(fWv);
            var fFrist = _field(doc, 'aiw-cal-new-frist',
                                'Vorwarnfrist (Tage)', 'number', '7');
            fFrist.eingabe.setAttribute('data-hilfe-id',
                                        'calendar.bedienung.vorwarnfrist');
            form.appendChild(fFrist);

            var ok = _btn(doc, 'aiw-cal-new-save', 'Anlegen');
            ok.setAttribute('data-hilfe-id', 'calendar.bedienung.anlegen');
            ok.addEventListener('click', function () {
                send(createRequest({
                    subject_id: doc.getElementById('aiw-cal-new-fall').value,
                    kind: doc.getElementById('aiw-cal-new-kind').value,
                    betreff: doc.getElementById('aiw-cal-new-betreff').value,
                    adressat: doc.getElementById('aiw-cal-new-adressat').value,
                    aktenzeichen: doc.getElementById('aiw-cal-new-az').value,
                    wiedervorlage_am: doc.getElementById('aiw-cal-new-wv').value,
                    vorwarnfrist_tage:
                        doc.getElementById('aiw-cal-new-frist').value
                }), opts.onCreate || function () {});
            });
            form.appendChild(ok);

            var ab = _btn(doc, 'aiw-cal-new-cancel', 'Abbrechen');
            ab.setAttribute('data-hilfe-id',
                            'calendar.bedienung.formular_abbrechen');
            ab.addEventListener('click', function () {
                form.textContent = '';
                setResult('Abgebrochen. Es wurde nichts geschrieben.', false);
            });
            form.appendChild(ab);
        }

        var newBtn = mainEl.querySelector('#aiw-cal-new');
        if (newBtn) { newBtn.addEventListener('click', openForm); }

        // --- Tabelle ----------------------------------------------------------
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        var TK = _tk();
        if (typeof Ctor !== 'function' || !TK) {
            // Build 551: die ZAHL gehoert in die Ersatzmeldung — ohne sie
            // saehe der Ausfall aus wie ein Leerbefund (Grundregel 1).
            container.appendChild(_el(doc, 'div', 'aiw-placeholder',
                'Tabellenbibliothek nicht verfügbar — es liegen '
                + rows.length + ' Vorgänge vor. Raster, Warnungen und '
                + 'Stichtag oben sind dennoch gültig.'));
            log('renderCalendar: kein Tabulator-Ctor/TableKit');
            return { table: null, setResult: setResult,
                     getSelected: function () { return selected; },
                     selectRow: selectRow, openForm: openForm };
        }

        // Build 551 (UX): Aufbau ueber das gemeinsame Tabellen-Werkzeug.
        //
        // DER ZEILENKLICK GEHT UEBER onRowClick UND NICHT ueber
        // tabulator.rowClick: letzteres ist in Tabulator v6.4.0 keine
        // Konstruktoroption und wurde IGNORIERT. Diese Sicht hat den Vorgang
        // beim Anklicken einer Zeile seit Build 386 nicht ausgewaehlt — ohne
        // Fehlermeldung. Derselbe Fehler steckte in support und reports;
        // Lektorat und Chef-Freigabe waren in Build 486 bereits repariert
        // worden, die uebrigen drei nie.
        var table = TK.tabelleAufbauen(doc, container, {
            sicht: 'calendar',
            rows: rows,
            columns: _mitHilfe(_COLUMNS, 'calendar', doc),
            Ctor: Ctor,
            einheit: 'Vorgänge',
            onRowClick: function (e, row) { selectRow(row.getData()); },
            tabulator: {
                height: '360px',
                rowFormatter: function (row) {
                    var el = row.getElement();
                    if (el && el.classList) {
                        el.classList.add('aiw-row-' + row.getData().ampel);
                    }
                }
            }
        }).table;

        sel.addEventListener('change', function () {
            var f = filterByAmpel(rows, sel.value);
            if (typeof table.replaceData === 'function') {
                table.replaceData(f);
            }
            panel.textContent = '';
            selected = null;
            log('Ampelfilter:', sel.value || '(alle)', '->', f.length);
        });

        log('renderCalendar:', ym, entries.length, 'Kalendereintraege,',
            rows.length, 'Vorgaenge,', alt.length, 'ueberfaellig ausserhalb');

        return { table: table, setResult: setResult,
                 getSelected: function () { return selected; },
                 selectRow: selectRow, openForm: openForm };
    }

    // =========================================================================
    // 3) UMD-Ausgang
    // =========================================================================
    var API = {
        WEEKDAYS: WEEKDAYS,
        isoOf: isoOf,
        dateOf: dateOf,
        ymOf: ymOf,
        monthRange: monthRange,
        shiftMonth: shiftMonth,
        monthLabel: monthLabel,
        gridDays: gridDays,
        entriesByDay: entriesByDay,
        outsideOverdue: outsideOverdue,
        ampelCounts: ampelCounts,
        toMatterRows: toMatterRows,
        filterByAmpel: filterByAmpel,
        availableActions: availableActions,
        createRequest: createRequest,
        deferRequest: deferRequest,
        answerRequest: answerRequest,
        closeRequest: closeRequest,
        confirmText: confirmText,
        renderCalendar: renderCalendar
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitCalendar = API; }
})();
