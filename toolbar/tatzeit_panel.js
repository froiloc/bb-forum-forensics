/* ===========================================================================
 * tatzeit_panel.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Fristen (AP-3A)
 * ---------------------------------------------------------------------------
 * Version: v0.8.534 · Build: 534 · 2026-07-26
 *
 * ZWECK
 *   Der Aufklappbereich "Tatzeitraum" im Annotations-Popup. Er erfasst zu
 *   einer Annotation den festgestellten Tatzeitraum und schreibt ihn ueber
 *   den auditierten Endpunkt /_forensic/tatzeit (Build 533).
 *
 * WARUM EINE EIGENE DATEI (Grundregel 10)
 *   toolbar.js hat 8073 Zeilen. Die Tatzeit ist ein abgeschlossenes Thema mit
 *   eigenem Endpunkt, eigenem Vokabular und eigenem Beleg — sie gehoert nicht
 *   in eine weitere Verzweigung eines ohnehin grossen Moduls. toolbar.js
 *   bekommt nur einen Ankerpunkt und drei Aufrufe; alles andere steht hier.
 *   Muster: toolbar/scroll_memory.js (Build 471), ebenfalls nach toolbar.js
 *   geladen und ueber window.* angebunden.
 *
 * ── WARUM AUFKLAPPBAR UND NICHT FEST IM FENSTER (mc 2026-07-26) ────────────
 *
 *   "Ich möchte die Oberfläche möglichst klar halten, und nicht alles, was
 *   eine Annotation bekommt, erhält auch einen Eintrag zum Zeitfenster."
 *
 *   Das Popup traegt schon Kategorie, Benutzer, Notiz, Tags und den markierten
 *   Text. Sechs weitere Felder fest eingebaut haetten die Maske ueberladen —
 *   fuer eine Angabe, die bei den meisten Annotationen gar nicht anfaellt.
 *   Der Bereich ist deshalb IMMER ZUGEKLAPPT, wenn das Popup aufgeht, auch
 *   wenn schon Eintraege vorliegen.
 *
 *   DARAUS FOLGT EINE ANPASSUNG EINER FRUEHEREN FESTLEGUNG, und die soll hier
 *   ausdruecklich stehen statt stillschweigend zu geschehen: mc hatte am
 *   2026-07-26 festgelegt, das leere Feld sei "hellgelb + ⚠" zu hinterlegen
 *   (Uebergabe §2.2 Nr. 8). Ein zugeklapptes Feld kann man aber nicht
 *   anmahnen — man saehe die Farbe nie. Die Mahnung wandert deshalb auf die
 *   AUFKLAPPZEILE: sie traegt den hellgelben Grund und das ⚠, solange bei
 *   einer §§-176/184-Annotation keine Tatzeit erfasst ist. Absicht und
 *   Wirkung der Festlegung bleiben damit erhalten — der Ort aendert sich.
 *   Statisch, ohne Animation (so festgelegt, damit keine
 *   prefers-reduced-motion-Sonderbehandlung noetig ist). Sobald ein Wert
 *   steht, verschwinden Farbe und Symbol GANZ und die Zeile zeigt statt
 *   dessen den erfassten Zeitraum.
 *
 * ── NUR §§ 176/184 WERDEN ANGEMAHNT ────────────────────────────────────────
 *
 *   Die Mahnung erscheint ausschliesslich bei den Kategorien CAT_176 und
 *   CAT_184 (toolbar.js:511-512). In allen anderen Kategorien ist die Zeile
 *   grau und sagt nichts — dort IST die Tatzeit optional, und ein Warnzeichen
 *   an einer Stelle, an der nichts zu tun ist, entwertet das Warnzeichen
 *   ueberall sonst. Erfassen kann man sie trotzdem; der Aufklappbereich sagt
 *   dann ausdruecklich, dass sie NICHT in die Fristberechnung eingeht.
 *   Die Mahnung folgt der Kategorie LIVE: wer das Dropdown im Popup auf 176
 *   stellt, sieht das Warnzeichen sofort (setCategory()).
 *
 * ── WANN GESCHRIEBEN WIRD ──────────────────────────────────────────────────
 *
 *   Der Bereich hat einen EIGENEN Knopf und schreibt SOFORT — er haengt NICHT
 *   am "Speichern" des Popups. Grund: der Tatzeit-Schreibvorgang ist ein
 *   eigener Beleg mit eigenem Handelnden, eigenem Zeitstempel und eigenem
 *   Ereignistyp (TATZEIT_SET, Build 533). An das Speichern der Notiz
 *   gekoppelt entstuende eine zusammengesetzte Handlung, deren Teilfehlschlag
 *   sich weder anzeigen noch belegen liesse.
 *
 *   IST DIE ANNOTATION NOCH NICHT GESPEICHERT, gibt es keine annotation_id,
 *   auf die sich die Tatzeit beziehen koennte. Der Knopf heisst dann
 *   "Annotation speichern und Tatzeit eintragen": er speichert zuerst die
 *   Annotation, wartet auf die vergebene ID und schreibt DANN die Tatzeit.
 *   Das Popup bleibt dabei offen — scheitert einer der beiden Schritte, steht
 *   der Grund in der Statuszeile und die eingegebenen Werte bleiben stehen.
 *   Kein stiller Teilzustand, und nichts geht verloren.
 *
 * ── DATUM -> UNIX-ZEIT ─────────────────────────────────────────────────────
 *
 *   <input type="date"> liefert 'JJJJ-MM-TT'. Umgerechnet wird auf UTC-
 *   MITTERNACHT (Date.UTC), NICHT auf lokale Mitternacht: der Server prueft
 *   gegen einen festen Rahmen (PLAUSIBEL_VON/BIS), und eine
 *   zeitzonenabhaengige Umrechnung machte aus derselben Eingabe je nach
 *   Rechner einen anderen Wert. Das Ende bekommt AUSDRUECKLICH KEINE
 *   23:59:59 aufaddiert — das waere erfundene Genauigkeit. Wie fein die
 *   Angabe ist, sagt allein das Feld "Genauigkeit".
 *
 * ── 'wortlaut' WIRD BEWUSST NICHT BESCHRIEBEN ──────────────────────────────
 *
 *   Die Spalte existiert seit m002, diese Maske fuellt sie NICHT. Sie waere
 *   bei einer unscharfen Angabe eine wortgleiche Dopplung von 'angabe_wert',
 *   und bei einer harten Angabe haette sie keinen Inhalt. Die Spalte bleibt
 *   fuer das reichere Modell unscharfer Angaben reserviert, das mc auf
 *   "spaeter" gelegt hat (Uebergabe §2.2 Nr. 9). Das ist ein bewusster
 *   Verzicht, kein Vergessen.
 *
 * DEBUG
 *   Ausgabelastiges Logging ueber window.forensicDebug === true (dieselbe
 *   Schaltung wie toolbar.js:539). Fuer PROD abschaltbar, ohne Codeaenderung.
 * ======================================================================== */

