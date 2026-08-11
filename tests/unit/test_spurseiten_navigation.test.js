/**
 * test_spurseiten_navigation.test.js
 *
 * Unit-Tests: Die Seiten-Knöpfe blättern durch die SEITEN MIT SPUREN
 * (Build 691, Vorgang c658fc41).
 *
 * DER GEMELDETE BEFUND (Alex, 30.07.2026): „#forensic-btn-nav-prev und
 * #forensic-btn-nav-next scheinen funktionslos zu sein. Nix passiert."
 *
 * DREI URSACHEN, gemessen am 05.08.2026 in der VM auf
 * /forum/viewtopic.php?id=120870&p=2 (drei Seiten, 40 Spuren):
 *
 *   (1) Der Weiter-Knopf war auf JEDER Seite tot. _detectPagination() suchte
 *       a[rel='next']; die Vorlage des Forums setzt rel nur am
 *       Zurück-Verweis. Gemessen: 0 Treffer für rel='next', 2 für rel='prev'.
 *       Ein deaktivierter Knopf löst kein Klickereignis aus.
 *   (2) Der Zurück-Knopf übergab die unaufgelöste Adresse aus
 *       getAttribute('href') — 'viewtopic.php?id=120870' statt
 *       '/forum/viewtopic.php?id=120870'. Die Abfrage lief ins Leere
 *       (in_scope=false), der Ermittler sah einen Hinweisstreifen. „Nix
 *       passiert" war ein Fehlschlag, der wie eine Zuständigkeitsgrenze aussah.
 *   (3) Die Spurensequenz kannte die Seite nicht — abgetrennt als 2f1044b9
 *       (Build 677) und c290939f (Build 685).
 *
 * ENTSCHEIDUNG VON ALEX am 05.08.2026: Die Knöpfe blättern durch die
 * SPURENTRAGENDEN SEITEN, nicht durch die Seitenzählung des Forums. Damit
 * sind (1) und (2) gegenstandslos: es waren Fehler im Auslesen einer
 * Datengrundlage, die gar nicht die richtige ist.
 *
 * Testfälle:
 *   SN01 — Mitten in der Liste: beide Knöpfe frei, Titel nennen das Ziel.
 *   SN02 — Der Weiter-Knopf lädt die nächste Seite der SEQUENZ, obwohl auf
 *          der Seite kein rel='next' steht. Das ist Ursache (1).
 *   SN03 — Der Zurück-Knopf fordert die AUFGELÖSTE Adresse an, nicht die
 *          rohe aus dem href-Attribut. Das ist Ursache (2).
 *   SN04 — Erste Seite: der Zurück-Knopf ist gesperrt UND nennt den Grund.
 *   SN05 — Letzte Seite: der Weiter-Knopf ist gesperrt UND nennt den Grund.
 *   SN06 — Steht die Seite nicht in der Liste, sind beide gesperrt, der
 *          Grund steht dran, und die Standanzeige erfindet keine Zahl.
 *   SN07 — Alt+→ wirkt wie der Knopf (das Kürzel umgeht die Sperre nicht).
 *   SN08 — Die Standanzeige nennt Rang und Gesamtzahl der Spurenliste.
 *   SN09 — Nach dem Blättern stimmt der Stand, und am Rand der Liste
 *          greift die Sperre. Richtig blättern und falsch melden wäre
 *          nur die halbe Behebung.
 *
 * GEGENPROBE GEGEN DEN ALTEN STAND (toolbar.js aus Build 686, Commit 970d9d5)
 * ist in der Übergabe protokolliert: SN01 bis SN09 fallen dort, keiner ist
 * grün. Ein Wächter, der auch auf dem alten Code grün ist, belegt nichts.
 *
 * Version: 0.1.0 · Build: 691 · 2026-08-11
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const QUELLE = readFileSync("toolbar/toolbar.js", "utf-8");

// Die Spurenliste des Servers: drei Seiten mit Spuren, aufsteigend.
// Die URLs sind die kanonischen Pfade, wie /_forensic/trace_sequence sie
// liefert - mit fuehrendem '/forum/'.
const SEQUENZ = [
  { url: "/forum/viewtopic.php?id=100", title: "Thema A", group: "topic", trace_id: 1 },
  { url: "/forum/viewtopic.php?id=200", title: "Thema B", group: "topic", trace_id: 2 },
  { url: "/forum/viewtopic.php?id=300", title: "Thema C", group: "topic", trace_id: 3 },
];

// Die Seitenvorlage des Forums, nachgestellt nach der Messung vom
// 05.08.2026: rel steht NUR am Zurueck-Verweis, und die Adressen sind
// relativ - genau die beiden Eigenschaften, an denen der alte Code scheiterte.
const SEITE_HTML =
  '<div class="postmsg" id="p1">Eins</div>' +
  '<div class="postmsg" id="p2">Zwei</div>' +
  '<div class="pagination">' +
  '<span class="previous"><a href="viewtopic.php?id=100" rel="prev">Vorherige</a></span>' +
  '<span class="next"><a href="viewtopic.php?id=300">Naechste</a></span>' +
  "</div>";

function schlafe(ms) {
  return new Promise((auf) => setTimeout(auf, ms));
}

/**
 * Baut die Toolbar auf und laedt EINE Seite ueber den regulaeren Weg.
 * Gibt das DOM und ein Protokoll aller /_forensic/page-Abfragen zurueck -
 * an diesem Protokoll haengen SN02 und SN03.
 */
