/**
 * tests/unit/test_block_wrapper.test.js
 * Unit-Tests fuer den BlockWrapperManager in userinfo/report_editor.js
 *
 * Getestet:
 *   T01 — _ownerColor: gleicher Username liefert immer denselben Wert
 *   T02 — _ownerColor: verschiedene Usernames liefern unterschiedliche Farben
 *   T03 — _ownerColor: leerer Username liefert Fallback-Farbe
 *   T04 — _ownerColor: Rueckgabe ist gueltiger CSS-Farbwert (hsl-Format)
 *   T05 — initBlockWrappers: erzeugt .block-wrapper fuer bekannte .ce-block
 *   T06 — initBlockWrappers: eigener Block erhaelt block-wrapper--own
 *   T07 — initBlockWrappers: fremder Block erhaelt block-wrapper--foreign
 *   T08 — initBlockWrappers: unbekannte block_id wird nicht gewrappt
 *   T09 — initBlockWrappers: Idempotenz — doppelter Aufruf wrapt nicht doppelt
 *   T10 — initBlockWrappers: .block-meta-bar ist vorhanden
 *   T11 — initBlockWrappers: Kommentieren-Button ist vorhanden
 *   T12 — _openAccordionSection: oeffnet Sektion, schliesst andere
 *   T13 — _openAccordionSection: aria-expanded wird korrekt gesetzt
 *   T14 — _openAccordionSection: localStorage-Key wird gesetzt
 *   T15 — window.initBlockWrappers ist exportiert
 *   T16 — window.openAccordionSection ist exportiert
 *   T17 — window.ownerColor ist exportiert
 *
 * Version: v0.6.101 · Build: 101 · 2026-05-06
 * Beleg: Bauplan B6 v0.5 §4.3, §4.4, Projektgespraech 2026-05-06
 */

import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

/**
 * Erzeugt ein JSDOM mit dem minimalen HTML fuer report_editor.js-Tests.
 * Enthaelt #report-editor-body, #editorjs-holder und #support-sidebar.
 */
function makeDOM() {
    const dom = new JSDOM(
        `<!DOCTYPE html><html><body>
            <div id="report-editor-body"
                 data-username="h001"
                 data-user-id="42"
                 data-autosave-debounce-ms="1500"></div>
            <div id="editorjs-holder"></div>
            <aside id="support-sidebar">
              <section class="support-accordion-section support-accordion-section--open"
                       data-accordion="blocks">
                <button class="support-accordion-toggle"
                        aria-expanded="true"
                        aria-controls="accordion-body-blocks">Bausteine
                  <span class="support-accordion-chevron">&#x25be;</span>
                </button>
                <div id="accordion-body-blocks"
                     class="support-accordion-body"></div>
              </section>
              <section class="support-accordion-section"
                       data-accordion="annotations">
                <button class="support-accordion-toggle"
                        aria-expanded="false"
                        aria-controls="accordion-body-annotations">Annotationen
                  <span class="support-accordion-chevron">&#x25be;</span>
                </button>
                <div id="accordion-body-annotations"
                     class="support-accordion-body" hidden></div>
              </section>
              <section class="support-accordion-section"
                       data-accordion="form">
                <button class="support-accordion-toggle"
                        aria-expanded="false"
                        aria-controls="accordion-body-form">Formular
                  <span class="support-accordion-chevron">&#x25be;</span>
                </button>
                <div id="accordion-body-form"
                     class="support-accordion-body" hidden></div>
              </section>
              <section class="support-accordion-section"
                       data-accordion="comments">
                <button class="support-accordion-toggle"
                        aria-expanded="false"
                        aria-controls="accordion-body-comments">Kommentare
                  <span class="support-accordion-chevron">&#x25be;</span>
                </button>
                <div id="accordion-body-comments"
                     class="support-accordion-body" hidden>
                  <textarea class="comment-input-textarea"></textarea>
                </div>
              </section>
            </aside>
        </body></html>`,
        {
            runScripts: "dangerously",
            url: "http://localhost",
        }
    );

    // Minimale globale Stubs
    dom.window.esc        = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    dom.window.EditorState = { lockId: null };
    dom.window.EditorTools = {};
    dom.window.EditorJS    = null;
    dom.window.crypto      = { randomUUID: () => "test-uuid-" + Math.random().toString(36).slice(2) };
    dom.window.localStorage = {
        _store: {},
        getItem(k)     { return this._store[k] ?? null; },
        setItem(k, v)  { this._store[k] = String(v); },
        removeItem(k)  { delete this._store[k]; },
    };

    // fetch-Stub: verhindert 'fetch is not defined' beim eval von report_editor.js
    // (Version-Fetch auf oberster Ebene). Beleg: Build 240 Bugfix
    dom.window.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });

    const src = readFileSync("userinfo/report_editor.js", "utf-8");
    dom.window.eval(src);
    return dom;
}

