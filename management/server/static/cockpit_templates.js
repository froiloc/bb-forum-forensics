/**
 * management/server/static/cockpit_templates.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Vermaehlung B6xB7 — W2 (Platzhalter & Queries), FRONTEND (Build 423)
 *
 * Zweck:
 *   Autoren-Sicht der Redakteur:in (Recht templates.edit): Einzeldaten-
 *   Platzhalter-Queries (templates.db.placeholder_queries) LISTEN, ANLEGEN und
 *   AENDERN. Kernstueck ist die Editor-Maske mit einem SCHREIBFREIEN Dry-Run:
 *   die Query kann gegen eine Beispiel-forensic_<uid>.db getestet werden, BEVOR
 *   sie gespeichert wird (Grundregel: Ueberpruefbarkeit; keine stille
 *   Fehlaufloesung). Das eigentliche Speichern laeuft ueber den auditierten
 *   Schreibpfad (POST /api/templates/query -> TemplatesWriter, Build 421/422).
 *
 *   Backend-Endpunkte (Build 422/423):
 *     GET  /api/templates/queries       — Liste
 *     POST /api/templates/query         — anlegen/aendern (auditiert)
 *     POST /api/templates/query/dryrun  — schreibfreie Vorschau (Validierung +
 *                                         fdb-Dry-Run), liefert {ok,errors,dry_run}
 *
 * Warum ':uid' der einzige Parameter der Query ist: der AutoQueryResolver
 *   (report_render/auto_query.py) fuehrt die Query mit exakt {"uid":<user_id>}
 *   aus. Das spiegeln wir im Hinweistext der Maske, damit die Autor:in es sofort
 *   sieht (der Server erzwingt es zusaetzlich, Build 422).
 *
 * JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging (DEV=false fuer
 *   PROD); ausfuehrliche Kommentare; Kapselung (Closure-Zustand, kleine API);
 *   REINE Funktionen separat exportiert (vitest). XSS-sicher: variable Texte
 *   ausschliesslich via textContent/value (die Query kann beliebige Zeichen und
 *   Sprachen enthalten — multilinguales Forum).
 *
 * Version: v0.7.423 · Build: 423 · 2026-07-14
 */
