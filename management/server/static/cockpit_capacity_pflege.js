// =============================================================================
// management/server/static/cockpit_capacity_pflege.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kapazitaetspflege
// =============================================================================
// Zweck:
//   Die PFLEGEFLAECHE der Kapazitaet (Build 559). Vier Bestaende aus
//   GET /api/capacity/stammdaten, jeder als eigene Tabelle ueber
//   cockpit_tablekit.js, dazu je ein Erfassungsformular auf die Schreibwege
//   aus Build 558.
//
// WARUM EINE EIGENE SICHT UND NICHT EIN ANBAU AN cockpit_capacity.js
//   (mc 2026-07-29): das Projekt hat diese Trennung schon einmal getroffen —
//   'policy' zeigt die RBAC-Matrix NUR LESEND, 'personnel' ist die zugehoerige
//   Pflegeflaeche. Dieselbe Zweiteilung an anderer Stelle anders zu loesen
//   waere genau die Uneinheitlichkeit, gegen die das Tabellen-Arbeitspaket
//   fuenfzehn Sichten umgebaut hat. Nebeneffekt: das ECharts-Diagramm wird
//   nicht bei jedem Speichern neu gezeichnet.
//
// DIE ZWEI DINGE, DIE DIE MASKE AUSDRUECKLICH SAGEN MUSS, weil korrektes
// Verhalten sonst wie ein Fehler aussieht:
//   1) ARBEITSZEIT IST APPEND-ONLY. Eine Korrektur legt eine NEUE datierte
//      Zeile an; die alte bleibt stehen, weil sie der Beleg fuer den Zeitraum
//      ist, in dem sie galt. Ohne Hinweis sieht das nach Doppelspeicherung
//      aus, und jemand loescht "die alte" — was nicht geht und auch nicht
//      gehen darf.
//   2) RECHENART IST NICHT GRUND. 'garantie'/'einschraenkung' ist die
//      Rechenart (schemagebunden, m008; sie traegt die Arithmetik
//      netto = max(basis - einschraenkungen, garantie_boden)). "Urlaub",
//      "Krank", "Schulung" sind GRUENDE aus einem frei erweiterbaren Katalog.
//      Beides sind getrennte Felder, und die Rechenart-Liste kommt VOM SERVER
//      (data.kinds) — eine im Frontend nachgebaute Kopie waere die zweite
//      Wahrheit, die eines Tages von der ersten abweicht.
//
// SCOPE WIRD SICHTBAR GEMACHT, NICHT NUR DURCHGESETZT: bei scope='eigene'
//   entfaellt die Personenauswahl (es gibt genau eine Person), und Feiertage
//   und Gruende erscheinen NUR LESEND — mit ausdruecklicher Begruendung, statt
//   dass Knoepfe fehlen und niemand weiss, warum. Ganz verstecken waere falsch:
//   ohne den Gruendekatalog stuende in den eigenen Abwesenheitszeilen ein
//   nackter Code.
//
// KEIN OPTIMISTISCHES UI: nach jedem Schreibvorgang laedt die Sicht neu. Auch
//   im Fehlerfall — dann zeigt die Liste den tatsaechlichen Stand (es wurde
//   nichts geschrieben). Muster: cockpit_personnel.js.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE + 'use strict'. 2) DEV-Debug-Logging zur Laufzeit umschaltbar
//   (window.AIW_COCKPIT_DEBUG). 3) Ausfuehrliche Kommentare. 4) Reine
//   Funktionen ohne DOM mit UMD-Ausgang -> vitest testet den ECHTEN Code.
//
// XSS: variabler Text ausschliesslich ueber textContent. Die Tabulator-
//   Standardformatter setzen Werte per textContent; die eigenen Formatter
//   dieser Datei bauen Knoepfe und schreiben Text ebenfalls nur so.
//
// Version: v0.8.559 · Build: 559 · 2026-07-29
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
        args.unshift('[AIW-Kapazitaetspflege]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var TAGE = [
        { feld: 'mon_min', kurz: 'Mo' }, { feld: 'tue_min', kurz: 'Di' },
        { feld: 'wed_min', kurz: 'Mi' }, { feld: 'thu_min', kurz: 'Do' },
        { feld: 'fri_min', kurz: 'Fr' }, { feld: 'sat_min', kurz: 'Sa' },
        { feld: 'sun_min', kurz: 'So' }
    ];

    // =========================================================================
    // 1) REINE FUNKTIONEN (ohne DOM, vollstaendig testbar).
    // =========================================================================

    function scopeText(scope) {
        if (scope === 'alle') {
            return 'Umfang: alle Ermittler:innen koennen gepflegt werden.';
        }
        if (scope === 'eigene') {
            return 'Umfang: nur die eigene Kapazitaet. Feiertage und '
                + 'Abwesenheitsgruende wirken auf alle Personen und werden '
                + 'deshalb nur angezeigt, nicht gepflegt.';
        }
        return 'Umfang: eingeschraenkt.';
    }

    function personLabel(zeile) {
        if (!zeile) { return ''; }
        return zeile.display_name || zeile.system_username
            || ('#' + zeile.person_id);
    }

    // wochenSumme: Minuten der sieben Wochentage. Sie steht als eigene Spalte,
    // weil "480/480/480/480/480/0/0" niemand im Kopf addiert — und weil die
    // Basis der Rechnung genau daraus entsteht.
    function wochenSumme(zeile) {
        var s = 0;
        TAGE.forEach(function (t) {
            var v = zeile ? zeile[t.feld] : 0;
            s += (typeof v === 'number' && isFinite(v)) ? v : 0;
        });
        return s;
    }

    // katalogLabel: Code -> Beschriftung, MIT sichtbarem Rueckfall. Ein
    // unbekannter Code wird als "code (unbekannt)" ausgewiesen und nicht
    // stillschweigend zu einem leeren Feld: ein Grund, der aus dem Katalog
    // entfernt wurde, ist ein Befund und kein Anzeigefehler (Grundregel 1).
    function katalogLabel(code, liste, feldCode, feldLabel) {
        if (code === null || code === undefined || code === '') { return ''; }
        var treffer = null;
        (liste || []).forEach(function (e) {
            if (e && e[feldCode] === code) { treffer = e; }
        });
        return treffer ? (treffer[feldLabel] || code)
                       : (code + ' (unbekannt)');
    }

    function kindLabel(code, kinds) {
        return katalogLabel(code, kinds, 'code', 'label');
    }
    function reasonLabel(code, reasons) {
        return katalogLabel(code, reasons, 'code', 'label');
    }

    // wertText: genau EINES von value_pct/value_minutes ist gesetzt (Schema-
    // CHECK). Die Tabelle zeigt beides in EINER Spalte, weil zwei Spalten mit
    // je zur Haelfte leeren Zellen schlechter lesbar sind als eine mit Einheit.
    function wertText(zeile) {
        if (!zeile) { return ''; }
        if (zeile.value_pct !== null && zeile.value_pct !== undefined) {
            return zeile.value_pct + ' %';
        }
        if (zeile.value_minutes !== null
                && zeile.value_minutes !== undefined) {
            return zeile.value_minutes + ' min';
        }
        return '';
    }

    // --- Zeilenaufbereitung ---------------------------------------------
    // ABGELEITETE FILTERFELDER STATT ROHWERTE (Regel 1 des UX-Bauplans):
    // die Kopffilter von tablekit arbeiten auf dem, was in der Zelle steht.
    // Ein Filter ueber 'einschraenkung'/'garantie' als Rohcode waere fuer die
    // Bedienung unbrauchbar; er laeuft deshalb ueber die Beschriftung.

    function worktimeRows(data) {
        var zeilen = (data && data.worktimes) || [];
        return zeilen.map(function (z) {
            var r = {
                id: z.id, person_id: z.person_id,
                person: personLabel(z),
                effective_from: z.effective_from || '',
                effective_to: z.effective_to || '(offen)',
                woche_min: wochenSumme(z),
                audit_seq: z.audit_seq
            };
            TAGE.forEach(function (t) {
                r[t.feld] = (typeof z[t.feld] === 'number') ? z[t.feld] : 0;
            });
            return r;
        });
    }

    function availabilityRows(data) {
        var zeilen = (data && data.availability) || [];
        var kinds = (data && data.kinds) || [];
        var reasons = (data && data.reasons) || [];
        return zeilen.map(function (z) {
            return {
                id: z.id, person_id: z.person_id,
                person: personLabel(z),
                zeitraum: (z.period_start || '') + ' bis ' + (z.period_end || ''),
                art: kindLabel(z.kind, kinds),
                wert: wertText(z),
                grund: reasonLabel(z.reason_code, reasons),
                note: z.note || '',
                audit_seq: z.audit_seq
            };
        });
    }

    function holidayRows(data) {
        return ((data && data.holidays) || []).map(function (z) {
            return {
                id: z.id, day: z.day || '', label: z.label || '',
                region: z.region || '(alle)', audit_seq: z.audit_seq
            };
        });
    }

    function reasonRows(data) {
        return ((data && data.reasons) || []).map(function (z) {
            return {
                code: z.code, label: z.label || '',
                sort: (typeof z.sort === 'number') ? z.sort : 0,
                audit_seq: z.audit_seq
            };
        });
    }

    function darfAnlagenweit(scope) { return scope === 'alle'; }

    // =========================================================================
    // 2) DOM / RENDER.
    // =========================================================================

    function _el(tag, cls, text) {
        var e = document.createElement(tag);
        if (cls) { e.className = cls; }
        if (text !== undefined && text !== null) { e.textContent = text; }
        return e;
    }

    function _feld(art, id, platzhalter, wert) {
        var i = document.createElement('input');
        i.type = art;
        i.id = id;
        if (platzhalter) { i.placeholder = platzhalter; }
        if (wert !== undefined && wert !== null) { i.value = wert; }
        i.className = 'aiw-input';
        return i;
    }

    function _auswahl(id, eintraege, wertFeld, textFeld) {
        var s = document.createElement('select');
        s.id = id;
        s.className = 'aiw-select';
        (eintraege || []).forEach(function (e) {
            var o = document.createElement('option');
            o.value = String(e[wertFeld]);
            o.textContent = String(e[textFeld]);
            s.appendChild(o);
        });
        return s;
    }

    function _knopf(id, text, onClick) {
        var b = document.createElement('button');
        b.type = 'button';
        b.id = id;
        b.className = 'aiw-btn';
        b.textContent = text;
        if (typeof onClick === 'function') {
            b.addEventListener('click', onClick);
        }
        return b;
    }

    // _abschnitt: Ueberschrift + optionaler Erklaertext + Behaelter. Die
    // Ueberschrift bekommt einen Hilfe-Anker (Build 548), damit die spaetere
    // Hilfsdokumente-Bibliothek (AP-3H/B540) hier andocken kann, ohne dass
    // jede Sicht noch einmal angefasst werden muss.
    function _abschnitt(mainEl, sicht, titel, erklaerung, tk) {
        var h = _el('h3', 'aiw-sectionhead', titel);
        if (tk && typeof tk.hilfeAnker === 'function') {
            tk.hilfeAnker(h, sicht + '.titel');
        }
        mainEl.appendChild(h);
        if (erklaerung) {
            mainEl.appendChild(_el('p', 'aiw-sectionsub', erklaerung));
        }
        var box = _el('div', 'aiw-capp-section');
        mainEl.appendChild(box);
        return box;
    }

    // _entfernenSpalte: Aktionsspalte mit einem Knopf je Zeile. Sie entsteht
    // im SPALTEN-FORMATTER und nicht im rowFormatter — so findet die
    // Konformitaetssuite sie, und der Knopf traegt seine Kennung an den Daten
    // (data-id), nicht an der Zeilenposition.
    function _entfernenSpalte(titel, idFeld, onClick, gesperrt) {
        return {
            title: titel, field: '_aktion', headerSort: false,
            formatter: function (cell) {
                var d = cell.getData ? cell.getData() : {};
                if (gesperrt) {
                    return _el('span', 'aiw-hint', '—');
                }
                var b = _knopf('', 'Entfernen', function () {
                    if (typeof onClick === 'function') { onClick(d[idFeld]); }
                });
                b.setAttribute('data-id', String(d[idFeld]));
                b.classList.add('aiw-btn-klein');
                return b;
            }
        };
    }

    // renderCapacityPflege: baut die ganze Sicht.
    //   data = Antwort von GET /api/capacity/stammdaten
    //   opts.Tabulator          — Konstruktor (injizierbar; Tests)
    //   opts.onWorktimeSet(body), opts.onAvailabilitySet(body),
    //   opts.onAvailabilityRemove(entry_id), opts.onHolidayAdd(body),
    //   opts.onHolidayRemove(holiday_id), opts.onReasonAdd(body)
    // Rueckgabe: { tables: [worktime, availability, holiday, reason],
    //              setResult(text, istFehler) }
    function renderCapacityPflege(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return { tables: [], setResult: function () {} }; }
        mainEl.textContent = '';

        var tk = (typeof window !== 'undefined')
            ? window.AIWTableKit : null;
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);
        var scope = data ? data.scope : null;
        var anlagenweit = darfAnlagenweit(scope);
        var personen = (data && data.persons) || [];
        var kinds = (data && data.kinds) || [];
        var reasons = (data && data.reasons) || [];

        var h = _el('h2', 'aiw-pagehead', 'Kapazitaetspflege');
        mainEl.appendChild(h);
        mainEl.appendChild(_el('p', 'aiw-pagesub', scopeText(scope)));

        // Ergebniszeile: EIN Ort fuer alle Rueckmeldungen, damit eine Meldung
        // nicht im jeweiligen Formular verschwindet, aus dem sie stammt.
        var ergebnis = _el('p', 'aiw-result', '');
        mainEl.appendChild(ergebnis);
        function setResult(text, istFehler) {
            ergebnis.textContent = text || '';
            ergebnis.className = 'aiw-result' + (istFehler ? ' aiw-error' : '');
        }

        var tables = [];

        function bauen(sicht, box, rows, columns, einheit, eigene) {
            if (!tk || typeof tk.tabelleAufbauen !== 'function') {
                // KEIN STILLER AUSFALL: die Zahl steht da, auch wenn die
                // Tabellenmechanik fehlt. Eine leere Flaeche saehe aus wie
                // "keine Daten vorhanden".
                box.appendChild(_el('div', 'aiw-placeholder',
                    'Tabellenmechanik nicht verfuegbar — es sind '
                    + rows.length + ' ' + einheit + ' hinterlegt.'));
                tables.push(null);
                return null;
            }
            var r = tk.tabelleAufbauen(document, box, {
                sicht: sicht, rows: rows, columns: columns, Ctor: Ctor,
                einheit: einheit, eigene: eigene || [],
                tabulator: {
                    layout: 'fitColumns',
                    placeholder: 'Keine ' + einheit + ' erfasst.'
                }
            });
            tables.push(r ? r.table : null);
            return r;
        }

        // ------------------------------------------------- 1) Arbeitszeiten
        var boxWt = _abschnitt(mainEl, 'capacity_worktime',
            'Regel-Arbeitszeiten',
            'Minuten je Wochentag, gueltig ab einem Stichtag. Eine Korrektur '
            + 'legt eine NEUE Zeile an — die bisherige bleibt stehen, weil sie '
            + 'der Beleg fuer den Zeitraum ist, in dem sie galt. Es gilt '
            + 'jeweils die Zeile mit dem juengsten Stichtag vor dem Tag der '
            + 'Berechnung.', tk);

        var spaltenWt = [
            { title: 'Person', field: 'person' },
            { title: 'Gueltig ab', field: 'effective_from' },
            { title: 'Bis', field: 'effective_to' }
        ];
        TAGE.forEach(function (t) {
            spaltenWt.push({ title: t.kurz, field: t.feld, hozAlign: 'right' });
        });
        spaltenWt.push({ title: 'Woche (min)', field: 'woche_min',
                         hozAlign: 'right' });
        spaltenWt.push({ title: 'Beleg', field: 'audit_seq',
                         hozAlign: 'right' });

        var formWt = _el('div', 'aiw-capp-form');
        var wtPerson = anlagenweit
            ? _auswahl('aiw-capp-wt-person', personen, 'id', 'display_name')
            : null;
        if (wtPerson) {
            formWt.appendChild(_el('label', 'aiw-label', 'Person'));
            formWt.appendChild(wtPerson);
        }
        var wtAb = _feld('date', 'aiw-capp-wt-ab', 'gueltig ab');
        formWt.appendChild(_el('label', 'aiw-label', 'Gueltig ab'));
        formWt.appendChild(wtAb);
        var wtFelder = {};
        TAGE.forEach(function (t) {
            formWt.appendChild(_el('label', 'aiw-label', t.kurz));
            wtFelder[t.feld] = _feld('number', 'aiw-capp-wt-' + t.feld,
                                     'min', '0');
            formWt.appendChild(wtFelder[t.feld]);
        });
        formWt.appendChild(_knopf('aiw-capp-wt-save', 'Arbeitszeit speichern',
            function () {
                var body = {
                    person_id: wtPerson ? Number(wtPerson.value)
                                        : (data && data.person_id),
                    effective_from: wtAb.value
                };
                TAGE.forEach(function (t) {
                    body[t.feld] = Number(wtFelder[t.feld].value || 0);
                });
                if (typeof opts.onWorktimeSet === 'function') {
                    opts.onWorktimeSet(body);
                }
            }));
        boxWt.appendChild(formWt);
        bauen('capacity_worktime', boxWt, worktimeRows(data), spaltenWt,
              'Arbeitszeit-Regeln');

        // -------------------------------------------------- 2) Abwesenheiten
        var boxAv = _abschnitt(mainEl, 'capacity_availability',
            'Abwesenheiten und Garantien',
            'RECHENART und GRUND sind zweierlei. Die Rechenart entscheidet, '
            + 'WIE gerechnet wird (Einschraenkung = Abzug, Garantie = '
            + 'Mindestboden); sie ist fest. Der Grund sagt, WARUM — "Urlaub", '
            + '"Krank", "Schulung" — und wird von der Leitung gepflegt.', tk);

        var spaltenAv = [
            { title: 'Person', field: 'person' },
            { title: 'Zeitraum', field: 'zeitraum' },
            { title: 'Rechenart', field: 'art' },
            { title: 'Wert', field: 'wert', hozAlign: 'right' },
            { title: 'Grund', field: 'grund' },
            { title: 'Notiz', field: 'note' },
            { title: 'Beleg', field: 'audit_seq', hozAlign: 'right' },
            _entfernenSpalte('Aktion', 'id', function (id) {
                if (typeof opts.onAvailabilityRemove === 'function') {
                    opts.onAvailabilityRemove(id);
                }
            }, false)
        ];

        var formAv = _el('div', 'aiw-capp-form');
        var avPerson = anlagenweit
            ? _auswahl('aiw-capp-av-person', personen, 'id', 'display_name')
            : null;
        if (avPerson) {
            formAv.appendChild(_el('label', 'aiw-label', 'Person'));
            formAv.appendChild(avPerson);
        }
        var avVon = _feld('date', 'aiw-capp-av-von');
        var avBis = _feld('date', 'aiw-capp-av-bis');
        // Die Rechenarten kommen VOM SERVER (data.kinds) — keine zweite Kopie.
        var avArt = _auswahl('aiw-capp-av-art', kinds, 'code', 'label');
        var avGrund = _auswahl('aiw-capp-av-grund',
            [{ code: '', label: '(kein Grund)' }].concat(reasons),
            'code', 'label');
        var avPct = _feld('number', 'aiw-capp-av-pct', 'Prozent');
        var avMin = _feld('number', 'aiw-capp-av-min', 'Minuten');
        var avNotiz = _feld('text', 'aiw-capp-av-note', 'Notiz');
        [['Von', avVon], ['Bis', avBis], ['Rechenart', avArt],
         ['Grund', avGrund], ['Prozent', avPct], ['Minuten', avMin],
         ['Notiz', avNotiz]].forEach(function (paar) {
            formAv.appendChild(_el('label', 'aiw-label', paar[0]));
            formAv.appendChild(paar[1]);
        });
        formAv.appendChild(_el('p', 'aiw-hint',
            'Genau EINES von Prozent oder Minuten ausfuellen — beides zugleich '
            + 'weist der Server zurueck (Schema-Regel, kein Formularfehler).'));
        formAv.appendChild(_knopf('aiw-capp-av-save', 'Abwesenheit speichern',
            function () {
                var body = {
                    person_id: avPerson ? Number(avPerson.value)
                                        : (data && data.person_id),
                    period_start: avVon.value, period_end: avBis.value,
                    kind: avArt.value,
                    reason_code: avGrund.value || null,
                    note: avNotiz.value || null
                };
                // Leerfelder werden zu null und NICHT zu 0: eine 0 waere eine
                // Angabe ("null Minuten"), ein leeres Feld ist keine.
                body.value_pct = avPct.value === '' ? null
                                                    : Number(avPct.value);
                body.value_minutes = avMin.value === '' ? null
                                                        : Number(avMin.value);
                if (typeof opts.onAvailabilitySet === 'function') {
                    opts.onAvailabilitySet(body);
                }
            }));
        boxAv.appendChild(formAv);
        bauen('capacity_availability', boxAv, availabilityRows(data),
              spaltenAv, 'Abwesenheiten');

        // ------------------------------------------------------ 3) Feiertage
        var boxHo = _abschnitt(mainEl, 'capacity_holiday', 'Feiertage',
            anlagenweit
                ? 'Ein Feiertag entfernt den Tag aus der Basis ALLER Personen.'
                : 'Feiertage wirken auf alle Personen und sind deshalb nur '
                  + 'mit dem vollen Pflegeumfang aenderbar. Hier stehen sie '
                  + 'zur Ansicht, damit die eigene Berechnung nachvollziehbar '
                  + 'bleibt.', tk);
        var spaltenHo = [
            { title: 'Tag', field: 'day' },
            { title: 'Bezeichnung', field: 'label' },
            { title: 'Region', field: 'region' },
            { title: 'Beleg', field: 'audit_seq', hozAlign: 'right' },
            _entfernenSpalte('Aktion', 'id', function (id) {
                if (typeof opts.onHolidayRemove === 'function') {
                    opts.onHolidayRemove(id);
                }
            }, !anlagenweit)
        ];
        if (anlagenweit) {
            var formHo = _el('div', 'aiw-capp-form');
            var hoTag = _feld('date', 'aiw-capp-ho-tag');
            var hoLabel = _feld('text', 'aiw-capp-ho-label', 'Bezeichnung');
            var hoRegion = _feld('text', 'aiw-capp-ho-region',
                                 'Region (optional)');
            [['Tag', hoTag], ['Bezeichnung', hoLabel],
             ['Region', hoRegion]].forEach(function (paar) {
                formHo.appendChild(_el('label', 'aiw-label', paar[0]));
                formHo.appendChild(paar[1]);
            });
            formHo.appendChild(_knopf('aiw-capp-ho-save', 'Feiertag anlegen',
                function () {
                    if (typeof opts.onHolidayAdd === 'function') {
                        opts.onHolidayAdd({
                            day: hoTag.value, label: hoLabel.value,
                            region: hoRegion.value || null
                        });
                    }
                }));
            boxHo.appendChild(formHo);
        }
        bauen('capacity_holiday', boxHo, holidayRows(data), spaltenHo,
              'Feiertage');

        // ------------------------------------------------------- 4) Gruende
        var boxRe = _abschnitt(mainEl, 'capacity_reason',
            'Abwesenheitsgruende',
            anlagenweit
                ? 'Der Katalog ist frei erweiterbar: welche Abwesenheitsarten '
                  + 'legitim sind, entscheidet die Leitung, nicht der Code. '
                  + 'Ein Grund wird nie hart geloescht, sondern stillgelegt — '
                  + 'bestehende Eintraege behalten ihren Bezug.'
                : 'Der Gruendekatalog wirkt auf alle Personen und ist deshalb '
                  + 'nur mit dem vollen Pflegeumfang aenderbar. Er steht hier, '
                  + 'damit die eigenen Abwesenheitszeilen lesbar sind.', tk);
        var spaltenRe = [
            { title: 'Code', field: 'code' },
            { title: 'Bezeichnung', field: 'label' },
            { title: 'Reihung', field: 'sort', hozAlign: 'right' },
            { title: 'Beleg', field: 'audit_seq', hozAlign: 'right' }
        ];
        if (anlagenweit) {
            var formRe = _el('div', 'aiw-capp-form');
            var reCode = _feld('text', 'aiw-capp-re-code', 'Code (z. B. urlaub)');
            var reLabel = _feld('text', 'aiw-capp-re-label', 'Bezeichnung');
            var reSort = _feld('number', 'aiw-capp-re-sort', 'Reihung', '0');
            [['Code', reCode], ['Bezeichnung', reLabel],
             ['Reihung', reSort]].forEach(function (paar) {
                formRe.appendChild(_el('label', 'aiw-label', paar[0]));
                formRe.appendChild(paar[1]);
            });
            formRe.appendChild(_knopf('aiw-capp-re-save', 'Grund anlegen',
                function () {
                    if (typeof opts.onReasonAdd === 'function') {
                        opts.onReasonAdd({
                            code: reCode.value, label: reLabel.value,
                            sort: Number(reSort.value || 0)
                        });
                    }
                }));
            boxRe.appendChild(formRe);
        }
        bauen('capacity_reason', boxRe, reasonRows(data), spaltenRe,
              'Abwesenheitsgruende');

        log('gerendert: scope', scope, '/ Tabellen', tables.length);
        return { tables: tables, setResult: setResult };
    }

    // =========================================================================
    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        TAGE: TAGE,
        scopeText: scopeText,
        personLabel: personLabel,
        wochenSumme: wochenSumme,
        kindLabel: kindLabel,
        reasonLabel: reasonLabel,
        wertText: wertText,
        worktimeRows: worktimeRows,
        availabilityRows: availabilityRows,
        holidayRows: holidayRows,
        reasonRows: reasonRows,
        darfAnlagenweit: darfAnlagenweit,
        renderCapacityPflege: renderCapacityPflege
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') {
        window.AIWCockpitCapacityPflege = API;
    }
})();
