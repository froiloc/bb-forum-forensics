/**
 * tests/unit/test_cockpit_stats.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Statistiken
 *
 * Testsuite fuer management/server/static/cockpit_stats.js (Build 371).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitStats).
 *
 * SS01 — API verfuegbar.
 * SS02 — barOption: Achsen/Serie aus {schluessel: anzahl}.
 * SS03 — throughputOption: Linie aus [{day, count}].
 * SS04 — assigneeRows: by_assignee + (nicht zugewiesen).
 * SS05 — renderStats: Tabs + Charts + Tabelle; Download-Buttons rufen Callbacks.
 * SS06 — Tab-Wechsel schaltet Sichtbarkeit um (resize wird gerufen).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_stats.js",
  "utf-8"
);

// Build 552: das gemeinsame Tabellen-Werkzeug MUSS im Kontext liegen — genau
// wie im Browser. Ohne es faellt der Reiter "Ermittler" in seinen Ersatzpfad.
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
function _api() { return _ctx().AIWCockpitStats; }

function _data() {
  return {
    scope: "alle",
    generated_at: 1000,
    totals: { cases: 4, assigned: 3, unassigned: 1, events: 12 },
    by_status: { open: 2, in_progress: 1, approved: 1, closed: 0 },
    by_priority: { "1": 0, "2": 1, "3": 3, "4": 0, "5": 0 },
    by_ampel: { gruen: 2, gelb: 1, rot: 1 },
    by_assignee: [
      { person_id: 2, display_name: "Mueller", count: 2 },
      { person_id: 3, display_name: "Gamma", count: 1 },
    ],
    throughput_by_day: [
      { day: "2026-07-09", count: 3 },
      { day: "2026-07-10", count: 7 },
    ],
  };
}

// Stub-ECharts: jede init-Instanz merkt sich setOption + zaehlt resize.
function makeStubECharts(registry) {
  return {
    init: function (div) {
      var inst = {
        div: div, option: null, resizeCount: 0,
        setOption: function (o) { this.option = o; },
        resize: function () { this.resizeCount++; },
        dispose: function () {},
      };
      registry.push(inst);
      return inst;
    },
  };
}
function StubTab(container, opts) { this.opts = opts; }
StubTab.prototype.redraw = function () {};
StubTab.prototype.destroy = function () {};

describe("cockpit_stats.js — Statistiken (Build 371)", () => {
  it("SS01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.barOption).toBe("function");
    expect(typeof api.renderStats).toBe("function");
  });

  it("SS02: barOption", () => {
    const api = _api();
    const opt = api.barOption("Status", { open: 2, closed: 0 });
    expect(opt.xAxis.data).toEqual(["open", "closed"]);
    expect(opt.series[0].data).toEqual([2, 0]);
    expect(opt.series[0].type).toBe("bar");
  });

  it("SS03: throughputOption", () => {
    const api = _api();
    const opt = api.throughputOption([{ day: "2026-07-10", count: 7 }]);
    expect(opt.xAxis.data).toEqual(["2026-07-10"]);
    expect(opt.series[0].data).toEqual([7]);
    expect(opt.series[0].type).toBe("line");
  });

  it("SS04: assigneeRows", () => {
    const api = _api();
    const rows = api.assigneeRows(_data());
    expect(rows.length).toBe(3); // 2 Ermittler + (nicht zugewiesen)
    expect(rows[0]).toEqual({ ermittler: "Mueller", anzahl: 2 });
    expect(rows[2]).toEqual({ ermittler: "(nicht zugewiesen)", anzahl: 1 });
  });

  it("SS05: renderStats — Tabs, Charts, Tabelle, Downloads", () => {
    const win = _ctx();
    const api = win.AIWCockpitStats;
    const main = win.document.createElement("main");
    const charts = [];
    let csvClicks = 0, jsonClicks = 0;

    const res = api.renderStats(main, _data(), {
      ECharts: makeStubECharts(charts),
      Tabulator: StubTab,
      onDownloadCsv: function () { csvClicks++; },
      onDownloadJson: function (d) { jsonClicks++; expect(d.totals.cases).toBe(4); },
    });

    // 4 Charts (Status/Prio/Ampel + Durchsatz), 1 Tabelle.
    expect(res.charts.length).toBe(4);
    expect(res.tables.length).toBe(1);
    // Drei Tab-Buttons.
    expect(main.querySelectorAll(".aiw-tab").length).toBe(3);
    // Download-Buttons wired.
    main.querySelector("#aiw-stats-csv").click();
    main.querySelector("#aiw-stats-json").click();
    expect(csvClicks).toBe(1);
    expect(jsonClicks).toBe(1);
    // Kopf + Summen-Text.
    expect(main.querySelector(".aiw-pagehead").textContent)
      .toContain("Statistiken");
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("4 Faelle");
  });

  it("SS06: Tab-Wechsel schaltet Sichtbarkeit + resize", () => {
    const win = _ctx();
    const api = win.AIWCockpitStats;
    const main = win.document.createElement("main");
    const charts = [];
    api.renderStats(main, _data(), {
      ECharts: makeStubECharts(charts),
      Tabulator: StubTab,
    });
    const flowContent = main.querySelector('.aiw-tabcontent[data-tab="flow"]');
    expect(flowContent.style.display).toBe("none"); // initial versteckt
    const flowBtn = main.querySelector('.aiw-tab[data-tab="flow"]');
    flowBtn.click();
    expect(flowContent.style.display).toBe("block"); // jetzt sichtbar
    // Der Durchsatz-Chart (letzte init-Instanz) wurde beim Wechsel resized.
    const flowChart = charts[charts.length - 1];
    expect(flowChart.resizeCount).toBeGreaterThanOrEqual(1);
  });
});
