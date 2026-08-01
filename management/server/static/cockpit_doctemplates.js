/**
 * management/server/static/cockpit_doctemplates.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Vermaehlung B6xB7 — W3 (Dokumentvorlagen), FRONTEND (Build 425)
 *
 * Zweck:
 *   Autoren-Sicht der Redakteur:in (Recht templates.edit): DOKUMENTVORLAGEN
 *   (templates.db.report_templates) LISTEN, ANLEGEN und AENDERN. Eine Vorlage
 *   ist eine benannte, wiederverwendbare BLOCK-STRUKTUR, die der forensische
 *   Webserver spaeter ueber ihren stabilen template_key laedt (insert_template)
 *   und je Block eine frische UUID vergibt. Deshalb steht hier ein kleiner
 *   BLOCKLISTEN-EDITOR im Mittelpunkt: pro Block ein Typ (einer der neun
 *   bekannten Editor.js-Typen) und die block_data als JSON-Objekt.
 *
 *   Vor dem Speichern kann die Struktur mit "Struktur-Vorschau" SCHREIBFREI
 *   geprueft werden (POST /api/templates/document/dryrun -> {ok,errors,summary}
 *   mit Blocktyp-Zaehlung). Das eigentliche Speichern laeuft ueber den
 *   auditierten Pfad (POST /api/templates/document -> TemplatesWriter, Build 424).
 *
 *   Backend-Endpunkte (Build 424):
 *     GET  /api/templates/documents        — Liste
 *     POST /api/templates/document         — anlegen/aendern (auditiert)
 *     POST /api/templates/document/dryrun  — schreibfreie Struktur-Vorschau
 *
 *   ABGRENZUNG zu W2 (cockpit_templates.js): W2 pflegt EINZELDATEN-Queries;
 *   DIESE Sicht pflegt ganze Vorlagen (Block-Geruest). Beide schreiben nur ueber
 *   den auditierten templates.db-Pfad.
 *
 * JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging (DEV=false fuer
 *   PROD); ausfuehrliche Kommentare; Kapselung (Closure-Zustand, kleine API);
 *   REINE Funktionen separat exportiert (vitest). XSS-sicher: variable Texte
 *   ausschliesslich via textContent/value (multilinguales Forum, UTF-8).
 *
 * Build 487: Browser-Zwischenspeicher (localStorage) des NICHT gespeicherten
 *   Editor-Entwurfs — ein Fensterwechsel verliert keine Arbeit mehr: jede
 *   Nutzer-Aenderung wird gesichert, beim Betreten der Sicht wiederhergestellt,
 *   nach erfolgreichem Speichern verworfen (Schluessel DRAFT_KEY, nur Client,
 *   migrationsneutral). Zudem: Block-Textarea jetzt 5 Zeilen hoch (statt 2).
* Build 635 (Vorgang 17200856, Welle B3): HILFE-MARKEN fuer die elf
*   Bedienelemente dieser Sicht - damit tragen alle eine. Die Texte
*   stehen in management/help/inhalt/redaktion.py.
 * Version: v0.8.635 · Build: 635 · 2026-08-01
 */
