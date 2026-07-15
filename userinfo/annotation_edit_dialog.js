// =============================================================================
// userinfo/annotation_edit_dialog.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
// -----------------------------------------------------------------------------
// ZWECK (gesicherte Intention):
//   Schlanke, EIGENSTAENDIGE Bearbeiten-Maske fuer eine bestehende Annotation
//   im Nutzerinfo-Fenster. Optisch an die B3-Maske angelehnt (Feldaufbau:
//   Kategorie, Notiz, Tags, markierter Text), aber OHNE die harten Toolbar-
//   Abhaengigkeiten des Originals AnnotationPopupModule.
//
//   Warum Neubau statt Wiederverwendung (Entscheidung E1, belegt):
//     AnnotationPopupModule (toolbar.js:2536) ist modul-privat (kein Export) und
//     fest an den Seitenkontext gebunden — _state-Globals, ForensicToolbar.config,
//     HighlightModule/MinimapModule/AccessibilityModule sowie _positionPopup()
//     am markierten Forums-DOM. Im Recherche-Kontext existiert dieser Kontext
//     NICHT. Eine schlanke, gegen POST /_forensic/annotate arbeitende Maske ist
//     korrekter und wartbarer. (Bauplan §12; Assessment 2026-07-14.)
//
//   Speichern laeuft ueber den Store (Upsert via local_id), damit die
//   Versionskette serverseitig sauber fortgeschrieben wird.
// =============================================================================

(function () {
  'use strict';

  var DEBUG = false;
  function dbg() {
    if (DEBUG && typeof console !== 'undefined') {
      console.log.apply(console, ['[AIW-Edit]'].concat([].slice.call(arguments)));
    }
  }

  var F = null; // lazy: window.AIWAnnotationFilter

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function AnnotationEditDialog(store) {
    this._store = store;
    this._overlay = null;
    this._ann = null;
    this._onSaved = null;
  }

  // open(ann, onSaved): Maske fuer eine Annotation oeffnen.
  AnnotationEditDialog.prototype.open = function (ann, onSaved) {
    F = window.AIWAnnotationFilter;
    this._ann = ann;
    this._onSaved = onSaved || null;
    this._build();
  };

  AnnotationEditDialog.prototype._build = function () {
    var self = this, ann = this._ann;
    this._destroy(); // evtl. offene Instanz sauber abbauen

    var overlay = el('div', 'air-modal-overlay');
    var modal = el('div', 'air-modal');
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Annotation bearbeiten');

    // Kopf
    var head = el('div', 'air-modal-head');
    head.appendChild(el('span', 'air-modal-title', 'Annotation bearbeiten'));
    head.appendChild(el('span', 'air-modal-id', 'ID ' + ann.id + (ann.versionNr ? ' · v' + ann.versionNr : '')));
    modal.appendChild(head);

    var bodyWrap = el('div', 'air-modal-body');

    // --- Kategorie ---
    bodyWrap.appendChild(el('label', 'air-field-label', 'Kategorie'));
    var sel = el('select', 'air-select');
    F.CATEGORIES.forEach(function (c) {
      var o = el('option', null, c.icon + ' ' + c.label + ' — ' + c.desc);
      o.value = c.id;
      if (c.id === ann.category) o.selected = true;
      sel.appendChild(o);
    });
    this._sel = sel;
    bodyWrap.appendChild(sel);

    // --- Notiz ---
    bodyWrap.appendChild(el('label', 'air-field-label', 'Notiz'));
    var ta = el('textarea', 'air-textarea');
    ta.value = ann.text || '';
    ta.setAttribute('rows', '4');
    this._ta = ta;
    bodyWrap.appendChild(ta);

    // --- Tags ---
    bodyWrap.appendChild(el('label', 'air-field-label', 'Tags (kommagetrennt)'));
    var tagInp = el('input', 'air-input');
    tagInp.type = 'text';
    tagInp.value = (ann.tags || []).join(', ');
    tagInp.setAttribute('list', 'air-edit-tagvocab');
    this._tagInp = tagInp;
    bodyWrap.appendChild(tagInp);
    // Vorschlagsliste aus dem Vokabular (belegt toolbar.js:509)
    var dl = el('datalist'); dl.id = 'air-edit-tagvocab';
    F.TAG_VOCABULARY.forEach(function (t) { var o = el('option'); o.value = t; dl.appendChild(o); });
    bodyWrap.appendChild(dl);

    // --- Markierter Text (read-only, falls vorhanden) ---
    var selText = ann.selection && (ann.selection.text || ann.selection.textContent);
    if (selText) {
      bodyWrap.appendChild(el('label', 'air-field-label', 'Markierter Text'));
      var q = el('div', 'air-seltext', '„' + selText + '“');
      bodyWrap.appendChild(q);
    }

    // Fehlerzeile
    this._errLine = el('div', 'air-modal-error');
    this._errLine.style.display = 'none';
    bodyWrap.appendChild(this._errLine);

    modal.appendChild(bodyWrap);

    // Fuss: Abbrechen / Speichern
    var foot = el('div', 'air-modal-foot');
    var btnCancel = el('button', 'air-btn air-btn-secondary', 'Abbrechen');
    var btnSave = el('button', 'air-btn air-btn-primary', '💾 Speichern');
    this._btnSave = btnSave;
    foot.appendChild(btnCancel);
    foot.appendChild(btnSave);
    modal.appendChild(foot);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    this._overlay = overlay;

    // Interaktionen
    btnCancel.addEventListener('click', function () { self._destroy(); });
    overlay.addEventListener('mousedown', function (ev) { if (ev.target === overlay) self._destroy(); });
    document.addEventListener('keydown', this._escHandler = function (ev) {
      if (ev.key === 'Escape') self._destroy();
    });
    btnSave.addEventListener('click', function () { self._save(); });

    // Fokus in die Notiz (haeufigstes Bearbeitungsziel)
    setTimeout(function () { try { ta.focus(); } catch (e) {} }, 0);
    dbg('Maske geoeffnet fuer', ann.id);
  };

  AnnotationEditDialog.prototype._parseTags = function (raw) {
    return String(raw || '')
      .split(',')
      .map(function (t) { return t.trim(); })
      .filter(function (t) { return t.length > 0; });
  };

  AnnotationEditDialog.prototype._save = function () {
    var self = this, ann = this._ann;
    var overrides = {
      category: this._sel.value,
      text: this._ta.value,
      tags: this._parseTags(this._tagInp.value)
    };
    this._btnSave.disabled = true;
    this._errLine.style.display = 'none';
    dbg('speichere', overrides);
    this._store.saveEdit(ann, overrides).then(function () {
      if (self._onSaved) self._onSaved();
      self._destroy();
    }).catch(function (err) {
      self._btnSave.disabled = false;
      self._errLine.textContent = 'Fehler: ' + (err && err.message ? err.message : err);
      self._errLine.style.display = 'block';
    });
  };

  AnnotationEditDialog.prototype._destroy = function () {
    if (this._escHandler) { document.removeEventListener('keydown', this._escHandler); this._escHandler = null; }
    if (this._overlay && this._overlay.parentNode) { this._overlay.parentNode.removeChild(this._overlay); }
    this._overlay = null;
  };

  window.AIWAnnotationEditDialog = AnnotationEditDialog;
  window.AIWAnnotationEditDialog._setDebug = function (v) { DEBUG = !!v; };
})();
