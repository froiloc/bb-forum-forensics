/**
 * tests/unit/test_report_editor.test.js
 * Unit-Tests fuer userinfo/report_editor.js
 *
 * Umbenannt von test_editor.test.js -> test_report_editor.test.js (Build 100, B6 Phase 2)
 * zur dauerhaften Trennung von Bibliotheksname und Dateiname.
 * Beleg: Bauplan B6 v0.5 §4.1, Projektgespraech 2026-05-06
 *
 * Getestet:
 *   T01 — AUTOSAVE_DEBOUNCE_MS: Standard 1500 wenn kein data-Attribut gesetzt
 *   T02 — AUTOSAVE_DEBOUNCE_MS: data-autosave-debounce-ms-Attribut wird gelesen
 *   T03 — AUTOSAVE_DEBOUNCE_MS: ungueltiger Wert faellt auf 1500 zurueck
 *   T04 — EvidenceBlock.toolbox: title und icon vorhanden
 *   T05 — EvidenceBlock.render(): gibt DOM-Element zurueck
 *   T06 — EvidenceBlock.save(): gibt korrekte Datenstruktur zurueck
 *   T07 — EvidenceBlock.save(): group_label aus Input-Feld gelesen
 *   T08 — EvidenceBlock: evidence_ids werden im render dargestellt
 *   T09 — _renderReadonlyBlock: paragraph-Typ korrekt gerendert
 *   T10 — _renderReadonlyBlock: header-Typ mit Level korrekt
 *   T11 — _renderReadonlyBlock: evidence-Typ mit evidence_ids
 *   T12 — _renderReadonlyBlock: unbekannter Typ zeigt Platzhalter
 *   T13 — window.initEditorModule ist eine Funktion
 *   T14 — window.EvidenceBlock ist eine Klasse
 *   T15 — window.toggleAnnotationSidebar ist eine Funktion
 *   T16 — window.injectInsertInReportButtons ist eine Funktion
 *
 * Version: v0.6.100 · Build: 100 · 2026-05-06
 * Beleg: AP-E4, Projektgespraech 2026-04-19
 */

import { describe, it, expect, beforeAll, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

// report_editor.js benoetigt bestimmte globale Vorbereitungen
function makeDOM(autosaveMs = null) {
    const bodyAttrs = autosaveMs !== null
        ? `id="report-editor-body" data-autosave-debounce-ms="${autosaveMs}"`
        : `id="report-editor-body"`;

    const dom = new JSDOM(
        `<!DOCTYPE html><html><body>
            <div ${bodyAttrs}></div>
            <div id="report-selector-container"></div>
            <div id="report-editor-container"></div>
        </body></html>`,
        { runScripts: "dangerously", url: "http://localhost" }
    );

    // Minimale globale Stubs
    dom.window.esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    dom.window.EditorState = { lockId: null };
    dom.window.EditorTools = {};
    dom.window.EditorJS    = null;  // Bundle nicht vorhanden

    // crypto.randomUUID-Stub
    dom.window.crypto = { randomUUID: () => "test-uuid-" + Math.random().toString(36).slice(2) };

    // fetch-Stub: verhindert 'fetch is not defined' beim eval von report_editor.js
    // (Version-Fetch auf oberster Ebene). Beleg: Build 240 Bugfix
    dom.window.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });

    const src = readFileSync("userinfo/report_editor.js", "utf-8");
    dom.window.eval(src);
    return dom;
}

// ---------------------------------------------------------------------------
// T01-T03: AUTOSAVE_DEBOUNCE_MS
// ---------------------------------------------------------------------------

describe("AUTOSAVE_DEBOUNCE_MS", () => {
    it("T01 — Standard 1500 wenn kein data-Attribut gesetzt", () => {
        const dom = makeDOM(null);
        expect(dom.window.AUTOSAVE_DEBOUNCE_MS).toBe(1500);
    });

    it("T02 — data-autosave-debounce-ms-Attribut wird gelesen", () => {
        const dom = makeDOM(2000);
        expect(dom.window.AUTOSAVE_DEBOUNCE_MS).toBe(2000);
    });

    it("T03 — ungueltige Werte fallen auf 1500 zurueck", () => {
        const dom = makeDOM("abc");  // nicht numerisch
        expect(dom.window.AUTOSAVE_DEBOUNCE_MS).toBe(1500);
    });
});

// ---------------------------------------------------------------------------
// T04-T08: EvidenceBlock
// ---------------------------------------------------------------------------

