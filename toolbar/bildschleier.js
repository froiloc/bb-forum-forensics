/* ===========================================================================
 * bildschleier.js
 * IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 772, 775)
 * ---------------------------------------------------------------------------
 * Version: v0.8.775 · Build: 775 · 2026-10-14
 *
 * ZWECK
 *   Die Augen-Schaltflaeche 👁 in der Werkzeugleiste und das Setzen der
 *   seitenbezogenen Ausnahmen vom Bildschleier. Bauplan:
 *   management/Bauplan_Builds771-773_Bildschleier_v0_5.md, §5.1 und §5.5.
 *
 * WAS DIESE DATEI NICHT TUT — UND WARUM DAS DIE SICHERHEIT TRAEGT
 *   Sie schaltet den Schleier NICHT ein. Das tut der Server: er schreibt die
 *   Klasse 'aiw-image-veil' an <html>, bevor das erste Byte Seiteninhalt
 *   existiert, und die Grundregel /_forensic/image-veil.css verschleiert dann
 *   jedes Bild (core/bildschleier_css.py). Laedt diese Datei nicht oder
 *   wirft sie, BLEIBT der Schleier — es fehlen nur die Ausnahmen (Forensymbole
 *   bleiben dann ebenfalls verschleiert) und die Schaltflaeche.
 *   Diese Datei kann den Schleier nur in ZWEI Faellen entfernen: wenn der
 *   Server im Seitenumschlag ausdruecklich veiled=false meldet, oder wenn
 *   die Person einen Schleier aufhebt, den DIESE Datei nach einem
 *   gescheiterten Speichern nur lokal gesetzt hat (Build 775, siehe unten) —
 *   dann gilt wieder der gespeicherte, vom Server gemeldete Zustand "klar".
 *
 * DIE DREI ZUSTAENDE DER SCHALTFLAECHE (Alex, 09.10.2026)
 *   gesperrt     — Auge verschwommen + grau + blass, Klick wirkungslos,
 *                  der Kurzhinweis nennt den Grund (vom Server, wortgleich)
 *   verschleiert — Auge verschwommen, farbig; Klick schaltet aus
 *   klar         — Auge scharf, farbig; Klick schaltet ein
 *
 * REIHENFOLGE BEIM UMSCHALTEN (Bauplan §5.5)
 *   Einschalten: ZUERST die Klasse setzen (sofortiger Schutz), DANN
 *                speichern, DANN neu laden.
 *   Ausschalten: ZUERST speichern, DANN neu laden. Die Klasse wird hier nie
 *                entfernt — das tut erst die neu geladene Shell.
 *   Schlaegt das Speichern fehl, bleibt der Schleier in BEIDEN Faellen
 *   aktiv, und die Schaltflaeche zeigt den Fehler. Ein gescheitertes
 *   AUSschalten entschleiert also nie.
 *   Neu geladen wird, weil Bilder aus Stylesheets (ab Build 773 serverseitig
 *   ersetzt) erst mit dem naechsten Abruf der Stylesheets wechseln; die
 *   Scrollposition stellt scroll_memory.js wieder her (Alex: "Ja, das ist
 *   okay").
 *
 * BUILD 775 — NUR LOKAL VERSCHLEIERT (Befund 13.10.2026, D2)
 *   Scheiterte das EINschalten, stand die Klasse, der gemeldete Zustand aber
 *   blieb "klar": die Schaltflaeche zeigte "klar", ein zweiter Klick
 *   versuchte erneut EINzuschalten, und zurueck ging es nur mit F5.
 *   Jetzt gibt es einen vierten Zustand 'lokal': Klasse gesetzt, gespeichert
 *   ist "klar". Die Schaltflaeche zeigt ihn als verschleiert mit dem Hinweis
 *   "Nur lokal verschleiert — nicht gespeichert". Ein Klick hebt den
 *   lokalen Schleier auf (kein Request — es gilt wieder der gespeicherte
 *   Zustand), der naechste Klick versucht erneut zu speichern. Beim Blaettern
 *   innerhalb der Shell bleibt der lokale Schleier stehen; nach dem
 *   Neuladen gilt der gespeicherte Zustand.
 *   Der Server liefert seit Build 775 auch bei HTTP 500 den gespeicherten
 *   Zustand mit (forensic_api/bildschleier.py, _fehlerantwort).
 *
 * BUILD 775 — AUSNAHMEN AUCH IM KLAREN ZUSTAND (D1)
 *   Der Umschlag traegt 'exempt_css' jetzt immer; seiteAnwenden() setzt es
 *   in beiden Zustaenden. Die Regeln wirken nur unter html.aiw-image-veil.
 *   So bleiben Symbole und Abzeichen auch beim sofortigen Einschalten auf
 *   einer klar geladenen Seite unverschleiert.
 *
 * ANBINDUNG
 *   window.BildschleierSchalter — von toolbar.js aufgerufen:
 *     .binden(button)        beim Zeichnen der Leiste (Sektion 5)
 *     .seiteAnwenden(iv)     in _handleEnvelope VOR viewport.innerHTML
 *   Geladen VOR toolbar.js (server/shell_handler.py).
 *
 * DEBUG
 *   Ausgabelastiges Logging ueber window.forensicDebug === true (dieselbe
 *   Schaltung wie toolbar.js). Fuer PROD abschaltbar, ohne Codeaenderung.
 * ======================================================================== */

