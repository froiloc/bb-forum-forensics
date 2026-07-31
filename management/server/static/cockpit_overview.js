// =============================================================================
// management/server/static/cockpit_overview.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Overview-Sicht
// =============================================================================
// Zweck:
//   Rendert die Fall-Uebersicht (/api/overview) als Tabulator-v6-Tabelle. Die
//   Sicht ist die Cockpit-Entsprechung des Ampel-Dashboards, aber mit client-
//   seitiger Sortierung/Filterung ueber Tabulator (Beleg: Bauplan B7 v1.1
//   §11.2 "Tabellen mit Tabulator.js").
//
// KONVENTIONS-VERTRAG (Quelle der Wahrheit = Backend):
//   Ampel-Vokabular (rot/gelb/gruen), ampel_reason-Codes und die Anzeige-
//   Sortierung (Ampel-Schwere -> Prioritaet aufsteigend -> letzte Aktivitaet
//   absteigend -> subject_id) spiegeln dashboard_repo.AMPEL_* (Build 315) und
//   dashboard.js. Bewusst hier eigenstaendig + eigenstaendig getestet gehalten
//   (Split-Build 348, keine Kopplung an die getrennte Dashboard-Auslieferung);
//   der gemeinsame Vertrag ist das Backend-Vokabular, nicht diese Datei.
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE-Wrapper mit 'use strict'.
//   2) DEV-Debug-Logging, per Flag abschaltbar (PROD: aus).
//   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
//   4) Logik gekapselt; REINE Funktionen fassen NIE das DOM an.
//   UMD-artiger Ausgang -> vitest testet den ECHTEN Code (keine Dublette).
//
// SICHERHEIT (XSS): Fallwerte (username/status/...) stammen aus Forumsdaten und
//   sind potenziell fremdbestimmt. Textspalten nutzen daher Tabulators
//   'plaintext'-Formatter (textContent). Eigene Formatter bauen DOM-Knoten und
//   setzen variablen Text ausschliesslich via textContent (nie innerHTML).
//
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Version: v0.7.469 · Build: 469 · 2026-07-20
// =============================================================================

