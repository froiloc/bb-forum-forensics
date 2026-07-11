/**
 * tests/unit/test_cockpit_policy.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Rechte / Policy
 *
 * Testsuite fuer management/server/static/cockpit_policy.js (Build 362).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitPolicy).
 *
 * PO01 — API verfuegbar.
 * PO02 — capLabelIndex + grantRows: Label-Anreicherung.
 * PO03 — assignmentRows: Personen-Zuweisungen.
 * PO04 — renderPolicy: Kopf/counts + zwei Tabulator-Instanzen + Katalog.
 * PO05 — renderPolicy ohne Tabulator: Platzhalter + [] + Katalog dennoch da.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_policy.js",
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

function _api() {
  return _ctx().AIWCockpitPolicy;
}

function _data() {
  return {
    scope: "alle",
    roles: [{ code: "supervisor", label: "Chef-Ermittlerin" },
            { code: "investigator", label: "Ermittler:in" }],
    capabilities: [{ code: "policy.view", label: "RBAC-Richtlinie einsehen" },
                   { code: "mycases.view", label: "Eigene Faelle sehen" }],
    grants: [
      { role_code: "supervisor", capability_code: "policy.view",
        scope: "alle", audit_seq: 42, note: "" },
      { role_code: "investigator", capability_code: "mycases.view",
        scope: "eigene", audit_seq: 43, note: "PoC" },
    ],
    assignments: [
      { person_id: 5, system_username: "h0a2898", display_name: "Chefin",
        role_code: "supervisor", audit_seq: 37 },
    ],
    counts: { roles: 2, capabilities: 2, grants: 2, assignments: 1 },
  };
}

describe("cockpit_policy.js — Rechte/Policy (Build 362)", () => {
  it("PO01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.grantRows).toBe("function");
    expect(typeof api.assignmentRows).toBe("function");
    expect(typeof api.renderPolicy).toBe("function");
  });

  it("PO02: capLabelIndex + grantRows", () => {
    const api = _api();
    const idx = api.capLabelIndex(_data());
    expect(idx["policy.view"]).toBe("RBAC-Richtlinie einsehen");
    const rows = api.grantRows(_data());
    expect(rows.length).toBe(2);
    const first = rows[0];
    expect(first.role_code).toBe("supervisor");
    expect(first.capability_label).toBe("RBAC-Richtlinie einsehen");
    expect(rows[1].scope).toBe("eigene");
    expect(rows[1].note).toBe("PoC");
  });

  it("PO03: assignmentRows", () => {
    const api = _api();
    const rows = api.assignmentRows(_data());
    expect(rows.length).toBe(1);
    expect(rows[0].display_name).toBe("Chefin");
    expect(rows[0].system_username).toBe("h0a2898");
    expect(rows[0].role_code).toBe("supervisor");
  });

  it("PO04: renderPolicy — zwei Tabellen + Katalog", () => {
    const win = _ctx();
    const api = win.AIWCockpitPolicy;
    const main = win.document.createElement("main");

    const made = [];
    function StubTab(container, opts) {
      this.container = container;
      this.opts = opts;
      made.push(this);
    }
    StubTab.prototype.destroy = function () {};

    const tables = api.renderPolicy(main, _data(), { Tabulator: StubTab });
    expect(tables.length).toBe(2);
    expect(made.length).toBe(2);
    // Grants-Tabelle erhielt die angereicherten Zeilen.
    expect(made[0].opts.data[0].capability_label).toBe("RBAC-Richtlinie einsehen");
    // Zuweisungs-Tabelle.
    expect(made[1].opts.data[0].display_name).toBe("Chefin");
    // Kopf + counts.
    expect(main.querySelector(".aiw-pagehead").textContent).toBe("Rechte / Policy");
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("2 Grants");
    // Katalog gerendert.
    expect(main.querySelector(".aiw-policy-catalog")).toBeTruthy();
  });

  it("PO05: renderPolicy ohne Tabulator -> Platzhalter + []", () => {
    const win = _ctx();
    const api = win.AIWCockpitPolicy;
    const main = win.document.createElement("main");
    const tables = api.renderPolicy(main, _data(), { Tabulator: null });
    expect(tables).toEqual([]);
    expect(main.querySelector(".aiw-placeholder")).toBeTruthy();
    // Katalog wird auch ohne Tabulator gezeigt.
    expect(main.querySelector(".aiw-policy-catalog")).toBeTruthy();
  });
});
