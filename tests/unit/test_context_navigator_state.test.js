/**
 * test_context_navigator_state.test.js
 * Unit-Tests: ContextNavigatorModule — State-Erweiterung, Event-Routing,
 *             Cache-Invalidierung
 * Bauplan: Baustelle 3 Ergänzung Kontext-Navigator v0.6, §3 + §12 Phase KN-1
 * Version: 0.1.0 · Build: 066 · 2026-04-26
 * Klassifikation: VERTRAULICH — NUR FÜR DEN DIENSTGEBRAUCH
 */

import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

let dom, ft, nav;

beforeAll(() => {
  const src = readFileSync("toolbar/toolbar.js", "utf-8");
  dom = new JSDOM(
    "<!DOCTYPE html><html><body>" +
    "<div id=\"forensic-toolbar\"></div>" +
    "<div id=\"forensic-viewport\"></div>" +
    "</body></html>",
    { runScripts: "dangerously", url: "http://aiw.local/forum/index.php" }
  );
  // Stubs — JSDOM unterstützt kein fetch/rAF
  dom.window.fetch = () =>
    Promise.resolve({ ok: true, json: () => ({ status: "ok", version: "test" }) });
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.EventSource = function () {
    return { addEventListener: () => {}, close: () => {} };
  };
  dom.window.eval(src);
  ft  = dom.window.ForensicToolbar;
  nav = dom.window.ForensicToolbar.navigator;
});

// ---------------------------------------------------------------------------
// State-Erweiterung (§3 Bauplan Kontext-Navigator)
// ---------------------------------------------------------------------------
describe("State — neue Felder (Build 066, §3 Bauplan KN)", () => {
  it("contextDropdownOpen ist initial false", () => {
    expect(ft.state.get("contextDropdownOpen")).toBe(false);
  });

  it("contextModalOpen ist initial false", () => {
    expect(ft.state.get("contextModalOpen")).toBe(false);
  });

  it("contextSearchResults ist initial leeres Array", () => {
    const r = ft.state.get("contextSearchResults");
    expect(Array.isArray(r)).toBe(true);
    expect(r.length).toBe(0);
  });

  it("bestehende State-Felder unverändert vorhanden (Regressions-Check)", () => {
    const s = ft.state.getAll();
    const required = [
      "currentUrl", "scrapeContext", "fetchFailed", "inScope",
      "activeCategory", "annotations", "viewMode", "traceElements",
      "supportStatus", "investigatorUsername", "forumHostname",
    ];
    required.forEach((key) => {
      expect(key in s).toBe(true);
    });
  });
});

// ---------------------------------------------------------------------------
// ForensicToolbar.navigator — öffentliche API
// ---------------------------------------------------------------------------
describe("ForensicToolbar.navigator — öffentliche API", () => {
  it("navigator ist definiert und exponiert getPages + invalidateCache", () => {
    expect(nav).toBeDefined();
    expect(typeof nav.getPages).toBe("function");
    expect(typeof nav.invalidateCache).toBe("function");
  });
});

// ---------------------------------------------------------------------------
// Cache-Verwaltung
// ---------------------------------------------------------------------------
describe("ContextNavigatorModule — Cache-Verwaltung", () => {
  beforeEach(() => {
    // Cache vor jedem Test zurücksetzen
    nav.invalidateCache();
  });

  it("getPages() liefert ein Array zurück (Phase KN-2: Mock-Daten)", async () => {
    const pages = await nav.getPages();
    expect(Array.isArray(pages)).toBe(true);
    expect(pages.length).toBeGreaterThan(0);
  });

  it("getPages() liefert PageSummaryRecords mit Pflichtfeldern", async () => {
    const pages = await nav.getPages();
    const required = [
      "url", "title", "scrapeContext", "fetchFailed",
      "progressPercent", "traceCountTotal", "annotationsTotal",
    ];
    pages.forEach((p) => {
      required.forEach((key) => {
        expect(key in p).toBe(true);
      });
    });
  });

  it("getPages() setzt contextSearchResults im State", async () => {
    await nav.getPages();
    const results = ft.state.get("contextSearchResults");
    expect(Array.isArray(results)).toBe(true);
    expect(results.length).toBeGreaterThan(0);
  });

  it("invalidateCache() leert contextSearchResults im State", () => {
    nav.invalidateCache();
    const results = ft.state.get("contextSearchResults");
    expect(results).toEqual([]);
  });

  it("getPages() zweiter Aufruf liefert gecachtes Ergebnis (kein neues Promise)", async () => {
    const first  = await nav.getPages();
    const second = await nav.getPages();
    // Identische Referenz — Cache-Hit
    expect(first).toBe(second);
  });

  it("invalidateCache() + getPages() lädt neu (kein Cache-Hit nach Invalidierung)", async () => {
    const first = await nav.getPages();
    nav.invalidateCache();
    const second = await nav.getPages();
    // Neues Array-Objekt nach Invalidierung
    expect(first).not.toBe(second);
    // Inhalt aber gleich (Mock-Daten unverändert)
    expect(first.length).toBe(second.length);
  });
});

