/**
 * tests/unit/test_cockpit_capacity.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Kapazitaet
 *
 * Testsuite fuer management/server/static/cockpit_capacity.js (Build 360).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitCapacity).
 *
 * CA01 — API verfuegbar.
 * CA02 — utilization: netto/basis; null bei basis<=0.
 * CA03 — utilColor: Schwellen gruen/gelb/rot; grau bei null.
 * CA04 — sortRows: stark reduzierte zuerst, basis-lose ans Ende.
 * CA05 — echartsOption: Basis+Netto-Serien, Netto-Farben, yAxis.inverse.
 * CA06 — defaultPeriod: erster/letzter Tag des laufenden Monats.
 * CA07 — renderCapacity: Kopf/Zeitraum + Stub-ECharts; onPeriodChange bei Klick.
 * CA08 — renderCapacity ohne ECharts -> null + Hinweis.
 */

import { describe, it, expect, vi } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_capacity.js",
  "utf-8"
);
// Build 663: der ECHTE Datumspaar-Baustein, nicht ein Nachbau.
const _dpSrc = readFileSync(
  "management/server/static/cockpit_datumspaar.js",
  "utf-8"
);

function _ctx(mitDatumspaar) {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  if (mitDatumspaar !== false) { dom.window.eval(_dpSrc); }
  dom.window.eval(_src);
  return dom.window;
}

function _api() {
  return _ctx().AIWCockpitCapacity;
}

function C(over) {
  return Object.assign(
    { person_id: 1, system_username: "h1", display_name: "A",
      basis: 2400, einschraenkungen: 0, garantie_boden: 0, netto: 2400 },
    over
  );
}

