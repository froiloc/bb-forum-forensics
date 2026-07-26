/**
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 * tests/unit/test_cockpit_mentoring.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Ermittler-Betreuung
 *
 * Testsuite fuer management/server/static/cockpit_mentoring.js (Build 369).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitMentoring).
 *
 * MT01 — API verfuegbar.
 * MT02 — fmtDuration: Sekunden -> kompakte Dauer.
 * MT03 — supporterLabel + statusLabel.
 * MT04 — toRows + staleCount.
 * MT05 — renderMentoring: Kopf/count + Stub-Tabulator; ohne -> Platzhalter+null.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_mentoring.js",
  "utf-8"
);

// Build 549: das gemeinsame Tabellen-Werkzeug MUSS im Kontext liegen — genau
// wie im Browser (cockpit.html laedt cockpit_tablekit.js vor den Sichten).
// Ohne es faellt die Sicht in ihren ausdruecklichen Ersatzpfad, und der Test
// wuerde die Tabelle gar nicht mehr beruehren.
const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

function _ctx() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_tkSrc);
  dom.window.eval(_src);
  return dom.window;
}
function _api() { return _ctx().AIWCockpitMentoring; }

function _data() {
  return {
    scope: "alle", stale_sec: 30, count: 2,
    sessions: [
      { id: 7, subject_id: 19, username: "b19", supporter_id: 3,
        supporter_system_username: "h003", supporter_display_name: "Gamma",
        started_at: 1000, last_heartbeat: 1100,
        heartbeat_age_sec: 150, started_ago_sec: 300, live: false },
      { id: 5, subject_id: 18, username: "b18", supporter_id: 2,
        supporter_system_username: "h002", supporter_display_name: "Mueller",
        started_at: 1400, last_heartbeat: 1490,
        heartbeat_age_sec: 5, started_ago_sec: 65, live: true },
    ],
  };
}

describe("cockpit_mentoring.js — Ermittler-Betreuung (Build 369)", () => {
  it("MT01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.toRows).toBe("function");
    expect(typeof api.renderMentoring).toBe("function");
  });

  it("MT02: fmtDuration", () => {
    const api = _api();
    expect(api.fmtDuration(9)).toBe("9s");
    expect(api.fmtDuration(65)).toBe("1m 5s");
    expect(api.fmtDuration(3720)).toBe("1h 2m");
    expect(api.fmtDuration(0)).toBe("0s");
    expect(api.fmtDuration(-5)).toBe("0s");
  });

  it("MT03: supporterLabel + statusLabel", () => {
    const api = _api();
    expect(api.supporterLabel({ supporter_display_name: "Gamma" })).toBe("Gamma");
    expect(api.supporterLabel({ supporter_id: null })).toBe("herrenlos");
    expect(api.statusLabel({ live: true })).toBe("live");
    expect(api.statusLabel({ live: false })).toContain("stale");
  });

  it("MT04: toRows + staleCount", () => {
    const api = _api();
    const rows = api.toRows(_data());
    expect(rows.length).toBe(2);
    expect(rows[0].laufzeit).toBe("5m 0s");
    expect(rows[0]._live).toBe(false);
    expect(rows[0].heartbeat).toContain("her");
    expect(api.staleCount(_data())).toBe(1);
  });

  it("MT05: renderMentoring + ohne Tabulator", () => {
    const win = _ctx();
    const api = win.AIWCockpitMentoring;
    const main = win.document.createElement("main");
    let made = null;
    function StubTab(container, opts) { made = { container, opts }; }
    const inst = api.renderMentoring(main, _data(), { Tabulator: StubTab });
    expect(inst).toBeInstanceOf(StubTab);
    expect(main.querySelector(".aiw-pagehead").textContent)
      .toBe("Ermittler-Betreuung");
    expect(main.querySelector(".aiw-pagesub").textContent)
      .toContain("betreuungsbeduerftig");
    expect(made.opts.data.length).toBe(2);
    // rowFormatter vorhanden.
    expect(typeof made.opts.rowFormatter).toBe("function");

    const win2 = _ctx();
    const main2 = win2.document.createElement("main");
    const inst2 = win2.AIWCockpitMentoring.renderMentoring(main2, _data(),
      { Tabulator: null });
    expect(inst2).toBe(null);
    expect(main2.querySelector(".aiw-placeholder")).toBeTruthy();
  });
});
