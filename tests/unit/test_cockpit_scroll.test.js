/**
 * tests/unit/test_cockpit_scroll.test.js
 * IT-Forensisches Ermittlungswerkzeug — Baustelle 7
 * =============================================================================
 * Testsuite fuer Build 566: getrennte Bildlaufflaechen (Ticket fbfc418c).
 *
 * SC01 — sichtNachOben setzt den Bildlauf der Sicht auf 0 und vertraegt ein
 *        fehlendes Element (kein Absturz mitten im Sichtwechsel).
 * SC02 — navEintragZeigen holt den AKTIVEN Eintrag ins Bild, benutzt dabei
 *        block:'nearest' (ein sichtbarer Eintrag darf nicht zappeln).
 * SC03 — ohne aktiven Eintrag passiert nichts.
 * SC04 — kennt die Umgebung die scrollIntoView-Optionen nicht, wird ohne
 *        Optionen gesprungen statt eine Ausnahme zu werfen.
 * SC05 — das Stylesheet trennt die Flaechen tatsaechlich: eigener Bildlauf
 *        fuer Leiste UND Sicht, und 'min-height: 0' am Rahmen. Ohne diese
 *        eine Zeile griffe keine der overflow-Regeln.
 * SC06 — der Druck nimmt die feste Hoehe zurueck. Ohne das braeche ein
 *        Ausdruck nach einer Seite ab, weil der Rest im Bildlauf steckt.
 *
 * Version: v0.8.566 · Build: 566 · 2026-07-29
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

const _js = readFileSync("management/server/static/cockpit.js", "utf-8");
const _css = readFileSync("management/server/static/cockpit.css", "utf-8");

function _api() {
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously", url: "http://localhost",
  });
  dom.window.eval(_js);
  return { win: dom.window, api: dom.window.AIWCockpit };
}

describe("Getrennte Bildlaufflaechen (Build 566)", () => {
  // SC01 --------------------------------------------------------------------
  it("SC01: sichtNachOben setzt den Bildlauf zurueck", () => {
    const { win, api } = _api();
    const main = win.document.createElement("div");
    main.scrollTop = 240;
    win.document.body.appendChild(main);

    api.sichtNachOben(main);
    expect(main.scrollTop).toBe(0);

    // Ein fehlendes Element darf den Sichtwechsel nicht abbrechen.
    expect(() => api.sichtNachOben(null)).not.toThrow();
    expect(() => api.sichtNachOben(undefined)).not.toThrow();
  });

  // SC02 --------------------------------------------------------------------
  it("SC02: navEintragZeigen holt den aktiven Eintrag ins Bild", () => {
    const { win, api } = _api();
    const nav = win.document.createElement("nav");
    const a = win.document.createElement("button");
    a.className = "aiw-navitem";
    const b = win.document.createElement("button");
    b.className = "aiw-navitem active";
    nav.appendChild(a);
    nav.appendChild(b);
    win.document.body.appendChild(nav);

    let gerufen = null;
    b.scrollIntoView = (opt) => { gerufen = opt; };
    a.scrollIntoView = () => { throw new Error("falscher Eintrag bewegt"); };

    api.navEintragZeigen(nav);
    // 'nearest' ist der Punkt: ein bereits sichtbarer Eintrag bleibt stehen,
    // die Leiste zappelt bei jedem Sichtwechsel nicht.
    expect(gerufen).toEqual({ block: "nearest" });
  });

  // SC03 --------------------------------------------------------------------
  it("SC03: ohne aktiven Eintrag geschieht nichts", () => {
    const { win, api } = _api();
    const nav = win.document.createElement("nav");
    const a = win.document.createElement("button");
    a.className = "aiw-navitem";
    a.scrollIntoView = () => { throw new Error("darf nicht bewegt werden"); };
    nav.appendChild(a);
    win.document.body.appendChild(nav);

    expect(() => api.navEintragZeigen(nav)).not.toThrow();
    expect(() => api.navEintragZeigen(null)).not.toThrow();
  });

  // SC04 --------------------------------------------------------------------
  it("SC04: alte Umgebung ohne Options-Unterstuetzung springt trotzdem", () => {
    const { win, api } = _api();
    const nav = win.document.createElement("nav");
    const b = win.document.createElement("button");
    b.className = "aiw-navitem active";
    nav.appendChild(b);
    win.document.body.appendChild(nav);

    let ohneOptionen = 0;
    b.scrollIntoView = (opt) => {
      if (opt !== undefined) { throw new TypeError("Optionen unbekannt"); }
      ohneOptionen += 1;
    };
    expect(() => api.navEintragZeigen(nav)).not.toThrow();
    expect(ohneOptionen).toBe(1);
  });

  // SC05 --------------------------------------------------------------------
  it("SC05: das Stylesheet trennt die Flaechen wirklich", () => {
    // Die Regeln sind der eigentliche Pruefgegenstand — die JS-Haelfte allein
    // wuerde das gemeldete Verhalten nicht beheben.
    const rahmen = _css.match(/\.aiw-frame\s*\{[^}]*\}/);
    expect(rahmen).not.toBeNull();
    expect(rahmen[0]).toMatch(/min-height:\s*0/);
    expect(rahmen[0]).toMatch(/flex:\s*1 1 auto/);

    const leiste = _css.match(/nav\.aiw-side\s*\{[^}]*\}/);
    expect(leiste[0]).toMatch(/overflow-y:\s*auto/);

    const sicht = _css.match(/main\.aiw-main\s*\{[^}]*\}/);
    expect(sicht[0]).toMatch(/overflow:\s*auto/);

    // Das Dokument selbst scrollt nicht mehr — sonst waeren es wieder zwei
    // Flaechen zu viel.
    const koerper = _css.match(/\nbody\s*\{[^}]*\}/);
    expect(koerper[0]).toMatch(/overflow:\s*hidden/);
    expect(koerper[0]).toMatch(/flex-direction:\s*column/);
  });

  // SC06 --------------------------------------------------------------------
  it("SC06: der Druck nimmt die feste Hoehe zurueck", () => {
    const druck = _css.match(/@media print\s*\{[\s\S]*?\n\}/);
    expect(druck).not.toBeNull();
    // Ohne diese Ruecknahme braeche der Ausdruck nach einer Seite ab, weil
    // der Rest im nicht gedruckten Bildlauf steckt.
    expect(druck[0]).toMatch(/html,\s*body\s*\{[^}]*height:\s*auto/);
    expect(druck[0]).toMatch(/overflow:\s*visible/);
  });
});
