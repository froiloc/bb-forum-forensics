/**
 * toolbar.js — Forensischer Werkzeugbalken (Stub / Proof of Concept)
 * IT-Forensisches Ermittlungswerkzeug · Baustelle 2
 *
 * Stand Build 010: Minimaler Stub. Beweist den Two-Phase-Load-Mechanismus.
 * Die vollständige Implementierung erfolgt in Baustelle 3.
 *
 * Was dieser Stub tut:
 *   1. Beim Laden: AJAX-Request auf /_forensic/page?url=<aktuelle URL>
 *   2. BLOB-Inhalt in #forensic-viewport injizieren
 *   3. Alle Link-Klicks abfangen und per AJAX nachladen
 *   4. Einen "Annotieren"-Knopf anzeigen (sendet Beispiel-Annotation)
 *   5. Viewport-Tracking mit IntersectionObserver (Basis-Implementierung)
 */

(function () {
  "use strict";

  // -------------------------------------------------------------------------
  // Konfiguration
  // -------------------------------------------------------------------------
  const API_PAGE      = "/_forensic/page";
  const API_ANNOTATE  = "/_forensic/annotate";
  const API_VIEWPORT  = "/_forensic/viewport";
  const API_STATUS    = "/_forensic/status";

  // -------------------------------------------------------------------------
  // Hilfsfunktionen
  // -------------------------------------------------------------------------

  /** Sendet einen AJAX-GET und gibt ein Promise<Object> zurück. */
  function ajaxGet(url) {
    return fetch(url, {
      headers: { "X-Forensic-Request": "ajax" }
    }).then(function (r) { return r.json(); });
  }

  /** Sendet einen AJAX-POST mit JSON-Body. */
  function ajaxPost(url, data) {
    return fetch(url, {
      method:  "POST",
      headers: {
        "Content-Type":      "application/json",
        "X-Forensic-Request": "ajax"
      },
      body: JSON.stringify(data)
    }).then(function (r) { return r.json(); });
  }

  // -------------------------------------------------------------------------
  // Toolbar-Status anzeigen
  // -------------------------------------------------------------------------

  function setToolbarStatus(text, color) {
    var el = document.getElementById("forensic-status-text");
    if (el) {
      el.textContent = text;
      el.style.color = color || "#c8d0e8";
    }
  }

  function setContextBadge(scrapeContext) {
    var badge = document.getElementById("forensic-context-badge");
    if (!badge) return;
    if (scrapeContext === "investigator") {
      badge.textContent = "⚠ ERMITTLER-SESSION";
      badge.style.backgroundColor = "#e84040";
      badge.style.color = "#fff";
    } else if (scrapeContext && scrapeContext.startsWith("actor:")) {
      badge.textContent = "⚠ FREMD-SESSION";
      badge.style.backgroundColor = "#f5a623";
      badge.style.color = "#fff";
    } else {
      badge.textContent = "USER-SESSION";
      badge.style.backgroundColor = "#2a7a2a";
      badge.style.color = "#fff";
    }
  }

  // -------------------------------------------------------------------------
  // Seite per AJAX laden (Two-Phase-Load + Navigation)
  // -------------------------------------------------------------------------

  function loadPage(url, pushState) {
    setToolbarStatus("Lade…", "#aaa");

    ajaxGet(API_PAGE + "?url=" + encodeURIComponent(url))
      .then(function (envelope) {
        var viewport = document.getElementById("forensic-viewport");
        if (!viewport) return;

        if (!envelope.in_scope) {
          viewport.innerHTML =
            "<p style='color:#e84040;padding:20px'>" +
            "⚠ Diese Seite liegt nicht im Umfang der Ermittlungen.<br>" +
            "<small>URL: " + _esc(url) + "</small></p>";
          setToolbarStatus("NICHT IM SCOPE", "#e84040");
          setContextBadge(null);
          return;
        }

        if (envelope.fetch_failed || !envelope.html) {
          viewport.innerHTML =
            "<p style='color:#f5a623;padding:20px'>" +
            "⚠ Seite erfasst, Abruf fehlgeschlagen (HTTP " +
            envelope.http_status + ").<br>" +
            "<small>URL: " + _esc(url) + "</small></p>";
          setToolbarStatus("ABRUF FEHLGESCHLAGEN (HTTP " + envelope.http_status + ")", "#f5a623");
          return;
        }

        // BLOB-Inhalt injizieren
        viewport.innerHTML = envelope.html;

        // Zum Fragment scrollen falls vorhanden
        if (envelope.fragment) {
          var target = document.getElementById(envelope.fragment) ||
                       document.getElementsByName(envelope.fragment)[0];
          if (target) { target.scrollIntoView({ block: "start" }); }
        }

        // Toolbar aktualisieren
        setContextBadge(envelope.scrape_context);
        setToolbarStatus("Bereit", "#4caf50");

        // Aktuelle URL im Toolbar anzeigen
        var urlEl = document.getElementById("forensic-current-url");
        if (urlEl) { urlEl.textContent = envelope.url_canonical || url; }

        // Browser-Adressleiste aktualisieren
        if (pushState) {
          history.pushState({ forensicUrl: url }, "", url);
        }

        // Links im neuen Inhalt abfangen
        _interceptLinks(viewport);

        // Viewport-Tracking starten
        _startViewportTracking(viewport, envelope.url_canonical || url);
      })
      .catch(function (err) {
        setToolbarStatus("Fehler: " + err.message, "#e84040");
        console.error("[Forensic] Ladefehler:", err);
      });
  }

  // -------------------------------------------------------------------------
  // Link-Abfangung
  // -------------------------------------------------------------------------

  function _interceptLinks(container) {
    var links = container.querySelectorAll("a[href]");
    links.forEach(function (a) {
      a.addEventListener("click", function (e) {
        var href = a.getAttribute("href");
        if (!href || href.startsWith("#") || href.startsWith("javascript:")) return;
        // Externe Links durchlassen
        if (href.startsWith("http") && !href.includes(location.hostname)) return;
        e.preventDefault();
        loadPage(href, true);
      });
    });
  }

  // -------------------------------------------------------------------------
  // Viewport-Tracking (Basis)
  // -------------------------------------------------------------------------

  var _viewportBuffer = [];
  var _currentPageUrl = "";
  var _flushTimer     = null;
  var _observer       = null;
  var _enterTimes     = {};

  function _startViewportTracking(container, pageUrl) {
    _currentPageUrl = pageUrl;
    _viewportBuffer = [];
    if (_observer) { _observer.disconnect(); }
    _enterTimes = {};

    if (!window.IntersectionObserver) return;

    _observer = new IntersectionObserver(function (entries) {
      var now = Date.now();
      entries.forEach(function (entry) {
        var id = entry.target.id || entry.target.dataset.postId || null;
        if (!id) return;

        if (entry.isIntersecting) {
          _enterTimes[id] = now;
        } else {
          var enter = _enterTimes[id];
          if (enter) {
            _viewportBuffer.push({
              element_id: id,
              visible_ms: now - enter,
              ts_enter:   enter,
              ts_leave:   now
            });
            delete _enterTimes[id];
          }
        }
      });
      _scheduleFlush();
    }, { threshold: 0.5 });

    // Post-Elemente beobachten (typisches FluxBB-Muster: id="p12345")
    container.querySelectorAll("[id^='p']").forEach(function (el) {
      if (/^p\d+$/.test(el.id)) { _observer.observe(el); }
    });
  }

  function _scheduleFlush() {
    if (_flushTimer) return;
    _flushTimer = setTimeout(_flushViewportBuffer, 2000);
  }

  function _flushViewportBuffer() {
    _flushTimer = null;
    if (!_viewportBuffer.length || !_currentPageUrl) return;
    var toSend = _viewportBuffer.splice(0);
    ajaxPost(API_VIEWPORT, {
      page_url: _currentPageUrl,
      events:   toSend
    }).catch(function (e) {
      console.warn("[Forensic] Viewport-Flush fehlgeschlagen:", e);
    });
  }

  // -------------------------------------------------------------------------
  // Annotation senden (Stub-Demo)
  // -------------------------------------------------------------------------

  function sendAnnotation(category, text, elementId) {
    var url = document.getElementById("forensic-current-url");
    var pageUrl = (url && url.textContent) || location.pathname + location.search;

    ajaxPost(API_ANNOTATE, {
      page_url:   pageUrl,
      element_id: elementId || null,
      category:   category,
      text:       text
    }).then(function (r) {
      if (r.status === "ok") {
        setToolbarStatus("Annotation #" + r.id + " gespeichert", "#4caf50");
        setTimeout(function () { setToolbarStatus("Bereit", "#4caf50"); }, 2000);
      } else {
        setToolbarStatus("Fehler: " + (r.error || "unbekannt"), "#e84040");
      }
    }).catch(function (e) {
      setToolbarStatus("Netzfehler: " + e.message, "#e84040");
    });
  }

  // -------------------------------------------------------------------------
  // Toolbar-UI aufbauen
  // -------------------------------------------------------------------------

  function buildToolbar() {
    var toolbar = document.getElementById("forensic-toolbar");
    if (!toolbar) return;

    toolbar.innerHTML =
      '<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;' +
      'font-family:monospace;font-size:12px;background:#1a1f2e;border-bottom:2px solid #2d3550;">' +

      // Kontext-Badge
      '<span id="forensic-context-badge" style="padding:3px 8px;border-radius:3px;' +
      'background:#555;color:#fff;font-size:10px;font-weight:bold">…</span>' +

      // Aktuelle URL
      '<span style="color:#5a6580;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' +
      'URL: <span id="forensic-current-url" style="color:#c8d0e8">' +
      _esc(location.pathname + location.search) + '</span></span>' +

      // Status
      '<span id="forensic-status-text" style="color:#aaa">Initialisiere…</span>' +

      // Demo-Annotier-Knopf (Stub für Baustelle 3)
      '<button onclick="window._forensicAnnotateDemo()" ' +
      'style="padding:4px 10px;background:#4f8ef7;color:#fff;border:none;' +
      'border-radius:3px;cursor:pointer;font-size:11px">' +
      'Annotieren (Demo)</button>' +

      '</div>';
  }

  // Demo-Funktion für den Stub-Knopf
  window._forensicAnnotateDemo = function () {
    var text = prompt("Anmerkung eingeben:", "");
    if (text === null) return;
    sendAnnotation("CAT_OTHER", text || "(leer)", null);
  };

  // -------------------------------------------------------------------------
  // Browser-Navigation (Vorwärts/Zurück)
  // -------------------------------------------------------------------------

  window.addEventListener("popstate", function (e) {
    var url = (e.state && e.state.forensicUrl) ||
              location.pathname + location.search;
    loadPage(url, false);
  });

  // -------------------------------------------------------------------------
  // HTML-Escaping
  // -------------------------------------------------------------------------

  function _esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // -------------------------------------------------------------------------
  // Initialisierung
  // -------------------------------------------------------------------------

  document.addEventListener("DOMContentLoaded", function () {
    buildToolbar();

    // Two-Phase-Load: aktuell angezeigte URL per AJAX laden
    var initialUrl = location.pathname + location.search;
    loadPage(initialUrl, false);

    // Status vorab laden (für spätere Nutzung durch Baustelle 3)
    ajaxGet(API_STATUS).then(function (s) {
      console.info(
        "[Forensic] Server:", s.version,
        "| Modus:", s.mode,
        "| Beschuldigter:", s.username,
        "| Seiten:", s.page_count
      );
    }).catch(function () {});
  });

})();
