/**
 * tests/unit/test_cockpit_palette_cases.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Kommandopalette Fall-Suche
 *
 * Testsuite fuer die Fall-Integration in cockpit_palette.js (Build 459).
 * Testet den ECHTEN Code (readFileSync + JSDOM) mit INJIZIERTER searchCases.
 *
 * PC01 — Fall-Treffer erscheinen (data-case-id) zusaetzlich zu Sicht-Treffern.
 * PC02 — Auswahl eines Fall-Treffers ruft onSelectCase(userId) und schliesst.
 * PC03 — veraltete (out-of-order) Antwort wird verworfen (_searchToken).
 * PC04 — ohne searchCases (Rueckwaertskompatibilitaet) nur Sicht-Treffer.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_palette.js",
  "utf-8"
);

const VIEWS = [
  { id: "dashboard", label: "Dashboard", group: "Ueberblick" },
  { id: "stats", label: "Statistiken", group: "Auswertung" },
];

function _ctx(opts) {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  const api = dom.window.AIWCockpitPalette;
  api.init(Object.assign({ getViews: () => VIEWS.slice() }, opts || {}));
  return { win: dom.window, api };
}

const _tick = () => new Promise((r) => setTimeout(r, 0));

describe("cockpit_palette.js — Fall-Suche (Build 459)", () => {
  it("PC01: Fall-Treffer erscheinen zusaetzlich", async () => {
    const { win, api } = _ctx({
      searchCases: () => Promise.resolve([
        { user_id: 18, username: "taeter_sued", status: "open" },
      ]),
    });
    api.open();
    const input = win.document.querySelector(".aiw-palette-input");
    input.value = "taeter";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
    await _tick();
    const caseItem = win.document.querySelector('[data-case-id="18"]');
    expect(caseItem).toBeTruthy();
    expect(caseItem.textContent).toContain("Fall 18");
  });

  it("PC02: Auswahl eines Fall-Treffers ruft onSelectCase", async () => {
    let chosen = null;
    const { win, api } = _ctx({
      searchCases: () => Promise.resolve([
        { user_id: 42, username: "x", status: "open" },
      ]),
      onSelectCase: (uid) => { chosen = uid; },
    });
    api.open();
    const input = win.document.querySelector(".aiw-palette-input");
    input.value = "x";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
    await _tick();
    const item = win.document.querySelector('[data-case-id="42"]');
    item.dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(chosen).toBe(42);
    const overlay = win.document.getElementById("aiw-palette-overlay");
    expect(overlay.hasAttribute("hidden")).toBe(true);
  });

  it("PC03: veraltete Antwort wird verworfen", async () => {
    // erste Suche loest SPAETER auf als die zweite -> nur die zweite zaehlt.
    let resolveFirst;
    const first = new Promise((res) => { resolveFirst = res; });
    let call = 0;
    const { win, api } = _ctx({
      searchCases: () => {
        call += 1;
        if (call === 1) { return first; }
        return Promise.resolve([{ user_id: 2, username: "zweite", status: "open" }]);
      },
    });
    api.open();
    const input = win.document.querySelector(".aiw-palette-input");
    input.value = "a";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));   // Suche 1
    input.value = "ab";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));   // Suche 2
    await _tick();
    // jetzt loest die ERSTE (veraltete) Suche auf:
    resolveFirst([{ user_id: 1, username: "erste", status: "open" }]);
    await _tick();
    expect(win.document.querySelector('[data-case-id="2"]')).toBeTruthy();
    expect(win.document.querySelector('[data-case-id="1"]')).toBeNull();
  });

  it("PC04: ohne searchCases nur Sicht-Treffer", async () => {
    const { win, api } = _ctx({});   // keine searchCases
    api.open();
    const input = win.document.querySelector(".aiw-palette-input");
    input.value = "dash";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
    await _tick();
    expect(win.document.querySelector('[data-view-id="dashboard"]')).toBeTruthy();
    expect(win.document.querySelector("[data-case-id]")).toBeNull();
  });
});
