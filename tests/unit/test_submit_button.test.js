/**
 * tests/unit/test_submit_button.test.js
 * IT-Forensisches Ermittlungswerkzeug — Berichtseditor
 *
 * Testsuite fuer den Freigabe-Button "Zur Abnahme freigeben" (Build 496),
 * portiert aus dem toten userinfo/report.js in userinfo/report_editor.js.
 * Geprueft wird gegen den ECHTEN Code (eval von report_editor.js +
 * submit_dialog.js), nicht gegen einen Nachbau.
 *
 * SB01 — eigener Vermerk im Status 'draft' -> Knopf erscheint
 * SB02 — fremder Vermerk -> kein Knopf (canSubmit false)
 * SB03 — bereits eingereicht ('submitted') -> kein Knopf
 * SB04 — Klick oeffnet den Bestaetigungsdialog (SubmitDialog.open) mit Titel+cb
 * SB05 — SubmitDialog nicht geladen -> kein Knopf (defensive Degradation)
 * SB06 — erneutes Rendern leert den Slot (kein Doppel-Knopf)
 *
 * Version: v0.8.496 · Build: 496 · 2026-07-22
 * Beleg: Diagnose-Console 2026-07-22 (report.js nie geladen);
 *        documents/Berichts_Statusmodell.md.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";

function makeDom(username = "h002") {
    const dom = new JSDOM(
        `<!DOCTYPE html><html><body>
            <div id="report-editor-body" data-username="${username}"></div>
            <div id="report-selector-container"></div>
            <div id="report-editor-container"></div>
            <div id="report-selector-bar">
                <span id="btn-submit-report-slot"></span>
                <span id="report-selector-status"></span>
            </div>
        </body></html>`,
        { runScripts: "dangerously", url: "http://localhost" }
    );
    const w = dom.window;
    w.esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    w.EditorState = { lockId: null };
    w.EditorTools = {};
    w.EditorJS = null;
    w.crypto = { randomUUID: () => "t-" + Math.random().toString(36).slice(2) };
    w.fetch = () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) });
    // Echten Dialog laden (canSubmit ist die eigentliche Torwaechter-Logik).
    w.eval(readFileSync("userinfo/submit_dialog.js", "utf-8"));
    w.eval(readFileSync("userinfo/report_editor.js", "utf-8"));
    return dom;
}

const OWN_DRAFT = { id: 7, title: "Mein Vermerk", status: "draft", created_by: "h002" };

describe("Build 496 — Freigabe-Button", () => {

    it("SB01: eigener Vermerk im Status draft -> Knopf erscheint", () => {
        const w = makeDom().window;
        w.ReportEditor._setCurrentReportForTest(OWN_DRAFT);
        w.ReportEditor._renderSubmitButton();
        const btn = w.document.getElementById("btn-submit-report");
        expect(btn).not.toBeNull();
        expect(btn.textContent).toContain("Abnahme");
    });

    it("SB02: fremder Vermerk -> kein Knopf", () => {
        const w = makeDom().window;
        w.ReportEditor._setCurrentReportForTest({ ...OWN_DRAFT, created_by: "h999" });
        w.ReportEditor._renderSubmitButton();
        expect(w.document.getElementById("btn-submit-report")).toBeNull();
    });

    it("SB03: bereits eingereicht -> kein Knopf", () => {
        const w = makeDom().window;
        w.ReportEditor._setCurrentReportForTest({ ...OWN_DRAFT, status: "submitted" });
        w.ReportEditor._renderSubmitButton();
        expect(w.document.getElementById("btn-submit-report")).toBeNull();
    });

    it("SB04: Klick oeffnet den Bestaetigungsdialog mit Titel und Callback", () => {
        const w = makeDom().window;
        let opened = null;
        w.SubmitDialog.open = (doc, title, cb) => { opened = { title, cb }; return null; };
        w.ReportEditor._setCurrentReportForTest(OWN_DRAFT);
        w.ReportEditor._renderSubmitButton();
        w.document.getElementById("btn-submit-report").click();
        expect(opened).not.toBeNull();
        expect(opened.title).toBe("Mein Vermerk");
        expect(typeof opened.cb).toBe("function");
    });

    it("SB05: SubmitDialog nicht geladen -> kein Knopf", () => {
        const w = makeDom().window;
        w.SubmitDialog = undefined;
        w.ReportEditor._setCurrentReportForTest(OWN_DRAFT);
        w.ReportEditor._renderSubmitButton();
        expect(w.document.getElementById("btn-submit-report")).toBeNull();
    });

    it("SB06: erneutes Rendern erzeugt keinen Doppel-Knopf", () => {
        const w = makeDom().window;
        w.ReportEditor._setCurrentReportForTest(OWN_DRAFT);
        w.ReportEditor._renderSubmitButton();
        w.ReportEditor._renderSubmitButton();
        expect(w.document.querySelectorAll("#btn-submit-report").length).toBe(1);
    });
});
