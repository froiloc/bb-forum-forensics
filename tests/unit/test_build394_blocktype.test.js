/**
 * tests/unit/test_build394_blocktype.test.js
 * IT-Forensisches Ermittlungswerkzeug — Regressionstests Build 394
 *
 * FRONTEND-Gegenstueck zu Build 392 (Backend-Haertung).
 *
 * GEPRUEFTE FEHLER:
 *   A) Der Client sendete bei zwei Aufrufern KEIN block_type mit
 *      (report_editor.js:753 _resolveAutoPlaceholders und :2058
 *      _onPlaceholderFieldSave). Der Server nahm daraufhin 'paragraph' an und
 *      schrieb den Typ eines TABLE-/HEADER-Blocks still um — die Tabelle
 *      verschwand aus dem Bericht (beobachtetes Symptom 2).
 *   B) _refreshChipsInBlock stieg bei a:-Chips aus. Die automatisch
 *      aufgeloesten Werte wurden zwar gespeichert, aber nicht im Editor
 *      angezeigt — der Ermittler musste erst 'Aktualisieren' klicken
 *      (beobachtetes Symptom 1).
 *
 * Getestet wird gegen den ECHTEN Code (report_editor.js wird in JSDOM
 * ausgewertet), nicht gegen einen Nachbau.
 *
 * Version: v0.7.394 · Build: 394 · 2026-07-12
 * Beleg: Bugbefund Projektgespraech 2026-07-12, Bauplan Build 392/394
 */

import { describe, it, expect, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

/** Laedt report_editor.js in eine frische JSDOM (Muster: test_report_editor.test.js). */
function makeDOM() {
    const dom = new JSDOM(
        `<!DOCTYPE html><html><body>
            <div id="report-editor-body"></div>
            <div id="report-selector-container"></div>
            <div id="report-editor-container"></div>
            <div id="editorjs-holder"></div>
        </body></html>`,
        { runScripts: "dangerously", url: "http://localhost" }
    );
    dom.window.esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    dom.window.EditorState = { lockId: null };
    dom.window.EditorTools = {};
    dom.window.EditorJS    = null;
    dom.window.crypto = { randomUUID: () => "uuid-" + Math.random().toString(36).slice(2) };
    dom.window.fetch  = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });

    dom.window.eval(readFileSync("userinfo/report_editor.js", "utf-8"));
    return dom;
}

let dom;
let RE;

beforeEach(() => {
    dom = makeDOM();
    RE  = dom.window.ReportEditor;
});

// ---------------------------------------------------------------------------
// A: _buildBlockSavePayload — block_type wird nie geraten
// ---------------------------------------------------------------------------

describe("A: save_block-Payload traegt den block_type", () => {

    it("A01: Die Payload-Fabrik ist exportiert", () => {
        expect(typeof RE._buildBlockSavePayload).toBe("function");
    });

    it("A02: KERNTEST — bekannter Typ 'table' wird mitgesendet", () => {
        // Genau der Aufruf aus _resolveAutoPlaceholders: nur Werte nachtragen.
        const p = RE._buildBlockSavePayload({
            blockId:   "t-1",
            blockType: "table",
            blockData: { withHeadings: false, content: [["a", "b"]] },
            owner:     "h001",
            placeholderValues: { "auto:user.posts_total": "17" },
        });
        expect(p.block_type).toBe("table");
        expect(p.block_id).toBe("t-1");
        expect(JSON.parse(p.placeholder_values_json)["auto:user.posts_total"]).toBe("17");
    });

    it("A03: KERNTEST — Typ 'header' wird mitgesendet (Spurennummer-Ueberschrift)", () => {
        const p = RE._buildBlockSavePayload({
            blockId:   "h-1",
            blockType: "header",
            blockData: { text: "Spurenvermerk {{m:spurennummer}}", level: 2 },
            owner:     "h001",
            placeholderValues: { spurennummer: "AIW12345" },
        });
        expect(p.block_type).toBe("header");
    });

    it("A04: unbekannter Typ -> Feld wird WEGGELASSEN, nicht geraten", () => {
        // Weglassen ist sicher: der Server behaelt den gespeicherten Typ bei
        // (Build 392). Ein geratenes 'paragraph' waere der Datenverlust.
        const p = RE._buildBlockSavePayload({
            blockId:   "x-1",
            blockType: undefined,
            blockData: { text: "x" },
            owner:     "h001",
        });
        expect("block_type" in p).toBe(false);
        expect(p.block_type).toBeUndefined();
    });

    it("A05: unbekannter Typ wird NIEMALS zu 'paragraph' ergaenzt", () => {
        // Der Regressionstest gegen den urspruenglichen Fehler in seiner
        // klarsten Form.
        for (const t of [undefined, null, ""]) {
            const p = RE._buildBlockSavePayload({
                blockId: "x", blockType: t, blockData: {}, owner: "h001",
            });
            expect(p.block_type).not.toBe("paragraph");
        }
    });

    it("A06: ohne placeholderValues wird kein leeres Feld gesendet", () => {
        const p = RE._buildBlockSavePayload({
            blockId: "b", blockType: "paragraph", blockData: { text: "" },
        });
        expect("placeholder_values_json" in p).toBe(false);
    });
});

