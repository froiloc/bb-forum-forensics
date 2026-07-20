/**
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 * tests/unit/test_cockpit_reports.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Berichts-Abnahme
 *
 * Testsuite fuer management/server/static/cockpit_reports.js (Build 375).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitReports).
 *
 * BR01 — API verfuegbar.
 * BR02 — toRows: Typ-/Status-Label, Freigaben-Anzahl, letzte Freigabe.
 * BR03 — filterByStatus + statusCounts.
 * BR04 — scanInfoText macht die Cache-Wirkung sichtbar (rescanned).
 * BR05 — renderReports: Tabelle + Filter + Neu-einlesen-Knopf (Callback).
 * BR06 — HINWEISE: nicht lesbare DBs + Faelle ohne DB werden ANGEZEIGT
 *        (Grundregel 1: nichts wird verschwiegen).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_reports.js",
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
function _api() { return _ctx().AIWCockpitReports; }

function _data() {
  return {
    scope: "alle",
    evidence_dir: "./data/evidence/",
    case_db_count: 3,
    rescanned: 1,
    count: 3,
    reports: [
      { subject_id: 18, username: "b18", id: 1, report_type: "interim",
        sequence_nr: 1, title: "Zwischenbericht", created_by: "h002",
        created_at: 1783000000, status: "submitted", approvals: [] },
      { subject_id: 19, username: "b19", id: 1, report_type: "final",
        sequence_nr: 1, title: "Abschlussbericht", created_by: "h003",
        created_at: 1783100000, status: "approved",
        approvals: [{ approved_by: "h0a2898", approved_at: 1783200000,
                      is_final: false, note: null }] },
      { subject_id: 20, username: "b20", id: 1, report_type: "addendum",
        sequence_nr: 2, title: "Nachtrag", created_by: "h002",
        created_at: 1783300000, status: "draft", approvals: [] },
    ],
    errors: [{ subject_id: 21, error: "nicht lesbar: file is not a database" }],
    cases_without_db: [22, 23],
  };
}

describe("cockpit_reports.js — Berichts-Abnahme (Build 375)", () => {
  it("BR01: API verfuegbar", () => {
    const api = _api();
    expect(typeof api.toRows).toBe("function");
    expect(typeof api.renderReports).toBe("function");
  });

  it("BR02: toRows", () => {
    const api = _api();
    const rows = api.toRows(_data());
    expect(rows.length).toBe(3);
    expect(rows[0].typ).toBe("Zwischenbericht");
    expect(rows[0].status_label).toBe("eingereicht");
    expect(rows[0].freigaben).toBe(0);
    expect(rows[1].freigaben).toBe(1);
    expect(rows[1].letzte_freigabe).toContain("h0a2898");
  });

  it("BR03: filterByStatus + statusCounts", () => {
    const api = _api();
    const rows = api.toRows(_data());
    expect(api.filterByStatus(rows, "").length).toBe(3);
    expect(api.filterByStatus(rows, "submitted").length).toBe(1);
    const counts = api.statusCounts(_data());
    expect(counts.submitted).toBe(1);
    expect(counts.approved).toBe(1);
    expect(counts.draft).toBe(1);
  });

  it("BR04: scanInfoText zeigt die Cache-Wirkung", () => {
    const api = _api();
    const t = api.scanInfoText(_data());
    expect(t).toContain("3 Fall-Datenbanken");
    expect(t).toContain("1 neu eingelesen");
    expect(t).toContain("3 Berichte");
  });

  it("BR05: renderReports — Tabelle, Filter, Neu einlesen", () => {
    const win = _ctx();
    const api = win.AIWCockpitReports;
    const main = win.document.createElement("main");
    let made = null;
    let rescans = 0;
    let filters = [];
    function StubTab(container, opts) {
      made = { container, opts };
      this.replaceData = function (d) { made.replaced = d; };
    }
    const table = api.renderReports(main, _data(), {
      Tabulator: StubTab,
      onForceRescan: function () { rescans++; },
      onFilter: function (s) { filters.push(s); },
    });
    expect(table).toBeInstanceOf(StubTab);
    expect(made.opts.data.length).toBe(3);

    // Neu-einlesen-Knopf.
    main.querySelector("#aiw-reports-rescan").click();
    expect(rescans).toBe(1);

    // Statusfilter: lokal filtern.
    const sel = main.querySelector("#aiw-reports-filter");
    sel.value = "submitted";
    sel.dispatchEvent(new win.Event("change"));
    expect(filters).toEqual(["submitted"]);
    expect(made.replaced.length).toBe(1);
  });

  it("BR06: Hinweise — defekte DBs und Faelle ohne DB sichtbar", () => {
    const win = _ctx();
    const api = win.AIWCockpitReports;
    const main = win.document.createElement("main");
    function StubTab() { this.replaceData = function () {}; }
    api.renderReports(main, _data(), { Tabulator: StubTab });
    const hints = main.querySelector("#aiw-reports-hints");
    expect(hints).toBeTruthy();
    expect(hints.textContent).toContain("nicht lesbar");
    expect(hints.textContent).toContain("22, 23");  // Faelle ohne evidence-DB
  });

  it("BR07: Betriebshinweis bei fehlendem Scan-Cache (Build 376)", () => {
    const win = _ctx();
    const api = win.AIWCockpitReports;
    const main = win.document.createElement("main");
    function StubTab() { this.replaceData = function () {}; }
    const data = _data();
    data.cache_error = "no such table: evidence_scan_cache";
    api.renderReports(main, data, { Tabulator: StubTab });
    const ce = main.querySelector("#aiw-reports-cacheerr");
    expect(ce).toBeTruthy();
    // Der Hinweis nennt den auszufuehrenden Befehl ...
    expect(ce.textContent).toContain("python -m management.migrate");
    // ... und stellt klar, dass die Liste dennoch vollstaendig ist.
    expect(ce.textContent).toContain("vollstaendig");
  });

  // --- Build 378: Freigabe-Aktionen + Siegelpruefung -----------------------

  it("BR08: availableActions spiegelt die Server-Vorbedingungen", () => {
    const api = _api();
    // (Signatur ab Build 380: (row, canApprove, canReview).)
    // Chefin auf 'submitted': freigeben UND zurueckgeben.
    let a = api.availableActions({ status: "submitted" }, true, false);
    expect(a.map((x) => x.kind)).toEqual(["approve", "return"]);
    // Ohne jede Berechtigung: keine Aktion.
    a = api.availableActions({ status: "submitted" }, false, false);
    expect(a).toEqual([]);

    // 'approved': Versand-Kennzeichnung + Siegelpruefung; KEINE Rueckgabe.
    a = api.availableActions({ status: "approved" }, true, false);
    expect(a.map((x) => x.kind)).toEqual(["final", "verify"]);
    // Siegelpruefung geht auch ohne Freigaberecht.
    a = api.availableActions({ status: "approved" }, false, false);
    expect(a.map((x) => x.kind)).toEqual(["verify"]);

    // Entwurf: nichts.
    expect(api.availableActions({ status: "draft" }, true, true)).toEqual([]);
    // Versandt: nur pruefen (unwiderruflich).
    a = api.availableActions({ status: "final" }, true, true);
    expect(a.map((x) => x.kind)).toEqual(["verify"]);
  });

  it("BR09: verifyText benennt eine ABWEICHUNG beim Namen", () => {
    const api = _api();
    expect(api.verifyText({ sealed: false })).toContain("Kein Siegel");
    expect(api.verifyText({ sealed: true, match: true }))
      .toContain("in Ordnung");
    const bad = api.verifyText({ sealed: true, match: false });
    expect(bad).toContain("ABWEICHUNG");
    expect(bad).toContain("Manipulationsverdacht");
  });

  it("BR10: Zeilenklick oeffnet das Aktionsfeld; Knoepfe rufen Callbacks", () => {
    const win = _ctx();
    const api = win.AIWCockpitReports;
    const main = win.document.createElement("main");
    const approvals = [];
    const verifies = [];
    let rowClick = null;
    function StubTab(container, opts) {
      rowClick = opts.rowClick;
      this.replaceData = function () {};
    }
    const data = _data();
    const t = api.renderReports(main, data, {
      Tabulator: StubTab,
      canApprove: true,
      onApprove: (u, r, f) => approvals.push([u, r, f]),
      onVerify: (u, r) => verifies.push([u, r]),
    });

    // Zeile 1 = Fall 18, status 'submitted' -> Freigabe-Knopf.
    const rows = api.toRows(data);
    rowClick(null, { getData: () => rows[0] });
    const btn = main.querySelector("#aiw-report-approve");
    expect(btn).toBeTruthy();
    btn.click();
    expect(approvals[0]).toEqual([18, 1, false]);

    // Zeile 2 = Fall 19, status 'approved' -> 'final' + 'verify'.
    rowClick(null, { getData: () => rows[1] });
    expect(main.querySelector("#aiw-report-final")).toBeTruthy();
    main.querySelector("#aiw-report-verify").click();
    expect(verifies[0]).toEqual([19, 1]);

    // Siegelpruefung anzeigen: ABWEICHUNG wird deutlich dargestellt.
    t.aiwShowVerify({
      sealed: true, match: false, sealed_sha256: "aaa", current_sha256: "bbb",
      approved_by: "h0a2898", approved_at: 1783200000, audit_seq: 42,
      is_final: false,
    });
    const res = main.querySelector("#aiw-report-result");
    expect(res.textContent).toContain("ABWEICHUNG");
    expect(res.querySelector("dl")).toBeTruthy();   // Hash-Gegenueberstellung
  });

  // --- Build 380: Rueckgabe + korrigierte Beschriftung ---------------------

  it("BR11: Rueckgabe-Aktion + korrigierte 'final'-Beschriftung", () => {
    const api = _api();

    // Lektor (nur review): darf zurueckgeben, aber NICHT freigeben.
    let a = api.availableActions({ status: "submitted" }, false, true);
    expect(a.map((x) => x.kind)).toEqual(["return"]);

    // Chefin (approve): freigeben UND zurueckgeben.
    a = api.availableActions({ status: "submitted" }, true, true);
    expect(a.map((x) => x.kind)).toEqual(["approve", "return"]);

    // Ohne beides: keine Aktion auf 'submitted'.
    expect(api.availableActions({ status: "submitted" }, false, false))
      .toEqual([]);

    // 'final' ist NICHT "hoehere Freigabestufe", sondern "an StA versandt".
    a = api.availableActions({ status: "approved" }, true, true);
    const finalAct = a.filter((x) => x.kind === "final")[0];
    expect(finalAct.label).toContain("versandt");
    expect(finalAct.label).not.toContain("Endgueltig freigeben");

    // Aus 'approved' gibt es KEINE Rueckgabe mehr (unwiderruflich).
    expect(a.map((x) => x.kind)).not.toContain("return");
  });

  it("BR12: Rueckgabe-Knopf ruft onReturn", () => {
    const win = _ctx();
    const api = win.AIWCockpitReports;
    const main = win.document.createElement("main");
    const returns = [];
    let rowClick = null;
    function StubTab(container, opts) {
      rowClick = opts.rowClick;
      this.replaceData = function () {};
    }
    const data = _data();
    api.renderReports(main, data, {
      Tabulator: StubTab,
      canApprove: false,
      canReview: true,
      onReturn: (u, r) => returns.push([u, r]),
    });
    const rows = api.toRows(data);
    rowClick(null, { getData: () => rows[0] });   // Fall 18, 'submitted'
    const btn = main.querySelector("#aiw-report-return");
    expect(btn).toBeTruthy();
    btn.click();
    expect(returns[0]).toEqual([18, 1]);
    // Der Lektor sieht KEINEN Freigabe-Knopf.
    expect(main.querySelector("#aiw-report-approve")).toBeNull();
  });
});
