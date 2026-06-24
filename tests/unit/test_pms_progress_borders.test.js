/**
 * test_pms_progress_borders.test.js
 * Unit-Tests: PMSTableOrganizerModule._applyProgressBorders() (Build 302)
 *
 * Prüft die Kernlogik des Fortschrittsrahmens auf PN-Dialog-Zeilen (pmsnew.php):
 *   - tid-Extraktion aus dem Link (robust gegen &amp;-Kodierung)
 *   - Bildung der kanonischen Dialog-URL /forum/pmsnew.php?mdl=topic&tid=<tid>
 *   - normalisierter URL-Match gegen die getPages()-Daten
 *   - Setzen von --trace-progress + Klasse .has_trace_progress am <tr>
 *   - Dialoge ohne Daten → pct=0 (roter Rahmen, einheitliches Schema)
 *
 * Das Modul ist als IIFE privat gekapselt und exportiert _applyProgressBorders
 * nicht. Daher wird die Kernlogik hier — analog zu test_table_organizer.test.js
 * (parseDate/levenshtein) — eigenständig im jsdom-DOM nachgebildet und gegen
 * dieselben Invarianten geprüft.
 *
 * Baustelle 3 · Beleg: Projektgespräch 2026-06-24.
 * Version: 0.1.0 · Build: 302 · 2026-06-24
 */

import { describe, it, expect, beforeEach } from "vitest";
import { JSDOM } from "jsdom";

// ---------------------------------------------------------------------------
// Nachbildung der Kernlogik aus PMSTableOrganizerModule._applyProgressBorders.
// 1:1 zur Implementierung in toolbar/toolbar.js (Build 302) gehalten.
// ---------------------------------------------------------------------------
function normUrl(u) {
  return String(u || "").toLowerCase().replace(/\/$/, "");
}

function applyProgressBorders(tbody, pages) {
  const progressByUrl = {};
  (pages || []).forEach((p) => {
    if (p && p.url) progressByUrl[normUrl(p.url)] = p.progressPercent || 0;
  });

  let applied = 0;
  let matched = 0;

  Array.from(tbody.rows).forEach((row) => {
    const link = row.querySelector('a[href*="pmsnew.php"][href*="tid="]');
    if (!link) return;

    let tid = null;
    try {
      tid = new URLSearchParams(link.search).get("tid");
    } catch (e) {
      const m = (link.getAttribute("href") || "").match(/[?&]tid=(\d+)/);
      tid = m ? m[1] : null;
    }
    if (!tid) return;

    const linkedUrl = "/forum/pmsnew.php?mdl=topic&tid=" + tid;
    const key = normUrl(linkedUrl);
    const hasData = Object.prototype.hasOwnProperty.call(progressByUrl, key);
    const pct = hasData ? progressByUrl[key] : 0;
    if (hasData) matched++;

    const tr = link.closest("tr") || row;
    tr.style.setProperty("--trace-progress", pct);
    tr.classList.add("has_trace_progress");
    applied++;
  });

  return { applied, matched };
}

// ---------------------------------------------------------------------------
// Mock-DOM: PN-Übersichtstabelle (Struktur aus dem realen pmsnew.php-Ausschnitt,
// inkl. &amp;-kodierter Links und einer Zeile ohne tid-Link).
// ---------------------------------------------------------------------------
function buildPmsDOM() {
  return new JSDOM(`<!DOCTYPE html><html>
    <head><base href="http://127.0.0.2:8080/forum/pmsnew.php"></head>
    <body>
    <div id="vf" class="blocktable">
      <div class="inbox">
        <table>
          <thead><tr><th class="tcl">Dialogue</th></tr></thead>
          <tbody>
            <tr class="rowodd" id="r1">
              <td class="tcl"><a href="pmsnew.php?mdl=topic&amp;tid=85844">Bäääätsch</a></td>
            </tr>
            <tr class="roweven" id="r2">
              <td class="tcl"><a href="pmsnew.php?mdl=topic&amp;tid=82544">Willkommen</a></td>
            </tr>
            <tr class="rowodd" id="r3">
              <td class="tcl"><a href="pmsnew.php?mdl=topic&amp;tid=73049">Re: Bernd</a></td>
            </tr>
            <tr class="roweven" id="r4">
              <td class="tcl">Zeile ohne PN-Link</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </body></html>`);
}

describe("PMSTableOrganizerModule._applyProgressBorders (Build 302)", () => {
  let dom, tbody;

  beforeEach(() => {
    dom = buildPmsDOM();
    global.URLSearchParams = dom.window.URLSearchParams;
    tbody = dom.window.document.querySelector("#vf tbody");
  });

  it("setzt --trace-progress aus passenden getPages-Daten", () => {
    const pages = [
      { url: "/forum/pmsnew.php?mdl=topic&tid=85844", progressPercent: 100 },
      { url: "/forum/pmsnew.php?mdl=topic&tid=82544", progressPercent: 50 },
      // tid=73049 fehlt absichtlich → muss auf 0 fallen
    ];
    const res = applyProgressBorders(tbody, pages);

    const r1 = dom.window.document.getElementById("r1");
    const r2 = dom.window.document.getElementById("r2");
    const r3 = dom.window.document.getElementById("r3");

    expect(r1.style.getPropertyValue("--trace-progress")).toBe("100");
    expect(r2.style.getPropertyValue("--trace-progress")).toBe("50");
    expect(r3.style.getPropertyValue("--trace-progress")).toBe("0");

    expect(res.applied).toBe(3); // r4 hat keinen tid-Link
    expect(res.matched).toBe(2); // nur r1 + r2 hatten Daten
  });

  it("vergibt die Klasse has_trace_progress an jede Dialog-Zeile", () => {
    applyProgressBorders(tbody, []);
    expect(dom.window.document.getElementById("r1").classList.contains("has_trace_progress")).toBe(true);
    expect(dom.window.document.getElementById("r2").classList.contains("has_trace_progress")).toBe(true);
    expect(dom.window.document.getElementById("r3").classList.contains("has_trace_progress")).toBe(true);
  });

  it("ohne Fortschrittsdaten sind alle Dialog-Zeilen rot (pct=0)", () => {
    applyProgressBorders(tbody, []);
    ["r1", "r2", "r3"].forEach((id) => {
      expect(dom.window.document.getElementById(id).style.getPropertyValue("--trace-progress")).toBe("0");
    });
  });

  it("ignoriert Zeilen ohne PN-Dialog-Link (kein Rahmen)", () => {
    applyProgressBorders(tbody, []);
    const r4 = dom.window.document.getElementById("r4");
    expect(r4.classList.contains("has_trace_progress")).toBe(false);
    expect(r4.style.getPropertyValue("--trace-progress")).toBe("");
  });

  it("liest tid robust trotz &amp;-Kodierung im Quelltext", () => {
    // Der Link enthält im HTML &amp;tid=85844 — die tid muss dennoch greifen.
    const pages = [{ url: "/forum/pmsnew.php?mdl=topic&tid=85844", progressPercent: 88 }];
    applyProgressBorders(tbody, pages);
    expect(dom.window.document.getElementById("r1").style.getPropertyValue("--trace-progress")).toBe("88");
  });

  it("matcht URL-unabhängig von Groß-/Kleinschreibung (Normalisierung)", () => {
    const pages = [{ url: "/FORUM/PMSNEW.PHP?MDL=TOPIC&TID=82544", progressPercent: 65 }];
    applyProgressBorders(tbody, pages);
    expect(dom.window.document.getElementById("r2").style.getPropertyValue("--trace-progress")).toBe("65");
  });
});
