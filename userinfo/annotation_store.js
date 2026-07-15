// =============================================================================
// userinfo/annotation_store.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
// -----------------------------------------------------------------------------
// ZWECK (gesicherte Intention):
//   EINZIGE Zustandsquelle ("single source of truth") der Recherche. Haelt die
//   Rohliste aller Annotationen des Beschuldigten UND das aktuelle Filter-
//   prädikat. Alle Sichten (Liste, spaeter Netz/Zeitstrahl/Steckbrief) haengen
//   sich als Beobachter an und werden bei jeder Zustandsaenderung benachrichtigt
//   (Leitbild §2 des Bauplans: "an einer Stelle anfassen, ueberall Reaktion").
//
//   Netzzugriff ausschliesslich hier gekapselt:
//     - GET  /_forensic/annotations           (Rohdaten laden; Beleg annotations.py:135)
//     - POST /_forensic/annotate              (Upsert via local_id; Beleg annotate.py:118)
//   Reine Ableitungen (Filtern/Sortieren/Facetten) delegiert der Store an den
//   testbaren Kern window.AIWAnnotationFilter (eigene Datei, Grundregel 10).
//
//   MIGRATION/01.07.2026: rein lesend + bestehender Schreibendpunkt. KEINE
//   Schemaaenderung an evidence_/forensic_/assets_-DB.
// =============================================================================

