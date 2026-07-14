/**
 * test_build400_trace_row_uid.test.js
 * Unit-Tests: _resolveTraceElement — Topic-Zeile OHNE &uid= (Build 400)
 * Baustelle 3 · Beleg: Console-Diagnose 2026-07-13, /forum/viewforum.php?id=294
 *
 * Hintergrund:
 *   Auf viewforum.php loest _resolveTraceElement ein Token "topic:<id>" zu der
 *   zugehoerigen Tabellenzeile (<tr>) auf. Bis Build 396 verlangte der Selektor
 *   zwingend '&uid=' im viewtopic-Link. Die reale Diagnose zeigte aber:
 *     traceElements = ["topic:41623"]
 *     Zeilen-Link   = 'viewtopic.php?id=41623'  (OHNE &uid=)
 *   -> linkGefunden:false -> kein Minimap-Marker UND kein Bearbeitungsstand-
 *      Rahmen (beide leiten sich aus dem hier aufgeloesten Element ab).
 *   Build 400 macht '&uid=' optional und prueft die EXAKTE topic_id per
 *   Grenz-Regex (verhindert Praefix-Kollision 41623 <-> 416230).
 *
 * Getestet wird gegen den ECHTEN Code: toolbar.js wird im JSDOM ausgewertet,
 * _resolveTraceElement ist ueber ForensicToolbar.config.resolveTraceElement
 * freigelegt. Kein Stub -> kein "green but dead".
 *
 * GEGENPROBE: derselbe Fixture wird gegen den ALTEN (&uid=-fordernden)
 * Selektor geprueft — er liefert fuer 41623 null. Damit ist der Test an den
 * neuen Code gebunden.
 *
 * Version: 0.7.400 · Build: 400 · 2026-07-13
 */

import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

let dom;
let doc;
let resolve;   // ForensicToolbar.config.resolveTraceElement (echter Code)

beforeAll(() => {
  const src = readFileSync("toolbar/toolbar.js", "utf-8");
  dom = new JSDOM("<!DOCTYPE html><html><body></body></html>", {
    runScripts: "dangerously",
    url: "http://localhost",
  });
  dom.window.fetch = () => Promise.resolve({ ok: false, json: () => ({}) });
  dom.window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  dom.window.eval(src);
  doc = dom.window.document;
  resolve = dom.window.ForensicToolbar.config.resolveTraceElement;
});

// Reale Struktur (Auszug viewforum.php?id=294): Trace-Topic 41623 OHNE &uid=,
// ein regulaeres uid-Topic 190261 und ein Praefix-Kollisions-Topic 416230.
const PAGE = `<table><tbody>
  <tr id="r-41623" class="topic-list hover roweven iclosed inew">
    <td class="title"><span class="link-top-line">
      <a href="#294" class="title raw-link raw-topic-link"><span class="closedtext"></span> </a><a href="viewtopic.php?id=41623" id="_vt_yb8kxb">topic_title</a> <span class="byuser">von username</span>
    </span></td>
    <td class="claps">2</td><td class="replies"><span class="posts">249</span></td><td class="views"><span class="views">11.976</span></td>
  </tr>
  <tr id="r-190261" class="topic-list">
    <td class="title"><a href="viewtopic.php?id=190261&amp;uid=524888">uid_topic</a></td>
  </tr>
  <tr id="r-416230" class="topic-list">
    <td class="title"><a href="viewtopic.php?id=416230&amp;uid=524888">praefix_kollision</a></td>
  </tr>
</tbody></table>`;

beforeEach(() => {
  doc.body.innerHTML = PAGE;
});

describe("Build 400 · _resolveTraceElement (topic ohne &uid=)", () => {
  it("topic:41623 OHNE &uid= -> wird zur richtigen Zeile aufgeloest", () => {
    const tr = resolve("topic:41623");
    expect(tr).not.toBe(null);
    expect(tr.id).toBe("r-41623");
    expect(tr.tagName.toLowerCase()).toBe("tr");
  });

  it("topic:190261 MIT &uid= -> weiterhin korrekt (keine Regression)", () => {
    const tr = resolve("topic:190261");
    expect(tr).not.toBe(null);
    expect(tr.id).toBe("r-190261");
  });

  it("Praefix-Kollision: topic:41623 trifft NICHT die 416230-Zeile", () => {
    // 41623 ist Praefix von 416230 — der Grenz-Regex muss das trennen.
    const tr = resolve("topic:41623");
    expect(tr.id).toBe("r-41623");
    expect(tr.id).not.toBe("r-416230");
  });

  it("topic:416230 -> eigene Zeile (Gegenrichtung der Kollision)", () => {
    const tr = resolve("topic:416230");
    expect(tr).not.toBe(null);
    expect(tr.id).toBe("r-416230");
  });

  it("nicht vorhandenes Topic -> null", () => {
    expect(resolve("topic:999999")).toBe(null);
  });

  it("Post-Token p<id> -> getElementById (unveraenderter Pfad)", () => {
    doc.body.innerHTML = `<div class="box" id="p777"><div class="cooked">x</div></div>`;
    const el = resolve("p777");
    expect(el).not.toBe(null);
    expect(el.id).toBe("p777");
  });

  it("leerer/null Token -> null", () => {
    expect(resolve(null)).toBe(null);
    expect(resolve("")).toBe(null);
  });

  // GEGENPROBE: der ALTE Selektor (verlangt &uid=) verfehlt 41623.
  it("Gegenprobe: alter &uid=-Selektor liefert fuer 41623 null", () => {
    const link = doc.querySelector('a[href*="viewtopic.php?id=41623&uid="]');
    expect(link).toBe(null);
    // ...der neue Pfad findet die Zeile hingegen:
    expect(resolve("topic:41623")).not.toBe(null);
  });
});