(function () {
  'use strict';

  // =========================================================================
  // KONSTANTEN
  // =========================================================================

  /** Kategorien, bei denen eine fehlende Tatzeit angemahnt wird. */
  var MAHN_KATEGORIEN = ['CAT_176', 'CAT_184'];

  var API_TATZEIT       = '/_forensic/tatzeit';
  var API_TATZEIT_CLEAR = '/_forensic/tatzeit/clear';

  /** Zeichenobergrenze fuer den Freitext einer 'sonstiges'-Quelle. */
  var FREITEXT_MAX = 200;

  function _dbg() {
    if (typeof window === 'undefined') return;
    if (window.forensicDebug !== true) return;
    var a = Array.prototype.slice.call(arguments);
    a.unshift('[Tatzeit]');
    try { console.log.apply(console, a); } catch (e) { /* egal */ }
  }

  function _esc(s) {
    return String(s === null || s === undefined ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // =========================================================================
  // ZEIT-HILFEN (rein, testbar ohne DOM)
  // =========================================================================

  /**
   * 'JJJJ-MM-TT' -> Unix-Sekunden (UTC-Mitternacht) oder null.
   * Gibt null bei leerer Eingabe zurueck; wirft NIE — eine unlesbare Eingabe
   * ergibt null und wird von der Feldpruefung als "nicht gesetzt" behandelt.
   */
  function datumTsUTC(text) {
    if (!text) return null;
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(text).trim());
    if (!m) return null;
    var jahr = parseInt(m[1], 10);
    var mon  = parseInt(m[2], 10);
    var tag  = parseInt(m[3], 10);
    if (mon < 1 || mon > 12 || tag < 1 || tag > 31) return null;
    var ts = Date.UTC(jahr, mon - 1, tag) / 1000;
    // Gegenprobe: Date.UTC rollt einen 31. Februar stillschweigend weiter.
    // Ohne diese Pruefung wuerde aus einem Tippfehler ein plausibles Datum.
    var d = new Date(ts * 1000);
    if (d.getUTCFullYear() !== jahr || (d.getUTCMonth() + 1) !== mon ||
        d.getUTCDate() !== tag) {
      return null;
    }
    return ts;
  }

  /** Unix-Sekunden -> 'JJJJ-MM-TT' (UTC) fuer <input type="date">. */
  function tsDatumUTC(ts) {
    if (ts === null || ts === undefined || ts === '') return '';
    var d = new Date(Number(ts) * 1000);
    if (isNaN(d.getTime())) return '';
    function p(n) { return (n < 10 ? '0' : '') + n; }
    return d.getUTCFullYear() + '-' + p(d.getUTCMonth() + 1) + '-' +
           p(d.getUTCDate());
  }

  /** Unix-Sekunden -> 'TT.MM.JJJJ' (UTC) fuer die Anzeige. */
  function tsAnzeige(ts) {
    if (ts === null || ts === undefined || ts === '') return '';
    var d = new Date(Number(ts) * 1000);
    if (isNaN(d.getTime())) return '';
    function p(n) { return (n < 10 ? '0' : '') + n; }
    return p(d.getUTCDate()) + '.' + p(d.getUTCMonth() + 1) + '.' +
           d.getUTCFullYear();
  }

  /**
   * Kurztext eines Eintrags fuer die Aufklappzeile.
   * Eine harte Angabe zeigt ihren Zeitraum, eine weiche ihren Wortlaut —
   * damit die zugeklappte Zeile sagt, WAS drinsteht, und nicht nur DASS.
   */
  function eintragKurz(e) {
    if (!e) return '';
    if (e.art === 'weich') {
      var w = String(e.angabe_wert || '').trim();
      return w ? ('„' + (w.length > 40 ? w.slice(0, 39) + '…' : w) + '"')
               : 'unscharfe Angabe';
    }
    var von = tsAnzeige(e.von_ts);
    var bis = tsAnzeige(e.bis_ts);
    if (von && bis) return (von === bis) ? von : (von + ' – ' + bis);
    if (von) return 'ab ' + von;
    if (bis) return 'bis ' + bis;
    return 'ohne Datum';
  }

  /** True, wenn eine fehlende Tatzeit bei dieser Kategorie anzumahnen ist. */
  function istMahnKategorie(catId) {
    return MAHN_KATEGORIEN.indexOf(String(catId || '')) !== -1;
  }

  /**
   * Zustand der Aufklappzeile aus Kategorie + vorhandenen Eintraegen.
   * Reine Funktion — der ganze Anzeigefall haengt an ihr, deshalb ist sie
   * getrennt vom DOM und einzeln geprueft (TP01-TP04).
   *
   * Rueckgabe: { mahnung: bool, symbol: string, text: string }
   */
  function zeilenZustand(catId, eintraege, opts) {
    var o = opts || {};
    var liste = eintraege || [];
    if (liste.length > 0) {
      // Sobald etwas steht, verschwinden Farbe und Symbol GANZ — nicht nur
      // blasser (ausdrueckliche Festlegung mc 2026-07-26).
      var txt = liste.map(eintragKurz).filter(Boolean).join(' · ');
      return { mahnung: false, symbol: '', text: txt || 'erfasst' };
    }
    if (o.unbekannt) {
      // Noch nicht geladen — es waere falsch, "nicht erfasst" zu behaupten,
      // bevor man nachgesehen hat.
      return { mahnung: false, symbol: '', text: 'wird geladen …' };
    }
    if (istMahnKategorie(catId)) {
      return { mahnung: true, symbol: '⚠', text: 'nicht erfasst' };
    }
    return { mahnung: false, symbol: '', text: 'nicht erfasst' };
  }

  // =========================================================================
  // EINGABEPRUEFUNG (rein, testbar ohne DOM)
  // =========================================================================

  /**
   * Baut aus den Feldwerten die Nutzlast fuer POST /_forensic/tatzeit.
   *
   * Prueft dieselben Regeln wie db/tatzeit_repo.py — ABER NICHT, UM SIE ZU
   * ERSETZEN. Der Server prueft in jedem Fall erneut, und die Datenbank hat
   * darunter noch ihre CHECKs (m002). Diese Ebene existiert allein dafuer,
   * dass die Ermittlerin den Grund SOFORT und in Klartext sieht, statt auf
   * eine Serverantwort zu warten.
   *
   * Rueckgabe: { ok: true, payload: {...} } oder { ok: false, fehler: '…' }
   */
  function baueNutzlast(werte, grenzen) {
    var w = werte || {};
    var g = grenzen || {};
    var art = w.art === 'weich' ? 'weich' : 'hart';

    var quelle = String(w.quelle_code || '').trim();
    if (!quelle) {
      return { ok: false, fehler: 'Bitte die Herkunft der Angabe auswählen. ' +
               'Eine Tatzeit ohne Herkunft ist kein Beleg.' };
    }

    var freitext = String(w.quelle_freitext || '').trim();
    if (quelle === 'sonstiges' && !freitext) {
      return { ok: false, fehler: 'Bei der Herkunft „Sonstiges" ist eine ' +
               'Angabe im Freitextfeld erforderlich.' };
    }
    if (quelle !== 'sonstiges' && freitext) { freitext = ''; }
    if (freitext.length > FREITEXT_MAX) {
      return { ok: false, fehler: 'Der Freitext ist auf ' + FREITEXT_MAX +
               ' Zeichen begrenzt (aktuell ' + freitext.length + ').' };
    }

    var p = {
      art: art,
      quelle_code: quelle,
      quelle_freitext: freitext || null,
    };

    if (art === 'hart') {
      var von = datumTsUTC(w.von);
      var bis = datumTsUTC(w.bis);
      if (von === null && bis === null) {
        return { ok: false, fehler: 'Bitte mindestens Beginn oder Ende ' +
                 'angeben. Eine datierbare Tatzeit ohne jeden Zeitwert würde ' +
                 'als festgestellt zählen, ohne etwas festzustellen.' };
      }
      if (w.von && von === null) {
        return { ok: false, fehler: 'Der Beginn ist kein gültiges Datum.' };
      }
      if (w.bis && bis === null) {
        return { ok: false, fehler: 'Das Ende ist kein gültiges Datum.' };
      }
      if (von !== null && bis !== null && bis < von) {
        return { ok: false, fehler: 'Das Ende liegt vor dem Beginn.' };
      }
      // Plausibilitaetsrahmen: die Grenzen kommen vom Server (GET-Antwort),
      // damit hier keine zweite Wahrheit entsteht. Fehlen sie, wird NICHT
      // geprueft — der Server tut es ohnehin, und eine geratene Grenze waere
      // schlimmer als keine.
      if (typeof g.von === 'number' && typeof g.bis === 'number') {
        var raus = [];
        if (von !== null && (von < g.von || von > g.bis)) raus.push('Beginn');
        if (bis !== null && (bis < g.von || bis > g.bis)) raus.push('Ende');
        if (raus.length) {
          return { ok: false, fehler: raus.join(' und ') + ' liegt außerhalb ' +
                   'des plausiblen Zeitraums (' + tsAnzeige(g.von) + ' bis ' +
                   tsAnzeige(g.bis) + ').' };
        }
      }
      p.von_ts = von;
      p.bis_ts = bis;
      p.genauigkeit = String(w.genauigkeit || '').trim() || null;
    } else {
      var wert = String(w.angabe_wert || '').trim();
      if (!wert) {
        return { ok: false, fehler: 'Bitte den Wortlaut der unscharfen ' +
                 'Angabe eintragen (zum Beispiel „vor zwei Jahren").' };
      }
      p.angabe_schluessel = 'markierung';
      p.angabe_wert = wert;
      p.genauigkeit = 'unbestimmt';
    }

    return { ok: true, payload: p };
  }

  // =========================================================================
  // KLASSE TatzeitPanel
  // =========================================================================

  /**
   * @param {Object} opts
   *   container   — HTMLElement, in das der Bereich gerendert wird
   *   ann         — die Annotation (localId, id, category, selection …)
   *   readOnly    — Fremdannotation: nur anzeigen
   *   ajaxGet     — function(url) -> Promise      (aus toolbar.js gereicht)
   *   ajaxPost    — function(url, body) -> Promise
   *   saveAnnotation — function() -> Promise, speichert die Annotation und
   *                    setzt ann.id (nur noetig fuer ungespeicherte)
   *   announce    — function(text), Barrierefreiheits-Ansage (optional)
   *   onChange    — function(), wird nach jeder Aenderung der Eintragslage
   *                 gerufen (damit das Popup andere Anzeigen nachziehen kann)
   */
  function TatzeitPanel(opts) {
    var o = opts || {};
    this._el        = o.container || null;
    this._ann       = o.ann || {};
    this._readOnly  = !!o.readOnly;
    this._ajaxGet   = o.ajaxGet || null;
    this._ajaxPost  = o.ajaxPost || null;
    this._saveAnn   = o.saveAnnotation || null;
    this._announce  = o.announce || function () {};
    this._onChange  = o.onChange || function () {};

    this._eintraege = [];
    this._geladen   = false;
    this._vokabular = null;
    this._grenzen   = {};
    this._canEdit   = false;
    this._readonlyGrund = null;
    this._kategorie = this._ann.category || '';
    this._busy      = false;

    _dbg('Panel erzeugt für Annotation', this._ann.id || '(neu)',
         'localId=', this._ann.localId, 'Kategorie=', this._kategorie);
  }

  // ---------------------------------------------------------------- Rendern
  TatzeitPanel.prototype.mount = function () {
    if (!this._el) { _dbg('mount(): kein Container — abgebrochen'); return this; }
    this._renderGeruest();
    this._ladeStand();
    return this;
  };

  TatzeitPanel.prototype._renderGeruest = function () {
    // <details> statt eigener Aufklapp-Logik: Tastaturbedienung,
    // Bildschirmleser-Semantik und der Zustand "offen/zu" kommen vom Browser.
    // Ein nachgebauter Umschalter waere mehr Code mit weniger Barrierefreiheit.
    this._el.innerHTML =
      '<details id="forensic-tatzeit" class="forensic-tatzeit">' +
      '<summary id="forensic-tatzeit-summary" class="forensic-tatzeit-summary">' +
      '<span class="forensic-tatzeit-caption">Tatzeitraum</span>' +
      '<span id="forensic-tatzeit-status" class="forensic-tatzeit-status">' +
      '</span></summary>' +
      '<div id="forensic-tatzeit-body" class="forensic-tatzeit-body">' +
      '<span class="forensic-popup-hint">Wird geladen …</span>' +
      '</div></details>';

    var self = this;
    var det = this._el.querySelector('#forensic-tatzeit');
    if (det) {
      det.addEventListener('toggle', function () {
        _dbg('Aufklappzustand:', det.open ? 'offen' : 'zu');
      });
    }
    this._zeichneZeile();
    return self;
  };

  /** Die Aufklappzeile — Mahnung, Symbol und Kurztext. */
  TatzeitPanel.prototype._zeichneZeile = function () {
    var sum = this._el && this._el.querySelector('#forensic-tatzeit-summary');
    var st  = this._el && this._el.querySelector('#forensic-tatzeit-status');
    if (!sum || !st) return;

    var z = zeilenZustand(this._kategorie, this._eintraege,
                          { unbekannt: !this._geladen });

    // Die Mahnklasse traegt hellgelben Grund und das Warnzeichen. Statisch,
    // keine Animation (Festlegung mc — so ist keine
    // prefers-reduced-motion-Sonderbehandlung noetig).
    if (z.mahnung) {
      sum.classList.add('forensic-tatzeit-summary--mahnung');
      sum.setAttribute('title', 'Bei §§ 176/184-Annotationen sollte der ' +
        'Tatzeitraum erfasst werden, sobald er zeitlich klar ist.');
    } else {
      sum.classList.remove('forensic-tatzeit-summary--mahnung');
      sum.removeAttribute('title');
    }
    st.textContent = (z.symbol ? z.symbol + ' ' : '') + z.text;
    _dbg('Zeile:', JSON.stringify(z));
  };

  // ------------------------------------------------------------------ Laden
  TatzeitPanel.prototype._ladeStand = function () {
    var self = this;
    if (!this._ajaxGet) {
      this._geladen = true;
      this._zeichneZeile();
      this._zeichneKoerper('Kein Zugriff auf den Server (kein ajaxGet).');
      return;
    }

    // Eine noch nicht gespeicherte Annotation hat keine ID — es gibt nichts
    // zu laden, und ein Abruf ohne Schluessel waere ein 400.
    var hatSchluessel = !!(this._ann.id || this._ann.localId);
    var url = API_TATZEIT + '?' +
      (this._ann.id ? 'annotation_id=' + encodeURIComponent(this._ann.id) : '') +
      (this._ann.id && this._ann.localId ? '&' : '') +
      (this._ann.localId ? 'local_id=' + encodeURIComponent(this._ann.localId) : '');

    if (!hatSchluessel) {
      _dbg('Kein Schlüssel — nichts zu laden (neue Annotation ohne localId).');
      this._geladen = true;
      this._zeichneZeile();
      this._zeichneKoerper();
      return;
    }

    _dbg('GET', url);
    this._ajaxGet(url).then(function (d) {
      _dbg('GET-Antwort:', JSON.stringify(d));
      if (!d || d.error) {
        // NICHT still leer lassen: eine leere Liste sähe aus wie
        // "nichts erfasst" — der Unterschied ist hier wesentlich.
        self._geladen = true;
        self._zeichneZeile();
        self._zeichneKoerper('Der Stand konnte nicht gelesen werden: ' +
          ((d && (d.detail || d.error)) || 'unbekannter Fehler') +
          ' — es ist NICHT gesagt, dass nichts erfasst ist.');
        return;
      }
      self._eintraege = d.eintraege || [];
      self._vokabular = d.vokabular || null;
      self._grenzen   = { von: d.plausibel_von, bis: d.plausibel_bis };
      self._canEdit   = !!d.can_edit && !self._readOnly;
      self._readonlyGrund = d.readonly_grund || null;
      self._wirdBerechnet = !!d.wird_berechnet;
      self._geladen   = true;
      self._zeichneZeile();
      self._zeichneKoerper();
      self._onChange();
    }).catch(function (e) {
      _dbg('GET fehlgeschlagen:', e);
      self._geladen = true;
      self._zeichneZeile();
      self._zeichneKoerper('Netzwerkfehler beim Lesen des Tatzeit-Standes — ' +
        'es ist NICHT gesagt, dass nichts erfasst ist.');
    });
  };

  // ----------------------------------------------------------- Koerper (Form)
  TatzeitPanel.prototype._zeichneKoerper = function (fehlermeldung) {
    var body = this._el && this._el.querySelector('#forensic-tatzeit-body');
    if (!body) return;

    var teile = [];

    if (fehlermeldung) {
      teile.push('<div class="forensic-tatzeit-fehler" role="alert">' +
                 _esc(fehlermeldung) + '</div>');
    }

    // Hinweis fuer Kategorien ausserhalb §§ 176/184 — die Angabe ist dort
    // erlaubt, geht aber nicht in die Fristberechnung ein. Das MUSS sichtbar
    // sein (Festlegung mc, Uebergabe §2.2 Nr. 11), sonst erwartet jemand eine
    // Wirkung, die es nicht gibt.
    if (!istMahnKategorie(this._kategorie)) {
      teile.push('<div id="forensic-tatzeit-hinweis-kat" ' +
        'class="forensic-tatzeit-hinweis">In dieser Kategorie geht die ' +
        'Tatzeit <strong>nicht</strong> in die Fristberechnung ein. Sie kann ' +
        'trotzdem festgehalten werden.</div>');
    }

    // Bis Build 535 rechnet der Fristenmonitor mit KEINER Tatzeit. Das sagt
    // der Server selbst (wird_berechnet), damit die Maske es nicht raten muss.
    if (this._geladen && this._wirdBerechnet === false) {
      teile.push('<div class="forensic-tatzeit-hinweis">Der Fristenmonitor ' +
        'wertet erfasste Tatzeiten derzeit noch <strong>nicht</strong> aus. ' +
        'Die Erfassung ist trotzdem verbindlich belegt.</div>');
    }

    teile.push(this._htmlListe());

    if (this._readOnly) {
      teile.push('<div class="forensic-tatzeit-hinweis">🔒 Fremdannotation — ' +
                 'nur lesen.</div>');
    } else if (this._readonlyGrund === 'support') {
      teile.push('<div class="forensic-tatzeit-hinweis">🔒 Im Live-Beistand ' +
        'kann keine Tatzeit erfasst werden: die Beweismitteldatenbank ist ' +
        'nur lesend angebunden.</div>');
    } else if (this._geladen && !this._canEdit) {
      teile.push('<div class="forensic-tatzeit-hinweis">🔒 Die Berechtigung ' +
        '„tatzeit.edit" ist nicht vergeben. Bitte an die Chef-Ermittlerin ' +
        'wenden.</div>');
    } else if (this._geladen) {
      teile.push(this._htmlFormular());
    }

    body.innerHTML = teile.join('');
    this._bindeFormular();
  };

  TatzeitPanel.prototype._htmlListe = function () {
    if (!this._eintraege.length) {
      return '<div class="forensic-tatzeit-leer">Noch keine Tatzeit erfasst.</div>';
    }
    var self = this;
    var zeilen = this._eintraege.map(function (e) {
      var q = e.quelle_code || e.quelle || '';
      var label = self._quelleLabel(q);
      if (e.quelle_freitext) { label += ': ' + e.quelle_freitext; }
      var gen = e.genauigkeit ? (' · Genauigkeit: ' + e.genauigkeit) : '';
      return '<li class="forensic-tatzeit-eintrag" data-tzid="' +
        _esc(e.id) + '">' +
        '<span class="forensic-tatzeit-eintrag-wert">' +
        _esc(eintragKurz(e)) + '</span>' +
        '<span class="forensic-tatzeit-eintrag-meta">' +
        _esc(label + gen + ' · Fassung ' + (e.version_nr || 1)) + '</span>' +
        (self._canEdit
          ? '<button type="button" class="forensic-btn forensic-btn-xs ' +
            'forensic-btn-secondary forensic-tatzeit-btn-clear" ' +
            'data-tzid="' + _esc(e.id) + '" ' +
            'title="Diese Angabe zurücknehmen">zurücknehmen</button>'
          : '') +
        '</li>';
    });
    return '<ul class="forensic-tatzeit-liste">' + zeilen.join('') + '</ul>';
  };

  TatzeitPanel.prototype._quelleLabel = function (code) {
    var v = this._vokabular && this._vokabular.quellen;
    if (v) {
      for (var i = 0; i < v.length; i++) {
        if (v[i].code === code) return v[i].label;
      }
    }
    return code || '(unbekannte Herkunft)';
  };

  TatzeitPanel.prototype._htmlFormular = function () {
    var quellen = (this._vokabular && this._vokabular.quellen) || [];
    var genau   = (this._vokabular && this._vokabular.genauigkeiten) ||
                  ['tag', 'monat', 'jahr', 'unbestimmt'];

    var qOpts = '<option value="">— Herkunft wählen —</option>' +
      quellen.map(function (q) {
        return '<option value="' + _esc(q.code) + '">' + _esc(q.label) +
               '</option>';
      }).join('');

    var gOpts = genau.map(function (g) {
      return '<option value="' + _esc(g) + '"' +
             (g === 'tag' ? ' selected' : '') + '>' + _esc(g) + '</option>';
    }).join('');

    // Vorbelegung des Wortlauts aus dem markierten Text: die unscharfe Angabe
    // steht in aller Regel genau dort (mc: "als Markierung um den Text
    // festhalten"). Nur ein Vorschlag — das Feld bleibt frei editierbar.
    var vorschlag = '';
    if (this._ann.selection && this._ann.selection.textContent) {
      vorschlag = String(this._ann.selection.textContent).trim().slice(0, 120);
    }

    var neu = !this._ann.id;
    var btnText = neu
      ? 'Annotation speichern und Tatzeit eintragen'
      : 'Tatzeit eintragen';

    return '' +
      '<fieldset class="forensic-tatzeit-form">' +
      '<legend class="forensic-popup-label">Neue Angabe</legend>' +

      '<div class="forensic-tatzeit-artwahl" role="radiogroup" ' +
      'aria-label="Art der Zeitangabe">' +
      '<label><input type="radio" name="forensic-tatzeit-art" ' +
      'id="forensic-tatzeit-art-hart" value="hart" checked> datierbar</label>' +
      '<label><input type="radio" name="forensic-tatzeit-art" ' +
      'id="forensic-tatzeit-art-weich" value="weich"> unscharf</label>' +
      '</div>' +

      '<div id="forensic-tatzeit-block-hart">' +
      '<div class="forensic-tatzeit-zeile">' +
      '<label for="forensic-tatzeit-von" class="forensic-popup-label ' +
      'forensic-popup-label--inline">Beginn:</label>' +
      '<input type="date" id="forensic-tatzeit-von" ' +
      'class="forensic-popup-input forensic-tatzeit-datum">' +
      '<label for="forensic-tatzeit-bis" class="forensic-popup-label ' +
      'forensic-popup-label--inline">Ende:</label>' +
      '<input type="date" id="forensic-tatzeit-bis" ' +
      'class="forensic-popup-input forensic-tatzeit-datum">' +
      '</div>' +
      '<label for="forensic-tatzeit-genauigkeit" class="forensic-popup-label">' +
      'Genauigkeit:</label>' +
      '<select id="forensic-tatzeit-genauigkeit" class="forensic-popup-select">' +
      gOpts + '</select>' +
      '</div>' +

      '<div id="forensic-tatzeit-block-weich" style="display:none">' +
      '<label for="forensic-tatzeit-wert" class="forensic-popup-label">' +
      'Wortlaut der Angabe:</label>' +
      '<input type="text" id="forensic-tatzeit-wert" ' +
      'class="forensic-popup-input" maxlength="200" ' +
      'placeholder="z. B. „vor zwei Jahren"" value="' + _esc(vorschlag) +
      '">' +
      '<div class="forensic-tatzeit-hinweis">Unscharfe Angaben werden ' +
      'festgehalten, aber <strong>nicht</strong> in eine Frist umgerechnet.</div>' +
      '</div>' +

      '<label for="forensic-tatzeit-quelle" class="forensic-popup-label">' +
      'Herkunft der Angabe:</label>' +
      '<select id="forensic-tatzeit-quelle" class="forensic-popup-select">' +
      qOpts + '</select>' +
      '<input type="text" id="forensic-tatzeit-freitext" ' +
      'class="forensic-popup-input" style="display:none" ' +
      'maxlength="' + FREITEXT_MAX + '" ' +
      'placeholder="Herkunft im Klartext (Pflicht bei „Sonstiges")">' +

      '<div id="forensic-tatzeit-meldung" class="forensic-tatzeit-meldung" ' +
      'role="status" aria-live="polite"></div>' +

      '<button type="button" id="forensic-tatzeit-btn-set" ' +
      'class="forensic-btn forensic-btn-primary forensic-tatzeit-btn-set">' +
      _esc(btnText) + '</button>' +
      '</fieldset>';
  };

  // -------------------------------------------------------------- Verdrahten
  TatzeitPanel.prototype._bindeFormular = function () {
    var self = this;
    var q = function (id) { return self._el.querySelector('#' + id); };

    var artHart  = q('forensic-tatzeit-art-hart');
    var artWeich = q('forensic-tatzeit-art-weich');
    var blkHart  = q('forensic-tatzeit-block-hart');
    var blkWeich = q('forensic-tatzeit-block-weich');

    function umschalten() {
      var weich = !!(artWeich && artWeich.checked);
      if (blkHart)  blkHart.style.display  = weich ? 'none' : '';
      if (blkWeich) blkWeich.style.display = weich ? '' : 'none';
      _dbg('Art umgeschaltet auf', weich ? 'weich' : 'hart');
    }
    if (artHart)  artHart.addEventListener('change', umschalten);
    if (artWeich) artWeich.addEventListener('change', umschalten);

    var quelle   = q('forensic-tatzeit-quelle');
    var freitext = q('forensic-tatzeit-freitext');
    if (quelle && freitext) {
      quelle.addEventListener('change', function () {
        var pflicht = self._freitextPflicht(quelle.value);
        freitext.style.display = pflicht ? '' : 'none';
        if (!pflicht) freitext.value = '';
        _dbg('Herkunft', quelle.value, '— Freitext', pflicht ? 'Pflicht' : 'aus');
      });
    }

    var btn = q('forensic-tatzeit-btn-set');
    if (btn) {
      btn.addEventListener('click', function () { self._eintragen(); });
    }

    var clears = this._el.querySelectorAll('.forensic-tatzeit-btn-clear');
    Array.prototype.forEach.call(clears, function (b) {
      b.addEventListener('click', function () {
        self._zuruecknehmen(b.getAttribute('data-tzid'));
      });
    });
  };

  TatzeitPanel.prototype._freitextPflicht = function (code) {
    var v = this._vokabular && this._vokabular.quellen;
    if (!v) return code === 'sonstiges';
    for (var i = 0; i < v.length; i++) {
      if (v[i].code === code) return !!v[i].freitext_pflicht;
    }
    return false;
  };

  TatzeitPanel.prototype._meldung = function (text, istFehler) {
    var el = this._el && this._el.querySelector('#forensic-tatzeit-meldung');
    if (!el) return;
    el.textContent = text || '';
    el.className = 'forensic-tatzeit-meldung' +
      (istFehler ? ' forensic-tatzeit-meldung--fehler' : '');
    if (text) { this._announce(text); }
  };

  // -------------------------------------------------------------- Schreiben
  TatzeitPanel.prototype._feldwerte = function () {
    var self = this;
    var q = function (id) { return self._el.querySelector('#' + id); };
    var w = function (id) { var e = q(id); return e ? e.value : ''; };
    var artWeich = q('forensic-tatzeit-art-weich');
    return {
      art: (artWeich && artWeich.checked) ? 'weich' : 'hart',
      von: w('forensic-tatzeit-von'),
      bis: w('forensic-tatzeit-bis'),
      genauigkeit: w('forensic-tatzeit-genauigkeit'),
      angabe_wert: w('forensic-tatzeit-wert'),
      quelle_code: w('forensic-tatzeit-quelle'),
      quelle_freitext: w('forensic-tatzeit-freitext'),
    };
  };

  TatzeitPanel.prototype._eintragen = function () {
    var self = this;
    if (this._busy) { _dbg('Eintragen ignoriert — Vorgang läuft bereits.'); return; }

    var gebaut = baueNutzlast(this._feldwerte(), this._grenzen);
    if (!gebaut.ok) {
      this._meldung(gebaut.fehler, true);
      _dbg('Eingabe abgelehnt:', gebaut.fehler);
      return;
    }

    this._busy = true;
    this._meldung('Wird eingetragen …', false);

    // Ist die Annotation noch nicht gespeichert, gibt es keine
    // annotation_id — erst speichern, dann eintragen. Das Popup bleibt
    // offen, damit ein Fehlschlag sichtbar ist (s. Kopfkommentar).
    var vorher = this._ann.id
      ? Promise.resolve(true)
      : this._speichereAnnotationZuerst();

    vorher.then(function (bereit) {
      if (!bereit) { self._busy = false; return null; }
      var payload = gebaut.payload;
      payload.annotation_id = self._ann.id;
      payload.local_id      = self._ann.localId || null;
      _dbg('POST', API_TATZEIT, JSON.stringify(payload));
      return self._ajaxPost(API_TATZEIT, payload).then(function (r) {
        self._busy = false;
        _dbg('POST-Antwort:', JSON.stringify(r));
        if (!r || !r.ok) {
          self._meldung('Nicht eingetragen: ' +
            ((r && (r.detail || r.error)) || 'unbekannter Fehler'), true);
          return;
        }
        self._meldung('Tatzeit eingetragen (Beleg #' + r.audit_seq + ').', false);
        self._ladeStand();
      });
    }).catch(function (e) {
      self._busy = false;
      _dbg('POST fehlgeschlagen:', e);
      self._meldung('Netzwerkfehler — es wurde NICHTS eingetragen. Die ' +
        'eingegebenen Werte bleiben stehen.', true);
    });
  };

  /**
   * Speichert die noch nicht persistierte Annotation und wartet auf ihre ID.
   * Liefert Promise<boolean> — false, wenn danach keine ID vorliegt.
   */
  TatzeitPanel.prototype._speichereAnnotationZuerst = function () {
    var self = this;
    if (!this._saveAnn) {
      this._meldung('Die Annotation ist noch nicht gespeichert und kann von ' +
        'hier aus nicht gespeichert werden. Bitte zuerst speichern.', true);
      return Promise.resolve(false);
    }
    _dbg('Annotation noch ohne ID — speichere zuerst.');
    return Promise.resolve(this._saveAnn()).then(function () {
      if (!self._ann.id) {
        // NICHT stillschweigend weitermachen: ohne ID gäbe es nichts, woran
        // die Tatzeit hängt. Der Grund steht in der Statuszeile, die Werte
        // bleiben im Formular.
        self._meldung('Die Annotation konnte nicht gespeichert werden — die ' +
          'Tatzeit wurde deshalb NICHT eingetragen. Die eingegebenen Werte ' +
          'bleiben stehen.', true);
        return false;
      }
      _dbg('Annotation gespeichert, ID =', self._ann.id);
      return true;
    });
  };

  TatzeitPanel.prototype._zuruecknehmen = function (tzid) {
    var self = this;
    if (this._busy || !tzid) return;
    this._busy = true;
    _dbg('POST', API_TATZEIT_CLEAR, 'tatzeit_id=', tzid);
    this._ajaxPost(API_TATZEIT_CLEAR, { tatzeit_id: Number(tzid) })
      .then(function (r) {
        self._busy = false;
        if (!r || !r.ok) {
          self._meldung('Nicht zurückgenommen: ' +
            ((r && (r.detail || r.error)) || 'unbekannter Fehler'), true);
          return;
        }
        self._meldung('Angabe zurückgenommen (Beleg #' + r.audit_seq + ').',
                      false);
        self._ladeStand();
      })
      .catch(function (e) {
        self._busy = false;
        _dbg('clear fehlgeschlagen:', e);
        self._meldung('Netzwerkfehler — es wurde NICHTS geändert.', true);
      });
  };

  // ------------------------------------------------------------ Aussen-API
  /**
   * Kategorie hat sich im Popup geaendert. Die Mahnung folgt LIVE, damit ein
   * Wechsel auf 176/184 sofort sichtbar wird.
   */
  TatzeitPanel.prototype.setCategory = function (catId) {
    if (this._kategorie === catId) return;
    _dbg('Kategorie geändert:', this._kategorie, '→', catId);
    this._kategorie = catId;
    this._zeichneZeile();
    // Der Hinweis "geht nicht in die Fristberechnung ein" haengt ebenfalls an
    // der Kategorie — der Koerper wird neu gezeichnet, wenn er offen ist.
    var det = this._el && this._el.querySelector('#forensic-tatzeit');
    if (det && det.open) { this._zeichneKoerper(); }
  };

  /** Anzahl aktiver Eintraege (fuer Anzeigen ausserhalb des Panels). */
  TatzeitPanel.prototype.count = function () {
    return this._eintraege.length;
  };

  TatzeitPanel.prototype.destroy = function () {
    _dbg('Panel abgeräumt.');
    this._el = null;
    this._ann = {};
    this._eintraege = [];
  };

  // =========================================================================
  // EXPORT
  // =========================================================================
  TatzeitPanel.datumTsUTC     = datumTsUTC;
  TatzeitPanel.tsDatumUTC     = tsDatumUTC;
  TatzeitPanel.tsAnzeige      = tsAnzeige;
  TatzeitPanel.eintragKurz    = eintragKurz;
  TatzeitPanel.zeilenZustand  = zeilenZustand;
  TatzeitPanel.baueNutzlast   = baueNutzlast;
  TatzeitPanel.istMahnKategorie = istMahnKategorie;
  TatzeitPanel.MAHN_KATEGORIEN  = MAHN_KATEGORIEN;
  TatzeitPanel.FREITEXT_MAX     = FREITEXT_MAX;

  if (typeof window !== 'undefined') {
    window.TatzeitPanel = TatzeitPanel;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = TatzeitPanel;
  }
})();
