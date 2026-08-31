/* ===========================================================================
 * debug/messung_wiederherstellung_M1b.js
 * AiW - Messung M1b: Was macht die Wiederherstellung wirklich?
 * ===========================================================================
 *
 * DIE FRAGE, DIE DAZU GEFUEHRT HAT (Alex, 31.08.2026)
 *
 *   "Wenn die XPath-Ausdruecke nicht passen wuerden, wieso werden dann
 *    dennoch die korrekten Stellen im Text markiert? Wie kann die
 *    Zielbeschreibung falsch sein, aber dennoch das Richtige rauskommen?"
 *
 *   Das ist der richtige Einwand, und er ist mit M1 NICHT beantwortet. M1
 *   hat gemessen, dass der Ausdruck auf einen Beitrag zeigt, in dem der
 *   markierte Wortlaut nicht steht. Es hat NICHT gemessen, was daraus im
 *   Ermittlungsfenster wird - und genau das ist die Frage.
 *
 * DIE DREI MOEGLICHEN ANTWORTEN, und dieses Skript unterscheidet sie
 *
 *   (A) Die Markierung wird an der FALSCHEN Stelle gezeichnet, und es ist
 *       bisher niemandem aufgefallen. Dann muessten hier Ranges herauskommen,
 *       deren Text nicht der gespeicherte Wortlaut ist.
 *   (B) Die Markierung wird GAR NICHT gezeichnet. 'renderHighlight()' bricht
 *       ab, wenn 'rangeFromSelection()' null liefert (toolbar.js Z. 1487-90),
 *       und null liefert es unter anderem dann, wenn 'range.setStart()' mit
 *       einem Versatz jenseits der Knotenlaenge wirft. Dann saehe der
 *       Ermittler nur die RICHTIGEN Markierungen - und der Eindruck "es
 *       stimmt alles" entstuende genau dadurch, dass die falschen fehlen.
 *   (C) Die Markierungen stimmen, und die Auswertung von M1 ist falsch.
 *
 *   (B) waere der unangenehmste Fall: eine stille Auslassung, die aussieht
 *   wie Ordnung. Deshalb zaehlt dieses Skript nicht nur je Markierung, was
 *   herauskommt, sondern auch, WIE VIELE Ranges ueberhaupt in den
 *   Highlight-Registern stehen - also wie viele Markierungen tatsaechlich
 *   gezeichnet sind.
 *
 * WIE ES MISST
 *
 *   Es bildet 'AnnotationStoreModule.rangeFromSelection()' NACH, Schritt fuer
 *   Schritt, so wie sie in toolbar.js steht (Z. 1143-1205): dieselbe
 *   Migration der Altformen ('//' -> './', '#text[n]' -> 'text()[n]'),
 *   dasselbe 'document.evaluate' gegen '#forensic-viewport', dasselbe
 *   'createRange' mit 'offsetStart'/'offsetEnd', derselbe Vergleich von
 *   'range.toString().trim()' gegen 'selection.textContent.trim()'.
 *
 *   NACHBILDUNG UND NICHT AUFRUF, und der Grund gehoert hierher: die Module
 *   liegen in einem IIFE und sind von aussen nicht erreichbar
 *   ('var AnnotationStoreModule = (function () {...})()' - kein Eintrag am
 *   Namensraum). Der eingebaute Gegentest 'window.forensicTestHighlight()'
 *   ruft die ECHTE Funktion auf; er ist damit der massgebliche Nachweis,
 *   dieses Skript die lesbare Tabelle dazu. WEICHEN DIE BEIDEN AB, GILT DER
 *   EINGEBAUTE - und dann ist die Nachbildung hier falsch und gehoert
 *   berichtigt.
 *
 * WANN   Auf derselben Seite und in derselben Lage wie M1.
 * WO     Entwicklerkonsole des Ermittlungsfensters (F12 -> Console).
 * WIE    Diese Datei vollstaendig einfuegen und ausfuehren. Der Bericht steht
 *        danach in der Zwischenablage (copy()) und in der Konsole.
 *
 * WAS BEOBACHTEN
 *   1. Die Zeile 'Ranges in den Highlight-Registern'. Steht dort eine Zahl,
 *      die deutlich unter der Zahl der Markierungen liegt, ist Fall (B)
 *      eingetreten: ein Teil der Markierungen wird nicht gezeichnet.
 *   2. Die Spalte 'ERGEBNIS':
 *        'stimmt'      - Range gebildet, Text gleich dem gespeicherten.
 *        'STALE'       - Range gebildet, Text ANDERS. Fall (A).
 *        'kein Range'  - Ausdruck oder Versatz tragen nicht. Fall (B).
 *   3. Die Spalte 'Range in Beitrag' gegen 'Wortlaut in Beitrag'.
 *
 * ES VERAENDERT NICHTS. document.evaluate, createRange und toString sind
 * lesende Vorgaenge; es wird nichts in den Baum geschrieben und nichts an
 * den Highlight-Registern geaendert.
 *
 * Version: Messung M1b - Build 753, 31.08.2026
 * =========================================================================== */

