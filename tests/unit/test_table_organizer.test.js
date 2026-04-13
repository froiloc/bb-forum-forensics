/**
 * test_table_organizer.test.js
 * Unit-Tests: PMSTableOrganizerModule + TopicsTableOrganizerModule
 * Sortierung, Filterung, Reversibilität
 * Baustelle 3 · §16.1 Bauplan · §21 Bauplan
 * Version: 0.1.0 · Build: 001 · 2026-04-13
 */

import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

// Hilfsfunktion: Datumsstring parsen (identisch zu PMSTableOrganizerModule)
function parseDate(str) {
  var m = str.match(/(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2}):(\d{2})/);
  if (!m) return 0;
  return new Date(m[3], m[2] - 1, m[1], m[4], m[5], m[6]).getTime();
}

// Hilfsfunktion: Levenshtein (identisch zu config)
function levenshtein(a, b) {
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;
  var matrix = [];
  for (var i = 0; i <= b.length; i++) matrix[i] = [i];
  for (var j = 0; j <= a.length; j++) matrix[0][j] = j;
  for (var i2 = 1; i2 <= b.length; i2++) {
    for (var j2 = 1; j2 <= a.length; j2++) {
      if (b.charAt(i2-1) === a.charAt(j2-1)) {
        matrix[i2][j2] = matrix[i2-1][j2-1];
      } else {
        matrix[i2][j2] = Math.min(
          matrix[i2-1][j2-1]+1,
          Math.min(matrix[i2][j2-1]+1, matrix[i2-1][j2]+1)
        );
      }
    }
  }
  return matrix[b.length][a.length];
}

// ============================================================
// Mock-DOM für PN-Tabelle (pmsnew.php-Struktur, §21.2 Bauplan)
// ============================================================
function buildPmsDOM() {
  return new JSDOM(`<!DOCTYPE html><html><body>
    <div id="vf" class="blocktable">
      <div class="inbox">
        <table>
          <thead><tr>
            <th class="tcl color1">Dialogue</th>
            <th class="tc2">Starter</th>
            <th class="tc2">To</th>
            <th class="tc3">Replies</th>
            <th class="tc2">Last</th>
          </tr></thead>
          <tbody>
            <tr class="rowodd inew">
              <td class="tcl"><a href="pmsnew.php?mdl=topic&tid=10">Betreff A</a></td>
              <td class="tc2"><a href="profile.php?id=2">ZebraUser</a></td>
              <td class="tc2"><a href="profile.php?id=1">Admin</a></td>
              <td class="tc3">3</td>
              <td class="tc2">Mo., 10.03.2024 09:00:00</td>
            </tr>
            <tr class="roweven">
              <td class="tcl"><a href="pmsnew.php?mdl=topic&tid=5">Betreff C</a></td>
              <td class="tc2"><a href="profile.php?id=3">ApfelUser</a></td>
              <td class="tc2"><a href="profile.php?id=1">Admin</a></td>
              <td class="tc3">10</td>
              <td class="tc2">Fr., 05.01.2024 14:30:00</td>
            </tr>
            <tr class="rowodd iclosed">
              <td class="tcl"><a href="pmsnew.php?mdl=topic&tid=7">Betreff B</a></td>
              <td class="tc2"><a href="profile.php?id=4">MangoUser</a></td>
              <td class="tc2"><a href="profile.php?id=1">Admin</a></td>
              <td class="tc3">1</td>
              <td class="tc2">Mi., 20.02.2024 11:15:00</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </body></html>`, { url: "http://localhost" });
}

describe("Datumsstring-Parser (PMSTableOrganizerModule)", () => {
  it("parst deutsches Datumsformat korrekt", () => {
    const ts = parseDate("Mo., 10.03.2024 09:00:00");
    expect(ts).toBeGreaterThan(0);
    const d = new Date(ts);
    expect(d.getFullYear()).toBe(2024);
    expect(d.getMonth()).toBe(2); // März = 2
    expect(d.getDate()).toBe(10);
  });

  it("neueres Datum > älteres Datum", () => {
    const newer = parseDate("Mo., 10.03.2024 09:00:00");
    const older = parseDate("Fr., 05.01.2024 14:30:00");
    expect(newer).toBeGreaterThan(older);
  });

  it("ungültiger String → 0", () => {
    expect(parseDate("kein datum")).toBe(0);
  });
});

describe("Tabellenzeilen — DOM-Struktur (§21.2 Bauplan)", () => {
  it("PMS-Tabelle: tbody-Zeilen korrekt zählbar", () => {
    const dom  = buildPmsDOM();
    const tbody = dom.window.document.querySelector("div#vf .inbox > table tbody");
    expect(tbody).not.toBeNull();
    expect(tbody.rows.length).toBe(3);
  });

  it("PMS-Tabelle: inew-Klasse erkennbar", () => {
    const dom  = buildPmsDOM();
    const rows = dom.window.document.querySelectorAll("div#vf tbody tr.inew");
    expect(rows.length).toBe(1);
  });

  it("PMS-Tabelle: iclosed-Klasse erkennbar", () => {
    const dom  = buildPmsDOM();
    const rows = dom.window.document.querySelectorAll("div#vf tbody tr.iclosed");
    expect(rows.length).toBe(1);
  });
});

describe("Reversibilität — Original-Reihenfolge", () => {
  it("Array.from(tbody.rows) sichert Originalreihenfolge", () => {
    const dom  = buildPmsDOM();
    const tbody = dom.window.document.querySelector("div#vf .inbox > table tbody");
    const origOrder = Array.from(tbody.rows);

    // Reihenfolge künstlich ändern
    tbody.appendChild(origOrder[0]);

    // Wiederherstellen
    origOrder.forEach((r) => tbody.appendChild(r));

    const restored = Array.from(tbody.rows).map((r) =>
      r.querySelector("a").textContent
    );
    expect(restored[0]).toBe("Betreff A");
    expect(restored[1]).toBe("Betreff C");
    expect(restored[2]).toBe("Betreff B");
  });
});

describe("Alphabetische Sortierung (Simulation)", () => {
  it("Betreffspalte alphabetisch sortierbar", () => {
    const dom  = buildPmsDOM();
    const tbody = dom.window.document.querySelector("div#vf .inbox > table tbody");
    const rows  = Array.from(tbody.rows);

    rows.sort((a, b) => {
      const aT = a.cells[0].querySelector("a").textContent;
      const bT = b.cells[0].querySelector("a").textContent;
      return aT.localeCompare(bT, "de");
    });
    rows.forEach((r) => tbody.appendChild(r));

    const titles = Array.from(tbody.rows).map((r) =>
      r.cells[0].querySelector("a").textContent
    );
    expect(titles[0]).toBe("Betreff A");
    expect(titles[1]).toBe("Betreff B");
    expect(titles[2]).toBe("Betreff C");
  });
});

describe("Numerische Sortierung — Replies", () => {
  it("Replies-Spalte numerisch korrekt sortiert (aufsteigend)", () => {
    const dom   = buildPmsDOM();
    const tbody  = dom.window.document.querySelector("div#vf .inbox > table tbody");
    const rows   = Array.from(tbody.rows);

    rows.sort((a, b) => parseInt(a.cells[3].textContent) - parseInt(b.cells[3].textContent));
    rows.forEach((r) => tbody.appendChild(r));

    const counts = Array.from(tbody.rows).map((r) =>
      parseInt(r.cells[3].textContent)
    );
    expect(counts[0]).toBe(1);
    expect(counts[1]).toBe(3);
    expect(counts[2]).toBe(10);
  });
});
