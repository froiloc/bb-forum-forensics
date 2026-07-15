// =============================================================================
// userinfo/annotation_identity_profile.js
// IT-Forensisches Ermittlungswerkzeug — Baustelle 4: Annotationsrecherche
// -----------------------------------------------------------------------------
// ZWECK (gesicherte Intention):
//   "Identitäts-Steckbrief" — verdichtet die in Annotationen GETAGGTEN
//   Identitaetswerte (realname, email, telefon, adresse, ip, pgp, social,
//   telegram, foto, username) der aktuell gefilterten Menge zu einem lebenden
//   Zuordnungsprofil des Forenkontos. Jeder Wert ist BELEGT und rueckverlinkt
//   auf seine Annotation(en) — das uebersetzt verstreute Einzelbelege in das
//   Projektziel "Konto -> reale Person". (Bauplan §10.)
//
//   FORENSISCHE INTEGRITAET (Grundregel 1): Werte, die ausschliesslich aus
//   VERMUTUNGS-Annotationen (Tag 'vermutung'/'hypothese') stammen, werden strikt
//   als "Vermutung" getrennt ausgewiesen und NICHT zu den gesicherten Werten
//   gezaehlt. Ein Wert gilt als gesichert, sobald ihn mindestens eine
//   NICHT-Vermutungs-Annotation stuetzt.
//
//   Zwei Teile in dieser Datei:
//     - build(annotations): REINER, testbarer Aggregator (kein DOM/Netz).
//     - IdentityProfileView: rendert das Ergebnis von build() ins DOM.
//   (Aggregator als reine Funktion ausgelagert; die Klasse ist die einzige
//    Klasse dieser Datei — Grundregel 10.)
// =============================================================================

