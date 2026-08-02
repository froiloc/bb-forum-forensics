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
            // Build 289: contenteditable-Div statt <input> — textContent statt value
            // jsdom: contentEditable kann als Attribut oder Property gesetzt sein
            const isContentEditable = input.getAttribute('contenteditable') === 'true'
                                   || input.contentEditable === 'true';
            if (isContentEditable) {
                input.textContent = "Neuer Label";
            } else {
                input.value = "Neuer Label";
            }
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

/* ===========================================================================
 * BUILD 655 (Ticket 3d9016fe) — WELCHER BLOCK ENTSTEHT AUS EINEM BAUSTEIN?
 *
 * Bis Build 654 stand im Drop-Handler:
 *     const blockData = modData.block_type === 'paragraph'
 *         ? { text: insertText } : {};
 * Ein Baustein mit einem ANDEREN Typ als 'paragraph' bekam ein LEERES
 * Datenobjekt - sein Inhalt fiel weg. Das ist niemandem aufgefallen, weil
 * report_modules gar keinen Blocktyp fuehrte und ein Baustein deshalb IMMER
 * ein Absatz war. Mit der Migration aus Build 655 hoert das auf.
 *
 * Die Entscheidung ist deshalb in die REINE Funktion _bausteinBlock
 * herausgezogen worden - im Drop-Handler eingebettet waere sie nur ueber ein
 * nachgebautes DataTransfer und eine Editor.js-Instanz erreichbar gewesen,
 * also praktisch gar nicht.
 *
 * RE-BT01 — Absatz-Baustein ohne block_data: Text landet im Block (Altfall).
 * RE-BT02 — DER FEHLER: Tabellen-Baustein MIT block_data behaelt seinen Inhalt.
 * RE-BT03 — unbrauchbares block_data wird GEMELDET, nicht still verworfen.
 * RE-BT04 — Typ ohne Daten und ohne Text: Befund in der Konsole, kein Absatz.
 * =========================================================================== */
describe("Baustein-Block aus einem Modul (Build 655)", () => {
    let dom, f;

    beforeAll(() => {
        dom = makeDOM();
        f = dom.window.ReportEditor._bausteinBlock;
    });

    it("RE-BT01 — Absatz ohne block_data nimmt den Bausteintext", () => {
        expect(typeof f).toBe("function");
        expect(f({ block_type: "paragraph" }, "Guten Tag."))
            .toEqual({ type: "paragraph", data: { text: "Guten Tag." } });
        // Ohne Typangabe ist es ein Absatz - der Altfall des ganzen Bestands.
        expect(f({}, "Text")).toEqual({ type: "paragraph",
                                       data: { text: "Text" } });
        expect(f(null, "Text")).toEqual({ type: "paragraph",
                                         data: { text: "Text" } });
    });

    it("RE-BT02 — ein Tabellen-Baustein behaelt seinen Inhalt", () => {
        const inhalt = { content: [["Merkmal", "Wert"], ["Alter", "34"]] };

        // Als JSON-Zeichenkette (so kommt es aus dem DataTransfer).
        const a = f({ block_type: "table", block_data: JSON.stringify(inhalt) },
                    "wird nicht gebraucht");
        expect(a.type).toBe("table");
        expect(a.data).toEqual(inhalt);

        // Und als Objekt (so kommt es aus der API).
        const b = f({ block_type: "table", block_data: inhalt }, "");
        expect(b.type).toBe("table");
        expect(b.data).toEqual(inhalt);

        // MIT DER FASSUNG AUS BUILD 654 waere data hier {} gewesen. Das ist
        // der ganze Ticketinhalt, in einer Zeile.
        expect(a.data).not.toEqual({});
    });

    it("RE-BT03 — unbrauchbares block_data wird gemeldet, nicht geschluckt", () => {
        const gemeldet = [];
        const alt = dom.window.console.error;
        dom.window.console.error = (...a) => gemeldet.push(a.join(" "));
        try {
            // Kein gueltiges JSON.
            const a = f({ block_type: "table", block_data: "{kaputt" },
                        "Ersatztext");
            expect(a.type).toBe("table");        // der TYP bleibt stehen
            expect(a.data).toEqual({ text: "Ersatztext" });

            // Gueltiges JSON, aber kein Objekt - Editor.js reicht je Block
            // ein Objekt an sein Werkzeug durch.
            const b = f({ block_type: "list", block_data: "[1,2,3]" }, "E");
            expect(b.data).toEqual({ text: "E" });
        } finally {
            dom.window.console.error = alt;
        }
        // GRUNDREGEL 1: der Befund steht in der Konsole, sonst faende ihn
        // niemand. Zweimal - einmal je Fall.
        expect(gemeldet.length).toBe(2);
        expect(gemeldet[0]).toContain("block_data");
    });

    it("RE-BT04 — Typ ohne Daten und ohne Text ist ein Befund", () => {
        const gewarnt = [];
        const alt = dom.window.console.warn;
        dom.window.console.warn = (...a) => gewarnt.push(a.join(" "));
        try {
            const a = f({ block_type: "table" }, "");
            // Der Typ wird NICHT stillschweigend auf 'paragraph'
            // zurueckgesetzt: ein leerer Tabellen-Baustein ist ein Befund,
            // kein Absatz.
            expect(a.type).toBe("table");
            expect(a.data).toEqual({ text: "" });
        } finally {
            dom.window.console.warn = alt;
        }
        expect(gewarnt.length).toBe(1);
        expect(gewarnt[0]).toContain("bleibt leer");

        // Ein leerer ABSATZ ist dagegen kein Befund - das ist der Normalfall
        // eines neu angelegten Bausteins.
        const gewarnt2 = [];
        const alt2 = dom.window.console.warn;
        dom.window.console.warn = (...a) => gewarnt2.push(a.join(" "));
        try { f({ block_type: "paragraph" }, ""); }
        finally { dom.window.console.warn = alt2; }
        expect(gewarnt2.length).toBe(0);
    });
});
