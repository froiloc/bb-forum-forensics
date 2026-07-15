// =============================================================================
// userinfo/annotation_filter.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
// -----------------------------------------------------------------------------
// ZWECK (gesicherte Intention):
//   Reine, seiteneffektfreie Filter-, Facetten- und Sortierlogik fuer die
//   Annotationsrecherche im Nutzerinfo-Tab. Dieses Modul kennt KEIN DOM und
//   KEINEN Netzwerkzugriff — es ist der testbare Rechenkern (Grundregel 3/9,
//   vitest gegen echten Code). Store (Netz/Zustand) und View (DOM) bauen darauf
//   auf, jede Klasse in eigener Datei (Grundregel 10).
//
// DATENVERTRAG (belegt in forensic_api/annotations.py:135–165):
//   Eine Annotation ist ein Objekt mit den camelCase-Feldern:
//     id, pageUrl, category, text, tags[], elementId, selection, postId,
//     localId, createdAt (ms), createdBy, syncState, versionNr, prevId,
//     actualUid, sowie OPTIONAL contentTs (Sekunden, Unix-Epoch) — letzteres
//     wird erst in einer spaeteren Welle (Zeitstrahl) serverseitig ergaenzt;
//     dieses Modul ist bereits darauf vorbereitet (annotationTimeMs()).
//
// Kategorien 1:1 aus toolbar.js:499–506 / annotation_sidebar.js:78–115
// uebernommen (Belegtreue: gleiche id/label/icon/color/Reihenfolge).
// =============================================================================

