/* ===========================================================================
 * AIW · Baustelle 3 (Toolbar) · DIAGNOSE-SONDE Scrollpositions-Wiederherstellung
 * ---------------------------------------------------------------------------
 * ZWECK
 *   Diese Sonde ist KEIN Fix. Sie ist ausgabelastiger Test-Code gemaess
 *   Projekt-Debugging-Protokoll ("Erst Console-Output anfordern, dann PoC,
 *   dann Fix"). Sie instrumentiert die LAUFENDE Seite und protokolliert
 *   luekenlos, WO und WIE eine Scrollposition gespeichert und wiederhergestellt
 *   wird — damit wir die Hypothese
 *
 *       "gespeicherte relative Position (Prozent) wird mit der Hoehe der
 *        ZUVOR angezeigten Seite multipliziert statt mit der Hoehe der
 *        NEU geladenen Seite"
 *
 *   empirisch BELEGEN oder WIDERLEGEN koennen, bevor wir eine Zeile Fix
 *   schreiben. (Grundregel: keine Behauptung ohne Beleg.)
 *
 * WICHTIGER BEFUND VORAB (Beleg, Build 0.8.470, Commit 551dfa9):
 *   Im ausgelieferten Code (toolbar/toolbar.js, MD5 080bd072a48b09adc3b14990b329cea4)
 *   existiert KEIN Speicher/Wiederherstellungs-Mechanismus fuer die Fenster-
 *   Scrollposition pro Seite. Es gibt nur:
 *     - scrollIntoView(...) fuer Sprungziele (Annotationen, Fragment, Trace)
 *     - Minimap-Prozentrechnung (nur Anzeige, kein scrollTo)
 *     - annotation_sidebar.js: scrollTop-Erhalt EINER Liste (Baustelle 4, absolut)
 *   => Die vom Kollegen beobachtete Funktion kommt daher entweder aus
 *      (a) nicht eingecheckten lokalen Aenderungen, (b) dem Browser-eigenen
 *      history.scrollRestoration, oder (c) einer anderen Datei/Baustelle.
 *   Diese Sonde deckt alle drei Faelle ab und macht sichtbar, was real passiert.
 *
 * EINSATZ (wann/wo/wie)
 *   1. Haupt-Forumsfenster oeffnen (http://127.0.0.2/... ueber unseren Server).
 *   2. DevTools -> Console. Diesen gesamten Block einfuegen und mit Enter
 *      ausfuehren. Die Sonde bleibt aktiv (bis Reload des Tabs).
 *   3. Eine LANGE Forumsseite (viel Scrollhoehe) oeffnen, ca. zur Mitte
 *      scrollen.
 *   4. Auf eine KURZE andere Seite navigieren (Paginierung ">" oder ein Link).
 *   5. Mit dem Browser-Zurueck-Button (oder Pagination "<") zur langen Seite
 *      zurueck. GENAU HIER soll die Position wiederhergestellt werden.
 *   6. Gesamte Console-Ausgabe kopieren und zuruecksenden.
 *
 * WAS BEOBACHTEN
 *   - Zeilen [SAVE]  : Wird beim Seitenwechsel eine Position gespeichert?
 *                      Mit welcher Bezugshoehe (scrollHeight) wird ein evtl.
 *                      Prozentwert gebildet?
 *   - Zeilen [APPLY] : Ruft irgendetwas window.scrollTo / scrollTop-Setter auf?
 *                      Mit welchem ABSOLUTEN Zielwert — und wie hoch ist die
 *                      Seite in DIESEM Moment schon (Layout fertig?)?
 *   - Zeilen [HEIGHT]: Entwicklung der Seitenhoehe nach dem Laden (0ms / rAF /
 *                      120ms / 400ms). Zeigt, ob ein Restore zu frueh feuert,
 *                      solange die neue Seite noch die ALTE (oder 0) Hoehe hat.
 *   - Zeilen [STORE] : Jeder Lese/Schreibzugriff auf session/localStorage.
 *
 * SICHERHEIT / RUECKBAU
 *   Rein additiv, wrappt Funktionen und stellt sie beim Tab-Reload automatisch
 *   zurueck (kein persistenter Eingriff). Keine Netzwerkaufrufe, keine DB-
 *   Schreibvorgaenge. Kann jederzeit mit  window.__aiwScrollProbe.stop()  beendet
 *   werden.
 * ===========================================================================*/