(function () {
  'use strict';

  // =========================================================================
  // KONSTANTEN
  // =========================================================================

  /** Klasse an <html>, die den Schleier einschaltet (core/bildschleier_css.py). */
  var HTML_KLASSE = 'aiw-image-veil';
  /** <style>-Element fuer die Ausnahmen der aktuellen Seite. */
  var STIL_ID = 'aiw-image-veil-page';
  /** Endpunkt (forensic_api/bildschleier.py). */
  var API = '/_forensic/image-veil';
  /** Das Zeichen der Schaltflaeche — EINE Stelle, schnell austauschbar
   *  (Alex, 09.10.2026: U+1F441). */
  var ZEICHEN = '👁';

  function _dbg() {
    if (typeof window === 'undefined') return;
    if (window.forensicDebug !== true) return;
    var a = Array.prototype.slice.call(arguments);
    a.unshift('[Bildschleier]');
    try { console.log.apply(console, a); } catch (e) { /* egal */ }
  }

  function _warn() {
    var a = Array.prototype.slice.call(arguments);
    a.unshift('[Bildschleier]');
    try { console.warn.apply(console, a); } catch (e) { /* egal */ }
  }

  // =========================================================================
  // ZUSTAND — gekapselt; nach aussen nur ueber die Methoden unten
  // =========================================================================

  /**
   * Der zuletzt bekannte Zustand. Startwert aus den data-Attributen, die
   * der Server an <html> geschrieben hat (core/bildschleier_dienst.py,
   * zustand_html_attribute). FEHLEN sie, gilt: verschleiert und gesperrt —
   * dieselbe sichere Richtung wie auf dem Server.
   */
  var _zustand = null;
  var _knopf = null;
  var _beschaeftigt = false;
  var _fehlertext = '';
  /** Build 775: Klasse steht nur lokal, gespeichert ist "klar". */
  var _lokal = false;

  function _ausHtml() {
    var el = document.documentElement;
    var d = (el && el.dataset) || {};
    if (d.imageVeilVeiled === undefined) {
      _warn('Keine data-image-veil-* Angaben an <html> — verschleiert und gesperrt.');
      return { veiled: true, locked: true, reason: 'internal_error',
               tooltip: 'Zustand unbekannt. Bilder bleiben verschleiert.' };
    }
    return {
      veiled:  d.imageVeilVeiled === '1',
      locked:  d.imageVeilLocked === '1',
      reason:  d.imageVeilReason || '',
      tooltip: d.imageVeilTooltip || '',
    };
  }

  function _zustandHolen() {
    if (_zustand === null) _zustand = _ausHtml();
    return _zustand;
  }

  function _zustandSetzen(z) {
    // Nur die bekannten Felder uebernehmen; ein Umschlag ohne Angaben
    // aendert nichts (die Shell hat bereits die Wahrheit gesetzt).
    if (!z || typeof z.veiled !== 'boolean' || typeof z.locked !== 'boolean') {
      _warn('Unvollstaendige Zustandsangabe ignoriert:', z);
      return _zustandHolen();
    }
    _zustand = { veiled: z.veiled, locked: z.locked,
                 reason: String(z.reason || ''), tooltip: String(z.tooltip || '') };
    var el = document.documentElement;
    if (el && el.dataset) {
      el.dataset.imageVeilVeiled  = z.veiled ? '1' : '0';
      el.dataset.imageVeilLocked  = z.locked ? '1' : '0';
      el.dataset.imageVeilReason  = _zustand.reason;
      el.dataset.imageVeilTooltip = _zustand.tooltip;
    }
    return _zustand;
  }

  // =========================================================================
  // DARSTELLUNG
  // =========================================================================

  /** Build 775: Kurzhinweis im Zustand 'lokal' (fester Text). */
  var TEXT_LOKAL = 'Nur lokal verschleiert — nicht gespeichert. ' +
                   'Klicken hebt den lokalen Schleier auf.';

  function _darstellen() {
    if (!_knopf) return;
    var z = _zustandHolen();
    // 'lokal' wird wie verschleiert gezeigt (die Bilder SIND verschleiert),
    // mit eigener Klasse und eigenem Hinweis.
    var verschleiert = !!z.veiled || _lokal;
    _knopf.textContent = ZEICHEN;
    _knopf.classList.toggle('is-locked', !!z.locked);
    _knopf.classList.toggle('is-veiled', !z.locked && verschleiert);
    _knopf.classList.toggle('is-clear', !z.locked && !verschleiert);
    _knopf.classList.toggle('is-local', !z.locked && _lokal);
    _knopf.classList.toggle('is-busy', _beschaeftigt);
    _knopf.classList.toggle('is-error', !!_fehlertext);
    _knopf.setAttribute('aria-pressed', verschleiert ? 'true' : 'false');
    _knopf.setAttribute('aria-disabled', z.locked || _beschaeftigt ? 'true' : 'false');
    var grund = _lokal ? TEXT_LOKAL : z.tooltip;
    var titel = _fehlertext ? (_fehlertext + ' — ' + grund) : grund;
    _knopf.title = titel;
    _knopf.setAttribute('aria-label', 'Bildschleier: ' + titel);
    _dbg('darstellen', { zustand: z, lokal: _lokal, beschaeftigt: _beschaeftigt,
                         fehler: _fehlertext });
  }

  // =========================================================================
  // SEITENAUSNAHMEN
  // =========================================================================

  /**
   * Wendet den Bildschleier-Teil eines Seitenumschlags an. MUSS vor dem
   * Einfuegen des Seiteninhalts laufen (toolbar.js _handleEnvelope).
   *   iv.veiled true  -> Klasse setzen, Ausnahmen der Seite setzen
   *   iv.veiled false -> Klasse entfernen, Ausnahmen leeren
   *   iv fehlt        -> NICHTS aendern (Warnung): die Shell hat den Zustand
   *                      gesetzt, und ohne Angabe wird nicht geraten.
   */
  function seiteAnwenden(iv) {
    var el = document.documentElement;
    var stil = document.getElementById(STIL_ID);
    if (!iv || typeof iv.veiled !== 'boolean') {
      _warn('Seitenumschlag ohne image_veil — Zustand bleibt, keine Ausnahmen.');
      if (stil) stil.textContent = '';
      return;
    }
    _zustandSetzen(iv);
    // Build 775 (D1): Ausnahmen in BEIDEN Zustaenden setzen — sie wirken nur
    // unter html.aiw-image-veil und stehen bereit, wenn sofort
    // eingeschaltet wird.
    if (!stil) {
      stil = document.createElement('style');
      stil.id = STIL_ID;
      document.head.appendChild(stil);
    }
    stil.textContent = typeof iv.exempt_css === 'string' ? iv.exempt_css : '';
    if (iv.veiled || iv.locked) {
      // Der Server meldet verschleiert: ein lokaler Schleier ist damit
      // gegenstandslos.
      _lokal = false;
      el.classList.add(HTML_KLASSE);
      _dbg('seiteAnwenden: verschleiert, Ausnahmen (Zeichen):', stil.textContent.length);
    } else if (_lokal) {
      // Build 775 (D2): lokal verschleiert bleibt beim Blaettern stehen.
      el.classList.add(HTML_KLASSE);
      _dbg('seiteAnwenden: gespeichert klar, lokal verschleiert — bleibt');
    } else {
      el.classList.remove(HTML_KLASSE);
      _dbg('seiteAnwenden: klar, Ausnahmen bereit (Zeichen):', stil.textContent.length);
    }
    _darstellen();
  }

  // =========================================================================
  // UMSCHALTEN
  // =========================================================================

  function _speichern(veiled) {
    return window.fetch(API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ veiled: veiled }),
      credentials: 'same-origin',
    }).then(function (antwort) {
      return antwort.json().catch(function () { return {}; }).then(function (daten) {
        if (!antwort.ok) {
          var e = new Error((daten && (daten.detail || daten.tooltip || daten.error))
                            || ('HTTP ' + antwort.status));
          e.daten = daten;
          throw e;
        }
        return daten;
      });
    });
  }

  /**
   * Schaltet um. Gibt ein Promise zurueck (fuer Tests); die Oberflaeche
   * wertet es nicht aus. Bei Erfolg wird neu geladen.
   */
  function umschalten() {
    var z = _zustandHolen();
    if (z.locked) {
      _dbg('umschalten: gesperrt (' + z.reason + ') — keine Wirkung');
      return Promise.resolve(false);
    }
    if (_beschaeftigt) {
      _dbg('umschalten: laeuft bereits');
      return Promise.resolve(false);
    }
    if (_lokal) {
      // Build 775 (D2): den nur lokal gesetzten Schleier aufheben. Kein
      // Request: gespeichert ist "klar", genau das gilt danach wieder.
      _lokal = false;
      _fehlertext = '';
      if (!z.veiled) document.documentElement.classList.remove(HTML_KLASSE);
      _dbg('umschalten: lokalen Schleier aufgehoben, es gilt der gespeicherte Zustand');
      _darstellen();
      return Promise.resolve(false);
    }
    var ziel = !z.veiled;
    if (ziel) {
      // Einschalten: Schutz SOFORT, vor jeder Netzwerkantwort.
      document.documentElement.classList.add(HTML_KLASSE);
    }
    _beschaeftigt = true;
    _fehlertext = '';
    _darstellen();
    _dbg('umschalten: speichere veiled=' + ziel);
    return _speichern(ziel).then(function (daten) {
      _zustandSetzen(daten);
      _dbg('umschalten: gespeichert, lade neu', daten);
      api._neuLaden();
      return true;
    }).catch(function (fehler) {
      _beschaeftigt = false;
      _fehlertext = 'Umschalten fehlgeschlagen: ' + (fehler && fehler.message);
      if (fehler && fehler.daten && typeof fehler.daten.veiled === 'boolean' &&
          typeof fehler.daten.locked === 'boolean') {
        _zustandSetzen(fehler.daten);
      }
      // Gleich was der Server meldet: nach einem Fehler bleibt die Klasse,
      // die vorher stand — und war der Wunsch "einschalten", steht sie jetzt.
      if (ziel) document.documentElement.classList.add(HTML_KLASSE);
      // Build 775 (D2): Einschalten gescheitert und gespeichert gilt (laut
      // Server bzw. mangels Antwort laut letztem Stand) "klar" -> 'lokal'.
      var nachher = _zustandHolen();
      _lokal = !!ziel && !nachher.veiled && !nachher.locked;
      _warn(_fehlertext);
      _darstellen();
      return false;
    });
  }

  // =========================================================================
  // ANBINDUNG
  // =========================================================================

  function binden(knopf) {
    if (!knopf) {
      _warn('binden: keine Schaltflaeche uebergeben.');
      return;
    }
    _knopf = knopf;
    knopf.addEventListener('click', function (ev) {
      ev.preventDefault();
      umschalten();
    });
    _darstellen();
    _dbg('binden: Schaltflaeche angebunden');
  }

  var api = {
    binden: binden,
    seiteAnwenden: seiteAnwenden,
    umschalten: umschalten,
    zustand: function () {
      var z = _zustandHolen();
      return { veiled: z.veiled, locked: z.locked, reason: z.reason, tooltip: z.tooltip,
               lokal: _lokal };
    },
    ZEICHEN: ZEICHEN,
    HTML_KLASSE: HTML_KLASSE,
    STIL_ID: STIL_ID,
    /** Austauschbar fuer Tests; in der Anwendung: Seite neu laden. */
    _neuLaden: function () { window.location.reload(); },
  };

  window.BildschleierSchalter = api;
  _dbg('geladen');
})();
