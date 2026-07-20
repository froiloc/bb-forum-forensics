/**
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 * tests/unit/test_cockpit_assignment.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Zuweisung
 *
 * Testsuite fuer management/server/static/cockpit_assignment.js (Build 373).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitAssignment).
 *
 * AZ01 — API verfuegbar.
 * AZ02 — toRows + assigneeLabel (inkl. nicht zugewiesen).
 * AZ03 — investigatorOptions: '(nicht zugewiesen)' + Ermittler mit Last.
 * AZ04 — changeRequest: assign/priority/status; '' -> person_id null.
 * AZ05 — renderAssignment: Tabelle + Auswahlfelder; Aenderung ruft onChange.
 * AZ06 — setMessage: Rueckmeldung (Erfolg/Fehler) sichtbar.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_assignment.js",
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
function _api() { return _ctx().AIWCockpitAssignment; }

function _data() {
  return {
    cases: [
      { subject_id: 18, username: "b18", assigned_to: 2,
        assigned_display_name: "Mueller", priority: 3, status: "in_progress" },
      { subject_id: 19, username: "b19", assigned_to: null,
        assigned_display_name: null, priority: 5, status: "open" },
    ],
    investigators: [
      { person_id: 1, system_username: "h0a2898", display_name: "Chefin",
        case_count: 0 },
      { person_id: 2, system_username: "h002", display_name: "Mueller",
        case_count: 1 },
    ],
    statuses: ["open", "in_progress", "approved", "closed"],
    priority_min: 1, priority_max: 5,
  };
}

describe("cockpit_assignment.js — Zuweisung (Build 373)", () => {
  it("AZ01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.changeRequest).toBe("function");
    expect(typeof api.renderAssignment).toBe("function");
  });

  it("AZ02: toRows + assigneeLabel", () => {
    const api = _api();
    const rows = api.toRows(_data());
    expect(rows.length).toBe(2);
    expect(rows[0].assignee).toBe("Mueller");
    expect(rows[0].status_label).toBe("in Arbeit");
    expect(rows[1].assignee).toBe("(nicht zugewiesen)");
    expect(rows[1].assigned_to).toBe(null);
  });

  it("AZ03: investigatorOptions", () => {
    const api = _api();
    const opts = api.investigatorOptions(_data());
    expect(opts[0]).toEqual({ value: "", label: "(nicht zugewiesen)" });
    expect(opts[1].value).toBe("1");
    expect(opts[2].label).toBe("Mueller (1)"); // mit aktueller Last
  });

  it("AZ04: changeRequest", () => {
    const api = _api();
    expect(api.changeRequest("assign", 18, "2")).toEqual({
      path: "/api/case/assign", body: { subject_id: 18, person_id: 2 },
    });
    // Entziehen: '' -> null
    expect(api.changeRequest("assign", 18, "")).toEqual({
      path: "/api/case/assign", body: { subject_id: 18, person_id: null },
    });
    expect(api.changeRequest("priority", 18, "1")).toEqual({
      path: "/api/case/priority", body: { subject_id: 18, priority: 1 },
    });
    expect(api.changeRequest("status", 18, "closed")).toEqual({
      path: "/api/case/status", body: { subject_id: 18, status: "closed" },
    });
    expect(api.changeRequest("pfui", 18, "x")).toBe(null);
  });

  it("AZ05: renderAssignment + onChange", () => {
    const win = _ctx();
    const api = win.AIWCockpitAssignment;
    const main = win.document.createElement("main");
    const changes = [];
    const view = api.renderAssignment(main, _data(), {
      onChange: function (kind, uid, val) { changes.push([kind, uid, val]); },
    });
    expect(view).toBeTruthy();
    // Zwei Datenzeilen, je drei Auswahlfelder.
    const trs = main.querySelectorAll("tbody tr");
    expect(trs.length).toBe(2);
    const sels = trs[0].querySelectorAll("select");
    expect(sels.length).toBe(3);

    // Ermittler-Auswahl aendern -> onChange('assign', 18, '1')
    sels[0].value = "1";
    sels[0].dispatchEvent(new win.Event("change"));
    expect(changes[changes.length - 1]).toEqual(["assign", 18, "1"]);

    // Status-Auswahl aendern -> onChange('status', 18, 'closed')
    sels[2].value = "closed";
    sels[2].dispatchEvent(new win.Event("change"));
    expect(changes[changes.length - 1]).toEqual(["status", 18, "closed"]);
  });

  it("AZ06: setMessage zeigt Rueckmeldung", () => {
    const win = _ctx();
    const api = win.AIWCockpitAssignment;
    const main = win.document.createElement("main");
    const view = api.renderAssignment(main, _data(), {});
    view.setMessage("Gespeichert (Beleg #42).", false);
    const msg = main.querySelector("#aiw-assign-msg");
    expect(msg.textContent).toContain("Beleg #42");
    expect(msg.classList.contains("error")).toBe(false);
    view.setMessage("Fehler: kaputt", true);
    expect(msg.classList.contains("error")).toBe(true);
  });
});
