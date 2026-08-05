/**
 * test_spurnav_unbekannter_rang.test.js
 *
 * Unit-Tests: Spur-Navigation bei UNBEKANNTEM Rang (Build 685, Vorgang c290939f).
 *
 * DER BEFUND (gemessen 05.08.2026, /forum/viewtopic.php?id=120870&p=2):
 *   `traceSeqIndex` stand auf -1, obwohl die Seite 40 Spuren trug — die Seite
 *   stand nicht in der Spurenliste. `_nextTargetForDirection()` rechnete mit
 *   dieser -1 weiter: vorwärts ergab '-1 + 1 = 0', also ein Sprung an den
 *   ANFANG der gesamten Sequenz, angeboten als „nächste Spur". Rückwärts ergab
 *   -2, die Bedingung fiel, und der Knopf blieb wortlos stehen.
 *
 *   -1 ist kein Rang, sondern eine Auskunft: „diese Seite steht nicht in der
 *   Spurenliste". Mit einer Auskunft rechnet man nicht.
 *
 * WARUM DER FALSCHE SPRUNG BISHER NICHT AUFTRAT — und warum das kein Grund
 * war, ihn stehenzulassen: `_update()` gab den Knopf gar nicht erst frei, weil
 * es die Bedingung STRENGER stellte. Zwei Stellen beantworteten dieselbe Frage
 * verschieden, und nur ihre Reihenfolge verhinderte den Sprung. Sichtbar war
 * der Widerspruch trotzdem: die Beschriftung stand auf '▶▶' (Seitenwechsel) an
 * einem Knopf, der sich nicht drücken ließ.
 *
 * Testfälle:
 *   UR01 — Steht die Seite nicht in der Liste, tragen die Knöpfe KEIN ◄◄/▶▶.
 *   UR02 — Beide Knöpfe sind deaktiviert, wenn die Seite keine Spuren trägt.
 *   UR03 — Der Grund steht dran: Titel und aria-label nennen ihn.
 *   UR04 — Gegenprobe: steht die Seite IN der Liste, funktioniert der
 *          Seitenwechsel wie bisher (◄◄/▶▶ und Titel mit Zielseite).
 *          Ein Wächter, der immer anschlägt, ist keiner.
 *   UR05 — Der ENTSCHEIDENDE Zustand: auf der LETZTEN Spur der Seite, wo die
 *          Navigation nach der nächsten SEITE fragt.
 *
 * GEGENPROBE GEGEN DEN ALTEN STAND (gemessen 05.08.2026, toolbar.js aus
 * Build 682, Commit 02f4bde): UR01+UR03, UR02 und UR05 fallen, UR04 bleibt
 * grün. UR05 fällt mit '▶▶' statt '▶' — genau die falsche Zusage.
 * ANMERKUNG ZUR ERSTEN FASSUNG: UR01/UR02/UR03 allein unterschieden NICHT
 * scharf genug. Bei '_currentIdx = -1' liegt das nächste Ziel innerhalb der
 * Seite, die Beschriftung stand also auch alt auf '▶'. Erst UR05 trifft die
 * Stelle, an der gerechnet wurde.
 *
 * Version: 0.1.0 · Build: 685 · 2026-08-05
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const QUELLE = readFileSync("toolbar/toolbar.js", "utf-8");

// Die Spurenliste des Servers. Die aktuelle Seite ('...&p=2') steht bewusst
// NICHT darin — genau die Lage, die am 05.08.2026 gemessen wurde.
const SEQUENZ = [
  { url: "/forum/viewtopic.php?id=100", title: "Thema A", group: "topic", trace_id: 1 },
  { url: "/forum/viewtopic.php?id=200", title: "Thema B", group: "topic", trace_id: 2 },
  { url: "/forum/viewtopic.php?id=300", title: "Thema C", group: "topic", trace_id: 3 },
];

function schlafe(ms) {
  return new Promise((auf) => setTimeout(auf, ms));
}

/**
 * Baut die Toolbar auf und laedt EINE Seite ueber den regulaeren Weg.
 *
 * seiteUrl: die URL, die geladen wird.
 * spuren:   trace_elements, die der Server fuer diese Seite meldet.
 */
