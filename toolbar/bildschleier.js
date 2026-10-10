/* ===========================================================================
 * bildschleier.js
 * IT-Forensisches Ermittlungswerkzeug — Bildschleier (Build 772)
 * ---------------------------------------------------------------------------
 * Version: v0.8.772 · Build: 772 · 2026-10-09
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
 *   Diese Datei kann den Schleier nur in EINEM Fall entfernen: wenn der
 *   Server im Seitenumschlag ausdruecklich veiled=false meldet.
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

  function _darstellen() {
    if (!_knopf) return;
    var z = _zustandHolen();
    _knopf.textContent = ZEICHEN;
    _knopf.classList.toggle('is-locked', !!z.locked);
    _knopf.classList.toggle('is-veiled', !z.locked && !!z.veiled);
    _knopf.classList.toggle('is-clear', !z.locked && !z.veiled);
    _knopf.classList.toggle('is-busy', _beschaeftigt);
    _knopf.classList.toggle('is-error', !!_fehlertext);
    _knopf.setAttribute('aria-pressed', z.veiled ? 'true' : 'false');
    _knopf.setAttribute('aria-disabled', z.locked || _beschaeftigt ? 'true' : 'false');
    var titel = _fehlertext ? (_fehlertext + ' — ' + z.tooltip) : z.tooltip;
    _knopf.title = titel;
    _knopf.setAttribute('aria-label', 'Bildschleier: ' + titel);
    _dbg('darstellen', { zustand: z, beschaeftigt: _beschaeftigt, fehler: _fehlertext });
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
    if (iv.veiled) {
      el.classList.add(HTML_KLASSE);
      if (!stil) {
        stil = document.createElement('style');
        stil.id = STIL_ID;
        document.head.appendChild(stil);
      }
      stil.textContent = typeof iv.exempt_css === 'string' ? iv.exempt_css : '';
      _dbg('seiteAnwenden: verschleiert, Ausnahmen (Zeichen):', stil.textContent.length);
    } else {
      if (stil) stil.textContent = '';
      el.classList.remove(HTML_KLASSE);
      _dbg('seiteAnwenden: klar');
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
      if (fehler && fehler.daten && typeof fehler.daten.veiled === 'boolean') {
        _zustandSetzen(fehler.daten);
      }
      // Gleich was der Server meldet: nach einem Fehler bleibt die Klasse,
      // die vorher stand — und war der Wunsch "einschalten", steht sie jetzt.
      if (ziel) document.documentElement.classList.add(HTML_KLASSE);
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
      return { veiled: z.veiled, locked: z.locked, reason: z.reason, tooltip: z.tooltip };
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
