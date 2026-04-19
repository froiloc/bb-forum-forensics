/**
 * test_form_intercept.test.js
 * Unit-Tests: Form-Submit-Abfangung und loadPage(method) in toolbar.js
 *
 * Getestete Verhaltensweisen:
 *   F01: loadPage(url, false, 'POST') → API-URL enthält &original_method=POST
 *   F02: loadPage(url, false, 'GET')  → API-URL ohne original_method=POST
 *   F03: loadPage(url, false)         → API-URL ohne original_method=POST (Default)
 *   F04: loadPage(url, false, 'post') → normalisiert zu POST
 *   F05: Form-Submit method="post"    → API-URL enthält original_method=POST
 *   F06: Form-Submit method="get"     → API-URL ohne original_method=POST
 *   F07: Form auf externer URL        → kein /_forensic/page-Aufruf
 *
 * Beleg: Projektgespräch 2026-04-19
 * Version: 0.1.0 · Build: 042 · 2026-04-19
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { JSDOM } from "jsdom";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { dirname, join } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TOOLBAR_SRC = readFileSync(
    join(__dirname, "../../toolbar/toolbar.js"), "utf-8"
);

// ---------------------------------------------------------------------------
// Hilfsfunktionen
// ---------------------------------------------------------------------------

/** Minimale fetch-Antwort die einen validen Envelope simuliert. */
function makeEnvelopeResponse(html = "<p>ok</p>") {
    return {
        ok: true,
        json: () => Promise.resolve({
            in_scope:       true,
            fetch_failed:   false,
            html,
            head: {
                title:         "T",
                base_href:     "/forum/",
                stylesheets:   [],
                inline_styles: [],
            },
            scrape_context: "user",
            url_canonical:  "/forum/viewtopic.php?id=42",
            fragment:       null,
            trace_elements: [],
        }),
    };
}

/**
 * Baut ein frisches JSDOM-Fenster mit toolbar.js und gibt es zurück.
 * fetch ist gemockt; DOMContentLoaded wird manuell ausgelöst.
 *
 * Rückgabe:
 *   { window, fetchMock, flushInitial }
 *   flushInitial() — wartet bis DOMContentLoaded-Handler fertig ist
 */
async function setupWindow(viewportHtml = "") {
    const dom = new JSDOM(
        `<!DOCTYPE html><html><head></head><body>
           <div id="forensic-toolbar"></div>
           <div id="forensic-viewport">${viewportHtml}</div>
         </body></html>`,
        {
            url:        "http://127.0.0.2:8080",
            runScripts: "dangerously",
            resources:  "usable",
        }
    );
    const { window } = dom;

    const fetchMock = vi.fn().mockResolvedValue(makeEnvelopeResponse());
    window.fetch = fetchMock;
    window.requestAnimationFrame = (cb) => setTimeout(cb, 0);

    // toolbar.js evaluieren — DOMContentLoaded-Handler wird registriert
    window.eval(TOOLBAR_SRC);

    // DOMContentLoaded manuell feuern (JSDOM feuert ihn nicht automatisch)
    const dce = new window.Event("DOMContentLoaded");
    window.document.dispatchEvent(dce);

    // Initialaufruf abwarten, dann Mock zurücksetzen
    await new Promise((r) => setTimeout(r, 50));
    fetchMock.mockClear();

    return { window, fetchMock };
}

/** Filtert fetch-Aufrufe an /_forensic/page heraus. */
function pageCalls(fetchMock) {
    return fetchMock.mock.calls
        .map((c) => c[0])
        .filter((u) => typeof u === "string" && u.includes("/_forensic/page"));
}

// ---------------------------------------------------------------------------
// Tests: loadPage(url, push, method) — direkte API
// ---------------------------------------------------------------------------