(function () {
    'use strict';

    // Build 349: DEBUG zur Laufzeit auslesen (kein Reload noetig).
    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Overview]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    var EM_DASH = '\u2014';

    // =========================================================================
    // 1) REINE FUNKTIONEN (kein DOM). vitest-getestet.
    // =========================================================================

    // Ampel-Rang: Schwere zuerst (rot 0 < gelb 1 < gruen 2). Unbekannt -> 99
    // (ans Ende), damit fehlerhafte Werte nie still verschwinden (Grundregel 1).
    var AMPEL_RANK = { rot: 0, gelb: 1, gruen: 2 };
    function ampelRank(ampel) {
        return Object.prototype.hasOwnProperty.call(AMPEL_RANK, ampel)
            ? AMPEL_RANK[ampel] : 99;
    }

    // ampel_reason-Code -> menschliches Label (Spiegel dashboard.js/Backend).
    var REASON_LABEL = {
        abgeschlossen: 'abgeschlossen',
        freigegeben: 'freigegeben',
        offen_nicht_zugewiesen: 'offen, nicht zugewiesen',
        inaktiv_lang: 'lange inaktiv',
        inaktiv_mittel: 'mittlere Inaktivitaet',
        aktiv: 'aktiv'
    };
    function reasonLabel(code) {
        return REASON_LABEL[code] || code || '';
    }

    // Zuweisung: Anzeigename bevorzugt, sonst system_username, sonst Gedankenstrich.
    function assigneeLabel(c) {
        return c.assigned_display_name
            || c.assigned_system_username
            || EM_DASH;
    }

    // Support-Abzeichen-Text (Praesenz, kein Fall-Zustand).
    function supportLabel(c) {
        return c.support_active
            ? ('Support aktiv (' + (c.support_count || 0) + ')')
            : '';
    }

    // Tage seit Unix-Zeitstempel (nowSec injizierbar); null bei fehlend/0.
    function daysSince(tsSec, nowSec) {
        if (!tsSec) { return null; }
        var now = (typeof nowSec === 'number')
            ? nowSec : Math.floor(Date.now() / 1000);
        return Math.floor((now - tsSec) / 86400);
    }

    // toRows: DTO-Faelle -> Tabulator-Zeilen. Ergaenzt abgeleitete Felder
    // (_rank/_reason/_assignee/_sinceDays/_support), laesst die Rohwerte drin.
    // Reine Abbildung; mutiert die Eingabe nicht.
    function toRows(cases, nowSec) {
        return (cases || []).map(function (c) {
            return {
                subject_id: c.subject_id,
                username: c.username,
                status: c.status,
                priority: c.priority,
                ampel: c.ampel,
                has_note: !!c.has_note,
                event_count: c.event_count,
                last_activity_at: c.last_activity_at,
                // abgeleitet:
                _rank: ampelRank(c.ampel),
                _reason: reasonLabel(c.ampel_reason),
                _assignee: assigneeLabel(c),
                _sinceDays: daysSince(c.last_activity_at, nowSec),
                _support: supportLabel(c)
            };
        });
    }

    // sortRows: Standard-Anzeigeordnung (Ampel-Schwere -> Prioritaet aufsteigend
    // -> letzte Aktivitaet absteigend -> subject_id). Gibt eine sortierte KOPIE
    // zurueck (mutiert die Eingabe nicht). Tabulator laesst spaeter Umsortieren zu.
    function sortRows(rows) {
        var copy = (rows || []).slice();
        copy.sort(function (a, b) {
            if (a._rank !== b._rank) { return a._rank - b._rank; }
            if (a.priority !== b.priority) { return a.priority - b.priority; }
            var la = a.last_activity_at || 0, lb = b.last_activity_at || 0;
            if (la !== lb) { return lb - la; }
            return (a.subject_id || 0) - (b.subject_id || 0);
        });
        return copy;
    }

    // columnDefs: Tabulator-Spaltenspezifikation (deterministisch/rein). Die
    // Formatter bauen DOM-Knoten (XSS-sicher); Textspalten nutzen 'plaintext'.
    function columnDefs() {
        return [
            {
                title: 'Ampel', field: '_rank', sorter: 'number', width: 190,
                // Farbpunkt + Grund; Grund stammt aus der Whitelist (safe).
                formatter: function (cell) {
                    var data = cell.getRow().getData();
                    var wrap = document.createElement('span');
                    var dot = document.createElement('span');
                    dot.className = 'dot ' + (data.ampel || '');
                    wrap.appendChild(dot);
                    var txt = document.createElement('span');
                    txt.textContent = ' ' + (data._reason || '');
                    wrap.appendChild(txt);
                    return wrap;
                }
            },
            { title: 'Prio', field: 'priority', sorter: 'number', hozAlign: 'right', width: 70 },
            { title: 'Subject-ID', field: 'subject_id', sorter: 'number', hozAlign: 'right', width: 90 },
            { title: 'Benutzer', field: 'username', formatter: 'plaintext' },
            { title: 'Status', field: 'status', formatter: 'plaintext', width: 110 },
            { title: 'Zugewiesen', field: '_assignee', formatter: 'plaintext' },
            {
                title: 'Letzte Aktivitaet', field: '_sinceDays', sorter: 'number',
                hozAlign: 'right', width: 140,
                formatter: function (cell) {
                    var v = cell.getValue();
                    var span = document.createElement('span');
                    span.textContent = (v === null || v === undefined)
                        ? EM_DASH : (v + ' Tg');
                    return span;
                }
            },
            { title: 'Ereignisse', field: 'event_count', sorter: 'number', hozAlign: 'right', width: 100 },
            {
                title: 'Notiz', field: 'has_note', width: 80,
                formatter: function (cell) {
                    var span = document.createElement('span');
                    span.textContent = cell.getValue() ? 'Notiz' : '';
                    return span;
                }
            },
            { title: 'Support', field: '_support', formatter: 'plaintext', width: 150 }
        ];
    }

    // scopeText: Umfang-Banner ('alle'/'eigene') als Klartext.
    function scopeText(scope) {
        if (scope === 'eigene') {
            return 'Umfang: nur eigene Zuweisungen (fremde Faelle gekapselt).';
        }
        if (scope === 'alle') {
            return 'Umfang: alle Faelle (Gesamtsicht).';
        }
        return 'Umfang: eingeschraenkt.';
    }

    // =========================================================================
    // 2) DOM/RENDER (nur Browser/jsdom).
    // =========================================================================

    // _tk / _mitHilfe (Build 549): Zugriff auf das gemeinsame Tabellen-Werkzeug
    // und die HILFE-ANKER der Spaltenkoepfe. LAZY, damit die Ladereihenfolge
    // diese Sicht nicht lautlos brechen kann.
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

    // renderOverview: baut Kopf + Tabulator-Tabelle in mainEl. data = Antwort
    // von /api/overview ({scope, count, cases}). opts.Tabulator injizierbar
    // (Default window.Tabulator); opts.nowSec fuer daysSince (Testbarkeit).
    // Rueckgabe: Tabulator-Instanz (oder null, wenn Tabulator fehlt) — der
    // Aufrufer zerstoert sie beim Sichtwechsel/Reload.
    function renderOverview(mainEl, data, opts) {
        opts = opts || {};
        if (!mainEl) { return null; }
        mainEl.textContent = '';

        var scope = data ? data.scope : null;
        var cases = (data && data.cases) || [];

        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        // Build 575: Titel gleich der Sicht-Beschriftung im VIEW_CATALOG
        // ('Fallübersicht'). Vorher stand hier 'Fall-Uebersicht' - dieselbe
        // Sache in zwei Schreibweisen, und die Navigation nannte sie anders
        // als die Seite selbst.
        h.textContent = 'Fallübersicht';
        // Build 592 (Baustelle H / H5): LITERALE Hilfe-Marken fuer Kopf und
        // Umfangszeile. Literal und nicht berechnet - genau darauf beruht der
        // Paritaetstest, der Marke und Registertext gegeneinander haelt
        // (Konzept §4.2a). Die Spaltenkoepfe bekommen ihre Anker weiterhin
        // vom gemeinsamen Tabellen-Werkzeug (Build 548).
        h.setAttribute('data-hilfe-id', 'faelle.titel');
        mainEl.appendChild(h);

        var sub = document.createElement('p');
        sub.className = 'aiw-pagesub';
        sub.textContent = scopeText(scope) + ' (' + cases.length + ' Faelle)';
        sub.setAttribute('data-hilfe-id', 'faelle.umfang');
        mainEl.appendChild(sub);

        // Build 549 (UX): Aufbau ueber das gemeinsame Tabellen-Werkzeug.
        //
        // 'index: subject_id' WIRD DURCHGEREICHT und ist hier nicht optional:
        // daran haengt focusCase(table, subject_id) und damit der Fallsprung
        // der Kommandopalette (Build 459). Ohne den Index fuehrte Strg-K zwar
        // weiterhin zur Uebersicht, koennte dort aber nichts mehr
        // hervorheben — ein stiller Ausfall.
        var doc = (typeof document !== 'undefined') ? document : null;
        var TK = _tk();
        var rows = sortRows(toRows(cases, opts.nowSec));
        var Ctor = opts.Tabulator
            || (typeof window !== 'undefined' ? window.Tabulator : undefined);

        if (!TK || !doc) {
            var note = (doc || document).createElement('div');
            note.className = 'aiw-placeholder';
            note.textContent = 'Gemeinsames Tabellen-Werkzeug nicht geladen — '
                + 'es liegen ' + rows.length + ' Fälle im Umfang.';
            mainEl.appendChild(note);
            log('renderOverview: kein TableKit');
            return null;
        }

        log('renderOverview:', rows.length, 'Zeilen, scope', scope);
        var auf = TK.tabelleAufbauen(doc, mainEl, {
            sicht: 'overview',
            rows: rows,
            columns: _mitHilfe(columnDefs(), 'overview', doc),
            Ctor: Ctor,
            einheit: 'Fälle',
            tabulator: {
                index: 'subject_id',
                height: '65vh',
                placeholder: 'Keine Faelle im Umfang.',
                rowFormatter: function (row) {
                    // Ampel-Zeilenklasse (dezent, konsistent zum Dashboard).
                    var d = row.getData();
                    row.getElement().classList.add(
                        'aiw-row-' + (d.ampel || 'none'));
                }
            }
        });
        return auf.table;
    }

    // =========================================================================
    // focusCase: springt in der Tabelle zu einem Fall (subject_id) und hebt die
    // Zeile kurz hervor. Fuer den Kommandopalette-Fallsprung (Build 459).
    // Voll abgesichert: fehlt die Zeile/Tabelle -> false (kein Absturz, GR1).
    // Die Hervorhebung erfolgt per Inline-Style (kein cockpit.css-Eingriff).
    function focusCase(table, subjectId) {
        if (!table || subjectId === null || subjectId === undefined
            || typeof table.getRow !== 'function') {
            return false;
        }
        try {
            if (typeof table.scrollToRow === 'function') {
                // Tabulator v6: (index, position, ifVisible). Kann ein Promise
                // liefern -> wir ignorieren den Rueckgabewert bewusst.
                try { table.scrollToRow(subjectId, 'center', false); }
                catch (e) { log('scrollToRow', e); }
            }
            var row = table.getRow(subjectId);
            if (row && typeof row.getElement === 'function') {
                var el = row.getElement();
                if (el) {
                    el.style.transition = 'background-color .3s';
                    var prev = el.style.backgroundColor;
                    el.style.backgroundColor = '#fff3b0';
                    setTimeout(function () {
                        el.style.backgroundColor = prev || '';
                    }, 2200);
                }
                return true;
            }
        } catch (e) {
            log('focusCase', e);
        }
        return false;
    }

    // 3) UMD-Ausgang.
    // =========================================================================
    var API = {
        AMPEL_RANK: AMPEL_RANK,
        ampelRank: ampelRank,
        reasonLabel: reasonLabel,
        assigneeLabel: assigneeLabel,
        supportLabel: supportLabel,
        daysSince: daysSince,
        toRows: toRows,
        sortRows: sortRows,
        columnDefs: columnDefs,
        scopeText: scopeText,
        renderOverview: renderOverview,
        focusCase: focusCase
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpitOverview = API; }
})();
