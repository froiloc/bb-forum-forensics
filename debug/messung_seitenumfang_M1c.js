/* ===========================================================================
 * debug/messung_seitenumfang_M1c.js
 * AiW - Messung M1c: Wie viele Beitraege traegt diese Seite, und wie viele
 *                    verlangen die gespeicherten XPath-Ausdruecke?
 * ===========================================================================
 *
 * WORAUS SIE ENTSTANDEN IST
 *
 *   Aus dem Forenquelltext, den Alex am 31.08.2026 in den Prepper gelegt hat:
 *   forum/html/include/pms_new/mdl/topic.php, Zeilen 122-166.
 *
 *     $num_pages  = ceil(($cur_topic['replies'] + 1) / $self['disp_posts']);
 *     $p          = (!isset($_GET['p']) || $_GET['p'] <= 1
 *                    || $_GET['p'] > $num_pages) ? 1 : intval($_GET['p']);
 *     $start_from = $self['disp_posts'] * ($p - 1);
 *     ...
 *     ORDER BY id LIMIT '.$start_from.','.$self['disp_posts'];
 *
 *   ZWEI FOLGERUNGEN, und beide sind fuer uns von Belang:
 *
 *   (1) Die PN-Themenseite IST paginiert. Wie viele Beitraege sie zeigt,
 *       haengt an '$self[disp_posts]' - einer Einstellung des ABRUFENDEN
 *       Kontos. Zwei Abzuege derselben Adresse, mit verschiedenen Konten
 *       oder Einstellungen gezogen, tragen verschieden viele Beitraege.
 *   (2) Jeder Beitrag traegt seine LAUFENDE NUMMER IM GESPRAECH im Kopf:
 *
 *         <h2><span><span class="conr">#<?php echo ($start_from
 *              + $post_count) ?></span> ...
 *
 *       Diese Zahl ist nicht die post_id, sondern die Zaehlung innerhalb des
 *       Gespraechs. Aus der ersten und der letzten laesst sich ablesen, mit
 *       welchem 'start_from' und mit welchem 'disp_posts' der Abzug gezogen
 *       worden ist - eine Angabe, die sonst nirgends steht.
 *
 * WAS SIE MISST
 *
 *   * die laufenden Nummern des ersten und des letzten Beitrags,
 *   * ob die Folge dazwischen LUECKENLOS ist (sie ist eine Zaehlung, kein
 *     Schluessel - eine Luecke waere ein Befund ueber die Auslieferung),
 *   * die Blaetterleiste: wie viele Seiten das Gespraech hat,
 *   * die Zahl der Beitraege im DOM,
 *   * und den HOECHSTEN Beitragsindex, den ein gespeicherter XPath-Ausdruck
 *     dieser Seite verlangt.
 *
 *   DIE LETZTE ZAHL IST DER MESSGEGENSTAND. Verlangt ein Ausdruck einen
 *   Beitragsindex, den die Seite gar nicht hat, dann hat die Seite, gegen
 *   die er gerechnet wurde, MEHR Beitraege getragen als die heutige - und
 *   zwar beziffert.
 *
 * WANN   Auf einer Seite mit vielen Beitraegen, die Teil des gesicherten
 *        Bestands ist - je laenger das Gespraech, desto aussagekraeftiger.
 * WO     Entwicklerkonsole des Ermittlungsfensters (F12 -> Console).
 * WIE    Vollstaendig einfuegen und ausfuehren. Bericht in der
 *        Zwischenablage und in der Konsole.
 *
 * ES VERAENDERT NICHTS - es liest Textinhalte und zaehlt Elemente.
 *
 * Version: Messung M1c - Build 753, 31.08.2026
 * =========================================================================== */

