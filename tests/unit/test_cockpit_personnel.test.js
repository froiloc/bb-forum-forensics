/**
 * Version: v0.8.503 · Build: 503 · 2026-07-24
 * tests/unit/test_cockpit_personnel.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Personalverwaltung
 *
 * Testsuite fuer management/server/static/cockpit_personnel.js (Build 503).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitPersonnel).
 *
 * PS01 — API verfuegbar (renderPersonnel + reine Funktionen).
 * PS02 — statusText: aktiv / inaktiv seit Datum (Grund).
 * PS03 — assignableRoles: nur noch nicht aktive Rollen; isSelf/canEditRow
 *        (Selbstschutz: eigene Zeile nie editierbar, auch mit can_edit).
 * PS04 — renderPersonnel: Tabelle mit Zeilen; eigene Zeile '(ich)' ohne
 *        Bedienelemente; XSS-sicher (textContent).
 * PS05 — Flag-Checkbox -> onFlags({person_id, <flag>}); Rollen-x ->
 *        onRevoke({person_role_id}); Dropdown -> onAssign.
 * PS06 — can_edit=false: keine Checkboxen/kein Dropdown/kein x.
 * PS07 — AD-Abschnitt nur bei can_sync; Knopf laedt lazy (onAdsyncLoad mit
 *        Container) und sperrt sich; adsyncOpen=true laedt sofort.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_personnel.js",
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

function _data(overrides) {
  return Object.assign(
    {
      persons: [
        {
          id: 1,
          system_username: "h0chef",
          display_name: "Chefin",
          is_investigator: true,
          is_supervisor: true,
          is_support: false,
          is_active: true,
          deactivated_at: null,
          deactivated_reason: null,
          roles: [
            { person_role_id: 11, role_code: "supervisor",
              label: "Chef-Ermittlerin / Aufsicht", assigned_at: 1 },
          ],
        },
        {
          id: 2,
          system_username: "h0erm",
          display_name: "KHK <b>Muster</b>",
          is_investigator: true,
          is_supervisor: false,
          is_support: false,
          is_active: true,
          deactivated_at: null,
          deactivated_reason: null,
          roles: [
            { person_role_id: 22, role_code: "investigator",
              label: "Ermittler:in", assigned_at: 1 },
          ],
        },
        {
          id: 3,
          system_username: "h0weg",
          display_name: "KOK Weg",
          is_investigator: true,
          is_supervisor: false,
          is_support: false,
          is_active: false,
          deactivated_at: 1753300000,
          deactivated_reason: "Nicht mehr im Active-Directory gefuehrt",
          roles: [],
        },
      ],
      roles_catalog: [
        { code: "investigator", label: "Ermittler:in" },
        { code: "supervisor", label: "Chef-Ermittlerin / Aufsicht" },
        { code: "searchagent", label: "Recherche mit Volltextsuche" },
      ],
      actor_person_id: 1,
      can_edit: true,
      can_sync: true,
    },
    overrides || {}
  );
}

describe("cockpit_personnel", () => {
  // PS01 --------------------------------------------------------------------
  it("PS01: API verfuegbar", () => {
    const api = _ctx().AIWCockpitPersonnel;
    expect(api).toBeTruthy();
    for (const fn of [
      "renderPersonnel",
      "statusText",
      "assignableRoles",
      "isSelf",
      "canEditRow",
    ]) {
      expect(typeof api[fn]).toBe("function");
    }
    expect(api.FLAGS.length).toBe(3);
  });

  // PS02 --------------------------------------------------------------------
  it("PS02: statusText", () => {
    const api = _ctx().AIWCockpitPersonnel;
    expect(api.statusText(_data().persons[0])).toBe("aktiv");
    const t = api.statusText(_data().persons[2]);
    expect(t).toContain("inaktiv seit 2025");
    expect(t).toContain("Active-Directory");
  });

  // PS03 --------------------------------------------------------------------
  it("PS03: assignableRoles + Selbstschutz-Logik", () => {
    const api = _ctx().AIWCockpitPersonnel;
    const d = _data();
    const forChef = api.assignableRoles(d.persons[0], d.roles_catalog);
    expect(forChef.map((r) => r.code)).toEqual([
      "investigator",
      "searchagent",
    ]);
    expect(api.isSelf(d.persons[0], d)).toBe(true);
    expect(api.isSelf(d.persons[1], d)).toBe(false);
    expect(api.canEditRow(d.persons[0], d)).toBe(false); // eigene Zeile!
    expect(api.canEditRow(d.persons[1], d)).toBe(true);
    expect(
      api.canEditRow(d.persons[1], _data({ can_edit: false }))
    ).toBe(false);
  });

  // PS04 --------------------------------------------------------------------
  it("PS04: renderPersonnel — Tabelle, (ich), XSS", () => {
    const w = _ctx();
    const api = w.AIWCockpitPersonnel;
    const main = w.document.createElement("div");
    const view = api.renderPersonnel(main, _data(), { doc: w.document });
    expect(typeof view.setResult).toBe("function");
    const rows = main.querySelectorAll(".aiw-pers-row");
    expect(rows.length).toBe(3);
    // Eigene Zeile: '(ich)', markiert, KEINE Bedienelemente.
    expect(rows[0].textContent).toContain("h0chef (ich)");
    expect(rows[0].classList.contains("self")).toBe(true);
    expect(rows[0].querySelectorAll("input,select,button").length).toBe(0);
    // Inaktive Zeile ist markiert.
    expect(rows[2].classList.contains("inactive")).toBe(true);
    // XSS: HTML im Anzeigenamen bleibt TEXT.
    expect(main.querySelector("b")).toBeNull();
    expect(main.textContent).toContain("KHK <b>Muster</b>");
  });

  // PS05 --------------------------------------------------------------------
  it("PS05: Callbacks flags/revoke/assign", () => {
    const w = _ctx();
    const api = w.AIWCockpitPersonnel;
    const main = w.document.createElement("div");
    const flags = [], revoked = [], assigned = [];
    api.renderPersonnel(main, _data(), {
      doc: w.document,
      onFlags: (b) => flags.push(b),
      onRevoke: (b) => revoked.push(b),
      onAssign: (b) => assigned.push(b),
    });
    const row2 = main.querySelectorAll(".aiw-pers-row")[1];
    // Flag: erste Checkbox (is_investigator, aktuell true) abwaehlen.
    const cb = row2.querySelector("input[type=checkbox]");
    cb.checked = false;
    cb.dispatchEvent(new w.Event("change"));
    expect(flags).toEqual([{ person_id: 2, is_investigator: false }]);
    // Rollen-x -> Widerruf mit exakter person_role_id.
    row2.querySelector(".aiw-pers-chip-x")
      .dispatchEvent(new w.Event("click"));
    expect(revoked).toEqual([{ person_role_id: 22 }]);
    // Dropdown -> Zuweisung.
    const sel = row2.querySelector(".aiw-pers-assign-sel");
    sel.value = "searchagent";
    sel.dispatchEvent(new w.Event("change"));
    expect(assigned).toEqual([{ person_id: 2, role_code: "searchagent" }]);
  });

  // PS06 --------------------------------------------------------------------
  it("PS06: ohne can_edit keine Bedienelemente", () => {
    const w = _ctx();
    const api = w.AIWCockpitPersonnel;
    const main = w.document.createElement("div");
    api.renderPersonnel(main, _data({ can_edit: false, can_sync: false }), {
      doc: w.document,
    });
    expect(main.querySelectorAll("input,select").length).toBe(0);
    expect(main.querySelectorAll(".aiw-pers-chip-x").length).toBe(0);
  });

  // PS07 --------------------------------------------------------------------
  it("PS07: AD-Abschnitt lazy / adsyncOpen", () => {
    const w = _ctx();
    const api = w.AIWCockpitPersonnel;
    // can_sync=false -> kein Abschnitt.
    const m0 = w.document.createElement("div");
    api.renderPersonnel(m0, _data({ can_sync: false }), { doc: w.document });
    expect(m0.querySelector(".aiw-pers-adsync")).toBeNull();

    // can_sync=true -> Abschnitt, Laden erst auf Klick.
    const m1 = w.document.createElement("div");
    const loads = [];
    api.renderPersonnel(m1, _data(), {
      doc: w.document,
      onAdsyncLoad: (box) => loads.push(box),
    });
    expect(m1.querySelector(".aiw-pers-adsync")).toBeTruthy();
    expect(loads.length).toBe(0); // lazy: noch kein LDAP-Abruf
    const btn = m1.querySelector(".aiw-pers-adsync-load");
    btn.dispatchEvent(new w.Event("click"));
    expect(loads.length).toBe(1);
    expect(loads[0].classList.contains("aiw-pers-adsync")).toBe(true);
    expect(btn.disabled).toBe(true);

    // adsyncOpen=true -> laedt sofort (nach eigener AD-Aktion).
    const m2 = w.document.createElement("div");
    const loads2 = [];
    api.renderPersonnel(m2, _data(), {
      doc: w.document,
      adsyncOpen: true,
      onAdsyncLoad: (box) => loads2.push(box),
    });
    expect(loads2.length).toBe(1);
  });
});
