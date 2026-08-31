/* ===========================================================================
 * debug/messung_xpath_blink_M1.js
 * AiW - Messung M1: XPath-Ausdruecke der Annotationen gegen den Blink-DOM
 * ===========================================================================
 *
 * ZWECK
 *   Die Frage, die alle anderen entscheidet, lautet: Sieht Blink an der
 *   Stelle, die 'selection_json.xpathStart' benennt, DASSELBE wie die
 *   serverseitige Auswertung im gesicherten Seitenabzug?
 *
 *   Dieses Skript MISST das. Es heilt nichts, es speichert nichts, es
 *   veraendert den DOM nicht - es liest ausschliesslich. Der Umbau kommt
 *   erst nach Messung, Analyse, Hypothese, Verifikation und PoC.
 *
 * WAS ES BEANTWORTET
 *   (A) Laeuft der <mark>-Pfad ueberhaupt? (CSS Custom Highlights API da?)
 *   (B) Loest der Ausdruck in Blink auf - und wenn nein, an welchem Schritt
 *       bricht er? (dieselbe Stufenmessung wie management/maintenance/
 *       anker_diagnose.py, nur eben in der Engine, die ihn erzeugt hat)
 *   (C) Auf WELCHEN BEITRAG zeigt er in Blink? Das ist die Zahl, die gegen
 *       den Befund des Trockenlaufs gehalten wird.
 *   (D) STEHT DER MARKIERTE WORTLAUT DORT? Ein Ausdruck, der auflöst, kann
 *       trotzdem auf die falsche Stelle zeigen - im Lauf 4 haben 34 von 35
 *       aufloesenden Teilankern die Kreuzprobe nicht bestanden. Auflösen
 *       allein ist deshalb KEIN Beleg; erst der Inhalt macht ihn zu einem.
 *   (E) Wie viele Textknoten hat der Traegerabsatz JETZT? Das ist die Zahl,
 *       die gegen die des Abzugs geht (auf tid=64200: 23).
 *
 * WANN   Nachdem die zu messende Seite im Ermittlungsfenster geladen ist -
 *        also genau in der Lage, in der auch markiert wird. Die Annotationen
 *        muessen geladen sein (Minimap zeigt Marker).
 * WO     Entwicklerkonsole des Ermittlungsfensters (F12 -> Console).
 * WIE    Diese Datei vollstaendig einfuegen und ausfuehren. Der Bericht steht
 *        danach in der Zwischenablage (copy()) UND in der Konsole.
 * WAS BEOBACHTEN
 *        1. Zeile 'CSS.highlights' - steht dort 'undefined', laeuft der
 *           <mark>-Fallback, und der DOM wird beim Markieren zerteilt.
 *        2. Spalte 'TEXTKNOTEN' - weicht sie von der Zahl des Abzugs ab,
 *           ist der Absatz zwischen Abzug und Markierung veraendert worden.
 *        3. Spalte 'BEITRAG(Blink)' gegen die Nummer aus dem Trockenlauf.
 *        4. Spalte 'WORTLAUT' - 'ja(1)' ist der starke Fall: der Wortlaut
 *           steht genau in diesem einen Beitrag der Seite.
 *
 * ZWEIMAL FAHREN, UND DAS IST DER EIGENTLICHE MESSAUFBAU:
 *        Lauf 1 in der Ansicht ANGEPASST (Markierungen sichtbar),
 *        Lauf 2 in der Ansicht ORIGINAL (Markierungen entfernt).
 *        Sind die Ergebnisse GLEICH, haengt die Aufloesung nicht am
 *        Markierungszustand. Sind sie VERSCHIEDEN, ist damit bewiesen,
 *        dass unser eigenes Werkzeug die Ankerlage verschiebt - und die
 *        Differenz beziffert, um wie viel.
 *
 * Version: Messung M1 - Stand 31.08.2026, Basis origin/master 090154e
 * =========================================================================== */

