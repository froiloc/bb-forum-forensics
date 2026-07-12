// =============================================================================
// userinfo/userinfo_results.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Ermittlungsergebnis
// =============================================================================
// Zweck:
//   Die ERFASSUNGSMASKE fuer die Bewertung des Ermittlungsergebnisses
//   (Backend: Build 387/390).
//
//     GET  /_forensic/results         -> Katalog + Stand + Historie + Kennzahl
//     POST /_forensic/results/assess  -> eine Bewertung (APPEND-ONLY)
//
// AUFBAU (mc 2026-07-12): EINE TABELLENZEILE JE KRITERIUM, Spalten 'schwerste'
//   und 'beste'. 10 Kriterien x 2 Extreme waeren als offenes Formular 20
//   Eingabebloecke auf einmal — unbedienbar und fehleranfaellig. Stattdessen:
//   Ueberblick in der Tabelle, und die Bearbeitung oeffnet EIN Feld UNTER der
//   Zeile. Es ist immer nur eine Bewertung gleichzeitig offen.
//
// DIE VIER DINGE, DIE DIESE MASKE RICHTIG MACHEN MUSS:
//
//   1) "ERFASSEN (neuer Stand)" — NICHT "Speichern". Jede Erfassung ist eine
//      NEUE ZEILE mit eigenem Beleg (append-only). Der Knopf sagt das, und die
//      Bestaetigung sagt es nochmal. Wer glaubt, er korrigiere einen Wert,
//      versteht das System falsch — er ERGAENZT einen Stand.
//
//   2) DIE HISTORIE IST SICHTBAR. Sie ist kein Beiwerk: sie belegt den
//      Erkenntnisgewinn (aus 'Verdacht' wird 'wahrscheinlich' wird
//      'gerichtsfest') und ist damit selbst ein Ermittlungsergebnis.
//
//   3) DIE SEMANTIK-WARNUNG DER SKALA WIRD ANGEZEIGT. 'ordinal' misst bei
//      location/victim die PRAEZISION, bei abuser die SCHWERE. Der Server
//      liefert diese Beschreibung mit (quality_beschreibung); sie steht als
//      Hinweis am Auswahlfeld. Ohne sie wuerde jemand die Zahlen vermischen.
//
//   4) DER VERMERK ZUR KENNZAHL IST NICHT WEGKLICKBAR. Die Zahl ist
//      provisorisch und mit niemandem abgestimmt. Sie ohne diesen Satz zu
//      zeigen, waere eine unbelegte Behauptung.
//
// KEINE QUALITAETSAUSWAHL, WO ES KEINE SKALA GIBT: Kriterien ohne
//   quality_scale zeigen dort GAR KEIN Feld — statt eines leeren, das nichts
//   taete und das der Server ohnehin mit 400 abwiese.
//
// GEBOTE: IIFE + 'use strict'; DEV-Logging (window.AIW_UI_DEBUG); reine
//   Funktionen ohne DOM (vitest gegen den ECHTEN Code, UMD-Ausgang);
//   ausschliesslich textContent (XSS: Freitexte stammen aus der Ermittlung,
//   Benutzernamen aus dem beschlagnahmten Forum).
//
// Version: v0.7.390 · Build: 390 · 2026-07-12
// =============================================================================

