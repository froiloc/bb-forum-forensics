/**
 * test_kontext_warnleiste.test.js
 *
 * Unit-Tests: Warnleiste im Kontext-Dropdown (Build 676, Vorgang d76c412d).
 *
 * WORUM ES GEHT — der Befund vom 05.08.2026 in der VM:
 *   Das Suchfeld im Kontext-Dropdown filtert die GELADENEN Seiten — höchstens
 *   50, ausgewählt nach Betrachtungszeit. Für den Begriff 'viewtopic' zeigte
 *   es 3 Treffer, während der Server die Grenze von 200 erreichte. Der
 *   Ermittler sah 3 und hatte keinen Anhaltspunkt, dass es mehr gibt.
 *
 *   Die Warnleiste repariert die Beschränkung nicht — sie macht sie SICHTBAR
 *   und bietet den Weg darüber hinaus an. Das ist hier die richtige Lösung:
 *   das Dropdown ist der schnelle Weg, die Menge gehört in die erweiterte
 *   Suche.
 *
 * Testfälle:
 *   WL01 — Server kennt mehr Treffer als örtlich gefunden → Leiste erscheint,
 *          nennt beide Zahlen.
 *   WL02 — Der Knopf trägt die Gesamtzahl und übernimmt den Suchbegriff.
 *   WL03 — Server kennt nicht mehr als örtlich sichtbar → KEINE Leiste.
 *          Ein Hinweis, der immer steht, wird nicht mehr gelesen.
 *   WL04 — Ohne Suchbegriff keine Leiste.
 *   WL05 — Zählung nicht ermittelbar (total = -1) → Leiste erscheint und sagt
 *          das, statt eine Zahl zu erfinden.
 *   WL06 — Auch bei NULL örtlichen Treffern erscheint die Leiste. Gerade dann
 *          ist sie am wichtigsten: 'Keine Seiten gefunden' wäre sonst falsch.
 *
 * Version: 0.1.0 · Build: 676 · 2026-08-05
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 */

import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const QUELLE = readFileSync("toolbar/toolbar.js", "utf-8");

const SEITEN = [
  { url: "/forum/viewtopic.php?id=7", title: "Thema A", scrapeContext: "user",
    fetchFailed: false, progressPercent: 10, traceCountTotal: 1,
    annotationsTotal: 0, tagList: [], lastViewedAt: null, firstViewedAt: null },
  { url: "/forum/viewtopic.php?id=8", title: "Thema B", scrapeContext: "user",
    fetchFailed: false, progressPercent: 10, traceCountTotal: 1,
    annotationsTotal: 0, tagList: [], lastViewedAt: null, firstViewedAt: null },
  { url: "/forum/profile.php?id=18", title: "Profil X", scrapeContext: "user",
    fetchFailed: false, progressPercent: 10, traceCountTotal: 1,
    annotationsTotal: 0, tagList: [], lastViewedAt: null, firstViewedAt: null },
];

function schlafe(ms) {
  return new Promise((aufloesen) => setTimeout(aufloesen, ms));
}

/**
 * Baut eine vollständige Toolbar in JSDOM auf.
 *
 * gesamtzahl: was der Server auf die Zählanfrage (limit=1) antwortet.
 *             null bedeutet: das Feld 'total' fehlt in der Antwort.
 */
