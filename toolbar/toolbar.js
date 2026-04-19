/**
 * toolbar.js — Forensischer Werkzeugbalken
 * IT-Forensisches Ermittlungswerkzeug · Baustelle 3
 *
 * Version: v0.1.0 · Build: 030 · 2026-04-16
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 *
 * Änderungen Build 030-A:
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
      if (!sel) return null;
      var startNode = _nodeFromXpath(sel.xpathStart);
      var endNode   = _nodeFromXpath(sel.xpathEnd);
      if (!startNode || !endNode) return null;
      try {
        var range = document.createRange();
        range.setStart(startNode, sel.offsetStart);
        range.setEnd(endNode, sel.offsetEnd);
        // Verifikation: textContent gegen gespeicherten Wert prüfen
        var actual = range.toString().trim();
        var stored = (sel.textContent || "").trim();
        var stale  = (actual !== stored);
        return { range: range, stale: stale };
      } catch (e) {
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
      _state.annotations.forEach(function (ann) {
        renderHighlight(ann);
      });
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

          // Sektion 1: Kontext-Badge
          '<div class="forensic-section forensic-sec1" aria-label="Ermittlungskontext">' +
          '<span id="forensic-context-badge" role="status" aria-live="polite" ' +
          'class="forensic-badge forensic-badge-user">Nutzersicht</span>' +
          '</div>' +

        '</div>' + // /zone-left

        // =====================================================================
        // ZONE MITTE — zentriert über die gesamte verbleibende Breite
        // Enthält: Seitenkontext-Dropdown | Marker-Buttons | Aktionen
        // =====================================================================
        '<div class="forensic-zone forensic-zone-center">' +

          // Sektion 2a: Seitenkontext-Dropdown (§OP-6, Dummy Build 030-B)
          // Ermöglicht Sprung zu anderen Seiten des Benutzers.
          // Funktionalität wird in späterem Build ergänzt.
          '<div class="forensic-section forensic-sec-context" aria-label="Seitenkontext">' +
          '<span class="forensic-sec-label">Kontext</span>' +
          '<select id="forensic-context-select" class="forensic-select" ' +
          'aria-label="Seitenkontext wählen" title="Seite direkt auswählen" disabled>' +
          '<option value="">— Seite wählen —</option>' +
          '</select>' +
          '</div>' +
          '<div class="forensic-separator" aria-hidden="true"></div>' +

          // Sektion 2b: Markier-Werkzeuge
          '<div class="forensic-section forensic-sec2" role="group" aria-label="Markierungskategorien">' +
          cats +
          '</div>' +
          '<div class="forensic-separator" aria-hidden="true"></div>' +

          // Sektion 3: Aktionen
          '<div class="forensic-section forensic-sec3">' +
          '<button id="forensic-btn-userinfo" class="forensic-btn" ' +
          'aria-label="Nutzerinfo-Tab öffnen (Alt+U)" title="Nutzerinfo öffnen [Alt+U]">' +
          '👤 Nutzerinfo</button>' +
          '<button id="forensic-btn-next-ann" class="forensic-btn" ' +
          'aria-label="Zur nächsten unkommentierten Annotation springen" ' +
          'title="Nächste Annotation">' +
          '▶ Nächste</button>' +
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

          // Sektion 4: Seitennavigation mit Spurennummer-Eingabe (§OP-5, Dummy Build 030-B)
          // Das Eingabefeld ermöglicht direktes Anspringen einer Spur per Nummer.
          // Funktionalität wird in späterem Build ergänzt (Annotation-Navigation).
          '<div class="forensic-section forensic-sec4" aria-label="Seitennavigation">' +
          '<button id="forensic-btn-nav-prev" class="forensic-btn forensic-nav-btn" ' +
          'aria-label="Vorherige Seite (Alt+Pfeil links)" title="Vorherige Seite [Alt+←]">◀</button>' +
          '<span id="forensic-page-info" class="forensic-page-info" aria-label="Seitenposition">—</span>' +
          '<button id="forensic-btn-nav-next" class="forensic-btn forensic-nav-btn" ' +
          'aria-label="Nächste Seite (Alt+Pfeil rechts)" title="Nächste Seite [Alt+→]">▶</button>' +
          '</div>' +
          '<div class="forensic-separator" aria-hidden="true"></div>' +

          // Spurennummer-Eingabe (Dummy)
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
          '<div class="forensic-separator" aria-hidden="true"></div>' +

          // Sektion 5: Session-Info
          '<div class="forensic-section forensic-sec5" aria-label="Sitzungsinformationen">' +
          '<span id="forensic-session-user" class="forensic-session-info">…</span>' +
          '<span id="forensic-annotation-count" class="forensic-session-info" ' +
          'aria-label="Anzahl Annotationen auf dieser Seite">0 Ann.</span>' +
          '<span id="forensic-sync-status" class="forensic-sync-ok" aria-live="polite" ' +
          'aria-label="Synchronisierungsstatus"></span>' +
          '<span id="forensic-support-indicator" class="forensic-support-hidden" ' +
          'role="status" aria-live="assertive"></span>' +
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

    function _jumpToNextAnnotation() {
      var first = null;
      _state.annotations.forEach(function (ann) {
        if (!ann.text && !first) first = ann;
      });
      if (!first) return;
      var el = first.elementId
        ? document.getElementById(first.elementId)
        : null;
      if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
    }

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

    function loadPage(url, pushState) {
      AccessibilityModule.announce("Lade Seite…");
      ajaxGet(ForensicToolbar.config.API_PAGE + "?url=" + encodeURIComponent(url))
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

      ForensicToolbar._setState({
        currentUrl:    envelope.url_canonical || url,
        baseHref:      (envelope.head && envelope.head.base_href) || null,
        scrapeContext: envelope.scrape_context || "user",
        fetchFailed:   !!envelope.fetch_failed,
        inScope:       !!envelope.in_scope,
        fragment:      envelope.fragment || null,
        // Build 030-C: Benutzer-Spuren aus Envelope übernehmen.
        // Leeres Array wenn Server keine Spuren liefert (älterer Build,
        // NOT_IN_SCOPE, oder tatsächlich keine Spuren auf dieser Seite).
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
        HighlightModule.restoreAll();
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
          loadPage(href, true);
        });
      });
    }

    function _detectPagination(viewport, envelope) {
      _prevUrl = null; _nextUrl = null;
      // FluxBB-Paginierung: Links mit rel="prev"/"next" oder Klasse "paged-num"
      var prevA = viewport.querySelector("a[rel='prev']");
      var nextA = viewport.querySelector("a[rel='next']");
      _prevUrl = prevA ? prevA.getAttribute("href") : null;
      _nextUrl = nextA ? nextA.getAttribute("href") : null;
      var pageInfo = document.getElementById("forensic-page-info");
      if (pageInfo) pageInfo.textContent = (_prevUrl || _nextUrl) ? "Paginierung aktiv" : "—";
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
  var AnnotationPopupModule = (function () {
    var _currentAnn = null;
    var _popupEl    = null;

    function open(ann) {
      _currentAnn = ann;
      _render(ann);
    }

    function close(save) {
      if (save && _currentAnn) {
        _currentAnn.text = _getFieldValue("forensic-popup-text");
        _currentAnn.tags = _parseTags(_getFieldValue("forensic-popup-tags"));
        AnnotationStoreModule.syncAnnotation(_currentAnn);
        ForensicToolbar.events.emit("annotation:created", _currentAnn);
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

    function _render(ann) {
      if (_popupEl) _popupEl.remove();

      var cat  = _getCat(ann.category);
      var catLabel = cat ? (cat.icon + " " + cat.label) : ann.category;

      _popupEl = document.createElement("div");
      _popupEl.id = "forensic-annotation-popup";
      _popupEl.setAttribute("role", "dialog");
      _popupEl.setAttribute("aria-modal", "true");
      _popupEl.setAttribute("aria-labelledby", "forensic-popup-title");
      _popupEl.className = "forensic-popup";
      _popupEl.innerHTML =
        '<div class="forensic-popup-header">' +
        '<span id="forensic-popup-title" class="forensic-popup-title">' +
        'Annotation · <span style="color:' + (cat ? cat.color : "#aaa") + '">' +
        _esc(catLabel) + '</span></span>' +
        '<button class="forensic-popup-close" aria-label="Schließen" ' +
        'id="forensic-popup-btn-close">✕</button>' +
        '</div>' +
        '<div class="forensic-popup-body">' +
        '<label for="forensic-popup-text" class="forensic-popup-label">Notiz (optional):</label>' +
        '<textarea id="forensic-popup-text" class="forensic-popup-textarea" ' +
        'aria-label="Ermittlungsnotiz eingeben" rows="3">' + _esc(ann.text) + '</textarea>' +
        '<label for="forensic-popup-tags" class="forensic-popup-label">Tags (mit Komma trennen):</label>' +
        '<input type="text" id="forensic-popup-tags" class="forensic-popup-input" ' +
        'aria-label="Tags eingeben, mit Komma getrennt" value="' + _esc((ann.tags || []).join(", ")) + '">' +
        '<div id="forensic-popup-tag-suggestion" class="forensic-popup-suggestion" style="display:none"></div>' +
        (ann.selection ?
          '<label class="forensic-popup-label">Markierter Text:</label>' +
          '<div class="forensic-popup-seltext">' + _esc(ann.selection.textContent) + '</div>' : "") +
        '</div>' +
        '<div class="forensic-popup-footer">' +
        '<button id="forensic-popup-btn-cancel" class="forensic-btn forensic-btn-secondary">Abbrechen</button>' +
        '<button id="forensic-popup-btn-save" class="forensic-btn forensic-btn-primary">💾 Speichern</button>' +
        '</div>';

      document.body.appendChild(_popupEl);
      _positionPopup(ann);

      // Fokus auf Notiz-Feld (§8 Bauplan)
      var txtArea = document.getElementById("forensic-popup-text");
      if (txtArea) txtArea.focus();

      // Event-Listener
      document.getElementById("forensic-popup-btn-close").addEventListener("click", function () { close(false); });
      document.getElementById("forensic-popup-btn-cancel").addEventListener("click", function () { close(false); });
      document.getElementById("forensic-popup-btn-save").addEventListener("click", function () { close(true); });

      // Levenshtein-Vorschlag beim Tag-Tippen (§19.2 Bauplan)
      var tagInput = document.getElementById("forensic-popup-tags");
      if (tagInput) {
        tagInput.addEventListener("input", function () {
          var last = (tagInput.value.split(",").pop() || "").trim();
          var sug  = ForensicToolbar.config.suggestTag(last, []);
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
            "button, textarea, input, [tabindex]:not([tabindex='-1'])"
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

    /** Popup nah an Markierung positionieren, nie über Toolbar (§8 Bauplan) */
    function _positionPopup(ann) {
      if (!_popupEl) return;
      var tb = ForensicToolbar.config.TOOLBAR_HEIGHT;
      var pw = _popupEl.offsetWidth || 420;
      var ph = _popupEl.offsetHeight || 280;
      var vw = window.innerWidth;
      var vh = window.innerHeight;

      var left = Math.max(8, Math.min(vw - pw - 8, (vw - pw) / 2));
      var top  = tb + 8;

      // Wenn Platz unter aktueller Scrollposition → nahe Mitte
      if (vh - tb - 8 > ph) {
        top = tb + Math.max(8, (vh - tb - ph) / 3);
      }

      _popupEl.style.left = left + "px";
      _popupEl.style.top  = top + "px";
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

    return { open: open, close: close };
  })();

  // ===========================================================================
  // PHASE 6: HoverMenuModule — Mini-Werkzeugleiste beim Hover
  // ===========================================================================
  var HoverMenuModule = (function () {
    var _timer   = null;
    var _menuEl  = null;
    var _targetAnn = null;

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

    function _showMenu(ann, x, y) {
      _hideMenu();
      _targetAnn = ann;
      _menuEl = document.createElement("div");
      _menuEl.className = "forensic-hover-menu";
      _menuEl.innerHTML =
        '<button class="forensic-hover-btn" data-action="edit" aria-label="Annotation bearbeiten">✏️</button>' +
        '<button class="forensic-hover-btn" data-action="delete" aria-label="Annotation löschen">🗑️</button>';
      _menuEl.style.left = x + "px";
      _menuEl.style.top  = y + "px";
      document.body.appendChild(_menuEl);

      _menuEl.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-action]");
        if (!btn) return;
        if (btn.dataset.action === "edit") {
          _hideMenu();
          AnnotationPopupModule.open(_targetAnn);
        } else if (btn.dataset.action === "delete") {
          _hideMenu();
          _state.annotations.delete(_targetAnn.localId || String(_targetAnn.id));
          HighlightModule.clearAll();
          HighlightModule.restoreAll();
          PostMarkerModule.clearAll();
          PostMarkerModule.restoreAll();
          MinimapModule.refresh();
          ForensicToolbar.events.emit("annotation:deleted", _targetAnn);
          ToolbarUIModule.updateSessionInfo();
        }
      });

      _menuEl.addEventListener("mouseleave", _hideMenu);
    }

    function _hideMenu() {
      if (_menuEl) { _menuEl.remove(); _menuEl = null; }
    }

    // Viewport-Event-Listener
    ForensicToolbar.events.on("page:loaded", function () {
      var vp = document.getElementById("forensic-viewport");
      if (!vp) return;

      vp.addEventListener("mouseover", function (e) {
        var ann = _findAnnotationAtElement(e.target);
        if (!ann) return;
        clearTimeout(_timer);
        _timer = setTimeout(function () {
          _showMenu(ann, e.pageX, e.pageY - 40);
        }, ForensicToolbar.config.HOVER_DELAY_MS);
      });

      vp.addEventListener("mouseout", function (e) {
        var related = e.relatedTarget;
        if (!related || !related.closest || !related.closest(".forensic-hover-menu")) {
          clearTimeout(_timer);
          if (!(_menuEl && _menuEl.matches(":hover"))) _hideMenu();
        }
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
      _state.traceElements.forEach(function (elemId) {
        var el = document.getElementById(elemId);
        if (!el) return;
        var pct = _pctOf(el);
        var bar = _makeBar(
          pct,
          "#3a5a8a",   // gedämpftes Grau-Blau — neutral, nicht kategorisiert
          "Spur: " + elemId,
          function () { el.scrollIntoView({ behavior: "smooth", block: "center" }); }
        );
        bar.className = "forensic-minimap-trace";
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
  // Navigation erfolgt über _state.traceElements (DOM-Element-IDs).
  // Index ist 1-basiert in der UI, 0-basiert intern.
  //
  // Beleg: §OP-4 Anforderung — Navigation zwischen Spuren per Pfeiltasten
  //        und Direkteingabe.
  // ===========================================================================
  var TraceNavigationModule = (function () {
    var _currentIdx = -1; // 0-basiert; -1 = keine Spur angesprungen

    // Listener-Referenzen für sauberes Entfernen ohne cloneNode
    var _prevListener = null;
    var _nextListener = null;
    var _inputKeyListener = null;
    var _inputBlurListener = null;

    // -------------------------------------------------------------------------
    // _update — UI-Elemente auf aktuellen Index synchronisieren
    // -------------------------------------------------------------------------
    function _update() {
      var traces  = _state.traceElements;
      var total   = traces.length;

      var inputEl = document.getElementById("forensic-trace-input");
      var totalEl = document.getElementById("forensic-trace-total");
      var prevBtn = document.getElementById("forensic-btn-trace-prev");
      var nextBtn = document.getElementById("forensic-btn-trace-next");

      // Elemente müssen existieren — Toolbar ist permanent im DOM
      if (!inputEl || !totalEl || !prevBtn || !nextBtn) {
        console.warn("[Forensic] TraceNavigation: UI-Elemente nicht gefunden.");
        return;
      }

      var hasTraces = total > 0;

      // Gesamtanzahl immer aktualisieren
      totalEl.textContent = "/ " + total;

      // Buttons und Eingabe aktivieren/deaktivieren
      inputEl.disabled = !hasTraces;
      prevBtn.disabled = !hasTraces || _currentIdx <= 0;
      nextBtn.disabled = !hasTraces || _currentIdx >= total - 1;

      // Eingabefeld
      inputEl.max         = String(total);
      inputEl.value       = (hasTraces && _currentIdx >= 0)
        ? String(_currentIdx + 1)  // 1-basiert in der UI
        : "";
      inputEl.placeholder = hasTraces ? "1" : "—";
    }

    // -------------------------------------------------------------------------
    // jumpTo — Zu einer Spur springen (0-basierter Index)
    // -------------------------------------------------------------------------
    function jumpTo(idx) {
      var traces = _state.traceElements;
      if (!traces.length) return;
      idx = Math.max(0, Math.min(traces.length - 1, idx));
      _currentIdx = idx;

      var elemId = traces[idx];
      var el = document.getElementById(elemId);

      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.style.transition = "outline 0.1s";
        el.style.outline    = "3px solid #4f8ef7";
        setTimeout(function () { el.style.outline = ""; }, 1200);
        AccessibilityModule.announce(
          "Spur " + (idx + 1) + " von " + traces.length + ": " + traces[idx]
        );
      }
      _update();
    }

    // -------------------------------------------------------------------------
    // init — Wird nach jedem Seitenload aufgerufen.
    // Setzt Listener neu (ohne cloneNode — über gespeicherte Referenzen).
    // -------------------------------------------------------------------------
    function init() {
      _currentIdx = -1;

      var prevBtn = document.getElementById("forensic-btn-trace-prev");
      var nextBtn = document.getElementById("forensic-btn-trace-next");
      var input   = document.getElementById("forensic-trace-input");

      // Alte Listener sauber entfernen bevor neue gesetzt werden
      if (prevBtn && _prevListener) {
        prevBtn.removeEventListener("click", _prevListener);
      }
      if (nextBtn && _nextListener) {
        nextBtn.removeEventListener("click", _nextListener);
      }
      if (input && _inputKeyListener) {
        input.removeEventListener("keydown", _inputKeyListener);
        input.removeEventListener("blur",    _inputBlurListener);
      }

      // Neue Listener anlegen und Referenzen speichern
      _prevListener = function () {
        jumpTo(_currentIdx <= 0 ? 0 : _currentIdx - 1);
      };
      _nextListener = function () {
        jumpTo(_currentIdx < 0 ? 0 : _currentIdx + 1);
      };
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

      // UI-Zustand setzen — traceElements sind zu diesem Zeitpunkt im State
      _update();
    }

    // Nach Seitenload neu initialisieren.
    // traceElements wurden bereits via _setState() in _handleEnvelope gesetzt,
    // bevor page:loaded emittiert wird — _update() in init() liest den
    // korrekten Wert.
    ForensicToolbar.events.on("page:loaded", function () {
      setTimeout(init, 0);
    });

    // State-Änderung an traceElements → Anzeige aktualisieren
    ForensicToolbar.events.on("state:changed", function (updates) {
      if ("traceElements" in updates) {
        _currentIdx = -1;
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
  var ContextBadgeModule = (function () {

    function update(scrapeContext) {
      var badge = document.getElementById("forensic-context-badge");
      if (!badge) return;

      badge.className = "forensic-badge";

      if (scrapeContext === "investigator") {
        badge.textContent = "🔴 ERMITTLER-SESSION";
        badge.className  += " forensic-badge-investigator";
        _showInvestigatorBanner();
      } else if (scrapeContext && scrapeContext.startsWith("actor:")) {
        var uid = scrapeContext.split(":")[1] || "?";
        badge.textContent = "⚠ Fremd-Session · Nutzer #" + uid;
        badge.className  += " forensic-badge-actor";
        _hideInvestigatorBanner();
      } else {
        badge.textContent = "✓ Nutzersicht";
        badge.className  += " forensic-badge-user";
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

    // Phase 12: SSE-Stream starten
    SupportIndicatorModule.init();

    // Session-Status laden
    ajaxGet(ForensicToolbar.config.API_STATUS)
      .then(function (s) {
        ForensicToolbar._setState({
          investigatorUsername: s.username || s.user_id || "—",
          forumHostname:        s.forum_hostname || "",
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

})();
