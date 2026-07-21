/**
 * Build 469: Schluesselumstellung user_id -> subject_id (M019)
 * Version: v0.7.469 · Build: 469 · 2026-07-20
 * tests/unit/test_cockpit_approval.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Chef-Freigabe (W5)
 *
 * Testsuite fuer management/server/static/cockpit_approval.js (Build 416,
 * Slice 1). Testet den ECHTEN Code (readFileSync + JSDOM,
 * window.AIWCockpitApproval).
 *
 * AP01 — API verfuegbar.
 * AP02 — reine Helfer: statusLabel/filterReports/renderUrl/canApprove/
 *        canVerify/verifyText.
 * AP03 — renderApproval: Auswahl (nur submitted) + iframe; Klick setzt
 *        iframe.src + baut Aktionsbereich.
 * AP04 — Aktionsbereich (submitted + canApprove): Freigeben ruft onApprove mit
 *        {is_final, note}; Zurueckweisen ruft onReturn.
 * AP05 — ohne canApprove: keine Freigabe-Knoepfe, Hinweis auf reports.approve.
 * AP06 — Siegelpruefung: Knopf ruft onVerify; renderVerify zeigt Klartext.
 * AP07 — nicht-vorgelegter Bericht: Hinweis, keine Freigabe-Knoepfe.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_approval.js",
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
function _api(win) { return (win || _ctx()).AIWCockpitApproval; }

function _data() {
  return {
    scope: "alle", count: 2,
    reports: [
      { subject_id: 700, username: "b700", id: 1, report_type: "final",
        sequence_nr: 1, title: "Abschluss", status: "submitted" },
      { subject_id: 701, username: "b701", id: 1, report_type: "interim",
        sequence_nr: 1, title: "Zwischen", status: "approved" },
    ],
  };
}

function _mount(win) {
  const main = win.document.createElement("div");
  win.document.body.appendChild(main);
  return main;
}

// Build 483: Auswahl erfolgt jetzt ueber den Tabulator-rowClick (statt einer
// Button-Liste). Der Tabulator-Ctor wird als Stub injiziert; die Auswahl wird
// durch direkten Aufruf von opts.rowClick simuliert.
function _stubTab() {
  let made = null;
  function StubTab(container, opts) {
    made = { container, opts };
    this.replaceData = function (d) { made.replaced = d; };
    this.destroy = function () {};
  }
  return { StubTab, get: () => made };
}
function _pick(made, i) {
  const row = made.opts.data[i || 0];
  made.opts.rowClick({}, { getData: () => row, getElement: () => null });
}

describe("cockpit_approval", () => {
  it("AP01 API verfuegbar", () => {
    const api = _api();
    expect(typeof api.renderApproval).toBe("function");
    expect(typeof api.renderVerify).toBe("function");
    expect(typeof api.verifyText).toBe("function");
    expect(typeof api.cleanup).toBe("function");
  });

  it("AP02 reine Helfer", () => {
    const api = _api();
    expect(api.statusLabel("submitted")).toBe("Zur Abnahme vorgelegt");
    expect(api.filterReports(_data(), "submitted").length).toBe(1);
    expect(api.filterReports(_data(), "alle").length).toBe(2);
    expect(api.renderUrl(700, 1)).toBe(
      "/api/report/render?subject_id=700&report_id=1"
    );
    expect(api.canApprove("submitted")).toBe(true);
    expect(api.canApprove("approved")).toBe(false);
    expect(api.canVerify("approved")).toBe(true);
    expect(api.canVerify("submitted")).toBe(false);
    expect(api.verifyText({ sealed: true, match: true }))
      .toContain("Siegel in Ordnung");
    expect(api.verifyText({ sealed: true, match: false }))
      .toContain("ABWEICHUNG");
    expect(api.verifyText({ sealed: false })).toContain("Kein Siegel");
  });

  it("AP03 renderApproval: Tabulator-Tabelle + rowClick setzt iframe.src", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    const tab = _stubTab();
    api.renderApproval(main, _data(), {
      status: "submitted", canApprove: true, Tabulator: tab.StubTab,
    });
    expect(tab.get().opts.data.length).toBe(1); // nur submitted
    // Build 483: Header-Filter + Paginierung 20/Seite.
    const cols = tab.get().opts.columns;
    expect(cols.find((c) => c.field === "username").headerFilter).toBe("input");
    expect(tab.get().opts.pagination).toBe("local");
    expect(tab.get().opts.paginationSize).toBe(20);
    const frame = main.querySelector("iframe.aiw-approval-preview");
    expect(frame).not.toBeNull();
    _pick(tab.get());
    expect(frame.src).toContain("/api/report/render?subject_id=700&report_id=1");
    expect(main.querySelector(".aiw-approval-statusline").textContent)
      .toContain("Zur Abnahme vorgelegt");
  });

  it("AP04 Freigeben/Zurueckweisen rufen Callbacks", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    let approved = null, returned = null;
    const tab = _stubTab();
    api.renderApproval(main, _data(), {
      status: "submitted", canApprove: true, Tabulator: tab.StubTab,
      onApprove: function (b) { approved = b; },
      onReturn: function (b) { returned = b; },
    });
    _pick(tab.get());

    // Freigeben mit Vermerk + is_final.
    main.querySelector(".aiw-approval-note").value = "geprueft";
    main.querySelector(".aiw-approval-isfinal").checked = true;
    main.querySelector(".aiw-approval-approvebtn")
      .dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(approved).toEqual({
      subject_id: 700, report_id: 1, is_final: true, note: "geprueft",
    });

    // Zurueckweisen mit Grund.
    main.querySelector(".aiw-approval-returnnote").value = "nachbessern";
    main.querySelector(".aiw-approval-returnbtn")
      .dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(returned).toEqual({
      subject_id: 700, report_id: 1, note: "nachbessern",
    });
  });

  it("AP05 ohne canApprove keine Freigabe-Knoepfe", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    const tab = _stubTab();
    api.renderApproval(main, _data(), {
      status: "submitted", canApprove: false, Tabulator: tab.StubTab,
    });
    _pick(tab.get());
    expect(main.querySelector(".aiw-approval-approvebtn")).toBeNull();
    expect(main.querySelector(".aiw-approval-action").textContent)
      .toContain("reports.approve");
  });

  it("AP06 Siegelpruefung", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    let verified = null;
    const tab = _stubTab();
    api.renderApproval(main, _data(), {
      status: "submitted", canApprove: true, Tabulator: tab.StubTab,
      onVerify: function (uid, rid) { verified = [uid, rid]; },
    });
    _pick(tab.get());
    main.querySelector(".aiw-approval-verify")
      .dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(verified).toEqual([700, 1]);

    api.renderVerify({ sealed: true, match: false });
    const vb = main.querySelector(".aiw-approval-verifybox");
    expect(vb.textContent).toContain("ABWEICHUNG");
    expect(vb.getAttribute("data-match")).toBe("mismatch");
  });

  it("AP07 nicht-vorgelegter Bericht -> Hinweis", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    const tab = _stubTab();
    api.renderApproval(main, _data(), {
      status: "approved", canApprove: true, Tabulator: tab.StubTab,
    });
    _pick(tab.get()); // erster (und einziger) Bericht im Status 'approved'
    expect(main.querySelector(".aiw-approval-approvebtn")).toBeNull();
    expect(main.querySelector(".aiw-approval-action").textContent)
      .toContain("Nur vorgelegte");
  });

  // --- Support-View: Belege (SF-2) + Kommentare (SF-3), Build 417 ---------
  it("AP08 reine Support-Helfer", () => {
    const api = _api();
    expect(api.annotationsUrl(700, 1)).toBe(
      "/api/report/annotations?subject_id=700&report_id=1"
    );
    expect(api.commentsUrl(700, 1)).toBe(
      "/api/report/comments?subject_id=700&report_id=1"
    );
    expect(api.categoryLabel("CAT_PERSON")).toBe("Person");
    expect(api.forumContext({ topic_id: 7, forum_id: 3 }))
      .toBe("Thema 7 · Unterforum 3");
    expect(api.commentStatusLabel("addressed")).toBe("erledigt");
    expect(api.reviewerRoleLabel("supervisor")).toBe("Chef-Ermittlerin");
  });

  it("AP09 Auswahl loest onSelect; Belege + Kommentare rendern", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    let sel = null;
    const tab = _stubTab();
    api.renderApproval(main, _data(), {
      status: "submitted", canApprove: true, Tabulator: tab.StubTab,
      onSelect: function (uid, rid) { sel = [uid, rid]; },
    });
    // Support-Panels existieren.
    expect(main.querySelector(".aiw-approval-annotations")).not.toBeNull();
    expect(main.querySelector(".aiw-approval-comments")).not.toBeNull();

    _pick(tab.get());
    expect(sel).toEqual([700, 1]);

    api.renderAnnotations({
      items: [
        { annotation_id: 10, block_id: "b1", block_type: "evidence",
          category: "CAT_PERSON", text: "Beleg A", post_id: 42,
          topic_id: 7, forum_id: 3, missing: false, deleted: false },
      ],
    });
    const annItems = main.querySelectorAll(".aiw-approval-ann-item");
    expect(annItems.length).toBe(1);
    expect(main.querySelector(".aiw-approval-annotations").textContent)
      .toContain("Beleg A");

    api.renderComments({
      comments: [
        { comment_id: "c1", block_id: "b1", reviewer_pid: 1,
          reviewer_role: "lector", comment_text: "Bitte praezisieren",
          suggested_content: null, status: "pending" },
      ],
    });
    const comItems = main.querySelectorAll(".aiw-approval-com-item");
    expect(comItems.length).toBe(1);
    expect(main.querySelector(".aiw-approval-comments").textContent)
      .toContain("Bitte praezisieren");
  });

  it("AP10 Kommentare read-only: kein Formular, keine Aufloesen-Knoepfe", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    api.renderApproval(main, _data(), { status: "submitted", canApprove: true });
    api.renderComments({
      comments: [
        { comment_id: "c1", reviewer_pid: 1, reviewer_role: "lector",
          comment_text: "X", status: "pending" },
      ],
    });
    const panel = main.querySelector(".aiw-approval-comments");
    expect(panel.querySelector("form")).toBeNull();
    expect(panel.querySelector("textarea")).toBeNull();
    expect(panel.querySelector(".aiw-approval-com-resolve")).toBeNull();
    // leere Belege -> Hinweis.
    api.renderAnnotations({ items: [] });
    expect(main.querySelector(".aiw-approval-annotations").textContent)
      .toContain("keine Belege");
  });

  // --- Ermittlungsergebnis (results, read-only, Build 418) ---------------
  it("AP11 reine Ergebnis-Helfer", () => {
    const api = _api();
    expect(api.resultsUrl(700)).toBe("/api/results?subject_id=700");
    expect(api.extremLabel("schwerste")).toBe("schwerste Auspraegung");
    expect(api.extremLabel("beste")).toBe("beste Auspraegung");
    expect(api.gapLabel({ code: "x", label: "Ort" })).toBe("Ort");
    expect(api.gapLabel("location")).toBe("location");
  });

  it("AP12 renderResults: Kennzahl, aktueller Stand, Luecken", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    api.renderApproval(main, _data(), { status: "submitted", canApprove: true });
    expect(main.querySelector(".aiw-approval-results")).not.toBeNull();

    api.renderResults({
      subject_id: 700, can_edit: false,
      current: [
        { criterion_code: "identification",
          criterion_label: "Identifizierung", extrem: "schwerste",
          confidence_code: "high", confidence_label: "hoch",
          quality_code: "q2", quality_label: "gut" },
      ],
      score: { score: 7.5, basis: 1, vermerk: "Vorlaeufige Zahl.",
               unbewertet: [{ code: "location", label: "Ort" }] },
    });
    const panel = main.querySelector(".aiw-approval-results");
    expect(panel.querySelector(".aiw-approval-res-score").textContent)
      .toContain("7.5");
    const items = panel.querySelectorAll(".aiw-approval-res-item");
    expect(items.length).toBe(1);
    expect(items[0].textContent).toContain("Identifizierung");
    expect(items[0].textContent).toContain("hoch");
    expect(items[0].textContent).toContain("gut");
    expect(panel.querySelector(".aiw-approval-res-gaps").textContent)
      .toContain("Ort");

    // Kein Ergebnis -> Hinweis.
    api.renderResults({ subject_id: 700, current: [], score: null });
    expect(main.querySelector(".aiw-approval-results").textContent)
      .toContain("Noch keine Ermittlungsergebnisse");

    // Fehler (z.B. 403) -> sichtbar.
    api.resultsError("HTTP 403");
    expect(main.querySelector(".aiw-approval-results").textContent)
      .toContain("HTTP 403");
  });

  // --- Bewertungs-Formular (einpflegen, append-only, Build 419) -----------
  function _catalog() {
    return {
      catalog_version: 2,
      extreme: ["schwerste", "beste"],
      confidence_items: [
        { code: "low", label: "niedrig" }, { code: "high", label: "hoch" },
      ],
      criteria: [
        { code: "identification", label: "Identifizierung",
          quality_items: [{ code: "q1", label: "schwach" },
                          { code: "q2", label: "gut" }] },
        { code: "location", label: "Ort", quality_items: [] },
      ],
      can_edit: true,
    };
  }

  it("AP13 qualityItemsFor", () => {
    const api = _api();
    const cat = _catalog();
    expect(api.qualityItemsFor(cat, "identification").length).toBe(2);
    expect(api.qualityItemsFor(cat, "location").length).toBe(0);
    expect(api.qualityItemsFor(cat, "unbekannt").length).toBe(0);
  });

  it("AP14 renderAssessForm: Auswahlfelder, Kopplung, Absenden", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    api.renderApproval(main, _data(), { status: "submitted", canApprove: true });

    let assessed = null;
    api.renderAssessForm(_catalog(), {
      subjectId: 700, onAssess: function (b) { assessed = b; },
    });
    const panel = main.querySelector(".aiw-approval-results");
    expect(panel.querySelector(".aiw-approval-assess-form")).not.toBeNull();
    expect(panel.querySelectorAll(".aiw-approval-assess-crit option").length)
      .toBe(2);
    expect(panel.querySelectorAll(".aiw-approval-assess-conf option").length)
      .toBe(2);
    expect(panel.querySelectorAll(".aiw-approval-assess-extrem option").length)
      .toBe(2);
    // Qualitaet fuer 'identification' = leer + 2.
    const qual = panel.querySelector(".aiw-approval-assess-qual");
    expect(qual.querySelectorAll("option").length).toBe(3);

    // Kriteriumwechsel -> Qualitaets-Optionen ziehen nach ('location' = leer).
    const crit = panel.querySelector(".aiw-approval-assess-crit");
    crit.value = "location";
    crit.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(qual.querySelectorAll("option").length).toBe(1);

    // Zurueck auf identification, Werte setzen, absenden.
    crit.value = "identification";
    crit.dispatchEvent(new win.Event("change", { bubbles: true }));
    panel.querySelector(".aiw-approval-assess-extrem").value = "schwerste";
    panel.querySelector(".aiw-approval-assess-conf").value = "high";
    panel.querySelector(".aiw-approval-assess-qual").value = "q2";
    panel.querySelector(".aiw-approval-assess-note").value = "geprueft";
    panel.querySelector(".aiw-approval-assess-form").dispatchEvent(
      new win.Event("submit", { bubbles: true, cancelable: true })
    );
    expect(assessed).toEqual({
      subject_id: 700, criterion_code: "identification", extrem: "schwerste",
      confidence_code: "high", quality_code: "q2", note: "geprueft",
    });
  });

  it("AP15 renderAssessForm: fehlende Pflichtangabe -> Fehler, kein onAssess", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    api.renderApproval(main, _data(), { status: "submitted", canApprove: true });
    let assessed = null;
    api.renderAssessForm(_catalog(), {
      subjectId: 700, onAssess: function (b) { assessed = b; },
    });
    const panel = main.querySelector(".aiw-approval-results");
    // Konfidenz auf leeren Wert zwingen (kein passendes <option>).
    panel.querySelector(".aiw-approval-assess-conf").value = "";
    panel.querySelector(".aiw-approval-assess-form").dispatchEvent(
      new win.Event("submit", { bubbles: true, cancelable: true })
    );
    expect(assessed).toBeNull();
    expect(panel.querySelector(".aiw-approval-assess-err").textContent)
      .toContain("erforderlich");
  });

  // --- Tabulator-Umbau (Build 483) --------------------------------------
  it("AP16 toRows: Felder + Fallbacks (Grundregel 1)", () => {
    const api = _api();
    const rows = api.toRows(_data(), "submitted");
    expect(rows.length).toBe(1); // nur submitted
    expect(rows[0]).toMatchObject({
      subject_id: 700, id: 1, username: "b700", title: "Abschluss",
      status: "submitted", status_label: "Zur Abnahme vorgelegt",
    });
    expect(rows[0].typ).toBe("Abschlussbericht"); // final -> Abschlussbericht
    const rows2 = api.toRows(
      { reports: [{ subject_id: 88, id: 9, status: "submitted" }] }, "submitted"
    );
    expect(rows2[0].username).toBe("uid 88");
    expect(rows2[0].title).toBe("(ohne Titel)");
  });

  it("AP17 statusCounts: Trefferzahl je Status + Gesamt", () => {
    const api = _api();
    const c = api.statusCounts(_data());
    expect(c.submitted).toBe(1);
    expect(c.approved).toBe(1);
    expect(c.alle).toBe(2);
    expect(c.draft).toBe(0);
  });

  it("AP18 Status-Schnellfilter zeigt Zaehler in den Optionen", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    const tab = _stubTab();
    api.renderApproval(main, _data(), {
      status: "submitted", canApprove: true, Tabulator: tab.StubTab,
    });
    const sel = main.querySelector("select.aiw-approval-status");
    const opts = Array.from(sel.options).map((o) => o.textContent);
    expect(opts).toContain("Zur Abnahme vorgelegt (1)");
    expect(opts).toContain("Alle (2)");
    // Statuswechsel tauscht die Daten via replaceData (kein Neu-Render).
    sel.value = "alle";
    sel.dispatchEvent(new win.Event("change", { bubbles: true }));
    expect(tab.get().replaced.length).toBe(2);
  });
});