(function () {
  'use strict';

  var DEBUG = false;
  function dbg() {
    if (DEBUG && typeof console !== 'undefined') {
      console.log.apply(console, ['[AIW-Steckbrief]'].concat([].slice.call(arguments)));
    }
  }

  // Anzeige-Metadaten der Identitaets-Tags (Reihenfolge = Wichtigkeit fuer die
  // Personenzuordnung). Schluessel = Tag (klein), wie im Vokabular toolbar.js:509.
  var IDENTITY_META = [
    { tag: 'realname', label: 'Klarname',       icon: '🪪' },
    { tag: 'email',    label: 'E-Mail',         icon: '📧' },
    { tag: 'telefon',  label: 'Telefon',        icon: '☎️' },
    { tag: 'adresse',  label: 'Adresse',        icon: '🏠' },
    { tag: 'ip',       label: 'IP-Adresse',     icon: '🌐' },
    { tag: 'pgp',      label: 'PGP',            icon: '🔑' },
    { tag: 'social',   label: 'Social Media',   icon: '💬' },
    { tag: 'telegram', label: 'Telegram',       icon: '✈️' },
    { tag: 'foto',     label: 'Foto',           icon: '📷' },
    { tag: 'username', label: 'Benutzername',   icon: '🏷️' }
  ];

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // valueOf(ann): der anzuzeigende Kandidatenwert einer Annotation.
  // Primaer der markierte Originaltext (selection.text) — das ist der Beleg;
  // sonst die Ermittler-Notiz; sonst ein sichtbarer Platzhalter (GR1: kein
  // stilles Verschlucken von "Tag ohne Textwert").
  function valueOf(ann) {
    var sel = ann.selection && (ann.selection.text || ann.selection.textContent);
    if (sel && String(sel).trim()) return String(sel).trim();
    if (ann.text && String(ann.text).trim()) return String(ann.text).trim();
    return '(kein Textwert — siehe Quelle)';
  }

  function norm(s) { return String(s).toLowerCase().replace(/\s+/g, ' ').trim(); }

  // ---------------------------------------------------------------------------
  // build(annotations): reiner Aggregator. annotations = bereits gefilterte Menge.
  // Rueckgabe siehe JSDoc am Kopf.
  // ---------------------------------------------------------------------------
  function build(annotations) {
    var F = window.AIWAnnotationFilter;
    var list = annotations || [];
    var sections = [];
    var coveredTypes = 0, totalValues = 0, hypothesisValues = 0, identityAnnotations = 0;
    var seenAnn = {};

    IDENTITY_META.forEach(function (meta) {
      // Annotationen mit diesem Identitaets-Tag heraussuchen.
      var withTag = list.filter(function (a) {
        return (a.tags || []).some(function (t) { return String(t).toLowerCase() === meta.tag; });
      });
      if (withTag.length === 0) return;

      // Nach normalisiertem Wert gruppieren; Belege je Wert sammeln.
      var groups = {}; // normValue -> { value, beleg:[{annId,category,createdBy,time,isHyp}], anyConfirmed }
      withTag.forEach(function (a) {
        if (!seenAnn[a.id]) { seenAnn[a.id] = true; identityAnnotations++; }
        var v = valueOf(a);
        var key = norm(v);
        if (!groups[key]) groups[key] = { value: v, beleg: [], anyConfirmed: false };
        var isHyp = F.isHypothesis(a);
        groups[key].beleg.push({
          annId: a.id, category: a.category, createdBy: a.createdBy || '—',
          time: F.annotationTimeMs(a), isHyp: isHyp
        });
        if (!isHyp) groups[key].anyConfirmed = true;
      });

      var confirmed = [], hypotheses = [];
      Object.keys(groups).forEach(function (k) {
        var g = groups[k];
        // Beleg nach Zeit sortieren (aeltester zuerst = fruehester Nachweis).
        g.beleg.sort(function (x, y) {
          if (x.time == null && y.time == null) return 0;
          if (x.time == null) return 1;
          if (y.time == null) return -1;
          return x.time - y.time;
        });
        if (g.anyConfirmed) confirmed.push(g); else hypotheses.push(g);
      });

      if (confirmed.length > 0) coveredTypes++;
      totalValues += confirmed.length;
      hypothesisValues += hypotheses.length;

      sections.push({
        tag: meta.tag, label: meta.label, icon: meta.icon,
        confirmed: confirmed, hypotheses: hypotheses
      });
    });

    return {
      sections: sections,
      coveredTypes: coveredTypes,
      totalValues: totalValues,
      hypothesisValues: hypothesisValues,
      identityAnnotations: identityAnnotations,
      identityTypeCount: IDENTITY_META.length
    };
  }

  // ---------------------------------------------------------------------------
  // IdentityProfileView: rendert das build()-Ergebnis. Rueckverlinkung ueber
  // Callback onFocus(annId) (die Recherche-View scrollt/hebt die Karte hervor).
  // ---------------------------------------------------------------------------
  function IdentityProfileView() {
    this._onFocus = null;
  }

  IdentityProfileView.prototype.render = function (container, annotations, opts) {
    opts = opts || {};
    this._onFocus = opts.onFocus || null;
    var self = this, F = window.AIWAnnotationFilter;
    while (container.firstChild) container.removeChild(container.firstChild);

    var profile = build(annotations);
    dbg('build', profile);

    // Kopfzeile: Abdeckung der Identitaetsmerkmale.
    var head = el('div', 'air-prof-head');
    head.appendChild(el('span', 'air-prof-cover',
      profile.coveredTypes + ' von ' + profile.identityTypeCount + ' Identitätsmerkmalen belegt'));
    if (profile.hypothesisValues > 0) {
      head.appendChild(el('span', 'air-prof-hypcount', '· ' + profile.hypothesisValues + ' Vermutung(en)'));
    }
    container.appendChild(head);

    if (profile.sections.length === 0) {
      container.appendChild(el('div', 'air-prof-empty',
        'Noch keine mit Identitäts-Tags (z. B. email, realname, ip) versehenen Annotationen in der aktuellen Auswahl. '
        + 'Tags an den Karten vergeben, um den Steckbrief aufzubauen.'));
      return;
    }

    profile.sections.forEach(function (sec) {
      var section = el('div', 'air-prof-section');
      var title = el('div', 'air-prof-tag');
      title.appendChild(el('span', 'air-prof-tag-icon', sec.icon));
      title.appendChild(el('span', 'air-prof-tag-label', sec.label));
      var total = sec.confirmed.length + sec.hypotheses.length;
      title.appendChild(el('span', 'air-prof-tag-count', String(total)));
      section.appendChild(title);

      sec.confirmed.forEach(function (g) { section.appendChild(self._valueRow(g, false)); });
      sec.hypotheses.forEach(function (g) { section.appendChild(self._valueRow(g, true)); });

      container.appendChild(section);
    });
  };

  IdentityProfileView.prototype._valueRow = function (group, isHyp) {
    var self = this, F = window.AIWAnnotationFilter;
    var row = el('div', 'air-prof-value' + (isHyp ? ' air-prof-value-hyp' : ''));

    var head = el('div', 'air-prof-value-head');
    if (isHyp) head.appendChild(el('span', 'air-prof-hyp-badge', 'Vermutung'));
    head.appendChild(el('span', 'air-prof-value-text', group.value));
    row.appendChild(head);

    // Belege (rueckverlinkt): je Beleg ein klickbarer Chip "ID n".
    var belege = el('div', 'air-prof-belege');
    belege.appendChild(el('span', 'air-prof-belege-label', 'belegt durch: '));
    group.beleg.forEach(function (b) {
      var meta = F.categoryMeta(b.category);
      var chip = el('button', 'air-prof-beleg');
      chip.style.borderColor = meta.color;
      chip.textContent = meta.icon + ' ID ' + b.annId;
      chip.title = (meta.label) + ' · ' + b.createdBy + (b.isHyp ? ' · Vermutung' : '');
      chip.addEventListener('click', function () { if (self._onFocus) self._onFocus(b.annId); });
      belege.appendChild(chip);
    });
    row.appendChild(belege);
    return row;
  };

  window.AIWIdentityProfile = {
    IDENTITY_META: IDENTITY_META,
    build: build,
    IdentityProfileView: IdentityProfileView,
    _setDebug: function (v) { DEBUG = !!v; }
  };
})();
