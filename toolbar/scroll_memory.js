/* ===========================================================================
 * scroll_memory.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 3 (Toolbar der Hauptseite)
 * ---------------------------------------------------------------------------
 * Version: v0.8.688 · Build: 688 · 2026-08-11
 *
 * ZWECK
 *   Merkt sich pro Forum-Seite (per kanonischer URL) die Lese-Position und
 *   stellt sie beim Zurueckkehren wieder her. Ab Build 473 INHALTSBASIERT:
 *   primaer ueber einen stabilen HTML-Anker (Beitrag 'p<id>' o.ae.) plus
 *   kleinen Pixel-Offset; nur wo kein Anker vorhanden ist, dient die absolute
 *   Y-Position als Rueckfallebene ("Anker primaer + Y-Fallback").
 *
 * ENTWICKLUNG
 *   Build 471: Erstimplementierung, ausschliesslich absolute Y-Position.
 *   Build 473: Anker-primaer + Y-Fallback. Persistenzschema additiv um
 *              {anchor, offset} erweitert — 471er-Datensaetze ohne Anker
 *              bleiben lesbar und laufen ueber den Y-Pfad.
 *   Build 688: URI-ANKER HAT VORRANG vor der gemerkten Position
 *              (Vorgang 74a95cba-21ba-4fc8-b882-afd44a887c17). Siehe unten.
 *
 * WARUM ANKER-PRIMAER (belegt durch DevTools-Messungen im Feld):
 *   F1 VERFUEGBARKEIT: Lange Thread-Seiten tragen hunderte stabile Anker
 *      (gemessen: 283x 'p<id>' auf einer pmsnew-topic-Seite); Uebersichts-/
 *      Suchseiten haben keine (gemessen: 0 auf pmsnew.php) -> dort Y-Fallback.
 *      An realen Verlass-Positionen ist der Offset klein (gemessen 216-236 px).
 *   F2 REFLOW/ZOOM: Die ABSOLUTE Position eines Ankers wandert waehrend des
 *      Ladens erheblich (gemessen absTop 2534 -> 1119; Hoehe 124838 -> 101454),
 *      weil seitenspezifisches CSS/Bilder asynchron nachladen. Absolute Y ist
 *      in diesem Fenster unzuverlaessig. Das Anker-Element beim Wiederherstellen
 *      NEU EINZULESEN und den kleinen Offset zu addieren, trifft dagegen exakt —
 *      und ist zugleich zoom- und viewportgroessen-unabhaengig (inhaltsbasiert).
 *
 * ---------------------------------------------------------------------------
 * BUILD 688 — VORRANG DES URI-ANKERS (Vorgang 74a95cba)
 *
 *   BEFUND (belegt am Quelltext von Build 686):
 *     toolbar.js/_handleEnvelope Z. 1933-1938 scrollt bei vorhandenem
 *     envelope.fragment per scrollIntoView() zum Anker. ERST DANACH wird
 *     Z. 1951-1954 'page:loaded' ausgesendet. Dieses Modul hat bis Build 686
 *     in _onPageLoaded() ausschliesslich auf den GEMERKTEN Datensatz gesehen
 *     und dessen Position nach dem Settle-Warten per window.scrollTo()
 *     angewandt. Beide Bewegungen sind also nacheinander gelaufen, die
 *     zweite hat die erste ueberschrieben — genau der gemeldete Ablauf
 *     ("springt zuerst an den Anker, nach dem Laden zur alten Position").
 *
 *   ENTSCHEIDUNG: Der URI-Anker ist eine AUSDRUECKLICHE Willensaeusserung
 *     ("zeige mir DIESEN Beitrag") und schlaegt die beilaeufig entstandene
 *     Erinnerung an den letzten Besuch. Er gilt aber nur, wenn er auf der
 *     Seite auch WIRKLICH vorhanden ist — sonst waere die Folge, dass eine
 *     tote Sprungmarke die gemerkte Position stillschweigend verwirft.
 *     Ist der Anker tot, laeuft unveraendert der bisherige Weg.
 *
 *   WARUM DIESES MODUL DIE BEWEGUNG UEBERNIMMT und nicht einfach schweigt:
 *     Die Alternative waere gewesen, den Restore nur zu unterdruecken und
 *     scrollIntoView() aus toolbar.js stehen zu lassen. Das waere nach dem
 *     Wortlaut des Vorgangs zulaessig ("entweder keine"), traefe aber
 *     nachweislich daneben: scrollIntoView() laeuft unmittelbar nach
 *     viewport.innerHTML, also in genau dem Zeitfenster, fuer das Beleg F2
 *     eine Wanderung der Ankerlage um ueber 1400 px misst. Dieses Modul hat
 *     mit _restoreWhenSettled() bereits die erprobte Antwort darauf. Der
 *     Anker wird deshalb NACH dem Settle-Warten erneut eingelesen und
 *     angefahren; das spaetere, harte window.scrollTo() bricht eine ggf. noch
 *     laufende weiche Animation von scrollIntoView() ab (CSSOM-View: ein neuer
 *     Scroll beendet einen laufenden). toolbar.js bleibt unangetastet — das
 *     haelt die Aenderung aus fremden Baustellen heraus.
 *
 *   WOHER DER ANKER KOMMT (drei Quellen, in dieser Reihenfolge):
 *     1. d.fragment aus dem 'page:loaded'-Ereignis, falls eine spaetere
 *        Fassung von toolbar.js es mitliefert (heute nicht der Fall).
 *     2. ForensicToolbar.state.get('fragment'). toolbar.js Z. 1894 setzt
 *        diesen Wert bei JEDER Navigation neu (envelope.fragment || null),
 *        und zwar VOR dem Aussenden von 'page:loaded' (Z. 1951). Das ist die
 *        tragende Quelle. Sie deckt zusaetzlich den Fall ab, in dem der
 *        Server den Anker erst aus einem Alias ableitet (blob_handler.py
 *        Z. 309-313: '?pid=12345' -> 'p12345') — dort steht im Adressfeld
 *        gar kein '#'.
 *     3. window.location.hash als Rueckfallebene. Sie traegt den Fall
 *        "Seite mit #-Anker neu geladen": toolbar.js Z. 8393 laedt die
 *        Startseite mit location.pathname + location.search und laesst den
 *        Hash weg, der Server sieht ihn also nie und envelope.fragment
 *        bleibt leer. Das Adressfeld traegt ihn aber weiterhin.
 *        (Dass toolbar.js den Hash dort und im popstate-Zweig Z. 2224
 *        fallenlaesst, ist ein eigener Befund und in diesem Build NICHT
 *        angefasst — er ist im Vorgang vermerkt.)
 *
 *   OBERKANTE: Der Anker wird NICHT auf y=0 gesetzt, sondern unter die fest
 *     eingeblendeten Leisten. toolbar.css Z. 112-116 setzt #forensic-toolbar
 *     auf position:fixed/top:0/z-index:9999, Z. 1524 ff. #forensic-hintbar
 *     ebenso darunter. Ein Ziel von exakt absTop haette den gesuchten Beitrag
 *     hinter der Leiste versteckt. Gemessen wird die Unterkante zur Laufzeit
 *     (nicht 62/28 fest verdrahtet), weil die Hinweiszeile ein- und
 *     ausklappbar ist und die Leistenhoehe damit veraenderlich ist.
 *
 * VERFAHREN
 *   SAVE:   Laufend beim Scrollen wird nur die (billige) Y-Position gemerkt.
 *           Am tatsaechlichen Verlass-Zeitpunkt (Klick/popstate/Entladen) wird
 *           zusaetzlich der Anker am oberen sichtbaren Inhaltsrand bestimmt
 *           (per elementFromPoint + Aufstieg zum stabilen id-Vorfahren — EINE
 *           Messung, kein Scan aller Elemente) und persistiert.
 *   WAIT:   Nach 'page:loaded' wird gewartet, bis document.scrollHeight ueber
 *           mehrere Frames stabil ist (Notbremse MAX_WAIT_MS) — erst dann steht
 *           die Ankerposition fest (Beleg F2).
 *   APPLY:  Ziel = anker.absTop(jetzt) + offset; ohne Anker: skalierte Y.
 *           Auf den gueltigen Bereich geklemmt, dann window.scrollTo.
 *           Optional (bildlastige Seiten): einmalige Nachkorrektur bei
 *           window.load, sofern der Nutzer seither nicht selbst gescrollt hat.
 *   VORRANG (Build 688): Liegt ein URI-Anker vor und ist er im DOM
 *           auffindbar, wird STATT des gemerkten Datensatzes ein
 *           Ersatzdatensatz {anchor:<fragment>, fromFragment:true} durch
 *           dieselbe WAIT/APPLY-Strecke geschickt. Der gemerkte Datensatz
 *           bleibt dabei unangetastet im Speicher stehen.
 *
 * PERSISTENZ: localStorage (Schluessel aiw:scrollpos:v1) — NICHT in einer DB
 *   (reiner UI-Zustand; kein Migrationsvorbehalt zum Stichtag 01.07.2026;
 *   ueberlebt Reload). LRU-Deckel MAX_ENTRIES. Browser-eigene
 *   history.scrollRestoration wird auf 'manual' gesetzt.
 *   Build 688 aendert das Schema NICHT: 'fromFragment' ist ein reines
 *   Laufzeitkennzeichen des Ersatzdatensatzes und wird nie geschrieben.
 *
 * MODULARITAET (Grundregel 10): eigene Datei, gekapselte Klasse ScrollMemory.
 *   Reine Entscheidungsfunktionen sind statische Methoden und werden fuer die
 *   Regressionstests exportiert (module.exports).
 *
 * JS-Gebote: IIFE + 'use strict'; DEV-Logging per window.forensicDebug (PROD
 *   still); ausfuehrliche Kommentare; Klasse/Zustand gekapselt.
 * ===========================================================================*/
