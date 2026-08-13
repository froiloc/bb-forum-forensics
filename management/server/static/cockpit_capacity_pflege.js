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
// BUILD 561 — WAS mc BEIM TESTEN GEFUNDEN HAT, UND WARUM ES SCHLIMMER WAR,
//   ALS ES AUSSAH: nach dem Speichern lud die Sicht neu und zeichnete das
//   Formular VOLLSTAENDIG NEU - dabei wurde auch das Stichtagsfeld geleert.
//   Wer danach einen Wert korrigierte, schickte ihn OHNE Datum ab; der Server
//   lehnte mit 400 ab. Es sah aus, als nehme das Werkzeug keine Aenderungen
//   mehr an - fuer keine Person. Ein leeres Pflichtfeld, das erst der Server
//   bemaengelt, ist eine Falle; und die Personenauswahl sprang zusaetzlich auf
//   den ersten Eintrag zurueck, was im schlimmsten Fall auf die FALSCHE Person
//   geschrieben haette. Vier Netze dagegen:
//     1) Der Formularzustand ueberlebt das Neuladen (opts.formular).
//     2) Die Personenauswahl behaelt die getroffene Wahl.
//     3) Das Stichtagsfeld ist mit dem heutigen Tag vorbelegt.
//     4) Die Rueckmeldung schreibt aus, WAS uebernommen wurde - nicht nur
//        "gespeichert".
//   Im Fehlerfall markiert die Maske ausserdem das schuldige Feld anhand von
//   'feld' aus der Antwort (Build 560). Bei sieben Minutenfeldern nebeneinander
//   ist ein Satz unter dem Formular sonst eine Suchaufgabe.
//
// ENTFERNEN UND BEARBEITEN (Build 560/561): 'Entfernen' ist ein SOFT-DELETE -
//   die Zeile bleibt in der Datenbank und faellt nur aus Rechnung und Liste.
//   'Bearbeiten' fuellt das Formular aus der Zeile und schaltet auf ERSETZEN:
//   das Speichern entfernt dann die alte Zeile und schreibt die neue in EINER
//   Transaktion. Das ist noetig, seit der Server eine zweite aktive Regel zum
//   selben Stichtag zurueckweist - und es ist der Weg, den mc gesucht hat.
//
// BUILD 563 — ENTFERNTE ZEILEN. 'Entfernen' ist ein Soft-Delete; die Zeile
//   bleibt in der Datenbank. Die Sicht zeigt jetzt BEIDES: eine Umschaltung
//   blendet sie ein, und AUCH WENN SIE AUS IST, steht die Zahl der
//   ausgeblendeten Zeilen da. Eine Umschaltung allein waere eine, die niemand
//   betaetigt - weil niemand ahnt, dass es etwas einzublenden gibt.
//   Eingeblendete entfernte Zeilen werden GEKENNZEICHNET (Spalte 'Stand' und
//   Zeilenklasse), sonst saehen sie aus wie gueltige Regeln; und ihre
//   Aktionsknoepfe entfallen, weil ein zweites Entfernen ohnehin abgewiesen
//   wuerde und 'Bearbeiten' eine stillgelegte Zeile ersetzen wollte.
//
// Build 637 (Vorgang 17200856, Welle B5 - die letzte): HILFE-MARKEN
//   fuer die siebenundzwanzig verbliebenen Bedienelemente dieser Sicht.
// Version: v0.8.637 · Build: 637 · 2026-08-01
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
                stand: istEntfernt(z) ? 'entfernt' : 'aktiv',
                _entfernt: istEntfernt(z),
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
                stand: istEntfernt(z) ? 'entfernt' : 'aktiv',
                _entfernt: istEntfernt(z),
                audit_seq: z.audit_seq,
                // BUILD 664: die ROHWERTE reisen mit. Die Spalten zeigen
                // Beschriftungen ('Urlaub', '50 %'), 'Bearbeiten' braucht
                // aber die Codes - aus 'Urlaub' laesst sich 'urlaub' nicht
                // zurueckrechnen, und aus '50 %' nicht, ob Prozent oder
                // Minuten gemeint waren. Sie stehen in keiner Spalte und
                // sind deshalb unsichtbar; sie sind der Bearbeitungspfad.
                _roh: {
                    person_id: z.person_id,
                    period_start: z.period_start || '',
                    period_end: z.period_end || '',
                    kind: z.kind,
                    value_pct: (z.value_pct === undefined) ? null
                                                           : z.value_pct,
                    value_minutes: (z.value_minutes === undefined) ? null
                                                                  : z.value_minutes,
                    reason_code: z.reason_code || '',
                    note: z.note || ''
                }
            };
        });
    }

    function holidayRows(data) {
        return ((data && data.holidays) || []).map(function (z) {
            return {
                id: z.id, day: z.day || '', label: z.label || '',
                region: z.region || '(alle)',
                stand: istEntfernt(z) ? 'entfernt' : 'aktiv',
                _entfernt: istEntfernt(z), audit_seq: z.audit_seq
            };
        });
    }

    function reasonRows(data) {
        return ((data && data.reasons) || []).map(function (z) {
            return {
                code: z.code, label: z.label || '',
                sort: (typeof z.sort === 'number') ? z.sort : 0,
                stand: istEntfernt(z) ? 'entfernt' : 'aktiv',
                _entfernt: istEntfernt(z), audit_seq: z.audit_seq
            };
        });
    }

    function darfAnlagenweit(scope) { return scope === 'alle'; }

    // istEntfernt: eine Zeile gilt als entfernt, sobald deleted_at gesetzt
    // ist. 0 ist KEIN gueltiger Zeitstempel in diesem Schema, aber auch kein
    // Grund, eine Zeile faelschlich fuer aktiv zu halten - deshalb die
    // Pruefung auf "vorhanden" statt auf "wahr".
    function istEntfernt(zeile) {
        return !!(zeile && zeile.deleted_at !== null
                  && zeile.deleted_at !== undefined);
    }

    // ausgeblendetText: die Zahl der NICHT gezeigten Zeilen in Worte fassen.
    // Rueckgabe null heisst "es ist nichts ausgeblendet" - dann steht auch
    // kein Hinweis da, statt eines Hinweises ueber null Zeilen.
    function ausgeblendetText(anzahl, einheit) {
        if (!anzahl) { return null; }
        return anzahl === 1
            ? ('1 entfernte Zeile ist ausgeblendet (' + einheit + ').')
            : (anzahl + ' entfernte Zeilen sind ausgeblendet ('
               + einheit + ').');
    }

    // historischText: die Zahl der wegen des Zeitfilters NICHT gezeigten
    // Zeilen in Worte fassen (Build 709, Vorgang 75f84fee).
    //
    // WARUM EIN EIGENER TEXT NEBEN ausgeblendetText(): Es sind zwei ganz
    // verschiedene Gruende, aus denen eine Zeile fehlen kann - stillgelegt
    // oder abgelaufen. Ein gemeinsamer Satz ("n Zeilen ausgeblendet") liesse
    // offen, welcher Schalter sie zurueckholt. Die GRENZE wird mitgenannt,
    // weil 'historisch' sonst eine Behauptung ohne Massstab ist.
    //
    // Rueckgabe null heisst "es ist nichts ausgeblendet" - dann steht auch
    // kein Hinweis da, statt eines Hinweises ueber null Zeilen.
    function historischText(anzahl, einheit, grenze) {
        if (!anzahl) { return null; }
        var ab = grenze ? (' vor dem ' + grenze) : '';
        return anzahl === 1
            ? ('1 historische Zeile ist ausgeblendet (' + einheit
               + ', abgelaufen' + ab + ').')
            : (anzahl + ' historische Zeilen sind ausgeblendet ('
               + einheit + ', abgelaufen' + ab + ').');
    }

    // heuteIso: Vorbelegung des Stichtags. Ein leeres Pflichtfeld, das erst
    // der Server bemaengelt, ist eine Falle (Befund mc, Build 560).
    function heuteIso(jetzt) {
        var d = jetzt ? new Date(jetzt) : new Date();
        function zwei(n) { return (n < 10 ? '0' : '') + n; }
        return d.getFullYear() + '-' + zwei(d.getMonth() + 1) + '-'
            + zwei(d.getDate());
    }

    // TAGESVORGABEN (mc 2026-07-29). Die Zahlen stehen NICHT im Code, weil der
    // Code sie braeuchte, sondern weil der Ausfuellende sie sonst nachschlagen
    // muss. Sie sind eine Hilfe, keine Regel: eintragen kann man jeden Wert.
    var VORGABEN = [
        { code: 'angestellte', label: 'Angestellte', minuten: 478 },
        { code: 'beamte', label: 'Beamte', minuten: 492 }
    ];

    // uebernahmeText: schreibt aus, WAS gespeichert wurde. "Gespeichert" allein
    // laesst offen, ob der eigene Tippfehler mitgespeichert wurde.
    function uebernahmeText(person, ab, minuten, beleg, ersetzt) {
        var teile = [];
        TAGE.forEach(function (t) {
            teile.push(t.kurz + ' ' + (minuten[t.feld] || 0));
        });
        return (ersetzt ? 'Ersetzt' : 'Gespeichert') + ': ' + person
            + ', ab ' + ab + ' — ' + teile.join(', ')
            + ' (Woche ' + wochenSumme(minuten) + ' min, Beleg #' + beleg + ')'
            + (ersetzt
                ? '. Die alte Zeile bleibt als Beleg erhalten.'
                : '');
    }

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
    //
    // BUILD 603: die Kennung wird VOLLSTAENDIG uebergeben und nicht mehr aus
    // der Abschnittskennung zusammengesetzt. Der Unterschied ist keine
    // Kosmetik: eine zusammengesetzte Kennung steht nirgends woertlich im
    // Quelltext, und die Paritaetspruefung (SP02) kann dann nicht sehen, dass
    // es zu einem Hilfetext auch eine Marke gibt. Das Konzept (§4.2a)
    // verlangt literale Marken genau aus diesem Grund.
    function _abschnitt(mainEl, ankerId, titel, erklaerung, tk) {
        var h = _el('h3', 'aiw-sectionhead', titel);
        if (tk && typeof tk.hilfeAnker === 'function') {
            tk.hilfeAnker(h, ankerId);
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
                // Build 637 (Vorgang 17200856): Hilfe-Marke, LITERAL an der
                // Abnahmestelle der Fabrik '_knopf' (Fabrikregel, Build 633).
                b.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.entfernen');
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

        // FORMULARZUSTAND (Build 561): die zuletzt eingegebenen Werte kommen
        // vom Lader zurueck und werden wieder eingesetzt. Ohne das leert jedes
        // Neuladen das Stichtagsfeld, und die naechste Eingabe scheitert am
        // Server - genau der Befund von mc.
        var f = opts.formular || {};
        var wtVorgabe = f.worktime || {};
        // Build 664 (Ticket 7b2f4a19): dasselbe fuer die Abwesenheiten. Ohne
        // den Formularzustand ginge eine begonnene Bearbeitung beim ersten
        // Serverfehler verloren - und der Fehler ist genau der Moment, in dem
        // die Eingaben am dringendsten stehenbleiben muessen.
        var avVorgabe = f.availability || {};
        var avErsetztId = avVorgabe._ersetzt_id || null;

        var h = _el('h2', 'aiw-pagehead', 'Kapazitaetspflege');
        // Build 603 (Baustelle H / H12): literale Hilfe-Marken.
        h.setAttribute('data-hilfe-id', 'capacity_pflege.titel');
        mainEl.appendChild(h);
        var umfangEl = _el('p', 'aiw-pagesub', scopeText(scope));
        umfangEl.setAttribute('data-hilfe-id', 'capacity_pflege.kennzeile');
        mainEl.appendChild(umfangEl);

        // Ergebniszeile: EIN Ort fuer alle Rueckmeldungen, damit eine Meldung
        // nicht im jeweiligen Formular verschwindet, aus dem sie stammt.
        var ergebnis = _el('p', 'aiw-result', '');
        mainEl.appendChild(ergebnis);
        function setResult(text, istFehler) {
            ergebnis.textContent = text || '';
            ergebnis.className = 'aiw-result' + (istFehler ? ' aiw-error' : '');
        }

        // UMSCHALTUNG 'auch entfernte anzeigen' (Build 563). Sie sitzt im
        // Kopf und gilt fuer ALLE VIER Bestaende gemeinsam - vier einzelne
        // Schalter waeren vier Orte, an denen man den Ueberblick verlieren
        // kann. Der Zustand kommt vom Server zurueck (data.include_deleted),
        // nicht aus dem Frontend: sonst koennte der Haken gesetzt sein,
        // waehrend die Liste noch die alte Antwort zeigt.
        var entferntZahlen = (data && data.entfernt) || {};
        var zeigeEntfernte = !!(data && data.include_deleted);
        var schalterZeile = _el('div', 'aiw-capp-schalter');
        var schalter = document.createElement('input');
        schalter.type = 'checkbox';
        schalter.id = 'aiw-capp-entfernte';
        schalter.checked = zeigeEntfernte;
        schalter.setAttribute('data-hilfe-id',
                              'capacity_pflege.bedienung.entfernte');
        schalter.addEventListener('change', function () {
            if (typeof opts.onEntfernteUmschalten === 'function') {
                opts.onEntfernteUmschalten(schalter.checked);
            }
        });
        var schalterLabel = document.createElement('label');
        schalterLabel.setAttribute('for', 'aiw-capp-entfernte');
        schalterLabel.className = 'aiw-label';
        schalterLabel.textContent = 'Auch entfernte Zeilen anzeigen';
        schalterZeile.appendChild(schalter);
        schalterZeile.appendChild(schalterLabel);
        var gesamtEntfernt = ['worktimes', 'availability', 'holidays',
                              'reasons'].reduce(function (s2, k) {
            return s2 + (entferntZahlen[k] || 0);
        }, 0);
        schalterZeile.appendChild(_el('span', 'aiw-hint',
            gesamtEntfernt
                ? (zeigeEntfernte
                    ? (gesamtEntfernt + ' entfernte Zeile(n) sind eingeblendet '
                       + 'und gekennzeichnet.')
                    : (gesamtEntfernt + ' entfernte Zeile(n) sind derzeit '
                       + 'ausgeblendet.'))
                : 'Es ist nichts entfernt.'));
        mainEl.appendChild(schalterZeile);

        // UMSCHALTUNG 'auch historische Daten anzeigen' (Build 709, Vorgang
        // 75f84fee). Zweite Zeile statt zweiter Haken in derselben - die
        // beiden Schalter blenden aus VERSCHIEDENEN Gruenden aus
        // (stillgelegt / abgelaufen), und sie wirken auf verschiedene
        // Bestaende. Nebeneinander in einer Zeile laege der Schluss nahe, es
        // sei zweimal dasselbe.
        //
        // WIE BEIM ENTFERNT-SCHALTER kommt der Zustand VOM SERVER
        // (data.include_historic) und nicht aus dem Frontend: sonst koennte
        // der Haken gesetzt sein, waehrend die Liste noch die alte Antwort
        // zeigt. Und gefiltert wird ebenfalls auf dem Server - ein
        // Frontend-Filter waere eine zweite Wahrheit ueber Sichtbarkeit.
        var histZahlen = (data && data.historisch) || {};
        var zeigeHistorie = !!(data && data.include_historic);
        var historischAb = (data && data.historisch_ab) || '';
        // Dieselbe Grundgestalt wie die Zeile darueber (aiw-capp-schalter),
        // dazu eine eigene Kennung: sie macht die beiden Zeilen fuer
        // Formatierung UND Pruefung unterscheidbar.
        var histZeile = _el('div', 'aiw-capp-schalter aiw-capp-historie');
        var histSchalter = document.createElement('input');
        histSchalter.type = 'checkbox';
        histSchalter.id = 'aiw-capp-historisch';
        histSchalter.checked = zeigeHistorie;
        histSchalter.setAttribute('data-hilfe-id',
                                  'capacity_pflege.bedienung.historisch');
        histSchalter.addEventListener('change', function () {
            if (typeof opts.onHistorieUmschalten === 'function') {
                opts.onHistorieUmschalten(histSchalter.checked);
            }
        });
        var histLabel = document.createElement('label');
        histLabel.setAttribute('for', 'aiw-capp-historisch');
        histLabel.className = 'aiw-label';
        histLabel.textContent = 'Auch historische Daten anzeigen';
        histZeile.appendChild(histSchalter);
        histZeile.appendChild(histLabel);
        var gesamtHistorisch = ['availability', 'holidays'].reduce(
            function (s3, k) { return s3 + (histZahlen[k] || 0); }, 0);
        // DIE GRENZE STEHT IMMER DA, auch wenn nichts ausgeblendet ist. Sie
        // ist die Antwort auf die Frage, die der Schalter aufwirft: ab wann
        // gilt eine Zeile als historisch?
        histZeile.appendChild(_el('span', 'aiw-hint',
            (gesamtHistorisch
                ? (zeigeHistorie
                    ? (gesamtHistorisch + ' historische Zeile(n) sind '
                       + 'eingeblendet.')
                    : (gesamtHistorisch + ' historische Zeile(n) sind derzeit '
                       + 'ausgeblendet.'))
                : 'Es liegt nichts vor dem laufenden Monat.')
            + (historischAb
                ? (' Angezeigt wird ab dem ' + historischAb
                   + '; abgelaufen heisst: Ende davor.')
                : '')));
        mainEl.appendChild(histZeile);

        // FELDMARKIERUNG: der Server nennt seit Build 560 das schuldige Feld.
        // Kennt er keines, wird auch keines markiert - ein geratenes rotes
        // Feld waere schlimmer als gar keines.
        function markiereFeld(feldName) {
            Array.prototype.forEach.call(
                mainEl.querySelectorAll('.aiw-feldfehler'),
                function (e) { e.classList.remove('aiw-feldfehler'); });
            if (!feldName) { return null; }
            var el = mainEl.querySelector('[data-feld="' + feldName + '"]');
            if (el) {
                el.classList.add('aiw-feldfehler');
                if (typeof el.focus === 'function') { el.focus(); }
            }
            return el;
        }

        var tables = [];

        function bauen(sicht, box, rows, columns, einheit, eigene, entferntZahl,
                       historischZahl) {
            // JE ABSCHNITT die eigene Zahl - eine Gesamtzahl im Kopf sagt
            // nicht, WO etwas fehlt. Der Hinweis entfaellt, sobald die Zeilen
            // eingeblendet sind (dann stehen sie ja da).
            if (!zeigeEntfernte) {
                var hinw = ausgeblendetText(entferntZahl, einheit);
                if (hinw) {
                    box.appendChild(_el('p', 'aiw-hint aiw-capp-ausgeblendet',
                                        hinw));
                }
            }
            // Build 709: dasselbe fuer den Zeitfilter - und ausdruecklich als
            // ZWEITE Zeile. Die beiden Gruende (stillgelegt / abgelaufen)
            // sind verschieden, und wer eine Zeile sucht, muss wissen, WELCHER
            // Schalter sie zurueckholt.
            if (!zeigeHistorie) {
                var hinwH = historischText(historischZahl, einheit,
                                           historischAb);
                if (hinwH) {
                    box.appendChild(_el('p', 'aiw-hint aiw-capp-historisch',
                                        hinwH));
                }
            }
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
                    placeholder: 'Keine ' + einheit + ' erfasst.',
                    // Entfernte Zeilen bekommen eine eigene Klasse. OHNE
                    // Kennzeichnung saehen sie aus wie gueltige Regeln - und
                    // genau das waere schlimmer als sie wegzulassen.
                    rowFormatter: function (row) {
                        var d = row.getData ? row.getData() : null;
                        if (d && d._entfernt && row.getElement) {
                            row.getElement().classList.add('aiw-zeile-entfernt');
                        }
                    }
                }
            });
            tables.push(r ? r.table : null);
            return r;
        }

        // ------------------------------------------------- 1) Arbeitszeiten
        var boxWt = _abschnitt(mainEl, 'capacity_worktime.titel',
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
        if (zeigeEntfernte) {
            spaltenWt.push({ title: 'Stand', field: 'stand' });
        }

        // ERSETZEN-MODUS: haelt die Zeile fest, die 'Bearbeiten' gewaehlt hat.
        // Solange sie gesetzt ist, geht das Speichern auf /replace statt auf
        // /worktime - der einzige Weg, der seit der Dublettensperre eine
        // Korrektur zum SELBEN Stichtag zulaesst.
        var ersetztId = (f.worktime && f.worktime._ersetzt_id) || null;

        var formWt = _el('div', 'aiw-capp-form');
        // Build 637: aus dem Fragezeichen-Ausdruck eine Zuweisung gemacht.
        // Eine Abnahmestelle, die nicht mit 'var X =' beginnt, kann die
        // Erhebung nicht als solche erkennen - und dann gilt die ganze
        // Fabrik als unmarkiert. Am Verhalten aendert sich nichts.
        var wtPerson = null;
        if (anlagenweit) {
            var wtPersonFeld = _auswahl('aiw-capp-wt-person', personen, 'id',
                                        'display_name');
            wtPersonFeld.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.wt_person');
            wtPerson = wtPersonFeld;
        }
        if (wtPerson) {
            wtPerson.setAttribute('data-feld', 'person_id');
            if (wtVorgabe.person_id !== undefined
                    && wtVorgabe.person_id !== null) {
                wtPerson.value = String(wtVorgabe.person_id);
            }
            formWt.appendChild(_el('label', 'aiw-label', 'Person'));
            formWt.appendChild(wtPerson);
        }
        var wtAb = _feld('date', 'aiw-capp-wt-ab', 'gueltig ab',
                         wtVorgabe.effective_from || heuteIso());
        wtAb.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.wt_ab');
        wtAb.setAttribute('data-feld', 'effective_from');
        formWt.appendChild(_el('label', 'aiw-label', 'Gueltig ab'));
        formWt.appendChild(wtAb);
        var wtFelder = {};
        TAGE.forEach(function (t) {
            formWt.appendChild(_el('label', 'aiw-label', t.kurz));
            var v = (wtVorgabe[t.feld] === undefined
                     || wtVorgabe[t.feld] === null)
                ? '0' : String(wtVorgabe[t.feld]);
            var wtFeld = _feld('number', 'aiw-capp-wt-' + t.feld, 'min', v);
            wtFeld.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.wt_minuten');
            wtFeld.setAttribute('data-feld', t.feld);
            wtFeld.classList.add('aiw-minutenfeld');
            wtFelder[t.feld] = wtFeld;
            formWt.appendChild(wtFeld);
        });

        // Tagesvorgaben: Hinweis UND Griff. Wer die Zahl liest, traegt sie
        // danach ohnehin siebenmal ein - der Knopf nimmt genau diesen Schritt ab
        // (Mo-Fr auf den Wert, Sa/So auf 0).
        var hinweis = _el('div', 'aiw-capp-vorgaben');
        hinweis.appendChild(_el('span', 'aiw-hint',
            'Ueblich sind ' + VORGABEN.map(function (v) {
                return v.label + ' ' + v.minuten + ' min/Tag';
            }).join(', ') + '. Abweichungen sind zulaessig.'));
        VORGABEN.forEach(function (v) {
            // Build 637: frueher direkt in appendChild. Eine Abnahmestelle
            // ohne Variable kann keine Marke tragen - der Knopf waere stumm.
            var bVorgabe = _knopf('aiw-capp-wt-vorgabe-' + v.code,
                v.label + ' (' + v.minuten + ')', function () {
                    TAGE.forEach(function (t) {
                        var werktag = t.feld !== 'sat_min'
                            && t.feld !== 'sun_min';
                        wtFelder[t.feld].value = werktag ? String(v.minuten) : '0';
                    });
                });
            bVorgabe.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.wt_vorgabe');
            hinweis.appendChild(bVorgabe);
        });
        formWt.appendChild(hinweis);

        function wtNutzlast() {
            var body = {
                person_id: wtPerson ? Number(wtPerson.value)
                                    : (data && data.person_id),
                effective_from: wtAb.value
            };
            TAGE.forEach(function (t) {
                body[t.feld] = Number(wtFelder[t.feld].value || 0);
            });
            return body;
        }

        if (ersetztId) {
            var warnung = _el('p', 'aiw-capp-ersetzt',
                'Bearbeitungsmodus: Speichern ERSETZT Zeile #' + ersetztId
                + '. Die alte Zeile wird stillgelegt und bleibt als Beleg '
                + 'erhalten.');
            formWt.appendChild(warnung);
            var bWtAb = _knopf('aiw-capp-wt-abbrechen',
                'Bearbeitung abbrechen', function () {
                    if (typeof opts.onWorktimeEditAbort === 'function') {
                        opts.onWorktimeEditAbort();
                    }
                });
            bWtAb.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.wt_abbrechen');
            formWt.appendChild(bWtAb);
        }

        var bWtSave = _knopf('aiw-capp-wt-save',
            ersetztId ? 'Zeile ersetzen' : 'Arbeitszeit speichern',
            function () {
                var body = wtNutzlast();
                if (ersetztId) {
                    body.worktime_id = ersetztId;
                    if (typeof opts.onWorktimeReplace === 'function') {
                        opts.onWorktimeReplace(body);
                    }
                } else if (typeof opts.onWorktimeSet === 'function') {
                    opts.onWorktimeSet(body);
                }
            });
        bWtSave.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.wt_speichern');
        formWt.appendChild(bWtSave);
        boxWt.appendChild(formWt);

        // Aktionsspalte: Bearbeiten UND Entfernen. 'Bearbeiten' schreibt
        // nichts - es fuellt nur das Formular und schaltet den Modus um.
        spaltenWt.push({
            title: 'Aktion', field: '_aktion', headerSort: false,
            formatter: function (cell) {
                var d = cell.getData ? cell.getData() : {};
                var box = _el('span', 'aiw-aktionen');
                if (d._entfernt) {
                    // Kein Knopf auf einer stillgelegten Zeile: ein zweites
                    // Entfernen wiese der Server ohnehin ab, und 'Bearbeiten'
                    // wollte eine Zeile ersetzen, die nicht mehr gilt.
                    box.appendChild(_el('span', 'aiw-hint', 'entfernt'));
                    return box;
                }
                var bE = _knopf('', 'Bearbeiten', function () {
                    if (typeof opts.onWorktimeEdit === 'function') {
                        opts.onWorktimeEdit(d);
                    }
                });
                bE.classList.add('aiw-btn-klein');
                bE.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.wt_bearbeiten');
                bE.setAttribute('data-id', String(d.id));
                var bX = _knopf('', 'Entfernen', function () {
                    if (typeof opts.onWorktimeRemove === 'function') {
                        opts.onWorktimeRemove(d.id);
                    }
                });
                bX.classList.add('aiw-btn-klein');
                bX.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.wt_entfernen');
                bX.setAttribute('data-id', String(d.id));
                box.appendChild(bE);
                box.appendChild(bX);
                return box;
            }
        });

        bauen('capacity_worktime', boxWt, worktimeRows(data), spaltenWt,
              'Arbeitszeit-Regeln', [], entferntZahlen.worktimes);

        // -------------------------------------------------- 2) Abwesenheiten
        var boxAv = _abschnitt(mainEl, 'capacity_availability.titel',
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
            // BUILD 664: Bearbeiten UND Entfernen (wie bei den Arbeitszeiten
            // seit Build 555). 'Bearbeiten' SCHREIBT NICHTS - es fuellt nur
            // das Formular und schaltet den Modus um.
            {
                title: 'Aktion', field: '_aktion', headerSort: false,
                formatter: function (cell) {
                    var d = cell.getData ? cell.getData() : {};
                    var box = _el('span', 'aiw-aktionen');
                    if (d._entfernt) {
                        // Kein Knopf auf einer stillgelegten Zeile: ein
                        // zweites Entfernen wiese der Server ohnehin ab, und
                        // 'Bearbeiten' wollte eine Zeile ersetzen, die nicht
                        // mehr gilt.
                        box.appendChild(_el('span', 'aiw-hint', 'entfernt'));
                        return box;
                    }
                    var bE = _knopf('', 'Bearbeiten', function () {
                        if (typeof opts.onAvailabilityEdit === 'function') {
                            opts.onAvailabilityEdit(d);
                        }
                    });
                    bE.classList.add('aiw-btn-klein');
                    bE.setAttribute('data-hilfe-id',
                                    'capacity_pflege.bedienung.av_bearbeiten');
                    bE.setAttribute('data-id', String(d.id));
                    var bX = _knopf('', 'Entfernen', function () {
                        if (typeof opts.onAvailabilityRemove === 'function') {
                            opts.onAvailabilityRemove(d.id);
                        }
                    });
                    bX.classList.add('aiw-btn-klein');
                    bX.setAttribute('data-hilfe-id',
                                    'capacity_pflege.bedienung.entfernen');
                    bX.setAttribute('data-id', String(d.id));
                    box.appendChild(bE);
                    box.appendChild(bX);
                    return box;
                }
            }
        ];

        var formAv = _el('div', 'aiw-capp-form');
        // Build 663: Steuerung der Von/Bis-Kopplung. Sie wird mit
        // zurueckgegeben, damit der Lader sie beim Neuzeichnen abmelden kann —
        // liegengebliebene Zuhoerer auf entsorgten Knoten sind die Sorte
        // Fehler, die man spaeter nicht mehr findet.
        var avKopplung = null;
        var avPerson = null;
        if (anlagenweit) {
            var avPersonFeld = _auswahl('aiw-capp-av-person', personen, 'id',
                                        'display_name');
            avPersonFeld.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.av_person');
            if (avVorgabe.person_id !== undefined
                    && avVorgabe.person_id !== null) {
                avPersonFeld.value = String(avVorgabe.person_id);
            }
            avPerson = avPersonFeld;
        }
        if (avPerson) {
            formAv.appendChild(_el('label', 'aiw-label', 'Person'));
            formAv.appendChild(avPerson);
        }
        var avVon = _feld('date', 'aiw-capp-av-von', '',
                          avVorgabe.period_start || '');
        avVon.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.av_von');
        avVon.setAttribute('data-feld', 'period_start');
        var avBis = _feld('date', 'aiw-capp-av-bis', '',
                          avVorgabe.period_end || '');
        avBis.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.av_bis');
        avBis.setAttribute('data-feld', 'period_end');
        // Die Rechenarten kommen VOM SERVER (data.kinds) — keine zweite Kopie.
        var avArt = _auswahl('aiw-capp-av-art', kinds, 'code', 'label');
        avArt.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.av_rechenart');
        if (avVorgabe.kind) { avArt.value = avVorgabe.kind; }
        // BUILD 663 — Ticket 65a230fd. Bis hierher zeigte die Auswahl bei
        // leerem Katalog NUR "(kein Grund)", und zwar wortlos. Damit war
        // "es ist noch kein Grund angelegt" von "die Gruende sind nicht
        // angekommen" nicht zu unterscheiden — eine stille Auslassung
        // (Grundregel 1) genau an der Stelle, an der die Bedienerin eine
        // Erklaerung braucht. Die Ursache des gemeldeten Befundes ist damit
        // NICHT behoben; sie wird sichtbar gemacht. Der Frontend-Pfad selbst
        // ist durch CP22 als in Ordnung nachgewiesen.
        var avGrund = _auswahl('aiw-capp-av-grund',
            [{ code: '', label: '(kein Grund)' }].concat(reasons),
            'code', 'label');
        avGrund.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.av_grund');
        var avGrundHinweis = null;
        if (avVorgabe.reason_code) { avGrund.value = avVorgabe.reason_code; }
        if (!reasons.length) {
            avGrundHinweis = _el('span', 'aiw-hint aiw-error',
                'Der Gruendekatalog ist LEER — es steht nur "(kein Grund)" '
                + 'zur Wahl. Sind unten unter "Abwesenheitsgruende" Eintraege '
                + 'sichtbar, ist das ein Fehler und kein leerer Katalog: '
                + 'bitte melden.');
            avGrundHinweis.setAttribute('data-hilfe-id',
                                        'capacity_pflege.bedienung.av_grund_leer');
        }
        // LEER IST KEINE 0. Die Vorbelegung uebernimmt einen Wert nur, wenn
        // er wirklich gesetzt ist - sonst stuende nach dem Bearbeiten in
        // BEIDEN Feldern eine 0, und der Server wiese die Zeile zurueck
        // ('genau eines von Prozent oder Minuten').
        var avPct = _feld('number', 'aiw-capp-av-pct', 'Prozent',
                          (avVorgabe.value_pct === null
                           || avVorgabe.value_pct === undefined)
                              ? '' : String(avVorgabe.value_pct));
        avPct.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.av_prozent');
        avPct.setAttribute('data-feld', 'value_pct');
        var avMin = _feld('number', 'aiw-capp-av-min', 'Minuten',
                          (avVorgabe.value_minutes === null
                           || avVorgabe.value_minutes === undefined)
                              ? '' : String(avVorgabe.value_minutes));
        avMin.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.av_minuten');
        avMin.setAttribute('data-feld', 'value_minutes');
        avMin.classList.add('aiw-minutenfeld');
        var avNotiz = _feld('text', 'aiw-capp-av-note', 'Notiz',
                            avVorgabe.note || '');
        avNotiz.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.av_notiz');
        [['Von', avVon], ['Bis', avBis], ['Rechenart', avArt],
         ['Grund', avGrund], ['Prozent', avPct], ['Minuten', avMin],
         ['Notiz', avNotiz]].forEach(function (paar) {
            formAv.appendChild(_el('label', 'aiw-label', paar[0]));
            formAv.appendChild(paar[1]);
        });
        if (avGrundHinweis) { formAv.appendChild(avGrundHinweis); }

        // BUILD 663 — Ticket d3f933cd. Die Kopplung sitzt HIER und nicht im
        // Baustein: nur diese Sicht weiss, dass ihre Rueckmeldungen in die
        // Ergebniszeile gehoeren, und nur sie weiss, dass ihr Paar eine
        // EINGABE ist (uebernehmen: true) und keine Filterspanne.
        // Der Baustein wird SPAET gesucht (nicht beim Laden der Datei):
        // fehlt er, bleibt die Maske vollstaendig bedienbar — der Ausfall
        // wird aber benannt und nicht verschwiegen (Grundregel 1).
        var dp = (typeof window !== 'undefined') ? window.AIWDatumspaar : null;
        if (dp && typeof dp.koppeln === 'function') {
            avKopplung = dp.koppeln(avVon, avBis, {
                uebernehmen: true,
                min: true,
                onUebernahme: function (datum) {
                    // Eine Wertaenderung, die niemand angefordert hat, muss
                    // sich erklaeren — sonst wirkt sie wie ein Fehler.
                    setResult('Bis-Datum auf ' + datum + ' vorbelegt (war '
                        + 'leer). Fuer einen laengeren Zeitraum einfach '
                        + 'ueberschreiben.', false);
                },
                onWarnung: function (text) { setResult(text, true); }
            });
        } else {
            formAv.appendChild(_el('p', 'aiw-hint',
                'Hinweis: die Datumskopplung (cockpit_datumspaar.js) ist nicht '
                + 'geladen. Von und Bis sind von Hand zu setzen.'));
        }
        formAv.appendChild(_el('p', 'aiw-hint',
            'Genau EINES von Prozent oder Minuten ausfuellen — beides zugleich '
            + 'weist der Server zurueck (Schema-Regel, kein Formularfehler).'));
        // BUILD 664 (Ticket 7b2f4a19): Bearbeitungsmodus. Er wird NUR durch
        // die Vorgabe getragen, nicht durch einen Zustand im Browser - so
        // ueberlebt er das Neuzeichnen nach einem Serverfehler.
        if (avErsetztId) {
            var avWarnung = _el('p', 'aiw-capp-ersetzt',
                'Bearbeitungsmodus: Speichern ERSETZT Eintrag #' + avErsetztId
                + '. Die alte Zeile wird stillgelegt und bleibt als Beleg '
                + 'erhalten.');
            formAv.appendChild(avWarnung);
            var bAvAb = _knopf('aiw-capp-av-abbrechen',
                'Bearbeitung abbrechen', function () {
                    if (typeof opts.onAvailabilityEditAbort === 'function') {
                        opts.onAvailabilityEditAbort();
                    }
                });
            bAvAb.setAttribute('data-hilfe-id',
                               'capacity_pflege.bedienung.av_abbrechen');
            formAv.appendChild(bAvAb);
        }

        // avNutzlast: EINE Stelle baut den Rumpf - Anlegen und Ersetzen
        // erwarten dieselben Felder. Zwei Bauplaetze liefen unweigerlich
        // auseinander, und der Unterschied faellt erst am Server auf.
        function avNutzlast() {
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
            body.value_pct = avPct.value === '' ? null : Number(avPct.value);
            body.value_minutes = avMin.value === '' ? null
                                                    : Number(avMin.value);
            return body;
        }

        var bAvSave = _knopf('aiw-capp-av-save',
            avErsetztId ? 'Zeile ersetzen' : 'Abwesenheit speichern',
            function () {
                var body = avNutzlast();
                if (avErsetztId) {
                    body.entry_id = avErsetztId;
                    if (typeof opts.onAvailabilityReplace === 'function') {
                        opts.onAvailabilityReplace(body);
                    }
                } else if (typeof opts.onAvailabilitySet === 'function') {
                    opts.onAvailabilitySet(body);
                }
            });
        bAvSave.setAttribute('data-hilfe-id',
                             'capacity_pflege.bedienung.av_speichern');
        formAv.appendChild(bAvSave);
        boxAv.appendChild(formAv);
        if (zeigeEntfernte) {
            spaltenAv.splice(spaltenAv.length - 1, 0,
                             { title: 'Stand', field: 'stand' });
        }
        bauen('capacity_availability', boxAv, availabilityRows(data),
              spaltenAv, 'Abwesenheiten', [], entferntZahlen.availability,
              histZahlen.availability);

        // ------------------------------------------------------ 3) Feiertage
        var boxHo = _abschnitt(mainEl, 'capacity_holiday.titel', 'Feiertage',
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
            hoTag.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.ho_tag');
            var hoLabel = _feld('text', 'aiw-capp-ho-label', 'Bezeichnung');
            hoLabel.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.ho_bezeichnung');
            var hoRegion = _feld('text', 'aiw-capp-ho-region',
                                 'Region (optional)');
            hoRegion.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.ho_region');
            [['Tag', hoTag], ['Bezeichnung', hoLabel],
             ['Region', hoRegion]].forEach(function (paar) {
                formHo.appendChild(_el('label', 'aiw-label', paar[0]));
                formHo.appendChild(paar[1]);
            });
            var bHoSave = _knopf('aiw-capp-ho-save', 'Feiertag anlegen',
                function () {
                    if (typeof opts.onHolidayAdd === 'function') {
                        opts.onHolidayAdd({
                            day: hoTag.value, label: hoLabel.value,
                            region: hoRegion.value || null
                        });
                    }
                });
            bHoSave.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.ho_anlegen');
            formHo.appendChild(bHoSave);
            boxHo.appendChild(formHo);
        }
        if (zeigeEntfernte) {
            spaltenHo.splice(spaltenHo.length - 1, 0,
                             { title: 'Stand', field: 'stand' });
        }
        bauen('capacity_holiday', boxHo, holidayRows(data), spaltenHo,
              'Feiertage', [], entferntZahlen.holidays,
              histZahlen.holidays);

        // ------------------------------------------------------- 4) Gruende
        var boxRe = _abschnitt(mainEl, 'capacity_reason.titel',
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
            reCode.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.re_code');
            var reLabel = _feld('text', 'aiw-capp-re-label', 'Bezeichnung');
            reLabel.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.re_bezeichnung');
            var reSort = _feld('number', 'aiw-capp-re-sort', 'Reihung', '0');
            reSort.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.re_reihung');
            [['Code', reCode], ['Bezeichnung', reLabel],
             ['Reihung', reSort]].forEach(function (paar) {
                formRe.appendChild(_el('label', 'aiw-label', paar[0]));
                formRe.appendChild(paar[1]);
            });
            var bReSave = _knopf('aiw-capp-re-save', 'Grund anlegen',
                function () {
                    if (typeof opts.onReasonAdd === 'function') {
                        opts.onReasonAdd({
                            code: reCode.value, label: reLabel.value,
                            sort: Number(reSort.value || 0)
                        });
                    }
                });
            bReSave.setAttribute('data-hilfe-id', 'capacity_pflege.bedienung.re_anlegen');
            formRe.appendChild(bReSave);
            boxRe.appendChild(formRe);
        }
        if (zeigeEntfernte) {
            spaltenRe.push({ title: 'Stand', field: 'stand' });
        }
        bauen('capacity_reason', boxRe, reasonRows(data), spaltenRe,
              'Abwesenheitsgruende', [], entferntZahlen.reasons);

        // ------------------------------------------------ Minutenrechner
        // ZIELVERFOLGUNG: der Rechner schreibt in das Feld, das zuletzt
        // angeklickt wurde. Er selbst kennt die Felder nicht (eigene Datei,
        // Grundregel 10) - die Sicht sagt ihm, wohin.
        var letztesZiel = null;
        Array.prototype.forEach.call(
            mainEl.querySelectorAll('.aiw-minutenfeld'),
            function (feld) {
                feld.addEventListener('focus', function () {
                    letztesZiel = feld;
                });
            });

        var Rechner = opts.Rechner
            || (typeof window !== 'undefined' ? window.AIWMinutenrechner
                                              : null);
        var rechnerAuf = null;
        var knopfRechner = _knopf('aiw-capp-rechner', 'Minutenrechner',
            function () {
                if (!Rechner || typeof Rechner.oeffnen !== 'function') {
                    // KEIN STILLER AUSFALL.
                    setResult('Der Minutenrechner ist nicht geladen '
                        + '(cockpit_minutenrechner.js).', true);
                    return;
                }
                if (rechnerAuf && rechnerAuf.istOffen()) {
                    rechnerAuf.aktualisieren();
                    return;
                }
                rechnerAuf = Rechner.oeffnen({
                    host: mainEl.ownerDocument.body,
                    zielGeben: function () {
                        if (!letztesZiel) { return null; }
                        return { id: letztesZiel.id,
                                 label: Rechner.zielName(letztesZiel.id) };
                    },
                    uebernehmen: function (minuten) {
                        if (!letztesZiel) { return; }
                        letztesZiel.value = String(minuten);
                    }
                });
            });
        knopfRechner.classList.add('aiw-btn-klein');
        knopfRechner.setAttribute('data-hilfe-id',
                                  'capacity_pflege.bedienung.rechner');
        h.appendChild(knopfRechner);

        log('gerendert: scope', scope, '/ Tabellen', tables.length,
            '/ Ersetzen-Modus', ersetztId);
        return { tables: tables, setResult: setResult,
                 rechnerSteuerung: function () { return rechnerAuf; },
                 datumspaarAbmelden: function () {
                     if (avKopplung) { avKopplung.abmelden(); avKopplung = null; }
                 },
                 markiereFeld: markiereFeld,
                 formularLesen: function () {
                     var z = wtNutzlast();
                     z._ersetzt_id = ersetztId;
                     // Build 664: der Abwesenheitsteil reist mit, sonst
                     // verlaesst eine begonnene Bearbeitung die Maske beim
                     // ersten Serverfehler.
                     var a = avNutzlast();
                     a._ersetzt_id = avErsetztId;
                     return { worktime: z, availability: a };
                 } };
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
        heuteIso: heuteIso,
        istEntfernt: istEntfernt,
        ausgeblendetText: ausgeblendetText,
        // Build 709 (Vorgang 75f84fee): der Text zum Zeitfilter - reine
        // Funktion, damit vitest ihn ohne DOM misst.
        historischText: historischText,
        VORGABEN: VORGABEN,
        uebernahmeText: uebernahmeText,
        renderCapacityPflege: renderCapacityPflege
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') {
        window.AIWCockpitCapacityPflege = API;
    }
})();
