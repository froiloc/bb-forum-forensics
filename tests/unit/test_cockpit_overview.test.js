/**
 * tests/unit/test_cockpit_overview.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Overview (Frontend)
 *
 * Testsuite fuer management/server/static/cockpit_overview.js (Build 348).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitOverview) —
 * KEIN dupliziertes Logik-Abbild (vermeidet die 'gruen-aber-tot'-Falle).
 *
 * OV01 — API verfuegbar.
 * OV02 — ampelRank(): rot<gelb<gruen, unbekannt -> 99.
 * OV03 — reasonLabel(): bekannte Codes gemappt, sonst Rohwert.
 * OV04 — assigneeLabel(): display_name > system_username > em-dash.
 * OV05 — supportLabel(): 'Support aktiv (N)' bzw. ''.
 * OV06 — daysSince(): Tage seit ts (nowSec injizierbar); null bei fehlend.
 * OV07 — toRows(): abgeleitete Felder gesetzt; Eingabe unveraendert.
 * OV08 — sortRows(): Ampel-Schwere -> Prio -> letzte Aktivitaet desc -> subject_id;
 *        gibt Kopie zurueck (mutiert nicht).
 * OV09 — columnDefs(): 10 Spalten; Ampel-Formatter rendert Farbpunkt + Grund.
 * OV10 — renderOverview(): Kopf/Scope/Count; Stub-Tabulator erhaelt sortierte
 *        Zeilen + Spalten; ohne Ctor -> null + Hinweis.
 *
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 2026-07-20
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_overview.js",
  "utf-8"
);
// Build 549: das gemeinsame Tabellen-Werkzeug MUSS im Kontext liegen —
// genau wie im Browser (cockpit.html laedt es vor den Sichten). Ohne es
// faellt die Sicht in ihren ausdruecklichen Ersatzpfad, und der Test
// wuerde die Tabelle gar nicht mehr beruehren.
const _tkSrc = readFileSync(
  "management/server/static/cockpit_tablekit.js",
  "utf-8"
);

function _makeContext() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(_tkSrc);
  dom.window.eval(_src);
  return dom.window;
}

function _api() {
  return _makeContext().AIWCockpitOverview;
}

// Fall-Erzeuger mit sinnvollen Defaults (DTO-Form aus /api/overview).
function C(over) {
  return Object.assign(
    {
      subject_id: 1,
      username: "u",
      status: "open",
      priority: 3,
      assigned_to: null,
      assigned_display_name: null,
      ampel: "gruen",
      ampel_reason: "aktiv",
      has_note: false,
      event_count: 0,
      last_activity_at: 0,
      support_active: false,
      support_count: 0,
    },
    over
  );
}

describe("cockpit_overview.js — Overview-Sicht (Build 348)", () => {
  // OV01 -------------------------------------------------------------------
  it("OV01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.renderOverview).toBe("function");
    expect(typeof api.toRows).toBe("function");
  });

  // OV02 -------------------------------------------------------------------
  it("OV02: ampelRank", () => {
    const api = _api();
    expect(api.ampelRank("rot")).toBe(0);
    expect(api.ampelRank("gelb")).toBe(1);
    expect(api.ampelRank("gruen")).toBe(2);
    expect(api.ampelRank("unbekannt")).toBe(99);
  });

  // OV03 -------------------------------------------------------------------
  it("OV03: reasonLabel", () => {
    const api = _api();
    expect(api.reasonLabel("offen_nicht_zugewiesen")).toBe(
      "offen, nicht zugewiesen"
    );
    expect(api.reasonLabel("aktiv")).toBe("aktiv");
    expect(api.reasonLabel("xyz")).toBe("xyz"); // Rohwert-Fallback
    expect(api.reasonLabel(null)).toBe("");
  });

  // OV04 -------------------------------------------------------------------
  it("OV04: assigneeLabel", () => {
    const api = _api();
    expect(api.assigneeLabel(C({ assigned_display_name: "Mueller" }))).toBe(
      "Mueller"
    );
    expect(
      api.assigneeLabel(C({ assigned_system_username: "h007" }))
    ).toBe("h007");
    expect(api.assigneeLabel(C({}))).toBe("\u2014");
  });

  // OV05 -------------------------------------------------------------------
  it("OV05: supportLabel", () => {
    const api = _api();
    expect(
      api.supportLabel(C({ support_active: true, support_count: 2 }))
    ).toBe("Support aktiv (2)");
    expect(api.supportLabel(C({ support_active: false }))).toBe("");
  });

  // OV06 -------------------------------------------------------------------
  it("OV06: daysSince (nowSec injizierbar)", () => {
    const api = _api();
    const now = 1000000;
    expect(api.daysSince(now - 3 * 86400, now)).toBe(3);
    expect(api.daysSince(0, now)).toBe(null);
    expect(api.daysSince(null, now)).toBe(null);
  });

  // OV07 -------------------------------------------------------------------
  it("OV07: toRows setzt abgeleitete Felder; Eingabe unveraendert", () => {
    const api = _api();
    const input = [
      C({
        subject_id: 42,
        ampel: "rot",
        ampel_reason: "inaktiv_lang",
        assigned_display_name: "Chefin",
        last_activity_at: 1000000 - 2 * 86400,
        support_active: true,
        support_count: 1,
      }),
    ];
    const snapshot = JSON.stringify(input);
    const rows = api.toRows(input, 1000000);
    expect(rows[0]._rank).toBe(0);
    expect(rows[0]._reason).toBe("lange inaktiv");
    expect(rows[0]._assignee).toBe("Chefin");
    expect(rows[0]._sinceDays).toBe(2);
    expect(rows[0]._support).toBe("Support aktiv (1)");
    // Keine Mutation der Eingabe.
    expect(JSON.stringify(input)).toBe(snapshot);
  });

  // OV08 -------------------------------------------------------------------
  it("OV08: sortRows Reihenfolge + Kopie", () => {
    const api = _api();
    const rows = api.toRows(
      [
        C({ subject_id: 1, ampel: "gruen", priority: 1 }),
        C({ subject_id: 2, ampel: "rot", priority: 3 }),
        C({ subject_id: 3, ampel: "gelb", priority: 2 }),
        C({ subject_id: 4, ampel: "rot", priority: 1 }),
      ],
      1000000
    );
    const sorted = api.sortRows(rows);
    // rot(prio1)=4, rot(prio3)=2, gelb=3, gruen=1
    expect(sorted.map((r) => r.subject_id)).toEqual([4, 2, 3, 1]);
    // Kopie: Original-Reihenfolge unveraendert.
    expect(rows.map((r) => r.subject_id)).toEqual([1, 2, 3, 4]);
  });

  // OV09 -------------------------------------------------------------------
  it("OV09: columnDefs + Ampel-Formatter", () => {
    const api = _api();
    const cols = api.columnDefs();
    expect(cols.length).toBe(10);
    expect(cols[0].title).toBe("Ampel");

    // Ampel-Formatter mit Fake-Cell aufrufen -> Farbpunkt + Grund.
    const fakeCell = {
      getRow: () => ({
        getData: () => ({ ampel: "rot", _reason: "lange inaktiv" }),
      }),
      getValue: () => 0,
    };
    const node = cols[0].formatter(fakeCell);
    expect(node.querySelector(".dot.rot")).toBeTruthy();
    expect(node.textContent).toContain("lange inaktiv");
  });

  // OV10 -------------------------------------------------------------------
  it("OV10: renderOverview Kopf/Scope/Count + Stub-Tabulator", () => {
    const win = _makeContext();
    const api = win.AIWCockpitOverview;
    const main = win.document.createElement("main");

    // Stub-Tabulator: merkt sich container + options.
    const seen = {};
    function StubTab(container, options) {
      seen.container = container;
      seen.options = options;
    }
    StubTab.prototype.destroy = function () {};

    const data = {
      scope: "alle",
      count: 2,
      cases: [
        C({ subject_id: 1, ampel: "gruen", priority: 3 }),
        C({ subject_id: 2, ampel: "rot", priority: 1 }),
      ],
    };
    const inst = api.renderOverview(main, data, {
      Tabulator: StubTab,
      nowSec: 1000000,
    });

    expect(inst).toBeInstanceOf(StubTab);
    expect(main.querySelector(".aiw-pagehead").textContent).toBe(
      "Fall-Uebersicht"
    );
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("alle");
    expect(main.querySelector(".aiw-pagesub").textContent).toContain(
      "2 Faelle"
    );
    // Zeilen sortiert an Tabulator uebergeben (rot subject_id=2 zuerst).
    expect(seen.options.data.map((r) => r.subject_id)).toEqual([2, 1]);
    expect(seen.options.columns.length).toBe(10);

    // Ohne Ctor -> null + Hinweis.
    const main2 = win.document.createElement("main");
    const none = api.renderOverview(main2, data, { Tabulator: null });
    expect(none).toBe(null);
    expect(main2.querySelector(".aiw-placeholder")).toBeTruthy();
  });
});
