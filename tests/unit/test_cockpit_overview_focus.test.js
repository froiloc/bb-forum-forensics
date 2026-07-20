/**
 * tests/unit/test_cockpit_overview_focus.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Overview focusCase
 *
 * Testsuite fuer focusCase in cockpit_overview.js (Build 459). Testet den ECHTEN
 * Code mit einer Fake-Tabulator-Tabelle (getRow/scrollToRow).
 *
 * OF01 — focusCase: scrollToRow(userId) aufgerufen; Zeile hervorgehoben; true.
 * OF02 — focusCase: unbekannte Zeile (getRow -> null) -> false, kein Absturz.
 * OF03 — focusCase: fehlende Tabelle / userId -> false (GR1).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_overview.js",
  "utf-8"
);

function _api() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return { win: dom.window, api: dom.window.AIWCockpitOverview };
}

function _fakeTable(win, hasRow) {
  const el = win.document.createElement("div");
  const calls = { scrollTo: [] };
  return {
    el,
    calls,
    scrollToRow(idx) { calls.scrollTo.push(idx); },
    getRow(idx) {
      if (!hasRow) { return null; }
      return { getElement: () => el, _idx: idx };
    },
  };
}

describe("cockpit_overview.js — focusCase (Build 459)", () => {
  it("OF01: scrollToRow + Hervorhebung + true", () => {
    const { win, api } = _api();
    const t = _fakeTable(win, true);
    const ok = api.focusCase(t, 18);
    expect(ok).toBe(true);
    expect(t.calls.scrollTo).toContain(18);
    expect(t.el.style.backgroundColor).toBeTruthy();   // hervorgehoben
  });

  it("OF02: unbekannte Zeile -> false", () => {
    const { win, api } = _api();
    const t = _fakeTable(win, false);
    expect(api.focusCase(t, 999)).toBe(false);
  });

  it("OF03: fehlende Tabelle/userId -> false", () => {
    const { api } = _api();
    expect(api.focusCase(null, 18)).toBe(false);
    expect(api.focusCase({ getRow() { return null; } }, null)).toBe(false);
  });
});
