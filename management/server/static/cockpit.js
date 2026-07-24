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
//   380 = Rueckgabe zur Nachbesserung (POST /api/report/return).
//   384 = Fall-Erkennung (cockpit_cases.js): GET /api/cases/detect (rein
//   lesender Abgleich Platte <-> Fallakte, vier Zustaende) + POST
//   /api/cases/import (auditierte Aufnahme der AUSGEWAEHLTEN Faelle, mit
//   Bestaetigung). Recht: assignment.edit (Backend-Vorgabe aus Build 383).
//   386 = Kalender & Wiedervorlage (cockpit_calendar.js): GET /api/calendar
//   (Monatsraster ueber ALLE Zeitquellen) + GET /api/external (Vorgangsliste)
//   + POST /api/external/create|defer|answer|close. Recht: external.view;
//   Schreiben nur mit external.edit.
//   395 = Ermittlungsergebnis (cockpit_results.js): Abdeckung JE FALL (auch
//   die NIE bewerteten — die blinden Flecken sind die Hauptaussage) +
//   Verteilung JE KRITERIUM (nie darueber hinweg). Recht: results.view.
//   406 = Betreuungs-Notizen (cockpit_notes.js): Pinboard der Ermittler-
//   Betreuung. Karten in Git-Commit-Metapher (erste Zeile = Ueberschrift, immer
//   sichtbar; Rest aufklappbar), Farbe + Tags, Status 'abarbeiten', client-
//   seitige Suche/Filter, Archiv-Umschalter, Anlegen/Bearbeiten/Duplizieren.
//   Recht: mentoring_notes.view (Lesen) / mentoring_notes.edit (Schreiben, POST
//   mit X-AIW-Token). Drag&Drop-Ordnung folgt in Block 4. Neuer Nav-Eintrag
//   'notes' (Gruppe Verwaltung) direkt neben 'mentoring'.
// Build 469: Schluesselumstellung user_id -> subject_id (M019)
// Build 479: SSE-Reload-Schutz fuer Lektorat (W4) und Chef-Freigabe (W5).
//   Beide Sichten schreiben beim Oeffnen eines Berichts ueber
//   /api/report/annotations einen Chain-of-Custody-Beleg in den audit_log
//   (Grundregel 1). Die SSE meldet diesen Ausschlag ~2s spaeter als 'changed';
//   der bisher folgende Reload verwarf die offene Auswahl + iframe-Vorschau
//   (gemeldeter Fehler, belegt). Der 'changed'-Handler unterdrueckt den Reload
//   nun, solange das jeweilige Modul via hasSelection() einen offenen Bericht
//   meldet. Ohne offene Auswahl wird wie bisher nachgeladen.
// Build 500: 'Meine Auftraege' reicht onLaunch durch -> POST /api/case/launch
//   startet den Forensik-Server (main.py) fuer einen zugewiesenen Fall; Erfolg/
//   Fehler als Banner (loadMyCases mit pendingMsg neu geladen).
// Build 502 (AD-Abgleich): Nav-Eintrag 'adsync' (personnel.sync) + loadAdSync
//   (Vorschau/apply/decide). BEWUSST ohne SSE-Auto-Reload: jeder Reload ist
//   eine Live-LDAP-Anfrage (siehe Kommentar an loadAdSync).
// Build 503 (Personalverwaltung): Nav-Eintrag 'personnel' (personnel.view)
//   ERSETZT 'adsync' — der AD-Abgleich ist jetzt LAZY-Abschnitt der
//   Personal-Seite (_adsyncInto, Wiederverwendung von AIWCockpitAdSync).
//   SSE-Reload laedt nur die Personenliste, nie den AD-Abschnitt.
// Version: v0.8.503 · Build: 503 · 2026-07-24
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
        // Kalender & Wiedervorlage (Build 386). Gruppe 'Ueberblick', weil die
        // Sicht BEIDE Rollen bedient: die Chefin sieht alle Faelligkeiten, der
        // Ermittler (Scope 'eigene') die seines Falls. Recht: external.view
        // (Backend-Vorgabe aus Build 385).
        { id: 'calendar',   cap: 'external.view',        group: 'Ueberblick',     label: 'Kalender & Wiedervorlage' },
        { id: 'assignment', cap: 'assignment.edit',      group: 'Verwaltung',     label: 'Zuweisung' },
        // Fall-Erkennung (Build 384): haengt an DERSELBEN Faehigkeit wie die
        // Zuweisung — das Backend (Build 383) schuetzt /api/cases/detect und
        // /api/cases/import mit 'assignment.edit' (Scope 'alle'). Wir fuehren
        // dafuer bewusst KEINE zweite Faehigkeit ein (mc 2026-07-12).
        { id: 'cases',      cap: 'assignment.edit',      group: 'Verwaltung',     label: 'Fall-Erkennung' },
        { id: 'mentoring',  cap: 'mentoring.view',       group: 'Verwaltung',     label: 'Ermittler-Betreuung' },
        // Betreuungs-Notizen ("Post-its", Build 406). Eigener Nav-Eintrag DIREKT
        // neben der Ermittler-Betreuung (abgestimmt mc 2026-07-13). Recht:
        // mentoring_notes.view. Privates Board pro Autor:in; Scope 'alle' sieht
        // fremde Boards (Backend-Vorgabe Build 401/405).
        { id: 'notes',      cap: 'mentoring_notes.view',  group: 'Verwaltung',     label: 'Betreuungs-Notizen' },
        // Berichts-Abnahme: 'reports.approve' ODER 'reports.review' genuegt
        // (wer freigeben darf, muss lesen duerfen). 'caps' = any-of; 'cap' bleibt
        // fuer den Scope-Tag/Platzhalter die Leitfaehigkeit.
        { id: 'reports',    cap: 'reports.approve',      caps: ['reports.approve', 'reports.review'], group: 'Verwaltung',     label: 'Berichts-Abnahme' },
        // Lektorat (W4, Build 413): Gegenlesen des Berichtstexts. 'caps' = any-of
        // (reports.review ODER reports.approve — die Chefin liest ebenfalls
        // gegen); Leitfaehigkeit fuer den Scope-Tag ist reports.review.
        { id: 'lectorate', cap: 'reports.review',       caps: ['reports.review', 'reports.approve'], group: 'Verwaltung',     label: 'Lektorat' },
        // Chef-Freigabe (W5, Build 416): Bericht lesen + Siegel pruefen +
        // freigeben/zurueckweisen. Recht reports.approve (Freigeben erfordert
        // serverseitig Scope 'alle').
        { id: 'approval',  cap: 'reports.approve',      group: 'Verwaltung',     label: 'Chef-Freigabe' },
        // Platzhalter & Queries (W2, Build 423): Autoren-Maske der Redakteur:in
        // fuer Einzeldaten-Platzhalter-Queries (templates.db). Eigene Gruppe
        // 'Redaktion', in der die weiteren Autoren-Werkzeuge (W1 Bausteine, W3
        // Dokumentvorlagen) folgen. Recht: templates.edit (Build 420).
        { id: 'templates', cap: 'templates.edit',       group: 'Redaktion',      label: 'Platzhalter & Queries' },
        // Dokumentvorlagen (W3, Build 425): Autoren-Maske der Redakteur:in fuer
        // wiederverwendbare Berichts-Gerueste (report_templates). Gleiche Gruppe
        // 'Redaktion' und gleiches Recht templates.edit wie W2.
        { id: 'doctemplates', cap: 'templates.edit',    group: 'Redaktion',      label: 'Dokumentvorlagen' },
        // Baustein-Module (W1, Build 427): Autoren-Maske der Redakteur:in fuer
        // wiederverwendbare Textbausteine (report_modules). Gleiche Gruppe
        // 'Redaktion' und Recht templates.edit wie W2/W3.
        { id: 'modules',   cap: 'templates.edit',       group: 'Redaktion',      label: 'Baustein-Module' },
        // Ermittlungsergebnis (Build 395). Recht: results.view. Ein Ermittler
        // mit Scope 'eigene' sieht die Sicht ebenfalls — er bekommt dann die
        // Abdeckung SEINER Faelle; die fallUEBERGREIFENDE Verteilung (/stats)
        // bleibt Scope 'alle' vorbehalten und wird in der Sicht BENANNT, statt
        // als leere Flaeche zu erscheinen.
        { id: 'results',    cap: 'results.view',         group: 'Auswertung',     label: 'Ermittlungsergebnis' },
        { id: 'stats',      cap: 'stats.export_sta',     group: 'Auswertung',     label: 'Statistiken (StA/Fuehrung)' },
        { id: 'planung',    cap: 'stats.export_sta',     group: 'Auswertung',     label: 'Prognose & Gantt' },
        { id: 'annostats',  cap: 'stats.export_sta',     group: 'Auswertung',     label: 'Annotations-Statistik' },
        { id: 'workload',   cap: 'workload.view',        group: 'Auswertung',     label: 'Lastverteilung' },
        { id: 'capacity',   cap: 'capacity.edit',        group: 'Auswertung',     label: 'Kapazitaet' },
        { id: 'support',    cap: 'support_history.view', group: 'Auswertung',     label: 'Support-Historie' },
        { id: 'mycases',    cap: 'mycases.view',         group: 'Persoenlich',    label: 'Meine Auftraege' },
        { id: 'myhistory',  cap: 'myhistory.view',       group: 'Persoenlich',    label: 'Meine Historie' },
        { id: 'policy',     cap: 'policy.view',          group: 'Administration', label: 'Rechte / Policy' },
        { id: 'integrity',  cap: 'ops.view',             group: 'Administration', label: 'Integritaet / Betrieb' },
        { id: 'audit',      cap: 'ops.view',             group: 'Administration', label: 'Audit-Explorer' },
        { id: 'promotion',  cap: 'ops.view',             group: 'Administration', label: 'Fremdforum-Promotion' },
        { id: 'releases',   cap: 'release.view',         group: 'Administration', label: 'Externe Fallfreigabe' },
        { id: 'onboarding', cap: 'onboarding.view',      group: 'Verwaltung',     label: 'Onboarding / Offboarding' },
        // Build 503: Personalverwaltung (personnel.view, Seed M021) ERSETZT
        // den separaten Eintrag 'adsync' aus Build 502 — der AD-Abgleich ist
        // jetzt ABSCHNITT der Personal-Seite (mc 2026-07-24: "Auf jener Seite
        // sollte dann auch die Einbindung sein"); sein Abschnitt erscheint
        // dort nur mit personnel.sync.
        { id: 'personnel',  cap: 'personnel.view',       group: 'Verwaltung',     label: 'Personalverwaltung' },
        // Build 471 (AP-2A(2b)): Katalog identifizierter Personen (Konto->reale
        // Person) mit Konfidenzstufe. Auswertungs-Sicht; Recht crossref.view.
        { id: 'crossref',   cap: 'crossref.view',        group: 'Auswertung',     label: 'Kreuzbezug' },
        // Build 478 (AP-2A(3)): Querfund-Meta-Uebersicht (rein lesend, Frontend
        // zu /api/crossfindings). Gleiche F5-Familie; Recht crossref.view.
        { id: 'crossfindings', cap: 'crossref.view',     group: 'Auswertung',     label: 'Querfunde' },
        // Build 505 (AP-2A/A1, Idee 8): globaler Alias-Katalog (Frontend zu
        // 504). EIGENE Sicht statt Anbau an 'crossref': Aliasse existieren
        // UNABHAENGIG vom Identitaetskatalog — ein Konto kann Aliasse und
        // KEINE Identifizierung haben; ein Anbau haette diese Faelle
        // unsichtbar gemacht (Grundregel 1). Gleiche F5-Familie, Recht
        // crossref.view (Pflegen zusaetzlich crossref.edit).
        { id: 'alias',      cap: 'crossref.view',        group: 'Auswertung',     label: 'Aliasse' }
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
        writeToken: null,
        // Build 475: Uebergabe eines aus einem Bericht erzeugten Vorlagen-
        // Entwurfs vom Lektorat an die Dokumentvorlagen-Sicht. {draft, findings,
        // warnings} oder null. Wird von loadDocTemplates EINMALIG konsumiert.
        pendingTemplateDraft: null
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
                        // Build 423: Fehlerantworten koennen eine strukturierte
                        // 'errors'-Liste tragen (z.B. Query-Validierung, W2).
                        // Diese hat Vorrang, damit ALLE konkreten Gruende sichtbar
                        // werden statt nur des Fehlercodes (Grundregel 1: kein
                        // stiller/unspezifischer Fehlschlag).
                        var detail = data.detail
                            || (data.errors && data.errors.length
                                ? data.errors.join('; ') : null)
                            || data.error || ('HTTP ' + r.status);
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
        // Drag&Drop-Handle der Betreuungs-Notizen abbauen (Build 407), damit
        // beim Sichtwechsel keine verwaisten Listener zuruueckbleiben.
        var notesMod = (typeof window !== 'undefined')
            ? window.AIWCockpitNotes : null;
        if (notesMod && typeof notesMod.cleanup === 'function') {
            notesMod.cleanup();
        }
        // Lektorat-Sicht (Build 413) abbauen (interne Referenzen loesen).
        var lectMod = (typeof window !== 'undefined')
            ? window.AIWCockpitLectorate : null;
        if (lectMod && typeof lectMod.cleanup === 'function') {
            lectMod.cleanup();
        }
        // Chef-Freigabe-Sicht (Build 416) abbauen.
        var apprMod = (typeof window !== 'undefined')
            ? window.AIWCockpitApproval : null;
        if (apprMod && typeof apprMod.cleanup === 'function') {
            apprMod.cleanup();
        }
        // Platzhalter/Query-Autorensicht (W2, Build 423) abbauen.
        var tplMod = (typeof window !== 'undefined')
            ? window.AIWCockpitTemplates : null;
        if (tplMod && typeof tplMod.cleanup === 'function') {
            tplMod.cleanup();
        }
        // Dokumentvorlagen-Autorensicht (W3, Build 425) abbauen.
        var dtplMod = (typeof window !== 'undefined')
            ? window.AIWCockpitDocTemplates : null;
        if (dtplMod && typeof dtplMod.cleanup === 'function') {
            dtplMod.cleanup();
        }
        // Baustein-Modul-Autorensicht (W1, Build 427) abbauen.
        var modMod = (typeof window !== 'undefined')
            ? window.AIWCockpitModules : null;
        if (modMod && typeof modMod.cleanup === 'function') {
            modMod.cleanup();
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
            // Fall-Fokus aus der Kommandopalette (Build 459): nach dem Rendern
            // zur gewaehlten Zeile springen und sie kurz hervorheben. Danach
            // zuruecksetzen, damit ein spaeterer Reload nicht erneut springt.
            if (state.focusCaseId !== null && state.focusCaseId !== undefined
                && typeof ov.focusCase === 'function') {
                ov.focusCase(state.table, state.focusCaseId);
                state.focusCaseId = null;
            }
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
    //
    // Build 500 (Fallstart aus dem Portal): reicht ein onLaunch-Callback durch.
    // Ein Klick auf "Fall starten" sendet POST /api/case/launch (auditfrei, kein
    // DB-Schreibzugriff — der Server prueft nur die Eigentuemerschaft und startet
    // den Forensik-Server main.py fuer den Fall). Erfolg/Fehler werden als Banner
    // ueber der Tabelle gezeigt; dazu wird die Sicht mit pendingMsg neu geladen.
    // opts.pendingMsg wird beim Reload EINMALIG angezeigt.
    function loadMyCases(mainEl, opts) {
        opts = opts || {};
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitMyCases : null;
        if (!mod) {
            renderError(mainEl, 'Modul "Meine Auftraege" nicht geladen.');
            return;
        }
        fetchJson('/api/mycases').then(function (data) {
            cleanupView();
            // Rueckmeldung eines Startversuchs in DERSELBEN Sicht neu laden.
            var reload = function (msg) {
                loadMyCases(mainEl, { pendingMsg: msg });
            };
            state.table = mod.renderMyCases(mainEl, data, {
                pendingMsg: opts.pendingMsg || null,
                onLaunch: function (subjectId) {
                    log('Fallstart angefordert fuer subject_id=', subjectId);
                    postJson('/api/case/launch', { subject_id: subjectId })
                        .then(function (r) {
                            reload({
                                text: 'Fall ' + subjectId + ' gestartet '
                                    + '(PID ' + (r && r.pid) + '). Der '
                                    + 'Forensik-Browser oeffnet sich in Kuerze.',
                                error: false
                            });
                        })
                        .catch(function (e) {
                            reload({
                                text: 'Fall ' + subjectId + ' konnte nicht '
                                    + 'gestartet werden: '
                                    + (e && e.message || e),
                                error: true
                            });
                        });
                }
            });
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

    // loadPlanung: Prognose & Gantt (cockpit_planung.js, Build 448). Holt BEIDE
    // read-only-Endpunkte (/api/forecast + /api/gantt) und rendert Szenario-
    // Tabelle + zwei ECharts. Die Charts wandern nach state.charts, damit
    // cleanupView sie beim Sichtwechsel entsorgt; je Chart ein Resize-Handler.
    function loadPlanung(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitPlanung : null;
        if (!mod) {
            renderError(mainEl, 'Planungs-Modul nicht geladen.');
            return;
        }
        Promise.all([fetchJson('/api/forecast'), fetchJson('/api/gantt')])
            .then(function (res) {
                cleanupView();
                var charts = mod.renderPlanung(
                    mainEl, { forecast: res[0], gantt: res[1] }, {}) || [];
                state.charts = charts;
                // Resize-Handler je Chart (in cleanupView via dispose entsorgt;
                // der Listener selbst wird ueber state.chartResize abgemeldet).
                state.chartResize = function () {
                    charts.forEach(function (c) {
                        try { c.resize(); } catch (e) { log('resize', e); }
                    });
                };
                window.addEventListener('resize', state.chartResize);
                log('Planung gerendert:', charts.length, 'Diagramm(e)');
            }).catch(function (err) {
                cleanupView();
                renderError(mainEl,
                    'Prognose/Gantt konnten nicht geladen werden: ' + err.message);
            });
    }

    // loadAnnostats: Annotations-Tortenstatistik (cockpit_annostats.js, Build
    // 450). Holt /api/annotation-stats und rendert zwei ECharts-Kreise
    // (Kategorie/Tag). Charts -> state.charts (cleanupView entsorgt); ein
    // Resize-Handler fuer beide.
    function loadAnnostats(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAnnostats : null;
        if (!mod) {
            renderError(mainEl, 'Annotations-Statistik-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/annotation-stats').then(function (data) {
            cleanupView();
            var charts = mod.renderAnnostats(mainEl, data, {}) || [];
            state.charts = charts;
            state.chartResize = function () {
                charts.forEach(function (c) {
                    try { c.resize(); } catch (e) { log('resize', e); }
                });
            };
            window.addEventListener('resize', state.chartResize);
            log('Annostats gerendert:', data.annotations_total, 'Annotationen');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Annotations-Statistik konnte nicht geladen werden: '
                + err.message);
        });
    }

    // loadNotes: Betreuungs-Notizen ("Post-its", Build 406). Laedt das Board
    // (/api/mentoring/notes, optional ?archived=1) und rendert das Pinboard
    // ueber das cockpit_notes-Modul. JEDE Schreibaktion (Anlegen/AEndern/
    // Archivieren/Wiederherstellen/Duplizieren) geht per POST an den
    // auditierten Schreibpfad; danach wird NEU GELADEN (kein optimistisches UI:
    // die Oberflaeche zeigt nur bestaetigt geschriebene Zustaende, Grundregel 1).
    // 'opts' traegt {archived, pendingMsg} durch den Reload hindurch, damit die
    // Archiv-Ansicht UND die Rueckmeldung nicht still verlorengehen.
    function loadNotes(mainEl, opts) {
        mainEl = mainEl || document.getElementById('aiw-main');
        opts = opts || {};
        var archived = opts.archived === true;
        // Aktuelle Ansicht (aktiv/Archiv) merken, damit der SSE-Reload sie
        // beibehaelt und nicht still ins aktive Board zurueckspringt.
        state.notesArchived = archived;
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitNotes : null;
        if (!mod) {
            renderError(mainEl, 'Betreuungs-Notizen-Modul nicht geladen.');
            return;
        }
        var url = '/api/mentoring/notes' + (archived ? '?archived=1' : '');
        fetchJson(url).then(function (data) {
            cleanupView();
            // Der Reload nach einem Schreibvorgang bleibt in derselben
            // Ansicht (aktiv/Archiv). Alle Callbacks fuehren ueber postJson und
            // laden dieselbe Ansicht neu; die Rueckmeldung wird mitgetragen.
            var reload = function (msg) {
                loadNotes(mainEl, { archived: archived, pendingMsg: msg });
            };
            var fail = function (err) {
                return function (e) {
                    log('Notiz-Schreibfehler', e);
                    reload({ text: 'Fehler: ' + (e && e.message || e),
                             error: true });
                };
            };
            mod.renderNotes(mainEl, data, {
                archived: archived,
                pendingMsg: opts.pendingMsg || null,
                // Ansicht wechseln (aktiv <-> Archiv) — reiner Lesewechsel.
                onToggleArchived: function (toArchived) {
                    loadNotes(mainEl, { archived: toArchived });
                },
                onCreate: function (body) {
                    postJson('/api/mentoring/note/create', body)
                        .then(function (r) {
                            reload({ text: 'Angelegt (Beleg #' + r.audit_seq
                                     + ').', error: false });
                        }).catch(fail());
                },
                onUpdate: function (body) {
                    postJson('/api/mentoring/note/update', body)
                        .then(function (r) {
                            reload({ text: 'Gespeichert (Beleg #' + r.audit_seq
                                     + ').', error: false });
                        }).catch(fail());
                },
                onArchive: function (id) {
                    postJson('/api/mentoring/note/archive', { id: id })
                        .then(function (r) {
                            reload({ text: 'Archiviert (Beleg #' + r.audit_seq
                                     + ').', error: false });
                        }).catch(fail());
                },
                onRestore: function (id) {
                    postJson('/api/mentoring/note/restore', { id: id })
                        .then(function (r) {
                            reload({ text: 'Wiederhergestellt (Beleg #'
                                     + r.audit_seq + ').', error: false });
                        }).catch(fail());
                },
                onDuplicate: function (id) {
                    postJson('/api/mentoring/note/duplicate', { id: id })
                        .then(function (r) {
                            reload({ text: 'Dupliziert (Beleg #' + r.audit_seq
                                     + ').', error: false });
                        }).catch(fail());
                },
                // Drag&Drop/Pfeil-Ordnung (Build 407): EIN gebuendelter
                // Reorder-Beleg pro Ablegen. req = {owner_id, ids}.
                onReorder: function (req) {
                    postJson('/api/mentoring/note/reorder', req)
                        .then(function (r) {
                            reload({ text: 'Reihenfolge gespeichert (Beleg #'
                                     + r.audit_seq + ').', error: false });
                        }).catch(fail());
                }
            });
            log('Betreuungs-Notizen gerendert:',
                (data.notes || []).length, 'Notizen', archived ? '(Archiv)' : '');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Betreuungs-Notizen konnten nicht geladen werden: '
                + err.message);
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
                onChange: function (kind, subjectId, value) {
                    var req = mod.changeRequest(kind, subjectId, value);
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
                // Rueckgabe zur Nachbesserung: Lektor (reports.review) ODER
                // Chefin (reports.approve — impliziert review).
                canReview: hasCap(state.capabilities, 'reports.review'),

                // FREIGABE (Schreibpfad, Build 377): POST mit Schreib-Token.
                // Danach NEU LADEN — die Sicht zeigt nur bestaetigt
                // geschriebene Zustaende (kein optimistisches UI).
                onApprove: function (subjectId, reportId, isFinal) {
                    postJson('/api/report/approve', {
                        subject_id: subjectId, report_id: reportId,
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

                // RUECKGABE zur Nachbesserung (Build 380): submitted -> draft.
                onReturn: function (subjectId, reportId) {
                    postJson('/api/report/return', {
                        subject_id: subjectId, report_id: reportId
                    }).then(function (res) {
                        loadReports(mainEl, false, {
                            text: 'Zur Nachbesserung zurueckgegeben (Beleg #'
                                + res.audit_seq + '). Der Autor kann den '
                                + 'Bericht wieder bearbeiten.',
                            error: false
                        });
                    }).catch(function (err) {
                        log('Rueckgabe-Fehler', err);
                        if (t && t.aiwSetResult) {
                            t.aiwSetResult('Fehler: ' + err.message, true);
                        }
                    });
                },

                // SIEGELPRUEFUNG (lesend): Hash neu bilden und vergleichen.
                onVerify: function (subjectId, reportId) {
                    fetchJson('/api/report/verify?subject_id=' + subjectId
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

    // loadResultsView: ERMITTLUNGSERGEBNIS (Build 395, Frontend zu 387/393).
    //
    //   GET /api/results/coverage -> Abdeckung JE FALL (auch nie bewertete)
    //   GET /api/results/stats    -> Verteilung je Kriterium
    //
    //   Die Statistik ist Scope 'alle' vorbehalten. Ein Ermittler mit 'eigene'
    //   bekommt dort 403 — das ist KEIN Fehler, sondern die Kapselung. Die
    //   Sicht faengt das ab und BENENNT es (statt eine leere Flaeche zu
    //   zeigen); die Abdeckung seiner eigenen Faelle sieht er vollstaendig.
    //   Deshalb darf ein Statistik-Fehler den GANZEN Aufbau nicht abbrechen.
    function loadResultsView(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitResults : null;
        if (!mod) {
            renderError(mainEl, 'Ergebnis-Modul nicht geladen.');
            return;
        }

        fetchJson('/api/results/coverage').then(function (cov) {
            return fetchJson('/api/results/stats')
                .then(function (st) { return { cov: cov, stats: st }; })
                .catch(function (err) {
                    log('Statistik nicht verfuegbar:', err.message);
                    return { cov: cov, stats: null };
                });
        }).then(function (both) {
            cleanupView();
            var res = mod.renderResults(mainEl, both.cov, both.stats, {})
                || { charts: [] };
            state.table = res.table || null;
            state.charts = res.charts || [];
            log('Ergebnis-Sicht gerendert:', both.cov.faelle_gesamt, 'Faelle,',
                both.cov.nie_bewertet, 'nie bewertet');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Ergebnis-Auswertung konnte nicht geladen werden: '
                + err.message);
        });
    }

    // loadCalendar: KALENDER & WIEDERVORLAGE (Build 386, Frontend zu 385).
    //
    //   ZWEI Abrufe, EINE Sicht:
    //     GET /api/calendar?von=&bis=  -> Monatsraster (externe Vorgaenge +
    //                                     Abwesenheiten + Feiertage)
    //     GET /api/external            -> Faelligkeitsliste + Arbeitsvorrat
    //   Beide muessen DENSELBEN Stichtag verwenden, sonst koennten Raster und
    //   Liste unterschiedliche Ampeln zeigen. Der Server bestimmt den Stichtag
    //   (Europe/Berlin); wir uebernehmen ihn aus der Kalender-Antwort und
    //   geben ihn der Vorgangsliste ausdruecklich mit.
    //
    //   KEIN optimistisches UI: jeder Schreibvorgang laedt beide Abrufe neu.
    function loadCalendar(mainEl, ym, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCalendar : null;
        if (!mod) {
            renderError(mainEl, 'Kalender-Modul nicht geladen.');
            return;
        }

        // Ohne Monatsangabe: der laufende Monat (Stichtag des Servers).
        ym = ym || state.calYm || mod.ymOf(new Date().toISOString().slice(0, 10));
        state.calYm = ym;
        var r = mod.monthRange(ym);

        fetchJson('/api/calendar?von=' + r.von + '&bis=' + r.bis)
            .then(function (cal) {
                // Vorgangsliste mit DEMSELBEN Stichtag abrufen.
                return fetchJson('/api/external?stichtag=' + cal.stichtag)
                    .then(function (ext) { return { cal: cal, ext: ext }; });
            })
            .then(function (both) {
                cleanupView();
                var canEdit = hasCap(state.capabilities, 'external.edit');

                function after(text, isError) {
                    loadCalendar(mainEl, ym, { text: text, error: isError });
                }
                function fail(err) {
                    // Der Fehler wird NICHT verschluckt; danach wird der
                    // TATSAECHLICHE Stand neu geladen.
                    log('Schreibfehler', err);
                    after('Fehler: ' + err.message + ' (es wurde nichts oder '
                          + 'nur ein Teil geschrieben \u2014 die Liste zeigt '
                          + 'den tatsaechlichen Stand).', true);
                }

                var view = mod.renderCalendar(mainEl, both.cal, both.ext, {
                    ym: ym,
                    canEdit: canEdit,
                    onMonth: function (neu) { loadCalendar(mainEl, neu); },

                    onCreate: function (body) {
                        postJson('/api/external/create', body)
                            .then(function (res) {
                                after('Vorgang ' + res.matter_id
                                      + ' angelegt (Beleg #' + res.audit_seq
                                      + ').', false);
                            }).catch(fail);
                    },
                    onDefer: function (body) {
                        postJson('/api/external/defer', body)
                            .then(function (res) {
                                after('Wiedervorlage verschoben auf '
                                      + body.wiedervorlage_am + ' (Beleg #'
                                      + res.audit_seq + ').', false);
                            }).catch(fail);
                    },
                    onAnswer: function (body) {
                        postJson('/api/external/answer', body)
                            .then(function (res) {
                                after('Antwort erfasst (Beleg #'
                                      + res.audit_seq + '). Der Vorgang bleibt '
                                      + 'in der Wiedervorlage, bis er '
                                      + 'ausgewertet ist.', false);
                            }).catch(fail);
                    },
                    onClose: function (body) {
                        postJson('/api/external/close', body)
                            .then(function (res) {
                                after('Vorgang ' + body.matter_id
                                      + ' ENDGUELTIG abgeschlossen ('
                                      + body.status + ', Beleg #'
                                      + res.audit_seq + ').', false);
                            }).catch(fail);
                    }
                });

                state.table = view && view.table;
                if (view && pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Kalender', ym, 'gerendert:', both.cal.count,
                    'Eintraege,', both.ext.count, 'Vorgaenge');
            })
            .catch(function (err) {
                cleanupView();
                renderError(mainEl,
                    'Kalender konnte nicht geladen werden: ' + err.message);
            });
    }

    // loadCases: FALL-ERKENNUNG (Build 384, Frontend zu 383).
    //   GET  /api/cases/detect  — rein lesender Abgleich Platte <-> Fallakte.
    //   POST /api/cases/import  — auditierte Aufnahme der AUSGEWAEHLTEN Faelle.
    // Wie bei der Zuweisung gilt: KEIN optimistisches UI. Nach dem Schreiben
    // wird neu geladen; die Rueckmeldung (Erfolg ODER Fehler ODER uebersprungene
    // Faelle) wird ueber 'pendingMsg' durch den Reload getragen, damit sie nicht
    // still verloren geht (Grundregel 1).
    function loadCases(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCases : null;
        if (!mod) {
            renderError(mainEl, 'Fall-Erkennungs-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/cases/detect').then(function (data) {
            cleanupView();
            var view = mod.renderCases(mainEl, data, {
                onImport: function (ids) {
                    var req = mod.importRequest(ids);
                    if (!req) {
                        if (view) {
                            view.setResult('Kein Fall ausgewaehlt.', true);
                        }
                        return;
                    }
                    postJson(req.path, req.body).then(function (res) {
                        // Serverantwort NICHT selbst deuten, sondern woertlich
                        // wiedergeben (imported MIT Beleg-Nr., skipped MIT
                        // Grund) — und dann den echten Zustand neu laden.
                        var r = mod.resultText(res);
                        loadCases(mainEl, { text: r.text, error: r.error });
                    }).catch(function (err) {
                        log('Aufnahme-Fehler', err);
                        loadCases(mainEl, {
                            text: 'Fehler bei der Aufnahme: ' + err.message
                                + ' (es wurde nichts oder nur ein Teil '
                                + 'geschrieben \u2014 die Liste oben zeigt den '
                                + 'tatsaechlichen Stand).',
                            error: true
                        });
                    });
                }
            });
            state.table = view && view.table;
            if (view && pendingMsg) {
                view.setResult(pendingMsg.text, pendingMsg.error);
            }
            log('Fall-Erkennung gerendert:', data.count, 'Faelle,',
                data.counts);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Fall-Erkennung konnte nicht geladen werden: ' + err.message);
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

    // loadPromotion: FREMDFORUM-PROMOTION (Build 461, Frontend zu 460).
    //   GET  /api/promotion          — Kandidaten (forensic da, evidence fehlt)
    //                                  + ihr Promotions-Zustand (read, ops.view).
    //   POST /api/promotion/decide   — auditierte Entscheidung (ops.promote).
    // Wie ueberall gilt: KEIN optimistisches UI. Nach dem Schreiben wird die
    // Sicht NEU geladen; die Rueckmeldung (Erfolg ODER Fehler) wird ueber
    // 'pendingMsg' durch den Reload getragen, damit sie nicht still verloren
    // geht (Grundregel 1). Der Kandidaten-Scan misst die PLATTE — nach einem
    // Ereignis (SSE 'changed') kann sich der Bestand aendern -> neu messen.
    function loadPromotion(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitPromotion : null;
        if (!mod) {
            renderError(mainEl, 'Promotions-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/promotion').then(function (data) {
            cleanupView();
            var canEdit = hasCap(state.capabilities, 'ops.promote');

            function after(text, isError) {
                loadPromotion(mainEl, { text: text, error: isError });
            }

            var view = mod.renderPromotion(mainEl, data, {
                canEdit: canEdit,
                onDecide: function (body) {
                    postJson('/api/promotion/decide', body)
                        .then(function (res) {
                            after('Kandidat ' + res.subject_id + ': ' + res.von
                                + ' → ' + res.auf + ' (Beleg #'
                                + res.audit_seq + ').', false);
                        })
                        .catch(function (err) {
                            // Der Fehler wird NICHT verschluckt; danach wird der
                            // TATSAECHLICHE Stand neu geladen.
                            after('Fehler: ' + err.message + ' (es wurde nichts '
                                + 'geschrieben — die Liste zeigt den '
                                + 'tatsaechlichen Stand).', true);
                        });
                }
            });

            if (view && pendingMsg) {
                view.setResult(pendingMsg.text, pendingMsg.error);
            }
            log('Promotion gerendert:', data.candidate_count, 'Kandidat(en)');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Fremdforum-Promotion konnte nicht geladen werden: '
                + err.message);
        });
    }

    // loadReleases: EXTERNE FALLFREIGABE (Build 463, Frontend zu 462).
    //   GET  /api/releases         — Freigaben + berechtigte Empfaenger (F4) +
    //                                Umfang-Katalog (read, release.view).
    //   POST /api/release/grant    — Fall freigeben (release.grant, auditiert).
    //   POST /api/release/revoke   — Freigabe widerrufen (release.grant).
    // KEIN optimistisches UI: nach dem Schreiben Reload; die Rueckmeldung
    // (Erfolg/Fehler) wird ueber 'pendingMsg' durch den Reload getragen (GR1).
    function loadReleases(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitReleases : null;
        if (!mod) {
            renderError(mainEl, 'Freigabe-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/releases').then(function (data) {
            cleanupView();
            var canEdit = hasCap(state.capabilities, 'release.grant');

            function after(text, isError) {
                loadReleases(mainEl, { text: text, error: isError });
            }
            function fail(err) {
                after('Fehler: ' + err.message + ' (es wurde nichts '
                    + 'geschrieben — die Liste zeigt den tatsaechlichen '
                    + 'Stand).', true);
            }

            var view = mod.renderReleases(mainEl, data, {
                canEdit: canEdit,
                onGrant: function (body) {
                    postJson('/api/release/grant', body)
                        .then(function (res) {
                            after('Fall ' + body.subject_id + ' an '
                                + res.recipient_display + ' freigegeben '
                                + '(Freigabe ' + res.release_id + ', Beleg #'
                                + res.audit_seq + ').', false);
                        }).catch(fail);
                },
                onRevoke: function (body) {
                    postJson('/api/release/revoke', body)
                        .then(function (res) {
                            after('Freigabe ' + body.release_id + ' widerrufen '
                                + '(Beleg #' + res.audit_seq + ').', false);
                        }).catch(fail);
                }
            });

            if (view && pendingMsg) {
                view.setResult(pendingMsg.text, pendingMsg.error);
            }
            log('Freigaben gerendert:', data.count, 'Eintraege');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Externe Fallfreigaben konnten nicht geladen werden: '
                + err.message);
        });
    }

    // loadOnboarding: ONBOARDING/OFFBOARDING (Build 465, Frontend zu 464).
    //   GET  /api/onboarding?person_id=&kind=  — Checkliste + Fall-Last (read,
    //                                            onboarding.view).
    //   POST /api/onboarding/step              — Schritt setzen (onboarding.edit).
    // Die gewaehlte Person/Art lebt NUR im State (kein localStorage — Projekt-
    // regel), damit SSE-Reloads dieselbe Sicht neu laden. KEIN optimistisches UI.
    function loadOnboarding(mainEl, personId, kind, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitOnboarding : null;
        if (!mod) {
            renderError(mainEl, 'Onboarding-Modul nicht geladen.');
            return;
        }
        var pid = (personId != null) ? personId : state.onbPerson;
        var k = kind || state.onbKind || 'onboarding';
        state.onbPerson = (pid != null) ? pid : null;
        state.onbKind = k;

        var view = null;
        function after(text, isError) {
            loadOnboarding(mainEl, pid, k, { text: text, error: isError });
        }
        var opts = {
            canEdit: hasCap(state.capabilities, 'onboarding.edit'),
            personId: pid, kind: k,
            onLoad: function (sel) {
                loadOnboarding(mainEl, sel.personId, sel.kind);
            },
            onInvalid: function (msg) { if (view) { view.setResult(msg, true); } },
            onStep: function (body) {
                postJson('/api/onboarding/step', body)
                    .then(function (res) {
                        after('Schritt „' + body.step_code + '“ → '
                            + res.status + ' (Beleg #' + res.audit_seq + ').',
                            false);
                    })
                    .catch(function (err) {
                        after('Fehler: ' + err.message + ' (es wurde nichts '
                            + 'geschrieben — die Liste zeigt den tatsaechlichen '
                            + 'Stand).', true);
                    });
            }
        };

        // Noch keine Person gewaehlt -> nur die Auswahl (kein GET).
        if (pid == null) {
            cleanupView();
            view = mod.renderOnboarding(mainEl, null, opts);
            if (pendingMsg) { view.setResult(pendingMsg.text, pendingMsg.error); }
            return;
        }

        fetchJson('/api/onboarding?person_id=' + encodeURIComponent(pid)
                + '&kind=' + encodeURIComponent(k))
            .then(function (data) {
                cleanupView();
                view = mod.renderOnboarding(mainEl, data, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Onboarding gerendert:', data.person_id, k);
            })
            .catch(function (err) {
                cleanupView();
                // Trotz Fehler die Auswahl zeigen, damit man korrigieren kann.
                view = mod.renderOnboarding(mainEl, null, opts);
                view.setResult('Konnte nicht geladen werden: ' + err.message,
                    true);
            });
    }

    // loadPersonnel: PERSONALVERWALTUNG (Build 503; ersetzt die separate
    //   AD-Abgleich-Sicht aus Build 502 — der Abgleich ist jetzt Abschnitt).
    //   GET  /api/personnel               — Liste (read, personnel.view,
    //                                       KEIN AD-Zugriff).
    //   POST /api/personnel/flags         — Rollen-Flag setzen (personnel.edit).
    //   POST /api/personnel/role/assign   — Rolle zuweisen (personnel.edit).
    //   POST /api/personnel/role/revoke   — Zuweisung widerrufen (Soft-Revoke).
    //   AD-Abschnitt (personnel.sync): LAZY via _adsyncInto — /api/adsync wird
    //   erst auf Nutzerhandlung geholt (Live-LDAP). Nach einer AD-Aktion wird
    //   die Sicht MIT offenem Abschnitt neu geladen (genau EIN frischer
    //   LDAP-Abruf nach eigener Aktion); der SSE-Reload laedt NUR die Liste.
    //   KEIN optimistisches UI: nach jedem Schreiben wird neu geladen.
    function loadPersonnel(mainEl, pendingMsg, adsyncOpen) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitPersonnel : null;
        if (!mod) {
            renderError(mainEl, 'Personalverwaltungs-Modul nicht geladen.');
            return;
        }
        var view = null;
        function after(text, isError, keepAdsync) {
            loadPersonnel(mainEl, { text: text, error: isError },
                keepAdsync === true);
        }
        // _post: gemeinsame Schreib-Huelle der Listen-Aktionen. Fehler laden
        // die Sicht ebenfalls neu — die Liste zeigt danach den tatsaechlichen
        // Stand (es wurde nichts geschrieben).
        function _post(url, body, okText) {
            postJson(url, body)
                .then(function (res) { after(okText(res), false, false); })
                .catch(function (err) {
                    after('Fehler: ' + err.message + ' (es wurde nichts '
                        + 'geschrieben — die Liste zeigt den tatsaechlichen '
                        + 'Stand).', true, false);
                });
        }
        var opts = {
            adsyncOpen: adsyncOpen === true,
            onFlags: function (body) {
                _post('/api/personnel/flags', body, function (res) {
                    return 'Flags aktualisiert (Beleg #' + res.audit_seq
                        + ').';
                });
            },
            onAssign: function (body) {
                _post('/api/personnel/role/assign', body, function (res) {
                    return 'Rolle ' + res.role_code + ' zugewiesen (Beleg #'
                        + res.audit_seq + ').';
                });
            },
            onRevoke: function (body) {
                _post('/api/personnel/role/revoke', body, function (res) {
                    return 'Zuweisung widerrufen (Soft-Revoke, Beleg #'
                        + res.audit_seq + ').';
                });
            },
            onAdsyncLoad: function (box, setResult) {
                _adsyncInto(box, setResult, after);
            }
        };
        fetchJson('/api/personnel')
            .then(function (data) {
                cleanupView();
                view = mod.renderPersonnel(mainEl, data, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Personalverwaltung gerendert:',
                    (data.persons || []).length, 'Personen');
            })
            .catch(function (err) {
                cleanupView();
                renderError(mainEl, 'Personalverwaltung konnte nicht '
                    + 'geladen werden: ' + err.message);
            });
    }

    // _adsyncInto: laedt die AD-Vorschau (/api/adsync) in den Abschnitts-
    //   Container der Personal-Seite und verdrahtet die Vollzugs-Callbacks
    //   der WIEDERVERWENDETEN Komponente AIWCockpitAdSync (Build 502).
    //   after(text, isError, keepAdsync=true) laedt die GANZE Sicht neu und
    //   oeffnet den AD-Abschnitt wieder (frische Vorschau nach eigener Aktion).
    function _adsyncInto(containerEl, setResult, after) {
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAdSync : null;
        if (!mod) {
            setResult('AD-Abgleich-Modul nicht geladen.', true);
            return;
        }
        var sub = null;
        fetchJson('/api/adsync')
            .then(function (data) {
                sub = mod.renderAdSync(containerEl, data, {
                    onApply: function () {
                        postJson('/api/adsync/apply', {})
                            .then(function (res) {
                                after(res.created.length + ' Neuaufnahmen, '
                                    + res.renamed.length
                                    + ' Namensaenderungen vollzogen '
                                    + '(Lauf-Beleg #' + res.run_seq + ').',
                                    false, true);
                            })
                            .catch(function (err) {
                                after('Fehler: ' + err.message + ' (es wurde '
                                    + 'ggf. nur ein Teil vollzogen — die '
                                    + 'Sicht zeigt den tatsaechlichen '
                                    + 'Stand).', true, true);
                            });
                    },
                    onDecide: function (body) {
                        postJson('/api/adsync/decide', body)
                            .then(function (res) {
                                var verb = { deactivate: 'deaktiviert (nur '
                                        + 'inaktiv, nicht geloescht)',
                                    abort: 'Abbruch protokolliert',
                                    reactivate: 'reaktiviert' }[res.action]
                                    || res.action;
                                after(res.system_username + ': ' + verb
                                    + ' (Beleg #' + res.audit_seq + ').',
                                    false, true);
                            })
                            .catch(function (err) {
                                // Falsches Wort/Fachfehler: NICHT neu laden
                                // (Eingaben erhalten), nur Ergebniszeile.
                                if (sub) {
                                    sub.setResult('Nicht vollzogen: '
                                        + err.message, true);
                                }
                            });
                    }
                });
                log('AD-Abschnitt gerendert:', data.counts);
            })
            .catch(function (err) {
                setResult('AD-Vorschau konnte nicht geladen werden: '
                    + err.message, true);
            });
    }

    // loadCrossref: KREUZBEZUG — Katalog identifizierter Personen (Build 471,
    //   AP-2A(2b), Frontend zu 470).
    //   GET  /api/crossref            — Katalog (read, crossref.view).
    //   POST /api/crossref/set        — Zuordnung anlegen/revidieren
    //                                   (crossref.edit). KEIN optimistisches UI:
    //                                   nach dem Schreiben Sicht NEU laden.
    function loadCrossref(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCrossref : null;
        if (!mod) {
            renderError(mainEl, 'Kreuzbezug-Modul nicht geladen.');
            return;
        }

        var view = null;
        function after(text, isError) {
            loadCrossref(mainEl, { text: text, error: isError });
        }
        var opts = {
            canEdit: hasCap(state.capabilities, 'crossref.edit'),
            onSet: function (body) {
                postJson('/api/crossref/set', body)
                    .then(function (res) {
                        var was = res.created ? 'angelegt' : 'revidiert';
                        after('Zuordnung subject_id ' + body.subject_id + ' '
                            + was + ' → ' + res.confidence_code
                            + ' (Beleg #' + res.audit_seq + ').', false);
                    })
                    .catch(function (err) {
                        after('Fehler: ' + err.message + ' (es wurde nichts '
                            + 'geschrieben — die Liste zeigt den tatsaechlichen '
                            + 'Stand).', true);
                    });
            }
        };

        fetchJson('/api/crossref')
            .then(function (data) {
                cleanupView();
                view = mod.renderCrossref(mainEl, data, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Kreuzbezug gerendert:',
                    (data && data.entries ? data.entries.length : 0));
            })
            .catch(function (err) {
                cleanupView();
                view = mod.renderCrossref(mainEl, { entries: [] }, opts);
                view.setResult('Konnte nicht geladen werden: ' + err.message,
                    true);
            });
    }

    // loadCrossfindings: QUERFUND-META-UEBERSICHT (Build 478, AP-2A(3), Frontend
    //   zu 474). REIN LESEND. GET /api/crossfindings (Recht crossref.view;
    //   optional ?only_open=1). KEIN SSE-Refresh — Querfunde entstehen ueber die
    //   automatische forensic_api-Pipeline, nicht ueber den audit_log; ein SSE-
    //   Trigger wuerde nicht feuern. Stattdessen manuelles „Aktualisieren".
    //   503 (Substrat fehlt) -> Fehlerzustand, KEINE leere Liste (Grundregel 1).
    function loadCrossfindings(mainEl, onlyOpen) {
        mainEl = mainEl || document.getElementById('aiw-main');
        onlyOpen = onlyOpen === true;
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitCrossfindings : null;
        if (!mod) {
            renderError(mainEl, 'Querfunde-Modul nicht geladen.');
            return;
        }

        var opts = {
            onlyOpen: onlyOpen,
            onReload: function (next) {
                // State merken, damit ein View-Wechsel den Filter beibehaelt.
                state.cfOnlyOpen = (next === true);
                loadCrossfindings(mainEl, state.cfOnlyOpen);
            }
        };
        var url = '/api/crossfindings' + (onlyOpen ? '?only_open=1' : '');

        fetchJson(url)
            .then(function (data) {
                cleanupView();
                mod.renderCrossfindings(mainEl, data, opts);
                log('Querfunde gerendert:',
                    (data && data.findings ? data.findings.length : 0));
            })
            .catch(function (err) {
                // Auch 503 landet hier — als Fehlerzustand anzeigen, NICHT leer.
                cleanupView();
                mod.renderCrossfindings(mainEl, { error: err.message }, opts);
            });
    }

    // loadAlias: GLOBALER ALIAS-KATALOG (Build 505, AP-2A/A1, Frontend zu 504).
    //   GET  /api/alias                    — Katalog / ?q= Rueckwaertssuche /
    //                                        ?subject_id=N / ?include_retracted=1
    //   POST /api/alias/add|update|retract|reinstate  (crossref.edit)
    //   KEIN optimistisches UI: nach jedem Schreiben wird die Sicht NEU geladen,
    //   damit auch ein serverseitig ABGELEHNTER Schreibversuch (Duplikat,
    //   fehlender Grund) den tatsaechlichen Stand zeigt.
    //   SSE-Refresh ist hier RICHTIG (anders als bei 'crossfindings'): Alias-
    //   Aenderungen laufen ueber den coordinator-audit_log, der Strom feuert.
    //   Such-/Filterzustand lebt im State (kein localStorage), damit ein
    //   SSE-Reload oder ein View-Wechsel dieselbe Sicht wiederherstellt.
    function loadAlias(mainEl, pendingMsg) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAlias : null;
        if (!mod) {
            renderError(mainEl, 'Alias-Modul nicht geladen.');
            return;
        }

        var query = state.aliasQuery || '';
        var inclRetr = state.aliasInclRetracted === true;
        var view = null;
        function after(text, isError) {
            loadAlias(mainEl, { text: text, error: isError });
        }
        function fail(err) {
            after('Fehler: ' + err.message + ' (es wurde nichts geschrieben — '
                + 'die Liste zeigt den tatsaechlichen Stand).', true);
        }

        var opts = {
            canEdit: hasCap(state.capabilities, 'crossref.edit'),
            query: query,
            includeRetracted: inclRetr,
            onSearch: function (term) {
                state.aliasQuery = String(term || '').trim();
                loadAlias(mainEl);
            },
            onToggleRetracted: function (next) {
                state.aliasInclRetracted = (next === true);
                loadAlias(mainEl);
            },
            onAdd: function (body) {
                postJson('/api/alias/add', body)
                    .then(function (res) {
                        after('Alias erfasst (Eintrag #' + res.alias_id
                            + ', Beleg #' + res.audit_seq + ').', false);
                    })
                    .catch(fail);
            },
            onUpdate: function (body) {
                postJson('/api/alias/update', body)
                    .then(function (res) {
                        after('Eintrag #' + res.alias_id + ' geändert '
                            + '(Beleg #' + res.audit_seq + ').', false);
                    })
                    .catch(fail);
            },
            onRetract: function (body) {
                postJson('/api/alias/retract', body)
                    .then(function (res) {
                        after('Eintrag #' + res.alias_id + ' widerrufen '
                            + '(Beleg #' + res.audit_seq + '). Die Zeile '
                            + 'bleibt als Beleg erhalten.', false);
                    })
                    .catch(fail);
            },
            onReinstate: function (body) {
                postJson('/api/alias/reinstate', body)
                    .then(function (res) {
                        after('Widerruf von Eintrag #' + res.alias_id
                            + ' zurückgenommen (Beleg #' + res.audit_seq
                            + ').', false);
                    })
                    .catch(fail);
            }
        };

        // Die Suchmaske ist bewusst EIN Feld: eine reine Zahl wird als Konto
        // gelesen, alles andere als Name. Zwei getrennte Felder haetten die
        // Ermittlerin bei jeder Suche zu einer Entscheidung gezwungen, die das
        // Werkzeug selbst treffen kann.
        var url = '/api/alias';
        var params = [];
        if (query) {
            params.push(/^\d+$/.test(query)
                ? ('subject_id=' + encodeURIComponent(query))
                : ('q=' + encodeURIComponent(query)));
        }
        if (inclRetr) { params.push('include_retracted=1'); }
        if (params.length) { url += '?' + params.join('&'); }

        fetchJson(url)
            .then(function (data) {
                cleanupView();
                view = mod.renderAlias(mainEl, data, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
                log('Aliasse gerendert:',
                    (data && data.entries ? data.entries.length : 0));
            })
            .catch(function (err) {
                // Ladefehler als FEHLER anzeigen, nicht als leeren Katalog.
                cleanupView();
                view = mod.renderAlias(mainEl, { error: err.message }, opts);
                if (pendingMsg) {
                    view.setResult(pendingMsg.text, pendingMsg.error);
                }
            });
    }

    // loadAudit: AUDIT-/REVISIONS-EXPLORER (Build 467, AP-2E). REIN LESEND.
    //   GET /api/audit/facets  — Filter-Auswahl (Event-Typen + Akteure).
    //   GET /api/audit         — gefilterte, paginierte Seite.
    //   Der "Gerichtsfeste Export" ist ein Link auf /api/audit/export mit den
    //   ANGEWANDTEN Filtern. Filter/Offset leben im State (kein localStorage),
    //   damit ein SSE-Reload dieselbe Sicht wiederherstellt.
    function loadAudit(mainEl, filters, offset) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitAudit : null;
        if (!mod) {
            renderError(mainEl, 'Audit-Modul nicht geladen.');
            return;
        }
        var f = filters || state.auditFilters || {};
        var off = (offset != null) ? offset : (state.auditOffset || 0);
        state.auditFilters = f;
        state.auditOffset = off;

        var qs = mod.buildQuery(f, { limit: 50, offset: off });
        // Facetten und Seite parallel; Facetten-Fehler darf die Sicht nicht
        // blockieren (dann eben ohne Vorauswahl-Listen).
        fetchJson('/api/audit/facets')
            .catch(function () { return { event_types: [], actors: [] }; })
            .then(function (facets) {
                return fetchJson('/api/audit?' + qs)
                    .then(function (data) { return { facets: facets, data: data }; });
            })
            .then(function (both) {
                cleanupView();
                mod.renderAudit(mainEl, both.data, both.facets, {
                    filters: f,
                    onFilter: function (nf) { loadAudit(mainEl, nf, 0); },
                    onPage: function (newOff) { loadAudit(mainEl, f, newOff); }
                });
                log('Audit gerendert:', both.data.total, 'Treffer');
            })
            .catch(function (err) {
                cleanupView();
                renderError(mainEl,
                    'Audit-Explorer konnte nicht geladen werden: '
                    + err.message);
            });
    }

    // loadLectorate: LEKTORAT (W4, Build 413, Slice 1). Laedt die Berichtsliste
    // (/api/reports, scope-korrekt serverseitig) und rendert die Gegenlese-
    // Sicht: Auswahl + read-only Berichtstext-Vorschau (<iframe> auf
    // /api/report/render, SF-1). Annotationen (SF-2) und Kommentare (SF-3)
    // folgen in den naechsten Slices (Build 414/415).
    function loadLectorate(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitLectorate : null;
        if (!mod) {
            renderError(mainEl, 'Lektorat-Modul nicht geladen.');
            return;
        }
        // reloadComments (Build 415): Kommentare (Union, SF-3) laden und
        // rendern. Nach JEDER Schreibaktion (Anlegen/Aufloesen) erneut
        // aufgerufen -> die Sicht zeigt nur bestaetigt geschriebene Zustaende
        // (kein optimistisches UI, Grundregel 1).
        var reloadComments = function (uid, rid) {
            fetchJson(mod.commentsUrl(uid, rid)).then(function (cd) {
                mod.renderComments(cd, {
                    personId: state.personId,
                    onAdd: function (body) {
                        postJson('/api/report/comment', body)
                            .then(function () {
                                reloadComments(body.subject_id, body.report_id);
                            })
                            .catch(function (e) {
                                mod.commentsError(e && e.message);
                            });
                    },
                    onResolve: function (body) {
                        postJson('/api/report/comment/resolve', body)
                            .then(function () { reloadComments(uid, rid); })
                            .catch(function (e) {
                                mod.commentsError(e && e.message);
                            });
                    }
                });
            }).catch(function (e) { mod.commentsError(e && e.message); });
        };

        // Build 475: "Als Vorlage uebernehmen" nur anbieten, wenn das Recht
        // templates.edit vorliegt (das Speichern der Vorlage erfordert es
        // ohnehin). Ohne das Recht bleibt der Knopf aus -> das Modul rendert ihn
        // dann gar nicht (Callback fehlt).
        var canEditTemplates = hasCap(state.capabilities, 'templates.edit');
        var onTransfer = canEditTemplates
            ? function (uid, rid) {
                var url = '/api/report/as-template-draft?subject_id='
                    + encodeURIComponent(uid) + '&report_id='
                    + encodeURIComponent(rid);
                fetchJson(url).then(function (res) {
                    if (!res || !res.ok || !res.draft) {
                        throw new Error('Der Server lieferte keinen Entwurf.');
                    }
                    // Entwurf fuer die naechste Sicht hinterlegen und in die
                    // Dokumentvorlagen wechseln (dort sichten + speichern).
                    state.pendingTemplateDraft = {
                        draft: res.draft,
                        findings: res.findings || [],
                        warnings: res.warnings || []
                    };
                    selectView('doctemplates');
                }).catch(function (e) {
                    // Kein stiller Fehlpfad (Grundregel 1): Fehler im Lektorat
                    // sichtbar machen und den Knopf wieder aktivieren.
                    mod.transferError(e && e.message);
                });
            }
            : null;

        fetchJson('/api/reports').then(function (data) {
            cleanupView();
            mod.renderLectorate(mainEl, data, {
                status: 'submitted',
                // Bei Auswahl eines Berichts die zugrunde liegenden Belege
                // (SF-2) UND die Kommentare (SF-3) laden. Fehler werden im
                // jeweiligen Panel sichtbar gemacht (Grundregel 1).
                onSelect: function (uid, rid) {
                    log('Lektorat: Bericht gewaehlt', uid, rid);
                    fetchJson(mod.annotationsUrl(uid, rid))
                        .then(function (ad) { mod.renderAnnotations(ad); })
                        .catch(function (e) {
                            mod.annotationsError(e && e.message);
                        });
                    reloadComments(uid, rid);
                },
                // Build 475: Uebernahme in eine Dokumentvorlage (nur mit Recht).
                onTransferToTemplate: onTransfer
            });
            log('Lektorat gerendert:', data && data.count, 'Berichte');
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Lektorat konnte nicht geladen werden: ' + err.message);
        });
    }

    // loadApproval: CHEF-FREIGABE (W5, Build 416, Slice 1). Laedt die
    // Berichtsliste und rendert die Freigabe-Sicht: Auswahl + read-only
    // Berichtstext (SF-1) + Aktionen (Siegel pruefen / freigeben+versiegeln /
    // zurueckweisen). Schreibaktionen laufen ueber postJson (X-AIW-Token); die
    // Freigabe ist UNWIDERRUFLICH -> Rueckfrage vor dem Absenden. Nach jeder
    // Aktion wird neu geladen (kein optimistisches UI, Grundregel 1). Belege
    // (SF-2), Kommentare (SF-3) und Ergebnis-Mitpruefen folgen in den Slices.
    function loadApproval(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitApproval : null;
        if (!mod) {
            renderError(mainEl, 'Chef-Freigabe-Modul nicht geladen.');
            return;
        }
        // Freigeben erfordert reports.approve mit Scope 'alle' (Server erzwingt
        // es; das UI zeigt die Freigabe-Knoepfe nur dann).
        var canApprove = !!(state.capabilities
            && state.capabilities['reports.approve'] === 'alle');

        // reloadResults (Build 418/419): Ergebnis (read-only) rendern und -
        // bei results.edit - das append-only Bewertungs-Formular aus dem
        // Katalog aufbauen. Nach JEDER Bewertung erneut aufgerufen (kein
        // optimistisches UI: erst der bestaetigte Stand, Grundregel 1).
        var reloadResults = function (uid) {
            fetchJson(mod.resultsUrl(uid)).then(function (rd) {
                mod.renderResults(rd);
                if (rd && rd.can_edit) {
                    fetchJson('/api/results/catalog').then(function (cat) {
                        mod.renderAssessForm(cat, {
                            subjectId: uid,
                            onAssess: function (body) {
                                postJson('/api/results/assess', body)
                                    .then(function () { reloadResults(uid); })
                                    .catch(function (e) {
                                        mod.assessError(e && e.message);
                                    });
                            }
                        });
                    }).catch(function (e) {
                        log('Katalog nicht ladbar', e && e.message);
                    });
                }
            }).catch(function (e) { mod.resultsError(e && e.message); });
        };

        var render = function () {
            fetchJson('/api/reports').then(function (data) {
                cleanupView();
                mod.renderApproval(mainEl, data, {
                    status: 'submitted',
                    canApprove: canApprove,
                    // Bei Auswahl eines Berichts die Belege (SF-2) UND die
                    // Kommentare (SF-3, read-only) laden, damit die Chefin die
                    // Aussagen vor der Freigabe am Beleg verifizieren kann.
                    onSelect: function (uid, rid) {
                        fetchJson(mod.annotationsUrl(uid, rid))
                            .then(function (ad) { mod.renderAnnotations(ad); })
                            .catch(function (e) {
                                mod.annotationsError(e && e.message);
                            });
                        fetchJson(mod.commentsUrl(uid, rid))
                            .then(function (cd) { mod.renderComments(cd); })
                            .catch(function (e) {
                                mod.commentsError(e && e.message);
                            });
                        // Ermittlungsergebnis (read-only) + ggf. Bewertungs-
                        // Formular (results.edit). Fehlt results.view, meldet
                        // der Server 403 -> im Panel sichtbar (Grundregel 1).
                        reloadResults(uid);
                    },
                    onVerify: function (uid, rid) {
                        fetchJson('/api/report/verify?subject_id=' + uid
                                  + '&report_id=' + rid)
                            .then(function (v) { mod.renderVerify(v); })
                            .catch(function (e) {
                                mod.verifyError(e && e.message);
                            });
                    },
                    onApprove: function (body) {
                        if (typeof window !== 'undefined' && window.confirm
                            && !window.confirm('Bericht endgueltig freigeben '
                               + 'und versiegeln? Das ist unwiderruflich.')) {
                            return;
                        }
                        postJson('/api/report/approve', body)
                            .then(function () { render(); })
                            .catch(function (e) {
                                if (typeof window !== 'undefined'
                                    && window.alert) {
                                    window.alert('Freigabe fehlgeschlagen: '
                                        + (e && e.message));
                                }
                            });
                    },
                    onReturn: function (body) {
                        if (typeof window !== 'undefined' && window.confirm
                            && !window.confirm('Bericht zur Nachbesserung an '
                               + 'den Entwurf zurueckweisen?')) {
                            return;
                        }
                        postJson('/api/report/return', body)
                            .then(function () { render(); })
                            .catch(function (e) {
                                if (typeof window !== 'undefined'
                                    && window.alert) {
                                    window.alert('Rueckweisung fehlgeschlagen: '
                                        + (e && e.message));
                                }
                            });
                    }
                });
                log('Chef-Freigabe gerendert:', data && data.count, 'Berichte');
            }).catch(function (err) {
                cleanupView();
                renderError(mainEl,
                    'Chef-Freigabe konnte nicht geladen werden: '
                    + err.message);
            });
        };
        render();
    }

    // loadTemplates: PLATZHALTER & QUERIES (W2, Build 423). Laedt die Liste der
    // Platzhalter-Queries und rendert die Autoren-Maske. Zwei Aktionen:
    //   - Dry-Run: POST /api/templates/query/dryrun (SCHREIBFREI) -> zeigt
    //     Validierung + fdb-Beispielwert, OHNE etwas zu speichern.
    //   - Speichern: POST /api/templates/query (auditiert, TemplatesWriter) ->
    //     nach Erfolg wird die LISTE neu geladen (kein optimistisches UI:
    //     erst der bestaetigte Stand, Grundregel 1).
    function loadTemplates(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitTemplates : null;
        if (!mod) {
            renderError(mainEl, 'Platzhalter/Query-Modul nicht geladen.');
            return;
        }
        // Build 490 (Platzhalter-Neuordnung): neue Routen aus Build 489.
        fetchJson('/api/templates/placeholders').then(function (data) {
            cleanupView();
            mod.renderTemplates(mainEl, data, {
                onDryRun: function (payload) {
                    postJson('/api/templates/placeholder/dryrun', payload)
                        .then(function (res) { mod.renderDryRun(res); })
                        .catch(function (e) { mod.dryRunError(e && e.message); });
                },
                onSave: function (payload) {
                    postJson('/api/templates/placeholder', payload)
                        .then(function (res) {
                            mod.saved(res);
                            // Liste neu laden, damit ein NEUER Eintrag sofort
                            // erscheint bzw. eine Aenderung sichtbar wird.
                            loadTemplates(mainEl);
                        })
                        .catch(function (e) { mod.saveError(e && e.message); });
                }
            });
            log('Platzhalter/Queries gerendert:', data && data.count);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Platzhalter & Queries konnten nicht geladen werden: '
                + err.message);
        });
    }

    // loadDocTemplates: DOKUMENTVORLAGEN (W3, Build 425). Laedt die Vorlagen-
    // Liste und rendert die Autoren-Maske. Zwei Aktionen:
    //   - Struktur-Vorschau: POST /api/templates/document/dryrun (SCHREIBFREI).
    //   - Speichern: POST /api/templates/document (auditiert) -> nach Erfolg
    //     wird die LISTE neu geladen (kein optimistisches UI, Grundregel 1).
    function loadDocTemplates(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitDocTemplates : null;
        if (!mod) {
            renderError(mainEl, 'Dokumentvorlagen-Modul nicht geladen.');
            return;
        }
        // Build 475: einen aus dem Lektorat uebergebenen Vorlagen-Entwurf
        // EINMALIG konsumieren. Sofort aus dem State loeschen, damit ein spaeter
        // Neu-Laden (z.B. nach dem Speichern) den Entwurf NICHT erneut anwendet.
        var pending = state.pendingTemplateDraft;
        state.pendingTemplateDraft = null;

        fetchJson('/api/templates/documents').then(function (data) {
            cleanupView();
            mod.renderDocTemplates(mainEl, data, {
                onDryRun: function (payload) {
                    postJson('/api/templates/document/dryrun', payload)
                        .then(function (res) { mod.renderDryRun(res); })
                        .catch(function (e) { mod.dryRunError(e && e.message); });
                },
                onSave: function (payload) {
                    postJson('/api/templates/document', payload)
                        .then(function (res) {
                            mod.saved(res);
                            loadDocTemplates(mainEl);
                        })
                        .catch(function (e) { mod.saveError(e && e.message); });
                },
                // Build 475: Entwurf aus Bericht (oder null im Normalfall).
                initialDraft: pending ? pending.draft : null,
                initialFindings: pending ? pending.findings : null,
                initialWarnings: pending ? pending.warnings : null
            });
            log('Dokumentvorlagen gerendert:', data && data.count);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Dokumentvorlagen konnten nicht geladen werden: '
                + err.message);
        });
    }

    // loadModules: BAUSTEIN-MODULE (W1, Build 427). Laedt die Baustein-Liste und
    // rendert die Autoren-Maske. Zwei Aktionen:
    //   - Vorschau: POST /api/templates/module/dryrun (SCHREIBFREI).
    //   - Speichern: POST /api/templates/module (auditiert) -> nach Erfolg wird
    //     die LISTE neu geladen (kein optimistisches UI, Grundregel 1).
    function loadModules(mainEl) {
        mainEl = mainEl || document.getElementById('aiw-main');
        var mod = (typeof window !== 'undefined')
            ? window.AIWCockpitModules : null;
        if (!mod) {
            renderError(mainEl, 'Baustein-Modul-Modul nicht geladen.');
            return;
        }
        fetchJson('/api/templates/modules').then(function (data) {
            cleanupView();
            mod.renderModules(mainEl, data, {
                onDryRun: function (payload) {
                    postJson('/api/templates/module/dryrun', payload)
                        .then(function (res) { mod.renderDryRun(res); })
                        .catch(function (e) { mod.dryRunError(e && e.message); });
                },
                onSave: function (payload) {
                    postJson('/api/templates/module', payload)
                        .then(function (res) {
                            mod.saved(res);
                            loadModules(mainEl);
                        })
                        .catch(function (e) { mod.saveError(e && e.message); });
                }
            });
            log('Baustein-Module gerendert:', data && data.count);
        }).catch(function (err) {
            cleanupView();
            renderError(mainEl,
                'Baustein-Module konnten nicht geladen werden: '
                + err.message);
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
        } else if (viewId === 'audit') {
            loadAudit(mainEl, state.auditFilters, state.auditOffset);
        } else if (viewId === 'promotion') {
            loadPromotion(mainEl);
        } else if (viewId === 'releases') {
            loadReleases(mainEl);
        } else if (viewId === 'onboarding') {
            loadOnboarding(mainEl, state.onbPerson, state.onbKind);
        } else if (viewId === 'personnel') {
            loadPersonnel(mainEl);
        } else if (viewId === 'crossref') {
            loadCrossref(mainEl);
        } else if (viewId === 'crossfindings') {
            loadCrossfindings(mainEl, state.cfOnlyOpen === true);
        } else if (viewId === 'alias') {
            loadAlias(mainEl);
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
        } else if (viewId === 'notes') {
            loadNotes(mainEl);
        } else if (viewId === 'stats') {
            loadStats(mainEl);
        } else if (viewId === 'planung') {
            loadPlanung(mainEl);
        } else if (viewId === 'annostats') {
            loadAnnostats(mainEl);
        } else if (viewId === 'assignment') {
            loadAssignment(mainEl);
        } else if (viewId === 'cases') {
            loadCases(mainEl);
        } else if (viewId === 'calendar') {
            loadCalendar(mainEl);
        } else if (viewId === 'results') {
            loadResultsView(mainEl);
        } else if (viewId === 'reports') {
            loadReports(mainEl);
        } else if (viewId === 'lectorate') {
            loadLectorate(mainEl);
        } else if (viewId === 'approval') {
            loadApproval(mainEl);
        } else if (viewId === 'templates') {
            loadTemplates(mainEl);
        } else if (viewId === 'doctemplates') {
            loadDocTemplates(mainEl);
        } else if (viewId === 'modules') {
            loadModules(mainEl);
        } else {
            renderPlaceholder(mainEl, viewById(viewId));
        }
    }

    // _moduleBusy (Build 479): Meldet ein Sicht-Modul einen aktuell geoeffneten
    // Bericht? Wird vom SSE-'changed'-Handler genutzt, um einen destruktiven
    // Reload der Lektorat-/Freigabe-Sicht zu unterdruecken, solange dort ein
    // Bericht in Sichtung ist (siehe Kopfkommentar Build 479). Defensiv: fehlt
    // das Modul oder die Methode, gilt "nicht beschaeftigt" -> bisheriges
    // Verhalten (Reload), damit ein fehlendes Skript nie einen Reload verschluckt.
    function _moduleBusy(moduleName) {
        var m = (typeof window !== 'undefined') ? window[moduleName] : null;
        return !!(m && typeof m.hasSelection === 'function' && m.hasSelection());
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
            } else if (state.activeId === 'audit') {
                // Neue Belege koennen dazugekommen sein -> Seite neu laden
                // (gleiche Filter/Offset aus dem State).
                loadAudit(undefined, state.auditFilters, state.auditOffset);
            } else if (state.activeId === 'promotion') {
                // Eine Entscheidung (auch durch eine andere Chefin) erzeugt einen
                // audit_log-Beleg; zudem misst die Sicht die Platte -> der
                // Kandidatenbestand kann kippen. Also neu laden.
                loadPromotion();
            } else if (state.activeId === 'releases') {
                // Eine Freigabe/ein Widerruf (auch durch eine andere Person)
                // erzeugt einen audit_log-Beleg -> Liste neu laden.
                loadReleases();
            } else if (state.activeId === 'onboarding') {
                // Nur neu laden, wenn bereits eine Person gewaehlt ist (sonst
                // steht die Auswahl und es gibt nichts zu aktualisieren).
                if (state.onbPerson != null) {
                    loadOnboarding(undefined, state.onbPerson, state.onbKind);
                }
            } else if (state.activeId === 'personnel') {
                // Personal-/Rollenaenderungen (auch durch andere) erzeugen
                // audit_log-Belege -> LISTE neu laden. Der AD-Abschnitt wird
                // dabei bewusst NICHT geladen (jeder Abruf waere eine
                // Live-LDAP-Anfrage; er bleibt Nutzerhandlung).
                loadPersonnel();
            } else if (state.activeId === 'crossref') {
                // Eine Anlage/Revision (auch durch eine andere Person) erzeugt
                // einen audit_log-Beleg -> Katalog neu laden.
                loadCrossref();
            } else if (state.activeId === 'alias') {
                // Build 505: Alias-Aenderungen laufen ueber den coordinator-
                // audit_log — der SSE-Strom feuert also korrekt (anders als bei
                // 'crossfindings', deren Substrat die forensic_api-Pipeline
                // schreibt). Such-/Filterzustand bleibt im State erhalten.
                loadAlias();
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
            } else if (state.activeId === 'notes') {
                // Ein audit_log-Ereignis kann eine Aenderung an einer Notiz
                // durch eine Vertretung sein -> Board neu laden. Die Archiv-
                // Ansicht bleibt erhalten (state.notesArchived).
                loadNotes(undefined, { archived: state.notesArchived === true });
            } else if (state.activeId === 'stats') {
                loadStats();
            } else if (state.activeId === 'planung') {
                loadPlanung();
            } else if (state.activeId === 'annostats') {
                loadAnnostats();
            } else if (state.activeId === 'assignment') {
                loadAssignment();
            } else if (state.activeId === 'results') {
                // Eine Bewertung durch einen Ermittler (Nutzerinfo-Tab,
                // Build 390) erzeugt einen audit_log-Beleg -> die Abdeckung
                // aendert sich. Neu messen.
                loadResultsView();
            } else if (state.activeId === 'calendar') {
                // Ein audit_log-Ereignis kann ein Verschieben/Abschliessen
                // durch eine andere Person sein -> Faelligkeiten neu messen.
                loadCalendar(null, state.calYm);
            } else if (state.activeId === 'cases') {
                // Die Fall-Erkennung misst die PLATTE. Ein audit_log-Ereignis
                // (z. B. eine Aufnahme durch eine andere Chefin) veraendert die
                // Fallakte -> die Zustaende koennen kippen. Also neu messen.
                loadCases();
            } else if (state.activeId === 'reports') {
                loadReports();
            } else if (state.activeId === 'lectorate') {
                // Build 479: KEIN destruktiver Live-Reload, solange ein Bericht
                // geoeffnet ist. Belegte Ursache-Wirkung:
                //   Bericht oeffnen -> onSelect holt /api/report/annotations
                //   -> Server schreibt Chain-of-Custody-Beleg
                //      'report_annotations_viewed' in coordinator.db-audit_log
                //      (management_app.py:_audit_annotation_view; Grundregel 1)
                //   -> audit_tip_seq steigt -> SSE meldet ~2s spaeter 'changed'
                //      (management_handler.py:_handle_sse, poll=2.0s)
                //   -> loadLectorate() wuerde die Sicht neu aufbauen und die
                //      Auswahl + iframe-Vorschau verwerfen (der gemeldete Bug).
                // Ein Wieder-Auswaehlen wuerde erneut auditieren -> Endlosloop.
                // Die Berichtsliste aendert sich nur bei Einreichen/Freigeben
                // (selten). Ohne offene Auswahl laden wir wie bisher nach; bei
                // Sichtwechsel (cleanup) bzw. Rueckkehr laedt die Liste frisch.
                if (!_moduleBusy('AIWCockpitLectorate')) {
                    loadLectorate();
                } else {
                    log('SSE changed: Lektorat-Reload unterdrueckt '
                        + '(Bericht in Sichtung).');
                }
            } else if (state.activeId === 'approval') {
                // Build 479: identischer Schutz wie im Lektorat — auch die
                // Chef-Freigabe holt in onSelect /api/report/annotations und
                // wuerde sonst durch den eigenen Lesebeleg neu geladen.
                if (!_moduleBusy('AIWCockpitApproval')) {
                    loadApproval();
                } else {
                    log('SSE changed: Freigabe-Reload unterdrueckt '
                        + '(Bericht in Sichtung).');
                }
            }
            // BEWUSST KEIN Auto-Reload der Redaktions-Sichten 'templates'
            // (W2 Build 423), 'doctemplates' (W3 Build 425) und 'modules'
            // (W1 Build 427): Schreibvorgaenge auf templates.db landen in
            // templates_audit_log (eigene Tabelle), NICHT im coordinator.db-
            // audit_log, das die SSE beobachtet -> ein Upsert loest hier ohnehin
            // kein 'changed' aus. Wuerden wir dennoch neu laden, wuerde ein
            // unabhaengiges Ereignis die noch nicht gespeicherte Eingabe der
            // Autor:in verwerfen. Nach dem Speichern laden loadTemplates/
            // loadDocTemplates/loadModules die Liste selbst.
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
            // Eigene person_id (Build 415): erlaubt der Lektorat-Sicht, die
            // AUFLOESEN-Knoepfe nur an EIGENEN Kommentaren zu zeigen.
            state.personId = who.person_id;
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

            // Kommandopalette (Strg-K, Build 457) initialisieren: sie holt die
            // Sichten stets frisch (rechte-gefiltert) und springt ueber
            // selectView. Entkoppelt -> die Palette kennt VIEW_CATALOG nicht.
            var pal = (typeof window !== 'undefined')
                ? window.AIWCockpitPalette : null;
            if (pal && typeof pal.init === 'function') {
                pal.init({
                    getViews: function () {
                        return visibleViews(state.capabilities);
                    },
                    onSelect: function (viewId) { selectView(viewId); },
                    // Fall-Suche (Build 459): read-only /api/search. Bei Fehler/
                    // 403 -> leere Liste (Palette bleibt fuer die Sicht-Suche
                    // nutzbar; kein harter Fehlpfad).
                    searchCases: function (q) {
                        return fetchJson('/api/search?q='
                                + encodeURIComponent(q) + '&limit=8')
                            .then(function (data) {
                                return (data && data.results) || [];
                            })
                            .catch(function () { return []; });
                    },
                    // Fall-Sprung: zur Uebersicht wechseln und die Zeile
                    // fokussieren (state.focusCaseId wird von loadOverview nach
                    // dem Rendern ausgewertet).
                    onSelectCase: function (subjectId) {
                        state.focusCaseId = subjectId;
                        selectView('dashboard');
                    }
                });
            }

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
