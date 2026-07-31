// =============================================================================
// management/server/static/cockpit_alias.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Aliasse (AP-2A)
// =============================================================================
// Zweck (Idee 8, Frontend zu Build 504):
//   Rendert den GLOBALEN ALIAS-KATALOG (/api/alias) — die fallUEBERGREIFENDE
//   Erkenntnis "Forenkonto <subject_id> tritt AUSSERDEM unter dem Namen <alias>
//   auf". Mit dem Recht crossref.edit koennen Aliasse angelegt, in Art/Basis/
//   Notiz geaendert, WIDERRUFEN und wieder zurueckgenommen werden.
//
// WARUM EINE EIGENE SICHT (und kein Anbau an "Kreuzbezug"):
//   Aliasse existieren UNABHAENGIG vom Identitaetskatalog — ein Konto kann fuenf
//   Aliasse und KEINE Identifizierung haben. Ein Anbau an die Kreuzbezug-Tabelle
//   haette genau diese Faelle unsichtbar gemacht (Grundregel 1). Ausserdem ist
//   die RUECKWAERTSSUCHE ("welches Konto fuehrt diesen Namen?") eine eigene
//   Arbeitsweise mit eigener Eingabemaske. Beide Sichten teilen sich das Recht
//   crossref.view/edit und stehen nebeneinander in der Gruppe "Auswertung".
//
// Datenform GET /api/alias (ManagementApp._alias):
//   { entries: [ {id, subject_id, alias, alias_norm, kind_code, kind_label,
//                 basis, note, is_active, retracted_reason, created_at,
//                 updated_at, audit_seq, created_audit_seq}, ... ],
//     counts: {total, aktiv, widerrufen, subjects},
//     mode: 'all' | 'subject' | 'search',
//     kinds: [ {code, label}, ... ] }
//   Die ARTEN-LISTE kommt bewusst vom SERVER: so kann die Oberflaeche keine
//   Auswahl anbieten, die die DDL-CHECK (M022) spaeter ablehnen wuerde. Faellt
//   sie aus, greift KINDS_FALLBACK — dann ist die Auswahl im Zweifel zu klein,
//   nie zu gross.
//
// SCHREIBEN (opts -> cockpit.js -> postJson mit X-AIW-Token):
//   onAdd({subject_id, alias, kind_code, basis, note}) -> /api/alias/add
//   onUpdate({alias_id, kind_code, basis, note})       -> /api/alias/update
//   onRetract({alias_id, reason})                      -> /api/alias/retract
//   onReinstate({alias_id})                            -> /api/alias/reinstate
//   KEIN optimistisches UI: nach jedem Schreiben laedt cockpit.js die Sicht NEU
//   (der Server bleibt die Wahrheit — auch bei einem abgelehnten Duplikat).
//
// SENSIBILITAET: alias/basis/note sind Freitext, der eine reale Person
//   identifizierbar machen KANN. Das Frontend reicht nur durch; der Ausschluss
//   aus dem Audit-Payload liegt im Server-Repo (subject_alias_repo.py).
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS: (1) IIFE + 'use strict'. (2) DEV-Logging
//   (AIW_COCKPIT_DEBUG). (3) ausfuehrliche Kommentare. (4) reine Funktionen
//   fassen NIE das DOM an -> vitest; opts.doc injizierbar (JSDOM).
// SICHERHEIT (XSS): alle variablen Texte via textContent.
//
// BUILD 600 — NAMENSAUFLOESUNG (Auftrag mc 2026-07-26):
//   "Unsere Ermittler sind mit den Namen der Forennutzer vertraut, aber
//   nicht mit den user_id oder subject_id. [...] In jedem Fall ist es den
//   Anwendern nicht zuzumuten, die subject_id zu kennen."
//
//   DREI ERGAENZUNGEN, alle ueber GET /api/names (crossref.view):
//   1) Unter dem Feld 'subject_id' steht der aufgeloeste Benutzername —
//      MIT seiner Herkunft (Fallakte oder globale Namensliste). Reine
//      Kontrollanzeige: sie sagt, ob die richtige Nummer erwischt wurde,
//      BEVOR ein Beleg entsteht.
//   2) Daneben eine Namenssuche: Namen eintippen, Treffer waehlen, die
//      Kennung wird gesetzt. Der Ermittler muss sie nie selbst kennen.
//   3) Unter der Katalogsuche das Ergebnis derselben Aufloesung — der
//      Katalog kennt nur ERFASSTE Aliasse, die Suche meint aber meist
//      den Namen als solchen.
//
//   DIE KASKADE UND IHR PREIS: gesucht wird erst in der Fallakte, dann
//   in der globalen Namensliste (Festlegung mc 2026-07-26). Eine
//   Kaskade, die schweigt, sieht aus wie ein vollstaendiges Ergebnis —
//   deshalb nennt 'kaskadenText' die ZAHL der nicht gelisteten Treffer
//   der zweiten Stufe. Und weil Namen OHNE Forenkonto (die 'Geister')
//   in KEINER Quelle dieses Servers stehen, traegt jede Antwort den
//   Hinweis, dass ein Leerbefund 'in den abgefragten Quellen nicht
//   gefunden' heisst und nicht 'gibt es nicht' (Grundregel 1).
//
// Version: v0.8.600 · 2026-07-26
//   Build 505: Erstfassung der Sicht (AP-2A, Idee 8)
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
        args.unshift('[AIW-Alias]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '—';

    // Notnagel, falls der Server die Arten-Liste einmal nicht mitliefert.
    // Deckungsgleich mit ALIAS_KINDS (subject_alias_repo.py) und der
    // DDL-CHECK in m022 — im Zweifel lieber zu klein als zu gross.
    var KINDS_FALLBACK = [
        { code: 'forenname', label: 'weiterer Forenname' },
        { code: 'handle', label: 'Handle/Nickname ausserhalb des Forums' },
        { code: 'signatur', label: 'Name aus einer Signatur' },
        { code: 'kontakt', label: 'Kontaktkennung (Messenger, Mail, o. ae.)' },
        { code: 'sonstiges', label: 'sonstiger Bezug' }
    ];

    // ------------------------------------------------------------------ Helfer
    // (rein — kein DOM, damit unter vitest direkt pruefbar)

    // entries/kinds/counts: robuste Extraktion der Datenform. Ein fehlendes
    // Feld darf nie einen TypeError werfen und die ganze Sicht killen.
    function entries(data) {
        return (data && Array.isArray(data.entries)) ? data.entries : [];
    }
    function kinds(data) {
        return (data && Array.isArray(data.kinds) && data.kinds.length)
            ? data.kinds : KINDS_FALLBACK;
    }
    function counts(data) {
        var c = (data && data.counts) ? data.counts : {};
        return {
            total: parseInt(c.total, 10) || 0,
            aktiv: parseInt(c.aktiv, 10) || 0,
            widerrufen: parseInt(c.widerrufen, 10) || 0,
            subjects: parseInt(c.subjects, 10) || 0
        };
    }

    // countsText: Kopfzeile. Beschreibt den Katalog in einem Satz.
    function countsText(data) {
        var c = counts(data);
        return c.aktiv + ' aktiv · ' + c.widerrufen + ' widerrufen · '
            + c.subjects + ' Konten betroffen (gesamt ' + c.total + ')';
    }

    // kindLabel: Anzeigetext einer Art (unbekannt -> Rohwert, nie leer).
    function kindLabel(code, kindList) {
        var list = kindList || KINDS_FALLBACK;
        for (var i = 0; i < list.length; i++) {
            if (list[i] && list[i].code === code) { return list[i].label; }
        }
        return String(code == null ? '' : code);
    }

    // statusClass: CSS-Suffix. Widerrufene Zeilen werden gedimmt dargestellt —
    // sie sind ein anderer Erkenntnisstand, kein Leerbefund.
    function statusClass(isActive) {
        return isActive ? 'aiw-alias-aktiv' : 'aiw-alias-widerrufen';
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

    // buildAddPayload: Formularfelder -> POST-Body. REIN. subject_id nur dann
    // als Zahl, wenn die Eingabe VOLLSTAENDIG ganzzahlig war (sonst null, damit
    // '47xy' nicht still zu 47 wird — das waere ein falsches Konto!).
    // Wirft NICHT; die Pflichtfeld-Pruefung macht der Aufrufer bzw. verbindlich
    // der Server.
    function buildAddPayload(fields) {
        fields = fields || {};
        var raw = (fields.subject_id == null) ? '' : String(fields.subject_id);
        var trimmed = raw.trim();
        var sid = parseInt(trimmed, 10);
        var note = (fields.note == null) ? '' : String(fields.note).trim();
        var body = {
            subject_id: (String(sid) === trimmed && !isNaN(sid)) ? sid : null,
            alias: String(fields.alias || '').trim(),
            kind_code: String(fields.kind_code || ''),
            basis: String(fields.basis || '').trim()
        };
        if (note !== '') { body.note = note; }
        return body;
    }

    // validateAdd: Vorpruefung im Browser (der Server bleibt verbindlich).
    // Gibt eine Fehlermeldung oder null zurueck. REIN.
    function validateAdd(body) {
        if (!body || body.subject_id == null) {
            return 'subject_id fehlt oder ist keine ganze Zahl.';
        }
        if (!body.alias) { return 'Der Alias darf nicht leer sein.'; }
        if (!body.kind_code) { return 'Bitte eine Alias-Art waehlen.'; }
        return null;
    }

    // =========================================================================
    // NAMENSAUFLOESUNG (Build 600) — reine Funktionen.
    //
    // ANLASS (mc 2026-07-26): "Unsere Ermittler sind mit den Namen der
    // Forennutzer vertraut, aber nicht mit den user_id oder subject_id. [...]
    // In jedem Fall ist es den Anwendern nicht zuzumuten, die subject_id zu
    // kennen."
    //
    // Die Texte stehen HIER und nicht im DOM-Teil, damit vitest sie prueft:
    // gerade die Unterscheidung "nicht gefunden" vs. "nicht abgefragt" ist
    // eine Aussage mit forensischem Gewicht und keine Kosmetik.
    // =========================================================================

    // aufloesungText: was unter dem subject_id-Feld steht.
    //   -> { text, art }   art: 'ok' | 'leer' | 'fehler' | 'wartet'
    //
    // DREI ZUSTAENDE, DIE NICHT VERWECHSELT WERDEN DUERFEN:
    //   'ok'     — ein Name ist da, MIT seiner Quelle. Die Quelle gehoert
    //              dazu: ein Name aus der Fallakte ist ein anderer Beleg als
    //              einer aus der globalen Namensliste.
    //   'leer'   — in den ABGEFRAGTEN Quellen nichts gefunden. Das ist NICHT
    //              "gibt es nicht" — die Geister (Namen ohne Forenkonto)
    //              stehen in keiner Quelle dieses Servers.
    //   'fehler' — eine Quelle war nicht abfragbar. Das darf NIE wie ein
    //              Leerbefund aussehen (Grundregel 1).
    function aufloesungText(data) {
        if (!data) { return { text: '', art: 'wartet' }; }
        if (data.fehler) {
            return { text: 'Name nicht auflösbar: ' + String(data.fehler),
                     art: 'fehler' };
        }
        if (data.gefunden === true && data.name) {
            var t = '„' + String(data.name) + '"';
            if (data.quelle_label) { t += ' — ' + String(data.quelle_label); }
            if (data.aliasse && data.aliasse.length) {
                t += ' · Aliasse: ' + data.aliasse.join(', ');
            }
            return { text: t, art: 'ok' };
        }
        // Nicht gefunden. Die HINWEISE sind hier die eigentliche Information
        // (fehlende default.db, Geisterband, …) und werden mitgezeigt.
        var txt = 'Kein Name gefunden — in den abgefragten Quellen.';
        var h = (data.hinweise || []);
        if (h.length) { txt += ' ' + h.join(' '); }
        return { text: txt, art: (h.length ? 'fehler' : 'leer') };
    }

    // trefferLabel: eine Zeile der Namenssuche.
    function trefferLabel(t) {
        if (!t) { return ''; }
        return String(t.name || '?') + '  (subject_id ' + t.subject_id + ')';
    }

    // kaskadenText: die Zusammenfassung ueber der Trefferliste.
    //
    // WARUM DIE ZWEITE ZAHL DA STEHT: die Suche laeuft als KASKADE (erst
    // Fallakte, dann globale Namensliste — Festlegung mc 2026-07-26). Eine
    // Kaskade, die schweigt, sieht aus wie ein vollstaendiges Ergebnis. Der
    // gesuchte Zweitaccount ist aber genau der Treffer, den sie verschweigen
    // wuerde. Deshalb nennt die Zeile die Zahl der NICHT gelisteten Treffer.
    function kaskadenText(data) {
        if (!data) { return ''; }
        var n = (data.treffer || []).length;
        var teile = [];
        if (n === 0) {
            teile.push('Kein Treffer in ' + (data.quelle_label || 'der Quelle')
                       + '.');
        } else {
            teile.push(n + ' Treffer in ' + (data.quelle_label || '?')
                       + (data.gekuerzt
                          ? ' (von ' + data.gesamt + ' — Liste gekürzt)' : ''));
        }
        var w = (data.weitere_treffer || {});
        if (w.forenkonto) {
            teile.push('Außerdem ' + w.forenkonto + ' Treffer in der globalen '
                       + 'Namensliste der Forenkonten — hier nicht gelistet '
                       + '(die Suche endet bei der ersten Quelle mit Treffer).');
        }
        (data.hinweise || []).forEach(function (h) { teile.push(h); });
        return teile.join(' ');
    }

    // =========================================================================
    // 1) DOM: Sicht rendern.
    // =========================================================================
    function renderAlias(mainEl, data, opts) {
        opts = opts || {};
        var doc = opts.doc
            || (typeof document !== 'undefined' ? document : null);
        if (!mainEl || !doc) { return { setResult: function () {} }; }
        var canEdit = opts.canEdit === true;
        var kindList = kinds(data);

        mainEl.textContent = '';

        var h = doc.createElement('h2');
        // Build 604 (Baustelle H / H13): literale Hilfe-Marken.
        h.className = 'aiw-pagehead';
        h.setAttribute('data-hilfe-id', 'alias.titel');
        h.textContent = 'Aliasse — globaler Namenskatalog';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.setAttribute('data-hilfe-id', 'alias.kennzeile');
        sub.textContent = 'Weitere Namen/Handles eines Forenkontos, '
            + 'fallübergreifend. Gross-/Kleinschreibung wird beim Abgleich '
            + 'nicht unterschieden. Jede Anlage, Änderung und jeder Widerruf '
            + 'wird auditiert; gelöscht wird nie.';
        mainEl.appendChild(sub);

        var head = doc.createElement('p');
        head.className = 'aiw-alias-counts';
        head.setAttribute('data-hilfe-id', 'alias.zahlen');
        head.textContent = countsText(data);
        mainEl.appendChild(head);

        // --- Ergebniszeile ---------------------------------------------------
        var result = doc.createElement('div');
        result.className = 'aiw-alias-result';
        result.id = 'aiw-alias-result';
        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }

        mainEl.appendChild(_searchBar(doc, opts));

        // --- Build 600: Namensauflösung zur Katalogsuche ------------------
        // Der Katalog kennt nur Namen, die jemand ALS ALIAS erfasst hat. Wer
        // hier sucht, meint aber meist den Namen als solchen. Deshalb steht
        // unter der Suche das Ergebnis der Namensauflösung (Fallakte, dann
        // globale Namensliste der Forenkonten) — mit ihrer Herkunft und mit
        // dem, was die Kaskade NICHT gelistet hat.
        if (opts.query && opts.namen) {
            mainEl.appendChild(_namensBlock(doc, opts));
        }

        if (canEdit) {
            mainEl.appendChild(_form(doc, kindList, setResult, opts));
        } else {
            var ro = doc.createElement('p');
            ro.className = 'aiw-pagesub aiw-alias-readonly';
            ro.textContent = 'Nur lesend — zum Pflegen fehlt das Recht '
                + '„crossref.edit“.';
            mainEl.appendChild(ro);
        }
        mainEl.appendChild(result);

        // --- Fehlerzustand ---------------------------------------------------
        // Ein Ladefehler ist KEIN Leerbefund: er bekommt eine eigene Anzeige,
        // damit niemand "keine Aliasse" liest, wo "nicht abrufbar" gilt.
        if (data && data.error) {
            var err = doc.createElement('p');
            err.className = 'aiw-alias-error';
            err.textContent = 'Katalog nicht abrufbar: ' + String(data.error);
            mainEl.appendChild(err);
            return { setResult: setResult };
        }

        // --- Tabelle ---------------------------------------------------------
        var rows = entries(data);
        if (rows.length === 0) {
            var empty = doc.createElement('p');
            empty.className = 'aiw-placeholder';
            empty.textContent = (opts.query)
                ? 'Kein Konto führt diesen Namen.'
                : 'Noch kein Alias im Katalog.';
            mainEl.appendChild(empty);
            log('renderAlias: leer, canEdit', canEdit, 'query', opts.query);
            return { setResult: setResult };
        }

        var table = doc.createElement('table');
        table.className = 'aiw-alias-table';
        var thead = doc.createElement('thead');
        var htr = doc.createElement('tr');
        ['subject_id', 'Alias', 'Art', 'Basis', 'Status', 'geändert', '']
            .forEach(function (label) {
                var th = doc.createElement('th');
                th.textContent = label;
                htr.appendChild(th);
            });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = doc.createElement('tbody');
        rows.forEach(function (e) {
            tbody.appendChild(_rowEl(doc, e, kindList, canEdit, setResult,
                                     opts));
        });
        table.appendChild(tbody);
        mainEl.appendChild(table);

        log('renderAlias:', rows.length, 'Eintraege, canEdit', canEdit);
        return { setResult: setResult };
    }

    // _searchBar: Rueckwaertssuche + Umschalter "Widerrufene zeigen".
    // Die Suche ist der eigentliche Ermittlungsnutzen: ein Name aus Fall A
    // fuehrt zu einem Konto in Fall B.
    function _searchBar(doc, opts) {
        var box = doc.createElement('div');
        box.className = 'aiw-alias-search';

        var lbl = doc.createElement('label');
        lbl.className = 'aiw-alias-lbl';
        lbl.textContent = 'Suche (Name oder subject_id): ';
        var inp = doc.createElement('input');
        inp.type = 'text';
        inp.id = 'aiw-alias-q';
        inp.setAttribute('data-hilfe-id', 'alias.bedienung.suche');
        inp.className = 'aiw-alias-input';
        inp.value = opts.query || '';
        lbl.appendChild(inp);
        box.appendChild(lbl);

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-alias-search-btn';
        btn.className = 'aiw-btn aiw-alias-btn';
        btn.textContent = 'Suchen';
        btn.addEventListener('click', function () {
            if (typeof opts.onSearch === 'function') {
                opts.onSearch(inp.value);
            }
        });
        box.appendChild(btn);

        var clear = doc.createElement('button');
        clear.type = 'button';
        clear.id = 'aiw-alias-clear-btn';
        clear.setAttribute('data-hilfe-id', 'alias.bedienung.ganzer_katalog');
        clear.className = 'aiw-btn aiw-alias-btn';
        clear.textContent = 'Ganzer Katalog';
        clear.addEventListener('click', function () {
            if (typeof opts.onSearch === 'function') { opts.onSearch(''); }
        });
        box.appendChild(clear);

        var tog = doc.createElement('label');
        tog.className = 'aiw-alias-lbl aiw-alias-toggle';
        var cb = doc.createElement('input');
        cb.type = 'checkbox';
        cb.id = 'aiw-alias-incl';
        cb.setAttribute('data-hilfe-id', 'alias.bedienung.widerrufene');
        cb.checked = opts.includeRetracted === true;
        cb.addEventListener('change', function () {
            if (typeof opts.onToggleRetracted === 'function') {
                opts.onToggleRetracted(cb.checked === true);
            }
        });
        tog.appendChild(cb);
        var tt = doc.createElement('span');
        tt.textContent = ' Widerrufene zeigen';
        tog.appendChild(tt);
        box.appendChild(tog);

        return box;
    }

    // _namensBlock: Ergebnis der Namensaufloesung unter der Katalogsuche
    // (Build 600). Ein Klick auf einen Treffer sucht den Katalog nach
    // DIESEM Konto ab — die Bruecke vom Namen zum Konto zum Aliaskatalog.
    function _namensBlock(doc, opts) {
        var daten = opts.namen || {};
        var box = doc.createElement('div');
        box.className = 'aiw-alias-namen';
        box.id = 'aiw-alias-namen';

        var kopf = doc.createElement('div');
        kopf.className = 'aiw-alias-namen-kopf';
        kopf.textContent = 'Namensauflösung: ' + kaskadenText(daten);
        kopf.setAttribute('data-hilfe-id',
                          'alias.abschnitt.namensaufloesung');
        box.appendChild(kopf);

        (daten.treffer || []).forEach(function (t) {
            var b = doc.createElement('button');
            b.type = 'button';
            b.className = 'aiw-alias-treffer-zeile';
            b.setAttribute('data-subject-id', String(t.subject_id));
            b.textContent = trefferLabel(t);
            b.title = String(t.detail || '');
            b.addEventListener('click', function () {
                if (typeof opts.onSubject === 'function') {
                    opts.onSubject(t.subject_id);
                }
            });
            box.appendChild(b);
        });

        // Der Quellen-Hinweis steht IMMER da — er ist der Unterschied zwischen
        // "gibt es nicht" und "hier nicht gesucht".
        if (daten.quellen_hinweis) {
            var fuss = doc.createElement('div');
            fuss.className = 'aiw-alias-namen-fuss';
            fuss.textContent = String(daten.quellen_hinweis);
            box.appendChild(fuss);
        }
        return box;
    }

    // _form: Anlage. Bewusst NUR Anlage — der Aliastext ist unveraenderlich
    // (Server-Regel: ein anderer Text ist eine andere Erkenntnis und entsteht
    // durch Widerruf + Neuanlage). Art/Basis/Notiz werden ueber die
    // Zeilen-Aktion "Ändern" gepflegt.
    function _form(doc, kindList, setResult, opts) {
        var box = doc.createElement('div');
        box.className = 'aiw-alias-form';

        var inSid = _field(doc, box, 'subject_id (Forenkonto): ',
            'aiw-alias-sid', 'text');

        // --- Build 600: RUECKWAERTS — Kennung eingetippt, Name darunter --
        // Reine Kontrollanzeige, kein Pflichtfeld. Sie sagt dem Ermittler, ob
        // er die richtige Nummer erwischt hat, BEVOR er einen Beleg erzeugt.
        var sidName = doc.createElement('div');
        sidName.className = 'aiw-alias-sidname';
        sidName.id = 'aiw-alias-sidname';
        sidName.setAttribute('data-hilfe-id', 'alias.aufloesung');
        box.appendChild(sidName);

        function zeigeAufloesung(daten) {
            var a = aufloesungText(daten);
            sidName.textContent = a.text;
            sidName.classList.remove('ok', 'leer', 'fehler', 'wartet');
            sidName.classList.add(a.art);
        }

        // Der Abruf laeuft entprellt: bei jedem Tastendruck eine Anfrage zu
        // schicken waere bei einer sechsstelligen Nummer ein halbes Dutzend
        // ueberfluessiger Abfragen. 350 ms sind lang genug fuer eine zuegige
        // Eingabe und kurz genug, um wie eine Sofortanzeige zu wirken.
        var entprellung = null;
        function aufloesenAnstossen() {
            var roh = String(inSid.value || '').trim();
            if (entprellung) { clearTimeout(entprellung); entprellung = null; }
            if (!roh) { zeigeAufloesung(null); return; }
            var sid = parseInt(roh, 10);
            if (String(sid) !== roh || isNaN(sid)) {
                // Keine ganze Zahl -> gar nicht erst fragen, aber SAGEN warum.
                sidName.textContent = 'Keine ganze Zahl — es wird nicht '
                    + 'aufgelöst.';
                sidName.classList.remove('ok', 'leer', 'fehler');
                sidName.classList.add('wartet');
                return;
            }
            sidName.textContent = 'Löse auf …';
            sidName.classList.remove('ok', 'leer', 'fehler');
            sidName.classList.add('wartet');
            entprellung = setTimeout(function () {
                if (typeof opts.onResolve === 'function') {
                    opts.onResolve(sid, zeigeAufloesung);
                } else {
                    zeigeAufloesung({ fehler: 'kein Auflösungspfad verdrahtet' });
                }
            }, 350);
        }
        inSid.addEventListener('input', aufloesenAnstossen);
        inSid.addEventListener('change', aufloesenAnstossen);

        // --- Build 600: VORWAERTS — Namen suchen, Kennung uebernehmen ----
        // Das ist der eigentliche Zweck des Auftrags: der Ermittler kennt den
        // NAMEN. Er tippt ihn hier ein, waehlt aus den Treffern, und die
        // Kennung wird gesetzt — er muss sie nie selbst kennen.
        var suchBox = doc.createElement('div');
        suchBox.className = 'aiw-alias-namensuche';

        var inSuche = _field(doc, suchBox, 'Konto über den Namen suchen: ',
            'aiw-alias-namesearch', 'text');

        var btnSuche = doc.createElement('button');
        btnSuche.type = 'button';
        btnSuche.id = 'aiw-alias-namesearch-btn';
        btnSuche.setAttribute('data-hilfe-id', 'alias.bedienung.kontosuche');
        btnSuche.className = 'aiw-btn aiw-alias-btn';
        btnSuche.textContent = 'Konto suchen';
        suchBox.appendChild(btnSuche);

        var trefferBox = doc.createElement('div');
        trefferBox.className = 'aiw-alias-treffer';
        trefferBox.id = 'aiw-alias-treffer';
        suchBox.appendChild(trefferBox);

        function zeigeTreffer(daten) {
            trefferBox.textContent = '';
            if (!daten) { return; }
            if (daten.fehler) {
                var e = doc.createElement('div');
                e.className = 'aiw-alias-treffer-kopf fehler';
                e.textContent = 'Suche fehlgeschlagen: ' + String(daten.fehler);
                trefferBox.appendChild(e);
                return;
            }
            var kopf = doc.createElement('div');
            kopf.className = 'aiw-alias-treffer-kopf';
            kopf.textContent = kaskadenText(daten);
            trefferBox.appendChild(kopf);

            (daten.treffer || []).forEach(function (t) {
                var b = doc.createElement('button');
                b.type = 'button';
                b.className = 'aiw-alias-treffer-zeile';
                b.setAttribute('data-subject-id', String(t.subject_id));
                b.textContent = trefferLabel(t);
                b.title = String(t.detail || '');
                b.addEventListener('click', function () {
                    // Uebernehmen heisst: Kennung setzen UND sofort
                    // rueckwaerts bestaetigen. Der Ermittler sieht damit an
                    // ZWEI Stellen dasselbe — die Uebernahme kann nicht
                    // unbemerkt die falsche Zeile erwischen.
                    inSid.value = String(t.subject_id);
                    aufloesenAnstossen();
                    setResult('Konto ' + t.subject_id + ' („' + t.name
                        + '") übernommen. Es wurde nichts geschrieben.', false);
                });
                trefferBox.appendChild(b);
            });
        }

        function sucheAnstossen() {
            var term = String(inSuche.value || '').trim();
            if (!term) {
                zeigeTreffer(null);
                setResult('Bitte einen Namen eingeben.', true);
                return;
            }
            trefferBox.textContent = 'Suche …';
            if (typeof opts.onNameSearch === 'function') {
                opts.onNameSearch(term, zeigeTreffer);
            } else {
                zeigeTreffer({ fehler: 'kein Suchpfad verdrahtet' });
            }
        }
        btnSuche.addEventListener('click', sucheAnstossen);
        inSuche.addEventListener('keydown', function (ev) {
            if (ev && ev.key === 'Enter') { sucheAnstossen(); }
        });

        box.appendChild(suchBox);

        var inAlias = _field(doc, box, 'Alias/Name: ', 'aiw-alias-name',
            'text');

        var lblK = doc.createElement('label');
        lblK.className = 'aiw-alias-lbl';
        lblK.textContent = 'Art: ';
        var selK = doc.createElement('select');
        selK.id = 'aiw-alias-kind';
        selK.setAttribute('data-hilfe-id', 'alias.bedienung.art');
        selK.className = 'aiw-alias-input';
        kindList.forEach(function (k) {
            var o = doc.createElement('option');
            o.value = k.code;
            o.textContent = k.label;
            selK.appendChild(o);
        });
        lblK.appendChild(selK);
        box.appendChild(lblK);

        var inBasis = _field(doc, box, 'Basis (Fundgrundlage): ',
            'aiw-alias-basis', 'text');
        var inNote = _field(doc, box, 'Notiz (optional): ', 'aiw-alias-note',
            'text');

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-alias-add';
        btn.setAttribute('data-hilfe-id', 'alias.bedienung.erfassen');
        btn.className = 'aiw-btn aiw-alias-btn';
        btn.textContent = 'Alias erfassen';
        btn.addEventListener('click', function () {
            var body = buildAddPayload({
                subject_id: inSid.value,
                alias: inAlias.value,
                kind_code: selK.value,
                basis: inBasis.value,
                note: inNote.value
            });
            var problem = validateAdd(body);
            if (problem) { setResult(problem, true); return; }
            setResult('Erfasse Alias …', null);
            if (typeof opts.onAdd === 'function') {
                opts.onAdd(body);
            } else {
                setResult('Kein Schreibpfad verdrahtet.', true);
            }
        });
        box.appendChild(btn);
        return box;
    }

    function _field(doc, parent, labelText, id, type) {
        var lbl = doc.createElement('label');
        lbl.className = 'aiw-alias-lbl';
        lbl.textContent = labelText;
        var inp = doc.createElement('input');
        inp.type = type || 'text';
        inp.id = id;
        inp.className = 'aiw-alias-input';
        lbl.appendChild(inp);
        parent.appendChild(lbl);
        return inp;
    }

    // _rowEl: eine Katalogzeile. Aktionen je nach Status:
    //   aktiv      -> "Ändern" (Art/Basis/Notiz) und "Widerrufen" (Grund PFLICHT)
    //   widerrufen -> "Zurücknehmen"
    function _rowEl(doc, e, kindList, canEdit, setResult, opts) {
        var tr = doc.createElement('tr');
        tr.className = statusClass(e.is_active === true);
        tr.setAttribute('data-alias-id', String(e.id));
        tr.setAttribute('data-subject', String(e.subject_id));

        var tdSid = doc.createElement('td');
        tdSid.textContent = String(e.subject_id);
        tr.appendChild(tdSid);

        var tdAlias = doc.createElement('td');
        tdAlias.className = 'aiw-alias-name-cell';
        // XSS: der Alias ist Fremdtext aus dem Forum — NIE innerHTML.
        tdAlias.textContent = e.alias || EM_DASH;
        tr.appendChild(tdAlias);

        var tdKind = doc.createElement('td');
        var badge = doc.createElement('span');
        badge.className = 'aiw-badge aiw-alias-kind';
        badge.textContent = e.kind_label
            || kindLabel(e.kind_code, kindList);
        tdKind.appendChild(badge);
        tr.appendChild(tdKind);

        var tdBasis = doc.createElement('td');
        tdBasis.textContent = e.basis || EM_DASH;
        tr.appendChild(tdBasis);

        var tdStatus = doc.createElement('td');
        if (e.is_active === true) {
            tdStatus.textContent = 'aktiv';
        } else {
            // Der Widerrufsgrund gehoert sichtbar in die Zeile: er ist die
            // Erkenntnis "warum traegt das nicht mehr".
            tdStatus.textContent = 'widerrufen'
                + (e.retracted_reason ? ' — ' + e.retracted_reason : '');
        }
        tr.appendChild(tdStatus);

        var tdTs = doc.createElement('td');
        tdTs.textContent = fmtTs(e.updated_at);
        tr.appendChild(tdTs);

        var tdAct = doc.createElement('td');
        tdAct.className = 'aiw-alias-actions';
        if (!canEdit) {
            tdAct.textContent = EM_DASH;
        } else if (e.is_active === true) {
            tdAct.appendChild(_btnChange(doc, e, kindList, setResult, opts));
            tdAct.appendChild(_btnRetract(doc, e, setResult, opts));
        } else {
            tdAct.appendChild(_btnReinstate(doc, e, setResult, opts));
        }
        tr.appendChild(tdAct);
        return tr;
    }

    // _btnChange: oeffnet eine Zeilen-Bearbeitung fuer Art/Basis/Notiz.
    // Bewusst INLINE (kein Modal): die Ermittlerin sieht beim Aendern weiter
    // den Kontext der Nachbarzeilen.
    function _btnChange(doc, e, kindList, setResult, opts) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'aiw-btn aiw-alias-btn aiw-alias-change';
        b.setAttribute('data-alias-id', String(e.id));
        b.textContent = 'Ändern';
        b.setAttribute('data-hilfe-id', 'alias.bedienung.aendern');
        b.addEventListener('click', function () {
            var row = b.parentNode && b.parentNode.parentNode;
            if (!row || row.getAttribute('data-editing') === '1') { return; }
            row.setAttribute('data-editing', '1');
            var host = doc.createElement('tr');
            host.className = 'aiw-alias-editrow';
            var td = doc.createElement('td');
            td.setAttribute('colspan', '7');

            var selK = doc.createElement('select');
            selK.className = 'aiw-alias-input aiw-alias-edit-kind';
            kindList.forEach(function (k) {
                var o = doc.createElement('option');
                o.value = k.code;
                o.textContent = k.label;
                if (k.code === e.kind_code) { o.selected = true; }
                selK.appendChild(o);
            });
            var inB = doc.createElement('input');
            inB.type = 'text';
            inB.className = 'aiw-alias-input aiw-alias-edit-basis';
            inB.value = e.basis || '';
            var inN = doc.createElement('input');
            inN.type = 'text';
            inN.className = 'aiw-alias-input aiw-alias-edit-note';
            inN.value = e.note || '';
            var save = doc.createElement('button');
            save.type = 'button';
            save.className = 'aiw-btn aiw-alias-btn aiw-alias-edit-save';
            save.textContent = 'Speichern';
            save.addEventListener('click', function () {
                setResult('Speichere Änderung …', null);
                if (typeof opts.onUpdate === 'function') {
                    opts.onUpdate({
                        alias_id: e.id,
                        kind_code: selK.value,
                        basis: inB.value.trim(),
                        note: inN.value.trim()
                    });
                } else {
                    setResult('Kein Schreibpfad verdrahtet.', true);
                }
            });

            td.appendChild(doc.createTextNode('Art: '));
            td.appendChild(selK);
            td.appendChild(doc.createTextNode(' Basis: '));
            td.appendChild(inB);
            td.appendChild(doc.createTextNode(' Notiz: '));
            td.appendChild(inN);
            td.appendChild(save);
            host.appendChild(td);
            if (row.parentNode) {
                row.parentNode.insertBefore(host, row.nextSibling);
            }
        });
        return b;
    }

    // _btnRetract: Widerruf mit PFLICHT-Grund. Das Grundfeld erscheint erst auf
    // Klick und der Absende-Knopf prueft es — ein stilles Aussortieren ohne
    // Begruendung ist genau das, was dieses System verhindern soll.
    function _btnRetract(doc, e, setResult, opts) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'aiw-btn aiw-alias-btn aiw-alias-retract';
        b.setAttribute('data-alias-id', String(e.id));
        b.textContent = 'Widerrufen';
        b.setAttribute('data-hilfe-id', 'alias.bedienung.widerrufen');
        b.addEventListener('click', function () {
            var row = b.parentNode && b.parentNode.parentNode;
            if (!row || row.getAttribute('data-retracting') === '1') { return; }
            row.setAttribute('data-retracting', '1');
            var host = doc.createElement('tr');
            host.className = 'aiw-alias-reasonrow';
            var td = doc.createElement('td');
            td.setAttribute('colspan', '7');
            var inR = doc.createElement('input');
            inR.type = 'text';
            inR.className = 'aiw-alias-input aiw-alias-reason';
            inR.setAttribute('placeholder', 'Grund des Widerrufs (Pflicht)');
            var go = doc.createElement('button');
            go.type = 'button';
            go.className = 'aiw-btn aiw-alias-btn aiw-alias-retract-go';
            go.textContent = 'Widerruf belegen';
            go.addEventListener('click', function () {
                var reason = String(inR.value || '').trim();
                if (!reason) {
                    setResult('Grund ist Pflicht — ein Alias darf nicht ohne '
                        + 'nachvollziehbaren Grund widerrufen werden.', true);
                    return;
                }
                setResult('Widerrufe Alias …', null);
                if (typeof opts.onRetract === 'function') {
                    opts.onRetract({ alias_id: e.id, reason: reason });
                } else {
                    setResult('Kein Schreibpfad verdrahtet.', true);
                }
            });
            td.appendChild(doc.createTextNode('Grund: '));
            td.appendChild(inR);
            td.appendChild(go);
            host.appendChild(td);
            if (row.parentNode) {
                row.parentNode.insertBefore(host, row.nextSibling);
            }
        });
        return b;
    }

    function _btnReinstate(doc, e, setResult, opts) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'aiw-btn aiw-alias-btn aiw-alias-reinstate';
        b.setAttribute('data-alias-id', String(e.id));
        b.textContent = 'Zurücknehmen';
        b.setAttribute('data-hilfe-id', 'alias.bedienung.zuruecknehmen');
        b.addEventListener('click', function () {
            setResult('Nehme Widerruf zurück …', null);
            if (typeof opts.onReinstate === 'function') {
                opts.onReinstate({ alias_id: e.id });
            } else {
                setResult('Kein Schreibpfad verdrahtet.', true);
            }
        });
        return b;
    }

    // =========================================================================
    // 2) UMD-Ausgang.
    // =========================================================================
    var API = {
        entries: entries,
        kinds: kinds,
        counts: counts,
        countsText: countsText,
        kindLabel: kindLabel,
        statusClass: statusClass,
        fmtTs: fmtTs,
        buildAddPayload: buildAddPayload,
        aufloesungText: aufloesungText,
        trefferLabel: trefferLabel,
        kaskadenText: kaskadenText,
        validateAdd: validateAdd,
        renderAlias: renderAlias,
        KINDS_FALLBACK: KINDS_FALLBACK
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitAlias = API; }
})();
