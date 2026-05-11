/**
 * toolbar.js — Forensischer Werkzeugbalken
 * IT-Forensisches Ermittlungswerkzeug · Baustelle 3
 *
 * Version: v0.1.0 · Build: 175 · 2026-05-11
 *
 * Änderungen Build 175 (BS3):
 *   Bug 2.67: investigatorUsername aus s.investigator_username (Ermittler),
 *     nicht mehr aus s.username (Beschuldigter). status.py liefert jetzt
 *     investigator_username als eigenes Feld.
 *   Bug 2.76: AnnotationPopupModule — Kategorie-Dropdown: Kategorie
 *     nachträglich änderbar. Dropdown zeigt Icon+Label; Badge sofort aktuell.
 *   Bug 2.77: AnnotationPopupModule — Forenbenutzer-Badge: user_id+username
 *     des Beschuldigten wird im Popup angezeigt.
 *   Bug 2.78: AnnotationPopupModule — Benutzer-Wechsel-Panel: Annotation
 *     einem anderen Beschuldigten zuordnen. Benutzer kommen von
 *     GET /_forensic/knownusers (lazy, gecacht). Neuer Endpunkt knownusers.py.
 *   Bug 2.80: MinimapModule — contains_traces-Klasse für Spur-Elemente
 *     (initial pulsierende Umrandung via CSS-Animation). DOM-basierter
 *     Tooltip statt generischem Token-Text (_buildTraceTooltip).
 *   _state.username + _state.user_id aus /status geladen (für Popup).
 *   API_KNOWN_USERS: neuer Config-Eintrag.
 *
 * Änderungen Build 077:
 *   Sektion 2: Label "Markierung" ergänzt. Ann.-Buttons (◄/►) von Sektion 3
 *     hierher verschoben, "Ann."-Text entfernt, initial disabled.
 *     Rechts-Ausrichtung via margin-left:auto auf erstem Ann.-Button.
 *   Sektion 3: Ann.-Buttons entfernt.
 *   Sektion 4: Label "Seite" ergänzt. Buttons initial disabled — werden
 *     von _detectPagination() aktiviert wenn rel="prev"/"next" gefunden.
 *     page-info zeigt Seitenzahl "N / M" oder ist leer (kein "—" mehr).
 *   Annotations-Navigation: echter _annIdx-Counter, sequenziell durch alle
 *     Annotationen der Seite. _updateAnnButtons() hält disabled-Zustand aktuell.
 *     Highlight-Outline bei Sprung (gelb, 1.2s). AccessibilityModule.announce().
 *
 * Änderungen Build 075 (OP-KN-8 — Hinweiszeile):
 *   HintsModule: Neue kontextsensitive Hinweiszeile unterhalb der Toolbar.
 *   - Position: fixed, top:62px (direkt unter Toolbar), height:28px.
 *   - Viewport-Verschiebung via CSS-Variable --forensic-hintbar-height.
 *   - Toggle-Button in Sektion 5: ⍖ (sichtbar) / ⍏ (versteckt).
 *   - Sanfte Ein-/Ausblend-Animation (CSS max-height + opacity).
 *   - Sichtbarkeitszustand in sessionStorage persistiert.
 *   - Kategorie-Aktivierung → kategoriespezifischer Hinweistext.
 *   - page:loaded mit fetchFailed/investigator → Warntext.
 *   - ForensicToolbar.hints exponiert (set/clear/show/hide).
 *   - Jedes Modul kann HintsModule.set(text) aufrufen.
 *
 * Änderungen Build 074: keine JS-Änderungen.
 *   Serverseite: get_trace_sequence() url_type-Mapping korrigiert.
 *   Beleg: reale forensic_2948078.db — url_type-Werte weichen von
 *   Build 072-Annahmen ab (viewtopic statt topic, pmsnew_topic statt pm usw.).
 *
 * Änderungen Build 073 (Fix — TraceNavigationModule ReferenceError):
 *   _ForensicToolbar_setState() war ein undefinierter lokaler Alias auf
 *   ForensicToolbar._setState(). Alle Aufrufe direkt auf
 *   ForensicToolbar._setState() umgestellt. Der ReferenceError verhinderte
 *   in Build 072 jeden Klick auf ◄◄/▶▶ (Seitenwechsel) und die
 *   Sequenz-Initialisierung.
 *   Beleg: Screenshot Build 072 — Buttons aktiv aber ohne Funktion.
 *
 * Änderungen Build 072 (OP-KN-7 — Spur-Navigation seitenübergreifend):
 *   TraceNavigationModule: Intra-page Navigation (Build 030-C) um
 *   seitenübergreifende Navigation erweitert.
 *   - Sequenz via /_forensic/trace_sequence beim ersten Seitenload laden.
 *   - Reihenfolge: Profil → PM → Posts → Sonstiges, innerhalb Gruppe
 *     chronologisch (scrape_targets.id ASC).
 *   - Buttons zeigen ◄/► (gleiche Seite) oder ◄◄/▶▶ (Seitenwechsel).
 *     title/aria-label nennen den Zieltitel bei Seitenwechsel.
 *   - Gruppenwechsel: kurzer Toast.
 *   - Einstiegspunkt: aktuell geladene Seite.
 *   - Kein Bestätigungs-Toast vor Seitenwechsel (sofortiger Load).
 *   AnnotationsNavigation: Buttons ◄/► Ann. jetzt in Sektion 3 neben
 *   Marker-Buttons (thematische Nähe). _jumpToPrevAnnotation() ergänzt.
 *   State: traceSequence[], traceSeqIndex hinzugefügt.
 *   Config: API_TRACE_SEQUENCE hinzugefügt.
 *   Neue Dateien: forensic_api/trace_sequence.py, db.get_trace_sequence().
 *
 * Änderungen Build 071:
 *   ContextNavigatorModule — kein funktionaler JS-Change.
 *   Datenbankschicht: search_pages() liest pages.title direkt aus der
 *   DB-Spalte (Build 071 — forensic_2948078_db.sql bestätigt pages.title TEXT).
 *   HeadExtractor-Import und BLOB-Parsing entfernt. Sauberer und schneller.
 *   Beleg: forensic_2948078_db.sql, Rückmeldung Build 070.
 *   ContextNavigatorModule.getPages(): Mock-Daten ersetzt durch echten
 *   AJAX-Call an /_forensic/search?limit=50&sort=last_viewed_desc.
 *   MOCK_PAGES-Array bleibt im Code als Dokumentation erhalten, wird aber
 *   nicht mehr aufgerufen. Server liefert ausschließlich Seiten des aktuellen
 *   Benutzers (aus forensic_<uid>.db).
 *   Fehlerfall: leeres Array, kein Absturz.
 *   Beleg: Bauplan KN v0.6 §5.6 + §12 Phase KN-3.
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 *
 * Änderungen Build 069 (Dropdown UX — Titel, Sortierung):
 *   1. Titel statt URL als primäre Anzeige (§5.3 Bauplan KN):
 *      _renderList() zeigt p.title als Hauptzeile (forensic-ctx-title,
 *      12px, heller). Die gekürzte URL erscheint als Subzeile in der
 *      Meta-Zeile (forensic-ctx-url-sub, 10px Monospace, gedimmt).
 *      Die volle URL bleibt als title-Attribut (Tooltip) erhalten.
 *      Fallback: wenn kein Titel vorhanden, wird die URL als Hauptzeile
 *      angezeigt (identisches Verhalten zur Vorgängerversion).
 *   2. Default-Sortierung last_viewed_desc für Mock-Daten:
 *      getPages() sortiert die Mock-Daten nach lastViewedAt absteigend,
 *      entsprechend dem späteren Server-Default (Bauplan KN §5.6:
 *      GET /_forensic/search?sort=last_viewed_desc). Seiten ohne
 *      lastViewedAt erscheinen am Ende.
 *   Beleg: Rückmeldung Build 068 — URL-Darstellung zu abstrakt,
 *   Reihenfolge nicht explizit.
 *
 * Änderungen Build 068 (Fix — Panel-Positionierung ContextDropdownModule):
 *   Das Panel verdrängte beim Öffnen den gesamten Toolbar-Inhalt nach oben,
 *   weil es als Kind von #forensic-toolbar eingefügt wurde, das overflow:hidden
 *   und height:62px hat. Das Panel wurde dadurch in den normalen Dokumentfluss
 *   eingebettet und schob den Toolbar-Inhalt über den Rand.
 *   Fix 1: Panel wird jetzt an document.body angehängt (außerhalb aller
 *     overflow:hidden-Ketten).
 *   Fix 2: CSS geändert von position:absolute+top:44px auf position:fixed
 *     (top/left ohne Wert — werden per JS gesetzt).
 *   Fix 3: _open() berechnet Position via _btn.getBoundingClientRect():
 *     top = rect.bottom + 4px, left = rect.left. Dadurch sitzt das Panel
 *     immer direkt unterhalb des Buttons, unabhängig von DOM-Kontext.
 *   Beleg: Screenshots Build 066/067 — Seitensuche verdrängte Toolbar-Inhalt.
 *
 * Änderungen Build 067 (Fix — Null-Guard in ContextDropdownModule._bindEvents):
 *   _bindEvents() crashte in JSDOM-Testumgebungen ohne vollständiges Shell-HTML
 *   (#forensic-sec1 / #forensic-toolbar fehlend), weil _buildDOM() bereits korrekt
 *   früh abbricht (Guard `if (!sec1) return`), aber _btn und _panel dadurch null
 *   bleiben. _bindEvents() versuchte trotzdem _btn.addEventListener() → TypeError.
 *   Fix: Guard `if (!_btn || !_panel) return;` am Anfang von _bindEvents().
 *   Betroffene Tests: test_levenshtein.test.js, test_state.test.js und alle anderen
 *   Tests mit minimal-DOM (ohne forensic-sec1/forensic-toolbar im JSDOM-HTML).
 *   Beleg: Fehlermeldung auf Produktivsystem Build 066 —
 *   `TypeError: Cannot read properties of null (reading 'addEventListener')`
 *   bei _bindEvents Zeile 3534.
 *
 * Änderungen Build 066 (Kontext-Navigator Phase KN-1 + KN-2):
 *
 *   ContextNavigatorModule (Phase KN-1):
 *     Koordinator für den Kontext-Navigator. Hält den Dropdown-Cache
 *     (bis zu 50 PageSummaryRecords), leitet Events zwischen
 *     ContextDropdownModule und NavigationModule und invalidiert den
 *     Cache bei page:loaded. Öffentlich exponiert als
 *     ForensicToolbar.navigator.
 *
 *   ContextDropdownModule (Phase KN-2):
 *     Ersetzt den statischen Badge (forensic-context-badge) und den
 *     Dummy-Select (forensic-context-select) durch einen vollständigen
 *     Dropdown-Button in Zone Links / Sektion 1.
 *     Features: Kontext-Badge (U/E/A), Panel mit Seitenliste,
 *     Freitextfilter (Debounce 150 ms), vier Schnellfilter-Chips,
 *     Lade-Indikator, «Erweiterte Suche»-Einstieg (Stub).
 *     Datenbasis: Mock-Daten (Phase KN-3 bringt Server-Anbindung).
 *     ARIA: role="combobox", aria-expanded, aria-haspopup="listbox",
 *     Focus-Trap im Panel, Esc schließt.
 *     Tastenkürzel: Alt+K öffnet/fokussiert das Dropdown.
 *     Beleg: Bauplan Baustelle 3 Ergänzung Kontext-Navigator v0.6 §5.
 *
 *   State-Erweiterung (§3 Bauplan Kontext-Navigator):
 *     contextDropdownOpen, contextModalOpen, contextSearchResults.
 *
 *   ToolbarUIModule: Dummy-Select-Block (forensic-sec-context) und
 *     zugehöriger Separator entfernt — Funktion wird vollständig
 *     durch ContextDropdownModule übernommen.
 *     Beleg: forensic-context-select war als Dummy markiert (Build 030-B).
 *
 *   ContextBadgeModule: bleibt als Modul erhalten, operiert aber
 *     nicht mehr auf einem eigenen DOM-Knoten in Zone Links — es
 *     delegiert stattdessen an ContextDropdownModule.updateBadge().
 *     Rückwärtskompatibel: ContextBadgeModule.update() funktioniert
 *     weiterhin und kann von NavigationModule aufgerufen werden.
 *
 *   API_SEARCH: Neuer Config-Eintrag für /_forensic/search.
 *
 * Änderungen Build 065:
 *
 *   Fix A — Falsche page_url nach 404-Navigation:
 *     _state.currentUrl wurde in _handleEnvelope() vor den in_scope/fetch_failed-
 *     Prüfungen gesetzt. Nach einem 404 blieb der Viewport unverändert, aber
 *     currentUrl zeigte die neue URL — alle folgenden Annotationen erhielten
 *     falsche page_url. Fix: currentUrl erst nach erfolgreichem Scope+HTML-Check,
 *     direkt vor viewport.innerHTML = envelope.html.
 *
 *   Fix B — HoverMenu für Textmarkierungen (CSS Custom Highlights):
 *     Neue Funktion _findAnnotationsAtPoint(clientX, clientY): findet alle
 *     Annotationen an einem Dokumentpunkt via caretRangeFromPoint/
 *     caretPositionFromPoint + Range-Boundary-Vergleich. Dwell-Timer nutzt
 *     jetzt diese Funktion statt Post-Container-Delegation.
 *     Neue Funktion _showMenuForList(anns, x, y): Multi-Annotation-Listenmenü
 *     mit Kategorie-Icon, Textkürzel (40 Zeichen), Edit/Delete pro Zeile.
 *     _deleteAnnotation() als extrahierte Hilfsfunktion (war dupliziert).
 *     AnnotationPopupModule.isOpen() als neue öffentliche Methode.
 *     Neue CSS-Klassen in toolbar.css: forensic-hover-menu--list,
 *     forensic-hover-list-header, forensic-hover-list-row,
 *     forensic-hover-list-cat, forensic-hover-list-label.
 *
 * Änderungen Build 064:
 *   Fix Race-Condition Textmarkierung vs. Post-Markierung:
 *   mouseup → _onMouseUp erstellt Textmarkierung + öffnet Popup + removeAllRanges().
 *   click → _onPostClick: Selektion ist durch removeAllRanges() bereits kollabiert,
 *   bisheriger Guard (sel.isCollapsed) reichte nicht — _onPostClick behandelte die
 *   Annotation als Post-Markierung und überschrieb selection=null + post_id gesetzt.
 *   Fix: AnnotationPopupModule.isOpen() — wenn Popup bereits offen, bricht
 *   _onPostClick sofort ab. isOpen() als neue öffentliche Methode ergänzt.
 *   Beleg: DB-Einträge zeigten selection_json=NULL + post_id gesetzt bei
 *   expliziter Textselektion.
 *
 * Änderungen Build 063:
 *   Fix HoverMenu-Retrigger: Mousemove-Debounce (_dwellTimer) — wenn die Maus
 *   nach Schließen des Menüs im Post verbleibt, öffnet Verweilen (HOVER_DELAY_MS)
 *   das Menü erneut, ohne dass die Maus das Post-Element verlassen muss.
 *   clearTimeout(_dwellTimer) auch in mouseout.
 *
 *   Diagnose-Hilfsfunktionen (global, aufrufbar in Browser-Console):
 *   - window.forensicTestHighlight(): Testet XPath-Auflösung aller Annotations
 *   - window.forensicForceRestoreAll(): Erzwingt clearAll + restoreAll sofort
 *   Beleg: Textmarkierungen nach Reload unsichtbar — Diagnose-Tools zur Isolation
 *   des Problems (viewMode? rangeFromSelection-Fehler? CSS Highlights API?).
 *
 * Änderungen Build 062:
 *
 *   Fix 3 — HoverMenu-Position: Menü erschien in rechter oberer Post-Ecke.
 *     _lastMouseX/_lastMouseY-Tracker via mousemove auf dem Viewport. setTimeout-
 *     Callback liest diese statt veraltete mouseover-Event-Koordinaten.
 *     Position: _lastMouseX + 12px, _lastMouseY - 36px (leicht rechts über Cursor).
 *
 *   Fix 4 — Debugging-Mode:
 *     _dbg()-Hilfsfunktion: aktivierbar per window.forensicDebug = true in der
 *     Browser-Console (kein Reload nötig, wirkt ab nächstem page:loaded-Event).
 *     ForensicToolbar.config.DEBUG: statisches Flag (Standard: false).
 *     Instrumentiert: rangeFromSelection(), restoreAll(), loadAnnotations-Callback,
 *     requestAnimationFrame-Callback. Ausgabe als console.groupCollapsed.
 *
 * Änderungen Build 060 (Bugfixes: Highlights + HoverMenu):
 *
 *   Fix 1 — Highlights nach Reload unsichtbar:
 *     HighlightModule.restoreAll() und alle post-load Module werden jetzt
 *     in requestAnimationFrame() verzögert. Beleg: Nach viewport.innerHTML
 *     ist das Browser-Rendering asynchron — XPath-Auflösung über
 *     #forensic-viewport schlug fehl weil der Layout-Tree noch nicht fertig
 *     war. Symptom: Minimap zeigte Annotations, <mark>-Tags fehlten.
 *
 *   Fix 2 — HoverMenu: Position instabil, Menü unerreichbar:
 *     Event-Delegation auf Post-Container-Ebene ([data-forensic-cat]) statt
 *     beliebige Kind-Elemente. Menüposition jetzt relativ zu getBoundingClientRect()
 *     des Post-Containers (stabil), nicht zur Mausposition (instabil).
 *     mouseout schließt das Menü nicht mehr wenn Maus noch im Post-Container
 *     oder im Menü selbst verbleibt.
 *     Beleg: mouseover auf Kind-Element + mouseout beim Verlassen in Richtung
 *     Menü führte zum sofortigen Schließen des Menüs.
 *
 * Änderungen Build 059 (OP-KN-9 — Annotation Hover-Menü Delete-Fix):
 *   - ajaxDelete(): neue AJAX-Hilfsfunktion für HTTP DELETE mit JSON-Body.
 *     Beleg: Server-Endpunkt annotate.py Build 059 unterstützt jetzt DELETE.
 *   - HoverMenuModule: Delete-Pfad ergänzt um Server-Call via ajaxDelete().
 *     Optimistic update: Client entfernt Annotation sofort, Server-Call erfolgt
 *     asynchron. Bei Fehler: Konsolenwarnung + ARIA-Announce. Keine Server-ID
 *     (syncState==="pending") → kein Server-Call nötig (nie persistiert).
 *     Beleg: OP-KN-9 — ohne diesen Fix erscheinen gelöschte Annotationen nach
 *     loadAnnotations() wieder (clientseitiger delete() ohne Server-Persistenz).
 *   - AnnotationPopupModule.close(true): Event "annotation:created" durch
 *     "annotation:updated" ersetzt wenn Annotation bereits Server-ID hat.
 *     Beleg: Semantische Korrektur für korrekte KN-Fortschrittsberechnung.
 *
 *   - loadPage(url, pushState, method): neuer optionaler method-Parameter.
 *     'POST' → API-URL enthält &original_method=POST für Poll-Ergebnisseiten.
 *     Default 'GET' wenn weggelassen. Beleg: Projektgespräch 2026-04-19.
 *   - _interceptLinks(): Form-Submit abfangen. form.method wird als
 *     original_method an loadPage weitergegeben. Nur lokale/Forum-Forms
 *     werden abgefangen. Beleg: Projektgespräch 2026-04-19.
 *   - ForensicToolbar.navigation: NavigationModule öffentlich exponiert
 *     für Tests und externe Aufrufer.
 *
 *   - HighlightModule: CSS Custom Highlights API Vorinitialisierung aller
 *     Kategorie-Sets beim Modulstart (kein bedingtes Set-Erstellen in render()).
 *   - HighlightModule: Fallback-Pfad ersetzt surroundContents() durch robusten
 *     TreeWalker-Ansatz (Beleg: PoC highlight_poc.html, MD5 2e449a68...); kein
 *     Absturz mehr bei Selektionen über Elementgrenzen hinweg.
 *   - HighlightModule: clearAll() leert Ranges in vorhandenen Sets statt Sets
 *     zu löschen und neu zu registrieren.
 *   - Kategorie-Buttons: Permanenter gedämpfter Rahmen in Kategoriefarbe auch
 *     im inaktiven Zustand (border-color: <color>72). Aktiver Zustand: volle
 *     Sättigung + schwacher Hintergrund.
 *   - XPath: _xpathOf() Präfix "./" statt "//" (relativ zum context-Node);
 *     Text-Nodes korrekt als text()[n] kodiert statt "#text[n]".
 *
 * Änderungen Build 030-B:
 *   - Toolbar: right: 0 statt right: 44px (#9 — Minimap liegt über Toolbar).
 *   - Toolbar: Drei-Zonen-Layout [Links: Badge] [Mitte: Werkzeuge] [Rechts:
 *     Navigation + Session] (#10 — Werkzeuge über Forum-Inhalt zentriert).
 *   - Seitenkontext-Dropdown (§OP-6): Dummy-Implementierung, deaktiviert.
 *   - Spurennummer-Eingabe (§OP-5): Dummy-Implementierung mit ◀/Eingabe/▶,
 *     deaktiviert — Funktionalität folgt in späterem Build.
 *
 * Änderungen Build 030-C:
 *   - State: traceElements[] aus envelope.trace_elements.
 *   - MinimapModule: Zwei Marker-Typen — Spur-Marker (traceElements, grau-blau,
 *     sofort beim Laden) und Annotations-Marker (Kategoriefarbe).
 *     Textmarkierungs-Annotationen werden über XPath-Range positioniert.
 *   - TraceNavigationModule (neu): Aktiviert Spurennummer-Eingabe und ◀/▶-
 *     Buttons; springt zu traceElements[idx] mit visuell. Aufblitzen.
 *   - _handleEnvelope: traceElements aus Envelope in State übernehmen.
 *
 * Architektur: Modularer Aufbau über ForensicToolbar-Namespace.
 * Kommunikation ausschließlich über CustomEvent-Bus (ForensicToolbar.events).
 * State ist nur über definierte Mutationsfunktionen änderbar.
 * DOM-Integrität des BLOBs ist forensisch unverletzlich (Grundregel 11).
 *
 * Module (in Initialisierungsreihenfolge):
 *   ForensicToolbar          — Namespace, State, Events, Config (Phase 1)
 *   ToolbarUIModule          — DOM-Aufbau der Toolbar (Phase 2)
 *   NavigationModule         — AJAX-Load, Link-Abfangung, History (Phase 3)
 *   AnnotationStoreModule    — XPath, Serialisierung, Server-Sync (Phase 4)
 *   HighlightModule          — CSS Custom Highlights API + Fallback (Phase 4)
 *   MarkerToolModule         — Textmarkierungs-Workflow (Phase 5)
 *   PostMarkerModule         — Ganzen Post markieren (Phase 5)
 *   AnnotationPopupModule    — Schwebendes Editor-Feld (Phase 6)
 *   HoverMenuModule          — Mini-Werkzeugleiste beim Hover (Phase 6)
 *   MinimapModule            — Seitenleiste mit Positions-Markern (Phase 7)
 *   ViewportTrackerModule    — IntersectionObserver → /_forensic/viewport (Phase 7)
 *   ContextBadgeModule       — scrape_context-Anzeige (Phase 10)
 *   FetchFailedModule        — Anzeige bei fetch_failed=true (Phase 10)
 *   UserInfoTabModule        — window.open() → /_forensic/userinfo (Phase 10)
 *   AccessibilityModule      — ARIA-Live-Region, Keyboard-Navigation (Phase 9)
 *   ViewModeModule           — Ansichtswechsel Original ↔ Angepasst (Phase 11)
 *   PMSTableOrganizerModule  — Sortierung/Filterung PN-Übersichtstabelle (Phase 11)
 *   TopicsTableOrganizerModule — Sortierung/Filterung Topic-Tabellen (Phase 11)
 *   SupportIndicatorModule   — SSE-Empfang, Support-Indikator (Phase 12)
 *   ContextNavigatorModule   — Koordinator Kontext-Navigator (Phase KN-1)
 *   ContextDropdownModule    — Schnell-Dropdown Sektion 1 (Phase KN-2)
 */