(function () {
    'use strict';

    function debugOn() {
        return (typeof window !== 'undefined') && window.AIW_UI_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Ergebnis]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EXTREME = ['schwerste', 'beste'];

    var EXTREM_LABEL = {
        schwerste: 'schwerste Erkenntnis',
        beste: 'beste Erkenntnis'
    };

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM) — genau diese prueft vitest.
    // =========================================================================

    // indexCurrent: aktueller Stand -> { 'kriterium|extrem': zeile }
    function indexCurrent(current) {
        var map = {};
        (current || []).forEach(function (r) {
            map[r.criterion_code + '|' + r.extrem] = r;
        });
        return map;
    }

    // cellText: was in der Zelle steht. OHNE Bewertung ist die Zelle NICHT leer,
    // sondern sagt ausdruecklich "nicht bewertet" — eine leere Zelle liesse
    // offen, ob nichts erfasst wurde oder ob nichts anzuzeigen ist.
    function cellText(row) {
        if (!row) { return 'nicht bewertet'; }
        var t = (row.confidence_label || row.confidence_code)
            + ' (' + row.confidence_ordinal + ')';
        if (row.quality_code) {
            t += ' \u00b7 ' + (row.quality_label || row.quality_code)
                + ' (' + row.quality_ordinal + ')';
        }
        return t;
    }

    // historyFor: Historie eines Kriteriums+Extrems, juengste zuerst.
    function historyFor(history, criterion, extrem) {
        return (history || []).filter(function (h) {
            return h.criterion_code === criterion && h.extrem === extrem;
        });
    }

    // historyLine: eine Zeile des Verlaufs.
    function historyLine(h) {
        var d = new Date((h.created_at || 0) * 1000);
        var when = isNaN(d.getTime()) ? '?' : d.toLocaleString('de-DE');
        var t = when + ' \u2014 ' + cellText(h)
            + ' [Katalog v' + h.catalog_version + ', Beleg #' + h.audit_seq + ']';
        if (h.note) { t += ' \u2014 ' + h.note; }
        return t;
    }

    // criterionByCode: Katalogeintrag holen (fuer die Auswahlfelder).
    function criterionByCode(catalog, code) {
        var list = (catalog && catalog.criteria) || [];
        for (var i = 0; i < list.length; i++) {
            if (list[i].code === code) { return list[i]; }
        }
        return null;
    }

    // hasQuality: hat dieses Kriterium ueberhaupt eine Qualitaetsskala?
    // Wenn nein, bietet die Maske dort KEIN Feld an (statt eines leeren).
    function hasQuality(catalog, code) {
        var c = criterionByCode(catalog, code);
        return !!(c && c.quality_scale && (c.quality_items || []).length);
    }

    // assessRequest: Anfrage bauen — mit Validierung VOR dem POST. Eine
    // Anfrage, die sicher scheitert, wird gar nicht erst gestellt.
    // Die user_id fehlt ABSICHTLICH: der Server nimmt sie aus dem Kontext
    // (der geoeffnete Fall). Sie hier mitzuschicken waere sinnlos und wuerde
    // serverseitig ohnehin ignoriert.
    function assessRequest(catalog, f) {
        f = f || {};
        if (!f.criterion_code) { return { error: 'Kein Kriterium gewaehlt.' }; }
        if (EXTREME.indexOf(f.extrem) === -1) {
            return { error: 'Extrem muss "schwerste" oder "beste" sein.' };
        }
        if (!f.confidence_code) {
            return { error: 'Konfidenz ist Pflicht (wie sicher ist die '
                            + 'Erkenntnis?).' };
        }
        var q = f.quality_code || null;
        if (q && !hasQuality(catalog, f.criterion_code)) {
            // Sollte die Oberflaeche gar nicht zulassen — aber wenn doch,
            // wird es hier gefangen und nicht dem Server zugemutet.
            return { error: 'Dieses Kriterium hat keine Qualitaetsskala.' };
        }
        return {
            path: '/_forensic/results/assess',
            body: {
                criterion_code: f.criterion_code,
                extrem: f.extrem,
                confidence_code: f.confidence_code,
                quality_code: q,
                note: String(f.note || '')
            }
        };
    }

    // confirmText: die Bestaetigung nennt die Folgen beim Namen.
    function confirmText(criterionLabel, extrem) {
        return 'Neuer Stand fuer "' + criterionLabel + '" ('
            + (EXTREM_LABEL[extrem] || extrem) + '): Es wird ein NEUER '
            + 'Eintrag erzeugt und im audit_log belegt. Der bisherige Stand '
            + 'bleibt in der Historie erhalten \u2014 es wird nichts '
            + 'ueberschrieben.';
    }

    // scoreText: Kennzahl im Klartext.
    function scoreText(score) {
        if (!score) { return ''; }
        return 'Provisorische Kennzahl: ' + score.score
            + ' (Basis: ' + score.basis + ' bewertete Kriterien, Abdeckung '
            + Math.round((score.abdeckung || 0) * 100) + ' %)';
    }

    // =========================================================================
    // 2) DOM/RENDER
    // =========================================================================

    function _el(doc, tag, cls, text) {
        var e = doc.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    function _select(doc, id, items, current, leerLabel) {
        var s = doc.createElement('select');
        s.id = id;
        if (leerLabel) {
            var o0 = doc.createElement('option');
            o0.value = '';
            o0.text = leerLabel;
            s.appendChild(o0);
        }
        (items || []).forEach(function (i) {
            var o = doc.createElement('option');
            o.value = i.code;
            o.text = i.label + ' (' + i.ordinal + ')';
            if (current === i.code) { o.selected = true; }
            s.appendChild(o);
        });
        return s;
    }

    // renderResults: Karte aufbauen.
    //   data — Antwort von GET /_forensic/results
    //   opts — { onAssess(body), canEdit }
    // Rueckgabe: { setResult, openEditor, close }
    function renderResults(cardEl, data, opts) {
        opts = opts || {};
        if (!cardEl) { return null; }
        var doc = cardEl.ownerDocument || document;
        cardEl.textContent = '';

        var catalog = (data && data.catalog) || {};
        var criteria = catalog.criteria || [];
        var canEdit = (opts.canEdit !== undefined)
            ? !!opts.canEdit : !!(data && data.can_edit);
        var cur = indexCurrent(data && data.current);
        var history = (data && data.history) || [];

        cardEl.appendChild(_el(doc, 'h2', null,
                               'Ermittlungsergebnis \u00b7 Bewertung'));

        var sub = _el(doc, 'div', 'uir-sub',
            'Jede Erfassung ist ein NEUER Stand (append-only) \u2014 der '
            + 'bisherige bleibt in der Historie erhalten. Katalogversion: '
            + (catalog.catalog_version || '?'));
        sub.id = 'uir-sub';
        cardEl.appendChild(sub);

        if (!canEdit) {
            cardEl.appendChild(_el(doc, 'div', 'uir-readonly',
                'Nur Lesezugriff \u2014 die Faehigkeit "results.edit" ist '
                + 'nicht vergeben.'));
        }

        // --- Tabelle: EINE ZEILE JE KRITERIUM -------------------------------
        var tbl = _el(doc, 'table', 'uir-table');
        tbl.id = 'uir-table';
        var thead = doc.createElement('thead');
        var htr = doc.createElement('tr');
        ['Kriterium', 'schwerste Erkenntnis', 'beste Erkenntnis', '']
            .forEach(function (t) {
                htr.appendChild(_el(doc, 'th', null, t));
            });
        thead.appendChild(htr);
        tbl.appendChild(thead);

        var tbody = doc.createElement('tbody');
        tbl.appendChild(tbody);
        cardEl.appendChild(tbl);

        var editorRow = null;      // die derzeit offene Bearbeitungszeile

        function closeEditor() {
            if (editorRow && editorRow.parentNode) {
                editorRow.parentNode.removeChild(editorRow);
            }
            editorRow = null;
        }

        var result = _el(doc, 'div', 'uir-result');
        result.id = 'uir-result';

        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }

        criteria.forEach(function (c) {
            var tr = doc.createElement('tr');
            tr.setAttribute('data-criterion', c.code);

            var tdName = _el(doc, 'td', 'uir-name', c.label);
            tr.appendChild(tdName);

            EXTREME.forEach(function (ex) {
                var row = cur[c.code + '|' + ex];
                var td = _el(doc, 'td', 'uir-cell');
                td.setAttribute('data-extrem', ex);
                if (!row) { td.classList.add('uir-leer'); }

                var val = _el(doc, 'div', 'uir-val', cellText(row));
                td.appendChild(val);

                var hist = historyFor(history, c.code, ex);
                // Die Historie ist SICHTBAR (aber eingeklappt) — sie belegt den
                // Erkenntnisgewinn und ist selbst ein Ermittlungsergebnis.
                if (hist.length > 1) {
                    var det = doc.createElement('details');
                    det.className = 'uir-hist';
                    var sum = doc.createElement('summary');
                    sum.textContent = 'Verlauf (' + hist.length + ')';
                    det.appendChild(sum);
                    var ul = doc.createElement('ul');
                    hist.forEach(function (h) {
                        ul.appendChild(_el(doc, 'li', null, historyLine(h)));
                    });
                    det.appendChild(ul);
                    td.appendChild(det);
                }

                if (canEdit) {
                    var b = doc.createElement('button');
                    b.type = 'button';
                    b.className = 'uir-btn uir-edit';
                    b.setAttribute('data-criterion', c.code);
                    b.setAttribute('data-extrem', ex);
                    b.textContent = row ? 'Neuer Stand' : 'Bewerten';
                    b.addEventListener('click', function () {
                        openEditor(c, ex);
                    });
                    td.appendChild(b);
                }
                tr.appendChild(td);
            });

            // Hinweisspalte: KEINE Qualitaetsskala -> das wird gesagt, nicht
            // durch ein leeres Feld angedeutet.
            var tdInfo = _el(doc, 'td', 'uir-info',
                c.quality_scale ? '' : 'nur Konfidenz');
            if (c.quality_beschreibung) {
                tdInfo.title = c.quality_beschreibung;
                tdInfo.textContent = 'i';
                tdInfo.classList.add('uir-i');
            }
            tr.appendChild(tdInfo);

            tbody.appendChild(tr);
        });

        // --- Bearbeitungszeile (immer nur EINE offen) ------------------------
        // Die Ankerzeile wird HIER aufgeloest, nicht uebergeben. Grund: nach
        // closeEditor() ist ein zuvor gemerktes Zeilen-Element moeglicherweise
        // aus dem DOM entfernt (es koennte die alte Editor-Zeile sein) — der
        // neue Editor haenge dann an einem Knoten ohne Elternteil und
        // erschiene STILL nicht. Wir suchen die Kriteriumszeile stattdessen
        // frisch. (Gefunden durch Test UR09, Build 390.)
        function openEditor(c, ex) {
            closeEditor();
            var afterTr = tbody.querySelector(
                'tr[data-criterion="' + c.code + '"]');
            var row = cur[c.code + '|' + ex];

            editorRow = doc.createElement('tr');
            editorRow.className = 'uir-editor';
            editorRow.id = 'uir-editor';
            var td = doc.createElement('td');
            td.setAttribute('colspan', '4');
            editorRow.appendChild(td);

            td.appendChild(_el(doc, 'div', 'uir-editor-title',
                c.label + ' \u2014 ' + (EXTREM_LABEL[ex] || ex)));

            // Konfidenz (immer).
            var lc = _el(doc, 'label', 'uir-field');
            lc.appendChild(_el(doc, 'span', null, 'Konfidenz (wie sicher?)'));
            lc.appendChild(_select(doc, 'uir-conf', catalog.confidence_items,
                                   row && row.confidence_code, '-- waehlen --'));
            td.appendChild(lc);

            // Qualitaet NUR, wenn es eine Skala gibt.
            if (hasQuality(catalog, c.code)) {
                var lq = _el(doc, 'label', 'uir-field');
                lq.appendChild(_el(doc, 'span', null,
                                   'Qualitaet (wie tief?)'));
                lq.appendChild(_select(doc, 'uir-qual', c.quality_items,
                                       row && row.quality_code,
                                       '-- keine Angabe --'));
                // DIE SEMANTIK-WARNUNG: 'ordinal' misst je nach Skala
                // Praezision ODER Schwere. Ohne diesen Hinweis wuerde jemand
                // die Zahlen vermischen.
                if (c.quality_beschreibung) {
                    var hint = _el(doc, 'small', 'uir-hint',
                                   c.quality_beschreibung);
                    lq.appendChild(hint);
                }
                td.appendChild(lq);
            }

            var ln = _el(doc, 'label', 'uir-field');
            ln.appendChild(_el(doc, 'span', null,
                               'Vermerk (Fundstelle, Begruendung)'));
            var note = doc.createElement('textarea');
            note.id = 'uir-note';
            note.rows = 2;
            ln.appendChild(note);
            td.appendChild(ln);

            var confirm = _el(doc, 'div', 'uir-confirm');
            confirm.id = 'uir-confirm';
            td.appendChild(confirm);

            var save = doc.createElement('button');
            save.type = 'button';
            save.className = 'uir-btn uir-primary';
            save.id = 'uir-save';
            // "Erfassen (neuer Stand)" — NICHT "Speichern". Wer glaubt, er
            // korrigiere einen Wert, versteht das System falsch.
            save.textContent = 'Erfassen (neuer Stand)';
            save.addEventListener('click', function () {
                // Stufe 1: Bestaetigung.
                confirm.textContent = '';
                confirm.appendChild(_el(doc, 'div', 'uir-confirm-title',
                                        confirmText(c.label, ex)));

                var yes = doc.createElement('button');
                yes.type = 'button';
                yes.className = 'uir-btn uir-primary';
                yes.id = 'uir-confirm-yes';
                yes.textContent = 'Ja, neuen Stand erfassen';
                yes.addEventListener('click', function () {
                    var qEl = doc.getElementById('uir-qual');
                    var req = assessRequest(catalog, {
                        criterion_code: c.code,
                        extrem: ex,
                        confidence_code: doc.getElementById('uir-conf').value,
                        quality_code: qEl ? qEl.value : null,
                        note: doc.getElementById('uir-note').value
                    });
                    if (req.error) { setResult(req.error, true); return; }
                    setResult('Erfasse \u2026', null);
                    if (typeof opts.onAssess === 'function') {
                        opts.onAssess(req.body);
                    } else {
                        setResult('Kein Schreibpfad verdrahtet.', true);
                    }
                });
                confirm.appendChild(yes);

                var no = doc.createElement('button');
                no.type = 'button';
                no.className = 'uir-btn';
                no.id = 'uir-confirm-no';
                no.textContent = 'Abbrechen';
                no.addEventListener('click', function () {
                    confirm.textContent = '';
                    setResult('Abgebrochen. Es wurde nichts geschrieben.',
                              false);
                });
                confirm.appendChild(no);
            });
            td.appendChild(save);

            var cancel = doc.createElement('button');
            cancel.type = 'button';
            cancel.className = 'uir-btn';
            cancel.id = 'uir-cancel';
            cancel.textContent = 'Schliessen';
            cancel.addEventListener('click', function () { closeEditor(); });
            td.appendChild(cancel);

            if (afterTr && afterTr.parentNode) {
                afterTr.parentNode.insertBefore(editorRow,
                                                afterTr.nextSibling);
            }
            log('Editor offen:', c.code, ex);
        }

        // --- Kennzahl + VERMERK (nicht wegklickbar) --------------------------
        var score = data && data.score;
        if (score) {
            var sc = _el(doc, 'div', 'uir-score');
            sc.id = 'uir-score';
            sc.appendChild(_el(doc, 'div', 'uir-score-val', scoreText(score)));

            if ((score.unbewertet || []).length) {
                sc.appendChild(_el(doc, 'div', 'uir-gaps',
                    'Noch nicht bewertet (hier ist zu ermitteln): '
                    + score.unbewertet.join(', ')));
            }
            // Der VERMERK ist Teil der Zahl, nicht ihr Beiwerk.
            sc.appendChild(_el(doc, 'div', 'uir-vermerk', score.vermerk));
            cardEl.appendChild(sc);
        }

        cardEl.appendChild(result);

        log('renderResults:', criteria.length, 'Kriterien,',
            (data && data.current || []).length, 'aktuelle Bewertungen');

        return { setResult: setResult, openEditor: openEditor,
                 close: closeEditor };
    }

    // =========================================================================
    // 3) UMD-Ausgang
    // =========================================================================
    var API = {
        EXTREME: EXTREME,
        EXTREM_LABEL: EXTREM_LABEL,
        indexCurrent: indexCurrent,
        cellText: cellText,
        historyFor: historyFor,
        historyLine: historyLine,
        criterionByCode: criterionByCode,
        hasQuality: hasQuality,
        assessRequest: assessRequest,
        confirmText: confirmText,
        scoreText: scoreText,
        renderResults: renderResults
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWUserinfoResults = API; }
})();
