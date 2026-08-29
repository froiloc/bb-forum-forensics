/* ===========================================================================
 * AIW · Baustelle 3 (Toolbar) · SONDE ANNOTATIONS-METADATEN
 * ---------------------------------------------------------------------------
 * ZWECK
 *   Diese Sonde ist KEIN Fix. Sie ist ausgabelastiger Test-Code gemaess
 *   Projekt-Debugging-Protokoll ("Erst Console-Output anfordern, dann PoC,
 *   dann Fix"). Sie MISST an der laufenden Seite, welche Verfahren die drei
 *   Metadaten einer Markierung liefern:
 *
 *       post_id   ·   timestamp (Originalzeit des Beitrags)   ·   subject
 *
 *   und zwar MEHRERE Verfahren nebeneinander, damit die Entscheidung
 *   "welches nehmen wir" an Messwerten haengt und nicht an meiner Vermutung.
 *   Genau daran hat es in den Builds 727-731 gefehlt: ich habe Symptome
 *   vermessen und Verfahren geraten (Befund Alex, 29.08.2026).
 *
 * ── EIN BEFUND VORAB, DEN DIESE SONDE NACHWEISEN SOLL ──────────────────────
 *
 *   Beim Lesen des Schreibpfades (toolbar/toolbar.js, MarkerToolModule) faellt
 *   auf:
 *
 *       Z. 2610   var selObj = AnnotationStoreModule.selectionFromBrowser(sel);
 *       Z. 2614   sel.removeAllRanges();          // <- Auswahl WEG
 *       Z. 2640   var postElFuerMarke = _postElementVon(selObj);
 *
 *   _postElementVon() liest die Auswahl ueber window.getSelection() ERNEUT -
 *   also NACHDEM sie geloescht wurde. 'sel.rangeCount' ist dann 0, die
 *   Funktion gibt null zurueck, und 'post_id' bleibt leer. Der Code aus
 *   Build 727 kann in dieser Reihenfolge NIE etwas liefern.
 *
 *   DAS IST MEIN FEHLER, und er ist auch deshalb entstanden, weil die
 *   JavaScript-Testfaelle (TB01-TB09) die Funktion DIREKT mit gesetzter
 *   Auswahl aufrufen - sie pruefen das Stueck, nicht den Weg. LAUF C dieser
 *   Sonde weist den Fehler an der laufenden Anlage nach, statt ihn zu
 *   behaupten.
 *
 * ── WAS DIE SONDE TUT ──────────────────────────────────────────────────────
 *
 *   LAUF A  Alle Beitraege der Seite: je Beitrag jedes Verfahren fuer
 *           post_id, timestamp und subject - mit Treffer/Fehlschlag.
 *   LAUF B  Die AKTUELLE Auswahl: was ein Markieren jetzt in den JSON
 *           schreiben wuerde, nach jedem Verfahren.
 *   LAUF C  Gegenprobe zum echten Codeweg: dieselbe Auswahl VOR und NACH
 *           removeAllRanges() durch die ausgelieferte Hilfsfunktion.
 *   LAUF D  Der Seitenrahmen an der Stelle, an der alle 26 Anker brechen
 *           ('./donate[1]/div[1]') - Browserseite des Abgleichs.
 *
 * ── ANONYMISIERUNG ─────────────────────────────────────────────────────────
 *
 *   Freitext (Betreff, Benutzername, Beitragstext) wird VOR der Ausgabe
 *   unkenntlich gemacht: Buchstaben -> 'x', Ziffern -> '9'; Satzzeichen,
 *   Leerraum und Laenge bleiben. Zusaetzlich steht zu jedem Wert ein kurzer
 *   Fingerabdruck - daran ist erkennbar, ob zwei Verfahren DENSELBEN Wert
 *   gefunden haben, ohne dass der Wert sichtbar wird.
 *
 *   NICHT anonymisiert werden: Beitragsnummern, Zeitstempel, Tag-, Klassen-
 *   und Kennungsnamen. Das sind die Metadaten, um die es geht, bzw. reine
 *   Geruestangaben - ohne sie waere die Messung wertlos.
 *
 *   Mit ANON=false laesst sich die Anonymisierung fuer den eigenen Blick
 *   abschalten. DIE AUSGABE IST DANN NICHT MEHR WEITERGEBBAR.
 *
 * ── BEDIENUNG ──────────────────────────────────────────────────────────────
 *
 *   WANN   Auf einer Seite, auf der auch markiert wird: eine Themenseite
 *          (viewtopic) und danach eine PN-Seite (pmsnew). Beide Aufbauten
 *          sind verschieden, deshalb bitte BEIDE messen.
 *   WO     Entwicklerkonsole des Ermittlungsfensters (F12).
 *   WIE    Ganze Datei einfuegen und ausfuehren.
 *          Fuer LAUF B/C vorher etwas IN EINEM BEITRAG markieren und die
 *          Auswahl stehen lassen (nicht klicken!), dann ausfuehren.
 *   WAS    Die Sonde legt das Ergebnis als JSON in die Zwischenablage
 *          (copy) UND gibt es als Tabelle aus. Bitte das JSON schicken.
 *
 * Version: v0.8.732 · Build: 732 · 2026-08-29
 * =========================================================================== */