// ---------------------------------------------------------------------------
// Event-Routing: page:loaded → Cache-Invalidierung
// ---------------------------------------------------------------------------
describe("ContextNavigatorModule — Event-Routing", () => {
  it("page:loaded emittiert navigator:cache_invalidated", () => {
    let received = false;
    ft.events.on("navigator:cache_invalidated", () => { received = true; });
    ft.events.emit("page:loaded", { scrapeContext: "user", html: "" });
    expect(received).toBe(true);
  });

  it("page:loaded invalidiert den Cache", async () => {
    // Cache vorladen
    await nav.getPages();
    const before = ft.state.get("contextSearchResults");
    expect(before.length).toBeGreaterThan(0);

    // Navigation simulieren
    ft.events.emit("page:loaded", { scrapeContext: "user", html: "" });

    // Cache muss leer sein
    const after = ft.state.get("contextSearchResults");
    expect(after).toEqual([]);
  });

  it("navigator:page_selected mit gültiger URL emittiert kein Fehler-Event", () => {
    let errorFired = false;
    ft.events.on("navigation:error", () => { errorFired = true; });
    // Minimal-Stub: navigator.loadPage ist in Tests nicht vollständig verfügbar,
    // aber das Event darf keinen Fehler werfen
    expect(() => {
      ft.events.emit("navigator:page_selected", { url: "/forum/viewtopic.php?id=7" });
    }).not.toThrow();
    expect(errorFired).toBe(false);
  });

  it("navigator:modal_open setzt contextModalOpen=true im State", () => {
    ft.events.emit("navigator:modal_open");
    expect(ft.state.get("contextModalOpen")).toBe(true);
    // Cleanup
    ft._setState({ contextModalOpen: false });
  });
});

// ---------------------------------------------------------------------------
// PageSummaryRecord-Schema-Validierung (Bauplan KN §4)
// ---------------------------------------------------------------------------
describe("PageSummaryRecord — Schema", () => {
  it("progressPercent liegt im Bereich 0–100", async () => {
    nav.invalidateCache();
    const pages = await nav.getPages();
    pages.forEach((p) => {
      expect(p.progressPercent).toBeGreaterThanOrEqual(0);
      expect(p.progressPercent).toBeLessThanOrEqual(100);
    });
  });

  it("scrapeContext ist 'user', 'investigator' oder beginnt mit 'actor:'", async () => {
    nav.invalidateCache();
    const pages = await nav.getPages();
    pages.forEach((p) => {
      const valid =
        p.scrapeContext === "user" ||
        p.scrapeContext === "investigator" ||
        (typeof p.scrapeContext === "string" && p.scrapeContext.startsWith("actor:"));
      expect(valid).toBe(true);
    });
  });

  it("tagList ist Array", async () => {
    nav.invalidateCache();
    const pages = await nav.getPages();
    pages.forEach((p) => {
      expect(Array.isArray(p.tagList)).toBe(true);
    });
  });

  it("fetchFailed ist Boolean", async () => {
    nav.invalidateCache();
    const pages = await nav.getPages();
    pages.forEach((p) => {
      expect(typeof p.fetchFailed).toBe("boolean");
    });
  });
});
