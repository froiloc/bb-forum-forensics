/**
 * tests/unit/test_cockpit_integrity.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit Integritaet (Frontend)
 *
 * Testsuite fuer management/server/static/cockpit_integrity.js (Build 349).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitIntegrity).
 *
 * IN01 — API verfuegbar.
 * IN02 — bannerModel(ok): gruen + 'intakt bis Sequenz N'.
 * IN03 — bannerModel(!ok): rot + 'KETTENBRUCH ab Sequenz M'.
 * IN04 — bannerModel: fehlende Sequenzwerte werden nicht still verschluckt ('?').
 * IN05 — applyBanner(): Klasse + Text gesetzt; entfernt aiw-integrity-hidden.
 * IN06 — renderIntegrity(ok): Kopf + Karte (Status intakt, tip_seq, detail).
 * IN07 — renderIntegrity(!ok): Status KETTENBRUCH + first_bad_seq sichtbar.
 * IN08 — renderIntegrity: detail via textContent (XSS-sicher).
 *
 * Version: v0.7.349 · Build: 349 · 2026-07-10
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_integrity.js",
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
  return _makeContext().AIWCockpitIntegrity;
}

describe("cockpit_integrity.js — Integritaets-/Ops-Sicht (Build 349)", () => {
  // IN01 -------------------------------------------------------------------
  it("IN01: API verfuegbar", () => {
    const api = _api();
    expect(api).toBeTruthy();
    expect(typeof api.bannerModel).toBe("function");
    expect(typeof api.renderIntegrity).toBe("function");
    expect(typeof api.applyBanner).toBe("function");
  });

  // IN02 -------------------------------------------------------------------
  it("IN02: bannerModel ok -> gruen", () => {
    const api = _api();
    const m = api.bannerModel({ ok: true, tip_seq: 39, first_bad_seq: null });
    expect(m.klass).toBe("ok");
    expect(m.text).toContain("intakt");
    expect(m.text).toContain("39");
  });

  // IN03 -------------------------------------------------------------------
  it("IN03: bannerModel !ok -> rot", () => {
    const api = _api();
    const m = api.bannerModel({ ok: false, first_bad_seq: 17, tip_seq: 39 });
    expect(m.klass).toBe("fehler");
    expect(m.text).toContain("KETTENBRUCH");
    expect(m.text).toContain("17");
  });

  // IN04 -------------------------------------------------------------------
  it("IN04: bannerModel fehlende Sequenzen -> '?'", () => {
    const api = _api();
    expect(api.bannerModel({ ok: true }).text).toContain("?");
    expect(
      api.bannerModel({ ok: false, first_bad_seq: null }).text
    ).toContain("?");
  });

  // IN05 -------------------------------------------------------------------
  it("IN05: applyBanner setzt Klasse/Text und entfernt hidden", () => {
    const win = _makeContext();
    const api = win.AIWCockpitIntegrity;
    const el = win.document.createElement("div");
    el.className = "aiw-integrity aiw-integrity-hidden";
    api.applyBanner(el, { klass: "ok", text: "alles gut" });
    expect(el.className).toBe("aiw-integrity ok");
    expect(el.className).not.toContain("aiw-integrity-hidden");
    expect(el.textContent).toBe("alles gut");
  });

  // IN06 -------------------------------------------------------------------
  it("IN06: renderIntegrity ok", () => {
    const win = _makeContext();
    const api = win.AIWCockpitIntegrity;
    const main = win.document.createElement("main");
    api.renderIntegrity(main, {
      ok: true,
      first_bad_seq: null,
      detail: "39 Zeilen geprueft",
      tip_seq: 39,
    });
    expect(main.querySelector(".aiw-pagehead").textContent).toContain(
      "Integritaet"
    );
    const card = main.querySelector(".aiw-card");
    expect(card).toBeTruthy();
    expect(card.textContent).toContain("Kette intakt");
    expect(card.textContent).toContain("39");
    expect(card.querySelector(".dot.gruen")).toBeTruthy();
  });

  // IN07 -------------------------------------------------------------------
  it("IN07: renderIntegrity !ok zeigt Bruchstelle", () => {
    const win = _makeContext();
    const api = win.AIWCockpitIntegrity;
    const main = win.document.createElement("main");
    api.renderIntegrity(main, {
      ok: false,
      first_bad_seq: 17,
      detail: "Hash-Abweichung bei seq=17",
      tip_seq: 39,
    });
    const card = main.querySelector(".aiw-card");
    expect(card.textContent).toContain("KETTENBRUCH");
    expect(card.textContent).toContain("17");
    expect(card.querySelector(".dot.rot")).toBeTruthy();
  });

  // IN08 -------------------------------------------------------------------
  it("IN08: renderIntegrity detail via textContent (XSS-sicher)", () => {
    const win = _makeContext();
    const api = win.AIWCockpitIntegrity;
    const main = win.document.createElement("main");
    api.renderIntegrity(main, {
      ok: false,
      first_bad_seq: 1,
      detail: "<img src=x onerror=alert(1)>",
      tip_seq: 5,
    });
    expect(main.querySelector("img")).toBe(null);
    expect(main.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