(function () {
    'use strict';

    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[doctemplates]');
            console.log.apply(console, a);
        }
    }

    // Closure-Zustand (gekapselt; nur ueber cleanup() geloest).
    var _state = {
        listEl: null,     // Liste (links)
        fields: null,     // Kopf-Felder (key/title/desc/report_type/sort_order)
        blocksEl: null,   // Container der Blockzeilen
        blocks: null,     // In-Memory-Modell der Bloecke: [{type, dataText}]
        msgEl: null,      // Rueckmeldezeile
        dryEl: null,      // Ausgabe der Struktur-Vorschau
        befundEl: null,   // Unverfaenglichkeits-Befund (Build 475, Report->Vorlage)
        selKey: null      // aktuell geladene template_key (null = Neu-Modus)
    };

    // Stabiler Schluessel-Zeichenraum (Spiegel der Server-Regel _KEY_RE).
    var _KEY_RE = /^[A-Za-z0-9._-]+$/;

    // Die NEUN bekannten Blocktypen — NUR fuer die Auswahlliste. Der Server
    // (template_validator, report_render.KNOWN_BLOCK_TYPES) bleibt die Autoritaet.
    var BLOCK_TYPES = ['paragraph', 'header', 'list', 'table', 'quote',
        'image', 'delimiter', 'marker', 'evidence'];

    // Sinnvolle Vorbelegung der block_data je Typ (nur Startwert; frei aenderbar).
    var _DATA_TEMPLATE = {
        paragraph: '{"text": ""}',
        header:    '{"text": "", "level": 2}',
        list:      '{"style": "unordered", "items": []}',
        table:     '{"content": []}',
        quote:     '{"text": "", "caption": ""}',
        image:     '{"url": "", "caption": ""}',
        delimiter: '{}',
        marker:    '{"text": ""}',
        evidence:  '{"text": ""}'
    };

    // Build 487: Schluessel des Browser-Zwischenspeichers (localStorage) fuer den
    // NOCH NICHT gespeicherten Editor-Entwurf. Versioniert, damit ein spaeteres
    // Format-Update alte Staende gezielt ignorieren kann. Zweck (mc-Wunsch): ein
    // Fensterwechsel darf unerledigte Arbeit an einer Vorlage nicht verlieren.
    // NUR Client-seitig — keine DB, kein Beleg-/Evidence-Bezug (migrationsneutral).
    var DRAFT_KEY = 'aiw.doctemplates.draft.v1';

    // _ls: sicherer Zugriff auf localStorage. In Privat-Modus/Sandbox/bei Quota
    // kann der Zugriff werfen -> dann null (Feature still deaktiviert, kein Crash).
    function _ls() {
        try {
            return (typeof localStorage !== 'undefined') ? localStorage : null;
        } catch (e) { return null; }
    }

    // =====================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — vitest.
    // =====================================================================

    // reportTypeLabel: Klartext zum Vermerkstyp (Fallback: Rohwert).
    // Build 473 (Refactoring "Bericht" -> "Vermerk", mc 2026-07-21): Labels
    // umbenannt; DB-Schluessel (Klammerzusatz) unveraendert. Beleg: Auftrag 2026-07-21.
    function reportTypeLabel(rt) {
        switch (rt) {
            case 'interim':  return 'Vermerk (interim)';
            case 'final':    return 'Abschlussbericht (final)';
            case 'addendum': return 'Ergänzungsvermerk (addendum)';
            default:         return rt || '';
        }
    }

    // templateLabel: Anzeigetext eines Listeneintrags: "Titel (key)".
    function templateLabel(t) {
        if (!t) { return '?'; }
        var key = (t.template_key === undefined || t.template_key === null)
            ? '' : String(t.template_key);
        var title = (t.title === undefined || t.title === null)
            ? '' : String(t.title);
        if (title && key) { return title + ' (' + key + ')'; }
        return title || key || '?';
    }

    // sortTemplates: neue Liste, nach sort_order dann template_key. Mutiert nicht.
    function sortTemplates(list) {
        var arr = (list || []).slice();
        arr.sort(function (a, b) {
            var ao = (a && a.sort_order) || 0;
            var bo = (b && b.sort_order) || 0;
            if (ao !== bo) { return ao - bo; }
            var ak = String((a && a.template_key) || '').toLowerCase();
            var bk = String((b && b.template_key) || '').toLowerCase();
            if (ak < bk) { return -1; }
            if (ak > bk) { return 1; }
            return 0;
        });
        return arr;
    }

    // isValidKey: Client-Spiegel der Server-Regel (Bequemlichkeit).
    function isValidKey(key) {
        return _KEY_RE.test(String(key || ''));
    }

    // parseBlockData: einen block_data-Text als JSON-OBJEKT parsen. Leerer Text
    // -> {} (z.B. delimiter). Gibt {ok, data} oder {ok:false, error}.
    function parseBlockData(text) {
        var s = String(text === undefined || text === null ? '' : text).trim();
        if (s === '') { return { ok: true, data: {} }; }
        var parsed;
        try {
            parsed = JSON.parse(s);
        } catch (e) {
            return { ok: false, error: 'kein gueltiges JSON (' + (e && e.message) + ')' };
        }
        if (parsed === null || typeof parsed !== 'object'
            || Array.isArray(parsed)) {
            return { ok: false, error: 'block_data muss ein JSON-Objekt sein.' };
        }
        return { ok: true, data: parsed };
    }

    // collectBlocks: aus einer flachen Zeilenliste [{type, dataText}] die Bloecke
    // {block_type, block_data} bauen. Meldet JEDEN fehlerhaften Block einzeln mit
    // Index (kein stiller Uebersprung). REIN und testbar.
    function collectBlocks(rows) {
        var blocks = [];
        var errors = [];
        (rows || []).forEach(function (r, idx) {
            var type = (r && r.type) || '';
            if (!type) {
                errors.push('Block ' + idx + ': kein block_type gewaehlt.');
            }
            var pd = parseBlockData(r && r.dataText);
            if (!pd.ok) {
                errors.push('Block ' + idx + ': ' + pd.error);
                return;
            }
            blocks.push({ block_type: type, block_data: pd.data });
        });
        if (!rows || !rows.length) {
            errors.push('Die Vorlage enthaelt keinen Block.');
        }
        return { blocks: blocks, errors: errors };
    }

    // buildPayload: Kopf-Felder + fertige Blockliste zum POST-Body. REIN.
    function buildPayload(fields, blocks) {
        var f = fields || {};
        return {
            template_key: String(f.template_key || '').trim(),
            title: String(f.title || '').trim(),
            description: (f.description === undefined || f.description === null)
                ? '' : String(f.description),
            report_type: f.report_type || 'interim',
            sort_order: parseInt(f.sort_order, 10) || 0,
            blocks: blocks || []
        };
    }

    // summaryText: Blocktyp-Zaehlung zu "header×1, paragraph×2" verdichten.
    function summaryText(summary) {
        if (!summary || !summary.length) { return ''; }
        return summary.map(function (s) {
            return String(s.block_type) + '×' + String(s.count);
        }).join(', ');
    }

    // errorsText: Fehlerliste zu einer Zeile verdichten ('' bei keiner).
    function errorsText(errors) {
        if (!errors || !errors.length) { return ''; }
        return errors.join('; ');
    }

    // -- Build 475: "Bericht als Vorlage uebernehmen" -------------------------
    // draftToRows: die block-Objekte eines Entwurfs ({block_type, block_data})
    // in das In-Memory-Modell [{type, dataText}] umsetzen. block_data ist HIER
    // bereits ein Objekt (nicht ein blocks_json-String wie beim Laden aus der
    // DB), daher direkt huebsch serialisieren, damit die supervisor:in es
    // sichten/bearbeiten kann. REIN und testbar (vitest).
    function draftToRows(draft) {
        var out = [];
        var blocks = (draft && draft.blocks) || [];
        if (!Array.isArray(blocks)) { return out; }
        blocks.forEach(function (blk) {
            if (blk && typeof blk === 'object') {
                out.push({
                    type: String(blk.block_type || 'paragraph'),
                    dataText: JSON.stringify(blk.block_data || {}, null, 2)
                });
            }
        });
        return out;
    }

    // findingsText: die Sanitisierungs-Befunde zu einer lesbaren Liste
    // verdichten (Grundregel 1: jede Entfernung sichtbar). REIN (vitest).
    function findingsText(findings) {
        if (!findings || !findings.length) { return ''; }
        return findings.map(function (f) {
            var pos = (f && f.block_index !== undefined && f.block_index !== null)
                ? ('Block ' + f.block_index) : 'Block ?';
            var bt = (f && f.block_type) ? (' [' + f.block_type + ']') : '';
            var det = (f && (f.detail || f.action)) || '';
            return pos + bt + ': ' + det;
        }).join(' · ');
    }

    // =====================================================================
    // 2) DOM-FUNKTIONEN (nur Browser/jsdom).
    // =====================================================================

    function _clearNode(el) { if (el) { el.textContent = ''; } }

    function _labeledField(parent, labelText, kind, className) {
        var lab = document.createElement('label');
        lab.className = 'aiw-dtpl-field';
        var span = document.createElement('span');
        span.className = 'aiw-dtpl-label';
        span.textContent = labelText;
        lab.appendChild(span);
        var input;
        if (kind === 'textarea') {
            input = document.createElement('textarea');
            input.rows = 2;
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

    // _renderBlocks: die Blockzeilen aus _state.blocks neu zeichnen. Jede Zeile:
    // [Typ-Auswahl][block_data JSON][hoch][runter][entfernen]. Das In-Memory-
    // Modell (_state.blocks) ist die Wahrheit; Struktur-Aenderungen (add/move/
    // remove) veraendern das Modell und zeichnen neu (robuster als DOM-Umbau).
    function _renderBlocks() {
        var host = _state.blocksEl;
        if (!host) { return; }
        _clearNode(host);
        _state.blocks.forEach(function (blk, idx) {
            var row = document.createElement('div');
            row.className = 'aiw-dtpl-block';
            row.setAttribute('data-idx', String(idx));

            var sel = document.createElement('select');
            sel.className = 'aiw-dtpl-btype';
            // Build 635 (Vorgang 17200856): Hilfe-Marke, LITERAL gesetzt.
            // Text in management/help/inhalt/redaktion.py.
            sel.setAttribute('data-hilfe-id', 'doctemplates.bedienung.blockart');
            BLOCK_TYPES.forEach(function (bt) {
                var opt = document.createElement('option');
                opt.value = bt;
                opt.textContent = bt;
                if (bt === blk.type) { opt.selected = true; }
                sel.appendChild(opt);
            });
            sel.addEventListener('change', function () {
                _state.blocks[idx].type = sel.value;
                // Nur wenn die block_data noch leer ist, sinnvolle Vorlage setzen.
                if (!String(_state.blocks[idx].dataText || '').trim()) {
                    _state.blocks[idx].dataText = _DATA_TEMPLATE[sel.value] || '{}';
                    _renderBlocks();
                }
            });
            row.appendChild(sel);

            var data = document.createElement('textarea');
            data.className = 'aiw-dtpl-bdata';
            data.setAttribute('data-hilfe-id',
                'doctemplates.bedienung.blockdaten');
            data.rows = 5;   // Build 487 (mc-Wunsch): mind. 5 Zeilen hoch.
            data.value = blk.dataText || '';
            data.addEventListener('input', function () {
                _state.blocks[idx].dataText = data.value;
            });
            row.appendChild(data);

            var ctr = document.createElement('div');
            ctr.className = 'aiw-dtpl-bctrl';
            // Build 635: Die drei Steuerknoepfe stammen aus der Fabrik
            // '_ctrlBtn' und wanderten bisher direkt in appendChild. Sie
            // bekommen je eine Variable, damit die Marke LITERAL am
            // EINZELNEN Knopf stehen kann - eine Fabrik koennte nur eine
            // Kennung fuer alle drei setzen, und die drei sagen
            // Verschiedenes. Am Verhalten aendert sich nichts.
            var bHoch = _ctrlBtn('↑', 'nach oben', function () {
                _moveBlock(idx, -1);
            });
            bHoch.setAttribute('data-hilfe-id',
                'doctemplates.bedienung.block_hoch');
            ctr.appendChild(bHoch);
            var bRunter = _ctrlBtn('↓', 'nach unten', function () {
                _moveBlock(idx, 1);
            });
            bRunter.setAttribute('data-hilfe-id',
                'doctemplates.bedienung.block_runter');
            ctr.appendChild(bRunter);
            var bWeg = _ctrlBtn('✕', 'entfernen', function () {
                _state.blocks.splice(idx, 1);
                _renderBlocks();
                _persistDraft();   // Build 487: Strukturaenderung sichern.
            });
            bWeg.setAttribute('data-hilfe-id',
                'doctemplates.bedienung.block_entfernen');
            ctr.appendChild(bWeg);
            row.appendChild(ctr);

            host.appendChild(row);
        });
    }

    function _ctrlBtn(label, title, onClick) {
        var b = document.createElement('button');
        b.type = 'button';
        b.className = 'aiw-dtpl-bbtn';
        b.textContent = label;
        b.title = title;
        b.addEventListener('click', onClick);
        return b;
    }

    // _moveBlock: Block um delta (-1/+1) verschieben (Grenzen beachten).
    function _moveBlock(idx, delta) {
        var to = idx + delta;
        if (to < 0 || to >= _state.blocks.length) { return; }
        var tmp = _state.blocks[idx];
        _state.blocks[idx] = _state.blocks[to];
        _state.blocks[to] = tmp;
        _renderBlocks();
        _persistDraft();   // Build 487: Reihenfolge-Aenderung sichern.
    }

    // _blocksFromJson: blocks_json (String) einer Vorlage in das In-Memory-Modell
    // umsetzen. Unlesbares JSON -> leere Liste + Meldung (kein stiller Verlust).
    function _blocksFromJson(blocksJson) {
        var out = [];
        var raw;
        try {
            raw = JSON.parse(blocksJson || '[]');
        } catch (e) {
            _setMsg('Achtung: blocks_json der Vorlage ist unlesbar — bitte neu '
                + 'aufbauen.', 'err');
            return out;
        }
        if (!Array.isArray(raw)) { return out; }
        raw.forEach(function (blk) {
            if (blk && typeof blk === 'object') {
                out.push({
                    type: String(blk.block_type || 'paragraph'),
                    // block_data huebsch (2 Leerzeichen) darstellen, damit die
                    // Autor:in es lesen/bearbeiten kann.
                    dataText: JSON.stringify(blk.block_data || {}, null, 2)
                });
            }
        });
        return out;
    }

    function _fillForm(t) {
        var f = _state.fields;
        if (!f) { return; }
        if (t) {
            f.template_key.value = t.template_key || '';
            f.template_key.disabled = true;   // Schluessel im Editier-Modus fix
            f.title.value = t.title || '';
            f.description.value = t.description || '';
            f.report_type.value = t.report_type || 'interim';
            f.sort_order.value = (t.sort_order === undefined
                || t.sort_order === null) ? 0 : t.sort_order;
            _state.blocks = _blocksFromJson(t.blocks_json);
            _state.selKey = String(t.template_key);
        } else {
            f.template_key.value = '';
            f.template_key.disabled = false;  // Neu-Modus: Schluessel eingeben
            f.title.value = '';
            f.description.value = '';
            f.report_type.value = 'interim';
            f.sort_order.value = 0;
            _state.blocks = [];
            _state.selKey = null;
        }
        _setMsg('');
        renderDryRun(null);
        _renderBefund(null);   // Build 475: Befund nur beim Entwurfs-Uebertrag
        _renderBlocks();
        _markActive();
    }

    // _renderBefund: den Unverfaenglichkeits-Befund (Build 475) anzeigen. Eine
    // Liste der serverseitig entfernten Inhalte (Platzhalter-Werte, evidence_ids)
    // und Warnungen. findings=null/[] leert den Bereich. XSS-sicher (textContent).
    function _renderBefund(findings, warnings) {
        var box = _state.befundEl;
        if (!box) { return; }
        _clearNode(box);
        var all = [];
        (findings || []).forEach(function (f) { all.push(f); });
        (warnings || []).forEach(function (w) {
            all.push({ block_index: w.block_index, block_type: w.block_type,
                detail: (w.detail || w.code) });
        });
        if (!all.length) { return; }
        var head = document.createElement('p');
        head.className = 'aiw-dtpl-befund-head';
        head.textContent = 'Unverfaenglichkeits-Befund (' + all.length
            + ') — bitte pruefen: die folgenden fallbezogenen Inhalte wurden '
            + 'beim Uebernehmen entfernt.';
        box.appendChild(head);
        var ul = document.createElement('ul');
        ul.className = 'aiw-dtpl-befund-list';
        all.forEach(function (f) {
            var li = document.createElement('li');
            var pos = (f.block_index !== undefined && f.block_index !== null)
                ? ('Block ' + f.block_index) : 'Block ?';
            var bt = f.block_type ? (' [' + f.block_type + ']') : '';
            li.textContent = pos + bt + ': ' + (f.detail || f.action || '');
            ul.appendChild(li);
        });
        box.appendChild(ul);
    }

    // _fillDraft: einen aus einem Bericht erzeugten ENTWURF in die Editor-Maske
    // laden (Build 475). NEU-MODUS: template_key bleibt EDITIERBAR (kein stilles
    // Ueberschreiben einer bestehenden Vorlage), selKey=null. Der Befund zeigt,
    // was beim Uebernehmen entfernt wurde (Grundregel 1).
    function _fillDraft(draft, findings, warnings) {
        var f = _state.fields;
        if (!f || !draft) { return; }
        f.template_key.value = draft.template_key || '';
        f.template_key.disabled = false;   // Neu-Modus: Schluessel editierbar
        f.title.value = draft.title || '';
        f.description.value = draft.description || '';
        f.report_type.value = draft.report_type || 'interim';
        f.sort_order.value = 0;
        _state.blocks = draftToRows(draft);
        _state.selKey = null;              // Neu-Modus (nie Overschreiben)
        _setMsg('Entwurf aus Bericht uebernommen — bitte Unverfaenglichkeit '
            + 'pruefen, dann template_key/Titel setzen und speichern.', 'ok');
        renderDryRun(null);
        _renderBefund(findings, warnings);
        _renderBlocks();
        _markActive();
    }

    function _currentFields() {
        var f = _state.fields;
        return {
            template_key: f.template_key.value,
            title: f.title.value,
            description: f.description.value,
            report_type: f.report_type.value,
            sort_order: f.sort_order.value
        };
    }

    function _markActive() {
        if (!_state.listEl) { return; }
        var items = _state.listEl.querySelectorAll('.aiw-dtpl-item');
        Array.prototype.forEach.call(items, function (it) {
            var on = (_state.selKey !== null
                && it.getAttribute('data-key') === _state.selKey);
            it.classList.toggle('is-active', on);
        });
    }

    function _setMsg(text, kind) {
        if (!_state.msgEl) { return; }
        _state.msgEl.textContent = text || '';
        _state.msgEl.className = 'aiw-dtpl-msg' + (kind ? (' is-' + kind) : '');
    }

    // renderDryRun: Ergebnis der schreibfreien Struktur-Vorschau anzeigen.
    // res=null leert den Bereich. Fehler (rot) haben Vorrang vor der
    // Blocktyp-Zusammenfassung (gruen) — Grundregel 1: Fehler nie still schlucken.
    function renderDryRun(res) {
        var box = _state.dryEl;
        if (!box) { return; }
        _clearNode(box);
        if (!res) { return; }
        var errs = errorsText(res.errors);
        if (errs) {
            var pe = document.createElement('p');
            pe.className = 'aiw-dtpl-dry is-err';
            pe.textContent = 'Nicht gueltig: ' + errs;
            box.appendChild(pe);
            return;
        }
        var ps = document.createElement('p');
        ps.className = 'aiw-dtpl-dry is-ok';
        var txt = summaryText(res.summary);
        ps.textContent = 'Struktur OK' + (txt ? (' — Bloecke: ' + txt) : '.');
        box.appendChild(ps);
    }

    function dryRunError(msg) {
        var box = _state.dryEl;
        if (!box) { return; }
        _clearNode(box);
        var p = document.createElement('p');
        p.className = 'aiw-dtpl-dry is-err';
        p.textContent = 'Vorschau fehlgeschlagen: ' + (msg || 'unbekannt');
        box.appendChild(p);
    }

    function saved(res) {
        var created = !!(res && res.created);
        var tid = (res && res.target_id) ? res.target_id : '?';
        _setMsg('Vorlage "' + tid + '" '
            + (created ? 'angelegt.' : 'geaendert.'), 'ok');
        // Build 487: erfolgreich gespeichert -> der Browser-Zwischenspeicher
        // waere jetzt veraltet und wird verworfen (der Server ist die Wahrheit).
        _clearDraft();
    }

    function saveError(msg) {
        _setMsg('Speichern fehlgeschlagen: ' + (msg || 'unbekannt'), 'err');
    }

    // --- Browser-Zwischenspeicher des Entwurfs (Build 487) ---------------
    // _draftFromState: aktuellen Editor-Zustand als serialisierbares Objekt.
    // Kopf-Felder + Bloecke (Typ/Text) + selKey (Editier- vs. Neu-Modus).
    function _draftFromState() {
        return {
            v: 1,
            fields: _currentFields(),
            blocks: (_state.blocks || []).map(function (b) {
                return { type: String(b.type || 'paragraph'),
                         dataText: String(b.dataText || '') };
            }),
            selKey: _state.selKey
        };
    }

    // _persistDraft: aktuellen Zustand in den Browserspeicher schreiben (best-
    // effort). Wird bei JEDER Nutzer-Aenderung gerufen (Eingaben ueber den form-
    // 'input'/'change'-Listener, Blockstruktur ueber die Knopf-Handler). Ohne
    // aufgebaute Maske (_state.fields===null, z.B. nach cleanup) ein No-op.
    function _persistDraft() {
        var ls = _ls();
        if (!ls || !_state.fields) { return; }
        try { ls.setItem(DRAFT_KEY, JSON.stringify(_draftFromState())); }
        catch (e) { log('persistDraft', e); }
    }

    // _loadDraft: gespeicherten Entwurf lesen (oder null). Unlesbar -> null.
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

    // _clearDraft: Entwurf verwerfen — nach ERFOLGREICHEM Speichern (dann ist der
    // Stand serverseitig persistiert und der Zwischenspeicher waere veraltet).
    function _clearDraft() {
        var ls = _ls();
        if (!ls) { return; }
        try { ls.removeItem(DRAFT_KEY); } catch (e) { log('clearDraft', e); }
    }

    // _restoreDraft: gespeicherten Entwurf in die Maske laden, OHNE ihn erneut zu
    // persistieren (keine Schleife). template_key ist im Editier-Modus (selKey
    // gesetzt) fix, im Neu-/Entwurfsmodus editierbar — analog _fillForm.
    function _restoreDraft(d) {
        var f = _state.fields;
        if (!f || !d) { return; }
        var fl = d.fields || {};
        f.template_key.value = fl.template_key || '';
        f.title.value = fl.title || '';
        f.description.value = fl.description || '';
        f.report_type.value = fl.report_type || 'interim';
        f.sort_order.value = (fl.sort_order === undefined
            || fl.sort_order === null) ? 0 : fl.sort_order;
        _state.selKey = (d.selKey === undefined) ? null : d.selKey;
        f.template_key.disabled = (_state.selKey !== null);
        _state.blocks = (Array.isArray(d.blocks) ? d.blocks : []).map(
            function (b) {
                return { type: String(b.type || 'paragraph'),
                         dataText: String(b.dataText || '') };
            });
        renderDryRun(null);
        _renderBefund(null);
        _renderBlocks();
        _markActive();
        _setMsg('Nicht gespeicherter Entwurf aus dem Browserspeicher '
            + 'wiederhergestellt. Speichern schliesst ihn ab.', '');
    }

    // renderDocTemplates: Gesamtsicht. data = {count, documents}. opts:
    //   onDryRun(payload)  — schreibfreie Struktur-Vorschau (cockpit.js -> POST)
    //   onSave(payload)    — auditiertes Speichern (cockpit.js -> POST)
    // Client-seitige Blocksammlung (collectBlocks) laeuft VOR dem Netz-Aufruf; bei
    // JSON-/Struktur-Fehlern wird gar nicht gesendet, sondern sofort gemeldet.
    function renderDocTemplates(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        _clearNode(mainEl);

        var wrap = document.createElement('div');
        wrap.className = 'aiw-dtpl-wrap';

        var h = document.createElement('h2');
        h.className = 'aiw-pagetitle';
        h.textContent = 'Dokumentvorlagen';
        // Build 598 (Baustelle H / H9): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'doctemplates.titel');
        wrap.appendChild(h);
        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'doctemplates.hinweis');
        sub.textContent = 'Wiederverwendbare Berichts-Gerueste pflegen. Eine '
            + 'Vorlage besteht aus Bloecken (Typ + block_data als JSON-Objekt). '
            + 'Platzhalter wie {{a:name}} bleiben im Text stehen und werden erst '
            + 'beim Rendern des konkreten Berichts aufgeloest. Vor dem Speichern '
            + 'mit "Struktur-Vorschau" pruefen.';
        wrap.appendChild(sub);

        var body = document.createElement('div');
        body.className = 'aiw-dtpl-body';

        // --- Linke Spalte: Liste + "Neu".
        var left = document.createElement('div');
        left.className = 'aiw-dtpl-listcol';
        var newBtn = document.createElement('button');
        newBtn.type = 'button';
        newBtn.className = 'aiw-dtpl-new';
        newBtn.textContent = '+ Neue Vorlage';
        newBtn.setAttribute('data-hilfe-id',
            'doctemplates.bedienung.neue_vorlage');
        newBtn.addEventListener('click', function () {
            _fillForm(null);
            _persistDraft();   // Build 487: Neu-Modus als aktuellen Entwurf sichern.
        });
        left.appendChild(newBtn);

        var list = document.createElement('div');
        list.className = 'aiw-dtpl-list';
        _state.listEl = list;
        var rows = sortTemplates(data && data.documents);
        if (!rows.length) {
            var empty = document.createElement('p');
            empty.className = 'aiw-dtpl-empty';
            empty.textContent = 'Noch keine Vorlagen angelegt.';
            list.appendChild(empty);
        }
        rows.forEach(function (t) {
            var it = document.createElement('button');
            it.type = 'button';
            it.className = 'aiw-dtpl-item';
            it.setAttribute('data-hilfe-id',
                'doctemplates.bedienung.vorlage_waehlen');
            it.setAttribute('data-key', String(t.template_key));
            it.textContent = templateLabel(t);
            it.addEventListener('click', function () {
                _fillForm(t);
                _persistDraft();   // Build 487: geladene Vorlage als Entwurf sichern.
            });
            list.appendChild(it);
        });
        left.appendChild(list);
        body.appendChild(left);

        // --- Rechte Spalte: Editor-Maske.
        var form = document.createElement('div');
        form.className = 'aiw-dtpl-form';

        var fKey = _labeledField(form, 'template_key (A-Z a-z 0-9 . _ -)',
            'text', 'aiw-dtpl-key');
        // Marken an den ABNAHMESTELLEN der Fabrik '_labeledField' - fuenf
        // verschiedene Felder aus einer Fabrik (Fabrikregel, Build 633).
        fKey.setAttribute('data-hilfe-id', 'doctemplates.bedienung.schluessel');
        var fTitle = _labeledField(form, 'Titel', 'text', 'aiw-dtpl-title');
        fTitle.setAttribute('data-hilfe-id',
            'doctemplates.bedienung.vorlagentitel');
        var fDesc = _labeledField(form, 'Beschreibung (optional)', 'textarea',
            'aiw-dtpl-desc');
        fDesc.setAttribute('data-hilfe-id',
            'doctemplates.bedienung.beschreibung');
        var fRt = _labeledField(form, 'Vermerkstyp', 'select', 'aiw-dtpl-rt');
        fRt.setAttribute('data-hilfe-id', 'doctemplates.bedienung.vermerkstyp');
        // Build 473: Reihenfolge interim -> addendum -> final (Abschlussbericht zuletzt).
        [['interim', reportTypeLabel('interim')],
         ['addendum', reportTypeLabel('addendum')],
         ['final', reportTypeLabel('final')]].forEach(function (o) {
            var opt = document.createElement('option');
            opt.value = o[0];
            opt.textContent = o[1];
            fRt.appendChild(opt);
        });
        var fSort = _labeledField(form, 'Sortierung', 'number',
            'aiw-dtpl-sort');
        fSort.setAttribute('data-hilfe-id', 'doctemplates.bedienung.sortierung');

        // Blocklisten-Editor.
        var blkHead = document.createElement('div');
        blkHead.className = 'aiw-dtpl-blockhead';
        var blkTitle = document.createElement('span');
        blkTitle.className = 'aiw-dtpl-label';
        blkTitle.textContent = 'Bloecke';
        blkHead.appendChild(blkTitle);
        var addBtn = document.createElement('button');
        addBtn.type = 'button';
        addBtn.className = 'aiw-dtpl-addblock';
        addBtn.textContent = '+ Block';
        addBtn.setAttribute('data-hilfe-id',
            'doctemplates.bedienung.block_hinzufuegen');
        addBtn.addEventListener('click', function () {
            _state.blocks.push({ type: 'paragraph',
                dataText: _DATA_TEMPLATE.paragraph });
            _renderBlocks();
            _persistDraft();   // Build 487: neuen Block sichern.
        });
        blkHead.appendChild(addBtn);
        form.appendChild(blkHead);

        var blocksHost = document.createElement('div');
        blocksHost.className = 'aiw-dtpl-blocks';
        _state.blocksEl = blocksHost;
        form.appendChild(blocksHost);

        // Aktionen: Vorschau + Speichern + Ausgabe/Rueckmeldung.
        var actions = document.createElement('div');
        actions.className = 'aiw-dtpl-actions';
        var dryBtn = document.createElement('button');
        dryBtn.type = 'button';
        dryBtn.className = 'aiw-dtpl-drybtn';
        dryBtn.textContent = 'Struktur-Vorschau (schreibfrei)';
        dryBtn.setAttribute('data-hilfe-id',
            'doctemplates.bedienung.strukturvorschau');
        actions.appendChild(dryBtn);
        var saveBtn = document.createElement('button');
        saveBtn.type = 'button';
        saveBtn.className = 'aiw-dtpl-save';
        saveBtn.textContent = 'Speichern (auditiert)';
        saveBtn.setAttribute('data-hilfe-id',
            'doctemplates.bedienung.speichern');
        actions.appendChild(saveBtn);
        var msg = document.createElement('span');
        msg.className = 'aiw-dtpl-msg';
        _state.msgEl = msg;
        actions.appendChild(msg);
        form.appendChild(actions);

        var dry = document.createElement('div');
        dry.className = 'aiw-dtpl-dryout';
        _state.dryEl = dry;
        form.appendChild(dry);

        // Build 475: Befund-Bereich fuer "Bericht als Vorlage uebernehmen".
        var befund = document.createElement('div');
        befund.className = 'aiw-dtpl-befund';
        _state.befundEl = befund;
        form.appendChild(befund);

        body.appendChild(form);
        wrap.appendChild(body);
        mainEl.appendChild(wrap);

        _state.fields = {
            template_key: fKey, title: fTitle, description: fDesc,
            report_type: fRt, sort_order: fSort
        };

        // Build 487: Jede Nutzer-Eingabe in der Maske (Kopf-Felder UND die
        // Block-Textareas/Typ-Auswahlen, die hierher blubbern) sichert den
        // aktuellen Stand im Browserspeicher. Programmatische Aenderungen
        // (_fillForm/_restoreDraft via .value=) loesen KEIN input/change aus und
        // ueberschreiben den Zwischenspeicher daher nicht ungewollt.
        form.addEventListener('input', _persistDraft);
        form.addEventListener('change', _persistDraft);

        // gemeinsame Vorbereitung fuer Vorschau/Speichern: Bloecke sammeln;
        // bei Client-Fehlern (kaputtes JSON etc.) NICHT senden, sondern melden.
        var prepare = function () {
            var collected = collectBlocks(_state.blocks);
            if (collected.errors.length) {
                renderDryRun({ ok: false, errors: collected.errors });
                return null;
            }
            return buildPayload(_currentFields(), collected.blocks);
        };

        dryBtn.addEventListener('click', function () {
            _setMsg('');
            var payload = prepare();
            if (payload && typeof opts.onDryRun === 'function') {
                opts.onDryRun(payload);
            }
        });
        saveBtn.addEventListener('click', function () {
            renderDryRun(null);
            var payload = prepare();
            if (payload && typeof opts.onSave === 'function') {
                opts.onSave(payload);
            }
        });

        // Startzustand: Neu-Modus.
        _fillForm(null);

        // Build 475/487: Vorrangfolge beim Betreten der Sicht:
        //   1) Ein aus dem Lektorat uebergebener Entwurf (opts.initialDraft) hat
        //      Vorrang — die Autor:in kam bewusst mit diesem Entwurf. Er wird
        //      eingefuellt UND als aktueller Zwischenspeicher gesichert.
        //   2) Sonst: ein NOCH NICHT gespeicherter Entwurf aus dem Browserspeicher
        //      (Build 487) — damit ein Fensterwechsel keine Arbeit verliert.
        //   3) Sonst bleibt der oben gesetzte Neu-Modus.
        // (2) darf (3) NICHT ueberschreiben, ohne dass wirklich ein Entwurf
        // vorliegt — _loadDraft() liefert dann null.
        if (opts.initialDraft) {
            _fillDraft(opts.initialDraft, opts.initialFindings,
                opts.initialWarnings);
            _persistDraft();
        } else {
            var _saved = _loadDraft();
            if (_saved) { _restoreDraft(_saved); }
        }

        log('renderDocTemplates:', rows.length, 'Vorlagen');
        return wrap;
    }

    function cleanup() {
        _state.listEl = null;
        _state.fields = null;
        _state.blocksEl = null;
        _state.blocks = null;
        _state.msgEl = null;
        _state.dryEl = null;
        _state.befundEl = null;
        _state.selKey = null;
    }

    // -------------------------------------------------------------------------
    // OEFFENTLICHE API. Reine Funktionen zuerst (vitest), dann DOM.
    // -------------------------------------------------------------------------
    window.AIWCockpitDocTemplates = {
        // reine Funktionen (vitest)
        reportTypeLabel: reportTypeLabel,
        templateLabel: templateLabel,
        sortTemplates: sortTemplates,
        isValidKey: isValidKey,
        parseBlockData: parseBlockData,
        collectBlocks: collectBlocks,
        buildPayload: buildPayload,
        summaryText: summaryText,
        errorsText: errorsText,
        draftToRows: draftToRows,
        findingsText: findingsText,
        BLOCK_TYPES: BLOCK_TYPES,
        DRAFT_KEY: DRAFT_KEY,             // Browser-Zwischenspeicher (Build 487)
        // DOM
        renderDocTemplates: renderDocTemplates,
        renderDryRun: renderDryRun,
        dryRunError: dryRunError,
        saved: saved,
        saveError: saveError,
        cleanup: cleanup
    };
})();
