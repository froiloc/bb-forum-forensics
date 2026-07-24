/**
 * Build 500: Fallstart aus dem Portal — Aktionsspalte/Banner/onLaunch (MYC06-09)
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.8.500 · Build: 500 · 2026-07-22
 * tests/unit/test_cockpit_mycases.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Meine Auftraege
 *
 * Testsuite fuer management/server/static/cockpit_mycases.js (Build 364).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitMyCases).
 *
 * MYC01 — API verfuegbar.
 * MYC02 — daysSince: Tage seit ts; null ohne ts.
 * MYC03 — toRows: Faelle -> Zeilen (has_note -> 'Notiz'/'', since_days).
 * MYC04 — renderMyCases: Kopf/count + Stub-Tabulator.
 * MYC05 — renderMyCases ohne Tabulator -> Platzhalter + null.
 *
 * Build 500 (Fallstart aus dem Portal):
 * MYC06 — columnsFor: ohne onLaunch nur Basisspalten; mit onLaunch +Aktion.
 * MYC07 — actionColumn-Formatter: liefert <button>, Klick ruft onLaunch(sid)
 *         und deaktiviert den Knopf (Doppelklick-Schutz).
 * MYC08 — renderMyCases mit onLaunch: Aktionsspalte in den Tabulator-Optionen.
 * MYC09 — pendingMsg -> Banner (is-ok/is-error) mit Text (XSS: textContent).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_mycases.js",
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
function _api() { return _ctx().AIWCockpitMyCases; }

function _data() {
  return {
    count: 2,
    cases: [
      { subject_id: 18, username: "b18", status: "in_progress", priority: 2,
        ampel: "gelb", event_count: 3, has_note: true,
        last_activity_at: 1000 },
      { subject_id: 20, username: "b20", status: "open", priority: 3,
        ampel: "gruen", event_count: 0, has_note: false,
        last_activity_at: null },
    ],
  };
}

describe("cockpit_mycases.js — Meine Auftraege (Build 364)", () => {
  it("MYC01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.toRows).toBe("function");
    expect(typeof api.renderMyCases).toBe("function");
  });

  it("MYC02: daysSince", () => {
    const api = _api();
    // now = 1000 + 3 Tage
    expect(api.daysSince(1000, 1000 + 3 * 86400)).toBe(3);
    expect(api.daysSince(null, 1000)).toBe(null);
  });

  it("MYC03: toRows", () => {
    const api = _api();
    const rows = api.toRows(_data(), 1000 + 2 * 86400);
    expect(rows.length).toBe(2);
    expect(rows[0].has_note).toBe("Notiz");
    expect(rows[0].since_days).toBe(2);
    expect(rows[1].has_note).toBe("");
    expect(rows[1].since_days).toBe(null);
  });

  it("MYC04: renderMyCases — Kopf + Stub-Tabulator", () => {
    const win = _ctx();
    const api = win.AIWCockpitMyCases;
    const main = win.document.createElement("main");
    let made = null;
    function StubTab(container, opts) { made = { container, opts }; }
    const inst = api.renderMyCases(main, _data(), { Tabulator: StubTab });
    expect(inst).toBeInstanceOf(StubTab);
    expect(main.querySelector(".aiw-pagehead").textContent).toBe("Meine Auftraege");
    expect(main.querySelector(".aiw-pagesub").textContent).toContain("(2)");
    expect(made.opts.data.length).toBe(2);
  });

  it("MYC05: ohne Tabulator -> Platzhalter + null", () => {
    const win = _ctx();
    const api = win.AIWCockpitMyCases;
    const main = win.document.createElement("main");
    const inst = api.renderMyCases(main, _data(), { Tabulator: null });
    expect(inst).toBe(null);
    expect(main.querySelector(".aiw-placeholder")).toBeTruthy();
  });

  it("MYC06: columnsFor — Aktionsspalte nur mit onLaunch", () => {
    const api = _api();
    const base = api.columnsFor();
    const withAction = api.columnsFor(function () {});
    expect(withAction.length).toBe(base.length + 1);
    const last = withAction[withAction.length - 1];
    expect(last.title).toBe("Aktion");
    expect(typeof last.formatter).toBe("function");
  });

  it("MYC07: actionColumn-Formatter — Button + Klick ruft onLaunch(sid)", () => {
    const win = _ctx();
    const api = win.AIWCockpitMyCases;
    // document global fuer den Formatter bereitstellen (nutzt globales document).
    const prevDoc = globalThis.document;
    globalThis.document = win.document;
    try {
      let called = null;
      const col = api.actionColumn(function (sid) { called = sid; });
      // Fake-Zelle wie Tabulator sie dem Formatter uebergibt.
      const btn = col.formatter({ getValue: () => 18 });
      expect(btn.tagName).toBe("BUTTON");
      expect(btn.textContent).toBe("Fall starten");
      expect(btn.getAttribute("data-subject-id")).toBe("18");
      btn.dispatchEvent(new win.Event("click"));
      expect(called).toBe(18);
      expect(btn.disabled).toBe(true);
      expect(btn.textContent).toBe("Startet…");
    } finally {
      globalThis.document = prevDoc;
    }
  });

  it("MYC08: renderMyCases mit onLaunch — Aktionsspalte in Tabulator-Optionen", () => {
    const win = _ctx();
    const api = win.AIWCockpitMyCases;
    const main = win.document.createElement("main");
    let made = null;
    function StubTab(container, opts) { made = { container, opts }; }
    api.renderMyCases(main, _data(), {
      Tabulator: StubTab,
      onLaunch: function () {},
    });
    const cols = made.opts.columns;
    expect(cols[cols.length - 1].title).toBe("Aktion");
  });

  it("MYC09: pendingMsg -> Banner (is-ok / is-error, textContent)", () => {
    const win = _ctx();
    const api = win.AIWCockpitMyCases;
    const main = win.document.createElement("main");
    function StubTab() {}
    api.renderMyCases(main, _data(), {
      Tabulator: StubTab,
      pendingMsg: { text: "Fall 18 gestartet.", error: false },
    });
    const ok = main.querySelector(".aiw-mycases-banner.is-ok");
    expect(ok).toBeTruthy();
    expect(ok.textContent).toBe("Fall 18 gestartet.");

    const main2 = win.document.createElement("main");
    api.renderMyCases(main2, _data(), {
      Tabulator: StubTab,
      pendingMsg: { text: "Fehlgeschlagen", error: true },
    });
    expect(main2.querySelector(".aiw-mycases-banner.is-error")).toBeTruthy();
  });
});