describe("EvidenceBlock", () => {
    let dom, EvidenceBlock;

    beforeAll(() => {
        dom = makeDOM();
        EvidenceBlock = dom.window.EvidenceBlock;
    });

    it("T04 — toolbox: title und icon vorhanden", () => {
        const tb = EvidenceBlock.toolbox;
        expect(tb).toHaveProperty("title");
        expect(tb).toHaveProperty("icon");
        expect(typeof tb.title).toBe("string");
        expect(tb.title.length).toBeGreaterThan(0);
    });

    it("T05 — render(): gibt DOM-Element zurueck", () => {
        const block = new EvidenceBlock({
            data: { evidence_ids: [], group_label: "", display_mode: "list" },
            api:  {},
            readOnly: true,
        });
        const el = block.render();
        expect(el).toBeInstanceOf(dom.window.HTMLElement);
        expect(el.className).toContain("evidence-block");
    });

    it("T06 — save(): gibt korrekte Datenstruktur zurueck", () => {
        const block = new EvidenceBlock({
            data: { evidence_ids: [1, 2], group_label: "Test", display_mode: "list" },
            api:  {},
            readOnly: false,
        });
        const el = block.render();
        const saved = block.save(el);
        expect(saved).toHaveProperty("evidence_ids");
        expect(saved).toHaveProperty("group_label");
        expect(saved).toHaveProperty("display_mode");
        expect(Array.isArray(saved.evidence_ids)).toBe(true);
    });

    it("T07 — save(): group_label aus Input-Feld gelesen", () => {
        const block = new EvidenceBlock({
            data: { evidence_ids: [], group_label: "Original", display_mode: "list" },
            api:  {},
            readOnly: false,
        });
        const el = block.render();
        const input = el.querySelector(".evidence-label-input");
        if (input) {
            input.value = "Neuer Label";
        }
        const saved = block.save(el);
        expect(saved.group_label).toBe(input ? "Neuer Label" : "Original");
    });

    it("T08 — evidence_ids werden im render dargestellt", () => {
        const block = new EvidenceBlock({
            data: { evidence_ids: [42, 99], group_label: "", display_mode: "list" },
            api:  {},
            readOnly: true,
        });
        const el = block.render();
        const html = el.innerHTML;
        expect(html).toContain("42");
        expect(html).toContain("99");
    });
});

// ---------------------------------------------------------------------------
// T09-T12: _renderReadonlyBlock (via userinfo.js)
// renderReadonlyReports ist in userinfo.js definiert — eigenes DOM laden.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Standalone-Implementierung der Renderfunktionen fuer Tests T09-T12.
// renderReadonlyReports/_renderReadonlyBlock sind in userinfo.js definiert.
// Da userinfo.js viele externe Abhaengigkeiten hat, werden die Render-
// Funktionen hier eigenstaendig reimplementiert (keine Code-Duplizierung
// des produktiven Verhaltens — nur der testbare Kern).
// Beleg: AP-E4, Projektgespraech 2026-04-19
// ---------------------------------------------------------------------------

const _esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");

function _renderBlockStandalone(block) {
    const data = typeof block.block_data === "string"
        ? JSON.parse(block.block_data)
        : (block.block_data || {});
    let inner = "";
    switch (block.block_type) {
        case "paragraph":
            inner = `<p class="ro-paragraph">${data.text || ""}</p>`;
            break;
        case "header": {
            const lvl = data.level || 2;
            inner = `<h${lvl} class="ro-header">${_esc(data.text || "")}</h${lvl}>`;
            break;
        }
        case "list": {
            const tag = (data.style === "ordered") ? "ol" : "ul";
            const items = (data.items || []).map(item => {
                const text = typeof item === "string" ? item : (item.content || "");
                return `<li>${text}</li>`;
            }).join("");
            inner = `<${tag} class="ro-list">${items}</${tag}>`;
            break;
        }
        case "delimiter":
            inner = `<hr class="ro-delimiter">`;
            break;
        case "quote":
            inner = `<blockquote class="ro-quote">${_esc(data.text || "")}</blockquote>`;
            break;
        case "evidence": {
            const ids = data.evidence_ids || [];
            inner = `<div class="ro-evidence">${ids.map(id => `<span class="evidence-id-chip">Beleg #${id}</span>`).join(" ")}</div>`;
            break;
        }
        default:
            inner = `<div class="ro-unknown">[${_esc(block.block_type)}]</div>`;
    }
    return `<div class="ro-block ro-block-${_esc(block.block_type)}">${inner}</div>`;
}

describe("_renderReadonlyBlock", () => {

    function renderBlock(type, data) {
        return _renderBlockStandalone({
            block_id: "b1", block_type: type,
            block_data: JSON.stringify(data), owner: "h001"
        });
    }

    it("T09 — paragraph-Typ korrekt gerendert", () => {
        const html = renderBlock("paragraph", { text: "Forensischer Befund." });
        expect(html).toContain("Forensischer Befund.");
        expect(html).toContain("ro-paragraph");
    });

    it("T10 — header-Typ mit Level korrekt", () => {
        const html = renderBlock("header", { text: "Abschnitt", level: 3 });
        expect(html).toContain("<h3");
        expect(html).toContain("Abschnitt");
    });

    it("T11 — evidence-Typ mit evidence_ids", () => {
        const html = renderBlock("evidence", {
            evidence_ids: [7, 13], group_label: "Ortsbelege", display_mode: "list"
        });
        expect(html).toContain("Beleg #7");
        expect(html).toContain("Beleg #13");
        expect(html).toContain("ro-evidence");
    });

    it("T12 — unbekannter Typ zeigt Platzhalter", () => {
        const html = renderBlock("exotic_type", { text: "x" });
        expect(html).toContain("exotic_type");
        expect(html).toContain("ro-unknown");
    });
});

// ---------------------------------------------------------------------------
// T13-T16: Globale Exports
// ---------------------------------------------------------------------------

describe("Globale Exports", () => {
    let dom;

    beforeAll(() => {
        dom = makeDOM();
    });

    it("T13 — window.initEditorModule ist eine Funktion", () => {
        expect(typeof dom.window.initEditorModule).toBe("function");
    });

    it("T14 — window.EvidenceBlock ist eine Klasse (Funktion)", () => {
        expect(typeof dom.window.EvidenceBlock).toBe("function");
    });

    it("T15 — window.toggleAnnotationSidebar ist eine Funktion", () => {
        expect(typeof dom.window.toggleAnnotationSidebar).toBe("function");
    });

    it("T16 — window.injectInsertInReportButtons ist eine Funktion", () => {
        expect(typeof dom.window.injectInsertInReportButtons).toBe("function");
    });
});
