/**
 * test_translation_module.test.js
 * Unit-Tests: reine Hilfslogik des TranslationModule (Build 329)
 * Baustelle 3 · Bauplan Build 329 §6.2
 *
 * Testet gegen den ECHTEN Code: toolbar.js wird im JSDOM ausgewertet, die
 * pure Logik ist ueber ForensicToolbar.config.translationHelpers freigelegt
 * (Muster analog ForensicToolbar.config.levenshtein). Kein dupliziertes Stub —
 * damit kein "green but dead" (B4-S12).
 *
 * Version: 0.7.329 · Build: 329 · 2026-07-07
 */

import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

let H;
beforeAll(() => {
  const src = readFileSync("toolbar/toolbar.js", "utf-8");
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => ({}) });
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.eval(src);
  H = dom.window.ForensicToolbar.config.translationHelpers;
});

describe("TranslationModule.topicIdFromUrl", () => {
  it("viewtopic mit id -> Zahl", () => {
    expect(H.topicIdFromUrl("/forum/viewtopic.php?id=69192")).toBe(69192);
  });
  it("viewtopic mit id und Seiten-Parameter -> weiterhin die topic_id", () => {
    expect(H.topicIdFromUrl("/forum/viewtopic.php?id=69192&p=2")).toBe(69192);
  });
  it("keine viewtopic-Seite -> null", () => {
    expect(H.topicIdFromUrl("/forum/viewforum.php?id=20")).toBe(null);
  });
  it("leer/null -> null", () => {
    expect(H.topicIdFromUrl("")).toBe(null);
    expect(H.topicIdFromUrl(null)).toBe(null);
  });
});

describe("TranslationModule.postIdFromContainerId", () => {
  it("p<n> -> Zahl", () => {
    expect(H.postIdFromContainerId("p706037")).toBe(706037);
  });
  it("Nicht-Post-Ids -> null", () => {
    expect(H.postIdFromContainerId("page-body")).toBe(null);
    expect(H.postIdFromContainerId("_vt_abc123")).toBe(null);
    expect(H.postIdFromContainerId("pmsnew")).toBe(null);
    expect(H.postIdFromContainerId("")).toBe(null);
  });
});

describe("TranslationModule.isTranslated", () => {
  it("Set-Mitgliedschaft", () => {
    const s = new Set([1, 2, 3]);
    expect(H.isTranslated(2, s)).toBe(true);
    expect(H.isTranslated(9, s)).toBe(false);
  });
  it("null-sicher (Set noch nicht geladen)", () => {
    expect(H.isTranslated(1, null)).toBe(false);
  });
});
