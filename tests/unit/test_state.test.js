/**
 * test_state.test.js
 * Unit-Tests: ForensicToolbar.state — Mutationen, Unveränderlichkeit von außen
 * Baustelle 3 · §16.1 Bauplan · §3 Bauplan
 * Version: 0.1.0 · Build: 001 · 2026-04-13
 */

import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

let dom, ft;
beforeAll(() => {
  const src = readFileSync("toolbar/toolbar.js", "utf-8");
  dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(src);
  ft = dom.window.ForensicToolbar;
});

describe("ForensicToolbar.state — Lesezugriff", () => {
  it("state.get liefert initialen viewMode 'enhanced'", () => {
    expect(ft.state.get("viewMode")).toBe("enhanced");
  });

  it("state.get liefert initialen activeCategory null", () => {
    expect(ft.state.get("activeCategory")).toBeNull();
  });

  it("state.getAll gibt Objekt zurück", () => {
    const s = ft.state.getAll();
    expect(typeof s).toBe("object");
    expect("currentUrl" in s).toBe(true);
  });
});

describe("ForensicToolbar._setState — Mutation", () => {
  it("_setState aktualisiert Wert korrekt", () => {
    ft._setState({ viewMode: "original" });
    expect(ft.state.get("viewMode")).toBe("original");
    // Aufräumen
    ft._setState({ viewMode: "enhanced" });
  });

  it("_setState emittiert state:changed Event", () => {
    let received = null;
    ft.events.on("state:changed", (data) => { received = data; });
    ft._setState({ activeCategory: "CAT_PERSON" });
    expect(received).not.toBeNull();
    expect(received.activeCategory).toBe("CAT_PERSON");
    ft._setState({ activeCategory: null });
  });

  it("state.getAll gibt flache Kopie zurück (externes Schreiben wirkt nicht)", () => {
    const copy = ft.state.getAll();
    copy.viewMode = "MANIPULATED";
    // Originalzustand unverändert
    expect(ft.state.get("viewMode")).toBe("enhanced");
  });
});

describe("ForensicToolbar.events — Pub/Sub", () => {
  it("on/emit: Listener wird aufgerufen", () => {
    let count = 0;
    ft.events.on("test:event", () => { count++; });
    ft.events.emit("test:event");
    expect(count).toBe(1);
  });

  it("off: Listener wird entfernt", () => {
    let count = 0;
    const fn = () => { count++; };
    ft.events.on("test:off", fn);
    ft.events.emit("test:off");
    ft.events.off("test:off", fn);
    ft.events.emit("test:off");
    expect(count).toBe(1);
  });

  it("emit ohne Listener wirft keinen Fehler", () => {
    expect(() => ft.events.emit("nonexistent:event")).not.toThrow();
  });
});