function baueUmgebung(gesamtzahl, verzoegerungMs) {
  const dom = new JSDOM(
    "<!DOCTYPE html><html><body>" +
    '<div id="forensic-toolbar"></div>' +
    '<div id="forensic-viewport"></div>' +
    "</body></html>",
    { runScripts: "dangerously", url: "http://aiw.local/forum/index.php" }
  );

  const abfragen = [];
  dom.window.fetch = (url) => {
    abfragen.push(String(url));
    const adresse = String(url);
    if (adresse.includes("/_forensic/search")) {
      // Die Zählanfrage der Warnleiste erkennt man an 'limit=1'.
      if (adresse.includes("limit=1")) {
        const koerper = { pages: [], status: "ok" };
        if (gesamtzahl !== null) koerper.total = gesamtzahl;
        // Build 677: Auf Wunsch antwortet der Stub verzögert — so lässt sich
        // der Wartehinweis messen, ohne auf eine echte 800-MB-Datenbank
        // angewiesen zu sein.
        if (verzoegerungMs) {
          return new Promise((aufloesen) => {
            setTimeout(() => aufloesen({ ok: true, json: () => koerper }),
                       verzoegerungMs);
          });
        }
        return Promise.resolve({ ok: true, json: () => koerper });
      }
      return Promise.resolve({
        ok: true,
        json: () => ({ pages: SEITEN, total: SEITEN.length,
                       geliefert: SEITEN.length, begrenzt: false,
                       status: "ok" }),
      });
    }
    if (adresse.includes("/_forensic/page")) {
      return Promise.resolve({
        ok: true,
        json: () => ({ in_scope: false, fetch_failed: true, html: null }),
      });
    }
    return Promise.resolve({ ok: true, json: () => ({ status: "ok" }) });
  };
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.EventSource = function () {
    return { addEventListener: () => {}, close: () => {} };
  };
  dom.window.eval(QUELLE);
  dom.window.document.dispatchEvent(
    new dom.window.Event("DOMContentLoaded", { bubbles: true })
  );
  return { dom, abfragen };
}

/** Dropdown öffnen, Begriff eintippen, Entprellung und Antwort abwarten. */
async function tippe(dom, begriff) {
  const d = dom.window.document;
  const btn = d.getElementById("forensic-ctx-dropdown-btn");
  btn.dispatchEvent(new dom.window.Event("click", { bubbles: true }));
  await schlafe(30);

  const feld = d.getElementById("forensic-ctx-search");
  feld.value = begriff;
  feld.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  // 150 ms Entprellung + Zeit für die Zählanfrage
  await schlafe(320);
  return {
    leiste: d.getElementById("forensic-ctx-warnleiste"),
    text: d.getElementById("forensic-ctx-warntext"),
    knopf: d.getElementById("forensic-ctx-alle-btn"),
  };
}