describe("cockpit_capacity.js — Kapazitaet (Build 360)", () => {
  it("CA01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.echartsOption).toBe("function");
    expect(typeof api.renderCapacity).toBe("function");
    expect(typeof api.defaultPeriod).toBe("function");
  });

  it("CA02: utilization", () => {
    const api = _api();
    expect(api.utilization(C({ basis: 2400, netto: 1200 }))).toBeCloseTo(0.5);
    expect(api.utilization(C({ basis: 0, netto: 0 }))).toBe(null);
  });

  it("CA03: utilColor Schwellen", () => {
    const api = _api();
    expect(api.utilColor(0.9)).toBe(api.COL_GRUEN);
    expect(api.utilColor(0.6)).toBe(api.COL_GELB);
    expect(api.utilColor(0.3)).toBe(api.COL_ROT);
    expect(api.utilColor(null)).toBe(api.COL_GRAU);
  });

  it("CA04: sortRows — reduzierte zuerst, basis-lose ans Ende", () => {
    const api = _api();
    const rows = [
      C({ person_id: 1, display_name: "voll", basis: 2400, netto: 2400 }), // 1.0
      C({ person_id: 2, display_name: "leer", basis: 0, netto: 0 }),       // null
      C({ person_id: 3, display_name: "halb", basis: 2400, netto: 1200 }), // 0.5
    ];
    const sorted = api.sortRows(rows).map((c) => c.display_name);
    expect(sorted).toEqual(["halb", "voll", "leer"]);
  });

  it("CA05: echartsOption Serien + Farben", () => {
    const api = _api();
    const data = {
      scope: "alle", count: 2, start: "2026-07-01", end: "2026-07-31",
      capacities: [
        C({ person_id: 1, display_name: "A", basis: 2400, netto: 2400 }),
        C({ person_id: 2, display_name: "B", basis: 2400, netto: 600 }),
      ],
    };
    const opt = api.echartsOption(data);
    expect(opt.series.map((s) => s.name)).toEqual(["Basis", "Netto"]);
    expect(opt.yAxis.inverse).toBe(true);
    // B (util 0.25 -> rot) muss oben stehen (inverse) -> Kategorie-Index 0.
    expect(opt.yAxis.data[0]).toBe("B");
    // Netto-Balken B ist rot gefaerbt.
    const nettoB = opt.series[1].data[0];
    expect(nettoB.itemStyle.color).toBe(api.COL_ROT);
  });

  it("CA06: defaultPeriod laufender Monat", () => {
    const api = _api();
    const p = api.defaultPeriod(new Date(2026, 1, 15)); // Februar 2026
    expect(p.start).toBe("2026-02-01");
    expect(p.end).toBe("2026-02-28");
  });

  it("CA07: renderCapacity Kopf + onPeriodChange", () => {
    const win = _ctx();
    const api = win.AIWCockpitCapacity;
    const main = win.document.createElement("main");

    let captured = null;
    const stubChart = { setOption: (o) => { captured = o; },
                        dispose: () => {}, resize: () => {} };
    const StubECharts = { init: () => stubChart };

    const changes = [];
    const data = {
      scope: "alle", count: 1, start: "2026-07-01", end: "2026-07-31",
      capacities: [C({})],
    };
    const inst = api.renderCapacity(main, data, {
      ECharts: StubECharts,
      onPeriodChange: (s, e) => changes.push([s, e]),
    });
    expect(inst).toBe(stubChart);
    expect(main.querySelector(".aiw-pagehead").textContent).toBe("Kapazitaet");
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("2026-07-01");
    expect(captured.yAxis.data).toEqual(["A"]);
    // Zeitraum-Felder vorbelegt, Button loest onPeriodChange aus.
    expect(main.querySelector("#aiw-cap-start").value).toBe("2026-07-01");
    main.querySelector("#aiw-cap-end").value = "2026-08-31";
    main.querySelector("#aiw-cap-reload").click();
    expect(changes[changes.length - 1]).toEqual(["2026-07-01", "2026-08-31"]);
  });

  it("CA08: renderCapacity ohne ECharts -> null + Hinweis", () => {
    const win = _ctx();
    const api = win.AIWCockpitCapacity;
    const main = win.document.createElement("main");
    const inst = api.renderCapacity(main,
      { scope: "alle", start: "2026-07-01", end: "2026-07-31", capacities: [] },
      { ECharts: null });
    expect(inst).toBe(null);
    expect(main.querySelector(".aiw-placeholder")).toBeTruthy();
  });

  // CA09 (Build 663, Ticket d3f933cd) ----------------------------------------
  it("CA09: Zeitraum -- Schranke JA, Uebernahme NEIN", () => {
    const win = _ctx();
    const api = win.AIWCockpitCapacity;
    const main = win.document.createElement("main");
    win.document.body.appendChild(main);
    api.renderCapacity(main,
      { scope: "alle", start: "", end: "", capacities: [] },
      { ECharts: null });
    const von = main.querySelector("#aiw-cap-start");
    const bis = main.querySelector("#aiw-cap-end");
    von.value = "2026-07-01";
    von.dispatchEvent(new win.Event("change"));
    // Die Schranke ist auch hier richtig: ein Ende vor dem Anfang ist unsinnig.
    expect(bis.getAttribute("min")).toBe("2026-07-01");
    // Die UEBERNAHME waere hier ein Schaden: ein leeres Bis-Feld heisst in
    // einer Zeitraumwahl "ohne obere Grenze". Spraenge es auf den Von-Tag,
    // schrumpfte die Auswertung stillschweigend auf 24 Stunden.
    expect(bis.value).toBe("");
  });

  // CA10 (Build 663) ---------------------------------------------------------
  it("CA10: ohne Datumspaar-Baustein bleibt die Zeitraumwahl bedienbar", () => {
    const win = _ctx(false);
    expect(win.AIWDatumspaar).toBeUndefined();
    const api = win.AIWCockpitCapacity;
    const main = win.document.createElement("main");
    win.document.body.appendChild(main);
    const changes = [];
    api.renderCapacity(main,
      { scope: "alle", start: "2026-07-01", end: "2026-07-31", capacities: [] },
      { ECharts: null, onPeriodChange: (a, b) => changes.push([a, b]) });
    main.querySelector("#aiw-cap-reload").click();
    expect(changes[0]).toEqual(["2026-07-01", "2026-07-31"]);
  });
});
