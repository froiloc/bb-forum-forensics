// =============================================================================
// management/support_overview/frontend/support_overview.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Support-Historie (Frontend)
// =============================================================================
// Zweck:
//   Render-Schicht der Support-Sitzungs-Historie (getrennte Admin-Oberflaeche
//   fuer die Chef-Ermittlerin). Nimmt die aus dem audit_log rekonstruierten
//   SupportSessionRecord-DTOs (Backend, Build 330) als JSON-Array entgegen und
//   rendert daraus eine FLACHE, chronologische, sortier- und filterbare Tabelle
//   (mc 2026-07-07: flache chronologische Sitzungsliste).
//
// ARCHITEKTUR-UNABHAENGIG (bewusst): Diese Schicht liest die Daten aus
//   window.__AIW_SUPPORT_OVERVIEW__ (inline eingebettet) ODER aus einem an
//   renderInto() uebergebenen Array. Damit funktioniert sie unabhaengig von der
//   Auslieferung (self-contained HTML-Export).
//
// KAPSELUNG / KONVENTIONEN (Projekt-Gebote fuer JS):
//   1) IIFE-Wrapper mit 'use strict'.
//   2) Exzessives DEV-Debug-Logging, per Flag abschaltbar (fuer PROD).
//   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
//   4) Klassen/Logik gekapselt.
//   Zusaetzlich: Die REINEN Funktionen (Status/Labels/Dauer/Sortierung/Filter)
//   werden am Ende ueber einen UMD-artigen Ausgang exportiert, damit die Vitest-
//   Tests den ECHTEN Code pruefen (kein dupliziertes Logik-Abbild -> vermeidet
//   die 'gruen-aber-tot'-Falle). Reine Funktionen fassen NIE das DOM an; nur
//   renderInto()/boot() beruehren document.
//
// SICHERHEIT: Alle Zellinhalte via textContent (kein innerHTML). Benutzernamen
//   sind beliebiger UTF-8-Text aus dem beschlagnahmten Forum — nie als HTML
//   interpretieren.
//
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Version: v0.7.469 · Build: 469 · 2026-07-20
// =============================================================================

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // DEV-Debug-Logging. Aktivierung im Browser vor dem Laden:
    //   window.AIW_SUPPORT_OVERVIEW_DEBUG = true;
    // Fuer PROD bleibt es aus (kein Output). Node/Vitest: standardmaessig aus.
    // -------------------------------------------------------------------------
    var DEBUG = (typeof window !== 'undefined'
        && window.AIW_SUPPORT_OVERVIEW_DEBUG === true);
    function log() {
        if (!DEBUG) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-SupportHist]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // -------------------------------------------------------------------------
    // Status-Vokabular (konsistent zum Backend: support_session_record.STATUS_*).
    // Farbklasse: beendet=gruen, orphan_timeout=gelb, offen=blau, herrenlos=rot.
    // -------------------------------------------------------------------------
    var STATUS_LABEL = {
        beendet: 'beendet',
        orphan_timeout: 'Zeitueberschreitung',
        offen: 'offen',
        herrenlos: 'herrenlos'
    };
    var STATUS_COLORCLASS = {
        beendet: 'aiw-status-beendet',
        orphan_timeout: 'aiw-status-orphan',
        offen: 'aiw-status-offen',
        herrenlos: 'aiw-status-herrenlos'
    };

    // Menschlich lesbare Kurztexte der Anomalie-Codes (Backend).
    var ANOMALY_LABEL = {
        doppeltes_started: 'doppeltes STARTED',
        doppeltes_ended: 'doppeltes ENDED',
        fehlende_session_id_im_payload: 'fehlende session_id'
    };

    // -------------------------------------------------------------------------
    // REINE FUNKTION: CSS-Klasse zum Status. Unbekannte Werte defensiv als
    // 'unknown' (nie stillschweigend als 'beendet' faerben -> koennte einen
    // offenen/auffaelligen Zustand verschleiern).
    // -------------------------------------------------------------------------
    function statusClass(status) {
        return STATUS_COLORCLASS[status] || 'aiw-status-unknown';
    }

    function statusLabel(status) {
        return STATUS_LABEL[status] || status || '';
    }

    function anomalyLabel(code) {
        if (!code) { return ''; }
        return ANOMALY_LABEL[code] || code;
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Supporter-Anzeige. Anzeigename bevorzugt, sonst System-
    // Benutzername, sonst (id N), sonst 'unbekannt' (z. B. bei 'herrenlos', wo
    // der ENDED-Beleg keinen Supporter traegt).
    // -------------------------------------------------------------------------
    function supporterLabel(rec) {
        if (rec.supporter_display_name) { return rec.supporter_display_name; }
        if (rec.supporter_system_username) { return rec.supporter_system_username; }
        if (rec.supporter_id !== null && rec.supporter_id !== undefined) {
            return '(id ' + rec.supporter_id + ')';
        }
        return 'unbekannt';
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Fall-Benutzername. cases.username, sonst deutlicher
    // Hinweis (Grundregel 1: die Zeile bleibt sichtbar, der Mangel benannt).
    // -------------------------------------------------------------------------
    function caseUserLabel(rec) {
        if (rec.username !== null && rec.username !== undefined
            && rec.username !== '') {
            return rec.username;
        }
        return '(kein cases-Eintrag)';
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Dauer menschlich (aus dem GESCHRIEBENEN duration_sec, nie
    // errechnet). null/undefined -> Gedankenstrich (offene/herrenlose Sitzung).
    // Format: 'Hh MMm SSs' bzw. 'MMm SSs' bzw. 'SSs'.
    // -------------------------------------------------------------------------
    function formatDuration(sec) {
        if (sec === null || sec === undefined) { return '\u2014'; }
        var s = Math.max(0, Math.floor(sec));
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        var ss = s % 60;
        function pad(n) { return (n < 10 ? '0' : '') + n; }
        if (h > 0) { return h + 'h ' + pad(m) + 'm ' + pad(ss) + 's'; }
        if (m > 0) { return m + 'm ' + pad(ss) + 's'; }
        return ss + 's';
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Unix-Sekunden -> 'YYYY-MM-DD HH:MMZ' (UTC, deterministisch;
    // Serverlogs sind Lokalzeit, die Historie fuehrt bewusst UTC). null -> '—'.
    // -------------------------------------------------------------------------
    function formatTs(sec) {
        if (sec === null || sec === undefined) { return '\u2014'; }
        var d = new Date(sec * 1000);
        function pad(n) { return (n < 10 ? '0' : '') + n; }
        return d.getUTCFullYear() + '-' + pad(d.getUTCMonth() + 1) + '-'
            + pad(d.getUTCDate()) + ' ' + pad(d.getUTCHours()) + ':'
            + pad(d.getUTCMinutes()) + 'Z';
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Anker-Zeitstempel (spiegelt die Backend-Ordnungsregel):
    // started_at, sonst started_ts, sonst ended_at, sonst ended_ts, sonst 0.
    // -------------------------------------------------------------------------
    function anchorTs(rec) {
        var candidates = [rec.started_at, rec.started_ts,
            rec.ended_at, rec.ended_ts];
        for (var i = 0; i < candidates.length; i++) {
            if (candidates[i] !== null && candidates[i] !== undefined) {
                return candidates[i];
            }
        }
        return 0;
    }

    // -------------------------------------------------------------------------
    // Sortierschluessel-Extraktoren je Spalte. Jeder liefert einen vergleichbaren
    // Primitivwert; die eigentliche Sortierung ist stabilisiert (Tiebreak
    // session_id), damit gleiche Werte reproduzierbar geordnet bleiben.
    // -------------------------------------------------------------------------
    var SORT_KEYS = {
        anchor: function (r) { return anchorTs(r); },
        session: function (r) { return r.session_id || 0; },
        user: function (r) { return r.subject_id || 0; },
        username: function (r) { return (caseUserLabel(r) || '').toLowerCase(); },
        supporter: function (r) { return (supporterLabel(r) || '').toLowerCase(); },
        start: function (r) { return (r.started_at === null
            || r.started_at === undefined) ? -1 : r.started_at; },
        ende: function (r) { return (r.ended_at === null
            || r.ended_at === undefined) ? -1 : r.ended_at; },
        dauer: function (r) { return (r.duration_sec === null
            || r.duration_sec === undefined) ? -1 : r.duration_sec; },
        status: function (r) { return statusLabel(r.status).toLowerCase(); }
    };

    // -------------------------------------------------------------------------
    // REINE FUNKTION: sortiert eine Kopie der Records. key aus SORT_KEYS
    // (default 'anchor'), dir 'asc'|'desc' (default 'asc'). Tiebreak: session_id
    // aufsteigend. Mutiert die Eingabe NICHT.
    // -------------------------------------------------------------------------
    function sortRecords(records, key, dir) {
        var extractor = SORT_KEYS[key] || SORT_KEYS.anchor;
        var sign = (dir === 'desc') ? -1 : 1;
        var copy = (records || []).slice();
        copy.sort(function (a, b) {
            var ka = extractor(a), kb = extractor(b);
            if (ka < kb) { return -1 * sign; }
            if (ka > kb) { return 1 * sign; }
            // Stabiler, richtungsunabhaengiger Tiebreak: session_id aufsteigend.
            return (a.session_id || 0) - (b.session_id || 0);
        });
        return copy;
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Volltextfilter (Teilstring, case-insensitiv) ueber die
    // sichtbaren Kernfelder. Leerer Filter -> alle. Mutiert nichts.
    // -------------------------------------------------------------------------
    function filterRecords(records, query) {
        var q = (query || '').trim().toLowerCase();
        if (!q) { return (records || []).slice(); }
        return (records || []).filter(function (r) {
            var hay = [
                supporterLabel(r),
                caseUserLabel(r),
                String(r.subject_id),
                String(r.session_id),
                statusLabel(r.status),
                (r.reason || ''),
                anomalyLabel(r.anomaly)
            ].join(' \u0001 ').toLowerCase();
            return hay.indexOf(q) !== -1;
        });
    }

    // -------------------------------------------------------------------------
    // REINE FUNKTION: Beleg-Verweis (audit_log-seq) kompakt: 'S123 / E124',
    // fehlende Seite als '—'. Macht die Nachpruefbarkeit sichtbar.
    // -------------------------------------------------------------------------
    function belegLabel(rec) {
        var s = (rec.started_seq === null || rec.started_seq === undefined)
            ? '\u2014' : ('S' + rec.started_seq);
        var e = (rec.ended_seq === null || rec.ended_seq === undefined)
            ? '\u2014' : ('E' + rec.ended_seq);
        return s + ' / ' + e;
    }

    // -------------------------------------------------------------------------
    // Spaltenmodell: Anzeigename + Sortierschluessel (null = nicht sortierbar).
    // -------------------------------------------------------------------------
    var COLUMNS = [
        { name: 'Status', key: 'status' },
        { name: 'Sitzung', key: 'session' },
        { name: 'Fall (subject_id)', key: 'user' },
        { name: 'Benutzer', key: 'username' },
        { name: 'Supporter', key: 'supporter' },
        { name: 'Start (UTC)', key: 'start' },
        { name: 'Ende (UTC)', key: 'ende' },
        { name: 'Dauer', key: 'dauer' },
        { name: 'Grund', key: null },
        { name: 'Beleg (seq)', key: null },
        { name: 'Anomalie', key: null }
    ];

    function cell(row, text, className) {
        var td = document.createElement('td');
        td.textContent = (text === null || text === undefined) ? '' : String(text);
        if (className) { td.className = className; }
        row.appendChild(td);
        return td;
    }

    // -------------------------------------------------------------------------
    // DOM-RENDER (nur Browser/jsdom). Baut die Tabelle aus BEREITS sortierten/
    // gefilterten Records in ein Zielelement. opts.onSort(key) verdrahtet die
    // Kopfzeilen-Klicks (optional; im reinen Render-Test nicht noetig).
    // opts.sortKey/opts.sortDir markieren die aktive Sortierspalte visuell.
    // -------------------------------------------------------------------------
    function renderInto(container, records, opts) {
        opts = opts || {};
        var rows = records || [];
        log('renderInto: rendere', rows.length, 'Sitzungen');

        while (container.firstChild) { container.removeChild(container.firstChild); }

        var table = document.createElement('table');
        table.className = 'aiw-support-table';

        var thead = document.createElement('thead');
        var htr = document.createElement('tr');
        COLUMNS.forEach(function (col) {
            var th = document.createElement('th');
            th.textContent = col.name;
            if (col.key) {
                th.className = 'aiw-sortable';
                th.setAttribute('data-sort-key', col.key);
                if (opts.sortKey === col.key) {
                    th.className += ' aiw-sort-active';
                    // Pfeil zeigt die Richtung an (rein visuell).
                    th.textContent = col.name
                        + (opts.sortDir === 'desc' ? ' \u25BC' : ' \u25B2');
                }
                if (typeof opts.onSort === 'function') {
                    (function (k) {
                        th.addEventListener('click', function () { opts.onSort(k); });
                    })(col.key);
                }
            }
            htr.appendChild(th);
        });
        thead.appendChild(htr);
        table.appendChild(thead);

        var tbody = document.createElement('tbody');
        rows.forEach(function (r) {
            var tr = document.createElement('tr');
            tr.className = statusClass(r.status);
            tr.setAttribute('data-session-id', String(r.session_id));
            if (r.anomaly) { tr.className += ' aiw-has-anomaly'; }

            cell(tr, statusLabel(r.status), 'aiw-status ' + statusClass(r.status));
            cell(tr, r.session_id);
            cell(tr, r.subject_id);
            cell(tr, caseUserLabel(r), 'aiw-username');
            cell(tr, supporterLabel(r));
            cell(tr, formatTs(r.started_at));
            cell(tr, formatTs(r.ended_at));
            cell(tr, formatDuration(r.duration_sec), 'aiw-dauer');
            cell(tr, r.reason || '\u2014', 'aiw-reason');
            cell(tr, belegLabel(r), 'aiw-beleg');
            cell(tr, anomalyLabel(r.anomaly),
                r.anomaly ? 'aiw-anomaly' : '');

            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        container.appendChild(table);

        log('renderInto: fertig,', rows.length, 'Zeilen');
        return { rows: rows.length };
    }

    // -------------------------------------------------------------------------
    // Bootstrap im Browser: haelt den Anzeigestand (Records, Sortierung, Filter),
    // verdrahtet Kopfzeilen-Sortierung und das Filterfeld (#aiw-filter) und
    // rendert in #aiw-support-overview-root. In Node/Vitest (kein document)
    // passiert nichts.
    // -------------------------------------------------------------------------
    function boot() {
        if (typeof document === 'undefined') { return; }
        var root = document.getElementById('aiw-support-overview-root');
        if (!root) { log('boot: kein #aiw-support-overview-root'); return; }

        var all = (typeof window !== 'undefined'
            && window.__AIW_SUPPORT_OVERVIEW__) || [];
        var state = { sortKey: 'anchor', sortDir: 'asc', filter: '' };
        log('boot: starte mit', all.length, 'Sitzungen');

        var filterInput = document.getElementById('aiw-filter');
        var countEl = document.getElementById('aiw-count');

        function apply() {
            var filtered = filterRecords(all, state.filter);
            var ordered = sortRecords(filtered, state.sortKey, state.sortDir);
            renderInto(root, ordered, {
                sortKey: state.sortKey,
                sortDir: state.sortDir,
                onSort: function (key) {
                    if (state.sortKey === key) {
                        state.sortDir = (state.sortDir === 'asc') ? 'desc' : 'asc';
                    } else {
                        state.sortKey = key;
                        state.sortDir = 'asc';
                    }
                    log('sort ->', state.sortKey, state.sortDir);
                    apply();
                }
            });
            if (countEl) {
                countEl.textContent = filtered.length + ' von ' + all.length
                    + ' Sitzungen';
            }
        }

        if (filterInput) {
            filterInput.addEventListener('input', function () {
                state.filter = filterInput.value;
                log('filter ->', state.filter);
                apply();
            });
        }
        apply();
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
        statusClass: statusClass,
        statusLabel: statusLabel,
        anomalyLabel: anomalyLabel,
        supporterLabel: supporterLabel,
        caseUserLabel: caseUserLabel,
        formatDuration: formatDuration,
        formatTs: formatTs,
        anchorTs: anchorTs,
        sortRecords: sortRecords,
        filterRecords: filterRecords,
        belegLabel: belegLabel,
        renderInto: renderInto,
        boot: boot
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWSupportOverview = API; }
})();