/**
 * Erzeugt ein .ce-block-Element mit data-id-Attribut im #editorjs-holder.
 */
function addCeBlock(dom, blockId) {
    const holder = dom.window.document.getElementById("editorjs-holder");
    const ceBlock = dom.window.document.createElement("div");
    ceBlock.className = "ce-block";
    ceBlock.dataset.id = blockId;
    holder.appendChild(ceBlock);
    return ceBlock;
}

// ---------------------------------------------------------------------------
// T01-T04: _ownerColor / window.ownerColor
// ---------------------------------------------------------------------------

describe("ownerColor", () => {
    let dom;
    beforeAll(() => { dom = makeDOM(); });

    it("T01 — gleicher Username liefert immer denselben Wert", () => {
        const c1 = dom.window.ownerColor("h001");
        const c2 = dom.window.ownerColor("h001");
        expect(c1).toBe(c2);
    });

    it("T02 — verschiedene Usernames liefern unterschiedliche Farben", () => {
        const c1 = dom.window.ownerColor("h001");
        const c2 = dom.window.ownerColor("h002");
        // Koennen gleich sein wenn Hash-Kollision — aber praktisch verschieden
        // Mindestens muss die Funktion beide ohne Fehler ausfuehren
        expect(typeof c1).toBe("string");
        expect(typeof c2).toBe("string");
        // Bei diesen zwei Usernames sollten die Farben verschieden sein
        expect(c1).not.toBe(c2);
    });

    it("T03 — leerer Username liefert Fallback-Farbe", () => {
        const c = dom.window.ownerColor("");
        expect(c).toBe("hsl(0, 0%, 70%)");
    });

    it("T04 — Rueckgabe ist gueltiger hsl()-Farbwert", () => {
        const c = dom.window.ownerColor("h012345");
        expect(c).toMatch(/^hsl\(\d+,\s*\d+%,\s*\d+%\)$/);
    });
});

// ---------------------------------------------------------------------------
// T05-T11: initBlockWrappers / window.initBlockWrappers
// ---------------------------------------------------------------------------

describe("initBlockWrappers", () => {
    let dom;

    beforeEach(() => {
        dom = makeDOM();
    });

    // Build 120 Redesign: Dekorationen direkt auf .ce-block, kein separates .block-wrapper-Element
    it("T05 — dekoriert .ce-block fuer bekannte block_ids", () => {
        addCeBlock(dom, "blk-1");
        const blocks = [{ block_id: "blk-1", author: "h001", created_at: 1700000000 }];
        dom.window.initBlockWrappers(blocks, "h001");
        const wrapper = dom.window.document.querySelector(".ce-block[data-block-id]");
        expect(wrapper).not.toBeNull();
        expect(wrapper.dataset.blockId).toBe("blk-1");
    });

    it("T06 — eigener Block erhaelt block-wrapper--own", () => {
        addCeBlock(dom, "blk-own");
        const blocks = [{ block_id: "blk-own", author: "h001", created_at: 1700000000 }];
        dom.window.initBlockWrappers(blocks, "h001");
        const wrapper = dom.window.document.querySelector(".ce-block[data-block-id]");
        expect(wrapper.classList.contains("block-wrapper--own")).toBe(true);
        expect(wrapper.classList.contains("block-wrapper--foreign")).toBe(false);
    });

    it("T07 — fremder Block erhaelt block-wrapper--foreign", () => {
        addCeBlock(dom, "blk-foreign");
        const blocks = [{ block_id: "blk-foreign", author: "h002", created_at: 1700000000 }];
        dom.window.initBlockWrappers(blocks, "h001");
        const wrapper = dom.window.document.querySelector(".ce-block[data-block-id]");
        expect(wrapper.classList.contains("block-wrapper--foreign")).toBe(true);
        expect(wrapper.classList.contains("block-wrapper--own")).toBe(false);
    });

    // Build 121 Fallback: unbekannte Bloecke erhalten author=username als Fallback.
    // T08 prueft daher: unbekannter Block erhaelt block-wrapper--own (eigener Fallback)
    it("T08 — unbekannte block_id erhaelt Fallback-Wrapper (Build 121)", () => {
        addCeBlock(dom, "blk-unknown");
        const blocks = [{ block_id: "blk-known", author: "h001", created_at: 1700000000 }];
        dom.window.initBlockWrappers(blocks, "h001");
        // Fallback: block erhaelt eigenen username als author -> block-wrapper--own
        const wrapper = dom.window.document.querySelector(".ce-block[data-block-id]");
        expect(wrapper).not.toBeNull();
        expect(wrapper.classList.contains("block-wrapper--own")).toBe(true);
    });

    it("T09 — Idempotenz: doppelter Aufruf erzeugt nur einen Wrapper", () => {
        addCeBlock(dom, "blk-idem");
        const blocks = [{ block_id: "blk-idem", author: "h001", created_at: 1700000000 }];
        dom.window.initBlockWrappers(blocks, "h001");
        dom.window.initBlockWrappers(blocks, "h001");
        const wrappers = dom.window.document.querySelectorAll(".ce-block[data-block-id]");
        expect(wrappers.length).toBe(1);
    });

    it("T10 — .block-meta-bar ist im Wrapper vorhanden", () => {
        addCeBlock(dom, "blk-meta");
        const blocks = [{ block_id: "blk-meta", author: "h001", created_at: 1700000000 }];
        dom.window.initBlockWrappers(blocks, "h001");
        const metaBar = dom.window.document.querySelector(".block-meta-bar");
        expect(metaBar).not.toBeNull();
    });

    it("T11 — Kommentieren-Button ist im Wrapper vorhanden", () => {
        addCeBlock(dom, "blk-btn");
        const blocks = [{ block_id: "blk-btn", author: "h001", created_at: 1700000000 }];
        dom.window.initBlockWrappers(blocks, "h001");
        const btn = dom.window.document.querySelector(".block-meta-comment-btn");
        expect(btn).not.toBeNull();
        expect(btn.tagName).toBe("BUTTON");
    });
});

