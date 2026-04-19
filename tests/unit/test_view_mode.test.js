/**
 * test_view_mode.test.js
 * Unit-Tests: ViewModeModule — Zustandswechsel, Reversibilität
 * Baustelle 3 · §16.1 Bauplan · §21.1 Bauplan
 * Version: 0.1.0 · Build: 001 · 2026-04-13
 */

import { describe, it, expect, beforeAll, vi } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

let dom, ft;

beforeAll(() => {
  const src = readFileSync("toolbar/toolbar.js", "utf-8");
  dom = new JSDOM(
    `<!DOCTYPE html>
    <html><body>
      <div id="forensic-toolbar">
        <button id="forensic-btn-viewmode" data-viewmode="enhanced">⊞ Angepasst</button>
      </div>
      <div id="forensic-minimap"></div>
      <div id="forensic-viewport">
        <article class="post" id="p300" data-forensic-cat="CAT_PERSON"
          style="border-left: 5px solid #f5c842">Postinhalt</article>
      </div>
    </body></html>`,
    { runScripts: "dangerously", url: "http://localhost" }
  );
  // Mocks
  dom.window.fetch = vi.fn().mockResolvedValue({
    json: () => Promise.resolve({ status: "ok", annotations: [] }),
  });
  // requestAnimationFrame-Stub (nicht in JSDOM)
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.eval(src);
  ft = dom.window.ForensicToolbar;
});

describe("ViewModeModule — Initialer Zustand", () => {
  it("Initialer viewMode ist 'enhanced'", () => {
    expect(ft.state.get("viewMode")).toBe("enhanced");
  });
});

describe("ViewModeModule — Wechsel über _setState", () => {
  it("_setState('original') setzt viewMode korrekt", () => {
    ft._setState({ viewMode: "original" });
    expect(ft.state.get("viewMode")).toBe("original");
  });

  it("_setState('enhanced') setzt viewMode korrekt", () => {
    ft._setState({ viewMode: "enhanced" });
    expect(ft.state.get("viewMode")).toBe("enhanced");
  });
});

describe("ViewModeModule — Event-Emittierung", () => {
  it("viewmode:original-Event wird emittiert", () => {
    let received = false;
    ft.events.on("viewmode:original", () => { received = true; });
    ft.events.emit("viewmode:original");
    expect(received).toBe(true);
  });

  it("viewmode:enhanced-Event wird emittiert", () => {
    let received = false;
    ft.events.on("viewmode:enhanced", () => { received = true; });
    ft.events.emit("viewmode:enhanced");
    expect(received).toBe(true);
  });
});

describe("ViewModeModule — Invarianten (§21.1 Bauplan)", () => {
  it("viewMode ist entweder 'enhanced' oder 'original'", () => {
    const valid = ["enhanced", "original"];
    expect(valid).toContain(ft.state.get("viewMode"));
  });

  it("Mehrfache Wechsel hintereinander ohne Fehler", () => {
    expect(() => {
      ft._setState({ viewMode: "original" });
      ft.events.emit("viewmode:original");
      ft._setState({ viewMode: "enhanced" });
      ft.events.emit("viewmode:enhanced");
      ft._setState({ viewMode: "original" });
      ft.events.emit("viewmode:original");
      ft._setState({ viewMode: "enhanced" });
      ft.events.emit("viewmode:enhanced");
    }).not.toThrow();
  });
});
