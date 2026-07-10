/**
 * test_toc_build.test.js
 * Unit-Tests: buildTableOfContents() aus userinfo.js (Inhaltsverzeichnis).
 *
 * Beleg: Bauplan Userinfo-Verschoenerung v0.2 Pkt.5, mc 2026-07-10.
 *
 * Anti-"gruen aber tot" (B4-S12): Der Test evaluiert die ECHTE Funktion aus
 * userinfo.js — sie wird per Klammer-Matching aus der Datei extrahiert und im
 * jsdom-Kontext ausgefuehrt, statt die Logik im Test zu duplizieren. So kann
 * eine Divergenz zwischen Test-Kopie und Produktivcode nicht entstehen.
 *
 * Muster wie test_navigate_to_url.test.js: eigenes JSDOM je Test.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

// --- Echte Funktion aus userinfo.js per Klammer-Matching extrahieren --------
function extractFn(src, name) {
    const start = src.indexOf("function " + name);
    if (start < 0) throw new Error("Funktion nicht gefunden: " + name);
    const braceStart = src.indexOf("{", start);
    let depth = 0, i = braceStart;
    for (; i < src.length; i++) {
        const c = src[i];
        if (c === "{") depth++;
        else if (c === "}") { depth--; if (depth === 0) { i++; break; } }
    }
    return src.slice(start, i);
}

const SRC    = readFileSync(join(__dirname, "../../userinfo/userinfo.js"), "utf-8");
const escSrc = extractFn(SRC, "esc");
const tocSrc = extractFn(SRC, "buildTableOfContents");

const OUTER = `
  <nav id="ui-toc" hidden></nav>
  <div class="ui-body">
    <div class="ui-card"><h2>Aktivitaet im Forum</h2></div>
    <div class="ui-card"><h2>Forensische Metadaten</h2></div>
  </div>
  <div id="userinfo-static">
    <details class="forensic-section" open>
      <summary class="forensic-section-title">Stammdaten</summary>
    </details>
    <details class="forensic-section">
      <summary class="forensic-section-title">Stammdaten</summary>
    </details>
  </div>`;

// Baut JSDOM, injiziert die ECHTE Funktion und ruft sie im dortigen Scope auf.
function runTocIn(bodyHtml) {
    const dom = new JSDOM(`<!DOCTYPE html><html><body>${bodyHtml}</body></html>`, {
        url: "http://127.0.0.2:8080",
    });
    const win = dom.window;
    // jsdom implementiert scrollIntoView nicht — harmloser Stub gegen Konsolen-
    // Rauschen. Die Funktion selbst ruft es nur auf, prueft aber nichts daran.
    win.Element.prototype.scrollIntoView = function () {};
    // eslint-disable-next-line no-new-func
    const factory = new win.Function(
        "document", "window", "_dbg",
        `${escSrc}\n${tocSrc}\nreturn buildTableOfContents;`
    );
    const fn = factory(win.document, win, () => {});
    fn();
    return dom;
}

describe("userinfo.js — buildTableOfContents()", () => {
    it("erfasst beide Kartensorten (ui-card + forensic-section)", () => {
        const dom = runTocIn(OUTER);
        const links = dom.window.document.querySelectorAll("#ui-toc a");
        expect(links.length).toBe(4);
        const texts = Array.from(links).map((a) => a.textContent);
        expect(texts).toContain("Aktivitaet im Forum");
        expect(texts).toContain("Stammdaten");
    });

    it("vergibt eindeutige Anker-ids (Kollisions-Suffix bei doppeltem Titel)", () => {
        const dom = runTocIn(OUTER);
        const sections = dom.window.document.querySelectorAll("#userinfo-static details");
        expect(sections[0].id).toBeTruthy();
        expect(sections[1].id).toBeTruthy();
        expect(sections[0].id).not.toBe(sections[1].id);
    });

    it("Links zeigen auf vergebene ids; #ui-toc wird sichtbar", () => {
        const dom = runTocIn(OUTER);
        const doc = dom.window.document;
        expect(doc.getElementById("ui-toc").hasAttribute("hidden")).toBe(false);
        doc.querySelectorAll("#ui-toc a").forEach((a) => {
            expect(doc.getElementById(a.dataset.tocTarget)).not.toBeNull();
        });
    });

    it("leerer Fall: keine Karten -> #ui-toc bleibt versteckt", () => {
        const dom = runTocIn(`<nav id="ui-toc" hidden></nav>`);
        expect(dom.window.document.getElementById("ui-toc").hidden).toBe(true);
    });

    it("Klick klappt geschlossenes <details> auf", () => {
        const dom = runTocIn(OUTER);
        const doc = dom.window.document;
        const closed = doc.querySelectorAll("#userinfo-static details")[1];
        expect(closed.open).toBe(false);
        const link = doc.querySelector(`#ui-toc a[data-toc-target="${closed.id}"]`);
        link.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
        expect(closed.open).toBe(true);
    });
});