describe("Warnleiste im Kontext-Dropdown (Vorgang d76c412d)", () => {

  let umgebung;
  beforeEach(() => { umgebung = null; });

  // -- WL01 ------------------------------------------------------------------
  it("WL01: nennt beide Zahlen, wenn der Server mehr kennt", async () => {
    umgebung = baueUmgebung(214);
    const { leiste, text } = await tippe(umgebung.dom, "viewtopic");

    expect(leiste).not.toBeNull();
    expect(leiste.hidden).toBe(false);
    // Örtlich sichtbar sind zwei viewtopic-Seiten, der Server kennt 214.
    expect(text.textContent).toContain("2 von 214");
    expect(text.textContent).toContain("nur die geladenen Seiten");
  });

  // -- WL02 ------------------------------------------------------------------
  it("WL02: der Knopf trägt die Gesamtzahl und übernimmt den Begriff",
     async () => {
    umgebung = baueUmgebung(214);
    const { knopf } = await tippe(umgebung.dom, "viewtopic");
    expect(knopf.textContent).toBe("Alle 214 anzeigen");

    // Klick öffnet die erweiterte Suche MIT dem Begriff. Ohne Übernahme
    // müsste der Ermittler ihn ein zweites Mal tippen.
    knopf.dispatchEvent(new umgebung.dom.window.Event("click", { bubbles: true }));
    await schlafe(60);

    const qFeld = umgebung.dom.window.document.getElementById("csm-q");
    expect(qFeld).not.toBeNull();
    expect(qFeld.value).toBe("viewtopic");
  });

  // -- WL03 ------------------------------------------------------------------
  it("WL03: keine Leiste, wenn nichts verborgen ist", async () => {
    // Der Server kennt genau die zwei, die auch örtlich sichtbar sind.
    umgebung = baueUmgebung(2);
    const { leiste } = await tippe(umgebung.dom, "viewtopic");
    expect(leiste.hidden).toBe(true);
  });

  // -- WL04 ------------------------------------------------------------------
  it("WL04: ohne Suchbegriff keine Leiste", async () => {
    umgebung = baueUmgebung(214);
    const { leiste } = await tippe(umgebung.dom, "");
    expect(leiste.hidden).toBe(true);
  });

  // -- WL05 ------------------------------------------------------------------
  it("WL05: nicht ermittelbare Gesamtzahl wird gesagt, nicht erfunden",
     async () => {
    umgebung = baueUmgebung(-1);
    const { leiste, text, knopf } = await tippe(umgebung.dom, "viewtopic");
    expect(leiste.hidden).toBe(false);
    expect(text.textContent).toContain("nicht ermittelbar");
    expect(text.textContent).not.toMatch(/\d+ von \d+/);
    expect(knopf.textContent).toBe("In der erweiterten Suche öffnen");
  });

  // -- WL06 ------------------------------------------------------------------
  it("WL06: erscheint auch, wenn örtlich NICHTS gefunden wurde", async () => {
    umgebung = baueUmgebung(37);
    const { leiste, text } = await tippe(umgebung.dom, "gibtesoertlichnicht");
    expect(leiste.hidden).toBe(false);
    expect(text.textContent).toContain("0 von 37");
  });

  // -- WL07 ------------------------------------------------------------------
  it("WL07: sagt bei langsamer Antwort, DASS noch gezählt wird", async () => {
    // Gemessen am 05.08.2026: bei einem großen Fall (Administrator, >10.000
    // Beiträge, 800 MB) brauchte die Zählung rund eine Minute. Alex sah die
    // Leiste erst nach der Rückkehr aus einem anderen Fenster und hielt sie
    // für unzuverlässig. Sie war es nicht — sie war nur noch nicht fertig.
    umgebung = baueUmgebung(2041, 2600);
    const d = umgebung.dom.window.document;
    const btn = d.getElementById("forensic-ctx-dropdown-btn");
    btn.dispatchEvent(new umgebung.dom.window.Event("click", { bubbles: true }));
    await schlafe(30);

    const feld = d.getElementById("forensic-ctx-search");
    feld.value = "view";
    feld.dispatchEvent(new umgebung.dom.window.Event("input", { bubbles: true }));

    // Nach 2,3 s: Antwort steht noch aus, der Hinweis muss stehen.
    await schlafe(2300);
    const leiste = d.getElementById("forensic-ctx-warnleiste");
    const text = d.getElementById("forensic-ctx-warntext");
    expect(leiste.hidden).toBe(false);
    expect(text.textContent).toContain("wird noch gezählt");
    expect(leiste.className).toContain("forensic-ctx-warnleiste--wartet");

    // Nach der Antwort steht die Zahl da, und der Wartezustand ist weg.
    await schlafe(900);
    expect(text.textContent).toContain("von 2041");
    expect(leiste.className).not.toContain("forensic-ctx-warnleiste--wartet");
  }, 12000);

  // -- WL08 ------------------------------------------------------------------
  it("WL08: derselbe Begriff wird nicht zweimal gezählt", async () => {
    // Eine Minute Wartezeit darf sich nicht wiederholen, nur weil jemand
    // einen Buchstaben löscht und wieder tippt.
    umgebung = baueUmgebung(2041);
    const d = umgebung.dom.window.document;
    await tippe(umgebung.dom, "view");

    const vorher = umgebung.abfragen.filter(
      (a) => a.includes("/_forensic/search") && a.includes("limit=1")).length;
    expect(vorher).toBe(1);

    const feld = d.getElementById("forensic-ctx-search");
    feld.value = "vie";
    feld.dispatchEvent(new umgebung.dom.window.Event("input", { bubbles: true }));
    await schlafe(320);
    feld.value = "view";
    feld.dispatchEvent(new umgebung.dom.window.Event("input", { bubbles: true }));
    await schlafe(320);

    const nachher = umgebung.abfragen.filter(
      (a) => a.includes("/_forensic/search") && a.includes("limit=1")).length;
    expect(nachher).toBe(2);   // nur 'vie' kam neu dazu, 'view' aus dem Vorrat

    const text = d.getElementById("forensic-ctx-warntext");
    expect(text.textContent).toContain("von 2041");
  });
});