async function baueUndLade(seiteUrl, spuren) {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body>" +
    '<div id="forensic-toolbar"></div>' +
    '<div id="forensic-viewport"></div>' +
    "</body></html>",
    { runScripts: "dangerously", url: "http://aiw.local" + seiteUrl }
  );

  const html = '<div class="postmsg" id="p1">Eins</div>' +
               '<div class="postmsg" id="p2">Zwei</div>';

  dom.window.fetch = (url) => {
    const a = String(url);
    if (a.includes("/_forensic/trace_sequence")) {
      return Promise.resolve({ ok: true,
        json: () => ({ sequence: SEQUENZ, total: SEQUENZ.length, status: "ok" }) });
    }
    if (a.includes("/_forensic/page")) {
      return Promise.resolve({ ok: true, json: () => ({
        in_scope: true, fetch_failed: false, html: html,
        url_canonical: seiteUrl, head: {}, fragment: null,
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
  // jsdom kennt scrollIntoView nicht. Ohne Stub bricht jumpTo() mitten im
  // Sprung ab, und der Zustand, den UR05 messen will, entsteht gar nicht
  // erst - der Fall waere dann rot aus einem Grund, der nichts mit der
  // Sache zu tun hat.
  dom.window.Element.prototype.scrollIntoView = function () {};
  dom.window.EventSource = function () {
    return { addEventListener: () => {}, close: () => {} };
  };
  dom.window.eval(QUELLE);
  dom.window.document.dispatchEvent(
    new dom.window.Event("DOMContentLoaded", { bubbles: true })
  );
  await schlafe(200);       // Seitenload, Sequenz, init()
  return dom;
}

function knoepfe(dom) {
  const d = dom.window.document;
  return {
    prev:  d.getElementById("forensic-btn-trace-prev"),
    next:  d.getElementById("forensic-btn-trace-next"),
    total: d.getElementById("forensic-trace-total"),
    rang:  dom.window.ForensicToolbar.state.get("traceSeqIndex"),
  };
}

describe("Spur-Navigation bei unbekanntem Rang (Vorgang c290939f)", () => {

  // -- UR01 / UR03 -----------------------------------------------------------
  it("UR01+UR03: kein ◄◄/▶▶ und ein Grund, wenn die Seite nicht in der Liste steht",
     async () => {
    const dom = await baueUndLade("/forum/viewtopic.php?id=100&p=2", ["p1", "p2"]);
    const k = knoepfe(dom);

    expect(k.rang).toBe(-1);            // die Lage, um die es geht

    expect(k.prev.textContent).toBe("◄");
    expect(k.next.textContent).toBe("▶");
    expect(k.prev.textContent).not.toContain("◄◄");
    expect(k.next.textContent).not.toContain("▶▶");

    expect(k.next.getAttribute("title")).toContain("nicht in der Spurenliste");
    expect(k.prev.getAttribute("title")).toContain("nicht in der Spurenliste");
    expect(k.next.getAttribute("aria-label")).toContain("nicht in der Spurenliste");
    // Auch die Gesamtzahl erklaert sich - dort steht '/ ?'.
    expect(k.total.getAttribute("title")).toContain("nicht in der Spurenliste");
  });

  // -- UR02 ------------------------------------------------------------------
  it("UR02: ohne Spuren auf der Seite bleiben beide Knöpfe deaktiviert",
     async () => {
    const dom = await baueUndLade("/forum/index.php", []);
    const k = knoepfe(dom);

    expect(k.rang).toBe(-1);
    expect(k.prev.disabled).toBe(true);
    expect(k.next.disabled).toBe(true);
    // Und der Grund steht dran, statt dass der Knopf für kaputt gehalten wird.
    expect(k.next.getAttribute("title")).toContain("nicht in der Spurenliste");
  });

  // -- UR05 ------------------------------------------------------------------
  it("UR05: auf der LETZTEN Spur verspricht der Knopf keinen Seitenwechsel",
     async () => {
    // DER ENTSCHEIDENDE ZUSTAND. Solange noch eine Spur auf der Seite liegt,
    // ist das nächste Ziel ohnehin ein Sprung innerhalb der Seite - da fiel
    // der Fehler nicht auf. Erst auf der LETZTEN Spur fragt die Navigation
    // nach der nächsten SEITE, und genau dort rechnete sie bis Build 682 mit
    // dem Rang -1 weiter und bot den Anfang der Sequenz an: der Knopf trug
    // '▶▶' und einen Titel mit dem Ziel 'Thema A' - an einem Knopf, der sich
    // nicht drücken ließ.
    const dom = await baueUndLade("/forum/viewtopic.php?id=100&p=2", ["p1", "p2"]);
    const d = dom.window.document;

    // Über die Spurennummer auf die letzte Spur springen - der Weg, den auch
    // der Ermittler nimmt.
    const feld = d.getElementById("forensic-trace-input");
    feld.value = "2";
    const ereignis = new dom.window.KeyboardEvent("keydown",
      { key: "Enter", bubbles: true });
    feld.dispatchEvent(ereignis);
    await schlafe(60);

    const k = knoepfe(dom);
    expect(k.rang).toBe(-1);
    expect(k.next.textContent).toBe("▶");
    expect(k.next.getAttribute("title")).toContain("nicht in der Spurenliste");
    expect(k.next.getAttribute("title")).not.toContain("Seitenwechsel");
    expect(k.next.disabled).toBe(true);
  });

  // -- UR04 ------------------------------------------------------------------
  it("UR04: steht die Seite IN der Liste, bleibt der Seitenwechsel wie bisher",
     async () => {
    // Rang 1 von 3: es gibt ein Vorher (Thema A) und ein Nachher (Thema C).
    const dom = await baueUndLade("/forum/viewtopic.php?id=200", ["p1", "p2"]);
    const k = knoepfe(dom);

    expect(k.rang).toBe(1);

    // Auf der ERSTEN Spur: rückwärts geht es nur über einen Seitenwechsel.
    expect(k.prev.textContent).toBe("◄◄");
    expect(k.prev.getAttribute("title")).toContain("Seitenwechsel zu");
    expect(k.prev.getAttribute("title")).toContain("Thema A");
    expect(k.prev.disabled).toBe(false);

    // Vorwärts liegt noch eine Spur auf DIESER Seite.
    expect(k.next.textContent).toBe("▶");
    expect(k.next.getAttribute("title")).toBe("Nächste Spur");

    // Kein Hinweis auf eine fehlende Liste - es gibt ja keine.
    expect(k.total.getAttribute("title")).toBeNull();
  });
});
