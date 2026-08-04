// =============================================================================
// userinfo/annotation_recherche.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
// -----------------------------------------------------------------------------
// ZWECK (gesicherte Intention):
//   Orchestrierende Sicht ("RechercheView") des Nutzerinfo-Recherchewerkzeugs.
//   Baut das Drei-Zonen-Layout (Filter-Schiene · Kartenliste · Detail) in den
//   Container #userinfo-recherche, verdrahtet den zentralen AnnotationStore mit
//   den Facetten der Filter-Schiene und der Kartenliste, ermoeglicht Inline-
//   Tagging und oeffnet die Bearbeiten-Maske. Netz/Zeitstrahl/Steckbrief folgen
//   in spaeteren Wellen und haengen sich an DENSELBEN Store (Leitbild §2).
//
//   Bedienphilosophie: Ermittler:innen werten Spuren durch Tag-Vergabe auf; das
//   Werkzeug macht Tagging niederschwellig (Inline an der Karte) und die Menge
//   sofort wieder filterbar. (Bauplan §7.)
//
//   Kapselung: eine Klasse in eigener Datei (Grundregel 10), IIFE-Wrapper,
//   schaltbares DEV-Logging, ausfuehrliche Kommentare (JS-Gebote 1–4).
// =============================================================================

(function () {
  'use strict';

  var DEBUG = false;
  function dbg() {
    if (DEBUG && typeof console !== 'undefined') {
      console.log.apply(console, ['[AIW-Recherche]'].concat([].slice.call(arguments)));
    }
  }

  // ------- kleine DOM-Helfer (bewusst lokal, keine Fremdabhaengigkeit) --------
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }

  function fmtDate(ms) {
    if (ms == null) return '—';
    try { return new Date(ms).toLocaleString('de-DE'); } catch (e) { return String(ms); }
  }

  function RechercheView(store) {
    this._store = store;
    this._root = null;
    this._els = {};              // Referenzen auf dynamische Regionen
    this._selectedId = null;     // aktuell im Detail gezeigte Annotation
    this._inlineOpenFor = null;  // Karten-id, deren Inline-Tag-Feld offen ist
  }

  // mount(container): Skelett EINMAL bauen, Store abonnieren, Daten laden.
  RechercheView.prototype.mount = function (container) {
    var self = this, F = window.AIWAnnotationFilter;
    // Platzhalter ("Lade…") entfernen — h2-Ueberschrift bleibt erhalten.
    var kids = [].slice.call(container.childNodes);
    kids.forEach(function (k) { if (k.nodeType === 1 && k.tagName !== 'H2') container.removeChild(k); });
    // Benutzername (Seitenkopf) fuer das Zentrum des Tag-Netzes.
    var h1 = document.querySelector('.ui-header h1');
    this._userLabel = (h1 && h1.textContent && h1.textContent.trim()) || 'Beschuldigter';
    this._root = el('div', 'air-root');

    // ----------------------------------------------------------------- Zone L
    var rail = el('div', 'air-rail');

    // Volltextsuche (persistenter Knoten → kein Fokusverlust beim Re-Render)
    var searchWrap = el('div', 'air-rail-block');
    searchWrap.appendChild(el('div', 'air-rail-title', 'Suche'));
    var search = el('input', 'air-search');
    search.type = 'search';
    search.placeholder = 'Notiz, Tag, Zitat…';
    search.setAttribute('aria-label', 'Volltextsuche in Annotationen');
    var searchTimer = null;
    search.addEventListener('input', function () {
      if (searchTimer) clearTimeout(searchTimer);
      // 250 ms Debounce (analog B6-Sidebar), damit nicht jede Taste re-filtert.
      searchTimer = setTimeout(function () {
        self._store.setPredicate({ search: search.value });
      }, 250);
    });
    this._els.searchInput = search;
    searchWrap.appendChild(search);
    rail.appendChild(searchWrap);

    // Kategorie-Tabs (feste Menge: Alle + 6; Counts werden aktualisiert)
    var catBlock = el('div', 'air-rail-block');
    catBlock.appendChild(el('div', 'air-rail-title', 'Kategorie'));
    var tabs = el('div', 'air-tabs');
    this._els.tabs = tabs;
    catBlock.appendChild(tabs);
    rail.appendChild(catBlock);

    // Sortierung
    var sortBlock = el('div', 'air-rail-block');
    sortBlock.appendChild(el('div', 'air-rail-title', 'Sortierung'));
    var sortSel = el('select', 'air-select');
    [['time', 'Zeit'], ['category', 'Kategorie'], ['author', 'Ermittler'], ['identity', 'Identitätsrelevanz']]
      .forEach(function (p) { var o = el('option', null, p[1]); o.value = p[0]; sortSel.appendChild(o); });
    sortSel.value = this._store._sortKey;
    var dirBtn = el('button', 'air-btn air-btn-secondary air-dir', '↓ absteigend');
    sortSel.addEventListener('change', function () { self._store.setSort(sortSel.value, null); });
    dirBtn.addEventListener('click', function () {
      var next = (self._store._sortDir === 'desc') ? 'asc' : 'desc';
      dirBtn.textContent = (next === 'desc') ? '↓ absteigend' : '↑ aufsteigend';
      self._store.setSort(null, next);
    });
    sortBlock.appendChild(sortSel);
    sortBlock.appendChild(dirBtn);
    rail.appendChild(sortBlock);

    // Tag-Wolke (dynamisch) + UND/ODER-Umschalter
    var tagBlock = el('div', 'air-rail-block');
    var tagHead = el('div', 'air-rail-title', 'Tags');
    var modeBtn = el('button', 'air-mode-toggle', 'ODER');
    modeBtn.title = 'Verknüpfung der gewählten Tags umschalten (UND/ODER)';
    modeBtn.addEventListener('click', function () {
      var next = (self._store.getPredicate().tagMode === 'and') ? 'or' : 'and';
      self._store.setPredicate({ tagMode: next });
    });
    this._els.modeBtn = modeBtn;
    tagHead.appendChild(modeBtn);
    tagBlock.appendChild(tagHead);
    var tagCloud = el('div', 'air-tagcloud');
    this._els.tagCloud = tagCloud;
    tagBlock.appendChild(tagCloud);
    rail.appendChild(tagBlock);

    // Ermittler-Facette (dynamisch)
    var authorBlock = el('div', 'air-rail-block');
    authorBlock.appendChild(el('div', 'air-rail-title', 'Ermittler'));
    var authorList = el('div', 'air-facet-list');
    this._els.authorList = authorList;
    authorBlock.appendChild(authorList);
    rail.appendChild(authorBlock);

    // Quellen-Facette (dynamisch)
    var sourceBlock = el('div', 'air-rail-block');
    sourceBlock.appendChild(el('div', 'air-rail-title', 'Quelle'));
    var sourceList = el('div', 'air-facet-list');
    this._els.sourceList = sourceList;
    sourceBlock.appendChild(sourceList);
    rail.appendChild(sourceBlock);

    // Zuordnungs-Facette (Cross-Annotation, Build 431): eigene vs. Fremd-UID.
    var crossBlock = el('div', 'air-rail-block');
    crossBlock.appendChild(el('div', 'air-rail-title', 'Zuordnung'));
    var crossList = el('div', 'air-facet-list');
    this._els.crossList = crossList;
    crossBlock.appendChild(crossList);
    rail.appendChild(crossBlock);

    // Zeitraum (auf annotationTimeMs; ab Welle 3 automatisch Inhaltszeit)
    var timeBlock = el('div', 'air-rail-block');
    timeBlock.appendChild(el('div', 'air-rail-title', 'Zeitraum'));
    var fromInp = el('input', 'air-date'); fromInp.type = 'date'; fromInp.setAttribute('aria-label', 'von');
    var toInp = el('input', 'air-date'); toInp.type = 'date'; toInp.setAttribute('aria-label', 'bis');
    function applyRange() {
      var from = fromInp.value ? new Date(fromInp.value + 'T00:00:00').getTime() : null;
      var to = toInp.value ? new Date(toInp.value + 'T23:59:59').getTime() : null;
      self._store.setPredicate({ from: from, to: to });
    }
    fromInp.addEventListener('change', applyRange);
    toInp.addEventListener('change', applyRange);

    // BUILD 663 (Ticket d3f933cd): Von/Bis koppeln -- NUR die untere Schranke,
    // KEINE Uebernahme des Von-Datums.
    //
    // Diese Schiene ist ein FILTER, kein Eingabeformular. Ein leeres Bis-Feld
    // heisst hier "ohne obere Grenze" (applyRange setzt to=null). Springt es
    // beim Setzen des Von-Datums stillschweigend auf denselben Tag, verschwinden
    // alle spaeteren Annotationen aus der Trefferliste, ohne dass jemand danach
    // gefragt haette -- eine stille Auslassung (Grundregel 1) mitten in der
    // Recherche. Die Schranke dagegen verhindert nur einen sinnlosen Zustand.
    var _dp = (typeof window !== 'undefined') ? window.AIWDatumspaar : null;
    if (_dp && typeof _dp.koppeln === 'function') {
      _dp.koppeln(fromInp, toInp, { uebernehmen: false, min: true });
    } else if (typeof console !== 'undefined') {
      console.warn('[AIR] cockpit_datumspaar.js nicht geladen - '
                   + 'Zeitraum-Felder bleiben ungekoppelt.');
    }
    timeBlock.appendChild(fromInp);
    timeBlock.appendChild(el('span', 'air-date-sep', '–'));
    timeBlock.appendChild(toInp);
    rail.appendChild(timeBlock);

    // Vermutungs-Filter (Trennung Vermutung/Beleg, GR1) + Zuruecksetzen
    var miscBlock = el('div', 'air-rail-block');
    var hypLabel = el('label', 'air-check');
    var hypBox = el('input'); hypBox.type = 'checkbox';
    hypBox.addEventListener('change', function () { self._store.setPredicate({ hypothesisOnly: hypBox.checked }); });
    hypLabel.appendChild(hypBox);
    hypLabel.appendChild(el('span', null, ' nur Vermutungen'));
    miscBlock.appendChild(hypLabel);
    var resetBtn = el('button', 'air-btn air-btn-secondary air-reset', '⟲ Filter zurücksetzen');
    resetBtn.addEventListener('click', function () {
      search.value = ''; fromInp.value = ''; toInp.value = ''; hypBox.checked = false;
      self._store.resetPredicate();
    });
    miscBlock.appendChild(resetBtn);
    rail.appendChild(miscBlock);

    // ----------------------------------------------------------------- Zone M
    var center = el('div', 'air-center');

    // Center-Umschalter Liste | Zeitstrahl (Build 430). Beide Sichten arbeiten
    // ueber derselben gefilterten Menge; nur die sichtbare wird aktualisiert.
    var cseg = el('div', 'air-seg air-center-seg');
    var segList = el('button', 'air-seg-btn air-seg-active', 'Liste');
    var segTime = el('button', 'air-seg-btn', 'Zeitstrahl');
    var segNet = el('button', 'air-seg-btn', 'Netz');
    cseg.appendChild(segList); cseg.appendChild(segTime); cseg.appendChild(segNet);
    center.appendChild(cseg);
    this._els.segList = segList; this._els.segTime = segTime; this._els.segNet = segNet;
    segList.addEventListener('click', function () { self._setCenterMode('list'); });
    segTime.addEventListener('click', function () { self._setCenterMode('timeline'); });
    segNet.addEventListener('click', function () { self._setCenterMode('network'); });

    var status = el('div', 'air-status');
    this._els.status = status;
    center.appendChild(status);

    var list = el('div', 'air-list');
    this._els.list = list;
    center.appendChild(list);

    // Zeitstrahl-Bereich (anfangs verborgen): Achsen-Umschalter, Chart-Host,
    // "ohne Inhaltszeit"-Zeile.
    var tlWrap = el('div', 'air-timeline-wrap');
    tlWrap.style.display = 'none';
    var tlBar = el('div', 'air-timeline-bar');
    tlBar.appendChild(el('span', 'air-tl-basis-label', 'Achse:'));
    var basisContent = el('button', 'air-seg-btn air-seg-active', 'Inhaltszeit');
    var basisAnn = el('button', 'air-seg-btn', 'Annotationszeit');
    tlBar.appendChild(basisContent); tlBar.appendChild(basisAnn);
    this._els.basisContent = basisContent; this._els.basisAnn = basisAnn;
    basisContent.addEventListener('click', function () { self._setBasis('content'); });
    basisAnn.addEventListener('click', function () { self._setBasis('annotation'); });
    tlWrap.appendChild(tlBar);
    var tlHost = el('div', 'air-timeline-host');
    this._els.tlHost = tlHost;
    tlWrap.appendChild(tlHost);
    var tlNote = el('div', 'air-timeline-note');
    this._els.tlNote = tlNote;
    tlWrap.appendChild(tlNote);
    this._els.tlWrap = tlWrap;
    center.appendChild(tlWrap);

    // Tag-Netz-Bereich (anfangs verborgen): Chart-Host + Hinweiszeile.
    var netWrap = el('div', 'air-network-wrap');
    netWrap.style.display = 'none';
    var netHost = el('div', 'air-network-host');
    this._els.netHost = netHost;
    netWrap.appendChild(netHost);
    var netNote = el('div', 'air-network-note');
    this._els.netNote = netNote;
    netWrap.appendChild(netNote);
    this._els.netWrap = netWrap;
    center.appendChild(netWrap);

    this._centerMode = 'list';       // 'list' | 'timeline' | 'network'

    // ----------------------------------------------------------------- Zone R
    // Zwei umschaltbare Panels: Identitaets-Steckbrief (Synthese der gefilterten
    // Menge, Standard) und Detail (ausgewaehlte Annotation). Build 429.
    var side = el('div', 'air-side');
    var seg = el('div', 'air-seg');
    var segProfile = el('button', 'air-seg-btn air-seg-active', 'Steckbrief');
    var segDetail = el('button', 'air-seg-btn', 'Detail');
    seg.appendChild(segProfile); seg.appendChild(segDetail);
    side.appendChild(seg);
    this._els.segProfile = segProfile;
    this._els.segDetail = segDetail;
    segProfile.addEventListener('click', function () { self._setSideMode('profile'); });
    segDetail.addEventListener('click', function () { self._setSideMode('detail'); });

    // Host: Identitaets-Steckbrief
    var profileHost = el('div', 'air-profile');
    this._els.profileHost = profileHost;
    side.appendChild(profileHost);
    this._profile = new window.AIWIdentityProfile.IdentityProfileView();

    // Host: Detail (anfangs verborgen)
    var detail = el('div', 'air-detail');
    detail.style.display = 'none';
    detail.appendChild(el('div', 'air-detail-empty', 'Eine Annotation auswählen, um Details zu sehen.'));
    this._els.detail = detail;
    side.appendChild(detail);

    this._sideMode = 'profile';   // 'profile' | 'detail'

    // Hinweis auf noch kommende Sichten (Ehrlichkeit ueber den Ausbaustand).
    var soon = el('div', 'air-side-soon', 'Tag-Netz und Zeitstrahl folgen in weiteren Ausbaustufen.');
    side.appendChild(soon);

    this._root.appendChild(rail);
    this._root.appendChild(center);
    this._root.appendChild(side);
    container.appendChild(this._root);

    // Store abonnieren und laden
    this._store.subscribe(function (view) { self._update(view); });
    this._store.load().catch(function () { /* Fehler wird in _update angezeigt */ });
    dbg('gemountet');
  };

  // _update(view): dynamische Regionen aktualisieren (Skelett bleibt bestehen).
  RechercheView.prototype._update = function (view) {
    this._renderTabs(view);
    this._renderTagCloud(view);
    this._renderFacet(this._els.authorList, view.facets.authors, view.predicate.authors, 'authors', null);
    this._renderSources(view);
    this._renderCross(view);
    this._renderStatus(view);
    this._renderList(view);
    this._els.modeBtn.textContent = (view.predicate.tagMode === 'and') ? 'UND' : 'ODER';
    this._els.modeBtn.classList.toggle('air-mode-and', view.predicate.tagMode === 'and');
    // Steckbrief spiegelt die aktuell gefilterte Menge (verknuepfte Sichten §2).
    this._lastView = view;
    if (this._sideMode === 'profile') this._renderProfile(view);
    if (this._centerMode === 'timeline') this._renderTimeline(view);
    if (this._centerMode === 'network') this._renderNetwork(view);
  };

  // ------- Center-Umschaltung (Liste/Zeitstrahl/Netz, Build 430/431) ----------
  RechercheView.prototype._setCenterMode = function (m) {
    this._centerMode = m;
    this._els.list.style.display = (m === 'list') ? '' : 'none';
    this._els.tlWrap.style.display = (m === 'timeline') ? '' : 'none';
    this._els.netWrap.style.display = (m === 'network') ? '' : 'none';
    this._els.segList.classList.toggle('air-seg-active', m === 'list');
    this._els.segTime.classList.toggle('air-seg-active', m === 'timeline');
    this._els.segNet.classList.toggle('air-seg-active', m === 'network');
    if (m === 'timeline' && this._lastView) this._renderTimeline(this._lastView);
    if (m === 'network' && this._lastView) this._renderNetwork(this._lastView);
  };

  // ------- Tag-Netz (Build 431) ----------------------------------------------
  RechercheView.prototype._renderNetwork = function (view) {
    var self = this;
    if (!window.AIWAnnotationTagNetwork) return;
    if (!this._network) {
      this._network = new window.AIWAnnotationTagNetwork.TagNetworkView();
      this._network.mount(this._els.netHost, {
        // Klick auf Tag-Knoten: Tag im Prädikat umschalten (wie Chip-Wolke).
        onToggleTag: function (tag) {
          var cur = self._store.getPredicate().tags.slice();
          var i = cur.map(function (t) { return t.toLowerCase(); }).indexOf(String(tag).toLowerCase());
          if (i === -1) cur.push(tag); else cur.splice(i, 1);
          self._store.setPredicate({ tags: cur });
        },
        // Klick auf Kategorie-Knoten: exklusiv filtern.
        onSetCategory: function (catId) { self._store.setPredicate({ categories: [catId] }); },
        // Klick auf Ko-Okkurrenz-Kante: auf beide Tags (UND) filtern.
        onSetPair: function (a, b) { self._store.setPredicate({ tags: [a, b], tagMode: 'and' }); },
        // Klick auf das Zentrum: Filter zuruecksetzen.
        onReset: function () { self._resetFromControls(); }
      });
      window.addEventListener('resize', function () { if (self._network) self._network.resize(); });
    }
    if (!this._network.available()) {
      this._els.netHost.innerHTML = '';
      this._els.netNote.textContent = 'Tag-Netz nicht verfügbar (Diagramm-Bibliothek nicht geladen). '
        + 'Die übrigen Sichten sind uneingeschränkt nutzbar.';
      return;
    }
    var res = this._network.render(view.filtered, { userLabel: this._userLabel || 'Beschuldigter' });
    var note = res.tagCount + ' Tags · ' + res.cooccurrenceEdges + ' Ko-Okkurrenz-Kanten';
    if (res.isolatedTags && res.isolatedTags.length) {
      note += ' · isoliert (nur an Kategorie/Zentrum): ' + res.isolatedTags.join(', ');
    }
    this._els.netNote.textContent = note;
  };

  // Filter zuruecksetzen inkl. Bedienelemente (vom Zentrum-Klick genutzt).
  RechercheView.prototype._resetFromControls = function () {
    if (this._els.searchInput) this._els.searchInput.value = '';
    this._store.resetPredicate();
  };

  RechercheView.prototype._setBasis = function (basis) {
    if (!this._timeline) return;
    this._timeline.setBasis(basis);
    this._els.basisContent.classList.toggle('air-seg-active', basis === 'content');
    this._els.basisAnn.classList.toggle('air-seg-active', basis === 'annotation');
    if (this._lastView) this._renderTimeline(this._lastView);
  };

  RechercheView.prototype._renderTimeline = function (view) {
    var self = this;
    if (!window.AIWAnnotationTimeline) return;
    if (!this._timeline) {
      this._timeline = new window.AIWAnnotationTimeline.AnnotationTimeline();
      this._timeline.mount(this._els.tlHost, {
        basis: 'content',
        onSelect: function (annId) {
          var ann = self._store.getById(annId);
          if (ann) self._select(ann);
        },
        // Gezogenes Zeitfenster -> gemeinsames Filterprädikat (alle Sichten).
        onBrush: function (fromMs, toMs) { self._store.setPredicate({ from: fromMs, to: toMs }); }
      });
      // Chart auf Fenstergroesse reagieren lassen.
      window.addEventListener('resize', function () { if (self._timeline) self._timeline.resize(); });
    }
    if (!this._timeline.available()) {
      this._els.tlHost.innerHTML = '';
      this._els.tlNote.textContent = 'Zeitstrahl nicht verfügbar (Diagramm-Bibliothek nicht geladen). '
        + 'Die übrigen Sichten sind uneingeschränkt nutzbar.';
      return;
    }
    var res = this._timeline.render(view.filtered);
    var basis = this._timeline.getBasis();
    var note = '';
    if (basis === 'content' && res.withoutTime > 0) {
      note = res.withoutTime + ' Annotation(en) ohne Inhaltszeit — nicht auf der Achse. '
        + 'Über „Annotationszeit" sichtbar.';
    }
    this._els.tlNote.textContent = note;
  };

  // _renderProfile(view): Identitaets-Steckbrief aus der gefilterten Menge bauen.
  RechercheView.prototype._renderProfile = function (view) {
    var self = this;
    this._profile.render(this._els.profileHost, view.filtered, {
      onFocus: function (annId) { self._focusCard(annId); }
    });
  };

  // _setSideMode(m): rechte Zone zwischen Steckbrief und Detail umschalten.
  RechercheView.prototype._setSideMode = function (m) {
    this._sideMode = m;
    var isProfile = (m === 'profile');
    this._els.profileHost.style.display = isProfile ? '' : 'none';
    this._els.detail.style.display = isProfile ? 'none' : '';
    this._els.segProfile.classList.toggle('air-seg-active', isProfile);
    this._els.segDetail.classList.toggle('air-seg-active', !isProfile);
    if (isProfile && this._lastView) this._renderProfile(this._lastView);
  };

  // _focusCard(annId): Karte in der Liste hervorheben und ins Sichtfeld holen
  // (Rueckverlinkung aus dem Steckbrief, ohne den Steckbrief zu verlassen).
  RechercheView.prototype._focusCard = function (annId) {
    var card = this._els.list.querySelector('.air-card[data-ann-id="' + annId + '"]');
    if (!card) return;
    try { card.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) { card.scrollIntoView(); }
    card.classList.add('air-card-flash');
    setTimeout(function () { card.classList.remove('air-card-flash'); }, 1200);
  };

  RechercheView.prototype._renderTabs = function (view) {
    var self = this, F = window.AIWAnnotationFilter, tabs = this._els.tabs;
    clear(tabs);
    var active = view.predicate.categories;
    // "Alle"
    tabs.appendChild(this._tab('Alle', '∑', view.total, active.length === 0, function () {
      self._store.setPredicate({ categories: [] });
    }));
    F.CATEGORIES.forEach(function (c) {
      var count = view.facets.categories[c.id] || 0;
      var isActive = active.length === 1 && active[0] === c.id;
      var t = self._tab(c.label, c.icon, count, isActive, function () {
        // Ein-Klick-Kategorie: exklusiv setzen; erneuter Klick → Alle.
        self._store.setPredicate({ categories: isActive ? [] : [c.id] });
      });
      t.style.borderColor = c.color;
      if (count === 0) t.classList.add('air-tab-empty');
      tabs.appendChild(t);
    });
  };

  RechercheView.prototype._tab = function (label, icon, count, active, onClick) {
    var t = el('button', 'air-tab' + (active ? ' air-tab-active' : ''));
    t.appendChild(el('span', 'air-tab-icon', icon));
    t.appendChild(el('span', 'air-tab-label', label));
    t.appendChild(el('span', 'air-tab-count', String(count)));
    t.addEventListener('click', onClick);
    return t;
  };

  RechercheView.prototype._renderTagCloud = function (view) {
    var self = this, cloud = this._els.tagCloud;
    clear(cloud);
    var selected = view.predicate.tags.map(function (t) { return String(t).toLowerCase(); });
    var entries = Object.keys(view.facets.tags).map(function (k) {
      return { tag: k, n: view.facets.tags[k] };
    }).sort(function (a, b) { return b.n - a.n || (a.tag < b.tag ? -1 : 1); });
    if (entries.length === 0) { cloud.appendChild(el('span', 'air-muted', 'keine Tags')); return; }
    entries.forEach(function (e) {
      var on = selected.indexOf(e.tag.toLowerCase()) !== -1;
      var chip = el('button', 'air-chip' + (on ? ' air-chip-on' : ''));
      chip.appendChild(el('span', 'air-chip-label', e.tag));
      chip.appendChild(el('span', 'air-chip-count', String(e.n)));
      chip.addEventListener('click', function () {
        var cur = self._store.getPredicate().tags.slice();
        var i = cur.map(function (t) { return t.toLowerCase(); }).indexOf(e.tag.toLowerCase());
        if (i === -1) cur.push(e.tag); else cur.splice(i, 1);
        self._store.setPredicate({ tags: cur });
      });
      cloud.appendChild(chip);
    });
  };

  // Generische Facettenliste (Ermittler). Mehrfachauswahl (ODER innerhalb Facette).
  RechercheView.prototype._renderFacet = function (container, counts, selectedList, field) {
    var self = this;
    clear(container);
    var keys = Object.keys(counts).sort(function (a, b) { return counts[b] - counts[a] || (a < b ? -1 : 1); });
    if (keys.length === 0) { container.appendChild(el('span', 'air-muted', '—')); return; }
    keys.forEach(function (k) {
      var on = selectedList.indexOf(k) !== -1;
      var row = el('label', 'air-facet-row' + (on ? ' air-facet-on' : ''));
      var box = el('input'); box.type = 'checkbox'; box.checked = on;
      box.addEventListener('change', function () {
        var cur = self._store.getPredicate()[field].slice();
        var i = cur.indexOf(k);
        if (box.checked && i === -1) cur.push(k);
        else if (!box.checked && i !== -1) cur.splice(i, 1);
        var patch = {}; patch[field] = cur; self._store.setPredicate(patch);
      });
      row.appendChild(box);
      row.appendChild(el('span', 'air-facet-name', k));
      row.appendChild(el('span', 'air-facet-count', String(counts[k])));
      container.appendChild(row);
    });
  };

  RechercheView.prototype._renderSources = function (view) {
    var self = this, F = window.AIWAnnotationFilter, container = this._els.sourceList;
    clear(container);
    var selected = view.predicate.sources;
    F.SOURCES.forEach(function (s) {
      var n = view.facets.sources[s.id] || 0;
      if (n === 0 && selected.indexOf(s.id) === -1) return; // leere Quelle ausblenden
      var on = selected.indexOf(s.id) !== -1;
      var row = el('label', 'air-facet-row' + (on ? ' air-facet-on' : ''));
      var box = el('input'); box.type = 'checkbox'; box.checked = on;
      box.addEventListener('change', function () {
        var cur = self._store.getPredicate().sources.slice();
        var i = cur.indexOf(s.id);
        if (box.checked && i === -1) cur.push(s.id);
        else if (!box.checked && i !== -1) cur.splice(i, 1);
        self._store.setPredicate({ sources: cur });
      });
      row.appendChild(box);
      row.appendChild(el('span', 'air-facet-name', s.icon + ' ' + s.label));
      row.appendChild(el('span', 'air-facet-count', String(n)));
      container.appendChild(row);
    });
  };

  // Zuordnungs-Facette (Cross-Annotation): 'eigene' vs. Fremd-UID (Build 431).
  RechercheView.prototype._renderCross = function (view) {
    var self = this, container = this._els.crossList;
    clear(container);
    var counts = view.facets.cross || {};
    var selected = view.predicate.cross;
    var keys = Object.keys(counts).sort(function (a, b) {
      // 'eigene' immer zuerst, dann nach Anzahl.
      if (a === 'eigene') return -1; if (b === 'eigene') return 1;
      return counts[b] - counts[a] || (a < b ? -1 : 1);
    });
    if (keys.length === 0) { container.appendChild(el('span', 'air-muted', '—')); return; }
    keys.forEach(function (k) {
      var on = selected.indexOf(k) !== -1;
      var row = el('label', 'air-facet-row' + (on ? ' air-facet-on' : ''));
      var box = el('input'); box.type = 'checkbox'; box.checked = on;
      box.addEventListener('change', function () {
        var cur = self._store.getPredicate().cross.slice();
        var i = cur.indexOf(k);
        if (box.checked && i === -1) cur.push(k);
        else if (!box.checked && i !== -1) cur.splice(i, 1);
        self._store.setPredicate({ cross: cur });
      });
      row.appendChild(box);
      var label = (k === 'eigene') ? '👤 eigene (Job-Benutzer)' : '↪ Fremd-UID ' + k;
      row.appendChild(el('span', 'air-facet-name', label));
      row.appendChild(el('span', 'air-facet-count', String(counts[k])));
      container.appendChild(row);
    });
  };

  RechercheView.prototype._renderStatus = function (view) {
    var s = this._els.status;
    clear(s);
    if (view.error) {
      s.appendChild(el('span', 'air-status-err', '⚠ Annotationen konnten nicht geladen werden.'));
      return;
    }
    if (!view.loaded) { s.appendChild(el('span', null, 'Lade…')); return; }
    s.appendChild(el('span', 'air-status-count', view.shown + ' von ' + view.total + ' Annotationen'));
  };

  // ------- Kartenliste (Optik an B6 as-Karte angelehnt) -----------------------
  RechercheView.prototype._renderList = function (view) {
    var self = this, F = window.AIWAnnotationFilter, list = this._els.list;
    clear(list);
    if (view.loaded && !view.error && view.shown === 0) {
      list.appendChild(el('div', 'air-empty', view.total === 0
        ? 'Für diesen Benutzer sind noch keine Annotationen gesichert.'
        : 'Keine Annotation entspricht dem aktuellen Filter.'));
      return;
    }
    view.filtered.forEach(function (ann) { list.appendChild(self._card(ann)); });
  };

  RechercheView.prototype._card = function (ann) {
    var self = this, F = window.AIWAnnotationFilter;
    var meta = F.categoryMeta(ann.category);
    var card = el('div', 'air-card');
    card.setAttribute('data-ann-id', ann.id);
    if (F.isHypothesis(ann)) card.classList.add('air-card-hyp'); // Vermutung optisch abgesetzt
    if (String(ann.id) === String(this._selectedId)) card.classList.add('air-card-sel');
    card.style.borderLeftColor = meta.color;

    // Kopf: Kategorie-Chip + Zeit
    var top = el('div', 'air-card-top');
    var catChip = el('span', 'air-cat-chip');
    catChip.style.background = meta.color;
    catChip.textContent = meta.icon + ' ' + meta.label;
    top.appendChild(catChip);
    top.appendChild(el('span', 'air-card-time', fmtDate(F.annotationTimeMs(ann))));
    card.appendChild(top);

    // Tags
    if (ann.tags && ann.tags.length) {
      var tagRow = el('div', 'air-card-tags');
      ann.tags.forEach(function (t) { tagRow.appendChild(el('span', 'air-tag', t)); });
      card.appendChild(tagRow);
    }

    // Notiz
    if (ann.text) card.appendChild(el('div', 'air-card-note', ann.text));

    // Zitat (markierter Text)
    var selText = ann.selection && (ann.selection.text || ann.selection.textContent);
    if (selText) card.appendChild(el('div', 'air-card-quote', '„' + selText + '“'));

    // Meta-Zeile
    var metaRow = el('div', 'air-card-meta');
    metaRow.appendChild(el('span', 'air-card-id', 'ID ' + ann.id));
    if (ann.createdBy) metaRow.appendChild(el('span', 'air-card-inv', '👤 ' + ann.createdBy));
    card.appendChild(metaRow);

    // Aktionen
    var actions = el('div', 'air-card-actions');
    var openBtn = el('button', 'air-btn air-btn-small', '🔗 In Forenansicht');
    openBtn.addEventListener('click', function (ev) { ev.stopPropagation(); self._jump(ann); });
    actions.appendChild(openBtn);

    if (this._store.canEdit(ann)) {
      var editBtn = el('button', 'air-btn air-btn-small', '✎ Bearbeiten');
      editBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var dlg = new window.AIWAnnotationEditDialog(self._store);
        dlg.open(ann, function () { dbg('gespeichert, Reload folgt via Store'); });
      });
      actions.appendChild(editBtn);

      var tagBtn = el('button', 'air-btn air-btn-small', '+ Tag');
      tagBtn.addEventListener('click', function (ev) { ev.stopPropagation(); self._toggleInlineTag(card, ann); });
      actions.appendChild(tagBtn);

      // Vermutungs-Workflow (Build 429): einen Klick, um die Annotation als
      // Vermutung zu markieren bzw. die Markierung aufzuheben. Trennung
      // Vermutung/Beleg ist Pflicht (GR1); der reservierte Tag 'vermutung'
      // steuert Optik (gestrichelt) und Steckbrief-Einordnung.
      var isHyp = F.isHypothesis(ann);
      var hypBtn = el('button', 'air-btn air-btn-small air-btn-hyp' + (isHyp ? ' air-btn-hyp-on' : ''),
        isHyp ? '⚑ Vermutung aufheben' : '⚑ als Vermutung');
      hypBtn.addEventListener('click', function (ev) {
        ev.stopPropagation();
        hypBtn.disabled = true;
        var p = isHyp ? self._store.removeTag(ann, 'vermutung') : self._store.addTags(ann, ['vermutung']);
        p.catch(function (err) {
          hypBtn.disabled = false;
          if (typeof console !== 'undefined') console.error('[AIW-Recherche] Vermutung-Toggle fehlgeschlagen:', err);
        });
      });
      actions.appendChild(hypBtn);
    } else {
      // GR1: kein stiller Ausfall — sichtbarer Hinweis, warum nicht editierbar.
      var lock = el('span', 'air-card-lock', '🔒 nicht editierbar (fehlende local_id)');
      actions.appendChild(lock);
    }
    card.appendChild(actions);

    // Karte klickbar → Detail rechts
    card.addEventListener('click', function () { self._select(ann); });
    return card;
  };

  // Inline-Tag-Eingabe direkt an der Karte (niederschwelliges Tagging).
  RechercheView.prototype._toggleInlineTag = function (card, ann) {
    var self = this, F = window.AIWAnnotationFilter;
    var existing = card.querySelector('.air-inline-tag');
    if (existing) { existing.parentNode.removeChild(existing); return; }
    var wrap = el('div', 'air-inline-tag');
    var inp = el('input', 'air-input'); inp.type = 'text';
    inp.placeholder = 'Tag hinzufügen und Enter';
    inp.setAttribute('list', 'air-inline-tagvocab');
    wrap.appendChild(inp);
    // gemeinsame Vorschlagsliste einmalig anlegen
    if (!document.getElementById('air-inline-tagvocab')) {
      var dl = el('datalist'); dl.id = 'air-inline-tagvocab';
      F.TAG_VOCABULARY.forEach(function (t) { var o = el('option'); o.value = t; dl.appendChild(o); });
      document.body.appendChild(dl);
    }
    inp.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') {
        var v = inp.value.trim();
        if (!v) return;
        inp.disabled = true;
        self._store.addTags(ann, [v]).catch(function (err) {
          inp.disabled = false;
          wrap.appendChild(el('div', 'air-modal-error', 'Fehler: ' + (err && err.message ? err.message : err)));
        });
      } else if (ev.key === 'Escape') {
        wrap.parentNode.removeChild(wrap);
      }
      ev.stopPropagation();
    });
    card.appendChild(wrap);
    setTimeout(function () { try { inp.focus(); } catch (e) {} }, 0);
  };

  // _jump(ann): im Hauptfenster (Opener) zur Quellseite navigieren.
  // Nutzt die bestehende postMessage-Bruecke (Beleg userinfo.js:185).
  RechercheView.prototype._jump = function (ann) {
    var target = window.opener || window.parent;
    if (!target || target === window) {
      dbg('kein Opener — Fallback: neues Fenster');
      if (ann.pageUrl) window.open(ann.pageUrl + (ann.elementId ? '#' + ann.elementId : ''), '_blank');
      return;
    }
    // Wir senden BEIDES: die Annotation-Navigation (falls das Hauptfenster darauf
    // hoert) und – als robuster Weg – die URL-Navigation.
    try {
      target.postMessage({ type: 'navigate_to_annotation', annotation_id: ann.id }, '*');
      if (ann.pageUrl) target.postMessage({ type: 'navigate_to_url', url: ann.pageUrl, fragment: ann.elementId || null }, '*');
    } catch (e) {
      if (typeof console !== 'undefined') console.error('[AIW-Recherche] Jump fehlgeschlagen:', e);
    }
  };

  RechercheView.prototype._select = function (ann) {
    this._selectedId = ann.id;
    // Auswahl-Markierung aktualisieren, ohne komplette Liste neu zu bauen
    var cards = this._els.list.querySelectorAll('.air-card');
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.toggle('air-card-sel', cards[i].getAttribute('data-ann-id') === String(ann.id));
    }
    this._renderDetail(ann);
    // Karten-Klick zeigt die Detailsicht (rechte Zone auf 'detail' schalten).
    this._setSideMode('detail');
  };

  RechercheView.prototype._renderDetail = function (ann) {
    var self = this, F = window.AIWAnnotationFilter, d = this._els.detail;
    clear(d);
    var meta = F.categoryMeta(ann.category);
    var h = el('div', 'air-detail-cat');
    h.style.color = meta.color;
    h.textContent = meta.icon + ' ' + meta.label + ' — ' + meta.desc;
    d.appendChild(h);

    if (F.isHypothesis(ann)) d.appendChild(el('div', 'air-detail-hyp', '⚠ Vermutung – nicht als gesicherter Beleg zu werten.'));

    if (ann.tags && ann.tags.length) {
      var tr = el('div', 'air-card-tags');
      ann.tags.forEach(function (t) { tr.appendChild(el('span', 'air-tag', t)); });
      d.appendChild(tr);
    }
    if (ann.text) d.appendChild(el('div', 'air-detail-note', ann.text));
    var selText = ann.selection && (ann.selection.text || ann.selection.textContent);
    if (selText) d.appendChild(el('div', 'air-card-quote', '„' + selText + '“'));

    var dl = el('div', 'air-detail-fields');
    function row(k, v) { var r = el('div', 'air-detail-row'); r.appendChild(el('span', 'air-detail-k', k)); r.appendChild(el('span', 'air-detail-v', v)); dl.appendChild(r); }
    row('ID', String(ann.id) + (ann.versionNr ? ' (v' + ann.versionNr + ')' : ''));
    row('Ermittler', ann.createdBy || '—');
    row('Zeit', fmtDate(F.annotationTimeMs(ann)));
    row('Quelle', (function () { var s = F.deriveSource(ann); var m = F.SOURCES.filter(function (x) { return x.id === s; })[0]; return m ? (m.icon + ' ' + m.label) : s; })());
    if (ann.postId != null) row('post_id', String(ann.postId));
    if (ann.actualUid != null) row('Fremd-UID', String(ann.actualUid));
    d.appendChild(dl);

    if (ann.pageUrl) {
      var a = el('a', 'air-detail-link', '🔗 Quellseite öffnen');
      a.href = ann.pageUrl + (ann.elementId ? '#' + ann.elementId : '');
      a.target = '_blank';
      a.addEventListener('click', function (ev) { ev.preventDefault(); self._jump(ann); });
      d.appendChild(a);
    }
  };

  // Oeffentliche Fassade + Selbst-Init im Nutzerinfo-Fenster.
  window.AIWUserinfoRecherche = {
    RechercheView: RechercheView,
    _setDebug: function (v) { DEBUG = !!v; },
    // init(): haengt die Recherche in #userinfo-recherche, sofern vorhanden.
    init: function () {
      var container = document.getElementById('userinfo-recherche');
      if (!container) { dbg('kein #userinfo-recherche — Init uebersprungen'); return; }
      if (!window.AIWAnnotationStore || !window.AIWAnnotationFilter) {
        if (typeof console !== 'undefined') console.error('[AIW-Recherche] Abhaengigkeiten fehlen (Store/Filter).');
        return;
      }
      var store = new window.AIWAnnotationStore();
      var view = new RechercheView(store);
      view.mount(container);
      // SSE-Refresh: wenn im Hauptfenster eine Annotation ergaenzt wurde, neu laden.
      window.addEventListener('message', function (ev) {
        if (ev && ev.data && ev.data.type === 'annotation_added') { store.reload(); }
      });
      window.AIWUserinfoRecherche._instance = { store: store, view: view };
    }
  };

  // Selbst-Init nach DOM-Ready (Muster analog userinfo.js:1059).
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { window.AIWUserinfoRecherche.init(); });
  } else {
    window.AIWUserinfoRecherche.init();
  }
})();
