/**
 * tests/unit/test_cockpit_promotion.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Fremdforum-Promotion
 *
 * Testsuite fuer management/server/static/cockpit_promotion.js (Build 461).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitPromotion).
 *
 * PP01 — API verfuegbar.
 * PP02 — allowedActions: offen -> 4 Ziele; gesichtet -> 3 (kein Selbst-Ueber-
 *        gang); zurueckgestellt enthaelt 'gesichtet' (Wiederaufgriff); End-
 *        zustaende -> [].
 * PP03 — reasonRequired/isFinal korrekt.
 * PP04 — countsModel: geordnet, fehlende Schluessel -> 0.
 * PP05 — statusDotClass: uebernommen=gruen, fremdzustaendig=rot, sonst gelb.
 * PP06 — renderPromotion: Kopf, Kennzahlen, Kandidatenzeilen; mit Recht
 *        Aktions-Buttons, ohne Recht Nur-Lesend-Hinweis und KEINE Buttons.
 * PP07 — Panel: grund-pflichtiges Ziel ohne Grund -> onDecide NICHT gerufen +
 *        Fehlermeldung; mit Grund -> onDecide mit korrektem Body.
 * PP08 — Panel: nicht-grund-pflichtiges Ziel (uebernommen) ohne Grund ->
 *        onDecide gerufen; Endzustand zeigt Warnung.
 * PP09 — leere Kandidatenliste -> Platzhalter; grund/herkunft via textContent
 *        (XSS-sicher).
 *
 * Version: v0.7.461 · Build: 461 · 2026-07-20
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_promotion.js",
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
  return _win().AIWCockpitPromotion;
}

function _sampleData() {
  return {
    candidate_count: 3,
    counts: { offen: 1, gesichtet: 1, zurueckgestellt: 1 },
    statuses: ["gesichtet", "uebernommen", "zurueckgestellt", "fremdzustaendig"],
    candidates: [
      { user_id: 77, status: "offen", status_label: "offen (unentschieden)",
        grund: null, herkunft: null, is_final: false },
      { user_id: 88, status: "gesichtet", status_label: "gesichtet",
        grund: null, herkunft: "Nachbarforum", is_final: false },
      { user_id: 99, status: "uebernommen", status_label: "uebernommen",
        grund: null, herkunft: null, is_final: true },
    ],
    decisions: [],
  };
}

describe("cockpit_promotion.js — Fremdforum-Promotion (Build 461)", () => {
  // PP01 -------------------------------------------------------------------
  it("PP01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.allowedActions).toBe("function");
    expect(typeof api.renderPromotion).toBe("function");
    expect(typeof api.countsModel).toBe("function");
  });

  // PP02 -------------------------------------------------------------------
  it("PP02: allowedActions spiegelt die Zustandsmaschine", () => {
    const api = _api();
    expect(api.allowedActions("offen").sort()).toEqual(
      ["fremdzustaendig", "gesichtet", "uebernommen", "zurueckgestellt"]
    );
    // gesichtet: kein Selbst-Uebergang.
    expect(api.allowedActions("gesichtet")).not.toContain("gesichtet");
    expect(api.allowedActions("gesichtet").sort()).toEqual(
      ["fremdzustaendig", "uebernommen", "zurueckgestellt"]
    );
    // Wiederaufgriff.
    expect(api.allowedActions("zurueckgestellt")).toContain("gesichtet");
    // Endzustaende: keine Aktion.
    expect(api.allowedActions("uebernommen")).toEqual([]);
    expect(api.allowedActions("fremdzustaendig")).toEqual([]);
    // Unbekannt -> leer, kein Fehler.
    expect(api.allowedActions("quatsch")).toEqual([]);
  });

  // PP03 -------------------------------------------------------------------
  it("PP03: reasonRequired/isFinal", () => {
    const api = _api();
    expect(api.reasonRequired("zurueckgestellt")).toBe(true);
    expect(api.reasonRequired("fremdzustaendig")).toBe(true);
    expect(api.reasonRequired("uebernommen")).toBe(false);
    expect(api.isFinal("uebernommen")).toBe(true);
    expect(api.isFinal("fremdzustaendig")).toBe(true);
    expect(api.isFinal("gesichtet")).toBe(false);
  });

  // PP04 -------------------------------------------------------------------
  it("PP04: countsModel geordnet, fehlende -> 0", () => {
    const api = _api();
    const m = api.countsModel({ counts: { offen: 2 } });
    expect(m.map((c) => c.status)).toEqual(
      ["offen", "gesichtet", "zurueckgestellt", "uebernommen", "fremdzustaendig"]
    );
    expect(m[0].count).toBe(2);
    expect(m[3].count).toBe(0); // uebernommen fehlt -> 0
  });

  // PP05 -------------------------------------------------------------------
  it("PP05: statusDotClass-Ampel", () => {
    const api = _api();
    expect(api.statusDotClass("uebernommen")).toBe("gruen");
    expect(api.statusDotClass("fremdzustaendig")).toBe("rot");
    expect(api.statusDotClass("offen")).toBe("gelb");
    expect(api.statusDotClass("zurueckgestellt")).toBe("gelb");
  });

  // PP06 -------------------------------------------------------------------
  it("PP06: renderPromotion mit/ohne Recht", () => {
    const win = _win();
    const api = win.AIWCockpitPromotion;
    const doc = win.document;

    // mit Recht: Aktions-Buttons vorhanden (offen -> 4).
    const main = doc.createElement("main");
    api.renderPromotion(main, _sampleData(), { canEdit: true, doc: doc });
    expect(main.querySelector(".aiw-pagehead").textContent).toContain(
      "Fremdforum-Promotion"
    );
    expect(main.querySelectorAll(".aiw-promo-table tbody tr").length).toBe(3);
    const btns77 = main.querySelectorAll('button[data-uid="77"]');
    expect(btns77.length).toBe(4);
    // Endgueltiger Kandidat 99 -> keine Aktions-Buttons.
    expect(main.querySelectorAll('button[data-uid="99"]').length).toBe(0);

    // ohne Recht: Hinweis + keine Buttons.
    const main2 = doc.createElement("main");
    api.renderPromotion(main2, _sampleData(), { canEdit: false, doc: doc });
    expect(main2.querySelector(".aiw-promo-readonly")).toBeTruthy();
    expect(main2.querySelectorAll("button[data-target]").length).toBe(0);
  });

  // PP07 -------------------------------------------------------------------
  it("PP07: Grund-Pflicht im Panel", () => {
    const win = _win();
    const api = win.AIWCockpitPromotion;
    const doc = win.document;
    const main = doc.createElement("main");
    const calls = [];
    api.renderPromotion(main, _sampleData(), {
      canEdit: true, doc: doc,
      onDecide: (body) => calls.push(body),
    });

    // 'zurueckgestellt' an Kandidat 77 -> Panel oeffnen.
    main.querySelector(
      'button[data-uid="77"][data-target="zurueckgestellt"]'
    ).click();
    // Bestaetigen OHNE Grund -> kein onDecide, Fehlermeldung.
    main.querySelector("#aiw-promo-confirm").click();
    expect(calls.length).toBe(0);
    expect(main.querySelector("#aiw-promo-result").className).toContain(
      "error"
    );

    // Panel erneut oeffnen, Grund setzen, bestaetigen.
    main.querySelector(
      'button[data-uid="77"][data-target="zurueckgestellt"]'
    ).click();
    main.querySelector("#aiw-promo-herkunft").value = "Forum Y";
    main.querySelector("#aiw-promo-grund").value = "kein Fallbezug";
    main.querySelector("#aiw-promo-confirm").click();
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({
      user_id: 77, status: "zurueckgestellt",
      grund: "kein Fallbezug", herkunft: "Forum Y",
    });
  });

  // PP08 -------------------------------------------------------------------
  it("PP08: nicht-grund-pflichtiges Ziel + Endzustands-Warnung", () => {
    const win = _win();
    const api = win.AIWCockpitPromotion;
    const doc = win.document;
    const main = doc.createElement("main");
    const calls = [];
    api.renderPromotion(main, _sampleData(), {
      canEdit: true, doc: doc,
      onDecide: (body) => calls.push(body),
    });

    // 'uebernommen' (endgueltig, aber KEIN Grund noetig) an 88.
    main.querySelector(
      'button[data-uid="88"][data-target="uebernommen"]'
    ).click();
    // Endzustand zeigt Warnung.
    expect(main.querySelector(".aiw-promo-warn")).toBeTruthy();
    // Ohne Grund bestaetigen -> onDecide gerufen (herkunft aus Vorbelegung).
    main.querySelector("#aiw-promo-confirm").click();
    expect(calls.length).toBe(1);
    expect(calls[0].user_id).toBe(88);
    expect(calls[0].status).toBe("uebernommen");
    expect(calls[0].grund).toBe("");
  });

  // PP09 -------------------------------------------------------------------
  it("PP09: leere Liste -> Platzhalter; Freitext XSS-sicher", () => {
    const win = _win();
    const api = win.AIWCockpitPromotion;
    const doc = win.document;

    const empty = doc.createElement("main");
    api.renderPromotion(empty, { candidate_count: 0, counts: {}, candidates: [] },
      { canEdit: true, doc: doc });
    expect(empty.querySelector(".aiw-placeholder")).toBeTruthy();
    expect(empty.querySelector(".aiw-promo-table")).toBe(null);

    const main = doc.createElement("main");
    api.renderPromotion(main, {
      candidate_count: 1, counts: {},
      candidates: [{ user_id: 5, status: "zurueckgestellt",
        status_label: "zurueckgestellt",
        grund: "<img src=x onerror=alert(1)>", herkunft: null }],
    }, { canEdit: false, doc: doc });
    expect(main.querySelector("img")).toBe(null);
    expect(main.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
