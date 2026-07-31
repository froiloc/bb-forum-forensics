/**
 * management/server/static/cockpit_lectorate.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Vermaehlung B6xB7 — W4 (Lektorat), SLICE 1 (Build 413)
 *
 * Zweck:
 *   Gegenlese-Sicht fuer Lektor:innen (Recht reports.review; die Chefin mit
 *   reports.approve sieht sie ebenfalls). SLICE 1 liefert:
 *     - eine Auswahl der gegenzulesenden Berichte (Quelle: /api/reports),
 *     - die READ-ONLY-Vorschau des Berichtstexts in einem <iframe>
 *       (Quelle: /api/report/render, SF-1 Build 410 — byte-identisch zum Export).
 *   Annotationen (SF-2) und das Kommentar-Panel (SF-3) folgen in den naechsten
 *   Slices (Build 414/415).
 *
 * JS-Gebote des Projekts:
 *   1) IIFE-Wrapper mit 'use strict'.
 *   2) Ausgiebiges DEV-Logging (DEV=true), fuer PROD ueber die Konstante DEV
 *      abschaltbar.
 *   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
 *   4) Kapselung: interner Zustand liegt in der Closure; nach aussen nur eine
 *      kleine API (window.AIWCockpitLectorate). REINE Funktionen (kein DOM)
 *      sind separat exportiert und werden von vitest geprueft.
 *
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Build 479: hasSelection() ergaenzt. Schutz vor selbst ausgeloestem
 *   SSE-Reload: Das Oeffnen eines Berichts holt /api/report/annotations, was
 *   serverseitig den Chain-of-Custody-Beleg 'report_annotations_viewed' in den
 *   coordinator.db-audit_log schreibt (management_app.py:_audit_annotation_view;
 *   Grundregel 1). Die SSE beobachtet die audit_log-Spitze und meldet ~2s
 *   spaeter 'changed' (management_handler.py:_handle_sse, poll=2.0s) -> der
 *   frueher folgende loadLectorate()-Reload verwarf Auswahl + iframe-Vorschau
 *   (gemeldeter Fehler). cockpit.js unterdrueckt den Reload nun anhand von
 *   hasSelection(), solange ein Bericht in Sichtung ist.
 * Build 480: Bugfix — der Statusfilter-Wechsel reichte onTransferToTemplate
 *   nicht mehr durch, wodurch der Knopf "Als Vorlage uebernehmen" nach jedem
 *   Filterwechsel verschwand. Callback wird nun beim Neu-Rendern erhalten.
 * Build 481 (Tabulator-Umbau, SLICE 1): Die Auswahl-Liste (bisher ein <button>
 *   je Bericht) wird durch eine Tabulator-Tabelle ersetzt (Muster
 *   cockpit_reports.js, Tabulator v6.4.0). Spalten: Benutzer, Titel, Typ, Nr.,
 *   Status, Verfasser, Erstellt. Auswahl per rowClick (verdrahtet unveraendert
 *   iframe-Vorschau + Belege/Kommentare + Uebernahme-Knopf). Der Statusfilter
 *   wechselt die Tabellendaten via table.replaceData() OHNE Neu-Render (damit
 *   entfaellt der 480-Fehlerfall strukturell). SLICE 2 (Build 482) ergaenzt
 *   Header-Filter, Paginierung (20/Seite), Status-Schnellfilter mit Zaehlern
 *   und verschiebt den Uebernahme-Knopf UNTER die Tabelle.
 * Build 482 (Tabulator-Umbau, SLICE 2): (a) Spalten-Header-Filter (Benutzer/
 *   Titel/Typ/Status/Verfasser als Freitext-Filter); (b) Paginierung 'local'
 *   mit 20 Zeilen/Seite + deutschem Pager; (c) Status-Schnellfilter mit
 *   Trefferzaehlern je Status; (d) Uebernahme-Knopf UNTER die Tabelle verschoben
 *   (naeher an der Darstellung).
 * Build 484: Typ- und Status-Spalte erhalten DROPDOWN-Header-Filter (list) mit
 *   festen Werten + 'alle'. Der separate Status-<select> ueber der Tabelle
 *   entfaellt; der Default 'Zur Abnahme vorgelegt' wird ueber initialHeaderFilter
 *   gesetzt, die Tabelle laedt alle Zeilen. statusCounts (Zaehler am alten
 *   Select) entfernt. Status filtert ueber den Roh-Status (rowData.status),
 *   damit 'Versandt' waehlbar bleibt.
 * Build 486: Zwei Bugfixes. (a) Zeilenklick reagierte nicht — 'rowClick' ist in
 *   Tabulator v6.4.0 KEINE Konstruktor-Option und wurde ignoriert; der Handler
 *   wird nun via table.on('rowClick', ...) angehaengt. (b) Der Typ-Dropdown
 *   matchte als Teilstring ('Vermerk' traf auch 'Ergänzungsvermerk'); jetzt
 *   exakter Full-Match ueber headerFilterFunc '='. Status war bereits exakt;
 *   die Eingabezeilen-Filter (Benutzer/Titel/Verfasser) bleiben bewusst
 *   case-insensitiv/teilstring.
 * Version: v0.8.486 · Build: 486 · 2026-07-21
 */