(function () {
  'use strict';

  // --- Konfiguration -------------------------------------------------------
  // DEBUG bewusst auf true (Sonde IST das Debugging). Fuer PROD wird sie nicht
  // ausgeliefert, sondern nur waehrend der Fehlersuche in die Console gepastet.
  var DEBUG = true;
  var TAG   = '%c[AIW-ScrollProbe]';
  var CSS   = 'color:#0a7; font-weight:bold';

  // Mehrfach-Injektion vermeiden: alte Sonde sauber zurueckbauen.
  if (window.__aiwScrollProbe && typeof window.__aiwScrollProbe.stop === 'function') {
    window.__aiwScrollProbe.stop();
  }

  // --- kleine Hilfen -------------------------------------------------------
  function log()   { if (DEBUG) console.log.apply(console, arguments); }
  function group(t){ if (DEBUG) console.group(TAG + ' ' + t, CSS); }
  function groupEnd(){ if (DEBUG) console.groupEnd(); }

  // Aktuelle Mess-Kennzahlen der Seite in EINEM Objekt — so sehen wir bei
  // jedem Ereignis Position UND Bezugsgroessen nebeneinander.
  function metrics() {
    var de = document.documentElement;
    return {
      scrollY:         window.scrollY,
      body_scrollH:    document.body ? document.body.scrollHeight : -1,
      doc_scrollH:     de ? de.scrollHeight : -1,
      innerHeight:     window.innerHeight,
      // relative Position, wie ein Prozent-Mechanismus sie SPEICHERN wuerde:
      pctBody: document.body && document.body.scrollHeight > 0
                 ? +(window.scrollY / document.body.scrollHeight * 100).toFixed(3) : null,
      url: location.pathname + location.search
    };
  }

  // Zeitstempel relativ zum Sondenstart (monoton, unabhaengig von Wanduhr).
  var t0 = (window.performance && performance.now) ? performance.now() : 0;
  function ts() {
    var now = (window.performance && performance.now) ? performance.now() : 0;
    return '+' + (now - t0).toFixed(0) + 'ms';
  }

  // Sammelt die Restore-Funktionen zum spaeteren Zurueckbau.
  var _restore = [];

  // =========================================================================
  // 1) window.scrollTo / window.scroll ueberwachen  -> [APPLY]
  //    Jeder programmatische Scroll landet hier. Wir loggen Zielwert PLUS die
  //    aktuelle Seitenhoehe: So sehen wir, ob ein absoluter Zielwert zu einer
  //    Seite passt, die noch gar nicht ihre endgueltige Hoehe hat.
  // =========================================================================
  ['scrollTo', 'scroll'].forEach(function (fn) {
    var orig = window[fn];
    if (typeof orig !== 'function') return;
    window[fn] = function () {
      var y = (arguments.length === 1 && arguments[0] && typeof arguments[0] === 'object')
                ? arguments[0].top : arguments[1];
      group('[APPLY] window.' + fn + '() ' + ts());
      log('  Zielwert y =', y);
      log('  Seiten-Metrik JETZT:', metrics());
      console.trace('  Aufruf-Stack (wer ruft?)');
      groupEnd();
      return orig.apply(this, arguments);
    };
    _restore.push(function () { window[fn] = orig; });
  });

  // =========================================================================
  // 2) scrollTop-Setter auf documentElement & body ueberwachen -> [APPLY]
  //    Manche Restore-Implementierungen setzen scrollTop direkt statt scrollTo.
  // =========================================================================
  [['documentElement', document.documentElement], ['body', document.body]].forEach(function (pair) {
    var name = pair[0], el = pair[1];
    if (!el) return;
    var proto = Object.getPrototypeOf(el);
    var desc  = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollTop')
             || Object.getOwnPropertyDescriptor(proto, 'scrollTop');
    if (!desc || !desc.set) return;
    try {
      Object.defineProperty(el, 'scrollTop', {
        configurable: true,
        get: function () { return desc.get.call(el); },
        set: function (v) {
          group('[APPLY] ' + name + '.scrollTop = ' + v + '  ' + ts());
          log('  Seiten-Metrik JETZT:', metrics());
          console.trace('  Aufruf-Stack (wer ruft?)');
          groupEnd();
          return desc.set.call(el, v);
        }
      });
      _restore.push(function () {
        // Instanz-Property wieder entfernen -> Prototyp-Getter/Setter greift.
        delete el.scrollTop;
      });
    } catch (e) { log(TAG + ' scrollTop-Hook fehlgeschlagen fuer ' + name, CSS, e); }
  });

  // =========================================================================
  // 3) Navigation abgreifen -> [SAVE]
  //    Vor JEDEM loadPage() halten wir fest, wo der Balken steht und mit
  //    welcher Bezugshoehe ein Prozentwert gebildet WUERDE. Das ist der Wert,
  //    der laut Hypothese spaeter mit der FALSCHEN (naemlich dieser hier,
  //    der alten) Hoehe zurueckgerechnet wird.
  // =========================================================================
  (function hookLoadPage() {
    var nav = window.ForensicToolbar && window.ForensicToolbar.navigation;
    if (nav && typeof nav.loadPage === 'function') {
      var orig = nav.loadPage;
      nav.loadPage = function (url, pushState, method) {
        group('[SAVE] vor loadPage("' + url + '") ' + ts());
        log('  Position der VERLASSENEN Seite:', metrics());
        log('  => Falls hier ein Prozentwert gemerkt wird, ist seine Bezugs-');
        log('     hoehe body_scrollH der ALTEN Seite. Beim Restore MUSS aber');
        log('     durch die Hoehe der NEUEN Zielseite geteilt/multipliziert werden.');
        groupEnd();
        return orig.apply(this, arguments);
      };
      _restore.push(function () { nav.loadPage = orig; });
      log(TAG + ' loadPage-Hook aktiv.', CSS);
    } else {
      log(TAG + ' ForensicToolbar.navigation.loadPage NICHT gefunden — ' +
          'Navigation laeuft evtl. anders. [SAVE]-Zeilen kommen dann aus popstate.', CSS);
    }
  })();

  // popstate (Zurueck-Button) zusaetzlich beobachten — dort passiert der Restore.
  window.addEventListener('popstate', function (e) {
    group('[NAV] popstate (Zurueck/Vor) ' + ts());
    log('  history.state =', e.state);
    log('  Metrik im popstate-Moment:', metrics());
    groupEnd();
  }, true);

  // =========================================================================
  // 4) Hoehenentwicklung nach page:loaded -> [HEIGHT]
  //    Kernbeleg fuer die "zu frueh"-Variante der Hypothese: Wenn ein Restore
  //    feuert, BEVOR die neue Seite ihre echte scrollHeight hat, landet der
  //    absolute Zielwert zwangslaeufig falsch.
  // =========================================================================
  function probeHeights(reason) {
    log(TAG + ' [HEIGHT] ' + reason + ' — sofort ' + ts(), CSS, metrics());
    requestAnimationFrame(function () {
      log(TAG + ' [HEIGHT] ' + reason + ' — nach rAF ' + ts(), CSS, metrics());
    });
    setTimeout(function () {
      log(TAG + ' [HEIGHT] ' + reason + ' — nach 120ms ' + ts(), CSS, metrics());
    }, 120);
    setTimeout(function () {
      log(TAG + ' [HEIGHT] ' + reason + ' — nach 400ms ' + ts(), CSS, metrics());
    }, 400);
  }
  var evt = window.ForensicToolbar && window.ForensicToolbar.events;
  if (evt && typeof evt.on === 'function') {
    evt.on('page:loaded', function (d) {
      probeHeights('page:loaded(' + (d && d.url) + ')');
    });
    log(TAG + ' page:loaded-Hook aktiv.', CSS);
  } else {
    log(TAG + ' ForensicToolbar.events NICHT gefunden — [HEIGHT] nur ueber popstate.', CSS);
    window.addEventListener('popstate', function () { probeHeights('popstate'); }, true);
  }

  // =========================================================================
  // 5) Storage-Zugriffe beobachten -> [STORE]
  //    Falls die Position doch irgendwo (session/localStorage) abgelegt wird,
  //    sehen wir Key + Wert und koennen die Bezugshoehe im Wert erkennen.
  // =========================================================================
  ['sessionStorage', 'localStorage'].forEach(function (store) {
    var s;
    try { s = window[store]; } catch (e) { return; }
    if (!s) return;
    ['setItem', 'getItem'].forEach(function (m) {
      var orig = s[m];
      s[m] = function (k, v) {
        if (/scroll|pos|pct|percent|ratio|y/i.test(String(k))) {
          log(TAG + ' [STORE] ' + store + '.' + m + '("' + k + '"'
              + (m === 'setItem' ? ', "' + v + '"' : '') + ') ' + ts(), CSS);
        }
        return orig.apply(this, arguments);
      };
      _restore.push(function () { s[m] = orig; });
    });
  });

  // --- Steuer-API + Startmeldung ------------------------------------------
  window.__aiwScrollProbe = {
    stop: function () {
      _restore.forEach(function (f) { try { f(); } catch (e) {} });
      _restore = [];
      log(TAG + ' gestoppt und zurueckgebaut.', CSS);
    },
    metrics: metrics
  };

  group('AKTIV — Sonde installiert ' + ts());
  log('  Build-Bezug: erwarte toolbar.js MD5 080bd072a48b09adc3b14990b329cea4');
  log('  Startmetrik:', metrics());
  log('  Jetzt: lange Seite -> scrollen -> wegnavigieren -> ZURUECK. Dann Console kopieren.');
  log('  Beenden mit: window.__aiwScrollProbe.stop()');
  groupEnd();
})();