async function baueUndLade(seiteUrl, spuren, sequenz) {
  const seiten = [];
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body>" +
    '<div id="forensic-toolbar"></div>' +
    '<div id="forensic-viewport"></div>' +
    "</body></html>",
    { runScripts: "dangerously", url: "http://aiw.local" + seiteUrl }
  );

  // Welche Seite der Server ausliefert, richtet sich nach der zuletzt
  // angefragten URL - so laesst sich der Seitenwechsel wirklich nachfahren.
  let aktuelleUrl = seiteUrl;

  dom.window.fetch = (url) => {
    const a = String(url);
    if (a.includes("/_forensic/trace_sequence")) {
      return Promise.resolve({ ok: true,
        json: () => ({ sequence: sequenz === undefined ? SEQUENZ : sequenz,
                       total: (sequenz === undefined ? SEQUENZ : sequenz).length,
                       status: "ok" }) });
    }
    if (a.includes("/_forensic/page")) {
      seiten.push(a);
      const m = a.match(/[?&]url=([^&]*)/);
      if (m) aktuelleUrl = decodeURIComponent(m[1]);
      return Promise.resolve({ ok: true, json: () => ({
        in_scope: true, fetch_failed: false, html: SEITE_HTML,
        url_canonical: aktuelleUrl, head: {}, fragment: null,
        trace_elements: spuren, scrape_context: "user", status: "ok",
      }) });
    }
    if (a.includes("/_forensic/annotations")) {
      return Promise.resolve({ ok: true, json: () => ({ annotations: [], status: "ok" }) });
    }
    if (a.includes("/_forensic/search")) {
      return Promise.resolve({ ok: true, json: () => ({ pages: [], total: 0, status: "ok" }) });
    }
    return Promise.resolve({ ok: true, json: () => ({ status: "ok" }) });
  };
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  // jsdom kennt scrollIntoView nicht - ohne Stub braechen Spruenge ab.
  dom.window.Element.prototype.scrollIntoView = function () {};
  dom.window.EventSource = function () {
    return { addEventListener: () => {}, close: () => {} };
  };
  dom.window.eval(QUELLE);

  // GENAU EIN AUFBAU - und zwar nachgemessen, nicht angenommen.
  //
  // jsdom stellt das Dokument nebenlaeufig fertig und feuert sein EIGENES
  // DOMContentLoaded. Trifft das nach dem eval ein, hat die Toolbar sich
  // bereits selbst aufgebaut; ein zusaetzlich von Hand ausgeloestes Ereignis
  // baut sie EIN ZWEITES MAL auf. Folge: die Tastenkuerzel haengen doppelt
  // am Dokument, und ein einziger Tastendruck blaettert zwei Seiten weit.
  // Das ist ein Fehler des Pruefstands, nicht des Werkzeugs - im Browser
  // feuert DOMContentLoaded genau einmal. Er waere aber als Fehler des
  // Werkzeugs missdeutbar, deshalb wird hier geprueft statt geraten.
  await schlafe(30);
  if (!dom.window.document.getElementById("forensic-btn-nav-next")) {
    dom.window.document.dispatchEvent(
      new dom.window.Event("DOMContentLoaded", { bubbles: true })
    );
  }
  await schlafe(200);       // Seitenload, Sequenz, Nachfuehrung
  return { dom, seiten };
}