(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // DEV-Logging: in der Entwicklung sehr gespraechig, fuer PROD per DEV=false
    // vollstaendig stumm (kein console-Rauschen im Produktivbetrieb).
    // -------------------------------------------------------------------------
    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[templates]');
            console.log.apply(console, a);
        }
    }

    // Closure-Zustand der Sicht (gekapselt; NUR ueber cleanup() geloest).
    var _state = {
        listEl: null,     // Container der Query-Liste (links)
        fields: null,     // Referenzen auf die Formularfelder
        msgEl: null,      // Rueckmeldezeile (Speichern-Ergebnis/-Fehler)
        dryEl: null,      // Ausgabebereich des Dry-Run
        selId: null       // aktuell im Editor geladene id (null = Neu-Modus)
    };

    // id-Zeichenraum — DECKUNGSGLEICH mit dem Server (query_validator._ID_RE)
    // und der Chip-Regex des Berichtseditors. Nur damit ist der Platzhalter
    // ueberhaupt aufloesbar; die Client-Pruefung ist reine Bequemlichkeit, die
    // Autoritaet liegt beim Server (Build 422).
    var _ID_RE = /^[A-Za-z0-9._-]+$/;

    // =====================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — genau diese testet vitest.
    // =====================================================================

    // returnTypeLabel: Klartext zum return_type (Fallback: der Rohwert).
    function returnTypeLabel(rt) {
        switch (rt) {
            case 'scalar': return 'Einzelwert (scalar)';
            case 'list':   return 'Liste (list)';
            case 'table':  return 'Tabelle (table)';
            default:       return rt || 'scalar';
        }
    }

    // queryLabel: Anzeigetext eines Listeneintrags: "Titel (id)". Faellt bei
    // fehlendem Titel auf die id zurueck, damit nie ein leerer Eintrag entsteht.
    function queryLabel(q) {
        if (!q) { return '?'; }
        var id = (q.id === undefined || q.id === null) ? '' : String(q.id);
        var title = (q.title === undefined || q.title === null)
            ? '' : String(q.title);
        if (title && id) { return title + ' (' + id + ')'; }
        return title || id || '?';
    }

    // sortQueries: neue, nach id (case-insensitive) sortierte Liste. Mutiert die
    // Eingabe NICHT (die Server-Liste bleibt unveraendert).
    function sortQueries(list) {
        var arr = (list || []).slice();
        arr.sort(function (a, b) {
            var ai = String((a && a.id) || '').toLowerCase();
            var bi = String((b && b.id) || '').toLowerCase();
            if (ai < bi) { return -1; }
            if (ai > bi) { return 1; }
            return 0;
        });
        return arr;
    }

    // isValidId: Client-Spiegel der Server-Regel (Bequemlichkeit).
    function isValidId(id) {
        return _ID_RE.test(String(id || ''));
    }

    // buildPayload: baut den POST-Body aus den (rohen) Feldwerten. REIN und
    // testbar. Trimmt id/title/sql; description bleibt wie eingegeben (leerer
    // String erlaubt, NULL nicht — der Server erzwingt es). test_user_id wird
    // nur uebernommen, wenn nicht leer (sonst kein Dry-Run).
    function buildPayload(fields) {
        var f = fields || {};
        var payload = {
            id: String(f.id || '').trim(),
            title: String(f.title || '').trim(),
            description: (f.description === undefined || f.description === null)
                ? '' : String(f.description),
            sql_query: String(f.sql_query || '').trim(),
            return_type: f.return_type || 'scalar'
        };
        var tags = f.tags;
        if (tags !== undefined && tags !== null && String(tags).trim() !== '') {
            payload.tags = String(tags).trim();
        }
        var tu = f.test_user_id;
        if (tu !== undefined && tu !== null && String(tu).trim() !== '') {
            payload.test_user_id = String(tu).trim();
        }
        return payload;
    }

    // errorsText: Fehlerliste zu einer Zeile verdichten ('' bei keiner).
    function errorsText(errors) {
        if (!errors || !errors.length) { return ''; }
        return errors.join('; ');
    }

    // dryRunSummary: menschenlesbare Zusammenfassung des Dry-Run-Ergebnisses.
    // Deckt drei Faelle ab: (a) nicht gelaufen (ran=false -> Grund), (b) gelaufen
    // mit Beispielwert, (c) gelaufen ohne Zeile. REIN und testbar.
    function dryRunSummary(res) {
        if (!res || res.ran !== true) {
            var reason = (res && res.reason) ? res.reason
                : 'Dry-Run nicht ausgefuehrt.';
            return 'Kein Dry-Run: ' + reason;
        }
        var cols = (res.columns === undefined || res.columns === null)
            ? '?' : String(res.columns);
        if (res.sample === undefined || res.sample === null) {
            return 'Dry-Run OK — ' + cols
                + ' Spalte(n), aber keine Beispielzeile (leeres Ergebnis).';
        }
        return 'Dry-Run OK — ' + cols + ' Spalte(n); Beispielwert: '
            + String(res.sample);
    }

    // =====================================================================
    // 2) DOM-FUNKTIONEN (nur Browser/jsdom).
    // =====================================================================

    // _clearNode: Kindelemente eines Knotens leeren (XSS-sicher, kein innerHTML).
    function _clearNode(el) {
        if (el) { el.textContent = ''; }
    }

    // _labeledField: erzeugt <label>Text<input/textarea/select></label> und gibt
    // das Eingabeelement zurueck. 'kind' waehlt den Feldtyp.
    function _labeledField(parent, labelText, kind, className) {
        var lab = document.createElement('label');
        lab.className = 'aiw-tpl-field';
        var span = document.createElement('span');
        span.className = 'aiw-tpl-label';
        span.textContent = labelText;
        lab.appendChild(span);
        var input;
        if (kind === 'textarea') {
            input = document.createElement('textarea');
            input.rows = 6;
        } else if (kind === 'select') {
            input = document.createElement('select');
        } else {
            input = document.createElement('input');
            input.type = (kind === 'number') ? 'number' : 'text';
        }
        input.className = className;
        lab.appendChild(input);
        parent.appendChild(lab);
        return input;
    }

    // _fillForm: die Formularfelder aus einer Query fuellen (Editier-Modus) oder
    // leeren (Neu-Modus, q=null). Setzt _state.selId entsprechend.
    function _fillForm(q) {
        var f = _state.fields;
        if (!f) { return; }
        if (q) {
            f.id.value = (q.id === undefined || q.id === null) ? '' : String(q.id);
            f.id.disabled = true;   // id ist der Schluessel — im Editier-Modus fix
            f.title.value = q.title || '';
            f.description.value = q.description || '';
            f.sql_query.value = q.sql_query || '';
            f.return_type.value = q.return_type || 'scalar';
            f.tags.value = q.tags || '';
            _state.selId = String(q.id);
        } else {
            f.id.value = '';
            f.id.disabled = false;  // Neu-Modus: id ist einzugeben
            f.title.value = '';
            f.description.value = '';
            f.sql_query.value = '';
            f.return_type.value = 'scalar';
            f.tags.value = '';
            _state.selId = null;
        }
        _setMsg('');
        renderDryRun(null);
        _markActive();
    }

    // _currentFields: die aktuellen (rohen) Feldwerte als flaches Objekt lesen.
    function _currentFields() {
        var f = _state.fields;
        return {
            id: f.id.value,
            title: f.title.value,
            description: f.description.value,
            sql_query: f.sql_query.value,
            return_type: f.return_type.value,
            tags: f.tags.value,
            test_user_id: f.test_user_id.value
        };
    }

    // _markActive: den zur _state.selId gehoerenden Listeneintrag hervorheben.
    function _markActive() {
        if (!_state.listEl) { return; }
        var items = _state.listEl.querySelectorAll('.aiw-tpl-item');
        Array.prototype.forEach.call(items, function (it) {
            var on = (_state.selId !== null
                && it.getAttribute('data-id') === _state.selId);
            it.classList.toggle('is-active', on);
        });
    }

    // _setMsg: Rueckmeldezeile setzen. 'kind' faerbt (ok/err/'' neutral).
    function _setMsg(text, kind) {
        if (!_state.msgEl) { return; }
        _state.msgEl.textContent = text || '';
        _state.msgEl.className = 'aiw-tpl-msg'
            + (kind ? (' is-' + kind) : '');
    }

    // renderDryRun: Ergebnis der schreibfreien Vorschau anzeigen. res=null leert
    // den Bereich. Zeigt zuerst etwaige Validierungs-/Dry-Run-FEHLER (rot), sonst
    // die Erfolgs-Zusammenfassung (Grundregel 1: Fehler nie still schlucken).
    function renderDryRun(res) {
        var box = _state.dryEl;
        if (!box) { return; }
        _clearNode(box);
        if (!res) { return; }
        var errs = errorsText(res.errors);
        if (errs) {
            var pe = document.createElement('p');
            pe.className = 'aiw-tpl-dry is-err';
            pe.textContent = 'Nicht gueltig: ' + errs;
            box.appendChild(pe);
            return;
        }
        var ps = document.createElement('p');
        ps.className = 'aiw-tpl-dry is-ok';
        ps.textContent = dryRunSummary(res.dry_run);
        box.appendChild(ps);
    }

    // dryRunError: Transportfehler des Dry-Run sichtbar machen.
    function dryRunError(msg) {
        var box = _state.dryEl;
        if (!box) { return; }
        _clearNode(box);
        var p = document.createElement('p');
        p.className = 'aiw-tpl-dry is-err';
        p.textContent = 'Dry-Run fehlgeschlagen: ' + (msg || 'unbekannt');
        box.appendChild(p);
    }

    // saved: erfolgreiche Speicherung melden (created=neu/geaendert).
    function saved(res) {
        var created = !!(res && res.created);
        var tid = (res && res.target_id) ? res.target_id : '?';
        _setMsg('Query "' + tid + '" '
            + (created ? 'angelegt.' : 'geaendert.'), 'ok');
    }

    // saveError: Speicherfehler (inkl. Server-Validierung) sichtbar machen.
    function saveError(msg) {
        _setMsg('Speichern fehlgeschlagen: ' + (msg || 'unbekannt'), 'err');
    }

    // renderTemplates: Gesamtsicht aufbauen. data = {count, queries}. opts:
    //   onDryRun(payload)  — schreibfreie Vorschau ausloesen (cockpit.js -> POST)
    //   onSave(payload)    — auditiertes Speichern ausloesen (cockpit.js -> POST)
    // Aufbau: links die Liste + "Neu", rechts die Editor-Maske.
    function renderTemplates(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        _clearNode(mainEl);

        var wrap = document.createElement('div');
        wrap.className = 'aiw-tpl-wrap';

        // Kopf.
        var h = document.createElement('h2');
        h.className = 'aiw-pagetitle';
        h.textContent = 'Platzhalter & Queries';
        wrap.appendChild(h);
        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = 'Einzeldaten-Platzhalter fuer Berichte pflegen. '
            + 'Jede Query darf NUR lesen (SELECT/WITH) und ausschliesslich den '
            + 'Parameter :uid verwenden. Vor dem Speichern mit "Dry-Run" gegen '
            + 'eine Beispiel-Nutzer-ID testen.';
        wrap.appendChild(sub);

        // Zweispaltiger Koerper.
        var body = document.createElement('div');
        body.className = 'aiw-tpl-body';

        // --- Linke Spalte: Liste + "Neu".
        var left = document.createElement('div');
        left.className = 'aiw-tpl-listcol';
        var newBtn = document.createElement('button');
        newBtn.type = 'button';
        newBtn.className = 'aiw-btn aiw-tpl-new';
        newBtn.textContent = '+ Neue Query';
        newBtn.addEventListener('click', function () { _fillForm(null); });
        left.appendChild(newBtn);

        var list = document.createElement('div');
        list.className = 'aiw-tpl-list';
        _state.listEl = list;
        var rows = sortQueries(data && data.queries);
        if (!rows.length) {
            var empty = document.createElement('p');
            empty.className = 'aiw-tpl-empty';
            empty.textContent = 'Noch keine Queries angelegt.';
            list.appendChild(empty);
        }
        rows.forEach(function (q) {
            var it = document.createElement('button');
            it.type = 'button';
            it.className = 'aiw-tpl-item';
            it.setAttribute('data-id', String(q.id));
            it.textContent = queryLabel(q);
            it.addEventListener('click', function () { _fillForm(q); });
            list.appendChild(it);
        });
        left.appendChild(list);
        body.appendChild(left);

        // --- Rechte Spalte: Editor-Maske.
        var form = document.createElement('div');
        form.className = 'aiw-tpl-form';

        var fId = _labeledField(form, 'id (A-Z a-z 0-9 . _ -)', 'text',
            'aiw-tpl-id');
        var fTitle = _labeledField(form, 'Titel', 'text', 'aiw-tpl-title');
        var fDesc = _labeledField(form, 'Beschreibung', 'textarea',
            'aiw-tpl-desc');
        fDesc.rows = 2;
        var fSql = _labeledField(form, 'SQL (SELECT ... :uid ...)', 'textarea',
            'aiw-tpl-sql');
        var fRt = _labeledField(form, 'Rueckgabetyp', 'select', 'aiw-tpl-rt');
        [['scalar', returnTypeLabel('scalar')],
         ['list', returnTypeLabel('list')],
         ['table', returnTypeLabel('table')]].forEach(function (o) {
            var opt = document.createElement('option');
            opt.value = o[0];
            opt.textContent = o[1];
            fRt.appendChild(opt);
        });
        var fTags = _labeledField(form, 'Tags (optional)', 'text',
            'aiw-tpl-tags');

        // Dry-Run-Zeile: Beispiel-Nutzer-ID + Button.
        var dryRow = document.createElement('div');
        dryRow.className = 'aiw-tpl-dryrow';
        var fTest = _labeledField(dryRow, 'Beispiel-Nutzer-ID (:uid) fuer Dry-Run',
            'number', 'aiw-tpl-testuid');
        var dryBtn = document.createElement('button');
        dryBtn.type = 'button';
        dryBtn.className = 'aiw-btn aiw-tpl-drybtn';
        dryBtn.textContent = 'Dry-Run (schreibfrei)';
        dryRow.appendChild(dryBtn);
        form.appendChild(dryRow);

        // Ausgabebereich des Dry-Run.
        var dry = document.createElement('div');
        dry.className = 'aiw-tpl-dryout';
        _state.dryEl = dry;
        form.appendChild(dry);

        // Aktionszeile: Speichern + Rueckmeldung.
        var actions = document.createElement('div');
        actions.className = 'aiw-tpl-actions';
        var saveBtn = document.createElement('button');
        saveBtn.type = 'button';
        saveBtn.className = 'aiw-btn aiw-tpl-save';
        saveBtn.textContent = 'Speichern (auditiert)';
        actions.appendChild(saveBtn);
        var msg = document.createElement('span');
        msg.className = 'aiw-tpl-msg';
        _state.msgEl = msg;
        actions.appendChild(msg);
        form.appendChild(actions);

        body.appendChild(form);
        wrap.appendChild(body);
        mainEl.appendChild(wrap);

        // Feld-Referenzen buendeln (fuer _fillForm/_currentFields).
        _state.fields = {
            id: fId, title: fTitle, description: fDesc, sql_query: fSql,
            return_type: fRt, tags: fTags, test_user_id: fTest
        };

        // Handler verdrahten.
        dryBtn.addEventListener('click', function () {
            _setMsg('');
            if (typeof opts.onDryRun === 'function') {
                opts.onDryRun(buildPayload(_currentFields()));
            }
        });
        saveBtn.addEventListener('click', function () {
            renderDryRun(null);
            if (typeof opts.onSave === 'function') {
                opts.onSave(buildPayload(_currentFields()));
            }
        });

        // Startzustand: Neu-Modus (leeres Formular).
        _fillForm(null);
        log('renderTemplates:', rows.length, 'Queries');
        return wrap;
    }

    // cleanup: interne Referenzen loesen (verhindert Leaks beim Sichtwechsel).
    function cleanup() {
        _state.listEl = null;
        _state.fields = null;
        _state.msgEl = null;
        _state.dryEl = null;
        _state.selId = null;
    }

    // -------------------------------------------------------------------------
    // OEFFENTLICHE API. Reine Funktionen zuerst (vitest), dann DOM.
    // -------------------------------------------------------------------------
    window.AIWCockpitTemplates = {
        // reine Funktionen (vitest)
        returnTypeLabel: returnTypeLabel,
        queryLabel: queryLabel,
        sortQueries: sortQueries,
        isValidId: isValidId,
        buildPayload: buildPayload,
        errorsText: errorsText,
        dryRunSummary: dryRunSummary,
        // DOM
        renderTemplates: renderTemplates,
        renderDryRun: renderDryRun,
        dryRunError: dryRunError,
        saved: saved,
        saveError: saveError,
        cleanup: cleanup
    };
})();
