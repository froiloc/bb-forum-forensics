/**
 * tests/unit/test_workload_render.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Lastverteilung (Frontend)
 *
 * Testsuite fuer management/workload/frontend/workload.js.
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWWorkload).
 *
 * WR01 -- API verfuegbar
 * WR02 -- nameLabel(): display > system; Rueckstau -> system_username
 * WR03 -- roleLabel(): E/C/S; Rueckstau -> Gedankenstrich
 * WR04 -- formatTs(): UTC; null -> Gedankenstrich
 * WR05 -- activityLabel(): Anzahl; Rueckstau -> Gedankenstrich
 * WR06 -- barSegments(): Prozentanteile; total 0 -> alle 0
 * WR07 -- sortRecords(): default rot desc, Rueckstau IMMER zuletzt, no mutate
 * WR08 -- filterRecords(): Name/System-Benutzer, leer -> alle
 * WR09 -- renderInto(): Zeilen, Rueckstau-Klasse, Last-Balken, XSS-sicher
 *
 * Version: v0.7.335 · Build: 335 · 2026-07-07
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/workload/frontend/workload.js",
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
  return _makeContext().AIWWorkload;
}

function L(over) {
  return Object.assign(
    {
      investigator_id: 1,
      system_username: "h001",
      display_name: "Alpha",
      is_investigator: true,
      is_supervisor: false,
      is_support: false,
      is_backlog: false,
      total_cases: 4,
      ampel_rot: 1,
      ampel_gelb: 1,
      ampel_gruen: 2,
      status_open: 2,
      status_in_progress: 1,
      status_approved: 0,
      status_closed: 1,
      active_cases: 3,
      done_cases: 1,
      audit_action_count: 5,
      last_action_at: 1609459200,
    },
    over
  );
}

function BACKLOG(over) {
  return L(
    Object.assign(
      {
        investigator_id: 0,
        system_username: "(nicht zugewiesen)",
        display_name: "(nicht zugewiesen)",
        is_investigator: false,
        is_backlog: true,
        audit_action_count: 0,
        last_action_at: null,
      },
      over
    )
  );
}

describe("workload.js — Lastverteilung Render-Schicht", () => {
  it("WR01 API verfuegbar", () => {
    const A = _api();
    expect(typeof A.sortRecords).toBe("function");
    expect(typeof A.renderInto).toBe("function");
    expect(typeof A.barSegments).toBe("function");
  });

  it("WR02 nameLabel", () => {
    const A = _api();
    expect(A.nameLabel(L({}))).toBe("Alpha");
    expect(A.nameLabel(L({ display_name: null }))).toBe("h001");
    expect(A.nameLabel(BACKLOG({}))).toBe("(nicht zugewiesen)");
  });

  it("WR03 roleLabel", () => {
    const A = _api();
    expect(A.roleLabel(L({ is_investigator: true, is_supervisor: true }))).toBe(
      "E/C"
    );
    expect(
      A.roleLabel(L({ is_investigator: false, is_supervisor: false, is_support: true }))
    ).toBe("S");
    expect(A.roleLabel(BACKLOG({}))).toBe("\u2014");
  });

  it("WR04 formatTs", () => {
    const A = _api();
    expect(A.formatTs(null)).toBe("\u2014");
    expect(A.formatTs(1609459200)).toBe("2021-01-01 00:00Z");
  });

  it("WR05 activityLabel", () => {
    const A = _api();
    expect(A.activityLabel(L({ audit_action_count: 7 }))).toBe("7");
    expect(A.activityLabel(BACKLOG({}))).toBe("\u2014");
  });

  it("WR06 barSegments", () => {
    const A = _api();
    const segs = A.barSegments(L({ total_cases: 4, ampel_rot: 1, ampel_gelb: 1, ampel_gruen: 2 }));
    expect(segs[0].pct).toBeCloseTo(25);
    expect(segs[1].pct).toBeCloseTo(25);
    expect(segs[2].pct).toBeCloseTo(50);
    // total 0 -> alle 0 (keine Division durch 0).
    const zero = A.barSegments(L({ total_cases: 0, ampel_rot: 0, ampel_gelb: 0, ampel_gruen: 0 }));
    expect(zero.every((s) => s.pct === 0)).toBe(true);
  });

  it("WR07 sortRecords default/backlog-last/no-mutate", () => {
    const A = _api();
    const input = [
      L({ investigator_id: 1, ampel_rot: 0 }),
      BACKLOG({}),
      L({ investigator_id: 2, ampel_rot: 5 }),
    ];
    const snap = input.map((r) => r.investigator_id);
    const out = A.sortRecords(input); // default rot desc
    // Ermittler nach rot desc (2 vor 1), Rueckstau zuletzt.
    expect(out.map((r) => r.investigator_id)).toEqual([2, 1, 0]);
    expect(out[out.length - 1].is_backlog).toBe(true);
    // Eingabe unveraendert.
    expect(input.map((r) => r.investigator_id)).toEqual(snap);
    // Auch bei aufsteigender Namenssortierung bleibt Rueckstau zuletzt.
    const byName = A.sortRecords(input, "name", "asc");
    expect(byName[byName.length - 1].is_backlog).toBe(true);
  });

  it("WR08 filterRecords", () => {
    const A = _api();
    const recs = [
      L({ investigator_id: 1, display_name: "Alpha", system_username: "h001" }),
      L({ investigator_id: 2, display_name: "Beta", system_username: "h002" }),
    ];
    expect(A.filterRecords(recs, "").length).toBe(2);
    expect(A.filterRecords(recs, "beta").map((r) => r.investigator_id)).toEqual([2]);
    expect(A.filterRecords(recs, "h001").map((r) => r.investigator_id)).toEqual([1]);
  });

  it("WR09 renderInto Zeilen/Backlog/Balken/XSS", () => {
    const win = _makeContext();
    const A = win.AIWWorkload;
    const doc = win.document;
    const root = doc.createElement("div");
    doc.body.appendChild(root);

    const recs = [L({ investigator_id: 1 }), BACKLOG({})];
    const res = A.renderInto(root, recs, {});
    expect(res.rows).toBe(2);

    const bodyRows = root.querySelectorAll("tbody tr");
    expect(bodyRows.length).toBe(2);
    expect(bodyRows[1].className).toContain("aiw-backlog");
    // Last-Balken-Segmente vorhanden (rot/gelb/gruen bei total>0).
    expect(root.querySelectorAll(".aiw-loadbar .aiw-seg").length).toBeGreaterThan(0);

    // XSS-sicher: '<img>' aus dem Anzeigenamen wird NICHT als Element erzeugt.
    const root2 = doc.createElement("div");
    doc.body.appendChild(root2);
    A.renderInto(root2, [L({ display_name: "<img src=x onerror=alert(1)>" })], {});
    expect(root2.querySelector("img")).toBeNull();
  });
});
