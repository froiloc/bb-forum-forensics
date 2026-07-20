/**
 * tests/unit/test_cockpit_palette.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Kommandopalette
 *
 * Testsuite fuer management/server/static/cockpit_palette.js (Build 457).
 * Testet den ECHTEN Code (readFileSync + JSDOM).
 *
 * PA01 — API verfuegbar (window.AIWCockpitPalette).
 * PA02 — filterViews: Teilstring (case-insensitiv); leerer Begriff -> Kopie.
 * PA03 — filterViews: frueherer Treffer zuerst (Praefix vor Mitte).
 * PA04 — Strg-K oeffnet Overlay; Escape schliesst.
 * PA05 — Tippen filtert die Trefferliste (DOM).
 * PA06 — ArrowDown + Enter waehlt -> onSelect(viewId) und schliesst.
 * PA07 — Klick auf Treffer waehlt.
 * PA08 — leerer Treffer -> Hinweis 'Keine passende Sicht.'
 */

import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_palette.js",
  "utf-8"
);

const VIEWS = [
  { id: "dashboard", label: "Dashboard", group: "Ueberblick" },
  { id: "planung", label: "Prognose & Gantt", group: "Auswertung" },
  { id: "stats", label: "Statistiken (StA/Fuehrung)", group: "Auswertung" },
  { id: "policy", label: "Rechte / Policy", group: "Administration" },
];

function _ctx(onSelect) {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  const api = dom.window.AIWCockpitPalette;
  api.init({ getViews: () => VIEWS.slice(), onSelect: onSelect || (() => {}) });
  return { win: dom.window, api };
}

function _key(win, target, key, opts) {
  const ev = new win.KeyboardEvent("keydown",
    Object.assign({ key: key, bubbles: true, cancelable: true }, opts || {}));
  target.dispatchEvent(ev);
}

describe("cockpit_palette.js — Kommandopalette (Build 457)", () => {
  it("PA01: API verfuegbar", () => {
    const { api } = _ctx();
    expect(api).toBeTruthy();
    expect(typeof api.filterViews).toBe("function");
    expect(typeof api.init).toBe("function");
  });

  it("PA02: filterViews Teilstring + leerer Begriff", () => {
    const { api } = _ctx();
    expect(api.filterViews(VIEWS, "").length).toBe(4);       // Kopie
    const r = api.filterViews(VIEWS, "STAT");
    expect(r.map((v) => v.id)).toContain("stats");
  });

  it("PA03: frueherer Treffer zuerst", () => {
    const { api } = _ctx();
    // 'a' kommt in 'Dashboard' (idx1) und 'Prognose & Gantt' (idx? 'Gantt'->'a' idx.. )
    const views = [
      { id: "x", label: "abc", group: "g" },   // idx 0
      { id: "y", label: "zab", group: "g" },   // idx 1
    ];
    const r = api.filterViews(views, "ab");
    expect(r[0].id).toBe("x");
  });

  it("PA04: Strg-K oeffnet, Escape schliesst", () => {
    const { win, api } = _ctx();
    _key(win, win.document, "k", { ctrlKey: true });
    const overlay = win.document.getElementById("aiw-palette-overlay");
    expect(overlay).toBeTruthy();
    expect(overlay.hasAttribute("hidden")).toBe(false);
    _key(win, win.document, "Escape");
    expect(overlay.hasAttribute("hidden")).toBe(true);
  });

  it("PA05: Tippen filtert die Trefferliste", () => {
    const { win, api } = _ctx();
    api.open();
    const input = win.document.querySelector(".aiw-palette-input");
    input.value = "policy";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
    const items = win.document.querySelectorAll(".aiw-palette-item");
    expect(items.length).toBe(1);
    expect(items[0].getAttribute("data-view-id")).toBe("policy");
  });

  it("PA06: ArrowDown + Enter waehlt und schliesst", () => {
    let chosen = null;
    const { win, api } = _ctx((id) => { chosen = id; });
    api.open();   // Liste = alle 4, sel=0 (dashboard)
    const input = win.document.querySelector(".aiw-palette-input");
    _key(win, input, "ArrowDown");   // sel -> planung
    _key(win, input, "Enter");
    expect(chosen).toBe("planung");
    const overlay = win.document.getElementById("aiw-palette-overlay");
    expect(overlay.hasAttribute("hidden")).toBe(true);
  });

  it("PA07: Klick auf Treffer waehlt", () => {
    let chosen = null;
    const { win, api } = _ctx((id) => { chosen = id; });
    api.open();
    const item = win.document.querySelector('[data-view-id="stats"]');
    item.dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(chosen).toBe("stats");
  });

  it("PA08: leerer Treffer -> Hinweis", () => {
    const { win, api } = _ctx();
    api.open();
    const input = win.document.querySelector(".aiw-palette-input");
    input.value = "zzzznichts";
    input.dispatchEvent(new win.Event("input", { bubbles: true }));
    expect(win.document.querySelector(".aiw-palette-empty")).toBeTruthy();
  });
});