(function () {
  'use strict';

  var DEBUG = false;
  function dbg() {
    if (DEBUG && typeof console !== 'undefined') {
      console.log.apply(console, ['[AIW-Store]'].concat([].slice.call(arguments)));
    }
  }

  var API_ANNOTATIONS = '/_forensic/annotations';
  var API_ANNOTATE    = '/_forensic/annotate';
  // Header identisch zu Toolbar/Sidebar (Beleg annotation_sidebar.js:169,
  // toolbar.js:710). KEIN CSRF-Token im System.
  var AJAX_HEADERS = { 'X-Forensic-Request': 'ajax' };

  function AnnotationStore() {
    this._raw = [];                         // Rohliste (unveraendert vom Server)
    this._predicate = window.AIWAnnotationFilter.emptyPredicate();
    this._sortKey = 'time';
    this._sortDir = 'desc';                  // neueste zuerst
    this._listeners = [];                    // Beobachter: fn(view)
    this._loaded = false;
    this._lastError = null;
  }

  // --- Beobachter-Muster ------------------------------------------------------
  AnnotationStore.prototype.subscribe = function (fn) {
    if (typeof fn === 'function' && this._listeners.indexOf(fn) === -1) {
      this._listeners.push(fn);
    }
    return this;
  };
  AnnotationStore.prototype._notify = function () {
    var view = this.getView();
    this._listeners.forEach(function (fn) {
      try { fn(view); } catch (e) {
        if (typeof console !== 'undefined') console.error('[AIW-Store] Listener-Fehler:', e);
      }
    });
  };

  // --- Laden ------------------------------------------------------------------
  // Laedt ALLE Annotationen (ohne url-Param → evidence.get_all_annotations()).
  AnnotationStore.prototype.load = function () {
    var self = this;
    dbg('load()…');
    return fetch(API_ANNOTATIONS, { headers: AJAX_HEADERS, credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        // Vertrag: { annotations: [...], status: "ok" } (annotations.py:165)
        self._raw = (data && Array.isArray(data.annotations)) ? data.annotations : [];
        self._loaded = true;
        self._lastError = null;
        dbg('geladen:', self._raw.length, 'Annotationen');
        self._notify();
        return self._raw;
      })
      .catch(function (err) {
        self._lastError = err;
        self._loaded = true;   // "geladen mit Fehler" — Sicht kann Hinweis zeigen (GR1)
        if (typeof console !== 'undefined') console.error('[AIW-Store] Ladefehler:', err);
        self._notify();
        throw err;
      });
  };

  // reload(): erneut vom Server holen (nach Schreibvorgang), damit Versionskette
  // (id/versionNr/prevId) und Tags konsistent bleiben. Der Datensatz eines
  // einzelnen Beschuldigten ist beschraenkt → Vollreload ist unkritisch.
  AnnotationStore.prototype.reload = function () { return this.load(); };

  // --- Prädikat / Sortierung --------------------------------------------------
  AnnotationStore.prototype.getPredicate = function () { return this._predicate; };

  // setPredicate(patch): Teil-Update des Prädikats. Jede Facette schreibt nur
  // ihren Teil; danach EINE Benachrichtigung an alle Sichten.
  AnnotationStore.prototype.setPredicate = function (patch) {
    var p = this._predicate, k;
    for (k in patch) { if (Object.prototype.hasOwnProperty.call(patch, k)) p[k] = patch[k]; }
    dbg('setPredicate', patch);
    this._notify();
    return this;
  };

  AnnotationStore.prototype.resetPredicate = function () {
    this._predicate = window.AIWAnnotationFilter.emptyPredicate();
    this._notify();
    return this;
  };

  AnnotationStore.prototype.setSort = function (key, dir) {
    this._sortKey = key || this._sortKey;
    this._sortDir = dir || this._sortDir;
    this._notify();
    return this;
  };

  // --- Ableitungen (an den reinen Kern delegiert) -----------------------------
  AnnotationStore.prototype.getAll = function () { return this._raw.slice(); };

  AnnotationStore.prototype.getFiltered = function () {
    var F = window.AIWAnnotationFilter;
    return F.sortAnnotations(F.applyFilter(this._raw, this._predicate), this._sortKey, this._sortDir);
  };

  // getView(): kompaktes Objekt, das die Sichten zum Rendern brauchen.
  AnnotationStore.prototype.getView = function () {
    var F = window.AIWAnnotationFilter;
    var filtered = this.getFiltered();
    return {
      loaded: this._loaded,
      error: this._lastError,
      total: this._raw.length,
      filtered: filtered,
      shown: filtered.length,
      facets: F.computeFacets(this._raw),       // Facetten aus Gesamtmenge (stabil)
      predicate: this._predicate,
      sortKey: this._sortKey,
      sortDir: this._sortDir
    };
  };

  AnnotationStore.prototype.getById = function (id) {
    for (var i = 0; i < this._raw.length; i++) {
      if (String(this._raw[i].id) === String(id)) return this._raw[i];
    }
    return null;
  };

  // --- Schreiben (Upsert via local_id) ---------------------------------------
  // canEdit(ann): Editieren/Tagging ist nur sicher, wenn local_id vorhanden ist.
  // Der Server-Upsert schluesselt auf local_id; bei fehlender local_id wuerde
  // ein Schreibvorgang eine DUPLIKAT-Annotation anlegen statt zu aktualisieren.
  // Deshalb: kein stiller Fallback, sondern Editieren gesperrt + Hinweis (GR1).
  AnnotationStore.prototype.canEdit = function (ann) {
    return !!(ann && ann.localId);
  };

  // _toApiBody(ann, overrides): camelCase-Annotation → snake_case-Request-Body
  // (Beleg annotate.py:118–134). Alle Felder werden erhalten, damit die neue
  // Version verlustfrei ist; nur 'overrides' (z. B. tags/text/category) aendern.
  AnnotationStore.prototype._toApiBody = function (ann, overrides) {
    overrides = overrides || {};
    var body = {
      page_url:       ann.pageUrl || '',
      category:       ('category' in overrides) ? overrides.category : ann.category,
      text:           ('text' in overrides) ? overrides.text : (ann.text || ''),
      element_id:     ann.elementId != null ? ann.elementId : null,
      local_id:       ann.localId,
      post_id:        ann.postId != null ? ann.postId : null,
      tags:           ('tags' in overrides) ? overrides.tags : (ann.tags || []),
      selection:      ann.selection != null ? ann.selection : null,
      target_user_id: ann.actualUid != null ? ann.actualUid : null
    };
    return body;
  };

  // saveEdit(ann, overrides): schreibt eine geaenderte Version und laedt neu.
  // Rueckgabe: Promise. Wirft bei fehlender local_id (canEdit=false).
  AnnotationStore.prototype.saveEdit = function (ann, overrides) {
    var self = this;
    if (!this.canEdit(ann)) {
      return Promise.reject(new Error('Annotation ohne local_id — Bearbeiten gesperrt (Duplikatschutz).'));
    }
    var body = this._toApiBody(ann, overrides);
    dbg('saveEdit POST', body);
    return fetch(API_ANNOTATE, {
      method: 'POST',
      headers: Object.assign({ 'Content-Type': 'application/json' }, AJAX_HEADERS),
      credentials: 'same-origin',
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok || !res.j || res.j.status !== 'ok') {
          throw new Error((res.j && res.j.error) || 'Speichern fehlgeschlagen');
        }
        dbg('saveEdit ok, neue id', res.j.id);
        return self.reload();
      });
  };

  // addTags(ann, newTags): Convenience — Tags additiv zusammenfuehren (Set-Union,
  // Reihenfolge stabil), dann als Edit speichern. Kern der "Tagging als
  // Erkenntnisarbeit"-Idee (Bauplan §7/§11).
  AnnotationStore.prototype.addTags = function (ann, newTags) {
    var merged = (ann.tags || []).slice();
    var lower = merged.map(function (t) { return String(t).toLowerCase(); });
    (newTags || []).forEach(function (t) {
      var tt = String(t).trim();
      if (tt && lower.indexOf(tt.toLowerCase()) === -1) { merged.push(tt); lower.push(tt.toLowerCase()); }
    });
    return this.saveEdit(ann, { tags: merged });
  };

  // removeTag(ann, tag): einen Tag entfernen (z. B. Fehlvergabe korrigieren).
  AnnotationStore.prototype.removeTag = function (ann, tag) {
    var t = String(tag).toLowerCase();
    var merged = (ann.tags || []).filter(function (x) { return String(x).toLowerCase() !== t; });
    return this.saveEdit(ann, { tags: merged });
  };

  window.AIWAnnotationStore = AnnotationStore;
  window.AIWAnnotationStore._setDebug = function (v) { DEBUG = !!v; };
})();
