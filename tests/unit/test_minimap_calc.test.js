/**
 * test_minimap_calc.test.js
 * Unit-Tests: MinimapModule — Proportionale Positionsberechnung
 * Baustelle 3 · §16.1 Bauplan · §9 Bauplan
 * Version: 0.1.0 · Build: 001 · 2026-04-13
 */

import { describe, it, expect } from "vitest";

/**
 * Die Positionsberechnung aus MinimapModule ist eine reine Funktion:
 *   pct = (element.top + scrollY) / scrollHeight * 100
 * Sie wird hier direkt als pure JS-Funktion getestet.
 */
function minimapPosition(elementTop, scrollY, scrollHeight) {
  if (!scrollHeight || scrollHeight <= 0) return 0;
  var pct = ((elementTop + scrollY) / scrollHeight) * 100;
  return Math.max(0, Math.min(99, pct));
}

describe("MinimapModule — Positionsberechnung", () => {
  it("Element ganz oben → Position ~0%", () => {
    expect(minimapPosition(0, 0, 1000)).toBeCloseTo(0);
  });

  it("Element in der Mitte → Position ~50%", () => {
    expect(minimapPosition(500, 0, 1000)).toBeCloseTo(50);
  });

  it("Element mit Scroll-Offset → Position korrekt berechnet", () => {
    // Element bei y=200, Scroll=300, Höhe=1000 → (200+300)/1000 = 50%
    expect(minimapPosition(200, 300, 1000)).toBeCloseTo(50);
  });

  it("Wert niemals > 99% (Clamp oben)", () => {
    expect(minimapPosition(2000, 0, 1000)).toBe(99);
  });

  it("Wert niemals < 0% (Clamp unten)", () => {
    expect(minimapPosition(-100, 0, 1000)).toBe(0);
  });

  it("scrollHeight=0 → kein Division-by-Zero-Fehler, gibt 0 zurück", () => {
    expect(minimapPosition(500, 0, 0)).toBe(0);
  });

  it("Element am Ende der Seite → Position nahe 99%", () => {
    // 990/1000 = 99% → wird auf 99 geclampt
    expect(minimapPosition(990, 0, 1000)).toBe(99);
  });

  it("Verschiedene Seitenhöhen — Proportionalität gewahrt", () => {
    const p1 = minimapPosition(100, 0, 1000);  // 10%
    const p2 = minimapPosition(200, 0, 2000);  // 10%
    expect(p1).toBeCloseTo(p2);
  });
});
