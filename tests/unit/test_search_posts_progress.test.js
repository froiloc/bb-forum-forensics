/**
 * test_search_posts_progress.test.js
 * Unit-Tests: SearchPostsProgressModule (Build 304, vervollständigt Build 303)
 *
 * Prüft die Kernlogik der Fortschrittsrahmen auf den Treffern von
 * search.php?action=show_user_posts:
 *   - pid-Extraktion aus 'viewtopic.php?pid=<id>#p<id>' (robust gegen &amp;)
 *   - Rauschfilter: notify=-Links und Links im #notification_list raus
 *   - Zuordnung Treffer → genau eine Zeile (<tr>) der gemeinsamen Tabelle
 *   - Setzen von --trace-progress + .has_trace_progress + .has_trace_progress_tight
 *   - Unaufgelöste pids → pct=0 (roter Rahmen, einheitliches Schema)
 *
 * Das Modul ist als IIFE privat gekapselt (kein Export). Daher wird die
 * Kernlogik hier — analog zu test_pms_progress_borders.test.js (Build 302) —
 * eigenständig im jsdom-DOM nachgebildet und gegen dieselben Invarianten
 * geprüft. 1:1 zur Implementierung in toolbar/toolbar.js gehalten.
 *
 * Baustelle 3 · Beleg: Projektgespräch 2026-06-25.
 * Version: 0.1.0 · Build: 304 · 2026-06-25
 */

import { describe, it, expect, beforeEach } from "vitest";
import { JSDOM } from "jsdom";

// ---------------------------------------------------------------------------
// Nachbildung der Kernlogik aus SearchPostsProgressModule (toolbar.js, B304).
// ---------------------------------------------------------------------------
function pidOf(a) {
  try {
    const p = new URLSearchParams(a.search).get("pid");
    if (p) return p;
  } catch (e) { /* Fallback */ }
  const m = (a.getAttribute("href") || "").match(/[?&]pid=(\d+)/);
  return m ? m[1] : null;
}

function isResultLink(a) {
  const href = a.getAttribute("href") || "";
  if (/[?&]notify=/.test(href)) return false;
  if (a.closest && a.closest("#notification_list")) return false;
  return !!pidOf(a);
}

function collectRowsByPid(root) {
  const links = Array.from(
    root.querySelectorAll('a[href*="viewtopic.php"][href*="pid="]')
  ).filter(isResultLink);
  const rowsByPid = {};
  links.forEach((a) => {
    const pid = pidOf(a);
    if (!pid) return;
    const row = a.closest("tr");
    if (!row) return;
    (rowsByPid[pid] = rowsByPid[pid] || []).push(row);
  });
  return { links, rowsByPid };
}

function applyBorders(rowsByPid, posts) {
  let applied = 0, resolved = 0, unresolved = 0;
  Object.keys(rowsByPid).forEach((pid) => {
    const info = posts[pid];
    const ok = !!(info && info.resolved);
    const pct = ok ? (info.progressPercent || 0) : 0;
    if (ok) resolved++; else unresolved++;
    rowsByPid[pid].forEach((row) => {
      row.style.setProperty("--trace-progress", pct);
      row.classList.add("has_trace_progress");
      row.classList.add("has_trace_progress_tight");
      applied++;
    });
  });
  return { applied, resolved, unresolved };
}

// ---------------------------------------------------------------------------
function makeDom(bodyHtml) {
  const dom = new JSDOM(`<!DOCTYPE html><html><body>${bodyHtml}</body></html>`);
  return dom.window.document;
}

describe("SearchPostsProgressModule — pid-Extraktion", () => {
  let doc;
  beforeEach(() => { doc = makeDom(""); });

  it("liest pid aus Standard-Permalink", () => {
    const a = doc.createElement("a");
    a.setAttribute("href", "/forum/viewtopic.php?pid=1878375#p1878375");
    doc.body.appendChild(a);
    expect(pidOf(a)).toBe("1878375");
  });

  it("liest pid auch bei zusätzlichen Parametern", () => {
    const a = doc.createElement("a");
    a.setAttribute("href", "/forum/viewtopic.php?notify=562278&pid=1893594#p1893594");
    doc.body.appendChild(a);
    expect(pidOf(a)).toBe("1893594");
  });
});