// ---------------------------------------------------------------------------
// B: _refreshChipsInBlock — a:-Chips werden aktualisiert
// ---------------------------------------------------------------------------

describe("B: Automatische Platzhalter erscheinen ohne 'Aktualisieren'", () => {

    /** Baut einen Editor-Block mit einem a:-Chip und einem m:-Chip. */
    function blockMitChips(doc) {
        const holder = doc.getElementById("editorjs-holder");
        holder.innerHTML = `
            <div class="ce-block" data-id="b-1">
                <span class="ph-chip ph-chip-auto"
                      data-chip-type="a"
                      data-chip-name="user.posts_total"
                      data-chip-default="0">user.posts_total</span>
                <span class="ph-chip ph-chip-empty"
                      data-chip-type="m"
                      data-chip-name="spurennummer"
                      data-chip-description="Spurennummer">Spurennummer *</span>
            </div>`;
        return holder;
    }

    it("B01: _refreshChipsInBlock ist exportiert", () => {
        expect(typeof RE._refreshChipsInBlock).toBe("function");
    });

    it("B02: KERNTEST — a:-Chip zeigt den aufgeloesten Wert sofort an", () => {
        const doc = dom.window.document;
        blockMitChips(doc);

        // So liegen die Werte nach _resolveAutoPlaceholders vor:
        // automatische Werte unter dem Praefix 'auto:' (Bug 2.53, Build 138).
        RE._refreshChipsInBlock("b-1", { "auto:user.posts_total": "17" });

        const chip = doc.querySelector('[data-chip-name="user.posts_total"]');
        expect(chip.textContent).toBe("17");
        // Die a:-Chip-Klasse (gruen) bleibt erhalten.
        expect(chip.classList.contains("ph-chip-auto")).toBe(true);
    });

    it("B03: a:-Chip OHNE aufgeloesten Wert bleibt unveraendert", () => {
        // Ehrlicher, als den Chip zu leeren: er zeigt weiter seinen Default.
        const doc = dom.window.document;
        blockMitChips(doc);
        RE._refreshChipsInBlock("b-1", { spurennummer: "AIW1" });

        const chip = doc.querySelector('[data-chip-name="user.posts_total"]');
        expect(chip.textContent).toBe("user.posts_total");
    });

    it("B04: m:-Chips funktionieren unveraendert weiter (keine Regression)", () => {
        const doc = dom.window.document;
        blockMitChips(doc);
        RE._refreshChipsInBlock("b-1", { spurennummer: "AIW12345" });

        const chip = doc.querySelector('[data-chip-name="spurennummer"]');
        expect(chip.textContent).toBe("AIW12345");
        expect(chip.classList.contains("ph-chip-filled")).toBe(true);
        expect(chip.classList.contains("ph-chip-empty")).toBe(false);
    });

    it("B05: a:- und m:-Chips werden im selben Durchlauf aktualisiert", () => {
        const doc = dom.window.document;
        blockMitChips(doc);
        RE._refreshChipsInBlock("b-1", {
            "auto:user.posts_total": "0",
            spurennummer: "BRU9",
        });
        expect(doc.querySelector('[data-chip-name="user.posts_total"]').textContent).toBe("0");
        expect(doc.querySelector('[data-chip-name="spurennummer"]').textContent).toBe("BRU9");
    });

    it("B06: Chips in einer TABELLENZELLE werden ebenfalls erfasst", () => {
        // Der Spurenvermerk traegt seine a:-Chips in Tabellenzellen (Build 388).
        const doc = dom.window.document;
        doc.getElementById("editorjs-holder").innerHTML = `
            <div class="ce-block" data-id="t-1">
                <table><tbody><tr>
                    <td>Anzahl Beitr\u00e4ge</td>
                    <td><span class="ph-chip ph-chip-auto"
                              data-chip-type="a"
                              data-chip-name="user.posts_total"
                              data-chip-default="0">user.posts_total</span></td>
                </tr></tbody></table>
            </div>`;

        RE._refreshChipsInBlock("t-1", { "auto:user.posts_total": "42" });
        expect(doc.querySelector('[data-chip-name="user.posts_total"]').textContent).toBe("42");
    });

    it("B07: unbekannte block_id -> kein Absturz", () => {
        expect(() => RE._refreshChipsInBlock("gibt-es-nicht", { a: "b" })).not.toThrow();
    });
});
