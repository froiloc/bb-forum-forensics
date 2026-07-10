/**
 * tests/unit/test_cockpit_workload.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Lastverteilung
 *
 * Testsuite fuer management/server/static/cockpit_workload.js (Build 351).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitWorkload).
 *
 * WL01 — API verfuegbar.
 * WL02 — nameLabel(): display_name > system_username > '?'.
 * WL03 — echartsOption(): Kategorien in Backend-Reihenfolge; 3 gestapelte
 *        Serien (Rot/Gelb/Gruen) mit korrekten Werten; yAxis.inverse.
 * WL04 — echartsOption(): Ampelfarben + stack gesetzt.
 * WL05 — echartsOption(): leere loads -> leere Kategorien/Serien (kein Fehler).
 * WL06 — renderWorkload(): Kopf/Scope/Count; Stub-ECharts.init + setOption
 *        erhalten die Option; Rueckgabe = Instanz.
 * WL07 — renderWorkload(): ohne ECharts -> null + Hinweis.
 *
 * Version: v0.7.351 · Build: 351 · 2026-07-10
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_workload.js",
  "utf-8"
);

function _makeContext() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_src);
  return dom.window;
}

function _api() {
  return _makeContext().AIWCockpitWorkload;
}

// Last-Zeile mit Defaults (InvestigatorLoad-DTO-Form aus /api/workload).
function L(over) {
  return Object.assign(
    {
      investigator_id: 1,
      system_username: "h001",
      display_name: "Chefin",
      is_backlog: false,
      total_cases: 0,
      ampel_rot: 0,
      ampel_gelb: 0,
      ampel_gruen: 0,
      active_cases: 0,
      done_cases: 0,
      audit_action_count: 0,
      last_action_at: null,
    },
    over
  );
}

describe("cockpit_workload.js — Lastverteilung (Build 351)", () => {
  // WL01 -------------------------------------------------------------------
  it("WL01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.echartsOption).toBe("function");
    expect(typeof api.renderWorkload).toBe("function");
  });

  // WL02 -------------------------------------------------------------------
  it("WL02: nameLabel Fallbacks", () => {
    const api = _api();
    expect(api.nameLabel(L({ display_name: "Chefin" }))).toBe("Chefin");
    expect(
      api.nameLabel(L({ display_name: null, system_username: "h009" }))
    ).toBe("h009");
    expect(api.nameLabel(L({ display_name: null, system_username: null }))).toBe(
      "?"
    );
  });

  // WL03 -------------------------------------------------------------------
  it("WL03: echartsOption Kategorien + Serien", () => {
    const api = _api();
    const data = {
      scope: "alle",
      count: 3,
      loads: [
        L({ display_name: "A", ampel_rot: 3, ampel_gelb: 1, ampel_gruen: 0 }),
        L({ display_name: "B", ampel_rot: 1, ampel_gelb: 2, ampel_gruen: 4 }),
        L({ display_name: "(nicht zugewiesen)", is_backlog: true, ampel_rot: 0, ampel_gelb: 0, ampel_gruen: 5 }),
      ],
    };
    const opt = api.echartsOption(data);
    expect(opt.yAxis.data).toEqual(["A", "B", "(nicht zugewiesen)"]);
    expect(opt.yAxis.inverse).toBe(true);
    expect(opt.series.length).toBe(3);
    expect(opt.series.map((s) => s.name)).toEqual(["Rot", "Gelb", "Gruen"]);
    expect(opt.series[0].data).toEqual([3, 1, 0]); // Rot
    expect(opt.series[1].data).toEqual([1, 2, 0]); // Gelb
    expect(opt.series[2].data).toEqual([0, 4, 5]); // Gruen
  });

  // WL04 -------------------------------------------------------------------
  it("WL04: Farben + stack", () => {
    const api = _api();
    const opt = api.echartsOption({ loads: [L({})] });
    expect(opt.color).toEqual([api.COL_ROT, api.COL_GELB, api.COL_GRUEN]);
    opt.series.forEach((s) => expect(s.stack).toBe("ampel"));
  });

  // WL05 -------------------------------------------------------------------
  it("WL05: leere loads", () => {
    const api = _api();
    const opt = api.echartsOption({ scope: "alle", count: 0, loads: [] });
    expect(opt.yAxis.data).toEqual([]);
    expect(opt.series[0].data).toEqual([]);
  });

  // WL06 -------------------------------------------------------------------
  it("WL06: renderWorkload Kopf + Stub-ECharts", () => {
    const win = _makeContext();
    const api = win.AIWCockpitWorkload;
    const main = win.document.createElement("main");

    let captured = null;
    let initEl = null;
    const stubChart = {
      setOption: (o) => {
        captured = o;
      },
      dispose: () => {},
      resize: () => {},
    };
    const StubECharts = {
      init: (el) => {
        initEl = el;
        return stubChart;
      },
    };

    const data = {
      scope: "alle",
      count: 2,
      loads: [
        L({ display_name: "A", ampel_rot: 2 }),
        L({ display_name: "B", ampel_gruen: 1 }),
      ],
    };
    const inst = api.renderWorkload(main, data, { ECharts: StubECharts });

    expect(inst).toBe(stubChart);
    expect(main.querySelector(".aiw-pagehead").textContent).toBe(
      "Lastverteilung"
    );
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("alle");
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("2 Zeilen");
    // ECharts.init bekam den Chart-Container; setOption die richtige Option.
    expect(initEl.id).toBe("aiw-workload-chart");
    expect(captured.yAxis.data).toEqual(["A", "B"]);
  });

  // WL07 -------------------------------------------------------------------
  it("WL07: renderWorkload ohne ECharts -> null + Hinweis", () => {
    const win = _makeContext();
    const api = win.AIWCockpitWorkload;
    const main = win.document.createElement("main");
    const inst = api.renderWorkload(main, { scope: "alle", loads: [] }, {
      ECharts: null,
    });
    expect(inst).toBe(null);
    expect(main.querySelector(".aiw-placeholder")).toBeTruthy();
  });
});
