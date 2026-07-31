/**
 * management/server/static/cockpit_modules.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit
 * Vermaehlung B6xB7 — W1 (Baustein-Module), FRONTEND (Build 427)
 *
 * Zweck:
 *   Autoren-Sicht der Redakteur:in (Recht templates.edit): BAUSTEIN-MODULE
 *   (templates.db.report_modules) LISTEN, ANLEGEN und AENDERN. Ein Baustein ist
 *   ein wiederverwendbarer FREITEXT-Baustein (body), den der Berichtseditor
 *   ueber seine STABILE Kennung module_key einfuegt. Der body darf Platzhalter
 *   {{a:}}/{{m:}}/{{o:}} enthalten, die erst beim Rendern des konkreten Berichts
 *   aufgeloest werden — hier NICHT.
 *
 *   Vor dem Speichern kann mit "Vorschau" SCHREIBFREI geprueft werden
 *   (POST /api/templates/module/dryrun -> {ok,errors,summary} mit Platzhalter-
 *   Zaehlung). Das Speichern laeuft ueber den auditierten Pfad
 *   (POST /api/templates/module -> TemplatesWriter, Build 426).
 *
 *   Backend-Endpunkte (Build 426):
 *     GET  /api/templates/modules        — Liste
 *     POST /api/templates/module         — anlegen/aendern (auditiert)
 *     POST /api/templates/module/dryrun  — schreibfreie Vorschau
 *
 *   ABGRENZUNG: W2 pflegt Einzeldaten-Queries, W3 ganze Dokumentvorlagen (Block-
 *   Geruest), DIESE Sicht einzelne Textbausteine. Alle drei schreiben nur ueber
 *   den auditierten templates.db-Pfad.
 *
 * JS-Gebote (Projektregeln): IIFE + 'use strict'; DEV-Logging (DEV=false fuer
 *   PROD); ausfuehrliche Kommentare; Kapselung; REINE Funktionen separat
 *   exportiert (vitest). XSS-sicher via textContent/value (multilingual, UTF-8).
 *
 * Build 488: Browser-Zwischenspeicher (localStorage) des NICHT gespeicherten
 *   Editor-Entwurfs (analog Dokumentvorlagen Build 487): jede Nutzer-Eingabe
 *   wird gesichert, beim Betreten/Neuladen wiederhergestellt, nach erfolgreichem
 *   Speichern verworfen. Eigener Schluessel DRAFT_KEY, nur Client, migrationsneutral.
 * Version: v0.8.488 · Build: 488 · 2026-07-21
 */
