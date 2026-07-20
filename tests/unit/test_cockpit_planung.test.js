/**
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 * tests/unit/test_cockpit_planung.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Prognose & Gantt
 *
 * Testsuite fuer management/server/static/cockpit_planung.js (Build 448).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitPlanung) —
 * kein dupliziertes Logik-Abbild.
 *
 * PL01 — API verfuegbar (window.AIWCockpitPlanung).
 * PL02 — forecastRows: mappt Szenarien; days=null bleibt null (ehrlich).
 * PL03 — forecastOption: Balken-Serie, Kategorien = Szenarionamen, Farben.
 * PL04 — ganttTasks: flacht Lanes zu Tasks, ts*1000 (ms), ongoing uebernommen.
 * PL05 — ganttOption: custom-Serie, data-Laenge = Taskzahl, xAxis time.
 * PL06 — fmtDate: ISO-Datum (UTC); null -> '-'.
 * PL07 — renderPlanung: Tabelle mit 'unbestimmt' bei days=null; Annahmen gelistet.
 * PL08 — renderPlanung: 2 Charts bei vorhandenem ECharts; XSS-sicher (textContent).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_planung.js",
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

function _api() {
  return _win().AIWCockpitPlanung;
}

function _forecast(over) {
  return Object.assign({
    now_day: "2026-07-19", backlog: 10, lookback_days: 30,
    completions_observed: 5, observed_rate_per_day: 0.1667,
    data_sufficient: true,
    scenarios: [
      { name: "optimistisch", factor: 1.25, rate_per_day: 0.2083,
        days_to_clear: 48, finish_day: "2026-09-05" },
      { name: "erwartet", factor: 1.0, rate_per_day: 0.1667,
        days_to_clear: 60, finish_day: "2026-09-17" },
      { name: "pessimistisch", factor: 0.75, rate_per_day: 0.125,
        days_to_clear: 80, finish_day: "2026-10-07" },
    ],
    assumptions: ["Backlog = open/in_progress.", "Rate aus approved-Ereignissen."],
    capacity_context: null,
  }, over || {});
}

function _gantt() {
  return {
    now_ts: 1700000000, range_start: 1699000000, range_end: 1700000000,
    total_bars: 2,
    lanes: [
      { assignee_id: 1, assignee_name: "Müller, A", bars: [
        { subject_id: 4711, username: "täter_süd", status: "approved",
          assignee_id: 1, assignee_name: "Müller, A",
          start_ts: 1699000000, end_ts: 1699500000, ongoing: false,
          completed_ts: 1699500000 }] },
      { assignee_id: null, assignee_name: "Rueckstau", bars: [
        { subject_id: 4712, username: "<script>x", status: "open",
          assignee_id: null, assignee_name: null,
          start_ts: 1699200000, end_ts: 1700000000, ongoing: true,
          completed_ts: null }] },
    ],
  };
}

function _fakeECharts() {
  const insts = [];
  return {
    _insts: insts,
    init() {
      const inst = {
        opt: null, setOption(o) { this.opt = o; },
        resize() {}, dispose() {},
      };
      insts.push(inst);
      return inst;
    },
  };
}

describe("cockpit_planung.js — Prognose & Gantt (Build 448)", () => {
  it("PL01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.renderPlanung).toBe("function");
    expect(typeof api.forecastOption).toBe("function");
  });

  it("PL02: forecastRows mappt; days=null bleibt null", () => {
    const api = _api();
    const rows = api.forecastRows(_forecast({
      scenarios: [{ name: "erwartet", factor: 1, rate_per_day: 0,
        days_to_clear: null, finish_day: null }] }));
    expect(rows).toHaveLength(1);
    expect(rows[0].days).toBeNull();
    expect(rows[0].finish).toBeNull();
  });

  it("PL03: forecastOption Balken + Kategorien + Farbe", () => {
    const api = _api();
    const opt = api.forecastOption(_forecast());
    expect(opt.series[0].type).toBe("bar");
    expect(opt.yAxis.data).toEqual(["optimistisch", "erwartet", "pessimistisch"]);
    expect(opt.series[0].data[0].itemStyle.color).toBe(api.SCEN_COL.optimistisch);
  });

  it("PL04: ganttTasks flacht Lanes, ms-Konvertierung", () => {
    const api = _api();
    const tasks = api.ganttTasks(_gantt());
    expect(tasks).toHaveLength(2);
    expect(tasks[0].startMs).toBe(1699000000 * 1000);
    expect(tasks[1].ongoing).toBe(true);
    expect(tasks[0].lane).toBe("Müller, A");
  });

  it("PL05: ganttOption custom-Serie, data-Laenge, time-Achse", () => {
    const api = _api();
    const opt = api.ganttOption(_gantt());
    expect(opt.series[0].type).toBe("custom");
    expect(opt.series[0].data).toHaveLength(2);
    expect(opt.xAxis.type).toBe("time");
    expect(typeof opt.series[0].renderItem).toBe("function");
  });

  it("PL06: fmtDate ISO/UTC; null -> '-'", () => {
    const api = _api();
    expect(api.fmtDate(1699000000)).toBe("2023-11-03");
    expect(api.fmtDate(null)).toBe("-");
  });

  it("PL07: renderPlanung Tabelle 'unbestimmt' + Annahmen", () => {
    const win = _win();
    const api = win.AIWCockpitPlanung;
    const main = win.document.createElement("div");
    const fc = _forecast({
      data_sufficient: false,
      scenarios: [{ name: "erwartet", factor: 1, rate_per_day: 0,
        days_to_clear: null, finish_day: null }],
      assumptions: ["Keine Abschluesse -> keine Prognose."],
    });
    api.renderPlanung(main, { forecast: fc, gantt: _gantt() },
      { ECharts: _fakeECharts() });
    expect(main.textContent).toContain("unbestimmt");
    expect(main.querySelectorAll("ul.aiw-assumptions li").length).toBe(1);
  });

  it("PL08: renderPlanung 2 Charts; XSS-sicher via textContent", () => {
    const win = _win();
    const api = win.AIWCockpitPlanung;
    const main = win.document.createElement("div");
    const echarts = _fakeECharts();
    const charts = api.renderPlanung(main, { forecast: _forecast(), gantt: _gantt() },
      { ECharts: echarts });
    expect(charts).toHaveLength(2);
    // Gantt-Task mit gefaehrlichem Benutzernamen darf NICHT als Markup landen.
    expect(main.innerHTML).not.toContain("<script>x");
  });
});
