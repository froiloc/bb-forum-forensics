/**
 * tests/unit/test_cockpit_lectorate.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Lektorat (W4)
 *
 * Testsuite fuer management/server/static/cockpit_lectorate.js (Build 413,
 * Slice 1). Testet den ECHTEN Code (readFileSync + JSDOM,
 * window.AIWCockpitLectorate).
 *
 * LE01 — API verfuegbar.
 * LE02 — statusLabel: deutsche Bezeichnungen (R1).
 * LE03 — filterReports: 'submitted' (Vorgabe), 'alle', leer; mutiert nicht.
 * LE04 — renderUrl: korrekte SF-1-URL (user_id/report_id).
 * LE05 — reportLabel: Zeilentext.
 * LE06 — renderLectorate: Auswahl-Liste (nur submitted) + <iframe>; Klick setzt
 *        iframe.src auf die Render-URL, markiert aktiv, ruft onSelect.
 * LE07 — Statuswechsel 'alle' rendert mehr Zeilen (reiner Lesewechsel).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_lectorate.js",
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
function _api(win) { return (win || _ctx()).AIWCockpitLectorate; }

function _data() {
  return {
    scope: "alle",
    count: 3,
    reports: [
      { user_id: 18, username: "b18", id: 1, report_type: "interim",
        sequence_nr: 1, title: "Zwischenbericht", status: "submitted" },
      { user_id: 19, username: "b19", id: 2, report_type: "final",
        sequence_nr: 3, title: "Abschlussbericht", status: "approved" },
      { user_id: 20, username: "b20", id: 1, report_type: "addendum",
        sequence_nr: 2, title: "Nachtrag", status: "submitted" },
    ],
  };
}

describe("cockpit_lectorate", () => {
  it("LE01 API verfuegbar", () => {
    const api = _api();
    expect(typeof api.renderLectorate).toBe("function");
    expect(typeof api.filterReports).toBe("function");
    expect(typeof api.renderUrl).toBe("function");
    expect(typeof api.cleanup).toBe("function");
  });

  it("LE02 statusLabel deutsch", () => {
    const api = _api();
    expect(api.statusLabel("submitted")).toBe("Zur Abnahme vorgelegt");
    expect(api.statusLabel("approved")).toBe("Freigegeben");
    expect(api.statusLabel("draft")).toBe("Entwurf");
    expect(api.statusLabel("xyz")).toBe("xyz");
  });

  it("LE03 filterReports", () => {
    const api = _api();
    const data = _data();
    expect(api.filterReports(data, "submitted").length).toBe(2);
    expect(api.filterReports(data, "alle").length).toBe(3);
    expect(api.filterReports(data, "approved").length).toBe(1);
    expect(api.filterReports({ reports: [] }, "submitted").length).toBe(0);
    // mutiert die Eingabe nicht:
    expect(data.reports.length).toBe(3);
  });

  it("LE04 renderUrl", () => {
    const api = _api();
    expect(api.renderUrl(18, 1)).toBe(
      "/api/report/render?user_id=18&report_id=1"
    );
  });

  it("LE05 reportLabel", () => {
    const api = _api();
    const r = _data().reports[0];
    const s = api.reportLabel(r);
    expect(s).toContain("b18");
    expect(s).toContain("Zwischenbericht");
    expect(s).toContain("Zur Abnahme vorgelegt");
  });

  it("LE06 renderLectorate + Auswahl setzt iframe.src", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);

    let picked = null;
    api.renderLectorate(main, _data(), {
      status: "submitted",
      onSelect: function (uid, rid) { picked = [uid, rid]; },
    });

    const items = main.querySelectorAll(".aiw-lectorate-item");
    expect(items.length).toBe(2); // nur submitted
    const frame = main.querySelector("iframe.aiw-lectorate-preview");
    expect(frame).not.toBeNull();

    // Klick auf den ersten Bericht (uid 18, rid 1).
    items[0].dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(frame.src).toContain("/api/report/render?user_id=18&report_id=1");
    expect(items[0].classList.contains("is-active")).toBe(true);
    expect(picked).toEqual([18, 1]);
  });

  it("LE07 Statuswechsel 'alle' zeigt mehr Zeilen", () => {
    const win = _ctx();
    const api = _api(win);
    const main = win.document.createElement("div");
    win.document.body.appendChild(main);
    api.renderLectorate(main, _data(), { status: "submitted" });
    expect(main.querySelectorAll(".aiw-lectorate-item").length).toBe(2);

    const sel = main.querySelector("select.aiw-lectorate-status");
    sel.value = "alle";
    sel.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(main.querySelectorAll(".aiw-lectorate-item").length).toBe(3);
  });
});
