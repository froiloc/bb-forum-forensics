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
//   349 = Integritaets-/Ops-Sicht (/api/integrity, cockpit_integrity.js) +
//   globaler Ketten-Banner (still ohne ops.view) + SSE-Reaktualisierung des
//   Banners; ausserdem Live-DEBUG (Flag zur Laufzeit auslesbar, kein Reload).
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
// Version: v0.7.349 · Build: 349 · 2026-07-10
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
        { id: 'reports',    cap: 'reports.approve',      group: 'Verwaltung',     label: 'Berichts-Abnahme' },
        { id: 'stats',      cap: 'stats.export_sta',     group: 'Auswertung',     label: 'Statistiken (StA/Fuehrung)' },
        { id: 'workload',   cap: 'workload.view',        group: 'Auswertung',     label: 'Lastverteilung' },
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
    function visibleViews(capabilities) {
        return VIEW_CATALOG.filter(function (v) {
            return hasCap(capabilities, v.cap);
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

            var scope = scopeTag(v.cap, capabilities);
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
    var state = { capabilities: {}, activeId: null, table: null, sse: null };

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

    // destroyTable: laufende Tabulator-Instanz sauber abbauen (verhindert
    // DOM-/Listener-Leaks und doppelte Tabellen beim Sichtwechsel/Reload).
    function destroyTable() {
        if (state.table && typeof state.table.destroy === 'function') {
            try { state.table.destroy(); } catch (e) { log('destroyTable', e); }
        }
        state.table = null;
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
            destroyTable();  // vorherige Instanz vor Neuaufbau abbauen
            state.table = ov.renderOverview(mainEl, data, {});
            log('Overview gerendert:', data.count, 'Faelle, scope', data.scope);
        }).catch(function (err) {
            destroyTable();
            renderError(mainEl,
                'Uebersicht konnte nicht geladen werden: ' + err.message);
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
        destroyTable();  // beim Sichtwechsel evtl. offene Tabelle abbauen
        var navEl = document.getElementById('aiw-nav');
        var mainEl = document.getElementById('aiw-main');
        var views = visibleViews(state.capabilities);
        buildNav(navEl, views, state.capabilities, state.activeId, selectView);
        if (viewId === 'dashboard') {
            loadOverview(mainEl);
        } else if (viewId === 'integrity') {
            loadIntegrity(mainEl);
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