(function () {
  'use strict';

  var WORTLAUT_MAX = 44;
  var zeilen = [];
  function sag(s) { zeilen.push(s === undefined ? "" : s); }
  function pad(s, n) {
    s = String(s);
    while (s.length < n) s += " ";
    return s;
  }

  var vp = document.getElementById("forensic-viewport");
  sag("=========================================================================");
  sag("MESSUNG M1b - Was die Wiederherstellung wirklich liefert (rein lesend)");
  sag("=========================================================================");
  sag("Zeitpunkt   : " + new Date().toISOString());
  sag("Adresse     : " + location.pathname + location.search);
  sag("User-Agent  : " + navigator.userAgent);
  try {
    sag("Ansicht     : " + window.ForensicToolbar.state.get("viewMode")
        + "   (in 'original' zeichnet renderHighlight() grundsaetzlich nicht)");
  } catch (e) {
    sag("Ansicht     : (nicht lesbar: " + e + ")");
  }
  if (!vp) {
    sag("ABBRUCH: #forensic-viewport nicht gefunden.");
    console.log(zeilen.join("\n"));
    return;
  }

  // -- Wie viele Markierungen sind tatsaechlich GEZEICHNET? ----------------
  //
  // Der Primaerpfad traegt die Ranges in vorinitialisierte Highlight-Sets
  // ein (toolbar.js Z. 1503-1508). Deren Fuellstand ist damit die Zahl der
  // wirklich sichtbaren Markierungen - unabhaengig davon, wie viele
  // Annotationen im State stehen. Genau diese Differenz ist Fall (B).
  var gezeichnet = 0;
  var register = [];
  try {
    if (typeof CSS !== "undefined" && CSS.highlights
        && typeof CSS.highlights.forEach === "function") {
      CSS.highlights.forEach(function (hl, name) {
        var n = (hl && typeof hl.size === "number") ? hl.size : 0;
        gezeichnet += n;
        if (n) register.push(name + "=" + n);
      });
    }
  } catch (e) {
    register.push("(nicht lesbar: " + e + ")");
  }
  var markZahl = vp.querySelectorAll("mark").length;

  // -- Beitragsreihe der Seite -------------------------------------------
  var reihe = [];
  var platzVon = {};
  (function () {
    var gesehen = {};
    var alle = vp.querySelectorAll("[id]");
    for (var i = 0; i < alle.length; i++) {
      var m = /^pp?(\d+)$/.exec(alle[i].id || "");
      if (!m) continue;
      var nr = parseInt(m[1], 10);
      if (gesehen[nr]) continue;
      gesehen[nr] = true;
      platzVon[nr] = reihe.length + 1;
      reihe.push({ nr: nr, el: alle[i] });
    }
  })();

  // -- Die Nachbildung von rangeFromSelection ----------------------------

  /** toolbar.js _nodeFromXpath - einschliesslich der beiden Migrationen. */
  function nodeFromXpath(xpath) {
    var migrated = String(xpath || "");
    if (migrated.substring(0, 2) === "//") {
      migrated = "./" + migrated.substring(2);
    }
    migrated = migrated.replace(/\/#text\[(\d+)\]/g, "/text()[$1]");
    try {
      return document.evaluate(migrated, vp, null, 9, null).singleNodeValue;
    } catch (e) {
      return null;
    }
  }

  /** toolbar.js rangeFromSelection - der XPath-Zweig. */
  function rangeAus(sel) {
    var startNode = nodeFromXpath(sel.xpathStart);
    var endNode = nodeFromXpath(sel.xpathEnd);
    if (!startNode || !endNode) {
      return { grund: "XPath loest nicht auf"
                 + (startNode ? "" : " (Start)")
                 + (endNode ? "" : " (Ende)") };
    }
    try {
      var range = document.createRange();
      range.setStart(startNode, sel.offsetStart);
      range.setEnd(endNode, sel.offsetEnd);
      var actual = range.toString().trim();
      var stored = String(sel.textContent || "").trim();
      return { range: range, actual: actual, stored: stored,
               stale: (actual !== stored) };
    } catch (e) {
      // GENAU HIER entsteht Fall (B): setStart wirft, wenn der Versatz
      // jenseits der Laenge des getroffenen Knotens liegt. rangeFromSelection
      // faengt die Ausnahme und liefert null - renderHighlight bricht dann
      // ab, OHNE zu zeichnen und OHNE eine sichtbare Meldung.
      return { grund: "Ausnahme: " + (e && e.name ? e.name : e) };
    }
  }

  function klartext(el) {
    return String((el && el.textContent) || "").replace(/\s+/g, " ").trim();
  }

  function beitragVon(knoten) {
    var el = (knoten && knoten.nodeType === 3) ? knoten.parentNode : knoten;
    while (el && el !== vp) {
      if (el.id && /^pp?\d+$/.test(el.id)) return el;
      el = el.parentNode;
    }
    return null;
  }

  function traegerVon(wortlaut) {
    var w = String(wortlaut || "").replace(/\s+/g, " ").trim();
    if (!w) return [];
    var treffer = [];
    for (var i = 0; i < reihe.length; i++) {
      if (klartext(reihe[i].el).indexOf(w) !== -1) treffer.push(reihe[i].nr);
    }
    return treffer;
  }

  // -- Der Durchlauf ------------------------------------------------------
  var annots = null;
  try { annots = window.ForensicToolbar.state.get("annotations"); } catch (e) {}
  if (!annots || typeof annots.forEach !== "function") {
    sag("ABBRUCH: Annotationen nicht lesbar. Ist die Toolbar geladen?");
    console.log(zeilen.join("\n"));
    return;
  }

  sag("Annotationen im State            : " + annots.size);
  sag("Ranges in den Highlight-Registern: " + gezeichnet
      + (register.length ? ("   [" + register.join(", ") + "]") : ""));
  sag("<mark>-Elemente im Viewport      : " + markZahl);
  sag("Beitraege im DOM                 : " + reihe.length);
  sag("");
  sag("  >>> LIEGT DIE ZWEITE ZAHL DEUTLICH UNTER DER ERSTEN, werden nicht");
  sag("      alle Markierungen gezeichnet - und der Eindruck, es stimme");
  sag("      alles, entsteht dadurch, dass die falschen fehlen.");
  sag("");
  sag("-------------------------------------------------------------------------");
  sag(pad("ID", 6) + " " + pad("ERGEBNIS", 26) + " " + pad("Range in", 10)
      + " " + pad("Wortlaut in", 14) + " Range-Text / gespeichert");
  sag("-------------------------------------------------------------------------");

  var z = { stimmt: 0, stale: 0, keinRange: 0, ohneAnker: 0, uebersetzung: 0 };
  var details = [];

  annots.forEach(function (ann) {
    var id = (ann && (ann.id !== undefined ? ann.id : ann.localId)) || "?";
    var sel = (ann && ann.selection) || ann || {};
    if (typeof sel === "string") {
      try { sel = JSON.parse(sel); } catch (e) { sel = {}; }
    }
    if (sel.target === "translation") {
      z.uebersetzung++;
      sag(pad(id, 6) + " (Uebersetzungsmarke, Offset-Anker - nicht hier)");
      return;
    }
    if (!sel.xpathStart) {
      z.ohneAnker++;
      sag(pad(id, 6) + " (kein xpathStart)");
      return;
    }

    var r = rangeAus(sel);
    var traeger = traegerVon(sel.textContent);
    var wortlautIn = traeger.length === 1 ? ("#" + traeger[0])
      : (traeger.length ? "(" + traeger.length + " Tr.)" : "-");

    if (!r.range) {
      z.keinRange++;
      sag(pad(id, 6) + " " + pad("kein Range: " + r.grund, 26) + " "
          + pad("-", 10) + " " + pad(wortlautIn, 14) + " "
          + JSON.stringify(String(sel.textContent || "").slice(0, WORTLAUT_MAX)));
      details.push({ id: id, ergebnis: "kein Range", grund: r.grund,
                     ausdruck: sel.xpathStart, offsetStart: sel.offsetStart,
                     offsetEnd: sel.offsetEnd, wortlaut_traeger: traeger });
      return;
    }

    var post = beitragVon(r.range.startContainer);
    var rangeIn = post ? ("#" + /^pp?(\d+)$/.exec(post.id)[1]) : "-";
    var ergebnis = r.stale ? "STALE - Text weicht ab" : "stimmt";
    if (r.stale) { z.stale++; } else { z.stimmt++; }

    sag(pad(id, 6) + " " + pad(ergebnis, 26) + " " + pad(rangeIn, 10) + " "
        + pad(wortlautIn, 14) + " "
        + JSON.stringify(r.actual.slice(0, WORTLAUT_MAX))
        + (r.stale ? ("  <-> " + JSON.stringify(
            r.stored.slice(0, WORTLAUT_MAX))) : ""));
    details.push({ id: id, ergebnis: ergebnis,
                   range_in_beitrag: rangeIn, wortlaut_traeger: traeger,
                   range_text: r.actual.slice(0, WORTLAUT_MAX),
                   gespeichert: r.stored.slice(0, WORTLAUT_MAX),
                   ausdruck: sel.xpathStart });
  });

  sag("-------------------------------------------------------------------------");
  sag("ZAEHLUNG");
  sag("  Range gebildet, Text stimmt        : " + z.stimmt);
  sag("  Range gebildet, Text weicht ab     : " + z.stale + "   <- Fall (A)");
  sag("  kein Range - wird NICHT gezeichnet : " + z.keinRange + "   <- Fall (B)");
  sag("  ohne xpathStart                    : " + z.ohneAnker);
  sag("  Uebersetzungsmarken                : " + z.uebersetzung);
  sag("");
  sag("GEGENPROBE MIT DEM EINGEBAUTEN WERKZEUG - bitte zusaetzlich fahren:");
  sag("  forensicTestHighlight()");
  sag("Es ruft die ECHTE rangeFromSelection() auf. Weichen seine Angaben von");
  sag("dieser Tabelle ab, gilt das eingebaute Werkzeug, und die Nachbildung");
  sag("hier gehoert berichtigt.");
  sag("=========================================================================");

  var bericht = zeilen.join("\n") + "\n\n--- Einzelheiten (JSON) ---\n"
    + JSON.stringify(details, null, 1);
  console.log(bericht);
  try {
    copy(bericht);
    console.log("[M1b] Bericht liegt in der Zwischenablage.");
  } catch (e) {
    console.log("[M1b] copy() nicht verfuegbar - bitte aus der Konsole "
                + "markieren und kopieren.");
  }
})();
