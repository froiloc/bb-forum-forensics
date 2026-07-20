/**
 * tests/unit/test_cockpit_onboarding.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Onboarding/Offboarding
 *
 * Testsuite fuer management/server/static/cockpit_onboarding.js (Build 465).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitOnboarding).
 *
 * OB01 — API verfuegbar.
 * OB02 — Helfer: statusDotClass, stepActions (aktueller Zustand nicht dabei).
 * OB03 — data===null -> nur Auswahl + Platzhalter, keine Tabelle.
 * OB04 — Auswahl: ungueltige person_id -> onInvalid; gueltig -> onLoad.
 * OB05 — renderOnboarding mit Daten: Kopf, Kennzahlen, Fall-Last-Warnung,
 *        Tabelle; mit Recht Aktions-Buttons, ohne Recht keine.
 * OB06 — 'erledigt'/'zuruecksetzen' feuern sofort; 'nicht_zutreffend' verlangt
 *        Grund (Panel) — leer -> kein onStep; mit Grund -> onStep.
 * OB07 — Freitext (Notiz) XSS-sicher.
 *
 * Version: v0.7.465 · Build: 465 · 2026-07-20
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_onboarding.js",
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
  return _win().AIWCockpitOnboarding;
}

function _data() {
  return {
    person_id: 2,
    person: { display_name: "Mueller", system_username: "mueller" },
    kind: "offboarding",
    kind_label: "Offboarding (Ausscheiden aus der EK)",
    kinds: ["onboarding", "offboarding"],
    counts: { offen: 3, erledigt: 1, nicht_zutreffend: 1 },
    open_case_load: 2,
    steps: [
      { step_code: "rollen_entzogen", label: "Rollen/Rechte entzogen (RBAC)",
        status: "erledigt", status_label: "erledigt", note: null,
        requires_reason: false },
      { step_code: "faelle_umverteilt", label: "Offene Faelle umverteilt",
        status: "offen", status_label: "offen", note: null,
        requires_reason: false },
    ],
  };
}

describe("cockpit_onboarding.js — Onboarding/Offboarding (Build 465)", () => {
  // OB01 -------------------------------------------------------------------
  it("OB01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.renderOnboarding).toBe("function");
    expect(typeof api.stepActions).toBe("function");
  });

  // OB02 -------------------------------------------------------------------
  it("OB02: Helfer", () => {
    const api = _api();
    expect(api.statusDotClass("erledigt")).toBe("gruen");
    expect(api.statusDotClass("nicht_zutreffend")).toBe("grau");
    expect(api.statusDotClass("offen")).toBe("gelb");
    // aktueller Zustand ist NICHT unter den Aktionen.
    expect(api.stepActions("offen").sort()).toEqual(
      ["erledigt", "nicht_zutreffend"]
    );
    expect(api.stepActions("erledigt")).not.toContain("erledigt");
  });

  // OB03 -------------------------------------------------------------------
  it("OB03: data null -> nur Auswahl + Platzhalter", () => {
    const win = _win();
    const doc = win.document;
    const main = doc.createElement("main");
    win.AIWCockpitOnboarding.renderOnboarding(main, null,
      { canEdit: true, doc: doc });
    expect(main.querySelector("#aiw-onb-show")).toBeTruthy();
    expect(main.querySelector(".aiw-placeholder")).toBeTruthy();
    expect(main.querySelector(".aiw-onb-table")).toBe(null);
  });

  // OB04 -------------------------------------------------------------------
  it("OB04: Auswahl validiert + onLoad", () => {
    const win = _win();
    const doc = win.document;
    const main = doc.createElement("main");
    const loads = [];
    const invalid = [];
    win.AIWCockpitOnboarding.renderOnboarding(main, null, {
      canEdit: true, doc: doc,
      onLoad: (s) => loads.push(s),
      onInvalid: (m) => invalid.push(m),
    });
    main.querySelector("#aiw-onb-person").value = "abc";
    main.querySelector("#aiw-onb-show").click();
    expect(loads.length).toBe(0);
    expect(invalid.length).toBe(1);

    main.querySelector("#aiw-onb-person").value = "2";
    // kind-Auswahl auf offboarding
    main.querySelector("#aiw-onb-kind").value = "offboarding";
    main.querySelector("#aiw-onb-show").click();
    expect(loads.length).toBe(1);
    expect(loads[0]).toEqual({ personId: 2, kind: "offboarding" });
  });

  // OB05 -------------------------------------------------------------------
  it("OB05: renderOnboarding mit Daten", () => {
    const win = _win();
    const doc = win.document;

    const main = doc.createElement("main");
    win.AIWCockpitOnboarding.renderOnboarding(main, _data(),
      { canEdit: true, doc: doc });
    expect(main.querySelector(".aiw-onb-head").textContent).toContain("Mueller");
    expect(main.querySelector(".aiw-onb-load-warn")).toBeTruthy(); // 2 offene Faelle
    expect(main.querySelectorAll(".aiw-onb-table tbody tr").length).toBe(2);
    // 'offen'-Schritt (faelle_umverteilt) -> 2 Aktionen (erledigt, n.z.).
    expect(
      main.querySelectorAll('button[data-step="faelle_umverteilt"]').length
    ).toBe(2);

    const ro = doc.createElement("main");
    win.AIWCockpitOnboarding.renderOnboarding(ro, _data(),
      { canEdit: false, doc: doc });
    expect(ro.querySelector(".aiw-onb-readonly")).toBeTruthy();
    expect(ro.querySelectorAll("button[data-target]").length).toBe(0);
  });

  // OB06 -------------------------------------------------------------------
  it("OB06: Aktionen + Grund-Pflicht bei nicht_zutreffend", () => {
    const win = _win();
    const doc = win.document;
    const main = doc.createElement("main");
    const steps = [];
    win.AIWCockpitOnboarding.renderOnboarding(main, _data(), {
      canEdit: true, doc: doc, onStep: (b) => steps.push(b),
    });

    // 'erledigt' an faelle_umverteilt -> sofort.
    main.querySelector(
      'button[data-step="faelle_umverteilt"][data-target="erledigt"]'
    ).click();
    expect(steps.length).toBe(1);
    expect(steps[0]).toEqual({
      person_id: 2, kind: "offboarding", step_code: "faelle_umverteilt",
      status: "erledigt", note: "",
    });

    // 'nicht_zutreffend' -> Panel; leerer Grund -> kein onStep.
    main.querySelector(
      'button[data-step="faelle_umverteilt"][data-target="nicht_zutreffend"]'
    ).click();
    main.querySelector("#aiw-onb-reason-confirm").click();
    expect(steps.length).toBe(1);
    expect(main.querySelector("#aiw-onb-result").className).toContain("error");

    // mit Grund -> onStep.
    main.querySelector(
      'button[data-step="faelle_umverteilt"][data-target="nicht_zutreffend"]'
    ).click();
    main.querySelector("#aiw-onb-reason").value = "extern erledigt";
    main.querySelector("#aiw-onb-reason-confirm").click();
    expect(steps.length).toBe(2);
    expect(steps[1].status).toBe("nicht_zutreffend");
    expect(steps[1].note).toBe("extern erledigt");
  });

  // OB07 -------------------------------------------------------------------
  it("OB07: Notiz XSS-sicher", () => {
    const win = _win();
    const doc = win.document;
    const main = doc.createElement("main");
    const data = _data();
    data.steps[0].note = "<img src=x onerror=alert(1)>";
    win.AIWCockpitOnboarding.renderOnboarding(main, data,
      { canEdit: false, doc: doc });
    expect(main.querySelector("img")).toBe(null);
    expect(main.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
