// =============================================================================
// management/dashboard/frontend/dashboard.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Ampel-Dashboard (Frontend)
// =============================================================================
// Zweck:
//   Render-Schicht des Ampel-Dashboards (getrennte Admin-Oberflaeche fuer die
//   Chef-Ermittlerin). Nimmt die Fall-Uebersicht (CaseOverview-DTOs aus dem
//   Backend, Build 314/315) als JSON-Array entgegen und rendert daraus eine
//   nach Dringlichkeit sortierte Tabelle (rot > gelb > gruen).
//
// ARCHITEKTUR-UNABHAENGIG (bewusst): Diese Schicht liest die Daten aus
//   window.__AIW_DASHBOARD__ (inline eingebettet) ODER aus einem an render()
//   uebergebenen Array. Damit funktioniert sie unabhaengig davon, WIE die
//   echten Daten spaeter ausgeliefert werden (self-contained HTML-Export,
//   eigener Admin-Server o. Ae.) — diese Entscheidung ist separat und beruehrt
//   diese Datei nicht.
//
// KAPSELUNG / KONVENTIONEN (Projekt-Gebote fuer JS):
//   1) IIFE-Wrapper mit 'use strict'.
//   2) Exzessives DEV-Debug-Logging, per Flag abschaltbar (fuer PROD).
//   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
//   4) Klassen/Logik gekapselt.
//   Zusaetzlich: Die REINEN Funktionen (Sortierung/Klassen/Labels) werden am
//   Ende ueber einen UMD-artigen Ausgang exportiert, damit die Vitest-Tests den
//   ECHTEN Code pruefen (kein dupliziertes Logik-Abbild -> vermeidet die
//   'gruen-aber-tot'-Falle). Reine Funktionen fassen NIE das DOM an; nur
//   render() beruehrt document (und wird nur im Browser/jsdom aufgerufen).
//
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Version: v0.7.469 · Build: 469 · 2026-07-20
// =============================================================================

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // DEV-Debug-Logging. Aktivierung im Browser vor dem Laden:
    //   window.AIW_DASHBOARD_DEBUG = true;
    // Fuer PROD bleibt es aus (kein Output). Node/Vitest: standardmaessig aus.
    // -------------------------------------------------------------------------
    var DEBUG = (typeof window !== 'undefined' && window.AIW_DASHBOARD_DEBUG === true);
    function log() {
        if (!DEBUG) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Dashboard]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // -------------------------------------------------------------------------
    // Ampel-Vokabular (konsistent zum Backend: dashboard_repo.AMPEL_*).
    // Rang steuert die Sortierung: rot am dringlichsten (0) ... gruen (2).
    // -------------------------------------------------------------------------
    var AMPEL_RANK = { rot: 0, gelb: 1, gruen: 2 };

    // Menschlich lesbare Kurzbezeichnung der ampel_reason-Codes (Backend).
    var REASON_LABEL = {
        abgeschlossen: 'abgeschlossen',
        freigegeben: 'freigegeben',
        offen_nicht_zugewiesen: 'offen, nicht zugewiesen',
        inaktiv_lang: 'lange inaktiv',
        inaktiv_mittel: 'mittlere Inaktivitaet',
        aktiv: 'aktiv'
    };

    // -------------------------------------------------------------------------
    // REINE FUNKTION: CSS-Klasse zur Ampel. Kapselt das Mapping an einer Stelle.
    // -------------------------------------------------------------------------
    function ampelClass(ampel) {
        // Unbekannte Werte defensiv als 'gruen' behandeln waere falsch (koennte
        // Dringlichkeit verschleiern); daher eigene 'unknown'-Klasse.
        if (ampel === 'rot' || ampel === 'gelb' || ampel === 'gruen') {
            return 'aiw-ampel-' + ampel;
        }
        return 'aiw-ampel-unknown';
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Sortierung fuer die Anzeige. Spiegelt die Backend-Regel
    // (Build 315): Ampel-Schwere zuerst, dann Prioritaet aufsteigend, dann
    // letzte Aktivitaet absteigend, dann subject_id. BEWUSST defensiv im Frontend
    // dupliziert, damit die Ansicht auch bei unsortierter Eingabe korrekt ist.
    // Gibt eine NEUE Liste zurueck (keine Mutation der Eingabe).
    // -------------------------------------------------------------------------
    function sortForDisplay(cases) {
        var copy = (cases || []).slice();
        copy.sort(function (a, b) {
            var ra = (a.ampel in AMPEL_RANK) ? AMPEL_RANK[a.ampel] : 99;
            var rb = (b.ampel in AMPEL_RANK) ? AMPEL_RANK[b.ampel] : 99;
            if (ra !== rb) { return ra - rb; }                 // rot < gelb < gruen
            if (a.priority !== b.priority) { return a.priority - b.priority; }  // 1 zuerst
            var la = a.last_activity_at || 0, lb = b.last_activity_at || 0;
            if (la !== lb) { return lb - la; }                 // juengste Aktivitaet zuerst
            return (a.subject_id || 0) - (b.subject_id || 0);
        });
        return copy;
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Support-Abzeichen-Text. Support-Praesenz ist bewusst ein
    // EIGENES Abzeichen (nicht Teil der Ampelfarbe) — konsistent zum Backend.
    // -------------------------------------------------------------------------
    function supportLabel(caseObj) {
        if (caseObj.support_active) {
            return 'Support aktiv (' + (caseObj.support_count || 0) + ')';
        }
        return '';
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Zuweisungs-Anzeige (Anzeigename bevorzugt, sonst
    // System-Benutzername, sonst Gedankenstrich).
    // -------------------------------------------------------------------------
    function assigneeLabel(caseObj) {
        return caseObj.assigned_display_name
            || caseObj.assigned_system_username
            || '\u2014'; // em-dash
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Tage seit einem Unix-Zeitstempel (fuer 'letzte Aktivitaet').
    // nowSec ist injizierbar (Testbarkeit/Determinismus).
    // -------------------------------------------------------------------------
    function daysSince(tsSec, nowSec) {
        if (!tsSec) { return null; }
        var now = (typeof nowSec === 'number') ? nowSec : Math.floor(Date.now() / 1000);
        return Math.floor((now - tsSec) / 86400);
    }

    function reasonLabel(reason) {
        return REASON_LABEL[reason] || reason || '';
    }

    // -------------------------------------------------------------------------
    // DOM-RENDER (nur Browser/jsdom). Baut die Tabelle in ein Zielelement.
    // Trennt strikt Daten -> Zellen; nutzt textContent (kein innerHTML) gegen
    // Injektion aus Forumsdaten (Benutzernamen sind beliebiger UTF-8-Text!).
    // -------------------------------------------------------------------------
    var COLUMNS = ['Ampel', 'Prio', 'subject_id', 'Benutzer', 'Status',
        'Zuweisung', 'Letzte Aktivitaet', 'Ereignis', 'Support', 'Ereign.', 'Notiz', 'Grund'];

    function cell(row, text, className) {
        var td = document.createElement('td');
        td.textContent = (text === null || text === undefined) ? '' : String(text);
        if (className) { td.className = className; }
        row.appendChild(td);
        return td;
    }

    function renderInto(container, cases, opts) {
        opts = opts || {};
        var nowSec = opts.nowSec;
        log('renderInto: erhalte', (cases || []).length, 'Faelle');

        var ordered = sortForDisplay(cases);
        log('renderInto: sortiert ->', ordered.map(function (c) {
            return c.subject_id + ':' + c.ampel;
        }));

        // Vorhandenen Inhalt leeren (idempotentes Re-Rendern).
        while (container.firstChild) { container.removeChild(container.firstChild); }

        var table = document.createElement('table');
        table.className = 'aiw-dashboard-table';

        var thead = document.createElement('thead');
        var htr = document.createElement('tr');
        COLUMNS.forEach(function (name) {
            var th = document.createElement('th');
            th.textContent = name;
            htr.appendChild(th);
        });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = document.createElement('tbody');
        ordered.forEach(function (c) {
            var tr = document.createElement('tr');
            tr.className = ampelClass(c.ampel);
            tr.setAttribute('data-subject-id', String(c.subject_id));

            // Ampel-Punkt (visuell) via eigener Zelle mit Klasse.
            var ampelTd = cell(tr, '', 'aiw-ampel-dot ' + ampelClass(c.ampel));
            ampelTd.setAttribute('title', c.ampel || '');

            cell(tr, c.priority, 'aiw-prio');
            cell(tr, c.subject_id);
            cell(tr, c.username, 'aiw-username');
            cell(tr, c.status);
            cell(tr, assigneeLabel(c));
            var d = daysSince(c.last_activity_at, nowSec);
            cell(tr, d === null ? '\u2014' : (d + ' Tg'));
            cell(tr, c.last_event_kind || '\u2014');
            var sup = supportLabel(c);
            cell(tr, sup, sup ? 'aiw-support-active' : '');
            cell(tr, c.event_count);
            cell(tr, c.has_note ? 'Notiz' : '', c.has_note ? 'aiw-has-note' : '');
            cell(tr, reasonLabel(c.ampel_reason), 'aiw-reason');

            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        container.appendChild(table);

        log('renderInto: fertig,', ordered.length, 'Zeilen gerendert');
        return { rows: ordered.length };
    }

    // -------------------------------------------------------------------------
    // Bootstrap im Browser: rendert automatisch aus window.__AIW_DASHBOARD__
    // in das Element #aiw-dashboard-root, sobald das DOM bereit ist.
    // In Node/Vitest (kein document) passiert hier nichts.
    // -------------------------------------------------------------------------
    function boot() {
        if (typeof document === 'undefined') { return; }
        var root = document.getElementById('aiw-dashboard-root');
        if (!root) { log('boot: kein #aiw-dashboard-root gefunden'); return; }
        var data = (typeof window !== 'undefined' && window.__AIW_DASHBOARD__) || [];
        log('boot: starte Render mit', data.length, 'Faellen');
        renderInto(root, data);
    }

    if (typeof document !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', boot);
        } else {
            boot();
        }
    }

    // -------------------------------------------------------------------------
    // UMD-artiger Ausgang: dieselbe API an window (Browser) UND module.exports
    // (Node/Vitest). So testen die Unit-Tests den ECHTEN Code.
    // -------------------------------------------------------------------------
    var API = {
        AMPEL_RANK: AMPEL_RANK,
        ampelClass: ampelClass,
        sortForDisplay: sortForDisplay,
        supportLabel: supportLabel,
        assigneeLabel: assigneeLabel,
        daysSince: daysSince,
        reasonLabel: reasonLabel,
        renderInto: renderInto,
        boot: boot
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWDashboard = API; }
})();
