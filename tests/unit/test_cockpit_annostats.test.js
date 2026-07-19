/**
 * tests/unit/test_cockpit_annostats.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Annotations-Statistik
 *
 * Testsuite fuer management/server/static/cockpit_annostats.js (Build 450).
 * Testet den ECHTEN Code (readFileSync + JSDOM).
 *
 * AS01 — API verfuegbar (window.AIWCockpitAnnostats).
 * AS02 — pieOption: Pie-Serie, Daten {name,value} aus [{key,count}].
 * AS03 — summaryText: weist 'ohne evidence' aus (GR1); Scope-Text.
 * AS04 — renderAnnostats: 2 Charts, Kopfzeile; XSS-sicher (textContent).
 * AS05 — renderAnnostats: keine Annotationen -> Leerhinweis.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_annostats.js",
  "utf-8"
);

function _win() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

function _data(over) {
  return Object.assign({
    scope: "alle", generated_at: 1700000000,
    cases_total: 3, cases_with_evidence: 2, cases_without_evidence: 1,
    annotations_total: 4,
    by_category: [{ key: "email", count: 3 }, { key: "<script>x", count: 1 }],
    by_tag: [{ key: "realname", count: 2 }],
  }, over || {});
}

function _fakeECharts() {
  const insts = [];
  return {
    _insts: insts,
    init() {
      const inst = { opt: null, setOption(o) { this.opt = o; },
                     resize() {}, dispose() {} };
      insts.push(inst); return inst;
    },
  };
}

describe("cockpit_annostats.js — Annotations-Statistik (Build 450)", () => {
  it("AS01: API verfuegbar", () => {
    const api = _win().AIWCockpitAnnostats;
    expect(api).toBeTruthy();
    expect(typeof api.renderAnnostats).toBe("function");
  });

  it("AS02: pieOption Serie + Daten", () => {
    const api = _win().AIWCockpitAnnostats;
    const opt = api.pieOption([{ key: "a", count: 2 }, { key: "b", count: 1 }], "T");
    expect(opt.series[0].type).toBe("pie");
    expect(opt.series[0].data).toEqual([
      { name: "a", value: 2 }, { name: "b", value: 1 },
    ]);
    expect(opt.title.text).toBe("T");
  });

  it("AS03: summaryText weist 'ohne' aus", () => {
    const api = _win().AIWCockpitAnnostats;
    const s = api.summaryText(_data());
    expect(s).toContain("1 ohne");
    expect(s).toContain("Alle Faelle");
    expect(api.summaryText(_data({ scope: "eigene" }))).toContain("Eigene Faelle");
  });

  it("AS04: renderAnnostats 2 Charts + XSS-sicher", () => {
    const win = _win();
    const api = win.AIWCockpitAnnostats;
    const main = win.document.createElement("div");
    const charts = api.renderAnnostats(main, _data(), { ECharts: _fakeECharts() });
    expect(charts).toHaveLength(2);
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("Annotationen");
    // gefaehrlicher Kategoriename darf nicht als Markup im DOM landen
    expect(main.innerHTML).not.toContain("<script>x");
  });

  it("AS05: keine Annotationen -> Leerhinweis", () => {
    const win = _win();
    const api = win.AIWCockpitAnnostats;
    const main = win.document.createElement("div");
    api.renderAnnostats(main, _data({
      annotations_total: 0, by_category: [], by_tag: [],
    }), { ECharts: _fakeECharts() });
    expect(main.textContent).toContain("Keine Annotationen");
  });
});
