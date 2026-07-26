// =============================================================================
// management/server/static/cockpit_cases.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit "Fall-Erkennung"
// =============================================================================
// Zweck:
//   Frontend zur Fall-Autodetektion (Backend: Build 383).
//   Quelle: GET /api/cases/detect  -> Abgleich Platte <-> Fallakte, rein lesend.
//   Aktion: POST /api/cases/import -> auditierte Aufnahme neu erkannter Faelle.
//
//   VIER ZUSTAENDE (Beleg: management/cases/case_detector.py):
//     ok         Fall in 'cases' UND forensic_<uid>.db vorhanden.
//     neu        forensic_<uid>.db da, aber NICHT in 'cases'  -> aufnehmbar.
//     vermisst   in 'cases', aber KEINE forensic_<uid>.db mehr -> MELDEN.
//     unlesbar   DB da, aber nicht lesbar / uid_profile fehlt  -> MELDEN.
//
// GRUNDREGEL 1 (kein stiller Fehlschlag) — hier an DREI Stellen umgesetzt:
//   (a) 'vermisst' und 'unlesbar' stehen NICHT nur als Zeile in der Tabelle,
//       sondern zusaetzlich in einem eigenen, deutlich abgesetzten WARNBEREICH
//       OBERHALB der Tabelle. Ein Statusfilter kann sie nicht wegblenden.
//   (b) Die Rueckmeldung nach der Aufnahme zeigt 'imported' UND 'skipped' —
//       jeden uebersprungenen Fall MIT GRUND.
//   (c) Die Verzeichnisse, ueber die gemessen wurde, werden angezeigt. Sonst
//       bliebe unklar, WORUEBER die Aussage "kein Fall gefunden" gilt.
//
// BEWUSSTE ENTSCHEIDUNGEN:
//   - Auswahlkaestchen NUR bei Status 'neu' MIT Benutzername. Das ist exakt die
//     Menge, die CaseDetector.importable() liefert. Die Oberflaeche bietet damit
//     keine Aktion an, die serverseitig zwingend als 'skipped' zurueckkaeme.
//   - KEIN "alles auswaehlen" und KEIN Aufruf von {all:true}. Die Aufnahme ist
//     ein bewusster, belegpflichtiger Vorgang; der Stapelbetrieb bleibt dem CLI
//     ('case_detect --auto') vorbehalten (mc 2026-07-10).
//   - ZWEISTUFIG: Knopf -> Bestaetigungsblock mit Auflistung -> Ausfuehren.
//     Ein Fehlklick darf keine Fallakte veraendern.
//   - KEIN optimistisches UI: nach dem POST wird neu geladen; angezeigt wird nur
//     der bestaetigt geschriebene Zustand.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging (window.AIW_COCKPIT_DEBUG).
//   3) Ausfuehrliche Kommentare. 4) Reine Funktionen (toRows/isSelectable/
//   filterByStatus/countsText/dirsText/warningRows/importRequest/resultText)
//   beruehren NIE das DOM -> vitest prueft den ECHTEN Code (UMD-Ausgang),
//   nicht ein Abbild davon ("gruen aber tot"-Falle).
//
// XSS: ausschliesslich textContent / Tabulator-Plaintext. Benutzernamen stammen
//   aus dem beschlagnahmten Forum und sind grundsaetzlich fremdbestimmt.
//
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Version: v0.7.469 · Build: 469 · 2026-07-20
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
        args.unshift('[AIW-Faelle]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // Klartext-Beschriftungen der vier Zustaende. 'vermisst'/'unlesbar' sind
    // bewusst als Missstand formuliert — sie sind KEIN Normalzustand.
    var STATUS_LABEL = {
        ok:       'erfasst',
        neu:      'neu (aufnehmbar)',
        vermisst: 'VERMISST',
        unlesbar: 'UNLESBAR'
    };

    // Reihenfolge im Filter: das Handlungsbeduerftige zuerst.
    var STATUS_ORDER = ['neu', 'vermisst', 'unlesbar', 'ok'];

    // Die beiden Zustaende, die einen Missstand anzeigen (Warnbereich).
    var WARN_STATUS = { vermisst: true, unlesbar: true };

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM). Genau diese testet vitest.
    // =========================================================================

    // ja/— fuer die Arbeitsstand-Spalten (evidence/assets). Bewusst KEIN
    // Haekchen-Zeichen: die Tabelle wird auch in Berichte kopiert.
    function fmtBool(b) {
        return b ? 'ja' : '\u2014';
    }

    // isSelectable: Nur 'neu' MIT Benutzername ist aufnehmbar. Spiegelt exakt
    // CaseDetector.importable() (Build 383). Ohne Benutzernamen wuerde der
    // Server den Fall zwingend als 'skipped' zurueckweisen — also bieten wir
    // ihn gar nicht erst zur Auswahl an.
    function isSelectable(c) {
        return !!c && c.status === 'neu' && !!c.username;
    }

    // toRows: /api/cases/detect.cases -> Tabellenzeilen.
    function toRows(data) {
        return ((data && data.cases) || []).map(function (c) {
            return {
                subject_id: c.subject_id,
                username: c.username || '',
                status: c.status,
                status_label: STATUS_LABEL[c.status] || c.status,
                in_cases: fmtBool(c.in_cases),
                forensic: fmtBool(c.has_forensic_db),
                evidence: fmtBool(c.has_evidence_db),
                assets: fmtBool(c.has_assets_db),
                detail: c.detail || '',
                // Nur diese Zeilen bekommen ein Auswahlkaestchen.
                selectable: isSelectable(c)
            };
        });
    }

    // selectableIds: alle aufnehmbaren subject_id (Basis fuer die Auswahl-Pruefung).
    function selectableIds(data) {
        return ((data && data.cases) || []).filter(isSelectable)
            .map(function (c) { return c.subject_id; });
    }

    // filterByStatus: '' (alle) oder genau ein Zustand.
    function filterByStatus(rows, status) {
        if (!status) { return rows; }
        return (rows || []).filter(function (r) { return r.status === status; });
    }

    // countsText: die Zaehler der vier Zustaende als eine Zeile Klartext.
    function countsText(data) {
        var c = (data && data.counts) || {};
        var n = (data && data.count) || 0;
        return n + ' Fall/Faelle gefunden: '
            + (c.ok || 0) + ' erfasst, '
            + (c.neu || 0) + ' neu, '
            + (c.vermisst || 0) + ' vermisst, '
            + (c.unlesbar || 0) + ' unlesbar.';
    }

    // dirsText: WORUEBER wurde gemessen? Ohne diese Angabe ist die Aussage
    // "keine Faelle gefunden" wertlos (falsches Verzeichnis sieht genauso aus).
    function dirsText(data) {
        if (!data) { return ''; }
        return 'forensic: ' + (data.forensic_dir || '?')
            + ' \u00b7 evidence: ' + (data.evidence_dir || '?')
            + ' \u00b7 assets: ' + (data.assets_dir || '?');
    }

    // warningRows: alle Faelle im Zustand 'vermisst' oder 'unlesbar'.
    // Diese Menge speist den Warnbereich (unabhaengig vom Statusfilter).
    function warningRows(data) {
        return ((data && data.cases) || []).filter(function (c) {
            return !!WARN_STATUS[c.status];
        });
    }

    // warningLine: eine Zeile des Warnbereichs (uid, Name, Grund).
    function warningLine(c) {
        var who = c.username ? (' (' + c.username + ')') : '';
        var why = c.detail ? (' \u2014 ' + c.detail) : '';
        return (STATUS_LABEL[c.status] || c.status) + ': Fall '
            + c.subject_id + who + why;
    }

    // importRequest: Anfrage fuer die auditierte Aufnahme. Leere Auswahl ->
    // null (der Aufrufer meldet das; wir schicken KEINEN Leer-POST, der Server
    // wuerde ihn zu Recht mit 400 abweisen).
    // KEIN {all:true}: die Auswahl bleibt bewusst explizit.
    function importRequest(subjectIds) {
        var ids = (subjectIds || []).map(function (u) { return parseInt(u, 10); })
            .filter(function (u) { return !isNaN(u); });
        if (!ids.length) { return null; }
        return { path: '/api/cases/import', body: { subject_ids: ids } };
    }

    // resultText: Rueckmeldung des Servers in Klartext. imported MIT Beleg-Nr.,
    // skipped MIT Grund. error=true, sobald auch nur ein Fall uebersprungen
    // wurde — das ist ein Befund, kein Erfolg (Grundregel 1).
    function resultText(res) {
        var imp = (res && res.imported) || [];
        var skp = (res && res.skipped) || [];
        var parts = [];

        if (imp.length) {
            parts.push(imp.length + ' Fall/Faelle aufgenommen: '
                + imp.map(function (i) {
                    return i.subject_id + ' (' + (i.username || '?')
                        + ', Beleg #' + i.audit_seq + ')';
                }).join(', ') + '.');
        } else {
            parts.push('Kein Fall aufgenommen.');
        }

        if (skp.length) {
            parts.push(skp.length + ' Fall/Faelle NICHT aufgenommen: '
                + skp.map(function (s) {
                    return s.subject_id + ' \u2014 ' + (s.reason || 'ohne Grund');
                }).join('; ') + '.');
        }

        return { text: parts.join(' '), error: skp.length > 0 };
    }

    // confirmText: Text des Bestaetigungsblocks. Nennt die Belegpflicht beim
    // Namen — der Ermittler soll wissen, dass er eine Spur erzeugt.
    function confirmText(rows) {
        var n = (rows || []).length;
        return 'Aufnahme von ' + n + ' Fall/Faellen in die Fallakte. Jede '
            + 'Aufnahme erzeugt einen Beleg im audit_log (case_created) und ist '
            + 'nicht stillschweigend rueckgaengig zu machen.';
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    // Build 534: JEDE Spalte ist filterbar (mc 2026-07-26: "In der
    // Fall-Erkennung sollten aber alle Spalten filterbar sein"). Die
    // Filterart bestimmt NICHT diese Liste, sondern das gemeinsame
    // Tabellen-Werkzeug aus den DATEN: wenige verschiedene Werte -> Auswahl
    // mit Mehrfachauswahl, sonst Freitext. 'filter_text' erzwingt Freitext
    // dort, wo man nach Teilen sucht statt aus einer Liste zu waehlen
    // (Benutzername, Hinweis) — eine Auswahlliste mit 163 Namen waere
    // unbedienbar, auch wenn die Schwelle es zuliesse.
    //
    // Der frueher hier stehende 'headerFilter: input' auf 'username' ist
    // entfallen: er ist jetzt der Regelfall und steht nicht mehr als
    // Einzelfall da (eine Spalte mit Filter und sieben ohne war die eigentliche
    // Unstimmigkeit).
    var _COLUMNS = [
        { title: 'Fall', field: 'subject_id', width: 90, sorter: 'number',
          filter_text: true },
        { title: 'Benutzername', field: 'username', filter_text: true },
        { title: 'Zustand', field: 'status_label' },
        { title: 'in Fallakte', field: 'in_cases', width: 110 },
        { title: 'forensic', field: 'forensic', width: 100 },
        { title: 'evidence', field: 'evidence', width: 100 },
        { title: 'assets', field: 'assets', width: 90 },
        { title: 'Hinweis', field: 'detail', filter_text: true }
    ];

    //: Kennung dieser Sicht fuer den gesicherten Bedienzustand (localStorage).
    var SICHT_ID = 'cases';

    function _tk() {
        return (typeof window !== 'undefined' && window.AIWTableKit)
            ? window.AIWTableKit : null;
    }

    // Zeilenfaerbung: Missstaende rot, Aufnehmbares gelb (Ampel-Vokabular des
    // Cockpits, vgl. Overview-Sicht Build 348).
    function _rowClass(status) {
        if (WARN_STATUS[status]) { return 'aiw-row-rot'; }
        if (status === 'neu') { return 'aiw-row-gelb'; }
        return 'aiw-row-gruen';
    }

    // renderCases: baut die gesamte Sicht auf.
    //   opts.Tabulator   — injizierbarer Ctor (Tests); sonst window.Tabulator
    //   opts.TableKit    — injizierbares Tabellen-Werkzeug (Tests)
    //   opts.onImport(ids) — die Shell fuehrt den POST aus (Schreib-Token!)
    //   opts.onStats(ids)  — die Shell holt die Kennzahlen (Build 534)
    // Rueckgabe: { table, setResult, showResult, getSelection, setStats }
    //   'table' kann null sein (keine Tabellenbibliothek) — die Bedienelemente
    //   und der Warnbereich stehen TROTZDEM (Grundregel 1: die Warnung darf
    //   nicht an einer fehlenden Bibliothek scheitern).
    function renderCases(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        var doc = mainEl.ownerDocument || document;
        var tk = opts.TableKit || _tk();
        mainEl.textContent = '';

        var rows = toRows(data);
        var warns = warningRows(data);
        var counts = (data && data.counts) || {};

        // Build 534: Kennzahlen (uid_stats) — dieselbe Mechanik wie in der
        // Zuweisung, damit beide Masken gleich bedient werden.
        var statsDaten = null;
        var gewaehlteStats = [];

        // --- Kopf ------------------------------------------------------------
        var h = doc.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = 'Fall-Erkennung';
        mainEl.appendChild(h);

        var sub = doc.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.id = 'aiw-cases-counts';
        sub.textContent = countsText(data);
        mainEl.appendChild(sub);

        var dirs = doc.createElement('p');
        dirs.className = 'aiw-pagesub aiw-cases-dirs';
        dirs.id = 'aiw-cases-dirs';
        dirs.textContent = dirsText(data);
        mainEl.appendChild(dirs);

        // --- WARNBEREICH (Grundregel 1) --------------------------------------
        // Steht OBERHALB der Tabelle und ist vom Statusfilter unabhaengig.
        if (warns.length) {
            var warnBox = doc.createElement('div');
            warnBox.className = 'aiw-cases-warn';
            warnBox.id = 'aiw-cases-warn';

            var wh = doc.createElement('div');
            wh.className = 'aiw-cases-warn-title';
            wh.textContent = warns.length + ' Fall/Faelle erfordern eine '
                + 'Pruefung durch einen Menschen (vermisst / unlesbar). Sie '
                + 'werden NICHT automatisch veraendert.';
            warnBox.appendChild(wh);

            var ul = doc.createElement('ul');
            warns.forEach(function (c) {
                var li = doc.createElement('li');
                li.textContent = warningLine(c);
                ul.appendChild(li);
            });
            warnBox.appendChild(ul);
            mainEl.appendChild(warnBox);
        }

        // --- Bedienleiste ----------------------------------------------------
        // Build 534: Der Zustands-Schnellfilter bleibt (er traegt die ZAEHLUNG
        // je Zustand und ist mit einem Griff bedient), bekommt aber die
        // gemeinsame Werkzeugleiste an die Seite — dieselbe wie in der
        // Zuweisung: Spaltenwahl, 'Filter zuruecksetzen', Trefferanzeige.
        // Beide Masken sehen damit gleich aus UND verhalten sich gleich.
        var bar = doc.createElement('div');
        bar.className = 'aiw-cases-bar aiw-tk-kopf';

        var sel = doc.createElement('select');
        sel.id = 'aiw-cases-filter';
        var optAll = doc.createElement('option');
        optAll.value = '';
        optAll.text = 'alle Zustaende (' + rows.length + ')';
        sel.appendChild(optAll);
        STATUS_ORDER.forEach(function (s) {
            var o = doc.createElement('option');
            o.value = s;
            o.text = (STATUS_LABEL[s] || s) + ' (' + (counts[s] || 0) + ')';
            sel.appendChild(o);
        });

        var leiste = null;
        if (tk) {
            leiste = tk.werkzeugleiste(doc, {
                id: 'aiw-cases-tk',
                eigene: [sel],
                spaltenwahl: {
                    id: 'aiw-cases-spalten',
                    katalog: [],
                    gewaehlt: [],
                    onChange: function (keys) {
                        gewaehlteStats = keys;
                        spaltenNeuSetzen();
                        zustandSichern();
                    }
                },
                onFilterLoeschen: function () {
                    tk.filterLoeschen(table);
                    // Auch der Zustands-Schnellfilter gehoert dazu — sonst
                    // hiesse die Schaltflaeche 'Filter zuruecksetzen' und
                    // liesse einen Filter stehen. Genau solche halben
                    // Zusicherungen kosten Vertrauen in das Werkzeug.
                    sel.value = '';
                    if (table && typeof table.replaceData === 'function') {
                        try { table.replaceData(datenZeilen()); }
                        catch (e) { log(e); }
                    }
                    zustandSichern();
                    setResult('Alle Filter entfernt.', false);
                }
            });
            bar.appendChild(leiste.el);
        } else {
            bar.appendChild(sel);
        }
        mainEl.appendChild(bar);

        // --- Tabelle ---------------------------------------------------------
        var container = doc.createElement('div');
        container.id = 'aiw-cases-table';
        mainEl.appendChild(container);

        // --- Aktionsfeld (immer vorhanden) -----------------------------------
        var panel = doc.createElement('div');
        panel.className = 'aiw-cases-actions';
        panel.id = 'aiw-cases-actions';
        mainEl.appendChild(panel);

        var btn = doc.createElement('button');
        btn.type = 'button';
        btn.id = 'aiw-cases-import';
        btn.className = 'aiw-btn aiw-cases-btn';
        btn.disabled = true;
        btn.textContent = 'Ausgewaehlte aufnehmen (0)';
        panel.appendChild(btn);

        var confirmBox = doc.createElement('div');
        confirmBox.className = 'aiw-cases-confirm';
        confirmBox.id = 'aiw-cases-confirm';
        panel.appendChild(confirmBox);

        var result = doc.createElement('div');
        result.className = 'aiw-cases-result';
        result.id = 'aiw-cases-result';
        panel.appendChild(result);

        // Auswahl-Zustand lebt NUR hier (kein localStorage — Projektregel).
        var selected = {};   // { subject_id: true }

        function selectionIds() {
            return Object.keys(selected)
                .filter(function (k) { return selected[k]; })
                .map(function (k) { return parseInt(k, 10); })
                .sort(function (a, b) { return a - b; });
        }

        function refreshButton() {
            var n = selectionIds().length;
            btn.textContent = 'Ausgewaehlte aufnehmen (' + n + ')';
            btn.disabled = (n === 0);
        }

        function setResult(text, isError) {
            result.textContent = text || '';
            result.classList.toggle('error', isError === true);
            result.classList.toggle('ok', isError === false);
        }

        // showResult: Serverantwort des Imports darstellen (imported + skipped).
        function showResult(res) {
            var r = resultText(res);
            setResult(r.text, r.error);
        }

        // --- Bestaetigung (zweistufig) ---------------------------------------
        function closeConfirm() {
            confirmBox.textContent = '';
        }

        function openConfirm() {
            var ids = selectionIds();
            if (!ids.length) {
                setResult('Kein Fall ausgewaehlt.', true);
                return;
            }
            // Die Namen der ausgewaehlten Faelle (aus den bereits geladenen
            // Zeilen — kein zweiter Serveraufruf).
            var chosen = rows.filter(function (r) {
                return ids.indexOf(r.subject_id) !== -1;
            });

            confirmBox.textContent = '';
            var q = doc.createElement('div');
            q.className = 'aiw-cases-confirm-title';
            q.textContent = confirmText(chosen);
            confirmBox.appendChild(q);

            var ul = doc.createElement('ul');
            chosen.forEach(function (r) {
                var li = doc.createElement('li');
                li.textContent = 'Fall ' + r.subject_id + ' \u2014 ' + r.username;
                ul.appendChild(li);
            });
            confirmBox.appendChild(ul);

            var yes = doc.createElement('button');
            yes.type = 'button';
            yes.id = 'aiw-cases-confirm-yes';
            yes.className = 'aiw-btn aiw-cases-btn';
            yes.textContent = 'Ja, ' + ids.length
                + ' Fall/Faelle aufnehmen';
            yes.addEventListener('click', function () {
                closeConfirm();
                setResult('Nehme auf \u2026', null);
                if (typeof opts.onImport === 'function') {
                    opts.onImport(ids);
                } else {
                    setResult('Kein Schreibpfad verdrahtet.', true);
                }
            });
            confirmBox.appendChild(yes);

            var no = doc.createElement('button');
            no.type = 'button';
            no.id = 'aiw-cases-confirm-no';
            no.className = 'aiw-btn aiw-cases-btn';
            no.textContent = 'Abbrechen';
            no.addEventListener('click', function () {
                closeConfirm();
                setResult('Abgebrochen. Es wurde nichts geschrieben.', false);
            });
            confirmBox.appendChild(no);
        }

        btn.addEventListener('click', openConfirm);

        // --- Tabulator -------------------------------------------------------
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        if (typeof Ctor !== 'function') {
            var note = doc.createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Tabellenbibliothek nicht verfuegbar. '
                + 'Warnungen und Zaehler oben sind dennoch gueltig.';
            container.appendChild(note);
            log('renderCases: kein Tabulator-Ctor');
            return {
                table: null, setResult: setResult, showResult: showResult,
                getSelection: selectionIds, setStats: function () {}
            };
        }

        // Auswahlspalte: EIGENER Formatter statt Tabulators 'rowSelection'.
        // Grund: wir brauchen die Auswahl NUR fuer aufnehmbare Zeilen und
        // bewusst KEIN "alles auswaehlen" im Spaltenkopf. Ein eigener Formatter
        // macht diese Regel im Code sichtbar, statt sie einer Bibliotheksoption
        // anzuvertrauen.
        var auswahlSpalte = {
            title: '', field: 'selectable', width: 44, headerSort: false,
            hozAlign: 'center',
            kein_filter: true,       // ein Filter auf Kaestchen waere sinnlos
            formatter: function (cell) {
                var d = cell.getData();
                if (!d.selectable) {
                    var dash = doc.createElement('span');
                    dash.textContent = '\u2014';
                    dash.title = 'nicht aufnehmbar';
                    return dash;
                }
                var box = doc.createElement('input');
                box.type = 'checkbox';
                box.checked = !!selected[d.subject_id];
                box.setAttribute('data-subject-id', String(d.subject_id));
                box.setAttribute('aria-label',
                    'Fall ' + d.subject_id + ' aufnehmen');
                box.addEventListener('click', function (e) {
                    e.stopPropagation();   // kein Zeilen-Klick-Nebeneffekt
                });
                box.addEventListener('change', function () {
                    selected[d.subject_id] = box.checked;
                    closeConfirm();        // Auswahl geaendert -> alte Frage weg
                    refreshButton();
                    log('Auswahl:', selectionIds());
                });
                return box;
            }
        };

        // datenZeilen: die Zeilen fuer die Tabelle — mit den Werten der
        // gewaehlten Kennzahl-Spalten AN DER ZEILE. Ohne diesen Schritt waere
        // eine Kennzahl-Spalte sichtbar, aber nicht sortier- und filterbar
        // (Tabulator arbeitet ueber Felder, nicht ueber den Formatter).
        function datenZeilen(basis) {
            var liste = basis || filterByStatus(rows, sel.value);
            if (tk && statsDaten && gewaehlteStats.length) {
                return tk.statFelder(liste, statsDaten.stats || {},
                                     gewaehlteStats);
            }
            return liste;
        }

        function spaltenBauen() {
            var spalten = [auswahlSpalte].concat(_COLUMNS);
            if (tk && statsDaten) {
                var s = tk.statSpalten((statsDaten.katalog || []),
                                       gewaehlteStats,
                                       (statsDaten.stats || {}));
                if (s.unbekannt.length) {
                    log('Unbekannte Kennzahl-Spalten uebergangen:',
                        s.unbekannt);
                }
                spalten = spalten.concat(s.spalten);
            }
            return tk ? tk.spaltenMitFilter(rows, spalten) : spalten;
        }

        function spaltenNeuSetzen() {
            if (!table || typeof table.setColumns !== 'function') { return; }
            try { table.setColumns(spaltenBauen()); }
            catch (e) { log('setColumns fehlgeschlagen:', e); }
            if (typeof table.replaceData === 'function') {
                try { table.replaceData(datenZeilen()); } catch (e2) { log(e2); }
            }
        }

        function zustandSichern() {
            if (!tk || !table) { return; }
            tk.zustandSchreiben(SICHT_ID,
                tk.zustandAusTabelle(table, gewaehlteStats));
        }

        var gesichert = tk ? tk.zustandLesen(SICHT_ID) : null;
        if (gesichert && gesichert.spalten) {
            gewaehlteStats = gesichert.spalten.slice();
        }

        var table = new Ctor(container, {
            data: datenZeilen(rows),
            columns: spaltenBauen(),
            layout: 'fitColumns',
            index: 'subject_id',
            height: '440px',
            rowFormatter: function (row) {
                var el = row.getElement();
                if (el && el.classList) {
                    el.classList.add(_rowClass(row.getData().status));
                }
            }
        });

        // Build 534: gesicherten Bedienzustand anwenden und Aenderungen
        // sichern. Dieselben Ereignisse wie in der Zuweisung — beide Sichten
        // merken sich Sortierung und Filter auf dieselbe Weise.
        if (typeof table.on === 'function') {
            table.on('tableBuilt', function () {
                if (tk && gesichert) {
                    var felder = (table.getColumnDefinitions
                        ? table.getColumnDefinitions() : [])
                        .map(function (c) { return c.field; })
                        .filter(Boolean);
                    var weg = tk.zustandAnwenden(table, gesichert, felder);
                    if (weg.length) {
                        log('Gesicherter Zustand teilweise uebergangen:', weg);
                    }
                }
                trefferAnzeigen();
                // Kennzahlen NACH der Tabelle anfordern — die Sicht ist
                // sofort arbeitsfaehig, auch wenn die forensic-Dateien
                // langsam sind. Angefragt werden GENAU die angezeigten
                // Kennungen, auch die noch nicht aufgenommenen.
                if (typeof opts.onStats === 'function') {
                    opts.onStats(rows.map(function (r) {
                        return r.subject_id;
                    }));
                }
            });
            table.on('dataFiltered', function () {
                trefferAnzeigen();
                zustandSichern();
            });
            table.on('dataSorted', function () { zustandSichern(); });
        }

        function trefferAnzeigen() {
            if (!leiste) { return; }
            var sichtbar = rows.length;
            try {
                var d = (typeof table.getData === 'function')
                    ? table.getData('active') : null;
                if (Array.isArray(d)) { sichtbar = d.length; }
            } catch (e) { log('getData(active) fehlgeschlagen:', e); }
            leiste.setTreffer(sichtbar, rows.length);
        }

        // setStats: die Kennzahlen sind da (eigener, spaeterer Abruf).
        //   Nicht gelesene Faelle werden BENANNT — in ihren Zellen steht '—'
        //   und NIE eine 0 (Grundregel 1; die Regel selbst steht im
        //   gemeinsamen Tabellen-Werkzeug).
        function setStats(payload) {
            statsDaten = payload || null;
            if (leiste && leiste.spaltenwahl && statsDaten) {
                leiste.spaltenwahl.setKatalog(statsDaten.katalog || []);
                gewaehlteStats = leiste.spaltenwahl.getGewaehlt();
            }
            spaltenNeuSetzen();
            var probleme = (statsDaten && statsDaten.probleme) || [];
            if (probleme.length) {
                log('Kennzahlen: ' + probleme.length + ' Fall/Faelle ohne '
                    + 'lesbare forensic-Datenbank.');
            }
        }

        // Statusfilter: lokal (die Daten liegen bereits vollstaendig vor).
        // Die AUSWAHL bleibt dabei erhalten (sie lebt in 'selected', nicht im
        // DOM) — ein Filterwechsel darf keine getroffene Auswahl still
        // verlieren.
        sel.addEventListener('change', function () {
            var filtered = filterByStatus(rows, sel.value);
            if (typeof table.replaceData === 'function') {
                // Build 534: ueber datenZeilen(), damit die Kennzahl-Felder
                // auch nach einem Wechsel des Schnellfilters an den Zeilen
                // haengen — sonst waeren die Zusatzspalten danach leer, und
                // das saehe aus wie 'keine Werte' statt wie 'nicht neu
                // angehaengt'.
                table.replaceData(datenZeilen(filtered));
            }
            closeConfirm();
            refreshButton();
            trefferAnzeigen();
            log('Filter:', sel.value || '(alle)', '->', filtered.length,
                'Zeilen; Auswahl unveraendert:', selectionIds());
        });

        log('renderCases:', rows.length, 'Faelle,', warns.length, 'Warnungen,',
            selectableIds(data).length, 'aufnehmbar');

        return {
            table: table, setResult: setResult, showResult: showResult,
            getSelection: selectionIds, setStats: setStats
        };
    }

    // =========================================================================
    // 3) UMD-Ausgang: dieselbe API an window (Browser) UND module.exports
    //    (Node/Vitest) — die Tests pruefen den ECHTEN Code.
    // =========================================================================
    var API = {
        STATUS_LABEL: STATUS_LABEL,
        STATUS_ORDER: STATUS_ORDER,
        fmtBool: fmtBool,
        isSelectable: isSelectable,
        toRows: toRows,
        selectableIds: selectableIds,
        filterByStatus: filterByStatus,
        countsText: countsText,
        dirsText: dirsText,
        warningRows: warningRows,
        warningLine: warningLine,
        importRequest: importRequest,
        resultText: resultText,
        confirmText: confirmText,
        renderCases: renderCases
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitCases = API; }
})();