function knoepfe(dom) {
  const d = dom.window.document;
  return {
    prev: d.getElementById("forensic-btn-nav-prev"),
    next: d.getElementById("forensic-btn-nav-next"),
    info: d.getElementById("forensic-page-info"),
  };
}

function klick(dom, el) {
  el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
}

describe("Seiten-Knöpfe blättern durch Seiten mit Spuren (Vorgang c658fc41)", () => {

  // -- SN01 ------------------------------------------------------------------
  it("SN01: mitten in der Liste sind beide Knöpfe frei und nennen ihr Ziel",
     async () => {
    const { dom } = await baueUndLade("/forum/viewtopic.php?id=200", ["p1", "p2"]);
    const k = knoepfe(dom);

    expect(k.prev.disabled).toBe(false);
    expect(k.next.disabled).toBe(false);

    // Der Titel nennt die ZIELSEITE, nicht bloß die Richtung. Wer blättert,
    // soll vorher wissen, wo er landet.
    expect(k.prev.getAttribute("title")).toContain("Thema A");
    expect(k.next.getAttribute("title")).toContain("Thema C");
    expect(k.prev.getAttribute("title")).toContain("Spuren");
    expect(k.next.getAttribute("aria-label")).toContain("Thema C");
  });

  // -- SN02 ------------------------------------------------------------------
  it("SN02: der Weiter-Knopf lädt die nächste SEQUENZ-Seite, obwohl kein " +
     "rel='next' auf der Seite steht", async () => {
    // URSACHE (1). Die nachgestellte Seitenvorlage traegt bewusst KEIN
    // rel='next' - genau wie die echte. Der alte Code liess den Knopf
    // deshalb dauerhaft gesperrt; hier muss er laden.
    const { dom, seiten } = await baueUndLade("/forum/viewtopic.php?id=200",
                                              ["p1", "p2"]);
    const d = dom.window.document;
    expect(d.querySelectorAll("a[rel='next']").length).toBe(0);   // die Lage
    expect(d.querySelectorAll("a[rel='prev']").length).toBe(1);

    const vorher = seiten.length;
    klick(dom, knoepfe(dom).next);
    await schlafe(80);

    expect(seiten.length).toBe(vorher + 1);
    expect(decodeURIComponent(seiten[seiten.length - 1]))
      .toContain("url=/forum/viewtopic.php?id=300");
  });

  // -- SN03 ------------------------------------------------------------------
  it("SN03: der Zurück-Knopf fordert die aufgelöste Adresse an, nicht die rohe",
     async () => {
    // URSACHE (2). Auf der Seite steht rel='prev' mit dem relativen
    // 'viewtopic.php?id=100'. Der alte Code uebergab genau diese Zeichenkette
    // und erhielt in_scope=false. Verlangt ist der kanonische Pfad aus der
    // Sequenz.
    const { dom, seiten } = await baueUndLade("/forum/viewtopic.php?id=200",
                                              ["p1", "p2"]);
    klick(dom, knoepfe(dom).prev);
    await schlafe(80);

    const letzte = decodeURIComponent(seiten[seiten.length - 1]);
    expect(letzte).toContain("url=/forum/viewtopic.php?id=100");
    // Und ausdruecklich NICHT die rohe Form ohne fuehrenden Pfad.
    expect(letzte).not.toContain("url=viewtopic.php?id=100");
  });

  // -- SN04 ------------------------------------------------------------------
  it("SN04: auf der ersten Seite ist der Zurück-Knopf gesperrt und sagt warum",
     async () => {
    const { dom } = await baueUndLade("/forum/viewtopic.php?id=100", ["p1"]);
    const k = knoepfe(dom);

    expect(k.prev.disabled).toBe(true);
    expect(k.prev.getAttribute("title")).toContain("erste Seite mit Spuren");
    // Vorwaerts geht es weiterhin - eine Sperre, die immer greift, waere keine.
    expect(k.next.disabled).toBe(false);
  });

  // -- SN05 ------------------------------------------------------------------
  it("SN05: auf der letzten Seite ist der Weiter-Knopf gesperrt und sagt warum",
     async () => {
    const { dom } = await baueUndLade("/forum/viewtopic.php?id=300", ["p1"]);
    const k = knoepfe(dom);

    expect(k.next.disabled).toBe(true);
    expect(k.next.getAttribute("title")).toContain("letzte Seite mit Spuren");
    expect(k.prev.disabled).toBe(false);
  });

  // -- SN06 ------------------------------------------------------------------
  it("SN06: steht die Seite nicht in der Liste, sind beide gesperrt und die " +
     "Standanzeige erfindet keine Zahl", async () => {
    // Dieselbe Lage wie in Vorgang c290939f: eine Folgeseite, die Spuren
    // traegt, aber nicht in der Sequenz steht.
    const { dom } = await baueUndLade("/forum/viewtopic.php?id=100&p=2",
                                      ["p1", "p2"]);
    const k = knoepfe(dom);

    expect(k.prev.disabled).toBe(true);
    expect(k.next.disabled).toBe(true);
    expect(k.prev.getAttribute("title")).toContain("nicht in der Spurenliste");
    expect(k.next.getAttribute("title")).toContain("nicht in der Spurenliste");

    // '? / 3' statt einer erfundenen Zahl - und die Gesamtzahl stimmt.
    expect(k.info.textContent).toBe("? / 3");
    expect(k.info.getAttribute("title")).toContain("nicht in der Spurenliste");
  });

  // -- SN07 ------------------------------------------------------------------
  it("SN07: Alt+→ wirkt wie der Knopf und umgeht die Sperre nicht",
     async () => {
    // Auf der letzten Seite darf auch das Kuerzel nicht weiterblaettern.
    const { dom, seiten } = await baueUndLade("/forum/viewtopic.php?id=300",
                                              ["p1"]);
    const vorher = seiten.length;
    dom.window.document.dispatchEvent(new dom.window.KeyboardEvent("keydown",
      { key: "ArrowRight", altKey: true, bubbles: true }));
    await schlafe(60);
    expect(seiten.length).toBe(vorher);

    // Rueckwaerts wirkt es dagegen.
    dom.window.document.dispatchEvent(new dom.window.KeyboardEvent("keydown",
      { key: "ArrowLeft", altKey: true, bubbles: true }));
    await schlafe(80);
    expect(seiten.length).toBe(vorher + 1);
    expect(decodeURIComponent(seiten[seiten.length - 1]))
      .toContain("url=/forum/viewtopic.php?id=200");
  });

  // -- SN09 ------------------------------------------------------------------
  it("SN09: nach dem Blättern stimmt der Stand - und am Ende greift die Sperre",
     async () => {
    // Ohne diesen Fall waere nur belegt, dass der richtige Aufruf abgesetzt
    // wird. Belegt sein muss aber auch, dass die Anzeige DANACH den neuen
    // Stand fuehrt - sonst blaettert das Werkzeug richtig und meldet falsch.
    const { dom } = await baueUndLade("/forum/viewtopic.php?id=200", ["p1"]);
    expect(knoepfe(dom).info.textContent).toBe("2 / 3");

    klick(dom, knoepfe(dom).next);
    await schlafe(120);

    const k = knoepfe(dom);
    expect(k.info.textContent).toBe("3 / 3");
    expect(k.next.disabled).toBe(true);
    expect(k.next.getAttribute("title")).toContain("letzte Seite mit Spuren");
    expect(k.prev.disabled).toBe(false);
    expect(k.prev.getAttribute("title")).toContain("Thema B");
  });

  // -- SN08 ------------------------------------------------------------------
  it("SN08: die Standanzeige nennt Rang und Gesamtzahl der Spurenliste",
     async () => {
    const { dom } = await baueUndLade("/forum/viewtopic.php?id=200", ["p1"]);
    const k = knoepfe(dom);

    // Bis Build 686 stand hier die Seitenzahl des THEMAS ('2 / 5') - eine
    // andere Groesse als die, die die Knoepfe jetzt bewegen.
    expect(k.info.textContent).toBe("2 / 3");
    expect(k.info.getAttribute("title")).toContain("Seiten mit Spuren");
  });
});