(function () {
  'use strict';

  // DEV-Debug-Logging: fuer PROD auf false setzen. Hilft in der DEV-Phase zu
  // sehen, welches Praedikat greift und wie viele Treffer verbleiben.
  var DEBUG = false;
  function dbg() {
    if (DEBUG && typeof console !== 'undefined') {
      console.log.apply(console, ['[AIW-Filter]'].concat([].slice.call(arguments)));
    }
  }

  // ---------------------------------------------------------------------------
  // Kategorie-Metadaten (kanonische Reihenfolge = Tastenkuerzel 1–6 in B3).
  // Beleg: toolbar/toolbar.js:499–506.
  // ---------------------------------------------------------------------------
  var CATEGORIES = [
    { id: 'CAT_PERSON',   label: 'PER', icon: '👤', color: '#f5c842', desc: 'Persönliche Identifikationsmerkmale' },
    { id: 'CAT_LOCATION', label: 'LOC', icon: '📍', color: '#4f8ef7', desc: 'Ortsangaben, geografische Hinweise' },
    { id: 'CAT_176',      label: '176', icon: '⚖️', color: '#e84040', desc: 'Relevanz §§ 176, 176a StGB' },
    { id: 'CAT_184',      label: '184', icon: '🔴', color: '#c040e8', desc: 'Relevanz §§ 184b, 184c StGB' },
    { id: 'CAT_VICTIM',   label: 'OPF', icon: '🛡️', color: '#e87040', desc: 'Hinweise auf mögliche Opfer' },
    { id: 'CAT_OTHER',    label: 'SON', icon: '📎', color: '#40c8a0', desc: 'Sonstige Ermittlungsrelevanz' }
  ];
  var CATEGORY_ORDER = CATEGORIES.map(function (c) { return c.id; });
  var CATEGORY_BY_ID = {};
  CATEGORIES.forEach(function (c) { CATEGORY_BY_ID[c.id] = c; });

  // Tag-Vokabular (Beleg: toolbar/toolbar.js:509–513). Rein informativ fuer
  // Vorschlaege; freie Tags bleiben zulaessig.
  var TAG_VOCABULARY = [
    'username', 'realname', 'email', 'telefon', 'adresse', 'ort', 'land',
    'ip', 'pgp', 'passwort', 'datum', 'foto', 'sprache', 'gerät',
    'krypto', 'social', 'telegram', 'signatur', 'opfer', 'alter'
  ];

  // Identitaets-Tags: jene Tags, die unmittelbar der Personenzuordnung dienen.
  // Werden vom (spaeteren) Steckbrief priorisiert; hier bereits definiert,
  // damit die Sortierung "Identitaetsrelevanz" schon nutzbar ist.
  var IDENTITY_TAGS = [
    'realname', 'email', 'telefon', 'adresse', 'ip', 'pgp', 'social',
    'telegram', 'foto', 'username'
  ];

  // Hypothesen-/Vermutungs-Tags: markieren NICHT gesicherte Einlassungen.
  // Trennung Vermutung/Beleg ist forensische Pflicht (Grundregel 1). Die
  // optische Absetzung/der dedizierte Filter folgt vollstaendig in Welle 2;
  // die Erkennung liegt bereits hier im reinen Kern.
  var HYPOTHESIS_TAGS = ['vermutung', 'hypothese'];

  // Quellenarten. Ableitung heuristisch aus pageUrl/postId (PunBB/FluxBB-URLs).
  // Als Heuristik gekennzeichnet — bei Unsicherheit 'other' statt Fehlzuordnung.
  var SOURCES = [
    { id: 'post',    label: 'Beitrag',  icon: '📄' },
    { id: 'pm',      label: 'PN',       icon: '✉️' },
    { id: 'profile', label: 'Profil',   icon: '👤' },
    { id: 'file',    label: 'Datei',    icon: '📁' },
    { id: 'other',   label: 'Sonstige', icon: '📎' }
  ];

  function categoryMeta(id) {
    return CATEGORY_BY_ID[id] || { id: id, label: String(id || '?'), icon: '❓', color: '#8a90a8', desc: '' };
  }

  // ---------------------------------------------------------------------------
  // deriveSource(ann): Quellenart einer Annotation bestimmen.
  // Reihenfolge bewusst: PN und Profil zuerst pruefen (spezifischer), dann
  // Datei, dann Beitrag (postId/viewtopic), sonst 'other'.
  // ---------------------------------------------------------------------------
  function deriveSource(ann) {
    var url = String((ann && ann.pageUrl) || '').toLowerCase();
    if (url.indexOf('pms') !== -1 || url.indexOf('message') !== -1 || url.indexOf('/pm') !== -1) return 'pm';
    if (url.indexOf('profile.php') !== -1 || url.indexOf('userinfo') !== -1) return 'profile';
    if (url.indexOf('gallery') !== -1 || url.indexOf('share') !== -1 ||
        url.indexOf('download') !== -1 || url.indexOf('dl.php') !== -1 || url.indexOf('/file') !== -1) return 'file';
    if ((ann && ann.postId != null) || url.indexOf('viewtopic') !== -1) return 'post';
    return 'other';
  }

  // annotationTimeMs(ann): einheitlicher Zeitzugriff in Millisekunden.
  // Bevorzugt die Inhaltszeit (contentTs, Sekunden) sobald vorhanden (Welle 3),
  // sonst die Annotationszeit (createdAt, bereits ms). So ist der Zeitraum-Filter
  // vorwaertskompatibel, ohne dass die View sich aendern muss.
  function annotationTimeMs(ann) {
    if (ann && ann.contentTs != null && !isNaN(ann.contentTs)) return Number(ann.contentTs) * 1000;
    if (ann && ann.createdAt != null && !isNaN(ann.createdAt)) return Number(ann.createdAt);
    return null;
  }

  function isHypothesis(ann) {
    var tags = (ann && ann.tags) || [];
    for (var i = 0; i < tags.length; i++) {
      if (HYPOTHESIS_TAGS.indexOf(String(tags[i]).toLowerCase()) !== -1) return true;
    }
    return false;
  }

  // ---------------------------------------------------------------------------
  // matchesSearch(ann, query): Volltextsuche ueber Tags + Notiz + Zitat.
  // Semantik uebernommen aus annotation_sidebar.js:190 (Belegtreue B6).
  // ---------------------------------------------------------------------------
  function matchesSearch(ann, query) {
    var q = String(query || '').trim().toLowerCase();
    if (!q) return true;
    if (String(ann.text || '').toLowerCase().indexOf(q) !== -1) return true;
    var tags = ann.tags || [];
    for (var i = 0; i < tags.length; i++) {
      if (String(tags[i]).toLowerCase().indexOf(q) !== -1) return true;
    }
    var selText = ann.selection && (ann.selection.text || ann.selection.textContent);
    if (selText && String(selText).toLowerCase().indexOf(q) !== -1) return true;
    return false;
  }

  // ---------------------------------------------------------------------------
  // emptyPredicate(): neutrales Filterprädikat (nichts eingeschraenkt).
  //   categories : string[]  (leer = alle)
  //   tags       : string[]  (leer = egal)
  //   tagMode    : 'or' | 'and'
  //   authors    : string[]  (leer = alle)
  //   sources    : string[]  (leer = alle)
  //   search     : string
  //   from, to   : number|null  (ms, inklusive Grenzen)
  //   hypothesisOnly : bool
  // ---------------------------------------------------------------------------
  function emptyPredicate() {
    return {
      categories: [], tags: [], tagMode: 'or', authors: [], sources: [],
      search: '', from: null, to: null, hypothesisOnly: false
    };
  }

  function inList(value, list) {
    // Leere Liste bedeutet: keine Einschraenkung.
    return !list || list.length === 0 || list.indexOf(value) !== -1;
  }

  function matchesTags(ann, tags, mode) {
    if (!tags || tags.length === 0) return true;
    var have = (ann.tags || []).map(function (t) { return String(t).toLowerCase(); });
    if (mode === 'and') {
      return tags.every(function (t) { return have.indexOf(String(t).toLowerCase()) !== -1; });
    }
    // Default ODER
    return tags.some(function (t) { return have.indexOf(String(t).toLowerCase()) !== -1; });
  }

  // ---------------------------------------------------------------------------
  // matchesPredicate(ann, pred): Kern-Prädikat. Alle Facetten sind UND-verknuepft;
  // innerhalb der Tag-Facette gilt pred.tagMode (UND/ODER).
  // ---------------------------------------------------------------------------
  function matchesPredicate(ann, pred) {
    if (!pred) return true;
    if (!inList(ann.category, pred.categories)) return false;
    if (!inList((ann.createdBy || ''), pred.authors)) return false;
    if (pred.sources && pred.sources.length && pred.sources.indexOf(deriveSource(ann)) === -1) return false;
    if (!matchesTags(ann, pred.tags, pred.tagMode)) return false;
    if (pred.hypothesisOnly && !isHypothesis(ann)) return false;
    if (!matchesSearch(ann, pred.search)) return false;
    if (pred.from != null || pred.to != null) {
      var t = annotationTimeMs(ann);
      if (t == null) return false;                 // ohne Zeit: bei Zeitfilter raus (GR1: nicht still mitzaehlen)
      if (pred.from != null && t < pred.from) return false;
      if (pred.to != null && t > pred.to) return false;
    }
    return true;
  }

  function applyFilter(annotations, pred) {
    var out = (annotations || []).filter(function (a) { return matchesPredicate(a, pred); });
    dbg('applyFilter', (annotations || []).length, '->', out.length);
    return out;
  }

  // ---------------------------------------------------------------------------
  // sortAnnotations(list, key, dir): stabil sortieren (nicht in-place).
  //   key: 'time' | 'category' | 'author' | 'identity'
  //   dir: 'asc' | 'desc'
  // 'identity' = Zahl der Identitaets-Tags (absteigend nuetzlich fuer Zuordnung).
  // ---------------------------------------------------------------------------
  function identityScore(ann) {
    var have = (ann.tags || []).map(function (t) { return String(t).toLowerCase(); });
    var n = 0;
    for (var i = 0; i < IDENTITY_TAGS.length; i++) {
      if (have.indexOf(IDENTITY_TAGS[i]) !== -1) n++;
    }
    return n;
  }

  function sortAnnotations(list, key, dir) {
    var arr = (list || []).slice();
    var sign = (dir === 'asc') ? 1 : -1;
    arr.sort(function (a, b) {
      var va, vb;
      switch (key) {
        case 'category':
          va = CATEGORY_ORDER.indexOf(a.category); vb = CATEGORY_ORDER.indexOf(b.category); break;
        case 'author':
          va = String(a.createdBy || ''); vb = String(b.createdBy || '');
          return va < vb ? -sign : (va > vb ? sign : 0);
        case 'identity':
          va = identityScore(a); vb = identityScore(b); break;
        case 'time':
        default:
          va = annotationTimeMs(a); vb = annotationTimeMs(b);
          // Annotationen ohne Zeit hinten einsortieren, egal welche Richtung.
          if (va == null && vb == null) return 0;
          if (va == null) return 1;
          if (vb == null) return -1;
          break;
      }
      return va < vb ? -sign : (va > vb ? sign : 0);
    });
    return arr;
  }

  // ---------------------------------------------------------------------------
  // computeFacets(annotations): Zaehlwerte je Facettenwert fuer die Filter-Schiene.
  // Rein aus der uebergebenen Menge (i. d. R. die UNgefilterte Gesamtmenge, damit
  // die Facetten stabil bleiben). Rueckgabe: einfache {wert: anzahl}-Maps.
  // ---------------------------------------------------------------------------
  function computeFacets(annotations) {
    var list = annotations || [];
    var categories = {}, tags = {}, authors = {}, sources = {};
    var hypotheses = 0;
    list.forEach(function (a) {
      categories[a.category] = (categories[a.category] || 0) + 1;
      (a.tags || []).forEach(function (t) {
        var k = String(t);
        tags[k] = (tags[k] || 0) + 1;
      });
      var au = a.createdBy || '—';
      authors[au] = (authors[au] || 0) + 1;
      var s = deriveSource(a);
      sources[s] = (sources[s] || 0) + 1;
      if (isHypothesis(a)) hypotheses++;
    });
    return { categories: categories, tags: tags, authors: authors, sources: sources, hypotheses: hypotheses, total: list.length };
  }

  // Oeffentliche, reine API. Kein DOM, kein Netz — voll unit-testbar.
  window.AIWAnnotationFilter = {
    CATEGORIES: CATEGORIES,
    CATEGORY_ORDER: CATEGORY_ORDER,
    TAG_VOCABULARY: TAG_VOCABULARY,
    IDENTITY_TAGS: IDENTITY_TAGS,
    HYPOTHESIS_TAGS: HYPOTHESIS_TAGS,
    SOURCES: SOURCES,
    categoryMeta: categoryMeta,
    deriveSource: deriveSource,
    annotationTimeMs: annotationTimeMs,
    isHypothesis: isHypothesis,
    identityScore: identityScore,
    matchesSearch: matchesSearch,
    emptyPredicate: emptyPredicate,
    matchesTags: matchesTags,
    matchesPredicate: matchesPredicate,
    applyFilter: applyFilter,
    sortAnnotations: sortAnnotations,
    computeFacets: computeFacets,
    _setDebug: function (v) { DEBUG = !!v; }
  };
})();