describe("SearchPostsProgressModule — Rauschfilter", () => {
  it("schließt notify=-Links aus", () => {
    const doc = makeDom(
      '<a href="/forum/viewtopic.php?notify=1&pid=999#p999">x</a>'
    );
    const a = doc.querySelector("a");
    expect(isResultLink(a)).toBe(false);
  });

  it("schließt Links im #notification_list aus", () => {
    const doc = makeDom(
      '<div id="notification_list"><a href="/forum/viewtopic.php?pid=999#p999">x</a></div>'
    );
    const a = doc.querySelector("a");
    expect(isResultLink(a)).toBe(false);
  });

  it("akzeptiert echte Treffer-Links", () => {
    const doc = makeDom(
      '<table><tbody><tr><td><a href="/forum/viewtopic.php?pid=123#p123">x</a></td></tr></tbody></table>'
    );
    const a = doc.querySelector("a");
    expect(isResultLink(a)).toBe(true);
  });
});

describe("SearchPostsProgressModule — Zeilenzuordnung", () => {
  it("ordnet jeden Treffer genau einer <tr> zu, ignoriert Rauschen", () => {
    const doc = makeDom(`
      <div id="notification_list">
        <ul><li><a href="/forum/viewtopic.php?notify=5&pid=900#p900">n</a></li></ul>
      </div>
      <table class="this"><tbody>
        <tr><td><a href="/forum/viewtopic.php?pid=100#p100">A</a></td></tr>
        <tr><td><a href="/forum/viewtopic.php?pid=200#p200">B</a></td></tr>
        <tr><td><a href="/forum/viewtopic.php?pid=300#p300">C</a></td></tr>
      </tbody></table>
    `);
    const { links, rowsByPid } = collectRowsByPid(doc);
    expect(links.length).toBe(3);                 // notify-Link draußen
    expect(Object.keys(rowsByPid).sort()).toEqual(["100", "200", "300"]);
    expect(rowsByPid["100"][0].tagName).toBe("TR");
  });
});

describe("SearchPostsProgressModule — Rahmen anwenden", () => {
  let doc, rowsByPid;
  beforeEach(() => {
    doc = makeDom(`
      <table><tbody>
        <tr id="r1"><td><a href="/forum/viewtopic.php?pid=100#p100">A</a></td></tr>
        <tr id="r2"><td><a href="/forum/viewtopic.php?pid=200#p200">B</a></td></tr>
        <tr id="r3"><td><a href="/forum/viewtopic.php?pid=300#p300">C</a></td></tr>
      </tbody></table>
    `);
    rowsByPid = collectRowsByPid(doc).rowsByPid;
  });

  it("setzt Fortschritt + beide Klassen je Zeile", () => {
    const posts = {
      "100": { resolved: true, progressPercent: 100 },
      "200": { resolved: true, progressPercent: 50 },
      "300": { resolved: false },
    };
    const stats = applyBorders(rowsByPid, posts);
    expect(stats.applied).toBe(3);
    expect(stats.resolved).toBe(2);
    expect(stats.unresolved).toBe(1);

    const r1 = doc.getElementById("r1");
    expect(r1.style.getPropertyValue("--trace-progress")).toBe("100");
    expect(r1.classList.contains("has_trace_progress")).toBe(true);
    expect(r1.classList.contains("has_trace_progress_tight")).toBe(true);

    const r2 = doc.getElementById("r2");
    expect(r2.style.getPropertyValue("--trace-progress")).toBe("50");

    // Unaufgelöst → pct=0 (rot), aber Rahmen dennoch gesetzt.
    const r3 = doc.getElementById("r3");
    expect(r3.style.getPropertyValue("--trace-progress")).toBe("0");
    expect(r3.classList.contains("has_trace_progress")).toBe(true);
  });

  it("fehlender Endpunkt-Eintrag → pct=0 (rot)", () => {
    const stats = applyBorders(rowsByPid, {}); // gar keine Auflösung
    expect(stats.unresolved).toBe(3);
    expect(doc.getElementById("r1").style.getPropertyValue("--trace-progress")).toBe("0");
  });
});