(function () {
  "use strict";

  // ===========================================================================
  // PHASE 1: ForensicToolbar — Namespace, State, Events, Config
  // ===========================================================================

  var ForensicToolbar = window.ForensicToolbar = {};

  // ---------------------------------------------------------------------------
  // Config — alle Konstanten
  // ---------------------------------------------------------------------------
  ForensicToolbar.config = {
    // API-Endpunkte
    API_PAGE:        "/_forensic/page",
    API_ANNOTATE:    "/_forensic/annotate",
    API_ANNOTATIONS: "/_forensic/annotations",
    API_STATUS:      "/_forensic/status",
    API_VIEWPORT:    "/_forensic/viewport",
    API_EVENTS:      "/_forensic/events",
    API_USERINFO:    "/_forensic/userinfo",
    // Kontext-Navigator (Build 066, Bauplan KN §7.3)
    API_SEARCH:           "/_forensic/search",
    // Spur-Navigation (Build 072, OP-KN-7)
    API_TRACE_SEQUENCE:   "/_forensic/trace_sequence",
    // Build 175 (Bug 2.78): Bekannte Beschuldigte-Benutzer
    API_KNOWN_USERS:      "/_forensic/knownusers",

    // Annotationskategorien (Reihenfolge = Tastenkürzel 1-6)
    CATEGORIES: [
      { id: "CAT_PERSON",   label: "PER", icon: "👤", color: "#f5c842", desc: "Persönliche Identifikationsmerkmale",  key: "1" },
      { id: "CAT_LOCATION", label: "LOC", icon: "📍", color: "#4f8ef7", desc: "Ortsangaben, geografische Hinweise",    key: "2" },
      { id: "CAT_176",      label: "176", icon: "⚖️", color: "#e84040", desc: "Relevanz §§ 176, 176a StGB",           key: "3" },
      { id: "CAT_184",      label: "184", icon: "🔴", color: "#c040e8", desc: "Relevanz §§ 184b, 184c StGB",          key: "4" },
      { id: "CAT_VICTIM",   label: "OPF", icon: "🛡️", color: "#e87040", desc: "Hinweise auf mögliche Opfer",          key: "5" },
      { id: "CAT_OTHER",    label: "SON", icon: "📎", color: "#40c8a0", desc: "Sonstige Ermittlungsrelevanz",         key: "6" },
    ],

    // Tag-Vokabular (§19.1 Bauplan)
    TAG_VOCABULARY: [
      "username","realname","email","telefon","adresse","ort","land",
      "ip","pgp","passwort","datum","foto","sprache","gerät",
      "krypto","social","telegram","signatur","opfer","alter",
    ],

    // Levenshtein-Schwellenwert für Tag-Vorschläge (§19.2)
    LEVENSHTEIN_THRESHOLD: 2,
    TAG_MAX_INPUT_LEN: 50,

    // Hover-Delay für HoverMenuModule (ms)
    HOVER_DELAY_MS: 600,

    // Debug-Modus: Ausführliche Console-Ausgabe für Diagnose.
    // Im Produktivbetrieb auf false setzen oder window.forensicDebug = false.
    // Build 061: Aktivierbar per window.forensicDebug = true in der Browser-Console.
    // Beleg: Highlight-Restore nach Reload nicht sichtbar — Debugging-Mode
    // zur Diagnose von rangeFromSelection() und restoreAll() eingeführt.
    DEBUG: (typeof window !== "undefined" && window.forensicDebug === true),

    // Viewport-Flush-Intervall (ms)
    VIEWPORT_FLUSH_MS: 2000,

    // Retry-Verzögerung bei Netzwerkfehler (ms)
    RETRY_DELAY_MS: 30000,

    // Toolbar-Höhe in px (CSS-Sync: toolbar.css)
    TOOLBAR_HEIGHT: 62,

    // Levenshtein-Distanz — pure JS, keine externe Bibliothek (§19.2)
    levenshtein: function (a, b) {
      if (a.length === 0) return b.length;
      if (b.length === 0) return a.length;
      var matrix = [];
      for (var i = 0; i <= b.length; i++) matrix[i] = [i];
      for (var j = 0; j <= a.length; j++) matrix[0][j] = j;
      for (var i2 = 1; i2 <= b.length; i2++) {
        for (var j2 = 1; j2 <= a.length; j2++) {
          if (b.charAt(i2 - 1) === a.charAt(j2 - 1)) {
            matrix[i2][j2] = matrix[i2 - 1][j2 - 1];
          } else {
            matrix[i2][j2] = Math.min(
              matrix[i2 - 1][j2 - 1] + 1,
              Math.min(matrix[i2][j2 - 1] + 1, matrix[i2 - 1][j2] + 1)
            );
          }
        }
      }
      return matrix[b.length][a.length];
    },

    // Hilfsfunktion: Tag-Vorschlag per Levenshtein
    suggestTag: function (input, knownTags) {
      if (!input || input.length > ForensicToolbar.config.TAG_MAX_INPUT_LEN) return null;
      var all = ForensicToolbar.config.TAG_VOCABULARY.concat(knownTags || []);
      var best = null, bestDist = Infinity;
      for (var i = 0; i < all.length; i++) {
        var d = ForensicToolbar.config.levenshtein(input.toLowerCase(), all[i].toLowerCase());
        if (d === 0) return all[i]; // exakter Treffer
        if (d < bestDist) { bestDist = d; best = all[i]; }
      }
      return (bestDist <= ForensicToolbar.config.LEVENSHTEIN_THRESHOLD) ? best : null;
    },
  };

  // ---------------------------------------------------------------------------
  // Events — Pub/Sub-Bus (CustomEvent-basiert)
  // ---------------------------------------------------------------------------
  ForensicToolbar.events = (function () {
    var _handlers = {};
    return {
      on: function (name, fn) {
        if (!_handlers[name]) _handlers[name] = [];
        _handlers[name].push(fn);
      },
      off: function (name, fn) {
        if (!_handlers[name]) return;
        _handlers[name] = _handlers[name].filter(function (h) { return h !== fn; });
      },
      emit: function (name, data) {
        if (!_handlers[name]) return;
        _handlers[name].forEach(function (h) {
          try { h(data); } catch (e) { console.error("[Forensic] Event-Handler Fehler (" + name + "):", e); }
        });
      },
    };
  })();

  // ---------------------------------------------------------------------------
  // State — einziger zentraler Zustandsspeicher
  // ---------------------------------------------------------------------------
  var _state = {
    currentUrl:          "",
    baseHref:            null,
    scrapeContext:       "user",
    fetchFailed:         false,
    inScope:             true,
    fragment:            null,
    activeCategory:      null,
    annotations:         new Map(),
    hoveredAnnotationId: null,
    serverReachable:     true,
    viewMode:            "enhanced",
    // Benutzer-Spuren auf der aktuellen Seite (DOM-Element-IDs, Build 030-C).
    // Befüllt vom Server via envelope.trace_elements.
    // Wird von MinimapModule und TraceNavigationModule verwendet.
    traceElements:       [],
    supportStatus: {
      active:   false,
      username: null,
      since:    null,
    },
    investigatorUsername: "",
    forumHostname:        "",
    lastSaveTs:           null,
    syncErrorCount:       0,
    // Kontext-Navigator (Build 066, Bauplan KN §3)
    // contextDropdownOpen: Dropdown gerade sichtbar?
    // contextModalOpen:    Erweiterte-Suche-Modal geöffnet?
    // contextSearchResults: Zuletzt geladene Seiten-Zusammenfassungen (PageSummaryRecord[]).
    //   Flüchtig — nicht persistiert, nicht zwischen Navigationen beibehalten.
    contextDropdownOpen:   false,
    contextModalOpen:      false,
    contextSearchResults:  [],
    // Spur-Navigation seitenübergreifend (Build 072, OP-KN-7)
    // traceSequence:  Array<{url, title, group, trace_id}> — geordnete Spurenliste
    // traceSeqIndex:  Index in traceSequence der aktuell betrachteten Seite (-1 = unbekannt)
    traceSequence:         [],
    traceSeqIndex:         -1,
  };

  // Öffentlicher Read-only-Zugriff auf State
  ForensicToolbar.state = {
    get: function (key) { return _state[key]; },
    getAll: function () {
      // Flache Kopie — direktes Schreiben hat keine Wirkung
      return Object.assign({}, _state);
    },
  };

  // State-Mutation nur über diese Funktion (kein direktes Schreiben von außen)
  ForensicToolbar._setState = function (updates) {
    Object.assign(_state, updates);
    ForensicToolbar.events.emit("state:changed", updates);
  };

  // ---------------------------------------------------------------------------
  // Hilfsfunktionen (global innerhalb des IIFE)
  // ---------------------------------------------------------------------------

  /** HTML-Sonderzeichen escapen */
  function _esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /** UUID v4 generieren (Browser-seitig) */
  function _uuid() {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    // Fallback für ältere Browser
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      return (c === "x" ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  /**
   * Debug-Logging-Hilfsfunktion.
   * Gibt nur aus wenn ForensicToolbar.config.DEBUG oder window.forensicDebug true ist.
   * Aufruf: _dbg("label", obj1, obj2, ...)
   * Aktivierung in der Browser-Console: window.forensicDebug = true; (kein Reload nötig,
   * wirkt aber erst ab dem nächsten page:loaded-Event für restoreAll)
   * Build 061: Eingeführt zur Diagnose von Highlight-Restore-Problemen.
   */
  function _dbg(label) {
    if (!ForensicToolbar.config.DEBUG && !window.forensicDebug) return;
    var args = Array.prototype.slice.call(arguments, 1);
    console.groupCollapsed("[Forensic DEBUG] " + label);
    args.forEach(function(a) { console.log(a); });
    console.groupEnd();
  }

  /** AJAX-GET → Promise<Object> */
  function ajaxGet(url) {
    return fetch(url, {
      headers: { "X-Forensic-Request": "ajax" }
    }).then(function (r) { return r.json(); });
  }

  /** AJAX-POST mit JSON-Body → Promise<Object> */
  function ajaxPost(url, data) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Forensic-Request": "ajax",
      },
      body: JSON.stringify(data),
    }).then(function (r) { return r.json(); });
  }

  /**
   * _resolveTraceElement(elemId) → HTMLElement | null
   *
   * Gemeinsame Hilfsfunktion für MinimapModule und TraceNavigationModule.
   * Löst einen traceElements-Token zu einem DOM-Element auf.
   *
   * Zwei Formate:
   *   "p<post_id>"     → document.getElementById("p<post_id>")
   *                      (Post-Container auf viewtopic.php)
   *   "topic:<id>"     → querySelector('a[href*="viewtopic.php?id=<id>&uid="]')
   *                      .closest("tr")
   *                      (Topic-Zeile auf viewforum.php — Build 082)
   *
   * Beleg: HTML-Analyse viewforum.php — Links haben immer &uid= Parameter.
   *        Selektor 'a[href*="?id=<id>&uid="]' ist eindeutig (kein Treffer
   *        auf action=new-Links da diese kein &uid= enthalten).
   */
  function _resolveTraceElement(elemId) {
    if (!elemId) return null;
    if (elemId.startsWith("topic:")) {
      var topicId = elemId.slice(6);
      var link = document.querySelector(
        'a[href*="viewtopic.php?id=' + topicId + '&uid="]'
      );
      return link ? link.closest("tr") : null;
    }
    return document.getElementById(elemId);
  }

  /**
   * AJAX-DELETE mit JSON-Body → Promise<Object>
   * Beleg: OP-KN-9 — Server-seitiges Löschen von Annotationen erfordert
   * HTTP DELETE (annotate.py Build 059).
   */
  function ajaxDelete(url, data) {
    return fetch(url, {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        "X-Forensic-Request": "ajax",
      },
      body: JSON.stringify(data),
    }).then(function (r) { return r.json(); });
  }

  /** Kategorie-Objekt anhand ID */
  function _getCat(catId) {
    return ForensicToolbar.config.CATEGORIES.find(function (c) { return c.id === catId; }) || null;
  }

  // ===========================================================================
  // PHASE 4: AnnotationStoreModule — XPath, Serialisierung, Server-Sync
  // ===========================================================================
  var AnnotationStoreModule = (function () {

    /**
     * XPath eines DOM-Knotens relativ zu #forensic-viewport berechnen.
     *
     * Korrekturen gegenüber Build 029:
     *   1. Präfix "./" statt "//" — document.evaluate() mit context-Node
     *      interpretiert "//" als "überall im Dokument" und ignoriert den
     *      context-Node. "./" bedeutet "relativ zum context-Node".
     *   2. Text-Nodes (#text) werden als text()[n] kodiert, nicht als
     *      "#text[n]" — "#text[n]" ist kein gültiger XPath-Schritt und
     *      wirft in document.evaluate() eine Exception.
     *
     * Beleg: XPath-Spezifikation §2.1 — Location Steps; MDN document.evaluate()
     */
    function _xpathOf(node) {
      var viewport = document.getElementById("forensic-viewport");
      if (!viewport || !viewport.contains(node)) return "";
      var parts = [];
      var current = node;
      while (current && current !== viewport) {
        var tag;
        if (current.nodeType === 3) {
          // Text-Node: XPath-Schritt ist text()[n]
          tag = "text()";
        } else {
          tag = current.nodeName.toLowerCase();
        }
        // Geschwister-Index berechnen (nur Geschwister desselben Typs zählen)
        var idx = 1;
        var sib = current.previousSibling;
        while (sib) {
          if (current.nodeType === 3) {
            if (sib.nodeType === 3) idx++;
          } else {
            if (sib.nodeName.toLowerCase() === tag) idx++;
          }
          sib = sib.previousSibling;
        }
        parts.unshift(tag + "[" + idx + "]");
        current = current.parentNode;
      }
      // "./" → relativ zum context-Node (viewport), nicht absolut im Dokument
      return "./" + parts.join("/");
    }

    /**
     * Knoten anhand XPath relativ zu #forensic-viewport finden.
     * Gibt null zurück wenn nicht gefunden.
     *
     * Migration alter XPath-Formate (Build 029 → 030):
     *   Build 029 speicherte XPaths mit zwei Fehlern:
     *     1. Präfix "//" statt "./" → wird on-the-fly ersetzt
     *     2. Text-Nodes als "#text[n]" statt "text()[n]" → wird ersetzt
     *   Beide Korrekturen erlauben das Wiederherstellen alter Annotationen
     *   ohne Datenverlust. Beleg: Fehlermeldung in Konsole Build 030-C.
     */
    function _nodeFromXpath(xpath) {
      var viewport = document.getElementById("forensic-viewport");
      if (!viewport) return null;

      // Migration: altes "//" → "./"
      var migrated = xpath;
      if (migrated.substring(0, 2) === "//") {
        migrated = "./" + migrated.substring(2);
      }
      // Migration: "#text[n]" → "text()[n]" (ungültiger XPath-Schritt)
      migrated = migrated.replace(/\/#text\[(\d+)\]/g, "/text()[$1]");

      try {
        var result = document.evaluate(
          migrated, viewport, null,
          XPathResult.FIRST_ORDERED_NODE_TYPE, null
        );
        return result.singleNodeValue;
      } catch (e) {
        console.warn("[Forensic] XPath-Auflösung fehlgeschlagen:", migrated, e.message);
        return null;
      }
    }

    /**
     * Selection-Objekt aus einer Browser-Selection erstellen.
     * Gibt null zurück wenn Selektion ungültig.
     */
    function selectionFromBrowser(sel) {
      if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
      var range = sel.getRangeAt(0);
      var viewport = document.getElementById("forensic-viewport");
      if (!viewport) return null;
      if (!viewport.contains(range.startContainer) ||
          !viewport.contains(range.endContainer)) return null;
      var text = sel.toString().trim();
      if (!text) return null;

      return {
        xpathStart:  _xpathOf(range.startContainer),
        offsetStart: range.startOffset,
        xpathEnd:    _xpathOf(range.endContainer),
        offsetEnd:   range.endOffset,
        textContent: text,
      };
    }

    /**
     * Browser-Range aus einem gespeicherten selection-Objekt wiederherstellen.
     * Gibt null zurück wenn Wiederherstellung scheitert.
     * Bei textContent-Abweichung → stale (§4 Bauplan).
     */
    function rangeFromSelection(sel) {
      if (!sel) {
        _dbg("rangeFromSelection: sel ist null/undefined");
        return null;
      }
      var startNode = _nodeFromXpath(sel.xpathStart);
      var endNode   = _nodeFromXpath(sel.xpathEnd);
      _dbg("rangeFromSelection",
        { xpathStart: sel.xpathStart, xpathEnd: sel.xpathEnd,
          textContent: sel.textContent,
          startNode: startNode, endNode: endNode }
      );
      if (!startNode || !endNode) {
        _dbg("rangeFromSelection: XPath-Auflösung fehlgeschlagen",
          { startNode: startNode, endNode: endNode,
            viewportExists: !!document.getElementById("forensic-viewport"),
            viewportChildren: document.getElementById("forensic-viewport")
              ? document.getElementById("forensic-viewport").children.length : 0 }
        );
        return null;
      }
      try {
        var range = document.createRange();
        range.setStart(startNode, sel.offsetStart);
        range.setEnd(endNode, sel.offsetEnd);
        // Verifikation: textContent gegen gespeicherten Wert prüfen
        var actual = range.toString().trim();
        var stored = (sel.textContent || "").trim();
        var stale  = (actual !== stored);
        _dbg("rangeFromSelection: Erfolg",
          { actual: actual, stored: stored, stale: stale, range: range.toString() }
        );
        return { range: range, stale: stale };
      } catch (e) {
        _dbg("rangeFromSelection: Ausnahme", e);
        return null;
      }
    }

    /**
     * Annotation erstellen (lokal, noch nicht gespeichert).
     * Gibt ein AnnotationRecord-artiges Objekt zurück.
     */
    function createAnnotation(category, pageUrl, elementId, selection, postId) {
      return {
        id:        null,
        localId:   _uuid(),
        pageUrl:   pageUrl,
        category:  category,
        text:      "",
        tags:      [],
        elementId: elementId || null,
        selection: selection || null,
        postId:    postId || null,
        createdAt: Date.now(),
        createdBy: _state.investigatorUsername,
        syncState: "pending",
        stale:     false,
      };
    }

    /**
     * Annotation an Server senden und in State speichern.
     * Bei Fehler: Status 'error', automatischer Retry nach RETRY_DELAY_MS.
     */
    function syncAnnotation(ann) {
      var payload = {
        page_url:   ann.pageUrl,
        category:   ann.category,
        text:       ann.text,
        element_id: ann.elementId || null,
        local_id:   ann.localId,
        post_id:    ann.postId || null,
        tags:       ann.tags || [],
        selection:  ann.selection || null,
      };

      return ajaxPost(ForensicToolbar.config.API_ANNOTATE, payload)
        .then(function (r) {
          if (r.status === "ok") {
            ann.id        = r.id;
            ann.syncState = "synced";
            _state.annotations.set(ann.localId, ann);
            _state.lastSaveTs = Date.now();
            ForensicToolbar.events.emit("annotation:synced", ann);
            AccessibilityModule.announce("Annotation #" + r.id + " gespeichert.");
            ToolbarUIModule.updateSessionInfo();
          } else {
            ann.syncState = "error";
            _state.syncErrorCount++;
            ForensicToolbar.events.emit("annotation:error", ann);
            AccessibilityModule.announce("Fehler beim Speichern der Annotation.");
            _scheduleRetry(ann);
          }
        })
        .catch(function (e) {
          ann.syncState = "error";
          _state.syncErrorCount++;
          ForensicToolbar.events.emit("annotation:error", ann);
          AccessibilityModule.announce("Netzwerkfehler: Annotation nicht gespeichert.");
          console.error("[Forensic] Annotation-Sync Fehler:", e);
          _scheduleRetry(ann);
        });
    }

    /** Automatischer Retry nach RETRY_DELAY_MS (einmalig, §11.4 Bauplan) */
    function _scheduleRetry(ann) {
      if (ann._retried) return; // Nur einmal wiederholen
      ann._retried = true;
      setTimeout(function () {
        if (ann.syncState === "error") {
          ann._retried = false;
          syncAnnotation(ann);
        }
      }, ForensicToolbar.config.RETRY_DELAY_MS);
    }

    /**
     * Annotationen vom Server laden und in State speichern.
     * Wird nach jedem BLOB-Load aufgerufen.
     */
    function loadAnnotations(pageUrl) {
      _state.annotations.clear();
      return ajaxGet(
        ForensicToolbar.config.API_ANNOTATIONS + "?url=" + encodeURIComponent(pageUrl)
      )
        .then(function (r) {
          if (!r.annotations) return;
          r.annotations.forEach(function (ann) {
            ann.syncState = "synced";
            ann.stale     = false;
            _state.annotations.set(ann.localId || String(ann.id), ann);
          });
          ForensicToolbar.events.emit("annotations:loaded", { count: r.annotations.length });
        })
        .catch(function (e) {
          console.warn("[Forensic] Annotationen konnten nicht geladen werden:", e);
        });
    }

    return {
      selectionFromBrowser: selectionFromBrowser,
      rangeFromSelection:   rangeFromSelection,
      createAnnotation:     createAnnotation,
      syncAnnotation:       syncAnnotation,
      loadAnnotations:      loadAnnotations,
    };
  })();

  // ===========================================================================
  // PHASE 4: HighlightModule — CSS Custom Highlights API + Fallback
  // Build 030-A: Vollständige Überarbeitung.
  //
  // Primärpfad (CSS Custom Highlights API):
  //   Beleg: PoC highlight_poc.html bestätigt Unterstützung in Firefox ESR.
  //   Highlight-Sets werden beim Modulstart für alle Kategorien vorinitialisiert
  //   und in CSS.highlights registriert. renderHighlight() trägt nur noch die
  //   Range ein — kein DOM-Eingriff, keine Ausnahmen möglich.
  //
  // Fallback (<mark>-Injection via TreeWalker):
  //   surroundContents() scheitert wenn eine Selektion Elementgrenzen
  //   überschreitet (z.B. <b>...</b> in der Mitte des markierten Texts).
  //   Stattdessen: TreeWalker über alle Text-Nodes im Range-Bereich;
  //   für jeden Text-Node wird ein eigenes <mark> erstellt.
  //   Beleg: PoC highlight_poc.html — _wrapRangeInMark() validiert.
  // ===========================================================================
  var HighlightModule = (function () {

    // Prüfen ob CSS Custom Highlights API verfügbar ist (§10.5 Bauplan).
    // Beleg: PoC bestätigt Verfügbarkeit in Firefox ESR.
    var _cssHighlightsAvailable = (
      typeof CSS !== "undefined" &&
      typeof CSS.highlights !== "undefined" &&
      typeof Highlight !== "undefined"
    );

    if (!_cssHighlightsAvailable) {
      console.warn("[Forensic] CSS Custom Highlights API nicht verfügbar — Fallback auf <mark>-Injection aktiv.");
    }

    // Highlight-Sets pro Kategorie — beim Modulstart für alle Kategorien
    // vorinitialisiert und in CSS.highlights registriert.
    // Vorteil: renderHighlight() muss nicht mehr prüfen ob das Set existiert;
    // kein Risiko von doppelten CSS.highlights.set()-Aufrufen beim restoreAll().
    var _highlights = {};
    if (_cssHighlightsAvailable) {
      ForensicToolbar.config.CATEGORIES.forEach(function (cat) {
        var hlName = "forensic-" + cat.id.toLowerCase();
        var hl = new Highlight();
        _highlights[cat.id] = hl;
        CSS.highlights.set(hlName, hl);
      });
    }

    // Injizierte <mark>-Elemente pro Annotation-localId (Fallback)
    var _marks = {};

    // ---------------------------------------------------------------------------
    // Hilfsfunktion: Hex-Farbe → rgba-String mit gewünschter Deckkraft
    // Beleg: PoC highlight_poc.html — _hexToRgba()
    // ---------------------------------------------------------------------------
    function _hexToRgba(hex, alpha) {
      var r = parseInt(hex.slice(1, 3), 16);
      var g = parseInt(hex.slice(3, 5), 16);
      var b = parseInt(hex.slice(5, 7), 16);
      return "rgba(" + r + "," + g + "," + b + "," + alpha + ")";
    }

    // ---------------------------------------------------------------------------
    // Robustes <mark>-Wrapping auch über Elementgrenzen hinweg (Fallback).
    //
    // Strategie: TreeWalker über alle Text-Nodes im gemeinsamen Ancestor-Container
    // der Range. Für jeden Text-Node der zum Range-Bereich gehört wird ein
    // eigenes <mark>-Element erstellt. Das vermeidet das surroundContents()-
    // Problem vollständig.
    //
    // Gibt Array der erstellten <mark>-Elemente zurück (leer bei Fehler).
    // Beleg: PoC highlight_poc.html — _wrapRangeInMark() validiert.
    // ---------------------------------------------------------------------------
    function _wrapRangeInMark(range, annKey, cat) {
      var marks = [];
      var viewport = document.getElementById("forensic-viewport");
      if (!viewport) return marks;

      var ancestor = range.commonAncestorContainer;
      var walkerRoot = (ancestor.nodeType === 3)
        ? ancestor.parentNode
        : ancestor;

      var walker = document.createTreeWalker(walkerRoot, NodeFilter.SHOW_TEXT, null);
      var textNodes = [];
      var node;
      while ((node = walker.nextNode())) {
        if (!viewport.contains(node)) continue;
        // Node muss den Range überlappen:
        //   range.END_TO_START >= 0  → Range endet vor oder am Anfang des Nodes → kein Overlap
        //   range.START_TO_END <= 0  → Range beginnt nach oder am Ende des Nodes → kein Overlap
        var nr = document.createRange();
        nr.selectNodeContents(node);
        if (range.compareBoundaryPoints(Range.END_TO_START, nr) >= 0) continue;
        if (range.compareBoundaryPoints(Range.START_TO_END, nr) <= 0) continue;
        textNodes.push(node);
      }

      textNodes.forEach(function (textNode) {
        var start = (textNode === range.startContainer) ? range.startOffset : 0;
        var end   = (textNode === range.endContainer)   ? range.endOffset   : textNode.length;
        if (start >= end) return;

        var nodeRange = document.createRange();
        nodeRange.setStart(textNode, start);
        nodeRange.setEnd(textNode, end);

        var mark = document.createElement("mark");
        mark.dataset.forensicAnnotation = annKey;
        mark.dataset.forensicCategory   = cat ? cat.id : "";
        mark.style.backgroundColor      = cat ? _hexToRgba(cat.color, 0.45) : "rgba(170,170,170,0.45)";
        mark.style.borderRadius         = "2px";
        mark.style.cursor               = "pointer";

        try {
          nodeRange.surroundContents(mark);
          marks.push(mark);
        } catch (e1) {
          // surroundContents scheitert wenn nodeRange selbst noch über eine
          // Elementgrenze geht. Dann extractContents + insertNode verwenden.
          try {
            var frag = nodeRange.extractContents();
            mark.appendChild(frag);
            nodeRange.insertNode(mark);
            marks.push(mark);
          } catch (e2) {
            console.warn("[Forensic] <mark>-Fallback: Fragment-Wrap Fehler:", e2);
          }
        }
      });

      return marks;
    }

    // ---------------------------------------------------------------------------
    // renderHighlight — Highlight für eine Annotation rendern
    // ---------------------------------------------------------------------------
    function renderHighlight(ann) {
      if (_state.viewMode === "original") return;
      if (!ann || !ann.selection) return;

      var restored = AnnotationStoreModule.rangeFromSelection(ann.selection);
      if (!restored) {
        ann.stale = true;
        return;
      }
      if (restored.stale) {
        ann.stale = true;
        AccessibilityModule.announce(
          "Warnung: Annotation #" + (ann.id || ann.localId) + " ist veraltet (Inhalt geändert)."
        );
      }

      var cat    = _getCat(ann.category);
      var annKey = ann.localId || String(ann.id);

      if (_cssHighlightsAvailable) {
        // Primärpfad: Range in vorinitialisiertes Highlight-Set eintragen.
        // Kein DOM-Eingriff; kein Ausnahmerisiko.
        var hlSet = _highlights[ann.category];
        if (hlSet) {
          hlSet.add(restored.range);
        } else {
          // Sollte durch Vorinitialisierung nie eintreten — defensiver Fallback
          console.warn("[Forensic] Highlight-Set fuer Kategorie nicht gefunden:", ann.category);
        }
      } else {
        // Fallback: TreeWalker-basiertes <mark>-Wrapping
        var newMarks = _wrapRangeInMark(restored.range, annKey, cat);
        if (newMarks.length > 0) {
          _marks[annKey] = (_marks[annKey] || []).concat(newMarks);
        } else {
          console.warn("[Forensic] <mark>-Fallback: Keine Fragmente erstellt fuer Annotation", annKey);
        }
      }
    }

    // ---------------------------------------------------------------------------
    // clearAll — Alle Highlights entfernen (viewmode:original)
    // ---------------------------------------------------------------------------
    function clearAll() {
      if (_cssHighlightsAvailable) {
        // Ranges aus allen Sets leeren; Sets selbst erhalten (CSS.highlights
        // Registrierung bleibt damit bei restoreAll() kein Re-Register nötig ist)
        Object.keys(_highlights).forEach(function (catId) {
          _highlights[catId].clear();
        });
      } else {
        // <mark>-Elemente aus DOM entfernen (reversibler Eingriff, §11 GR11b)
        Object.keys(_marks).forEach(function (key) {
          (_marks[key] || []).forEach(function (mark) {
            var parent = mark.parentNode;
            if (!parent) return;
            while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
            parent.removeChild(mark);
          });
        });
        _marks = {};
      }
    }

    // ---------------------------------------------------------------------------
    // restoreAll — Alle gespeicherten Highlights wiederherstellen (viewmode:enhanced)
    // ---------------------------------------------------------------------------
    function restoreAll() {
      var count = _state.annotations.size;
      _dbg("HighlightModule.restoreAll: START",
        { annotationCount: count,
          viewMode: _state.viewMode,
          cssHighlightsAvailable: _cssHighlightsAvailable,
          viewportExists: !!document.getElementById("forensic-viewport"),
          viewportChildCount: document.getElementById("forensic-viewport")
            ? document.getElementById("forensic-viewport").children.length : 0
        }
      );
      var restored = 0;
      _state.annotations.forEach(function (ann) {
        _dbg("restoreAll: Annotation", {
          id: ann.id, localId: ann.localId, category: ann.category,
          hasSelection: !!ann.selection, postId: ann.postId, stale: ann.stale
        });
        renderHighlight(ann);
        restored++;
      });
      _dbg("HighlightModule.restoreAll: DONE", { attempted: count, processed: restored });
    }

    return {
      render:     renderHighlight,
      clearAll:   clearAll,
      restoreAll: restoreAll,
    };
  })();

  // ===========================================================================
  // PHASE 2: ToolbarUIModule — DOM-Aufbau der Toolbar
  // ===========================================================================
  var ToolbarUIModule = (function () {

    function build() {
      var toolbar = document.getElementById("forensic-toolbar");
      if (!toolbar) return;

      toolbar.setAttribute("role", "toolbar");
      toolbar.setAttribute("aria-label", "Forensischer Werkzeugbalken");

      toolbar.innerHTML = _renderHTML();

      // Event-Listener auf Kategorie-Buttons
      ForensicToolbar.config.CATEGORIES.forEach(function (cat) {
        var btn = document.getElementById("forensic-cat-" + cat.id);
        if (btn) {
          btn.addEventListener("click", function () {
            MarkerToolModule.toggleCategory(cat.id);
          });
        }
      });

      // Nutzerinfo-Button
      var uiBtn = document.getElementById("forensic-btn-userinfo");
      if (uiBtn) {
        uiBtn.addEventListener("click", function () {
          UserInfoTabModule.open();
        });
      }

      // Nächste Annotation
      var nextBtn = document.getElementById("forensic-btn-next-ann");
      if (nextBtn) {
        nextBtn.addEventListener("click", function () {
          _jumpToNextAnnotation();
        });
      }
      // Vorherige Annotation (Build 072 — Button jetzt in Sektion 3 neben Marker-Buttons)
      var prevAnnBtn = document.getElementById("forensic-btn-prev-ann");
      if (prevAnnBtn) {
        prevAnnBtn.addEventListener("click", function () {
          _jumpToPrevAnnotation();
        });
      }

      // Ansichtswechsel
      var vmBtn = document.getElementById("forensic-btn-viewmode");
      if (vmBtn) {
        vmBtn.addEventListener("click", function () {
          ViewModeModule.toggle();
        });
      }

      // Navigation: Pfeiltasten
      var prevBtn = document.getElementById("forensic-btn-nav-prev");
      var nextPgBtn = document.getElementById("forensic-btn-nav-next");
      if (prevBtn) prevBtn.addEventListener("click", function () { NavigationModule.navigatePrev(); });
      if (nextPgBtn) nextPgBtn.addEventListener("click", function () { NavigationModule.navigateNext(); });
    }

    function _renderHTML() {
      var cats = ForensicToolbar.config.CATEGORIES.map(function (cat) {
        // border-color im Ruhezustand: Kategoriefarbe mit 45% Deckkraft (hex-Suffix "72").
        // Im aktiven Zustand wird der Rahmen durch updateCategoryButtons() auf volle
        // Sättigung gesetzt. So ist die Farb-Kennung dauerhaft sichtbar.
        // Beleg: §2 Anforderung — farblicher Rahmen auch im inaktiven Zustand.
        return (
          '<button id="forensic-cat-' + cat.id + '" ' +
          'class="forensic-cat-btn" ' +
          'data-category="' + cat.id + '" ' +
          'style="border-color:' + cat.color + '72;" ' +
          'aria-label="' + _esc(cat.desc) + ' (Taste ' + cat.key + ')" ' +
          'title="' + _esc(cat.desc) + ' [Taste ' + cat.key + ']" ' +
          'aria-pressed="false">' +
          '<span aria-hidden="true">' + cat.icon + '</span>' +
          '<span class="forensic-cat-label">' + cat.label + '</span>' +
          '</button>'
        );
      }).join("");

      return (
        // =====================================================================
        // ZONE LINKS — Kontext-Badge, fest am linken Rand
        // =====================================================================
        '<div class="forensic-zone forensic-zone-left">' +

          // Sektion 1: Kontext-Navigator (Build 066)
          // ContextDropdownModule mountet hier seinen Button + Panel.
          // Der frühere statische forensic-context-badge wird durch den
          // Dropdown-Button ersetzt (Bauplan KN §5.1).
          '<div class="forensic-section forensic-sec1" id="forensic-sec1" aria-label="Ermittlungskontext">' +
          '</div>' +

        '</div>' + // /zone-left

        // =====================================================================
        // ZONE MITTE — zentriert über die gesamte verbleibende Breite
        // Enthält: Seitenkontext-Dropdown | Marker-Buttons | Aktionen
        // =====================================================================
        '<div class="forensic-zone forensic-zone-center">' +

          // Sektion 2: Markier-Werkzeuge + Annotations-Navigation rechts
          // Label "Markierung" links, Kategorie-Buttons mittig,
          // ◄/► Annotations-Navigation am rechten Rand.
          // Build 077: Ann.-Buttons von Sektion 3 hierher verschoben,
          // "Ann."-Text entfernt, Label ergänzt.
          '<div class="forensic-section forensic-sec2" role="group" aria-label="Markierungskategorien">' +
          '<span class="forensic-sec-label">Markierung</span>' +
          cats +
          '<button id="forensic-btn-prev-ann" class="forensic-btn forensic-ann-nav-btn" ' +
          'aria-label="Zur vorherigen Annotation springen" ' +
          'title="Vorherige Annotation" disabled>◀</button>' +
          '<button id="forensic-btn-next-ann" class="forensic-btn forensic-ann-nav-btn" ' +
          'aria-label="Zur nächsten Annotation springen" ' +
          'title="Nächste Annotation" disabled>▶</button>' +
          '</div>' +
          '<div class="forensic-separator" aria-hidden="true"></div>' +

          // Sektion 3: Aktionen
          '<div class="forensic-section forensic-sec3">' +
          '<button id="forensic-btn-userinfo" class="forensic-btn" ' +
          'aria-label="Nutzerinfo-Tab öffnen (Alt+U)" title="Nutzerinfo öffnen [Alt+U]">' +
          '👤 Nutzerinfo</button>' +
          '<button id="forensic-btn-viewmode" class="forensic-btn" ' +
          'aria-label="Ansicht wechseln: Original oder Angepasst" ' +
          'title="Ansicht wechseln [Original / Angepasst]" ' +
          'data-viewmode="enhanced">' +
          '⊞ Angepasst</button>' +
          '</div>' +

        '</div>' + // /zone-center

        // =====================================================================
        // ZONE RECHTS — Navigation, Spurennummer, Session-Info
        // =====================================================================
        '<div class="forensic-zone forensic-zone-right">' +

          '<div class="forensic-separator" aria-hidden="true"></div>' +

          // Sektion 4: Seitennavigation (Pagination)
          // Label "Seite" links. Buttons sind initial disabled — NavigationModule
          // aktiviert sie sobald rel="prev"/"next"-Links auf der Seite gefunden werden.
          // Build 077: Label ergänzt, initial disabled.
          '<div class="forensic-section forensic-sec4" aria-label="Seitennavigation">' +
          '<span class="forensic-sec-label">Seite</span>' +
          '<button id="forensic-btn-nav-prev" class="forensic-btn forensic-nav-btn" ' +
          'aria-label="Vorherige Seite (Alt+Pfeil links)" title="Vorherige Seite [Alt+←]" disabled>◀</button>' +
          '<span id="forensic-page-info" class="forensic-page-info" aria-label="Seitenposition" aria-live="polite"></span>' +
          '<button id="forensic-btn-nav-next" class="forensic-btn forensic-nav-btn" ' +
          'aria-label="Nächste Seite (Alt+Pfeil rechts)" title="Nächste Seite [Alt+→]" disabled>▶</button>' +
          '</div>' +
          '<div class="forensic-separator" aria-hidden="true"></div>' +

          // Spurennummer-Eingabe + seitenübergreifende Spurennavigation (OP-KN-7, Build 072)
          // Buttons zeigen ◄/► wenn Ziel auf gleicher Seite, ◄◄/▶▶ wenn Seitenwechsel nötig.
          // Beschriftung wird von TraceNavigationModule dynamisch gesetzt.
          '<div class="forensic-section forensic-sec-trace" aria-label="Spurennavigation">' +
          '<span class="forensic-sec-label">Spur</span>' +
          '<div class="forensic-trace-row">' +
          '<button class="forensic-btn forensic-nav-btn" id="forensic-btn-trace-prev" ' +
          'aria-label="Vorherige Spur" title="Vorherige Spur" disabled>◀</button>' +
          '<input id="forensic-trace-input" type="number" min="1" ' +
          'class="forensic-trace-input" ' +
          'aria-label="Spurennummer direkt eingeben" ' +
          'title="Spurennummer eingeben und Enter drücken" ' +
          'placeholder="—" disabled>' +
          '<span class="forensic-trace-total" id="forensic-trace-total" ' +
          'aria-label="Gesamtanzahl Spuren">/ 0</span>' +
          '<button class="forensic-btn forensic-nav-btn" id="forensic-btn-trace-next" ' +
          'aria-label="Nächste Spur" title="Nächste Spur" disabled>▶</button>' +
          '</div>' +
          '</div>' +

          // Sektion 5: Session-Info
          '<div class="forensic-section forensic-sec5" aria-label="Sitzungsinformationen">' +
          '<span id="forensic-session-user" class="forensic-session-info">…</span>' +
          '<span id="forensic-annotation-count" class="forensic-session-info" ' +
          'aria-label="Anzahl Annotationen auf dieser Seite">0 Ann.</span>' +
          '<span id="forensic-sync-status" class="forensic-sync-ok" aria-live="polite" ' +
          'aria-label="Synchronisierungsstatus"></span>' +
          '<span id="forensic-support-indicator" class="forensic-support-hidden" ' +
          'role="status" aria-live="assertive"></span>' +
          // Hinweiszeile Toggle (Build 075, OP-KN-8)
          // 🛈▲ = sichtbar (Klick blendet aus), 🛈▼ = versteckt (Klick blendet ein)
          '<button id="forensic-hints-toggle" class="forensic-btn forensic-hints-toggle-btn" ' +
          'aria-label="Hinweiszeile ausblenden" title="Hinweiszeile ausblenden" ' +
          'aria-expanded="true">🛈▲</button>' +
          '</div>' +

        '</div>' // /zone-right
      );
    }

    /** Status-Text in Sektion 5 aktualisieren */
    function updateSessionInfo() {
      var userEl   = document.getElementById("forensic-session-user");
      var countEl  = document.getElementById("forensic-annotation-count");
      var syncEl   = document.getElementById("forensic-sync-status");
      if (userEl)  userEl.textContent  = _state.investigatorUsername || "—";
      if (countEl) countEl.textContent = _state.annotations.size + " Ann.";
      if (syncEl) {
        if (_state.syncErrorCount > 0) {
          syncEl.textContent = "⚠ " + _state.syncErrorCount + " Sync-Fehler";
          syncEl.className = "forensic-sync-error";
        } else {
          syncEl.textContent = _state.lastSaveTs
            ? "✓ " + new Date(_state.lastSaveTs).toLocaleTimeString("de-DE")
            : "";
          syncEl.className = "forensic-sync-ok";
        }
      }
    }

    /** Kategorie-Button visuell aktivieren/deaktivieren */
    function updateCategoryButtons(activeCatId) {
      ForensicToolbar.config.CATEGORIES.forEach(function (cat) {
        var btn = document.getElementById("forensic-cat-" + cat.id);
        if (!btn) return;
        var active = (cat.id === activeCatId);
        btn.setAttribute("aria-pressed", active ? "true" : "false");
        btn.classList.toggle("forensic-cat-active", active);
        if (active) {
          // Aktiv: volle Kategoriefarbe + schwacher Hintergrund
          btn.style.borderColor = cat.color;
          btn.style.background  = cat.color + "22";
        } else {
          // Inaktiv: gedämpfter Rahmen (45% Deckkraft, hex "72") bleibt sichtbar.
          // Beleg: §2 Anforderung — farbliche Kennung dauerhaft erkennbar.
          btn.style.borderColor = cat.color + "72";
          btn.style.background  = "";
        }
      });
      // Cursor im Viewport umschalten
      var vp = document.getElementById("forensic-viewport");
      if (vp) vp.style.cursor = activeCatId ? "crosshair" : "";
    }

    // Annotation-Navigation — sequenzieller Index (Build 078, fix Build 079)
    // _state.annotations ist eine Map<localId, AnnotationRecord>.
    // Annotationen haben kein elementId bei Textmarkierungen — die Position
    // wird über selection.xpathStart/End wiederhergestellt via
    // AnnotationStoreModule.rangeFromSelection().
    //
    // WICHTIG: _state.annotations wird per .set()/.clear() direkt mutiert —
    // _setState() wird NICHT aufgerufen, also feuert "state:changed" mit
    // "annotations" NIE. Stattdessen auf "annotations:loaded" und
    // "annotation:synced" / "annotation:deleted" hören.
    // Beleg: Build 079 — Diagnose ergab annotations:loaded als korrektes Event.
    var _annIdx = -1;

    function _annArray() {
      // Map-Insertion-Order entspricht Lade-Reihenfolge (ausreichend für Navigation).
      // Kein Range-Vergleich im Comparator — zu teuer bei vielen Annotationen.
      var arr = [];
      _state.annotations.forEach(function (ann) { arr.push(ann); });
      return arr;
    }

    function _annCount() {
      return _state.annotations ? _state.annotations.size : 0;
    }

    function _updateAnnButtons() {
      var prevBtn = document.getElementById("forensic-btn-prev-ann");
      var nextBtn = document.getElementById("forensic-btn-next-ann");
      var n = _annCount();
      if (prevBtn) prevBtn.disabled = (n === 0 || _annIdx <= 0);
      if (nextBtn) nextBtn.disabled = (n === 0 || _annIdx >= n - 1);
    }

    function _jumpToAnn(idx) {
      var arr = _annArray();
      if (!arr.length) return;
      idx = Math.max(0, Math.min(arr.length - 1, idx));
      _annIdx = idx;
      var ann = arr[idx];

      // Scrollziel: XPath-Range (Textmarkierung) oder Post-ID
      var scrollTarget = null;
      if (ann.selection) {
        try {
          var result = AnnotationStoreModule.rangeFromSelection(ann.selection);
          // rangeFromSelection gibt {range, stale} zurück — nicht die Range direkt.
          // Beleg: Build 079-Fix — range.startContainer war undefined.
          if (result && result.range) {
            var node = result.range.startContainer;
            scrollTarget = (node.nodeType === 3) ? node.parentElement : node;
          }
        } catch (e) { /* Range nicht auflösbar */ }
      }
      if (!scrollTarget && ann.elementId) {
        scrollTarget = document.getElementById(ann.elementId);
      }
      if (!scrollTarget && ann.postId) {
        scrollTarget = document.getElementById("p" + ann.postId);
      }

      if (scrollTarget) {
        scrollTarget.scrollIntoView({ behavior: "smooth", block: "center" });
        scrollTarget.style.transition = "outline 0.1s";
        scrollTarget.style.outline    = "3px solid #f5c842";
        setTimeout(function () { scrollTarget.style.outline = ""; }, 1200);
      }

      AccessibilityModule.announce(
        "Annotation " + (idx + 1) + " von " + arr.length +
        (ann.category ? " · " + ann.category : "") +
        (ann.selection && ann.selection.textContent
          ? " · \"" + ann.selection.textContent.substring(0, 30) + "\""
          : "")
      );
      _updateAnnButtons();
    }

    function _jumpToNextAnnotation() {
      if (!_annCount()) return;
      _jumpToAnn(_annIdx < 0 ? 0 : _annIdx + 1);
    }

    function _jumpToPrevAnnotation() {
      if (!_annCount()) return;
      _jumpToAnn(_annIdx <= 0 ? 0 : _annIdx - 1);
    }

    // Buttons aktualisieren wenn Annotationen geladen/geändert/gelöscht werden.
    // NICHT auf "state:changed" mit "annotations" — die Map wird direkt mutiert.
    ForensicToolbar.events.on("annotations:loaded",  function () {
      _annIdx = -1;
      _updateAnnButtons();
    });
    ForensicToolbar.events.on("annotation:synced",   function () { _updateAnnButtons(); });
    ForensicToolbar.events.on("annotation:deleted",  function () {
      _annIdx = -1;
      _updateAnnButtons();
    });
    ForensicToolbar.events.on("page:loaded", function () {
      _annIdx = -1;
      _updateAnnButtons();
    });

    // Event-Listener registrieren
    ForensicToolbar.events.on("state:changed", function (updates) {
      if ("activeCategory" in updates) updateCategoryButtons(_state.activeCategory);
      if ("annotations" in updates || "lastSaveTs" in updates || "syncErrorCount" in updates) {
        updateSessionInfo();
      }
    });
    ForensicToolbar.events.on("annotation:synced",   updateSessionInfo);
    ForensicToolbar.events.on("annotation:error",    updateSessionInfo);
    ForensicToolbar.events.on("annotations:loaded",  updateSessionInfo);

    return {
      build:                build,
      updateSessionInfo:    updateSessionInfo,
      updateCategoryButtons: updateCategoryButtons,
    };
  })();

  // ===========================================================================
  // PHASE 3: NavigationModule — AJAX-Load, Link-Abfangung, History
  // ===========================================================================
  var NavigationModule = (function () {
    // Pagination-Links der aktuellen Seite
    var _prevUrl = null;
    var _nextUrl = null;

    function loadPage(url, pushState, method) {
      // method: HTTP-Methode des Originalrequests ('GET' oder 'POST').
      // Default 'GET'. 'POST' für Poll-Abstimmungsergebnisse.
      // Beleg: Projektgespräch 2026-04-19.
      var originalMethod = (method && method.toUpperCase() === "POST") ? "POST" : "GET";
      AccessibilityModule.announce("Lade Seite…");
      var apiUrl = ForensicToolbar.config.API_PAGE
        + "?url=" + encodeURIComponent(url)
        + (originalMethod === "POST" ? "&original_method=POST" : "");
      ajaxGet(apiUrl)
        .then(function (envelope) {
          _handleEnvelope(envelope, url, pushState);
        })
        .catch(function (err) {
          ForensicToolbar._setState({ serverReachable: false });
          AccessibilityModule.announce("Fehler beim Laden der Seite: " + err.message);
          console.error("[Forensic] Ladefehler:", err);
        });
    }

    function _handleEnvelope(envelope, url, pushState) {
      var viewport = document.getElementById("forensic-viewport");
      if (!viewport) return;

      // currentUrl nur aktualisieren wenn die Seite tatsächlich geladen wird.
      // Beleg: Build 064 — bei NOT_IN_SCOPE oder fetch_failed (z.B. 404) wurde
      // currentUrl bereits auf die neue URL gesetzt bevor der Fehler erkannt wurde.
      // Folge: Alle nachfolgenden Annotationen erhielten die falsche page_url.
      // Fix: currentUrl wird nur gesetzt wenn in_scope=true und fetch_failed=false.
      // scrapeContext, fetchFailed, inScope, fragment, traceElements immer setzen
      // (für Toast/FetchFailedModule-Anzeige).
      ForensicToolbar._setState({
        baseHref:      (envelope.head && envelope.head.base_href) || null,
        scrapeContext: envelope.scrape_context || "user",
        fetchFailed:   !!envelope.fetch_failed,
        inScope:       !!envelope.in_scope,
        fragment:      envelope.fragment || null,
        traceElements: Array.isArray(envelope.trace_elements)
          ? envelope.trace_elements : [],
      });

      if (!envelope.in_scope) {
        ToastModule.show(
          "⚠ Diese Seite liegt nicht im Umfang der Ermittlungen: " + _esc(url),
          "warning",
          0   // bleibt bis manuelles Schließen
        );
        AccessibilityModule.announce("Seite nicht im Ermittlungsumfang.");
        return;
      }

      if (envelope.fetch_failed || !envelope.html) {
        FetchFailedModule.show(viewport, url, envelope.http_status);
        ToastModule.show(
          "⚠ Seitenabruf fehlgeschlagen (HTTP " + _esc(String(envelope.http_status || "—")) + "): " + _esc(url),
          "error",
          10000
        );
        return;
      }

      // Seite ist in_scope und html vorhanden: currentUrl jetzt setzen.
      // Beleg: Build 064 Fix A — currentUrl erst hier setzen, nicht vor den
      // Fehlerchecks. Andernfalls übernimmt _state.currentUrl die neue URL auch
      // bei 404/NOT_IN_SCOPE, und nachfolgende Annotationen erhalten falsche page_url.
      ForensicToolbar._setState({ currentUrl: envelope.url_canonical || url });

      // BLOB-Inhalt injizieren (erlaubter DOM-Eingriff: Navigation)
      viewport.innerHTML = envelope.html;

      // <head>-Elemente aus Envelope in Shell-<head> übernehmen
      // Wird bei jeder AJAX-Navigation aktualisiert, da jede Seite
      // eigene CSS-Dateien und einen eigenen Titel haben kann.
      _updateHead(envelope.head);

      // Fragment-Scroll
      if (envelope.fragment) {
        var target = document.getElementById(envelope.fragment) ||
                     document.getElementsByName(envelope.fragment)[0];
        if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      }

      // Browser-History
      if (pushState) {
        history.pushState({ forensicUrl: url }, "", url);
      }

      // Links abfangen
      _interceptLinks(viewport);

      // Pagination erkennen
      _detectPagination(viewport, envelope);

      // Alle nachgelagerten Module nach Load benachrichtigen
      ForensicToolbar.events.emit("page:loaded", {
        url:    _state.currentUrl,
        html:   envelope.html,
      });

      // Annotationen laden, Highlights + Minimap (inkl. Spuren) wiederherstellen
      AnnotationStoreModule.loadAnnotations(_state.currentUrl).then(function () {
        _dbg("loadAnnotations.then: Annotationen geladen",
          { url: _state.currentUrl, count: _state.annotations.size,
            viewMode: _state.viewMode }
        );
        // requestAnimationFrame stellt sicher, dass das Browser-Rendering nach
        // viewport.innerHTML abgeschlossen ist, bevor XPath-Lookups für Highlights
        // ausgeführt werden.
        //
        // Beleg: Fehler "Highlights nach Reload unsichtbar" — rangeFromSelection()
        // schlug fehl weil der DOM nach innerHTML noch nicht vollständig gerendert
        // war. Fix Build 060: Highlights werden erst nach nächstem Paint-Frame
        // wiederhergestellt. Annotations existieren (Minimap zeigt sie), aber
        // XPath-Auflösung über #forensic-viewport erfordert fertigen Layout-Tree.
        requestAnimationFrame(function () {
          _dbg("requestAnimationFrame: Callback feuert",
            { annotationCount: _state.annotations.size,
              viewportChildCount: document.getElementById("forensic-viewport")
                ? document.getElementById("forensic-viewport").children.length : 0 }
          );
          HighlightModule.restoreAll();
          // PostMarkerModule.restoreAll() stellt Post-Markierungen (ohne XPath/Selection,
          // nur postId) wieder her — wurde in Build 059/060 fälschlicherweise ausgelassen.
          // Beleg: Build 062 — nach Reload fehlten Post-Markierungen (Seitenneuladen
          // zeigte leeren Viewport-Inhalt ohne farbige Post-Hervorhebungen).
          PostMarkerModule.restoreAll();
          // MinimapModule.refresh() rendert sowohl Spur-Marker (traceElements)
          // als auch Annotations-Marker — traceElements sind zu diesem Zeitpunkt
          // bereits im State (setState in _handleEnvelope oben).
          MinimapModule.refresh();
          // TraceNavigationModule.init() aktiviert Spurennummer-Eingabe + ◀/▶
          TraceNavigationModule.init();
          ViewportTrackerModule.start(viewport, _state.currentUrl);
          PMSTableOrganizerModule.init(viewport);
          TopicsTableOrganizerModule.init(viewport);
          ToolbarUIModule.updateSessionInfo();
        }); // END requestAnimationFrame
      });

      ContextBadgeModule.update(_state.scrapeContext);
      AccessibilityModule.announce("Seite geladen: " + _state.currentUrl);
    }

    function _updateHead(head) {
      // Aktualisiert <title> und CSS-Elemente im Shell-<head> anhand der
      // head-Daten aus dem JSON-Envelope.
      //
      // Strategie CSS:
      //   Alle <link rel="stylesheet">- und <style>-Elemente, die beim
      //   vorherigen Seitenaufruf eingefügt wurden (erkennbar am Attribut
      //   data-forensic-page-css), werden entfernt. Dann werden die neuen
      //   Elemente der aktuellen Seite eingefügt.
      //   Forum-CSS aus dem initialen Shell-Load (kein data-forensic-page-css)
      //   bleibt unangetastet — das verhindert, dass /_forensic/toolbar.css
      //   oder andere Shell-eigene Styles entfernt werden.
      //
      // Strategie <title>:
      //   Wird direkt überschrieben wenn vorhanden. Fehlt der Titel im
      //   Envelope (null), bleibt der bisherige Titel erhalten.

      // Strategie <base href>:
      //   Wird aktualisiert wenn base_href im Envelope vorhanden ist.
      //   Existiert noch kein <base>-Element, wird es neu erstellt.
      //   Fehlt base_href (null), bleibt ein vorhandenes <base>-Element erhalten.

      if (!head) return;

      var docHead = document.head;

      // <base href> aktualisieren oder anlegen
      if (head.base_href !== null && head.base_href !== undefined) {
        var baseEl = docHead.querySelector("base");
        if (!baseEl) {
          baseEl = document.createElement("base");
          // <base> muss erstes Element im <head> sein
          docHead.insertBefore(baseEl, docHead.firstChild);
        }
        baseEl.setAttribute("href", head.base_href);
      }

      // Alte seitenspezifische CSS-Elemente entfernen
      docHead.querySelectorAll("[data-forensic-page-css]").forEach(function (el) {
        el.parentNode.removeChild(el);
      });

      // Neue externe Stylesheets einfügen
      if (head.stylesheets && head.stylesheets.length) {
        head.stylesheets.forEach(function (href) {
          var link = document.createElement("link");
          link.rel  = "stylesheet";
          link.href = href;
          link.setAttribute("data-forensic-page-css", "1");
          docHead.appendChild(link);
        });
      }

      // Neue Inline-Styles einfügen
      if (head.inline_styles && head.inline_styles.length) {
        head.inline_styles.forEach(function (css) {
          var style = document.createElement("style");
          style.setAttribute("data-forensic-page-css", "1");
          style.textContent = css;
          docHead.appendChild(style);
        });
      }

      // <title> aktualisieren
      if (head.title !== null && head.title !== undefined) {
        document.title = head.title;
      }
    }

    function _interceptLinks(container) {
      // Forum-Hostname aus State: Links mit diesem Host sind interne Links
      // und müssen per AJAX abgerufen werden, auch wenn sie absolut formuliert
      // sind (z.B. href="http://alice4n...onion/forum/viewtopic.php?id=42").
      var forumHost = ForensicToolbar.state.forumHostname || "";

      // Basispfad für relative URL-Auflösung.
      // Vorrang hat base_href aus dem BLOB-<head> — der Server kennt nach
      // Alias-Auflösung den tatsächlichen Dokumentpfad (z.B. liefert '/'
      // das Dokument aus '/forum/', dessen <base href="/forum/"> das korrekt
      // ausdrückt). Fallback: Verzeichnispfad von url_canonical.
      var basePath = ForensicToolbar.state.baseHref ||
        (function () {
          var cu = ForensicToolbar.state.currentUrl || "/";
          return cu.substring(0, cu.lastIndexOf("/") + 1) || "/";
        }());

      container.querySelectorAll("a[href]").forEach(function (a) {
        // target="_blank" entfernen — alle Navigationen bleiben im Shell-Frame
        if (a.getAttribute("target")) {
          a.removeAttribute("target");
        }

        a.addEventListener("click", function (e) {
          // a.href (Property, nicht Attribut) — der Browser hat <base href>
          // bereits berücksichtigt und liefert die vollständig aufgelöste
          // absolute URL.
          // Beispiel: <base href="/forum/beginner/">,
          //           <a href="viewforum.php?f=406">
          //           → a.href = "http://127.0.0.2:8080/forum/beginner/viewforum.php?f=406"
          var raw  = a.getAttribute("href") || "";
          var href = a.href || raw;

          if (!raw || raw.startsWith("#") || raw.startsWith("javascript:")) return;

          // Nur abfangen wenn lokaler Server oder Forum-Hostname
          var isLocal = href.includes(location.hostname);
          var isForum = forumHost && href.includes(forumHost);
          if (!isLocal && !isForum) return;

          // Protokoll und Host entfernen — nur Pfad an loadPage übergeben
          try {
            var parsed = new URL(href);
            href = parsed.pathname + parsed.search + parsed.hash;
          } catch (ex) {
            href = raw;
          }

          e.preventDefault();
          loadPage(href, true, "GET");
        });
      });

      // Form-Submit abfangen.
      // Das Forum sendet Poll-Abstimmungen als POST-Request über ein
      // <form method="post"> auf viewtopic.php. Damit der Webserver den
      // Poll-Ergebnis-BLOB ausliefert, muss original_method='POST' an
      // /_forensic/page übermittelt werden.
      // Alle anderen Forms (Antworten schreiben etc.) werden blockiert —
      // Ermittler nehmen keine aktiven Aktionen im Forum vor.
      //
      // Logik:
      //   - form.action wird wie ein Link aufgelöst (a.href-Equivalent)
      //   - form.method wird als original_method übergeben
      //   - Nur lokale/Forum-Forms werden abgefangen
      // Beleg: Projektgespräch 2026-04-19.
      container.querySelectorAll("form[action]").forEach(function (form) {
        form.addEventListener("submit", function (e) {
          e.preventDefault();

          // Action-URL vollständig auflösen (analog zu a.href)
          var actionRaw = form.getAttribute("action") || "";
          var actionHref;
          try {
            // Temporäres Anker-Element zur URL-Auflösung — nutzt <base href>
            var tmpA = document.createElement("a");
            tmpA.href = actionRaw;
            actionHref = tmpA.href;
          } catch (ex) {
            actionHref = actionRaw;
          }

          // Nur lokale oder Forum-URLs abfangen
          var isLocal = actionHref.includes(location.hostname);
          var isForum = forumHost && actionHref.includes(forumHost);
          if (!isLocal && !isForum) return;

          // Protokoll und Host entfernen
          var actionPath;
          try {
            var parsedAction = new URL(actionHref);
            actionPath = parsedAction.pathname + parsedAction.search;
          } catch (ex) {
            actionPath = actionRaw;
          }

          // form.method auslesen — 'post' oder 'get' (HTML-Standard, lowercase)
          // Beleg: Projektgespräch 2026-04-19.
          var formMethod = (form.method || "get").toUpperCase();

          loadPage(actionPath, true, formMethod);
        });
      });
    }

    function _detectPagination(viewport, envelope) {
      _prevUrl = null; _nextUrl = null;
      // FluxBB-Paginierung: Links mit rel="prev"/"next"
      var prevA = viewport.querySelector("a[rel='prev']");
      var nextA = viewport.querySelector("a[rel='next']");
      _prevUrl = prevA ? prevA.getAttribute("href") : null;
      _nextUrl = nextA ? nextA.getAttribute("href") : null;

      // Buttons aktivieren/deaktivieren je nach verfügbarer Paginierung
      var prevBtn  = document.getElementById("forensic-btn-nav-prev");
      var nextBtn  = document.getElementById("forensic-btn-nav-next");
      var pageInfo = document.getElementById("forensic-page-info");
      if (prevBtn)  prevBtn.disabled  = !_prevUrl;
      if (nextBtn)  nextBtn.disabled  = !_nextUrl;

      // Seiteninfo: "2 / 5" wenn Paginierung erkennbar, sonst leer
      if (pageInfo) {
        if (_prevUrl || _nextUrl) {
          // Seitenzahl aus URL extrahieren (?p=N) wenn vorhanden
          var curPage = null, totalPages = null;
          var pageLinks = viewport.querySelectorAll("a.paged-num, .pagination a, a[class*='page']");
          pageLinks.forEach(function (a) {
            var m = a.href && a.href.match(/[?&]p=(\d+)/);
            if (m) totalPages = Math.max(totalPages || 0, parseInt(m[1], 10));
          });
          var curM = (location.search || "").match(/[?&]p=(\d+)/);
          curPage  = curM ? parseInt(curM[1], 10) : (_prevUrl ? null : 1);
          if (curPage && totalPages) {
            pageInfo.textContent = curPage + " / " + totalPages;
          } else {
            pageInfo.textContent = _prevUrl ? "›" : "1";
          }
        } else {
          pageInfo.textContent = "";
        }
      }
    }

    function navigatePrev() {
      if (_prevUrl) loadPage(_prevUrl, true);
    }
    function navigateNext() {
      if (_nextUrl) loadPage(_nextUrl, true);
    }

    window.addEventListener("popstate", function (e) {
      var url = (e.state && e.state.forensicUrl) || location.pathname + location.search;
      loadPage(url, false);
    });

    return {
      loadPage:     loadPage,
      navigatePrev: navigatePrev,
      navigateNext: navigateNext,
    };
  })();

  // NavigationModule öffentlich exponieren — für Tests und externe Aufrufer.
  // Beleg: Projektgespräch 2026-04-19 — vitest-Tests benötigen Zugriff auf loadPage.
  ForensicToolbar.navigation = NavigationModule;

  // ===========================================================================
  // postMessage-Empfänger: Navigation aus Nutzerinfo-Tab und anderen Fenstern
  // ===========================================================================
  // Empfängt navigate_to_url-Nachrichten von Fenstern die dieses Hauptfenster
  // als opener oder parent haben (z.B. Nutzerinfo-Tab).
  // Beleg: Projektgespräch 2026-04-18 — Links in uid_aliases sollen im
  // Hauptfenster die AJAX-Navigation auslösen, nicht per <a href> navigieren.
  window.addEventListener("message", function (evt) {
    // Sicherheitsprüfung: nur Same-Origin-Nachrichten akzeptieren
    if (evt.origin !== window.location.origin) return;
    if (!evt.data || typeof evt.data !== "object") return;

    if (evt.data.type === "navigate_to_url") {
      var url = evt.data.url;
      if (typeof url === "string" && url.length > 0) {
        NavigationModule.loadPage(url, true);
      }
    }
  });

  // Build 173: BroadcastChannel 'forensic_navigation' — Navigation aus anderen
  // Fenstern (Fenster 2, Fenster 3) per BroadcastChannel empfangen.
  // Robuster als postMessage-Kette da kein opener noetig.
  // Beleg: Projektgespraech 2026-05-11
  (function() {
    if (typeof BroadcastChannel === 'undefined') return;
    var _navChannel = new BroadcastChannel('forensic_navigation');
    _navChannel.addEventListener('message', function(evt) {
      if (!evt.data || typeof evt.data !== 'object') return;
      if (evt.data.type === 'navigate_to_url') {
        var url = evt.data.url;
        if (typeof url === 'string' && url.length > 0) {
          NavigationModule.loadPage(url, true);
          // Empfang bestätigen damit Sender weiss, dass Navigation stattfindet
          _navChannel.postMessage({ type: 'navigate_ack', url: url });
        }
      }
    });
    // Fenster beim Server registrieren und Heartbeat alle 30s senden
    var _windowId = crypto.randomUUID ? crypto.randomUUID()
                  : Math.random().toString(36).slice(2);
    function _registerWindow() {
      fetch('/_forensic/windows', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Forensic-Request': 'ajax' },
        body: JSON.stringify({ window_id: _windowId, role: 'main' }),
      }).catch(function() {});
    }
    _registerWindow();
    setInterval(_registerWindow, 30000);
    window.addEventListener('unload', function() {
      navigator.sendBeacon('/_forensic/windows',
        new Blob([JSON.stringify({ window_id: _windowId })],
                 { type: 'application/json' }));
    });
  })();

  // ===========================================================================
  // PHASE 5: MarkerToolModule — Textmarkierungs-Workflow
  // ===========================================================================
  var MarkerToolModule = (function () {

    function toggleCategory(catId) {
      var current = _state.activeCategory;
      ForensicToolbar._setState({
        activeCategory: (current === catId) ? null : catId,
      });
    }

    function _onMouseUp(e) {
      var activeCat = _state.activeCategory;
      if (!activeCat) return;
      if (_state.viewMode === "original") return;

      var sel = window.getSelection();
      if (!sel || sel.isCollapsed) return;

      var selObj = AnnotationStoreModule.selectionFromBrowser(sel);
      if (!selObj) return;

      // Selektion sichern bevor sie verloren geht
      sel.removeAllRanges();

      // Annotation erstellen
      var ann = AnnotationStoreModule.createAnnotation(
        activeCat,
        _state.currentUrl,
        null,  // element_id: wird über XPath abgedeckt
        selObj,
        null
      );

      _state.annotations.set(ann.localId, ann);
      HighlightModule.render(ann);
      MinimapModule.refresh();
      AnnotationPopupModule.open(ann);
    }

    // Viewport abhören
    ForensicToolbar.events.on("page:loaded", function () {
      var vp = document.getElementById("forensic-viewport");
      if (vp) {
        // Alten Listener entfernen und neu setzen
        vp.removeEventListener("mouseup", _onMouseUp);
        vp.addEventListener("mouseup", _onMouseUp);
      }
    });

    return {
      toggleCategory: toggleCategory,
    };
  })();

  // ===========================================================================
  // PHASE 5: PostMarkerModule — Ganzen Post markieren
  // ===========================================================================
  var PostMarkerModule = (function () {
    // Beleg: §18.1 Bauplan — Selektor: article.post[id^="p"]
    var POST_SELECTOR = "article.post[id^='p']";

    function _onPostClick(e) {
      var activeCat = _state.activeCategory;
      if (!activeCat) return;
      if (_state.viewMode === "original") return;

      // Race-Condition-Guard: mouseup → _onMouseUp öffnet Popup für Textmarkierung,
      // dann feuert click → _onPostClick. _onMouseUp ruft removeAllRanges() auf,
      // deshalb ist die Selektion hier bereits kollabiert — der bisherige Guard
      // if (sel && !sel.isCollapsed) return  reichte nicht aus.
      // Lösung: Wenn das Popup bereits offen ist (von _onMouseUp geöffnet), nicht
      // als Post-Markierung behandeln.
      // Beleg: Build 063 — Textmarkierung wurde durch nachfolgenden click-Event als
      // Post-Markierung überschrieben (selection=null, post_id gesetzt).
      if (AnnotationPopupModule.isOpen()) return;

      // Nächsten Post-Container finden
      var target = e.target;
      var postEl = target.closest ? target.closest(POST_SELECTOR) : null;
      if (!postEl) return;

      // Prüfen ob Textmarkierung stattfindet (dann nicht als Post markieren)
      var sel = window.getSelection();
      if (sel && !sel.isCollapsed) return;

      var postId = parseInt(postEl.id.substring(1), 10);
      if (isNaN(postId)) return;

      // Bereits markiert? → Konflikt-Dialog (§7.2 Bauplan)
      var existingAnn = null;
      _state.annotations.forEach(function (ann) {
        if (ann.postId === postId) existingAnn = ann;
      });

      if (existingAnn) {
        var cat = _getCat(existingAnn.category);
        var catLabel = cat ? cat.label : existingAnn.category;
        if (!confirm("Post #" + postId + " ist bereits als [" + catLabel + "] markiert.\nÜberschreiben?")) {
          return;
        }
        // Alten Eintrag entfernen
        _state.annotations.delete(existingAnn.localId || String(existingAnn.id));
        _removePostVisual(postEl);
      }

      var ann = AnnotationStoreModule.createAnnotation(
        activeCat,
        _state.currentUrl,
        postEl.id,
        null,  // kein selection-Objekt bei Post-Markierung
        postId
      );

      _state.annotations.set(ann.localId, ann);
      _applyPostVisual(postEl, activeCat);
      MinimapModule.refresh();
      AnnotationPopupModule.open(ann);
      e.stopPropagation();
    }

    /** Visuellen Rahmen auf Post anwenden (reversibler DOM-Eingriff, §11 GR11b) */
    function _applyPostVisual(postEl, catId) {
      var cat = _getCat(catId);
      if (!cat) return;
      postEl.dataset.forensicCat = catId;
      postEl.style.borderLeft    = "5px solid " + cat.color;
      postEl.style.background    = cat.color + "0a";
    }

    /** Visuellen Rahmen entfernen (Reversibilität) */
    function _removePostVisual(postEl) {
      delete postEl.dataset.forensicCat;
      postEl.style.borderLeft = "";
      postEl.style.background = "";
    }

    /** Alle Post-Markierungen entfernen (viewmode:original) */
    function clearAll() {
      document.querySelectorAll("[data-forensic-cat]").forEach(function (el) {
        _removePostVisual(el);
      });
    }

    /** Alle Post-Markierungen aus State wiederherstellen (viewmode:enhanced) */
    function restoreAll() {
      _state.annotations.forEach(function (ann) {
        if (!ann.postId) return;
        var postEl = document.getElementById("p" + ann.postId);
        if (postEl) _applyPostVisual(postEl, ann.category);
      });
    }

    // Viewport abhören
    ForensicToolbar.events.on("page:loaded", function () {
      var vp = document.getElementById("forensic-viewport");
      if (vp) {
        vp.removeEventListener("click", _onPostClick);
        vp.addEventListener("click", _onPostClick);
      }
    });

    ForensicToolbar.events.on("viewmode:original",  clearAll);
    ForensicToolbar.events.on("viewmode:enhanced",  restoreAll);

    return { clearAll: clearAll, restoreAll: restoreAll };
  })();

  // ===========================================================================
  // PHASE 6: AnnotationPopupModule — Schwebendes Editor-Feld
  // ===========================================================================
  //
  // Build 175 (BS3):
  //   Bug 2.76: Kategorie-Dropdown im Popup — Kategorie nachträglich änderbar.
  //             Dropdown zeigt Icon + Label jeder Kategorie; Auswahl aktualisiert
  //             _currentAnn.category und den Titel-Badge sofort.
  //   Bug 2.77: Forenbenutzer-Anzeige im Popup — zeigt user_id + username des
  //             Beschuldigten, zu dem die Annotation gehört.
  //   Bug 2.78: Benutzer-Wechsel-Schaltfläche — Annotation einem anderen
  //             bekannten Beschuldigten zuordnen. Lädt bekannte Benutzer per
  //             GET /_forensic/knownusers (lazy, wird gecacht).
  //             Bei Wechsel: _currentAnn.targetUserId wird gesetzt; server-side
  //             schreibt die Annotation in coordinator.db statt evidence_db.
  //   Beleg: Projektgespräch 2026-05-11
  // ===========================================================================
  var AnnotationPopupModule = (function () {
    'use strict';

    var _currentAnn   = null;  // Aktuell bearbeitete Annotation
    var _popupEl      = null;  // DOM-Element des Popups

    // Cache für bekannte Benutzer (Bug 2.78) — wird einmalig geladen
    // Format: [{user_id: 538299, username: "uid_538299"}, ...]
    var _knownUsersCache = null;   // null = noch nicht geladen
    var _knownUsersLoading = false; // Ladevorgang läuft

    // =========================================================================
    // Öffentliche API
    // =========================================================================

    function open(ann) {
      _currentAnn = ann;
      _render(ann);
      // Bekannte Benutzer vorladen (Bug 2.78) — im Hintergrund, kein Blockieren
      _preloadKnownUsers();
    }

    function close(save) {
      if (save && _currentAnn) {
        _currentAnn.text     = _getFieldValue("forensic-popup-text");
        _currentAnn.tags     = _parseTags(_getFieldValue("forensic-popup-tags"));
        // Bug 2.76: Kategorie aus Dropdown übernehmen
        var selCat = _getFieldValue("forensic-popup-category");
        if (selCat) { _currentAnn.category = selCat; }
        AnnotationStoreModule.syncAnnotation(_currentAnn);
        // Semantisch korrekt: "created" nur bei neuen Annotationen (noch keine
        // Server-ID), "updated" bei bereits persistierten.
        // Beleg: OP-KN-9 Build 059
        var evtName = _currentAnn.id ? "annotation:updated" : "annotation:created";
        ForensicToolbar.events.emit(evtName, _currentAnn);
      } else if (!save && _currentAnn && _currentAnn.syncState === "pending") {
        // Abbrechen: pending-Annotation entfernen
        _state.annotations.delete(_currentAnn.localId || String(_currentAnn.id));
        HighlightModule.clearAll();
        HighlightModule.restoreAll();
        MinimapModule.refresh();
      }
      if (_popupEl) {
        _popupEl.remove();
        _popupEl = null;
      }
      _currentAnn = null;
    }

    // =========================================================================
    // Rendering
    // =========================================================================

    function _render(ann) {
      if (_popupEl) _popupEl.remove();

      var cat      = _getCat(ann.category);
      var catLabel = cat ? (cat.icon + " " + cat.label) : ann.category;
      var catColor = cat ? cat.color : "#aaa";

      // Bug 2.77: Forenbenutzer aus State lesen
      // _state.username = Beschuldigter (forum username), user_id = forum user_id
      var forumUser    = _state.username || ("uid_" + _state.user_id) || "—";
      var forumUserId  = _state.user_id  || "—";

      // Kategorie-Optionen für Dropdown (Bug 2.76)
      var catOptions = "";
      var cats = ForensicToolbar.config.CATEGORIES || [];
      for (var ci = 0; ci < cats.length; ci++) {
        var c = cats[ci];
        var sel = (c.id === ann.category) ? ' selected' : '';
        catOptions += '<option value="' + _esc(c.id) + '"' + sel + '>' +
          _esc(c.icon + " " + c.label) + '</option>';
      }

      _popupEl = document.createElement("div");
      _popupEl.id = "forensic-annotation-popup";
      _popupEl.setAttribute("role", "dialog");
      _popupEl.setAttribute("aria-modal", "true");
      _popupEl.setAttribute("aria-labelledby", "forensic-popup-title");
      _popupEl.className = "forensic-popup";
      _popupEl.innerHTML =
        // --- Header ---
        '<div class="forensic-popup-header">' +
        '<span id="forensic-popup-title" class="forensic-popup-title">' +
        'Annotation · <span id="forensic-popup-cat-badge" style="color:' + catColor + '">' +
        _esc(catLabel) + '</span></span>' +
        '<button class="forensic-popup-close" aria-label="Schließen" ' +
        'id="forensic-popup-btn-close">✕</button>' +
        '</div>' +
        // --- Body ---
        '<div class="forensic-popup-body">' +

        // Bug 2.76: Kategorie-Dropdown
        '<label for="forensic-popup-category" class="forensic-popup-label">Kategorie:</label>' +
        '<select id="forensic-popup-category" class="forensic-popup-select" ' +
        'aria-label="Kategorie auswählen">' +
        catOptions +
        '</select>' +

        // Bug 2.77: Forenbenutzer-Anzeige
        '<div class="forensic-popup-user-row">' +
        '<span class="forensic-popup-label forensic-popup-label--inline">Benutzer:</span>' +
        '<span id="forensic-popup-user-display" class="forensic-popup-user-badge" ' +
        'title="Forum-User-ID: ' + _esc(String(forumUserId)) + '">' +
        _esc(forumUser) + '</span>' +
        // Bug 2.78: Wechsel-Schaltfläche
        '<button id="forensic-popup-btn-change-user" ' +
        'class="forensic-btn forensic-btn-xs forensic-btn-secondary" ' +
        'title="Annotation einem anderen Beschuldigten zuordnen" ' +
        'aria-label="Benutzer wechseln">↔</button>' +
        '</div>' +
        // Benutzer-Wechsel-Panel (Bug 2.78) — initial versteckt
        '<div id="forensic-popup-user-panel" class="forensic-popup-user-panel" ' +
        'style="display:none" aria-live="polite">' +
        '<span class="forensic-popup-hint">Lade bekannte Benutzer…</span>' +
        '</div>' +

        // Notiz
        '<label for="forensic-popup-text" class="forensic-popup-label">Notiz (optional):</label>' +
        '<textarea id="forensic-popup-text" class="forensic-popup-textarea" ' +
        'aria-label="Ermittlungsnotiz eingeben" rows="3">' + _esc(ann.text) + '</textarea>' +

        // Tags
        '<label for="forensic-popup-tags" class="forensic-popup-label">Tags (mit Komma trennen):</label>' +
        '<input type="text" id="forensic-popup-tags" class="forensic-popup-input" ' +
        'aria-label="Tags eingeben, mit Komma getrennt" value="' +
        _esc((ann.tags || []).join(", ")) + '">' +
        '<div id="forensic-popup-tag-suggestion" class="forensic-popup-suggestion" ' +
        'style="display:none"></div>' +

        // Markierter Text (wenn vorhanden)
        (ann.selection ?
          '<label class="forensic-popup-label">Markierter Text:</label>' +
          '<div class="forensic-popup-seltext">' + _esc(ann.selection.textContent) + '</div>' : "") +

        '</div>' +
        // --- Footer ---
        '<div class="forensic-popup-footer">' +
        '<button id="forensic-popup-btn-cancel" class="forensic-btn forensic-btn-secondary">Abbrechen</button>' +
        '<button id="forensic-popup-btn-save" class="forensic-btn forensic-btn-primary">💾 Speichern</button>' +
        '</div>';

      document.body.appendChild(_popupEl);
      _positionPopup(ann);

      // Fokus auf Notiz-Feld (§8 Bauplan)
      var txtArea = document.getElementById("forensic-popup-text");
      if (txtArea) txtArea.focus();

      // --- Event-Listener ---

      document.getElementById("forensic-popup-btn-close").addEventListener("click", function () { close(false); });
      document.getElementById("forensic-popup-btn-cancel").addEventListener("click", function () { close(false); });
      document.getElementById("forensic-popup-btn-save").addEventListener("click", function () { close(true); });

      // Bug 2.76: Kategorie-Dropdown — Badge sofort aktualisieren bei Änderung
      var catSelect = document.getElementById("forensic-popup-category");
      if (catSelect) {
        catSelect.addEventListener("change", function () {
          var newCat    = catSelect.value;
          var newCatObj = _getCat(newCat);
          var badge     = document.getElementById("forensic-popup-cat-badge");
          if (badge && newCatObj) {
            badge.textContent = newCatObj.icon + " " + newCatObj.label;
            badge.style.color = newCatObj.color;
          }
          if (_currentAnn) { _currentAnn.category = newCat; }
          _dbg("[Popup] Kategorie geändert auf:", newCat);
        });
      }

      // Bug 2.78: Benutzer-Wechsel-Schaltfläche
      var btnChangeUser = document.getElementById("forensic-popup-btn-change-user");
      if (btnChangeUser) {
        btnChangeUser.addEventListener("click", function () {
          _toggleUserPanel();
        });
      }

      // Levenshtein-Vorschlag beim Tag-Tippen (§19.2 Bauplan)
      var tagInput = document.getElementById("forensic-popup-tags");
      if (tagInput) {
        tagInput.addEventListener("input", function () {
          var last  = (tagInput.value.split(",").pop() || "").trim();
          var sug   = ForensicToolbar.config.suggestTag(last, []);
          var sugEl = document.getElementById("forensic-popup-tag-suggestion");
          if (sugEl && sug && sug !== last) {
            sugEl.style.display = "block";
            sugEl.innerHTML = 'Meinten Sie: <button class="forensic-tag-suggest-btn" ' +
              'onclick="document.getElementById(\'forensic-popup-tags\').value = ' +
              'document.getElementById(\'forensic-popup-tags\').value.replace(/[^,]*$/, \'' +
              sug + '\');document.getElementById(\'forensic-popup-tag-suggestion\').style.display=\'none\'">' +
              _esc(sug) + '</button>?';
          } else if (sugEl) {
            sugEl.style.display = "none";
          }
        });
      }

      // Focus-Trap (§8 Bauplan): Tab verlässt Popup nicht
      _popupEl.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { close(false); }
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { close(true); }
        if (e.key === "Tab") {
          var focusable = _popupEl.querySelectorAll(
            "button, textarea, input, select, [tabindex]:not([tabindex='-1'])"
          );
          if (!focusable.length) return;
          var first = focusable[0];
          var last2 = focusable[focusable.length - 1];
          if (e.shiftKey) {
            if (document.activeElement === first) { e.preventDefault(); last2.focus(); }
          } else {
            if (document.activeElement === last2) { e.preventDefault(); first.focus(); }
          }
        }
      });
    }

    // =========================================================================
    // Bug 2.78: Benutzer-Wechsel-Panel
    // =========================================================================

    /**
     * Schaltet das Benutzer-Wechsel-Panel um (auf/zu).
     * Beim ersten Öffnen: Benutzer aus Cache oder Server laden.
     */
    function _toggleUserPanel() {
      var panel = document.getElementById("forensic-popup-user-panel");
      if (!panel) return;

      var isOpen = panel.style.display !== "none";
      if (isOpen) {
        panel.style.display = "none";
        _dbg("[Popup] Benutzer-Panel geschlossen");
        return;
      }

      // Panel öffnen
      panel.style.display = "block";
      _dbg("[Popup] Benutzer-Panel geöffnet");

      if (_knownUsersCache !== null) {
        // Cache vorhanden → sofort rendern
        _renderUserPanel(panel, _knownUsersCache);
      } else if (!_knownUsersLoading) {
        // Noch nicht geladen → jetzt laden
        _loadKnownUsers(function (users) {
          _renderUserPanel(panel, users);
        });
      } else {
        // Ladevorgang läuft bereits → Lade-Hinweis bleibt stehen
        _dbg("[Popup] Benutzer werden bereits geladen…");
      }
    }

    /**
     * Rendert die Benutzer-Liste in das Panel.
     * Jeder Eintrag hat einen Button, der die Annotation diesem Benutzer
     * zuordnet und den Benutzer-Badge im Header aktualisiert.
     */
    function _renderUserPanel(panel, users) {
      if (!users || users.length === 0) {
        panel.innerHTML = '<span class="forensic-popup-hint">Keine weiteren Benutzer bekannt.</span>';
        return;
      }

      var html = '<span class="forensic-popup-label forensic-popup-label--sm">' +
        'Annotation zuordnen:</span><div class="forensic-popup-user-list">';

      for (var i = 0; i < users.length; i++) {
        var u       = users[i];
        var isCurr  = (_currentAnn && _currentAnn.targetUserId === u.user_id);
        // Aktueller Beschuldigter des aktiven Jobs
        var isActive = (u.user_id === _state.user_id);
        var btnCls  = "forensic-btn forensic-btn-xs" +
          (isCurr || isActive ? " forensic-btn-primary" : " forensic-btn-secondary");
        var indicator = isActive ? " ✓" : "";

        html += '<button class="' + btnCls + '" ' +
          'data-uid="' + _esc(String(u.user_id)) + '" ' +
          'data-uname="' + _esc(u.username) + '" ' +
          'title="User-ID: ' + _esc(String(u.user_id)) + '">' +
          _esc(u.username) + indicator + '</button>';
      }
      html += '</div>';
      panel.innerHTML = html;

      // Event-Delegation: Klick auf Benutzer-Button
      panel.addEventListener("click", function (e) {
        var btn = e.target.closest("button[data-uid]");
        if (!btn) return;

        var uid   = parseInt(btn.getAttribute("data-uid"), 10);
        var uname = btn.getAttribute("data-uname");

        _dbg("[Popup] Benutzer-Wechsel →", uid, uname);

        // Annotation dem neuen Benutzer zuordnen
        if (_currentAnn) {
          _currentAnn.targetUserId   = uid;
          _currentAnn.targetUsername = uname;
        }

        // Badge aktualisieren
        var badge = document.getElementById("forensic-popup-user-display");
        if (badge) {
          badge.textContent = uname;
          badge.title       = "Forum-User-ID: " + uid;
        }

        // Panel schließen
        var panelEl = document.getElementById("forensic-popup-user-panel");
        if (panelEl) panelEl.style.display = "none";

        // Alle Buttons neu markieren
        var allBtns = panel.querySelectorAll("button[data-uid]");
        allBtns.forEach(function (b) {
          b.classList.remove("forensic-btn-primary");
          b.classList.add("forensic-btn-secondary");
        });
        btn.classList.remove("forensic-btn-secondary");
        btn.classList.add("forensic-btn-primary");
      });
    }

    /**
     * Lädt bekannte Benutzer vom Server (Bug 2.78).
     * Ergebnis wird in _knownUsersCache gespeichert.
     * callback(users) wird nach erfolgreichem Laden aufgerufen.
     */
    function _loadKnownUsers(callback) {
      _knownUsersLoading = true;
      _dbg("[Popup] Lade bekannte Benutzer von", ForensicToolbar.config.API_KNOWN_USERS);

      ajaxGet(ForensicToolbar.config.API_KNOWN_USERS)
        .then(function (data) {
          _knownUsersCache   = (data && Array.isArray(data.users)) ? data.users : [];
          _knownUsersLoading = false;
          _dbg("[Popup] Bekannte Benutzer geladen:", _knownUsersCache.length);
          if (callback) callback(_knownUsersCache);
        })
        .catch(function (err) {
          _knownUsersLoading = false;
          _knownUsersCache   = [];  // Leerer Cache verhindert erneute Ladeversuche
          _dbg("[Popup] Fehler beim Laden der Benutzer:", err);
          if (callback) callback([]);
        });
    }

    /**
     * Lädt bekannte Benutzer im Hintergrund vor (ohne Callback).
     * Wird beim Öffnen des Popups aufgerufen damit der Cache bereit ist.
     */
    function _preloadKnownUsers() {
      if (_knownUsersCache !== null || _knownUsersLoading) return;
      _loadKnownUsers(null);
    }

    // =========================================================================
    // Positionierung und Hilfsfunktionen
    // =========================================================================

    /** Popup nah an Markierung positionieren, nie über Toolbar (§8 Bauplan) */
    function _positionPopup(ann) {
      if (!_popupEl) return;
      var tb = ForensicToolbar.config.TOOLBAR_HEIGHT;
      var pw = _popupEl.offsetWidth  || 440;
      var ph = _popupEl.offsetHeight || 340;
      var vw = window.innerWidth;
      var vh = window.innerHeight;

      var left = Math.max(8, Math.min(vw - pw - 8, (vw - pw) / 2));
      var top  = tb + 8;

      // Wenn Platz unter aktueller Scrollposition → nahe Mitte
      if (vh - tb - 8 > ph) {
        top = tb + Math.max(8, (vh - tb - ph) / 3);
      }

      _popupEl.style.left = left + "px";
      _popupEl.style.top  = top  + "px";
    }

    function _getFieldValue(id) {
      var el = document.getElementById(id);
      return el ? el.value : "";
    }

    function _parseTags(raw) {
      return (raw || "").split(",")
        .map(function (t) { return t.trim(); })
        .filter(function (t) { return t.length > 0; });
    }

    return { open: open, close: close, isOpen: function () { return !!_popupEl; } };
  })();

  // ===========================================================================
  // PHASE 6: HoverMenuModule  // ===========================================================================
  // PHASE 6: HoverMenuModule — Mini-Werkzeugleiste beim Hover
  // ===========================================================================
  var HoverMenuModule = (function () {
    var _timer      = null;
    var _menuEl     = null;
    var _targetAnn  = null;
    // Letzte bekannte Mausposition — wird bei mousemove auf dem Viewport aktuell gehalten.
    // Beleg: Build 061 — setTimeout-Callback liest e.pageX/Y aus vergangenem mouseover-
    // Event, das veraltet ist. _lastMousePos gibt die aktuelle Position zum Feuerzeitpunkt.
    var _lastMouseX = 0;
    var _lastMouseY = 0;

    function _findAnnotationAtElement(el) {
      // Annotation über element_id oder data-forensic-annotation finden
      var annId = el.dataset && el.dataset.forensicAnnotation;
      if (annId) {
        var found = null;
        _state.annotations.forEach(function (ann) {
          if ((ann.localId === annId) || (String(ann.id) === annId)) found = ann;
        });
        return found;
      }
      // Post-Markierung
      var postEl = el.closest ? el.closest("[data-forensic-cat]") : null;
      if (postEl) {
        var pid = parseInt((postEl.id || "").substring(1), 10);
        if (!isNaN(pid)) {
          var found2 = null;
          _state.annotations.forEach(function (ann) {
            if (ann.postId === pid) found2 = ann;
          });
          return found2;
        }
      }
      return null;
    }

    /**
     * Alle Annotationen ermitteln die einen bestimmten Dokumentpunkt (pageX/Y)
     * abdecken. Berücksichtigt:
     *   - CSS Custom Highlights: Range-Vergleich via caretRangeFromPoint/
     *     caretPositionFromPoint
     *   - <mark>-Fallback: data-forensic-annotation am Element
     *   - Post-Markierungen: data-forensic-cat am Container
     *
     * Beleg: Build 064 — Textmarkierungen haben im CSS-Highlights-Pfad keine
     * DOM-Elemente, daher keine mouseover-Events. Lösung: Punkttest gegen
     * gespeicherte Ranges beim Mousemove/Mouseover.
     */
    function _findAnnotationsAtPoint(clientX, clientY) {
      var found = [];

      // 1. Fallback-Pfad: <mark>-Elemente mit data-forensic-annotation
      var el = document.elementFromPoint(clientX, clientY);
      if (el) {
        var markEl = el.closest ? el.closest("[data-forensic-annotation]") : null;
        if (markEl) {
          var annId = markEl.dataset.forensicAnnotation;
          _state.annotations.forEach(function (ann) {
            var key = ann.localId || String(ann.id);
            if (key === annId) found.push(ann);
          });
        }

        // Post-Markierung am Container
        var postEl = el.closest ? el.closest("[data-forensic-cat]") : null;
        if (postEl) {
          var pid = parseInt((postEl.id || "").substring(1), 10);
          if (!isNaN(pid)) {
            _state.annotations.forEach(function (ann) {
              if (ann.postId === pid) {
                // Nur wenn noch nicht aus mark-Suche vorhanden
                var alreadyFound = false;
                found.forEach(function (a) { if (a === ann) alreadyFound = true; });
                if (!alreadyFound) found.push(ann);
              }
            });
          }
        }
      }

      // 2. CSS Custom Highlights Primärpfad: Range-Punkttest
      // Prüft ob der Punkt innerhalb einer der gespeicherten Annotation-Ranges liegt.
      // Methode: caretRangeFromPoint (Chrome/FF) oder caretPositionFromPoint (Firefox)
      if (found.length === 0) {
        var caretRange = null;
        if (document.caretRangeFromPoint) {
          caretRange = document.caretRangeFromPoint(clientX, clientY);
        } else if (document.caretPositionFromPoint) {
          var pos = document.caretPositionFromPoint(clientX, clientY);
          if (pos) {
            caretRange = document.createRange();
            caretRange.setStart(pos.offsetNode, pos.offset);
            caretRange.setEnd(pos.offsetNode, pos.offset);
          }
        }

        if (caretRange) {
          _state.annotations.forEach(function (ann) {
            if (!ann.selection) return;
            var restored = AnnotationStoreModule.rangeFromSelection(ann.selection);
            if (!restored) return;
            var r = restored.range;
            // Punkt ist in Range wenn: range.START_TO_START <= 0 UND range.END_TO_END >= 0
            try {
              var cmp1 = r.compareBoundaryPoints(Range.START_TO_START, caretRange);
              var cmp2 = r.compareBoundaryPoints(Range.END_TO_END, caretRange);
              if (cmp1 <= 0 && cmp2 >= 0) found.push(ann);
            } catch (ex) { /* Range ungültig — überspringen */ }
          });
        }
      }

      return found;
    }

    /**
     * Menü anzeigen. Unterstützt einzelne Annotation und Liste.
     * Bei mehreren Annotationen (Textmarkierungen + Post, oder überlappende Texte):
     * Vertikale Liste mit Identifikation (Kategorie-Icon, Textkürzel) + Edit/Delete.
     *
     * Beleg: Build 154 — Textmarkierungen haben keinen HoverMenu-Trigger über
     * Post-Container-Delegation. Multi-Annotation-Ansicht löst auch Überlappungen.
     * Kategorie der Markierung kann geändert werden.
     */
     function _showMenu(ann, x, y) {
       _hideMenu();
       _targetAnn = ann;
       
       var activeCatId = ann.category;
       
       _menuEl = document.createElement("div");
       _menuEl.className = "forensic-hover-menu";
       _menuEl.setAttribute("role", "menu");
       _menuEl.setAttribute("aria-label", "Annotation-Menü");
       
       // Feste Aktionen (Edit + Delete)
       var actionsHtml = 
         '<div class="forensic-hover-actions" role="group" aria-label="Aktionen">' +
           '<button class="forensic-hover-btn" data-action="edit" aria-label="Annotation bearbeiten">✏️</button>' +
           '<button class="forensic-hover-btn" data-action="delete" aria-label="Annotation löschen">🗑️</button>' +
         '</div>';
       
       // Kategorie-Container mit allen 6 Buttons (OHNE Overlay hier)
       var catsHtml = '<div class="forensic-hover-cats" role="group" aria-label="Kategorie auswählen">';
       
       ForensicToolbar.config.CATEGORIES.forEach(function(c) {
         var isActive = (c.id === activeCatId);
         var activeClass = isActive ? ' forensic-hover-cat-wrapper--active' : '';
         catsHtml += 
           '<div class="forensic-hover-cat-wrapper' + activeClass + '" data-cat-id="' + c.id + '" ' +
           'role="menuitem" tabindex="-1" aria-label="Kategorie ' + c.label + '">' +
          '<span class="forensic-cat-icon" aria-hidden="true">' + c.icon + '</span>' +
          '<span class="forensic-cat-label">' + c.label + '</span>' +
           '</div>';
       });
       
       catsHtml += '</div>';
       
       _menuEl.innerHTML = actionsHtml + catsHtml;
       
       // Positionierung (nach Ihrer Korrektur: x und y direkt)
       _menuEl.style.left = x + "px";
       _menuEl.style.top  = y + "px";
       document.body.appendChild(_menuEl);
       
       // Events binden
       _bindHoverMenuEvents(_menuEl, _targetAnn);
     }

    function _bindHoverMenuEvents(menuEl, ann) {
      // Event-Delegation: Ein einziger Listener auf dem Menü fängt alle Klicks ab
      menuEl.addEventListener("click", function(e) {
        // Edit-Button
        var editBtn = e.target.closest("[data-action='edit']");
        if (editBtn) {
          e.stopPropagation();
          _hideMenu();
          AnnotationPopupModule.open(ann);
          return;
        }
        
        // Delete-Button
        var deleteBtn = e.target.closest("[data-action='delete']");
        if (deleteBtn) {
          e.stopPropagation();
          _hideMenu();
          _deleteAnnotation(ann);
          return;
        }
        
        // Kategorie-Wrapper
        var catWrapper = e.target.closest(".forensic-hover-cat-wrapper");
        if (!catWrapper) return;
        
        e.stopPropagation();
        var isExpanded = menuEl.classList.contains("forensic-hover-menu--expanded");
        var clickedCatId = catWrapper.dataset.catId;
        var isActive = catWrapper.classList.contains("forensic-hover-cat-wrapper--active");
        
        // Fall 1: Im kompakten Zustand -> nur der aktive Button ist sichtbar
        if (!isExpanded) {
          // Nur wenn der geklickte Wrapper der aktive ist, expandieren
          if (isActive) {
        _expandCategoryMenu(menuEl, ann);
          }
          return;
        }
        
        // Fall 2: Im expandierten Zustand
        if (isExpanded) {
          // Wenn der geklickte Wrapper der aktive ist -> nur einklappen
          if (isActive) {
        _collapseCategoryMenu(menuEl);
        return;
          }
          
          // Andernfalls: Kategorie ändern
          if (clickedCatId !== ann.category) {
        _changeAnnotationCategory(ann, clickedCatId);
          }
          _collapseCategoryMenu(menuEl);
        }
      });
      
      // Tastatursteuerung bleibt bestehen
      _setupHoverKeyboard(menuEl, ann, menuEl.querySelector(".forensic-hover-cats"), menuEl.querySelectorAll(".forensic-hover-cat-wrapper"));
    } 

    function _expandCategoryMenu(menuEl, ann) {
      if (menuEl.classList.contains("forensic-hover-menu--expanded")) return;
      
      menuEl.classList.add("forensic-hover-menu--expanded");
      menuEl.setAttribute("aria-label", "Annotation-Menü – Kategorieauswahl erweitert");
      
      // Fokus auf den aktiven Button setzen (für Tastatur)
      var activeWrapper = menuEl.querySelector(".forensic-hover-cat-wrapper--active");
      if (activeWrapper) {
        activeWrapper.setAttribute("tabindex", "0");
        activeWrapper.focus();
      }
    }

    function _collapseCategoryMenu(menuEl) {
      if (!menuEl.classList.contains("forensic-hover-menu--expanded")) return;
      
      menuEl.classList.remove("forensic-hover-menu--expanded");
      menuEl.setAttribute("aria-label", "Annotation-Menü");
      
      // Tabindex zurücksetzen: nur der aktive Button fokussierbar
      var allWrappers = menuEl.querySelectorAll(".forensic-hover-cat-wrapper");
      allWrappers.forEach(function(w) {
        w.setAttribute("tabindex", "-1");
      });
      
      var activeWrapper = menuEl.querySelector(".forensic-hover-cat-wrapper--active");
      if (activeWrapper) {
        activeWrapper.setAttribute("tabindex", "0");
        // Optional: Fokus zurücksetzen auf den aktiven Button (nicht zwingend)
        // activeWrapper.focus();
      }
    }

    function _setupHoverKeyboard(menuEl, ann, catsContainer, catWrappers) {
      menuEl.addEventListener("keydown", function(e) {
        var isExpanded = menuEl.classList.contains("forensic-hover-menu--expanded");
        var activeElement = document.activeElement;
        var currentIndex = -1;
        
        // Prüfen ob eines der Category-Wrapper fokussiert ist
        catWrappers.forEach(function(w, idx) {
          if (w === activeElement) currentIndex = idx;
        });
        
        // Escape: immer schließen (ohne Änderung)
        if (e.key === "Escape") {
          e.preventDefault();
          if (isExpanded) {
        _collapseCategoryMenu(menuEl);
          } else {
        _hideMenu();
          }
          return;
        }
        
        // Im expandierten Modus: Pfeiltasten-Navigation
        if (isExpanded && currentIndex !== -1) {
          if (e.key === "ArrowRight") {
        e.preventDefault();
        var nextIndex = (currentIndex + 1) % catWrappers.length;
        catWrappers[nextIndex].focus();
          } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        var prevIndex = (currentIndex - 1 + catWrappers.length) % catWrappers.length;
        catWrappers[prevIndex].focus();
          } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        var newCatId = catWrappers[currentIndex].dataset.catId;
        if (newCatId !== ann.category) {
          _changeAnnotationCategory(ann, newCatId);
        }
        _collapseCategoryMenu(menuEl);
          }
        } else if (!isExpanded && currentIndex !== -1 && (e.key === "Enter" || e.key === " ")) {
          // Kompakter Modus: Enter auf aktivem Button expandiert
          e.preventDefault();
          _expandCategoryMenu(menuEl, ann);
        }
      });
    }

    function _changeAnnotationCategory(ann, newCatId) {
      if (ann.category === newCatId) return;
      
      var oldCatId = ann.category;
      ann.category = newCatId;
      ann.syncState = "pending";
      
      // Visuelles Update
      HighlightModule.clearAll();
      HighlightModule.restoreAll();
      PostMarkerModule.clearAll();
      PostMarkerModule.restoreAll();
      MinimapModule.refresh();
      
      // Server-Sync
      AnnotationStoreModule.syncAnnotation(ann);
      
      // Event für andere Module (z.B. für Zähler im Toolbar)
      ForensicToolbar.events.emit("annotation:category_changed", {
        ann: ann,
        oldCat: oldCatId,
        newCat: newCatId
      });
      
      AccessibilityModule.announce("Kategorie geändert von " + oldCatId + " zu " + newCatId);

      // *** NEU: Aktualisiere das Hover-Menü, falls es noch offen ist ***
      if (_menuEl) {
        // Hole den aktiven Wrapper im aktuellen Menü
        var oldActiveWrapper = _menuEl.querySelector('.forensic-hover-cat-wrapper--active');
        if (oldActiveWrapper) {
          oldActiveWrapper.classList.remove('forensic-hover-cat-wrapper--active');
        }
        
        // Finde den neuen Wrapper anhand der data-cat-id
        var newActiveWrapper = _menuEl.querySelector('.forensic-hover-cat-wrapper[data-cat-id="' + newCatId + '"]');
        if (newActiveWrapper) {
          newActiveWrapper.classList.add('forensic-hover-cat-wrapper--active');
          newActiveWrapper.style.position = 'relative';
        }
        
        // Aktualisiere die Tab-Indizes (nur der neue aktive Button soll fokussierbar sein im kompakten Zustand)
        var allWrappers = _menuEl.querySelectorAll('.forensic-hover-cat-wrapper');
        allWrappers.forEach(function(w) {
          w.setAttribute('tabindex', '-1');
        });
        if (newActiveWrapper) {
          newActiveWrapper.setAttribute('tabindex', '0');
        }
      }        
    }
	  
    /**
     * Menü für eine Liste von Annotationen — erscheint wenn mehrere Annotations
     * an einem Punkt vorliegen (Textmarkierungen, Überlappungen, gemischt).
     *
     * Layout: Pro Annotation eine Zeile mit:
     *   [Kategorie-Icon] [Textkürzel 40 Zeichen] [✏️] [🗑️]
     *
     * Beleg: Build 064 — Textmarkierungen (CSS Custom Highlights) haben keine
     * DOM-Elemente für mouseover. Multi-Annotation-View als Workaround.
     */
    function _showMenuForList(anns, x, y) {
      _hideMenu();
      if (anns.length === 1) {
        _showMenu(anns[0], x, y);
        return;
      }
      _targetAnn = anns[0]; // Fallback
      _menuEl = document.createElement("div");
      _menuEl.className = "forensic-hover-menu forensic-hover-menu--list";
      _menuEl.style.left = x + "px";
      _menuEl.style.top  = y + "px";

      var html = '<div class="forensic-hover-list-header">Annotationen (' + anns.length + ')</div>';
      anns.forEach(function (ann, idx) {
        var cat = _getCat(ann.category);
        var icon = cat ? cat.icon : "📎";
        var label = ann.selection
          ? (ann.selection.textContent || "").substring(0, 40).replace(/\s+/g, " ").trim()
          : (ann.text || "Post #" + ann.postId || "—").substring(0, 40);
        if (label.length === 40) label += "…";
        html +=
          '<div class="forensic-hover-list-row" data-ann-idx="' + idx + '">' +
          '<span class="forensic-hover-list-cat" title="' + _esc(ann.category) + '">' + icon + '</span>' +
          '<span class="forensic-hover-list-label">' + _esc(label) + '</span>' +
          '<button class="forensic-hover-btn" data-action="edit" data-ann-idx="' + idx + '" aria-label="Bearbeiten">✏️</button>' +
          '<button class="forensic-hover-btn" data-action="delete" data-ann-idx="' + idx + '" aria-label="Löschen">🗑️</button>' +
          '</div>';
      });
      _menuEl.innerHTML = html;
      document.body.appendChild(_menuEl);

      _menuEl.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-action]");
        if (!btn) return;
        var idx = parseInt(btn.dataset.annIdx, 10);
        var ann = anns[idx];
        if (!ann) return;
        if (btn.dataset.action === "edit") {
          _hideMenu();
          AnnotationPopupModule.open(ann);
        } else if (btn.dataset.action === "delete") {
          _hideMenu();
          _deleteAnnotation(ann);
        }
      });

      _menuEl.addEventListener("mouseleave", _hideMenu);
    }

    /** Annotation löschen: clientseitig + Server. Extrahiert aus _showMenu. */
    function _deleteAnnotation(ann) {
      _state.annotations.delete(ann.localId || String(ann.id));
      HighlightModule.clearAll();
      HighlightModule.restoreAll();
      PostMarkerModule.clearAll();
      PostMarkerModule.restoreAll();
      MinimapModule.refresh();
      ForensicToolbar.events.emit("annotation:deleted", ann);
      ToolbarUIModule.updateSessionInfo();
      if (ann.id) {
        ajaxDelete(ForensicToolbar.config.API_ANNOTATE, { id: ann.id })
          .then(function (r) {
            if (r.status !== "ok") {
              console.warn("[Forensic] Server konnte Annotation nicht löschen:", r.status, ann.id);
            }
          })
          .catch(function (e) {
            console.error("[Forensic] Netzwerkfehler beim Löschen:", e);
          });
      }
    }

    function _hideMenu() {
      if (_menuEl) { _menuEl.remove(); _menuEl = null; }
    }

    // Viewport-Event-Listener
    //
    // Beleg: Fehler "HoverMenu unerreichbar" — Build 059 delegierte mouseover/
    // mouseout auf beliebige Kind-Elemente. Beim Verlassen eines Kind-Elements
    // in Richtung Menü feuerte mouseout → Menü verschwand.
    //
    // Fix Build 060: Event-Delegation auf Post-Ebene ([data-forensic-cat] oder
    // Post-ID-Anker [id^="p"]). Das Menü öffnet erst, wenn die Maus mindestens
    // HOVER_DELAY_MS auf dem Post-Container verbleibt. mouseout prüft ob das
    // relatedTarget noch im selben Post-Container liegt — wenn ja, kein Schließen.
    // Zusätzlich: _showMenu() positioniert das Menü relativ zum Post-Container
    // (getBoundingClientRect), nicht zur aktuellen Mausposition, damit die
    // Position stabil und vorhersehbar ist.
    ForensicToolbar.events.on("page:loaded", function () {
      var vp = document.getElementById("forensic-viewport");
      if (!vp) return;

      // Mausposition kontinuierlich aktualisieren, damit der setTimeout-Callback
      // die aktuelle (nicht die veraltete mouseover-Event) Position nutzen kann.
      // Beleg: Build 061 — getBoundingClientRect-Position war "rechts oben" und
      // entsprach nicht der Erwartung des Ermittlers (nahe Mauszeiger).
      //
      // Build 063: mousemove löst zusätzlich einen Dwell-Timer aus (Verweilzeit).
      // Problem: Nach Schließen des Menüs verbleibt die Maus im Post-Container —
      // kein mouseover feuert mehr, also kein Retrigger. Lösung: mousemove prüft
      // ob die Maus über einem annotierten Post verweilt und kein Menü aktiv ist.
      // Der Dwell-Timer wird bei jeder Mausbewegung zurückgesetzt (Debounce),
      // öffnet das Menü nach HOVER_DELAY_MS Stillstand.
      // Build 064: Dwell-Timer nutzt _findAnnotationsAtPoint() statt nur Post-Container —
      // damit werden auch Textmarkierungen (CSS Custom Highlights, kein DOM-Element)
      // im Dwell-Pfad erkannt.
      var _dwellTimer = null;
      vp.addEventListener("mousemove", function (e) {
        _lastMouseX = e.pageX;
        _lastMouseY = e.pageY;

        // Dwell-Logik: Nur wenn kein Menü aktiv
        if (_menuEl) return;

        var anns = _findAnnotationsAtPoint(e.clientX, e.clientY);
        if (anns.length === 0) {
          clearTimeout(_dwellTimer);
          _dwellTimer = null;
          return;
        }

        // Debounce: Bei jeder Bewegung neuen Timer setzen
        clearTimeout(_dwellTimer);
        var capturedAnns = anns.slice();
        _dwellTimer = setTimeout(function () {
          if (!_menuEl) {
            _showMenuForList(capturedAnns, _lastMouseX + 12, _lastMouseY - 36);
          }
          _dwellTimer = null;
        }, ForensicToolbar.config.HOVER_DELAY_MS);
      });

      vp.addEventListener("mouseover", function (e) {
        // Delegation: Post-Container finden (Post-Markierungen)
        var postEl = e.target.closest
          ? e.target.closest("[data-forensic-cat]")
          : null;
        if (!postEl) return;

        var ann = _findAnnotationAtElement(postEl);
        if (!ann) return;

        // Bereits im gleichen Post → Timer nicht neu starten
        if (_timer && _targetAnn && _targetAnn === ann) return;

        clearTimeout(_timer);
        _timer = setTimeout(function () {
          _showMenuForList([ann], _lastMouseX + 12, _lastMouseY - 36);
        }, ForensicToolbar.config.HOVER_DELAY_MS);
      });

      vp.addEventListener("mouseout", function (e) {
        var related = e.relatedTarget;
        // Wenn Maus zu Menü-Element wechselt → nicht schließen
        if (related && related.closest && related.closest(".forensic-hover-menu")) return;
        // Wenn Maus noch im selben Post-Container bleibt → nicht schließen
        var fromPost = e.target.closest ? e.target.closest("[data-forensic-cat]") : null;
        if (fromPost && related && fromPost.contains(related)) return;
        // Andernfalls: Timer abbrechen und Menü schließen
        clearTimeout(_timer);
        clearTimeout(_dwellTimer);
        _timer = null;
        _dwellTimer = null;
        if (!(_menuEl && _menuEl.matches(":hover"))) _hideMenu();
      });
    });

    return {};
  })();

  // ===========================================================================
  // PHASE 7: MinimapModule — Seitenleiste mit Positions-Markern
  //
  // Build 030-C: Zwei Marker-Typen:
  //   1. Spur-Marker (forensic-minimap-trace): Positionen aus traceElements.
  //      Werden beim Laden der Seite sofort gerendert — unabhängig davon ob
  //      der Ermittler bereits annotiert hat. Farbe: gedämpftes Grau-Blau.
  //      Zeigen dem Ermittler auf einen Blick wo der Beschuldigte aktiv war.
  //   2. Annotations-Marker (forensic-minimap-bar): Positionen von Annotationen.
  //      Farbe: Kategoriefarbe. Werden nach jeder Annotationsaktion aktualisiert.
  //
  // Beide Typen können gleichzeitig an derselben Position liegen (Post
  // annotiert UND Spur vorhanden) — Annotations-Marker liegt dann obendrauf.
  //
  // Position: Y-Prozent = (Element.top + scrollY) / body.scrollHeight.
  // Beleg: §9 Bauplan — Minimap zeigt Benutzer-Spuren und Annotationen.
  // ===========================================================================
  var MinimapModule = (function () {
    var _minimapEl = null;

    function init() {
      _minimapEl = document.createElement("div");
      _minimapEl.id = "forensic-minimap";
      _minimapEl.setAttribute("aria-label", "Spurenkarte");
      _minimapEl.setAttribute("role", "navigation");
      document.body.appendChild(_minimapEl);
    }

    // -------------------------------------------------------------------------
    // _pctOf — Y-Position eines Elements als Prozentwert der Seitenhöhe
    // -------------------------------------------------------------------------
    function _pctOf(el) {
      var totalH = Math.max(document.body.scrollHeight, 1);
      var pct = ((el.getBoundingClientRect().top + window.scrollY) / totalH) * 100;
      return Math.max(0, Math.min(99, pct));
    }

    // -------------------------------------------------------------------------
    // _buildTraceTooltip — Aussagekräftigen Tooltip-Text aus DOM ableiten
    // (Bug 2.80, Build 175)
    // -------------------------------------------------------------------------
    // Strategie:
    //   topic:<id>  → Linktext des Topic-Links (Titel des Themas)
    //   p<id>       → erster Textinhalt von .post-entry / .post-content / .post
    //                  (erste 80 Zeichen), Fallback: "Post #<id>"
    // Beleg: HTML-Analyse viewtopic.php + viewforum.php — DOM-Selektoren
    //        für FluxBB/PunBB-Markup. Projektgespräch 2026-05-11.
    // -------------------------------------------------------------------------
    function _buildTraceTooltip(elemId, el, isTopic) {
      _dbg("[Minimap] _buildTraceTooltip:", elemId, "isTopic:", isTopic);

      if (isTopic) {
        // Topic-Zeile: Linktext des viewtopic.php-Links extrahieren
        var topicId = elemId.slice(6);
        var link = el.querySelector('a[href*="viewtopic.php?id=' + topicId + '"]');
        if (link && link.textContent.trim()) {
          return "📌 Thema: " + link.textContent.trim().substring(0, 80);
        }
        // Fallback: erster Link-Text in der Zeile
        var anyLink = el.querySelector("a");
        if (anyLink && anyLink.textContent.trim()) {
          return "📌 Thema: " + anyLink.textContent.trim().substring(0, 80);
        }
        return "📌 Topic-Spur: " + topicId;
      }

      // Post-Eintrag: Inhalt aus bekannten FluxBB/PunBB-Selektoren
      // Reihenfolge: spezifischster Selektor zuerst
      var contentSelectors = [
        ".post-entry",
        ".post-body",
        ".entry",
        ".postmsg",
        ".post-content",
        ".post_body",
        ".message",
      ];
      for (var i = 0; i < contentSelectors.length; i++) {
        var contentEl = el.querySelector(contentSelectors[i]);
        if (contentEl) {
          var txt = (contentEl.textContent || "").replace(/\s+/g, " ").trim();
          if (txt.length > 0) {
            return "💬 Post: " + txt.substring(0, 80) + (txt.length > 80 ? "…" : "");
          }
        }
      }
      // Fallback: Autoren aus .username oder .post-author
      var authorEl = el.querySelector(".username, .post-author, .author");
      if (authorEl && authorEl.textContent.trim()) {
        return "💬 Post von " + authorEl.textContent.trim().substring(0, 40);
      }
      // Letzter Fallback
      return "💬 Post #" + elemId.slice(1);
    }

    // -------------------------------------------------------------------------
    // _makeBar — Minimap-Balken erstellen und einfügen
    // -------------------------------------------------------------------------
    function _makeBar(pct, color, label, onClick) {
      var bar = document.createElement("div");
      bar.style.top        = pct + "%";
      bar.style.background = color;
      bar.title            = label;
      bar.setAttribute("aria-label", label);
      bar.setAttribute("tabindex", "0");
      bar.addEventListener("click", onClick);
      bar.addEventListener("keypress", function (e) {
        if (e.key === "Enter") onClick();
      });
      return bar;
    }

    // -------------------------------------------------------------------------
    // refresh — Minimap neu aufbauen
    // Wird nach Seitenload, nach jeder Annotationsaktion und nach
    // viewmode-Wechsel aufgerufen.
    // -------------------------------------------------------------------------
    function refresh() {
      if (!_minimapEl) return;
      _minimapEl.innerHTML = "";

      // --- Typ 1: Spur-Marker (traceElements aus Envelope) ---
      // Sofort beim Laden sichtbar; zeigen Aktivität des Beschuldigten.
      // "p<id>"      → Post-Container auf viewtopic.php (Farbe: Grau-Blau)
      // "topic:<id>" → Topic-Zeile auf viewforum.php   (Farbe: Grün, Build 082)
      // Bug 2.80 (Build 175): contains_traces-Klasse an Spur-Elemente vergeben
      // + DOM-basierter Tooltip statt generischer "Spur: p<id>"-Text.
      // Beleg: Projektgespräch 2026-05-11
      //
      // Tooltip-Strategie (clientseitig, kein Server-Roundtrip):
      //   topic:<id>  → Titel aus <a href*="viewtopic.php?id=<id>">-Linktext
      //   p<id>       → Textvorschau aus .post-content (erste 80 Zeichen)
      //
      // contains_traces-Klasse: initial pulsierende Umrandung via CSS-Animation.
      _state.traceElements.forEach(function (elemId) {
        var el = _resolveTraceElement(elemId);
        if (!el) return;

        // contains_traces-Klasse für CSS-Highlighting setzen
        if (!el.classList.contains("contains_traces")) {
          el.classList.add("contains_traces");
        }

        var isTopic = elemId.startsWith("topic:");
        var color   = isTopic ? "#3a7a4a" : "#3a5a8a";

        // DOM-basierter Tooltip (Bug 2.80)
        var label = _buildTraceTooltip(elemId, el, isTopic);

        var pct = _pctOf(el);
        var bar = _makeBar(
          pct,
          color,
          label,
          function () { el.scrollIntoView({ behavior: "smooth", block: "center" }); }
        );
        bar.className = isTopic ? "forensic-minimap-topic" : "forensic-minimap-trace";
        _minimapEl.appendChild(bar);
      });

      // --- Typ 2: Annotations-Marker ---
      // Überlagern ggf. vorhandene Spur-Marker an derselben Position.
      _state.annotations.forEach(function (ann) {
        // Position: bevorzugt elementId (Post-Markierung), sonst XPath-Range
        var el = ann.elementId ? document.getElementById(ann.elementId) : null;

        // Für Textmarkierungen: Element über XPath-Range ermitteln
        if (!el && ann.selection) {
          var restored = AnnotationStoreModule.rangeFromSelection(ann.selection);
          if (restored && restored.range) {
            var container = restored.range.startContainer;
            el = (container.nodeType === 3)
              ? container.parentElement
              : container;
          }
        }
        if (!el) return;

        var pct = _pctOf(el);
        var cat = _getCat(ann.category);
        var preview = (ann.text || (ann.selection && ann.selection.textContent) || "—")
          .substring(0, 60);

        var bar = _makeBar(
          pct,
          cat ? cat.color : "#aaa",
          (cat ? cat.label : "?") + ": " + preview,
          function () { el.scrollIntoView({ behavior: "smooth", block: "center" }); }
        );
        bar.className = "forensic-minimap-bar";
        if (ann.stale) bar.style.outline = "1px dashed #aaa";
        _minimapEl.appendChild(bar);
      });
    }

    // Ereignisse die eine Minimap-Aktualisierung auslösen
    ForensicToolbar.events.on("annotation:created", refresh);
    ForensicToolbar.events.on("annotation:deleted", refresh);
    ForensicToolbar.events.on("annotation:synced",  refresh);
    ForensicToolbar.events.on("annotations:loaded", refresh);
    // Spur-Marker nach viewmode-Wechsel wiederherstellen
    ForensicToolbar.events.on("viewmode:enhanced",  refresh);
    ForensicToolbar.events.on("viewmode:original",  function () {
      if (!_minimapEl) return;
      _minimapEl.innerHTML = "";
    });

    return { init: init, refresh: refresh };
  })();

  // ===========================================================================
  // PHASE 7b: TraceNavigationModule — Navigation zwischen Benutzer-Spuren
  //
  // Build 030-C: Aktiviert die in Build 030-B als Dummy eingebauten Elemente:
  //   - #forensic-trace-input   (Direkteingabe Spurennummer)
  //   - #forensic-btn-trace-prev / -next  (◀/▶-Buttons)
  //   - #forensic-trace-total   (Gesamtanzahl "/ N")
  //
  // Navigation erfolgt über _state.traceElements (DOM-Element-IDs)
  // für Spuren auf der AKTUELLEN Seite.
  //
  // Build 072 (OP-KN-7): Seitenübergreifende Navigation ergänzt.
  //   - Beim Start: Sequenz via /_forensic/trace_sequence laden.
  //   - Buttons zeigen ◄/► wenn Ziel auf gleicher Seite (Scroll),
  //     ◄◄/▶▶ wenn Ziel auf anderer Seite (Seitenwechsel).
  //   - Reihenfolge: Profil → PM → Posts → Sonstiges, innerhalb
  //     Gruppe: scrape_targets.id ASC (chronologisch).
  //   - Einstiegspunkt: aktuell geladene Seite. Nach Seitenload wird
  //     traceSeqIndex auf die aktuelle Seite gesetzt.
  //   - Gruppenwechsel: Toast-Benachrichtigung.
  //
  // Beleg: §OP-4 (intra-page), OP-KN-7 (inter-page), Build 072.
  // ===========================================================================
  var TraceNavigationModule = (function () {
    var _currentIdx = -1; // 0-basiert; -1 = keine Spur angesprungen (intra-page)

    // Listener-Referenzen für sauberes Entfernen ohne cloneNode
    var _prevListener = null;
    var _nextListener = null;
    var _inputKeyListener = null;
    var _inputBlurListener = null;

    // -------------------------------------------------------------------------
    // _getSeq — Sequenz aus State holen
    // -------------------------------------------------------------------------
    function _getSeq() {
      return _state.traceSequence || [];
    }

    // -------------------------------------------------------------------------
    // _currentUrl — normalisierte URL der aktuellen Seite
    // -------------------------------------------------------------------------
    function _currentUrl() {
      return _state.currentUrl || "";
    }

    // -------------------------------------------------------------------------
    // _seqIndexForUrl — Index in traceSequence für eine URL (-1 wenn nicht gefunden)
    // -------------------------------------------------------------------------
    function _seqIndexForUrl(url) {
      var seq = _getSeq();
      for (var i = 0; i < seq.length; i++) {
        if (seq[i].url === url) return i;
      }
      return -1;
    }

    // -------------------------------------------------------------------------
    // _nextTargetForDirection — liefert {seqIdx, intraIdx} oder null
    //
    // Logik:
    //   1. Gibt es noch unbesuchte Spuren auf der aktuellen Seite (intra)?
    //      → intra-page Sprung
    //   2. Sonst: nächste Seite in traceSequence
    // -------------------------------------------------------------------------
    function _nextTargetForDirection(dir) {
      var traces  = _state.traceElements || [];
      var seq     = _getSeq();
      var seqIdx  = _state.traceSeqIndex;
      if (seqIdx < 0) seqIdx = _seqIndexForUrl(_currentUrl());

      // Intra-page Sprung?
      if (dir === "next") {
        var nextIntra = _currentIdx + 1;
        if (nextIntra < traces.length) {
          return { seqIdx: seqIdx, intraIdx: nextIntra, crossPage: false };
        }
        // Nächste Seite in Sequenz
        var nextSeq = seqIdx + 1;
        if (nextSeq < seq.length) {
          return { seqIdx: nextSeq, intraIdx: 0, crossPage: true };
        }
        return null; // Ende der Sequenz
      } else {
        var prevIntra = _currentIdx - 1;
        if (prevIntra >= 0) {
          return { seqIdx: seqIdx, intraIdx: prevIntra, crossPage: false };
        }
        // Vorherige Seite in Sequenz
        var prevSeq = seqIdx - 1;
        if (prevSeq >= 0) {
          return { seqIdx: prevSeq, intraIdx: -1, crossPage: true }; // -1 = letzte Spur der Seite
        }
        return null; // Anfang der Sequenz
      }
    }

    // -------------------------------------------------------------------------
    // _updateButtonLabels — ◄/► oder ◄◄/▶▶ je nach nächstem Ziel
    // -------------------------------------------------------------------------
    function _updateButtonLabels() {
      var prevBtn = document.getElementById("forensic-btn-trace-prev");
      var nextBtn = document.getElementById("forensic-btn-trace-next");
      if (!prevBtn || !nextBtn) return;

      var prevTarget = _nextTargetForDirection("prev");
      var nextTarget = _nextTargetForDirection("next");

      // Beschriftung: ◄◄/▶▶ signalisiert Seitenwechsel
      prevBtn.textContent = (prevTarget && prevTarget.crossPage) ? "◄◄" : "◄";
      nextBtn.textContent = (nextTarget && nextTarget.crossPage) ? "▶▶" : "▶";

      // ARIA-Labels mitpflegen
      if (prevTarget && prevTarget.crossPage) {
        var seq = _getSeq();
        var prevTitle = seq[prevTarget.seqIdx] ? (seq[prevTarget.seqIdx].title || seq[prevTarget.seqIdx].url) : "";
        prevBtn.setAttribute("title", "Vorherige Spur — Seitenwechsel zu: " + prevTitle);
        prevBtn.setAttribute("aria-label", "Vorherige Spur (andere Seite): " + prevTitle);
      } else {
        prevBtn.setAttribute("title", "Vorherige Spur");
        prevBtn.setAttribute("aria-label", "Vorherige Spur");
      }
      if (nextTarget && nextTarget.crossPage) {
        var seq = _getSeq();
        var nextTitle = seq[nextTarget.seqIdx] ? (seq[nextTarget.seqIdx].title || seq[nextTarget.seqIdx].url) : "";
        nextBtn.setAttribute("title", "Nächste Spur — Seitenwechsel zu: " + nextTitle);
        nextBtn.setAttribute("aria-label", "Nächste Spur (andere Seite): " + nextTitle);
      } else {
        nextBtn.setAttribute("title", "Nächste Spur");
        nextBtn.setAttribute("aria-label", "Nächste Spur");
      }
    }

    // -------------------------------------------------------------------------
    // _update — UI-Elemente auf aktuellen Index synchronisieren
    // -------------------------------------------------------------------------
    function _update() {
      var traces  = _state.traceElements;
      var total   = traces.length;
      var seq     = _getSeq();
      var seqIdx  = _state.traceSeqIndex;
      if (seqIdx < 0) seqIdx = _seqIndexForUrl(_currentUrl());

      var inputEl = document.getElementById("forensic-trace-input");
      var totalEl = document.getElementById("forensic-trace-total");
      var prevBtn = document.getElementById("forensic-btn-trace-prev");
      var nextBtn = document.getElementById("forensic-btn-trace-next");

      if (!inputEl || !totalEl || !prevBtn || !nextBtn) {
        console.warn("[Forensic] TraceNavigation: UI-Elemente nicht gefunden.");
        return;
      }

      var hasTraces    = total > 0;
      var hasSeqPrev   = seqIdx > 0;
      var hasSeqNext   = seqIdx >= 0 && seqIdx < seq.length - 1;
      var canGoPrev    = hasTraces ? (_currentIdx > 0 || hasSeqPrev) : hasSeqPrev;
      var canGoNext    = hasTraces ? (_currentIdx < total - 1 || hasSeqNext) : hasSeqNext;

      totalEl.textContent = "/ " + (hasTraces ? total : (seq.length > 0 ? "?" : "0"));
      inputEl.disabled    = !hasTraces;
      prevBtn.disabled    = !canGoPrev;
      nextBtn.disabled    = !canGoNext;
      inputEl.max         = String(total);
      inputEl.value       = (hasTraces && _currentIdx >= 0) ? String(_currentIdx + 1) : "";
      inputEl.placeholder = hasTraces ? "1" : "—";

      _updateButtonLabels();
    }

    // -------------------------------------------------------------------------
    // jumpTo — Zu einer Spur springen (0-basierter Index, intra-page)
    // -------------------------------------------------------------------------
    function jumpTo(idx) {
      var traces = _state.traceElements;
      if (!traces.length) return;
      idx = Math.max(0, Math.min(traces.length - 1, idx));
      _currentIdx = idx;

      var elemId = traces[idx];
      var el = _resolveTraceElement(elemId);

      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.style.transition = "outline 0.1s";
        el.style.outline    = "3px solid #4f8ef7";
        setTimeout(function () { el.style.outline = ""; }, 1200);
        var label = elemId.startsWith("topic:")
          ? "Topic-Spur " + (idx + 1) + " von " + traces.length + ": Topic " + elemId.slice(6)
          : "Spur " + (idx + 1) + " von " + traces.length + ": " + elemId;
        AccessibilityModule.announce(label);
      }
      _update();
    }

    // -------------------------------------------------------------------------
    // _navigate — Hauptnavigationslogik (intra + inter-page)
    // -------------------------------------------------------------------------
    function _navigate(dir) {
      var target = _nextTargetForDirection(dir);
      if (!target) return;

      if (!target.crossPage) {
        // Intra-page Sprung
        jumpTo(target.intraIdx);
        return;
      }

      // Seitenübergreifend: sofort laden (OP-KN-7 — kein Bestätigungs-Toast)
      var seq  = _getSeq();
      var dest = seq[target.seqIdx];
      if (!dest) return;

      // Gruppe ankündigen wenn Gruppenwechsel
      var curSeqIdx = _state.traceSeqIndex >= 0
        ? _state.traceSeqIndex : _seqIndexForUrl(_currentUrl());
      var curGroup  = curSeqIdx >= 0 ? seq[curSeqIdx].group : null;
      if (curGroup && dest.group !== curGroup) {
        var groupLabels = {
          "profile": "Profilseiten",
          "pm":      "Private Nachrichten",
          "topic":   "Beiträge",
          "other":   "Sonstige Seiten",
        };
        ToastModule.show(
          "Gruppe: " + (groupLabels[dest.group] || dest.group),
          ToastModule.TYPES[0]
        );
      }

      // traceSeqIndex vorab setzen — wird nach page:loaded von _update() genutzt
      ForensicToolbar._setState({ traceSeqIndex: target.seqIdx });

      // Seitenload anstoßen
      ForensicToolbar.navigation.loadPage(dest.url, true);
    }

    // -------------------------------------------------------------------------
    // _loadSequence — Sequenz vom Server laden und in State schreiben
    // -------------------------------------------------------------------------
    function _loadSequence() {
      ajaxGet(ForensicToolbar.config.API_TRACE_SEQUENCE)
        .then(function (data) {
          var seq = (data && Array.isArray(data.sequence)) ? data.sequence : [];
          ForensicToolbar._setState({ traceSequence: seq });
          // Initialen seqIndex anhand der aktuellen Seite setzen
          var idx = _seqIndexForUrl(_currentUrl());
          ForensicToolbar._setState({ traceSeqIndex: idx });
          _update();
          _dbg("TraceSequence geladen: " + seq.length + " Einträge, seqIdx=" + idx);
        })
        .catch(function (err) {
          _dbg("TraceSequence Ladefehler", err);
        });
    }

    // Hilfsfunktion entfernt — ForensicToolbar._setState direkt verwenden.
    // Build 072-Fix: _ForensicToolbar_setState war undefinierter Alias.

    // -------------------------------------------------------------------------
    // init — Wird nach jedem Seitenload aufgerufen.
    // -------------------------------------------------------------------------
    function init() {
      _currentIdx = -1;

      var prevBtn = document.getElementById("forensic-btn-trace-prev");
      var nextBtn = document.getElementById("forensic-btn-trace-next");
      var input   = document.getElementById("forensic-trace-input");

      // Alte Listener sauber entfernen
      if (prevBtn && _prevListener) prevBtn.removeEventListener("click", _prevListener);
      if (nextBtn && _nextListener) nextBtn.removeEventListener("click", _nextListener);
      if (input && _inputKeyListener) {
        input.removeEventListener("keydown", _inputKeyListener);
        input.removeEventListener("blur",    _inputBlurListener);
      }

      _prevListener = function () { _navigate("prev"); };
      _nextListener = function () { _navigate("next"); };
      _inputKeyListener = function (e) {
        if (e.key !== "Enter") return;
        var val = parseInt(input.value, 10);
        if (!isNaN(val)) jumpTo(val - 1);
      };
      _inputBlurListener = function () {
        var val = parseInt(input.value, 10);
        var max = _state.traceElements.length;
        if (!isNaN(val) && val >= 1 && val <= max) {
          jumpTo(val - 1);
        } else {
          _update();
        }
      };

      if (prevBtn) prevBtn.addEventListener("click", _prevListener);
      if (nextBtn) nextBtn.addEventListener("click", _nextListener);
      if (input) {
        input.addEventListener("keydown", _inputKeyListener);
        input.addEventListener("blur",    _inputBlurListener);
      }

      // seqIndex auf aktuelle Seite setzen (Sequenz bereits geladen)
      var idx = _seqIndexForUrl(_currentUrl());
      if (idx >= 0) {
        ForensicToolbar._setState({ traceSeqIndex: idx });
      }

      _update();
    }

    // Nach erstem Seitenload Sequenz laden
    var _seqLoaded = false;
    ForensicToolbar.events.on("page:loaded", function () {
      if (!_seqLoaded) {
        _seqLoaded = true;
        _loadSequence();
      } else {
        // Sequenz-Cache ist stabil (Server-Daten ändern sich nicht während Session)
        // Nur seqIndex neu bestimmen
        var idx = _seqIndexForUrl(_currentUrl());
        ForensicToolbar._setState({ traceSeqIndex: idx });
      }
      setTimeout(init, 0);
    });

    // State-Änderung an traceElements → Anzeige aktualisieren
    ForensicToolbar.events.on("state:changed", function (updates) {
      if ("traceElements" in updates) {
        _currentIdx = -1;
        _update();
      }
      if ("traceSequence" in updates || "traceSeqIndex" in updates) {
        _update();
      }
    });

    return { jumpTo: jumpTo, init: init };
  })();

  // ===========================================================================
  // PHASE 7: ViewportTrackerModule — IntersectionObserver → /_forensic/viewport
  // ===========================================================================
  var ViewportTrackerModule = (function () {
    var _buffer    = [];
    var _pageUrl   = "";
    var _observer  = null;
    var _enterTs   = {};
    var _flushTimer = null;

    function start(container, pageUrl) {
      _pageUrl = pageUrl;
      _buffer  = [];
      _enterTs = {};
      if (_observer) _observer.disconnect();
      if (!window.IntersectionObserver) return;

      _observer = new IntersectionObserver(function (entries) {
        var now = Date.now();
        entries.forEach(function (entry) {
          var id = entry.target.id || null;
          if (!id) return;
          if (entry.isIntersecting) {
            _enterTs[id] = now;
          } else {
            var enter = _enterTs[id];
            if (enter) {
              _buffer.push({
                element_id: id,
                visible_ms: now - enter,
                ts_enter:   enter,
                ts_leave:   now,
              });
              delete _enterTs[id];
            }
          }
        });
        _scheduleFlush();
      }, { threshold: 0.5 });

      // Post-Elemente beobachten (Beleg: §18.1 Bauplan — id="p12345")
      container.querySelectorAll("[id^='p']").forEach(function (el) {
        if (/^p\d+$/.test(el.id)) _observer.observe(el);
      });
    }

    function _scheduleFlush() {
      if (_flushTimer) return;
      _flushTimer = setTimeout(_flush, ForensicToolbar.config.VIEWPORT_FLUSH_MS);
    }

    function _flush() {
      _flushTimer = null;
      if (!_buffer.length || !_pageUrl) return;
      var toSend = _buffer.splice(0);
      ajaxPost(ForensicToolbar.config.API_VIEWPORT, {
        page_url: _pageUrl,
        events:   toSend,
      }).catch(function (e) {
        console.warn("[Forensic] Viewport-Flush Fehler:", e);
      });
    }

    return { start: start };
  })();

  // ===========================================================================
  // PHASE 10: ContextBadgeModule — scrape_context-Anzeige
  // ===========================================================================
  // Build 066: Das Modul delegiert an ContextDropdownModule.updateBadge().
  // Der eigene DOM-Knoten (forensic-context-badge) existiert nicht mehr —
  // das Badge ist jetzt Teil des Dropdown-Buttons in Sektion 1.
  // ContextBadgeModule bleibt als öffentliche Schnittstelle erhalten, damit
  // NavigationModule (_handleEnvelope) ohne Änderung weiterarbeitet.
  // Beleg: Bauplan KN §5.1 — «ContextBadgeModule selbst bleibt unverändert —
  // ContextDropdownModule rendert seinen eigenen Button».
  // Anpassung Build 066: Da wir den DOM-Knoten übernehmen, delegieren wir.
  var ContextBadgeModule = (function () {

    function update(scrapeContext) {
      // Delegation an ContextDropdownModule (Build 066).
      // ContextDropdownModule ist nach ContextBadgeModule initialisiert —
      // beim ersten Aufruf aus _handleEnvelope ist es bereits verfügbar.
      if (typeof ContextDropdownModule !== "undefined") {
        ContextDropdownModule.updateBadge(scrapeContext);
      }
      // Investigator-Banner weiterhin direkt verwalten (kein Dropdown-Bezug).
      if (scrapeContext === "investigator") {
        _showInvestigatorBanner();
      } else {
        _hideInvestigatorBanner();
      }
    }

    function _showInvestigatorBanner() {
      var existing = document.getElementById("forensic-investigator-banner");
      if (existing) return;
      var banner = document.createElement("div");
      banner.id        = "forensic-investigator-banner";
      banner.className = "forensic-investigator-banner";
      banner.setAttribute("role", "alert");
      banner.innerHTML =
        "🔴 ERMITTLER-SESSION — Diese Seite wurde mit dem Ermittler-Account abgerufen. " +
        "Der Beschuldigte hatte möglicherweise keinen Zugriff.";
      var vp = document.getElementById("forensic-viewport");
      if (vp) vp.parentNode.insertBefore(banner, vp);
    }

    function _hideInvestigatorBanner() {
      var existing = document.getElementById("forensic-investigator-banner");
      if (existing) existing.remove();
    }

    ForensicToolbar.events.on("viewmode:original", function () {
      var banner = document.getElementById("forensic-investigator-banner");
      if (banner) banner.style.visibility = "hidden";
    });
    ForensicToolbar.events.on("viewmode:enhanced", function () {
      var banner = document.getElementById("forensic-investigator-banner");
      if (banner) banner.style.visibility = "";
    });

    return { update: update };
  })();

  // ===========================================================================
  // PHASE 10: FetchFailedModule — Anzeige bei fetch_failed=true
  // ===========================================================================
  var FetchFailedModule = (function () {

    function show(viewport, url, httpStatus) {
      viewport.innerHTML =
        '<div class="forensic-fetch-failed" role="alert">' +
        '<h2>⚠ Abruf fehlgeschlagen</h2>' +
        '<p>Diese Seite konnte zum Zeitpunkt der Sicherung nicht abgerufen werden.</p>' +
        '<p>HTTP-Status: <strong>' + _esc(String(httpStatus || "—")) + '</strong></p>' +
        '<p>Der Eintrag ist in der forensischen Datenbank vorhanden — der Abruf ist belegt.</p>' +
        '<small>URL: ' + _esc(url) + '</small>' +
        '</div>';
      AccessibilityModule.announce("Achtung: Seitenabruf fehlgeschlagen. HTTP " + (httpStatus || "unbekannt"));
    }

    return { show: show };
  })();

  // ===========================================================================
  // PHASE 10: UserInfoTabModule — window.open() → /_forensic/userinfo
  // ===========================================================================
  var UserInfoTabModule = (function () {
    function open() {
      window.open(
        ForensicToolbar.config.API_USERINFO,
        "forensic_userinfo",
        "width=1100,height=800,menubar=no,toolbar=no,status=no,scrollbars=yes"
      );
    }
    return { open: open };
  })();

  // ===========================================================================
  // PHASE 9: AccessibilityModule — ARIA-Live-Region, Keyboard-Navigation
  // ===========================================================================
  var AccessibilityModule = (function () {
    var _liveEl = null;

    function init() {
      // ARIA-Live-Region (§10.1 Bauplan)
      _liveEl = document.createElement("div");
      _liveEl.id               = "forensic-a11y-live";
      _liveEl.setAttribute("role", "status");
      _liveEl.setAttribute("aria-live", "polite");
      _liveEl.setAttribute("aria-atomic", "true");
      _liveEl.className        = "forensic-visually-hidden";
      document.body.appendChild(_liveEl);

      // Keyboard-Navigation (§10.2 Bauplan)
      document.addEventListener("keydown", function (e) {
        // Kein Shortcut wenn Fokus in Eingabefeld
        if (e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) {
          return;
        }

        // 1-6: Kategorie wählen
        if (e.key >= "1" && e.key <= "6" && !e.ctrlKey && !e.altKey && !e.metaKey) {
          var idx = parseInt(e.key, 10) - 1;
          var cat = ForensicToolbar.config.CATEGORIES[idx];
          if (cat) MarkerToolModule.toggleCategory(cat.id);
          return;
        }

        // Esc: Aktiven Modus deaktivieren / Popup schließen
        if (e.key === "Escape") {
          if (_state.activeCategory) {
            ForensicToolbar._setState({ activeCategory: null });
          }
          return;
        }

        // Alt+U: Nutzerinfo öffnen
        if (e.key === "u" && e.altKey) {
          e.preventDefault();
          UserInfoTabModule.open();
          return;
        }

        // Alt+→: Nächste Seite
        if (e.key === "ArrowRight" && e.altKey) {
          e.preventDefault();
          NavigationModule.navigateNext();
          return;
        }

        // Alt+←: Vorherige Seite
        if (e.key === "ArrowLeft" && e.altKey) {
          e.preventDefault();
          NavigationModule.navigatePrev();
          return;
        }
      });
    }

    /** Meldung in ARIA-Live-Region schreiben */
    function announce(msg) {
      if (!_liveEl) return;
      // Kurz leeren damit dieselbe Meldung wiederholt vorgelesen wird
      _liveEl.textContent = "";
      setTimeout(function () { _liveEl.textContent = msg; }, 50);
    }

    return { init: init, announce: announce };
  })();

  // ===========================================================================
  // PHASE 11: ViewModeModule — Ansichtswechsel Original ↔ Angepasst
  // ===========================================================================
  var ViewModeModule = (function () {

    function toggle() {
      if (_state.viewMode === "enhanced") {
        _setOriginal();
      } else {
        _setEnhanced();
      }
    }

    function _setOriginal() {
      ForensicToolbar._setState({ viewMode: "original" });

      // Highlights entfernen (GR11a)
      HighlightModule.clearAll();

      // Post-Markierungen entfernen (GR11b)
      PostMarkerModule.clearAll();

      // Toolbar-Eingriffe unsichtbar (visibility:hidden — Layout bleibt, §21.1 Bauplan)
      var banner = document.getElementById("forensic-investigator-banner");
      if (banner) banner.style.visibility = "hidden";
      var minimap = document.getElementById("forensic-minimap");
      if (minimap) minimap.style.visibility = "hidden";

      // Button-Kennzeichnung
      var btn = document.getElementById("forensic-btn-viewmode");
      if (btn) {
        btn.textContent   = "⊟ Original";
        btn.dataset.viewmode = "original";
        btn.style.outline = "3px solid #e84040";
      }

      ForensicToolbar.events.emit("viewmode:original");
      AccessibilityModule.announce("Original-Ansicht aktiv — alle Anreicherungen deaktiviert.");
    }

    function _setEnhanced() {
      ForensicToolbar._setState({ viewMode: "enhanced" });

      // Highlights wiederherstellen
      HighlightModule.restoreAll();

      // Post-Markierungen wiederherstellen
      PostMarkerModule.restoreAll();

      // Toolbar-Eingriffe wieder sichtbar
      var banner = document.getElementById("forensic-investigator-banner");
      if (banner) banner.style.visibility = "";
      var minimap = document.getElementById("forensic-minimap");
      if (minimap) minimap.style.visibility = "";

      // Button-Kennzeichnung
      var btn = document.getElementById("forensic-btn-viewmode");
      if (btn) {
        btn.textContent      = "⊞ Angepasst";
        btn.dataset.viewmode = "enhanced";
        btn.style.outline    = "";
      }

      ForensicToolbar.events.emit("viewmode:enhanced");
      AccessibilityModule.announce("Angepasste Ansicht aktiv — Anreicherungen sichtbar.");
    }

    return { toggle: toggle };
  })();

  // ===========================================================================
  // PHASE 11: PMSTableOrganizerModule — PN-Übersichtstabelle (pmsnew.php)
  // ===========================================================================
  var PMSTableOrganizerModule = (function () {
    // Beleg: §21.2 Bauplan (Selektoren verifiziert gegen aiw_pmsnew_new.html)
    var TABLE_SEL   = "div#vf .inbox > table";
    var ROW_SEL     = "div#vf tbody > tr";
    var HEADER_SEL  = "div#vf thead > tr > th";

    var _tbody      = null;
    var _origOrder  = null; // Original-Reihenfolge gesichert beim Start
    var _currentSort = { col: -1, dir: "asc" };
    var _filterText  = "";
    var _filterMode  = "all"; // "all" | "unread" | "read" | "closed"
    var _container   = null;

    function init(viewport) {
      var table = viewport.querySelector(TABLE_SEL);
      if (!table) return;

      _tbody     = table.querySelector("tbody");
      if (!_tbody) return;

      // Original-Reihenfolge sichern (Invariante §21.2 Bauplan)
      _origOrder = Array.from(_tbody.rows);
      _currentSort = { col: -1, dir: "asc" };
      _filterText  = "";
      _filterMode  = "all";

      _injectControls(viewport, table);

      // viewmode:original → Original-Reihenfolge wiederherstellen
      ForensicToolbar.events.on("viewmode:original", _restoreOriginal);
      ForensicToolbar.events.on("viewmode:enhanced", function () {
        _applySort();
        _applyFilter();
      });
    }

    function _injectControls(viewport, table) {
      var existing = viewport.querySelector("#forensic-pms-controls");
      if (existing) existing.remove();

      var ctrl = document.createElement("div");
      ctrl.id = "forensic-pms-controls";
      ctrl.className = "forensic-table-controls";
      ctrl.setAttribute("role", "toolbar");
      ctrl.setAttribute("aria-label", "PN-Tabelle sortieren und filtern");
      ctrl.innerHTML =
        '<input type="text" id="forensic-pms-filter" placeholder="Betreff oder Absender filtern…" ' +
        'class="forensic-table-filter-input" aria-label="PN-Tabelle filtern">' +
        '<select id="forensic-pms-mode" class="forensic-table-select" aria-label="Anzeigefilter">' +
        '<option value="all">Alle</option>' +
        '<option value="unread">Nur ungelesen</option>' +
        '<option value="read">Nur gelesen</option>' +
        '<option value="closed">Nur geschlossen</option>' +
        '</select>' +
        '<button class="forensic-btn forensic-btn-sm" id="forensic-pms-reset" ' +
        'aria-label="Sortierung und Filter zurücksetzen">↺ Reset</button>';

      table.parentNode.insertBefore(ctrl, table);

      document.getElementById("forensic-pms-filter").addEventListener("input", function () {
        _filterText = this.value.toLowerCase();
        _applyFilter();
      });
      document.getElementById("forensic-pms-mode").addEventListener("change", function () {
        _filterMode = this.value;
        _applyFilter();
      });
      document.getElementById("forensic-pms-reset").addEventListener("click", function () {
        _restoreOriginal();
        _filterText = ""; _filterMode = "all";
        document.getElementById("forensic-pms-filter").value = "";
        document.getElementById("forensic-pms-mode").value   = "all";
      });

      // Sortier-Header
      var headers = table.querySelectorAll(HEADER_SEL);
      headers.forEach(function (th, idx) {
        // Checkbox- und Status-Spalten nicht sortierbar (§21.2 Bauplan)
        if (th.classList.contains("tce") || (idx >= 5)) return;
        th.style.cursor = "pointer";
        th.setAttribute("tabindex", "0");
        th.setAttribute("aria-sort", "none");
        th.title = "Klick zum Sortieren";
        th.addEventListener("click", function () { _sortByCol(idx, th); });
        th.addEventListener("keypress", function (e) {
          if (e.key === "Enter") _sortByCol(idx, th);
        });
      });
    }

    function _sortByCol(colIdx, thEl) {
      if (_state.viewMode === "original") return;
      var dir = (_currentSort.col === colIdx && _currentSort.dir === "asc") ? "desc" : "asc";
      _currentSort = { col: colIdx, dir: dir };

      var rows = Array.from(_tbody.rows);
      rows.sort(function (a, b) {
        var aVal = _cellValue(a, colIdx);
        var bVal = _cellValue(b, colIdx);
        if (colIdx === 3) { // Replies: numerisch
          return (dir === "asc") ? (parseInt(aVal) - parseInt(bVal)) : (parseInt(bVal) - parseInt(aVal));
        }
        if (colIdx === 4) { // Last: Datum
          return (dir === "asc")
            ? (_parseDate(aVal) - _parseDate(bVal))
            : (_parseDate(bVal) - _parseDate(aVal));
        }
        return (dir === "asc") ? aVal.localeCompare(bVal, "de") : bVal.localeCompare(aVal, "de");
      });

      rows.forEach(function (r) { _tbody.appendChild(r); });

      // ARIA-Sort-Attribute aktualisieren
      var headers = document.querySelectorAll(HEADER_SEL);
      headers.forEach(function (th, idx) {
        th.setAttribute("aria-sort", idx === colIdx ? (dir === "asc" ? "ascending" : "descending") : "none");
      });
    }

    function _cellValue(row, colIdx) {
      var cell = row.cells[colIdx];
      if (!cell) return "";
      var link = cell.querySelector("a");
      return (link ? link.textContent : cell.textContent).trim();
    }

    function _parseDate(str) {
      // Format: "Ddd., DD.MM.YYYY HH:MM:SS" (§21.2 Bauplan)
      var m = str.match(/(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})/);
      if (!m) return 0;
      return new Date(m[3], m[2] - 1, m[1], m[4], m[5], m[6]).getTime();
    }

    function _applySort() {
      if (_currentSort.col >= 0) {
        var headers = document.querySelectorAll(HEADER_SEL);
        var th = headers[_currentSort.col];
        if (th) _sortByCol(_currentSort.col, th);
      }
    }

    function _applyFilter() {
      if (!_tbody) return;
      Array.from(_tbody.rows).forEach(function (row) {
        var show = true;
        if (_filterText) {
          var subjCell = row.cells[0] ? row.cells[0].textContent.toLowerCase() : "";
          var fromCell = row.cells[1] ? row.cells[1].textContent.toLowerCase() : "";
          if (!subjCell.includes(_filterText) && !fromCell.includes(_filterText)) show = false;
        }
        if (_filterMode === "unread"  && !row.classList.contains("inew"))    show = false;
        if (_filterMode === "read"    && row.classList.contains("inew"))     show = false;
        if (_filterMode === "closed"  && !row.classList.contains("iclosed")) show = false;

        row.style.display = show ? "" : "none";
      });
    }

    function _restoreOriginal() {
      if (!_tbody || !_origOrder) return;
      _origOrder.forEach(function (row) { _tbody.appendChild(row); });
      Array.from(_tbody.rows).forEach(function (row) { row.style.display = ""; });
    }

    return { init: init };
  })();

  // ===========================================================================
  // PHASE 11: TopicsTableOrganizerModule — Topic-Tabellen in Forenübersichten
  // ===========================================================================
  var TopicsTableOrganizerModule = (function () {
    // Beleg: §21.3 Bauplan (Selektoren verifiziert gegen aiw-forum-index.html)
    var TABLE_SEL  = "div.category > fieldset > table";
    var ROW_SEL    = "tbody > tr";
    var HEAD_SEL   = "thead > tr > th";

    var _tables = []; // Array von {tbody, origOrder}

    function init(viewport) {
      _tables = [];
      viewport.querySelectorAll(TABLE_SEL).forEach(function (table, tableIdx) {
        var tbody = table.querySelector("tbody");
        if (!tbody) return;
        var origOrder = Array.from(tbody.rows);
        _tables.push({ table: table, tbody: tbody, origOrder: origOrder });

        _injectControls(viewport, table, tableIdx, tbody, origOrder);
      });

      ForensicToolbar.events.on("viewmode:original", function () {
        _tables.forEach(function (t) {
          t.origOrder.forEach(function (r) { t.tbody.appendChild(r); });
          Array.from(t.tbody.rows).forEach(function (r) { r.style.display = ""; });
        });
      });
    }

    function _injectControls(viewport, table, tableIdx, tbody, origOrder) {
      var ctrl = document.createElement("div");
      ctrl.className = "forensic-table-controls";
      ctrl.setAttribute("role", "toolbar");
      ctrl.setAttribute("aria-label", "Topic-Tabelle " + (tableIdx + 1) + " sortieren und filtern");

      var filterId = "forensic-topic-filter-" + tableIdx;
      var resetId  = "forensic-topic-reset-" + tableIdx;
      ctrl.innerHTML =
        '<input type="text" id="' + filterId + '" placeholder="Titel filtern…" ' +
        'class="forensic-table-filter-input" aria-label="Topic-Titel filtern">' +
        '<button class="forensic-btn forensic-btn-sm" id="' + resetId + '" ' +
        'aria-label="Filter zurücksetzen">↺</button>';

      table.parentNode.insertBefore(ctrl, table);

      document.getElementById(filterId).addEventListener("input", function () {
        var val = this.value.toLowerCase();
        Array.from(tbody.rows).forEach(function (row) {
          var titleCell = row.querySelector("td.tcl .tclcon a");
          var txt = titleCell ? titleCell.textContent.toLowerCase() : row.cells[0] ? row.cells[0].textContent.toLowerCase() : "";
          row.style.display = txt.includes(val) ? "" : "none";
        });
      });
      document.getElementById(resetId).addEventListener("click", function () {
        origOrder.forEach(function (r) { tbody.appendChild(r); });
        Array.from(tbody.rows).forEach(function (r) { r.style.display = ""; });
        document.getElementById(filterId).value = "";
      });

      // Sortier-Header
      table.querySelectorAll(HEAD_SEL).forEach(function (th, idx) {
        th.style.cursor = "pointer";
        th.setAttribute("tabindex", "0");
        th.setAttribute("aria-sort", "none");
        th.title = "Klick zum Sortieren";
        th.addEventListener("click", function () { _sortTable(tbody, idx, th, table); });
        th.addEventListener("keypress", function (e) {
          if (e.key === "Enter") _sortTable(tbody, idx, th, table);
        });
      });
    }

    function _sortTable(tbody, colIdx, thEl, table) {
      if (_state.viewMode === "original") return;
      var prev = thEl.getAttribute("aria-sort") || "none";
      var dir  = (prev === "ascending") ? "desc" : "asc";

      var rows = Array.from(tbody.rows);
      rows.sort(function (a, b) {
        var aVal = _cellText(a, colIdx);
        var bVal = _cellText(b, colIdx);
        // Spalten 1+2 (Themen/Beiträge): numerisch
        if (colIdx >= 1 && colIdx <= 2) {
          return (dir === "asc") ? (parseInt(aVal) - parseInt(bVal)) : (parseInt(bVal) - parseInt(aVal));
        }
        return (dir === "asc") ? aVal.localeCompare(bVal, "de") : bVal.localeCompare(aVal, "de");
      });
      rows.forEach(function (r) { tbody.appendChild(r); });

      table.querySelectorAll(HEAD_SEL).forEach(function (th, idx) {
        th.setAttribute("aria-sort", idx === colIdx ? (dir === "asc" ? "ascending" : "descending") : "none");
      });
    }

    function _cellText(row, idx) {
      var cell = row.cells[idx];
      if (!cell) return "";
      var a = cell.querySelector("a");
      return (a ? a.textContent : cell.textContent).trim();
    }

    return { init: init };
  })();

  // ===========================================================================
  // PHASE 12: SupportIndicatorModule — SSE-Empfang, Support-Indikator
  // ===========================================================================
  var SupportIndicatorModule = (function () {
    var _es = null;

    function init() {
      if (typeof EventSource === "undefined") {
        console.warn("[Forensic] EventSource nicht verfügbar — Support-Indikator deaktiviert.");
        return;
      }
      _es = new EventSource(ForensicToolbar.config.API_EVENTS);

      _es.addEventListener("support_status", function (e) {
        var data;
        try { data = JSON.parse(e.data); } catch (ex) { return; }
        ForensicToolbar.events.emit("support:status_changed", data);
      });

      _es.addEventListener("error", function () {
        console.warn("[Forensic] SSE-Verbindung unterbrochen — Browser versucht automatisch reconnect.");
      });
    }

    ForensicToolbar.events.on("support:status_changed", function (data) {
      var el = document.getElementById("forensic-support-indicator");
      if (!el) return;

      if (data.support_active) {
        ForensicToolbar._setState({
          supportStatus: {
            active:   true,
            username: data.support_user,
            since:    data.since,
          },
        });
        el.className   = "forensic-support-active";
        el.textContent = "⚠️ Support aktiv · " + _esc(data.support_user || "?");
        // ARIA-Ankündigung (§6 Bauplan)
        AccessibilityModule.announce("Support-Zugriff durch " + (data.support_user || "unbekannt") + " aktiv.");
      } else {
        ForensicToolbar._setState({
          supportStatus: { active: false, username: null, since: null },
        });
        el.className   = "forensic-support-hidden";
        el.textContent = "";
      }
    });

    return { init: init };
  })();

  // ===========================================================================
  // PHASE 13: ToastModule — nicht-invasive Hinweis-Meldungen
  // ===========================================================================
  // Zeigt selbst verschwindende Toast-Nachrichten rechts unten an.
  // Kein globales LOG-Objekt erforderlich — in sich geschlossen.
  // Wird für NOT_IN_SCOPE, fetch_failed und andere Systemhinweise verwendet.
  // ===========================================================================
  var ToastModule = (function () {

    var _container = null;
    var _active    = [];          // Liste aktiver Toast-Elemente
    var MAX_TOASTS = 4;

    var TYPES = {
      info:    "forensic-toast--info",
      warning: "forensic-toast--warning",
      error:   "forensic-toast--error",
      success: "forensic-toast--success",
    };

    function _ensureContainer() {
      if (_container) return;
      _container = document.createElement("div");
      _container.id = "forensic-toast-container";
      _container.setAttribute("aria-live", "polite");
      _container.setAttribute("aria-atomic", "false");
      document.body.appendChild(_container);
    }

    function _remove(el) {
      el.classList.remove("forensic-toast--visible");
      setTimeout(function () {
        if (el.parentNode) el.parentNode.removeChild(el);
        var idx = _active.indexOf(el);
        if (idx !== -1) _active.splice(idx, 1);
      }, 300);  // CSS-Transition-Dauer
    }

    /**
     * Zeigt eine Toast-Nachricht an.
     * @param {string} message  — Anzuzeigende Nachricht (wird escaped)
     * @param {string} type     — 'info' | 'warning' | 'error' | 'success'
     * @param {number} duration — Anzeigedauer ms (0 = bleibt bis Schließen)
     */
    function show(message, type, duration) {
      _ensureContainer();
      type     = TYPES[type] ? type : "info";
      duration = (duration === undefined) ? 6000 : duration;

      // Ältesten Toast entfernen wenn Maximum erreicht
      if (_active.length >= MAX_TOASTS) {
        _remove(_active[0]);
      }

      var toast = document.createElement("div");
      toast.className = "forensic-toast " + TYPES[type];
      toast.setAttribute("role", "alert");

      var msgEl = document.createElement("span");
      msgEl.className   = "forensic-toast__msg";
      msgEl.textContent = message;

      var closeBtn = document.createElement("button");
      closeBtn.className        = "forensic-toast__close";
      closeBtn.textContent      = "✕";
      closeBtn.setAttribute("aria-label", "Meldung schließen");
      closeBtn.addEventListener("click", function () { _remove(toast); });

      toast.appendChild(msgEl);
      toast.appendChild(closeBtn);
      _container.appendChild(toast);
      _active.push(toast);

      // Animation einschalten (nächster Frame damit Transition greift)
      requestAnimationFrame(function () {
        toast.classList.add("forensic-toast--visible");
      });

      // Automatisch entfernen
      if (duration > 0) {
        setTimeout(function () {
          if (_active.indexOf(toast) !== -1) _remove(toast);
        }, duration);
      }

      return toast;
    }

    return { show: show, TYPES: Object.keys(TYPES) };
  })();

  // ===========================================================================
  // PHASE KN-1: ContextNavigatorModule — Koordinator Kontext-Navigator
  // ===========================================================================
  // Bauplan: Baustelle 3 Ergänzung Kontext-Navigator v0.6, §2 + §3.
  //
  // Aufgaben:
  //   - Hält den Seiten-Cache (Array von PageSummaryRecord, max. 50 Einträge)
  //   - Invalidiert den Cache bei page:loaded (Fortschrittsgrad kann sich
  //     geändert haben)
  //   - Leitet navigator:page_selected → NavigationModule.loadPage()
  //   - Öffnet Erweiterungs-Suche-Modal (Stub KN-4) bei navigator:modal_open
  //   - Exponiert ForensicToolbar.navigator für Tests und ContextDropdownModule
  //
  // Phase KN-3 ergänzt hier: _loadFromServer() statt Mock-Daten.
  // ===========================================================================
  var ContextNavigatorModule = (function () {

    // Cache: Array<PageSummaryRecord> | null (null = noch nicht geladen)
    var _cache = null;

    // Cache-Ladeversprechen — verhindert parallele Anfragen
    var _loadingPromise = null;

    // Mock-Daten für Phase KN-2 (wird in Phase KN-3 durch Server-Anbindung ersetzt)
    // Beleg: Bauplan KN §12 Phase KN-2 — «Lokale Datenhaltung mit Mock-Daten».
    var MOCK_PAGES = [
      {
        url: "/forum/viewtopic.php?id=7",
        title: "Thema: Tauschangebot",
        scrapeContext: "user",
        fetchFailed: false,
        progressPercent: 52,
        traceCountTotal: 15,
        annotationsTotal: 3,
        tagList: ["username", "pgp"],
        lastViewedAt: Date.now() - 86400000,  // gestern
        firstViewedAt: null,
      },
      {
        url: "/forum/viewtopic.php?id=12",
        title: "Thema: Kontaktaufnahme",
        scrapeContext: "user",
        fetchFailed: false,
        progressPercent: 88,
        traceCountTotal: 8,
        annotationsTotal: 7,
        tagList: ["realname", "email", "telefon"],
        lastViewedAt: Date.now() - 3600000 * 3,
        firstViewedAt: null,
      },
      {
        url: "/forum/profile.php?id=18",
        title: "Profil: Beschuldigter",
        scrapeContext: "investigator",
        fetchFailed: true,
        progressPercent: 30,
        traceCountTotal: 4,
        annotationsTotal: 1,
        tagList: ["foto"],
        lastViewedAt: Date.now() - 86400000 * 3,
        firstViewedAt: null,
      },
      {
        url: "/forum/viewtopic.php?id=19",
        title: "Thema: Allgemein",
        scrapeContext: "user",
        fetchFailed: false,
        progressPercent: 0,
        traceCountTotal: 2,
        annotationsTotal: 0,
        tagList: [],
        lastViewedAt: null,
        firstViewedAt: null,
      },
      {
        url: "/forum/pmsnew.php",
        title: "Private Nachrichten",
        scrapeContext: "user",
        fetchFailed: false,
        progressPercent: 100,
        traceCountTotal: 23,
        annotationsTotal: 12,
        tagList: ["username", "adresse", "krypto"],
        lastViewedAt: Date.now() - 1800000,
        firstViewedAt: null,
      },
      {
        url: "/forum/viewforum.php?id=3",
        title: "Unterforum: Marktplatz",
        scrapeContext: "user",
        fetchFailed: false,
        progressPercent: 65,
        traceCountTotal: 6,
        annotationsTotal: 2,
        tagList: ["krypto"],
        lastViewedAt: Date.now() - 7200000,
        firstViewedAt: null,
      },
    ];

    /**
     * Liefert den Cache als Promise<PageSummaryRecord[]>.
     * Phase KN-3: Echter Server-Aufruf an /_forensic/search.
     * Beleg: Bauplan KN v0.6 §5.6 + §12 Phase KN-3.
     */
    function getPages() {
      if (_cache !== null) {
        return Promise.resolve(_cache);
      }
      if (_loadingPromise) {
        return _loadingPromise;
      }
      // KN-3: Echter Server-Aufruf — zuletzt betrachtete 50 Seiten des
      // aktuellen Benutzers (Daten stammen ausschließlich aus forensic_<uid>.db).
      _loadingPromise = ajaxGet(
        ForensicToolbar.config.API_SEARCH + "?limit=50&sort=last_viewed_desc"
      ).then(function (data) {
        var pages = (data && Array.isArray(data.pages)) ? data.pages : [];
        _cache = pages;
        ForensicToolbar._setState({ contextSearchResults: _cache });
        _loadingPromise = null;
        return _cache;
      }).catch(function (err) {
        _dbg("ContextNavigatorModule.getPages() Fehler", err);
        _loadingPromise = null;
        _cache = [];
        return _cache;
      });
      return _loadingPromise;
    }

    /** Cache invalidieren — wird bei page:loaded aufgerufen */
    function invalidateCache() {
      _cache = null;
      _loadingPromise = null;
      ForensicToolbar._setState({ contextSearchResults: [] });
    }

    function init() {
      // Cache bei Seitennavigation invalidieren (Fortschrittsgrad kann sich ändern)
      ForensicToolbar.events.on("page:loaded", function () {
        invalidateCache();
        // Dropdown informieren, falls geöffnet (es zeigt dann Lade-Indikator)
        ForensicToolbar.events.emit("navigator:cache_invalidated");
      });

      // Seitenauswahl aus Dropdown → NavigationModule
      ForensicToolbar.events.on("navigator:page_selected", function (data) {
        if (data && data.url) {
          ForensicToolbar.navigation.loadPage(data.url, true);
        }
      });

      // Modal öffnen (Stub — KN-4 implementiert das vollständige Modal)
      ForensicToolbar.events.on("navigator:modal_open", function () {
        ForensicToolbar._setState({ contextModalOpen: true });
        ToastModule.show("Erweiterte Suche — folgt in Phase KN-4", ToastModule.TYPES[0]);
      });
    }

    // Öffentliche API
    ForensicToolbar.navigator = {
      getPages:        getPages,
      invalidateCache: invalidateCache,
    };

    return { init: init, getPages: getPages, invalidateCache: invalidateCache };
  })();

  // ===========================================================================
  // PHASE KN-2: ContextDropdownModule — Schnell-Dropdown in Sektion 1
  // ===========================================================================
  // Bauplan: Baustelle 3 Ergänzung Kontext-Navigator v0.6, §5.
  //
  // Aufbau:
  //   [🔍 Kontext [U]▾]  ← Button (mounted in #forensic-sec1)
  //   ┌──────────────────────────────┐
  //   │ 🔍 [ Seitensuche...        ] │  ← Freitextfilter (Debounce 150 ms)
  //   ├──────────────────────────────┤
  //   │ [Alle][Offen][Abg.][Fehlg.] │  ← Schnellfilter-Chips
  //   ├──────────────────────────────┤
  //   │ ... Seiteneinträge ...       │
  //   ├──────────────────────────────┤
  //   │ 🔎 Erweiterte Suche ...      │
  //   └──────────────────────────────┘
  //
  // DOM-Eingriffe: Nur eigene Elemente — kein Eingriff in #forensic-viewport.
  // ARIA: role=combobox + aria-expanded auf Button, role=listbox auf Panel.
  // Tastenkürzel: Alt+K → Button fokussieren / Dropdown öffnen.
  // ===========================================================================
  var ContextDropdownModule = (function () {

    var _btn    = null;   // Dropdown-Button
    var _panel  = null;   // Dropdown-Panel
    var _search = null;   // Sucheingabe
    var _list   = null;   // Seitenliste (ul)

    var _filterText   = "";
    var _filterChip   = "all";   // "all" | "open" | "done" | "failed"
    var _debounceTimer = null;
    var _isOpen       = false;

    // Badge-Klassen nach scrapeContext
    var BADGE_CONFIG = {
      "user":         { label: "U", cls: "forensic-ctx-badge--user",        title: "Nutzersicht" },
      "investigator": { label: "E", cls: "forensic-ctx-badge--investigator", title: "Ermittler-Session" },
      "actor":        { label: "A", cls: "forensic-ctx-badge--actor",        title: "Fremd-Session" },
    };

    function _badgeForContext(scrapeContext) {
      if (!scrapeContext || scrapeContext === "user") {
        return BADGE_CONFIG["user"];
      }
      if (scrapeContext === "investigator") {
        return BADGE_CONFIG["investigator"];
      }
      if (scrapeContext.startsWith("actor:")) {
        return BADGE_CONFIG["actor"];
      }
      return BADGE_CONFIG["user"];
    }

    // -----------------------------------------------------------------------
    // DOM aufbauen
    // -----------------------------------------------------------------------
    function _buildDOM() {
      var sec1 = document.getElementById("forensic-sec1");
      if (!sec1) return;

      // Button
      _btn = document.createElement("button");
      _btn.id        = "forensic-ctx-dropdown-btn";
      _btn.className = "forensic-btn forensic-ctx-dropdown-btn";
      _btn.setAttribute("aria-haspopup", "listbox");
      _btn.setAttribute("aria-expanded", "false");
      _btn.setAttribute("aria-controls", "forensic-ctx-dropdown-panel");
      _btn.setAttribute("title", "Seitenübersicht öffnen [Alt+K]");
      _btn.setAttribute("aria-label", "Seitenübersicht — Ermittlungskontext");
      _btn.innerHTML =
        "<span class=\"forensic-ctx-btn-icon\">🔍</span>" +
        "<span class=\"forensic-ctx-btn-label\">Kontext</span>" +
        "<span id=\"forensic-ctx-badge\" class=\"forensic-ctx-badge forensic-ctx-badge--user\" aria-label=\"Kontext: Nutzersicht\">U</span>" +
        "<span class=\"forensic-ctx-btn-arrow\" aria-hidden=\"true\">▾</span>";

      // Panel
      _panel = document.createElement("div");
      _panel.id        = "forensic-ctx-dropdown-panel";
      _panel.className = "forensic-ctx-panel";
      _panel.setAttribute("role", "listbox");
      _panel.setAttribute("aria-label", "Seitenübersicht");
      _panel.hidden = true;
      _panel.innerHTML =
        // Suchzeile
        "<div class=\"forensic-ctx-search-row\">" +
          "<span class=\"forensic-ctx-search-icon\" aria-hidden=\"true\">🔍</span>" +
          "<input id=\"forensic-ctx-search\" type=\"search\" " +
            "class=\"forensic-ctx-search\" placeholder=\"Seitensuche...\" " +
            "autocomplete=\"off\" aria-label=\"Seiten durchsuchen\" />" +
        "</div>" +
        // Schnellfilter-Chips
        "<div class=\"forensic-ctx-chips\" role=\"group\" aria-label=\"Schnellfilter\">" +
          "<button class=\"forensic-ctx-chip forensic-ctx-chip--active\" data-filter=\"all\">Alle</button>" +
          "<button class=\"forensic-ctx-chip\" data-filter=\"open\">Offen</button>" +
          "<button class=\"forensic-ctx-chip\" data-filter=\"done\">Abgeschlossen</button>" +
          "<button class=\"forensic-ctx-chip\" data-filter=\"failed\">Fehlgeschlagen</button>" +
        "</div>" +
        // Seitenliste
        "<ul id=\"forensic-ctx-list\" class=\"forensic-ctx-list\" role=\"presentation\">" +
          "<li class=\"forensic-ctx-loading\" aria-live=\"polite\">Lade…</li>" +
        "</ul>" +
        // Footer
        "<div class=\"forensic-ctx-footer\">" +
          "<button id=\"forensic-ctx-modal-btn\" class=\"forensic-ctx-modal-link\">" +
            "🔎 Erweiterte Suche öffnen…" +
          "</button>" +
        "</div>";

      sec1.appendChild(_btn);
      // Panel an document.body hängen — NICHT an #forensic-toolbar.
      // #forensic-toolbar hat overflow:hidden und height:62px, was das Panel
      // abschneidet oder den Toolbar-Inhalt verdrängt.
      // position:fixed in der CSS-Klasse + dynamische Top/Left-Berechnung
      // in _open() via getBoundingClientRect() positioniert das Panel
      // korrekt unterhalb des Buttons, unabhängig vom DOM-Kontext.
      // Beleg: Build 067-Fix — Panel verdrängte Toolbar-Inhalt nach oben.
      document.body.appendChild(_panel);

      _search = document.getElementById("forensic-ctx-search");
      _list   = document.getElementById("forensic-ctx-list");
    }

    // -----------------------------------------------------------------------
    // Events verdrahten
    // -----------------------------------------------------------------------
    function _bindEvents() {
      // Guard: DOM nicht aufgebaut (z.B. minimale JSDOM-Testumgebung ohne
      // #forensic-sec1 / #forensic-toolbar). _buildDOM() setzt _btn/_ panel
      // nur wenn #forensic-sec1 vorhanden ist. Fehlt es, bricht diese Funktion
      // sofort ab — kein Absturz, kein Event-Binding.
      // Beleg: Build 066-Fix — test_levenshtein/test_state crashten weil
      // _btn null war. JSDOM-Tests ohne vollständiges Shell-HTML brauchen keinen
      // Event-Binding-Versuch.
      if (!_btn || !_panel) return;

      // Button-Klick → Dropdown toggeln
      _btn.addEventListener("click", function (e) {
        e.stopPropagation();
        _isOpen ? _close() : _open();
      });

      // Tastatureingaben auf dem Button
      _btn.addEventListener("keydown", function (e) {
        if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (!_isOpen) _open();
          // Fokus in Suche verschieben
          setTimeout(function () { if (_search) _search.focus(); }, 30);
        }
        if (e.key === "Escape") { _close(); }
      });

      // Klick außerhalb schließt
      document.addEventListener("click", function (e) {
        if (_isOpen && !_panel.contains(e.target) && e.target !== _btn) {
          _close();
        }
      });

      // Escape im Panel
      _panel.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
          _close();
          _btn.focus();
        }
      });

      // Freitextfilter (Debounce 150 ms — Bauplan KN §5.4)
      _search.addEventListener("input", function () {
        clearTimeout(_debounceTimer);
        _debounceTimer = setTimeout(function () {
          _filterText = _search.value.trim().toLowerCase();
          _renderList();
        }, 150);
      });

      // Schnellfilter-Chips
      _panel.addEventListener("click", function (e) {
        var chip = e.target.closest("[data-filter]");
        if (chip) {
          _filterChip = chip.dataset.filter;
          _panel.querySelectorAll(".forensic-ctx-chip").forEach(function (c) {
            c.classList.toggle("forensic-ctx-chip--active", c.dataset.filter === _filterChip);
          });
          _renderList();
          return;
        }
        // Seiteneintrag
        var item = e.target.closest("[data-url]");
        if (item) {
          var url = item.dataset.url;
          _close();
          ForensicToolbar.events.emit("navigator:page_selected", { url: url });
          return;
        }
        // Erweiterte Suche
        if (e.target.id === "forensic-ctx-modal-btn" || e.target.closest("#forensic-ctx-modal-btn")) {
          _close();
          ForensicToolbar.events.emit("navigator:modal_open");
        }
      });

      // Tastaturnavigation in der Liste (Pfeil rauf/runter)
      _list.addEventListener("keydown", function (e) {
        var items = Array.from(_list.querySelectorAll("[data-url]"));
        if (!items.length) return;
        var idx = items.indexOf(document.activeElement);
        if (e.key === "ArrowDown") {
          e.preventDefault();
          (items[idx + 1] || items[0]).focus();
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          if (idx <= 0) { _search.focus(); } else { items[idx - 1].focus(); }
        } else if (e.key === "Enter" && idx >= 0) {
          e.preventDefault();
          items[idx].click();
        }
      });

      // Cache-Invalidierung → neu laden wenn Dropdown offen
      ForensicToolbar.events.on("navigator:cache_invalidated", function () {
        if (_isOpen) {
          _showLoading();
          _loadAndRender();
        }
      });
    }

    // -----------------------------------------------------------------------
    // Öffnen / Schließen
    // -----------------------------------------------------------------------
    function _open() {
      _isOpen = true;
      // Panel unterhalb des Buttons positionieren (position:fixed im Body).
      // getBoundingClientRect() liefert viewport-relative Koordinaten.
      // Beleg: Build 067-Fix — Panel liegt jetzt im Body-DOM, braucht
      // explizite Positionierung statt CSS-Relative zum Toolbar.
      var rect = _btn.getBoundingClientRect();
      _panel.style.top  = (rect.bottom + 4) + "px";
      _panel.style.left = rect.left + "px";
      _panel.hidden = false;
      _btn.setAttribute("aria-expanded", "true");
      _btn.classList.add("forensic-ctx-dropdown-btn--open");
      ForensicToolbar._setState({ contextDropdownOpen: true });
      _loadAndRender();
      // Fokus in Suchfeld
      setTimeout(function () { if (_search) _search.focus(); }, 30);
    }

    function _close() {
      _isOpen = false;
      _panel.hidden = true;
      _btn.setAttribute("aria-expanded", "false");
      _btn.classList.remove("forensic-ctx-dropdown-btn--open");
      ForensicToolbar._setState({ contextDropdownOpen: false });
    }

    function _showLoading() {
      if (_list) {
        _list.innerHTML = "<li class=\"forensic-ctx-loading\" aria-live=\"polite\">Lade…</li>";
      }
    }

    // -----------------------------------------------------------------------
    // Daten laden + rendern
    // -----------------------------------------------------------------------
    function _loadAndRender() {
      _showLoading();
      ContextNavigatorModule.getPages().then(function (pages) {
        _renderList(pages);
      });
    }

    /**
     * Filtert und rendert die Seitenliste.
     * pages: PageSummaryRecord[] — wenn weggelassen, wird _state.contextSearchResults verwendet.
     */
    function _renderList(pages) {
      var all = pages || ForensicToolbar.state.get("contextSearchResults") || [];

      // Text-Filter (URL + Titel)
      var filtered = all.filter(function (p) {
        if (_filterText) {
          var haystack = (p.url + " " + (p.title || "")).toLowerCase();
          if (haystack.indexOf(_filterText) === -1) return false;
        }
        // Schnellfilter-Chip
        if (_filterChip === "open")   return p.progressPercent < 100;
        if (_filterChip === "done")   return p.progressPercent >= 100;
        if (_filterChip === "failed") return p.fetchFailed === true;
        return true;
      });

      if (!_list) return;

      if (!filtered.length) {
        _list.innerHTML = "<li class=\"forensic-ctx-empty\">Keine Seiten gefunden.</li>";
        return;
      }

      _list.innerHTML = "";

      // Maximal 8 Einträge ohne Scrollen (CSS regelt das via max-height)
      filtered.forEach(function (p) {
        var li = document.createElement("li");
        li.className = "forensic-ctx-item";
        li.setAttribute("role", "option");
        li.setAttribute("tabindex", "0");
        li.setAttribute("data-url", p.url);
        li.setAttribute("aria-label",
          (p.title || p.url) + " · " + p.progressPercent + "% ausgewertet");

        var badge     = _badgeForContext(p.scrapeContext);
        var pct       = p.progressPercent || 0;
        var barClass  = pct >= 80 ? "forensic-ctx-bar--green"
                      : pct >= 30 ? "forensic-ctx-bar--yellow"
                      : "forensic-ctx-bar--red";
        var segments  = "";
        var filled    = Math.round(pct / 10);
        for (var i = 0; i < 10; i++) {
          segments += "<span class=\"forensic-ctx-seg" + (i < filled ? " forensic-ctx-seg--on" : "") + "\"></span>";
        }
        var urlShort  = _shortenUrl(p.url);
        // Anzeigename: Titel bevorzugt (Themenbetreff, PN-Betreff, Profilname),
        // Fallback auf gekürzte URL. Bauplan KN §5.3 — URL als Tooltip.
        var displayTitle = (p.title && p.title.trim()) ? p.title.trim() : urlShort;
        var failIcon  = p.fetchFailed ? " <span class=\"forensic-ctx-fail\" aria-label=\"Abruf fehlgeschlagen\">⚠️</span>" : "";
        var lastViewed = p.lastViewedAt ? _relativeTime(p.lastViewedAt) : "—";

        li.innerHTML =
          "<div class=\"forensic-ctx-item-row\">" +
            "<div class=\"forensic-ctx-bar-wrap " + barClass + "\" aria-hidden=\"true\">" +
              segments +
            "</div>" +
            "<span class=\"forensic-ctx-pct\">" + pct + "%</span>" +
            "<span class=\"forensic-ctx-traces\" title=\"Spuren\">🔗 " + (p.traceCountTotal || 0) + "</span>" +
            "<span class=\"forensic-ctx-anns\"   title=\"Annotationen\">📌 " + (p.annotationsTotal || 0) + "</span>" +
            // Titel + ggf. Fehlerindikator; volle URL im title-Attribut als Tooltip
            "<span class=\"forensic-ctx-title\" title=\"" + _esc(p.url) + "\">" + _esc(displayTitle) + failIcon + "</span>" +
          "</div>" +
          "<div class=\"forensic-ctx-item-meta\">" +
            "<span class=\"forensic-ctx-badge " + badge.cls + "\" title=\"" + badge.title + "\">" + badge.label + "</span>" +
            // URL als Subzeile (klein, gedimmt) — gibt technischen Kontext ohne
            // die lesbare Titelzeile zu überladen
            "<span class=\"forensic-ctx-url-sub\" title=\"" + _esc(p.url) + "\">" + _esc(urlShort) + "</span>" +
            "<span class=\"forensic-ctx-time\">" + _esc(lastViewed) + "</span>" +
          "</div>";

        _list.appendChild(li);
      });
    }

    // -----------------------------------------------------------------------
    // Hilfsfunktionen
    // -----------------------------------------------------------------------

    /** URL auf 40 Zeichen kürzen — nur Pfad+Query, kein Host */
    function _shortenUrl(url) {
      try {
        var u = new URL(url, "http://placeholder");
        var short = u.pathname + u.search;
        if (short.length > 40) {
          short = short.substring(0, 37) + "…";
        }
        return short;
      } catch (e) {
        return url.length > 40 ? url.substring(0, 37) + "…" : url;
      }
    }

    /** Relatives Zeitformat (z.B. "heute 14:22", "gestern", "vor 3 Tagen") */
    function _relativeTime(ts) {
      if (!ts) return "—";
      var now  = Date.now();
      var diff = now - ts;
      var d    = new Date(ts);
      var hhmm = d.getHours().toString().padStart(2, "0") + ":" + d.getMinutes().toString().padStart(2, "0");
      if (diff < 86400000) {
        var today = new Date();
        if (d.getDate() === today.getDate()) {
          return "heute " + hhmm;
        }
        return "gestern " + hhmm;
      }
      var days = Math.round(diff / 86400000);
      if (days === 1) return "gestern";
      if (days < 7)  return "vor " + days + " Tagen";
      return d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" });
    }

    // -----------------------------------------------------------------------
    // Öffentliche API
    // -----------------------------------------------------------------------

    /**
     * updateBadge(scrapeContext) — wird von ContextBadgeModule.update() aufgerufen.
     * Aktualisiert das Kontext-Badge im Dropdown-Button.
     * Beleg: Build 066 — ContextBadgeModule delegiert an diese Funktion.
     */
    function updateBadge(scrapeContext) {
      var badgeEl = document.getElementById("forensic-ctx-badge");
      if (!badgeEl) return;
      var cfg = _badgeForContext(scrapeContext);
      badgeEl.textContent = cfg.label;
      badgeEl.className   = "forensic-ctx-badge " + cfg.cls;
      badgeEl.setAttribute("aria-label", "Kontext: " + cfg.title);
    }

    function init() {
      _buildDOM();
      _bindEvents();

      // Alt+K → Dropdown öffnen/fokussieren (Bauplan KN §11)
      document.addEventListener("keydown", function (e) {
        if (e.altKey && e.key === "k") {
          e.preventDefault();
          if (_isOpen) { _close(); _btn.focus(); }
          else { _btn.focus(); _open(); }
        }
      });

      // Badge bei Navigation mitführen
      ForensicToolbar.events.on("page:loaded", function (data) {
        if (data && data.scrapeContext !== undefined) {
          updateBadge(data.scrapeContext);
        }
      });
    }

    return { init: init, updateBadge: updateBadge };
  })();

  // ===========================================================================
  // PHASE KN-8: HintsModule — Kontextsensitive Hinweiszeile (OP-KN-8)
  // ===========================================================================
  // Bauplan: OP-KN-8, Build 075.
  //
  // Aufbau:
  //   [forensic-toolbar]  (fixed, top:0, height:62px)
  //   [forensic-hintbar]  (fixed, top:62px, height:28px, animiert)
  //   [body / viewport]   verschiebt sich dynamisch per CSS-Variable
  //                       --forensic-hintbar-height (0 oder 28px)
  //
  // API:
  //   HintsModule.set(text)     — Text setzen (Modul bringt eigenen Text)
  //   HintsModule.clear()       — Standardtext wiederherstellen
  //   HintsModule.show()        — Zeile einblenden (falls manuell versteckt)
  //   HintsModule.hide()        — Zeile ausblenden
  //
  // Toggle-Button (#forensic-hints-toggle):
  //   ⍖ = Zeile sichtbar (aria-expanded="true")
  //   ⍏ = Zeile versteckt (aria-expanded="false")
  //
  // Persistenz: Sichtbarkeitszustand in sessionStorage gespeichert
  //   (bleibt während der Ermittlungssitzung erhalten, Reset bei Neustart).
  //
  // Beleg: OP-KN-8, Projektgespräch 2026-04-27.
  // ===========================================================================
  var HintsModule = (function () {

    // Standardtext wenn kein Modul aktiv ist
    var DEFAULT_TEXT =
      "Kategorie wählen und Textstelle markieren — oder auf einen Beitrag klicken für Post-Markierung.";

    var _currentText = DEFAULT_TEXT;
    var _visible     = true;  // Startzustand: sichtbar
    var _bar         = null;  // DOM-Element #forensic-hintbar
    var _textEl      = null;  // DOM-Element #forensic-hint-text
    var _toggleBtn   = null;  // DOM-Element #forensic-hints-toggle

    // SessionStorage-Key für Persistenz
    var STORAGE_KEY = "forensic_hintbar_visible";

    // -----------------------------------------------------------------------
    // DOM aufbauen (wird in init() aufgerufen)
    // -----------------------------------------------------------------------
    function _buildBar() {
      _bar = document.createElement("div");
      _bar.id        = "forensic-hintbar";
      _bar.className = "forensic-hintbar";
      _bar.setAttribute("role", "status");
      _bar.setAttribute("aria-live", "polite");
      _bar.setAttribute("aria-label", "Kontextsensitiver Hinweis");
      _bar.setAttribute("aria-atomic", "true");

      _textEl = document.createElement("span");
      _textEl.id        = "forensic-hint-text";
      _textEl.className = "forensic-hint-text";
      _textEl.setAttribute("aria-label", "Hinweistext");
      _textEl.textContent = _currentText;

      _bar.appendChild(_textEl);
      document.body.appendChild(_bar);
    }

    // -----------------------------------------------------------------------
    // CSS-Variable aktualisieren → verschiebt Viewport
    // -----------------------------------------------------------------------
    function _updateOffset() {
      var h = _visible ? "28px" : "0px";
      document.documentElement.style.setProperty("--forensic-hintbar-height", h);
    }

    // -----------------------------------------------------------------------
    // Toggle-Button-Icon synchronisieren
    // -----------------------------------------------------------------------
    function _syncToggleBtn() {
      if (!_toggleBtn) return;
      // 🛈▲ = Zeile sichtbar → Klick blendet aus (Pfeil nach oben = einfahren)
      // 🛈▼ = Zeile versteckt → Klick blendet ein (Pfeil nach unten = ausfahren)
      // Beleg: Projektgespräch 2026-04-27 — Symbole korrigiert.
      _toggleBtn.textContent = _visible ? "🛈▲" : "🛈▼";
      _toggleBtn.setAttribute("aria-expanded", _visible ? "true" : "false");
      _toggleBtn.setAttribute("aria-label",
        _visible ? "Hinweiszeile ausblenden" : "Hinweiszeile einblenden");
      _toggleBtn.title = _visible ? "Hinweiszeile ausblenden" : "Hinweiszeile einblenden";
    }

    // -----------------------------------------------------------------------
    // Sichtbarkeit anwenden (mit Animation via CSS-Klasse)
    // -----------------------------------------------------------------------
    function _applyVisibility() {
      if (!_bar) return;
      if (_visible) {
        _bar.classList.remove("forensic-hintbar--hidden");
      } else {
        _bar.classList.add("forensic-hintbar--hidden");
      }
      _updateOffset();
      _syncToggleBtn();
      // Persistenz
      try { sessionStorage.setItem(STORAGE_KEY, _visible ? "1" : "0"); } catch (e) {}
    }

    // -----------------------------------------------------------------------
    // Öffentliche API
    // -----------------------------------------------------------------------

    /** Text setzen — Modul bringt eigenen Hinweistext */
    function set(text) {
      _currentText = text || DEFAULT_TEXT;
      if (_textEl) _textEl.textContent = _currentText;
    }

    /** Standardtext wiederherstellen */
    function clear() {
      _currentText = DEFAULT_TEXT;
      if (_textEl) _textEl.textContent = _currentText;
    }

    /** Zeile einblenden */
    function show() {
      _visible = true;
      _applyVisibility();
    }

    /** Zeile ausblenden */
    function hide() {
      _visible = false;
      _applyVisibility();
    }

    /** Toggle */
    function toggle() {
      _visible = !_visible;
      _applyVisibility();
    }

    // -----------------------------------------------------------------------
    // Init
    // -----------------------------------------------------------------------
    function init() {
      // Sichtbarkeitszustand aus sessionStorage wiederherstellen
      try {
        var stored = sessionStorage.getItem(STORAGE_KEY);
        if (stored === "0") _visible = false;
      } catch (e) {}

      _buildBar();
      _updateOffset();

      // Toggle-Button verdrahten
      _toggleBtn = document.getElementById("forensic-hints-toggle");
      if (_toggleBtn) {
        _toggleBtn.addEventListener("click", function () { toggle(); });
      }

      _applyVisibility();

      // Kategorie-Aktivierung → Hinweistext anpassen
      ForensicToolbar.events.on("state:changed", function (updates) {
        if ("activeCategory" in updates) {
          var cat = updates.activeCategory;
          if (!cat) {
            clear();
            return;
          }
          // Kategorie-spezifische Texte (Beleg: §19 Bauplan B3 — Kategoriensystem)
          var CAT_HINTS = {
            CAT_PERSON:   "👤 PER aktiv — Textstelle mit persönlichem Identifikationsmerkmal auswählen (Name, Alias, Kontaktdaten…)",
            CAT_LOCATION: "📍 LOC aktiv — Textstelle mit Ortsangabe oder geografischem Hinweis auswählen",
            CAT_176:      "⚖️ §176 aktiv — Textstelle mit Relevanz für §§ 176, 176a StGB auswählen",
            CAT_184:      "🔴 §184 aktiv — Textstelle mit Relevanz für §§ 184b, 184c StGB auswählen",
            CAT_VICTIM:   "🛡️ OPF aktiv — Textstelle mit Hinweis auf mögliche Opfer auswählen",
            CAT_OTHER:    "📎 SON aktiv — Textstelle mit sonstiger Ermittlungsrelevanz auswählen",
          };
          set(CAT_HINTS[cat] || ("Kategorie " + cat + " aktiv — Textstelle auswählen"));
        }
      });

      // Fetch-Fehler → Warnung
      ForensicToolbar.events.on("page:loaded", function (data) {
        if (data && data.fetchFailed) {
          set("⚠️ Diese Seite konnte beim Abruf nicht geladen werden — der angezeigte Inhalt ist möglicherweise unvollständig.");
        } else if (data && data.scrapeContext === "investigator") {
          set("🔴 Ermittler-Session — diese Seite wurde mit dem Ermittler-Account abgerufen. Der Beschuldigte hatte möglicherweise keinen Zugriff.");
        } else {
          clear();
        }
      });
    }

    // Öffentlich exponieren für andere Module
    ForensicToolbar.hints = { set: set, clear: clear, show: show, hide: hide };

    return { init: init, set: set, clear: clear, show: show, hide: hide };
  })();

  // ===========================================================================
  // CSS-Highlight-Regeln für CSS Custom Highlights API (§5 Bauplan)
  //
  // Die Highlight-Sets werden im HighlightModule vorinitialisiert und in
  // CSS.highlights registriert. Diese Funktion injiziert ausschließlich die
  // zugehörigen ::highlight()-CSS-Regeln in den <head>. Ohne diese Regeln
  // würden die registrierten Sets keine sichtbare Wirkung haben.
  // Beleg: PoC highlight_poc.html — ::highlight()-Regeln im <style>-Block.
  // ===========================================================================
  (function _injectHighlightStyles() {
    if (typeof CSS === "undefined" || !CSS.highlights) return;
    var style = document.createElement("style");
    var rules = ForensicToolbar.config.CATEGORIES.map(function (cat) {
      var name = "forensic-" + cat.id.toLowerCase();
      // Kategorie-Farbe mit 55% Deckkraft — konsistent mit PoC-Werten
      return "::highlight(" + name + ") { background-color: " + cat.color + "55; }";
    });
    style.textContent = rules.join("\n");
    document.head.appendChild(style);
  })();

  // ===========================================================================
  // Initialisierung
  // ===========================================================================
  document.addEventListener("DOMContentLoaded", function () {
    // Phase 1+2: Toolbar aufbauen
    ToolbarUIModule.build();

    // Phase 9: ARIA-Live-Region
    AccessibilityModule.init();

    // Phase 7: Minimap initialisieren
    MinimapModule.init();

    // Phase KN-8: Hinweiszeile
    HintsModule.init();

    // Phase 12: SSE-Stream starten
    SupportIndicatorModule.init();

    // Phase KN-1+2: Kontext-Navigator initialisieren
    // ContextNavigatorModule muss vor ContextDropdownModule init laufen
    // (Navigator.getPages wird vom Dropdown benötigt).
    ContextNavigatorModule.init();
    ContextDropdownModule.init();

    // Session-Status laden
    ajaxGet(ForensicToolbar.config.API_STATUS)
      .then(function (s) {
        ForensicToolbar._setState({
          // Bug 2.67 (Build 175): investigator_username = Ermittler (z.B. "paul"),
          // NICHT s.username = Beschuldigter (z.B. "uid_538299").
          // Beleg: Projektgespraech 2026-05-11 — status.py liefert jetzt investigator_username.
          investigatorUsername: s.investigator_username || s.user_id || "—",
          forumHostname:        s.forum_hostname || "",
          // Bug 2.77 (Build 175): Beschuldigten-Username + user_id für Popup-Anzeige.
          // _state.username/user_id werden vom AnnotationPopupModule verwendet.
          username: s.username || null,
          user_id:  s.user_id  || null,
        });
        ToolbarUIModule.updateSessionInfo();
        console.info(
          "[Forensic] Server:", s.version,
          "| Modus:", s.mode,
          "| Beschuldigter:", s.username,
          "| Seiten:", s.page_count,
        );
      })
      .catch(function () {});

    // Phase 3: Initiale Seite laden (Two-Phase-Load)
    NavigationModule.loadPage(
      location.pathname + location.search, false
    );
  });

  // ---------------------------------------------------------------------------
  // Diagnose-Hilfsfunktionen (Build 063)
  // Aufruf in der Browser-Console — kein Reload erforderlich.
  // ---------------------------------------------------------------------------

  /**
   * window.forensicTestHighlight()
   * Testet die Highlight-Wiederherstellung für alle Annotationen im aktuellen State.
   * Gibt eine Übersicht in der Console aus.
   *
   * Anleitung:
   *   1. Seite mit einer Annotation aufrufen (AJAX-Navigation)
   *   2. In der Browser-Console eingeben: forensicTestHighlight()
   *   3. Ausgabe zeigt für jede Annotation ob XPath auflösbar ist
   */
  window.forensicTestHighlight = function () {
    var anns = _state.annotations;
    console.group("[Forensic Diagnose] forensicTestHighlight() — " + anns.size + " Annotations");
    console.log("viewMode:", _state.viewMode);
    console.log("cssHighlightsAvailable:", typeof CSS !== "undefined" && typeof CSS.highlights !== "undefined");
    var vp = document.getElementById("forensic-viewport");
    console.log("viewport exists:", !!vp, "children:", vp ? vp.children.length : 0);

    anns.forEach(function (ann, key) {
      console.group("Annotation " + key + " (id=" + ann.id + ", cat=" + ann.category + ")");
      console.log("hasSelection:", !!ann.selection);
      console.log("postId:", ann.postId);
      console.log("syncState:", ann.syncState);
      if (ann.selection) {
        console.log("selection:", ann.selection);
        var restored = AnnotationStoreModule.rangeFromSelection(ann.selection);
        console.log("rangeFromSelection result:", restored);
        if (restored) {
          console.log("range text:", restored.range.toString().substring(0, 80));
          console.log("stale:", restored.stale);
        }
      }
      console.groupEnd();
    });
    console.groupEnd();
  };

  /**
   * window.forensicForceRestoreAll()
   * Erzwingt restoreAll() für Highlights und PostMarker sofort.
   * Nützlich um zu testen ob der Timing-Fix wirkt.
   */
  window.forensicForceRestoreAll = function () {
    console.log("[Forensic Diagnose] forensicForceRestoreAll() — forciere Highlight-Restore");
    HighlightModule.clearAll();
    HighlightModule.restoreAll();
    PostMarkerModule.clearAll();
    PostMarkerModule.restoreAll();
    MinimapModule.refresh();
    console.log("[Forensic Diagnose] Done. Annotations im State:", _state.annotations.size);
  };

})();
