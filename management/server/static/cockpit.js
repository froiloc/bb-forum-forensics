// =============================================================================
// management/server/static/cockpit.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit-Shell (Frontend)
// =============================================================================
// Zweck:
//   Baut die policy-getriebene Navigation der Verwaltungsoberflaeche im Browser
//   auf. Quelle der Wahrheit ist /api/whoami: dort liefert der Server die
//   aufgeloesten Faehigkeiten je Person als { cap: scope }-Objekt (scope =
//   'alle' | 'eigene' | null). Aus DIESEN Faehigkeiten leiten sich (a) die
//   sichtbaren Nav-Eintraege und (b) der angezeigte Scope ab — nicht aus einem
//   fest verdrahteten Rollenbild.
//   Beleg: Bauplan B7 v1.1 §11.2; Referenzlayout AIW_Verwaltung_Mockup.html.
//
// ABGRENZUNG (Split analog 314/315, Beleg: UEBERGABE_Build346 §6):
//   347 = Fundament (Nav, Rechte). 348 = Overview-Sicht (Tabulator) + SSE-Reload.
//   349 = Integritaets-/Ops-Sicht + Ketten-Banner + Live-DEBUG.
//   350 = Backend /api/workload + ECharts-Vendoring.
//   351 = Lastverteilung-Sicht (/api/workload, cockpit_workload.js) als
//   gestapeltes ECharts-Balkendiagramm + SSE-Reload; ECharts-Lifecycle
//   (dispose + Resize) in cleanupView().
//
// KAPSELUNG / PROJEKT-GEBOTE FUER JS:
//   1) IIFE-Wrapper mit 'use strict'.
//   2) Exzessives DEV-Debug-Logging, per Flag abschaltbar (PROD: aus).
//   3) Ausfuehrliche Kommentare (Zweck + Ueberlegung).
//   4) Logik gekapselt; REINE Funktionen fassen NIE das DOM an.
//   Zusaetzlich: UMD-artiger Ausgang, damit die Vitest-Tests den ECHTEN Code
//   pruefen (kein dupliziertes Logik-Abbild -> vermeidet die 'gruen-aber-tot'-
//   Falle). Nur die render/boot-Funktionen beruehren document (Browser/jsdom).
//
// SICHERHEIT: Anzeigename (display_name) stammt aus dem AD und ist potenziell
//   fremdbestimmt -> IMMER via textContent setzen, nie via innerHTML. Nav-Label
//   und Gruppen stammen aus dem statischen VIEW_CATALOG (unkritisch), werden
//   aber ebenfalls via textContent gesetzt (Prinzip: kein innerHTML mit
//   variablem Text).
//
//   360 = Kapazitaets-Sicht (/api/capacity, cockpit_capacity.js) als ECharts-
//   Diagramm (Basis vs. netto, Auslastungs-Faerbung, Zeitraumwahl) + SSE-Reload.
//   362 = Rechte/Policy-Sicht (/api/policy, cockpit_policy.js): Tabulator-Tabellen
//   fuer Grants + Rollen-Zuweisungen + Katalog + SSE-Reload.
//   364 = Persoenliche Sichten (cockpit_mycases.js / cockpit_myhistory.js):
//   Meine Auftraege + Meine Historie (Tabulator) + SSE-Reload.
//   367 = Support-Historie (/api/support, cockpit_support.js): zwei Listen (Meine
//   Sitzungen / An meinen Faellen) + Detail-Mini-Modal + SSE-Reload.
//   369 = Ermittler-Betreuung (/api/mentoring, cockpit_mentoring.js): Live-Sicht
//   laufender Support-Sitzungen (Ampel/Laufzeit) + periodischer Refresh.
//   371 = Statistiken (/api/stats, cockpit_stats.js): Reiterstruktur, ECharts-
//   Diagramme (Verteilungen/Durchsatz), Ermittler-Tabelle, CSV/JSON-Download.
//   373 = Zuweisung (SCHREIB-Sicht): /api/assignable + POST /api/case/* mit
//   Schreib-Token (X-AIW-Token aus /api/whoami); kein optimistisches UI.
//   375 = Berichts-Abnahme (/api/reports, cockpit_reports.js) + Nav-Korrektur:
//   Sichten koennen mehrere Faehigkeiten haben (any-of, Feld 'caps').
//   378 = Berichts-Freigabe im Cockpit (POST /api/report/approve mit Schreib-
//   Token, GET /api/report/verify zur Siegelpruefung).
// Version: v0.7.378 · Build: 378 · 2026-07-10
// =============================================================================

