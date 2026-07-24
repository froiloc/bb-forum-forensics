/**
 * Version: v0.8.502 · Build: 502 · 2026-07-24
 * tests/unit/test_cockpit_adsync.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7: Cockpit AD-Abgleich
 *
 * Testsuite fuer management/server/static/cockpit_adsync.js (Build 502).
 * Testet den ECHTEN Code (readFileSync + JSDOM, window.AIWCockpitAdSync).
 *
 * ADS01 — API verfuegbar (renderAdSync + reine Funktionen).
 * ADS02 — counts/hasAutomatic/summaryText: Zaehler defensiv, Lagebild-Zeile.
 * ADS03 — confirmWords: Serverworte; Fallback nur ohne Serverangabe.
 * ADS04 — validateWord: EXAKTER Vergleich (kein trim, keine Gross/Klein-
 *         Toleranz — 'entfernen' zaehlt nicht).
 * ADS05 — decideBody: Request-Koerper je Aktion (nur gesetzte Felder).
 * ADS06 — renderAdSync: Abschnitte nur bei Inhalt; Kandidaten-Zeilen mit
 *         Wort-Eingabe; XSS-sicher (textContent, kein innerHTML-Markup).
 * ADS07 — Deaktivieren-Klick mit falschem Wort -> KEIN onDecide, Fehlerzeile;
 *         mit exaktem Wort -> onDecide({action:'deactivate', ...}).
 * ADS08 — 'Abbruch protokollieren' -> onDecide({action:'abort', note}).
 * ADS09 — Reaktivieren mit exaktem Wort -> onDecide mit display_name_ad;
 *         Apply-Knopf ruft onApply und sperrt sich (Doppelklick-Schutz).
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _src = readFileSync(
  "management/server/static/cockpit_adsync.js",
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

function _data(overrides) {
  return Object.assign(
    {
      group: "SEC_AIW_Ermittler",
      confirm: { deactivate: "Entfernen", reactivate: "Reaktivieren" },
      create: [{ sam: "h0neu", display_name: "KOKin Neuling" }],
      rename: [
        {
          person_id: 2,
          system_username: "h0erm",
          display_name_alt: "KHK Muster",
          display_name_neu: "KHK Muster, PP Neustadt",
        },
      ],
      deactivate_candidates: [
        { person_id: 3, system_username: "h0weg", display_name: "KOK Weg" },
      ],
      reactivate_candidates: [
        {
          person_id: 4,
          system_username: "h0alt",
          display_name: "KHKin Ruhe",
          display_name_ad: "KHKin Zurueck",
        },
      ],
      counts: {
        create: 1,
        rename: 1,
        deactivate_candidates: 1,
        reactivate_candidates: 1,
        unchanged: 5,
        unchanged_inactive: 2,
      },
    },
    overrides || {}
  );
}

describe("cockpit_adsync", () => {
  // ADS01 --------------------------------------------------------------------
  it("ADS01: API verfuegbar", () => {
    const w = _ctx();
    const api = w.AIWCockpitAdSync;
    expect(api).toBeTruthy();
    for (const fn of [
      "renderAdSync",
      "counts",
      "hasAutomatic",
      "summaryText",
      "confirmWords",
      "validateWord",
      "decideBody",
    ]) {
      expect(typeof api[fn]).toBe("function");
    }
  });

  // ADS02 --------------------------------------------------------------------
  it("ADS02: counts defensiv + summaryText", () => {
    const api = _ctx().AIWCockpitAdSync;
    expect(api.counts(null)).toEqual({
      create: 0,
      rename: 0,
      deactivate_candidates: 0,
      reactivate_candidates: 0,
      unchanged: 0,
      unchanged_inactive: 0,
    });
    expect(api.hasAutomatic(_data())).toBe(true);
    expect(api.hasAutomatic(_data({ counts: { create: 0, rename: 0 } }))).toBe(
      false
    );
    const line = api.summaryText(_data());
    expect(line).toContain("Neu: 1");
    expect(line).toContain("Entfernungs-Kandidaten: 1");
    expect(line).toContain("unveraendert aktiv: 5");
  });

  // ADS03 --------------------------------------------------------------------
  it("ADS03: confirmWords vom Server, Fallback ohne Angabe", () => {
    const api = _ctx().AIWCockpitAdSync;
    expect(api.confirmWords(_data())).toEqual({
      deactivate: "Entfernen",
      reactivate: "Reaktivieren",
    });
    expect(api.confirmWords({})).toEqual({
      deactivate: "Entfernen",
      reactivate: "Reaktivieren",
    });
  });

  // ADS04 --------------------------------------------------------------------
  it("ADS04: validateWord exakt", () => {
    const api = _ctx().AIWCockpitAdSync;
    expect(api.validateWord("Entfernen", "Entfernen")).toBe(true);
    expect(api.validateWord("Entfernen", "entfernen")).toBe(false);
    expect(api.validateWord("Entfernen", "Entfernen ")).toBe(false);
    expect(api.validateWord("Entfernen", "")).toBe(false);
    expect(api.validateWord("Entfernen", null)).toBe(false);
  });

  // ADS05 --------------------------------------------------------------------
  it("ADS05: decideBody nur gesetzte Felder", () => {
    const api = _ctx().AIWCockpitAdSync;
    expect(api.decideBody("h0weg", "deactivate", "Entfernen")).toEqual({
      system_username: "h0weg",
      action: "deactivate",
      confirmation: "Entfernen",
    });
    expect(api.decideBody("h0weg", "abort", null, "erst fragen")).toEqual({
      system_username: "h0weg",
      action: "abort",
      note: "erst fragen",
    });
    expect(
      api.decideBody("h0alt", "reactivate", "Reaktivieren", null, "KHKin Z")
    ).toEqual({
      system_username: "h0alt",
      action: "reactivate",
      confirmation: "Reaktivieren",
      display_name_ad: "KHKin Z",
    });
  });

  // ADS06 --------------------------------------------------------------------
  it("ADS06: renderAdSync Abschnitte + XSS-sicher", () => {
    const w = _ctx();
    const api = w.AIWCockpitAdSync;
    const main = w.document.createElement("div");
    const data = _data({
      create: [{ sam: "h0neu", display_name: "<img src=x onerror=alert(1)>" }],
    });
    const view = api.renderAdSync(main, data, { doc: w.document });
    expect(typeof view.setResult).toBe("function");
    // Abschnitte vorhanden (Neu/Umbenennung/Kandidaten).
    const sects = main.querySelectorAll(".aiw-adsync-sect");
    expect(sects.length).toBe(4);
    // XSS: der Angreifertext ist TEXT, kein Element.
    expect(main.querySelector("img")).toBeNull();
    expect(main.textContent).toContain("<img src=x onerror=alert(1)>");
    // Kandidaten-Zeile hat Wort-Eingabe.
    expect(main.querySelectorAll(".aiw-adsync-word").length).toBe(2);
    // Leere Mengen -> keine Abschnitte.
    const main2 = w.document.createElement("div");
    api.renderAdSync(
      main2,
      _data({
        create: [],
        rename: [],
        deactivate_candidates: [],
        reactivate_candidates: [],
        counts: { create: 0, rename: 0 },
      }),
      { doc: w.document }
    );
    expect(main2.querySelectorAll(".aiw-adsync-sect").length).toBe(0);
    expect(main2.querySelector(".aiw-adsync-apply")).toBeNull();
  });

  // ADS07 --------------------------------------------------------------------
  it("ADS07: Deaktivieren nur mit exaktem Wort", () => {
    const w = _ctx();
    const api = w.AIWCockpitAdSync;
    const main = w.document.createElement("div");
    const calls = [];
    const view = api.renderAdSync(main, _data(), {
      doc: w.document,
      onDecide: (b) => calls.push(b),
    });
    void view;
    const row = main.querySelectorAll(".aiw-adsync-cand")[0];
    const input = row.querySelector(".aiw-adsync-word");
    const btn = row.querySelector(".aiw-adsync-deact");

    input.value = "entfernen"; // falsch (klein)
    btn.dispatchEvent(new w.Event("click"));
    expect(calls.length).toBe(0);
    expect(main.querySelector(".aiw-adsync-result").textContent).toContain(
      "Nicht vollzogen"
    );

    input.value = "Entfernen";
    btn.dispatchEvent(new w.Event("click"));
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({
      system_username: "h0weg",
      action: "deactivate",
      confirmation: "Entfernen",
    });
  });

  // ADS08 --------------------------------------------------------------------
  it("ADS08: Abbruch protokollieren mit Notiz", () => {
    const w = _ctx();
    const api = w.AIWCockpitAdSync;
    const main = w.document.createElement("div");
    const calls = [];
    api.renderAdSync(main, _data(), {
      doc: w.document,
      onDecide: (b) => calls.push(b),
    });
    const row = main.querySelectorAll(".aiw-adsync-cand")[0];
    row.querySelector(".aiw-adsync-note").value = "erst Personalstelle fragen";
    row
      .querySelector(".aiw-adsync-abort")
      .dispatchEvent(new w.Event("click"));
    expect(calls.length).toBe(1);
    expect(calls[0]).toEqual({
      system_username: "h0weg",
      action: "abort",
      note: "erst Personalstelle fragen",
    });
  });

  // ADS09 --------------------------------------------------------------------
  it("ADS09: Reaktivieren + Apply-Knopf", () => {
    const w = _ctx();
    const api = w.AIWCockpitAdSync;
    const main = w.document.createElement("div");
    const decided = [];
    let applied = 0;
    api.renderAdSync(main, _data(), {
      doc: w.document,
      onDecide: (b) => decided.push(b),
      onApply: () => {
        applied += 1;
      },
    });
    // Reaktivieren (2. Kandidaten-Zeile).
    const row = main.querySelectorAll(".aiw-adsync-cand")[1];
    row.querySelector(".aiw-adsync-word").value = "Reaktivieren";
    row
      .querySelector(".aiw-adsync-react")
      .dispatchEvent(new w.Event("click"));
    expect(decided.length).toBe(1);
    expect(decided[0]).toEqual({
      system_username: "h0alt",
      action: "reactivate",
      confirmation: "Reaktivieren",
      display_name_ad: "KHKin Zurueck",
    });
    // Apply-Knopf: ruft onApply und sperrt sich (Doppelklick-Schutz).
    const applyBtn = main.querySelector(".aiw-adsync-apply");
    applyBtn.dispatchEvent(new w.Event("click"));
    expect(applied).toBe(1);
    expect(applyBtn.disabled).toBe(true);
  });
});