(function () {
    'use strict';

    var DEV = false;
    function log() {
        if (DEV && typeof console !== 'undefined' && console.log) {
            var a = Array.prototype.slice.call(arguments);
            a.unshift('[modules]');
            console.log.apply(console, a);
        }
    }

    var _state = {
        listEl: null, fields: null, msgEl: null, dryEl: null,
        selKey: null, selId: null, nachtragId: null,
        keyHinweisEl: null
    };

    // Build 488: Browser-Zwischenspeicher (localStorage) des NOCH NICHT
    // gespeicherten Editor-Entwurfs (analog Dokumentvorlagen Build 487). Eigener
    // versionierter Schluessel. Nur Client-seitig, migrationsneutral.
    var DRAFT_KEY = 'aiw.modules.draft.v1';
    function _ls() {
        try {
            return (typeof localStorage !== 'undefined') ? localStorage : null;
        } catch (e) { return null; }
    }

    // Stabiler Schluessel-Zeichenraum (Spiegel der Server-Regel _KEY_RE).
    var _KEY_RE = /^[A-Za-z0-9._-]+$/;

    // Zulaessige Rollen (deckungsgleich mit report_modules.role / module_validator.ROLES).
    var ROLES = ['intro', 'conclusion', 'body', 'legal', 'appendix', 'closing'];

    // =====================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — vitest.
    // =====================================================================

    // roleLabel: Klartext zur Rolle (Fallback: Rohwert).
    function roleLabel(role) {
        switch (role) {
            case 'intro':      return 'Einleitung (intro)';
            case 'conclusion': return 'Fazit (conclusion)';
            case 'body':       return 'Hauptteil (body)';
            case 'legal':      return 'Rechtliches (legal)';
            case 'appendix':   return 'Anhang (appendix)';
            case 'closing':    return 'Schluss (closing)';
            default:           return role || '';
        }
    }

    // moduleLabel: Anzeigetext eines Listeneintrags: "Titel (key)".
    function moduleLabel(m) {
        if (!m) { return '?'; }
        var key = (m.module_key === undefined || m.module_key === null)
            ? '' : String(m.module_key);
        var title = (m.title === undefined || m.title === null)
            ? '' : String(m.title);
        if (title && key) { return title + ' (' + key + ')'; }
        return title || key || '?';
    }

    // sortModules: neue Liste, nach role dann sort_order dann module_key.
    // Mutiert die Eingabe NICHT.
    function sortModules(list) {
        var arr = (list || []).slice();
        arr.sort(function (a, b) {
            var ar = String((a && a.role) || '');
            var br = String((b && b.role) || '');
            if (ar !== br) { return ar < br ? -1 : 1; }
            var ao = (a && a.sort_order) || 0;
            var bo = (b && b.sort_order) || 0;
            if (ao !== bo) { return ao - bo; }
            var ak = String((a && a.module_key) || '').toLowerCase();
            var bk = String((b && b.module_key) || '').toLowerCase();
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

    // schluesselVorschlag: aus einem Titel eine zulaessige Kennung bauen
    // (Build 565). Ein leeres Pflichtfeld ohne Anhalt ist eine Falle - wer
    // acht Altbausteine nachtragen muss, soll nicht achtmal ueberlegen
    // muessen, wie ein Schluessel auszusehen hat. Der Vorschlag ist frei
    // ueberschreibbar; er wird NIE automatisch gespeichert.
    //
    // Regeln: Umlaute ausschreiben (sonst faellt 'Beschluss' zu 'Beschluss'
    // und 'Anhörung' zu 'Anhrung' zusammen), alles klein, jede unzulaessige
    // Folge zu einem Punkt, Raender abschneiden. Der erlaubte Zeichenraum
    // ist [A-Za-z0-9._-] (module_validator).
    function schluesselVorschlag(titel, rolle) {
        var t = String(titel || '').toLowerCase();
        t = t.replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue')
             .replace(/ß/g, 'ss');
        t = t.replace(/[^a-z0-9]+/g, '.').replace(/^\.+|\.+$/g, '');
        if (!t) { return ''; }
        var r = String(rolle || '').replace(/[^a-z0-9]+/g, '');
        // Praefix aus der Rolle, wie beim Bestand ('intro.standard',
        // 'legal.ki_uebersetzung'): so bleibt die Liste sortierbar.
        return r ? (r + '.' + t) : t;
    }

    // buildPayload: Feldwerte zum POST-Body. REIN. module_key/title/topic werden
    // getrimmt; body NICHT (Freitext bleibt exakt erhalten); description wie
    // eingegeben (leer erlaubt); sort_order als Zahl.
    function buildPayload(fields) {
        var f = fields || {};
        return {
            // Build 564/565: die id wird NUR mitgesendet, wenn ein Schluessel
            // nachzutragen ist. Sonst bliebe sie ein zweiter Adressweg neben
            // dem module_key - und zwei Adresswege auf dieselbe Zeile sind
            // einer zu viel.
            id: (f.id === undefined || f.id === null || f.id === '')
                ? undefined : f.id,
            module_key: String(f.module_key || '').trim(),
            title: String(f.title || '').trim(),
            description: (f.description === undefined || f.description === null)
                ? '' : String(f.description),
            role: f.role || 'body',
            topic: String(f.topic || '').trim(),
            body: (f.body === undefined || f.body === null) ? '' : String(f.body),
            sort_order: parseInt(f.sort_order, 10) || 0
        };
    }

    // summaryText: Platzhalter-Zaehlung zu "auto×2, mandatory×1" verdichten.
    function summaryText(summary) {
        if (!summary || !summary.length) { return ''; }
        return summary.map(function (s) {
            return String(s.kind) + '×' + String(s.count);
        }).join(', ');
    }

    // errorsText: Fehlerliste zu einer Zeile ('' bei keiner).
    function errorsText(errors) {
        if (!errors || !errors.length) { return ''; }
        return errors.join('; ');
    }

    // =====================================================================
    // 2) DOM-FUNKTIONEN (nur Browser/jsdom).
    // =====================================================================

    function _clearNode(el) { if (el) { el.textContent = ''; } }

    function _labeledField(parent, labelText, kind, className) {
        var lab = document.createElement('label');
        lab.className = 'aiw-mod-field';
        var span = document.createElement('span');
        span.className = 'aiw-mod-label';
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

    function _fillForm(m) {
        var f = _state.fields;
        if (!f) { return; }
        if (m) {
            // BUILD 565 - ALTBESTAND OHNE SCHLUESSEL.
            // Bis Build 564 war das Feld im Editier-Modus IMMER gesperrt. Das
            // ist fuer Bausteine MIT Schluessel richtig (er ist eine stabile
            // Kennung, auf die Berichtsvorlagen verweisen) - fuer Altzeilen
            // OHNE Schluessel war es eine Sackgasse: sie liessen sich weder
            // in der Vorschau ansehen noch aendern, weil die Validierung den
            // Schluessel verlangt und niemand ihn eintragen konnte.
            var hatKey = !!(m.module_key);
            f.module_key.value = m.module_key || '';
            _state.nachtragId = hatKey ? null : m.id;
            if (!hatKey) {
                // Vorschlag setzen, aber NICHT speichern - das tut erst der
                // Anwender mit dem Speichern-Knopf.
                f.module_key.value = schluesselVorschlag(m.title, m.role);
            }
            f.title.value = m.title || '';
            f.description.value = m.description || '';
            f.role.value = m.role || 'body';
            f.topic.value = m.topic || '';
            f.body.value = m.body || '';
            f.sort_order.value = (m.sort_order === undefined
                || m.sort_order === null) ? 0 : m.sort_order;
            // selKey adressiert die Zeile in der Liste. Bei einer Altzeile
            // gibt es keinen Schluessel - dann wird ueber die id adressiert,
            // sonst stuende dort der Text "null".
            _state.selKey = hatKey ? String(m.module_key) : null;
            _state.selId = m.id;
        } else {
            f.module_key.value = '';
            f.title.value = '';
            f.description.value = '';
            f.role.value = 'body';
            f.topic.value = '';
            f.body.value = '';
            f.sort_order.value = 0;
            _state.selKey = null;
            _state.selId = null;
            _state.nachtragId = null;
        }
        // Build 575: EINE Regel fuer Sperre UND Hinweis - abgeleitet aus dem
        // Wert im Feld, nicht aus einem Zustandsfeld.
        _schluesselFeldStand();
        _setMsg('');
        renderDryRun(null);
        _markActive();
        // Build 577: die Vorschau folgt dem Formular - auch wenn es
        // programmatisch gefuellt wurde (Auswahl aus der Liste, Entwurf).
        // Programmatische .value-Zuweisungen loesen kein 'input' aus.
        _vorschauAktualisieren();
    }

    // _schluesselFeldStand: DIE EINZIGE Regel fuer Sperre und Hinweis des
    // Schluesselfeldes (Build 575).
    //
    // WARUM DAS NOETIG WAR: es gab DREI unabhaengige Ausdruecke dafuer -
    // _fillForm mit Modul (disabled = hatKey), _fillForm ohne Modul
    // (disabled = false) und die Entwurfs-Wiederherstellung
    // (disabled = selKey !== null). Der dritte kannte den Nachtragsmodus
    // nicht. Ein Entwurf aus der Zeit VOR Build 565 traegt selKey als die
    // Zeichenkette "null" (damals: String(m.module_key)) und ein leeres
    // module_key-Feld - beim Wiederherstellen ergab das genau das von mc
    // gemeldete Bild: GESPERRT UND LEER, also wieder die Sackgasse.
    //
    // Die neue Regel leitet den Zustand aus dem WERT ab und nicht aus einem
    // Zustandsfeld: ein Feld mit Schluessel ist fest, ein leeres ist offen.
    // Damit kann kein Zustand aus irgendeiner Quelle mehr eine Sperre
    // erzeugen, hinter der nichts steht.
    function _schluesselFeldStand() {
        var f = _state.fields;
        if (!f || !f.module_key) { return; }
        var wert = String(f.module_key.value || '').trim();
        var nachtrag = !!_state.nachtragId;
        f.module_key.disabled = (!nachtrag && wert !== '');
        _renderKeyHinweis();
    }

    // _renderKeyHinweis: erklaert den Zustand des Schluesselfeldes.
    // ------------------------------------------------------------------
    // BUILD 577 - VORSCHAU DES BAUSTEINS.
    //
    // Zeigt den Baustein so, wie ihn der Ermittler spaeter IM BERICHTSEDITOR
    // sieht: Editor.js im Nur-Lese-Modus, Platzhalter als Chips. Die
    // Umschaltung 'Vorschau / Rohansicht' merkt sich NICHTS - sie ist ein
    // Moment, keine Vorliebe. Die Rohansicht bleibt erreichbar, damit dem
    // Redakteur der genaue Text nicht genommen wird.
    // ------------------------------------------------------------------
    function _vorschauAufbauen(form) {
        var kopf = document.createElement('div');
        kopf.className = 'aiw-mod-vorschau-kopf';
        var titel = document.createElement('span');
        titel.className = 'aiw-mod-vorschau-titel';
        titel.textContent = 'Vorschau (Ansicht im Berichtseditor)';
        kopf.appendChild(titel);
        var schalter = document.createElement('button');
        schalter.type = 'button';
        schalter.className = 'aiw-btn aiw-btn-klein';
        schalter.id = 'aiw-mod-vorschau-schalter';
        schalter.textContent = 'Rohansicht';
        kopf.appendChild(schalter);
        form.appendChild(kopf);

        var host = document.createElement('div');
        host.className = 'aiw-mod-vorschau';
        host.id = 'aiw-mod-vorschau';
        form.appendChild(host);
        _state.vorschauEl = host;

        var vs = (typeof window !== 'undefined')
            ? window.AIWBausteinVorschau : null;
        if (vs && typeof vs.erzeuge === 'function') {
            _state.vorschau = vs.erzeuge(host, {});
        } else {
            // KEIN STILLER AUSFALL - die Flaeche sagt, was fehlt.
            host.textContent = 'Vorschau-Modul nicht geladen '
                + '(cockpit_baustein_vorschau.js).';
            host.classList.add('ist-warnung');
        }

        schalter.addEventListener('click', function () {
            _state.vorschauAn = !_state.vorschauAn;
            schalter.textContent = _state.vorschauAn ? 'Rohansicht' : 'Vorschau';
            host.hidden = !_state.vorschauAn;
            if (_state.vorschauAn) { _vorschauAktualisieren(); }
            else if (_state.vorschau) { _state.vorschau.aus(); }
        });
    }

    // _vorschauAktualisieren: aus dem AKTUELLEN Formularzustand, nicht aus dem
    // gespeicherten Datensatz - der Redakteur soll sehen, was er gerade tippt.
    function _vorschauAktualisieren() {
        if (!_state.vorschauAn || !_state.vorschau || !_state.fields) { return; }
        var f = _state.fields;
        _state.vorschau.zeige({ body: f.body ? f.body.value : '' });
    }

    function _renderKeyHinweis() {
        var el = _state.keyHinweisEl;
        if (!el) { return; }
        el.classList.remove('aiw-mod-keyhinweis-warn');
        if (_state.nachtragId) {
            el.textContent = 'Dieser Baustein stammt aus der Zeit vor der '
                + 'Schluessel-Einfuehrung und hat noch keine Kennung. Ohne sie '
                + 'ist weder Vorschau noch Aenderung moeglich. Der Vorschlag '
                + 'ist aus dem Titel gebildet und frei aenderbar — nach dem '
                + 'Speichern ist die Kennung ENDGUELTIG, weil '
                + 'Berichtsvorlagen ueber sie auf den Baustein verweisen.';
            el.classList.add('aiw-mod-keyhinweis-warn');
        } else if (_state.selKey) {
            el.textContent = 'Die Kennung ist fest: Berichtsvorlagen verweisen '
                + 'ueber sie auf diesen Baustein.';
        } else if (_state.selId) {
            // Ein bestehendes Modul ohne Kennung, dessen Zeilen-id wir NICHT
            // kennen (alter Entwurf). Speichern wuerde hier eine ZWEITE Zeile
            // anlegen statt die alte zu ergaenzen - deshalb der ausdrueckliche
            // Hinweis, das Modul neu aus der Liste zu waehlen.
            el.textContent = 'Dieser Entwurf stammt aus einer aelteren Fassung '
                + 'und kann die Kennung nicht sicher zuordnen. Bitte den '
                + 'Baustein links erneut anklicken, dann wird sie korrekt '
                + 'nachgetragen.';
            el.classList.add('aiw-mod-keyhinweis-warn');
        } else {
            el.textContent = 'Kennung frei waehlbar; nach dem ersten Speichern '
                + 'bleibt sie unveraendert.';
        }
    }

    function _currentFields() {
        var f = _state.fields;
        return {
            id: _state.nachtragId,
            module_key: f.module_key.value,
            title: f.title.value,
            description: f.description.value,
            role: f.role.value,
            topic: f.topic.value,
            body: f.body.value,
            sort_order: f.sort_order.value
        };
    }

    function _markActive() {
        if (!_state.listEl) { return; }
        var items = _state.listEl.querySelectorAll('.aiw-mod-item');
        Array.prototype.forEach.call(items, function (it) {
            var kennung = _state.selKey !== null
                ? _state.selKey
                : (_state.selId ? ('#id:' + _state.selId) : null);
            var on = (kennung !== null
                && it.getAttribute('data-key') === kennung);
            it.classList.toggle('is-active', on);
        });
    }

    function _setMsg(text, kind) {
        if (!_state.msgEl) { return; }
        _state.msgEl.textContent = text || '';
        _state.msgEl.className = 'aiw-mod-msg' + (kind ? (' is-' + kind) : '');
    }

    // renderDryRun: Ergebnis der schreibfreien Vorschau. res=null leert. Fehler
    // (rot) haben Vorrang vor der Platzhalter-Zusammenfassung (gruen) —
    // Grundregel 1: Fehler nie still schlucken.
    function renderDryRun(res) {
        var box = _state.dryEl;
        if (!box) { return; }
        _clearNode(box);
        if (!res) { return; }
        var errs = errorsText(res.errors);
        if (errs) {
            var pe = document.createElement('p');
            pe.className = 'aiw-mod-dry is-err';
            pe.textContent = 'Nicht gueltig: ' + errs;
            box.appendChild(pe);
            return;
        }
        var ps = document.createElement('p');
        ps.className = 'aiw-mod-dry is-ok';
        var txt = summaryText(res.summary);
        ps.textContent = 'Felder OK' + (txt
            ? (' — Platzhalter: ' + txt)
            : ' — keine Platzhalter im Text.');
        box.appendChild(ps);
    }

    function dryRunError(msg) {
        var box = _state.dryEl;
        if (!box) { return; }
        _clearNode(box);
        var p = document.createElement('p');
        p.className = 'aiw-mod-dry is-err';
        p.textContent = 'Vorschau fehlgeschlagen: ' + (msg || 'unbekannt');
        box.appendChild(p);
    }

    function saved(res) {
        var created = !!(res && res.created);
        var tid = (res && res.target_id) ? res.target_id : '?';
        _setMsg('Baustein "' + tid + '" '
            + (created ? 'angelegt.' : 'geaendert.'), 'ok');
        _clearDraft();   // Build 488: gespeichert -> Zwischenspeicher verwerfen.
    }

    function saveError(msg) {
        _setMsg('Speichern fehlgeschlagen: ' + (msg || 'unbekannt'), 'err');
    }

    // --- Browser-Zwischenspeicher des Entwurfs (Build 488) ---------------
    function _draftFromState() {
        return { v: 1, fields: _currentFields(), selKey: _state.selKey,
                 selId: _state.selId, nachtragId: _state.nachtragId };
    }
    function _persistDraft() {
        var ls = _ls();
        if (!ls || !_state.fields) { return; }
        try { ls.setItem(DRAFT_KEY, JSON.stringify(_draftFromState())); }
        catch (e) { log('persistDraft', e); }
    }
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
    function _clearDraft() {
        var ls = _ls();
        if (!ls) { return; }
        try { ls.removeItem(DRAFT_KEY); } catch (e) { log('clearDraft', e); }
    }
    // _restoreDraft: Entwurf laden, OHNE erneut zu persistieren. module_key ist
    // der Schluessel: im Editier-Modus (selKey gesetzt) fix, sonst editierbar.
    function _restoreDraft(d) {
        var f = _state.fields;
        if (!f || !d) { return; }
        var fl = d.fields || {};
        f.module_key.value = fl.module_key || '';
        f.title.value = fl.title || '';
        f.description.value = fl.description || '';
        f.role.value = fl.role || 'body';
        f.topic.value = fl.topic || '';
        f.body.value = fl.body || '';
        f.sort_order.value = (fl.sort_order === undefined
            || fl.sort_order === null) ? 0 : fl.sort_order;
        _state.selKey = (d.selKey === undefined) ? null : d.selKey;
        _state.selId = (d.selId === undefined) ? null : d.selId;
        _state.nachtragId = (d.nachtragId === undefined) ? null : d.nachtragId;
        // Build 575: KEINE eigene Sperrlogik mehr. Ein Entwurf aus einer
        // aelteren Fassung kann selKey als Zeichenkette "null" tragen; das
        // wird hier abgefangen, damit daraus keine Sperre ohne Inhalt wird.
        if (_state.selKey === 'null' || _state.selKey === 'undefined'
                || _state.selKey === '') {
            _state.selKey = null;
        }
        _schluesselFeldStand();
        _vorschauAktualisieren();
        renderDryRun(null);
        _markActive();
        _setMsg('Nicht gespeicherter Entwurf aus dem Browserspeicher '
            + 'wiederhergestellt. Speichern schliesst ihn ab.', '');
    }

    // renderModules: Gesamtsicht. data = {count, modules}. opts:
    //   onDryRun(payload) — schreibfreie Vorschau (cockpit.js -> POST)
    //   onSave(payload)   — auditiertes Speichern (cockpit.js -> POST)
    function renderModules(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        _clearNode(mainEl);

        var wrap = document.createElement('div');
        wrap.className = 'aiw-mod-wrap';

        var h = document.createElement('h2');
        h.className = 'aiw-pagetitle';
        h.textContent = 'Baustein-Module';
        // Build 598 (Baustelle H / H9): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'modules.titel');
        wrap.appendChild(h);
        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'modules.hinweis');
        sub.textContent = 'Wiederverwendbare Textbausteine pflegen. Der Text '
            + '(body) ist Freitext und darf Platzhalter wie {{a:name}} / '
            + '{{m:name}} / {{o:name}} enthalten; diese werden erst beim Rendern '
            + 'des konkreten Berichts aufgeloest. Vor dem Speichern mit '
            + '"Vorschau" pruefen.';
        wrap.appendChild(sub);

        var body = document.createElement('div');
        body.className = 'aiw-mod-body';

        // --- Linke Spalte: Liste + "Neu".
        var left = document.createElement('div');
        left.className = 'aiw-mod-listcol';
        var newBtn = document.createElement('button');
        newBtn.type = 'button';
        newBtn.className = 'aiw-mod-new';
        newBtn.textContent = '+ Neuer Baustein';
        newBtn.addEventListener('click', function () {
            _fillForm(null);
            _persistDraft();   // Build 488: Neu-Modus als aktuellen Entwurf sichern.
        });
        left.appendChild(newBtn);

        var list = document.createElement('div');
        list.className = 'aiw-mod-list';
        _state.listEl = list;
        var rows = sortModules(data && data.modules);
        if (!rows.length) {
            var empty = document.createElement('p');
            empty.className = 'aiw-mod-empty';
            empty.textContent = 'Noch keine Bausteine angelegt.';
            list.appendChild(empty);
        }
        rows.forEach(function (m) {
            var it = document.createElement('button');
            it.type = 'button';
            it.className = 'aiw-mod-item';
            // Altzeilen haben keinen Schluessel - dann traegt der
            // Eintrag seine id, damit die Markierung nicht auf dem
            // Text 'null' beruht.
            it.setAttribute('data-key', m.module_key
                ? String(m.module_key) : ('#id:' + m.id));
            it.textContent = moduleLabel(m);
            it.addEventListener('click', function () {
                _fillForm(m);
                _persistDraft();   // Build 488: geladenen Baustein als Entwurf sichern.
            });
            list.appendChild(it);
        });
        left.appendChild(list);
        body.appendChild(left);

        // --- Rechte Spalte: Editor-Maske.
        var form = document.createElement('div');
        form.className = 'aiw-mod-form';

        var fKey = _labeledField(form, 'module_key (A-Z a-z 0-9 . _ -)', 'text',
            'aiw-mod-key');
        // Build 565: Hinweiszeile DIREKT unter dem Feld. Sie sagt, warum das
        // Feld gerade gesperrt oder offen ist - ein Feld, das mal geht und mal
        // nicht, ohne dass jemand sagt warum, wirkt kaputt.
        var keyHinweis = document.createElement('p');
        keyHinweis.className = 'aiw-mod-keyhinweis';
        form.appendChild(keyHinweis);
        _state.keyHinweisEl = keyHinweis;
        _state.vorschauEl = null;
        _state.vorschau = null;
        _state.vorschauAn = true;
        var fTitle = _labeledField(form, 'Titel', 'text', 'aiw-mod-title');
        var fRole = _labeledField(form, 'Rolle', 'select', 'aiw-mod-role');
        ROLES.forEach(function (r) {
            var opt = document.createElement('option');
            opt.value = r;
            opt.textContent = roleLabel(r);
            fRole.appendChild(opt);
        });
        var fTopic = _labeledField(form, 'Thema (topic)', 'text', 'aiw-mod-topic');
        var fDesc = _labeledField(form, 'Beschreibung (optional)', 'textarea',
            'aiw-mod-desc');
        fDesc.rows = 2;
        var fBody = _labeledField(form, 'Bausteintext (body)', 'textarea',
            'aiw-mod-bodytext');
        var fSort = _labeledField(form, 'Sortierung', 'number', 'aiw-mod-sort');

        // Aktionen: Vorschau + Speichern + Rueckmeldung + Ausgabe.
        var actions = document.createElement('div');
        actions.className = 'aiw-mod-actions';
        var dryBtn = document.createElement('button');
        dryBtn.type = 'button';
        dryBtn.className = 'aiw-mod-drybtn';
        dryBtn.textContent = 'Vorschau (schreibfrei)';
        actions.appendChild(dryBtn);
        var saveBtn = document.createElement('button');
        saveBtn.type = 'button';
        saveBtn.className = 'aiw-mod-save';
        saveBtn.textContent = 'Speichern (auditiert)';
        actions.appendChild(saveBtn);
        var msg = document.createElement('span');
        msg.className = 'aiw-mod-msg';
        _state.msgEl = msg;
        actions.appendChild(msg);
        form.appendChild(actions);

        var dry = document.createElement('div');
        dry.className = 'aiw-mod-dryout';
        _state.dryEl = dry;
        form.appendChild(dry);

        body.appendChild(form);
        wrap.appendChild(body);
        mainEl.appendChild(wrap);

        _state.fields = {
            module_key: fKey, title: fTitle, role: fRole, topic: fTopic,
            description: fDesc, body: fBody, sort_order: fSort
        };

        // Build 488: jede Nutzer-Eingabe sichert den Stand (programmatische
        // .value-Zuweisungen loesen kein input/change aus -> kein Ueberschreiben).
        form.addEventListener('input', _persistDraft);
        form.addEventListener('change', _persistDraft);

        // BUILD 577: DIE VORSCHAU ENTSTEHT ERST JETZT — nach mainEl.appendChild.
        // Editor.js misst beim Aufbau die Groesse seines Behaelters; auf einem
        // noch nicht eingehaengten Element sind das NULL Pixel, und es zeichnet
        // ins Nichts. Genau dieser Fehler hat in Build 570 bis 573 die
        // Kacheldiagramme unsichtbar gemacht; die Lehre steht hier als Zeile.
        _vorschauAufbauen(form);

        // Beim Tippen mitlaufen, aber entprellt: Editor.js baut je Aktualisierung
        // eine Instanz auf, und das bei jedem Tastendruck waere Verschwendung.
        var vsTimer = null;
        fBody.addEventListener('input', function () {
            if (vsTimer) { clearTimeout(vsTimer); }
            vsTimer = setTimeout(_vorschauAktualisieren, 350);
        });

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

        _fillForm(null);
        // Build 488: noch nicht gespeicherter Entwurf aus dem Browserspeicher
        // hat Vorrang vor dem leeren Neu-Modus (Neuladen verliert keine Arbeit).
        var _saved = _loadDraft();
        if (_saved) { _restoreDraft(_saved); }
        log('renderModules:', rows.length, 'Bausteine');
        return wrap;
    }

    function cleanup() {
        _state.listEl = null;
        _state.fields = null;
        _state.msgEl = null;
        _state.dryEl = null;
        _state.selKey = null;
        _state.selId = null;
        _state.nachtragId = null;
    }

    // -------------------------------------------------------------------------
    // OEFFENTLICHE API. Reine Funktionen zuerst (vitest), dann DOM.
    // -------------------------------------------------------------------------
    window.AIWCockpitModules = {
        // reine Funktionen (vitest)
        roleLabel: roleLabel,
        moduleLabel: moduleLabel,
        sortModules: sortModules,
        isValidKey: isValidKey,
        buildPayload: buildPayload,
        schluesselVorschlag: schluesselVorschlag,
        _vorschauAktualisieren: _vorschauAktualisieren,
        _schluesselFeldStand: _schluesselFeldStand,
        summaryText: summaryText,
        errorsText: errorsText,
        ROLES: ROLES,
        DRAFT_KEY: DRAFT_KEY,             // Browser-Zwischenspeicher (Build 488)
        // DOM
        renderModules: renderModules,
        renderDryRun: renderDryRun,
        dryRunError: dryRunError,
        saved: saved,
        saveError: saveError,
        cleanup: cleanup
    };
})();