(function () {
  'use strict';

  // --- Standardkonfiguration ----------------------------------------------
  var DEFAULTS = {
    STORAGE_KEY:      'aiw:scrollpos:v1', // Schema additiv erweitert (abwaertskompatibel)
    MAX_ENTRIES:      300,                // LRU-Deckel gegen unbegrenztes Wachsen
    STABLE_FRAMES:    4,                  // so viele Frames konstante Hoehe = "gesetzt"
    MAX_WAIT_MS:      1000,               // Notbremse fuer das Settle-Warten
    RESTORE_MIN_PX:   8,                  // darunter lohnt kein Y-Restore
    FOLD_SAMPLE_PAD:  2,                  // Sampling-Abstand unter dem Inhaltsrand (px)
    REASSERT_ON_LOAD: true,               // einmalige Nachkorrektur bei window.load
    // Build 688: IDs der fest eingeblendeten Leisten am oberen Rand.
    // Ihre Unterkante bestimmt, wie weit ein per URI-Anker angefahrenes
    // Element nach unten versetzt werden muss, damit es sichtbar bleibt.
    OVERLAY_IDS:      ['forensic-toolbar', 'forensic-hintbar']
  };

  // Stabile, inhaltsabgeleitete Anker-IDs (aus der DB, ladefest). Bewusst eng.
  // Beleg: viewtopic0.php -> Beitrags-Container 'p<postid>'; Uebersichtszeilen
  // 'forum<id>'/'topic<id>'. Synthetische '_vt_<rnd>'-IDs sind AUSGESCHLOSSEN.
  var STABLE_ID_RE = /^(p\d+|forum\d+|topic\d+|pid\d+)$/;

  // =========================================================================
  // REINE HELFER (ohne Seiteneffekte) — direkt testbar (Grundregel 3).
  // =========================================================================

  function isStableId(id) {
    return typeof id === 'string' && STABLE_ID_RE.test(id);
  }

  /**
   * Build 688: Ist der Anker eines Datensatzes benutzbar?
   *
   * Fuer GEMERKTE Datensaetze gilt weiterhin die enge Positivliste
   * STABLE_ID_RE — dort hat niemand den Anker ausgewaehlt, er wurde per
   * elementFromPoint aufgesammelt, und eine synthetische '_vt_<rnd>'-ID
   * waere beim naechsten Abruf eine andere.
   *
   * Fuer den URI-Anker gilt sie NICHT: Er ist vom Ermittler bzw. vom
   * verlinkenden Beitrag ausdruecklich benannt, und das Forum vergibt
   * Sprungmarken auch ausserhalb des 'p<id>'-Schemas (z. B. Namensanker in
   * aelteren Vorlagen). Ihn an der Positivliste zu messen hiesse, eine
   * gueltige, im DOM nachweisbar vorhandene Sprungmarke zu verwerfen —
   * das waere eine stille Auslassung (GR1).
   */
  function anchorUsable(entry) {
    if (!entry || typeof entry.anchor !== 'string' || !entry.anchor) return false;
    if (entry.fromFragment === true) return true;
    return isStableId(entry.anchor);
  }

  /**
   * Build 688: '#p12345' / 'p12345' -> 'p12345'; alles Unbrauchbare -> null.
   * Bewusst OHNE decodeURIComponent — das Entschluesseln gehoert zur
   * DOM-Suche (dort werden beide Schreibweisen probiert), nicht hierher.
   */
  function normalizeFragment(fragment) {
    if (typeof fragment !== 'string') return null;
    var id = fragment.charAt(0) === '#' ? fragment.slice(1) : fragment;
    return id ? id : null;
  }

  /**
   * Build 688: Ersatzdatensatz aus einem URI-Anker.
   * offset bleibt hier 0 — der tatsaechliche Versatz unter die fixen Leisten
   * wird erst beim Anwenden gemessen (_computeTarget), weil die Hinweiszeile
   * zwischen Planung und Anwendung ein- oder ausgeklappt werden kann.
   */
  function fragmentEntry(fragment) {
    var id = normalizeFragment(fragment);
    if (!id) return null;
    return { anchor: id, offset: 0, fromFragment: true };
  }

  /** Zielposition auf [0, scrollHeight-innerHeight] klemmen. */
  function clampTarget(target, scrollHeight, innerHeight) {
    var max = Math.max(0, (scrollHeight || 0) - (innerHeight || 0));
    if (!(target > 0)) return 0;
    return Math.min(target, max);
  }

  /** Zielposition an geaenderte Zoomstufe anpassen (Best-Effort, nur Y-Pfad). */
  function scaleForZoom(y, savedDpr, currentDpr) {
    if (!savedDpr || !currentDpr || savedDpr === currentDpr) return y;
    return y * (currentDpr / savedDpr);
  }

  /** Absolute Zielposition aus Ankerlage + Offset. */
  function anchorTarget(anchorAbsTopNow, offset) {
    return anchorAbsTopNow + (offset || 0);
  }

  /** Y-Restore nur oberhalb der Mindestschwelle sinnvoll. */
  function shouldRestore(target, minPx) {
    return typeof target === 'number' && isFinite(target) && target > minPx;
  }

  /** Gibt es ueberhaupt etwas wiederherzustellen (Anker ODER brauchbare Y)? */
  function hasRestore(entry, minPx) {
    if (!entry) return false;
    if (anchorUsable(entry)) return true;
    return shouldRestore(entry.y, minPx);
  }

  /**
   * Kern-Entscheidung: bestimmt das (geklemmte) Ziel und den benutzten Pfad.
   * @param {Object} entry           gespeicherter Datensatz {y,dpr,anchor?,offset?}
   *                                 oder Ersatzdatensatz {anchor,offset,fromFragment}
   * @param {number|null} anchorAbsTopNow  aktuelle absolute Ankerlage (px) oder null
   * @param {number} curDpr          aktuelle devicePixelRatio
   * @param {number} scrollHeight    document.documentElement.scrollHeight
   * @param {number} innerHeight     window.innerHeight
   * @param {number} minPx           RESTORE_MIN_PX
   * @returns {{y:number, via:('fragment'|'anchor'|'y'|'none')}}
   *
   * Build 688: Der Ersatzdatensatz aus dem URI-Anker meldet sich als
   * via='fragment' zurueck. Das ist KEIN eigener Rechenweg (er ist mit dem
   * Anker-Pfad identisch), sondern dient der Nachvollziehbarkeit im
   * DEV-Protokoll: an der Zeile ist ablesbar, WARUM die Seite dort steht.
   * Findet sich der URI-Anker im DOM nicht mehr (anchorAbsTopNow === null),
   * faellt der Ersatzdatensatz auf 'none' — er traegt kein y. Damit bleibt
   * die Seite dort stehen, wo der Browser sie hingestellt hat; es wird
   * ausdruecklich NICHT ersatzweise die gemerkte Position angefahren, denn
   * diese Entscheidung ist bereits in _onPageLoaded gefallen.
   */
  function resolveTarget(entry, anchorAbsTopNow, curDpr, scrollHeight, innerHeight, minPx) {
    if (anchorUsable(entry) && typeof anchorAbsTopNow === 'number') {
      var raw = anchorTarget(anchorAbsTopNow, entry.offset);
      return {
        y:   clampTarget(raw, scrollHeight, innerHeight),
        via: entry.fromFragment === true ? 'fragment' : 'anchor'
      };
    }
    if (entry && shouldRestore(entry.y, minPx)) {
      var scaled = scaleForZoom(entry.y, entry.dpr, curDpr);
      return { y: clampTarget(scaled, scrollHeight, innerHeight), via: 'y' };
    }
    return { y: 0, via: 'none' };
  }

  /** Settle-Kriterium: genug stabile Frames ODER Notbremse. */
  function isSettled(stableFrames, elapsedMs, cfg) {
    return stableFrames >= cfg.STABLE_FRAMES || elapsedMs >= cfg.MAX_WAIT_MS;
  }

  /** LRU-Beschneidung auf maxEntries (juengste behalten); ohne Mutation. */
  function pruneStore(store, maxEntries) {
    var keys = Object.keys(store || {});
    if (keys.length <= maxEntries) {
      var copy = {};
      keys.forEach(function (k) { copy[k] = store[k]; });
      return copy;
    }
    keys.sort(function (a, b) {
      return ((store[b] && store[b].t) || 0) - ((store[a] && store[a].t) || 0);
    });
    var kept = {};
    keys.slice(0, maxEntries).forEach(function (k) { kept[k] = store[k]; });
    return kept;
  }

  /** JSON-Parsen mit Fallback auf {} (nie werfen). */
  function parseStore(raw) {
    if (!raw) return {};
    try {
      var obj = JSON.parse(raw);
      return (obj && typeof obj === 'object') ? obj : {};
    } catch (e) { return {}; }
  }

  // =========================================================================
  // KLASSE ScrollMemory
  // =========================================================================

  function ScrollMemory(opts) {
    opts = opts || {};
    this._win     = opts.win || (typeof window !== 'undefined' ? window : null);
    this._storage = opts.storage || (this._win && this._win.localStorage) || null;

    this._cfg = {};
    var k;
    for (k in DEFAULTS) { if (DEFAULTS.hasOwnProperty(k)) this._cfg[k] = DEFAULTS[k]; }
    if (opts.cfg) { for (k in opts.cfg) { if (opts.cfg.hasOwnProperty(k)) this._cfg[k] = opts.cfg[k]; } }

    this._mem        = this._loadStore();
    this._currentUrl = this._win ? (this._win.location.pathname + this._win.location.search) : '';
    this._restoring  = false;
    this._scrollRaf  = 0;
    this._detached   = false;
    this._listeners  = [];
    this._pageLoadedFn = null;
    this._prevScrollRestoration = null;
    this._loadReassertFn = null;   // aktuell registrierter window.load-Handler
    this._lastAppliedY   = null;   // fuer die "hat der Nutzer gescrollt?"-Pruefung
  }

  // Statische Helfer (Tests + interne Nutzung).
  ScrollMemory.isStableId        = isStableId;
  ScrollMemory.anchorUsable      = anchorUsable;      // Build 688
  ScrollMemory.normalizeFragment = normalizeFragment; // Build 688
  ScrollMemory.fragmentEntry     = fragmentEntry;     // Build 688
  ScrollMemory.clampTarget   = clampTarget;
  ScrollMemory.scaleForZoom  = scaleForZoom;
  ScrollMemory.anchorTarget  = anchorTarget;
  ScrollMemory.shouldRestore = shouldRestore;
  ScrollMemory.hasRestore    = hasRestore;
  ScrollMemory.resolveTarget = resolveTarget;
  ScrollMemory.isSettled     = isSettled;
  ScrollMemory.pruneStore    = pruneStore;
  ScrollMemory.parseStore    = parseStore;
  ScrollMemory.DEFAULTS      = DEFAULTS;

  // --- interne Hilfen ------------------------------------------------------

  ScrollMemory.prototype._dbg = function () {
    if (!this._win || this._win.forensicDebug !== true) return;
    var args = Array.prototype.slice.call(arguments);
    args.unshift('[AIW-ScrollMemory]');
    if (this._win.console && this._win.console.log) this._win.console.log.apply(this._win.console, args);
  };

  ScrollMemory.prototype._now = function () {
    return (this._win && this._win.performance && this._win.performance.now)
      ? this._win.performance.now() : Date.now();
  };

  ScrollMemory.prototype._loadStore = function () {
    if (!this._storage) return {};
    try { return parseStore(this._storage.getItem(this._cfg.STORAGE_KEY)); }
    catch (e) { return {}; }
  };

  ScrollMemory.prototype._persist = function () {
    if (!this._storage) return;
    this._mem = pruneStore(this._mem, this._cfg.MAX_ENTRIES);
    try { this._storage.setItem(this._cfg.STORAGE_KEY, JSON.stringify(this._mem)); }
    catch (e) { this._dbg('persist fehlgeschlagen:', e && e.message); }
  };

  /**
   * Anker am oberen sichtbaren Inhaltsrand bestimmen. Nutzt elementFromPoint
   * (EINE Hit-Test-Messung) statt eines Scans aller id-Elemente — vermeidet
   * den teuren Forced-Reflow auf Seiten mit hunderten Ankern.
   * @returns {{id:string, offset:number}|null}
   */
  ScrollMemory.prototype._detectAnchor = function () {
    var win = this._win, doc = win && win.document;
    if (!doc || typeof doc.elementFromPoint !== 'function') return null;

    // Oberer Inhaltsrand: Oberkante des Viewport-Containers (unter der fixen
    // Toolbar), leicht nach innen versetzt.
    var vp = doc.getElementById('forensic-viewport');
    var foldY = (vp ? Math.max(0, vp.getBoundingClientRect().top) : 0) + this._cfg.FOLD_SAMPLE_PAD;
    var vw = win.innerWidth || 1000;
    var x = Math.max(2, Math.min(Math.floor(vw / 2), vw - 2));

    var el = doc.elementFromPoint(x, foldY);
    var steps = 0;
    while (el && el !== doc.body && el !== doc.documentElement && steps < 40) {
      if (el.id && isStableId(el.id)) {
        // Offset = wie weit der Inhaltsrand UNTER der Ankerkante liegt.
        // (client-0-basiert; der Toolbar-/Fold-Term kuerzt sich beim Restore heraus.)
        var rectTop = el.getBoundingClientRect().top;
        return { id: el.id, offset: Math.round(-rectTop) };
      }
      el = el.parentElement;
      steps++;
    }
    return null;
  };

  // -----------------------------------------------------------------------
  // Build 688: URI-Anker — Quelle, DOM-Suche, Leistenhoehe
  // -----------------------------------------------------------------------

  /**
   * Aktuellen URI-Anker ermitteln. Reihenfolge und Begruendung siehe
   * Dateikopf, Abschnitt "WOHER DER ANKER KOMMT".
   * @param {Object} d  Nutzlast des 'page:loaded'-Ereignisses (darf leer sein)
   * @returns {string|null} normalisierter Anker ohne '#'
   */
  ScrollMemory.prototype._activeFragment = function (d) {
    var win = this._win;
    if (!win) return null;

    // (1) Direkt aus dem Ereignis — heute nicht belegt, aber vorgesehen.
    if (d && typeof d.fragment === 'string') {
      var fromEvent = normalizeFragment(d.fragment);
      if (fromEvent) return fromEvent;
    }

    // (2) Zustand der Toolbar. Tragende Quelle; deckt auch Server-Aliasse ab.
    var FT = win.ForensicToolbar;
    if (FT && FT.state && typeof FT.state.get === 'function') {
      try {
        var fromState = normalizeFragment(FT.state.get('fragment'));
        if (fromState) return fromState;
      } catch (e) { /* Zustand nicht lesbar — naechste Quelle */ }
    }

    // (3) Adressfeld. Traegt den Fall "Seite mit #-Anker neu geladen".
    try {
      var fromHash = normalizeFragment(win.location && win.location.hash);
      if (fromHash) return fromHash;
    } catch (e2) { /* kein location — nichts zu tun */ }

    return null;
  };

  /**
   * Das zum URI-Anker gehoerende Element suchen.
   * Geprueft werden id UND name (aeltere Forenvorlagen setzen <a name="...">),
   * jeweils in der rohen und in der prozentdekodierten Schreibweise — das
   * Forum ist mehrsprachig (Fallerkenntnis 2), Sprungmarken koennen also
   * Nicht-ASCII-Zeichen tragen und im Adressfeld kodiert erscheinen.
   * @returns {Element|null}
   */
  ScrollMemory.prototype._findFragmentElement = function (id) {
    var doc = this._win && this._win.document;
    if (!doc || !id) return null;

    var kandidaten = [id];
    try {
      var dekodiert = decodeURIComponent(id);
      if (dekodiert && dekodiert !== id) kandidaten.push(dekodiert);
    } catch (e) { /* fehlerhafte Prozentfolge — nur die rohe Form probieren */ }

    for (var i = 0; i < kandidaten.length; i++) {
      var el = doc.getElementById(kandidaten[i]);
      if (el) return el;
      if (typeof doc.getElementsByName === 'function') {
        var byName = doc.getElementsByName(kandidaten[i]);
        if (byName && byName.length) return byName[0];
      }
    }
    return null;
  };

  /**
   * Unterkante der fest eingeblendeten Leisten am oberen Rand (px).
   * Zur Laufzeit gemessen statt fest verdrahtet — die Hinweiszeile ist
   * ein-/ausklappbar (toolbar.js HintBar) und aendert die Hoehe.
   * Nur sichtbare Leisten zaehlen (height > 0).
   */
  ScrollMemory.prototype._overlayHeight = function () {
    var doc = this._win && this._win.document;
    if (!doc || typeof doc.getElementById !== 'function') return 0;
    var ids = this._cfg.OVERLAY_IDS || [];
    var unten = 0;
    for (var i = 0; i < ids.length; i++) {
      var el = doc.getElementById(ids[i]);
      if (!el || typeof el.getBoundingClientRect !== 'function') continue;
      var r = el.getBoundingClientRect();
      if (r && r.height > 0 && r.bottom > unten) unten = r.bottom;
    }
    return Math.round(unten);
  };

  /** Laufender, billiger Save der Y-Position (kein Anker-Scan). */
  ScrollMemory.prototype.record = function () {
    if (this._restoring || !this._win) return;
    var prev = this._mem[this._currentUrl];
    this._mem[this._currentUrl] = {
      y:   this._win.scrollY,
      dpr: this._win.devicePixelRatio || 1,
      t:   Date.now(),
      // Anker aus vorherigem Save beibehalten, bis saveCurrent ihn neu setzt.
      anchor: prev ? prev.anchor : undefined,
      offset: prev ? prev.offset : undefined
    };
  };

  /** Save am Verlass-Zeitpunkt: inkl. Anker-Bestimmung + Persistenz. */
  ScrollMemory.prototype.saveCurrent = function (reason) {
    if (this._restoring || !this._win) return;
    var a = this._detectAnchor();
    var rec = {
      y:   this._win.scrollY,
      dpr: this._win.devicePixelRatio || 1,
      t:   Date.now()
    };
    if (a) { rec.anchor = a.id; rec.offset = a.offset; }
    this._mem[this._currentUrl] = rec;
    this._persist();
    this._dbg('SAVE (' + reason + ') url=' + this._currentUrl +
      ' y=' + this._win.scrollY.toFixed(1) +
      (a ? (' anker=' + a.id + ' offset=' + a.offset) : ' (kein Anker)'));
  };

  ScrollMemory.prototype.lookup = function (url) { return this._mem[url] || null; };

  // --- Browser-Verdrahtung -------------------------------------------------

  ScrollMemory.prototype._addListener = function (target, type, fn, capture) {
    target.addEventListener(type, fn, capture || false);
    this._listeners.push({ target: target, type: type, fn: fn, capture: capture || false });
  };

  ScrollMemory.prototype.attach = function () {
    var self = this, win = this._win;
    if (!win) return this;

    var FT = win.ForensicToolbar, evt = FT && FT.events;
    if (!evt || typeof evt.on !== 'function') {
      this._dbg('attach: ForensicToolbar.events fehlt — kein Abonnement.');
      return this;
    }

    if ('scrollRestoration' in win.history) {
      this._prevScrollRestoration = win.history.scrollRestoration;
      try { win.history.scrollRestoration = 'manual'; } catch (e) {}
    }

    // Laufender Y-Save beim Scrollen (throttled). Loescht eine anstehende
    // Load-Nachkorrektur, weil der Nutzer die Position selbst veraendert.
    this._addListener(win, 'scroll', function () {
      if (!self._restoring) self._cancelLoadReassert();
      if (self._restoring || self._scrollRaf) return;
      self._scrollRaf = win.requestAnimationFrame(function () {
        self._scrollRaf = 0;
        if (!self._restoring) self.record();
      });
    }, false);

    // Verlass-Zeitpunkte: hier Anker bestimmen + persistieren.
    this._addListener(win.document, 'click', function () { self.saveCurrent('click'); }, true);
    this._addListener(win, 'popstate', function () { self.saveCurrent('popstate'); }, true);
    this._addListener(win, 'pagehide', function () { self.saveCurrent('pagehide'); }, false);
    this._addListener(win, 'beforeunload', function () { self.saveCurrent('beforeunload'); }, false);

    this._pageLoadedFn = function (d) { self._onPageLoaded(d); };
    evt.on('page:loaded', this._pageLoadedFn);

    this._dbg('attach OK (Build 688, URI-Anker > Anker > Y). gespeicherte Seiten=' +
      Object.keys(this._mem).length);
    return this;
  };

  ScrollMemory.prototype._onPageLoaded = function (d) {
    var url = d && d.url;
    if (!url) return;
    this._cancelLoadReassert();
    this._currentUrl = url;

    // ---- Build 688: Vorrang des URI-Ankers (Vorgang 74a95cba) ------
    // Der Anker gilt nur, wenn er auf DIESER Seite auch wirklich steht.
    // Die Pruefung laeuft VOR dem Settle-Warten, weil das Element bereits
    // im DOM haengt (toolbar.js hat viewport.innerHTML gesetzt, bevor es
    // 'page:loaded' ausgesendet hat) — nur seine LAGE ist noch in Bewegung.
    var frag = this._activeFragment(d);
    if (frag) {
      if (this._findFragmentElement(frag)) {
        var ersatz = fragmentEntry(frag);
        this._restoring = true;
        this._dbg('LOAD url=' + url + ' -> URI-Anker "' + frag +
          '" hat Vorrang vor der gemerkten Position');
        this._restoreWhenSettled(url, ersatz);
        return;
      }
      // Tote Sprungmarke: ausdruecklich vermerken, nicht stillschweigend
      // uebergehen (GR1). Danach laeuft der bisherige Weg unveraendert.
      this._dbg('LOAD url=' + url + ' -> URI-Anker "' + frag +
        '" ist auf der Seite nicht vorhanden; gemerkte Position gilt weiter');
    }
    // ---------------------------------------------------------------------

    var entry = this._mem[url] || null;

    if (hasRestore(entry, this._cfg.RESTORE_MIN_PX)) {
      this._restoring = true;
      this._dbg('LOAD url=' + url + ' -> Restore geplant' +
        (entry.anchor ? (' (anker=' + entry.anchor + ' offset=' + entry.offset + ')')
                      : (' (y=' + entry.y + ')')));
      this._restoreWhenSettled(url, entry);
    } else {
      this._restoring = false;
      this._dbg('LOAD url=' + url + ' -> kein Ziel, bleibe oben');
    }
  };

  /** Aktuelle absolute Ankerlage lesen (oder null), dann Ziel bestimmen. */
  ScrollMemory.prototype._computeTarget = function (entry) {
    var win = this._win, doc = win.document;
    var anchorAbsTopNow = null;
    var wirksam = entry;

    if (entry && entry.fromFragment === true) {
      // Build 688: URI-Anker. Suche ueber id UND name (siehe
      // _findFragmentElement); Versatz = Unterkante der fixen Leisten,
      // damit der gesuchte Beitrag nicht dahinter verschwindet.
      var fel = this._findFragmentElement(entry.anchor);
      if (fel) anchorAbsTopNow = fel.getBoundingClientRect().top + win.scrollY;
      wirksam = {
        anchor:       entry.anchor,
        fromFragment: true,
        offset:       -this._overlayHeight()
      };
    } else if (entry && entry.anchor && isStableId(entry.anchor)) {
      var el = doc.getElementById(entry.anchor);
      if (el) anchorAbsTopNow = el.getBoundingClientRect().top + win.scrollY;
    }

    return resolveTarget(
      wirksam, anchorAbsTopNow, win.devicePixelRatio || 1,
      doc.documentElement.scrollHeight, win.innerHeight, this._cfg.RESTORE_MIN_PX
    );
  };

  ScrollMemory.prototype._restoreWhenSettled = function (url, entry) {
    var self = this, win = this._win;
    var start = this._now(), lastH = -1, stable = 0;

    function step() {
      if (self._detached) { self._restoring = false; return; }
      if (url !== self._currentUrl) { self._restoring = false; return; }

      var h = win.document.documentElement.scrollHeight;
      if (h === lastH) { stable++; } else { stable = 0; lastH = h; }
      var elapsed = self._now() - start;

      if (isSettled(stable, elapsed, self._cfg)) {
        self._applyRestore(url, entry, h, elapsed, stable);
        return;
      }
      win.requestAnimationFrame(step);
    }
    win.requestAnimationFrame(step);
  };

  ScrollMemory.prototype._applyRestore = function (url, entry, settledHeight, waitedMs, stableFrames) {
    var self = this, win = this._win;
    if (url !== this._currentUrl) { this._restoring = false; return; }

    var res = this._computeTarget(entry);
    if (res.via === 'none') { this._restoring = false; return; }

    // Hartes scrollTo: beendet zugleich eine ggf. noch laufende weiche
    // Animation von scrollIntoView() aus toolbar.js (CSSOM-View).
    win.scrollTo(0, res.y);
    this._lastAppliedY = res.y;
    this._dbg('RESTORE url=' + url + ' via=' + res.via + ' y=' + res.y.toFixed(1) +
      ' hoehe=' + settledHeight + ' gewartet=' + waitedMs.toFixed(0) + 'ms/' + stableFrames + 'frames');

    // Optionale Nachkorrektur, falls Bilder erst mit window.load fertig werden
    // und die Ankerlage danach noch minimal wandert. Nur wenn der Nutzer seither
    // NICHT selbst gescrollt hat (Schutz vor "Zurueckreissen").
    if (this._cfg.REASSERT_ON_LOAD && entry.anchor &&
        win.document.readyState !== 'complete') {
      this._scheduleLoadReassert(url, entry);
    }

    // Guard erst nach zwei Frames freigeben (eigener Scroll != User-Save).
    win.requestAnimationFrame(function () {
      win.requestAnimationFrame(function () { self._restoring = false; });
    });
  };

  ScrollMemory.prototype._scheduleLoadReassert = function (url, entry) {
    var self = this, win = this._win;
    this._cancelLoadReassert();
    this._loadReassertFn = function () {
      self._loadReassertFn = null;
      if (self._detached || url !== self._currentUrl) return;
      // Hat der Nutzer inzwischen gescrollt? Dann nichts tun.
      if (self._lastAppliedY === null || Math.abs(win.scrollY - self._lastAppliedY) > 2) return;
      self._restoring = true;
      var res = self._computeTarget(entry);
      if (res.via !== 'none') {
        win.scrollTo(0, res.y);
        self._lastAppliedY = res.y;
        self._dbg('RESTORE(load-reassert) url=' + url + ' via=' + res.via + ' y=' + res.y.toFixed(1));
      }
      win.requestAnimationFrame(function () {
        win.requestAnimationFrame(function () { self._restoring = false; });
      });
    };
    win.addEventListener('load', this._loadReassertFn, { once: true });
  };

  ScrollMemory.prototype._cancelLoadReassert = function () {
    if (this._loadReassertFn && this._win) {
      try { this._win.removeEventListener('load', this._loadReassertFn); } catch (e) {}
    }
    this._loadReassertFn = null;
  };

  ScrollMemory.prototype.detach = function () {
    this._detached = true;
    this._restoring = true;
    this._cancelLoadReassert();
    var win = this._win;
    this._listeners.forEach(function (l) {
      try { l.target.removeEventListener(l.type, l.fn, l.capture); } catch (e) {}
    });
    this._listeners = [];
    if (win && win.ForensicToolbar && win.ForensicToolbar.events &&
        typeof win.ForensicToolbar.events.off === 'function' && this._pageLoadedFn) {
      win.ForensicToolbar.events.off('page:loaded', this._pageLoadedFn);
    }
    if (win && this._prevScrollRestoration !== null && 'scrollRestoration' in win.history) {
      try { win.history.scrollRestoration = this._prevScrollRestoration; } catch (e) {}
    }
    this._dbg('detach: abgebaut.');
  };

  // =========================================================================
  // BOOTSTRAP
  // =========================================================================
  if (typeof window !== 'undefined') {
    window.ScrollMemory = ScrollMemory;

    var _boot = function () {
      if (window.__aiwScrollMemory) return true;
      if (!window.ForensicToolbar || !window.ForensicToolbar.events) return false;
      window.__aiwScrollMemory = new ScrollMemory().attach();
      return true;
    };

    if (!_boot()) {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _boot, { once: true });
      }
      window.addEventListener('load', _boot, { once: true });
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ScrollMemory;
  }
})();
