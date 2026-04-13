/**
 * test_levenshtein.test.js
 * Unit-Tests: Levenshtein-Funktion und Tag-Vorschlagsmechanismus
 * Baustelle 3 · §16.1 Bauplan · §19.2 Bauplan
 * Version: 0.1.0 · Build: 001 · 2026-04-13
 */

import { describe, it, expect, beforeAll } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

// toolbar.js laden und im JSDOM-Kontext auswerten
let ForensicToolbar;
beforeAll(() => {
  const src = readFileSync("toolbar/toolbar.js", "utf-8");
  const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.eval(src);
  ForensicToolbar = dom.window.ForensicToolbar;
});

describe("ForensicToolbar.config.levenshtein", () => {
  it("identische Strings → Distanz 0", () => {
    expect(ForensicToolbar.config.levenshtein("email", "email")).toBe(0);
  });

  it("leerer String → Länge des anderen Strings", () => {
    expect(ForensicToolbar.config.levenshtein("", "abc")).toBe(3);
    expect(ForensicToolbar.config.levenshtein("abc", "")).toBe(3);
  });

  it("eine Einfügung → Distanz 1", () => {
    // "usrname" → "username": 1 Einfügung ('e' nach 'u')
    expect(ForensicToolbar.config.levenshtein("usrname", "username")).toBe(1);
    // "emal" → "email": 1 Einfügung ('i')
    expect(ForensicToolbar.config.levenshtein("emal", "email")).toBe(1);
  });

  it("Transposition (Standard-Levenshtein) → Distanz 2", () => {
    // Standard-Levenshtein zählt Transposition als 2 Operationen (kein Damerau).
    // "emali" → "email": Vertauschung l↔i = löschen+einfügen = Distanz 2.
    expect(ForensicToolbar.config.levenshtein("emali", "email")).toBe(2);
    // "realnme" → "realname": 1 Einfügung ('a') → tatsächlich Distanz 1
    expect(ForensicToolbar.config.levenshtein("realnme", "realname")).toBe(1);
  });

  it("vollständig verschieden (kurz) → Distanz = Max-Länge", () => {
    expect(ForensicToolbar.config.levenshtein("abc", "xyz")).toBe(3);
  });
});

describe("ForensicToolbar.config.suggestTag", () => {
  it("exakter Treffer → Rückgabe ohne Umweg", () => {
    expect(ForensicToolbar.config.suggestTag("email", [])).toBe("email");
  });

  it("Distanz 1 → Vorschlag zurückgegeben", () => {
    const sug = ForensicToolbar.config.suggestTag("emali", []);
    expect(sug).toBe("email");
  });

  it("Distanz 2 → Vorschlag zurückgegeben", () => {
    const sug = ForensicToolbar.config.suggestTag("realnme", []);
    expect(sug).toBe("realname");
  });

  it("Distanz > 2 → null zurückgegeben", () => {
    expect(ForensicToolbar.config.suggestTag("xxxxxxxx", [])).toBeNull();
  });

  it("Eingabe zu lang → null zurückgegeben", () => {
    const lang = "a".repeat(60);
    expect(ForensicToolbar.config.suggestTag(lang, [])).toBeNull();
  });

  it("leere Eingabe → null zurückgegeben", () => {
    expect(ForensicToolbar.config.suggestTag("", [])).toBeNull();
  });

  it("custom knownTags werden einbezogen", () => {
    const sug = ForensicToolbar.config.suggestTag("btcoin", ["bitcoin"]);
    expect(sug).toBe("bitcoin");
  });
});
