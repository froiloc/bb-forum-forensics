/**
 * test_translation_mark.test.js
 * Unit-Tests: Offset-Anker-Helfer fuer Uebersetzungs-Markierungen (Build 333)
 * Baustelle 3 · Bauplan Build 333 §2/§7
 *
 * Testet gegen den ECHTEN Code (JSDOM-eval von toolbar.js), die reinen
 * Offset-Helfer sind ueber ForensicToolbar.config.annTranslationTest freigelegt.
 *
 * Version: 0.7.333 · Build: 333 · 2026-07-07
 */

import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

let dom, doc, H;
beforeAll(() => {
  const src = readFileSync("toolbar/toolbar.js", "utf-8");
  dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.fetch = () => Promise.resolve({ json: () => Promise.resolve({}) });
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.eval(src);
  doc = dom.window.document;
  H = dom.window.ForensicToolbar.config.annTranslationTest;
});

function makeBody(html) {
  const b = doc.createElement("div");
  b.className = "aiw-translation-body";
  b.innerHTML = html;
  doc.body.appendChild(b);
  return b;
}

describe("Build 333: fnv1a", () => {
  it("stabil und aenderungssensitiv", () => {
    expect(H.fnv1a("Hallo Welt")).toBe(H.fnv1a("Hallo Welt"));
    expect(H.fnv1a("Hallo Welt")).not.toBe(H.fnv1a("Hallo Welt!"));
  });
});

describe("Build 333: Offsets im Einzel-Textknoten", () => {
  it("offsetInBody + rangeFromOffsets Round-Trip", () => {
    const body = makeBody("Hallo Welt Uebersetzung");
    const tn = body.firstChild;
    expect(H.offsetInBody(body, tn, 6)).toBe(6);      // Start von "Welt"
    const r = H.rangeFromOffsets(body, 6, 10);
    expect(r.toString()).toBe("Welt");
  });
});

describe("Build 334: autoTagsForSelection (#KI-Übersetzung)", () => {
  it("Uebersetzungs-Selektion -> KI-Tag", () => {
    const tags = H.autoTagsForSelection({ target: "translation" });
    expect(tags).toEqual(["#KI-Übersetzung"]);
  });
  it("Original-Selektion (XPath) -> kein Tag", () => {
    expect(H.autoTagsForSelection({ xpathStart: "./p[1]" })).toEqual([]);
    expect(H.autoTagsForSelection(null)).toEqual([]);
  });
});

describe("Build 340: Provenienz einfrieren (selectionFromBrowser)", () => {
  function setupPanel(withProvenance) {
    const oldVp = doc.getElementById("forensic-viewport");
    if (oldVp) oldVp.remove();
    const vp = doc.createElement("div");
    vp.id = "forensic-viewport";
    const panel = doc.createElement("div");
    panel.className = "aiw-translation-panel aux-part";
    panel.setAttribute("data-post-id", "705985");
    panel.setAttribute("data-source", "posts");
    if (withProvenance) {
      panel.setAttribute("data-model", "gpt-x");
      panel.setAttribute("data-created", "2026-06-01T10:00:00");
    }
    const body = doc.createElement("div");
    body.className = "aiw-translation-body";
    body.textContent = "Hallo Welt Uebersetzung";
    panel.appendChild(body);
    vp.appendChild(panel);
    doc.body.appendChild(vp);
    return body.firstChild; // Textknoten
  }
  function fakeSel(textNode, start, end) {
    const range = doc.createRange();
    range.setStart(textNode, start);
    range.setEnd(textNode, end);
    return {
      rangeCount: 1,
      isCollapsed: false,
      getRangeAt: () => range,
      toString: () => textNode.textContent.slice(start, end),
    };
  }

  it("friert Modell + Datum aus den Panel-Attributen ein", () => {
    const tn = setupPanel(true);
    const a = H.selectionFromBrowser(fakeSel(tn, 6, 10)); // "Welt"
    expect(a.target).toBe("translation");
    expect(a.postId).toBe(705985);
    expect(a.textContent).toBe("Welt");
    expect(a.model).toBe("gpt-x");
    expect(a.created).toBe("2026-06-01T10:00:00");
  });

  it("ohne Panel-Provenienz -> model/created null, Anker bleibt gueltig", () => {
    const tn = setupPanel(false);
    const a = H.selectionFromBrowser(fakeSel(tn, 0, 5)); // "Hallo"
    expect(a.target).toBe("translation");
    expect(a.model).toBe(null);
    expect(a.created).toBe(null);
    expect(a.textHash).toBeTruthy();
  });
});
