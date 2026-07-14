/**
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
      { user_id: 700, username: "b700", id: 1, report_type: "final",
        sequence_nr: 1, title: "Abschluss", status: "submitted" },
      { user_id: 701, username: "b701", id: 1, report_type: "interim",
        sequence_nr: 1, title: "Zwischen", status: "approved" },
    ],
  };
}

function _mount(win) {
  const main = win.document.createElement("div");
  win.document.body.appendChild(main);
  return main;
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
      "/api/report/render?user_id=700&report_id=1"
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

  it("AP03 renderApproval + Auswahl setzt iframe.src", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    api.renderApproval(main, _data(), { status: "submitted", canApprove: true });
    const items = main.querySelectorAll(".aiw-approval-item");
    expect(items.length).toBe(1); // nur submitted
    const frame = main.querySelector("iframe.aiw-approval-preview");
    expect(frame).not.toBeNull();
    items[0].dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(frame.src).toContain("/api/report/render?user_id=700&report_id=1");
    expect(main.querySelector(".aiw-approval-statusline").textContent)
      .toContain("Zur Abnahme vorgelegt");
  });

  it("AP04 Freigeben/Zurueckweisen rufen Callbacks", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    let approved = null, returned = null;
    api.renderApproval(main, _data(), {
      status: "submitted", canApprove: true,
      onApprove: function (b) { approved = b; },
      onReturn: function (b) { returned = b; },
    });
    main.querySelector(".aiw-approval-item")
      .dispatchEvent(new win.Event("click", { bubbles: true }));

    // Freigeben mit Vermerk + is_final.
    main.querySelector(".aiw-approval-note").value = "geprueft";
    main.querySelector(".aiw-approval-isfinal").checked = true;
    main.querySelector(".aiw-approval-approvebtn")
      .dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(approved).toEqual({
      user_id: 700, report_id: 1, is_final: true, note: "geprueft",
    });

    // Zurueckweisen mit Grund.
    main.querySelector(".aiw-approval-returnnote").value = "nachbessern";
    main.querySelector(".aiw-approval-returnbtn")
      .dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(returned).toEqual({
      user_id: 700, report_id: 1, note: "nachbessern",
    });
  });

  it("AP05 ohne canApprove keine Freigabe-Knoepfe", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    api.renderApproval(main, _data(), { status: "submitted", canApprove: false });
    main.querySelector(".aiw-approval-item")
      .dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(main.querySelector(".aiw-approval-approvebtn")).toBeNull();
    expect(main.querySelector(".aiw-approval-action").textContent)
      .toContain("reports.approve");
  });

  it("AP06 Siegelpruefung", () => {
    const win = _ctx();
    const api = _api(win);
    const main = _mount(win);
    let verified = null;
    api.renderApproval(main, _data(), {
      status: "submitted", canApprove: true,
      onVerify: function (uid, rid) { verified = [uid, rid]; },
    });
    main.querySelector(".aiw-approval-item")
      .dispatchEvent(new win.Event("click", { bubbles: true }));
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
    api.renderApproval(main, _data(), { status: "approved", canApprove: true });
    main.querySelector(".aiw-approval-item")
      .dispatchEvent(new win.Event("click", { bubbles: true }));
    expect(main.querySelector(".aiw-approval-approvebtn")).toBeNull();
    expect(main.querySelector(".aiw-approval-action").textContent)
      .toContain("Nur vorgelegte");
  });

  // --- Support-View: Belege (SF-2) + Kommentare (SF-3), Build 417 ---------
  it("AP08 reine Support-Helfer", () => {
    const api = _api();
    expect(api.annotationsUrl(700, 1)).toBe(
      "/api/report/annotations?user_id=700&report_id=1"
    );
    expect(api.commentsUrl(700, 1)).toBe(
      "/api/report/comments?user_id=700&report_id=1"
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
    api.renderApproval(main, _data(), {
      status: "submitted", canApprove: true,
      onSelect: function (uid, rid) { sel = [uid, rid]; },
    });
    // Support-Panels existieren.
    expect(main.querySelector(".aiw-approval-annotations")).not.toBeNull();
    expect(main.querySelector(".aiw-approval-comments")).not.toBeNull();

    main.querySelector(".aiw-approval-item")
      .dispatchEvent(new win.Event("click", { bubbles: true }));
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
    expect(api.resultsUrl(700)).toBe("/api/results?user_id=700");
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
      user_id: 700, can_edit: false,
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
    api.renderResults({ user_id: 700, current: [], score: null });
    expect(main.querySelector(".aiw-approval-results").textContent)
      .toContain("Noch keine Ermittlungsergebnisse");

    // Fehler (z.B. 403) -> sichtbar.
    api.resultsError("HTTP 403");
    expect(main.querySelector(".aiw-approval-results").textContent)
      .toContain("HTTP 403");
  });
});