(function () {
    'use strict';

    // --- DEV-Logging (fuer PROD auf false) -------------------------------
    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[lectorate]');
            console.log.apply(console, a);
        }
    }

    // --- gekapselter Sicht-Zustand (Closure, nicht nach aussen sichtbar) --
    var _state = {
        iframe: null,     // aktuelles Vorschau-<iframe>
        selKey: null,     // aktuell gewaehlter Bericht ('uid:rid')
        annPanel: null,   // Belege-Panel (Annotationen, SF-2, Build 414)
        comPanel: null,   // Kommentar-Panel (SF-3, Build 415)
        // Build 475: "Bericht als Vorlage uebernehmen"
        selUid: null,     // subject_id des gewaehlten Berichts
        selRid: null,     // report_id des gewaehlten Berichts
        xferBtn: null,    // Uebernahme-Schaltflaeche (nur mit templates.edit)
        xferMsg: null,    // Rueckmeldezeile der Uebernahme
        // Build 481 (Slice 1): Umstellung der Auswahl-Liste auf eine
        // Tabulator-Tabelle (Muster cockpit_reports.js). Die Instanz wird
        // modul-intern gehalten und in cleanup()/am Kopf von renderLectorate
        // zerstoert (cockpit.js:cleanupView ruft AIWCockpitLectorate.cleanup()).
        table: null,      // aktuelle Tabulator-Instanz (oder null)
        activeRowEl: null // DOM der aktiv markierten Zeile (fuer Entmarkierung)
    };

    // =====================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — genau diese testet vitest.
    // =====================================================================

    // Menschliche Statusbezeichnung (R1-Sprachregelung wie im Renderer).
    function statusLabel(status) {
        switch (status) {
            case 'draft':     return 'Entwurf';
            case 'submitted': return 'Zur Abnahme vorgelegt';
            case 'approved':  return 'Freigegeben';
            case 'final':     return 'Versandt/abgeschlossen';
            default:          return status || 'unbekannt';
        }
    }

    // filterReports: liefert die Berichte je Status. status==='alle' -> alle;
    // Vorgabe der Sicht ist 'submitted' (die zum Gegenlesen vorgelegten). Gibt
    // IMMER ein neues Array (mutiert die Eingabe nicht).
    function filterReports(data, status) {
        var list = (data && data.reports) ? data.reports : [];
        if (!status || status === 'alle') { return list.slice(); }
        return list.filter(function (r) { return r && r.status === status; });
    }

    // renderUrl: URL des read-only Berichtstexts (SF-1). subject_id + report_id
    // werden URL-kodiert (Multilingualitaet/Sonderzeichen unkritisch).
    function renderUrl(uid, rid) {
        return '/api/report/render?subject_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }

    // reportLabel: Zeilentext eines Berichts in der Auswahl.
    function reportLabel(r) {
        if (!r) { return ''; }
        return (r.username || ('uid ' + r.subject_id)) + ' · '
            + (r.title || '(ohne Titel)')
            + ' (' + (r.report_type || '?') + ', Nr. ' + (r.sequence_nr || '?')
            + ') — ' + statusLabel(r.status);
    }

    // selectionKey: stabiler Schluessel eines Berichts (fuer die Markierung).
    function selectionKey(uid, rid) { return String(uid) + ':' + String(rid); }

    // --- Tabellen-Abbildung (Build 481, Slice 1) -------------------------
    // TYPE_LABEL/typeLabel: menschliche Berichtstyp-Bezeichnung. Deckungsgleich
    // zur Berichts-Abnahme (cockpit_reports.js, Build 473 "Vermerk"-Sprachregel),
    // damit beide Berichtstabellen dasselbe Vokabular zeigen. Fallback = Rohcode
    // (Grundregel 1: ein unbekannter Typ bleibt sichtbar).
    var TYPE_LABEL = {
        interim:  'Vermerk',
        addendum: 'Ergänzungsvermerk',
        final:    'Abschlussbericht'
    };
    function typeLabel(t) { return TYPE_LABEL[t] || t || ''; }

    // --- Dropdown-Header-Filter (Build 484) ------------------------------
    // Wertelisten fuer die list-Header-Filter. Der leere Wert '' ('alle') setzt
    // keinen Filter (Tabulator raeumt den Spaltenfilter bei leerem Wert).
    // Reihenfolge = Anzeigereihenfolge im Dropdown.
    var TYP_FILTER_VALUES = {
        '': 'alle',
        'Vermerk': 'Vermerk',
        'Ergänzungsvermerk': 'Ergänzungsvermerk',
        'Abschlussbericht': 'Abschlussbericht'
    };
    // Status: Werte sind die ROH-Statuscodes (nicht die Labels), damit 'Versandt'
    // waehlbar bleibt, obwohl statusLabel('final') = 'Versandt/abgeschlossen'.
    var STATUS_FILTER_VALUES = {
        '': 'alle',
        'submitted': 'Zur Abnahme vorgelegt',
        'approved': 'Freigegeben',
        'final': 'Versandt',
        'draft': 'Entwurf'
    };
    // _statusHeaderFilter: die Status-Spalte zeigt status_label, filtert aber
    // ueber den Roh-Status der Zeile (rowData.status). Leerer Wert => alle. REIN.
    function _statusHeaderFilter(headerValue, rowValue, rowData) {
        if (headerValue === '' || headerValue == null) { return true; }
        return !!rowData && rowData.status === headerValue;
    }

    // fmtTs: Unix-Sekunden -> 'YYYY-MM-DD' (leere Zeichenkette bei 0/undefined).
    // Identisch zu cockpit_reports.js:fmtTs.
    function fmtTs(tsSec) {
        if (!tsSec) { return ''; }
        var d = new Date(tsSec * 1000);
        function p(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
    }

    // toRows: bildet die (nach Status gefilterten) Berichte auf Tabellenzeilen
    // ab. REIN (kein DOM) -> vitest-pruefbar. Fehlende Felder werden sichtbar
    // ersetzt (username -> 'uid <subject_id>'), nicht verschluckt (Grundregel 1).
    // subject_id/id bleiben roh erhalten (fuer die Auswahl in rowClick).
    function toRows(data, status) {
        return filterReports(data, status).map(function (r) {
            return {
                subject_id: r.subject_id,
                id: r.id,
                username: r.username || ('uid ' + r.subject_id),
                title: r.title || '(ohne Titel)',
                typ: typeLabel(r.report_type),
                nr: (r.sequence_nr != null ? r.sequence_nr : ''),
                status: r.status,
                status_label: statusLabel(r.status),
                created_by: r.created_by || '',
                created: fmtTs(r.created_at)
            };
        });
    }

    // annotationsUrl: URL des Annotations-Support-Views (SF-2, Build 411).
    function annotationsUrl(uid, rid) {
        return '/api/report/annotations?subject_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }

    // categoryLabel: menschliche Kategoriebezeichnung. Fallback = Rohcode,
    // damit eine unbekannte Kategorie sichtbar bleibt (Grundregel 1).
    function categoryLabel(cat) {
        switch (cat) {
            case 'CAT_PERSON':   return 'Person';
            case 'CAT_LOCATION': return 'Ort';
            case 'CAT_CONTACT':  return 'Kontakt';
            case 'CAT_TIME':     return 'Zeit';
            case 'CAT_OTHER':    return 'Sonstiges';
            default:             return cat || '—';
        }
    }

    // forumContext: Forenkontext einer Annotation als Text ('—' wenn unbekannt,
    // z.B. wenn fdb.post_aliases die post_id nicht fuehrt).
    function forumContext(item) {
        if (!item || item.topic_id == null || item.forum_id == null) {
            return '—';
        }
        return 'Thema ' + item.topic_id + ' · Unterforum ' + item.forum_id;
    }

    // --- Kommentare (SF-3, Build 415) ---
    // commentsUrl: URL des Union-Lesepfads der Review-Kommentare (SF-3).
    function commentsUrl(uid, rid) {
        return '/api/report/comments?subject_id=' + encodeURIComponent(uid)
            + '&report_id=' + encodeURIComponent(rid);
    }

    // commentStatusLabel: menschliche Statusbezeichnung eines Kommentars.
    function commentStatusLabel(status) {
        switch (status) {
            case 'pending':   return 'offen';
            case 'addressed': return 'erledigt';
            case 'dismissed': return 'verworfen';
            case 'revoked':   return 'zurueckgenommen';
            default:          return status || 'unbekannt';
        }
    }

    // reviewerRoleLabel: Rolle der/des Kommentierenden.
    function reviewerRoleLabel(role) {
        switch (role) {
            case 'supervisor': return 'Chef-Ermittlerin';
            case 'lector':     return 'Lektorat';
            default:           return role || '—';
        }
    }

    // isOwnComment: gehoert der Kommentar der aktuell angemeldeten Person?
    // (Nur eigene Kommentare koennen aufgeloest werden — der Server erzwingt es
    // strukturell ueber den Dateipfad; das UI zeigt die Knoepfe entsprechend.)
    function isOwnComment(comment, personId) {
        return !!comment && personId != null
            && Number(comment.reviewer_pid) === Number(personId);
    }

    // =====================================================================
    // 2) DOM-Aufbau.
    // =====================================================================

    // cleanup: Sicht-Artefakte abbauen (wird aus cockpit.js:cleanupView beim
    // Sichtwechsel gerufen). Da renderLectorate mainEl.innerHTML neu setzt,
    // werden Knoten/Listener ohnehin ersetzt; wir loesen zusaetzlich die
    // internen Referenzen, damit nichts haengen bleibt.
    // _destroyTable (Build 481): die aktuelle Tabulator-Instanz abbauen. Best-
    // effort (Tabulator.destroy kann bei bereits entferntem DOM werfen), damit
    // ein Cleanup nie den Sichtwechsel scheitern laesst.
    function _destroyTable() {
        if (_state.table && typeof _state.table.destroy === 'function') {
            try { _state.table.destroy(); } catch (e) { log('destroyTable', e); }
        }
        _state.table = null;
    }

    function cleanup() {
        _destroyTable();
        _state.iframe = null;
        _state.selKey = null;
        _state.annPanel = null;
        _state.comPanel = null;
        _state.selUid = null;
        _state.selRid = null;
        _state.xferBtn = null;
        _state.xferMsg = null;
        _state.activeRowEl = null;
        log('cleanup');
    }

    // hasSelection: hat die/der Nutzer:in aktuell einen Bericht geoeffnet?
    // (Build 479) Genutzt vom SSE-'changed'-Handler in cockpit.js, um einen
    // destruktiven Live-Reload dieser Sicht zu unterdruecken, solange ein
    // Bericht in Sichtung ist. Hintergrund: Das Oeffnen eines Berichts erzeugt
    // ueber /api/report/annotations ZWINGEND einen Lesebeleg im audit_log
    // (Grundregel 1 — der Beleg darf NICHT entfallen); die SSE meldet diesen
    // Ausschlag als 'changed'. Ein Reload wuerde die Auswahl verwerfen, und ein
    // automatisches Wieder-Auswaehlen wuerde erneut auditieren -> Endlosschleife.
    // Deshalb bleibt der Beleg erhalten und STATTDESSEN unterbleibt der Reload,
    // solange hasSelection() true liefert. _state.selKey wird beim Verlassen der
    // Sicht (cleanup) bzw. beim Neuaufbau (renderLectorate) auf null gesetzt.
    function hasSelection() { return _state.selKey !== null; }

    // --- Uebernahme "Bericht als Vorlage" (Build 475) --------------------
    // _setXferMsg: Rueckmeldezeile der Uebernahme setzen ('' leert). kind:
    // '' | 'err' | 'ok'. XSS-sicher (textContent).
    function _setXferMsg(text, kind) {
        if (!_state.xferMsg) { return; }
        _state.xferMsg.textContent = text || '';
        _state.xferMsg.className = 'aiw-lectorate-xfermsg'
            + (kind ? (' is-' + kind) : '');
    }

    // transferError: von cockpit.js gerufen, wenn der Entwurf NICHT geholt
    // werden konnte (Grundregel 1: kein stiller Fehlpfad). Reaktiviert den
    // Knopf, damit die supervisor:in es erneut versuchen kann.
    function transferError(msg) {
        _setXferMsg('Uebernahme fehlgeschlagen: ' + (msg || 'Fehler'), 'err');
        if (_state.xferBtn
            && _state.selUid !== null && _state.selRid !== null) {
            _state.xferBtn.disabled = false;
        }
    }

    // renderLectorate(mainEl, data, opts)
    //   data — Antwort von /api/reports (reports[], scope, ...).
    //   opts — { status?: 'submitted'|'approved'|'final'|'draft'|'alle',
    //            onSelect?: function(uid, rid){}   // Benachrichtigung (Logging)
    //          }
    // _tk / _mitHilfe (Build 553): gemeinsames Tabellen-Werkzeug + Hilfe-Anker
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

    // Baut: Kopf + Statusfilter + Auswahl-Liste + Vorschau-<iframe>.
    function renderLectorate(mainEl, data, opts) {
        opts = opts || {};
        var status = opts.status || 'submitted';
        log('renderLectorate', { status: status,
            count: (data && data.count) });

        // Vollstaendiger Neuaufbau (kein optimistisches UI, Grundregel 1).
        // Build 481: eine ggf. bestehende Tabulator-Instanz VOR dem Leeren des
        // Containers zerstoeren (verhindert haengende Instanzen/Listener). Im
        // Normalfall ruft cockpit.js:cleanupView bereits AIWCockpitLectorate.
        // cleanup() vor loadLectorate — dies ist die defensive Doppelabsicherung.
        _destroyTable();
        mainEl.innerHTML = '';
        _state.iframe = null;
        _state.selKey = null;
        _state.annPanel = null;
        _state.comPanel = null;
        _state.selUid = null;
        _state.selRid = null;
        _state.xferBtn = null;
        _state.xferMsg = null;
        _state.activeRowEl = null;

        var wrap = document.createElement('div');
        wrap.className = 'aiw-lectorate';

        var h = document.createElement('h2');
        h.textContent = 'Lektorat — Gegenlesen';
        // Build 598 (Baustelle H / H9): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'lectorate.titel');
        wrap.appendChild(h);

        // Scope-Hinweis (der Server filtert scope-korrekt; wir benennen ihn).
        var meta = document.createElement('p');
        meta.className = 'aiw-lectorate-meta';
        meta.setAttribute('data-hilfe-id', 'lectorate.umfang');
        meta.textContent = 'Sichtbarer Umfang: ' + ((data && data.scope)
            || 'unbekannt') + '. Vorgelegt zum Gegenlesen sind Berichte im '
            + 'Status „Zur Abnahme vorgelegt".';
        wrap.appendChild(meta);

        // --- Status-Vorbelegung (Build 484) ------------------------------
        // Der fruehere Status-<select> UEBER der Tabelle entfaellt. Die
        // Statusfilterung erfolgt jetzt ausschliesslich ueber den Dropdown-
        // Header-Filter der Status-Spalte (s. Spaltendefinition unten). Der
        // Default (Vorgabe 'submitted' bzw. opts.status) wird ueber Tabulators
        // initialHeaderFilter gesetzt; 'alle' => keine Vorbelegung (kein Filter).
        // Die Tabelle laedt daher ALLE Zeilen (toRows(..., 'alle')), damit ein
        // Statuswechsel im Header ohne Datenneuladen wirkt.
        var _initHF = [];
        if (status && status !== 'alle') {
            _initHF.push({ field: 'status_label', value: status });
        }

        // --- Vorschau-Bereich: Berichtstext (iframe) + Belege (Annotationen) -
        // Zuerst aufgebaut, damit der rowClick-Handler der Tabelle die
        // iframe-Referenz (frame) bereits schliessen kann.
        var preview = document.createElement('div');
        preview.className = 'aiw-lectorate-preview-wrap';

        var frame = document.createElement('iframe');
        frame.className = 'aiw-lectorate-preview';
        frame.title = 'Berichtstext (read-only)';
        frame.setAttribute('sandbox', 'allow-same-origin');
        _state.iframe = frame;

        var ann = document.createElement('div');
        ann.className = 'aiw-lectorate-annotations';
        _state.annPanel = ann;
        _annHint('Bericht in der Tabelle auswaehlen, um die zugrunde liegenden '
            + 'Belege zu sehen.');

        preview.appendChild(frame);
        preview.appendChild(ann);

        // --- Uebernahme-Leiste (Build 475): "Bericht als Vorlage uebernehmen".
        // Nur wenn der Aufrufer (cockpit.js) einen Callback liefert — das setzt
        // er ausschliesslich bei vorhandenem Recht templates.edit. Der Knopf ist
        // erst aktiv, sobald ein Bericht gewaehlt wurde (selUid/selRid gesetzt).
        // Build 482 (Slice 2): Die Leiste wird UNTER der Tabelle eingehaengt
        // (naeher an der Darstellung) — hier nur GEBAUT, Einhaengen s. unten.
        var xbar = null;
        var canTransfer = (typeof opts.onTransferToTemplate === 'function');
        if (canTransfer) {
            xbar = document.createElement('div');
            xbar.className = 'aiw-lectorate-xferbar';
            var xbtn = document.createElement('button');
            xbtn.type = 'button';
            xbtn.className = 'aiw-lectorate-xfer';
            xbtn.textContent = 'Als Vorlage uebernehmen';
            xbtn.disabled = true;   // erst nach Berichtsauswahl
            xbtn.title = 'Aus dem gewaehlten Bericht eine Dokumentvorlage '
                + 'erzeugen (fallbezogene Platzhalter-Werte werden entfernt).';
            xbtn.addEventListener('click', function () {
                if (_state.selUid === null || _state.selRid === null) { return; }
                _setXferMsg('Uebernehme Bericht in Vorlage …', '');
                xbtn.disabled = true;
                opts.onTransferToTemplate(_state.selUid, _state.selRid);
            });
            _state.xferBtn = xbtn;
            xbar.appendChild(xbtn);
            var xmsg = document.createElement('span');
            xmsg.className = 'aiw-lectorate-xfermsg';
            _state.xferMsg = xmsg;
            xbar.appendChild(xmsg);
        }

        // --- Auswahl-Tabelle (Build 481/482): Tabulator statt Button-Liste.
        // Muster cockpit_reports.js. opts.Tabulator ist fuer Tests injizierbar.
        var container = document.createElement('div');
        container.className = 'aiw-lectorate-table';
        wrap.appendChild(container);
        // Build 482: Uebernahme-Leiste UNTER der Tabelle (naeher an der Auswahl).
        if (xbar) { wrap.appendChild(xbar); }
        wrap.appendChild(preview);

        // _selectReport: gemeinsame Auswahl-Logik (rowClick). Merkt den Bericht,
        // aktiviert den Uebernahme-Knopf, laedt die read-only Vorschau und
        // stoesst ueber opts.onSelect die Belege-/Kommentar-Abrufe an. rowEl ist
        // die Zeilen-DOM (fuer die visuelle Markierung), optional.
        function _selectReport(r, rowEl) {
            if (!r) { return; }
            if (_state.activeRowEl && _state.activeRowEl.classList) {
                _state.activeRowEl.classList.remove('is-active');
            }
            if (rowEl && rowEl.classList) {
                rowEl.classList.add('is-active');
                _state.activeRowEl = rowEl;
            }
            _state.selKey = selectionKey(r.subject_id, r.id);
            _state.selUid = r.subject_id;
            _state.selRid = r.id;
            if (_state.xferBtn) {
                _state.xferBtn.disabled = false;
                _setXferMsg('', '');
            }
            frame.src = renderUrl(r.subject_id, r.id);
            annotationsLoading();
            commentsLoading();
            log('select', _state.selKey, frame.src);
            if (typeof opts.onSelect === 'function') {
                opts.onSelect(r.subject_id, r.id);
            }
        }

        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        var TK = _tk();
        if (typeof Ctor !== 'function' || !TK) {
            // Kein stiller Leerzustand (Grundregel 1): sichtbarer Hinweis —
            // Build 553 zusaetzlich MIT der Zahl. Ohne sie saehe der Ausfall
            // aus wie 'keine Berichte vorhanden'.
            var note = document.createElement('p');
            note.className = 'aiw-lectorate-empty aiw-placeholder';
            note.textContent = 'Tabellenbibliothek nicht verfügbar — es '
                + 'liegen ' + toRows(data, 'alle').length + ' Berichte vor.';
            container.appendChild(note);
            _state.table = null;
            log('renderLectorate: kein Tabulator-Ctor/TableKit');
        } else {
            // Build 553 (UX): Aufbau ueber das gemeinsame Tabellen-Werkzeug.
            // Werkzeugleiste, Trefferzahl, 'Filter zuruecksetzen', gesicherter
            // Bedienzustand und Hilfe-Anker kommen von dort.
            //
            // DIE HANDGESETZTEN FILTER BLEIBEN UNANGETASTET: spaltenMitFilter
            // fuellt nur Felder, die NICHT ausdruecklich gesetzt sind. Der exakte
            // Full-Match beim Typ (Build 486) und die Statusfilterung ueber den
            // ROH-Status (_statusHeaderFilter) haengen an dieser Sicht und duerfen
            // nicht von der Automatik ueberschrieben werden.
            //
            // Der Zeilenklick laeuft ueber onRowClick (tabelleAufbauen haengt ihn
            // ueber table.on an) — als Konstruktoroption wird er von Tabulator
            // v6.4.0 still ignoriert (Befund Build 486, im Werkzeug seit 551).
            _state.table = TK.tabelleAufbauen(document, container, {
                sicht: 'lectorate',
                rows: toRows(data, 'alle'),
                // Build 482/484: Kopffilter je Spalte. Benutzer/Titel/
                // Verfasser Freitext; Typ und Status als DROPDOWN (list) mit
                // festen Werten + 'alle' (leerer Wert => kein Filter).
                columns: _mitHilfe([
                        { title: 'Benutzer',  field: 'username',
                          headerFilter: 'input' },
                        { title: 'Titel',     field: 'title',
                          headerFilter: 'input' },
                        // Build 486: exakter Full-Match ('='), sonst wuerde der
                        // list-Default als Teilstring 'Vermerk' auch in
                        // 'Ergänzungsvermerk' finden.
                        { title: 'Typ',       field: 'typ',
                          headerFilter: 'list',
                          headerFilterParams: { values: TYP_FILTER_VALUES },
                          headerFilterFunc: '=' },
                        { title: 'Nr.',       field: 'nr', hozAlign: 'right' },
                        // Status: die Spalte ZEIGT status_label, FILTERT aber ueber
                        // den Roh-Status (rowData.status) — so bleibt 'Versandt'
                        // waehlbar, obwohl das Label 'Versandt/abgeschlossen' lautet.
                        { title: 'Status',    field: 'status_label',
                          headerFilter: 'list',
                          headerFilterParams: { values: STATUS_FILTER_VALUES },
                          headerFilterFunc: _statusHeaderFilter },
                        { title: 'Verfasser', field: 'created_by',
                          headerFilter: 'input' },
                        { title: 'Erstellt',  field: 'created' }
                ], 'lectorate', document),
                Ctor: Ctor,
                einheit: 'Berichte',
                onRowClick: function (e, row) {
                    var el = (typeof row.getElement === 'function')
                        ? row.getElement() : null;
                    _selectReport(row.getData(), el);
                },
                tabulator: {
                    // Build 484: Default-Statusfilter (Vorgabe 'submitted').
                    // ALLE Zeilen sind geladen; die Statusfilterung uebernimmt
                    // der Dropdown-Kopffilter der Status-Spalte, damit ein
                    // Statuswechsel ohne Neuladen wirkt.
                    initialHeaderFilter: _initHF,
                    // Build 482: Paginierung mit 20 Zeilen/Seite. height:false
                    // (kein maxHeight) — verhindert das dokumentierte Pager-Clipping
                    // (Beleg: userinfo.js buildTabulatorConfig, Console-Diagnose
                    // 2026-07-10). Deutscher Pager ueber locale/langs.
                    height: false,
                    pagination: 'local',
                    paginationSize: 20,
                    paginationCounter: 'rows',
                    locale: 'de-de',
                    langs: {
                        'de-de': {
                            pagination: {
                                first: 'Erste', first_title: 'Erste Seite',
                                last: 'Letzte', last_title: 'Letzte Seite',
                                prev: 'Zurück', prev_title: 'Vorige Seite',
                                next: 'Weiter', next_title: 'Nächste Seite',
                                counter: {
                                    showing: 'Zeige', of: 'von',
                                    rows: 'Zeilen', pages: 'Seiten'
                                }
                            }
                        }
                    },
                    // Kein stiller Leerzustand: sichtbarer Hinweis bei 0 Zeilen.
                    placeholder: 'Keine Berichte im gewaehlten Status.'
                }
            }).table;
        }

        // --- Kommentar-Panel (SF-3, Slice 3) unter dem Vorschau-Bereich. ----
        var com = document.createElement('div');
        com.className = 'aiw-lectorate-comments';
        _state.comPanel = com;
        _comHint('Bericht auswaehlen, um Kommentare zu sehen und zu erfassen.');
        wrap.appendChild(com);

        mainEl.appendChild(wrap);
        return wrap;
    }

    // --- Belege-Panel (SF-2) ---------------------------------------------

    // _annHint: setzt das Belege-Panel auf EINEN Hinweistext (ersetzt Inhalt).
    function _annHint(msg) {
        if (!_state.annPanel) { return; }
        _state.annPanel.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'aiw-lectorate-ann-hint';
        p.textContent = msg;
        _state.annPanel.appendChild(p);
    }

    // Ladehinweis waehrend der Abruf von /api/report/annotations laeuft.
    function annotationsLoading() { _annHint('Belege werden geladen …'); }

    // Fehlerhinweis (kein stiller Fehlpfad, Grundregel 1).
    function annotationsError(msg) {
        _annHint('Belege konnten nicht geladen werden: ' + (msg || 'Fehler'));
    }

    // renderAnnotations(data): baut das Belege-Panel aus der SF-2-Antwort
    // (data.items). Ohne aktives Panel (Sicht verlassen) ein No-op.
    function renderAnnotations(data) {
        var panel = _state.annPanel;
        if (!panel) { return; }
        panel.innerHTML = '';
        var items = (data && data.items) ? data.items : [];

        var head = document.createElement('h3');
        head.className = 'aiw-lectorate-ann-head';
        head.textContent = 'Belege (' + items.length + ')';
        panel.appendChild(head);

        if (!items.length) {
            var p = document.createElement('p');
            p.className = 'aiw-lectorate-ann-hint';
            p.textContent = 'Zu diesem Bericht sind keine Belege verankert.';
            panel.appendChild(p);
            return;
        }

        items.forEach(function (it) {
            var box = document.createElement('div');
            box.className = 'aiw-lectorate-ann-item';
            if (it.missing) { box.classList.add('is-missing'); }
            if (it.deleted) { box.classList.add('is-deleted'); }

            var cat = document.createElement('span');
            cat.className = 'aiw-lectorate-ann-cat';
            cat.textContent = categoryLabel(it.category);
            box.appendChild(cat);

            var txt = document.createElement('div');
            txt.className = 'aiw-lectorate-ann-text';
            // Fehlt die Annotation (Anker zeigt ins Leere) -> sichtbar machen.
            txt.textContent = it.missing
                ? '⚠ Beleg nicht (mehr) vorhanden (Annotation #'
                    + it.annotation_id + ')'
                : (it.text || '');
            box.appendChild(txt);

            var metaLine = document.createElement('div');
            metaLine.className = 'aiw-lectorate-ann-meta';
            var bits = [];
            if (it.post_id != null) { bits.push('Beitrag #' + it.post_id); }
            bits.push('Forum: ' + forumContext(it));
            if (it.block_id) {
                bits.push('Block ' + it.block_id
                    + (it.block_type ? ' (' + it.block_type + ')' : ''));
            }
            if (it.deleted) { bits.push('geloescht'); }
            metaLine.textContent = bits.join(' · ');
            box.appendChild(metaLine);

            panel.appendChild(box);
        });
    }

    // --- Kommentar-Panel (SF-3) ------------------------------------------

    // _comHint: setzt das Kommentar-Panel auf EINEN Hinweistext.
    function _comHint(msg) {
        if (!_state.comPanel) { return; }
        _state.comPanel.innerHTML = '';
        var p = document.createElement('p');
        p.className = 'aiw-lectorate-com-hint';
        p.textContent = msg;
        _state.comPanel.appendChild(p);
    }

    function commentsLoading() { _comHint('Kommentare werden geladen …'); }
    function commentsError(msg) {
        _comHint('Kommentar-Aktion fehlgeschlagen: ' + (msg || 'Fehler'));
    }

    // renderComments(data, opts): baut Formular (neuer Kommentar) + Liste der
    // vorhandenen Kommentare (Union aller Prueferinnen) in das Kommentar-Panel.
    //   data — Antwort von /api/report/comments {subject_id, report_id, comments[]}
    //   opts — { personId, onAdd(body), onResolve(body) }
    function renderComments(data, opts) {
        var panel = _state.comPanel;
        if (!panel) { return; }
        opts = opts || {};
        panel.innerHTML = '';
        var comments = (data && data.comments) ? data.comments : [];
        var uid = data ? data.subject_id : null;
        var rid = data ? data.report_id : null;

        var head = document.createElement('h3');
        head.className = 'aiw-lectorate-com-head';
        head.textContent = 'Kommentare (' + comments.length + ')';
        panel.appendChild(head);

        // --- Formular: neuen Kommentar erfassen --------------------------
        var form = document.createElement('form');
        form.className = 'aiw-lectorate-com-form';

        var ta = document.createElement('textarea');
        ta.className = 'aiw-lectorate-com-text';
        ta.setAttribute('rows', '2');
        ta.setAttribute('placeholder', 'Kommentar zum Bericht …');
        form.appendChild(ta);

        var blockIn = document.createElement('input');
        blockIn.type = 'text';
        blockIn.className = 'aiw-lectorate-com-block';
        blockIn.setAttribute('placeholder', 'Block-ID (optional)');
        form.appendChild(blockIn);

        var sug = document.createElement('textarea');
        sug.className = 'aiw-lectorate-com-suggest';
        sug.setAttribute('rows', '1');
        sug.setAttribute('placeholder', 'Aenderungsvorschlag (optional)');
        form.appendChild(sug);

        var submit = document.createElement('button');
        submit.type = 'submit';
        submit.className = 'aiw-lectorate-com-submit';
        submit.textContent = 'Kommentar hinzufuegen';
        form.appendChild(submit);

        var errBox = document.createElement('div');
        errBox.className = 'aiw-lectorate-com-formerr';
        form.appendChild(errBox);

        form.addEventListener('submit', function (ev) {
            ev.preventDefault();
            errBox.textContent = '';
            var text = (ta.value || '').trim();
            if (!text) {
                errBox.textContent = 'Bitte einen Kommentartext eingeben.';
                return;
            }
            var body = {
                subject_id: uid, report_id: rid,
                block_id: (blockIn.value || '').trim() || null,
                comment_text: text,
                suggested_content: (sug.value || '').trim() || null
            };
            log('addComment', body);
            if (typeof opts.onAdd === 'function') { opts.onAdd(body); }
        });
        panel.appendChild(form);

        // --- Liste vorhandener Kommentare --------------------------------
        if (!comments.length) {
            var none = document.createElement('p');
            none.className = 'aiw-lectorate-com-hint';
            none.textContent = 'Noch keine Kommentare zu diesem Bericht.';
            panel.appendChild(none);
            return;
        }

        comments.forEach(function (c) {
            var box = document.createElement('div');
            box.className = 'aiw-lectorate-com-item';
            box.setAttribute('data-status', c.status || '');
            if (c.status && c.status !== 'pending') {
                box.classList.add('is-resolved');
            }

            var top = document.createElement('div');
            top.className = 'aiw-lectorate-com-top';
            var role = document.createElement('span');
            role.className = 'aiw-lectorate-com-role';
            role.textContent = reviewerRoleLabel(c.reviewer_role);
            top.appendChild(role);
            var st = document.createElement('span');
            st.className = 'aiw-lectorate-com-status';
            st.textContent = commentStatusLabel(c.status);
            top.appendChild(st);
            box.appendChild(top);

            var body = document.createElement('div');
            body.className = 'aiw-lectorate-com-body';
            body.textContent = c.comment_text || '';
            box.appendChild(body);

            if (c.suggested_content) {
                var sugv = document.createElement('div');
                sugv.className = 'aiw-lectorate-com-suggestion';
                sugv.textContent = 'Vorschlag: ' + c.suggested_content;
                box.appendChild(sugv);
            }

            var meta = document.createElement('div');
            meta.className = 'aiw-lectorate-com-meta';
            var mbits = [];
            if (c.block_id) { mbits.push('Block ' + c.block_id); }
            mbits.push('Prueferin #' + c.reviewer_pid);
            meta.textContent = mbits.join(' · ');
            box.appendChild(meta);

            // Aufloesen NUR fuer eigene, offene Kommentare (Server erzwingt es
            // strukturell; das UI zeigt die Knoepfe nur, wo sie wirken).
            if (isOwnComment(c, opts.personId) && c.status === 'pending') {
                var actions = document.createElement('div');
                actions.className = 'aiw-lectorate-com-actions';
                [['addressed', 'Als erledigt'], ['dismissed', 'Verwerfen']]
                    .forEach(function (a) {
                        var btn = document.createElement('button');
                        btn.type = 'button';
                        btn.className = 'aiw-lectorate-com-resolve';
                        btn.setAttribute('data-status', a[0]);
                        btn.textContent = a[1];
                        btn.addEventListener('click', function () {
                            var rb = { subject_id: uid, comment_id: c.comment_id,
                                       status: a[0] };
                            log('resolveComment', rb);
                            if (typeof opts.onResolve === 'function') {
                                opts.onResolve(rb);
                            }
                        });
                        actions.appendChild(btn);
                    });
                box.appendChild(actions);
            }

            panel.appendChild(box);
        });
    }

    // --- oeffentliche API -------------------------------------------------
    window.AIWCockpitLectorate = {
        // Build 553: die Tabulator-Instanz nach aussen. renderLectorate gibt
        // das Wrapper-Element zurueck, nicht die Tabelle — ohne diesen Zugang
        // koennte die Konformitaetssuite die Sicht nicht pruefen, und ein
        // Aufraeumen beim Sichtwechsel muesste raten.
        getTable: function () { return _state.table; },
        // reine Funktionen (vitest)
        statusLabel: statusLabel,
        filterReports: filterReports,
        renderUrl: renderUrl,
        reportLabel: reportLabel,
        selectionKey: selectionKey,
        toRows: toRows,                   // Tabellen-Abbildung (Build 481)
        typeLabel: typeLabel,             // Berichtstyp-Label (Build 481)
        statusFilter: _statusHeaderFilter,   // Status-Dropdown-Filter (Build 484)
        annotationsUrl: annotationsUrl,   // SF-2 (Build 414)
        categoryLabel: categoryLabel,
        forumContext: forumContext,
        commentsUrl: commentsUrl,         // SF-3 (Build 415)
        commentStatusLabel: commentStatusLabel,
        reviewerRoleLabel: reviewerRoleLabel,
        isOwnComment: isOwnComment,
        // DOM
        renderLectorate: renderLectorate,
        renderAnnotations: renderAnnotations,   // Belege-Panel (SF-2)
        annotationsLoading: annotationsLoading,
        annotationsError: annotationsError,
        renderComments: renderComments,         // Kommentar-Panel (SF-3)
        commentsLoading: commentsLoading,
        commentsError: commentsError,
        transferError: transferError,           // Uebernahme B6->Vorlage (Build 475)
        hasSelection: hasSelection,             // SSE-Reload-Schutz (Build 479)
        cleanup: cleanup
    };
    log('Modul geladen.');
})();
