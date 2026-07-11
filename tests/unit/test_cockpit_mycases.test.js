/**
 * tests/unit/test_cockpit_mycases.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Meine Auftraege
 *
 * Testsuite fuer management/server/static/cockpit_mycases.js (Build 364).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitMyCases).
 *
 * MYC01 — API verfuegbar.
 * MYC02 — daysSince: Tage seit ts; null ohne ts.
 * MYC03 — toRows: Faelle -> Zeilen (has_note -> 'Notiz'/'', since_days).
 * MYC04 — renderMyCases: Kopf/count + Stub-Tabulator.
 * MYC05 — renderMyCases ohne Tabulator -> Platzhalter + null.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_mycases.js",
  "utf-8"
);

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}
function _api() { return _ctx().AIWCockpitMyCases; }

function _data() {
  return {
    count: 2,
    cases: [
      { user_id: 18, username: "b18", status: "in_progress", priority: 2,
        ampel: "gelb", event_count: 3, has_note: true,
        last_activity_at: 1000 },
      { user_id: 20, username: "b20", status: "open", priority: 3,
        ampel: "gruen", event_count: 0, has_note: false,
        last_activity_at: null },
    ],
  };
}

describe("cockpit_mycases.js — Meine Auftraege (Build 364)", () => {
  it("MYC01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.toRows).toBe("function");
    expect(typeof api.renderMyCases).toBe("function");
  });

  it("MYC02: daysSince", () => {
    const api = _api();
    // now = 1000 + 3 Tage
    expect(api.daysSince(1000, 1000 + 3 * 86400)).toBe(3);
    expect(api.daysSince(null, 1000)).toBe(null);
  });

  it("MYC03: toRows", () => {
    const api = _api();
    const rows = api.toRows(_data(), 1000 + 2 * 86400);
    expect(rows.length).toBe(2);
    expect(rows[0].has_note).toBe("Notiz");
    expect(rows[0].since_days).toBe(2);
    expect(rows[1].has_note).toBe("");
    expect(rows[1].since_days).toBe(null);
  });

  it("MYC04: renderMyCases — Kopf + Stub-Tabulator", () => {
    const win = _ctx();
    const api = win.AIWCockpitMyCases;
    const main = win.document.createElement("main");
    let made = null;
    function StubTab(container, opts) { made = { container, opts }; }
    const inst = api.renderMyCases(main, _data(), { Tabulator: StubTab });
    expect(inst).toBeInstanceOf(StubTab);
    expect(main.querySelector(".aiw-pagehead").textContent).toBe("Meine Auftraege");
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("(2)");
    expect(made.opts.data.length).toBe(2);
  });

  it("MYC05: ohne Tabulator -> Platzhalter + null", () => {
    const win = _ctx();
    const api = win.AIWCockpitMyCases;
    const main = win.document.createElement("main");
    const inst = api.renderMyCases(main, _data(), { Tabulator: null });
    expect(inst).toBe(null);
    expect(main.querySelector(".aiw-placeholder")).toBeTruthy();
  });
});
