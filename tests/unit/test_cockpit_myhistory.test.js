/**
 * tests/unit/test_cockpit_myhistory.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Meine Historie
 *
 * Testsuite fuer management/server/static/cockpit_myhistory.js (Build 364).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitMyHistory).
 *
 * MYH01 — API verfuegbar.
 * MYH02 — herkunftLabel: ich / mein Fall / beides / leer.
 * MYH03 — targetLabel: 'case #18' / ''.
 * MYH04 — toRows: events -> Zeilen (zeit/ziel/herkunft).
 * MYH05 — renderMyHistory: Kopf/count + Stub-Tabulator; ohne -> Platzhalter+null.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_myhistory.js",
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
function _api() { return _ctx().AIWCockpitMyHistory; }

function _data() {
  return {
    person_id: 2,
    limit: 200,
    count: 3,
    my_case_count: 1,
    events: [
      { seq: 50, ts: 1000, actor_id: 2, event_type: "case_note_set",
        target_type: "case", target_id: "18", mine: true, mycase: true },
      { seq: 40, ts: 900, actor_id: 1, event_type: "case_assigned",
        target_type: "case", target_id: "18", mine: false, mycase: true },
      { seq: 30, ts: 800, actor_id: 2, event_type: "rbac_granted",
        target_type: "grant", target_id: "7", mine: true, mycase: false },
    ],
  };
}

describe("cockpit_myhistory.js — Meine Historie (Build 364)", () => {
  it("MYH01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.toRows).toBe("function");
    expect(typeof api.renderMyHistory).toBe("function");
  });

  it("MYH02: herkunftLabel", () => {
    const api = _api();
    expect(api.herkunftLabel({ mine: true, mycase: true }))
      .toBe("ich \u00b7 mein Fall");
    expect(api.herkunftLabel({ mine: true, mycase: false })).toBe("ich");
    expect(api.herkunftLabel({ mine: false, mycase: true })).toBe("mein Fall");
    expect(api.herkunftLabel({ mine: false, mycase: false })).toBe("");
  });

  it("MYH03: targetLabel", () => {
    const api = _api();
    expect(api.targetLabel({ target_type: "case", target_id: "18" }))
      .toBe("case #18");
    expect(api.targetLabel({ target_type: null })).toBe("");
  });

  it("MYH04: toRows", () => {
    const api = _api();
    const rows = api.toRows(_data());
    expect(rows.length).toBe(3);
    expect(rows[0].seq).toBe(50);
    expect(rows[0].ziel).toBe("case #18");
    expect(rows[0].herkunft).toBe("ich \u00b7 mein Fall");
    expect(rows[1].herkunft).toBe("mein Fall");
    expect(rows[2].herkunft).toBe("ich");
    // Zeit formatiert (nicht leer).
    expect(rows[0].zeit).not.toBe("");
  });

  it("MYH05: renderMyHistory + ohne Tabulator", () => {
    const win = _ctx();
    const api = win.AIWCockpitMyHistory;
    const main = win.document.createElement("main");
    let made = null;
    function StubTab(container, opts) { made = { container, opts }; }
    const inst = api.renderMyHistory(main, _data(), { Tabulator: StubTab });
    expect(inst).toBeInstanceOf(StubTab);
    expect(main.querySelector(".aiw-pagehead").textContent).toBe("Meine Historie");
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("3 Eintraege");
    expect(made.opts.data.length).toBe(3);

    const win2 = _ctx();
    const main2 = win2.document.createElement("main");
    const inst2 = win2.AIWCockpitMyHistory.renderMyHistory(main2, _data(),
      { Tabulator: null });
    expect(inst2).toBe(null);
    expect(main2.querySelector(".aiw-placeholder")).toBeTruthy();
  });
});
