/**
 * test_annotation_store.test.js
 * Unit-Tests: AnnotationStoreModule — Serialisierung, stale-Erkennung
 * Baustelle 3 · §16.1 Bauplan · §4 Bauplan
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
      <div id="forensic-toolbar"></div>
      <div id="forensic-viewport">
        <article class="post" id="p200"><div class="postmsg"><p>Testinhalt</p></div></article>
      </div>
    </body></html>`,
    { runScripts: "dangerously", url: "http://localhost" }
  );
  // fetch mocken (kein echter Server)
  dom.window.fetch = vi.fn().mockResolvedValue({
    json: () => Promise.resolve({ status: "ok", id: 99 }),
  });
  // requestAnimationFrame-Stub (nicht in JSDOM)
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.eval(src);
  ft = dom.window.ForensicToolbar;
});

describe("AnnotationRecord — Struktur", () => {
  it("annotations-Map ist initial leer", () => {
    expect(ft.state.get("annotations").size).toBe(0);
  });

  it("State nimmt neue annotations-Map entgegen", () => {
    const m = new dom.window.Map();
    m.set("abc", { localId: "abc", category: "CAT_OTHER", syncState: "pending" });
    ft._setState({ annotations: m });
    expect(ft.state.get("annotations").size).toBe(1);
    // Aufräumen
    ft._setState({ annotations: new dom.window.Map() });
  });
});

describe("VALID_CATEGORIES — Vollständigkeit", () => {
  it("Sechs Kategorien definiert", () => {
    expect(ft.config.CATEGORIES.length).toBe(6);
  });

  it("Alle Kategorien haben id, label, icon, color, key", () => {
    ft.config.CATEGORIES.forEach((cat) => {
      expect(cat.id).toBeTruthy();
      expect(cat.label).toBeTruthy();
      expect(cat.icon).toBeTruthy();
      expect(cat.color).toMatch(/^#[0-9a-f]{6}$/i);
      expect(cat.key).toMatch(/^[1-6]$/);
    });
  });

  it("Kategorie-Schlüssel 1-6 sind eindeutig", () => {
    const keys = ft.config.CATEGORIES.map((c) => c.key);
    const unique = new Set(keys);
    expect(unique.size).toBe(6);
  });
});

describe("Annotation syncState — Übergänge", () => {
  it("_setState mit syncErrorCount erhöht Zähler", () => {
    ft._setState({ syncErrorCount: 0 });
    ft._setState({ syncErrorCount: ft.state.get("syncErrorCount") + 1 });
    expect(ft.state.get("syncErrorCount")).toBe(1);
    ft._setState({ syncErrorCount: 0 });
  });
});

describe("Tags — Vokabular", () => {
  it("TAG_VOCABULARY enthält mindestens 15 Einträge", () => {
    expect(ft.config.TAG_VOCABULARY.length).toBeGreaterThanOrEqual(15);
  });

  it("Alle bekannten forensischen Tags vorhanden", () => {
    const required = ["username", "realname", "email", "telefon", "ip", "pgp"];
    required.forEach((tag) => {
      expect(ft.config.TAG_VOCABULARY).toContain(tag);
    });
  });
});

describe("Build 337: isWholePostMark (Post-Marke vs Text-/Übersetzungs-Marke)", () => {
  it("post_id ohne selection -> echte Ganz-Post-Marke", () => {
    expect(ft.config.isWholePostMark({ postId: 705985, selection: null })).toBe(true);
    expect(ft.config.isWholePostMark({ postId: 705985 })).toBe(true);
  });
  it("post_id MIT selection (Übersetzungs-Marke) -> KEINE Post-Marke", () => {
    expect(ft.config.isWholePostMark({
      postId: 705985,
      selection: { target: "translation", charStart: 1, charEnd: 5 }
    })).toBe(false);
  });
  it("ohne post_id / null -> keine Post-Marke", () => {
    expect(ft.config.isWholePostMark({ postId: null, selection: null })).toBe(false);
    expect(ft.config.isWholePostMark(null)).toBe(false);
  });
});