(function () {
    'use strict';

    // -------------------------------------------------------------------------
    // DEV-Debug-Logging. Aktivierung im Browser JEDERZEIT (zur Laufzeit):
    //   window.AIW_COCKPIT_DEBUG = true;   // an
    //   window.AIW_COCKPIT_DEBUG = false;  // aus
    // Build 349: Das Flag wird bei JEDEM log()-Aufruf ausgelesen (nicht mehr
    // einmalig beim Laden), damit es ohne Reload umschaltbar ist. PROD: aus.
    // -------------------------------------------------------------------------
    function debugOn() {
        return (typeof window !== 'undefined')
            && window.AIW_COCKPIT_DEBUG === true;
    }
    function log() {
        if (!debugOn()) { return; }
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[AIW-Cockpit]');
        // eslint-disable-next-line no-console
        console.log.apply(console, args);
    }

    // =========================================================================
    // 1) SICHTEN-KATALOG (statisch). Jede Sicht haengt an GENAU EINER Faehigkeit
    //    und erscheint nur, wenn die Person diese Faehigkeit besitzt. 'group'
    //    ordnet die Nav; die Reihenfolge hier bestimmt Nav- UND Gruppen-Folge.
    //    Abgeleitet aus dem Mockup (VIEWS) + Ergaenzung 'integrity' (cap
    //    'ops.view'), da das Backend /api/integrity bereitstellt (Build 346).
    // =========================================================================
    var VIEW_CATALOG = [
        { id: 'dashboard',  cap: 'dashboard.view',       group: 'Ueberblick',     label: 'Dashboard' },
        { id: 'assignment', cap: 'assignment.edit',      group: 'Verwaltung',     label: 'Zuweisung' },
        { id: 'mentoring',  cap: 'mentoring.view',       group: 'Verwaltung',     label: 'Ermittler-Betreuung' },
        // Berichts-Abnahme: 'reports.approve' ODER 'reports.review' genuegt
        // (wer freigeben darf, muss lesen duerfen). 'caps' = any-of; 'cap' bleibt
        // fuer den Scope-Tag/Platzhalter die Leitfaehigkeit.
        { id: 'reports',    cap: 'reports.approve',      caps: ['reports.approve', 'reports.review'], group: 'Verwaltung',     label: 'Berichts-Abnahme' },
        { id: 'stats',      cap: 'stats.export_sta',     group: 'Auswertung',     label: 'Statistiken (StA/Fuehrung)' },
        { id: 'workload',   cap: 'workload.view',        group: 'Auswertung',     label: 'Lastverteilung' },
        { id: 'capacity',   cap: 'capacity.edit',        group: 'Auswertung',     label: 'Kapazitaet' },
        { id: 'support',    cap: 'support_history.view', group: 'Auswertung',     label: 'Support-Historie' },
        { id: 'mycases',    cap: 'mycases.view',         group: 'Persoenlich',    label: 'Meine Auftraege' },
        { id: 'myhistory',  cap: 'myhistory.view',       group: 'Persoenlich',    label: 'Meine Historie' },
        { id: 'policy',     cap: 'policy.view',          group: 'Administration', label: 'Rechte / Policy' },
        { id: 'integrity',  cap: 'ops.view',             group: 'Administration', label: 'Integritaet / Betrieb' }
    ];

    // Gueltige Scope-Werte fuer die Anzeige (weitere -> kein Tag).
    var VALID_SCOPES = { alle: true, eigene: true };

    // =========================================================================
    // 2) REINE FUNKTIONEN (kein DOM). Genau diese testet vitest.
    // =========================================================================

    // hasCap: besitzt die Person die Faehigkeit? Praesenz des Schluessels zaehlt
    // (scope darf null sein — z.B. global geltende Faehigkeiten).
    function hasCap(capabilities, cap) {
        return !!capabilities
            && Object.prototype.hasOwnProperty.call(capabilities, cap);
    }

    // visibleViews: Sichten, deren Faehigkeit vorliegt — in Katalog-Reihenfolge.
    // Gibt eine NEUE Liste zurueck (mutiert VIEW_CATALOG nicht).
    // viewCaps: Faehigkeiten, von denen EINE genuegt (any-of). Faellt auf die
    // Einzel-Faehigkeit 'cap' zurueck (Rueckwaertskompatibilitaet).
    function viewCaps(v) {
        return (v.caps && v.caps.length) ? v.caps : [v.cap];
    }

    // effectiveCap: die erste vorhandene Faehigkeit der Sicht (fuer Scope-Tag).
    function effectiveCap(v, capabilities) {
        var caps = viewCaps(v);
        for (var i = 0; i < caps.length; i++) {
            if (hasCap(capabilities, caps[i])) { return caps[i]; }
        }
        return v.cap;
    }

    function visibleViews(capabilities) {
        return VIEW_CATALOG.filter(function (v) {
            return viewCaps(v).some(function (c) {
                return hasCap(capabilities, c);
            });
        });
    }

    // scopeTag: Scope-Text fuer die Nav ('alle'/'eigene') oder '' (kein Tag,
    // z.B. bei scope null oder unbekanntem Wert).
    function scopeTag(cap, capabilities) {
        if (!hasCap(capabilities, cap)) { return ''; }
        var s = capabilities[cap];
        return VALID_SCOPES[s] ? s : '';
    }

    // firstViewId: ID der ersten sichtbaren Sicht oder null (Startauswahl /
    // Rueckfall, wenn die aktive Sicht nicht mehr sichtbar ist).
    function firstViewId(views) {
        return (views && views.length) ? views[0].id : null;
    }

    // groupSequence: geordnete, eindeutige Gruppenfolge der sichtbaren Sichten
    // (bestimmt die Reihenfolge der Nav-Gruppenkoepfe).
    function groupSequence(views) {
        var seen = {};
        var out = [];
        (views || []).forEach(function (v) {
            if (!Object.prototype.hasOwnProperty.call(seen, v.group)) {
                seen[v.group] = true;
                out.push(v.group);
            }
        });
        return out;
    }

    // viewById: Katalogeintrag zu einer ID (oder null).
    function viewById(id) {
        for (var i = 0; i < VIEW_CATALOG.length; i++) {
            if (VIEW_CATALOG[i].id === id) { return VIEW_CATALOG[i]; }
        }
        return null;
    }

    // =========================================================================
    // 3) DOM-FUNKTIONEN (nur Browser/jsdom). Beruehren document.
    // =========================================================================

    // setWho: Anzeigename in die Kopfleiste schreiben. display_name via
    // textContent (AD-Herkunft -> XSS-sicher), system_username in Klammern.
    function setWho(whoEl, displayName, systemUsername) {
        if (!whoEl) { return; }
        whoEl.textContent = '';
        var strong = document.createElement('strong');
        strong.textContent = displayName || '?';
        whoEl.appendChild(document.createTextNode('angemeldet als '));
        whoEl.appendChild(strong);
        if (systemUsername) {
            whoEl.appendChild(
                document.createTextNode(' (' + systemUsername + ')'));
        }
    }

    // buildNav: Navigation in 'navEl' neu aufbauen. views = sichtbare Sichten
    // (aus visibleViews), capabilities fuer die Scope-Tags, activeId markiert
    // die aktive Sicht, onSelect(viewId) wird bei Klick aufgerufen.
    // XSS-sicher: alle variablen Texte via textContent.
    function buildNav(navEl, views, capabilities, activeId, onSelect) {
        if (!navEl) { return; }
        navEl.textContent = '';
        var lastGroup = null;
        views.forEach(function (v) {
            if (v.group !== lastGroup) {
                var g = document.createElement('div');
                g.className = 'aiw-navgroup';
                g.textContent = v.group;
                navEl.appendChild(g);
                lastGroup = v.group;
            }
            var b = document.createElement('button');
            b.className = 'aiw-navitem' + (v.id === activeId ? ' active' : '');
            b.setAttribute('type', 'button');
            b.setAttribute('data-view-id', v.id);

            var labelSpan = document.createElement('span');
            labelSpan.textContent = v.label;
            b.appendChild(labelSpan);

            var scope = scopeTag(effectiveCap(v, capabilities), capabilities);
            if (scope) {
                var tag = document.createElement('span');
                tag.className = 'aiw-scopetag ' + scope;
                tag.textContent = scope;
                b.appendChild(tag);
            }

            b.addEventListener('click', function () {
                log('Nav-Klick', v.id);
                if (typeof onSelect === 'function') { onSelect(v.id); }
            });
            navEl.appendChild(b);
        });
        log('Nav gebaut:', views.length, 'Sichten, aktiv:', activeId);
    }

    // renderPlaceholder: Leerzustand fuer die gewaehlte Sicht (Build 347). Die
    // echte Sicht-Verdrahtung folgt in 348.
    function renderPlaceholder(mainEl, view) {
        if (!mainEl) { return; }
        mainEl.textContent = '';
        var h = document.createElement('h2');
        h.className = 'aiw-pagehead';
        h.textContent = view ? view.label : 'Keine Sicht verfuegbar';
        mainEl.appendChild(h);

        var p = document.createElement('p');
        p.className = 'aiw-pagesub';
        p.textContent = view
            ? ('Faehigkeit: ' + view.cap)
            : 'Fuer diese Identitaet ist keine Sicht freigegeben (default-deny).';
        mainEl.appendChild(p);

        if (view) {
            var box = document.createElement('div');
            box.className = 'aiw-placeholder';
            box.textContent = 'Diese Sicht wird in einem Folge-Build (348) '
                + 'verdrahtet. Das Fundament (Navigation, Rechte) ist aktiv.';
            mainEl.appendChild(box);
        }
    }

    // =========================================================================
    // 4) BOOT — im Browser: whoami holen, Nav bauen, erste Sicht anzeigen.
    // =========================================================================

    // Zustand lebt nur im Speicher (kein localStorage — Projekt-/Artefakt-Regel).
    // table = aktuelle Tabulator-Instanz (Build 348, Overview); sse = EventSource.
    var state = {
        capabilities: {}, activeId: null,
        table: null,        // aktuelle Tabulator-Instanz (Overview)
        tables: [],         // mehrere Tabulator-Instanzen (Policy-Sicht)
        charts: [],         // mehrere ECharts-Instanzen (Statistik-Sicht)
        chart: null,        // aktuelle ECharts-Instanz (Lastverteilung/Kapazitaet)
        chartResize: null,  // Resize-Handler der ECharts-Instanz
        capacityPeriod: null,  // {start, end} der Kapazitaets-Sicht (SSE-Reload)
        mentoringTimer: null,  // Intervall-Handle des Betreuungs-Live-Refresh
        sse: null,
        // Schreib-Token (Build 372/373): kommt aus /api/whoami und MUSS bei
        // jedem POST als 'X-AIW-Token' mitgeschickt werden.
        writeToken: null
    };

    // fetchJson: kleiner Wrapper mit DEV-Logging und klarer Fehlermeldung.
    function fetchJson(url) {
        log('fetch', url);
        return fetch(url, { headers: { 'Accept': 'application/json' } })
            .then(function (r) {
                if (!r.ok) {
                    throw new Error('HTTP ' + r.status + ' bei ' + url);
                }
                return r.json();
            });
    }

    // postJson: AUDITIERTER SCHREIBZUGRIFF (Build 372). Sendet JSON mit dem
    // Schreib-Token. Fehlerantworten werden AUSGEWERTET und als Fehler mit der
    // Server-Begruendung weitergereicht (Grundregel 1: kein stiller Fehlschlag).
    function postJson(url, body) {
        log('post', url, body);
        if (!state.writeToken) {
            return Promise.reject(new Error(
                'Kein Schreib-Token vorhanden (Server neu gestartet? '
                + 'Seite neu laden).'));
        }
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-AIW-Token': state.writeToken
            },
            body: JSON.stringify(body)
        }).then(function (r) {
            return r.json().catch(function () { return {}; })
                .then(function (data) {
                    if (!r.ok) {
                        var detail = data.detail || data.error
                            || ('HTTP ' + r.status);
                        throw new Error(detail);
                    }
                    return data;
                });
        });
    }

    // destroyTable: laufende Tabulator-Instanz sauber abbauen (verhindert
    // DOM-/Listener-Leaks und doppelte Tabellen beim Sichtwechsel/Reload).
    function destroyTable() {
        if (state.table && typeof state.table.destroy === 'function') {
            try { state.table.destroy(); } catch (e) { log('destroyTable', e); }
        }
        state.table = null;
    }

    // destroyChart: laufende ECharts-Instanz entsorgen (dispose) und den daran
    // gebundenen Resize-Handler abmelden. ECharts nutzt dispose(), nicht
    // destroy() -> daher getrennt von destroyTable().
    function destroyChart() {
        if (state.chartResize && typeof window !== 'undefined') {
            window.removeEventListener('resize', state.chartResize);
            state.chartResize = null;
        }
        if (state.chart && typeof state.chart.dispose === 'function') {
            try { state.chart.dispose(); } catch (e) { log('destroyChart', e); }
        }
        state.chart = null;
    }

    // cleanupView: alle sicht-spezifischen Artefakte (Tabelle UND Diagramm)
    // abbauen. Wird beim Sichtwechsel und vor jedem Neuaufbau aufgerufen.
    function cleanupView() {
        destroyTable();
        // Mehrfach-Tabellen (Policy-Sicht) abbauen.
        (state.tables || []).forEach(function (t) {
            if (t && typeof t.destroy === 'function') {
                try { t.destroy(); } catch (e) { log('destroyTables', e); }
            }
        });
        state.tables = [];
        destroyChart();
        // Mehrfach-Charts (Statistik-Sicht) entsorgen.
        (state.charts || []).forEach(function (c) {
            if (c && typeof c.dispose === 'function') {
                try { c.dispose(); } catch (e) { log('destroyCharts', e); }
            }
        });
        state.charts = [];
        // Periodischen Betreuungs-Refresh stoppen (Live-Sicht verlassen).
        if (state.mentoringTimer) {
            clearInterval(state.mentoringTimer);
            state.mentoringTimer = null;
        }
    }

    // renderError: sichtbarer Fehlerhinweis im Hauptbereich (kein stiller Fehlpfad).
    function renderError(mainEl, msg) {
        if (!mainEl) { return; }
        mainEl.textContent = '';
        var p = document.createElement('p');
        p.className = 'aiw-pagesub';
        p.textContent = msg;
        mainEl.appendChild(p);
    }

    // loadOverview: /api/overview holen und als Tabulator-Tabelle rendern
    // (cockpit_overview.js). Wird bei Sichtwahl 'dashboard' UND bei SSE-'changed'
    // auf der aktiven Overview-Sicht aufgerufen.
    function loadOverview(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var ov = (typeof window !== 'undefined') ? window.AIWCockpitOverview : null;
        if (!ov) {
            renderError(mainEl, 'Overview-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/overview').then(function (data) {
            cleanupView();  // vorherige Artefakte vor Neuaufbau abbauen
            state.table = ov.renderOverview(mainEl, data, {});
            log('Overview gerendert:', data.count, 'Faelle, scope', data.scope);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Uebersicht konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadWorkload: /api/workload holen und als ECharts-Diagramm rendern
    // (cockpit_workload.js). Bindet einen Resize-Handler an die Instanz, damit
    // das Diagramm bei Fensteraenderung mitwaechst (in cleanupView abgemeldet).
    function loadWorkload(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined') ? window.AIWCockpitWorkload : null;
        if (!mod) {
            renderError(mainEl, 'Workload-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/workload').then(function (data) {
            cleanupView();  // Tabelle/altes Diagramm vor Neuaufbau abbauen
            state.chart = mod.renderWorkload(mainEl, data, {});
            if (state.chart && typeof state.chart.resize === 'function') {
                state.chartResize = function () {
                    try { state.chart.resize(); } catch (e) { log('resize', e); }
                };
                window.addEventListener('resize', state.chartResize);
            }
            log('Workload gerendert:', data.count, 'Zeilen, scope', data.scope);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Lastverteilung konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadCapacity: /api/capacity (Aggregat, ohne person_id) fuer einen Zeitraum
    // holen und als ECharts-Diagramm rendern (cockpit_capacity.js). Der Zeitraum
    // wird in state.capacityPeriod gehalten (Default: laufender Monat), damit der
    // SSE-Reload denselben Zeitraum verwendet. Die Zeitraum-Wahl im View ruft
    // loadCapacity mit neuem Zeitraum erneut auf.
    function loadCapacity(mainEl, period) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCapacity : null;
        if (!mod) {
            renderError(mainEl, 'Kapazitaets-Modul nicht geladen.');
            return;
        }
        if (!period) {
            period = state.capacityPeriod || mod.defaultPeriod();
        }
        state.capacityPeriod = period;
        var url = '/api/capacity?start=' + encodeURIComponent(period.start)
            + '&end=' + encodeURIComponent(period.end);
        fetchJson(url).then(function (data) {
            cleanupView();
            state.chart = mod.renderCapacity(mainEl, data, {
                onPeriodChange: function (start, end) {
                    if (start && end) {
                        loadCapacity(mainEl, { start: start, end: end });
                    }
                }
            });
            if (state.chart && typeof state.chart.resize === 'function') {
                state.chartResize = function () {
                    try { state.chart.resize(); } catch (e) { log('resize', e); }
                };
                window.addEventListener('resize', state.chartResize);
            }
            log('Kapazitaet gerendert:', data.count, 'Ermittler,',
                period.start, 'bis', period.end);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Kapazitaet konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadPolicy: /api/policy holen und als RBAC-Policy-Sicht rendern
    // (cockpit_policy.js). Liefert mehrere Tabulator-Instanzen -> state.tables
    // (in cleanupView abgebaut).
    function loadPolicy(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined') ? window.AIWCockpitPolicy : null;
        if (!mod) {
            renderError(mainEl, 'Policy-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/policy').then(function (data) {
            cleanupView();
            state.tables = mod.renderPolicy(mainEl, data, {}) || [];
            log('Policy gerendert:', (data.counts && data.counts.grants),
                'Grants, scope', data.scope);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Policy konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadMyCases: /api/mycases holen und als persoenliche Fall-Liste rendern
    // (cockpit_mycases.js). Einzelne Tabulator-Instanz -> state.table.
    function loadMyCases(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMyCases : null;
        if (!mod) {
            renderError(mainEl, 'Modul "Meine Auftraege" nicht geladen.');
            return;
        }
        fetchJson('/api/mycases').then(function (data) {
            cleanupView();
            state.table = mod.renderMyCases(mainEl, data, {});
            log('Meine Auftraege gerendert:', data.count);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Meine Auftraege konnten nicht geladen werden: ' + err.message);
        });
    }

    // loadMyHistory: /api/myhistory holen und als kombinierte Zeitleiste
    // rendern (cockpit_myhistory.js). Einzelne Tabulator-Instanz -> state.table.
    function loadMyHistory(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMyHistory : null;
        if (!mod) {
            renderError(mainEl, 'Modul "Meine Historie" nicht geladen.');
            return;
        }
        fetchJson('/api/myhistory').then(function (data) {
            cleanupView();
            state.table = mod.renderMyHistory(mainEl, data, {});
            log('Meine Historie gerendert:', data.count, 'Eintraege');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Meine Historie konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadSupport: /api/support holen und als Support-Historie rendern
    // (cockpit_support.js). Liefert mehrere Tabulator-Instanzen -> state.tables
    // (in cleanupView abgebaut).
    function loadSupport(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitSupport : null;
        if (!mod) {
            renderError(mainEl, 'Support-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/support').then(function (data) {
            cleanupView();
            state.tables = mod.renderSupport(mainEl, data, {}) || [];
            log('Support-Historie gerendert:', data.count, 'Sitzungen');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Support-Historie konnte nicht geladen werden: ' + err.message);
        });
    }

    // Betreuung: LIVE-Sicht. Heartbeats sind nicht auditiert -> SSE genuegt
    // nicht; wir laden periodisch nach (Intervall). MENTORING_REFRESH_MS unter
    // der Stale-Schwelle (30 s), damit der Uebergang live->stale zeitnah
    // sichtbar wird.
    var MENTORING_REFRESH_MS = 15000;

    // refreshMentoring: ein Refresh-Tick — Daten neu holen und die Tabelle neu
    // aufbauen, OHNE den Timer anzufassen (sonst Timer-Churn). Nur wirksam,
    // solange die Betreuungs-Sicht aktiv ist.
    function refreshMentoring(mainEl) {
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMentoring : null;
        if (!mod) { return; }
        fetchJson('/api/mentoring').then(function (data) {
            if (state.activeId !== 'mentoring') { return; }
            if (state.table && typeof state.table.destroy === 'function') {
                try { state.table.destroy(); } catch (e) { log('refresh', e); }
            }
            state.table = mod.renderMentoring(mainEl, data, {});
            log('Betreuung aktualisiert:', data.count, 'laufend');
        }).catch(function (err) { log('Betreuung-Refresh-Fehler', err); });
    }

    // loadMentoring: Erst-Laden + periodischen Refresh scharf schalten.
    function loadMentoring(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMentoring : null;
        if (!mod) {
            renderError(mainEl, 'Betreuungs-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/mentoring').then(function (data) {
            cleanupView();  // baut alte Tabelle ab UND stoppt alten Timer
            state.table = mod.renderMentoring(mainEl, data, {});
            state.mentoringTimer = setInterval(function () {
                refreshMentoring(mainEl);
            }, MENTORING_REFRESH_MS);
            log('Betreuung gerendert:', data.count, 'laufend');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Ermittler-Betreuung konnte nicht geladen werden: '
                + err.message);
        });
    }

    // downloadBlob: erzeugt aus Text einen Download (Blob + <a download>).
    // Fehler werden geloggt, nicht verschluckt.
    function downloadBlob(filename, text, mime) {
        try {
            var blob = new Blob([text], { type: mime });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e) {
            log('downloadBlob-Fehler', e);
        }
    }

    // loadStats: /api/stats holen und als Statistik-Sicht rendern
    // (cockpit_stats.js). Mehrere ECharts -> state.charts; eine Tabelle ->
    // state.tables. Downloads: CSV via Endpunkt (?format=csv), JSON aus den
    // bereits geladenen Daten.
    function loadStats(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitStats : null;
        if (!mod) {
            renderError(mainEl, 'Statistik-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/stats').then(function (data) {
            cleanupView();
            var day = mod.isoDate();
            var res = mod.renderStats(mainEl, data, {
                onDownloadCsv: function () {
                    // CSV kommt aus dem Endpunkt (scope-korrekt serverseitig).
                    fetch('/api/stats?format=csv').then(function (r) {
                        return r.text();
                    }).then(function (text) {
                        downloadBlob('aiw_statistik_' + day + '.csv', text,
                            'text/csv;charset=utf-8');
                    }).catch(function (e) { log('CSV-Download', e); });
                },
                onDownloadJson: function (d) {
                    downloadBlob('aiw_statistik_' + day + '.json',
                        JSON.stringify(d, null, 2),
                        'application/json;charset=utf-8');
                }
            }) || { charts: [], tables: [] };
            state.charts = res.charts || [];
            state.tables = res.tables || [];
            log('Statistik gerendert:', data.totals && data.totals.cases,
                'Faelle');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Statistiken konnten nicht geladen werden: ' + err.message);
        });
    }

    // loadAssignment: SCHREIB-Sicht. Laedt /api/assignable und rendert die
    // Zuweisungs-Tabelle. Jede Aenderung geht per POST an den auditierten
    // Schreibpfad; danach wird NEU GELADEN (kein optimistisches UI: die
    // Oberflaeche zeigt nur bestaetigt geschriebene Zustaende). 'pendingMsg'
    // traegt die Rueckmeldung (Erfolg ODER Fehler) durch den Reload hindurch —
    // so bleibt sie sichtbar und geht nicht still verloren (Grundregel 1).
    function loadAssignment(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAssignment : null;
        if (!mod) {
            renderError(mainEl, 'Zuweisungs-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/assignable').then(function (data) {
            cleanupView();
            var view = mod.renderAssignment(mainEl, data, {
                onChange: function (kind, userId, value) {
                    var req = mod.changeRequest(kind, userId, value);
                    if (!req) {
                        view.setMessage('Unbekannte Aenderungsart: ' + kind,
                                        true);
                        return;
                    }
                    view.setMessage('Schreibe \u2026', false);
                    postJson(req.path, req.body).then(function (res) {
                        loadAssignment(mainEl, {
                            text: 'Gespeichert (Beleg #' + res.audit_seq + ').',
                            error: false
                        });
                    }).catch(function (err) {
                        log('Schreibfehler', err);
                        // Neu laden -> keine ungeschriebene Auswahl bleibt
                        // stehen; die Fehlermeldung wird mitgetragen.
                        loadAssignment(mainEl, {
                            text: 'Fehler: ' + err.message, error: true
                        });
                    });
                }
            });
            if (view && pendingMsg) {
                view.setMessage(pendingMsg.text, pendingMsg.error);
            }
            log('Zuweisung gerendert:', (data.cases || []).length, 'Faelle');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Zuweisung konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadReports: Berichts-Abnahme (/api/reports). force=true umgeht den
    // serverseitigen Scan-Cache (liest alle evidence-DBs neu ein).
    function loadReports(mainEl, force, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitReports : null;
        if (!mod) {
            renderError(mainEl, 'Berichts-Modul nicht geladen.');
            return;
        }
        var url = '/api/reports' + (force ? '?force=1' : '');
        fetchJson(url).then(function (data) {
            cleanupView();
            var t = mod.renderReports(mainEl, data, {
                onForceRescan: function () { loadReports(mainEl, true); },
                // Nur wer reports.approve besitzt, bekommt die Freigabe-Knoepfe.
                // (Der Server prueft es ohnehin erneut — die Oberflaeche soll
                // nur keine Aktion anbieten, die zwingend scheitern wuerde.)
                canApprove: hasCap(state.capabilities, 'reports.approve'),

                // FREIGABE (Schreibpfad, Build 377): POST mit Schreib-Token.
                // Danach NEU LADEN — die Sicht zeigt nur bestaetigt
                // geschriebene Zustaende (kein optimistisches UI).
                onApprove: function (userId, reportId, isFinal) {
                    postJson('/api/report/approve', {
                        user_id: userId, report_id: reportId,
                        is_final: !!isFinal
                    }).then(function (res) {
                        loadReports(mainEl, false, {
                            text: (isFinal ? 'Endgueltig freigegeben'
                                           : 'Freigegeben und versiegelt')
                                + ' (Beleg #' + res.audit_seq + ', Hash '
                                + String(res.content_sha256).slice(0, 12)
                                + '\u2026).',
                            error: false
                        });
                    }).catch(function (err) {
                        log('Freigabe-Fehler', err);
                        if (t && t.aiwSetResult) {
                            t.aiwSetResult('Fehler: ' + err.message, true);
                        }
                    });
                },

                // SIEGELPRUEFUNG (lesend): Hash neu bilden und vergleichen.
                onVerify: function (userId, reportId) {
                    fetchJson('/api/report/verify?user_id=' + userId
                              + '&report_id=' + reportId)
                        .then(function (v) {
                            if (t && t.aiwShowVerify) { t.aiwShowVerify(v); }
                            log('Siegelpruefung', v);
                        }).catch(function (err) {
                            if (t && t.aiwSetResult) {
                                t.aiwSetResult(
                                    'Siegelpruefung fehlgeschlagen: '
                                    + err.message, true);
                            }
                        });
                }
            });
            state.table = t;
            if (t && pendingMsg && t.aiwSetResult) {
                // Rueckmeldung der Freigabe durch den Reload tragen.
                t.aiwSelectRow(null);
                var box = mainEl.querySelector('#aiw-report-actions');
                if (box) {
                    var m = document.createElement('div');
                    m.className = pendingMsg.error ? 'error' : 'ok';
                    m.id = 'aiw-report-msg';
                    m.textContent = pendingMsg.text;
                    box.appendChild(m);
                }
            }
            log('Berichte gerendert:', data.count, '-', data.rescanned,
                'DBs neu eingelesen');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Berichte konnten nicht geladen werden: ' + err.message);
        });
    }

    // applyIntegrity: zentrale Banner-Aktualisierung aus einer Integritaets-
    // Antwort ({ok, first_bad_seq, detail, tip_seq}). Nutzt das Integritaets-
    // Modul (bannerModel + applyBanner). Wird von loadIntegrity UND refreshBanner
    // aufgerufen, damit der Banner-Zustand an genau einer Stelle entsteht.
    function applyIntegrity(data) {
        var mod = (typeof window !== 'undefined') ? window.AIWCockpitIntegrity : null;
        var bannerEl = document.getElementById('aiw-integrity');
        if (!mod || !bannerEl) { return; }
        mod.applyBanner(bannerEl, mod.bannerModel(data));
    }

    // refreshBanner: Ketten-Gesundheit GLOBAL im Banner anzeigen — unabhaengig
    // von der aktiven Sicht. Ohne 'ops.view' bleibt der Banner still/neutral
    // (kein 403-Rauschen; Entscheidung 2026-07-10). Wird bei boot() und bei
    // SSE-'changed' (wenn die aktive Sicht nicht 'integrity' ist) aufgerufen.
    function refreshBanner() {
        var bannerEl = document.getElementById('aiw-integrity');
        if (!hasCap(state.capabilities, 'ops.view')) {
            if (bannerEl) {
                bannerEl.textContent = '';
                bannerEl.className = 'aiw-integrity aiw-integrity-hidden';
            }
            return;
        }
        fetchJson('/api/integrity').then(function (data) {
            applyIntegrity(data);
            log('Banner aktualisiert: ok =', data.ok, 'tip', data.tip_seq);
        }).catch(function (err) {
            // Fehler nicht verschlucken: Banner in den Fehlerzustand setzen.
            if (bannerEl) {
                bannerEl.className = 'aiw-integrity fehler';
                bannerEl.textContent =
                    'Integritaet nicht pruefbar: ' + err.message;
            }
        });
    }

    // loadIntegrity: Integritaets-/Ops-Sicht rendern (cockpit_integrity.js) und
    // dabei den globalen Banner gleich mit aktualisieren (eine Quelle).
    function loadIntegrity(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined') ? window.AIWCockpitIntegrity : null;
        if (!mod) {
            renderError(mainEl, 'Integritaets-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/integrity').then(function (data) {
            mod.renderIntegrity(mainEl, data);
            applyIntegrity(data);
            log('Integritaet gerendert: ok =', data.ok, 'tip', data.tip_seq);
        }).catch(function (err) {
            renderError(mainEl,
                'Integritaet konnte nicht geladen werden: ' + err.message);
        });
    }

    // selectView: aktive Sicht setzen, Nav neu markieren, Inhalt dispatchen.
    // Build 349: 'dashboard' -> Overview; 'integrity' -> Integritaets-Sicht;
    // sonst Platzhalter (weitere Sichten folgen).
    function selectView(viewId) {
        state.activeId = viewId;
        cleanupView();  // beim Sichtwechsel offene Tabelle/Diagramm abbauen
        var navEl = document.getElementById('aiw-nav');
        var mainEl = document.getElementById('aiw-main');
        var views = visibleViews(state.capabilities);
        buildNav(navEl, views, state.capabilities, state.activeId, selectView);
        if (viewId === 'dashboard') {
            loadOverview(mainEl);
        } else if (viewId === 'integrity') {
            loadIntegrity(mainEl);
        } else if (viewId === 'workload') {
            loadWorkload(mainEl);
        } else if (viewId === 'capacity') {
            loadCapacity(mainEl);
        } else if (viewId === 'policy') {
            loadPolicy(mainEl);
        } else if (viewId === 'mycases') {
            loadMyCases(mainEl);
        } else if (viewId === 'myhistory') {
            loadMyHistory(mainEl);
        } else if (viewId === 'support') {
            loadSupport(mainEl);
        } else if (viewId === 'mentoring') {
            loadMentoring(mainEl);
        } else if (viewId === 'stats') {
            loadStats(mainEl);
        } else if (viewId === 'assignment') {
            loadAssignment(mainEl);
        } else if (viewId === 'reports') {
            loadReports(mainEl);
        } else {
            renderPlaceholder(mainEl, viewById(viewId));
        }
    }

    // startSse: Live-Aktualisierung. Server pollt die audit_log-Spitze; bei
    // 'changed' laedt der Client NUR die aktive Sicht neu (kein F5, §11.2/§11.1).
    // hello/keepalive sind reine Lebenszeichen. EventSource reconnectet selbst.
    function startSse() {
        if (typeof EventSource === 'undefined') {
            log('EventSource n/a — kein Live-Reload');
            return;
        }
        var es = new EventSource('/events');
        es.addEventListener('hello', function (e) { log('SSE hello', e.data); });
        es.addEventListener('keepalive', function () { /* Lebenszeichen */ });
        es.addEventListener('changed', function (e) {
            log('SSE changed', e.data);
            // Aktive Sicht neu laden (kein F5, §11.2/§11.1):
            if (state.activeId === 'dashboard') {
                loadOverview();
            } else if (state.activeId === 'integrity') {
                loadIntegrity();   // aktualisiert Sicht UND Banner
            } else if (state.activeId === 'workload') {
                loadWorkload();
            } else if (state.activeId === 'capacity') {
                loadCapacity(undefined, state.capacityPeriod);
            } else if (state.activeId === 'policy') {
                loadPolicy();
            } else if (state.activeId === 'mycases') {
                loadMyCases();
            } else if (state.activeId === 'myhistory') {
                loadMyHistory();
            } else if (state.activeId === 'support') {
                loadSupport();
            } else if (state.activeId === 'mentoring') {
                loadMentoring();
            } else if (state.activeId === 'stats') {
                loadStats();
            } else if (state.activeId === 'assignment') {
                loadAssignment();
            } else if (state.activeId === 'reports') {
                loadReports();
            }
            // Banner global frisch halten, wenn die aktive Sicht nicht die
            // Integritaets-Sicht ist (dort geschieht es bereits oben).
            if (state.activeId !== 'integrity') {
                refreshBanner();
            }
        });
        es.onerror = function () {
            // Bei Reconnect/Serverneustart normal; kein harter Fehler.
            log('SSE onerror (Auto-Reconnect)');
        };
        state.sse = es;
        log('SSE gestartet');
    }

    function boot() {
        log('boot() Start');
        fetchJson('/api/whoami').then(function (who) {
            log('whoami', who);
            state.capabilities = who.capabilities || {};
            // Schreib-Token uebernehmen (nur ueber diesen authentifizierten
            // GET erhaeltlich; Voraussetzung fuer alle POSTs).
            state.writeToken = who.write_token || null;
            if (!state.writeToken) {
                log('WARNUNG: kein write_token in /api/whoami');
            }
            setWho(document.getElementById('aiw-who'),
                   who.display_name, who.system_username);

            var views = visibleViews(state.capabilities);
            state.activeId = firstViewId(views);
            // Erste Sicht ueber selectView anzeigen (laedt ggf. die Overview).
            if (state.activeId) {
                selectView(state.activeId);
            } else {
                buildNav(document.getElementById('aiw-nav'), views,
                         state.capabilities, null, selectView);
                renderPlaceholder(document.getElementById('aiw-main'), null);
            }

            // Ketten-Gesundheit global im Banner anzeigen (still, wenn keine
            // ops.view). Wenn 'integrity' die erste Sicht ist, hat selectView
            // den Banner bereits gesetzt -> Doppel-Fetch vermeiden.
            if (state.activeId !== 'integrity') {
                refreshBanner();
            }

            // Live-Reload aktivieren.
            startSse();

            log('boot() fertig:', views.length, 'Sichten');
        }).catch(function (err) {
            // Kein stiller Fehlpfad: sichtbarer Hinweis + Console.
            // eslint-disable-next-line no-console
            console.error('[AIW-Cockpit] boot-Fehler:', err);
            var main = document.getElementById('aiw-main');
            if (main) {
                main.textContent = 'Fehler beim Laden der Identitaet: '
                    + err.message;
            }
        });
    }

    // Auto-Boot nur im echten Browser: window + document + fetch muessen da
    // sein. Unter Node/Vitest (JSDOM ohne fetch) wird NICHT gebootet — die
    // Unit-Tests rufen die (reinen/DOM-)Funktionen gezielt selbst auf. So
    // sprengt das fehlende fetch nicht den Modul-Eval.
    if (typeof window !== 'undefined' && typeof document !== 'undefined'
            && typeof fetch !== 'undefined') {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', boot);
        } else {
            boot();
        }
    }

    // =========================================================================
    // 5) UMD-artiger Ausgang: dieselbe API an window (Browser) UND
    //    module.exports (Node/Vitest). So testen die Unit-Tests den ECHTEN Code.
    // =========================================================================
    var API = {
        VIEW_CATALOG: VIEW_CATALOG,
        hasCap: hasCap,
        viewCaps: viewCaps,
        effectiveCap: effectiveCap,
        visibleViews: visibleViews,
        scopeTag: scopeTag,
        firstViewId: firstViewId,
        groupSequence: groupSequence,
        viewById: viewById,
        setWho: setWho,
        buildNav: buildNav,
        renderPlaceholder: renderPlaceholder,
        boot: boot
    };
    if (typeof module !== 'undefined' && module.exports) { module.exports = API; }
    if (typeof window !== 'undefined') { window.AIWCockpit = API; }
})();