(function () {
  'use strict';

  var zeilen = [];
  function sag(s) { zeilen.push(s === undefined ? "" : s); }

  var vp = document.getElementById("forensic-viewport");
  sag("=========================================================================");
  sag("MESSUNG M1c - Seitenumfang und verlangte Beitragsindizes (rein lesend)");
  sag("=========================================================================");
  sag("Zeitpunkt : " + new Date().toISOString());
  sag("Adresse   : " + location.pathname + location.search);
  if (!vp) {
    sag("ABBRUCH: #forensic-viewport nicht gefunden.");
    console.log(zeilen.join("\n"));
    return;
  }

  // -- Die Beitraege und ihre laufenden Nummern ---------------------------
  var beitraege = [];
  (function () {
    var gesehen = {};
    var alle = vp.querySelectorAll("[id]");
    for (var i = 0; i < alle.length; i++) {
      var m = /^pp?(\d+)$/.exec(alle[i].id || "");
      if (!m) continue;
      var nr = parseInt(m[1], 10);
      if (gesehen[nr]) continue;
      gesehen[nr] = true;
      // Die laufende Nummer steht im Kopf des Beitrags, in <span class="conr">
      // als '#<Zahl>'. Fehlt sie, bleibt der Eintrag null - das ist eine
      // Auskunft und kein Fehler (andere Seitenarten haben sie nicht).
      var conr = alle[i].querySelector("h2 .conr");
      var lauf = null;
      if (conr) {
        var t = /#\s*(\d+)/.exec(conr.textContent || "");
        if (t) lauf = parseInt(t[1], 10);
      }
      beitraege.push({ post: nr, lauf: lauf, el: alle[i] });
    }
  })();

  sag("Beitraege im DOM : " + beitraege.length);
  if (!beitraege.length) {
    sag("Keine Beitraege gefunden - ist das eine Themen- oder PN-Seite?");
    console.log(zeilen.join("\n"));
    return;
  }
  sag("erster Beitrag   : #" + beitraege[0].post
      + "   laufende Nummer im Gespraech: "
      + (beitraege[0].lauf === null ? "(keine)" : beitraege[0].lauf));
  var letzt = beitraege[beitraege.length - 1];
  sag("letzter Beitrag  : #" + letzt.post
      + "   laufende Nummer im Gespraech: "
      + (letzt.lauf === null ? "(keine)" : letzt.lauf));

  // -- Ist die Zaehlung lueckenlos? ---------------------------------------
  //
  // Sie ist ein Zaehler ('$start_from + $post_count'), kein Schluessel. Sie
  // MUSS lueckenlos sein. Ist sie es nicht, ist zwischen Auslieferung und
  // Messung etwas aus dem Baum verschwunden - und das waere ein Befund ueber
  // das Ermittlungsfenster, nicht ueber das Forum.
  var luecken = [];
  for (var i = 1; i < beitraege.length; i++) {
    var a = beitraege[i - 1].lauf, b = beitraege[i].lauf;
    if (a !== null && b !== null && b !== a + 1) {
      luecken.push(a + " -> " + b);
    }
  }
  if (beitraege[0].lauf === null) {
    sag("Laufende Nummern : nicht vorhanden (andere Seitenart)");
  } else if (!luecken.length) {
    sag("Laufende Nummern : LUECKENLOS von " + beitraege[0].lauf
        + " bis " + letzt.lauf);
    sag("  -> start_from = " + (beitraege[0].lauf - 1)
        + ", auf dieser Seite ausgeliefert: " + beitraege.length + " Beitraege");
  } else {
    sag("Laufende Nummern : " + luecken.length + " LUECKE(N): "
        + luecken.slice(0, 12).join(", ")
        + (luecken.length > 12 ? " ..." : ""));
    sag("  >>> BEFUND: die Zaehlung des Forums ist lueckenlos erzeugt worden.");
    sag("      Eine Luecke hier heisst, dass im ausgelieferten Baum Beitraege");
    sag("      fehlen, die die Seite hatte.");
  }

  // -- Die Blaetterleiste --------------------------------------------------
  var seiten = [];
  vp.querySelectorAll(".pagepost .pagelink a, .pagepost .pagelink strong")
    .forEach(function (a) {
      var t = (a.textContent || "").trim();
      if (/^\d+$/.test(t)) seiten.push(parseInt(t, 10));
    });
  var leiste = vp.querySelector(".pagepost .pagelink");
  sag("Blaetterleiste   : "
      + (leiste ? JSON.stringify((leiste.textContent || "").trim()
                                 .replace(/\s+/g, " ").slice(0, 120))
                : "(keine gefunden)"));
  if (seiten.length) {
    var hoechste = Math.max.apply(null, seiten);
    sag("  -> genannte Seitenzahlen bis " + hoechste
        + ";  bei " + beitraege.length + " Beitraegen je Seite waeren das bis zu "
        + (hoechste * beitraege.length) + " Nachrichten im Gespraech.");
    sag("     ACHTUNG: 'bis zu'. paginate() kuerzt die Liste bei vielen");
    sag("     Seiten, die hoechste genannte Zahl ist deshalb eine UNTERE");
    sag("     Schranke, keine Gesamtzahl.");
  }

  // -- Welchen Beitragsindex verlangen die gespeicherten Ausdruecke? ------
  var annots = null;
  try { annots = window.ForensicToolbar.state.get("annotations"); } catch (e) {}
  sag("");
  if (!annots || typeof annots.forEach !== "function") {
    sag("Annotationen nicht lesbar - der zweite Teil der Messung entfaellt.");
    console.log(zeilen.join("\n"));
    return;
  }

  // Der Beitragsbehaelter der Seite - der Elternknoten des ersten Beitrags.
  var behaelter = beitraege[0].el.parentNode;
  var kinder = behaelter ? behaelter.children.length : 0;
  sag("Beitragsbehaelter: " + kinder + " Elementkinder"
      + "   (erster Beitrag steht an Position "
      + (Array.prototype.indexOf.call(behaelter.children,
                                      beitraege[0].el) + 1) + ")");

  var hoechsterIndex = null, hoechsterVon = null, ueber = 0, gemessen = 0;
  annots.forEach(function (ann) {
    var sel = (ann && ann.selection) || ann || {};
    if (typeof sel === "string") {
      try { sel = JSON.parse(sel); } catch (e) { return; }
    }
    var a = String(sel.xpathStart || "");
    if (!a) return;
    // Der Schritt, der den Beitrag benennt: der letzte 'div[n]' VOR der
    // Folge von Schritten innerhalb des Beitrags. Robust bestimmt als der
    // groesste Index aller div-Schritte - im gemessenen Aufbau ist das
    // genau der Beitragsindex, weil die Schritte darunter alle klein sind.
    var groesster = 0;
    a.replace(/div\[(\d+)\]/g, function (_m, n) {
      var v = parseInt(n, 10);
      if (v > groesster) groesster = v;
      return _m;
    });
    if (!groesster) return;
    gemessen++;
    if (hoechsterIndex === null || groesster > hoechsterIndex) {
      hoechsterIndex = groesster;
      hoechsterVon = (ann.id !== undefined ? ann.id : ann.localId);
    }
    if (groesster > kinder) ueber++;
  });

  sag("Ausdruecke mit Beitragsindex     : " + gemessen);
  sag("hoechster verlangter Index       : "
      + (hoechsterIndex === null ? "-" : hoechsterIndex)
      + (hoechsterVon === null ? "" : ("  (Annotation " + hoechsterVon + ")")));
  sag("davon jenseits der Kinderzahl    : " + ueber);
  if (ueber) {
    sag("");
    sag("  >>> BEFUND: " + ueber + " Ausdruck/Ausdruecke verlangen eine");
    sag("      Position, die dieser Beitragsbehaelter nicht hat. Die Seite,");
    sag("      gegen die sie gerechnet wurden, war LAENGER als die heutige.");
    sag("      Differenz mindestens " + (hoechsterIndex - kinder)
        + " Elementpositionen.");
  } else {
    sag("");
    sag("  Alle verlangten Positionen liegen innerhalb der heutigen Seite.");
    sag("  Das schliesst einen Versatz NICHT aus - ein zu grosser Index");
    sag("  faellt auf, ein falscher innerhalb der Seite nicht.");
  }
  sag("=========================================================================");

  var bericht = zeilen.join("\n");
  console.log(bericht);
  try {
    copy(bericht);
    console.log("[M1c] Bericht liegt in der Zwischenablage.");
  } catch (e) {
    console.log("[M1c] copy() nicht verfuegbar - bitte aus der Konsole kopieren.");
  }
})();