(function () {
  'use strict';

  // -- Konfiguration ------------------------------------------------------
  // AUSFUEHRLICH ist Absicht: in der DEV-Phase ist die Ausgabe der
  // Messwert. Auf false gesetzt bleibt nur die Tabelle.
  var AUSFUEHRLICH = true;
  //: Wie viele Zeichen des Wortlauts in den Bericht duerfen. Der Wortlaut
  //: traegt Fallbezug; er wird deshalb GEKUERZT und nicht vollstaendig
  //: ausgegeben - der Bericht soll teilbar bleiben.
  var WORTLAUT_MAX = 40;

  var zeilen = [];
  function sag(s) { zeilen.push(s); }

  // -- (A) Umgebung -------------------------------------------------------
  var vp = document.getElementById('forensic-viewport');
  sag('=========================================================================');
  sag('MESSUNG M1 - XPath-Ausdruecke gegen den Blink-DOM (rein lesend)');
  sag('=========================================================================');
  sag('Zeitpunkt          : ' + new Date().toISOString());
  sag('Adresse            : ' + location.pathname + location.search);
  sag('User-Agent         : ' + navigator.userAgent);
  sag('CSS.highlights     : ' + (typeof CSS !== 'undefined' ? typeof CSS.highlights : '(kein CSS)'));
  sag('Highlight-Konstr.  : ' + (typeof Highlight));
  sag('  -> ist eines davon "undefined", laeuft der <mark>-Fallback und der');
  sag('     DOM wird beim Markieren zerteilt (HighlightModule Z. 1453 ff.).');
  sag('<mark> im Viewport : ' + (vp ? vp.querySelectorAll('mark').length : '-'));
  try {
    sag('Ansicht (viewMode) : ' + window.ForensicToolbar.state.get('viewMode'));
  } catch (e) {
    sag('Ansicht (viewMode) : (nicht lesbar: ' + e + ')');
  }
  sag('Viewport vorhanden : ' + !!vp + (vp ? ('  direkte Kinder: ' + vp.children.length) : ''));

  if (!vp) {
    sag('ABBRUCH: #forensic-viewport nicht gefunden. Ist eine Forumseite geladen?');
    console.log(zeilen.join('\n'));
    return;
  }

  // -- Die Beitragsreihe der Seite ---------------------------------------
  //
  // DIESELBE REGEL WIE SERVERSEITIG (absatz_finder.beitragsreihe): die
  // aeussere Kennung 'p<Nr>' und die innere 'pp<Nr>' bezeichnen DENSELBEN
  // Beitrag; gezaehlt wird je Nummer nur beim ersten Auftreten. Waere das
  // hier anders, waeren die beiden Messungen nicht vergleichbar - und eine
  // Messung, die man nicht gegenhalten kann, ist keine.
  var reihe = [];       // [{nr, el}] in Dokumentreihenfolge
  var platzVon = {};    // post_id -> Platz (0-basiert)
  (function () {
    var gesehen = {};
    var alle = vp.querySelectorAll('[id]');
    for (var i = 0; i < alle.length; i++) {
      var m = /^pp?(\d+)$/.exec(alle[i].id || '');
      if (!m) continue;
      var nr = parseInt(m[1], 10);
      if (gesehen[nr]) continue;
      gesehen[nr] = true;
      platzVon[nr] = reihe.length;
      reihe.push({ nr: nr, el: alle[i] });
    }
  })();
  sag('Beitraege im DOM   : ' + reihe.length
      + (reihe.length ? ('   erster #' + reihe[0].nr
                         + ', letzter #' + reihe[reihe.length - 1].nr) : ''));

  // -- Hilfsfunktionen ----------------------------------------------------

  /** Einen XPath-Ausdruck relativ zum Viewport aufloesen. null bei Fehlschlag. */
  function loese(ausdruck, wurzel) {
    try {
      var r = document.evaluate(ausdruck, wurzel || vp, null,
                                XPathResult.FIRST_ORDERED_NODE_TYPE, null);
      return r.singleNodeValue;
    } catch (e) {
      return null;
    }
  }

  /**
   * Stufenweise aufloesen: bis zu welchem Schritt traegt der Ausdruck?
   * Rueckgabe {gegangen, gesamt, bruch, knoten}.
   *
   * WARUM STUFENWEISE: 'loest nicht auf' ist keine Diagnose. Die Angabe,
   * WELCHER Schritt bricht, unterscheidet einen Gerueststreit (Schritt 3)
   * von einer Textknotenzaehlung (Schritt 16) - zwei voellig verschiedene
   * Ursachen mit zwei voellig verschiedenen Abhilfen.
   */
  function stufen(ausdruck) {
    var roh = String(ausdruck || '').replace(/^\.\//, '');
    var schritte = roh.split('/').filter(function (s) { return s.length; });
    var pfad = '.';
    var letzterKnoten = vp;
    for (var i = 0; i < schritte.length; i++) {
      pfad += '/' + schritte[i];
      var k = loese(pfad);
      if (!k) {
        return { gegangen: i, gesamt: schritte.length,
                 bruch: schritte[i], knoten: letzterKnoten, pfad: pfad };
      }
      letzterKnoten = k;
    }
    return { gegangen: schritte.length, gesamt: schritte.length,
             bruch: '', knoten: letzterKnoten, pfad: pfad };
  }

  /** Der naechste Vorfahr mit Beitragskennung - oder null. */
  function beitragVon(knoten) {
    var el = (knoten && knoten.nodeType === 3) ? knoten.parentNode : knoten;
    while (el && el !== vp) {
      if (el.id && /^pp?\d+$/.test(el.id)) return el;
      el = el.parentNode;
    }
    return null;
  }

  /** Klartext eines Elements, Leerraum gefaltet - wie serverseitig _klartext. */
  function klartext(el) {
    return String((el && el.textContent) || '').replace(/\s+/g, ' ').trim();
  }

  /** In WIE VIELEN Beitraegen der Seite kommt dieser Wortlaut vor? */
  function traegerZahl(wortlaut) {
    var w = String(wortlaut || '').replace(/\s+/g, ' ').trim();
    if (!w) return { anzahl: 0, nummern: [] };
    var treffer = [];
    for (var i = 0; i < reihe.length; i++) {
      if (klartext(reihe[i].el).indexOf(w) !== -1) treffer.push(reihe[i].nr);
    }
    return { anzahl: treffer.length, nummern: treffer };
  }

  /** Wie viele Textknoten hat das Elternelement dieses Knotens? */
  function textknoten(knoten) {
    var el = (knoten && knoten.nodeType === 3) ? knoten.parentNode : knoten;
    if (!el || !el.childNodes) return -1;
    var n = 0;
    for (var i = 0; i < el.childNodes.length; i++) {
      if (el.childNodes[i].nodeType === 3) n++;
    }
    return n;
  }

  /** Elementindex eines Knotens unter seinem Elternelement (1-basiert). */
  function elementIndex(el) {
    if (!el || !el.parentNode) return -1;
    var k = el.parentNode.children, i;
    for (i = 0; i < k.length; i++) { if (k[i] === el) return i + 1; }
    return -1;
  }

  // -- (B)-(E) Je Annotation ---------------------------------------------
  var annots = null;
  try { annots = window.ForensicToolbar.state.get('annotations'); } catch (e) {}
  if (!annots || typeof annots.forEach !== 'function') {
    sag('');
    sag('ABBRUCH: ForensicToolbar.state.get("annotations") nicht lesbar.');
    sag('Ist die Toolbar geladen und sind die Annotationen da (Minimap)?');
    console.log(zeilen.join('\n'));
    return;
  }

  sag('Annotationen       : ' + annots.size);
  sag('');
  sag('-------------------------------------------------------------------------');
  sag('ID     | SCHRITTE | BRUCH BEI   | BEITRAG(Blink) | PLATZ | TEXTKNOTEN | WORTLAUT');
  sag('-------------------------------------------------------------------------');

  var zaehler = { gesamt: 0, ganz: 0, gebrochen: 0, ohne_anker: 0,
                  wortlaut_ja_1: 0, wortlaut_ja_n: 0, wortlaut_nein: 0,
                  ohne_beitrag: 0, uebersetzung: 0 };
  var details = [];

  annots.forEach(function (ann) {
    zaehler.gesamt++;
    var id  = (ann && (ann.id !== undefined ? ann.id : ann.localId)) || '?';
    var sel = (ann && ann.selection) || ann || {};
    if (typeof sel === 'string') { try { sel = JSON.parse(sel); } catch (e) { sel = {}; } }

    // Uebersetzungsmarken tragen keinen XPath-Ausdruck - sie sind ueber
    // Offsets verankert (Build 333) und gehoeren hier nicht hin.
    if (sel.target === 'translation') {
      zaehler.uebersetzung++;
      sag(pad(id, 6) + ' | (Uebersetzungsmarke, Offset-Anker - kein XPath)');
      return;
    }

    var ausdruck = sel.xpathStart || '';
    if (!ausdruck) {
      zaehler.ohne_anker++;
      sag(pad(id, 6) + ' | (kein xpathStart)');
      return;
    }

    var st = stufen(ausdruck);
    if (st.gegangen >= st.gesamt) zaehler.ganz++; else zaehler.gebrochen++;

    var post = beitragVon(st.knoten);
    var nr   = post ? parseInt(/^pp?(\d+)$/.exec(post.id)[1], 10) : null;
    if (nr === null) zaehler.ohne_beitrag++;

    var tk  = textknoten(st.knoten);
    var tr  = traegerZahl(sel.textContent);
    var wl;
    if (nr === null || !tr.anzahl) {
      wl = 'nein';
      if (tr.anzahl === 0) zaehler.wortlaut_nein++;
    } else if (tr.nummern.indexOf(nr) === -1) {
      wl = 'NEIN! steht in #' + tr.nummern.join(',#');
      zaehler.wortlaut_nein++;
    } else if (tr.anzahl === 1) {
      wl = 'ja(1) EINDEUTIG';
      zaehler.wortlaut_ja_1++;
    } else {
      wl = 'ja(' + tr.anzahl + ') schwach';
      zaehler.wortlaut_ja_n++;
    }

    sag(pad(id, 6) + ' | ' + pad(st.gegangen + '/' + st.gesamt, 8)
        + ' | ' + pad(st.bruch || '-', 11)
        + ' | ' + pad(nr === null ? '-' : ('#' + nr), 14)
        + ' | ' + pad(nr === null ? '-' : (platzVon[nr] + 1) + '/' + reihe.length, 5)
        + ' | ' + pad(tk < 0 ? '-' : String(tk), 10)
        + ' | ' + wl);

    if (AUSFUEHRLICH) {
      details.push({
        id: id,
        ausdruck: ausdruck,
        aufgeloest_bis: st.pfad,
        beitrag_blink: nr,
        beitrag_elementindex: post ? elementIndex(post) : null,
        platz_von: nr === null ? null : (platzVon[nr] + 1),
        textknoten_im_traeger: tk,
        wortlaut_kurz: String(sel.textContent || '').slice(0, WORTLAUT_MAX),
        wortlaut_traeger: tr.nummern
      });
    }
  });

  function pad(s, n) {
    s = String(s);
    while (s.length < n) s += ' ';
    return s;
  }

  sag('-------------------------------------------------------------------------');
  sag('ZAEHLUNG');
  sag('  Annotationen gesamt            : ' + zaehler.gesamt);
  sag('  Ausdruck loest GANZ auf        : ' + zaehler.ganz);
  sag('  Ausdruck BRICHT                : ' + zaehler.gebrochen);
  sag('  ohne xpathStart                : ' + zaehler.ohne_anker);
  sag('  Uebersetzungsmarken            : ' + zaehler.uebersetzung);
  sag('  kein Beitragsvorfahr           : ' + zaehler.ohne_beitrag);
  sag('  Wortlaut im benannten Beitrag, EINDEUTIG auf der Seite : '
      + zaehler.wortlaut_ja_1);
  sag('  Wortlaut im benannten Beitrag, aber auch anderswo      : '
      + zaehler.wortlaut_ja_n);
  sag('  Wortlaut NICHT im benannten Beitrag                    : '
      + zaehler.wortlaut_nein);
  sag('');
  sag('LESEHILFE');
  sag('  "Wortlaut NICHT im benannten Beitrag" ist der Fall, auf den es');
  sag('  ankommt: dort loest der Ausdruck auf UND zeigt trotzdem daneben.');
  sag('  Genau diese Faelle bleiben serverseitig heute UNGEPRUEFT, wenn der');
  sag('  Ausdruck ganz aufloest.');
  sag('=========================================================================');

  var bericht = zeilen.join('\n');
  console.log(bericht);
  if (AUSFUEHRLICH) {
    console.log('--- Einzelheiten (JSON) ---');
    console.log(JSON.stringify(details, null, 1));
  }
  try {
    copy(bericht + (AUSFUEHRLICH
      ? ('\n\n--- Einzelheiten (JSON) ---\n' + JSON.stringify(details, null, 1))
      : ''));
    console.log('[M1] Bericht liegt in der Zwischenablage.');
  } catch (e) {
    console.log('[M1] copy() nicht verfuegbar - Bericht bitte aus der Konsole '
                + 'markieren und kopieren.');
  }
})();