// ---------------------------------------------------------------------------
// T12-T14: openAccordionSection / window.openAccordionSection
// ---------------------------------------------------------------------------

describe("openAccordionSection", () => {
    let dom;

    beforeEach(() => {
        dom = makeDOM();
    });

    it("T12 — oeffnet Ziel-Sektion und schliesst alle anderen", () => {
        const sidebar = dom.window.document.getElementById("support-sidebar");
        const annotationSection = sidebar.querySelector('[data-accordion="annotations"]');
        dom.window.openAccordionSection(annotationSection);

        const sections = sidebar.querySelectorAll(".support-accordion-section");
        let openCount = 0;
        sections.forEach(s => {
            if (s.classList.contains("support-accordion-section--open")) openCount++;
        });
        expect(openCount).toBe(1);
        expect(annotationSection.classList.contains("support-accordion-section--open")).toBe(true);
    });

    it("T13 — aria-expanded wird korrekt gesetzt", () => {
        const sidebar = dom.window.document.getElementById("support-sidebar");
        const formSection = sidebar.querySelector('[data-accordion="form"]');
        dom.window.openAccordionSection(formSection);

        const formBtn  = formSection.querySelector(".support-accordion-toggle");
        const otherBtn = sidebar.querySelector('[data-accordion="blocks"] .support-accordion-toggle');
        expect(formBtn.getAttribute("aria-expanded")).toBe("true");
        expect(otherBtn.getAttribute("aria-expanded")).toBe("false");
    });

    it("T14 — localStorage-Key b6_sidebar_open wird gesetzt", () => {
        const sidebar = dom.window.document.getElementById("support-sidebar");
        const commentsSection = sidebar.querySelector('[data-accordion="comments"]');
        dom.window.openAccordionSection(commentsSection);
        expect(dom.window.localStorage.getItem("b6_sidebar_open")).toBe("comments");
    });
});

// ---------------------------------------------------------------------------
// T15-T17: Globale Exports
// ---------------------------------------------------------------------------

describe("Globale Exports (Phase 3)", () => {
    let dom;
    beforeAll(() => { dom = makeDOM(); });

    it("T15 — window.initBlockWrappers ist eine Funktion", () => {
        expect(typeof dom.window.initBlockWrappers).toBe("function");
    });

    it("T16 — window.openAccordionSection ist eine Funktion", () => {
        expect(typeof dom.window.openAccordionSection).toBe("function");
    });

    it("T17 — window.ownerColor ist eine Funktion", () => {
        expect(typeof dom.window.ownerColor).toBe("function");
    });
});
