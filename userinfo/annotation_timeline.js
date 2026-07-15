// =============================================================================
// userinfo/annotation_timeline.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
// -----------------------------------------------------------------------------
// ZWECK (gesicherte Intention):
//   Zeitstrahl der Annotationen (ECharts). Primärachse = INHALTSZEIT (wann der
//   Post/die PN im Forum entstand — die eigentliche Spur/Einlassung), farb-
//   codiert nach Kategorie; umschaltbar auf die ANNOTATIONSZEIT (Arbeits-
//   fortschritt). Punkte sind klickbar (Auswahl/Detail), ein gezogenes
//   Zeitfenster (Brush) setzt das gemeinsame Filterprädikat {from,to} und
//   filtert damit ALLE Sichten (verknüpfte Sichten §2).
//
//   FORENSISCHE INTEGRITAET (GR1): Annotationen ohne aufloesbare Inhaltszeit
//   werden NICHT still verschluckt, sondern sichtbar als "N ohne Inhaltszeit"
//   ausgewiesen (und sind ueber die Annotationszeit-Ansicht erreichbar).
//
//   Aufbau: reiner, testbarer Option-Builder buildTimelineOption() (kein DOM/
//   Netz, keine ECharts-Abhaengigkeit) + Klasse AnnotationTimeline (rendert und
//   verdrahtet ECharts). Faellt ECharts aus, bleibt die Recherche bedienbar;
//   der Zeitstrahl zeigt dann einen erklaerenden Hinweis (Bauplan §14).
// =============================================================================

