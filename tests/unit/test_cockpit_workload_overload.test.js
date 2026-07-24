/**
 * tests/unit/test_cockpit_workload_overload.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Lastverteilung
 *
 * Testsuite fuer Build 514 (AP-2F / Idee 21): die AKTIVE UEBERLASTWARNUNG im
 * Banner ueber dem Lastdiagramm. Getestet wird der ECHTE Code
 * (readFileSync + JSDOM, window.AIWCockpitWorkload) — keine Nachbildung.
 *
 * Die Testfaelle bilden die fuenf Bannerregeln aus dem Dateikopf von
 * cockpit_workload.js ab. Sie pruefen NICHT die Bewertungslogik (die liegt im
 * Backend und ist dort belegt), sondern ob die Sicht das Ergebnis
 * VOLLSTAENDIG und UNVERFAELSCHT wiedergibt.
 *
 * UO01 — API vollstaendig verfuegbar (alle reinen Funktionen exportiert)
 * UO02 — overloadLevel(): none / ok / warn / overload aus den Zaehlern
 * UO03 — overloadLevel(): Rueckstau-Alarm allein ergibt 'warn' (systemisch,
 *        NICHT 'overload' — es ist keine Personen-Ueberlast)
 * UO04 — R1: die Begruendung kommt WOERTLICH aus dem Backend (reasons)
 * UO05 — R2: thresholdText() nennt alle drei angewandten Schwellen
 * UO06 — R3: die Unauffaelligen werden GEZAEHLT und genannt
 * UO07 — R4: scope_limited wird benannt UND die nicht erhobene Rueckstau-Zahl
 *        wird NICHT als Leerbefund ausgegeben
 * UO08 — R5: fehlender overload-Block -> 'none' + ausdrueckliche Ansage
 * UO09 — renderOverloadBanner(): Banner erscheint IMMER, mit data-level
 * UO10 — renderOverloadBanner(): jede Zeile aus overloadLines() steht als <li>
 *        im DOM — nichts wird beim Rendern verschluckt
 * UO11 — XSS/Markup: ein Anzeigename mit Markup landet als TEXT, nicht als DOM
 *        (multilingualer Bestand, Namen sind ungeprueftes Fremdmaterial)
 * UO12 — renderWorkload(): das Banner steht VOR dem Diagramm-Container
 *
 * Version: v0.8.514 · Build: 514 · 2026-07-24
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

// Ueberlast-Block in der Form aus Build 513 (flache Skalare).
function OV(over) {
  return Object.assign(
    {
      generated_at: 1750000000,
      max_active_cases: 10,
      max_red_cases: 3,
      backlog_alert: 5,
      overloaded_count: 0,
      warned_count: 0,
      backlog_size: 0,
      backlog_alarm: false,
      scope_limited: false,
    },
    over
  );
}

// Eine Bewertungszeile (overload_assessments).
function A(over) {
  return Object.assign(
    {
      investigator_id: 1,
      name: "Alpha",
      active_cases: 1,
      red_cases: 0,
      total_cases: 1,
      level: "ok",
      reasons: [],
    },
    over
  );
}

// Vollstaendige /api/workload-Antwort.
function D(over) {
  return Object.assign(
    { scope: "alle", count: 0, loads: [], overload: OV(), overload_assessments: [] },
    over
  );
}

describe("cockpit_workload.js — Ueberlastwarnung (Build 514)", () => {
  // UO01 --------------------------------------------------------------------
  it("UO01: API vollstaendig", () => {
    const api = _api();
    [
      "overloadOf",
      "assessmentsOf",
      "overloadLevel",
      "overloadTitle",
      "thresholdText",
      "assessmentLine",
      "overloadLines",
      "renderOverloadBanner",
    ].forEach((n) => {
      expect(typeof api[n], n).toBe("function");
    });
  });

  // UO02 --------------------------------------------------------------------
  it("UO02: overloadLevel aus den Zaehlern", () => {
    const api = _api();
    expect(api.overloadLevel({})).toBe("none");
    expect(api.overloadLevel(D())).toBe("ok");
    expect(api.overloadLevel(D({ overload: OV({ warned_count: 1 }) }))).toBe(
      "warn"
    );
    expect(
      api.overloadLevel(D({ overload: OV({ overloaded_count: 1 }) }))
    ).toBe("overload");
    // Ueberlast schlaegt Warnung.
    expect(
      api.overloadLevel(
        D({ overload: OV({ overloaded_count: 1, warned_count: 3 }) })
      )
    ).toBe("overload");
  });

  // UO03 --------------------------------------------------------------------
  it("UO03: Rueckstau-Alarm allein ist 'warn', nicht 'overload'", () => {
    const api = _api();
    const d = D({ overload: OV({ backlog_alarm: true, backlog_size: 9 }) });
    expect(api.overloadLevel(d)).toBe("warn");
    // ... und er wird als eigene Zeile benannt (R1: nichts still).
    const lines = api.overloadLines(d);
    expect(lines.some((l) => l.includes("Rückstau: 9"))).toBe(true);
    expect(lines.some((l) => l.includes("Alarm ab 5"))).toBe(true);
    expect(api.overloadTitle("warn", d.overload)).toContain("Rückstau-Alarm");
  });

  // UO04 --------------------------------------------------------------------
  it("UO04: R1 — Begruendung woertlich aus dem Backend", () => {
    const api = _api();
    const grund = "aktive Faelle 12 > Grenze 10";
    const zeile = api.assessmentLine(
      A({ name: "Beta", level: "overload", reasons: [grund] })
    );
    expect(zeile).toContain("Beta");
    expect(zeile).toContain(grund);
    expect(zeile).toContain("ÜBER GRENZE");
    // 'warn' wird anders benannt als 'overload' — die Stufe muss lesbar sein.
    expect(
      api.assessmentLine(A({ name: "Beta", level: "warn", reasons: [grund] }))
    ).toContain("an Grenze");
    // Mehrere Ausloeser gehen ALLE mit.
    const zwei = api.assessmentLine(
      A({ level: "overload", reasons: ["Grund A", "Grund B"] })
    );
    expect(zwei).toContain("Grund A");
    expect(zwei).toContain("Grund B");
  });

  // UO05 --------------------------------------------------------------------
  it("UO05: R2 — alle drei angewandten Schwellen im Text", () => {
    const api = _api();
    const t = api.thresholdText(
      OV({ max_active_cases: 7, max_red_cases: 2, backlog_alert: 4 })
    );
    expect(t).toContain("7");
    expect(t).toContain("2");
    expect(t).toContain("4");
    expect(api.thresholdText(null)).toBe("");
  });

  // UO06 --------------------------------------------------------------------
  it("UO06: R3 — die Unauffaelligen werden gezaehlt", () => {
    const api = _api();
    const d = D({
      overload: OV({ overloaded_count: 1 }),
      overload_assessments: [
        A({ investigator_id: 2, name: "Beta", level: "overload", reasons: ["X"] }),
        A({ investigator_id: 1, name: "Alpha", level: "ok" }),
        A({ investigator_id: 3, name: "Gamma", level: "ok" }),
      ],
    });
    const lines = api.overloadLines(d);
    expect(lines.some((l) => l.includes("2 von 3 ohne Beanstandung"))).toBe(
      true
    );
    // Genau EINE beanstandete Zeile — die ok-Zeilen werden nicht einzeln
    // aufgefuehrt, aber sie sind gezaehlt (kein stiller Verzicht).
    expect(lines.filter((l) => l.includes("ÜBER GRENZE")).length).toBe(1);
  });

  // UO07 --------------------------------------------------------------------
  it("UO07: R4 — begrenzter Umfang wird benannt, keine Schein-Null", () => {
    const api = _api();
    const d = D({
      scope: "eigene",
      overload: OV({ scope_limited: true, backlog_size: 0 }),
      overload_assessments: [A({ level: "ok" })],
    });
    const lines = api.overloadLines(d);
    expect(lines.some((l) => l.includes("Umfang begrenzt"))).toBe(true);
    expect(lines.some((l) => l.includes("NICHT erhoben"))).toBe(true);
    // Die nicht erhobene Rueckstau-Zahl darf NICHT als Leerbefund erscheinen.
    expect(lines.some((l) => l.startsWith("Rückstau:"))).toBe(false);
    // Zum Gegenbeweis: bei vollem Umfang steht die Rueckstau-Zeile sehr wohl.
    const voll = D({ overload: OV({ backlog_size: 0 }) });
    expect(
      api.overloadLines(voll).some((l) => l.startsWith("Rückstau:"))
    ).toBe(true);
  });

  // UO08 --------------------------------------------------------------------
  it("UO08: R5 — fehlender Block wird ausdruecklich angesagt", () => {
    const api = _api();
    const d = { scope: "alle", count: 0, loads: [] };
    expect(api.overloadLevel(d)).toBe("none");
    const lines = api.overloadLines(d);
    expect(lines.length).toBe(1);
    expect(lines[0]).toContain("keinen Überlast-Block");
    expect(lines[0]).toContain("NICHT bewertet");
    expect(api.overloadTitle("none", null)).toContain("nicht verfügbar");
  });

  // UO09 --------------------------------------------------------------------
  it("UO09: Banner erscheint IMMER, mit data-level", () => {
    const win = _makeContext();
    const api = win.AIWCockpitWorkload;
    ["none", "ok", "warn", "overload"].forEach((erwartet) => {
      const parent = win.document.createElement("div");
      let d;
      if (erwartet === "none") {
        d = { scope: "alle", loads: [] };
      } else if (erwartet === "ok") {
        d = D();
      } else if (erwartet === "warn") {
        d = D({ overload: OV({ warned_count: 1 }) });
      } else {
        d = D({ overload: OV({ overloaded_count: 1 }) });
      }
      const box = api.renderOverloadBanner(parent, d);
      expect(box).toBeTruthy();
      expect(box.getAttribute("data-level")).toBe(erwartet);
      expect(box.className).toContain("is-" + erwartet);
      expect(parent.querySelector(".aiw-overload")).toBe(box);
    });
  });

  // UO10 --------------------------------------------------------------------
  it("UO10: jede Zeile aus overloadLines steht im DOM", () => {
    const win = _makeContext();
    const api = win.AIWCockpitWorkload;
    const d = D({
      overload: OV({ overloaded_count: 1, backlog_alarm: true, backlog_size: 8 }),
      overload_assessments: [
        A({ name: "Beta", level: "overload", reasons: ["aktive Faelle 12 > Grenze 10"] }),
        A({ name: "Alpha", level: "ok" }),
      ],
    });
    const parent = win.document.createElement("div");
    const box = api.renderOverloadBanner(parent, d);

    const erwartet = api.overloadLines(d);
    const gerendert = Array.from(box.querySelectorAll("li")).map(
      (li) => li.textContent
    );
    expect(gerendert).toEqual(erwartet);
    // Die Schwellen-Fussnote ist da (R2).
    expect(box.querySelector(".aiw-overload-foot").textContent).toContain("10");
  });

  // UO11 --------------------------------------------------------------------
  it("UO11: Markup im Anzeigenamen bleibt Text", () => {
    const win = _makeContext();
    const api = win.AIWCockpitWorkload;
    const boese = '<img src=x onerror="1">Пётр';
    const d = D({
      overload: OV({ overloaded_count: 1 }),
      overload_assessments: [
        A({ name: boese, level: "overload", reasons: ["Grund"] }),
      ],
    });
    const parent = win.document.createElement("div");
    const box = api.renderOverloadBanner(parent, d);
    expect(box.querySelector("img")).toBe(null);
    expect(box.textContent).toContain(boese);
    // UTF-8 bleibt unversehrt (multilinguales Forum).
    expect(box.textContent).toContain("Пётр");
  });

  // UO12 --------------------------------------------------------------------
  it("UO12: Banner steht VOR dem Diagramm", () => {
    const win = _makeContext();
    const api = win.AIWCockpitWorkload;
    const main = win.document.createElement("main");
    const stub = {
      init: () => ({ setOption: () => {}, dispose: () => {}, resize: () => {} }),
    };
    api.renderWorkload(main, D({ overload: OV({ warned_count: 1 }) }), {
      ECharts: stub,
    });
    const kinder = Array.from(main.children);
    const iBanner = kinder.findIndex((e) =>
      e.className.includes("aiw-overload")
    );
    const iChart = kinder.findIndex((e) => e.id === "aiw-workload-chart");
    expect(iBanner).toBeGreaterThan(-1);
    expect(iChart).toBeGreaterThan(-1);
    expect(iBanner).toBeLessThan(iChart);
  });
});
