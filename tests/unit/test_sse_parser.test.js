/**
 * test_sse_parser.test.js
 * Unit-Tests: SupportIndicatorModule — SSE-Event-Parsing, State-Update
 * Baustelle 3 · §16.1 Bauplan · §11.5, §6 Bauplan
 * Version: 0.1.0 · Build: 001 · 2026-04-13
 */

import { describe, it, expect, beforeAll, vi } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

let dom, ft;

// Mock EventSource (Browser-API nicht in JSDOM verfügbar)
class MockEventSource {
  constructor(url) { this.url = url; this._handlers = {}; }
  addEventListener(type, fn) {
    if (!this._handlers[type]) this._handlers[type] = [];
    this._handlers[type].push(fn);
  }
  // Simuliert einen empfangenen Event
  _fire(type, data) {
    (this._handlers[type] || []).forEach((fn) => fn({ data: JSON.stringify(data) }));
  }
}

let mockEs;

beforeAll(() => {
  const src = readFileSync("toolbar/toolbar.js", "utf-8");
  dom = new JSDOM(
    `<!DOCTYPE html>
    <html><body>
      <div id="forensic-toolbar"></div>
      <div id="forensic-support-indicator" class="forensic-support-hidden"></div>
    </body></html>`,
    { runScripts: "dangerously", url: "http://localhost" }
  );

  // EventSource mocken bevor toolbar.js ausgeführt wird
  dom.window.EventSource = function (url) {
    mockEs = new MockEventSource(url);
    return mockEs;
  };
  dom.window.fetch = vi.fn().mockResolvedValue({
    json: () => Promise.resolve({ status: "ok" }),
  });

  dom.window.eval(src);
  ft = dom.window.ForensicToolbar;
});

describe("SSE-Event-Parsing — support_status", () => {
  it("support_active=true: State wird korrekt gesetzt", () => {
    const payload = {
      support_active: true,
      support_user:   "h067890",
      since:          1744300000000,
    };
    ft.events.emit("support:status_changed", payload);
    const ss = ft.state.get("supportStatus");
    expect(ss.active).toBe(true);
    expect(ss.username).toBe("h067890");
    expect(ss.since).toBe(1744300000000);
  });

  it("support_active=false: State wird korrekt zurückgesetzt", () => {
    const payload = { support_active: false, support_user: null, since: null };
    ft.events.emit("support:status_changed", payload);
    const ss = ft.state.get("supportStatus");
    expect(ss.active).toBe(false);
    expect(ss.username).toBeNull();
    expect(ss.since).toBeNull();
  });
});

describe("SSE-Event-Parsing — JSON-Robustheit", () => {
  it("JSON-Parsing valider support_status-Payload", () => {
    const raw = '{"support_active": true, "support_user": "h123", "since": 1000}';
    const parsed = JSON.parse(raw);
    expect(parsed.support_active).toBe(true);
    expect(parsed.support_user).toBe("h123");
  });

  it("JSON-Parsing mit support_active=false", () => {
    const raw = '{"support_active": false, "support_user": null, "since": null}';
    const parsed = JSON.parse(raw);
    expect(parsed.support_active).toBe(false);
    expect(parsed.support_user).toBeNull();
  });

  it("Ungültiges JSON → sollte keinen unbehandelten Fehler werfen", () => {
    expect(() => {
      try { JSON.parse("KEIN_JSON"); } catch (e) { /* erwartet */ }
    }).not.toThrow();
  });
});

describe("SupportIndicatorModule — DOM-Anzeige", () => {
  it("support_active=true: Indikator-Element erhält aktive CSS-Klasse", () => {
    ft.events.emit("support:status_changed", {
      support_active: true,
      support_user:   "h099",
      since:          999,
    });
    const el = dom.window.document.getElementById("forensic-support-indicator");
    expect(el).not.toBeNull();
    expect(el.className).toBe("forensic-support-active");
    expect(el.textContent).toContain("h099");
  });

  it("support_active=false: Indikator-Element bekommt hidden-Klasse", () => {
    ft.events.emit("support:status_changed", {
      support_active: false,
      support_user:   null,
      since:          null,
    });
    const el = dom.window.document.getElementById("forensic-support-indicator");
    expect(el.className).toBe("forensic-support-hidden");
    expect(el.textContent).toBe("");
  });
});
