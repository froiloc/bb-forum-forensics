/**
 * tests/unit/test_cockpit_audit.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Audit-Explorer
 *
 * Testsuite fuer management/server/static/cockpit_audit.js (Build 467).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitAudit).
 *
 * AU01 — API verfuegbar.
 * AU02 — Helfer: buildQuery (leere weg, extra dabei), payloadShort, targetLabel,
 *        actorLabel.
 * AU03 — renderAudit: Kopf, Filterleiste (Facetten), Tabelle, Trefferinfo.
 * AU04 — Export-Link traegt die ANGEWANDTEN Filter.
 * AU05 — Filtern ruft onFilter mit den Eingaben; Blaettern ruft onPage.
 * AU06 — Paginierung: prev bei offset 0 deaktiviert; next nur bei has_more.
 * AU07 — leere Treffer -> Platzhalter; Payload XSS-sicher (textContent).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_audit.js",
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
  return _win().AIWCockpitAudit;
}

function _facets() {
  return {
    event_types: ["case_created", "case_assigned"],
    actors: [{ actor_id: 1, actor_name: "Chefin", actor_username: "chef" }],
  };
}
function _data() {
  return {
    total: 67,
    limit: 50,
    offset: 0,
    has_more: true,
    rows: [
      { seq: 67, ts: 1700000000, actor_id: 1, actor_name: "Chefin",
        actor_username: "chef", event_type: "case_created",
        target_type: "case", target_id: "1006",
        content: '{"user_id":1006}', row_hash: "abcd" },
    ],
  };
}

describe("cockpit_audit.js — Audit-Explorer (Build 467)", () => {
  // AU01 -------------------------------------------------------------------
  it("AU01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.renderAudit).toBe("function");
    expect(typeof api.buildQuery).toBe("function");
  });

  // AU02 -------------------------------------------------------------------
  it("AU02: Helfer", () => {
    const api = _api();
    const qs = api.buildQuery(
      { event_type: "case_created", actor_id: "", target_type: "case" },
      { limit: 50, offset: 0 });
    expect(qs).toContain("event_type=case_created");
    expect(qs).toContain("target_type=case");
    expect(qs).not.toContain("actor_id="); // leer weggelassen
    expect(qs).toContain("limit=50");
    expect(api.payloadShort("x".repeat(200)).length).toBeLessThanOrEqual(91);
    expect(api.targetLabel({ target_type: "case", target_id: "5" })).toBe(
      "case/5");
    expect(api.actorLabel({ actor_name: "Chefin", actor_username: "chef" }))
      .toBe("Chefin (chef)");
  });

  // AU03 -------------------------------------------------------------------
  it("AU03: renderAudit Grundgeruest", () => {
    const win = _win();
    const doc = win.document;
    const main = doc.createElement("main");
    win.AIWCockpitAudit.renderAudit(main, _data(), _facets(), { doc: doc });
    expect(main.querySelector(".aiw-pagehead").textContent).toContain(
      "Audit");
    expect(main.querySelector("#aiw-audit-event")).toBeTruthy();
    expect(main.querySelector("#aiw-audit-actor")).toBeTruthy();
    expect(main.querySelectorAll(".aiw-audit-table tbody tr").length).toBe(1);
    expect(main.querySelector(".aiw-audit-info").textContent).toContain("67");
  });

  // AU04 -------------------------------------------------------------------
  it("AU04: Export-Link mit angewandten Filtern", () => {
    const win = _win();
    const doc = win.document;
    const main = doc.createElement("main");
    win.AIWCockpitAudit.renderAudit(main, _data(), _facets(), {
      doc: doc, filters: { event_type: "case_created", actor_id: "1" },
    });
    const href = main.querySelector("#aiw-audit-export").getAttribute("href");
    expect(href).toContain("/api/audit/export?");
    expect(href).toContain("event_type=case_created");
    expect(href).toContain("actor_id=1");
  });

  // AU05 -------------------------------------------------------------------
  it("AU05: Filtern/Blaettern rufen Callbacks", () => {
    const win = _win();
    const doc = win.document;
    const main = doc.createElement("main");
    const filterCalls = [];
    const pageCalls = [];
    win.AIWCockpitAudit.renderAudit(main, _data(), _facets(), {
      doc: doc,
      onFilter: (f) => filterCalls.push(f),
      onPage: (o) => pageCalls.push(o),
    });
    main.querySelector("#aiw-audit-event").value = "case_created";
    main.querySelector("#aiw-audit-to").value = "50";
    main.querySelector("#aiw-audit-filter").click();
    expect(filterCalls.length).toBe(1);
    expect(filterCalls[0].event_type).toBe("case_created");
    expect(filterCalls[0].seq_to).toBe("50");

    main.querySelector("#aiw-audit-next").click();
    expect(pageCalls).toEqual([50]); // offset 0 + limit 50
  });

  // AU06 -------------------------------------------------------------------
  it("AU06: Paginierungs-Buttons", () => {
    const win = _win();
    const doc = win.document;
    // offset 0, has_more true -> prev disabled, next aktiv
    const m1 = doc.createElement("main");
    win.AIWCockpitAudit.renderAudit(m1, _data(), _facets(), { doc: doc });
    expect(m1.querySelector("#aiw-audit-prev").disabled).toBe(true);
    expect(m1.querySelector("#aiw-audit-next").disabled).toBe(false);
    // offset 50, has_more false -> prev aktiv, next disabled
    const d2 = _data();
    d2.offset = 50;
    d2.has_more = false;
    const m2 = doc.createElement("main");
    win.AIWCockpitAudit.renderAudit(m2, d2, _facets(), { doc: doc });
    expect(m2.querySelector("#aiw-audit-prev").disabled).toBe(false);
    expect(m2.querySelector("#aiw-audit-next").disabled).toBe(true);
  });

  // AU07 -------------------------------------------------------------------
  it("AU07: leere Treffer + XSS-sicher", () => {
    const win = _win();
    const doc = win.document;
    const empty = doc.createElement("main");
    win.AIWCockpitAudit.renderAudit(empty,
      { total: 0, limit: 50, offset: 0, has_more: false, rows: [] },
      _facets(), { doc: doc });
    expect(empty.querySelector(".aiw-placeholder")).toBeTruthy();

    const xss = doc.createElement("main");
    const d = _data();
    d.rows[0].content = "<script>alert(1)</script>";
    win.AIWCockpitAudit.renderAudit(xss, d, _facets(), { doc: doc });
    expect(xss.querySelector("script")).toBe(null);
    expect(xss.textContent).toContain("<script>alert(1)</script>");
  });
});