(function () {
  'use strict';

  var DEBUG = false;
  function dbg() {
    if (DEBUG && typeof console !== 'undefined') {
      console.log.apply(console, ['[AIW-Zeitstrahl]'].concat([].slice.call(arguments)));
    }
  }

  // timeForBasis(ann, basis): Zeitwert (ms) fuer die gewaehlte Achse.
  //   'content'    -> NUR Inhaltszeit (contentTs, Sekunden -> ms); sonst null.
  //   'annotation' -> Annotationszeit (createdAt, bereits ms); sonst null.
  // Bewusst NICHT annotationTimeMs(): dort ist 'content bevorzugt, sonst
  // annotation' verschmolzen — hier brauchen wir die strikte Trennung.
  function timeForBasis(ann, basis) {
    if (basis === 'annotation') {
      return (ann && ann.createdAt != null && !isNaN(ann.createdAt)) ? Number(ann.createdAt) : null;
    }
    // Default: Inhaltszeit
    return (ann && ann.contentTs != null && !isNaN(ann.contentTs)) ? Number(ann.contentTs) * 1000 : null;
  }

  function shortText(ann) {
    var sel = ann.selection && (ann.selection.text || ann.selection.textContent);
    var s = (sel && String(sel)) || (ann.text && String(ann.text)) || '';
    s = s.replace(/\s+/g, ' ').trim();
    return s.length > 80 ? s.slice(0, 80) + '…' : s;
  }

  // ---------------------------------------------------------------------------
  // buildTimelineOption(annotations, opts): REINE Funktion.
  //   opts.basis: 'content' | 'annotation' (Default 'content')
  // Rueckgabe: { option, categories:[label], withoutTime:int, plotted:int }
  //   option = ECharts-Option (Scatter auf Zeit-x / Kategorie-y).
  // ---------------------------------------------------------------------------
  function buildTimelineOption(annotations, opts) {
    opts = opts || {};
    var basis = opts.basis === 'annotation' ? 'annotation' : 'content';
    var F = window.AIWAnnotationFilter;
    var cats = F.CATEGORIES;                    // kanonische Reihenfolge
    var labels = cats.map(function (c) { return c.icon + ' ' + c.label; });
    var labelByCat = {};
    cats.forEach(function (c) { labelByCat[c.id] = c.icon + ' ' + c.label; });

    var points = [];
    var withoutTime = 0;
    (annotations || []).forEach(function (a) {
      var t = timeForBasis(a, basis);
      if (t == null) { withoutTime++; return; }
      var meta = F.categoryMeta(a.category);
      points.push({
        value: [t, labelByCat[a.category] || (meta.icon + ' ' + meta.label)],
        annId: a.id,
        itemStyle: { color: meta.color },
        // Zusatzinfos fuer den Tooltip (kein Einfluss auf die Darstellung)
        _cat: meta.label, _by: a.createdBy || '—', _txt: shortText(a),
        _hyp: F.isHypothesis(a)
      });
    });

    var option = {
      grid: { left: 120, right: 24, top: 16, bottom: 64 },
      tooltip: {
        trigger: 'item',
        formatter: function (p) {
          var d = p.data || {};
          var when = new Date(p.value[0]).toLocaleString('de-DE');
          return '<b>ID ' + d.annId + '</b> · ' + (d._cat || '') + (d._hyp ? ' · Vermutung' : '') +
            '<br>' + when + '<br>👤 ' + (d._by || '') +
            (d._txt ? '<br><i>' + d._txt.replace(/</g, '&lt;') + '</i>' : '');
        }
      },
      xAxis: { type: 'time', axisLabel: { hideOverlap: true } },
      yAxis: { type: 'category', data: labels, inverse: true, axisTick: { alignWithLabel: true } },
      // Visuelles Zoomen (getrennt vom Filter-Brush): Rad/Ziehen + Slider.
      dataZoom: [
        { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
        { type: 'slider', xAxisIndex: 0, filterMode: 'none', height: 18, bottom: 28 }
      ],
      // Brush auf der X-Achse: gezogenes Fenster -> Filterprädikat (Handler in der Klasse).
      brush: {
        xAxisIndex: 0, brushType: 'lineX', brushMode: 'single',
        throttleType: 'debounce', throttleDelay: 300,
        transformable: false, removeOnClick: true
      },
      series: [{
        type: 'scatter', symbolSize: 11, data: points,
        emphasis: { scale: 1.4 }
      }]
    };

    return { option: option, categories: labels, withoutTime: withoutTime, plotted: points.length };
  }

  // ---------------------------------------------------------------------------
  // AnnotationTimeline: rendert den Zeitstrahl in einen Container und verdrahtet
  // ECharts-Interaktionen. Callbacks: onSelect(annId), onBrush(fromMs,toMs).
  // ---------------------------------------------------------------------------
  function AnnotationTimeline() {
    this._chart = null;
    this._host = null;
    this._basis = 'content';
    this._onSelect = null;
    this._onBrush = null;
    this._suppressBrush = false;   // verhindert Rueckkopplung beim Neuaufbau
  }

  AnnotationTimeline.prototype.available = function () {
    return typeof window.echarts !== 'undefined' && window.echarts && typeof window.echarts.init === 'function';
  };

  AnnotationTimeline.prototype.mount = function (host, opts) {
    opts = opts || {};
    this._host = host;
    this._onSelect = opts.onSelect || null;
    this._onBrush = opts.onBrush || null;
    this._basis = opts.basis || 'content';
  };

  AnnotationTimeline.prototype.setBasis = function (basis) { this._basis = basis; };
  AnnotationTimeline.prototype.getBasis = function () { return this._basis; };

  // render(annotations): Chart (neu) aufbauen. Liefert withoutTime zurueck, damit
  // die View die "ohne Inhaltszeit"-Zeile beschriften kann.
  AnnotationTimeline.prototype.render = function (annotations) {
    if (!this.available()) {
      dbg('ECharts nicht verfuegbar');
      return { available: false, withoutTime: 0, plotted: 0 };
    }
    var self = this;
    var built = buildTimelineOption(annotations, { basis: this._basis });

    if (!this._chart) {
      this._chart = window.echarts.init(this._host);
      // Punkt-Klick -> Auswahl
      this._chart.on('click', function (params) {
        if (params && params.data && params.data.annId != null && self._onSelect) {
          self._onSelect(params.data.annId);
        }
      });
      // Brush-Ende -> Zeitfenster als Filter uebernehmen.
      this._chart.on('brushEnd', function (params) {
        if (self._suppressBrush) return;
        var range = self._extractRange(params);
        if (range && self._onBrush) self._onBrush(range[0], range[1]);
      });
      // Manche ECharts-Versionen liefern das Ergebnis ueber 'brushselected'.
      this._chart.on('brushselected', function (params) {
        if (self._suppressBrush) return;
        var range = self._extractRange(params);
        if (range && self._onBrush) self._onBrush(range[0], range[1]);
      });
    }

    this._suppressBrush = true;
    this._chart.setOption(built.option, true);
    // lineX-Brush aktivieren, damit sofort ohne Toolbox gezogen werden kann.
    try {
      this._chart.dispatchAction({
        type: 'takeGlobalCursor', key: 'brush',
        brushOption: { brushType: 'lineX', brushMode: 'single' }
      });
    } catch (e) { dbg('takeGlobalCursor fehlgeschlagen', e); }
    this._suppressBrush = false;

    return { available: true, withoutTime: built.withoutTime, plotted: built.plotted };
  };

  // _extractRange(params): aus einem Brush-Event das [fromMs, toMs] lesen.
  // lineX-Brush liefert coordRange = [xmin, xmax] in Achsen-(Zeit-)Werten (ms).
  AnnotationTimeline.prototype._extractRange = function (params) {
    var areas = (params && params.areas) ? params.areas
      : (params && params.batch && params.batch[0] ? params.batch[0].areas : null);
    if (!areas || !areas.length) return null;
    var cr = areas[0].coordRange;
    if (!cr || cr.length !== 2) return null;
    var a = Math.min(cr[0], cr[1]), b = Math.max(cr[0], cr[1]);
    return [Math.round(a), Math.round(b)];
  };

  AnnotationTimeline.prototype.resize = function () { if (this._chart) this._chart.resize(); };

  AnnotationTimeline.prototype.dispose = function () {
    if (this._chart) { this._chart.dispose(); this._chart = null; }
  };

  window.AIWAnnotationTimeline = {
    buildTimelineOption: buildTimelineOption,
    timeForBasis: timeForBasis,
    AnnotationTimeline: AnnotationTimeline,
    _setDebug: function (v) { DEBUG = !!v; }
  };
})();