describe("toolbar.js — loadPage mit method-Parameter", () => {

    it("F01: loadPage mit 'POST' → API-URL enthält original_method=POST", async () => {
        const { window, fetchMock } = await setupWindow();

        window.ForensicToolbar.navigation.loadPage(
            "/forum/viewtopic.php?id=42", false, "POST"
        );
        await new Promise((r) => setTimeout(r, 50));

        const calls = pageCalls(fetchMock);
        expect(calls.length).toBe(1);
        expect(calls[0]).toContain("original_method=POST");
        expect(calls[0]).toContain(encodeURIComponent("/forum/viewtopic.php?id=42"));
    });

    it("F02: loadPage mit 'GET' → API-URL enthält KEIN original_method=POST", async () => {
        const { window, fetchMock } = await setupWindow();

        window.ForensicToolbar.navigation.loadPage(
            "/forum/viewtopic.php?id=42", false, "GET"
        );
        await new Promise((r) => setTimeout(r, 50));

        const calls = pageCalls(fetchMock);
        expect(calls.length).toBe(1);
        expect(calls[0]).not.toContain("original_method=POST");
    });

    it("F03: loadPage ohne method → kein original_method=POST (Default GET)", async () => {
        const { window, fetchMock } = await setupWindow();

        window.ForensicToolbar.navigation.loadPage(
            "/forum/viewtopic.php?id=42", false
        );
        await new Promise((r) => setTimeout(r, 50));

        const calls = pageCalls(fetchMock);
        expect(calls.length).toBe(1);
        expect(calls[0]).not.toContain("original_method=POST");
    });

    it("F04: loadPage mit 'post' (lowercase) → normalisiert zu POST", async () => {
        const { window, fetchMock } = await setupWindow();

        window.ForensicToolbar.navigation.loadPage(
            "/forum/viewtopic.php?id=42", false, "post"
        );
        await new Promise((r) => setTimeout(r, 50));

        const calls = pageCalls(fetchMock);
        expect(calls.length).toBe(1);
        expect(calls[0]).toContain("original_method=POST");
    });
});

// ---------------------------------------------------------------------------
// Tests: Form-Submit-Abfangung (_interceptLinks aufgerufen via page:loaded)
// ---------------------------------------------------------------------------

describe("toolbar.js — Form-Submit-Abfangung", () => {

    /**
     * Hilfsfunktion: Lädt eine Seite via loadPage und wartet bis
     * _interceptLinks auf dem viewport-Inhalt gelaufen ist.
     * Gibt die Form im neu geladenen viewport zurück.
     */
    async function loadPageWithForm(window, fetchMock, formHtml, url = "/forum/viewtopic.php?id=42") {
        // fetch-Mock so konfigurieren, dass der Viewport-HTML unsere Form enthält
        fetchMock.mockResolvedValueOnce(makeEnvelopeResponse(formHtml));
        window.ForensicToolbar.navigation.loadPage(url, false, "GET");
        await new Promise((r) => setTimeout(r, 60));
        // Nach _handleEnvelope ist der viewport mit formHtml befüllt
        return window.document.querySelector("#forensic-viewport form");
    }

    it("F05: POST-Form-Submit → API-URL enthält original_method=POST", async () => {
        const { window, fetchMock } = await setupWindow();

        const form = await loadPageWithForm(
            window, fetchMock,
            `<form action="/forum/viewtopic.php?id=42" method="post">
               <input type="submit" value="Abstimmen">
             </form>`
        );
        expect(form).not.toBeNull();

        fetchMock.mockClear();

        const evt = new window.Event("submit", { bubbles: true, cancelable: true });
        form.dispatchEvent(evt);
        await new Promise((r) => setTimeout(r, 50));

        const calls = pageCalls(fetchMock);
        expect(calls.length).toBe(1);
        expect(calls[0]).toContain("original_method=POST");
        expect(calls[0]).toContain(encodeURIComponent("/forum/viewtopic.php?id=42"));
    });

    it("F06: GET-Form-Submit → API-URL enthält KEIN original_method=POST", async () => {
        const { window, fetchMock } = await setupWindow();

        const form = await loadPageWithForm(
            window, fetchMock,
            `<form action="/forum/search.php" method="get">
               <input type="submit" value="Suchen">
             </form>`,
            "/forum/search.php"
        );
        expect(form).not.toBeNull();

        fetchMock.mockClear();

        const evt = new window.Event("submit", { bubbles: true, cancelable: true });
        form.dispatchEvent(evt);
        await new Promise((r) => setTimeout(r, 50));

        const calls = pageCalls(fetchMock);
        expect(calls.length).toBe(1);
        expect(calls[0]).not.toContain("original_method=POST");
        expect(calls[0]).toContain(encodeURIComponent("/forum/search.php"));
    });

    it("F07: Form-Submit auf externer URL → kein /_forensic/page-Aufruf", async () => {
        const { window, fetchMock } = await setupWindow();

        const form = await loadPageWithForm(
            window, fetchMock,
            `<form action="https://external.example.com/data" method="post">
               <input type="submit" value="Extern">
             </form>`
        );
        expect(form).not.toBeNull();

        fetchMock.mockClear();

        const evt = new window.Event("submit", { bubbles: true, cancelable: true });
        form.dispatchEvent(evt);
        await new Promise((r) => setTimeout(r, 50));

        // Kein Aufruf mit externer URL
        const calls = pageCalls(fetchMock);
        const externalCalls = calls.filter((u) => u.includes("external.example.com"));
        expect(externalCalls.length).toBe(0);
    });
});