(function () {
  "use strict";

  // =========================================================================
  // Einstellungen
  // =========================================================================

  /** Freitext unkenntlich machen. Fuer die Weitergabe IMMER true lassen. */
  var ANON = true;

  /** Hoechstzahl der Beitraege in LAUF A. Eine Themenseite traegt bis zu 500;
   *  fuer die Messung genuegen die ersten - die Aufbauten wiederholen sich. */
  var MAX_BEITRAEGE = 12;

  var AUSGABE = { version: "sonde_annotation_metadaten v2 (Build 733)",
                  zeit: new Date().toISOString(),
                  anonymisiert: ANON };

  // =========================================================================
  // Anonymisierung
  // =========================================================================

  var Anon = (function () {
    /** Kurzer, stabiler Fingerabdruck (FNV-1a, wie toolbar.js _fnv1a). */
    function hash(s) {
      var h = 0x811c9dc5;
      for (var i = 0; i < s.length; i++) {
        h ^= s.charCodeAt(i);
        h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
      }
      return ("00000000" + h.toString(16)).slice(-8);
    }

    /**
     * Buchstaben -> 'x', Ziffern -> '9'. Satzzeichen, Leerraum und Laenge
     * bleiben - daran ist noch erkennbar, ob ein Wert wie ein Betreff
     * aussieht ("Re: xxx xxx") oder wie etwas anderes.
     */
    function verdecken(s) {
      return String(s).replace(/[^\W\d_]/gu, "x").replace(/\d/g, "9");
    }

    /** Ein Freitextwert fuer die Ausgabe: verdeckt + Laenge + Fingerabdruck. */
    function wert(s) {
      if (s === null || s === undefined) return null;
      s = String(s);
      var kurz = s.length > 120 ? s.slice(0, 120) + "…" : s;
      return {
        text: ANON ? verdecken(kurz) : kurz,
        laenge: s.length,
        fp: hash(s)          // gleiche fp = gleicher Wert, ohne ihn zu zeigen
      };
    }

    /** Ein Wert, der NICHT anonymisiert wird (Nummer, Zeitstempel, Geruest). */
    function offen(s) {
      return (s === null || s === undefined) ? null : String(s);
    }

    return { wert: wert, offen: offen, hash: hash };
  })();

  // =========================================================================
  // Kleine Helfer
  // =========================================================================

  function txt(el) {
    return el ? String(el.textContent || "").replace(/\s+/g, " ").trim() : "";
  }

  function beschreibe(el) {
    if (!el) return null;
    var s = "<" + el.tagName.toLowerCase();
    if (el.id) s += "#" + el.id;
    if (el.className) {
      s += "." + String(el.className).trim().split(/\s+/).slice(0, 2).join(".");
    }
    return s + ">";
  }

  function viewport() { return document.getElementById("forensic-viewport"); }

  /**
   * Der BEITRAGSBEHAELTER zu einem Knoten - der AEUSSERSTE, nicht der erste.
   *
   * DAS IST EINE GEMESSENE KORREKTUR UND KEINE VORSICHTSMASSNAHME. Der erste
   * Entwurf dieser Sonde nahm 'closest("article.post, div.blockpost,
   * div[id^=p]")'. In der viewtopic-Ansicht trifft das zuerst auf
   * <div class="box" id="pp1164441"> - und DARIN steht der <h2> nicht, denn
   * der ist sein GESCHWISTER:
   *
   *     <article class="post" id="p1164441">
   *       <div class="blockpost">
   *         <h2>… Betreff, Datum, Verfasser …</h2>   <- hier stehen sie
   *         <div class="box" id="pp1164441">          <- das traf closest()
   *           … <div class="postmsg">                 <- hier wird markiert
   *
   * Folge im Probelauf: Zeit und Betreff kamen als 'null' zurueck, obwohl
   * beide auf der Seite standen. Wer daraus geschlossen haette, die Angaben
   * seien nicht zu holen, haette sich am eigenen Werkzeug geirrt.
   *
   * Deshalb wird aufgestiegen und der AEUSSERSTE Treffer genommen: bei
   * viewtopic das <article>, bei pmsnew das <div class="blockpost">. Beide
   * enthalten den Kopf.
   */
  function beitragBehaelter(el) {
    var vp = viewport();
    var treffer = null;
    while (el && el.nodeType === 1 && el !== vp) {
      var kennung = /^pp?\d+$/.test(el.id || "");
      var klasse = /(^|\s)(post|blockpost)(\s|$)/.test(el.className || "");
      if (kennung || (klasse && el.querySelector("h2"))) treffer = el;
      el = el.parentElement;
    }
    return treffer;
  }

  // =========================================================================
  // Die Verfahren
  // =========================================================================
  //
  // JEDES VERFAHREN IST EIN OBJEKT MIT NAMEN UND EINER FUNKTION. So laesst
  // sich die Liste erweitern, ohne den Messrahmen anzufassen - und die
  // Ausgabe nennt zu jedem Wert das Verfahren, das ihn geliefert hat. Ein
  // Wert ohne Herkunft waere in einer Akte nicht ueberpruefbar.

  /** -------- post_id ---------------------------------------------------- */
  var VERFAHREN_POST_ID = [
    {
      name: "P1_aeussere_kennung",
      zweck: "Vorfahr mit id='p<Nummer>' - viewtopic <article>, pmsnew <div>",
      lauf: function (el) {
        while (el && el.nodeType === 1) {
          var t = /^p(\d+)$/.exec(el.id || "");
          if (t) return parseInt(t[1], 10);
          el = el.parentElement;
        }
        return null;
      }
    },
    {
      name: "P2_innere_kennung",
      zweck: "Vorfahr mit id='pp<Nummer>' - viewtopic <div class=box>",
      lauf: function (el) {
        while (el && el.nodeType === 1) {
          var t = /^pp(\d+)$/.exec(el.id || "");
          if (t) return parseInt(t[1], 10);
          el = el.parentElement;
        }
        return null;
      }
    },
    {
      name: "P3_pid_im_link",
      zweck: "erster Link mit '?pid=<Nummer>' im Beitrag (beide Ansichten)",
      lauf: function (el) {
        var behaelter = beitragBehaelter(el);
        var a = behaelter ? behaelter.querySelector("a[href*='pid=']") : null;
        var t = a ? /[?&]pid=(\d+)/.exec(a.getAttribute("href") || "") : null;
        return t ? parseInt(t[1], 10) : null;
      }
    },
    {
      name: "P4_anker_im_link",
      zweck: "erster Link mit '#p<Nummer>' im Beitrag",
      lauf: function (el) {
        var behaelter = beitragBehaelter(el);
        var a = behaelter ? behaelter.querySelector("a[href*='#p']") : null;
        var t = a ? /#p(\d+)\b/.exec(a.getAttribute("href") || "") : null;
        return t ? parseInt(t[1], 10) : null;
      }
    },
    {
      name: "P5_data_post_id",
      zweck: "unsere eigene Uebersetzungsflagge, data-post-id",
      lauf: function (el) {
        var behaelter = beitragBehaelter(el);
        var b = behaelter ? behaelter.querySelector("[data-post-id]") : null;
        return b ? parseInt(b.getAttribute("data-post-id"), 10) || null : null;
      }
    },
    {
      name: "P6_sichtbare_nummer",
      zweck: "die im Kopf angezeigte '#<Nummer>' (viewtopic, rechts)",
      lauf: function (el) {
        var behaelter = beitragBehaelter(el);
        var h2 = behaelter ? behaelter.querySelector("h2") : null;
        var t = h2 ? /(?:^|\s)#(\d{3,})(?:\s|$)/.exec(txt(h2)) : null;
        return t ? parseInt(t[1], 10) : null;
      }
    }
  ];

  /** -------- timestamp --------------------------------------------------- */
  //
  // DIE ZEITANGABE IST IM FORUM EIN TEXT, kein maschinenlesbares Attribut.
  // Beide Auszuege (Alex, 28.08.2026) zeigen dieselbe Schreibweise:
  //     "Fri., 16.12.2022 19:08:03"   (viewtopic, im inneren <i>)
  //     "Mon., 26.04.2021 20:36:03"   (pmsnew, im Link des <h2>)
  // Das 'title'-Attribut daneben ("3 years ago") ist RELATIV und damit
  // unbrauchbar - es aendert sich mit dem Lesezeitpunkt.
  //
  // ZEITZONE: Ein Forum rendert in der Zone seiner Einstellung. Die Sonde
  // rechnet deshalb NICHT in Epoch um, sondern gibt den Rohtext und die
  // zerlegten Bestandteile aus. Was die Zone ist, ist eine eigene Frage und
  // wird nicht geraten - eine Tatzeit mit falscher Zone ist um Stunden falsch.

  /** Der zuletzt verworfene 'title'-Text - nur zur Anzeige. */
  var LETZTER_TITLE = null;

  var ZEIT_MUSTER = /(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?/;

  function zerlegeZeit(s) {
    var t = ZEIT_MUSTER.exec(String(s || ""));
    if (!t) return null;
    return {
      roh: String(s).trim(),
      tag: +t[1], monat: +t[2], jahr: +t[3],
      stunde: +t[4], minute: +t[5], sekunde: t[6] ? +t[6] : 0,
      iso_ohne_zone: t[3] + "-" + ("0" + t[2]).slice(-2) + "-"
                     + ("0" + t[1]).slice(-2) + "T" + ("0" + t[4]).slice(-2)
                     + ":" + t[5] + ":" + ("0" + (t[6] || "00")).slice(-2)
    };
  }

  var VERFAHREN_ZEIT = [
    {
      name: "T1_inneres_i_im_h2",
      zweck: "viewtopic: <h2> … <i><i title='3 years ago'>Datum</i></i>",
      lauf: function (behaelter) {
        var h2 = behaelter.querySelector("h2");
        if (!h2) return null;
        var kandidaten = h2.querySelectorAll("i");
        for (var i = 0; i < kandidaten.length; i++) {
          var z = zerlegeZeit(txt(kandidaten[i]));
          if (z) return z;
        }
        return null;
      }
    },
    {
      name: "T2_link_im_h2",
      zweck: "pmsnew: <h2> … <a href='…pid=…#p…'>Datum</a>",
      lauf: function (behaelter) {
        var h2 = behaelter.querySelector("h2");
        var a = h2 ? h2.querySelector("a[href*='pid=']") : null;
        return a ? zerlegeZeit(txt(a)) : null;
      }
    },
    {
      name: "T3_h2_gesamttext",
      zweck: "Rueckfall: Muster ueber den ganzen Kopftext",
      lauf: function (behaelter) {
        var h2 = behaelter.querySelector("h2");
        return h2 ? zerlegeZeit(txt(h2)) : null;
      }
    },
    {
      name: "T4_title_attribut",
      zweck: "GEGENPROBE: das title-Attribut ist RELATIV und darf NICHT taugen",
      lauf: function (behaelter) {
        // MESSUNG ALEX 29.08.2026: liefert "Original Poster", "4 years ago",
        // "Report a problem" - nie ein Datum. Die Gegenprobe hat damit
        // bestaetigt, dass 'title' untauglich ist.
        //
        // BIS v1 GAB DIESER ZWEIG EIN OBJEKT ZURUECK, und die Zaehlung fuehrte
        // ihn als TREFFER (4 von 4). Eine Gegenprobe, die als Erfolg zaehlt,
        // verdirbt genau die Quote, wegen der es sie gibt. Jetzt: null, und
        // der gefundene Text steht getrennt daneben.
        var e = behaelter.querySelector("[title]");
        if (!e) return null;
        var z = zerlegeZeit(e.getAttribute("title"));
        if (z) return z;
        LETZTER_TITLE = e.getAttribute("title");
        return null;
      }
    }
  ];

  /** -------- subject ----------------------------------------------------- */
  //
  // ACHTUNG, DIE BEIDEN ANSICHTEN SIND HIER GRUNDVERSCHIEDEN:
  //   viewtopic - der Betreff steht IM Beitrag (Link im <h2>, und noch einmal
  //               als <h3> in .postright).
  //   pmsnew    - der Titel der Unterhaltung steht AUSSERHALB des Beitrags,
  //               einmal je Seite: <div class="block2col"><div class="block">
  //               <h2 style="color:#115098;">TITEL</h2>.
  // Ein Verfahren, das nur im Beitrag sucht, findet bei PN also nichts - und
  // das ist kein Fehler, sondern der Aufbau.

  var VERFAHREN_BETREFF = [
    {
      name: "S1_link_im_h2",
      zweck: "viewtopic: Linktext im Kopf ('Re: …')",
      imBeitrag: true,
      lauf: function (behaelter) {
        // MESSUNG ALEX 29.08.2026: der ERSTE Link mit 'viewtopic.php' im Kopf
        // ist auf seiner Seite der DAUERLINK, dessen Text die Beitragsnummer
        // ist ("#721583"). v1 lieferte deshalb die Nummer statt des Betreffs.
        // Jetzt werden alle Links des Kopfes durchgesehen und die
        // uebersprungen, deren Text nur aus '#' und Ziffern besteht.
        var h2 = behaelter.querySelector("h2");
        if (!h2) return null;
        var links = h2.querySelectorAll("a[href*='viewtopic.php']");
        for (var i = 0; i < links.length; i++) {
          var t = txt(links[i]);
          if (t && !/^#?\d+$/.test(t)) return t;
        }
        return null;
      }
    },
    {
      name: "S2_h3_in_postright",
      zweck: "viewtopic: <h3> ueber dem Beitragstext",
      imBeitrag: true,
      lauf: function (behaelter) {
        var h3 = behaelter.querySelector(".postright h3, h3");
        return h3 ? txt(h3) : null;
      }
    },
    {
      name: "S3_seitentitel_block2col",
      zweck: "pmsnew: <div class=block2col><div class=block><h2>TITEL</h2>",
      imBeitrag: false,
      lauf: function () {
        var vp = viewport();
        var h2 = vp ? vp.querySelector(".block2col .block > h2") : null;
        return h2 ? txt(h2) : null;
      }
    },
    {
      name: "S4_erster_h2_ohne_beitrag",
      zweck: "Rueckfall: erster <h2> der Seite, der NICHT in einem Beitrag "
             + "sitzt",
      imBeitrag: false,
      lauf: function () {
        var vp = viewport();
        if (!vp) return null;
        var alle = vp.querySelectorAll("h2");
        for (var i = 0; i < alle.length; i++) {
          if (!beitragBehaelter(alle[i])) {
            return txt(alle[i]);
          }
        }
        return null;
      }
    },
    {
      name: "S6_themenbetreff_ohne_nummer",
      zweck: "wie S4, aber ohne den angehaengten '#<Zahl>' (MESSUNG Alex: "
             + "S4 lieferte 'Titel? #99999')",
      imBeitrag: false,
      lauf: function () {
        var vp = viewport();
        if (!vp) return null;
        var alle = vp.querySelectorAll("h2");
        for (var i = 0; i < alle.length; i++) {
          if (beitragBehaelter(alle[i])) continue;
          var t = txt(alle[i]).replace(/\s*#\d+\s*$/, "").trim();
          if (t) return t;
        }
        return null;
      }
    },
    {
      name: "S5_dokumenttitel",
      zweck: "GEGENPROBE: document.title - er traegt meist Forumsname mit",
      imBeitrag: false,
      lauf: function () { return document.title || null; }
    }
  ];

  // =========================================================================
  // LAUF A - alle Beitraege der Seite
  // =========================================================================

  function beitraegeFinden() {
    var vp = viewport();
    if (!vp) return [];
    // Beide Aufbauten in EINEM Selektor. 'div[id^=p]' faengt die PN-Ansicht
    // und die reduzierte Ansicht; 'article.post' die Vollansicht.
    var roh = vp.querySelectorAll(
      "article.post, div.blockpost[id], div[id^='p'][class*='blockpost']");
    var aus = [];
    for (var i = 0; i < roh.length && aus.length < MAX_BEITRAEGE; i++) {
      // Verschachtelte Treffer ueberspringen (article > div.blockpost).
      var drin = false;
      for (var j = 0; j < aus.length; j++) {
        if (aus[j].contains(roh[i])) { drin = true; break; }
      }
      if (!drin) aus.push(roh[i]);
    }
    return aus;
  }

  function laufA() {
    var beitraege = beitraegeFinden();
    console.groupCollapsed("%cLAUF A%c  " + beitraege.length
      + " Beitraege · je Verfahren ein Messwert",
      "background:#036;color:#fff;padding:2px 6px", "");

    var zeilen = [];
    beitraege.forEach(function (b, nr) {
      // Der Textknoten, von dem aus die post_id-Verfahren AUFSTEIGEN - also
      // genau der Punkt, an dem auch eine Markierung sitzen wuerde.
      var msg = b.querySelector(".postmsg");
      var start = msg && msg.firstElementChild ? msg.firstElementChild : msg || b;

      var zeile = { nr: nr + 1, behaelter: beschreibe(b) };

      VERFAHREN_POST_ID.forEach(function (v) {
        zeile[v.name] = v.lauf(start);
      });
      VERFAHREN_ZEIT.forEach(function (v) {
        var z = v.lauf(b);
        zeile[v.name] = z ? (z.iso_ohne_zone || z.roh) : null;
      });
      VERFAHREN_BETREFF.forEach(function (v) {
        var s = v.imBeitrag ? v.lauf(b) : v.lauf();
        var w = Anon.wert(s);
        zeile[v.name] = w ? (w.text + " [" + w.fp + "]") : null;
      });
      zeilen.push(zeile);
    });

    if (console.table) console.table(zeilen);
    else console.log(zeilen);
    console.groupEnd();

    AUSGABE.lauf_a = {
      anzahl_beitraege: beitraege.length,
      verfahren_post_id: VERFAHREN_POST_ID.map(function (v) {
        return { name: v.name, zweck: v.zweck }; }),
      verfahren_zeit: VERFAHREN_ZEIT.map(function (v) {
        return { name: v.name, zweck: v.zweck }; }),
      verfahren_betreff: VERFAHREN_BETREFF.map(function (v) {
        return { name: v.name, zweck: v.zweck }; }),
      zeilen: zeilen
    };

    // Trefferquote je Verfahren - DIE eigentliche Entscheidungsgrundlage.
    var quote = {};
    zeilen.forEach(function (z) {
      Object.keys(z).forEach(function (k) {
        if (k === "nr" || k === "behaelter") return;
        quote[k] = quote[k] || { treffer: 0, von: 0 };
        quote[k].von++;
        if (z[k] !== null && z[k] !== undefined) quote[k].treffer++;
      });
    });
    console.groupCollapsed("%cLAUF A · Trefferquote je Verfahren%c",
      "background:#036;color:#fff;padding:2px 6px", "");
    if (console.table) console.table(quote); else console.log(quote);
    console.groupEnd();
    AUSGABE.lauf_a.trefferquote = quote;
  }

  // =========================================================================
  // LAUF B - die aktuelle Auswahl
  // =========================================================================

  function laufB() {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
      console.warn("[Sonde] LAUF B uebersprungen: keine Auswahl. Bitte im "
        + "Beitragstext etwas markieren, die Auswahl STEHEN LASSEN und die "
        + "Sonde erneut ausfuehren.");
      AUSGABE.lauf_b = { uebersprungen: "keine Auswahl" };
      return;
    }
    var range = sel.getRangeAt(0);
    var knoten = range.startContainer;
    var el = knoten.nodeType === 3 ? knoten.parentElement : knoten;
    var behaelter = beitragBehaelter(el);

    var b = { start_knoten: knoten.nodeType === 3 ? "#text" : beschreibe(el),
              beitragsbehaelter: beschreibe(behaelter),
              wortlaut: Anon.wert(sel.toString()) };

    VERFAHREN_POST_ID.forEach(function (v) { b[v.name] = v.lauf(el); });
    if (behaelter) {
      VERFAHREN_ZEIT.forEach(function (v) {
        var z = v.lauf(behaelter);
        b[v.name] = z || null;
      });
      VERFAHREN_BETREFF.forEach(function (v) {
        var s = v.imBeitrag ? v.lauf(behaelter) : v.lauf();
        b[v.name] = Anon.wert(s);
      });
    }

    console.groupCollapsed("%cLAUF B%c  die aktuelle Auswahl",
      "background:#063;color:#fff;padding:2px 6px", "");
    console.log(b);
    console.groupEnd();
    AUSGABE.lauf_b = b;
  }

  // =========================================================================
  // LAUF C - Gegenprobe zum ausgelieferten Codeweg
  // =========================================================================
  //
  // DER KERN DIESER SONDE. Die ausgelieferte Hilfsfunktion wird ZWEIMAL
  // aufgerufen: einmal mit stehender Auswahl, einmal nachdem die Auswahl
  // geloescht wurde - also genau in der Reihenfolge, die _onMouseUp() hat.
  // Liefert der erste Aufruf eine Nummer und der zweite null, ist der Befund
  // aus dem Kopf dieser Datei an der laufenden Anlage BELEGT.

  function laufC() {
    var helfer = window.ForensicToolbar
      && window.ForensicToolbar.config
      && window.ForensicToolbar.config.markerHelpers;
    if (!helfer || typeof helfer.postElementVon !== "function") {
      console.warn("[Sonde] LAUF C uebersprungen: "
        + "ForensicToolbar.config.markerHelpers.postElementVon fehlt. "
        + "Diese Anlage laeuft mit einem Build vor 727.");
      AUSGABE.lauf_c = { uebersprungen: "markerHelpers fehlt (Build < 727)" };
      return;
    }
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
      console.warn("[Sonde] LAUF C uebersprungen: keine Auswahl.");
      AUSGABE.lauf_c = { uebersprungen: "keine Auswahl" };
      return;
    }

    // Auswahl merken, damit sie danach wiederhergestellt werden kann - die
    // Sonde soll die Arbeit des Bedieners nicht wegwerfen.
    var gemerkt = sel.getRangeAt(0).cloneRange();

    var mitAuswahl = helfer.postElementVon(null);
    sel.removeAllRanges();                       // genau wie Z. 2614
    var ohneAuswahl = helfer.postElementVon(null);

    sel.removeAllRanges();
    sel.addRange(gemerkt);                       // Auswahl zurueckgeben

    var c = {
      aufruf_mit_stehender_auswahl: mitAuswahl,
      aufruf_nach_removeAllRanges: ohneAuswahl,
      befund: (mitAuswahl !== null && ohneAuswahl === null)
        ? "BELEGT: die Funktion liefert nur MIT stehender Auswahl eine "
          + "Nummer. _onMouseUp() ruft sie NACH removeAllRanges() - dort "
          + "kann sie nichts liefern, und post_id bleibt leer."
        : (mitAuswahl === null && ohneAuswahl === null)
          ? "BEIDE null - die Auswahl sitzt womoeglich nicht in einem "
            + "Beitrag. Bitte im Beitragstext markieren und wiederholen."
          : "UNERWARTET - bitte die beiden Werte schicken."
    };
    console.groupCollapsed("%cLAUF C%c  Gegenprobe zum Codeweg",
      "background:#630;color:#fff;padding:2px 6px", "");
    console.log(c);
    console.groupEnd();
    AUSGABE.lauf_c = c;
  }

  // =========================================================================
  // LAUF D - der Seitenrahmen an der Bruchstelle der Anker
  // =========================================================================
  //
  // Alle 26 Anker brechen bei './donate[1]/div[1]'; der Abzug hat dort
  // <div#brdleft> und <div#page-header>. Was der Browser dort hat, misst
  // dieser Lauf - damit beide Listen aus EINEM Aufruf kommen und nicht aus
  // zweien, die man erst zusammensuchen muss.

  function laufD() {
    var vp = viewport();
    if (!vp) {
      AUSGABE.lauf_d = { uebersprungen: "kein #forensic-viewport" };
      return;
    }
    function kinder(el) {
      return Array.prototype.map.call(el.children, function (k, i) {
        return (i + 1) + ": " + beschreibe(k);
      });
    }
    var d = { viewport_kinder: kinder(vp) };

    var ziel = document.evaluate("./donate[1]/div[1]", vp, null, 9, null)
                 .singleNodeValue;
    d.pfad_donate_div = ziel ? beschreibe(ziel) : "loest im Browser NICHT auf";
    if (ziel) {
      d.kinder_an_der_bruchstelle = kinder(ziel);
      d.anzahl_div = ziel.querySelectorAll(":scope > div").length;
      // NUR die <div> - so zaehlt auch XPath 'div[n]'. Alex' Anker verlangt
      // div[3] (PN) bzw. div[4] (Forum); ohne diese Liste laesst sich nicht
      // sagen, WELCHES div das ist.
      d.nur_divs = Array.prototype.map.call(
        ziel.querySelectorAll(":scope > div"), function (k, i) {
          return "div[" + (i + 1) + "]: " + beschreibe(k); });
    }
    // Und die erste Ebene darunter, falls der Pfad anders liegt.
    var erstes = vp.firstElementChild;
    d.erstes_kind_des_viewports = beschreibe(erstes);
    if (erstes) d.kinder_des_ersten_kindes = kinder(erstes);

    console.groupCollapsed("%cLAUF D%c  Seitenrahmen an der Bruchstelle",
      "background:#306;color:#fff;padding:2px 6px", "");
    console.log(d);
    console.groupEnd();
    AUSGABE.lauf_d = d;
  }

  // =========================================================================
  // Lauf
  // =========================================================================

  console.log("%c AIW · SONDE ANNOTATIONS-METADATEN ",
              "background:#000;color:#0f0;padding:4px 10px;font-weight:bold");
  console.log("Seite: " + location.pathname + location.search);
  console.log("Anonymisierung: " + (ANON ? "AN (Ausgabe weitergebbar)"
                                         : "AUS - NICHT WEITERGEBEN"));

  AUSGABE.seite = location.pathname + location.search;

  try { laufA(); } catch (e) { AUSGABE.lauf_a = { fehler: String(e) };
                               console.error("[Sonde] LAUF A:", e); }
  try { laufB(); } catch (e) { AUSGABE.lauf_b = { fehler: String(e) };
                               console.error("[Sonde] LAUF B:", e); }
  try { laufC(); } catch (e) { AUSGABE.lauf_c = { fehler: String(e) };
                               console.error("[Sonde] LAUF C:", e); }
  try { laufD(); } catch (e) { AUSGABE.lauf_d = { fehler: String(e) };
                               console.error("[Sonde] LAUF D:", e); }

  var json = JSON.stringify(AUSGABE, null, 2);
  window.__aiwSonde = AUSGABE;
  try {
    if (typeof copy === "function") {
      copy(json);
      console.log("%c-> Ergebnis liegt in der Zwischenablage. Bitte schicken.",
                  "color:#0a0;font-weight:bold");
    } else {
      console.log("[Sonde] 'copy' steht nicht zur Verfuegung - JSON folgt:");
      console.log(json);
    }
  } catch (e) {
    console.log("[Sonde] Zwischenablage nicht erreichbar - JSON folgt:");
    console.log(json);
  }
  console.log("Das Ergebnis liegt ausserdem in window.__aiwSonde.");
})();
