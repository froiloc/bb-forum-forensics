/**
 * tests/unit/test_cockpit_crossfindings.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Querfunde (AP-2A)
 *
 * Testsuite fuer management/server/static/cockpit_crossfindings.js (Build 478).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitCrossfindings).
 *
 * QF01 — API verfuegbar.
 * QF02 — reine Helfer: statusLabel/statusClass, findings(), fmtTs().
 * QF03 — mit Funden: counts-Kopf, Tabelle, Status-Badge-Klasse.
 * QF04 — echter Leerbefund: „Keine Querfunde" / „Keine offenen Querfunde".
 * QF05 — Fehlerzustand ({error}): Meldung, KEINE Tabelle (Grundregel 1).
 * QF06 — Steuerung: Checkbox spiegelt onlyOpen; Toggle/Aktualisieren -> onReload.
 * QF07 — XSS-sicher; nicht zuordenbarer Ermittler (source_name null) -> iid.
 *
 * Version: v0.8.478 · Build: 478 · 2026-07-21
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_crossfindings.js",
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
function _mount(win) {
  const el = win.document.createElement("div");
  win.document.body.appendChild(el);
  return el;
}
function _data() {
  return {
    counts: { total: 2, offen: 1, integriert: 1 },
    findings: [
      { id: 2, subject_id: 800, source_iid: 1, source_name: "Chefin",
        has_case: true, annotation_local_id: "a1", db_path: "/x/e1.db",
        created_at: 1700000000, integrated_at: null, status: "offen" },
      { id: 1, subject_id: 801, source_iid: 9, source_name: null,
        has_case: false, annotation_local_id: "a2", db_path: "/x/e2.db",
        created_at: 1700000100, integrated_at: 1700000500,
        status: "integriert" },
    ],
  };
}

describe("cockpit_crossfindings", () => {
  // QF01 --------------------------------------------------------------------
  it("QF01: API-Oberflaeche vorhanden", () => {
    const api = _win().AIWCockpitCrossfindings;
    expect(api).toBeTruthy();
    ["statusLabel", "statusClass", "findings", "fmtTs",
     "renderCrossfindings"].forEach((fn) => {
      expect(typeof api[fn]).toBe("function");
    });
  });

  // QF02 --------------------------------------------------------------------
  it("QF02: reine Helfer", () => {
    const api = _win().AIWCockpitCrossfindings;
    expect(api.statusLabel("offen")).toBe("offen");
    expect(api.statusLabel("integriert")).toBe("integriert");
    expect(api.statusClass("offen")).toBe("aiw-cf-offen");
    expect(api.statusClass("integriert")).toBe("aiw-cf-integriert");
    expect(api.statusClass("xyz")).toBe("aiw-cf-unbekannt");
    expect(api.findings(null)).toEqual([]);
    expect(api.findings({ findings: [{ id: 1 }] }).length).toBe(1);
    expect(api.fmtTs(0)).toBe("—");
    expect(typeof api.fmtTs(1700000000)).toBe("string");
  });

  // QF03 --------------------------------------------------------------------
  it("QF03: Funde -> counts-Kopf, Tabelle, Badge-Klasse", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    api.renderCrossfindings(el, _data(), { doc: win.document });

    expect(el.querySelector(".aiw-cf-counts").textContent).toContain("offen: 1");
    expect(el.querySelector(".aiw-cf-counts").textContent)
      .toContain("gesamt: 2");
    const rows = el.querySelectorAll(".aiw-cf-table tbody tr");
    expect(rows.length).toBe(2);
    expect(rows[0].querySelector(".aiw-cf-badge").className)
      .toContain("aiw-cf-offen");
    expect(rows[0].getAttribute("data-subject")).toBe("800");
    expect(rows[1].querySelector(".aiw-cf-badge").className)
      .toContain("aiw-cf-integriert");
  });

  // QF04 --------------------------------------------------------------------
  it("QF04: echter Leerbefund", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;

    const el1 = _mount(win);
    api.renderCrossfindings(el1, { counts: { total: 0, offen: 0, integriert: 0 },
      findings: [] }, { doc: win.document, onlyOpen: false });
    expect(el1.querySelector(".aiw-cf-table")).toBeNull();
    expect(el1.querySelector(".aiw-placeholder").textContent)
      .toBe("Keine Querfunde.");

    const el2 = _mount(win);
    api.renderCrossfindings(el2, { counts: { total: 0, offen: 0, integriert: 0 },
      findings: [] }, { doc: win.document, onlyOpen: true });
    expect(el2.querySelector(".aiw-placeholder").textContent)
      .toBe("Keine offenen Querfunde.");
  });

  // QF05 --------------------------------------------------------------------
  it("QF05: Fehlerzustand zeigt Meldung, KEINE Tabelle (Grundregel 1)", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    api.renderCrossfindings(el, { error: "crossfindings_unavailable" },
      { doc: win.document });
    expect(el.querySelector(".aiw-cf-table")).toBeNull();
    expect(el.querySelector(".aiw-placeholder")).toBeNull();
    const err = el.querySelector(".aiw-cf-result.error");
    expect(err).toBeTruthy();
    expect(err.textContent).toContain("nicht verfügbar");
  });

  // QF06 --------------------------------------------------------------------
  it("QF06: Steuerung spiegelt onlyOpen und loest onReload aus", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const doc = win.document;
    const el = _mount(win);
    const calls = [];
    api.renderCrossfindings(el, _data(), {
      doc, onlyOpen: true, onReload: (v) => calls.push(v),
    });

    const cb = doc.getElementById("aiw-cf-onlyopen");
    expect(cb.checked).toBe(true); // spiegelt onlyOpen
    cb.checked = false;
    cb.dispatchEvent(new win.Event("change"));
    expect(calls[calls.length - 1]).toBe(false);

    doc.getElementById("aiw-cf-refresh").click();
    expect(calls.length).toBe(2);
  });

  // QF07 --------------------------------------------------------------------
  it("QF07: XSS-sicher; nicht zuordenbarer Ermittler -> iid", () => {
    const win = _win();
    const api = win.AIWCockpitCrossfindings;
    const el = _mount(win);
    const evil = '<img src=x onerror=alert(1)>';
    api.renderCrossfindings(el, {
      counts: { total: 1, offen: 1, integriert: 0 },
      findings: [{ id: 1, subject_id: 5, source_iid: 42, source_name: evil,
        created_at: 1700000000, integrated_at: null, status: "offen" }],
    }, { doc: win.document });
    expect(el.querySelector("img")).toBeNull();      // kein Markup
    expect(el.textContent).toContain(evil);          // als Text

    // source_name null -> "iid 42" (Zeile bleibt aussagekraeftig).
    const el2 = _mount(win);
    api.renderCrossfindings(el2, {
      counts: { total: 1, offen: 1, integriert: 0 },
      findings: [{ id: 1, subject_id: 5, source_iid: 42, source_name: null,
        created_at: 1700000000, integrated_at: null, status: "offen" }],
    }, { doc: win.document });
    expect(el2.textContent).toContain("iid 42");
  });
});
