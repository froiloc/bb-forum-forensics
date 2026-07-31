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
 *   (report_render/auto_query.py) fuehrt die Query mit exakt {"uid":<subject_id>}
 *   aus. Das spiegeln wir im Hinweistext der Maske, damit die Autor:in es sofort
 *   sieht (der Server erzwingt es zusaetzlich, Build 422).
 *
 * JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging (DEV=false fuer
 *   PROD); ausfuehrliche Kommentare; Kapselung (Closure-Zustand, kleine API);
 *   REINE Funktionen separat exportiert (vitest). XSS-sicher: variable Texte
 *   ausschliesslich via textContent/value (die Query kann beliebige Zeichen und
 *   Sprachen enthalten — multilinguales Forum).
 *
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Build 488: Browser-Zwischenspeicher (localStorage) des NICHT gespeicherten
 *   Editor-Entwurfs (analog Dokumentvorlagen Build 487): jede Nutzer-Eingabe
 *   wird gesichert, beim Betreten/Neuladen wiederhergestellt, nach erfolgreichem
 *   Speichern verworfen. Eigener Schluessel DRAFT_KEY, nur Client, migrationsneutral.
 * Build 490 (Platzhalter-Neuordnung, Slice 2 — Bauplan Platzhalter_DB v0.1,
 *   mc 2026-07-21): Die Maske verwaltet jetzt ALLE drei Platzhalter-Typen aus
 *   templates.db.placeholders (Backend Build 489):
 *     - Typ-Dropdown 'automatisch {{a:}}' / 'verpflichtend {{m:}}' /
 *       'optional {{o:}}';
 *     - Feldlogik je Typ: SQL bei 'a' Pflicht, bei m/o optionale Default-
 *       Quelle; default_value + Validierungsblock NUR bei m/o; return_type bei
 *       m/o fest 'scalar' (Serverregel gespiegelt);
 *     - Validierungsblock: validation_type (regex [JAVASCRIPT-Dialekt/
 *       ECMAScript] | list [JSON-Array] | like [%/_]) + Klartext-Textarea,
 *       LIVE-Gueltigkeitspruefung (new RegExp in try/catch — hier liegt die
 *       verbindliche Regex-Syntaxpruefung, der Server prueft nur best-effort
 *       mit Python-re und warnt) + TESTFELD (Beispiel-Eingabe live gegen die
 *       Regel geprueft). Base64 ist hier NICHT im Spiel: die DB speichert
 *       Klartext; kodiert wird erst im Token-Transport (mc-Entscheid §2.2).
 *   Routen: GET /api/templates/placeholders, POST /api/templates/placeholder
 *   (+/dryrun) — die Legacy-Aliase aus 489 entfallen serverseitig mit diesem
 *   Build. Entwurfs-Zwischenspeicher auf v2 (neue Felder).
 * Build 497 (Case-Insensitivity): Validierungsblock erhaelt einen Schalter
 *   'Gross-/Kleinschreibung ignorieren' (validation_ci, 0/1) fuer regex/list/like.
 *   buildPayload/_currentFields/_fillForm/_restoreDraft/testRule/likeToRegExp
 *   beruecksichtigen ihn; deckungsgleich zu validation_rules.js (Ermittler) und
 *   Server. Beleg: mc 2026-07-22.
 * Version: v0.8.497 · Build: 497 · 2026-07-22
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
        selId: null,      // aktuell im Editor geladene id (null = Neu-Modus)
        typeUi: null      // Build 490: {apply()} — Feldlogik je Typ (a/m/o)
    };

    // Build 488: Browser-Zwischenspeicher (localStorage) des NOCH NICHT
    // gespeicherten Editor-Entwurfs (analog Dokumentvorlagen, Build 487) — ein
    // Neuladen/Fensterwechsel verliert keine unerledigte Arbeit. EIGENER,
    // versionierter Schluessel je Sicht. Nur Client-seitig, keine DB, kein
    // Beleg-/Evidence-Bezug (migrationsneutral).
    // Build 490: v2 — Entwurf traegt zusaetzlich type/default_value/validation/
    // validation_type. Alte v1-Entwuerfe werden bewusst ignoriert (anderer
    // Schluessel), statt sie fehlerhaft zu deuten.
    var DRAFT_KEY = 'aiw.templates.draft.v2';

    // _ls: sicherer Zugriff auf localStorage (Privat-Modus/Quota -> null, Feature
    // still deaktiviert, kein Crash).
    function _ls() {
        try {
            return (typeof localStorage !== 'undefined') ? localStorage : null;
        } catch (e) { return null; }
    }

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

    // typeLabel (Build 490): menschliche Typbezeichnung inkl. Token-Syntax.
    function typeLabel(t) {
        switch (t) {
            case 'a': return 'automatisch {{a:}}';
            case 'm': return 'verpflichtend {{m:}}';
            case 'o': return 'optional {{o:}}';
            default:  return t || '?';
        }
    }

    // queryLabel: Anzeigetext eines Listeneintrags: "[typ] Titel (id)". Faellt
    // bei fehlendem Titel auf die id zurueck, damit nie ein leerer Eintrag
    // entsteht. Build 490: Typ-Praefix, damit a/m/o in der Liste unterscheidbar
    // sind (fehlender Typ -> kein Praefix, kein stilles '[a]'-Raten).
    function queryLabel(q) {
        if (!q) { return '?'; }
        var id = (q.id === undefined || q.id === null) ? '' : String(q.id);
        var title = (q.title === undefined || q.title === null)
            ? '' : String(q.title);
        var base = (title && id) ? (title + ' (' + id + ')')
            : (title || id || '?');
        return q.type ? ('[' + q.type + '] ' + base) : base;
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
    // String erlaubt, NULL nicht — der Server erzwingt es). test_subject_id wird
    // nur uebernommen, wenn nicht leer (sonst kein Dry-Run).
    function buildPayload(fields) {
        var f = fields || {};
        var ptype = f.type || 'a';
        var payload = {
            id: String(f.id || '').trim(),
            title: String(f.title || '').trim(),
            description: (f.description === undefined || f.description === null)
                ? '' : String(f.description),
            type: ptype,
            sql_query: String(f.sql_query || '').trim(),
            // Build 490: m/o strikt 'scalar' (Serverregel gespiegelt — die
            // Default-Quelle liefert genau EINEN Wert).
            return_type: (ptype === 'a') ? (f.return_type || 'scalar')
                : 'scalar'
        };
        // Build 490: default_value + Validierung nur bei m/o; bei 'a' werden
        // sie NICHT gesendet (der Server lehnte eine a-Validierung ohnehin ab).
        if (ptype !== 'a') {
            var dv = f.default_value;
            if (dv !== undefined && dv !== null && String(dv).trim() !== '') {
                payload.default_value = String(dv);
            }
            var val = String(f.validation || '');
            var vt = String(f.validation_type || '');
            if (val.trim() !== '' && vt !== '') {
                payload.validation = val;
                payload.validation_type = vt;
                // Build 497: case-insensitive-Flag (0/1) — nur paarweise mit
                // einer aktiven Validierung sinnvoll.
                payload.validation_ci = f.validation_ci ? 1 : 0;
            }
        }
        var tags = f.tags;
        if (tags !== undefined && tags !== null && String(tags).trim() !== '') {
            payload.tags = String(tags).trim();
        }
        var tu = f.test_subject_id;
        if (tu !== undefined && tu !== null && String(tu).trim() !== '') {
            payload.test_subject_id = String(tu).trim();
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

    // --- Validierungsregeln (Build 490) ----------------------------------
    // Alle drei Pruefarten laufen CLIENTSEITIG im JavaScript-Dialekt — genau
    // die Umgebung, in der auch der Berichts-Editor (Wizard) prueft. Fuer
    // 'regex' ist DIES die verbindliche Syntaxpruefung (der Server prueft nur
    // best-effort mit Python-re und WARNT; Beleg placeholder_validator.py).

    // likeToRegExp: SQL-LIKE-Muster -> verankerte RegExp. % = beliebig viele
    // Zeichen, _ = genau ein Zeichen; alles andere woertlich (escaped).
    // Build 497: ci=true -> RegExp-Flag 'i' (case-insensitive).
    function likeToRegExp(pattern, ci) {
        var esc = String(pattern == null ? '' : pattern)
            .replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
            .replace(/%/g, '[\\s\\S]*')
            .replace(/_/g, '[\\s\\S]');
        return new RegExp('^' + esc + '$', ci ? 'i' : '');
    }

    // validateRule: ist die Regel SELBST gueltig? -> {ok, error}.
    //   regex — new RegExp(...) in try/catch (ECMAScript-Dialekt);
    //   list  — nicht-leeres JSON-Array aus Strings;
    //   like  — nicht leer.
    // Leere Regel + leere Art gelten als 'keine Regel' (ok).
    function validateRule(vtype, rule) {
        var v = String(vtype || '');
        var r = String(rule == null ? '' : rule);
        if (v === '' && r.trim() === '') { return { ok: true, error: null }; }
        if (v === '' || r.trim() === '') {
            return { ok: false, error: 'Pruefart und Regel gehoeren '
                + 'zusammen — bitte beides angeben.' };
        }
        if (v === 'regex') {
            try { new RegExp(r); return { ok: true, error: null }; }
            catch (e) {
                return { ok: false, error: 'Regex ungueltig (JavaScript-'
                    + 'Dialekt): ' + (e && e.message) };
            }
        }
        if (v === 'list') {
            var parsed;
            try { parsed = JSON.parse(r); }
            catch (e) {
                return { ok: false, error: 'Kein gueltiges JSON: '
                    + (e && e.message) };
            }
            if (!Array.isArray(parsed) || !parsed.length) {
                return { ok: false, error: 'list erwartet ein NICHT-leeres '
                    + 'JSON-Array erlaubter Werte.' };
            }
            for (var i = 0; i < parsed.length; i++) {
                if (typeof parsed[i] !== 'string') {
                    return { ok: false, error: 'list darf nur Zeichenketten '
                        + 'enthalten.' };
                }
            }
            return { ok: true, error: null };
        }
        if (v === 'like') {
            if (!r.trim()) {
                return { ok: false, error: 'like-Muster darf nicht leer sein.' };
            }
            return { ok: true, error: null };
        }
        return { ok: false, error: 'Unbekannte Pruefart: ' + v };
    }

    // testRule: prueft eine BEISPIEL-Eingabe gegen die Regel ->
    // {ok, match, error}. ok=false, wenn die Regel selbst ungueltig ist.
    //   regex — RegExp.test() (Anker ^/$ setzt die Autor:in selbst);
    //   list  — exakte Mitgliedschaft im Array;
    //   like  — verankertes LIKE-Muster (Full-Match).
    // Build 497: ci (validation_ci) -> case-insensitive fuer regex/list/like.
    function testRule(vtype, rule, sample, ci) {
        var chk = validateRule(vtype, rule);
        if (!chk.ok) { return { ok: false, match: null, error: chk.error }; }
        var v = String(vtype || '');
        var s = String(sample == null ? '' : sample);
        var insens = !!ci;
        if (v === '') { return { ok: true, match: null, error: null }; }
        if (v === 'regex') {
            return { ok: true,
                     match: new RegExp(String(rule), insens ? 'i' : '').test(s),
                     error: null };
        }
        if (v === 'list') {
            var needle = insens ? s.toLowerCase() : s;
            var arr = JSON.parse(String(rule));
            var found = arr.some(function (x) {
                return (insens ? String(x).toLowerCase() : String(x)) === needle;
            });
            return { ok: true, match: found, error: null };
        }
        // like
        return { ok: true, match: likeToRegExp(rule, insens).test(s), error: null };
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
            f.type.value = q.type || 'a';
            f.sql_query.value = q.sql_query || '';
            f.return_type.value = q.return_type || 'scalar';
            f.default_value.value = (q.default_value == null)
                ? '' : q.default_value;
            f.validation.value = (q.validation == null) ? '' : q.validation;
            f.validation_type.value = q.validation_type || '';
            if (f.validation_ci) { f.validation_ci.checked = !!q.validation_ci; } // Build 497
            f.tags.value = q.tags || '';
            _state.selId = String(q.id);
        } else {
            f.id.value = '';
            f.id.disabled = false;  // Neu-Modus: id ist einzugeben
            f.title.value = '';
            f.description.value = '';
            f.type.value = 'a';
            f.sql_query.value = '';
            f.return_type.value = 'scalar';
            f.default_value.value = '';
            f.validation.value = '';
            f.validation_type.value = '';
            if (f.validation_ci) { f.validation_ci.checked = false; }   // Build 497
            f.tags.value = '';
            _state.selId = null;
        }
        _setMsg('');
        renderDryRun(null);
        // Build 490: Sichtbarkeit/Sperren je Typ + Live-Pruefungen nachziehen
        // (typeUi wird von renderTemplates gesetzt; ohne Maske ein No-op).
        if (_state.typeUi) { _state.typeUi.apply(); }
        _markActive();
    }

    // _currentFields: die aktuellen (rohen) Feldwerte als flaches Objekt lesen.
    function _currentFields() {
        var f = _state.fields;
        return {
            id: f.id.value,
            title: f.title.value,
            description: f.description.value,
            type: f.type.value,
            sql_query: f.sql_query.value,
            return_type: f.return_type.value,
            default_value: f.default_value.value,
            validation: f.validation.value,
            validation_type: f.validation_type.value,
            validation_ci: (f.validation_ci && f.validation_ci.checked) ? 1 : 0, // Build 497
            tags: f.tags.value,
            test_subject_id: f.test_subject_id.value
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
        // Build 490: Server-WARNUNGEN (z.B. Python-re konnte die JS-Regex
        // nicht kompilieren) sichtbar machen — sie blockieren nicht
        // (Grundregel 11), duerfen aber nie still verschwinden (Grundregel 1).
        if (res.warnings && res.warnings.length) {
            var pw = document.createElement('p');
            pw.className = 'aiw-tpl-dry is-warn';
            pw.textContent = 'Hinweis: ' + res.warnings.join(' | ');
            box.appendChild(pw);
        }
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
        // Build 490: Server-Warnungen an die Erfolgsmeldung anhaengen
        // (gespeichert WURDE — die Warnung darf trotzdem nicht untergehen).
        var warn = (res && res.warnings && res.warnings.length)
            ? (' Hinweis: ' + res.warnings.join(' | ')) : '';
        _setMsg('Platzhalter "' + tid + '" '
            + (created ? 'angelegt.' : 'geaendert.') + warn, 'ok');
        _clearDraft();   // Build 488: gespeichert -> Zwischenspeicher verwerfen.
    }

    // saveError: Speicherfehler (inkl. Server-Validierung) sichtbar machen.
    function saveError(msg) {
        _setMsg('Speichern fehlgeschlagen: ' + (msg || 'unbekannt'), 'err');
    }

    // --- Browser-Zwischenspeicher des Entwurfs (Build 488) ---------------
    // _draftFromState: aktuellen Editor-Zustand serialisierbar. Kopf-Felder +
    // selId (Editier- vs. Neu-Modus).
    function _draftFromState() {
        return { v: 1, fields: _currentFields(), selId: _state.selId };
    }
    // _persistDraft: aktuellen Stand sichern (best-effort). Ohne Maske No-op.
    function _persistDraft() {
        var ls = _ls();
        if (!ls || !_state.fields) { return; }
        try { ls.setItem(DRAFT_KEY, JSON.stringify(_draftFromState())); }
        catch (e) { log('persistDraft', e); }
    }
    // _loadDraft: gespeicherten Entwurf lesen (oder null bei fehlend/unlesbar).
    function _loadDraft() {
        var ls = _ls();
        if (!ls) { return null; }
        try {
            var s = ls.getItem(DRAFT_KEY);
            if (!s) { return null; }
            var d = JSON.parse(s);
            return (d && typeof d === 'object') ? d : null;
        } catch (e) { log('loadDraft', e); return null; }
    }
    // _clearDraft: nach erfolgreichem Speichern verwerfen (Server ist Wahrheit).
    function _clearDraft() {
        var ls = _ls();
        if (!ls) { return; }
        try { ls.removeItem(DRAFT_KEY); } catch (e) { log('clearDraft', e); }
    }
    // _restoreDraft: Entwurf in die Maske laden, OHNE erneut zu persistieren.
    // id ist der Schluessel: im Editier-Modus (selId gesetzt) fix, sonst editierbar.
    function _restoreDraft(d) {
        var f = _state.fields;
        if (!f || !d) { return; }
        var fl = d.fields || {};
        f.id.value = fl.id || '';
        f.title.value = fl.title || '';
        f.description.value = fl.description || '';
        f.type.value = fl.type || 'a';                    // Build 490
        f.sql_query.value = fl.sql_query || '';
        f.return_type.value = fl.return_type || 'scalar';
        f.default_value.value = fl.default_value || '';   // Build 490
        f.validation.value = fl.validation || '';         // Build 490
        f.validation_type.value = fl.validation_type || ''; // Build 490
        if (f.validation_ci) { f.validation_ci.checked = !!fl.validation_ci; } // Build 497
        f.tags.value = fl.tags || '';
        if (f.test_subject_id) {
            f.test_subject_id.value = (fl.test_subject_id == null)
                ? '' : fl.test_subject_id;
        }
        _state.selId = (d.selId === undefined) ? null : d.selId;
        f.id.disabled = (_state.selId !== null);
        renderDryRun(null);
        if (_state.typeUi) { _state.typeUi.apply(); }     // Build 490
        _markActive();
        _setMsg('Nicht gespeicherter Entwurf aus dem Browserspeicher '
            + 'wiederhergestellt. Speichern schliesst ihn ab.', '');
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
        // Build 598 (Baustelle H / H9): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'templates.titel');
        wrap.appendChild(h);
        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'templates.hinweis');
        sub.textContent = 'Platzhalter fuer Berichte pflegen — automatisch '
            + '({{a:}}, SQL-Query), verpflichtend ({{m:}}) und optional '
            + '({{o:}}, je mit optionaler Eingabe-Validierung). SQL darf NUR '
            + 'lesen (SELECT/WITH) und ausschliesslich den Parameter :uid '
            + 'verwenden. Vor dem Speichern mit "Dry-Run" testen.';
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
        newBtn.addEventListener('click', function () {
            _fillForm(null);
            _persistDraft();   // Build 488: Neu-Modus als aktuellen Entwurf sichern.
        });
        left.appendChild(newBtn);

        var list = document.createElement('div');
        list.className = 'aiw-tpl-list';
        _state.listEl = list;
        // Build 490: der Server liefert 'placeholders' (Build 489).
        var rows = sortQueries(data && data.placeholders);
        if (!rows.length) {
            var empty = document.createElement('p');
            empty.className = 'aiw-tpl-empty';
            empty.textContent = 'Noch keine Platzhalter angelegt.';
            list.appendChild(empty);
        }
        rows.forEach(function (q) {
            var it = document.createElement('button');
            it.type = 'button';
            it.className = 'aiw-tpl-item';
            it.setAttribute('data-id', String(q.id));
            it.textContent = queryLabel(q);
            it.addEventListener('click', function () {
                _fillForm(q);
                _persistDraft();   // Build 488: geladene Query als Entwurf sichern.
            });
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

        // --- Typ (Build 490): bestimmt die Feldlogik der Maske. -----------
        var fType = _labeledField(form, 'Typ', 'select', 'aiw-tpl-type');
        [['a', typeLabel('a')], ['m', typeLabel('m')], ['o', typeLabel('o')]]
            .forEach(function (o) {
                var opt = document.createElement('option');
                opt.value = o[0];
                opt.textContent = o[1];
                fType.appendChild(opt);
            });

        var fSql = _labeledField(form, 'SQL (SELECT ... :uid ...)', 'textarea',
            'aiw-tpl-sql');
        // Referenz auf den Beschriftungs-Span (Label wechselt je Typ).
        var fSqlLabel = fSql.parentNode.querySelector('.aiw-tpl-label');
        var fRt = _labeledField(form, 'Rueckgabetyp', 'select', 'aiw-tpl-rt');
        [['scalar', returnTypeLabel('scalar')],
         ['list', returnTypeLabel('list')],
         ['table', returnTypeLabel('table')]].forEach(function (o) {
            var opt = document.createElement('option');
            opt.textContent = o[1];
            opt.value = o[0];
            fRt.appendChild(opt);
        });
        var fTags = _labeledField(form, 'Tags (optional)', 'text',
            'aiw-tpl-tags');

        // --- Default + Validierung (Build 490, NUR m/o) --------------------
        var fDefault = _labeledField(form, 'Default-Wert (optional)', 'text',
            'aiw-tpl-default');

        var valWrap = document.createElement('div');
        valWrap.className = 'aiw-tpl-valwrap';
        var fVt = _labeledField(valWrap, 'Pruefart', 'select', 'aiw-tpl-vtype');
        [['', 'keine Pruefung'],
         ['regex', 'Regex (JavaScript-Dialekt)'],
         ['list', 'Werteliste (JSON-Array)'],
         ['like', 'LIKE-Muster (% und _)']].forEach(function (o) {
            var opt = document.createElement('option');
            opt.value = o[0];
            opt.textContent = o[1];
            fVt.appendChild(opt);
        });
        var fVal = _labeledField(valWrap, 'Validierungsregel (Klartext)',
            'textarea', 'aiw-tpl-validation');
        fVal.rows = 3;
        fVal.title = 'Regex im JavaScript-Dialekt (ECMAScript); Pruefung per '
            + 'RegExp.test() — Anker ^ und $ bei Bedarf selbst setzen.';
        // Unterschrift (mc-Wunsch): der unterstuetzte Dialekt steht IN der Maske.
        var valNote = document.createElement('p');
        valNote.className = 'aiw-tpl-valnote';
        valNote.textContent = 'regex: JavaScript-Dialekt (ECMAScript), '
            + 'Pruefung per RegExp.test() — Anker ^/$ selbst setzen. '
            + 'list: JSON-Array erlaubter Werte, z.B. ["ja","nein"]. '
            + 'like: % = beliebig viele Zeichen, _ = genau ein Zeichen '
            + '(Full-Match). Gespeichert wird Klartext (UTF-8).';
        valWrap.appendChild(valNote);
        // Build 497: Case-Insensitivity-Schalter. Gilt fuer alle drei Pruefarten
        // (regex/list/like). JavaScript kennt kein Inline-(?i); das 'i'-Flag wird
        // am RegExp-Konstruktor gesetzt bzw. der Listenvergleich in Kleinschreibung
        // gefuehrt (mc 2026-07-22).
        var ciLabel = document.createElement('label');
        ciLabel.className = 'aiw-tpl-cilabel';
        var fCi = document.createElement('input');
        fCi.type = 'checkbox';
        fCi.className = 'aiw-tpl-vci';
        ciLabel.appendChild(fCi);
        ciLabel.appendChild(document.createTextNode(
            ' Gross-/Kleinschreibung ignorieren (regex/list/like)'));
        valWrap.appendChild(ciLabel);
        // Live-Gueltigkeitsausgabe der Regel selbst.
        var valCheck = document.createElement('div');
        valCheck.className = 'aiw-tpl-valcheck';
        valWrap.appendChild(valCheck);
        // Testfeld: Beispiel-Eingabe live gegen die Regel pruefen.
        var testIn = _labeledField(valWrap, 'Testfeld: Beispiel-Eingabe',
            'text', 'aiw-tpl-valtest');
        var testOut = document.createElement('div');
        testOut.className = 'aiw-tpl-valtestout';
        valWrap.appendChild(testOut);
        form.appendChild(valWrap);

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
            id: fId, title: fTitle, description: fDesc, type: fType,
            sql_query: fSql, return_type: fRt, default_value: fDefault,
            validation: fVal, validation_type: fVt,
            validation_ci: fCi,   // Build 497
            tags: fTags, test_subject_id: fTest
        };

        // --- Typ-Logik + Live-Pruefungen (Build 490) -----------------------
        // _refreshChecks: Regel-Gueltigkeit + Testfeld-Ergebnis neu bewerten.
        // Die verbindliche Regex-Syntaxpruefung passiert HIER (new RegExp im
        // JS-Dialekt); der Server prueft nur best-effort (Warnung).
        var _refreshChecks = function () {
            _clearNode(valCheck);
            _clearNode(testOut);
            if ((fType.value || 'a') === 'a') { return; }
            var vt = fVt.value;
            var rule = fVal.value;
            if (vt === '' && !String(rule).trim()) { return; } // keine Regel
            var chk = validateRule(vt, rule);
            var pc = document.createElement('p');
            pc.className = 'aiw-tpl-valcheckmsg '
                + (chk.ok ? 'is-ok' : 'is-err');
            pc.textContent = chk.ok ? 'Regel gueltig.' : chk.error;
            valCheck.appendChild(pc);
            var sample = testIn.value;
            if (sample === '') { return; } // ohne Beispiel keine Test-Ausgabe
            var res = testRule(vt, rule, sample, fCi.checked);   // Build 497: ci
            var pt = document.createElement('p');
            if (!res.ok) {
                pt.className = 'aiw-tpl-valtestmsg is-err';
                pt.textContent = 'Test nicht moeglich: ' + res.error;
            } else {
                pt.className = 'aiw-tpl-valtestmsg '
                    + (res.match ? 'is-ok' : 'is-err');
                pt.textContent = res.match
                    ? 'Beispiel-Eingabe BESTEHT die Pruefung.'
                    : 'Beispiel-Eingabe besteht die Pruefung NICHT.';
            }
            testOut.appendChild(pt);
        };
        // _applyType: Sichtbarkeit/Sperren je Typ. a: SQL Pflicht, KEINE
        // Validierung/Default (Serverregel); m/o: SQL optionale Default-Quelle,
        // return_type fest 'scalar'.
        var _applyType = function () {
            var isA = (fType.value || 'a') === 'a';
            fSqlLabel.textContent = isA
                ? 'SQL (Pflicht: SELECT ... :uid ...)'
                : 'SQL als Default-Quelle (optional: SELECT ... :uid ...)';
            if (!isA) { fRt.value = 'scalar'; }
            fRt.disabled = !isA;
            fDefault.parentNode.classList.toggle('aiw-tpl-hidden', isA);
            valWrap.classList.toggle('aiw-tpl-hidden', isA);
            _refreshChecks();
        };
        _state.typeUi = { apply: _applyType };
        fType.addEventListener('change', _applyType);
        fVt.addEventListener('change', _refreshChecks);
        fVal.addEventListener('input', _refreshChecks);
        fCi.addEventListener('change', _refreshChecks);   // Build 497
        testIn.addEventListener('input', _refreshChecks);

        // Build 488: Jede Nutzer-Eingabe sichert den Stand im Browserspeicher.
        // Programmatische .value-Zuweisungen (_fillForm/_restoreDraft) loesen kein
        // input/change aus und ueberschreiben den Speicher daher nicht ungewollt.
        form.addEventListener('input', _persistDraft);
        form.addEventListener('change', _persistDraft);

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
        // Build 488: Ein noch nicht gespeicherter Entwurf aus dem Browserspeicher
        // hat Vorrang vor dem leeren Neu-Modus (Fensterwechsel/Neuladen verliert
        // keine Arbeit). Ohne Entwurf liefert _loadDraft() null -> Neu-Modus.
        var _saved = _loadDraft();
        if (_saved) { _restoreDraft(_saved); }
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
        _state.typeUi = null;   // Build 490
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
        DRAFT_KEY: DRAFT_KEY,             // Browser-Zwischenspeicher (Build 488)
        typeLabel: typeLabel,             // Platzhalter-Typen (Build 490)
        validateRule: validateRule,       // Regel-Gueltigkeit (Build 490)
        testRule: testRule,               // Testfeld-Logik (Build 490)
        likeToRegExp: likeToRegExp,       // LIKE->RegExp (Build 490)
        // DOM
        renderTemplates: renderTemplates,
        renderDryRun: renderDryRun,
        dryRunError: dryRunError,
        saved: saved,
        saveError: saveError,
        cleanup: cleanup
    };
})();
